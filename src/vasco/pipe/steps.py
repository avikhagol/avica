
from vasco.util import read_metafile, read_inputfile, save_metafile, latest_file, create_config
from pathlib import Path
import shutil
import logging
import polars as pl
from datetime import datetime
from copy import deepcopy

import traceback
import glob
import numpy as np
import json
import subprocess

from .helpers import del_fl, count_freqids, meta_from_fitsfile, meta_from_fitsfile_freqid, get_logfilename, single_ifcheck, fillinp_fromiwd, read_vasco_sources_msmeta
from .helpers import alls_fromobs, update_from_vascometa, check_target_in_ms, fits_has_target, fill_input_byvalues

from .core import PipelineStepBase, StepResult, VascoResult, ColName, PipelineContext
from vasco.fitsidiutil.op import count_tsys_in_fitsfile
from .core import step_stage, InitVariables, RunValidation, WorkDirMeta, UpdateResults, UpdateSheet
from .core import ImportFITSIdi, MsTransform, CasaConfigGen, MpiVascoPayload,VascoSnRatinCMD, MpiCasaPayload, PicardPayload, GenerateAndAppendAntab, PicardTask
from .config import PHASESHIFT_PERL_SCRIPT

log = logging.getLogger("vasco.pipeline")
#_____________________________________________________________________________________
#                                                                                     #
#                                Pipeline Steps                                       #
#_____________________________________________________________________________________#

class PreProcessFitsIdi(PipelineStepBase):
    """
        _______________________________________________________
        
        1. Fix minor problems in the fits.
        2. Check scanlist, print listobs if scanlist output file not found in metadata.
        3. Split sources to contain only desired sources.
        4. Fix remaining problems.
        5. Split in frequency id and attach missing tsys, gain curve table.
        6. Fill optional metadata in the pipeline input files.
        
        _________________________________________________________
        
    """
    
    # ----------------------------------------------------------
    name            =   "preprocess_fitsidi"
    colnames        =   ColName('preprocess_fitsidi', 'Comment_prepfits', 'timestamp_prepfits')
    py_env          =   ""
    description     =   """performs sanity checks and applies fixes on table data and headers, splits file to keep desired sources, splits by freqid, downloads TSYS and GC and generates ANTAB and attaches the ANTAB to the fitsfiles."""
    validate_by     =   [InitVariables, RunValidation, UpdateResults, UpdateSheet]
    result          =   StepResult(name=name, detail={},
                                       success_count=0, failed_count=0, start_stamp=datetime.now())
    # initialized_config  =   PipelineContext.params
    output_printable    =   ""
    
    # ----------------------------------------------------------
    
    def run(self, lf, fitsfiles, target, wd_ifolder, verbose=False):
        
        from vasco.fitsidiutil.validation import fitsidi_check
        from vasco.fitsidiutil.obs import ObservationSummary
        from vasco.pipe.core import split_by_catalog_search, split_in_freqid
        
        with step_stage("init WorkDirMeta", wd_ifolder=wd_ifolder):
            wd_meta         =   WorkDirMeta(wd_ifolder=wd_ifolder)
            wd              =   wd_meta.wd
            metafolder      =   wd_meta.metafolder
            targets         =   PipelineContext.params['targets'] or [] if 'targets' in PipelineContext.params else []
            target          =   PipelineContext.params['target']
            tmpfitsfiles        =   deepcopy(fitsfiles)
        
        rfc_catalog_file        =   PipelineContext.params['rfc_catalogfile']
        class_search_asciifile  =   PipelineContext.params['class_search_asciifile']
        reference_ifolder       =   PipelineContext.params['picard_input_template']
        
        
        if not Path(metafolder).exists():
            Path(metafolder).mkdir(parents=True, exist_ok=True)
        
            
        del_fl(metafolder, 0, wd_meta.meta_used_ff, rm=True)                                    # delete used_fitsfile metadata
        
        
        # 1     ________________________________    fix minor issues
        
        with step_stage("fix minor issues"):
            tmpfitsfiles = tuple([ff + ".tmp" for ff in deepcopy(fitsfiles)])
            for i, ff in enumerate(fitsfiles):
                tmpff = tmpfitsfiles[i]
                shutil.copy(ff, tmpff)
                result_minor_fixes      =   fitsidi_check(fitsfilepath=tmpff).filter_codes('extra_byte', 'binary', 'date').run(fix=True)
                self.output_printable += str(result_minor_fixes)
                log.info(result_minor_fixes)
                if verbose: print(result_minor_fixes)
        
        # 2     ________________________________    get observation summary
        #                                                                                       NOTE: if not found in cached output dictionary result; for force redo delete the wd_meta.listobs_out
        with step_stage("get observation summary", fitsfiles=fitsfiles):
            dic_obs_summary         =   wd_meta.get_diclistobs()
            obsdata                 =   ObservationSummary(fitsfilepaths=fitsfiles)
            if not dic_obs_summary or (target not in dic_obs_summary['sources'].values()):
                obsdata.get()
                dic_obs_summary     =  obsdata.dic_summary
            else:
                obsdata.dic_summary =   dic_obs_summary
            ppout                   =   str(obsdata.to_polars())
            
            with open(f"{wd_meta.outfile_listobs_out}", 'w') as ppoutbuff:
                ppoutbuff.write(f"{ppout}")
            self.output_printable += f"\n\n{ppout}"
            if verbose: print(f"\n\n{ppout}")
            log.info(f"\n\n{ppout}")
            
        # 3     ________________________________    splitting and keeping only desired sources
        msg_info = "splitting and keeping only desired sources"
        log.info(msg_info)
        with step_stage(msg_info, fitsfiles=fitsfiles, tmpfitsfiles=tmpfitsfiles):
            for i,ff in enumerate(fitsfiles):
                tmpff  =   tmpfitsfiles[i]
                
                if rfc_catalog_file is not None:
                    split_by_catalog_search(tmpff, outfitsfilepath=ff, targets=targets, scanlist_arr=obsdata.scanlist(),
                                            calibrator_catalog_file=rfc_catalog_file, coord_inpfile=class_search_asciifile, 
                                        matched_coord_outfile=wd_meta.matched_coord_outfile, metafolder=metafolder)
                else:
                    with step_stage(f"3 - moving file {tmpff} --> {ff}", tmpfitsfiles=tmpfitsfiles):
                        shutil.move(tmpff, ff)
            
        # 4     ________________________________    fixing remaining fitsidi problems
        msg_info = "fixing remaining fitsidi problems"
        log.info(msg_info)
        with step_stage(msg_info, fitsfiles=fitsfiles):
            for ff in fitsfiles:
                result_remaining_fixes = fitsidi_check(fitsfilepath=ff).run(fix=True, scanlist=obsdata.scanlist())
                self.output_printable += str(result_remaining_fixes)
                if verbose: print(result_remaining_fixes)
                log.info(result_remaining_fixes)
        
        # 5     ________________________________    split in freqid / attach missing tsys
        with step_stage("splitting in freqid / attaching missing tsys", fitsfiles=fitsfiles):
            multifreqid     =   PipelineContext.params['multifreqid']                          =   True if any([count_freqids(fitsfile)>1 for fitsfile in fitsfiles]) else False
            
            fitsfiles_used  =   fitsfiles
            if multifreqid:
                res_splitdata   = split_in_freqid(fitsfiles=fitsfiles, verbose=verbose) # result = {"workingfits": workingfits, "split_result": split_result}
                
                for ff in res_splitdata['split_result']:
                    newff = res_splitdata['split_result'][ff]
                    if isinstance(newff, list):
                        children = "\n".join(f"      ├─ {Path(f).name}" for f in newff)
                        print(f"  {Path(ff).name} -->\n{children}")
                    else:
                        print(f"  {Path(ff).name} --> {Path(newff).name}")
                
                ga              =   GenerateAndAppendAntab(fitsfiles=res_splitdata['workingfits'], metafolder=metafolder, verbose=True, wd=wd, valid_perc=5)
                
                ga.attach_antab(only_first=False, attach_all=True)               #  to attach antab if it is mixed w. splitted freqid and non multiple?
                fitsfiles_used  =   ga.workingfits
            else:
                ga              =   GenerateAndAppendAntab(fitsfiles=fitsfiles_used, metafolder=metafolder, verbose=True, wd=wd, valid_perc=5)
                ga.attach_antab(only_first=False)
                fitsfiles_used  =   ga.workingfits
            
        with step_stage("validating...", fitsfiles=fitsfiles):
            ga.validate()
        
        with step_stage("saving metadata", fitsfiles=fitsfiles):
            PipelineContext.params['filepaths']     =   fitsfiles_used
            save_metafile(wd_meta.metafile_used_ff, {"filepath": fitsfiles_used}) 
        
        # ___________________________________________________________                                                        Fill meta [optional]
        
        with step_stage("reading input file from fitsfile data", fitsfiles=fitsfiles):
            meta_from_fitsfile(fitsfiles_used[0], target, wd_ifolder, metafolder, reference_ifolder, do_manual_selection=True)
            
            if multifreqid:
                meta_from_fitsfile_freqid(fitsfiles_used, target, wd_ifolder, metafolder, reference_ifolder, do_manual_selection=True)
        
        with step_stage("validate and collect results.", fitsfiles=fitsfiles):
            validate_tsys_count_multifreqid    =   all([count_tsys_in_fitsfile(ff_freqid, target) for ff_freqid in fitsfiles_used if "freqid" in ff_freqid]) if multifreqid else True
            
            #### _________________________________________________________                       if count_tsys_in_fitsfile(fitsfiles_used[0], target) and validate_tsys_count_multifreqid:           # this ensures that we take fitsfile with max TSYS rows (viz validates non multifreqid) - TODO: doesn't validate mixed w/w.o freqid splitted fitsfiles
            self.result.success = [count_tsys_in_fitsfile(ff, target)>0 for ff in fitsfiles_used]
            if any(self.result.success):
                self.result.success_count += 1
            else:
                self.result.failed_count += 1
            lf.put_value("success")
        self.result.end_stamp   =   datetime.now()
        
        return self.result
        
