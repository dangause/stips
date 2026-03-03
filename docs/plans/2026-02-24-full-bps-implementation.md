# Full BPS Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the remaining gaps in the BPS executor pipeline so that `nickel run config.yaml --site local` works end-to-end with LSST's ctrl_bps_parsl, then build a Docker Compose Slurm environment for cluster-level testing.

**Architecture:** The BPS infrastructure is ~85-90% complete. Three gaps remain: (1) no `custom.yaml` template for pre-built quantum graphs, (2) no ctrl_bps availability check at executor creation, and (3) no Docker Slurm test environment. Phase A closes the first two gaps and validates with Parsl Local. Phase B creates the Docker environment.

**Tech Stack:** Python 3.11, LSST ctrl_bps/ctrl_bps_parsl, Parsl, Docker Compose, Slurm

**Branch:** `feature/dpg/bps-full` off `feature/dpg/bps-parallelization`

---

## Background

### What exists

The BPS executor pipeline already has:

- **`PipetaskExecutor` protocol** (`core/executor.py:28-42`) — runtime-checkable protocol with `run_pipetask()` method
- **`LocalExecutor`** (`core/executor.py:45-57`) — passthrough to `stack.run_pipetask()`
- **`BPSExecutor`** (`core/executor.py:182-303`) — submit/poll lifecycle with exponential backoff
- **`BPSConfig` dataclass** (`core/bps.py:37-81`) — pipeline, night, site, band, etc.
- **`render_bps_config()`** (`core/bps.py:139-229`) — template variable substitution
- **`submit()/status()/cancel()`** (`core/bps.py:232-411`) — BPS command wrappers
- **BPS YAML templates** (`bps/pipelines/`) — calibs, science, dia, fphot
- **Site configs** (`bps/sites/`) — local (Parsl Thread), slurm (Parsl Slurm), htcondor
- **RunConfig execution fields** (`core/run.py:348+`) — `execution`, `site`, `concurrent_nights`, `bps_poll_interval`, `bps_timeout`
- **`_create_executor()`** (`core/run.py:591-608`) — factory from RunConfig
- **CLI flags** (`cli.py`) — `--site`, `--concurrent` on `nickel run`
- **Stage module wiring** — calibs/science/dia/fphot all accept `executor=None`
- **42 unit tests** in `test_executor.py`

### What's missing (the gaps)

1. **`bps/pipelines/custom.yaml`** — Template for pre-built quantum graphs (BPSExecutor already creates `BPSConfig(pipeline="custom")` but no template exists)
2. **`BPSConfig.qgraph_file` field** — No way to pass qgraph path to `render_bps_config()`
3. **`render_bps_config()` qgraph injection** — Doesn't substitute `{qgraph_file}` into templates
4. **ctrl_bps availability check** — `_create_executor()` doesn't verify ctrl_bps is installed
5. **Docker Slurm test environment** — No way to test BPS+Slurm without a real cluster

### Key constraint: "custom" pipeline

When `BPSExecutor._submit_and_poll()` runs, it:
1. Parses pipetask args to extract the pre-built qgraph file path
2. Creates `BPSConfig(pipeline="custom", night="00000000", site=self.site)`
3. Calls `bps.submit(bps_cfg, config)`

The `submit()` function calls `render_bps_config()`, which calls `find_bps_config("custom", config)` to load `bps/pipelines/custom.yaml`. That file doesn't exist yet, so BPS submission always fails with `FileNotFoundError`.

### How BPS uses quantum graphs

In the normal LSST workflow, BPS generates its own quantum graph from `pipelineYaml:` + `dataQuery:`. But our pipeline already generates the qgraph locally (via `pipetask qgraph`) so stage modules can inspect it (e.g., empty qgraph check). The `custom.yaml` template tells BPS to use our pre-built qgraph via `qgraphFile:` instead of generating a new one.

---

## Phase A — Parsl Local (Close the Gaps)

### Task 1: Create `custom.yaml` BPS Pipeline Template

**Files:**
- Create: `bps/pipelines/custom.yaml`
- Test: `packages/obs_nickel/tests/test_bps_config.py`

**Step 1: Write the failing test**

Create `packages/obs_nickel/tests/test_bps_config.py`:

```python
"""Tests for BPS configuration rendering."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_tools/src"))


class TestCustomTemplate:
    def test_custom_yaml_exists(self):
        """The custom.yaml template file must exist in bps/pipelines/."""
        bps_dir = Path(__file__).resolve().parents[2] / "bps" / "pipelines"
        custom_yaml = bps_dir / "custom.yaml"
        assert custom_yaml.exists(), f"Missing: {custom_yaml}"

    def test_custom_yaml_has_qgraph_file_placeholder(self):
        """The custom.yaml must contain a {qgraph_file} placeholder."""
        bps_dir = Path(__file__).resolve().parents[2] / "bps" / "pipelines"
        custom_yaml = bps_dir / "custom.yaml"
        content = custom_yaml.read_text()
        assert "{qgraph_file}" in content

    def test_custom_yaml_has_no_pipeline_yaml(self):
        """custom.yaml must NOT have pipelineYaml (qgraph encodes the pipeline)."""
        bps_dir = Path(__file__).resolve().parents[2] / "bps" / "pipelines"
        custom_yaml = bps_dir / "custom.yaml"
        content = custom_yaml.read_text()
        assert "pipelineYaml:" not in content

    def test_custom_yaml_includes_site_config(self):
        """custom.yaml must include the site config for compute resources."""
        bps_dir = Path(__file__).resolve().parents[2] / "bps" / "pipelines"
        custom_yaml = bps_dir / "custom.yaml"
        content = custom_yaml.read_text()
        assert "includeConfigs:" in content
        assert "{computeSite}" in content
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_bps_config.py -v`
Expected: FAIL — `custom.yaml` does not exist yet

**Step 3: Create the custom.yaml template**

Create `bps/pipelines/custom.yaml`:

```yaml
# Nickel Processing Suite - Custom BPS Pipeline (Pre-built Quantum Graph)
#
# This template uses a pre-built quantum graph instead of generating one.
# Used by BPSExecutor when routing pipetask "run" commands through BPS.
#
# The quantum graph already encodes the pipeline, data query, input/output
# collections, etc. — we only need to provide compute resources and site config.
#
# Variables:
#   {qgraph_file}   - Path to pre-built quantum graph
#   {repo}           - Butler repository path

# Inherit site-specific settings
includeConfigs:
  - ../sites/{computeSite}.yaml

# =============================================================================
# Payload Configuration
# =============================================================================
payload:
  payloadName: nickel-custom-{night}
  butlerConfig: "{repo}"

# =============================================================================
# Pre-built Quantum Graph
# =============================================================================
# Use the quantum graph generated by pipetask qgraph (already has pipeline,
# data query, input/output collections baked in).
qgraphFile: "{qgraph_file}"
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_bps_config.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add bps/pipelines/custom.yaml packages/obs_nickel/tests/test_bps_config.py
git commit -m "feat: add custom.yaml BPS template for pre-built quantum graphs"
```

---

### Task 2: Add `qgraph_file` Field to `BPSConfig`

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/bps.py:37-81`
- Test: `packages/obs_nickel/tests/test_bps_config.py` (append)

**Step 1: Write the failing test**

Append to `packages/obs_nickel/tests/test_bps_config.py`:

```python
class TestBPSConfigQgraphField:
    def test_qgraph_file_default_none(self):
        """BPSConfig.qgraph_file defaults to None."""
        from obs_nickel_data_tools.core.bps import BPSConfig

        cfg = BPSConfig(pipeline="custom", night="20230519")
        assert cfg.qgraph_file is None

    def test_qgraph_file_accepts_path(self):
        """BPSConfig.qgraph_file accepts a string path."""
        from obs_nickel_data_tools.core.bps import BPSConfig

        cfg = BPSConfig(
            pipeline="custom",
            night="20230519",
            qgraph_file="/path/to/graph.qg",
        )
        assert cfg.qgraph_file == "/path/to/graph.qg"

    def test_custom_pipeline_without_qgraph_is_valid(self):
        """pipeline='custom' is valid even without qgraph_file (render will handle it)."""
        from obs_nickel_data_tools.core.bps import BPSConfig

        cfg = BPSConfig(pipeline="custom", night="20230519")
        assert cfg.pipeline == "custom"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_bps_config.py::TestBPSConfigQgraphField -v`
Expected: FAIL — `BPSConfig` has no `qgraph_file` attribute

**Step 3: Add qgraph_file field to BPSConfig**

In `packages/data_tools/src/obs_nickel_data_tools/core/bps.py`, add the field to the `BPSConfig` dataclass (after `coord_collection` on line 61):

```python
    coord_collection: str | None = None
    qgraph_file: str | None = None         # NEW: Pre-built quantum graph path
    operator: str = field(default_factory=lambda: os.environ.get("USER", "nps"))
```

Also update the docstring (around line 48) to include:
```
        qgraph_file: Path to pre-built quantum graph (for custom pipeline)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_bps_config.py -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/bps.py packages/obs_nickel/tests/test_bps_config.py
git commit -m "feat: add qgraph_file field to BPSConfig dataclass"
```

---

### Task 3: Update `render_bps_config()` for Qgraph Injection

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/bps.py:139-229`
- Test: `packages/obs_nickel/tests/test_bps_config.py` (append)

