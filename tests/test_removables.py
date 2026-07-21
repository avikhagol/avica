from copy import deepcopy
from pathlib import Path

from avica.pipe.core import PipelineContext
from avica.pipe.helpers import del_fl
from avica.pipe.main import AvicaPipeline
from avica.pipe.steps import PreProcessFitsIdi


def test_del_fl_anchors_absolute_pattern_to_workdir(tmp_path):
    wd = tmp_path / "wd"
    raw = wd / "raw"
    raw.mkdir(parents=True)
    removable = raw / "one file.tmp"
    removable.write_text("temporary")

    removed_count = del_fl(wd, fl="/raw/*.tmp", rm=True)

    assert removed_count == 1
    assert not removable.exists()


def test_del_fl_rejects_matches_outside_workdir(tmp_path):
    wd = tmp_path / "wd"
    wd.mkdir()
    outside = tmp_path / "outside.tmp"
    outside.write_text("keep")

    removed_count = del_fl(wd, fl="../outside.tmp", rm=True)

    assert removed_count == 0
    assert outside.exists()


def test_rm_only_removes_before_processing_even_when_rm_pre_is_false(tmp_path):
    wd = tmp_path / "wd"
    input_template = wd / "input_template"
    raw = wd / "raw"
    input_template.mkdir(parents=True)
    raw.mkdir()
    removable = raw / "one.tmp"
    removable.write_text("temporary")

    original_result = deepcopy(PreProcessFitsIdi.result)
    try:
        result = PreProcessFitsIdi().run(
            None,
            [],
            "target",
            str(input_template),
            removables=["raw/*.tmp"],
            rm_only=True,
            rm_pre=False,
        )

        assert not removable.exists()
        assert result.success == [True]
        assert result.success_count == 1
        assert result.failed_count == 0
    finally:
        PreProcessFitsIdi.result = original_result


def test_config_report_distinguishes_defaults_from_input():
    PipelineContext.reset_params()
    pipeline = AvicaPipeline()

    status = pipeline.config_report("preprocess_fitsidi")[0]["removables"]

    assert status.value == ["raw/*.tmp"]
    assert not status.in_input_config


def test_explicit_global_input_overrides_step_default():
    PipelineContext.reset_params()
    removables = ["raw/*.custom"]
    pipeline = AvicaPipeline({"removables": removables})

    kwargs = pipeline.get_kwargs(pipeline._steps["preprocess_fitsidi"])
    status = pipeline.config_report("preprocess_fitsidi")[0]["removables"]

    assert kwargs["removables"] == removables
    assert status.value == removables
    assert status.in_input_config
    assert status.input_name == "removables"


def test_explicit_step_input_overrides_global_input():
    PipelineContext.reset_params()
    pipeline = AvicaPipeline({
        "removables": ["raw/*.global"],
        "preprocess_fitsidi.removables": ["raw/*.step"],
    })

    kwargs = pipeline.get_kwargs(pipeline._steps["preprocess_fitsidi"])

    assert kwargs["removables"] == ["raw/*.step"]
