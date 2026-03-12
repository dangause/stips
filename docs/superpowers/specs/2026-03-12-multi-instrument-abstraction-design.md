# Multi-Instrument Abstraction Design

**Date:** 2026-03-12
**Status:** Draft
**Goal:** Refactor Nickel Processing Suite (NPS) into a generic small-telescope pipeline framework, with Nickel as the first supported instrument.

---

## Context

NPS is currently hardcoded for the Nickel 1-meter telescope at Lick Observatory. The codebase has ~80+ coupling points where "Nickel" is baked in: ~30 collection name prefixes, ~18 Butler WHERE clauses, ~8 skymap references, instrument class paths, config fields, CLI naming, and more. See "Detailed Parameterization Plan" for the full catalog.

The target is to support **other small (1-2m) single-CCD telescopes** at different observatories — different FITS headers, filters, cameras, and archives — while sharing the full pipeline workflow: calibration, science processing, DIA, forced photometry, transit detection, variable star monitoring, and lightcurve extraction.

### Constraints discovered during audit

1. **Butler stores Python class paths** — each instrument needs a unique importable Python class for `register-instrument`.
2. **Translators register via entry points** — each needs its own `can_translate()` classmethod.
3. **Formatters couple to instrument classes** — each formatter calls `InstrumentClass().getCamera()[id]`.

A purely config-driven approach (zero Python per instrument) is not possible. But the Python per instrument can be reduced to **~40 lines of boilerplate stubs** that delegate to YAML config and shared base classes.

---

## Architecture Overview

The system splits into two layers:

1. **`obs_smalltel`** — Generic LSST instrument package. Handles camera geometry, FITS translation, filter definitions, and pipeline tasks. Per-telescope customization is 4 YAML files + thin Python subclasses.

2. **`pipeline_tools` (small-tel-tools)** — Generic pipeline orchestration CLI. Handles calibration, science processing, DIA, forced photometry, lightcurves, transit detection. Per-telescope customization is an `InstrumentPlugin` that provides archive access, bootstrap steps, and default configs.

```
┌─────────────────────────────────────────────────┐
│  Target YAML Config (scripts/config/{target}/)  │
│  instrument: nickel                             │
│  ra, dec, bands, nights, options...             │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  pipeline_tools (small-tel-tools)               │
│  CLI: stt run config.yaml                       │
│  Core: calibs, science, dia, fphot, lightcurve  │
│  Plugin: InstrumentPlugin (archive, bootstrap)  │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  obs_smalltel (LSST instrument package)         │
│  Base: GenericSmallTelInstrument                 │
│  Base: ConfigurableTranslator                    │
│  Per-telescope: YAML config + Python stubs      │
│  Shared: pipeline tasks, pipeline YAMLs         │
└─────────────────────────────────────────────────┘
```

---

## Repository Structure

