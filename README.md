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

The pipeline uses a numbered script workflow for clarity:

#### Step -1 (optional): Fetch raws from the Lick archive

Download a night's raws directly into the layout expected by the ingest scripts:

```bash
# If you haven't pip-installed the archive client, point to your clone:
export LICK_ARCHIVE_DIR=~/Developer/lick/lick_searchable_archive

# Pull raws for a local observing night (noon→noon Pacific) into $RAW_PARENT_DIR/20210219/raw/
./scripts/fetch_archive_night.py --night 20210219
```

#### Step 0: Bootstrap Repository (One-Time Setup)

Initialize the Butler repository, ingest reference catalogs, and register the skymap:

```bash
./scripts/00_bootstrap_repo.sh
```

This script:
- Creates Butler repository if needed
- Ingests Gaia DR3 and PS1 reference catalogs
- Ingests the_monster catalog (if available)
- Chains reference catalogs for automatic selection
- Registers the Nickel skymap

**Run this once** when setting up a new repository.

#### Step 1: Process Calibrations (Per Night)

Build nightly calibration products:

```bash
./scripts/10_calibs.sh --night YYYYMMDD
```

This script:
- Ingests raw data for the night
- Writes curated calibrations (camera geometry)
- Constructs combined bias frames
- Constructs combined flat fields per filter
- Generates defect masks from flats
- Updates the `Nickel/calib/current` chain

**Run this for each new night** before science processing.

#### Step 2: Process Science Data (Per Night)

Process science images through the DRP pipeline:

```bash
# Basic usage
./scripts/20_science.sh --night YYYYMMDD

# Exclude bad exposures
./scripts/20_science.sh --night 20210219 --bad 1032,1051,1052

# Exclude from file
./scripts/20_science.sh --night 20210219 --bad-file bad_exposures.txt
```

This script:
- Runs ISR (Instrument Signature Removal)
- Performs source detection and measurement
- Computes astrometric solution (WCS)
- Performs photometric calibration
- Consolidates visit-level catalogs
- (Optional) Generates coadds
- (Optional) Runs difference imaging

**Run this for each night** after calibrations are built.

### Complete Processing Example

```bash
# First time only: bootstrap the repository
./scripts/00_bootstrap_repo.sh

# For each new night:
NIGHT=20210219

# 1. Build calibrations
./scripts/10_calibs.sh --night $NIGHT

# 2. Process science data
./scripts/20_science.sh --night $NIGHT --bad 1032,1051,1052

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

# Download from archive + process all nights (download → calibs → science → coadds)
./scripts/batch_process_nights.sh --nights-file my_nights.txt

# Process existing data (skip download)
./scripts/batch_process_nights.sh --nights-file my_nights.txt --skip-download

# With more options
./scripts/batch_process_nights.sh \
  --nights-file my_nights.txt \
  -j 16 \
  --continue-on-error \
  --build-template \
  --template-tract 1099 \
  --template-band r
```

**Helper scripts for batch processing:**

```bash
# Generate nights list from date range
./scripts/generate_nights_list.py --start 20210219 --end 20210228 -o nights.txt

# Auto-discover nights from raw data directory
./scripts/generate_nights_list.py --auto-discover -o nights.txt

# Monitor batch processing progress
./scripts/monitor_batch.sh
```

See [scripts/BATCH_PROCESSING.md](scripts/BATCH_PROCESSING.md) for detailed documentation.

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

### Stage 3: Difference Imaging

| Dataset Type | Description |
|-------------|-------------|
| `template_coadd` | Reference templates for subtraction |
| `difference_image` | Science - Template subtracted images |
| `dia_source_unfiltered` | Difference image sources |

**See [DIA.md](DIA.md) for complete DIA workflow and documentation.**

---

## Directory Structure

```
obs_nickel/
├── camera/                    # Camera geometry YAML
├── configs/                   # Pipeline configuration overrides
│   ├── calibrateImage/
│   │   └── tuned_configs/    # Optimized configs
│   └── colorterms.py         # Color term corrections
├── pipelines/                 # Pipeline definitions
│   ├── DRP.yaml              # Full data release processing
│   └── ProcessCcd.yaml       # Single visit processing
├── python/lsst/obs/nickel/   # Python package
│   ├── translator.py         # FITS header translator
│   ├── rawFormatter.py       # Raw data formatter
│   └── nickelFilters.py      # Filter definitions
├── scripts/                   # Processing scripts
│   ├── 00_bootstrap_repo.sh  # Repository setup
│   ├── 10_calibs.sh          # Calibration processing
│   ├── 20_science.sh         # Science processing
│   ├── 30_coadds.sh          # Template building
│   ├── 40_diff_imaging.sh    # DIA pipeline
│   ├── run_extract_lightcurve.sh # Light curve extraction
│   └── defects/              # Defect mask tools
├── tests/                     # Unit tests
└── tuning/                    # Config optimization tools
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
