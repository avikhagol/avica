from casatools import logsink

vascolog=logsink('vasco.casa_log')
vascolog.setlogfile='vasco.casa_log'
vascolog.setglobal(True)

from casatools import table
from casatasks import fringefit, listobs, flagdata, mstransform
from casatools import table
from casatools import msmetadata
import sys
from pathlib import Path
from datetime import datetime
from pandas import DataFrame as df, concat as pdconc
from astropy.time import Time, TimeDelta
from astropy.coordinates import SkyCoord
from astropy import units as u
import json
import numpy as np
from pandas import DataFrame as df

import glob

from vasco.util import read_inputfile, latest_file
from vasco.sources import check_band, identify_sources_fromtarget
from vasco import c

from casampi.MPICommandClient import MPICommandClient

msmd=msmetadata()
tb = table()

SNR_THRES = 7.0

def start_mpi():
    try:
        client = MPICommandClient()
        client.start_services()
        client.set_log_mode('redirect')
        # client.set_log_level('SEVERE') does not work
        # and neither does casalog.filter('SEVERE') :(
        client.set_log_level('INFO4')
    except RuntimeError:
        client = False
    return client

def select_long_scans(field_id, fields, scan_df):
    """
    sort the scan by number of rows and select the first five as list

    Example
    ---

    scannos                    =   select_long_scans(fid)
    scannos                    =   ",".join(scannos)        
    """
    
    npand                   =   scan_df.td[fields[field_id]['scans']]
    npand                   =   npand.sort_values(ascending=False)
    scans                   =   list(npand.index)
    return scans

def vals_fromtab(caltable):
    tb                      =   table()
    tb.open(caltable)
    snr                     =   tb.getcol('SNR').ravel()
    an1                     =   tb.getcol('ANTENNA1').ravel()
    an2                     =   tb.getcol('ANTENNA2').ravel()
    time                    =   tb.getcol('TIME').ravel()
    scan                    =   tb.getcol('SCAN_NUMBER').ravel()
    flag                    =   tb.getcol('FLAG').ravel()
    fid                     =   tb.getcol('FIELD_ID').ravel()
    # wt=tb.getcol('WEIGHT').ravel()
    tb.close()

    return snr,an1,an2,time,scan,fid,flag

def ants_intbls_unique(vis=None, msmd=None, tbls=None):
    
    tb = table()
    antid, msm                =   [], None
    
    for tbl in tbls:
        tb.open(tbl)
        tbl_antid             =   tb.getcol('ANTENNA1')
        if not len(antid):antid =   tbl_antid
        antid                 =   np.intersect1d(antid, tbl_antid)
    if not msmd: 
        msm = msmetadata()
        msm.open(vis)
    else:
        msm = msmd
    ants = msm.antennanames(np.unique(antid))
    if not msmd: msm.close()
    return ants, antid

