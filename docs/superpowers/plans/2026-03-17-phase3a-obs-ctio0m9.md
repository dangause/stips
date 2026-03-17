# obs_ctio0m9 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an LSST instrument package for the CTIO/SMARTS 0.9m telescope (single-amp mode only).

**Architecture:** Mirrors obs_nickel structure exactly. Single detector (SITE2K), single amplifier. Translator bridges FITS header `INSTRUME="cfccd"` to LSST instrument name `"ctio0m9"`.

**Tech Stack:** Python 3.12+, lsst.obs.base, astro_metadata_translator, YAML camera definition

**Spec:** `docs/superpowers/specs/2026-03-17-phase3a-obs-ctio0m9-design.md`

---

## File Structure

```
packages/obs_ctio0m9/
├── camera/
│   └── ctio0m9.yaml              # Camera geometry (2048×2048, single amp)
├── configs/
│   └── .gitkeep                  # Empty initially
├── pipelines/
│   ├── DRP.yaml                  # Data release pipeline
│   ├── DIA.yaml                  # Difference imaging
│   └── ForcedPhotRaDec.yaml      # Forced photometry
├── python/lsst/obs/ctio0m9/
│   ├── __init__.py               # Package exports
│   ├── _instrument.py            # Ctio0m9 Instrument class
│   ├── _version.py               # Version string
│   ├── ctio0m9Filters.py         # Filter definitions
│   ├── rawFormatter.py           # FITS reader
│   └── translator.py             # Header translations
├── tests/
│   └── test_instrument.py        # Unit tests
├── pyproject.toml                # Package metadata + entry points
└── ups/
    └── obs_ctio0m9.table         # EUPS dependencies
```

---

## Task 1: Package Scaffolding

Create the basic package structure with pyproject.toml, __init__.py, _version.py, and EUPS table.

**Files:**
- Create: `packages/obs_ctio0m9/pyproject.toml`
- Create: `packages/obs_ctio0m9/python/lsst/__init__.py`
- Create: `packages/obs_ctio0m9/python/lsst/obs/__init__.py`
- Create: `packages/obs_ctio0m9/python/lsst/obs/ctio0m9/__init__.py`
- Create: `packages/obs_ctio0m9/python/lsst/obs/ctio0m9/_version.py`
- Create: `packages/obs_ctio0m9/ups/obs_ctio0m9.table`
- Create: `packages/obs_ctio0m9/configs/.gitkeep`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p packages/obs_ctio0m9/{camera,configs,pipelines,tests}
mkdir -p packages/obs_ctio0m9/python/lsst/obs/ctio0m9
mkdir -p packages/obs_ctio0m9/ups
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "obs-ctio0m9"
version = "0.1.0"
description = "LSST obs package for the CTIO/SMARTS 0.9m telescope"
authors = [{ name = "Dan Gause" }]
requires-python = ">=3.12"
dependencies = [
    "astro_metadata_translator>=0.11.0",
    "astropy",
]
readme = "README.md"

[project.entry-points."astro_metadata_translator.translators"]
ctio0m9 = "lsst.obs.ctio0m9.translator:Ctio0m9Translator"

[tool.setuptools.packages.find]
where = ["python"]
```

- [ ] **Step 3: Create namespace __init__.py files**

`packages/obs_ctio0m9/python/lsst/__init__.py`:
```python
__path__ = __import__("pkgutil").extend_path(__path__, __name__)
```

`packages/obs_ctio0m9/python/lsst/obs/__init__.py`:
```python
__path__ = __import__("pkgutil").extend_path(__path__, __name__)
```

- [ ] **Step 4: Create package __init__.py**

`packages/obs_ctio0m9/python/lsst/obs/ctio0m9/__init__.py`:
```python
from ._version import __version__
from ._instrument import Ctio0m9

__all__ = ["Ctio0m9", "__version__"]
```

- [ ] **Step 5: Create _version.py**

`packages/obs_ctio0m9/python/lsst/obs/ctio0m9/_version.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 6: Create EUPS table**

