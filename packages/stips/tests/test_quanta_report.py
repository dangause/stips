"""Tests for stips.core.quanta_report (pipetask --summary JSON parsing)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _write(tmp_path, obj) -> Path:
    p = tmp_path / "run_summary.json"
    p.write_text(json.dumps(obj))
    return p


def test_summary_run_args():
    from stips.core import quanta_report

    assert quanta_report.summary_run_args("/x/s.json") == ["--summary", "/x/s.json"]
    assert quanta_report.summary_run_args(Path("/x/s.json")) == ["--summary", "/x/s.json"]


def test_counts_success_and_failure(tmp_path):
    from stips.core import quanta_report

    # lowercase status values, as the installed v30 stack serializes them
    p = _write(
        tmp_path,
        {
            "quantaReports": [
                {"status": "success", "taskLabel": "isr"},
                {"status": "success", "taskLabel": "calibrateImage"},
                {"status": "failure", "taskLabel": "subtractImages"},
            ]
        },
    )
    assert quanta_report.parse_summary_file(p) == (2, 1)


def test_timeout_counts_as_failure_skipped_ignored(tmp_path):
    from stips.core import quanta_report

    p = _write(
        tmp_path,
        {
            "quantaReports": [
                {"status": "success"},
                {"status": "timeout"},
                {"status": "skipped"},
            ]
        },
    )
    # success=1, failed=1 (timeout), skipped not counted
    assert quanta_report.parse_summary_file(p) == (1, 1)


def test_status_case_insensitive(tmp_path):
    from stips.core import quanta_report

    p = _write(
        tmp_path,
        {"quantaReports": [{"status": "SUCCESS"}, {"status": "Failure"}]},
    )
    assert quanta_report.parse_summary_file(p) == (1, 1)


def test_empty_quanta_list(tmp_path):
    from stips.core import quanta_report

    p = _write(tmp_path, {"quantaReports": []})
    assert quanta_report.parse_summary_file(p) == (0, 0)


def test_missing_file_returns_none(tmp_path):
    from stips.core import quanta_report

    assert quanta_report.parse_summary_file(tmp_path / "nope.json") is None


def test_malformed_json_returns_none(tmp_path):
    from stips.core import quanta_report

    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert quanta_report.parse_summary_file(p) is None


def test_unrecognized_shape_returns_none(tmp_path):
    from stips.core import quanta_report

    # no quantaReports key -> None (fall back to regex), not (0, 0)
    p = _write(tmp_path, {"somethingElse": []})
    assert quanta_report.parse_summary_file(p) is None