class FitsIdiToMS(PipelineStepBase):
    """
        _______________________________________________________
        
        - uses the last used fitsfiled to run `importfitsidi`
        - runs iteratively for files requiring different vis output.
        - casa tasks is triggered with the correct python environment using `payload service`
        - logs "vis exists!" when the visiblity file is already present.
        
        _________________________________________________________
        
    """
    
    name            =   "fits_to_ms"
    colnames        =   ColName('fits_to_ms', 'Comment_fits2ms', 'timestamp_fits2ms')
    py_env          =   ""
    description     =   "load fits to ms"
    validate_by     =   [InitVariables, RunValidation, UpdateResults, UpdateSheet]
    result          =   StepResult(name=name, detail={},
                                       success_count=0, failed_count=0, start_stamp=datetime.now())
    # ----------------------------------------------------------
    
    def run(self, lf, casadir, wd_ifolder):
        
        wd_meta         =   WorkDirMeta(wd_ifolder=wd_ifolder)
        fitsfiles       =   wd_meta.ff_used
        multifreqid     =   len([ff for ff in fitsfiles if "freqid" in ff])>0
        
        wd              =   wd_meta.wd
        metafolder      =   wd_meta.metafolder
        vis             =   wd_meta.vis
        
        if vis is None:
            raise NameError(f"vis = {vis}; wd_ifolder ={wd_ifolder}")
        
        tasks_list        =   []
        used_wd_ifolder =   []
        used_ff_wd_ifolder = []
        
        wds_ifolder_for_payload  =   []
        casalogfile     =   f'{wd}/{get_logfilename(fnname=self.name, start_stamp=self.result.start_stamp, module_name="casa")}'
        errcasalogfile     =   f'{wd}/{get_logfilename(fnname=self.name, start_stamp=self.result.start_stamp, module_name="err-casa")}'
        
        
        # ------------------------ w/o multiple frequency IDs
        msg                             =   "setting up casatask"
        log.info(msg)
        with step_stage(msg, vis=str(vis)):
            if not multifreqid:
                if not Path(str(vis)).exists():
                    task            =   ImportFITSIdi(vis=vis, fitsidifile=fitsfiles)
                    step             =   task.to_step(logfile=casalogfile, errf=errcasalogfile, casadir=casadir)
                    msg                             =   "appending step"
                    log.info(msg)
                    with step_stage(msg, vis=vis):
                        tasks_list.append(step)
                        wds_ifolder_for_payload.append(wd_ifolder)
                else:
                    self.result.desc.append(f"vis exists! {Path(vis).name}")
                    self.result.success.append(True)
                used_wd_ifolder.append(wd_ifolder)
                used_ff_wd_ifolder.append(fitsfiles)
                
            else:
                msg                             =   "setting up casatask and has multifreqid"
                log.info(msg)
                
                with step_stage(msg, vis=vis):
            # ------------------------ with and w/o multiple frequency IDs
                    fitsfilefreqid  =   [ff for ff in fitsfiles if "freqid" in ff]                                              # During the split the files containing "freqid" are the ones with multiple freqid
                    otherfitsfile   =   [ff for ff in fitsfiles if "freqid" not in ff]
                    
                    wd_ifolder_freqids = [f"{wd_ifolder}_{freqid+1}" for freqid, ff in enumerate(fitsfilefreqid) if "freqid" in ff]
                    
                    #  ------- with freqid
                    for i, wd_ifolder_freqid in enumerate(wd_ifolder_freqids):
                        params_freqid, _, _    =   read_inputfile(wd_ifolder_freqid, "observation.inp")
                        vis_freqid      =   f"{wd}/{params_freqid['ms_name']}"
                        ff_freqid       =   [fitsfilefreqid[i]]
                        
                        if not Path(vis_freqid).exists():
                            task            =   ImportFITSIdi(vis=vis_freqid, fitsidifile=ff_freqid)
                            step             =   task.to_step(logfile=casalogfile, errf=errcasalogfile, casadir=casadir)
                            tasks_list.append(step)
                            wds_ifolder_for_payload.append(wd_ifolder_freqid)
                        else:
                            self.result.desc.append(f"vis exists! {Path(vis_freqid).name}")
                            self.result.success.append(True)
                        used_wd_ifolder.append(wd_ifolder_freqid)
                        used_ff_wd_ifolder.append(ff_freqid)
                        
                    #  ------- w/o freqid
                    if otherfitsfile:
                        if not Path(vis).exists():
                            task            =   ImportFITSIdi(vis=vis, fitsidifile=otherfitsfile)
                            step             =   task.to_step(logfile=casalogfile, errf=errcasalogfile, casadir=casadir)
                            tasks_list.append(step)
                            wds_ifolder_for_payload.append(wd_ifolder)
                        else:
                            self.result.desc.append(f"vis exists! {Path(vis).name}")
                            self.result.success.append(True)
                            
                        used_wd_ifolder.append(wd_ifolder)
                        used_ff_wd_ifolder.append(otherfitsfile)
                    
        wd_meta.wd_used = used_wd_ifolder
            
        # -------------------------------- Execution
        msg                             =   "folder deletions"
        log.info(msg)
        with step_stage(msg, vis=vis):
            # --- del file for current wd being used
            for wd_ifolder_payload in wds_ifolder_for_payload:
                _           =   del_fl(Path(wd_ifolder_payload).parent, 1,fl=f"*{vis}*", rm=True)
                _           =   del_fl(Path(wd_ifolder_payload).parent, 1,fl="*stored*", rm=True)
                _           =   del_fl(Path(wd_ifolder_payload).parent, 1,fl="*tmp*", rm=True)
        
        with step_stage("payload execution", vis=vis):
            payload                     =   MpiCasaPayload(tasks_list=tasks_list)
            payload.run()
        
        
        # ---------------- finalize outputs and metadata
        
        for casastep in tasks_list:
            output_vis = Path(casastep.cmd.args['vis'])
            if output_vis.exists():
                self.result.success_count    +=  1
                self.result.desc.append(f"FITS to MS conversion successfull! for {output_vis.name}")
                self.result.success.append(True)
            else:
                self.result.failed_count     +=  1
                # last_log = latest_file(Path(output_vis).parent, '*err.out*')
                self.result.desc.append(f"failed! vis:{output_vis.name} check logs: {errcasalogfile}")
                if not all([Path(ff).exists() for ff in casastep.cmd.args['fitsidifile']]):
                    self.result.desc.append(f"input fitsidifile not found! {casastep.cmd.args['fitsidifile']}")
                self.result.success.append(False)
                
                
        self.result.end_stamp                   =   datetime.now()
        del_fl(metafolder, 0, "available_wd_ifolder.vasco", rm=True)
        save_metafile(wd_meta.metafile_available_wd_ff, {"input_folder": used_wd_ifolder, "fitsfiles": used_ff_wd_ifolder})
        
        return self.result
    
