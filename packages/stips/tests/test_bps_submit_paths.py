"""Each BPS submission gets a config directory and submit path of its own.

Nights run concurrently (``options.concurrent_nights``) submit within the same
second, so a name built from the pipeline, night and a one-second timestamp is
not enough: the submissions overwrote each other's rendered config and the
second ``bps submit`` failed creating an existing submit directory.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO_ROOT = Path(__file__).resolve().parents[3]
TIMESTAMP = "20261110T113848"


def _config(tmp_path):
    config = MagicMock()
    config.instrument_dir = REPO_ROOT / "instruments" / "nickel"
    config.repo = tmp_path / "repo"
    config.stack_dir = Path("/fake/stack")
    config.cp_pipe_dir = Path("/fake/cp_pipe")
    config.raw_parent_dir = Path("/fake/raw")
    config.refcat_repo = Path("/fake/refcats")
    return config


def _submit_path(rendered: Path) -> str:
    return yaml.safe_load(rendered.read_text())["submitPath"]


def _submit(tmp_path, qgraph_file, site="local"):
    from stips.core import bps

    bps_cfg = bps.BPSConfig(
        pipeline="custom",
        night="00000000",
        site=site,
        qgraph_file=qgraph_file,
        output_run="r/run",
    )
    done = subprocess.CompletedProcess(["bps"], 0, stdout="Run Id: None\n", stderr="")
    with patch("stips.core.bps.generate_timestamp", return_value=TIMESTAMP), patch(
        "stips.core.stack.run_with_stack", return_value=done
    ):
        result = bps.submit(bps_cfg, _config(tmp_path))
    assert result.success, result.error
    return Path(result.config_file)


class TestSubmissionPaths:
    def test_concurrent_nights_do_not_share_paths(self, tmp_path):
        a = _submit(tmp_path, "/q/processCcd_20091029_20261110T163738Z_cfg0.qg")
        b = _submit(tmp_path, "/q/processCcd_20091030_20261110T163738Z_cfg0.qg")

        assert a.parent != b.parent
        assert _submit_path(a) != _submit_path(b)
        assert "processCcd_20091029" in _submit_path(a)
        assert "processCcd_20091030" in _submit_path(b)
        # Each keeps its own graph.
        assert "20091029" in yaml.safe_load(a.read_text())["qgraphFile"]
        assert "20091030" in yaml.safe_load(b.read_text())["qgraphFile"]

    def test_same_graph_twice_in_one_second(self, tmp_path):
        a = _submit(tmp_path, "/q/template_t305_i.qg")
        b = _submit(tmp_path, "/q/template_t305_i.qg")

        assert a.parent != b.parent
        assert _submit_path(a) != _submit_path(b)

    def test_parsl_run_dir_is_per_submission(self, tmp_path):
        """Parsl numbers its run directories by listing them, which races."""
        a = _submit(tmp_path, "/q/a.qg", site="singularity-slurm")
        b = _submit(tmp_path, "/q/b.qg", site="singularity-slurm")

        def run_dir(rendered):
            site = rendered.parent / "sites" / "singularity-slurm.yaml"
            return yaml.safe_load(site.read_text())["site"]["singularity-slurm"]["run_dir"]

        assert run_dir(a) != run_dir(b)
        assert run_dir(a).startswith(_submit_path(a))
