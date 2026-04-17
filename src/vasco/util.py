
from pandas import read_csv, read_parquet
from pandas import DataFrame as df, concat, read_fwf
from io import StringIO
from astropy.coordinates import SkyCoord, search_around_sky, Angle
import astropy.units as u
import glob, re
from collections import defaultdict
from pathlib import Path
import json
import subprocess
import numpy as np
import shutil
import warnings

# ------ read ASCII

def clean_ascii_to_polarsdf(ascii_str):
    import polars as pl
    lines = [
        line.strip().strip('|')
        for line in ascii_str.strip().split('\n')
        if not (line.startswith('+') or line.strip() == "")
    ]
    
    csv_content = "\n".join(lines)
    
    return pl.read_csv(
        StringIO(csv_content), 
        separator='|', 
        try_parse_dates=True
    ).with_columns(pl.all().str.strip_chars()) 

# -----------


def check_band(freq, bands=None):
        """
        Input
        ---

        freq            (float)
                        value of the reference fequency in GHz

        bands           (dict)
                        dictionary of bands containing numpy array of limiting values of range of the band.

        Return
        ---
        
        band closest to S,C,X,U,K,Q,W of observation

        https://science.nrao.edu/facilities/vlba/docs/manuals/oss/bands-perf
        """   
        band = None
        if not bands:
            bands = {
            'S' : np.array([2.0, 2.6]),
            'C' : np.array([3.5, 6.4]),
            'X' : np.array([7.401, 8.8]),
            'U' : np.array([11.8, 15.7]),
            'K' : np.array([20.0, 25.0]),
            'Q' : np.array([40.0, 46.0]),
            'W' : np.array([80.0, 90.0]),
        }
        compare = 999.0
        for k,v in bands.items():
            val = (np.abs(v-freq)).min()

            if compare > val: 
                band = k
                compare = val
        if band is None:
            warnings.warn(f"no matching band was found", UserWarning)
        return band

def read_inputfile(folder,inputfile='.inp'):
    """Read the input file and return a dictionary with the parameters.

    Returns
    ---

    (params, files, input_folder)

    """
    params = defaultdict(list)
    input_folder= None
    files=glob.glob(f'{folder}/*{inputfile}',recursive=True)
    if not files: files=glob.glob(f'{folder}/*/*{inputfile}',recursive=False)
    if not files: files=glob.glob(f'{folder}/*/*/*{inputfile}',recursive=False)
    if files:
        input_folder = str(Path(files[-1]).parent) + '/'
        for filepath in files:
            if inputfile in filepath:
                with open(filepath,'r') as f:
                    pr=f.read().splitlines()
                    for p in pr:
                        if '#' in p:
                            continue
                        elif '=' in p:
                            k,v=p.split('=')
                            # check for leading zeros
                            if str(v).strip() and v.strip()[0] == '0':
                                v   =   str(v).strip()
                                
                            else:
                                try:
                                    v=int(v)
                                except (ValueError, TypeError):
                                    try:
                                        v=float(v)
                                    except (ValueError, TypeError):
                                        v=str(v).strip()
                                        if "*" in v:
                                            try:
                                                v = glob.glob(f'{v}', recursive=True)
                                            except (ValueError, TypeError):
                                                v = str(v)
                                        else:
                                            v = v.lower() == 'true' if (any(boolv == v.lower() for boolv in ['true', 'false'])) else v
                            params[k.strip()]=v
                            
    return params, files, input_folder

def save_metafile(metafile, metad):
    with open(str(metafile), 'w') as mf: json.dump(metad, mf)
    print("saved", str(metafile))

def read_metafile(metafile):
    with open(metafile, 'r') as sf:
        metad                       =   sf.read()
        meta                        =   json.loads(metad)
    return meta

