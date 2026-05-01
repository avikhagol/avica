from avica import c
from avica.util import read_metafile, save_metafile

from avica.ms.mpiclient import get_mpi_client
from avica.ms.tables import an_dic, get_ant_scans, get_name_dict, get_tb_data
from avica.config import Config, CONFIG_MAPPING

from casatools import table, logsink
import polars as pl
import numpy as np

from typing import List
from collections import Counter, defaultdict
from itertools import zip_longest
from pathlib import Path

SNR_CLIP_DEFAULT = 600

avicalog=logsink('avica.casa_log')
avicalog.setlogfile='avica.casa_log'
avicalog.setglobal(True)


class ObservationInp(Config):
    science_target                  =   None
    calibrators_instrphase          =   None
    calibrators_bandpass            =   None
    calibrators_rldly               =   None
    calibrators_phaseref            =   None

class ArrayInp(Config):
    refant                          =   ''

# -------------------------------------- Main Class

class FringeDetectionRating:
    def __init__(self, vis:str, caltable_folder:str=None, n_refant=5, n_calib=6, n_scans=10, iter_scan_count=5,
                 selected_sources:List[str]=None, selected_scans:List[int]=None, selected_ants:List[int]=None, selected_spws=[],
                 gaintables=[], interp=[], metafolder="", verbose=False):
        """rates antenna and sources by FFT SNR from the fringefit task.
        Args:
            vis (str): measurement set file.
            caltable_folder (str, optional): calibration table folder. Defaults to None.
            n_refant (int, optional): number of refant to select. Defaults to 5.
            n_calib (int, optional): number of calibrators to select. Defaults to 6.
            selected_sources (List[str], optional): filter result for only selected sources. Defaults to None.
            selected_scans (List[int], optional): filter result for only selected scans. Defaults to None.
            selected_ants (List[int], optional): filter result for only selected antennas. Defaults to None.
            selected_spws (list, optional): filter result for only selected spws. Defaults to [].
            gaintables (list, optional): input gaintables to use for fringefit task. Defaults to [].
            interp (list, optional): input interpolation on gaintables to use for fringefit task. Defaults to [].

        Example:

        ```python
        sr = FringeDetectionRating(vis,selected_sources = ['source-name'])
        sr.caltable_folder ='somewhere'
        dic_field, refants, pp_out = sr.exec_FFT_fringefit(multiband=True)
        res = {'observation': sr.obs.data,'array': sr.arr.data}
        ```

        """

        self.vis                    =   vis
        self.caltable_folder        =   caltable_folder or str(Path(vis).parent.absolute())
        self.n_calib                =   n_calib
        self.n_refant               =   n_refant
        self.n_scans                =   n_scans
        self.verbose                =   verbose
        self.iter_scan_count        =   iter_scan_count

        self.dict_antenna           =   an_dic(self.vis)                                    # {int:ANNAME:str,'d':np.float,'STD_TSYS':np.float}
        self.dict_sources           =   get_name_dict(self.vis, 'FIELD')                    # {int:str}
        self.dict_sources_r         =   {v:k for k,v in self.dict_sources.items()}          # {str:int}

        self.tsys_antid             =   [antid for antid, v in self.dict_antenna.items() if not np.isnan(v['STD_TSYS']) and v['STD_TSYS'] >=0.0]

        self.gaintables             =   gaintables
        self.interp                 =   interp
        self.selected_spws          =   selected_spws
        self.selected_sources       =   selected_sources or list(self.dict_sources_r.keys())
        self.selected_source_ids    =   [int(sourceid) for sourceid,sourcename in self.dict_sources.items() if sourcename in self.selected_sources]
        self.selected_scans         =   selected_scans
        self.metafolder             =   Path(metafolder) if metafolder else Path(caltable_folder).parent / "avica.meta"

        self.selected_ants          =   selected_ants or self.tsys_antid

        self.dict_field_ant_withscans=   get_ant_scans(self.vis, self.selected_source_ids)   # {fid:{anid:set(scids)}]
        self.df_scans               =   get_df_scans(vis=self.vis, dict_field_ant_with_scans=self.dict_field_ant_withscans)

        self.refants                =   []
        self.calibrators            =   {}
        self.snr_dict_forsources    =   {}

        self.mpiclient              =   get_mpi_client()

        self.obs                    =   ObservationInp()
        self.arr                    =   ArrayInp()


    def select_good_scans(self, nscans=9, anid=None):
        """selects nscans with longest duration and maximum antenna availability

        Args:
            nscans (int, optional): number of scans. Defaults to 9.
        """
        df_scans = self.df_scans
        if anid is not None : df_scans = df_scans.filter(pl.col('anid')==anid)
        self.selected_good_scans    =   get_best_scans(df_scans, nscans)
        return self.selected_good_scans

    def get_dic_ant_with_scans(self):
        dic_ant_with_scans = {}
        for antid in self.selected_ants:
            if antid not in dic_ant_with_scans:
                dic_ant_with_scans[antid] = {'scans':[], 'name':str(self.dict_antenna[antid]['ANNAME'])}
                for scs_in_source in self.select_good_scans(nscans=self.n_scans, anid=antid).values():
                    dic_ant_with_scans[antid]['scans'].extend(scs_in_source)
        return dic_ant_with_scans

    def exec_FFT_fringefit(self, multiband=True):
        dic_ant_with_scans                              =   self.get_dic_ant_with_scans()
        dic_result                                      =   task_fringefit_fft_only(self.vis, dic_ant_with_scans=dic_ant_with_scans,
                                                                    iter_scan_count=self.iter_scan_count,
                                                                    caltable_folder=self.caltable_folder, gt=self.gaintables, interp=self.interp,
                                                                    spws=self.selected_spws, multiband=multiband, verbose=self.verbose)
        self.dic_field, self.refants, self.pp_out       =   find_refant_fromdf(tbls=dic_result['tbl_names'], an_dict=self.dict_antenna, sources_dict=self.dict_sources,
                                                                    n_calib=self.n_calib, n_refant=self.n_refant)

        self.obs.calibrators_instrphase                             =   self.dic_field['NAME']
        self.obs.calibrators_bandpass = self.obs.calibrators_rldly  =   self.obs.calibrators_instrphase[0]
        self.arr.refant                                             =   self.refants


        if not self.metafolder.exists():
            self.metafolder.mkdir(exist_ok=True)
        save_metafile(self.metafolder / "sources.avica", metad=self.dic_field)
        save_metafile(self.metafolder / "refants.avica", metad={"refant":self.refants})
        with open(str(self.metafolder / "snrating.out"), "w") as wbuff: wbuff.write(f"{self.pp_out}")
        return self.dic_field, self.refants, self.pp_out

