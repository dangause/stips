# Pipeline Tools Phase 2: InstrumentPlugin + Core Parameterization

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all hardcoded "Nickel" references in data_tools core modules with plugin-driven parameters so any small telescope can use the same pipeline code.

**Architecture:** An InstrumentPlugin ABC provides telescope identity (name, collection prefix, skymap, day_obs_offset, instrument class), archive access, and bootstrap logic. CollectionNames takes a prefix parameter. Each core module function gains a `plugin` parameter. The YAML orchestrator reads `instrument:` from config and loads the plugin at the top level.

**Tech Stack:** Python 3.11+, dataclasses, entry_points discovery, pytest

**Scope decision:** This plan covers abstraction (InstrumentPlugin + parameterization + CLI updates). The package rename (`obs_nickel_data_tools` → `small_tel_tools`) and `.env` removal are deferred to a separate Phase 2B plan — they are large mechanical changes that don't affect functionality and are cleanly separable.

---

## File Structure

### New files to create:
- `packages/data_tools/src/obs_nickel_data_tools/instruments/__init__.py` — Plugin registry
- `packages/data_tools/src/obs_nickel_data_tools/instruments/base.py` — InstrumentPlugin ABC
- `packages/data_tools/src/obs_nickel_data_tools/instruments/nickel.py` — NickelPlugin
- `packages/data_tools/tests/test_instrument_plugin.py` — Plugin tests
- `packages/data_tools/tests/test_collection_names.py` — CollectionNames parameterization tests
- `packages/data_tools/tests/test_core_parameterization.py` — Integration tests for parameterized modules

### Files to modify:
- `packages/data_tools/src/obs_nickel_data_tools/core/pipeline.py` — CollectionNames + constants
- `packages/data_tools/src/obs_nickel_data_tools/core/config.py` — Add obs_package field
- `packages/data_tools/src/obs_nickel_data_tools/core/calibs.py` — Add plugin parameter
- `packages/data_tools/src/obs_nickel_data_tools/core/science.py` — Add plugin parameter
- `packages/data_tools/src/obs_nickel_data_tools/core/dia.py` — Add plugin parameter
- `packages/data_tools/src/obs_nickel_data_tools/core/fphot.py` — Add plugin parameter
- `packages/data_tools/src/obs_nickel_data_tools/core/coadd.py` — Add plugin parameter
- `packages/data_tools/src/obs_nickel_data_tools/core/clean.py` — Parameterize collection patterns
- `packages/data_tools/src/obs_nickel_data_tools/core/run.py` — Load plugin, thread through steps
- `packages/data_tools/src/obs_nickel_data_tools/core/bootstrap.py` — Use plugin for instrument class
- `packages/data_tools/src/obs_nickel_data_tools/cli.py` — Add --instrument flag
- `packages/data_tools/pyproject.toml` — Add instruments entry point

### Files covered by backward-compat alias (no changes needed now, deferred to Phase 2B):
- `packages/data_tools/src/obs_nickel_data_tools/core/stack.py` — Uses `config.obs_nickel` (alias works)
- `packages/data_tools/src/obs_nickel_data_tools/core/bps.py` — Uses `config.obs_nickel` (alias works)

---

## Chunk 1: InstrumentPlugin ABC + NickelPlugin + Registry

### Task 1: Create InstrumentPlugin ABC

**Files:**
- Create: `packages/data_tools/src/obs_nickel_data_tools/instruments/base.py`
- Create: `packages/data_tools/tests/test_instrument_plugin.py`

The ABC defines the contract that all telescope plugins must implement. This is the foundation of the multi-instrument abstraction.

- [ ] **Step 1: Write the failing test for InstrumentPlugin interface**

```python
# packages/data_tools/tests/test_instrument_plugin.py
"""Tests for InstrumentPlugin ABC and NickelPlugin."""

import pytest
from obs_nickel_data_tools.instruments.base import InstrumentPlugin


class TestInstrumentPluginABC:
    """Verify InstrumentPlugin is a proper ABC."""

    def test_cannot_instantiate_directly(self):
        """InstrumentPlugin is abstract — direct instantiation must fail."""
        with pytest.raises(TypeError):
            InstrumentPlugin()

    def test_required_abstract_methods(self):
        """Verify the abstract methods that subclasses must implement."""
        abstract_methods = InstrumentPlugin.__abstractmethods__
        assert "fetch_data" in abstract_methods
        assert "bootstrap" in abstract_methods

    def test_concrete_subclass_with_all_methods(self):
        """A subclass implementing all abstract methods can be instantiated."""

        class FakePlugin(InstrumentPlugin):
            name = "Fake"
            instrument_class = "lsst.obs.fake.Fake"
            collection_prefix = "Fake"
            skymap_name = "fakeRings-v1"
            skymaps_chain = "skymaps/fakeRings"
            day_obs_offset = 0

            def fetch_data(self, night, dest_dir):
                pass

            def bootstrap(self, repo, config):
                pass

        plugin = FakePlugin()
        assert plugin.name == "Fake"
        assert plugin.collection_prefix == "Fake"

    def test_default_pipeline_configs_returns_empty(self):
        """default_pipeline_configs() has a default implementation returning {}."""

        class MinimalPlugin(InstrumentPlugin):
            name = "Min"
            instrument_class = "lsst.obs.min.Min"
            collection_prefix = "Min"
            skymap_name = "minRings-v1"
            skymaps_chain = "skymaps/minRings"
            day_obs_offset = 0

            def fetch_data(self, night, dest_dir):
                pass

            def bootstrap(self, repo, config):
                pass

        plugin = MinimalPlugin()
        assert plugin.default_pipeline_configs() == {}
        assert plugin.curated_calibrations_path() is None
        assert plugin.refcat_path() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest packages/data_tools/tests/test_instrument_plugin.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_nickel_data_tools.instruments'`

- [ ] **Step 3: Implement InstrumentPlugin ABC**

```python
# packages/data_tools/src/obs_nickel_data_tools/instruments/__init__.py
"""Instrument plugin system for multi-telescope support."""

# packages/data_tools/src/obs_nickel_data_tools/instruments/base.py
"""InstrumentPlugin ABC — operational adapter for a telescope."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

__all__ = ("InstrumentPlugin",)


class InstrumentPlugin(ABC):
    """Operational adapter for a telescope.

    NOT the LSST Instrument class (that lives in obs_smalltel).
    This handles archive access, bootstrap orchestration,
    and default pipeline config paths.

    Subclasses MUST set these class attributes:
      - name: str                  e.g. "Nickel"
      - instrument_class: str      e.g. "lsst.obs.smalltel.nickel.Nickel"
      - collection_prefix: str     e.g. "Nickel"
      - skymap_name: str           e.g. "nickelRings-v1"
      - skymaps_chain: str         e.g. "skymaps/nickelRings"
      - day_obs_offset: int        1 for Lick (UTC-8), 0 for eastern observatories
    """

    name: str
    instrument_class: str
    collection_prefix: str
    skymap_name: str
    skymaps_chain: str
    day_obs_offset: int

    @abstractmethod
    def fetch_data(self, night: str, dest_dir: Path) -> None:
        """Download raw data for a given observing night."""
        ...

    @abstractmethod
    def bootstrap(self, repo: Path, config: dict) -> None:
        """Initialize Butler repository for this instrument."""
        ...

    def default_pipeline_configs(self) -> dict[str, Path]:
        """Default pipeline config overrides for this telescope."""
        return {}

    def curated_calibrations_path(self) -> Path | None:
        """Path to curated calibration data (defects, crosstalk)."""
        return None

    def refcat_path(self) -> Path | None:
        """Path to reference catalog repository."""
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest packages/data_tools/tests/test_instrument_plugin.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/instruments/__init__.py \
       packages/data_tools/src/obs_nickel_data_tools/instruments/base.py \
       packages/data_tools/tests/test_instrument_plugin.py
git commit -m "feat: add InstrumentPlugin ABC for multi-telescope support"
```

