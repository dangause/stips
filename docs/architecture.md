# Architecture Overview

This document describes the architecture of the Nickel Processing Suite (NPS).

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                          │
│  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────┐    │
│  │  nickel CLI  │  │  Pipeline YAML   │  │  .env Profiles     │    │
│  └──────────────┘  └──────────────────┘  └────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Orchestration Layer                             │
│  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────┐    │
│  │   run.py     │  │     bps.py       │  │ processing_log.py  │    │
│  │  (YAML run)  │  │  (HPC submit)    │  │ (failure tracking) │    │
│  └──────────────┘  └──────────────────┘  └────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Core Processing Modules                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │bootstrap │ │ calibs   │ │ science  │ │   dia    │ │  fphot   │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐                                          │
│  │lightcurve│ │ps1_templ │                                          │
│  └──────────┘ └──────────┘                                          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Infrastructure Layer                            │
│  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────┐    │
│  │  config.py   │  │    stack.py      │  │   pipeline.py      │    │
│  │ (env loading)│  │ (LSST activation)│  │ (collections,      │    │
│  │              │  │                  │  │  coord validation)  │    │
│  └──────────────┘  └──────────────────┘  └────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        External Systems                              │
│  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────┐    │
│  │   Butler     │  │ LSST Pipelines   │  │    HPC Cluster     │    │
│  │ Repository   │  │ (pipetask, etc.) │  │ (Slurm/HTCondor)   │    │
│  └──────────────┘  └──────────────────┘  └────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

## Package Structure

NPS is organized as a monorepo with three main packages:

### 1. obs_nickel (LSST Instrument Package)

Defines the Nickel telescope for the LSST Science Pipelines:

```
obs_nickel/
├── python/lsst/obs/nickel/
│   ├── _instrument.py      # Nickel instrument class
│   ├── nickelFilters.py    # B, V, R, I filter definitions
│   ├── translator.py       # FITS header → LSST metadata
│   └── rawFormatter.py     # Raw data reader
├── camera/
│   └── nickel.yaml         # Camera geometry (1024×1024 CCD)
├── pipelines/
│   ├── DIA.yaml            # Difference imaging pipeline
│   ├── ForcedPhotRaDec.yaml
│   └── ...
└── configs/
    ├── calibrateImage/     # ISR/astrometry configs
    └── dia/                # Subtraction configs
```

### 2. obs_nickel_data (Curated Calibrations)

Pre-built calibration products following LSST conventions:

```
obs_nickel_data/
├── Nickel/
│   └── defects/
│       └── ccd0/
│           └── 19700101T000000.ecsv  # Defect mask
└── python/lsst/obs/nickel_data/
    └── __init__.py
```

### 3. data_tools (CLI & Core Modules)

The main Python package providing CLI and processing logic:

```
data_tools/src/obs_nickel_data_tools/
├── cli.py                 # nickel CLI entry point
├── core/
│   ├── config.py          # Environment/config loading
│   ├── stack.py           # LSST stack activation
│   ├── pipeline.py        # Collection naming utilities
│   ├── bootstrap.py       # Repository initialization
│   ├── calibs.py          # Nightly calibrations
│   ├── science.py         # Science processing
│   ├── dia.py             # Difference imaging
│   ├── fphot.py           # Forced photometry
│   ├── lightcurve.py      # Light curve extraction
│   ├── ps1_template.py    # PS1 template ingestion
│   ├── run.py             # YAML pipeline orchestrator
│   ├── bps.py             # HPC batch submission
│   └── processing_log.py  # Failure tracking
└── pipeline_tools/
    ├── fetch_archive_night.py
    ├── extract_lightcurve.py
    └── ...
```

## Data Flow

### Complete Pipeline Flow

```
Raw FITS Files
     │
     ▼
┌─────────────────┐
│   Bootstrap     │ ──► Butler repo created
│   (one-time)    │     Instrument registered
└─────────────────┘     Refcats ingested
     │
     ▼
┌─────────────────┐
│   Calibrations  │ ──► Bias frames
│   (per night)   │     Flat fields
└─────────────────┘     Defect masks certified
     │
     ▼
┌─────────────────┐
│    Science      │ ──► ISR-corrected images
│   Processing    │     WCS solutions
│   (per night)   │     Photometric calibration
└─────────────────┘     Source catalogs
     │
     ▼
┌─────────────────┐
│    Template     │ ──► PS1 cutouts or
│   Preparation   │     Nickel coadd stacks
└─────────────────┘
     │
     ▼
┌─────────────────┐
│   Difference    │ ──► Difference images
│    Imaging      │     DIA source catalogs
│ (per night/band)│
└─────────────────┘
     │
     ▼
┌─────────────────┐
│    Forced       │ ──► Flux measurements
│   Photometry    │     at target coords
└─────────────────┘
     │
     ▼
┌─────────────────┐
│   Light Curve   │ ──► CSV files
│   Extraction    │     Plots
└─────────────────┘
```