def read_flaglist(flaglistfile):
  with open(flaglistfile, 'r') as flagfile:
    flagcontent = flagfile.read()
    src_start           = False
    dic_src_flaggedants = {}
    for line in flagcontent.split("\n"):
      if line:
        if not 'amou' in line[:5].lower():
          if '--' in line[:5].lower():
            src= line.replace('--', '').strip()
            dic_src_flaggedants[src] = {}
            src_start = True
          else:
            ant, perc = '', 'nan'
            if ":" in line[:4]:
              src_start = False
              ant = line[:2]
              if "%" in line:
                perc = line.replace(ant, "").replace(":","").replace("%","").strip()
              else:
                perc = "nan"
              dic_src_flaggedants[src][ant] = perc
  return dic_src_flaggedants

# targets = SkyCoord([23.997513*u.hourangle],[47.119273*u.deg], frame='fk5')

def create_df_fromrfcfile(rfc_filepath):
    
    rfc_dfpath = Path(rfc_filepath).parent / f'{Path(rfc_filepath).stem}.pkl'
    with open(rfc_filepath, 'r') as rfc:
        header_lines = 0
        dic_comments = {}
        for i,line in enumerate(rfc.readlines()):
            if line[0]=='#': 
                dic_comments[i]=line.strip('#').strip()
                header_lines+=1
            else:
                break

    columns = [
        "origin",
            
        "J2000_name", "Comm_name", "RAh", "RAm", "RAs", "DECd", "DECm", "DECs", 
        "D_alp", "D_Del", "Corr", "Obs", "Sca", "Ses", 
        "S-band Shr", "S-band Mid", "S-band Unres", 
        "C-band Shr", "C-band Mid", "C-band Unres", 
        "X-band Shr", "X-band Mid", "X-band Unres", 
        "U-band Shr", "U-band Mid", "U-band Unres", 
        "K-band Shr", "K-band Mid", "K-band Unres", "Epoch"
    ]
    start_buff = list(dic_comments.keys())[-1]+1
    with open(rfc_filepath, 'r') as rfc:
        for _ in range(start_buff):
            rfc.readline()
        rfcbuff = StringIO(rfc.read())
        
    df_rfc = read_csv(rfcbuff, names=columns, delim_whitespace=True, dtype='str')
    df_rfc['RA_J2000']=Angle(df_rfc['RAh']+':'+df_rfc['RAm']+':'+df_rfc['RAs'], unit=u.hourangle)
    df_rfc['DEC_J2000']=Angle(df_rfc['DECd']+':'+df_rfc['DECm']+':'+df_rfc['DECs'], unit=u.deg)
    df_filtered = df_rfc.drop(columns=["RAh", "RAm", "RAs", "DECd", "DECm", "DECs"])
    df_filtered.insert(1, 'RA_J2000', df_filtered.pop('RA_J2000'))
    df_filtered.insert(2, 'DEC_J2000', df_filtered.pop('DEC_J2000'))
    if Path(rfc_dfpath).exists(): Path.unlink(rfc_dfpath)
    df_filtered.to_parquet(rfc_dfpath,engine='pyarrow')
    return df_filtered

def search_rfc_catalog(targets, rfc_filepath, reset=False, seplimit=10, columns=[]):
    # rfcbuff = None
    rfc_dfpath = Path(rfc_filepath).parent / f'{Path(rfc_filepath).stem}.pkl'
    if rfc_dfpath.exists() and not reset:
        df_rfc = read_parquet(rfc_dfpath)
    else:
        df_rfc = create_df_fromrfcfile(rfc_filepath=rfc_filepath)
        
    catalog = SkyCoord(df_rfc['RA_J2000'].values*u.hourangle, df_rfc['DEC_J2000'].values*u.deg, frame='icrs')
    idxsearcharound, idxself, sep2d, dist3d =  search_around_sky(catalog, targets, seplimit=seplimit*u.milliarcsecond)
    df_res = df_rfc.loc[idxsearcharound[idxself]]
    df_res['sep(mas)'] = sep2d.milliarcsecond
    df_res['coordinate'] = SkyCoord(df_res['RA_J2000'].values*u.hourangle, df_res['DEC_J2000'].values*u.deg).to_string('hmsdms')
    # df_res['RA_J2000'] = (df_res['RA_J2000'].values*u.hourangle).to_value('hms')
    # df_res['DEC_J2000'] = (df_res['DEC_J2000'].values*u.hourangle).to_value('dms')
    
    df_res.insert(0, 'sep(mas)', df_res.pop('sep(mas)'))
    df_res.insert(1, 'coordinate', df_res.pop('coordinate'))

    cols= '|'.join(columns)
    df_res = df_res[df_res.filter(regex=rf'RA|DEC|{cols}').columns]
    return df_res

