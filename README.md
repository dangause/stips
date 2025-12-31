# obs_nickel

Gen3 **obs** package for the **Nickel 1-m telescope (Lick Observatory)**.

This package provides:
- Single-detector camera model (`camera/nickel.yaml`)
- FITS metadata translator (`NickelTranslator`)
- Raw data formatter (`NickelRawFormatter`)
- Filter definitions (Johnson/Bessell **B, V**; Cousins **R, I**)
- Complete DRP pipeline for science processing
- Calibration pipeline (bias, flats, defects)
- Ingest and validation tests

> ✅ Tested with `lsst-scipipe-10.1.0` and `lsst-scipipe-11.0.0`

---

## Quick Start

### Prerequisites

1. **LSST Science Pipelines** installed (tested with v10.1+)
2. **Reference catalogs** ingested (Gaia DR3, PS1, or the_monster)
3. **Raw data** from Nickel telescope

### Setup Environment

```bash
# Navigate to your LSST stack
cd /path/to/lsst_stack
source loadLSST.zsh

# Setup the stack and obs_nickel
setup lsst_distrib
eups declare -r /path/to/obs_nickel obs_nickel -t current
setup obs_nickel
```

### Create Repository (First Time Only)

```bash
# Set your paths
export REPO=/path/to/butler/repo
export INSTRUMENT=lsst.obs.nickel.Nickel

# Create and initialize repository
butler create "$REPO"
butler register-instrument "$REPO" "$INSTRUMENT"
```

---

## Running the Pipeline

### Environment Variables

Create a `.env` file in the obs_nickel root with your paths:

```bash
# .env - Edit these paths for your system
REPO=/path/to/butler/repo
STACK_DIR=/path/to/lsst_stack
OBS_NICKEL=/path/to/obs_nickel
RAW_PARENT_DIR=/path/to/raw/data
REFCAT_REPO=/path/to/refcat/repo
CP_PIPE_DIR=${STACK_DIR}/cp_pipe
# Optional: archive client for auto-downloads
LICK_ARCHIVE_DIR=/path/to/lick_searchable_archive
LICK_ARCHIVE_URL=https://archive.ucolick.org/archive
```

### Processing Workflow

The pipeline uses numbered scripts organized in `scripts/pipeline/` for a clear processing flow:

#### Step 0: Bootstrap Repository (One-Time Setup)

Initialize the Butler repository, ingest reference catalogs, and register the skymap:

```bash
./scripts/pipeline/00_bootstrap_repo.sh
```

This script:
- Creates Butler repository if needed
- Ingests Gaia DR3 and PS1 reference catalogs
- Ingests the_monster catalog (if available)
- Chains reference catalogs for automatic selection
- Registers the Nickel skymap

**Run this once** when setting up a new repository.

#### Step 1: Download Archive Data (Optional)

Download a night's raw data from the Lick Observatory archive:

```bash
# Download single night
./scripts/pipeline/01_download_archive.sh --night 20210219

# Or use the Python script directly for more options
./scripts/python/pipeline_tools/fetch_archive_night.py --night 20210219 --overwrite
```

**Skip this step** if you already have raw data locally.

#### Step 2: Process Calibrations (Per Night)

Build nightly calibration products (bias, flats, defects):

```bash
./scripts/pipeline/10_calibs.sh --night YYYYMMDD
```

This script:
- Ingests raw data for the night
- Writes curated calibrations (camera geometry)
- Constructs combined bias frames
- Constructs combined flat fields per filter
- Generates defect masks from flats
- Updates the `Nickel/calib/current` chain

**Run this for each new night** before science processing.

#### Step 3: Process Science Data (Per Night)

Process science images through the DRP pipeline:

```bash
# Basic usage
./scripts/pipeline/20_science.sh --night YYYYMMDD

# Process only specific object (filter by OBJECT header)
./scripts/pipeline/20_science.sh --night 20210219 --object "2020wnt"

# Exclude bad exposures
./scripts/pipeline/20_science.sh --night 20210219 --bad 1032,1051,1052

# Exclude from file
./scripts/pipeline/20_science.sh --night 20210219 --bad-file bad_exposures.txt
```

This script:
- Runs ISR (Instrument Signature Removal)
- Performs source detection and measurement
- Computes astrometric solution (WCS)
- Performs photometric calibration
- Consolidates visit-level catalogs
- Generates quality metrics
- (Optional) Generates coadds

**Run this for each night** after calibrations are built.

#### Step 4: Build Templates (For Difference Imaging)

Build deep coadd templates for difference imaging:

```bash
# Download archival template data
./scripts/pipeline/05_build_template.sh --tract 1099 --band r

# Process template images
./scripts/pipeline/06_process_template.sh --tract 1099 --band r

# Build coadd template
./scripts/pipeline/07_build_coadd_template.sh --tract 1099 --band r
```

**Run these steps** if you plan to do difference imaging.

#### Step 5: Generate Coadds (Optional)

Create coadded images from multiple visits:

```bash
./scripts/pipeline/30_coadds.sh --tract 1099 --band r
```

#### Step 6: Difference Imaging (DIA)

Run difference imaging to detect transients and variable sources:

```bash
# Auto-discover best template (recommended)
./scripts/pipeline/40_diff_imaging.sh --night YYYYMMDD --auto-template

# Use specific template
./scripts/pipeline/40_diff_imaging.sh --night YYYYMMDD --template templates/deep/r

# Process specific object in specific band
./scripts/pipeline/40_diff_imaging.sh \
  --night 20210219 \
  --auto-template \
  --object "2020wnt" \
  --band r
```

This script:
- Reprocesses visit images with full calibration metadata
- Warps template coadds to match science image geometry
- Performs PSF-matched image subtraction (Alard-Lupton)
- Detects and measures difference sources
- Injects sky sources for false positive estimation
- Generates quality metrics

**Run this after science processing** to search for transients/variables.

### Complete Processing Example

```bash
# First time only: bootstrap the repository
./scripts/pipeline/00_bootstrap_repo.sh

# For each new night:
NIGHT=20210219

# 1. Download data (optional, if using archive)
./scripts/pipeline/01_download_archive.sh --night $NIGHT

# 2. Build calibrations
./scripts/pipeline/10_calibs.sh --night $NIGHT

# 3. Process science data
./scripts/pipeline/20_science.sh --night $NIGHT --bad 1032,1051,1052

# Check results
butler query-datasets $REPO preliminary_visit_image \
  --where "day_obs=20210219"
```

### Batch Processing Multiple Nights

For processing multiple nights efficiently, use the batch processing script. **It automatically downloads data from the Lick archive:**

```bash
# Create a nights list file
cat > my_nights.txt <<EOF
20210219
20210220
20210221
EOF

# Download from archive + process all nights (download → calibs → science)
./scripts/pipeline/batch_process_nights.sh --nights-file my_nights.txt

# Process existing data (skip download)
./scripts/pipeline/batch_process_nights.sh --nights-file my_nights.txt --skip-download

# Process with DIA (transient detection)
./scripts/pipeline/batch_process_nights.sh \
  --nights-file my_nights.txt \
  --run-dia \
  --dia-auto-template

# Process only specific object (e.g., supernova 2020wnt) with DIA
./scripts/pipeline/batch_process_nights.sh \
  --nights-file my_nights.txt \
  --object "2020wnt" \
  --skip-calibs \
  --run-dia \
  --dia-template "templates/deep/r"

# With more options
./scripts/pipeline/batch_process_nights.sh \
  --nights-file my_nights.txt \
  -j 16 \
  --continue-on-error \
  --build-template \
  --template-tract 1099 \
  --template-band r
```

**Helper utilities:**

```bash
# Generate nights list from date range
./scripts/python/pipeline_tools/generate_nights_list.py --start 20210219 --end 20210228 -o nights.txt

# Auto-discover nights from raw data directory
./scripts/python/pipeline_tools/generate_nights_list.py --auto-discover -o nights.txt

# Monitor batch processing progress
./scripts/utilities/monitor_batch.sh

# Extract light curves from DIA results
./scripts/utilities/run_extract_lightcurve.sh --ra 56.665 --dec 43.228 --output lightcurve.csv
```

---

## Pipeline Configuration

### Current Calibration State

The pipeline uses **optimized configurations** tuned for Nickel data:

- **Config file**: `configs/calibrateImage/tuned_configs/best_calib_t071.py`
- **Key parameters**:
  - PSF detection threshold: 3.19σ (optimized for Nickel seeing)
  - Astrometry: Relaxed matching for archival data (max offset 500 pixels)
  - Photometry: 3.5" matching radius to handle astrometric residuals
  - Source selection: SNR > 16.3 for astrometry, > 37 for aperture correction

### Reference Catalogs

The pipeline is configured to use:
- **Astrometry**: the_monster catalog (Gaia DR3 + more)
- **Photometry**: the_monster catalog with filter mappings:
  - B → monster_ComCam_g
  - V → monster_ComCam_g
  - R → monster_ComCam_r
  - I → monster_ComCam_i

### Filters

Defined in `python/lsst/obs/nickel/nickelFilters.py`:

| Physical Filter | Band | System         | Central λ |
|----------------|------|----------------|-----------|
| B              | b    | Johnson/Bessell| ~440 nm   |
| V              | v    | Johnson/Bessell| ~550 nm   |
| R              | r    | Cousins        | ~640 nm   |
| I              | i    | Cousins        | ~790 nm   |

---

## Camera Specification

- **Detector**: Single CCD (detector ID: 0)
- **Format**: 1024×1024 imaging area + 32 column overscan
- **Raw frame size**: 1056×1024 pixels
- **Amplifier**: Single readout (A00)
- **Pixel scale**: 0.37"/pixel
- **Field of view**: ~6.3' × 6.3'
- **Gain**: ~1.8 e-/ADU (per camera YAML)
- **Read noise**: ~7 e- (per camera YAML)

See `camera/nickel.yaml` for complete specifications.

---

## Pipeline Products

### Stage 1: Single Visit Processing

| Dataset Type | Description |
|-------------|-------------|
| `post_isr_image` | ISR-corrected exposures |
| `preliminary_visit_image` | Calibrated exposures with WCS/PhotoCalib |
| `single_visit_star` | Detected sources catalog |
| `preliminary_visit_summary` | Visit-level summary statistics |

### Stage 2: Coadds (In Development)

| Dataset Type | Description |
|-------------|-------------|
| `direct_warp` | Resampled visit images |
| `deep_coadd` | Combined coadded images |
| `template_coadd` | Template images for difference imaging |

### Stage 3: Difference Imaging (DIA)

| Dataset Type | Description |
|-------------|-------------|
| `template_coadd` | Reference templates for subtraction |
| `visit_image` | Reprocessed visit images with full metadata |
| `template_detector` | Template warped to science image geometry |
| `difference_image_predetection` | Raw difference image (science - template) |
| `template_matched` | PSF-matched template |
| `difference_kernel` | PSF matching kernel |
| `difference_kernel_sources` | Stars used for kernel fitting |
| `difference_image` | Final difference image with detections |
| `dia_source_unfiltered` | Difference image sources (detections) |
| `dia_source_schema` | Schema for DIA source catalogs |

**Use [scripts/pipeline/40_diff_imaging.sh](scripts/pipeline/40_diff_imaging.sh) for the complete DIA workflow.**

---

## Difference Imaging (DIA) Pipeline

The DIA pipeline detects transients and variable sources by subtracting deep template images from science exposures.

### Overview

**Purpose**: Detect transient sources (supernovae, asteroids, variables) by image subtraction

**Method**: Alard-Lupton PSF-matched image subtraction with quality control

**Key Features**:
- Automatic template discovery from existing coadds
- Optimized PSF matching for varying seeing conditions
- Sky source injection for false positive estimation
- Configurable detection thresholds
- Multi-band support

### DIA Workflow

```
Science Image → Visit Reprocessing → PSF Matching → Subtraction → Detection
                      ↓                    ↓              ↓            ↓
Template Coadd → Warp to Science → Match PSFs → Difference → DIA Sources
```

### Prerequisites

Before running DIA, you need:

1. **Science processing completed** ([20_science.sh](scripts/pipeline/20_science.sh))
   - Produces `preliminary_visit_image` (calibrated science images)
   - Must have good astrometry (< 1" RMS)
   - Must have photometric calibration

2. **Template coadds built** (one of):
   - Multi-night coadds from [30_coadds.sh](scripts/pipeline/30_coadds.sh)
   - External deep templates (e.g., from surveys)
   - Template collections in butler under `templates/*` or `coadds/*`

### Running DIA

#### Single Night DIA

```bash
# Auto-discover best template (recommended)
./scripts/pipeline/40_diff_imaging.sh --night 20210219 --auto-template

# Specify template collection
./scripts/pipeline/40_diff_imaging.sh --night 20210219 --template templates/deep/r

# Filter by object and band
./scripts/pipeline/40_diff_imaging.sh \
  --night 20210219 \
  --auto-template \
  --object "2020wnt" \
  --band r

# Exclude bad exposures
./scripts/pipeline/40_diff_imaging.sh \
  --night 20210219 \
  --auto-template \
  --bad 1032,1051 \
  --bad-file bad_exposures.txt
```

#### Batch DIA Processing

```bash
# Process multiple nights with auto-template discovery
./scripts/pipeline/batch_process_nights.sh \
  --nights-file my_nights.txt \
  --run-dia \
  --dia-auto-template

# Use specific template for all nights
./scripts/pipeline/batch_process_nights.sh \
  --nights-file my_nights.txt \
  --run-dia \
  --dia-template "templates/deep/r"
```

### DIA Configuration

DIA-specific configurations are in [configs/dia/](configs/dia/):

**[subtractImages.py](configs/dia/subtractImages.py)** - PSF matching and image subtraction:
- Kernel size: 21 pixels (~3× median FWHM)
- Spatial order: 2 (polynomial kernel variation across field)
- Background subtraction: enabled with 128-pixel bins
- Kernel stars: 50-sigma detection threshold

**[detectAndMeasure.py](configs/dia/detectAndMeasure.py)** - DIA source detection:
- Detection threshold: 3.0-sigma (optimized for transients)
- Minimum pixels: 5 connected pixels
- Both positive and negative detections
- Sky source injection: 100 sources per visit for FP estimation

### Analyzing DIA Results

#### Light Curve Extraction

Extract photometry for a specific transient/variable:

```bash
# By coordinates
python scripts/python/pipeline_tools/extract_lightcurve.py \
  --repo $REPO \
  --collection "Nickel/runs/*/diff/*/run" \
  --ra 123.456 --dec +12.345 \
  --radius 1.0 \
  --output lightcurve.csv

# By object name (SIMBAD/NED lookup)
python scripts/python/pipeline_tools/extract_lightcurve.py \
  --repo $REPO \
  --collection "Nickel/runs/20210*/diff/*/run" \
  --object "AT2021abc" \
  --output lightcurve_AT2021abc.csv

# Filter by band and minimum S/N
python scripts/python/pipeline_tools/extract_lightcurve.py \
  --repo $REPO \
  --collection "Nickel/runs/*/diff/*/run" \
  --ra 123.456 --dec +12.345 \
  --band r \
  --min-snr 5.0 \
  --output lightcurve_filtered.csv
```

Output CSV contains: MJD, band, visit, RA, Dec, flux, flux_err, mag, mag_err, S/N, separation

#### Quality Assessment

Assess DIA processing quality for a night:

```bash
python scripts/python/pipeline_tools/assess_dia_quality.py \
  --repo $REPO \
  --collection "Nickel/runs/20210219/diff/*/run" \
  --night 20210219 \
  --output dia_quality_20210219.txt
```

Quality report includes:
- Number of difference images and sources
- Sources per visit statistics
- False positive rate estimate (from sky sources)
- Per-band breakdown
- Quality flags and warnings

#### Querying DIA Results

```bash
# List difference images for a night
butler query-datasets $REPO difference_image \
  --collections "Nickel/runs/20210219/diff/*/run" \
  --where "instrument='Nickel' AND day_obs=20210219"

# Count DIA sources per visit
butler query-datasets $REPO dia_source_unfiltered \
  --collections "Nickel/runs/20210219/diff/*/run" \
  --where "instrument='Nickel' AND day_obs=20210219"

# Query visits with most detections (potential transient-rich fields)
# (requires loading catalogs and counting sources)
```

### DIA Troubleshooting

**Common Issues**:

1. **"No template collections found"**
   - Build templates first: `./scripts/pipeline/30_coadds.sh --tract 1099 --band r`
   - Or manually create template collection chain in butler

2. **"Template doesn't cover tract/patch"**
   - Science exposures outside template footprint
   - Check overlap: `butler query-datasets $REPO template_coadd --where "tract=1099"`

3. **"Insufficient kernel stars for PSF matching"**
   - Science or template image has poor seeing / few stars
   - Check image quality and field density
   - May need to adjust `detection.thresholdValue` in `configs/dia/subtractImages.py`

4. **High false positive rate (> 50%)**
   - Image quality mismatch (seeing, depth) between science and template
   - Poor astrometric alignment (check science WCS quality)
   - Detection threshold too aggressive (increase from 3.0 to 5.0 sigma)

5. **Very few DIA sources detected (< 5 per visit)**
   - Detection threshold too conservative
   - Template too deep (no transients visible)
   - Check difference image visually for actual transients

### Template Date Range Management

**Critical for transient observations!** When observing transients (supernovae, variables), you must avoid using templates that include observations when the transient was visible.

#### Automatic Metadata Recording

When building templates with [30_coadds.sh](scripts/pipeline/30_coadds.sh), metadata about date ranges is **automatically recorded** to `$REPO/template_metadata.json`.

#### Excluding Contaminated Date Ranges

For a supernova campaign from Feb 19-28, 2021:

```bash
# Build "pre-campaign" template (before transient appeared)
./scripts/pipeline/30_coadds.sh \
  --nights-file pre_campaign_nights.txt \
  --tract 1099 \
  --band r

# Run DIA excluding the campaign dates
./scripts/pipeline/40_diff_imaging.sh \
  --night 20210225 \
  --auto-template \
  --exclude-start 20210219 \
  --exclude-end 20210228
# → Only selects templates that don't overlap with Feb 19-28

# Batch processing with date exclusion
./scripts/pipeline/batch_process_nights.sh \
  --nights-file campaign_nights.txt \
  --run-dia \
  --dia-auto-template \
  --dia-exclude-start 20210219 \
  --dia-exclude-end 20210228
```

#### Managing Template Metadata

```bash
# List all template metadata
python scripts/python/pipeline_tools/template_metadata.py list --repo $REPO

# Manually record metadata for external template
python scripts/python/pipeline_tools/template_metadata.py record \
  --repo $REPO \
  --collection templates/external/r \
  --start 20200101 \
  --end 20201231 \
  --tract 1099 \
  --band r

# Query templates excluding specific dates
python scripts/python/pipeline_tools/template_metadata.py query \
  --repo $REPO \
  --exclude-start 20210219 \
  --exclude-end 20210228 \
  --band r
```

### Advanced DIA Usage

#### Using External Templates

If you have external deep templates (e.g., from other surveys):

```bash
# 1. Ingest templates as Butler datasets
butler ingest-files $REPO <template_files> --dataset-type template_coadd

# 2. Create template collection
butler collection-chain $REPO templates/external template_coadd_run

# 3. Record metadata for date filtering
python scripts/python/pipeline_tools/template_metadata.py record \
  --repo $REPO \
  --collection templates/external \
  --start 20200101 \
  --end 20201231 \
  --description "External survey template"

# 4. Run DIA with external templates
./scripts/pipeline/40_diff_imaging.sh \
  --night 20210219 \
  --template templates/external
```

#### Pipeline Modes

The DIA pipeline supports two modes:

1. **Standalone mode** (default): Uses [pipelines/DIA.yaml](pipelines/DIA.yaml)
   - Self-contained DIA pipeline
   - Faster for DIA-only processing

2. **Integrated mode**: Uses DRP.yaml#difference-imaging subset
   - Part of full DRP pipeline
   - Better for combined processing

```bash
# Standalone (default)
./scripts/pipeline/40_diff_imaging.sh --night 20210219 --auto-template

# Integrated
./scripts/pipeline/40_diff_imaging.sh \
  --night 20210219 \
  --auto-template \
  --pipeline integrated
```

### Specialized DIA Workflows

For specific observing campaigns, use the dedicated workflow scripts instead of batch processing:

#### Complete End-to-End Pipeline (Transients)

Use [scripts/pipeline/run_full_transient_pipeline.sh](scripts/pipeline/run_full_transient_pipeline.sh) to run the complete pipeline from raw data to DIA analysis in a single command.

**This script runs all stages**:
1. Bootstrap repository (00_bootstrap_repo.sh)
2. Download raw data (fetch_archive_night.py) - optional
3. Build calibrations & ingest raws (10_calibs.sh)
4. Single-frame processing (20_science.sh / processCcd)
5. Build template (30_coadds.sh via 50_transient_dia.sh)
6. Run DIA (40_diff_imaging.sh)
7. Extract light curve
8. Generate quality reports

**Example - Complete pipeline**:
```bash
# Create nights files
cat > template_nights.txt <<EOF
20201207
20201215
20201223
EOF

cat > campaign_nights.txt <<EOF
20210219
20210220
EOF

# Run entire pipeline from scratch
./scripts/pipeline/run_full_transient_pipeline.sh \
  --template-nights template_nights.txt \
  --dia-nights campaign_nights.txt \
  --band r \
  --transient-name "SN2020wnt" \
  --ra 83.8145 \
  --dec 3.0847 \
  --jobs 4
```

**Example - Resume from processCcd** (if you've already run calibs):
```bash
./scripts/pipeline/run_full_transient_pipeline.sh \
  --template-nights template_nights.txt \
  --dia-nights campaign_nights.txt \
  --band r \
  --transient-name "SN2020wnt" \
  --ra 83.8145 \
  --dec 3.0847 \
  --skip-bootstrap \
  --skip-download \
  --skip-calibs
```

**Key flags**:
- `--template-nights FILE`: Nights for template (pre-transient)
- `--dia-nights FILE`: Nights for DIA (during/after transient)
- `--band BAND`: Filter band (required)
- `--ra / --dec`: Coordinates for light curve extraction and auto-tract
- `--skip-bootstrap / --skip-download / --skip-calibs / --skip-processccd`: Resume from specific stage
- `--skip-template / --skip-dia / --skip-lightcurve`: Skip DIA workflow stages

#### Transient/Supernova Campaigns (DIA Only)

Use [scripts/pipeline/50_transient_dia.sh](scripts/pipeline/50_transient_dia.sh) for transient observations where template contamination is critical.

**Note**: This script assumes you've already run stages 00-20 (bootstrap, download, 10_calibs, 20_science). Use `run_full_transient_pipeline.sh` if starting from scratch.

**Features**:
- Separate template and science night lists
- Automatic date exclusion to prevent template contamination
- Light curve extraction for transient coordinates
- Quality assessment reports

**Example workflow**:

```bash
# 1. Create nights files
cat > template_nights.txt <<EOF
20201207
20201215
20201223
20210101
EOF

cat > campaign_nights.txt <<EOF
20210219
20210220
20210225
20210228
EOF

# 2. Run DIA workflow only (assumes stages 00-20 already complete)
# Note: --tract is optional when --ra/--dec provided (auto-determined from coordinates)
./scripts/pipeline/50_transient_dia.sh \
  --template-nights template_nights.txt \
  --dia-nights campaign_nights.txt \
  --band r \
  --transient-name "SN2021abc" \
  --ra 150.123 \
  --dec 2.456 \
  --jobs 8 \
  --output-dir ./sn2021abc_results

# Output:
#   ./sn2021abc_results/
#   ├── SN2021abc_lightcurve.ecsv
#   ├── SN2021abc_quality_20210219.txt
#   ├── SN2021abc_quality_20210220.txt
#   └── ...
```

**Key flags**:
- `--template-nights FILE`: Nights to use for building template (pre-transient)
- `--dia-nights FILE`: Nights to process with DIA (during/after transient)
- `--band BAND`: Filter band (required)
- `--tract NUM`: Sky tract (optional if --ra/--dec provided - will auto-determine)
- `--transient-name NAME`: Name for output files and collections
- `--ra / --dec`: Coordinates for light curve extraction (also enables auto-tract)
- `--skip-template`: Skip template building (use existing)
- `--skip-dia`: Only extract light curve from existing DIA results
- `--skip-lightcurve`: Only build template and run DIA

#### Variable Star Monitoring

Use [scripts/pipeline/50_variable_dia.sh](scripts/pipeline/50_variable_dia.sh) for variable star observations.

**Note**: This script assumes you've already run stages 00-20 (bootstrap, ingest, processCcd). For a complete end-to-end variable star pipeline, you can adapt `run_full_transient_pipeline.sh`.

**Features**:
- Single nights list (can overlap template and science)
- Multiple template selection strategies (first, best seeing, evenly spread)
- Rolling template mode (rebuild for each night)
- Batch light curve extraction for multiple targets

**Example workflow**:

```bash
# 1. Create nights list
cat > m67_nights.txt <<EOF
20201207
20201215
20201223
20210101
20210115
20210201
EOF

# 2. Create targets file (RA Dec Name)
cat > m67_variables.txt <<EOF
132.8458  11.8144  V1
132.8521  11.8067  V2
132.8395  11.8211  V3
132.8612  11.8189  V4
EOF

# 3. Run variable star workflow (assumes stages 00-20 already complete)
# Note: --tract is optional when --targets-file provided (auto-determined from first target)
./scripts/pipeline/50_variable_dia.sh \
  --nights m67_nights.txt \
  --band r \
  --field-name "M67" \
  --targets-file m67_variables.txt \
  --template-fraction 0.5 \
  --template-selection best \
  --seeing-file seeing_log.txt \
  --jobs 8 \
  --output-dir ./m67_variables

# Output:
#   ./m67_variables/
#   ├── M67_V1_lightcurve.ecsv
#   ├── M67_V2_lightcurve.ecsv
#   ├── M67_V3_lightcurve.ecsv
#   ├── M67_V4_lightcurve.ecsv
#   ├── M67_quality_summary.txt
#   └── ...
```

**Template selection strategies**:
- `first`: Use first N nights chronologically (default)
- `best`: Use N nights with best seeing (requires `--seeing-file`)
- `spread`: Use evenly distributed nights across time baseline

**Rolling template mode**:
```bash
# Build new template for each night (excluding that night)
# Useful for detecting rare variables that might contaminate static template
./scripts/pipeline/50_variable_dia.sh \
  --nights m67_nights.txt \
  --tract 1099 \
  --band r \
  --field-name "M67" \
  --rolling-template \
  --targets-file m67_variables.txt
```

**Key flags**:
- `--nights FILE`: All nights for processing
- `--band BAND`: Filter band (required)
- `--tract NUM`: Sky tract (optional if --targets-file provided - will auto-determine)
- `--template-fraction NUM`: Fraction of nights for template (0.0-1.0, default: 0.5)
- `--template-selection MODE`: How to select template nights (first/best/spread)
- `--seeing-file FILE`: Seeing measurements for "best" selection
- `--targets-file FILE`: Variable star positions for light curve extraction (also enables auto-tract)
- `--rolling-template`: Rebuild template for each night (CPU intensive)
- `--field-name NAME`: Field identifier for output files

---

## Logging

Pipeline scripts write logs to `logs/{RUN_ID}/` with nested organization by stage:

```
logs/
  └── YYYYMMDD_HHMMSS_{pid}/
      ├── run_info.txt           # Run metadata
      ├── summary.txt            # Final statistics
      ├── bootstrap/             # 00_bootstrap_repo.sh
      ├── calibs/{night}/        # 10_calibs.sh
      │   ├── calibs.log
      │   ├── cpBias.log
      │   └── cpFlat.log
      ├── science/{night}/       # 20_science.sh
      │   ├── science.log
      │   ├── processCcd.log
      │   └── coadds.log
      ├── templates/{band}/tract_{tract}/  # 30_coadds.sh
      └── dia/{night}/{band}/    # 40_diff_imaging.sh
          ├── dia.log
          ├── quantum.log
          └── results.txt
```

All logs include timestamps and are saved to both file and console. Each pipeline run gets a unique `RUN_ID` that groups all related logs together.

---

## Directory Structure

```
obs_nickel/
├── camera/                    # Camera geometry YAML
├── configs/                   # Pipeline configuration overrides
│   ├── calibrateImage/
│   │   ├── tuned_configs/    # Optimized configs (best_calib_t071.py)
│   │   ├── apcorr/           # Aperture correction configs
│   │   ├── astrometry/       # Astrometry configs
│   │   └── psf_*/            # PSF detection/measurement configs
│   ├── dia/                  # Difference imaging configs
│   │   ├── subtractImages.py        # PSF matching configuration
│   │   └── detectAndMeasure.py      # DIA source detection
│   ├── colorterms.py         # Color term corrections
│   ├── filter_map.py         # Filter to reference catalog mapping
│   └── makeSkyMap*.py        # SkyMap configuration
├── pipelines/                 # Pipeline definitions
│   ├── DRP.yaml              # Full data release processing (DIA enabled)
│   ├── DIA.yaml              # Standalone difference imaging pipeline
│   ├── ProcessCcd.yaml       # Single visit processing
│   ├── experimental/         # Test/experimental pipelines
│   │   └── DIA_test.yaml
│   └── *.yaml                # Analysis pipelines
├── python/lsst/obs/nickel/   # Python package
│   ├── _instrument.py        # Instrument class
│   ├── translator.py         # FITS header translator
│   ├── rawFormatter.py       # Raw data formatter
│   └── nickelFilters.py      # Filter definitions
├── scripts/                   # Processing scripts (organized)
│   ├── pipeline/             # Main processing workflow
│   │   ├── 00_bootstrap_repo.sh        # Initialize repository
│   │   ├── 01_download_archive.sh      # Download raw data
│   │   ├── 05-07_build_template*.sh    # Template building
│   │   ├── 10_calibs.sh                # Calibration processing
│   │   ├── 20_science.sh               # Science processing
│   │   ├── 30_coadds.sh                # Coadd generation
│   │   ├── 40_diff_imaging.sh          # Difference imaging
│   │   ├── 50_transient_dia.sh         # DIA workflow for transients
│   │   ├── 50_variable_dia.sh          # DIA workflow for variables
│   │   ├── run_full_transient_pipeline.sh  # Complete end-to-end pipeline
│   │   └── batch_process_nights.sh     # Batch orchestrator
│   ├── python/               # Python helper scripts
│   │   ├── data/            # Data handling
│   │   │   ├── fetch_archive_night.py       # Download archive data
│   │   │   ├── generate_nights_list.py      # Generate nights lists
│   │   │   ├── extract_lightcurve.py        # DIA lightcurve extraction
│   │   │   └── assess_dia_quality.py        # DIA quality assessment
│   │   ├── skymap/          # SkyMap builders
│   │   ├── calibration/     # Calibration tools (colorterms)
│   │   └── defects_tools/   # Defect mask generation
│   ├── utilities/            # Helper utilities
│   │   ├── monitor_batch.sh
│   │   ├── run_extract_lightcurve.sh
│   │   └── stack-activate.sh
│   ├── test/                 # Debug/test scripts
│   └── config/               # Example configuration files
├── tests/                     # Unit tests (pytest)
├── tuning/                    # Config optimization framework
│   └── calibrate_pipe_tuner/ # Automated parameter tuning
└── README.md                  # This file
```

---

## Butler Collections

The pipeline uses a hierarchical collection structure:

```
Nickel/
├── raw/
│   └── YYYYMMDD/            # Raw data by night
│       └── TIMESTAMP/
├── calib/
│   ├── current              # CHAIN: Latest calibrations
│   ├── curated              # CHAIN: Camera geometry
│   ├── defects/             # Defect masks
│   ├── YYYYMMDD/            # Nightly calibrations
│   └── cp/                  # Calibration products
│       └── YYYYMMDD/
│           ├── bias/
│           └── flat/
├── runs/
│   └── YYYYMMDD/            # Science processing
│       ├── processCcd/
│       ├── coadd/
│       └── diff/
└── refcats                   # CHAIN: Reference catalogs
```

---

## Testing

### Unit Tests

Run the full test suite:

```bash
# Requires testdata_nickel package
pytest -v
```

Individual test modules:
- `tests/test_translator.py` - FITS header translation
- `tests/test_instrument.py` - Camera and filter registration
- `tests/test_ingest.py` - Raw data ingest and visit definition

### Integration Tests

Process test data:

```bash
# Setup test environment
export TESTDATA_NICKEL_DIR=/path/to/testdata_nickel
setup testdata_nickel

# Run simple processing test
./scripts/run_processCcd_and_visits.sh
```

---

## Configuration Tuning

The pipeline includes an automated tuning framework in `tuning/calibrate_pipe_tuner/`:

```bash
# Run parameter optimization
python -m tuning.calibrate_pipe_tuner.cli \
  --repo "$REPO" \
  --obs-nickel "$OBS_NICKEL" \
  --workdir tuning/results \
  --trials 50 \
  --config tuning/tune.yaml
```

This optimizes:
- PSF detection thresholds
- Source selection criteria
- Astrometric matching parameters
- Aperture correction settings

---

## Common Issues and Solutions

### Issue: "No matches to use for photocal"

**Cause**: Photometric matching radius too small for astrometric residuals.

**Solution**: Already fixed in `best_calib_t071.py`:
```python
config.photometry.match.matchRadius = 3.5  # Increased from 1.5"
config.photometry.minMatches = 3           # Reduced from ~10
```

### Issue: Astrometry failures

**Cause**: Poor initial WCS in archival data.

**Solution**: Already relaxed in `best_calib_t071.py`:
```python
config.astrometry.matcher.maxOffsetPix = 500        # Increased from 300
config.astrometry.maxMeanDistanceArcsec = 100.0     # Increased from 60
```

### Issue: Not enough PSF stars

**Cause**: Detection threshold too high or poor seeing.

**Solution**: Lower threshold in config:
```python
config.psf_detection.thresholdValue = 3.2  # Already optimized
```

---

## Development

### Code Quality

Pre-commit hooks are configured for linting and formatting:

```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

### Adding New Features

1. Create feature branch: `git checkout -b feature-name`
2. Make changes and add tests
3. Run tests: `pytest`
4. Run linting: `pre-commit run --all-files`
5. Submit pull request

### Continuous Integration

GitHub Actions CI runs on all PRs:
- Linting with ruff
- Unit tests with pytest
- Integration tests with test data

See `.github/workflows/ci.yml` for details.

---

## Roadmap

### Current Status (v1.0)

- ✅ Single-visit processing (ISR through calibrateImage)
- ✅ Optimized config for Nickel data
- ✅ Calibration pipeline (bias, flats, defects)
- ✅ Reference catalog integration

### Recently Added

- ✅ Coadd generation (template building)
- ✅ Difference imaging pipeline (DIA)
- ✅ Light curve extraction

### In Development

- 🚧 Archival data processing mode
- 🚧 Color term refinement
- 🚧 DIA production integration (enable in DRP.yaml)

### Future Plans

- Automated standard star calibration
- Real-time processing mode
- Advanced QA metrics and visualization
- Multi-night calibration tracking

---

## Contributing

Contributions are welcome! Please:
1. Follow the existing code style
2. Add tests for new features
3. Update documentation
4. Submit pull requests against `main`

---

## References

- **LSST Science Pipelines**: https://pipelines.lsst.io
- **Butler Gen3**: https://pipelines.lsst.io/modules/lsst.daf.butler
- **Obs Base**: https://github.com/lsst/obs_base

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
