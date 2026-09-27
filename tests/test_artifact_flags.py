"""UVFLG discovery/conversion and CASA orchestration; no network or CASA needed."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from astropy.io import fits
from astropy.time import Time

from avica.pipe.artifact_flags import build_artifact_flagcmd, discover_flagfiles, read_uvflg
from avica.pipe.core import StepResult
from avica.pipe.steps import FitsIdiToMS


FLAG = """! station flags
opcode='FLAG' dtimrang=1 timeoff=0
ant_name='EF' timerang=145,03,39,33,145,03,39,60 reason='Antenna off source' /
ant_name='WB' timerang=145,04,00,00,145,04,01,00 reason='bad data' /
"""


class ArtifactFlagsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        self.ff = self.make_fits(self.root / 'one.IDI1')
        self.output = self.root / 'output.flagcmd'

    def make_fits(self, path, date='2025-05-25', antennas=('EF', 'WB'), bands=2, channels=16):
        geometry = fits.BinTableHDU.from_columns([
            fits.Column(name='ANNAME', format='8A', array=list(antennas)),
        ], name='ARRAY_GEOMETRY')
        geometry.header.update(NO_BAND=bands, NO_CHAN=channels, RDATE=date)
        uv = fits.BinTableHDU.from_columns([
            fits.Column(name='DATE', format='1D', array=[Time(date).jd] * 2),
            fits.Column(name='TIME', format='1D', array=[0, 23/24]),
        ], name='UV_DATA')
        fits.HDUList([fits.PrimaryHDU(), geometry, uv]).writeto(path)
        return path

    def flag(self, name='experiment.flag', text=FLAG):
        path = self.data / name
        path.write_text(text)
        return path

    def build(self, **kwargs):
        count, reports = build_artifact_flagcmd([self.ff], self.output, [self.data], **kwargs)
        return count, reports, self.output.read_text()

    def test_station_file_time_normalization_reason_and_padding(self):
        self.flag()
        count, reports, text = self.build()
        self.assertEqual(count, 2)
        self.assertIn("timerange='2025/05/25/03:39:32~2025/05/25/03:40:01'", text)
        self.assertIn("reason='Antenna off source'", text)
        self.assertIn("mode='manual'", text)
        self.assertEqual(reports[0]['parsed_rows'], 2)

    def test_timeoff_and_padding_persist_with_aips_zero_semantics(self):
        self.flag(text=FLAG.replace('timeoff=0', 'timeoff=60').replace("ant_name='WB'", "timeoff=0 dtimrang=0 ant_name='WB'"))
        _, _, text = self.build()
        self.assertIn('03:40:32~2025/05/25/03:41:01', text)
        self.assertIn('04:00:59~2025/05/25/04:02:01', text)

    def test_case_insensitive_discovery_and_symlink_deduplication(self):
        local = self.flag('one.FLAG')
        (self.data / 'alias.flag').symlink_to(local)
        self.flag('ignored.txt')
        self.assertEqual(discover_flagfiles([self.data, self.data]), [local.resolve()])

    def test_files_are_combined_and_commands_deduplicated(self):
        self.flag('a.flag')
        self.flag('b.fg', FLAG + "ant_name='EF' timerang=145,5,0,0,145,5,1,0 /\n")
        count, reports, _ = self.build()
        self.assertEqual(count, 3)
        self.assertEqual([r['unique_commands'] for r in reports], [2, 1])

    def test_explicit_unusual_extension_overrides_discovery(self):
        self.flag('auto.flag')
        explicit = self.flag('manual.txt', "ant_name='EF' timerang=0 /\n")
        count, reports, _ = self.build(explicit=[str(explicit)])
        self.assertEqual(count, 1)
        self.assertEqual(reports[0]['origin'], 'explicit')

    def test_missing_stations_and_unrelated_times_only_skip_their_records(self):
        self.flag(text=FLAG + "ant_name='DE' timerang=0 /\nant_name='EF' timerang=144,0,0,0,144,1,0,0 /\n")
        with self.assertLogs('avica.pipeline', level='WARNING'):
            count, reports, _ = self.build()
        self.assertEqual(count, 2)
        self.assertEqual(reports[0]['skipped'], {'unknown_antenna': 1, 'outside_time': 1})

    def test_partial_station_file_is_accepted(self):
        self.flag(text="ant_name='EF' timerang=0 /\n")
        self.assertEqual(self.build()[0], 1)

    def test_if_and_channel_ranges_are_zero_based(self):
        self.flag(text="ant_name='EF' timerang=0 bif=2 eif=2 bchan=3 echan=7 /\n")
        self.assertIn("spw='1:2~6'", self.build()[2])

    def test_invalid_selectors_do_not_broaden_flags(self):
        invalid = ["bif=3", "bchan=17", "opcode='UFLG'", "sources='other'", "timerang=5"]
        self.flag(text=FLAG + ''.join(f"ant_name='EF' {extra} /\n" for extra in invalid))
        with self.assertLogs('avica.pipeline', level='WARNING'):
            count, reports, _ = self.build()
        self.assertEqual(count, 2)
        self.assertEqual(reports[0]['skipped']['invalid_record'], 5)

    def test_bad_file_does_not_discard_good_file(self):
        self.flag('good.flag')
        self.flag('bad.flag', "ant_name='EF' timerang=0")
        with self.assertLogs('avica.pipeline', level='WARNING'):
            count, reports, _ = self.build()
        self.assertEqual(count, 2)
        self.assertEqual(reports[0]['status'], 'rejected')

    def test_no_files_does_not_read_fits_or_make_commands(self):
        with patch('avica.pipe.artifact_flags.fits_flag_contexts') as context:
            self.assertEqual(self.build(), (0, [], ''))
        context.assert_not_called()

    def test_split_outputs_use_their_own_time_and_band_layout(self):
        self.flag()
        other = self.make_fits(self.root/'other_freqid2.fits', date='2025-05-26', bands=1)
        count, _ = build_artifact_flagcmd([other], self.output, [self.data])
        self.assertEqual(count, 0)
        self.assertEqual(self.build()[0], 2)

    def test_new_year_and_leap_year(self):
        self.flag(text="ant_name='EF' timerang=366,23,59,59,1,0,0,1 /\n")
        newyear = self.make_fits(self.root/'newyear.fits', date='2025-01-01')
        count, _ = build_artifact_flagcmd([newyear], self.output, [self.data])
        self.assertEqual(count, 1)
        self.assertIn('2025/01/01/00:00:01', self.output.read_text())

    def test_real_ey034_file(self):
        example = Path('/mnt/6438D98627D1388F/Intelligence/tests/vasco_0.3/ey034.flag')
        if not example.exists():
            self.skipTest('optional external EY034 flag fixture is unavailable')
        records = read_uvflg(example)
        self.assertEqual(len(records), 2798)
        antennas = sorted({row['ANT_NAME'].upper() for row in records})
        fixture = self.make_fits(self.root/'ey034.fits', antennas=antennas)
        count, reports = build_artifact_flagcmd([fixture], self.output, [], explicit=[str(example)])
        self.assertGreater(count, 0)
        self.assertNotIn('invalid_record', reports[0]['skipped'])
        self.assertEqual(reports[0]['parsed_rows'], 2798)


class ArtifactFlagApplicationTest(unittest.TestCase):
    make_fits = ArtifactFlagsTest.make_fits
    flag = ArtifactFlagsTest.flag

    def setUp(self):
        ArtifactFlagsTest.setUp(self)
        self.step = FitsIdiToMS()
        self.step.result = StepResult(name='fits_to_ms', detail={}, desc=[], success=[],
                                      success_count=0, failed_count=0, start_stamp=datetime.now())
        self.vis = self.root/'test.ms'
        self.options = dict(directories=[self.data])
        self.flag()

    def apply(self):
        return self.step._apply_flags(None, self.vis, [self.ff], '', '', '',
                                      flag_source='artifact', artifact_options=self.options)

    def test_application_uses_backup_list_and_after_backup(self):
        with patch.object(self.step, '_run_casa_step') as run:
            self.assertTrue(self.apply())
        steps = [c.args[1].cmd for c in run.call_args_list]
        self.assertEqual([s.task_casa for s in steps], ['flagmanager', 'flagdata', 'flagmanager'])
        self.assertEqual(steps[1].args['mode'], 'list')
        self.assertTrue(steps[0].args['versionname'].startswith('before_artifact_flags_'))
        report = self.step.result.detail['artifact_flags'][str(self.vis)]
        self.assertEqual(report['status'], 'applied')
        self.assertEqual(json.loads(Path(report['flagcmd']+'.json').read_text())['status'], 'applied')

    def test_casa_failure_retains_before_backup_and_reports_failure(self):
        with patch.object(self.step, '_run_casa_step', side_effect=[None, RuntimeError('CASA failure')]) as run:
            with self.assertRaisesRegex(RuntimeError, 'CASA failure'):
                self.apply()
        self.assertEqual(run.call_count, 2)
        report = self.step.result.detail['artifact_flags'][str(self.vis)]
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('applied_commands', report['files'][0])

    def test_additive_flags_and_disable_switch_are_independent(self):
        for idi, artifact, expected in [(True, True, ['ms', 'artifact']), (True, False, ['ms']),
                                        (False, True, ['artifact']), (False, False, [])]:
            with patch.object(self.step, '_apply_flags') as apply:
                self.step._apply_selected_flags(apply_flag_from_idi=idi, apply_flag_from_artifacts=artifact,
                                                artifact_options=self.options, flag_source='ms')
            self.assertEqual([c.kwargs['flag_source'] for c in apply.call_args_list], expected)

    def test_existing_ms_requires_opt_in_and_artifact_only_starts_runner(self):
        self.vis.mkdir()
        meta = SimpleNamespace(ff_used=[str(self.ff)], wd=self.root, metafolder=self.root,
                               vis=str(self.vis), metafile_available_wd_ff=self.root/'used.json')
        for enabled, count in [(False, 0), (True, 1)]:
            with patch('avica.pipe.steps.WorkDirMeta', return_value=meta), \
                 patch('avica.pipe.steps.PersistentMpiCasaRunner') as runner, \
                 patch.object(self.step, '_apply_selected_flags', return_value=True) as apply, \
                 patch('avica.pipe.steps.del_fl'):
                self.step.run(None, '', str(self.root/'input_template'), apply_flag_from_idi=False,
                              apply_flag_from_artifacts=True, apply_flag_to_existing_vis=enabled,
                              artifact_dirs=[str(self.data)])
            self.assertEqual(apply.call_count, count)
            self.assertEqual(runner.call_count, count)

    def test_new_and_split_outputs_receive_their_corresponding_fits(self):
        for split in (False, True):
            with self.subTest(split=split):
                inputs = ([str(self.root/'a_freqid1.fits'), str(self.root/'a_freqid2.fits')]
                          if split else [str(self.ff)])
                vis = self.root / ('split.ms' if split else 'new.ms')
                meta = SimpleNamespace(ff_used=inputs, wd=self.root, metafolder=self.root,
                                       vis=str(vis), metafile_available_wd_ff=self.root/'used.json')

                def submit(task_name, args, **kwargs):
                    Path(args['vis']).mkdir()
                    return {'status': 'success', 'ret': 1}

                with patch('avica.pipe.steps.WorkDirMeta', return_value=meta), \
                     patch('avica.pipe.steps.PersistentMpiCasaRunner') as runner, \
                     patch.object(self.step, '_apply_selected_flags', return_value=True) as apply, \
                     patch('avica.pipe.steps.del_fl'), \
                     patch('avica.pipe.steps.read_inputfile', side_effect=[
                         ({'ms_name': 'band1.ms'}, [], ''), ({'ms_name': 'band2.ms'}, [], '')]):
                    runner.return_value.run_task.side_effect = submit
                    runner.return_value.get_response.return_value = {
                        'status': 'success', 'ret': [{'successful': True}]}
                    self.step.run(None, '', str(self.root/'input_template'), apply_flag_from_idi=False,
                                  apply_flag_from_artifacts=True, artifact_dirs=[str(self.data)])
                actual = [c.kwargs['fitsfiles'] for c in apply.call_args_list]
                self.assertEqual(actual, [[f] for f in inputs] if split else [inputs])
                for call in apply.call_args_list:
                    self.assertIn(str(self.data), call.kwargs['artifact_options']['directories'])


if __name__ == '__main__':
    unittest.main()