def fringefit_for_refant_fields(vis, caltable, fields, refants, sources, spws, gaintable, scan_df, mpi):
    print("..doing FFT")
    tbl_names, status, err          =   [], True, ''
    
    msmd.open(vis)
    MPICLIENT = start_mpi()
    success = False
    ants_with_solution, anid        =   ants_intbls_unique(msmd=msmd, tbls=gaintable)
    refants                         =   np.intersect1d(ants_with_solution, refants)
    d_fields                        =   {}
    # print(refamts, )
    try:
        # print(refants, ants_with_solution, anid)
        for refant in refants:        
            for fid in fields:
                field_name  = fields[fid]['name']
                scans = select_long_scans(fid, fields, scan_df)
                
                nscans, usescans = 0, []
                for scan in scans:
                    antennasforscan = list(msmd.antennasforscan(int(scan)))
                    antid           = msmd.antennaids(refant)[0]
                    
                    if antid in antennasforscan:
                        nscans+=1
                        usescans.append(scan)
                    else:
                        print(f'scan {scan} not available in antenna {refant}')
                        scans.remove(scan)
                    if nscans>=5: break
                scannos                    =   ",".join(usescans)
                
                
                res, e      = [], ''
                ff_caltable = f"{str(Path(caltable).absolute() / Path(caltable).name)}_{refant}__{field_name}.t"
                gt = [str(Path(gaintabl).absolute()) for gaintabl in gaintable]
                try:
                    if sources and (not field_name in sources):
                        e = f"skipping {field_name} not selected"
                    elif not len(usescans)<1:
                        e = "not enough scans"                    
                        
                        if not mpi:
                            fringefit(
                                vis=vis,
                                caltable=f"{ff_caltable}", 
                                field=f'{fid}', 
                                selectdata=True,
                                scan=scannos,
                                solint='inf', zerorates=True,
                                refant=refant, minsnr=3, 
                                gaintable=gt,
                                interp=['nearest', 'nearest', 'nearest,nearest'],
                                globalsolve=False, 
                                docallib=False, 
                                parang=False,
                            )
                            success = True
                        else:
                            # print(refants, ants_with_solution, anid)
                            # print(fid, refant, scannos)
                            if MPICLIENT:
                                ms_name_fp      = vis#_inp_params.workdir + _inp_params.ms_name
                                caltable_fp     = ff_caltable#_inp_params.workdir + caltable
                                gaintable_fp    = gt#[_inp_params.workdir + gt for gt in gaintable]
                                
                                spw             =   spws #','.join([str(spw) for spw in spws])
                                corrcomb        =   'none'
                                combine         =   ''
                                # interp          =   'nearest'
                                gainfield = []
                                fringefit_cmd = ("""fringefit(vis='{0}',""".format(ms_name_fp)
                                                + """caltable='{0}',""".format(caltable_fp)
                                                + """field='{0}',""".format(str(fid))
                                                + """spw='{0}',""".format(spw)
                                                + """selectdata={0},""".format('True')
                                                + """timerange='{0}',""".format('')
                                                + """antenna='{0}',""".format(str(",".join(ants_with_solution)))
                                                + """scan='{0}',""".format(str(scannos))
                                                + """observation='{0}',""".format('')
                                                + """msselect='{0}',""".format('')
                                                + """solint='inf',"""
                                                + """combine='{0}',""".format(str(combine))
                                                + """refant='{0}',""".format(str(refant))
                                                + """minsnr={0},""".format(str(3))
                                                + """zerorates={0},""".format('False')
                                                + """globalsolve={0},""".format('False')
                        #                         + """weightfactor={0},""".format(str(weightfactor))
                                                # + """delaywindow={0},""".format(str(list(delaywindow)))
                                                # + """ratewindow={0},""".format(str(list(ratewindow)))
                                                # + """niter={0},""".format(str(_inp_params.fringe_maxiter_lsquares))
                                                # + """append={0},""".format(str(append))
                                                + """docallib={0},""".format('False')
                                                + """callib='{0}',""".format('')
                                                + """gaintable={0},""".format(str(gaintable_fp))
                                                + """gainfield={0},""".format(str(gainfield))
                                                # + """interp='{0}',""".format(str(interp))
                                                # + """spwmap={0},""".format(str(spwmap))
                                                + """corrdepflags={0},""".format('False')
                                                # + """paramactive={0},""".format(str(list(paramactive)))
                                                + """concatspws={0},""".format('True')
                                                + """corrcomb='{0}',""".format(str(corrcomb))
                                                + """parang={0}""".format('True')
                                                + """)"""
                                                )
                                # print(fringefit_cmd)
                                res = MPICLIENT.push_command_request(fringefit_cmd, block=False)
                                print(f'processing {refant} with scans {str(scannos)}')
                                # res_list.extend(res)
                                # success = res[0]['successful']
                                # print(res)
                                # e = res[0]['']
                    else:
                         success = False
                         
                except Exception as e:
                    success = False
                finally:
                    d_fields[f"{fid}___{refant}"] =  {'scannos': scannos, 'mpi_ids': res, 'e':e, 'tbl_names': ff_caltable}
                    
                        
    except Exception as e:
        status, err =False, e
    finally:
        msmd.done()
        if not status: raise SystemExit(f"{c['r']}Failed! {c['y']}{str(err)}{c['x']}")
    # ret = 
    # # print(ret)
    for k,v in d_fields.items():
        success = False
        if len(v['mpi_ids']): 
            res         =   MPICLIENT.get_command_response(v['mpi_ids'], block=True)
            success     =   res[0]['successful']
            if not success:
                # print('Errfinding traceback')
                e           =   res[0]['traceback']
        else:
            success     =   False
            e           =   v['e']

        fid, refant     =   k.split('___')
        field_name      =   fields[fid]['name']
        scannos         =   v['scannos']
        if not success:
            print(f'{c["r"]}processing failed{c["x"]}', scannos,'for field', field_name, 'with refant', refant, f"\nreason : {e}\n")
        else: 
            if Path(v['tbl_names']).exists(): 
                print(f'{c["g"]}processed{c["x"]}', scannos,'for field', field_name, 'with refant', refant)
                tbl_names.append(v['tbl_names'])
            else:
                err_flag = f"Successful fringefit execution but table not found"
                d_fields[f"{fid}___{refant}"]['err_flag'] = err_flag
                print(f'{c["r"]}processing failed{c["x"]}', scannos,'for field', field_name, 'with refant', refant, f"\nreason : {err_flag}\n")
                
    tbl_metafile = f"{str(Path(caltable).absolute() / Path(caltable).name)}.vasco"
    save_metafile(metafile=tbl_metafile, metad=d_fields)
    return tbl_names

