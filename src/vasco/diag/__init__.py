from os import path, makedirs
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib import rcParams
from astropy.time import Time
from pathlib import Path
import base64, io
from pandas import DataFrame as df
from matplotlib import cm

DPI = rcParams["figure.dpi"]= 360
rcParams['lines.markersize'] = 0.2
plt.rcParams['font.size'] = 6
plt.rcParams['font.family'] = 'sans-serif' 

def pl_diag(axs_df, eps=0.005, n_cores=15, kind='png', autocorr=False, prefix=''):
    if not autocorr:
        axs_df = axs_df.loc[axs_df['an1']!=axs_df['an2']]

    print("plotting...")
    dic_pl_scatter={
        'x_labels':[ 'time', 'time'],
        'y_labels':[ 'amp (Jy)', 'phase (deg)'],
        'color_axs':'uvdist',
        'cmap':'jet',
        'select':'*',
    }
    
    output=f"{prefix}_vs_time.jpg"
    pl_scatter(axs_df, kind=kind, output=output, **dic_pl_scatter)

    dic_pl_scatter={
        'x_labels':[ 'uvdist (λ)', 'uvdist (λ)'],
        'y_labels':[ 'amp (Jy)', 'phase (deg)'],
        'color_axs':'an1',
        'cmap':'jet',
        'select':'*',
    }
    
    output=f"{prefix}_vs_uvdist.jpg"
    pl_scatter(axs_df, kind=kind, output=output, **dic_pl_scatter)
    dic_pl_scatter={
        'x_labels':['amp (Jy)'],
        'y_labels':['phase (deg)'],
        'color_axs':'uvdist',
        'cmap':'jet',
    }
    
    output=f"{prefix}_ph_vs_amp.jpg"
    pl_scatter(axs_df, kind=kind, output=output, **dic_pl_scatter)

    ap_normalised = np.column_stack((axs_df['amp'], (axs_df['phase'] + 180) / 360,))
    # eps=find_eps(ap_normalised)
    #     Find clusters
    min_samples=int(np.log(len(ap_normalised))/2)
    if min_samples < 5: min_samples=5
    labels = get_labels_dbscan(ap_normalised, eps, min_samples, n_jobs=n_cores)
    
    #     calculating scatter
    axs_df_scatter = calcscatter_fromlabels_df(axs_df, labels, 'amp', 'phase')
    
    #     plotting and printing results
    dic_pl_scatter={
        'x_labels':['amp (Jy)'],
        'y_labels':['phase (deg)'],
        'color_axs':'labels',
        'cmap':'jet',
    }
    
    output=f"{prefix}_ph_vs_amp_dbscan.jpg"
    pl_scatter(axs_df_scatter, kind=kind, output=output, **dic_pl_scatter)

    dic_pl_scatter={
        'x_labels':['time', 'time'],
        'y_labels':[ 'amp (Jy)', 'phase (deg)'],
        'color_axs':'labels',
        'cmap':'jet',
    }
    
    output=f"{prefix}_vs_time_dbscan.jpg"
    pl_scatter(axs_df_scatter, kind=kind, output=output, **dic_pl_scatter)
    

    dic_pl_scatter={
        'x_labels':['uvdist (λ)', 'uvdist (λ)'],
        'y_labels':[ 'amp (Jy)', 'phase (deg)'],
        'color_axs':'labels',
        'cmap':'jet',
    }
    
    output=f"{prefix}_vs_uvdist_dbscan.jpg"
    pl_scatter(axs_df_scatter, kind=kind, output=output, **dic_pl_scatter)
    
    good_scatter_dic = stat_gooddata(axs_df_scatter, pop_perc=0.8)
    big_group_scatter = good_scatter_dic[good_scatter_dic['good_labels'][0]] if 'good_labels' in good_scatter_dic else np.nan
    if np.nan == big_group_scatter:
        print("No good clusters!")
    return big_group_scatter


