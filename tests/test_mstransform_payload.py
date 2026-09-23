"""CASA dispatch and pipeline bookkeeping tests without the science stack."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import logging
import shutil
import sys
import traceback
import unittest
from unittest.mock import Mock, patch

from test_serial_casa import load_definitions


def step(output, logfile="", errf="", **args):
    return SimpleNamespace(cmd=SimpleNamespace(
        task_casa="mstransform", args=dict(outputvis=str(output), **args),
        args_type={}, logfile=logfile, errf=errf))


def payload(runner):
    return load_definitions("tasks/mstransform.py", {"task_mstransform_payload"}, dict(
        Path=Path, traceback=traceback, PersistentMpiCasaRunner=runner,
    ))["task_mstransform_payload"]


def successful_runner():
    factory = Mock()
    factory.return_value.run_task.return_value = {
        "status": "success", "ret": [{"successful": True}]}
    factory.return_value.runner.get_stderr.return_value = "worker diagnostics\n"
    return factory


class PayloadTests(unittest.TestCase):
    def test_empty_work_does_not_start_casa(self):
        factory = successful_runner()
        self.assertEqual(payload(factory)({}, "/casa"), {})
        factory.assert_not_called()

    def test_reuses_runner_preserves_arguments_and_logs(self):
        factory = successful_runner()
        with TemporaryDirectory() as folder:
            root = Path(folder)
            jobs = {}
            for key, chanbin in (("C", 4), ("L", [2, 4])):
                output = root / f"{key}.ms"
                output.mkdir()
                jobs[key] = step(output, str(root / f"{key}.log"), str(root / f"{key}.err"),
                                 vis="quoted'input.ms", chanbin=chanbin, createmms=True)
            results = payload(factory)(jobs, "/casa", mpi_cores=1)
            self.assertEqual([r["status"] for r in results.values()], ["success", "success"])
            factory.assert_called_once_with(casadir="/casa", mpi_cores=1)
            calls = factory.return_value.run_task.call_args_list
            self.assertEqual(calls[0].kwargs["args"]["chanbin"], 4)
            self.assertEqual(calls[1].kwargs["args"]["chanbin"], [2, 4])
            self.assertEqual(calls[0].kwargs["logfile"], jobs["C"].cmd.logfile)
            self.assertTrue(calls[0].kwargs["run_on_master"])
            self.assertTrue(calls[0].kwargs["block"])
            self.assertIn("worker diagnostics", (root / "C.err").read_text())
            self.assertEqual(
                [c[0] for c in factory.return_value.method_calls][:2],
                ["run_task", "run_task"])
        factory.return_value.close.assert_called_once()

    def test_execution_failure_rejects_partial_output_and_continues(self):
        factory = successful_runner()
        factory.return_value.run_task.side_effect = [
            {"status": "success", "ret": [{"successful": False, "traceback": "bad MS"}]},
            {"status": "success", "ret": [{"successful": True}]},
        ]
        with TemporaryDirectory() as folder:
            results = payload(factory)({"bad": step(folder), "good": step(folder)}, "/casa")
        self.assertEqual(results["bad"]["status"], "error")
        self.assertIn("bad MS", results["bad"]["err_msg"])
        self.assertEqual(results["good"]["status"], "success")
        factory.return_value.close.assert_called_once()

    def test_submission_failure_missing_output_and_empty_response(self):
        for failure in ("submission", "missing", "empty", "exception"):
            with self.subTest(failure=failure), TemporaryDirectory() as folder:
                factory = successful_runner()
                if failure == "submission":
                    factory.return_value.run_task.return_value = {"status": "error", "error": "rejected"}
                elif failure == "empty":
                    factory.return_value.run_task.return_value = {"status": "success", "ret": []}
                elif failure == "exception":
                    factory.return_value.run_task.side_effect = RuntimeError("worker died")
                result = payload(factory)({"C": step(Path(folder) / "absent.ms")}, "/casa")["C"]
                self.assertEqual(result["status"], "error")
                self.assertTrue(result["err_msg"])
                factory.return_value.close.assert_called_once()

    def test_startup_failure_is_recorded_for_each_job(self):
        factory = Mock(side_effect=RuntimeError("CASA unavailable"))
        with TemporaryDirectory() as folder:
            errf = str(Path(folder) / "task.err")
            results = payload(factory)({"C": step(folder, errf=errf)}, "/casa")
            self.assertIn("CASA unavailable", results["C"]["err_msg"])
            self.assertIn("CASA unavailable", Path(errf).read_text())


def pipeline_class(name, extra):
    result = lambda **kwargs: SimpleNamespace(**kwargs, success=[], desc=[])
    namespace = dict(PipelineStepBase=object, ColName=lambda *args: SimpleNamespace(
        working_col=args[0], comment_col=args[1]), InitVariables=None, RunValidation=None,
        CasaSetup=None, UpdateResults=None, UpdateSheet=None, StepResult=result,
        datetime=datetime, Path=Path, traceback=traceback, shutil=shutil,
        log=logging.getLogger(__name__), step_stage=lambda *a, **kw: nullcontext(),
        task_mstransform_payload=Mock(), **extra)
    return load_definitions("steps.py", {name}, namespace)[name]


class FinalSplitTests(unittest.TestCase):
    def exercise(self, failure=None):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            meta = Mock(wd=root, metafolder=root, metafile_msmeta_sources="bands")
            original = root / "C" / "test.ms"
            original.mkdir(parents=True)
            source_input = original.parent / "input"
            target_dir = root / "C_target"
            target_input = target_dir / "input"
            (root / "msmeta_sources_C_target.avica").touch()

            def workdir(band, target="", create=True):
                directory, inputs = (target_dir, target_input) if target else (original.parent, source_input)
                if create:
                    inputs.mkdir(parents=True, exist_ok=True)
                return directory, inputs

            meta.to_new_WD.side_effect = workdir
            target_inputs_populated = False
            input_events = []

            def fill_inputs(source, target):
                nonlocal target_inputs_populated
                input_events.append("fill")
                target_inputs_populated = True

            def get_inp(**kwargs):
                inpfile = kwargs.get("inpfile")
                if not inpfile:
                    return {"ms_name": "test.ms"}
                input_events.append(f"read:{inpfile}")
                if inpfile == "array.inp":
                    # read_inputfile returns comma-separated refants as a string.
                    return {"refant": "A,B,C,D"} if target_inputs_populated else {"refant": []}
                if inpfile == "array_finetune.inp":
                    return ({"rldly_stations": "''", "preserved": True}
                            if target_inputs_populated else {})
                return {}

            meta.get_inp.side_effect = get_inp
            metadata = Mock()
            metadata.scansforfield.return_value = [1, 2]
            repairs = Mock()
            if failure == "repair":
                repairs.side_effect = RuntimeError("repair failed")
            modules = {"avica.ms": SimpleNamespace(get_best_spws=lambda _: [0],
                       check_and_fix_spw_partitioning=repairs),
                       "avica.ms.compat": SimpleNamespace(CasaMSMetadata=lambda: metadata)}
            configs = Mock()
            cls = pipeline_class("FinalSplitMs", dict(
                WorkDirMeta=lambda **kw: meta, read_metafile=lambda _: {"bands_dict": {"bands_known": ["C"]}},
                alls_fromobs=lambda _: ["target"], create_config=configs,
                fillinp_fromiwd=fill_inputs,
                get_logfilename=lambda **kw: kw["module_name"] + ".log",
                MsTransform=lambda outputvis, **kw: SimpleNamespace(to_step=lambda **opts: step(
                    outputvis, **kw, logfile=opts["logfile"], errf=opts["errf"])),
            ))
            def execute(jobs, **kwargs):
                self.assertFalse(original.exists())
                self.assertEqual(kwargs["mpi_cores"], 1)
                output = Path(jobs["C"].cmd.args["outputvis"])
                output.mkdir()
                if failure == "exception":
                    raise RuntimeError("transport failed")
                return {"C": {"status": "error" if failure == "task" else "success", "err_msg": "task failed"}}

            cls.run.__globals__["task_mstransform_payload"].side_effect = execute
            with patch.dict(sys.modules, modules):
                if failure == "exception":
                    with self.assertRaisesRegex(RuntimeError, "transport failed"):
                        cls().run(Mock(), source_input, "/casa", "target", mpi_cores=1)
                else:
                    result = cls().run(Mock(), source_input, "/casa", "target", mpi_cores=1)
                    expected = failure is None
                    self.assertEqual(result.success, [expected])
                    self.assertEqual(result.success_count, int(expected))
                    self.assertEqual(result.failed_count, int(not expected))
                    if expected:
                        self.assertEqual(input_events[:3], [
                            "fill", "read:array_finetune.inp", "read:array.inp"])
                        array_finetune = configs.call_args_list[0].args[0]
                        self.assertEqual(array_finetune["rldly_stations"], "A,B,C")
                        self.assertTrue(array_finetune["preserved"])
                        observation = configs.call_args_list[-1].args[0]
                        self.assertEqual(observation["ms_name"], "test_old.ms")
                        self.assertTrue((target_dir / observation["ms_name"]).exists())
                    else:
                        configs.assert_not_called()
            self.assertTrue(original.exists())
            self.assertFalse(original.with_name("test_old.ms").exists())
            metadata.done.assert_called_once()

    def test_success_and_single_count(self):
        self.exercise()

    def test_failed_task_does_not_publish_partial_output(self):
        self.exercise("task")

    def test_repair_failure_and_exception_restore_input(self):
        self.exercise("repair")
        self.exercise("exception")


class AverageTests(unittest.TestCase):
    def exercise(self, mode):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "C" / "test_C.ms"
            iwd = output.parent / "input_template_C"
            iwd.mkdir(parents=True)
            if mode == "reuse":
                output.mkdir()
            meta = Mock(wd=root, metafolder=root, vis=str(root / "test.ms"),
                        obs_dic={"ms_name": "test.ms"}, wd_used=["input"],
                        metafile_available_wd_ff=None)
            meta.to_new_WD.return_value = (output.parent, iwd)
            band_info = Mock()
            band_info.bands_dict = {} if mode == "empty" else {"C": {"nobs": 1}}
            band_info.get_band_detail.return_value = {"C0": {
                "spws": [0], "missing_antennas": [], "timeavg": True,
                0: {"good_scans": {"1", "2"}, "fields": [0], "nchan": 16,
                    "chwidth": 125, "bw_khz": 2000}}}
            repairs = Mock()
            if mode == "repair":
                repairs.side_effect = RuntimeError("bad SPW")
            tsys = Mock(return_value=0)
            live = Mock(return_value={0: ([5, 8], [1])})
            choose = Mock(return_value="LL")
            modules = {"avica.ms": SimpleNamespace(check_and_fix_spw_partitioning=repairs),
                       "avica.ms.meta": SimpleNamespace(BandInfoMS=lambda *a, **kw: band_info),
                       "avica.ms.tables": SimpleNamespace(repair_mixed_single_pol_syscal_tsys=tsys,
                                                          live_correlations=live,
                                                          choose_live_correlation=choose)}
            configs = Mock()
            cls = pipeline_class("AverageMS", dict(
                WorkDirMeta=lambda **kw: meta, del_fl=Mock(), save_metafile=Mock(),
                deepcopy=deepcopy, single_ifcheck=lambda *a: 4,
                read_inputfile=lambda *a: ({"ms_name": "test.ms"}, None, None),
                create_config=configs, fillinp_fromiwd=Mock(),
                get_logfilename=lambda **kw: kw["module_name"] + ".log",
                MsTransform=lambda outputvis, **kw: SimpleNamespace(to_step=lambda **opts: step(
                    outputvis, **kw, logfile=opts["logfile"], errf=opts["errf"])),
            ))
            def execute(jobs, **kwargs):
                self.assertEqual(kwargs["mpi_cores"], 1)
                if mode in ("reuse", "empty"):
                    self.assertEqual(jobs, {})
                    return {}
                self.assertEqual(jobs["C"].cmd.args["chanbin"], 4)
                self.assertEqual(jobs["C"].cmd.args["spw"], "0:0~15")
                self.assertEqual(jobs["C"].cmd.args["correlation"], "LL")
                output.mkdir()
                return {"C": {"status": "error" if mode == "task" else "success", "err_msg": "bad task"}}
            cls.run.__globals__["task_mstransform_payload"].side_effect = execute
            lf = Mock()
            lf.get_value.return_value = ""
            with patch.dict(sys.modules, modules):
                result = cls().run(lf, "input", "/casa", ["one", "two"], "one", mpi_cores=1)
            expected = mode in ("success", "reuse")
            self.assertEqual(result.success_count, int(expected))
            self.assertEqual(result.failed_count, int(not expected and mode != "empty"))
            self.assertEqual(result.success, [] if mode == "empty" else [expected])
            if mode == "success":
                configs.assert_called_once()
                repairs.assert_called_once()
                tsys.assert_called_once()
                live.assert_called_once_with(str(root / "test.ms"), [0])
            else:
                configs.assert_not_called()
            if mode == "task":
                repairs.assert_not_called()
                tsys.assert_not_called()

    def test_success_reuse_empty_and_failures(self):
        for mode in ("success", "reuse", "empty", "task", "repair"):
            with self.subTest(mode=mode):
                self.exercise(mode)


if __name__ == "__main__":
    unittest.main()
