from avica.pipe.config import MPI_CASA_PERL_SCRIPT, PHASESHIFT_PERL_SCRIPT, MPICASA_WORKER, VLBA_GAINS_KEY
import subprocess
import sys
from pathlib import Path
from typing import List, Any

from avica.util import read_metafile, read_inputfile, save_metafile, latest_file
from avica.util import rfc_ascii_to_df, parse_class_cat, compute_sep
from avica.pipe.helpers import count_freqids
from avica.fitsidiutil.io import FITSIDI, read_idi
from avica.fitsidiutil.op import get_colname, dict_baseline
from avica.fitsidiutil.obs import ListObs
from avica.fitsidiutil.split import SplitData
from avica.sources import check_band
from avica.util import make_art


from copy import deepcopy

from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord
import numpy as np
from pandas import concat, DataFrame as df
import polars as pl

from collections import UserList
from typing import NamedTuple
from dataclasses import asdict


from abc import ABC, abstractmethod
from typing import List, Dict
from dataclasses import dataclass, field
from typing import Callable, Literal

from typing import List, Any
from typing import List, Dict, Any, Optional

from .helpers import X, B, BC, c, Y, D, BY

import urllib.request, urllib.error
import json, subprocess, os
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

from avica.pipe.helpers import find_tsys, FileSize, tsys_exists, tsys_exists_in_fitsfiles, overlap_percentage, del_fl, parse_params, get_allfitsfiles
from avica.pipe.helpers import get_targets_filenames, setup_workdir, add_O, get_logfilename
from avica.pipe.config import DEFAULT_PARAMS, CSV_POPULATED_STEPS, _CASA_INPROCESS_MODULES,  setup_casa_path, get_added_casa_paths, get_added_casa_lib_dirs

from copy import deepcopy

from contextlib import contextmanager

import time, shutil
from datetime import datetime
from collections import UserList
import inspect
import traceback
import logging
import warnings

SERVER_PORT = 5030



# ----      Class helpers     -------------------------------------------



def catalog_search_from_fits(fitsfile, df_catalog, seplimit, thres_sep, source_name_col='Obsname',
                             frame='icrs', include_not_found=False, verbose=False, outdir=''):

    if source_name_col in df_catalog.columns:
        df_catalog      =   df_catalog.drop_duplicates(subset=source_name_col, keep='first')

    fo              =   FITSIDI(fitsfile, mode='r')
    hdul            =   fo.read()
    source_hdu      =   hdul['SOURCE']

    target_names    =   np.array(source_hdu['SOURCE'])
    idx_found       =   np.zeros(np.shape(target_names), dtype=bool)        # i.e not found

    sid_colname     =   get_colname(source_hdu, ['ID_NO','ID_NO.', 'SOURCE_ID', 'SOURCE ID'])

    sids            =   source_hdu[sid_colname]
    # sids            =   hdu_astropy['SOURCE'].data[sid_colname]
    ra              =   source_hdu['RAEPO']*u.deg
    dec             =   source_hdu['DECEPO']*u.deg
    target_coords   =   SkyCoord(ra,dec, frame=frame)
    epoch           =   np.unique(source_hdu['EPOCH'])
    # epoch           =   np.unique(hdu_astropy['SOURCE'].data['EPOCH'])

    if not len(epoch)==1: raise ValueError(f'Multiple EQUINOX values are not supported yet : {epoch}')

                                                            # searching by name first
    match_res       =   df_catalog[df_catalog[source_name_col].isin(target_names)]

    if not match_res.empty:
        idx_found       =   np.in1d(target_names, match_res[source_name_col].values)

                                                            # since each row found corrosponds to the name match from fits
    if source_name_col in match_res.columns:
        match_res            =   match_res.rename(columns={source_name_col:'fits_target'})

    if 'fits_target' in match_res.columns:
        match_res['sep'] =   match_res.apply(lambda row: compute_sep(row, target_names, target_coords, frame), axis=1 )

    if any(~idx_found):
        if verbose:
            print("  searching by coordinate for..."," ".join(target_names[~idx_found]))

        catalog                             =   SkyCoord(df_catalog['coordinate'].values, unit=(u.hourangle, u.deg), frame=frame)

        idxtarget, idxself, sep2d, dist3d   =   catalog.search_around_sky(target_coords[~idx_found], seplimit=seplimit*u.milliarcsecond)
        df_coord_search                     =   df_catalog.iloc[idxself].copy()
        df_coord_search['sep']              =   sep2d.milliarcsecond

                                                            # in order to keep consistency.
        df_coord_search['fits_target']      =   target_names[~idx_found][idxtarget]

        if not match_res.empty:
            df_coord_search                 =   df_coord_search[match_res.columns]
            df_coord_search.index =  df_coord_search.index + 10000

        match_res = concat([match_res, df_coord_search])
#         match_res = match_res.drop(columns=['RAh', 'RAm','RAs', 'DE-', 'DEd', 'DEm', 'DEs', 'Nobs', 'Nsca', 'Nses', 'Corr'],errors='ignore')
        if 'coordinate' in match_res:
            match_res.insert(2, 'coordinate', match_res.pop('coordinate'))
        if 'sep' in match_res:
            match_res.insert(0, 'sep', match_res.pop('sep'))


        if verbose: print(len(idxtarget), "found by coordinate")
        if verbose: print(sum(idx_found), "found by name")

        unmatched_indices = np.where(~idx_found)[0]
        idx_found[unmatched_indices[idxtarget]] = True


    if verbose: print(len(target_names[idx_found]), "found of", len(target_names))
    if verbose: print(len(target_names[~idx_found]), "not found")
    if include_not_found:
#         col_usable = ['sep', 'fits_target','coordinate']
        dic_df = {'coordinate':target_coords[~idx_found].to_string('hmsdms', sep=':'), 'fits_target': target_names[~idx_found],
                 'sep': None}
        match_res = concat([match_res, df(dic_df)])
    return match_res

def df_search_brightcalib_fromascii_catalogfile(fitsfile, rfc_filepath, class_filepath, scanlist_arr, targets=[],
                              seplimit=5e3, thres_sep=1e4, crossmatch_sep=600, outfile='', nfilter_sources=20):
    """
    TODO: Increase seplimit for sources which were not found by the seplimit
    class_filepath e.g '/data/avi/d/smile/smile_complete_table.txt'

    """
    hdul            =   read_idi(fitsfile)
    hdu             =   hdul['SOURCE']


    sid_colname =   get_colname(hdu, ['ID_NO', 'ID_NO.','SOURCE_ID', 'SOURCE ID'])
    sids        =  hdu[sid_colname]
    stargets    =  hdu['SOURCE']
    dic_targets =  dict(zip(stargets, sids))

    bandfreq    =   hdul['FREQUENCY']['BANDFREQ']
    reffreq     =   hdul['FREQUENCY'].header['REF_FREQ']
    bands       =   set([check_band(freq) for freq in (bandfreq + reffreq).flatten()/1e9])

    cols_req    =   [f'Fm{band}' for band in bands]


    df_rfc      =   rfc_ascii_to_df(rfc_filepath)
    df_class    =   parse_class_cat(class_filepath)

