from . import listobs as listobs_fits
from fitsio import FITS
from astropy.time import Time, TimeDelta
import numpy as np
from pandas import DataFrame as df


def get_colnames(hdu, cols):
    matching_cols = []
    found_cols = hdu.get_colnames()
    
    for col in cols:
        matching_cols += [colname for colname in found_cols if col in colname]

    return matching_cols


class ListObs:
    def __init__(self, fitsfilepath, sids=None, time_scale_data='tai', scangap=15, scale_dateobs='utc'):
        self.fitsfilepath                               =   fitsfilepath
        self.time_scale_data                            =   time_scale_data
        self.scale_dateobs                              =   scale_dateobs
        self.scangap                                    =   scangap
    
        self.scanlist                                   =   []
        
        
        
        
        self.sids                                       =   [int(s) for s in sids] if sids else None
        
        
        
        self.df_listobs                                 =   self.fetch()
    
    
        
    
    
    def fetch(self,):
        rowd = listobs_fits(fitsfilepath=self.fitsfilepath, sids=self.sids)
    
        fo              =   FITS(self.fitsfilepath, mode='r')
        dateobs         =   fo[0].read_header()['DATE-OBS']
        dateobs         =   Time(dateobs, format='isot', scale=self.scale_dateobs)
        shdu            =   fo.movnam_hdu('SOURCE')
        hdu             =   fo[shdu-1]
        sid_colname     =   get_colnames(hdu, ['ID_NO', 'SOURCE_ID'])[0]
        
        sids = [int(sid) for sid in hdu[sid_colname].read()]
        stargets = [str(src) for src in hdu['SOURCE'].read()]
        dic_sources = dict(zip(sids,stargets))
        
        self.dic_sources    =   dic_sources
        fo.close()
    
        prev_end_mjd = Time(0, format='mjd', scale=self.time_scale_data)
    
        scan_n = 0
        dict_listobs = {}
    
        for row in rowd:
            time_start_mjd = Time(row.time_start + dateobs.mjd, format='mjd', scale='tai')
            time_end_mjd = Time(row.time_end + dateobs.mjd, format='mjd', scale='tai')

            if (time_end_mjd - prev_end_mjd).sec>=self.scangap:
                
                time_start_isot, time_end_isot = time_start_mjd.isot, time_end_mjd.isot
                
                inttime_rounded = np.round(np.array(row.inttime), 3)

                # print(time_start_isot, "\t", time_end_isot, "\t",
                #     row.source, "\t", row.nrows, "\t", inttime_rounded)
                
                dict_listobs[scan_n] = {'start_time': time_start_isot, 'end_time': time_end_isot, 'sid': row.source, 'nrows': row.nrows, 'inttime': list(inttime_rounded)}
                self.scanlist.append(row.source)
                scan_n      += 1
            prev_end_mjd = time_end_mjd
    
        self.dict_listobs       =   dict_listobs
        df_listobs = df.from_dict(dict_listobs, orient='index')
    
        df_listobs['source'] = df_listobs['sid'].map(dic_sources)
        df_listobs.index += 1
    
        df_listobs.insert(3, 'source', df_listobs.pop('source'))
        return df_listobs
        
        