# Nickel Processing Suite

## Project Overview

This is a **monorepo** for processing data from the **Nickel 1-meter telescope** at Lick Observatory using the **LSST Science Pipelines**. The primary use case is **difference imaging analysis (DIA)** for transient astronomy, particularly supernovae monitoring campaigns.

## Repository Structure

```
nickel_processing_suite/
├── packages/
│   ├── obs_nickel/           # LSST instrument package (camera geometry, ISR, pipelines)
│   ├── obs_nickel_data/      # Curated calibrations (defects, crosstalk)
│   └── data_tools/           # Python CLI and pipeline tools (main development focus)
├── scripts/
│   ├── pipeline/             # Shell scripts for pipeline stages (being migrated to Python)
│   ├── config/               # Per-target YAML configs (2023ixf, 2020wnt, etc.)
│   └── utilities/            # Helper scripts (logging, night conversion)
├── .env.*                    # Profile-based configuration files
└── Makefile                  # Dev tasks only (not for pipeline execution)
```

## Key Packages

### packages/data_tools (Primary Development Focus)

The unified Python package providing CLI and programmatic access to all pipeline functionality.

**Entry point:** `nickel` CLI command

**Core modules:**
- `obs_nickel_data_tools.core.config` - Configuration loading from .env files
- `obs_nickel_data_tools.core.stack` - LSST stack activation and command execution
- `obs_nickel_data_tools.core.calibs` - Nightly calibration processing
- `obs_nickel_data_tools.core.science` - Science frame processing (ISR, WCS, photometry); supports `target_ra`/`target_dec` for pre-flight coordinate validation
- `obs_nickel_data_tools.core.dia` - Difference imaging analysis; detects template overlap failures (diff_count==0)
- `obs_nickel_data_tools.core.ps1_template` - PS1 template ingestion (configurable cutout size via `size` param)
- `obs_nickel_data_tools.core.coadd` - Nickel coadd template building from multiple nights
- `obs_nickel_data_tools.core.fphot` - Forced photometry at coordinates (per-band)
- `obs_nickel_data_tools.core.lightcurve` - Lightcurve extraction; `LightcurveConfig` dataclass for display options (y-axis mode, x-axis mode, distance modulus, explosion date, error filtering)
- `obs_nickel_data_tools.core.run` - YAML-driven pipeline orchestration
- `obs_nickel_data_tools.core.pipeline` - Shared utilities (CollectionNames, validation, coordinate checks)

**CLI commands:**
- `nickel env` - Show/validate configuration
- `nickel bootstrap` - Initialize Butler repository
- `nickel calibs <night>` - Run nightly calibrations (bias, flat, defects)
- `nickel science <night> [--ra --dec]` - Process science frames (--ra/--dec enables coordinate validation)
- `nickel dia <night> --auto` - Single-band difference imaging
- `nickel download <night>` - Fetch data from Lick archive
- `nickel ps1-template --ra --dec --band` - Ingest PS1 templates for DIA
- `nickel fphot <night> --ra --dec` - Forced photometry at RA/Dec
- `nickel lightcurve --ra --dec --collections` - Extract lightcurves from DIA sources (supports `--y-axis`, `--x-axis`, `--explosion-mjd`, `--distance-modulus`, `--max-mag-err`)
- `nickel run <config.yaml>` - YAML-driven full pipeline orchestration

### packages/obs_nickel

LSST-compatible instrument package defining:
- Camera geometry and detector layout
- Instrument signature removal (ISR) configuration
- Pipeline definitions (YAML files in `pipelines/`)
- Custom PipelineTasks for Nickel-specific processing

**Key pipeline files:**
- `pipelines/DRP.yaml` - Full data release pipeline (ISR, calibration, coaddition); includes Nickel-specific relaxed thresholds for `makeDirectWarp`, `selectDeepCoaddVisits`, `selectTemplateCoaddVisits`
- `pipelines/DIA.yaml` - Difference imaging pipeline
- `pipelines/ForcedPhotRaDec.yaml` - Forced photometry pipeline
- `pipelines/nickel-analysis-dia-lightcurve.yaml` - Lightcurve extraction

### packages/obs_nickel_data

Curated calibration data:
- Defect maps per detector
- Crosstalk coefficients
- Other static calibration products

## Configuration System

### Profile-based Configuration

Uses `.env` files with profile support:
```bash
# Default profile
nickel env

# Named profile (loads .env.2023ixf or .env.2023ixf.ps1)
nickel -p 2023ixf env

# Explicit env file
nickel --env-file .env.2020wnt calibs 20201207
```

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `REPO` | Path to Butler repository |
| `STACK_DIR` | Path to LSST stack installation |
| `OBS_NICKEL` | Path to obs_nickel package |
| `RAW_PARENT_DIR` | Parent directory for raw data (contains YYYYMMDD/raw/) |