```
small_telescope_suite/
├── packages/
│   ├── obs_smalltel/                    # Generic LSST instrument package
│   │   ├── pyproject.toml
│   │   ├── python/lsst/obs/smalltel/
│   │   │   ├── __init__.py
│   │   │   ├── base_instrument.py       # GenericSmallTelInstrument
│   │   │   ├── base_translator.py       # ConfigurableTranslator
│   │   │   ├── base_formatter.py        # GenericRawFormatter
│   │   │   ├── nickel/                  # Nickel thin subclasses (~40 lines total)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── instrument.py
│   │   │   │   ├── translator.py
│   │   │   │   └── formatter.py
│   │   │   └── tasks/                   # Shared pipeline tasks (instrument-agnostic)
│   │   │       ├── forcedPhotRaDec.py
│   │   │       ├── differentialPhot.py
│   │   │       └── calibCombine.py
│   │   ├── instruments/                 # Per-telescope YAML config
│   │   │   └── nickel/
│   │   │       ├── instrument.yaml
│   │   │       ├── camera.yaml
│   │   │       ├── filters.yaml
│   │   │       └── header_map.yaml
│   │   ├── pipelines/                   # Shared pipeline definitions
│   │   │   ├── DRP.yaml
│   │   │   ├── DIA.yaml
│   │   │   ├── ForcedPhotRaDec.yaml
│   │   │   └── DifferentialPhot.yaml
│   │   └── configs/                     # Pipeline config overrides
│   │       ├── common/                  # Defaults for all small telescopes
│   │       └── nickel/                  # Nickel-specific tuning
│   │
│   ├── obs_nickel_data/                 # Curated Nickel calibrations (unchanged)
│   │
│   └── pipeline_tools/                  # Generic pipeline orchestration
│       ├── pyproject.toml               # package: small-tel-tools
│       └── src/small_tel_tools/
│           ├── __init__.py
│           ├── cli.py                   # stt CLI entry point
│           ├── instruments/
│           │   ├── __init__.py
│           │   ├── base.py              # InstrumentPlugin ABC
│           │   ├── registry.py          # Plugin discovery via entry points
│           │   └── nickel.py            # NickelPlugin
│           ├── core/                    # Generic pipeline modules
│           │   ├── config.py            # YAML-only configuration
│           │   ├── pipeline.py          # CollectionNames(prefix, night)
│           │   ├── calibs.py
│           │   ├── science.py
│           │   ├── dia.py
│           │   ├── fphot.py
│           │   ├── coadd.py
│           │   ├── lightcurve.py
│           │   ├── transit.py
│           │   ├── run.py               # YAML orchestrator
│           │   ├── stack.py
│           │   ├── bootstrap.py
│           │   └── executor.py
│           └── standalone/            # Scripts that run inside LSST stack env
│               ├── fetch_archive.py     # Delegates to plugin.fetch_data()
│               ├── ingest_ps1_template.py
│               ├── extract_lightcurve.py
│               └── differential_phot.py
│
├── scripts/
│   ├── config/                          # Per-target YAML configs
│   └── utilities/
├── docs/
├── Makefile
└── pyproject.toml                       # Workspace root
```

---

## Component Design

### 1. obs_smalltel: GenericSmallTelInstrument

Base class that loads camera geometry, filters, and registration data from YAML config files.

```python
class GenericSmallTelInstrument(lsst.obs.base.Instrument):
    """Base instrument for single-CCD small telescopes.

    Subclasses set `instrument_name` and `config_dir`.
    Everything else loads from YAML in instruments/{config_dir}/.
    """
    instrument_name: str   # e.g., "Nickel"
    config_dir: str        # e.g., "nickel" — subdirectory under instruments/

    def getName(self):
        return self.instrument_name

    def getCamera(self):
        camera_yaml = self._config_path("camera.yaml")
        return yamlCamera.makeCamera(camera_yaml)

    def register(self, registry, update=False):
        instrument_config = self._load_yaml("instrument.yaml")
        camera = self.getCamera()
        with registry.transaction():
            registry.syncDimensionData("instrument", {
                "name": self.getName(),
                "class_name": get_full_type_name(type(self)),
                "detector_max": len(camera),
                "visit_max": 2**31,
                "visit_system": VisitSystem[instrument_config.get(
                    "visit_system", "ONE_TO_ONE"
                )].value,
                "exposure_max": 2**31,
            }, update=update)
            for det in camera:
                registry.syncDimensionData("detector", {
                    "instrument": self.getName(),
                    "id": int(det.getId()),
                    "full_name": det.getName(),
                    "name_in_raft": det.getName(),
                    "raft": "R00",
                    "purpose": det.getType().name,
                }, update=update)
            # Register filter definitions with Butler
            self._registerFilters(registry, update=update)

    @property
    def filterDefinitions(self):
        """Load filter definitions from YAML. Cached after first access."""
        if not hasattr(self, "_filter_defs"):
            filters_config = self._load_yaml("filters.yaml")
            self._filter_defs = FilterDefinitionCollection(*[
                FilterDefinition(f["name"], band=f.get("band"), doc=f.get("doc", ""))
                for f in filters_config["filters"]
            ])
        return self._filter_defs

    def getRawFormatter(self, dataId):
        # Subclass overrides this to return its specific formatter
        raise NotImplementedError

    def _config_path(self, filename):
        return Path(__file__).parent.parent.parent / "instruments" / self.config_dir / filename

    def _load_yaml(self, filename):
        with open(self._config_path(filename)) as f:
            return yaml.safe_load(f)
```

A Nickel instrument subclass is minimal:

```python
# python/lsst/obs/smalltel/nickel/instrument.py
from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument

class Nickel(GenericSmallTelInstrument):
    instrument_name = "Nickel"
    policyName = "Nickel"
    config_dir = "nickel"

    def getRawFormatter(self, dataId):
        from .formatter import NickelRawFormatter
        return NickelRawFormatter
```

