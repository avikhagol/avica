from astropy.io import fits
from astropy.time import Time, TimeDelta
import astropy.units as u
from astropy.table import Table, QTable
from datetime import datetime
import numpy as np
from collections import Counter
import numpy as np
import itertools
from pathlib import Path
from pandas import DataFrame as df, set_option
import warnings
import re
from numpy.lib.stride_tricks import sliding_window_view
warnings.filterwarnings(action='ignore', message='Mean of empty slice')

set_option('display.max_colwidth', None)
def _getcolname(data,colnames=['SOURCE']):
    _colname=None
    for cname in data.columns:
        for colname in colnames:
            if colname in str(cname.name).upper():
                _colname=str(cname.name)
    return _colname

def _gethduname(hdulist,hdunames=['SYSTEM_TEMPERATURE']):
    _hduname=None
    hduids = []
    for lid,hdu in enumerate(hdulist):
        for hduname in hdunames:
            if str(hduname).upper() in str(hdu.name).upper():
                _hduname=str(hdu.name)
                hduids.append(lid)
    return _hduname, hduids

def _listobs(fitsfile,cardname=None) :
    """
    read fits file hdus, produce a CASA listobs() output

    Parameters:
    ----------

    :fitsfile: (str)
        - give path for the right fitsfile eg .uvfits, .fits, .idifits
    
    :cardname: (str)
        - give name of the HDUList hdus separeted by comma
    
    Return:
    ------

    Tabular format output from the fits data.

    Ex.
    ```bash
    $ vasco -l "SCAN,SOURCE,ANTENNA" -f test.fits > list.obs
    ```
    
    """
    hdudata,hdunames=None,[]
    
    with fits.open(fitsfile, 'readonly') as hdul:
        
        for c in hdul:
            try:
                dateobs=c.header['DATE-OBS']
            except:
                pass
            if c.name in cardname:
                hdudata=c.data
                print(Table(hdudata))
            hdunames.append(c.name)
        if "SCAN" in cardname:
                # cardname="PRIMARY"
                if "UV_DATA" in hdunames: 
                    cardname="UV_DATA"
                else:
                    raise ValueError("This fits file is not supported for this operation: Missing 'UV_DATA' extension")
                uvtime=hdul[cardname].data.TIME
                uvsid_colname='SOURCE'                       # SOURCE_ID name not consistent b/w VLBA and EVN column ofcardname                
                uvsidd=hdul[cardname].data
                sourced=hdul['SOURCE'].data
                uvsid_colname=_getcolname(uvsidd,['SOURCE'])
                # for cname in uvsidd.columns:
                #     if 'SOURCE' in str(cname.name).upper(): 
                #         uvsid_colname=str(cname.name)
                uvsid=uvsidd[uvsid_colname]

                # scanmjd=Time(uvtime, format='mjd', scale='utc')
                zerotime=Time(dateobs, format='isot',scale='utc')
                scantime = np.array(zerotime.mjd, dtype=np.float64)+np.array(uvtime, dtype=np.float64)
                scantime = Time(scantime, format='mjd', scale='tt')
                # scantime=zerotime.mjd+uvtime
                integrationTime=Counter(hdul[cardname].data.INTTIM).keys()
                sourcename={}
                ind_inst=np.where((np.diff(uvsid)!=0)==True)
                ind_inst=np.append(ind_inst,-1)
                scanlist=uvsid[ind_inst]
                totalrows=len(uvsid)
                sourceid_colname=_getcolname(sourced,['SOURCE_ID', 'ID_NO.', 'ID_NO'])        
                                                                                                # ID_NO. name not consistent b/w VLBA nad EVN column of SOURCE

                for i,sid in enumerate(sourced[sourceid_colname]):
                    sourcename[sid]=hdul['SOURCE'].data.SOURCE[i]
                print(sourcename)
                print(f"sequence - {str(scanlist)}")
                ninst=len(ind_inst)
                r_s=0
                print("TIME OBSERVED".ljust(50," "), "SOURCE".ljust(15," "),"SID".ljust(4," ") ,"nRows")
                for i,j in enumerate(ind_inst):
                    r_e=j+1
                    if j==-1:r_e=totalrows
                    ind_inst_cut=range(r_s,r_e)
                    nrows=np.size(ind_inst_cut)
                    time_inst=scantime[ind_inst_cut]

                    if len(time_inst) :
                        timeobserved=f"{time_inst[0].fits} - {time_inst[-1].fits}"
                        print(timeobserved.ljust(50," "), sourcename[scanlist[i]].ljust(15," "), str(scanlist[i]).ljust(4," "), nrows,)

                    r_s=j+1

    
    print(f"Possible hdus can be: {str(hdunames)}")



def check_seq_occurance(arr, seq=[1]):
    mask_freqid             =   np.insert(arr[1:] != arr[:-1], 0, True)
    deduplicated_freqid     =   arr[mask_freqid]
    windows                 =   sliding_window_view(deduplicated_freqid, len(seq))[::len(seq)]
    return np.all(np.all(windows == seq, axis=1))

