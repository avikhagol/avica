from astropy.io import fits
from astropy.time import Time
import astropy.units as u
from astropy.table import Table, QTable
import numpy as np
from collections import Counter
import numpy as np
from scipy.spatial import distance

def _getcolname(data,colnames=['SOURCE']):
    _colname=None
    for cname in data.columns:
        for colname in colnames:
            if colname in str(cname.name).upper():
                _colname=str(cname.name)
            
    return _colname

def _gethduname(hdulist,hdunames=['SYSTEM_TEMPERATURE']):
    _hduname=None
    for hdu in hdulist:
        for hduname in hdunames:
            if str(hduname).upper() in str(hdu.name).upper():
                _hduname=str(hdu.name)
            
    return _hduname

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
                uvsid_colname=_getcolname(uvsidd,['SOURCE'])
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
            # except Exception as e:
            #     print(e)
    
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

def identify_targets(ispref,sdict,sourcename):
        targets={}
        # scanlist_arr,ind_sl=scanlist(hdul)
        # ispref,sdict=check_phaseref(scanlist_arr)
        # sourcename=sources(hdul)
        if ispref:
            st,pt,ct=_return_target(sdict)
            # targets['phref']=[sourcename[s] for s in list(sdict['phref'])]
            targets['science']=[sourcename[s] for s in st]
            targets['phase']=[sourcename[p] for p in pt]
            targets['other']=[sourcename[c] for c in ct]
            
        else:
            print('not phase referencing')
            targets['science']=[sourcename[s] for s in list(sdict['other'].keys())]
        
        return targets

def find_refant(fitsfile):
    """takes fitsfile as input and returns the reference antenna which is good geometrically, observation length, and by SEFD
    prints table with columns [ANNAME,STD_TSYS,nRows,Distance] sorted by best reference antenna; returns a dictionary of the same table.

    Returns:
    -----

    (dict)
    sorted dictionary in order of best antenna.

    key         {key        : param}

    ANNAME      {antenna_id : antenna_name}
    STD_TSYS    {antenna_id : standard_deviation_of_TSYS}
    nRows       {antenna_id : no_of_datapoints}
    Distance    {antenna_id : median_distance}

    """
    f=fits.open(fitsfile)
    hduname=_gethduname(f, ['SYSTEM_TEMPERATURE'])
    # hduname='SYSTEM_TEMPERATURE'
    if hduname:
        tsys1=f[hduname].data.TSYS_1
        tsys2=None
        if 'TSYS_2' in f[hduname].columns.names:tsys2=f[hduname].data.TSYS_2
        antenna=f[hduname].data.ANTENNA_NO
        antenna_dict=dict(zip(f['ANTENNA'].data['ANTENNA_NO'],(f['ANTENNA'].data['ANNAME'])))
        xyz,anname_geom=f['ARRAY_GEOMETRY'].data.STABXYZ, f['ARRAY_GEOMETRY'].data.ANNAME

        anlist,tsys1_std,tsys2_std,ancountlist,missing_antennav=[],[],[],[],[]
        ancount=Counter(antenna)
        med_d=[]
        for ant in antenna_dict.keys():

            s_ind=np.where(antenna==ant) # select each antenna for all sources
            if len(s_ind[0]):
                anlist.append(antenna_dict[ant])    
                tsys1_std.append(np.median((np.std(tsys1[s_ind], axis=0))))
                if tsys2 is not None: tsys2_std.append(np.median((np.std(tsys2[s_ind], axis=0))))
                ancountlist.append(ancount[ant])
            else:
                missing_antennav.append(antenna_dict[ant])
                
            
            d=[]
            refcoord=xyz[np.where(anname_geom==antenna_dict[ant])][0]
            # xyz - np.min(xyz, axis=0)
            for i,v in enumerate(xyz):
                d.append(distance.minkowski(refcoord,v)*.0001) # distance of all from one refant
            med_d.append((antenna_dict[ant],np.median(d)))                    # median distance of all ants for one refant
    #     med_dlist=list(zip(*med_d))[1]
        ant_with_d=dict(med_d)
                
        if len(tsys2_std) == len(tsys1_std):
            tsys_std=np.median([tsys1_std,tsys2_std],axis=0)

        else:
            tsys_std=tsys1_std
            
            

        t=QTable([anlist,tsys_std,ancountlist], names=('ANNAME', 'STD_TSYS','nRows'), meta={'name':'ANTENNA TSYS Variance'})
        t['Distance']=[ant_with_d[ant] for ant in t['ANNAME']]
        for ant in missing_antennav: t.add_row([ant, float('nan'), 0,ant_with_d[ant]])
        tp=t.to_pandas()
        tp.index += 1
        med_tp=tp['nRows'].median()
        for sigma_cut in [1.5,1.4,1.3,1.2,1.1,1.0,0.9]:
            med_above=tp['nRows']>=med_tp*sigma_cut
            tp_cut=tp[med_above]
            if len(tp_cut)>=4:break
        tp_res=tp_cut.sort_values(by=['STD_TSYS', 'Distance'], ascending=[True, True])
        print(tp_res.to_string(index=False))
        return tp_res.to_dict()
    else:
        print('missing TSYS info!\n')
    

class Targets:
    def __init__(self,fitsfile) -> None:
        self.fitsfile=fitsfile
    
        # helper and output variables
        self.hdul=fits.open(fitsfile)
        self.scanlist_arr,ind_sl=scanlist(self.hdul)
        self.sourcename=sources(self.hdul)
        
        self.check_phaseref=check_phaseref(self.scanlist_arr)
        self.identify_target=identify_targets(self.check_phaseref[0],self.check_phaseref[1],self.sourcename)
        # self.targets = identify_targets(self.fitsfile)
    
    
    

# fitsfile='/data/avi/d/BB240GD/BB240/BB240GD/VLBA_BB240GD_bb240gd_BIN0_SRC0_0_110927T171838.idifits'
# # uv_data=hdul['UV_DATA'].data
# # sa,ind_sa= scanlist(uv_data)
# # isph,sdict=_check_phaseref(sa)
# # st,pt,ct=_return_target(sdict)
# # print(st,pt,ct)
# print(identify_targets(fitsfile))