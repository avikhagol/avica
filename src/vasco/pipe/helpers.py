# from alfrd import Pipeline, c # FIXME: revive
from pathlib import Path
import time, glob, numpy as np, subprocess, os, shutil, sys, json
# from alfrd.util import timeinmin, read_inputfile, del_fl, read_metafile
from vasco.util import create_config, read_metafile, read_inputfile
from collections import defaultdict
from copy import deepcopy
import warnings

import traceback

import re
import urllib.request
from urllib.error import URLError

from datetime import datetime

from vasco.fitsidiutil import read_idi

#  ____________________________________________________________________     Init Variables


def get_targets_filenames(lf, filename_col, targetname_col):
    alltargets                  =   list(lf.df_sheet0[lf.df_sheet0[filename_col]==lf.get_value(filename_col)][targetname_col].values)
    target                      =   lf.get_value(targetname_col)
    parsed_filenames            =   lf.get_value(filename_col).replace('[', '').replace(']', '').replace('"', '').replace("'", '').replace('"""', '').replace("'''", '')
    fitsfilenames               =   parsed_filenames.split(',')
    return target, alltargets, fitsfilenames



def get_wd_ifolder_multiplefits(fitsfiles, target_dir, ifolder):
    
    wds = []
    for fitsfile in fitsfiles:
        wds.extend(str(Path(iwd).parent) for iwd in iwd_for_fitsfile(fitsfile, target_dir, ifolder=ifolder, create=False, allwds=True)[0])       # not taking set, as that randomizes wds for further selection, we anyway select the first wd with fitting criterion
    wds             =   np.sort(list(set(wds)))
    
    new             =   False
    wd_ifolder      =   None
    rawf            =   ""
    expected_ffnames = {Path(f).name for f in fitsfiles}

    for wd in wds:
        
        rawf        =   Path(wd) / 'raw'
        found_ffnames = {f.name for f in rawf.glob('*fits') if f.is_file()}
        if  all(expected_ffname in found_ffnames for expected_ffname in expected_ffnames):
            new         =   False
            wd_ifolder  =   f"{wd}/{Path(ifolder).name}"
            break
        else:
            new         =   True 
            
    
    if new:
        allwds  = [wd.name for wd in Path(wds[0]).parent.glob("wd*")]
        n_incr = [int(wd.split('_')[1]) for wd in allwds if '_' in wd]
        incr = np.max(n_incr)+1 if len(n_incr) else 1
        wd = f"{str(Path(wds[0]).parent)}/wd_{incr}"
        wd_ifolder = f"{wd}/{Path(ifolder).name}"
        
        shutil.copytree(f"{ifolder}", wd_ifolder)
        rawf = f"{wd}/raw"
        Path(rawf).mkdir(parents=True, exist_ok=False)
        print(f"{wd_ifolder} created")
    
    
    return wd_ifolder

def search_input_template(picard_input_template, ifolder, depth=4):
        pattern = ""
        ifolder = picard_input_template
        if "input_template" not in picard_input_template:
            for i in range(depth):
                ifolder.extend(glob.glob(f"{picard_input_template}{pattern}*input_template"))
                if len(ifolder):
                    break
                pattern += "*/"
            
        if isinstance(ifolder, list):
            if len(ifolder):
                ifolder = ifolder[0]
        
        # warnings.warn(f"could not find the input_template folder in {picard_input_template}", UserWarning)
        return ifolder

def setup_workdir(lf, target_dir, fitsfilenames, allfitsfile, picard_input_template):
    ff_path_existing            =   [fpe for fpe in allfitsfile for ff in fitsfilenames if ff in fpe]
    ifolder = []
    if not Path(picard_input_template).exists():
        raise FileNotFoundError(f"{picard_input_template}")
    
    ifolder                     =   search_input_template(picard_input_template, ifolder)
    wd_ifolder                  =   get_wd_ifolder_multiplefits(ff_path_existing, target_dir, ifolder=ifolder)
    
    filepaths                   =   []
    
    ff_path                     =   []
    
    for ff in fitsfilenames:
        if ff:
            ff_path             =   [fp for fp in allfitsfile if ff in fp]
        
        if not ff_path:
            raise ValueError(f"`{ff}` is not correct `fitsfile` \n \
                            Check params : fitsfile_path, primary_colname, primary_value:\n \
                            ({ff_path}, {lf.primary_colname}, {lf.primary_value})")
        if not wd_ifolder: 
            wd_ifolder                  =   get_wd_ifolder(fitsfile=ff_path[0], target_dir=target_dir, ifolder=ifolder)[0]
        destpath                    =   f"{(Path(wd_ifolder).parent)}/raw/{ff}"
        if destpath not in filepaths:
            filepaths.append(destpath)
        if not Path(destpath).exists():
            shutil.copy(ff_path[0], destpath)
        if not Path(destpath).exists():
            raise FileNotFoundError(f"{ff_path[0]} --> {destpath}")
    return wd_ifolder, filepaths



def fits_has_target(fitsfiles, target):
    return any([target in read_idi(fitsfile)['SOURCE']['SOURCE'] for fitsfile in fitsfiles])

def add_O(src_name):
    
    # corrected_source=[('O' * (len(src_name) - len(src_name.lstrip('0'))) + src_name.lstrip('0')) 
    #                   if src_name.lstrip('0').isdigit() else src_name][0]
    if str(src_name)[0] == '0':
        zero_grouped = re.match(r'(0*)(.*)', src_name).groups()
        prefix = "O"*len(zero_grouped[0])
        print(src_name, "has zero ==>", prefix+zero_grouped[1])
        return prefix+zero_grouped[1]


def parse_params(lf, params):
    for ky in params:
        if ky=="folder_for_fits" and '$' in params[ky]:
            
            dollar_sep          =   params[ky].split('$')
            dollar_var          =   dollar_sep[1].split('/')[0]
            dollar_var_post     =   dollar_sep[1].split('/')[-1]
            params[ky]          =   dollar_sep[0] + lf.get_value(dollar_var) + dollar_var_post
            
    return params


def get_logfilename(fnname="fitsidiutil", start_stamp=datetime.now(), module_name="vasco"):
    """
    Return
    
    {fnname}_{module_name}_log-{start_stamp.strftime("%Y%m%d_%H%M%S")}.log
    
    fnn
    """
    
    return f'{fnname}_{module_name}_log-{start_stamp.strftime("%Y%m%d_%H%M%S")}.log'

# --- sn rating, metfill, splitms

def read_vasco_sources_msmeta(metafile):
    
    alls, spws = {}, {}
    meta = read_metafile(metafile)
    for band in meta['s_dict'].keys():
        if 'known' not in band:
            alls[band] = read_vasco_sources(s=meta['s_dict'][band])
            spws[band] = meta["bands_dict"][band]['spws']
    return alls, spws


def alls_fromobs(obs_b):
    alls    =   set()
    for obs_key in obs_b:
        if any(key_name==obs_key for key_name in ['science_target', 'calibrators_instrphase', 'calibrators_bandpass', 
                                                  'calibrators_rldly', 'calibrators_dterms', 'calibrators_phaseref']):
            if obs_b[obs_key] and str(obs_b[obs_key]).lower()!='none':
                srcs    =   str(obs_b[obs_key]).split(',')
                
                alls.update(srcs)

    alls = list(alls)
    return alls

def read_vasco_sources(vascometafile=None, s=None):
    if not s: s       =   read_vascometa(vascometafile=vascometafile)
    alls    =   set()
    for k, source_list in s.items():
        if source_list: alls.update(source_list)
    return list(alls)