#     df_search_rfc = catalog_search_from_fits(ff, df_rfc, seplimit=150,
#                                              thres_sep=5e2, include_not_found=True,
#                                              source_name_col='Comnam', verbose=True)

    coord_search_class = catalog_search_from_fits(fitsfile, df_class, seplimit=seplimit,
                                                  thres_sep=thres_sep,
                                                  include_not_found=True)

    rfc_catalog = SkyCoord(df_rfc['coordinate'].values, unit=(u.hourangle, u.deg), frame='icrs')
    fits_sources = SkyCoord(coord_search_class['coordinate'].values, unit=(u.hourangle, u.deg),
                            frame='icrs')

    idxtarget, idxself, sep2d, dist3d   =   rfc_catalog.search_around_sky(fits_sources,
                                                                          seplimit=300*u.mas)

    df_res_rfcsearch = df()

                                                                                                            # We have searched for all the sources, now searching flux
    df_rfc['fits_target'] = ''
    df_rfc.loc[idxself, 'fits_target'] = coord_search_class.reset_index().iloc[idxtarget]['fits_target'].values         # reset_index because the index here is not same as the fits_source, as the later uses .values; so need to reindex
    df_rfc['sid'] = df_rfc['fits_target'].map(dic_targets)

    coord_search_class['sid'] = coord_search_class['fits_target'].map(dic_targets)

    # checking which sources dont have any data in UV_DATA
    df_rfc_filtered = df_rfc[df_rfc['sid'].isin(set(scanlist_arr))]

    # search for flux info in each band
    for col_req in cols_req:
        df_res_rfcsearch = concat([df_rfc_filtered.sort_values(by=col_req, ascending=False),
                                    df_res_rfcsearch]).head(nfilter_sources)
    # add targets
    df_res_rfcsearch = concat([df_res_rfcsearch,
                              coord_search_class[coord_search_class['fits_target'].isin(targets)][['coordinate', 'sep', 'fits_target', 'sid', 'GB6']]]
                             )

    df_res_rfcsearch = df_res_rfcsearch.drop_duplicates(['fits_target'])
    df_res_rfcsearch['sid'] = df_res_rfcsearch['sid'].astype('int')


    if outfile:
        with open(outfile, 'w') as of:
            of.write(df_res_rfcsearch.to_string())

    return df_res_rfcsearch


def split_by_catalog_search(fitsfilepath, outfitsfilepath, targets, scanlist_arr,
                            calibrator_catalog_file, coord_inpfile, matched_coord_outfile, metafolder):

    """
    uses scanlist information to check if sources, dont have any data in UV_DATA.
    searches for source information by coordinate from fits in the calibrator fille,

    if provided uses true coordinates from coordinate file to make separation limits to calibrators,
    also saves output file containing separation (in mas) between provided and observed file coordinate



    """
    # classoutfile = matched_coord_outfile
    # classoutfile = f"{wd}/class_search.out"

# cmd                                 =   ['/data/avi/env/py11/bin/fitsidiutil','split-x',
#                                          ff_path, self.tmpfs[i], '/data/avi/d/smile/smile_complete_table.txt','--nfiltersource', str(nfiltersource),
                                        #  '--wd', str(self.metafolder),'--targets',",".join(self.targets),'--rfcfilepath','/data/avi/d/rfc_2024d/rfc_2024d_cat.txt']
    if not Path(fitsfilepath).exists():
        raise FileNotFoundError(f"{fitsfilepath}")
    fo  =   FITSIDI(fitsfile=fitsfilepath)
    hdul=   fo.read()
    fo.close()

    source_data = hdul['SOURCE']
    nsources   = source_data.nrows

    nfiltersource = int(nsources)
    if int(nsources)>nfiltersource:
        sids = df_search_brightcalib_fromascii_catalogfile(fitsfilepath, calibrator_catalog_file, coord_inpfile, scanlist_arr,
                                        targets, outfile=matched_coord_outfile, nfilter_sources=nfiltersource)['sid'].values

        sids = [str(sid) for sid in sids]
    else:
        sids = None
    if fitsfilepath!=outfitsfilepath:
        Path(outfitsfilepath).unlink(missing_ok=True)
        sp = SplitData(inpfits=fitsfilepath, outfits=outfitsfilepath)
        sp.split(source_ids=sids)
    else:
        raise NameError(f"both input and output are same files: {fitsfilepath}")



def split_in_freqid(fitsfiles, verbose=False):
    workingfits                 =   deepcopy(fitsfiles)
    split_result                =   {}
    for fitsfile in fitsfiles:
        freqids                     =   count_freqids(fitsfile)

        split_result                =   {fitsfile:[]}

        if freqids>1:
            for i in range(freqids):
                freqid              =   i+1
                newfitsfile         =  str(Path(fitsfile).parent / f'{Path(fitsfile).stem}_freqid{freqid}') + Path(fitsfile).suffix

                del_fl(Path(newfitsfile).parent, 0, Path(newfitsfile).name, rm=True)
                if Path(newfitsfile).exists():
                    Path(newfitsfile).unlink()

                if verbose     :
                    print(f"\nsplitting... FREQID=={freqid}")

                sp      =   SplitData(inpfits=fitsfile, outfits=newfitsfile, verbose=verbose)
                sp.split(source_ids=None, freqids=[freqid])

                split_result[fitsfile].append(newfitsfile)
                if fitsfile in workingfits:
                    workingfits.remove(fitsfile)
                workingfits.append(newfitsfile)

    result = {"workingfits": workingfits, "split_result": split_result}
    return result


def python_type_to_str(value: Any) -> str:
    if value is None:
        return "str"
    if isinstance(value, list):
        inner = python_type_to_str(value[0]) if value else "str"
        return f"List[{inner}]"
    return {
        str:   "str",
        bool:  "bool",
        int:   "int",
        float: "float",
    }.get(type(value), "str")


def dic_from_inpfile(wd_ifolder, *args) -> List | None:
    res_list = None
    if Path(wd_ifolder).exists():
        res_list = []
        for inpfile in args:
            dic_data, _, _ = read_inputfile(wd_ifolder, inpfile)
            res_list.append(dic_data)
    return res_list


def merge_obs_data(base_dict, *new_dicts):
        """provide time sorted dicts to create a merged dicts of listobs.

        Args:
            base_dict (_type_): _description_

        Returns:
            _type_: _description_
        """
        for new_dict in new_dicts:
            if base_dict:
                base_dict['scanlist'].extend(new_dict['scanlist'])
                current_offset = len(base_dict['listobs'])

                for key, value in new_dict['listobs'].items():

                    new_key = str(current_offset + int(key))
                    base_dict['listobs'][new_key] = value
                    base_dict['listobs'][new_key]['scan'] += current_offset
                base_dict['sources'].update(new_dict['sources'])
            else:
                base_dict = new_dict
        return base_dict

#####################################################################
# -------------         Classes         -----------------------------#
#####################################################################


# -------------------------------------                 Pipeline helpers






# -------------------------------------                 Definitions / Abstraction


@dataclass
class StepResult:
    name            :   str
    success_count   :   int
    failed_count    :   int

    start_stamp     :   datetime
    detail          :   Dict

    desc                :   List[str]     =   field(default_factory=list)
    success             :   List[bool]     =   field(default_factory=list)
    end_stamp: datetime = field(default_factory=datetime.now)

class ColName(NamedTuple):
    working_col     :   str
    comment_col     :   str
    timestamp_col   :   str


