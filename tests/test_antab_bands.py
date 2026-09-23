"""Band-correct gain curves and partial-calibration attach; real JIVE append code, no CASA."""
import tempfile
import unittest
import warnings
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
from astropy.io import fits
from astropy.time import Time

from avica.external.jive import append_gc as GCData
from avica.fitsidiutil import FITSIDI, read_idi
from avica.fitsidiutil.antab_bands import (antab_groups, band_gain_curve, if_centres_mhz, make_skeleton,
                                           read_cal_table, write_gain_curve)
from avica.pipe.core import GenerateAndAppendAntab
from avica.pipe.helpers import uncalibrated_antennas

RDATE = '2025-03-21'
# IF1-2 K band, IF3-4 Q band, as in the KVN combined K/Q layout.
BANDFREQ = [0.0, 2.048e9, 21.55e9, 23.598e9]
REF_FREQ = 21.55e9
BANDWIDTH = 2.048e9


def gain(an, mount, lo, hi, dpfu, poly):
    return f"GAIN {an} {mount} FREQ={lo},{hi} DPFU={dpfu} POLY={','.join(map(str, poly))} /\n"


def tsys(an, rows):
    body = ''.join(f"080 {t} {' '.join(map(str, v))}\n" for t, v in rows)
    return f"TSYS {an} FT=1.0 TIMEOFF=0.0 INDEX='L1','L2','R3','R4' /\n!DOY UT TSYS*\n{body}/\n"


ROWS = [('01:00:00', [65.5, 70.6, 161.8, 247.6]), ('03:00:00', [66.0, 71.0, 162.0, 248.0])]


def station(an, mount='ELEV', q_poly=(0.975, 0.0027, -0.000027), rows=ROWS):
    return ("!--- Gains (DPFUs)\n"
            + gain(an, mount, 18000, 26000, 0.0955, [1.02, 0.00033, -0.0000062])
            + gain(an, mount, 35000, 50000, 0.0854, q_poly)
            + gain(an, mount, 80000, 98000, 0.0753, [0.90, 0.009, -0.0000875])
            + gain(an, mount, 98000, 116000, 0.0600, [0.90, 0.0127, -0.000128])
            + "!\n" + tsys(an, rows))


def make_idi(path, antennas=('KC', 'KT'), infile_tsys=None, infile_gain=False):
    """Minimal FITS-IDI with 4 IFs; infile_tsys: {ANTENNA_NO: TSYS_1/TSYS_2 values} rows at 01:00, 03:00."""
    def table(name, columns, **header):
        hdu = fits.BinTableHDU.from_columns([fits.Column(name=n, format=f, array=a) for n, f, a in columns], name=name)
        hdu.header.update(header)
        return hdu

    common = dict(OBSCODE='N24JK03', NO_STKD=2, STK_1=-1, NO_BAND=4, NO_CHAN=16,
                  REF_FREQ=REF_FREQ, CHAN_BW=5e5, REF_PIXL=1.0, RDATE=RDATE)
    ids = list(range(1, len(antennas) + 1))
    primary = fits.PrimaryHDU()
    primary.header['DATE-OBS'] = RDATE
    geometry = table('ARRAY_GEOMETRY', [('ANNAME', '8A', list(antennas)), ('NOSTA', '1J', ids)], EXTVER=1, **common)
    antenna = table('ANTENNA', [('ANTENNA_NO', '1J', ids), ('ANNAME', '8A', list(antennas))], **common)
    frequency = table('FREQUENCY', [('FREQID', '1J', [1]), ('BANDFREQ', '4D', [BANDFREQ]),
                                    ('TOTAL_BANDWIDTH', '4E', [[BANDWIDTH] * 4]), ('SIDEBAND', '4J', [[1] * 4])],
                      **common)
    source = table('SOURCE', [('SOURCE_ID', '1J', [1]), ('SOURCE', '16A', ['3C84'])], **common)
    jd = Time(RDATE).jd
    uv = table('UV_DATA', [('DATE', '1D', [jd] * 2), ('TIME', '1D', [0.5 / 24, 3.5 / 24]),
                           ('SOURCE_ID', '1J', [1, 1])], **common)
    uv.header['DATE-OBS'] = RDATE
    hdus = [primary, geometry, antenna, frequency, source, uv]
    if infile_tsys:
        times, ants, t1, t2 = [], [], [], []
        for anno, values in infile_tsys.items():
            for t in (1 / 24, 3 / 24):
                times.append(t); ants.append(anno)
                t1.append([-999.9, -999.9, values[2], values[3]]); t2.append([values[0], values[1], -999.9, -999.9])
        st = table('SYSTEM_TEMPERATURE', [('TIME', '1D', times), ('TIME_INTERVAL', '1E', [0.0] * len(times)),
                                          ('SOURCE_ID', '1J', [1] * len(times)), ('ANTENNA_NO', '1J', ants),
                                          ('ARRAY', '1J', [1] * len(times)), ('FREQID', '1J', [1] * len(times)),
                                          ('TSYS_1', '4E', t1), ('TANT_1', '4E', [[np.nan] * 4] * len(times)),
                                          ('TSYS_2', '4E', t2), ('TANT_2', '4E', [[np.nan] * 4] * len(times))],
                   NO_POL=2, **common)
        hdus.append(st)
    fits.HDUList(hdus).writeto(path, overwrite=True)
    if infile_gain:
        antab = Path(path).with_suffix('.gain.antab')
        antab.write_text(''.join(gain(an, 'ELEV', 18000, 26000, 0.1, [1.0]) for an in antennas))
        GCData.append_gc(antabfile=str(antab), idifile=str(path), replace=True)
    return Path(path)


class AntabBandsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.write_text(text)
        return path

    def test_groups_keep_text_verbatim_and_tsys_rows(self):
        text = station('KC') + station('KT')
        groups = antab_groups(text)
        self.assertEqual([(g.kind, g.antenna) for g in groups],
                         [('GAIN', 'KC')] * 4 + [('TSYS', 'KC')] + [('GAIN', 'KT')] * 4 + [('TSYS', 'KT')])
        self.assertEqual(''.join(g.text for g in groups), text)
        self.assertIn('080 03:00:00', groups[4].text)

    def test_single_gain_per_antenna_keeps_plain_append_gc(self):
        antab = self.write('one.antab', gain('KC', 'ELEV', 18000, 26000, 0.1, [1.0]) + tsys('KC', ROWS))
        # the FITS file is not even opened on this path
        self.assertIsNone(band_gain_curve(antab, self.root / 'absent.fits', GCData.append_gc))

    def test_if_centres(self):
        ff = make_idi(self.root / 'a.fits')
        np.testing.assert_allclose(if_centres_mhz(ff), [22574, 24622, 44124, 46172])

    def test_one_row_per_antenna_with_per_band_dpfu_poly_and_mount(self):
        ff = make_idi(self.root / 'a.fits')
        antab = self.write('kvn.antab', station('KC') + station('KT', mount='ALTAZ', q_poly=(0.97, 0.002)))
        table = band_gain_curve(antab, ff, GCData.append_gc, workdir=self.root)
        self.assertEqual(sorted(table.columns['ANTENNA_NO']), [1, 2])
        self.assertEqual(table.get('NO_TABS'), 3)
        self.assertEqual(table.formats['Y_TYP_1'], '4J')
        self.assertEqual(table.formats['GAIN_1'], '12E')
        self.assertEqual(table.columns['Y_TYP_1'].dtype, np.int64)
        rows = {int(a): j for j, a in enumerate(table.columns['ANTENNA_NO'])}
        col = lambda name, an: table.columns[name][rows[an]]
        np.testing.assert_allclose(col('SENS_1', 1), [0.0955, 0.0955, 0.0854, 0.0854], rtol=1e-6)
        self.assertEqual(list(col('Y_TYP_1', 1)), [1, 1, 1, 1])                   # ELEV
        self.assertEqual(list(col('Y_TYP_1', 2)), [2, 2, 2, 2])                   # ALTAZ kept as given
        poly = col('GAIN_1', 2).reshape(4, 3)
        np.testing.assert_allclose(poly[0], [1.02, 0.00033, -0.0000062], rtol=1e-5)
        np.testing.assert_allclose(poly[2], [0.97, 0.002, 0.0], rtol=1e-5)          # shorter Q poly padded
        self.assertEqual(list(col('NTERM_1', 2)), [3, 3, 2, 2])

    def test_plain_append_gc_has_duplicates_that_the_splice_removes(self):
        ff = make_idi(self.root / 'a.fits')
        antab = self.write('kvn.antab', station('KC') + station('KT'))
        GCData.append_gc(antabfile=str(antab), idifile=str(ff), replace=True)
        with fits.open(ff) as hdul:
            self.assertEqual(len(hdul['GAIN_CURVE'].data), 8)            # what the plain path produces

    def test_overlapping_freq_ranges_fall_back(self):
        ff = make_idi(self.root / 'a.fits')
        text = station('KC') + gain('KC', 'ELEV', 20000, 30000, 0.2, [1.0])
        antab = self.write('overlap.antab', text)
        with self.assertWarnsRegex(RuntimeWarning, 'plain append_gc'):
            self.assertIsNone(band_gain_curve(antab, ff, GCData.append_gc, workdir=self.root))

    def test_uncovered_if_falls_back(self):
        ff = make_idi(self.root / 'a.fits')
        antab = self.write('konly.antab', gain('KC', 'ELEV', 18000, 26000, 0.1, [1.0])
                           + gain('KC', 'ELEV', 80000, 98000, 0.2, [1.0]))
        with self.assertWarnsRegex(RuntimeWarning, 'IF3'):
            self.assertIsNone(band_gain_curve(antab, ff, GCData.append_gc, workdir=self.root))

    def test_stations_absent_from_fits_are_ignored(self):
        ff = make_idi(self.root / 'a.fits', antennas=('KC',))
        antab = self.write('extra.antab', station('KX') + station('KC'))
        table = band_gain_curve(antab, ff, GCData.append_gc, workdir=self.root)
        self.assertEqual(list(table.columns['ANTENNA_NO']), [1])
        np.testing.assert_allclose(table.columns['SENS_1'][0], [0.0955, 0.0955, 0.0854, 0.0854], rtol=1e-6)

    def test_old_extension_without_replace_table_falls_back(self):
        ff = make_idi(self.root / 'a.fits')
        antab = self.write('kvn.antab', station('KC'))
        with patch('avica.fitsidiutil.antab_bands.ReadIO', object), \
             self.assertWarnsRegex(RuntimeWarning, 'rebuild'):
            self.assertIsNone(band_gain_curve(antab, ff, GCData.append_gc, workdir=self.root))

    def test_append_failure_in_band_path_falls_back(self):
        ff = make_idi(self.root / 'a.fits')
        antab = self.write('kvn.antab', station('KC'))
        with self.assertWarnsRegex(RuntimeWarning, 'boom'):
            self.assertIsNone(band_gain_curve(antab, ff, lambda **kw: (_ for _ in ()).throw(RuntimeError('boom')),
                                              workdir=self.root))