def generic_df_fromtab(tbl, colnames=[]):  

    tbl_tuple = []
    tb=table()
    tb.open(tbl)
    for colname in tb.colnames():
        try:
            tbl_d = tb.getcol(str(colname))
            tbl_tuple.append(tbl_d)
            colnames.append(colname)
        except:
            pass
    tb.close()
    tbl_data   =  list(zip(*tbl_tuple))
    df_tbl_data=df(columns=colnames, data=tbl_data)

    return df_tbl_data

def df_fromtables(tbl_names):
    df_tb          =  None
    snr_0,an1_0,an2_0,time_0,scan_0,fid_0,flag_0= ([] for i in range(7))
    for i,tbl_name in enumerate(tbl_names):
        if i==0:
            snr_0,an1_0,an2_0,time_0,scan_0,fid_0,flag_0  =   vals_fromtab(str(tbl_name))

            tbl_data    =   list(zip(*(time_0, an1_0,an2_0,scan_0,fid_0,flag_0, snr_0))) 
            df_tb       =   df(tbl_data, 
                                columns  =  ["TIME", "ANTENNA1","ANTENNA2","SCAN","FIELD_ID","FLAG","SNR"])
        else:
            snr_1,an1_1,an2_1,time_1,scan_1,fid_1,flag_1 =   vals_fromtab(str(tbl_name))
            tbl_data    =   list(zip(*(time_1, an1_1,an2_1,scan_1,fid_1,flag_1, snr_1))) 

            new_df = df(tbl_data, 
                     columns  =  ["TIME", "ANTENNA1","ANTENNA2","SCAN","FIELD_ID","FLAG","SNR"])
# #             df_tb.append(new_df)
            df_tb  = pdconc([df_tb, new_df])
        
    
    df_tb  =  df_tb.sort_values(by=["SNR"], ascending=[False])
    # df_tb  =  df_tb[df_tb['ANTENNA1']!=df_tb['ANTENNA2']]
    # print(df_tb)
    return df_tb

