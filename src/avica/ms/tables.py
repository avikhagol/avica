from avica.ms.compat import CasaMSMetadata as msmetadata, ctable
import polars as pl
import numpy as np
from scipy.spatial import distance

from pathlib import Path

from typing import List
from collections import defaultdict
from avica.util import check_band

def get_tb_data(vis, axs=[]):
    """get table data from the table by specifying valid columns in axs.

    Args:
        vis (str):  measurement set file path.
        axs (list, optional): name of the columns to read from the measurement set. Defaults to [].

    Raises:
        NameError: if specified column not found.

    Returns:
        list: list of data corresponding to the columns specified.
    """
    tb = ctable(vis, readonly=True, ack=False)

    available_cols = tb.colnames()
    res = []
    if len(axs):
        for ax in axs:
            if ax in available_cols:
                data_value = tb.getcol(ax)
                if isinstance(data_value, np.ndarray):
                    if data_value.ndim != 1:
                        res.append(data_value.T)
                    else:
                        res.append(data_value)
                else:
                    res.append(data_value)
            else:
                raise NameError(f"{ax} is not a valid column, choose from {','.join(available_cols)}")
    tb.close()
    return res

def select_long_scans(vis, fids=[], sources=[], nscan=5):
    """takes visibility file path, source ID or source name as list and returns the top nscan long scans

    Args:
        vis (str): measurement set file path
        fids (list, optional): list of field ID associated to the measurement set, infers from sources if fids not provided. Defaults to [].
        sources (list, optional): list of sources. Defaults to [].
        nscan (int, optional): number of top scans to choose based on the scan durations. Defaults to 5.

    Returns:
        res (dict):
        dict of fid with assoicated scan numbers for each fids
    """
    tb = ctable(vis, readonly=True, ack=False)
    res = {}

    if not fids:
        if sources:
            tb_field = ctable(vis + "/FIELD", readonly=True, ack=False)
            fields = tb_field.getcol('NAME')
            for field in sources:
                fids.append(list(fields).index(field))
            tb_field.close()

    for fid in fids:
        subtb = tb.query(columns="DISTINCT SCAN_NUMBER,TIME", query=f'FIELD_ID=={fid}')

        time = subtb.getcol('TIME')
        scans = subtb.getcol('SCAN_NUMBER')
        subtb.close()

        scans_df = pl.DataFrame({
            'time': time,
            'scans': scans
        })

        scan_durations = (
            scans_df.group_by('scans')
            .agg((pl.col('time').max() - pl.col('time').min()).alias('duration'))
            .sort('duration', descending=True)
            )
        res[fid] = scan_durations.get_column("scans").to_list()[:nscan]
    tb.close()

    return res


def getremovableant_fromsource(vis, source):
    tb1 = ctable(f"{vis}/FIELD", readonly=True, ack=False)
    idx_source = list(tb1.getcol("NAME")).index(source)
    tb1.close()

    tb1 = ctable(vis, readonly=True, ack=False)
    anids = set()
    subtb = tb1.query(f"FIELD_ID=={idx_source}")
    anids.update(np.unique(subtb.getcol('ANTENNA1')))
    anids.update(np.unique(subtb.getcol('ANTENNA2')))
    subtb.close()
    tb1.close()

    tb1 = ctable(f"{vis}/ANTENNA", readonly=True, ack=False)
    annames = tb1.getcol("NAME")
    tb1.close()

    # anids_list = list(anids)
    rm_anids = []

    # source_annames = annames[anids_list]
    for anid in range(len(annames)):
        if anid not in anids:
            rm_anids.append(list(range(len(annames))).pop(anid))
    return list(rm_anids), list(annames[rm_anids])



