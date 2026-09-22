"""Discover station UVFLG artifacts and build additive CASA manual flags.

Uses the JIVE keyin parser also used by casavlbitools.convert_flags. TIMEOFF
and DTIMRANG follow AIPS UVFLG INTEXT semantics (seconds, persistent nonzero
values): https://www.aips.nrao.edu/cgi-bin/ZXHLP2.PL?UVFLG
Unsupported selectors are rejected rather than silently broadening a flag.
"""
from datetime import datetime, timedelta
from calendar import isleap
from io import StringIO
from pathlib import Path
import logging
import math
import re

import numpy as np
from astropy.io import fits
from astropy.time import Time

from avica.external.jive.casavlbitools.key import read_keyfile
from avica.pipe.helpers import casa_quote, normalize_strlist

FLAG_EXTENSIONS = '.fg;.uvflag;.uvflg;.uvfg;.flag;.flg;.uvflags;.uvflgs;.uvfgs;.flags;.flgs'
log = logging.getLogger('avica.pipeline')


def discover_flagfiles(directories, extensions=FLAG_EXTENSIONS, explicit=None):
    """Explicit files override discovery; each resolved path is visited once."""
    supplied = normalize_strlist(explicit)
    if supplied:
        return sorted({Path(p).expanduser().resolve() for p in supplied})
    extensions = extensions.split(';') if isinstance(extensions, str) else extensions
    suffixes = {'.' + str(ext).strip().lstrip('.').lower() for ext in extensions if str(ext).strip()}
    found = set()
    for directory in normalize_strlist(directories):
        directory = Path(directory).expanduser()
        if directory.is_dir():
            found.update(p.resolve() for p in directory.iterdir()
                         if p.is_file() and p.suffix.lower() in suffixes)
    return sorted(found)


def read_uvflg(path):
    text = Path(path).read_text()
    # Preserve ! and / inside quoted reasons. Reject unterminated input, which
    # the vendored parser otherwise silently drops at EOF.
    tokens = re.findall(r"'[^'\n]*'|\"[^\"\n]*\"|![^\n]*|[^'\"!]", text)
    clean = ''.join(token for token in tokens if not token.startswith('!'))
    if clean.strip() and not clean.rstrip().endswith('/'):
        raise ValueError('unterminated UVFLG entry (missing /)')
    records = [dict(group) for group in read_keyfile(StringIO(clean + '\n'))]
    timing = {'TIMEOFF': 0.0, 'DTIMRANG': 0.0}
    for row in records:
        for key in timing:
            if key in row and row[key] != 0:
                timing[key] = row[key]
        row.update(timing)
    return records


def fits_flag_contexts(fitsfiles):
    """Read antennas, IF dimensions and actual UV time ranges per input file."""
    contexts = []
    for filename in fitsfiles:
        with fits.open(filename, memmap=True) as hdus:
            geometry = hdus['ARRAY_GEOMETRY'] if 'ARRAY_GEOMETRY' in hdus else hdus['ANTENNA']
            antennas = {str(name).strip().upper(): str(name).strip() for name in geometry.data['ANNAME']}
            uv = hdus['UV_DATA']
            nband = int(uv.header.get('NO_BAND', geometry.header.get('NO_BAND', 0)))
            nchan = int(uv.header.get('NO_CHAN', geometry.header.get('NO_CHAN', 0)))
            if not len(uv.data) or nband < 1 or nchan < 1:
                raise ValueError(f'Cannot determine flagging layout/time coverage of {filename}')
            low, high = math.inf, -math.inf
            # Bound temporary allocations for large visibility tables.
            for offset in range(0, len(uv.data), 65536):
                rows = uv.data[offset:offset + 65536]
                times = np.asarray(rows['DATE'], dtype=float) + np.asarray(rows['TIME'], dtype=float)
                low, high = min(low, float(np.nanmin(times))), max(high, float(np.nanmax(times)))
            contexts.append(dict(antennas=antennas, nband=nband, nchan=nchan,
                                 start=Time(low, format='jd').to_datetime(),
                                 end=Time(high, format='jd').to_datetime()))
    return contexts


def _number(value):
    if isinstance(value, bool):
        raise ValueError('missing numeric value')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('non-finite numeric value')
    return value


def _range(row, first, last, maximum):
    lo, hi = _number(row.get(first, 0)), _number(row.get(last, 0))
    lo, hi = lo or 1, hi or maximum
    if int(lo) != lo or int(hi) != hi:
        raise ValueError(f'{first}/{last} must be integers')
    if not 1 <= lo <= hi <= maximum:
        raise ValueError(f'{first}/{last}={lo:g}/{hi:g} outside 1..{maximum}')
    return int(lo) - 1, int(hi) - 1