def df_fromtb(tbls):
    """
    returns dataframes containing:
    "ANTENNA2", "SNR_median", "FIELD_ID", "SNR_FIELD"
    
    CASA uses "ANTENNA2" as the reference antenna used for the table.
    """
    tbd = df_fromtables(tbls)
    i,j=0,0
    df_o = tbd.loc[tbd['ANTENNA1']!=tbd['ANTENNA2']]
    df_o_flagged = df_o.loc[df_o['FLAG']==False]
    
    for fid in tbd['FIELD_ID'].unique():
        tbd_source = df_o_flagged.loc[df_o_flagged['FIELD_ID']==fid]
        for refant in tbd_source['ANTENNA2'].unique():
            refant_snr = tbd_source.loc[tbd_source['ANTENNA2']==refant]['SNR']
            refant_snr_max = refant_snr.max()
            # if refant_snr_max>SNR_THRES:
            #     refant_snr  = refant_snr.loc[refant_snr>SNR_THRES]

                # refant      =   refant[[refant_snr.index]]
                # fid         =   fid[[refant_snr.index]]
                # tbd_source  =   tbd_source[[refant_snr.index]]
            tb_data=[[refant, refant_snr.median(), refant_snr.mean(),refant_snr_max, fid, tbd_source.SNR.median()]]      # median value for all scans
            if i==0:
                df_field_ant = df(tb_data,
                                 columns=["ANTENNA2", "SNR_median", "SNR_mean", "SNR_max", "FIELD_ID", "SNR_FIELD"])
                i=1
            else:
                new_df       = df(tb_data,
                                 columns=["ANTENNA2", "SNR_median", "SNR_mean", "SNR_max", "FIELD_ID", "SNR_FIELD"])
                df_field_ant = pdconc([df_field_ant, new_df], ignore_index=True)
    
    return df_field_ant

def flagsummary(vis, **kwargs):
      d=  flagdata(vis, mode='summary', 
                #  name=self.name, 
                 fieldcnt=True, basecnt=True, **kwargs, )
      return d

def save_metafile(metafile, metad):
    with open(str(metafile), 'w') as mf: json.dump(metad, mf)

def read_metafile(metafile):
    with open(metafile, 'r') as sf:
        metad                       =   sf.read()
        meta                        =   json.loads(metad)
    return meta

def splitms_mpi(vis, outvis, fids):

    MPICLIENT = start_mpi()
    mstransform_cmd =   (f"mstransform(vis='{str(vis)}', outputvis='{str(outvis)}', datacolumn='data', field='{fids}', createmms=True)")
    
    res         = MPICLIENT.push_command_request(mstransform_cmd, block=True)

    return res

def listobs_mpi(vis, overwrite, listfile, verbose):
    MPICLIENT = start_mpi()
    listobs_cmd = (f"listobs(vis='{vis}', overwrite={overwrite}, listfile='{listfile}',verbose={verbose})")
    res = MPICLIENT.push_command_request(listobs_cmd, block=True)
    return res[0]['ret']

def load_metadata(vis, metafile, refants=None, spws=None, sources=None, determine=False, mpi=False):
    if (not Path(metafile).exists()) or determine:
        if not sources: sources = []
        
        if not mpi:
            meta=listobs(vis=vis, overwrite=True, listfile=f'{str(Path(metafile).parent / "listobs.txt")}',verbose=False)
        else:
            
            meta=listobs_mpi(vis, overwrite=True, listfile=f'{str(Path(metafile).parent / "listobs.txt")}',verbose=False)
            
        print("loaded listobs..")
        fields = {}
        for k,v in meta.items():
            if ('field_' in k):
                if sources and v['name'] in sources:
                    fields[k.replace('field_', '')]      =    {'name':v['name']}
                elif not sources:
                    fields[k.replace('field_', '')]      =    {'name':v['name']}

        # fields                          =   {k.replace('field_', ''):{'name':v['name']} for k,v in meta.items() if ('field_' in k)}
        scans                           =   {k.replace('scan_', ''):{'t0':v['0']['BeginTime'],'t1':v['0']['EndTime']} for k,v in meta.items() if 'scan_' in k}
        for fk in fields:
            fields[str(fk)]['scans']    =   [k.replace('scan_', '') for k,v in meta.items() if ('scan_' in k) and (v['0']['FieldId']==int(fk))]
        # fs                 =   flagsummary(vis)
        meta={'fields': fields, 'scans': scans,}        
        if spws: meta['spws'] = spws
        save_metafile(metafile, meta)
    else:
        with open(metafile, 'r') as sf:
            metad                       =   sf.read()
            meta                        =   json.loads(metad)
    if refants: meta['refants'] =   refants
    if sources: meta['sources'] =   sources
    if spws:    meta['spws'] = spws
    return meta

    
