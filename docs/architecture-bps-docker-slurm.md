# BPS + Docker + Slurm Architecture Guide

## What Problem Are We Solving?

The Nickel Processing Suite runs astronomical data through the LSST Science Pipelines — a sequence of computationally intensive steps (calibration, astrometry, photometry, image subtraction). A single night of Nickel telescope data has ~20-200 exposures, and a typical campaign has 10-30 nights. Processing all of this serially on one machine is slow.

The BPS (Batch Processing Service) integration distributes the heavy computation across multiple machines using **Slurm** (an HPC job scheduler), orchestrated by **Parsl** (a Python parallel execution framework), all running inside **Docker** containers for reproducibility.

```
┌─────────────────────────────────────────────────────────────┐
│  Your Machine (macOS)                                       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Docker Network                                       │   │
│  │                                                      │   │
│  │  ┌─────────┐    ┌───────────┐    ┌──────────────┐   │   │
│  │  │  MySQL   │───▶│ slurmdbd  │───▶│  slurmctld   │   │   │
│  │  │ (acctg)  │    │ (Slurm DB)│    │ (controller) │   │   │
│  │  └─────────┘    └───────────┘    └──────┬───────┘   │   │
│  │                                         │            │   │
│  │  ┌──────────────────────────────────────┤            │   │
│  │  │                                      │            │   │
│  │  │  ┌────────────┐   ┌────────────┐     │            │   │
│  │  │  │     c1      │   │     c2      │    │            │   │
│  │  │  │ (compute)   │   │ (compute)   │    │            │   │
│  │  │  │  slurmd     │   │  slurmd     │    │            │   │
│  │  │  │  + LSST     │   │  + LSST     │    │            │   │
│  │  │  │  + NPS      │   │  + NPS      │    │            │   │
│  │  │  └────────────┘   └────────────┘     │            │   │
│  │  │       ▲                 ▲             │            │   │
│  │  │       │    Slurm jobs   │             │            │   │
│  │  │       └────────┬────────┘             │            │   │
│  │  │                │                      │            │   │
│  │  │  ┌─────────────┴──────────────────┐   │            │   │
│  │  │  │         nps-hpc                │◀──┘            │   │
│  │  │  │    (login / submit node)       │                │   │
│  │  │  │                                │                │   │
│  │  │  │  stips -c config.yaml run      │                │   │
│  │  │  │    → calibs (LOCAL)            │                │   │
│  │  │  │    → bps submit (science)      │                │   │
│  │  │  │    → bps submit (DIA)          │                │   │
│  │  │  │    → bps submit (fphot)        │                │   │
│  │  │  └────────────────────────────────┘                │   │
│  │  │                                                    │   │
│  │  │  Shared Volumes:                                   │   │
│  │  │    /data/repo    (Butler repository)               │   │
│  │  │    /data/raw     (raw FITS files)                  │   │
│  │  │    /data/refcats (reference catalogs)              │   │
│  │  └────────────────────────────────────────────────────┘   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```


## The Six Containers

The Docker Slurm cluster runs six containers (defined in `docker/docker-compose.slurm.yml`):

| Container | Role | What It Does |
|-----------|------|-------------|
| **mysql** | Database | Stores Slurm accounting records (job history, resource usage) |
| **slurmdbd** | Slurm DB Daemon | Bridges Slurm ↔ MySQL; must start before slurmctld |
| **slurmctld** | Slurm Controller | The "brain" — schedules jobs, manages the queue, allocates nodes |
| **c1** | Compute Node 1 | Runs `slurmd` daemon; executes assigned `pipetask run-qbb` jobs |
| **c2** | Compute Node 2 | Same as c1; provides parallelism |
| **nps-hpc** | Login/Submit Node | Where you run `stips ... run`; submits BPS jobs to Slurm |

All containers share the same Docker network and mount the same data volumes, so they all see the same `/data/repo`, `/data/raw`, and `/data/refcats` directories.

### Why All These Containers?