# -------------------------------------- Pipeline Specific injectors


# -------------------------------------- CASA tasks

def casatask_fringefit(vis:str, fid:str, scannos:str, refant:str, ff_caltable:str, gt:List=[], interp:List[str]=[], spws:List=[], antenna:List=[],
                       minsnr=3, multiband=False, mpiclient=None):
    """execute CASA task fringefit in MPI mode if MPI mode was activated else on single core.

    Args:
        vis (str): measurement set file.
        fid (str): field id of the source
        scannos (str): scan numbers joined.
        refant (str): refant selected.
        ff_caltable (str): output calibration table name.
        gt (List, optional): gain tables. Defaults to [].
        interp (List[str], optional): interpolation on the gain tables. Defaults to [].
        spws (List, optional): spws selected. Defaults to [].
        antenna (List, optional): antenna selected. Defaults to [].
        minsnr (int, optional): minimum SNR. Defaults to 3.
        multiband (bool, optional): choose multiband vs sinle band. Defaults to False.
        mpiclient (_type_, optional): MPICLIENT from the casampi module. Defaults to None.

    Returns: (dict/str)
        dict result from the MPI run in MPI mode else 'None'
    """
    ms_name_fp      = vis
    caltable_fp     = ff_caltable
    gaintable_fp    = gt
    interp          = interp

    spw             =   ",".join([str(sp) for sp in spws])
    corrcomb        =   'none'
    append          =    False
    combine         =   '' if not multiband else 'spw'
    concatspws      =   'False' if not multiband else 'True'
    gainfield       = []
    res             =   'None'
    fringefit_cmd   = ("""fringefit(vis='{0}',""".format(ms_name_fp)
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
                    + """interp={0},""".format(str(interp))
                    + """corrdepflags={0},""".format('True')
                    + """concatspws={0},""".format(concatspws)
                    + """corrcomb='{0}',""".format(str(corrcomb))
                    + """parang={0}""".format('True')
                    + """)"""
                    )

    if mpiclient is None:
        from casatasks import fringefit
        eval(fringefit_cmd)
    else:
        res             =   mpiclient.push_command_request(fringefit_cmd, block=False)

    return res

