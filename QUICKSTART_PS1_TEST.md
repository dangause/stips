# Quick Start: PS1 Template Testing for 2023ixf

## Exact Commands to Run

### Option 1: Run Full Test Script (Recommended)

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel

# Run entire test workflow
./TEST_PS1_COMMANDS.sh
```

### Option 2: Run Commands Manually (Step-by-Step)

#### Setup (Run Once)

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel

# Load environment
set -a
source .env.recalib
set +a

# Setup LSST stack
cd $STACK_DIR
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel

cd $OBS_NICKEL
```

#### Create New Repo

```bash
# Create fresh Butler repo
butler create $REPO

# Register instrument
butler register-instrument $REPO lsst.obs.nickel.Nickel

# Register skymap
butler register-skymap $REPO \
    -C $OBS_NICKEL/configs/makeSkyMap.py

# Verify
butler query-datasets $REPO skyMap --collections "skymaps/*"
```

#### Check PS1 Coverage

```bash
./scripts/utilities/check_template_coverage.sh \
    --ra 210.9106 \
    --dec 54.3118 \
    --band r \
    --check-ps1
```

#### Ingest PS1 Templates

```bash
# Ingest r-band
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 210.9106 \
    --dec 54.3118 \
    --band r \
    --collection templates/ps1/2023ixf/r \
    --size 0.3

# Ingest i-band
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 210.9106 \
    --dec 54.3118 \
    --band i \
    --collection templates/ps1/2023ixf/i \
    --size 0.3
```

#### Verify Ingestion

```bash
# Check collections
butler query-collections $REPO | grep ps1

# Check templates
butler query-datasets $REPO template_coadd \
    --collections "templates/ps1/2023ixf/*"

# Check metadata
python packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/template_metadata.py \
    list --repo $REPO --source ps1
```

---

## If You Want to Import Existing 2023ixf Data

### From Your Current 2023ixf Repo

Using `butler transfer-datasets` (faster and cleaner than export/import):

```bash
# Set old repo path (adjust this!)
OLD_REPO=/Users/dangause/Developer/lick/lsst/data/nickel/2023ixf_mini_repo

# Transfer calibrations
butler transfer-datasets $OLD_REPO $REPO \
    --collections "Nickel/calib/*" \
    --register-dataset-types \
    --transfer symlink

# Transfer raw data (2023ixf observations)
butler transfer-datasets $OLD_REPO $REPO \
    --collections "Nickel/raw/2023*" \
    --where "exposure.target_name='2023ixf'" \
    --register-dataset-types \
    --transfer symlink

# Transfer processed data
butler transfer-datasets $OLD_REPO $REPO \
    --collections "Nickel/runs/2023*/processCcd/*" \
    --where "exposure.target_name='2023ixf'" \
    --register-dataset-types \
    --transfer symlink
```

**Benefits of `transfer-datasets` over export/import:**
- No intermediate export directory needed
- Can use symlinks (saves disk space)
- Transfers registry metadata directly
- Faster for large datasets

---

## Run DIA with PS1 Templates

### After you have science data:

```bash
# Specific template
./scripts/pipeline/40_diff_imaging.sh \
    --night 20230520 \
    --template templates/ps1/2023ixf/r \
    --object 2023ixf \
    --band r

# Auto-discovery (prefer PS1)
./scripts/pipeline/40_diff_imaging.sh \
    --night 20230520 \
    --prefer-ps1 --auto-template \
    --object 2023ixf \
    --band r
```

---

## Useful Verification Commands

```bash
# List all collections
butler query-collections $REPO

# View PS1 templates
butler query-datasets $REPO template_coadd \
    --collections "templates/ps1/*"

# View template metadata (detailed)
python packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/template_metadata.py \
    list --repo $REPO --source ps1 --verbose

# Check what nights you have
butler query-dimension-records $REPO exposure \
    --where "exposure.target_name='2023ixf'" \
    | grep day_obs

# Check processed visits
butler query-datasets $REPO preliminary_visit_image \
    --where "exposure.target_name='2023ixf'"
```

---

## Quick Test Summary

**Minimum viable test** (no science data needed):

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel
source .env.recalib
cd $STACK_DIR && source loadLSST.zsh && setup lsst_distrib && setup obs_nickel
cd $OBS_NICKEL

# Create repo + skymap (1 min)
butler create $REPO
butler register-instrument $REPO lsst.obs.nickel.Nickel
butler register-skymap $REPO -C configs/makeSkyMap.py

# Ingest PS1 template (2-3 min)
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 210.9106 --dec 54.3118 --band r \
    --collection templates/ps1/2023ixf/r --size 0.3

# Verify (instant)
butler query-datasets $REPO template_coadd --collections "templates/ps1/*"
```

**Total time**: ~5 minutes

---

## What Gets Created

After running the test:

```
$REPO/
├── template_metadata.json          # PS1 metadata tracking
├── datastore/                       # PS1 template FITS
└── gen3.sqlite3                     # Butler registry

$OBS_NICKEL/ps1_templates/2023ixf/  # Downloaded PS1 FITS
├── ps1_r_ra210.9106_dec54.3118.fits
└── lsst_template_r.fits
```

---

## Troubleshooting

### PS1 download fails
```bash
# Try different download method
# Edit ingest_ps1_template.py line 188:
# download_ps1_cutout(..., force_service='fitscut')
```

### Skymap not found
```bash
# Check available skymaps
butler query-datasets $REPO skyMap

# Re-register if needed
butler register-skymap $REPO \
    -C configs/makeSkyMap.py
```

### Template ingestion fails
```bash
# Check detailed logs
tail -100 /path/to/log/file

# Verify FITS file downloaded
ls -lh $OBS_NICKEL/ps1_templates/2023ixf/
```

---

## Ready to Test!

Run this now:
```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel
./TEST_PS1_COMMANDS.sh
```

Or step through manually using the commands above.
