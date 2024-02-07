import glob
from collections import defaultdict
from pathlib import Path

def read_inputfile(folder,inputfile='config.inp',):
    """
    Read the input file and return a dictionary with the parameters.
    """
    params = {}
    input_folder= ''
    files=glob.glob(f'{folder}/*{inputfile}',recursive=True)
    if not files: files=glob.glob(f'{folder}/*/*{inputfile}',recursive=False)
    if not files: files=glob.glob(f'{folder}/*/*/*{inputfile}',recursive=False)
    
    if files:
        input_folder = str(Path(files[-1]).parent) + '/'
        for filepath in files:
            if '.inp' in filepath:
                with open(filepath,'r') as f:
                    pr=f.read().splitlines()
                    for p in pr:
                        if '#' in p:
                            continue
                        elif '=' in p:
                            k,v=p.split('=')
                            try:
                                v=int(v)
                            except:
                                try:
                                    v=float(v)
                                except:
                                    v=str(v).strip()
                                    if any(s in v for s in ['~',',']):
                                        v=v.split(',')
                                        av=[]
                                        for a in v:
                                            if '~' in a:
                                                av=a.split('~')
                                                av=list(range(int(av[0]), int(av[1])+1))
                                            else:
                                                try:
                                                    av+=[int(a)]
                                                except:
                                                    av=v
                                        v=av
                                        
                                    if ',' in v:
                                        v=v.split(',')
                                        v=[int(a) for a in v if a]
                                    
                                    elif 'True' in v: v=v.lower()=='true'
                                    elif 'False' in v:v=v.lower()=='true'
                            params[k.strip()]=v                             # type: ignore
    return params, files, input_folder


def create_config(params, out='config.inp'):
    with open(out, 'w') as o:
        for k,v in params.items():
            
            if isinstance(v,list) : 
                v=map(str, v)
                o.write(f'{k}={",".join(v)}\n')
            elif isinstance(v, range):
                o.write(f'{k}={v.start}~{v.stop}\n')
            else:
                o.write(f'{k}={v}\n')
    return out