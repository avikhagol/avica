import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from avica.pipe.helpers import setup_workdir


class WorkdirReuseTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.target = self.root / 'reductions'
        self.template = self.root / 'input_template'
        self.template.mkdir()
        (self.template / 'observation.inp').write_text('template')
        self.names = [f'ey034_1_1.IDI{i}' for i in range(1, 8)]
        for name in self.names:
            (self.source / name).write_text('input')
        project = patch('avica.pipe.helpers.get_project', return_value='EY034')
        project.start()
        self.addCleanup(project.stop)

    def wd(self, name, filenames=None, preprocessed=False):
        wd = self.target / 'EY034' / name
        (wd / 'raw').mkdir(parents=True)
        (wd / 'input_template').mkdir()
        for filename in self.names if filenames is None else filenames:
            (wd / 'raw' / filename).write_text('processed')
        if preprocessed:
            (wd / 'avica.meta').mkdir()
            (wd / 'avica.meta' / 'fitsfiles_used.avica').write_text('{}')
        return wd

    def setup(self, names=None):
        return setup_workdir(None, str(self.target) + '/', names or self.names,
                             list(self.source.iterdir()), str(self.template))

    def test_idi_files_and_extra_antab_reused_repeatedly(self):
        wd = self.wd('wd')
        (wd / 'raw' / 'ey034.antab').write_text('calibration')
        first = self.setup()
        self.assertEqual(first, self.setup())
        self.assertEqual(first[0], str(wd / 'input_template'))
        self.assertTrue(all(Path(ff).read_text() == 'processed' for ff in first[1]))
        self.assertEqual(list(wd.parent.iterdir()), [wd])

    def test_successful_wd3_preferred_to_unprocessed_wd4(self):
        self.wd('wd')
        selected = self.wd('wd_3', preprocessed=True)
        self.wd('wd_4')
        self.assertEqual(self.setup()[0], str(selected / 'input_template'))

    def test_generation_order_is_numeric_within_same_status(self):
        self.wd('wd_9', preprocessed=True)
        selected = self.wd('wd_10', preprocessed=True)
        self.assertEqual(self.setup()[0], str(selected / 'input_template'))

    def test_incomplete_directory_creates_one_new_complete_directory(self):
        old = self.wd('wd', self.names[:-1], preprocessed=True)
        (old.parent / 'wd_L').mkdir()
        selected, files = self.setup()
        self.assertEqual(selected, str(old.parent / 'wd_1' / 'input_template'))
        self.assertEqual(len(files), 7)
        self.assertEqual(self.setup(), (selected, files))

    def test_exact_basename_and_arbitrary_extension(self):
        for name in ['visibility.custom', 'visibility.custom.backup']:
            (self.source / name).write_text(name)
        selected = self.wd('wd', ['visibility.custom'])
        folder, files = self.setup(['visibility.custom'])
        self.assertEqual(folder, str(selected / 'input_template'))
        self.assertEqual(files, [str(selected / 'raw' / 'visibility.custom')])

    def test_missing_exact_name_rejected_before_directory_creation(self):
        with self.assertRaisesRegex(ValueError, 'not found'):
            self.setup(['ey034_1_1.IDI'])
        self.assertFalse(self.target.exists())

    def test_initial_setup_reused_on_second_call(self):
        folder, files = self.setup()
        self.assertEqual(Path(folder).parent.name, 'wd')
        self.assertTrue(all(Path(ff).is_file() for ff in files))
        self.assertEqual(self.setup(), (str(folder), files))


if __name__ == '__main__':
    unittest.main()
