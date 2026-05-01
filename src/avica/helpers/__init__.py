from pathlib import Path
import os, ast
from os import path, makedirs
from pyvirtualdisplay import Display
import requests
import pyvo as vo

def vlba_tap_query(target_name='', sel='TOP 5 s_ra,s_dec,access_url', where='', table='tap_schema.obscore'):
    service =vo.dal.TAPService("https://data-query.nrao.edu/tap")
    _wh = f"""WHERE target_name='{target_name}'""" if target_name else f"""WHERE {where}"""
    q = f"""
    SELECT {sel}
    FROM {table}
    """ + _wh
    print(q)
    result = service.search(q)
    return result


def query_vlba(proj,fits,target_name):
    return vlba_tap_query(
    sel='DISTINCT TOP 10 s_ra,s_dec,freq_max,instrument_name,project_code,access_url,pol_states',
    where=f"project_code='{proj}' AND instrument_name='VLBA' AND (access_url LIKE  '%{fits}%') AND target_name='{target_name}'"
    )

def get_functionnames(modulefile=None,module=None, match=''):
    """
    return a list of function names from a given file or ast module object.
    import glob
        from avica.helpers import get_functionnames
        for fl in glob.glob(__path__[0]+'/fits/*py'):
            print(get_functionnames(modulefile=fl,))
    """
    if modulefile is not None:
        with open(modulefile) as f:
            module=ast.parse(f.read())

    functiondefs=[]
    for elem in module.body:
        if isinstance(elem,ast.FunctionDef):
            if match in elem.name:functiondefs.append(elem.name)
    return functiondefs


def J2000_toB1920(s):
    from astropy.coordinates import SkyCoord
    c = SkyCoord.from_name(s, frame='fk5')
    print(c)

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
