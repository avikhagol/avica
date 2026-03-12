from casatools import logsink

vascolog=logsink('vasco.casa_log')
vascolog.setlogfile='vasco.casa_log'
vascolog.setglobal(True)

from casatools import table
from casatasks import fringefit, listobs, flagdata, mstransform
from casatools import table
from casatools import msmetadata
import sys
from pathlib import Path
from datetime import datetime
from pandas import DataFrame as df, concat as pdconc
from astropy.time import Time, TimeDelta
from astropy.coordinates import SkyCoord
from astropy import units as u
import json
import numpy as np
from pandas import DataFrame as df
from typing import List

import glob

from vasco.util import read_inputfile, latest_file, save_metafile, read_metafile
from vasco.sources import check_band, identify_sources_fromtarget, choose_calib_for_snr_rating
from scipy.spatial import distance

from vasco import c
from vasco.diag import get_avg_amp_phase, pl_diag, get_labels_dbscan, calcscatter_fromlabels_df

from vasco.ms.fringefit import start_mpi
import traceback

msmd=msmetadata()
tb = table()

SNR_THRES = 7.0



def read_df_vis(vis:str, corr: List = [], spw: List =[], dcol:str='DATA', sel_row:List=[]):
    import polars as pl
    df_list = []
    
    [field_name] = get_tb_data(f"{vis}/FIELD", axs=['NAME'])
    [antenna_name] = get_tb_data(f"{vis}/ANTENNA", axs=['NAME'])
    [data_desc_spw] = get_tb_data(f"{vis}/DATA_DESCRIPTION", axs=['SPECTRAL_WINDOW_ID'])
    
    tb_data = get_tb_data(
                        vis, 
                        axs=['TIME','EXPOSURE','SCAN_NUMBER', 'FIELD_ID', dcol, 
                             'SIGMA','WEIGHT','ANTENNA1','ANTENNA2','UVW','FLAG', 'DATA_DESC_ID']
                        )

    time, expos, sid, fid, data, sigma, weight, an1, an2, uvw, flag, data_desc_id = tb_data
    ncorr, nspw, nrow = data.shape
    
    if len(corr)<1:
        corr = [0] if ncorr==1 else range(0, ncorr)
    if len(spw)<1:
        spw = [0] if nspw==1 else range(0, nspw)

    for sel_corr in corr:
        for sel_chan in spw:
            df_vis_single = read_df_vis_single(vis, tb_data , field_name, antenna_name, data_desc_spw, sel_corr, sel_chan, sel_row)
            df_vis_single = df_vis_single.with_columns(pl.lit(sel_corr).alias("corr"), pl.lit(sel_chan).alias("chan"))
            df_list.append(df_vis_single) 
            
    df_vis = pl.concat(df_list, how="vertical")

    return df_vis
    
def read_df_vis_single(vis:str, tb_data, field_name, antenna_name, data_desc_spw, sel_corr:int=0, sel_chan:int=0, sel_row:List=[]):
    """
    assumes dimensions:
    (corr, chan, row)

    """
    import polars as pl
    time, expos, sid, fid, data, sigma, weight, an1, an2, uvw, flag, data_desc_id = tb_data

    ncorr, nspw, nrow = data.shape
    if not sel_row: sel_row = (0, nrow)
    sel_data = data[sel_corr][sel_chan][sel_row[0]:sel_row[1]]
    sel_real = sel_data.real
    sel_imag = sel_data.imag
    sel_flag = flag[sel_corr][sel_chan][sel_row[0]:sel_row[1]]

    u,v,w    = uvw[0][sel_row[0]:sel_row[1]]   ,uvw[1][sel_row[0]:sel_row[1]]   ,uvw[2][sel_row[0]:sel_row[1]]   
    uvdist   = np.sqrt(u*u + v*v)
    sel_sigma= sigma[sel_corr][sel_row[0]:sel_row[1]]
    sel_weight = weight[sel_corr][sel_row[0]:sel_row[1]]
            
    data_series = [
        pl.Series("time", time, dtype=pl.Float64),
        pl.Series("uvdist", uvdist, dtype=pl.Float64),
        pl.Series("expos", expos, dtype=pl.Float32),
        pl.Series("fid", fid, dtype=pl.Int64),
        pl.Series("sid", sid, dtype=pl.Int64),
        pl.Series("data_desc_id", data_desc_id, dtype=pl.Int64),
        pl.Series("an1", an1, dtype=pl.Int64),
        pl.Series("an2", an2, dtype=pl.Int64),
        pl.Series("amp", np.abs(sel_data), dtype=pl.Float64),
        pl.Series("phase", np.angle(sel_data, deg=True), dtype=pl.Float64),
        pl.Series("real", sel_real, dtype=pl.Float64),
        pl.Series("imag", sel_imag, dtype=pl.Float64),
        pl.Series("flag", sel_flag, dtype=pl.Boolean),
        pl.Series("u", u, dtype=pl.Float64),
        pl.Series("v", v, dtype=pl.Float64),
        pl.Series("w", w, dtype=pl.Float64),
        pl.Series("sigma", sel_sigma, dtype=pl.Float64),
        pl.Series("weight", sel_weight, dtype=pl.Float64),
    ]

    df_vis = pl.DataFrame(data_series)
    
    df_field_map = (pl.DataFrame([{"fid": fid, "field": name}for fid, name in enumerate(field_name)]) )
    df_vis = df_vis.join(df_field_map, on="fid", how="inner")
    
    df_an_map = (pl.DataFrame([{"an1": an1, "an1_name": name}for an1, name in enumerate(antenna_name)]) )
    df_vis = df_vis.join(df_an_map, on="an1", how="inner")
    
    df_an_map = (pl.DataFrame([{"an2": an1, "an2_name": name}for an1, name in enumerate(antenna_name)]) )
    df_vis = df_vis.join(df_an_map, on="an2", how="inner")

    df_spw_map = (pl.DataFrame([{"data_desc_id": data_desc_id, "spw": spw}for data_desc_id, spw in enumerate(data_desc_spw)]) )
    df_vis = df_vis.join(df_spw_map, on="data_desc_id", how="inner")
    
    return df_vis


def get_dic_an(vis, spw_col):

    tban, tbfeed, tbdesc, tbvis = table(), table(), table(), table()
    
    tbvis.open(vis)
    tbdesc.open(f"{vis}/DATA_DESCRIPTION")
    tbfeed.open(f"{vis}/FEED")
    tban.open(f"{vis}/ANTENNA")
    
    anname = tban.getcol('NAME')

    if 'ANTENNA_ID' not in tban.colnames():
        anid = list(range(len(anname)))
    else:
        anid = tban.getcol('ANTENNA_ID')
        
    dic_an = {k: {'name': v} for k, v in zip(anid, anname)}
    dic_an

    tbfeed.colnames()
    if 'ANTENNA_ID' not in tbfeed.colnames():
        anids = list(range(len(anname)))
    else:
        anids = tbfeed.getcol('ANTENNA_ID')
        for anid in anids:
            mask = anid==anids
            feedid = np.unique(tbfeed.getcol('FEED_ID')[mask])
            dic_an[anid]['feedid'] = list(feedid)
    for anid in dic_an:
        mask = (tbvis.getcol('ANTENNA1') == anid) | (tbvis.getcol('ANTENNA2') == anid)
        descid = np.unique(tbvis.getcol('DATA_DESC_ID')[mask])
        dic_an[anid]['spw'] = list(tbdesc.getcol(spw_col)[descid])
        
    return dic_an