class FitsidiutilIOTest(unittest.TestCase):
    """read(hdus=), column types and replace_table of avica.fitsidiutil on small FITS-IDI files."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ff = make_idi(self.root / 'a.fits', infile_tsys={1: [65.5, 70.6, 161.8, 247.6]})
        self.antab = self.root / 'kvn.antab'
        self.antab.write_text(station('KC') + station('KT'))
        GCData.append_gc(antabfile=str(self.antab), idifile=str(self.ff), replace=True)   # 8 plain rows

    def test_read_only_requested_tables(self):
        hdul = read_idi(str(self.ff), hdus=['FREQUENCY'])
        self.assertIn('SYSTEM_TEMPERATURE', hdul.names)                  # headers of every HDU
        self.assertIsNotNone(hdul['FREQUENCY'].cols)
        self.assertIsNone(hdul['SYSTEM_TEMPERATURE'].cols)
        self.assertIsNotNone(read_idi(str(self.ff))['SYSTEM_TEMPERATURE'].cols)   # default unchanged

    def test_column_formats_and_typed_restore_integer_vectors(self):
        gc = read_idi(str(self.ff), hdus=['GAIN_CURVE'])['GAIN_CURVE']
        self.assertEqual(gc.column_formats['Y_TYP_1'], (4, 'J'))
        self.assertEqual(gc.column_formats['ANTENNA_NO'], (1, 'J'))
        self.assertEqual(np.asarray(gc['Y_TYP_1']).dtype, np.float64)        # as read_table_chunked returns it
        self.assertEqual(gc.typed('Y_TYP_1').dtype, np.int64)
        self.assertEqual(gc.typed('SENS_1').dtype, np.float64)
        self.assertEqual(gc.typed('Y_TYP_1').tolist(), [[1, 1, 1, 1]] * 8)

    def test_replace_table_shrinks_in_place_and_keeps_other_hdus(self):
        with fits.open(self.ff) as before:
            names = [h.name for h in before]
            kept = {h.name: (h.header.tostring(), h.data.tobytes() if h.data is not None else b'')
                    for h in before if h.name != 'GAIN_CURVE'}
        table = band_gain_curve(self.antab, self.ff, GCData.append_gc, workdir=self.root)
        write_gain_curve(self.ff, table)
        with fits.open(self.ff) as after:
            self.assertEqual([h.name for h in after], names)                # same position
            for h in after:
                if h.name != 'GAIN_CURVE':
                    self.assertEqual((h.header.tostring(), h.data.tobytes() if h.data is not None else b''),
                                     kept[h.name], h.name)
            gc = after['GAIN_CURVE']
            self.assertEqual(len(gc.data), 2)
            self.assertEqual(gc.header['NO_TABS'], 3)
            self.assertEqual(gc.header['NO_BAND'], 4)
            self.assertEqual(gc.columns['Y_TYP_1'].format, '4J')
            np.testing.assert_allclose(gc.data['SENS_1'][0], [0.0955, 0.0955, 0.0854, 0.0854], rtol=1e-6)
            self.assertEqual(gc.data['NTERM_1'][0].tolist(), [3, 3, 3, 3])
        again = read_cal_table(self.ff, 'GAIN_CURVE')                        # same values via fitsidiutil
        np.testing.assert_allclose(again.columns['GAIN_1'], table.columns['GAIN_1'], rtol=1e-6)

    def test_jive_append_still_works_after_replace(self):
        write_gain_curve(self.ff, band_gain_curve(self.antab, self.ff, GCData.append_gc, workdir=self.root))
        from avica.external.jive import append_tsys as TsysData
        TsysData.append_tsys(antabfile=str(self.antab), idifiles=str(self.ff), replace=True)
        GCData.append_gc(antabfile=str(self.antab), idifile=str(self.ff), replace=True)
        with fits.open(self.ff) as hdul:
            self.assertEqual(sorted(set(hdul['SYSTEM_TEMPERATURE'].data['ANTENNA_NO'])), [1, 2])

    def test_replace_table_appends_when_absent(self):
        ff = make_idi(self.root / 'nogc.fits', infile_tsys={1: [65.5, 70.6, 161.8, 247.6]})
        write_gain_curve(ff, band_gain_curve(self.antab, ff, GCData.append_gc, workdir=self.root))
        with fits.open(ff) as hdul:
            self.assertEqual(hdul[-1].name, 'GAIN_CURVE')
            self.assertEqual(len(hdul['GAIN_CURVE'].data), 2)

    def test_replace_table_needs_write_mode(self):
        with FITSIDI(str(self.ff)).open('r') as fo:
            with self.assertRaises(IOError):
                fo.replace_table('GAIN_CURVE', [('ANTENNA_NO', '1J', '')], {'ANTENNA_NO': np.array([1])})

    def test_skeleton_has_every_hdu_and_one_uv_row(self):
        out = self.root / 'skel.fits'
        make_skeleton(self.ff, out)
        hdul = read_idi(str(out))
        self.assertEqual(hdul.names, read_idi(str(self.ff), hdus=[]).names)
        self.assertEqual(hdul['UV_DATA'].nrows, 1)


class PartialCalibrationAttachTest(unittest.TestCase):
    """KC calibrated in the file (as the correlator delivers N24JK03), KT only via local ANTAB."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'raw').mkdir()
        self.artifacts = self.root / 'artifacts'
        self.artifacts.mkdir()
        self.ff = make_idi(self.root / 'raw' / 'n24jk03a.fits', infile_tsys={1: [65.5, 70.6, 161.8, 247.6]})
        self.ga = GenerateAndAppendAntab([str(self.ff)], self.root, False, self.root, artifact_dirs=[self.artifacts])
        self.date = patch('avica.fitsidiutil.op.get_dateobs', return_value=datetime(2025, 3, 21))
        self.date.start()
        self.addCleanup(self.date.stop)

    def test_detection(self):
        self.assertEqual(uncalibrated_antennas(str(self.ff)), {'tsys': ['KT'], 'gain': ['KC', 'KT']})

    def test_invalid_only_rows_do_not_count_as_tsys(self):
        ff = make_idi(self.root / 'bad.fits', infile_tsys={1: [65.5, 70.6, 161.8, 247.6],
                                                           2: [-999.9, -999.9, -999.9, -999.9]})
        self.assertEqual(uncalibrated_antennas(str(ff))['tsys'], ['KT'])

    def test_partial_file_gets_local_antab_without_download_and_rerun_is_a_no_op(self):
        antab = self.artifacts / 'n24jk03a.antab'
        antab.write_text(station('KC') + station('KT'))
        with patch('avica.pipe.core.find_tsys') as download, warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.ga.attach_antab(only_first=False)
        download.assert_not_called()
        self.assertEqual(self.ga.calibration_sources[-1]['kind'], 'local_antab')
        self.assertEqual(uncalibrated_antennas(str(self.ff)), {'tsys': [], 'gain': []})
        with fits.open(self.ff) as hdul:
            st, gc = hdul['SYSTEM_TEMPERATURE'].data, hdul['GAIN_CURVE'].data
            self.assertEqual(sorted(set(st['ANTENNA_NO'])), [1, 2])
            self.assertEqual(len(gc), 2)                                     # one row per antenna
            for row in gc:
                np.testing.assert_allclose(row['SENS_1'], [0.0955, 0.0955, 0.0854, 0.0854], rtol=1e-6)
        with patch.object(self.ga, '_append_antab_file') as append, patch('avica.pipe.core.find_tsys') as download:
            self.ga.attach_antab(only_first=False)
        append.assert_not_called()
        download.assert_not_called()

    def test_antab_that_only_repeats_calibrated_antennas_is_not_applied(self):
        ff = make_idi(self.root / 'raw' / 'gc.fits', infile_tsys={1: [65.5, 70.6, 161.8, 247.6]}, infile_gain=True)
        (self.artifacts / 'kc_only.antab').write_text(station('KC'))
        ga = GenerateAndAppendAntab([str(ff)], self.root, False, self.root, artifact_dirs=[self.artifacts])
        with patch.object(ga, '_append_antab_file') as append, patch('avica.pipe.core.find_tsys') as download, \
             warnings.catch_warnings():
            warnings.simplefilter('ignore')
            ga.attach_antab(only_first=False)
        append.assert_not_called()
        download.assert_not_called()
        self.assertEqual(ga.calibration_decisions[-1]['status'], 'partial_unresolved')

    def test_fully_calibrated_file_skips_the_search(self):
        ff = make_idi(self.root / 'raw' / 'full.fits', infile_tsys={1: [65.5, 70.6, 161.8, 247.6],
                                                                    2: [60.0, 61.0, 150.0, 200.0]},
                      infile_gain=True)
        ga = GenerateAndAppendAntab([str(ff)], self.root, False, self.root, artifact_dirs=[self.artifacts])
        with patch.object(ga, '_find_local_antab') as search, patch('avica.pipe.core.find_tsys') as download:
            ga.attach_antab(only_first=False)
        search.assert_not_called()
        download.assert_not_called()

    def test_ambiguous_or_failing_attach_is_reported_and_file_left_unchanged(self):
        (self.artifacts / 'a.antab').write_text(station('KC') + station('KT'))
        (self.artifacts / 'b.antab').write_text(station('KC') + station('KT'))
        before = self.ff.read_bytes()
        with self.assertLogs('avica.pipeline', level='ERROR'), warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.ga.attach_antab(only_first=False)                     # must not raise
        self.assertEqual(self.ff.read_bytes(), before)
        self.assertIn('Ambiguous', self.ga.calibration_decisions[-1]['reason'])
        (self.artifacts / 'b.antab').unlink()
        with patch('avica.external.jive.append_tsys.append_tsys', side_effect=RuntimeError('bad tsys')), \
             self.assertLogs('avica.pipeline', level='ERROR'), warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.ga.attach_antab(only_first=False)
        self.assertEqual(self.ff.read_bytes(), before)
        self.assertEqual(list((self.root / 'raw').glob('*.tmp')), [])

    def test_local_antab_disabled_keeps_previous_behaviour(self):
        (self.artifacts / 'n24jk03a.antab').write_text(station('KC') + station('KT'))
        self.ga.use_local_antab = False
        with patch.object(self.ga, '_append_antab_file') as append, patch('avica.pipe.core.find_tsys') as download:
            self.ga.attach_antab(only_first=False)
        append.assert_not_called()
        download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
