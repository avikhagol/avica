import numpy as np
from pandas import DataFrame as df
import itertools

def check_band(freq, bands=None):
        """
        Input
        ---

        freq            (float)
                        value of the reference fequency in GHz

        bands           (dict)
                        dictionary of bands containing numpy array of limiting values of range of the band.

        Return
        ---
        
        band closest to S,C,X,U,K,Q,W of observation

        https://science.nrao.edu/facilities/vlba/docs/manuals/oss/bands-perf
        """   
        band = freq
        if not bands:
            bands = {
            'S' : np.array([2.0, 2.6]),
            'C' : np.array([3.5, 6.4]),
            'X' : np.array([7.401, 8.8]),
            'U' : np.array([11.8, 15.7]),
            'K' : np.array([20.0, 25.0]),
            'Q' : np.array([40.0, 46.0]),
            'W' : np.array([80.0, 90.0]),
        }
        compare = 999.0
        for k,v in bands.items():
            val = (np.abs(v-freq)).min()

            if compare > val: 
                band = k
                compare = val
        return band

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

def get_sources_id(sources_dict, sources):
    """
    returns source id for source name as input
    """
    s_df = df(list(sources_dict.values()), columns=['source_name'], index=list(sources_dict.keys()))
    sourceid = s_df[s_df['source_name'].isin(sources)]
    
    return list(sourceid.index)

def find_phaseref_pairs(c_target, target, c_others, others, scanlist_seq, sourcenames, sep_limit=10):
        """
        assumes isphref is True
        
        Input
        ---

        :c_target:     (SkyCoord Object) coordinate of the target
        :target:       (str)   source to look for phase_reference as input 
        
        :c_others:     (SkyCoord Object) coordinate of the target
        :others:       (list)  other sources to look for potential phase_reference pair from
        :sep_limit:    (float) separation limit in degrees

        Returns
        ---

        DataFrame with Source_ID, Sources, Chances sorted in descending by chances
        
        where 
        p_sep = sep_limit - source_sep # a comparison parameter e.g closer to sep_limit is not good indicator for a pair
        closer_scan = 1 if occurs in pair even once with the target
        chance = ((1/sep_limit)*p_sep + closer_scan)/2

        """

        c                           =   c_target
        allsources                  =   c_others
        
        idxres                      =   allsources.separation(c)
        idx_target                  =   list(sourcenames.values()).index(target)
        id_target                   =   list(sourcenames.keys())[idx_target]
        
        chances                     =   [0.0]*len(idxres)
        other_dict                  =   sourcenames.copy()
        other_dict.pop(id_target)
        
        for i,seps in enumerate(idxres):
            p_sep, closer_scan      =   [0.0]*2
            id_ps                   =   list(sourcenames.values()).index(others[i])
            p_sep                   =   sep_limit - seps.deg
            id_found                =   find_first_occurrence(scanlist_seq, (id_ps, id_target), 0)
            if id_found is None: id_found = find_first_occurrence(scanlist_seq, (id_target, id_ps))
            if id_found : closer_scan = 1
            chances[i]              =   (np.round(((1/sep_limit)*p_sep + closer_scan)/2, 3))
        print(others)
        print(chances)
        print(other_dict,"\n",list(other_dict.keys()))
        res                         =   df()
        res                         =   df(zip(others, chances), index=list(other_dict.keys()), columns=['source', 'chances'])
        res                         =   res.sort_values(by=['chances'], ascending=[False])    
        return res