Slurm is designed for multi-machine clusters. Even in Docker, it needs the full stack:
- **MySQL + slurmdbd**: Slurm refuses to start without accounting. These provide it.
- **slurmctld**: The scheduler. It decides which compute node runs which job.
- **c1, c2**: The workers. In production HPC, these would be physical servers with many cores.
- **nps-hpc**: The login node. This is where the pipeline orchestrator runs. It submits jobs but doesn't execute them.

### Authentication: Munge

All Slurm containers need to trust each other. They use **Munge** — a shared-key authentication system. A random key is generated at build time and shared via a Docker volume (`munge-etc`). Each container copies this key and starts a `munged` daemon. If Munge isn't running or the key doesn't match, Slurm commands fail with cryptic auth errors.


## The Execution Model: Two Paths

The pipeline orchestrator (`stips ... run`) processes data through stages: calibs → science → DIA → fphot → lightcurve. Each stage calls `pipetask` commands. The key architectural choice is **how** those commands execute:

```
                  stips -c config.yaml run
                         │
              ┌──────────┴──────────┐
              │    options:          │
              │      execution: bps  │
              │      site: docker-slurm
              └──────────┬──────────┘
                         │
           ┌─────────────┼─────────────┐
           │             │             │
     ┌─────┴─────┐ ┌────┴────┐  ┌─────┴─────┐
     │  CALIBS   │ │ SCIENCE │  │  DIA/FPHOT │
     │  (local)  │ │  (BPS)  │  │   (BPS)    │
     └─────┬─────┘ └────┬────┘  └─────┬─────┘
           │             │             │
    subprocess      bps submit     bps submit
    on nps-hpc      → Parsl        → Parsl
                    → Slurm        → Slurm
                    → c1/c2        → c1/c2
```

### Path 1: Local Execution (Calibrations)

Calibrations (bias, flat, defects) are **small** pipelines — typically 5-17 quanta. The overhead of BPS submission (rendering configs, Slurm scheduling, Parsl worker startup, LSST env activation on compute nodes) exceeds the actual computation time. So calibs **always run locally** on the submit node via subprocess.

```python
# In core/calibs.py — defaults to LocalExecutor
executor = executor or LocalExecutor()
```

The `LocalExecutor` simply wraps `pipetask run` in a shell that sources the LSST stack:

```bash
source /opt/lsst/software/stack/loadLSST.bash
setup lsst_distrib
setup -r /opt/nps/packages/obs_stips obs_stips
export INSTRUMENT_DIR=/opt/nps/instruments/nickel
pipetask run -b /data/repo -g /path/to/qgraph.qg -j 4
```

### Path 2: BPS Execution (Science, DIA, Forced Photometry)

Science processing (astrometry, photometry per exposure) can have **dozens of quanta** per night, and across 22 nights that's hundreds of independent tasks. These benefit from parallel execution on multiple nodes.

The `BPSExecutor` intercepts `pipetask` commands and routes them differently:

```
pipetask qgraph ...  →  Still runs locally (fast, needed for validation)
pipetask run ...     →  Routed through BPS → Parsl → Slurm
```

This split is critical: quantum graph *generation* (planning what to do) must happen locally so the orchestrator can inspect it, check for empty graphs, validate inputs, etc. Only the *execution* (actually running the compute) goes to the cluster.


## BPS: The Glue Between NPS and Slurm

**BPS (Batch Processing Service)** is LSST's abstraction layer for submitting pipetask work to HPC schedulers. NPS doesn't talk to Slurm directly — it talks to BPS, which talks to Parsl, which talks to Slurm.

### The BPS Submission Flow