`packages/obs_ctio0m9/ups/obs_ctio0m9.table`:
```
# Python Middleware
setupRequired(utils)
setupRequired(daf_butler)
setupRequired(pipe_base)
setupRequired(resources)
setupRequired(astro_metadata_translator)
setupRequired(pex_config)

# LSST C++
setupRequired(daf_base)
setupRequired(afw)
setupRequired(geom)
setupRequired(pex_exceptions)
setupOptional(log)

envPrepend(PYTHONPATH, ${PRODUCT_DIR}/python)
envPrepend(PATH, ${PRODUCT_DIR}/bin)
```

- [ ] **Step 7: Create .gitkeep for configs/**

```bash
touch packages/obs_ctio0m9/configs/.gitkeep
```

- [ ] **Step 8: Commit**

```bash
git add packages/obs_ctio0m9/
git commit -m "feat(obs_ctio0m9): add package scaffolding"
```

---

## Task 2: Camera Geometry

Create the camera YAML defining detector and amplifier geometry.

**Files:**
- Create: `packages/obs_ctio0m9/camera/ctio0m9.yaml`

- [ ] **Step 1: Create camera YAML**

`packages/obs_ctio0m9/camera/ctio0m9.yaml`:
```yaml
# Camera geometry for CTIO/SMARTS 0.9m with Tek2K CCD
# Single-amplifier readout mode only
#
# Detector: SITE2K (Tek2K_3)
# Pixels: 2048 x 2048 active, 24μm pitch
# Plate scale: 0.401"/px (16.0 arcsec/mm)
#
# Note: Overscan dimensions are approximate.
# Verify against real FITS headers (DATASEC, BIASSEC) and adjust.

name: ctio0m9

AMP: &AMP
  perAmpData: true
  dataExtent: [2098, 2048]           # 2048 active + ~50 overscan columns
  readCorner: LL
  rawBBox: [[0, 0], [2098, 2048]]
  rawDataBBox: [[10, 0], [2048, 2048]]         # Skip 10-col prescan
  rawSerialPrescanBBox: [[0, 0], [10, 2048]]   # 10-column prescan
  rawSerialOverscanBBox: [[2058, 0], [40, 2048]]  # 40-column overscan
  rawParallelPrescanBBox: [[0, 0], [0, 0]]     # No parallel prescan
  rawParallelOverscanBBox: [[0, 0], [0, 0]]    # No parallel overscan
  gain: 2.8                          # e-/ADU (average of quad-mode gains)
  readNoise: 15.0                    # ADU
  saturation: 30000                  # Conservative (digital max 65535)
  linearityType: PROPORTIONAL
  linearityThreshold: 0
  linearityMax: 30000
  linearityCoeffs: [0.0, 1.0]
  hdu: 0
  ixy: [0, 0]
  flipXY: [false, false]

CCD: &CCD
  detectorType: 0                    # SCIENCE
  physicalType: SCIENCE
  refpos: [1023.5, 1023.5]           # Center of 2048×2048 active area
  offset: [0.0, 0.0, 0.0]
  bbox: [[0, 0], [2048, 2048]]
  pixelSize: [0.024, 0.024]          # mm (24μm)
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
    name_in_raft: "S00"
```

- [ ] **Step 2: Commit**

```bash
git add packages/obs_ctio0m9/camera/
git commit -m "feat(obs_ctio0m9): add camera geometry YAML"
```

---

## Task 3: Filter Definitions

Create the filter definitions for Johnson-Cousins UBVRI.

**Files:**
- Create: `packages/obs_ctio0m9/python/lsst/obs/ctio0m9/ctio0m9Filters.py`

- [ ] **Step 1: Create filter definitions**

`packages/obs_ctio0m9/python/lsst/obs/ctio0m9/ctio0m9Filters.py`:
```python
"""Filter definitions for the CTIO/SMARTS 0.9m telescope."""

from lsst.obs.base import FilterDefinition, FilterDefinitionCollection

__all__ = ["CTIO0M9_FILTER_DEFINITIONS"]

CTIO0M9_FILTER_DEFINITIONS = FilterDefinitionCollection(
    # Johnson-Cousins broadband (with lambdaEff for photometry)
    FilterDefinition(physical_filter="U", band="u", lambdaEff=357.0, alias={"u"}),
    FilterDefinition(physical_filter="B", band="b", lambdaEff=420.2, alias={"b"}),
    FilterDefinition(physical_filter="V", band="v", lambdaEff=547.5, alias={"v"}),
    FilterDefinition(physical_filter="R", band="r", lambdaEff=640.0, alias={"r"}),
    FilterDefinition(physical_filter="I", band="i", lambdaEff=811.8, alias={"i"}),
    # Open/clear for calibrations
    FilterDefinition(physical_filter="OPEN", band=None, doc="Open filter wheel position"),
)
```

- [ ] **Step 2: Commit**

```bash
git add packages/obs_ctio0m9/python/lsst/obs/ctio0m9/ctio0m9Filters.py
git commit -m "feat(obs_ctio0m9): add filter definitions"
```

---

## Task 4: Translator

Create the metadata translator to parse CTIO 0.9m FITS headers.

**Files:**
- Create: `packages/obs_ctio0m9/python/lsst/obs/ctio0m9/translator.py`

- [ ] **Step 1: Create translator**

`packages/obs_ctio0m9/python/lsst/obs/ctio0m9/translator.py`:
```python
"""Metadata translator for the CTIO/SMARTS 0.9m telescope."""

from __future__ import annotations

__all__ = ("Ctio0m9Translator",)

import logging
import re
from typing import Any

import astropy.time
import astropy.units as u
from astro_metadata_translator.translator import cache_translation
from astro_metadata_translator.translators.fits import FitsTranslator
from astropy.coordinates import Angle, EarthLocation, SkyCoord

log = logging.getLogger(__name__)

# Epoch for exposure ID calculation (2010-01-01)
EPOCH_MJD = 55197.0


class Ctio0m9Translator(FitsTranslator):
    """Metadata translator for CTIO 0.9m with Tek2K CCD.

    The raw FITS header has INSTRUME="cfccd" (Cassegrain Focus CCD).
    This translator maps it to LSST instrument name "ctio0m9".
    """

    name = "ctio0m9"
    supported_instrument = "cfccd"

    _const_map = {
        "boresight_rotation_angle": Angle(0.0 * u.deg),
        "boresight_rotation_coord": "sky",
    }

    _trivial_map: dict[str, str | list[str] | tuple[Any, ...]] = {
        "exposure_time": ("EXPTIME", {"unit": u.s, "default": 0.0 * u.s}),
        "dark_time": ("EXPTIME", {"unit": u.s, "default": 0.0 * u.s}),
        "boresight_airmass": ("AIRMASS", {"default": float("nan")}),
        "object": ("OBJECT", {"default": "UNKNOWN"}),
        "telescope": ("TELESCOP", {"default": "CTIO 0.9m"}),
    }

    @classmethod
    def can_translate(cls, header, filename=None):
        """Check if this translator can handle the given header."""
        instrume = header.get("INSTRUME", "").strip().lower()
        return instrume == "cfccd"

    @cache_translation
    def to_instrument(self) -> str:
        """Return the LSST instrument name."""
        return "ctio0m9"

    @cache_translation
    def to_datetime_begin(self):
        """Parse DATE-OBS with sanitization for non-ISO8601 values.

        CTIO 0.9m data may have non-compliant DATE-OBS formats.
        This method handles various formats found in the archive.
        """
        value = self._header.get("DATE-OBS")
        if value is None:
            raise ValueError("DATE-OBS header is missing")

        # Try standard ISO8601 first
        try:
            return astropy.time.Time(value, format="isot", scale="utc")
        except ValueError:
            pass

        # Try other common formats
        # Format: YYYY-MM-DDTHH:MM:SS.sss (standard)
        # Format: YYYY/MM/DD (legacy)
        # Format: DD/MM/YY (very old)
        try:
            # Handle YYYY/MM/DD format
            if "/" in value and "T" not in value:
                parts = value.split("/")
                if len(parts) == 3:
                    if len(parts[0]) == 4:  # YYYY/MM/DD
                        iso_date = f"{parts[0]}-{parts[1]}-{parts[2]}T00:00:00"
                    else:  # DD/MM/YY
                        year = int(parts[2])
                        if year < 50:
                            year += 2000
                        else:
                            year += 1900
                        iso_date = f"{year}-{parts[1]}-{parts[0]}T00:00:00"
                    return astropy.time.Time(iso_date, format="isot", scale="utc")
        except (ValueError, IndexError):
            pass

        raise ValueError(f"Cannot parse DATE-OBS value: {value!r}")

    @cache_translation
    def to_datetime_end(self):
        """Calculate end time from begin + EXPTIME."""
        begin = self.to_datetime_begin()
        exptime = float(self._header.get("EXPTIME", 0.0) or 0.0)
        if exptime > 0:
            return begin + astropy.time.TimeDelta(exptime, format="sec", scale="tai")
        return begin

    @cache_translation
    def to_day_obs(self) -> int:
        """Observing day as YYYYMMDD (UTC)."""
        return int(self.to_datetime_end().datetime.strftime("%Y%m%d"))

    @cache_translation
    def to_exposure_id(self) -> int:
        """Generate unique exposure ID from MJD.

        Algorithm (from legacy obs_ctio0m9):
        - Get MJD from DATE-OBS
        - Subtract MJD of 2010-01-01 (55197.0) as epoch
        - Multiply by 100000 to get integer with sub-day resolution
        - Result fits in 31-bit signed int for ~58 years from epoch
        """
        mjd = self.to_datetime_begin().mjd
        exposure_id = int((mjd - EPOCH_MJD) * 100000)
        if exposure_id >= 2**31:
            raise ValueError(f"exposure_id {exposure_id} is out of 31-bit range")
        return exposure_id

    @cache_translation
    def to_visit_id(self) -> int:
        """Visit ID equals exposure ID (one-to-one)."""
        return self.to_exposure_id()

    @cache_translation
    def to_observation_id(self) -> str:
        """String ID that must be globally unique for the instrument."""
        return f"ctio0m9_{self.to_exposure_id()}"

    @cache_translation
    def to_physical_filter(self) -> str:
        """Combine FILTER1 and FILTER2 for dual filter wheel.

        Examples:
        - FILTER1="V", FILTER2="OPEN" → "V"
        - FILTER1="V", FILTER2="ND" → "ND+V" (sorted)
        - FILTER1="OPEN", FILTER2="OPEN" → "OPEN"
        - FILTER1="B", FILTER2="NONE" → "B"
        """
        f1 = str(self._header.get("FILTER1", "OPEN")).strip().upper()
        f2 = str(self._header.get("FILTER2", "OPEN")).strip().upper()

        # Normalize empty/open values
        open_values = {"OPEN", "NONE", "CLEAR", ""}
        filters = sorted([f for f in [f1, f2] if f not in open_values])

        return "+".join(filters) if filters else "OPEN"

    @cache_translation
    def to_observation_type(self) -> str:
        """Map IMAGETYP to standard observation types."""
        imgtype = str(self._header.get("IMAGETYP", "")).strip().lower()
        mapping = {
            "object": "science",
            "flat": "flat",
            "bias": "bias",
            "dark": "dark",
            "focus": "focus",
            "zero": "bias",
            "dome flat": "flat",
            "sky flat": "flat",
        }
        return mapping.get(imgtype, "science")

    @cache_translation
    def to_observation_reason(self) -> str:
        """Return the reason for the observation."""
        obs_type = self.to_observation_type()
        if obs_type in ("flat", "bias", "dark"):
            return "calibration"
        if obs_type == "focus":
            return "focus"
        return "science"

    @cache_translation
    def to_tracking_radec(self):
        """Extract RA/DEC from headers.

        RA is in sexagesimal hours (HH:MM:SS.ss), DEC in degrees (DD:MM:SS.s).
        """
        ra_str = self._header.get("RA")
        dec_str = self._header.get("DEC")

        if not ra_str or not dec_str:
            raise ValueError("RA/DEC headers are missing")

        # Parse sexagesimal coordinates
        ra_angle = Angle(ra_str, unit=u.hourangle)
        dec_angle = Angle(dec_str, unit=u.deg)

        # Get reference frame from RADECSYS/RADESYS
        ref_system = (
            self._header.get("RADECSYS")
            or self._header.get("RADESYS")
            or "ICRS"
        )

        return SkyCoord(ra_angle, dec_angle, frame=ref_system.lower())

    @cache_translation
    def to_location(self) -> EarthLocation:
        """Return CTIO location."""
        # CTIO coordinates: -30.1653, -70.8148, 2207m
        return EarthLocation.from_geodetic(
            lon=-70.8148 * u.deg,
            lat=-30.1653 * u.deg,
            height=2207 * u.m,
        )

    @cache_translation
    def to_detector_num(self) -> int:
        """Single detector, ID 0."""
        return 0

    @cache_translation
    def to_detector_name(self) -> str:
        """Detector name matches camera.yaml."""
        return "SITE2K"

    @cache_translation
    def to_detector_unique_name(self) -> str:
        return "SITE2K"

    @cache_translation
    def to_detector_serial(self) -> str:
        return self._header.get("DETECTOR", "Tek2K_3")

    @cache_translation
    def to_detector_group(self) -> str:
        return ""

    @cache_translation
    def to_detector_exposure_id(self) -> int:
        return self.to_exposure_id()

    @cache_translation
    def to_focus_z(self) -> u.Quantity:
        return 0.0 * u.m

    @cache_translation
    def to_altaz_begin(self):
        return None

    @cache_translation
    def to_pressure(self):
        return None

    @cache_translation
    def to_temperature(self) -> u.Quantity:
        """Detector temperature if available."""
        temp = self._header.get("CCDTEMP")
        if temp is not None:
            return (float(temp) + 273.15) * u.K
        return 0.0 * u.K
```

- [ ] **Step 2: Commit**

```bash
git add packages/obs_ctio0m9/python/lsst/obs/ctio0m9/translator.py
git commit -m "feat(obs_ctio0m9): add metadata translator"
```

---

## Task 5: Raw Formatter

Create the raw FITS formatter.

**Files:**
- Create: `packages/obs_ctio0m9/python/lsst/obs/ctio0m9/rawFormatter.py`

- [ ] **Step 1: Create raw formatter**

`packages/obs_ctio0m9/python/lsst/obs/ctio0m9/rawFormatter.py`:
```python
"""Raw data formatter for the CTIO/SMARTS 0.9m telescope."""

__all__ = ["Ctio0m9RawFormatter"]

from lsst.obs.base import FitsRawFormatterBase

from ._instrument import Ctio0m9
from .ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS
from .translator import Ctio0m9Translator


class Ctio0m9RawFormatter(FitsRawFormatterBase):
    """Raw data formatter for CTIO 0.9m single-amp data."""

    translatorClass = Ctio0m9Translator
    filterDefinitions = CTIO0M9_FILTER_DEFINITIONS

    def getDetector(self, id):
        return Ctio0m9().getCamera()[id]
```

- [ ] **Step 2: Commit**

```bash
git add packages/obs_ctio0m9/python/lsst/obs/ctio0m9/rawFormatter.py
git commit -m "feat(obs_ctio0m9): add raw formatter"
```

---

## Task 6: Instrument Class

Create the main Instrument class.

**Files:**
- Create: `packages/obs_ctio0m9/python/lsst/obs/ctio0m9/_instrument.py`

- [ ] **Step 1: Create instrument class**

`packages/obs_ctio0m9/python/lsst/obs/ctio0m9/_instrument.py`:
```python
"""Instrument class for the CTIO/SMARTS 0.9m telescope."""

from __future__ import annotations

__all__ = ["Ctio0m9"]

import os

from lsst.obs.base import DefineVisitsTask, Instrument, VisitSystem, yamlCamera
from lsst.utils import getPackageDir
from lsst.utils.introspection import get_full_type_name

from .ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS
from .translator import Ctio0m9Translator


class Ctio0m9(Instrument):
    """Instrument class for the CTIO/SMARTS 0.9m telescope with Tek2K CCD.

    This instrument supports single-amplifier readout mode only.
    The raw FITS header has INSTRUME="cfccd" (Cassegrain Focus CCD).
    """

    name = "ctio0m9"
    policyName = "ctio0m9"
    obsDataPackage = None  # No curated calibrations package
    filterDefinitions = CTIO0M9_FILTER_DEFINITIONS
    translatorClass = Ctio0m9Translator

    _camera = None  # Cache for parsed camera

    def __init__(self, collection_prefix: str | None = None):
        super().__init__(collection_prefix=collection_prefix)

    def getCamera(self):
        """Return the camera geometry from YAML."""
        path = os.path.join(getPackageDir("obs_ctio0m9"), "camera", "ctio0m9.yaml")
        return yamlCamera.makeCamera(path)

    @classmethod
    def getName(cls):
        """Return the instrument name."""
        return "ctio0m9"

    def getRawFormatter(self, dataId):
        """Return the raw formatter class."""
        from .rawFormatter import Ctio0m9RawFormatter
        return Ctio0m9RawFormatter

    def getDefineVisitsTask(self):
        """One exposure = one visit."""
        return DefineVisitsTask

    def register(self, registry, update: bool = False):
        """Register the instrument with a Butler registry."""
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
                    "visit_system": VisitSystem.ONE_TO_ONE.value,
                    "exposure_max": obsMax,
                },
                update=update,
            )

            # Single-CCD camera
            for det in camera:
                registry.syncDimensionData(
                    "detector",
                    {
                        "instrument": self.getName(),
                        "id": int(det.getId()),
                        "full_name": det.getName(),
                        "name_in_raft": "S00",
                        "raft": "R00",
                        "purpose": det.getType().name,
                    },
                    update=update,
                )

            self._registerFilters(registry, update=update)
```

- [ ] **Step 2: Update __init__.py to avoid circular import**

The __init__.py already imports _instrument, but rawFormatter imports _instrument.
This is safe because rawFormatter is only imported at runtime in getRawFormatter().

- [ ] **Step 3: Commit**

```bash
git add packages/obs_ctio0m9/python/lsst/obs/ctio0m9/_instrument.py
git commit -m "feat(obs_ctio0m9): add instrument class"
```

---

## Task 7: Unit Tests

Create unit tests for the instrument package.

**Files:**
- Create: `packages/obs_ctio0m9/tests/test_instrument.py`

- [ ] **Step 1: Create test file**

`packages/obs_ctio0m9/tests/test_instrument.py`:
```python
"""Unit tests for obs_ctio0m9 instrument package."""

import unittest

import astropy.time
import astropy.units as u
import lsst.utils.tests


class TestCtio0m9Filters(unittest.TestCase):
    """Test filter definitions."""

    def test_filter_collection_exists(self):
        """Filter collection should be importable."""
        from lsst.obs.ctio0m9.ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS
        self.assertIsNotNone(CTIO0M9_FILTER_DEFINITIONS)

    def test_filter_count(self):
        """Should have 6 filters defined."""
        from lsst.obs.ctio0m9.ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS
        self.assertEqual(len(CTIO0M9_FILTER_DEFINITIONS), 6)

    def test_broadband_filters(self):
        """Should have UBVRI broadband filters."""
        from lsst.obs.ctio0m9.ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS
        names = {f.physical_filter for f in CTIO0M9_FILTER_DEFINITIONS}
        self.assertIn("U", names)
        self.assertIn("B", names)
        self.assertIn("V", names)
        self.assertIn("R", names)
        self.assertIn("I", names)


class TestCtio0m9Translator(unittest.TestCase):
    """Test metadata translator."""

    def setUp(self):
        """Create a mock FITS header."""
        self.header = {
            "INSTRUME": "cfccd",
            "DETECTOR": "Tek2K_3",
            "DATE-OBS": "2020-06-15T03:45:30.5",
            "EXPTIME": 120.0,
            "FILTER1": "V",
            "FILTER2": "OPEN",
            "IMAGETYP": "object",
            "RA": "12:34:56.78",
            "DEC": "-45:23:12.3",
            "AIRMASS": 1.234,
            "OBJECT": "test_field",
        }

    def test_can_translate(self):
        """Translator should recognize cfccd instrument."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator
        self.assertTrue(Ctio0m9Translator.can_translate(self.header))

    def test_cannot_translate_other(self):
        """Translator should not recognize other instruments."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator
        other_header = {"INSTRUME": "other_camera"}
        self.assertFalse(Ctio0m9Translator.can_translate(other_header))

    def test_to_instrument(self):
        """Should return 'ctio0m9' as instrument name."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator
        translator = Ctio0m9Translator(self.header)
        self.assertEqual(translator.to_instrument(), "ctio0m9")

    def test_to_physical_filter_single(self):
        """Single filter should return filter name."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator
        translator = Ctio0m9Translator(self.header)
        self.assertEqual(translator.to_physical_filter(), "V")

    def test_to_physical_filter_dual(self):
        """Dual filters should be concatenated and sorted."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator
        header = dict(self.header)
        header["FILTER1"] = "V"
        header["FILTER2"] = "ND"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_physical_filter(), "ND+V")

    def test_to_physical_filter_both_open(self):
        """Both filters open should return 'OPEN'."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator
        header = dict(self.header)
        header["FILTER1"] = "OPEN"
        header["FILTER2"] = "OPEN"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_physical_filter(), "OPEN")

    def test_to_observation_type(self):
        """Should map IMAGETYP to observation type."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        # object -> science
        translator = Ctio0m9Translator(self.header)
        self.assertEqual(translator.to_observation_type(), "science")

        # flat -> flat
        header = dict(self.header)
        header["IMAGETYP"] = "flat"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_observation_type(), "flat")

        # bias -> bias
        header["IMAGETYP"] = "bias"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_observation_type(), "bias")

    def test_to_detector_name(self):
        """Should return SITE2K."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator
        translator = Ctio0m9Translator(self.header)
        self.assertEqual(translator.to_detector_name(), "SITE2K")

    def test_to_exposure_id_range(self):
        """Exposure ID should fit in 31 bits."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator
        translator = Ctio0m9Translator(self.header)
        exp_id = translator.to_exposure_id()
        self.assertLess(exp_id, 2**31)
        self.assertGreater(exp_id, 0)


class TestCtio0m9Camera(unittest.TestCase):
    """Test camera geometry loading."""

    def test_camera_loads(self):
        """Camera YAML should load without error."""
        from lsst.obs.ctio0m9 import Ctio0m9
        camera = Ctio0m9().getCamera()
        self.assertIsNotNone(camera)

    def test_single_detector(self):
        """Camera should have exactly one detector."""
        from lsst.obs.ctio0m9 import Ctio0m9
        camera = Ctio0m9().getCamera()
        self.assertEqual(len(camera), 1)

    def test_detector_name(self):
        """Detector should be named SITE2K."""
        from lsst.obs.ctio0m9 import Ctio0m9
        camera = Ctio0m9().getCamera()
        det = camera[0]
        self.assertEqual(det.getName(), "SITE2K")

    def test_detector_dimensions(self):
        """Active area should be 2048x2048."""
        from lsst.obs.ctio0m9 import Ctio0m9
        camera = Ctio0m9().getCamera()
        det = camera[0]
        bbox = det.getBBox()
        self.assertEqual(bbox.getWidth(), 2048)
        self.assertEqual(bbox.getHeight(), 2048)


class TestCtio0m9Instrument(unittest.TestCase):
    """Test instrument class."""

    def test_instrument_name(self):
        """Instrument name should be 'ctio0m9'."""
        from lsst.obs.ctio0m9 import Ctio0m9
        self.assertEqual(Ctio0m9.getName(), "ctio0m9")

    def test_no_obs_data_package(self):
        """Should have no curated calibrations package."""
        from lsst.obs.ctio0m9 import Ctio0m9
        self.assertIsNone(Ctio0m9.obsDataPackage)

    def test_get_raw_formatter(self):
        """Should return Ctio0m9RawFormatter."""
        from lsst.obs.ctio0m9 import Ctio0m9
        from lsst.obs.ctio0m9.rawFormatter import Ctio0m9RawFormatter
        inst = Ctio0m9()
        formatter = inst.getRawFormatter({})
        self.assertEqual(formatter, Ctio0m9RawFormatter)


class MemoryTester(lsst.utils.tests.MemoryTestCase):
    """Check for memory leaks."""
    pass


def setup_module(module):
    """Set up LSST test environment."""
    lsst.utils.tests.init()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Commit**

```bash
git add packages/obs_ctio0m9/tests/
git commit -m "test(obs_ctio0m9): add unit tests"
```

---

## Task 8: Pipelines

Create pipeline YAML files (copy from obs_nickel with adjustments).

**Files:**
- Create: `packages/obs_ctio0m9/pipelines/DRP.yaml`
- Create: `packages/obs_ctio0m9/pipelines/DIA.yaml`
- Create: `packages/obs_ctio0m9/pipelines/ForcedPhotRaDec.yaml`

- [ ] **Step 1: Create DRP.yaml**

`packages/obs_ctio0m9/pipelines/DRP.yaml`:
```yaml
description: CTIO 0.9m Data Release Pipeline
imports:
  - $DRP_PIPE_DIR/pipelines/DRP.yaml

tasks:
  isr:
    class: lsst.ip.isr.IsrTask
    config:
      # Single-amp, no need for crosstalk correction
      doCrosstalk: false
      # No linearity characterization available
      doLinearize: false
      # Enable overscan subtraction
      doOverscan: true
```

- [ ] **Step 2: Create DIA.yaml**

`packages/obs_ctio0m9/pipelines/DIA.yaml`:
```yaml
description: CTIO 0.9m Difference Imaging Pipeline
imports:
  - $AP_PIPE_DIR/pipelines/ApPipe.yaml
```

- [ ] **Step 3: Create ForcedPhotRaDec.yaml**

`packages/obs_ctio0m9/pipelines/ForcedPhotRaDec.yaml`:
```yaml
# NOTE: Requires LSST environment with PIPE_TASKS_DIR set.
# Will be expanded via 'pipetask build-workflow' when executed.
description: CTIO 0.9m Forced Photometry at RA/Dec
imports:
  - $PIPE_TASKS_DIR/pipelines/ForcedPhotCoadd.yaml

tasks:
  forcedPhotCoadd:
    class: lsst.pipe.tasks.forcedPhotCoadd.ForcedPhotCoaddTask
```

- [ ] **Step 4: Commit**

```bash
git add packages/obs_ctio0m9/pipelines/
git commit -m "feat(obs_ctio0m9): add pipeline definitions"
```

---

## Task 9: Integration Test

Run the tests and verify the package works.

**Files:**
- None (verification only)

- [ ] **Step 1: Install the package in development mode**

```bash
cd packages/obs_ctio0m9
pip install -e .
```

- [ ] **Step 2: Run unit tests**

```bash
cd packages/obs_ctio0m9
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 3: Verify camera loads in Python**

```python
from lsst.obs.ctio0m9 import Ctio0m9
camera = Ctio0m9().getCamera()
print(f"Camera has {len(camera)} detector(s)")
print(f"Detector name: {camera[0].getName()}")
print(f"Detector bbox: {camera[0].getBBox()}")
```

Expected output:
```
Camera has 1 detector(s)
Detector name: SITE2K
Detector bbox: Box2I(corner=Point2I(0, 0), dimensions=Extent2I(2048, 2048))
```

- [ ] **Step 4: Verify translator entry point is registered**

```bash
python -c "from astro_metadata_translator import MetadataTranslator; print([t.name for t in MetadataTranslator.all_translators() if 'ctio' in t.name.lower()])"
```

Expected: `['ctio0m9']`

- [ ] **Step 5: Final commit with README**

Create a minimal README:

`packages/obs_ctio0m9/README.md`:
```markdown
# obs_ctio0m9

LSST Science Pipelines instrument package for the CTIO/SMARTS 0.9m telescope.

## Features

- Single-amplifier readout mode (Tek2K CCD)
- Johnson-Cousins UBVRI filter support
- Dual filter wheel handling

## Installation

```bash
pip install -e .
```

Or with EUPS:

```bash
setup -r . obs_ctio0m9
```

## Usage

```python
from lsst.obs.ctio0m9 import Ctio0m9

# Register instrument with Butler
butler.registry.registerInstrument(Ctio0m9())
```
```

```bash
git add packages/obs_ctio0m9/README.md
git commit -m "docs(obs_ctio0m9): add README"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Package scaffolding | pyproject.toml, __init__.py, _version.py, ups table |
| 2 | Camera geometry | camera/ctio0m9.yaml |
| 3 | Filter definitions | ctio0m9Filters.py |
| 4 | Translator | translator.py |
| 5 | Raw formatter | rawFormatter.py |
| 6 | Instrument class | _instrument.py |
| 7 | Unit tests | tests/test_instrument.py |
| 8 | Pipelines | DRP.yaml, DIA.yaml, ForcedPhotRaDec.yaml |
| 9 | Integration test | Verification only |

Total: 9 tasks, ~20 files created