def ff_to_tbl_names(vis, meta, metafile, refants=None, sources=None, spws=None, gaintable=None, new_tbls=False, mpi=False):
    """
    
    """
    #   prepare and load
    hms                         =   datetime.now().strftime("%m%d_%H%M%S")
    wd                          =   Path(vis).parent
    fft_tb                      =   f"{wd}/fft_tab/{Path(vis).stem}_{hms}_ff"
    
    # if not metafile : metafile = str(wd / 'meta_shortfft.vasco')
    # meta = load_metadata(vis, metafile=metafile, refants=refants, sources=sources, determine=new_meta)
    
    scans                       =   meta['scans']
    fields                      =   meta['fields']
    refants                     =   meta['refants']
    sp                          =   df.from_dict(scans, orient='index')
    td                          =   Time(sp.t1, format='mjd')-Time(sp.t0, format='mjd')
    sp['td']                    =   TimeDelta(td, format='jd').sec
    
    if not gaintable: gaintable =   [f'{wd}/calibration_tables/accor.t',f'{wd}/calibration_tables/gc.t',f'{wd}/calibration_tables/tsys.t']
    
    #   fringefit for each refant for each source
    
    if not new_tbls:
        tbl_names               =   glob.glob(f"{str(Path(meta['fft_tb']))}*.t")
        if len(tbl_names) < 1: 
            meta['fft_tb'] = None
            raise SystemExit(f"{c['r']} Failed! couldn't find tables{c['x']}")
    else:
        Path(fft_tb).mkdir(exist_ok=True, parents=True)
        tbl_names               =   fringefit_for_refant_fields(vis, fft_tb, fields, refants, sources, spws, gaintable, sp, mpi)
        meta['fft_tb'] = fft_tb
    save_metafile(metafile, meta)
    return tbl_names

def find_refant_fromtbls(vis, tbls, fields,verbose=False):
    """
    finds refants from Short Fringe Fit tables
    """
    df_field_ant = df_fromtb(tbls)
    n_ant                                   =   4
    print_tbls                              =   """ """
    msmd.open(vis)
    # TODO: remove antenna without any scans
    ants = msmd.antennanames()
    antsid = msmd.antennaids(name=ants)
    ants_dict = dict(zip(antsid, ants))
    
    msmd.done()
    
    fields_dict = {}
    
    for fid in fields.keys():
        fields_dict[int(fid)] = fields[fid]['name']
    
    df_field_ant.loc[:,'ANNAME']            =   df_field_ant['ANTENNA2'].map(ants_dict)
    df_field_ant_sorted                     =   df_field_ant.sort_values(by=["SNR_median"], ascending = False)
    
    
    df_field_ant                            =   df_field_ant.loc[df_field_ant['SNR_median']>SNR_THRES]
    
    ant_sorted                              =   df_field_ant.groupby('ANNAME').median().sort_values(by=['SNR_median'], ascending=False)
    
    df_field_ant_sorted['FIELD_NAME']       =   df_field_ant_sorted['FIELD_ID'].map(fields_dict)
    ant_sorted                              =   ant_sorted.drop(columns=['FIELD_ID', 'SNR_FIELD'])

    ant_sorted.rename(columns={'SNR_median':'SNR_median', 'ANTENNA2':'ID'}, inplace=True)
    ant_sorted['ID']=ant_sorted['ID'].astype('Int64')
    refants_final = list(ant_sorted.index.values[:n_ant])        

    ant_selected = df_field_ant_sorted.loc[df_field_ant_sorted['ANNAME'].isin(ant_sorted.index[:1])]
    ant_selected = ant_selected[['ANNAME', 'SNR_median', 'FIELD_ID', 'FIELD_NAME' , 'SNR_FIELD']].sort_values(by=['SNR_FIELD'], ascending=False)
    ant_selected= ant_selected.set_index('FIELD_ID')

    print_tbls += df_field_ant_sorted.to_string()   + "\n"
    print_tbls += ant_sorted.to_string()            + "\n"
    print_tbls += ant_selected.to_string()

    snr_thres_for_calib = SNR_THRES
    ant_to_calib = ant_selected[['FIELD_NAME', 'SNR_FIELD']]
    calibs = ant_to_calib[ant_to_calib['SNR_FIELD']>snr_thres_for_calib].to_dict('list')
    if verbose: print(print_tbls)
    return refants_final, calibs, print_tbls

