# obs_smalltel Package — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `obs_smalltel` LSST instrument package with Nickel as the first instrument, extracting generic base classes from the existing `obs_nickel` package.

**Architecture:** Three base classes (`GenericSmallTelInstrument`, `ConfigurableTranslator`, `GenericRawFormatter`) load telescope configuration from YAML files. Per-telescope Python subclasses are thin stubs (~10-40 lines) that set class attributes and override only telescope-specific methods. Nickel's existing logic is refactored into this pattern as the first implementation.

**Tech Stack:** Python 3.12+, LSST Science Pipelines (`obs.base`, `afw`, `astro_metadata_translator`), astropy, PyYAML

**Spec:** `docs/superpowers/specs/2026-03-12-multi-instrument-abstraction-design.md`

**Note:** This is Phase 1 of the multi-instrument abstraction. Phase 2 (pipeline_tools refactor) will be a separate plan.

**Prerequisites:** The implementation worktree should be rebased on the latest `feature/conference-cleanup` branch before starting, since it contains files (`calibCombine.py`, `DifferentialPhot.yaml`, `NickelCpBias.yaml`, `NickelCpFlat.yaml`) not present in the older worktree base.

---

## File Structure

### New files to create

```
packages/obs_smalltel/
├── pyproject.toml                                    # Package metadata, entry points, package data
├── python/lsst/obs/smalltel/
│   │   (NO lsst/__init__.py or lsst/obs/__init__.py — LSST uses implicit namespace packages)
│   ├── __init__.py                                   # Package exports
│   ├── base_instrument.py                            # GenericSmallTelInstrument (~100 lines)
│   ├── base_translator.py                            # ConfigurableTranslator (~150 lines)
│   ├── base_formatter.py                             # GenericRawFormatter (~25 lines)
│   ├── nickel/
│   │   ├── __init__.py                               # Nickel instrument exports
│   │   ├── instrument.py                             # Nickel instrument (~15 lines)
│   │   ├── translator.py                             # Nickel translator (~180 lines, custom overrides)
│   │   └── formatter.py                              # Nickel formatter (~10 lines)
│   └── tasks/                                        # Shared pipeline tasks (moved from obs_nickel)
│       ├── __init__.py
│       ├── forcedPhotRaDec.py                        # (moved from obs_nickel)
│       ├── forcedPhotLightcurve.py                   # (moved)
│       ├── forcedPhotDiffimLightcurveBand.py         # (moved)
│       ├── diaLightcurvePlot.py                      # (moved)
│       ├── diaLightcurveCombinedPlot.py              # (moved)
│       ├── calibCombine.py                           # (moved from obs_nickel package root)
│       └── plotting.py                               # (moved from obs_nickel package root)
├── instruments/
│   └── nickel/
│       ├── instrument.yaml                           # Identity, location, visit system
│       ├── camera.yaml                               # Detector geometry (moved from obs_nickel)
│       ├── filters.yaml                              # Filter definitions
│       └── header_map.yaml                           # FITS keyword mappings
├── pipelines/                                        # Shared pipeline definitions (moved from obs_nickel)
│   ├── DRP.yaml
│   ├── DIA.yaml
│   ├── DifferentialPhot.yaml
│   ├── ForcedPhotRaDec.yaml
│   ├── ForcedPhot.yaml
│   ├── NickelCpBias.yaml                             # Nickel calibration (kept Nickel-prefixed)
│   ├── NickelCpFlat.yaml                             # Nickel calibration (kept Nickel-prefixed)
│   ├── ProcessCcd.yaml
│   ├── PostProcessing.yaml
│   └── (analysis pipelines)
├── configs/                                          # Pipeline config overrides
│   ├── common/                                       # Defaults for all small telescopes
│   └── nickel/                                       # Nickel-specific tuning (moved from obs_nickel)
└── tests/
    ├── test_yaml_configs.py                          # YAML loading/validation tests
    ├── test_base_instrument.py                       # GenericSmallTelInstrument tests
    ├── test_base_translator.py                       # ConfigurableTranslator tests
    ├── test_nickel_instrument.py                     # Nickel integration tests
    └── test_nickel_translator.py                     # Nickel translator tests
```

### Files moved from obs_nickel (unchanged or minimal edits)

| Source | Destination | Changes |
|--------|-------------|---------|
| `obs_nickel/camera/nickel.yaml` | `obs_smalltel/instruments/nickel/camera.yaml` | None |
| `obs_nickel/pipelines/*.yaml` | `obs_smalltel/pipelines/` | Update task import paths |
| `obs_nickel/configs/` | `obs_smalltel/configs/nickel/` | None |
| `obs_nickel/python/lsst/obs/nickel/tasks/` | `obs_smalltel/python/lsst/obs/smalltel/tasks/` | Update imports |
| `obs_nickel/python/lsst/obs/nickel/calibCombine.py` | `obs_smalltel/python/lsst/obs/smalltel/tasks/calibCombine.py` | Update imports |
| `obs_nickel/python/lsst/obs/nickel/plotting.py` | `obs_smalltel/python/lsst/obs/smalltel/tasks/plotting.py` | Update imports |

### Testing constraints

- **Pure unit tests** (no LSST stack): YAML parsing, header_map processing, filter map lookups, can_translate() logic
- **LSST-dependent tests** (require stack): Instrument registration, camera creation, filter definitions, full translator validation
- Tests that need LSST use `pytest.importorskip("lsst.obs.base")` to skip gracefully

---

## Chunk 1: Package Scaffold + YAML Configs

### Task 1: Create obs_smalltel package scaffold

**Files:**
- Create: `packages/obs_smalltel/pyproject.toml`
- Create: `packages/obs_smalltel/python/lsst/obs/smalltel/__init__.py`
- Create: `packages/obs_smalltel/python/lsst/obs/smalltel/nickel/__init__.py`

**IMPORTANT:** Do NOT create `python/lsst/__init__.py` or `python/lsst/obs/__init__.py`. LSST uses PEP 420 implicit namespace packages. Creating these files would shadow all other `lsst.*` packages in the environment.

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p packages/obs_smalltel/python/lsst/obs/smalltel/nickel
mkdir -p packages/obs_smalltel/python/lsst/obs/smalltel/tasks
mkdir -p packages/obs_smalltel/instruments/nickel
mkdir -p packages/obs_smalltel/pipelines
mkdir -p packages/obs_smalltel/configs/common
mkdir -p packages/obs_smalltel/configs/nickel
mkdir -p packages/obs_smalltel/tests
```

- [ ] **Step 2: Create pyproject.toml**

```toml
# packages/obs_smalltel/pyproject.toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "obs-smalltel"
version = "0.1.0"
description = "LSST obs package for single-CCD small telescopes"
authors = [{ name = "Dan Gause" }]
requires-python = ">=3.12"
dependencies = [
    "astro_metadata_translator>=0.11.0",
    "astropy",
    "pyyaml>=6.0",
]
readme = "README.md"

[project.entry-points."astro_metadata_translator.translators"]
Nickel = "lsst.obs.smalltel.nickel.translator:NickelTranslator"

[tool.setuptools.packages.find]
where = ["python"]

# Include non-Python data files needed at runtime
[tool.setuptools.package-data]
"*" = ["instruments/**/*.yaml", "pipelines/*.yaml", "configs/**/*.py", "camera/*.yaml"]
```

- [ ] **Step 3: Create __init__.py files**

No `__init__.py` at `python/lsst/` or `python/lsst/obs/` — LSST uses implicit namespace packages (PEP 420). Only create `__init__.py` at the actual package level:

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/__init__.py
from .nickel.instrument import Nickel
from .nickel.translator import NickelTranslator

__all__ = [
    "Nickel",
    "NickelTranslator",
]

# Import tasks submodule for LSST doImport discovery
try:
    from . import tasks  # noqa: F401
    __all__.append("tasks")
except ImportError:
    pass
```

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/nickel/__init__.py
from .instrument import Nickel
from .translator import NickelTranslator