def add_spwid_totab(tb, spwid_missing, warnonly=True, dic_an_spw={}):
    """
    NOTE: This code is redundant. 
    FIXME : This assumes that the FEED1 and FEED2 are always 0. the dic_an_spw now has feedid as well.
    FIXME: existing bug, mask of antenna selection does not assume mask on spw.
    """
    colnames        =   tb.colnames()
    has_anid        =   'ANTENNA_ID' in colnames
    has_feedid      =   any(fky in colnames for fky in ['FEED1', 'FEED2', 'FEED_ID'])
    anmask          =   []
    
    if warnonly: tb  =   tb.copy("mem.dat",deep=False, valuecopy=True, memorytable=True)
    
    
    nrows           =   tb.nrows()
    spwids          =   tb.getcol("SPECTRAL_WINDOW_ID").copy()
    
    spwid0_rows = spwids[spwids[0]==spwids]         # HACK: assuming that first spw is available for all rows for the required spw. else use ANTENNA_ID
    fixed_row_len = len(spwid0_rows)
    
    
    startrow = 0
    for spwid_add in spwid_missing:
        
        if len(spwids[spwid_add==spwids])==0:       # checking if spwid already present
            if has_anid and dic_an_spw:
                anmask = np.zeros(tb.nrows(), dtype=bool)
                for an, _dicrest in dic_an_spw.items():
                    spws = _dicrest['spw']
                    if spwid_add in spws:
                        mask = tb.getcol('ANTENNA_ID') == an
                        anmask |= mask
                # print(an,anmask)
                fixed_row_len = len(anmask)                         # creating a fixed length of row from the fact that SUM(anI_nrows) corrosponds to spwid in uvdata
            
            tb.addrows(fixed_row_len)
            
            spwid_add_arr = np.zeros(fixed_row_len, dtype=int)+spwid_add
            print("fixing...", tb.name())
            for col in colnames:
                if col!="SPECTRAL_WINDOW_ID":
                    
                    
                    if has_anid and dic_an_spw:                                 # this mask is actually corrosponding the antennaid
                        # print(f"using mask of len {len(anmask)}")
                        
                        if tb.isvarcol(col) and col!='POLARIZATION_TYPE':
                            vals_orig = tb.getvarcol(col)
                            vals_new = {}
                            i_new = 0
                            for i_old, use in enumerate(anmask):
                                if use:
                                    vals_new[f"r{nrows + i_new+1}"] = vals_orig[f"r{i_old+1}"].copy().astype(vals_orig[f"r{i_old+1}"].dtype)
                                    i_new += 1

                            vals_combined = {**vals_orig, **vals_new}

                            # Sanity check:
                            if len(vals_combined) != tb.nrows():
                                raise RuntimeError(f"Expected {tb.nrows()} rows after addrows, but varcol has {len(vals_combined)} entries")

                            tb.putvarcol(col, vals_combined)
                        else:
                            # allvals = tb.getcol(col, startrow=0, nrow=nrows)            # value in (0, nrows) where nrows<=allrows; nrows = orig_rows + last_fixed_row_len
                            vals_orig = tb.getcol(col, startrow=0, nrow=nrows)  # only from existing rows
                            
                            # vals = vals_orig[anmask]  # mask only existing
                        
                            if vals_orig.ndim == 3:
                                vals = vals_orig[:, :, anmask]  # assuming shape (chan, pol, row)
                                expanded_vals = np.concatenate([vals_orig, vals], axis=2)
                            elif vals_orig.ndim == 2:
                                vals = vals_orig[:, anmask]     # assuming shape (pol, row)
                                expanded_vals = np.concatenate([vals_orig, vals], axis=1)
                            elif vals_orig.ndim == 1:
                                vals = vals_orig[anmask]
                                expanded_vals = np.concatenate([vals_orig, vals], axis=0)
                            else:
                                raise ValueError(f"Unexpected ndim={vals_orig.ndim} for column {col}")
                            # expanded_vals = np.concatenate([allvals, vals], axis=-1)
                            
                            print(col,": added spws " , str(",".join(np.unique(spwid_add_arr).astype(str))))
                            tb.putcol(col, expanded_vals)
                    
                    
                else:
                    spwids = np.append(spwids,spwid_add_arr)
                    tb.putcol(col, spwids)
                    
                if warnonly:print(col, nrows,"->" , nrows+fixed_row_len)
            startrow += fixed_row_len
            nrows += fixed_row_len
    return tb


def fix_feedid(vis, spw_col = 'SPECTRAL_WINDOW_ID', warnonly=True, verbose=True):
    
    fix_dic = {}
    tbfeed, tbsys, tbgain, tbvis, tbdesc = table(), table(), table(),table(), table()
    
    tbfeed.open(f"{vis}/FEED", nomodify=warnonly)
    tbsys.open(f"{vis}/SYSCAL", nomodify=warnonly)
    tbgain.open(f"{vis}/GAIN_CURVE", nomodify=warnonly)
    tbvis.open(vis)
    tbdesc.open(f"{vis}/DATA_DESCRIPTION")
    descid = np.unique(tbvis.getcol('DATA_DESC_ID'))
    
    spwidsexpected = tbdesc.getcol(spw_col)[descid]
    dic_an = get_dic_an(vis, spw_col=spw_col)
    if spw_col in tbfeed.colnames():
        alltbs = [tbfeed,tbsys,tbgain]
        
        for tbchk in alltbs:
            fix_dic[str(tbchk.name())] = {'expected':list(spwidsexpected), 'present': list(np.unique(tbchk.getcol(spw_col)))}
            if not all([spwid in tbchk.getcol(spw_col) for spwid in spwidsexpected]):
                if warnonly and verbose:
                    print(f"{tbchk.name()} : missing few values for SPECTRAL_WINDOW_ID")
                    print(f"expected: {spwidsexpected}, present: {np.unique(tbchk.getcol(spw_col))}")
                    
                tbchk = add_spwid_totab(tbchk, spwidsexpected, warnonly=warnonly, dic_an_spw=dic_an)
                if not warnonly:
                    tbchk.flush()
                    tbchk.close()
                    tbchk.done()
    return fix_dic

def get_tb_data(vis, axs=[]):
    tb.open(vis)

    available_cols = tb.colnames()
    res = []
    if len(axs):
        for ax in axs:
            if ax in available_cols:
                res.append(tb.getcol(ax))
            else:
                raise NameError(f"{ax} is not a valid column, choose from {','.join(available_cols)}")
    tb.close()
    return res

def select_long_scans(field_id, fields, scan_df):
    """
    sort the scan by number of rows and select the first five as list

    Example
    ---

    scannos                    =   select_long_scans(fid)
    scannos                    =   ",".join(scannos)        
    """
    
    npand                   =   scan_df.td[fields[field_id]['scans']]
    npand                   =   npand.sort_values(ascending=False)
    scans                   =   list(npand.index)
    return scans

def vals_fromtab(caltable):
    tb                      =   table()
    tb.open(caltable)
    snr                     =   tb.getcol('SNR').ravel()
    an1                     =   tb.getcol('ANTENNA1').ravel()
    an2                     =   tb.getcol('ANTENNA2').ravel()
    time                    =   tb.getcol('TIME').ravel()
    scan                    =   tb.getcol('SCAN_NUMBER').ravel()
    flag                    =   tb.getcol('FLAG').ravel()
    fid                     =   tb.getcol('FIELD_ID').ravel()
    # wt=tb.getcol('WEIGHT').ravel()
    tb.close()

    return snr,an1,an2,time,scan,fid,flag

def get_sci_ant(vis, tbls, target, msmd=None):
    tb = table()
    msm                =   None
    field_id           =   None
    antid              =   []
    if not msmd: 
        msm = msmetadata()
        
    else:
        msm = msmd
    
    msm.open(vis)
    field_id = msm.fieldsforname(target)[0]    
    
    if tbls:
        for tbl in tbls:
            tb.open(tbl)
            tbl_antid             =   tb.getcol('ANTENNA1')[np.where(tb.getcol('FIELD_ID')==field_id)]
            if not len(antid):antid =   tbl_antid
            antid                 =   np.intersect1d(antid, tbl_antid)
    
    ants = msm.antennanames(np.unique(antid)) if len(antid) else []
    if not msmd: msm.close()
    return ants, antid

def get_calib_df_sorted_desc(vis, tbls, target, calibs, msmd=None, dic=False):
    tb = table()
    calib_dic          =   {}