class AvicaResult(UserList[StepResult]):

    def to_polars(self) -> pl.DataFrame:
        if not self.data:
            return pl.DataFrame()

        dicts = []
        for r in self.data:
            row = {}
            for k, v in asdict(r).items():
                if isinstance(v, (dict, list)):
                    row[k] = json.dumps(v) if v else None
                else:
                    row[k] = v
            dicts.append(row)

        return pl.DataFrame(dicts, infer_schema_length=None)

    def summary(self) -> pl.DataFrame:
        df = self.to_polars()
        if df.is_empty():
            print("Empty results.")
            return df

        return df.with_columns([
            pl.col("start_stamp").cast(pl.Datetime).dt.round("1ms"),
            pl.col("end_stamp").cast(pl.Datetime).dt.round("1ms")
        ])

    def __repr__(self) -> str:
        df = self.to_polars()
        if df.is_empty():
            return "AvicaResult(empty)"
        return df.__repr__()

@contextmanager
def step_stage(name: str, **context):
    """Wraps a stage inside run(), logs entry and enriches any exception with context."""
    log = logging.getLogger("avica.pipeline")
    log.debug(f"[{name}] starting | {context}")
    try:
        yield
    except Exception as exc:
        ctx_str = " | ".join(f"{k}={v!r}" for k, v in context.items())
        raise type(exc)(f"[stage: {name}] {exc} | context: {ctx_str}") from exc


class PipelineContext:
    params: Dict = {}
    step_name: str = ""
    validation_success: bool | None = None
    result: StepResult | None = None
    colnames: ColName | None = None
    logfolder:str ="avica.logs/"

    @classmethod
    def init_params(cls, params: dict):
        cls.params.update(params)

    @classmethod
    def read_paramfile(cls, filepath: str):
        paramfolder = Path(filepath).parent
        paramfilename = Path(filepath).name
        paramdict, _, _ = read_inputfile(paramfolder, paramfilename)
        cls.params.update(paramdict)

    @classmethod
    def reset_params(cls):
        cls.params.clear()

@contextmanager
def pipeline_context(params: dict):
    PipelineContext.reset()
    PipelineContext.params.update(params)
    try:
        yield PipelineContext
    finally:
        PipelineContext.reset()

class WorkDirMeta:
    def __init__(self, wd_ifolder):
        self.wd_ifolder = wd_ifolder

        # -----------------------------
        self.wd         =   Path(self.wd_ifolder).parent.absolute()
        self.metafolder =   str(self.wd / "avica.meta")
        self.obs_dic     =   self.get_inp(inpfile="observation.inp")
        self.ms_name    =   None
        self.vis    =   None

         # -------------- input wd_ifolder & fitsfiles used

        self.ff_used : List[str] =   []
        self.wd_used : List[str] =   []

        # --------------- band | target

        self.band: str = ""
        self.target: str = ""

        self.wd_b: str = ""
        self.wd_b_target: str = ""
        self.vis_b: str = ""
        self.vis_b_target: str = ""

        # --------------- metafile names
        self.meta_av_wd_ff  : str =   "available_wd_ifolder.avica"
        self.meta_used_ff :  str = "fitsfiles_used.avica"
        self.meta_sources_snrating: str = "sources.avica"
        self.meta_refants_snrating: str = "refants.avica"
        self.msmeta_sources:str = 'msmeta_sources.avica'

        self.listobs_filename : str = "listobs.json"

        self.snrating_out: str = "snrating.out"
        self.listobs_out:    str =   "listobs_fits.out"
        self.match_coord_out: str = "class_search.out"

        # --------------- metafile complete paths
        self.wd_used : str = ""

        self.metafile_available_wd_ff = f"{self.metafolder}/{self.meta_av_wd_ff}"
        self.metafile_used_ff = f"{self.metafolder}/{self.meta_used_ff}"
        self.metafile_msmeta_sources = f"{self.metafolder}/{self.msmeta_sources}"
        self.metafile_sources_snrating  = f"{self.metafolder}/{self.meta_sources_snrating}"
        self.metafile_refants_snrating  = f"{self.metafolder}/{self.meta_refants_snrating}"
        self.metafile_listobs = f"{self.metafolder}/{self.listobs_filename}"
        self.outfile_listobs_out    =   f"{self.metafolder}/{self.listobs_out}"
        self.matched_coord_outfile  =   f"{self.metafolder}/{self.match_coord_out}"

        # --------------- get used wd_ifolders and fitsfiles
        if Path(self.metafile_available_wd_ff).exists():
                dic_available_wd_ff = read_metafile(self.metafile_available_wd_ff)
                if "input_folder" in dic_available_wd_ff:
                    self.wd_used = dic_available_wd_ff['input_folder']

        if Path(self.metafile_used_ff).exists():
            dic_used_ff = read_metafile(self.metafile_used_ff)

            if "filepath" in dic_used_ff:
                self.ff_used = dic_used_ff['filepath']

        if self.obs_dic:
            if isinstance(self.obs_dic, list):
                self.obs_dic = self.obs_dic[0]
            self.ms_name    =   self.obs_dic['ms_name']
            self.vis    =   str(self.wd / self.ms_name)


    def to_new_WD(self, band, target, create=True) -> tuple[Path, Path]:
        iwd                 =   Path(self.wd_ifolder).absolute()
        wd_suffix           =   iwd.parent.absolute()
        iwd_b_suffix        =   iwd

        if band:
            suffix              =   band if not target else f"{band}_{target}"

            wd_suffix           =   iwd.parent / f'wd_{suffix}'
            iwd_b_suffix        =  Path(f'{str(wd_suffix)}/{iwd.name}_{suffix}')

        if create:
            Path(iwd_b_suffix).mkdir(exist_ok=True, parents=True)
        return wd_suffix, iwd_b_suffix


    def get_inp(self, band="", target="", inpfile="observation.inp") -> dict:
        """
        Returns
        (obs_dic, arr_dic, flag_dic, arr_finetune_dic, constants_dic)
        """
        _,wd_new_ifolder = self.to_new_WD(band=band, target=target, create=False)

        result = dic_from_inpfile(str(wd_new_ifolder), inpfile)
        result = result[0] if result else None
        if result is None:
            warnings.warn(f"problem reading : {str(wd_new_ifolder)}")
        return result


    def get_diclistobs(self):
        dic_data = {}
        if Path(self.metafile_listobs).exists():
            dic_data = read_metafile(self.metafile_listobs)
            if 'listobs' in dic_data:
                for idx_str, obs_content in dic_data['listobs'].items():
                    if 'scan' not in obs_content:
                        obs_content['scan'] = int(idx_str) + 1
                    if ('sid' in obs_content) and ('source_id' not in obs_content):
                        obs_content['source_id'] = obs_content.pop('sid')
        return dic_data


    def to_dict(self):
        return self.__dict__


@dataclass
class PipelineStepValidatorResult:
    success : List[bool]
    msg: str

class PipelineStepValidatorBase(ABC):
    name: str   =   "default"
    run_after: bool =   False
    run_once: bool  =   False
    desc: str   =   ""
    result :PipelineStepValidatorResult =  PipelineStepValidatorResult([False], "")

    @abstractmethod
    def run(self, **kwargs)->PipelineStepValidatorResult:
        return self.result


class PipelineStepBase(ABC):
    """
    _________________________________________________

    - All the intialized arguments outside the step should be passed in initialized_config.
        - this makes easy checking for missing requirements when .run() is called.
    - Everything else goes as function arguments.

    _________________________________________________

    """

    name                :   str
    validate_by         :   List
    description         :   str
    colnames            :   ColName

    metadata            :   Dict
    output_printable    :   str

    result              :   StepResult
    initialized_config  :   Dict


    @abstractmethod
    def run(self, step_name: str, wd_ifolder:str, pipe_params:Dict,)->StepResult: ...


# _________________________________________________________________________________________________________.

