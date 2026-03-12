from pathlib import Path

from casacore.tables import table, taql
# from casatools import table

import numpy as np
def check_band(freq, bands=None):
        """
        Input
        ---

        freq            (float)
                        value of the reference fequency in GHz

        bands           (dict)
                        dictionary of bands containing numpy array of limiting values of range of the band.

        Return
        ---
        
        band closest to S,C,X,U,K,Q,W of observation

        https://science.nrao.edu/facilities/vlba/docs/manuals/oss/bands-perf
        """   
        band = freq
        if not bands:
            bands = {
            'S' : np.array([2.0, 2.6]),
            'C' : np.array([3.5, 6.4]),
            'X' : np.array([7.401, 8.8]),
            'U' : np.array([11.8, 15.7]),
            'K' : np.array([20.0, 25.0]),
            'Q' : np.array([40.0, 46.0]),
            'W' : np.array([80.0, 90.0]),
        }
        compare = 999.0
        for k,v in bands.items():
            val = (np.abs(v-freq)).min()

            if compare > val: 
                band = k
                compare = val
        return band
    
def get_unflagged_data(tb, fid, dscids, above_weightzero=True, autocorr=False):
    query = f"SELECT * FROM $tb WHERE all(not all(FLAG) and FIELD_ID==$fid and (DATA_DESC_ID in $dscids)"
    if above_weightzero:
        query += " and WEIGHT>0"
    if not autocorr:
        query += " and ANTENNA1!=ANTENNA2"

    query += ")"
    d = taql(query)
    return d


def get_summary_fromd(d):
    """
    
    """
    dic_target_summary = {}
    
    baselines = taql(f"SELECT ANTENNA1, ANTENNA2 FROM $d GROUPBY ANTENNA1, ANTENNA2")
    nbaseline = baselines.nrows()
    
    tints = taql(f"SELECT TIME FROM $d GROUPBY TIME")
    ntint = tints.nrows()
    
    
    scans = taql(f"SELECT SCAN_NUMBER FROM $d GROUPBY SCAN_NUMBER").getcol('SCAN_NUMBER')
    
    obslen=0
    scanlens = []
    for scan in scans:
        exptime_scantints = taql(f"SELECT EXPOSURE,TIME FROM $d WHERE SCAN_NUMBER={scan} GROUPBY TIME")
        scan_tints = exptime_scantints.getcol('TIME')
        expos = exptime_scantints.getcol('EXPOSURE')
    
        scanlen = np.round(scan_tints.max()-scan_tints.min(),2)
        expos_min = np.round(expos.min(),3)
        expos_max = np.round(expos.max(),3)
        obslen += scanlen
        scanlens.append(scanlen)
    scanlen_max = max(scanlens)
    scanlen_min = min(scanlens)
    
    dic_target_summary={
                "nbaseline":nbaseline, "ntint":ntint,
                "expos_max":expos_max, "expos_min":expos_min,
                "obslen":obslen,
                "scan_min":scanlen_min,
                "scan_max":scanlen_max,
                
            }
    return dic_target_summary

def get_vis_summary(vis, target,wo_nchan=True, **kwargs):
    """

    :wo_nchan:    (bool) (default=True)
                  get nvis and flagged data without nchan considered i.e counting unflagged data in nchan is ignored.
    """

    dic_summary = {}
    tb = table(vis)
    tb_field = table(tb.getkeyword('FIELD'))
    spw_table = table(tb.getkeyword('SPECTRAL_WINDOW'))
    data_dsc_tbl = table(tb.getkeyword('DATA_DESCRIPTION'))
    
    fid = list(tb_field.getcol('NAME')).index(target)
    reffreqs = spw_table.getcol('REF_FREQUENCY')
    spwids_indatadsc = data_dsc_tbl.getcol('SPECTRAL_WINDOW_ID')
    
    dic_band_dscid = {}
    for dscid, spwid in enumerate(spwids_indatadsc):
        reffreq = reffreqs[spwid]
        band = check_band(reffreq/1e9)
    
        if band in dic_band_dscid:
            dic_band_dscid[band].append(dscid)
        else:
            dic_band_dscid[band]  = [dscid]
    
        chwidth = (spw_table.getcol('CHAN_WIDTH')[spwid]/1e03).min() # FIXME: correct way is to use from dictionary 
    for band in dic_band_dscid:
        # print(band)
        dscids = dic_band_dscid[band]
        d = get_unflagged_data(tb, fid, dscids, **kwargs)
        
        flags = d.getcol('FLAG')
        flagged = np.count_nonzero(flags)
        # print(np.shape(flags))
        nrow,nchan,ncorr = np.shape(flags)
        nvis = nrow*nchan*ncorr
        unflagged_nvis = nvis - flagged
        nspw = len(dscids)

        perc_flagged = (flagged/nvis)*100       # Note nvis includes flagged datapoints too
        dic_summary[band] = get_summary_fromd(d)
        
        dic_summary[band]['chwidth'] = chwidth
        dic_summary[band].update({"tot_nvis":nvis,
        "nvis":unflagged_nvis,"nspw":nspw,
        "nchan" : nchan,
        "apparant_sampling": unflagged_nvis/nspw/nchan/ncorr/dic_summary[band]['nbaseline']/dic_summary[band]['ntint'],
        "perc_flagged" : perc_flagged,
                                 })
    tb.close()
    return dic_summary
