"""Single-pol bands: detect the dead correlation so avica_avg can split with only the live one."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from casacore.tables import table, makescacoldesc, makearrcoldesc, maketabdesc

import avica.ms.compat as compat
import avica.ms.tables as tables
from avica.ms.tables import choose_live_correlation, dead_corr_mask, live_correlations

RR, LL = 5, 8


def _make_ms(path, dead_by_spw, nrow=40, nchan=8):
    """Tiny MS with 2 spws x [RR, LL]; dead_by_spw[spw] = corr index that is NaN + flagged."""
    main = maketabdesc([
        makescacoldesc("DATA_DESC_ID", 0), makescacoldesc("ANTENNA1", 0), makescacoldesc("ANTENNA2", 0),
        makearrcoldesc("FLAG", False, ndim=2), makearrcoldesc("DATA", 0j, ndim=2),
    ])
    nspw = len(dead_by_spw)
    t = table(str(path), main, nrow=nrow * nspw, ack=False)
    for spw, dead in enumerate(dead_by_spw):
        rows = range(spw * nrow, (spw + 1) * nrow)
        flag = np.zeros((nrow, nchan, 2), bool)
        data = np.ones((nrow, nchan, 2), complex)
        if dead is not None:
            flag[..., dead] = True
            data[..., dead] = np.nan
        t.putcol("DATA_DESC_ID", np.full(nrow, spw), rows.start, nrow)
        t.putcol("ANTENNA1", np.zeros(nrow, int), rows.start, nrow)
        t.putcol("ANTENNA2", np.ones(nrow, int), rows.start, nrow)
        t.putcol("FLAG", flag, rows.start, nrow)
        t.putcol("DATA", data, rows.start, nrow)

    dd = table(f"{path}/DATA_DESCRIPTION", maketabdesc([
        makescacoldesc("SPECTRAL_WINDOW_ID", 0), makescacoldesc("POLARIZATION_ID", 0)]), nrow=nspw, ack=False)
    dd.putcol("SPECTRAL_WINDOW_ID", np.arange(nspw))
    dd.putcol("POLARIZATION_ID", np.zeros(nspw, int))
    pol = table(f"{path}/POLARIZATION", maketabdesc([makearrcoldesc("CORR_TYPE", 0, ndim=1)]), nrow=1, ack=False)
    pol.putcell("CORR_TYPE", 0, np.array([RR, LL]))
    t.putkeyword("DATA_DESCRIPTION", f"Table: {path}/DATA_DESCRIPTION")
    t.putkeyword("POLARIZATION", f"Table: {path}/POLARIZATION")
    for tb in (dd, pol, t):
        tb.close()


@pytest.fixture(autouse=True)
def casacore_backend(monkeypatch):
    monkeypatch.setattr(compat, "CTABLE_BACKEND", "casacore")
    monkeypatch.setattr(tables, "ctable", table)


def test_dead_corr_mask_axis_order():
    flag = np.zeros((10, 4, 2), bool)
    flag[..., 0] = True                                   # casacore: (nrow, nchan, ncorr)
    assert dead_corr_mask(flag, np.ones_like(flag, complex), -1).tolist() == [True, False]
    ct = np.transpose(flag, (2, 1, 0))                    # casatools: (ncorr, nchan, nrow)
    assert dead_corr_mask(ct, np.ones_like(ct, complex), 0).tolist() == [True, False]


@pytest.mark.parametrize("dead_by_spw, expected", [
    ((0, 0), "LL"),        # K band: RR dead in every spw
    ((1, 1), "RR"),        # Q band: LL dead in every spw
    ((None, None), ""),    # dual-pol: keep both
    ((0, 1), ""),          # spws disagree: one mstransform selection cannot serve both
    ((0, None), ""),       # partially dual-pol band
])
def test_live_correlation_choice(dead_by_spw, expected):
    with tempfile.TemporaryDirectory() as tmp:
        ms = Path(tmp) / "t.ms"
        _make_ms(ms, dead_by_spw)
        live = live_correlations(ms, [0, 1], nchunks=3, chunk_rows=7)
        assert set(live) == {0, 1}
        assert choose_live_correlation(live) == expected


def test_only_requested_spws():
    with tempfile.TemporaryDirectory() as tmp:
        ms = Path(tmp) / "t.ms"
        _make_ms(ms, (0, 1))
        live = live_correlations(ms, [1])
        assert list(live) == [1]
        assert choose_live_correlation(live) == "RR"
