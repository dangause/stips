"""Tests for PipetaskExecutor protocol and implementations."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class TestLocalExecutor:
    def test_delegates_to_run_pipetask(self):
        from stips.core.executor import LocalExecutor

        executor = LocalExecutor()
        mock_config = MagicMock()
        expected = subprocess.CompletedProcess(
            args=["pipetask"], returncode=0, stdout="ok"
        )

        with patch(
            "stips.core.executor.run_pipetask", return_value=expected
        ) as mock_rp:
            result = executor.run_pipetask(
                ["qgraph", "-b", "/repo"], mock_config, capture_output=True, check=False
            )

        mock_rp.assert_called_once_with(
            ["qgraph", "-b", "/repo"], mock_config, capture_output=True, check=False
        )
        assert result.returncode == 0

    def test_passes_log_file_kwarg(self):
        from stips.core.executor import LocalExecutor

        executor = LocalExecutor()
        mock_config = MagicMock()
        expected = subprocess.CompletedProcess(args=["pipetask"], returncode=0)
        log_path = Path("/tmp/test.log")

        with patch(
            "stips.core.executor.run_pipetask", return_value=expected
        ) as mock_rp:
            executor.run_pipetask(
                ["run", "-b", "/repo"], mock_config, log_file=log_path, check=False
            )

        mock_rp.assert_called_once_with(
            ["run", "-b", "/repo"], mock_config, log_file=log_path, check=False
        )

    def test_local_does_not_inject_datastore_records(self):
        # LocalExecutor.needs_datastore_records is False -> flag never added
        from stips.core.executor import LocalExecutor

        with patch(
            "stips.core.executor.run_pipetask",
            return_value=subprocess.CompletedProcess(args=["pipetask"], returncode=0),
        ) as mrp:
            LocalExecutor().run_pipetask(
                ["qgraph", "-b", "/repo"], MagicMock(), check=False
            )
        passed_args = mrp.call_args[0][0]
        assert "--qgraph-datastore-records" not in passed_args


class TestWithDatastoreRecords:
    def test_appends_for_qgraph_when_needed(self):
        from stips.core.executor import _with_datastore_records

        out = _with_datastore_records(["qgraph", "-b", "/r"], True)
        assert out == ["qgraph", "-b", "/r", "--qgraph-datastore-records"]

    def test_noop_when_not_needed(self):
        from stips.core.executor import _with_datastore_records

        assert _with_datastore_records(["qgraph", "-b"], False) == ["qgraph", "-b"]

    def test_noop_for_non_qgraph(self):
        from stips.core.executor import _with_datastore_records

        assert _with_datastore_records(["run", "-g", "x"], True) == ["run", "-g", "x"]

    def test_idempotent(self):
        from stips.core.executor import _with_datastore_records

        args = ["qgraph", "--qgraph-datastore-records"]
        assert _with_datastore_records(args, True) == args

    def test_bps_injects_on_qgraph(self):
        from stips.core.executor import BPSExecutor

        with patch(
            "stips.core.executor.run_pipetask",
            return_value=subprocess.CompletedProcess(args=["pipetask"], returncode=0),
        ) as mrp:
            # qgraph subcommand runs locally even under BPS; flag must be injected
            BPSExecutor().run_pipetask(["qgraph", "-b", "/r"], MagicMock(), check=False)
        assert "--qgraph-datastore-records" in mrp.call_args[0][0]


class TestParsePipetaskArgs:
    def test_parses_qgraph_file(self):
        from stips.core.executor import _parse_pipetask_args

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
        from stips.core.executor import _parse_pipetask_args

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
        from stips.core.executor import _parse_pipetask_args

        args = ["run", "-b", "/repo", "-g", "/path/to/graph.qg"]
        parsed = _parse_pipetask_args(args)
        assert parsed["subcommand"] == "run"
        assert parsed["jobs"] is None


class TestParseBpsReport:
    def test_parses_succeeded_report(self):
        from stips.core.executor import _parse_bps_report

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
        from stips.core.executor import _parse_bps_report

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
        from stips.core.executor import _parse_bps_report

        result = _parse_bps_report("")
        assert result["state"] == "UNKNOWN"
        assert result["succeeded"] == 0
        assert result["failed"] == 0


class TestTranslateBpsResult:
    def test_succeeded_maps_to_returncode_zero(self):
        from stips.core.executor import (
            _translate_bps_to_completed_process,
        )

        status = {"state": "SUCCEEDED", "succeeded": 10, "failed": 0}
        result = _translate_bps_to_completed_process(status)
        assert result.returncode == 0

    def test_failed_maps_to_returncode_one(self):
        from stips.core.executor import (
            _translate_bps_to_completed_process,
        )

        status = {"state": "FAILED", "succeeded": 7, "failed": 3}
        result = _translate_bps_to_completed_process(status)
        assert result.returncode == 1

    def test_unknown_maps_to_returncode_one(self):
        from stips.core.executor import (
            _translate_bps_to_completed_process,
        )

        status = {"state": "UNKNOWN", "succeeded": 0, "failed": 0}
        result = _translate_bps_to_completed_process(status)
        assert result.returncode == 1

    def test_counts_written_to_summary_file_not_fabricated_stdout(self, tmp_path):
        """F-028: counts flow through the structured --summary channel.

        science.py reads quanta counts via quanta_report.parse_summary_file, not
        by regex-parsing stdout. The translated result must populate that file,
        and its stdout must NOT match the old fabricated pattern that the real
        quanta regex never accepted.
        """
        from stips.core import quanta_report
        from stips.core.executor import _translate_bps_to_completed_process
        from stips.core.pipeline import parse_quanta_summary

        summary_file = tmp_path / "science.summary.json"
        status = {"state": "FAILED", "succeeded": 5, "failed": 2}
        result = _translate_bps_to_completed_process(
            status, summary_file=str(summary_file)
        )

        # Structured channel carries the real counts.
        assert quanta_report.parse_summary_file(summary_file) == (5, 2)
        # No dead-link fabricated stdout: the old "out of total" string is gone,
        # and the human-readable regex finds nothing to parse.
        assert "out of total" not in result.stdout
        assert parse_quanta_summary(result.stdout) == (0, 0)


class TestBPSExecutor:
    def test_qgraph_runs_locally(self):
        """QGraph generation always runs via local pipetask."""
        from stips.core.executor import BPSExecutor

        executor = BPSExecutor(site="local")
        mock_config = MagicMock()
        expected = subprocess.CompletedProcess(
            args=["pipetask"], returncode=0, stdout=""
        )

        with patch(
            "stips.core.executor.run_pipetask",
            return_value=expected,
        ):
            result = executor.run_pipetask(
                ["qgraph", "-b", "/repo", "-p", "DRP.yaml"],
                mock_config,
                capture_output=True,
            )

        assert result.returncode == 0

    def test_run_submits_to_bps(self, tmp_path):
        """Pipeline execution routes through BPS submit + poll.

        The async poll resolves SUCCEEDED and the quanta counts are conveyed via
        the structured --summary file (F-028), not a fabricated stdout string.
        """
        from stips.core import quanta_report
        from stips.core.executor import BPSExecutor

        executor = BPSExecutor(site="htcondor", poll_interval=0.01, timeout=1.0)
        mock_config = MagicMock()
        mock_config.repo = Path("/repo")
        mock_config.instrument_dir = Path("/obs_nickel")

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

        summary_file = tmp_path / "science.summary.json"

        with patch("stips.core.executor.bps") as mock_bps_mod, patch(
            "stips.core.executor.bps_report"
        ) as mock_report_mod:
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.status.return_value = mock_status
            mock_bps_mod.is_synchronous_site.return_value = False
            mock_bps_mod.BPSConfig = MagicMock()
            mock_bps_mod.render_bps_config = MagicMock(
                return_value=Path("/rendered.yaml")
            )
            # Force the text-table fallback path (structured API "unavailable").
            mock_report_mod.summary_for_run.return_value = None

            result = executor.run_pipetask(
                [
                    "run",
                    "-b",
                    "/repo",
                    "-g",
                    "/path/to/graph.qg",
                    "-j",
                    "4",
                    "--summary",
                    str(summary_file),
                ],
                mock_config,
                capture_output=True,
                check=False,
            )

        assert result.returncode == 0
        assert quanta_report.parse_summary_file(summary_file) == (4, 0)

    def test_sync_site_no_run_id_is_legitimate(self, tmp_path, caplog):
        """Parsl (synchronous) site with no run id: expected, not degraded.

        Verifies the collection-probe path and that no degraded WARNING naming
        WMS polling is emitted, and that counts flow through the --summary file.
        """
        import logging

        from stips.core import quanta_report
        from stips.core.executor import BPSExecutor

        executor = BPSExecutor(site="local", poll_interval=0.01, timeout=1.0)
        mock_config = MagicMock()
        summary_file = tmp_path / "s.summary.json"

        mock_bps_result = MagicMock()
        mock_bps_result.success = True
        mock_bps_result.run_id = None
        mock_bps_result.stderr = ""

        with patch("stips.core.executor.bps") as mock_bps_mod, patch(
            "stips.core.executor._check_output_collection", return_value=True
        ), caplog.at_level(logging.WARNING, logger="stips.core.executor"):
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.is_synchronous_site.return_value = True
            mock_bps_mod.BPSConfig = MagicMock()

            result = executor.run_pipetask(
                [
                    "run",
                    "-b",
                    "/repo",
                    "-g",
                    "/g.qg",
                    "--output-run",
                    "r/run",
                    "--summary",
                    str(summary_file),
                ],
                mock_config,
                check=False,
            )

        assert result.returncode == 0
        assert quanta_report.parse_summary_file(summary_file) == (1, 0)
        # No "cannot poll WMS" degraded warning on the legitimate sync path.
        assert not any(
            "cannot poll wms" in r.getMessage().lower() for r in caplog.records
        )

    def test_async_site_no_run_id_is_degraded(self, tmp_path, caplog):
        """HTCondor (async) site with no run id: loud degraded mode, not silent.

        This is F-015: previously misclassified as a finished synchronous
        backend. Now it warns that WMS polling is unavailable and names the
        output-collection-probe fallback.
        """
        import logging

        from stips.core.executor import BPSExecutor

        executor = BPSExecutor(site="htcondor", poll_interval=0.01, timeout=1.0)
        mock_config = MagicMock()

        mock_bps_result = MagicMock()
        mock_bps_result.success = True
        mock_bps_result.run_id = None
        mock_bps_result.stderr = ""

        with patch("stips.core.executor.bps") as mock_bps_mod, patch(
            "stips.core.executor._check_output_collection", return_value=False
        ), caplog.at_level(logging.WARNING, logger="stips.core.executor"):
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.is_synchronous_site.return_value = False
            mock_bps_mod.BPSConfig = MagicMock()

            result = executor.run_pipetask(
                ["run", "-b", "/repo", "-g", "/g.qg", "--output-run", "r/run"],
                mock_config,
                check=False,
            )

        assert result.returncode == 1
        # Loud, explicit about the consequence.
        assert any("cannot poll wms" in r.getMessage().lower() for r in caplog.records)

    def test_run_returns_failure_on_bps_submit_error(self):
        """If BPS submit fails, return non-zero CompletedProcess."""
        from stips.core.executor import BPSExecutor

        executor = BPSExecutor(site="local")
        mock_config = MagicMock()
        mock_config.repo = Path("/repo")
        mock_config.instrument_dir = Path("/obs_nickel")

        mock_bps_result = MagicMock()
        mock_bps_result.success = False
        mock_bps_result.error = "Config render failed"

        with patch("stips.core.executor.bps") as mock_bps_mod:
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
        from stips.core.executor import BPSExecutor

        executor = BPSExecutor(site="local", poll_interval=0.01, timeout=0.05)
        mock_config = MagicMock()
        mock_config.repo = Path("/repo")
        mock_config.instrument_dir = Path("/obs_nickel")

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

        with patch("stips.core.executor.bps") as mock_bps_mod, patch(
            "stips.core.executor.bps_report"
        ) as mock_report_mod:
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.status.return_value = mock_status
            mock_bps_mod.BPSConfig = MagicMock()
            mock_bps_mod.render_bps_config = MagicMock(
                return_value=Path("/rendered.yaml")
            )
            mock_report_mod.summary_for_run.return_value = None

            result = executor.run_pipetask(
                ["run", "-b", "/repo", "-g", "/graph.qg"],
                mock_config,
                check=False,
            )

        assert result.returncode == 1
        assert (
            "timeout" in result.stderr.lower() or "timed out" in result.stderr.lower()
        )


class TestExecutorWiring:
    """Verify stage modules accept and use executor parameter."""

    def test_calibs_accepts_executor(self):
        import inspect

        from stips.core import calibs

        sig = inspect.signature(calibs.run)
        assert "executor" in sig.parameters

    def test_science_accepts_executor(self):
        import inspect

        from stips.core import science

        sig = inspect.signature(science.run)
        assert "executor" in sig.parameters

    def test_dia_accepts_executor(self):
        import inspect

        from stips.core import dia

        sig = inspect.signature(dia.run)
        assert "executor" in sig.parameters

    def test_fphot_accepts_executor(self):
        import inspect

        from stips.core import fphot

        sig = inspect.signature(fphot.run)
        assert "executor" in sig.parameters


class TestDispatchConcurrent:
    def test_runs_all_items(self):
        from stips.core.run import _dispatch_concurrent

        results = _dispatch_concurrent(
            lambda x: x * 2,
            [1, 2, 3, 4],
            max_workers=2,
        )
        assert results == {1: 2, 2: 4, 3: 6, 4: 8}

    def test_handles_exceptions(self):
        from stips.core.run import _dispatch_concurrent

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
        from stips.core.run import _dispatch_concurrent

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
        from stips.core.run import _dispatch_concurrent

        order = []

        def tracking_fn(x):
            order.append(x)
            return x

        _dispatch_concurrent(tracking_fn, [1, 2, 3], max_workers=1)
        assert len(order) == 3


class TestIntegration:
    def test_executor_protocol_compliance(self):
        """Both executors satisfy the PipetaskExecutor protocol."""
        from stips.core.executor import (
            BPSExecutor,
            LocalExecutor,
            PipetaskExecutor,
        )

        assert isinstance(LocalExecutor(), PipetaskExecutor)
        assert isinstance(BPSExecutor(site="local"), PipetaskExecutor)

    def test_local_executor_is_default(self):
        """When no executor param, stage modules default to None."""
        import inspect

        from stips.core import calibs, dia, fphot, science

        for mod in [calibs, science, dia, fphot]:
            sig = inspect.signature(mod.run)
            param = sig.parameters["executor"]
            assert (
                param.default is None
            ), f"{mod.__name__}.run executor default should be None"

    def test_create_executor_roundtrip(self):
        """RunConfig -> executor -> can be called."""
        from stips.core.executor import BPSExecutor, LocalExecutor
        from stips.core.run import RunConfig, _create_executor

        # Local
        local_cfg = RunConfig(object_name="test", ra=100, dec=10, bands=["r"])
        local_exec = _create_executor(local_cfg)
        assert isinstance(local_exec, LocalExecutor)

        # BPS
        bps_cfg = RunConfig(
            object_name="test",
            ra=100,
            dec=10,
            bands=["r"],
            execution="bps",
            site="slurm",
        )
        bps_exec = _create_executor(bps_cfg)
        assert isinstance(bps_exec, BPSExecutor)
        assert bps_exec.site == "slurm"