def params_check(vis, sources, refants, spws, ff_tbls, new_meta, new_tbls, mpi):
    """
    - sanitizes arguments
    - loads metadata
    """
    wd = Path(vis).parent
    wd_ifolder = str(wd.absolute() / 'input_template/')
    caltab = str(wd / 'calibration_tables/')
    
    if not refants or not refants[0]:
        msmd.open(vis)
        refants         =   msmd.antennanames()
        msmd.done()
    meta = None
    for folder in [wd_ifolder, caltab]:
        if not Path(folder).exists():
            raise FileNotFoundError(f"Expected '''{folder}''' not found") 
    d, _,_ = read_inputfile(wd_ifolder, 'array.inp')

    metafile = str(wd / 'vasco.meta' / 'msmeta_snrrating.vasco')
    Path(metafile).parent.mkdir(exist_ok=True, parents=True)
    if (not new_meta) and (not Path(metafile).exists()):
        new_meta = True
    print("loading metadata..")
    meta = load_metadata(vis, metafile=metafile, refants=refants, spws=spws, sources=sources, determine=new_meta, mpi=mpi)
    print("loading metadata done..")
    if (not ff_tbls) and (not new_tbls):
        lastf           =   latest_file(Path('fft_tab/'),'*_ff/*.t').parent
        if meta and ('fft_tb' in meta) and meta['fft_tb']:
            ff_tbls     =   glob.glob(f"{meta['fft_tb'].replace('./','')}/*.t")
        elif not ff_tbls and len(str(lastf))>5:
            ff_tbls     =   lastf.glob('*.t')
        else:
            new_tbls    =   True
            ff_tbls     =   None    
    print("params check done..")
    return refants, ff_tbls, new_meta, new_tbls, meta, metafile

def identify_refant_casa(vis, sources=None, refants=None, spws=None, ff_tbls=None, new_meta=False, new_tbls=False, mpi=False, verbose=True):
    """
    Returns
    refant_list, calib_dictionary
    
    :refant_list:       [refants]
    :calib_dictionary:  {'FIELD_NAME': [sources], {'SNR_FIELD':[snr_sources]}}
                        snr_sources: median values of all scans, antennas in the field
    """
    if not sources:
        sources=None
    print("..short FFT for refant and calibrator sources")
    refants, ff_tbls, new_meta, new_tbls, meta, metafile = params_check(vis=vis, sources=sources, refants=refants, spws=spws, ff_tbls=ff_tbls, new_meta=new_meta, new_tbls=new_tbls, mpi=mpi)
    # print(new_tbls, "new_tbls")
    if not ff_tbls: 
        print("finding tables..")
        try:
            ff_tbls = ff_to_tbl_names(vis, meta, metafile, refants=refants, sources=sources, spws=spws, new_tbls=new_tbls, mpi=mpi)
        except Exception as e:
            print("Exception occured!!!","\n\n",str(e))
    print("tables collected..")
    # print(meta['fields'])
    # print(ff_tbls)
    return find_refant_fromtbls(vis, ff_tbls, fields=meta['fields'], verbose=verbose)


