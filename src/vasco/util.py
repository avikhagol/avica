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


def create_config(params, out='config.inp', lj=1, rj=1):
    with open(out, 'w') as o:
        for k,v in params.items():
            
            if isinstance(v,list) : 
                v=map(str, v)
                v = f'{",".join(v)}'
            elif isinstance(v, range):
                v = f"{v.start}~{v.stop}"
            if type(v) is str():
                v = f"{v.rjust(rj)}"
            o.write(f'{k.ljust(lj)} = {v}\n')
    return out

def read_txt_file(filename):
    """
    reads rfc catalog file and parses into a dict, 
    use `df_fromtxt()` to get dataframe

    Input
    ---

    filename

    Returns
    ---

    total_fields
    non_fields
    fields
    vals
    
    """   
    nfield, fail_dic = 0, 0
    cols = [
    'Category',
    'IVS name',
    'J2000 name',
    'hh(RA)', 'mm(RA)', 'ss(RA)',
    'dd(DEC)', 'mm(DEC)', 'ss(DEC)',
    'D_alp',
    'D_Del',
    'Corr',
    'Obs',
    'S_T-', 'S_Tot', 'S_u-', 'S_unres', 
    'C_T-', 'C_Tot', 'C_u-', 'C_unres', 
    'X_T-', 'X_Tot', 'X_u-', 'X_unres', 
    'U_T-', 'U_Tot', 'U_u-', 'U_unres', 
    'K_T-', 'K_Tot', 'K_u-', 'K_unres', 
    'Type', 
    'Cat']

    dic, vals = {'fields':{}, 'vals':[]}, []

    if Path(filename).exists():
        with open(filename, 'r') as rfc:
            rl = rfc.readlines()
            row=[]
            for il,l in enumerate(rl):
                if '#' in l:
                    if 'Field' in l:
                        try:
                            field_content   = l.replace('#', '').strip()
                            field_content   = field_content.replace('Field','')
                            field_content   = [field_content[:9].strip(), field_content[9:15].strip(), field_content[15:].strip()]
                            
                            field_content[0]     = field_content[0].split(':')
                            field_content[0]     = (int(field_content[0][0]),int(field_content[0][1]))
                            
                            if cols[nfield] in dic['fields'].keys(): print(cols[nfield])
                            dic['fields'][cols[nfield]] = field_content
                            nfield += 1
                            
                        except Exception as e:
                            fail_dic += 1
                            dic['err'] = str(e)
                            
                    dic['total_fields']=nfield
                    dic['non_fields']= fail_dic
                else:
                    for v in dic['fields'].values():
                            row.append(l[v[0][0]-1:v[0][1]])
                    vals.append(row)
                    row=[]
            dic['vals'] = vals
    return dic
    
def df_fromtxt(filename):
    from pandas import DataFrame as df
    dic = read_txt_file(filename)
    df_rfc = df(dic['vals'], columns=list(dic['fields'].keys()))
    return df_rfc

def search_source(sources, filename, concat, j2colname='J2000 name', ivscolname='IVS name'):
    """
    
    """
    
    df_rfc = df_fromtxt(filename)
    for txt_count in [10,9]:          
        nsources = [source[:txt_count] for source in sources]
    jsources = []
    for source in nsources:
        
        if source[0]!='J': 
            jsources.extend([f'J{source}'])
            
        else: 
            jsources.extend([source])
            nsources.remove(source)
            nsources.extend([source[1:]])
    res = concat([df_rfc.loc[df_rfc[ivscolname].str.startswith(tuple(nsources))], df_rfc.loc[df_rfc[j2colname].str.startswith(tuple(jsources))]])
    return res

def search_sources(sources, filename, j2colname='J2000 name', ivscolname='IVS name'):
    """
    takes input sources list and returns a dataframe with search result in the colnames specified.
    
    :sources:       (list)
                    list of sources to search in the calibrator list

    :filename:      (str)
                    path of the calibrator list (in ascii) text file.
    
    :j2colname:     (str)
                    name of the J2000 column name to check the J2000 name of the sources
    
    :IVS name:      (str)
                    name of the IVS column name to check for the corrosponding sources.

    """
    from pandas import concat

    res = search_source([sources[0]], filename=filename, concat=concat, j2colname=j2colname, ivscolname=ivscolname)
    if len(sources)>1:
        for source in sources[1:]:
            res = concat([res, search_source([source], filename=filename, concat=concat)], axis=0)
    return res

def latest_file(path: Path, pattern: str = "*"):
    """
    to get the last file that was generated, this can be useful for getting any new logfiles.
    """
    files = path.glob(pattern)
    lastf = Path('')
    
    try:
        lastf = max(files, key=lambda x: x.stat().st_ctime)
    finally:
        return lastf