def run_fitsverify(fitsfile):
    """Run fitsverify and capture output for extra byte

    Args:
        fitsfile (_type_): _description_

    Returns:
        _type_: _description_
    """
    val = None
    try:
        
        result = subprocess.run(["fitsverify", fitsfile], capture_output=True, text=True)
                                
        output = result.stdout + "\n" + result.stderr
        match = re.search(r"File has extra byte\(s\) after last HDU at byte (\d+)", output)
        
        if match:
            val = int(match.group(1))
        
    except subprocess.CalledProcessError as e:
            return f"Error running fitsverify: {e}"

    return val


def create_config(params, out='config.inp', lj=1, rj=1, verbose=True):
    with open(out, 'w') as o:
        for k,v in params.items():
            
            if isinstance(v,list) : 
                v=map(str, v)
                v = f'{",".join(v)}'
            elif isinstance(v, range):
                v = f"{v.start}~{v.stop}"
            if isinstance(v, str):
                v = f"{v.rjust(rj)}"
            o.write(f'{k.ljust(lj)} = {v}\n')
    if verbose:print("created", f'{out}' )
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
    df_rfc = df_fromtxt(filename)
    ivs_search_terms = set()
    j20_search_terms = set()

    for s in sources:
        base = s[1:] if s.startswith('J') else s
        for length in [9, 10]:
            short_name = base[:length]
            ivs_search_terms.add(short_name)
            j20_search_terms.add(f"J{short_name}")
    res_ivs = df_rfc[df_rfc[ivscolname].str.startswith(tuple(ivs_search_terms), na=False)]
    res_j20 = df_rfc[df_rfc[j2colname].str.startswith(tuple(j20_search_terms), na=False)]
    return concat([res_ivs, res_j20]).drop_duplicates()

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
    res['orig_sourcename'] = sources[0]
    
    if len(sources)>1:
        for source in sources[1:]:
            temp_res = search_source([source], filename=filename, concat=concat)
            temp_res['orig_sourcename'] = source
            res = concat([res, temp_res], axis=0)
            
    return res

def latest_file(path: Path, pattern: str = "*"):
    """
    to get the last file that was generated, this can be useful for getting any new logfiles.
    """
    files = path.glob(pattern)
    lastf = Path('')
    
    try:
        lastf = max(files, key=lambda x: x.stat().st_ctime)
    except Exception:
        return Path('')
    finally:
        return lastf



# __________________________ Catalog file reading utilities _______________________________


def infercoltype(typechar):
    if 'A' in  typechar:
        return "str"
    if 'I' in typechar:
        return 'int'
    if 'F' in typechar:
        return 'float'
    else:
        print(f"warning datatype not recognised for {typechar}")
        return 'str'
    
def parse_line(line, dic_col, **colkwargs):
    import numpy as np
    line_cols = line[:]
    
    parsed_line = {}
    for c,colk in enumerate(dic_col):
        typ = dic_col[c]['type']
        col = dic_col[c]['name']
        sb = dic_col[c]['start_byte']
        eb = sb+dic_col[c]['bytelen']
        colv = line_cols[sb:eb].strip()
        parsed_line[col] = str(colv)
    
    ra, de = '', parsed_line['DE-']
    for ccrd in ['RAh', 'RAm', 'RAs']:
        ra += parsed_line[ccrd] + ccrd.replace('RA', '')
    
    for ccrd in ['DEd', 'DEm', 'DEs']:
        de += parsed_line[ccrd] + ccrd.replace('DE', '')
        
    parsed_line['coordinate'] = ra + ' ' + de
    for col in colkwargs:
        parsed_line[col]    = colkwargs[col]
        
    return parsed_line



