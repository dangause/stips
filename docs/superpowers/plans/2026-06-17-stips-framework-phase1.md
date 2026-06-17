# STIPS Framework — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract an instrument-agnostic STIPS framework (`stips` core + `obs_stips` LSST glue) and reimplement the Nickel instrument as a thin profile on top of it, with byte-for-byte translation parity.

**Architecture:** Three packages. `stips` core owns the `InstrumentProfile` dataclass + hook mechanism (import-light: only `stips` + astropy). `obs_stips` owns the generic `StipsInstrument`/`StipsTranslator`/`StipsRawFormatter` + the moved generic PipelineTasks + `plotting.py`. The Nickel fork `lsst.obs.nickel` shrinks to `profile.py` (declarative config + `@hook` quirks) + import-light binding modules (`translator.py`, `_instrument.py`, `rawFormatter.py`, each ≤6 lines) + the two genuine Nickel quirks (`calibCombine.py`, `visitInfo.py`) + `camera/nickel.yaml`.

**Tech Stack:** Python 3.12, uv workspace, pytest (unittest-style), ruff + black (pre-commit), LSST Science Pipelines (`lsst.obs.base`), `astro_metadata_translator`, astropy.

**Scope note:** Phase 1 of the 3-phase spec (`docs/superpowers/specs/2026-06-17-stips-multi-instrument-framework-design.md`). Phase 2 (tooling rename + de-hardcode, incl. `stips.collections`) and Phase 3 (docs) are separate plans. At the end of Phase 1 the `data_tools` tooling still imports `lsst.obs.nickel` exactly as today — nothing in `data_tools` changes here. **`stips/collections.py` is intentionally NOT built in Phase 1**: the existing `CollectionNames(night, run_ts)` in `data_tools/.../core/pipeline.py` has no callers in `stips` yet, so building a prefix-based version now would be dead code (YAGNI). It is wired in Phase 2's de-hardcode pass.

**Import-lightness rule (critical for the stack-free parity test):** `stips.profile`, `lsst.obs.stips.translator`, and the Nickel `profile.py` + `translator.py` must import **only** `stips`, `astro_metadata_translator`, and astropy — never `lsst.obs.base`. So: (a) the entry point stays `Nickel = lsst.obs.nickel.translator:NickelTranslator` pointing at a translator-only module; (b) `obs_stips/__init__.py` and `lsst.obs.nickel/__init__.py` import the translator eagerly but guard `instrument`/`formatter`/`tasks`/`plotting` behind `try/except ImportError` (mirroring the current `obs_nickel/__init__.py`), so importing the translator submodule never drags in `lsst.obs.base`.

**Test environment note:** Profile and translator tests are **stack-free** (plain `pytest`). Instrument-registration, formatter, and end-to-end tests are **stack-required** — run them inside the activated LSST stack (`setup -r packages/stips stips; setup -r packages/obs_stips obs_stips; setup -r packages/obs_nickel obs_nickel`). Each step marks which kind it is.

**Reference (read before starting):**
- Spec: `docs/superpowers/specs/2026-06-17-stips-multi-instrument-framework-design.md`
- Current instrument: `packages/obs_nickel/python/lsst/obs/nickel/_instrument.py`
- Current translator (quirk source of truth to port): `packages/obs_nickel/python/lsst/obs/nickel/translator.py` — note `to_location()` uses `EarthLocation.of_site("Lick Observatory")`, and `_const_map` carries `boresight_rotation_angle`/`_coord`.
- Current translator tests (golden-value source): `packages/obs_nickel/tests/test_translator.py` (e.g. `to_exposure_id() == 89421032`).

---

## File Structure

**New package `stips` (core, import-light):**
- `packages/stips/pyproject.toml` — distribution `stips`, `src/stips`
- `packages/stips/src/stips/__init__.py` — re-exports `InstrumentProfile`, `Site`, `Field`, `hook`
- `packages/stips/src/stips/profile.py` — `Site`, `Field`, `InstrumentProfile`, `hook`
- `packages/stips/tests/test_profile.py`

**New package `obs_stips` (LSST glue):**
- `packages/obs_stips/pyproject.toml` — distribution `obs-stips`, package under `python/`
- `packages/obs_stips/python/lsst/obs/stips/__init__.py`
- `packages/obs_stips/python/lsst/obs/stips/translator.py` — `StipsTranslator` (import-light)
- `packages/obs_stips/python/lsst/obs/stips/instrument.py` — `StipsInstrument` (stack)
- `packages/obs_stips/python/lsst/obs/stips/formatter.py` — `StipsRawFormatter` (stack)
- `packages/obs_stips/python/lsst/obs/stips/plotting.py` — moved from obs_nickel
- `packages/obs_stips/python/lsst/obs/stips/tasks/` — moved generic tasks
- `packages/obs_stips/tests/test_stips_translator.py` — synthetic-profile tests (stack-free)
- `packages/obs_stips/tests/test_stips_instrument.py` — registration (stack)
- `packages/obs_stips/tests/test_differential_phot.py` — moved with the task

