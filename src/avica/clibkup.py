#!/usr/bin/env python3
from pathlib import Path
from typing import List, Optional

import json, time, shutil, subprocess, resource
import typer
from typing_extensions import Annotated

rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (26000, rlimit[1]))

vascodir = str(Path.home()) + '/.vasco/'

c = {"x": "\033[0m", "g": "\033[32m", "r": "\033[31m", "b": "\033[34m",
     "c": "\033[36m", "w": "\033[0m", "y": "\033[33m"}
rfc_filepath = f"{vascodir}/rfc_path.txt"

ASCII_ART = """\b

____    ____  ___           _______.  ______   ______   
\   \  /   / /   \         /       | /      | /  __  \  
 \   \/   / /  ^  \       |   (----`|  ,----'|  |  |  | 
  \      / /  /_\  \       \   \    |  |     |  |  |  | 
   \    / /  _____  \  .----)   |   |  `----.|  `--'  | 
    \__/ /__/     \__\ |_______/     \______| \______/  

    VLBI and SMILE-based CASA Optimizations (VASCO).
"""

vasco_cli = typer.Typer(
    name="vasco",
    help=f"{ASCII_ART}",
    add_completion=True,
    rich_markup_mode="rich",
)


def params_fromlist(pl_value: str) -> dict:
    params = {}
    for pl_i in pl_value.split(','):
        if '=' in pl_i:
            k, v = pl_i.split('=')
            if "'" in v:
                v = v.replace("'", "")
            else:
                try:
                    v = int(v)
                except ValueError:
                    try:
                        v = float(v)
                    except ValueError:
                        v = str(v).strip()
            params[k] = v
    return params


def casadir_find(write: bool = True):
    import readline
    readline.set_completer_delims('\t\n=')
    readline.parse_and_bind("tab: complete")
    cp_txt, do, auto = '', 'y', 'y'
    casa_path = f"{vascodir}/casa_path.txt"
    casadir = ''
    if Path(casa_path).exists():
        with open(casa_path, "r") as cp:
            cp_txt = cp.readlines()[0]
            if cp_txt:
                auto = 'no'
                casadir = cp_txt
                print(f"There is a CASA path already written: {cp_txt}")
    if write:
        if cp_txt:
            print(f"{c['c']} Are you sure you want to proceed overwriting?{c['x']}")
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
            print(f"{c['r']}Failed!{c['x']} The path '{casadir}' is not a valid casa directory")
            print("Proceed with automatic search? (y/n):")
            auto = input()
    if str(auto).lower() in ["y", "yes"]:
        casadir = Path(str(shutil.which("casa"))).resolve().parent

    if Path(casadir).exists():
        print(f"{c['g']}Success!{c['x']} Found this casa directory:{c['g']} {casadir}{c['x']}")
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


def rfc_find(write: bool = True) -> str:
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
            print(f"{c['c']} Are you sure you want to proceed overwriting?{c['x']}\n\n")
            do = input("(y/n)")
        if str(do).lower() in ["y", "yes"] and not rfc_txt:
            print("Please enter the path for the ASCII file:")
            rfc_txt = input()
        with open(filepath, 'w') as o:
            o.write(f"{rfc_txt}")
    return rfc_txt


def run_withmpi(input_file: List[str], cmd_args: List[str], n_core: int):
    casadir = casadir_find(write=False)
    thisdate = time.strftime('%F-%T', time.gmtime()).replace(':', '_')
    errlogf = f'mpi_and_err.out_{thisdate}'
    casalogf = f'casa.log_{thisdate}'
    vascopath = shutil.which(__name__)
    cmd = [f'{casadir}/mpicasa', '--oversubscribe', '-n', str(n_core),
           f'{casadir}/casa', '--agg', '--nogui', '--logfile', casalogf,
           '-c', vascopath]
    if cmd_args:
        cmd = cmd + cmd_args

    if n_core == 1:
        print(" ".join(cmd))
        raise typer.Exit()
    elif cmd and vascopath:
        rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (26000, rlimit[1]))
        subprocess.run(cmd, stderr=open(errlogf, "+a"))
        proc = subprocess.Popen(['tail', '-n', '5', errlogf], stdout=subprocess.PIPE)
        print(proc.stdout.read().decode('utf-8'))
        if Path(casalogf).exists():
            proc = subprocess.Popen(['tail', '-n', '5', casalogf], stdout=subprocess.PIPE)
            print(proc.stdout.read().decode('utf-8'))