# ---------         Connection

# def connect(sheet_url, worksheet, primary_value):
#     from alfrd.lib import GSC, LogFrame
#     gsc                             =   GSC(url=sheet_url, wname=worksheet)
#     df_vlba                         =   gsc.open()
#     lf                              =   LogFrame(gsc)
#     if not ( 'primary_colname' in Pipeline.params and Pipeline.params['primary_colname']):
#         Pipeline.params['primary_colname']              =   lf.primary_colname          =   'FILE_NAME'
#     else:
#         lf.primary_colname                              =   Pipeline.params['primary_colname']
#     Pipeline.params['primary_value']                    =   lf.primary_value            =   primary_value
#     Pipeline.params['lf']                               =   lf
#     Pipeline.params['working_col']                      =   Pipeline.step_name

# ---------         Configuration Files
def update_constants(wd_ifolder, filename=None, val_dict=defaultdict(), new_wd=None, ):
    inpfile                 =   'constants.inp'
    
    p, _, _                 =   read_inputfile(wd_ifolder, inpfile)
    
    p['fast_metadata_AK']   =   True                                                                                                                                           # FIXME : testing done with AK metadata= False
    p['flagfile_extensions']=   '.fg;.FG;.uvflag;.UVFLAG;.uvflg;.UVFLG;.uvfg;.UVFG;.flag;.FLAG;.flg;.FLG'
    p['antab_extensions']   =   '.an;.AN;.antab;.ANTAB;.vlog;.VLOG;.antabfs;.ANTABFS'
    p['fitsidi_extensions'] =   '.uvfits;.fits;.FITS;.idifits;.IDIFITS;.IDI;.IDI0;.IDI1;.IDI2;.IDI3;.IDI4;.IDI5;.IDI6'
    # p['avg_final_time']     =   False
    if filename:
        va              =   read_vascometa(vascometafile=filename, wd_ifolder=wd_ifolder)
    else:
        va          =   val_dict
    p.update((k, va[k]) for k in set(va).intersection(p))
    if new_wd and Path(new_wd).exists():
        wd_ifolder = new_wd
    create_config(p, f'{wd_ifolder}/{inpfile}')

def read_vascometa(wd_ifolder=None, vascometafile=None):
    s = defaultdict(list)
    if not vascometafile: 
        if not wd_ifolder:
            raise TypeError(f"'{wd_ifolder}' not valid wd_ifolder")
        vascometafile = Path(wd_ifolder).parent / 'vasco.meta'
    if Path(vascometafile).exists(): 
        with open(str(vascometafile), 'r') as vm: s  =   json.loads(vm.read())
    return s

def update_from_vascometa(wd_ifolder, filename=None, inpfile='', val_dict=None, new_wd=None, reference_ifolder=''):
    
    p, _, _         =   read_inputfile(wd_ifolder, inpfile)
    if not p: p,_,_ =   read_inputfile(f"{reference_ifolder}", inpfile)
    if filename:
        va              =   read_vascometa(vascometafile=filename, wd_ifolder=wd_ifolder)
    else:
        va          =   val_dict or []
    
    p.update((k, va[k]) for k in set(va).intersection(p))

    if new_wd and Path(new_wd).exists():
        wd_ifolder = new_wd
    create_config(p, f'{wd_ifolder}/{inpfile}')
    
def array_finetune_read(p: dict) -> dict:
    C_LEN = 15
    result = {}
    for k, v in p.items():
        if k.startswith('calib_'):
            if isinstance(v, str) and ';' in v:
                
                parts = [x.strip().strip("'\"") for x in v.split(';')]
                
                parts = (parts + [''] * C_LEN)[:C_LEN]
                result[k] = parts
            else:
                
                result[k] = [v] + [''] * (C_LEN - 1)
        else:
            result[k] = v
    return result


def array_finetune_write(p):
    for k,v in p.items():
        if 'calib_' in k and type(v) is list:
            p[k] = f"""{' ; '.join(str(vv) if str(vv) else "''" for vv in v)}"""
    return p

def update_array_finetune(wd_ifolder, new_wd=None, dic_p={}):
    p, files, folder = read_inputfile(wd_ifolder, 'array_finetune.inp')    
    
    if dic_p: p.update(dic_p)
    p['fringe_minSNR_mb_short_cal'] = 4
    p['fringe_minSNR_mb_reiterate'] = 3.38
    p['minblperant_cmplx_bandpass'] = 3
    p['minsnr_cmplx_bandpass']  =   3.8
    p['fringe_mbdelay_smoothtime'] = '60.'
    p['fringe_instrumental_method'] = 'constant'
    p['sbd_no_stationflag'] = 'False'
    p['solvemode_scalar_bandpass'] = 'const'
    p['solnorm_cmplx_bandpass'] = 0.75
    
    p['flagged_calib_thresh']   =   "0.4"
    if new_wd: wd_ifolder = new_wd
    cpath = Path(wd_ifolder) / 'array_finetune.inp'
    p_l = update_array_finetune_values(p)
    
    create_config(p_l, cpath, lj=31)
    # print("created", f'{cpath}' )

def update_array_finetune_values(p):
        if 'array_type' in p: del p['array_type']
        p_l = array_finetune_read(p)
        
        iD = int(p_l['C_DIG'])
        iGFD = int(p_l['C_GFD'])
        p_l['calib_accor'][iD] = 'ACCOR'
        p_l['calib_tsys'][iD] = 'TSYS'
        p_l['calib_gaincurve'][iGFD] = ''
        p_l['calib_scalar_bandpass'][iD] = 'SC_BP'
        p_l['calib_complex_bandpass'][iD] = 'C_BP'
        p_l['calib_fringefit_solint_cal'][iD]   =   'None'
        p_l['calib_fringefit_solint_sci'][iD]   =   'None'
        p_l['calib_fringefit_single'][iD]   =   'None'
        p_l['calib_fringefit_multi_cal_coher'][iD]  =   'None'
        p_l['calib_fringefit_multi_cal_short'][iD]  =   'None'
        p_l['calib_fringefit_multi_sci_long'][iD]   =   'multi_sci_long'
        p_l['calib_fringefit_multi_sci_short'][iD]  =   'multi_sci_short'
        p_l['calib_atmo_selfcal_startmod'][iD]  =   'None'
        p_l['calib_rldelay'][iD]    =   'None'
        p_l['calib_rlphase'][iD]    =   'None'
        p_l['calib_dterms'][iD] =   'None'
        p_l['calib_phase_offsets_ALMA'][iD] =   'None'
        p_l['calib_alignbands_ffospws'][iD] =   'None'
        p_l['calib_coarse_phbpass_ffospws'][iD] =   'None'
        p_l = array_finetune_write(p_l)
        return p_l

def fillinp_fromiwd(iwd, iwd_b):
    # Update observation.inp
    update_from_vascometa(iwd, val_dict=defaultdict(), new_wd=iwd_b, inpfile='observation.inp')
    
    #  Update array.inp
    update_from_vascometa(iwd, val_dict=defaultdict(), new_wd=iwd_b, inpfile='array.inp')

    # Update array_finetune.inp
    update_array_finetune(iwd, new_wd=iwd_b)

    # Update constants.inp
    update_constants(iwd, new_wd=iwd_b)

    # Update flagging.inp
    update_from_vascometa(iwd, val_dict=defaultdict(), new_wd=iwd_b, inpfile='flagging.inp')


