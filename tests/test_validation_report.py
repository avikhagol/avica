"""Contract tests for FITS-IDI validators and the ValidationReport summary.

Why this exists
---------------
``ValidationReport.to_polars()`` builds one polars DataFrame from every
``ValidationResult``. Each validator stores different things in ``detail`` /
``bad_data`` (str, list[str], dict, whole numpy/FITS columns, ...). Polars
infers a column's dtype from the first rows, so a result whose payload has a
different type than earlier rows crashes the *printing* of the report, e.g.:

    polars.exceptions.ComputeError: could not append value: [0, 0, ... 0]
    of type: list[i64] to the builder

(BW106, preprocess_fitsidi, "fixing remaining fitsidi problems").

These tests run every registered validator's ``check()`` against a small
in-memory fake HDU list crafted so each one *does* report a problem, then feed
the real results into ValidationReport in several orders. They need no FITS
file, CASA or network.

When you add a validator, add a trigger for it in ``TRIGGERS`` below;
``test_every_registered_validator_has_a_trigger`` fails until you do.
"""

from __future__ import annotations

import itertools
import unittest

import numpy as np
import polars as pl

from avica.fitsidiutil import validation as V


# --------------------------------------------------------------------------
# Minimal stand-ins for FITSIDI's IdiHDUList / IdiHDU (only what check() uses)
# --------------------------------------------------------------------------
class FakeHDU:
    def __init__(self, columns=None, header=None):
        self._columns = dict(columns or {})
        self.header = dict(header or {})

    @property
    def cols(self):
        return list(self._columns)

    def __getitem__(self, col):
        return self._columns[col]

    def __contains__(self, col):
        return col in self._columns


class FakeHDUList:
    def __init__(self, hdus: dict, extra_byte_location=None, filename="fake.idifits"):
        self._hdus = dict(hdus)
        self.extra_byte_location = extra_byte_location
        self.filename = filename

    @property
    def names(self):
        return list(self._hdus)

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._hdus.values())[key]
        return self._hdus[key]


def _clean_hdul(**overrides):
    """A small, internally consistent FITS-IDI-like layout with no problems."""
    hdus = {
        "PRIMARY": FakeHDU(header={"NAXIS": 0, "EXTEND": True}),
        "ANTENNA": FakeHDU(
            {
                "ANNAME": np.array(["BR", "FD", "HN"]),
                "ANTENNA_NO": np.array([1, 2, 3]),
                "POLTYA": np.array(["R", "R", "R"]),
                "POLTYB": np.array(["L", "L", "L"]),
                "FREQID": np.array([1, 1, 1]),
            },
            header={"RDATE": "2013-06-03"},
        ),
        "SOURCE": FakeHDU(
            {
                "SOURCE": np.array(["3C84", "3C274", "OJ287"]),
                "SOURCE_ID": np.array([1, 2, 3]),
                "FREQID": np.array([1, 1, 1]),
            }
        ),
        "FREQUENCY": FakeHDU({"FREQID": np.array([1])}),
        "PHASE-CAL": FakeHDU({"ANTENNA_NO": np.array([1, 2, 3]), "ARRAY": np.array([1, 1, 1])}),
        "UV_DATA": FakeHDU({"ARRAY": np.array([1, 1])}, header={"DATE-OBS": "2013-06-03"}),
    }
    hdus.update(overrides)
    return FakeHDUList(hdus)