def task_fringefit_fft_only(vis:str, dic_ant_with_scans:dict, caltable_folder:str, gt:List[str]=[], interp:List[str]=[], spws:List=[], iter_scan_count=5,
                            multiband=False, verbose=True):
    """calls casatasks.fringefit with/without MPI with default values set to do either multiband/single fringefit without global solve.

    Args:
        vis (str): measurement set file.
        dic_ant_with_scans (dict): input dictionary {anid:{'scans':[scan], 'name':ANNAME}}
        caltable_folder (str): calibration table folder to produce tables from fringefit task.
        gt (List[str]): input gain tables for the fringefit.
        interp (List[str]): interpolation for gain tables.
        spws (List): list of spws to consider during fringefit.
        iter_scan_count (int, optional): number of scans to do fringefit in a single run. Defaults to 5.
        multiband (bool, optional): choose between multiband/single band. Defaults to False.
        verbose (bool, optional): print output. Defaults to True.

    Raises:
        FileNotFoundError: if the folder for calibration doesn't exist

    Returns:
        dic_result (dict): dictionary containing key : refant_joinedscans for values mpi_ids, scan numbers, fringefit caltable, error. And a key with complete table path . {tbl_names:[..], refant_joinedscannos:{...}}
    """
    if not Path(caltable_folder).absolute().exists():
        raise FileNotFoundError(f"caltable_folder : {caltable_folder}")

    mpiclient       =   get_mpi_client()

    if verbose : print("..doing FFT")

    tbl_names, status, err          =   [], True, ''
    res, e                          =   [], ''

    dic_result                      =   {}

    for refantid, v in dic_ant_with_scans.items():
        scans = v['scans']
        refant = v['name']

        refantid = int(refantid)
        iter_by_scans = list(zip_longest(*[iter(scans)] * iter_scan_count, fillvalue=None))
        for sel_scan in iter_by_scans:
            ff_scans = [str(s) for s in sel_scan if s is not None]
            ff_scans_joined = ",".join(ff_scans)
            ff_caltable = f"{str(Path(caltable_folder).absolute() / Path(caltable_folder).name)}_{refant}_{''.join(ff_scans)}.t"
            try:
                print(f'processing.. refant:{refant} scans:{ff_scans_joined}')

                res             =   casatask_fringefit(vis, fid='', scannos=ff_scans_joined, refant=refant,
                                    ff_caltable=ff_caltable, gt=gt, interp=interp, spws=spws, multiband=multiband, mpiclient=mpiclient)
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
            if v['mpi_ids']=='None':
                success=True
            else:
                res         =   mpiclient.get_command_response(v['mpi_ids'], block=True)
                success     =   res[0]['successful']
                if not success:
                    # print('Errfinding traceback')
                    e           =   res[0]['traceback']
        else:
            success     =   False
            e           =   v['e']

        refant, sca     =   k.split('___')
        # field_name      =   fields[fid]['name']
        scannos         =   v['scannos']
        if not success:
            print(f'{c["r"]}processing failed{c["x"]}','for scans', scannos, 'with refant', refant, f"\nreason : {e}\n")
        else:
            if Path(v['ff_caltable']).exists():
                print(f'{c["g"]}processed{c["x"]}','for scans', scannos, 'with refant', refant)
                tbl_names.append(v['ff_caltable'])
            else:
                err_flag = "Successful fringefit execution but table not found"
                dic_result[f"{refant}___{'_'.join(ff_scans)}"]['err_flag'] = err_flag
                print(f'{c["r"]}processing failed{c["x"]}','for scans', scannos, 'with refant', refant, f"\nreason : {err_flag}\n")

    dic_result['tbl_names'] = tbl_names
    tbl_metafile = f"{str(Path(caltable_folder).absolute() / Path(caltable_folder).name)}.avica"
    save_metafile(metafile=tbl_metafile, metad=dic_result)
    return dic_result

# -------------------------------------- Dataframes