### 1b. obs_smalltel: GenericRawFormatter

The formatter needs to know which instrument class to instantiate for camera access.
Subclasses set `instrument_class` as their only customization.

```python
# python/lsst/obs/smalltel/base_formatter.py
from lsst.obs.base import FitsRawFormatterBase

class GenericRawFormatter(FitsRawFormatterBase):
    """Raw data formatter for small telescopes.

    Subclasses MUST set:
      - instrument_class: the GenericSmallTelInstrument subclass
      - translatorClass: the ConfigurableTranslator subclass
    """
    instrument_class = None   # Set by subclass
    translatorClass = None    # Set by subclass

    @property
    def filterDefinitions(self):
        return self.instrument_class().filterDefinitions

    def getDetector(self, id):
        return self.instrument_class().getCamera()[id]
```

A Nickel formatter is pure wiring:

```python
# python/lsst/obs/smalltel/nickel/formatter.py
from lsst.obs.smalltel.base_formatter import GenericRawFormatter
from .instrument import Nickel
from .translator import NickelTranslator

class NickelRawFormatter(GenericRawFormatter):
    instrument_class = Nickel
    translatorClass = NickelTranslator
```

### 2. obs_smalltel: ConfigurableTranslator

Base translator that reads FITS header keyword mappings from YAML.

```python
class ConfigurableTranslator(FitsTranslator):
    """FITS header translator driven by YAML keyword mappings.

    Subclasses set `supported_instrument` and `config_dir`.
    Override individual `to_*` methods only for telescope-specific quirks.
    """
    supported_instrument: str
    config_dir: str

    def __init_subclass__(cls, **kwargs):
        """Load header mappings from YAML when subclass is defined."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "config_dir"):
            mappings = cls._load_header_map()
            cls._const_map = mappings.get("const_map", {})
            cls._trivial_map = cls._parse_trivial_map(mappings.get("trivial_map", {}))

    @classmethod
    def can_translate(cls, header, filename=None):
        instrume = header.get("INSTRUME", "").strip().lower()
        return cls.supported_instrument.lower() in instrume

    @classmethod
    def _load_header_map(cls):
        config_path = (Path(__file__).parent.parent.parent
                      / "instruments" / cls.config_dir / "header_map.yaml")
        with open(config_path) as f:
            return yaml.safe_load(f)

    @classmethod
    def _parse_trivial_map(cls, raw_map):
        """Convert YAML trivial_map to LSST's expected format."""
        result = {}
        for prop, spec in raw_map.items():
            if isinstance(spec, str):
                result[prop] = spec
            elif isinstance(spec, dict):
                key = spec["key"]
                kwargs = {}
                if "unit" in spec:
                    kwargs["unit"] = getattr(u, spec["unit"])
                if "default" in spec:
                    default = spec["default"]
                    if "unit" in spec:
                        default = default * getattr(u, spec["unit"])
                    kwargs["default"] = default
                result[prop] = (key, kwargs) if kwargs else key
        return result

    # --- YAML-driven to_* method implementations ---
    # These base methods read from header_map.yaml sections.
    # Subclasses override only for telescope-specific quirks.

    def to_physical_filter(self):
        """Map FITS filter keyword to canonical name via filter_name_map."""
        mappings = self._load_header_map()
        filter_map = mappings.get("filter_name_map", {})
        raw_filter = self._header.get("FILTNAM", "UNKNOWN").strip()
        return filter_map.get(raw_filter, raw_filter)

    def to_observation_type(self):
        """Map FITS OBSTYPE to standard type via observation_type_map."""
        mappings = self._load_header_map()
        obs_type_map = mappings.get("observation_type_map", {})
        raw_type = self._header.get("OBSTYPE", "").strip().lower()
        return obs_type_map.get(raw_type, "science")

    def to_location(self):
        """Return telescope EarthLocation from instrument.yaml."""
        inst_config = self._load_instrument_config()
        loc = inst_config["location"]
        return EarthLocation.from_geodetic(
            lon=loc["longitude"], lat=loc["latitude"], height=loc["elevation"]
        )

    @classmethod
    def _load_instrument_config(cls):
        config_path = (Path(__file__).parent.parent.parent
                      / "instruments" / cls.config_dir / "instrument.yaml")
        with open(config_path) as f:
            return yaml.safe_load(f)
```

**Which `to_*` methods the base class provides from YAML vs which need overrides:**