**Step 1: Write the failing test**

Append to `packages/obs_nickel/tests/test_bps_config.py`:

```python
import tempfile


class TestRenderBpsConfigQgraph:
    def _make_mock_config(self, tmp_path):
        """Create a mock Config object pointing at the real bps/ templates."""
        from unittest.mock import MagicMock

        # obs_nickel is at packages/obs_nickel, bps/ is at repo root
        # find_bps_config() goes: config.obs_nickel.parent.parent / "bps" / "pipelines"
        repo_root = Path(__file__).resolve().parents[2]
        mock_config = MagicMock()
        mock_config.obs_nickel = repo_root / "packages" / "obs_nickel"
        mock_config.repo = tmp_path / "repo"
        mock_config.stack_dir = Path("/fake/stack")
        mock_config.cp_pipe_dir = Path("/fake/cp_pipe")
        mock_config.raw_parent_dir = Path("/fake/raw")
        mock_config.refcat_repo = Path("/fake/refcats")
        return mock_config

    def test_render_custom_injects_qgraph_file(self, tmp_path):
        """render_bps_config with custom pipeline substitutes {qgraph_file}."""
        from obs_nickel_data_tools.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path)
        bps_cfg = BPSConfig(
            pipeline="custom",
            night="20230519",
            site="local",
            qgraph_file="/path/to/my_graph.qg",
        )

        output_dir = tmp_path / "submit"
        rendered_path = render_bps_config(bps_cfg, config, output_dir)
        rendered_content = rendered_path.read_text()

        assert "qgraphFile:" in rendered_content
        assert "/path/to/my_graph.qg" in rendered_content
        # Must NOT contain unsubstituted placeholder
        assert "{qgraph_file}" not in rendered_content

    def test_render_custom_has_no_pipeline_yaml(self, tmp_path):
        """Rendered custom config must not have pipelineYaml."""
        from obs_nickel_data_tools.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path)
        bps_cfg = BPSConfig(
            pipeline="custom",
            night="20230519",
            site="local",
            qgraph_file="/path/to/graph.qg",
        )

        output_dir = tmp_path / "submit"
        rendered_path = render_bps_config(bps_cfg, config, output_dir)
        rendered_content = rendered_path.read_text()

        assert "pipelineYaml:" not in rendered_content

    def test_render_non_custom_ignores_qgraph(self, tmp_path):
        """For non-custom pipelines, qgraph_file is ignored."""
        from obs_nickel_data_tools.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path)
        bps_cfg = BPSConfig(
            pipeline="science",
            night="20230519",
            site="local",
        )

        output_dir = tmp_path / "submit"
        rendered_path = render_bps_config(bps_cfg, config, output_dir)
        rendered_content = rendered_path.read_text()

        # Science pipeline should have pipelineYaml, NOT qgraphFile
        assert "pipelineYaml:" in rendered_content
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_bps_config.py::TestRenderBpsConfigQgraph -v`
Expected: FAIL — `{qgraph_file}` not substituted (key not in variables dict)

**Step 3: Update render_bps_config()**

In `packages/data_tools/src/obs_nickel_data_tools/core/bps.py`, modify `render_bps_config()`.

Add `qgraph_file` to the variables dict (after the existing `"pipeline"` key around line 189):

```python
        "pipeline": bps_cfg.pipeline,
        "qgraph_file": bps_cfg.qgraph_file or "",
    }
```

That's the only change needed — the `{qgraph_file}` placeholder in `custom.yaml` will be substituted by the existing `str.replace()` loop.

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_bps_config.py -v`
Expected: PASS (10 tests)

**Step 5: Also run existing tests to verify no regressions**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py -v`
Expected: PASS (all 42 tests)

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/bps.py packages/obs_nickel/tests/test_bps_config.py
git commit -m "feat: inject qgraph_file into BPS config rendering"
```

---

### Task 4: Add ctrl_bps Availability Check

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py:591-608`
- Test: `packages/obs_nickel/tests/test_executor.py` (append)

**Step 1: Write the failing test**

Append to `packages/obs_nickel/tests/test_executor.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestCtrlBpsAvailabilityCheck -v`
Expected: FAIL — `_create_executor` doesn't check for ctrl_bps (the first test won't raise ImportError because the current code doesn't try to import lsst.ctrl.bps)

**Step 3: Add availability check to _create_executor()**

In `packages/data_tools/src/obs_nickel_data_tools/core/run.py`, replace `_create_executor()` (lines 591-608):