## Key Design Patterns

### 1. Result Objects

Each core module returns a dataclass with status and outputs:

```python
@dataclass
class ScienceResult:
    success: bool
    error: str | None = None
    science_run: str | None = None
    coadd_run: str | None = None
```

### 2. Stack Wrapping

All LSST commands run through `stack.py`:

```python
def run_with_stack(cmd: list[str], config: Config, **kwargs) -> subprocess.CompletedProcess:
    """Execute command with LSST stack activated."""
    # Sources loadLSST.bash
    # Sets up lsst_distrib and obs_nickel
    # Exports config as environment variables
    # Runs the command
```

### 3. Collection Naming & Coordinate Validation

`pipeline.py` provides consistent collection names and pre-flight data quality checks:

```python
class CollectionNames:
    def __init__(self, night: str, timestamp: str):
        self.raw_run = f"Nickel/raw/{night}/{timestamp}"
        self.calib_chain = f"Nickel/calib/{night}"
        self.science_run = f"Nickel/runs/{night}/processCcd/{timestamp}/run"
        self.diff_run = f"Nickel/runs/{night}/diff/{timestamp}/run"
        # ...

def find_bad_coord_exposures(config, night, target_ra, target_dec, ...):
    """Query Butler for exposures with coordinates far from the target.
    Returns exposure IDs to exclude from processing."""
```

The coordinate validation catches the Nickel telescope's known issue where DEC headers can freeze at a previous pointing's value, which would otherwise crash the qgraph builder due to missing refcat coverage.

### 4. Processing Logs

`processing_log.py` tracks fallback attempts:

```python
@dataclass
class ProcessingLog:
    night: str
    step: str
    timestamp: str
    configs_tried: list[ConfigAttempt]
    final_status: str
    output_collection: str | None
```

### 5. YAML-Driven Orchestration

`run.py` parses YAML and calls other modules:

```python
def run(config_file: Path, config: Config, dry_run: bool) -> RunResult:
    yaml_config = load_yaml(config_file)

    # Step 0: Bootstrap if needed
    if bootstrap.needs_bootstrap(config):
        bootstrap.run(config)

    # Step 1: Templates
    for band in yaml_config['bands']:
        ps1_template.run(band=band, ...)

    # Step 2-4: Per night
    for night in yaml_config['nights']:
        calibs.run(night, config)
        science.run(night, config, ...)
        dia.run(night, config, ...)
        fphot.run(night, config, ...)

    # Step 5: Light curve
    lightcurve.run(...)
```

## Butler Collection Structure

```
Nickel/
├── raw/YYYYMMDD/timestamp/        # RUN: Ingested raw data
├── calib/
│   ├── current                    # CHAIN: Points to latest calibs
│   ├── curated                    # CHAIN: Camera + defects
│   ├── YYYYMMDD/                  # RUN: Certified calibs
│   └── cp/YYYYMMDD/bias/          # RUN: Constructed calibs
├── runs/YYYYMMDD/
│   ├── processCcd/timestamp/run   # RUN: Science outputs
│   ├── diff/timestamp/run         # RUN: DIA outputs
│   └── forcedPhotRaDec/.../run    # RUN: Forced phot outputs
├── templates/
│   ├── ps1/{band}                 # RUN: External templates
│   └── deep/tract{N}/{band}       # RUN: Nickel coadds
└── refcats                        # CHAIN: Reference catalogs
```

## Extension Points

### Adding New Pipeline Steps

1. Create module in `core/`:
   ```python
   # core/my_step.py
   @dataclass
   class MyStepResult:
       success: bool
       error: str | None = None

   def run(night: str, config: Config, **options) -> MyStepResult:
       ...
   ```

2. Add CLI command in `cli.py`:
   ```python
   @cli.command()
   def my_step(ctx, night, ...):
       result = my_step_module.run(night, ...)
   ```

3. Integrate in `run.py` if needed

### Adding New Instruments

Follow the `obs_nickel` pattern:
1. Create `obs_{instrument}/` package
2. Define instrument class extending `lsst.obs.base.Instrument`
3. Create camera geometry YAML
4. Create translator for FITS headers
5. Add pipeline definitions

## Dependencies

```
┌─────────────────────────────────────────┐
│              data_tools                  │
│  ┌───────────────┐  ┌────────────────┐  │
│  │   obs_nickel  │  │ obs_nickel_data│  │
│  └───────────────┘  └────────────────┘  │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│         LSST Science Pipelines           │
│  ┌──────────┐ ┌────────┐ ┌───────────┐  │
│  │daf.butler│ │obs.base│ │pipe.tasks │  │
│  └──────────┘ └────────┘ └───────────┘  │
└─────────────────────────────────────────┘
```

## See Also

- [Pipeline Flow Diagram](diagrams/pipeline-flow.mmd)
- [CLI Commands Diagram](diagrams/cli-commands.mmd)
- [Butler Collections Diagram](diagrams/butler-collections.mmd)
