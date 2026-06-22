from pathlib import Path

import pytest

# instruments/nickel/tests/test_drp_pipeline_config.py -> parents[3] == repo root.
# Derive the framework-defaults DRP.yaml relative to this file so the test does
# not depend on the caller exporting an env var (only run_with_stack does that),
# matching the file-relative idiom in conftest.py.
DRP_YAML_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "obs_stips"
    / "instrument_defaults"
    / "pipelines"
    / "DRP.yaml"
)


def test_select_template_coadd_qmax_lt_one() -> None:
    """Ensure DRP coadd quantile config remains valid for LSST RangeField."""
    lsst_pipe_base = pytest.importorskip("lsst.pipe.base")
    pipeline_cls = lsst_pipe_base.Pipeline

    if not DRP_YAML_PATH.exists():
        pytest.skip(f"framework DRP.yaml not found at {DRP_YAML_PATH}")
    pipeline = pipeline_cls.fromFile(f"{DRP_YAML_PATH}#coadds-only")
    graph = pipeline.to_graph()

    assert "selectTemplateCoaddVisits" in graph.tasks
    qmax = graph.tasks["selectTemplateCoaddVisits"].config.qMax
    assert qmax < 1.0
