import numpy as np
from astropy.io import fits
from typing import List
import polars as pl
from .io import FITSIDI, read_idi
from datetime import datetime
from astropy.time import Time, TimeDelta
from vasco.util import compute_sep

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
    
    startyday=(Time(hdul[lids[0]]['DATE'][0], format='jd') + TimeDelta(hdul[lids[0]].data['TIME'][0], format='jd')).yday    
    nrows = hdul[lids[-1]].nrows
    fo.read(10, start_row=nrows-5)
    
    endyday=(Time(hdul[lids[-1]]['DATE'][-1], format='jd') + TimeDelta(hdul[lids[-1]].data['TIME'][-1], format='jd')).yday
    
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

def find_refant(fitsfile, verbose=True, err_onmissing=False, tsys_wt=0.99, nrows_wt=0.95, distance_wt=0.80):
    """takes fitsfile as input and returns the reference antenna which is good geometrically, observation length, and by TSYS
    prints table with columns [ANNAME,STD_TSYS,nRows,Distance,c] sorted by best reference antenna;

    Returns:
    -----

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