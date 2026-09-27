"""Real FITS/JIVE regression checks for partial calibration updates."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from astropy.io import fits
from astropy.time import Time

from avica.pipe.core import GenerateAndAppendAntab
from avica.fitsidiutil.calibration import merge_calibration


def antab(antennas, times=(9, 13), value=30, gain=True, poly='1,0.01', dpfu='0.1,0.2'):
    blocks = []
    for antenna in antennas:
        if gain:
            blocks.append(f'GAIN {antenna} ELEV DPFU={dpfu} POLY={poly} /\n')
        blocks.append(f"TSYS {antenna} INDEX='R1','L1','R2','L2' /\n")
        blocks.extend(f'100 {hour:02}:00:00 {value} {value+1} {value+2} {value+3}\n' for hour in times)
        blocks.append('/\n')
    return ''.join(blocks)


class CalibrationMergeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.ff = self.root / 'vlba.fits'

        def table(name, columns):
            return fits.BinTableHDU.from_columns([
                fits.Column(name=n, format=f, array=a) for n, f, a in columns], name=name)

        geometry = table('ARRAY_GEOMETRY', [('ANNAME', '8A', ['LA', 'PT']), ('NOSTA', '1J', [1, 2])])
        geometry.header.update(EXTVER=1, OBSCODE='TEST', NO_STKD=2, STK_1=-1,
                               NO_BAND=2, NO_CHAN=1, REF_FREQ=5e9, CHAN_BW=1e6,
                               REF_PIXL=1, RDATE='2025-04-10')
        frequency = table('FREQUENCY', [('FREQID', '1J', [1]), ('BANDFREQ', '2D', [[0, 1e6]])])
        source = table('SOURCE', [('SOURCE_ID', '1J', [1]), ('SOURCE', '8A', ['TEST'])])
        uv = table('UV_DATA', [('DATE', '1D', [Time('2025-04-10').jd] * 2),
                               ('TIME', '1D', [8/24, 14/24]), ('SOURCE_ID', '1J', [1, 1])])
        primary = fits.PrimaryHDU()
        primary.header['DATE-OBS'] = '2025-04-10'
        fits.HDUList([primary, geometry, frequency, source, uv]).writeto(self.ff)
        self.ga = GenerateAndAppendAntab([str(self.ff)], self.root, False, self.root,
                                        artifact_dirs=[self.root], local_antab_require_full_array=False)
        self.apply(antab(['LA', 'PT'], times=(9, 11, 13)))

    def apply(self, text, files=None):
        local = self.root / 'input.antab'
        local.write_text(text)
        self.ga._append_antab_file(local, files or [str(self.ff)])

    def tables(self):
        with fits.open(self.ff) as hdus:
            return hdus['SYSTEM_TEMPERATURE'].copy(), hdus['GAIN_CURVE'].copy()

    def test_partial_update_preserves_station_gains_and_outside_tsys(self):
        old_tsys, old_gain = self.tables()
        self.apply(antab(['LA'], times=(10, 12), value=80, poly='2', dpfu='0.3'))
        tsys, gain = self.tables()
        self.assertEqual(set(gain.data['ANTENNA_NO']), {1, 2})
        for name in old_gain.columns.names:
            np.testing.assert_equal(gain.data[name][gain.data['ANTENNA_NO'] == 2],
                                    old_gain.data[name][old_gain.data['ANTENNA_NO'] == 2])
        for name in old_tsys.columns.names:
            np.testing.assert_equal(tsys.data[name][tsys.data['ANTENNA_NO'] == 2],
                                    old_tsys.data[name][old_tsys.data['ANTENNA_NO'] == 2])
        la = tsys.data[tsys.data['ANTENNA_NO'] == 1]
        np.testing.assert_allclose(la['TIME'] * 24, [9, 10, 12, 13])
        np.testing.assert_allclose(la['TSYS_1'][:, 0], [30, 80, 80, 30])
        self.assertEqual(gain.header['NO_TABS'], 2)
        self.assertEqual(gain.header['NO_POL'], 2)
        np.testing.assert_allclose(gain.data['SENS_2'][gain.data['ANTENNA_NO'] == 1], [[0.3, 0.3]])

    def test_longer_polynomial_pads_retained_gain_per_band(self):
        _, before = self.tables()
        self.apply(antab(['LA'], poly='2,0.1,0.001'))
        _, after = self.tables()
        old = before.data['GAIN_1'][before.data['ANTENNA_NO'] == 2].reshape(1, 2, 2)
        new = after.data['GAIN_1'][after.data['ANTENNA_NO'] == 2].reshape(1, 2, 3)
        np.testing.assert_equal(new[:, :, :2], old)
        np.testing.assert_equal(new[:, :, 2], 0)

    def test_tsys_only_preserves_all_existing_gains(self):
        _, before = self.tables()
        with self.assertWarnsRegex(RuntimeWarning, 'no gain entries'):
            self.apply(antab(['LA'], times=(10, 12), gain=False))
        _, after = self.tables()
        for field in before.columns.names:
            np.testing.assert_equal(after.data[field], before.data[field])

    def test_real_discovery_accepts_if_mismatch_and_preserves_other_station(self):
        local = self.root / 'input.antab'
        local.write_text(antab(['LA'], times=(10, 12), value=80).replace(
            "'R1','L1','R2','L2'", "'R1','L1'"))
        with patch('avica.pipe.core.find_tsys') as download, \
             self.assertLogs('avica.pipeline', level='WARNING') as logged:
            self.ga.find_and_attach_antab(str(self.ff), [str(self.ff)], self.root/'generated.antab', False)
        download.assert_not_called()
        self.assertIn('NO_BAND=2', '\n'.join(logged.output))
        self.assertEqual(self.ga.calibration_decisions[-1]['status'], 'selected')
        self.assertFalse(self.ga.calibration_decisions[-1]['if_compatible'])
        tsys, gain = self.tables()
        self.assertEqual(set(gain.data['ANTENNA_NO']), {1, 2})
        pt = tsys.data[tsys.data['ANTENNA_NO'] == 2]
        np.testing.assert_allclose(pt['TSYS_1'][:, 0], [30, 30, 30])

    def test_tsys_append_failure_preserves_every_original(self):
        from avica.external.jive import append_tsys
        original_append = append_tsys.append_tsys
        second = self.root / 'second.fits'
        second.write_bytes(self.ff.read_bytes())
        before = [p.read_bytes() for p in (self.ff, second)]
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise RuntimeError('TSYS append failed')
            return original_append(**kwargs)

        with patch.object(append_tsys, 'append_tsys', side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, 'TSYS append failed'):
                self.apply(antab(['LA']), [str(self.ff), str(second)])
        self.assertEqual([p.read_bytes() for p in (self.ff, second)], before)
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_merge_failure_preserves_every_original(self):
        second = self.root / 'second.fits'
        second.write_bytes(self.ff.read_bytes())
        before = [p.read_bytes() for p in (self.ff, second)]
        with patch.object(self.ga, '_preserve_calibration', side_effect=[None, ValueError('bad schema')]):
            with self.assertRaisesRegex(ValueError, 'bad schema'):
                self.apply(antab(['LA']), [str(self.ff), str(second)])
        self.assertEqual([p.read_bytes() for p in (self.ff, second)], before)
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_empty_import_does_not_replace_original(self):
        before = self.ff.read_bytes()
        # Some JIVE/Astropy versions reject empty vector tables before our guard.
        with self.assertRaises(ValueError):
            self.apply(antab(['LA'], times=(1, 2), gain=False))
        self.assertEqual(self.ff.read_bytes(), before)

    def test_empty_staged_table_is_rejected(self):
        old, _ = self.tables()
        empty = old.copy()
        empty.data = empty.data[:0]
        with self.assertRaisesRegex(ValueError, 'empty SYSTEM_TEMPERATURE'):
            merge_calibration(old, empty)

    def test_array_and_frequency_ids_are_preserved(self):
        old, _ = self.tables()
        new = old.copy()
        new.data = new.data[:1].copy()
        new.data['ARRAY'] = 2
        new.data['FREQID'] = 2
        merged = merge_calibration(old, new)
        self.assertEqual(len(merged.data), len(old.data) + 1)

    def test_different_reference_dates_are_aligned_before_replacement(self):
        old, _ = self.tables()
        new = old.copy()
        new.header['RDATE'] = '2025-04-11'
        new.data['TIME'] -= 1
        new.data['TSYS_1'] = 99
        merged = merge_calibration(old, new)
        self.assertEqual(len(merged.data), len(old.data))
        np.testing.assert_allclose(merged.data['TIME'], np.sort(old.data['TIME']))
        np.testing.assert_allclose(merged.data['TSYS_1'], 99)


if __name__ == '__main__':
    unittest.main()