**Modified Nickel fork `obs_nickel`:**
- NEW `python/lsst/obs/nickel/profile.py` — the Nickel profile (import-light)
- REPLACE-with-binding `python/lsst/obs/nickel/translator.py` (import-light, ≤6 lines)
- REPLACE-with-binding `python/lsst/obs/nickel/_instrument.py` (stack, ≤8 lines)
- REPLACE-with-binding `python/lsst/obs/nickel/rawFormatter.py` (stack, ≤8 lines)
- REWRITE `python/lsst/obs/nickel/__init__.py`
- KEEP `python/lsst/obs/nickel/{calibCombine,visitInfo}.py`, `camera/nickel.yaml`
- DELETE `python/lsst/obs/nickel/nickelFilters.py` (filters now in profile), `tasks/` (moved), `plotting.py` (moved), `tests/test_translator.py` (superseded by parity test)
- `pipelines/*.yaml` — repoint generic-task `class:` paths to `lsst.obs.stips.tasks.*`
- `pyproject.toml` — add `obs-stips`, `stips` deps; entry point target unchanged

**Root config:** `pyproject.toml` — add `packages/stips`, `packages/obs_stips` to ruff `src` and their `tests` dirs to pytest `testpaths`.

---

## Task 1: Capture golden translation values (baseline before any change)

Record the CURRENT `NickelTranslator` outputs so the reimplementation is provably identical. MUST precede any code change.

**Files:** Create `packages/obs_nickel/tests/test_translation_golden.py`

- [ ] **Step 1: Write the golden test against the CURRENT translator (stack-free).** Use the **full** header dict from the existing `test_translator.py:setUp` (copy it verbatim, including CRPIX/CTYPE/CUNIT/EQUINOX), plus a calibration header. Pin every `to_*` the fork relies on with **literal** expected values:

```python
# packages/obs_nickel/tests/test_translation_golden.py
"""Golden baseline: current NickelTranslator outputs. After the Phase 1
reimplementation, test_nickel_translator_parity.py re-asserts these SAME
literals against the new StipsTranslator-bound NickelTranslator."""
import unittest
import astropy.units as u
from astropy.time import Time
from lsst.obs.nickel.translator import NickelTranslator

SCIENCE_HEADER = {
    "INSTRUME": "Nickel Direct Camera", "OBSNUM": 1032, "EXPTIME": 120.0,
    "DATE-BEG": "2024-06-25T05:15:49.25", "DATE-END": "2024-06-25T05:17:49.25",
    "CRVAL1": 179.1170349121, "CRVAL2": 55.1252822876,
    "CRPIX1": 512.0, "CRPIX2": 512.0, "CUNIT1": "deg", "CUNIT2": "deg",
    "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN", "RADECSYS": "FK5", "EQUINOX": 2000.0,
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
        self.assertEqual(self.tr.to_exposure_id(), 89421032)  # from test_translator.py:128

    def test_telescope_default(self):
        self.assertEqual(self.tr.to_telescope(), "Nickel 1m")

    def test_boresight_airmass(self):
        self.assertAlmostEqual(self.tr.to_boresight_airmass(), 1.281367778778, places=6)

    def test_temperature_kelvin(self):
        self.assertAlmostEqual(self.tr.to_temperature().to_value(u.K), -109.7 + 273.15, places=3)

    def test_datetime_end(self):
        self.assertAlmostEqual(
            self.tr.to_datetime_end().mjd,
            Time("2024-06-25T05:17:49.25", format="isot", scale="utc").mjd, places=9)

    def test_tracking_radec(self):
        c = self.tr.to_tracking_radec()
        self.assertAlmostEqual(c.ra.deg, 179.1170349121, places=4)
        self.assertAlmostEqual(c.dec.deg, 55.1252822876, places=4)

    def test_location_is_lick(self):
        # of_site("Lick Observatory") — pin the exact resolved geodetic values.
        loc = self.tr.to_location()
        self.assertAlmostEqual(loc.lat.deg, 37.34333, places=4)   # confirm in Step 2
        self.assertAlmostEqual(loc.lon.deg, -121.63667, places=4) # confirm in Step 2

    def test_boresight_rotation(self):
        self.assertAlmostEqual(self.tr.to_boresight_rotation_angle().asDegrees(), 0.0, places=6)

class TestGoldenCalib(unittest.TestCase):
    def test_observation_type_flat(self):
        self.assertEqual(NickelTranslator(dict(CALIB_HEADER)).to_observation_type(), "flat")
```

