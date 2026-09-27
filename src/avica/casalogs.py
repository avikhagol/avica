"""
One CASA log per pipeline run (issue #58).

Every CASA process started by a pipeline run -- the persistent (mpi)casa
workers and CASA tools imported into the AVICA process itself -- writes to a
single file in ``casa.logs/`` next to ``avica.logs/``::

    casa.logs/casa__log-YYYYmmdd_HHMMSS.log        CASA log
    casa.logs/err-casa__log-YYYYmmdd_HHMMSS.log    stderr / tracebacks

Each CASA task is preceded by a marker line (see `task_marker`) so the log can
be read on a terminal, e.g. ``grep -n '>>> avica' casa.logs/casa__log-*.log``.

Log files that CASA still creates with its default name (``casa-*.log``,
``ipython-*.log``) in the run directory during the run are appended to the run
log and removed by `collect_stray_logs` when the run ends (never mid-run, so
no live CASA process loses its open log file).

This module deliberately imports nothing heavy so it can be used from
`avica.ms.compat` at CASA import time.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

CASA_LOG_FOLDER = "casa.logs"
STRAY_LOG_PATTERNS = ("casa-*.log", "ipython-*.log")
MARKER_PREFIX = ">>> avica"

_state = {"logfile": None, "errfile": None, "started": None, "rundir": None}


def run_logfilenames(folder: str | Path = CASA_LOG_FOLDER,
                     stamp: Optional[datetime] = None) -> Tuple[Path, Path]:
    stamp = stamp or datetime.now()
    tag = stamp.strftime("%Y%m%d_%H%M%S")
    folder = Path(folder).absolute()
    return folder / f"casa__log-{tag}.log", folder / f"err-casa__log-{tag}.log"


def start_run(folder: str | Path = CASA_LOG_FOLDER, stamp: Optional[datetime] = None,
              header: str = "") -> Tuple[str, str]:
    """Create ``casa.logs/`` and register this run's CASA log + err file."""
    stamp = stamp or datetime.now()
    logfile, errfile = run_logfilenames(folder, stamp)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    _state.update(logfile=str(logfile), errfile=str(errfile),
                  started=stamp.timestamp(), rundir=str(Path.cwd()))
    with logfile.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp:%Y-%m-%d %H:%M:%S}\tINFO\tavica\t{MARKER_PREFIX} run started {header}\n")
    redirect_inprocess()
    return str(logfile), str(errfile)


def end_run() -> None:
    collect_stray_logs()
    _state.update(logfile=None, errfile=None, started=None, rundir=None)


def current_logfile() -> Optional[str]:
    return _state["logfile"]


def current_errfile() -> Optional[str]:
    return _state["errfile"]


def task_marker(step: str = "", task: str = "", detail: str = "") -> str:
    """One-line header written into the CASA log before each task."""
    parts = [MARKER_PREFIX]
    if step:
        parts.append(f"[{step}]")
    if task:
        parts.append(task)
    if detail:
        parts.append(detail)
    return " ".join(parts)


def _inprocess_casalog():
    if "casatasks" in sys.modules:
        from casatasks import casalog
        return casalog
    import casatools
    return casatools.logsink()


def redirect_inprocess() -> bool:
    """
    Point CASA tools already imported into this process at the run log.
    Called by `start_run` and by `avica.ms.compat` right after importing
    casatools. Does nothing outside a pipeline run or without casatools.
    """
    logfile = _state["logfile"]
    if not logfile or not ({"casatools", "casatasks"} & set(sys.modules)):
        return False
    try:
        sink = _inprocess_casalog()
        if sink.logfile() != logfile:
            sink.setlogfile(logfile)
    except Exception:
        return False
    # The default log created by the import is merged by `end_run`, once no
    # CASA process can still be writing to it.
    return True


def collect_stray_logs(directory: str | Path | None = None) -> list:
    """
    Append default-named CASA logs created in `directory` (the run directory)
    since the run started to the run log, then remove them. Returns the
    merged paths.
    """
    logfile, started = _state["logfile"], _state["started"]
    if not logfile or started is None:
        return []
    directory = Path(directory or _state["rundir"] or Path.cwd())
    merged = []
    for pattern in STRAY_LOG_PATTERNS:
        for stray in sorted(directory.glob(pattern)):
            try:
                if stray.resolve() == Path(logfile).resolve():
                    continue
                # only files this run created: never touch older logs
                if stray.stat().st_mtime < started - 1 or _created(stray) < started - 1:
                    continue
                content = stray.read_text(encoding="utf-8", errors="replace")
                with open(logfile, "a", encoding="utf-8") as fh:
                    if content.strip():
                        fh.write(f"{MARKER_PREFIX} ---- merged from {stray.name} ----\n")
                        fh.write(content if content.endswith("\n") else content + "\n")
                stray.unlink()
                merged.append(str(stray))
            except OSError:
                continue
    return merged


def _created(path: Path) -> float:
    st = path.stat()
    return getattr(st, "st_birthtime", None) or st.st_ctime