class Phaseshift(PipelineStepBase):
    """
        _______________________________________________________
        
        - works if coordinate file was provided e.g class_search_coord.ascii
        - match sources by coordinate and phaseshift if not coordinates within 1 arcsecond
        - casa tasks is triggered with the correct python environment using `payload service`
        
        _________________________________________________________
        
    """
    
    # ----------------------------------------------------------
    name            =   "phaseshift"
    colnames        =   ColName('phaseshift', 'Comment_phaseshift', 'timestamp_phaseshift')
    py_env          =   "casa-6.7"
    description     =   """uses the coodinate search file result from previous step, performs phaseshift when source is off by 1 arcsecond"""
    validate_by     =   [InitVariables, RunValidation, UpdateResults, UpdateSheet]
    result          =   StepResult(name=name, detail={},
                                       success_count=0, failed_count=0, start_stamp=datetime.now())
    
    # ----------------------------------------------------------
    
    def run(self, lf, wd_ifolder, fitsfile, target, separation_thres, class_search_asciifile, verbose=False,):
        from vasco.util import parse_class_cat
        from vasco.fitsidiutil.op import catalog_search_from_fits
        
                            
        self.result.detail              =   {}
        # wds_ifolder_for_payload         =   []
        
        wd_meta                         =   WorkDirMeta(wd_ifolder=wd_ifolder)
        
        class_searchcoord_file          =   wd_meta.matched_coord_outfile
        
        metafile_av_iwd_ff              =   wd_meta.metafile_available_wd_ff
        wd_ifolders                     =   read_metafile(metafile_av_iwd_ff)['input_folder'] if metafile_av_iwd_ff is not None and  Path(metafile_av_iwd_ff).exists() else [wd_ifolder]
        fitsfiles_for_iwd               =   read_metafile(metafile_av_iwd_ff)['fitsfiles'] if Path(metafile_av_iwd_ff).exists() else [[fitsfile]]
        
        log.info(f"working fitsfiles : {fitsfiles_for_iwd}")
        
        UNDER_DEVELOPMENT               =   True    # TODO : finish me
        if UNDER_DEVELOPMENT:
            msg     =   """\nUNDER_DEVELOPMENT!! this step will generate metadata but will not actually phaseshift\n 
                  # this is because the phaseshift perl script currently works with hard-coded python environment"""
            print(msg)
            log.info(msg)
            
        # --------------------------------------------------------------------
        
        
        if class_search_asciifile is None:
            msg                         =   f"skipping - ascii file with coordinates was not passed"
            log.info(msg)
            print(msg)
        else:
            df_class                    =   parse_class_cat(class_search_asciifile)
            msg                         =   "iterating through the previously used input folders"
            log.info(msg)
            with step_stage(msg):
                for ifreqid,wd_ifolder_freqid in enumerate(wd_ifolders):                                                        
                    fitsfile        =   [ff for ff in fitsfiles_for_iwd[ifreqid] if fits_has_target([ff], target)][0]           #  checks fits has target source and select that only                                                    #  checks fits has target source and select that only

                    msg             =   "checking separation from phase-center and phaseshift if required"
                    log.info(msg)                                           
                    with step_stage(msg):
                        try:
                            obs, _, _       =   read_inputfile(wd_ifolder_freqid, "observation.inp")
                            vis             =   wd_meta.vis
                            
                            print(" \nchecking coordinate at phasecenter...")
                            coord_search_class  = catalog_search_from_fits(fitsfile, df_class, seplimit=60e3, # arcmin -> mas
                                                                            thres_sep=60e3, # not used
                                                                            include_not_found=False) # being true can give NaN separation
                            if not coord_search_class.empty:
                                with open(class_searchcoord_file, 'w') as class_outfile:
                                    class_outfile.write(coord_search_class.to_string())
                                
                            df_coord_target     = coord_search_class.loc[coord_search_class['fits_target']==target]
                            df_coord_target     = df_coord_target.sort_values(by=['sep'])
                            
                            if not UNDER_DEVELOPMENT and (not df_coord_target.loc[df_coord_target['sep']>=separation_thres].empty): # in mas
                                
                                c_source = df_coord_target['coordinate'].values[0]
                                coord_splitted = str(c_source).split(' ')
                                
                                c_source = ' '.join(coord_splitted[:-1] + [coord_splitted[-1].replace(':','.')])
                                if not '_shifted' in obs['ms_name'] : obs['ms_name'] = str(Path(obs['ms_name']).stem)+ '_shifted' + str(Path(obs['ms_name']).suffix)
                                
                                vis_shifted = f"{str(wd_meta.wd)}/{obs['ms_name']}"
                                visorig     = vis
                                
                                if vis == vis_shifted:          # this means that there are multiple targets in the MS, needing phaseshift.
                                    vis         = f"{vis}.old"
                                    shutil.move(visorig, vis)
                                
                                pout = f"\nThe following sources were found to be {np.round(df_coord_target['sep'].values[0]/1e3, 2)} arcsec from phase-center and will be phase-shifted:\n"
                                pout += f"{target}:\t {c_source}"
                                print(pout)
                                log.info(f"{pout}")
                                
                                if Path(vis_shifted).exists():
                                    del_fl(str(Path(vis_shifted).parent), 0, fl=f"{Path(vis_shifted).name}", rm=True)
                                    
                                # -----------------------------------------------------------
                                # # split the file w/o target and
                                # # phaseshift and split the target
                                # # 
                                # # virtualconcatenate to vis_shifted
                                # ---------- ------------------------- -----------------------
                                
                                subprocess.run([PHASESHIFT_PERL_SCRIPT,'--vis', vis, '--outvis',vis_shifted, '--c', c_source, '--target', target])
                                success_val     =   'partial'
                                
                                if Path(vis_shifted).exists():
                                    del_fl(str(Path(vis_shifted).parent), 0, fl=f"{Path(vis_shifted).name}.old", rm=True)
                                    vis             =   vis_shifted
                                    
                                    obs['ms_name']  =   str(Path(vis).name)
                                    
                                    success_val     =   str(vis_shifted)
                                    update_from_vascometa(wd_ifolder_freqid, inpfile='observation.inp', val_dict=obs)
                                else:
                                    if not Path(visorig).exists():
                                        shutil.move(vis, visorig)
                            
                            else:
                                success_val     =   'skipped'
                                print(" ...target is within 1 arcsec, not performing phaseshift\n\n")
                            
                            self.result.success_count   +=   1
                            _               =   lf.put_value(f"{success_val}", self.colnames.working_col, 1)
                        except Exception as e:
                            traceback.print_exc()
                            log.exception(e)
                            errfile              =   latest_file(Path(wd_ifolder).parent, pattern='*mpi*err*')
                            self.result.failed_count               =   lf.put_value(f"{errfile}", self.colnames.comment_col, self.result.failed_count)
                            _                    =   lf.put_value("failed", self.colnames.working_col, self.result.failed_count)
        self.result.end_stamp   = datetime.now()
        
        return self.result
        
