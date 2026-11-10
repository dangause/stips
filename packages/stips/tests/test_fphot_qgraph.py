"""Forced photometry builds a quantum graph, then runs it.

``BPSExecutor`` sends only a ``pipetask run -g <graph>`` to the cluster; a
one-step ``pipetask run --pipeline`` ran on the controller.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core import fphot  # noqa: E402

PARENT = "Nickel/runs/20211030/processCcd/20261006T110000Z"
DIFF = "Nickel/runs/20211030/diff/ts/run"


def _run(tmp_path, image_type, *, run_rc=0, empty=False):
    config = MagicMock()
    config.repo = tmp_path
    config.require_profile.return_value = SimpleNamespace(
        name="Nickel", collection_prefix="Nickel", skymap_collection="skymaps/x",
        night_to_dayobs_offset_days=1,
    )  # fmt: skip
    config.profile = config.require_profile.return_value
    config.resolve_pipeline.return_value = Path("/p/ForcedPhotRaDec.yaml")
    calls = []

    def run_pipetask(args, cfg, **kw):
        calls.append((list(args), kw))
        rc = run_rc if args[0] == "run" else 0
        return SimpleNamespace(returncode=rc, stdout="", stderr="boom" if rc else "")

    executor = MagicMock()
    executor.run_pipetask.side_effect = run_pipetask
    with (
        patch.object(fphot, "resolve_processccd_collections", return_value=[PARENT]),
        patch.object(fphot, "_select_diff_collection", return_value=(DIFF, [])),
        patch.object(fphot.butler_query, "quantum_graph_is_empty", return_value=empty),
        patch.object(fphot, "redefine_chain") as chain,
    ):  # fmt: skip
        result = fphot.run("20211030", 56.65, 43.23, config, band="rp",
                           image_type=image_type, jobs=3, executor=executor)  # fmt: skip
    return result, calls, chain


@pytest.mark.parametrize(
    "image_type, subset, task",
    [("visit", "visit-image", "forcedPhotRaDec"), ("diffim", "diffim", "forcedPhotDiffimRaDec")],
)
def test_builds_graph_then_runs_it(tmp_path, image_type, subset, task):
    result, calls, chain = _run(tmp_path, image_type)
    assert result.success, result.error
    (qgraph, _), (run, run_kw) = calls
    assert qgraph[0] == "qgraph"
    assert qgraph[qgraph.index("-p") + 1] == f"/p/ForcedPhotRaDec.yaml#{subset}"
    graph = qgraph[qgraph.index("--save-qgraph") + 1]
    assert f"{task}:useConfigCoords=True" in qgraph
    assert f"{task}:ra=[56.65]" in qgraph

    assert run[:2] == ["run", "-b"]
    assert run[run.index("-g") + 1] == graph
    output_run = qgraph[qgraph.index("--output-run") + 1]
    assert run[run.index("--output-run") + 1] == output_run
    assert run[run.index("-j") + 1] == "3"
    assert "--summary" in run
    assert run_kw["output_run"] == output_run

    # The output chain gets what `pipetask -o` gave it: the run, then the inputs.
    parent = qgraph[qgraph.index("-o") + 1]
    inputs = qgraph[qgraph.index("-i") + 1].split(",")
    chain.assert_called_once()
    assert chain.call_args.args[1:] == (parent, [output_run, *inputs])
    assert result.output_collections == [parent]


def test_failed_run_is_an_error_and_leaves_no_chain(tmp_path):
    result, _, chain = _run(tmp_path, "visit", run_rc=1)
    assert not result.success
    assert "boom" in result.error
    chain.assert_not_called()


def test_empty_graph_is_an_error_and_skips_the_run(tmp_path):
    result, calls, chain = _run(tmp_path, "visit", empty=True)
    assert not result.success
    assert "no quanta" in result.error.lower()
    assert [c[0][0] for c in calls] == ["qgraph"]
    chain.assert_not_called()
