# STIPS Framework — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract an instrument-agnostic STIPS framework (`stips` core + `obs_stips` LSST glue) and reimplement the Nickel instrument as a thin profile on top of it, with byte-for-byte translation parity.

**Architecture:** Three packages. `stips` core owns the `InstrumentProfile` dataclass + hook mechanism + collection naming (import-light, no heavy LSST imports). `obs_stips` owns the generic `StipsInstrument`/`StipsTranslator`/`StipsRawFormatter` + the moved generic PipelineTasks + `plotting.py`. The Nickel fork package `lsst.obs.nickel` shrinks to `profile.py` (declarative config + `@hook` quirks) + 3-line bindings + the two genuine Nickel quirks (`calibCombine.py`, `visitInfo.py`) + `camera.yaml`.

**Tech Stack:** Python 3.12, uv workspace, pytest (unittest-style), ruff + black (pre-commit), LSST Science Pipelines (`lsst.obs.base`), `astro_metadata_translator`, astropy.

**Scope note:** This is Phase 1 of the 3-phase spec (`docs/superpowers/specs/2026-06-17-stips-multi-instrument-framework-design.md`). Phase 2 (tooling rename + de-hardcode) and Phase 3 (docs) get their own plans after this lands. At the end of Phase 1 the tooling still imports `lsst.obs.nickel` exactly as today — nothing in `data_tools` changes here.

**Test environment note:** Translator/profile/collection tests are **stack-free** — they import only `stips`, `astro_metadata_translator`, and astropy, so they run under plain `pytest`. Instrument-registration and end-to-end tests require the activated LSST stack; run those via the project's stack activation (e.g. `source` the stack loader, `setup -r packages/obs_stips obs_stips`, `setup -r packages/obs_nickel obs_nickel`) before invoking pytest. Each task marks which kind it is.

**Reference (read before starting):**
- Spec: `docs/superpowers/specs/2026-06-17-stips-multi-instrument-framework-design.md`
- Current instrument: `packages/obs_nickel/python/lsst/obs/nickel/_instrument.py`
- Current translator (the quirk source of truth to port): `packages/obs_nickel/python/lsst/obs/nickel/translator.py`
- Current translator tests (golden-value source): `packages/obs_nickel/tests/test_translator.py`

---

## File Structure

**New package `stips` (core, import-light):**
- `packages/stips/pyproject.toml` — distribution `stips`, src layout `src/stips`
- `packages/stips/src/stips/__init__.py` — re-exports `InstrumentProfile`, `Site`, `Field`, `hook`
- `packages/stips/src/stips/profile.py` — `Site`, `Field`, `InstrumentProfile`, `hook`
- `packages/stips/src/stips/collections.py` — `CollectionNames(prefix)` derivation
- `packages/stips/tests/test_profile.py`, `tests/test_collections.py`

**New package `obs_stips` (LSST glue):**
- `packages/obs_stips/pyproject.toml` — distribution `obs-stips`, package under `python/`
- `packages/obs_stips/python/lsst/obs/stips/__init__.py`
- `packages/obs_stips/python/lsst/obs/stips/translator.py` — `StipsTranslator`
- `packages/obs_stips/python/lsst/obs/stips/instrument.py` — `StipsInstrument`
- `packages/obs_stips/python/lsst/obs/stips/formatter.py` — `StipsRawFormatter`
- `packages/obs_stips/python/lsst/obs/stips/plotting.py` — moved from obs_nickel
- `packages/obs_stips/python/lsst/obs/stips/tasks/` — moved generic tasks
- `packages/obs_stips/tests/test_stips_translator.py` — synthetic-profile translation tests

**Modified Nickel fork `obs_nickel`:**
- `packages/obs_nickel/python/lsst/obs/nickel/profile.py` — NEW: the Nickel profile
- `packages/obs_nickel/python/lsst/obs/nickel/__init__.py` — bindings only
- `packages/obs_nickel/python/lsst/obs/nickel/{calibCombine,visitInfo}.py` — KEEP
- `packages/obs_nickel/python/lsst/obs/nickel/camera/nickel.yaml` — KEEP
- DELETE after parity: `_instrument.py`, `translator.py`, `rawFormatter.py`, `nickelFilters.py`, `plotting.py`, `tasks/`
- `packages/obs_nickel/pipelines/*.yaml` — repoint generic-task `class:` paths
- `packages/obs_nickel/pyproject.toml` — add `obs-stips`/`stips` deps

