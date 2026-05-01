from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import logging
from avica.pipe.core import PipelineStepBase, AvicaResult, StepResult
from avica.pipe.steps import FitsIdiToMS, PreProcessFitsIdi

# from alfrd.plugins import register, validate, validator


def run_pipeline(
                steps: List[PipelineStepBase],
                lf: Any,
                wd_ifolder: str,
                pipe_params: Dict,
                params: Dict,
                stop_on_failure: bool = False,
                ) -> AvicaResult:
    """
    Execute all pipeline steps sequentially and collect results.

    Parameters
    ----------
    steps           : ordered list of PipelineStepBase instances to run
    lf              : alfrd instance
    wd_ifolder      : working input folder shared across steps
    pipe_params     : pipeline-level configuration (casadir, etc.)
    params          : observation / step-level parameters
    stop_on_failure : if True, abort the pipeline on the first failed step

    Returns
    -------
    AvicaResult     : list-like container of StepResult objects
    """
    results = AvicaResult()
    log = logging.getLogger("avica.pipeline")

    log.info("=" * 60)
    log.info(f"Pipeline started  — {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info(f"Steps to run      : {[s.name for s in steps]}")
    log.info("=" * 60)

    for step in steps:
        log.info(f"[{step.name}] Starting …")
        step_start = datetime.now()

        try:
            result: StepResult = step.run(
                lf=lf,
                wd_ifolder=wd_ifolder,
                pipe_params=pipe_params,
                params=params,
            )
        except Exception as exc:
            result = StepResult(
                name=step.name,
                success_count=0,
                failed_count=1,
                start_stamp=step_start,
                end_stamp=datetime.now(),
                detail={},
                desc=[f"Unhandled exception: {exc}"],
                success=[False],
            )
            log.exception(f"[{step.name}] Unhandled exception — {exc}")

        results.append(result)

        elapsed = (result.end_stamp - result.start_stamp).total_seconds()
        status  = "OK" if all(result.success) else "FAILED"
        log.info(
            f"[{step.name}] {status} | "
            f"✓ {result.success_count}  ✗ {result.failed_count} | "
            f"{elapsed:.1f}s"
        )
        for line in result.desc:
            log.debug(f"  · {line}")

        if stop_on_failure and result.failed_count > 0:
            log.warning(f"stop_on_failure=True — aborting after [{step.name}]")
            break

    log.info("=" * 60)
    log.info(
        f"Pipeline finished — "
        f"total ✓ {sum(r.success_count for r in results)}  "
        f"✗ {sum(r.failed_count for r in results)}"
    )
    log.info("=" * 60)

    return results


# ___________________________________________________________________ entrypoint
# @register("main func")
def main() -> AvicaResult:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # _______________________________________________________________ config
    wd_ifolder  = "BA048/input_template/"
    pipe_params = {
        'filepaths': ["BA048/raw/VLBA_VSN004097_file7.uvfits"],
        "targets":['B1504+105'],
        "target": "B1504+105",
        "casadir": "/"+"home/avi/intelligence/env/casa-6.7.0-31-py3.10.el8/",
        'rfc_catalogfile':None,
        'class_search_asciifile':None,
        'picard_dir':None,
    }
    params = {}
    lf     = None

    # _______________________________________________________________ pipe sequence
    steps: List[PipelineStepBase] = [
        PreProcessFitsIdi(),
        FitsIdiToMS()
    ]

    # _______________________________________________________________ main execution
    results = run_pipeline(
        steps=steps,
        lf=lf,
        wd_ifolder=wd_ifolder,
        pipe_params=pipe_params,
        params=params,
        stop_on_failure=False,
    )

    # _______________________________________________________________ summarize
    # print(results)
    df = results.to_polars()
    # df.write_csv("pipeline_results.csv")

    return results