def flatten_data_for_freqid(freqd, freqid :int =1, verbose=True):
    """
    flattens data to single row if multiple rows found
    Note: Only tested on FREQUENCY table.
    """
    nrows = len(freqd)
    if nrows>1:
        if verbose: print(f"{nrows} rows found! flattening to 1.")
        freql = {0: np.array(freqid, dtype=freqd['FREQID'].dtype)}
        for j,row in enumerate(freqd):
            for i,colv in enumerate(row):
                if i not in freql: freql[i] = np.array([])
                if i>=1:
                    freql[i] = np.append(freql[i],colv)
                    freql[i] = np.array(freql[i], dtype=colv.dtype)
        data = tuple(freql.values())
        new_fields = []
        name, (typ, shape) = None, (None, None)
        
        for i,row in enumerate(freqd.dtype.descr):
            if len(row)==2:
                name, typ = row
            else:
                name, typ, shape = row
            
            if shape:
                
                new_shape = (nrows*shape[0],)
                if verbose: print(name, shape, '-->', new_shape)
                new_fields.append((name, typ, new_shape))
            else:
                new_fields.append((name, typ))

        new_dtype = np.dtype(new_fields)
        data = tuple(data)

        new_freqhdudata = fits.FITS_rec(np.rec.array([data], new_dtype)) # equivalent to hdu['FREQUENCY].data
        freqd = new_freqhdudata
    return freqd



def bintb_tohdu(hdu, hdu_data, automatic_format=True, verbose=True):
    
    hdu_data_coldefined                  =   fits.ColDefs(hdu_data)
    hdu_new_tbl                             =   fits.BinTableHDU.from_columns(hdu_data_coldefined)
    nspws                               =   hdu_new_tbl.data['BANDFREQ'].shape[1]
    
    if not automatic_format:
        for colf in hdu_new_tbl.columns:
            if colf.format == 'J':
                hdu_new_tbl.columns[str(colf.name)].format = fits.column._ColumnFormat("1J")        
    
    if not 'NO_BAND' in hdu_new_tbl.header:
            hdu_new_tbl.header['NO_BAND']   =   nspws
    
    for card in hdu.header:
            if not card in hdu_new_tbl.header :
                hdu_new_tbl.header[card]    =   hdu.header[card]
                print(f"{card} ...copied")
            else:
                if hdu.header[card]    !=  hdu_new_tbl.header[card]:
                    if verbose : print(card, hdu.header[card],"-->" , hdu_new_tbl.header[card])
    return hdu_new_tbl

def fix_freqid_bintab(hdul, tab=['UV_DATA'], verbose=True):
    """
    checks sequence of occurance matches withe the unique sorted values in FREQID
    e.g expected sequence [1,2] if finds [2,1] for FREQID sequence will throw error
    else change to FREQID=1 
    
    Returns
    -------
    
    hdu with FREQID changed to first value of FREQID in FREQUENCY table
    
    """
    
    freqhdudata = hdul['FREQUENCY'].data
    nspws   =   freqhdudata['BANDFREQ'].shape[1]
    
    
    for itb in hdul:
        if 'NO_BAND' in hdul[itb].header:
                hdul[itb].header['NO_BAND'] = nspws
    
    _, tbindex = _gethduname(hdul, tab)
    
    for tb in tbindex:
        
        
        arr = hdul[tb].data['FREQID']
        
        
        
        mask_freqid             =   np.insert(arr[1:] != arr[:-1], 0, True)
        deduplicated_freqid     =   arr[mask_freqid]
        freqids                 =   np.unique(arr)

        if check_seq_occurance(deduplicated_freqid, freqids):    
            if len(freqhdudata)==1:
                if len(freqids)>1 or freqhdudata['FREQID'][0]!=freqids[0]:
                    freqid      =   freqhdudata['FREQID'][0]
                    if verbose: 
                        print(f"\nfixing {hdul[tb]}")
                        print(f"FREQID {freqids} --> {freqid}")
                    hdul[tb].data['FREQID']  =   freqid
        else:
            raise IndexError(f"Found incompatible sequence in {deduplicated_freqid} of FREQID in {tab}. Required: {freqids}")
    return hdul

def add_rows_for_freqid(hdu, tab='ANTENNA'):
    """
    Populates duplicate antenna rows for different freqid if found in FREQUENCY table.
    """
    if not all(np.unique(hdu['FREQUENCY'].data['FREQID']) == np.unique(hdu[tab].data['FREQID'])):
        dic_ant_table = {}
        binTable = hdu[tab].data.copy()
        
        freqid = np.unique(hdu['FREQUENCY'].data['FREQID'])
        count = 0
        for j,row in enumerate(binTable):
            for i,freq_id in enumerate(freqid):
                row['FREQID'] = freq_id
                
                dic_ant_table[count] = [np.rec.array(list(row), dtype=binTable.dtype)]
                
                count+=1
                
        data = np.hstack(list(dic_ant_table.values()))

        fits_rec = fits.FITS_rec(data)
        
        hdu_new_tbl = fits.BinTableHDU.from_columns(fits.ColDefs(fits_rec))
        for card in hdu[tab].header:
            if not card in hdu_new_tbl.header :
                hdu_new_tbl.header[card] = hdu[tab].header[card]
                
        hdu[tab] = hdu_new_tbl
    return hdu

def add_antenna_for_freqid(hdu):
    """
    Populates duplicate antenna rows for different freqid if found in FREQUENCY table.
    """
    if not all(np.unique(hdu['FREQUENCY'].data['FREQID']) == np.unique(hdu['ANTENNA'].data['FREQID'])):
        hdu = add_rows_for_freqid(hdu, tab='ANTENNA')
    return hdu

