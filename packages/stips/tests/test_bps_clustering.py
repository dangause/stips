"""Tests for stips.core.bps_clustering (one BPS job per visit)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core.bps_clustering import visit_cluster_config, visit_task_labels  # noqa: E402

VISIT = {"instrument", "visit", "detector"}
EXPOSURE = {"instrument", "exposure", "detector"}
GLOBAL = {"instrument"}


def test_per_visit_chain_is_grouped():
    order = ["isr", "calibrateImage", "consolidate"]
    dims = {"isr": EXPOSURE, "calibrateImage": VISIT, "consolidate": {"instrument", "visit"}}
    preds = {"isr": set(), "calibrateImage": {"isr"}, "consolidate": {"calibrateImage"}}
    assert visit_task_labels(order, dims, preds) == ["isr", "calibrateImage", "consolidate"]


def test_tasks_without_visit_stay_out():
    order = ["isr", "calibrateImage", "makeVisitTable"]
    dims = {"isr": EXPOSURE, "calibrateImage": VISIT, "makeVisitTable": GLOBAL}
    preds = {"isr": set(), "calibrateImage": {"isr"}, "makeVisitTable": {"calibrateImage"}}
    assert visit_task_labels(order, dims, preds) == ["isr", "calibrateImage"]


def test_visit_task_after_a_global_one_would_make_a_cycle():
    # calibrateImage -> associate (global) -> analyzeVisit: putting analyzeVisit
    # in the visit cluster would make cluster -> associate -> cluster.
    order = ["calibrateImage", "associate", "analyzeVisit", "plotVisit"]
    dims = {
        "calibrateImage": VISIT,
        "associate": GLOBAL,
        "analyzeVisit": VISIT,
        "plotVisit": VISIT,
    }
    preds = {
        "calibrateImage": set(),
        "associate": {"calibrateImage"},
        "analyzeVisit": {"associate", "calibrateImage"},
        "plotVisit": {"analyzeVisit"},
    }
    assert visit_task_labels(order, dims, preds) == ["calibrateImage"]


def test_global_input_not_fed_by_the_cluster_is_fine():
    # A global task with no visit ancestry (a lookup table, say) feeding a
    # per-visit task makes no cycle.
    order = ["table", "isr", "calibrateImage"]
    dims = {"table": GLOBAL, "isr": EXPOSURE, "calibrateImage": VISIT}
    preds = {"table": set(), "isr": {"table"}, "calibrateImage": {"isr"}}
    assert visit_task_labels(order, dims, preds) == ["isr", "calibrateImage"]


@pytest.mark.parametrize("n", [0, 1])
def test_no_cluster_for_fewer_than_two_tasks(n):
    order = ["calibrateImage", "makeVisitTable"][: n + 1]
    dims = {"calibrateImage": VISIT if n else GLOBAL, "makeVisitTable": GLOBAL}
    preds = {"calibrateImage": set(), "makeVisitTable": {"calibrateImage"}}
    assert visit_cluster_config(order, dims, preds) is None


def test_cluster_config_shape():
    # Nothing outside the visit needs these, so they are all one job.
    order = ["isr", "calibrateImage"]
    dims = {"isr": EXPOSURE, "calibrateImage": VISIT}
    preds = {"isr": set(), "calibrateImage": {"isr"}}
    assert visit_cluster_config(order, dims, preds) == {
        "visit": {
            "pipetasks": "isr, calibrateImage",
            "dimensions": "visit",
            "equalDimensions": "visit:exposure",
        }
    }


def test_tasks_nothing_outside_needs_get_their_own_job():
    # A failing analysis quantum must not fail the job that makeVisitTable
    # waits on: BPS skips every job downstream of a failed one.
    order = ["isr", "calibrateImage", "consolidate", "analyze", "plot", "makeVisitTable"]
    dims = {
        "isr": EXPOSURE,
        "calibrateImage": VISIT,
        "consolidate": {"instrument", "visit"},
        "analyze": VISIT,
        "plot": VISIT,
        "makeVisitTable": GLOBAL,
    }
    preds = {
        "isr": set(),
        "calibrateImage": {"isr"},
        "consolidate": {"calibrateImage"},
        "analyze": {"calibrateImage"},
        "plot": {"analyze"},
        "makeVisitTable": {"consolidate"},
    }
    section = visit_cluster_config(order, dims, preds)
    assert section["visit"]["pipetasks"] == "isr, calibrateImage, consolidate"
    assert section["visit_leaves"]["pipetasks"] == "analyze, plot"
    assert section["visit_leaves"]["dimensions"] == "visit"


def test_slurm_sites_use_visit_clustering():
    root = Path(__file__).resolve().parents[3]
    for site in ("slurm", "singularity-slurm"):
        text = (root / "bps" / "sites" / f"{site}.yaml").read_text()
        assert "clusterAlgorithm: stips.core.bps_clustering.visit_clustering" in text


class _Config:
    """Stand-in for BpsConfig.search."""

    def __init__(self, **values):
        self.values = values

    def search(self, key, opt=None):
        return (key in self.values, self.values.get(key))


def test_empty_cluster_section_is_not_a_user_definition():
    # ctrl_bps leaves `cluster: {}` in the submitted config.
    from stips.core.bps_clustering import _defines_clusters

    assert not _defines_clusters(_Config())
    assert not _defines_clusters(_Config(cluster={}))
    assert _defines_clusters(_Config(cluster={"visit": {"pipetasks": "isr"}}))
