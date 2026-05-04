import numpy as np
from astropy.io import fits
from typing import List
import polars as pl
from .io import FITSIDI, read_idi
from datetime import datetime, timedelta
from astropy.time import Time, TimeDelta
from avica.util import compute_sep
from avica.config import avica_data_dir

from avica.sources import check_band
from urllib import request

from pathlib import Path
from collections import Counter

# ______________________________________________

class IdiHDUAstropy(fits.PrimaryHDU):
    @classmethod
    def match_header(cls, header):
        try:
            keyword = header.cards[0].keyword
        except Exception:
            keyword = header.ascard[0].key
            pass

        return (keyword == 'SIMPLE' and 'GROUPS' in header and
            header['GROUPS'] == True and 'NAXIS' in header and header['NAXIS'] == 0)

fits.register_hdu(IdiHDUAstropy)

# ______________________________________________

def dict_baseline(fitsfile=None,hdul=None):
    """
    For each baseline stores tuple of (distance, label, (id_an1, id_an2)).
    Args:
        fitsfile (str, optional): Path to the fitsfile. Defaults to None.
        hdul (FITSIDI.IdiHDUList, optional): hdul instance. Defaults to None.

    Raises:
        ValueError: If neither path or hdul is given.

    Returns:
        Dict: dict_baseline. (distance, label, (id_an1, id_an2)).
    """
    fo = None
    from scipy.spatial import distance
    if hdul is None:
        if fitsfile is None: raise ValueError("missing fits file path or hdul")
        else:
            fo = FITSIDI(fitsfile)
            hdul=fo.read()
    xyz,annames=hdul['ARRAY_GEOMETRY']['STABXYZ'], hdul['ARRAY_GEOMETRY']['ANNAME']

    dict_baseline={}

    for i,an1 in enumerate(annames):
        for j,an2 in enumerate(annames):
                d=distance.euclidean(xyz[i],xyz[j])*.001
                baseline_label=f"{an1}-{an2}"
                baseline_id=(i+1)*256+(j+1)
                dict_baseline[baseline_id]=(d,baseline_label,(i+1,j+1))
    if fo: fo.close()
    return dict_baseline


def _gethduname(hdul, hdu_names:List[str]):
    hdu_ids = []
    hdu_name = ''
    for i,hdu_found in enumerate(hdul.names) :
        for col_given in hdu_names:
            if col_given in hdu_found:
                hdu_ids.append(i)
                hdu_name = hdu_found
    return hdu_name, hdu_ids

def get_hduname(hdul, hdu_names:List[str])-> tuple[str, List]:
    """fuzzy search for hdu name.

    Args:
        hdul (FITSIDI.IdiHDUList): hdul from FITSIDI.open().
        hdu_names (List[str]): name of hdus for which to retrieve ids and true name.

    Returns:
        List[str, List[str]]: [hdu_name, hdu_ids]
    """
    return _gethduname(hdul=hdul,hdu_names=hdu_names)


def _getcolname(hdu, cols:List[str]):
    colfound = [col_found for col_found in hdu.cols for col_given in cols if col_given in col_found]
    if len(colfound):
        colfound=colfound[0]
    else:
        raise NameError(f"column not found for {cols}")
    return colfound

def get_colname(hdu, cols:List[str])->str:
    """fuzzy search for hdu column name.

    Args:
        hdu (FITSIDI.IdiHDU): hdu from hdul.
        cols (List[str]): name of columns for which to retrieve the true name.

    Returns:
        str: col_found
    """
    return _getcolname(hdu=hdu,cols=cols)

def get_yyyymmdd(dateobs):
    """
    Takes FITS DATE-OBS with fromat : yy/mm/dd or dd-mm-yyyy and returns (yyyy,mm,dd)
    Args:
        dateobs (str): FITS DATE-OBS/RDATE format

    Returns:
        tuple: (yyyy,mm,dd)
    """
    yyyy, mm, dd = 0,0,0
    try:
        dateobs = [int(d) for d in dateobs.split('-')]
        yyyy = dateobs[0]
        mm, dd = dateobs[1], dateobs[2]
    except Exception:
        dateobs = [int(d) for d in dateobs.split('/')]
        yyyy = dateobs[2]+1900 if 90<=dateobs[2]<=99 else dateobs[2]+2000
        mm, dd = dateobs[1], dateobs[0]
    return yyyy,mm,dd




# -------------- reading from table


def datetimerange_fromfits(fitsfile):
    """
    Returns
    ---

    (yday_start, yday_end)
    """
    fo            =   FITSIDI(fitsfile)
    hdul = fo.read(5)

    hduname, lids = _gethduname(hdul,['UV_DATA'])

    startyday=(Time(hdul[lids[0]]['DATE'][0], format='jd') + TimeDelta(hdul[lids[0]]['TIME'][0], format='jd')).yday
    nrows = hdul[lids[-1]].nrows
    fo.read(10, start_row=nrows-5)

    endyday=(Time(hdul[lids[-1]]['DATE'][-1], format='jd') + TimeDelta(hdul[lids[-1]]['TIME'][-1], format='jd')).yday

    fo.close()
    return startyday, endyday

