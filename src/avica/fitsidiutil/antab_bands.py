"""Band-correct GAIN_CURVE from ANTABs that carry one GAIN line per band.

The vendored JIVE ``append_gc`` ignores ``FREQ=`` on GAIN lines: every GAIN line
becomes its own GAIN_CURVE row and its DPFU/POLY is copied to all IFs. KVN (and
avica's own multi-band VLBA ANTAB) list one GAIN line per receiver band, so a
FITS-IDI file ends up with several conflicting rows per antenna.

`band_gain_curve` keeps ``append_gc`` unchanged: it runs it once per distinct IF
selection on a small copy of the FITS-IDI file (`FITSIDI.save_as` with one
UV_DATA row), feeding only the GAIN lines whose ``FREQ`` range contains those
IFs, then splices each IF slot from the matching run into one row per antenna.
Whenever the selection is not unique it returns None and the caller keeps the
plain ``append_gc`` result.

All FITS access here goes through `avica.fitsidiutil` (CFITSIO); only the
vendored JIVE code uses astropy.
"""

import logging
import re
import shutil
import tempfile
import warnings
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, NamedTuple, Tuple

import numpy as np

from .core import ReadIO
from .io import FITSIDI, I, F, L, read_idi

log = logging.getLogger("avica.pipeline")

_FREQ = re.compile(r"\bFREQ\s*=\s*([-+\d.eE]+)\s*,\s*([-+\d.eE]+)", re.I)
_UNSUPPORTED_GAIN = re.compile(r"\b(TABLE|GCNRAO)\b", re.I)
_KEYS = ('ANTENNA_NO', 'ARRAY', 'FREQID')
_PER_IF = ('TYPE', 'NTERM', 'X_TYP', 'Y_TYP', 'X_VAL', 'SENS')          # [NO_BAND]
_PER_IF_TAB = ('Y_VAL', 'GAIN')                                          # [NO_BAND * NO_TABS]
_SKELETON_NEEDS = ('ARRAY_GEOMETRY', 'SOURCE', 'FREQUENCY', 'UV_DATA')
_STRUCTURAL = re.compile(r"^(XTENSION|BITPIX|NAXIS\d*|PCOUNT|GCOUNT|TFIELDS|EXTNAME|"
                         r"TTYPE\d+|TFORM\d+|TUNIT\d+|TDIM\d+|TNULL\d+|TSCAL\d+|TZERO\d+|THEAP|END)$")


class AntabGroup(NamedTuple):
    kind: str           # 'GAIN', 'TSYS' or other keyin keyword
    antenna: str
    text: str           # verbatim text, including leading comments and TSYS rows


@dataclass
class CalTable:
    """A binary table independent of any FITS library; vectors are rows-first 2-D arrays."""
    name: str
    columns: Dict[str, np.ndarray]
    formats: Dict[str, str]                                   # TFORM, e.g. '4J'
    units: Dict[str, str] = field(default_factory=dict)
    header: List[Tuple[str, object, str]] = field(default_factory=list)   # (key, value, comment)

    @property
    def nrows(self):
        return len(next(iter(self.columns.values()))) if self.columns else 0

    def get(self, key, default=None):
        return next((value for k, value, _ in self.header if k == key), default)


# ------------------------------------------------------------------ ANTAB text

def _body(line):
    return line.split('!', 1)[0].strip()


def antab_groups(text):
    """Split ANTAB text into keyin groups; a TSYS group keeps its rows up to the closing '/'."""
    groups, lines, header, in_rows = [], [], [], False
    for line in text.splitlines(keepends=True):
        lines.append(line)
        body = _body(line)
        if not body:
            continue
        if in_rows:
            if body.endswith('/'):
                groups.append(_group(header, lines))
                lines, header, in_rows = [], [], False
            continue
        header.append(body)
        if body.endswith('/'):
            if header[0].split()[0].upper() == 'TSYS':
                in_rows = True
                continue
            groups.append(_group(header, lines))
            lines, header = [], []
    if header or in_rows:
        raise ValueError("Unterminated ANTAB header or TSYS block")
    return groups


def _group(header, lines):
    tokens = ' '.join(header).replace('/', ' ').split()
    kind = tokens[0].upper()
    antenna = tokens[1].strip("'\"").upper() if len(tokens) > 1 else ''
    return AntabGroup(kind, antenna, ''.join(lines))


def _gain_freq(group):
    """(lo, hi) in MHz, or None when the GAIN line applies to every frequency."""
    match = _FREQ.search(' '.join(_body(l) for l in group.text.splitlines()))
    return (float(match[1]), float(match[2])) if match else None


# ------------------------------------------------------------------ FITS-IDI access (fitsidiutil)

def _require(hdul, fitsfile, names):
    missing = [n for n in names if n not in hdul.names]
    if missing:
        raise IOError(f"{fitsfile}: missing HDU(s) {', '.join(missing)} (read gave {hdul.names})")