# ---------------------- helper functions for Identifying sources using .MS for finding calibrators and phaserefence pair (check vasco.sources)

def get_scanlist_seq(msmd):
    scans = msmd.scannumbers()

    scanlist_seq = [int(msmd.fieldsforscan(scan)[0]) for scan in scans]
    return scanlist_seq

def get_sourcenames(msmd):

    warn_msg = ""
    sourcenames = {}
    for sid in msmd.fieldsforsource():
        if len(msmd.spwsforfield(sid)):
            sourcenames[sid]=msmd.namesforfields(sid)[0]
        else:
            warn_msg = f"{c['y']}{msmd.namesforfields(sid)[0]} has {len(msmd.spwsforfield(sid))} spws present{c['x']}"
            sourcenames[sid]=msmd.namesforfields(sid)[0]
    if warn_msg: print(warn_msg)
    return sourcenames

def coordinate_for_sources(vis, sourcenames):
    """
    Input
    
    :vis:       (str)   ms filepath

    Returns 
    
                (dictionary)
    
    key         :   value
    SOURCE_NAME : (ra,dec) 
                    scalar tuple in radians
    """
    c = {}
    tb.open(f"{vis}/FIELD")
    ra,dec = tb.getcol('REFERENCE_DIR')
    for i,s in enumerate(tb.getcol('NAME')):
        if s in sourcenames.values():
            c[s]=(ra[0][i], dec[0][i])
    tb.done()
    return c

def check_bands_ms(msmd):
    """
    Returns
    ---
    
    (dict)
    key      
    {
    'BAND': 
        {'reffreqs': [reffreqs], 'spws':[spws]}
    }
    
    'BAND'   = (str) "C", "X", "S"
    reffreqs = (list)   (float) (Hz)
    spws     = (list)   (int)
    
    """
    spws = set()
    spwsforfields = msmd.spwsforfields()
    for spws_inf in spwsforfields.values():
        spws.update(spws_inf)

    d= {}
    for spw in spws:

        reffreq = msmd.reffreq(spw)['m0']['value']
        band    = str(check_band(reffreq/1.0E+09))
        if band not in d.keys():
            d[band] = {}
        if 'spws' not in d[band].keys():
            d[band]['spws'] = [int(spw)]
            d[band]['reffreqs'] = [reffreq]
        else:
            d[band]['spws'].extend([int(spw)])
            d[band]['reffreqs'].extend([reffreq])
    return d

def get_target_in_bands(msmd, target, bands_dict):
    spws = msmd.spwsforfield(target)
    bands = []
    for band in bands_dict:
        if all(spw_band in list(spws) for spw_band in list(bands_dict[band]['spws'])):
            bands.extend([band])
        else:
            print(f"{target} is not in {band} band", spws)
    return bands

def coordinate_for_target(vis, target, sourcenames):
    """

    Returns
    ---

    (tuple)

    other_names, c_other, c_target

    :other_names:       (list) list of other source names
    :c_other:           (tuple) (astropy.units.radian, astropy.units.radian)
    :c_target:           (tuple) (astropy.units.radian, astropy.units.radian)
    """
    s = {}
    c = coordinate_for_sources(vis, sourcenames)
    # idx_target = list(c.keys()).index(target)
    sv = c.pop(target, None)
    sv = SkyCoord(sv[0]*u.rad,sv[1]*u.rad)
    
    r, d = list(zip(*c.values()))
    oth = SkyCoord(r*u.rad,d*u.rad)
    
    return oth, list(c.keys()), sv

