"""Date parsing must retain legacy VLBA dates alongside EVN formats."""

import unittest

from astropy.time import Time

from avica.fitsidiutil.op import get_yyyymmdd


class FITSIDIDateTests(unittest.TestCase):
    def test_supported_dates_and_legacy_century_pivot(self):
        cases = {
            "23/08/96": (1996, 8, 23),
            "24/08/96": (1996, 8, 24),
            "01/01/90": (1990, 1, 1),
            "31/12/99": (1999, 12, 31),
            "01/01/00": (2000, 1, 1),
            "01/01/31": (2031, 1, 1),
            "01/01/32": (2032, 1, 1),
            "01/01/89": (2089, 1, 1),
            "23/08/1996": (1996, 8, 23),
            "1996/08/23": (1996, 8, 23),
            "23-08-1996": (1996, 8, 23),
            "1996-08-23": (1996, 8, 23),
            "2026-09-16T01:23:45": (2026, 9, 16),
            "2026-09-16 01:23:45": (2026, 9, 16),
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(get_yyyymmdd(value), expected)

    def test_legacy_date_can_be_used_by_observation_summary(self):
        year, month, day = get_yyyymmdd("23/08/96")
        parsed = Time(f"{year}-{month:02}-{day:02}", format="isot", scale="utc")
        self.assertEqual(parsed.isot, "1996-08-23T00:00:00.000")
