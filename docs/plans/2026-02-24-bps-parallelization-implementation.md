# BPS Parallelization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate BPS execution and cross-night parallelism into the `nickel run` orchestrator via an executor abstraction layer.

**Architecture:** A `PipetaskExecutor` protocol replaces direct `run_pipetask()` calls in stage modules. `LocalExecutor` preserves current behavior; `BPSExecutor` routes pipeline execution through BPS with submit/poll. The orchestrator gains `_dispatch_concurrent()` for cross-night parallelism via `ThreadPoolExecutor`.

**Tech Stack:** Python 3.11+, `concurrent.futures`, existing `core/bps.py` module, `core/stack.py`

**Design doc:** `docs/plans/2026-02-24-bps-parallelization-design.md`

---

### Task 1: PipetaskExecutor Protocol and LocalExecutor

**Files:**
- Create: `packages/data_tools/src/obs_nickel_data_tools/core/executor.py`
- Test: `packages/obs_nickel/tests/test_executor.py`

**Step 1: Write the failing test**

```python
# packages/obs_nickel/tests/test_executor.py
"""Tests for PipetaskExecutor protocol and implementations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_tools/src"))


class TestLocalExecutor:
    def test_delegates_to_run_pipetask(self):
        from obs_nickel_data_tools.core.executor import LocalExecutor

        executor = LocalExecutor()
        mock_config = MagicMock()
        expected = subprocess.CompletedProcess(args=["pipetask"], returncode=0, stdout="ok")

        with patch("obs_nickel_data_tools.core.executor.run_pipetask", return_value=expected) as mock_rp:
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

        with patch("obs_nickel_data_tools.core.executor.run_pipetask", return_value=expected) as mock_rp:
            executor.run_pipetask(
                ["run", "-b", "/repo"], mock_config, log_file=log_path, check=False
            )

        mock_rp.assert_called_once_with(
            ["run", "-b", "/repo"], mock_config, log_file=log_path, check=False
        )
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'obs_nickel_data_tools.core.executor'`

**Step 3: Write minimal implementation**

```python
# packages/data_tools/src/obs_nickel_data_tools/core/executor.py
"""Execution backends for pipetask commands.

Provides an abstraction over how pipetask commands are executed, allowing
the same stage module code to run via direct subprocess (LocalExecutor)
or via BPS batch submission (BPSExecutor).

Stage modules call executor.run_pipetask() instead of stack.run_pipetask(),
preserving all existing stage-level logic (fallbacks, validation, etc.).
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from obs_nickel_data_tools.core.stack import run_pipetask

if TYPE_CHECKING:
    from pathlib import Path

    from obs_nickel_data_tools.core.config import Config


@runtime_checkable
class PipetaskExecutor(Protocol):
    """Protocol for pipetask execution backends.

    Stage modules use this instead of calling run_pipetask() directly.
    The executor handles how the command is actually executed (local
    subprocess vs BPS submission).
    """

    def run_pipetask(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess: ...


class LocalExecutor:
    """Execute pipetask commands via direct subprocess (current behavior).

    This is a passthrough to stack.run_pipetask() with zero behavior change.
    """

    def run_pipetask(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        return run_pipetask(args, config, **kwargs)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/executor.py packages/obs_nickel/tests/test_executor.py
git commit -m "feat: add PipetaskExecutor protocol and LocalExecutor"
```

---

