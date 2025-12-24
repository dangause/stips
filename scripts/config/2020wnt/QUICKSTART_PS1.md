# SN 2020wnt DIA with PS1 Template - Quick Start

Fresh repository setup using PS1 template (raw data already downloaded).

**SN 2020wnt**: RA=83.8145°, Dec=3.0847°, R-band

---

## Prerequisites

- Raw data already in `/Users/dangause/Developer/lick/data/YYYYMMDD/raw/`
- Nights: 20220105, 20220108, 20220110, 20220118, 20220124, 20220126, 20220129, 20220208, 20220212
- LSST Stack set up

---

## Step-by-Step Commands

### 1. Create Fresh Repository

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel
source .env

# Create new repo
export NEW_REPO="/Users/dangause/Developer/lick/lsst/data/nickel/2020wnt_ps1_repo"
butler create "$NEW_REPO"
butler register-instrument "$NEW_REPO" lsst.obs.nickel.Nickel
```

### 2. Bootstrap (Refcats + Skymap)

**Option A - Copy from existing repo** (fastest):

```bash
# Copy reference catalogs
butler transfer-datasets \
    /Users/dangause/Developer/lick/lsst/data/nickel/2020wnt_batch_process_repo \
    "$NEW_REPO" \
    --collections "the_monster_20250219_local" \
    --dataset-type ref_cat

# Create refcats chain
butler collection-chain "$NEW_REPO" refcats the_monster_20250219_local --mode redefine

# Copy skymap
butler transfer-datasets \
    /Users/dangause/Developer/lick/lsst/data/nickel/2020wnt_batch_process_repo \
    "$NEW_REPO" \
    skyMap \
    --collections "skymaps/nickelRings"

butler collection-chain "$NEW_REPO" skymaps skymaps/nickelRings --mode redefine
```

**Option B - Run bootstrap script** (if you want fresh refcat ingest):

```bash
# Temporarily override REPO variable for bootstrap
REPO="$NEW_REPO" ./scripts/pipeline/00_bootstrap_repo.sh
```

### 3. Install astroquery (if not already installed)

```bash
# In LSST environment
pip install astroquery
```

### 4. Ingest PS1 Template

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel

# Download and ingest PS1 r-band template
REPO="$NEW_REPO" ./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 83.8145 \
    --dec 3.0847 \
    --band r \
    --collection "templates/ps1/r" \
    --size 0.15 \
    --output-dir "./ps1_templates_2020wnt"
```

**Expected output:**
- Downloads PS1 r-band image (~30 seconds)
- Converts to LSST format
- Ingests to `templates/ps1/r`
- Saves FITS to `./ps1_templates_2020wnt/lsst_template_r.fits`

**Verify:**
```bash
butler query-datasets "$NEW_REPO" template_coadd --collections "templates/ps1/r"
```

### 5. Process Calibrations (All Nights)

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel

# Process calibrations for all SN nights
for night in 20220105 20220108 20220110 20220118 20220124 20220126 20220129 20220208 20220212; do
    echo "Processing calibrations: $night"
    REPO="$NEW_REPO" ./scripts/pipeline/10_calibs.sh --night "$night"
done
```

**This will take**: ~5-10 minutes per night (bias, flats, defects)

### 6. Process Science Images (processCcd)

```bash
# Process R-band science images for SN 2020wnt
for night in 20220105 20220108 20220110 20220118 20220124 20220126 20220129 20220208 20220212; do
    echo "Processing science: $night"
    REPO="$NEW_REPO" ./scripts/pipeline/20_science.sh \
        --night "$night" \
        --object "2020wnt" \
        --skip-coadds \
        -j 8
done
```

**This will take**: ~10-15 minutes per night

### 7. Run DIA with PS1 Template

```bash
# Run difference imaging for each night
for night in 20220105 20220108 20220110 20220118 20220124 20220126 20220129 20220208 20220212; do
    echo "Running DIA: $night"
    REPO="$NEW_REPO" ./scripts/pipeline/40_diff_imaging.sh \
        --night "$night" \
        --template "templates/ps1/r" \
        --band r \
        --object "2020wnt" \
        -j 8
done
```

**This will take**: ~5-10 minutes per night

### 8. Extract Light Curve

```bash
# Create output directory
mkdir -p ./sn2020wnt_ps1_results

# Extract light curve from all DIA results
python scripts/python/pipeline_tools/extract_lightcurve.py \
    --repo "$NEW_REPO" \
    --collection "Nickel/runs/*/diff/*/run" \
    --ra 83.8145 \
    --dec 3.0847 \
    --radius 1.0 \
    --band r \
    --min-snr 3.0 \
    --output ./sn2020wnt_ps1_results/lightcurve_ps1template.ecsv