#                   Main Pipeline Execution : data, validations in row/columns, main pipeline loop.
# _________________________________________________________________________________________________________.


class InitVariables(PipelineStepValidatorBase):
    name = "init_variables"
    run_after = False
    run_once = False
    desc = "Uses the provided parameters to initialize the variables"

    def run(self, lf, target, targets, init_params):
        if init_params:
            PipelineContext.params.update(init_params)
        parsed = parse_params(lf, PipelineContext.params)
        PipelineContext.params.update(parsed)
        # parsed = parse_params(lf, PipelineContext.params)
        # PipelineContext.params.clear()
        # PipelineContext.params.update(parsed)
        primary_value = PipelineContext.params['primary_value']
        if str(primary_value)[0] == '0':
            try:
                int(primary_value)
                primary_value = add_O(primary_value)
            except ValueError:
                pass

        lf.primary_colname  = PipelineContext.params['primary_colname']
        lf.primary_value    = primary_value                              # sheet lookups now use correct value
        PipelineContext.params['primary_value'] = primary_value
        target_dir     = PipelineContext.params['target_dir']
        lf.primary_colname = PipelineContext.params['primary_colname']
        lf.primary_value   = PipelineContext.params['primary_value']
        folder_for_fits    = PipelineContext.params['folder_for_fits']
        if folder_for_fits and "." == folder_for_fits:
            folder_for_fits = str(Path().cwd())

        filename_col       = PipelineContext.params['filename_col']
        targetname_col     = PipelineContext.params['targetname_col']
        picard_input_template         = PipelineContext.params['picard_input_template']

        allfitsfile                          = get_allfitsfiles(folder_for_fits=folder_for_fits)



        primary_target, alltargets, fitsfilenames   = get_targets_filenames(lf, filename_col, targetname_col) if lf.is_googlesheet else target, targets, init_params.get('fitsfilenames')

        if isinstance(fitsfilenames, str):
            fitsfilenames = fitsfilenames.split(",")

        wd_ifolder, filepaths                       = setup_workdir(lf, f"{str(Path(target_dir).absolute())}/", fitsfilenames, allfitsfile, picard_input_template=picard_input_template)
        if not filepaths:
            return PipelineStepValidatorResult(success=[False], msg="no fitsfiles found")

        PipelineContext.params['multifreqid']   = any(count_freqids(f) > 1 for f in filepaths)
        PipelineContext.params['targets']       = alltargets

        # if str(PipelineContext.params['target'])[0] == '0':
        #     try:
        #         int(PipelineContext.params['target'])
        #         PipelineContext.params['target'] = add_O(target)
        #     except ValueError:
        #         pass
        PipelineContext.params['target']        = primary_target if primary_target else lf.primary_value

        PipelineContext.params['allfitsfile']   = allfitsfile
        PipelineContext.params['fitsfilenames'] = fitsfilenames
        PipelineContext.params['fitsfiles']     = filepaths
        PipelineContext.params['fitsfile']      = filepaths[0] if filepaths else None
        PipelineContext.params['wd_ifolder']    = str(wd_ifolder)
        PipelineContext.params['nfiles']        = len(allfitsfile)
        PipelineContext.params['lf']            = lf

        if Path(wd_ifolder).parent.exists():
            (Path(wd_ifolder).parent / "avica.meta").mkdir(exist_ok=True)


        print("\tInput folder\t\t:", wd_ifolder)
        print("\tPrimary Value\t\t:", lf.primary_value)
        print("\tWorking Directory\t:", str(Path(wd_ifolder).parent))


        return PipelineStepValidatorResult(success=[True], msg="init")

class CasaSetup(PipelineStepValidatorBase):
    name = "casadir_setup"
    run_after = False
    desc = "If use_casadir_pythonpath is True, adds the casadir to PATH"

    def check_casa_import(self) -> bool:
        try:
            for mod in _CASA_INPROCESS_MODULES:
                __import__(mod)
            return True
        except ImportError:
            return False

    def run(self, lf, casadir, use_casadir_pythonpath):
        if use_casadir_pythonpath:
            setup_casa_path(casadir=casadir)
        return PipelineStepValidatorResult(success=[self.check_casa_import()], msg="")

class ColValidation(PipelineStepValidatorBase):
    name = "col_validations"
    run_after = False
    desc = "Executes the step column-wise validation"
    def run(self, lf, working_col, first_col, skip_cols=True):
        lf.working_col = PipelineContext.step_name or first_col
        lf.working_cols = [
            col for col in lf.df_sheet.columns
            if not str(col).lower().startswith(('comment', 'timestamp'))
        ]

        if first_col in lf.working_cols:
            idx_zero = lf.working_cols.index(first_col)
        elif working_col and working_col in lf.working_cols:
            idx_zero = lf.working_cols.index(working_col)
        else:
            idx_zero = 0    # fallback — start from beginning
            print(f"Warning: neither first_col={first_col!r} nor working_col={working_col!r} found in columns, starting from 0")
        lf.working_cols      = lf.working_cols[idx_zero:]
        working_col_idx      = lf.working_cols.index(lf.working_col)

        PipelineContext.params['lf']               = lf
        PipelineContext.params['next_working_cols'] = (
            lf.working_cols[working_col_idx:]
            if not PipelineContext.params['working_col_only']
            else [working_col]
        )
        PipelineContext.validation_success = True

        next_empty_cols = [
            col for col in PipelineContext.params['next_working_cols']
            if not lf.get_value(col)
        ]
        PipelineContext.params['empty_cols']       = next_empty_cols
        skippable_cols = [
            col for col in PipelineContext.params['next_working_cols']
            if col not in next_empty_cols
        ]
        PipelineContext.params['empty_cols_count'] = len(next_empty_cols)

        if not PipelineContext.params['empty_cols']:
            skippable_cols = PipelineContext.params['next_working_cols']
            print("skipping all")

        PipelineContext.params['skippable_cols'] = skippable_cols

        if skippable_cols and skip_cols:
            PipelineContext.validation_success = (
                False if PipelineContext.step_name in skippable_cols else True
            )
            with open("alfrd.skip", "w") as alfrd_skip:
                alfrd_skip.write(";".join(skippable_cols))


class RowValidation(PipelineStepValidatorBase):
    name    = "row_validations"
    run_after = False
    desc    = "Uses parameters derived by iterating each row in a given sheet"

    def run(self, fitsfile):
        lf      = PipelineContext.params['lf']
        target  = PipelineContext.params['target']
        fitsfile_name = PipelineContext.params['fitsfile_name']

        size = FileSize(fitsfile)

        size_validation = size.GB <= PipelineContext.params['size_limit']
        tsys_validation = True
        col_validations = not lf.get_value()
        prev_col        = (lf.get_previous_working_col()
                           if PipelineContext.params['do_pcol_validation'] else False)
        pcol_validation = (
            (lf.get_value(prev_col))
            and all(v not in lf.get_value(prev_col) for v in ['err', 'manual', 'fail'])
            if prev_col else True
        )

        row_validated = size_validation and tsys_validation and col_validations and pcol_validation



        PipelineContext.validation_success       = row_validated
        PipelineContext.params['target']         = target
        PipelineContext.params['row_validated']  = row_validated
        PipelineContext.params['fitsfile_name']  = fitsfile_name
        PipelineContext.params['fitsfile']       = fitsfile

        return PipelineStepValidatorResult(success=row_validated, msg="")