def df_fromables(tbl_names:List[str])->pl.DataFrame:
    """Efficiently loads and concatenates multiple tables into a Dask DataFrame.

    Args:
        tbl_names (List[str]): path of calibration tables from the fringefit task.

    Returns:
        df_tb (pl.DataFrame): concatenated tables from the calibration tables.
    """

    dataframes = []

    for tbl_name in tbl_names:

        snr, an1, an2, time, scan, fid, flag, spw = get_tb_data(tbl_name, ['SNR', 'ANTENNA1', 'ANTENNA2', 'TIME', 'SCAN_NUMBER', 'FIELD_ID', 'FLAG','SPECTRAL_WINDOW_ID'])

        df_tb = pl.DataFrame({
            "TIME": time.ravel(),
            "ANTENNA1": an1.ravel(),
            "ANTENNA2": an2.ravel(),
            "SCAN": scan.ravel(),
            "FIELD_ID": fid.ravel(),
            "FLAG": flag.all(axis=0).ravel(),
            'SPW':spw.ravel(),
            "SNR": snr.mean(axis=0).ravel(),
        })

        dataframes.append(df_tb)

    df_tb = pl.concat(dataframes, )

    return df_tb

def select_df_refant_sources(tbls:List[str], an_dict:dict, autocorr=False, minsnr=3.0, calib_snr_thres=7.0, wt_d=1.0, wt_tsys=0.0, wt_occ=0.85, wt_snr=1.0):
    """get DataFrame containing reference antenna and another DataFrame containing tables from the fringefit calibration with merged columns from antenna selection DataFrame.

    Args:
        tbls (List[str]): fringefit calibration tables path
        an_dict (Dict): dictionary of antenna from avica.ms.tables.an_dic
        autocorr (bool, optional): whether to consider autocorr. Defaults to False.
        minsnr (float, optional): minimum SNR threshold. Defaults to 3.0.
        calib_snr_thres (float, optional): deprecated. Defaults to 7.0.
        wt_d (float, optional): weight to apply on Distance column. Defaults to 1.0.
        wt_tsys (float, optional): weight to apply on STD_TSYS column. Defaults to 0.0.
        wt_occ (float, optional): weight to apply on antenna occurance column. Defaults to 0.85.
        wt_snr (float, optional): weight to apply on SNR column. Defaults to 1.0.
        n_refant (int, optional): Number of refant to select. Defaults to 5.

    Returns: (tuple)
        res (pl.DataFrame): polars DataFrame containing result of refant selection.
        df_tbl (pl.DataFrame): polars DataFrame containing fringefit calibration table data.
    """
    df_tbl = df_fromables(tbls)
    an_df = pl.DataFrame([
        {"id": int(k), "ANNAME": v['ANNAME'], "d": v['d'], "STD_TSYS": v['STD_TSYS']}
        for k,v in an_dict.items()
    ])

    df_tbl = df_tbl.filter(pl.col('SNR')>minsnr)

    if not autocorr:
        df_tbl = df_tbl.filter(pl.col('ANTENNA1')!=pl.col('ANTENNA2'))

    df_tbl = (
        df_tbl
        .join(an_df.rename({"ANNAME": "n1", "d": "d1", "STD_TSYS": "t1"}), left_on="ANTENNA1", right_on="id", how="left")
        .join(an_df.rename({"ANNAME": "n2", "d": "d2", "STD_TSYS": "t2"}), left_on="ANTENNA2", right_on="id", how="left")
    )

    df_tbl = df_tbl.with_columns([
        pl.when(pl.col("d1") < pl.col("d2"))
          .then(pl.col("n1")).otherwise(pl.col("n2")).alias("refant"),
        pl.when(pl.col("d1") < pl.col("d2"))
          .then(pl.col("ANTENNA1")).otherwise(pl.col("ANTENNA2")).alias("refantid"),
        pl.when(pl.col("d1") < pl.col("d2"))
          .then(pl.col("d1")).otherwise(pl.col("d2")).alias("refant_D"),
        pl.when(pl.col("d1") < pl.col("d2"))
          .then(pl.col("t1")).otherwise(pl.col("t2")).alias("STD_TSYS")
    ])
    df_tbl = df_tbl.with_columns(
        pl.col("refantid")                                # NOTE: here refantid refers to the shorter distance from centroid, hence counting "over" refantid is different than counting "over" ANTENNA for each baseline.
        .filter(pl.col("FLAG") == False)
        .count().over("refantid").alias("refant_occ")
    )
    df_tbl = df_tbl.with_columns(
        pl.col("refant_occ").fill_null(0)
    )

    refant_snr_median = (
        df_tbl.group_by(['FIELD_ID', 'refant', 'refantid', 'refant_D', 'STD_TSYS', 'refant_occ'])
        .agg(pl.col("SNR").median())
        .sort("refant_occ", descending=True)
    )

    # for threshold in [18, calib_snr_thres, minsnr, 1.0]:        # checks the snr thresholds and selects all sources above the SNR limit if atleast ncalib are there.
    #     filtered = refant_snr_median.filter(pl.col("SNR") > threshold).drop_nulls()
    #     if filtered.select(pl.col("FIELD_ID").n_unique()).to_series()[0] >= n_calib + 1:
    #         break
    # refant_snr_median = filtered

    res = refant_snr_median.with_columns([
        (1 - (pl.col("refant_D") / pl.col("refant_D").max())).alias("d_norm"),
        (1 - (pl.col("STD_TSYS") / pl.col("STD_TSYS").max())).alias("tsys_norm"),
        (pl.col("SNR").clip(None,SNR_CLIP_DEFAULT) / pl.col("SNR").clip(None,SNR_CLIP_DEFAULT).max()).alias("snr_norm"),
        (pl.col("refant_occ") / pl.col("refant_occ").max()).alias("occ_norm")
    ])

    res = res.with_columns(
        c = ((pl.col("d_norm") * wt_d) + (pl.col("snr_norm") * wt_snr) +
             (pl.col("tsys_norm") * wt_tsys) + (pl.col("occ_norm") * wt_occ)) /
            (wt_d + wt_snr + wt_tsys + wt_occ)
    ).sort("c", descending=True)

    res = res.group_by('refant').head(1)      # keeps row with max `c` per field because of sort done before
    res = res.sort("c", descending=True)

    return res, df_tbl