def rfc_parse_col(lines):
    
    col_decimalround        =   0
    label_byte              =   0
    endh_line_byte          =   0
    
    for line in lines:
        if '#' in line:
            endh_line_byte += 1
        else:
            break
    
    # starth_line_byte    =   endh_line_byte - col_gap
    something_starts    =   False    
    read_col            =   False
    something_indicator =   '---------------------'
    dic_col             =   {}
    col_i               =   0
    
    for line in lines[:endh_line_byte]:
        if something_indicator in line:
            something_starts = True
        
        if something_starts and not something_indicator in line:
            if 'Name' in line:
                label_byte = len(line.split('Name')[0])+4 -1
                read_col=True
        
        if read_col:
            col_row = line.rstrip('\n').strip(r'#').strip()
            col_name        =   col_row[:label_byte].split()[-1]
            col_desc        =   col_row[label_byte:].strip()
            col_row_cols    =   col_row.split('-')
            col_start_byte  =   int(col_row_cols[0])-1
            col_end_byte    =   int(col_row_cols[1].split()[0])-1
            
            typechar        =   str(col_row_cols[1].strip().split()[1].strip().split()[0])
            col_type        =   infercoltype(typechar)
            col_bytelen     =   int(typechar[1:].split('.')[0].strip())
            if 'float' in col_type:
                col_decimalround    =   int(typechar[1:].split('.')[1])
            
            col_unitchar            =   str(col_row_cols[1].split()[2]) if len(col_row_cols[1].split())>2 else 'null'

            if 'MeaEpo' in line:
                read_col = False
                
            dic_col[col_i] = {
                'name'          :   col_name,
                'start_byte'    :   col_start_byte,
                'end_byte'      :   col_end_byte,
                'type'          :   col_type,
                'bytelen'       :   col_bytelen,
                'round'         :   col_decimalround,
                'unit'          :   col_unitchar,
                'desc'          :   col_desc,
            }
            col_i   +=    1
    return dic_col, endh_line_byte

def rfc_parse_search_pattern(file_path, patterns=[], verbose=False, col_rows=4, search_key='pattern'):
    file_path               =   Path(file_path)
    endh_line_byte          =   0
    asciiout                =   """"""
    
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    dic_col, endh_line_byte   =   rfc_parse_col(lines)
    starth_line_byte          =     endh_line_byte - col_rows
    
    if verbose:
        lines[starth_line_byte]                 =   lines[starth_line_byte][0].replace('#', 'O') + lines[starth_line_byte][1:]
        asciiout                                +=  "".join(lines[starth_line_byte:endh_line_byte])
        asciiout                                =   asciiout.replace("#", '_')
    matched = []
    if any(patterns):        
        for pattern in patterns:
            matched += [parse_line(line, dic_col, **{search_key:pattern}) for line in lines if pattern in line]
    df_res = df(matched)
    
    df_res = df_res.drop(columns=['RAh', 'RAm','RAs', 'DE-', 'DEd', 'DEm', 'DEs', 'Nobs', 'Nsca', 'Nses'],errors='ignore')
    if 'coordinate' in df_res:
        df_res.insert(2, 'coordinate', df_res.pop('coordinate'))
    return df_res


def rfc_ascii_to_df(file_path):
    
    lines = []
    data_dicts = []
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    dic_col, ehb  =   rfc_parse_col(lines)
    data_dicts +=   [parse_line(line, dic_col) for line in lines[ehb:]]
    
    return df(data_dicts)


def compute_sep(row, target_names, target_coords, frame='icrs'):
    try:
        idx_target = list(target_names).index(row['fits_target'])
        c_targetfound = row['coordinate']
        c_targetfits = target_coords[idx_target]
        sep = SkyCoord(c_targetfound, unit=(u.hourangle, u.deg), frame=frame).separation(SkyCoord(c_targetfits, frame=frame))
        return sep.to(u.mas).value
    except (ValueError, IndexError):
        return None  