def update_obsfrom_vascometa(wd_ifolder, sources_dict=None, new_wd=None, band=None):
    obs , files, folder = read_inputfile(wd_ifolder, 'observation.inp')
    
    s = sources_dict if sources_dict else read_vascometa(wd_ifolder=wd_ifolder)
    if s['calibrators_phaseref'] and not s['calibrators_instrphase']:
        s['calibrators_bandpass'] = s['calibrators_instrphase']     =   s['calibrators_phaseref']
    s['calibrators_rldly'] =   [s['calibrators_instrphase'][0]]                              # HACK : we need calibrators_rldly for non-polarization calibration as well
    obs.update(s)
    # if band:                                                                                # FIXME: The changing of observation.inp was not suitable so I have removed. e.g if band=S2, but _S is added
    #     if not f'_{band}.ms' in obs['ms_name']:
    #         obs['ms_name']            =   obs['ms_name'].replace('.ms', f'_{band}.ms')
    if 'array_type' in obs: del obs['array_type']
    if new_wd and Path(new_wd).exists():
        wd_ifolder = new_wd
    create_config(obs, f'{wd_ifolder}/observation.inp')


def fill_input_byvalues(wd_ifolder, iwd_b, vis, target,flux_thres, n_calib,  caliblist_file, sourcesf,
                        refantsf, sourcesf_snr , band=None, edgeflagging=True, pipe_params=None, hi_freq_ref=11):
    success                             =   False
    from vasco.ms import identify_sources_fromsnr_ms, get_antenna_name, has_table, get_reffreq
    
           
    
    
    try:
        sources_with_snr                =   read_vascometa(vascometafile=sourcesf)
        s                               =   identify_sources_fromsnr_ms(vis=vis, target_source=target, 
                                                                caliblist_file=caliblist_file ,
                                                                        snr_metafile=sourcesf, outfile=sourcesf_snr,
                                                                        flux_thres=flux_thres, min_flux=flux_thres, ncalib=n_calib)
        if band:    s                   =   s[band]
        for k,v in s.items():
            
            if s[k] and len(s[k])>=2:
                for source_name in s[k]:
                    if source_name not in sources_with_snr['NAME']:
                        s[k].remove(source_name)
        # print(s)
        # Update observation.inp
        update_obsfrom_vascometa(wd_ifolder, sources_dict=s, new_wd=iwd_b, band=band)
        
        #  Update array.inp
        refants_d                       =   read_vascometa(vascometafile=refantsf)
        if 'refants' in refants_d: refants_d['refant'] = refants_d['refants']
        
        refants_d['array_type']             =   get_antenna_name(vis)
        if get_reffreq(vis)>hi_freq_ref and all(has_table(vis, "WEATHER", "SYSTEM_TEMPERATURE")):
            refants_d['array_type']         =   refants_d['array_type'] + 'hi'
        
        update_from_vascometa(wd_ifolder, val_dict=refants_d, new_wd=iwd_b, inpfile='array.inp')

        dict_arr_ft = {}
        
        if pipe_params and 'accor_solint' in pipe_params and pipe_params['accor_solint'] : 
            dict_arr_ft['accor_solint'] = pipe_params['accor_solint']
        
        update_array_finetune(wd_ifolder, new_wd=iwd_b, dic_p=dict_arr_ft)

        # Update constants.inp
        update_constants(wd_ifolder, new_wd=iwd_b)

        flagging_d = {
            'flag_from_metadata' : True,
            'aply_from_idifile': True,
            'flag_autocorr_vs_freq' : False,
            'flag_autocorr_vs_time' : False,
            'begi_quacking' : 1,
            'end_quacking':1,
            'flag_quacking':False,
            'flag_edge_channels' : edgeflagging,
            'numo_edge_channels' : "7,7",
        }
        
        
        # Update flagging.inp
        update_from_vascometa(wd_ifolder, val_dict=flagging_d, new_wd=iwd_b, inpfile='flagging.inp')

        success                         =   True
    except:
        traceback.print_exc()
        success                         =   False    
    return success







# ----------       Utilities

def get_allfitsfiles(folder_for_fits, depth=3):
    allfiles = []
    # Find all files for operation
    pattern = ""
    prev_dir = ""
    for i in range(depth):
        matched_files = glob.glob(f"{folder_for_fits}{pattern}*fits")
        allfiles.extend(matched_files)
        pattern += "*/"
        if "." in folder_for_fits:
            break
    if not allfiles:
        allfiles.extend(glob.glob(f"{folder_for_fits}/*fits"))
    return allfiles

def build_path(filepath):
    opt = filepath
    if Path(filepath).exists():
        numb = 1
        while Path(filepath).exists():
            filepath = "{0}_{2}{1}".format(
                *(Path(opt).parent / Path(opt).stem, Path(opt).suffix,numb))
            if (filepath is not None) and (Path(filepath).exists()):
                    numb += 1 
    return filepath

class   FileSize:
    def __init__(self, dest, u='GB'):
        
        p               =   subprocess.run(['du', '-sb', dest], capture_output=True)
        self.B          =   float(p.stdout.split(b'\t')[0])
        self.KB, self.MB, self.GB, self.TB, self.PB         =   self._find_size()

        self.u          =   u
        self.v          =   f"{self.get_size(u)} {u}"

    def _find_size(self):
        __KB = self.get_size('KB')
        __MB = self.get_size('MB')
        __GB = self.get_size('GB')
        __TB = self.get_size('TB')
        __PB = self.get_size('PB')
        return __KB, __MB, __GB, __TB, __PB
    
    def get_size(self, u):
        if u        == 'KB' : val   =   1
        elif u      == 'MB' : val   =   2
        elif u      == 'GB' : val   =   3
        elif u      == 'TB' : val   =   4
        elif u      == 'PB' : val   =   5
        self.u = u
        return np.round((self.B / (1024)**val), 2)

    def __str__(self):
        return self.v
    
def symlink_bywd(wd, fitsfile, create=True):
    rawsymlink          =   f"{wd}/raw/{Path(fitsfile).name}" 
    
    if create : 
        Path(f"{wd}/raw").mkdir(parents=True, exist_ok=True)
        os.symlink(fitsfile, rawsymlink)
    return rawsymlink

def get_project(fitsfile):
    segment     =   ''#str(Path(fitsfile).parent.name)
    if not len(segment):
        from vasco.fitsidiutil import read_idi
        hdul = read_idi(fitsfile)
        segment = hdul[0].header['OBSERVER']
        
        
    return str(segment)

def iwd_for_fitsfile(fitsfile, target_dir, ifolder=None, create=False, splitted=False, allwds=False):
    """
    looks for wd using project name
    """
    new                 =   True
    segment             =   get_project(fitsfile)
    wd                  =   f"{target_dir}{segment}/wd"
    wd_ifolder          =   None
    lookfile            =   fitsfile if not splitted else f"{str(Path(fitsfile).stem)}_split{Path(fitsfile).suffix}"
    possible_file       =   symlink_bywd(wd, fitsfile, create=False)
    if create:
        if ifolder is None:
            raise FileNotFoundError(f"ifolder : {ifolder}")
        
        if not Path(f"{wd}/raw/{Path(lookfile).name}").exists():
            wd                  =   build_path(wd)
        try:
            _ = symlink_bywd(wd, fitsfile)
            wd_ifolder          =   [f'{wd}/input_template/']
            if not Path(wd_ifolder[0]).exists():shutil.copytree(ifolder,wd_ifolder[0])
        except Exception as e:
            print(f"exists? : {segment} : {e}")
            new             =   False
        new             =   False
    else:
        possible_files = glob.glob(f'{wd}*/raw/{Path(lookfile).name}')
        if len(possible_files):
            possible_file = possible_files[0]
            # print(f"duplicates found: \n{' '.join(possible_files[1:])}")
            new = False
        wd_ifolder = [Path(possible_file).parent.parent / "input_template"]
        if allwds: wd_ifolder = [Path(possible_file).parent.parent / "input_template" for possible_file in possible_files]
    return wd_ifolder, new


