import numpy as np
from itertools import zip_longest
import glob, json

from datetime import datetime
from astropy.time import Time, TimeDelta
# from pandas import DataFrame as df, concat as pdconc
from scipy.spatial import distance

# from pathlib import Path

# from vasco import c
from vasco.util import save_metafile, latest_file


# from casatools import msmetadata, table
from casatasks import listobs



from casatools import table
from pathlib import Path
# tb = table()
# import dask.dataframe as dd
# from dask import compute as d_compute, persist as d_persist
from pandas import DataFrame as df, concat as pdconc
# import dask.array as da
from astropy.time import Time
import numpy as np
from scipy.spatial import distance

from pandas import IndexSlice as islice
from vasco import c
from itertools import zip_longest
import shutil
from datetime import datetime
import glob
from vasco.util import save_metafile
from collections import Counter
import traceback



MPICLIENT = ''

# msmd=msmetadata()
tb = table()

SNR_THRES = 7.0


def listobs_mpi(vis, overwrite, listfile, verbose):
    MPICLIENT = start_mpi()
    listobs_cmd = (f"listobs(vis='{vis}', overwrite={overwrite}, listfile='{listfile}',verbose={verbose})")
    res = MPICLIENT.push_command_request(listobs_cmd, block=True)
    return res[0]['ret']

# def load_metadata(vis, metafile, refants=None, spws=None, sources=None, determine=False, mpi=False):
#     """_summary_
    
#     TODO: use msmd or ms casatools

#     Args:
#         vis (_str_): _name of the visibility file_
#         metafile (_str_): _path of the metafile_
#         refants (_list_, optional): _list of Antenna names for refants_. Defaults to None.
#         spws (_list_, optional): _spectral window ids_. Defaults to None.
#         sources (_list_, optional): _field names_. Defaults to None.
#         determine (bool, optional): _whether to determine the metadata or load the older one if found_. Defaults to False.
#         mpi (bool, optional): _use of MPI_. Defaults to False.

#     Returns:
#         _dict_: _dictionary of metadata_
#     """
#     if (not Path(metafile).exists()) or determine:
#         if not sources is None: sources = []
        
#         if not mpi:
#             meta=listobs(vis=vis, overwrite=True, listfile=f'{str(Path(metafile).parent / "listobs.txt")}',verbose=False)
#         else:
            
#             meta=listobs_mpi(vis, overwrite=True, listfile=f'{str(Path(metafile).parent / "listobs.txt")}',verbose=False)
            
#         print("loaded listobs..")
#         fields = {}
#         for k,v in meta.items():
#             if ('field_' in k):
#                 if sources and v['name'] in sources:
#                     fields[k.replace('field_', '')]      =    {'name':v['name']}
#                 elif not sources is None:
#                     fields[k.replace('field_', '')]      =    {'name':v['name']}

#         # fields                          =   {k.replace('field_', ''):{'name':v['name']} for k,v in meta.items() if ('field_' in k)}
#         scans                           =   {k.replace('scan_', ''):{'t0':v['0']['BeginTime'],'t1':v['0']['EndTime']} for k,v in meta.items() if 'scan_' in k}
#         for fk in fields:
#             fields[str(fk)]['scans']    =   [k.replace('scan_', '') for k,v in meta.items() if ('scan_' in k) and (v['0']['FieldId']==int(fk))]
#         # fs                 =   flagsummary(vis)
#         meta={'fields': fields, 'scans': scans,}        
#         if spws: meta['spws'] = spws
#         save_metafile(metafile, meta)
#     else:
#         with open(metafile, 'r') as sf:
#             metad                       =   sf.read()
#             meta                        =   json.loads(metad)
#     if refants: meta['refants'] =   refants
#     if sources: meta['sources'] =   sources
#     if spws:    meta['spws'] = spws
#     return meta


# def params_check(vis, sources, refants, spws, ff_tbls, new_meta, new_tbls, mpi):
#     """
#     TODO: check refants

#     - sanitizes arguments
#     - loads metadata
#     """
#     wd = Path(vis).parent
#     meta = None
    
#     metafile = str(wd / 'vasco.meta' / 'msmeta_snrrating.vasco')
#     Path(metafile).parent.mkdir(exist_ok=True, parents=True)
#     if (not new_meta) and (not Path(metafile).exists()):
#         new_meta = True
#     print("loading metadata..")
#     meta = load_metadata(vis, metafile=metafile, refants=refants, spws=spws, sources=sources, determine=new_meta, mpi=mpi)
#     print("loading metadata done..")
#     if (not ff_tbls) and (not new_tbls):
#         lastf           =   latest_file(Path('fft_tab/'),'*_ff/*.t').parent
#         if meta and ('fft_tb' in meta) and meta['fft_tb']:
#             ff_tbls     =   glob.glob(f"{meta['fft_tb'].replace('./','')}/*.t")
#         elif not ff_tbls and len(str(lastf))>5:
#             ff_tbls     =   lastf.glob('*.t')
#         else:
#             new_tbls    =   True
#             ff_tbls     =   None    
#     print("params check done..")
#     return refants, ff_tbls, new_meta, new_tbls, meta, metafile

# def get_tb_data(vis, axs=[]):
#     tb.open(vis)
#     res = []
#     if len(axs):
#         for ax in axs:
#             res.append(tb.getcol(ax))
#     tb.close()
#     return res


# def vals_fromtab(caltable):
#     tb                      =   table()
#     tb.open(caltable)
#     snr                     =   tb.getcol('SNR').ravel()
#     an1                     =   tb.getcol('ANTENNA1').ravel()
#     an2                     =   tb.getcol('ANTENNA2').ravel()
#     time                    =   tb.getcol('TIME').ravel()
#     scan                    =   tb.getcol('SCAN_NUMBER').ravel()
#     flag                    =   tb.getcol('FLAG').ravel()
#     fid                     =   tb.getcol('FIELD_ID').ravel()
#     # wt=tb.getcol('WEIGHT').ravel()
#     tb.close()

#     return snr,an1,an2,time,scan,fid,flag

# def df_fromtables(tbl_names):
#     df_tb          =  None
#     snr_0,an1_0,an2_0,time_0,scan_0,fid_0,flag_0= ([] for i in range(7))
#     for i,tbl_name in enumerate(tbl_names):
#         if i==0:
#             snr_0,an1_0,an2_0,time_0,scan_0,fid_0,flag_0  =   vals_fromtab(str(tbl_name))

#             tbl_data    =   list(zip(*(time_0, an1_0,an2_0,scan_0,fid_0,flag_0, snr_0))) 
#             df_tb       =   df(tbl_data, 
#                                 columns  =  ["TIME", "ANTENNA1","ANTENNA2","SCAN","FIELD_ID","FLAG","SNR"])
#         else:
#             snr_1,an1_1,an2_1,time_1,scan_1,fid_1,flag_1 =   vals_fromtab(str(tbl_name))
#             tbl_data    =   list(zip(*(time_1, an1_1,an2_1,scan_1,fid_1,flag_1, snr_1))) 

#             new_df = df(tbl_data, 
#                      columns  =  ["TIME", "ANTENNA1","ANTENNA2","SCAN","FIELD_ID","FLAG","SNR"])
# # #             df_tb.append(new_df)
#             df_tb  = pdconc([df_tb, new_df])
        
    
#     df_tb  =  df_tb.sort_values(by=["SNR"], ascending=[False])
#     # df_tb  =  df_tb[df_tb['ANTENNA1']!=df_tb['ANTENNA2']]
#     # print(df_tb)
#     return df_tb

