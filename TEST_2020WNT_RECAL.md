# Testing Recalibration Pipeline with 2020wnt Data

This guide walks you through testing the DRP recalibration pipeline using 7 nights from the 2020wnt campaign.

## Quick Start

```bash
# Run everything at once
./test_recal_2020wnt.sh
```

That's it! This will process 7 nights and run the complete recalibration pipeline.

---

## What Gets Tested

### Data
- **7 nights**: December 2020 through March 2021
- **Multi-band**: r, i, v, b filters
- **Object**: 2020wnt (SN IIP in M61)
- **Tract**: 1825

### Pipeline Stages
1. ✅ Bootstrap repository (first run only)
2. ✅ Process calibrations (7 nights)
3. ✅ Stage 1 science (single-visit processing, 7 nights)
4. ✅ **Stage 2 recalibration** (FGCM + GBDES + PSF refit)
5. ✅ Build coadds (4 bands, using recalibrated data)

### Why This Dataset is Good
- **FGCM**: 7 nights × 4 bands = enough data for photometric calibration
- **GBDES**: Multiple nights observing same field = good overlap for joint astrometry
- **Real science**: Actual supernova observations with varying atmospheric conditions

---

## Step-by-Step (Manual Control)

If you want to run each stage separately:

### 1. Bootstrap (once)

```bash
ENV_FILE=.env.recal ./scripts/pipeline/00_bootstrap_repo_recal.sh
```

### 2. Process Each Night

Run for all 7 nights:

```bash
# Night 1: 20201207
ENV_FILE=.env.recal ./scripts/pipeline/10_calibs_recal.sh \
  --night 20201207 --jobs 4

ENV_FILE=.env.recal ./scripts/pipeline/20_science_recal.sh \
  --night 20201207 --object 2020wnt --jobs 4

# Night 2: 20201219
ENV_FILE=.env.recal ./scripts/pipeline/10_calibs_recal.sh \
  --night 20201219 --jobs 4

ENV_FILE=.env.recal ./scripts/pipeline/20_science_recal.sh \
  --night 20201219 --object 2020wnt --jobs 4

# Nights 3-7: 20210208, 20210218, 20210228, 20210306, 20210321
# (repeat the same pattern for each night)
```

Or use a loop:

```bash
for night in 20201207 20201219 20210208 20210218 20210228 20210306 20210321; do
  echo "Processing night $night..."

  ENV_FILE=.env.recal ./scripts/pipeline/10_calibs_recal.sh \
    --night $night --jobs 4

  ENV_FILE=.env.recal ./scripts/pipeline/20_science_recal.sh \
    --night $night --object 2020wnt --jobs 4
done
```

### 3. Stage 2 Recalibration (after all nights)

```bash
ENV_FILE=.env.recal ./scripts/pipeline/21_recalibrate.sh \
  --nights-file nights_2020wnt_recal_test.txt \
  --tract 1825 \
  --object 2020wnt \
  --jobs 4
```

This runs all recalibration steps:
- Step 2a: FGCM photometric calibration
- Step 2b: GBDES tract-level astrometric fit
- Step 2c: GBDES healpix-level fit (optional)
- Step 2d: Refit PSFs and update visit_summary
- Step 2f: Generate final tables

### 4. Build Coadds (per band)

```bash
# r-band
ENV_FILE=.env.recal ./scripts/pipeline/30_coadds_recal.sh \
  --nights-file nights_2020wnt_recal_test.txt \
  --band r \
  --tract 1825 \
  --jobs 4

# i-band
ENV_FILE=.env.recal ./scripts/pipeline/30_coadds_recal.sh \
  --nights-file nights_2020wnt_recal_test.txt \
  --band i \
  --tract 1825 \
  --jobs 4

# Repeat for v and b if desired
```

---

## Verification

### Check Repository

```bash
# Source environment
source .env.recal

# Check repository exists
ls -lh $REPO/butler.yaml
```

### Verify Stage 1 Outputs

```bash
# Stage 1 collections (one per night)
butler query-collections $REPO | grep "recal/runs"

# Should see 7 collections like:
#   Nickel/recal/runs/20201207/stage1/...
#   Nickel/recal/runs/20201219/stage1/...
#   etc.

# Check preliminary visit summaries
butler query-datasets $REPO preliminary_visit_summary \
  --collections "Nickel/recal/runs/*/stage1/*"

# Check isolated star associations
butler query-datasets $REPO isolated_star_association \
  --collections "Nickel/recal/runs/*/stage1/*"
```

### Verify Stage 2 Outputs