def choose_correct_id_forduplicate_fields(hdu, fix=False):
    """
    if duplicates in SOURCE['SOURCE']:
        - remove the duplicate source name if no rows in uv_data
        else:
            - replace the duplicate source name in uv_data for the ones with count(rows)>0 IF the duplicates have no difference in coord and frequency in the SOURCE table
            else:
                - change the source name in the SOURCE table with the rule "{duplicate_name}_{ncount}"
    """
    list_chosen_ids, list_dupl_ids, list_repl_names = [], [], []
    
    
    chosen_id, dupl_ids = None, None
    # from dask import array as da
    shdu, shduids           = _gethduname(hdu, ['SOURCE'])
    source_data             =   hdu[shdu].data
    source_col              = _getcolname(source_data,['SOURCE'])
    id_col                  = _getcolname(source_data,['SOURCE_ID', 'ID_NO.', 'ID_NO'])
    
    validation_sourcecols   =  ['FREQOFF', 'RAEPO', 'DECEPO', 'EPOCH', 'RAAPP', 'DECAPP', 'RESTFREQ', 'PMRA', 'PMDEC']

    snames = list(hdu[shdu].data[source_col])

    if len(snames)!=len(np.unique(snames)):
        duplicates          =   [k for k,v in Counter(snames).items() if v>1]
        
        for duplicate_source in duplicates:
            rejected_ids        =   []
            repl_names          =   []
            dupl_ids            =   []
            nonzero_rows        =   []
            duplicate_ids       =   hdu[shdu].data[id_col][np.where(hdu[shdu].data[source_col]==duplicate_source)]
            preferred_inpairs   =   {}
            
            rec =hdu['SOURCE'].data[np.isin(hdu['SOURCE'].data[id_col],duplicate_ids)]

            df_rec = df(rec.tolist(), columns=rec.dtype.names)
            df_nunique = df_rec.apply(lambda col: col.astype(str).nunique())
            non_unique_series = df_nunique[df_nunique>1]
            
            source_names_replaceable = bool(sum(non_unique_series.index.isin(validation_sourcecols)))
            non_zero_rowsc      =   0
            if source_names_replaceable:
                print(f"both source names have different column values in the table SOURCE for {validation_sourcecols}")
                repl_names = [f"{duplicate_source}_{d}" for d, did in enumerate(df_rec[non_unique_series.index][id_col]) if d]
                chosen_id = duplicate_ids[0]
            else:
                _, uvhduids     =   _gethduname(hdu, ['UV_DATA'])
                this_new_hduid_with_nrows   =   False
                for hduid in uvhduids:
                    src             =   hdu[hduid].data['SOURCE']

                    compare         =   -1
                    chosen_id       =   None
                    
                    
                    for d, did in enumerate(duplicate_ids):
                        idx_did     =   np.where(src==did)
                        rows_val    =   src[idx_did]
                        
                        if len(rows_val):
                            non_zero_rowsc+=1
                        else:
                            this_new_hduid_with_nrows   =   False
                        
                        if rows_val.shape[0]>compare:
                            oth_id     =   did
                            chosen_id   =   chosen_id or did     # only chooses did when chosen_id has initialized value
                            if not oth_id in preferred_inpairs:
                                preferred_inpairs[chosen_id]    =   chosen_id
                                preferred_inpairs[oth_id]    =   chosen_id
                                for id_remain in duplicate_ids:
                                    if id_remain!=oth_id and id_remain!=chosen_id:
                                        preferred_inpairs[id_remain] = chosen_id
                                this_new_hduid_with_nrows   =   False
                            else:
                                
                                if len(rows_val):
                                    this_new_hduid_with_nrows = True
                                        
                            
                            # compare     =   rows_val.shape[0]
                        
                        modify_value_hdul = len(idx_did) and non_zero_rowsc>1 and this_new_hduid_with_nrows and did!=preferred_inpairs[chosen_id]
                        # print(modify_value_hdul, hduid, len(rows_val), did, duplicate_source, preferred_inpairs[chosen_id] , (len(idx_did[0]) , non_zero_rowsc>1 , this_new_hduid_with_nrows, chosen_id , did!=preferred_inpairs[chosen_id]))

                        if modify_value_hdul and fix:        # TODO: replace the row values for SOURCE_ID with the chosenid
                            print(f"There are duplicate fields with data in the FITS! count({duplicate_source})=={non_zero_rowsc} IDs: {duplicate_ids} (choosing {preferred_inpairs[chosen_id]})")
                            
                            prefid  = preferred_inpairs[chosen_id]
                            hdu[hduid].data['SOURCE'][idx_did]   =  prefid           # next hduid should also correct for this;
        
            dupl_ids = [rmid for i,rmid in enumerate(duplicate_ids) if rmid!=chosen_id]
            
            
            list_repl_names.append(repl_names)
            list_chosen_ids.append(chosen_id)
            list_dupl_ids.append(dupl_ids)

    return list_chosen_ids, list_dupl_ids, list_repl_names, hdu

def check_missing_ant(hdul, table_name="FLAG", col="ANTS"):
    """returns index where the ants is missing"""
    hdul['ANTENNA'].data['ANTENNA_NO']
    set_flag = set()
    rm_rows = np.array([])
    multidimcol = len(hdul[table_name].data[col].shape)>1
    if multidimcol:
        set_flag.update([an for an in hdul[table_name].data[col][:,0]])
    else:
        set_flag.update([an for an in hdul[table_name].data[col]])

    for an in set_flag:
        if not sum(np.isin(hdul['ANTENNA'].data['ANTENNA_NO'], [an])):
            print(f"an {an} not present, in {table_name}")
            if multidimcol:
                rm_rows = np.isin(hdul[table_name].data[col][:,0], [an])
            else:
                rm_rows = np.isin(hdul[table_name].data[col], [an])        
    return rm_rows

def fix_missing_ant(hdul, table_name, col):
    rm_rows         =   check_missing_ant(hdul, table_name, col)
    fhdu, fhduids   = _gethduname(hdul, [table_name])
    
    table_data       =   hdul[fhdu].data
    hdul[fhdu].data  =   table_data[~rm_rows]
    return hdul

