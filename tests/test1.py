
import fitsidiutil
from astropy.time import Time
from astropy.io import fits

import fitsidiutil
ff = 'test.fits'

hdu = fits.open(ff)
dateobs = hdu[0].header['DATE-OBS']

dateobs_mjd = Time(dateobs, format='isot', scale='utc').mjd
sids = []
d = fitsidiutil.listobs(ff, sids)

for row in d:
    time_start_mjd = Time(row.time_start + dateobs_mjd, format='mjd', scale='utc').isot
    time_end_mjd = Time(row.time_end + dateobs_mjd, format='mjd', scale='utc').isot
    inttime_rounded = np.round(np.array(row.inttime), 3)  
    print(time_start_mjd, "\t", time_end_mjd, "\t",
            row.source, "\t", row.nrows, "\t", inttime_rounded)