"""Tests for stips.core.bps_report and the bps run-id scrape fix."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class TestSummaryScript:
    def test_script_is_valid_python_and_uses_structured_api(self):
        from stips.core import bps_report

        s = bps_report._build_summary_script("run42", bps_report.HTCONDOR_SERVICE)
        ast.parse(s)  # raises if malformed
        assert "retrieve_report" in s
        assert "WmsStates" in s
        # counts keyed by enum identity, not table columns
        assert "WmsStates.SUCCEEDED" in s
        assert "WmsStates.PRUNED" in s  # folded into failed
        assert "run42" in s
        assert bps_report.HTCONDOR_SERVICE in s

    def test_script_embeds_values_safely(self):
        from stips.core import bps_report

        # awkward run id with quotes must not break the snippet
        s = bps_report._build_summary_script("ru'n", "x.Service")
        ast.parse(s)


class TestSummaryForRun:
    def _cfg(self):
        cfg = MagicMock()
        cfg.repo = "/repo"
        return cfg

    def test_returns_dict_when_state_present(self):
        from stips.core import bps_report

        payload = {
            "state": "RUNNING",
            "expected": 20,
            "succeeded": 17,
            "failed": 1,
            "unready": 0,
            "ready": 1,
            "running": 1,
        }
        with patch.object(bps_report, "run_butler_python_json", return_value=payload):
            assert bps_report.summary_for_run("r1", self._cfg()) == payload

    def test_none_when_no_report(self):
        from stips.core import bps_report

        # snippet printed "{}" -> empty dict -> fall back
        with patch.object(bps_report, "run_butler_python_json", return_value={}):
            assert bps_report.summary_for_run("r1", self._cfg()) is None

    def test_none_when_query_failed(self):
        from stips.core import bps_report

        with patch.object(bps_report, "run_butler_python_json", return_value=None):
            assert bps_report.summary_for_run("r1", self._cfg()) is None


class TestExtractRunId:
    def test_v30_banner_run_id_label(self):
        from stips.core import bps

        # v30 prints "Run Id:" then "Run Name:"
        out = "Submit dir: /x\nRun Id: 42.0\nRun Name: dia_20230519\n"
        assert bps._extract_run_id(out) == "42.0"

    def test_does_not_match_run_name(self):
        from stips.core import bps

        # if only Run Name is present, no id is returned (not the name)
        assert bps._extract_run_id("Run Name: dia_20230519\n") is None

    def test_legacy_uppercase_label(self):
        from stips.core import bps

        assert bps._extract_run_id("Run ID: abc123\n") == "abc123"

    def test_missing_returns_none(self):
        from stips.core import bps

        assert bps._extract_run_id("nothing here\n") is None