# def df_fromtb(vis, tbls, msmd):
#     """
#     TODO: following is outdated.
#     returns dataframes containing:
#     "ANTENNA2", "SNR_median", "FIELD_ID", "SNR_FIELD"

#     CASA uses "ANTENNA2" as the reference antenna used for the table.
#     """
#     tb_ant = table()
#     tb_tsys = table()
#     tb_ant.open(f'{vis}/ANTENNA')
#     tb_tsys.open(f"{vis}/SYSCAL")
    
#     an_dict = {}
    
#     xyz = list(zip(*tb_ant.getcol('POSITION')))
#     an = tb_ant.getcol('NAME')
#     tsys_anid = tb_tsys.getcol('ANTENNA_ID')
#     tsys_vals = tb_tsys.getcol('TSYS')
    
#     for i,an in enumerate(an):
#         i_anid = msmd.antennaids(an)[0]
        
#         # calculating TSYS variability
#         tsys_std = []
#         for tsys_val in tsys_vals:
#             itsys = np.where(tsys_anid==i_anid)
#             tsy_an_std = np.nanstd(tsys_val[itsys]) if len(itsys) else np.float('nan')
#             tsys_std.append(tsy_an_std)
        
#         an_dict[msmd.antennaids(an)[0]]={'ANNAME': an}
#         an_dict[i_anid]['STD_TSYS']= np.nanmean(tsys_std)
        
#         # measuring centroid distance
#         d=[]
#         refcoord=xyz[i]
#         for v in xyz:
#             d.append(distance.euclidean(refcoord,v)*.001)                                       # Distance of all from one refant
#         an_dict[i_anid]['d']=np.nanmedian(d)   # Median distance of all ants for one refant
    
#     tbd = df_fromtables(tbls)
#     tb_ant.done()
    
    
#     i,j=0,0
#     df_o = tbd.loc[tbd['ANTENNA1']!=tbd['ANTENNA2']]
#     df_o_unflagged = df_o.loc[df_o['FLAG']==False]

#     for fid in tbd['FIELD_ID'].unique():
#         tbd_source = df_o_unflagged.loc[df_o_unflagged['FIELD_ID']==fid]
#         for refant in tbd_source['ANTENNA2'].unique():
#             refant_snr = tbd_source.loc[tbd_source['ANTENNA2']==refant]['SNR']
#             refant_snr_max = refant_snr.max()
#             dist = an_dict[refant]['d']
#             anname = an_dict[refant]['ANNAME']
#             std_tsys = an_dict[refant]['STD_TSYS']
#             tb_data=[[refant, anname, refant_snr.median(), refant_snr.mean(),refant_snr_max, fid, tbd_source.SNR.median(),dist, std_tsys]]      # median value for all scans
#             if i==0:
#                 df_field_ant = df(tb_data,
#                                  columns=["ANTENNA2", "ANNAME", "SNR_median", "SNR_mean", "SNR_max", "FIELD_ID", "SNR_FIELD", "d", "STD_TSYS"])
#                 i=1
#             else:
#                 new_df       = df(tb_data,
#                                  columns=["ANTENNA2", "ANNAME", "SNR_median", "SNR_mean", "SNR_max", "FIELD_ID", "SNR_FIELD", "d", "STD_TSYS"])
#                 df_field_ant = pdconc([df_field_ant, new_df], ignore_index=True)
#     tb_ant.done()
#     return df_field_ant


def start_mpi():
    # try:
    from casampi.MPICommandClient import MPICommandClient
    client = MPICommandClient()
    client.start_services()
    client.set_log_mode('redirect')
    # client.set_log_level('SEVERE') does not work
    # and neither does casalog.filter('SEVERE') :(
    client.set_log_level('INFO4')
    # except RuntimeError:
        # traceback.print_exc
        # client = False
    return client

# def meta_fid(dic, val):
#     return next((k for k, v in dic.items() if dic[k]['name'] == val), None)

# def get_scan_for_ants(df_vis, required_ants, scan_list):
#     dic_scan_ans = {}    
#     for scan_id in scan_list:
#         idx_scan = df_vis['sid']==scan_id
        
#         ans_scan = set(df_vis.loc[idx_scan]['an1'].values)
#         ans_scan.update(df_vis.loc[idx_scan]['an2'].values)
        
#         required_an_found = ans_scan.intersection(required_ants)
#         if required_an_found:
#             dic_scan_ans[scan_id] = set(required_an_found)
#     return dic_scan_ans

# def get_ans_with_scans(df_vis, scan_list, required_ants=[]):
# #     dic_scans_with_ans = {}    
#     dic_ans_with_scans = {}
#     if required_ants is None: required_ants=[]
#     for scan_id in scan_list:
#         idx_scan = df_vis['sid']==scan_id
        
#         ans_scan = set(df_vis.loc[idx_scan]['an1'].values)
#         ans_scan.update(df_vis.loc[idx_scan]['an2'].values)
        
#         required_an_found = ans_scan.intersection(required_ants) if len(required_ants) else ans_scan
#         if required_an_found:
# #             dic_scans_with_ans[scan_id] = set(required_an_found)
#             for an in required_an_found:
#                 if an in dic_ans_with_scans:
#                     dic_ans_with_scans[an].append(scan_id)
#                 else:
#                     dic_ans_with_scans[an] = [scan_id]
    
#     return dic_ans_with_scans

# def compute_time_diff(df):
#     df = df.sort_values('time')  # Sort inside partitions
#     t0 = Time(df['time'].iloc[0], format='decimalyear')
#     t1 = Time(df['time'].iloc[-1], format='decimalyear')
#     df['scan_td'] = (t1 - t0).to_value('sec')  # Assign column efficiently
#     return df


# def select_long_scans(field_id, scan_df, select_single_t=False):
#     """
#     sort the scan by number of rows and select the first five as array
#     requires fid, sid
#     Example
#     ---

#     scannos                    =   ",".join(scannos)        
#     """
    
#     long_scans                  =   None
    
    
#     scan_df = scan_df.groupby('sid').map_partitions(compute_time_diff)
#     idx_fid                     =   np.where(scan_df['fid']==field_id)

#     # scans                       =   scan_df[idx_fid]['sid'].unique().compute()
#     # for scan in scans:
#     #     idx_scan                =   np.where(scan_df['sid']==scan)
#     #     t                       =   scan_df[idx_scan]['time'].compute()
#     #     t.sort_values(ascending=True)
#     #     t0                      =   Time(t.values[0], format='decimalyear')
#     #     t1                      =   Time(t.values[-1], format='decimalyear')
#     #     mask = idx_fid & idx_scan
#         # scan_df = scan_df.map_partitions(
#         #     lambda df: df.assign(scan_td=np.where(mask.compute(), (t1 - t0).to_value('sec'), df['scan_td']))
#         # )
#         # scan_df.loc[idx_fid & idx_scan, 'scan_td'] = (t1-t0).to_value('sec')
#     long_scans = scan_df[idx_fid].sort_values(by=['scan_td'])['sid'].unique()[:5].compute()
#     return long_scans



# def task_short_fringefit(vis, df_vis, required_ants, scan_list, anname, spws, caltable, gaintable, iter_scan_count=1, mpiclient=MPICLIENT):
#     dic_result,e = {},''
        
#     gt = [str(Path(gaintabl).absolute()) for gaintabl in gaintable]
    
#     ans_with_scans = get_ans_with_scans(df_vis, scan_list=scan_list, required_ants=required_ants)
    
