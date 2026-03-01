# Full BPS Implementation Design

## Goal

Close the remaining gaps in the BPS executor pipeline so that `nickel run config.yaml --site local` works end-to-end with LSST's ctrl_bps_parsl, then build a Docker Compose Slurm environment for cluster-level testing.

## Current State

The BPS infrastructure is ~85-90% complete on `feature/dpg/bps-parallelization`:

- **Complete:** PipetaskExecutor protocol, LocalExecutor, BPSExecutor with submit/poll lifecycle, BPS YAML templates (base + 3 sites + 4 pipelines), RunConfig execution fields, executor factory, cross-night concurrent dispatch, CLI flags (`--site`, `--concurrent`), 42 unit tests passing, stage module wiring (executor param in calibs/science/dia/fphot)
- **Gaps:** Pre-built qgraph injection into BPS config, `custom.yaml` template, ctrl_bps availability check, real-data validation with Parsl Local, Docker Slurm test environment

## Architecture

Two phases, one branch (`feature/dpg/bps-full` off `feature/dpg/bps-parallelization`):

### Phase A — Parsl Local (close the gaps)

1. **Qgraph injection** — Add `qgraphFile:` support to `render_bps_config()` + create `custom.yaml` BPS template
2. **ctrl_bps availability check** — Fail fast with clear error at executor creation
3. **Parsl Local validation** — End-to-end test with real 2023ixf data

Data flow:
```
nickel run config.yaml --site local
  │
  ├─ RunConfig.from_yaml() → execution="bps", site="local"
  ├─ _create_executor() → BPSExecutor(site="local")
  │   └─ Checks: import lsst.ctrl.bps (fail fast if missing)
  │
  ├─ Stage: calibs.run(night, config, executor=bps_executor)
  │   ├─ executor.run_pipetask(["qgraph", ...]) → runs locally (fast)
  │   ├─ executor.run_pipetask(["run", "-g", "graph.qg", ...])
  │   │   ├─ _parse_pipetask_args() → extracts qgraph_file
  │   │   ├─ BPSConfig(pipeline="custom", qgraph_file="graph.qg", site="local")
  │   │   ├─ render_bps_config() → injects qgraphFile: into custom.yaml
  │   │   ├─ bps.submit() → `bps submit rendered.yaml`
  │   │   │   └─ ctrl_bps_parsl: ThreadPoolExecutor runs pipetask locally
  │   │   ├─ Poll: bps.status() → `bps report <run_id>`
  │   │   └─ _translate_bps_to_completed_process() → CompletedProcess
  │   └─ Stage module processes result as usual
  │
  └─ Same flow for science, dia, fphot stages
```

### Phase B — Docker Slurm Test Environment

```
docker/
├── docker-compose.yml          # 3 services: slurmctld, slurmd, login
├── Dockerfile.login            # lsstsqre base + obs_nickel + ctrl_bps_parsl
├── slurm/
│   ├── slurm.conf              # 1 partition, 1 node, 4 cores
│   └── cgroup.conf             # Resource isolation
├── scripts/
│   └── run-bps-test.sh         # Smoke test: bootstrap + 2 nights via BPS
└── README.md                   # Build/run/teardown instructions
```

Services:

| Service | Base Image | Role | Volumes |
|---------|-----------|------|---------|
| slurmctld | giovtorres/slurm-docker-cluster | Controller | /data, /repo |
| slurmd | Same | Worker (runs pipetask) | /data, /repo |
| login | lsstsqre/centos:7-stack-lsst_distrib + obs_nickel | Submit node | /data, /repo, obs_nickel |

Key decisions:
- Shared volume for Butler repo (Slurm workers need direct filesystem access)
- Single worker node with 4 cores (enough to test, won't overwhelm host)
- Test data: 2-3 night subset of 2023ixf raw data (~500MB)
- New `bps/sites/docker-slurm.yaml` site config (conservative: 4GB mem, 1 CPU, 30min walltime)

## Components

### Phase A

#### 1. `bps/pipelines/custom.yaml`
Minimal BPS template that uses a pre-built quantum graph instead of generating one:
- `qgraphFile: "{qgraph_file}"` (variable-substituted)
- Includes site config via `includeConfigs`
- No `pipelineYaml:` field (qgraph already encodes the pipeline)

#### 2. `BPSConfig.qgraph_file` field
Add optional `qgraph_file: str | None = None` to the dataclass. When set, `render_bps_config()` selects the `custom.yaml` template and injects the path.

#### 3. `render_bps_config()` update
Add `qgraph_file` to the variable substitution dict. When `pipeline == "custom"` and `qgraph_file` is set, use `custom.yaml` template.

#### 4. `_create_executor()` availability check
When `execution == "bps"`:
- Try `import lsst.ctrl.bps` — if fails, raise with install instructions
- When `site == "local"`, also check for `lsst.ctrl.bps.parsl`

#### 5. Integration test
Mock `run_with_stack` to simulate `bps submit` + `bps report` with realistic output. Verify that the custom.yaml template renders with `qgraphFile:` and the full lifecycle produces correct CompletedProcess.

### Phase B

#### 6. Docker Compose environment
- `slurmctld` + `slurmd` from giovtorres base image
- `login` from lsstsqre image with obs_nickel and ctrl_bps_parsl installed
- Shared volume at `/shared` for Butler repo and raw data

#### 7. `bps/sites/docker-slurm.yaml`
Parsl SlurmProvider config targeting the containerized cluster:
- 4 cores, 1 node, 4GB memory, 30min walltime
- `max_blocks: 2` (conservative for Docker)

#### 8. Smoke test script
`docker/scripts/run-bps-test.sh`:
1. Bootstrap Butler repo in shared volume
2. Ingest 2 nights of raw data
3. Run `nickel run test-config.yaml --site slurm`
4. Verify output collections exist
5. Exit 0/1

## Error Handling

| Scenario | Handling |
|----------|---------|
| ctrl_bps not installed | Clear error at executor creation |
| BPS submit fails (bad config) | Return CompletedProcess(returncode=1), log rendered YAML path |
| Slurm job OOM killed | BPS retry with 2x memory (already in base.yaml) |
| Slurm partition unavailable | Submit fails, executor returns failure with stderr |
| Poll timeout exceeded | Already handled in BPSExecutor |
| Partial quanta failure | Already handled by _translate_bps_to_completed_process() |

## Testing

- **Unit tests:** Existing 42 tests cover protocol, parsers, translators — no changes needed
- **Integration test:** New test mocking run_with_stack for full submit/report cycle with custom.yaml
- **Real-data test (Phase A):** Manual — 2023ixf with `--site local` via Parsl, compare against LocalExecutor results
- **Docker smoke test (Phase B):** `run-bps-test.sh` — runs via `docker compose up --exit-code-from login`

## What We're NOT Building (YAGNI)

- Per-stage timeout overrides (global timeout sufficient)
- Qgraph caching (generation is <1 min per night)
- Per-quantum failure detail parsing (stage-level pass/fail is enough)
- HTCondor testing (Slurm is the target)
- Direct ctrl_bps Python API (shell-out is the recommended pattern)

## Branch Strategy

`feature/dpg/bps-full` off `feature/dpg/bps-parallelization`
