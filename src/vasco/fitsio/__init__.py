import numpy as np
from astropy.time import Time
from astropy import units as u
from fitsio import FITS
from pandas import DataFrame as df, concat
from astropy.coordinates import SkyCoord
import warnings
import itertools
from vasco import rfc_find
from vasco.util import rfc_ascii_to_df, parse_class_cat, compute_sep    
from vasco.sources import check_band


warnings.filterwarnings(action='ignore', message='ERFA function')
warnings.filterwarnings(action='ignore', message='Numerical value without unit')
warnings.filterwarnings(action='ignore', message='Unexpected extra padding')

def get_sources_id(sources_dict, sources):
    """
    returns source id for source name as input
    """
    s_df = df(list(sources_dict.values()), columns=['source_name'], index=list(sources_dict.keys()))
    sourceid = s_df[s_df['source_name'].isin(sources)]
    
    return list(sourceid.index)

def get_colnames(hdu, cols):
    matching_cols = []
    found_cols = hdu.get_colnames()
    
    for col in cols:
        matching_cols += [colname for colname in found_cols if col in colname]

    return matching_cols

def sources_fio(hdul):
    _, lids   = _gethduname_fio(hdul,['SOURCE'])
    sourced=hdul[lids[0]]
    sourcename={}
    _, cid=_getcolname_fio(sourced,['SOURCE_ID', 'SOURCE ID', 'ID_NO.', 'ID_NO'])
    _, sid=_getcolname_fio(sourced,['SOURCE'])
    alls = sourced.read_column(sid)
    for i,sid in enumerate(sourced.read_columns(cid)):
            sourcename[sid]=alls[i].strip()
    return sourcename

def scanlist_fio(hdul, combine=False):
    """
    return array of scanlist and index of the scan in the sequence of data from UV_DATA column
    """
    _, lids   = _gethduname_fio(hdul,['UV_DATA'])
    ret, nrow = {},{}
    for lid in lids:
        nrow[lid] = hdul[lid].get_nrows()
        last_ind = nrow[lid]-1
        uv_data=hdul[lid]
        
        uvsid_colname, uvsid_n=_getcolname_fio(uv_data,['SOURCE'])
        uvsid=uv_data.read_columns(uvsid_n)
        ind_inst    =   np.where(np.diff(uvsid)!=0)
        
        ind_inst    =   np.append(ind_inst,last_ind)
        
        scanlist_arr=   uvsid[ind_inst]
        ret[lid] =[scanlist_arr, ind_inst]
    if combine:
        scarr, inds, lidk=[],[],0
        for i,[arr, ind] in ret.items():
            scarr.extend(arr)
            if len(inds):
                prev_lid = list(nrow.keys())[lidk]
                lidk+=1
                ind = np.array(ind)+np.sum(list(nrow.values())[:lidk])
            inds.extend(ind)
        ret=[scarr,inds, nrow]
    return ret

def _gethduname_fio(hdulist,hdunames=['SYSTEM_TEMPERATURE']):
    _hduname=None
    hduids  = []
    allhdus = set()
    for lid,hdu in enumerate(hdulist):
        for hduname in hdunames:
            curr_hduname = hdu.get_extname()
            allhdus.add(curr_hduname)
            
            if str(hduname).upper() in str(curr_hduname).upper():
                _hduname=str(curr_hduname)
                hduids.append(lid)
    if hdunames=='*':
        _hduname = list(allhdus)
    return _hduname, hduids
    
def _getcolname_fio(data,colnames=['SOURCE']):
    _colname, cid=None, None
    for i,cname in enumerate(data.get_colnames()):
        for colname in colnames:
            if colname in str(cname).upper():
                _colname=str(cname)
                cid = i
    return _colname, cid


def get_scantime(hdu, dateobs):

    t,ti=_getcolname_fio(hdu, ['TIME'])
    
    hdutime = hdu.read_column(ti)

    zerotime=Time(dateobs, format='isot',scale='utc')
    # scantime=zerotime.mjd+scanmjd
    scantime = Time(zerotime.mjd+hdutime, format='mjd', scale='tt')
    return scantime

