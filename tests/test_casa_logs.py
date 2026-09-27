"""Issue #58: one CASA log (+ err file) per pipeline run, in casa.logs/."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from avica import casalogs

PIPE = Path(__file__).resolve().parents[1] / "src" / "avica" / "pipe"
spec = importlib.util.spec_from_file_location("worker58", PIPE / "mpicasa_worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class RunDirTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        self.addCleanup(casalogs.end_run)


class CasaLogsModuleTest(RunDirTest):
    def test_start_run_creates_single_pair_in_casa_logs(self):
        logfile, errfile = casalogs.start_run(stamp=datetime(2026, 9, 27, 12, 0, 0), header="target=J0102")
        self.assertEqual(Path(logfile), self.root / "casa.logs" / "casa__log-20260927_120000.log")
        self.assertEqual(Path(errfile), self.root / "casa.logs" / "err-casa__log-20260927_120000.log")
        self.assertIn("run started target=J0102", Path(logfile).read_text())
        self.assertEqual(casalogs.current_logfile(), logfile)
        casalogs.end_run()
        self.assertIsNone(casalogs.current_logfile())

    def test_marker(self):
        self.assertEqual(casalogs.task_marker("avica_snr", "fringefit", "vis=X.ms"),
                         ">>> avica [avica_snr] fringefit vis=X.ms")

    def test_stray_logs_of_this_run_are_merged_older_ones_kept(self):
        old = self.root / "casa-20200101-000000.log"
        old.write_text("old run\n")
        t = time.time() - 3600
        os.utime(old, (t, t))
        logfile, _ = casalogs.start_run()
        stray = self.root / "casa-20260927-120001.log"
        stray.write_text("INFO msmetadata::open\n")
        empty = self.root / "ipython-20260927-120001.log"
        empty.write_text("")

        merged = casalogs.collect_stray_logs()

        self.assertEqual(sorted(Path(m).name for m in merged), sorted([stray.name, empty.name]))
        self.assertFalse(stray.exists())
        self.assertFalse(empty.exists())
        self.assertTrue(old.exists())
        text = Path(logfile).read_text()
        self.assertIn(f"merged from {stray.name}", text)
        self.assertIn("msmetadata::open", text)
        self.assertNotIn("old run", text)

    def test_nothing_happens_outside_a_run(self):
        stray = self.root / "casa-20260927-120001.log"
        stray.write_text("x")
        self.assertEqual(casalogs.collect_stray_logs(), [])
        self.assertFalse(casalogs.redirect_inprocess())
        self.assertTrue(stray.exists())

    def test_redirect_inprocess_switches_casatools_sink(self):
        logfile, _ = casalogs.start_run()
        sink = Mock()
        sink.logfile.return_value = str(self.root / "casa-default.log")
        tools = ModuleType("casatools")
        tools.logsink = Mock(return_value=sink)
        with patch.dict(sys.modules, {"casatools": tools}):
            sys.modules.pop("casatasks", None)
            self.assertTrue(casalogs.redirect_inprocess())
        sink.setlogfile.assert_called_once_with(logfile)


class StepLogfilesTest(RunDirTest):
    def test_run_level_inside_run_per_step_outside(self):
        from avica.pipe.core import casa_logfiles
        stamp = datetime(2026, 9, 27, 12, 0, 0)
        outside = casa_logfiles("/wd", "avica_snr", stamp)
        self.assertEqual(outside[0], "/wd/avica_snr_casa_log-20260927_120000.log")
        logfile, errfile = casalogs.start_run()
        self.assertEqual(casa_logfiles("/wd/C", "avica_snr", stamp), (logfile, errfile))
        self.assertEqual(casa_logfiles("/wd/X", "avica_split_ms", stamp), (logfile, errfile))


class RunnerTest(RunDirTest):
    def make_runner(self, cores=1):
        from avica.pipe import core
        self.subprocess = Mock()
        self.subprocess.return_value.get_stderr.return_value = "WARN from worker\n"
        with patch.object(core, "IterativeSubprocess", self.subprocess):
            return core.PersistentMpiCasaRunner("/casa", cores)

    def test_logfile_passed_to_casa_and_payload(self):
        logfile, errfile = casalogs.start_run()
        for cores in (1, 4):
            runner = self.make_runner(cores)
            cmd = self.subprocess.call_args.kwargs["cmd_list"]
            self.assertEqual(cmd[cmd.index("--logfile") + 1], logfile)
            self.assertLess(cmd.index("--logfile"), cmd.index("-c"))
        send = runner.runner.send_and_receive
        send.return_value = {"status": "success", "ret": [1]}
        from avica.pipe.core import PipelineContext
        with patch.object(PipelineContext, "step_name", "fits_to_ms"):
            runner.run_task("importfitsidi", {"vis": "/wd/EY034_C.ms"}, {})
        payload = send.call_args.args[0]
        self.assertEqual(payload["logfile"], logfile)
        self.assertEqual(payload["label"], ">>> avica [fits_to_ms] importfitsidi vis=EY034_C.ms")

    def test_no_logfile_outside_run(self):
        self.make_runner(1)
        self.assertNotIn("--logfile", self.subprocess.call_args.kwargs["cmd_list"])

    def test_failures_and_stderr_go_to_run_err_file(self):
        _, errfile = casalogs.start_run()
        runner = self.make_runner(1)
        send = runner.runner.send_and_receive
        send.return_value = {"status": "success", "ret": [7]}
        runner.run_task("fringefit", {"vis": "a.ms"}, {}, label="LBL-7")
        send.return_value = {"status": "success", "ret": [
            {"id": 7, "successful": False, "traceback": "Traceback: boom"}]}
        runner.get_response([7])
        runner.close()
        text = Path(errfile).read_text()
        self.assertIn("LBL-7 FAILED\nTraceback: boom", text)
        self.assertIn("casa worker stderr\nWARN from worker", text)


class WorkerMarkerTest(unittest.TestCase):
    def tasks(self):
        tasks = ModuleType("casatasks")
        for name in ("importfitsidi", "flagdata", "flagmanager", "fringefit", "mstransform", "casalog"):
            setattr(tasks, name, Mock(return_value=None))
        return tasks

    def test_serial_posts_marker_and_keeps_same_logfile(self):
        tasks = self.tasks()
        tasks.casalog.logfile.return_value = "run.log"
        request = {"task_casa": "mstransform", "args": {"chanbin": 4},
                   "logfile": "run.log", "label": ">>> avica [avica_avg] mstransform"}
        with patch.dict(sys.modules, {"casatasks": tasks, "casampi": None}), \
             patch.object(sys, "argv", ["worker.py", "--serial"]), \
             patch.object(sys, "stdin", io.StringIO(json.dumps(request))), \
             patch.object(sys, "stdout", io.StringIO()):
            worker.main()
        tasks.casalog.setlogfile.assert_not_called()
        tasks.casalog.post.assert_called_once_with(">>> avica [avica_avg] mstransform", "INFO", "avica")

    def test_mpi_command_string_carries_marker(self):
        tasks = self.tasks()
        mpi_module = ModuleType("casampi.MPICommandClient")
        client = Mock()
        client.push_command_request.return_value = [1]
        mpi_module.MPICommandClient = Mock(return_value=client)
        request = {"task_casa": "fringefit", "args": {"vis": "a.ms"},
                   "logfile": "run.log", "label": "M"}
        with patch.dict(sys.modules, {"casatasks": tasks, "casampi": ModuleType("casampi"),
                                      "casampi.MPICommandClient": mpi_module}), \
             patch.object(sys, "argv", ["worker.py"]), \
             patch.object(sys, "stdin", io.StringIO(json.dumps(request))), \
             patch.object(sys, "stdout", io.StringIO()):
            worker.main()
        cmd = client.push_command_request.call_args.args[0]
        self.assertIn("casalog.post('M', 'INFO', 'avica')", cmd)
        self.assertIn("casalog.setlogfile('run.log') if casalog.logfile() != 'run.log' else None", cmd)
        self.assertTrue(cmd.endswith("fringefit(vis='a.ms')"))
        compile(cmd, "<cmd>", "exec")


if __name__ == "__main__":
    unittest.main()
