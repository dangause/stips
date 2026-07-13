# STIPS — The Small Telescope Image Processing Suite

[![CI](https://github.com/dangause/stips/actions/workflows/ci.yml/badge.svg)](https://github.com/dangause/stips/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](pyproject.toml)

**STIPS** brings the [LSST Science Pipelines](https://pipelines.lsst.io/) to 1-meter class telescopes. It wraps the Rubin/LSST reduction stack with the per-telescope plumbing — a declarative instrument profile, prefab YAML pipelines, and a unified CLI — needed to run survey-grade calibration, difference imaging, forced photometry, and lightcurve extraction on small-telescope data, without requiring deep LSST middleware knowledge.

**Supported instruments:**

- ✅ **Nickel 1-m** at Lick Observatory — reference implementation, used in active SN, exoplanet, and variable-star follow-up
- ✅ **CTIO 1.0m / Y4KCam** — second instrument; validated end-to-end on archival standard-star data. Exercises the framework's **multi-amplifier camera** support (4-amp, central-cross overscan), **on-chip binning** (unbinned 4064² and 2×2-binned 2072²), **multi-band** B/V/R/I reductions, and a **NOIRLab Astro Data Archive** fetch hook.
- ➕ **Other 1-m telescopes** — add one by dropping a declarative profile under `instruments/<name>/` (a `profile.py` + camera + hooks, loaded by path — no per-instrument LSST `obs_` package). The framework core and science pipelines work unchanged. See the [forking guide](docs/forking-stips.md).

> The CLI is `stips`. The active instrument is a declarative profile under `instruments/<name>/`, selected at runtime via the `INSTRUMENT_DIR` path in your config's `env:` block (the reference profile is `instruments/nickel`).

> **Supported LSST stack:** release **`v30_0_3`** — the version the Docker
> images build on and the one the docs are validated against. CI validates every
> push against the pinned weekly **`w_2025_32`**, and a scheduled canary tracks
> **`w_latest`** so upcoming breakage surfaces before the pin moves. (The old
> "v11.0.0" note here was a `rubin-env` conda-environment number, not a stack
> release — a category error, now removed.) Before bumping the stack, follow
> [docs/stack-bump-runbook.md](docs/stack-bump-runbook.md).

---

## Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Monorepo Structure](#monorepo-structure)
- [The stips CLI](#the-stips-cli)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running Pipelines](#running-pipelines)
- [YAML-Driven Pipelines](#yaml-driven-pipelines)
- [Docker Containerization](#docker-containerization)
- [BPS Batch Processing](#bps-batch-processing)
- [Camera Specification](#camera-specification)
- [Butler Collections](#butler-collections)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Install the framework (stips + obs_stips); instruments load by path
uv sync --group dev

# 2. Run a full pipeline from a YAML config (self-contained)
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml run

# 3. Or use individual commands — the same -c YAML supplies the config
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml calibs 20230519   # Calibrations
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml science 20230519  # Science frames
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml dia 20230519 --auto  # Difference imaging
```

> The active instrument is whatever `INSTRUMENT_DIR` in the config's `env:` block points at (`instruments/nickel` here). `uv sync` installs the framework packages (`stips`, `obs_stips`); the instrument profile is loaded from its directory at runtime — there is no per-instrument package to install.

### Docker Quick Start

```bash
# Run with Docker
docker-compose run --rm stips stips calibs 20230519

# Or build and run directly
docker build -t stips:latest -f docker/Dockerfile .
docker run -v /path/to/repo:/data/repo \
           -v /path/to/raw:/data/raw \
           -v /path/to/refcats:/data/refcats \
           stips:latest stips env
```

---

## Features

### Declarative instrument profiles (`instruments/<name>/`)
- An instrument is a directory — a `profile.py` (camera, site, filters, header translation, ISR overrides, data-fetch hook), an optional camera YAML, and tuned configs — **loaded by path** via `INSTRUMENT_DIR`. No per-instrument LSST `obs_` package or EUPS product.
- `obs_stips` synthesizes the LSST `Instrument`, translator, and raw formatter from the profile at runtime.
- **Cameras**: in-memory `CameraSpec` (single-amp) or a full multi-amp camera YAML; **on-chip binning** scales the geometry from a `CCD_BINNING` knob.
- Ships two instruments: **Nickel** (reference, single-CCD, B/V/R/I) and **CTIO 1.0m / Y4KCam** (4-amp, binned/unbinned, B/V/R/I).

### Complete Processing Pipelines
- **Calibration pipeline**: bias, flats, curated defect masks
- **Single-frame DRP**: ISR, source detection, WCS, photometry
- **Coadd generation**: deep template building
- **Difference imaging (DIA)**: transient/variable detection
- **Forced photometry**: measurements at arbitrary RA/Dec
- **Light curve extraction**: multi-band light curves from DIA or forced photometry

### Unified CLI (`stips`)
- **Single-YAML configuration** (`-c <config.yaml>`) — the sole config source per run
- **YAML-driven pipeline orchestration** with automatic bootstrap
- **BPS integration** for HPC cluster execution (Slurm, HTCondor)
- **Processing logs** for tracking fallback configs and failures

### Containerization & HPC Support
- **Docker images** based on official LSST Science Pipelines
- **Singularity/Apptainer** definitions for HPC environments
- **BPS configurations** for Slurm and HTCondor clusters

---

## Monorepo Structure

```
stips/
├── packages/                 # Framework only
│   ├── stips/                # Framework core + CLI (the `stips` command) + pipeline tools
│   ├── obs_stips/            # Instrument-neutral LSST glue (lsst.obs.stips): translator base,
│   │                         #   camera builder, the `active` Instrument/translator synthesizer,
│   │                         #   shared tasks, and reference pipelines/configs (instrument_defaults/)
│   └── refcats/              # Reference-catalog tooling (dist `stips-refcats`, import `stips_refcats`):
│                             #   Gaia DR3 / PS1 cone fetch, HTM coverage, LSST refcat conversion
├── instruments/              # Declarative instrument profiles (loaded by INSTRUMENT_DIR)
│   ├── nickel/               # Reference profile (profile.py, camera, fetch.py, tests)
│   │   ├── configs/          # Nickel-fitted calibration (colorterms, tuned_configs, PS1 overlay)
│   │   ├── obs_nickel_data/  # Curated Nickel calibrations (defects) — EUPS data package
│   │   ├── testdata/         # Test fixtures and data (testdata_nickel EUPS product)
│   │   ├── defects/          # Defect mask generation (stips-defects-build)
│   │   ├── colorterms/       # Color term fitting (stips-colorterms-fit)
│   │   ├── tuning/           # Pipeline tuning utilities (stips-tune-calibrate-image)
│   │   └── vendor/lick_searchable_archive/  # Vendored Lick archive (client used by fetch.py)
│   └── ctio1m/               # CTIO 1.0m / Y4KCam (4-amp camera, NOIRLab fetch, tests)
├── scripts/
│   ├── config/               # Per-target YAML configs (2023ixf, 2020wnt, ctio1m, ...)
│   ├── pipeline/             # Bootstrap script
│   └── utilities/            # Helper scripts
├── docs/                     # User guides, architecture docs, diagrams
├── docker/
│   ├── Dockerfile            # Standard Docker image
│   ├── Dockerfile.hpc        # HPC-optimized image
│   ├── Dockerfile.slurm      # Slurm service image (controller + compute nodes)
│   ├── docker-compose.yml    # Local development
│   ├── docker-compose.slurm.yml  # 6-container Slurm test cluster
│   └── stips.def             # Singularity/Apptainer definition
├── bps/
│   ├── base.yaml             # Base BPS configuration
│   ├── sites/                # Site configs (slurm, htcondor, local)
│   └── pipelines/            # Pipeline-specific BPS configs
├── pyproject.toml            # Workspace configuration
└── README.md                 # This file
```

---

## The `stips` CLI

The unified command-line interface for all pipeline operations. Supporting console scripts are installed under the `stips-*` prefix (e.g. `stips-dia-lightcurve`, `stips-eda-butler`).

### Commands Reference

All commands take the group-level config via `stips -c <config.yaml> <command> ...`
(the `-c` YAML's `env:` block supplies the configuration).

| Command | Description |
|---------|-------------|
| `stips env` | Show configuration and validate paths |
| `stips bootstrap` | Initialize Butler repository |
| `stips download NIGHT` | Fetch raw data via the instrument's `fetch_data` hook (Nickel → Lick archive; CTIO → NOIRLab Astro Data Archive) |
| `stips calibs NIGHT` | Run nightly calibrations (bias, flat, defects) |
| `stips measure-crosstalk NIGHTS...` | Measure & certify intra-detector crosstalk (multi-amp cameras; needs a profile `CrosstalkSpec`) |
| `stips science NIGHT` | Process science frames (ISR, WCS, photometry) |
| `stips dia NIGHT` | Run difference imaging analysis |
| `stips ps1-template` | Download and ingest PS1 template |
| `stips fphot NIGHT` | Run forced photometry at RA/Dec |
| `stips lightcurve` | Extract light curve from sources |
| `stips calib-metrics` | Dump per-visit astrometric/photometric calibration metrics to CSV |
| `stips landolt-validate` | Validate photometric calibration against Landolt standards |
| `stips clean` | Remove processing outputs for re-runs (plan/execute; `--dry-run`) |
| `stips run` | Run full pipeline from the `-c` YAML config |
| `stips dashboard` | Launch browser-based pipeline monitoring (needs the `stips[dashboard]` extra) |
| `stips refcat fetch\|status` | On-demand Gaia DR3 + PS1 refcat coverage for a target cone |
| `stips bps submit\|status\|cancel\|list` | Submit and manage BPS cluster runs |
| `stips provenance sync\|mark-deleted` | Maintain the run-provenance document (`provenance/runs.json`) |

### Multi-Target Workflows

The recommended path for multi-target work is per-target YAML configs (in `scripts/config/<target>/`). Each YAML is self-contained — including the environment paths in an `env:` block — so switching targets is one command:

```bash
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml run
stips -c scripts/config/2020wnt/pipeline_ps1_template.yaml run
```

The group-level `-c/--config` YAML is the sole config source. Its `env:` block supplies `REPO`/`STACK_DIR`/`INSTRUMENT_DIR`/`RAW_PARENT_DIR`; the same file's pipeline sections drive `stips run`. (`.env` files and `-p <profile>` are no longer supported.)

### Transient Analysis Workflow

> **Use full-precision coordinates** (6+ decimal places, e.g. SN 2023ixf at
> `210.910750, 54.311694`). Rounding RA/Dec to 2 decimals is a ~5–17″ offset —
> enough to miss a point source on Nickel's 0.37″/pixel scale, so forced
> photometry measures galaxy background instead of the SN.

> Each command still needs the group-level `-c <config.yaml>` (omitted below for
> brevity; see the note under [Running Pipelines](#running-pipelines)).

```bash
# 1. Ingest PS1 template for r-band
stips ps1-template --ra 210.910750 --dec 54.311694 --band r

# 2. Run forced photometry on difference images
stips fphot 20230519 --ra 210.910750 --dec 54.311694

# 3. Extract light curve
stips lightcurve --ra 210.910750 --dec 54.311694 \
    --collections "Nickel/runs/20230519/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "SN 2023ixf"
```

---

## Installation

### Prerequisites

- **Python 3.12+**
- **LSST Science Pipelines** (for running pipelines)
- **UV** package manager: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Installation Options

#### Minimal Development Setup
```bash
uv sync --group dev
```
Installs the framework workspace packages (`stips`, `obs_stips`, and support packages) plus code quality tools (ruff, pyright, pre-commit). Instrument profiles under `instruments/` are loaded by path at runtime (via `INSTRUMENT_DIR`), so there is no per-instrument package to install.

A fork adds its own profile directory under `instruments/<name>/` and points `INSTRUMENT_DIR` at it — no new `obs_` package required. See the [forking guide](docs/forking-stips.md).

#### Full Development Setup
```bash
uv sync --all-groups
```
Installs everything including Jupyter notebooks and analysis libraries.

### Verification

```bash
# Run test suite (automatically activates stack)
make test

# Test CLI tools
stips --help
stips env
```

---

## Configuration

### YAML Pipeline Configuration (Recommended)

Self-contained YAML files with inline environment:

```yaml
# scripts/config/2023ixf/pipeline_ps1_template.yaml
env:
  REPO: "/path/to/butler/repo"
  STACK_DIR: "/path/to/lsst_stack"
  INSTRUMENT_DIR: "/path/to/stips/instruments/nickel"
  RAW_PARENT_DIR: "/path/to/raw/data"
  REFCAT_REPO: "/path/to/refcats"

object: "2023ixf"
ra: 210.910750
dec: 54.311694
bands: ["r", "i"]

template:
  type: ps1
  size: 0.4               # Cutout size in degrees

science:
  nights:
    - 20230519
    - 20230521
    - 20230523

configs:
  science:
    calibrate_image: calibrateImage/tuned_configs/dense_strict.py
    calibrate_image_fallbacks:
      - calibrateImage/tuned_configs/dense_relaxed.py
      - calibrateImage/tuned_configs/sparse_relaxed.py
    colorterms: apply_colorterms.py
  dia:
    subtract_images: dia/subtractImages_ps1.py
    detect_and_measure: dia/detectAndMeasure.py

options:
  jobs: 6
  concurrent_nights: 3
  forced_phot: true
  continue_on_error: true
  use_fallbacks: true

lightcurve:
  enabled: true
  dataset_type: forced_phot_diffim_radec
  min_snr: 1
  max_mag_err: 1.0
  y_axis: apparent_mag
  x_axis: days_since_explosion
  explosion_mjd: 60082.75
```

### Config File `env:` Block

Configuration lives in the `env:` block of the YAML you pass with `-c/--config`
(the same file that drives `stips run`). It is the sole config source:

```yaml
# scripts/config/<target>/pipeline_ps1_template.yaml
env:
  REPO: /path/to/butler/repo
  STACK_DIR: /path/to/lsst_stack
  INSTRUMENT_DIR: /path/to/stips/instruments/nickel   # the declarative instrument dir
  RAW_PARENT_DIR: /path/to/raw/data
  REFCAT_REPO: /path/to/refcats
  CP_PIPE_DIR: "${STACK_DIR}/cp_pipe"   # ${VAR} expands within the env: block
  # CCD_BINNING: 2   # optional; scale the camera for 2x2-binned raws (default 1)
```

### Required Variables

| Variable | Description |
|----------|-------------|
| `REPO` | Path to Butler repository |
| `STACK_DIR` | Path to LSST stack installation |
| `INSTRUMENT_DIR` | Path to the active declarative instrument profile dir (e.g. `instruments/nickel`, `instruments/ctio1m`) |
| `RAW_PARENT_DIR` | Parent directory for raw data |

### Optional Variables

| Variable | Description |
|----------|-------------|
| `REFCAT_REPO` | Path to reference catalog repository |
| `CP_PIPE_DIR` | Path to cp_pipe (auto-discovered if not set) |
| `CCD_BINNING` | On-chip binning factor; scales the camera geometry (default 1 = unbinned) |
| `LICK_ARCHIVE_DIR` | Path to the Lick archive client (Nickel `download`) |
| `NOIRLAB_PROPOSAL` | Optional proposal-id filter for the CTIO NOIRLab `download` |

---

## Running Pipelines

> Every command needs the group-level `-c <config.yaml>` (its `env:` block is the
> sole config source). It is shown on the bootstrap step below and omitted from
> the later one-liners for brevity — prefix each with your config, e.g.
> `stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml calibs 20230519`.

### Step 0: Bootstrap (Automatic)

The `stips run` command automatically bootstraps the repository if needed. For manual bootstrap:

```bash
# Config comes from the group -c YAML (self-contained)
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml bootstrap

# The bootstrap step:
# - Creates Butler repository
# - Registers Nickel instrument
# - Ingests reference catalogs (Gaia DR3, PS1, the_monster)
# - Registers the Nickel skymap
```

### Step 1: Download Data (Optional)

```bash
stips download 20230519
```

### Step 2: Calibrations

```bash
stips calibs 20230519
stips calibs 20230519 --jobs 8  # More parallel jobs
```

### Step 3: Science Processing

```bash
stips science 20230519
stips science 20230519 --object 2023ixf --skip-coadds
stips science 20230519 --bad 12345,12346  # Exclude bad exposures
```

### Step 4: Difference Imaging

```bash
stips dia 20230519 --auto                    # Auto-discover template
stips dia 20230519 --template templates/ps1/r  # Specific template
stips dia 20230519 --auto --prefer-ps1 --band r  # Prefer PS1 template
```

### Step 5: Forced Photometry

Pass **full-precision** RA/Dec (6+ decimals); 2-decimal rounding offsets the
aperture by ~5–17″ and measures background instead of the source.

```bash
stips fphot 20230519 --ra 210.910750 --dec 54.311694
stips fphot 20230519 --ra 210.910750 --dec 54.311694 --band r --image-type both
```

### Step 6: Light Curve Extraction

```bash
# From DIA sources
stips lightcurve --ra 210.910750 --dec 54.311694 \
    --collections "Nickel/runs/*/diff/*/run" \
    --name "SN 2023ixf"

# From forced photometry (more reliable)
stips lightcurve --ra 210.910750 --dec 54.311694 \
    --collections "Nickel/runs/*/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "SN 2023ixf"

# With display options (absolute magnitude, days since explosion)
stips lightcurve --ra 210.910750 --dec 54.311694 \
    --collections "Nickel/runs/*/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "SN 2023ixf" \
    --y-axis absolute_mag --distance-modulus 29.05 \
    --x-axis days_since_explosion --explosion-mjd 60082.75 \
    --max-mag-err 1.0
```

---

## YAML-Driven Pipelines

Run complete workflows from a single configuration file:

```bash
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml run
stips -c scripts/config/2023ixf/pipeline_nickel_template.yaml run
stips -c pipeline.yaml run --dry-run  # Preview without executing
```

### Template Types

**PS1 Templates** (r/i bands only):
```yaml
template:
  type: ps1
  degrade_seeing: 2.0  # Convolve to match Nickel seeing
```

**Nickel Coadd Templates** (all bands):
```yaml
template:
  type: coadd
  nights:
    - "20230905"
    - "20230910"
    - "20231211"
```

**Transit Pipelines** (differential aperture photometry):
```yaml
template:
  type: ps1

options:
  pipeline_type: transit
  forced_phot_image_type: visit
  transit_search: true
  search_method: bls
```

### Fallback Configs

Set `use_fallbacks: true` in `options:` to automatically try progressively relaxed `calibrateImage` configs when the primary config fails (e.g., dense_strict → dense_relaxed → sparse_relaxed). Each fallback writes to its own RUN collection (`/run_fb1`, `/run_fb2`).

### Processing Logs

Pipeline runs create a unified log directory at `logs/{RUN_ID}/` with subdirectories for each step (`calibs/`, `science/`, `dia/`, `fphot/`, `lightcurve/`). Logs are automatically split by exposure for easier debugging.

- `logs/{RUN_ID}/pipeline.log` — Python-level orchestration log
- `logs/{RUN_ID}/summary.txt` — Final success/failure counts

---

## Docker Containerization

### Building the Docker Image

```bash
# Default build (LSST v30_0_3)
docker build -t stips:latest -f docker/Dockerfile .

# Specific LSST version
docker build --build-arg LSST_TAG=w_2025_19 -t stips:weekly .
```

### Running with Docker Compose

```bash
# Start with defaults
docker-compose up -d

# With custom paths
REPO=/path/to/repo RAW_PARENT_DIR=/path/to/raw docker-compose up -d

# Run a command
docker-compose run --rm stips stips calibs 20230519

# Interactive shell
docker-compose run --rm stips bash
```

### Docker Compose Services

| Service | Description | Profile |
|---------|-------------|---------|
| `stips` | Main processing service | default |
| `jupyter` | JupyterLab for interactive analysis | `interactive` |
| `bps-worker` | BPS local worker for testing | `bps` |

```bash
# Start Jupyter Lab
docker-compose --profile interactive up jupyter

# Access at http://localhost:8888
```

### Singularity/Apptainer for HPC

For HPC environments requiring Singularity:

```bash
# Convert Docker image to Singularity
singularity build stips.sif docker-daemon://stips:latest

# Run with bind mounts
singularity run -B /scratch/repo:/data/repo \
                -B /archive/raw:/data/raw \
                -B /common/refcats:/data/refcats \
                stips.sif stips calibs 20230519
```

---

## BPS Batch Processing

BPS (Batch Processing Service) enables large-scale parallel processing on HPC clusters.

### Available Sites

| Site | Description | Backend |
|------|-------------|---------|
| `slurm` | Slurm clusters | Parsl SlurmProvider |
| `htcondor` | HTCondor pools | lsst.ctrl.bps.htcondor |
| `local` | Local machine (testing) | Parsl ThreadPoolExecutor |

### Submitting Pipelines

```bash
# Submit to Slurm
stips bps submit calibs 20230519 --site slurm
stips bps submit science 20230519 --site slurm
stips bps submit dia 20230519 --site slurm --band r

# Submit with project/account
stips bps submit science 20230519 --site slurm --project myallocation

# Dry run (show what would be submitted)
stips bps submit calibs 20230519 --site local --dry-run
```

### Managing Runs

```bash
# Check status
stips bps status RUN_ID

# List recent runs
stips bps list

# Cancel a run
stips bps cancel RUN_ID
```

### BPS Configuration

Site configurations in `bps/sites/`:

```yaml
# bps/sites/slurm.yaml
site:
  slurm:
    class: lsst.ctrl.bps.parsl.sites.Slurm
    nodes: 1
    cores_per_node: 32
    mem_per_node: 128
    walltime: "04:00:00"
    scheduler_options: |
      #SBATCH --partition=normal
      #SBATCH --account={project}
```

Task-specific resource overrides:

```yaml
pipetask:
  calibrateImage:
    requestMemory: 8192
    requestCpus: 2
    numberOfRetries: 3

  subtractImages:
    requestMemory: 16384
    requestCpus: 2
```

---

## Camera Specification

Each instrument declares its camera in its profile — either an in-memory
`CameraSpec` (single-amplifier) or a full multi-amp camera YAML. On-chip
binning is applied at build time from `CCD_BINNING` (imaging pixels scale by the
factor; overscan strips stay fixed), so the same profile reduces binned and
unbinned raws.

| | **Nickel 1-m** | **CTIO 1.0m / Y4KCam** |
|---|---|---|
| Detector | single CCD | single CCD |
| Amplifiers | 1 (`A00`) | **4** (central-cross overscan) |
| Imaging area | 1024×1024 | 4064×4064 (unbinned) · 2032×2032 (2×2 binned) |
| Pixel scale | 0.37″/pix | 0.289″/pix (0.578″ binned 2×2) |
| Camera source | `CameraSpec` | `camera/y4kcam.yaml` |
| Data fetch | Lick archive | NOIRLab Astro Data Archive |

### Filters

Both instruments use Johnson/Bessell **B, V** and Cousins **R, I** (CTIO also
defines **U**):

| Physical Filter | Band | System | Central λ |
|----------------|------|--------|-----------|
| B | b | Johnson/Bessell | ~440 nm |
| V | v | Johnson/Bessell | ~550 nm |
| R | r | Cousins | ~640 nm |
| I | i | Cousins | ~790 nm |

---

## Butler Collections

The pipeline uses a hierarchical collection structure:

```
Nickel/
├── raw/
│   └── YYYYMMDD/                    # Raw data by night
│       └── TIMESTAMP/
├── calib/
│   ├── current                      # CHAIN: Latest calibrations
│   ├── curated                      # CHAIN: Camera geometry
│   ├── YYYYMMDD/                    # Nightly calibrations
│   └── cp/
│       └── YYYYMMDD/
│           ├── bias/
│           └── flat/
├── runs/
│   └── YYYYMMDD/                    # Processing outputs
│       ├── processCcd/TIMESTAMP/    # CHAINED parent (use this)
│       │   ├── run                  # Primary config outputs
│       │   ├── run_fb1              # Fallback 1 outputs
│       │   └── run_fb2              # Fallback 2 outputs
│       ├── diff/TIMESTAMP/run
│       ├── forcedPhotRaDec/TIMESTAMP/
│       │   ├── diffim_{band}        # Forced phot on difference images
│       │   └── visit_{band}         # Forced phot on visit images
│       └── differentialPhot/        # Differential aperture photometry
├── templates/
│   ├── ps1/{band}                   # PS1 external templates
│   └── deep/tract{N}/{band}         # Nickel coadd templates
└── refcats                          # CHAIN: Reference catalogs
```

---

## Development

### Code Quality

```bash
# Linting and formatting
make lint
make format

# Pre-commit hooks
pre-commit install
pre-commit run --all-files
```

### Testing

```bash
# Run full test suite
make test

# Individual test modules
pytest packages/obs_stips/tests/ -v          # framework glue + camera builder
pytest instruments/ctio1m/tests/ -v          # an instrument profile (translator, camera, fetch)
```

### Interactive Development

```bash
# Start Jupyter with LSST stack
make notebook

# Or with Docker
docker-compose --profile interactive up jupyter
```

---

## Troubleshooting

### "LSST stack not found"

Ensure `STACK_DIR` points to a valid LSST installation:
```bash
ls $STACK_DIR/loadLSST.bash  # Should exist
```

### "Command not found: stips"

Install the stips package:
```bash
uv sync --group dev
# or
pip install -e packages/stips -e packages/obs_stips
```

### Pipeline fails with import errors

The LSST stack must be active:
```bash
source $STACK_DIR/loadLSST.bash
setup lsst_distrib
```

### Bootstrap fails to find script

Run from the repository root directory:
```bash
cd /path/to/stips
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml bootstrap
```

### Forced photometry finds no processCcd collection

The science processing step may have failed. Check:
1. Processing logs in `logs/{RUN_ID}/`
2. That science processing completed successfully
3. That collections match the expected pattern

---

## References

- **LSST Science Pipelines**: https://pipelines.lsst.io
- **Butler Gen3**: https://pipelines.lsst.io/modules/lsst.daf.butler
- **BPS Documentation**: https://pipelines.lsst.io/modules/lsst.ctrl.bps
- **UV Package Manager**: https://docs.astral.sh/uv/

---

## License

This package is distributed under **GPL-3.0** license.

---

## Contact

For questions or issues:
- Create an issue on GitHub
- Contact the maintainer: Dan Gause

---

## Acknowledgments

Built on the LSST Science Pipelines framework. Thanks to the LSST Data Management team for the excellent infrastructure and documentation.
