# Quick Start: DRP with Recalibration

## TL;DR - Run Everything at Once

```bash
# 1. Create a nights list
cat > nights.txt <<EOF
20240624
20240625
20240626
EOF

# 2. Run the full pipeline
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
  --nights-file nights.txt \
  --tract 1825 \
  --jobs 4
```

That's it! This will run the complete DRP with Stage 2 recalibration.

---

## What Gets Run

1. **Bootstrap** (if repo doesn't exist)
   - Creates Butler repository
   - Ingests reference catalogs
   - Registers skymap

2. **Download** (optional, can skip with `--skip-download`)
   - Downloads raw data from Lick archive

3. **Calibrations** (per night)
   - Processes bias, flat, dark frames
   - Creates calibration products

4. **Stage 1 Science** (per night)
   - ISR (Instrument Signature Removal)
   - Single-visit calibration
   - PSF modeling
   - Astrometry (initial, using Gaia)
   - Photometry (initial, using reference catalog)
   - Isolated star association

5. **Stage 2 Recalibration** (all nights together)
   - **FGCM**: Global photometric calibration
   - **GBDES**: Joint astrometric fit (tract-level)
   - **PSF refit**: Improved PSF models
   - **visit_summary update**: Apply FGCM + GBDES to visit metadata

6. **Coadds** (per band)
   - Warps with recalibrated data
   - Template coadds for difference imaging

---

## Common Options

### Skip stages you've already done

```bash
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
  --nights-file nights.txt \
  --tract 1825 \
  --skip-bootstrap \
  --skip-download \
  --skip-calibs \
  --skip-science \
  --jobs 4
```

This runs only Stage 2 and coadds.

### Process multiple bands

```bash
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
  --nights-file nights.txt \
  --tract 1825 \
  --bands "r,i,g" \
  --jobs 4
```

### Auto-determine tract from RA/Dec

```bash
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
  --nights-file nights.txt \
  --ra 202.5 \
  --dec 47.2 \
  --jobs 4
```

### Continue on errors

```bash
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
  --nights-file nights.txt \
  --tract 1825 \
  --continue-on-error \
  --jobs 4
```

If one night fails, the pipeline continues with the rest.

---

## Step-by-Step (Manual Control)

If you want fine-grained control, run each stage separately:

### 1. Bootstrap (once)

```bash
ENV_FILE=.env.recal ./scripts/pipeline/00_bootstrap_repo_recal.sh
```

### 2. Process each night

```bash
# Calibrations
ENV_FILE=.env.recal ./scripts/pipeline/10_calibs_recal.sh \
  --night 20240624 --jobs 4

# Stage 1 science
ENV_FILE=.env.recal ./scripts/pipeline/20_science_recal.sh \
  --night 20240624 --jobs 4
```

Repeat for each night.

### 3. Stage 2 recalibration (once, after all nights)

```bash
ENV_FILE=.env.recal ./scripts/pipeline/21_recalibrate.sh \
  --nights-file nights.txt \
  --tract 1825 \
  --jobs 4
```

### 4. Build coadds (per band)

```bash
ENV_FILE=.env.recal ./scripts/pipeline/30_coadds_recal.sh \
  --nights-file nights.txt \
  --band r \
  --tract 1825 \
  --jobs 4
```

---

## Monitoring Progress

### Check collections

```bash
# Stage 1 outputs (per night)
butler query-collections $REPO | grep "recal/runs"

# Stage 2 outputs (global)
butler query-collections $REPO | grep "recal/stage2"

# Coadds
butler query-collections $REPO | grep "recal/coadds"
```

### Check datasets

```bash
# Isolated stars (needed for FGCM)
butler query-datasets $REPO isolated_star_association

# FGCM photometric calibration
butler query-datasets $REPO fgcmPhotoCalibCatalog

# GBDES astrometric fit
butler query-datasets $REPO gbdesAstrometricFitSkyWcsCatalog

# Recalibrated visit summary
butler query-datasets $REPO visit_summary --collections "Nickel/recal/stage2/*"

# Coadds
butler query-datasets $REPO template_coadd --collections "Nickel/recal/coadds/*"
```

### Check logs

Logs are in `$REPO/logs/`:
```bash
ls $REPO/logs/
tail -f $REPO/logs/recalibrate/LATEST.log
```

---

## Troubleshooting

**"No Stage 1 collection found for night X"**
→ Run `20_science_recal.sh` for that night first

**"No Stage 2 recalibration collection found"**
→ Run `21_recalibrate.sh` before building coadds

**FGCM fails with "insufficient data"**
→ FGCM needs multiple nights and multiple bands. Try with more data.

**GBDES fails**
→ Check isolated star associations exist. May need more overlap between visits.

**"Pipeline not found"**
→ Check `OBS_NICKEL` in `.env.recal` points to the right directory

---

## What's Different from Standard DRP?

1. Uses **isolated repo** (`.env.recal` → `REPO=/path/to/recal_repo`)
2. Uses **DRP_recal.yaml** pipeline (includes Stage 2 tasks)
3. Outputs to **`Nickel/recal/*`** collections (won't touch existing data)
4. **Separate scripts** (all have `_recal` suffix)

Everything is isolated - you can run this alongside your regular DRP without any conflicts.

---

## Full Options Reference

```bash
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh --help
```

See [README_RECAL.md](README_RECAL.md) for full documentation.
