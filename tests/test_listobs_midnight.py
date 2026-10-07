"""Scan times must follow the UV_DATA DATE column across midnight (#74)."""
import tempfile
import unittest
from pathlib import Path

from astropy.io import fits
from astropy.time import Time

from avica.fitsidiutil.obs import ObservationSummary

SECOND = 1 / 86400


def make_idi(path, rdate, rows):
    """Minimal FITS-IDI; rows: [(DATE jd, TIME days, SOURCE_ID)]."""
    def table(name, columns):
        hdu = fits.BinTableHDU.from_columns([fits.Column(name=n, format=f, array=a) for n, f, a in columns], name=name)
        hdu.header['RDATE'] = rdate
        return hdu

    primary = fits.PrimaryHDU()
    primary.header['DATE-OBS'] = rdate
    frequency = table('FREQUENCY', [('FREQID', '1J', [1]), ('BANDFREQ', '2D', [[0.0, 32e6]])])
    source = table('SOURCE', [('SOURCE_ID', '1J', [1, 2]), ('SOURCE', '16A', ['3C84', '3C274'])])
    dates, times, sids = zip(*rows)
    uv = table('UV_DATA', [('DATE', '1D', dates), ('TIME', '1D', times), ('SOURCE_ID', '1J', sids),
                           ('FREQID', '1J', [1] * len(rows)), ('INTTIM', '1D', [2.0] * len(rows))])
    uv.header['DATE-OBS'] = rdate
    fits.HDUList([primary, frequency, source, uv]).writeto(path)


def scan(jd, start, end, sid):
    """Two rows: start and end, as (DATE, TIME) offsets in days from jd."""
    return [(jd + int(start), start - int(start), sid), (jd + int(end), end - int(end), sid)]


def hms(h, m, s=0):
    return (h * 3600 + m * 60 + s) * SECOND


class ListObsMidnightTests(unittest.TestCase):
    def summarize(self, rdate, rows):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'test.idifits')
            make_idi(path, rdate, rows)
            summary = ObservationSummary(fitsfilepaths=[path])
            summary.get()
        return [(s['start_time'][:19], s['end_time'][:19], s['source_id'])
                for s in summary.dic_summary['listobs'].values()]

    def test_date_rolls_over_and_midnight_scan_is_kept(self):
        jd = Time('2013-06-03').jd
        rows = (scan(jd, hms(23, 30), hms(23, 40), 1)
                # crosses midnight: DATE increments and TIME resets inside the scan
                + [(jd, hms(23, 55), 2), (jd + 1, hms(0, 0), 2), (jd + 1, hms(0, 5), 2)]
                + [(jd + 1, hms(0, 10), 1), (jd + 1, hms(0, 20), 1)])
        self.assertEqual(self.summarize('2013-06-03', rows), [
            ('2013-06-03T23:30:00', '2013-06-03T23:40:00', 1),
            ('2013-06-03T23:55:00', '2013-06-04T00:05:00', 2),
            ('2013-06-04T00:10:00', '2013-06-04T00:20:00', 1),
        ])

    def test_year_boundary_over_more_than_two_days(self):
        jd = Time('2024-12-31').jd
        rows = (scan(jd, hms(23, 0), hms(23, 10), 1)
                + [(jd + 1, 0.0, 2), (jd + 1, hms(0, 10), 2)]          # starts exactly at 00:00:00
                + [(jd + 2, hms(1, 0), 1), (jd + 2, hms(1, 10), 1)])
        self.assertEqual(self.summarize('2024-12-31', rows), [
            ('2024-12-31T23:00:00', '2024-12-31T23:10:00', 1),
            ('2025-01-01T00:00:00', '2025-01-01T00:10:00', 2),
            ('2025-01-02T01:00:00', '2025-01-02T01:10:00', 1),
        ])

    def test_constant_date_with_time_past_one_day(self):
        jd = Time('2013-06-03').jd
        rows = [(jd, t, sid) for t, sid in [(hms(23, 30), 1), (hms(23, 40), 1),
                                            (1 + hms(0, 10), 2), (1 + hms(0, 20), 2)]]
        self.assertEqual(self.summarize('2013-06-03', rows), [
            ('2013-06-03T23:30:00', '2013-06-03T23:40:00', 1),
            ('2013-06-04T00:10:00', '2013-06-04T00:20:00', 2),
        ])


if __name__ == '__main__':
    unittest.main()