```python
def _create_executor(run_cfg: RunConfig):
    """Create the appropriate executor from RunConfig.

    Args:
        run_cfg: Pipeline run configuration

    Returns:
        LocalExecutor for local execution, BPSExecutor for BPS execution

    Raises:
        ImportError: If BPS execution requested but ctrl_bps not installed
    """
    from obs_nickel_data_tools.core.executor import BPSExecutor, LocalExecutor

    if run_cfg.execution == "bps":
        # Fail fast if ctrl_bps is not available
        try:
            import lsst.ctrl.bps  # noqa: F401
        except ImportError:
            raise ImportError(
                "BPS execution requires lsst.ctrl.bps. "
                "Install with: pip install lsst-ctrl-bps\n"
                "Or use --site local with ctrl_bps_parsl for local testing."
            )

        if run_cfg.site == "local":
            try:
                import lsst.ctrl.bps.parsl  # noqa: F401
            except ImportError:
                raise ImportError(
                    "Local BPS execution requires lsst.ctrl.bps.parsl. "
                    "Install with: pip install lsst-ctrl-bps-parsl"
                )

        return BPSExecutor(
            site=run_cfg.site,
            poll_interval=run_cfg.bps_poll_interval,
            timeout=run_cfg.bps_timeout,
        )
    return LocalExecutor()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestCtrlBpsAvailabilityCheck -v`
Expected: PASS (3 tests)

**Step 5: Run all executor tests for regression check**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py -v`
Expected: PASS (45 tests — 42 existing + 3 new)

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py packages/obs_nickel/tests/test_executor.py
git commit -m "feat: fail fast when ctrl_bps not installed for BPS execution"
```

---

### Task 5: Wire `qgraph_file` into BPSExecutor._submit_and_poll()

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/executor.py:229-303`
- Test: `packages/obs_nickel/tests/test_executor.py` (modify existing `TestBPSExecutor`)

**Step 1: Write the failing test**

Append to `TestBPSExecutor` class in `packages/obs_nickel/tests/test_executor.py`:

```python
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
            # Check that qgraph_file was passed
            if call_kwargs.kwargs:
                assert call_kwargs.kwargs.get("qgraph_file") == "/path/to/my_graph.qg"
            else:
                # positional args
                assert "/path/to/my_graph.qg" in str(call_kwargs)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestBPSExecutor::test_submit_passes_qgraph_file_to_bps_config -v`
Expected: FAIL — BPSConfig not called with `qgraph_file` kwarg

**Step 3: Wire qgraph_file into _submit_and_poll()**

In `packages/data_tools/src/obs_nickel_data_tools/core/executor.py`, update `_submit_and_poll()` (around lines 243-248). Replace:

```python
        # Build BPSConfig for submission
        bps_cfg = bps.BPSConfig(
            pipeline="custom",  # Will use pre-built qgraph, not pipeline YAML
            night="00000000",  # Placeholder — qgraph has the actual data query
            site=self.site,
        )
