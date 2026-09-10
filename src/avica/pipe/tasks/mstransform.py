"""Execute prepared mstransform jobs through the persistent CASA worker."""
from pathlib import Path
import traceback

from avica.pipe.core import PersistentMpiCasaRunner


def task_mstransform_payload(jobs, casadir, mpi_cores=5):
    """Return results keyed like ``jobs`` (a mapping of IDs to CasaSteps).

    Jobs are submitted and collected in order. Keeping one transformation in
    flight preserves the old launcher's scheduling until concurrent MMS
    creation has been validated with real data.
    """
    if not jobs:
        return {}
    results = {}
    runner = None
    try:
        runner = PersistentMpiCasaRunner(casadir=casadir, mpi_cores=mpi_cores)
        for key, step in jobs.items():
            output = str(step.cmd.args["outputvis"])
            result = {"outputvis": output, "mpi_ids": [], "status": "error", "err_msg": ""}
            try:
                response = runner.run_task(
                    task_name=step.cmd.task_casa,
                    args={name: str(value) if isinstance(value, Path) else value
                          for name, value in step.cmd.args.items()},
                    args_type=step.cmd.args_type,
                    block=True,
                    logfile=step.cmd.logfile,
                    run_on_master=bool(step.cmd.args.get("createmms", False)),
                )
                replies = response.get("ret")
                if (response.get("status") != "success" or not replies
                        or not all(ret.get("successful", False) for ret in replies)):
                    raise RuntimeError(f"CASA mstransform failed: {response}")
                if not Path(output).exists():
                    raise RuntimeError(f"Successful mstransform execution but output not found: {output}")
                result["status"] = "success"
            except Exception:
                result["err_msg"] = traceback.format_exc()
            results[key] = result
    except Exception:
        error = traceback.format_exc()
        for key, step in jobs.items():
            results.setdefault(key, {"outputvis": str(step.cmd.args["outputvis"]),
                                     "mpi_ids": [], "status": "error", "err_msg": error})
    finally:
        if runner is not None:
            try:
                runner.close()
            except Exception:
                error = traceback.format_exc()
                for result in results.values():
                    result["status"] = "error"
                    result["err_msg"] += error
        # Keep diagnostics on disk even for failed submissions or worker startup.
        stderr = runner.runner.get_stderr() if runner is not None else ""
        for key, result in results.items():
            errf = jobs[key].cmd.errf
            if errf:
                try:
                    with Path(errf).open("a") as stream:
                        stream.write(result["err_msg"] + stderr)
                except OSError:
                    result["status"] = "error"
                    result["err_msg"] += traceback.format_exc()
    return results