class Sources:
    def __init__(self, scanlist_seq, sourcenames):
        self.scanlist_seq = scanlist_seq
        self.sourcenames  = sourcenames
        
    def check_phaseref(self):
        sdict={'phref':{},'other':{}}
        isTrue=False
        sources=np.unique(self.scanlist_seq)
        for source in sources:
            source_seq_ind=np.where(source==self.scanlist_seq)
            phaseref_ind=np.where(np.diff(source_seq_ind)[0]==2)[0]
            if len(phaseref_ind)>1:
                isTrue=True
                sdict['phref'][source]=source_seq_ind
            else:
                sdict['other'][source]=source_seq_ind
        return isTrue,sdict

    def identify_sources(self):
        s = {
                'calibrators_instrphase' : '',
                'calibrators_bandpass' : '',
                'calibrators_rldly' : None,
                'calibrators_dterms': None,
                'calibrators_phaseref' : None,
                'science_target' : None
            }
        self.isphref, dic            =   self.check_phaseref()
        science_target          =   []
        calibrators_phaseref    =   []
        
        sd                      =   set(dic['phref'].keys())
        
        seq_s                   =   itertools.combinations(sd,2) # TODO: when len(nsources)==3 and len (phref list_source_id)==1: make pairs with rest of ids
        
        if self.isphref:
            for seq in seq_s:
                idx_f_o_cl          =   find_first_occurrence(self.scanlist_seq,seq, 0)
                
                if idx_f_o_cl is not None: 
                    sid = self.scanlist_seq[idx_f_o_cl]
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
    


def find_phref_for_target_islowsnr(t, target_source, other_sources, c_target, c_others ,  caliblist_file, source_fluxes, flux_thres=0.150, sep_limit=2):
    """
    if scanlist is non-phaseref and target is low snr or flux missing for target 
    treats as phref. 
    checks if flux of target source is below the flux_thres (Jy)

    
    But if phref not found in set sep_limit treat as non-phaseref.
    
    Returns
    ---    
    
    phaseref_source_name, phaseref_source_id
    """
    phref_source, p_id = [None]*2
    
    if not hasattr(t,'isphref'): t.check_phaseref() # TODO : instead put t.isphref inside t.check_phaseref()
#     else: isphref = t.isphref
#     if source_fluxes is None: source_fluxes = id_flux_for_sources(t, caliblist_file)
    
    target_id = get_sources_id(t.sourcenames, [target_source])[0] 
    flux_target    =   source_fluxes['flux'][target_id] if target_id in source_fluxes.index else None
#     print("flux target", flux_target)
    if flux_target and flux_target>flux_thres:
        # print("target is bright")
        t.isphref = False
    else: # low snr case
#         if not target_id in source_fluxes.index: 
        if t.isphref:
#                 phref_source, p_id = find_phaseref(target_source, t=t, source_fluxes=source_fluxes, sep_limit=sep_limit)
            #
            df_pairs = find_phaseref_pairs(c_target=c_target, target=target_source, others=other_sources, c_others=c_others, scanlist_seq=t.scanlist_seq, sourcenames=t.sourcenames)
            phref_pairs = df_pairs.loc[df_pairs['chances']>0.10]
#             print(phref_pairs)
            if not phref_pairs.empty:
                phref_source = phref_pairs[:1]['source'].values[0]
                p_id         = phref_pairs[:1].index[0]
    return phref_source, p_id

def id_flux_for_sources(sourcenames, sources_list,  caliblist_file, band='C'):
    
    from vasco.util import search_sources
    
    res = search_sources(sources_list, caliblist_file)
    if band and f'{band}_T-' in res.columns:
        res = res[['IVS name', 'J2000 name', f'{band}_T-', f'{band}_Tot', 'orig_sourcename']]
    _, _, m, flux, orig_srcs = res.values.T if not res.empty else ([], [], [], [], [])
    dic = {}
    sids = get_sources_id(sourcenames, orig_srcs)
    
    for s,sid in enumerate(sids):
        if m[s]!='-':
            dic[sid] = {'flux':float(flux[s])}
    
    return df.from_dict(dic, orient='index', columns=['flux'])