def get_dateobs(fitsfile):
    fo            =   FITSIDI(fitsfile)
    hdul = fo.read()
    fo.close()

    dateobs         =   hdul[0].header['DATE-OBS']
    yyyy,mm,dd      =   get_yyyymmdd(dateobs)
    return datetime(yyyy, mm, dd)


def count_tsys_in_fitsfile(fitsfile, target=None):
    fo              =   FITSIDI(fitsfile, mode='r', )
    count_tsys      =   0

    with fo.open() as fop:
        hdul            =   fop.read()
        source_hdu      =   hdul['SOURCE']

        if 'SYSTEM_TEMPERATURE' in hdul.names:
            tsys_hdu        =   hdul['SYSTEM_TEMPERATURE']
            sid_colname     =   _getcolname(source_hdu, ['ID_NO', 'ID_NO.', 'SOURCE_ID', 'SOURCE ID', 'SOURCE_ID.'])
            count_tsys      =   tsys_hdu.nrows

            if target:
                # target_names    =   source_hdu['SOURCE']
                sid             =   source_hdu.df.filter(pl.col('SOURCE')==target)[sid_colname].to_list()[0]
                tsyssid_colname     =   _getcolname(tsys_hdu, ['ID_NO','ID_NO.', 'SOURCE_ID', 'SOURCE ID', 'SOURCE_ID.'])
                count_tsys      =   len(tsys_hdu.df.filter(pl.col(tsyssid_colname)==sid)[tsyssid_colname].to_list())
    return count_tsys


# _____________________________________________________________     find reference antenna / sources


def identify_refant(fitsfile, n=4, refants=[], **kwargs):
    """
    returns dataframe of first "n" best refants has id as the index
    TODO: use SEFD instead of TSYS.
    """
    refant_found, _ = find_refant(fitsfile, **kwargs)

    if len(refants):
        refant_found = refant_found.filter(pl.col("ANNAME").is_in(refants))
    refants = refant_found[:n]['ANNAME'].to_list()
    dict_refant_selection = refant_found.to_dict(as_series=False)
    return refants, dict_refant_selection

"""

    Returns:


    (pandas dataframe)
    sorted dataframe in order of best antenna.

    if return_onmissing is True, returns False for missing TSYS info.

    columns

    ANNAME      : Antenna Name
    STD_TSYS    : Standard Deviation in the TSYS value
    nRows       : number of rows for each station/anenna
    Distance    : Centroid distance for each station/antenna
    c           : confidence value taken as the multiplication of the normalized three values.

    TODO: prompt on nan values when present in TSYS

    """