**Root config:**
- `pyproject.toml` — add new packages to ruff `src` and pytest `testpaths`

---

## Task 1: Capture golden translation values (baseline before any change)

Record the current `NickelTranslator`'s outputs so we can prove the reimplementation is identical. This MUST happen before any code moves.

**Files:**
- Create: `packages/obs_nickel/tests/test_translation_golden.py`

- [ ] **Step 1: Write the golden test against the CURRENT translator**

Use the header dict from the existing `test_translator.py:setUp` plus a second header exercising the stuck-DEC path (CRVAL2 disagreeing with DEC) and a calibration header (OBSTYPE/OBJECT → bias/flat/focus). For each header, assert the concrete values of every `to_*` the fork relies on:

```python
# packages/obs_nickel/tests/test_translation_golden.py
"""Golden baseline: current NickelTranslator outputs. After the Phase 1
reimplementation, test_nickel_translator_parity.py re-asserts these SAME
values against the new StipsTranslator-bound NickelTranslator."""
import unittest
import astropy.units as u
from astropy.time import Time
from lsst.obs.nickel.translator import NickelTranslator

SCIENCE_HEADER = {
    "INSTRUME": "Nickel Direct Camera", "OBSNUM": 1032, "EXPTIME": 120.0,
    "DATE-BEG": "2024-06-25T05:15:49.25", "DATE-END": "2024-06-25T05:17:49.25",
    "CRVAL1": 179.1170349121, "CRVAL2": 55.1252822876,
    "RADECSYS": "FK5", "RA": "11:56:28.09", "DEC": "+55:07:31.0",
    "OBJECT": "NGC_3982", "AIRMASS": 1.281367778778, "TEMPDET": -109.7,
    "FILTNAM": "B", "TELESCOP": "Nickel 1m",
}
CALIB_HEADER = {**SCIENCE_HEADER, "OBSTYPE": "flat", "OBJECT": "dome flat", "FILTNAM": "V"}

class TestGoldenScience(unittest.TestCase):
    def setUp(self):
        self.tr = NickelTranslator(dict(SCIENCE_HEADER))

    def test_instrument(self):
        self.assertEqual(self.tr.to_instrument(), "Nickel")

    def test_physical_filter(self):
        self.assertEqual(self.tr.to_physical_filter(), "B")

    def test_observation_type(self):
        self.assertEqual(self.tr.to_observation_type(), "science")

    def test_exposure_id(self):
        # Record the exact integer the current code produces.
        self.assertEqual(self.tr.to_exposure_id(), self.tr.to_exposure_id())  # placeholder

    def test_temperature_kelvin(self):
        self.assertAlmostEqual(
            self.tr.to_temperature().to_value(u.K), (-109.7 + 273.15), places=3)

class TestGoldenCalib(unittest.TestCase):
    def test_observation_type_flat(self):
        tr = NickelTranslator(dict(CALIB_HEADER))
        self.assertEqual(tr.to_observation_type(), "flat")
```

- [ ] **Step 2: Run it and capture the REAL values**

Run: `pytest packages/obs_nickel/tests/test_translation_golden.py -v`
Expected: PASS. For `to_exposure_id` (placeholder above), read the actual integer from a quick `python -c` and replace the placeholder assertion with the literal value, so the number is pinned. Add explicit literal assertions for `to_day_obs`, `to_observation_id`, `to_observation_reason`, and `to_tracking_radec` (ra/dec degrees) the same way.

- [ ] **Step 3: Commit**

```bash
git add packages/obs_nickel/tests/test_translation_golden.py
git commit -m "test(obs_nickel): pin golden translation values before STIPS refactor"
```

---

## Task 2: Scaffold `stips` core package + profile + collections

**Files:**
- Create: `packages/stips/pyproject.toml`, `packages/stips/src/stips/__init__.py`,
  `packages/stips/src/stips/profile.py`, `packages/stips/src/stips/collections.py`
- Create: `packages/stips/tests/test_profile.py`, `packages/stips/tests/test_collections.py`
- Modify: root `pyproject.toml` (ruff `src`, pytest `testpaths`)

- [ ] **Step 1: Write failing profile tests**

