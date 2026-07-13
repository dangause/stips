"""Collector prefers structured provenance/runs.json over log regex (F-023/D2).

Builds a fake run log directory plus a fixture ``runs.json`` (written via
``core.provenance``'s own dataclasses, so the fixture always matches the real
schema) and asserts the dashboard's per-night science status and run-level
science counts come from the structured records, not from the summary.txt
regexes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core.provenance import RunRecord, save_store  # noqa: E402
from stips.dashboard import collector  # noqa: E402


def _record(repo: Path, night: str, status: str, **kw) -> RunRecord:
    return RunRecord(
        repo=repo.name,
        repo_path=str(repo),
        target="2023ixf",
        instrument="nickel",
        night=night,
        step="science",
        final_status=status,
        timestamp_end=kw.pop("timestamp_end", "20260701T000000Z"),
        **kw,
    )


def _make_run_dir(tmp_path: Path, repo: Path, nights: list[str]) -> Path:
    """A completed run whose summary.txt DISAGREES with provenance."""
    run_dir = tmp_path / "logs" / "20260701_000000_1"
    run_dir.mkdir(parents=True)
    (run_dir / "run_info.txt").write_text(
        "Run ID: 20260701_000000_1\n"
        "Started: 2026-07-01T00:00:00+00:00\n"
        f"Repository: {repo}\n"
    )
    # summary.txt claims every night succeeded — the regex-scraped view
    (run_dir / "summary.txt").write_text(
        "Status: SUCCESS\n"
        "Object: 2023ixf\n"
        "Bands: ['r', 'i']\n"
        f"Science OK: {len(nights)}/{len(nights)}\n"
        "Failed science: []\n"
    )
    science_dir = run_dir / "science"
    science_dir.mkdir()
    for night in nights:
        (science_dir / f"{night}.log").write_text("ok\n")
    return run_dir


def _point_store_at(monkeypatch, store: Path) -> None:
    monkeypatch.setattr(collector, "_provenance_store_path", lambda: store)


class TestProvenanceOverlay:
    def test_science_status_comes_from_runs_json(self, tmp_path, monkeypatch):
        """Structured record (failed) beats the log-derived guess (success)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        run_dir = _make_run_dir(tmp_path, repo, ["20230519", "20230521"])

        store = tmp_path / "provenance" / "runs.json"
        save_store(
            store,
            [
                _record(repo, "20230519", "success"),
                _record(repo, "20230521", "failed"),
            ],
        )
        _point_store_at(monkeypatch, store)

        info = collector.get_run(run_dir.parent, run_dir.name)
        assert info is not None
        assert info.provenance_backed is True
        by_night = {ns.night: ns.science for ns in info.nights}
        assert by_night["20230519"] == "success"
        # summary.txt said success; provenance knows it failed — structured wins
        assert by_night["20230521"] == "failed"
        # full coverage → run-level counts recomputed from provenance
        assert info.science_total == 2
        assert info.science_ok == 1

    def test_partial_status_mapped(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        run_dir = _make_run_dir(tmp_path, repo, ["20230519"])

        store = tmp_path / "provenance" / "runs.json"
        save_store(store, [_record(repo, "20230519", "partial")])
        _point_store_at(monkeypatch, store)

        info = collector.get_run(run_dir.parent, run_dir.name)
        assert info.nights[0].science == "partial"
        # partial still counts as ok (matches the log-derived convention)
        assert info.science_ok == 1
        assert info.science_total == 1

    def test_latest_record_wins_per_night(self, tmp_path, monkeypatch):
        """Re-runs append records (key includes timestamp); newest wins."""
        repo = tmp_path / "repo"
        repo.mkdir()
        run_dir = _make_run_dir(tmp_path, repo, ["20230519"])

        store = tmp_path / "provenance" / "runs.json"
        save_store(
            store,
            [
                _record(repo, "20230519", "failed", timestamp_end="20260630T000000Z"),
                _record(repo, "20230519", "success", timestamp_end="20260701T120000Z"),
            ],
        )
        _point_store_at(monkeypatch, store)

        info = collector.get_run(run_dir.parent, run_dir.name)
        assert info.nights[0].science == "success"

    def test_partial_coverage_keeps_log_counts(self, tmp_path, monkeypatch):
        """Records for only some nights must not misstate run-level totals."""
        repo = tmp_path / "repo"
        repo.mkdir()
        run_dir = _make_run_dir(tmp_path, repo, ["20230519", "20230521"])

        store = tmp_path / "provenance" / "runs.json"
        save_store(store, [_record(repo, "20230519", "failed")])
        _point_store_at(monkeypatch, store)

        info = collector.get_run(run_dir.parent, run_dir.name)
        # the covered night is refined...
        by_night = {ns.night: ns.science for ns in info.nights}
        assert by_night["20230519"] == "failed"
        # ...but the run-level counts keep the summary.txt values (2/2)
        assert info.science_total == 2
        assert info.science_ok == 2

    def test_stack_version_and_target_exposed(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        run_dir = _make_run_dir(tmp_path, repo, ["20230519"])

        store = tmp_path / "provenance" / "runs.json"
        rec = _record(repo, "20230519", "success")
        rec.lsst_pipelines_version = "gf03f954c0e+3d14ea8aaf"
        rec.lsst_stack_version = "lsst-scipipe-12.1.0"
        save_store(store, [rec])
        _point_store_at(monkeypatch, store)

        info = collector.get_run(run_dir.parent, run_dir.name)
        # true pipelines version preferred over the conda env name (F-019)
        assert info.stack_version == "gf03f954c0e+3d14ea8aaf"

    def test_no_store_keeps_log_derived_view(self, tmp_path, monkeypatch):
        """Absent runs.json → graceful fallback to the log-scraped picture."""
        repo = tmp_path / "repo"
        repo.mkdir()
        run_dir = _make_run_dir(tmp_path, repo, ["20230519"])
        _point_store_at(monkeypatch, store=tmp_path / "nope" / "runs.json")

        info = collector.get_run(run_dir.parent, run_dir.name)
        assert info is not None
        assert info.provenance_backed is False
        assert info.stack_version == ""
        assert info.nights[0].science == "success"
        assert info.science_total == 1

    def test_other_repo_records_ignored(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        other = tmp_path / "other_repo"
        other.mkdir()
        run_dir = _make_run_dir(tmp_path, repo, ["20230519"])

        store = tmp_path / "provenance" / "runs.json"
        save_store(store, [_record(other, "20230519", "failed")])
        _point_store_at(monkeypatch, store)

        info = collector.get_run(run_dir.parent, run_dir.name)
        assert info.provenance_backed is False
        assert info.nights[0].science == "success"

    def test_running_science_cell_not_clobbered(self, tmp_path, monkeypatch):
        """A live 'running' cell is never overwritten by an old record."""
        repo = tmp_path / "repo"
        repo.mkdir()
        run_dir = tmp_path / "logs" / "20260701_000000_2"
        run_dir.mkdir(parents=True)
        (run_dir / "run_info.txt").write_text(
            "Run ID: 20260701_000000_2\n"
            "Started: 2026-07-01T00:00:00+00:00\n"
            f"Repository: {repo}\n"
        )
        # Active run currently in the science phase, night dir exists but no
        # per-night science log yet -> collector marks science 'running'.
        (run_dir / "pipeline.log").write_text(
            "Pipeline run for 2023ixf\nRunning science for 20230519\n"
        )
        (run_dir / "calibs").mkdir()
        (run_dir / "calibs" / "20230519.log").write_text("ok\n")

        store = tmp_path / "provenance" / "runs.json"
        save_store(store, [_record(repo, "20230519", "failed")])
        _point_store_at(monkeypatch, store)

        info = collector.get_run(run_dir.parent, run_dir.name)
        assert info.current_phase is collector.Phase.SCIENCE
        assert info.nights[0].science == "running"
