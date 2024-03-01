from astropy.io import fits
from astropy.time import Time
import astropy.units as u
from astropy.table import Table, QTable
import numpy as np
from collections import Counter
import numpy as np
import itertools
from pathlib import Path

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

                scanmjd=Time(uvtime, format='mjd', scale='utc')
                zerotime=Time(dateobs, format='isot',scale='utc')
                scantime=zerotime.mjd+scanmjd
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

def sources(hdul):
    sourced=hdul['SOURCE'].data
    sourcename={}
    sourceid_colname=_getcolname(sourced,['SOURCE_ID', 'ID_NO.', 'ID_NO'])
    for i,sid in enumerate(sourced[sourceid_colname]):
            sourcename[sid]=hdul['SOURCE'].data.SOURCE[i]
    return sourcename


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
            compare_val.append(np.std(sdict['phref'][s])/np.mean(sdict['phref'][s])*100) #coeff of variab check for indices
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
                # sdict['phref']['nbr']=
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

def find_first_occurrence(arr, sequence):
    # Convert sequence to set for faster membership testing
    sequence_set = set(sequence)
    sequence_length = len(sequence_set)

    # Find occurrences of the sequence
    occurrences = [i for i in range(len(arr) - sequence_length + 1) if set(arr[i:i+sequence_length]) == sequence_set]

    if len(occurrences)>1:
        # Find the index of the first occurrence
        first_occurrence_index = occurrences[0]
        return first_occurrence_index
    else:
        # Return None if no occurrence is found
        return None
    
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
    
    science_target=[]
    calibrators_phaseref=[]
    _, dic = t.check_phaseref
#     seq_s,idx_s=find_source_seq(t)
    sd = set(dic['phref'].keys())
    sourcenames = sources(t.hdul)
    seq_s = itertools.combinations(sd,2)
    for seq in seq_s:
        idx_f_o_cl= find_first_occurrence(source_list,seq)
        
        if idx_f_o_cl is not None: 
            sid = source_list[idx_f_o_cl]
            st = seq[0] if sid == seq[1] else seq[1]
            if sid not in science_target:
                calibrators_phaseref.extend([sid])
            if st not in calibrators_phaseref:
                science_target.extend([st])
#             print(sid,st,s['calibrators_phaseref'])
    phrefs = list(set(dic['other'].keys()))
    if len(phrefs):
        s['calibrators_instrphase'] = [sourcenames[s] for s in phrefs]
        s['calibrators_bandpass'] = s['calibrators_instrphase']
    if len(science_target):
        s['science_target'] = [sourcenames[s] for s in list(set(science_target))]
    if len(calibrators_phaseref):
        s['calibrators_phaseref'] = [sourcenames[s] for s in list(set(calibrators_phaseref))]
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

def identify_refant(fitsfile, n=4, **kwargs):
    """
    returns dataframe of first "n" best refants has id as the index
    TODO: multiply some weights to central antennas.
    """
    refants = find_refant(fitsfile, **kwargs)[:n].ANNAME
    return refants

def find_refant(fitsfile, verbose=True, return_onmissing=False):
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
    hduname,lids=_gethduname(f, ['SYSTEM_TEMPERATURE'])
    
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
        
        for ant in missing_antennav: t.add_row([ant, float('nan'), 0,ant_with_d[ant]])
        
        tp=t.to_pandas()
        tp.index += 1
    
        tp_res=tp
        max_nrows= tp_res['nRows'].max()
        max_distance = tp_res['Distance'].max()
        max_std_tsys = tp_res['STD_TSYS'].median()

        tsys=tp_res['STD_TSYS']/max_std_tsys
        nrows= tp_res['nRows']/max_nrows
        distance = tp_res['Distance']/max_distance

        res=tsys*nrows*distance
        res=1-(res/res.max())
        
        tp_res.insert(4,'c', res)
        tp_res = tp_res.sort_values(by='c', ascending=[False])
        if verbose: print(tp_res.to_string(index=False))
        return tp_res
    else:
        if verbose: print('missing TSYS info!\n')
        if return_onmissing: return False

def split(hdul, sids, outfits):
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

class Targets:
    def __init__(self,fitsfile) -> None:
        self.fitsfile=fitsfile
    
        # helper and output variables
        self.hdul=fits.open(fitsfile)
        self.scanlist_arr,ind_sl=scanlist(self.hdul)
        self.sourcename=sources(self.hdul)
        
        self.check_phaseref=check_phaseref(self.scanlist_arr)
        # self.identify_sources = identify_sources()
        # self.identify_target=identify_targets(self.check_phaseref[0],self.check_phaseref[1],self.sourcename)