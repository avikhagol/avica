from pathlib import Path
import os
from os import path, makedirs
from pyvirtualdisplay import Display
from casatools import logsink

vascolog=logsink('vasco.log')
vascolog.setlogfile='vasco.log'
vascolog.setglobal(True)


def genplotms(vis, suffix='',kind='plot',w=None,h=None,z=1.5, **kwargs):
    """"
    This helper script can be used with jupyter notebook to create plots using plotms
    """
    from casaplotms import plotms
    
    params={'xaxis':'u', 'yaxis':'v'}
    params.update(kwargs)
    xaxis,yaxis=params['xaxis'],params['yaxis']
    
    if w is None:w=4096
    if h is None:h=2880
    
    with Display(visible=False,size=(w,h)) as disp:
    
        if z: w,h=int(w/z),int(h/z)
                
        print('plotms start....')
        plotfolder='plots/'
        
        if not path.exists(plotfolder):
            try:
                oumask = os.umask(0)
                makedirs(plotfolder)
            except:
                os.umask(oumask)
                makedirs(plotfolder, 777)
        stem=Path(vis).stem
        plotfile=plotfolder+f'{yaxis}_{xaxis}_{stem}_{suffix}.jpg'
        retplot=plotms(vis=vis, showgui=False, 
            plotfile=plotfile,width=int(w),height=int(h),
            overwrite=True, clearplots=True,
            highres=False, 
            customsymbol=True, symbolshape='square',flaggedsymbolshape='square',
            xaxisfont=22,yaxisfont=22,titlefont=22,
            **kwargs)
        print('..stopping')
        
    if kind!='plot':
        return plotfile
    else:
        from IPython.display import display as Idisplay, Image as Iimg
        Idisplay(Iimg(plotfile))