```
┌─────────────────────────────────────────────────────────┐
│ NPS Orchestrator (run.py)                               │
│                                                         │
│  1. Build quantum graph (local pipetask qgraph)         │
│  2. executor.run_pipetask(["run", ...])                 │
│     ↓                                                   │
│  BPSExecutor._submit_and_poll()                         │
│     ↓                                                   │
│  3. render_bps_config()                                 │
│     - Load template: bps/pipelines/custom.yaml          │
│     - Load site config: bps/sites/docker-slurm.yaml     │
│     - Substitute variables: {repo}, {night}, {band}...  │
│     - Write rendered YAML to submit directory            │
│     ↓                                                   │
│  4. bps.submit(rendered_config)                         │
│     ↓                                                   │
│  run_with_stack(["bps", "submit", rendered.yaml])       │
│     ↓                                                   │
└─────┬───────────────────────────────────────────────────┘
      │
      │  (inside LSST stack environment)
      ▼
┌─────────────────────────────────────────────────────────┐
│ ctrl_bps (LSST BPS Framework)                           │
│                                                         │
│  5. Parse BPS config YAML                               │
│  6. Cluster quantum graph into jobs                     │
│  7. Translate to Parsl workflow                          │
│  8. Submit Parsl workflow                                │
│     ↓                                                   │
└─────┬───────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│ Parsl (Python Parallel Execution)                       │
│                                                         │
│  9. Start HTEX interchange process                      │
│  10. Request Slurm allocation (sbatch)                  │
│  11. Wait for worker pool to start on allocated nodes   │
│      ↓                                                  │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│ Slurm                                                   │
│                                                         │
│  12. slurmctld allocates c1 (or c2)                     │
│  13. slurmd on c1 starts Parsl worker pool              │
│  14. Worker pool receives tasks from interchange         │
│      ↓                                                  │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│ Compute Node (c1 or c2)                                 │
│                                                         │
│  15. For each quantum:                                  │
│      a. Shell setup (commandPrefix):                    │
│         source loadLSST.bash                            │
│         setup lsst_distrib                              │
│         setup -r .../obs_stips obs_stips                │
│         export INSTRUMENT_DIR=.../instruments/nickel    │
│         export REPO=/data/repo ...                      │
│                                                         │
│      b. Execute:                                        │
│         pipetask run-qbb /data/repo /path/to/qgraph.qg │
│           --qgraph-node-id {quantum-uuid}               │
│                                                         │
│  16. Results written to /data/repo (shared volume)      │
│      ↓                                                  │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│ Back on nps-hpc                                         │
│                                                         │
│  17. Parsl detects all tasks complete                    │
│  18. BPS runs "finalJob" (aggregate-graph):             │
│      - Ingests quantum execution results into Butler    │
│  19. bps submit returns (exit code 0 or non-zero)       │
│  20. NPS orchestrator parses result, continues pipeline  │
└─────────────────────────────────────────────────────────┘
```

### Key Concept: `bps submit` Blocks

With the Parsl backend, `bps submit` is a **blocking call**. It doesn't return until all quanta have finished executing on the compute nodes. This simplifies the orchestrator — it just waits for the return code instead of polling.

### Key Concept: `pipetask run-qbb`

On the compute nodes, each quantum runs via `pipetask run-qbb` (Quantum-Backed Butler), not `pipetask run`. The difference:

- `pipetask run`: Reads the full quantum graph, finds matching quanta, executes them
- `pipetask run-qbb`: Executes exactly ONE quantum (identified by `--qgraph-node-id`), using pre-baked datastore records

This is more efficient for distributed execution — each compute node only loads what it needs.


## BPS Configuration: Three Layers

BPS configs are YAML files organized in three layers, each including the next:

```
bps/pipelines/science.yaml          ← What to process
  └── includes: ../sites/slurm.yaml  ← Where to run it
        └── includes: ../base.yaml   ← Resource defaults
```

### Layer 1: base.yaml (Resource Defaults)

Shared across all pipelines and sites. Sets sensible defaults:

```yaml
# Resource defaults
requestMemory: 4096        # 4 GB per quantum
requestCpus: 1
requestDisk: 10240         # 10 GB scratch
numberOfRetries: 3         # Retry on failure
memoryMultiplier: 2.0      # Double memory on OOM retry
memoryLimit: 32768         # Cap at 32 GB

# Logging
pipetask:
  pipetaskArgs: "--long-log --log-level INFO"

# Quantum clustering: one quantum per job
# (prevents one failure from cascading to co-clustered quanta)
```

### Layer 2: Site Configs (Where to Run)

Each compute environment gets its own config:

**docker-slurm.yaml** (our Docker test cluster):
```yaml
computeSite: docker-slurm
wmsServiceClass: lsst.ctrl.bps.parsl.ParslService
parsl:
  provider: SlurmProvider
  nodes_per_block: 1
  cores_per_node: 4
  mem_per_node: 4           # GB — conservative for Docker
  walltime: "00:30:00"
  max_blocks: 1
  commandPrefix: |
    source /opt/lsst/software/stack/loadLSST.bash
    setup lsst_distrib
    setup -r /opt/nps/packages/obs_stips obs_stips 2>/dev/null || true
    export REPO=/data/repo
    export INSTRUMENT_DIR=/opt/nps/instruments/nickel
    ...
```

**slurm.yaml** (production HPC):
```yaml
computeSite: slurm
parsl:
  nodes_per_block: 1
  cores_per_node: 32        # Full HPC node
  mem_per_node: 128         # 128 GB
  walltime: "04:00:00"      # 4 hours
  max_blocks: 10            # Up to 10 parallel Slurm jobs
```

The `commandPrefix` is critical — it's the shell code that runs **on each compute node** before every quantum. It sets up the LSST environment and exports paths so `pipetask run-qbb` can find everything.

### Layer 3: Pipeline Configs (What to Process)

Each pipeline type defines its inputs, outputs, and data queries:

**science.yaml**:
```yaml
pipelineYaml: "{instrument_dir}/pipelines/DRP.yaml#calibrateImage"
inputCollections: "Nickel/raw/{night}/*,Nickel/calib/current,refcats"
outputRun: "Nickel/runs/{night}/processCcd/{timestamp}/run"
dataQuery: "instrument='Nickel' AND exposure.observation_type='science'"
```

**custom.yaml** (used by BPSExecutor for pre-built quantum graphs):
```yaml
# Special: uses pre-built qgraph file instead of generating one
qgraphFile: "{qgraph_file}"
outputRun: "{output_run}"    # Preserves collection names from qgraph
```

Variables like `{night}`, `{repo}`, `{instrument_dir}` (and `{obs_stips_dir}`) are substituted at submission time by `render_bps_config()`.


## The Code: Key Modules

### executor.py — The Routing Layer

```python
class PipetaskExecutor(Protocol):
    def run_pipetask(self, args, config, **kwargs) -> CompletedProcess: ...

class LocalExecutor:
    """Direct subprocess execution on the current machine."""
    def run_pipetask(self, args, config, **kwargs):
        return stack.run_pipetask(args, config, **kwargs)

class BPSExecutor:
    """Routes pipetask commands through BPS → Parsl → Slurm."""
    def run_pipetask(self, args, config, **kwargs):
        subcommand = args[0]   # "qgraph" or "run"

        if subcommand != "run":
            # qgraph generation stays local
            return stack.run_pipetask(args, config, **kwargs)

        # Extract qgraph file and output run from args
        qgraph_file, output_run = _parse_pipetask_args(args)

        # Submit through BPS
        return self._submit_and_poll(qgraph_file, output_run, config)
```

### bps.py — Config Rendering and Submission

```python
def render_bps_config(bps_cfg, config, output_dir) -> Path:
    """Turn a template BPS config into a concrete, ready-to-submit YAML."""
    template = find_bps_config(bps_cfg.pipeline, config)
    variables = {
        "repo": str(config.repo),
        "night": bps_cfg.night,
        "instrument_dir": str(config.instrument_dir),
        "obs_stips_dir": str(config.obs_stips_dir),
        "computeSite": bps_cfg.site,
        # ... etc
    }
    rendered = template.read_text()
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    # Also renders base.yaml and site config into submit directory
    return output_file

def submit(bps_cfg, config) -> BPSResult:
    """Run `bps submit` inside the LSST stack environment."""
    rendered_config = render_bps_config(bps_cfg, config, submit_dir)
    result = run_with_stack(["bps", "submit", str(rendered_config)], config)
    return BPSResult(success=result.returncode == 0, ...)
```

### run.py — The Orchestrator

