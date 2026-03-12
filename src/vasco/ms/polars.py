
from . import get_tb_data
import polars as pl
import numpy as np
from pathlib import Path

from typing import List

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