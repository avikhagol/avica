"""Preserve FITS-IDI calibration when replacing only part of an observation."""

import numpy as np
from astropy.io import fits
from astropy.time import Time


def _key(row):
    return tuple(int(row[name]) for name in ('ANTENNA_NO', 'ARRAY', 'FREQID'))


def merge_calibration(old, new, reference_date=None):
    """Replace matching gain rows or TSYS time spans, retaining other rows.

    Keys include antenna, array and frequency ID. TSYS spans are computed from
    rows actually written by the importer, separately for each key. Incompatible
    schemas fail before the staged file can replace the working FITS file.
    """
    name = new.name
    if not len(new.data):
        raise ValueError(f'ANTAB produced an empty {name} table')
    if old is None or not len(old.data):
        return new
    for key in ('NO_BAND', 'STK_1'):
        if old.header.get(key) != new.header.get(key):
            raise ValueError(f'Cannot merge {name}: incompatible {key}')
    new = new.copy()
    if name == 'SYSTEM_TEMPERATURE':
        old_date = old.header.get('RDATE', reference_date)
        new_date = new.header.get('RDATE', reference_date)
        if not old_date or not new_date:
            raise ValueError('Cannot preserve TSYS without a reference date')
        new.data['TIME'] += Time(new_date).mjd - Time(old_date).mjd

    spans = {}
    for row in new.data:
        key = _key(row)
        if name == 'SYSTEM_TEMPERATURE':
            t = float(row['TIME'])
            if not np.isfinite(t):
                raise ValueError('ANTAB produced a non-finite TSYS time')
            lo, hi = spans.get(key, (t, t))
            spans[key] = min(lo, t), max(hi, t)
        else:
            spans[key] = None
    keep = np.array([_key(row) not in spans or (
        name == 'SYSTEM_TEMPERATURE' and not
        spans[_key(row)][0] <= row['TIME'] <= spans[_key(row)][1])
        for row in old.data], dtype=bool)
    retained = old.data[keep]
    bands = int(new.header['NO_BAND'])
    tabs = max(int(old.header.get('NO_TABS', 1)), int(new.header.get('NO_TABS', 1)))
    columns = []
    names = list(dict.fromkeys(old.columns.names + new.columns.names))
    for field in names:
        a = old.columns[field] if field in old.columns.names else None
        b = new.columns[field] if field in new.columns.names else None
        col = (a if a is not None else b).copy()
        polynomial = name == 'GAIN_CURVE' and field.startswith(('GAIN_', 'Y_VAL_'))
        if a is not None and b is not None:
            if a.unit and b.unit and a.unit != b.unit:
                raise ValueError(f'Cannot merge {name}.{field}: incompatible units')
            if a.format.format != b.format.format:
                if {a.format.format, b.format.format} <= {'E', 'D'}:
                    col.format = fits.Column(name=field, format=f'{col.format.repeat}D').format
                else:
                    raise ValueError(f'Cannot merge {name}.{field}: incompatible column types')
            if a.format.repeat != b.format.repeat and not polynomial:
                raise ValueError(f'Cannot merge {name}.{field}: incompatible column sizes')
        if polynomial:
            col.format = fits.Column(name=field, format=f'{bands * tabs}{col.format.format}').format
            col.dim = None
        col.array = None
        columns.append(col)
    header = old.header.copy()
    header['NO_POL'] = max(old.header.get('NO_POL', 1), new.header.get('NO_POL', 1))
    if name == 'GAIN_CURVE':
        header['NO_TABS'] = tabs
    else:
        header['RDATE'] = old_date
    result = fits.BinTableHDU.from_columns(columns, header=header,
                                           nrows=len(retained) + len(new.data))
    for table, rows, start in ((old, retained, 0), (new, new.data, len(retained))):
        stop = start + len(rows)
        for field in names:
            dest = result.data[field][start:stop]
            source = field
            if source not in table.columns.names:
                # A single-polarization GAIN is the common curve for both hands.
                if name == 'GAIN_CURVE' and field.endswith('_2'):
                    source = field[:-1] + '1'
                elif field.startswith(('TSYS_', 'TANT_')):
                    dest[...] = -999.9 if field.startswith('TSYS_') else np.nan
                    continue
                else:
                    raise ValueError(f'Cannot merge {name}: missing column {field}')
            if source not in table.columns.names:
                raise ValueError(f'Cannot merge {name}: missing column {source}')
            if name == 'GAIN_CURVE' and field.startswith(('GAIN_', 'Y_VAL_')):
                source_tabs = int(table.header['NO_TABS'])
                dest[...] = 0 if field.startswith('GAIN_') else np.nan
                dest.reshape(len(rows), bands, tabs)[:, :, :source_tabs] = np.asarray(
                    rows[source]).reshape(len(rows), bands, source_tabs)
            else:
                dest[...] = np.asarray(rows[source]).reshape(dest.shape)
    if name == 'SYSTEM_TEMPERATURE':
        result.data = result.data[np.argsort(result.data['TIME'], kind='stable')]
    if not set(old.data['ANTENNA_NO']).issubset(set(result.data['ANTENNA_NO'])):
        raise ValueError(f'Merging {name} would remove a calibrated antenna')
    return result


def preserve_calibration(original, staged, has_gain):
    """Validate and merge appended tables on a staging copy only."""
    names = ['SYSTEM_TEMPERATURE'] + (['GAIN_CURVE'] if has_gain else [])
    with fits.open(original, memmap=False) as before, fits.open(staged, mode='update', memmap=False) as after:
        reference = before['ARRAY_GEOMETRY'].header.get('RDATE')
        for name in names:
            if sum(hdu.name == name for hdu in before) > 1 or sum(hdu.name == name for hdu in after) != 1:
                raise ValueError(f'Cannot safely merge multiple or missing {name} extensions')
            old = before[name] if name in before else None
            merged = merge_calibration(old, after[name], reference)
            after[after.index_of(name)] = merged