__all__ = ["Nickel", "NickelTranslator"]
```

- [ ] **Step 4: Create placeholder base class files**

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/base_instrument.py
"""Generic instrument base class for single-CCD small telescopes."""
# Implementation in Task 6
```

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/base_translator.py
"""Configurable FITS translator driven by YAML keyword mappings."""
# Implementation in Task 10
```

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/base_formatter.py
"""Generic raw formatter for single-CCD small telescopes."""
# Implementation in Task 14
```

- [ ] **Step 5: Verify package installs**

```bash
cd packages/obs_smalltel && pip install -e . --no-deps 2>&1 | tail -3
```

Expected: Installation succeeds (imports will fail until LSST stack is active, but pip install should work).

- [ ] **Step 6: Commit**

```bash
git add packages/obs_smalltel/
git commit -m "feat(obs_smalltel): create package scaffold with directory structure"
```

---

### Task 2: Create Nickel instrument.yaml

**Files:**
- Create: `packages/obs_smalltel/instruments/nickel/instrument.yaml`

- [ ] **Step 1: Write test for instrument.yaml loading**

```python
# packages/obs_smalltel/tests/test_yaml_configs.py
"""Tests for YAML configuration loading (no LSST stack required)."""
from pathlib import Path

import pytest
import yaml

INSTRUMENTS_DIR = Path(__file__).parent.parent / "instruments"


class TestNickelInstrumentYaml:
    @pytest.fixture
    def config(self):
        with open(INSTRUMENTS_DIR / "nickel" / "instrument.yaml") as f:
            return yaml.safe_load(f)

    def test_required_fields(self, config):
        assert config["name"] == "Nickel"
        assert "location" in config
        assert "visit_system" in config

    def test_location_fields(self, config):
        loc = config["location"]
        assert "latitude" in loc
        assert "longitude" in loc
        assert "elevation" in loc
        assert -90 <= loc["latitude"] <= 90
        assert -180 <= loc["longitude"] <= 180
        assert loc["elevation"] > 0

    def test_day_obs_offset(self, config):
        assert config["day_obs_offset"] in (0, 1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest packages/obs_smalltel/tests/test_yaml_configs.py::TestNickelInstrumentYaml -v
```

