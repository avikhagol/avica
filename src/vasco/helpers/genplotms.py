###### from casaplotms import plotms

from pathlib import Path
import os
from os import path, makedirs
from pyvirtualdisplay import Display
from IPython.display import display as Idisplay, Image as Iimg
from casaplotms import plotms

def genplotms(vis, suffix='',kind='plot',w=None,h=None,z=1.5, **kwargs):
    """"
    This helper script can be used with jupyter notebook to create plots using plotms
    """
    params={'xaxis':'u', 'yaxis':'v'}
    params.update(kwargs)
    xaxis,yaxis=params['xaxis'],params['yaxis']
    
    if w is None:w=4096
    if h is None:h=2880
    
    display = Display(visible=0,size=(w,h))
    
    if z: w,h=int(w/z),int(h/z)
    
    display.start()
    
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
    display.stop()
    if kind!='plot':
        return plotfile
    else:
        Idisplay(Iimg(plotfile))
#         return Idisplay(Iimg(retplot))