class AverageMS(PipelineStepBase):
    """
        _______________________________________________________
        
        - When required average data to 2s and 500KHz in time and frequency resolution.
        - split the averaged data by removing filtered anenna.
        
        _________________________________________________________
        
    """
    
    # ----------------------------------------------------------
    name            =   "vasco_avg"
    colnames        =   ColName('vasco_avg', 'Comment_avg', 'timestamp_avg')
    py_env          =   "casa-6.7"
    description     =   """Average the Measurement Set to have INTTIM=2sec, CHWIDTH=500KHz | uses CASA task mstransform"""
    validate_by     =   [InitVariables, RunValidation, UpdateResults, UpdateSheet]
    result          =   StepResult(name=name, detail={},
                                       success_count=0, failed_count=0, start_stamp=datetime.now())
    
    # ----------------------------------------------------------
    
    def run(self, lf, wd_ifolder, casadir, verbose=True):
        from vasco.ms.meta import BandInfoMS
        # log = logging.getLogger("vasco.pipeline")
        
        global_bands_dict               =   {}
        self.result.detail              =   {}
        band_counts                     =   {}
        bands_known                     =   []
        
        min_expt                        =   1.4
        wds_ifolder_for_payload         =   []
        
        wd_meta                         =   WorkDirMeta(wd_ifolder=wd_ifolder)
        metafile_av_iwd_ff              =   wd_meta.metafile_available_wd_ff
        wd_ifolders                     =   read_metafile(metafile_av_iwd_ff)['input_folder'] if metafile_av_iwd_ff is not None and  Path(metafile_av_iwd_ff).exists() else [wd_ifolder]
        
        # --------------------------------------------------------------------
        msg                         =   "iterating through the previously used input folders"
        log.info(msg)
        with step_stage(msg):
            del_fl(wd_meta.metafolder, 0, wd_meta.msmeta_sources, rm=True)
            
            for wd_ifolder in wd_ifolders:    
                obs                 =   wd_meta.obs_dic
                vis                         =   wd_meta.vis
                
                if vis is None:
                    raise FileNotFoundError(f"vis not found : {vis}")
                
                timebin             =   "2s"
                mpi_cores           =   15
                
                bandms              =   BandInfoMS(vis, min_expt, verbose=verbose)
                bands_in_wd_ifolder =   list(bandms.bands_dict.keys())
                
                for band in bands_in_wd_ifolder:
                    if band in band_counts:
                        band_counts[band]       +=  1
                        bandms.bands_dict[f"{band}{band_counts[band]}"] = bandms.bands_dict.pop(band)
                    else:
                        if 'known' not in band:
                            band_counts[band]   =   1
                global_bands_dict.update(bandms.bands_dict)
                save_metafile(wd_meta.metafile_msmeta_sources, {'bands_dict': global_bands_dict})
                
                
                band_chwidth, good_scan_list, missing_antennas  = {}, [], set()
                msg                             =   "gathering band information"
                log.info(msg)
                with step_stage(msg):
                    try:
                        success_band            =   []
                        
                        for band in bandms.bands_dict:
                            for bandobsid in range(bandms.bands_dict[band]['nobs']):
                                bandobs         =   f"{band}{bandobsid}" if bandms.bands_dict[band]['nobs']>1 else f"{band}"
                                bands_known.append(bandobs)
                                d_bands         =   bandms.get_band_detail(band)[f"{band}{bandobsid}"]
                                wd_b, iwd_b     =   wd_meta.to_new_WD(bandobs, target="")
                                                                                                        # changed the input_template name as the freqid identifier number is bogus, and band key is unique
                                iwd_b_new       =   f"{wd_b.absolute()}/input_template_{bandobs}"    
                                shutil.move(str(iwd_b), iwd_b_new)
                                iwd_b           =   iwd_b_new
                                
                                
                                for spw in d_bands['spws']:
                                    good_scan_list.append(d_bands[spw]['good_scans'])
                                    missing_antennas.update(d_bands['missing_antennas'])
                                
                                nchan       =   [d_bands[s]['nchan'] for s in d_bands['spws']]
                                chwidth     =   [d_bands[s]['chwidth'] for s in d_bands['spws']]
                                bw_khz      =   min([d_bands[s]['bw_khz'] for s in d_bands['spws']])
                                timeavg     =   d_bands['timeavg']
                                
                                spws            =   [f"{s}:0~{d_bands[s]['nchan']-1}" for s in d_bands['spws']]
                                
                                chanbin = [single_ifcheck(nch, chwidth[i]) for i, nch in enumerate(nchan)]  # List[int]

                                if isinstance(chanbin, list) and len(set(chanbin)) == 1:
                                    chanbin = chanbin[0]            # single int

                                chanavg = (max(chanbin) > 1) if isinstance(chanbin, list) else (chanbin > 1)
                                
                                # chanbin         =   ",".join(chanbin)
                                good_scans      =   ",".join(set.intersection(*good_scan_list))
                                an_remove       =   ";".join([f"!{an}" for an in missing_antennas])
                                
                                obs_b, _, _                     =   read_inputfile(wd_ifolder, "observation.inp")
                                if f'_{band}.ms' not in obs['ms_name']:
                                    obs_b['ms_name']            =   obs['ms_name'].replace('.ms', f'_{band}.ms')

                                outvis                          =   str(Path(iwd_b).parent / obs_b['ms_name'])
                                
                                if outvis==vis:
                                    raise NameError("both outvis and vis are the same file")        
                                
                                chanavg                         =   False
                                band_chwidth[band]              =   chwidth
                                
                                    # ---------------------------------------------------   Execution
                                if Path(outvis).exists():
                                    self.result.detail[band]     =   "vis-exists"
                                else:
                                    
                                    msg                 =   "executing casatask payload mstransform"
                                    log.info(msg)
                                    with step_stage(msg, chanbin=chanbin):
                                        casalogfile     =   f'{wd_b}/{get_logfilename(fnname=self.name, start_stamp=self.result.start_stamp, module_name="casa")}'
                                        errcasalogfile     =   f'{wd_b}/{get_logfilename(fnname=self.name, start_stamp=self.result.start_stamp, module_name="err-casa")}'
                                        
                                        task            =   MsTransform(vis=vis, outputvis=outvis, antenna=an_remove,scan=good_scans,
                                                                chanbin=chanbin, spw=",".join(spws), chanaverage=chanavg, 
                                                                timeaverage=timeavg, timebin=timebin)
                                        
                                        step             =   task.to_step(logfile=casalogfile, casadir=casadir, errf=errcasalogfile, mpi_cores=mpi_cores)
                                        tasks_list        =   [step]
                                        wds_ifolder_for_payload.append(wd_ifolder)
                                        wd_meta.wd_used
                                            
                                    
                                    payload             =   MpiCasaPayload(tasks_list=tasks_list)
                                    payload.run()
                                    if not Path(outvis).exists():
                                        self.result.detail[band]     =   f"check {errcasalogfile}"  
                                        self.result.success.append(False)
                                    else: 
                                        str(Path(outvis).name)
                                    
                                    # --------------------------------------------------------------------
                                
                                if Path(outvis).exists():
                                    self.result.success.append(True)
                                    fillinp_fromiwd(wd_ifolder, iwd_b)
                                    create_config(obs_b, f'{iwd_b}/observation.inp')
                                    success_band.append(band)
                                    
                        
                        succeed         =   len(success_band)/len(bands_known)                                                       # this should update for each freqid 
                        comment_val     =   " ".join([f"{b}:{w} kHz" for b,w in band_chwidth.items() if b in success_band])
                        success_val     =   " ".join([f"{b}:{td_b}" for b,td_b in self.result.detail.items()])
                        
                        if succeed  == 1:
                            # success_val =   lf.get_value(col) + ' ' + success_val if lf.get_value(col) else success_val
                            comment_val                     =   lf.get_value(self.colnames.comment_col) + ' ' + comment_val if lf.get_value(self.colnames.comment_col) else comment_val
                            self.result.success_count       +=  1
                            _                               =   lf.put_value(success_val, self.colnames.working_col, self.result.success_count)        
                            _                               =   lf.put_value(comment_val, self.colnames.comment_col)
                            
                        elif succeed>0:
                            _                               =   lf.put_value(success_val, self.colnames.working_col, self.result.success_count)
                            failed_band                     =   " ".join([f"{b}: failed" for b,w in band_chwidth.items() if b not in success_band])
                            self.result.failed_count        +=  1
                            _                               =   lf.put_value(f'{comment_val} {failed_band}', self.colnames.comment_col, self.result.failed_count)
                        else:
                            self.result.failed_count        +=  1
                            _                               =   lf.put_value('failed', self.colnames.working_col, self.result.failed_count)
                            
                    except Exception as e:
                        traceback.print_exc()
                
        global_bands_dict['bands_known'] = bands_known
        save_metafile(wd_meta.metafile_msmeta_sources, {'bands_dict': global_bands_dict})
        
        self.result.end_stamp   =   datetime.now()
        
        return self.result