def get_wd_ifolder(fitsfile, target_dir, ifolder):
    iwd, new                =   iwd_for_fitsfile(fitsfile, target_dir, ifolder)
    if new: iwd, new        =   iwd_for_fitsfile(fitsfile, target_dir, ifolder, create=True)
    return iwd

def single_ifcheck(nchan, chwidth, nchan_default=16, chwidth_bound=500.0):
    chanbin = 1    
    if chwidth < chwidth_bound: # and nchan>nchan_default:
        chanbin = int(chwidth_bound // chwidth) or 1
        nchan_new = nchan/chanbin
        if nchan%nchan_new:      # to see if rounding off has happened.
            print(f"WARN! selected bin is {chanbin}, atleast {nchan%nchan_new} will not be included.")
        print(f"{nchan} channels will be squeezed to {int(nchan_new)} with a bin of {chanbin}")
    return chanbin

def latest_file(path: Path, pattern: str = "*"):
    files = path.glob(pattern)
    lastf = Path('')
    try:
        lastf = max(files, key=lambda x: x.stat().st_ctime)
    finally:
        return lastf
    
# ------------- DataFrame adjustments -----------------

def split_band_and_data(x):
    from pandas import Series
    # x = x[:2]  # Skip first two characters
    parts = x.split(':', 1)  # Split on the first colon only
    if len(parts) == 2:
        return Series([parts[0], parts[1]])
    else:
        return Series([None, None])  # or use x and None


def split_and_stack_multiple_cols(dfsheet, cols):
    """
    Only for columns containing values = [f"{band}: float]

    Splits and stacks multiple columns in a DataFrame.
    Params:
        dfsheet (pd.DataFrame): The input DataFrame.
        cols (list): List of column names to process.

    Returns:
        pd.DataFrame: A DataFrame with split and stacked rows for all specified columns.
    """
    # from pandas import DataFrame as df
    import pandas as pd
    result_df = pd.DataFrame()

    for col_name in cols:
        split_df = dfsheet[col_name].str.strip().str.split(" ", expand=True).stack().reset_index(level=1, drop=True).reset_index(name=col_name)
        split_df[['band', col_name]] = split_df[col_name].apply(split_band_and_data)
        
        split_df[col_name] = split_df[col_name].str.strip()
        converted = pd.to_numeric(split_df[col_name], errors='ignore')
        if pd.api.types.is_numeric_dtype(converted):
            split_df[col_name] = converted
        else:
            split_df[col_name] = split_df[col_name].astype(str)

        if result_df.empty:
            result_df = split_df
        else:
            result_df = result_df.merge(split_df, on=['index', 'band'], how='outer')

    return result_df

"""OLDER SCRIPT below"""
# def split_and_stack_multiple_cols(dfsheet, cols):
#     """
#     Only for columns containing values = [f"{band}: float]

#     Splits and stacks multiple columns in a DataFrame.
#     Params:
#         dfsheet (pd.DataFrame): The input DataFrame.
#         cols (list): List of column names to process.

#     Returns:
#         pd.DataFrame: A DataFrame with split and stacked rows for all specified columns.
#     """
#     from pandas import DataFrame as df
#     result_df = df()

#     for col_name in cols:
#         split_df = dfsheet[col_name].str.split(expand=True).stack().reset_index(level=1, drop=True).reset_index(name=col_name)
#         split_df[['band', col_name]] = split_df[col_name].str.split(':', expand=True)
#         try:
#           split_df[col_name] = split_df[col_name].astype(float)
#         except:
#           split_df[col_name] = split_df[col_name].astype(str)

#         if result_df.empty:
#             result_df = split_df
#         else:
#             result_df = result_df.merge(split_df, on=['index', 'band'], how='outer')

#     return result_df

# ------------ read fringefit_overview csv ------------

# def good_solutions(lf, wd_ifolder, count, failed, snr, col = 'good_solutions', ignore_flagged=False):
#     phref=False
#     from pandas import read_csv, DataFrame as df
#     success, success_count             =   '', 0
#     t0 = time.time()
#     minsnr = 0 if ignore_flagged else -1
        
#     metafile            =   Path(wd_ifolder).parent / 'vasco.meta' / 'msmeta_sources.vasco'
#     metd                =   read_metafile(metafile)

#     bands_dict                      =   read_metafile(metafile)['bands_dict']
#     bands                           =   list(bands_dict.keys())
#     target                          =   Pipeline.params['target']
#     for band in bands:
#         ct = 0
#         wd, iwd_b                       =   to_new_WD(wd_ifolder, band, target=target)
#         obs_b, _, _                       =   read_inputfile(iwd_b, "observation.inp")
#         target_source                   =   Pipeline.params['target']
        

#         ffoverview                      =   latest_file(Path(iwd_b).parent,"diagnostics_*/fringes_overview.csv.sci*")
#         if not len(str(ffoverview))>5 or not ffoverview.exists():
#             if obs_b['calibrators_phaseref'] and obs_b['calibrators_phaseref'].lower()!='none':
#                 phref=True
#                 # idx_target = obs_b['science_target'].index(target_source)
#                 target_source = obs_b['calibrators_phaseref']
#             ffoverview                  =   latest_file(Path(iwd_b).parent,"diagnostics_*/fringes_overview.csv.cal*")
#         # print(ffoverview)
#         if ffoverview.exists() and '.csv' in str(ffoverview):
#             success_count               +=  1
            
#             dfcsv                          =   read_csv(str(ffoverview))
#             dfcsv['Source']                =   [str(sc) for sc in dfcsv['Source']]
#             df_source                   =   dfcsv.loc[dfcsv['Source'].str.startswith(target_source)]
            
#             total_solutions             =   df_source.loc[df_source['SNR']>minsnr]['Detection'].count()
#             total_solutions             =   total_solutions if total_solutions > 0 else 0.01
#             good_solution_percentage    =   np.round((df_source.loc[df_source['SNR']>snr]['Detection'].count()/total_solutions)*100, 2)
#             success                     +=  f'{band}:{good_solution_percentage}% '
            
            
#         else:
#             failed += 1
            
#     if phref:
#         _           =   lf.put_value(f"phref {target_source}", "Comment fill_input", count)
#     print(col, success, success_count)
#     if success_count>=0:
#         # _           =   lf.put_value('partial', comment_col, 0)
#         count       =   lf.put_value(success, col, count)

#     return count, failed

# ------------ IMAGING code essentials ----------------
    
# def imaging_entropy(lf, wd_ifolder, count,failed, uvf=None, col='imaging_task', version='', selfcal=False):
#     from pandas import read_csv, DataFrame as df
    
#     t0 = time.time()
#     metafile                        =   Path(wd_ifolder).parent / 'vasco.meta' / 'msmeta_sources.vasco'
#     target                          =   lf.get_value('TARGET_NAME')
#     bands_dict                      =   read_metafile(metafile)['bands_dict']
#     bands                           =   list(bands_dict.keys())
#     errf                            =   ''
#     suffix                          =   '' if not selfcal else '_self'
#     col_value   =   ''
#     img_keys = {f'noise_estimate':'',f'total_flux':'' ,f'resid_rms':'', f'clean_map_peak':'' ,f'clean_map_rms':'' ,f'far_field_rms':'' ,f'dynamic range':'' ,f'uv_chisq':''}

#     for band in bands:
#         ct = 0
#         wd, iwd_b                       =   to_new_WD(wd_ifolder, band, target=target)
#         obs, _, _                       =   read_inputfile(wd_ifolder, "observation.inp")
#         if uvf is None: uvf             =   f"{target}_calibrated.uvf"
#         target_stem                     =   str(Path(uvf).stem)
#         uvave                           =   f"{target}_calibrated.uvave"

#         if Path(f'{str(wd)}/{uvf}').exists():
            
#             if selfcal:
            
#                 csvfile                         =   f"{wd}/imaging_result{version}{suffix}/{target_stem}/{target_stem}.icn{suffix}.stats.csv" #TODO: path should be absolute - Add method in argparse of the imaging_with_clean to create folder and files on this abs path
#             else:
#                 csvfile                         =   f"{wd}/imaging_result{version}/{target_stem}/{target_stem}.icn.stats.csv" #TODO: path should be absolute - Add method in argparse of the imaging_with_clean to create folder and files on this abs path
                
#             del_fl(f"{wd}/imaging_result{version}{suffix}/{target_stem}/", rm=True)
#             del_fl(f"{wd}/data_uvave{version}/", rm=True)
            
#             Path(f"{wd}/data_uvave{version}/").mkdir(exist_ok=True)
            
#             cmd0    =   ['python3', f'/data/avi/gh/imaging_with_clean{version}/time_averaging.py', f'{str(wd)}/{uvf}']
            
#             cmd1    =   ['python3', f'/data/avi/gh/imaging_with_clean{version}/imaging_clean_main.py', f'{str(wd)}/data_uvave{version}/{uvave}']
#             if selfcal : cmd1 += ['--selfcal']
            
#             try:
#                 print(" ".join(cmd0))
#                 res0     =   subprocess.run(cmd0, stdout=subprocess.PIPE, timeout=240)
#                 print(" ".join(cmd1))
#                 res1     =   subprocess.run(cmd1, stdout=subprocess.PIPE, timeout=3200)
                
#             except Exception as e:
#                 print(e)
#                 failed+=1
#             if Path(csvfile).exists():
#                 count+=1
#                 df_csv = read_csv(csvfile)
#                 for vcol, v in img_keys.items():
#                     val                     =   df_csv.loc[df_csv['Variable']==vcol]['Value'].values[0]
#                     img_keys[vcol]           =   v+f" {band}:{val}" if v else v+f"{band}:{val}"
#                     ct = lf.put_value(img_keys[vcol], f"{vcol}{suffix}", 0)
#             else:
#                 print(csvfile, "not found!")
#         if ct>0: count+=1    
#     t1 = time.time()
#     td = timeinmin(t1-t0)
#     lf.put_value(td, col, 0)
#     return count, failed

def calc_vis_perc(fitsfile, calibrated=False):
    from astropy.io import fits
    hdul = fits.open(fitsfile)
    hdul
    
    
    
    
    
# ____________                  ___________________
#               steps helpers
# __________________________________________________



# def run_vasco(wd_ifolder, cmd_args, n_cores=1, ants=[], sources=[], spws=[]):
#     """
#     can handle vasco with or without mpi and runs inside the casapy38 environment
#     """
#     print(wd_ifolder, cmd_args, n_cores)
#     success = False
#     t0 = time.time()
#     try:
#         thisdate    =   time.strftime('%F-%T', time.gmtime())
#         thisdate    =   thisdate.replace(':', '_')
#         wd          =   Path(wd_ifolder).parent
#         errlogf     =   str(wd / f'mpi_and_err.out_{thisdate}')
#         casalogf    =   str(wd / f'casa.log_{thisdate}')
        
#         if not '--wd' in cmd_args: 
#             cmd_args += ['--wd', str(wd)]

#         casadir = '/data/avi/env/rPicard/casa-CAS-14169-1-py3.8.el7/bin'    #open(os.path.join(pipedir, 'your_casapath.txt')).read().strip()
#         os.system('ulimit -n 24576 &>/dev/null')
#         if n_cores>1:
#             cmd     =   [f'{casadir}/mpicasa', '--oversubscribe', '-n', str(n_cores), 
#                          f'{casadir}/casa', '--agg', '--nogui', '--logfile', casalogf, '-c',  
#                          '/data/avi/env/casapy38/bin/vasco'] + cmd_args
#         else:
#             cmd     =   ['/data/avi/env/casapy38/bin/vasco'] + cmd_args
        
#         if ants and len(ants):
#             cmd     +=  ['--ants', ",".join(ants)]
#         if sources and len(sources):
#             cmd     +=  ['--sources', ",".join(sources)]
#         if spws and len(spws):
#             # spws    =   
#             cmd     +=  ['--spws', ",".join([str(spw) for spw in spws])]

#         success     =   True
#         print(" ".join(cmd))
#         subprocess.run(cmd, stderr=open(errlogf,"+a"))
#     except Exception as e:
#         print(f"\n***\n   Oops, something went wrong:\n   {str(e)}\n***\n")
#         traceback.print_exc()
#         if Path(errlogf).exists():
#             print(errlogf)
#             proc = subprocess.Popen(['tail', '-n', '100', errlogf], stdout=subprocess.PIPE)
#             lines = proc.stdout.read()
#             print(lines.decode('utf-8'))
#         if Path(casalogf).exists():
#             print(casalogf)
#             proc = subprocess.Popen(['tail', '-n', '20', casalogf], stdout=subprocess.PIPE)
#             lines = proc.stdout.read()
#             print(lines.decode('utf-8'))
#         sys.exit(1)
#     t1 = time.time()
#     td = timeinmin(t1-t0)
#     return success, td, errlogf, casalogf


#   ..  ..... for vasco_antab ................................................

def proj_search(url, proj):
    urls  = []
    found = False
    res   = None

    try:
        with urllib.request.urlopen(url) as response:
            html = response.read().decode('utf-8')
    except URLError:
        return res, found, urls

    res = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)

    for r in res:
        row_text = re.sub(r'<[^>]+>', ' ', r)
        
        row_text_sep = row_text.split()
        row_res  = row_text_sep[0] if row_text_sep else ''

        link_match = re.search(r'<a[^>]+href=["\']([^"\'?]+)["\']', r, re.IGNORECASE)
        link_text  = link_match.group(1).strip('/') if link_match else ''

        if all(c.lower() in row_res.lower() for c in [proj, 'cal.vlba']) or \
           all(c.lower() in row_res.lower() for c in [proj, '.tsys']):
            urls.append(url + f"/{link_text}")
            found = True

    return res, found, urls