def fix_duplicate_fields(hdu):
    
    chosen_id, dup_ids, repl_names, hdu = choose_correct_id_forduplicate_fields(hdu, fix=True)
    shdu, shduids   =   _gethduname(hdu, ['SOURCE'])
    source_data     =   hdu[shdu].data
    source_col      =   _getcolname(source_data,['SOURCE'])
    id_col          =   _getcolname(source_data,['SOURCE_ID', 'ID_NO.', 'ID_NO'])
    rem_ids         =   []
    for c, dup_id in enumerate(dup_ids):
        if not chosen_id[c] is None:
            if dup_id != chosen_id[c]:
                rem_ids.extend(dup_id)
        else:
            raise NotImplementedError("duplicate source names but have distinct coordinate or frequency offset values")
    print("removing ...", rem_ids)
    
    hdu[shdu].data = source_data[~np.isin(source_data['ID_NO.'],rem_ids)]

    return hdu


def add_O(src_name):
    if str(src_name)[0] == '0':
        zero_grouped = re.match(r'(0*)(.*)', src_name).groups()
        prefix = "O"*len(zero_grouped[0])
        print(src_name, "has zero ==>", prefix+zero_grouped[1])
        return prefix+zero_grouped[1]

def fix_leading_zeros(hdu):
    shdu, shduids   = _gethduname(hdu, ['SOURCE'])
    source_data     =   hdu[shdu].data
    source_col = _getcolname(source_data,['SOURCE'])
    for i,src in enumerate(hdu[shdu].data[source_col]):
        if str(src)[0] == '0':
            hdu[shdu].data[source_col][i] = add_O(src)
    return hdu        

def datetimerange_fromfits(fitsfile):
    """
    Returns
    ---
    
    (yday_start, yday_end)
    """
    hdul = fits.open(fitsfile)
    hduname, lids = _gethduname(hdul,['UV_DATA'])
    startyday=(Time(hdul[lids[0]].data['DATE'][0], format='jd') + TimeDelta(hdul[lids[0]].data['TIME'][0], format='jd')).yday    
    endyday=(Time(hdul[lids[-1]].data['DATE'][-1], format='jd') + TimeDelta(hdul[lids[-1]].data['TIME'][-1], format='jd')).yday
    
    return startyday, endyday

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
    except:
        dateobs = [int(d) for d in dateobs.split('/')]
        yyyy = dateobs[2]+1900 if 90<=dateobs[2]<=99 else dateobs[2]+2000
        mm, dd = dateobs[1], dateobs[0]
    return yyyy,mm,dd

def get_dateobs(fitsfile):
    hdul            =   fits.open(fitsfile)
    dateobs         =   hdul[0].header['DATE-OBS']
    yyyy,mm,dd      =   get_yyyymmdd(dateobs)
    return datetime(yyyy, mm, dd)

def groupfreq_byband(fitsfile):
    hdul = fits.open(fitsfile)
    groupfreq = {}
    bandfreq= hdul['FREQUENCY'].data['BANDFREQ'] + hdul['FREQUENCY'].header['REF_FREQ']
    for freq in bandfreq[0]:
        band = check_band(freq=freq/1000000000)
        if band in groupfreq:
            groupfreq[band].append(freq)
        else:
            groupfreq[band] = [freq]
    return groupfreq

def get_source_id(hdul, source_name, source_hduname = 'SOURCE'):
    """
    returns source id for source name as input
    """
    source_data = hdul[source_hduname].data

    source_col = _getcolname(source_data,['SOURCE'])
    id_col = _getcolname(source_data,['SOURCE_ID', 'ID_NO.', 'ID_NO'])
    
    sourceid = hdul[source_col].data[source_data[source_col]==source_name][id_col]
    
    return sourceid

def get_sources_id(sources_dict, sources):
    """
    returns source id for source name as input
    """
    s_df = df(list(sources_dict.values()), columns=['source_name'], index=list(sources_dict.keys()))
    sourceid = s_df[s_df['source_name'].isin(sources)]
    
    return list(sourceid.index)

def sources(hdul):
    sourced=hdul['SOURCE'].data
    sourcename={}
    sourceid_colname=_getcolname(sourced,['SOURCE_ID', 'ID_NO.', 'ID_NO'])
    for i,sid in enumerate(sourced[sourceid_colname]):
            sourcename[sid]=hdul['SOURCE'].data.SOURCE[i]
    return sourcename


# def scanlist(hdul):
#     """
#     return array of scanlist and index of the scan in the sequence of data from UV_DATA column
#     """
#     hduname, lids   = _gethduname(hdul,['UV_DATA'])
#     scanlist_arr    = np.array([])
#     ind_insts       = []
#     for lid in lids:
#         uv_data=hdul[lid].data
        
#         uvsid_colname=_getcolname(uv_data,['SOURCE'])
#         uvsid=uv_data[uvsid_colname]
#         ind_inst    =   np.where((np.diff(uvsid)!=0)==True)
#         if lid==lids[-1]:
#             ind_inst    =   np.append(ind_inst,-1)
#         ind_insts   =   np.append(ind_insts, ind_inst)
#         scanlist_arr=   np.append(scanlist_arr,uvsid[ind_inst])
#     return scanlist_arr, ind_insts

def scanlist(hdul):
    """
    return array of scanlist and index of the scan in the sequence of data from UV_DATA column
    """

    uv_data=hdul['UV_DATA'].data
    
    uvsid_colname=_getcolname(uv_data,['SOURCE'])
    uvsid=uv_data[uvsid_colname]
    ind_inst=np.where((np.diff(uvsid)!=0)==True)
    ind_inst=np.append(ind_inst,-1)
    scanlist_arr=np.array(uvsid[ind_inst])
    return scanlist_arr, ind_inst


def __sel_ind(data):
    ind=np.where((np.diff(data)!=0)==True)
    ind=np.append(ind,-1)
    grouped_data=data[ind]
    return grouped_data