### Optional Environment Variables

| Variable | Description |
|----------|-------------|
| `REFCAT_REPO` | Path to reference catalog repository |
| `CP_PIPE_DIR` | Path to cp_pipe (auto-discovered if not set) |
| `LICK_ARCHIVE_DIR` | Path to lick_searchable_archive client |

## LSST Stack Integration

The package wraps LSST commands (pipetask, butler) by:
1. Sourcing the LSST stack loader script
2. Setting up lsst_distrib and obs_nickel
3. Exporting environment variables from config
4. Running commands within the activated environment

Key function: `run_with_stack()` in `core/stack.py`

## Data Flow

### Collection Naming Convention

```
Nickel/raw/{night}/{timestamp}                        # Ingested raw data
Nickel/calib/{night}                                  # Certified calibrations
Nickel/calib/current                                  # Unified calibration chain
Nickel/runs/{night}/processCcd/{ts}                   # CHAINED: unified science outputs
Nickel/runs/{night}/processCcd/{ts}/run               # RUN: primary config outputs
Nickel/runs/{night}/processCcd/{ts}/run_fb1           # RUN: fallback 1 outputs (if used)
Nickel/runs/{night}/processCcd/{ts}/run_fb2           # RUN: fallback 2 outputs (if used)
Nickel/runs/{night}/diff/{ts}/run                     # Difference imaging outputs
Nickel/runs/{night}/forcedPhotRaDec/{ts}/diffim_{band} # Forced photometry per band
templates/deep/tract{N}/{band}                        # Nickel coadd templates
templates/deep/tract{N}/{band}/{ts}                   # Coadd template RUN collections
templates/ps1/{band}                                  # PS1 external templates
```

Downstream consumers (DIA, coadd, fphot) should use the CHAINED parent collection (`processCcd/{ts}`) rather than individual RUN collections, since the CHAINED parent includes results from both the primary config and any successful fallback configs.

### Pipeline Workflow

1. **Bootstrap** - Create repo, register instrument, ingest refcats, create skymap
2. **Templates** - PS1 template ingestion (r/i bands) or Nickel coadd template building (b/v/r/i)
3. **Calibs** - Ingest raws, build bias/flat, certify calibrations
4. **Science** - ISR, WCS fitting, photometric calibration (with optional coordinate validation)
5. **DIA** - Image subtraction per night per band, source detection
6. **Forced Photometry** - Per night per band at target RA/Dec on difference images
7. **Lightcurve** - Extract combined multi-band lightcurve from forced photometry results

## Observing Night vs UT Day

Lick observations use **local date** (Pacific time) for the observing night, but FITS headers contain **UT dates**. The convention:
- Observing night `20230519` (local) → UT day_obs `20230520`
- Pipeline collections use observing night for human readability
- Butler queries use UT day_obs for data selection

## Target Campaigns

### 2023ixf (SN 2023ixf in M101)
- RA: 210.910750°, Dec: 54.311694° (14:03:38.580, +54:18:42.10)
- Distance: 6.7 Mpc (distance_modulus: 29.05)
- Explosion MJD: 60082.75 (2023-05-19)
- Nights: 20230519, 20230521, 20230523, ... through 20231211
- Config: `scripts/config/2023ixf/`

### 2020wnt (SN 2020wnt, SLSN-I at z=0.032)
- RA: 56.658125°, Dec: 43.229250° (03:46:37.950, +43:13:45.30)
- Explosion MJD: 59180.0 (2020-11-27)
- Nights: 20201207, 20210228, 20210324, ... through 20211111
- Config: `scripts/config/2020wnt/`

## Development Setup

```bash
# Clone and enter repo
cd nickel_processing_suite

# Create venv and install
uv venv
source .venv/bin/activate
uv pip install -e packages/data_tools

# Verify installation
nickel --help
nickel -p 2023ixf env
```

## Key Design Decisions

1. **Python CLI over Makefile** - Makefile kept only for dev tasks (lint, test), all pipeline operations via `nickel` CLI

2. **Profile system** - `-p` flag for easy switching between target campaigns without changing environment

3. **Modular commands** - Individual commands (calibs, science, dia) that can be composed, plus orchestrator for batch runs

4. **CP_PIPE_DIR auto-discovery** - Queries eups to find cp_pipe location, avoiding hardcoded paths

5. **Shell script delegation** - Bootstrap delegates to shell scripts via `run_with_stack()`; coadd template building is now pure Python in `core/coadd.py`

6. **Per-band DIA and fphot** - DIA and forced photometry run per night per band, so partial band failures don't block other bands