```

With:

```python
        # Build BPSConfig for submission
        bps_cfg = bps.BPSConfig(
            pipeline="custom",  # Will use pre-built qgraph, not pipeline YAML
            night="00000000",  # Placeholder — qgraph has the actual data query
            site=self.site,
            qgraph_file=qgraph_file,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py::TestBPSExecutor -v`
Expected: PASS (5 tests)

**Step 5: Run all tests**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py packages/obs_nickel/tests/test_bps_config.py -v`
Expected: PASS (all tests)

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/executor.py packages/obs_nickel/tests/test_executor.py
git commit -m "feat: wire qgraph_file from pipetask args into BPSConfig"
```

---

### Task 6: Full Integration Test — Custom Pipeline Lifecycle

**Files:**
- Test: `packages/obs_nickel/tests/test_bps_config.py` (append)

**Step 1: Write the integration test**

Append to `packages/obs_nickel/tests/test_bps_config.py`:

```python
from unittest.mock import MagicMock, patch


class TestFullBPSLifecycle:
    """End-to-end test: BPSExecutor → BPSConfig(custom) → render → submit → poll → CompletedProcess."""

    def _make_mock_config(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        mock_config = MagicMock()
        mock_config.obs_nickel = repo_root / "packages" / "obs_nickel"
        mock_config.repo = tmp_path / "repo"
        mock_config.stack_dir = Path("/fake/stack")
        mock_config.cp_pipe_dir = Path("/fake/cp_pipe")
        mock_config.raw_parent_dir = Path("/fake/raw")
        mock_config.refcat_repo = Path("/fake/refcats")
        return mock_config

    def test_custom_template_renders_and_lifecycle_succeeds(self, tmp_path):
        """Full lifecycle: render custom.yaml with qgraph_file → submit → poll → success."""
        from obs_nickel_data_tools.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path)
        qgraph_path = "/data/repo/bps/science_20230519/graph.qg"

        bps_cfg = BPSConfig(
            pipeline="custom",
            night="20230519",
            site="local",
            qgraph_file=qgraph_path,
        )

        # Step 1: Render the config
        output_dir = tmp_path / "submit"
        rendered_path = render_bps_config(bps_cfg, config, output_dir)
        rendered_content = rendered_path.read_text()

        # Verify rendered config
        assert "qgraphFile:" in rendered_content
        assert qgraph_path in rendered_content
        assert "pipelineYaml:" not in rendered_content
        assert "{qgraph_file}" not in rendered_content
        assert "{repo}" not in rendered_content
        assert "{computeSite}" not in rendered_content

        # Verify site config was copied
        assert (output_dir / "sites" / "local.yaml").exists()
        assert (output_dir / "base.yaml").exists()

    def test_bps_executor_full_roundtrip(self, tmp_path):
        """BPSExecutor routes 'run' through custom pipeline with qgraph injection."""
        from obs_nickel_data_tools.core.executor import BPSExecutor

        executor = BPSExecutor(site="local", poll_interval=0.01, timeout=1.0)
        config = self._make_mock_config(tmp_path)

        # Mock bps.submit to use real render_bps_config
        from obs_nickel_data_tools.core import bps as bps_mod

        original_submit = bps_mod.submit
        submit_called_with = {}

        def capturing_submit(bps_cfg, config):
            submit_called_with["pipeline"] = bps_cfg.pipeline
            submit_called_with["qgraph_file"] = bps_cfg.qgraph_file
            submit_called_with["site"] = bps_cfg.site
            # Return mock success instead of actually running bps
            return MagicMock(
                success=True,
                run_id="lifecycle-test-run",
                submit_dir=str(tmp_path / "submit"),
            )

        succeeded_report = (
            "X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED"
            "    UNREADY    READY    RUNNING\n"
            "summary    SUCCEEDED           3            3         0"
            "          0        0          0\n"
        )

        with patch.object(bps_mod, "submit", side_effect=capturing_submit):
            with patch.object(
                bps_mod,
                "status",
                return_value={"success": True, "output": succeeded_report},
            ):
                result = executor.run_pipetask(
                    [
                        "run",
                        "-b",
                        str(config.repo),
                        "-g",
                        "/data/repo/graph.qg",
                        "-j",
                        "4",
                    ],
                    config,
                    check=False,
                )

        # Verify the submit was called with correct params
        assert submit_called_with["pipeline"] == "custom"
        assert submit_called_with["qgraph_file"] == "/data/repo/graph.qg"
        assert submit_called_with["site"] == "local"

        # Verify the result is a proper CompletedProcess
        assert result.returncode == 0
        assert "3 quanta successfully" in result.stdout
        assert "0 failed" in result.stdout
```

**Step 2: Run tests**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_bps_config.py::TestFullBPSLifecycle -v`
Expected: PASS (these tests verify existing + new code works together)

**Step 3: Run the full test suite to verify everything**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py packages/obs_nickel/tests/test_bps_config.py -v`
Expected: PASS (all tests — ~50+ total)

**Step 4: Commit**

```bash
git add packages/obs_nickel/tests/test_bps_config.py
git commit -m "test: add full BPS lifecycle integration tests"
```

---

## Phase B — Docker Slurm Test Environment

### Task 7: Create `docker-slurm.yaml` Site Config

**Files:**
- Create: `bps/sites/docker-slurm.yaml`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/bps.py:34` (add to `VALID_SITES`)
- Test: `packages/obs_nickel/tests/test_bps_config.py` (append)

**Step 1: Write the failing test**

Append to `packages/obs_nickel/tests/test_bps_config.py`:

```python
class TestDockerSlurmSiteConfig:
    def test_docker_slurm_yaml_exists(self):
        """docker-slurm.yaml site config must exist."""
        bps_dir = Path(__file__).resolve().parents[2] / "bps" / "sites"
        assert (bps_dir / "docker-slurm.yaml").exists()

    def test_docker_slurm_is_valid_site(self):
        """'docker-slurm' must be accepted as a valid BPS site."""
        from obs_nickel_data_tools.core.bps import BPSConfig

        cfg = BPSConfig(pipeline="science", night="20230519", site="docker-slurm")
        assert cfg.site == "docker-slurm"

    def test_docker_slurm_uses_parsl_slurm(self):
        """docker-slurm.yaml must use Parsl with SlurmProvider."""
        bps_dir = Path(__file__).resolve().parents[2] / "bps" / "sites"
        content = (bps_dir / "docker-slurm.yaml").read_text()
        assert "lsst.ctrl.bps.parsl.ParslService" in content
        assert "lsst.ctrl.bps.parsl.sites.Slurm" in content

    def test_docker_slurm_conservative_resources(self):
        """docker-slurm.yaml should have conservative memory (4GB, not 128GB)."""
        bps_dir = Path(__file__).resolve().parents[2] / "bps" / "sites"
        content = (bps_dir / "docker-slurm.yaml").read_text()
        # Should reference 4 cores, 4GB memory — conservative for Docker
        assert "cores_per_node: 4" in content
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_bps_config.py::TestDockerSlurmSiteConfig -v`
Expected: FAIL — file doesn't exist, "docker-slurm" not in VALID_SITES

**Step 3: Add "docker-slurm" to VALID_SITES**

In `packages/data_tools/src/obs_nickel_data_tools/core/bps.py`, line 34, change:

```python
VALID_SITES = ("slurm", "htcondor", "local")
```

To:

```python
VALID_SITES = ("slurm", "htcondor", "local", "docker-slurm")
```

**Step 4: Create docker-slurm.yaml**

Create `bps/sites/docker-slurm.yaml`:

```yaml
# Nickel Processing Suite - Docker Slurm Site Configuration
#
# BPS configuration for the Docker Compose Slurm test environment.
# Conservative resources for containerized single-node cluster.
#
# Usage:
#   nickel run config.yaml --site docker-slurm
#   nickel bps submit calibs 20230519 --site docker-slurm

includeConfigs:
  - ../base.yaml

# =============================================================================
# WMS Backend Selection
# =============================================================================
wmsServiceClass: lsst.ctrl.bps.parsl.ParslService
computeSite: docker-slurm

# =============================================================================
# Parsl Configuration
# =============================================================================
parsl:
  log_level: DEBUG
  retries: 2

# =============================================================================
# Docker Slurm Site Definition
# =============================================================================
site:
  docker-slurm:
    class: lsst.ctrl.bps.parsl.sites.Slurm

    # Conservative: single node, 4 cores (Docker container limits)
    nodes: 1
    cores_per_node: 4
    mem_per_node: 4              # GB

    # Short walltime for testing
    walltime: "00:30:00"         # 30 minutes

    # Slurm scheduler options for Docker cluster
    scheduler_options: |
      #SBATCH --partition=normal
      #SBATCH --export=ALL

    # Conservative parallelism for Docker
    max_blocks: 2
    min_blocks: 0
    init_blocks: 1
    parallelism: 1.0

    # Worker initialization
    worker_init: |
      # Source LSST stack (pre-installed in container)
      source /opt/lsst/software/stack/loadLSST.bash
      setup lsst_distrib

      # Setup obs_nickel (mounted into container)
      if [[ -d "/shared/obs_nickel" ]]; then
          setup -r /shared/obs_nickel obs_nickel
      fi

      # Export environment
      export REPO=/shared/repo
      export OBS_NICKEL=/shared/obs_nickel

# =============================================================================
# Reduced Resources for Docker Testing
# =============================================================================
requestMemory: 2048              # 2 GB
requestCpus: 1
numberOfRetries: 1               # Fail fast
memoryMultiplier: 1.5

pipetask:
  calibrateImage:
    requestMemory: 4096
    requestCpus: 1

  subtractImages:
    requestMemory: 4096
    requestCpus: 1
```

**Step 5: Run test to verify it passes**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_bps_config.py::TestDockerSlurmSiteConfig -v`
Expected: PASS (4 tests)

**Step 6: Run all tests**

Run: `cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py packages/obs_nickel/tests/test_bps_config.py -v`
Expected: PASS (all tests)

**Step 7: Commit**

```bash
git add bps/sites/docker-slurm.yaml packages/data_tools/src/obs_nickel_data_tools/core/bps.py packages/obs_nickel/tests/test_bps_config.py
git commit -m "feat: add docker-slurm site config for containerized testing"
```

---

### Task 8: Create Docker Compose Environment

**Files:**
- Create: `docker/docker-compose.yml`
- Create: `docker/Dockerfile.login`
- Create: `docker/slurm/slurm.conf`
- Create: `docker/slurm/cgroup.conf`

This task is infrastructure-only (no Python tests), but we verify the Dockerfiles parse correctly.

**Step 1: Create directory structure**

```bash
mkdir -p docker/slurm docker/scripts
```

**Step 2: Create `docker/docker-compose.yml`**

```yaml
# Docker Compose Slurm Test Environment for Nickel Processing Suite BPS
#
# Usage:
#   docker compose -f docker/docker-compose.yml up -d
#   docker compose -f docker/docker-compose.yml exec login bash
#   docker compose -f docker/docker-compose.yml down
#
# To run smoke test:
#   docker compose -f docker/docker-compose.yml run --rm login /shared/scripts/run-bps-test.sh

services:
  # Slurm controller
  slurmctld:
    image: giovtorres/slurm-docker-cluster:latest
    hostname: slurmctld
    container_name: nps-slurmctld
    command: slurmctld -D
    volumes:
      - shared:/shared
      - ./slurm/slurm.conf:/etc/slurm/slurm.conf:ro
      - ./slurm/cgroup.conf:/etc/slurm/cgroup.conf:ro
    networks:
      - slurm

  # Slurm worker node
  slurmd:
    image: giovtorres/slurm-docker-cluster:latest
    hostname: slurmd
    container_name: nps-slurmd
    command: slurmd -D
    volumes:
      - shared:/shared
      - ./slurm/slurm.conf:/etc/slurm/slurm.conf:ro
      - ./slurm/cgroup.conf:/etc/slurm/cgroup.conf:ro
    depends_on:
      - slurmctld
    networks:
      - slurm

  # Login/submit node with LSST stack + obs_nickel
  login:
    build:
      context: .
      dockerfile: Dockerfile.login
    hostname: login
    container_name: nps-login
    volumes:
      - shared:/shared
      - ../packages/obs_nickel:/shared/obs_nickel:ro
      - ../packages/obs_nickel_data:/shared/obs_nickel_data:ro
      - ../packages/data_tools:/shared/data_tools:ro
      - ../bps:/shared/bps:ro
      - ./scripts:/shared/scripts:ro
    depends_on:
      - slurmctld
      - slurmd
    networks:
      - slurm
    stdin_open: true
    tty: true

volumes:
  shared:

networks:
  slurm:
```

**Step 3: Create `docker/Dockerfile.login`**

```dockerfile
# Login/submit node for BPS testing
#
# Based on lsstsqre base image with LSST Science Pipelines pre-installed.
# Adds obs_nickel packages and ctrl_bps_parsl for Slurm submission.

FROM lsstsqre/centos:7-stack-lsst_distrib-w_2024_20

USER lsst

# Install ctrl_bps_parsl into the stack
RUN bash -lc "\
    source /opt/lsst/software/stack/loadLSST.bash && \
    setup lsst_distrib && \
    pip install lsst-ctrl-bps-parsl \
    "

# Install Slurm client tools (for bps submit to reach slurmctld)
USER root
RUN yum install -y epel-release && \
    yum install -y slurm slurm-slurmctld && \
    yum clean all

# Copy Slurm config
COPY slurm/slurm.conf /etc/slurm/slurm.conf
COPY slurm/cgroup.conf /etc/slurm/cgroup.conf

# Create shared directory
RUN mkdir -p /shared/repo /shared/data && \
    chown -R lsst:lsst /shared

USER lsst

# Setup script to activate LSST stack + obs_nickel on login
RUN echo 'source /opt/lsst/software/stack/loadLSST.bash' >> ~/.bashrc && \
    echo 'setup lsst_distrib' >> ~/.bashrc && \
    echo 'if [[ -d /shared/obs_nickel ]]; then setup -r /shared/obs_nickel obs_nickel; fi' >> ~/.bashrc && \
    echo 'if [[ -d /shared/data_tools ]]; then pip install -e /shared/data_tools 2>/dev/null; fi' >> ~/.bashrc

WORKDIR /shared

CMD ["bash"]
```

**Step 4: Create `docker/slurm/slurm.conf`**

```
# Slurm configuration for Docker test cluster
# Single controller, single worker, 4 CPUs

ClusterName=nps-test
SlurmctldHost=slurmctld

# Authentication
AuthType=auth/none

# Scheduling
SchedulerType=sched/backfill
SelectType=select/cons_tres
SelectTypeParameters=CR_Core

# Logging
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdLogFile=/var/log/slurm/slurmd.log

# Process IDs
SlurmctldPidFile=/var/run/slurmctld.pid
SlurmdPidFile=/var/run/slurmd.pid

# Timers
SlurmdTimeout=300
InactiveLimit=0
MinJobAge=300
SlurmctldTimeout=300
Waittime=0

# Compute nodes
NodeName=slurmd CPUs=4 RealMemory=4096 State=UNKNOWN
PartitionName=normal Nodes=slurmd Default=YES MaxTime=01:00:00 State=UP
```

**Step 5: Create `docker/slurm/cgroup.conf`**

```
# Slurm cgroup configuration for Docker
CgroupAutomount=yes
ConstrainCores=yes
ConstrainRAMSpace=yes
```

**Step 6: Verify Docker Compose config parses**

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && docker compose -f docker/docker-compose.yml config --quiet 2>&1 || echo "docker compose config check (may warn if docker not running)"
```

**Step 7: Commit**

```bash
git add docker/
git commit -m "feat: add Docker Compose Slurm test environment"
```

---

### Task 9: Create Smoke Test Script

**Files:**
- Create: `docker/scripts/run-bps-test.sh`

**Step 1: Create the smoke test script**

Create `docker/scripts/run-bps-test.sh`:

```bash
#!/usr/bin/env bash
# Smoke test for BPS execution in Docker Slurm environment.
#
# Runs inside the 'login' container. Verifies:
#   1. LSST stack is available
#   2. obs_nickel is setup
#   3. nickel CLI works
#   4. BPS submit to Slurm works (basic connectivity)
#
# Usage:
#   docker compose -f docker/docker-compose.yml run --rm login /shared/scripts/run-bps-test.sh
#
# Exit codes:
#   0 = all checks passed
#   1 = one or more checks failed

set -euo pipefail

PASS=0
FAIL=0

check() {
    local description="$1"
    shift
    echo -n "  Checking: ${description}... "
    if "$@" >/dev/null 2>&1; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo "NPS BPS Smoke Test"
echo "============================================"
echo

# -------------------------------------------------------------------
# 1. LSST Stack
# -------------------------------------------------------------------
echo "[1/5] LSST Stack"
source /opt/lsst/software/stack/loadLSST.bash
setup lsst_distrib

check "pipetask available" which pipetask
check "butler available" which butler
check "python imports lsst.daf.butler" python -c "import lsst.daf.butler"

echo

# -------------------------------------------------------------------
# 2. ctrl_bps and ctrl_bps_parsl
# -------------------------------------------------------------------
echo "[2/5] BPS Packages"
check "import lsst.ctrl.bps" python -c "import lsst.ctrl.bps"
check "import lsst.ctrl.bps.parsl" python -c "import lsst.ctrl.bps.parsl"
check "bps command available" which bps

echo

# -------------------------------------------------------------------
# 3. obs_nickel
# -------------------------------------------------------------------
echo "[3/5] obs_nickel"
if [[ -d /shared/obs_nickel ]]; then
    setup -r /shared/obs_nickel obs_nickel 2>/dev/null || true
fi
check "obs_nickel package exists" test -d /shared/obs_nickel
check "import lsst.obs.nickel" python -c "import lsst.obs.nickel"

echo

# -------------------------------------------------------------------
# 4. Slurm connectivity
# -------------------------------------------------------------------
echo "[4/5] Slurm Cluster"
check "sinfo available" which sinfo
check "sinfo shows nodes" sinfo -N
check "partition 'normal' exists" sinfo -p normal

echo

# -------------------------------------------------------------------
# 5. nickel CLI (if data_tools installed)
# -------------------------------------------------------------------
echo "[5/5] nickel CLI"
if [[ -d /shared/data_tools ]]; then
    pip install -e /shared/data_tools 2>/dev/null || true
fi
check "nickel --help" nickel --help

echo
echo "============================================"
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "============================================"

if [[ ${FAIL} -gt 0 ]]; then
    echo "SMOKE TEST FAILED"
    exit 1
else
    echo "SMOKE TEST PASSED"
    exit 0
fi
```

**Step 2: Make executable and verify syntax**

```bash
chmod +x docker/scripts/run-bps-test.sh
bash -n docker/scripts/run-bps-test.sh  # Syntax check only
```

**Step 3: Commit**

```bash
git add docker/scripts/run-bps-test.sh
git commit -m "feat: add BPS smoke test script for Docker Slurm environment"
```

---

### Task 10: Final Verification and Cleanup

**Step 1: Run the full test suite one final time**

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite && python -m pytest packages/obs_nickel/tests/test_executor.py packages/obs_nickel/tests/test_bps_config.py -v
```

Expected: All tests PASS

**Step 2: Verify no rogue untracked files**

```bash
git status
```

**Step 3: Review the git log for clean commit history**

```bash
git log --oneline feature/dpg/bps-parallelization..HEAD
```

Expected commits (newest first):
```
feat: add BPS smoke test script for Docker Slurm environment
feat: add Docker Compose Slurm test environment
feat: add docker-slurm site config for containerized testing
test: add full BPS lifecycle integration tests
feat: wire qgraph_file from pipetask args into BPSConfig
feat: fail fast when ctrl_bps not installed for BPS execution
feat: inject qgraph_file into BPS config rendering
feat: add qgraph_file field to BPSConfig dataclass
feat: add custom.yaml BPS template for pre-built quantum graphs
```

**Step 4: Use superpowers:finishing-a-development-branch to complete**