- [ ] **Step 2: Run it and pin the REAL values.** `pytest packages/obs_nickel/tests/test_translation_golden.py -v`. For `to_location`, replace the placeholder lat/lon with the actual `of_site("Lick Observatory")` values printed by `python -c "from astropy.coordinates import EarthLocation; e=EarthLocation.of_site('Lick Observatory'); print(e.lat.deg, e.lon.deg, e.height)"`. Also add literal assertions for `to_day_obs`, `to_observation_id`, `to_observation_reason`. Expected: PASS with every value a hard literal.

- [ ] **Step 3: Commit.**
```bash
git add packages/obs_nickel/tests/test_translation_golden.py
git commit -m "test(obs_nickel): pin golden translation values before STIPS refactor"
```

---

## Task 2: Scaffold `stips` core package + profile

**Files:** Create `packages/stips/pyproject.toml`, `src/stips/__init__.py`, `src/stips/profile.py`, `tests/test_profile.py`. Modify root `pyproject.toml`.

- [ ] **Step 1: Write failing profile tests (stack-free).**
```python
# packages/stips/tests/test_profile.py
import unittest
from stips import InstrumentProfile, Site, Field, hook

def make_profile(**over):
    base = dict(name="Test", site=Site(0.0, 0.0, 0.0),
                filters={"B": "B", "OPEN": "clear"},
                header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
                camera="camera/test.yaml")
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

    def test_const_map_defaults_empty(self):
        self.assertEqual(make_profile().const_map, {})

class TestHookRegistration(unittest.TestCase):
    def test_hook_registers_by_function_name(self):
        p = make_profile()
        @hook(p)
        def observation_type(header):
            return "science"
        self.assertIn("observation_type", p.hooks)
        self.assertEqual(p.hooks["observation_type"]({}), "science")
```

- [ ] **Step 2: Run to verify it fails.** `pytest packages/stips/tests/test_profile.py -v` → FAIL (`ModuleNotFoundError: stips`).

- [ ] **Step 3: Implement the package.**

`packages/stips/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "stips"
version = "0.1.0"
description = "STIPS framework core: instrument profiles and hooks"
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
    """Telescope location. If ``name`` is set, the translator uses
    ``EarthLocation.of_site(name)``; otherwise geodetic lat/lon/elev."""
    latitude: float
    longitude: float
    elevation: float
    name: Optional[str] = None


@dataclass(frozen=True)
class Field:
    """One FITS-header → metadata mapping. unit is an astropy unit name (e.g. "s")."""
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
    eups_package: Optional[str] = None  # EUPS product name for getPackageDir (camera path)
    const_map: dict[str, Any] = field(default_factory=dict)
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
from .profile import Field, InstrumentProfile, Site, hook

__all__ = ["Field", "InstrumentProfile", "Site", "hook"]
```

- [ ] **Step 4: Register + install + run + lint.**
In root `pyproject.toml` add `"packages/stips"` to `[tool.ruff].src` and `"packages/stips/tests"` to `testpaths`.
```bash
uv pip install -e packages/stips
pytest packages/stips/tests -v                # PASS
ruff check packages/stips && black --check packages/stips
```

- [ ] **Step 5: Commit.**
```bash
git add packages/stips pyproject.toml
git commit -m "feat(stips): add framework core — InstrumentProfile, Site, Field, hook"
```

---

## Task 3: `StipsTranslator` (generic, header-map + hook driven, import-light)

Imports only `astro_metadata_translator` + astropy + `stips`. No `lsst.obs.base`.

**Files:** Create `packages/obs_stips/pyproject.toml`, `python/lsst/obs/stips/__init__.py`, `python/lsst/obs/stips/translator.py`, `tests/test_stips_translator.py`.

- [ ] **Step 1: Write failing tests with a SYNTHETIC profile (proves genericity, stack-free).**
```python
# packages/obs_stips/tests/test_stips_translator.py
import unittest
from stips import InstrumentProfile, Site, Field, hook
from lsst.obs.stips.translator import StipsTranslator

PROFILE = InstrumentProfile(
    name="Demo", site=Site(10.0, 20.0, 100.0),
    filters={"B": "B", "OPEN": "clear"},
    header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0),
                "telescope": Field("TELESCOP", default="Demo 1m")},
    const_map={"boresight_rotation_angle": 0.0, "boresight_rotation_coord": "sky"},
    camera="camera/demo.yaml", filter_key="FILTNAM",
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
        self.assertEqual(DemoTranslator({"INSTRUME": "Demo", "FILTNAM": "B"}).to_physical_filter(), "B")

    def test_unknown_filter_uses_hook(self):
        self.assertEqual(DemoTranslator({"INSTRUME": "Demo", "FILTNAM": "ZZ"}).to_physical_filter(), "clear")

    def test_location_geodetic(self):
        loc = DemoTranslator({"INSTRUME": "Demo"}).to_location()
        self.assertAlmostEqual(loc.lat.deg, 10.0, places=6)

    def test_telescope_trivial_default(self):
        self.assertEqual(DemoTranslator({"INSTRUME": "Demo"}).to_telescope(), "Demo 1m")

    def test_boresight_rotation_from_const_map(self):
        self.assertAlmostEqual(
            DemoTranslator({"INSTRUME": "Demo"}).to_boresight_rotation_angle().asDegrees(), 0.0, places=6)
```