#     calib_df           =   df(data=[], colum)
    msm                =   None
    field_id           =   []
    
    if not msmd: 
        msm = msmetadata()
            
    else:
        msm = msmd
    
    msm.open(vis)
    for calib in calibs:
        if calib!=target:
            antid              =   []
            field_id           =   msm.fieldsforname(calib)[0]
            calib_dic[field_id]=   {}
            calib_dic[field_id]['source'] = calib
            if tbls and field_id:
                for tbl in tbls:
                    tb.open(tbl)
                    tbl_antid             =   tb.getcol('ANTENNA1')[np.where(tb.getcol('FIELD_ID')==field_id)]
                    if not len(antid):antid =   tbl_antid
                    antid                 =   np.intersect1d(antid, tbl_antid)

            ants = msm.antennanames(np.unique(antid)) if len(antid) else []
            calib_dic[field_id]['antennas'] = ants
    if not msmd: msm.close()
    if dic:
        return calib_dic
    else:
        return df.from_dict(calib_dic, orient='index')

def ants_intbls_unique(vis=None, msmd=None, tbls=None):
    
    tb = table()
    antid, msm                =   [], None
    if tbls:
        for tbl in tbls:
            tb.open(tbl)
            tbl_antid             =   tb.getcol('ANTENNA1')
            if not len(antid):antid =   tbl_antid
            antid                 =   np.intersect1d(antid, tbl_antid)
    if not msmd: 
        msm = msmetadata()
        msm.open(vis)
    else:
        msm = msmd
    ants = msm.antennanames(np.unique(antid)) if len(antid) else msmd.antennanames()
    if not msmd: msm.close()
    return ants, antid

def fringefit_for_refant_fields(vis, caltable, fields, refants, sources, spws, gaintable, scan_df, mpi, target=''):
    """"
    TODO: 
    all_sci_avail_ants = check all the ants available on science 
    find good_calibrator = {
        0. Calibrator with all sci_ants + above SNR_THRES
        1. calibrators_list = such that: combination([calibrator_covering avail_ants]) == all_sci_avail_ants
        1.1 : choose antennas still from the TSYS table.
        2. the current approach of rating calibrator based on the first refant is bad, use refant such that all_sci_avail_ants are present.
        3. The refant selection should be based on baseline i.e ANTENNA1-ANTENNA2 containing preferred refant
    }
    unflagged data from calibrator sources


    NEW: 
    calibs + target == sources (input parameter)
    """
    print("..doing FFT")
    tbl_names, status, err          =   [], True, ''
    
    msmd.open(vis)
    MPICLIENT                       =   start_mpi()
    success                         =   False
    ants_with_solution, anid        =   ants_intbls_unique(msmd=msmd, tbls=gaintable)
    refants                         =   np.intersect1d(ants_with_solution, refants)
    d_fields                        =   {}
    
    if target:
        all_sci_ant, ant_id         =   get_sci_ant(vis, gaintable, target, msmd=msmd)
        calibrator_df_sorted_desc   =   get_calib_df_sorted_desc(vis, gaintable, target, calibs=sources, msmd=msmd)
        sel_calibrator, remain_ant  =   choose_calib_for_snr_rating(all_sci_ant, calibrator_df_sorted_desc, n_ant=9)
    
        sources                         =   sel_calibrator + [target]
        if remain_ant:
            print(f"{c['r']}{remain_ant} was not found in any Calibrator Sources:{c['x']} {sel_calibrator}")

    try:
        for refant in refants:        
            for fid in fields:
                field_name  = fields[fid]['name']
                scans = select_long_scans(fid, fields, scan_df)
                
                nscans, usescans = 0, []
                for scan in scans:
                    antennasforscan = list(msmd.antennasforscan(int(scan)))
                    antid           = msmd.antennaids(refant)[0]
                    
                    if antid in antennasforscan:
                        nscans+=1
                        usescans.append(scan)
                    else:
                        print(f'scan {scan} not available in antenna {refant}')
                        scans.remove(scan)
                    if nscans>=5: break
                scannos                    =   ",".join(usescans)
                
                
                res, e      = [], ''
                ff_caltable = f"{str(Path(caltable).absolute() / Path(caltable).name)}_{refant}__{field_name}.t"
                gt = [str(Path(gaintabl).absolute()) for gaintabl in gaintable]
                try:
                    if sources and (not field_name in sources):
                        e = f"skipping {field_name} not selected"
                    elif not len(usescans)<1:
                        e = "not enough scans"                    
                        
                        if not mpi:
                            fringefit(
                                vis=vis,
                                caltable=f"{ff_caltable}", 
                                field=f'{fid}', 
                                selectdata=True,
                                scan=scannos,
                                solint='inf', zerorates=True,
                                refant=refant, minsnr=3, 
                                gaintable=gt,
                                interp=['nearest,nearest'],
                                globalsolve=False, 
                                docallib=False, 
                                parang=False,
                            )
                            success = True
                        else:
                            # print(refants, ants_with_solution, anid)
                            # print(fid, refant, scannos)
                            if MPICLIENT:
                                ms_name_fp      = vis#_inp_params.workdir + _inp_params.ms_name
                                caltable_fp     = ff_caltable#_inp_params.workdir + caltable
                                gaintable_fp    = gt#[_inp_params.workdir + gt for gt in gaintable]
                                
                                spw             =   spws #','.join([str(spw) for spw in spws])
                                corrcomb        =   'none'
                                combine         =   ''
                                # interp          =   'nearest'
                                gainfield = []
                                fringefit_cmd = ("""fringefit(vis='{0}',""".format(ms_name_fp)
                                                + """caltable='{0}',""".format(caltable_fp)
                                                + """field='{0}',""".format(str(fid))
                                                + """spw='{0}',""".format(spw)
                                                + """selectdata={0},""".format('True')
                                                + """timerange='{0}',""".format('')
                                                + """antenna='{0}',""".format(str(",".join(ants_with_solution)))
                                                + """scan='{0}',""".format(str(scannos))
                                                + """observation='{0}',""".format('')
                                                + """msselect='{0}',""".format('')
                                                + """solint='inf',"""
                                                + """combine='{0}',""".format(str(combine))
                                                + """refant='{0}',""".format(str(refant))
                                                + """minsnr={0},""".format(str(3))
                                                + """zerorates={0},""".format('False')
                                                + """globalsolve={0},""".format('False')
                        #                         + """weightfactor={0},""".format(str(weightfactor))
                                                # + """delaywindow={0},""".format(str(list(delaywindow)))
                                                # + """ratewindow={0},""".format(str(list(ratewindow)))
                                                # + """niter={0},""".format(str(_inp_params.fringe_maxiter_lsquares))
                                                # + """append={0},""".format(str(append))
                                                + """docallib={0},""".format('False')
                                                + """callib='{0}',""".format('')
                                                + """gaintable={0},""".format(str(gaintable_fp))
                                                + """gainfield={0},""".format(str(gainfield))
                                                # + """interp='{0}',""".format(str(interp))
                                                # + """spwmap={0},""".format(str(spwmap))
                                                + """corrdepflags={0},""".format('False')
                                                # + """paramactive={0},""".format(str(list(paramactive)))
                                                + """concatspws={0},""".format('True')
                                                + """corrcomb='{0}',""".format(str(corrcomb))
                                                + """parang={0}""".format('True')
                                                + """)"""
                                                )
                                # print(fringefit_cmd)
                                res = MPICLIENT.push_command_request(fringefit_cmd, block=False)
                                print(f'processing {refant} with scans {str(scannos)}')
                                # res_list.extend(res)
                                # success = res[0]['successful']
                                # print(res)
                                # e = res[0]['']
                    else:
                         success = False
                         
                except Exception as e:
                    success = False
                finally:
                    d_fields[f"{fid}___{refant}"] =  {'scannos': scannos, 'mpi_ids': res, 'e':e, 'tbl_names': ff_caltable}
                    
                        
    except Exception as e:
        status, err =False, e
    finally:
        msmd.done()
        if not status: raise SystemExit(f"{c['r']}Failed! {c['y']}{str(err)}{c['x']}")
    # ret = 
    # # print(ret)
    for k,v in d_fields.items():
        success = False
        if len(v['mpi_ids']): 
            res         =   MPICLIENT.get_command_response(v['mpi_ids'], block=True)
            success     =   res[0]['successful']
            if not success:
                # print('Errfinding traceback')
                e           =   res[0]['traceback']
        else:
            success     =   False
            e           =   v['e']

        fid, refant     =   k.split('___')
        field_name      =   fields[fid]['name']
        scannos         =   v['scannos']
        if not success:
            print(f'{c["r"]}processing failed{c["x"]}', scannos,'for field', field_name, 'with refant', refant, f"\nreason : {e}\n")
        else: 
            if Path(v['tbl_names']).exists(): 
                print(f'{c["g"]}processed{c["x"]}', scannos,'for field', field_name, 'with refant', refant)
                tbl_names.append(v['tbl_names'])
            else:
                err_flag = f"Successful fringefit execution but table not found"
                d_fields[f"{fid}___{refant}"]['err_flag'] = err_flag
                print(f'{c["r"]}processing failed{c["x"]}', scannos,'for field', field_name, 'with refant', refant, f"\nreason : {err_flag}\n")
                
    tbl_metafile = f"{str(Path(caltable).absolute() / Path(caltable).name)}.vasco"
    save_metafile(metafile=tbl_metafile, metad=d_fields)
    return tbl_names

