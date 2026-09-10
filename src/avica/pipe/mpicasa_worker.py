import sys
import json
import traceback
from contextlib import redirect_stdout


class SerialCommandClient:
    """Keep the MPI response protocol while executing tasks sequentially."""

    def __init__(self, tasks):
        self.tasks = tasks
        self.responses = {}
        self.next_id = 1

    def run_task(self, task_name, args, block=False):
        command_id = self.next_id
        self.next_id += 1
        try:
            with redirect_stdout(sys.stderr):
                result = self.tasks[task_name](**args)
            response = {"id": command_id, "successful": True,
                        "ret": result, "traceback": None}
        except Exception:
            response = {"id": command_id, "successful": False,
                        "ret": None, "traceback": traceback.format_exc()}
        self.responses[command_id] = response
        return self.get_command_response([command_id]) if block else [command_id]

    def get_command_response(self, command_ids, block=True):
        if isinstance(command_ids, int):
            command_ids = [command_ids]
        return [self.responses.pop(command_id) for command_id in command_ids]

    def stop_services(self):
        self.responses.clear()


def main():
    from casatasks import importfitsidi, fringefit, mstransform, flagdata, flagmanager
    tasks = dict(importfitsidi=importfitsidi, fringefit=fringefit,
                 mstransform=mstransform, flagdata=flagdata,
                 flagmanager=flagmanager)
    serial = "--serial" in sys.argv
    if serial:
        client = SerialCommandClient(tasks)
    else:
        from casampi.MPICommandClient import MPICommandClient
        client = MPICommandClient()
        client.set_log_mode('redirect')
        client.start_services()

    print(json.dumps({"status": "ready"}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            task_name = payload.get("task_casa")
            args = payload.get("args", {})
            block=payload.get("block", False)
            target_server=payload.get("target_server", 0)
            parameters=payload.get("parameters", args)
            logfile = payload.get("logfile", "")
            run_on_master = payload.get("run_on_master", False)

            if task_name == "get_command_response":
                command_ids = parameters["command_ids"]
                block = parameters.get("block", True)
                ret = client.get_command_response(command_ids, block)
            elif task_name == "close":
                ret = client.close()
            elif task_name == "open":
                ret = client.open()
            elif task_name == "set_log_mode":
                ret = client.set_log_mode(**parameters)
            elif task_name == "start_services":
                ret = client.start_services()
            elif task_name == "stop_services":
                ret = client.stop_services()
            elif run_on_master:
                if logfile:
                    from casatasks import casalog
                    casalog.setlogfile(logfile)
                try:
                    # This loop runs on rank 0. Internally parallel CASA tasks
                    # such as mstransform(createmms=True) must start here so
                    # they can distribute their own work to the MPI servers.
                    with redirect_stdout(sys.stderr):
                        task_result = tasks[task_name](**parameters)
                    ret = [{"id": 0, "successful": True, "ret": task_result,
                            "traceback": None}]
                except Exception:
                    ret = [{"id": 0, "successful": False, "ret": None,
                            "traceback": traceback.format_exc()}]
            elif serial:
                if logfile:
                    from casatasks import casalog
                    casalog.setlogfile(logfile)
                ret = client.run_task(task_name, parameters, block)
            else:
                parts = [f"{k}={v!r}" for k, v in parameters.items()]
                cmd_str = task_name + "(" + ", ".join(parts) + ")"
                if logfile:
                    cmd_str = f"from casatasks import casalog; casalog.setlogfile({logfile!r}); " + cmd_str
                ret = client.push_command_request(cmd_str, block, target_server)

            print(json.dumps({"status": "success", "task": task_name, "ret": ret}), flush=True)

        except Exception as e:
            err_msg = str(e)
            print(json.dumps({"status": "error", "error": err_msg, "traceback": traceback.format_exc(), "ret": None}), flush=True)

if __name__ == "__main__":
    main()