class VascoMetaMS(PipelineStepBase):
    """
        _______________________________________________________

        - Creates metadata by identifying sources from MS file per band.
        - Saves msmeta and sources vasco files per band.

        _________________________________________________________

    """

    # ----------------------------------------------------------
    name        = "vascometa_ms"
    colnames    = ColName('vascometa_ms', 'Comment_metams', 'timestamp_metams')
    py_env      = "casa-6.7"
    description = """Creates MS metadata by identifying sources per band"""
    validate_by     =   [InitVariables, RunValidation, UpdateResults, UpdateSheet]
    result      = StepResult(name=name, detail={},
                             success_count=0, failed_count=0, start_stamp=datetime.now())

    # ----------------------------------------------------------

    def run(self, lf, wd_ifolder, init_params, rfc_catalogfile, target, verbose=True):
        from vasco.ms import identify_sources_fromtarget_ms
        
        
        log             = logging.getLogger("vasco.pipeline")
        self.result.detail = {}

        wd_meta         = WorkDirMeta(wd_ifolder=wd_ifolder)
        metafolder      = Path(wd_meta.metafolder)

        bands_dict      = read_metafile(wd_meta.metafile_msmeta_sources)['bands_dict']
        bands           = list(bands_dict['bands_known'])
        success_band    = []
        vasco_b         = {}
        
        msg = f"iterating through bands for MS metadata: {', '.join(bands)}"
        log.info(msg)
        with step_stage(msg):
            try:
                for band in bands:
                    success             =   True
                    wd_b, _             = wd_meta.to_new_WD(band, target='', create=False)
                    
                    metadir_b         =   Path(f"{wd_b}/vasco.meta/")
                    metadir_b.mkdir(exist_ok=True)
                    
                    iwd_b_new           = f"{wd_b.absolute()}/input_template_{band}"
                    obs_b, _, _         = read_inputfile(iwd_b_new, "observation.inp")
                    
                    vis_b           = str(Path(iwd_b_new).parent / obs_b['ms_name']) if 'ms_name' in obs_b and obs_b['ms_name'] else None
                    
                    errf = ""
                    try:
                        s_dict              =   identify_sources_fromtarget_ms(vis_b, target_source=target, caliblist_file=rfc_catalogfile,
                                                    flux_thres=0.150, min_flux=0.025, ncalib=20, flux_df=None, 
                                                    sourcenames=None, hard_selection=False, metafolder=str(metadir_b))
                    except Exception:
                        traceback.print_exc()
                        
                    if not Path(metadir_b / 'msmeta_sources.vasco').exists():
                        success = False
                    else:
                        msmeta_b    = read_metafile(str(metadir_b / 'msmeta_sources.vasco'))
                        save_metafile(str(metafolder / f'msmeta_sources_{band}_{target}.vasco'), msmeta_b)
                        
                        for band, sources_d in s_dict.items():
                            print(band, "band")
                            save_metafile(str(metafolder / f'sources_ms_{band}_{target}.vasco'),     sources_d)
                            update_from_vascometa(iwd_b_new, inpfile='observation.inp', val_dict=sources_d)
                                
                        success_band.append(band)

                    if Path(vis_b).exists():
                        if not check_target_in_ms(vis_b, target):
                            errf = 'target missing'

                    vasco_b[band]               = (success, errf)
                    self.result.detail[band]    = errf if not success else 'ok'
                    self.result.success.append(success)

                vasco_sources_ms    = glob.glob(str(metafolder / f'sources_ms_*_{target}.vasco'))
                succeed             = len(success_band) / len(bands) if bands else 0
                success_val         = " ".join([f"{b}:{'ok' if s else e}" for b, (s, e) in vasco_b.items()])

                if succeed == 1:
                    self.result.success_count   = lf.put_value(success_val, self.colnames.working_col,
                                                               self.result.success_count)
                elif succeed > 0:
                    failed_band                 = " ".join([f"{b}:failed" for b, (s, _) in vasco_b.items() if not s])
                    _                           = lf.put_value(success_val, self.colnames.working_col,
                                                               self.result.success_count)
                    self.result.failed_count    = lf.put_value(failed_band, self.colnames.comment_col,
                                                               self.result.failed_count)
                else:
                    self.result.failed_count    = lf.put_value('failed', self.colnames.working_col,
                                                               self.result.failed_count)

            except Exception:
                traceback.print_exc()
        self.result.desc = success_band
        self.result.end_stamp = datetime.now()
        return self.result