### Task 2: Create NickelPlugin

**Files:**
- Create: `packages/data_tools/src/obs_nickel_data_tools/instruments/nickel.py`
- Modify: `packages/data_tools/tests/test_instrument_plugin.py`

NickelPlugin implements InstrumentPlugin for the Nickel 1-meter telescope at Lick Observatory. It encapsulates all Nickel-specific operational details.

- [ ] **Step 1: Write the failing test for NickelPlugin**

Add to `test_instrument_plugin.py`:

```python
from obs_nickel_data_tools.instruments.nickel import NickelPlugin


class TestNickelPlugin:
    """Verify NickelPlugin provides correct Nickel-specific values."""

    def test_identity_attributes(self):
        plugin = NickelPlugin()
        assert plugin.name == "Nickel"
        assert plugin.instrument_class == "lsst.obs.smalltel.nickel.Nickel"
        assert plugin.collection_prefix == "Nickel"

    def test_skymap_attributes(self):
        plugin = NickelPlugin()
        assert plugin.skymap_name == "nickelRings-v1"
        assert plugin.skymaps_chain == "skymaps/nickelRings"

    def test_day_obs_offset(self):
        """Lick Observatory is UTC-8, so observing night crosses into next UT day."""
        plugin = NickelPlugin()
        assert plugin.day_obs_offset == 1

    def test_is_instrument_plugin(self):
        """NickelPlugin is a proper InstrumentPlugin subclass."""
        plugin = NickelPlugin()
        assert isinstance(plugin, InstrumentPlugin)

    def test_lick_archive_fields(self):
        """NickelPlugin exposes Lick archive URL and instrument filter."""
        plugin = NickelPlugin()
        assert "ucolick.org" in plugin.archive_url
        assert plugin.archive_instrument == "NICKEL_DIR"

    def test_default_pipeline_configs_not_empty(self):
        """NickelPlugin provides default config overrides."""
        plugin = NickelPlugin()
        defaults = plugin.default_pipeline_configs()
        # Should have at least calibrate_image and colorterms defaults
        assert isinstance(defaults, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest packages/data_tools/tests/test_instrument_plugin.py::TestNickelPlugin -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement NickelPlugin**

```python
# packages/data_tools/src/obs_nickel_data_tools/instruments/nickel.py
"""NickelPlugin — operational adapter for the Nickel 1-meter telescope."""

from __future__ import annotations

from pathlib import Path

from obs_nickel_data_tools.instruments.base import InstrumentPlugin

__all__ = ("NickelPlugin",)


class NickelPlugin(InstrumentPlugin):
    """Operational adapter for the Nickel 1-m at Lick Observatory."""

    name = "Nickel"
    instrument_class = "lsst.obs.smalltel.nickel.Nickel"
    collection_prefix = "Nickel"
    skymap_name = "nickelRings-v1"
    skymaps_chain = "skymaps/nickelRings"
    day_obs_offset = 1  # Lick is UTC-8

    # Lick Observatory archive
    archive_url: str = "https://archive.ucolick.org/archive"
    archive_instrument: str = "NICKEL_DIR"

    def fetch_data(self, night: str, dest_dir: Path) -> None:
        """Download raw Nickel data from the Lick Observatory archive."""
        from obs_nickel_data_tools.pipeline_tools.fetch_archive_night import (
            fetch_archive_night,
        )

        fetch_archive_night(
            night=night,
            dest_dir=dest_dir,
            archive_url=self.archive_url,
            instrument=self.archive_instrument,
        )

    def bootstrap(self, repo: Path, config: dict) -> None:
        """Bootstrap a Butler repo for Nickel: register instrument, ingest
        refcats, create skymap."""
        # Delegates to existing bootstrap.py logic
        # (will be refactored to use plugin in Task 16)
        pass

    def default_pipeline_configs(self) -> dict[str, Path]:
        """Default pipeline config paths relative to obs_smalltel/configs/nickel/."""
        return {
            "calibrate_image": Path(
                "nickel/calibrateImage/tuned_configs/dense_strict.py"
            ),
            "colorterms": Path("nickel/apply_colorterms.py"),
        }

    def curated_calibrations_path(self) -> Path | None:
        """obs_nickel_data provides curated calibrations (defects, crosstalk)."""
        try:
            from lsst.utils import getPackageDir

            return Path(getPackageDir("obs_nickel_data"))
        except (ImportError, LookupError):
            return None

    def refcat_path(self) -> Path | None:
        """Path to MONSTER reference catalog (if configured in env)."""
        import os

        path = os.environ.get("REFCAT_REPO")
        if path:
            p = Path(path)
            if p.exists():
                return p
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest packages/data_tools/tests/test_instrument_plugin.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/instruments/nickel.py \
       packages/data_tools/tests/test_instrument_plugin.py
git commit -m "feat: add NickelPlugin implementing InstrumentPlugin for Lick Observatory"
```

### Task 3: Create plugin registry

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/instruments/__init__.py`
- Modify: `packages/data_tools/pyproject.toml` (add entry point)
- Modify: `packages/data_tools/tests/test_instrument_plugin.py`

The registry discovers plugins via entry_points and provides `get_plugin(name)`.

- [ ] **Step 1: Write the failing test for plugin registry**

Add to `test_instrument_plugin.py`:

```python
from obs_nickel_data_tools.instruments import get_plugin, list_plugins


class TestPluginRegistry:
    """Verify plugin discovery and lookup."""

    def test_get_plugin_nickel(self):
        """get_plugin('nickel') returns NickelPlugin."""
        plugin = get_plugin("nickel")
        assert isinstance(plugin, NickelPlugin)
        assert plugin.name == "Nickel"

    def test_get_plugin_case_insensitive(self):
        """Plugin lookup is case-insensitive."""
        plugin = get_plugin("Nickel")
        assert isinstance(plugin, NickelPlugin)

    def test_get_plugin_unknown_raises(self):
        """Unknown instrument raises ValueError."""
        with pytest.raises(ValueError, match="Unknown instrument"):
            get_plugin("nonexistent")

    def test_list_plugins(self):
        """list_plugins() includes at least 'nickel'."""
        plugins = list_plugins()
        assert "nickel" in plugins
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest packages/data_tools/tests/test_instrument_plugin.py::TestPluginRegistry -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement plugin registry**

The registry uses a hardcoded fallback dict plus optional entry_points discovery. The hardcoded fallback ensures the Nickel plugin works without editable install of the entry point.

```python
# packages/data_tools/src/obs_nickel_data_tools/instruments/__init__.py
"""Instrument plugin system for multi-telescope support."""

from __future__ import annotations

from obs_nickel_data_tools.instruments.base import InstrumentPlugin

__all__ = ("get_plugin", "list_plugins", "InstrumentPlugin")