7. **Template force rebuild** - When science is re-processed (`skip_science: false`), coadd templates are force-rebuilt via `overwrite=True` to pick up improved inputs

8. **Fallback config strategy** - Science processing tries a primary `calibrateImage` config, then up to 3 fallbacks (dense/sparse x strict/relaxed). Each writes to its own RUN collection (`/run_fb1`, etc.) — see "Science fallback configs" in Common Issues for details.

9. **Self-contained YAML configs** - Pipeline configs embed `env:` section with all paths, making them portable without needing `.env` files

## YAML-Driven Pipeline Orchestration

The `nickel run <config.yaml>` command orchestrates the full pipeline from a self-contained YAML config. Key config sections:

```yaml
env:                    # Inline environment variables (REPO, STACK_DIR, etc.)
object: "2023ixf"       # Target name (matched against FITS headers)
ra: 210.910750          # Target RA — use full TNS precision (see Coordinate Precision below)
dec: 54.311694          # Target Dec
bands: ["r", "i"]       # Bands to process

template:
  type: ps1             # "ps1" or "coadd"
  size: 0.3             # PS1 cutout size in degrees (default: 0.3)
  degrade_seeing: 2.0   # Optional: convolve PS1 to match Nickel seeing
  nights: [...]         # For coadd type: template nights (SN faded)

science:
  nights:               # Science nights (simple list)
    - 20230519
    - 20230521

configs:                # Pipeline config files (paths relative to obs_nickel/configs/)
  science:
    calibrate_image: calibrateImage/tuned_configs/dense_strict.py
    calibrate_image_fallbacks: [...]
    colorterms: apply_colorterms.py
  coadd:
    make_direct_warp: coadds/makeDirectWarp_relaxed.py
  dia:
    subtract_images: dia/subtractImages.py
    detect_and_measure: dia/detectAndMeasure.py

options:
  jobs: 6
  skip_calibs: false
  skip_science: false
  skip_dia: false
  forced_phot: true
  forced_phot_image_type: diffim   # visit, diffim, or both
  continue_on_error: true
  use_fallbacks: true              # Try fallback calibrateImage configs on failure

# Lightcurve configuration (top-level section, replaces old options: keys)
lightcurve:
  enabled: true
  dataset_type: forced_phot_diffim_radec  # or dia_source_unfiltered
  min_snr: 2                       # Minimum S/N for detections
  max_mag_err: 1.0                 # Max magnitude error for plot filtering
  y_axis: apparent_mag             # apparent_mag | absolute_mag | flux_nJy | flux_adu
  x_axis: days_since_explosion     # mjd | days_since_explosion
  explosion_mjd: 60082.75          # Required when x_axis=days_since_explosion
  # distance_modulus: 29.05        # Required when y_axis=absolute_mag
```

Target configs live in `scripts/config/{target}/`:
- `pipeline_ps1_template.yaml` - PS1-based DIA (r/i bands only)
- `pipeline_nickel_template.yaml` - Nickel coadd-based DIA (all bands)

## Logging

Pipeline runs create a unified log directory at `logs/{RUN_ID}/` with subdirectories:
- `bootstrap/`, `calibs/`, `science/`, `dia/`, `fphot/`, `lightcurve/`
- `calibs_template/`, `science_template/` - For coadd template night processing
- `templates/{band}/` - Template build logs (both Python and shell script logs)
- `pipeline.log` - Python-level log of the full orchestration
- `summary.txt` - Final success/failure counts

Shell scripts (bootstrap) and Python (`run.py`) share the same `RUN_ID` via environment, so all logs land in the same run directory. Per-night logs are automatically split by exposure for easier debugging.

## Current Development Focus

The full Python CLI pipeline is operational. Active work:

1. **Robustness** - Coordinate validation, fallback configs, template overlap detection
2. **Template strategies** - PS1 external templates (r/i) and Nickel coadd templates (b/v/r/i)
3. **Per-band orchestration** - DIA and forced photometry run per-band to maximize partial results

## Testing

```bash
# Individual commands (using profile)
nickel -p 2023ixf calibs 20230519
nickel -p 2023ixf science 20230519 --object 2023ixf --ra 210.91 --dec 54.32
nickel -p 2023ixf dia 20230519 --auto --object 2023ixf

# Full pipeline orchestration (preferred)
nickel run scripts/config/2023ixf/pipeline_ps1_template.yaml
nickel run scripts/config/2023ixf/pipeline_nickel_template.yaml

# Dry run to preview commands
nickel run scripts/config/2023ixf/pipeline_ps1_template.yaml --dry-run
```

## Common Issues