def find_refant_fromdf(tbls:List[str], an_dict:dict, sources_dict:dict, autocorr=False, minsnr=3.0, calib_snr_thres=7.0, n_refant=4, n_calib=6, verbose=True):
    """takes fringefit calibration tables path and gives refant and calibrators

    Args:
        tbls (List[str]): fringefit calibration tables path
        an_dict (Dict): dictionary of antenna from avica.ms.tables.an_dic
        sources_dict (Dict): dictionary of sources {FIELD_ID:NAME}
        autocorr (bool, optional): whether to consider autocorr. Defaults to False.
        minsnr (float, optional): minimum SNR threshold. Defaults to 3.0.
        calib_snr_thres (float, optional): deprecated. Defaults to 7.0.
        n_refant (int, optional): Number of refant to select. Defaults to 4.
        n_calib (int, optional): Number of calibrators to select. Defaults to 6.
        verbose (bool, optional): print output. Defaults to True.

    Returns:
        (dic_field, refants, pp_out)
        dic_field (dict): {'FIELD_ID': [...], 'NAME': [...], 'SNR': [...]}
        refants (List[str]): [...]
        pp_out (str): printable string output
    """

    pp_out              =   ""
    tbls                =   list(filter(lambda t: Path(t).exists(), tbls))
    df_refant, df_tbl   =   select_df_refant_sources(tbls=tbls, an_dict=an_dict, autocorr=autocorr, minsnr=minsnr, calib_snr_thres=calib_snr_thres)
    refants             =   (df_refant
                                .unique(subset="refantid", keep="first", maintain_order=True)
                                .head(n_refant).get_column("refant")
                                .to_list())

    df_field            =   (df_tbl.group_by(['FIELD_ID', 'SCAN'])
                                .agg(pl.col("SNR").mean())
                                .sort("SNR", descending=True))

    src_df              =   pl.DataFrame({"FIELD_ID": [int(k) for k in sources_dict.keys()],"NAME": list(sources_dict.values())})
    df_field            =   df_field.join(src_df, on="FIELD_ID", how="left")

    with pl.Config(
            ascii_tables                =   True,       # Use +--+ instead of Unicode boxes
            tbl_hide_column_data_types  =   True,
            tbl_hide_dataframe_shape    =   True,
            tbl_width_chars             =   10000,
            float_precision             =   4,
            tbl_rows                    =   -1,
            tbl_cols                    =   -1
            ):
        pp_out += str(df_refant) + "\n\n"
        pp_out += str(df_field)

    if verbose:
        print(pp_out)

    dic_field = (
        df_field.sort("SNR", descending=True)
        .group_by("FIELD_ID")
        .head(1)
        .select(["FIELD_ID", "NAME", "SNR"])
        .sort("SNR", descending=True).head(n_calib)
        .to_dict(as_series=False) #
    )

    return dic_field, refants, pp_out

# -------------------------------------- Helpers to get dictionaries reading Measurement Set

