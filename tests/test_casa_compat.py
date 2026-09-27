
from __future__ import annotations

import os
import sys
import shutil
import tempfile
from pathlib import Path

import importlib.util

import numpy as np
import pytest

from casacore.tables import (
    table,
    makescacoldesc as makescalarcoldesc,
    makearrcoldesc as makearraycoldesc,
    maketabdesc,
)


def _load_compat_module():
    path = Path(__file__).resolve().parents[1] / "src" / "avica" / "ms" / "compat.py"
    spec = importlib.util.spec_from_file_location("_avica_casa_compat", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_compat = _load_compat_module()
MSMetadata = _compat.CasaMSMetadata


# ---------------------------------------------------------------------------
# Fixture: minimal MS layout
#
#   1 observation, 3 antennas, 2 fields, 2 spws (1:1 with ddids),
#   2 scans. MAIN holds 4 rows: scan 1 has two ddids with antennas (0,1),
#   scan 2 has two ddids with antennas (1,2). Field 0 -> scan 1, field 1 -> scan 2.
# ---------------------------------------------------------------------------

ANT_NAMES = ["AN1", "AN2", "AN3"]
FIELD_NAMES = ["FIELD0", "FIELD1"]
SPW_REF_FREQS = [1.0e9, 5.0e9]                # Hz
SPW_CHAN_FREQS = [
    np.linspace(1.0e9, 1.001e9, 4),           # spw 0: 4 channels
    np.linspace(5.0e9, 5.002e9, 4),           # spw 1: 4 channels
]
SPW_CHAN_WIDTHS = [
    np.full(4, 250e3),                        # 250 kHz/chan
    np.full(4, 500e3),                        # 500 kHz/chan
]
SPW_TOTAL_BW = [1.0e6, 2.0e6]                 # Hz

# (obsid, scan, ddid, ant1, ant2, time, exposure, field)
MAIN_ROWS = [
    (0, 1, 0, 0, 1, 100.0, 2.0, 0),
    (0, 1, 1, 0, 1, 100.0, 2.0, 0),
    (0, 2, 0, 1, 2, 200.0, 4.0, 1),
    (0, 2, 1, 1, 2, 200.0, 4.0, 1),
]


def _make_main(vis: str) -> None:
    desc = maketabdesc([
        makescalarcoldesc("TIME", 0.0),
        makescalarcoldesc("FIELD_ID", 0),
        makescalarcoldesc("DATA_DESC_ID", 0),
        makescalarcoldesc("SCAN_NUMBER", 0),
        makescalarcoldesc("OBSERVATION_ID", 0),
        makescalarcoldesc("ANTENNA1", 0),
        makescalarcoldesc("ANTENNA2", 0),
        makescalarcoldesc("EXPOSURE", 0.0),
    ])
    t = table(vis, desc, nrow=len(MAIN_ROWS), ack=False)
    obsid, scan, ddid, a1, a2, time_, expt, fld = zip(*MAIN_ROWS)
    t.putcol("OBSERVATION_ID", list(obsid))
    t.putcol("SCAN_NUMBER", list(scan))
    t.putcol("DATA_DESC_ID", list(ddid))
    t.putcol("ANTENNA1", list(a1))
    t.putcol("ANTENNA2", list(a2))
    t.putcol("TIME", list(time_))
    t.putcol("EXPOSURE", list(expt))
    t.putcol("FIELD_ID", list(fld))
    t.close()


def _make_spw(path: str) -> None:
    desc = maketabdesc([
        makescalarcoldesc("REF_FREQUENCY", 0.0),
        makescalarcoldesc("TOTAL_BANDWIDTH", 0.0),
        makearraycoldesc("CHAN_FREQ", 0.0, ndim=1),
        makearraycoldesc("CHAN_WIDTH", 0.0, ndim=1),
    ])
    t = table(path, desc, nrow=len(SPW_REF_FREQS), ack=False)
    t.putcol("REF_FREQUENCY", list(SPW_REF_FREQS))
    t.putcol("TOTAL_BANDWIDTH", list(SPW_TOTAL_BW))
    for i in range(len(SPW_REF_FREQS)):
        t.putcell("CHAN_FREQ", i, SPW_CHAN_FREQS[i])
        t.putcell("CHAN_WIDTH", i, SPW_CHAN_WIDTHS[i])
    t.close()


def _make_ant(path: str) -> None:
    desc = maketabdesc([makescalarcoldesc("NAME", "")])
    t = table(path, desc, nrow=len(ANT_NAMES), ack=False)
    t.putcol("NAME", list(ANT_NAMES))
    t.close()


def _make_field(path: str) -> None:
    desc = maketabdesc([makescalarcoldesc("NAME", "")])
    t = table(path, desc, nrow=len(FIELD_NAMES), ack=False)
    t.putcol("NAME", list(FIELD_NAMES))
    t.close()


def _make_field_with_source(path: str) -> None:
    """Field subtable with NAME + SOURCE_ID. Replaces _make_field at fixture build time."""
    desc = maketabdesc([
        makescalarcoldesc("NAME", ""),
        makescalarcoldesc("SOURCE_ID", 0),
    ])
    t = table(path, desc, nrow=len(FIELD_NAMES), ack=False)
    t.putcol("NAME", list(FIELD_NAMES))
    t.putcol("SOURCE_ID", list(range(len(FIELD_NAMES))))   # 1:1 source<->field
    t.close()


def _make_observation(path: str) -> None:
    desc = maketabdesc([makescalarcoldesc("OBSERVER", "")])
    t = table(path, desc, nrow=1, ack=False)
    t.putcol("OBSERVER", ["test"])
    t.close()


def _make_data_description(path: str) -> None:
    desc = maketabdesc([makescalarcoldesc("SPECTRAL_WINDOW_ID", 0)])
    # 1:1 mapping: ddid i -> spw i
    n = len(SPW_REF_FREQS)
    t = table(path, desc, nrow=n, ack=False)
    t.putcol("SPECTRAL_WINDOW_ID", list(range(n)))
    t.close()


@pytest.fixture(scope="module")
def mini_ms() -> str:
    tmp = tempfile.mkdtemp(prefix="avica_test_ms_")
    vis = os.path.join(tmp, "mini.ms")
    os.makedirs(vis, exist_ok=False)
    try:
        _make_main(vis)
        _make_spw(f"{vis}/SPECTRAL_WINDOW")
        _make_ant(f"{vis}/ANTENNA")
        _make_field_with_source(f"{vis}/FIELD")
        _make_observation(f"{vis}/OBSERVATION")
        _make_data_description(f"{vis}/DATA_DESCRIPTION")
        yield vis
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture()
def msmd(mini_ms):
    md = MSMetadata()
    md.open(mini_ms)
    yield md
    md.done()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_open_and_done_idempotent(mini_ms):
    md = MSMetadata()
    md.open(mini_ms)
    md.done()
    # done() twice should not raise
    md.done()


def test_nobservations(msmd):
    assert msmd.nobservations() == 1


def test_spwsforfields(msmd):
    out = msmd.spwsforfields()
    # Both fields appear with both spws (via ddid 0 and 1).
    # casatools returns a record: field-ID keys are strings.
    assert out == {"0": [0, 1], "1": [0, 1]}


def test_scansforspws_all(msmd):
    out = msmd.scansforspws()
    # Both spws appear in scans 1 and 2.
    # casatools: spw-ID keys are strings, scan numbers are integers.
    assert set(out.keys()) == {"0", "1"}
    assert out["0"] == [1, 2]
    assert out["1"] == [1, 2]


def test_scansforspws_obsid(msmd):
    out = msmd.scansforspws(obsid=0)
    assert out == {"0": [1, 2], "1": [1, 2]}


def test_reffreq_shape_matches_casatools(msmd):
    r0 = msmd.reffreq(0)
    assert r0["m0"]["value"] == pytest.approx(SPW_REF_FREQS[0])
    assert r0["m0"]["unit"] == "Hz"
    assert "type" in r0
    r1 = msmd.reffreq(1)
    assert r1["m0"]["value"] == pytest.approx(SPW_REF_FREQS[1])


def test_meanfreq(msmd):
    expected = float(np.mean(SPW_CHAN_FREQS[0]))
    assert msmd.meanfreq(0) == pytest.approx(expected)


def test_chanwidths(msmd):
    cw = msmd.chanwidths(1)
    assert isinstance(cw, np.ndarray)
    np.testing.assert_allclose(cw, SPW_CHAN_WIDTHS[1])


def test_bandwidths(msmd):
    assert msmd.bandwidths(0) == pytest.approx(SPW_TOTAL_BW[0])
    assert msmd.bandwidths(1) == pytest.approx(SPW_TOTAL_BW[1])


def test_exposuretime_shape_and_value(msmd):
    e = msmd.exposuretime(scan=1, spwid=0, obsid=0)
    assert e == {"value": pytest.approx(2.0), "unit": "s"}
    e2 = msmd.exposuretime(scan=2, spwid=1, obsid=0)
    assert e2["value"] == pytest.approx(4.0)


def test_exposuretime_missing_raises(msmd):
    with pytest.raises(ValueError):
        msmd.exposuretime(scan=99, spwid=0, obsid=0)


def test_antennasforscan(msmd):
    a1 = msmd.antennasforscan(1)
    np.testing.assert_array_equal(np.sort(a1), np.array([0, 1]))
    a2 = msmd.antennasforscan(2)
    np.testing.assert_array_equal(np.sort(a2), np.array([1, 2]))


def test_timesforscan(msmd):
    t1 = msmd.timesforscan(1)
    np.testing.assert_allclose(t1, [100.0])
    t2 = msmd.timesforscan(2)
    np.testing.assert_allclose(t2, [200.0])


def test_antennanames_all(msmd):
    assert msmd.antennanames() == ANT_NAMES


def test_antennanames_scalar(msmd):
    assert msmd.antennanames(0) == ["AN1"]
    assert msmd.antennanames(2) == ["AN3"]


def test_antennanames_list(msmd):
    assert msmd.antennanames([0, 2]) == ["AN1", "AN3"]


def test_ctable_opens_subtable(mini_ms):
    """Sanity check: the compat ctable() factory works on a subtable."""
    t = _compat.ctable(f"{mini_ms}/ANTENNA", readonly=True, ack=False)
    try:
        assert list(t.getcol("NAME")) == ANT_NAMES
    finally:
        t.close()


# ---------------------------------------------------------------------------
# Tests for the second batch of methods (used by ms/__init__.py)
# ---------------------------------------------------------------------------

def test_antennaids_scalar(msmd):
    np.testing.assert_array_equal(msmd.antennaids("AN1"), np.array([0]))
    np.testing.assert_array_equal(msmd.antennaids("AN3"), np.array([2]))


def test_antennaids_list(msmd):
    np.testing.assert_array_equal(
        np.sort(msmd.antennaids(["AN1", "AN3"])), np.array([0, 2])
    )


def test_antennaids_unknown_returns_empty(msmd):
    assert msmd.antennaids("NOPE").size == 0


def test_scannumbers(msmd):
    np.testing.assert_array_equal(msmd.scannumbers(), np.array([1, 2]))


def test_fieldsforscan(msmd):
    np.testing.assert_array_equal(msmd.fieldsforscan(1), np.array([0]))
    np.testing.assert_array_equal(msmd.fieldsforscan(2), np.array([1]))


def test_fieldsforsource(msmd):
    # Fixture has 1:1 mapping: source 0 -> field 0, source 1 -> field 1
    assert msmd.fieldsforsource() == {0: [0], 1: [1]}


def test_spwsforfield(msmd):
    # Both fields have ddids 0 and 1 in MAIN, mapping to spws 0 and 1.
    # casatools accepts a zero-based field ID (int) or a field name (str).
    np.testing.assert_array_equal(msmd.spwsforfield(0), np.array([0, 1]))
    np.testing.assert_array_equal(msmd.spwsforfield(1), np.array([0, 1]))
    np.testing.assert_array_equal(msmd.spwsforfield("FIELD1"), np.array([0, 1]))
    assert msmd.spwsforfield(99).size == 0
    assert msmd.spwsforfield("NOPE").size == 0


def test_scansforfield_id_or_name(msmd):
    assert msmd.scansforfield(0) == [1]
    assert msmd.scansforfield("FIELD1") == [2]
    assert msmd.scansforfield("NOPE") == []


def test_namesforfields_all(msmd):
    assert msmd.namesforfields() == FIELD_NAMES


def test_namesforfields_scalar(msmd):
    assert msmd.namesforfields(0) == ["FIELD0"]
    assert msmd.namesforfields(1) == ["FIELD1"]


def test_namesforfields_list(msmd):
    assert msmd.namesforfields([1, 0]) == ["FIELD1", "FIELD0"]


def test_fieldsforname(msmd):
    np.testing.assert_array_equal(msmd.fieldsforname("FIELD0"), np.array([0]))
    np.testing.assert_array_equal(msmd.fieldsforname("FIELD1"), np.array([1]))


def test_fieldsforname_unknown(msmd):
    assert msmd.fieldsforname("NOPE").size == 0