def find_refant(fitsfile, verbose=True, err_onmissing=False, tsys_wt=0.99, nrows_wt=0.95, distance_wt=0.80):
    """
    Takes fitsfile as input and returns the reference antenna which is sorted in descending by combination of
    geometrically, observation length, and by TSYS variability, weights determine preference in parameter.
    Prints table with columns [ANNAME,STD_TSYS,nRows,Distance,c] sorted by best reference antenna.

    Note:
        This logic applies only to identifying the reference antenna using ``TSYS``, ``NROWS_TSYS``,
        and ``ANTENNA_DIST`` from the FITS-IDI file. Use with caution — these parameters alone
        may not be sufficient to determine a reliable reference antenna.

    Args:
        fitsfile (str): path for the fitsfile.
        verbose (bool, optional): prints generated output. Defaults to True.
        err_onmissing (bool, optional): raises error if SYSTEM_TEMPERATURE is missing. Defaults to False.
        tsys_wt (float, optional): weight corresponding to the TSYS variability. Defaults to 0.99.
        nrows_wt (float, optional): weight corresponding to the number of rows found in TSYS. Defaults to 0.95.
        distance_wt (float, optional): weight corresponding to the centroid distance. Defaults to 0.80.

    Raises:
        ValueError:  if SYSTEM_TEMPERATURE is missing

    Returns:
        (pl.DataFrame, str): table_containing result and printable output.
    """
    fo      =   FITSIDI(fitsfile=fitsfile)
    fo.open()
    hdul    =   fo.read()

    hduname,_=_gethduname(hdul, ['SYSTEM_TEMPERATURE'])

    if hduname:
        from scipy.spatial import distance
        tsys1=hdul[hduname]['TSYS_1']                                                                # This axis should be always present
        tsys2=None
        antenna_d=hdul['ANTENNA']

        if 'TSYS_2' in hdul[hduname].cols:  tsys2=hdul[hduname]['TSYS_2']

        tsysantenna                 =   np.array(hdul[hduname]['ANTENNA_NO'])
        antenna_dict        =   dict(zip(antenna_d['ANTENNA_NO'],(antenna_d['ANNAME'])))
        xyz,anname_geom     =   np.array(hdul['ARRAY_GEOMETRY']['STABXYZ']), np.array(hdul['ARRAY_GEOMETRY']['ANNAME'])

        anlist,tsys1_std,tsys2_std,ancountlist,missing_antennav =   [],[],[],[],[]
        ancount             =   Counter(tsysantenna)
        med_d               =   []

        for ant in antenna_dict.keys():

            ant_mask           =   np.where(tsysantenna==ant)                                                # mask for each antenna for all sources in TSYS table
            if len(ant_mask[0]):
                anlist.append(antenna_dict[ant])
                tsys1_std.append(np.nanmedian((np.nanstd(tsys1[ant_mask], axis=0))))                         # Calculates standard deviation for each ants and then takes median
                if tsys2 is not None: tsys2_std.append(np.nanmedian((np.nanstd(tsys2[ant_mask], axis=0))))
                ancountlist.append(ancount[ant])
            else:
                missing_antennav.append(antenna_dict[ant])


            d=[]
            refcoord=xyz[np.where(anname_geom==antenna_dict[ant])][0]

            for i,v in enumerate(xyz):
                d.append(distance.euclidean(refcoord,v)*.001)                                       # Distance of all from one refant
            med_d.append((antenna_dict[ant],np.nanmedian(d)))                                          # Median distance of all ants for one refant

        ant_with_d=dict(med_d)

        if len(tsys2_std) == len(tsys1_std):
            tsys_std=np.nanmedian([tsys1_std,tsys2_std],axis=0)                                        # Calculate median if TSYS1 and TSYS2 both are present

        else:
            tsys_std=tsys1_std

        data        =   [anlist,tsys_std,ancountlist]
        names       =   ('ANNAME', 'STD_TSYS','nRows')
        t           =   pl.DataFrame(dict(zip(names, data)))
        t.meta      =   {'name':'ANTENNA TSYS Variance'}

        t           =   (t.with_columns(pl.col("ANNAME").replace(ant_with_d).alias("Distance").cast(pl.Float64))
                        .with_columns(
                            max_s = pl.col("STD_TSYS").max(),
                            max_n = pl.col("nRows").max(),
                            max_d = pl.col("Distance").max())
                        .with_columns(c = ((1 - (pl.col("STD_TSYS") / pl.col("max_s"))) * tsys_wt +
                                           (pl.col("nRows") / pl.col("max_n")) * nrows_wt +
                                            (1 - (pl.col("Distance") / pl.col("max_d"))) * distance_wt
                                            ) / (tsys_wt + nrows_wt + distance_wt))
                        .drop(["max_s", "max_n", "max_d"])
                        .sort("c", descending=True))
        print_out   =   str(t)
        if verbose: print(print_out)
        return t, print_out
    else:
        if verbose: print('missing TSYS info!\n')
        if err_onmissing: raise ValueError("SYSTEM_TEMPERATURE not found!")
    return False, False




def catalog_search_from_fits(fitsfile, df_catalog, seplimit, thres_sep, source_name_col='Obsname',
                             frame='icrs', include_not_found=False, verbose=False, outdir=''):
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from pandas import concat, DataFrame as df

    if source_name_col in df_catalog.columns:
        df_catalog  =   df_catalog.drop_duplicates(subset=source_name_col, keep='first')

    hdul            =   read_idi(fitsfile)

    source_hdu      =   hdul['SOURCE']

    target_names    =   source_hdu['SOURCE']
    idx_found       =   np.zeros(np.shape(target_names), dtype=bool)        # i.e not found

    sid_colname     =   get_colname(source_hdu, ['ID_NO','ID_NO.', 'SOURCE_ID', 'SOURCE ID'])

    sids            =   source_hdu[sid_colname]
    ra              =   source_hdu['RAEPO']*u.deg
    dec             =   source_hdu['DECEPO']*u.deg
    target_coords   =   SkyCoord(ra,dec, frame=frame)
    epoch           =   np.unique(source_hdu['EPOCH'])


    if not len(epoch)==1: raise NotImplementedError(f'Multiple EQUINOX values are not supported yet : {epoch}')

    # _________________________________________________________________            searching by name first

    match_res       =   df_catalog[df_catalog[source_name_col].isin(target_names)]

    if not match_res.empty:
        idx_found       =   np.in1d(target_names, match_res[source_name_col].values)

    # _________________________________________________________________            since each row found corrosponds to the name match from fits
    if source_name_col in match_res.columns: match_res            =   match_res.rename(columns={source_name_col:'fits_target'})

    if 'fits_target' in match_res.columns: match_res['sep'] =   match_res.apply(lambda row: compute_sep(row, target_names, target_coords, frame), axis=1 )

    if any(~idx_found):
        if verbose: print("  searching by coordinate for..."," ".join(target_names[~idx_found]))

        catalog                             =   SkyCoord(df_catalog['coordinate'].values, unit=(u.hourangle, u.deg), frame=frame)

        idxtarget, idxself, sep2d, dist3d   =   catalog.search_around_sky(target_coords[~idx_found], seplimit=seplimit*u.milliarcsecond)
        df_coord_search                     =   df_catalog.iloc[idxself].copy()
        df_coord_search['sep']              =   sep2d.milliarcsecond

        # _________________________________________________________________           important in order to keep consistency.
        df_coord_search['fits_target']      =   target_names[~idx_found][idxtarget]

        if not match_res.empty:
            df_coord_search                 =   df_coord_search[match_res.columns]
            df_coord_search.index =  df_coord_search.index + 10000

        match_res = concat([match_res, df_coord_search])