class RunValidation(PipelineStepValidatorBase):
    name      = "run_validations"
    run_after = False

    def run(self, working_col, first_col, skip_cols=True):
        lf       = PipelineContext.params['lf']
        fitsfile = PipelineContext.params['fitsfile']
        ColValidation().run(lf, working_col, first_col, skip_cols)
        if PipelineContext.validation_success:
            RowValidation().run(fitsfile)

        return PipelineStepValidatorResult(success=[PipelineContext.validation_success], msg="")

class UpdateResults(PipelineStepValidatorBase):
    name = "update_results"
    run_after=True

    def run(self,lf, count, failed, fitsfile_name):
        lf.put_value(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "last_update", count)

        # lf.update_sheet(PipelineContext.result.success_count, PipelineContext.result.failed_count)

        if PipelineContext.validation_success is None:
            if failed > 0:
                PipelineContext.validation_success = False

        if PipelineContext.validation_success is False:
            with open("alfrd.failed", "w") as f:
                f.write(f"{PipelineContext.step_name};{fitsfile_name}")

        success      = PipelineContext.result.success_count
        failed     = PipelineContext.result.failed_count
        PipelineContext.params['registered'] = lf.register = (success, failed)
        PipelineContext.params['lf']           =   lf
        return PipelineStepValidatorResult(success=[PipelineContext.validation_success], msg="")

class UpdateSheet(PipelineStepValidatorBase):
    name = "update_sheet"
    run_after=True
    run_once=False

    def run(self,lf, count, failed, fitsfile_name, csv_file=None):

        success     =   PipelineContext.result.success_count
        failed      =   PipelineContext.result.failed_count
        colnames    =   PipelineContext.colnames

        # -----

        if not (failed - PipelineContext.params['registered'][1]):                # means success/skipped
            with open('alfrd.last', 'w') as alfrd_last:
                PipelineContext.validation_success = True
                alfrd_last.write(f"{lf.working_col};{fitsfile_name}")
        else:
            print("failed")
            with open('alfrd.failed', 'w') as alfrd_failed:
                PipelineContext.validation_success = False
                alfrd_failed.write(f"{lf.working_col};{fitsfile_name}")

        csvfile = csv_file or lf.csv_file
        lf.update_sheet(count, failed, by_cell=True, comment_col=colnames.comment_col, csvfile=csvfile)

        print("Files Found\t:", PipelineContext.params['nfiles'])
        print("Failed Cells\t:", failed)
        return PipelineStepValidatorResult(success=[PipelineContext.validation_success], msg="")