```python
# packages/stips/tests/test_profile.py
import unittest
from stips import InstrumentProfile, Site, Field, hook

def make_profile(**over):
    base = dict(
        name="Test", site=Site(0.0, 0.0, 0.0),
        filters={"B": "B", "OPEN": "clear"},
        header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
        camera="camera.yaml",
    )
    base.update(over)
    return InstrumentProfile(**base)

class TestProfileDefaults(unittest.TestCase):
    def test_policy_and_prefix_default_to_name(self):
        p = make_profile()
        self.assertEqual(p.policy_name, "Test")
        self.assertEqual(p.collection_prefix, "Test")

    def test_explicit_prefix_overrides(self):
        self.assertEqual(make_profile(collection_prefix="X").collection_prefix, "X")

    def test_night_offset_default_is_one(self):
        self.assertEqual(make_profile().night_to_dayobs_offset_days, 1)

class TestHookRegistration(unittest.TestCase):
    def test_hook_registers_by_function_name(self):
        p = make_profile()
        @hook(p)
        def observation_type(header):
            return "science"
        self.assertIn("observation_type", p.hooks)
        self.assertEqual(p.hooks["observation_type"]({}), "science")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest packages/stips/tests/test_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stips'`.

- [ ] **Step 3: Implement the package**

`packages/stips/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "stips"
version = "0.1.0"
description = "STIPS framework core: instrument profiles and collection naming"
requires-python = ">=3.12"
dependencies = ["astropy"]

[tool.setuptools.packages.find]
where = ["src"]
```

`packages/stips/src/stips/profile.py`:
```python
"""STIPS instrument profile: the single surface a forking telescope team edits."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class Site:
    """Telescope geodetic location (degrees, degrees, meters)."""
    latitude: float
    longitude: float
    elevation: float


@dataclass(frozen=True)
class Field:
    """One FITS-header → metadata mapping for a profile's header_map.

    key:     FITS keyword. unit: astropy unit name (e.g. "s") or None.
    default: value used when the keyword is absent.
    """
    key: str
    unit: Optional[str] = None
    default: Any = None


@dataclass
class InstrumentProfile:
    """Everything instrument-specific, in one object. See spec §3.2."""
    name: str
    site: Site
    filters: dict[str, str]
    header_map: dict[str, Field]
    camera: str
    filter_key: str = "FILTNAM"
    night_to_dayobs_offset_days: int = 1
    policy_name: Optional[str] = None
    collection_prefix: Optional[str] = None
    skymap_name: Optional[str] = None
    skymap_collection: Optional[str] = None
    obs_data_package: Optional[str] = None
    package_dir: Optional[str] = None
    refcat_path: Optional[str] = None
    fetch_data: Optional[Callable] = None
    hooks: dict[str, Callable] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.policy_name is None:
            self.policy_name = self.name
        if self.collection_prefix is None:
            self.collection_prefix = self.name


def hook(profile: InstrumentProfile, name: Optional[str] = None) -> Callable:
    """Decorator: register a quirk override on a profile, keyed by function name."""
    def deco(fn: Callable) -> Callable:
        profile.hooks[name or fn.__name__] = fn
        return fn
    return deco
```

`packages/stips/src/stips/__init__.py`:
```python
from .collections import CollectionNames
from .profile import Field, InstrumentProfile, Site, hook

__all__ = ["CollectionNames", "Field", "InstrumentProfile", "Site", "hook"]
```

- [ ] **Step 4: Run profile tests — expect PASS**

Run: `pytest packages/stips/tests/test_profile.py -v`
Expected: PASS.

- [ ] **Step 5: Write failing collections test, then implement `collections.py`**

```python
# packages/stips/tests/test_collections.py
import unittest
from stips import CollectionNames

class TestCollectionNames(unittest.TestCase):
    def setUp(self):
        self.c = CollectionNames(prefix="Nickel")

    def test_raw(self):
        self.assertEqual(self.c.raw("20230519", "ts1"),
                         "Nickel/raw/20230519/ts1")

    def test_calib_current(self):
        self.assertEqual(self.c.calib_current(), "Nickel/calib/current")

    def test_prefix_swaps_for_other_instrument(self):
        self.assertEqual(CollectionNames(prefix="ctio0m9").calib_current(),
                         "ctio0m9/calib/current")
```

Implement `CollectionNames` in `collections.py` by porting the existing prefix-based
methods from `packages/data_tools/src/obs_nickel_data_tools/core/pipeline.py` (the
`CollectionNames` class / `"Nickel/"` literals around lines 258–320), replacing the
hardcoded `"Nickel"` with the `prefix` constructor arg. Include at minimum:
`raw`, `calib`, `calib_current`, `processCcd_chain`, `diff`, `forced_phot`. Keep methods
that the tooling already calls; do not invent new ones (YAGNI).

Run: `pytest packages/stips/tests/test_collections.py -v` → PASS.

