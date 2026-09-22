"""Local calibration selection and append safety; no network or CASA required."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from astropy.time import Time

from avica.pipe.core import GenerateAndAppendAntab
from avica.fitsidiutil.op import parse_antab


ANTAB = """! Ready-to-use station calibration
GAIN EF ELEV DPFU=0.1
POLY=1.0, /
TSYS EF TIMEOFF=0
 INDEX='R1','L1' /
 100 10:00.0 30 31
! a comment inside the data
 100 12:00:00 32 33
/
"""


class LocalAntabTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / 'raw'
        self.raw.mkdir()
        self.artifacts = self.root / 'artifacts'
        self.artifacts.mkdir()
        self.fits = [str(self.raw / 'one.fits'), str(self.raw / 'two.fits')]
        for ff in self.fits:
            Path(ff).write_text('original')
        self.ga = GenerateAndAppendAntab(self.fits, self.root, False, self.root,
                                        artifact_dirs=[self.artifacts])
        self.date = patch('avica.fitsidiutil.op.get_dateobs', return_value=datetime(2025, 4, 10))
        self.date.start()
        self.addCleanup(self.date.stop)
        self.times = patch('avica.pipe.core.tsys_exists', return_value=(
            False, None, None, Time('2025-04-10T10:00:00'), Time('2025-04-10T12:00:00')))
        self.times.start()
        self.addCleanup(self.times.stop)

    def antab(self, name='experiment.AnTaB', text=ANTAB, directory=None):
        path = (directory or self.artifacts) / name
        path.write_text(text)
        return path

    def run_find(self, files=None):
        files = self.fits if files is None else files
        self.ga.find_and_attach_antab(files[0], files, self.root / 'generated.antab', False)

    def test_parser_handles_standard_times_comments_multiline_and_timeoff(self):
        path = self.antab(text=ANTAB.replace('TIMEOFF=0', 'TIMEOFF=60'))
        parsed = parse_antab(path, self.fits[0])
        self.assertIn('EF', parsed['gain_dic'])
        self.assertEqual(parsed['tsys_dic']['start_time'], datetime(2025, 4, 10, 10, 1))
        self.assertEqual(parsed['tsys_dic']['end_time'], datetime(2025, 4, 10, 12, 1))
        self.assertEqual(len(parsed['tsys_dic']['EF']['data']), 2)

    def test_local_antab_bypasses_download_and_conversion(self):
        local = self.antab()
        with patch('avica.pipe.core.find_tsys') as download, \
             patch('avica.fitsidiutil.ANTAB') as converter, \
             patch.object(self.ga, '_append_antab_file') as append:
            self.run_find()
        download.assert_not_called()
        converter.assert_not_called()
        append.assert_called_once_with(local, self.fits)
        self.assertEqual(len(self.ga.calibration_sources), 2)
        self.assertEqual(local.read_text(), ANTAB)

    def test_same_antab_can_be_reused_for_split_files(self):
        local = self.antab()
        with patch('avica.pipe.core.find_tsys') as download, \
             patch.object(self.ga, '_append_antab_file') as append:
            for ff in self.fits:
                self.ga.find_and_attach_antab(ff, [ff], self.root / 'generated', True)
        self.assertEqual(append.call_count, 2)
        self.assertEqual(append.call_args.args, (local, [self.fits[1]]))
        download.assert_not_called()

    def test_best_overlap_and_ambiguous_tie(self):
        local = self.antab()
        self.antab('partial.antab', ANTAB.replace('12:00:00', '11:00:00'))
        self.assertEqual(self.ga._find_local_antab(self.fits[0]), local)
        self.antab('duplicate.antab')
        with self.assertRaisesRegex(ValueError, 'Ambiguous ANTAB'):
            self.ga._find_local_antab(self.fits[0])

    def test_raw_directory_discovery(self):
        local = self.antab(directory=self.raw)
        self.assertEqual(self.ga._find_local_antab(self.fits[0]), local)

    def test_invalid_and_unrelated_files_allow_fallback(self):
        self.antab('unrelated.antab', ANTAB.replace('100 ', '101 '))
        self.antab('broken.antab', 'TSYS EF /\ninvalid row\n/\n')
        with patch('avica.pipe.core.find_tsys', return_value=(0, 1, [])) as download, \
             self.assertWarnsRegex(RuntimeWarning, 'Skipping ANTAB'):
            self.run_find()
        download.assert_called_once()

    def test_no_local_file_uses_vlba_conversion(self):
        rawcal = self.raw / 'calibration.log'
        rawcal.write_text('raw calibration')
        def generate(outfile, **kwargs):
            Path(outfile).write_text(ANTAB)
            return ['EF'], {}, []
        with patch('avica.pipe.core.find_tsys', return_value=(0, 0, [str(rawcal)])), \
             patch('avica.fitsidiutil.ANTAB') as converter, \
             patch('avica.fitsidiutil.get_dateobs', return_value=datetime(2025, 4, 10)), \
             patch.object(self.ga, '_append_antab_file') as append:
            converter.return_value.gen_antab.side_effect = generate
            self.run_find()
        converter.assert_called_once_with(self.fits[0], str(rawcal))
        append.assert_called_once()
        self.assertEqual(self.ga.tsysfiles, {str(rawcal)})

    def test_append_failure_preserves_all_originals_and_source(self):
        local = self.antab()
        def append_tsys(**kwargs):
            Path(kwargs['idifiles']).write_text('modified staging copy')
        with patch('avica.external.jive.append_tsys.append_tsys', side_effect=append_tsys), \
             patch('avica.external.jive.append_gc.append_gc', side_effect=[None, RuntimeError('bad gain')]):
            with self.assertRaisesRegex(RuntimeError, 'bad gain'):
                self.ga._append_antab_file(local, self.fits)
        self.assertTrue(all(Path(ff).read_text() == 'original' for ff in self.fits))
        self.assertEqual(list(self.raw.glob('*.tmp')), [])
        self.assertEqual(local.read_text(), ANTAB)

    def test_success_commits_staged_files(self):
        local = self.antab()
        def append_tsys(**kwargs):
            Path(kwargs['idifiles']).write_text('calibrated')
        with patch('avica.external.jive.append_tsys.append_tsys', side_effect=append_tsys), \
             patch('avica.external.jive.append_gc.append_gc') as gain:
            self.ga._append_antab_file(local, self.fits)
        self.assertTrue(all(Path(ff).read_text() == 'calibrated' for ff in self.fits))
        self.assertEqual(gain.call_count, 2)
        self.assertEqual(list(self.raw.glob('*.tmp')), [])

    def test_missing_gain_preserves_existing_gain_table(self):
        local = self.antab(text=ANTAB.replace('GAIN EF ELEV DPFU=0.1\nPOLY=1.0, /\n', ''))
        with patch('avica.external.jive.append_tsys.append_tsys'), \
             patch('avica.external.jive.append_gc.append_gc') as gain, \
             self.assertWarnsRegex(RuntimeWarning, 'no gain entries'):
            self.ga._append_antab_file(local, [self.fits[0]])
        gain.assert_not_called()

    def test_real_jive_append_creates_tsys_and_gain_tables(self):
        from astropy.io import fits

        def table(name, columns):
            return fits.BinTableHDU.from_columns([
                fits.Column(name=col, format=fmt, array=values)
                for col, fmt, values in columns
            ], name=name)

        geometry = table('ARRAY_GEOMETRY', [('ANNAME', '8A', ['EF']), ('NOSTA', '1J', [1])])
        geometry.header.update(EXTVER=1, OBSCODE='TEST', NO_STKD=2, STK_1=-1,
                               NO_BAND=1, NO_CHAN=1, REF_FREQ=5e9, CHAN_BW=1e6,
                               REF_PIXL=1, RDATE='2025-04-10')
        frequency = table('FREQUENCY', [('FREQID', '1J', [1]), ('BANDFREQ', '1D', [0])])
        source = table('SOURCE', [('SOURCE_ID', '1J', [1]), ('SOURCE', '8A', ['TEST'])])
        uv = table('UV_DATA', [('DATE', '1D', [Time('2025-04-10').jd] * 2),
                               ('TIME', '1D', [9 / 24, 13 / 24]),
                               ('SOURCE_ID', '1J', [1, 1])])
        ff = self.raw / 'real.fits'
        fits.HDUList([fits.PrimaryHDU(), geometry, frequency, source, uv]).writeto(ff)
        local = self.antab()
        with patch('avica.pipe.core.find_tsys') as download:
            self.run_find([str(ff)])
        download.assert_not_called()
        with fits.open(ff) as hdus:
            self.assertEqual(len(hdus['SYSTEM_TEMPERATURE'].data), 2)
            self.assertEqual(list(hdus['SYSTEM_TEMPERATURE'].data['TSYS_1']), [30, 32])
            self.assertEqual(len(hdus['GAIN_CURVE'].data), 1)
            self.assertAlmostEqual(float(hdus['GAIN_CURVE'].data['SENS_1'][0]), 0.1)
        self.assertEqual(local.read_text(), ANTAB)


if __name__ == '__main__':
    unittest.main()
