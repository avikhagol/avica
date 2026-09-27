from typing import List
import numpy as np
from .core import split as fio_split
from .op import dict_baseline, get_hduname
from .io import FITSIDI, read_idi


class SplitData:
    def __init__(self, inpfits:str, outfits:str, verbose:bool=False):
        self.inpfits    =   inpfits
        self.outfits    =   outfits
        self.hduname    =   "UV_DATA"
        self.hdu_i      =   read_idi(inpfits)
        self.fo_out         =   FITSIDI(fitsfile=self.outfits)
        self.verbose    =   verbose

    def _open_forupdate(self):
        self.fo_out.open(mode="w")
        return self.fo_out.read()


    def mandatory_headers(self):                                    # TODO: 1. move to `.io``  2. enable .yaml input for the mandatory headers
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

    def split(self, source_ids:List=None, baseline_ids:List=None, freqids:List=None, expr:str=""):


        source_ids = [int(s) for s in source_ids] if source_ids else None

        if freqids is not None:
            if isinstance(freqids, int):
                freqids = [freqids]
            else:
                freqids = [int(s) for s in freqids]

        if baseline_ids and 'auto' in baseline_ids:
            baseline_ids        =   [str(basl) for basl in list(dict_baseline(fitsfile=self.inpfits).keys())]
            baseline_ids        =   ",".join(baseline_ids)

        baseline_ids = baseline_ids.split(',') if baseline_ids else None
        baseline_ids = [int(bl) for bl in baseline_ids] if baseline_ids else None


        fio_split(fitsfilepath=self.inpfits,
                        outfitsfilepath=self.outfits,
                        sids=source_ids, baseline_ids=baseline_ids, freqids=freqids,
                        source_col="SOURCE", baseline_col="BASELINE", frequency_col="FREQID",
                        expression=expr, verbose=False)
        if self.verbose : print("splitted successfully!")
        self.hdu_o      =   self._open_forupdate()
        self.update_header()

    def update_header(self):
        mh, hdrs_found = self.check_headers()
        # if len(mh)>len(hdrs_found):                                 # TODO: check strongly for the mandatory headers
        #     print(f"Warning! Not all mandatory headers were found : {set(mh).difference(set(hdrs_found))}")

        _, tbidxs   = get_hduname(self.hdu_i, [self.hduname])

        hdul_inp    =   read_idi(self.inpfits)
        hdul_out_readonly    =   read_idi(self.outfits)
        fo          =   FITSIDI(self.outfits)

        with fo.open("w") as fop:
            hdul_out = fop.read()
            for tbidx in tbidxs:
                tbinp_uv_data      =   hdul_inp[tbidx]
                header_inp          =   tbinp_uv_data.header
                header_outp_existing = hdul_out_readonly[tbidx].header
                prev_key            =   None

                for pos, key in enumerate(header_inp.keys()):
                    if key not in header_outp_existing:

                        dtype = header_inp.get_dtype(key)
                        value = header_inp[key]

                        if prev_key is None:
                            hdul_out[tbidx].add_key(key, value, position=pos, dtype=dtype)
                        else:
                            hdul_out[tbidx].add_key(key, value, after=prev_key, dtype=dtype)
                    elif key not in ['NAXIS2']:
                        hdul_out[tbidx].update_key(key, header_inp[key])

                    prev_key = key


                hdul_out[tbidx].update()
            fo.flush()

    def reindex(self, sel_freqids):
        if sel_freqids:
            reindex_freqid(fitsfilepath=self.outfits, sel_freqids=sel_freqids)

    def rm_tbl(self, tbl_names):
        _, _idxs = get_hduname(self.hdu_o, tbl_names)
        for tbidx in _idxs:
            del self.hdu_o[tbidx]
            self.hdu_o[tbidx].update()
        self.fo_out.flush()


def reindex_freqid(fitsfilepath, sel_freqids : List = []):
    """Uses sel_freqids to filter FREQID in FREQUENCY binary table and from the filtered values create a reindexed FREQID from 1,..N
        Similarly filters values in UV_DATA and fixes FREQID=1 on all that found

    Note:
        Dont use multiple sel_freqids, currently not supported

    Args:
        fitsfilepath
        sel_freqids (List, optional): selected FREQID values in list. Defaults to [].

    Raises:
        ValueError: if fitsfile and hdul not provided.
        ValueError: if sel_index has more than one value.

    Returns:
        fits.HDUList: will be closed if the fitsfile path is provided, else will return a flushed HDUL.
    """
    fo          =   FITSIDI(fitsfilepath)

    with fo.open("w") as fop:
        hdul = fop.read()
        for tb_name in ["FREQUENCY", "GAIN_CURVE", "SYSTEM_TEMPERATURE"]:
            if tb_name in hdul.names:
                tbld               =   np.array(hdul[tb_name])
                tbld               =   tbld[np.isin(tbld['FREQID'], sel_freqids)]

                # reindexed_id        =   [newid+1 for newid,_ in enumerate(np.unique(tbld['FREQID']))]
                tbld['FREQID']      =   1

                if len(np.unique(tbld['FREQID']))==1:
                    hdul[tb_name]                  =   tbld
                    naxis2                         =   np.shape(hdul[tb_name]['FREQID'])[0]
                    hdul[tb_name].update_key('NAXIS2', naxis2)
                else:
                    if len(np.unique(tbld['FREQID']))>1:
                        raise ValueError(f"Aborting reindex.. only single FREQID is supported! found : {tbld['FREQID']} ({tb_name})")
                    else:
                        if all(np.isin(hdul[tb_name]['FREQID'], [1])):
                            print(f"Skipped reindexing and keeping the original values for {tb_name}")
                        else:
                            raise RuntimeWarning(f"Skipped reindex.. chosen FREQID ({sel_freqids}) not found! ({tb_name})")
            hdul[tb_name].update()
        fop.flush()


    hdul        = read_idi(fitsfile=fitsfilepath)
    fo          = FITSIDI(fitsfilepath)
    _, tbidxs   = get_hduname(hdul, ['UV_DATA'])
    for tb in tbidxs:
        with fo.open("w") as fop:
            for hdu_chunk in fop.iter_read(fop.read().nrows):
                hdulmask = np.isin(np.array(hdu_chunk[tb]['FREQID']), sel_freqids)

                hdu_chunk[tb].filter_inplace(hdulmask)
                hdu_chunk[tb]['FREQID'] = 1
                hdu_chunk[tb].update_key('NAXIS2', sum(hdulmask))
                hdu_chunk[tb].update()

            fop.flush()


    return hdul