from pathlib import Path

import pytest


def test_select_template_coadd_qmax_lt_one() -> None:
    """Ensure DRP coadd quantile config remains valid for LSST RangeField."""
    lsst_pipe_base = pytest.importorskip("lsst.pipe.base")
    pipeline_cls = lsst_pipe_base.Pipeline

    drp_yaml = Path(__file__).resolve().parents[1] / "pipelines" / "DRP.yaml"
    pipeline = pipeline_cls.fromFile(f"{drp_yaml}#coadds-only")
    graph = pipeline.to_graph()

    assert "selectTemplateCoaddVisits" in graph.tasks
    qmax = graph.tasks["selectTemplateCoaddVisits"].config.qMax
    assert qmax < 1.0
