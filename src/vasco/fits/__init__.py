from astropy.io import fits
from astropy.time import Time
import astropy.units as u
from astropy.table import Table, QTable
import numpy as np
from collections import Counter
import numpy as np


def __getcolname(data,colnames=['SOURCE']):
    _colname=None
    for cname in data.columns:
        for colname in colnames:
            if colname in str(cname.name).upper():
                _colname=str(cname.name)
            
    return _colname

def _listobs(fitsfile,hduname=None) :
    """
    read fits file hdus, produce a CASA listobs() output

    Parameters:
    ----------

    :fitsfile: (str)
        - give path for the right fitsfile eg .uvfits, .fits, .idifits
    
    :hduname: (str)
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
            if c.name in hduname:
                hdudata=c.data
                print(Table(hdudata))
            hdunames.append(c.name)
        if "SCAN" in hduname:
            
                uvtime=hdul['UV_DATA'].data.TIME
                uvsid_colname='SOURCE'                       # SOURCE_ID name not consistent b/w VLBA nad EVN column of UV_DATA
                uvsidd=hdul['UV_DATA'].data
                sourced=hdul['SOURCE'].data
                uvsid_colname=__getcolname(uvsidd,['SOURCE'])
                # for cname in uvsidd.columns:
                #     if 'SOURCE' in str(cname.name).upper(): 
                #         uvsid_colname=str(cname.name)
                uvsid=uvsidd[uvsid_colname]

                scanmjd=Time(uvtime, format='mjd', scale='utc')
                zerotime=Time(dateobs, format='isot',scale='utc')
                scantime=zerotime.mjd+scanmjd
                integrationTime=Counter(hdul['UV_DATA'].data.INTTIM).keys()
                
                sourcename={}
                ind_inst=np.where((np.diff(uvsid)!=0)==True)
                ind_inst=np.append(ind_inst,-1)
                scanlist=uvsid[ind_inst]
                totalrows=len(uvsid)
                sourceid_colname=__getcolname(sourced,['SOURCE_ID', 'ID_NO.', 'ID_NO'])        
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
            # except Exception as e:
            #     print(e)
    
    print(f"Possible hdus can be: {str(hdunames)}")

def sources(hdul):
    sourced=hdul['SOURCE'].data
    sourcename={}
    sourceid_colname=__getcolname(sourced,['SOURCE_ID', 'ID_NO.', 'ID_NO'])
    for i,sid in enumerate(sourced[sourceid_colname]):
            sourcename[sid]=hdul['SOURCE'].data.SOURCE[i]
    return sourcename




def scanlist(uv_data):
    """
    return array of scanlist and index of the scan in the sequence of data from UV_DATA column
    """
    uvsid_colname=__getcolname(uv_data,['SOURCE'])
    uvsid=uv_data[uvsid_colname]
    ind_inst=np.where((np.diff(uvsid)!=0)==True)
    ind_inst=np.append(ind_inst,-1)
    scanlist_arr=uvsid[ind_inst]
    return scanlist_arr, ind_inst

def __sel_ind(data):
    ind=np.where((np.diff(data)!=0)==True)
    ind=np.append(ind,-1)
    grouped_data=data[ind]
    return grouped_data

def __check_phaseref(scanlist_arr):
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

def __return_target(sdict):
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

def identify_targets(fitsfile):
    with fits.open(fitsfile, 'readonly') as hdul:
        uv_data=hdul['UV_DATA'].data
        sourcename=sources(hdul)
        sl_arr,ind_sl=scanlist(uv_data)
        ispref,sdict=__check_phaseref(sl_arr)
        if ispref:
            st,pt,ct=__return_target(sdict)
            print(f"science:{[sourcename[s] for s in st]}\n")
            print(f"phase:{[sourcename[p] for p in pt]}\n")
            print(f"brightcal:{[sourcename[c] for c in ct]}\n")
            # return {'science':sourcename[st],'phase':sourcename[pt],'brightcal':sourcename[ct]}
        else:
            print('not phase referencing')
            print(f"science:{[sourcename[s] for s in list(sdict['other'].keys())]}\n")

# hdul=fits.open('/data/avi/d/BB240GD/BB240/BB240GD/VLBA_BB240GD_bb240gd_BIN0_SRC0_0_110927T171838.idifits')
# uv_data=hdul['UV_DATA'].data
# sa,ind_sa= scanlist(uv_data)
# isph,sdict=__check_phaseref(sa)
# st,pt,ct=__return_target(sdict)
# print(st,pt,ct)
