# Observing Night Schema Refactor

## Date: 2025-12-31

## Summary

Refactored the DIA pipeline and reference files to properly distinguish between **observing nights** (collection organization) and **UT day_obs** (Butler queries). This fixes timezone confusion and empty quantum graphs.

## Problem

The original schema organized data by UT day_obs, but:
1. **Collections are named by observing night** (local date): `Nickel/raw/20201207/`, `Nickel/runs/20201207/`
2. **Butler queries use day_obs** (UT date from FITS): `exposure.day_obs=20201208`
3. **These differ by ~1 day** for California observations (UTC-8)

This mismatch caused:
- "No raw run found" errors when searching for collections by day_obs
- "No science run found" errors
- Empty quantum graphs from incorrect Butler queries

## Solution

### New Reference File Schema

**Before** (incorrect - organized by day_obs):
```yaml
filters:
  v:
    20201208:        # UT day_obs
      visits: [76482094]
```

**After** (correct - organized by observing night):
```yaml
nights:
  20201207:          # Observing night (local date)
    day_obs: 20201208  # UT date (for Butler queries)
    filters:
      v: [76482094]
      r: [76482095, 76482092]
      b: [76482093]
      i: [76482096]
```

### Key Changes

#### 1. Reference File Generation (`scripts/utilities/generate_nights_reference.py`)
- **New Python script** that queries Butler SQLite registry
- Automatically computes observing night from day_obs (subtract 1 day)
- Generates properly structured YAML with obs_night → day_obs → filters mapping
- Usage:
  ```bash
  python3 scripts/utilities/generate_nights_reference.py \
    $REPO "2020wnt" \
    --output science_nights_reference.yaml \
    --end-date 20211231  # Filter by date range
  ```

#### 2. Pipeline YAML Parsing (`run_dia_multi_band.sh`)
- **Updated `parse_reference_yaml()` function**
- Extracts **observing nights** (not day_obs) from reference files
- These are the keys under `nights:` section
- Passed to subscripts via `--night` parameter

#### 3. DIA Script Updates (`40_diff_imaging.sh`)
- **Added `obs_night_to_day_obs()` function** to convert obs_night → day_obs (+1 day)
- **Uses observing night** for collection path greps:
  - `Nickel/raw/${NIGHT}/` ✓ (NIGHT = observing night)
  - `Nickel/runs/${NIGHT}/` ✓
- **Uses day_obs** for Butler WHERE clauses:
  - `exposure.day_obs=${DAY_OBS}` ✓ (DAY_OBS = obs_night + 1)
- Example output:
  ```
  [night] Observing night: 20201207 (local date)
  [night] UT day_obs: 20201208 (FITS header date)
  ```

## Files Modified

1. **`scripts/utilities/generate_nights_reference.py`** [NEW]
   - Python script to generate reference YAML files from Butler registry
   - Auto-computes obs_night from day_obs

2. **`scripts/config/2020wnt/science_nights_reference.yaml`**
   - Regenerated with new schema: 37 nights (Dec 2020 - Dec 2021)
   - Organized by observing night with day_obs mapping

3. **`scripts/config/2020wnt/template_nights_reference.yaml`**
   - Regenerated with new schema: 9 nights (Jan-Feb 2022)
   - Template epochs when SN had faded

4. **`scripts/config/2020wnt/README.md`** [NEW]
   - Documentation for reference file schema
   - Usage examples and troubleshooting

5. **`scripts/pipeline/run_dia_multi_band.sh`**
   - Updated `parse_reference_yaml()` to extract observing nights
   - Updated usage documentation with new YAML format

6. **`scripts/pipeline/40_diff_imaging.sh`**
   - Added `obs_night_to_day_obs()` conversion function
   - Uses observing night for collection paths
   - Computes day_obs for Butler queries

7. **`scripts/pipeline/CHANGELOG_DAY_OBS_FIX.md`**
   - Previous changelog (now superseded by this refactor)

## Benefits

1. **Correct collection discovery**: Searches for `Nickel/raw/20201207/` (observing night)
2. **Correct Butler queries**: Uses `day_obs=20201208` (UT date from FITS)
3. **No timezone confusion**: Explicitly separates local vs UT dates
4. **Self-documenting**: Reference files show both obs_night and day_obs
5. **Automatic generation**: Script generates mappings from Butler registry

## Testing

Test the updated pipeline:

```bash
./scripts/pipeline/run_dia_multi_band.sh \
  --template-reference scripts/config/2020wnt/template_nights_reference.yaml \
  --science-reference scripts/config/2020wnt/science_nights_reference.yaml \
  --bands v \
  --ra 56.66 --dec 43.23 \
  --object "2020wnt" \
  --skip-calibs \
  --skip-template-build
```

Expected output:
```
[nights] Extracted 9 template nights from reference
[nights] Extracted 37 science nights from reference
[night] Observing night: 20201207 (local date)
[night] UT day_obs: 20201208 (FITS header date)
[inputs] RAW_RUN=Nickel/raw/20201207/20251230T001721Z
[science] Finding science processing run for observing night 20201207...
```

## Migration Guide

If you have old reference files organized by day_obs:

1. **Regenerate using the new script**:
   ```bash
   python3 scripts/utilities/generate_nights_reference.py \
     $REPO "YOUR_OBJECT" \
     --output new_reference.yaml
   ```

2. **Or manually convert**:
   - Change top-level key from `filters:` to `nights:`
   - For each night, subtract 1 day to get observing night
   - Add `day_obs:` field with the original UT date
   - Nest filters under the observing night

## Backwards Compatibility

- **Breaking change**: Old reference files (organized by day_obs) will not work
- **Recommendation**: Regenerate all reference files using the new script
- Plain text night files still work (interpreted as observing nights)