#     for refantid, scans in ans_with_scans.items():
#         refant = anname[refantid]
#         for sel_scan in list(zip_longest(*[iter(scans)] * iter_scan_count, fillvalue=None)):
#             ff_scans = [str(s) for s in sel_scan if s is not None]
#             ff_scans_joined = ",".join(ff_scans)            
#             ff_caltable = f"{str(Path(caltable).absolute() / Path(caltable).name)}_{refant}_{''.join(ff_scans)}.t"
#             try:                
#                 res = mpi_fringefit(vis, fid='', scannos=ff_scans_joined, refant=refant, 
#                                     ff_caltable=ff_caltable, gt=gt, spws=spws, mpiclient=mpiclient)
#             except Exception as e:
#                 print(f'{c["r"]}processing failed!{c["x"]} check parameters | refant:{refant} scans:{ff_scans_joined} \n{e}')
#             finally:
#                 dic_result[f"{refant}___{'_'.join(ff_scans)}"] =  {'scannos': ff_scans_joined, 'mpi_ids': res, 
#                                                     'e':e, 'tbl_names': ff_caltable}
#     return dic_result
    
# def fringefit_for_refant_scans(vis, df_vis, target, sources_dict, anname, caltable='', refants=[], selected_sources=[], spws='0', gaintable=[], mpi=True):

#     print("..doing FFT")
#     tbl_names, status, err          =   [], True, ''


#     MPICLIENT                       =   start_mpi()
#     dic_result                      =   {}

#     an_tsys                         =   get_tb_data(f"{vis}/SYSCAL", axs=['ANTENNA_ID']).compute()
#     an_tsys                         =   np.unique(an_tsys)
#     rsources_dict                   =   {v: k for k, v in sources_dict.items()}

#     fid                             =   rsources_dict[target]
#     tmask                           =   np.where(df_vis['fid']==int(fid))
#     df_target                       =   df_vis[tmask]

#     ans_target                      =   set(df_target['an1'].dropna().unique().compute())
#     ans_target.update(df_target['an2'].dropna().unique().compute())
#     ans_target                      =   ans_target.intersection(an_tsys)
    
#     selected_scans = []
#     for fid in sources_dict:
#         scans                       =   select_long_scans(fid, df_vis)    
#         selected_scans.extend(scans)

#     try:
#         dic_result = task_short_fringefit(vis, df_vis, an_tsys, selected_scans, anname=anname, spws=spws, 
#                                           caltable=caltable, gaintable=gaintable, iter_scan_count=5, mpiclient=MPICLIENT)
#     except Exception as e:
#         status, err =False, e
#     finally:
#         if not status: raise SystemExit(f"{c['r']}Failed! {c['y']}{str(err)}{c['x']}")

#     for k,v in dic_result.items():
#         success = False
#         if len(v['mpi_ids']): 
#             res         =   MPICLIENT.get_command_response(v['mpi_ids'], block=True)
#             success     =   res[0]['successful']
#             if not success:
#                 e       =   res[0]['traceback']
#         else:
#             success     =   False
#             e           =   v['e']

#         refant,scansj   =   k.split('___')
        
#         scannos         =   v['scannos']
#         if not success:
#             print(f'{c["r"]}processing failed!{c["x"]}', scannos,'with refant', refant, f"\nreason : {e}\n")
#         else: 
#             if Path(v['tbl_names']).exists(): 
#                 print(f'{c["g"]}processed{c["x"]}', scannos,'with refant', refant)
#                 tbl_names.append(v['tbl_names'])
#             else:
#                 err_flag = f"Successful fringefit execution but table not found"
#                 dic_result[f"{refant}"]['err_flag'] = err_flag
#                 print(f'{c["r"]}processing failed{c["x"]}', scannos,'with refant', refant, f"\nreason : {err_flag}\n")
#     return tbl_names

# def ff_to_tbl_names(vis, df_vis, sources_dict, anname, meta, metafile, refants=None, selected_sources=None, spws='', target='', gaintable=None, new_tbls=False, mpi=True):
#     """
    
#     """
#     #   prepare and load
#     hms                         =   datetime.now().strftime("%m%d_%H%M%S")
#     wd                          =   Path(vis).parent
#     fft_tb                      =   f"{wd}/fft_tab/{Path(vis).stem}_{hms}_ff"
    
#     # if not metafile : metafile = str(wd / 'meta_shortfft.vasco')
#     # meta = load_metadata(vis, metafile=metafile, refants=refants, sources=sources, determine=new_meta)
    
#     # scans                       =   meta['scans']
#     # fields                      =   meta['fields']
#     # refants                     =   meta['refants']
#     # sp                          =   df.from_dict(scans, orient='index')
#     # td                          =   Time(sp.t1, format='mjd')-Time(sp.t0, format='mjd')
#     # sp['td']                    =   TimeDelta(td, format='jd').sec
    
#     if not gaintable: 
#         gaintable               =   [f'{wd}/calibration_tables/accor.t',f'{wd}/calibration_tables/gc.t',f'{wd}/calibration_tables/tsys.t']
#         gaintable               =   [gt for gt in gaintable if Path(gt).exists()]
    
#     if not new_tbls:
#         tbl_names               =   glob.glob(f"{str(Path(meta['fft_tb']))}*.t")
#         if len(tbl_names) < 1: 
#             meta['fft_tb'] = None
#             raise SystemExit(f"{c['r']} Failed! couldn't find tables{c['x']}")
#     else:
#         Path(fft_tb).mkdir(exist_ok=True, parents=True)
#         tbl_names               =   fringefit_for_refant_scans(vis, df_vis, target, sources_dict, anname, caltable=fft_tb, refants=refants, selected_sources=selected_sources, 
#                                                                spws=spws, gaintable=gaintable)
#         meta['fft_tb']          =   fft_tb
#     save_metafile(metafile, meta)
#     return tbl_names


# def find_refant_fromtbls(vis, tbls, sources_dict, verbose=False, wt_d=1.0, wt_snr=0.9, wt_tsys=0.8):
#     """
#     finds refants from Short Fringe Fit tables
#     """
#     SNR_UPPER_LIMIT                         =   380
#     msmd.open(vis)

#     df_field_ant                            =   df_fromtb(vis, tbls, msmd)
#     n_ant                                   =   4
#     print_tbls                              =   """ """

#     msmd.done()

#     df_field_ant_sorted                     =   df_field_ant.sort_values(by=["SNR_median"], ascending = False)
    

#     df_field_ant                            =   df_field_ant.loc[df_field_ant['SNR_median']>SNR_THRES]
#     std_tsys                                =   df_field_ant['STD_TSYS']

#     p_ofd                       =   (1-(df_field_ant['d']/df_field_ant['d'].max()))
#     p_ofsnr                     =   (df_field_ant.SNR_median.clip(upper=SNR_UPPER_LIMIT)/SNR_UPPER_LIMIT) if df_field_ant.SNR_median.max()>SNR_UPPER_LIMIT else (df_field_ant['SNR_median']/df_field_ant['SNR_median'].max())
#     p_oftsys                    =   (1-(std_tsys/std_tsys.max()))
    
#     df_field_ant.loc[:, 'p']    =   ((p_ofd*wt_d)+(p_ofsnr*wt_snr)+(p_oftsys*wt_tsys))/(wt_d+wt_snr+wt_tsys)
    
#     df_field_ant_sorted                     =   df_field_ant.sort_values(by=['p'], ascending=False)
#     df_field_ant_sorted.rename(columns={'ANTENNA2':'AN_ID'}, inplace=True)
#     df_field_ant_sorted['FIELD_NAME']       =   df_field_ant_sorted['FIELD_ID'].map(sources_dict)
    
#     refants_final               =   list(df_field_ant_sorted['ANNAME'].unique())[:n_ant]
#     calibs                                  =   df_field_ant_sorted[df_field_ant_sorted['ANNAME'].isin(refants_final)]
    