class AvicaPipelineCore:

    def __init__(self, pipe_params, steps):
        self.lf                    = None
        self._steps: Dict[str, PipelineStepBase]    = {}
        self.steps                                  = steps
        self.pipe_params                            = pipe_params
        self.allresults                             = AvicaResult()

        self.register_steps()

    def register_steps(self):
        for cls in self.steps:
            instance               = cls()
            self._steps[instance.name] = instance

    def get_kwargs(self, step):
        sig = inspect.signature(step.run)
        kwargs = {}

        for name, param in sig.parameters.items():
            if name != 'self':
                val = PipelineContext.params.get(name)
                if val is None and param.default is not inspect.Parameter.empty:
                    val = param.default
                kwargs[name] = val
        return kwargs

    def get_config_requirements(self, *steps_to_check):
        complete_pipeline_params = {}
        for step_name in steps_to_check:
            step_av = self._steps[step_name]
            complete_pipeline_params[step_name]=self.get_kwargs(step_av)
        return complete_pipeline_params


    def check_config_requirements(self, step):
        param_dict = self.get_config_requirements(step)
        allparam_names  = list(param_dict[step].keys())
        ParamStatus = NamedTuple('ParamStatus', [
            ('name', str),
            ('has_default', bool),
            ('in_input_config', bool),
            ('in_context', bool)
        ])

        _report = {}
        for param_name in allparam_names:
            _report[param_name] =   ParamStatus(
                                        name=param_name,
                                        has_default = param_name in param_dict[step] and param_dict[step][param_name] is not None,
                                        in_input_config = param_name in self.pipe_params,
                                        in_context = param_name in PipelineContext.params,
                                        )
        return _report



    def filter_steps(self,*keys):
        if len(keys):
            self._steps = {k: v for k, v in self._steps.items() if k in keys}
        # if not len(list(self._steps.keys())):
        #     raise SystemExit(f"no steps found.")
        return self


    def execute(self, loglevel="INFO") -> AvicaResult:

        # ~~~~~~~~~~~ initialize ~~~~~~~~~~~~~~~~~~~~~~~~~~
        Path(PipelineContext.logfolder).mkdir(exist_ok=True)
        log                     =   logging.getLogger("avica.pipeline")
        numeric_level           =   getattr(logging, loglevel.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: %s' % loglevel)
        logfile                 =   f'{PipelineContext.logfolder}/{get_logfilename(fnname="avica",module_name="")}'
        log.setLevel(numeric_level)
        if not log.handlers:
            fh = logging.FileHandler(logfile, encoding="utf-8")
            fh.setLevel(numeric_level)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            log.addHandler(fh)
            log.propagate = False
        # PipelineContext.params = DEFAULT_PARAMS

        PipelineContext.params.clear()
        PipelineContext.params.update({**DEFAULT_PARAMS, **self.pipe_params})
        PipelineContext.params['init_params'] = self.pipe_params

        # ~~~~~~~~~~~ cli messages ~~~~~~~~~~~~~~~~~~~~~~~~~~
        make_art()
        print("Following steps will be executed in the sequence:")
        print(f"  {BC} - " + "\n   - ".join(self._steps.keys()) + f"{X}\n")

        log.info("=" * 60)
        log.info("Pipeline started")
        log.info(f"Steps to run: {[s.name for s in self._steps.values()]}")
        log.info("=" * 60)
        first_step = next(iter(self._steps.values()))
        if hasattr(first_step, 'colnames'):
            PipelineContext.params['first_col'] = first_step.colnames.working_col

        PipelineContext.validation_success  = True

        # ~~~~~~~~~~~ iterate by steps ~~~~~~~~~~~~~~~~~~~~~~~~~~
        for step_name, step in self._steps.items():
            if PipelineContext.validation_success:
                exc=None
                step_start = datetime.now()
                log.info(f"[{step_name}] Starting  {step_start}")

                if not hasattr(step, "colnames"):
                    warnings.warn(f"{step_name} is missing colnames!")
                else:
                    PipelineContext.params['working_col'] = step.colnames.working_col

                step_validators = step.validate_by
                validate_before = [v() for v in step_validators if not v.run_after]
                validate_after  = [v() for v in step_validators if v.run_after]

                result = StepResult(
                    name          = step_name,
                    success_count = 0,
                    detail        = "",
                    failed_count  = 0,
                    start_stamp   = step_start,
                    success       = [False],
                )


                try:
                    PipelineContext.step_name = step_name

                    # ~~~~~~~~~~ pre-processing ~~~~~~~~~~~~~~~~~
                    if validate_before:
                        print(f"\n>  {B}Pre-processing{X} ({step_name})")
                        print("  " + "─" * 65)
                        for step_validator in validate_before:
                            msg_info = f"executing validator step: {step_validator.name} "
                            log.info(msg_info)
                            print(f" • {step_validator.name}")
                            with step_stage(msg_info, step_validator=step_validator):
                                validator_kwargs = self.get_kwargs(step=step_validator)
                                res = step_validator.run(**validator_kwargs)
                                PipelineContext.validation_success = any(res.success)
                    if hasattr(step, 'colnames'):
                        PipelineContext.params['working_col'] = step.colnames.working_col

                    # ~~~~~~~~~~ main-step ~~~~~~~~~~~~~~~~~~~~~~~
                    if PipelineContext.validation_success:
                        print(f"\n>  {B}Processing{X}: {BC}{step_name}{X}")
                        print("  " + "─" * 65)
                        pipe_kwargs = self.get_kwargs(step=step)
                        for name, status in self.check_config_requirements(step=step_name).items():
                                if not any([status.has_default, status.in_input_config, status.in_context]):
                                    print(f"  {B}! {D}{name:<15}·{X} {Y}missing{X}")
                        result      = step.run(**pipe_kwargs)
                        result.end_stamp    =   datetime.now()
                        PipelineContext.validation_success  = any(result.success)
                        if pipe_kwargs.get('lf') is not None:
                            PipelineContext.params['lf'] = pipe_kwargs.get('lf')

                        PipelineContext.result              = result
                        PipelineContext.colnames            = step.colnames

                    # ~~~~~~~~~~ post-processing ~~~~~~~~~~~~~~~~~~
                    if PipelineContext.validation_success and validate_after:
                        print(f"\n>  {B}Post-processing{X} ({step_name})")
                        print("  " + "─" * 65)

                        for step_validator in validate_after:
                            msg_info = f"executing validator step: {step_validator.name} "
                            log.info(msg_info)
                            with step_stage(msg_info, step_validator=step_validator):
                                validator_kwargs = self.get_kwargs(step=step_validator)
                                res = step_validator.run(**validator_kwargs)
                                PipelineContext.validation_success = any(res.success)

                    # ~~~~~~~~~~~ validation-message ~~~~~~~~~~~~~~~~
                    if PipelineContext.validation_success:
                        print(f"{B} finished : {BC}{step_name}{X}")
                    else:
                        print(f"{B} skipped  : {BC}{step_name}{X}")

                except Exception as exc:

                    result = StepResult(
                        name          = step_name,
                        success_count = 0,
                        failed_count  = 1,
                        start_stamp   = step_start,
                        end_stamp     = datetime.now(),
                        detail        = {},
                        desc          = [f"Unhandled exception: {exc}"],
                        success       = [False],
                    )
                    formatted_exc = traceback.format_exc()
                    end_stamp = datetime.now()

                    print(f"\n  {Y}CRITICAL ERROR{X}")
                    print(f"  {'─' * 65}")
                    print(f"  {BY}Type:{X} {type(exc).__name__}")
                    print(f"  {BY}Info:{X} {str(exc)}\n")
                    print(f"  {Y}{str(formatted_exc)}{X}")
                    crash_file = f"{PipelineContext.logfolder}/avica_crash_{step.name}.json"
                    print(f"  {B}Snapshot:{X} Context saved to {BC}{crash_file}{X}")
                    print(f"  {'─' * 65}\n")

                    snapshot = {k: str(v) for k, v in PipelineContext.params.items()}
                    snapshot["_exception"] = formatted_exc
                    with open(crash_file, "w") as f:
                        json.dump(snapshot, f, indent=2)

                    log.error(f"[{step.name}] params snapshot written to {crash_file}")
                    log.exception(f"[{step.name}] Unhandled exception — {exc}")

                    result.end_stamp = end_stamp
                    PipelineContext.validation_success = False

                self.allresults.append(result)

                elapsed = (result.end_stamp - result.start_stamp).total_seconds()
                status  = "OK" if result.success_count != 0 else "FAILED"
                log.info(
                    f"[{step.name}] {status} | "
                    f"✓ {result.success_count}  ✗ {result.failed_count} | "
                    f"{elapsed:.1f}s"
                )
                for line in result.desc:
                    log.info(f"  · {line}")

        # ~~~~~~~ pipeline-summary ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        total_ok   = sum(r.success_count for r in self.allresults)
        total_fail = sum(r.failed_count  for r in self.allresults)
        print(f"\n    {'─' * 63}")
        print(f"    {B}Pipeline finished{X} — {BC}✓ {total_ok}{X}  ✗ {total_fail}")
        print(f"    {'─' * 63}\n")

        log.info("=" * 60)
        log.info(f"Pipeline finished — Total Success: {total_ok}  Failures: {total_fail}")
        log.info("=" * 60)

        return self.allresults



# ___________________________________________       Main Pipeline execution ends.

# ------------------------------------------------------------------------------------------------------------------------


# _________________________________________________________________________________________________.
#
#                       To create CASA task payload metadata and inputs
# __________________________________________________________________________________________________.



@dataclass
class PicardCMD:
    picard_input_template:        str
    input_template: str
    logfile:        str
    errfile:        str
    args:           Dict[str, Any]
    args_type:      Dict[str, str]
    mpi_cores:      int             = 10
    verbose:        bool            = False



@dataclass
class CasaTaskCMD:
    casadir: str
    task_casa: str
    logfile: str
    errf: str
    args: Dict[str, Any]
    args_type: Dict[str, str]
    mpi_cores: int = 0

@dataclass
class CasaStep:
    meta: Dict[str, Any]
    cmd: CasaTaskCMD

@dataclass
class CasaConfigGen:
    tasks_list: List[CasaStep] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        steps = []
        for item in data.get("tasks_list", []):
            cmd_obj = CasaTaskCMD(**item["cmd"])
            step_obj = CasaStep(meta=item["meta"], cmd=cmd_obj)
            steps.append(step_obj)

        return cls(tasks_list=steps)

@dataclass
class CasaTask:
    """
    """
    def to_args(self):
        return asdict(self)

    def task_meta(self) -> str:
        return {'name':self.__class__.__name__}

    def parse_to_step(self, task_name:str, logfile:str, errf:str, casadir:str, mpi_cores:int=5) -> CasaStep:
        task_cmd            =   CasaTaskCMD(
                                    args= self.to_args(),
                                    casadir=casadir,
                                    task_casa=task_name, logfile=logfile, errf=errf, mpi_cores=mpi_cores, args_type={})
        for key, argv in task_cmd.args.items():
            task_cmd.args_type[key] = python_type_to_str(argv)

        cmd                 =   CasaStep(meta=self.task_meta(),cmd=task_cmd)
        return cmd


# _____________________________________________________________________             fitsidiutil related core class

class GenerateAndAppendAntab:
    def __init__(self, fitsfiles, metafolder, verbose, wd, valid_perc=5):

        self.fitsfiles                  =   fitsfiles
        self.metafolder                 =   metafolder
        self.verbose                    =   verbose
        self.wd                         =   wd
        self.valid_perc                 =   valid_perc
        self.workingfits                =   deepcopy(fitsfiles)

        self.success                    =   None
        self.desc                       =   ""

        self.tsysfiles                  =   set()

    def find_and_attach_antab(self, fitsfile, fitsfiles, antabfile, attach_all, verbose=False):
        from avica.fitsidiutil import ANTAB, get_dateobs, parse_antab
        from avica.external.jive import append_tsys as TsysData, append_gc as GCData

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
                if ('.tsys' not in gf):
                    print("using", gf)
                    for gzippable_format in ['.Z', '.gz']:
                        if gzippable_format in gf:
                            subprocess.run(['gzip', '-df', gf])
                            gf          =   gf.replace(gzippable_format,'')
                    if attach_all or (gf not in self.tsysfiles):
                        try:
                            an              =   ANTAB(fitsfile, gf)
                            anfile          =   f'{antabfile}.{i}'
                            allans, _tsys_head, gain_missing    = an.gen_antab(anfile, vlbagainfile=VLBA_GAINS_KEY)
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
                    Path(dic_gf[_file][2]).rename(antabfile)
                    t1              =   time.time()
                    self.tmpfs      =   deepcopy(fitsfiles)


                    for i, ff in enumerate(fitsfiles):
                        tmpf            =   f"{Path(ff)}.tmp"
                        self.tmpfs[i]   =   tmpf
                        if Path(tmpf).exists(): Path(tmpf).unlink()
                        shutil.copy(str(Path(ff).absolute()), tmpf)

                    alldobs = [get_dateobs(fitsfile_tmp) for fitsfile_tmp in self.tmpfs]
                    dict_res = parse_antab(antabfile=antabfile, fitsfile=self.tmpfs[0])
                    # print(dict_res.keys())
                    antab_start_time    = dict_res["tsys_dic"]['start_time']
                    antab_end_time      = dict_res["tsys_dic"]['end_time']


                    if any(antab_start_time.date() <= dobs.date() <= antab_end_time.date() for dobs in alldobs):
                        for idifile in self.tmpfs:
                            if verbose: print(f"....appending System Temperature to {idifile}")
                            TsysData.append_tsys(antabfile=antabfile, idifiles=idifile, replace=True)
                            if verbose: print(f"....appending Gain Curve to {idifile}")
                            GCData.append_gc(antabfile=antabfile, idifile=idifile, replace=True)

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
        tsys_found_in_files             =   []
        for i, fitsfile in enumerate(self.workingfits):
            antabfile                   =   Path(self.wd) / f'gc_dpfu_fromidi.ANTAB.{i}'
            del_fl(Path(self.wd), fl=f'gc_dpfu_fromidi.ANTAB.{i}', rm=True)
            tsys_found, _, _ , _, _     =   tsys_exists(fitsfile)
            tsys_found_in_files.append(tsys_found)
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
        if len(tsys_found_in_files) and (not all(tsys_found_in_files)) and self.verbose:
            print("Attaching TSYS finished!")

    def sort_by_time(self):
        starttime = []
        valid_fits = []

        for fitsfile in self.workingfits:
            success, _, _, starttime_uvd, _ = tsys_exists(fitsfile, self.valid_perc)
            if starttime_uvd:
                starttime.append(starttime_uvd.mjd)
                valid_fits.append(fitsfile)
            else:
                print("UV data not found..", fitsfile)

        self.workingfits = [x for _, x in sorted(zip(starttime, valid_fits), reverse=True)]
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


#

# __________________________________________________________________________________.
#
#                                                CASA Tasks
#
# __________________________________________________________________________________.


#  ----------------------      Fits to MS (importfitsidi)

@dataclass
class ImportFITSIdi(CasaTask):
    vis:              str  = ""
    fitsidifile:      List[str] = field(default_factory=list)
    constobsid:       bool  = True
    scanreindexgap_s: float = 15.0


    def to_step(self, logfile:str, errf:str, casadir:str, mpi_cores:int=5):
        task_cmd                 =   self.parse_to_step(task_name="importfitsidi", logfile=logfile, errf=errf, casadir=casadir, mpi_cores=mpi_cores)
        return task_cmd

#  ----------------------      FringeFit (fringefit)
@dataclass
class FringeFit(CasaTask):
    vis:str                 =   ""
    caltable:str            =   ""
    field:str               =   ""
    spw:str                 =   ""
    selectdata:bool         =   True
    timerange:str           =   ""
    antenna:str             =   ""
    scan:str                =   ""
    observation:str         =   ""
    msselect:str            =   ""
    solint:str              =   'inf'
    combine:str             =   "spw"
    refant:str              =   ""
    minsnr:str              =   ""
    zerorates:bool          =   False
    globalsolve:bool        =   False
    append:bool             =   False
    docallib:bool           =   False
    callib:str              =   ""
    gaintable:List | str    =   ""
    gainfield:List | str    =   ""
    interp:str              =   ""
    corrdepflags:bool       =   True
    concatspws:bool         =   True
    corrcomb:str            =   "none"
    parang:bool             =   True


    def to_step(self, logfile:str, casadir:str, errf:str, mpi_cores:int=5):
        task_cmd                 =   self.parse_to_step(task_name="fringefit", logfile=logfile, errf=errf, casadir=casadir, mpi_cores=mpi_cores)
        return task_cmd


#  ----------------------      Average MS / Split MS  (mstransform)

@dataclass
class MsTransform(CasaTask):
    vis:str             =   ""
    outputvis:str       =   ""
    datacolumn:str      =   "data"
    field:str           =   ""
    spw:str             =   ""
    antenna:str         =   ""
    scan:str            =   ""
    chanaverage:bool    =   False
    chanbin:int|List[int]    =   1
    timeaverage:bool    =   False
    timebin:str         =   "0s"
    hanning:bool        =   False
    reindex:bool        =   True
    keepflags:bool      =   True
    createmms:bool      =   True


    def to_step(self, logfile:str, casadir:str, errf:str, mpi_cores:int=5):
        task_cmd                 =   self.parse_to_step(task_name="mstransform", logfile=logfile, errf=errf, casadir=casadir, mpi_cores=mpi_cores)
        return task_cmd

#  ----------------------      Flag Data


@dataclass
class FlagData(CasaTask):
    vis:str             =   ""
    mode:str            =   "manual"
    datacolumn:str      =   "data"
    field:str           =   ""
    spw:str             =   ""
    antenna:str         =   ""
    scan:str            =   ""

    def to_step(self, logfile:str, casadir:str, errf:str, mpi_cores:int=5):
        task_cmd                 =   self.parse_to_step(step_name="flagdata", logfile=logfile, errf=errf, casadir=casadir, mpi_cores=mpi_cores)
        return task_cmd



# __________________________________________________________________________________.
#
#                                               Payload Handler
# __________________________________________________________________________________.



class IterativeSubprocess:
    def __init__(self, cmd_list, clean_env=True, verbose=True):
        self.verbose = verbose
        self._stderr_lines = []
        self._stderr_lock = threading.Lock()

        env_found = {
            k: v for k, v in os.environ.items()
            if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} or not clean_env
        }
        self.process = subprocess.Popen(
            cmd_list, env=env_found,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1
        )
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

        self._wait_for_ready()  # block here until worker signals ready

    def _wait_for_ready(self, timeout=120):
        """Read stdout lines until we see the ready signal, discarding startup noise."""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"Worker died during startup.\n{self.get_stderr()}")
            line = self.process.stdout.readline()
            if not line:
                continue
            if self.verbose:
                print(f"[startup] {line}", end="", flush=True)
            try:
                msg = json.loads(line.strip())
                if msg.get("status") == "ready":
                    return
            except json.JSONDecodeError:
                pass  # discard startup noise
        raise TimeoutError(f"Worker did not become ready within {timeout}s.\n{self.get_stderr()}")

    def _drain_stderr(self):
        for line in self.process.stderr:
            with self._stderr_lock:
                self._stderr_lines.append(line)
            if self.verbose:
                print(f"[mpicasa stderr] {line}", end="", flush=True)

    def get_stderr(self):
        with self._stderr_lock:
            return "".join(self._stderr_lines)

    def send_and_receive(self, inp_data: dict) -> dict:
        if self.process.poll() is not None:
            raise RuntimeError(f"Subprocess terminated.\nstderr:\n{self.get_stderr()[-2000:]}")

        self.process.stdin.write(json.dumps(inp_data) + "\n")
        self.process.stdin.flush()

        # loop until we get a JSON line — discards any stray stdout noise
        while True:
            line = self.process.stdout.readline()
            if not line:
                return {"error": "Received empty response from subprocess"}
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                if self.verbose:
                    print(f"[non-JSON stdout, skipping] {line}", flush=True)

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            self.process.wait()
        self._stderr_thread.join(timeout=5)