- [ ] **Step 6: Register `stips` in root config**

In root `pyproject.toml`: add `"packages/stips"` to `[tool.ruff].src` and
`"packages/stips/tests"` to `[tool.pytest.ini_options].testpaths`.

- [ ] **Step 7: Install into the workspace and run the full new suite + lint**

```bash
uv pip install -e packages/stips
pytest packages/stips/tests -v          # PASS
ruff check packages/stips && black --check packages/stips
```

- [ ] **Step 8: Commit**

```bash
git add packages/stips pyproject.toml
git commit -m "feat(stips): add framework core — InstrumentProfile, hooks, CollectionNames"
```

---

## Task 3: `StipsTranslator` (generic, header-map + hook driven)

Stack-free: imports only `astro_metadata_translator` + astropy + `stips`.

**Files:**
- Create: `packages/obs_stips/pyproject.toml`, `python/lsst/obs/stips/__init__.py`,
  `python/lsst/obs/stips/translator.py`
- Create: `packages/obs_stips/tests/test_stips_translator.py`

- [ ] **Step 1: Write failing tests with a SYNTHETIC profile (proves genericity)**

```python
# packages/obs_stips/tests/test_stips_translator.py
import unittest
from stips import InstrumentProfile, Site, Field, hook
from lsst.obs.stips.translator import StipsTranslator

PROFILE = InstrumentProfile(
    name="Demo", site=Site(10.0, 20.0, 100.0),
    filters={"B": "B", "OPEN": "clear"},
    header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
    camera="camera.yaml", filter_key="FILTNAM",
)

@hook(PROFILE)
def unknown_filter(header, raw):
    return "clear"

class DemoTranslator(StipsTranslator):
    profile = PROFILE

class TestStipsTranslator(unittest.TestCase):
    def test_can_translate_matches_name(self):
        self.assertTrue(DemoTranslator.can_translate({"INSTRUME": "Demo cam"}))
        self.assertFalse(DemoTranslator.can_translate({"INSTRUME": "Other"}))

    def test_known_filter_from_map(self):
        tr = DemoTranslator({"INSTRUME": "Demo", "FILTNAM": "B"})
        self.assertEqual(tr.to_physical_filter(), "B")

    def test_unknown_filter_uses_hook(self):
        tr = DemoTranslator({"INSTRUME": "Demo", "FILTNAM": "ZZ"})
        self.assertEqual(tr.to_physical_filter(), "clear")

    def test_location_from_site(self):
        tr = DemoTranslator({"INSTRUME": "Demo"})
        loc = tr.to_location()
        self.assertAlmostEqual(loc.lat.deg, 10.0, places=6)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest packages/obs_stips/tests/test_stips_translator.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `StipsTranslator`**

`packages/obs_stips/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "obs-stips"
version = "0.1.0"
description = "STIPS generic LSST obs glue (instrument, translator, formatter, tasks)"
requires-python = ">=3.12"
dependencies = ["stips", "astro_metadata_translator>=0.11.0", "astropy"]

[tool.setuptools.packages.find]
where = ["python"]
```

`python/lsst/obs/stips/translator.py` — implement the generic translator. Build
`_trivial_map`/`_const_map` from `profile.header_map` in `__init_subclass__`; resolve
`to_physical_filter` from `profile.filters` first, then the `unknown_filter` hook; source
`to_location` from `profile.site`; provide single-CCD defaults
(`to_detector_num`→0, etc.). For each hookable `to_*` (the spec §3.2 list), dispatch via a
small helper:

```python
from __future__ import annotations
import astropy.units as u
from astro_metadata_translator.translator import cache_translation
from astro_metadata_translator.translators.fits import FitsTranslator
from astropy.coordinates import EarthLocation