| Method | Base class (from YAML) | Typical overrides |
|--------|----------------------|-------------------|
| `to_physical_filter()` | `filter_name_map` lookup | Rarely — only if filter keyword varies per exposure type |
| `to_observation_type()` | `observation_type_map` lookup | Sometimes — if classification needs multi-keyword logic |
| `to_location()` | `instrument.yaml` location | Never — pure config |
| `to_exposure_time()` | `_trivial_map` | Never |
| `to_object()` | `_trivial_map` | Never |
| `to_tracking_radec()` | **Not in base** — too telescope-specific | Always — coordinate source varies per telescope |
| `to_exposure_id()` | **Not in base** — encoding varies | Always — each telescope has its own ID scheme |
| `to_datetime_begin/end()` | **Not in base** — fallback chains vary | Usually — header keyword names and fallback logic differ |
| `to_day_obs()` | **Not in base** | Usually — date formatting logic varies |

Nickel's translator overrides only the methods with custom logic:

```python
# python/lsst/obs/smalltel/nickel/translator.py
from lsst.obs.smalltel.base_translator import ConfigurableTranslator

class NickelTranslator(ConfigurableTranslator):
    supported_instrument = "Nickel"
    config_dir = "nickel"

    def to_tracking_radec(self):
        """Handle Nickel's stuck-DEC keyword bug."""
        # ~50 lines of existing custom logic
        ...

    def to_exposure_id(self):
        """Nickel-specific days-since-2000 encoding."""
        # ~15 lines of existing custom logic
        ...
```

A telescope with clean FITS headers needs no overrides:

```python
# python/lsst/obs/smalltel/newtel/translator.py
from lsst.obs.smalltel.base_translator import ConfigurableTranslator

class NewTelTranslator(ConfigurableTranslator):
    supported_instrument = "NewTel"
    config_dir = "newtel"
    # No overrides needed — all mappings come from header_map.yaml
```

### 3. obs_smalltel: Per-Telescope YAML Config Files

#### instrument.yaml

```yaml
# instruments/nickel/instrument.yaml
name: Nickel
policyName: Nickel
obsDataPackage: obs_nickel_data           # curated calibrations package (optional)
visit_system: ONE_TO_ONE                  # single exposure = single visit
detector_count: 1

# Observatory location (used by translator for to_location())
location:
  name: "Lick Observatory"
  latitude: 37.3414           # degrees N
  longitude: -121.6429        # degrees W
  elevation: 1283.0           # meters

# Observing night → UT day_obs offset.
# Lick is UTC-8; observations starting at local evening cross into next UT day.
# Set to 1 for western-hemisphere observatories where local night = UT next day.
# Set to 0 for observatories where local night ≈ same UT date (e.g., UTC+8 and east).
day_obs_offset: 1
```

#### camera.yaml

Standard LSST camera format — existing `packages/obs_nickel/camera/nickel.yaml` moves here unchanged.

#### filters.yaml

```yaml
# instruments/nickel/filters.yaml
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

#### header_map.yaml

```yaml
# instruments/nickel/header_map.yaml
const_map:
  boresight_rotation_angle: 0.0   # degrees
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
  object:
    key: OBJECT
    default: UNKNOWN

# Filter name normalization (FITS value → canonical name)
filter_name_map:
  OPEN: clear
  C: clear
  CLEAR: clear
  GP: gp
  "G'": gp
  RP: rp
  "R'": rp
  HALPHA: Halpha

# Observation type classification (FITS OBSTYPE value → standard type)
observation_type_map:
  object: science
  bias: bias
  dflat: flat
  dark: dark
  focus: focus
```

### 4. pipeline_tools: InstrumentPlugin

```python
# packages/pipeline_tools/src/small_tel_tools/instruments/base.py
from abc import ABC, abstractmethod
from pathlib import Path