def an_dic(vis, source=None, antenna=[], notantenna=[]):
    """Antenna dictionary with median distance to centroid and standard deviation in TSYS

    Args:
        vis (str):  measurement set file path.
        source (str, optional): source name. Defaults to None.
        antenna (list, optional): filter only specified antenna names. Defaults to [].
        notantenna (list, optional): remove antennas from selection. Defaults to [].

    Returns:
        dict: Antenna dictionary {int:ANNAME:str}
    """

    tsys_anid, tsys_vals        =   get_tb_data(f"{vis}/SYSCAL", axs=['ANTENNA_ID', 'TSYS'])
    pos, annames                =   get_tb_data(f"{vis}/ANTENNA", axs=['POSITION', 'NAME'])

    xyz                         =   list(zip(*pos))
    if source is not None:
        _, rm_ants      =   getremovableant_fromsource(vis, source)
        notantenna      =   notantenna + rm_ants

    an_dict = {}
    for anid,an in enumerate(annames):
        if not antenna: antenna = list(range(len(annames)))                                         # here, in case something changes within loop
        antenna = [antv for antv in antenna if annames[antv] not in notantenna]
        if anid in antenna:
            an_dict[anid]={'ANNAME': an}
                                                                                                    # measuring centroid distance
            d=[]
            refcoord=xyz[anid]
            for v in xyz:
                d.append(distance.euclidean(refcoord,v)*.001)                                       # Distance of all from one refant
            an_dict[anid]['d']=np.nanmedian(d)                                                      # Median distance of all ants for one refant

                                                                                                    # calculating TSYS variability
            tsys_std = []
            for tsys_val in tsys_vals:
                itsys = np.where(tsys_anid==anid)
                tsy_an_std = np.nanstd(tsys_val[itsys]) if len(itsys) else float('nan')
                tsys_std.append(tsy_an_std)

            an_dict[anid]['STD_TSYS']= np.nanmean(tsys_std, axis=0) if not all(np.isnan(tsys_std)) else float('nan')
    return an_dict



def get_name_dict(vis, tab):
    [names] = get_tb_data(f"{vis}/{tab}", ['NAME'])
    res_dic = {}
    for fid, name in enumerate(names):
        res_dic[fid] = str(name)

    return res_dic

def get_ant_scans(vis:str, fids:List):
    """Dictionary with antenna and scan availability for each field.


    Args:
        vis (str): measurement set file.
        fids (List): field ids.

    Returns:
        Dict: {fid:{antid:set(scans)}}
    """
    ant_with_available_scans = defaultdict(lambda: defaultdict(set))

    tb = ctable(vis, readonly=True, ack=False)
    for fid in fids:

        subtb = tb.query(query=f'FIELD_ID=={fid}', columns='DISTINCT SCAN_NUMBER,ANTENNA1,ANTENNA2')

        a1 = subtb.getcol("ANTENNA1")
        a2 = subtb.getcol("ANTENNA2")
        scans = subtb.getcol("SCAN_NUMBER")
        for i in range(len(scans)):
            s = int(scans[i])
            an1 = int(a1[i])
            an2 = int(a2[i])

            ant_with_available_scans[fid][an1].add(s)
            ant_with_available_scans[fid][an2].add(s)

        subtb.close()
    tb.close()
    return ant_with_available_scans

# ------------------------------ Read the MS data and get a polars DataFrame         -------------------------------

def read_df_vis(vis:str, corr: List = [], spw: List =[], dcol:str='DATA', sel_row:List=[]):

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


# ------------------------------ check the Similar MS tables and fix duplicated rows -------------------------------

def chk_tbl(subt1, subt2, relax_order=False):
    """
    subt1 and subt2 are subtables in polars dataframe
    Checks if subt2 has multiple copies of subt1.
    For each iteration i, compare row n from subt1 with row n * i from subt2
    """
    chk   = []
    dic_res = {}
    nrow1 = subt1.shape[0]
    nrow2 = subt2.shape[0]

    if relax_order and nrow1>nrow2:
        cmprow, subtcmp = nrow1, subt1
        nrow1, subt1 = nrow2, subt2
        nrow2, subt2 = cmprow, subtcmp

    niter = nrow2/nrow1

    if niter>1:
        if nrow2 % niter != 0:
            raise SystemExit(f"rownr {subt2.shape[0]} of subt2 is not the valid factor of the rownr {subt1.shape[0]} of subt1\nAborting!")
    else:
        for i in range(int(niter)):
            si = nrow1*i
            ei = si+nrow1
            chk.append((subt2[si:ei]==subt1).to_series().all())
    if all(chk):
        dic_res['dubplicate_row'] = [nrow1, nrow2]
    dic_res['duplicate'] = all(chk)
    dic_res['niter'] = niter


    return dic_res