#     calibs.index                            =   calibs['FIELD_ID'].values
#     calibs                                  =   calibs[['FIELD_NAME', 'SNR_FIELD']]
    
#     calibs                                  =   calibs.drop_duplicates(['FIELD_NAME'])
    
#     calibs_final                =   calibs[calibs['SNR_FIELD']>SNR_THRES]
#     calibs_final                =   calibs_final.to_dict('list')
    
#     print_tbls                              +=  df_field_ant_sorted.to_string() + "\n"
#     print_tbls                              +=  calibs[calibs['SNR_FIELD']>SNR_THRES].to_string()
#     if verbose: print(print_tbls)
#     return refants_final, calibs_final, print_tbls

# def identify_refant_casa(vis, selected_sources=None, refants=None, spws=None, target='', ff_tbls=None, new_meta=False, new_tbls=False, mpi=False, verbose=True):
#     """
#     Returns
#     refant_list, calib_dictionary
    
#     :refant_list:       [refants]
#     :calib_dictionary:  {'FIELD_NAME': [sources], {'SNR_FIELD':[snr_sources]}}
#                         snr_sources: median values of all scans, antennas in the field
#     """
#     # ___________________ Reading the Measeurement Set file ____________________

#     [sources] = get_tb_data(f"{vis}/FIELD", axs=['NAME'])
#     [anname] = get_tb_data(f"{vis}/ANTENNA", axs=['NAME'])
    
#     sources_dict = {}
#     for sid, source_name in enumerate(sources): 
#         sources_dict[sid]=str(source_name)

#     time, an1, an2, fids, sids = get_tb_data(f'{vis}', axs=['TIME','ANTENNA1', 'ANTENNA2', 'FIELD_ID', 'SCAN_NUMBER'])
#     time = time/(3600*24)
#     time = Time(time, format='mjd').to_value('decimalyear')

#     data_dict = {
#         'time': time,
#         'an1':an1.T, 'an2':an2.T, 'fid':fids.T,
#         'sid':sids.T
#     }

#     df_vis = df(data_dict)

#     print("..short FFT for refant and calibrator sources")
#     refants, ff_tbls, new_meta, new_tbls, meta, metafile = params_check(vis=vis, sources=sources, refants=refants, spws=spws, ff_tbls=ff_tbls, new_meta=new_meta, new_tbls=new_tbls, mpi=mpi)
    
#     if not ff_tbls: 
#         print("finding tables..")
#         # try:
#             # ff_to_tbl_names(vis, df_vis, sources_dict, anname, meta, metafile, refants=None, selected_sources=None, spws='', target='', gaintable=None, new_tbls=False, mpi=True):
#         ff_tbls     =   ff_to_tbl_names(vis, df_vis, sources_dict, anname, meta, metafile, refants=refants, selected_sources=selected_sources, spws=spws, target=target, new_tbls=new_tbls, mpi=mpi)
#         # except Exception as e:
#         # print("Exception occured!!!","\n\n",e)
#     print("tables collected..")
#     return find_refant_fromtbls(vis, ff_tbls, sources_dict=sources_dict, verbose=verbose)





# _________________________________________________________________



# _____________________________________________________________________________________________________________




# from dask_mpi import initialize
# from dask.distributed import Client, progress, LocalCluster

# initialize()
def daskclient(
    n_workers=10,
    memory_limit="1GB",
    local_directory="/cache/avi/processing/"):

    cluster = LocalCluster(n_workers=n_workers, memory_limit=memory_limit, local_directory=local_directory,)
    client = Client(cluster)

    return client

def get_obsdetails(df_vis_field):                                                       # not being used, this might be ineffecient compared to the groupby which is tested to be giving correct values.
    df_loc  = df_vis_field.compute()
    unique_sids, idx_first_occur = np.unique(df_loc['sid'], return_index=True)

    obs_details = {}

    for i, sid in enumerate(unique_sids):
        start_idx = idx_first_occur[i]
        sid_val     =   df_loc['sid'].values[start_idx]
        if i + 1 < len(idx_first_occur):
            end_idx = idx_first_occur[i + 1] - 1
        else:
            end_idx = len(df_loc) - 1
        t = Time(df_loc.iloc[[start_idx, end_idx]]/(3600*24), format='mjd', scale='tt')
        
        t1 = t[1]
        t0 = t[0]
        td = (t1-t0).to_value('sec')
        
        if 'sid' not in obs_details:
            obs_details = {'sid':[sid_val],'idx': [(start_idx, end_idx)], 'td':[td]}
        else:
            obs_details['sid'].append(sid_val)
            obs_details['idx'].append((start_idx, end_idx))
            obs_details['td'].append(td)
        print(td, t)
        obs_details['tot_obs'] = np.sum(obs_details['td'])
        obs_details['scan_min'] = np.min(obs_details['td'])
        obs_details['scan_max'] = np.max(obs_details['td'])
        
    return obs_details

def get_df_vis_forsampling(vis):
    time, expos, an1, an2, fids, sids, flag_row = get_tb_data(f'{vis}', axs=['TIME', 'EXPOSURE', 'ANTENNA1', 'ANTENNA2', 'FIELD_ID', 'SCAN_NUMBER', 'FLAG_ROW'])

    unflagged                               = np.logical_not(flag_row).astype(int)

    data_dict = {
        'time': time, 'expos':expos,
        'an1': an1.T, 'an2': an2.T, 'fid': fids.T,
        'sid': sids.T, 'unflagged':unflagged.T
    }
    df_vis = dd.from_pandas(df(data_dict), npartitions=10)  
    return df_vis

