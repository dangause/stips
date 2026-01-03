# DRP with Recalibration Pipeline

This directory contains a complete, isolated setup for running the LSST DRP pipeline with Stage 2 recalibration (FGCM photometric calibration + GBDES astrometric fit + PSF refit).

## Overview

The recalibration pipeline adds multi-epoch calibration stages to the standard DRP:

- **Stage 1** (steps 1a-1d): Single-visit processing (same as standard DRP)
- **Stage 2** (steps 2a-2f): Multi-epoch recalibration
  - **Step 2a**: FGCM photometric calibration (global)
  - **Step 2b**: GBDES astrometric fit (per-tract)
  - **Step 2c**: GBDES healpix fit (optional, per-healpix)
  - **Step 2d**: Refit PSFs and update visit_summary with new calibrations
  - **Step 2f**: Generate final tables and stellar motion fit
- **Coadds**: Build coadds using recalibrated visit_summary
- **DIA**: Difference imaging (optional)

## Files

### Configuration
- `.env.recal` - Environment configuration (isolated repo, paths, settings)
- `packages/obs_nickel/pipelines/experimental/DRP_recal.yaml` - Pipeline definition with Stage 2 tasks

### Scripts

#### Core Pipeline Scripts (Recal-specific copies)
- `scripts/pipeline/00_bootstrap_repo_recal.sh` - Bootstrap repository
- `scripts/pipeline/10_calibs_recal.sh` - Process calibration frames
- `scripts/pipeline/20_science_recal.sh` - **Stage 1 single-visit processing only**
- `scripts/pipeline/21_recalibrate.sh` - **Stage 2 recalibration (NEW)**
- `scripts/pipeline/30_coadds_recal.sh` - Build coadds from recalibrated data

#### Orchestration Scripts
- `scripts/pipeline/run_drp_recal.sh` - **Master script to run full pipeline**

## Quick Start

### 1. Create a nights list file

Create a text file with the nights you want to process (one YYYYMMDD per line):

```bash
# nights.txt
20240624
20240625
20240626
```

### 2. Run the full pipeline

```bash
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
  --nights-file nights.txt \
  --tract 1825 \
  --jobs 4
```

This will:
1. Bootstrap the repository (if needed)
2. Download raw data from archive (optional)
3. Process calibration frames
4. Run Stage 1 (single-visit processing)
5. Run Stage 2 (recalibration)
6. Build coadds with recalibrated data

### 3. Skip already-done stages

If you've already run some stages, you can skip them:

```bash
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
  --nights-file nights.txt \
  --tract 1825 \
  --skip-bootstrap \
  --skip-calibs \
  --skip-science \
  --jobs 4
```

## Step-by-Step Usage

If you prefer to run each stage separately:

### Stage 0: Bootstrap (once per repo)

```bash
ENV_FILE=.env.recal ./scripts/pipeline/00_bootstrap_repo_recal.sh
```

### Stage 1: Process each night

```bash
# Download raw data (optional)
./scripts/pipeline/01_download_archive.sh --night 20240624

# Process calibration frames
ENV_FILE=.env.recal ./scripts/pipeline/10_calibs_recal.sh \
  --night 20240624 \
  --jobs 4

# Process science (Stage 1 only)
ENV_FILE=.env.recal ./scripts/pipeline/20_science_recal.sh \
  --night 20240624 \
  --jobs 4
```

Repeat for each night.

### Stage 2: Recalibration (after all Stage 1 processing)

```bash
ENV_FILE=.env.recal ./scripts/pipeline/21_recalibrate.sh \
  --nights-file nights.txt \
  --tract 1825 \
  --jobs 4
```

This runs all Stage 2 steps:
- Step 2a: FGCM (global photometric calibration)
- Step 2b: GBDES tract-level astrometric fit
- Step 2c: GBDES healpix-level fit (optional)
- Step 2d: Refit PSFs and update visit_summary
- Step 2f: Final tables and stellar motion

You can skip individual steps with `--skip-step2a`, `--skip-step2b`, etc.

### Stage 3: Build coadds (per band)

```bash
ENV_FILE=.env.recal ./scripts/pipeline/30_coadds_recal.sh \
  --nights-file nights.txt \
  --band r \
  --tract 1825 \
  --jobs 4
```

Repeat for each band you want to process.

## Environment Variables

Key variables in `.env.recal`:

```bash
# Isolated repository (won't touch your main repo)
REPO=/path/to/recal_repo

# LSST stack
STACK_DIR=/path/to/lsst_stack
OBS_NICKEL=/path/to/obs_nickel

# Pipeline (uses experimental recal version)
# Automatically set to: packages/obs_nickel/pipelines/experimental/DRP_recal.yaml
```

## Pipeline Details

### What's Different from Standard DRP?

1. **Separate pipeline YAML**: Uses `DRP_recal.yaml` which imports `DRP.yaml` and adds Stage 2 tasks
2. **Collection structure**: Outputs go to `Nickel/recal/*` instead of `Nickel/runs/*`
3. **Stage 1 vs Stage 2 separation**: Stage 1 must complete for all nights before Stage 2 runs
4. **Updated datasets**: Coadds use `visit_summary` (recalibrated) instead of `preliminary_visit_summary`

### Collection Organization

```
Nickel/
├── raw/
│   └── {NIGHT}/
│       └── {TIMESTAMP}/
├── calib/
│   └── current/
└── recal/
    ├── runs/
    │   └── {NIGHT}/
    │       └── stage1/
    │           └── {TIMESTAMP}/
    ├── stage2/
    │   └── {TIMESTAMP}/
    └── coadds/
        └── tract{TRACT}/
            └── {BAND}/
                └── {TIMESTAMP}/
```

### Data Flow

```
Stage 1 (per night):
  raw → isr → calibrateImage → single_visit_star → preliminary_visit_summary
  ↓
  isolated_star_association (per tract)

Stage 2 (global/tract-level):
  isolated_star → FGCM → fgcmPhotoCalibCatalog
  single_visit_star → GBDES → gbdesAstrometricFitSkyWcsCatalog
  ↓
  PSF refit + visit_summary update
  ↓
  visit_summary (with FGCM photometry + GBDES astrometry)

Coadds:
  preliminary_visit_image + visit_summary → warps → template_coadd
```

## Troubleshooting

### "No Stage 1 collection found"
- Make sure you've run `20_science_recal.sh` for all nights in your nights file
- Check collections: `butler query-collections $REPO | grep "recal/runs"`

### "No Stage 2 recalibration collection found"
- Make sure you've run `21_recalibrate.sh` before building coadds
- Check collections: `butler query-collections $REPO | grep "recal/stage2"`

### "Pipeline not found"
- Verify `DRP_recal.yaml` exists: `ls packages/obs_nickel/pipelines/experimental/DRP_recal.yaml`
- Check `OBS_NICKEL` is set correctly in `.env.recal`

### FGCM or GBDES failures
- Ensure you have enough data (FGCM needs multiple nights, multiple bands)
- Check isolated star associations: `butler query-datasets $REPO isolated_star_association`
- Try skipping problematic steps with `--skip-step2a`, `--skip-step2b`, etc.

## Comparing with Original Files

This setup uses **copies** of everything to avoid touching the original pipeline:

| Original | Recal Copy | Purpose |
|----------|-----------|---------|
| `.env` | `.env.recal` | Environment configuration |
| `DRP.yaml` | `DRP_recal.yaml` | Pipeline definition (adds Stage 2) |
| `10_calibs.sh` | `10_calibs_recal.sh` | Calibration processing |
| `20_science.sh` | `20_science_recal.sh` | Stage 1 only (no coadds) |
| N/A | `21_recalibrate.sh` | **NEW**: Stage 2 recalibration |
| `30_coadds.sh` | `30_coadds_recal.sh` | Coadds with recal data |
| N/A | `run_drp_recal.sh` | **NEW**: Master orchestration |

## Next Steps

After successfully running the recalibration pipeline:

1. **Inspect calibrations**: Check that FGCM and GBDES produced good calibrations
   ```bash
   butler query-datasets $REPO fgcmPhotoCalibCatalog
   butler query-datasets $REPO gbdesAstrometricFitSkyWcsCatalog
   ```

2. **Compare with standard DRP**: Run the same data through standard DRP and compare photometry/astrometry

3. **Build templates**: Use recalibrated coadds for difference imaging

4. **Run DIA**: Test difference imaging with improved calibrations

## References

- LSST DRP Pipeline: https://pipelines.lsst.io/
- FGCM: https://github.com/erykoff/fgcm
- GBDES: https://github.com/gbernstein/gbdes
- obs_nickel documentation: See main README.md