def verifysubt_byeachelem(refvis, newvis):
    tb = ctable(refvis, readonly=True, ack=False)

    keywords =tb.keywordnames()
    tb.close()

    dic_kywchecked = {}
    if 'PHASE_CAL' in keywords:
        phcal_orig, phcal_shifted           = read_phasecal(refvis), read_phasecal(newvis)
        dic_kywchecked['PHASE_CAL']         = chk_tbl(phcal_orig, phcal_shifted)
    if 'WEATHER' in keywords:
        weather_orig, weather_shifted       = read_weather(refvis), read_weather(newvis)
        dic_kywchecked['WEATHER']           = chk_tbl(weather_orig, weather_shifted)
    if 'SYSCAL' in keywords:
        syscal_orig, syscal_shifted         = read_syscal(refvis), read_syscal(newvis)
        dic_kywchecked['SYSCAL']            = chk_tbl(syscal_orig, syscal_shifted)
    if 'ANTENNA' in keywords:
        ant_orig, ant_shifted               = read_antenna(refvis), read_antenna(newvis)
        dic_kywchecked['ANTENNA']           = chk_tbl(ant_orig, ant_shifted)
    if 'GAIN_CURVE' in keywords:
        gain_orig, gain_shifted             = read_gain(refvis), read_gain(newvis)
        dic_kywchecked['GAIN_CURVE']        = chk_tbl(gain_orig, gain_shifted)

    return dic_kywchecked

def verifysubt_nrows(refvis, newvis):

    defectedsubt = []
    tb = ctable(refvis, readonly=True, ack=False)
    keywords_tochk =tb.keywordnames()
    tb.close()

    excludechk = ['MS_VERSION','DATA_DESCRIPTION','FEED','FLAG_CMD','FIELD','HISTORY']
    for keyw in excludechk:
        if keyw in keywords_tochk:
            keywords_tochk.remove(keyw)

    for subt in keywords_tochk:
        tb = ctable(f"{refvis}/{subt}", readonly=True, ack=False)
        tb1 = ctable(f"{newvis}/{subt}", readonly=True, ack=False)

        nrows = tb.nrows()
        nrows1 = tb1.nrows()

        tb.close()
        tb1.close()

        if nrows1!=nrows:
            defectedsubt.append(subt)
            if not nrows==0:
                print(subt,nrows,nrows1,nrows1/nrows)
            else:
                print(subt,nrows,nrows1,'inf')
    return defectedsubt


def read_gain(vis, query=''):

    orig_tb = ctable(f"{vis}/GAIN_CURVE", readonly=True, ack=False)
    if query:
        tb = orig_tb.query(query)
    else:
        tb = orig_tb
    anid,feedid,spwid,time,interval,typ,numpoly,gain,sens = [tb.getcol(col) for col in ['ANTENNA_ID','FEED_ID','SPECTRAL_WINDOW_ID','TIME','INTERVAL','TYPE','NUM_POLY','GAIN','SENSITIVITY']]
    data = {
        'anid':anid,'feedid':feedid,'spwid':spwid,'time':time,'interval':interval,'typ':typ,'numpoly':numpoly,'gain':gain.T,'sens':sens.T,
    }
    tb.close()
    if tb is not orig_tb:
        orig_tb.close()
    return pl.DataFrame(data=data)

def read_antenna(vis, query=''):

    orig_tb = ctable(f"{vis}/ANTENNA", readonly=True, ack=False)
    if query:
        tb = orig_tb.query(query)
    else:
        tb = orig_tb
    offs, pos, typ, dishdiam, flag, mount, name, station = [tb.getcol(col) for col in ['OFFSET','POSITION', 'TYPE', 'DISH_DIAMETER', 'FLAG_ROW', 'MOUNT', 'NAME', 'STATION']]

    data = {
        'offs':offs.T, 'pos':pos.T, 'typ':typ, 'dishdiam':dishdiam, 'flag':flag, 'mount':mount, 'name':name, 'station':station,
    }
    tb.close()
    if tb is not orig_tb:
        orig_tb.close()
    return pl.DataFrame(data=data)