def choose_calib_for_snr_rating(all_sci_ant, calibrator_df_sorted_desc, n_ant=9):
    """
    the calibrator sources are selected from the provided dataframe based on the needed science antenna,
    :all_sci_ant:
                                    (list | required )
                                    list of the name of the antennas.
    :calibrator_df_sorted_desc:
                                    (pandas.DataFrame | required)
                                    with atleast columns: source, antennas
                                    
    Returns
    -----
    
    :sel_calibrator:
                                    (list)
                                    list of calibrator sources selected
    :remain_ant:
                                    (set)
                                    returns a set of antennas not found in the provided dataframe
    """
    _remain_ant = set(all_sci_ant)

    _sel_calibrator = []
    count_cal       =   0

    for calibrator in calibrator_df_sorted_desc['source']:
        idx = calibrator_df_sorted_desc['source']==calibrator
        if (count_cal<n_ant) or any(remain_an in calibrator_df_sorted_desc.loc[idx]['antennas'].values[0] for remain_an in _remain_ant):
            _sel_calibrator.append(calibrator)

            common_ant = np.intersect1d(calibrator_df_sorted_desc.loc[idx]['antennas'].values[0], all_sci_ant)
            _remain_ant = _remain_ant.difference(common_ant)
            count_cal   +=  1
            # if (not _remain_ant) and (count_cal>=n_ant): 
            #     print(count_cal)
            #     break
        
    return _sel_calibrator, _remain_ant
    

def identify_calibrators(t, target, ps, flux_thres, flux_df, min_flux=0.025, ncalib=9, calib_ids=[], hard_selection=False, flux_comparison_factor=1.8):
    """
    write dictionary after finding calib from TSYS and flux info

    assumes df_flux 
    has correct field ids as index and `flux` column
    
    :flux_comparison_factor:    (float)
                                currently not used
    """
    target_bright               =   False
    calib,least_calib           =   {}, 1
    calib_df                    =   df(list(t.sourcenames.values()), index=list(t.sourcenames.keys()), columns=['source_name'])
    calib_df.loc[:, 'flux']     =   flux_df
    fx = calib_df['flux']       =   calib_df['flux'].fillna(0)
    calib_df                    =   calib_df.sort_values(by=['flux'], ascending=[False])
    target_flux                 =   calib_df.loc[calib_df['source_name']==target]['flux'].values[0]
    chk_flux                    =   min_flux
    if target_flux >= flux_thres :
        target_bright           =   True
        least_calib             =   2                       # we can increase this to 1 or 2
        # chk_flux                =   target_flux*flux_comparison_factor         # to check if there is calibrator with higher flux present; 1.8 is random; # This creates problem when there are calibrators with refant missing. Using similar SNR calibrator e.g 30 is fine
    calib_df                    =   calib_df.loc[calib_ids]
    calib_df                    =   calib_df.sort_values(by=['flux'], ascending=[False])
    bright_calib_df             =   calib_df.loc[calib_df['flux']>chk_flux]         # even if target is bright if there is a brighter calib let's choose that as intr/bandpass calib.
    
    calib_df_selected           =   calib_df.loc[calib_df['flux']>chk_flux] if (len(calib_df['source_name'])>=least_calib and (hard_selection or len(calib_df['source_name'])>ncalib)) else calib_df        # if hard_selection select 2 calib only
    list_calib                  =   list(calib_df_selected['source_name'][:ncalib]) if not calib_df_selected.empty else list(calib_df['source_name'][:ncalib])
    
    if target_bright:        
        calib['calibrators_phaseref'] = None
        if target not in list_calib:
            if len(bright_calib_df):
                list_calib      =   list(calib_df_selected['source_name'][:ncalib])
                calib['science_target'] = [target]
            # if not hard_selection:          # use ncalib to restrict number of calibrator using least_calibrator. i.e let this get extended
            else:
                calib['science_target'] = None
                list_calib.extend([target])
            # else:
            #     list_calib  =   [target]
    else:
        print('target not bright enough')
        if target in list_calib: list_calib.remove(target)
        if ps and (ps in list_calib) : list_calib.remove(ps)
    calib['calibrators_instrphase'] = calib['calibrators_bandpass'] = list_calib
    return calib

