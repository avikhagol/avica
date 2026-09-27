"""Issue #59: result CSV named result__{target}__{project_code}__{workdir}.csv."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from avica.pipe.helpers import (
    find_result_csvs, legacy_result_csv_path, parse_result_csv_name,
    resolve_result_csv, result_csv_name, result_csv_path, safe_name_part,
)


class ResultCsvNameTest(unittest.TestCase):
    def test_pattern(self):
        self.assertEqual(result_csv_name("J0102+5824", "EY034", "wd_2"),
                         "result__J0102+5824__EY034__wd_2.csv")

    def test_round_trip(self):
        name = result_csv_name("0059+581", "BK123A", "wd")
        self.assertEqual(parse_result_csv_name(name),
                         dict(target="0059+581", project_code="BK123A", workdir="wd"))

    def test_single_underscores_survive(self):
        name = result_csv_name("src_a", "ey_034", "wd_10")
        self.assertEqual(parse_result_csv_name(name),
                         dict(target="src_a", project_code="ey_034", workdir="wd_10"))

    def test_unsafe_parts_are_cleaned(self):
        self.assertEqual(safe_name_part("A. Kumar / obs"), "A.-Kumar-obs")
        self.assertEqual(safe_name_part("a__b"), "a_b")
        self.assertEqual(safe_name_part(""), "unknown")
        name = result_csv_name("t__x", "P/1", "wd")
        self.assertIsNotNone(parse_result_csv_name(name))

    def test_non_matching_names(self):
        for name in ("J0102_result.csv", "result__a__b.csv", "result__a__b__c.txt",
                     "other__a__b__c.csv", "result____b__c.csv"):
            self.assertIsNone(parse_result_csv_name(name), name)

    def test_legacy_path(self):
        self.assertEqual(legacy_result_csv_path("reductions", "J0102"),
                         Path("reductions/J0102_result.csv"))


class FindResultCsvsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)

    def touch(self, target, project, wd, age):
        path = result_csv_path(self.dir, target, project, wd)
        path.write_text("name\n")
        t = time.time() - age
        os.utime(path, (t, t))
        return path

    def test_newest_first_and_filters(self):
        old = self.touch("J0102", "EY034", "wd", age=100)
        new = self.touch("J0102", "EY034", "wd_1", age=10)
        other_proj = self.touch("J0102", "BK123", "wd", age=50)
        self.touch("J9999", "EY034", "wd", age=1)
        (self.dir / "J0102_result.csv").write_text("name\n")

        self.assertEqual(find_result_csvs(self.dir, "J0102"), [new, other_proj, old])
        self.assertEqual(find_result_csvs(self.dir, "J0102", project_code="EY034"), [new, old])
        self.assertEqual(find_result_csvs(self.dir, "J0102", workdir="wd"), [other_proj, old])
        self.assertEqual(find_result_csvs(self.dir, "J0102", "BK123", "wd"), [other_proj])
        self.assertEqual(find_result_csvs(self.dir, "nothing"), [])


class ResolveResultCsvTest(unittest.TestCase):
    """The CLI must find the same workdir that setup_workdir will reuse, without creating one."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.target_dir = self.root / "reductions"
        self.template = self.root / "input_template"
        self.template.mkdir()
        self.names = ["ey034_1_1.IDI1", "ey034_1_1.IDI2"]
        for name in self.names:
            (self.source / name).write_text("input")
        p = patch("avica.pipe.helpers.get_project", return_value="EY034")
        p.start()
        self.addCleanup(p.stop)

    def wd(self, name, preprocessed=False):
        wd = self.target_dir / "EY034" / name
        (wd / "raw").mkdir(parents=True)
        (wd / "input_template").mkdir()
        for n in self.names:
            (wd / "raw" / n).write_text("x")
        if preprocessed:
            (wd / "avica.meta").mkdir()
            (wd / "avica.meta" / "fitsfiles_used.avica").write_text("{}")
        return wd

    def resolve(self):
        return resolve_result_csv(str(self.target_dir) + "/", "J0102", self.names,
                                  str(self.source) + "/", str(self.template))

    def test_no_workdir_yet(self):
        self.assertIsNone(self.resolve())
        self.assertFalse(self.target_dir.exists())

    def test_picks_reused_workdir(self):
        self.wd("wd")
        self.wd("wd_1", preprocessed=True)
        self.wd("wd_2")
        before = sorted(p.name for p in (self.target_dir / "EY034").iterdir())
        self.assertEqual(self.resolve().name, "result__J0102__EY034__wd_1.csv")
        self.assertEqual(sorted(p.name for p in (self.target_dir / "EY034").iterdir()), before)


if __name__ == "__main__":
    unittest.main()