class StipsTranslator(FitsTranslator):
    """Generic FITS translator; subclass binds a `profile`. See spec §3.3."""
    profile = None  # set by subclass

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        p = getattr(cls, "profile", None)
        if p is None:
            return
        cls.name = p.name
        cls._trivial_map = _build_trivial_map(p.header_map)
        cls._const_map = {}

    @classmethod
    def can_translate(cls, header, filename=None):
        return cls.profile.name.lower() in str(header.get("INSTRUME", "")).lower()

    def _hook(self, name):
        return self.profile.hooks.get(name)

    @cache_translation
    def to_location(self):
        s = self.profile.site
        return EarthLocation.from_geodetic(lon=s.longitude, lat=s.latitude,
                                           height=s.elevation)

    def to_physical_filter(self):
        raw = str(self._header.get(self.profile.filter_key, "UNKNOWN")).strip()
        fmap = self.profile.filters
        if raw in fmap:
            return fmap[raw]
        if raw.upper() in fmap:
            return fmap[raw.upper()]
        h = self._hook("unknown_filter")
        return h(self._header, raw) if h else raw

    @cache_translation
    def to_observation_type(self):
        h = self._hook("observation_type")
        return h(self._header) if h else "science"

    @cache_translation
    def to_tracking_radec(self):
        h = self._hook("tracking_radec")
        if h:
            return h(self._header, default=self._default_tracking_radec)
        return self._default_tracking_radec()

    def _default_tracking_radec(self):
        from astro_metadata_translator.translators.helpers import (
            tracking_from_degree_headers,
        )
        return tracking_from_degree_headers(
            self, ("RADECSYS", "RADESYS"), (("CRVAL1", "CRVAL2"),), unit=u.deg)

    # ... single-CCD defaults: to_detector_num/name/serial/group/exposure_id ...
    # ... add the remaining hookable to_* (observation_reason, exposure_id, visit_id,
    #     temperature, day_obs, datetime_begin/end) following the same _hook(...) pattern.


def _build_trivial_map(header_map):
    """Convert profile.header_map (dict[str, Field]) → LSST trivial_map format."""
    import astropy.units as u
    result = {}
    for prop, f in header_map.items():
        kwargs = {}
        if f.unit is not None:
            unit = getattr(u, f.unit)
            kwargs["unit"] = unit
            if f.default is not None:
                kwargs["default"] = f.default * unit
        elif f.default is not None:
            kwargs["default"] = f.default
        result[prop] = (f.key, kwargs) if kwargs else f.key
    return result
```

`python/lsst/obs/stips/__init__.py`:
```python
from .translator import StipsTranslator
__all__ = ["StipsTranslator"]
# instrument/formatter/tasks added in later tasks; import lazily where LSST is needed.
```

- [ ] **Step 4: Run translator tests — expect PASS**

Run: `pip install -e packages/obs_stips && pytest packages/obs_stips/tests/test_stips_translator.py -v`
Expected: PASS.

- [ ] **Step 5: Register `obs_stips` in root config + commit**

Add `"packages/obs_stips"` to ruff `src` and `"packages/obs_stips/tests"` to `testpaths`.
```bash
ruff check packages/obs_stips && black --check packages/obs_stips
git add packages/obs_stips pyproject.toml
git commit -m "feat(obs_stips): add generic StipsTranslator driven by profile + hooks"
```

---

## Task 4: `StipsInstrument` + `StipsRawFormatter`

**Stack-required** (imports `lsst.obs.base`). Run under the activated LSST stack.

**Files:**
- Create: `python/lsst/obs/stips/instrument.py`, `python/lsst/obs/stips/formatter.py`
- Create: `packages/obs_stips/tests/test_stips_instrument.py`

- [ ] **Step 1: Write failing instrument test (synthetic profile + the real camera)**

Test that a `StipsInstrument` subclass bound to a profile returns `getName()==profile.name`,
builds filter definitions from `profile.filters`, and that `register()` writes one
instrument + one detector record (use an in-memory/temp Butler registry as the existing
`packages/obs_nickel/tests/test_instrument.py` does — mirror its setup exactly).

- [ ] **Step 2: Run to verify it fails** (`ModuleNotFoundError`/attribute).

- [ ] **Step 3: Implement by porting `_instrument.py`**

Port `packages/obs_nickel/python/lsst/obs/nickel/_instrument.py` into a generic
`StipsInstrument(Instrument)`:
- `getName()` → `cls.profile.name`; `policyName` → `profile.policy_name`;
  `obsDataPackage` → `profile.obs_data_package`.
- `filterDefinitions` → build a `FilterDefinitionCollection` from `profile.filters`.
- `getCamera()` → `yamlCamera.makeCamera(profile.camera)` (resolve the camera path relative
  to the bound subclass's package via `getPackageDir`, matching current behavior).
- `register()` → identical body to the current Nickel one (single-CCD R00/S00 labels),
  but `class_name` is naturally the bound subclass path.
- `getRawFormatter()` → returns `StipsRawFormatter` (or the subclass's, if overridden).
- `translatorClass` → set by the subclass binding.

`formatter.py`: port `rawFormatter.py` to a generic `StipsRawFormatter` (it is already
instrument-agnostic — confirm by reading the 19-line current file).

- [ ] **Step 4: Run instrument tests under the stack — expect PASS**

```bash
# inside activated stack: setup -r packages/stips stips; setup -r packages/obs_stips obs_stips
pytest packages/obs_stips/tests/test_stips_instrument.py -v
```

- [ ] **Step 5: Commit**

```bash
git add packages/obs_stips/python/lsst/obs/stips/instrument.py \
        packages/obs_stips/python/lsst/obs/stips/formatter.py \
        packages/obs_stips/tests/test_stips_instrument.py