def if_centres_mhz(fitsfile, hdul=None):
    """IF centre frequencies of FREQID 1, or None if the file has several FREQIDs."""
    hdul = read_idi(str(fitsfile), hdus=['FREQUENCY']) if hdul is None else hdul
    _require(hdul, fitsfile, ['FREQUENCY'])
    freq = hdul['FREQUENCY']
    if freq.nrows != 1:
        return None
    bandfreq = np.atleast_2d(np.asarray(freq['BANDFREQ'], dtype=float))[0]
    width = (np.atleast_2d(np.asarray(freq['TOTAL_BANDWIDTH'], dtype=float))[0]
             if 'TOTAL_BANDWIDTH' in freq.cols else np.zeros_like(bandfreq))
    sideband = (np.atleast_2d(freq.typed('SIDEBAND'))[0]
                if 'SIDEBAND' in freq.cols else np.ones_like(bandfreq))
    ref = freq.header.get('REF_FREQ', hdul['ARRAY_GEOMETRY'].header.get('REF_FREQ')
                          if 'ARRAY_GEOMETRY' in hdul.names else None)
    centre = float(ref) + bandfreq + np.where(sideband >= 0, width, -width) / 2
    return centre / 1e6


def _idi_antennas(fitsfile, hdul=None):
    """Antenna names as the JIVE IdiData antenna_map sees them."""
    hdul = read_idi(str(fitsfile), hdus=['ARRAY_GEOMETRY']) if hdul is None else hdul
    _require(hdul, fitsfile, ['ARRAY_GEOMETRY'])
    return {(n.decode('ascii', errors='ignore').strip()[:2] if isinstance(n, bytes) else str(n).strip()).upper()
            for n in hdul['ARRAY_GEOMETRY']['ANNAME']}


def make_skeleton(fitsfile, out):
    """Copy of `fitsfile` with every HDU but a single UV_DATA row; enough for JIVE append_gc."""
    with FITSIDI(str(fitsfile)).open('r') as fo:
        fo.read(hdus=['UV_DATA'])
        fo.save_as(str(out))
    _require(read_idi(str(out), hdus=[]), out, _SKELETON_NEEDS)


def read_cal_table(fitsfile, name):
    """Read one binary table into a CalTable, restoring integer columns from TFORM."""
    hdul = read_idi(str(fitsfile), hdus=[name])
    _require(hdul, fitsfile, [name])
    hdu = hdul[name]
    formats = {col: f"{repeat}{code}" for col, (repeat, code) in hdu.column_formats.items()}
    tfields = int(hdu.header.get('TFIELDS', 0) or 0)
    units = {str(hdu.header.get(f'TTYPE{n}')).strip(): str(hdu.header.get(f'TUNIT{n}', '') or '').strip()
             for n in range(1, tfields + 1)}
    header = []
    for card in hdu.header:
        key = card['key']
        if _STRUCTURAL.match(key):
            continue
        value = card['value']
        if card.get('dtype') == L:
            value = str(value).strip().upper().startswith('T')
        elif card.get('dtype') == I:
            value = int(value)
        elif card.get('dtype') == F:
            value = float(value)
        header.append((key, value, card.get('comment', '') or ''))
    columns = {col: hdu.typed(col) for col in formats} if hdu.nrows else {col: np.array([]) for col in formats}
    return CalTable(name, columns, formats, units, header)


def write_gain_curve(fitsfile, table):
    """Replace (or append) GAIN_CURVE in place via fitsidiutil; later HDUs are shifted, not the file."""
    with FITSIDI(str(fitsfile), mode='w').open('w') as fo:
        fo.replace_table(table.name,
                         [(name, table.formats[name], table.units.get(name, '')) for name in table.columns],
                         table.columns, table.header)


# ------------------------------------------------------------------ band-correct gain curve

def _fallback(msg):
    msg = f"{msg}; keeping the plain append_gc GAIN_CURVE"
    log.warning(msg)
    warnings.warn(msg, RuntimeWarning)
    return None


def band_gain_curve(antabfile, fitsfile, append_gc, workdir=None):
    """Return a band-correct GAIN_CURVE `CalTable` for `fitsfile`, or None.

    None means the plain `append_gc` result is already right (at most one GAIN
    line per antenna) or the per-IF selection is not unique; the caller then
    keeps the existing behaviour. Unexpected failures also fall back.
    """
    try:
        gains = [g for g in antab_groups(Path(antabfile).read_text()) if g.kind == 'GAIN']
    except ValueError as exc:
        return _fallback(f"ANTAB {antabfile}: {exc}")
    per_antenna = Counter(g.antenna for g in gains)
    if not gains or max(per_antenna.values()) < 2:
        return None
    if not hasattr(ReadIO, 'replace_table'):
        return _fallback("the compiled avica.fitsidiutil extension has no replace_table "
                         "(rebuild/reinstall avica)")
    try:
        return _band_gain_curve(antabfile, fitsfile, append_gc, workdir, gains)
    except Exception as exc:
        return _fallback(f"band-correct GAIN_CURVE failed for {Path(fitsfile).name}: {exc}")