#         match_res = match_res.drop(columns=['RAh', 'RAm','RAs', 'DE-', 'DEd', 'DEm', 'DEs', 'Nobs', 'Nsca', 'Nses', 'Corr'],errors='ignore')
        if 'coordinate' in match_res:
            match_res.insert(2, 'coordinate', match_res.pop('coordinate'))
        if 'sep' in match_res:
            match_res.insert(0, 'sep', match_res.pop('sep'))


        if verbose: print(len(idxtarget), "found by coordinate")
        if verbose: print(sum(idx_found), "found by name")

        unmatched_indices = np.where(~idx_found)[0]
        idx_found[unmatched_indices[idxtarget]] = True


    if verbose: print(len(target_names[idx_found]), "found of", len(target_names))
    if verbose: print(len(target_names[~idx_found]), "not found")
    if include_not_found:
#         col_usable = ['sep', 'fits_target','coordinate']
        dic_df = {'coordinate':target_coords[~idx_found].to_string('hmsdms', sep=':'), 'fits_target': target_names[~idx_found],
                 'sep': None}
        match_res = concat([match_res, df(dic_df)])
    return match_res


# ########################################################################################|
# ################################      Generate ANTAB      ##############################|
# ########################################################################################|

class ANTAB:
    """
    To deal with all the ANTAB related tasks.
    looks for `vlba_gains.key` file if not self.vlbagainfile
    """
    def __init__(self, fitsfile, vlbacalfile):
        self.fitsfile       =   fitsfile
        self.vlbacalfile    =   vlbacalfile

        self.tsystxt,_,_    =   get_tsys_txt_fromtsmcallog(vlbacalfile)
        self.vlbagainfile   =   None
        self.dateobs        =   get_dateobs(fitsfile)
        self.gainfilename   =   'vlba_gains.key'

    def make_thevlbagainfile(self):
        if not self.vlbagainfile or not Path(self.vlbagainfile).exists():
            self.vlbagainfile = str(Path(avica_data_dir) / self.gainfilename)
        return self.vlbagainfile

    def get_vlbagainfile(self):
        vlbagainfile                =   self.make_thevlbagainfile()
        if not vlbagainfile or not Path(vlbagainfile).exists():
            _                       =   get_vlbagains(fl=self.gainfilename, outfile=vlbagainfile)
        return vlbagainfile

    def gen_antab(self, outfile, vlbagainfile=None):
        """
        TODO: if VLBA get_vlbagainfile, elif EVLA get_ygainfile, elif global get_gainlist
        """
        vlbagainfile                =   vlbagainfile or self.get_vlbagainfile()
        main_antab_txt              =   ''
        allans                      =   []

        last_pcol_td                =   None
        pols, freq_range            =   [], []
        freq = None

        tsys_found, gain_found      =   False, False
        _tsys_head                  =   {}
        allans, ind, pols           =   [],[], []
        ant_header_count            =   0
        ant_header                  =   False
        end_file                    =   False
        antenna_changed             =   False
        gain_header                 =   ""

        this_an_gain_processed      =   False
        mount                       =   ''
        gain_missing                =   []

        yday_start, yday_end        =   datetimerange_fromfits(self.fitsfile)
        yyyy                        =   yday_start.split(':')[0]
        tsys_lines = self.tsystxt.split('\n')
        tsys_lines.append('__END__')
        pols_global, freq_range_global = [], []
        dic_header_an               =   {}
        with open(outfile, "w") as oa:
            for ti,t in enumerate(tsys_lines):

                # --------- Check working Station/Antenna
                if 'tsys information for' in t.lower():
                    an=t.lower().replace('tsys information for','').replace(' ','').replace('-','').replace('!','').upper()
                    antenna_changed = True
                    allans.append(an)
                    this_an_gain_processed = False
                    ant_header = False

                # ---------- Check rcp,lcp,freq availability -> choose the header with closest timestamp
                if ti+1 < len(tsys_lines) and any(pol in tsys_lines[ti+1].lower() for pol in ['rcp', 'lcp']):
                    headv = [v for v in t.split(' ') if v]
                    for hv in headv:
                        if all(v in hv for v in [':', '-', '/']):                                                           # HACK: looks for the timestamp pattern unique to header
                            hv = hv.split('/')
                            timv = [f"{yyyy}:{t_hv.replace('-', ':')}" for t_hv in hv if t_hv]
                            if last_pcol_td is None or antenna_changed:#or last_pcol_td <= 999: #(Time(yday_start)- Time(timv[0])).value:             # checking closest timestamp
                                antenna_changed = False
                                last_pcol_td = (Time(yday_start)- Time(timv[0])).value
                                # print(last_pcol_td, "was last time diff", "timestamp from header:", timv)
                                pols, freq_range = [], []
                            # else:
                            #     print(last_pcol_td, "REJECTED: was last time diff", "timestamp from header:", timv)
                if any(pol in t.lower() for pol in ['rcp', 'lcp']):
                    p = [pol for pol in ['rcp', 'lcp'] if pol in t.lower()]
                    if p:
                        pols.append(p[0])
                        line = [l for l in t.split(' ') if l]
                        if ti-1>0 and not any(pol in tsys_lines[ti-1].lower() for pol in ['rcp', 'lcp']):                   # checking first row with freq

                            if 'K' in str(line[-3]):
                                bw         = float(line[-3].replace('K',''))/2000
                            else:
                                bw         = float(line[-3].replace('M',''))/2

                            freq_range = [str(float(line[-2].replace('MHz',''))-bw)]                                                       # HACK: hardcoded -2 might not be always true, check header info
                        if ti+1<len(tsys_lines) and not any(pol in tsys_lines[ti+1].lower() for pol in ['rcp', 'lcp']):     # checking last row with freq in TSYS header
                            freq_range.append(str(float(line[-2].replace('MHz',''))+bw))                                                   # HACK: hardcoded "MHz" can be avoided
                        if freq_range and not this_an_gain_processed:
                            ## TODO: we should store R{nrcp},L{nlcp} in a dict
                            # for freq in freq_range:
                                # band = check_band(freq/1e3) # as freq in MHz -> GHz
                                # ---> change indent for following:
                            freq = abs(float(freq_range[0]))

                            mount, dpfu, poly           =   find_gain_fromgaintable(fitsfile=self.fitsfile, vlbagainfile=vlbagainfile, an=an, date=self.dateobs, freq=freq)
                            if mount is None:
                                mount, dpfu, poly       =   find_gain(vlbagainfile, an, self.dateobs, freq)
                            this_an_gain_processed = True
                            if not mount:
                                gain_missing.append(an)
                                # if band not in dic_header_an: dic_header_an[band] = {an:{}}
                                # dic_header_an[band][an] = {"mount":mount, "dpfu":dpfu, "poly":poly, 'pols': pols, 'freq' :freq}

                # ---------- Gathering TSYS header info
                if 'TSYS ' in t:
                    tsys_found          =   True

                    tv                  =   [tt for tt in t.split(' ') if tt]
                    tv.remove('TSYS')
                    tv.remove('/')

                    d_val               =   {}
                    for i,each_tv in enumerate(tv):
                        if '=' in each_tv:
                            tv_val      =   ''
                            try:
                                tv_val  =   float(tv[i+1])
                            except:
                                tv_val  =   0#str(tv[i+1])                      # HACK: if the value is not numeric consider 0.
                                                                                        # Only verified with TIMEOFF=* -> AIPS TASK ANTAB -> TIMEOFF=0
                            d_val[str(tv[i-1])] =   tv_val
                            tv.pop(i-1)
                            tv.pop(i-1)
                            tv.pop(i-1)

                    _tsys_head[str(tv[0])]      =   d_val


                elif t and t[0]=='/':
                    tsys_found=False

                # ---------- Create main_antab_txt
                elif tsys_found:                                                # HACK: Using elif (instead of if) avoids finding 'TSYS:'

                    if t and t[0]!='!':
                        if mount and an in _tsys_head:
                            if not ant_header:
                                if pols:
                                    rc,lc       =   0,0
                                    # print(f"pols={pols} {an} , {len(ind)}")
                                    for i,pol in enumerate(pols):

                                        if 'rcp' in pol:
                                            rc          +=  1
                                            ind.append(f"'R{rc}'")
                                        elif 'lcp' in pol:
                                            lc          +=  1
                                            ind.append(f"'L{lc}'")

                                an_values               =   [f"{k.upper()}={v}" for k,v in _tsys_head[an].items()]

                                antab_header            =   f"GAIN {an} {mount} DPFU={','.join(map(str,dpfu))} "
                                # antab_header            +=  f"FREQ={','.join(freq_range)} "
                                antab_header            +=  f"POLY={','.join(map(str,poly))} /"
                                antab_header            +=  f"\nTSYS {an} {' '.join(an_values)} INDEX={','.join(ind)} /\n"
                                pols, ind               =   [], []
                                # print(antab_header)
                                if ant_header_count:
                                    main_antab_txt          += '/\n'

                                main_antab_txt         +=  antab_header
                                ant_header_count       +=  1
                                ant_header              =   True
                            rowv = [v for v in t.split('!')[0].split(' ') if v]
                            if len(rowv)>1:
                                if '.' in rowv[1]:
                                    hh,mm                   =   rowv[1].split(':')
                                    sec_dec                 =   mm.split('.')[1]
                                    mm                      =   f"{mm.split('.')[0]}:{float(sec_dec) * 0.6*0.1**len(sec_dec)}"
                                    rowv[1]                 =   f"{hh}:{mm}"

                                hh_strp, mm_strp, ss_strp = rowv[1].split(':')

                                fixed_time = (datetime.strptime("0:0:0.0", "%H:%M:%S.%f") + timedelta(hours=float(hh_strp), minutes=float(mm_strp),seconds=float(ss_strp))).strftime("%H:%M:%S.%f")
                                yday_row                    =   Time(f"{yyyy}:{rowv[0]}:{fixed_time}")
                                row_validation              =   True#yday_start < yday_row < yday_end
                                #idx_freq                   =   [idxf for idxf in range(ind) freq_start < freq_ro]
                                if row_validation:

                                    row_vv                  =   [v for v in t.split('!')[0].split(' ') if v]
                                    row_vv[1]               =   yday_row.strftime(f'%H:%M:%S.%f')[:-2]
                                    row_vv                  =   " ".join(row_vv)
                                    # print(row_vv)
                                    main_antab_txt          +=  f"{row_vv}\n"


                        if main_antab_txt:
                            # print(main_antab_txt)
                            oa.write(main_antab_txt)
                            main_antab_txt=''
                if '__END__' in t:
                    end_file = True
                    if end_file:
                            oa.write('/')

        return allans, _tsys_head, gain_missing

