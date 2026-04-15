from .core import VascoPipelineCore, DEFAULT_PARAMS
from .steps import PreProcessFitsIdi, FitsIdiToMS, Phaseshift, VascoMetaMS, AverageMS, SnRating, FinalSplitMs, Calibration, FillInputMs


class VascoPipeline(VascoPipelineCore):
    
    DEFAULT_STEPS = [
        PreProcessFitsIdi, FitsIdiToMS, 
        Phaseshift, 
        AverageMS, VascoMetaMS, SnRating, FillInputMs,
        FinalSplitMs, 
        Calibration
    ]
    
    def __init__(self, pipe_params: dict = None, steps: list = None):
        
        merged_params = {**DEFAULT_PARAMS, **(pipe_params or {})}
        super().__init__(
            pipe_params = merged_params,
            steps       = steps or self.DEFAULT_STEPS,
        )