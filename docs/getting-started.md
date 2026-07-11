# Getting Started with STIPS

This guide walks you through setting up the Small Telescope Image Processing Suite and running your first pipeline.

## Prerequisites

Before you begin, ensure you have:

1. **Python 3.12+** installed
2. **LSST Science Pipelines** — supported release **`v30_0_3`** (the version the
   Docker images build on and the docs are validated against). CI additionally
   pins the weekly **`w_2025_32`**; newer weeklies usually work but are validated
   only by the scheduled `w_latest` canary. Before upgrading the stack, follow
   the [stack-bump runbook](stack-bump-runbook.md).
3. **UV package manager** installed:
   ```bash
   pip install uv
   # or
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
4. **Raw Nickel data** (FITS files organized by night)
5. **Reference catalogs** (Gaia DR3, PS1, optionally the_monster)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/dangause/stips.git
cd stips
```

### 2. Install Dependencies

```bash
# Minimal setup (CLI + core packages)
uv sync --group dev

# Full setup (includes Jupyter, analysis tools)
uv sync --all-groups
```

### 3. Verify Installation

```bash
# Check CLI is available
stips --help

# Check LSST stack is accessible
source /path/to/lsst_stack/loadLSST.bash
setup lsst_distrib
python -c "from lsst.daf.butler import Butler; print('OK')"
```

## Quick Start: Your First Pipeline

The fastest way to run STIPS is using a YAML configuration file.

### Option A: Use an Existing Campaign Config

```bash
# Run the SN 2023ixf pipeline (edit paths first!)
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml run --dry-run

# If the dry run looks good, run for real
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml run
```

### Option B: Create a Minimal Config

Create a file `my_pipeline.yaml`:

```yaml
# Minimal pipeline configuration
env:
  REPO: "/path/to/my/butler_repo"
  STACK_DIR: "/path/to/lsst_stack"
  INSTRUMENT_DIR: "/path/to/stips/instruments/nickel"
  RAW_PARENT_DIR: "/path/to/raw/data"
  REFCAT_REPO: "/path/to/refcats"

# Target information
object: "my_target"
ra: 123.456
dec: 45.678

# Bands to process
bands: ["r", "i"]

# Template type
template:
  type: ps1
  degrade_seeing: 2.0

# Nights to process (empty list = all visits)
nights:
  20240101:
    r: []
    i: []

# Processing options
options:
  jobs: 8
  forced_phot: true

# Lightcurve extraction
lightcurve:
  enabled: true
  dataset_type: forced_phot_diffim_radec
  min_snr: 1
  y_axis: apparent_mag
  x_axis: mjd
```

Then run:

```bash
stips -c my_pipeline.yaml run
```

## Understanding What Happens

When you run `stips -c pipeline.yaml run`, STIPS automatically:

1. **Bootstraps** the Butler repository (if it doesn't exist)
2. **Ingests PS1 templates** for the specified bands
3. **For each night:**
   - Runs calibrations (bias, flat)
   - Runs science processing (ISR, WCS, photometry)
   - Runs difference imaging
   - Runs forced photometry at your target coordinates
4. **Extracts a combined light curve** from all nights

## Step-by-Step Alternative

If you prefer more control, run each step individually:

```bash
# 1. Check your configuration
stips env

# 2. Bootstrap the repository
stips -c my_pipeline.yaml bootstrap

# 3. Process calibrations for a night
stips calibs 20240101

# 4. Process science frames (--ra/--dec enables coordinate validation)
stips science 20240101 --object my_target --ra 123.456 --dec 45.678

# 5. Ingest PS1 template
stips ps1-template --ra 123.456 --dec 45.678 --band r

# 6. Run difference imaging
stips dia 20240101 --auto --band r

# 7. Run forced photometry
stips fphot 20240101 --ra 123.456 --dec 45.678

# 8. Extract light curve
stips lightcurve --ra 123.456 --dec 45.678 \
    --collections "Nickel/runs/*/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "My Target" \
    --y-axis apparent_mag --x-axis mjd
```

## Output Files

After a successful run, you'll find:

| Location | Contents |
|----------|----------|
| `{REPO}/` | Butler repository with all data products |
| `{REPO}/lightcurves/` | Light curve CSV files and plots |
| `{REPO}/processing_log/` | JSON logs tracking processing status |

## Common Issues

### "LSST stack not found"

Make sure `STACK_DIR` points to a valid LSST installation:

```bash
ls $STACK_DIR/loadLSST.bash  # Should exist
```

### "No calibration frames found"

Ensure your raw data directory has the expected structure:

```
RAW_PARENT_DIR/
└── YYYYMMDD/
    └── raw/
        ├── bias_001.fits
        ├── flat_r_001.fits
        └── science_001.fits
```

### "Bootstrap failed"

Run from the stips directory:

```bash
cd /path/to/stips
stips -c my_pipeline.yaml bootstrap
```

### "FileNotFoundError: astrometry_ref_cat" during science processing

This usually means some exposures have incorrect coordinates in their FITS headers (a known Nickel telescope issue where the DEC keyword gets stuck). When using `stips run` with a pipeline YAML, coordinate validation is automatic. For standalone commands, pass `--ra` and `--dec` to enable it:

```bash
stips science 20230519 --object 2023ixf --ra 210.91 --dec 54.32
```

### `ModuleNotFoundError` or stale paths after moving/renaming the checkout

The `.venv` is an editable install: it records **absolute** paths to the
packages (via `.pth` files) at install time. If you move, rename, or copy the
repository checkout to a new location, a `.venv` carried over from the old path
points at packages that no longer exist there, producing import errors or
picking up a stale copy. Rebuild the environment from scratch:

```bash
rm -rf .venv && uv sync --group dev
```


## Next Steps

- See [Starting a New Campaign](new-campaign.md) for new transient targets
- Explore [Architecture Overview](architecture.md) to understand how STIPS works

## Getting Help

- Check existing [pipeline configs](../scripts/config/) for examples
- Review [processing logs](../README.md#processing-logs) when things fail
- Open an issue on GitHub for bugs or questions