```bash
# Stage 2 collection (global)
butler query-collections $REPO | grep "recal/stage2"

# Should see: Nickel/recal/stage2/{TIMESTAMP}

# Check FGCM photometric calibration
butler query-datasets $REPO fgcmPhotoCalibCatalog

# Check GBDES astrometric fit
butler query-datasets $REPO gbdesAstrometricFitSkyWcsCatalog

# Check recalibrated visit summary (the key output!)
butler query-datasets $REPO visit_summary \
  --collections "Nickel/recal/stage2/*"
```

### Verify Coadds

```bash
# Coadd collections
butler query-collections $REPO | grep "recal/coadds"

# Should see: Nickel/recal/coadds/tract1825/{band}/{TIMESTAMP}

# Check template coadds
butler query-datasets $REPO template_coadd \
  --collections "Nickel/recal/coadds/*" \
  --where "tract=1825"

# Check deep coadds
butler query-datasets $REPO deep_coadd_predetection \
  --collections "Nickel/recal/coadds/*" \
  --where "tract=1825"
```

### Check Logs

```bash
# All logs are in $REPO/logs/
ls -lh $REPO/logs/

# Latest recalibration log
tail -100 $REPO/logs/recalibrate/LATEST.log

# Check for errors
grep -i "error\|fail" $REPO/logs/recalibrate/*.log
```

---

## Expected Runtime

On a typical machine with 4 jobs:
- **Bootstrap**: ~5-10 minutes (first run only)
- **Calibrations**: ~5-10 minutes per night = 35-70 minutes total
- **Stage 1 Science**: ~10-20 minutes per night = 70-140 minutes total
- **Stage 2 Recalibration**: ~30-60 minutes (depends on data volume)
- **Coadds**: ~5-15 minutes per band = 20-60 minutes for 4 bands

**Total**: ~2.5-5 hours for the full pipeline

You can speed this up by increasing `--jobs` if you have more CPU cores.

---

## Troubleshooting

### FGCM Fails
- **Check**: Do you have data in multiple bands?
- **Fix**: Verify isolated star associations exist for all nights
- **Command**: `butler query-datasets $REPO isolated_star_association`

### GBDES Fails
- **Check**: Do visits overlap in the tract?
- **Fix**: Verify all nights have data in tract 1825
- **Command**: `butler query-datasets $REPO preliminary_visit_image --where "tract=1825"`

### Coadds Fail
- **Check**: Did Stage 2 complete successfully?
- **Fix**: Verify `visit_summary` datasets exist in Stage 2 collection
- **Command**: `butler query-datasets $REPO visit_summary --collections "Nickel/recal/stage2/*"`

### "No Stage 1 collection found"
- **Check**: Did you run `20_science_recal.sh` for that night?
- **Fix**: Run Stage 1 processing for the missing night

### Out of Memory
- **Check**: How many jobs are you running?
- **Fix**: Reduce `--jobs` to 2 or even 1

---

## Comparing Results

Compare recalibrated photometry/astrometry with initial calibration:

```bash
# Initial photometry (from preliminary_visit_summary)
butler query-datasets $REPO preliminary_visit_summary \
  --collections "Nickel/recal/runs/20201207/stage1/*"

# Recalibrated photometry (from visit_summary)
butler query-datasets $REPO visit_summary \
  --collections "Nickel/recal/stage2/*"

# You can use the LSST Science Pipelines to load and compare the actual values
```

---

## Next Steps

After successful testing:

1. **Analyze calibrations**: Examine FGCM and GBDES outputs for quality
2. **Compare with standard DRP**: Run same data through regular DRP and compare
3. **Use for science**: Build templates and run difference imaging
4. **Scale up**: Process more nights from 2020wnt or other campaigns

---

## Files

- **[nights_2020wnt_recal_test.txt](nights_2020wnt_recal_test.txt)** - List of 7 test nights
- **[test_recal_2020wnt.sh](test_recal_2020wnt.sh)** - Automated test script
- **[.env.recal](.env.recal)** - Environment configuration
- **[README_RECAL.md](README_RECAL.md)** - Complete documentation
- **[QUICKSTART_RECAL.md](QUICKSTART_RECAL.md)** - Quick reference guide

---

## Summary

You're testing the recalibration pipeline with:
- ✅ **7 nights** of real SN data
- ✅ **Multi-band** observations (r, i, v, b)
- ✅ **Sufficient data** for FGCM and GBDES
- ✅ **Isolated repo** (won't affect existing data)
- ✅ **Complete pipeline** (Stage 1 + Stage 2 + coadds)

**Ready to run!**

```bash
./test_recal_2020wnt.sh
```
