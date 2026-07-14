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


class TestListRunsScript:
    def test_script_is_valid_python_and_lists_runs(self):
        from stips.core import bps_report

        s = bps_report._build_list_runs_script(bps_report.HTCONDOR_SERVICE)
        ast.parse(s)  # raises if malformed
        assert "retrieve_report" in s
        # run_id=None is the documented "list all runs" form
        assert "run_id=None" in s
        # emits the identifying fields the matcher uses
        assert "wms_id" in s
        assert '"run"' in s
        assert bps_report.HTCONDOR_SERVICE in s

    def test_script_embeds_fqn_safely(self):
        from stips.core import bps_report

        s = bps_report._build_list_runs_script("x'y.Service")
        ast.parse(s)


class TestListRuns:
    def _cfg(self):
        cfg = MagicMock()
        cfg.repo = "/repo"
        return cfg

    def test_returns_list_when_present(self):
        from stips.core import bps_report

        payload = [{"wms_id": "42.0", "run": "Nickel/runs/x/run"}]
        with patch.object(bps_report, "run_butler_python_json", return_value=payload):
            assert bps_report.list_runs(self._cfg()) == payload

    def test_none_when_empty(self):
        from stips.core import bps_report

        with patch.object(bps_report, "run_butler_python_json", return_value=[]):
            assert bps_report.list_runs(self._cfg()) is None

    def test_none_when_query_failed(self):
        from stips.core import bps_report

        with patch.object(bps_report, "run_butler_python_json", return_value=None):
            assert bps_report.list_runs(self._cfg()) is None


class TestSiteClassification:
    def test_parsl_sites_are_synchronous(self):
        from stips.core import bps

        for site in ("local", "slurm", "singularity-slurm", "docker-slurm"):
            assert bps.is_synchronous_site(site) is True

    def test_htcondor_is_asynchronous(self):
        from stips.core import bps

        assert bps.is_synchronous_site("htcondor") is False

    def test_wms_fqn_for_htcondor(self):
        from stips.core import bps

        assert (
            bps.wms_service_fqn_for_site("htcondor")
            == "lsst.ctrl.bps.htcondor.HTCondorService"
        )

    def test_wms_fqn_for_parsl_site(self):
        from stips.core import bps

        assert "parsl" in bps.wms_service_fqn_for_site("local").lower()

    def test_wms_fqn_unknown_site(self):
        from stips.core import bps

        assert bps.wms_service_fqn_for_site("nonsense") is None


class TestMatchRunId:
    def test_unique_match_on_run_field(self):
        from stips.core import bps

        runs = [
            {"wms_id": "1.0", "run": "Nickel/runs/a/run", "payload": "", "path": ""},
            {"wms_id": "2.0", "run": "Nickel/runs/b/run", "payload": "", "path": ""},
        ]
        assert bps._match_run_id(runs, "Nickel/runs/b/run") == "2.0"

    def test_substring_match_on_path(self):
        from stips.core import bps

        runs = [
            {
                "wms_id": "9.0",
                "run": "",
                "payload": "",
                "path": "/repo/bps/submit/custom_x_ts",
            }
        ]
        # output_run echoed inside a longer path still matches
        assert bps._match_run_id(runs, "custom_x_ts") == "9.0"

    def test_ambiguous_match_returns_none(self):
        from stips.core import bps

        runs = [
            {"wms_id": "1.0", "run": "Nickel/runs/x/run", "payload": "", "path": ""},
            {"wms_id": "2.0", "run": "Nickel/runs/x/run", "payload": "", "path": ""},
        ]
        assert bps._match_run_id(runs, "Nickel/runs/x/run") is None

    def test_no_match_returns_none(self):
        from stips.core import bps

        runs = [{"wms_id": "1.0", "run": "other", "payload": "", "path": ""}]
        assert bps._match_run_id(runs, "Nickel/runs/x/run") is None

    def test_empty_output_run_returns_none(self):
        from stips.core import bps

        runs = [{"wms_id": "1.0", "run": "anything", "payload": "", "path": ""}]
        assert bps._match_run_id(runs, "") is None