def _band_gain_curve(antabfile, fitsfile, append_gc, workdir, gains):
    if any(_UNSUPPORTED_GAIN.search(g.text) for g in gains):
        return _fallback(f"ANTAB {antabfile}: tabulated GAIN entries cannot be split per band")

    hdul = read_idi(str(fitsfile), hdus=['FREQUENCY', 'ARRAY_GEOMETRY'])
    centres = if_centres_mhz(fitsfile, hdul=hdul)
    if centres is None:
        return _fallback(f"{Path(fitsfile).name}: several FREQIDs")
    known = _idi_antennas(fitsfile, hdul=hdul)
    gains = [g for g in gains if g.antenna in known]
    antennas = sorted({g.antenna for g in gains})
    if not gains:
        return None

    selections = []                                 # per IF: indices into gains
    for i, centre in enumerate(centres):
        chosen = tuple(k for k, g in enumerate(gains)
                       if (_gain_freq(g) is None or _gain_freq(g)[0] <= centre <= _gain_freq(g)[1]))
        counts = Counter(gains[k].antenna for k in chosen)
        bad = [an for an in antennas if counts[an] != 1]
        if bad:
            return _fallback(f"ANTAB {antabfile}: IF{i + 1} ({centre:.1f} MHz) matches "
                             + ', '.join(f"{an}:{counts[an]}" for an in bad) + " GAIN entries")
        selections.append(chosen)

    runs = {}
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        skeleton = Path(tmp) / 'skeleton.fits'
        make_skeleton(fitsfile, skeleton)
        for n, chosen in enumerate(dict.fromkeys(selections)):
            antab = Path(tmp) / f'gain_{n}.antab'
            antab.write_text(''.join(gains[k].text for k in chosen))
            staged = Path(tmp) / f'gain_{n}.fits'
            shutil.copy(skeleton, staged)
            append_gc(antabfile=str(antab), idifile=str(staged), replace=True)
            runs[chosen] = read_cal_table(staged, 'GAIN_CURVE')

    table = _splice(runs, selections)
    log.info("band-correct GAIN_CURVE for %s: %d antennas, %d IF selections from %s",
             Path(fitsfile).name, table.nrows, len(runs), antabfile)
    return table


def _row_keys(table):
    return [tuple(int(v) for v in row) for row in zip(*(table.columns[k] for k in _KEYS))]


def _stem(name):
    return name[:-2] if name[-2:] in ('_1', '_2') else name


def _splice(runs, selections):
    """One row per antenna: IF slot i comes from the run selected for IF i."""
    first = runs[selections[0]]
    keys = _row_keys(first)
    for table in runs.values():
        run_keys = _row_keys(table)
        if len(set(run_keys)) != len(run_keys) or set(run_keys) != set(keys):
            raise ValueError("append_gc produced inconsistent GAIN_CURVE rows per band")
    n_band = len(selections)
    n_tab = max(int(t.get('NO_TABS', 1)) for t in runs.values())
    names = list(dict.fromkeys(n for t in runs.values() for n in t.columns))

    def source(table, name):
        # A single-DPFU GAIN line is the common curve for both hands (as merge_calibration assumes).
        return name if name in table.columns else name[:-1] + '1'

    def index(table):
        return {k: j for j, k in enumerate(_row_keys(table))}

    columns, formats, units = {}, {}, {}
    for name in names:
        template = next(t for t in runs.values() if name in t.columns)
        stem, code = _stem(name), template.formats[name].lstrip('0123456789')
        units[name] = template.units.get(name, '')
        if name in _KEYS:
            columns[name], formats[name] = np.array([k[_KEYS.index(name)] for k in keys], dtype=np.int64), f'1{code}'
        elif stem in _PER_IF:
            array = np.zeros((len(keys), n_band), dtype=np.asarray(first.columns[source(first, name)]).dtype)
            for i, chosen in enumerate(selections):
                table = runs[chosen]
                values = np.asarray(table.columns[source(table, name)]).reshape(table.nrows, n_band)
                rows = index(table)
                array[:, i] = [values[rows[k], i] for k in keys]
            columns[name], formats[name] = array, f'{n_band}{code}'
        elif stem in _PER_IF_TAB:
            array = np.full((len(keys), n_band, n_tab), np.nan if stem == 'Y_VAL' else 0.0)
            for i, chosen in enumerate(selections):
                table = runs[chosen]
                tabs = int(table.get('NO_TABS', 1))
                values = np.asarray(table.columns[source(table, name)], dtype=float).reshape(table.nrows, n_band, tabs)
                rows = index(table)
                array[:, i, :tabs] = [values[rows[k], i] for k in keys]
            columns[name], formats[name] = array.reshape(len(keys), n_band * n_tab), f'{n_band * n_tab}{code}'
        else:
            raise ValueError(f"unexpected GAIN_CURVE column {name}")

    header = [(k, v, c) for k, v, c in first.header if k not in ('NO_TABS', 'NO_POL')]
    header += [('NO_POL', max(int(t.get('NO_POL', 1)) for t in runs.values()), ''),
               ('NO_TABS', n_tab, '')]
    return CalTable(first.name, columns, formats, units, header)