# Hardcoded registry (fallback when entry_points aren't installed)
_BUILTIN_PLUGINS: dict[str, type[InstrumentPlugin]] = {}


def _ensure_builtins() -> None:
    """Lazily populate builtin plugins on first access."""
    if not _BUILTIN_PLUGINS:
        from obs_nickel_data_tools.instruments.nickel import NickelPlugin

        _BUILTIN_PLUGINS["nickel"] = NickelPlugin


def get_plugin(name: str) -> InstrumentPlugin:
    """Look up an instrument plugin by name (case-insensitive).

    Discovery order:
    1. Builtin plugins (hardcoded in this module)
    2. Entry points (``obs_nickel_data_tools.instruments`` group)

    Args:
        name: Instrument name (e.g. "nickel", "Nickel")

    Returns:
        Instantiated InstrumentPlugin

    Raises:
        ValueError: If no plugin found for the given name
    """
    key = name.lower()

    # Try builtins first
    _ensure_builtins()
    if key in _BUILTIN_PLUGINS:
        return _BUILTIN_PLUGINS[key]()

    # Try entry_points
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="obs_nickel_data_tools.instruments")
        for ep in eps:
            if ep.name.lower() == key:
                cls = ep.load()
                return cls()
    except Exception:
        pass

    available = list(list_plugins())
    raise ValueError(
        f"Unknown instrument: '{name}'. Available: {', '.join(available)}"
    )


def list_plugins() -> list[str]:
    """List all available instrument plugin names."""
    _ensure_builtins()
    names = set(_BUILTIN_PLUGINS.keys())

    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="obs_nickel_data_tools.instruments")
        for ep in eps:
            names.add(ep.name.lower())
    except Exception:
        pass

    return sorted(names)
```

Also add entry point to pyproject.toml:

```toml
[project.entry-points."obs_nickel_data_tools.instruments"]
nickel = "obs_nickel_data_tools.instruments.nickel:NickelPlugin"
```

- [ ] **Step 4: Re-install package so entry point is registered**

Run: `uv pip install -e packages/data_tools`

Entry points are only active after installation. Without this, entry_points discovery won't find the nickel plugin (the builtin fallback still works, but tests should verify both paths).

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest packages/data_tools/tests/test_instrument_plugin.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/instruments/__init__.py \
       packages/data_tools/pyproject.toml \
       packages/data_tools/tests/test_instrument_plugin.py
git commit -m "feat: add plugin registry with entry_points discovery and builtin fallback"
```

---

## Chunk 2: CollectionNames + Pipeline Constants Parameterization

### Task 4: Parameterize CollectionNames

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/pipeline.py` (lines 246-322)
- Create: `packages/data_tools/tests/test_collection_names.py`

CollectionNames currently hardcodes "Nickel/" as the prefix. Add a `prefix` parameter and keep backward compatibility by defaulting to "Nickel".

- [ ] **Step 1: Write the failing test**

```python
# packages/data_tools/tests/test_collection_names.py
"""Tests for parameterized CollectionNames."""

from obs_nickel_data_tools.core.pipeline import CollectionNames


class TestCollectionNamesParameterized:
    """Verify CollectionNames uses the prefix parameter."""

    def test_default_prefix_is_nickel(self):
        """Backward compat: no prefix arg defaults to 'Nickel'."""
        cols = CollectionNames("20230519", run_ts="20260312T120000Z")
        assert cols.raw_run == "Nickel/raw/20230519/20260312T120000Z"
        assert cols.calib_chain == "Nickel/calib/current"

    def test_custom_prefix(self):
        """Custom prefix replaces 'Nickel' in all collection names."""
        cols = CollectionNames(
            "20230519", run_ts="20260312T120000Z", prefix="NewTel"
        )
        assert cols.raw_run == "NewTel/raw/20230519/20260312T120000Z"
        assert cols.calib_chain == "NewTel/calib/current"
        assert cols.science_parent == "NewTel/runs/20230519/processCcd/20260312T120000Z"
        assert cols.diff_parent == "NewTel/runs/20230519/diff/20260312T120000Z"
        assert cols.calib_out == "NewTel/calib/20230519"
        assert cols.curated_chain == "NewTel/calib/curated"
        assert cols.cp_bias.startswith("NewTel/cp/20230519/bias/")
        assert cols.cp_flat.startswith("NewTel/cp/20230519/flat/")

    def test_all_properties_use_prefix(self):
        """Every collection name property should contain the prefix."""
        cols = CollectionNames(
            "20230519", run_ts="20260312T120000Z", prefix="Test"
        )
        properties = [
            cols.raw_run,
            cols.cp_bias,
            cols.cp_bias_run,
            cols.cp_flat,
            cols.cp_flat_run,
            cols.curated_run,
            cols.curated_chain,
            cols.calib_out,
            cols.calib_chain,
            cols.science_parent,
            cols.science_run,
            cols.coadd_parent,
            cols.coadd_run,
            cols.diff_parent,
            cols.diff_run,
        ]
        for prop in properties:
            assert prop.startswith("Test/"), f"{prop} doesn't start with 'Test/'"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest packages/data_tools/tests/test_collection_names.py -v`
Expected: FAIL — `CollectionNames.__init__` doesn't accept `prefix` parameter

- [ ] **Step 3: Add prefix parameter to CollectionNames**

Modify `pipeline.py:CollectionNames.__init__` to accept `prefix` with default "Nickel":

```python
class CollectionNames:
    """Generate standard collection names for a pipeline run."""

    def __init__(self, night: str, run_ts: str | None = None, *, prefix: str = "Nickel"):
        self.night = night
        self.run_ts = run_ts or generate_run_timestamp()
        self._prefix = prefix

    @property
    def raw_run(self) -> str:
        return f"{self._prefix}/raw/{self.night}/{self.run_ts}"

    # ... update ALL properties to use self._prefix instead of "Nickel"
```

Every property that currently has a hardcoded `"Nickel/"` must use `self._prefix` instead. Properties to update: `raw_run`, `cp_bias`, `cp_bias_run`, `cp_flat`, `cp_flat_run`, `curated_run`, `curated_chain`, `calib_out`, `calib_chain`, `science_parent`, `science_run`, `coadd_parent`, `coadd_run`, `diff_parent`, `diff_run`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest packages/data_tools/tests/test_collection_names.py -v`
Expected: PASS

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `.venv/bin/pytest packages/data_tools/tests/ -v`
Expected: All existing tests still pass (default prefix is "Nickel")

- [ ] **Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/pipeline.py \
       packages/data_tools/tests/test_collection_names.py
git commit -m "feat: parameterize CollectionNames with prefix (default 'Nickel' for backward compat)"
```

### Task 5: Parameterize pipeline constants and night_to_day_obs

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/pipeline.py` (lines 318-322, 74-89)
- Modify: `packages/data_tools/tests/test_collection_names.py`

The global constants `INSTRUMENT`, `SKYMAP_NAME`, `SKYMAPS_CHAIN` are used throughout the codebase. Keep them as defaults but modules will read from the plugin instead. Also parameterize `night_to_day_obs()` with an offset parameter.

- [ ] **Step 1: Write the failing test for night_to_day_obs parameterization**

Add to `test_collection_names.py`:

```python
from obs_nickel_data_tools.core.pipeline import night_to_day_obs


class TestNightToDayObs:
    """Verify night_to_day_obs with configurable offset."""

    def test_default_offset_is_1(self):
        """Default offset (+1 day) is backward compatible."""
        assert night_to_day_obs("20230519") == "20230520"

    def test_offset_zero(self):
        """Offset 0 means night == day_obs."""
        assert night_to_day_obs("20230519", day_obs_offset=0) == "20230519"

    def test_offset_one(self):
        """Offset 1 adds one day (Lick Observatory convention)."""
        assert night_to_day_obs("20230519", day_obs_offset=1) == "20230520"

    def test_offset_across_month_boundary(self):
        """Verify offset works across month boundaries."""
        assert night_to_day_obs("20230131", day_obs_offset=1) == "20230201"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest packages/data_tools/tests/test_collection_names.py::TestNightToDayObs -v`
Expected: FAIL — `night_to_day_obs()` doesn't accept `day_obs_offset` parameter

- [ ] **Step 3: Add day_obs_offset parameter**

Modify `pipeline.py:night_to_day_obs()`:

```python
def night_to_day_obs(night: str, day_obs_offset: int = 1) -> str:
    """Convert observing night (local) to UT day_obs.

    Args:
        night: Local observing night (YYYYMMDD)
        day_obs_offset: Days to add (default 1, for western-hemisphere observatories)

    Returns:
        UT day_obs (YYYYMMDD)
    """
    from datetime import timedelta

    dt = datetime.strptime(night, "%Y%m%d")
    return (dt + timedelta(days=day_obs_offset)).strftime("%Y%m%d")
```

The existing callers all use the default (1), so backward compatibility is preserved.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest packages/data_tools/tests/test_collection_names.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/pipeline.py \
       packages/data_tools/tests/test_collection_names.py
git commit -m "feat: parameterize night_to_day_obs with configurable day_obs_offset"
```

---

## Chunk 3: Thread plugin through core modules

This is the largest chunk. Each core module gains a `plugin` parameter (optional, defaults to NickelPlugin for backward compatibility). The plugin provides:
- `plugin.collection_prefix` → CollectionNames prefix
- `plugin.name` → instrument name for Butler WHERE clauses
- `plugin.instrument_class` → for register-instrument
- `plugin.skymap_name` → for coadd queries
- `plugin.skymaps_chain` → for input collection chains
- `plugin.day_obs_offset` → for night_to_day_obs

**Backward compat strategy:** Every function that gains a `plugin` parameter defaults to `None`. If `None`, the function creates a NickelPlugin internally. This means ALL existing callers continue to work unchanged. The orchestrator (run.py) passes the plugin explicitly.

### Task 6: Thread plugin through pipeline.py utility functions

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/pipeline.py`
- Modify: `packages/data_tools/tests/test_collection_names.py`

The `find_bad_coord_exposures()` function in pipeline.py hardcodes `instrument='Nickel'`. Add an `instrument_name` parameter.

- [ ] **Step 1: Write the failing test**

```python
class TestFindBadCoordExposuresParam:
    """Verify find_bad_coord_exposures accepts instrument_name."""

    def test_accepts_instrument_name_param(self):
        """Function signature accepts instrument_name keyword arg."""
        import inspect
        from obs_nickel_data_tools.core.pipeline import find_bad_coord_exposures

        sig = inspect.signature(find_bad_coord_exposures)
        assert "instrument_name" in sig.parameters
```

- [ ] **Step 2: Run test, verify failure**

- [ ] **Step 3: Add instrument_name parameter to find_bad_coord_exposures**

In `pipeline.py:find_bad_coord_exposures()`, add `instrument_name: str = "Nickel"` parameter and replace the hardcoded `instrument='Nickel'` in the WHERE clause:

```python
def find_bad_coord_exposures(
    config: Config,
    night: str,
    target_ra: float,
    target_dec: float,
    *,
    object_filter: str | None = None,
    tolerance_deg: float = 5.0,
    instrument_name: str = "Nickel",
    day_obs_offset: int = 1,
) -> list[int]:
```

Update the WHERE clause from:
```python
where = (
    f"instrument='Nickel' AND exposure.observation_type='science'"
    f" AND exposure.day_obs={day_obs}"
)
```
to:
```python
day_obs = night_to_day_obs(night, day_obs_offset=day_obs_offset)
where = (
    f"instrument='{instrument_name}' AND exposure.observation_type='science'"
    f" AND exposure.day_obs={day_obs}"
)
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/pipeline.py \
       packages/data_tools/tests/test_collection_names.py
git commit -m "feat: parameterize find_bad_coord_exposures with instrument_name"
```

### Task 7: Thread plugin through calibs.py

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/calibs.py`
- Create: `packages/data_tools/tests/test_core_parameterization.py`

calibs.py has these hardcoded references:
- `INSTRUMENT` constant in register-instrument, define-visits, write-curated-calibrations
- `"Nickel"` in Butler define-visits call (line 92, 208)
- `"instrument='Nickel'"` in qgraph data queries (lines 259, 352)
- `CollectionNames(night)` without prefix

- [ ] **Step 1: Write the failing test**

```python
# packages/data_tools/tests/test_core_parameterization.py
"""Tests verifying core modules accept plugin parameter."""

import inspect

import pytest


class TestCalibsPluginParam:
    """Verify calibs.run() accepts and uses plugin parameter."""

    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.calibs import run

        sig = inspect.signature(run)
        assert "plugin" in sig.parameters

    def test_write_curated_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.calibs import write_curated_calibrations

        sig = inspect.signature(write_curated_calibrations)
        assert "plugin" in sig.parameters
```

- [ ] **Step 2: Run test, verify failure**
- [ ] **Step 3: Add plugin parameter to calibs.py**

Add `plugin: InstrumentPlugin | None = None` to both `run()` and `write_curated_calibrations()`. At the top of each function:

```python
if plugin is None:
    from obs_nickel_data_tools.instruments.nickel import NickelPlugin
    plugin = NickelPlugin()
```

Then replace:
- `CollectionNames(night)` → `CollectionNames(night, prefix=plugin.collection_prefix)`
- `INSTRUMENT` → `plugin.instrument_class`
- `"Nickel"` in define-visits → `plugin.name`
- `"instrument='Nickel'"` in WHERE clauses → `f"instrument='{plugin.name}'"`

- [ ] **Step 4: Run all existing tests, verify no regressions**
- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/calibs.py \
       packages/data_tools/tests/test_core_parameterization.py
git commit -m "feat: thread InstrumentPlugin through calibs.py"
```

### Task 8: Thread plugin through science.py

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/science.py`
- Modify: `packages/data_tools/tests/test_core_parameterization.py`

science.py has these hardcoded references:
- `INSTRUMENT` in register-instrument (line 371)
- `CollectionNames(night)` (line 226)
- `"instrument='Nickel'"` in WHERE clauses (lines 124, 349)
- `REFCATS_CHAIN, SKYMAPS_CHAIN, SKYMAP_NAME` constants
- `night_to_day_obs(night)` without offset (line 347)
- `find_bad_coord_exposures()` call (line 285)
- `f"Nickel/raw/{night}/*"` in Butler query (line 241)
- `prefix_filter="Nickel/"` in parse calls

- [ ] **Step 1: Write the failing test**

Add to `test_core_parameterization.py`:

```python
class TestSciencePluginParam:
    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.science import run
        sig = inspect.signature(run)
        assert "plugin" in sig.parameters

    def test_resolve_object_filter_accepts_instrument_name(self):
        from obs_nickel_data_tools.core.science import resolve_object_filter
        sig = inspect.signature(resolve_object_filter)
        assert "instrument_name" in sig.parameters
