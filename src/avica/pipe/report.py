"""
Rendering of AVICA pipeline result CSVs.

A result CSV is written incrementally by `append_step_result_csv()` in
avica.pipe.core, one row per step attempt, with the column layout of
`StepResult`:

    name, success_count, failed_count, start_stamp, detail, desc, success, end_stamp

The file is APPEND-ONLY: re-running a step appends a further row, so a step
name may appear several times.  `latest_per_step()` collapses to the most
recent attempt; `render_history()` shows every attempt.

Four layouts are provided:

    render_ladder()   one row per pipeline step in canonical order, with a
                      status tally and the command needed to resume
    render_detail()   full `desc` text in panels, for steps that did not
                      fully succeed
    render_history()  every attempt of every step, grouped by step
    render_oneline()  a single compact status line, for scripts and CI

`render_result()` composes them according to the flags passed by
`avica pipe result`.

Reading uses the standard-library csv module so that inspecting a result file
never requires the heavier pipeline imports.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from avica.pipe.config import CSV_POPULATED_STEPS

__all__ = [
    "read_result_csv",
    "classify",
    "latest_per_step",
    "resume_step",
    "render_result",
    "render_ladder",
    "render_detail",
    "render_history",
    "render_oneline",
]

# Status -> (glyph, rich style).  Mirrors the source_colours map used by
# `avica pipe config --summary`, so colour carries meaning rather than decoration.
STATUS_STYLE = {
    "ok":      ("✔", "green"),
    "partial": ("⚠", "yellow"),
    "failed":  ("✘", "yellow"),
    "pending": ("·", "yellow"),
}

DIM = "white"
WARN = "yellow"
DASH = "–"


# ______________________________________________________________________________
#
#                                   reading
# ______________________________________________________________________________

def _json_cell(value):
    """`detail`, `desc` and `success` are JSON-encoded on write, or empty."""
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _stamp(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def read_result_csv(csvfile) -> List[Dict]:
    """
    Read every attempt recorded in a result CSV, oldest first.

    Returns an empty list when the file is missing or has no usable rows, so
    callers can distinguish "nothing ran" from "something failed".
    """
    path = Path(csvfile)
    if not path.exists():
        return []

    rows: List[Dict] = []
    with open(path, newline="") as fh:
        for raw in csv.DictReader(fh):
            if not raw.get("name"):
                continue
            rows.append({
                "name":          raw["name"],
                "success_count": _int(raw.get("success_count")),
                "failed_count":  _int(raw.get("failed_count")),
                "start_stamp":   _stamp(raw.get("start_stamp")),
                "end_stamp":     _stamp(raw.get("end_stamp")),
                "detail":        _json_cell(raw.get("detail")),
                "desc":          _json_cell(raw.get("desc")) or [],
                "success":       _json_cell(raw.get("success")) or [],
            })
    return rows


def classify(row: Optional[Dict]) -> str:
    """
    Status of a single attempt.

    'ok' is the same condition as cli_new._is_successful_result(); 'partial'
    additionally distinguishes a step that produced some output but also
    recorded failures, which a success/fail flag alone cannot express.
    """
    if row is None:
        return "pending"

    ok, bad = row["success_count"], row["failed_count"]
    if ok > 0 and bad == 0:
        return "ok"
    if ok > 0 and bad > 0:
        return "partial"
    if bad > 0:
        return "failed"
    return "pending"


def latest_per_step(rows: List[Dict]) -> Dict[str, Dict]:
    """Collapse the append-only log to the most recent attempt of each step."""
    latest: Dict[str, Dict] = {}
    for row in rows:
        latest[row["name"]] = row
    return latest


def attempt_counts(rows: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["name"]] = counts.get(row["name"], 0) + 1
    return counts


def effective_steps(rows: List[Dict]) -> List[str]:
    """
    Canonical pipeline order, followed by any step present in the CSV that is
    not part of the current pipeline (e.g. rows left by a step since disabled).
    """
    extra = [
        name for name in dict.fromkeys(row["name"] for row in rows)
        if name not in CSV_POPULATED_STEPS
    ]
    return [*CSV_POPULATED_STEPS, *extra]


def resume_step(rows: List[Dict]) -> Optional[str]:
    """
    First pipeline step that has not completed successfully, i.e. the step
    `avica pipe run --resume` would start from.  None when all steps are done.
    """
    latest = latest_per_step(rows)
    for step in CSV_POPULATED_STEPS:
        if classify(latest.get(step)) != "ok":
            return step
    return None


# ______________________________________________________________________________
#
#                                 formatting
# ______________________________________________________________________________

def fmt_duration(row: Dict) -> str:
    start, end = row["start_stamp"], row["end_stamp"]
    if not start or not end:
        return DASH

    secs = (end - start).total_seconds()
    if secs < 0:
        return DASH
    if secs < 60:
        return f"{secs:.1f} s"
    if secs < 3600:
        return f"{int(secs // 60)}m {int(secs % 60):02d}s"
    return f"{int(secs // 3600)}h {int((secs % 3600) // 60):02d}m"


def fmt_stamp(stamp: Optional[datetime], with_date: bool = False) -> str:
    if not stamp:
        return DASH
    return stamp.strftime("%m-%d %H:%M:%S" if with_date else "%H:%M:%S")


def fmt_items(success, limit: int = 12) -> Text:
    """
    Per-item pass/fail strip built from the `success` list, e.g. OK OK X OK.

    This is the only place the per-item outcome is visible; the counts alone
    cannot say *which* band or file failed.
    """
    if not isinstance(success, list) or not success:
        return Text(DASH, style=DIM)

    out = Text()
    for flag in success[:limit]:
        out.append("✔" if flag else "✘", style="green" if flag else WARN)
    if len(success) > limit:
        out.append(f" +{len(success) - limit}", style=DIM)
    return out


def condense(desc, width: int = 60) -> str:
    """Collapse a `desc` list to one short line, for a table cell."""
    if not desc:
        return ""

    text = desc[0] if isinstance(desc, list) else desc
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 1] + "…"


# ______________________________________________________________________________
#
#                          layout A  --  progress ladder
# ______________________________________________________________________________

#: Width below which the ladder drops its `Note` column rather than letting
#: rich squeeze every other column to fit it.  Failure text is still shown in
#: full by render_detail(), so nothing is lost on a narrow terminal.
NOTE_MIN_WIDTH = 140


def render_ladder(console: Console, rows: List[Dict], target: str = "",
                  note: Optional[bool] = None) -> None:
    """
    One row per pipeline step, in canonical order rather than CSV order, so
    steps that never ran are shown as pending instead of being absent.

    `note` defaults to showing the condensed failure note only when the
    terminal is wide enough to carry it.
    """
    if note is None:
        note = console.width >= NOTE_MIN_WIDTH

    latest = latest_per_step(rows)
    attempts = attempt_counts(rows)
    steps = effective_steps(rows)

    table = Table(
        title=f"AVICA pipeline result{f' — {target}' if target else ''}",
        header_style="bold",
        show_lines=False,
        row_styles=["", ""],
    )
    table.add_column("#", style=DIM, justify="right", no_wrap=True)
    table.add_column("Step", style="bold cyan", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("ok", justify="right", no_wrap=True)
    table.add_column("failed", justify="right", no_wrap=True)
    table.add_column("Items", no_wrap=True)
    table.add_column("Duration", justify="right", no_wrap=True)
    table.add_column("Finished", no_wrap=True)
    if note:
        table.add_column("Note", overflow="ellipsis")

    tally = dict.fromkeys(STATUS_STYLE, 0)

    for idx, step in enumerate(steps, start=1):
        row = latest.get(step)
        status = classify(row)
        tally[status] += 1
        glyph, colour = STATUS_STYLE[status]

        label = f"{glyph} {status}"
        tries = attempts.get(step, 0)
        if tries > 1:
            label += f" ({tries}×)"

        if row is None:
            cells = [
                Text(step, style=DIM),
                Text(label, style=colour),
                *(Text(DASH, style=DIM) for _ in range(5)),
            ]
            note_cell = Text("")
        else:
            cells = [
                Text(step),
                Text(label, style=colour),
                Text(str(row["success_count"]),
                     style="green" if row["success_count"] else DIM),
                Text(str(row["failed_count"]),
                     style=WARN if row["failed_count"] else DIM),
                fmt_items(row["success"]),
                Text(fmt_duration(row)),
                Text(fmt_stamp(row["end_stamp"])),
            ]
            note_cell = Text(condense(row["desc"]),
                             style=WARN if row["failed_count"] else DIM)

        table.add_row(str(idx), *cells, *([note_cell] if note else []))

    console.print(table)
    _render_footer(console, rows, tally)


def _render_footer(console: Console, rows: List[Dict], tally: Dict[str, int]) -> None:
    """Status tally plus the command that continues the run."""
    parts = []
    for status in ("ok", "partial", "failed", "pending"):
        if tally.get(status):
            glyph, colour = STATUS_STYLE[status]
            parts.append(f"[{colour}]{glyph} {tally[status]} {status}[/{colour}]")
    if parts:
        console.print("  " + "   ".join(parts))

    nxt = resume_step(rows)
    if nxt:
        console.print(
            f"  [bold]▸ resume:[/bold] "
            f"[cyan]avica pipe run --resume-from {nxt}[/cyan]"
        )
    else:
        console.print("  [green]▸ all pipeline steps completed successfully[/green]")


# ______________________________________________________________________________
#
#                          layout B  --  failure detail
# ______________________________________________________________________________

def render_detail(console: Console, rows: List[Dict], target: str = "") -> None:
    """
    Full `desc` text for every step that did not fully succeed, one panel each.

    `desc` holds complete exception traces; rendering it in a table cell would
    dictate the width of every other column, so it is given its own block.
    """
    latest = latest_per_step(rows)
    problems = [
        (step, latest[step])
        for step in effective_steps(rows)
        if step in latest and classify(latest[step]) in ("failed", "partial")
    ]

    if not problems:
        return

    for step, row in problems:
        glyph, colour = STATUS_STYLE[classify(row)]

        body = Text()
        for i, message in enumerate(row["desc"] or ["(no description recorded)"]):
            if i:
                body.append("\n\n")
            body.append(" ".join(str(message).split()))

        console.print(Panel(
            body,
            title=(f"[{colour}]{glyph} {step}[/{colour}] — "
                   f"{row['failed_count']} failed / {row['success_count']} ok"),
            title_align="left",
            border_style=colour,
            padding=(0, 1),
        ))


# ______________________________________________________________________________
#
#                          layout C  --  run history
# ______________________________________________________________________________

def render_history(console: Console, rows: List[Dict], target: str = "") -> None:
    """
    Every recorded attempt, grouped by step.  The step name is printed only on
    the first row of each group and groups are separated by a rule, following
    the grouping style of `avica pipe config --summary`.
    """
    table = Table(
        title=f"AVICA run history{f' — {target}' if target else ''}",
        header_style="bold",
        show_lines=False,
    )
    table.add_column("Step", style="bold cyan", no_wrap=True)
    table.add_column("Try", justify="right", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("ok", justify="right", no_wrap=True)
    table.add_column("failed", justify="right", no_wrap=True)
    table.add_column("Duration", justify="right", no_wrap=True)
    table.add_column("Started", no_wrap=True)
    table.add_column("Note", overflow="ellipsis")

    by_step: Dict[str, List[Dict]] = {}
    for row in rows:
        by_step.setdefault(row["name"], []).append(row)

    for step in effective_steps(rows):
        attempts = by_step.get(step)
        if not attempts:
            continue

        for i, row in enumerate(attempts, start=1):
            glyph, colour = STATUS_STYLE[classify(row)]
            table.add_row(
                step if i == 1 else "",
                str(i),
                Text(f"{glyph} {classify(row)}", style=colour),
                Text(str(row["success_count"]),
                     style="green" if row["success_count"] else DIM),
                Text(str(row["failed_count"]),
                     style=WARN if row["failed_count"] else DIM),
                fmt_duration(row),
                fmt_stamp(row["start_stamp"], with_date=True),
                Text(condense(row["desc"], 50),
                     style=WARN if row["failed_count"] else DIM),
            )
        table.add_section()

    console.print(table)


# ______________________________________________________________________________
#
#                          layout D  --  one-line status
# ______________________________________________________________________________

def render_oneline(console: Console, rows: List[Dict], target: str = "") -> None:
    """A single line: per-step glyph strip, tally, and the next step to run."""
    latest = latest_per_step(rows)
    steps = effective_steps(rows)
    tally = dict.fromkeys(STATUS_STYLE, 0)

    strip = Text()
    for step in steps:
        status = classify(latest.get(step))
        tally[status] += 1
        glyph, colour = STATUS_STYLE[status]
        strip.append(glyph, style=colour)

    line = Text()
    line.append(f"{target or 'pipeline'} ", style="bold cyan")
    line.append_text(strip)
    line.append(f"  {tally['ok']}/{len(steps)} ok")
    for status, style in (("partial", "yellow"), ("failed", WARN), ("pending", DIM)):
        if tally[status]:
            line.append(f", {tally[status]} {status}", style=style)

    nxt = resume_step(rows)
    if nxt:
        line.append(f"  → next: {nxt}", style="bold")

    console.print(line)


# ______________________________________________________________________________
#
#                                 composition
# ______________________________________________________________________________

def render_result(rows: List[Dict], target: str = "", history: bool = False,
                  oneline: bool = False, detail: bool = True,
                  console: Optional[Console] = None) -> None:
    """
    Render a result CSV according to the flags of `avica pipe result`.

    oneline   a single status line, and nothing else
    history   every attempt, instead of the collapsed ladder
    detail    append failure panels when a step did not fully succeed
    """
    console = console or Console()

    if oneline:
        render_oneline(console, rows, target)
        return

    if history:
        render_history(console, rows, target)
    else:
        render_ladder(console, rows, target)

    if detail:
        render_detail(console, rows, target)
