# Using PS1 Templates for Difference Imaging

This guide explains how to use Pan-STARRS1 (PS1) survey images as templates for difference imaging when you don't have archival Nickel data for a field.

## Overview

The PS1 template ingestion workflow:
1. **Downloads** PS1 stacked images from STScI MAST archive
2. **Converts** PS1 FITS to LSST Exposure format with proper WCS and photometric calibration
3. **Ingests** into your Butler repository as `template_coadd` datasets
4. **Uses** in your existing DIA pipeline without modification

## Quick Start

### Basic Usage

For a new supernova at RA=150.123°, Dec=2.456° in R-band:

```bash
# Download and ingest PS1 r-band template
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 150.123 \
    --dec 2.456 \
    --band r \
    --collection templates/ps1/r
```

This will:
- Auto-download PS1 r-band stacked image
- Convert to Nickel R-band template
- Ingest into collection `templates/ps1/r`
- Auto-determine the tract/patch from coordinates

### Using the Template in DIA

Once ingested, use the PS1 template in your DIA pipeline:

```bash
# Run DIA with PS1 template
./scripts/pipeline/40_diff_imaging.sh \
    --night 20241222 \
    --template templates/ps1/r \
    --band r
```

Or in the full transient pipeline:

```bash
# Skip template building, use PS1 instead
./scripts/pipeline/run_full_transient_pipeline.sh \
    --template-nights dummy_nights.txt \
    --dia-nights campaign_nights.txt \
    --band r \
    --transient-name "SN2024xyz" \
    --ra 150.123 \
    --dec 2.456 \
    --skip-template
```

Then manually set the template collection in your pipeline configuration or pass to DIA script.

## Filter Mapping

PS1 → Nickel band mapping:

| Nickel Band | PS1 Band | Quality | Notes |
|-------------|----------|---------|-------|
| R           | r        | ★★★★★   | Excellent match |
| I           | i        | ★★★★★   | Excellent match |
| V           | g        | ★★★☆☆   | Reasonable (color terms needed) |
| B           | g        | ★★☆☆☆   | Poor match (use with caution) |

### Auto-Mapping

By default, the script auto-maps:
- `--band r` → PS1 r
- `--band i` → PS1 i
- `--band v` → PS1 g
- `--band b` → PS1 g

Override with `--ps1-band`:

```bash
# Force PS1 i-band for Nickel V (not recommended)
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 150.123 --dec 2.456 \
    --band v \
    --ps1-band i
```

## Advanced Usage

### Specify Tract/Patch

If you know the tract number:

```bash
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 150.123 --dec 2.456 \
    --band r \
    --tract 1099 \
    --collection templates/ps1/r/tract1099
```

### Use Existing PS1 FITS

If you already downloaded PS1 images:

```bash
# Ingest from existing FITS
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 150.123 --dec 2.456 \
    --band r \
    --ps1-fits ./my_ps1_image.fits \
    --skip-download
```

### Larger Cutouts

For extended fields (default is 0.2° = 12 arcmin):

```bash
# 0.5 degree cutout
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 150.123 --dec 2.456 \
    --band r \
    --size 0.5
```

### Download Only (No Ingest)

To inspect the PS1 image before ingesting:

```bash
# Download and convert, but don't ingest
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 150.123 --dec 2.456 \
    --band r \
    --skip-ingest \
    --output-dir ./ps1_preview

# Check the FITS
ds9 ./ps1_preview/lsst_template_r.fits
```

## Troubleshooting

### No PS1 Coverage

PS1 covers δ > -30°. For southern targets, consider:
- Skymapper (southern hemisphere survey)
- DECam Legacy Survey (DECaLS)
- Building templates from other Nickel nights if available

### Download Failures

The script tries two methods:
1. MAST archive query (preferred)
2. PS1 image cutout service (fallback)

If both fail, manually download from:
- https://ps1images.stsci.edu/cgi-bin/ps1cutouts
- https://mast.stsci.edu/

Then use `--ps1-fits` to ingest.

### Photometric Calibration Issues

PS1 zeropoints are approximate (~25 AB mag). For precise photometry:

1. Check the ingested template:
```bash
butler get $REPO template_coadd \
    --collections templates/ps1/r \
    tract=1099 patch=42 band=r
```

2. Verify PhotoCalib:
```python
import lsst.daf.butler as dafButler
butler = dafButler.Butler('/path/to/repo')
template = butler.get('template_coadd',
                      collections='templates/ps1/r',
                      tract=1099, patch=42, band='r')
print(template.getPhotoCalib())
```