def create_df_fromrfcfile(rfc_filepath):
    
    rfc_dfpath = Path(rfc_filepath).parent / f'{Path(rfc_filepath).stem}.pkl'
    with open(rfc_filepath, 'r') as rfc:
        header_lines = 0
        dic_comments = {}
        for i,line in enumerate(rfc.readlines()):
            if line[0]=='#': 
                dic_comments[i]=line.strip('#').strip()
                header_lines+=1
            else:
                break

    columns = [
        "origin",
            
        "J2000_name", "Comm_name", "RAh", "RAm", "RAs", "DECd", "DECm", "DECs", 
        "D_alp", "D_Del", "Corr", "Obs", "Sca", "Ses", 
        "S-band Shr", "S-band Mid", "S-band Unres", 
        "C-band Shr", "C-band Mid", "C-band Unres", 
        "X-band Shr", "X-band Mid", "X-band Unres", 
        "U-band Shr", "U-band Mid", "U-band Unres", 
        "K-band Shr", "K-band Mid", "K-band Unres", "Epoch"
    ]
    start_buff = list(dic_comments.keys())[-1]+1
    with open(rfc_filepath, 'r') as rfc:
        for _ in range(start_buff):
            rfc.readline()
        rfcbuff = StringIO(rfc.read())
        
    df_rfc = read_csv(rfcbuff, names=columns, delim_whitespace=True, dtype='str')
    df_rfc['RA_J2000']=Angle(df_rfc['RAh']+':'+df_rfc['RAm']+':'+df_rfc['RAs'], unit=u.hourangle)
    df_rfc['DEC_J2000']=Angle(df_rfc['DECd']+':'+df_rfc['DECm']+':'+df_rfc['DECs'], unit=u.deg)
    df_filtered = df_rfc.drop(columns=["RAh", "RAm", "RAs", "DECd", "DECm", "DECs"])
    df_filtered.insert(1, 'RA_J2000', df_filtered.pop('RA_J2000'))
    df_filtered.insert(2, 'DEC_J2000', df_filtered.pop('DEC_J2000'))
    if Path(rfc_dfpath).exists(): Path.unlink(rfc_dfpath)
    df_filtered.to_parquet(rfc_dfpath,engine='pyarrow')
    return df_filtered

# def search_rfc_catalog(targets, rfc_filepath, reset=False, seplimit=10, columns=[]):

#     rfc_dfpath = Path(rfc_filepath).parent / f'{Path(rfc_filepath).stem}.pkl'
#     if rfc_dfpath.exists() and not reset:
#         df_rfc = read_parquet(rfc_dfpath)
#     else:
#         df_rfc = create_df_fromrfcfile(rfc_filepath=rfc_filepath)
        
#     catalog = SkyCoord(df_rfc['RA_J2000'].values*u.hourangle, df_rfc['DEC_J2000'].values*u.deg, frame='fk5')
#     idxsearcharound, idxself, sep2d, dist3d =  catalog.search_around_sky(targets, seplimit=seplimit*u.milliarcsecond)
#     df_res = df_rfc.loc[idxself]
#     df_res['sep(mas)'] = sep2d.milliarcsecond
#     df_res['coordinate'] = SkyCoord(df_res['RA_J2000'].values*u.hourangle, df_res['DEC_J2000'].values*u.deg).to_string('hmsdms')
    
#     df_res.insert(0, 'sep(mas)', df_res.pop('sep(mas)'))
#     df_res.insert(1, 'coordinate', df_res.pop('coordinate'))

#     cols= '|'.join(columns)
#     df_res = df_res[df_res.filter(regex=rf'RA|DEC|{cols}').columns]
#     return df_res

def format_coord(coord_str):
    parts = coord_str.strip().split()
    if len(parts) == 6:
        h, m1, s1, d, m2, s2 = parts
        return f"{h}:{m1}:{s1} {d}:{m2}:{s2}"
    else:
        return None

def read_df_out(filepath):
    with open(filepath) as f:
        lines = f.read().splitlines()
        data = [re.split(r' {2,}', line.strip()) for line in lines[1:]]
        columns = [re.split(r' {1,}', line.strip()) for line in lines[:1]]
        cols = ['idx'] + columns[0]
    return df(data, columns=cols).set_index('idx')