def generic_df_fromtab(tbl, colnames=[]):  

    tbl_tuple = []
    tb=table()
    tb.open(tbl)
    for colname in tb.colnames():
        try:
            tbl_d = tb.getcol(str(colname))
            tbl_tuple.append(tbl_d)
            colnames.append(colname)
        except:
            pass
    tb.close()
    tbl_data   =  list(zip(*tbl_tuple))
    df_tbl_data=df(columns=colnames, data=tbl_data)

    return df_tbl_data

def df_fromtables(tbl_names):
    df_tb          =  None
    snr_0,an1_0,an2_0,time_0,scan_0,fid_0,flag_0= ([] for i in range(7))
    for i,tbl_name in enumerate(tbl_names):
        if i==0:
            snr_0,an1_0,an2_0,time_0,scan_0,fid_0,flag_0  =   vals_fromtab(str(tbl_name))

            tbl_data    =   list(zip(*(time_0, an1_0,an2_0,scan_0,fid_0,flag_0, snr_0))) 
            df_tb       =   df(tbl_data, 
                                columns  =  ["TIME", "ANTENNA1","ANTENNA2","SCAN","FIELD_ID","FLAG","SNR"])
        else:
            snr_1,an1_1,an2_1,time_1,scan_1,fid_1,flag_1 =   vals_fromtab(str(tbl_name))
            tbl_data    =   list(zip(*(time_1, an1_1,an2_1,scan_1,fid_1,flag_1, snr_1))) 

            new_df = df(tbl_data, 
                     columns  =  ["TIME", "ANTENNA1","ANTENNA2","SCAN","FIELD_ID","FLAG","SNR"])
# #             df_tb.append(new_df)
            df_tb  = pdconc([df_tb, new_df])
        
    
    df_tb  =  df_tb.sort_values(by=["SNR"], ascending=[False])
    # df_tb  =  df_tb[df_tb['ANTENNA1']!=df_tb['ANTENNA2']]
    # print(df_tb)
    return df_tb

def df_fromtb(vis, tbls, msmd):
    """
    TODO: following is outdated.
    returns dataframes containing:
    "ANTENNA2", "SNR_median", "FIELD_ID", "SNR_FIELD"

    CASA uses "ANTENNA2" as the reference antenna used for the table.
    """
    tb_ant = table()
    tb_tsys = table()
    tb_ant.open(f'{vis}/ANTENNA')
    tb_tsys.open(f"{vis}/SYSCAL")
    
    an_dict = {}
    
    xyz = list(zip(*tb_ant.getcol('POSITION')))
    an = tb_ant.getcol('NAME')
    tsys_anid = tb_tsys.getcol('ANTENNA_ID')
    tsys_vals = tb_tsys.getcol('TSYS')
    
    for i,an in enumerate(an):
        i_anid = msmd.antennaids(an)[0]
        
        # calculating TSYS variability
        tsys_std = []
        for tsys_val in tsys_vals:
            itsys = np.where(tsys_anid==i_anid)
            tsy_an_std = np.nanstd(tsys_val[itsys]) if len(itsys) else np.float('nan')
            tsys_std.append(tsy_an_std)
        
        an_dict[msmd.antennaids(an)[0]]={'ANNAME': an}
        an_dict[i_anid]['STD_TSYS']= np.nanmean(tsys_std)
        
        # measuring centroid distance
        d=[]
        refcoord=xyz[i]
        for v in xyz:
            d.append(distance.euclidean(refcoord,v)*.001)                                       # Distance of all from one refant
        an_dict[i_anid]['d']=np.nanmedian(d)   # Median distance of all ants for one refant
    
    tbd = df_fromtables(tbls)
    tb_ant.done()
    
    
    i,j=0,0
    df_o = tbd.loc[tbd['ANTENNA1']!=tbd['ANTENNA2']]
    df_o_unflagged = df_o.loc[df_o['FLAG']==False]

    for fid in tbd['FIELD_ID'].unique():
        tbd_source = df_o_unflagged.loc[df_o_unflagged['FIELD_ID']==fid]
        for refant in tbd_source['ANTENNA2'].unique():
            refant_snr = tbd_source.loc[tbd_source['ANTENNA2']==refant]['SNR']
            refant_snr_max = refant_snr.max()
            dist = an_dict[refant]['d']
            anname = an_dict[refant]['ANNAME']
            std_tsys = an_dict[refant]['STD_TSYS']
            tb_data=[[refant, anname, refant_snr.median(), refant_snr.mean(),refant_snr_max, fid, tbd_source.SNR.median(),dist, std_tsys]]      # median value for all scans
            if i==0:
                df_field_ant = df(tb_data,
                                 columns=["ANTENNA2", "ANNAME", "SNR_median", "SNR_mean", "SNR_max", "FIELD_ID", "SNR_FIELD", "d", "STD_TSYS"])
                i=1
            else:
                new_df       = df(tb_data,
                                 columns=["ANTENNA2", "ANNAME", "SNR_median", "SNR_mean", "SNR_max", "FIELD_ID", "SNR_FIELD", "d", "STD_TSYS"])
                df_field_ant = pdconc([df_field_ant, new_df], ignore_index=True)
    tb_ant.done()
    return df_field_ant

def flagsummary(vis, **kwargs):
      d=  flagdata(vis, mode='summary', 
                #  name=self.name, 
                 fieldcnt=True, basecnt=True, **kwargs, )
      return d

def splitms_mpi(vis, outvis, fids):

    MPICLIENT = start_mpi()
    mstransform_cmd =   (f"mstransform(vis='{str(vis)}', outputvis='{str(outvis)}', datacolumn='data', field='{fids}', createmms=True)")
    
    res         = MPICLIENT.push_command_request(mstransform_cmd, block=True)

    return res

def listobs_mpi(vis, overwrite, listfile, verbose):
    MPICLIENT = start_mpi()
    listobs_cmd = (f"listobs(vis='{vis}', overwrite={overwrite}, listfile='{listfile}',verbose={verbose})")
    res = MPICLIENT.push_command_request(listobs_cmd, block=True)
    return res[0]['ret']

