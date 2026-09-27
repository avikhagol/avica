"""Writing a config touches exactly one layer and preserves the rest of it."""

from importlib import import_module
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from avica.pipe.config import PipeConfig


cli = import_module("avica.cli_new")


class ConfigWriteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="avica-write-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.global_dir = self.root / "package"
        self.user_dir = self.root / "user"
        self.local_dir = self.root / "work"
        for directory in (self.global_dir, self.user_dir, self.local_dir):
            directory.mkdir()
        previous_dir = Path.cwd()
        os.chdir(self.local_dir)
        self.addCleanup(os.chdir, previous_dir)
        for patcher in (
            patch.object(cli, "avica_pkg_dir", str(self.global_dir)),
            patch.object(cli, "avica_data_dir", str(self.user_dir)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.runner = CliRunner()

    def write_config(self, directory, contents):
        path = directory / "avica.inp"
        path.write_text(contents)
        return path

    def config(self, *args, exit_code=0):
        result = self.runner.invoke(cli.avica_cli, ["pipe", "config", *args])
        self.assertEqual(result.exit_code, exit_code, f"{result.output}\n{result.exception}")
        return result

    def user_params(self):
        return PipeConfig(self.user_dir / "avica.inp").to_dict()

    def test_default_merges_instead_of_truncating(self):
        self.write_config(self.user_dir, "casadir = /user/\nsize_limit = 222\ntarget_dir = keep-me/\n")
        self.config("--default", "casadir=/new/")
        written = self.user_params()
        self.assertEqual(written["casadir"], "/new/")
        self.assertEqual(written["size_limit"], 222)
        self.assertEqual(written["target_dir"], "keep-me/")

    def test_default_does_not_import_builtin_or_global_layers(self):
        self.write_config(self.global_dir, "flux_calibrator = /global/\nsize_limit = 111\n")
        self.write_config(self.user_dir, "casadir = /user/\n")
        self.config("--default", "casadir=/new/")
        keys = set(self.user_params())
        self.assertEqual(keys, {"casadir"})

    def test_default_ignores_a_local_config_file(self):
        self.write_config(self.local_dir, "casadir = /local/\nsnr_threshold_phref = 333\n")
        self.write_config(self.user_dir, "casadir = /user/\n")
        self.config("--default", "target_dir=from-cli/")
        written = self.user_params()
        self.assertEqual(written["casadir"], "/user/")
        self.assertEqual(written["target_dir"], "from-cli/")
        self.assertNotIn("snr_threshold_phref", written)

    def test_default_on_a_fresh_file_writes_only_the_given_keys(self):
        self.write_config(self.global_dir, "size_limit = 111\n")
        self.config("--default", "casadir=/new/")
        self.assertEqual(dict(self.user_params()), {"casadir": "/new/"})

    def test_inpfile_overlays_the_existing_user_file(self):
        self.write_config(self.user_dir, "casadir = /user/\ntarget_dir = keep-me/\n")
        explicit = self.root / "explicit.inp"
        explicit.write_text("casadir = /explicit/\nsize_limit = 444\n")
        self.config("--default", "--inpfile", str(explicit))
        written = self.user_params()
        self.assertEqual(written["casadir"], "/explicit/")
        self.assertEqual(written["size_limit"], 444)
        self.assertEqual(written["target_dir"], "keep-me/")

    def test_comments_ordering_and_type_suffixes_survive(self):
        source = (
            "# user defaults\n"
            "casadir      = /user/\n"
            "\n"
            "size_limit   = 10 # str\n"
            "target_dir   = keep-me/\n"
        )
        self.write_config(self.user_dir, source)
        self.config("--default", "size_limit=20")
        text = (self.user_dir / "avica.inp").read_text()
        self.assertIn("# user defaults", text)
        self.assertIn("size_limit   = 20 # str", text)
        self.assertIn("casadir      = /user/", text)
        self.assertEqual(self.user_params()["size_limit"], "20")
        self.assertLess(text.index("casadir"), text.index("size_limit"))

    def test_untouched_values_are_not_re_rendered(self):
        # `read_inputfile` glob-expands a `*` value on the way in, so a value
        # nobody asked to change must survive as its own line rather than being
        # round-tripped through the parser.
        self.write_config(self.user_dir, "removables_pattern = /data/*.ms\ncasadir = /user/\n")
        self.config("--default", "casadir=/new/")
        text = (self.user_dir / "avica.inp").read_text()
        self.assertIn("removables_pattern = /data/*.ms", text)

    def test_previous_contents_are_kept_as_a_backup(self):
        original = "casadir = /user/\n"
        self.write_config(self.user_dir, original)
        self.config("--default", "casadir=/new/")
        self.assertEqual((self.user_dir / "avica.inp.bak").read_text(), original)

    def test_local_write_updates_in_place(self):
        self.write_config(self.local_dir, "# local\ncasadir = /local/\ntarget_dir = keep-me/\n")
        self.config("casadir=/new/")
        text = (self.local_dir / "avica.inp").read_text()
        self.assertIn("# local", text)
        local = PipeConfig(self.local_dir / "avica.inp").to_dict()
        self.assertEqual(local["casadir"], "/new/")
        self.assertEqual(local["target_dir"], "keep-me/")
        self.assertFalse((self.user_dir / "avica.inp").exists())

    def test_nothing_to_write_is_rejected(self):
        self.write_config(self.user_dir, "casadir = /user/\n")
        self.config("--default", exit_code=2)
        self.assertEqual(self.user_params()["casadir"], "/user/")


if __name__ == "__main__":
    unittest.main()
