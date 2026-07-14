# obs_nickel_data

Curated calibration data for the Nickel 1-meter telescope at Lick Observatory.

## Overview

This package provides versioned calibration data for the Nickel telescope, following the LSST `obs_lsst_data` pattern. The data can be ingested into a Butler repository using:

```bash
butler write-curated-calibrations <REPO> lsst.obs.stips.active.Instrument
```

## Directory Structure

```
Nickel/
└── defects/
    └── ccd0/              # Detector name (lowercase)
        └── YYYYMMDDTHHMMSS.ecsv   # Defects valid from this date
```

## Calibration Types

### Defects

Defect masks identify bad pixels that should be masked during ISR (Instrument Signature Removal). Each ECSV file contains rectangular defect regions with:

- `x0`, `y0`: Bottom-left corner coordinates (pixels)
- `width`, `height`: Dimensions of the defect region (pixels)

The filename timestamp indicates when the defects become valid. Defects remain valid until superseded by a newer file.

## Adding New Calibrations

### Defects

1. Generate defects using the `stips-defects-build` tool (see `instruments/nickel/defects/README.md`)
2. Convert the CSV output to ECSV format with proper metadata headers
3. Name the file with the validity start date: `YYYYMMDDTHHMMSS.ecsv`
4. Place in `Nickel/defects/ccd0/`

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
# - {INSTRUME: Nickel}
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
field, declared in `instruments/nickel/profile.py`:

```python
profile = InstrumentProfile(
    name="Nickel",
    obs_data_package="obs_nickel_data",
    # ... rest of the profile
)
```

Once configured, `butler write-curated-calibrations` automatically finds and
ingests calibrations from this package.

## Version History

- **0.1.0**: Initial release with defect masks derived from flat field analysis
