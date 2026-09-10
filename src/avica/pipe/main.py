from .core import AvicaPipelineCore, DEFAULT_PARAMS
from .steps import PreProcessFitsIdi, FitsIdiToMS, Phaseshift, AvicaMetaMS, AverageMS, SnRating, FinalSplitMs, Calibration, FillInputMs


class AvicaPipeline(AvicaPipelineCore):

    DEFAULT_STEPS = [
        PreProcessFitsIdi, FitsIdiToMS,
        Phaseshift,
        AverageMS, AvicaMetaMS, SnRating, FillInputMs,
        FinalSplitMs,
        Calibration
    ]

    def __init__(self, pipe_params: dict = None, steps: list = None):

        provided_pipe_params = dict(pipe_params or {})
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