def load_metadata(vis, metafile, refants=None, spws=None, sources=None, determine=False, mpi=False):
    """_summary_
    
    TODO: use msmd or ms casatools

    Args:
        vis (_str_): _name of the visibility file_
        metafile (_str_): _path of the metafile_
        refants (_list_, optional): _list of Antenna names for refants_. Defaults to None.
        spws (_list_, optional): _spectral window ids_. Defaults to None.
        sources (_list_, optional): _field names_. Defaults to None.
        determine (bool, optional): _whether to determine the metadata or load the older one if found_. Defaults to False.
        mpi (bool, optional): _use of MPI_. Defaults to False.

    Returns:
        _dict_: _dictionary of metadata_
    """
    if (not Path(metafile).exists()) or determine:
        if not sources: sources = []
        
        if not mpi:
            meta=listobs(vis=vis, overwrite=True, listfile=f'{str(Path(metafile).parent / "listobs.txt")}',verbose=False)
        else:
            
            meta=listobs_mpi(vis, overwrite=True, listfile=f'{str(Path(metafile).parent / "listobs.txt")}',verbose=False)
            
        print("loaded listobs..")
        fields = {}
        for k,v in meta.items():
            if ('field_' in k):
                if sources and v['name'] in sources:
                    fields[k.replace('field_', '')]      =    {'name':v['name']}
                elif not sources:
                    fields[k.replace('field_', '')]      =    {'name':v['name']}

        # fields                          =   {k.replace('field_', ''):{'name':v['name']} for k,v in meta.items() if ('field_' in k)}
        scans                           =   {k.replace('scan_', ''):{'t0':v['0']['BeginTime'],'t1':v['0']['EndTime']} for k,v in meta.items() if 'scan_' in k}
        for fk in fields:
            fields[str(fk)]['scans']    =   [k.replace('scan_', '') for k,v in meta.items() if ('scan_' in k) and (v['0']['FieldId']==int(fk))]
        # fs                 =   flagsummary(vis)
        meta={'fields': fields, 'scans': scans,}        
        if spws: meta['spws'] = spws
        save_metafile(metafile, meta)
    else:
        with open(metafile, 'r') as sf:
            metad                       =   sf.read()
            meta                        =   json.loads(metad)
    if refants: meta['refants'] =   refants
    if sources: meta['sources'] =   sources
    if spws:    meta['spws'] = spws
    return meta

    
def ff_to_tbl_names(vis, meta, metafile, refants=None, sources=None, spws=None, target='', gaintable=None, new_tbls=False, mpi=False):
    """
    
    """
    #   prepare and load
    hms                         =   datetime.now().strftime("%m%d_%H%M%S")
    wd                          =   Path(vis).parent
    fft_tb                      =   f"{wd}/fft_tab/{Path(vis).stem}_{hms}_ff"
    
    # if not metafile : metafile = str(wd / 'meta_shortfft.vasco')
    # meta = load_metadata(vis, metafile=metafile, refants=refants, sources=sources, determine=new_meta)
    
    scans                       =   meta['scans']
    fields                      =   meta['fields']
    refants                     =   meta['refants']
    sp                          =   df.from_dict(scans, orient='index')
    td                          =   Time(sp.t1, format='mjd')-Time(sp.t0, format='mjd')
    sp['td']                    =   TimeDelta(td, format='jd').sec
    
    if not gaintable: 
        gaintable               =   [f'{wd}/calibration_tables/accor.t',f'{wd}/calibration_tables/gc.t',f'{wd}/calibration_tables/tsys.t']
        gaintable               =   [gt for gt in gaintable if Path(gt).exists()]
    
    #   fringefit for each refant for each source
    
    if not new_tbls:
        tbl_names               =   glob.glob(f"{str(Path(meta['fft_tb']))}*.t")
        if len(tbl_names) < 1: 
            meta['fft_tb'] = None
            raise SystemExit(f"{c['r']} Failed! couldn't find tables{c['x']}")
    else:
        Path(fft_tb).mkdir(exist_ok=True, parents=True)
        tbl_names               =   fringefit_for_refant_fields(vis, fft_tb, fields, refants, sources, spws, gaintable, sp, mpi, target=target)
        meta['fft_tb'] = fft_tb
    save_metafile(metafile, meta)
    return tbl_names

def find_refant_fromtbls(vis, tbls, fields, verbose=False, wt_d=1.0, wt_snr=0.9, wt_tsys=0.8):
    """
    finds refants from Short Fringe Fit tables
    """
    SNR_UPPER_LIMIT                         =   380
    msmd.open(vis)

    df_field_ant                            =   df_fromtb(vis, tbls, msmd)
    n_ant                                   =   4
    print_tbls                              =   """ """

    msmd.done()

    fields_dict = {}

    for fid in fields.keys():
        fields_dict[int(fid)] = fields[fid]['name']

    df_field_ant_sorted                     =   df_field_ant.sort_values(by=["SNR_median"], ascending = False)
    

    df_field_ant                            =   df_field_ant.loc[df_field_ant['SNR_median']>SNR_THRES]
    std_tsys                                =   df_field_ant['STD_TSYS']

    p_ofd                       =   (1-(df_field_ant['d']/df_field_ant['d'].max()))
    p_ofsnr                     =   (df_field_ant.SNR_median.clip(upper=SNR_UPPER_LIMIT)/SNR_UPPER_LIMIT) if df_field_ant.SNR_median.max()>SNR_UPPER_LIMIT else (df_field_ant['SNR_median']/df_field_ant['SNR_median'].max())
    p_oftsys                    =   (1-(std_tsys/std_tsys.max()))
    
    df_field_ant.loc[:, 'p']    =   ((p_ofd*wt_d)+(p_ofsnr*wt_snr)+(p_oftsys*wt_tsys))/(wt_d+wt_snr+wt_tsys)
    
    df_field_ant_sorted                     =   df_field_ant.sort_values(by=['p'], ascending=False)
    df_field_ant_sorted.rename(columns={'ANTENNA2':'AN_ID'}, inplace=True)
    df_field_ant_sorted['FIELD_NAME']       =   df_field_ant_sorted['FIELD_ID'].map(fields_dict)
    
    refants_final               =   list(df_field_ant_sorted['ANNAME'].unique())[:n_ant]
    calibs                                  =   df_field_ant_sorted[df_field_ant_sorted['ANNAME'].isin(refants_final)]
    
    calibs.index                            =   calibs['FIELD_ID'].values
    calibs                                  =   calibs[['FIELD_NAME', 'SNR_FIELD']]
    
    calibs                                  =   calibs.drop_duplicates(['FIELD_NAME'])
    
    calibs_final                =   calibs[calibs['SNR_FIELD']>SNR_THRES]
    calibs_final                =   calibs_final.to_dict('list')
    
    print_tbls                              +=  df_field_ant_sorted.to_string() + "\n"
    print_tbls                              +=  calibs[calibs['SNR_FIELD']>SNR_THRES].to_string()
    if verbose: print(print_tbls)
    return refants_final, calibs_final, print_tbls

def params_check(vis, sources, refants, spws, ff_tbls, new_meta, new_tbls, mpi):
    """
    - sanitizes arguments
    - loads metadata
    """
    wd = Path(vis).parent
    
    if not refants or not refants[0]:
        msmd.open(vis)
        refants         =   msmd.antennanames()
        msmd.done()
    meta = None
    # for folder in [wd_ifolder, caltab]:
    #     if not Path(folder).exists():
    #         raise FileNotFoundError(f"Expected '''{folder}''' not found") 
    # d, _,_ = read_inputfile(wd_ifolder, 'array.inp')

    metafile = str(wd / 'vasco.meta' / 'msmeta_snrrating.vasco')
    Path(metafile).parent.mkdir(exist_ok=True, parents=True)
    if (not new_meta) and (not Path(metafile).exists()):
        new_meta = True
    print("loading metadata..")
    meta = load_metadata(vis, metafile=metafile, refants=refants, spws=spws, sources=sources, determine=new_meta, mpi=mpi)
    print("loading metadata done..")
    if (not ff_tbls) and (not new_tbls):
        lastf           =   latest_file(Path('fft_tab/'),'*_ff/*.t').parent
        if meta and ('fft_tb' in meta) and meta['fft_tb']:
            ff_tbls     =   glob.glob(f"{meta['fft_tb'].replace('./','')}/*.t")
        elif not ff_tbls and len(str(lastf))>5:
            ff_tbls     =   lastf.glob('*.t')
        else:
            new_tbls    =   True
            ff_tbls     =   None    
    print("params check done..")
    return refants, ff_tbls, new_meta, new_tbls, meta, metafile