```

**Output**: `./sn2020wnt_ps1_results/lightcurve_ps1template.ecsv`

### 9. Quality Assessment

```bash
# Generate quality reports for each night
for night in 20220105 20220108 20220110 20220118 20220124 20220126 20220129 20220208 20220212; do
    python scripts/python/pipeline_tools/assess_dia_quality.py \
        --repo "$NEW_REPO" \
        --collection "Nickel/runs/$night/diff/*/run" \
        --night "$night" \
        --output ./sn2020wnt_ps1_results/dia_quality_$night.txt
done
```

---

## Verification & Inspection

### Check Template Ingestion

```bash
butler query-datasets "$NEW_REPO" template_coadd --collections "templates/ps1/r"
```

### Check Science Processing

```bash
butler query-datasets "$NEW_REPO" preliminary_visit_image \
    --where "instrument='Nickel' AND exposure.target_name='2020wnt'"
```

### Check DIA Outputs

```bash
butler query-datasets "$NEW_REPO" difference_image \
    --collections "Nickel/runs/*/diff/*/run"
```

### View Light Curve

```bash
# With TOPCAT (if installed)
topcat ./sn2020wnt_ps1_results/lightcurve_ps1template.ecsv

# Or inspect with Python
python -c "
from astropy.table import Table
lc = Table.read('./sn2020wnt_ps1_results/lightcurve_ps1template.ecsv')
print(lc)
"
```

### Inspect Difference Images

```bash
# Get a difference image
butler get "$NEW_REPO" difference_image \
    --collections "Nickel/runs/20220105/diff/*/run" \
    instrument=Nickel detector=0 \
    | ds9 -
```

---

## Troubleshooting

### PS1 Download Fails

If PS1 download fails:
1. Check internet connection
2. Try again (service can be flaky)
3. Manual download from: https://ps1images.sticsi.edu/cgi-bin/ps1cutouts
4. Use `--ps1-fits` option with downloaded file

### No DIA Sources

If no sources detected in difference images:
1. Check template quality: `ds9 ./ps1_templates_2020wnt/lsst_template_r.fits`
2. Verify science images processed: `butler query-datasets`
3. Lower detection threshold in `configs/dia/detectAndMeasure.py`
4. Check PSF matching succeeded in logs

### Calibration Failures

If calibration processing fails:
1. Verify raw data exists: `ls /Users/dangause/Developer/lick/data/YYYYMMDD/raw/`
2. Check for sufficient bias/flat frames
3. Review logs in `$NEW_REPO/logs/`

---

## Timeline Estimate

| Step | Duration | Notes |
|------|----------|-------|
| 1. Create repo | 10 sec | Quick |
| 2. Bootstrap | 2-5 min | Copy from existing or fresh ingest |
| 3. Install astroquery | 30 sec | One-time |
| 4. PS1 template | 1-2 min | Download + ingest |
| 5. Calibrations (9 nights) | 45-90 min | ~5-10 min/night |
| 6. Science (9 nights) | 90-135 min | ~10-15 min/night |
| 7. DIA (9 nights) | 45-90 min | ~5-10 min/night |
| 8. Light curve | 1 min | Fast |
| 9. Quality reports | 2 min | Fast |
| **Total** | **~3-5 hours** | Mostly automated |

---

## All-in-One Script

For fully automated execution:

```bash
chmod +x scripts/config/2020wnt/ps1_dia_commands.sh
./scripts/config/2020wnt/ps1_dia_commands.sh
```

This will run all steps with prompts for manual verification.

---

## Output Files

After completion:

```
$NEW_REPO/                                      # Butler repository
ps1_templates_2020wnt/                          # PS1 downloaded templates
  ├── ps1_r_ra83.8145_dec3.0847.fits           # Original PS1 FITS
  └── lsst_template_r.fits                      # Converted LSST template

sn2020wnt_ps1_results/                          # Results
  ├── lightcurve_ps1template.ecsv              # Light curve
  ├── dia_quality_20220105.txt                  # Quality reports
  ├── dia_quality_20220108.txt
  └── ...
```

---

## Comparison with Nickel Template

To compare PS1 vs Nickel template results:

```bash
# If you have existing Nickel template DIA results:
python -c "
from astropy.table import Table
import matplotlib.pyplot as plt

# Load both light curves
lc_ps1 = Table.read('sn2020wnt_ps1_results/lightcurve_ps1template.ecsv')
lc_nickel = Table.read('sn2020wnt_results/lightcurve_nickel_template.ecsv')  # If exists

# Plot comparison
plt.errorbar(lc_ps1['mjd'], lc_ps1['mag'], yerr=lc_ps1['mag_err'],
             fmt='o', label='PS1 template')
plt.errorbar(lc_nickel['mjd'], lc_nickel['mag'], yerr=lc_nickel['mag_err'],
             fmt='s', label='Nickel template')
plt.gca().invert_yaxis()
plt.xlabel('MJD')
plt.ylabel('Magnitude')
plt.legend()
plt.savefig('ps1_vs_nickel_comparison.png')
plt.show()
"
```
