# 2020wnt Reference Files

## Overview

These reference files map **observing nights** (local dates) to **UT day_obs** values (FITS header dates) for the 2020wnt supernova campaign. This mapping is necessary because:

- **Butler collections** are organized by observing night (e.g., `Nickel/raw/20201207/`)
- **Butler registry queries** use UT day_obs from FITS headers (e.g., `exposure.day_obs=20201208`)
- For California observations (UTC-8), most nights after ~4pm local time have **day_obs = obs_night + 1**

## Schema

```yaml
object: "2020wnt"

nights:
  20201207:                     # Observing night (local date when observations began)
    day_obs: 20201208           # UT date in FITS headers
    filters:
      v: [76482094]             # Visit IDs for V-band
      r: [76482095, 76482092]   # Visit IDs for R-band
      b: [76482093]             # Visit IDs for B-band
      i: [76482096]             # Visit IDs for I-band
```

### Key Concepts

- **Observing night**: Local date when observations BEGIN (directory names, collection paths)
- **day_obs**: UT date when exposures are RECORDED (FITS headers, Butler WHERE clauses)
- **Filters**: Per-night, per-band visit ID lists (optional, for fine-grained control)

## Files

### `science_nights_reference.yaml`
- **Purpose**: Science epochs when the SN was BRIGHT
- **Date range**: Dec 2020 - Dec 2021 (37 nights)
- **Usage**: These nights are processed for DIA to detect the transient

### `template_nights_reference.yaml`
- **Purpose**: Template epochs when the SN had FADED
- **Date range**: Jan 2022 - Feb 2022 (9 nights)
- **Usage**: These nights are used to build deep template coadds (no transient contamination)

## Usage

### Run DIA Pipeline

```bash
./scripts/pipeline/run_dia_multi_band.sh \
  --template-reference scripts/config/2020wnt/template_nights_reference.yaml \
  --science-reference scripts/config/2020wnt/science_nights_reference.yaml \
  --bands v,r,i \
  --ra 56.66 --dec 43.23 \
  --object "2020wnt"
```

## Date: 2025-12-31