def find_url_tsys(fitsfile, proj=''):
    """
    TODO: if it is EVLA observation you need ppppcal.y for VLA refer https://science.nrao.edu/facilities/vlba/calibration-and-tools/caliblogs
    """
    from vasco.fitsidiutil.io import FITSIDI
    hdul    =   FITSIDI(fitsfile).read()
    head    =   hdul[0].header
    url     =   'https://www.vlba.nrao.edu/astro/VOBS/astronomy/'

    dateobs =   head['DATE-OBS']
    proj    =   str(head['OBSERVER']).strip()
    dateobs =   str(dateobs).strip().split('/')

    if not len(dateobs)==3:
        dateobs = dateobs[0].split('-')
        yy  =   dateobs[0][-2:]
    else:
        yy  = dateobs[2]
    mmm     =   ['','jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'][int(dateobs[1])]

    url     =   url+mmm+yy
    
    res, found, urls = proj_search(url, proj)

    if not found and res:
        for r in res:
            row_res = r.get_text().split(' ')[0]
            
            if proj.lower() in row_res.lower():
                url = url + f'/{r.contents[1].text}'
                res, found, urls = proj_search(url, proj)
                if not found and res:
                    url = url + 'jobs/'
                    res, found, urls = proj_search(url, proj)
    if not found:
        res, found, urls = proj_search(url, proj.replace('0', ''))          # sometimes project name without zeros are stored as names of the cal.vlba file
        
        
    return urls