def _vitals_check(
    input_file: List[str],
    sources: List[str],
    identify_targets: bool,
    find_refant: bool,
    split_source: Optional[str],
    metafolder: str,
) -> tuple[bool, str, list]:
    status_check, desc, desc_arr = True, '', []
    if not Path(vascodir).exists():
        Path(vascodir).mkdir(parents=True, exist_ok=True)
    if not Path(metafolder).exists():
        Path(metafolder).mkdir(parents=True, exist_ok=True)

    if sources:
        if identify_targets:
            try:
                desc = open(rfc_filepath, 'r').read()
            except FileNotFoundError:
                _ = rfc_find(write=True)
        elif find_refant:
            desc = 'refants'
        elif split_source:
            pass
        else:
            desc = 'search source'
    elif input_file:
        for file in input_file:
            print(file)
            if not Path(file).exists():
                status_check = False
                desc = f"Input file not found: '{file}'"

    return status_check, desc, desc_arr
setup_app = typer.Typer(help="Configure VASCO paths.")
vasco_cli.add_typer(setup_app, name="setup")

@setup_app.command("casa")
def setup_casa():
    """Set the monolithic CASA installation path."""
    casadir_find(write=True)

@setup_app.command("rfc")
def setup_rfc():
    """Set the RFC calibrator list path."""
    rfc_find(write=True)