def parse_equals(gain_dic, antb_line_cols):
    key                             =   "undefined"
    for val in antb_line_cols:
        val                         =   val.replace("'", "")
        val                         =   val.replace('"', "")

        if "=" in val:
            key, firstvalue         =   val.split("=")
            gain_dic[key]  =    []
            if firstvalue.strip():
                gain_dic[key]  =   [firstvalue.strip()]
        else:
            if not "," in val:
                gain_dic[key].append(val)
            else:
                gain_dic[key].extend(val.split(','))
    return gain_dic

def parse_gain_from_antab(gain_dic, antb_line_cols):
    gain_dic           =   {}
    gain_dic['MOUNT']  =   antb_line_cols[2].strip()
    rest                        =   antb_line_cols[3:-1]
    gain_dic                    =   parse_equals(gain_dic, rest)
    return gain_dic

def parse_tsys_from_antab(tsys_dic, antb_line_cols):
    rest               =    antb_line_cols[2:-1]
    tsys_dic           =   parse_equals(tsys_dic, rest)
    tsys_dic['data']   =   []
    return tsys_dic

def parse_antab(antabfile, fitsfile):
    yy              =   get_dateobs(fitsfile=fitsfile).year
    with open(antabfile) as antb:
        gain_dic                =   {}
        tsys_dic                =   {}
        tsys_row                =   False
        tsys_head_recorded      =   False
        mintime, maxtime        =   "", ""
        for antb_line in antb.readlines():
            antb_line_cols      =   antb_line.split(" ")
            firstcol            =   antb_line_cols[0].strip()

            if firstcol in ["GAIN", "TSYS"]:
                antenna         =   antb_line_cols[1].strip()
                if firstcol == "GAIN":                                          # Record gain header
                    tsys_row    =   False
                    gain_dic[antenna]    =   {}
                    gain_dic[antenna]    =   parse_gain_from_antab(gain_dic[antenna], antb_line_cols)

                elif firstcol == "TSYS":                                        # Record tsys header
                    tsys_row            =   True
                    tsys_head_recorded  =   True
                    if not antenna in tsys_dic:  tsys_dic[antenna]   =   {}
                    tsys_dic[antenna]   =   parse_tsys_from_antab(tsys_dic[antenna], antb_line_cols)

            if tsys_row:
                if tsys_head_recorded:
                    tsys_head_recorded  =   False
                else:
                    if firstcol != "/":                                         # Record tsys Data
                        antb_line_cols[-1]  =   antb_line_cols[-1].replace("\n", "")
                        # tsys_dic[antenna]['data'].append(antb_line_cols)

                        s               =   " ".join(antb_line_cols[:2])
                        tsys_values     =   [float(v) for v in antb_line_cols[2:]]

                        # dt              =   datetime.strptime(s, "%j %H:%M:%S.%f").replace(year=yy) # does not consider leap year
                        dt              =   datetime.strptime(f"{yy} {s}", "%Y %j %H:%M:%S.%f")
                        if not mintime or mintime> dt: mintime = dt
                        if not maxtime or maxtime< dt: maxtime = dt

                        tsys_dic[antenna]['data'].append([str(dt), tsys_values])
                        tsys_dic["start_time"] = mintime
                        tsys_dic["end_time"] = maxtime
    return {"gain_dic": gain_dic, "tsys_dic": tsys_dic}

