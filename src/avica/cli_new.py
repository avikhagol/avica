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

from avica.util import casadir_find, rfc_find, create_config, update_config
from avica.pipe.config import CSV_POPULATED_STEPS, PipeConfig

from avica.pipe.main import AvicaPipeline

rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
_soft_target = 26000 if rlimit[1] == resource.RLIM_INFINITY else min(26000, rlimit[1])
try:
    if rlimit[0] != resource.RLIM_INFINITY and rlimit[0] < _soft_target:
        resource.setrlimit(resource.RLIMIT_NOFILE, (_soft_target, rlimit[1]))
except (ValueError, OSError):
    pass    # keep the inherited limit (e.g. macOS caps below the hard limit)

avicadir = str(Path.home()) + '/.avica/'

c = {"x": "\033[0m", "g": "\033[32m", "r": "\033[31m", "b": "\033[34m",
     "c": "\033[36m", "w": "\033[0m", "y": "\033[33m"}

X  = "\033[0m"

rfc_filepath = f"{avicadir}/rfc_path.txt"


def _resolve_run_csv(pipe_params):
    """
    The result CSV that `pipe run` with these params will append to, or None
    when its workdir does not exist yet.  The authoritative path is set again
    by `InitVariables` once the workdir is known (issue #59).
    Falls back to the pre-#59 `{target}_result.csv` when that is all there is.
    """
    from avica.pipe.config import DEFAULT_PARAMS
    from avica.pipe.helpers import resolve_result_csv, legacy_result_csv_path

    params = {**DEFAULT_PARAMS, **pipe_params}   # same layering as AvicaPipeline.execute()
    target_dir = params["target_dir"]
    target = params["target"]
    try:
        csvfile = resolve_result_csv(
            target_dir, target,
            fitsfilenames=params.get("fitsfilenames"),
            folder_for_fits=params.get("folder_for_fits"),
            picard_input_template=params.get("picard_input_template"),
        )
    except Exception as exc:
        typer.echo(f"Warning: could not resolve the workdir for the result CSV: {exc}", err=True)
        csvfile = None

    if csvfile is not None and csvfile.exists():
        return csvfile
    legacy = legacy_result_csv_path(target_dir, target)
    if legacy.exists():
        typer.echo(f"Warning: using old-style result CSV {legacy}; "
                   f"new results are written to result__{{target}}__{{project}}__{{workdir}}.csv", err=True)
        return legacy
    return csvfile


def _select_result_csv(pipe_params, project_code=None, workdir=None):
    """
    Locate the result CSV for `pipe result`. With several matches, list them
    and use the newest. Returns None when nothing matches.
    """
    from avica.pipe.helpers import find_result_csvs, legacy_result_csv_path

    target_dir = pipe_params["target_dir"]
    target = pipe_params["target"]
    matches = find_result_csvs(target_dir, target, project_code=project_code, workdir=workdir)
    if len(matches) > 1:
        typer.echo(f"Found {len(matches)} result CSVs for target '{target}' (newest first):", err=True)
        for path in matches:
            typer.echo(f"  {path}", err=True)
        typer.echo(f"Using the newest: {matches[0]}  (narrow with --project / --workdir, or pass --csvfile)", err=True)
    if matches:
        return matches[0]
    if not project_code and not workdir:
        legacy = legacy_result_csv_path(target_dir, target)
        if legacy.exists():
            typer.echo(f"Warning: using old-style result CSV {legacy}.", err=True)
            return legacy
    return None