Expected: FAIL — `FileNotFoundError` (instrument.yaml doesn't exist yet)

- [ ] **Step 3: Create instrument.yaml**

```yaml
# packages/obs_smalltel/instruments/nickel/instrument.yaml
name: Nickel
policyName: Nickel
obsDataPackage: obs_nickel_data
visit_system: ONE_TO_ONE
detector_count: 1

location:
  name: "Lick Observatory"
  latitude: 37.3414
  longitude: -121.6429
  elevation: 1283.0

# Western hemisphere: observing night crosses into next UT day
day_obs_offset: 1
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest packages/obs_smalltel/tests/test_yaml_configs.py::TestNickelInstrumentYaml -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/instruments/nickel/instrument.yaml packages/obs_smalltel/tests/test_yaml_configs.py
git commit -m "feat(obs_smalltel): add Nickel instrument.yaml with tests"
```

---

### Task 3: Copy camera.yaml from obs_nickel

**Files:**
- Create: `packages/obs_smalltel/instruments/nickel/camera.yaml` (copied from `packages/obs_nickel/camera/nickel.yaml`)

- [ ] **Step 1: Add camera.yaml test to test_yaml_configs.py**

```python
# Add to packages/obs_smalltel/tests/test_yaml_configs.py

class TestNickelCameraYaml:
    @pytest.fixture
    def config(self):
        with open(INSTRUMENTS_DIR / "nickel" / "camera.yaml") as f:
            return yaml.safe_load(f)

    def test_has_ccds(self, config):
        assert "CCDs" in config
        assert len(config["CCDs"]) >= 1

    def test_has_plate_scale(self, config):
        assert "plateScale" in config
        assert config["plateScale"] > 0

    def test_single_detector(self, config):
        """Small telescopes have a single CCD."""
        assert len(config["CCDs"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest packages/obs_smalltel/tests/test_yaml_configs.py::TestNickelCameraYaml -v
```

Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: Copy camera.yaml**

```bash
cp packages/obs_nickel/camera/nickel.yaml packages/obs_smalltel/instruments/nickel/camera.yaml
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest packages/obs_smalltel/tests/test_yaml_configs.py::TestNickelCameraYaml -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/instruments/nickel/camera.yaml packages/obs_smalltel/tests/test_yaml_configs.py
git commit -m "feat(obs_smalltel): add Nickel camera.yaml (from obs_nickel)"
```

---

### Task 4: Create Nickel filters.yaml

**Files:**
- Create: `packages/obs_smalltel/instruments/nickel/filters.yaml`

- [ ] **Step 1: Add filters.yaml test**

```python
# Add to packages/obs_smalltel/tests/test_yaml_configs.py

class TestNickelFiltersYaml:
    @pytest.fixture
    def config(self):
        with open(INSTRUMENTS_DIR / "nickel" / "filters.yaml") as f:
            return yaml.safe_load(f)

    def test_has_filters(self, config):
        assert "filters" in config
        assert len(config["filters"]) >= 4  # at minimum B, V, R, I

    def test_filter_fields(self, config):
        for f in config["filters"]:
            assert "name" in f, f"Filter missing 'name': {f}"
            assert "band" in f or f.get("band") is None

    def test_standard_bvri_present(self, config):
        names = {f["name"] for f in config["filters"]}
        assert {"B", "V", "R", "I"}.issubset(names)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest packages/obs_smalltel/tests/test_yaml_configs.py::TestNickelFiltersYaml -v
```

Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: Create filters.yaml**

```yaml
# packages/obs_smalltel/instruments/nickel/filters.yaml
#
# Filter definitions for the Nickel 1-meter telescope.
# Each entry becomes an lsst.obs.base.FilterDefinition.
filters:
  - name: B
    band: b
    doc: "Johnson/Bessell B"
  - name: V
    band: v
    doc: "Johnson/Bessell V"
  - name: R
    band: r
    doc: "Cousins R"
  - name: I
    band: i
    doc: "Cousins I"
  - name: clear
    band: null
    doc: "Unfiltered / open wheel"
  - name: gp
    band: gp
    doc: "Sloan g-prime"
  - name: rp
    band: rp
    doc: "Sloan r-prime"
  - name: Halpha
    band: halpha
    doc: "H-alpha 6563A narrowband"
  - name: OIII
    band: oiii
    doc: "[OIII] 5007A narrowband"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest packages/obs_smalltel/tests/test_yaml_configs.py::TestNickelFiltersYaml -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/instruments/nickel/filters.yaml packages/obs_smalltel/tests/test_yaml_configs.py
git commit -m "feat(obs_smalltel): add Nickel filters.yaml with 9 filter definitions"
```

---

### Task 5: Create Nickel header_map.yaml

**Files:**
- Create: `packages/obs_smalltel/instruments/nickel/header_map.yaml`

- [ ] **Step 1: Add header_map.yaml test**

```python
# Add to packages/obs_smalltel/tests/test_yaml_configs.py

class TestNickelHeaderMapYaml:
    @pytest.fixture
    def config(self):
        with open(INSTRUMENTS_DIR / "nickel" / "header_map.yaml") as f:
            return yaml.safe_load(f)

    def test_has_required_sections(self, config):
        assert "const_map" in config
        assert "trivial_map" in config

    def test_const_map_has_rotation(self, config):
        cm = config["const_map"]
        assert "boresight_rotation_angle" in cm
        assert "boresight_rotation_coord" in cm

    def test_trivial_map_has_exposure_time(self, config):
        tm = config["trivial_map"]
        assert "exposure_time" in tm

    def test_filter_name_map(self, config):
        assert "filter_name_map" in config
        fnm = config["filter_name_map"]
        # OPEN and C should map to clear
        assert fnm.get("OPEN") == "clear"
        assert fnm.get("C") == "clear"

    def test_observation_type_map(self, config):
        assert "observation_type_map" in config
        otm = config["observation_type_map"]
        assert otm.get("object") == "science"
        assert otm.get("bias") == "bias"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest packages/obs_smalltel/tests/test_yaml_configs.py::TestNickelHeaderMapYaml -v
```

Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: Create header_map.yaml**

```yaml
# packages/obs_smalltel/instruments/nickel/header_map.yaml
#
# FITS header keyword mappings for the Nickel 1-meter telescope.
# Used by ConfigurableTranslator to build _const_map and _trivial_map.

const_map:
  boresight_rotation_angle: 0.0  # degrees
  boresight_rotation_coord: sky

trivial_map:
  exposure_time:
    key: EXPTIME
    unit: s
    default: 0.0
  dark_time:
    key: EXPTIME
    unit: s
    default: 0.0
  boresight_airmass:
    key: AIRMASS
    default: NaN
  object:
    key: OBJECT
    default: UNKNOWN
  telescope:
    key: TELESCOP
    default: "Nickel 1m"
  science_program:
    key: PROGRAM
    default: unknown
  relative_humidity:
    key: HUMIDITY
    default: 0.0

# Filter name normalization (raw FITS FILTNAM value -> canonical name)
filter_name_map:
  B: B
  V: V
  R: R
  I: I
  OPEN: clear
  C: clear
  CLEAR: clear
  GP: gp
  "G'": gp
  RP: rp
  "R'": rp
  HALPHA: Halpha
  OIII: OIII

# Observation type classification (raw FITS OBSTYPE -> standard type)
# Note: Nickel's to_observation_type() uses multi-keyword logic (OBSTYPE + OBJECT)
# and overrides the simple lookup. This map serves as a fallback reference.
observation_type_map:
  object: science
  bias: bias
  dark: dark
  dflat: flat
  flat: flat
  focus: focus
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest packages/obs_smalltel/tests/test_yaml_configs.py::TestNickelHeaderMapYaml -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/instruments/nickel/header_map.yaml packages/obs_smalltel/tests/test_yaml_configs.py
git commit -m "feat(obs_smalltel): add Nickel header_map.yaml with keyword mappings"
```

---

## Chunk 2: GenericSmallTelInstrument Base Class

### Task 6: Implement YAML config loading helpers

**Files:**
- Modify: `packages/obs_smalltel/python/lsst/obs/smalltel/base_instrument.py`
- Create: `packages/obs_smalltel/tests/test_base_instrument.py`

- [ ] **Step 1: Write failing test for _config_path and _load_yaml**

```python
# packages/obs_smalltel/tests/test_base_instrument.py
"""Tests for GenericSmallTelInstrument base class."""
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


class TestConfigLoading:
    """Test YAML config loading helpers (no LSST stack needed)."""

    def test_config_path_resolves_to_instruments_dir(self):
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument

        class FakeInstrument(GenericSmallTelInstrument):
            instrument_name = "Fake"
            config_dir = "nickel"

            def getRawFormatter(self, dataId):
                return None

        inst = FakeInstrument.__new__(FakeInstrument)
        path = inst._config_path("instrument.yaml")
        assert path.exists(), f"Expected {path} to exist"
        assert path.name == "instrument.yaml"
        assert "instruments/nickel" in str(path)

    def test_load_yaml_returns_dict(self):
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument

        class FakeInstrument(GenericSmallTelInstrument):
            instrument_name = "Fake"
            config_dir = "nickel"

            def getRawFormatter(self, dataId):
                return None

        inst = FakeInstrument.__new__(FakeInstrument)
        data = inst._load_yaml("instrument.yaml")
        assert isinstance(data, dict)
        assert data["name"] == "Nickel"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest packages/obs_smalltel/tests/test_base_instrument.py::TestConfigLoading -v
```

Expected: FAIL — `GenericSmallTelInstrument` has no real implementation

- [ ] **Step 3: Implement _config_path and _load_yaml**

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/base_instrument.py
"""Generic instrument base class for single-CCD small telescopes."""
from __future__ import annotations

__all__ = ("GenericSmallTelInstrument",)

from pathlib import Path

import yaml


class GenericSmallTelInstrument:
    """Base instrument for single-CCD small telescopes.

    Subclasses set ``instrument_name`` and ``config_dir``.
    Everything else loads from YAML in instruments/{config_dir}/.

    This is a mixin/base that will inherit from lsst.obs.base.Instrument
    when the full class is assembled (Task 7). The YAML loading helpers
    are defined here for testability without the LSST stack.
    """

    instrument_name: str  # e.g., "Nickel"
    config_dir: str  # subdirectory under instruments/

    @classmethod
    def _package_root(cls) -> Path:
        """Resolve the obs_smalltel package root directory.

        Uses LSST's getPackageDir (EUPS) as primary resolution method,
        falling back to Path(__file__) traversal for editable pip installs.
        """
        try:
            from lsst.utils import getPackageDir
            return Path(getPackageDir("obs_smalltel"))
        except (ImportError, LookupError):
            return Path(__file__).parent.parent.parent.parent.parent

    def _config_path(self, filename: str) -> Path:
        """Resolve path to a YAML config file in instruments/{config_dir}/."""
        return self._package_root() / "instruments" / self.config_dir / filename

    def _load_yaml(self, filename: str) -> dict:
        """Load and parse a YAML config file."""
        with open(self._config_path(filename)) as f:
            return yaml.safe_load(f)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest packages/obs_smalltel/tests/test_base_instrument.py::TestConfigLoading -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/python/lsst/obs/smalltel/base_instrument.py packages/obs_smalltel/tests/test_base_instrument.py
git commit -m "feat(obs_smalltel): add YAML config loading helpers to base instrument"
```

---

### Task 7: Implement full GenericSmallTelInstrument with LSST integration

**Files:**
- Modify: `packages/obs_smalltel/python/lsst/obs/smalltel/base_instrument.py`
- Modify: `packages/obs_smalltel/tests/test_base_instrument.py`

- [ ] **Step 1: Write tests for LSST-dependent methods**

```python
# Add to packages/obs_smalltel/tests/test_base_instrument.py

obs_base = pytest.importorskip("lsst.obs.base")


class TestGenericSmallTelInstrumentLSST:
    """Tests that require the LSST stack."""

    def _make_nickel_subclass(self):
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument

        class TestNickel(GenericSmallTelInstrument):
            instrument_name = "Nickel"
            config_dir = "nickel"

            def getRawFormatter(self, dataId):
                return None

        return TestNickel

    def test_get_name(self):
        cls = self._make_nickel_subclass()
        assert cls.getName() == "Nickel"

    def test_get_camera_returns_camera(self):
        cls = self._make_nickel_subclass()
        inst = cls()
        camera = inst.getCamera()
        assert len(camera) == 1  # single CCD

    def test_filter_definitions_loaded_from_yaml(self):
        cls = self._make_nickel_subclass()
        inst = cls()
        filt_defs = inst.filterDefinitions
        names = {f.physical_filter for f in filt_defs}
        assert {"B", "V", "R", "I", "clear"}.issubset(names)

    def test_is_lsst_instrument(self):
        cls = self._make_nickel_subclass()
        assert issubclass(cls, obs_base.Instrument)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest packages/obs_smalltel/tests/test_base_instrument.py::TestGenericSmallTelInstrumentLSST -v
```

Expected: FAIL — class doesn't inherit from `Instrument` yet

- [ ] **Step 3: Implement full GenericSmallTelInstrument**

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/base_instrument.py
"""Generic instrument base class for single-CCD small telescopes."""
from __future__ import annotations

__all__ = ("GenericSmallTelInstrument",)

from pathlib import Path

import yaml
from lsst.obs.base import (
    DefineVisitsTask,
    FilterDefinition,
    FilterDefinitionCollection,
    VisitSystem,
    yamlCamera,
)
from lsst.obs.base._instrument import Instrument
from lsst.utils.introspection import get_full_type_name


class GenericSmallTelInstrument(Instrument):
    """Base instrument for single-CCD small telescopes.

    Subclasses set ``instrument_name`` and ``config_dir``.
    Everything else loads from YAML in instruments/{config_dir}/.
    """

    instrument_name: str  # e.g., "Nickel"
    config_dir: str  # subdirectory under instruments/

    def __init__(self, collection_prefix: str | None = None):
        super().__init__(collection_prefix=collection_prefix)

    @classmethod
    def getName(cls) -> str:
        return cls.instrument_name

    def getCamera(self):
        camera_yaml = self._config_path("camera.yaml")
        return yamlCamera.makeCamera(camera_yaml)

    @property
    def filterDefinitions(self):
        """Load filter definitions from filters.yaml. Cached after first access."""
        if not hasattr(self, "_filter_defs"):
            filters_config = self._load_yaml("filters.yaml")
            self._filter_defs = FilterDefinitionCollection(
                *[
                    FilterDefinition(
                        f["name"],
                        band=f.get("band"),
                        doc=f.get("doc", ""),
                    )
                    for f in filters_config["filters"]
                ]
            )
        return self._filter_defs

    def register(self, registry, update: bool = False):
        instrument_config = self._load_yaml("instrument.yaml")
        camera = self.getCamera()
        with registry.transaction():
            registry.syncDimensionData(
                "instrument",
                {
                    "name": self.getName(),
                    "class_name": get_full_type_name(type(self)),
                    "detector_max": len(camera),
                    "visit_max": 2**31,
                    "visit_system": VisitSystem[
                        instrument_config.get("visit_system", "ONE_TO_ONE")
                    ].value,
                    "exposure_max": 2**31,
                },
                update=update,
            )
            for det in camera:
                registry.syncDimensionData(
                    "detector",
                    {
                        "instrument": self.getName(),
                        "id": int(det.getId()),
                        "full_name": det.getName(),
                        "name_in_raft": "S00",  # stable label for single-CCD
                        "raft": "R00",
                        "purpose": det.getType().name,
                    },
                    update=update,
                )
            self._registerFilters(registry, update=update)

    def getRawFormatter(self, dataId):
        raise NotImplementedError(
            f"{type(self).__name__} must implement getRawFormatter()"
        )

    def getDefineVisitsTask(self):
        return DefineVisitsTask

    @property
    def policyName(self):
        config = self._load_yaml("instrument.yaml")
        return config.get("policyName", self.instrument_name)

    @property
    def obsDataPackage(self):
        config = self._load_yaml("instrument.yaml")
        return config.get("obsDataPackage")

    def _config_path(self, filename: str) -> Path:
        """Resolve path to a YAML config in instruments/{config_dir}/."""
        return (
            Path(__file__).parent.parent.parent.parent.parent
            / "instruments"
            / self.config_dir
            / filename
        )

    def _load_yaml(self, filename: str) -> dict:
        """Load and parse a YAML config file."""
        with open(self._config_path(filename)) as f:
            return yaml.safe_load(f)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest packages/obs_smalltel/tests/test_base_instrument.py -v
```

Expected: All PASS (both config loading and LSST tests)

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/python/lsst/obs/smalltel/base_instrument.py packages/obs_smalltel/tests/test_base_instrument.py
git commit -m "feat(obs_smalltel): implement GenericSmallTelInstrument with YAML-driven config"
```

---

### Task 8: Implement ConfigurableTranslator — YAML loading + can_translate

**Files:**
- Modify: `packages/obs_smalltel/python/lsst/obs/smalltel/base_translator.py`
- Create: `packages/obs_smalltel/tests/test_base_translator.py`

- [ ] **Step 1: Write failing test for YAML-driven translator setup**

```python
# packages/obs_smalltel/tests/test_base_translator.py
"""Tests for ConfigurableTranslator base class."""
import pytest


class TestTranslatorYamlLoading:
    """Test header_map.yaml loading (no LSST stack needed for these)."""

    def test_can_translate_matching_instrument(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        header = {"INSTRUME": "Nickel Direct Imager"}
        assert FakeTranslator.can_translate(header) is True

    def test_can_translate_non_matching(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        header = {"INSTRUME": "LRIS"}
        assert FakeTranslator.can_translate(header) is False

    def test_can_translate_case_insensitive(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        header = {"INSTRUME": "NICKEL Direct Imager"}
        assert FakeTranslator.can_translate(header) is True

    def test_const_map_loaded_from_yaml(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        assert "boresight_rotation_coord" in FakeTranslator._const_map

    def test_trivial_map_loaded_from_yaml(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        assert "exposure_time" in FakeTranslator._trivial_map
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest packages/obs_smalltel/tests/test_base_translator.py::TestTranslatorYamlLoading -v
```

Expected: FAIL — `ConfigurableTranslator` not implemented

- [ ] **Step 3: Implement ConfigurableTranslator core**

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/base_translator.py
"""Configurable FITS translator driven by YAML keyword mappings."""
from __future__ import annotations

__all__ = ("ConfigurableTranslator",)

import logging
import math
from pathlib import Path

import astropy.units as u
import yaml
from astro_metadata_translator.translator import cache_translation
from astro_metadata_translator.translators.fits import FitsTranslator
from astropy.coordinates import Angle, EarthLocation

log = logging.getLogger(__name__)


class ConfigurableTranslator(FitsTranslator):
    """FITS header translator driven by YAML keyword mappings.

    Subclasses set ``supported_instrument`` and ``config_dir``.
    Override individual ``to_*`` methods only for telescope-specific quirks.
    """

    supported_instrument: str
    config_dir: str

    def __init_subclass__(cls, **kwargs):
        """Load header mappings from YAML when subclass is defined."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "config_dir") and cls.config_dir is not None:
            try:
                mappings = cls._load_header_map()
                cls._const_map = cls._build_const_map(mappings.get("const_map", {}))
                cls._trivial_map = cls._build_trivial_map(
                    mappings.get("trivial_map", {})
                )
            except FileNotFoundError:
                # Config not yet created — allow class definition to proceed
                pass

    @classmethod
    def can_translate(cls, header, filename=None):
        instrume = header.get("INSTRUME", "").strip().lower()
        return cls.supported_instrument.lower() in instrume

    @classmethod
    def _package_root(cls) -> Path:
        """Resolve obs_smalltel package root (same logic as base_instrument)."""
        try:
            from lsst.utils import getPackageDir
            return Path(getPackageDir("obs_smalltel"))
        except (ImportError, LookupError):
            return Path(__file__).parent.parent.parent.parent.parent

    @classmethod
    def _instruments_dir(cls) -> Path:
        return cls._package_root() / "instruments" / cls.config_dir

    @classmethod
    def _load_header_map(cls) -> dict:
        config_path = cls._instruments_dir() / "header_map.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

    @classmethod
    def _load_instrument_config(cls) -> dict:
        config_path = cls._instruments_dir() / "instrument.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

    @classmethod
    def _build_const_map(cls, raw_map: dict) -> dict:
        """Convert YAML const_map to LSST format (with Angle wrapping)."""
        result = {}
        for key, value in raw_map.items():
            if key == "boresight_rotation_angle":
                result[key] = Angle(float(value) * u.deg)
            else:
                result[key] = value
        return result

    @classmethod
    def _build_trivial_map(cls, raw_map: dict) -> dict:
        """Convert YAML trivial_map to LSST's expected format.

        LSST trivial_map entries can be:
          - str: just the header keyword name
          - tuple: (keyword, {unit: ..., default: ...})
        """
        result = {}
        for prop, spec in raw_map.items():
            if isinstance(spec, str):
                result[prop] = spec
            elif isinstance(spec, dict):
                key = spec["key"]
                kwargs = {}
                if "unit" in spec:
                    unit = getattr(u, spec["unit"])
                    kwargs["unit"] = unit
                if "default" in spec:
                    default = spec["default"]
                    if isinstance(default, float) and math.isnan(default):
                        default = float("nan")
                    if "unit" in spec:
                        unit = getattr(u, spec["unit"])
                        default = default * unit
                    kwargs["default"] = default
                result[prop] = (key, kwargs) if kwargs else key
        return result

    # --- Default to_* methods from YAML ---

    def to_physical_filter(self) -> str:
        """Map FITS filter keyword to canonical name via filter_name_map."""
        mappings = self._load_header_map()
        filter_map = mappings.get("filter_name_map", {})
        raw_filter = str(self._header.get("FILTNAM", "UNKNOWN")).strip()
        # Try exact match, then uppercase match
        if raw_filter in filter_map:
            return filter_map[raw_filter]
        upper = raw_filter.upper()
        if upper in filter_map:
            return filter_map[upper]
        return raw_filter

    @cache_translation
    def to_location(self) -> EarthLocation:
        """Return telescope EarthLocation from instrument.yaml."""
        inst_config = self._load_instrument_config()
        loc = inst_config["location"]
        return EarthLocation.from_geodetic(
            lon=loc["longitude"], lat=loc["latitude"], height=loc["elevation"]
        )

    # --- Single-CCD defaults ---
    # Override these only if the telescope has multiple detectors.

    @cache_translation
    def to_detector_num(self) -> int:
        return 0

    @cache_translation
    def to_detector_name(self) -> str:
        return "0"

    @cache_translation
    def to_detector_unique_name(self) -> str:
        return "0"

    @cache_translation
    def to_detector_serial(self) -> str:
        return ""

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest packages/obs_smalltel/tests/test_base_translator.py::TestTranslatorYamlLoading -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/python/lsst/obs/smalltel/base_translator.py packages/obs_smalltel/tests/test_base_translator.py
git commit -m "feat(obs_smalltel): implement ConfigurableTranslator with YAML-driven mappings"
```

---

### Task 9: Test ConfigurableTranslator to_physical_filter and to_location

**Files:**
- Modify: `packages/obs_smalltel/tests/test_base_translator.py`

- [ ] **Step 1: Write tests for to_physical_filter and to_location**

```python
# Add to packages/obs_smalltel/tests/test_base_translator.py

class TestTranslatorMethods:
    """Test translator methods using mock headers."""

    def _make_translator(self, header_dict):
        """Create a translator subclass and instantiate with a mock header."""
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class TestTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"
            name = "TestNickel"

        # FitsTranslator.__init__ expects a dict-like header
        return TestTranslator(header_dict)

    def test_to_physical_filter_standard(self):
        t = self._make_translator({"INSTRUME": "Nickel", "FILTNAM": "B"})
        assert t.to_physical_filter() == "B"

    def test_to_physical_filter_open_maps_to_clear(self):
        t = self._make_translator({"INSTRUME": "Nickel", "FILTNAM": "OPEN"})
        assert t.to_physical_filter() == "clear"

    def test_to_physical_filter_c_maps_to_clear(self):
        t = self._make_translator({"INSTRUME": "Nickel", "FILTNAM": "C"})
        assert t.to_physical_filter() == "clear"

    def test_to_physical_filter_unknown_passthrough(self):
        t = self._make_translator({"INSTRUME": "Nickel", "FILTNAM": "EXOTIC"})
        assert t.to_physical_filter() == "EXOTIC"

    def test_to_location_returns_earth_location(self):
        from astropy.coordinates import EarthLocation

        t = self._make_translator({"INSTRUME": "Nickel"})
        loc = t.to_location()
        assert isinstance(loc, EarthLocation)
        # Lick Observatory is roughly at lat 37.3, lon -121.6
        assert abs(loc.lat.deg - 37.3414) < 0.01
        assert abs(loc.lon.deg - (-121.6429)) < 0.01
```

- [ ] **Step 2: Run tests**

```bash
pytest packages/obs_smalltel/tests/test_base_translator.py::TestTranslatorMethods -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add packages/obs_smalltel/tests/test_base_translator.py
git commit -m "test(obs_smalltel): add translator method tests for filter and location"
```

---

### Task 10: Implement GenericRawFormatter

**Files:**
- Modify: `packages/obs_smalltel/python/lsst/obs/smalltel/base_formatter.py`

- [ ] **Step 1: Write test for GenericRawFormatter structure**

```python
# Add to packages/obs_smalltel/tests/test_base_instrument.py

class TestGenericRawFormatter:
    """Test GenericRawFormatter base class."""

    def test_requires_instrument_class(self):
        obs_base = pytest.importorskip("lsst.obs.base")
        from lsst.obs.smalltel.base_formatter import GenericRawFormatter

        assert hasattr(GenericRawFormatter, "instrument_class")

    def test_requires_translator_class(self):
        obs_base = pytest.importorskip("lsst.obs.base")
        from lsst.obs.smalltel.base_formatter import GenericRawFormatter

        assert hasattr(GenericRawFormatter, "translatorClass")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest packages/obs_smalltel/tests/test_base_instrument.py::TestGenericRawFormatter -v
```

Expected: FAIL — base_formatter.py is a placeholder

- [ ] **Step 3: Implement GenericRawFormatter**

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/base_formatter.py
"""Generic raw formatter for single-CCD small telescopes."""
from __future__ import annotations

__all__ = ("GenericRawFormatter",)

from lsst.obs.base import FitsRawFormatterBase


class GenericRawFormatter(FitsRawFormatterBase):
    """Raw data formatter for small telescopes.

    Subclasses MUST set:
      - instrument_class: the GenericSmallTelInstrument subclass
      - translatorClass: the ConfigurableTranslator subclass
    """

    instrument_class = None
    translatorClass = None

    @property
    def filterDefinitions(self):
        return self.instrument_class().filterDefinitions

    def getDetector(self, id):
        return self.instrument_class().getCamera()[id]
```

- [ ] **Step 4: Run tests**

```bash
pytest packages/obs_smalltel/tests/test_base_instrument.py::TestGenericRawFormatter -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/python/lsst/obs/smalltel/base_formatter.py packages/obs_smalltel/tests/test_base_instrument.py
git commit -m "feat(obs_smalltel): implement GenericRawFormatter base class"
```

---

## Chunk 3: Nickel Subclasses + Entry Points

### Task 11: Create Nickel instrument subclass

**Files:**
- Create: `packages/obs_smalltel/python/lsst/obs/smalltel/nickel/instrument.py`
- Create: `packages/obs_smalltel/tests/test_nickel_instrument.py`

- [ ] **Step 1: Write failing test**

```python
# packages/obs_smalltel/tests/test_nickel_instrument.py
"""Tests for Nickel instrument implementation."""
import pytest

obs_base = pytest.importorskip("lsst.obs.base")


class TestNickelInstrument:
    def test_name(self):
        from lsst.obs.smalltel.nickel.instrument import Nickel

        assert Nickel.getName() == "Nickel"

    def test_is_generic_small_tel(self):
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument
        from lsst.obs.smalltel.nickel.instrument import Nickel

        assert issubclass(Nickel, GenericSmallTelInstrument)

    def test_camera_single_ccd(self):
        from lsst.obs.smalltel.nickel.instrument import Nickel

        inst = Nickel()
        camera = inst.getCamera()
        assert len(camera) == 1

    def test_filter_definitions(self):
        from lsst.obs.smalltel.nickel.instrument import Nickel

        inst = Nickel()
        names = {f.physical_filter for f in inst.filterDefinitions}
        assert {"B", "V", "R", "I", "clear"}.issubset(names)

    def test_get_raw_formatter(self):
        from lsst.obs.smalltel.nickel.instrument import Nickel

        inst = Nickel()
        fmt_cls = inst.getRawFormatter({})
        assert fmt_cls is not None
        assert "NickelRawFormatter" in fmt_cls.__name__
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest packages/obs_smalltel/tests/test_nickel_instrument.py -v
```

Expected: FAIL — nickel/instrument.py not implemented

- [ ] **Step 3: Implement Nickel instrument**

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/nickel/instrument.py
"""Nickel telescope instrument definition."""
from __future__ import annotations

__all__ = ("Nickel",)

from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument


class Nickel(GenericSmallTelInstrument):
    """Instrument class for the Nickel 1-meter telescope at Lick Observatory."""

    instrument_name = "Nickel"
    config_dir = "nickel"

    def getRawFormatter(self, dataId):
        from .formatter import NickelRawFormatter

        return NickelRawFormatter
```

- [ ] **Step 4: Run tests (getRawFormatter will fail until formatter exists)**

Note: `test_get_raw_formatter` will fail until Task 13. Run the other tests:

```bash
pytest packages/obs_smalltel/tests/test_nickel_instrument.py -v -k "not raw_formatter"
```

Expected: 4 PASS, 1 skipped

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/python/lsst/obs/smalltel/nickel/instrument.py packages/obs_smalltel/tests/test_nickel_instrument.py
git commit -m "feat(obs_smalltel): add Nickel instrument subclass"
```

---

### Task 12: Create NickelTranslator with custom overrides

**Files:**
- Create: `packages/obs_smalltel/python/lsst/obs/smalltel/nickel/translator.py`
- Create: `packages/obs_smalltel/tests/test_nickel_translator.py`

This is the most complex subclass — it carries the Nickel-specific logic from `obs_nickel/translator.py`. The following methods are overridden (not generic):

- `to_instrument()` — returns "Nickel"
- `to_exposure_id()` / `to_visit_id()` — Nickel-specific days-since-2000 encoding
- `to_datetime_begin()` / `to_datetime_end()` — Nickel-specific header fallback chain
- `to_day_obs()` — derived from datetime_end
- `to_observation_id()` — Nickel-specific format
- `to_observation_type()` — multi-keyword OBSTYPE + OBJECT logic
- `to_observation_reason()` — multi-keyword logic
- `to_tracking_radec()` — stuck-DEC bug handling
- `to_temperature()` — Nickel-specific header keyword

- [ ] **Step 1: Write tests for Nickel-specific translator methods**

```python
# packages/obs_smalltel/tests/test_nickel_translator.py
"""Tests for NickelTranslator — Nickel-specific method overrides."""
import pytest


class TestNickelTranslator:
    def _make_translator(self, extra_headers=None):
        from lsst.obs.smalltel.nickel.translator import NickelTranslator

        header = {
            "INSTRUME": "Nickel Direct Imager",
            "EXPTIME": 60.0,
            "OBJECT": "2023ixf",
            "OBSTYPE": "object",
            "FILTNAM": "R",
            "OBSNUM": 42,
            "DATE-OBS": "2023-05-20T05:30:00",
            "DATE-END": "2023-05-20T05:31:00",
            "RA": "14:03:38.58",
            "DEC": "+54:18:42.1",
            "CRVAL1": 210.9108,
            "CRVAL2": 54.3117,
            "AIRMASS": 1.2,
        }
        if extra_headers:
            header.update(extra_headers)
        return NickelTranslator(header)

    def test_can_translate(self):
        from lsst.obs.smalltel.nickel.translator import NickelTranslator

        assert NickelTranslator.can_translate({"INSTRUME": "Nickel Direct Imager"})
        assert not NickelTranslator.can_translate({"INSTRUME": "LRIS"})

    def test_to_instrument(self):
        t = self._make_translator()
        assert t.to_instrument() == "Nickel"

    def test_to_exposure_id_range(self):
        t = self._make_translator()
        eid = t.to_exposure_id()
        assert 0 < eid < 2**31

    def test_to_visit_id_equals_exposure_id(self):
        t = self._make_translator()
        assert t.to_visit_id() == t.to_exposure_id()

    def test_to_day_obs(self):
        t = self._make_translator()
        day = t.to_day_obs()
        assert day == 20230520  # UT date from DATE-END

    def test_to_observation_type_science(self):
        t = self._make_translator()
        assert t.to_observation_type() == "science"

    def test_to_observation_type_bias(self):
        t = self._make_translator({"OBSTYPE": "dark", "OBJECT": "bias"})
        assert t.to_observation_type() == "bias"

    def test_to_observation_type_flat(self):
        t = self._make_translator({"OBSTYPE": "flat", "OBJECT": "domeflat"})
        assert t.to_observation_type() == "flat"

    def test_to_physical_filter(self):
        t = self._make_translator()
        assert t.to_physical_filter() == "R"

    def test_to_physical_filter_open(self):
        t = self._make_translator({"FILTNAM": "OPEN"})
        assert t.to_physical_filter() == "clear"

    def test_to_physical_filter_unknown_falls_back_to_clear(self):
        """Nickel convention: unknown filters map to 'clear'."""
        t = self._make_translator({"FILTNAM": "EXOTIC"})
        assert t.to_physical_filter() == "clear"

    def test_to_tracking_radec_crval(self):
        """When CRVAL and RA/DEC agree, use CRVAL."""
        t = self._make_translator()
        coord = t.to_tracking_radec()
        assert abs(coord.ra.deg - 210.91) < 0.1
        assert abs(coord.dec.deg - 54.31) < 0.1

    def test_to_tracking_radec_stuck_dec(self):
        """When CRVAL2 disagrees with DEC by >1 deg, use RA/DEC."""
        t = self._make_translator({"CRVAL2": 30.0})
        coord = t.to_tracking_radec()
        # Should fall back to RA/DEC headers
        assert abs(coord.dec.deg - 54.31) < 0.1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest packages/obs_smalltel/tests/test_nickel_translator.py -v
```

Expected: FAIL — nickel/translator.py not created

- [ ] **Step 3: Implement NickelTranslator**

This is extracted from `packages/obs_nickel/python/lsst/obs/nickel/translator.py` with import path changes. The base class provides `_const_map`, `_trivial_map`, `can_translate()`, `to_physical_filter()`, `to_location()`, and single-CCD detector defaults. Nickel overrides the rest:

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/nickel/translator.py
"""Metadata translator for the Nickel telescope at Lick Observatory."""
from __future__ import annotations

__all__ = ("NickelTranslator",)

import logging

import astropy.time
import astropy.units as u
from astro_metadata_translator.translator import cache_translation
from astro_metadata_translator.translators.helpers import (
    tracking_from_degree_headers,
)
from astropy.coordinates import Angle, EarthLocation

from lsst.obs.smalltel.base_translator import ConfigurableTranslator

log = logging.getLogger(__name__)

EPOCH0 = astropy.time.Time("2000-01-01T00:00:00", scale="utc")


class NickelTranslator(ConfigurableTranslator):
    """Metadata translator for the Nickel 1-meter telescope."""

    name = "Nickel"
    supported_instrument = "Nickel"
    config_dir = "nickel"

    _observing_day_offset = astropy.time.TimeDelta(
        12 * 3600, format="sec", scale="tai"
    )

    @cache_translation
    def to_instrument(self) -> str:
        return "Nickel"

    @cache_translation
    def to_day_obs(self) -> int:
        return int(self.to_datetime_end().datetime.strftime("%Y%m%d"))

    @cache_translation
    def to_observation_id(self) -> str:
        return f"{self.to_day_obs():08d}_{int(self._header.get('OBSNUM', 0))}"

    @cache_translation
    def to_exposure_id(self) -> int:
        """Unique exposure/visit ID: (days_since_2000 * 10000) + OBSNUM."""
        obsnum = int(self._header["OBSNUM"])
        t = self.to_datetime_end()
        days = int((t - EPOCH0).to_value("day"))
        exposure_id = days * 10000 + obsnum
        if exposure_id >= 2**31:
            raise ValueError(f"exposure_id {exposure_id} is out of 31-bit range")
        return exposure_id

    @cache_translation
    def to_visit_id(self) -> int:
        return self.to_exposure_id()

    @cache_translation
    def to_datetime_begin(self):
        t = self._from_fits_date("DATE-BEG", scale="utc")
        if t is not None:
            return t
        return self._from_fits_date("DATE-OBS", scale="utc")

    @cache_translation
    def to_datetime_end(self):
        begin = self.to_datetime_begin()
        end = self._from_fits_date("DATE-END", scale="utc")
        if end is None or (begin is not None and end < begin):
            exptime = float(self._header.get("EXPTIME", 0.0) or 0.0)
            if begin is not None:
                if exptime > 0.0:
                    end = begin + astropy.time.TimeDelta(
                        exptime, format="sec", scale="tai"
                    )
                else:
                    end = begin
        return end

    def to_physical_filter(self) -> str:
        """Override base class to fall back to 'clear' for unknown filters.

        The base class passes through unrecognized filter names, but Nickel
        convention is to treat any unrecognized filter as 'clear' (unfiltered).
        """
        result = super().to_physical_filter()
        known = {"B", "V", "R", "I", "clear", "gp", "rp", "Halpha", "OIII"}
        if result not in known:
            log.warning(f"Unknown filter '{result}', mapping to 'clear'")
            return "clear"
        return result

    @cache_translation
    def to_observation_type(self) -> str:
        obstype = self._header.get("OBSTYPE", "").strip().lower()
        obj = self._header.get("OBJECT", "").strip().lower()
        if obstype == "dark":
            return "bias" if "bias" in obj else "dark"
        if obstype == "flat" or "flat" in obj:
            return "flat"
        if any(w in obj for w in ("focus", "focusing", "point")):
            return "focus"
        if "test" in obj or "post" in obj:
            return "focus"
        if "bias" in obj:
            return "bias"
        return "science"

    @cache_translation
    def to_observation_reason(self) -> str:
        object_str = self._header.get("OBJECT", "").strip().lower()
        if any(w in object_str for w in ("flat", "bias", "dark")):
            return "calibration"
        if "focus" in object_str:
            return "focus"
        if "test" in object_str or "post" in object_str:
            return "test"
        if object_str == "point":
            return "pointing"
        return "science"

    @cache_translation
    def to_tracking_radec(self):
        """Get tracking RA/Dec with CRVAL vs RA/DEC cross-validation.

        Handles Nickel's known stuck-DEC bug where CRVAL2 freezes at a
        previous pointing's value.
        """
        from astropy.coordinates import SkyCoord

        tolerance_deg = 1.0

        crval_coord = None
        try:
            crval_coord = tracking_from_degree_headers(
                self,
                ("RADECSYS", "RADESYS"),
                (("CRVAL1", "CRVAL2"),),
                unit=u.deg,
            )
        except Exception as e:
            log.warning(f"Failed to read CRVAL1/CRVAL2: {e}")

        radec_coord = None
        try:
            ra_str = self._header.get("RA")
            dec_str = self._header.get("DEC")
            if ra_str and dec_str:
                ra_angle = Angle(ra_str, unit=u.hourangle)
                dec_angle = Angle(dec_str, unit=u.deg)
                ref_system = (
                    self._header.get("RADECSYS")
                    or self._header.get("RADESYS")
                    or "ICRS"
                )
                radec_coord = SkyCoord(
                    ra_angle, dec_angle, frame=ref_system.lower()
                )
        except Exception as e:
            log.debug(f"Failed to read RA/DEC keywords: {e}")

        if crval_coord and radec_coord:
            crval_ra = crval_coord.ra.to(u.deg).value
            crval_dec = crval_coord.dec.to(u.deg).value
            radec_ra = radec_coord.ra.to(u.deg).value
            radec_dec = radec_coord.dec.to(u.deg).value

            ra_diff = abs(crval_ra - radec_ra)
            dec_diff = abs(crval_dec - radec_dec)
            if ra_diff > 180:
                ra_diff = 360 - ra_diff

            if ra_diff > tolerance_deg or dec_diff > tolerance_deg:
                log.warning(
                    f"CRVAL1/CRVAL2 ({crval_ra:.4f}, {crval_dec:.4f}) "
                    f"disagrees with RA/DEC ({radec_ra:.4f}, {radec_dec:.4f}) "
                    f"by ΔRA={ra_diff:.2f}°, ΔDec={dec_diff:.2f}°. "
                    f"Using RA/DEC from telescope control system."
                )
                return radec_coord

        if crval_coord:
            return crval_coord
        if radec_coord:
            log.info("CRVAL1/CRVAL2 not available, using RA/DEC keywords")
            return radec_coord

        raise ValueError("No valid tracking coordinates found in FITS header")

    @cache_translation
    def to_temperature(self) -> u.Quantity:
        temp_celsius = self._header.get("TEMPDET", -999.0)
        return (temp_celsius + 273.15) * u.K
```

- [ ] **Step 4: Run tests**

```bash
pytest packages/obs_smalltel/tests/test_nickel_translator.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/python/lsst/obs/smalltel/nickel/translator.py packages/obs_smalltel/tests/test_nickel_translator.py
git commit -m "feat(obs_smalltel): add NickelTranslator with custom overrides"
```

---

### Task 13: Create NickelRawFormatter

**Files:**
- Create: `packages/obs_smalltel/python/lsst/obs/smalltel/nickel/formatter.py`

- [ ] **Step 1: Implement NickelRawFormatter**

```python
# packages/obs_smalltel/python/lsst/obs/smalltel/nickel/formatter.py
"""Raw data formatter for the Nickel telescope."""
from __future__ import annotations

__all__ = ("NickelRawFormatter",)

from lsst.obs.smalltel.base_formatter import GenericRawFormatter
from .instrument import Nickel
from .translator import NickelTranslator


class NickelRawFormatter(GenericRawFormatter):
    instrument_class = Nickel
    translatorClass = NickelTranslator
```

- [ ] **Step 2: Run the deferred test from Task 11**

```bash
pytest packages/obs_smalltel/tests/test_nickel_instrument.py::TestNickelInstrument::test_get_raw_formatter -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add packages/obs_smalltel/python/lsst/obs/smalltel/nickel/formatter.py
git commit -m "feat(obs_smalltel): add NickelRawFormatter"
```

---

### Task 14: Update package __init__.py files and verify all imports

**Files:**
- Modify: `packages/obs_smalltel/python/lsst/obs/smalltel/__init__.py`
- Modify: `packages/obs_smalltel/python/lsst/obs/smalltel/nickel/__init__.py`

- [ ] **Step 1: Write import smoke test**

```python
# Add to packages/obs_smalltel/tests/test_nickel_instrument.py

class TestPackageImports:
    def test_import_from_package_root(self):
        from lsst.obs.smalltel import Nickel, NickelTranslator

        assert Nickel.getName() == "Nickel"
        assert NickelTranslator.supported_instrument == "Nickel"

    def test_import_from_nickel_subpackage(self):
        from lsst.obs.smalltel.nickel import Nickel, NickelTranslator

        assert Nickel is not None
        assert NickelTranslator is not None

    def test_import_base_classes(self):
        from lsst.obs.smalltel.base_formatter import GenericRawFormatter
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        assert GenericSmallTelInstrument is not None
        assert ConfigurableTranslator is not None
        assert GenericRawFormatter is not None
```

- [ ] **Step 2: Run import tests**

```bash
pytest packages/obs_smalltel/tests/test_nickel_instrument.py::TestPackageImports -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add packages/obs_smalltel/python/lsst/obs/smalltel/__init__.py packages/obs_smalltel/python/lsst/obs/smalltel/nickel/__init__.py packages/obs_smalltel/tests/test_nickel_instrument.py
git commit -m "feat(obs_smalltel): finalize package exports and verify all imports"
```

---

## Chunk 4: Pipeline Assets + Validation

### Task 15: Move shared pipeline tasks from obs_nickel

**Files:**
- Create: `packages/obs_smalltel/python/lsst/obs/smalltel/tasks/__init__.py`
- Copy: `packages/obs_nickel/python/lsst/obs/nickel/tasks/*.py` → `packages/obs_smalltel/python/lsst/obs/smalltel/tasks/`

The task modules are instrument-agnostic pipeline tasks that operate on generic LSST data types. The `calibCombine.py` (handles missing VisitInfo dates — useful for any small telescope) and `plotting.py` (shared lightcurve styling) also move from the obs_nickel package root into tasks/.

- [ ] **Step 1: Copy task files**

```bash
# Tasks from tasks/ subdirectory
cp packages/obs_nickel/python/lsst/obs/nickel/tasks/forcedPhotRaDec.py \
   packages/obs_smalltel/python/lsst/obs/smalltel/tasks/
cp packages/obs_nickel/python/lsst/obs/nickel/tasks/forcedPhotLightcurve.py \
   packages/obs_smalltel/python/lsst/obs/smalltel/tasks/
cp packages/obs_nickel/python/lsst/obs/nickel/tasks/forcedPhotDiffimLightcurveBand.py \
   packages/obs_smalltel/python/lsst/obs/smalltel/tasks/
cp packages/obs_nickel/python/lsst/obs/nickel/tasks/diaLightcurvePlot.py \
   packages/obs_smalltel/python/lsst/obs/smalltel/tasks/
cp packages/obs_nickel/python/lsst/obs/nickel/tasks/diaLightcurveCombinedPlot.py \
   packages/obs_smalltel/python/lsst/obs/smalltel/tasks/

# Modules from obs_nickel package root that belong with shared tasks
cp packages/obs_nickel/python/lsst/obs/nickel/calibCombine.py \
   packages/obs_smalltel/python/lsst/obs/smalltel/tasks/
cp packages/obs_nickel/python/lsst/obs/nickel/plotting.py \
   packages/obs_smalltel/python/lsst/obs/smalltel/tasks/
```

- [ ] **Step 2: Create tasks/__init__.py (copy and update imports)**

Copy `obs_nickel/python/lsst/obs/nickel/tasks/__init__.py` and update import paths from `lsst.obs.nickel.tasks` to `lsst.obs.smalltel.tasks`.

- [ ] **Step 3: Search for any `obs_nickel` imports within task files and update**

```bash
grep -r "lsst.obs.nickel" packages/obs_smalltel/python/lsst/obs/smalltel/tasks/
```

Replace any `lsst.obs.nickel` references with `lsst.obs.smalltel`.

- [ ] **Step 4: Verify task imports**

```bash
python -c "from lsst.obs.smalltel.tasks import ForcedPhotRaDecTask; print('OK')"
```

Expected: `OK` (or ImportError if LSST stack not active — that's fine)

- [ ] **Step 5: Commit**

```bash
git add packages/obs_smalltel/python/lsst/obs/smalltel/tasks/
git commit -m "feat(obs_smalltel): move shared pipeline tasks from obs_nickel"
```

---

### Task 16: Move pipeline YAMLs from obs_nickel

**Files:**
- Copy: `packages/obs_nickel/pipelines/*.yaml` → `packages/obs_smalltel/pipelines/`

- [ ] **Step 1: Copy pipeline YAML files**

```bash
# Core pipelines
cp packages/obs_nickel/pipelines/DRP.yaml packages/obs_smalltel/pipelines/
cp packages/obs_nickel/pipelines/DIA.yaml packages/obs_smalltel/pipelines/
cp packages/obs_nickel/pipelines/DifferentialPhot.yaml packages/obs_smalltel/pipelines/
cp packages/obs_nickel/pipelines/ForcedPhotRaDec.yaml packages/obs_smalltel/pipelines/
cp packages/obs_nickel/pipelines/ForcedPhot.yaml packages/obs_smalltel/pipelines/
cp packages/obs_nickel/pipelines/ProcessCcd.yaml packages/obs_smalltel/pipelines/
cp packages/obs_nickel/pipelines/PostProcessing.yaml packages/obs_smalltel/pipelines/

# Nickel calibration pipelines (kept Nickel-prefixed — future telescopes add their own)
cp packages/obs_nickel/pipelines/NickelCpBias.yaml packages/obs_smalltel/pipelines/
cp packages/obs_nickel/pipelines/NickelCpFlat.yaml packages/obs_smalltel/pipelines/

# Analysis pipelines
cp packages/obs_nickel/pipelines/nickel-analysis-*.yaml packages/obs_smalltel/pipelines/
cp packages/obs_nickel/pipelines/nickel-visit-quality-detector.yaml packages/obs_smalltel/pipelines/
```

- [ ] **Step 2: Update any task import paths in YAML files**

Search for `lsst.obs.nickel.tasks` references in pipeline YAMLs and update to `lsst.obs.smalltel.tasks`:

```bash
grep -r "lsst.obs.nickel" packages/obs_smalltel/pipelines/
```

Replace occurrences with `lsst.obs.smalltel`.

- [ ] **Step 3: Commit**

```bash
git add packages/obs_smalltel/pipelines/
git commit -m "feat(obs_smalltel): move pipeline YAMLs from obs_nickel"
```

---

### Task 17: Move pipeline config overrides from obs_nickel

**Files:**
- Copy: `packages/obs_nickel/configs/` → `packages/obs_smalltel/configs/nickel/`

- [ ] **Step 1: Copy config files**

```bash
cp -r packages/obs_nickel/configs/* packages/obs_smalltel/configs/nickel/
```

- [ ] **Step 2: Verify config structure**

```bash
ls -la packages/obs_smalltel/configs/nickel/
ls -la packages/obs_smalltel/configs/nickel/calibrateImage/tuned_configs/
```

Expected: All config files present under `configs/nickel/`

- [ ] **Step 3: Commit**

```bash
git add packages/obs_smalltel/configs/
git commit -m "feat(obs_smalltel): move Nickel pipeline configs from obs_nickel"
```

---

### Task 18: Full integration validation

**Files:**
- None (validation only)

This task validates that the `obs_smalltel` package works end-to-end with the LSST stack. Each step is a manual verification — if any fails, fix the issue before proceeding.

- [ ] **Step 1: Run all tests**

```bash
pytest packages/obs_smalltel/tests/ -v
```

Expected: All PASS

- [ ] **Step 2: Verify translator entry point resolves**

```bash
python -c "
from astro_metadata_translator import ObservationInfo
from lsst.obs.smalltel.nickel.translator import NickelTranslator
header = {'INSTRUME': 'Nickel Direct Imager', 'EXPTIME': 60.0,
          'DATE-OBS': '2023-05-20T05:30:00', 'DATE-END': '2023-05-20T05:31:00',
          'OBSNUM': 42, 'FILTNAM': 'R', 'OBSTYPE': 'object', 'OBJECT': 'test',
          'RA': '14:03:38.58', 'DEC': '+54:18:42.1',
          'CRVAL1': 210.9108, 'CRVAL2': 54.3117}
oi = ObservationInfo(header, translator_class=NickelTranslator)
print(f'instrument: {oi.instrument}')
print(f'exposure_id: {oi.exposure_id}')
print(f'observation_type: {oi.observation_type}')
print(f'physical_filter: {oi.physical_filter}')
print(f'day_obs: {oi.day_obs}')
"
```

Expected output should show valid Nickel metadata.

- [ ] **Step 3: Verify instrument can create camera**

```bash
python -c "
from lsst.obs.smalltel.nickel.instrument import Nickel
inst = Nickel()
cam = inst.getCamera()
print(f'Camera: {cam.getName()}, detectors: {len(cam)}')
for det in cam:
    print(f'  Detector {det.getId()}: {det.getName()}, {det.getBBox()}')
"
```

Expected: Shows single CCD with correct geometry.

- [ ] **Step 4: Verify formatter wiring**

```bash
python -c "
from lsst.obs.smalltel.nickel.instrument import Nickel
inst = Nickel()
fmt_cls = inst.getRawFormatter({})
print(f'Formatter: {fmt_cls.__name__}')
print(f'Translator: {fmt_cls.translatorClass.__name__}')
print(f'Instrument: {fmt_cls.instrument_class.__name__}')
"
```

Expected:
```
Formatter: NickelRawFormatter
Translator: NickelTranslator
Instrument: Nickel
```

- [ ] **Step 5: Commit integration test script (optional)**

If desired, save the validation as a script:

```bash
git add -A && git commit -m "chore(obs_smalltel): Phase 1 complete — package validated"
```

---

## Summary

Phase 1 creates the `obs_smalltel` package with:
- 3 base classes: `GenericSmallTelInstrument`, `ConfigurableTranslator`, `GenericRawFormatter`
- 4 YAML config files for Nickel: `instrument.yaml`, `camera.yaml`, `filters.yaml`, `header_map.yaml`
- 3 thin Nickel subclasses: `Nickel`, `NickelTranslator`, `NickelRawFormatter`
- Shared pipeline tasks, YAMLs, and configs moved from `obs_nickel`
- Full test coverage for YAML loading, translator methods, and integration

**Next:** Phase 2 plan will cover refactoring `obs_nickel_data_tools` → `small_tel_tools` with the `InstrumentPlugin` system and parameterized core modules.