def find_eps(normalised_data):

    from sklearn.neighbors import NearestNeighbors
    from kneed import KneeLocator
    # Compute k-nearest neighbors (k=5)
    neighbors = NearestNeighbors(n_neighbors=5)
    neighbors_fit = neighbors.fit(normalised_data)
    distances, indices = neighbors_fit.kneighbors(normalised_data)

    # Sort distances to the k-th nearest neighbor
    distances = np.sort(distances[:, -1])

    # Use KneeLocator to find the knee point
    kneedle = KneeLocator(range(len(distances)), distances, curve="convex", direction="increasing", interp_method="polynomial", polynomial_degree=8)
    knee_index = kneedle.knee
    knee_value = distances[knee_index]

    # Plot the K-distance graph
    fig, ax = plt.subplots(1, 1)
    ax.plot(distances, label="5th Nearest Neighbor Distance")
    ax.scatter(knee_index, knee_value, color="red", s=20, zorder=3, label=f"Knee at {knee_value:.4f}")
    
    ax.set_xlabel("Points sorted by distance")
    ax.set_ylabel("5th Nearest Neighbor Distance")
    ax.set_title("K-Distance Plot for DBSCAN")
    ax.legend()
    
    save_fig(plt, fig, kind='jpg', output='KneeFind.jpg')
    
    return knee_value

def get_avg_amp_phase(data, weight):
    """
    averaged over all SPWs/IFs,
    
    Returns
    :amp:    (np.ndarray)
            Averaged amplitude over all SPWs (assuming one band).
            
    :phase:  (np.ndarray)
            Averaged phase over all SPWs (assuming one band).

    """
    amp     = np.sqrt(data.real.T*data.real.T + data.imag.T*data.imag.T)
    avg_amp = np.nanmean(amp.T, axis=0)[0]#*weight[0]
    avg_phase= np.nanmean(np.rad2deg(np.arctan2(data.imag, data.real)), axis=0)[0]
    return avg_amp, avg_phase

def pl_imshow(imgs, titles, xlabels, ylabels, extents=[None], kind='jpg', cmap='Purples'):
    fig, ax = plt.subplots(1,len(imgs))
    if len(imgs)<2: ax = [ax]
    for i,img in enumerate(imgs):
        ax[i].imshow(img, cmap=cmap, origin='lower', 
                     extent=extents[i], 
                     aspect='auto')
        ax[i].set_xlabel(xlabels[i])
        ax[i].set_ylabel(ylabels[i])
        ax[i].set_title(titles[i])
    save_fig(plt, fig, kind=kind)

def get_labels_dbscan(data, eps, min_samples, n_jobs=15):
    from sklearn.cluster import DBSCAN
    db = DBSCAN(eps=eps, # radius of the circle to find cluster member 
        min_samples=min_samples, metric='euclidean', n_jobs=n_jobs).fit(data)
    return db.labels_

def calcscatter_fromlabels_df(axs_df, labels, x_label, y_label):    
    tot_labels = len(labels)
    unique_labels = np.unique(labels)
    axs_df['labels'] = labels # since the labels is in the exact sequence as the provided data no need to map
    good_labels={}
    other_labels={}
    
    for label in unique_labels:
        idx_label = labels==label
        perc_label = np.round((sum(idx_label)/tot_labels)*100,2)
        
        if 'phase' in y_label:
            y = (axs_df[y_label]+180)/360
        else:
            y = axs_df[y_label]
        x_scatter, y_scatter = calc_scatter(axs_df[x_label][idx_label]), calc_scatter(y[idx_label])
        axs_df.loc[idx_label,f'{x_label}_scatter'] = x_scatter
        axs_df.loc[idx_label,f'{y_label}_scatter'] = y_scatter
    return axs_df