# code -> (hdu_name, key, hdul) that must make check() report need_fixing=True.
# The payloads mimic what real files produce (whole int/str columns, etc.).
TRIGGERS = {
    "extra_byte": lambda: ("PRIMARY", "", FakeHDUList(_clean_hdul()._hdus, extra_byte_location=12345)),
    "col_spell": lambda: (
        "SOURCE",
        "SOURCE_ID",
        _clean_hdul(SOURCE=FakeHDU({"SOURCE": np.array(["3C84"]), "SOURCE ID": np.array([1])})),
    ),
    "binary": lambda: (
        "ANTENNA",
        "ANNAME",
        _clean_hdul(ANTENNA=FakeHDU({"ANNAME": np.array(["BR\\x00", "FD", "HN"]), "ANTENNA_NO": np.array([1, 2, 3])})),
    ),
    "empty": lambda: (
        "ANTENNA",
        "POLTYB",
        _clean_hdul(ANTENNA=FakeHDU({"ANNAME": np.array(["BR", "FD"]), "POLTYB": np.array(["", ""])})),
    ),
    "duplicate": lambda: (
        "SOURCE",
        "",
        _clean_hdul(SOURCE=FakeHDU({"SOURCE": np.array(["3C84", "3C84", "OJ287"]), "SOURCE_ID": np.array([1, 2, 3])})),
    ),
    "zeros": lambda: (
        "SOURCE",
        "",
        _clean_hdul(SOURCE=FakeHDU({"SOURCE": np.array(["0716", "3C84"]), "SOURCE_ID": np.array([1, 2])})),
    ),
    # PHASE-CAL references antenna 9, which is not in the ANTENNA table
    "anmap": lambda: (
        "PHASE-CAL",
        "ANTENNA_NO",
        _clean_hdul(**{"PHASE-CAL": FakeHDU({"ANTENNA_NO": np.array([1, 2, 9])})}),
    ),
    # the BW106 case: an all-zeros int FREQID column after splitting
    "multifreqid": lambda: (
        "SOURCE",
        "",
        _clean_hdul(SOURCE=FakeHDU({"SOURCE": np.array(["3C84"] * 50), "FREQID": np.zeros(50, dtype=np.int64)})),
    ),
    "date": lambda: ("UV_DATA", "", _clean_hdul(UV_DATA=FakeHDU({}, header={"DATE-OBS": "03/06/13"}))),
    "primary": lambda: ("PRIMARY", "", _clean_hdul(PRIMARY=FakeHDU(header={"NAXIS": 2}))),
}


# Validators with a known, not-yet-fixed bug. They are left out of the generic
# tests below and covered by KnownBugTests (expectedFailure) instead, so the
# suite stays green but flips to "unexpected success" once the bug is fixed —
# then delete the entry here and the matching KnownBugTests method.
KNOWN_BROKEN = {
    # check_missing_ant() compares ANTENNA.ANNAME (strings) against the missing
    # antenna *number*, so the masks are all False, and check() returns
    # need_fixing=sum(list_of_masks)>0, i.e. a numpy bool *array*. Result: a
    # missing antenna is never reported, and with >1 ANTENNA row the pipeline's
    # `if results.need_fixing and fix:` would raise "truth value is ambiguous".
    "anmap",
}


def _registered_validators():
    # _register_defaults() only instantiates classes; no file is opened.
    return V.FITSIDIValidator("unused.idifits").validators


def _triggered_results(include_broken=False):
    results = {}
    for code, validator in _registered_validators().items():
        if code in KNOWN_BROKEN and not include_broken:
            continue
        hdu_name, key, hdul = TRIGGERS[code]()
        results[code] = validator.check(hdu_name, key, hdul)
    return results


def _clean_results():
    """Results from running every validator over a problem-free layout."""
    hdul = _clean_hdul()
    out = []
    for hdu_name, columns in V.FITSIDIValidator("unused.idifits").issues:
        if hdu_name not in hdul.names:
            continue
        for code, validator in _registered_validators().items():
            if code in KNOWN_BROKEN:
                continue
            keys = [""] if validator.scope in ("header", "data") else columns
            for key in keys:
                out.append(validator.check(hdu_name, key, hdul))
    return out


def _assert_report_renders(testcase, results, label=""):
    report = V.ValidationReport(results)
    try:
        df = report.to_polars()
        summary = report.summary()
        text = repr(report)
    except Exception as exc:  # pragma: no cover - failure path
        testcase.fail(
            f"ValidationReport failed to render {label}: {type(exc).__name__}: {exc}\n"
            f"payload types: {[(r.code, type(r.detail).__name__, type(r.bad_data).__name__) for r in results]}"
        )
    testcase.assertEqual(df.height, len(results))
    testcase.assertIsInstance(summary, pl.DataFrame)
    testcase.assertIn("hdu", text)