git commit -m "feat(obs_stips): add generic StipsInstrument and StipsRawFormatter"
```

---

## Task 5: Move generic tasks + `plotting.py` into `obs_stips`

**Files:**
- Move: `obs_nickel/.../plotting.py` → `obs_stips/.../plotting.py`
- Move: `obs_nickel/.../tasks/{forcedPhotRaDec,diaLightcurvePlot,diaLightcurveCombinedPlot,differentialPhot}.py`
  and `tasks/__init__.py` → `obs_stips/.../tasks/`
- Modify: the three plot/diff task imports `from ...plotting import` →
  `from lsst.obs.stips.plotting import`
- Modify: `obs_stips/.../__init__.py` to expose `tasks` (mirror the try/except in the
  current `obs_nickel/__init__.py`)

- [ ] **Step 1: Move the files with `git mv` (preserve history)**

```bash
git mv packages/obs_nickel/python/lsst/obs/nickel/plotting.py \
       packages/obs_stips/python/lsst/obs/stips/plotting.py
mkdir -p packages/obs_stips/python/lsst/obs/stips/tasks
git mv packages/obs_nickel/python/lsst/obs/nickel/tasks/forcedPhotRaDec.py \
       packages/obs_stips/python/lsst/obs/stips/tasks/forcedPhotRaDec.py
# ...repeat for diaLightcurvePlot.py, diaLightcurveCombinedPlot.py, differentialPhot.py, __init__.py
```

- [ ] **Step 2: Repoint imports**

In the three movers that import plotting, change `from ..plotting import ...` (or
`from lsst.obs.nickel.plotting import ...`) → `from lsst.obs.stips.plotting import ...`.
Grep to confirm none remain: `grep -rn "obs.nickel.plotting\|\.\.plotting" packages/obs_stips`.

- [ ] **Step 3: Neutralize instrument-tuned defaults**

In `differentialPhot.py`, change the `matchRadius` default from `10.0` to an
instrument-neutral default (LSST's standard 2.0″) in the `ConfigClass`; the Nickel 10.0″
value will be set in the fork config tree in Phase 2. Add a code comment pointing to spec §3.6.

- [ ] **Step 4: Expose tasks from `obs_stips/__init__.py`**

Copy the try/except `from . import tasks` / `from . import plotting` pattern from the
current `obs_nickel/__init__.py` into `obs_stips/__init__.py`.

- [ ] **Step 5: Run the moved task tests**

The existing `packages/obs_nickel/tests/test_differential_phot.py` imports the task — update
its import to `lsst.obs.stips.tasks` and run it (stack-required for the LSST parts; the
pure-numpy `_process_catalogs` tests are stack-free):
```bash
pytest packages/obs_nickel/tests/test_differential_phot.py -v
```
Expected: PASS after import fix.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(obs_stips): move generic tasks + plotting from obs_nickel; neutralize tuned defaults"
```

---

## Task 6: Build the Nickel fork profile + bindings

**Files:**
- Create: `packages/obs_nickel/python/lsst/obs/nickel/profile.py`
- Modify: `packages/obs_nickel/python/lsst/obs/nickel/__init__.py`
- Modify: `packages/obs_nickel/pyproject.toml` (deps + entry point unchanged target)
- KEEP: `calibCombine.py`, `visitInfo.py`, `camera/nickel.yaml`

- [ ] **Step 1: Write `profile.py` — declarative config + all Nickel quirk hooks**

Port every Nickel-specific `to_*` from `packages/obs_nickel/python/lsst/obs/nickel/translator.py`
into `@hook` functions on the profile, and move the trivial mappings into `header_map` /
`filters`. The quirks to port as hooks (exact logic from the current translator): `observation_type`,
`observation_reason`, `tracking_radec` (stuck-DEC cross-check), `exposure_id`, `visit_id`,
`unknown_filter` (→ `clear`), `temperature` (°C→K), and the `datetime_begin/end` /
`day_obs` / `observation_id` logic. Keep each hook's body byte-identical to the current
method body (only the signature wrapper changes).