def _result_label(csvfile, target=""):
    from avica.pipe.helpers import parse_result_csv_name

    parsed = parse_result_csv_name(csvfile)
    if parsed:
        return f"{parsed['target']} ({parsed['project_code']}/{parsed['workdir']})"
    return target or Path(csvfile).name.replace("_result.csv", "")


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
    no_inpfile: Annotated[bool, typer.Option("--no-inpfile", help="do not discover the local avica.inp for --summary")] = False,
    default: Annotated[bool, typer.Option("--default", help="merge the settings into ~/.avica/avica.inp")] = False,
    global_default: Annotated[bool, typer.Option("--global", help="merge the settings into the installed global avica.inp")] = False,
    data: Annotated[Optional[List[str]], typer.Argument(help="key=value pairs")] = None,
    summary: Annotated[bool, typer.Option("--summary", help="print a report summary of the parameters")] = False,
    ):
    # Summaries layer every scope the way `pipe run` resolves them.  A write
    # touches exactly one layer: the destination is resolved first and updated
    # in place, so lower layers (built-in defaults, the packaged global file, a
    # local avica.inp) are never copied into it, and keys already in the file
    # that nobody asked about survive.
    if summary:
        params = PipeConfig(None).defaults()
        param_sources = dict.fromkeys(params, "default")
        global_configfile = str(Path(avica_pkg_dir) / "avica.inp")
        global_params = PipeConfig(global_configfile).to_dict()
        params.update(global_params)
        param_sources.update(dict.fromkeys(global_params, "global"))

        user_configfile = Path(avica_data_dir) / "avica.inp"
        if user_configfile.exists():
            user_params = PipeConfig(user_configfile).to_dict()
            params.update(user_params)
            param_sources.update(dict.fromkeys(user_params, "user"))

        if not inpfile and not no_inpfile and Path(outfile).exists():
            inpfile = outfile
    else:
        if default:
            outfile = str(Path(avica_data_dir) / Path(outfile).name)

        if global_default:
            outfile = str(Path(avica_pkg_dir) / Path(outfile).name)

        params = {}
        param_sources = {}

    if inpfile:
        try:
            input_params = PipeConfig(inpfile).to_dict()
        except Exception as e:
            raise typer.BadParameter(f"Failed to read config file '{inpfile}': {e}") from e
        params.update(input_params)
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
        raise typer.BadParameter("No configuration to write. Provide either --inpfile or key=value arguments.")

    else:
        update_config(params=params, out=outfile, rj=1, lj=1)

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

    # Known only once the workdir exists; InitVariables sets the final path.
    result_csvfile = _resolve_run_csv(pipe_params) if (resume or resume_from) else None
    pipe_params["result_csv_file"] = str(result_csvfile) if result_csvfile else None

    # print(DEFAULT_PARAMS['allfitsfile'])
    main_pipeline = AvicaPipeline(pipe_params=pipe_params)

    main_pipeline.filter_steps(*steps)
    if resume_from:
        try:
            steps = main_pipeline.steps_from(resume_from)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--resume-from") from exc
    elif resume:
        if result_csvfile is None or not result_csvfile.exists():
            typer.echo(f"No result CSV found for target '{pipe_params['target']}'; running requested steps.")
        else:
            typer.echo(f"Resuming according to {result_csvfile}")
            resume_from = _infer_resume_step(result_csvfile, main_pipeline.step_names())

        if result_csvfile is not None and result_csvfile.exists() and resume_from is None:
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
    project: Annotated[Optional[str], typer.Option("--project", help="Project code, to pick among result CSVs of the same target.")] = None,
    workdir: Annotated[Optional[str], typer.Option("--workdir", help="Workdir name (e.g. wd, wd_2), to pick among result CSVs of the same target.")] = None,
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
        result_csvfile = _select_result_csv(pipe_params, project_code=project, workdir=workdir)

    if result_csvfile is None or not Path(result_csvfile).exists():
        where = result_csvfile or Path(pipe_params['target_dir']) / f"result__{pipe_params['target']}__*.csv"
        typer.echo(f"No result CSV found at {where}.", err=True)
        typer.echo("Run the pipeline first, or pass --csvfile.", err=True)
        raise typer.Exit(code=1)

    rows = read_result_csv(result_csvfile)
    label = _result_label(result_csvfile, target)

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