class SnRating(PipelineStepBase):
    """
        _______________________________________________________
        
        - iteratively run s/n rating through each workdir
        - 
        
        _________________________________________________________
        
    """
    
    # ----------------------------------------------------------
    name            =   "vasco_snr"
    colnames        =   ColName('vasco_snr', 'Comment_vasco_snr', 'timestamp_vasco_snr')
    py_env          =   "casa-6.7"
    description     =   """To do a short fringefit to get the signal-to-noise rating"""
    validate_by     =   [InitVariables, RunValidation, UpdateResults, UpdateSheet]
    result          =   StepResult(name=name, detail={},
                                       success_count=0, failed_count=0, start_stamp=datetime.now())
    
    # ----------------------------------------------------------
    
    def run(self, lf, wd_ifolder, init_params, casadir, target, n_refant=5, n_calib=6, multiband_snrating=True, n_scan_snrting=7, verbose=True):
        from vasco.ms import get_best_spws
        log                             =   logging.getLogger("vasco.pipeline")
        band_count                      =   0
        
        wd_meta                         =   WorkDirMeta(wd_ifolder=wd_ifolder)
        metafolder                      =   Path(wd_meta.metafolder)
        desc                             =   {}
        iter_scan_count                 =   init_params['iter_scan_count_snrating'] if 'iter_scan_count_snrating' in init_params else 5
        
        bands_dict                      =   read_metafile(wd_meta.metafile_msmeta_sources)['bands_dict']
        bands                           =   list(bands_dict['bands_known'])
        nband                           =   0
        
        msg                             =   f"iterating through the workdir for each bands: {','.join(bands)}"
        log.info(msg)
        with step_stage(msg):
            for band in bands:
                success                     =   True
                msmetafile_b                =   metafolder / f'msmeta_sources_{band}_{target}.vasco'
                if msmetafile_b.exists():
                    allsd, spwsd                =   read_vasco_sources_msmeta(msmetafile_b)
                    alls                        =   allsd[band[0]]                                                  # band only useful single letter in metadata
                    desc[band]                   =   []
                    
                    wd_b, iwd_b                 =   wd_meta.to_new_WD(band, target='', create=False)
                    print(wd_b)
                    obs_b                       =   wd_meta.get_inp(band=band, inpfile="observation.inp")
                    
                    
                    vis_b                       =   str(iwd_b.parent / obs_b['ms_name']) if 'ms_name' in obs_b and obs_b['ms_name'] else None
                    nband                       +=  1
                    
                    if vis_b and Path(vis_b).exists():

                        del_fl(Path(iwd_b).parent,0, '*tmp*', rm=True)
                        del_fl(Path(iwd_b).parent, 0, '*stored*', rm=True)
                        del_fl(Path(iwd_b).parent, 0, '*fringe*', rm=True)
                        del_fl(Path(iwd_b).parent, 0, '*fft*', rm=True)
                        refants                 =   ['failed']
                        caltable_folder         =   wd_b / "fft_tab"
                        caltable_folder.mkdir(exist_ok=True)
                        

                        if target in alls: alls.remove(target)
                        allsources                      =   [target] + alls                     # ensuring the target is the first source.
                        goodspws                        =   get_best_spws(vis_b)
                        goodspws                        =   [int(spw) for spw in goodspws]
                        
                        metadir_b                    =   wd_b / "vasco.meta"
                        metadir_b.mkdir(exist_ok=True)
                        
                        msg                             =   f"preparing run for fringefit on {Path(vis_b).name}"
                        log.info(msg)
                        with step_stage(msg):
                                
                            # fdr                             =   FringeDetectionRating(vis=vis_b, caltable_folder=str(caltable_folder), 
                            #                                         n_refant=n_refant, n_calib=n_calib, n_scans=n_scan_snrting, iter_scan_count=iter_scan_count,
                            #                                         selected_sources=allsources, selected_scans=[], selected_ants=[], selected_spws=goodspws,
                            #                                         gaintables=[], interp=[], verbose=verbose)
                            # success                         =   True
                            
                            
                            cmd                             =     VascoSnRatinCMD(vis=str(vis_b), caltable_folder=str(caltable_folder), 
                                                                        n_refant=int(n_refant), n_calib=int(n_calib), n_scans=int(n_scan_snrting), 
                                                                        iter_scan_count=int(iter_scan_count),
                                                                        selected_sources=list(allsources), selected_scans=[], selected_ants=[], 
                                                                        selected_spws=goodspws,
                                                                        gaintables=[], interp=[], metafolder=str(metadir_b), verbose=verbose)
                            
                            payload                          =     MpiVascoPayload(cmd = cmd, casadir=str(casadir),mpi_cores=5)
                            msg                             =   f"running fringefit on {Path(vis_b).name}"
                            log.info(msg)
                            with step_stage(msg):
                                try:
                                    payload.run()
                                    # dic_field, refants, pp_out  =   fdr.exec_FFT_fringefit(multiband=multiband_snrating)
                                    
                                    dic_field, refants, pp_out      =   cmd.get_result()
                                    log.info(f"\t\t{pp_out}")
                                    if verbose: print(f"\t\t{pp_out}")
                                    vasco_sources               =   metadir_b / wd_meta.meta_sources_snrating
                                    vasco_refants               =   metadir_b / wd_meta.meta_refants_snrating
                                    vasco_snr_out               =   metadir_b / wd_meta.snrating_out
                                    
                                    vasco_sources_dest               =   metafolder / f'{Path(wd_meta.meta_sources_snrating).stem}_{band}_{target}.vasco'
                                    vasco_refants_dest               =   metafolder / f'{Path(wd_meta.meta_refants_snrating).stem}_{band}_{target}.vasco'
                                    vasco_snr_out_dest               =   metafolder / f'{Path(wd_meta.snrating_out).stem}_{band}_{target}.out'
                                    
                                    # save_metafile(vasco_snr_out, pp_out)
                                    save_metafile(vasco_sources_dest, dic_field)
                                    save_metafile(vasco_refants_dest, {"refant":refants})
                                    shutil.move(vasco_snr_out, vasco_snr_out_dest)

                                except Exception:
                                    traceback.print_exc()
                                    success=False
                        
                        print("success:", success)
                        if success:
                            
                            if vasco_refants.exists() and vasco_sources.exists():
                                band_count              +=  1
                                desc[band].extend(refants)
                            else:
                                success                 =   False
                        
                        self.result.success.append(success)
                        print("success:", success)
                        refants_str                         =   ','.join(refants)
                        col_value                           =   f'{lf.get_value(colname=self.colnames.working_col)} {f"{band}:{refants_str}"}'.strip()
                        if not success:
                            self.result.failed_count        +=   1
                            _                               =   lf.put_value(col_value, self.colnames.working_col, self.result.failed_count)
                            self.result.success.append(False)
                        else:
                            
                            self.result.success_count       +=   1
                            _                               =   lf.put_value(col_value,self.colnames.working_col, 
                                                                             self.result.success_count)
                            self.result.success.append(True)
            self.result.desc = desc[band]
        self.result.end_stamp   =   datetime.now()
        return self.result