def find_gain_fromgaintable(fitsfile, vlbagainfile, an, freq, gaintbname="GAIN_CURVE", date="", verbose=True):
    """
    assumes DATE-OBS wont change anything.

    """
    from avica.fitsidiutil.io import FITSIDI

    fo = FITSIDI(fitsfile=fitsfile)
    hdul = fo.read()
    fo.close()

    mount, sensitivity, poly = None, None, None

    if gaintbname in hdul:

        tb_ant  = hdul['ANTENNA']

        idx_tba =   list(tb_ant['ANNAME']).index(an)
        anid    =   tb_ant['ANTENNA_NO'][idx_tba]
        pola    =   tb_ant['POLTYA'][idx_tba]

        gaintb  =   hdul[gaintbname]
        mask_an_gtb = np.array(gaintb['ANTENNA_NO'])==anid

        reffreq = hdul['FREQUENCY'].header['REF_FREQ']
        freqtb  = hdul['FREQUENCY']
        ntab    = hdul[gaintbname].header['NO_TABS']
        dic_band = {}

        for i,freqid in enumerate(freqtb['FREQID']):
            bandfreq                    = reffreq + freqtb['BANDFREQ'][i]
            for j,freq_sel in enumerate(bandfreq):
                band                    = check_band(freq_sel/1e9)
                if not band in dic_band:
                    dic_band[band]      =  {j:freq_sel}
                else:
                    dic_band[band][j]   = freq_sel

        freq_given_Hz           = freq*1e6           # because freq is in MHz
        given_band              = check_band(freq_given_Hz/1e9)

        idx_band_seq            = list(dic_band[given_band].keys())

        pol1g                   =   np.max(np.array(gaintb['SENS_1'])[mask_an_gtb][0][idx_band_seq])                                      # HACK : hardcoded index 0 of the array result
        pol2g                   =   np.max(np.array(gaintb['SENS_2'])[mask_an_gtb][0][idx_band_seq]) if 'SENS_2' in gaintb.cols else pol1g

        sensitivity             = [pol1g, pol2g] if pola =='R' else [pol2g, pol1g]
        an_gain                 = parse_vlbagain(vlbagainfile,an, freq=freq)
        mount                   = an_gain['MOUNT'].values[-1] if not an_gain.empty else "ALTAZ"

        nchan                   = len(freqtb['BANDFREQ'][0])                                                                   # HACK: assumes freqid at col 0
        polytb                  = np.array(gaintb[mask_an_gtb]['GAIN_1'])[0].reshape(nchan,ntab)[idx_band_seq][0]
        poly                    = []
        for polyv in polytb:
            if polyv==0:break
            poly.append(polyv)
        if mount is not None and verbose:
            print(f"\t{gaintbname} found! values registered for {an}")
    return mount, sensitivity, poly