def identify_refant_casa(vis, selected_sources=None, refants=None, spws=None, target='', ff_tbls=None, new_meta=False, new_tbls=False, mpi=False, verbose=True):
    """
    Returns
    refant_list, calib_dictionary
    
    :refant_list:       [refants]
    :calib_dictionary:  {'FIELD_NAME': [sources], {'SNR_FIELD':[snr_sources]}}
                        snr_sources: median values of all scans, antennas in the field
    """
    if not selected_sources:
        selected_sources=None
    print("..short FFT for refant and calibrator sources")
    refants, ff_tbls, new_meta, new_tbls, meta, metafile = params_check(vis=vis, sources=selected_sources, refants=refants, spws=spws, ff_tbls=ff_tbls, new_meta=new_meta, new_tbls=new_tbls, mpi=mpi)
    # print(new_tbls, "new_tbls")
    if not ff_tbls: 
        print("finding tables..")
        try:
            ff_tbls     =   ff_to_tbl_names(vis, meta, metafile, refants=refants, sources=selected_sources, spws=spws, target=target, new_tbls=new_tbls, mpi=mpi)
        except Exception as e:
            print("Exception occured!!!","\n\n",str(e))
    print("tables collected..")
    # print(meta['fields'])
    # print(ff_tbls)
    return find_refant_fromtbls(vis, ff_tbls, fields=meta['fields'], verbose=verbose)


# ---------------------- helper functions for Identifying sources using .MS for finding calibrators and phaserefence pair (check vasco.sources)

def get_scanlist_seq(msmd):
    scans = msmd.scannumbers()

    scanlist_seq = [int(msmd.fieldsforscan(scan)[0]) for scan in scans]
    return scanlist_seq

def get_sourcenames(msmd):

    warn_msg = ""
    sourcenames = {}
    for sid in msmd.fieldsforsource():
        if len(msmd.spwsforfield(sid)):
            sourcenames[sid]=msmd.namesforfields(sid)[0]
        else:
            warn_msg = f"{c['y']}{msmd.namesforfields(sid)[0]} has {len(msmd.spwsforfield(sid))} spws present{c['x']}"
            sourcenames[sid]=msmd.namesforfields(sid)[0]
    if warn_msg: print(warn_msg)
    return sourcenames

def coordinate_for_sources(vis, sourcenames):
    """
    Input
    
    :vis:       (str)   ms filepath

    Returns 
    
                (dictionary)
    
    key         :   value
    SOURCE_NAME : (ra,dec) 
                    scalar tuple in radians
    """
    c = {}
    tb.open(f"{vis}/FIELD")
    ra,dec = tb.getcol('REFERENCE_DIR')
    for i,s in enumerate(tb.getcol('NAME')):
        if s in sourcenames.values():
            c[s]=(ra[0][i], dec[0][i])
    tb.done()
    return c

def check_bands_ms(msmd):
    """
    Returns
    ---
    
    (dict)
    key      
    {
    'BAND': 
        {'reffreqs': [reffreqs], 'spws':[spws]}
    }
    
    'BAND'   = (str) "C", "X", "S"
    reffreqs = (list)   (float) (Hz)
    spws     = (list)   (int)
    
    """
    spws = set()
    spwsforfields = msmd.spwsforfields()
    for spws_inf in spwsforfields.values():
        spws.update(spws_inf)

    d= {}
    for spw in spws:

        reffreq = msmd.reffreq(spw)['m0']['value']
        band    = str(check_band(reffreq/1.0E+09))
        if band not in d.keys():
            d[band] = {}
        if 'spws' not in d[band].keys():
            d[band]['spws'] = [int(spw)]
            d[band]['reffreqs'] = [reffreq]
        else:
            d[band]['spws'].extend([int(spw)])
            d[band]['reffreqs'].extend([reffreq])
    return d

def get_target_in_bands(msmd, target, bands_dict):
    spws = msmd.spwsforfield(str(target))
    bands = []
    for band in bands_dict:
        if all(spw_band in list(bands_dict[band]['spws']) for spw_band in list(spws)):
            bands.extend([band])
        else:
            print(f"{target} is not in {band} band", spws)
    return bands

def coordinate_for_target(vis, target, sourcenames):
    """

    Returns
    ---

    (tuple)

    other_names, c_other, c_target

    :other_names:       (list) list of other source names
    :c_other:           (tuple) (astropy.units.radian, astropy.units.radian)
    :c_target:           (tuple) (astropy.units.radian, astropy.units.radian)
    """
    s = {}
    c = coordinate_for_sources(vis, sourcenames)
    # idx_target = list(c.keys()).index(target)
    sv = c.pop(target, None)
    sv = SkyCoord(sv[0]*u.rad,sv[1]*u.rad) if sv else None
    
    if c:
        r, d = list(zip(*c.values()))
        oth = SkyCoord(r*u.rad,d*u.rad)
    else:                                       # when target is the only source in file
        oth = sv
    
    return oth, list(c.keys()), sv

def identify_sources_fromtarget_ms(vis, target_source, caliblist_file=None, flux_thres=0.150, min_flux=0.025, ncalib=20, flux_df=None, sourcenames=None, hard_selection=False, metafolder=None):
    """
    TODO: change caliblist_file name to calibrator catalog file
    """
    
    if metafolder is None: metafolder       =   Path(vis).parent / 'vasco.meta'
    metafile                                =   Path(metafolder)  / 'msmeta_sources.vasco'
    msmd.open(vis)

    if not sourcenames : sourcenames        =   get_sourcenames(msmd)
    c_others ,other_sources, c_target       =   coordinate_for_target(vis, target=target_source, sourcenames=sourcenames)
    scanlist_seq                            =   get_scanlist_seq(msmd)
    bands_dict                              =   check_bands_ms(msmd)
    target_in_bands                         =   get_target_in_bands(msmd, target_source, bands_dict)
    # bands                                   =   list(bands_dict.keys())
    msmd.done()

    meta = {
        # 'sourcenames': sourcenames, 
            'c_others': c_others.to_string('hmsdms'), 
            'other_sources':other_sources, 
            'c_target': c_target.to_string('hmsdms'),
            'scanlist_seq':scanlist_seq, 
            'bands_dict': bands_dict
            }

    s_dict                                  =   {}
    for band in target_in_bands:
        s                                   =   identify_sources_fromtarget(scanlist_seq, sourcenames, target_source, other_sources, c_target, c_others, 
                                                    band=band, flux_thres=flux_thres, min_flux=min_flux, ncalib=ncalib, caliblist_file=caliblist_file, verbose=True, flux_df=flux_df, hard_selection=hard_selection)
        s_dict[band]                        =   s
    print(flux_thres)
    meta['s_dict']                          =   s_dict
    save_metafile(metafile, meta)
    return s_dict

def identify_sources_fromsnr_ms(vis, target_source, caliblist_file=None, snr_metafile=None, outfile='',
                                flux_thres=18.0, min_flux=7.0,ncalib=9,  msmd=msmd):

    if not snr_metafile: snr_metafile       =   Path(vis).parent / 'vasco.meta' / 'sources.vasco'
    mf_dic                                  =   read_metafile(snr_metafile)
    if caliblist_file is None: caliblist_file                          =   mf_dic['NAME']
    msmd.open(vis)
    sourcenames=get_sourcenames(msmd)
    # sourcenames                             =   {}
    # for i,fid in enumerate(mf_dic['FIELD_ID']):
    #     sourcenames[fid]    =   mf_dic['NAME'][i]
    # print(sourcenames)
    s_df                                    =   df(data=sourcenames.values(), index=sourcenames.keys(), columns=['source_name'])
    mf_df                                   =   df.from_dict(mf_dic)
    mf_df                                   =   mf_df.rename(columns={'NAME':'source_name', 'SNR':'flux'})
    
    # mf_df.loc[:,'FIELD_ID']                 =   [int(s_df.loc[s_df['source_name']==sname].index.values[0]) for sname in mf_df['source_name']]

    mf_df                                   =   mf_df.drop_duplicates()
    mf_df                                   =   mf_df.set_index('FIELD_ID')
    mf_df                                   =   s_df.merge(mf_df, on='source_name', how='left')
    flux_df                                 =   df(mf_df['flux'])
    sd = identify_sources_fromtarget_ms(vis, target_source, caliblist_file=caliblist_file, 
                                flux_thres=flux_thres, min_flux=min_flux, ncalib=ncalib, flux_df=flux_df, sourcenames=sourcenames, 
                                hard_selection=True)
    if not outfile: outfile = str(Path(vis).parent / 'vasco.meta' / 'sources_ms_snr.vasco')
    save_metafile(outfile, sd)
    return sd


