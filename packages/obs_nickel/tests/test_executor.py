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
