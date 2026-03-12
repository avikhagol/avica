import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
import matplotlib.cm as cm
from matplotlib import rcParams
import matplotlib.gridspec as gridspec
from matplotlib.colors import BoundaryNorm
import matplotlib.ticker as ticker
from pathlib import Path
import polars as pl
from os import path
import base64
import io
from vasco.diag.cluster import get_labels_dbscan, calc_scatter

from vasco.ms import get_tb_data
import polars as pl
import numpy as np
from pathlib import Path
import io, base64
from os import path

from typing import List

DPI = rcParams["figure.dpi"]= 300
rcParams['lines.markersize'] = 0.2
plt.rcParams['font.size'] = 8
plt.rcParams['font.family'] = 'sans-serif' 

# read visibilties

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

# ---- plotting library

def save_fig(plt, fig, kind='base64', output='output.jpg', dpi=300):
    
    if kind == 'base64':
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                    transparent=True, pad_inches=0)
        buf.seek(0)
        string = base64.b64encode(buf.read())
        plt.close()
        return string
    elif kind == 'plot':
        plt.show()
        return 'plotted'
    else :
        if not Path(output).parent.exists():
            Path(output).parent.mkdir()
        if Path(output).parent == Path().cwd():
            newPath = 'output/'+output
        else:
            newPath = output
        opt = newPath
        if Path(newPath).exists():
            numb = 1
            while Path(newPath).exists():
                newPath = "{0}_{2}{1}".format(
                    *path.splitext(opt) + (numb,))
                try :
                    if Path(newPath).exists():
                        numb += 1 
                except:
                    pass               
        fig.savefig(newPath, format=kind, bbox_inches='tight',
                    pad_inches=0, dpi=dpi)
        print("saved {}".format(newPath))
        plt.close()
        return newPath

def pl_scatter_iterate(df_vis, iterby="", **kwargs):
    
    df_vis_pl = df_vis
    op = kwargs['output']
    if iterby:
        if iterby=='baseline':
            
            for an1_name, an2_name in df_vis.group_by(['an1_name','an2_name']).agg().iter_rows():
                df_vis_pl = df_vis.filter(pl.col("an1_name").is_in([an1_name]) & pl.col("an2_name").is_in([an2_name]))
                kwargs['output'] = Path(op).stem + f"_{an1_name}_{an2_name}" + Path(op).suffix
                pl_scatter_polars(df_vis_pl, **kwargs)
                
        elif iterby=="scan":
            for sid, field in df_vis.group_by(['sid', 'field']).agg().iter_rows():
                df_vis_pl = df_vis.filter(pl.col("sid").is_in([sid]))
                kwargs['output'] = Path(op).stem + f"_scan{sid}_{field}" + Path(op).suffix
                pl_scatter_polars(df_vis_pl, **kwargs)
                
        elif iterby in df_vis:
            for colv in df_vis.group_by([iterby]).agg().iter_rows():
                df_vis_pl = df_vis.filter(pl.col(iterby).is_in([colv[0]]))
                kwargs['output'] = Path(op).stem + f" {iterby}{colv}" + Path(op).suffix
                pl_scatter_polars(df_vis_pl, **kwargs)