def listobs(fitsfile, asdf=True):
    
    hdul = FITS(fitsfile)
    dateobs=hdul[0].read_header()['DATE-OBS']
    ddic={}
    sourcename = sources_fio(hdul)
    scan_seq=0
    nspw=hdul['FREQUENCY']['BANDFREQ'][:].size
    
    for h, [scanlist_arr, ind_inst] in scanlist_fio(hdul).items():
        
        d = hdul[h]

        scantime = get_scantime(d, dateobs)
        totalrows = d.get_nrows()

        r_s=0
        for i,j in enumerate(ind_inst):

            r_e=j+1
            if j==-1:r_e=totalrows

            nrows=(r_e - r_s)*nspw
            time_inst=scantime[r_s:r_e]
            sid = scanlist_arr[i]
            CREATE_NEW_DICT=True
            if len(time_inst) :
                prev_seq=scan_seq
                
                # timeobserved=f"{time_inst[0].fits} - {time_inst[-1].fits}"
                if prev_seq in ddic.keys(): 
                    if ddic[prev_seq]['sid'] == sid:
                            ddic[prev_seq]['nrows']+=nrows
                            ddic[prev_seq]['time_end'] =time_inst[-1].fits
                            CREATE_NEW_DICT=False
                if CREATE_NEW_DICT:
                    scan_seq+=1
                    ddic[scan_seq] = {'time_start': time_inst[0].fits, 'time_end':time_inst[-1].fits, 
                              'source': sourcename[scanlist_arr[i]],
                               'sid' : sid,
                               'nrows': nrows}
            r_s=j+1
    if asdf: return df(ddic.values(), index=ddic.keys())
    return ddic

def find_first_occurrence(arr, sequence, occured_freq=1):
    """
    finds id of the source from the sequence for the list of array
    """
    
    sequence_set = set(sequence)                    # Convert sequence to set for faster membership testing
    sequence_length = len(sequence_set)
    first_occurrence_index = None
    
    occurrences = [i for i in range(len(arr) - sequence_length + 1) if set(arr[i:i+sequence_length]) == sequence_set] # Find occurrences of the sequence

    if len(occurrences)>occured_freq:
        first_occurrence_index = occurrences[0]                                                     # Find the index of the first occurrence
    return first_occurrence_index

def find_calibrators_from_tsys(t, calib_ids=[]):
    """
    To find calibrator sources using TSYS and refant information.
    """
    sources_dict =   t.sourcenames
    source_df    =   df(list(sources_dict.values()), index=list(sources_dict.keys()), columns=['source_name'])

    hduname,hid  =   _gethduname_fio(t.hdul, ['SYSTEM_TEMPERATURE'])
    calids       =  calib_ids if len(calib_ids) else list(sources_dict.keys())
    tsys2, sids_present, tsys1_std,tsys2_std        =  None, [], [], []
    if hid:
        sid_colname,scid  =   _getcolname_fio(t.hdul[hid[0]],['SOURCE_ID', 'SOURCE ID', 'ID_NO.', 'ID_NO'])

        tsys_arr     =   t.hdul[hid[0]]
        
        str_ts1, str_ts2 = 'TSYS_1', 'TSYS_2'
        tsys1        =   tsys_arr[str_ts1]
        tsys2        =   tsys_arr[str_ts2] if str_ts2 in tsys_arr.get_colnames() else None
        sids_present = tsys_arr.read()['SOURCE_ID', 'SOURCE ID']

    for c in calids:
        if len(np.shape(tsys_arr[tsys_arr.where(f"{sid_colname}=={c}")][str_ts1]))>1:           # HACK: For Mult-IF : This condition makes it work on datasets with single and multiple IF
            std_tsys_v=np.std(np.nanmean(tsys_arr[tsys_arr.where(f"{sid_colname}=={c}")][str_ts1], axis=1)) if c in sids_present else 0     # takes mean of all the IFs and std of all the values for the possible calibrator
            tsys2_std.append(np.std(np.nanmean(tsys_arr[tsys_arr.where(f"{sid_colname}=={c}")][str_ts2], axis=1)) if (tsys2 is not None) and (c in sids_present) else std_tsys_v )
        else:                                                                                   # for single IF
            std_tsys_v=np.std(tsys_arr[tsys_arr.where(f"{sid_colname}=={c}")][str_ts1]) if c in sids_present else 0
            tsys2_std.append(np.std(tsys_arr[tsys_arr.where(f"{sid_colname}=={c}")][str_ts2]) if (tsys2 is not None) and (c in sids_present) else std_tsys_v )
        tsys1_std.append(std_tsys_v)         
        
    tsys_std    =   np.nanmean([tsys1_std, tsys2_std], axis=0)                                      # mean for non-tsys2 case is still valid because std_tsys1 = std_tsys2 in that case
    tsys_df     =   df(tsys_std, index=calids, columns=['std_tsys'])
    tsys_df     =   tsys_df.sort_values(by=['std_tsys'],ascending=[True])
    tsys_df.loc[:, 'sources'] =   source_df