### Task 2: BPS Arg Parser

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/executor.py`
- Test: `packages/obs_nickel/tests/test_executor.py`

**Step 1: Write the failing tests**

Add to `test_executor.py`:

```python
class TestParsePipetaskArgs:
    def test_parses_qgraph_file(self):
        from obs_nickel_data_tools.core.executor import _parse_pipetask_args

        args = ["run", "-b", "/repo", "-g", "/path/to/graph.qg", "-j", "6",
                "--register-dataset-types"]
        parsed = _parse_pipetask_args(args)
        assert parsed["subcommand"] == "run"
        assert parsed["repo"] == "/repo"
        assert parsed["qgraph_file"] == "/path/to/graph.qg"
        assert parsed["jobs"] == "6"

    def test_parses_qgraph_subcommand(self):
        from obs_nickel_data_tools.core.executor import _parse_pipetask_args

        args = ["qgraph", "-b", "/repo", "-p", "DRP.yaml#processCcd",
                "-i", "Nickel/raw/20230519", "-o", "Nickel/runs/20230519/processCcd/ts",
                "--output-run", "Nickel/runs/20230519/processCcd/ts/run",
                "--save-qgraph", "/path/to/out.qg",
                "-d", "exposure.day_obs = 20230520"]
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestParsePipetaskArgs -v`
Expected: FAIL — `ImportError: cannot import name '_parse_pipetask_args'`

**Step 3: Write minimal implementation**

Add to `executor.py`:

```python
def _parse_pipetask_args(args: list[str]) -> dict:
    """Parse pipetask command-line args into a structured dict.

    Extracts key fields from pipetask qgraph/run argument lists so the
    BPSExecutor can map them to BPS configuration parameters.

    Args:
        args: Arguments as passed to pipetask (e.g., ["run", "-b", "/repo", ...])

    Returns:
        Dict with keys: subcommand, repo, qgraph_file, pipeline,
        input_collections, output_collection, output_run, data_query, jobs
    """
    parsed: dict = {
        "subcommand": args[0] if args else None,
        "repo": None,
        "qgraph_file": None,
        "pipeline": None,
        "input_collections": None,
        "output_collection": None,
        "output_run": None,
        "data_query": None,
        "jobs": None,
    }

    # Map short/long flags to their keys
    flag_map = {
        "-b": "repo",
        "-g": "qgraph_file",
        "-p": "pipeline",
        "-i": "input_collections",
        "-o": "output_collection",
        "-d": "data_query",
        "-j": "jobs",
        "--output-run": "output_run",
        "--save-qgraph": "save_qgraph",
    }

    i = 1  # Skip subcommand
    while i < len(args):
        if args[i] in flag_map and i + 1 < len(args):
            parsed[flag_map[args[i]]] = args[i + 1]
            i += 2
        else:
            i += 1

    return parsed
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestParsePipetaskArgs -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/executor.py packages/obs_nickel/tests/test_executor.py
git commit -m "feat: add pipetask arg parser for BPS executor"
```

---

### Task 3: BPS Report Parser

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/executor.py`
- Test: `packages/obs_nickel/tests/test_executor.py`

**Step 1: Write the failing tests**

Add to `test_executor.py`:

```python
class TestParseBpsReport:
    def test_parses_succeeded_report(self):
        from obs_nickel_data_tools.core.executor import _parse_bps_report

        report = (
            "X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED    UNREADY    READY    RUNNING\n"
            "---------  ---------  ----------  -----------  --------  ---------  -------  ---------\n"
            "summary    SUCCEEDED          12           12         0          0        0          0\n"
        )
        result = _parse_bps_report(report)
        assert result["state"] == "SUCCEEDED"
        assert result["succeeded"] == 12
        assert result["failed"] == 0
        assert result["expected"] == 12

    def test_parses_failed_report(self):
        from obs_nickel_data_tools.core.executor import _parse_bps_report

        report = (
            "X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED    UNREADY    READY    RUNNING\n"
            "---------  ---------  ----------  -----------  --------  ---------  -------  ---------\n"
            "summary    FAILED              8            5         3          0        0          0\n"
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestParseBpsReport -v`
Expected: FAIL — `ImportError: cannot import name '_parse_bps_report'`

**Step 3: Write minimal implementation**

Add to `executor.py`:

```python
def _parse_bps_report(raw_output: str) -> dict:
    """Parse bps report tabular output into structured data.

    BPS report outputs a table with columns:
        X_REPORT  STATE  EXPECTED  SUCCEEDED  FAILED  UNREADY  READY  RUNNING

    We extract the 'summary' row.

    Args:
        raw_output: Raw text output from `bps report <run_id>`

    Returns:
        Dict with state, expected, succeeded, failed, unready, ready, running
    """
    for line in raw_output.splitlines():
        stripped = line.strip()
        if stripped.startswith("summary"):
            parts = stripped.split()
            if len(parts) >= 8:
                return {
                    "state": parts[1],
                    "expected": int(parts[2]),
                    "succeeded": int(parts[3]),
                    "failed": int(parts[4]),
                    "unready": int(parts[5]),
                    "ready": int(parts[6]),
                    "running": int(parts[7]),
                }
    return {"state": "UNKNOWN", "expected": 0, "succeeded": 0, "failed": 0,
            "unready": 0, "ready": 0, "running": 0}
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestParseBpsReport -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/executor.py packages/obs_nickel/tests/test_executor.py
git commit -m "feat: add BPS report parser"
```

---