def del_fl(wd:str, count:int=0, fl:str='*ms*', rm:bool=False):
    """delete files from the input folder

    Args:
        wd (str): where to look for the file
        count (int, optional): _description_. Defaults to 0.
        fl (str, optional): _description_. Defaults to '*ms*'.
        rm (bool, optional): _description_. Defaults to False.

    Returns:
        _type_: _description_
    """
    
    wd          =   Path(wd)
    filefound = glob.glob(f"{str(wd)}/{fl}")
    if len(filefound):
        cmd = ['rm','-rf']
        cmd.extend(str( wd / " ".join(filefound)).split(' '))
        print(" ".join(cmd))
        count+=1
        if rm: 
            subprocess.run(cmd)
    return count

def find_tsys(wd_ifolder, fitsfile, count, failed):
    import urllib.request
    durl        =   find_url_tsys(fitsfile)
    rawfs       =   []
    
    if durl:
        
        for url in durl:
            rawf        =   Path(wd_ifolder).parent / 'raw' / Path(url).stem / Path(url).name
            del_fl(rawf.parent.parent,fl=str(Path(url).stem), rm=True)
            rawf.parent.mkdir(exist_ok=True)
            rawf        =   f"{str(rawf)}"
            del_fl(rawf, rm=True)
            rawfs.append(rawf)
            urllib.request.urlretrieve(url, rawf)
            
    if rawfs:
        count+=1
    else:
        failed+=1
    return count, failed, rawfs

def overlap_percentage(A_start, A_end, B_start, B_end):
    lenB = B_end - B_start
    overlap = max(0, min(A_end, B_end) - max(A_start, B_start))
    overlap_perc = np.round((overlap / lenB),4) * 100 if lenB > 0 else 0
    return overlap_perc


def tsys_exists(fitsfile, valid_perc=5, verbose=False):
    from vasco.fitsidiutil.io import FITSIDI
    from vasco.fitsidiutil.op import get_yyyymmdd
    from astropy.time import Time
    
    success                 =   False
    fo                      =   FITSIDI(fitsfile, mode='r')
    hdul = fo.read()
    fo.close()
    
    scale_dateobs, scale_time = 'utc', 'tai'

    starttime_tsys, starttime_uvd   =   None, None
    lasttime_tsys, lasttime_uvd     =   None, None
    if verbose: print("checking TSYS :", fitsfile)
    i_uvd                           =   0
    for hdu in hdul:
        if 'DATE-OBS' in hdu.header:
            refdate = hdu.header['DATE-OBS']
            if '/' in refdate:
                yyyy,mm,dd         =   get_yyyymmdd(dateobs=refdate)
                refdate         =   f"{yyyy}-{mm:02}-{dd:02}"
                
            zerotime=Time(refdate, format='isot',scale='utc')
        if hdu.extname == 'UV_DATA' and hdu.nrows:
            hdutime         =   np.array(hdu['TIME'])
            refdate_uvd     =   np.array(hdu['DATE'])
            nrow            =   hdu.nrows
            
            szero           =   Time(refdate_uvd[0], format='jd', scale='tt')
            ezero           =   Time(refdate_uvd[-1], format='jd', scale='tt')
            lastt           =   hdutime[-1]
                
            with fo.open("r") as fop:
                hdul_chunk  =   fop.read(10, start_row=nrow-6)
                ezero           =   Time(hdul_chunk['UV_DATA']['DATE'][-1], format='jd', scale='tt')
                lastt           =   hdul_chunk['UV_DATA']['TIME'][-1]
            if i_uvd==0:
                starttime_uvd   =   Time(szero.mjd+hdutime[0], format='mjd', scale='tt')
            lasttime_uvd    =   Time(ezero.mjd+lastt, format='mjd', scale='tt')            
            i_uvd           +=  1
            
        if hdu.extname == 'SYSTEM_TEMPERATURE':
            success         =   True
            hdutime         =   np.array(hdu['TIME'])

            zerotime        =   Time(refdate, format='isot',scale='utc')
            scantime        =   Time(zerotime.mjd+hdutime, format='mjd', scale='tt')

            lasttime_tsys   =   max(scantime) if scantime else None
            starttime_tsys  =   min(scantime) if scantime else None
            
    if lasttime_tsys is None:
        success             =   False
        if verbose: print("TSYS missing!")
    else:
        if overlap_percentage(starttime_tsys.mjd, lasttime_tsys.mjd, starttime_uvd.mjd, lasttime_uvd.mjd)>valid_perc:
                success     =   True
        else:
            if verbose: print(f"<{valid_perc}% overlap b/w SYSTEM_TEMPERATURE and UV_DATA tables for {fitsfile}")
            success         =    False
                
    return success, starttime_tsys, lasttime_tsys, starttime_uvd, lasttime_uvd
    
def tsys_exists_in_fitsfiles(fitsfile, fitsfiles, valid_perc=5, verbose=True):
    best_fitsfile =""
    ref_ov_perc = 0.0
    success = False
    for ff in fitsfiles:
        
        if not fitsfile in ff:
            success, stff, ltff, stu, ltu = tsys_exists(ff, valid_perc=valid_perc)
            if not stff is None:
                ov_perc =overlap_percentage(stff.mjd, ltff.mjd, stu.mjd, ltu.mjd)
                if ref_ov_perc<ov_perc:
                    ref_ov_perc = ov_perc
                    best_fitsfile = fitsfile
                
                if ov_perc>valid_perc:
                    success = True
                    # if verbose: print(f"Around {np.round(ov_perc,2)}% of data is overlapping TSYS values!")
                    
                else:
                    missing_perc = np.round(100.0-ov_perc, 2)
                    if verbose: print(f"Around {missing_perc}% of data is missing TSYS values!")
    if verbose: print("TSYS found in", Path(ff).name, "for", Path(best_fitsfile).name, f"( {(np.round(ref_ov_perc,2))}% )")
                
    return success