class InstrumentPlugin(ABC):
    """Operational adapter for a telescope.

    NOT the LSST Instrument class (that lives in obs_smalltel).
    This handles archive access, bootstrap orchestration,
    and default pipeline config paths.
    """

    # --- Identity ---
    name: str                      # "Nickel"
    instrument_class: str          # "lsst.obs.smalltel.nickel.Nickel"
    collection_prefix: str         # "Nickel" — prefix for Butler collections
    skymap_name: str               # "nickelRings-v1"
    skymaps_chain: str             # "skymaps/nickelRings"
    day_obs_offset: int            # 1 for Lick (UTC-8), 0 for eastern observatories

    # --- LSST Stack ---
    obs_package_path: str          # Path to obs_smalltel package root

    # --- Data Access ---
    @abstractmethod
    def fetch_data(self, night: str, dest_dir: Path) -> None:
        """Download raw data for a given observing night."""
        ...

    # --- Repository Setup ---
    @abstractmethod
    def bootstrap(self, repo: Path, config: dict) -> None:
        """Initialize Butler repository: register instrument,
        ingest reference catalogs, create skymap."""
        ...

    # --- Pipeline Defaults ---
    def default_pipeline_configs(self) -> dict[str, Path]:
        """Default pipeline config overrides for this telescope.
        Keys: 'calibrate_image', 'subtract_images', etc.
        Values: paths relative to obs_smalltel/configs/."""
        return {}

    def curated_calibrations_path(self) -> Path | None:
        """Path to curated calibration data (defects, crosstalk)."""
        return None

    def refcat_path(self) -> Path | None:
        """Path to reference catalog repository."""
        return None
```

### 5. pipeline_tools: Core Module Changes

#### CollectionNames parameterization

```python
# core/pipeline.py
class CollectionNames:
    def __init__(self, prefix: str, night: str, run_ts: str | None = None):
        self._prefix = prefix
        self._night = night
        self._ts = run_ts or datetime.now().strftime("%Y%m%dT%H%M%S")

    @property
    def raw_run(self) -> str:
        return f"{self._prefix}/raw/{self._night}/{self._ts}"

    @property
    def calib_out(self) -> str:
        return f"{self._prefix}/calib/{self._night}"

    @property
    def science_parent(self) -> str:
        return f"{self._prefix}/runs/{self._night}/processCcd/{self._ts}"

    # ... all other properties follow same pattern
```

#### Threading plugin through core modules

Each core module function gains a `plugin` parameter:

```python
# core/calibs.py — before
def run(night, config, ...):
    cols = CollectionNames(night)
    run_pipetask(["register-instrument", config.repo, INSTRUMENT])
    ...

# core/calibs.py — after
def run(night, config, plugin: InstrumentPlugin, ...):
    cols = CollectionNames(plugin.collection_prefix, night)
    run_pipetask(["register-instrument", config.repo, plugin.instrument_class])
    ...
```

#### YAML orchestrator reads instrument

```python
# core/run.py — before
def run_pipeline(config_path):
    config = RunConfig.from_yaml(config_path)
    calibs.run(night, config)
    ...

# core/run.py — after
def run_pipeline(config_path):
    config = RunConfig.from_yaml(config_path)
    plugin = get_plugin(config.instrument)  # from registry
    calibs.run(night, config, plugin)
    ...
```

### 6. pipeline_tools: CLI Design

```python
# cli.py
@click.group()
@click.option("--instrument", "-i", default=None,
              help="Instrument name (default: from YAML config)")
@click.pass_context
def cli(ctx, instrument):
    ctx.ensure_object(dict)
    ctx.obj["instrument"] = instrument

@cli.command()
@click.argument("config_path", type=click.Path(exists=True))
@click.pass_context
def run(ctx, config_path):
    """Run full pipeline from YAML config."""
    config = RunConfig.from_yaml(config_path)
    # instrument comes from YAML; CLI flag overrides if present
    instrument_name = ctx.obj["instrument"] or config.instrument
    plugin = get_plugin(instrument_name)
    run_pipeline(config, plugin)

@cli.command()
@click.argument("night")
@click.pass_context
def calibs(ctx, night):
    """Run nightly calibrations."""
    instrument_name = ctx.obj["instrument"]
    if not instrument_name:
        raise click.UsageError(
            "No instrument specified. Use --instrument <name> "
            "or use 'stt run <config.yaml>' with instrument in YAML."
        )
    plugin = get_plugin(instrument_name)
    ...
```

Entry points:

```toml
# packages/pipeline_tools/pyproject.toml
[project.scripts]
stt = "small_tel_tools.cli:main"
nickel = "small_tel_tools.cli:main"     # backwards-compat alias

[project.entry-points."small_tel_tools.instruments"]
nickel = "small_tel_tools.instruments.nickel:NickelPlugin"
```

### 7. Configuration: YAML-Only

The `.env` profile system is removed. All configuration comes from YAML:

```yaml
# scripts/config/2023ixf/pipeline_ps1_template.yaml
instrument: nickel