def _timeranges(row, context):
    values = row.get('TIMERANG', 0)
    if values == 0 or values == [0, 0, 0, 0, 400, 0, 0, 0] or values == [0] * 8:
        return [(context['start'], context['end'])]
    if not isinstance(values, list) or len(values) != 8:
        raise ValueError('TIMERANG requires eight numbers or zero')
    values = [_number(v) for v in values]
    if not any(values[4:]):
        values[4:] = values[:4]
    for day, hour, minute, second in (values[:4], values[4:]):
        if not (day.is_integer() and 1 <= day <= 366 and 0 <= hour <= 24 and
                0 <= minute <= 60 and 0 <= second <= 60):
            raise ValueError('invalid day-of-year TIMERANG')
    timeoff, padding = _number(row['TIMEOFF']), _number(row['DTIMRANG'])
    if padding < 0:
        raise ValueError('negative DTIMRANG')
    if values[:4] == values[4:]:
        padding = max(padding, 0.5)
    result = []
    for year in range(context['start'].year - 1, context['end'].year + 1):
        endyear = year + 1 if values[4] < values[0] else year
        if values[0] > 365 + isleap(year) or values[4] > 365 + isleap(endyear):
            continue
        start = datetime(year, 1, 1) + timedelta(days=values[0] - 1, hours=values[1],
                                               minutes=values[2], seconds=values[3] + timeoff)
        end = datetime(endyear, 1, 1) + timedelta(days=values[4] - 1, hours=values[5],
                                                minutes=values[6], seconds=values[7] + timeoff)
        if end < start:
            raise ValueError('reversed TIMERANG')
        start, end = start - timedelta(seconds=padding), end + timedelta(seconds=padding)
        if start <= context['end'] and end >= context['start']:
            result.append((max(start, context['start']), min(end, context['end'])))
    return result


def _time(value):
    return value.strftime('%Y/%m/%d/%H:%M:%S.%f').rstrip('0').rstrip('.')


def row_commands(row, contexts):
    supported = {'ANT_NAME', 'TIMERANG', 'OPCODE', 'REASON', 'TIMEOFF', 'DTIMRANG',
                 'BIF', 'EIF', 'BCHAN', 'ECHAN'}
    if set(row) - supported:
        raise ValueError('unsupported UVFLG selectors: ' + ', '.join(sorted(set(row) - supported)))
    if str(row.get('OPCODE', 'FLAG')).strip().upper() not in ('', 'FLAG'):
        raise ValueError('only OPCODE=FLAG is supported')
    antenna = str(row.get('ANT_NAME', '')).strip().upper()
    relevant = [c for c in contexts if antenna in c['antennas']]
    if not relevant:
        return [], 'unknown_antenna'
    commands = []
    # Only the output MS's corresponding FITS files are supplied by FitsToMS.
    for context in relevant:
        bif, eif = _range(row, 'BIF', 'EIF', context['nband'])
        bchan, echan = _range(row, 'BCHAN', 'ECHAN', context['nchan'])
        spw = f'{bif}~{eif}' if bif != eif else str(bif)
        if bchan != 0 or echan != context['nchan'] - 1:
            spw += f':{bchan}~{echan}'
        for start, end in _timeranges(row, context):
            parts = ["mode='manual'", 'antenna=' + casa_quote(context['antennas'][antenna]),
                     'timerange=' + casa_quote(f'{_time(start)}~{_time(end)}'),
                     'spw=' + casa_quote(spw)]
            reason = str(row.get('REASON', '')).strip()
            if '\n' in reason or '\r' in reason:
                raise ValueError('multiline reason')
            if reason:
                parts.append('reason=' + casa_quote(reason))
            commands.append(' '.join(parts))
    return commands, None if commands else 'outside_time'


def build_artifact_flagcmd(fitsfiles, output, directories, extensions=FLAG_EXTENSIONS, explicit=None):
    """Return command count and per-file provenance without modifying input data."""
    paths = discover_flagfiles(directories, extensions, explicit)
    reports, commands = [], {}
    contexts = fits_flag_contexts(fitsfiles) if paths else []
    for path in paths:
        report = dict(path=str(path), origin='explicit' if normalize_strlist(explicit) else 'discovered',
                      parsed_rows=0, accepted_rows=0, unique_commands=0, skipped={}, errors=[], status='prepared')
        reports.append(report)
        try:
            rows = read_uvflg(path)
        except Exception as exc:
            report.update(status='rejected', error=str(exc))
            log.warning('Skipping flag artifact %s: %s', path, exc)
            continue
        report['parsed_rows'] = len(rows)
        for number, row in enumerate(rows, 1):
            try:
                lines, rejected = row_commands(row, contexts)
            except (ValueError, TypeError, OverflowError) as exc:
                lines, rejected = [], 'invalid_record'
                report['errors'].append(dict(record=number, reason=str(exc)))
            if rejected:
                report['skipped'][rejected] = report['skipped'].get(rejected, 0) + 1
            else:
                report['accepted_rows'] += 1
                for line in lines:
                    if line not in commands:
                        commands[line] = None
                        report['unique_commands'] += 1
        if report['skipped']:
            log.warning('Flag artifact %s: skipped records %s; see provenance for details', path, report['skipped'])
    output = Path(output)
    output.write_text('\n'.join(commands) + ('\n' if commands else ''))
    return len(commands), reports