def _return_target(sdict):
    """
    TODO: group by occurance of phaseref combination, as the cov is affected by indices
    """
    compare_val,phrefs=[],[]
    for s in sdict['phref']:
            compare_val.append(np.std(sdict['phref'][s])/np.mean(sdict['phref'][s])*100)            #coeff of variab check for indices
            phrefs.append(s)
    ind=np.argsort(compare_val)
    phrefs=(np.array(phrefs)[ind])
    science_targets=phrefs[::2]
    phase_cal=phrefs[1::2]
    bright_cal=list(sdict['other'].keys())
    return science_targets,phase_cal,bright_cal

def check_phaseref(scanlist_arr):
        """
        check scan list and see if phase referencing is used.
        """
        sdict={'phref':{}, 'other':{}}
        isTrue=False
        sources=np.unique(scanlist_arr)    
        for source in sources:
            source_seq_ind=np.where(source==scanlist_arr)
            phaseref_ind=np.where(np.diff(source_seq_ind)[0]==2)[0]
            if len(phaseref_ind)>1:
                isTrue=True
                sdict['phref'][source]=source_seq_ind
                
            else:
                sdict['other'][source]=source_seq_ind
        return isTrue,sdict


# def get_phref(s, sl, dic):
#     phref_byidx = {}

#     for sid in s:
#         ps = dic['phref'][sid][0]
#         for idx in ps[1:-1]:
#             if sl[idx-1] == sl[idx+1]:
#                 phref_byidx[idx] = (sid, sl[idx-1])

#     return phref_byidx

# def seq_s_fromphrefidx(phref_byidx):
#     seq_s = dict(Counter(phref_byidx.values()))
#     seq_snew = {}

#     for ss, countt in seq_s.items():
#         if (ss[1], ss[0]) in seq_s:
#             seq_snew[(ss[1], ss[0])] = countt + int(seq_s[(ss[1], ss[0])])

#     return seq_snew

# def find_source_seq(t):
#     bolean, dic = t.check_phaseref
#     phref_byidx={}
#     s = set(dic['phref'].keys())
#     print(s) # debugging
#     phref_byidx = get_phref(s, sl, dic)
    
#     seq_s = seq_s_fromphrefidx(phref_byidx)
    
#     return seq_s, phref_byidx

class Phaseref:
    
    from astropy.coordinates import SkyCoord as SC
    

    
    def __init__(self, fitsfile, target_source, sep_limit=10) -> None:

        self.fitsfile               =   fitsfile
        self.target_source          =   target_source
        self.sep_limit              =   sep_limit
        self.hdul                   =   fits.open(fitsfile)

    

def find_first_occurrence(arr, sequence, occured_freq=1):
    """
    finds id of the source from the sequence for the list of array
    """
    # Convert sequence to set for faster membership testing
    sequence_set = set(sequence)
    sequence_length = len(sequence_set)
    first_occurrence_index = None
    # Find occurrences of the sequence
    occurrences = [i for i in range(len(arr) - sequence_length + 1) if set(arr[i:i+sequence_length]) == sequence_set]

    if len(occurrences)>occured_freq:
        first_occurrence_index = occurrences[0]                                                     # Find the index of the first occurrence
    return first_occurrence_index
    
def identify_sources(fitsfile):
    t = Targets(fitsfile)
    source_list = t.scanlist_arr
    s = {
        'calibrators_instrphase' : '',
        'calibrators_bandpass' : '',
        'calibrators_rldly' : None,
        'calibrators_dterms': None,
        'calibrators_phaseref' : None,
        'science_target' : None
    }
    
    science_target          =   []
    calibrators_phaseref    =   []
    isphref, dic            =   t.check_phaseref
    sd                      =   set(dic['phref'].keys())
    sourcenames             =   sources(t.hdul)
    seq_s                   =   itertools.combinations(sd,2) # TODO: when len(nsources)==3 and len (phref list_source_id)==1: make pairs with rest of ids
    if isphref:
        for seq in seq_s:
            idx_f_o_cl          =   find_first_occurrence(source_list,seq, 0)
            
            if idx_f_o_cl is not None: 
                sid = source_list[idx_f_o_cl]
                st = seq[0] if sid == seq[1] else seq[1]
                if sid not in science_target:
                    calibrators_phaseref.extend([sid])
                if st not in calibrators_phaseref:
                    science_target.extend([st])
    phrefs = list(set(dic['other'].keys()))
    if len(phrefs):
        s['calibrators_instrphase']     =   [sourcenames[s] for s in phrefs]
        s['calibrators_bandpass']       =   s['calibrators_instrphase']
    if len(science_target):
        s['science_target']             =   [sourcenames[s] for s in list(set(science_target))]
    if len(calibrators_phaseref):
        s['calibrators_phaseref']       =   [sourcenames[s] for s in list(set(calibrators_phaseref))]
    return s

def list_fromdict(d):
    nlist=set()
    d.values()
    for ss in d.values():
        if ss:
            nlist.update(ss)
    return list(nlist)


def check_band(hdul):
    """
    return band closest to S,C,X,U,K of observation
    Gregorian Bands: Q=40-50GHz, K=18-26.5GHz, U=12.4-15.4GHz, X=8.2-10.0GHz, C=3.95-5.85GHz, S=1.73-2.6GHz, L=1.15-1.73GHz
    """   
    
    freq = hdul['FREQUENCY'].header['REF_FREQ']/1.0E+09
    band = freq
    bands = {
        'S' : np.array([2.0, 3.35]),
        'C' : np.array([3.355, 5.5]),
        'X' : np.array([8.0, 12.0]),
        'U' : np.array([40.0, 60.0]),
        'K' : np.array([18.0, 27.0])
    }
    compare = 999.0
    for k,v in bands.items():
        val = (np.abs(v-freq)).min()
        
        if compare > val: 
            band = k
            compare = val
    return band

