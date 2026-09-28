import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from avica.pipe.steps import _restore_modified_raw_fits, _should_restore_raw_fits


class PreprocessRawResetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.origin = self.root / 'origin'
        self.raw = self.root / 'wd' / 'raw'
        self.origin.mkdir()
        self.raw.mkdir(parents=True)
        self.source = self.origin / 'observation.idifits'
        self.local = self.raw / self.source.name
        self.source.write_text('original visibility data')

    def test_gate_is_single_target_or_force_reset(self):
        self.assertTrue(_should_restore_raw_fits(False, ['target']))
        self.assertTrue(_should_restore_raw_fits(True, ['one', 'two']))
        self.assertTrue(_should_restore_raw_fits('true', ['one', 'two']))
        self.assertFalse(_should_restore_raw_fits(False, ['one', 'two']))

    def test_modified_local_file_is_restored(self):
        self.local.write_text('filtered')

        restored = _restore_modified_raw_fits([self.local], [self.source])

        self.assertEqual(restored, [str(self.local)])
        self.assertEqual(self.local.read_text(), self.source.read_text())
        self.assertEqual(self.local.stat().st_mtime_ns, self.source.stat().st_mtime_ns)

    def test_unchanged_local_file_is_not_copied(self):
        from shutil import copy2
        copy2(self.source, self.local)

        with patch('avica.pipe.steps.shutil.copy2') as copy:
            restored = _restore_modified_raw_fits([self.local], [self.source])

        self.assertEqual(restored, [])
        copy.assert_not_called()

    def test_pristine_origin_symlink_is_not_replaced(self):
        self.local.symlink_to(self.source)

        restored = _restore_modified_raw_fits([self.local], [self.source])

        self.assertEqual(restored, [])
        self.assertTrue(self.local.is_symlink())


if __name__ == '__main__':
    unittest.main()