env:
  REPO: /data/nickel/repo
  STACK_DIR: /opt/lsst
  OBS_SMALLTEL: /path/to/obs_smalltel
  RAW_PARENT_DIR: /data/nickel/raw
  REFCAT_REPO: /data/refcats

object: "2023ixf"
ra: 210.910750
dec: 54.311694
bands: ["r", "i"]

template:
  type: ps1
  size: 0.3

science:
  nights:
    - 20230519
    - 20230521

configs:
  science:
    calibrate_image: nickel/calibrateImage/dense_strict.py
    calibrate_image_fallbacks:
      - nickel/calibrateImage/dense_relaxed.py
      - nickel/calibrateImage/sparse_relaxed.py
  dia:
    subtract_images: nickel/dia/subtractImages.py

options:
  jobs: 6
  skip_calibs: false
  continue_on_error: true
  use_fallbacks: true

lightcurve:
  enabled: true
  y_axis: apparent_mag
  x_axis: days_since_explosion
  explosion_mjd: 60082.75
```

---

## What Adding a New Telescope Requires

### Must provide:

| Component | Format | Effort |
|-----------|--------|--------|
| `instruments/{name}/instrument.yaml` | YAML | 5 min |
| `instruments/{name}/camera.yaml` | YAML (LSST standard) | 30 min |
| `instruments/{name}/filters.yaml` | YAML | 5 min |
| `instruments/{name}/header_map.yaml` | YAML | 20 min |
| `python/lsst/obs/smalltel/{name}/instrument.py` | Python (~15 lines) | 5 min |
| `python/lsst/obs/smalltel/{name}/translator.py` | Python (~10 lines + overrides) | 10 min–2 hours |
| `python/lsst/obs/smalltel/{name}/formatter.py` | Python (~8 lines) | 5 min |
| `small_tel_tools/instruments/{name}.py` | Python (InstrumentPlugin) | 30 min–2 hours |
| Entry points in `pyproject.toml` | TOML (2 lines) | 2 min |

### Does NOT need to write:

- No calibs, science, dia, fphot, lightcurve, transit, coadd, or run module code
- No CLI code
- No collection naming logic
- No executor/BPS code
- No template pipeline code
- No lightcurve extraction code

### Total effort per telescope:

- **Clean FITS headers, familiar with LSST camera YAML format**: ~1 day
- **Quirky headers or custom archive API**: ~2-3 days
- **First-time LSST camera setup (learning curve)**: ~1 week
- **Complex multi-detector camera**: Not supported (out of scope for small-tel)

---

## Detailed Parameterization Plan

Every hardcoded "Nickel" reference in the codebase must be replaced. This section catalogs them exhaustively.

### Category 1: Collection name prefixes (~30 occurrences)

All routed through `CollectionNames(prefix, night)`. The prefix comes from `plugin.collection_prefix`.

| Module | Current pattern | After |
|--------|----------------|-------|
| `pipeline.py:CollectionNames` | `f"Nickel/raw/{night}/..."` | `f"{self._prefix}/raw/{night}/..."` |
| `run.py` | `f"Nickel/runs/{night}/processCcd/*"` | `f"{plugin.collection_prefix}/runs/{night}/processCcd/*"` |
| `run.py` | `f"Nickel/runs/{night}/differentialPhot"` | `f"{plugin.collection_prefix}/runs/{night}/differentialPhot"` |
| `run.py` | `f"Nickel/calib/current,refcats,skymaps/nickelRings"` | `f"{plugin.collection_prefix}/calib/current,refcats,{plugin.skymaps_chain}"` |
| `run.py` | `_discover_fphot_collections`: `f"Nickel/runs/{night}/forcedPhotRaDec/*/{suffix}*"` | Uses `plugin.collection_prefix` |
| `run.py` | `_discover_dia_collections`: `prefix_filter="Nickel/runs/"`, `f"Nickel/runs/{night}/diff/*/run"` | Uses `plugin.collection_prefix` |
| `clean.py` | `"Nickel/runs/*/processCcd/*"` (6+ patterns) | `f"{plugin.collection_prefix}/runs/*/processCcd/*"` |
| `fphot.py` | `f"Nickel/runs/{night}/forcedPhotRaDec/..."` | Via `CollectionNames` |

### Category 2: Butler WHERE clause `instrument='Nickel'` (~18 occurrences)

All replaced with `instrument='{plugin.name}'`.

| Module | Lines | Pattern |
|--------|-------|---------|
| `calibs.py` | 259, 352 | `"instrument='Nickel'"` |
| `science.py` | 124 | `"instrument='Nickel'"` |
| `dia.py` | 45, 179, 223, 413, 431 | `"instrument='Nickel'"` |
| `fphot.py` | 45 | `"instrument='Nickel'"` |
| `coadd.py` | 218 | `"instrument='Nickel'"` |
| `pipeline.py` | 179, 209 | `"instrument='Nickel'"` in coordinate validation |
| `extract_lightcurve.py` | 396 | `"instrument='Nickel'"` |
| `assess_dia_quality.py` | 97, 118 | `"instrument='Nickel'"` |
| `run.py` | multiple | collection discovery functions |

### Category 3: Instrument class path constant (1 definition, ~10 usages)

`INSTRUMENT = "lsst.obs.nickel.Nickel"` → `plugin.instrument_class`

Used in: `register-instrument`, `define-visits`, `write-curated-calibrations`

### Category 4: Skymap references (~8 occurrences)

| Constant | Current | Source |
|----------|---------|--------|
| `SKYMAP_NAME` | `"nickelRings-v1"` | `plugin.skymap_name` |
| `SKYMAPS_CHAIN` | `"skymaps/nickelRings"` | `plugin.skymaps_chain` |
| `ingest_ps1_template.py` | hardcoded `"nickelRings-v1"` | `plugin.skymap_name` (passed as arg) |

### Category 5: Config dataclass fields

| Current field | Renamed to | Source |
|--------------|------------|--------|
| `config.obs_nickel` | `config.obs_package` | YAML `env.OBS_SMALLTEL` |
| `config.pipelines_dir` | Derived from `config.obs_package / "pipelines"` | Same logic, new field name |
| `config.configs_dir` | Derived from `config.obs_package / "configs"` | Same logic, new field name |
| `config.lick_archive_dir` | Removed | Moved to `NickelPlugin.fetch_data()` |
| `config.lick_archive_url` | Removed | Moved to `NickelPlugin` |
| `config.lick_archive_instr` | Removed | Moved to `NickelPlugin` |

### Category 6: Observing night → UT day_obs conversion

`pipeline.py:night_to_day_obs()` currently hardcodes `+1 day` offset (Lick is UTC-8).

**Fix:** Read `day_obs_offset` from `instrument.yaml` via the plugin:

```python
# InstrumentPlugin gains:
day_obs_offset: int  # 1 for Lick (UTC-8), 0 for eastern observatories