class FillInputMs(PipelineStepBase):
    """
        _______________________________________________________
        
        - Fills input folder using metadata from the s/n rating if exists.
        
        _________________________________________________________
        
    """
    
    # ----------------------------------------------------------
    name            =   "vasco_fill_input"
    colnames        =   ColName('vasco_fill_input', 'Comment fill_input', 'timestamp_fill_input')
    py_env          =   "casa-6.7"
    description     =   """fill the rPicard input using the metadata from the previous step"""
    validate_by     =   [InitVariables, RunValidation, UpdateResults, UpdateSheet]
    result          =   StepResult(name=name, detail={},
                                       success_count=0, failed_count=0, start_stamp=datetime.now())
    
    # ----------------------------------------------------------
    
    def run(self, lf, wd_ifolder, rfc_catalogfile, target, n_calib=6, hi_freq_ref=11, verbose=True):
        
        log                             =   logging.getLogger("vasco.pipeline")
        
        wd_meta                         =   WorkDirMeta(wd_ifolder=wd_ifolder)
        metafolder                      =   Path(wd_meta.metafolder)
        desc                             =   {}
        
        bands_dict                      =   read_metafile(wd_meta.metafile_msmeta_sources)['bands_dict']
        bands                           =   list(bands_dict['bands_known'])
        errf                            =   ""
        msg                             =   f"iterating through the workdir for each bands: {','.join(bands)}"
        log.info(msg)
        with step_stage(msg):
            for band in bands:
                
                success                     =   True
                print(f"found {band} band..")
                wd_b, iwd_b                       =   wd_meta.to_new_WD(band=band, target="")
                params                    =   wd_meta.get_inp(band=band, inpfile="observation.inp")
                vis_b                         =   Path(iwd_b).parent / params['ms_name'] if params['ms_name'] else None

                if vis_b and vis_b.exists():
                    sourcesf                    =   f'{Path(wd_ifolder).parent}/vasco.meta/sources_{band}_{target}.vasco'
                    refantsf                    =   f'{Path(wd_ifolder).parent}/vasco.meta/refants_{band}_{target}.vasco'
                    sourcesf_snr                =   f'{Path(wd_ifolder).parent}/vasco.meta/sources_snr_{band}_{target}.vasco'
                    if Path(sourcesf).exists() and read_metafile(sourcesf):
                        
                        success                     =   fill_input_byvalues(iwd_b,          
                                                                            iwd_b, 
                                                                            str(vis_b), target,
                                                                            flux_thres=7, 
                                                                            n_calib=n_calib,  
                                                                            caliblist_file=rfc_catalogfile, 
                                                                            sourcesf=sourcesf, refantsf=refantsf, sourcesf_snr=sourcesf_snr, 
                                                                            band=band[0], edgeflagging=True, 
                                                                            pipe_params=PipelineContext.params,
                                                                            hi_freq_ref=hi_freq_ref) # TODO: complete population of input parameters from user provided config file
                    else:
                        success                 =   False
                        errf                    =   "check prev"
                else:
                    success                     =   False
                    errf                        =   "no vis"
                if not success:
                    found = check_target_in_ms(str(vis_b), target)
                    if not found:
                        errf = "target missing"
                    if not errf:   errf         =   str(latest_file(Path(iwd_b).parent, f'*err.out*'))
                    _                           =   lf.put_value(f"{lf.get_value(colname=self.colnames.working_col)} {band}:{errf}".strip(), self.colnames.working_col, self.result.failed_count)
                    
                    self.result.failed_count      += 1
                    self.result.detail[band]          =   errf
                    self.result.success.append(False)
                    
                else:
                    self.result.success_count                       =   lf.put_value(f"{lf.get_value(colname=self.colnames.working_col)} {band}:done".strip(), 
                                                                                     self.colnames.working_col, self.result.success_count)
                    print(f"filled band : {band}")
                    self.result.success_count             +=  1
                    self.result.detail[band]          =   "done"
                    self.result.success.append(True)
                
        
        self.result.end_stamp                   =   datetime.now()
        return self.result
    
class FinalSplitMs(PipelineStepBase):
    """
        _______________________________________________________
        
        - Uses mstransform to split the input visibility to contain only the final selected sources.
        
        
        _________________________________________________________
        
    """
    
    # ----------------------------------------------------------
    name            =   "vasco_split_ms"
    colnames        =   ColName('vasco_split_ms', 'Comment split ms', 'timestamp_split_ms')
    py_env          =   "casa-6.7"
    description     =   """Split the MS file to only contain selected sources."""
    validate_by     =   [InitVariables, RunValidation, UpdateResults, UpdateSheet]
    result          =   StepResult(name=name, detail={},
                                       success_count=0, failed_count=0, start_stamp=datetime.now())
    
    # ----------------------------------------------------------
    
    def run(self, lf, wd_ifolder, casadir, target, verbose=True):
        from vasco.ms import get_best_spws
        log                             =   logging.getLogger("vasco.pipeline")
        wd_meta                         =   WorkDirMeta(wd_ifolder=wd_ifolder)
        metafolder                      =   Path(wd_meta.metafolder)
        desc                             =   {}
        wds_ifolder_for_payload         =   []
        
        bands_dict                      =   read_metafile(wd_meta.metafile_msmeta_sources)['bands_dict']
        bands                           =   list(bands_dict['bands_known'])
        nband                           =   0
        
        msg                             =   f"iterating through the workdir for each bands: {','.join(bands)}"
        log.info(msg)
        with step_stage(msg):
            for band in bands:
                print(f"found {band} band..")
                wd, iwd_b                       =   wd_meta.to_new_WD(band=band, target="")
                msmetafile_b                    =   metafolder / f'msmeta_sources_{band}_{target}.vasco'
                if msmetafile_b.exists():
                    allsd, spwsd                =   read_vasco_sources_msmeta(msmetafile_b)
                    allsources                  =   allsd[band[0]]
                    spws                        =   spwsd[band[0]]
                    
                    params, _, _                    =   read_inputfile(iwd_b, "observation.inp")
                    ms_name                         =   Path(iwd_b).parent / params['ms_name'] if params['ms_name'] else None   # ms_name is our working ms file

                    if ms_name and ms_name.exists():
                        spws                            =   [str(spw) for spw in spws]
                        obs_b                           =   wd_meta.get_inp(band=band, target="")
                        vis_b                       =   Path(iwd_b).parent / obs_b['ms_name'] if obs_b['ms_name'] else None   # should be VLBI_{band}.ms OR # should be VLBI_{band}_old.ms
                        orig_vis_b                  =   deepcopy(vis_b)
                    
                        old_file                        =   vis_b.parent / Path(f"{vis_b.stem}_old{vis_b.suffix}")
                        nband                       +=  1
                        del_fl(Path(old_file).parent, 0, f'{Path(old_file).stem}*', rm=True)                                    # delete all VLBI_{band}_old.ms*
                        
                        if f'_old{vis_b.suffix}' not in str(vis_b):
                            vis_b                             =   vis_b.rename(old_file)                 # mv VLBI_{band}.ms ----->  VLBI_{band}_old.ms
                            
                        wd_t, iwd_b_t                       =   wd_meta.to_new_WD(band, target=target, create=False)
                        if Path(wd_t).exists(): 
                            shutil.rmtree(wd_t)
                        wd_t, iwd_b_t                       =   wd_meta.to_new_WD(band, target=target, create=True)
                        outvis                              =   wd_t / vis_b.name
                        
                        if outvis==vis_b:
                            raise TypeError(f"both outvis and vis are the same file {vis_b}")
                        
                        allsources                           =   alls_fromobs(obs_b)
                        
                        del_fl(wd_t, 0, fl=f"{outvis.name}*", rm=True)                                 # deletes all VLBI_{band}_{target}.ms* i.e also flagversions
                        del_fl(wd_t, 0, fl="*stored*", rm=True)
                        del_fl(wd_t, 0, fl="*tmp*", rm=True)
                        listof_uniquespws = get_best_spws(str(vis_b))
                        listof_uniquespws = [str(bspw) for bspw in listof_uniquespws]
                        
                        # ---------------------------------------------------   Execution
                        
                        msg                 =   "executing casatask payload mstransform"
                        log.info(msg)
                        with step_stage(msg):
                            casalogfile     =   f'{wd_t}/{get_logfilename(fnname=self.name, start_stamp=self.result.start_stamp, module_name="casa")}'
                            errcasalogfile  =   f'{wd_t}/{get_logfilename(fnname=self.name, start_stamp=self.result.start_stamp, module_name="err-casa")}'
                            
                            task            =   MsTransform(vis=str(vis_b), outputvis=str(outvis), field=",".join(allsources),
                                                    spw=",".join(listof_uniquespws))
                            
                            step             =   task.to_step(logfile=casalogfile, casadir=casadir, errf=errcasalogfile, mpi_cores=10)
                            tasks_list        =   [step]
                            wds_ifolder_for_payload.append(wd_ifolder)
                            
                            tasks_payload   =   MpiCasaPayload(tasks_list=tasks_list)
                            tasks_payload.run()
                            self.result.detail[band]     =   "check mstransform" if not Path(outvis).exists() else str(Path(outvis).name)
                        
                        if Path(outvis).exists(): 
                            msg                 =   "creating input and updating values"
                            log.info(msg)
                            with step_stage(msg):
                                desc[band]                 =   outvis.name
                                self.result.success_count   +=  1
                                
                                arr_finetune                    =   wd_meta.get_inp(band=band, target=target, inpfile="array_finetune.inp")
                                arr                             =   wd_meta.get_inp(band=band, target=target, inpfile="array.inp")
                                arr_finetune['rldly_stations']  =   ",".join(arr['refant'][:3])
                                
                                create_config(arr_finetune, f'{iwd_b_t}/array_finetune.inp')
                                fillinp_fromiwd(iwd_b, iwd_b_t)
                                create_config(obs_b, f'{iwd_b_t}/observation.inp')
                        else:
                            self.result.success.append(False)
                            desc[band]                 =   "casa task failed"
                        
                        if vis_b.exists() and "_old" in vis_b.name:
                            vis_b.rename(orig_vis_b)                        # mv VLBLI_{band}_old.ms --> VLBI_{band}*.ms
                        
                        self.result.detail[band] = str(vis_b)
                            
                        obs_b['ms_name']                =   vis_b.name
                        create_config(obs_b, f'{iwd_b_t}/observation.inp')
                        self.result.success.append(True)
                    else:
                        self.result.success.append(False)
                        desc[band]                 =   "no vis"
                    
                    if not self.result.success[-1]:
                        _        =   lf.put_value(f"{lf.get_value(colname=self.colnames.working_col)} {band}:{desc[band]}".strip(), 
                                                                         self.colnames.working_col, self.result.failed_count)
                        self.result.failed_count      += 1
                        
                        self.result.success.append(False)
                    else:
                        _        =   lf.put_value(f"{lf.get_value(colname=self.colnames.working_col)} {band}:{desc[band]}".strip(), 
                                                                         self.colnames.working_col, self.result.success_count)
                        desc[band]=f"..splitted {','.join(allsources)} for band : {band} ({target})"
                        print(desc[band])
                        self.result.success_count+=1
                        self.result.desc.append(desc[band])
                    
        
        self.result.end_stamp = datetime.now()
        
        return self.result

