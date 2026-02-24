"""Tests for PipetaskExecutor protocol and implementations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_tools/src"))


class TestLocalExecutor:
    def test_delegates_to_run_pipetask(self):
        from obs_nickel_data_tools.core.executor import LocalExecutor

        executor = LocalExecutor()
        mock_config = MagicMock()
        expected = subprocess.CompletedProcess(
            args=["pipetask"], returncode=0, stdout="ok"
        )

        with patch(
            "obs_nickel_data_tools.core.executor.run_pipetask", return_value=expected
        ) as mock_rp:
            result = executor.run_pipetask(
                ["qgraph", "-b", "/repo"], mock_config, capture_output=True, check=False
            )

        mock_rp.assert_called_once_with(
            ["qgraph", "-b", "/repo"], mock_config, capture_output=True, check=False
        )
        assert result.returncode == 0

    def test_passes_log_file_kwarg(self):
        from obs_nickel_data_tools.core.executor import LocalExecutor

        executor = LocalExecutor()
        mock_config = MagicMock()
        expected = subprocess.CompletedProcess(args=["pipetask"], returncode=0)
        log_path = Path("/tmp/test.log")

        with patch(
            "obs_nickel_data_tools.core.executor.run_pipetask", return_value=expected
        ) as mock_rp:
            executor.run_pipetask(
                ["run", "-b", "/repo"], mock_config, log_file=log_path, check=False
            )

        mock_rp.assert_called_once_with(
            ["run", "-b", "/repo"], mock_config, log_file=log_path, check=False
        )


class TestParsePipetaskArgs:
    def test_parses_qgraph_file(self):
        from obs_nickel_data_tools.core.executor import _parse_pipetask_args

        args = [
            "run",
            "-b",
            "/repo",
            "-g",
            "/path/to/graph.qg",
            "-j",
            "6",
            "--register-dataset-types",
        ]
        parsed = _parse_pipetask_args(args)
        assert parsed["subcommand"] == "run"
        assert parsed["repo"] == "/repo"
        assert parsed["qgraph_file"] == "/path/to/graph.qg"
        assert parsed["jobs"] == "6"

    def test_parses_qgraph_subcommand(self):
        from obs_nickel_data_tools.core.executor import _parse_pipetask_args

        args = [
            "qgraph",
            "-b",
            "/repo",
            "-p",
            "DRP.yaml#processCcd",
            "-i",
            "Nickel/raw/20230519",
            "-o",
            "Nickel/runs/20230519/processCcd/ts",
            "--output-run",
            "Nickel/runs/20230519/processCcd/ts/run",
            "--save-qgraph",
            "/path/to/out.qg",
            "-d",
            "exposure.day_obs = 20230520",
        ]
        parsed = _parse_pipetask_args(args)
        assert parsed["subcommand"] == "qgraph"
        assert parsed["pipeline"] == "DRP.yaml#processCcd"
        assert parsed["input_collections"] == "Nickel/raw/20230519"
        assert parsed["output_collection"] == "Nickel/runs/20230519/processCcd/ts"
        assert parsed["output_run"] == "Nickel/runs/20230519/processCcd/ts/run"
        assert parsed["data_query"] == "exposure.day_obs = 20230520"

    def test_handles_missing_optional_args(self):
        from obs_nickel_data_tools.core.executor import _parse_pipetask_args

        args = ["run", "-b", "/repo", "-g", "/path/to/graph.qg"]
        parsed = _parse_pipetask_args(args)
        assert parsed["subcommand"] == "run"
        assert parsed["jobs"] is None


class TestParseBpsReport:
    def test_parses_succeeded_report(self):
        from obs_nickel_data_tools.core.executor import _parse_bps_report

        report = (
            "X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED"
            "    UNREADY    READY    RUNNING\n"
            "---------  ---------  ----------  -----------  --------"
            "  ---------  -------  ---------\n"
            "summary    SUCCEEDED          12           12         0"
            "          0        0          0\n"
        )
        result = _parse_bps_report(report)
        assert result["state"] == "SUCCEEDED"
        assert result["succeeded"] == 12
        assert result["failed"] == 0
        assert result["expected"] == 12

    def test_parses_failed_report(self):
        from obs_nickel_data_tools.core.executor import _parse_bps_report

        report = (
            "X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED"
            "    UNREADY    READY    RUNNING\n"
            "---------  ---------  ----------  -----------  --------"
            "  ---------  -------  ---------\n"
            "summary    FAILED              8            5         3"
            "          0        0          0\n"
        )
        result = _parse_bps_report(report)
        assert result["state"] == "FAILED"
        assert result["succeeded"] == 5
        assert result["failed"] == 3

    def test_handles_empty_output(self):
        from obs_nickel_data_tools.core.executor import _parse_bps_report

        result = _parse_bps_report("")
        assert result["state"] == "UNKNOWN"
        assert result["succeeded"] == 0
        assert result["failed"] == 0


class TestTranslateBpsResult:
    def test_succeeded_maps_to_returncode_zero(self):
        from obs_nickel_data_tools.core.executor import (
            _translate_bps_to_completed_process,
        )

        status = {"state": "SUCCEEDED", "succeeded": 10, "failed": 0}
        result = _translate_bps_to_completed_process(status)
        assert result.returncode == 0
        assert "10" in result.stdout
        assert "0 failed" in result.stdout

    def test_failed_maps_to_returncode_one(self):
        from obs_nickel_data_tools.core.executor import (
            _translate_bps_to_completed_process,
        )

        status = {"state": "FAILED", "succeeded": 7, "failed": 3}
        result = _translate_bps_to_completed_process(status)
        assert result.returncode == 1
        assert "7" in result.stdout
        assert "3 failed" in result.stdout

    def test_unknown_maps_to_returncode_one(self):
        from obs_nickel_data_tools.core.executor import (
            _translate_bps_to_completed_process,
        )

        status = {"state": "UNKNOWN", "succeeded": 0, "failed": 0}
        result = _translate_bps_to_completed_process(status)
        assert result.returncode == 1

    def test_stdout_matches_quanta_summary_format(self):
        """Verify stdout format is parseable by pipeline.parse_quanta_summary()."""
        from obs_nickel_data_tools.core.executor import (
            _translate_bps_to_completed_process,
        )

        status = {"state": "FAILED", "succeeded": 5, "failed": 2}
        result = _translate_bps_to_completed_process(status)
        assert "5 quanta successfully" in result.stdout
        assert "2 failed" in result.stdout


class TestBPSExecutor:
    def test_qgraph_runs_locally(self):
        """QGraph generation always runs via local pipetask."""
        from obs_nickel_data_tools.core.executor import BPSExecutor

        executor = BPSExecutor(site="local")
        mock_config = MagicMock()
        expected = subprocess.CompletedProcess(
            args=["pipetask"], returncode=0, stdout=""
        )

        with patch(
            "obs_nickel_data_tools.core.executor.run_pipetask",
            return_value=expected,
        ):
            result = executor.run_pipetask(
                ["qgraph", "-b", "/repo", "-p", "DRP.yaml"],
                mock_config,
                capture_output=True,
            )

        assert result.returncode == 0

    def test_run_submits_to_bps(self):
        """Pipeline execution routes through BPS submit + poll."""
        from obs_nickel_data_tools.core.executor import BPSExecutor

        executor = BPSExecutor(site="local", poll_interval=0.01, timeout=1.0)
        mock_config = MagicMock()
        mock_config.repo = Path("/repo")
        mock_config.obs_nickel = Path("/obs_nickel")

        mock_bps_result = MagicMock()
        mock_bps_result.success = True
        mock_bps_result.run_id = "test-run-123"
        mock_bps_result.submit_dir = "/repo/bps/submit"

        succeeded_report = (
            "X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED"
            "    UNREADY    READY    RUNNING\n"
            "---------  ---------  ----------  -----------  --------"
            "  ---------  -------  ---------\n"
            "summary    SUCCEEDED           4            4         0"
            "          0        0          0\n"
        )
        mock_status = {"success": True, "output": succeeded_report}

        with patch("obs_nickel_data_tools.core.executor.bps") as mock_bps_mod:
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.status.return_value = mock_status
            mock_bps_mod.BPSConfig = MagicMock()
            mock_bps_mod.render_bps_config = MagicMock(
                return_value=Path("/rendered.yaml")
            )

            result = executor.run_pipetask(
                ["run", "-b", "/repo", "-g", "/path/to/graph.qg", "-j", "4"],
                mock_config,
                capture_output=True,
                check=False,
            )

        assert result.returncode == 0
        assert "4 quanta successfully" in result.stdout

    def test_run_returns_failure_on_bps_submit_error(self):
        """If BPS submit fails, return non-zero CompletedProcess."""
        from obs_nickel_data_tools.core.executor import BPSExecutor

        executor = BPSExecutor(site="local")
        mock_config = MagicMock()
        mock_config.repo = Path("/repo")
        mock_config.obs_nickel = Path("/obs_nickel")

        mock_bps_result = MagicMock()
        mock_bps_result.success = False
        mock_bps_result.error = "Config render failed"

        with patch("obs_nickel_data_tools.core.executor.bps") as mock_bps_mod:
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.BPSConfig = MagicMock()
            mock_bps_mod.render_bps_config = MagicMock(
                return_value=Path("/rendered.yaml")
            )

            result = executor.run_pipetask(
                ["run", "-b", "/repo", "-g", "/graph.qg"],
                mock_config,
                check=False,
            )

        assert result.returncode == 1

    def test_timeout_returns_failure(self):
        """If polling exceeds timeout, return failure."""
        from obs_nickel_data_tools.core.executor import BPSExecutor

        executor = BPSExecutor(site="local", poll_interval=0.01, timeout=0.05)
        mock_config = MagicMock()
        mock_config.repo = Path("/repo")
        mock_config.obs_nickel = Path("/obs_nickel")

        mock_bps_result = MagicMock()
        mock_bps_result.success = True
        mock_bps_result.run_id = "stuck-run"
        mock_bps_result.submit_dir = "/submit"

        running_report = (
            "X_REPORT    STATE    EXPECTED    SUCCEEDED    FAILED"
            "    UNREADY    READY    RUNNING\n"
            "summary    RUNNING          4            0         0"
            "          0        2          2\n"
        )
        mock_status = {"success": True, "output": running_report}

        with patch("obs_nickel_data_tools.core.executor.bps") as mock_bps_mod:
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.status.return_value = mock_status
            mock_bps_mod.BPSConfig = MagicMock()
            mock_bps_mod.render_bps_config = MagicMock(
                return_value=Path("/rendered.yaml")
            )

            result = executor.run_pipetask(
                ["run", "-b", "/repo", "-g", "/graph.qg"],
                mock_config,
                check=False,
            )

        assert result.returncode == 1
        assert (
            "timeout" in result.stderr.lower() or "timed out" in result.stderr.lower()
        )
