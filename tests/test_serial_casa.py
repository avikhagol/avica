"""Worker protocol tests without requiring CASA or AVICA's science stack."""
import ast
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import List
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch


PIPE = Path(__file__).resolve().parents[1] / "src/avica/pipe"


def load_definitions(filename, names, namespace):
    tree = ast.parse((PIPE / filename).read_text())
    tree.body = [node for node in tree.body if getattr(node, "name", None) in names]
    exec(compile(tree, str(PIPE / filename), "exec"), namespace)
    return namespace


spec = importlib.util.spec_from_file_location("worker", PIPE / "mpicasa_worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class SerialCasaTests(unittest.TestCase):
    def test_launcher_modes_and_invalid_counts(self):
        from typing import Any, Dict, Optional
        subprocess = Mock()
        ns = load_definitions("core.py", {"PersistentMpiCasaRunner"}, dict(
            Any=Any, Dict=Dict, Optional=Optional, MPICASA_WORKER="worker.py",
            IterativeSubprocess=subprocess))
        runner = ns["PersistentMpiCasaRunner"]
        for cores in (1, 2, 5):
            runner("/casa", cores)
            cmd = subprocess.call_args.kwargs["cmd_list"]
            self.assertEqual(cmd[0], "/casa/bin/casa" if cores == 1 else "/casa/bin/mpicasa")
            self.assertEqual("--serial" in cmd, cores == 1)
            if cores > 1:
                self.assertEqual(cmd[cmd.index("-n") + 1], str(cores))
        for cores in (0, -1):
            with self.assertRaises(ValueError):
                runner("/casa", cores)

    def test_picard_serial_translation(self):
        from dataclasses import dataclass
        from typing import List
        task = load_definitions("core.py", {"PicardTask"}, dict(
            dataclass=dataclass, List=List))["PicardTask"]
        for count, expected in ((1, "2"), (2, "2"), (5, "5")):
            self.assertEqual(task("input", count).to_args(), ["-n", expected, "--input", "input"])
        with self.assertRaises(ValueError):
            task("input", 0).to_args()

    def test_serial_protocol_without_casampi(self):
        tasks = ModuleType("casatasks")
        def noisy_task(**kwargs):
            print("CASA task output")
            return kwargs
        for name in ("importfitsidi", "flagdata", "flagmanager", "fringefit", "mstransform"):
            setattr(tasks, name, Mock(side_effect=noisy_task))
        requests = []
        for index, name in enumerate(("importfitsidi", "flagdata", "flagmanager", "fringefit"), 1):
            requests.extend([
                {"task_casa": name, "args": {"vis": "test.ms"}, "block": False},
                {"task_casa": "get_command_response", "parameters": {"command_ids": [index]}},
            ])
        requests.append({"task_casa": "stop_services"})
        output = io.StringIO()
        with patch.dict(sys.modules, {"casatasks": tasks, "casampi": None}), \
             patch.object(sys, "argv", ["worker.py", "--serial"]), \
             patch.object(sys, "stdin", io.StringIO("\n".join(map(json.dumps, requests)))), \
             patch.object(sys, "stdout", output), patch.object(sys, "stderr", io.StringIO()):
            worker.main()
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(responses[0], {"status": "ready"})
        for index in range(1, 5):
            self.assertEqual(responses[index * 2 - 1]["ret"], [index])
            self.assertTrue(responses[index * 2]["ret"][0]["successful"])
        tasks.importfitsidi.assert_called_once_with(vis="test.ms")
        tasks.fringefit.assert_called_once_with(vis="test.ms")

    def test_serial_failure_and_blocking_response(self):
        client = worker.SerialCommandClient({"fringefit": Mock(side_effect=RuntimeError("bad data"))})
        ids = client.run_task("fringefit", {})
        response = client.get_command_response(ids)[0]
        self.assertFalse(response["successful"])
        self.assertIn("bad data", response["traceback"])
        self.assertFalse(client.run_task("fringefit", {}, block=True)[0]["successful"])
        self.assertEqual(client.responses, {})

    def test_fringefit_empty_work_and_cleanup_on_exception(self):
        runner = Mock()
        ns = load_definitions("tasks/fringefit.py", {"task_fringefit_payload"}, dict(
            List=List, Path=Path, PersistentMpiCasaRunner=runner,
            zip_longest=__import__("itertools").zip_longest,
            casatask_fringefit=Mock(side_effect=RuntimeError("task construction failed"))))
        task = ns["task_fringefit_payload"]
        self.assertEqual(task("test.ms", {}, str(PIPE)), {"tbl_names": []})
        runner.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "task construction failed"):
            task("test.ms", {0: {"name": "ANT", "scans": [1]}}, str(PIPE), mpi_cores=1)
        runner.return_value.close.assert_called_once()

    def test_fringefit_failed_response_rejects_existing_table(self):
        runner = Mock()
        runner.return_value.run_task.return_value = {"status": "success", "ret": [1]}
        runner.return_value.get_response.return_value = {
            "status": "success", "ret": [{"successful": False, "traceback": "bad data"}]}
        task_builder = Mock()
        task_builder.return_value.to_step.return_value.cmd.args = {"refant": "ANT"}
        ns = load_definitions("tasks/fringefit.py", {"task_fringefit_payload"}, dict(
            List=List, Path=Path, PersistentMpiCasaRunner=runner,
            zip_longest=__import__("itertools").zip_longest,
            casatask_fringefit=task_builder, c={"g": "", "r": "", "x": ""}))
        with TemporaryDirectory() as folder:
            (Path(folder) / (Path(folder).name + "_ANT_1.t")).mkdir()
            result = ns["task_fringefit_payload"](
                "test.ms", {0: {"name": "ANT", "scans": [1]}}, folder, mpi_cores=1)
        self.assertEqual(result["tbl_names"], [])
        self.assertEqual(result["ANT___1"]["status"], "error")
        self.assertIn("bad data", result["ANT___1"]["err_msg"])
        runner.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