def attach_antab(self, only_first=True, attach_all=False):
        """
        
        """
        antabfile                       =   Path(self.wd) / 'gc_dpfu_fromidi.ANTAB'
        self.success, self.desc         =   False, "Failed"
                
        for i, fitsfile in enumerate(self.workingfits):
            antabfile                   =   Path(self.wd) / f'gc_dpfu_fromidi.ANTAB.{i}'
            del_fl(Path(self.wd), fl=f'gc_dpfu_fromidi.ANTAB.{i}', rm=True)
            tsys_found, _, _ , _, _     =   tsys_exists(fitsfile)
            if not tsys_found:
                if self.verbose: print("TSYS not found! Searching in other fitsfile")
                
                fitsfiles_toattach_antab = self.workingfits if not attach_all else [fitsfile]    
                if not tsys_exists_in_fitsfiles(fitsfile, fitsfiles_toattach_antab, self.valid_perc):
                    if self.verbose: print("TSYS not found in other fitsfiles")
                    if len(fitsfiles_toattach_antab)>1:
                        self.sort_by_time()
                        print("SORTED by time : ", self.workingfits)
                    self.find_and_attach_antab(fitsfile=fitsfile, antabfile=antabfile, fitsfiles=fitsfiles_toattach_antab, attach_all=attach_all) # changed fitsfile = self.workingfits[0] to fitsfile = fitsfile
                    if only_first:   break
                else:
                    if self.verbose: print("TSYS exists in another fitsfile!")
        if self.verbose: print("Attaching TSYS finished!")



class GenerateAndAppendAntab:
    def __init__(self, fitsfiles, targets, metafolder, verbose, wd, valid_perc=5):
        
        self.fitsfiles                  =   fitsfiles
        self.targets                    =   targets
        self.metafolder                 =   metafolder
        self.verbose                    =   verbose
        self.wd                         =   wd
        self.valid_perc                 =   valid_perc
        
        self.success                    =   None
        self.desc                       =   ""
        
        self.tsysfiles                  =   set()
    
    def find_and_attach_antab(self, fitsfile, fitsfiles, antabfile, attach_all, verbose=False):
        from vasco.idifits import ANTAB, get_dateobs, parse_antab
        from vasco.external import append_tsys as TsysData, append_gc as GCData
        
        ans_found                       =   set()
        dic_gf                          =   {}
        found_gf                        =   ''
        gain_missing                    =   []
        bsize                           =   float(FileSize('/dev/null').B)
        
        
        if self.verbose: print("finding tsys...")
        _, failed, rawfs            =   find_tsys(f"{self.wd}/raw", fitsfile, 0, 0)                         
        if not rawfs:
            self.success, self.desc =   False, "Downloading failed!"
            print(self.desc)
        else:
            for i,gf in enumerate(rawfs):
                if (not '.tsys' in gf):
                    print("using", gf)
                    for gzippable_format in ['.Z', '.gz']:
                        if gzippable_format in gf:
                            subprocess.run(['gzip', '-d', gf])
                            gf          =   gf.replace(gzippable_format,'')
                    if attach_all or not gf in self.tsysfiles:
                        try:
                            an              =   ANTAB(fitsfile, gf)
                            anfile          =   f'{antabfile}.{i}'
                            allans, _tsys_head, gain_missing    = an.gen_antab(anfile)
                            if bsize<float(FileSize(gf).B):
                                found_gf    =   gf
                                bsize       =   float(FileSize(gf).B)
                            if allans:  dic_gf[gf]=allans,gain_missing,anfile
                            ans_found.update(allans)
                        except Exception as e:
                            print(gf, e)
                            traceback.print_exc()
                else:
                    print("not using", gf)
            for _file in dic_gf.keys():
                # if found_gf!=_file:
                #         del_fl(_file, rm=True)
                # else:
                #     found_gf = ''
                
                if _file and Path(dic_gf[_file][-1]).exists():
                    if Path(antabfile).exists() : Path(antabfile).unlink()
                    Path(dic_gf[_file][2]).rename(Path(self.wd) / antabfile)
                    t1              =   time.time()
                    self.tmpfs      =   deepcopy(fitsfiles)
                    

                    for i, ff in enumerate(fitsfiles):
                        tmpf            =   f"{Path(ff)}.tmp"
                        self.tmpfs[i]   =   tmpf
                        if Path(tmpf).exists(): Path(tmpf).unlink()
                        shutil.copy(str(Path(ff).absolute()), tmpf)
                            
                    # self.sort_by_time()
                    alldobs = [get_dateobs(fitsfile_tmp) for fitsfile_tmp in self.tmpfs]
                    dict_res = parse_antab(antabfile=antabfile, fitsfile=self.tmpfs[0])
                    print(dict_res.keys())
                    antab_start_time    = dict_res["tsys_dic"]['start_time']
                    antab_end_time      = dict_res["tsys_dic"]['end_time']
                    # print(antab_start_time, antab_end_time, alldobs)
                    # print(self.tmpfs)
                    
                    if any(antab_start_time.date() <= dobs.date() <= antab_end_time.date() for dobs in alldobs):
                        for idifile in self.tmpfs:
                            if verbose: print(f"....appending System Temperature to {idifile}")
                            TsysData.append_tsys(antabfile=antabfile, idifiles=idifile, replace=True)
                            if verbose: print(f"....appending Gain Curve to {idifile}")
                            GCData.append_gc(antabfile=antabfile, idifile=idifile, replace=True)
                        # cmd = ['/data/avi/env/casapy38/bin/python3','/data/avi/gh/casa-vlbi/append_tsys.py', str(antabfile)] + self.tmpfs + ["--replace"]
                        # print(" ".join(cmd))
                        
                        # subprocess.run(cmd)
                        # cmd = ['/data/avi/env/casapy38/bin/python3', '/data/avi/gh/casa-vlbi/append_gc.py', str(antabfile) ] + self.tmpfs + ["--replace"]
                        # print(" ".join(cmd))
                        # subprocess.run(cmd)
                        
                    for i, ff in enumerate(fitsfiles):
                        tmpf            =   f"{Path(ff)}.tmp"
                        Path(ff).unlink()
                        Path(tmpf).rename(ff)
                        self.tmpfs[i]   =   ff
                    self.tsysfiles.add(gf)
    
    def attach_antab(self, only_first=True, attach_all=False):
        """
        
        """
        antabfile                       =   Path(self.wd) / 'gc_dpfu_fromidi.ANTAB'
        self.success, self.desc         =   False, "Failed"
                
        for i, fitsfile in enumerate(self.workingfits):
            antabfile                   =   Path(self.wd) / f'gc_dpfu_fromidi.ANTAB.{i}'
            del_fl(Path(self.wd), fl=f'gc_dpfu_fromidi.ANTAB.{i}', rm=True)
            tsys_found, _, _ , _, _     =   tsys_exists(fitsfile)
            if not tsys_found:
                if self.verbose: print("TSYS not found! Searching in other fitsfile")
                
                fitsfiles_toattach_antab = self.workingfits if not attach_all else [fitsfile]    
                if not tsys_exists_in_fitsfiles(fitsfile, fitsfiles_toattach_antab, self.valid_perc):
                    if self.verbose: print("TSYS not found in other fitsfiles")
                    if len(fitsfiles_toattach_antab)>1:
                        self.sort_by_time()
                        print("SORTED by time : ", self.workingfits)
                    self.find_and_attach_antab(fitsfile=fitsfile, antabfile=antabfile, fitsfiles=fitsfiles_toattach_antab, 
                                               attach_all=attach_all, verbose=self.verbose) # changed fitsfile = self.workingfits[0] to fitsfile = fitsfile
                    if only_first:   break
                else:
                    if self.verbose: print("TSYS exists in another fitsfile!")
        if self.verbose: print("Attaching TSYS finished!")