### Python alias conflicts
If using a shell alias for `python`, it may override the venv. Use `.venv/bin/python` or `.venv/bin/nickel` explicitly.

### CP_PIPE_DIR not found
The system auto-discovers cp_pipe from the LSST stack. If it fails, the stack may not be properly installed.

### Raw data not found
Ensure `RAW_PARENT_DIR/{night}/raw/` exists with FITS files. Use `nickel download <night>` to fetch from archive.

### Stale DEC headers / "FileNotFoundError: astrometry_ref_cat"
The Nickel telescope DEC keyword can freeze at a previous pointing's value. Both CRVAL2 and DEC agree on the wrong coordinate, defeating the translator's fallback. Pre-flight coordinate validation in `pipeline.py:find_bad_coord_exposures()` catches these by comparing exposure coordinates against the expected target RA/Dec (5° tolerance with RA wrap-around handling). Automatic when using `nickel run` (YAML has ra/dec); for standalone `nickel science`, pass `--ra` and `--dec`.

### DIA reports success but no difference images
`dia.py` checks `diff_image_count` after pipeline execution. If the pipeline "succeeds" (exit code 0) but produces zero difference images (typically because `rewarpTemplate` found no template overlap), it correctly reports failure. This cascade is the most common DIA failure mode — the template doesn't spatially overlap the science visit footprint.

### PS1 template overlap failures
PS1 template cutout size defaults to 0.3° (18 arcmin). The Nickel FOV is ~6.3 arcmin, so this gives ~6 arcmin margin per side. If overlap failures persist, increase `template.size` in the YAML config. The `ingest_ps1_template.py` cache validates both target coverage and file size, so increasing the size will trigger a re-download.

### DRP.yaml config field names
The LSST stack version installed uses specific config field names that may differ from documentation:
- `BestSeeingQuantileSelectVisitsConfig`: uses `qMin`/`qMax` (NOT `quantile`)
- `BestSeeingSelectVisitsConfig`: uses `maxPsfFwhm`/`nVisitsMax`
- `makeDirectWarp` selection: `select.maxEllipResidual`, `select.maxScaledSizeScatter`

### Coordinate precision for forced photometry
Target RA/Dec must use full TNS precision (sexagesimal → decimal, 6+ decimal places). Rounding to 2 decimal places in degrees causes 5-17" offsets — enough to completely miss a point source on Nickel's 0.37"/pixel scale. Always convert from TNS sexagesimal (e.g., `14:03:38.580, +54:18:42.10`) rather than rounding. Symptom of wrong coordinates: 100% negative forced-photometry flux (measuring galaxy background instead of SN).

### PS1 template pixel units
PS1 templates must be pre-calibrated to nJy during ingestion (`ingest_ps1_template.py` does this automatically). If templates are in raw ADU (~363 nJy/ADU), the DIA kernel must absorb a ~363× flux ratio on top of PSF matching, causing numerical instability and unreliable kernel sums (200-1300 instead of ~1.0). After re-ingesting templates, existing DIA results must be rerun.

### Nickel coadd template contamination
If Nickel coadd templates are built from epochs when the SN is still active (e.g., 2023ixf template nights 20230728-20231211 = days 70-206 post-explosion, SN at mag 12-14), the template contains SN flux. This produces: (1) negative difference flux when science SN is fainter than template SN, (2) systematically underestimated flux at all epochs. Use PS1 templates for early epochs, or build Nickel templates only from SN-free data (post-fading or pre-explosion).

### Science fallback configs and collection naming
Each fallback calibrateImage config writes to its own RUN collection (`/run_fb1`, `/run_fb2`, `/run_fb3`) under the same CHAINED parent as the primary `/run`. This is required because LSST's Butler enforces config consistency per task label within a single RUN collection — writing a different `calibrateImage_config` into an existing RUN raises `ConflictingDefinitionError`. Downstream steps (DIA, coadd, fphot) should always use the CHAINED parent collection, not individual `/run` or `/run_fb*` collections.

## File Locations

- CLI entry point: `packages/data_tools/src/obs_nickel_data_tools/cli.py`
- Core modules: `packages/data_tools/src/obs_nickel_data_tools/core/`
- Pipeline tools: `packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/`
- PS1 ingestion: `packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/ingest_ps1_template.py`
- LSST pipelines: `packages/obs_nickel/pipelines/` (DRP.yaml, DIA.yaml, ForcedPhotRaDec.yaml)
- LSST pipeline configs: `packages/obs_nickel/configs/` (calibrateImage/, dia/, coadds/)
- Shell scripts: `scripts/pipeline/` (bootstrap, legacy utilities)
- Target configs: `scripts/config/{target}/`
- Logging utilities: `scripts/utilities/logging.sh`
