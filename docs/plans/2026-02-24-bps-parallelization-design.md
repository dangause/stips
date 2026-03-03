# BPS Parallelization Design

**Date:** 2026-02-24
**Status:** Approved
**Approach:** Executor Abstraction Layer with concurrent cross-night dispatch (~910 lines across 11 files)

## Motivation

The Nickel Processing Suite orchestrator (`nickel run`) processes pipeline stages sequentially: each night completes before the next begins, and within DIA/fphot, each band completes before the next. For campaigns with 20-30 science nights, this means the pipeline runs end-to-end without exploiting the inherent independence between nights.

Additionally, the codebase already contains a BPS module (`core/bps.py`) with submit/status/cancel functions, site configs (Slurm, HTCondor, Local), and pipeline-specific resource overrides — but this infrastructure is only accessible via the standalone `nickel bps submit` CLI, not wired into the `nickel run` orchestrator.

This design integrates BPS execution into the orchestrator and adds cross-night parallelism, enabling:
- Processing multiple nights simultaneously
- Cluster execution via Slurm/HTCondor
- BPS retry/memory-scaling robustness features
- All three execution environments (local, Slurm, HTCondor)

## Goals

1. **Wire up existing BPS code** into the `nickel run` orchestrator
2. **Enable cross-night parallelism** — process N nights simultaneously per stage
3. **BPS robustness features** — per-quantum retries, automatic memory scaling on OOM
4. **Support local/Slurm/HTCondor** execution environments

## Design

### 1. Executor Protocol — Core Abstraction

**New file: `core/executor.py` (~250 lines)**

The executor abstraction replaces `stack.run_pipetask()` calls inside stage modules. Stage-level logic (fallbacks, validation, certification) is preserved unchanged.

```python
from typing import Protocol

class PipetaskExecutor(Protocol):
    """Abstraction over how pipetask commands are executed."""
    def run_pipetask(self, args: list[str], config: Config, **kwargs) -> CompletedProcess: ...
```

#### LocalExecutor

Direct passthrough to the current `stack.run_pipetask()`:

```python
class LocalExecutor:
    """Current behavior — direct subprocess calls via run_with_stack()."""
    def run_pipetask(self, args, config, **kwargs):
        return stack.run_pipetask(args, config, **kwargs)
```

Zero behavior change from current code. This is the default.

#### BPSExecutor

Wraps `bps.submit()` + poll for completion:

```python
class BPSExecutor:
    """BPS-based execution with retries and monitoring."""
    def __init__(self, site: str = "local", poll_interval: float = 5.0, timeout: float = 7200.0):
        self.site = site
        self.poll_interval = poll_interval
        self.timeout = timeout

    def run_pipetask(self, args, config, **kwargs):
        subcommand = args[0]  # "qgraph" or "run"

        if subcommand == "qgraph":
            # QGraph generation is fast (query planning, no data processing).
            # Always run locally to preserve empty-qgraph validation in stage modules.
            return stack.run_pipetask(args, config, **kwargs)

        elif subcommand == "run":
            # 1. Parse args to extract qgraph file, collections, etc.
            # 2. Build BPSConfig from parsed args + self.site
            # 3. Render BPS config with qgraphFile: <pre-built.qg>
            # 4. Submit via bps.submit()
            # 5. Poll via bps.status() with exponential backoff
            # 6. Map BPS result to CompletedProcess
            ...
```

