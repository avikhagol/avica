#!/usr/bin/env python3
from pathlib import Path
from shutil import make_archive
from typing import List, Optional

import resource
import typer
import textwrap
from rich.console import Console
from rich.panel import Panel
from avica.util import ASCII_ART, make_art

from typing_extensions import Annotated
from avica.config import avica_data_dir

from avica.util import casadir_find, rfc_find
from avica.pipe.config import CSV_POPULATED_STEPS, PipeConfig

from avica.pipe.main import AvicaPipeline

rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (26000, rlimit[1]))

avicadir = str(Path.home()) + '/.avica/'

c = {"x": "\033[0m", "g": "\033[32m", "r": "\033[31m", "b": "\033[34m",
     "c": "\033[36m", "w": "\033[0m", "y": "\033[33m"}

X  = "\033[0m"

rfc_filepath = f"{avicadir}/rfc_path.txt"


avica_cli = typer.Typer(name="avica",help=ASCII_ART,
    add_completion=False, rich_markup_mode="rich")

@avica_cli.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        make_art()

# ________________________________________________________________________________
#

rfc_filepath = f"{avicadir}/rfc_path.txt"


# ______________________________________________________________________.

#                       Setup
# _______________________________________________________________________.

setup_app = typer.Typer(help="Setup for AVICA pipeline.")
avica_cli.add_typer(setup_app, name="setup")

@setup_app.command("casa")
def setup_casa():
    """Set the monolithic CASA installation path."""
    casadir_find(avica_data_dir, write=True)

@setup_app.command("rfc")
def setup_rfc(rfc_filepath):
    """Set the RFC calibrator list path."""
    rfc_find(rfc_filepath, write=True)

# __________________________    without command

listobs_app = typer.Typer(help="List observation data")
avica_cli.add_typer(listobs_app, name="listobs")

@listobs_app.callback(invoke_without_command=True)
def listobs(fitsfilenames: Annotated[Optional[List[str]], typer.Argument()] = None):
    from avica.fitsidiutil import ObservationSummary
    print(ObservationSummary(fitsfilepaths=fitsfilenames).to_polars())
    # df_obsdata = obsdata.to_polars()

    # print(df_obsdata)


fitsidicheck_app = typer.Typer(help="validate and fix, known FITS-IDI problems")
avica_cli.add_typer(fitsidicheck_app, name="fitsidi_check")

@fitsidicheck_app.callback(invoke_without_command=True)
def fitsidicheck(fitsfilenames: Annotated[Optional[List[str]], typer.Argument()] = None,
                 fix:bool=False, desc:bool=False):
    """
    "validate and fix, known FITS-IDI problems"
    """
    from avica.fitsidiutil.validation import fitsidi_check
    if fitsfilenames is not None:
        for fitsfile in fitsfilenames:
            validators = fitsidi_check(fitsfilepath=fitsfile)
            if desc:
                print(validators)
            else:
                print(validators.run(fix=fix))





# ___________________________


pipeline_app = typer.Typer(help="AVICA pipeline.")
avica_cli.add_typer(pipeline_app, name="pipe")

@pipeline_app.command("run")
def run_pipeline(
    fitsfilenames: Annotated[str,typer.Option("--f", "--fitsfilenames", help="fitsfile names comma separated")] = '',
    stps: Annotated[Optional[List[str]],typer.Argument(help="steps for execution")] = CSV_POPULATED_STEPS,
    target: Annotated[str,typer.Option("--t", "--target", help="Selected field / sourc name")] = '',
    configfile: Optional[str] = typer.Option("avica.inp", help="config file containing key=value"),
    ):
    """
    _______________________

    pipeline steps:
    -   preprocess_fitsidi
    -   fits_to_ms
    -   phaseshift
    -   avica_avg
    -   avicameta_ms
    -   avica_snr
    -   avica_fill_input
    -   avica_split_ms
    -   rpicard


    ________________________

    """

    pipe_params={
                "folder_for_fits": ".",
                 "target_dir" : "reduction/",
                 "primary_value": target,
                #  "casadir":"/home/avi/intelligence/env/casa-6.7.0-31-py3.10.el8/",
                #  "rfc_catalogfile":"rfc_2024a_cat.txt",
                 "target":target,
                 "fitsfilenames": fitsfilenames.split(","),
                 }


    pipe_params.update(PipeConfig(configfile).to_dict())

    # if configfile:
    #     configdata = PipeConfig(configfile=configfile)
    #     pipe_params.update(configdata.to_dict())

    # print(DEFAULT_PARAMS['allfitsfile'])
    main_pipeline = AvicaPipeline(pipe_params=pipe_params)

    # main_pipeline.execute()
    main_pipeline.filter_steps(*stps)
    result = main_pipeline.execute()

    target = f"{pipe_params['target']}_"
    csvfile = f"{pipe_params['target_dir']}/{target}result.csv"


    print(result)

    if not Path(csvfile).exists():
        result.to_polars().write_csv(csvfile)
    else:
        with open(csvfile, "ab") as f:
            result.to_polars().write_csv(f, include_header=False)


if __name__=='__main__':
    avica_cli()