def pl_scatter(vis_df, x_labels, y_labels, color_axs, cmap, select='*', kind='plot', output='output.jpg', new=True, fill_colorbars=None):
    if select and not '*' in select:
        vis_df = vis_df.query(select)
    
    unique_labels = vis_df[color_axs].unique()
    
    if color_axs=='labels':
        vis_df[color_axs] = vis_df[color_axs].where(vis_df[color_axs] != -1, vis_df[color_axs].max() + 10)
    
    if fill_colorbars:
        mapping = {name: i for i, name in enumerate(fill_colorbars)}
        vis_df[f"{color_axs}_str"] = vis_df[color_axs].map(mapping)
        unique_labels = np.array(list(mapping.values()))
        tick_labels = tick_label_names = fill_colorbars
    else:
        unique_labels = np.sort(vis_df[color_axs].unique())
        tick_labels = unique_labels[::max(1, len(unique_labels)//10)] # at most 10 ticks
        
        if 'time' in color_axs:
            tick_label_names = [f"{Time(label, format='decimalyear').datetime.strftime('%H:%M:%S')}" for label in tick_labels]
            tick_label_names[0] = f"{tick_label_names[0]}\n\n{Time(tick_labels[0], format='decimalyear').datetime.strftime('%Y-%m-%d')}"
        else:
            tick_label_names = [f"{label:.1e}" if len(str(label)) > 4 else f"{label}" for label in tick_labels]
            
        
    norm = plt.Normalize(vmin=unique_labels.min(), vmax=unique_labels.max())
    cmap = plt.get_cmap(cmap, len(unique_labels))        
    if new:
        fig, ax = plt.subplots(len(y_labels),1, layout='constrained')
    else:
        fig, ax = plt.subplots(1,len(x_labels), layout='constrained')
    if len(x_labels)<2: ax = [ax]
    for i,(xlabel,ylabel) in enumerate(zip(x_labels, y_labels)):
        xlabelv, ylabelv = xlabel.split(' ')[0], ylabel.split(' ')[0]
        xlabel, ylabel = xlabelv.upper()+ ' '.join(xlabel.split(' ')[1:]), ylabelv.upper() + ' '.join(ylabel.split(' ')[1:])
        title = f"{ylabel}_{xlabel}"
        ax[i].scatter(vis_df[xlabelv],vis_df[ylabelv], 
                        c=vis_df[color_axs], 
                        cmap=cmap, norm=norm, marker=',',
                          label=color_axs,
                         )
        ax[i].set_xlabel(xlabel)
        ax[i].set_ylabel(ylabel)
        ax[i].set_title(title)
    # cbar = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax[-1], shrink=0.4)
    # cbar.set_label(f"{color_axs}")
    mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(mappable, ax=ax, shrink=0.6)
    cbar.set_label(f"{color_axs}")
    
    
    # tick_locs = np.arange(len(tick_labels))
    tick_locs   = tick_labels
    cbar.set_ticks(tick_locs)
    cbar.set_ticklabels(tick_label_names)
    
#     plt.colorbar(ax=ax[0])
    save_fig(plt, fig, kind=kind, output=output)

def calc_scatter(arr, axis=0):
    arr_Q3 = np.quantile(arr, 0.75, axis=axis)
    arr_Q1 = np.quantile(arr, 0.25, axis=axis)

    arr_scatter      =  np.round(((arr_Q3 - arr_Q1)/(arr_Q3 + arr_Q1))*100, 2)
    return arr_scatter

def stat_gooddata(axs_df_field_scatter, pop_perc=0.8):
    label_grouped = axs_df_field_scatter.groupby('labels')

    group_sizes = label_grouped.size()
    total_size = len(axs_df_field_scatter)
    group_percentages = (group_sizes / total_size) * 100


    print(f"\t % data\t [amp, phase] % scatter")
    sorted_groups = group_percentages.sort_values(ascending=False)
    noise_group = axs_df_field_scatter['labels'].max()
    
    # Print percentage, amp_scatter, and phase_scatter for each group
    good_group = {}
    for group_name in sorted_groups.index:
        group_data = axs_df_field_scatter[axs_df_field_scatter['labels'] == group_name]
        if group_percentages[group_name]>pop_perc:
            if group_name != noise_group:
                good_group[str(group_name)]={'scatter':list(group_data[['amp_scatter', 'phase_scatter']].values[0]), 'perc_data':np.round(group_percentages[group_name], 3)}
                if 'good_labels' not in good_group:
                    good_group['good_labels']=[]
                good_group['good_labels'].append(str(group_name))    
                    # good_group['good_labels']={}
                # good_group['good_labels'][str(group_name)] = group_percentages[group_name]
                print(f"Group: {group_name} | {group_percentages[group_name]:.2f}%","\t", group_data[['amp_scatter', 'phase_scatter']].values[0])
            else:
                print(f"Noise: {group_name} | {group_percentages[group_name]:.2f}%","\t", group_data[['amp_scatter', 'phase_scatter']].values[0])
            print("------")
    
    return good_group

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
        plt.close("all")
        return newPath

# def pl_x_y(x, y, xlabel='', ylabel='', kind='plot', output='output.png'):
#     fig,ax0 = plt.subplots(1,1, figsize=(15,12))
#     ax0.set_xlabel(xlabel)
#     ax0.set_ylabel(ylabel)
#     ax0.scatter(x, y, c='blue', marker=',')
#     plt.title(Path(output).stem)
#     save_fig(plt, fig, kind=kind, output=output)

# def pl_dbscan(XY, labels, db, xlabel='Amp', ylabel='Phase (deg)',idx_baseline=None, kind='plot', output='output.png'):
#     unique_labels = set(labels)
#     core_samples_mask = np.zeros_like(labels, dtype=bool)
#     core_samples_mask[db.core_sample_indices_] = True
#     if not idx_baseline is None:
#         core_samples_mask = core_samples_mask[idx_baseline]
#         XY, labels = XY[idx_baseline], labels[idx_baseline]
        
#     colors = [plt.cm.Spectral(each) for each in np.linspace(0, 1, len(unique_labels))]
#     fig,ax0 = plt.subplots(1,1, tight_layout=True)
#     ax0.set_xlabel(xlabel)
#     ax0.set_ylabel(ylabel)
#     for k, col in zip(unique_labels, colors):
#         if k == -1:
#             # Black used for noise.
#             col = [0, 0, 0, 1]
#             markersize=1
#         else:
#             markersize=6
#         class_member_mask = labels == k
        
#     #    For the non noisy data
#         xy = XY[class_member_mask & core_samples_mask]
#         ax0.plot(
#             xy[:, 0],
#             xy[:, 1],
#             "o",
#             markerfacecolor=tuple(col),
#             markersize=1,
#             linewidth=0,
#                 )

#     #    For the noise
#         xy = XY[class_member_mask & ~core_samples_mask]
#         ax0.plot(
#             xy[:, 0],
#             xy[:, 1],
#             "o",
#             markerfacecolor=tuple(col),
#             markersize=1,
#                 )

#         plt.title(f"{output}")
        
#     save_fig(plt, fig, kind=kind, output=output)

# def labels_percent(labels):
#     label_perc = {}
#     total_pts = len(labels)
#     unique_labels = set(labels)
#     for label in unique_labels:
#         sel_labels = labels==label
#         _perc = np.round((sum(sel_labels)/total_pts)*100,2)
#         label_perc[label+1] = _perc
#     return label_perc

# def calc_scatter(arr, axis=0):
#     arr_Q3 = np.quantile(arr, 0.75, axis=axis)
#     arr_Q1 = np.quantile(arr, 0.25, axis=axis)

#     arr_scatter      =  np.round(((arr_Q3 - arr_Q1)/(arr_Q3 + arr_Q1))*100, 2)
    
#     return arr_scatter

# def est_scatter(labels,  XY_normalised, xlabel, ylabel):
#     ind_label_good      =   [False]*len(labels)
#     for label in set(labels):
        
#         ind_labelled    =   labels==label
#         perc_dict       =   labels_percent(labels)
        
#         X           =   XY_normalised[ind_labelled].T[0]
#         Y           =   XY_normalised[ind_labelled].T[1]
        
        
#         X_scatter      =   calc_scatter(X)
#         Y_scatter      =   calc_scatter(Y)
        
#         if perc_dict[label+1]>1:
#             if label!=-1:
#                 ind_label_good = np.logical_or(ind_label_good, ind_labelled) # updates ind_label_good
            
#             m = f"{label} ({perc_dict[label+1]} %) : "
#             if not any( nl in xlabel.lower() for nl in ['freq', 'time']):
#                 m += f" {xlabel}_scatter:{X_scatter} %"
#             if not any(nl in ylabel.lower() for nl in ['freq', 'time']):
#                 m += f" {ylabel}_scatter:{Y_scatter} %"
#             print(m)
        
#     if sum(ind_label_good):
        
#         X          =   XY_normalised[ind_label_good].T[0]
#         Y           =   XY_normalised[ind_label_good].T[1]

#         X_scatter      =   calc_scatter(X)
#         Y_scatter      =   calc_scatter(Y)
        
#         m = f"\n ({np.round(sum(ind_label_good)/len(labels)*100,2)} %) :"
#         if not any( nl in xlabel.lower() for nl in ['freq', 'time']):
#             m += f" {xlabel}_scatter:{X_scatter} %"
#         if not any(nl in ylabel.lower() for nl in ['freq', 'time']):
#             m += f" {ylabel}_scatter:{Y_scatter} %"
#         print(m)
#         return X_scatter, Y_scatter

# def xy_dbscan_scatter(target, X, Y, time, idx_baseline, xlabel, ylabel, kind='jpg', eps=0.005, min_samples=5):
#     XY = np.array(list(zip(X,Y)))
#     XY_normalised = np.array(list(zip(X,(Y+180)/360)))
    
#     db = DBSCAN(eps=eps, # radius of the circle to find cluster member 
#             min_samples=min_samples, metric='euclidean').fit(XY_normalised)
#     labels = db.labels_
#     sca, scp = est_scatter(labels, XY_normalised,xlabel=xlabel, ylabel=ylabel)
    
# #     X, Y, time, labels = X[idx_baseline], Y[idx_baseline], time[idx_baseline], labels[idx_baseline]
    
#     pl_dbscan(XY, labels, db, xlabel=xlabel, ylabel=ylabel, idx_baseline=idx_baseline, kind=kind, output=f'{target}_{ylabel}_{xlabel}_dbscan.png')
#     XY, xlabel = np.array(list(zip(time,Y))), 'Time'
#     pl_dbscan(XY, labels, db, xlabel=xlabel, ylabel=ylabel, idx_baseline=idx_baseline, kind=kind, output=f'{target}_{ylabel}_{xlabel}_dbscan.png')
#     XY, ylabel = np.array(list(zip(time,X))), 'Amp'
#     pl_dbscan(XY, labels, db, xlabel=xlabel, ylabel=ylabel, idx_baseline=idx_baseline, kind=kind, output=f'{target}_{ylabel}_{xlabel}_dbscan.png')
    
#     return sca, scp

# def df_baseline_by(allbaselines, annames, xyz, by='', antenna='', aid=None, maxd=None, mind=None, autocorr=True, autocorr_only=False):
    
#     df_baseline = df.from_dict(dict_baseline(allbaselines, annames, xyz, autocorr=autocorr, autocorr_only=autocorr_only), columns=['distance', 'name', 'ij'], orient='index')
#     if not maxd:maxd = df_baseline['distance'].max()
#     if not mind:mind = df_baseline['distance'].min()
#     if by=='id':
#         name = annames[aid]
#         by='antenna'
#     if antenna: by = 'antenna'
#     if by=='antenna':
#         return df_baseline.loc[df_baseline['name'].str.contains(antenna)]
#     if by=='distance':
#         return df_baseline.loc[list(df_baseline['distance']<maxd) or list(df_baseline['distance']>mind)]
#     return df_baseline

# def dict_baseline(allbaselines, annames, xyz, autocorr=False, autocorr_only=False):
#     dict_baseline={}

#     for i,an1 in enumerate(annames):
#             for j,an2 in enumerate(annames):
#                 an_condition = an1!=an2 or autocorr if not autocorr_only else an1==an2
#                 if an_condition :
#         #             print(xyz[i],xyz[j])
#                     d=distance.euclidean(xyz[i],xyz[j])*.001
#                     baseline_label=f"{an1}-{an2}"
#                     ij = [i,j]
#                     baseline_id=(ij[0]+1)*256+(ij[1]+1) # 
#     #                 print(baseline_id, baseline_label)
#                     if baseline_id in allbaselines and not baseline_id in dict_baseline:
#                         dict_baseline[baseline_id]=(d,baseline_label, ij)
                    
#     return dict_baseline


# def pl_diag(target, amp, phase, time, idx_baseline, idx_sel=None, kind='jpg', eps=0.005, min_samples=5):
#     if idx_sel:
#         amp, phase, time, idx_baseline = amp[idx_sel], phase[idx_sel], time[idx_sel], idx_baseline[idx_sel]
#     pl_x_y(amp, phase,xlabel='Amp', ylabel='Phase (deg)', kind=kind, output=f'{target}_ph_amp.png')
#     pl_x_y(time, phase, xlabel='Time', ylabel='Phase (deg)', kind=kind, output=f'{target}_ph_time.png')
#     pl_x_y(time, amp, xlabel='Time', ylabel='Amp', kind=kind, output=f'{target}_amp_time.png')    
#     return xy_dbscan_scatter(target, amp, phase, time=time, idx_baseline=idx_baseline, xlabel='Amp', ylabel='Phase(deg)', kind=kind, eps=eps, min_samples=min_samples)

