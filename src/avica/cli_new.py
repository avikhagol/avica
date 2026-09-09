#!/usr/bin/env python3
import csv
from multiprocessing import Pipe
from pathlib import Path
from typing import List, Optional, Any

import resource
import typer

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from avica.util import ASCII_ART, make_art

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

from avica.config import avica_data_dir, avica_pkg_dir

from avica.util import casadir_find, rfc_find, create_config
from avica.pipe.config import CSV_POPULATED_STEPS, PipeConfig

from avica.pipe.main import AvicaPipeline

rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (26000, rlimit[1]))

avicadir = str(Path.home()) + '/.avica/'

c = {"x": "\033[0m", "g": "\033[32m", "r": "\033[31m", "b": "\033[34m",
     "c": "\033[36m", "w": "\033[0m", "y": "\033[33m"}

X  = "\033[0m"

rfc_filepath = f"{avicadir}/rfc_path.txt"


def _result_csv_path(pipe_params):
    target = f"{pipe_params['target']}_"
    return Path(pipe_params["target_dir"]) / f"{target}result.csv"


def _is_successful_result(row):
    try:
        success_count = int(row.get("success_count") or 0)
        failed_count = int(row.get("failed_count") or 0)
    except (TypeError, ValueError):
        return False

    return success_count > 0 and failed_count == 0


def _infer_resume_step(csvfile, ordered_steps):
    csvfile = Path(csvfile)
    if not csvfile.exists():
        return None

    latest_step = None
    latest_success = False
    with open(csvfile, newline="") as result_csv:
        reader = csv.DictReader(result_csv)
        if not reader.fieldnames or "name" not in reader.fieldnames:
            return ordered_steps[0] if ordered_steps else None

        for row in reader:
            name = row.get("name")
            if name in ordered_steps:
                latest_step = name
                latest_success = _is_successful_result(row)

    if latest_step is None:
        return ordered_steps[0] if ordered_steps else None

    latest_idx = ordered_steps.index(latest_step)
    if not latest_success:
        return latest_step

    next_idx = latest_idx + 1
    return ordered_steps[next_idx] if next_idx < len(ordered_steps) else None


def _resolve_pipe_params(target="", configfile="avica.inp",
                         default_configfile="avica.inp", fitsfilenames=""):
    """
    Layer configuration the way `pipe run` does, so that a target's result CSV
    is looked for in the same place it was written to: built-in defaults, then
    the installed global avica.inp, then ~/.avica/avica.inp, then the local
    config file.  `target` is applied last, since it names the CSV.
    """
    global_configfile = str(Path(avica_pkg_dir) / "avica.inp")
    user_configfile = str(Path(avica_data_dir) / Path(default_configfile).name)

    _params = PipeConfig(global_configfile).to_dict()
    if Path(user_configfile).exists():
        _params.update(PipeConfig(user_configfile).to_dict())

    pipe_params = {
        "folder_for_fits": ".",
        "target_dir": "reduction/",
        "primary_value": target,
        "target": target,
        "fitsfilenames": fitsfilenames.split(",") if fitsfilenames else [],
    }
    pipe_params.update(_params)

    if configfile and Path(configfile).exists():
        try:
            pipe_params.update(PipeConfig(configfile).to_dict())
        except Exception as e:
            raise typer.BadParameter(
                f"Failed to read config file '{configfile}': {e}") from e

    if target:
        pipe_params["target"] = target
        pipe_params["primary_value"] = target

    return pipe_params


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
    "validate and fix, known FITS-IDI issues"
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