```python
def _create_executor(run_cfg) -> PipetaskExecutor:
    """Factory: select executor based on YAML config."""
    if run_cfg.execution == "bps":
        return BPSExecutor(site=run_cfg.site, ...)
    return LocalExecutor()

# In the main pipeline flow:
executor = _create_executor(run_cfg)

# Step 1: Bootstrap (always local)
_run_bootstrap(...)

# Step 2: Calibrations (ALWAYS local — too small for BPS overhead)
_run_calibs_step(all_nights, ...)  # No executor passed → LocalExecutor

# Step 3: Science (through executor — BPS if configured)
for night in nights:
    science.run(night, config, executor=executor)  # → BPS

# Step 4: DIA (through executor)
for night, band in night_band_pairs:
    dia.run(night, band, config, executor=executor)  # → BPS

# Step 5: Forced photometry (through executor)
# Step 6: Lightcurve extraction (always local — just reads Butler)
```


## Shared Filesystem: Why It Matters

All containers mount the same Docker volumes:

```yaml
volumes:
  - nps-repo:/data/repo        # Butler repository (SQLite + FITS)
  - nps-raw:/data/raw          # Raw telescope data
  - nps-refcats:/data/refcats  # Reference catalogs
```

This is critical because:

1. **nps-hpc** writes quantum graphs to `/data/repo/qgraphs/`
2. **c1/c2** read those quantum graphs during `run-qbb`
3. **c1/c2** write output datasets back to `/data/repo/`
4. **nps-hpc** reads those outputs when checking results

Without a shared filesystem, BPS would need a separate data transfer mechanism. In a real HPC cluster, this role is filled by NFS or a parallel filesystem like Lustre.


## Critical Implementation Details

### 1. `--qgraph-datastore-records` (Most Common Failure)

When building quantum graphs for BPS execution, you **must** include `--qgraph-datastore-records`:

```bash
pipetask qgraph \
  -b /data/repo \
  --qgraph-datastore-records \  # ← THIS IS CRITICAL
  -o output_collection \
  ...
```

Without this flag, the quantum graph lacks information about where input files live on disk. When `run-qbb` tries to execute on a compute node, it can't find the reference catalogs, calibrations, or science images. The error is usually a cryptic missing-dataset failure.

### 2. `doLinearize: false` for Nickel

BPS `run-qbb` doesn't attach detector metadata to Nickel's single-extension FITS files the same way direct execution does. This causes `detector=None` in the ISR task, which crashes when trying to look up linearization curves. Since Nickel doesn't need linearization, the fix is to disable it in all pipeline definitions.

### 3. `outputRun` Preservation

By default, BPS renames output collections to `u/{operator}/{payloadName}/{timestamp}`. Our pipeline builds quantum graphs with specific output collection names (e.g., `Nickel/runs/20230519/processCcd/.../run`). The `custom.yaml` template sets `outputRun: "{output_run}"` to preserve these names.

### 4. Calibrations Must Run Locally

Calibration pipelines are small (17 quanta for bias, 5 for flat). The BPS overhead (Slurm scheduling + Parsl worker startup + LSST env activation per node) easily exceeds the actual computation. In testing, BPS-routed calibrations took longer and sometimes caused race conditions with the orchestrator. The fix: `_run_calibs_step()` never receives an executor, so it always falls back to `LocalExecutor`.


## How to Operate the Docker Cluster

### Starting the Cluster

```bash
cd nickel_processing_suite/.worktrees/bps-full

# Build images
docker build -t nps:latest -f docker/Dockerfile .
docker build -t nps-slurm:latest -f docker/Dockerfile.slurm .

# Start all 6 containers
docker compose -f docker/docker-compose.slurm.yml up -d

# Verify Slurm is healthy
docker exec nps-hpc sinfo
# Expected: c1 and c2 in "idle" state
```

### Running the Pipeline

```bash
# Interactive (see output in terminal)
docker exec -it nps-hpc bash -c '
  source /opt/lsst/software/stack/loadLSST.bash
  setup lsst_distrib
  setup -r /opt/nps/packages/obs_stips obs_stips 2>/dev/null || true
  export INSTRUMENT_DIR=/opt/nps/instruments/nickel
  export PYTHONPATH=/opt/nps/packages/stips/src:${PYTHONPATH:-}
  python -m stips.cli run \
    /opt/nps/scripts/config/2023ixf/pipeline_docker_bps_test.yaml
'

# Background (detached)
docker exec -d nps-hpc bash -c '
  source /opt/lsst/software/stack/loadLSST.bash
  ...same as above...
' > /tmp/pipeline.log 2>&1
```