- [ ] **Step 2: Run to verify it fails.** `pytest packages/obs_stips/tests/test_stips_translator.py -v` → FAIL.

- [ ] **Step 3: Implement.**

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

`python/lsst/obs/stips/translator.py` — build `_trivial_map`/`_const_map` from the profile
in `__init_subclass__`; set both `name` and `supported_instrument`; resolve filters from
`profile.filters` first then the `unknown_filter` hook; `to_location` uses
`of_site(site.name)` when set else `from_geodetic`; dispatch each hookable `to_*` via
`self._hook(...)`:
```python
from __future__ import annotations
import astropy.units as u
from astro_metadata_translator.translator import cache_translation
from astro_metadata_translator.translators.fits import FitsTranslator
from astropy.coordinates import Angle, EarthLocation


class StipsTranslator(FitsTranslator):
    """Generic FITS translator; subclass binds a ``profile``. See spec §3.3."""
    profile = None  # set by subclass binding

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        p = getattr(cls, "profile", None)
        if p is None:
            return
        cls.name = p.name
        cls.supported_instrument = p.name
        cls._trivial_map = _build_trivial_map(p.header_map)
        cls._const_map = _build_const_map(p.const_map)

    @classmethod
    def can_translate(cls, header, filename=None):
        return cls.profile.name.lower() in str(header.get("INSTRUME", "")).lower()

    def _hook(self, name):
        return self.profile.hooks.get(name)

    @cache_translation
    def to_location(self):
        s = self.profile.site
        if s.name:
            return EarthLocation.of_site(s.name)
        return EarthLocation.from_geodetic(lon=s.longitude, lat=s.latitude, height=s.elevation)

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
    def to_observation_reason(self):
        h = self._hook("observation_reason")
        return h(self._header) if h else "science"

    @cache_translation
    def to_temperature(self):
        h = self._hook("temperature")
        return h(self._header) if h else None

    @cache_translation
    def to_exposure_id(self):
        h = self._hook("exposure_id")
        return h(self._header) if h else None

    @cache_translation
    def to_visit_id(self):
        h = self._hook("visit_id")
        return h(self._header) if h else self.to_exposure_id()

    @cache_translation
    def to_tracking_radec(self):
        h = self._hook("tracking_radec")
        if h:
            return h(self._header, default=self._default_tracking_radec)
        return self._default_tracking_radec()

    def _default_tracking_radec(self):
        from astro_metadata_translator.translators.helpers import tracking_from_degree_headers
        return tracking_from_degree_headers(
            self, ("RADECSYS", "RADESYS"), (("CRVAL1", "CRVAL2"),), unit=u.deg)

    # Add the remaining hookable to_* (observation_id, day_obs, datetime_begin/end)
    # following the same _hook(...) pattern; provide a sensible generic default only
    # where one exists, else require a hook.

    # --- single-CCD defaults ---
    @cache_translation
    def to_detector_num(self):
        return 0
    @cache_translation
    def to_detector_name(self):
        return "0"
    @cache_translation
    def to_detector_serial(self):
        return ""
    @cache_translation
    def to_detector_group(self):
        return ""
    @cache_translation
    def to_detector_exposure_id(self):
        return self.to_exposure_id()


def _build_trivial_map(header_map):
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


def _build_const_map(raw):
    result = {}
    for k, v in raw.items():
        result[k] = Angle(float(v) * u.deg) if k == "boresight_rotation_angle" else v
    return result
```

`python/lsst/obs/stips/__init__.py` (import-light: translator eager, LSST-heavy guarded):
```python
from .translator import StipsTranslator
__all__ = ["StipsTranslator"]
try:
    from .instrument import StipsInstrument  # noqa: F401
    from .formatter import StipsRawFormatter  # noqa: F401
    __all__ += ["StipsInstrument", "StipsRawFormatter"]
except ImportError:
    pass
try:
    from . import plotting, tasks  # noqa: F401
    __all__ += ["plotting", "tasks"]
except ImportError:
    pass
```

- [ ] **Step 4: Install + run translator tests — expect PASS.**
```bash
uv pip install -e packages/obs_stips
pytest packages/obs_stips/tests/test_stips_translator.py -v
```