def parse_class_cat(filepath, skiprows=7):
    df_res = read_fwf(filepath_or_buffer=filepath, skiprows=skiprows, delimiter='|')
    df_res.columns = [col.strip() for col in df_res.columns]
    
    if '--' in df_res['GB6'].iloc[0] : df_res = df_res.drop(0)
    
    df_res.rename(columns={'h  m       s   d  m      s': 'RADEC'}, inplace=True)
    df_res['coordinate'] = df_res['RADEC'].apply(format_coord)
    df_res = df_res.drop(columns=['RADEC'],errors='ignore')
    return df_res


# ____________________________________



# --------- colors
c = {
    "b": "\033[1m",   # Bold
    "d": "\033[2m",   # Dim

    # Normal Colors
    "k": "\033[30m",  # Black
    "r": "\033[31m",  # Red
    "g": "\033[32m",  # Green
    "y": "\033[33m",  # Yellow
    "bl": "\033[34m", # Blue
    "m": "\033[35m",  # Magenta
    "c": "\033[36m",  # Cyan
    "w": "\033[37m",  # White
}


X  = "\033[0m"

# _____________________________________



def casadir_find(vasco_data_dir, write: bool = True):
    import readline
    readline.set_completer_delims('\t\n=')
    readline.parse_and_bind("tab: complete")
    cp_txt, do, auto = '', 'y', 'y'
    casa_path = f"{vasco_data_dir}/casa_path.txt"
    casadir = ''
    if Path(casa_path).exists():
        with open(casa_path, "r") as cp:
            lines = cp.readlines()
            if not lines:
                raise ValueError(f'Empty calibrator file: {cp.name}')
            cp_txt = lines[0]
            
            if cp_txt:
                auto = 'no'
                casadir = cp_txt
                print(f"There is a CASA path already written: {cp_txt}")
    if write:
        if cp_txt:
            print(f"{c['c']} Are you sure you want to proceed overwriting?{X}")
            do = input("(y/n)")
        if str(do).lower() in ["y", "yes"]:
            print("Please enter your monolithic casa directory "
                  "(eg /path/to/casa-CASA-xxx-xxx-py3.xxx/bin/):")
            casadir = input()
            with open(casa_path, 'w') as o:
                o.write(f"{casadir}/")
        try:
            subprocess.run([f"{casadir}/casa", '-v'], shell=False,
                           stdout=subprocess.DEVNULL)
        except FileNotFoundError:
            print(f"{c['r']}Failed!{X} The path '{casadir}' is not a valid casa directory")
            print("Proceed with automatic search? (y/n):")
            auto = input()
    if str(auto).lower() in ["y", "yes"]:
        casadir = Path(str(shutil.which("casa"))).resolve().parent

    if Path(casadir).exists():
        print(f"{c['g']}Success!{X} Found this casa directory:{c['g']} {casadir}{X}")
    if not Path(casadir / 'mpicasa').exists():
        print("Failed! mpicasa was not found")
    else:
        casadir = Path(casadir)
        subprocess.run([f"{str(casadir)}/casa", '-v'], shell=False,
                       stdout=subprocess.DEVNULL)
        subprocess.run([f"{str(casadir)}/mpicasa", '-h'], shell=False,
                       stdout=subprocess.DEVNULL)

    print(f"casa_path : {casa_path}")
    if not write:
        return casadir


def rfc_find(rfc_filepath, write: bool = True) -> str:
    import readline
    readline.set_completer_delims('\t\n=')
    readline.parse_and_bind("tab: complete")
    rfc_txt, do = '', 'y'
    filepath = rfc_filepath
    if Path(filepath).exists():
        with open(filepath, "r") as cp:
            lines = cp.readlines()
            rfc_txt = lines[0] if lines else ""
    if write:
        if rfc_txt:
            filepath = rfc_txt
            print(f"There is a path already written: {rfc_txt}")
            print(f"{c['c']} Are you sure you want to proceed overwriting?{X}\n\n")
            do = input("(y/n)")
        if str(do).lower() in ["y", "yes"] and not rfc_txt:
            print("Please enter the path for the ASCII file:")
            rfc_txt = input()
        with open(filepath, 'w') as o:
            o.write(f"{rfc_txt}")
    return rfc_txt