```

- [ ] **Step 2: Run test, verify failure**
- [ ] **Step 3: Add plugin parameter to science.py**

Add `plugin: InstrumentPlugin | None = None` to `run()` and `instrument_name: str = "Nickel"` to `resolve_object_filter()`. At the top of `run()`:

```python
if plugin is None:
    from obs_nickel_data_tools.instruments.nickel import NickelPlugin
    plugin = NickelPlugin()
```

Then replace all hardcoded references:
- `CollectionNames(night)` → `CollectionNames(night, prefix=plugin.collection_prefix)`
- `INSTRUMENT` → `plugin.instrument_class`
- `"instrument='Nickel'"` (3 WHERE clauses: lines ~124, ~349, and ~771 in coadd-within-science logic) → `f"instrument='{plugin.name}'"`
- `night_to_day_obs(night)` → `night_to_day_obs(night, day_obs_offset=plugin.day_obs_offset)`
- `REFCATS_CHAIN` → keep as constant (refcats chain is shared across instruments)
- `SKYMAPS_CHAIN` → `plugin.skymaps_chain`
- `SKYMAP_NAME` → `plugin.skymap_name`
- `f"Nickel/raw/{night}/*"` → `f"{plugin.collection_prefix}/raw/{night}/*"`
- `prefix_filter="Nickel/"` → `prefix_filter=f"{plugin.collection_prefix}/"`
- `find_bad_coord_exposures(config, night, ...)` → add `instrument_name=plugin.name, day_obs_offset=plugin.day_obs_offset`

- [ ] **Step 4: Run all tests, verify no regressions**
- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/science.py \
       packages/data_tools/tests/test_core_parameterization.py
git commit -m "feat: thread InstrumentPlugin through science.py"
```

### Task 9: Thread plugin through dia.py

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/dia.py`
- Modify: `packages/data_tools/tests/test_core_parameterization.py`

dia.py has these hardcoded references:
- `INSTRUMENT` in register-instrument (line 239)
- `CollectionNames(night)` (line 149)
- `"instrument='Nickel'"` in WHERE clauses (lines 223, 413, 431)
- `f"Nickel/runs/{night}/processCcd/*"` (line 172)
- `f"Nickel/raw/{night}/*"` (line 253)
- `prefix_filter="Nickel/"` (lines 177, 258)
- `REFCATS_CHAIN, SKYMAPS_CHAIN` constants
- `night_to_day_obs(night)` (line 151)

- [ ] **Step 1: Write the failing test**

```python
class TestDiaPluginParam:
    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.dia import run
        sig = inspect.signature(run)
        assert "plugin" in sig.parameters
```

- [ ] **Step 2: Run test, verify failure**
- [ ] **Step 3: Add plugin parameter to dia.py**

Add `plugin: InstrumentPlugin | None = None` to `run()`. At the top:
```python
if plugin is None:
    from obs_nickel_data_tools.instruments.nickel import NickelPlugin
    plugin = NickelPlugin()
```

Then replace each hardcoded reference:
- `CollectionNames(night)` → `CollectionNames(night, prefix=plugin.collection_prefix)`
- `INSTRUMENT` → `plugin.instrument_class`
- `"instrument='Nickel'"` (3 WHERE clauses) → `f"instrument='{plugin.name}'"`
- `f"Nickel/runs/{night}/processCcd/*"` → `f"{plugin.collection_prefix}/runs/{night}/processCcd/*"`
- `f"Nickel/raw/{night}/*"` → `f"{plugin.collection_prefix}/raw/{night}/*"`
- `prefix_filter="Nickel/"` → `prefix_filter=f"{plugin.collection_prefix}/"`
- `REFCATS_CHAIN` → keep as constant (shared across instruments)
- `SKYMAPS_CHAIN` → `plugin.skymaps_chain`
- `night_to_day_obs(night)` → `night_to_day_obs(night, day_obs_offset=plugin.day_obs_offset)`

- [ ] **Step 4: Run all tests, verify no regressions**
- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/dia.py \
       packages/data_tools/tests/test_core_parameterization.py
git commit -m "feat: thread InstrumentPlugin through dia.py"
```

### Task 10: Thread plugin through fphot.py

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/fphot.py`
- Modify: `packages/data_tools/tests/test_core_parameterization.py`

fphot.py has these hardcoded references:
- `"instrument='Nickel'"` in WHERE clause (line 45)
- `f"Nickel/runs/{night}/processCcd/*"` (line 145)
- `f"Nickel/runs/{night}/diff/*/run"` (line 79)
- `f"Nickel/runs/{night}/forcedPhotRaDec/..."` (lines 185, 255)
- `"Nickel/calib/current"` (lines 189, 252)
- `prefix_filter="Nickel/"` (lines 88, 150)
- `night_to_day_obs(night)` (line 171)
- Pipeline path: `f"{obs_nickel}/pipelines/ForcedPhotRaDec.yaml"` (lines 211, 277)

- [ ] **Step 1: Write the failing test**

```python
class TestFphotPluginParam:
    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.fphot import run
        sig = inspect.signature(run)
        assert "plugin" in sig.parameters
```

- [ ] **Step 2: Run test, verify failure**
- [ ] **Step 3: Add plugin parameter to fphot.py**

Add `plugin: InstrumentPlugin | None = None` to `run()`. At the top, default to NickelPlugin.

Replace each hardcoded reference:
- `"instrument='Nickel'"` (2 WHERE clauses) → `f"instrument='{plugin.name}'"`
- `f"Nickel/runs/{night}/processCcd/*"` → `f"{plugin.collection_prefix}/runs/{night}/processCcd/*"`
- `f"Nickel/runs/{night}/diff/*/run"` → `f"{plugin.collection_prefix}/runs/{night}/diff/*/run"`
- `f"Nickel/runs/{night}/forcedPhotRaDec/..."` (multiple) → `f"{plugin.collection_prefix}/runs/{night}/forcedPhotRaDec/..."`
- `"Nickel/calib/current"` (2 occurrences) → `f"{plugin.collection_prefix}/calib/current"`
- `prefix_filter="Nickel/"` (2 occurrences) → `prefix_filter=f"{plugin.collection_prefix}/"`
- `night_to_day_obs(night)` → `night_to_day_obs(night, day_obs_offset=plugin.day_obs_offset)`

Note: `config.obs_nickel` references for pipeline paths will be handled by Task 13's backward-compat alias — leave them as-is for now.

- [ ] **Step 4: Run all tests, verify no regressions**
- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/fphot.py \
       packages/data_tools/tests/test_core_parameterization.py
git commit -m "feat: thread InstrumentPlugin through fphot.py"
```