def get_scan_durations(vis:str, sids:List[int]):
    """gets a dictionary containing scan duration reading the measurement set file.

    Args:
        vis (str): measurement set file.
        sids (List[int]): list of scan number.

    Returns:
        dict: dictionary containing scan duration. {scan_id:scan_duration}
    """
    tb = table()
    tb.open(vis)
    subtb = tb.query(columns="DISTINCT SCAN_NUMBER,TIME", query=f'SCAN_NUMBER in {sids}')
    time = subtb.getcol('TIME')
    scans = subtb.getcol('SCAN_NUMBER')
    subtb.close()

    scans_df = pl.DataFrame({
        'time': time,
        'scans': scans
    })
    scan_durations = (
        scans_df.group_by('scans')
        .agg([
            pl.col('time').min().alias('start'),
            pl.col('time').max().alias('end'),
            (pl.col('time').max() - pl.col('time').min()).alias('duration')
        ])
        .sort('duration', descending=True)
    )

    tb.close()

    # Create a nested dictionary: {scan_id: {"duration": X, "start": Y, "end": Z}}
    dict_scan_durations = {
        row["scans"]: {
            "duration": row["duration"],
            "start": row["start"],
            "end": row["end"]
        }
        for row in scan_durations.to_dicts()
    }
    return dict_scan_durations

def get_df_scans(vis:str, dict_field_ant_with_scans:dict):
    """_summary_

    Args:
        vis (str): measurement set file.
        dict_field_ant_with_scans (dict): input dictionary {fid:{anid:[scan]}}

    Returns:
        pl.DataFrame: DataFrame containing `fid`, `anid`, `scan` columns
    """

    dict_res = defaultdict(set)

    fids = list(dict_field_ant_with_scans.keys())
    sids = [sid for fid in fids for scans in dict_field_ant_with_scans.get(fid, {}).values() for sid in scans]
    scan_counts = Counter(sids)

    dict_scan_durations = get_scan_durations(vis, list(set(sids)))


    for fid in fids:
        for anid, scans in dict_field_ant_with_scans[fid].items():
            dict_res[anid].update(scans)

    rows = []
    for fid, ant_dict in dict_field_ant_with_scans.items():
        for antid, scans in ant_dict.items():
            for sid in scans:
                rows.append({
                    "fid": fid,
                    "anid": antid,
                    "scan": sid,
                    "duration": dict_scan_durations[sid]['duration'],
                    'start_time':dict_scan_durations[sid]['start'],
                    'end_time':dict_scan_durations[sid]['end'],
                    "anfreq":scan_counts[sid],
                })

    df_scans = pl.DataFrame(rows)
    df_scans = df_scans.with_columns([
        pl.col("fid").cast(pl.Int32),
        pl.col("anid").cast(pl.Int32),
        pl.col("scan").cast(pl.Int32)
    ])


    return df_scans


def get_best_scans(df_scans:pl.DataFrame, nscans:int)->dict:
    """returns best scans from the scan duration

    Args:
        df_scans (pl.DataFrame): input polars DataFrame
        nscans (int): number of scans

    Returns:
        dict_res (Dict[List]): dictionary containing best scans
        {fid:[scan]}

    """
    top_scans = (
    df_scans
    .unique(subset=["fid", "scan"])
    .with_columns(
        mid_time = (pl.col("end_time") + pl.col("start_time")) / 2)
    .sort(["duration", "anfreq", "mid_time"], descending=[True, True, True])
    .group_by("fid")
    .head(nscans))

    result_df = top_scans.group_by("fid").agg(pl.col("scan"))
    dict_res = {fid: result_df.filter(pl.col("fid") == fid)["scan"].to_list()[0] for fid in result_df["fid"]}
    return dict_res

if __name__ == "__main__":
    import argparse
    import sys
    import json
    mpiclient =  get_mpi_client()
    print(dir(mpiclient))
    kwargs = {}
    if not sys.stdin.isatty():
        try:
            kwargs = json.load(sys.stdin)
            print(kwargs)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON input - {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser = argparse.ArgumentParser(description="fringefit for fft s/n rating")
        parser.add_argument('params', nargs='*', help="Pairs of key=value")
        args = parser.parse_args()
        try:
            for arg in args.params:
                key, value = arg.split('=', 1)
                # Optional: Convert string numbers/booleans to Python types
                if value.lower() == 'true': value = True
                elif value.lower() == 'false': value = False

                kwargs[key] = value
        except ValueError:
            print("Error: Arguments must be in the format key=value")
            sys.exit(1) # Exit gracefully

    fr = FringeDetectionRating(**kwargs)
    fr.exec_FFT_fringefit()
