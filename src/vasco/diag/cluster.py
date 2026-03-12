import numpy as np
from . import pl_scatter

class ClusterStats:
    def __init__(self, axs_df, x_labels, y_labels, eps=0.005, n_cores=15, kind='png', autocorr=False, prefix=''):
        self.axs_df = axs_df
        self.x_labels = x_labels
        self.y_labels = y_labels
        self.eps = eps
        self.n_cores = n_cores
        self.kind = kind
        self.autocorr = autocorr
        self.prefix = prefix
        
    def pl_summary(self,):
        if not self.autocorr:
            axs_df = self.axs_df.loc[self.axs_df['an1']!=self.axs_df['an2']]
        print("plotting...")
        dic_pl_scatter={
            'x_labels':[ 'time', 'time'],
            'y_labels':[ 'amp (Jy)', 'phase (deg)'],
            'color_axs':'uvdist',
            'cmap':'jet',
            'select':'*',
        }
        
        output=f"{self.prefix}_vs_time.jpg"
        pl_scatter(axs_df, kind=self.kind, output=output, **dic_pl_scatter)

        dic_pl_scatter={
            'x_labels':[ 'uvdist (λ)', 'uvdist (λ)'],
            'y_labels':[ 'amp (Jy)', 'phase (deg)'],
            'color_axs':'an1',
            'cmap':'jet',
            'select':'*',
        }
        
        output=f"{self.prefix}_vs_uvdist.jpg"
        pl_scatter(axs_df, kind=self.kind, output=output, **dic_pl_scatter)
        dic_pl_scatter={
            'x_labels':['amp (Jy)'],
            'y_labels':['phase (deg)'],
            'color_axs':'uvdist',
            'cmap':'jet',
        }
        
        output=f"{self.prefix}_ph_vs_amp.jpg"
        pl_scatter(axs_df, kind=self.kind, output=output, **dic_pl_scatter)
        
    def pl_diag(self,):
        if not self.autocorr:
            axs_df = self.axs_df.loc[self.axs_df['an1']!=self.axs_df['an2']]
        else:
            axs_df = self.axs_df
        

        ap_normalised = np.column_stack((axs_df['amp'], (axs_df['phase'] + 180) / 360,))
        
        min_samples=int(np.log(len(ap_normalised))/2)
        if min_samples < 5: min_samples=5
        labels = get_labels_dbscan(ap_normalised, self.eps, min_samples, n_jobs=self.n_cores)
        
        
        axs_df_scatter = calcscatter_fromlabels_df(axs_df, labels, 'amp', 'phase')
        
        dic_pl_scatter={
            'x_labels':['amp (Jy)'],
            'y_labels':['phase (deg)'],
            'color_axs':'labels',
            'cmap':'jet',
        }
        
        output=f"{self.prefix}_ph_vs_amp_dbscan.jpg"
        pl_scatter(axs_df_scatter, kind=self.kind, output=output, **dic_pl_scatter)

        dic_pl_scatter={
            'x_labels':['time', 'time'],
            'y_labels':[ 'amp (Jy)', 'phase (deg)'],
            'color_axs':'labels',
            'cmap':'jet',
        }
        
        output=f"{self.prefix}_vs_time_dbscan.jpg"
        pl_scatter(axs_df_scatter, kind=self.kind, output=output, **dic_pl_scatter)
        

        dic_pl_scatter={
            'x_labels':['uvdist (λ)', 'uvdist (λ)'],
            'y_labels':[ 'amp (Jy)', 'phase (deg)'],
            'color_axs':'labels',
            'cmap':'jet',
        }
        
        output=f"{self.prefix}_vs_uvdist_dbscan.jpg"
        pl_scatter(axs_df_scatter, kind=self.kind, output=output, **dic_pl_scatter)
        
        good_scatter_dic = stat_gooddata(axs_df_scatter, pop_perc=0.8)
        big_group_scatter = good_scatter_dic[good_scatter_dic['good_labels'][0]] if 'good_labels' in good_scatter_dic else np.nan
        if np.nan == big_group_scatter:
            print("No good clusters!")
        return big_group_scatter
        
def get_labels_dbscan(data, eps, min_samples, n_jobs=15):
    from sklearn.cluster import DBSCAN
    db = DBSCAN(eps=eps, # radius of the circle to find cluster member 
        min_samples=min_samples, metric='euclidean', n_jobs=n_jobs).fit(data)
    return db.labels_

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