#     
    return tsys_df

def identify_calibrators_from_flux(t, flux_df, calib_ids=[], ts_w=1, fx_w=1):
    """
    find calib from TSYS and flux info
    """
    calib_df = find_calibrators_from_tsys(t, calib_ids)
#     if not flux_df.empty: 
    calib_df.loc[:, 'flux'] = flux_df
    fx = calib_df['flux'] = calib_df['flux'].fillna(0)
    ts = calib_df['std_tsys']
    ts_p = (1-np.log(ts)/ts.max())
    calib_df.loc[:, 'c'] = (ts_p*ts_w+fx*fx_w)/(ts_w+fx_w)
    
    return calib_df.sort_values(by=['c'], ascending=[False])

def identify_calibrators(t, flux_df, calib_ids=[]):
    """
    write dictionary after finding calib from TSYS and flux info
    """
    calib         =   {}
    _calib_df     =  find_calibrators_from_tsys(t, calib_ids) if flux_df is None else identify_calibrators_from_flux(t, flux_df, calib_ids)
    
    calib['calibrators_instrphase'] = calib['calibrators_bandpass'] = list(_calib_df['sources'][:9])
    return calib

def id_flux_for_sources(t, sources_list, rfcfile, dataframe=True, infer=False):
    
    from vasco.util import search_sources
    print(sources_list)
    res0 = search_sources(sources_list, rfcfile)
    
    res = res0[['IVS name', 'J2000 name', f'{t.band}_T-', f'{t.band}_Tot']].copy()
    print(res.to_string())
    nsources = [source_name[:9] for source_name in sources_list] # source[:9] is already used in search_sources
    ivsname, j2name, m, flux = res.values.T
    # j2name = [j2n[1:] if j2n[0]=='J' else j2n for j2n in j2name]

    dic = {}
    for s,source in enumerate(nsources):
        sid = get_sources_id(t.sourcenames, [sources_list[s]])
        inferred = False
        idx = None
        for i, isource in enumerate(ivsname):
            if source in isource: idx = i
        for j, jsource in enumerate(j2name):
            if source in jsource: idx = j

        if not idx is None:
            # print(idx, "idx")
            if m[idx]!='-': 
                dic[sid[0]] = {'flux':float(flux[idx])}
            elif infer and not inferred:
                for tband in ['S', 'C', 'X', 'U', 'K']:
                    
                    m_neg = res0[[f'{tband}_T-']].values.T[0][idx].strip()
                    if m_neg!='-' and not sid[0] in dic:
                        flx = float(res0[[f'{tband}_Tot']].values.T[0][idx].strip())
                        dic[sid[0]] = {'flux':flx}
                        inferred = True
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
    treats as phref. 
    checks if flux of target source is below the flux_thres (mJy)

    
    But if phref not found in set sep_limit treat as non-phaseref.
    
    Returns
    ---    
    
    phaseref_source_name, phaseref_source_id
    """
    phref_source, p_id = [None]*2
    
    if not hasattr(t,'isphref'): isphref,_  =   t.check_phaseref() # TODO : instead put t.isphref inside t.check_phaseref()
    else: isphref = t.isphref
    if source_fluxes is None: source_fluxes = id_flux_for_sources(t, rfcfile, infer=True)
    
    target_id = get_sources_id(t.sourcenames, [target_source])[0] 
    flux_target = None
    if target_id in source_fluxes.index: # also when low snr
        flux_target    =   source_fluxes['flux'][target_id]
    
    if flux_target and flux_target>flux_thres:
        t.isphref = False
    else:
        if not target_id in source_fluxes.index:
            if not isphref:
                phref_source, p_id = find_phaseref(target_source, t=t, source_fluxes=source_fluxes, sep_limit=sep_limit)
    
        
    return phref_source, p_id

def identify_sources_fromtarget(fitsfile, target_source, rfcfile=None, verbose=False, flux_df=None):
    """
    TODO: make it work for non rfcfile cases as well.
    [ ] make it work with coordinate search
    """
    t = IdentifySource(fitsfile)
    s = t.identify_sources()
    if not rfcfile: rfcfile = t.rfcfile
    
    allsources=set()
    calib_from_seq=set()
    for k,ss in s.items():
        if ss:
            allsources.update(ss)
            if 'calibrator' in k:calib_from_seq.update(ss)
    # print(allsources)
    calib_from_seq = list(calib_from_seq).copy()
    calib_candidates = allsources.copy()
    calib_candidates.remove(target_source)
    alls = list(allsources).copy()
    
    if len(allsources)>=2:
        s['science_target'] = [target_source]
        if (flux_df is None): 
            # HACK:        to get None values back from id_flux_for_sources we use rfcfile=True
            flux_df = id_flux_for_sources(t, alls, rfcfile, infer=True) if rfcfile else id_flux_for_sources(t, alls, True)
        
        if t.isphref: # check whether science target is a phaseref calibrator
            if verbose: print('is phref')
            
            ps, pid = find_phref_for_target_islowsnr(t, target_source, rfcfile, source_fluxes=flux_df, sep_limit=20)
            
            if (target_source in calib_from_seq):
                
                if s['calibrators_phaseref']:
                    if (target_source in s['calibrators_phaseref']): 
                        if verbose: print('target is phref calib')
                    else:
                        if verbose: print('target is calib')
            if not ps: 
                if verbose : print('target is in phref but ps not found')
                t.isphref = False
                s['calibrators_phaseref'] = None
                
            else:
                s['calibrators_phaseref'] = ps
                if ps in calib_candidates: calib_candidates.remove(ps)      # See identify_calibrators_comment
    # else:
    #     s['calibrators_instrphase'] = [target_source]

    if target_source in s['calibrators_instrphase']:    s['calibrators_instrphase'].remove(target_source)
    
    id_calib_candidates = get_sources_id(t.sourcenames, calib_candidates)
    calib = identify_calibrators(t, flux_df ,id_calib_candidates)           # identify_calibrators_comment: Only calibrators_instrphase and calibrators_bandpass will be updated
    s.update(calib)
    
    return s


class IdentifySource:
    from astropy.coordinates import SkyCoord as SC
    def __init__(self, fitsfile):
        self.hdul = FITS(fitsfile)
        self.sourcenames             =   sources_fio(self.hdul)
        self.band = self.check_band()
        self.rfcfile = rfc_find(write=False)
        self.isphref = None

    def check_band(self, bands=None):
        """
        return band closest to S,C,X,U,K of observation
        """   
    
        freq = self.hdul['FREQUENCY'].read_header()['REF_FREQ']/1.0E+09
        band = freq
        if not bands:
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

    def check_phaseref(self):
        """
        check scan list and see if phase referencing is used.
        """
        self.scanlist_arr, self.scanlist_ind, self.scanlist_nrow = scanlist_fio(self.hdul, combine=True)
        sdict={'phref':{}, 'other':{}}
        isTrue=False
        sources=np.unique(self.scanlist_arr)    
        for source in sources:
            source_seq_ind=np.where(source==self.scanlist_arr)
            phaseref_ind=np.where(np.diff(source_seq_ind)[0]==2)[0]
            if len(phaseref_ind)>1:
                isTrue=True
                sdict['phref'][source]=source_seq_ind
            else:
                sdict['other'][source]=source_seq_ind
        return isTrue,sdict
    
    def identify_sources(self):
#     t = Targets(fitsfile)
        self.isphref, dic            =   self.check_phaseref()
        scan_list_arr           =   self.scanlist_arr
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
        
        sd                      =   set(dic['phref'].keys())
        
        seq_s                   =   itertools.combinations(sd,2) # TODO: when len(nsources)==3 and len (phref list_source_id)==1: make pairs with rest of ids
        if self.isphref:
            for seq in seq_s:
                idx_f_o_cl          =   find_first_occurrence(scan_list_arr,seq, 0)
                
                if idx_f_o_cl is not None: 
                    sid = scan_list_arr[idx_f_o_cl]
                    st = seq[0] if sid == seq[1] else seq[1]
                    if sid not in science_target:
                        calibrators_phaseref.extend([sid])
                    if st not in calibrators_phaseref:
                        science_target.extend([st])
            if len(sd)==1:
                """meaning the pair for one of the phref source was not 
                found - most likely a science target
                """
                science_target.extend(sd)
                
        other = list(set(dic['other'].keys()))
        if len(other):            
            s['calibrators_instrphase']     =   [self.sourcenames[o] for o in other]
            s['calibrators_bandpass']       =   s['calibrators_instrphase']
        if len(science_target):
            s['science_target']             =   [self.sourcenames[o] for o in list(set(science_target))]
        if len(calibrators_phaseref):
            s['calibrators_phaseref']       =   [self.sourcenames[o] for o in list(set(calibrators_phaseref))]
        return s
    
    def find_phaseref_pairs(self, target_source, sep_limit=10):
        """
        assumes isphref is True
        
        Input
        ---

        :target_source:     (str)   source to look for phase_reference as input 
        :sep_limit:         (float) separation limit in degrees

        Returns
        ---

        DataFrame with Source_ID, Sources, Chances sorted in descending by chances

        """
        _, lids                     =   _gethduname_fio(self.hdul,['SOURCE'])
        SOURCE                      =   self.hdul[lids[0]]
        sid_colname,scid            =   _getcolname_fio(SOURCE,['SOURCE_ID', 'SOURCE ID', 'ID_NO.', 'ID_NO'])
        
        other_sources               =   SOURCE.read()[SOURCE.read()['SOURCE']!=target_source]
        id_target                   =   get_sources_id(self.sourcenames, [target_source])[0]
        target_source               =   SOURCE.read()[SOURCE.read()['SOURCE']==target_source]
        
        c                           =   self.SC(target_source['RAEPO']*u.degree,target_source['DECEPO']*u.degree)
        allsources                  =   self.SC(other_sources['RAEPO']*u.degree,other_sources['DECEPO']*u.degree)
        
        _, idxres, seps, _          =   allsources.search_around_sky(c, sep_limit*u.degree)
        
        chances                     =   [0.0]*len(idxres)

        for i, idx in enumerate(idxres):
            
            p_sep, closer_scan      =   [0.0]*2
            
            id_ps                   =   get_sources_id(self.sourcenames, [other_sources['SOURCE'][idx]])[0]
            p_sep                   =   sep_limit - seps[i].deg
            if not hasattr(self,'scanlist_arr'): 
                self.scanlist_arr, self.scanlist_ind, self.scanlist_nrow = scanlist_fio(self.hdul, combine=True)
            id_found                =   find_first_occurrence(self.scanlist_arr, (id_ps, id_target), 0)
            if id_found is None: id_found = find_first_occurrence(self.scanlist_arr, (id_target, id_ps))
            if id_found : closer_scan = 1
            chances[i]              =   (np.round(((1/sep_limit)*p_sep + closer_scan)/2, 3))
        res                         =   df(zip(other_sources[idxres]['SOURCE'], chances), index=list(other_sources[idxres][sid_colname]), columns=['source', 'chances'])
        res                         =   res.sort_values(by=['chances'], ascending=[False])    
        
def rfc_search_from_fits(fitsfile, rfc_filepath, seplimit=5e3, thres_sep=1e4):
    from vasco.util import rfc_parse_search_pattern, SkyCoord, rfc_ascii_to_df, compute_sep, concat
    
    frame           =   'icrs'
    fo              =   FITS(fitsfile, mode='r')
    shdu            =   fo.movnam_hdu('SOURCE')
    
    target_names    =   fo[shdu-1].read()['SOURCE']
    
    idx_found       =   np.zeros(np.shape(target_names), dtype=bool)
    
    match_res       =   rfc_parse_search_pattern(rfc_filepath, patterns=target_names, verbose=False, col_rows=4, search_key='fits_target')
    
    if not match_res.empty:
        idx_found       =   np.in1d(target_names, match_res['fits_target'].values)
    
    ra              =   fo[shdu-1].read()['RAEPO']*u.deg
    dec             =   fo[shdu-1].read()['DECEPO']*u.deg
    target_coords   =   SkyCoord(ra,dec, frame=frame)
    epoch         =   np.unique(fo[shdu-1].read()['EPOCH'])
    
    if not len(epoch)==1:
    #     frame       =   frame if epoch[0] == 2000 else frame
    # else:
        raise ValueError(f'Multiple EQUINOX values are not supported yet : {epoch}')
    
    if not match_res.empty:
        match_res['sep'] = match_res.apply(lambda row: compute_sep(row, target_names, target_coords), axis=1, )
        
        # if not match_res['fits_target'].is_unique:
        #     ...
        # check if multiple results, sort by the closest one remove the one above sepration threshold
        
        idx_overthres_fits    =  np.in1d(target_names,match_res[match_res['sep']>thres_sep].values)
        idx_found[idx_overthres_fits] = False
        
        idx_overthres_df    =  np.in1d(match_res['sep'].values,match_res[match_res['sep']>thres_sep].values)
        idx_overthres_arg   =   np.argwhere(idx_overthres_df).T[0]
        print("  found by name but separation above threshold, ignoring....", " ".join(match_res.loc[idx_overthres_df]['fits_target']))
        match_res.drop(index=idx_overthres_arg, inplace=True)
        
    if any(~idx_found):
        print("  searching by coordinate for..."," ".join(target_names[~idx_found]))
        
        
        df_rfc = rfc_ascii_to_df(rfc_filepath)
        
        catalog = SkyCoord(df_rfc['coordinate'].values, frame=frame)
        
        idxtarget, idxself, sep2d, dist3d = catalog.search_around_sky(target_coords[~idx_found], seplimit=seplimit*u.milliarcsecond)
        df_coord_search = df_rfc.loc[idxself]
        df_coord_search['sep'] = sep2d.milliarcsecond
        df_coord_search['fits_target'] = target_names[~idx_found][idxtarget]
        if not match_res.empty:
            # match_res['sep'] = match_res.apply(lambda row: compute_sep(row, target_names, target_coords), axis=1, )
            df_coord_search = df_coord_search[match_res.columns]
            df_coord_search.index =  df_coord_search.index + 10000
        
        match_res = concat([match_res, df_coord_search])
        match_res = match_res.drop(columns=['RAh', 'RAm','RAs', 'DE-', 'DEd', 'DEm', 'DEs', 'Nobs', 'Nsca', 'Nses', 'Corr'],errors='ignore')
        if 'coordinate' in match_res:
            match_res.insert(2, 'coordinate', match_res.pop('coordinate'))
        if 'sep' in match_res:
            match_res.insert(0, 'sep', match_res.pop('sep'))
        
    return match_res



# def catalog_search_from_fits(fitsfile, df_catalog, seplimit, thres_sep, source_name_col='Obsname', frame='icrs'):
    
#     from vasco.util import SkyCoord, compute_sep, concat
#     if 'GB6' in df_catalog.columns:
#         df_catalog      =   df_catalog.drop_duplicates(subset='GB6', keep='first')#.set_index('GB6')
    
#     fo              =   FITS(fitsfile, mode='r')
#     shdu            =   fo.movnam_hdu('SOURCE')
    
#     target_names    =   fo[shdu-1].read()['SOURCE']
#     idx_found       =   np.zeros(np.shape(target_names), dtype=bool)        # i.e not found
    
#     ra              =   fo[shdu-1].read()['RAEPO']*u.deg
#     dec             =   fo[shdu-1].read()['DECEPO']*u.deg
#     target_coords   =   SkyCoord(ra,dec, frame=frame)
#     epoch           =   np.unique(fo[shdu-1].read()['EPOCH'])
    
#     if len(epoch)==1:
#         frame       =   'icrs' if epoch[0] == 2000 else 'icrs'
#     else:
#         raise ValueError(f'Multiple EQUINOX values are not supported yet : {epoch}')
    
#     match_res       =   df_catalog[df_catalog[source_name_col].isin(target_names)]
#     if not match_res.empty:
#         idx_found       =   np.in1d(target_names, match_res[source_name_col].values)
    
#     if source_name_col in match_res.columns: match_res            =   match_res.rename(columns={source_name_col:'fits_target'})                     # since each row found corrosponds to the name match from fits
#                                                                                                                                                         # assumes the column will be populated with consistency
#     if 'fits_target' in match_res.columns: match_res['sep'] =   match_res.apply(lambda row: compute_sep(row, target_names, target_coords, frame), axis=1 )
    
#     if any(~idx_found):
#         print("  searching by coordinate for..."," ".join(target_names[~idx_found]))
    
#         catalog                             =   SkyCoord(df_catalog['coordinate'].values, unit=(u.hourangle, u.deg), frame=frame)
        
#         idxtarget, idxself, sep2d, dist3d   =   catalog.search_around_sky(target_coords[~idx_found], seplimit=seplimit*u.milliarcsecond)
#         df_coord_search                     =   df_catalog.iloc[idxself].copy()
#         df_coord_search['sep']              =   sep2d.milliarcsecond
        
#         df_coord_search['fits_target']      =   target_names[~idx_found][idxtarget]                                                                             # important in order to keep consistency.
        
#         if not match_res.empty:
#             df_coord_search                 =   df_coord_search[match_res.columns]
#             df_coord_search.index =  df_coord_search.index + 10000
        
#         match_res = concat([match_res, df_coord_search])
#         # match_res = match_res.drop(columns=['RAh', 'RAm','RAs', 'DE-', 'DEd', 'DEm', 'DEs', 'Nobs', 'Nsca', 'Nses', 'Corr'],errors='ignore')
#         if 'coordinate' in match_res:
#             match_res.insert(2, 'coordinate', match_res.pop('coordinate'))
#         if 'sep' in match_res:
#             match_res.insert(0, 'sep', match_res.pop('sep'))
        
#     return match_res

def df_source_fits(fitsfile, frame='icrs', coord_col= 'fits_coordinate'):
    fo              =   FITS(fitsfile, mode='r')
    shdu            =   fo.movnam_hdu('SOURCE')
    source_hdu      =   fo[shdu-1]

    target_names    =   source_hdu.read()['SOURCE']
    idx_found       =   np.zeros(np.shape(target_names), dtype=bool)        # i.e not found

    sid_colname     =   get_colnames(source_hdu, ['ID_NO','ID_NO.', 'SOURCE_ID', 'SOURCE ID'])[0]

    sids            =   source_hdu[sid_colname].read()
    ra              =   source_hdu['RAEPO'].read()*u.deg
    dec             =   source_hdu['DECEPO'].read()*u.deg
    target_coords   =   SkyCoord(ra,dec, frame=frame)
    epoch           =   np.unique(source_hdu.read()['EPOCH'])
    
    dic_df = {coord_col:target_coords.to_string('hmsdms', sep=':'), 'fits_target': target_names}
    return df(dic_df)

def df_search_brightcalib_rfc(fitsfile, rfc_filepath, class_filepath, scanlist_arr, targets=[], 
                              seplimit=5e3, thres_sep=1e4, crossmatch_sep=600, outfile='', nfilter_sources=20):
    """
    TODO: Increase seplimit for sources which were not found by the seplimit 
        else add name in smile complete list for negative name matches but positive coordinate cross-match
    
    """
    fo              =   FITS(fitsfile, mode='r')
    shdu            =   fo.movnam_hdu('SOURCE')
    hdu = fo[shdu-1]


    sid_colname = get_colnames(hdu, ['ID_NO', 'ID_NO.','SOURCE_ID', 'SOURCE ID'])[0]
    sids = hdu[sid_colname].read()
    stargets = hdu['SOURCE'].read()
    dic_targets = dict(zip(stargets, sids))
    
    bandfreq = fo['FREQUENCY']['BANDFREQ'].read()
    reffreq = fo['FREQUENCY'].read_header()['REF_FREQ']
    bands = set([check_band(freq) for freq in (bandfreq + reffreq).flatten()/1e9])

    cols_req = [f'Fm{band}' for band in bands]
    
    
    df_rfc = rfc_ascii_to_df(rfc_filepath)
    df_class = parse_class_cat(class_filepath) # '/data/avi/d/smile/smile_complete_table.txt'
    
#     df_search_rfc = catalog_search_from_fits(ff, df_rfc, seplimit=150, 
#                                              thres_sep=5e2, include_not_found=True, 
#                                              source_name_col='Comnam', verbose=True)
    
    coord_search_class = catalog_search_from_fits(fitsfile, df_class, seplimit=seplimit, 
                                                  thres_sep=thres_sep, 
                                                  include_not_found=True)
        
    rfc_catalog = SkyCoord(df_rfc['coordinate'].values, unit=(u.hourangle, u.deg), frame='icrs')
    fits_sources = SkyCoord(coord_search_class['coordinate'].values, unit=(u.hourangle, u.deg), 
                            frame='icrs')
    
    idxtarget, idxself, sep2d, dist3d   =   rfc_catalog.search_around_sky(fits_sources, 
                                                                          seplimit=300*u.mas)
    
    df_res_rfcsearch = df()

    # We have searched for all the sources, now searching flux
    df_rfc['fits_target'] = ''
    df_rfc.loc[idxself, 'fits_target'] = coord_search_class.reset_index().iloc[idxtarget]['fits_target'].values         # reset_index because the index here is not same as the fits_source, as the later uses .values; so need to reindex
    df_rfc['sid'] = df_rfc['fits_target'].map(dic_targets)
    
    coord_search_class['sid'] = coord_search_class['fits_target'].map(dic_targets)
    
    # checking which sources dont have any data in UV_DATA
    df_rfc_filtered = df_rfc[df_rfc['sid'].isin(set(scanlist_arr))]
    
    # search for flux info in each band
    for col_req in cols_req:
        df_res_rfcsearch = concat([df_rfc_filtered.sort_values(by=col_req, ascending=False),
                                    df_res_rfcsearch]).head(nfilter_sources)
    # add targets
    df_res_rfcsearch = concat([df_res_rfcsearch,     
                              coord_search_class[coord_search_class['fits_target'].isin(targets)][['coordinate', 'sep', 'fits_target', 'sid', 'GB6']]]
                             )
    
    df_res_rfcsearch = df_res_rfcsearch.drop_duplicates(['fits_target'])
    df_res_rfcsearch['sid'] = df_res_rfcsearch['sid'].astype('int')
    
    
    if outfile:
        with open(outfile, 'w') as of:
            of.write(df_res_rfcsearch.to_string())
            
    return df_res_rfcsearch

# def catalog_search_from_coord(coord, ):
    

def catalog_search_from_fits(fitsfile, df_catalog, seplimit, thres_sep, source_name_col='Obsname', 
                             frame='icrs', include_not_found=False, verbose=False, outdir=''):
    from astropy.table import Table
    from astropy.io import fits
    if source_name_col in df_catalog.columns:
        df_catalog      =   df_catalog.drop_duplicates(subset=source_name_col, keep='first')
    
    fo              =   FITS(fitsfile, mode='r', encodeing='latin-1')
    shdu            =   fo.movnam_hdu('SOURCE', hdutype=2)
    source_hdu      =   fo[shdu-1]
    
    target_names    =   source_hdu.read()['SOURCE']
    # hdu_astropy = fits.open(fitsfile)
    # target_names = hdu_astropy['SOURCE'].data['SOURCE']
    # target_names = [tn for tn in target_names]
    
    idx_found       =   np.zeros(np.shape(target_names), dtype=bool)        # i.e not found
    
    sid_colname     =   get_colnames(source_hdu, ['ID_NO','ID_NO.', 'SOURCE_ID', 'SOURCE ID'])[0]
    
    sids            =   source_hdu[sid_colname].read()
    # sids            =   hdu_astropy['SOURCE'].data[sid_colname]
    ra              =   source_hdu['RAEPO'].read()*u.deg
    dec             =   source_hdu['DECEPO'].read()*u.deg
    target_coords   =   SkyCoord(ra,dec, frame=frame)
    epoch           =   np.unique(source_hdu.read()['EPOCH'])
    # epoch           =   np.unique(hdu_astropy['SOURCE'].data['EPOCH'])
    
    if not len(epoch)==1: raise ValueError(f'Multiple EQUINOX values are not supported yet : {epoch}')
    
    # searching by name first
    match_res       =   df_catalog[df_catalog[source_name_col].isin(target_names)]
    
    if not match_res.empty:
        idx_found       =   np.in1d(target_names, match_res[source_name_col].values)
    
    # since each row found corrosponds to the name match from fits
    if source_name_col in match_res.columns: match_res            =   match_res.rename(columns={source_name_col:'fits_target'})                     
        
    if 'fits_target' in match_res.columns: match_res['sep'] =   match_res.apply(lambda row: compute_sep(row, target_names, target_coords, frame), axis=1 )
    
    if any(~idx_found):
        if verbose: print("  searching by coordinate for..."," ".join(target_names[~idx_found]))
    
        catalog                             =   SkyCoord(df_catalog['coordinate'].values, unit=(u.hourangle, u.deg), frame=frame)
        
        idxtarget, idxself, sep2d, dist3d   =   catalog.search_around_sky(target_coords[~idx_found], seplimit=seplimit*u.milliarcsecond)
        df_coord_search                     =   df_catalog.iloc[idxself].copy()
        df_coord_search['sep']              =   sep2d.milliarcsecond
        
        # important in order to keep consistency.
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

def count_tsys_in_fitsfile(fitsfile, target=None):
    fo              =   FITS(fitsfile, mode='r', 
                            #  encodeing='latin-1'
                             )
    shdu            =   fo.movnam_hdu('SOURCE', hdutype=2)
    source_hdu      =   fo[shdu-1]
    
    count_tsys      =   0
    if any(['SYSTEM_TEMPERATURE' in [hdu.get_extname() for hdu in fo]]):
        thdu            =   fo.movnam_hdu('SYSTEM_TEMPERATURE', hdutype=2)
        tsys_hdu        =   fo[thdu-1]
        sid_colname     =   get_colnames(source_hdu, ['ID_NO', 'ID_NO.', 'SOURCE_ID', 'SOURCE ID', 'SOURCE_ID.'])[0]


        count_tsys      =   tsys_hdu.get_nrows()

        if target:
            target_names    =   source_hdu['SOURCE'].read()
            sid             =   source_hdu.read()[target_names==target][sid_colname][0]
            sid_colname     =   get_colnames(tsys_hdu, ['ID_NO','ID_NO.', 'SOURCE_ID', 'SOURCE ID', 'SOURCE_ID.'])[0]
            count_tsys      =   len(tsys_hdu.read()[tsys_hdu.read()[sid_colname]==sid])
    return count_tsys