def pl_scatter_polars(vis_df, x_labels, y_labels, color_axs, cmap, select='*', kind='plot', output='output.jpg',
                         label_map=None, fill_colorbars=None, label_dict=None):
    """
    Uses polars/pandas dataframe to plot simple plots.
    """
    pl_dim = (8, 3* len(x_labels))
    
    unique_labels = vis_df[color_axs].unique()
    
    if color_axs=='labels':
        max_val = vis_df[color_axs].max() 
        new_val = (max_val+max_val*10 if max_val is not None else 0) + 999

        # The Polars way to perform conditional replacement
        vis_df = vis_df.with_columns(
            pl.when(pl.col(color_axs) == -1)
            .then(new_val)
            .otherwise(pl.col(color_axs))
            .alias(color_axs) # This overwrites the column in place
        )
    
    if fill_colorbars:
        
        mapping = {name: i for i, name in enumerate(fill_colorbars)}
        
        unique_labels   = np.array(list(mapping.values()))
        step = max(1, len(fill_colorbars) // 10) # Aim for ~10 ticks
        tick_locs = unique_labels[::step]
        
        color_col = f"{color_axs}_numeric"
        vis_df = vis_df.with_columns([
                pl.col(color_axs).replace(mapping).alias(color_col)
            ])
        step = max(1, len(fill_colorbars) // 10) 
        tick_locs = unique_labels[::step]
        
        tick_label_names = [str(fill_colorbars[i]) for i in range(0, len(fill_colorbars), step)]
        tick_labels = tick_label_names #= fill_colorbars
        
    else:
        unique_labels = np.sort(vis_df[color_axs].unique())
        
        tick_labels = unique_labels[::max(1, len(unique_labels)//10)]
        
        if 'time' in color_axs:
            tick_label_names = [f"{Time(label, format='decimalyear').datetime.strftime('%H:%M:%S')}" for label in tick_labels]
            tick_label_names[0] = f"{tick_label_names[0]}\n\n{Time(tick_labels[0], format='decimalyear').datetime.strftime('%Y-%m-%d')}"
        elif label_map:
            if label_map:
                tick_label_names = [label_map[unique_label] for unique_label in unique_labels]
        else:
            tick_label_names = [f"{label:.1e}" if len(str(label)) > 4 else f"{label}" for label in tick_labels]
        
                
        tick_locs   = tick_labels
        color_col = color_axs
    if not 'label' in color_col and not label_map:
        vmin = unique_labels.min()
    else:
        vmin = 0
    norm = plt.Normalize(vmin=vmin, vmax=unique_labels.max())
    cmap = plt.get_cmap(cmap, len(unique_labels))        
    cmap.set_under('lightgrey')
    
    sharex  = True if len(np.unique(x_labels))==1 else False
    fig, ax = plt.subplots(len(x_labels), 1, figsize=pl_dim, sharex=sharex, layout='constrained')
    if len(x_labels) < 2:  ax = [ax]
    gs1 = gridspec.GridSpec(*pl_dim)
    gs1.update(wspace=0.025, hspace=0.01)
    if not label_dict:
        label_dict = {}
    for xlabel, ylabel in zip(x_labels, y_labels):
        if not xlabel in label_dict: label_dict[xlabel] = xlabel
        if not ylabel in label_dict: label_dict[ylabel] = ylabel
            
    prevlabel = x_labels[0]
    for i, (xlabel, ylabel) in enumerate(zip(x_labels, y_labels)):
        sc = ax[i].scatter(
            vis_df[xlabel], 
            vis_df[ylabel], 
            c=vis_df[color_col],
            cmap=cmap,
            norm=norm,
            # s=0.3,  
            # alpha=0.6,
            marker=',',
            # edgecolors='none'
        )
        
        # sc = ax[i].hexbin(
        #     vis_df[xlabel].to_numpy(), 
        #     vis_df[ylabel].to_numpy(), 
        #     C=vis_df[color_col].to_numpy() if color_col else None,
        #     gridsize=300,           # Adjust for resolution
        #     cmap=cmap,#cmap_obj,
        #     norm=norm,
        #     reduce_C_function=np.mean, # Average color/cluster value in that hex
        #     mincnt=1,               # Only plot hexagons with at least 1 point
        #     edgecolors='none',
        #     linewidths=0
        # )
            
        if prevlabel==xlabel:
            ax[i-1].tick_params(labelbottom=False)
            
        if len(x_labels)>1 and i!=len(x_labels)-1: # x label handling for multiple x-labels
            if prevlabel!=xlabel:               
                thelabel = label_dict[prevlabel]
                ax[i-1].set_xlabel(thelabel)
        else:
            thelabel = label_dict[xlabel]
            ax[i].set_xlabel(thelabel)
            ax[i].tick_params(labelbottom=True)
            
        prevlabel = xlabel
        thelabel = label_dict[ylabel]
        ax[i].set_ylabel(thelabel)
        
        x_range = vis_df[xlabel].max() - vis_df[xlabel].min()
        y_range = vis_df[ylabel].max() - vis_df[ylabel].min()
        
        x_pad = 0.01 * x_range
        y_pad = 0.01 * y_range
        
        ax[i].set_xlim(vis_df[xlabel].min() - x_pad, vis_df[xlabel].max() + x_pad)
        ax[i].set_ylim(vis_df[ylabel].min() - y_pad, vis_df[ylabel].max() + y_pad)
        
        ax[i].xaxis.set_major_locator(ticker.MaxNLocator(nbins=5, prune=None))
        ax[i].yaxis.set_major_locator(ticker.MaxNLocator(nbins=5, prune=None))
        
        ans1 = vis_df['an1_name'].unique() if 'an1_name' in vis_df else ''
        ans2 = vis_df['an2_name'].unique() if 'an2_name' in vis_df else ''
        ans = "".join(ans1) + " " + "".join(ans2)
        
        ax[i].text(0.01, 0.99, ans,
                   transform=ax[i].transAxes,
                   fontsize=6, 
                   color='blue',
                   ha='left', va='top')
        
        src = " ".join(vis_df['field'].unique()) if 'field' in vis_df else ''
        ax[i].annotate(
            src,
            xy=(0.99, 0.99),
            xycoords='axes fraction',
            fontsize=6,
            ha='right',
            va='top',
            # color='gray',
        )
        
    output_title = f"{output}"
    fig.suptitle(output_title)
    mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(mappable, ax=ax, shrink=0.6)
    cbar.set_label(f"{color_axs}")
    
    cbar.set_ticks(tick_locs)
    cbar.set_ticklabels(tick_label_names)
    
    try:
        save_fig(plt, fig, kind=kind, output=output)
    except NameError:
        fig.savefig(output, dpi=300, bbox_inches='tight')
    plt.close()
    
    
# ----- Calculations

def get_labels_dbscan(data, eps, min_samples, n_jobs=15):
    from sklearn.cluster import DBSCAN
    data = np.ascontiguousarray(data, dtype=np.float32)
    db = DBSCAN(
        eps=eps, 
        min_samples=min_samples, 
        metric='euclidean', 
        algorithm='kd_tree', 
        # leaf_size=40,
        n_jobs=n_jobs,
    ).fit(data)
    
    return db.labels_
    
def calcscatter_fromlabels_df(axs_df, labels, x_label, y_label):
    if not 'labels' in axs_df:
        axs_df = axs_df.with_columns(pl.Series("labels", labels))
    if 'phase' in y_label:
        y_col = (pl.col(y_label) + 180) / 360
    else:
        y_col = pl.col(y_label)

    axs_df = axs_df.with_columns([
        
        pl.col(x_label).map_batches(calc_scatter).over("labels").alias(f"{x_label}_scatter"),
        y_col.map_batches(calc_scatter).over("labels").alias(f"{y_label}_scatter")
    ])
    
    return axs_df
    
    
def analyse_dbscan_polars(df_vis, target, eps=0.005, min_samples=5, n_jobs=15, avg=True):
    df_vis = df_vis.with_columns([
    ((pl.col("phase_corrected") + 180) / 360).alias("phase_norm"),
    (pl.col("amp_corrected")/pl.col('amp_corrected').max()).alias("amp_norm")
    ])

    if avg:
        df_pl = df_vis.group_by('time', 'uvdist','an1', 'an1_name',
                            'an2', 'an2_name', 'field', 'sid').agg(pl.col('amp_corrected', 'amp_norm', 
                                                              'phase_corrected', 'phase_norm', 
                                                              'uvdist_lambda', 'flag').mean(), pl.col('amp_corrected').std().alias('amp_std'))
    else:
        df_pl = df_vis

    mask_target = df_pl['field']==target
    ap_normalised = (
        df_pl.filter(mask_target).select([
            pl.col("amp_norm").cast(pl.Float32), 
            pl.col("phase_norm").cast(pl.Float32)
        ])
        .to_numpy()
    )
    ap_normalised = np.nan_to_num(ap_normalised, nan=0.0, copy=False)
    min_samples=int(np.log(len(ap_normalised))/2)
    if min_samples < 5: min_samples=5

    labels = get_labels_dbscan(ap_normalised, eps=eps, min_samples=min_samples, n_jobs=n_jobs)
    
    full_labels = np.full(len(df_pl), -1, dtype=np.int32)
    full_labels[mask_target] = labels
    df_pl = df_pl.with_columns(pl.Series("labels", full_labels))
    
    # axs_df_scatter = calcscatter_fromlabels_df(df_pl.filter(mask_target), labels, 'amp_norm', 'phase_norm')
    
    return df_pl

    
    

def pl_diag_ms_polars(vis, target, dcol='DATA', kind='png', **kwargs):
    from vasco.diag.polars import analyse_dbscan_polars, read_df_vis, get_tb_data, pl_scatter_iterate, pl_scatter_polars
    df_vis = read_df_vis(vis, dcol=dcol)

    meanfreq = np.mean(get_tb_data(f"{vis}/SPECTRAL_WINDOW", axs=['CHAN_FREQ']))
    wavelength = 299792458.0 / meanfreq

    df_vis = df_vis.with_columns(
        amp_corrected = pl.when(pl.col("flag") == 0)
                    .then(pl.col("amp"))
                    #   * pl.col("weight") / pl.col("weight").sum().over(pl.col("time")))
                    .otherwise(None),
        phase_corrected = pl.when(pl.col("flag") == 0)
                    .then(pl.col("phase") )
                    #   * pl.col("weight") / pl.col("weight").sum().over(pl.col("time")))
                    .otherwise(None),
        uvdist_lambda = pl.col("uvdist")  / (299792458 / meanfreq)
    )

    df_pl = analyse_dbscan_polars(df_vis, target=target, eps=0.005)
    labels = df_pl['labels']
    unique_labels = np.unique(labels)
    max_val = labels.max() 
    new_val = (max_val+max_val*10 if max_val is not None else 0) + 999

    unique_labels[unique_labels==-1]=new_val
    # calibrator = '1749+096'd.filt
    # target = 'J17111+3818'
    ans = dict(df_pl[['an1', 'an1_name']].unique().to_numpy())
    dic_pl_scatter={
            'x_labels':[ 'uvdist', 'uvdist'],
            'y_labels':[ 'amp_corrected', 'phase_corrected'],
            'label_dict':{'uvdist_lambda': 'Radial UV distance (λ)', 'amp_corrected':'Amp (Jy)','phase_corrected':'Phase(deg)' },
            'color_axs':'labels',
            'cmap':'jet',
            'kind':kind,
            'fill_colorbars':list(np.unique(unique_labels)),
            # 'iterby':'an1',
            'output':'Amp(Jy) & Phase(deg) vs Radial UV distance (λ)'
        }
    pl_scatter_polars(df_pl.filter( (pl.col('field')==target) & (pl.col('an1')!=pl.col('an2')) & (pl.col('amp_corrected')<1.54) 
                                & (pl.col('flag')==0)) ,
                  **dic_pl_scatter)