# ----------------------------------------------------------------

def split_ms(vis, outvis, source_list=[], fids=[], mpi=False):
    
    if not fids:
        fids=[]
        if not source_list: raise TypeError(f"source_list is required")
        try:
            msmd.open(vis)
            for f in source_list:
                fid = msmd.fieldsforname(str(f))[0]
                fids.append(str(fid))
        except Exception as e:
            # closed = msmd.done()
            print(str(e))
        finally:
            msmd.done()
    
    fids=','.join(fids)

    if mpi:
        ret = splitms_mpi(vis, outvis, fids)
    else:
        ret =   mstransform(vis=f'{vis}', outputvis=f'{outvis}', datacolumn='data', field=f'{fids}', createmms=True)
    # res         = MPICLIENT.push_command_request(mstransform_cmd, block=True)
    return ret

# ---------- Diagnostics -----------


# def sel_by_baseline(vis, **kwargs):
    
#     tb.open(vis)
#     ij = tb.getcol('ANTENNA1'),tb.getcol('ANTENNA2')
#     baseline_seq = ((ij[0]+1)*256) + (ij[1]+1)
#     allbaselines = np.unique(baseline_seq)
#     tb.done()
#     tb.open(f"{vis}/ANTENNA")
#     annames = tb.getcol('NAME')
#     xyz =list(zip(*tb.getcol('POSITION')))
#     tb.done()
    
    
#     return np.isin(baseline_seq, df_baseline_by(allbaselines, annames, xyz, **kwargs).index)

def get_df_vis(vis, dcol='DATA'):
    """
    
    """
    time, expos, sid, fid, data, sigma, an1, an2, uvw, flag = get_tb_data(vis, axs=['TIME','EXPOSURE','SCAN_NUMBER', 'FIELD_ID', dcol, 
                                                                      'SIGMA','ANTENNA1','ANTENNA2','UVW',
                                                                      'FLAG'])

    [field_name]               = get_tb_data(f"{vis}/FIELD", axs=['NAME'])
    
    npol =data.shape[0]
    nchan=data.shape[1]
    nrows=data.shape[2]
    
    batch_idx = np.repeat(np.arange(npol), nrows * nchan)  # (npol * nrows * nchan,)
    sample_idx = np.tile(np.repeat(np.arange(nrows), nchan), npol)  # (npol * nrows * nchan,)
    channel_idx = np.tile(np.arange(nchan), npol * nrows)  # (npol * nrows * nchan,)
    
    multi_index = MultiIndex.from_arrays(
        [batch_idx, sample_idx, channel_idx], names=["pol", "row", "nchan"]
    )
    
    wt_calc = 1/(sigma*sigma)
    
    amp = np.abs(data)
    phase = np.angle(data, deg=True)
    
    amp_reshaped = amp.transpose(0, 2, 1).reshape(-1, 1)  # Reshape to (npol * nrows * nchan, 1)
    phase_reshaped = phase.transpose(0, 2, 1).reshape(-1, 1)  # Reshape to (npol * nrows * nchan, 1)
    flag_reshaped = flag.transpose(0, 2, 1).reshape(-1, 1)  # Reshape to (npol * nrows * nchan, 1)
    
    wt_calc_reshaped = np.repeat(wt_calc.T, nchan, axis=0).reshape(-1, 1)  # Broadcast over channels
    
    time_repeated = np.tile(np.repeat(time, nchan), npol).reshape(-1, 1)  # Repeating time for each channel
    expos_repeated = np.tile(np.repeat(expos, nchan), npol).reshape(-1, 1)  
    an1_repeated =  np.tile(np.repeat(an1, nchan), npol).reshape(-1, 1)  
    an2_repeated =  np.tile(np.repeat(an2, nchan), npol).reshape(-1, 1)  
    fid_repeated =  np.tile(np.repeat(fid, nchan), npol).reshape(-1, 1)  
    sid_repeated =  np.tile(np.repeat(sid, nchan), npol).reshape(-1, 1)  
    uvw_repeated =  np.tile(np.repeat(uvw.T, nchan, axis=0), npol)
    
    dfs = df(
        np.hstack([time_repeated,expos_repeated,uvw_repeated, an1_repeated,an2_repeated,
                   fid_repeated, sid_repeated, wt_calc_reshaped, flag_reshaped, amp_reshaped, phase_reshaped], dtype='object'),
        index=multi_index,
        columns=['time','expos','u','v','w', 'an1','an2','fid','sid', 'wt_calc', 'flag', 'amp', 'phase',]
    )
    
    
    dic_field   = {fid: fname for fid,fname in enumerate(field_name)}
    dfs['field']  =  dfs['fid'].map(dic_field)
    
    u=dfs['u'].astype('float64')
    v=dfs['v'].astype('float64')
    dfs['uvdist'] = np.sqrt(u*u + v*v)

    return dfs

def get_axes(vis):
    tb.open(vis)
    
    time = tb.getcol('TIME')/(3600*24)
    time = Time(time, format='mjd')
    data = tb.getcol('DATA')
    field   = tb.getcol('FIELD_ID')
    tb.done()
    amp     = np.sqrt(data.real.T*data.real.T + data.imag.T*data.imag.T)
    avg_amp = np.nanmean(amp.T, axis=0)[0]
    avg_phase= np.nanmean(np.rad2deg(np.arctan2(data.imag, data.real)), axis=0)[0]
    
    wo_nan  = np.argwhere(~np.isnan(avg_amp)).T[0]
    
    field   = field[wo_nan]
    avg_amp = avg_amp[wo_nan]
    avg_phase=avg_phase[wo_nan]
    time = time.mjd[wo_nan]
    return field, avg_amp, avg_phase, time, wo_nan

def get_fid(vis, target):
    fid=None
    
    msmd = msmetadata()
    try:
        msmd.open(vis)

        fid = msmd.fieldsforname(target)[0]

    except Exception as e:
        print(str(e))
    finally:
        msmd.done()                   

    return fid


def get_axs(vis, ret_sel_idx=False):
    """
    Returns avg_amp, avg_phase, time, antenna
    uvdist is taken assuming UVW is taken from a reference origin at (0,0,0)
    # TODO: take nchan, nspw and create amp/flux for each, that way we can do average later and consider flag for each nchan, nspw etc
    """
    from vasco.ms import get_tb_data
    time, field, data, weight, an1, an2, uvw, flag = get_tb_data(vis, axs=['TIME', 'FIELD_ID', 'DATA', 
                                                                      'WEIGHT','ANTENNA1','ANTENNA2','UVW',
                                                                      'FLAG_ROW'])
    
    mean_freq                  =   np.mean(get_tb_data(f"{vis}/SPECTRAL_WINDOW", axs=['CHAN_FREQ']))
    amp, ph                  = get_avg_amp_phase(data, weight)
    weight_idx               =  weight>=0.0
    sel_idx                  = np.argwhere(~np.isnan(amp)).T[0] 
        
    wavelength = 299792458.0 / mean_freq
    
    # is_not_nan = ~np.isnan(amp)
    # is_notnegweighted = weight >= 0.0
    # sel_idx = np.where(is_not_nan & is_notnegweighted)[0]
    
    if (sel_idx is not None) and len(sel_idx):
        amp, ph                        = amp[sel_idx], ph[sel_idx]
    if (sel_idx is not None) and not len(sel_idx):
        sel_idx  = None
    time                              = Time(time/(3600*24), format='mjd')[sel_idx].decimalyear
    an1                               = an1[sel_idx]
    an2                               = an2[sel_idx]
    uvdist                            = np.sqrt((uvw[0].T*uvw[0])+(uvw[1].T*uvw[1]))
    uvdist                            = uvdist[sel_idx]/wavelength
    field                             = field[sel_idx]
    
    # unflagged                         = ((~flag).sum(axis=0)).astype(int)[0][sel_idx] # for tb.getcol('FLAG') which operates on spw etc
    unflagged                         = (~flag).astype(int).T
    if (unflagged==0).sum()>0:
        unflagged                   = unflagged[sel_idx]
    
    data_dict                         = {'time':time.T, 'unflagged':unflagged.T, 'uvdist':uvdist,
                                         'an1':an1.T,'an2':an2.T, 'field':field.T, 
                                         'amp':amp.T, 'phase':ph.T,
                                        }
    
    axs_df                            = df(data_dict)
    
    if ret_sel_idx: return axs_df, sel_idx
    return axs_df