def id_flux_for_sources(hdul, sources, rfcfile, dataframe=True):
    band     = check_band(hdul)
    from vasco.util import search_sources
    
    res = search_sources(sources, rfcfile)[['IVS name', 'J2000 name', f'{band}_T-', f'{band}_Tot']]
    nsources = [source[:9] for source in sources]
    ivsname, j2name, m, flux = res.values.T
    j2name = [j2n[1:] if j2n[0]=='J' else j2n for j2n in j2name]

    dic = {}
    for s,source in enumerate(nsources):
        sid = get_source_id(hdul, sources[s])

        idx = None
        for i, isource in enumerate(ivsname):
            if source in isource: idx = i
        for j, jsource in enumerate(j2name):
            if source in jsource: idx = j
        if idx: 
            if m[idx]!='-': dic[sid[0]] = {'flux':float(flux[idx])}
        
    if dataframe:return df.from_dict(dic, orient='index', columns=['flux'])
    else: return dic
    
def find_phaseref(target_source, t, source_fluxes, flux_thres=0.150, sep_limit=2):
    """
    finds phaseref source in the sep_limit
    """
    phref_pair_res     =   t.find_phaseref_pairs(target_source, sep_limit)
    phref_id           =   phref_pair_res[:2].index
    
    phref_source,sel_pid=   [None]*2
    if not phref_id.empty:
        for p_id in phref_id:
            if p_id in source_fluxes.index:
                flux = source_fluxes['flux'][p_id]
                if flux > flux_thres:
                    sel_pid = p_id
    if sel_pid: 
        phref_source = phref_pair_res['source'][sel_pid]
    return phref_source, sel_pid

def find_phref_for_target_islowsnr(t, target_source, rfcfile, source_fluxes=None, flux_thres=150, sep_limit=2):
    """
    if scanlist is non-phaseref and target is low snr or flux missing for target 
    treat as phref. 
    But if phref not found in set sep_limit treat as non-phaseref.
    
    Returns
    ---    
    
    phaseref_source_name, phaseref_source_id
    """
    phref_source, p_id = [None]*2
    isphref, dic_phref     =   t.check_phaseref
    if source_fluxes is None: source_fluxes = id_flux_for_sources(t.hdul, t.sources_list, rfcfile)
    target_id = get_source_id(t.hdul, target_source)[0] 
    flux_target = 0
    if target_id in source_fluxes.index: # also when low snr
        flux_target    =   source_fluxes['flux'][target_id]
    if (flux_target<flux_thres) or (not target_id in source_fluxes.index):
        if not isphref:
            phref_source, p_id = find_phaseref(target_source, t, source_fluxes, sep_limit)
        
    return phref_source, p_id

def find_calibrators(hdul, calib_ids=[]):
    """
    To find calibrator sources using TSYS and refant information.
    """
    sources_dict =   sources(hdul)
    source_df    =   df(list(sources_dict.values()), index=list(sources_dict.keys()), columns=['source_name'])

    hduname,_    =   _gethduname(hdul, ['SYSTEM_TEMPERATURE'])
    sid_colname  =   _getcolname(hdul[hduname],['SOURCE_ID', 'ID_NO.', 'ID_NO'])

    tsys_rec     =   hdul[hduname].data
    tsys1_std,tsys2_std    =   [],[]
    str_ts1, str_ts2 = 'TSYS_1', 'TSYS_2'
    tsys1        =   tsys_rec[str_ts1]
    tsys2        =   tsys_rec[str_ts2] if str_ts2 in tsys_rec.columns.names else None

    
    calids = calib_ids if len(calib_ids) else list(sources_dict.keys())

    for c in calids:
        std_tsys_v = np.nanstd(np.nanmean(tsys_rec[tsys_rec[sid_colname]==c][str_ts1], axis=0))     # takes mean of all the IFs and std of all the values for the possible calibrator
        tsys1_std.append(std_tsys_v) 
        tsys2_std.append(np.nanstd(np.nanmean(tsys_rec[tsys_rec[sid_colname]==c][str_ts2], axis=0)) if tsys2 is not None else std_tsys_v ) 
        
    tsys_std    =   np.nanmean([tsys1_std, tsys2_std], axis=0)                                      # mean for non-tsys2 case is still valid because std_tsys1 = std_tsys2 in that case
    tsys_df     =   df(tsys_std, index=calids, columns=['std_tsys'])
    tsys_df     =   tsys_df.sort_values(by=['std_tsys'],ascending=[True])
    tsys_df.loc[:, 'sources'] =   source_df
#     
    return tsys_df


def identify_calibrators_from_flux(hdul, flux_df, calib_ids=[]):
    """
    find calib from TSYS and flux info
    """
    calib_df = find_calibrators(hdul, calib_ids)
#     if not flux_df.empty: 
    calib_df.loc[:, 'flux'] = flux_df
    fx = calib_df['flux'] = calib_df['flux'].fillna(0)
    ts = calib_df['std_tsys']
    ts_p = (1-np.log(ts)/ts.max())
    ts_w, fx_w = 1,1
    calib_df.loc[:, 'c'] = (ts_p*ts_w+fx*fx_w)/(ts_w+fx_w)
    
    return calib_df.sort_values(by=['c'], ascending=[False])

def identify_calibrators(hdul, flux_df, calib_ids=[]):
    """
    write dictionary after finding calib from TSYS and flux info
    """
    calib         =   {}
    
    
    _calib_df     =  find_calibrators(hdul, calib_ids) if flux_df is None else identify_calibrators_from_flux(hdul, flux_df, calib_ids)
    
    calib['calibrators_instrphase'] = calib['calibrators_bandpass'] = list(_calib_df['sources'][:2])
    return calib

