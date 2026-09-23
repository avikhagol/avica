"""Band-correct GAIN_CURVE from ANTABs that carry one GAIN line per band.

The vendored JIVE ``append_gc`` ignores ``FREQ=`` on GAIN lines: every GAIN line
becomes its own GAIN_CURVE row and its DPFU/POLY is copied to all IFs. KVN (and
avica's own multi-band VLBA ANTAB) list one GAIN line per receiver band, so a
FITS-IDI file ends up with several conflicting rows per antenna.

`band_gain_curve` keeps ``append_gc`` unchanged: it runs it once per distinct IF
selection on a small skeleton copy of the FITS-IDI file, feeding only the GAIN
lines whose ``FREQ`` range contains those IFs, then splices each IF slot from the
matching run into one row per antenna. Whenever the selection is not unique it
returns None and the caller keeps the plain ``append_gc`` result.
"""

import logging
import re
import shutil
import tempfile
import warnings
from collections import Counter
from pathlib import Path
from typing import NamedTuple

import numpy as np
from astropy.io import fits

log = logging.getLogger("avica.pipeline")

_FREQ = re.compile(r"\bFREQ\s*=\s*([-+\d.eE]+)\s*,\s*([-+\d.eE]+)", re.I)
_UNSUPPORTED_GAIN = re.compile(r"\b(TABLE|GCNRAO)\b", re.I)
_SKELETON_HDUS = ('ARRAY_GEOMETRY', 'SOURCE', 'ANTENNA', 'FREQUENCY')
_KEYS = ('ANTENNA_NO', 'ARRAY', 'FREQID')
_PER_IF = ('TYPE', 'NTERM', 'X_TYP', 'Y_TYP', 'X_VAL', 'SENS')          # [NO_BAND]
_PER_IF_TAB = ('Y_VAL', 'GAIN')                                          # [NO_BAND * NO_TABS]


class AntabGroup(NamedTuple):
    kind: str           # 'GAIN', 'TSYS' or other keyin keyword
    antenna: str
    text: str           # verbatim text, including leading comments and TSYS rows


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


def if_centres_mhz(fitsfile):
    """IF centre frequencies of FREQID 1, or None if the file has several FREQIDs."""
    with fits.open(fitsfile, memmap=True, lazy_load_hdus=True) as hdul:
        freq = hdul['FREQUENCY']
        if len(freq.data) != 1:
            return None
        row = freq.data[0]
        names = freq.columns.names
        bandfreq = np.atleast_1d(row['BANDFREQ']).astype(float)
        width = np.atleast_1d(row['TOTAL_BANDWIDTH']).astype(float) if 'TOTAL_BANDWIDTH' in names else np.zeros_like(bandfreq)
        sideband = np.atleast_1d(row['SIDEBAND']) if 'SIDEBAND' in names else np.ones_like(bandfreq)
        ref = freq.header.get('REF_FREQ', hdul['ARRAY_GEOMETRY'].header.get('REF_FREQ'))
        centre = ref + bandfreq + np.where(sideband >= 0, width, -width) / 2
    return centre / 1e6


def _idi_antennas(fitsfile):
    """Antenna names as the JIVE IdiData antenna_map sees them."""
    with fits.open(fitsfile, memmap=True, lazy_load_hdus=True) as hdul:
        names = hdul['ARRAY_GEOMETRY'].data['ANNAME']
    return {(n.decode('ascii', errors='ignore').strip()[:2] if isinstance(n, bytes) else str(n).strip()).upper()
            for n in names}


def make_skeleton(fitsfile, out):
    """Small HDUs of `fitsfile` plus a one-row UV_DATA; enough for JIVE append_gc."""
    with fits.open(fitsfile, memmap=True, lazy_load_hdus=True) as hdul:
        hdus = [fits.PrimaryHDU(header=hdul[0].header.copy())]
        hdus += [fits.BinTableHDU(data=hdul[name].data.copy(), header=hdul[name].header.copy())
                 for name in _SKELETON_HDUS if name in hdul]
    hdus.append(fits.BinTableHDU.from_columns([fits.Column(name='DATE', format='1D', array=[0.0]),
                                               fits.Column(name='TIME', format='1D', array=[0.0]),
                                               fits.Column(name='SOURCE', format='1J', array=[1])],
                                              name='UV_DATA'))
    fits.HDUList(hdus).writeto(out, overwrite=True)


def _fallback(msg):
    msg = f"{msg}; keeping the plain append_gc GAIN_CURVE"
    log.warning(msg)
    warnings.warn(msg, RuntimeWarning)
    return None