@vasco_cli.command()
def cli(
        # --- Positional ---
        input_file: Annotated[Optional[List[str]],typer.Argument(help="Input file path(s).")] = None,

        # --- General options ---
        wd: Annotated[str, typer.Option("--wd", help="Current workdir; path used for the metafolder.")] = str(Path.cwd()),
        mpi: Annotated[int, typer.Option("--mpi", help="Use MPI when available.")] = 1,
        ants: Annotated[str,typer.Option("--ants", help="Selected antennas (comma-separated).")] = '',
        spws: Annotated[str,typer.Option("--spws", help="Selected SPWs (comma-separated).")] = '',
        sources: Annotated[str,typer.Option("-S", "--sources", help="Selected fields / source names (comma-separated).")] = '',
        from_meta: Annotated[bool,typer.Option("--from-meta", help="Run without re-determining metadata and tables.")] = False,
        from_snr: Annotated[bool,typer.Option("--from-snr",help=("Find sources from SNR data. Second input_file is the SNR metafile "
                                                "(must have .vasco in path). Also needs --output-file, else only prints."),)    ] = False,
        output_file: Annotated[Optional[str],typer.Option("-o", "--output-file", help="Output file path.")] = None,
        gen_antab: Annotated[bool,typer.Option("--gen-antab", help="Generate ANTAB.")] = False,
        modify: Annotated[bool,typer.Option("--modify", help="Allow table modification (used with --fix-dupltb).")] = False,

        # --- Operations ---
        list_observation: Annotated[Optional[str],typer.Option("-l", "--list-observation",help="List useful observation details (like listobs/listr). "
                                                                                                "Optionally pass a card name; defaults to SCAN.",)] = None,
        identify_targets: Annotated[bool,typer.Option("-t", "--identify-targets",help="Find targets for phasecal, science, and bright cal for FF.")] = False,
        find_refant: Annotated[bool,typer.Option("-r", "--find-refant",help="Find reference antenna by checking TSYS info.")] = False,
        fix_dupltb: Annotated[bool,typer.Option("--fix-dupltb",help="Find and remove duplicate rows in tables after concat.")] = False,
        split_source: Annotated[Optional[str],typer.Option("-s", "--split-source",help="Comma-separated SOURCE_ID/SOURCE_NAME values to split into a new FITS/MS.")] = None,
        to_b: Annotated[Optional[str],typer.Option("--to-B", help="Convert coordinates to B1950.")] = None,
        
        # --- Calibrator List ---
        column: Annotated[Optional[str],typer.Option("-C", "--column",help="Comma-separated column names to retrieve from calibrator list.")] = None,
    ):
    """VLBI and SMILE source based CASA Optimizations (VASCO)."""

    # --- Resolve defaults that depend on other values ---
    if input_file is None:
        input_file = [rfc_filepath] if Path(rfc_filepath).exists() else []

    sources_list: List[str] = sources.split(',') if sources else []
    ants_list: List[str] = ants.split(',') if ants else []
    spws_val = spws if spws else []

    metafolder = f'{wd}/vasco.meta'
    status_check, desc, desc_arr = _vitals_check(
        input_file, sources_list, identify_targets, find_refant, split_source, metafolder
    )
    new_tbls = new_meta = not from_meta
    searchs = 'search source' in desc

    # ------------------------------------------------------------------
    # --gen-antab
    # ------------------------------------------------------------------
    if gen_antab:
        from vasco.idifits import ANTAB
        fitsfile = input_file[0]
        vlbacalf = input_file[1]
        antabfile = f'{wd}/gc_dpfu_fromidi.ANTAB'
        an = ANTAB(fitsfile, vlbacalf)
        allans, _tsys_head, dmissing = an.gen_antab(antabfile)
        pout = ""
        pout += f"missing         \t\t\t:{','.join(dmissing)}\n" if dmissing else "\n"
        pout += f"all antennas    \t:{','.join(allans)}\n" if allans else "\n"
        print(pout)

    # ------------------------------------------------------------------
    # --to-B
    # ------------------------------------------------------------------
    if to_b:
        from vasco.helpers import J2000_toB1920
        print(J2000_toB1920(to_b))

    # ------------------------------------------------------------------
    # Bail on bad inputs
    # ------------------------------------------------------------------
    if not status_check:
        typer.echo(f"Error: {desc}", err=True)
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Source search (calibrator list)
    # ------------------------------------------------------------------
    if searchs:
        from vasco.util import search_sources
        source_found = search_sources(sources_list, str(rfc_find(write=False)))
        if column:
            cols = column.split(',')
            source_found = source_found[cols]
            print(f"search_sources({sources_list}, {desc})[{cols}]")
        else:
            print(f"search_sources({sources_list}, {desc})")
        print(source_found)
        return

    # ------------------------------------------------------------------
    # All other operations require fits / MS imports
    # ------------------------------------------------------------------
    from vasco.fits import _listobs, Targets as t, split, fits
    from vasco.fitsioutil import listobs, IdentifySource as IdS, identify_sources_fromtarget
    from vasco.fitsidiutil.obs import ListObs
    from vasco.fitsidiutil.lib import find_refant as _find_refant_fits

    # --fix-dupltb
    if fix_dupltb:
        from vasco.ms.tables import fix_duplicatedrows
        fix_duplicatedrows(
            refvis=input_file[0],
            newvis=input_file[1],
            nomodify=not modify,
        )

    # -l / --list-observation
    if list_observation is not None:
        cardname = list_observation.split(',')
        for fitsfile in input_file:
            print(Path(fitsfile).name)
            lobs = ListObs(fitsfilepath=fitsfile)
            print(lobs.df_listobs)

    # -t / --identify-targets
    if identify_targets:
        sources_dict = None
        if from_snr and sources_list:
            from vasco.ms import identify_sources_fromsnr_ms
            msname = input_file[0]
            target = sources_list[0]
            sourcesf = (
                input_file[1]
                if len(input_file) > 1 and '.vasco' in input_file[1]
                else None
            )
            minsnr = 7.0
            s = identify_sources_fromsnr_ms(
                msname,
                target_source=target,
                caliblist_file=rfc_find(write=False),
                snr_metafile=sourcesf,
                outfile=output_file,
                flux_thres=minsnr,
                min_flux=minsnr,
                ncalib=6,
            )
            print(s)
        else:
            for fitsfile in input_file:
                if '.ms' not in str(fitsfile).lower():
                    print(Path(fitsfile).name)
                    if sources_list:
                        print(sources_list)
                    if not sources_list:
                        ids = IdS(fitsfile)
                        sources_dict = ids.identify_sources()
                    else:
                        sources_dict = identify_sources_fromtarget(
                            fitsfile=fitsfile,
                            target_source=sources_list[0],
                            rfcfile=rfc_find(write=False),
                            verbose=True,
                        )
                    print(sources_dict)
                    if sources_dict:
                        with open(f'{metafolder}/sources_fits.vasco', 'w') as vrm:
                            json.dump(sources_dict, vrm)
                        sources_list = list(sources_dict.values())
                else:
                    from vasco.ms import identify_sources_fromtarget_ms
                    print(fitsfile)
                    if sources_list:
                        s_dict = identify_sources_fromtarget_ms(
                            fitsfile, sources_list[0], rfc_find(write=False),
                            metafolder=metafolder
                        )
                        for band, sources_d in s_dict.items():
                            print(band, "band")
                            print(sources_d)
                            with open(f'{metafolder}/sources_ms_{band}.vasco', 'w') as vrm:
                                json.dump(sources_d, vrm)

    # -r / --find-refant
    if find_refant:
        for fitsfile in input_file:
            if '.ms' not in str(fitsfile).lower():
                print(Path(fitsfile).name)
                refant_pl, print_outs = _find_refant_fits(fitsfile, err_onmissing=False)
                if print_outs:
                    with open(f'{metafolder}/refants_fits.vasco', 'w') as vrm:
                        json.dump(refant_pl.to_dict(as_series=False), vrm)
                    with open(f'{metafolder}/refants_fits.out', 'w') as vrm:
                        vrm.write(print_outs)
            else:
                from vasco.ms import identify_refant_casa
                print(fitsfile)
                refants, calibs, print_outs = identify_refant_casa(
                    str(fitsfile),
                    new_tbls=new_tbls,
                    new_meta=new_meta,
                    mpi=mpi,
                    target=sources_list[0] if sources_list else '',
                    selected_sources=sources_list,
                    refants=ants_list,
                    spws=spws_val,
                    verbose=True,
                )
                refant_dict = {'refants': refants}
                with open(f'{metafolder}/sources.vasco', 'w') as vrm:
                    json.dump(calibs, vrm)
                with open(f'{metafolder}/refants.vasco', 'w') as vrm:
                    json.dump(refant_dict, vrm)
                with open(f'{metafolder}/refants_sources.out', 'w') as vrm:
                    vrm.write(print_outs)
                print(refant_dict, calibs)

    # -s / --split-source
    if sources_list and split_source:
        for fl in input_file:
            print(fl)
            if '.ms' in fl.lower():
                if mpi > 1:
                    run_withmpi(
                        input_file,
                        ['-s', 'mpi', '-S', ",".join(sources_list),
                         '--output-file', output_file, fl],
                        mpi,
                    )
                else:
                    parallel = split_source == 'mpi'
                    from vasco.ms import split_ms
                    print("running without mpi" if not parallel else "running with mpi")
                    split_ms(vis=fl, outvis=output_file, source_list=sources_list, mpi=parallel)
            else:
                sids = [int(sid) for sid in sources.split(',')]
                for fitsfile in fl:
                    print(Path(fitsfile).name)
                    hdul = fits.open(fitsfile)
                    file_new = Path(hdul.filename())
                    file_new = f"{file_new.stem}_new{file_new.suffix}"
                    split(hdul, sids, file_new)


if __name__ == '__main__':
    vasco_cli()