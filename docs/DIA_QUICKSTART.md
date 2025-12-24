# DIA Quick Start - Nickel Templates

Fast reference for running Difference Image Analysis with Nickel-built templates.

## One-Command Test

```bash
# Automated end-to-end test (edit script configuration first)
./scripts/pipeline/test_nickel_template_dia.sh --repo $REPO
```

## Minimal Manual Workflow

### 1. Build Template (once per field)

```bash
# Create nights file
cat > template_nights.txt <<EOF
20201207
20201219
20210208
EOF

# Process template nights
for night in $(cat template_nights.txt); do
    ./scripts/pipeline/10_calibs.sh --night $night -j 8
    ./scripts/pipeline/20_science.sh --night $night --skip-coadds -j 8
done

# Build deep template
./scripts/pipeline/30_coadds.sh \
    --tract 1099 \
    --band r \
    --nights-file template_nights.txt \
    -j 8
```

### 2. Process Science Night

```bash
NIGHT=20220105

# Process calibrations and science
./scripts/pipeline/10_calibs.sh --night $NIGHT -j 8
./scripts/pipeline/20_science.sh --night $NIGHT --skip-coadds -j 8

# Run DIA (auto-finds template)
./scripts/pipeline/40_diff_imaging.sh \
    --night $NIGHT \
    --auto-template \
    --band r \
    -j 8
```

### 3. Extract Light Curve

```bash
python scripts/python/pipeline_tools/extract_lightcurve.py \
    --repo $REPO \
    --collection 'Nickel/runs/*/diff/*/run' \
    --ra 83.8145 \
    --dec 3.0847 \
    --radius 1.0 \
    --band r \
    --output lightcurve.ecsv
```

## Common Commands

### Query DIA Results

```bash
# List DIA collections
butler query-collections $REPO | grep diff

# Count difference images
butler query-datasets $REPO difference_image \
    --collections 'Nickel/runs/20220105/diff/*/run'

# Count DIA sources
butler query-datasets $REPO dia_source_unfiltered \
    --collections 'Nickel/runs/20220105/diff/*/run'
```

### Inspect Difference Images

```bash
# Get specific difference image
butler get $REPO difference_image \
    --collections 'Nickel/runs/20220105/diff/*/run' \
    --where "instrument='Nickel' AND visit=80514098"

# Get DIA source catalog
butler get $REPO dia_source_unfiltered \
    --collections 'Nickel/runs/20220105/diff/*/run' \
    --where "instrument='Nickel' AND visit=80514098"
```

### Find Templates

```bash
# List all templates
butler query-collections $REPO | grep templates

# Check template coverage
butler query-datasets $REPO template_coadd \
    --collections 'templates/deep/tract1099/r/*' \
    --where "tract=1099 AND band='r'"

# List templates with metadata
python scripts/python/pipeline_tools/template_metadata.py list \
    --repo $REPO
```

### Process Multiple Nights

```bash
# Process all nights in a file
for night in $(cat science_nights.txt); do
    ./scripts/pipeline/10_calibs.sh --night $night -j 8
    ./scripts/pipeline/20_science.sh --night $night --skip-coadds -j 8
    ./scripts/pipeline/40_diff_imaging.sh --night $night --auto-template --band r -j 8
done
```

## DIA Parameters

### Use Specific Template

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --template "templates/deep/tract1099/r/20251224T120000Z" \
    --band r \
    -j 8
```

### Filter by Object

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --auto-template \
    --band r \
    --object "2020wnt" \
    -j 8
```

### Exclude Template Dates (avoid transient contamination)

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --auto-template \
    --exclude-start 20220101 \
    --exclude-end 20220301 \
    --band r \
    -j 8
```

### Limit to Specific Tract

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20220105 \
    --auto-template \
    --tract 1099 \
    --band r \
    -j 8
```

## Troubleshooting

### Check Processing Status

```bash
# Verify raw data ingested
butler query-collections $REPO | grep "Nickel/raw/$NIGHT"

# Verify calibrations exist
butler query-datasets $REPO bias \
    --collections 'Nickel/calib/current' \
    --where "instrument='Nickel' AND day_obs=$NIGHT"

# Verify science processed
butler query-datasets $REPO preliminary_visit_image \
    --collections "Nickel/runs/$NIGHT/processCcd/*/run" \
    --where "instrument='Nickel'"

# Verify template exists
butler query-datasets $REPO template_coadd \
    --collections 'templates/deep/tract*/r/*'
```

### Check Logs

```bash
# Recent DIA logs
ls -lht logs/diff_*.log | head -5

# Check for errors
grep -i "error" logs/diff_20220105_*.log

# Check kernel quality
grep -i "kernel" logs/diff_20220105_*.log
```

### Common Fixes

**No template found:**
```bash
# Build template first
./scripts/pipeline/30_coadds.sh --tract 1099 --band r --nights-file template_nights.txt
```

**No preliminary_visit_image:**
```bash
# Run science processing
./scripts/pipeline/20_science.sh --night 20220105 --skip-coadds
```

**Tract mismatch:**
```bash
# Find correct tract
butler query-datasets $REPO preliminary_visit_image \
    --collections "Nickel/runs/$NIGHT/processCcd/*/run" | grep tract
```

## Configuration Files

- **DIA pipeline:** [pipelines/DIA.yaml](../pipelines/DIA.yaml)
- **Subtraction config:** [configs/dia/subtractImages.py](../configs/dia/subtractImages.py)
- **Detection config:** [configs/dia/detectAndMeasure.py](../configs/dia/detectAndMeasure.py)

## Full Documentation

See [NICKEL_TEMPLATE_DIA_GUIDE.md](NICKEL_TEMPLATE_DIA_GUIDE.md) for complete workflow and troubleshooting.

## Example: Complete SN Campaign

```bash
#!/bin/bash
# Process SN 2020wnt with Nickel templates

# Configuration
TEMPLATE_NIGHTS=(20201207 20201219 20210208)
SN_NIGHTS=(20220105 20220108 20220110)
TRACT=1099
BAND=r
SN_RA=83.8145
SN_DEC=3.0847

# 1. Process template nights
for night in "${TEMPLATE_NIGHTS[@]}"; do
    ./scripts/pipeline/10_calibs.sh --night $night -j 8
    ./scripts/pipeline/20_science.sh --night $night --skip-coadds -j 8
done

# 2. Build template
printf "%s\n" "${TEMPLATE_NIGHTS[@]}" > template_nights.txt
./scripts/pipeline/30_coadds.sh \
    --tract $TRACT --band $BAND \
    --nights-file template_nights.txt -j 8

# 3. Process SN nights and run DIA
for night in "${SN_NIGHTS[@]}"; do
    ./scripts/pipeline/10_calibs.sh --night $night -j 8
    ./scripts/pipeline/20_science.sh --night $night --skip-coadds -j 8
    ./scripts/pipeline/40_diff_imaging.sh \
        --night $night --auto-template --band $BAND -j 8
done

# 4. Extract light curve
python scripts/python/pipeline_tools/extract_lightcurve.py \
    --repo $REPO \
    --collection 'Nickel/runs/*/diff/*/run' \
    --ra $SN_RA --dec $SN_DEC \
    --radius 1.0 --band $BAND \
    --output sn2020wnt_lightcurve.ecsv

echo "Done! Light curve: sn2020wnt_lightcurve.ecsv"
```
