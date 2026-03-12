# Nickel Processing Suite

Gen3 LSST Science Pipelines integration for the **Nickel 1-meter telescope** at Lick Observatory.

A complete, production-ready monorepo providing telescope configuration, data pipelines, and analysis tools for automated astronomical survey processing.

> Tested with LSST Science Pipelines `v30.0.3` and `v11.0.0`

---

## Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Monorepo Structure](#monorepo-structure)
- [The nickel CLI](#the-nickel-cli)
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
# 1. Install all packages
uv sync --group dev

# 2. Run a full pipeline from YAML config (self-contained)
nickel run scripts/config/2023ixf/pipeline_ps1_template.yaml

# 3. Or use individual commands with profiles
nickel -p 2023ixf calibs 20230519        # Run calibrations
nickel -p 2023ixf science 20230519       # Process science frames
nickel -p 2023ixf dia 20230519 --auto    # Difference imaging
```

### Docker Quick Start

```bash
# Run with Docker
docker-compose run --rm nps nickel calibs 20230519

# Or build and run directly
docker build -t nps:latest -f docker/Dockerfile .
docker run -v /path/to/repo:/data/repo \
           -v /path/to/raw:/data/raw \
           -v /path/to/refcats:/data/refcats \
           nps:latest nickel env
```

---

## Features

### Core Instrument Package (`obs_nickel`)
- Single-detector camera model (1024x1024 CCD)
- FITS metadata translator (`NickelTranslator`)
- Raw data formatter (`NickelRawFormatter`)
- Filter definitions: Johnson/Bessell **B, V**; Cousins **R, I**
- Optimized pipeline configurations for Nickel data

### Complete Processing Pipelines
- **Calibration pipeline**: bias, flats, curated defect masks
- **Single-frame DRP**: ISR, source detection, WCS, photometry
- **Coadd generation**: deep template building
- **Difference imaging (DIA)**: transient/variable detection
- **Forced photometry**: measurements at arbitrary RA/Dec
- **Light curve extraction**: multi-band light curves from DIA or forced photometry

### Unified CLI (`nickel`)
- **Profile-based configuration** for multi-repository workflows
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
nickel_processing_suite/
├── packages/
│   ├── obs_nickel/           # LSST instrument package
│   ├── obs_nickel_data/      # Curated calibrations (defects)
│   ├── data_tools/           # Python CLI and pipeline tools
│   ├── defects/              # Defect mask generation
│   ├── refcats/              # Reference catalog scripts
│   └── colorterms/           # Color term fitting
├── scripts/
│   ├── config/               # Per-target YAML configs (2023ixf, 2020wnt)
│   ├── pipeline/             # Shell scripts for pipeline stages
│   └── utilities/            # Helper scripts
├── docker/
│   ├── Dockerfile            # Standard Docker image
│   ├── Dockerfile.hpc        # HPC-optimized image
│   ├── docker-compose.yml    # Local development
│   └── nps.def               # Singularity definition
├── bps/
│   ├── base.yaml             # Base BPS configuration
│   ├── sites/                # Site configs (slurm, htcondor, local)
│   └── pipelines/            # Pipeline-specific BPS configs
├── pyproject.toml            # Workspace configuration
└── README.md                 # This file
```

---

## The `nickel` CLI

The unified command-line interface for all pipeline operations.

### Commands Reference

| Command | Description |
|---------|-------------|
| `nickel env` | Show configuration and validate paths |
| `nickel bootstrap [CONFIG.yaml]` | Initialize Butler repository |
| `nickel download NIGHT` | Fetch data from Lick archive |
| `nickel calibs NIGHT` | Run nightly calibrations (bias, flat, defects) |
| `nickel science NIGHT` | Process science frames (ISR, WCS, photometry) |
| `nickel dia NIGHT` | Run difference imaging analysis |
| `nickel ps1-template` | Download and ingest PS1 template |
| `nickel fphot NIGHT` | Run forced photometry at RA/Dec |
| `nickel lightcurve` | Extract light curve from sources |
| `nickel run CONFIG.yaml` | Run full pipeline from YAML config |
| `nickel bps submit` | Submit pipeline to BPS cluster |
| `nickel bps status` | Check BPS run status |
| `nickel bps cancel` | Cancel BPS run |
| `nickel bps list` | List recent BPS runs |

### Profile-Based Configuration

Work with multiple Butler repositories using profiles:

```bash
# Create profile-specific env files
cp .env.example .env.2023ixf  # For SN 2023ixf campaign
cp .env.example .env.2020wnt  # For SN 2020wnt campaign

# Use profiles with any command
nickel -p 2023ixf calibs 20230519
nickel -p 2020wnt dia 20201207 --auto

# Profiles look for .env.{profile} or .env.{profile}.ps1
```

### Transient Analysis Workflow

```bash
# 1. Ingest PS1 template for r-band
nickel ps1-template --ra 210.91 --dec 54.32 --band r

# 2. Run forced photometry on difference images
nickel fphot 20230519 --ra 210.91 --dec 54.32

# 3. Extract light curve
nickel lightcurve --ra 210.91 --dec 54.32 \
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
Installs all workspace packages plus code quality tools (ruff, pyright, pre-commit).

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
nickel --help
nickel env
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
  OBS_NICKEL: "/path/to/nickel_processing_suite/packages/obs_nickel"
  RAW_PARENT_DIR: "/path/to/raw/data"
  REFCAT_REPO: "/path/to/refcats"

object: "2023ixf"
ra: 210.910750
dec: 54.311694
bands: ["r", "i"]

template:
  type: ps1
  degrade_seeing: 2.0

nights:
  20230519:
    r: []
    i: []
  20230521:
    r: []
    i: []

options:
  jobs: 8
  forced_phot: true
  lightcurve: true
  continue_on_error: true
  use_fallbacks: true
```

### Environment File Configuration

For single-repository setups or profiles:

```bash
# .env or .env.{profile}
REPO=/path/to/butler/repo
STACK_DIR=/path/to/lsst_stack
OBS_NICKEL=/path/to/obs_nickel
RAW_PARENT_DIR=/path/to/raw/data
REFCAT_REPO=/path/to/refcats
```

### Required Variables

| Variable | Description |
|----------|-------------|
| `REPO` | Path to Butler repository |
| `STACK_DIR` | Path to LSST stack installation |
| `OBS_NICKEL` | Path to obs_nickel package |
| `RAW_PARENT_DIR` | Parent directory for raw data |

### Optional Variables

| Variable | Description |
|----------|-------------|
| `REFCAT_REPO` | Path to reference catalog repository |
| `CP_PIPE_DIR` | Path to cp_pipe (auto-discovered if not set) |
| `LICK_ARCHIVE_DIR` | Path to lick_searchable_archive client |

---

## Running Pipelines

### Step 0: Bootstrap (Automatic)

The `nickel run` command automatically bootstraps the repository if needed. For manual bootstrap:

```bash
# From YAML config (recommended - self-contained)
nickel bootstrap scripts/config/2023ixf/pipeline_ps1_template.yaml

# With profile
nickel -p 2023ixf bootstrap

# The bootstrap step:
# - Creates Butler repository
# - Registers Nickel instrument
# - Ingests reference catalogs (Gaia DR3, PS1, the_monster)
# - Registers the Nickel skymap
```

### Step 1: Download Data (Optional)

```bash
nickel download 20230519
```

### Step 2: Calibrations

```bash
nickel calibs 20230519
nickel calibs 20230519 --jobs 8  # More parallel jobs
```

### Step 3: Science Processing

```bash
nickel science 20230519
nickel science 20230519 --object 2023ixf --skip-coadds
nickel science 20230519 --bad 12345,12346  # Exclude bad exposures
```

### Step 4: Difference Imaging

```bash
nickel dia 20230519 --auto                    # Auto-discover template
nickel dia 20230519 --template templates/ps1/r  # Specific template
nickel dia 20230519 --auto --prefer-ps1 --band r  # Prefer PS1 template
```

### Step 5: Forced Photometry

```bash
nickel fphot 20230519 --ra 210.91 --dec 54.32
nickel fphot 20230519 --ra 210.91 --dec 54.32 --band r --image-type both
```

### Step 6: Light Curve Extraction

```bash
# From DIA sources
nickel lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/*/diff/*/run" \
    --name "SN 2023ixf"

# From forced photometry (more reliable)
nickel lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/*/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "SN 2023ixf"
```

---

## YAML-Driven Pipelines

Run complete workflows from a single configuration file:

```bash
nickel run scripts/config/2023ixf/pipeline_ps1_template.yaml
nickel run scripts/config/2023ixf/pipeline_nickel_template.yaml
nickel run pipeline.yaml --dry-run  # Preview without executing
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

### Processing Logs

The pipeline creates JSON logs in `{repo}/processing_log/` to track:
- Which configs were attempted for each step
- Whether fallback configs were used
- Failed quanta and their error messages
- Overall success/failure status

Example log path: `{repo}/processing_log/20230519_science_20240101T120000.json`

---

## Docker Containerization

### Building the Docker Image

```bash
# Default build (LSST v30_0_3)
docker build -t nps:latest -f docker/Dockerfile .

# Specific LSST version
docker build --build-arg LSST_TAG=w_2025_19 -t nps:weekly .
```

### Running with Docker Compose

```bash
# Start with defaults
docker-compose up -d

# With custom paths
REPO=/path/to/repo RAW_PARENT_DIR=/path/to/raw docker-compose up -d

# Run a command
docker-compose run --rm nps nickel calibs 20230519

# Interactive shell
docker-compose run --rm nps bash
```

### Docker Compose Services

| Service | Description | Profile |
|---------|-------------|---------|
| `nps` | Main processing service | default |
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
singularity build nps.sif docker-daemon://nps:latest

# Run with bind mounts
singularity run -B /scratch/repo:/data/repo \
                -B /archive/raw:/data/raw \
                -B /common/refcats:/data/refcats \
                nps.sif nickel calibs 20230519
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
nickel bps submit calibs 20230519 --site slurm
nickel bps submit science 20230519 --site slurm
nickel bps submit dia 20230519 --site slurm --band r

# Submit with project/account
nickel bps submit science 20230519 --site slurm --project myallocation

# Dry run (show what would be submitted)
nickel bps submit calibs 20230519 --site local --dry-run
```

### Managing Runs

```bash
# Check status
nickel bps status RUN_ID

# List recent runs
nickel bps list

# Cancel a run
nickel bps cancel RUN_ID
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

- **Detector**: Single CCD (detector ID: 0)
- **Format**: 1024x1024 imaging area + 32 column overscan
- **Raw frame size**: 1056x1024 pixels
- **Amplifier**: Single readout (A00)
- **Pixel scale**: 0.37"/pixel
- **Field of view**: ~6.3' x 6.3'
- **Gain**: ~1.8 e-/ADU
- **Read noise**: ~7 e-

### Filters

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
│       ├── processCcd/TIMESTAMP/run
│       ├── diff/TIMESTAMP/run
│       └── forcedPhotRaDec/TIMESTAMP/run
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
pytest packages/obs_nickel/tests/ -v
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

### "Command not found: nickel"

Install the data_tools package:
```bash
uv sync --group dev
# or
pip install -e packages/data_tools
```

### Pipeline fails with import errors

The LSST stack must be active:
```bash
source $STACK_DIR/loadLSST.bash
setup lsst_distrib
```

### Bootstrap fails to find script

Run from the nickel_processing_suite directory:
```bash
cd /path/to/nickel_processing_suite
nickel bootstrap scripts/config/2023ixf/pipeline_ps1_template.yaml
```

### Forced photometry finds no processCcd collection

The science processing step may have failed. Check:
1. Processing logs in `{repo}/processing_log/`
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
