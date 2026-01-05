# PS1 Templates for DIA - Complete Guide

This guide explains how to use Pan-STARRS1 (PS1) stacked images as templates for Difference Image Analysis (DIA) in the obs_nickel package.

## Table of Contents

- [Overview](#overview)
- [When to Use PS1 Templates](#when-to-use-ps1-templates)
- [Band Mapping](#band-mapping)
- [Quick Start](#quick-start)
- [Detailed Workflows](#detailed-workflows)
- [Template Discovery in DIA](#template-discovery-in-dia)
- [Troubleshooting](#troubleshooting)
- [Advanced Topics](#advanced-topics)

---

## Overview

### What are PS1 Templates?

Pan-STARRS1 (PS1) provides deep, high-quality stacked images covering the entire sky north of Dec -30°. These can serve as excellent templates for DIA when:
- You don't have enough Nickel observations to build internal templates
- You need templates for new fields
- You want deeper templates than achievable with limited Nickel data

### Architecture

The PS1 template system consists of:

1. **Download & Conversion** ([ingest_ps1_template.py](../packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/ingest_ps1_template.py))
   - Downloads PS1 cutouts from MAST or PS1 image services
   - Converts PS1 FITS to LSST Exposure format
   - Handles WCS and photometric calibration conversion

2. **Butler Ingestion**
   - Ingests PS1 exposures as `template_coadd` datasets
   - Auto-determines tract/patch from coordinates
   - Stores in `templates/ps1/` collections

3. **Metadata Tracking** ([template_metadata.py](../packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/template_metadata.py))
   - Records PS1 provenance (filter, coordinates, cutout size)
   - Enables template discovery and filtering

4. **DIA Integration** ([40_diff_imaging.sh](../scripts/pipeline/40_diff_imaging.sh))
   - Auto-discovers PS1 templates with `--prefer-ps1` flag
   - Seamlessly uses PS1 templates in subtraction pipeline

---

## When to Use PS1 Templates

### ✅ Good Use Cases

- **New Fields**: No existing Nickel observations → Use PS1
- **Sparse Coverage**: Only 1-2 Nickel nights → PS1 provides deeper template
- **Emergency Targets**: Need DIA immediately → PS1 available instantly
- **Comparison**: Test DIA quality with both internal and PS1 templates

### ❌ Not Recommended

- **Well-observed Fields**: If you have 5+ clear nights → Internal templates better
- **B-band**: PS1 has no B-band → Must use internal templates
- **Southern Fields**: PS1 only covers Dec > -30°

### Performance Expectations

| Aspect | Internal Templates | PS1 Templates |
|--------|-------------------|---------------|
| **Depth** | Depends on #nights (typically shallower) | Very deep (~5 years stacked) |
| **PSF Match** | Excellent (same telescope) | Good (PS1 PSF ~1", Nickel ~2-3") |
| **Photometry** | Native calibration | Requires band mapping/colorterms |
| **Coverage** | Limited to observed fields | Full sky (Dec > -30°) |
| **Availability** | After template building | Instant (download) |

---

## Band Mapping

### PS1 → Nickel Filter Conversion

PS1 and Nickel use different filter systems. The ingestion script automatically maps filters:

| PS1 Filter | λ_eff (Å) | Nickel Filter | Notes |
|------------|-----------|---------------|-------|
| **g** | 4866 | **v** (V) | PS1 g is bluer than Johnson V |
| **r** | 6215 | **r** (R) | Good match (Cousins R) |
| **i** | 7545 | **i** (I) | Good match (Cousins I) |
| **z** | 8679 | **i** (I) | Nickel has no z-band |
| **y** | 9633 | **i** (I) | Nickel has no y-band |

### Photometric Considerations

1. **Zeropoints**: PS1 zeropoints are extracted from FITS headers when available, otherwise defaults to 25.0 AB mag
2. **Color Terms**: Currently not applied - future enhancement
3. **V-band**: Using PS1 g as proxy for Nickel V is approximate (color-dependent offset ~0.3 mag)
4. **B-band**: No PS1 equivalent - must use internal templates

**Recommendation**: For critical photometry, prefer internal templates. PS1 templates work well for transient *detection*, but source photometry may need color corrections.

---

## Quick Start

### 1. Check if PS1 Coverage Exists

```bash
./scripts/utilities/check_template_coverage.sh \
    --ra 150.123 \
    --dec 2.456 \
    --band r \
    --check-ps1
```

This will tell you:
- If the field has PS1 coverage (Dec > -30°)
- If templates already exist in your Butler repo
- Recommendations for next steps

### 2. Ingest a Single PS1 Template

```bash
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 150.123 \
    --dec 2.456 \
    --band r \
    --collection templates/ps1/myfield/r \
    --size 0.2
```

**Parameters**:
- `--ra`, `--dec`: Field center (degrees)
- `--band`: Nickel band (b, v, r, i)
- `--collection`: Butler collection name (convention: `templates/ps1/FIELDNAME/BAND`)
- `--size`: Cutout size in degrees (default 0.2° = 12 arcmin)

### 3. Run DIA with PS1 Template

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20240625 \
    --template templates/ps1/myfield/r
```

Or use auto-discovery:

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20240625 \
    --prefer-ps1 \
    --auto-template \
    --band r
```

---

## Detailed Workflows

### Workflow 1: Single Field, Multiple Bands

For a supernova campaign targeting SN 2024abc:

```bash
# Field coordinates
RA=150.123
DEC=2.456
FIELD="sn2024abc"

# Ingest templates for r and i bands
for BAND in r i; do
    ./scripts/pipeline/08_ingest_ps1_template.sh \
        --ra $RA \
        --dec $DEC \
        --band $BAND \
        --collection templates/ps1/${FIELD}/${BAND} \
        --size 0.3
done

# Verify ingestion
butler query-datasets $REPO template_coadd \
    --collections "templates/ps1/${FIELD}/*"

# Run DIA for observation night
./scripts/pipeline/40_diff_imaging.sh \
    --night 20240625 \
    --template templates/ps1/${FIELD}/r
```

### Workflow 2: Batch Ingestion for Multiple Fields

Create a fields file `targets.txt`:

```
# NAME     RA        DEC       TRACT
sn2024abc  150.123   2.456     1825
sn2024xyz  210.456  15.789     1900
m67        132.825  11.800     1650
```

Run batch ingestion:

```bash
./scripts/utilities/batch_ingest_ps1.sh \
    --fields targets.txt \
    --bands "r,i" \
    --size 0.2 \
    -j 4  # 4 parallel jobs
```

This will:
- Ingest PS1 templates for all fields in both r and i bands
- Run 4 ingestions in parallel
- Log results to `logs/ps1_batch/TIMESTAMP/`

### Workflow 3: Using Existing PS1 FITS Files

If you've already downloaded PS1 images:

```bash
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 150.123 \
    --dec 2.456 \
    --band r \
    --ps1-fits /path/to/ps1_stack.fits \
    --skip-download \
    --collection templates/ps1/myfield/r
```

### Workflow 4: Template Comparison (Internal vs PS1)

Compare DIA quality with both template types:

```bash
NIGHT=20240625

# Run DIA with internal template
./scripts/pipeline/40_diff_imaging.sh \
    --night $NIGHT \
    --template templates/deep/tract1825/r \
    --band r

# Run DIA with PS1 template
./scripts/pipeline/40_diff_imaging.sh \
    --night $NIGHT \
    --template templates/ps1/myfield/r \
    --band r

# Compare results (check source counts, residuals, etc.)
```

---

## Template Discovery in DIA

The DIA pipeline ([40_diff_imaging.sh](../scripts/pipeline/40_diff_imaging.sh)) can automatically discover templates.

### Discovery Modes

#### 1. Manual Template Selection

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20240625 \
    --template templates/ps1/myfield/r
```

**Use when**: You know exactly which template to use

#### 2. Auto-Discovery (Internal Preference)

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20240625 \
    --auto-template \
    --band r
```

**Priority**:
1. `templates/deep/` (internally-built deep coadds)
2. `templates/` (other internal templates)
3. `coadds/` (regular coadds)

**Use when**: You have internal templates and want to use them by default

#### 3. Auto-Discovery (PS1 Preference)

```bash
./scripts/pipeline/40_diff_imaging.sh \
    --night 20240625 \
    --prefer-ps1 \
    --auto-template \
    --band r
```

**Priority**:
1. `templates/ps1/` (PS1 templates)
2. `templates/deep/` (fallback to internal if no PS1)

**Use when**: You prefer PS1 templates when available

### Date-Based Filtering (Transient Campaigns)

Exclude templates contaminated by the transient:

```bash
# SN 2023ixf exploded on 2023-05-19
# Exclude templates overlapping May 2023
./scripts/pipeline/40_diff_imaging.sh \
    --night 20230520 \
    --auto-template \
    --exclude-start 20230501 \
    --exclude-end 20230531
```

This uses metadata from `template_metadata.json` to filter templates.

---

## Troubleshooting

### Problem: Download Fails

**Symptoms**:
```
ERROR: All PS1 download methods failed
```

**Solutions**:

1. **Check PS1 service status**:
   - Try manually: https://ps1images.stsci.edu/cgi-bin/ps1filenames.py
   - PS1 services can be temporarily down

2. **Check coordinates**:
   ```bash
   # Verify Dec > -30°
   ./scripts/utilities/check_template_coverage.sh --ra RA --dec DEC --check-ps1
   ```

3. **Try different download method**:
   ```python
   # Edit ingest_ps1_template.py and force a specific method:
   download_ps1_cutout(..., force_service='fitscut')
   ```

4. **Manual download**:
   - Download from https://ps1images.stsci.edu/cgi-bin/fitscut.cgi
   - Use `--ps1-fits` flag to skip download

### Problem: WCS Conversion Fails

**Symptoms**:
```
ERROR: Failed to convert WCS
```

**Solutions**:

1. **Check FITS header**:
   ```bash
   fitsheader /path/to/ps1_template.fits | grep -E 'CRVAL|CRPIX|CD|CTYPE'
   ```

2. **Verify WCS with astropy**:
   ```python
   from astropy.io import fits
   from astropy.wcs import WCS

   with fits.open('ps1_template.fits') as hdul:
       wcs = WCS(hdul[0].header)
       print(wcs)
   ```

3. **Update astropy**:
   ```bash
   pip install --upgrade astropy
   ```

### Problem: Butler Ingestion Fails

**Symptoms**:
```
ERROR: Failed to ingest exposure
```

**Common Causes & Solutions**:

1. **Skymap not found**:
   ```bash
   # Check available skymaps
   butler query-datasets $REPO skyMap

   # Set correct skymap
   export SKYMAP_NAME=nickelRings-v1
   export SKYMAPS_CHAIN=skymaps/nickelRings,skymaps
   ```

2. **Dimension mismatch**:
   - PS1 templates use dimensions: `(skymap, tract, patch, band)`
   - Internal templates may have: `(instrument, skymap, tract, patch, band)`
   - The ingestion script handles this automatically

3. **Collection already exists**:
   ```bash
   # Check existing templates
   butler query-datasets $REPO template_coadd \
       --collections "templates/ps1/*"

   # Remove if needed (CAREFUL!)
   butler remove-runs $REPO templates/ps1/myfield/r
   ```

### Problem: DIA Fails with PS1 Template

**Symptoms**:
- PSF matching failure
- High residuals in difference image
- No sources detected

**Diagnostics**:

1. **Check PSF difference**:
   ```python
   # Compare seeing
   # PS1: ~1" typical
   # Nickel: 2-3" typical
   # Large PSF mismatch can cause issues
   ```

2. **Check photometric calibration**:
   ```python
   # Verify template zeropoint
   exposure = butler.get('template_coadd', ...)
   photo_calib = exposure.getPhotoCalib()
   print(photo_calib.getCalibrationMean())
   ```

3. **Adjust DIA parameters**:
   ```bash
   # Relax bad subtraction threshold
   ./scripts/pipeline/40_diff_imaging.sh \
       --night 20240625 \
       --template templates/ps1/myfield/r \
       --bad-sub-threshold 0.5  # default is 0.2
   ```

4. **Tune subtraction kernel**:
   Edit `configs/dia/subtractImages.py`:
   ```python
   # Increase kernel size for larger PSF differences
   config.kernelSize = 31  # default is 21
   ```

---

## Advanced Topics

### Custom PS1 Filter Mapping

Edit [ingest_ps1_template.py](../packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/ingest_ps1_template.py):

```python
# Customize band mapping
PS1_TO_NICKEL_BANDS = {
    "g": "b",  # Map PS1 g → Nickel B (not recommended)
    "r": "r",
    "i": "i",
    "z": "i",
    "y": "i",
}

# Customize zeropoints (if needed)
PS1_ZEROPOINTS = {
    "g": 25.1,  # Adjust based on your calibration
    "r": 25.0,
    "i": 24.9,
    "z": 24.5,
    "y": 23.5,
}
```

### Template Metadata Management

View all templates:

```bash
python packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/template_metadata.py \
    list --repo $REPO --verbose
```

Filter by source:

```bash
# Show only PS1 templates
python ... list --repo $REPO --source ps1

# Show only internal templates
python ... list --repo $REPO --source nickel
```

Query templates for a specific date range:

```bash
# Find templates NOT overlapping with SN activity
python ... query --repo $REPO \
    --exclude-start 20230515 \
    --exclude-end 20230531 \
    --band r
```

### Hybrid Templates (Advanced)

Combine PS1 base with Nickel observations for optimal depth and PSF matching:

1. Ingest PS1 template
2. Warp PS1 to Nickel pixel grid
3. Add clean Nickel visits from non-transient epochs
4. Create hybrid coadd

(This workflow is planned for future implementation)

### PS1 Cutout Size Optimization

| Cutout Size | Use Case | Download Time |
|-------------|----------|---------------|
| 0.1° (6') | Small galaxies, point sources | Fast (~5s) |
| 0.2° (12') | Default, good for most fields | Medium (~15s) |
| 0.3° (18') | Large galaxies, extended sources | Slow (~30s) |
| 0.5° (30') | Wide-field coverage | Very slow (~60s) |

**Recommendation**: Use 0.2° for most cases. Increase only if Nickel field-of-view requires it.

---

## Best Practices

### ✅ Do

- **Check coverage first**: Use `check_template_coverage.sh` before ingesting
- **Use consistent naming**: `templates/ps1/FIELDNAME/BAND` convention
- **Record metadata**: Ingestion automatically records, but verify with `template_metadata.py list`
- **Test DIA quality**: Compare subtraction with internal templates when available
- **Monitor band mapping**: PS1 g → Nickel V is approximate, check photometry

### ❌ Don't

- **Don't use for B-band**: No PS1 equivalent, results will be poor
- **Don't skip verify**: Always check template ingestion with `butler query-datasets`
- **Don't ignore seeing**: Large PSF mismatch (PS1 ~1" vs Nickel 4"+) may fail
- **Don't over-rely on photometry**: Use PS1 for detection, internal templates for precise photometry

---

## Additional Resources

### Scripts

- [08_ingest_ps1_template.sh](../scripts/pipeline/08_ingest_ps1_template.sh) - Single template ingestion wrapper
- [batch_ingest_ps1.sh](../scripts/utilities/batch_ingest_ps1.sh) - Batch ingestion for multiple fields
- [check_template_coverage.sh](../scripts/utilities/check_template_coverage.sh) - Check template availability
- [40_diff_imaging.sh](../scripts/pipeline/40_diff_imaging.sh) - DIA pipeline with PS1 support

### Python Modules

- [ingest_ps1_template.py](../packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/ingest_ps1_template.py) - Core ingestion logic
- [template_metadata.py](../packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/template_metadata.py) - Metadata management

### Tests

- [test_ps1_templates.py](../tests/test_ps1_templates.py) - Comprehensive test suite

### External Documentation

- [PS1 Image Services](https://outerspace.stsci.edu/display/PANSTARRS/PS1+Image+Cutout+Service)
- [PS1 Data Release](https://outerspace.stsci.edu/display/PANSTARRS/PS1+Data+Archive+Home+Page)
- [LSST DIA Pipeline](https://pipelines.lsst.io/v/weekly/modules/lsst.ip.diffim/index.html)

---

## Support

For questions, issues, or contributions:
- Check [troubleshooting](#troubleshooting) section
- Review test cases in `tests/test_ps1_templates.py`
- File issues on GitHub (if applicable)

**Happy template hunting!** 🔭
