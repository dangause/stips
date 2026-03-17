# Phase 3A Design Specification: obs_ctio0m9 LSST Instrument Package

**Date:** 2026-03-17
**Status:** Draft
**Author:** Claude
**Branch:** feature/obs-smalltel-phase1

## Overview

Build an LSST Science Pipelines instrument package for the CTIO/SMARTS 0.9m telescope with Tek2K CCD, supporting **single-amplifier readout mode only**. This is the minimal viable instrument package that proves the multi-telescope architecture works.

## Background

### Why CTIO 0.9m?

- **Single-amp mode available** — simplest FITS format (single-extension, like Nickel)
- **Public archive with REST API** — NOIRLab Astro Data Archive at `astroarchive.noirlab.edu`
- **Similar pixel scale to Nickel** — 0.401"/px vs 0.37"/px
- **Legacy reference** — deprecated `obs_ctio0m9` (Gen2) provides header translation patterns
- **Southern hemisphere** — complements Lick's Northern sky coverage

### Telescope Specifications

| Parameter | Value |
|-----------|-------|
| Aperture | 0.9 m |
| Location | Cerro Tololo, Chile |
| Operator | SMARTS Consortium / Georgia State University |
| Plate Scale | 16.0 arcsec/mm (0.401"/px) |
| FOV | 13.6' × 13.6' |

### Tek2K CCD Specifications

| Parameter | Value |
|-----------|-------|
| Detector | SITE2K (Tek2K_3) |
| Pixels | 2048 × 2048 |
| Pixel Size | 24 × 24 μm |
| Gain | ~2.8 e-/ADU (single-amp) |
| Read Noise | ~15 ADU |
| Saturation | 30,000 DN (conservative) |

### Readout Modes

| Mode | Amps | Support |
|------|------|---------|
| SINGLE | 1 | ✅ This phase |
| DUAL | 2 | ❌ Out of scope |
| QUAD | 4 | ❌ Out of scope |

Single-amp mode is the science-quality readout with lowest noise. Dual/quad modes trade noise for speed.

## Design Decisions

### D1: Single-Amp Only

**Decision:** Support only single-amplifier readout mode.

**Rationale:**
- Minimal complexity — mirrors obs_nickel pattern exactly
- Single-amp is the preferred science mode (lowest read noise)
- Quad mode has known issues (amp 1 unreliable since 2009)
- Can add multi-amp support later if needed (YAGNI)

### D2: Package Location

**Decision:** `packages/obs_ctio0m9/` parallel to `packages/obs_nickel/`

**Rationale:** Consistent monorepo structure. Each LSST instrument package is a separate directory.

### D3: EUPS Compatibility

**Decision:** Include `ups/obs_ctio0m9.table` for EUPS compatibility.

**Rationale:** LSST stack uses EUPS for package management. Required for `setup obs_ctio0m9` to work.

### D4: No Curated Calibrations Package

**Decision:** No `obs_ctio0m9_data` package initially.

**Rationale:** We'll build calibrations from archive data rather than shipping pre-built defect maps. Can add later if needed.

### D5: Reference Catalog Strategy

**Decision:** Defer refcat setup to Phase 3B. Plan to use MONSTER with RA/DEC cone queries.

**Rationale:** MONSTER covers Southern sky. The small_tel_tools plugin (Phase 3B) will handle refcat ingestion per-field rather than whole-sky pre-ingestion.

### D6: Filter Handling

**Decision:** Support Johnson-Cousins UBVRI as primary filters. Handle dual filter wheel by concatenating FILTER1+FILTER2.

**Rationale:** Johnson-Cousins is the standard filter set for CTIO 0.9m. The dual filter wheel sometimes uses both positions (e.g., "V+OPEN").

## Package Structure

```
packages/obs_ctio0m9/
├── camera/
│   └── ctio0m9.yaml              # Camera geometry
├── configs/
│   └── (empty initially)         # Pipeline config overrides
├── pipelines/
│   ├── DRP.yaml                  # Data release pipeline
│   ├── DIA.yaml                  # Difference imaging
│   └── ForcedPhotRaDec.yaml      # Forced photometry
├── python/lsst/obs/ctio0m9/
│   ├── __init__.py
│   ├── _instrument.py            # Ctio0m9 class
│   ├── _version.py
│   ├── ctio0m9Filters.py         # Filter definitions
│   ├── rawFormatter.py           # FITS reader
│   └── translator.py             # Header translations
├── tests/
│   └── test_instrument.py
├── pyproject.toml
└── ups/
    └── obs_ctio0m9.table
```

## Component Specifications

### Camera Geometry (ctio0m9.yaml)

Single detector (SITE2K), single amplifier configuration:

```yaml
name: ctio0m9

AMP: &AMP
  perAmpData: true
  dataExtent: [2098, 2048]           # 2048 active + ~50 overscan
  readCorner: LL
  rawBBox: [[0, 0], [2098, 2048]]
  rawDataBBox: [[10, 0], [2048, 2048]]
  rawSerialPrescanBBox: [[0, 0], [10, 2048]]
  rawSerialOverscanBBox: [[2058, 0], [40, 2048]]
  rawParallelPrescanBBox: [[0, 0], [0, 0]]
  rawParallelOverscanBBox: [[0, 0], [0, 0]]
  gain: 2.8
  readNoise: 15.0
  saturation: 30000
  linearityType: PROPORTIONAL
  linearityThreshold: 0
  linearityMax: 30000
  linearityCoeffs: [0.0, 1.0]
  hdu: 0
  ixy: [0, 0]
  flipXY: [false, false]

CCD: &CCD
  detectorType: 0
  physicalType: SCIENCE
  refpos: [1023.5, 1023.5]
  offset: [0.0, 0.0, 0.0]
  bbox: [[0, 0], [2048, 2048]]
  pixelSize: [0.024, 0.024]          # mm
  transposeDetector: false
  pitch: 0.0
  yaw: 0.0
  roll: 0.0
  amplifiers:
    A00:
      <<: *AMP

CCDs:
  SITE2K: &SITE2K
    <<: *CCD
    id: 0
    serial: "Tek2K_3"
```

**Note:** Overscan region dimensions are approximate. Will verify against real FITS headers and adjust.

### Instrument Class (_instrument.py)

**Note:** The raw FITS header `INSTRUME="cfccd"` (Cassegrain Focus CCD) differs from the LSST instrument name `"ctio0m9"`. The translator's `supported_instrument = "cfccd"` bridges this mapping.

```python
from __future__ import annotations

import os

from lsst.obs.base import DefineVisitsTask, Instrument, VisitSystem, yamlCamera
from lsst.utils import getPackageDir
from lsst.utils.introspection import get_full_type_name

from .ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS
from .translator import Ctio0m9Translator

class Ctio0m9(Instrument):
    """Instrument class for the CTIO/SMARTS 0.9m telescope."""

    name = "ctio0m9"
    policyName = "ctio0m9"
    obsDataPackage = None  # No curated calibrations package (Decision D4)
    filterDefinitions = CTIO0M9_FILTER_DEFINITIONS
    translatorClass = Ctio0m9Translator

    def __init__(self, collection_prefix=None):
        super().__init__(collection_prefix=collection_prefix)

    def getCamera(self):
        path = os.path.join(getPackageDir("obs_ctio0m9"), "camera", "ctio0m9.yaml")
        return yamlCamera.makeCamera(path)

    @classmethod
    def getName(cls):
        return "ctio0m9"

    def getRawFormatter(self, dataId):
        from .rawFormatter import Ctio0m9RawFormatter
        return Ctio0m9RawFormatter

    @classmethod
    def getDefineVisitsTask(cls):
        return DefineVisitsTask

    def register(self, registry, update=False):
        camera = self.getCamera()
        obsMax = 2**31
        with registry.transaction():
            registry.syncDimensionData(
                "instrument",
                {
                    "name": self.getName(),
                    "class_name": get_full_type_name(type(self)),
                    "detector_max": len(camera),
                    "visit_max": obsMax,
                    "exposure_max": obsMax,
                    "visit_system": VisitSystem.ONE_TO_ONE.value,
                },
                update=update,
            )
            for detector in camera:
                registry.syncDimensionData(
                    "detector",
                    {
                        "instrument": self.getName(),
                        "id": detector.getId(),
                        "full_name": detector.getName(),
                        "name_in_raft": detector.getName(),
                        "raft": "R00",
                        "purpose": str(detector.getPhysicalType()),
                    },
                    update=update,
                )
            self._registerFilters(registry, update=update)
```

### Translator (translator.py)

Port key translations from legacy `obs_ctio0m9/ingest.py`:

```python
from astro_metadata_translator import SubaruTranslator  # Base class pattern
from astro_metadata_translator.translators.helpers import (
    tracking_from_degree_headers,
)

class Ctio0m9Translator(FitsTranslator):
    """Metadata translator for CTIO 0.9m with Tek2K CCD."""

    name = "ctio0m9"
    supported_instrument = "cfccd"

    _const_map = {
        "instrument": "ctio0m9",
        "detector_name": "SITE2K",
        "detector_num": 0,
    }

    _trivial_map = {
        "exposure_time": "EXPTIME",
        "object": "OBJECT",
    }

    def to_datetime_begin(self):
        """Parse DATE-OBS with sanitization for non-ISO8601 values."""
        value = self._header.get("DATE-OBS")
        # Handle various date formats found in CTIO data
        # Legacy ingest.py had extensive date sanitization
        ...

    def to_exposure_id(self):
        """Generate unique exposure ID from MJD.

        Algorithm (from legacy obs_ctio0m9):
        - Get MJD from DATE-OBS
        - Subtract MJD of 2010-01-01 (55197.0) as epoch
        - Multiply by 100000 to get integer with sub-day resolution
        - Result fits in 31-bit signed int for ~58 years from epoch
        """
        mjd = self.to_datetime_begin().mjd
        epoch_mjd = 55197.0  # 2010-01-01
        return int((mjd - epoch_mjd) * 100000)

    def to_physical_filter(self):
        """Combine FILTER1 and FILTER2 for dual filter wheel.

        Examples:
        - FILTER1="V", FILTER2="OPEN" → "V"
        - FILTER1="V", FILTER2="ND" → "ND+V" (sorted)
        - FILTER1="OPEN", FILTER2="OPEN" → "OPEN"
        - FILTER1="B", FILTER2="NONE" → "B"
        """
        f1 = self._header.get("FILTER1", "OPEN")
        f2 = self._header.get("FILTER2", "OPEN")
        # Concatenate non-OPEN filters, sort for consistency
        filters = sorted([f for f in [f1, f2] if f not in ("OPEN", "NONE", "")])
        return "+".join(filters) if filters else "OPEN"

    def to_observation_type(self):
        """Map IMAGETYP to standard observation types."""
        imgtype = self._header.get("IMAGETYP", "").lower()
        mapping = {
            "object": "science",
            "flat": "flat",
            "bias": "bias",
            "dark": "dark",
            "focus": "focus",
        }
        return mapping.get(imgtype, "science")

    def to_boresight_airmass(self):
        return self._header.get("AIRMASS")

    def to_tracking_radec(self):
        """Extract RA/DEC from headers. RA is in hours, DEC in degrees."""
        ra_hours = self._header.get("RA")
        dec_deg = self._header.get("DEC")
        # Convert RA hours to degrees
        ...
```

### Filter Definitions (ctio0m9Filters.py)

```python
from lsst.obs.base import FilterDefinition, FilterDefinitionCollection

CTIO0M9_FILTER_DEFINITIONS = FilterDefinitionCollection(
    # Johnson-Cousins
    FilterDefinition(physical_filter="U", band="u", lambdaEff=357.0, alias={"u"}),
    FilterDefinition(physical_filter="B", band="b", lambdaEff=420.2, alias={"b"}),
    FilterDefinition(physical_filter="V", band="v", lambdaEff=547.5, alias={"v"}),
    FilterDefinition(physical_filter="R", band="r", lambdaEff=640.0, alias={"r"}),
    FilterDefinition(physical_filter="I", band="i", lambdaEff=811.8, alias={"i"}),
    # OPEN filter (for calibrations)
    FilterDefinition(physical_filter="OPEN", band="white"),
)
```

### Raw Formatter (rawFormatter.py)

```python
from lsst.obs.base import FitsRawFormatterBase

class Ctio0m9RawFormatter(FitsRawFormatterBase):
    """FITS reader for CTIO 0.9m single-amp data."""

    translatorClass = Ctio0m9Translator
    filterDefinitions = CTIO0M9_FILTER_DEFINITIONS

    def getDetector(self, id):
        return self.getCamera()[id]

    def readImage(self):
        """Read single-extension FITS image."""
        return super().readImage()

    # Overscan extraction uses IRAF-format keywords if present
    # (DATASEC, BIASSEC, TRIMSEC), otherwise falls back to camera.yaml
```

### Pipelines

**DRP.yaml** — Copy from obs_nickel, adjust ISR config:

```yaml
description: CTIO 0.9m Data Release Pipeline
imports:
  - $DRP_PIPE_DIR/pipelines/DRP.yaml

tasks:
  isr:
    class: lsst.ip.isr.IsrTask
    config:
      doOverscan: true
      doLinearize: false
      doCrosstalk: false
```

**DIA.yaml** and **ForcedPhotRaDec.yaml** — Copy from obs_nickel with minimal changes.

## FITS Header Reference

Key headers from CTIO 0.9m data (legacy obs_ctio0m9):

| Header | Example | Notes |
|--------|---------|-------|
| INSTRUME | "cfccd" | Cassegrain Focus CCD |
| DETECTOR | "Tek2K_3" | CCD serial |
| IMAGETYP | "object" | Observation type |
| FILTER1 | "V" | Primary filter |
| FILTER2 | "OPEN" | Secondary filter |
| DATE-OBS | "2015-03-21T02:34:56" | May be non-ISO8601 |
| EXPTIME | 120.0 | Exposure time (seconds) |
| RA | "12:34:56.7" | Right ascension (hours) |
| DEC | "-45:23:12.3" | Declination (degrees) |
| AIRMASS | 1.234 | Airmass |
| DATASEC | "[11:2058,1:2048]" | IRAF-format data section |
| BIASSEC | "[2059:2098,1:2048]" | IRAF-format overscan |

**Known issues:**
- DATE-OBS may not be ISO8601 compliant (requires sanitization)
- Filter names may be inconsistent
- Some headers may be missing or unreliable
- Data sections specified in IRAF format (1-indexed, inclusive)

## Testing Strategy

### Unit Tests

1. Camera YAML loads correctly
2. Instrument registers in Butler
3. Filter definitions are valid
4. Translator handles various header formats

### Integration Tests

1. Download single frame from NOIRLab archive
2. Ingest raw data into test Butler
3. Verify header translation produces valid metadata
4. Run ISR and verify output

### Manual Validation

1. Visual inspection of processed images
2. Compare astrometry/photometry to catalog values
3. Test with multiple observation types (science, flat, bias)

## Out of Scope

- Dual/quad amplifier readout modes
- Curated calibrations package (obs_ctio0m9_data)
- Reference catalog ingestion (deferred to Phase 3B)
- small_tel_tools plugin (Ctio0m9Plugin) — Phase 3B
- Archive data fetcher — Phase 3B

## Dependencies

- lsst.obs.base
- lsst.afw
- lsst.ip.isr
- astro_metadata_translator

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Overscan region dimensions incorrect | Verify against real FITS headers, adjust camera.yaml |
| Header sanitization incomplete | Port all edge cases from legacy ingest.py |
| Archive data format changed since legacy package | Test with recent archive data |
| Single-amp data rare in archive | Query archive to confirm availability |

## Pre-Implementation Validation Checklist

Before implementing, verify these assumptions with real data:

### Archive Data Availability
- [ ] Query NOIRLab archive for CTIO 0.9m single-amp data
- [ ] Confirm telescope/instrument codes (e.g., `ct09m`, `cfccd`)
- [ ] Download 10+ sample FITS files spanning science/flat/bias types

### Camera Geometry Verification
- [ ] Extract DATASEC/BIASSEC from sample FITS headers
- [ ] Compare IRAF-format sections against camera.yaml dimensions
- [ ] Verify prescan (10 cols), data (2048×2048), overscan (40 cols) regions
- [ ] Adjust camera.yaml if dimensions differ

### Header Translation Validation
- [ ] Test DATE-OBS parsing on all samples (verify ISO8601 compliance or sanitization needed)
- [ ] Verify FILTER1+FILTER2 concatenation produces valid filter names
- [ ] Confirm RA/DEC format (sexagesimal vs decimal)
- [ ] Implement exposure_id algorithm (MJD-based, unique within 31 bits)

### ISR Configuration
- [ ] Confirm doLinearize=false is appropriate (no linearity characterization available)
- [ ] Confirm doCrosstalk=false is appropriate (single-amp, no crosstalk)
- [ ] Test overscan subtraction produces reasonable bias levels

## Success Criteria

1. `butler register-instrument` succeeds with ctio0m9
2. Raw CTIO 0.9m FITS files ingest without error
3. ISR produces reasonable output (overscan subtracted, correct dimensions)
4. Package structure passes LSST coding standards
5. Unit tests pass

## References

- [Legacy obs_ctio0m9](https://github.com/lsst/legacy-obs_ctio0m9) — Gen2 package, header translations
- [NOIRLab Tek2K Documentation](https://noirlab.edu/science/programs/ctio/instruments/Tek2K)
- [NOIRLab Archive API](https://astroarchive.noirlab.edu/api/docs/)
- [SMARTS 0.9m Filter List](http://www.astro.gsu.edu/~thenry/SMARTS/0.9m.filters.text)