class TestResolveRunIdViaWms:
    def _cfg(self):
        return MagicMock()

    def test_synchronous_site_skips_wms(self):
        from stips.core import bps

        cfg = bps.BPSConfig(
            pipeline="custom", night="00000000", site="local", output_run="r/run"
        )
        with patch("stips.core.bps_report.list_runs") as mlist:
            assert bps._resolve_run_id_via_wms(cfg, self._cfg()) is None
            mlist.assert_not_called()

    def test_async_site_matches_run(self):
        from stips.core import bps

        cfg = bps.BPSConfig(
            pipeline="custom",
            night="00000000",
            site="htcondor",
            output_run="Nickel/runs/b/run",
        )
        runs = [
            {"wms_id": "7.0", "run": "Nickel/runs/b/run", "payload": "", "path": ""}
        ]
        with patch("stips.core.bps_report.list_runs", return_value=runs):
            assert bps._resolve_run_id_via_wms(cfg, self._cfg()) == "7.0"

    def test_async_site_wms_unavailable(self):
        from stips.core import bps

        cfg = bps.BPSConfig(
            pipeline="custom",
            night="00000000",
            site="htcondor",
            output_run="Nickel/runs/b/run",
        )
        with patch("stips.core.bps_report.list_runs", return_value=None):
            assert bps._resolve_run_id_via_wms(cfg, self._cfg()) is None


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

    def test_underscore_variant(self):
        from stips.core import bps

        # the original substring check matched "run_id:"; keep that working
        assert bps._extract_run_id("run_id: u-42\n") == "u-42"

    def test_tolerates_log_prefix(self):
        from stips.core import bps

        out = "lsst.ctrl.bps INFO: Run Id: 99.0\nRun Name: x\n"
        assert bps._extract_run_id(out) == "99.0"

    def test_missing_returns_none(self):
        from stips.core import bps

        assert bps._extract_run_id("nothing here\n") is None


class TestSubmitLayeredRunId:
    """submit() layers banner parse -> WMS fallback and stops being silent."""

    def _cfg(self, tmp_path):
        cfg = MagicMock()
        cfg.repo = tmp_path
        return cfg

    def _result(self, stdout="", returncode=0, stderr=""):
        import subprocess

        return subprocess.CompletedProcess(
            args=["bps", "submit"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_banner_success_skips_wms(self, tmp_path):
        from stips.core import bps

        cfg = self._cfg(tmp_path)
        bcfg = bps.BPSConfig(
            pipeline="custom",
            night="00000000",
            site="htcondor",
            output_run="Nickel/runs/a/run",
        )
        with patch(
            "stips.core.bps.render_bps_config", return_value=tmp_path / "c.yaml"
        ), patch(
            "stips.core.stack.run_with_stack",
            return_value=self._result("Run Id: 55.0\nRun Name: x\n"),
        ), patch(
            "stips.core.bps._resolve_run_id_via_wms"
        ) as mres:
            res = bps.submit(bcfg, cfg)

        assert res.run_id == "55.0"
        mres.assert_not_called()

    def test_banner_fail_uses_wms_fallback(self, tmp_path):
        from stips.core import bps

        cfg = self._cfg(tmp_path)
        bcfg = bps.BPSConfig(
            pipeline="custom",
            night="00000000",
            site="htcondor",
            output_run="Nickel/runs/a/run",
        )
        with patch(
            "stips.core.bps.render_bps_config", return_value=tmp_path / "c.yaml"
        ), patch(
            "stips.core.stack.run_with_stack",
            return_value=self._result("no id in this banner\n"),
        ), patch(
            "stips.core.bps._resolve_run_id_via_wms", return_value="77.0"
        ):
            res = bps.submit(bcfg, cfg)

        assert res.run_id == "77.0"

    def test_both_fail_async_logs_error(self, tmp_path, caplog):
        import logging

        from stips.core import bps

        cfg = self._cfg(tmp_path)
        bcfg = bps.BPSConfig(
            pipeline="custom",
            night="00000000",
            site="htcondor",
            output_run="Nickel/runs/a/run",
        )
        with patch(
            "stips.core.bps.render_bps_config", return_value=tmp_path / "c.yaml"
        ), patch(
            "stips.core.stack.run_with_stack",
            return_value=self._result("no id\n"),
        ), patch(
            "stips.core.bps._resolve_run_id_via_wms", return_value=None
        ), caplog.at_level(
            logging.ERROR, logger="stips.core.bps"
        ):
            res = bps.submit(bcfg, cfg)

        assert res.run_id is None
        assert any(
            "no run id could be extracted" in r.getMessage() for r in caplog.records
        )

    def test_sync_site_missing_run_id_is_not_an_error(self, tmp_path, caplog):
        import logging

        from stips.core import bps

        cfg = self._cfg(tmp_path)
        bcfg = bps.BPSConfig(
            pipeline="custom",
            night="00000000",
            site="local",
            output_run="Nickel/runs/a/run",
        )
        # No WMS patch needed: _resolve_run_id_via_wms short-circuits for Parsl.
        with patch(
            "stips.core.bps.render_bps_config", return_value=tmp_path / "c.yaml"
        ), patch(
            "stips.core.stack.run_with_stack",
            return_value=self._result("no id (parsl ran synchronously)\n"),
        ), caplog.at_level(
            logging.ERROR, logger="stips.core.bps"
        ):
            res = bps.submit(bcfg, cfg)

        assert res.run_id is None
        assert res.success is True
        # Legitimate synchronous case: no ERROR emitted.
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
