import io
from os import path, makedirs
import base64
from matplotlib import pyplot as plt
from pathlib import Path
import numpy as np


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

def pl_dbscan(XY, labels, db, xlabel='Amp', ylabel='Phase (deg)', kind='plot', output='output.png'):
    unique_labels = set(labels)
    core_samples_mask = np.zeros_like(labels, dtype=bool)
    core_samples_mask[db.core_sample_indices_] = True

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

    