```python
# packages/obs_nickel/python/lsst/obs/nickel/profile.py
"""Nickel 1-meter telescope profile (Lick Observatory).
Copy this file, rename, and edit for your telescope. See spec §3.2."""
from stips import Field, InstrumentProfile, Site, hook

profile = InstrumentProfile(
    name="Nickel",
    policy_name="Nickel",
    site=Site(latitude=37.3414, longitude=-121.6429, elevation=1283.0),
    filters={"B": "B", "V": "V", "R": "R", "I": "I", "OPEN": "clear",
             "C": "clear", "CLEAR": "clear", "GP": "gp", "G'": "gp",
             "RP": "rp", "R'": "rp", "HALPHA": "Halpha", "OIII": "OIII"},
    filter_key="FILTNAM",
    header_map={
        "exposure_time": Field("EXPTIME", unit="s", default=0.0),
        "dark_time": Field("EXPTIME", unit="s", default=0.0),
        "boresight_airmass": Field("AIRMASS", default=float("nan")),
        "object": Field("OBJECT", default="UNKNOWN"),
        "science_program": Field("PROGRAM", default="unknown"),
        "relative_humidity": Field("HUMIDITY", default=0.0),
    },
    camera="camera/nickel.yaml",  # resolved relative to the package by the instrument
    night_to_dayobs_offset_days=1,
    skymap_name="nickelRings-v1",
    skymap_collection="skymaps/nickelRings",
    obs_data_package="obs_nickel_data",
    package_dir="lsst.obs.nickel",
)

# --- Quirk hooks: ported verbatim from the old NickelTranslator ---
@hook(profile)
def observation_type(header):
    ...  # exact body from translator.py:to_observation_type

@hook(profile)
def tracking_radec(header, default):
    ...  # exact stuck-DEC body from translator.py:to_tracking_radec
# ...remaining hooks...
```

- [ ] **Step 2: Rewrite `__init__.py` as bindings only**

```python
from stips import hook  # noqa: F401  (profile.py uses it)
from .profile import profile
from lsst.obs.stips.instrument import StipsInstrument
from lsst.obs.stips.translator import StipsTranslator


class NickelTranslator(StipsTranslator):
    profile = profile


class Nickel(StipsInstrument):
    profile = profile
    translatorClass = NickelTranslator

    def getRawFormatter(self, dataId):
        from .rawFormatter import NickelRawFormatter  # if a Nickel-specific one is needed
        return NickelRawFormatter


__all__ = ["Nickel", "NickelTranslator", "profile"]
```

Note: if the current `rawFormatter.py` is fully generic (confirm — it is 19 lines), drop
the override and let `StipsInstrument.getRawFormatter` return `StipsRawFormatter`; then
`NickelRawFormatter` is not needed. Decide based on reading the file.

- [ ] **Step 3: Update `pyproject.toml`**

Add `"obs-stips"` and `"stips"` to `dependencies`. Leave the entry point as
`Nickel = "lsst.obs.nickel:NickelTranslator"` (now resolves to the binding in `__init__.py`).

- [ ] **Step 4: Smoke-import under the stack**

```bash
python -c "from lsst.obs.nickel import Nickel, NickelTranslator; print(Nickel.getName())"
```
Expected: prints `Nickel`.

- [ ] **Step 5: Commit**

```bash
git add packages/obs_nickel/python/lsst/obs/nickel/profile.py \
        packages/obs_nickel/python/lsst/obs/nickel/__init__.py \
        packages/obs_nickel/pyproject.toml
git commit -m "feat(obs_nickel): reimplement Nickel as a STIPS profile + thin bindings"
```

---

## Task 7: Translation parity (the proof)

**Files:**
- Create: `packages/obs_nickel/tests/test_nickel_translator_parity.py`

- [ ] **Step 1: Write the parity test** — same headers as the Task 1 golden test, asserting
the SAME literal values, but importing the new `NickelTranslator`:

```python
# packages/obs_nickel/tests/test_nickel_translator_parity.py
"""New StipsTranslator-bound NickelTranslator must reproduce the Task 1 golden values."""
import unittest
from lsst.obs.nickel import NickelTranslator
from .test_translation_golden import SCIENCE_HEADER, CALIB_HEADER

class TestParity(unittest.TestCase):
    def test_science_filter(self):
        self.assertEqual(NickelTranslator(dict(SCIENCE_HEADER)).to_physical_filter(), "B")
    # ...mirror EVERY assertion from test_translation_golden.py with the same literals...
```