class PersistentMpiCasaRunner:
    def __init__(self, casadir: str, mpi_cores: int = 10, verbose:bool=False):
        """single MPI process to recieve payload"""
        self.verbose = verbose
        cmd_list = [
            f"{casadir}/bin/mpicasa", "-n", str(mpi_cores),
            "--oversubscribe", f"{casadir}/bin/casa", "--nologger", "--nogui", "--agg",
            "-c", f"{MPICASA_WORKER}"]
        self.runner = IterativeSubprocess(cmd_list=cmd_list, clean_env=True, verbose=verbose)

    def run_task(self, task_name: str, args: dict, args_type:Dict[str, Any], block=False, target_server:Optional[int]=None):
        payload = {
            "task_casa": task_name,
            "args": args,
            "args_type":args_type,
            "block": block,
            "target_server": target_server
        }
        return self.runner.send_and_receive(payload)

    def get_response(self, command_ids: Any, block: bool = True):
        payload = {
            "task_casa": "get_command_response",
            "parameters": {"command_ids": command_ids, "block": block}
        }
        return self.runner.send_and_receive(payload)

    def close(self):
        self.runner.close()



def run_subprocess(cmd_list: List[str], inp_data: dict, mode: str = "stdin", clean_env:bool=True, verbose:bool=True) -> dict:

    env_found = {
        k: v for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", } or not clean_env
    }
    if mode == "stdin":
        stdin_input = json.dumps(inp_data)
        full_cmd    = cmd_list
    else:
        stdin_input = None
        full_cmd    = cmd_list + [str(a) for a in inp_data.get("args", [])]

    process = subprocess.Popen(
        full_cmd,
        env    = env_found,
        stdin  = subprocess.PIPE if mode == "stdin" else None,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        text   = True,
    )
    if stdin_input:
        process.stdin.write(stdin_input)
        process.stdin.close()
    stderr_lines = []
    def read_stderr():
        for line in iter(process.stderr.readline, ""):
            stderr_lines.append(line)

    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()

    stdout_lines = []
    for line in iter(process.stdout.readline, ""):
        if verbose:
            print(line, end="", flush=True)
        stdout_lines.append(line)

    process.wait()
    stderr_thread.join()

    success = process.returncode == 0

    for line in reversed(stdout_lines):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue

    return {"raw": "".join(stdout_lines)}

