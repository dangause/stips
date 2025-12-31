# DIA Pipeline Fix: Day_Obs-Based Collection Discovery

## Problem

The DIA pipeline (`40_diff_imaging.sh`) was searching for Butler collections by grepping collection paths:

```bash
# OLD - Failed when collections organized by UT day_obs
RAW_RUN="$(butler query-collections "$REPO" | grep -E "^Nickel/raw/${NIGHT}/" | tail -n1)"
SCI_PARENT="$(butler query-collections "$REPO" | grep -E "^Nickel/runs/${NIGHT}/" | tail -n1)"
```

This approach failed with error: `ERROR: No raw run found for night 20201208`

**Root cause**: The script assumed collections were organized by observing night labels, but reference files provide UT day_obs values. Even if collections use day_obs in their paths, grepping is fragile and doesn't handle:
- Different collection naming conventions
- Multiple runs for the same night
- Collections organized differently than expected

## Solution

Query Butler registry to find collections containing datasets with matching day_obs:

```bash
# NEW - Query Butler by day_obs (works regardless of collection naming)
RAW_RUN="$(butler query-datasets "$REPO" raw \
  --collections 'Nickel/raw/*' \
  --where "instrument='Nickel' AND exposure.day_obs=${NIGHT}" \
  2>/dev/null | tail -n +2 | head -1 | awk '{print $2}')"

SCI_PARENT="$(butler query-datasets "$REPO" preliminary_visit_image \
  --collections 'Nickel/runs/*' \
  --where "instrument='Nickel' AND exposure.day_obs=${NIGHT}" \
  2>/dev/null | tail -n +2 | head -1 | awk '{print $2}')"
```

## Changes Made

### File: `scripts/pipeline/40_diff_imaging.sh`

**Lines 209-216** (Raw collection discovery):
- Changed from grepping collection paths to querying raw datasets by day_obs
- Updated error message to clarify it's searching by day_obs

**Lines 334-357** (Science collection discovery):
- Changed from grepping collection paths to querying preliminary_visit_image datasets by day_obs
- Improved error output to show available datasets when not found

## Benefits

1. **Works with any collection naming convention** - doesn't assume path structure
2. **Finds the actual collection containing data** - queries the registry, not path strings
3. **Robust to UT/local time differences** - uses day_obs from Butler metadata
4. **Compatible with reference files** - works seamlessly with filter → day_obs → visits schema

## Testing

To test the fix, run:

```bash
./scripts/pipeline/run_dia_multi_band.sh \
  --template-reference scripts/config/2020wnt/template_nights_reference.yaml \
  --science-reference scripts/config/2020wnt/science_nights_reference.yaml \
  --bands v \
  --ra 56.66 --dec 43.23 \
  --object "2020wnt" \
  --skip-calibs \
  --skip-science \
  --skip-template-build
```

This should now correctly find raw and science collections for day_obs values like 20201208.

## Date: 2025-12-31
