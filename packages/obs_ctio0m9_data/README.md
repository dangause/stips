# obs_ctio0m9_data

Curated calibration data for the CTIO/SMARTS 0.9m telescope with Tek2K CCD.

## Contents

### Defects

Located in `ctio0m9/defects/SITE2K/`:

- `20090527T000000.ecsv` - Defect map derived from bias frame analysis
  - Bad column at x=293 (full detector height)
  - Hot pixel regions identified from 5-sigma outlier analysis

## Usage

This package is automatically discovered by the LSST Butler when
`obs_ctio0m9` sets `obsDataPackage = "obs_ctio0m9_data"`.

To ingest curated calibrations:

```bash
butler write-curated-calibrations REPO ctio0m9 INPUT_COLLECTION --collection OUTPUT_COLLECTION
```

## File Format

Defect files use ECSV format with columns:
- `x0`: X coordinate of bottom-left corner (pixels)
- `y0`: Y coordinate of bottom-left corner (pixels)
- `width`: Width of defect region (pixels)
- `height`: Height of defect region (pixels)

Required metadata:
- `OBSTYPE`: "defects"
- `INSTRUME`: "ctio0m9"
- `DETECTOR`: detector ID (0 for SITE2K)
- `CALIBDATE`: validity start date (YYYY-MM-DD)
