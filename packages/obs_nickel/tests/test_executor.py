"""Tests for PipetaskExecutor protocol and implementations."""

from __future__ import annotations

import subprocess
import sys
import time
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

    def test_submit_passes_qgraph_file_to_bps_config(self):
        """BPSExecutor passes qgraph_file from pipetask args to BPSConfig."""
        from obs_nickel_data_tools.core.executor import BPSExecutor

        executor = BPSExecutor(site="local", poll_interval=0.01, timeout=1.0)
        mock_config = MagicMock()
        mock_config.repo = Path("/repo")
        mock_config.obs_nickel = Path("/obs_nickel")

        mock_bps_result = MagicMock()
        mock_bps_result.success = True
        mock_bps_result.run_id = "test-run-456"
        mock_bps_result.submit_dir = "/repo/bps/submit"

        succeeded_report = (
            "X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED"
            "    UNREADY    READY    RUNNING\n"
            "summary    SUCCEEDED           2            2         0"
            "          0        0          0\n"
        )
        mock_status = {"success": True, "output": succeeded_report}

        with patch("obs_nickel_data_tools.core.executor.bps") as mock_bps_mod:
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.status.return_value = mock_status
            mock_bps_mod.BPSConfig = MagicMock()

            executor.run_pipetask(
                ["run", "-b", "/repo", "-g", "/path/to/my_graph.qg", "-j", "4"],
                mock_config,
                check=False,
            )

            # Verify BPSConfig was created with qgraph_file
            call_kwargs = mock_bps_mod.BPSConfig.call_args
            assert call_kwargs is not None
            assert call_kwargs.kwargs.get("qgraph_file") == "/path/to/my_graph.qg"


class TestExecutorWiring:
    """Verify stage modules accept and use executor parameter."""

    def test_calibs_accepts_executor(self):
        import inspect

        from obs_nickel_data_tools.core import calibs

        sig = inspect.signature(calibs.run)
        assert "executor" in sig.parameters

    def test_science_accepts_executor(self):
        import inspect

        from obs_nickel_data_tools.core import science

        sig = inspect.signature(science.run)
        assert "executor" in sig.parameters

    def test_dia_accepts_executor(self):
        import inspect

        from obs_nickel_data_tools.core import dia

        sig = inspect.signature(dia.run)
        assert "executor" in sig.parameters

    def test_fphot_accepts_executor(self):
        import inspect

        from obs_nickel_data_tools.core import fphot

        sig = inspect.signature(fphot.run)
        assert "executor" in sig.parameters


class TestDispatchConcurrent:
    def test_runs_all_items(self):
        from obs_nickel_data_tools.core.run import _dispatch_concurrent

        results = _dispatch_concurrent(
            lambda x: x * 2,
            [1, 2, 3, 4],
            max_workers=2,
        )
        assert results == {1: 2, 2: 4, 3: 6, 4: 8}

    def test_handles_exceptions(self):
        from obs_nickel_data_tools.core.run import _dispatch_concurrent

        def failing_fn(x):
            if x == 2:
                raise ValueError("boom")
            return x * 10

        results = _dispatch_concurrent(failing_fn, [1, 2, 3], max_workers=2)
        assert results[1] == 10
        assert results[2] is None  # Failed items return None
        assert results[3] == 30

    def test_runs_concurrently(self):
        """Items actually run in parallel, not sequentially."""
        from obs_nickel_data_tools.core.run import _dispatch_concurrent

        def slow_fn(x):
            time.sleep(0.1)
            return x

        start = time.monotonic()
        results = _dispatch_concurrent(slow_fn, [1, 2, 3, 4], max_workers=4)
        elapsed = time.monotonic() - start

        assert len(results) == 4
        # 4 items at 0.1s each with 4 workers should take ~0.1s, not 0.4s
        assert elapsed < 0.3

    def test_single_worker_runs_sequentially(self):
        from obs_nickel_data_tools.core.run import _dispatch_concurrent

        order = []

        def tracking_fn(x):
            order.append(x)
            return x

        _dispatch_concurrent(tracking_fn, [1, 2, 3], max_workers=1)
        assert len(order) == 3