**Why qgraph runs locally:** Stage modules generate quantum graphs, then check for empty graphs (dia.py's "no quanta" detection) or inspect graph contents. These checks happen between qgraph generation and pipeline execution. By running qgraph locally and only routing the "run" subcommand to BPS, all existing validation logic works unchanged.

**BPS config uses pre-built qgraph:** The locally-generated `.qg` file is passed to BPS via `qgraphFile:` in the rendered config. This means:
- BPS skips its "Acquire" phase (no duplicate graph generation)
- Output collection names are baked into the qgraph, matching the existing naming convention exactly
- Butler collections are populated identically to local execution

### 2. BPSExecutor: Submit + Poll Lifecycle

When a stage module calls `executor.run_pipetask(["run", ...])`:

**Step 1: Parse pipetask args** — Extract repo, qgraph file, jobs count, input/output collections from the args list.

**Step 2: Build BPSConfig** — Map parsed args to the existing `BPSConfig` dataclass plus inject the pre-built qgraph path.

**Step 3: Render and submit** — Use existing `bps.render_bps_config()` and `bps.submit()`. The rendered config includes `qgraphFile:` pointing to the pre-built graph.

**Step 4: Poll with exponential backoff**
```python
poll_interval = self.poll_interval  # Start at 5 seconds
max_interval = 60.0                 # Cap at 1 minute
start = time.monotonic()
while time.monotonic() - start < self.timeout:
    status = bps.status(bps_result.run_id, config)
    if status.get("state") in ("SUCCEEDED", "FAILED", "DELETED"):
        break
    time.sleep(poll_interval)
    poll_interval = min(poll_interval * 1.5, max_interval)
```

**Step 5: Map BPS result to CompletedProcess**

Stage modules expect `CompletedProcess` with `returncode` and `stdout`. The BPSExecutor translates:

```python
def _translate_bps_result(self, bps_status: dict) -> CompletedProcess:
    state = bps_status.get("state", "UNKNOWN")
    quanta_ok = bps_status.get("succeeded", 0)
    quanta_fail = bps_status.get("failed", 0)

    returncode = 0 if state == "SUCCEEDED" else 1

    # Format stdout to match _parse_quanta_summary() expectations
    stdout = (
        f"Executed {quanta_ok} quanta successfully, "
        f"{quanta_fail} failed out of total {quanta_ok + quanta_fail}"
    )

    return CompletedProcess(args=["bps"], returncode=returncode, stdout=stdout, stderr="")
```

#### BPS Report Parsing

The `bps report` command produces tabular output:
```
X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED    ...
summary    SUCCEEDED          12           12         0    ...
```

The BPSExecutor parses this into a structured dict with `state`, `succeeded`, `failed` counts, which are then mapped to the `CompletedProcess` format above.

#### Partial Failure Semantics

| BPS State | Quanta | Maps To | Orchestrator Effect |
|-----------|--------|---------|-------------------|
| SUCCEEDED | all OK, 0 failed | returncode=0 | Stage success |
| FAILED | some OK, some failed | returncode=1, quanta_ok>0 | Partial success (stage module decides) |
| FAILED | 0 OK, all failed | returncode=1, quanta_ok=0 | Stage failure |
| DELETED | N/A | returncode=1 | Job cancelled |

BPS's retry features (`numberOfRetries: 3`, `memoryMultiplier: 2.0` from existing `bps/base.yaml`) mean BPS mode may produce fewer partial failures than local mode — quanta that OOM locally get retried with more memory.

#### Collection Naming

BPS writes to the same Butler collections as local execution because:
- Output collection names are baked into the pre-built qgraph (via `--output` and `--output-run` flags during local qgraph generation)
- BPS executes the pre-built qgraph without overriding collection names
- `outputRun` in BPS YAML is only used when BPS generates its own qgraph (which we skip)

All downstream consumers (DIA, fphot, lightcurve extraction) work unchanged.

#### Log File Integration

BPS creates per-quantum logs in `{submit_dir}/logging/`. After job completion, the BPSExecutor appends the BPS submit_dir path to the stage log file:
```
BPS job completed: run_id=<id>, state=SUCCEEDED, logs at: /path/to/submit_dir/logging/
```

This preserves the existing `logs/{RUN_ID}/{stage}/` structure while providing a pointer to BPS-level detail.

### 3. Cross-Night Concurrent Dispatch

**New utility in `core/run.py`:**

```python
def _dispatch_concurrent(fn, items, *, max_workers=4, item_label="night"):
    """Run fn(item) concurrently for each item. Returns {item: result}."""
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

Each orchestrator step function gains concurrent dispatch:

```python
def _run_calibs_step(all_nights, run_cfg, config, result, executor, dry_run):
    if run_cfg.concurrent_nights > 1:
        night_results = _dispatch_concurrent(
            lambda night: calibs.run(night, config, jobs=run_cfg.jobs, executor=executor),
            all_nights,
            max_workers=run_cfg.concurrent_nights,
        )
        for night in all_nights:
            if night_results.get(night) is None or not night_results[night].success:
                result.failed_calibs.append(night)
    else:
        # Sequential: current behavior (default)
        for night in all_nights:
            calib_result = calibs.run(night, config, jobs=run_cfg.jobs, executor=executor)
            if not calib_result.success:
                result.failed_calibs.append(night)
```

#### Dependency-Aware Scheduling

Cross-night dependencies don't exist within a pipeline stage — night A's calibs don't depend on night B's calibs. The dependency chain is:

```
Calibs(night) → Science(night) → DIA(night, band) → Fphot(night, band)
```

Since the orchestrator already processes stages in order (all calibs → all science → all DIA → all fphot), cross-night independence is guaranteed:

| Stage | Parallelized Across | Constraint |
|-------|-------------------|------------|
| Calibs | All nights | None (independent) |
| Science | All nights | Skips failed calibs nights |
| DIA | All nights × bands | Skips failed science nights; requires template |
| Fphot | All nights × bands | Skips failed DIA night/bands |
| Templates | Per-band | Must complete before DIA |

#### Concurrency + BPS Interaction

| Mode | Cross-night | Within-night |
|------|------------|-------------|
| Local, sequential | For loop | `pipetask run -j {jobs}` |
| Local, concurrent | ThreadPoolExecutor | `pipetask run -j {jobs}` |
| BPS Local (Parsl) | ThreadPoolExecutor of submissions | Parsl ThreadPool per job |
| BPS Slurm/HTCondor | ThreadPoolExecutor of submissions | Cluster resources per job |

For BPS cluster modes, the ThreadPoolExecutor is lightweight — it just submits + polls. The heavy computation is on the cluster.

### 4. RunConfig Extension

**New fields:**

```python
# In RunConfig dataclass:
execution: str = "local"           # "local" | "bps"
site: str = "local"                # "local" | "slurm" | "htcondor"
concurrent_nights: int = 0         # 0 = sequential (default)
bps_poll_interval: float = 5.0     # Seconds between BPS status checks
bps_timeout: float = 7200.0        # Per-stage BPS timeout in seconds (2 hours)
```

**YAML config:**

```yaml
options:
  execution: bps
  site: slurm
  concurrent_nights: 4
  bps_poll_interval: 10.0
  bps_timeout: 7200
```

**Validation:**
- `execution: bps` requires BPS + site plugin to be importable
- `execution: local` ignores `site` (uses direct pipetask)
- `concurrent_nights: 0` means sequential (backward compatible default)
- `--site slurm` CLI flag implies `execution: bps`

### 5. CLI Changes

```bash
# New flags on `nickel run`:
nickel run config.yaml --site slurm           # BPS with Slurm
nickel run config.yaml --site htcondor        # BPS with HTCondor
nickel run config.yaml --site local           # BPS with Parsl Local
nickel run config.yaml --concurrent 4         # 4 nights in parallel (local execution)
nickel run config.yaml --site slurm --concurrent 8  # BPS Slurm + 8 concurrent submissions
```

`--site` overrides the YAML `site` field. Any `--site` value implies `execution: bps`.
`--concurrent` overrides the YAML `concurrent_nights` field.

### 6. Executor Factory

```python
def _create_executor(run_cfg: RunConfig) -> PipetaskExecutor:
    """Create the appropriate executor from RunConfig."""
    if run_cfg.execution == "bps":
        return BPSExecutor(
            site=run_cfg.site,
            poll_interval=run_cfg.bps_poll_interval,
            timeout=run_cfg.bps_timeout,
        )
    return LocalExecutor()
```

Created once in `run()` and passed to all stage step functions.

## What Does NOT Change

| Component | Why No Changes Needed |
|-----------|----------------------|
| `core/calibs.py` internal logic | Gains `executor` param; certification, partial failure handling unchanged |
| `core/science.py` fallback logic | Gains `executor` param; primary/fallback retry loop unchanged |
| `core/dia.py` validation | Gains `executor` param; empty qgraph check, diff_count validation unchanged |
| `core/fphot.py` collection discovery | Gains `executor` param; verification logic unchanged |
| `core/coadd.py` | Not BPS-managed (Python-level Butler operations) |
| `core/lightcurve.py` | Post-processing, no pipetask calls |
| `core/period.py` / `core/transit.py` | Post-processing, no pipetask calls |
| `core/pipeline.py` | Shared utilities, no execution |
| All pipeline YAMLs (DRP, DIA, ForcedPhot) | Target-type agnostic |
| All existing campaign configs | Backward compatible (defaults: local, sequential) |
| Butler collections | Same naming regardless of execution mode |
| Existing `nickel bps submit` CLI | Standalone BPS commands remain for ad-hoc use |
| `bps/` config directory | Existing site/pipeline configs reused |
| Log directory structure | Preserved (`logs/{RUN_ID}/{stage}/`) |

## Complete Change Summary

| File | Change Type | Lines | Description |
|------|------------|-------|-------------|
| `core/executor.py` | **New** | ~250 | PipetaskExecutor protocol, LocalExecutor, BPSExecutor |
| `core/run.py` | Modified | ~80 | RunConfig fields, executor factory, `_dispatch_concurrent()`, concurrent step functions |
| `core/bps.py` | Modified | ~40 | Enhanced `_parse_bps_report()`, better status parsing |
| `core/calibs.py` | Modified | ~5 | Add `executor` parameter, pass to `run_pipetask` calls |
| `core/science.py` | Modified | ~10 | Add `executor` parameter, pass to `run_pipetask` calls |
| `core/dia.py` | Modified | ~5 | Add `executor` parameter, pass to `run_pipetask` calls |
| `core/fphot.py` | Modified | ~5 | Add `executor` parameter, pass to `run_pipetask` calls |
| `cli.py` | Modified | ~10 | Add `--site` and `--concurrent` flags to `nickel run` |
| `tests/test_executor.py` | **New** | ~300 | Unit tests for executor protocol + BPS result mapping |
| `tests/test_run_concurrent.py` | **New** | ~200 | Concurrent dispatch tests |
| Example YAML configs | Modified | ~5 | Add execution config examples in comments |
| **Total** | | **~910** | |

## Stage Module Change Pattern

Each stage module (`calibs.py`, `science.py`, `dia.py`, `fphot.py`) follows the same minimal change:

```python
# Function signature gains executor parameter:
def run(night, config, *, jobs=8, executor=None, ...):
    if executor is None:
        executor = LocalExecutor()

    # All run_pipetask() calls become:
    result = executor.run_pipetask(args, config, ...)
    # Instead of:
    # result = run_pipetask(args, config, ...)
```

Butler calls (`run_butler`, `run_butler_query`) remain direct — only pipetask execution is abstracted.

## Example YAML Config

```yaml
# Full pipeline with BPS + concurrent execution
options:
  jobs: 6
  execution: bps
  site: slurm
  concurrent_nights: 4
  bps_timeout: 7200
  continue_on_error: true
```

```yaml
# Local concurrent (no BPS, just ThreadPoolExecutor)
options:
  jobs: 4
  concurrent_nights: 3
```

```yaml
# Default: current behavior (backward compatible)
options:
  jobs: 6
```

## Future: BPS-Driven Mode

This design is compatible with a future BPS-driven mode where the entire campaign is expressed as a single BPS workflow DAG. The executor abstraction cleanly separates "what to run" from "how to run it", making it possible to add a `CampaignBPSExecutor` that generates a multi-stage workflow without changing stage modules.

This is deferred because expressing the orchestrator's campaign logic (fallback configs, per-band iteration, partial failure tracking, lightcurve extraction) as BPS DAG constraints is a significant separate project.