- [ ] **Step 5: Register `obs_stips` in root config + lint + commit.**
Add `"packages/obs_stips"` to ruff `src` and `"packages/obs_stips/tests"` to `testpaths`.
```bash
ruff check packages/obs_stips && black --check packages/obs_stips
git add packages/obs_stips pyproject.toml
git commit -m "feat(obs_stips): add generic StipsTranslator (import-light, profile + hooks)"
```

---

## Task 4: `StipsInstrument` + `StipsRawFormatter` (stack-required)

**Files:** Create `python/lsst/obs/stips/instrument.py`, `python/lsst/obs/stips/formatter.py`, `tests/test_stips_instrument.py`.

- [ ] **Step 1: Write failing instrument test (synthetic profile, real camera).** Mirror the
setup of `packages/obs_nickel/tests/test_instrument.py` exactly (it shows how to build an
in-memory registry and call `register`). Assert: `Subclass.getName()==profile.name`;
`filterDefinitions` built from `profile.filters`; `register()` writes one instrument + one
detector row.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement by porting `_instrument.py`.** Generic `StipsInstrument(Instrument)`:
- `getName()` → `cls.profile.name`; `policyName` property → `profile.policy_name`;
  `obsDataPackage` property → `profile.obs_data_package`.
- `filterDefinitions` → `FilterDefinitionCollection` built from `profile.filters`
  (one `FilterDefinition(physical, band=band)` per mapped value; de-dup bands).
- `getCamera()` → `yamlCamera.makeCamera(os.path.join(getPackageDir(profile.eups_package), profile.camera))`.
  (For Nickel, `eups_package="obs_nickel"`, `camera="camera/nickel.yaml"` → the existing
  `packages/obs_nickel/camera/nickel.yaml`.)
- `register()` → identical body to current Nickel `register()` (single-CCD R00/S00 labels);
  `class_name` is naturally the bound subclass path.
- `getRawFormatter()` → returns `self.rawFormatterClass` (set by the binding; default
  `StipsRawFormatter`).
- `translatorClass`, `rawFormatterClass` → set by the subclass binding.

`formatter.py` — generic `StipsRawFormatter(FitsRawFormatterBase)`; the binding subclass
supplies `instrumentClass`/`translatorClass`/`filterDefinitions`:
```python
__all__ = ["StipsRawFormatter"]
from lsst.obs.base import FitsRawFormatterBase

class StipsRawFormatter(FitsRawFormatterBase):
    """Generic single-CCD raw formatter; subclass sets instrumentClass/translatorClass."""
    instrumentClass = None   # set by binding (e.g. Nickel)
    translatorClass = None   # set by binding (e.g. NickelTranslator)
    def getDetector(self, id):
        return self.instrumentClass().getCamera()[id]
```

- [ ] **Step 4: Run instrument tests under the stack — expect PASS.**
```bash
pytest packages/obs_stips/tests/test_stips_instrument.py -v
```

- [ ] **Step 5: Commit.**
```bash
git add packages/obs_stips/python/lsst/obs/stips/instrument.py \
        packages/obs_stips/python/lsst/obs/stips/formatter.py \
        packages/obs_stips/tests/test_stips_instrument.py
git commit -m "feat(obs_stips): add generic StipsInstrument and StipsRawFormatter"
```

---

## Task 5: Move generic tasks + `plotting.py` into `obs_stips`

**Files:** `git mv` plotting + four task modules + `tasks/__init__.py` and the differential-phot test.

- [ ] **Step 1: Move with `git mv` (preserve history).**
```bash
git mv packages/obs_nickel/python/lsst/obs/nickel/plotting.py \
       packages/obs_stips/python/lsst/obs/stips/plotting.py
mkdir -p packages/obs_stips/python/lsst/obs/stips/tasks
for f in __init__ forcedPhotRaDec diaLightcurvePlot diaLightcurveCombinedPlot differentialPhot; do
  git mv packages/obs_nickel/python/lsst/obs/nickel/tasks/$f.py \
         packages/obs_stips/python/lsst/obs/stips/tasks/$f.py
done
git mv packages/obs_nickel/tests/test_differential_phot.py \
       packages/obs_stips/tests/test_differential_phot.py
```

- [ ] **Step 2: Repoint plotting imports inside the moved tasks.** In
`differentialPhot.py`, `diaLightcurveCombinedPlot.py`, `diaLightcurvePlot.py` change
`from lsst.obs.nickel.plotting import ...` → `from lsst.obs.stips.plotting import ...`.
Verify none remain: `grep -rn "obs.nickel.plotting\|obs\.nickel\.tasks" packages/obs_stips`.