def find_gain(vlbagainfile, an, obsdate, freq):
    """
    Reads the vlba_gain.keys file and returns the GAIN value associated to the ANTENNA.

    Input
    ---

    :vlbagainfile:      (str)
                        path of the vlbagainfile.

    :an:                (str)
                        antenna name

    :obsdate:           (datetime.datetime object)
                        datetime object to compare GAIN values from

    :freq:              (float)
                        frequency value in MHz

    Returns
    ---
    (MOUNT, DPFU, POLY)
    The GAIN information associated with the ANTENNA from the vlba_gains.key file.

    e.g

    >>> find_gain('vlba.gains','SC', daterange=datetime(2015,5,1), freq=6000)
    [output]
    SC GAIN ALTAZ DPFU = 0.111, 0.104 POLY = 1.0 /
    """
    mount, dpfu, poly = None, None, None
    an_gain = parse_vlbagain(vlbagainfile,an, freq=freq)

    an_gain['date_comp'] = [obsdate]*len(an_gain)
    found_date = an_gain.loc[an_gain['date_comp'].between(an_gain['FROM'],an_gain['TO'])]
    idx_by_nearest_freq = abs(found_date['FREQ'] - freq).sort_values(ascending=True).index
    try:
        df_selected = an_gain.iloc[idx_by_nearest_freq[0]]
        mount, dpfu, poly = df_selected['MOUNT'], df_selected['DPFU'], df_selected['POLY']
    except:
        print(f"failed for {an} with {obsdate} and {freq}MHz")
    # print(f"{an} GAIN {df_selected['MOUNT']} DPFU = {','.join(map(str,df_selected['DPFU']))} POLY = {','.join(map(str,df_selected['POLY']))} /")
    return mount, dpfu, poly

def get_vlbagains(fl='vlba_gains.key', outfile='vlba_gains.key'):
    from contextlib import closing
    txt = None
    with closing(request.urlopen(f'http://www.vlba.nrao.edu/astro/VOBS/astronomy/{fl}')) as r:
        txt = r.read()
        if outfile:
            if not Path(outfile).parent.exists():
                Path(outfile).parent.mkdir(exist_ok=True)
            with open(outfile, 'wb') as cvlba:
                cvlba.write(txt)
    return txt

def parseval(val):
    if ' ' in val:
        try:
            val = [int(v) for v in val.split(' ') if v]
        except:
            try:
                val = [float(v) for v in val.split(' ') if v]
            except:
                val = [str(v) for v in val.split(' ') if v]
    else:
        try:
            val = int(val)
        except:
            try:
                val = float(val)
            except:
                val = str(val)

    return val