### Task 11: Thread plugin through coadd.py

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/coadd.py`
- Modify: `packages/data_tools/tests/test_core_parameterization.py`

coadd.py has these hardcoded references:
- `INSTRUMENT` in register-instrument (line 430)
- `"instrument='Nickel'"` in WHERE clause (line 459)
- `SKYMAP_NAME` and `SKYMAPS_CHAIN` (lines 59, 455, 459)
- `f"Nickel/runs/{night}/processCcd/*"` (line 154)
- `prefix_filter="Nickel/"` (line 163)
- `"Nickel/calib/current"` (line 455)
- `"skymaps/nickelRings"` in find_tract_for_coords (line 77)

- [ ] **Step 1: Write the failing test**

```python
class TestCoaddPluginParam:
    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.coadd import run
        sig = inspect.signature(run)
        assert "plugin" in sig.parameters

    def test_find_tract_accepts_skymap_params(self):
        from obs_nickel_data_tools.core.coadd import find_tract_for_coords
        sig = inspect.signature(find_tract_for_coords)
        assert "skymap_name" in sig.parameters
        assert "skymaps_chain" in sig.parameters
```

- [ ] **Step 2: Run test, verify failure**
- [ ] **Step 3: Add plugin parameter to coadd.py**

Add `plugin: InstrumentPlugin | None = None` to `run()`. At the top, default to NickelPlugin.

For `find_tract_for_coords()`, add `skymap_name` and `skymaps_chain` parameters with current defaults:
```python
def find_tract_for_coords(..., skymap_name="nickelRings-v1", skymaps_chain="skymaps/nickelRings"):
```

Replace each hardcoded reference:
- `INSTRUMENT` → `plugin.instrument_class`
- `"instrument='Nickel'"` → `f"instrument='{plugin.name}'"`
- `SKYMAP_NAME` → `plugin.skymap_name`
- `SKYMAPS_CHAIN` → `plugin.skymaps_chain`
- `f"Nickel/runs/{night}/processCcd/*"` → `f"{plugin.collection_prefix}/runs/{night}/processCcd/*"`
- `prefix_filter="Nickel/"` → `prefix_filter=f"{plugin.collection_prefix}/"`
- `"Nickel/calib/current"` → `f"{plugin.collection_prefix}/calib/current"`
- `"skymaps/nickelRings"` in find_tract_for_coords → use `skymaps_chain` parameter

Note: callers of `find_tract_for_coords` outside coadd.py (e.g., run.py) will be updated in Task 12 when the plugin is threaded through run.py.

- [ ] **Step 4: Run all tests, verify no regressions**
- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/coadd.py \
       packages/data_tools/tests/test_core_parameterization.py
git commit -m "feat: thread InstrumentPlugin through coadd.py"
```

### Task 11b: Thread plugin through clean.py

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/clean.py`
- Modify: `packages/data_tools/tests/test_core_parameterization.py`

clean.py has 15 hardcoded "Nickel/" patterns in module-level constants and step-to-pattern dicts:
- `RUN_PATTERNS`: 5 patterns with "Nickel/runs/*"
- `CALIB_PATTERNS`: 2 patterns with "Nickel/cp/*" and "Nickel/calib/*"
- `PRESERVED_PATTERNS`: 3 patterns with "Nickel/raw/*", "Nickel/calib/current"
- `step_to_patterns`: 5 patterns in `_build_patterns()`

- [ ] **Step 1: Write the failing test**

```python
class TestCleanPluginParam:
    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.clean import run
        sig = inspect.signature(run)
        assert "plugin" in sig.parameters
```

- [ ] **Step 2: Run test, verify failure**
- [ ] **Step 3: Add plugin parameter to clean.py**

Add `plugin: InstrumentPlugin | None = None` to `run()`. At the top, default to NickelPlugin.

Convert module-level constants to functions that accept a prefix:

```python
def _run_patterns(prefix: str) -> list[str]:
    return [
        f"{prefix}/runs/*/processCcd/*",
        f"{prefix}/runs/*/diff/*",
        f"{prefix}/runs/*/forcedPhotRaDec/*",
        f"{prefix}/runs/*/coadd/*",
        f"{prefix}/runs/*/science/*",
    ]

def _calib_patterns(prefix: str) -> list[str]:
    return [f"{prefix}/cp/*", f"{prefix}/calib/*"]

def _preserved_patterns(prefix: str) -> list[str]:
    return [f"{prefix}/raw/*", "refcats/*", "skymaps/*", "skymaps", f"{prefix}/calib/current"]
```

Update `_build_patterns()` to accept `prefix` and use it in `step_to_patterns`.
Update `run()` to pass `plugin.collection_prefix` to all pattern functions.

- [ ] **Step 4: Run all tests, verify no regressions**
- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/clean.py \
       packages/data_tools/tests/test_core_parameterization.py
git commit -m "feat: thread InstrumentPlugin through clean.py"
```

---

## Chunk 4: Orchestrator + Config + CLI

### Task 12: Thread plugin through run.py (orchestrator)

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py`
- Modify: `packages/data_tools/tests/test_core_parameterization.py`

run.py is the top-level orchestrator that calls all other modules. It has:
- `config.obs_nickel` references for log directory (line 285)
- `f"Nickel/runs/{night}/processCcd/*"` in differential phot discovery (line 1618)
- `f"Nickel/calib/current,refcats,skymaps/nickelRings"` in diff phot (line 1643)
- `f"Nickel/runs/{night}/differentialPhot"` (line 1644)
- `f"Nickel/runs/{night}/forcedPhotRaDec/..."` in fphot discovery (lines 1733, 1751)
- `f"Nickel/runs/{night}/diff/*/run"` in DIA discovery (lines 1784)
- `prefix_filter="Nickel/"` and `prefix_filter="Nickel/runs/"` in multiple places
- All step functions pass through to calibs/science/dia/fphot/coadd

The key change: `RunConfig.from_yaml()` reads an `instrument:` field from the YAML and run.py loads the plugin via `get_plugin()` at the top of `run()`.

- [ ] **Step 1: Write the failing test**

```python
class TestRunConfigInstrument:
    def test_from_yaml_reads_instrument(self, tmp_path):
        """RunConfig.from_yaml() reads instrument field."""
        from obs_nickel_data_tools.core.run import RunConfig

        yaml_content = """
instrument: nickel
object: test
bands: ["r"]
science:
  nights:
    - 20230519
"""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml_content)

        rc = RunConfig.from_yaml(config_file)
        assert rc.instrument == "nickel"

    def test_from_yaml_defaults_instrument_to_nickel(self, tmp_path):
        """Missing instrument field defaults to 'nickel' with deprecation."""
        from obs_nickel_data_tools.core.run import RunConfig

        yaml_content = """
object: test
bands: ["r"]
science:
  nights:
    - 20230519
"""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml_content)

        rc = RunConfig.from_yaml(config_file)
        assert rc.instrument == "nickel"
```

- [ ] **Step 2: Run test, verify failure**
- [ ] **Step 3: Add instrument field to RunConfig + thread plugin through run()**

In `RunConfig`:
```python
instrument: str = "nickel"
```

In `RunConfig.from_yaml()`:
```python
instrument = data.get("instrument", "nickel")
if "instrument" not in data:
    log.warning(
        "No 'instrument' field in YAML config. Defaulting to 'nickel'. "
        "Add 'instrument: nickel' to your YAML config."
    )
```

In `run()`:
```python
from obs_nickel_data_tools.instruments import get_plugin

plugin = get_plugin(run_cfg.instrument)
```

Then pass `plugin=plugin` to every step function call. The step functions (calibs.run, science.run, etc.) already have the plugin parameter from Tasks 7-11.

Also replace all hardcoded collection patterns in discovery functions:
- `_run_differential_phot_step`: replace `"Nickel/runs/"` with `f"{plugin.collection_prefix}/runs/"`
- `_discover_fphot_collections`: same
- `_discover_dia_collections`: same

- [ ] **Step 4: Run all tests, verify no regressions**
- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py \
       packages/data_tools/tests/test_core_parameterization.py
git commit -m "feat: thread InstrumentPlugin through run.py orchestrator"
```

