# Architecture Overview

This document describes the architecture of STIPS — the Small Telescope Image Processing Suite. STIPS is a generic framework that brings the LSST Science Pipelines to 1-meter class telescopes, plus a per-telescope instrument *profile*. The Nickel 1-m at Lick is the reference instrument; a fork supports another telescope by adding its own `obs_<instrument>` profile package.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                          │
│  ┌──────────────┐  ┌──────────────────────────────────────────┐    │
│  │  stips CLI   │  │  Config YAML  (-c: env: block + pipeline) │    │
│  └──────────────┘  └──────────────────────────────────────────┘    │
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

STIPS is a monorepo organized around a three-package framework split: the CLI/tooling (`stips`), the instrument-agnostic LSST glue (`obs_stips`), and a per-telescope instrument profile (`obs_nickel`, the reference). A fork adds its own `obs_<instrument>` profile alongside `obs_nickel`. The runtime instrument is chosen via the `INSTRUMENT_PACKAGE` environment variable (default `lsst.obs.nickel`); the tooling imports `<pkg>.profile` and drives all collection names, Butler queries, and skymap behavior from it.

### 1. stips (Framework Core, CLI & Tooling)

The main Python package. It depends on the profile *types* exposed by `stips` itself (`InstrumentProfile`, `Site`, `Field`, `@hook`, `collections.CollectionNames`) and imports the active instrument's `profile` module at runtime:

```
packages/stips/src/stips/
├── cli.py                 # `stips` CLI entry point (console script: stips)
├── profile.py             # InstrumentProfile / Site / Field / @hook framework types
├── collections.py         # CollectionNames (driven by the active profile)
├── core/
│   ├── config.py          # Environment/config loading
│   ├── stack.py           # LSST stack activation
│   ├── pipeline.py        # Collection naming + coordinate validation
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
├── pipeline_tools/        # stips-* console scripts (archive, dia, ...)
├── eda/                   # Butler/archive inspection tools
├── skymap/                # Skymap construction tools
└── dashboard/             # Browser monitoring (optional `stips[dashboard]` extra)
```

### 2. obs_stips (Instrument-Agnostic LSST Glue)

The generic LSST middleware layer (`lsst.obs.stips`). It provides the base instrument/translator/formatter that profiles specialize, plus the shared PipelineTasks every instrument reuses:

```
obs_stips/
└── python/lsst/obs/stips/
    ├── instrument.py       # Generic StipsInstrument base
    ├── translator.py       # Generic StipsTranslator base
    ├── formatter.py        # Generic StipsRawFormatter base
    ├── plotting.py         # Shared plotting helpers
    └── tasks/              # Shared PipelineTasks (lsst.obs.stips.tasks.*)
        ├── forcedPhotRaDec.py
        ├── differentialPhot.py
        └── diaLightcurve*.py
```

### 3. obs_nickel (Reference Instrument Profile)

The Nickel telescope profile (`lsst.obs.nickel`) — a thin specialization of `obs_stips`:

```
obs_nickel/
├── python/lsst/obs/nickel/
│   ├── profile.py          # InstrumentProfile + @hook quirks (the profile)
│   ├── _instrument.py      # Nickel binding (StipsInstrument subclass)
│   ├── translator.py       # NickelTranslator (StipsTranslator subclass)
│   ├── rawFormatter.py     # NickelRawFormatter
│   ├── calibCombine.py     # Nickel-specific calib combination task
│   └── visitInfo.py        # Nickel-specific visit info task
├── camera/
│   └── nickel.yaml         # Camera geometry (1024×1024 CCD)
├── pipelines/              # DIA.yaml, ForcedPhotRaDec.yaml, ...
└── configs/                # calibrateImage/, dia/, coadds/
```

### 4. obs_nickel_data (Curated Calibrations)

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

`stips.collections` builds consistent collection names, parameterized by the active
instrument's `collection_prefix` (a fork's collections become `<prefix>/...`); `core/pipeline.py`
re-exports `CollectionNames` and provides the pre-flight coordinate/data-quality checks:

```python
class CollectionNames:
    # prefix = config.profile.collection_prefix ("Nickel" for the reference instrument)
    def __init__(self, night: str, run_ts: str | None = None, *, prefix: str):
        self.raw_run = f"{prefix}/raw/{night}/{run_ts}"
        self.calib_chain = f"{prefix}/calib/current"
        self.science_parent = f"{prefix}/runs/{night}/processCcd/{run_ts}"  # CHAINED
        self.science_run = f"{self.science_parent}/run"                     # Primary RUN
        # Fallback RUNs: {science_parent}/run_fb1, run_fb2, etc.
        self.diff_run = f"{prefix}/runs/{night}/diff/{run_ts}/run"
        # ...

def find_bad_coord_exposures(config, night, target_ra, target_dec, ...):
    """Query Butler for exposures with coordinates far from the target.
    Returns exposure IDs to exclude from processing."""
```

Downstream modules (DIA, coadd, fphot) use the CHAINED parent (`science_parent`) rather than `science_run` to include results from both the primary config and any fallback configs.

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
│   ├── processCcd/timestamp/      # CHAIN: Unified science (primary + fallbacks)
│   │   ├── run                    # RUN: Primary config outputs
│   │   ├── run_fb1                # RUN: Fallback 1 outputs (if used)
│   │   └── run_fb2                # RUN: Fallback 2 outputs (if used)
│   ├── diff/timestamp/run         # RUN: DIA outputs
│   └── forcedPhotRaDec/.../run    # RUN: Forced phot outputs
├── templates/
│   ├── ps1/{band}                 # RUN: External templates
│   └── deep/tract{N}/{band}       # RUN: Nickel coadds
└── refcats                        # CHAIN: Reference catalogs
```

The `processCcd/timestamp/` CHAINED collection is what downstream steps (DIA, coadd, fphot) use as input. It chains together the primary RUN and any fallback RUNs, providing a unified view of all successfully processed quanta.

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

Fork STIPS and add an `obs_<instrument>` profile alongside `obs_nickel`, following the same thin-profile pattern:
1. Create the `obs_{instrument}/` package providing `lsst.obs.<instrument>`
2. Add `profile.py` (an `InstrumentProfile` plus any `@hook` quirks)
3. Bind the instrument/translator/formatter on top of the `obs_stips` base classes
4. Create the camera geometry YAML and any instrument-specific pipeline configs
5. Set `INSTRUMENT_PACKAGE=lsst.obs.<instrument>` so the CLI loads the new profile

The shared PipelineTasks in `obs_stips` and the `stips` tooling work unchanged. See the [forking guide](forking-stips.md) for the full walkthrough.

## Dependencies

The framework splits into three layers. `stips` (CLI/tooling) defines the profile types and loads the active instrument profile at runtime. `obs_stips` is the generic LSST glue. `obs_nickel` is the reference instrument profile and depends on `obs_stips`; a fork adds its own `obs_<instrument>` profile in the same slot.

```
                      ┌──────────────────────────────────┐
                      │              stips               │
                      │  CLI · tooling · profile types   │
                      │  (InstrumentProfile, @hook,      │
                      │   CollectionNames)               │
                      └──────────────────────────────────┘
                       │ defines profile API      │ loads profile
                       │ (imported by profiles)   │ at runtime via
                       ▼                          ▼ INSTRUMENT_PACKAGE
   ┌───────────────────────────┐      ┌──────────────────────────────────────┐
   │      obs_nickel           │      │     obs_<instrument>  (a fork)        │
   │  reference profile        │ ...  │  another telescope's profile          │
   │  profile.py + bindings    │      │  profile.py + bindings                │
   │  + obs_nickel_data        │      │                                       │
   └───────────────────────────┘      └──────────────────────────────────────┘
                       │  each profile depends on  │
                       ▼                           ▼
                      ┌──────────────────────────────────┐
                      │             obs_stips            │
                      │  generic LSST glue (instrument,  │
                      │  translator, formatter, shared   │
                      │  PipelineTasks: lsst.obs.stips.*)│
                      └──────────────────────────────────┘
                                       │
                                       ▼
                      ┌──────────────────────────────────┐
                      │       LSST Science Pipelines      │
                      │  daf.butler · obs.base ·          │
                      │  pipe.tasks · ip.diffim · ...     │
                      └──────────────────────────────────┘
```

## See Also

- [Pipeline Flow Diagram](diagrams/pipeline-flow.mmd)
- [CLI Commands Diagram](diagrams/cli-commands.mmd)
- [Butler Collections Diagram](diagrams/butler-collections.mmd)