def identify_sources_fromtarget(scanlist_seq, sourcenames, target_source, other_sources, c_target, c_others, 
                                   band='C', flux_thres=0.150, min_flux=0.025, ncalib=9, caliblist_file=None, verbose=False, flux_df=None,
                                   hard_selection=False):
    """
    Input
    ---

    :scanlist_seq:          (list)
                            list of scan numbers in the sequence of occurance.

    :sourcenames:           (dict)
                            dict with key, value -> {field_id : field_name}

    :target_source:         (string)
                            Name of the target source.

    :other_sources:         (list)
                            sourcenames in list

    :c_target:              (tuple) (astropy.units.radian, astropy.units.radian)
                            (ra, dec) of the target source in astropy radian units

    :c_others:              (tuple) (astropy.units.radian, astropy.units.radian)
                            (ra, dec) of the other sources in astropy radian units

    :band:                  (string)
                            choose from S,C,X,U,K; or look at check_band() description.

    :flux_thres:            (float)     (Jy)
                            hard flux threshold for selecting bright calibrators and to check target source brightness
                            default: 0.150

    :min_flux:              (float)
                            minimum flux value threshold below which sources are considered low SNR/ value not found

    :caliblist_file:        (str)
                            path of the calibrator list file (e.g. VLBA calibrator list)

    :verbose:               (boolean)
                            prints useful calculation results.

    :flux_df:               (pandas.DataFrame)
                            see id_flux_for_sources()

    TODO: 
    [ ] make it work for non caliblist_file cases as well.
    [ ] make it work for nsources <3
    """
    
    
#     t = IdentifySource(fitsfile)
#     s_dict = t.identify_sources()
    
#     if not caliblist_file: caliblist_file = IdS.caliblist_file
    IdS = Sources(scanlist_seq, sourcenames)
    s = IdS.identify_sources()
#     sources_df      =   df(list(t.sourcenames.values()), index=list(t.sourcenames.keys()), columns=['source_name'])
    ps             = None
    allsources     = set()
    calib_from_seq = set()
    
    for k,ss in s.items():
        if ss:
            allsources.update(ss)
            if 'calibrator' in k:calib_from_seq.update(ss)
    
    calib_from_seq   = list(calib_from_seq).copy()
    calib_candidates = allsources.copy()
    
    if target_source in calib_candidates:
        calib_candidates.remove(target_source)
    alls             = list(allsources).copy()
    
    if len(allsources)>=2:
        s['science_target'] = [target_source]
        if (flux_df is None): 
            # HACK:        to get None values back from id_flux_for_sources using caliblist_file=True
            flux_df  = id_flux_for_sources(sourcenames, alls, caliblist_file, band) if caliblist_file else id_flux_for_sources(sourcenames, alls, True, band)
        flux_df = flux_df.sort_values(by=['flux'], ascending=False)
        print(flux_df)
#         print(flux_df)
        if IdS.isphref: # check whether science target is a phaseref calibrator
            if verbose: print('is phref')            
            if (target_source in calib_from_seq):
#                 if verbose: print('target is calib')
                if s['calibrators_phaseref']:
                    if (target_source in s['calibrators_phaseref']): 
                        if verbose: print('target was phref calib (from sequence)')
                        s['calibrators_phaseref'].remove(target_source)
                        
            else:
                ps, pid = find_phref_for_target_islowsnr(IdS, target_source, other_sources, c_target, c_others, caliblist_file, flux_df, flux_thres=flux_thres, sep_limit=20)

            msg=''
            if not ps: 
                
                if not IdS.isphref: 
                    msg='bright enough'
                else :
                    msg='no suitable calibrator pair found'
                    IdS.isphref = False
                
                s['calibrators_phaseref'] = None
            else:
                if not IdS.isphref:
                    """
                    since the isphref=True changes to False due to bright target
                    """
                    msg='bright enough'
                    s['calibrators_phaseref'] = None
                else:
                    s['calibrators_phaseref'] = [ps]
                    if ps in s['calibrators_instrphase']:
                        s['calibrators_instrphase'].remove(ps)
                    # s['phaseref_ff_science'] = False # for weak science target, setting true means, `the science targets are strong enough for a residual fringe-fit`
                    
            if verbose: print(f'target is in phref but {msg}')
        
    if target_source in s['calibrators_instrphase']:    s['calibrators_instrphase'].remove(target_source)
    
    id_calib_candidates = get_sources_id(sourcenames, calib_candidates)
    
    calib               = identify_calibrators(t=IdS, target=target_source, ps=ps, flux_thres=flux_thres, min_flux=min_flux, ncalib=ncalib, flux_df=flux_df , calib_ids=id_calib_candidates, hard_selection=hard_selection)
    
    s.update(calib)
    
    return s