def identify_sources_fromtarget(fitsfile, target_source, rfcfile=None, verbose=False, flux_df=None):
    """
    TODO: make it work for non rfcfile cases as well.
    """
    t = Targets(fitsfile)
    s = identify_sources(fitsfile)
    
    isphref, dic = t.check_phaseref
    sources_dict = sources(t.hdul)
    
    allsources=set()
    
    for ss in s.values():
        if ss:
            allsources.update(ss)
    calib_candidates = allsources.copy()
    calib_candidates.remove(target_source)
    
    
    if len(allsources)>=3:
        s['science_target'] = [target_source]
        if (flux_df is None): 
            # HACK:        to get None values back from id_flux_for_sources we use rfcfile=True
            flux_df = id_flux_for_sources(t.hdul, t.sources_list, rfcfile) if rfcfile else id_flux_for_sources(t.hdul, t.sources_list, True)
        
        
        if isphref: # check whether science target is a phaseref calibrator
            if verbose: print('is phref')
            
            ps, pid = find_phref_for_target_islowsnr(t, target_source, rfcfile, flux_df, sep_limit=18)
            
            if (target_source in s['calibrators_phaseref']) or (target_source in s['calibrators_instrphase']):
                if verbose: print('target is calib')
                if (target_source in s['calibrators_phaseref']): 
                    if verbose: print('target is phref calib')
            if not ps: 
                if verbose : print('target is in phref but ps not found')
                isphref = False
                s['calibrators_phaseref'] = None
            else:
                s['calibrators_phaseref'] = ps

    if target_source in s['calibrators_instrphase']:    s['calibrators_instrphase'].remove(target_source)
    
    id_calib_candidates = get_sources_id(sources_dict, calib_candidates)
    calib = identify_calibrators(t.hdul, flux_df ,id_calib_candidates)
    s.update(calib)
    
    return s

# def identify_targets(ispref,sdict,sourcename):
#         """
        # Depreciated: as dictionary key relative to picard input_template is used.
#         """
        
#         targets={}
#         # scanlist_arr,ind_sl=scanlist(hdul)
#         # ispref,sdict=check_phaseref(scanlist_arr)
#         # sourcename=sources(hdul)
#         if ispref:
#             st,pt,ct=_return_target(sdict)
#             # targets['phref']=[sourcename[s] for s in list(sdict['phref'])]
#             targets['science']=[sourcename[s] for s in st]
#             targets['phase']=[sourcename[p] for p in pt]
#             targets['other']=[sourcename[c] for c in ct]
            
#         else:
#             print('not phase referencing')
#             targets['science']=[sourcename[s] for s in list(sdict['other'].keys())]
        
#         return targets

def identify_refant(fitsfile, n=4, refants=[], **kwargs):
    """
    returns dataframe of first "n" best refants has id as the index
    TODO: multiply some weights to central antennas. Is necessary?
    """
    refant_found, _ = find_refant(fitsfile, **kwargs)
    if len(refants): refants =refant_found[refant_found['ANNAME'].isin(refants)][:n]#.ANNAME
    else: refants = refant_found[:n]#.ANNAME
    return refants

def find_refant(fitsfile, verbose=True, return_onmissing=False, tsys_wt=0.99, nrows_wt=0.95, distance_wt=0.80):
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
    f=fits.open(fitsfile)
    hduname,_=_gethduname(f, ['SYSTEM_TEMPERATURE'])
    
    if hduname:
        from scipy.spatial import distance
        tsys1=f[hduname].data.TSYS_1                                                                # This axis should be always present
        tsys2=None
        antenna_d=f['ANTENNA'].data
        if 'TSYS_2' in f[hduname].columns.names:tsys2=f[hduname].data.TSYS_2
        antenna=f[hduname].data.ANTENNA_NO
        antenna_dict=dict(zip(antenna_d['ANTENNA_NO'],(antenna_d['ANNAME'])))
        xyz,anname_geom=f['ARRAY_GEOMETRY'].data.STABXYZ, f['ARRAY_GEOMETRY'].data.ANNAME

        anlist,tsys1_std,tsys2_std,ancountlist,missing_antennav=[],[],[],[],[]
        ancount=Counter(antenna)
        med_d=[]
        for ant in antenna_dict.keys():

            s_ind=np.where(antenna==ant)                                                            # Select each antenna for all sources
            if len(s_ind[0]):
                anlist.append(antenna_dict[ant])    
                tsys1_std.append(np.nanmedian((np.nanstd(tsys1[s_ind], axis=0))))                         # Calculates standard deviation for each ants and then takes median
                if tsys2 is not None: tsys2_std.append(np.nanmedian((np.nanstd(tsys2[s_ind], axis=0))))
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
        
        t=QTable([anlist,tsys_std,ancountlist], names=('ANNAME', 'STD_TSYS','nRows'), meta={'name':'ANTENNA TSYS Variance'})
        t['Distance']  = [ant_with_d[ant] for ant in t['ANNAME']]
        
        for ant in missing_antennav: 
            # print(ant,"\n", t)
            t.add_row([ant, float('nan'), 0,ant_with_d[ant]])  # for antenna missing tsys value adds row with `nan`
        
        tp=t.to_pandas()
        tp.index += 1
    
        tp_res=tp
        max_nrows= tp_res['nRows'].max()
        max_distance = tp_res['Distance'].max()
        max_std_tsys = tp_res['STD_TSYS'].max()

        tsys=1-(tp_res['STD_TSYS']/max_std_tsys)
        nrows= (tp_res['nRows']/max_nrows)
        distance = 1-((tp_res['Distance']/max_distance))
        
        res=(tsys*tsys_wt+nrows*nrows_wt+distance*distance_wt)/(tsys_wt+nrows_wt+distance_wt)
        
        tp_res.insert(4,'c', res)
        tp_res = tp_res.sort_values(by='c', ascending=[False])
        print_out       =   tp_res.to_string(index=False)
        if verbose: print(print_out)
        return tp_res, print_out
    else:
        if verbose: print('missing TSYS info!\n')
        if return_onmissing: return False, False

