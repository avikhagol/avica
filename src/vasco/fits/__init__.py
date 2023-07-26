from astropy.io import fits
from astropy.time import Time
import astropy.units as u
from astropy.table import Table, QTable
import numpy as np
from collections import Counter


def _listobs(fitsfile,cardname=None) :
    """
    read fits file cards, produce a CASA listobs() output

    Parameters:
    ----------

    :fitsfile: (str)
        - give path for the right fitsfile eg .uvfits, .fits, .idifits
    
    :cardname: (str)
        - give name of the HDUList Cards separeted by comma
    
    Return:
    ------

    Tabular format output from the fits data.

    Ex.
    ```bash
    $ vasco -l "SCAN,SOURCE,ANTENNA" -f test.fits > list.obs
    ```
    
    """
    carddata,cardnames=None,[]
    with fits.open(fitsfile) as hdul:
        
        for c in hdul:
            try:
                dateobs=c.header['DATE-OBS']
            except:
                pass

            if c.name in cardname:
                carddata=c.data
                print(Table(carddata))
            cardnames.append(c.name)
        if "SCAN" in cardname:
            uvtime=hdul['UV_DATA'].data.TIME
                                                        # SOURCE_ID name not consistent b/w VLBA nad EVN column of UV_DATA
            uvsidd=hdul['UV_DATA'].data
            sourced=hdul['SOURCE'].data
            for cname in uvsidd.columns:
                if 'SOURCE' in str(cname.name).upper(): 
                    uvsid_colname=str(cname.name)
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
                                                        # ID_NO. name not consistent b/w VLBA nad EVN column of SOURCE
            for cname in sourced.columns:
                if  str(cname.name).upper() in ['SOURCE_ID', 'ID_NO.', 'ID_NO']: 
                    
                    sourceid_colname=str(cname.name)
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
    
                
            
        # print(Table(carddata))
    print(f"other possible cards can be: {str(cardnames)}")

    
