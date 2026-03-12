import numpy as np
from astropy.io import fits

class IdiHDU(fits.PrimaryHDU):
    @classmethod
    def match_header(cls, header):
        try:
            keyword = header.cards[0].keyword
        except:
            keyword = header.ascard[0].key
            pass
        
        return (keyword == 'SIMPLE' and 'GROUPS' in header and
            header['GROUPS'] == True and 'NAXIS' in header and header['NAXIS'] == 0)

fits.register_hdu(IdiHDU)

def dict_baseline(fitsfile=None,hdul=None):
    """
    for each baseline stores tuple of (distance,label,(id_an1,id_an2))
    """
    from scipy.spatial import distance
    if hdul is None:
        if fitsfile is None: raise ValueError("missing fits file path")
        else:hdul=fits.open(fitsfile)
    xyz,annames=hdul['ARRAY_GEOMETRY'].data.STABXYZ, hdul['ARRAY_GEOMETRY'].data.ANNAME

    dict_baseline={}
    
    for i,an1 in enumerate(annames):
        for j,an2 in enumerate(annames):
                d=distance.euclidean(xyz[i],xyz[j])*.001
                baseline_label=f"{an1}-{an2}"
                baseline_id=(i+1)*256+(j+1)
                dict_baseline[baseline_id]=(d,baseline_label,(i+1,j+1))
    return dict_baseline