class TestIntegration:
    def test_executor_protocol_compliance(self):
        """Both executors satisfy the PipetaskExecutor protocol."""
        from obs_nickel_data_tools.core.executor import (
            BPSExecutor,
            LocalExecutor,
            PipetaskExecutor,
        )

        assert isinstance(LocalExecutor(), PipetaskExecutor)
        assert isinstance(BPSExecutor(site="local"), PipetaskExecutor)

    def test_local_executor_is_default(self):
        """When no executor param, stage modules default to None."""
        import inspect

        from obs_nickel_data_tools.core import calibs, dia, fphot, science

        for mod in [calibs, science, dia, fphot]:
            sig = inspect.signature(mod.run)
            param = sig.parameters["executor"]
            assert (
                param.default is None
            ), f"{mod.__name__}.run executor default should be None"

    def test_create_executor_roundtrip(self):
        """RunConfig -> executor -> can be called."""
        from obs_nickel_data_tools.core.executor import BPSExecutor, LocalExecutor
        from obs_nickel_data_tools.core.run import RunConfig, _create_executor

        # Local
        local_cfg = RunConfig(object_name="test", ra=100, dec=10, bands=["r"])
        local_exec = _create_executor(local_cfg)
        assert isinstance(local_exec, LocalExecutor)

        # BPS (mock lsst.ctrl.bps since it's not installed in dev env)
        bps_cfg = RunConfig(
            object_name="test",
            ra=100,
            dec=10,
            bands=["r"],
            execution="bps",
            site="slurm",
        )

        import builtins

        original_import = builtins.__import__

        def allow_lsst_import(name, *args, **kwargs):
            if name in ("lsst.ctrl.bps", "lsst.ctrl.bps.parsl"):
                return MagicMock()
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=allow_lsst_import):
            bps_exec = _create_executor(bps_cfg)
        assert isinstance(bps_exec, BPSExecutor)
        assert bps_exec.site == "slurm"


class TestCtrlBpsAvailabilityCheck:
    def test_bps_executor_fails_fast_when_ctrl_bps_missing(self):
        """_create_executor raises ImportError when ctrl_bps is not installed."""
        from obs_nickel_data_tools.core.run import RunConfig, _create_executor

        bps_cfg = RunConfig(
            object_name="test",
            ra=100,
            dec=10,
            bands=["r"],
            execution="bps",
            site="slurm",
        )

        # Mock the ctrl_bps import to fail
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "lsst.ctrl.bps":
                raise ImportError("No module named 'lsst.ctrl.bps'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            try:
                _create_executor(bps_cfg)
                assert False, "Should have raised ImportError"
            except ImportError as e:
                assert "ctrl_bps" in str(e).lower() or "lsst" in str(e).lower()

    def test_bps_local_fails_fast_when_ctrl_bps_parsl_missing(self):
        """_create_executor raises ImportError when ctrl_bps_parsl missing for local site."""
        from obs_nickel_data_tools.core.run import RunConfig, _create_executor

        bps_cfg = RunConfig(
            object_name="test",
            ra=100,
            dec=10,
            bands=["r"],
            execution="bps",
            site="local",
        )

        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "lsst.ctrl.bps.parsl":
                raise ImportError("No module named 'lsst.ctrl.bps.parsl'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            try:
                _create_executor(bps_cfg)
                assert False, "Should have raised ImportError"
            except ImportError as e:
                assert "parsl" in str(e).lower()

    def test_local_executor_skips_ctrl_bps_check(self):
        """_create_executor with execution='local' never checks for ctrl_bps."""
        from obs_nickel_data_tools.core.executor import LocalExecutor
        from obs_nickel_data_tools.core.run import RunConfig, _create_executor

        local_cfg = RunConfig(
            object_name="test",
            ra=100,
            dec=10,
            bands=["r"],
            execution="local",
        )
        executor = _create_executor(local_cfg)
        assert isinstance(executor, LocalExecutor)