def add_band_column(df_vis, bands_dict, numchan, nrows):
    
    bandsize_arr        =   [sum(numchan[band_info["spws"]]) for band_info in bands_dict.values()]   # nspw*nchan
    
    pattern_length      =   sum(bandsize_arr)

    band_ids             =   np.repeat(range(len(bandsize_arr)), bandsize_arr)
    
    
    band_ids_tiled = np.tile(band_ids, nrows // pattern_length + 1)
    
    band_series = df(band_ids_tiled, columns=['band_id'])
    
    df_vis = df_vis.assign(band_id=band_series['band_id'])
    
    id_toband = {}
    for i,band in enumerate(bands_dict):
        id_toband[i] = band
    
    df_vis['band'] = df_vis['band_id'].map(id_toband)
    

    return df_vis


def apparant_sampling(vis, target, bands_dict : dict = None, selected_band="", nvis_includes_nchan=False):
    """
    
    calculates nvis/nspw/nbaseline/ntint
    for selected target & band
    
    """
    dic_apparant_sampling   =   {}
    fields = get_tb_data(f"{vis}/FIELD", ['NAME'])
    fid     =   list(fields).index(target)


    tb= table()
    tb.open(f"{vis}/SPECTRAL_WINDOW")
    numchan = tb.getcol('NUM_CHAN')
    chwidths = tb.getcol('CHAN_WIDTH')
    
    tb.done()

    df_vis = get_df_vis_forsampling(vis)
    
    tb.open(f"{vis}")
    nrowsd = tb.nrows()
    tb.close()
    
    
    df_vis                  =   df_vis
    
    if not selected_band:
        df_vis              =   add_band_column(df_vis=df_vis, bands_dict=bands_dict, numchan=numchan, nrows=nrowsd)             # this is based on the assumption that for each timestamp, there will be nspws
        bands_to_process    =   [band for band in bands_dict]
    else:
        bands_to_process    =   [selected_band]
    
    df_vis_field            =   df_vis.query(f"fid=={fid}")
    
    
    if selected_band:
        df_vis_field[f'band']     =   selected_band
        
    
    for band in bands_to_process:
        dic_apparant_sampling[band] = {}
        
        df_vis_field_band   =   df_vis_field.query(f"band=='{band}' & unflagged==1")
        
        expos_max, expos_min =df_vis_field_band['expos'].max().compute(),df_vis_field_band['expos'].min().compute()
        nrows               =   len(df_vis_field_band.index)                  # CASA seems to give nrows in listobs for target as the flagged+unflagged data.
        
        
        
        ntint               =   len(df_vis_field_band.groupby(['time']).max().index)#shape[0]
        nbaseline           =   len(df_vis_field_band.groupby(['an1','an2']).max().index)#shape[0]
        spws                =   bands_dict[band]['spws']                    # is found in the col of chwidths
        # nchan               =   numchan                                            # is found in the row of the chwidths
        chwidth             =   np.min(chwidths[:,spws])/1e3
        
        # df_vis_field_band   =   df_vis_field_band.query(f'an1!=an2')                      # if want to remove auto-corr # alternatively: rem flag and autocorr -> df_vis_field_band[['an1','an2', 'time']][(df_vis_field_band['unflagged']==1) & (df_vis_field_band['an1']!=df_vis_field_band['an2'])]
        # time_groups = df_vis_field_band.groupby([['sid','time']])
        # t1 = Time(time_groups.max().compute().values / (3600 * 24), format='mjd').decimalyear
        # t2 = Time(time_groups.min().compute().values / (3600 * 24), format='mjd').decimalyear
    
        t1 = Time(df_vis_field_band[['time', 'sid']].groupby(['sid']).max().compute()['time'].values/(3600*24), format='mjd').decimalyear
        t2 = Time(df_vis_field_band[['time', 'sid']].groupby(['sid']).min().compute()['time'].values/(3600*24), format='mjd').decimalyear
        
        obslen      =   sum((Time(t1, format='decimalyear')-Time(t2, format='decimalyear')).to_value('sec'))
        scan_min    =   min((Time(t1, format='decimalyear')-Time(t2, format='decimalyear')).to_value('sec'))
        scan_max    =   max(((Time(t1, format='decimalyear')-Time(t2, format='decimalyear')).to_value('sec')))
        
        nspw        =   len(spws)
        nchan       =   max(numchan[bands_dict[band]['spws']])
        nvis                =   nrows*nchan if nvis_includes_nchan else nrows
        # obslen = (Time(df_vis_field_band[['field','time']].groupby(['field']).max()['time'].values[0], format='decimalyear')- Time(df_vis_field_band[['field','time']].groupby(['field']).min()['time'].values[0], format='decimalyear')).to_value('sec')
        
        dic_apparant_sampling[band]={
            "nvis":nvis, "nspw":nspw, "nbaseline":nbaseline, "ntint":ntint,
            "nchan" : nchan,
            "chwidth" : chwidth,
            "apparant_sampling": nvis/nspw/nbaseline/ntint,
            "expos_max":expos_max, "expos_min":expos_min,
            "obslen":obslen,
            "scan_min":scan_min,
            "scan_max":scan_max
        }
        print(band, "done")
    return dic_apparant_sampling


def get_df_vis(vis):
    time, an1, an2, fids, sids = get_tb_data(f'{vis}', axs=['TIME', 'ANTENNA1', 'ANTENNA2', 'FIELD_ID', 'SCAN_NUMBER'])

    # time = time / (3600 * 24)
    # time = Time(time, format='mjd').to_value('unix_tai')

    data_dict = {
        'time': time,
        'an1': an1.T, 'an2': an2.T, 'fid': fids.T,
        'sid': sids.T
    }
    df_vis = dd.from_pandas(df(data_dict), npartitions=10)  # Adjust partitions based on your dataset size

    return df_vis

def get_tb_data(vis, axs=[]):
    tb_tool = table()
    tb_tool.open(vis)
    total_rows = tb_tool.nrows()
    # chunks = max(1000, int(total_rows / np.log10(total_rows + 1)))
    
    m = 1000000
    max_chunks = 40*m # N million rows, each row=20B => 20N MB each chunk
    chunks = int(total_rows / np.log10(total_rows + 1))
    chunks = max(100000, min(chunks, max_chunks))        # min 20B * 10000 => 200KB each chunk

    # if  < 2000:
    #     chunks = 1
    # elif tb_tool.nrows() < 20000:
    #     chunks = tb_tool.nrows() // 10
    # elif tb_tool.nrows() < 200000:
    #     chunks = tb_tool.nrows() // 100
    # else:
    #     chunks = tb_tool.nrows() // 1000

    res = []
    if isinstance(axs, str):
        axs = [axs]

    if len(axs):
        for ax in axs:
            col_data = da.from_array(tb_tool.getcol(ax), chunks=chunks).persist()
            res.append(col_data)

    tb_tool.close()
    
    if len(res)==1:
        res = res[0]
    return res

def select_long_scans(df_vis, fids, nscan=5):    
    selected_long_scans = {}
    if not isinstance(fids, list):
        fids = [fids]
    tmask = df_vis['fid'].isin(fids)

    df_field = df_vis[tmask].persist()
    df_group = df_field.groupby(['fid', 'sid'])

    mx_group = df_group.max().compute()
    mn_group = df_group.min().compute()


    for fid in fids:
        
        fmx = mx_group.query(f'fid=={fid}').reset_index()
        fmn = mn_group.query(f'fid=={fid}').reset_index()
        fmx['time'] = fmx['time'] / (3600 * 24)
        fmx['time'] = Time(fmx['time'], format='mjd').to_value('decimalyear')
        fmn['time'] = fmn['time'] / (3600 * 24)
        fmn['time'] = Time(fmn['time'], format='mjd').to_value('decimalyear')
        
        td = Time(fmx['time'], format='decimalyear') - Time(fmn['time'], format='decimalyear')
        # print(td.to_value('sec')[np.argsort(-td.to_value('sec'))][:nscan])
        selected_long_scans[fid] =list(fmx['sid'][np.argsort(-td.to_value('sec'))][:nscan])
    return selected_long_scans

def compute_antennas(group):
    return set(group['an1']).intersection(set(group['an2']))

def compute_scans(group, selected_scans=None):
    if selected_scans:
        mask    =   group['sid'].isin(selected_scans)
    else:
        mask    =   group['sid'].notnull()
    return group.groupby(['an1', 'an2'])['sid'].apply(lambda x: x[mask].tolist())

def mpi_fringefit(vis, fid, scannos, refant, ff_caltable, gt, spws, antenna=[], minsnr=3, mpiclient=MPICLIENT):
    ms_name_fp      = vis
    caltable_fp     = ff_caltable
    gaintable_fp    = gt
    
    spw             =   spws 
    corrcomb        =   'none'
    append          =    False
    combine         =   ''
    gainfield       = []
    
    fringefit_cmd = ("""fringefit(vis='{0}',""".format(ms_name_fp)
                    + """caltable='{0}',""".format(caltable_fp)
                    + """field='{0}',""".format(str(fid))
                    + """spw='{0}',""".format(spw)
                    + """selectdata={0},""".format('True')
                    + """timerange='{0}',""".format('')
                    + """antenna='{0}',""".format(str(",".join(antenna)))
                    + """scan='{0}',""".format(str(scannos))
                    + """observation='{0}',""".format('')
                    + """msselect='{0}',""".format('')
                    + """solint='inf',"""
                    + """combine='{0}',""".format(str(combine))
                    + """refant='{0}',""".format(str(refant))
                    + """minsnr={0},""".format(str(minsnr))
                    + """zerorates={0},""".format('False')
                    + """globalsolve={0},""".format('False')
                    + """append={0},""".format(str(append))
                    + """docallib={0},""".format('False')
                    + """callib='{0}',""".format('')
                    + """gaintable={0},""".format(str(gaintable_fp))
                    + """gainfield={0},""".format(str(gainfield))
                    + """corrdepflags={0},""".format('True')
                    + """concatspws={0},""".format('True')
                    + """corrcomb='{0}',""".format(str(corrcomb))
                    + """parang={0}""".format('True')
                    + """)"""
                    )
    res = mpiclient.push_command_request(fringefit_cmd, block=False)
    
    return res

def short_fringe_fit_mpi(vis, dic_ant_with_scans, annames, caltable, gt, spws, iter_scan_count=5, mpiclient=MPICLIENT):
    
    print("..doing FFT")
    tbl_names, status, err          =   [], True, ''
    res, e = [], ''

    # MPICLIENT                       =   start_mpi()
    dic_result                      =   {}
    
    for refantid, scans in dic_ant_with_scans.items():
        refant = annames[refantid]
        scans = scans[0]
        # print(refant,scans)
        for sel_scan in list(zip_longest(*[iter(scans)] * iter_scan_count, fillvalue=None)):
            ff_scans = [str(s) for s in sel_scan if s is not None]
            ff_scans_joined = ",".join(ff_scans)            
            ff_caltable = f"{str(Path(caltable).absolute() / Path(caltable).name)}_{refant}_{''.join(ff_scans)}.t"
            try:            
                print(f'{c["g"]}processing..{c["x"]} refant:{refant} scans:{ff_scans_joined}')    
                res = mpi_fringefit(vis, fid='', scannos=ff_scans_joined, refant=refant, 
                                    ff_caltable=ff_caltable, gt=gt, spws=spws, mpiclient=mpiclient)
            except Exception as e:
                print(f'{c["r"]}processing failed!{c["x"]} check parameters | refant:{refant} scans:{ff_scans_joined} \n{e}')
                status      =   'failed'
            finally:
                if not status=='failed':
                    tbl_names.append(ff_caltable)
                    dic_result[f"{refant}___{'_'.join(ff_scans)}"] =  {'scannos': ff_scans_joined, 'mpi_ids': res, 
                                                    'e':e, 'ff_caltable': ff_caltable}
                status=''

    for k,v in dic_result.items():
        success = False
        if len(v['mpi_ids']): 
            res         =   mpiclient.get_command_response(v['mpi_ids'], block=True)
            success     =   res[0]['successful']
            if not success:
                # print('Errfinding traceback')
                e           =   res[0]['traceback']
        else:
            success     =   False
            e           =   v['e']

        fid, refant     =   k.split('___')
        # field_name      =   fields[fid]['name']
        scannos         =   v['scannos']
        if not success:
            print(f'{c["r"]}processing failed{c["x"]}', scannos,'for scans', scannos, 'with refant', refant, f"\nreason : {e}\n")
        else: 
            if Path(v['tbl_names']).exists(): 
                print(f'{c["g"]}processed{c["x"]}', scannos,'for scans', scannos, 'with refant', refant)
                tbl_names.append(v['tbl_names'])
            else:
                err_flag = f"Successful fringefit execution but table not found"
                dic_result[f"{refant}___{'_'.join(ff_scans)}"]['err_flag'] = err_flag
                print(f'{c["r"]}processing failed{c["x"]}', scannos,'for scans', scannos, 'with refant', refant, f"\nreason : {err_flag}\n")
                
    tbl_metafile = f"{str(Path(caltable).absolute() / Path(caltable).name)}.vasco"
    save_metafile(metafile=tbl_metafile, metad=dic_result)
    
    return dic_result, tbl_names
# all_selected_scans


def getremovableant_fromtarget(vis, target):
    tb1 = table()
    tb1.open(f"{vis}/FIELD")
    idx_target = list(tb1.getcol("NAME")).index(target)
    tb1.close()

    tb1.open(vis)
    anids = set()
    anids.update(np.unique(tb1.query(f"FIELD_ID=={idx_target}").getcol('ANTENNA1')))
    anids.update(np.unique(tb1.query(f"FIELD_ID=={idx_target}").getcol('ANTENNA2')))
    tb1.close()

    tb1.open(f"{vis}/ANTENNA")
    annames = tb1.getcol("NAME")
    tb1.close()
    
    anids_list = list(anids)
    rm_anids = []

    target_annames = annames[anids_list]
    for anid in range(len(annames)):
        if not anid in anids:
            rm_anids.append(list(range(len(annames))).pop(anid))
    return list(rm_anids), list(annames[rm_anids])


def an_dic(vis, target=None, antenna=[], notantenna=[]):

    tsys_anid, tsys_vals  = get_tb_data(f"{vis}/SYSCAL", axs=['ANTENNA_ID', 'TSYS'])
    pos, annames           = get_tb_data(f"{vis}/ANTENNA", axs=['POSITION', 'NAME'])
    pos = pos.compute()
    xyz = list(zip(*pos))
    tsys_anid = tsys_anid.compute()
    if target is not None: 
        _, rm_ants = getremovableant_fromtarget(vis, target)
        notantenna = notantenna + rm_ants    
    
    tsys_vals = tsys_vals.compute()
    an_dict = {}

    ans_seq = []

    for anid,an in enumerate(annames.compute()):
        if not antenna: antenna = list(range(len(annames)))         # here, in case something changes within loop
        antenna = [antv for antv in antenna if annames[antv] not in notantenna]
        if anid in antenna:       
            an_dict[anid]={'ANNAME': an}
            # measuring centroid distance
            d=[]
            refcoord=xyz[anid]
            for v in xyz:
                d.append(distance.euclidean(refcoord,v)*.001)                                       # Distance of all from one refant
            an_dict[anid]['d']=np.nanmedian(d)   # Median distance of all ants for one refant
            
            # calculating TSYS variability
            tsys_std = []
            for tsys_val in tsys_vals:
                itsys = np.where(tsys_anid==anid)
                tsy_an_std = np.nanstd(tsys_val[itsys]) if len(itsys) else float('nan')
                tsys_std.append(tsy_an_std)
                
            an_dict[anid]['STD_TSYS']= np.nanmean(tsys_std, axis=0) if not all(np.isnan(tsys_std)) else float('nan')
    return an_dict


def df_fromables(tbl_names):
    """
    Efficiently loads and concatenates multiple tables into a Dask DataFrame.
    """

    dataframes = []  # Collect dataframes first, process later

    for tbl_name in tbl_names:
        
        snr, an1, an2, time, scan, fid, flag = get_tbd(tbl_name, ['SNR', 'ANTENNA1', 'ANTENNA2', 'TIME', 'SCAN_NUMBER', 'FIELD_ID', 'FLAG'])

        # Convert directly to Pandas DataFrame (kept small for efficiency)
        df_tb = df({
            "TIME": time.ravel(),
            "ANTENNA1": an1.ravel(),
            "ANTENNA2": an2.ravel(),
            "SCAN": scan.ravel(),
            "FIELD_ID": fid.ravel(),
            "FLAG": flag.all(axis=0).ravel(),
            "SNR": snr.mean(axis=0).ravel(),
        })

        dataframes.append(df_tb)  # Collect for later concatenation

    # Convert to a single Pandas DataFrame and then to Dask
    df_tb = pdconc(dataframes, ignore_index=True)

    # Convert to Dask DataFrame for scalability
    ddf = dd.from_pandas(df_tb, npartitions=1)
    # ddf = ddf.sort_values(by="SNR", ascending=False)

    return ddf.persist()

def get_tbd(tbl, cols=[]):
    tb=table()
    tb.open(tbl)
    res=[]
    if isinstance(cols, str):
        cols = [cols]
    for col in cols:
        res.append(tb.getcol(col))

    tb.close()
    return res[0] if len(res)==1 else res

def select_df_refant_sources(tbls, an_dict, autocorr=False, minsnr=3.0, calib_snr_thres=7.0, wt_d=1.0, wt_tsys=0.0, wt_occ=0.85, wt_snr=1.0, n_calib=6):
    
    ddf_tbl = df_fromables(tbls)
    
    ddf_tbl = ddf_tbl.query(f'SNR>{minsnr}')

    if not autocorr:
        ddf_tbl = ddf_tbl.query('ANTENNA1!=ANTENNA2')
    # field_snr = ddf_tbl.groupby(['FIELD_ID']).median()[['SNR']].sort_values(by=['SNR'], ascending=False)
    # ddf_snr_baselines = ddf_tbl.groupby(['ANTENNA2', 'ANTENNA1']).median().sort_values(by=['SNR'], ascending=False).compute()
    ddf_tbl['baseline'] = ddf_tbl.apply(lambda row: tuple(sorted([row["ANTENNA1"], row["ANTENNA2"]])), axis=1, meta=('x', 'object'))
    # ddf_tbl.groupby(['baseline', 'FIELD_ID']).count().compute()
    # ddf_tbl['baseline_occ']=ddf_tbl['baseline'].map(Counter(ddf_tbl['baseline']))#.groupby(['baseline', ''])
    # ddf_tbl.groupby(['baseline', 'baseline_occ'])['SNR'].median().compute().reset_index().sort_values(by=['SNR', 'baseline_occ'], ascending=False)

    def select_lower_antenna(row):
        """Selects the antenna with the lower distance based on the dictionary."""
        a1, a2 = row["ANTENNA1"], row["ANTENNA2"]
        
        return an_dict[int(a1)]['ANNAME'] if (int(a1) in an_dict and int(a2) in an_dict and an_dict[int(a1)]['d']<an_dict[int(a2)]['d']) else an_dict[int(a2)]['ANNAME']

    def select_antenna_id(row):
        """Selects the antenna with the lower distance based on the dictionary."""
        a1, a2 = row["ANTENNA1"], row["ANTENNA2"]
        
        return a1 if (int(a1) in an_dict and int(a2) in an_dict and an_dict[int(a1)]['d']<an_dict[int(a2)]['d']) else a2

    def select_refant_d(row):
        """Selects the antenna with the lower distance based on the dictionary."""
        a1, a2 = row["ANTENNA1"], row["ANTENNA2"]
        
        return an_dict[int(a1)]['d'] if (int(a1) in an_dict and int(a2) in an_dict and an_dict[int(a1)]['d']<an_dict[int(a2)]['d']) else an_dict[int(a2)]['d']

    def select_tsys_d(row):
        """Selects the antenna with the lower distance based on the dictionary."""
        a1, a2 = row["ANTENNA1"], row["ANTENNA2"]
        
        return an_dict[int(a1)]['STD_TSYS'] if (int(a1) in an_dict and int(a2) in an_dict and an_dict[int(a1)]['d']<an_dict[int(a2)]['d']) else an_dict[int(a2)]['STD_TSYS']


    # ddf_tbl["a1"] = ddf_tbl["ANTENNA1"].map(lambda x: an_dict[int(x)]["ANNAME"], meta=("a1", "str"))
    # ddf_tbl["a2"] = ddf_tbl["ANTENNA2"].map(lambda x: an_dict[int(x)]["ANNAME"], meta=("a2", "str"))
    # ddf_tbl["a1_D"] = ddf_tbl["ANTENNA1"].map(lambda x: an_dict[int(x)]["d"], meta=("a1_D", "float64"))
    # ddf_tbl["a2_D"] = ddf_tbl["ANTENNA2"].map(lambda x: an_dict[int(x)]["d"], meta=("a2_D", "float64"))
    # ddf_tbl['a1_count']=ddf_tbl['ANTENNA1'].map(Counter(ddf_tbl['ANTENNA1']))
    # ddf_tbl['a2_count']=ddf_tbl['ANTENNA2'].map(Counter(ddf_tbl['ANTENNA2']))


    ddf_tbl["refant"] = ddf_tbl.apply(select_lower_antenna,axis=1, meta=("refant", "str"))
    ddf_tbl["refantid"] = ddf_tbl.apply(select_antenna_id,axis=1, meta=("refantid", "int"))
    ddf_tbl["refant_D"] = ddf_tbl.apply(select_refant_d,axis=1, meta=("refant_D", "float64"))
    ddf_tbl["STD_TSYS"] = ddf_tbl.apply(select_tsys_d,axis=1, meta=("STD_TSYS", "float64"))

    ddf_tbl['refant_count']=ddf_tbl['refant'].map(Counter(ddf_tbl['refant']))
    ddf_tbl['refant_count'] = ddf_tbl['refant_count']/ddf_tbl['refant_count']
    ddf_tbl = ddf_tbl.sort_values(by=['refant_count'], ascending=False)

    refant_snr_median = ddf_tbl.groupby(['FIELD_ID','refant','refantid', 'refant_D','STD_TSYS', 'refant_count'])[['SNR']].median().reset_index().compute()
    
    refant_snr_median_18 = refant_snr_median.dropna().query('SNR>18')
    if len(refant_snr_median_18['FIELD_ID'].unique())<n_calib+1:
        refant_snr_median_18 = refant_snr_median.dropna().query(f'SNR>{calib_snr_thres}')
    if len(refant_snr_median_18['FIELD_ID'].unique())<n_calib+1:
        refant_snr_median_18 = refant_snr_median.dropna().query(f'SNR>{minsnr}')
    if len(refant_snr_median_18['FIELD_ID'].unique())<n_calib+1:
        refant_snr_median_18 = refant_snr_median.dropna().query(f'SNR>1')
        
    d, std_tsys, occ, snr   =   refant_snr_median_18['refant_D'], refant_snr_median_18['STD_TSYS'], refant_snr_median_18['refant_count'], refant_snr_median_18['SNR']
    d_norm                  =   1-(d/d.max())
    tsys_norm               =   1-(std_tsys/std_tsys.max())
    max_field_snr           =   refant_snr_median_18['SNR'].max()
    if max_field_snr>600:
        max_field_snr           =   600#field_snr['SNR'].compute().values[0]
        print(f"for robustness clipping SNR>{np.round(max_field_snr,3)} in the `c` calculation\n")
        snr                     =   snr.clip(upper=max_field_snr)
    snr_norm                =   snr/snr.max()
    occ_norm                =   occ/occ.max()
    

    refant_snr_median_18['c']  =   ((d_norm*wt_d)+(snr_norm*wt_snr)+(tsys_norm*wt_tsys)+(occ_norm*wt_occ))/(wt_d+wt_snr+wt_tsys+wt_occ)
    # refant_snr_median_18['c']  =   ((d_norm*wt_d)+(snr_norm*wt_snr)+(occ_norm*wt_occ))/(wt_d+wt_snr+wt_occ)
    refant_with_c =         refant_snr_median_18.sort_values(by=['c'], ascending=False)

    return refant_with_c, ddf_tbl.persist()

def find_refant_fromdf(tbls, an_dict, sources_dict, autocorr=False, minsnr=3.0, calib_snr_thres=7.0, n_refant=4, n_calib=6, verbose=True):

    tbls = [tbl for tbl in tbls if Path(tbl).exists()]

    df_refant, ddf_tbl = select_df_refant_sources(tbls=tbls, an_dict=an_dict, autocorr=autocorr, minsnr=minsnr, calib_snr_thres=calib_snr_thres, n_calib=n_calib)

    refants = df_refant['refant'].unique()[:n_refant]

    pp_out                          =   ""
    ddf_tbl_18 = ddf_tbl.dropna().query('SNR>18')
    if len(ddf_tbl_18['FIELD_ID'].unique())<n_calib+1:
        ddf_tbl_18 = ddf_tbl.dropna().query(f'SNR>{calib_snr_thres}')
    df_field = ddf_tbl_18[['FIELD_ID','SCAN', 'SNR']].groupby(['FIELD_ID','SCAN']).mean().compute().sort_values(by=['SNR'], ascending=False).reset_index()
    
    pp_out += df_refant.to_string() + "\n"
    pp_out += "\n"
    pp_out += df_field.groupby(by=['FIELD_ID']).max().reset_index()[['FIELD_ID','SNR']].sort_values(by=['SNR'], ascending=False).to_string() + "\n"
    
    df_field = df_field.groupby(by=['FIELD_ID']).max().reset_index()[['FIELD_ID','SNR']].sort_values(by=['SNR'], ascending=False)[:n_calib]          # taking first n_calib considering scans
    
    df_field['NAME'] = df_field['FIELD_ID'].map(sources_dict)
    if verbose: print(pp_out)
    dic_field                       =   df_field.reset_index()[['FIELD_ID','NAME', 'SNR']].groupby(['FIELD_ID']).max().reset_index().to_dict('list')
    return dic_field, refants, pp_out

# def identify_refant_ms(vis, selected_sources=None, refants=None, spws=None, gaintable=[], target='', ff_tbl_name=None, new_meta=False, new_tbls=False, mpi=False, verbose=True):
#     """
#     Returns
#     ----
    
#     refant_list, FIELD_dictionary, printable_output
    
#     :refant_list:       (_list_)
#                         [refants]
#     :FIELD_dictionary:  (_dict_)
#                         {'NAME': [sources], 'SNR':[snr_sources], 'FIELD_ID':[sources_id]}}
#                         snr_sources: median values of all scans, antennas in the field
#     :printable_output:  (_str_)
#                         table as string
#     OLD:
#     :FIELD_dictionary:  {'FIELD_NAME': [sources], {'SNR_FIELD':[snr_sources]}}
#                         snr_sources: median values of all scans, antennas in the field
#     """


#     # ___________________ Reading the Measeurement Set file ____________________
#     dic_field, refants, pp_out      =   {}, [], ""
#     initialize()
#     print("starting MPI")
#     MPICLIENT           =   start_mpi()
    
#     DASKCLIENT                      =   daskclient()
#     DASKCLIENT.restart()
#     # try:
#     df_vis                      =   get_df_vis(vis).persist()
    
#     metadir                     =   Path(vis).parent / 'vasco.meta'
    
#     sources_list                =   get_tb_data(f"{vis}/FIELD", axs=["NAME"]).compute()
#     annames                     =   get_tb_data(f"{vis}/ANTENNA", axs=["NAME"]).compute()
    
#     sources_dict                =   {}
#     for sid, src in enumerate(sources_list):
#         sources_dict[sid]       =   src

#     # ___________________ Processing ____________________

#     print("..short fringefit to rate the antennas and sources")
#     # refants, ff_tbls, new_meta, new_tbls, meta, metafile = params_check(vis=vis, sources=sources, refants=refants, spws=spws, ff_tbls=ff_tbls, new_meta=new_meta, new_tbls=new_tbls, mpi=mpi)
    
    
#     if not ff_tbl_name: ff_tbl_name = f'{vis}_{target}_ff'

#     an_tsys                         =   get_tb_data(f"{vis}/SYSCAL", axs=['ANTENNA_ID']).compute()
#     an_tsys                         =   np.unique(an_tsys)
#     rsources_dict                   =   {v: k for k, v in sources_dict.items()}

#     fields                          =   df_vis['fid'].unique().persist()
#     nfields                         =   len(fields)
#     fid                             =   rsources_dict[target]
#     tmask                           =   df_vis['fid']==int(fid)
#     df_target                       =   df_vis[tmask].persist()

#     ans_target                      =   set(df_target['an1'].unique().compute())
#     ans_target.update(df_target['an2'].unique().compute())
#     ans_target                      =   ans_target.intersection(an_tsys)

#     fids = sources_dict.keys()

#     nscan = 5
#     if nfields > 50:   
#         nscan = 2
#     if nfields > 90:   
#         nscan = 1
#     print(f"\t{nfields} fields found, using {nscan} long scans for each field")
    
#     selected_long_scans          =   select_long_scans(df_vis, list(fids), nscan=nscan)

#     all_selected_scans            =   []
#     dic_ant_with_scans            =   {}
#     all_selected_scans.extend(sid for f in selected_long_scans for sid in selected_long_scans[f])
#     print("..processed 0")
#     df_sid_ans              =       df_vis.groupby(['sid', 'an1', 'an2']).max().reset_index()

#     df_sid_ans              =       df_sid_ans.persist()

#     scan_with_ants          =       df_sid_ans.groupby('sid').apply(compute_antennas, meta=('anid', 'object'))
#     scan_with_ants          =       scan_with_ants.persist()
#     print("..processed ..1")
#     print(df_sid_ans.to_string())
#     ant_with_scans          =       df_sid_ans.map_partitions(compute_scans, selected_scans=all_selected_scans, meta=('sid', 'object')).compute()
#     print("..processed ....2")
#     anmax                   =       max(ant_with_scans.index.max())
#     print("..processed ......3")

#     # ___________________ Creating Metadata ____________________
#     res_metafile            =   f'{metadir}/meta_snrrating.vasco'
#     df_metafile             =   f'{metadir}/{Path(vis).stem}_df_vis.parquet'
#     dic_result              =   {}

#     shutil.rmtree(df_metafile, ignore_errors=True)
#     shutil.rmtree(res_metafile, ignore_errors=True)
#     # df_vis.to_parquet(df_metafile,  engine="pyarrow", write_index=True)
#     # dic_result['df_vis']    =   df_metafile
#     # except Exception as e:
#     #     traceback.print_exc()
#     # finally:
#     #     # ___________________ Stopping dask client ____________________
#     #     DASKCLIENT.shutdown()

#     # ___________________ Using MPI for fringefitting _____________
#     for i in range(anmax+1):
#         dic_ant_with_scans[i] = list(ant_with_scans[islice[:], islice[i]].ravel())
#         dic_ant_with_scans[i].extend(ant_with_scans[islice[i], islice[:]].ravel())

#     dic_result, tbls    =   short_fringe_fit_mpi(vis, dic_ant_with_scans, annames, caltable=ff_tbl_name, gt=gaintable, spws=spws, iter_scan_count=5, mpiclient=MPICLIENT)
    
#     print("tables collected..")
#     save_metafile(res_metafile, dic_result)

#     # ___________________ Starting dask client ____________________
#     # if DASKCLIENT.status == 'closed':
#     #     DASKCLIENT = daskclient()
#     # DASKCLIENT.restart()

#     # try:
#     #     # ___________________ finding refant and sources ______________

#     #     dic_field, refants, pp_out = find_refant_fromdf(tbls, an_dic(vis), sources_dict, verbose=verbose)
#     # except Exception as e:
#     #     traceback.print_exc()
#     # finally:
#     DASKCLIENT.shutdown()
#     return dic_field, refants, pp_out
