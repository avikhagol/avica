# from casatools import table, msmetadata
from pathlib import Path
from os import path, makedirs
from pyvirtualdisplay import Display
import numpy as np
from matplotlib import pyplot as plt
from matplotlib import rcParams
from astropy.time import Time
from sklearn.cluster import DBSCAN

import base64, io
from scipy.spatial import distance
from pandas import DataFrame as df

rcParams["figure.dpi"]=240
rcParams['lines.markersize'] = 0.3



def save_fig(plt, fig, kind='base64', output='output.jpg'):
    
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
        if not path.exists('output'):
            makedirs('output')
        newPath = 'output/'+output
        opt = newPath
        if path.exists(newPath):
            numb = 1
            while path.exists(newPath):
                newPath = "{0}_{2}{1}".format(
                    *path.splitext(opt) + (numb,))
                try :
                    if path.exists(newPath):
                        numb += 1 
                except:
                    pass               
        fig.savefig(newPath, format=kind, bbox_inches='tight',
                    pad_inches=0)
        print("saved {}".format(newPath))
        plt.close()
        return newPath

def pl_x_y(x, y, xlabel='', ylabel='', kind='plot', output='output.png'):
    fig,ax0 = plt.subplots(1,1, figsize=(15,12))
    ax0.set_xlabel(xlabel)
    ax0.set_ylabel(ylabel)
    ax0.scatter(x, y, c='blue', marker=',')
    plt.title(Path(output).stem)
    save_fig(plt, fig, kind=kind, output=output)

def pl_dbscan(XY, labels, db, xlabel='Amp', ylabel='Phase (deg)',idx_baseline=None, kind='plot', output='output.png'):
    unique_labels = set(labels)
    core_samples_mask = np.zeros_like(labels, dtype=bool)
    core_samples_mask[db.core_sample_indices_] = True
    if not idx_baseline is None:
        core_samples_mask = core_samples_mask[idx_baseline]
        XY, labels = XY[idx_baseline], labels[idx_baseline]
        
    colors = [plt.cm.Spectral(each) for each in np.linspace(0, 1, len(unique_labels))]
    fig,ax0 = plt.subplots(1,1, tight_layout=True)
    ax0.set_xlabel(xlabel)
    ax0.set_ylabel(ylabel)
    for k, col in zip(unique_labels, colors):
        if k == -1:
            # Black used for noise.
            col = [0, 0, 0, 1]
            markersize=1
        else:
            markersize=6
        class_member_mask = labels == k
        
    #    For the non noisy data
        xy = XY[class_member_mask & core_samples_mask]
        ax0.plot(
            xy[:, 0],
            xy[:, 1],
            "o",
            markerfacecolor=tuple(col),
            markersize=1,
            linewidth=0,
                )

    #    For the noise
        xy = XY[class_member_mask & ~core_samples_mask]
        ax0.plot(
            xy[:, 0],
            xy[:, 1],
            "o",
            markerfacecolor=tuple(col),
            markersize=1,
                )

        plt.title(f"{output}")
        
    save_fig(plt, fig, kind=kind, output=output)

def labels_percent(labels):
    label_perc = {}
    total_pts = len(labels)
    unique_labels = set(labels)
    for label in unique_labels:
        sel_labels = labels==label
        _perc = np.round((sum(sel_labels)/total_pts)*100,2)
        label_perc[label+1] = _perc
    return label_perc

def calc_scatter(arr, axis=0):
    arr_Q3 = np.quantile(arr, 0.75, axis=axis)
    arr_Q1 = np.quantile(arr, 0.25, axis=axis)

    arr_scatter      =  np.round(((arr_Q3 - arr_Q1)/(arr_Q3 + arr_Q1))*100, 2)
    
    return arr_scatter

def est_scatter(labels,  XY_normalised, xlabel, ylabel):
    ind_label_good      =   [False]*len(labels)
    for label in set(labels):
        
        ind_labelled    =   labels==label
        perc_dict       =   labels_percent(labels)
        
        X           =   XY_normalised[ind_labelled].T[0]
        Y           =   XY_normalised[ind_labelled].T[1]
        
        
        X_scatter      =   calc_scatter(X)
        Y_scatter      =   calc_scatter(Y)
        
        if perc_dict[label+1]>1:
            if label!=-1:
                ind_label_good = np.logical_or(ind_label_good, ind_labelled) # updates ind_label_good
            
            m = f"{label} ({perc_dict[label+1]} %) : "
            if not any( nl in xlabel.lower() for nl in ['freq', 'time']):
                m += f" {xlabel}_scatter:{X_scatter} %"
            if not any(nl in ylabel.lower() for nl in ['freq', 'time']):
                m += f" {ylabel}_scatter:{Y_scatter} %"
            print(m)
        
    if sum(ind_label_good):
        
        X          =   XY_normalised[ind_label_good].T[0]
        Y           =   XY_normalised[ind_label_good].T[1]

        X_scatter      =   calc_scatter(X)
        Y_scatter      =   calc_scatter(Y)
        
        m = f"\n ({np.round(sum(ind_label_good)/len(labels)*100,2)} %) :"
        if not any( nl in xlabel.lower() for nl in ['freq', 'time']):
            m += f" {xlabel}_scatter:{X_scatter} %"
        if not any(nl in ylabel.lower() for nl in ['freq', 'time']):
            m += f" {ylabel}_scatter:{Y_scatter} %"
        print(m)
        return X_scatter, Y_scatter