def split(hdul, sids: list, outfits : str):
    """
    Takes hdul and splits file to 'outfits' with only 'sids' present.
    """
    if not Path(outfits).exists():
        hduname, lids = _gethduname(hdul,['UV_DATA'])
        hdul_new = hdul
        for lid in lids:
            idx = np.isin(hdul_new[lid].data.SOURCE, sids)
            # uvd = hdul_new[15].data.SOURCE[idx]
            uvd = hdul_new[lid].data[idx]
            hdr = hdul_new[lid].header
            colD= hdul_new[lid].columns

            bT  = fits.BinTableHDU.from_columns(colD)
            bT.name = hduname
            bT.data = uvd
            bT.header = hdr
            hdul_new.insert(lid, bT)
            del hdul_new[lid+1]

        hdul_new.filename = outfits  
        hdul_new.writeto(str(outfits))
        return hdul_new.filename
    else:
        print('File Exists!')
        return False

def split_up(fitsfile:str, sids: list, outfits:str):
    """
    Takes fitsfile and splits file to 'outfits' with only 'sids' present.
    """
    import shutil
    shutil.copy(fitsfile, outfits)
    with fits.open(outfits, mode='update') as hdul_new:
        hduname, lids = _gethduname(hdul_new,['UV_DATA'])
        for lid in lids:
            idx = np.isin(hdul_new[lid].data.SOURCE, sids)
            # uvd = hdul_new[15].data.SOURCE[idx]
            uvd = hdul_new[lid].data[idx]
            hdr = hdul_new[lid].header
            colD= hdul_new[lid].columns

            bT  = fits.BinTableHDU.from_columns(colD)
            bT.name = hduname
            bT.data = uvd
            bT.header = hdr
            hdul_new.insert(lid, bT)
            del hdul_new[lid+1]

        hdul_new.filename = outfits  
        return hdul_new.filename

class Targets:
    from astropy.coordinates import SkyCoord as SC
    

    
    def __init__(self,fitsfile) -> None:
        self.fitsfile               =   fitsfile
    
        # helper and output variables
        self.hdul                   =   fits.open(fitsfile)
        self.scanlist_arr,_         =   scanlist(self.hdul)
        self.sourcename             =   sources(self.hdul)
        self.SOURCE                 =   self.hdul['SOURCE'].data
        self.scolname               =   _getcolname(self.SOURCE,['SOURCE'])
        self.sources_list           =   self.SOURCE[self.scolname]
        
        self.check_phaseref         =   check_phaseref(self.scanlist_arr)

    def find_nearby_source(self, target_source):
        """
        use coordinate information in SOURCE table to look for nearest source
        returns source_name, 2d_sky_distance
        """
        ps, sep                     =   [None]*2
        # SOURCE                      =   self.hdul['SOURCE'].data
        other_sources               =   self.SOURCE[self.SOURCE.SOURCE!=target_source]

        allsources                  =   self.SC(other_sources['RAEPO']*u.degree,other_sources['DECEPO']*u.degree)
        target_source               =   self.SOURCE[self.SOURCE['SOURCE']==target_source]
        c                           =   self.SC(target_source.RAEPO*u.degree, target_source.DECEPO*u.degree)
        idx, d2d, _                 =   c.match_to_catalog_sky(allsources)
        if idx.size: ps, sep        =   other_sources[idx].SOURCE[0], d2d[0].deg
        return ps, sep

    def find_phaseref_pairs(self, target_source, sep_limit=10):
        """
        Input
        ---

        :target_source:     (str)   source to look for phase_reference as input 
        :sep_limit:         (float) separation limit in degrees

        Returns
        ---

        DataFrame with Source_ID, Sources, Chances sorted in descending by chances

        """
        slist, _                    =   scanlist(self.hdul)
        # SOURCE                      =   self.hdul['SOURCE'].data
        sid_colname                 =   _getcolname(self.SOURCE,['SOURCE_ID', 'ID_NO.', 'ID_NO'])
        other_sources               =   self.SOURCE[self.SOURCE.SOURCE!=target_source]
        id_target                   =   get_source_id(self.hdul, target_source)[0]
        target_source               =   self.SOURCE[self.SOURCE['SOURCE']==target_source]
        
        c                           =   self.SC(target_source.RAEPO*u.degree, target_source.DECEPO*u.degree)
        allsources                  =   self.SC(other_sources['RAEPO']*u.degree,other_sources['DECEPO']*u.degree)
        
        _, idxres, seps, _          =   allsources.search_around_sky(c, sep_limit*u.degree)
        
        chances                     =   [0.0]*len(idxres)

        for i, idx in enumerate(idxres):
            
            p_sep, closer_scan      =   [0.0]*2
            
            id_ps                   =   get_source_id(self.hdul, other_sources.SOURCE[idx])[0]
            p_sep                   =   sep_limit - seps[i].deg
            id_found                =   find_first_occurrence(slist, (id_ps, id_target), 0)
            if id_found is None: id_found = find_first_occurrence(slist, (id_target, id_ps))
            if id_found : closer_scan = 1
            chances[i]              =   (np.round(((1/sep_limit)*p_sep + closer_scan)/2, 3))
        res                         =   df(zip(other_sources[idxres].SOURCE, chances), index=list(other_sources[idxres][sid_colname]), columns=['source', 'chances'])
        res                         =   res.sort_values(by=['chances'], ascending=[False])
        return res