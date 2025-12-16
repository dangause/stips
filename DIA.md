# Difference Image Analysis (DIA)

## Quick Start

### 1. Build Template
```bash
./scripts/30_coadds.sh --tract 1099 --band r --nights 20240624 -j 8
```

### 2. Run DIA
```bash
./scripts/40_diff_imaging.sh \
  --night 20240624 \
  --template templates/deep/tract1099/r \
  --band r -j 8
```

### 3. Extract Light Curve
```bash
./scripts/run_extract_lightcurve.sh \
  --repo $REPO \
  --collection 'Nickel/runs/20240624/diff/*/run' \
  --ra 266.3396 --dec -0.4552 \
  --radius 5.0 --min-snr 3.0 \
  --output lightcurve.csv \
  --verbose
```

## Tract Coverage

Your data spans multiple sky tracts in the nickelRings-v1 skymap:

| Tract | Nights | Targets |
|-------|--------|---------|
| 1099 | 20240624 | 109_199 |
| 1255 | 20240624 | PG1530+057 |
| 1856 | 20201219, 20210208, 20210218 | 2020uxz, 2020sgf |
| 1825 | 20201208 | 2020wnt |
| 1876 | 20201207 | 2020yvu |
| 812 | 20201207 | 2020aatb |

**Key Point**: Template and science visits must overlap the same tract.

## Scripts

- `30_coadds.sh` - Build template coadds from multiple nights
- `40_diff_imaging.sh` - Run DIA pipeline on science visits
- `run_extract_lightcurve.sh` - Extract light curves from DIA catalogs
- `extract_lightcurve.py` - Python light curve extraction (use wrapper script)
- `find_visit_ids.sh` - Find valid visit IDs for a night

## Expected Behavior

**Not all visits succeed** - this is normal!
- Success rate 70-90% is excellent
- Visits fail with `BadSubtractionError` when:
  - Seeing differs between science and template
  - Sky brightness changes significantly
  - PSF matching doesn't converge well

Your test run: 78% success rate (14/18 quanta) ✅

## File Locations

- **Logs**: `logs/diff_*.log`
- **Quantum graphs**: `$REPO/qgraphs/diff_*.qg`
- **DIA catalogs**: Butler collection `Nickel/runs/{NIGHT}/diff/{TIMESTAMP}/run`
- **Difference images**: Same collection as catalogs

## Light Curve Output

CSV columns:
- `mjd` - Modified Julian Date (from visit records)
- `band` - Filter (b/v/r/i)
- `visit` - Visit ID
- `ra`, `dec` - Source coordinates (radians)
- `flux`, `flux_err` - Instrumental flux (ADU)
- `mag`, `mag_err` - Instrumental magnitude (zeropoint 31.4)
- `snr` - Signal-to-noise ratio
- `separation_arcsec` - Distance from target position

## Troubleshooting

**Empty quantum graph** → Visit doesn't overlap template tract. Check tract coverage above.

**BadSubtractionError** → Normal! Adjust threshold in `pipelines/DRP.yaml` if needed:
```yaml
detectAndMeasureDiaSource:
  config:
    badSubtractionRatioThreshold: 5.0  # Default: 0.2
```

**Object not found** → Use `--ra` and `--dec` instead of `--object` for objects not in SIMBAD/NED.

**No template available** → You need reference images without the transient. For 2020wnt, you only have observations when the SN was active.

## Pipeline Configuration

Uses `pipelines/DRP.yaml#difference-imaging` subset:
- `rewarpTemplate` - Warp template to science image WCS
- `subtractImages` - Alard-Lupton image subtraction
- `detectAndMeasureDiaSource` - Detect and measure DIA sources

## Production Notes

The DIA tasks are currently **commented out** in `pipelines/DRP.yaml`. To enable:

1. Uncomment lines 208-252 (task definitions)
2. Uncomment lines 369-373 (subset definition)
3. Uncomment lines 388-389 (step definition)

Until then, the pipeline automatically detects this and works without those sections.