def xy_dbscan_scatter(target, X, Y, time, idx_baseline, xlabel, ylabel, kind='jpg', eps=0.005, min_samples=5):
    XY = np.array(list(zip(X,Y)))
    XY_normalised = np.array(list(zip(X,(Y+180)/360)))
    
    db = DBSCAN(eps=eps, # radius of the circle to find cluster member 
            min_samples=min_samples, metric='euclidean').fit(XY_normalised)
    labels = db.labels_
    sca, scp = est_scatter(labels, XY_normalised,xlabel=xlabel, ylabel=ylabel)
    
#     X, Y, time, labels = X[idx_baseline], Y[idx_baseline], time[idx_baseline], labels[idx_baseline]
    
    pl_dbscan(XY, labels, db, xlabel=xlabel, ylabel=ylabel, idx_baseline=idx_baseline, kind=kind, output=f'{target}_{ylabel}_{xlabel}_dbscan.png')
    XY, xlabel = np.array(list(zip(time,Y))), 'Time'
    pl_dbscan(XY, labels, db, xlabel=xlabel, ylabel=ylabel, idx_baseline=idx_baseline, kind=kind, output=f'{target}_{ylabel}_{xlabel}_dbscan.png')
    XY, ylabel = np.array(list(zip(time,X))), 'Amp'
    pl_dbscan(XY, labels, db, xlabel=xlabel, ylabel=ylabel, idx_baseline=idx_baseline, kind=kind, output=f'{target}_{ylabel}_{xlabel}_dbscan.png')
    
    return sca, scp

def df_baseline_by(allbaselines, annames, xyz, by='', antenna='', aid=None, maxd=None, mind=None, autocorr=True, autocorr_only=False):
    
    df_baseline = df.from_dict(dict_baseline(allbaselines, annames, xyz, autocorr=autocorr, autocorr_only=autocorr_only), columns=['distance', 'name', 'ij'], orient='index')
    if not maxd:maxd = df_baseline['distance'].max()
    if not mind:mind = df_baseline['distance'].min()
    if by=='id':
        name = annames[aid]
        by='antenna'
    if antenna: by = 'antenna'
    if by=='antenna':
        return df_baseline.loc[df_baseline['name'].str.contains(antenna)]
    if by=='distance':
        return df_baseline.loc[list(df_baseline['distance']<maxd) or list(df_baseline['distance']>mind)]
    return df_baseline

def dict_baseline(allbaselines, annames, xyz, autocorr=False, autocorr_only=False):
    dict_baseline={}

    for i,an1 in enumerate(annames):
            for j,an2 in enumerate(annames):
                an_condition = an1!=an2 or autocorr if not autocorr_only else an1==an2
                if an_condition :
        #             print(xyz[i],xyz[j])
                    d=distance.euclidean(xyz[i],xyz[j])*.001
                    baseline_label=f"{an1}-{an2}"
                    ij = [i,j]
                    baseline_id=(ij[0]+1)*256+(ij[1]+1) # 
    #                 print(baseline_id, baseline_label)
                    if baseline_id in allbaselines and not baseline_id in dict_baseline:
                        dict_baseline[baseline_id]=(d,baseline_label, ij)
                    
    return dict_baseline


def pl_diag(target, amp, phase, time, idx_baseline, idx_sel=None, kind='jpg', eps=0.005, min_samples=5):
    if idx_sel:
        amp, phase, time, idx_baseline = amp[idx_sel], phase[idx_sel], time[idx_sel], idx_baseline[idx_sel]
    pl_x_y(amp, phase,xlabel='Amp', ylabel='Phase (deg)', kind=kind, output=f'{target}_ph_amp.png')
    pl_x_y(time, phase, xlabel='Time', ylabel='Phase (deg)', kind=kind, output=f'{target}_ph_time.png')
    pl_x_y(time, amp, xlabel='Time', ylabel='Amp', kind=kind, output=f'{target}_amp_time.png')    
    return xy_dbscan_scatter(target, amp, phase, time=time, idx_baseline=idx_baseline, xlabel='Amp', ylabel='Phase(deg)', kind=kind, eps=eps, min_samples=min_samples)