def parse_block_head(block_head):
    psv= [parseval(num) for num in block_head.split(' ') if num]
    workr = psv.copy()
    for tx in workr:
        if isinstance(tx, str) and not ('(' in tx and ')' in tx):
                psv.remove(tx)
    if psv:
        pol = [val for val in psv if isinstance(val, str)][0].replace('(','').replace(')','').split(',')
    meas = psv[:len(pol)]
    proj = psv[len(pol)+1:]

    return meas,proj

def parse_vlbagain_anblock(block):
    dc = {'ANNAME':'', 'MOUNT':'', 'DPFU':[], 'POLY':[],
          'measurements':(), # measurements can be already checked before the parsing of these texts
                'BAND':'', 'TIMERANG':[],'FREQ':0., 'COMMENT':'', 'TS':[], 'TR':[], 'TCAL':[], 'FT':[]
         }

    for tx in block.split('\n'):
        tx=" = ".join(tx.split('='))

        tx = [t for t in tx.split(' ') if t]
    #     tx_len = len(tx)
        if tx:
            if '/' in tx:
                dc['ANNAME'] = tx[0]
                dc['MOUNT'] = tx[2]
            for ti,t in enumerate(tx):
                if '=' in t:
                    tx_val = []
                    if ti-1>=0 and tx[ti-1] in dc:
                        _key = tx[ti-1].lstrip().strip()
                        if ti+1<=len(tx):
                            if not '=' in tx[ti+1]:
                                k,pool = tx[ti-1], tx[ti+1:]

                                for j, val in enumerate(pool):

                                    if j+1<=len(pool):
                                        if not j+1==len(pool) and pool[j+1]=='=':
                                            break
                                        parsed_val = parseval(str(val).replace(',',' ').strip())

                                        if parsed_val!='/':
                                            if _key=='POLY' and isinstance(parsed_val, list):
#                                                 print(parsed_val)
                                                parsed_val = [pv for pv in parsed_val if pv]
                                                tx_val.extend(parsed_val)
                                            else:
                                                tx_val.append(parsed_val)
                            else:
                                tx_val = parseval(str(tx[ti+1].strip()))
                        dc[_key] = tx_val
    return dc

def parse_vlbagain(vlbagainfile, an='LA', freq=0., meas_upper=[10,10],):
    """
    Converts vlba_gains.key file to pandas dataframe
    """
    from pandas import DataFrame as df
    countan = 0
    headstart = False
    meas,proj = [11,11], [1,1]
    idx=0
    dfable = []
    with open(vlbagainfile, 'r') as vg:
        vglines = vg.readlines()
        tx=''
        for gi,vgl in enumerate(vglines):
            if all(headk in vgl.lower() for headk in ['the', 'following', 'are', 'based']):
                meas,proj = parse_block_head(vgl)
                headstart=True

            if vgl[0]!='!':
                if vgl=='\n':
                    headstart=True
                    tx=''
                if len(vgl)>3 and headstart:
                    tx+=vgl
                if '/\n' in vgl:
                    if an in vgl[:4]:
                        countan+=1
                        dc = parse_vlbagain_anblock(tx)
                        # print(dc,meas)
                        if meas>meas_upper:
                            freq_validation = check_band(dc['FREQ'][0]/1000)==check_band(freq/1000)
                            if dc['ANNAME']==an and freq_validation:
                                dfable.append([dc['MOUNT'],dc['DPFU'], dc['POLY'], datetime(*dc['TIMERANG'][0]),datetime(*dc['TIMERANG'][1]),dc['FREQ'][0]])
                    tx=''
                    headstart=False
    return df(data=dfable, columns=['MOUNT','DPFU', 'POLY', 'FROM', 'TO', 'FREQ'])

def get_tsys_txt_fromtsmcallog(cal_vlbafile):
    """
    Returns
    ---

    Tsys text: contains the whole tsys block extracted from the TSM log file
    Timerange From: 'yyyyMONdd'
    Timerange To: 'yyyyMONdd'
    """
    tsysv,fr,to = '', None, None
    with open(cal_vlbafile, 'r') as cvlba:
        tsys_text = False
        tsm_lines = cvlba.readlines()
        for li,line in enumerate(tsm_lines):
            if all(reqtxt in line.lower() for reqtxt in ['tsys', 'information']):
                tsys_text=True
            if li-1>0 and tsys_text and all(k in tsm_lines[li-1].lower() for k in ['for', 'timerange']):
                timerange_text = tsm_lines[li-1].split('to')
                to = timerange_text[1].split('at')[0].strip().split('/')[0]
                fr = [txt for txt in timerange_text[0].split('at')[0].split(' ') if txt]
                fr = fr[-1].strip().split('/')[0]
            if '/' in line[0]:
                tsys_text=False
            if tsys_text: tsysv += line
    return tsysv, fr, to