@pipeline_app.command("config")
def pipe_config(
    outfile: Optional[str] = typer.Option("avica.inp", help="output config file containing key=value"),
    inpfile: Optional[str] = typer.Option(None, help="input config file containing key=value"),
    no_inpfile: Annotated[bool, typer.Option("--no-inpfile", help="do not use the default avica.inp file")] = False,
    default: Annotated[bool, typer.Option("--default", help="adds the configfile to the default config directory")] = False,
    global_default: Annotated[bool, typer.Option("--global", help="adds the configfile to the global config directory")] = False,
    data: Annotated[Optional[List[str]], typer.Argument(help="key=value pairs")] = None,
    summary: Annotated[bool, typer.Option("--summary", help="print a report summary of the parameters")] = False,
    ):
    params = PipeConfig(None).defaults()
    param_sources = dict.fromkeys(params, "default")
    global_configfile = str(Path(avica_pkg_dir) / "avica.inp")
    global_params = PipeConfig(global_configfile).to_dict()
    params.update(global_params)
    param_sources.update(dict.fromkeys(global_params, "global"))

    # Summaries use the same file precedence as pipe run. Writing a config
    # remains scoped to its selected input, without importing user defaults.
    if summary:
        user_configfile = Path(avica_data_dir) / "avica.inp"
        if user_configfile.exists():
            user_params = PipeConfig(user_configfile).to_dict()
            params.update(user_params)
            param_sources.update(dict.fromkeys(user_params, "user"))

    if not inpfile and not no_inpfile:
        local_configfile = outfile if summary else (
            "avica.inp" if not (global_default or default) else None
        )
        if local_configfile and Path(local_configfile).exists():
            inpfile = local_configfile
    if inpfile:
        try:
            input_params = PipeConfig(inpfile).to_dict()
        except Exception as e:
            raise typer.BadParameter(f"Failed to read config file '{inpfile}': {e}") from e
        if summary:
            params.update(input_params)
        else:
            params = input_params
        param_sources.update(dict.fromkeys(input_params, "inpfile"))

    if data:
        for item in data:
            if "=" not in item:
                raise typer.BadParameter(f"Invalid key=value format: '{item}' (missing '=')")
            key, value = item.split("=", 1)
            params[key] = value
            param_sources[key] = "cli"

    source_colours = {
        "default": "yellow", "global": "yellow", "user": "cyan",
        "inpfile": "green", "cli": "magenta",
    }

    def parameter_source(status) -> tuple[str, str, Any]:
        if status.in_input_config:
            input_name = getattr(status, "input_name", status.name)
            origin = param_sources.get(input_name, "inpfile")
            scope = "step" if input_name != status.name else "core"
            return f"{origin}/{scope}", source_colours[origin], status.value
        if status.in_context:
            return "context", "cyan", status.value
        if status.has_default:
            return "default", "yellow", status.value

        return "required/runtime", "red", status.value


    if summary:
        main_pipeline = AvicaPipeline(pipe_params=params)
        main_pipeline.filter_steps(*CSV_POPULATED_STEPS)

        console = Console()

        table = Table(
            title="AVICA parameter summary",
            header_style="bold",
            show_lines=False,
            row_styles=["", ""],
        )

        table.add_column("Step", style="bold cyan", no_wrap=True)
        table.add_column("Parameter")
        table.add_column("Source", no_wrap=True)
        table.add_column("Value")

        reported_params = set()
        for step in main_pipeline.step_names():
            [step_report] = main_pipeline.config_report(step)

            first_row = True
            for name, status in step_report.items():
                source, colour, value = parameter_source(status)

                table.add_row(
                    step if first_row else "",
                    name,
                    Text(source, style=colour),
                    Text(str(value), style=colour),
                )
                first_row = False

                reported_params.add(name)
                reported_params.add(f"{step}.{name}")
            table.add_section()

        first_row = True
        core_defaults = PipeConfig(None).defaults(all=True)

        for param, value in main_pipeline.pipe_params.items():
            if param in reported_params:
                continue

            if param in param_sources:
                origin = param_sources[param]
                source = f"{origin}/core"
                style = source_colours[origin]
            elif param in core_defaults:
                source = "default/core"
                style = "yellow"
            else:
                source = "unknown"
                style = "red"

            table.add_row(
                "other" if first_row else "",
                param,
                Text(source, style=style),
                Text(str(value), style=style),
            )

            first_row = False
        console.print(table)

    elif not params:
        raise typer.BadParameter("No configuration to write. Provide either --inpfile or --data arguments.")

    else:

        if default:
            outfile = str(Path(avica_data_dir) / Path(outfile).name)

        if global_default:
            outfile = str(Path(avica_pkg_dir) / Path(outfile).name)

        create_config(params=params, out=outfile, rj=1, lj=1)

