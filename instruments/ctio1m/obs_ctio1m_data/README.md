# obs_ctio1m_data

Curated calibration data for the CTIO 1.0m (Yale/SMARTS 1m, Y4KCam) telescope.

## Overview

This package provides versioned calibration data for the CTIO1m instrument,
following the LSST `obs_lsst_data` pattern (mirrors `obs_nickel_data`). The
data can be ingested into a Butler repository using:

```bash
butler write-curated-calibrations <REPO> lsst.obs.stips.active.Instrument
```

## Directory Structure

```
CTIO1m/
└── defects/
    └── ccd0/              # Detector name (lowercase)
        └── YYYYMMDDTHHMMSS.ecsv   # Defects valid from this date
```

## Calibration Types

### Defects

Defect masks identify bad pixels that should be masked during ISR (Instrument
Signature Removal). Each ECSV file contains rectangular defect regions with:

- `x0`, `y0`: Bottom-left corner coordinates (pixels)
- `width`, `height`: Dimensions of the defect region (pixels)

The filename timestamp indicates when the defects become valid. Defects
remain valid until superseded by a newer file.

The base file `CTIO1m/defects/ccd0/19700101T000000.ecsv` is an EMPTY defect
table (zero rows) valid from the epoch. It masks nothing, so all pre-2010
epochs (e.g. the 2006 NGC2298 run, where amp A01 is healthy) process
unaffected. A later, epoch-scoped file (validity start = the first affected
night) carries the amp A01 dead-region box for the Jan-2010 SA98 run.

## Adding New Calibrations

### Defects

1. Generate defects (box coordinates) for the affected epoch
2. Convert to ECSV format with proper metadata headers (see the base file)
3. Name the file with the validity start date: `YYYYMMDDTHHMMSS.ecsv`
4. Place in `CTIO1m/defects/ccd0/`

### ECSV Format

Defect files use the ECSV 0.9 format with metadata:

```
# %ECSV 0.9
# ---
# datatype:
# - {name: x0, unit: pixel, datatype: int32, description: x coordinate of bottom-left corner of box}
# - {name: y0, unit: pixel, datatype: int32, description: y coordinate of bottom-left corner of box}
# - {name: width, unit: pixel, datatype: int32, description: width of box}
# - {name: height, unit: pixel, datatype: int32, description: height of box}
# meta: !!omap
# - {OBSTYPE: defects}
# - {INSTRUME: CTIO1m}
# - {DETECTOR: 0}
# - {CALIBDATE: 'YYYY-MM-DD'}
# - SCHEMA_VERSION: {simple: 1}
# schema: astropy-2.0
x0 y0 width height
...
```

## Curated calibration discovery

`butler write-curated-calibrations` discovers this package via the active
instrument's `obsDataPackage` attribute. The synthesized instrument
(`lsst.obs.stips`) sets `obsDataPackage` from the profile's `obs_data_package`
field, declared in `instruments/ctio1m/profile.py`:

```python
profile = InstrumentProfile(
    name="CTIO1m",
    obs_data_package="obs_ctio1m_data",
    # ... rest of the profile
)
```

Once configured, `butler write-curated-calibrations` automatically finds and
ingests calibrations from this package.

## Version History

- **0.1.0**: Initial release with an empty base defect (masks nothing); the
  epoch-scoped amp A01 defect for the Jan-2010 SA98 run follows.