### Monitoring

```bash
# Pipeline orchestrator log
docker exec nps-hpc tail -f /opt/nps/logs/{RUN_ID}/pipeline.log

# Slurm job queue
docker exec nps-hpc squeue

# What's running on compute nodes
docker exec c1 ps aux | grep pipetask
docker exec c2 ps aux | grep pipetask

# BPS submit directories (rendered configs, per-quantum logs)
docker exec nps-hpc ls /data/repo/bps/submit/

# Butler collections (what's been processed)
docker exec nps-hpc bash -c '
  source /opt/lsst/software/stack/loadLSST.bash
  setup lsst_distrib
  butler query-collections /data/repo
'

# Per-night calibration logs
docker exec nps-hpc ls /opt/nps/logs/{RUN_ID}/calibs/

# Per-night science logs (once science starts)
docker exec nps-hpc ls /opt/nps/logs/{RUN_ID}/science/
```

### Troubleshooting

**Slurm nodes stuck in "alloc" after killing jobs:**
```bash
docker exec nps-hpc scontrol update NodeName=c1 State=idle
docker exec nps-hpc scontrol update NodeName=c2 State=idle
```

**Munge authentication errors:**
```bash
# Check munge is running on all nodes
docker exec nps-hpc bash -c 'munge -n | unmunge'
docker exec c1 bash -c 'munge -n | unmunge'
```

**BPS submit fails with FileExistsError:**
The submit directory already exists from a previous run. Either clean it up or ensure timestamps differ:
```bash
docker exec nps-hpc rm -rf /data/repo/bps/submit/custom_*
```

**Clean restart (wipe everything):**
```bash
docker exec nps-hpc rm -rf /data/repo/*
docker exec nps-hpc rm -rf /data/repo/bps /data/repo/parsl_runinfo
# Then re-run bootstrap + pipeline
```


## How It Compares to Local Execution

| Aspect | Local (`execution: local`) | BPS (`execution: bps`) |
|--------|--------------------------|----------------------|
| Calibrations | subprocess on your machine | subprocess on nps-hpc (same) |
| Science | subprocess, -j N threads | Distributed across c1, c2 via Slurm |
| DIA | subprocess, -j N threads | Distributed across c1, c2 via Slurm |
| Parallelism | Limited by one machine's cores | Scales with compute nodes |
| Overhead | None | ~30-60s per BPS submission (Slurm + Parsl startup) |
| Best for | 1-3 nights, development | 10+ nights, production runs |
| Failure mode | Direct error in terminal | Errors in BPS submit dir logs |


## File Reference

```
bps/
├── base.yaml                    # Resource defaults, retry policy, logging
├── pipelines/
│   ├── calibs.yaml              # Bias + flat pipeline definition
│   ├── science.yaml             # CalibrateImage pipeline definition
│   ├── dia.yaml                 # Difference imaging pipeline definition
│   ├── fphot.yaml               # Forced photometry pipeline definition
│   └── custom.yaml              # Pre-built quantum graph (used by BPSExecutor)
└── sites/
    ├── docker-slurm.yaml        # Docker test cluster (conservative resources)
    ├── slurm.yaml               # Production HPC cluster
    ├── local.yaml               # Parsl ThreadPool (development)
    └── htcondor.yaml            # HTCondor cluster

docker/
├── Dockerfile                   # NPS container (LSST + packages + Slurm client)
├── Dockerfile.slurm             # Slurm service container (controller + compute)
├── docker-compose.yml           # Single-container development
├── docker-compose.slurm.yml     # Full 6-container Slurm cluster
├── entrypoint.sh                # Container init (LSST setup, Munge, env validation)
└── scripts/
    └── run-bps-test.sh          # Cluster readiness smoke test

packages/stips/src/stips/core/
├── executor.py                  # LocalExecutor + BPSExecutor
├── bps.py                       # BPSConfig, render, submit, status, cancel
├── stack.py                     # LSST stack activation, pipetask/butler wrappers
└── run.py                       # YAML orchestrator (executor factory, stage dispatch)

scripts/config/2023ixf/
└── pipeline_docker_bps_test.yaml  # 22-night BPS test config (container paths)
```
