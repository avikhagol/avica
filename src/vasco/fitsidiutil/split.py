from astropy.io import fits
from typing import List, Any
import numpy as np
from vasco.fits import _gethduname
from fitsio import FITS
class SPLIT:
    def __init__(self, inpfits, outfits):
        self.inpfits    =   inpfits
        self.outfits    =   outfits
        self.hduname    =   "UV_DATA"
        self.hdu_i      =   fits.open(inpfits)
        self.hdu_o      =   fits.open(outfits, mode='update')
        
    def mandatory_headers(self):                                    # TODO: enable .yaml input for the mandatory headers
        __header_list  = ['EXTNAME', 'TABREV', 'NMATRIX', 'MAXIS', 
                          'MAXISm', 'CTYPEm', 'CDELTm', 'CRPIXm', 'CRVALm', 'TMATXn',
                          'NO_STKD', 'STK_1', 'NO_BAND', 'NO_CHAN', 'REF_FREQ', 'CHAN_BW']
        return __header_list
    
    def special_headers(self):
        __header_list = ['EQUINOX', 'WEIGHTYP']
        return __header_list
        
    def optional_headers(self):
        __header_list = ['DATE-OBS', 'TELESCOP', 'OBSERVER', 'VIS_CAL', 'SORT']
        return __header_list
    
    def check_headers(self):
        hdr_found   =   set()
        mh          =   self.mandatory_headers()
        for headerkey in mh:
            for headervalue in self.hdu_i[self.hduname].header:
                if headerkey.replace('m', '') in headervalue:
                    hdr_found.add(headerkey)
                if headerkey.replace('n', '') in headervalue:
                    hdr_found.add(headerkey)
        return mh, hdr_found
    
    def update_header(self):
        mh, hdrs_found = self.check_headers()
        if len(mh)>len(hdrs_found):                                 # TODO: check strongly for the mandatory headers
            print("Warning! Not all mandatory headers were found.")
        
        _, tbidxs   = _gethduname(self.hdu_i, [self.hduname])
        
        fits_inp = FITS(self.inpfits)
        for hdu in fits_inp:
            if hdu.get_extname() == self.hduname:
                tb          =   hdu.get_extnum()
                header_inp  =   hdu.read_header()

                with FITS(self.outfits, mode='rw') as fnew:
                    for key in header_inp.keys():
                        if not key in ['NAXIS2']:
                            fnew[tb].write_key(key, header_inp[key])
                        
                    
        # for tb in tbidxs:
        #     print(f"....processing header {tb}")
            
        #     naxis2                          = self.hdu_o[tb].header['NAXIS2']
        #     self.hdu_o[tb].header           = self.hdu_i[tb].header.copy()
            
        #     self.hdu_o[tb].header['NAXIS2'] = naxis2
        #     self.hdu_o.flush()
        #     print(f"MAXIS1, inp=>{self.hdu_i[tb].header['MAXIS1']}, oup=> {self.hdu_o[tb].header['MAXIS1']}")
    
    def reindex(self, sel_freqids):
        if sel_freqids:
            reindex_freqid(hdul=self.hdu_o, sel_freqids=sel_freqids)
            
    def rm_tbl(self, tbl_names):
        for tbl_name in tbl_names:
            del self.hdu_o[tbl_name]
            
    
def reindex_freqid(fitsfile : str = None, hdul: fits.HDUList = None, sel_freqids : List = []):
    """Uses sel_freqids to filter FREQID in FREQUENCY binary table and from the filtered values create a reindexed FREQID from 1,..N
        Similarly filters values in UV_DATA and fixes FREQID=1 on all that found
        Note: Dont use multiple sel_freqids, currently not supported

    Args:
        fitsfile (str, optional): path of the fitsfile. Defaults to None.
        hdul (fits.HDUList, optional): fits HDUL. Defaults to None.
        sel_freqids (List, optional): selected FREQID values in list. Defaults to [].

    Raises:
        ValueError: if fitsfile and hdul not provided.
        ValueError: if sel_index has more than one value.

    Returns:
        fits.HDUList: will be closed if the fitsfile path is provided, else will return a flushed HDUL.
    """
    
    if hdul is None:
        if fitsfile is None: raise ValueError("missing fits file path")
        else: hdul=fits.open(fitsfile, mode="update")
        
    
    for tb_name in ["FREQUENCY", "GAIN_CURVE", "SYSTEM_TEMPERATURE"]:   
        if tb_name in hdul: 
            tbld               =   hdul[tb_name].data.copy()
            tbld               =   tbld[np.isin(tbld['FREQID'], sel_freqids)]
            
            # reindexed_id        =   [newid+1 for newid,_ in enumerate(np.unique(tbld['FREQID']))]
            tbld['FREQID']      =   1
            
            if len(np.unique(tbld['FREQID']))==1:
                hdul[tb_name].data                  =   tbld
                hdul[tb_name].header['NAXIS2']      =   hdul[tb_name].data['FREQID'].shape[0]
            else:
                if len(np.unique(tbld['FREQID']))>1:
                    raise ValueError(f"Aborting reindex.. only single FREQID is supported! found : {tbld['FREQID']} ({tb_name})")
                else:
                    if all(np.isin(hdul[tb_name].data['FREQID'], [1])):
                        print(f"Skipped reindexing and keeping the original values for {tb_name}")
                    else:
                        raise RuntimeWarning(f"Skipped reindex.. chosen FREQID ({sel_freqids}) not found! ({tb_name})")
                
                    
    _, tbidxs   = _gethduname(hdul, ['UV_DATA'])

    for tb in tbidxs:
        
        hdulmask                     =   np.isin(hdul[tb].data['FREQID'], sel_freqids)
        hdul[tb].data                =   hdul[tb].data[hdulmask]
        hdul[tb].data['FREQID']      =   1
        hdul[tb].header['NAXIS2']    =   sum(hdulmask)

        
    
    
    hdul.flush()
    
    if fitsfile is not None:
        hdul.close()
        
    return hdul