import sys
import json
import traceback


def main():
    from casatasks import importfitsidi, fringefit, mstransform, flagdata
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
            else:
                args_type = payload.get("args_type", {})
                parts = []
                for k, v in parameters.items():
                    t = args_type.get(k, "")
                    if isinstance(v, list):
                        parts.append(f"{k}={repr(v)}")
                    elif isinstance(v, bool):
                        parts.append(f"{k}={v}")
                    elif isinstance(v, (int, float)):
                        parts.append(f"{k}={v}")
                    else:
                        parts.append(f"{k}='{v}'")
                cmd_str = task_name + "(" + ", ".join(parts) + ")"
                ret = client.push_command_request(cmd_str, block, target_server)
            
            print(json.dumps({"status": "success", "task": task_name, "ret": ret}), flush=True)
            
        except Exception as e:
            err_msg = str(e)
            print(json.dumps({"status": "error", "error": err_msg, "traceback": traceback.format_exc(), "ret": None}), flush=True)

if __name__ == "__main__":
    main()