class ValidatorCoverageTests(unittest.TestCase):
    def test_every_registered_validator_has_a_trigger(self):
        missing = set(_registered_validators()) - set(TRIGGERS)
        self.assertFalse(
            missing,
            f"new validator(s) {sorted(missing)} have no entry in TRIGGERS in "
            f"{__file__}; add one so their results are checked against ValidationReport",
        )


class ValidationResultContractTests(unittest.TestCase):
    """Shape of what each validator's check() returns."""

    def test_triggers_actually_trigger(self):
        for code, res in _triggered_results().items():
            with self.subTest(code=code):
                self.assertTrue(bool(np.all(res.need_fixing)), f"trigger for {code!r} no longer reports a problem")

    def test_need_fixing_is_a_scalar_bool(self):
        # pipeline does `if results.need_fixing and fix:` -> must not be an array
        for code, res in list(_triggered_results().items()) + [(r.code, r) for r in _clean_results()]:
            with self.subTest(code=code, hdu=res.hdu, key=res.key):
                self.assertIsInstance(res.need_fixing, (bool, np.bool_), f"need_fixing is {type(res.need_fixing).__name__}")

    def test_scalar_fields_are_strings(self):
        for code, res in _triggered_results().items():
            with self.subTest(code=code):
                for name in ("code", "hdu", "key", "msg"):
                    self.assertIsInstance(getattr(res, name), str, f"{name} is {type(getattr(res, name)).__name__}")


class ValidationReportRenderTests(unittest.TestCase):
    """ValidationReport must print whatever mix of results the validators produce."""

    def test_empty_report(self):
        self.assertEqual(V.ValidationReport().summary(), "No issues found.")

    def test_clean_run_renders(self):
        _assert_report_renders(self, _clean_results(), "clean run")

    def test_each_triggered_result_alone(self):
        for code, res in _triggered_results().items():
            with self.subTest(code=code):
                _assert_report_renders(self, [res], code)

    def test_every_ordered_pair_of_triggered_results(self):
        # polars infers dtype from the first rows, so order matters
        triggered = _triggered_results()
        for (a, ra), (b, rb) in itertools.permutations(triggered.items(), 2):
            with self.subTest(first=a, second=b):
                _assert_report_renders(self, [ra, rb], f"{a} then {b}")

    def test_triggered_results_mixed_into_clean_run(self):
        # closest to the real failure: many clean rows, then problems
        clean, triggered = _clean_results(), list(_triggered_results().values())
        _assert_report_renders(self, clean + triggered, "clean + triggered")
        _assert_report_renders(self, triggered + clean, "triggered + clean")
        _assert_report_renders(self, list(reversed(triggered)) + clean, "reversed triggered + clean")

    def test_summary_counts(self):
        triggered = _triggered_results()
        summary = V.ValidationReport(list(triggered.values())).summary()
        self.assertEqual(int(summary["fixable"].sum()), len(triggered))
        self.assertEqual(int(summary["total"].sum()), len(triggered))


class KnownBugTests(unittest.TestCase):
    """Each test here documents a bug in KNOWN_BROKEN and is expected to fail."""

    @unittest.expectedFailure
    def test_anmap_reports_missing_antenna_as_scalar_bool(self):
        res = _triggered_results(include_broken=True)["anmap"]
        self.assertIsInstance(res.need_fixing, (bool, np.bool_))
        self.assertTrue(res.need_fixing)
        _assert_report_renders(self, [res] + list(_triggered_results().values()), "anmap + others")


class OtherReprTests(unittest.TestCase):
    def test_validator_and_issue_list_repr(self):
        val = V.FITSIDIValidator("unused.idifits")
        self.assertIn("code", repr(val))
        self.assertIn("class", repr(val.issues))


if __name__ == "__main__":
    unittest.main()