# pipeline.py:
def night_to_date_range(night: str, day_obs_offset: int) -> tuple[str, str]:
    """Convert observing night to UT day_obs range for Butler queries."""
    night_date = datetime.strptime(night, "%Y%m%d")
    ut_date = night_date + timedelta(days=day_obs_offset)
    ...
```

### Category 7: Coordinate validation (`find_bad_coord_exposures`)

Currently hardcodes `instrument='Nickel'`. This function becomes generic:
- Accept `plugin` parameter for instrument name in WHERE clause
- The function itself is useful for ANY telescope (coordinate sanity check)
- Nickel's specific stuck-DEC bug is handled in the translator, not here

### Category 8: Curated calibration ingestion

Currently `calibs.py:write_curated_calibrations()` calls Butler's `write-curated-calibrations` with the instrument class. Parameterized:

```python
# Before
run_butler(["write-curated-calibrations", repo, "lsst.obs.nickel.Nickel"])

# After
if plugin.curated_calibrations_path():
    run_butler(["write-curated-calibrations", repo, plugin.instrument_class])
```

Telescopes without curated calibrations skip this step entirely.

### Category 9: Bootstrap

Currently delegates to `00_bootstrap_repo.sh`. The plugin's `bootstrap()` method replaces this:

```python
class NickelPlugin(InstrumentPlugin):
    def bootstrap(self, repo, config):
        """Register Nickel, ingest MONSTER refcat, create nickelRings skymap."""
        run_butler(["create", str(repo)])
        run_butler(["register-instrument", str(repo), self.instrument_class])
        if self.refcat_path():
            run_butler(["register-dataset-type", str(repo), ...])
            # ingest reference catalogs
        run_pipetask([...])  # makeSkyMap with Nickel-specific config