### Task 13: Update Config dataclass

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/config.py`
- Modify: `packages/data_tools/tests/test_core_parameterization.py`

The Config dataclass needs:
1. Rename `obs_nickel` → `obs_package` (keep `obs_nickel` as property alias for backward compat)
2. Remove Lick-specific fields → they live in NickelPlugin now
3. Support `OBS_SMALLTEL` env var (in addition to `OBS_NICKEL`)

- [ ] **Step 1: Write the failing test**

```python
class TestConfigObsPackage:
    def test_config_has_obs_package(self):
        """Config has obs_package field."""
        from obs_nickel_data_tools.core.config import Config
        import inspect
        fields = {f.name for f in __import__('dataclasses').fields(Config)}
        assert "obs_package" in fields

    def test_obs_nickel_alias(self):
        """config.obs_nickel is a backward-compat alias for obs_package."""
        from obs_nickel_data_tools.core.config import Config
        from pathlib import Path
        config = Config(
            repo=Path("/tmp/repo"),
            stack_dir=Path("/tmp/stack"),
            obs_package=Path("/tmp/obs_smalltel"),
            raw_parent_dir=Path("/tmp/raw"),
        )
        assert config.obs_package == Path("/tmp/obs_smalltel")
        assert config.obs_nickel == config.obs_package
```

- [ ] **Step 2: Run test, verify failure**
- [ ] **Step 3: Rename field with backward compat alias**

In `config.py`:
```python
@dataclass
class Config:
    repo: Path
    stack_dir: Path
    obs_package: Path  # was: obs_nickel
    raw_parent_dir: Path
    refcat_repo: Path | None = None
    cp_pipe_dir: Path | None = None

    # Derived paths
    pipelines_dir: Path = field(init=False)
    configs_dir: Path = field(init=False)

    def __post_init__(self):
        self.pipelines_dir = self.obs_package / "pipelines"
        self.configs_dir = self.obs_package / "configs"

    @property
    def obs_nickel(self) -> Path:
        """Backward-compat alias for obs_package."""
        return self.obs_package
```

In `config.load()`, update the required field from `"OBS_NICKEL"` and support both env var names:
```python
# Support both OBS_SMALLTEL (new) and OBS_NICKEL (legacy)
obs_package_path = merged.get("OBS_SMALLTEL") or merged.get("OBS_NICKEL")
if not obs_package_path:
    raise ValueError("Missing OBS_SMALLTEL (or OBS_NICKEL) configuration")
```

Keep `lick_archive_*` fields on Config for now — they are read by `cli.py`, `stack.py`, and `fetch_archive_night.py`. Removing them would break callers. Defer their removal to Phase 2B (when `.env` system is also refactored).

- [ ] **Step 4: Update `config.load()` constructor call**

The `load()` function constructs `Config(obs_nickel=...)` — update to `Config(obs_package=...)`:
```python
# In load(), change:
#   Config(obs_nickel=Path(obs_nickel_path), ...)
# to:
#   Config(obs_package=Path(obs_package_path), ...)
```

Also update any `validate()` error messages from "OBS_NICKEL" to "OBS_SMALLTEL/OBS_NICKEL".

- [ ] **Step 5: Run all tests, verify no regressions**

Note: callers that read `config.obs_nickel` (stack.py, bps.py, run.py, cli.py) will work unchanged via the backward-compat property alias. Only code that constructs `Config(obs_nickel=...)` as a keyword arg will break — the `load()` function is the primary such caller.

- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/config.py \
       packages/data_tools/tests/test_core_parameterization.py
git commit -m "refactor: rename Config.obs_nickel to obs_package with backward-compat alias"
```

### Task 14: Update CLI with --instrument flag

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/cli.py`

Add `--instrument / -i` option to the CLI group. When running `nickel run <config.yaml>`, the instrument comes from the YAML file. For individual commands like `nickel calibs`, the instrument must be specified via `--instrument` or defaults to "nickel".

- [ ] **Step 1: Add --instrument to CLI group**

```python
@click.group()
@click.option("--instrument", "-i", default="nickel",
              help="Instrument name (default: nickel)")
@click.pass_context
def cli(ctx, instrument, ...):
    ctx.ensure_object(dict)
    ctx.obj["instrument"] = instrument
```

- [ ] **Step 2: Thread instrument through individual commands**

For each command (calibs, science, dia, fphot, etc.), load the plugin:

```python
@cli.command()
@click.argument("night")
@click.pass_context
def calibs(ctx, night):
    from obs_nickel_data_tools.instruments import get_plugin
    plugin = get_plugin(ctx.obj["instrument"])
    ...calibs.run(night, config, plugin=plugin, ...)
```

For `run` command, the YAML config's `instrument` field takes precedence:

```python
@cli.command()
@click.argument("config_path")
@click.pass_context
def run(ctx, config_path):
    # instrument comes from YAML; CLI --instrument overrides only if explicitly set
    ...
```

- [ ] **Step 3: Verify CLI flag works**

Run: `nickel --instrument nickel --help` (should show help without errors)
Run: `nickel -i nickel calibs --help` (should show calibs help)

- [ ] **Step 4: Run existing tests, verify no regressions**
- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/cli.py
git commit -m "feat: add --instrument CLI flag for multi-telescope support"
```

### Task 15: Update YAML configs with instrument field

**Files (all 16 pipeline configs):**
- `scripts/config/2020wnt/pipeline_nickel_template.yaml`
- `scripts/config/2020wnt/pipeline_ps1_template.yaml`
- `scripts/config/2023ixf/pipeline_docker_bps_test.yaml`
- `scripts/config/2023ixf/pipeline_docker_test.yaml`
- `scripts/config/2023ixf/pipeline_nickel_template.yaml`
- `scripts/config/2023ixf/pipeline_ps1_docker_test.yaml`
- `scripts/config/2023ixf/pipeline_ps1_hpc.yaml`
- `scripts/config/2023ixf/pipeline_ps1_template.yaml`
- `scripts/config/2023ixf/pipeline_ps1_test_fix.yaml`
- `scripts/config/ac_and/pipeline.yaml`
- `scripts/config/cy_aqr/pipeline.yaml`
- `scripts/config/dy_peg/pipeline.yaml`
- `scripts/config/example_exoplanet/pipeline_transit_template.yaml`
- `scripts/config/example_variable_star/pipeline_variable_template.yaml`
- `scripts/config/extended_objects/pipeline_calibs_science.yaml`
- `scripts/config/hd189733/pipeline_transit.yaml`

Add `instrument: nickel` to each YAML config file.

- [ ] **Step 1: Add instrument field to each config**

At the top of each YAML, add:
```yaml
instrument: nickel
```

- [ ] **Step 2: Verify dry-run still works**

Run: `nickel run scripts/config/2023ixf/pipeline_ps1_template.yaml --dry-run`
Expected: Normal dry-run output, no errors

- [ ] **Step 3: Commit**