def band_gain_curve(antabfile, fitsfile, append_gc, workdir=None):
    """Return a band-correct GAIN_CURVE BinTableHDU for `fitsfile`, or None.

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
    try:
        return _band_gain_curve(antabfile, fitsfile, append_gc, workdir, gains)
    except Exception as exc:
        return _fallback(f"band-correct GAIN_CURVE failed for {Path(fitsfile).name}: {exc}")


def _band_gain_curve(antabfile, fitsfile, append_gc, workdir, gains):
    if any(_UNSUPPORTED_GAIN.search(g.text) for g in gains):
        return _fallback(f"ANTAB {antabfile}: tabulated GAIN entries cannot be split per band")

    centres = if_centres_mhz(fitsfile)
    if centres is None:
        return _fallback(f"{Path(fitsfile).name}: several FREQIDs")
    known = _idi_antennas(fitsfile)
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
            with fits.open(staged) as hdul:
                runs[chosen] = hdul['GAIN_CURVE'].copy()

    hdu = _splice(runs, selections)
    log.info("band-correct GAIN_CURVE for %s: %d antennas, %d IF selections from %s",
             Path(fitsfile).name, len(hdu.data), len(runs), antabfile)
    return hdu


def _row_keys(hdu):
    return [tuple(int(row[k]) for k in _KEYS) for row in hdu.data]


def _stem(name):
    return name[:-2] if name[-2:] in ('_1', '_2') else name


def _splice(runs, selections):
    """One row per antenna: IF slot i comes from the run selected for IF i."""
    first = runs[selections[0]]
    keys = _row_keys(first)
    for hdu in runs.values():
        run_keys = _row_keys(hdu)
        if len(set(run_keys)) != len(run_keys) or set(run_keys) != set(keys):
            raise ValueError("append_gc produced inconsistent GAIN_CURVE rows per band")
    n_band = len(selections)
    n_tab = max(int(hdu.header['NO_TABS']) for hdu in runs.values())
    names = list(dict.fromkeys(n for hdu in runs.values() for n in hdu.columns.names))

    def source(hdu, name):
        # A single-DPFU GAIN line is the common curve for both hands (as merge_calibration assumes).
        return name if name in hdu.columns.names else name[:-1] + '1'

    columns = []
    for name in names:
        template = next(hdu.columns[name] for hdu in runs.values() if name in hdu.columns.names)
        stem, letter = _stem(name), template.format.format
        if name in _KEYS:
            array, fmt = np.array([k[_KEYS.index(name)] for k in keys]), f'1{letter}'
        elif stem in _PER_IF:
            array = np.zeros((len(keys), n_band), dtype=np.asarray(first.data[source(first, name)]).dtype)
            for i, chosen in enumerate(selections):
                hdu = runs[chosen]
                index = {k: j for j, k in enumerate(_row_keys(hdu))}
                values = np.asarray(hdu.data[source(hdu, name)]).reshape(len(hdu.data), n_band)
                array[:, i] = [values[index[k], i] for k in keys]
            fmt = f'{n_band}{letter}'
        elif stem in _PER_IF_TAB:
            array = np.full((len(keys), n_band, n_tab), np.nan if stem == 'Y_VAL' else 0.0)
            for i, chosen in enumerate(selections):
                hdu = runs[chosen]
                tabs = int(hdu.header['NO_TABS'])
                index = {k: j for j, k in enumerate(_row_keys(hdu))}
                values = np.asarray(hdu.data[source(hdu, name)]).reshape(len(hdu.data), n_band, tabs)
                array[:, i, :tabs] = [values[index[k], i] for k in keys]
            array, fmt = array.reshape(len(keys), n_band * n_tab), f'{n_band * n_tab}{letter}'
        else:
            raise ValueError(f"unexpected GAIN_CURVE column {name}")
        columns.append(fits.Column(name=name, format=fmt, unit=template.unit, array=array))

    header = first.header.copy()
    for key in ('NAXIS1', 'NAXIS2', 'TFIELDS'):
        header.remove(key, ignore_missing=True)
    header['NO_TABS'] = n_tab
    header['NO_POL'] = max(int(hdu.header.get('NO_POL', 1)) for hdu in runs.values())
    hdu = fits.BinTableHDU.from_columns(columns, name='GAIN_CURVE')
    for card in header.cards:
        if not card.keyword.startswith(('TTYPE', 'TFORM', 'TUNIT', 'TDIM', 'XTENSION', 'BITPIX',
                                        'NAXIS', 'PCOUNT', 'GCOUNT', 'TFIELDS')):
            hdu.header[card.keyword] = (card.value, card.comment)
    return hdu


def write_gain_curve(fitsfile, hdu):
    """Replace or append GAIN_CURVE the way JIVE append_gc does."""
    with fits.open(fitsfile, memmap=True, lazy_load_hdus=True) as hdul:
        present = 'GAIN_CURVE' in hdul
    if present:
        fits.update(fitsfile, hdu.data, hdu.header, 'GAIN_CURVE')
    else:
        fits.append(fitsfile, hdu.data, hdu.header)