```

Each telescope implements its own bootstrap with its own refcats and skymap config.

---

## Entry Point Conflict Policy

When both `obs_nickel` and `obs_smalltel` are installed, both register translators that match `INSTRUME=Nickel`. LSST's `astro_metadata_translator` will non-deterministically pick one.

**Policy:** `obs_nickel` and `obs_smalltel`'s Nickel translator MUST NOT be installed simultaneously.

- **New Butler repos:** Use `obs_smalltel` only. Do not install `obs_nickel`.
- **Existing Butler repos:** Keep `obs_nickel` installed. The `obs_smalltel` package can be installed but the Nickel translator entry point should be disabled (e.g., install without the Nickel extras, or use a separate venv).
- **Migration path:** When ready to migrate an existing repo, uninstall `obs_nickel`, install `obs_smalltel`, and re-register the instrument: `butler register-instrument <repo> lsst.obs.smalltel.nickel.Nickel --update`.

---

## Modules Not in Main Structure

### `core/clean.py`

Has 14+ hardcoded `"Nickel/"` collection patterns for cleanup operations. Parameterized with `plugin.collection_prefix` like all other modules.

### `pipeline_tools/` subpackage naming

The internal subpackage `small_tel_tools/pipeline_tools/` is renamed to `small_tel_tools/standalone/` to avoid confusion with the parent `packages/pipeline_tools/` directory:

```
packages/pipeline_tools/src/small_tel_tools/
    ...
    standalone/                   # Scripts that run inside LSST stack env
        fetch_archive.py
        ingest_ps1_template.py
        extract_lightcurve.py
        differential_phot.py
```

---

## Migration Plan

### Phase 1: Create obs_smalltel with Nickel

- Build `GenericSmallTelInstrument`, `ConfigurableTranslator`, `GenericRawFormatter` base classes
- Create Nickel YAML configs from existing `obs_nickel` data
- Create thin Nickel subclasses
- Move shared pipeline tasks (`forcedPhotRaDec`, `differentialPhot`, `calibCombine`)
- Move shared pipeline YAMLs (`DRP.yaml`, `DIA.yaml`, etc.)
- Validate: fresh Butler repo with `lsst.obs.smalltel.nickel.Nickel` produces identical outputs

### Phase 2: Refactor data_tools → pipeline_tools

- Rename package: `obs_nickel_data_tools` → `small_tel_tools`
- Rename CLI: `nickel` → `stt` (keep `nickel` alias)
- Implement `InstrumentPlugin` ABC + `NickelPlugin`
- Parameterize all core modules (remove hardcoded "Nickel" strings)
- Remove `.env` profile system — YAML-only configuration
- Simplify `config.py` to read from YAML `env:` section
- Validate: `stt run` produces identical results to current `nickel run`

### Phase 3: Add second instrument

- Create YAML configs + thin Python stubs for new telescope
- Implement `NewTelPlugin` with archive fetcher
- Create example target config
- Validate: full pipeline runs end-to-end for new telescope

### Backwards compatibility

| Item | Approach |
|------|----------|
| `nickel` CLI command | Kept as alias for `stt` |
| Existing Butler repos | Keep `obs_nickel` installed alongside `obs_smalltel` |
| YAML configs missing `instrument:` | Default to `nickel` with deprecation warning |
| `.env` files and `-p` flag | Removed (Phase 2) |
| `from obs_nickel_data_tools...` imports | Break immediately — clean rename, no shim |

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LSST base class API changes | Medium | Pin LSST version, test against stack updates |
| Dynamic translator loading fails | High | Integration test: register + ingest for each instrument |
| Camera YAML format differences | Low | LSST camera YAML is well-documented and stable |
| Pipeline configs not portable | Medium | Use `common/` defaults, per-telescope overrides only when needed |
| Butler migration for existing repos | Low | Don't migrate — keep `obs_nickel` for old repos |
| Entry point conflicts with `obs_nickel` | High | Do NOT install both simultaneously. See "Entry Point Conflict Policy" section above. |

---

## Out of Scope

- Multi-CCD cameras (e.g., DECam, ZTF) — fundamentally different detector geometry
- Non-LSST pipelines — this framework assumes LSST Science Pipelines
- Automated instrument discovery from FITS headers alone — still need per-telescope config
- PyPI publishing — packages are installed from source within the monorepo
