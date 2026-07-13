"""Tests for stips.dashboard.queries (dashboard Butler queries, F-023).

The dashboard's old ``butler_query.py``/``catalog_query.py`` ran bare
``python3 -c`` subprocesses (no stack activation) against stale dataset-type
names, so it silently reported zeros for current runs. These tests pin the fix:

* every query goes through ``stips.core.stack.run_butler_python_json`` (mocked
  here — no stack needed), never a bare subprocess;
* the snippets query the CURRENT canonical dataset-type names from
  ``stips.core.dataset_types`` and never the stale ones;
* the snippet builders emit valid, version-gated Python (v28+ API with a v27
  registry fallback), matching the house pattern in ``core/butler_query``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

STALE_NAMES = (
    "goodSeeingDiff_differenceExp",
    "goodSeeingDiff_templateExp",
    "forced_diff_radec",
    "initial_pvi",
    '"calexp"',
    "'calexp'",
)


def _cfg(repo: str = "/base_repo"):
    from stips.core.config import Config

    return Config(
        repo=Path(repo),
        stack_dir=Path("/stack"),
        instrument_dir=Path("/instruments/nickel"),
        raw_parent_dir=Path("/raw"),
    )


def _write_run_info(logs_dir: Path, run_id: str, repo: Path) -> None:
    run_dir = logs_dir / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_info.txt").write_text(
        f"Run ID: {run_id}\nStarted: 2026-07-01T00:00:00+00:00\nRepository: {repo}\n"
    )


def _imported_modules(py_file: Path) -> set[str]:
    """Top-level module names imported anywhere in ``py_file`` (via ast)."""
    tree = ast.parse(py_file.read_text())
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


class TestNoBareSubprocessPath:
    def test_queries_module_does_not_spawn_subprocesses(self):
        """The bare ``python3 -c`` path is gone: no subprocess import at all."""
        import stips.dashboard.queries as q

        assert "subprocess" not in _imported_modules(Path(q.__file__))

    def test_image_renderer_does_not_spawn_subprocesses(self):
        import stips.dashboard.image_renderer as ir

        assert "subprocess" not in _imported_modules(Path(ir.__file__))

    def test_old_modules_are_gone(self):
        import importlib.util

        assert importlib.util.find_spec("stips.dashboard.butler_query") is None
        assert importlib.util.find_spec("stips.dashboard.catalog_query") is None


class TestCurrentDatasetTypes:
    def test_monitored_types_are_core_constants(self):
        from stips.core import dataset_types as dts
        from stips.dashboard.queries import MONITORED_DATASET_TYPES

        assert dts.DIFFERENCE_IMAGE in MONITORED_DATASET_TYPES
        assert dts.DIA_SOURCE_UNFILTERED in MONITORED_DATASET_TYPES
        assert dts.FORCED_PHOT_DIFFIM_RADEC in MONITORED_DATASET_TYPES
        assert dts.PRELIMINARY_VISIT_IMAGE in MONITORED_DATASET_TYPES

    def test_no_stale_names_in_query_constants(self):
        from stips.dashboard.queries import (
            CATALOG_TYPES,
            IMAGE_DATASET_TYPES,
            MONITORED_DATASET_TYPES,
        )

        for name in (
            list(MONITORED_DATASET_TYPES)
            + list(IMAGE_DATASET_TYPES)
            + list(CATALOG_TYPES)
        ):
            assert name not in (
                "goodSeeingDiff_differenceExp",
                "goodSeeingDiff_templateExp",
                "forced_diff_radec",
                "initial_pvi",
                "calexp",
            )

    def test_counts_script_queries_current_names_only(self):
        from stips.dashboard.queries import (
            MONITORED_DATASET_TYPES,
            _build_counts_script,
        )

        s = _build_counts_script("/repo", MONITORED_DATASET_TYPES)
        ast.parse(s)
        assert "difference_image" in s
        assert "dia_source_unfiltered" in s
        assert "forced_phot_diffim_radec" in s
        assert "preliminary_visit_image" in s
        for stale in STALE_NAMES:
            assert stale not in s

    def test_image_list_script_queries_current_names_only(self):
        from stips.dashboard.image_renderer import _build_list_script

        s = _build_list_script("/repo")
        ast.parse(s)
        assert "preliminary_visit_image" in s
        assert "template_detector" in s
        assert "difference_image" in s
        for stale in STALE_NAMES:
            assert stale not in s


class TestScriptBuilders:
    def test_counts_script_is_version_gated(self):
        from stips.dashboard.queries import (
            MONITORED_DATASET_TYPES,
            _build_counts_script,
        )

        s = _build_counts_script("/repo", MONITORED_DATASET_TYPES)
        # v28+ public API preferred, v27 registry fallback present
        assert "butler.query_datasets" in s
        assert "registry.queryDatasets" in s
        assert "Butler.from_config" in s
        assert "MissingDatasetTypeError" in s

    def test_catalog_script_valid_and_parameterized(self):
        from stips.dashboard.queries import _build_catalog_script

        s = _build_catalog_script(
            "/repo",
            "dia_source_unfiltered",
            ["coord_ra", "coord_dec"],
            "instrument='Nickel' AND day_obs=20230520",
            limit=100,
            offset=20,
        )
        ast.parse(s)
        assert "dia_source_unfiltered" in s
        assert "day_obs=20230520" in s
        assert "coord_ra" in s

    def test_metrics_script_valid_and_parameterized(self):
        from stips.dashboard.queries import METRIC_TYPES, _build_metrics_script

        fields = {dt: list(info["metrics"]) for dt, info in METRIC_TYPES.items()}
        s = _build_metrics_script("/repo", fields)
        ast.parse(s)
        assert "calibrateImage_metadata_metrics" in s
        assert "spatialKernelSum" in s

    def test_render_script_valid_and_parameterized(self):
        from stips.dashboard.image_renderer import _build_render_script

        s = _build_render_script(
            "/repo", "difference_image", "20230520", "r", "/tmp/out.png", "Nickel"
        )
        ast.parse(s)
        assert "difference_image" in s
        assert "day_obs=20230520" in s
        assert "/tmp/out.png" in s


class TestQueryDatasetCounts:
    def test_routes_through_run_butler_python_json(self, tmp_path):
        """The counts query executes in-stack with a repo-swapped Config."""
        import stips.dashboard.queries as q

        repo = tmp_path / "repo"
        repo.mkdir()
        logs = tmp_path / "logs"
        _write_run_info(logs, "run1", repo)

        payload = {
            "dataset_types": q.MONITORED_DATASET_TYPES,
            "nights": {"20230519": {"difference_image": {"r": 3}}},
        }
        with patch.object(
            q, "run_butler_python_json", return_value=payload
        ) as mocked:
            q._counts_cache.clear()
            out = q.query_dataset_counts(_cfg(), "run1", logs)

        assert out["available"] is True
        assert out["nights"]["20230519"]["difference_image"]["r"] == 3
        # The in-stack snippet was built for THIS run's repo, on a Config that
        # keeps the launch stack but swaps in the run's repo path.
        (script, used_cfg), _ = mocked.call_args
        assert str(repo) in script
        assert used_cfg.repo == repo
        assert used_cfg.stack_dir == Path("/stack")

    def test_counts_cached_per_repo(self, tmp_path):
        import stips.dashboard.queries as q

        repo = tmp_path / "repo"
        repo.mkdir()
        logs = tmp_path / "logs"
        _write_run_info(logs, "run1", repo)

        payload = {"dataset_types": [], "nights": {}}
        with patch.object(
            q, "run_butler_python_json", return_value=payload
        ) as mocked:
            q._counts_cache.clear()
            q.query_dataset_counts(_cfg(), "run1", logs)
            q.query_dataset_counts(_cfg(), "run1", logs)
        assert mocked.call_count == 1
        q._counts_cache.clear()

    def test_failed_snippet_reads_as_unavailable_not_zero(self, tmp_path):
        """A failed in-stack query must NOT masquerade as 'zero datasets'."""
        import stips.dashboard.queries as q

        repo = tmp_path / "repo"
        repo.mkdir()
        logs = tmp_path / "logs"
        _write_run_info(logs, "run1", logs / "nonexistent-marker")
        _write_run_info(logs, "run2", repo)

        with patch.object(q, "run_butler_python_json", return_value=None):
            q._counts_cache.clear()
            out = q.query_dataset_counts(_cfg(), "run2", logs)
        assert out["available"] is False
        assert out["error"]

    def test_no_config_reads_as_unavailable(self, tmp_path):
        import stips.dashboard.queries as q

        out = q.query_dataset_counts(None, "run1", tmp_path)
        assert out["available"] is False
        assert "config" in out["error"]

    def test_missing_repo_reads_as_unavailable(self, tmp_path):
        import stips.dashboard.queries as q

        out = q.query_dataset_counts(_cfg(), "no-such-run", tmp_path)
        assert out["available"] is False


class TestQueryCatalog:
    def test_where_clause_and_result_mapping(self, tmp_path):
        import stips.dashboard.queries as q

        payload = {"columns": ["night", "band"], "rows": [{"night": "x"}], "total": 1}
        with patch.object(
            q, "run_butler_python_json", return_value=payload
        ) as mocked:
            out = q.query_catalog(
                _cfg(),
                str(tmp_path),
                "dia_source_unfiltered",
                night="20230519",
                band="r",
                instrument_name="Nickel",
            )
        assert out["available"] is True
        assert out["total"] == 1
        (script, _), _ = mocked.call_args
        assert "instrument='Nickel'" in script
        assert "day_obs=20230519" in script
        assert "band='r'" in script

    def test_unknown_catalog_rejected_without_query(self, tmp_path):
        import stips.dashboard.queries as q

        with patch.object(q, "run_butler_python_json") as mocked:
            out = q.query_catalog(
                _cfg(), str(tmp_path), "calexp", instrument_name="Nickel"
            )
        assert out["available"] is False
        mocked.assert_not_called()


class TestQueryMetrics:
    def test_thresholds_always_attached(self, tmp_path):
        import stips.dashboard.queries as q

        with patch.object(q, "run_butler_python_json", return_value=None):
            out = q.query_metrics(_cfg(), str(tmp_path))
        assert out["available"] is False
        assert "diffimMetadata_metrics" in out["thresholds"]

    def test_success_maps_metric_groups(self, tmp_path):
        import stips.dashboard.queries as q

        payload = {
            "metric_groups": {"diffimMetadata_metrics": {"20230519/r": {"x": 1.0}}}
        }
        with patch.object(q, "run_butler_python_json", return_value=payload):
            out = q.query_metrics(_cfg(), str(tmp_path))
        assert out["available"] is True
        assert out["metric_groups"]["diffimMetadata_metrics"]["20230519/r"] == {
            "x": 1.0
        }


class TestResolveRepoPath:
    def test_resolves_existing_repo(self, tmp_path):
        from stips.dashboard.queries import resolve_repo_path

        repo = tmp_path / "repo"
        repo.mkdir()
        logs = tmp_path / "logs"
        _write_run_info(logs, "run1", repo)
        assert resolve_repo_path(logs, "run1") == str(repo)

    def test_none_for_missing_run_info_or_stale_repo(self, tmp_path):
        from stips.dashboard.queries import resolve_repo_path

        assert resolve_repo_path(tmp_path, "absent") is None
        _write_run_info(tmp_path / "logs", "run1", tmp_path / "deleted-repo")
        assert resolve_repo_path(tmp_path / "logs", "run1") is None


class TestAppRouting:
    """The FastAPI endpoints route through the new queries module."""

    def test_butler_counts_endpoint_uses_queries(self, tmp_path, monkeypatch):
        import pytest

        pytest.importorskip("fastapi")
        pytest.importorskip("httpx")
        from fastapi.testclient import TestClient

        import stips.dashboard.queries as q
        from stips.dashboard.app import create_app

        seen = {}

        def fake_counts(config, run_id, logs_dir):
            seen["args"] = (config, run_id, logs_dir)
            return {"available": True, "error": None, "dataset_types": [], "nights": {}}

        monkeypatch.setattr(q, "query_dataset_counts", fake_counts)

        cfg = _cfg()
        app = create_app(tmp_path, instrument_name="Nickel", config=cfg)
        client = TestClient(app)
        resp = client.get("/api/butler-counts/run1")
        assert resp.status_code == 200
        assert resp.json()["available"] is True
        assert seen["args"][0] is cfg
        assert seen["args"][1] == "run1"

    def test_catalog_endpoint_uses_queries(self, tmp_path, monkeypatch):
        import pytest

        pytest.importorskip("fastapi")
        pytest.importorskip("httpx")
        from fastapi.testclient import TestClient

        import stips.dashboard.queries as q
        from stips.dashboard.app import create_app

        repo = tmp_path / "repo"
        repo.mkdir()
        logs = tmp_path / "logs"
        _write_run_info(logs, "run1", repo)

        seen = {}

        def fake_catalog(config, repo_path, catalog_type, *a, instrument_name, **kw):
            seen["repo_path"] = repo_path
            seen["catalog_type"] = catalog_type
            seen["instrument_name"] = instrument_name
            return {
                "available": True,
                "error": None,
                "columns": [],
                "rows": [],
                "total": 0,
            }

        monkeypatch.setattr(q, "query_catalog", fake_catalog)

        app = create_app(logs, instrument_name="Nickel", config=_cfg())
        client = TestClient(app)
        resp = client.get("/api/catalog/run1/dia_source_unfiltered")
        assert resp.status_code == 200
        assert resp.json()["available"] is True
        assert seen["repo_path"] == str(repo)
        assert seen["catalog_type"] == "dia_source_unfiltered"
        assert seen["instrument_name"] == "Nickel"