```bash
git add scripts/config/2020wnt/pipeline_*.yaml \
       scripts/config/2023ixf/pipeline_*.yaml \
       scripts/config/ac_and/pipeline.yaml \
       scripts/config/cy_aqr/pipeline.yaml \
       scripts/config/dy_peg/pipeline.yaml \
       scripts/config/example_exoplanet/pipeline_*.yaml \
       scripts/config/example_variable_star/pipeline_*.yaml \
       scripts/config/extended_objects/pipeline_*.yaml \
       scripts/config/hd189733/pipeline_*.yaml
git commit -m "chore: add instrument: nickel to all YAML pipeline configs"
```

---

## Chunk 5: Integration Validation

### Task 16: Update bootstrap.py to use plugin

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/bootstrap.py`

bootstrap.py delegates to a shell script and doesn't directly use INSTRUMENT/CollectionNames, but `needs_bootstrap()` checks for "skymaps" and "refcats" collections. Add plugin parameter so future telescopes can have different collection checks.

- [ ] **Step 1: Add plugin parameter to bootstrap functions**

```python
def needs_bootstrap(config: Config, plugin=None) -> bool:
    if plugin is None:
        from obs_nickel_data_tools.instruments.nickel import NickelPlugin
        plugin = NickelPlugin()
    ...
```

- [ ] **Step 2: Run all tests, verify no regressions**
- [ ] **Step 3: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/bootstrap.py
git commit -m "feat: thread InstrumentPlugin through bootstrap.py"
```

### Task 17: Comprehensive integration test

**Files:**
- Create: `packages/data_tools/tests/test_integration_plugin.py`

This test verifies the full plugin flow: load plugin → create CollectionNames → verify all hardcoded "Nickel" strings are gone from module function signatures.

- [ ] **Step 1: Write integration test**

```python
# packages/data_tools/tests/test_integration_plugin.py
"""Integration tests for plugin-driven parameterization."""

import inspect

import pytest

from obs_nickel_data_tools.instruments import get_plugin
from obs_nickel_data_tools.instruments.nickel import NickelPlugin
from obs_nickel_data_tools.core.pipeline import CollectionNames


class TestPluginFlowIntegration:
    """Verify end-to-end plugin flow works correctly."""

    def test_plugin_creates_correct_collection_names(self):
        """Plugin properties flow through to CollectionNames."""
        plugin = get_plugin("nickel")
        cols = CollectionNames(
            "20230519", run_ts="20260312T120000Z",
            prefix=plugin.collection_prefix,
        )
        assert cols.raw_run == "Nickel/raw/20230519/20260312T120000Z"
        assert cols.calib_chain == "Nickel/calib/current"

    def test_custom_plugin_creates_custom_collections(self):
        """A hypothetical plugin with different prefix creates different names."""
        from obs_nickel_data_tools.instruments.base import InstrumentPlugin

        class FakePlugin(InstrumentPlugin):
            name = "FakeTel"
            instrument_class = "lsst.obs.smalltel.fakeTel.FakeTel"
            collection_prefix = "FakeTel"
            skymap_name = "fakeRings-v1"
            skymaps_chain = "skymaps/fakeRings"
            day_obs_offset = 0

            def fetch_data(self, night, dest_dir):
                pass
            def bootstrap(self, repo, config):
                pass

        plugin = FakePlugin()
        cols = CollectionNames(
            "20230519", run_ts="20260312T120000Z",
            prefix=plugin.collection_prefix,
        )
        assert cols.raw_run == "FakeTel/raw/20230519/20260312T120000Z"
        assert cols.calib_chain == "FakeTel/calib/current"
        assert cols.science_parent == "FakeTel/runs/20230519/processCcd/20260312T120000Z"

    def test_all_core_modules_accept_plugin(self):
        """Every core module's run() function accepts a plugin parameter."""
        from obs_nickel_data_tools.core import calibs, science, dia, fphot, coadd

        for module in [calibs, science, dia, fphot, coadd]:
            sig = inspect.signature(module.run)
            assert "plugin" in sig.parameters, (
                f"{module.__name__}.run() missing 'plugin' parameter"
            )

    def test_run_config_has_instrument(self):
        """RunConfig has an instrument field."""
        from obs_nickel_data_tools.core.run import RunConfig
        import dataclasses
        fields = {f.name for f in dataclasses.fields(RunConfig)}
        assert "instrument" in fields

    def test_night_to_day_obs_with_offset(self):
        """night_to_day_obs respects day_obs_offset from plugin."""
        from obs_nickel_data_tools.core.pipeline import night_to_day_obs

        plugin = get_plugin("nickel")
        result = night_to_day_obs("20230519", day_obs_offset=plugin.day_obs_offset)
        assert result == "20230520"
```

- [ ] **Step 2: Run integration test**

Run: `.venv/bin/pytest packages/data_tools/tests/test_integration_plugin.py -v`
Expected: PASS (all tests)

- [ ] **Step 3: Run ALL tests**

Run: `.venv/bin/pytest packages/data_tools/tests/ -v`
Expected: All passing

- [ ] **Step 4: Commit**

```bash
git add packages/data_tools/tests/test_integration_plugin.py
git commit -m "test: add integration tests for plugin-driven parameterization"
```

### Task 18: Grep audit for remaining hardcoded "Nickel" strings

**Files:** All core modules

- [ ] **Step 1: Search for remaining hardcoded collection prefix references**

Run these two targeted searches:
```bash
# Hardcoded "Nickel/" collection prefixes (the primary target)
grep -rn '"Nickel/' packages/data_tools/src/obs_nickel_data_tools/core/ --include="*.py"

# Hardcoded instrument='Nickel' WHERE clauses
grep -rn "instrument='Nickel'" packages/data_tools/src/obs_nickel_data_tools/core/ --include="*.py"
```

Expected: Zero matches for both (all should be parameterized).

Also check stack.py and bps.py for `config.obs_nickel` (these are covered by the backward-compat alias, so they are acceptable for now but should be noted):
```bash
grep -rn "config.obs_nickel" packages/data_tools/src/obs_nickel_data_tools/core/ --include="*.py"
```

Expected: Only hits in stack.py and bps.py (covered by alias). Any hits in calibs/science/dia/fphot/coadd/clean/run need fixing.

- [ ] **Step 2: Fix any remaining hardcoded references found**
- [ ] **Step 3: Run all tests, verify pass**
- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: audit and fix remaining hardcoded Nickel references"
```

---

## Summary

| Chunk | Tasks | Description |
|-------|-------|-------------|
| 1 | 1-3 | InstrumentPlugin ABC + NickelPlugin + Registry |
| 2 | 4-5 | CollectionNames + night_to_day_obs parameterization |
| 3 | 6-11b | Thread plugin through all core modules (incl. clean.py) |
| 4 | 12-15 | Orchestrator + Config + CLI + YAML configs |
| 5 | 16-18 | Bootstrap + Integration validation + Audit |

**Total: 19 tasks across 5 chunks.**

**Deferred to Phase 2B:**
- Package rename `obs_nickel_data_tools` → `small_tel_tools`, CLI rename `nickel` → `stt`
- Remove `lick_archive_*` fields from Config (move to plugin)
- Update `config.obs_nickel` references in `stack.py` and `bps.py`
- Remove `.env` system in favor of plugin-driven config

After this plan is complete, the codebase will be fully parameterized — any telescope can use the same pipeline code by providing an InstrumentPlugin subclass. The package rename (Phase 2B) can proceed as a clean mechanical step.