@pipeline_app.command("run")
def run_pipeline(
    fitsfilenames: Annotated[str,typer.Option("--f", "--fitsfilenames", help="fitsfile names comma separated")] = '',
    steps: Annotated[Optional[List[str]],typer.Argument(help="steps for execution")] = CSV_POPULATED_STEPS,
    target: Annotated[str,typer.Option("--t", "--target", help="Selected field / sourc name")] = '',
    configfile: Optional[str] = typer.Option("avica.inp", help="config file containing key=value"),
    default_configfile: Optional[str] = typer.Option("avica.inp", help="default config file name containing key=value"),
    resume: Annotated[bool, typer.Option("--resume", help="Resume after the last successful step in the result CSV.")] = False,
    resume_from: Annotated[Optional[str], typer.Option("--resume-from", help="Start from this pipeline step.")] = None,
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

    global_configfile = str(Path(avica_pkg_dir) / "avica.inp")
    default_configfile = str(Path(avica_data_dir) / Path(default_configfile).name)

    _params = PipeConfig(global_configfile).to_dict()
    if Path(default_configfile).exists():
        _params.update(PipeConfig(default_configfile).to_dict())
    pipe_params={
                "folder_for_fits": ".",
                 "target_dir" : "reduction/",
                 "primary_value": target,
                #  "casadir":"/home/avi/intelligence/env/casa-6.7.0-31-py3.10.el8/",
                #  "rfc_catalogfile":"rfc_2024a_cat.txt",
                 "target":target,
                 "fitsfilenames": fitsfilenames.split(","),
                 }

    pipe_params.update(_params)
    if configfile and Path(configfile).exists():
        try:
            pipe_params.update(PipeConfig(configfile).to_dict())
        except Exception as e:
            raise typer.BadParameter(f"Failed to read config file '{configfile}': {e}") from e
    elif configfile:
        typer.echo(f"Warning: Config file '{configfile}' not found, skipping.", err=True)

    # if configfile:
    #     configdata = PipeConfig(configfile=configfile)
    #     pipe_params.update(configdata.to_dict())

    result_csvfile = _result_csv_path(pipe_params)
    pipe_params["result_csv_file"] = str(result_csvfile)

    # print(DEFAULT_PARAMS['allfitsfile'])
    main_pipeline = AvicaPipeline(pipe_params=pipe_params)

    main_pipeline.filter_steps(*steps)
    if resume_from:
        try:
            steps = main_pipeline.steps_from(resume_from)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--resume-from") from exc
    elif resume:
        if not result_csvfile.exists():
            typer.echo(f"No result CSV found at {result_csvfile}; running requested steps.")
        else:
            resume_from = _infer_resume_step(result_csvfile, main_pipeline.step_names())

        if result_csvfile.exists() and resume_from is None:
            typer.echo(f"All pipeline steps already completed according to {result_csvfile}.")
            return
        if resume_from:
            steps = main_pipeline.steps_from(resume_from)
            typer.echo(f"Resuming from step: {resume_from}")

    if resume_from is not None and resume_from.lower() == 'rpicard':
        main_pipeline.pipe_params['delete_previous_data'] = False

    main_pipeline.filter_steps(*steps)
    result = main_pipeline.execute()


    print(result)


@pipeline_app.command("result")
def pipe_result(
    target: Annotated[str, typer.Option("--t", "--target", help="Selected field / source name")] = '',
    csvfile: Annotated[Optional[str], typer.Option("--csvfile", help="Path to a result CSV. Overrides the --target lookup.")] = None,
    configfile: Optional[str] = typer.Option("avica.inp", help="config file containing key=value"),
    default_configfile: Optional[str] = typer.Option("avica.inp", help="default config file name containing key=value"),
    history: Annotated[bool, typer.Option("--history", help="Show every recorded attempt of every step, instead of the latest.")] = False,
    oneline: Annotated[bool, typer.Option("--oneline", help="Print a single compact status line.")] = False,
    no_detail: Annotated[bool, typer.Option("--no-detail", help="Do not append failure detail panels.")] = False,
    check: Annotated[bool, typer.Option("--check", help="Exit non-zero unless every pipeline step completed successfully.")] = False,
    ):
    """
    _______________________

    Report a pipeline run from its result CSV.

    The default view lists every pipeline step in order with its status,
    counts, duration, and the command needed to continue the run. Steps that
    have not run yet are shown as pending. Failure text is appended below the
    table for any step that did not fully succeed.

    -   --history    every attempt of every step (the CSV is append-only)
    -   --oneline    one status line, for scripts and CI
    -   --check      exit 1 unless the whole pipeline succeeded

    ________________________

    """
    from avica.pipe.report import read_result_csv, render_result, resume_step

    if csvfile:
        result_csvfile = Path(csvfile)
    else:
        pipe_params = _resolve_pipe_params(
            target=target, configfile=configfile,
            default_configfile=default_configfile,
        )
        result_csvfile = _result_csv_path(pipe_params)

    if not Path(result_csvfile).exists():
        typer.echo(f"No result CSV found at {result_csvfile}.", err=True)
        typer.echo("Run the pipeline first, or pass --csvfile.", err=True)
        raise typer.Exit(code=1)

    rows = read_result_csv(result_csvfile)
    label = target or Path(result_csvfile).name.replace("_result.csv", "")

    render_result(
        rows,
        target=label,
        history=history,
        oneline=oneline,
        detail=not no_detail,
    )

    if check and resume_step(rows) is not None:
        raise typer.Exit(code=1)


if __name__=='__main__':
    avica_cli()
