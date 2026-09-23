from __future__ import annotations

from traceback import print_exc
import numpy as np
try:
    from casatools import table as _casatools_table
    CTABLE_BACKEND = "casatools"      # array columns: (..., nrow), e.g. DATA (ncorr, nchan, nrow)
    def ctable(path=None, readonly=True, **_):
        t = _casatools_table()
        if path is not None:
            t.open(path, nomodify=readonly)
        return t
except ImportError:
    from casacore.tables import table as ctable
    CTABLE_BACKEND = "casacore"       # array columns: (nrow, ...), e.g. DATA (nrow, nchan, ncorr)

class CasaMSMetadata:
    def __init__(self):
        self._vis = None
        self._tbvis = None
        self._spw = None
        self._ant = None
        self._fld = None
        self._obs = None
        self._ddesc = None

    def open(self, vis: str) -> None:
        self._vis = vis
        self._tbvis = ctable(vis, readonly=True, ack=False)
        self._spw = ctable(f"{vis}/SPECTRAL_WINDOW", readonly=True, ack=False)
        self._ant = ctable(f"{vis}/ANTENNA", readonly=True, ack=False)
        self._fld = ctable(f"{vis}/FIELD", readonly=True, ack=False)
        self._obs = ctable(f"{vis}/OBSERVATION", readonly=True, ack=False)
        self._ddesc = ctable(f"{vis}/DATA_DESCRIPTION", readonly=True, ack=False)

    def done(self) -> None:
        for t in (self._tbvis, self._spw, self._ant, self._fld, self._obs, self._ddesc):
            if t is not None:
                try:
                    t.close()
                except Exception:
                    print_exc()
        self._tbvis = self._spw = self._ant = self._fld = self._obs = self._ddesc = None
        self._vis = None

    close = done


    def _ddid_to_spw(self, ddid: int) -> int:
        return int(self._ddesc.getcol("SPECTRAL_WINDOW_ID")[ddid])

    def _spw_to_ddids(self, spw: int) -> list[int]:
        spw_col = self._ddesc.getcol("SPECTRAL_WINDOW_ID")
        return [int(i) for i, s in enumerate(spw_col) if int(s) == int(spw)]

    def spwsforfields(self) -> dict:
        """{field_id: sorted unique spws appearing in MAIN for that field}."""
        fid_col = self._tbvis.getcol("FIELD_ID")
        ddid_col = self._tbvis.getcol("DATA_DESC_ID")
        spw_map = self._ddesc.getcol("SPECTRAL_WINDOW_ID")
        out: dict[int, list[int]] = {}
        unique_fids = np.unique(fid_col)
        for fid in unique_fids:
            mask = fid_col == fid
            spws = np.unique(spw_map[ddid_col[mask]])
            out[int(fid)] = [int(s) for s in spws]
        return out

    def nobservations(self) -> int:
        return int(self._obs.nrows())

    def fieldnames(self) -> list[str]:
        return [str(n) for n in self._fld.getcol("NAME")]

    def scansforfield(self, field, obsid=-1, arrayid=-1) -> list[int]:
        fid = self.fieldsforname(field)
        if len(fid):
            fid = fid[0]
        else:
            return []
        sub = self._tbvis.query(f"FIELD_ID=={int(fid)}")
        scan_col = sub.getcol("SCAN_NUMBER")
        return [int(s) for s in np.unique(scan_col)]

    def scansforspws(self, obsid: int | None = None) -> dict:
        """{spw_id: sorted unique scans}, optionally restricted to obsid."""
        if obsid is None:
            sub = self._tbvis
            close_after = False
        else:
            sub = self._tbvis.query(f"OBSERVATION_ID=={int(obsid)}")
            close_after = True
        try:
            ddid_col = sub.getcol("DATA_DESC_ID")
            scan_col = sub.getcol("SCAN_NUMBER")
        finally:
            if close_after:
                sub.close()

        spw_map = self._ddesc.getcol("SPECTRAL_WINDOW_ID")
        spws = spw_map[ddid_col]
        out: dict[str, list[str]] = {}
        for spw in np.unique(spws):
            mask = spws == spw
            out[str(spw)] = [str(s) for s in np.unique(scan_col[mask])]
        return out

    def reffreq(self, spw: int) -> dict:
        """Mimic casatools shape: {'m0': {'value': hz, 'unit': 'Hz'}, ...}."""
        v = float(self._spw.getcol("REF_FREQUENCY")[int(spw)])
        return {"m0": {"value": v, "unit": "Hz"}, "refer": "LSRK", "type": "frequency"}

    def meanfreq(self, spw: int) -> float:
        chan_freq = self._spw.getcell("CHAN_FREQ", int(spw))
        return float(np.mean(chan_freq))

    def chanwidths(self, spw: int) -> np.ndarray:
        return np.asarray(self._spw.getcell("CHAN_WIDTH", int(spw)))

    def bandwidths(self, spw: int) -> float:
        return float(self._spw.getcol("TOTAL_BANDWIDTH")[int(spw)])

    def exposuretime(self, scan: int, spwid: int, obsid: int) -> dict:
        ddids = self._spw_to_ddids(spwid)
        if not ddids:
            raise ValueError(f"No DATA_DESC_ID maps to spw {spwid}")
        ddid_clause = ",".join(str(d) for d in ddids)
        q = (
            f"SCAN_NUMBER=={int(scan)} AND OBSERVATION_ID=={int(obsid)} "
            f"AND DATA_DESC_ID IN [{ddid_clause}]"
        )
        sub = self._tbvis.query(q)
        try:
            if sub.nrows() == 0:
                raise ValueError(f"No rows for scan={scan} spw={spwid} obs={obsid}")
            v = float(sub.getcol("EXPOSURE")[0])
        finally:
            sub.close()
        return {"value": v, "unit": "s"}

    def antennasforscan(self, scan: int) -> np.ndarray:
        sub = self._tbvis.query(f"SCAN_NUMBER=={int(scan)}")
        try:
            a1 = sub.getcol("ANTENNA1")
            a2 = sub.getcol("ANTENNA2")
        finally:
            sub.close()
        return np.unique(np.concatenate([a1, a2])).astype(int)

    def timesforscan(self, scan: int) -> np.ndarray:
        sub = self._tbvis.query(f"SCAN_NUMBER=={int(scan)}")
        try:
            t = np.unique(sub.getcol("TIME"))
        finally:
            sub.close()
        return t

    def antennanames(self, antid=None) -> list:
        names = self._ant.getcol("NAME")
        if antid is None:
            return [str(n) for n in names]
        if np.isscalar(antid):
            return [str(names[int(antid)])]
        return [str(names[int(i)]) for i in antid]

    def antennaids(self, name) -> np.ndarray:
        """Antenna IDs whose NAME matches. Accepts str or iterable of str."""
        names = self._ant.getcol("NAME")
        targets = {str(name)} if isinstance(name, str) else {str(n) for n in name}
        return np.array(
            [i for i, n in enumerate(names) if str(n) in targets], dtype=int
        )

    def scannumbers(self) -> np.ndarray:
        """All unique scan numbers in MAIN."""
        return np.unique(self._tbvis.getcol("SCAN_NUMBER")).astype(int)

    def fieldsforscan(self, scan: int) -> np.ndarray:
        """Field IDs that appear in MAIN for the given scan."""
        sub = self._tbvis.query(f"SCAN_NUMBER=={int(scan)}")
        try:
            fids = np.unique(sub.getcol("FIELD_ID"))
        finally:
            sub.close()
        return fids.astype(int)

    def fieldsforsource(self, source:int = -1) -> dict:
        """{source_id: [field_ids]} from FIELD.SOURCE_ID."""
        fids = [source] if source != -1 else list(range(self._fld.nrows()))
        out: dict[int, list[int]] = {}
        for fid in fids:
            out.setdefault(int(fid), []).append(int(fid))
        return out

    def spwsforfield(self, field: str | int) -> np.ndarray:
        """SPW IDs that appear in MAIN rows of the given field."""
        fid = self.fieldsforname(field)
        if len(fid):
            fid = fid[0]
        else:
            return np.array([])
        sub = self._tbvis.query(f"FIELD_ID=={int(fid)}")
        try:
            ddids = np.unique(sub.getcol("DATA_DESC_ID"))
        finally:
            sub.close()
        spw_map = self._ddesc.getcol("SPECTRAL_WINDOW_ID")
        return np.unique(spw_map[ddids]).astype(int)

    def namesforfields(self, fid=None) -> list:
        """Names of given field IDs (or all if None)."""
        names = self._fld.getcol("NAME")
        if fid is None:
            return [str(n) for n in names]
        if np.isscalar(fid):
            return [str(names[int(fid)])]
        return [str(names[int(i)]) for i in fid]

    def fieldsforname(self, name: str) -> np.ndarray:
        """Field IDs whose NAME equals the given string."""
        names = self._fld.getcol("NAME")
        return np.array(
            [i for i, n in enumerate(names) if str(n) == str(name)], dtype=int
        )