def identify_sources_fromtarget_ms(vis, target_source, caliblist_file=None, msmd=msmd, flux_thres=0.150, min_flux=0.025, ncalib=9, flux_df=None, sourcenames=None, hard_selection=False):
    
    
    metafile                                =   Path(vis).parent / 'vasco.meta' / 'msmeta_sources.vasco'
    msmd.open(vis)

    if not sourcenames : sourcenames        =   get_sourcenames(msmd)
    c_others ,other_sources, c_target       =   coordinate_for_target(vis, target=target_source, sourcenames=sourcenames)
    scanlist_seq                            =   get_scanlist_seq(msmd)
    bands_dict                              =   check_bands_ms(msmd)
    target_in_bands                         =   get_target_in_bands(msmd, target_source, bands_dict)
    # bands                                   =   list(bands_dict.keys())
    msmd.done()

    meta = {
        # 'sourcenames': sourcenames, 
            'c_others': c_others.to_string('hmsdms'), 
            'other_sources':other_sources, 
            'c_target': c_target.to_string('hmsdms'),
            'scanlist_seq':scanlist_seq, 
            'bands_dict': bands_dict
            }

    s_dict                                  =   {}
    for band in target_in_bands:
        s                                   =   identify_sources_fromtarget(scanlist_seq, sourcenames, target_source, other_sources, c_target, c_others, 
                                                    band=band, flux_thres=flux_thres, min_flux=min_flux, ncalib=ncalib, caliblist_file=caliblist_file, verbose=True, flux_df=flux_df, hard_selection=hard_selection)
        s_dict[band]                        =   s
    
    meta['s_dict']                          =   s_dict
    save_metafile(metafile, meta)
    return s_dict

def identify_sources_fromsnr_ms(vis, target_source, caliblist_file=None, snr_metafile=None, outfile='',
                                flux_thres=18.0, min_flux=8.0,ncalib=9,  msmd=msmd):

    if not snr_metafile: snr_metafile       =   Path(vis).parent / 'vasco.meta' / 'sources.vasco'
    mf_dic                                  =   read_metafile(snr_metafile)

    msmd.open(vis)
    sourcenames                             =   get_sourcenames(msmd)

    s_df                                    =   df(data=sourcenames.values(), index=sourcenames.keys(), columns=['source_name'])
    mf_df                                   =   df.from_dict(mf_dic)
    mf_df                                   =   mf_df.rename(columns={'FIELD_NAME':'source_name', 'SNR_FIELD':'flux'})

    mf_df                                   =   s_df.merge(mf_df, on='source_name', how='left')
    flux_df                                 =   df(mf_df['flux'])
    
    sd = identify_sources_fromtarget_ms(vis, target_source, caliblist_file=caliblist_file, 
                                msmd=msmd,
                                flux_thres=flux_thres, min_flux=min_flux,ncalib=ncalib, flux_df=flux_df, sourcenames=sourcenames, 
                                hard_selection=True)
    if not outfile: outfile = str(Path(vis).parent / 'vasco.meta' / 'sources_ms_snr.vasco')
    save_metafile(outfile, sd)
    return sd


# ----------------------------------------------------------------

def split_ms(vis, outvis, source_list=[], fids=[], mpi=False):
    
    if not fids:
        fids=[]
        if not source_list: raise TypeError(f"source_list is required")
        try:
            msmd.open(vis)
            for f in source_list:
                fid = msmd.fieldsforname(str(f))[0]
                fids.append(str(fid))
        except Exception as e:
            # closed = msmd.done()
            print(str(e))
        finally:
            msmd.done()
    
    fids=','.join(fids)

    if mpi:
        ret = splitms_mpi(vis, outvis, fids)
    else:
        ret =   mstransform(vis=f'{vis}', outputvis=f'{outvis}', datacolumn='data', field=f'{fids}', createmms=True)
    # res         = MPICLIENT.push_command_request(mstransform_cmd, block=True)
    return ret