- [ ] **Step 3: Fix the moved test's file-path loader.** `test_differential_phot.py` loads
the module by path via `importlib.util.spec_from_file_location` using a `_mod_path`. After
the move the test lives in `packages/obs_stips/tests/`, so update `_mod_path` to:
```python
_mod_path = (
    Path(__file__).resolve().parents[1]   # packages/obs_stips
    / "python" / "lsst" / "obs" / "stips" / "tasks" / "differentialPhot.py"
)
```

- [ ] **Step 4: Neutralize the instrument-tuned default.** In `differentialPhot.py`, change
the `matchRadius` `ConfigClass` default from `10.0` to LSST-neutral `2.0`, with a comment
`# Nickel's 10" value is set in the fork config tree — see spec §3.6`.

- [ ] **Step 5: Run the moved test.** The pure-numpy helpers are stack-free:
```bash
pytest packages/obs_stips/tests/test_differential_phot.py -v   # PASS
```

- [ ] **Step 6: Commit.** (Note: between this commit and Task 6, `obs_nickel/__init__.py`
still `try`s `from . import tasks`; it now fails the `try` silently — harmless, and the
YAMLs that still point at `lsst.obs.nickel.tasks.*` aren't exercised until Task 9.)
```bash
git add -A
git commit -m "refactor(obs_stips): move generic tasks + plotting from obs_nickel; neutralize matchRadius default"
```

---

## Task 6: Build the Nickel fork profile + import-light bindings

**Files:** Create `profile.py`; replace `translator.py`, `_instrument.py`, `rawFormatter.py`
with bindings; rewrite `__init__.py`; KEEP `calibCombine.py`, `visitInfo.py`; update `pyproject.toml`.

- [ ] **Step 1: Write `profile.py` — declarative config + all Nickel quirk hooks (stack-free).**
Port every Nickel-specific `to_*` body from the current `translator.py` **verbatim** into
`@hook` functions (only the wrapper signature changes). Move trivial mappings into
`header_map`/`filters`, and the boresight constants into `const_map`.
```python
# packages/obs_nickel/python/lsst/obs/nickel/profile.py
"""Nickel 1-meter telescope profile (Lick Observatory).
Copy this file, rename, and edit for your telescope. See spec §3.2."""
from stips import Field, InstrumentProfile, Site, hook

profile = InstrumentProfile(
    name="Nickel",
    policy_name="Nickel",
    site=Site(latitude=37.3414, longitude=-121.6429, elevation=1283.0,
              name="Lick Observatory"),   # name → EarthLocation.of_site (parity)
    filters={"B": "B", "V": "V", "R": "R", "I": "I", "OPEN": "clear", "C": "clear",
             "CLEAR": "clear", "GP": "gp", "G'": "gp", "RP": "rp", "R'": "rp",
             "HALPHA": "Halpha", "OIII": "OIII"},
    filter_key="FILTNAM",
    header_map={
        "exposure_time": Field("EXPTIME", unit="s", default=0.0),
        "dark_time": Field("EXPTIME", unit="s", default=0.0),
        "boresight_airmass": Field("AIRMASS", default=float("nan")),
        "object": Field("OBJECT", default="UNKNOWN"),
        "science_program": Field("PROGRAM", default="unknown"),
        "relative_humidity": Field("HUMIDITY", default=0.0),
        "telescope": Field("TELESCOP", default="Nickel 1m"),
    },
    const_map={"boresight_rotation_angle": 0.0, "boresight_rotation_coord": "sky"},
    camera="camera/nickel.yaml",
    eups_package="obs_nickel",
    night_to_dayobs_offset_days=1,
    skymap_name="nickelRings-v1",
    skymap_collection="skymaps/nickelRings",
    obs_data_package="obs_nickel_data",
    package_dir="lsst.obs.nickel",
)

@hook(profile)
def observation_type(header):
    ...  # exact body from translator.py:to_observation_type

@hook(profile)
def observation_reason(header):
    ...  # exact body from translator.py:to_observation_reason

@hook(profile)
def tracking_radec(header, default):
    ...  # exact stuck-DEC body from translator.py:to_tracking_radec

@hook(profile)
def exposure_id(header):
    ...  # exact body from translator.py:to_exposure_id (days*10000 + OBSNUM)

@hook(profile)
def visit_id(header):
    ...  # = exposure_id

@hook(profile)
def temperature(header):
    ...  # (TEMPDET + 273.15) * u.K

@hook(profile)
def unknown_filter(header, raw):
    ...  # log + return "clear"

# also port observation_id / day_obs / datetime_begin / datetime_end hooks
```

- [ ] **Step 2: Replace `translator.py` with an import-light binding** (keeps the entry
point target valid and stack-free):
```python
# packages/obs_nickel/python/lsst/obs/nickel/translator.py
from lsst.obs.stips.translator import StipsTranslator
from .profile import profile

__all__ = ["NickelTranslator"]

class NickelTranslator(StipsTranslator):
    profile = profile
```

- [ ] **Step 3: Replace `_instrument.py` with a binding** (stack):
```python
# packages/obs_nickel/python/lsst/obs/nickel/_instrument.py
from lsst.obs.stips.instrument import StipsInstrument
from .profile import profile
from .translator import NickelTranslator

__all__ = ["Nickel"]

class Nickel(StipsInstrument):
    profile = profile
    translatorClass = NickelTranslator
    @property
    def rawFormatterClass(self):
        from .rawFormatter import NickelRawFormatter
        return NickelRawFormatter
```

- [ ] **Step 4: Replace `rawFormatter.py` with a binding** (stack):
```python
# packages/obs_nickel/python/lsst/obs/nickel/rawFormatter.py
__all__ = ["NickelRawFormatter"]
from lsst.obs.stips.formatter import StipsRawFormatter
from ._instrument import Nickel
from .translator import NickelTranslator

class NickelRawFormatter(StipsRawFormatter):
    instrumentClass = Nickel
    translatorClass = NickelTranslator
    filterDefinitions = Nickel.filterDefinitions
```
(This keeps `from lsst.obs.nickel.rawFormatter import NickelRawFormatter` valid, so
`packages/obs_nickel/tests/test_formatter.py` needs no change. Confirm by reading it.)

- [ ] **Step 5: Rewrite `__init__.py`** (translator eager + light; instrument/formatter/
quirk-tasks guarded):
```python
from .translator import NickelTranslator
from .profile import profile

__all__ = ["NickelTranslator", "profile"]
try:
    from ._instrument import Nickel
    from .rawFormatter import NickelRawFormatter  # noqa: F401
    __all__ += ["Nickel", "NickelRawFormatter"]
except ImportError:
    pass
try:
    from . import calibCombine, visitInfo  # noqa: F401
    __all__ += ["calibCombine", "visitInfo"]
except ImportError:
    pass
```

- [ ] **Step 6: Update `pyproject.toml`.** Add `"obs-stips"`, `"stips"` to `dependencies`.
Entry point stays `Nickel = "lsst.obs.nickel.translator:NickelTranslator"`.

- [ ] **Step 7: Smoke-import.** Stack-free: `python -c "from lsst.obs.nickel.translator import NickelTranslator; print(NickelTranslator.name)"` → `Nickel`. Stack: `python -c "from lsst.obs.nickel import Nickel; print(Nickel.getName())"` → `Nickel`.

- [ ] **Step 8: Commit.**
```bash
git add packages/obs_nickel/python/lsst/obs/nickel/{profile,translator,_instrument,rawFormatter,__init__}.py \
        packages/obs_nickel/pyproject.toml
git commit -m "feat(obs_nickel): reimplement Nickel as a STIPS profile + import-light bindings"
```

---

## Task 7: Translation parity (the proof, stack-free)

**Files:** Create `packages/obs_nickel/tests/test_nickel_translator_parity.py`.

- [ ] **Step 1: Write the parity test.** Import the new translator from the **submodule**
(`from lsst.obs.nickel.translator import NickelTranslator`) so the test stays stack-free
(it must NOT do `from lsst.obs.nickel import ...`, which would pull in `_instrument` →
`lsst.obs.base`). Reuse the golden headers and assert the SAME literals:
```python
# packages/obs_nickel/tests/test_nickel_translator_parity.py
"""New StipsTranslator-bound NickelTranslator must reproduce the Task 1 golden literals."""
import unittest
import astropy.units as u
from lsst.obs.nickel.translator import NickelTranslator
from .test_translation_golden import SCIENCE_HEADER, CALIB_HEADER

class TestParity(unittest.TestCase):
    def setUp(self):
        self.tr = NickelTranslator(dict(SCIENCE_HEADER))
    # Mirror EVERY assertion from test_translation_golden.py with the same literals:
    def test_instrument(self): self.assertEqual(self.tr.to_instrument(), "Nickel")
    def test_filter(self): self.assertEqual(self.tr.to_physical_filter(), "B")
    def test_exposure_id(self): self.assertEqual(self.tr.to_exposure_id(), 89421032)
    def test_telescope(self): self.assertEqual(self.tr.to_telescope(), "Nickel 1m")
    def test_temperature(self):
        self.assertAlmostEqual(self.tr.to_temperature().to_value(u.K), -109.7 + 273.15, places=3)
    def test_location(self):
        self.assertAlmostEqual(self.tr.to_location().lat.deg, 37.34333, places=4)
    def test_boresight_rotation(self):
        self.assertAlmostEqual(self.tr.to_boresight_rotation_angle().asDegrees(), 0.0, places=6)
    def test_calib_flat(self):
        self.assertEqual(NickelTranslator(dict(CALIB_HEADER)).to_observation_type(), "flat")
    # ...continue until every golden assertion is mirrored...
```

- [ ] **Step 2: Run.** `pytest packages/obs_nickel/tests/test_nickel_translator_parity.py -v`.
Expected: PASS. If a value differs, fix the corresponding hook/field in `profile.py` until
it matches the golden literal. **Do not change the golden file.**

- [ ] **Step 3: Commit.**
```bash
git add packages/obs_nickel/tests/test_nickel_translator_parity.py
git commit -m "test(obs_nickel): parity — new NickelTranslator matches golden values"
```

---

## Task 8: Repoint pipelines + delete the superseded fat modules

**Files:** Modify `packages/obs_nickel/pipelines/*.yaml`; delete `nickelFilters.py`, `tests/test_translator.py`.

- [ ] **Step 1: Repoint generic-task `class:` paths in pipeline YAMLs.**
```bash
grep -rln "lsst.obs.nickel.tasks" packages/obs_nickel/pipelines
```
For each hit (`ForcedPhotRaDec.yaml`, `DifferentialPhot.yaml`, `nickel-analysis-dia-*.yaml`,
…) replace `lsst.obs.nickel.tasks.X` → `lsst.obs.stips.tasks.X`. **Leave unchanged:**
`instrument: lsst.obs.nickel.Nickel` lines and any `NickelCalibCombineTask` /
`lsst.obs.nickel.calibCombine` references (those are fork quirks). Verify:
`grep -rn "lsst.obs.nickel.tasks" packages/obs_nickel/pipelines` → no hits.

- [ ] **Step 2: Delete the superseded modules** (their bodies now live in the profile/bindings/obs_stips):
```bash
git rm packages/obs_nickel/python/lsst/obs/nickel/nickelFilters.py \
       packages/obs_nickel/tests/test_translator.py
```
(`translator.py`, `_instrument.py`, `rawFormatter.py` are NOT deleted — they are now
bindings from Task 6. `calibCombine.py`/`visitInfo.py` stay. `visitInfo.py` keeps
`from .translator import NickelTranslator`, which still resolves.)

- [ ] **Step 3: Full suite under the stack.**
```bash
pytest packages/stips/tests packages/obs_stips/tests packages/obs_nickel/tests -v
```
Expected: PASS — profile, stips-translator, golden, parity, instrument, formatter,
differential_phot, ingest tests all green.

- [ ] **Step 4: Lint gate.**
```bash
ruff check packages/stips packages/obs_stips packages/obs_nickel
black --check packages/stips packages/obs_stips packages/obs_nickel
```

- [ ] **Step 5: Commit.**
```bash
git add -A
git commit -m "refactor(obs_nickel): delete superseded filters/translator test; repoint task paths to obs_stips"
```

---

## Task 9: End-to-end smoke (fresh repo, one Nickel night) — manual gate

**Stack-required. Not an automated unit test.** Tooling is still on `nickel` this phase.

- [ ] **Step 1: Fresh bootstrap + one night.**
```bash
nickel -p 2023ixf bootstrap
nickel -p 2023ixf calibs 20230519
```
Expected: instrument registers as `Nickel`; raws ingest through the new translator; calib
collections appear under `Nickel/...`. Translation errors are the most likely failure surface.

- [ ] **Step 2: Spot-check one science exposure** processes and lands in `Nickel/runs/...`.
Note: differential-phot `matchRadius` now defaults to 2.0″ (Nickel's 10″ returns in Phase 2
config) — don't run a differential-phot validation expecting the 10″ behavior here.

- [ ] **Step 3: Record the result** (success + quanta counts) in the PR description. No code
commit unless a defect is found; if so, add a regression test first, then fix.

---

## Done criteria (Phase 1)

- [ ] `stips`, `obs_stips` packages exist and install into the workspace.
- [ ] `lsst.obs.nickel` is reduced to `profile.py` + ≤6-line bindings + `calibCombine.py` +
      `visitInfo.py` + `camera/`; no hand-written instrument/translator/filters bodies remain.
- [ ] Golden + parity tests prove translation (incl. location, telescope, boresight, exposure_id) is byte-for-byte unchanged.
- [ ] Generic tasks + `plotting.py` live in `obs_stips`; pipeline YAMLs reference them; `calibCombine`/`visitInfo` stay in the fork.
- [ ] `lsst.obs.stips.translator` and `lsst.obs.nickel.translator` import without the LSST stack (parity test runs stack-free).
- [ ] Full suite + ruff + black green; one Nickel night processes end-to-end on a fresh repo.
- [ ] `data_tools` is untouched (Phase 2 work).