def read_weather(vis, query=''):

    orig_tb = ctable(f"{vis}/WEATHER", readonly=True, ack=False)
    if query:
        tb = orig_tb.query(query)
    else:
        tb = orig_tb
    anid, interval, time, dewpoint, h2o, ionose, pres, temp, winddir, windspeed = [tb.getcol(col) for col in ['ANTENNA_ID','INTERVAL','TIME','DEW_POINT','H2O','IONOS_ELECTRON','PRESSURE','TEMPERATURE','WIND_DIRECTION','WIND_SPEED']]
    tb.close()
    if tb is not orig_tb:
        orig_tb.close()

    data = {
        'anid':anid, 'interval':interval, 'time':time, 'dewpoint':dewpoint, 'h2o':h2o, 'ionose':ionose, 'pres':pres, 'temp':temp, 'winddir':winddir, 'windspeed':windspeed
    }

    return pl.DataFrame(data=data)

def read_syscal(vis, query=''):

    orig_tb = ctable(f"{vis}/SYSCAL", readonly=True, ack=False)
    if query:
        tb = orig_tb.query(query)
    else:
        tb = orig_tb

    anid,feedid,interval,spwid,time,tsys = [tb.getcol(col) for col in ['ANTENNA_ID', 'FEED_ID', 'INTERVAL', 'SPECTRAL_WINDOW_ID', 'TIME', 'TSYS']]
    tb.close()
    if tb is not orig_tb:
        orig_tb.close()

    data = {
        'anid' : anid,
        'feedid' : feedid,
        'interval' : interval,
        'spwid' : spwid,
        'time' : time,
        'tsys1' : tsys[0],
    }

    if len(tsys)>1:
        data['tsys2'] = tsys[1]


    return pl.DataFrame(data=data)


def read_phasecal(vis, query=''):
    orig_tb = ctable(f"{vis}/PHASE_CAL", readonly=True, ack=False)
    if query:
        tb = orig_tb.query(query)
    else:
        tb = orig_tb

    anid,feedid,spwid,time,interval,num_tones,tonefreq, phcal, cable_cal = [tb.getcol(col) for col in ['ANTENNA_ID','FEED_ID','SPECTRAL_WINDOW_ID','TIME', 'INTERVAL','NUM_TONES','TONE_FREQUENCY','PHASE_CAL','CABLE_CAL']]
    tb.close()
    if tb is not orig_tb:
        orig_tb.close()

    data = {
        'anid' : anid,
        'feedid' : feedid,
        'interval' : interval,
        'spwid' : spwid,
        'time' : time,
        'num_tones': num_tones,
        'cable_cal': cable_cal,
        'phcalr':phcal.T.real,
        'phcali':phcal.T.imag,
        'tonefreqr':tonefreq.T.real,
        'tonefreqi':tonefreq.T.imag

    }
    return pl.DataFrame(data=data)


def fix_duplicatedrows(refvis, newvis, nomodify=True):
    """
    TODO: not tested with the readonly.
    """
    tb = ctable()
    dic_subts    =  verifysubt_byeachelem(refvis, newvis)
    dupl_removed = 0
    tobe = "to be" if nomodify else " are"
    for subt, dic_subt in dic_subts.items():
        if dic_subt['duplicate'] and dic_subt['niter']>1:
            if not dupl_removed: print("...found duplicates")
            dupr = dic_subt['dubplicate_row']
            dupr = dupr[0]-1,dupr[1]-1
            dupr = list(range(*dupr))
            print("\t",subt, "rows", (dupr[0], dupr[-1]))
            dupl_removed+=1

            tb = ctable(f"{newvis}/{subt}", readonly=nomodify, ack=False)
            if not nomodify:
                tb.removerows(dupr)
                tb.flush()
            tb.close()

    ndupl = "No" if not dupl_removed else str(dupl_removed)
    print(f"{ndupl} duplicates {tobe} removed!")
