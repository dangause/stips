# Nickel Template DIA Guide

Complete workflow for running Difference Image Analysis (DIA) using Nickel telescope deep coadd templates.

## Overview

This guide covers the **Nickel-built template workflow**, where you create deep templates from multiple nights of Nickel observations and use them for difference imaging.

**When to use Nickel templates vs PS1 templates:**
- **Nickel templates**: Better matched PSF, same filter system, optimal for well-observed fields
- **PS1 templates**: Deeper, available for any field, but PSF/filter mismatch possible

## Quick Start

### Automated Test Workflow

For testing the complete pipeline:

```bash
# Edit test configuration in the script first
./scripts/pipeline/test_nickel_template_dia.sh --repo $REPO
```

This runs the full workflow:
1. Template night calibrations
2. Template night science processing
3. Deep template building
4. Science night calibrations
5. Science night science processing
6. Difference imaging
7. Light curve extraction

### Manual Workflow

For production use with custom configuration:

## Step-by-Step Workflow

### Prerequisites

1. **Bootstrap repository** (one-time setup):
   ```bash
   ./scripts/pipeline/00_bootstrap_repo.sh
   ```

2. **Download raw data** for both template and science nights:
   ```bash
   NIGHT=20201207 ./scripts/pipeline/01_download_archive.sh
   NIGHT=20220105 ./scripts/pipeline/01_download_archive.sh
   # ... repeat for all nights
   ```

### Step 1: Choose Template Nights

Select nights for building your deep template:

**Selection criteria:**
- Pre-transient observations (avoid contamination)
- Good seeing (< 2.5" for best PSF matching)
- Photometric conditions
- Same filter as your science observations
- Multiple nights (3-5 recommended) for depth

**Example template selection:**
```bash
# For SN 2020wnt (first detected Jan 2022)
# Choose pre-SN nights in R-band from 2020-2021
TEMPLATE_NIGHTS=(
    20201207
    20201219
    20210208
    20210218
)
```

Create a nights file:
```bash
cat > template_nights.txt <<EOF
20201207
20201219
20210208
20210218
EOF
```

### Step 2: Process Template Nights

#### 2a. Process Calibrations

For each template night:

```bash
./scripts/pipeline/10_calibs.sh --night 20201207 -j 8
./scripts/pipeline/10_calibs.sh --night 20201219 -j 8
# ... repeat for all template nights
```

**What this does:**
- Constructs bias frames
- Constructs flat frames
- Identifies and masks defects
- Creates calibration products in `Nickel/calib/...` collections

#### 2b. Process Science Images

For each template night:

```bash
./scripts/pipeline/20_science.sh \
    --night 20201207 \
    --skip-coadds \
    -j 8

./scripts/pipeline/20_science.sh \
    --night 20201219 \
    --skip-coadds \
    -j 8
# ... repeat for all template nights
```

**What this does:**
- ISR (bias/flat correction, cosmic ray removal)
- Astrometric calibration (Gaia DR3 via the_monster)
- Photometric calibration (PS1 via the_monster)
- PSF modeling
- Creates `preliminary_visit_image` datasets

**Note:** We use `--skip-coadds` because we'll build multi-night coadds separately.

### Step 3: Build Deep Template Coadd

Combine all template nights into a deep template:

```bash
./scripts/pipeline/30_coadds.sh \
    --tract 1099 \
    --band r \
    --nights-file template_nights.txt \
    -j 8
```

**Required parameters:**
- `--tract`: Tract ID covering your field (find with skymap queries)
- `--band`: Filter band (b, v, r, i)
- `--nights-file`: File listing template nights

**Optional parameters:**
- `--patch PATCH`: Build specific patch only (default: all patches in tract)
- `-o COLLECTION`: Custom output collection name

**What this does:**
- Warps all `preliminary_visit_image` to common sky grid
- Combines images with outlier rejection
- Creates deep PSF model
- Produces `template_coadd` dataset

**Output collection format:**
```
templates/deep/tract{TRACT}/{BAND}/{TIMESTAMP}
```

Example:
```
templates/deep/tract1099/r/20251224T120000Z
```

**Verify template:**
```bash
# List template coadds
butler query-datasets $REPO template_coadd \
    --collections 'templates/deep/tract1099/r/*'

# Check coverage
butler query-datasets $REPO template_coadd \
    --collections 'templates/deep/tract1099/r/*' \
    --where "tract=1099 AND band='r'"
```

### Step 4: Process Science Nights

Now process the nights containing your transient/variable:

#### 4a. Process Calibrations

```bash
./scripts/pipeline/10_calibs.sh --night 20220105 -j 8
./scripts/pipeline/10_calibs.sh --night 20220108 -j 8
# ... repeat for all science nights
```

#### 4b. Process Science Images

```bash
./scripts/pipeline/20_science.sh \
    --night 20220105 \
    --skip-coadds \
    -j 8

./scripts/pipeline/20_science.sh \
    --night 20220108 \
    --skip-coadds \
    -j 8
# ... repeat for all science nights
```

**Optional filters:**
```bash
# Process only specific object
./scripts/pipeline/20_science.sh \
    --night 20220105 \
    --object "2020wnt" \
    --skip-coadds \
    -j 8
```

### Step 5: Run Difference Imaging

Subtract template from each science night:

#### Using Auto-Template Discovery (Recommended)

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --auto-template \
    --band r \
    -j 8
```

The script will automatically find the most recent template for your tract/band.

#### Using Specific Template

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --template "templates/deep/tract1099/r/20251224T120000Z" \
    --band r \
    -j 8
```

#### With Date Exclusion (for transient campaigns)

If your template might be contaminated by the transient:

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --auto-template \
    --exclude-start 20220101 \
    --exclude-end 20220301 \
    --band r \
    -j 8
```

This excludes templates built from nights in that date range.

#### Additional Filters

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --auto-template \
    --band r \
    --object "2020wnt" \
    --tract 1099 \
    -j 8
```

**What this does:**
1. **Warp template** to match science image geometry (`rewarpTemplate`)
2. **PSF matching** using Alard-Lupton algorithm (`subtractImages`)
   - Finds kernel stars (bright, isolated sources)
   - Computes spatially-varying matching kernel
   - Convolves template to match science PSF
   - Subtracts: `difference = science - convolved_template`
3. **Detect sources** in difference image (`detectAndMeasureDiaSource`)
   - 3σ threshold (optimized for transients)
   - Measures flux, position, shape
   - Flags artifacts
4. **Consolidate** DIA sources into catalog

**Output datasets:**
- `difference_image`: Science - template subtraction
- `template_matched`: Template after PSF matching
- `difference_kernel`: PSF matching kernel
- `dia_source_unfiltered`: Detected transient/variable sources

**Output collection format:**
```
Nickel/runs/{NIGHT}/diff/{TIMESTAMP}/run
```

### Step 6: Extract Light Curve

Extract photometry for your target:

#### By Coordinates

```bash
python scripts/python/pipeline_tools/extract_lightcurve.py \
    --repo $REPO \
    --collection 'Nickel/runs/*/diff/*/run' \
    --ra 83.8145 \
    --dec 3.0847 \
    --radius 1.0 \
    --band r \
    --min-snr 3.0 \
    --output lightcurve_sn2020wnt.ecsv
```

#### By Object Name (via SIMBAD)

```bash
python scripts/python/pipeline_tools/extract_lightcurve.py \
    --repo $REPO \
    --collection 'Nickel/runs/*/diff/*/run' \
    --object "SN 2020wnt" \
    --radius 1.0 \
    --band r \
    --output lightcurve_sn2020wnt.ecsv
```

**Parameters:**
- `--collection`: Glob pattern or comma-separated DIA collections
- `--radius`: Match radius in arcsec
- `--min-snr`: Minimum S/N threshold (default: 3.0)
- `--output`: Output file (ECSV format)

**View light curve:**
```bash
# With TOPCAT
topcat lightcurve_sn2020wnt.ecsv

# Or inspect with Python
python -c "
from astropy.table import Table
lc = Table.read('lightcurve_sn2020wnt.ecsv')
print(lc)
"
```

### Step 7: Quality Assessment

#### Visual Inspection

View difference images in DS9 or Firefly:

```bash
# Get specific difference image
butler get $REPO difference_image \
    --collections 'Nickel/runs/20220105/diff/*/run' \
    --where "instrument='Nickel' AND visit=80514098"
```

**What to check:**
- ✅ Clean subtraction (no residuals from bright stars)
- ✅ Transient/variable clearly detected
- ✅ Minimal artifacts (cosmic rays, diffraction spikes)
- ❌ Residual patterns (indicates PSF mismatch)
- ❌ "Dipoles" everywhere (indicates WCS mismatch)

#### Catalog Inspection

```bash
# Count DIA sources per night
butler query-datasets $REPO dia_source_unfiltered \
    --collections 'Nickel/runs/20220105/diff/*/run' \
    --where "instrument='Nickel'"

# Get DIA source catalog
butler get $REPO dia_source_unfiltered \
    --collections 'Nickel/runs/20220105/diff/*/run' \
    --where "instrument='Nickel' AND visit=80514098"
```

#### Quality Metrics

```bash
# Check logs for warnings
grep -i "warning\|error" logs/diff_*.log

# Check kernel quality
butler query-datasets $REPO difference_kernel_sources \
    --collections 'Nickel/runs/20220105/diff/*/run'
```

**Red flags:**
- Too few kernel stars (< 10): Poor PSF matching
- High χ² residuals: PSF model failure
- Systematic flux offsets: Photometric calibration mismatch

## Advanced Usage

### Multi-Night Batch Processing

Process multiple science nights in one go:

```bash
# Create science nights file
cat > science_nights.txt <<EOF
20220105
20220108
20220110
20220118
EOF

# Process all nights
while read -r night; do
    echo "Processing $night..."

    # Calibrations
    ./scripts/pipeline/10_calibs.sh --night "$night" -j 8

    # Science
    ./scripts/pipeline/20_science.sh \
        --night "$night" \
        --skip-coadds \
        -j 8

    # DIA
    ./scripts/pipeline/40_diff_imaging.sh \
        --night "$night" \
        --auto-template \
        --band r \
        -j 8

done < science_nights.txt
```

Or use the batch script:

```bash
./scripts/pipeline/batch_process_nights.sh \
    --nights-file science_nights.txt \
    --template-auto \
    --band r
```

### Template Metadata Tracking

Record template date ranges to avoid contamination:

```bash
# List templates with metadata
python scripts/python/pipeline_tools/template_metadata.py list \
    --repo $REPO

# Query templates excluding date range
python scripts/python/pipeline_tools/template_metadata.py query \
    --repo $REPO \
    --exclude-start 20220101 \
    --exclude-end 20220301 \
    --band r
```

This is automatically done when building templates with [30_coadds.sh](../scripts/pipeline/30_coadds.sh).

### Building Multiple Templates

You can build separate templates for different fields/purposes:

```bash
# Template for field A (tract 1099)
./scripts/pipeline/30_coadds.sh \
    --tract 1099 \
    --band r \
    --nights-file fieldA_nights.txt \
    -o "templates/deep/tract1099/r/fieldA"

# Template for field B (tract 1100)
./scripts/pipeline/30_coadds.sh \
    --tract 1100 \
    --band r \
    --nights-file fieldB_nights.txt \
    -o "templates/deep/tract1100/r/fieldB"
```

Then specify which template to use in DIA:

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --template "templates/deep/tract1099/r/fieldA" \
    --band r
```

### Reprocessing DIA with Different Parameters

If you need to reprocess with different detection thresholds or kernel sizes:

1. Edit [configs/dia/detectAndMeasure.py](../configs/dia/detectAndMeasure.py)
2. Edit [configs/dia/subtractImages.py](../configs/dia/subtractImages.py)
3. Re-run DIA (science processing doesn't need to be re-run):

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --template "templates/deep/tract1099/r/20251224T120000Z" \
    --band r \
    --force-reprocess \
    -j 8
```

## Troubleshooting

### "No template collections found"

**Cause:** Template coadds haven't been built yet.

**Solution:**
```bash
# Verify template nights are processed
butler query-datasets $REPO preliminary_visit_image \
    --collections 'Nickel/runs/*/processCcd/*/run' \
    --where "band='r'"

# Build template
./scripts/pipeline/30_coadds.sh \
    --tract 1099 \
    --band r \
    --nights-file template_nights.txt
```

### "Template doesn't cover tract/patch"

**Cause:** Science observations are in different tract/patch than template.

**Solution:**
```bash
# Find which tract/patch your science observations cover
butler query-datasets $REPO preliminary_visit_image \
    --collections 'Nickel/runs/20220105/processCcd/*/run'

# Look for tract, patch in output
# Build template for that tract
```

### "Quantum graph generation failed"

**Cause:** Usually missing datasets or mismatched data IDs.

**Solution:**
```bash
# Check if preliminary_visit_image exists
butler query-datasets $REPO preliminary_visit_image \
    --collections 'Nickel/runs/20220105/processCcd/*/run' \
    --where "instrument='Nickel'"

# Check if template exists
butler query-datasets $REPO template_coadd \
    --collections 'templates/deep/tract1099/r/*' \
    --where "tract=1099 AND band='r'"

# Check for tract/patch overlap
# (template must cover the same tract/patch as science images)
```

### "Subtraction failed - PSF mismatch"

**Cause:** Large difference in seeing between science and template.

**Solutions:**
1. Use template nights with similar seeing
2. Increase kernel size in [configs/dia/subtractImages.py](../configs/dia/subtractImages.py):
   ```python
   config.makeKernel.kernelSize = 25  # Increase from 21
   ```
3. Build templates only from best-seeing nights

### "Too few kernel stars"

**Cause:** Field is sparse, or detection threshold too high.

**Solutions:**
1. Check field has sufficient stars:
   ```bash
   butler query-datasets $REPO single_visit_star_footprints \
       --collections 'Nickel/runs/20220105/processCcd/*/run'
   ```
2. Lower kernel star detection threshold in config (if using old stack version)
3. Increase field coverage / choose denser field

### "No valid pixels in warped template"

**Cause:** Template doesn't spatially overlap with science image.

**Solutions:**
1. Verify tract/patch match:
   ```bash
   # Science tract/patch
   butler query-datasets $REPO preliminary_visit_image \
       --collections 'Nickel/runs/20220105/processCcd/*/run' | grep tract

   # Template tract/patch
   butler query-datasets $REPO template_coadd \
       --collections 'templates/deep/tract1099/r/*' | grep tract
   ```
2. Build template for correct tract
3. Check skymap configuration is consistent

## Configuration Reference

### DIA Pipeline Config

**Location:** [pipelines/DIA.yaml](../pipelines/DIA.yaml)

**Key parameters:**
- Pipeline uses `preliminary_visit_image` (from processCcd) as science input
- Template input: `template_coadd` (from 30_coadds.sh or PS1 ingestion)
- Outputs: `difference_image`, `dia_source_unfiltered`

### Subtraction Config

**Location:** [configs/dia/subtractImages.py](../configs/dia/subtractImages.py)

**Key parameters:**
- `kernelSize`: Kernel width in pixels (default: 21)
  - Typical seeing: 1.5-2.5" / 0.37"/pix = 4-7 pix FWHM
  - Kernel should be ~3× FWHM
- `doSubtractBackground`: Enable background subtraction (default: True)
- `allowKernelSourceDetection`: Auto-detect kernel stars (default: True)

### Detection Config

**Location:** [configs/dia/detectAndMeasure.py](../configs/dia/detectAndMeasure.py)

**Note:** Mostly using task defaults in LSST stack v12.0.0+ for compatibility.

**Effective settings (from task defaults):**
- Detection threshold: ~3σ (good for transients)
- Minimum pixels: 5 connected pixels
- Includes both positive and negative detections
- PSF flux measurement for point sources

## Performance Tips

1. **Parallelization:** Use `-j 8` (or more) for faster processing
2. **Template reuse:** Build template once, use for many science nights
3. **Incremental processing:** Process new nights as they arrive
4. **Resource limits:** Reduce `-j` if running out of memory
5. **Disk space:** DIA generates large difference images; clean old runs periodically

## Data Products Summary

| Dataset Type | Description | Created By |
|--------------|-------------|------------|
| `preliminary_visit_image` | Single-visit calibrated image | 20_science.sh (processCcd) |
| `template_coadd` | Deep multi-night coadd | 30_coadds.sh |
| `template_detector` | Warped template | 40_diff_imaging.sh (rewarpTemplate) |
| `difference_image` | Science - template | 40_diff_imaging.sh (subtractImages) |
| `template_matched` | PSF-matched template | 40_diff_imaging.sh (subtractImages) |
| `difference_kernel` | PSF matching kernel | 40_diff_imaging.sh (subtractImages) |
| `dia_source_unfiltered` | DIA source catalog | 40_diff_imaging.sh (detectAndMeasure) |

## Collection Structure

```
Nickel/
├── raw/
│   └── {NIGHT}/
│       └── {TIMESTAMP}/                    # Raw data ingestion
├── calib/
│   ├── current/                            # Current calibration chain
│   ├── {NIGHT}/
│   │   ├── bias/{TIMESTAMP}/
│   │   ├── flat/{TIMESTAMP}/
│   │   └── defects/{TIMESTAMP}/
└── runs/
    └── {NIGHT}/
        ├── processCcd/{TIMESTAMP}/
        │   └── run/                        # Single-visit processing
        └── diff/{TIMESTAMP}/
            └── run/                        # DIA outputs

templates/
└── deep/
    └── tract{TRACT}/
        └── {BAND}/
            └── {TIMESTAMP}/                # Template coadds

refcats/                                    # Reference catalogs (Gaia, PS1)
skymaps/                                    # Skymap definitions
```

## References

- **LSST Science Pipelines:** https://pipelines.lsst.io/
- **DIA Documentation:** https://pipelines.lsst.io/modules/lsst.ip.diffim/
- **Butler Gen3:** https://pipelines.lsst.io/modules/lsst.daf.butler/
- **obs_nickel README:** [../README.md](../README.md)

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review logs in `logs/diff_*.log`
3. Test with [test_nickel_template_dia.sh](../scripts/pipeline/test_nickel_template_dia.sh)
4. Check GitHub issues: https://github.com/astrophysics/obs_nickel/issues
