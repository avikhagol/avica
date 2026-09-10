"""Exercise real task-package imports in a fresh interpreter."""
from pathlib import Path
import subprocess
import sys
import unittest


class TaskImportTests(unittest.TestCase):
    def test_mstransform_does_not_eagerly_import_fringefit(self):
        source = Path(__file__).resolve().parents[1] / "src"
        script = r'''
import importlib
import sys
from pathlib import Path
from types import ModuleType

source = Path(sys.argv[1])
# Model the partially initialized parent packages during CLI startup: avica.c
# does not exist yet. Import the actual tasks package and mstransform module.
for name, directory in (("avica", source / "avica"),
                        ("avica.pipe", source / "avica/pipe")):
    package = ModuleType(name)
    package.__path__ = [str(directory)]
    sys.modules[name] = package
core = ModuleType("avica.pipe.core")
core.PersistentMpiCasaRunner = object
sys.modules[core.__name__] = core
sys.modules["avica.pipe.tasks.fringefit"] = None
sys.modules["avica.ms"] = None

module = importlib.import_module("avica.pipe.tasks.mstransform")
assert callable(module.task_mstransform_payload)
tasks = importlib.import_module("avica.pipe.tasks")
assert "exec_FFT_fringefit" in tasks.__all__

# The existing public export must still resolve when explicitly requested.
fringefit = ModuleType("avica.pipe.tasks.fringefit")
fringefit.exec_FFT_fringefit = object()
sys.modules[fringefit.__name__] = fringefit
from avica.pipe.tasks import exec_FFT_fringefit
assert exec_FFT_fringefit is fringefit.exec_FFT_fringefit
try:
    tasks.nonexistent_task
except AttributeError:
    pass
else:
    raise AssertionError("Unknown task attribute should raise AttributeError")
'''
        completed = subprocess.run([sys.executable, "-c", script, str(source)],
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
