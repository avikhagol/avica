"""Archive fallback handles the HTML strings returned by proj_search."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from avica.pipe.helpers import find_url_tsys


class TsysArchiveTest(unittest.TestCase):
    def setUp(self):
        reader = patch('avica.fitsidiutil.io.FITSIDI')
        self.reader = reader.start()
        self.addCleanup(reader.stop)
        self.reader.return_value.read.return_value = [
            SimpleNamespace(header={'DATE-OBS': '2025-04-10', 'OBSCODE': 'EY034'})]

    def test_unrelated_html_rows_return_no_match_without_crashing(self):
        rows = ['<td><a href="other/">other/</a></td>', '<td> </td>']
        with patch('avica.pipe.helpers.proj_search', return_value=(rows, False, [])):
            self.assertEqual(find_url_tsys('test.fits'), [])

    def test_project_and_jobs_links_are_resolved_from_html_strings(self):
        month = 'https://www.vlba.nrao.edu/astro/VOBS/astronomy/apr25'
        project = '<td><a href="EY034/">EY034/</a></td>'
        calibration = month + '/EY034/jobs/ey034cal.vlba'
        with patch('avica.pipe.helpers.proj_search', side_effect=[
            ([project], False, []), (['<td>jobs/</td>'], False, []),
            ([], True, [calibration]),
        ]) as search:
            self.assertEqual(find_url_tsys('test.fits'), [calibration])
        self.assertEqual([call.args[0] for call in search.call_args_list],
                         [month, month + '/EY034/', month + '/EY034/jobs/'])

    def test_direct_month_match_is_unchanged(self):
        with patch('avica.pipe.helpers.proj_search', return_value=([], True, ['cal.vlba'])) as search:
            self.assertEqual(find_url_tsys('test.fits'), ['cal.vlba'])
        search.assert_called_once()


if __name__ == '__main__':
    unittest.main()
