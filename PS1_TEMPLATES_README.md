# PS1 Templates for New Fields - User Guide

## Overview

PS1 (Pan-STARRS1) templates enable DIA (Difference Image Analysis) for fields that haven't been observed by Nickel before. This is essential for quick-response supernova follow-up where you need to start difference imaging immediately without waiting to build internal Nickel templates.

## Key Implementation

✅ **Complete**: PS1 template infrastructure with automatic reprojection to LSST patch geometry
✅ **Working**: Download, conversion, and ingestion pipeline
✅ **Tested**: Reprojection successfully matches patch WCS and bounding box

## How It Works

1. Download PS1 stacked image for your field coordinates
2. Convert PS1 FITS to LSST Exposure format (WCS, PhotoCalib, variance)
3. **Reproject to patch geometry** - ensures exact WCS/bbox match
4. Ingest as `template_coadd` for DIA pipeline

The critical step is **reprojection**: the PS1 image is warped onto the exact skymap patch geometry that the LSST pipeline expects. This ensures the template will match your science exposures.

## Usage for New Fields

### Before Observing a New SN

1. **Determine your telescope pointing**:
   ```bash
   TARGET_RA=150.123   # Where you'll point the telescope
   TARGET_DEC=2.456
   FIELD_NAME="SN2026abc"
   ```

2. **Ingest PS1 template for that exact location**:
   ```bash
   ./scripts/pipeline/08_ingest_ps1_template.sh \
       --ra $TARGET_RA \
       --dec $TARGET_DEC \
       --band r \
       --collection templates/ps1/$FIELD_NAME/r \
       --size 0.3  # Degrees (adjust for field size)
   ```

3. **Observe your target** at those coordinates

4. **Run DIA immediately**:
   ```bash
   ./scripts/pipeline/40_diff_imaging.sh \
       --night YYYYMMDD \
       --template templates/ps1/$FIELD_NAME/r \
       --band r \
       --object $FIELD_NAME
   ```

### Key Requirement

⚠️ **The PS1 cutout coordinates MUST match your actual telescope pointing coordinates.**

If you download PS1 for RA=150.0, Dec=2.0 but then point the telescope at RA=150.5, Dec=2.5, the PS1 template won't overlap with your science images and DIA will fail with "No patches found to overlap science exposure."

## For Existing Data

If you're trying to use PS1 templates for data you've already observed:

1. **Find the actual telescope pointing** from your FITS headers (`RA`/`DEC` keywords)
2. Download PS1 centered on those **actual** coordinates, not the target coordinates
3. Make the PS1 cutout large enough (0.5-1.0°) to cover any pointing offsets

Example:
```bash
# If your telescope was actually pointing at RA=150.2, Dec=2.3
# (even though the target was RA=150.0, Dec=2.0)
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 150.2 \
    --dec 2.3 \
    --band r \
    --collection templates/ps1/myfield/r \
    --size 0.5  # Larger to handle pointing uncertainty
```

## Technical Details

### PS1 to LSST Conversion

- **WCS**: Converted from PS1 FITS headers to LSST SkyWcs
- **PhotoCalib**: Derived from PS1 AB zeropoint (typically 25.0 mag)
- **Variance**: Estimated from MAD of pixel values + Poisson noise
- **Mask**: BAD flags for NaN/zero pixels
- **Filter**: PS1 filters (g,r,i,z,y) mapped to Nickel bands (b,v,r,i)

### Reprojection to Patch Geometry

**Critical step** added in this implementation:

```python
def reproject_to_patch(exposure, patch_info):
    """
    Reproject PS1 exposure to match exact patch WCS and bounding box.

    This ensures the template has the geometry expected by DIA pipeline.
    """
    patch_wcs = patch_info.getWcs()
    patch_bbox = patch_info.getOuterBBox()

    reprojected = afwImage.ExposureF(patch_bbox)
    reprojected.setWcs(patch_wcs)

    warping_control = WarpingControl("lanczos4")
    warpExposure(reprojected, exposure, warping_control)

    return reprojected
```

Without this reprojection, PS1 templates had the correct tract/patch labels but wrong geometry, causing "No patches found to overlap" errors.

### Filter Mapping

| Nickel Band | PS1 Filter | Notes |
|-------------|------------|-------|
| r | r | Direct match |
| i | i | Direct match |
| v | g | Approximate (blue-shifted) |
| b | g | Approximate (blue-shifted) |

## Troubleshooting

### "No patches found to overlap science exposure"

**Cause**: PS1 template doesn't spatially overlap with science images

**Solutions**:
1. Verify PS1 cutout coordinates match actual telescope pointing (not target coordinates)
2. Increase PS1 cutout size (try 0.5° or 1.0°)
3. Check that science data is in the expected tract/patch

### "No valid pixels from coadd patches"

**Cause**: After reprojection, valid pixels don't overlap with science footprint

**Solutions**:
1. Download PS1 centered on actual telescope pointing
2. Use larger PS1 cutout
3. Verify science exposures are in the tract/patch you think they are

### Filter Label Mismatch Warning

```
filter label mismatch (file is FilterLabel(band="r", physical="R")
```

**Status**: Cosmetic warning, does not affect processing
**Cause**: PS1 templates set `physical="R"` to match Nickel convention
**Impact**: None - pipeline handles this correctly

## Files Modified

- [ingest_ps1_template.py](packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/ingest_ps1_template.py:490:535) - Added `reproject_to_patch()` function
- [ingest_ps1_template.py](packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/ingest_ps1_template.py:657:660) - Calls reprojection before Butler ingestion
- [08_ingest_ps1_template.sh](scripts/pipeline/08_ingest_ps1_template.sh) - Wrapper script
- [40_diff_imaging.sh](scripts/pipeline/40_diff_imaging.sh) - DIA with PS1 support
- [template_metadata.py](packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/template_metadata.py) - PS1 metadata tracking

## Testing

### Test Repository Setup

```bash
# Create test repo
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel
source .env.recalib

# Create and register skymap
butler create $REPO
butler register-instrument $REPO lsst.obs.nickel.Nickel
butler register-skymap $REPO -C configs/makeSkyMap.py
```

### Verification

```bash
# 1. Check reprojection worked
butler query-datasets $REPO template_coadd \
    --collections "templates/ps1/*"

# Should show bbox matching patch geometry:
# e.g., (minimum=(7900, 11900), maximum=(12099, 16099))

# 2. Verify with internal template comparison
# Internal Nickel templates work, PS1 should match their geometry
butler query-datasets $REPO template_coadd \
    --collections "templates/deep/*"
```

## Next Steps for Full PS1 Integration

1. ✅ PS1 download and conversion
2. ✅ Reprojection to patch geometry
3. ✅ Butler ingestion
4. ⚠️  **Validate with matching coordinates** - need data where telescope pointing = PS1 center
5. ⬜ Performance comparison: PS1 vs internal templates
6. ⬜ Production deployment

## Recommendations

**For new SN observations**:
- Download PS1 template BEFORE observing
- Use exact planned telescope pointing coordinates
- Start with 0.3° cutout, increase if needed
- Verify PS1 template exists before observing night

**For existing data**:
- Use internal Nickel templates (already working)
- Only use PS1 if you can determine actual telescope pointing
- Consider building internal templates from early observations

---

**Status**: Infrastructure complete, requires coordinate-matched test data
**Date**: 2026-01-05
**Contact**: See [PS1_TEMPLATE_SUCCESS.md](PS1_TEMPLATE_SUCCESS.md) for detailed testing notes