3. If needed, manually adjust zeropoint in the Python script (`PS1_ZEROPOINTS` dict)

### PSF Matching Failures

PS1 seeing is typically ~1.0-1.3", better than Nickel (~2.0"). The DIA pipeline will:
- Convolve PS1 template to match Nickel PSF ✓
- This is the preferred direction (easier than deconvolution)

If PSF matching fails:
- Check `subtractImages` config in `configs/dia/subtractImages.py`
- Increase `makeKernel.kernelSize` if needed (default: 21)
- Check for sufficient kernel stars (`detection.thresholdValue`)

## Python API

For programmatic use:

```python
from pathlib import Path
import sys
sys.path.insert(0, str(Path('scripts/python/pipeline_tools')))

from ingest_ps1_template import (
    download_ps1_cutout,
    convert_ps1_to_lsst_exposure,
    ingest_exposure_to_butler
)

# Download
ps1_fits = download_ps1_cutout(
    ra=150.123, dec=2.456,
    band='r', size_deg=0.2,
    output_dir='./ps1_data'
)

# Convert
exposure = convert_ps1_to_lsst_exposure(ps1_fits, nickel_band='r')

# Ingest
import lsst.daf.butler as dafButler
butler = dafButler.Butler('/path/to/repo', writeable=True)
data_id = ingest_exposure_to_butler(
    butler, exposure,
    ra=150.123, dec=2.456,
    band='r',
    collection='templates/ps1/r'
)
```

## Dependencies

The script requires:
- `astroquery` (for PS1 access)
- `requests` (for HTTP downloads)
- LSST Stack (lsst_distrib)

If `astroquery` is not installed:

```bash
# In your LSST environment
pip install astroquery
```

## Validation Checklist

Before using PS1 templates in production:

- [ ] Verify PS1 coverage at your coordinates
- [ ] Check filter mapping is appropriate
- [ ] Confirm template was ingested: `butler query-datasets`
- [ ] Test DIA on one visit before batch processing
- [ ] Inspect difference images visually
- [ ] Check for systematic artifacts (edge effects, bad PSF matching)
- [ ] Validate photometry against known sources

## Integration with Existing Workflows

### Single-Night DIA

```bash
# 1. Ingest PS1 template
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 83.8145 --dec 3.0847 \
    --band r

# 2. Process calibrations
./scripts/pipeline/10_calibs.sh --night 20241222

# 3. Process science
./scripts/pipeline/20_science.sh --night 20241222

# 4. Run DIA with PS1 template
./scripts/pipeline/40_diff_imaging.sh \
    --night 20241222 \
    --template templates/ps1/r \
    --band r
```

### Batch Processing

For multiple nights:

```bash
# Create nights list
cat > sn_campaign.txt <<EOF
20241222
20241223
20241224
EOF

# Ingest PS1 template once
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 83.8145 --dec 3.0847 --band r

# Batch process with PS1 template
# (Requires manual modification of batch script to use templates/ps1/r)
./scripts/pipeline/batch_process_nights.sh \
    --nights-file sn_campaign.txt \
    --run-dia \
    --dia-template templates/ps1/r
```

## Comparison: PS1 vs Nickel Templates

| Aspect | PS1 Template | Nickel Template |
|--------|--------------|-----------------|
| **Depth** | ~23 mag | ~21-22 mag (single night) |
| **Seeing** | 1.0-1.3" | ~2.0" |
| **PSF matching** | Convolve PS1 → Nickel ✓ | Match similar PSFs ✓ |
| **Filter accuracy** | Approximate (r,i good) | Exact |
| **Photometry** | Approximate zeropoints | Calibrated with refcats |
| **Template contamination** | None (pre-transient) ✓ | Risk if SN in data |
| **Availability** | δ > -30° coverage | Only observed fields |
| **Setup time** | ~5 minutes | Hours (download + stack) |

## Best Practices

1. **Use PS1 for:**
   - New transients without archival coverage
   - Quick-look difference imaging
   - R and I bands (best filter match)

2. **Use Nickel templates for:**
   - Fields with good archival coverage (>3 nights)
   - Precise photometry requirements
   - B and V bands (better filter match)

3. **Quality control:**
   - Always visually inspect first difference image
   - Check for edge artifacts, bad PSF matching
   - Validate against 2-3 known sources if available

## Support

Issues or questions:
- Check Butler ingestion: `butler query-datasets $REPO template_coadd`
- Verify DIA config: `configs/dia/subtractImages.py`
- Review logs in `$REPO/logs/`
- Open GitHub issue with error messages
