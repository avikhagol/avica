"""Configuration summaries should resolve the same file layers as pipe run."""

from importlib import import_module
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from rich.console import Console
from typer.testing import CliRunner

from avica.pipe.config import PipeConfig
from avica.pipe.core import PipelineContext


cli = import_module("avica.cli_new")


class ConfigSummaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="avica-summary-test-")
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
            patch.object(cli, "Console", lambda: Console(width=260, color_system=None)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        context_params = dict(PipelineContext.params)
        PipelineContext.reset_params()
        self.addCleanup(PipelineContext.params.update, context_params)
        self.addCleanup(PipelineContext.reset_params)
        self.runner = CliRunner()

    def write_config(self, directory, contents):
        path = directory / "avica.inp"
        path.write_text(contents)
        return path

    def summary(self, *args):
        result = self.runner.invoke(cli.avica_cli, ["pipe", "config", "--summary", *args])
        self.assertEqual(result.exit_code, 0, f"{result.output}\n{result.exception}")
        return [
            [cell.strip() for cell in line.split("│")[1:-1]]
            for line in result.output.splitlines()
            if "│" in line
        ]

    def assert_parameter(self, rows, name, value, source):
        matches = [row for row in rows if len(row) == 4 and row[1] == name]
        self.assertTrue(matches, f"No summary row for {name}")
        for row in matches:
            self.assertEqual(row[2:], [source, str(value)])

    def test_layers_overlay_and_summary_does_not_write(self):
        files = [
            self.write_config(self.global_dir, "size_limit = 111\ncasadir = /global/\n"),
            self.write_config(self.user_dir, "snr_threshold_phref = 222\ncasadir = /user/\n"),
            self.write_config(self.local_dir, "target_dir = local-result\ncasadir = /local/\n"),
        ]
        before = {path: path.read_bytes() for path in files}
        rows = self.summary()
        self.assert_parameter(rows, "size_limit", 111, "global/core")
        self.assert_parameter(rows, "snr_threshold_phref", 222, "user/core")
        self.assert_parameter(rows, "target_dir", "local-result", "inpfile/core")
        self.assert_parameter(rows, "casadir", "/local/", "inpfile/core")
        self.assertEqual({path: path.read_bytes() for path in files}, before)

    def test_user_overrides_global_without_local_file(self):
        self.write_config(self.global_dir, "casadir = /global/\nsize_limit = 111\n")
        self.write_config(self.user_dir, "casadir = /user/\n")
        rows = self.summary()
        self.assert_parameter(rows, "casadir", "/user/", "user/core")
        self.assert_parameter(rows, "size_limit", 111, "global/core")
        self.assertFalse((self.local_dir / "avica.inp").exists())

    def test_global_survives_when_user_and_local_files_are_missing(self):
        self.write_config(self.global_dir, "casadir = /global/\n")
        self.assert_parameter(self.summary(), "casadir", "/global/", "global/core")

    def test_no_inpfile_skips_local_discovery(self):
        self.write_config(self.user_dir, "casadir = /user/\n")
        self.write_config(self.local_dir, "casadir = /local/\n")
        self.assert_parameter(self.summary("--no-inpfile"), "casadir", "/user/", "user/core")

    def test_explicit_input_overlays_user_and_replaces_local_selection(self):
        self.write_config(self.global_dir, "size_limit = 111\n")
        self.write_config(self.user_dir, "casadir = /user/\n")
        self.write_config(self.local_dir, "target_dir = local-result\n")
        explicit = self.root / "explicit.inp"
        explicit.write_text("target_dir = explicit-result\n")
        rows = self.summary("--no-inpfile", "--inpfile", str(explicit))
        self.assert_parameter(rows, "size_limit", 111, "global/core")
        self.assert_parameter(rows, "casadir", "/user/", "user/core")
        self.assert_parameter(rows, "target_dir", "explicit-result", "inpfile/core")

    def test_command_line_and_step_specific_sources(self):
        for directory, value in (
            (self.global_dir, "global"), (self.user_dir, "user"), (self.local_dir, "local")
        ):
            self.write_config(directory, f"casadir = /{value}/\npreprocess_fitsidi.removables = ['{value}.tmp']\n")
        rows = self.summary("casadir=/cli/", "preprocess_fitsidi.removables=['cli.tmp']")
        self.assert_parameter(rows, "casadir", "/cli/", "cli/core")
        step_row = next(row for row in rows if row[1] == "removables" and "cli.tmp" in row[3])
        self.assertEqual(step_row[2], "cli/step")

    def test_user_step_override_reports_user_source(self):
        self.write_config(self.global_dir, "preprocess_fitsidi.removables = ['global.tmp']\n")
        self.write_config(self.user_dir, "preprocess_fitsidi.removables = ['user.tmp']\n")
        rows = self.summary()
        step_row = next(row for row in rows if row[1] == "removables" and "user.tmp" in row[3])
        self.assertEqual(step_row[2], "user/step")

    def test_global_write_does_not_import_user_or_local_settings(self):
        self.write_config(self.global_dir, "casadir = /global/\nsize_limit = 111\n")
        user_file = self.write_config(self.user_dir, "casadir = /user/\nsize_limit = 222\n")
        local_file = self.write_config(self.local_dir, "casadir = /local/\nsize_limit = 333\n")
        before = {path: path.read_bytes() for path in (user_file, local_file)}
        result = self.runner.invoke(cli.avica_cli, ["pipe", "config", "--global", "casadir=/new/"])
        self.assertEqual(result.exit_code, 0, f"{result.output}\n{result.exception}")
        written = PipeConfig(self.global_dir / "avica.inp").to_dict()
        self.assertEqual(written["casadir"], "/new/")
        self.assertEqual(written["size_limit"], 111)
        self.assertEqual({path: path.read_bytes() for path in before}, before)


if __name__ == "__main__":
    unittest.main()