# -------------------------------------------------------------------------------------------
    def sort_by_time(self):
        starttime = []
        endtime = []
        for i, fitsfile in enumerate(self.workingfits):
            success, starttime_tsys, lasttime_tsys, starttime_uvd, lasttime_uvd = tsys_exists(fitsfile, self.valid_perc)
            if starttime_uvd:
                starttime.append(starttime_uvd.mjd)
            else:
                print("UV data not found..")
                self.workingfits.remove(fitsfile)
        self.workingfits = [x for _, x in sorted(zip(starttime, self.workingfits), reverse=True)]
        return self.workingfits
    
    def sort_by_tsys(self):
        perc_ffs = []
        allsuccess = []
        for i, fitsfile in enumerate(self.workingfits):
            success, starttime_tsys, lasttime_tsys, starttime_uvd, lasttime_uvd = tsys_exists(fitsfile, self.valid_perc)
            if success:
                perc_ffs.append(overlap_percentage(starttime_tsys.mjd, lasttime_tsys.mjd, starttime_uvd.mjd, lasttime_uvd.mjd))
            else:
                perc_ffs.append(0.0)
            allsuccess.append(success or tsys_exists_in_fitsfiles(fitsfile, self.workingfits, self.valid_perc))
        self.workingfits = [x for _, x in sorted(zip(perc_ffs, self.workingfits), reverse=True)]
        allsuccess = [x for _, x in sorted(zip(perc_ffs, allsuccess), reverse=True)]
        return allsuccess
                                                                                              
    def validate(self):
        """
        tsys_exists_in_fitsfiles(fitsfile, self.fitsfiles)
        gc_exists_in_fitsfiles(fitsfile, self.fitsfiles)
        other things are already checked
        """
        
        self.success = all(self.sort_by_tsys())
        
        if self.success:
            self.desc = "TSYS found"
        else:
            self.desc = "TSYS not found!"
        
        return self.success

def meta_from_fitsfile(fitsfile, target, wd_ifolder, metafolder, reference_ifolder, do_manual_selection):
    from vasco.fitsidiutil.op import identify_refant
    metaf_refant_dict     =   str(Path(metafolder) / 'refants_fits.vasco')
    metaf_source_dict     =   str(Path(metafolder) / 'sources_fits.vasco')

    refant, refant_dict = identify_refant(fitsfile=fitsfile, n=4)
    
    
    source = {'calibrators_instrphase': [target], 
    'calibrators_bandpass': [target], 
    'calibrators_rldly': None, 
    'calibrators_dterms': None, 
    'calibrators_phaseref': None, 
    'science_target': None
    }
    
    if not do_manual_selection:
        raise NotImplementedError(f"identify sources from fitsfile")
        cmd_source      =   ['-t', fitsfile]
        run_vasco(wd_ifolder, cmd_args=cmd_source, sources=[target])
        source          =   read_vascometa(vascometafile=source_dict)
        
        if source and 'science_target' in source:  # if target in science and calibrator remove  target from science
            if source['science_target']:
                if target in source['science_target'] :
                    if source['calibrators_phaseref']:
                        if not source['calibrators_instrphase']:
                            source['calibrators_instrphase']    =   source['calibrators_phaseref']
                            
                        else:
                            source['calibrators_instrphase'] = list(set(source['calibrators_instrphase'].extend(source['calibrators_phaseref'])))
                        source['calibrators_phaseref']      =   None
                cal_instrph =   source['calibrators_instrphase'] or []
                cal_phref   =   source['calibrators_phaseref'] or []
                if sum([sst in set(cal_instrph+cal_phref) for sst in source['science_target']]):
                    source['science_target'] =  None

            
        source['calibrators_rldly'] =   source['calibrators_instrphase']
    if not Path(wd_ifolder).exists(): Path(wd_ifolder).mkdir()
    update_from_vascometa(wd_ifolder, inpfile='array.inp' ,val_dict=refant, reference_ifolder=reference_ifolder)
    update_from_vascometa(wd_ifolder, inpfile='observation.inp' ,val_dict=source, reference_ifolder=reference_ifolder)
    update_from_vascometa(wd_ifolder, inpfile='flagging.inp', reference_ifolder=reference_ifolder)
    update_from_vascometa(wd_ifolder, inpfile='array_finetune.inp', reference_ifolder=reference_ifolder)
    update_from_vascometa(wd_ifolder, inpfile='constants.inp', reference_ifolder=reference_ifolder)
    update_constants(wd_ifolder)
    
    
    

def meta_from_fitsfile_freqid(fitsfiles, wd_ifolder, metafolder, do_manual_selection):
    """
    assumes wd_ifolder exists    
    """
    freqid = 1
    for i, ff in enumerate(fitsfiles):
        if "freqid" in ff:
            wd_ifolder_freqid = f"{Path(wd_ifolder).absolute()}_{freqid}"
            if not Path(wd_ifolder_freqid).exists(): shutil.copytree(wd_ifolder, wd_ifolder_freqid, dirs_exist_ok=True)
            
            params_freqid, _, _         =   read_inputfile(wd_ifolder_freqid, "observation.inp")
            params_freqid['ms_name']    =   f"{Path(params_freqid['ms_name']).stem}_{freqid}" + Path(params_freqid['ms_name']).suffix
            
            del_fl(wd_ifolder_freqid, 0, "observation.inp", rm=True)
            create_config(params_freqid, f"{wd_ifolder_freqid}/observation.inp")
            
            meta_from_fitsfile(ff, wd_ifolder_freqid, metafolder, do_manual_selection)
            freqid  +=  1
            

def count_freqids(fitsfile):
    from vasco.fitsidiutil.io import FITSIDI
    
    fo = FITSIDI(fitsfile)

    FREQID_CHK_HDUNAME = ['FREQUENCY', 'ANTENNA', 'GAIN_CURVE', 'SYSTEM_TEMPERATURE', 'SOURCE']
    freqids                     =   1
    
    with fo.open('r') as fop:
        
        hdul = fop.read()
        
        try:
            ind_freqid_chk              =   [all(np.array(hdul[hduname_forfreqid]['FREQID'])==1) for hduname_forfreqid in FREQID_CHK_HDUNAME if hduname_forfreqid in hdul] # checking if there is only FREQID==1 or not
            if not all(ind_freqid_chk):
                freqids                 =   len(hdul['FREQUENCY'].data['FREQID'])
        except Exception as e:
            print(f"something went wrong!", e)
        
    return freqids




def check_target_in_ms(vis, target):
    from casatools import msmetadata
    msmd = msmetadata()
    found = False
    
    if Path(vis).exists():
        msmd.open(vis)
        
        alls = msmd.fieldnames()
        if target in alls:
            if len(msmd.scansforfield(target)):
                found = True
            
    return found


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

    # Bright Colors
    "bk": "\033[90m",  # Bright Black
    "br": "\033[91m",  # Bright Red
    "bg": "\033[92m",  # Bright Green
    "by": "\033[93m",  # Bright Yellow
    "bbl": "\033[94m", # Bright Blue
    "bm": "\033[95m",  # Bright Magenta
    "bc": "\033[96m",  # Bright Cyan
    "bw": "\033[97m",  # Bright White

    # Background Colors (Shortened Keys)
    "bk_": "\033[40m",  # Black BG
    "r_": "\033[41m",   # Red BG
    "g_": "\033[42m",   # Green BG
    "y_": "\033[43m",   # Yellow BG
    "bl_": "\033[44m",  # Blue BG
    "m_": "\033[45m",   # Magenta BG
    "c_": "\033[46m",   # Cyan BG
    "w_": "\033[47m",   # White BG
}

B  = "\033[1m"
X  = "\033[0m"
BC = "\033[96m"   # bright cyan
BY = c['by']

Y = c['y']
D = c['d']
