from itertools import zip_longest
from pathlib import Path
from typing import List
from vasco.pipe.core import PersistentMpiCasaRunner, FringeFit
from vasco.util import c, save_metafile
from vasco.ms.fringefit import find_refant_fromdf

def casatask_fringefit(
    vis: str,
    fid: str,
    scannos: str,
    refant: str,
    ff_caltable: str,
    gt: List = [],
    interp: List[str] = [],
    spws: List = [],
    antenna: List = [],
    minsnr=3,
    multiband=False,
    mpiclient=None,
):
    """Returns CASA task fringefit command used by vasco pipeline for single reference antenna.

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
        mpiclient (MPICommandClient, optional): MPICLIENT from the casampi module. Defaults to None.

    Returns: (dict/str)
        casa task fringefit command
    """
    spw = ",".join([str(sp) for sp in spws])
    corrcomb = "none"
    append = False
    combine = "" if not multiband else "spw"
    concatspws = False if not multiband else True
    gainfield = []

    task_frigefit_cmd = FringeFit(
        vis=vis,
        field=str(fid),
        caltable=ff_caltable,
        minsnr=minsnr,
        antenna=str(",".join(antenna)),
        scan=str(scannos),
        refant=refant,
        spw=spw,
        corrcomb=corrcomb,
        append=append,
        combine=combine,
        concatspws=concatspws,
        selectdata=True,
        timerange="",
        observation="",
        msselect="",
        solint="inf",
        callib="",
        gaintable=gt,
        interp=interp,
        gainfield=gainfield,
        zerorates=False,
        globalsolve=False,
        docallib=False,
        corrdepflags=True,
        parang=True,
    )

    return task_frigefit_cmd


def task_fringefit_payload(
    vis: str,
    dic_ant_with_scans: dict,
    caltable_folder: str,
    gt: List[str] = [],
    interp: List[str] = [],
    spws: List = [],
    iter_scan_count=5,
    multiband=False,
    verbose=True,
    casadir="",
    errf="",
    logfile="",
    mpi_cores=10,
):
    dic_result = {"tbl_names": []}
    if not Path(caltable_folder).absolute().exists():
        raise FileNotFoundError(
            f"caltable_folder : {caltable_folder}"
        )

    tbl_names = []
    dic_result = {}
    if verbose:
        print("..doing FFT")
    mpi_runner = PersistentMpiCasaRunner(
        casadir=casadir, mpi_cores=mpi_cores
    )
    job_ids = []
    for refantid, v in dic_ant_with_scans.items():
        scans = v["scans"]
        refant = v["name"]

        refantid = int(refantid)
        iter_by_scans = list(
            zip_longest(
                *[iter(scans)] * iter_scan_count, fillvalue=None
            )
        )

        for sel_scan in iter_by_scans:
            ff_scans = [str(s) for s in sel_scan if s is not None]
            ff_scans_joined = ",".join(ff_scans)
            ff_caltable = f"{str(Path(caltable_folder).absolute() / Path(caltable_folder).name)}_{refant}_{''.join(ff_scans)}.t"

            print(
                f"processing.. refant:{refant} scans:{ff_scans_joined}"
            )

            cmd_ff = casatask_fringefit(
                vis,
                fid="",
                scannos=ff_scans_joined,
                refant=refant,
                ff_caltable=ff_caltable,
                gt=gt,
                interp=interp,
                spws=spws,
                multiband=multiband,
            )
            step = cmd_ff.to_step(
                casadir=casadir,
                errf=errf,
                logfile=logfile,
                mpi_cores=mpi_cores,
            )

            ff_caltable = f"{str(Path(caltable_folder).absolute() / Path(caltable_folder).name)}_{refant}_{''.join(ff_scans)}.t"

            # push to mpi and catch errors
            res = mpi_runner.run_task(
                task_name=step.cmd.task_casa,
                args=step.cmd.args,
                args_type=step.cmd.args_type,
                block=False,
            )
            dic_result_key = f"{refant}___{'_'.join(ff_scans)}"
            job_ids.append(
                (
                    step.cmd.args["refant"],
                    ff_scans_joined,
                    ff_caltable,
                    dic_result_key,
                    res,
                )
            )
            dic_result[dic_result_key] = {
                "scannos": ff_scans_joined,
                "mpi_ids": res["ret"],
                "status": res["status"],
                "ff_caltable": ff_caltable,
                "err_msg": "",
            }

    # checking response
    err_msg = ""
    for anname, ff_scans_joined, ff_caltable, dic_result_key, res in job_ids:
        if "status" in res and res["status"] == "success":
            final_response = mpi_runner.get_response(
                res["ret"], block=True
            )
            if Path(ff_caltable).exists():
                print(
                    f"{c['g']}processed{c['x']}",
                    "for scans",
                    ff_scans_joined,
                    "with refant",
                    anname,
                )
                tbl_names.append(ff_caltable)
            else:
                err_msg = "Successful fringefit execution but table not found"
                print(
                    f"{c['r']}processing failed{c['x']}",
                    "for scans",
                    ff_scans_joined,
                    "with refant",
                    anname,
                    f"\nreason : {err_msg}\n",
                )
        else:
            err_msg = (
                res["error"]
                if "error" in res
                else "Failed to push command."
            )
            trcback_msg = (
                res["traceback"] if "traceback" in res else f"{res}"
            )

            print(
                f"{c['r']}processing failed{c['x']}",
                "for scans",
                ff_scans_joined,
                "with refant",
                anname,
                f"\nreason : {err_msg}\n{trcback_msg}",
            )
        dic_result[dic_result_key]["err_msg"] = (
            err_msg
        )

    dic_result["tbl_names"] = tbl_names
    if verbose:
        print("..collected tables\n")
        print("..closing MPI")
    mpi_runner.close()
    if verbose:
        print("done\n")
    return dic_result



def exec_FFT_fringefit(
    self, casadir, errfile, logfile, mpi_cores, multiband=True
):
    dic_ant_with_scans = self.get_dic_ant_with_scans()
    dic_result = task_fringefit_payload(
        self.vis,
        dic_ant_with_scans=dic_ant_with_scans,
        iter_scan_count=self.iter_scan_count,
        caltable_folder=self.caltable_folder,
        gt=self.gaintables,
        interp=self.interp,
        spws=self.selected_spws,
        multiband=multiband,
        verbose=self.verbose,
        casadir=casadir,
        errf=errfile,
        logfile=logfile,
        mpi_cores=mpi_cores,
    )

    self.dic_field, self.refants, self.pp_out = find_refant_fromdf(
        tbls=dic_result["tbl_names"],
        an_dict=self.dict_antenna,
        sources_dict=self.dict_sources,
        n_calib=self.n_calib,
        n_refant=self.n_refant,
    )

    self.obs.calibrators_instrphase = self.dic_field["NAME"]
    self.obs.calibrators_bandpass = self.obs.calibrators_rldly = (
        self.obs.calibrators_instrphase[0]
    )
    self.arr.refant = self.refants

    if not self.metafolder.exists():
        self.metafolder.mkdir(exist_ok=True)
    save_metafile(
        self.metafolder / "sources.vasco", metad=self.dic_field
    )
    save_metafile(
        self.metafolder / "refants.vasco",
        metad={"refant": self.refants},
    )
    with open(str(self.metafolder / "snrating.out"), "w") as wbuff:
        wbuff.write(f"{self.pp_out}")
    return self.dic_field, self.refants, self.pp_out