### Task 4: BPS Result Translator

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/executor.py`
- Test: `packages/obs_nickel/tests/test_executor.py`

**Step 1: Write the failing tests**

Add to `test_executor.py`:

```python
class TestTranslateBpsResult:
    def test_succeeded_maps_to_returncode_zero(self):
        from obs_nickel_data_tools.core.executor import _translate_bps_to_completed_process

        status = {"state": "SUCCEEDED", "succeeded": 10, "failed": 0}
        result = _translate_bps_to_completed_process(status)
        assert result.returncode == 0
        assert "10" in result.stdout
        assert "0 failed" in result.stdout

    def test_failed_maps_to_returncode_one(self):
        from obs_nickel_data_tools.core.executor import _translate_bps_to_completed_process

        status = {"state": "FAILED", "succeeded": 7, "failed": 3}
        result = _translate_bps_to_completed_process(status)
        assert result.returncode == 1
        assert "7" in result.stdout
        assert "3 failed" in result.stdout

    def test_unknown_maps_to_returncode_one(self):
        from obs_nickel_data_tools.core.executor import _translate_bps_to_completed_process

        status = {"state": "UNKNOWN", "succeeded": 0, "failed": 0}
        result = _translate_bps_to_completed_process(status)
        assert result.returncode == 1

    def test_stdout_matches_quanta_summary_format(self):
        """Verify stdout format is parseable by pipeline.parse_quanta_summary()."""
        from obs_nickel_data_tools.core.executor import _translate_bps_to_completed_process

        status = {"state": "FAILED", "succeeded": 5, "failed": 2}
        result = _translate_bps_to_completed_process(status)
        # The format should contain "N quanta successfully" and "M failed"
        assert "5 quanta successfully" in result.stdout
        assert "2 failed" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestTranslateBpsResult -v`
Expected: FAIL — `ImportError: cannot import name '_translate_bps_to_completed_process'`

**Step 3: Write minimal implementation**

Add to `executor.py`:

```python
def _translate_bps_to_completed_process(bps_status: dict) -> subprocess.CompletedProcess:
    """Translate BPS status into a CompletedProcess.

    Stage modules parse CompletedProcess.stdout with _parse_quanta_summary()
    which looks for "Executed N quanta successfully, M failed out of total T".
    We format our stdout to match that pattern.

    Args:
        bps_status: Dict with state, succeeded, failed keys from _parse_bps_report()

    Returns:
        CompletedProcess with returncode and formatted stdout
    """
    state = bps_status.get("state", "UNKNOWN")
    quanta_ok = bps_status.get("succeeded", 0)
    quanta_fail = bps_status.get("failed", 0)
    total = quanta_ok + quanta_fail

    returncode = 0 if state == "SUCCEEDED" else 1

    stdout = (
        f"Executed {quanta_ok} quanta successfully, "
        f"{quanta_fail} failed out of total {total}"
    )

    return subprocess.CompletedProcess(
        args=["bps", "submit"],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestTranslateBpsResult -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/executor.py packages/obs_nickel/tests/test_executor.py
git commit -m "feat: add BPS result translator for stage module compatibility"
```

---

### Task 5: BPSExecutor Submit/Poll Lifecycle

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/executor.py`
- Test: `packages/obs_nickel/tests/test_executor.py`

**Step 1: Write the failing tests**

Add to `test_executor.py`:

```python
class TestBPSExecutor:
    def test_qgraph_runs_locally(self):
        """QGraph generation always runs via local pipetask."""
        from obs_nickel_data_tools.core.executor import BPSExecutor

        executor = BPSExecutor(site="local")
        mock_config = MagicMock()
        expected = subprocess.CompletedProcess(args=["pipetask"], returncode=0, stdout="")

        with patch("obs_nickel_data_tools.core.executor.run_pipetask", return_value=expected):
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
            "X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED    UNREADY    READY    RUNNING\n"
            "---------  ---------  ----------  -----------  --------  ---------  -------  ---------\n"
            "summary    SUCCEEDED           4            4         0          0        0          0\n"
        )
        mock_status = {"success": True, "output": succeeded_report}

        with patch("obs_nickel_data_tools.core.executor.bps") as mock_bps_mod:
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.status.return_value = mock_status
            mock_bps_mod.BPSConfig = MagicMock()
            mock_bps_mod.render_bps_config = MagicMock(return_value=Path("/rendered.yaml"))

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
            mock_bps_mod.render_bps_config = MagicMock(return_value=Path("/rendered.yaml"))

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

        # Status always returns RUNNING (never completes)
        running_report = (
            "X_REPORT    STATE    EXPECTED    SUCCEEDED    FAILED    UNREADY    READY    RUNNING\n"
            "summary    RUNNING          4            0         0          0        2          2\n"
        )
        mock_status = {"success": True, "output": running_report}

        with patch("obs_nickel_data_tools.core.executor.bps") as mock_bps_mod:
            mock_bps_mod.submit.return_value = mock_bps_result
            mock_bps_mod.status.return_value = mock_status
            mock_bps_mod.BPSConfig = MagicMock()
            mock_bps_mod.render_bps_config = MagicMock(return_value=Path("/rendered.yaml"))

            result = executor.run_pipetask(
                ["run", "-b", "/repo", "-g", "/graph.qg"],
                mock_config,
                check=False,
            )

        assert result.returncode == 1
        assert "timeout" in result.stderr.lower() or "timed out" in result.stderr.lower()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestBPSExecutor -v`
Expected: FAIL — `ImportError: cannot import name 'BPSExecutor'`

**Step 3: Write minimal implementation**

Add to `executor.py`:

```python
import logging
import time

from obs_nickel_data_tools.core import bps

log = logging.getLogger(__name__)


class BPSExecutor:
    """Execute pipetask commands via BPS batch submission.

    QGraph generation ("qgraph" subcommand) always runs locally since it's
    fast and stage modules need to inspect the graph (e.g., empty qgraph check).

    Pipeline execution ("run" subcommand) is routed through BPS:
    1. Parse pipetask args to extract the pre-built qgraph file
    2. Build a BPSConfig and render the BPS YAML
    3. Submit via bps.submit()
    4. Poll via bps.status() until completion
    5. Translate BPS result to CompletedProcess for stage module compatibility

    Args:
        site: Compute site ("local", "slurm", "htcondor")
        poll_interval: Initial seconds between status checks (grows with backoff)
        timeout: Maximum seconds to wait for a single BPS job
    """

    def __init__(
        self,
        site: str = "local",
        poll_interval: float = 5.0,
        timeout: float = 7200.0,
    ):
        self.site = site
        self.poll_interval = poll_interval
        self.timeout = timeout

    def run_pipetask(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        subcommand = args[0] if args else ""

        if subcommand == "qgraph":
            # QGraph generation runs locally (fast, needed for validation)
            return run_pipetask(args, config, **kwargs)

        if subcommand != "run":
            # Unknown subcommand — fall back to local execution
            return run_pipetask(args, config, **kwargs)

        return self._submit_and_poll(args, config, **kwargs)

    def _submit_and_poll(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        """Submit a pipeline run to BPS and poll until completion."""
        parsed = _parse_pipetask_args(args)
        qgraph_file = parsed.get("qgraph_file")

        if not qgraph_file:
            log.warning("No qgraph file in args, falling back to local execution")
            return run_pipetask(args, config, **kwargs)

        # Build BPSConfig for submission
        bps_cfg = bps.BPSConfig(
            pipeline="custom",  # Will use pre-built qgraph, not pipeline YAML
            night="00000000",   # Placeholder — qgraph has the actual data query
            site=self.site,
        )

        # Submit to BPS
        log.info(f"  Submitting to BPS (site={self.site}, qgraph={qgraph_file})")
        bps_result = bps.submit(bps_cfg, config)

        if not bps_result.success:
            log.error(f"  BPS submit failed: {bps_result.error}")
            return subprocess.CompletedProcess(
                args=["bps", "submit"],
                returncode=1,
                stdout="",
                stderr=bps_result.error or "BPS submission failed",
            )

        # Poll until completion
        run_id = bps_result.run_id
        log.info(f"  BPS job submitted: run_id={run_id}")

        interval = self.poll_interval
        max_interval = 60.0
        start = time.monotonic()

        while time.monotonic() - start < self.timeout:
            status_result = bps.status(run_id, config)
            raw_output = status_result.get("output", "")
            parsed_status = _parse_bps_report(raw_output)
            state = parsed_status["state"]

            if state in ("SUCCEEDED", "FAILED", "DELETED"):
                log.info(
                    f"  BPS job {state}: {parsed_status['succeeded']} ok, "
                    f"{parsed_status['failed']} failed"
                )
                if bps_result.submit_dir:
                    log_file = kwargs.get("log_file")
                    if log_file:
                        with open(log_file, "a") as f:
                            f.write(
                                f"\nBPS job completed: run_id={run_id}, "
                                f"state={state}, "
                                f"logs at: {bps_result.submit_dir}/logging/\n"
                            )
                return _translate_bps_to_completed_process(parsed_status)

            time.sleep(interval)
            interval = min(interval * 1.5, max_interval)

        # Timeout
        log.warning(f"  BPS job timed out after {self.timeout}s (run_id={run_id})")
        return subprocess.CompletedProcess(
            args=["bps", "submit"],
            returncode=1,
            stdout="",
            stderr=f"BPS job timed out after {self.timeout}s (run_id={run_id})",
        )
```

**Important:** The `BPSConfig` validation requires `pipeline` to be in `VALID_PIPELINES` and `night` to match `YYYYMMDD`. We need to relax validation in `bps.py` for the executor use case. For now, add `"custom"` to `VALID_PIPELINES` in `bps.py` (line 31):

```python
VALID_PIPELINES = ("calibs", "science", "dia", "fphot", "custom")
```

And make the night validation accept the placeholder:

```python
# In BPSConfig.__post_init__, change line 80:
if self.night != "00000000" and not re.match(r"^\d{8}$", self.night):
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestBPSExecutor -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/executor.py packages/data_tools/src/obs_nickel_data_tools/core/bps.py packages/obs_nickel/tests/test_executor.py
git commit -m "feat: add BPSExecutor with submit/poll lifecycle"
```

---

### Task 6: RunConfig Execution Fields

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py:347-520`
- Test: `packages/obs_nickel/tests/test_run_config.py`

**Step 1: Write the failing tests**

Add to `test_run_config.py`:

```python
@pytest.fixture
def bps_yaml(tmp_path):
    cfg = {
        "object": "2023ixf",
        "ra": 210.91,
        "dec": 54.32,
        "bands": ["r", "i"],
        "science": {"nights": [20230519]},
        "options": {
            "execution": "bps",
            "site": "slurm",
            "concurrent_nights": 4,
            "bps_poll_interval": 10.0,
            "bps_timeout": 3600,
        },
    }
    path = tmp_path / "bps.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return path


class TestRunConfigExecutionFields:
    def test_parses_bps_execution_fields(self, bps_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(bps_yaml)
        assert cfg.execution == "bps"
        assert cfg.site == "slurm"
        assert cfg.concurrent_nights == 4
        assert cfg.bps_poll_interval == 10.0
        assert cfg.bps_timeout == 3600

    def test_default_execution_is_local(self, sn_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(sn_yaml)
        assert cfg.execution == "local"
        assert cfg.site == "local"
        assert cfg.concurrent_nights == 0
        assert cfg.bps_poll_interval == 5.0
        assert cfg.bps_timeout == 7200.0

    def test_concurrent_nights_without_bps(self, tmp_path):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg_data = {
            "object": "test",
            "ra": 100.0,
            "dec": 10.0,
            "bands": ["r"],
            "science": {"nights": [20230101]},
            "options": {"concurrent_nights": 3},
        }
        path = tmp_path / "concurrent.yaml"
        with open(path, "w") as f:
            yaml.dump(cfg_data, f)
        cfg = RunConfig.from_yaml(path)
        assert cfg.execution == "local"
        assert cfg.concurrent_nights == 3
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_run_config.py::TestRunConfigExecutionFields -v`
Expected: FAIL — `AttributeError: 'RunConfig' has no attribute 'execution'`

**Step 3: Write minimal implementation**

In `run.py`, add to the `RunConfig` dataclass (after the transit search fields, around line 397):

```python
    # Execution backend
    execution: str = "local"          # "local" | "bps"
    site: str = "local"               # "local" | "slurm" | "htcondor"
    concurrent_nights: int = 0        # 0 = sequential (default)
    bps_poll_interval: float = 5.0    # Seconds between BPS status checks
    bps_timeout: float = 7200.0       # Per-stage BPS timeout in seconds
```

In `from_yaml()`, add to the `return cls(...)` call (after `transit_duration_max`, around line 518):

```python
            execution=options.get("execution", "local"),
            site=options.get("site", "local"),
            concurrent_nights=int(options.get("concurrent_nights", 0)),
            bps_poll_interval=float(options.get("bps_poll_interval", 5.0)),
            bps_timeout=float(options.get("bps_timeout", 7200.0)),
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_run_config.py::TestRunConfigExecutionFields -v`
Expected: 3 PASSED

**Step 5: Run all existing RunConfig tests to verify no regressions**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_run_config.py -v`
Expected: All tests PASS (existing + new)

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py packages/obs_nickel/tests/test_run_config.py
git commit -m "feat: add execution/site/concurrent_nights fields to RunConfig"
```

---

### Task 7: Executor Factory and Orchestrator Wiring

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py`
- Test: `packages/obs_nickel/tests/test_run_config.py`

**Step 1: Write the failing tests**

Add to `test_run_config.py`:

```python
class TestExecutorFactory:
    def test_local_config_creates_local_executor(self, sn_yaml):
        from obs_nickel_data_tools.core.executor import LocalExecutor
        from obs_nickel_data_tools.core.run import RunConfig, _create_executor

        cfg = RunConfig.from_yaml(sn_yaml)
        executor = _create_executor(cfg)
        assert isinstance(executor, LocalExecutor)

    def test_bps_config_creates_bps_executor(self, bps_yaml):
        from obs_nickel_data_tools.core.executor import BPSExecutor
        from obs_nickel_data_tools.core.run import RunConfig, _create_executor

        cfg = RunConfig.from_yaml(bps_yaml)
        executor = _create_executor(cfg)
        assert isinstance(executor, BPSExecutor)
        assert executor.site == "slurm"
        assert executor.poll_interval == 10.0
        assert executor.timeout == 3600
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_run_config.py::TestExecutorFactory -v`
Expected: FAIL — `ImportError: cannot import name '_create_executor'`

**Step 3: Write minimal implementation**

Add to `run.py` (after the `RunResult` dataclass, around line 577):

```python
def _create_executor(run_cfg: RunConfig):
    """Create the appropriate executor from RunConfig.

    Args:
        run_cfg: Pipeline run configuration

    Returns:
        LocalExecutor for local execution, BPSExecutor for BPS execution
    """
    from obs_nickel_data_tools.core.executor import BPSExecutor, LocalExecutor

    if run_cfg.execution == "bps":
        return BPSExecutor(
            site=run_cfg.site,
            poll_interval=run_cfg.bps_poll_interval,
            timeout=run_cfg.bps_timeout,
        )
    return LocalExecutor()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_run_config.py::TestExecutorFactory -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py packages/obs_nickel/tests/test_run_config.py
git commit -m "feat: add executor factory to orchestrator"
```

---

### Task 8: Wire Executor into Stage Modules

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/calibs.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/science.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/dia.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/fphot.py`
- Test: `packages/obs_nickel/tests/test_executor.py`

Each stage module follows the same pattern:
1. Add `executor=None` parameter to `run()`
2. Default to `LocalExecutor()` if None
3. Replace `run_pipetask(args, config, ...)` with `executor.run_pipetask(args, config, ...)`
4. Keep `run_butler()` and `run_butler_query()` calls unchanged

**Step 1: Write the failing test**

Add to `test_executor.py`:

```python
class TestExecutorWiring:
    """Verify stage modules accept and use executor parameter."""

    def test_calibs_accepts_executor(self):
        """calibs.run() signature accepts executor kwarg."""
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestExecutorWiring -v`
Expected: FAIL — `AssertionError` (no `executor` parameter)

**Step 3: Modify each stage module**

**calibs.py** — Change the `run()` signature (line 38) and add executor defaulting:

```python
def run(
    night: str,
    config: Config,
    *,
    jobs: int = 4,
    log_file: Path | None = None,
    executor=None,
) -> CalibsResult:
```

At the top of the function body, add:

```python
    from obs_nickel_data_tools.core.executor import LocalExecutor

    if executor is None:
        executor = LocalExecutor()
```

Then replace all `run_pipetask(` calls with `executor.run_pipetask(` (4 occurrences at lines 152, 174, 239, 265). The import `from obs_nickel_data_tools.core.stack import run_butler, run_pipetask` on line 17 becomes `from obs_nickel_data_tools.core.stack import run_butler` (remove `run_pipetask`).

**science.py** — Same pattern. Change `run()` signature (line 178), add `executor=None` parameter:

```python
def run(
    night: str,
    config: Config,
    *,
    jobs: int = 8,
    bad_exposures: str | None = None,
    bad_file: Path | None = None,
    object_filter: str | None = None,
    skip_coadds: bool = False,
    science_config: Path | None = None,
    science_cfg: ScienceConfig | None = None,
    use_fallbacks: bool = True,
    bands: list[str] | None = None,
    target_ra: float | None = None,
    target_dec: float | None = None,
    log_file: Path | None = None,
    executor=None,
```

Add executor defaulting at top of body. Replace `run_pipetask(` with `executor.run_pipetask(` (4 occurrences at lines 458, 482, 714, 736). Update import on line 26-30.

**dia.py** — Same pattern. Add `executor=None` to `run()` (line 98). Replace 2 `run_pipetask(` calls (lines 272, 306). Update import on line 23.

**fphot.py** — Same pattern. Add `executor=None` to `run()` (line 97). Replace 2 `run_pipetask(` calls (lines 189, 257). Update import on line 19.

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestExecutorWiring -v`
Expected: 4 PASSED

**Step 5: Run full test suite to check for regressions**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/ -v`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/calibs.py packages/data_tools/src/obs_nickel_data_tools/core/science.py packages/data_tools/src/obs_nickel_data_tools/core/dia.py packages/data_tools/src/obs_nickel_data_tools/core/fphot.py packages/obs_nickel/tests/test_executor.py
git commit -m "feat: wire executor parameter into stage modules"
```

---

### Task 9: Pass Executor Through Orchestrator Steps

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py`

**Step 1: Modify orchestrator step functions to accept and pass executor**

Update signatures for `_run_calibs_step`, `_run_science_step`, `_run_dia_step`, `_run_fphot_step` to accept `executor` parameter, and pass it through to stage module `run()` calls.

For example, `_run_calibs_step` (line 779):

```python
def _run_calibs_step(
    all_nights: list[str],
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    dry_run: bool,
    executor=None,
) -> RunResult | None:
```

And in the body, change line 797-798 from:

```python
            calib_result = calibs.run(
                night, config, jobs=run_cfg.jobs, log_file=calib_log
            )
```

To:

```python
            calib_result = calibs.run(
                night, config, jobs=run_cfg.jobs, log_file=calib_log,
                executor=executor,
            )
```

Apply same pattern to `_run_science_step` (line 843-854), `_run_dia_step` (line 921-933), and `_run_fphot_step` (line 979-988).

Then in the main `run()` function (line 1232+), create the executor and pass it:

```python
    # After loading RunConfig, create executor
    executor = _create_executor(run_cfg)
    log.info(f"Execution: {run_cfg.execution} (site={run_cfg.site})")
```

And pass `executor=executor` to each step call:

```python
    # Calibs step
    early = _run_calibs_step(all_nights, run_cfg, config, result, dry_run, executor=executor)
    # Science step
    early = _run_science_step(all_nights, run_cfg, config, result, science_cfg, dry_run, executor=executor)
    # DIA step
    early = _run_dia_step(all_nights, run_cfg, config, result, dry_run, executor=executor)
    # Fphot step
    _run_fphot_step(all_nights, run_cfg, config, result, dry_run, executor=executor)
```

**Step 2: Verify all tests pass**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py
git commit -m "feat: pass executor through orchestrator to stage modules"
```

---

### Task 10: Concurrent Dispatch Utility

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py`
- Test: `packages/obs_nickel/tests/test_executor.py`

**Step 1: Write the failing tests**

Add to `test_executor.py`:

```python
import time


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
        assert len(order) == 3  # All items ran
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestDispatchConcurrent -v`
Expected: FAIL — `ImportError: cannot import name '_dispatch_concurrent'`

**Step 3: Write minimal implementation**

Add to `run.py` (after `_create_executor`, before the step functions):

```python
import concurrent.futures


def _dispatch_concurrent(
    fn,
    items: list,
    *,
    max_workers: int = 4,
    item_label: str = "item",
):
    """Run fn(item) concurrently for each item.

    Args:
        fn: Callable that takes a single item and returns a result
        items: List of items to process
        max_workers: Maximum concurrent workers
        item_label: Label for log messages

    Returns:
        Dict mapping each item to its result (None if fn raised an exception)
    """
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_item = {pool.submit(fn, item): item for item in items}
        for future in concurrent.futures.as_completed(future_to_item):
            item = future_to_item[future]
            try:
                results[item] = future.result()
            except Exception as e:
                log.error(f"  {item_label} {item} raised: {e}")
                results[item] = None
    return results
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestDispatchConcurrent -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py packages/obs_nickel/tests/test_executor.py
git commit -m "feat: add _dispatch_concurrent utility for cross-night parallelism"
```

---

### Task 11: Wire Concurrent Dispatch into Orchestrator Steps

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py`

**Step 1: Add concurrent execution path to each step function**

Update `_run_calibs_step` to use `_dispatch_concurrent` when `concurrent_nights > 1`:

```python
def _run_calibs_step(
    all_nights, run_cfg, config, result, dry_run, executor=None,
) -> RunResult | None:
    from obs_nickel_data_tools.core import calibs

    if dry_run:
        for night in all_nights:
            log.info(f"  [DRY RUN] calibs.run({night})")
        return None

    if run_cfg.concurrent_nights > 1:
        log.info(f"Running calibrations for {len(all_nights)} nights "
                 f"(concurrent={run_cfg.concurrent_nights})...")

        def _run_calib(night):
            log.info(f"Running calibrations for {night}...")
            calib_log = _get_step_log_file("calibs", night=night)
            calib_result = calibs.run(
                night, config, jobs=run_cfg.jobs, log_file=calib_log,
                executor=executor,
            )
            _maybe_split_log(calib_log)
            return calib_result

        night_results = _dispatch_concurrent(
            _run_calib, all_nights,
            max_workers=run_cfg.concurrent_nights,
            item_label="night",
        )
        for night in all_nights:
            r = night_results.get(night)
            if r is None or not r.success:
                result.failed_calibs.append(night)
                log.warning(f"Calibrations failed for {night}")
        if result.failed_calibs and not run_cfg.continue_on_error:
            result.success = False
            result.error = f"Calibrations failed for {result.failed_calibs[0]}"
            return result
    else:
        # Sequential: existing behavior
        for night in all_nights:
            log.info(f"Running calibrations for {night}...")
            calib_log = _get_step_log_file("calibs", night=night)
            calib_result = calibs.run(
                night, config, jobs=run_cfg.jobs, log_file=calib_log,
                executor=executor,
            )
            _maybe_split_log(calib_log)
            if not calib_result.success:
                result.failed_calibs.append(night)
                log.warning(f"Calibrations failed for {night}: {calib_result.error}")
                if not run_cfg.continue_on_error:
                    result.success = False
                    result.error = f"Calibrations failed for {night}"
                    return result

    return None
```

Apply the same concurrent/sequential pattern to `_run_science_step`, `_run_dia_step`, and `_run_fphot_step`. For DIA and fphot, the items are `(night, band)` tuples since they iterate over nights AND bands.

**Step 2: Verify all tests pass**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py
git commit -m "feat: wire concurrent dispatch into orchestrator step functions"
```

---

### Task 12: CLI Flags

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/cli.py`

**Step 1: Add --site and --concurrent flags to `nickel run` command**

Find the `nickel run` command definition in `cli.py` and add options:

```python
@click.option("--site", type=click.Choice(["local", "slurm", "htcondor"]),
              help="Execution site (implies BPS execution)")
@click.option("--concurrent", type=int, default=None,
              help="Max nights to process in parallel")
```

In the command body, override RunConfig values:

```python
    if site:
        run_cfg.execution = "bps"
        run_cfg.site = site
    if concurrent is not None:
        run_cfg.concurrent_nights = concurrent
```

**Step 2: Verify CLI works**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m obs_nickel_data_tools.cli run --help`
Expected: Shows `--site` and `--concurrent` options

**Step 3: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/cli.py
git commit -m "feat: add --site and --concurrent CLI flags to nickel run"
```

---

### Task 13: Final Integration Test

**Files:**
- Test: `packages/obs_nickel/tests/test_executor.py`

**Step 1: Write integration test**

Add to `test_executor.py`:

```python
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
        """When no executor param, stage modules default to LocalExecutor."""
        import inspect
        from obs_nickel_data_tools.core import calibs, dia, fphot, science

        for mod in [calibs, science, dia, fphot]:
            sig = inspect.signature(mod.run)
            param = sig.parameters["executor"]
            assert param.default is None, f"{mod.__name__}.run executor default should be None"

    def test_create_executor_roundtrip(self):
        """RunConfig -> executor -> can be called."""
        from obs_nickel_data_tools.core.executor import BPSExecutor, LocalExecutor
        from obs_nickel_data_tools.core.run import RunConfig, _create_executor

        # Local
        local_cfg = RunConfig(object_name="test", ra=100, dec=10, bands=["r"])
        local_exec = _create_executor(local_cfg)
        assert isinstance(local_exec, LocalExecutor)

        # BPS
        bps_cfg = RunConfig(
            object_name="test", ra=100, dec=10, bands=["r"],
            execution="bps", site="slurm",
        )
        bps_exec = _create_executor(bps_cfg)
        assert isinstance(bps_exec, BPSExecutor)
        assert bps_exec.site == "slurm"
```

**Step 2: Run all tests**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add packages/obs_nickel/tests/test_executor.py
git commit -m "test: add integration tests for executor protocol"
```

---

## Dependency Graph

```
Task 1 (Protocol + LocalExecutor)
  └─ Task 2 (Arg Parser)
       └─ Task 3 (Report Parser)
            └─ Task 4 (Result Translator)
                 └─ Task 5 (BPSExecutor lifecycle)
Task 6 (RunConfig fields) ─────────────┐
Task 7 (Executor factory) ─── needs 1,6 ┤
Task 8 (Stage module wiring) ─ needs 1  │
Task 9 (Orchestrator wiring) ─ needs 7,8┤
Task 10 (Concurrent utility) ────────── │
Task 11 (Concurrent in orch) ─ needs 9,10
Task 12 (CLI flags) ── needs 6
Task 13 (Integration test) ── needs all
```

Tasks 1-5 are sequential (BPS executor build-up).
Tasks 6, 8, 10, 12 can run in parallel with the BPS chain.
Tasks 7, 9, 11, 13 are integration points.
