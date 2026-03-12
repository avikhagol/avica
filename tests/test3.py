#!/usr/bin/env python3
import sys
from astropy.io import fits
from astropy.time import Time
import fitsidiutil
import numpy as np

if __name__ == "__main__":
    argl = sys.argv[1:]
    sids = []

    if len(argl) < 1:
        print("Usage: test3.py <FITS file> [source IDs]")
        sys.exit(1)
    
    ff = str(argl[0])      
    if len(argl) == 2:
        sids = [int(sid) for sid in argl[1].split(',')]

    hdu = fits.open(ff)
    dateobs = hdu[0].header['DATE-OBS']

    dateobs_mjd = Time(dateobs, format='isot', scale='utc').mjd

    d = fitsidiutil.listobs(ff, sids)
    
    for row in d:
        time_start_mjd = Time(row.time_start + dateobs_mjd, format='mjd', scale='utc').isot
        time_end_mjd = Time(row.time_end + dateobs_mjd, format='mjd', scale='utc').isot
        inttime_rounded = np.round(np.array(row.inttime), 3)  
        print(time_start_mjd, "\t", time_end_mjd, "\t",
              row.source, "\t", row.nrows, "\t", inttime_rounded)