class SubprocessPayload:
    cmd_list: List[str] =   []
    mode: str =   "stdin"
    clean_env:bool = True

    def __init__(self,inp_data: dict,cmd_list: List[str] = None,host: str = "localhost",port: int = SERVER_PORT):
        self.inp_data = inp_data
        self.cmd_list   = cmd_list or self.__class__.cmd_list

    def run(self)->dict:
        return run_subprocess(cmd_list=self.cmd_list, inp_data=self.inp_data, mode=self.mode, clean_env=self.clean_env)

class MpiCasaPayload(SubprocessPayload):
    cmd_list    =   ["perl", MPI_CASA_PERL_SCRIPT]
    mode        =   "stdin"

    def __init__(self, tasks_list: List[CasaStep], host: str = "localhost", port: int = SERVER_PORT):
        inp_data    =   CasaConfigGen(tasks_list=tasks_list).to_dict()
        super().__init__(inp_data=inp_data, host=host, port=port)

@dataclass
class PicardTask:
    input:      str
    n:          int = 10

    def to_args(self) -> List[str]:
        return ["-n", str(self.n), "--input", self.input]



@dataclass
class PicardStepParser:
    casadir:    str
    logfile:    str
    errf:       str

    def parse(self, task: PicardTask) -> CasaStep:
        cmd = CasaTaskCMD(
            args        = asdict(task),
            args_type   = {k: python_type_to_str(v) for k, v in asdict(task).items()},
            casadir     = self.casadir,
            task_casa   = "picard",
            logfile     = self.logfile,
            errf        = self.errf,
            mpi_cores   = 0,            # picard handles its own parallelism via -n
        )
        return CasaStep(meta={'name': 'picard', 'runner': 'picard'}, cmd=cmd)


class PicardPayload(SubprocessPayload):
    mode = "args"

    def __init__(self, task: PicardTask):
        super().__init__(
            inp_data = asdict(task),
            cmd_list = ["picard"] + task.to_args(),
        )

# --------------------------------------------- For future.


# def http_handler(cmd_list: List[str], mode: str = "stdin"):
#     """

#     Args:
#         cmd_list (List[str]):   list of command args
#         mode (str, optional):   mode='args args list appended to cmd_list. Defaults to "stdin".
#                                 mode='stdin' JSON config piped to process stdin.


#     """
#     class Handler(BaseHTTPRequestHandler):
#         def do_POST(self):
#             length      =   int(self.headers["Content-Length"])
#             payload     =   json.loads(self.rfile.read(length))

#             if mode == "stdin":
#                 full_cmd    =   cmd_list
#                 stdin_input =   json.dumps(payload)

#             elif mode == "args":
#                 extra_args  =   payload.get("args", [])
#                 full_cmd    =   cmd_list + [str(a) for a in extra_args]
#                 stdin_input =   None

#             process = subprocess.Popen(
#                 full_cmd,
#                 env         =   CLEAN_ENV,
#                 stdin       =   subprocess.PIPE if mode == "stdin" else None,
#                 stdout      =   subprocess.PIPE,
#                 stderr      =   subprocess.PIPE,
#                 text        =   True,
#             )

#             stdout_raw, stderr = process.communicate(input=stdin_input)
#             success = process.returncode == 0

#             try:
#                 script_result = json.loads(stdout_raw)
#             except json.JSONDecodeError:
#                 script_result = {"raw": stdout_raw}

#             body    =   json.dumps({"success":       success,
#                                 "script_result": script_result,
#                                 "stderr":        stderr,}
#                               ).encode()

#             self.send_response(200)
#             self.send_header("Content-Type", "application/json")
#             self.end_headers()
#             self.wfile.write(body)

#         def log_message(self, format, *args):
#             pass

#     return Handler

# class ServerPayload:
#     cmd_list: List[str] =   []
#     mode: str =   "stdin"

#     def __init__(self,inp_data: dict,cmd_list: List[str] = None,host: str = "localhost",port: int = SERVER_PORT):
#         self.inp_data = inp_data
#         self.host     = host
#         self.port     = port

#     def __enter__(self):
#         handler_cls  = http_handler(self.cmd_list, mode=self.__class__.mode)
#         self._server = HTTPServer((self.host, self.port), handler_cls)
#         self._thread = threading.Thread(target=self._server.handle_request)
#         self._thread.start()
#         return self

#     def run(self) -> dict:
#         data    =   json.dumps(self.inp_data).encode()
#         req     =   urllib.request.Request(f"http://{self.host}:{self.port}/run", data=data, headers={"Content-Type": "application/json"})
#         with urllib.request.urlopen(req) as resp:
#             result  =   json.loads(resp.read())

#         if not result["success"]:
#             print("STDERR:", result["stderr"], flush=True)

#         return result["script_result"]

#     def __exit__(self, *args):
#         self._thread.join()
#         self._server.server_close()
