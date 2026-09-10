import warnings

from .core import AvicaPipelineCore, DEFAULT_PARAMS
from .steps import PreProcessFitsIdi, FitsIdiToMS, Phaseshift, AvicaMetaMS, AverageMS, SnRating, FinalSplitMs, Calibration, FillInputMs


class AvicaPipeline(AvicaPipelineCore):

    LEGACY_MPI_PARAMS = {
        "mpi_cores_importfitsidi": "fits_to_ms.mpi_cores",
        "mpi_cores_avgms": "avica_avg.mpi_cores",
        "mpi_cores_snrating": "avica_snr.mpi_cores",
        "mpi_cores_splitms": "avica_split_ms.mpi_cores",
        "mpi_cores_rpicard": "rpicard.mpi_cores",
    }

    DEFAULT_STEPS = [
        PreProcessFitsIdi, FitsIdiToMS,
        Phaseshift,
        AverageMS, AvicaMetaMS, SnRating, FillInputMs,
        FinalSplitMs,
        Calibration
    ]

    def __init__(self, pipe_params: dict = None, steps: list = None):

        provided_pipe_params = dict(pipe_params or {})
        for old_name, new_name in self.LEGACY_MPI_PARAMS.items():
            if old_name not in provided_pipe_params:
                continue
            if new_name not in provided_pipe_params:
                provided_pipe_params[new_name] = provided_pipe_params[old_name]
            warnings.warn(
                f"{old_name} is deprecated; use {new_name}",
                DeprecationWarning,
                stacklevel=2,
            )
            del provided_pipe_params[old_name]
        merged_params = {**DEFAULT_PARAMS, **provided_pipe_params}
        super().__init__(
            pipe_params = merged_params,
            steps       = steps or self.DEFAULT_STEPS,
            provided_pipe_params = provided_pipe_params,
        )

    def step_names(self):
        return list(self._steps.keys())

    def steps_from(self, step_name):
        step_names = self.step_names()
        if step_name not in step_names:
            raise ValueError(f"Unknown pipeline step: {step_name}")

        idx_step = step_names.index(step_name)
        return step_names[idx_step:]

    def config_report(self, *step_names):
        if not step_names:
            step_names = self.step_names()
        step_reports = []
        for step_name in step_names:
            step_report = self.check_config_requirements(step_name)
            step_reports.append(step_report)

        return step_reports