def pl_diag_ms(vis, target, kind='png', **kwargs):
    
    fid=''
    
    #       Create dataframe from the MS file
    axs_df = get_axs(vis)
    
    
    if target:
        msmd.open(vis)
        fid=msmd.fieldsforname(target)
        msmd.done() 
        axs_df = axs_df[axs_df['field'].values==fid]
        
    unflagged = axs_df['unflagged']==1
    wd = (Path(vis).parent / 'output' / target).resolve()
    return pl_diag(axs_df[unflagged], kind=kind, prefix=str(wd) , **kwargs)

def flag_d(vis, target,flag=True):
    success=True
    flagged_perc = 0.0
    eps=0.005 
    n_cores=15
    kind='png'

    df_vis = get_axs(vis)

    df_ms = df_vis
    # idx_autocorr = df_ms['an1']==df_ms['an2']
    idx_non_autocorr = df_ms['an1']!=df_ms['an2']
    # df_ms.loc[idx_autocorr,'unflagged'] = 0
    idx_field = None
    axs_d = df_ms[idx_non_autocorr]
    if target:
        msmd.open(vis)
        fid=msmd.fieldsforname(target)
    msmd.done() 
    if target:
        idx_field = axs_d['field'].values==fid
        axs_d = axs_d.loc[idx_field]
    
    amp = axs_d['amp'].values
    phase = ((axs_d['phase'] + 180)/360).values

    ap_normalised = np.column_stack((amp, phase))

    min_samples=int(np.log(len(ap_normalised))/2)
    if min_samples < 5: min_samples=5
    labels = get_labels_dbscan(ap_normalised, eps, min_samples, n_jobs=n_cores)

    axs_df_scatter = calcscatter_fromlabels_df(axs_d, labels, 'amp', 'phase')

    # good_scatter_dic = stat_gooddata(axs_df_scatter, pop_perc=0.8)
    flaggable_idx = axs_df_scatter['labels']==-1
    
    print(sum(flaggable_idx), "flaggable visibility")
    if flag:
        tb = table()
        tb.open(vis, nomodify=False)
        
        size =  df_vis.index.max() + 1  
        idx_int = df_vis[idx_non_autocorr][idx_field][flaggable_idx].index
        
        
        
        flaggable_data = tb.getcol('FLAG_ROW')
        if len(flaggable_data)!= len(df_vis.index): raise TypeError("The flag row column is not the same as column data")

        flaggable_data[idx_int] = True

        # flag= tb.getcol('FLAG')
        # flag.T[idx_int] = ~tb.getcol('FLAG').T[idx_int]
        
        try:
            
            tb.putcol('FLAG_ROW', flaggable_data)
            # tb.putcol('FLAG', flag)
            success = tb.flush()
            tb.close()
            tb.done()
            
            flagged_perc = np.round(len(idx_int)/len(flaggable_data)*100,3)
            overall_flagged = np.round(sum(flaggable_data)/len(flaggable_data)*100,3)
            print(f"Flagged successfully: {flagged_perc} % | overall flagged: {overall_flagged} %")
            
        except:
            traceback.print_exc()
            success=False
    return flagged_perc, success

def flag_byweights(vis, nomodify=True):
    tb.open(vis, nomodify=nomodify)
        
    size =  df_vis.index.max() + 1  
    idx_int = df_vis[idx_non_autocorr][idx_field][flaggable_idx].index
    
    
    
    flaggable_data = tb.getcol('FLAG_ROW')
    if len(flaggable_data)!= len(df_vis.index): raise TypeError("The flag row column is not the same as column data")

    flaggable_data[idx_int] = True

    # flag= tb.getcol('FLAG')
    # flag.T[idx_int] = ~tb.getcol('FLAG').T[idx_int]
    
    try:
        
        tb.putcol('FLAG_ROW', flaggable_data)
        # tb.putcol('FLAG', flag)
        success = tb.flush()
        tb.close()
        tb.done()
        
        flagged_perc = np.round(len(idx_int)/len(flaggable_data)*100,3)
        overall_flagged = np.round(sum(flaggable_data)/len(flaggable_data)*100,3)
        print(f"Flagged successfully: {flagged_perc} % | overall flagged: {overall_flagged} %")
        
    except:
        traceback.print_exc()
        success=False

def find_phasecenter_inms(fitsfile, vis, class_searchcoord_file, sep=0.85 ):
    """
    uses the coordinate, fits_target columns in the dataframe from class_searchcoord_file to find fields need phaseshift when separation in arcsec >{sep}"
    """
    from vasco.util import read_df_out
    from vasco.fitsio import df_source_fits
    dic_phase_center = {}
    
    df_class_search = read_df_out(class_searchcoord_file)
    df_fits = df_source_fits(fitsfile)

    df_class_compare = df_class_search[['fits_target', 'sid', 'coordinate']].copy()
    df_class_compare = df_class_compare.merge(
        df_fits[['fits_target', 'fits_coordinate']],
        on='fits_target',
        how='left'
    )

    coord1 = df_class_compare['coordinate'].values
    coord2 = df_class_compare['fits_coordinate'].values

    df_class_compare['sep_arcsec'] = SkyCoord(coord1, unit=(u.hourangle, u.deg), frame='icrs').separation(SkyCoord(coord2, unit=(u.hourangle, u.deg), frame='icrs') ).arcsec
    df_class_compare = df_class_compare.query(f'sep_arcsec >= {sep}')[['fits_target', 'coordinate', 'sid', 'sep_arcsec']]
    
    if not df_class_compare.empty:
        from vasco.ms import get_tb_data
        [field_name]               = get_tb_data(f"{vis}/FIELD", axs=['NAME'])
        
        field_name = [str(fn) for fn in field_name]
        dic_phase_center = {}

        fields_forphaseshift = df_class_compare['fits_target'].values

        for field in fields_forphaseshift:
            try:
                field_idx = field_name.index(field)
                field_found = True
            except:
                field_found = False
                field = '0' + field[1:]
                try:
                    field_idx = field_name.index(field)
                    field_found = True
                except:
                    field_found = False
            if not field_found: 
                raise NameError(f"field {field} not found")
            else:
                coord = df_class_compare.loc[df_class_compare['fits_target'] == field]['coordinate'].values[0]
                coord = SkyCoord(coord, unit=(u.hourangle, u.deg), frame='icrs').to_string('hmsdms', sep=':')
                dic_phase_center[str(field_idx)] = 'ICRS ' + str(coord)

    return dic_phase_center

from itertools import product

def get_alluniquecomb_spws(vis):
    """
    when there are similar band for multiple spws
    """
    tbfo = table()
    
    tbfo.open(f'{vis}/SPECTRAL_WINDOW')
    freqs = tbfo.getcol('CHAN_FREQ')
    tbfo.close()
    spws_freq_list = freqs.mean(axis=0)
    unique_freqs_cen = np.unique(spws_freq_list)

    spw_for_freq=[]
    for freq in unique_freqs_cen:
        spw_for_freq.append(np.where(spws_freq_list==freq))
    
    spwscomb = list(product(*(t[0] for t in spw_for_freq)))
    
    return spwscomb
    

def get_best_spws(vis):
    bestspws = []
    countscans = 0
    countants = 0
    spwscomb = get_alluniquecomb_spws(vis)
    
    msmd = msmetadata()
    
    msmd.open(vis)
    scansforspws = msmd.scansforspws()
    

    for uniquespws in spwscomb:
        allscans  = set()
        antennacount = 0
        for spw in uniquespws:
            allscans.update(scansforspws[str(spw)])
        for scan in allscans:
            antennacount += len(msmd.antennasforscan(scan))
            
        has_morescans = countscans < len(allscans)
        has_moreants = countants < antennacount
        
        if has_moreants and has_morescans:
            bestspws = uniquespws
            countants = antennacount
            countscans = len(allscans)
    msmd.close
    return bestspws