class Calibration(PipelineStepBase):
    """
        _______________________________________________________
        
        - Runs the complete rPicard calibrtion framework.        
        
        _________________________________________________________
        
    """
    
    # ----------------------------------------------------------
    name            =   "rpicard"
    colnames        =   ColName('rpicard', 'Comment_rpicard', 'timestamp_rpicard')
    py_env          =   "casa-6.7"
    description     =   """run the complete rPicard calibrtion framework."""
    validate_by     =   [InitVariables, RunValidation, UpdateResults, UpdateSheet]
    result          =   StepResult(name=name, detail={},
                                       success_count=0, failed_count=0, start_stamp=datetime.now())
    
    # ----------------------------------------------------------
    
    def run(self, lf, wd_ifolder, casadir, target, verbose=True):
        from vasco.ms import get_best_spws
        log                             =   logging.getLogger("vasco.pipeline")
        wd_meta                         =   WorkDirMeta(wd_ifolder=wd_ifolder)
        metafolder                      =   Path(wd_meta.metafolder)
        desc                             =   {}
        wds_ifolder_for_payload         =   []
        
        bands_dict                      =   read_metafile(wd_meta.metafile_msmeta_sources)['bands_dict']
        bands                           =   list(bands_dict['bands_known'])
        
        msg                             =   f"iterating through the workdir for each bands: {','.join(bands)}"
        log.info(msg)
        with step_stage(msg):
            for band in bands:
                print(f"found {band} band..")
                wd_t, iwd_b_t                       =   wd_meta.to_new_WD(band, target=target, create=False)
                obs_b_t                             =   wd_meta.get_inp(band=band, target=target, inpfile="observation.inp")
                allsources                          =   alls_fromobs(obs_b_t)
                
                exp_calibrated_files            =   [str(wd_t / f"{src}_calibrated.uvf") for src in allsources]
                vis                             =   wd_t / obs_b_t['ms_name'] if obs_b_t['ms_name'] else None
                if '_old' in str(vis):
                    obs_b_t['ms_name']            =   str(vis.stem).replace('_old', '') + str(vis.suffix)
                    create_config(obs_b_t, f'{iwd_b_t}/observation.inp')
                    new_vis_path                =   vis.parent / obs_b_t['ms_name']
                    vis                         =   vis.rename(new_vis_path)
                
                del_fl(wd_t,0, '*.ms.flagversions', rm=True)
                del_fl(wd_t,0, '*ms.avg', rm=True)
                del_fl(wd_t,0, '*tmp*', rm=True)
                del_fl(wd_t, 0, '*.stored*', rm=True)
                del_fl(wd_t, 0, '*fringe*', rm=True)
                del_fl(wd_t,0, '*.uvf', rm=True)
                del_fl(wd_t,0, '*calibration_tables', rm=True)
                
                
                payload         =   PicardPayload(PicardTask(input=iwd_b_t, n=PipelineContext.params['mpi_cores_rpicard']))
                payload.run()
            
                calibrated_files = glob.glob(f"{wd_t}/*_calibrated.uvf")
                col                 =   self.colnames.working_col
                comment_col = self.colnames.comment_col
                calibrated_sources = [str(Path(calfile).name).replace("_calibrated.uvf", "") for calfile in calibrated_files]
                missing_sources = list(set(allsources).difference(calibrated_files))
                desc[band]                  =   f"calibrated {','.join(calibrated_sources)}"
                target_calfile = [str(calfile) for calfile in calibrated_files if target in calfile]
                self.result.detail[band] = target_calfile[0] if len(target_calfile) else "uvf not found"
                
                print("calibrated_files", calibrated_files)
                
                self.result.desc.append(desc[band])
                
                if len(exp_calibrated_files) > len(calibrated_files):    
                    
                    print("expected calibrated_files", exp_calibrated_files)
                if len(calibrated_files)==len(exp_calibrated_files):
                    self.result.success.append(True)
                    _   =   lf.put_value(f"{lf.get_value(colname=col)} {band}:{desc[band]}".strip(), col, self.result.success_count)
                    self.result.success_count += 1
                elif len(calibrated_files)>0:
                    _   =   lf.put_value(f"{lf.get_value(colname=col)} {band}:{desc[band]}".strip(), col, self.result.success_count)
                    _   =   lf.put_value(f"{lf.get_value(colname=comment_col)} {band}:missing {','.join(missing_sources)}".strip(), comment_col, self.result.success_count)
                    self.result.success_count += 1
                else:
                    errf    =   latest_file(wd_t, '*err.out*')
                    self.result.success.append(False)
                    errv    =   ','.join(missing_sources)
                    _       =   lf.put_value(f"{lf.get_value(colname=col)} {band}:{errv}".strip(), col, self.result.success_count)
                    _       =   lf.put_value(f"{lf.get_value(colname=comment_col)} {band}:{errf}".strip(), comment_col, self.result.failed_count)
                    self.result.failed_count += 1
                    self.result.detail[band] = f"{errv},{errf}"

            self.result.end_stamp           =   datetime.now()
            return self.result

