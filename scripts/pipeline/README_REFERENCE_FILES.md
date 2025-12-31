# Reference-Based Night Processing

## Problem: Observing Nights vs UT Day_Obs

The Nickel telescope has a timezone issue where **observing night labels** (directory names) don't match **Butler day_obs values** (UT dates in FITS headers):

- **Observing night**: Local date when observations BEGIN (e.g., `20210810` = Aug 10, 2021 local time)
- **Butler day_obs**: UT date when exposures are RECORDED (e.g., `20210811` = Aug 11, 2021 UT)

For California (UTC-8), most observations after ~4pm local time have the **next day's UT date** in their FITS headers.

## Solution: Reference YAML Files

Reference files explicitly map observing night labels to actual UT day_obs values that Butler uses.

### YAML Format

```yaml
object: "TARGET_NAME"

nights:
  20201207: [20201208]    # obs_night: [day_obs_values]
  20201219: [20201220]
  20210810: [20210811]    # Most common case: +1 day
  20210825: [20210825, 20210826]  # Rare: spans two UT days
```

### Creating Reference Files

**Option 1: Manually query Butler** (recommended for now)

```bash
# Source your environment
source .env
source $STACK_DIR/loadLSST.bash
setup lsst_distrib

# For each observing night, query Butler to find actual day_obs
butler query-dimension-records $REPO exposure \
  --where "instrument='Nickel' AND exposure.day_obs=20210811 AND exposure.target_name='2020wnt'"

# Create YAML file mapping obs_night -> day_obs
```

**Option 2: Use build_nights_reference.sh** (has environment issues)

```bash
./scripts/utilities/build_nights_reference.sh \
  --object 2020wnt \
  --nights scripts/config/2020wnt/sn_nights.txt \
  --output scripts/config/2020wnt/science_nights_reference.yaml
```

Note: This script has Butler environment issues in subshells. Manual creation is more reliable.

### Using Reference Files

#### Method 1: Reference files (recommended)

```bash
./scripts/pipeline/run_dia_multi_band.sh \
  --template-reference scripts/config/2020wnt/template_nights_reference.yaml \
  --science-reference scripts/config/2020wnt/science_nights_reference.yaml \
  --bands v \
  --ra 56.66 --dec 43.23 \
  --object "2020wnt"
```

#### Method 2: Plain text UT day_obs files

```bash
# Create files with actual UT dates (not observing nights)
echo "20201208" > template_nights.txt
echo "20201220" >> template_nights.txt

./scripts/pipeline/run_dia_multi_band.sh \
  --template-nights template_nights.txt \
  --science-nights science_nights.txt \
  --bands v \
  --ra 56.66 --dec 43.23
```

#### Method 3: Auto-convert observing nights (may have issues)

```bash
# Uses observing_night_to_ut.sh to query Butler
./scripts/pipeline/run_dia_multi_band.sh \
  --observing-template-nights template_obs_nights.txt \
  --observing-science-nights science_obs_nights.txt \
  --bands v \
  --ra 56.66 --dec 43.23
```

## Example Reference Files

See:
- [scripts/config/2020wnt/template_nights_reference.yaml](../config/2020wnt/template_nights_reference.yaml)
- [scripts/config/2020wnt/science_nights_reference.yaml](../config/2020wnt/science_nights_reference.yaml)

## Troubleshooting

### Empty quantum graphs

If you get "Initial data ID query returned no rows", you're likely using observing night dates instead of UT day_obs:

```
# WRONG (using observing night)
butler query-datasets $REPO --where "day_obs=20210810"

# CORRECT (using UT day_obs from reference file)
butler query-datasets $REPO --where "day_obs=20210811"
```

### How to verify correct day_obs

```bash
# Check what day_obs values exist for a target
butler query-dimension-records $REPO exposure \
  --where "instrument='Nickel' AND exposure.target_name='2020wnt'" | \
  awk '{print $3}' | sort -u
```

This shows all UT dates (day_obs) that have data for your target.
