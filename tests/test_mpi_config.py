import inspect

import pytest

from avica.pipe.config import PipeConfig
from avica.pipe.core import PipelineContext
from avica.pipe.main import AvicaPipeline


STEP_MPI_DEFAULTS = {
    "fits_to_ms": 5,
    "avica_avg": 5,
    "avica_snr": 5,
    "avica_split_ms": 10,
    "rpicard": 10,
}


def mpi_value(pipeline, step_name):
    return pipeline.get_kwargs(pipeline._steps[step_name])["mpi_cores"]


def test_mpi_parameter_is_shared_name_with_per_step_defaults():
    PipelineContext.reset_params()
    pipeline = AvicaPipeline()

    for step_name, expected in STEP_MPI_DEFAULTS.items():
        parameters = inspect.signature(pipeline._steps[step_name].run).parameters
        assert "mpi_cores" in parameters
        assert not any(name.startswith("mpi_cores_") for name in parameters)
        assert mpi_value(pipeline, step_name) == expected

    defaults = PipeConfig(None).defaults()
    assert {f"{step}.mpi_cores" for step in STEP_MPI_DEFAULTS} <= defaults.keys()


def test_global_and_step_specific_mpi_overrides():
    PipelineContext.reset_params()
    pipeline = AvicaPipeline({
        "mpi_cores": 3,
        "avica_split_ms.mpi_cores": 7,
        "rpicard.mpi_cores": 9,
    })

    assert mpi_value(pipeline, "fits_to_ms") == 3
    assert mpi_value(pipeline, "avica_avg") == 3
    assert mpi_value(pipeline, "avica_snr") == 3
    assert mpi_value(pipeline, "avica_split_ms") == 7
    assert mpi_value(pipeline, "rpicard") == 9


@pytest.mark.parametrize("old_name,step_name", [
    ("mpi_cores_importfitsidi", "fits_to_ms"),
    ("mpi_cores_avgms", "avica_avg"),
    ("mpi_cores_snrating", "avica_snr"),
    ("mpi_cores_splitms", "avica_split_ms"),
    ("mpi_cores_rpicard", "rpicard"),
])
def test_legacy_mpi_names_are_migrated(old_name, step_name):
    PipelineContext.reset_params()
    with pytest.warns(DeprecationWarning, match=old_name):
        pipeline = AvicaPipeline({old_name: 2})

    assert mpi_value(pipeline, step_name) == 2
    assert old_name not in pipeline.provided_pipe_params
    assert pipeline.provided_pipe_params[f"{step_name}.mpi_cores"] == 2


def test_new_step_specific_name_wins_over_legacy_alias():
    PipelineContext.reset_params()
    with pytest.warns(DeprecationWarning):
        pipeline = AvicaPipeline({
            "mpi_cores_avgms": 2,
            "avica_avg.mpi_cores": 6,
        })

    assert mpi_value(pipeline, "avica_avg") == 6