- [ ] **Step 2: Run parity test** (stack-free):

Run: `pytest packages/obs_nickel/tests/test_nickel_translator_parity.py -v`
Expected: PASS — identical outputs. If any value differs, fix the corresponding hook in
`profile.py` until it matches the golden literal. Do not change the golden file.

- [ ] **Step 3: Run the OLD translator test too** — it still imports `lsst.obs.nickel.translator`
which we are about to delete; confirm it currently passes, then it will be superseded in Task 8.

- [ ] **Step 4: Commit**

```bash
git add packages/obs_nickel/tests/test_nickel_translator_parity.py
git commit -m "test(obs_nickel): parity — new NickelTranslator matches golden values"
```

---

## Task 8: Repoint pipelines + retire old hand-written Python

**Files:**
- Modify: `packages/obs_nickel/pipelines/*.yaml` (generic-task `class:` paths)
- Delete: `_instrument.py`, `translator.py`, `nickelFilters.py`, old `tasks/` dir
  (already moved), and `test_translator.py` (superseded by the parity test)
- Delete `rawFormatter.py` only if Task 6 dropped the override

- [ ] **Step 1: Repoint generic-task class paths in pipeline YAMLs**

```bash
grep -rln "lsst.obs.nickel.tasks" packages/obs_nickel/pipelines
# For each: ForcedPhotRaDec.yaml, DifferentialPhot.yaml, nickel-analysis-dia-*.yaml ...
# replace  lsst.obs.nickel.tasks.X  ->  lsst.obs.stips.tasks.X
```
Leave `instrument: lsst.obs.nickel.Nickel` lines unchanged (the instrument stays Nickel).
Leave any `lsst.obs.nickel.NickelCalibCombineTask` / calibCombine references unchanged.

- [ ] **Step 2: Delete the superseded hand-written modules**

```bash
git rm packages/obs_nickel/python/lsst/obs/nickel/_instrument.py \
       packages/obs_nickel/python/lsst/obs/nickel/translator.py \
       packages/obs_nickel/python/lsst/obs/nickel/nickelFilters.py \
       packages/obs_nickel/tests/test_translator.py
# rawFormatter.py only if dropped in Task 6
```
Update `visitInfo.py`'s import (`from .translator import NickelTranslator` →
`from . import NickelTranslator`, now defined in `__init__.py`).

- [ ] **Step 3: Run the full obs_nickel + obs_stips + stips suites under the stack**

```bash
pytest packages/stips/tests packages/obs_stips/tests packages/obs_nickel/tests -v
```
Expected: PASS (golden + parity + instrument + differential_phot + formatter + ingest tests).

- [ ] **Step 4: Lint gate**

```bash
ruff check packages/stips packages/obs_stips packages/obs_nickel
black --check packages/stips packages/obs_stips packages/obs_nickel
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(obs_nickel): retire hand-written instrument/translator; repoint task paths to obs_stips"
```

---

## Task 9: End-to-end smoke (fresh repo, one Nickel night)

**Stack-required.** This is a manual verification gate, not an automated unit test.

- [ ] **Step 1: Fresh bootstrap + one night**

With the tooling still on `nickel` (unchanged this phase):
```bash
nickel -p 2023ixf bootstrap        # fresh repo
nickel -p 2023ixf calibs 20230519  # ingest + calibs through the new instrument/translator
```
Expected: instrument registers as `Nickel`; raws ingest; calibration collections appear
under `Nickel/...`. Watch for translation errors (the most likely failure surface).

- [ ] **Step 2: Spot-check one science exposure** processes and lands in `Nickel/runs/...`.

- [ ] **Step 3: Record the result** in the PR description (success + any quanta counts).
No code commit unless a defect is found and fixed (add a regression test first if so).

---

## Done criteria (Phase 1)

- [ ] `stips`, `obs_stips` packages exist and install into the workspace.
- [ ] `lsst.obs.nickel` is reduced to `profile.py` + bindings + `calibCombine.py` +
      `visitInfo.py` + `camera/`; no hand-written instrument/translator/filters remain.
- [ ] Golden + parity tests prove translation is byte-for-byte unchanged.
- [ ] Generic tasks + `plotting.py` live in `obs_stips`; pipeline YAMLs reference them.
- [ ] Full suite + ruff + black green; one Nickel night processes end-to-end on a fresh repo.
- [ ] `data_tools` is untouched (Phase 2 work).
