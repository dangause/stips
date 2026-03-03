# LSST-Native Differential Photometry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace standalone `differential_phot.py` with an LSST PipelineTask that reads pre-computed aperture fluxes from `calibrateImage` star catalogs.

**Architecture:** Single consolidation-level PipelineTask (`DifferentialPhotTask`) at `dimensions=(instrument,)` that reads all `single_visit_star_unstandardized` SourceCatalogs, selects comparison stars, computes differential flux ratios, and outputs a normalized lightcurve as ArrowAstropy table. Follows `ForcedPhotLightcurveTask` pattern.

**Tech Stack:** LSST pipe.base (PipelineTask, PipelineTaskConfig, PipelineTaskConnections), lsst.afw.table (SourceCatalog), lsst.geom (SpherePoint, degrees), astropy.table, numpy, matplotlib.

---

### Task 1: Connections and Config classes

**Files:**
- Create: `packages/obs_nickel/python/lsst/obs/nickel/tasks/differentialPhot.py`
- Test: `packages/obs_nickel/tests/test_differential_phot.py`

**Step 1: Write the failing test**

```python
# test_differential_phot.py
#!/usr/bin/env python3
"""Unit tests for DifferentialPhotTask."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "data_tools/src"),
)

# Test that classes can be imported
def test_imports():
    from lsst.obs.nickel.tasks.differentialPhot import (
        DifferentialPhotConfig,
        DifferentialPhotConnections,
        DifferentialPhotTask,
    )
    assert DifferentialPhotTask is not None


def test_config_defaults():
    from lsst.obs.nickel.tasks.differentialPhot import DifferentialPhotConfig

    config = DifferentialPhotConfig()
    assert config.apertureRadius == 17.0
    assert config.nComparisons == 10
    assert config.minComparisons == 3
    assert config.matchRadius == 2.0
    assert config.minRelMag == 0.5
    assert config.maxRelMag == 4.0
    assert config.minDetectionFraction == 0.8
    assert config.bandFilter == ""


def test_config_validation_bad_radius():
    from lsst.obs.nickel.tasks.differentialPhot import DifferentialPhotConfig

    config = DifferentialPhotConfig()
    config.apertureRadius = 5.0  # Not in valid set
    with pytest.raises(Exception):
        config.validate()
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/obs_nickel/tests/test_differential_phot.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# differentialPhot.py
"""LSST PipelineTask for differential aperture photometry.

Reads pre-computed aperture fluxes from calibrateImage star catalogs,
selects a comparison star ensemble, and produces differential flux
lightcurves. Designed for bright star time-domain science (exoplanet
transits, variable stars) where PSF-fitting fails.
"""

from __future__ import annotations

import logging

import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase
from lsst.pipe.base import connectionTypes as ct

__all__ = [
    "DifferentialPhotConfig",
    "DifferentialPhotTask",
]

_LOG = logging.getLogger(__name__)

# Valid aperture radii from calibrateImage (best_calib_t071.py)
VALID_APERTURE_RADII = [3.0, 6.0, 9.0, 12.0, 17.0, 25.0, 35.0, 50.0, 70.0]


class DifferentialPhotConnections(
    pipeBase.PipelineTaskConnections,
    dimensions=("instrument",),
    defaultTemplates={
        "starCatalogName": "single_visit_star_unstandardized",
        "visitTableName": "preliminary_visit_table",
        "outputName": "differential_phot_lightcurve",
    },
):
    """Connections for DifferentialPhotTask."""

    starCatalogs = ct.Input(
        doc="Star catalogs from calibrateImage with aperture fluxes.",
        name="{starCatalogName}",
        storageClass="SourceCatalog",
        dimensions=("instrument", "visit", "detector"),
        multiple=True,
        deferLoad=True,
    )
    visitTable = ct.Input(
        doc="Visit table with MJD and metadata.",
        name="{visitTableName}",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
    )
    lightcurveTable = ct.Output(
        doc="Differential photometry lightcurve.",
        name="{outputName}_table",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
    )
    lightcurvePlot = ct.Output(
        doc="Differential photometry lightcurve plot.",
        name="{outputName}_plot",
        storageClass="Plot",
        dimensions=("instrument",),
    )


class DifferentialPhotConfig(
    pipeBase.PipelineTaskConfig,
    pipelineConnections=DifferentialPhotConnections,
):
    """Configuration for DifferentialPhotTask."""

    targetRa = pexConfig.Field(
        dtype=float,
        default=0.0,
        doc="Target right ascension in degrees.",
    )
    targetDec = pexConfig.Field(
        dtype=float,
        default=0.0,
        doc="Target declination in degrees.",
    )
    apertureRadius = pexConfig.Field(
        dtype=float,
        default=17.0,
        doc=(
            "Aperture radius in pixels. Must match one of the radii "
            "configured in calibrateImage: "
            + ", ".join(str(r) for r in VALID_APERTURE_RADII)
        ),
    )
    nComparisons = pexConfig.Field(
        dtype=int,
        default=10,
        doc="Maximum number of comparison stars to use.",
    )
    minComparisons = pexConfig.Field(
        dtype=int,
        default=3,
        doc="Minimum comparison stars required per visit (fewer = skip visit).",
    )
    matchRadius = pexConfig.Field(
        dtype=float,
        default=2.0,
        doc="Cross-match radius in arcseconds.",
    )
    minRelMag = pexConfig.Field(
        dtype=float,
        default=0.5,
        doc="Comparison stars must be at least this many mag fainter than target.",
    )
    maxRelMag = pexConfig.Field(
        dtype=float,
        default=4.0,
        doc="Comparison stars must be no more than this many mag fainter than target.",
    )
    minDetectionFraction = pexConfig.Field(
        dtype=float,
        default=0.8,
        doc="Comparison stars must be detected in at least this fraction of visits.",
    )
    bandFilter = pexConfig.Field(
        dtype=str,
        default="",
        doc="Only process visits in this band (empty = all bands).",
    )
    targetName = pexConfig.Field(
        dtype=str,
        default="",
        doc="Target name for plot title.",
    )

    def validate(self):
        super().validate()
        if self.apertureRadius not in VALID_APERTURE_RADII:
            raise pexConfig.FieldValidationError(
                self.__class__.apertureRadius,
                self,
                f"apertureRadius={self.apertureRadius} not in valid set: "
                f"{VALID_APERTURE_RADII}",
            )
        if self.nComparisons < self.minComparisons:
            raise pexConfig.FieldValidationError(
                self.__class__.nComparisons,
                self,
                "nComparisons must be >= minComparisons",
            )


class DifferentialPhotTask(pipeBase.PipelineTask):
    """Compute differential aperture photometry from calibrateImage catalogs."""

    ConfigClass = DifferentialPhotConfig
    _DefaultName = "differentialPhot"
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/obs_nickel/tests/test_differential_phot.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add packages/obs_nickel/python/lsst/obs/nickel/tasks/differentialPhot.py \
       packages/obs_nickel/tests/test_differential_phot.py
git commit -m "feat(diffphot): add DifferentialPhotTask connections and config"
```

---

### Task 2: Cross-match and comparison star selection

**Files:**
- Modify: `packages/obs_nickel/python/lsst/obs/nickel/tasks/differentialPhot.py`
- Modify: `packages/obs_nickel/tests/test_differential_phot.py`

**Step 1: Write the failing tests**

```python
def _make_mock_catalog(n_sources, rng, center_ra=300.18, center_dec=22.71,
                       fov_deg=0.1, flux_range=(1e6, 1e9)):
    """Create a mock SourceCatalog-like list of dicts for testing."""
    ras = center_ra + rng.uniform(-fov_deg / 2, fov_deg / 2, n_sources)
    decs = center_dec + rng.uniform(-fov_deg / 2, fov_deg / 2, n_sources)
    fluxes = rng.uniform(flux_range[0], flux_range[1], n_sources)
    flux_errs = fluxes * 0.01  # 1% errors
    return [
        {
            "coord_ra": np.radians(ra),
            "coord_dec": np.radians(dec),
            "base_CircularApertureFlux_17_0_instFlux": flux,
            "base_CircularApertureFlux_17_0_instFluxErr": flux_err,
            "base_PixelFlags_flag_saturatedCenter": False,
            "base_PixelFlags_flag_edge": False,
            "deblend_nChild": 0,
        }
        for ra, dec, flux, flux_err in zip(ras, decs, fluxes, flux_errs)
    ]


def test_find_target():
    from lsst.obs.nickel.tasks.differentialPhot import _find_target

    rng = np.random.default_rng(42)
    sources = _make_mock_catalog(20, rng)
    # Plant target at known position
    target_ra, target_dec = 300.182, 22.711
    sources[5]["coord_ra"] = np.radians(target_ra)
    sources[5]["coord_dec"] = np.radians(target_dec)

    idx = _find_target(sources, target_ra, target_dec, match_radius_arcsec=5.0)
    assert idx == 5


def test_find_target_no_match():
    from lsst.obs.nickel.tasks.differentialPhot import _find_target

    rng = np.random.default_rng(42)
    sources = _make_mock_catalog(20, rng, center_ra=100.0, center_dec=50.0)
    idx = _find_target(sources, 300.0, 22.0, match_radius_arcsec=5.0)
    assert idx is None


def test_select_comparisons():
    from lsst.obs.nickel.tasks.differentialPhot import _select_comparisons

    rng = np.random.default_rng(42)
    sources = _make_mock_catalog(30, rng)
    target_idx = 0
    # Make target the brightest
    sources[0]["base_CircularApertureFlux_17_0_instFlux"] = 2e9

    comps = _select_comparisons(
        sources, target_idx, aperture_col="base_CircularApertureFlux_17_0_instFlux",
        n_max=6, min_rel_mag=0.5, max_rel_mag=4.0,
    )
    assert len(comps) <= 6
    assert target_idx not in comps
    # All comparisons should be fainter than target
    target_flux = sources[target_idx]["base_CircularApertureFlux_17_0_instFlux"]
    for ci in comps:
        assert sources[ci]["base_CircularApertureFlux_17_0_instFlux"] < target_flux
```

**Step 2: Run tests to verify they fail**

Run: `pytest packages/obs_nickel/tests/test_differential_phot.py::test_find_target -v`
Expected: FAIL with `ImportError: cannot import name '_find_target'`

**Step 3: Write implementation**

Add to `differentialPhot.py` (module-level helper functions):

```python
import numpy as np


def _angular_separation_arcsec(ra1_deg, dec1_deg, ra2_rad, dec2_rad):
    """Compute angular separation in arcseconds.

    Parameters
    ----------
    ra1_deg, dec1_deg : float
        First position in degrees.
    ra2_rad, dec2_rad : float
        Second position in radians (as stored in SourceCatalog).
    """
    ra1 = np.radians(ra1_deg)
    dec1 = np.radians(dec1_deg)
    cos_sep = (
        np.sin(dec1) * np.sin(dec2_rad)
        + np.cos(dec1) * np.cos(dec2_rad) * np.cos(ra1 - ra2_rad)
    )
    cos_sep = np.clip(cos_sep, -1.0, 1.0)
    return np.degrees(np.arccos(cos_sep)) * 3600.0


def _find_target(sources, target_ra_deg, target_dec_deg, match_radius_arcsec=2.0):
    """Find the target star in a source catalog by position.

    Returns index into sources list, or None if no match within radius.
    """
    best_idx = None
    best_sep = match_radius_arcsec
    for i, src in enumerate(sources):
        sep = _angular_separation_arcsec(
            target_ra_deg, target_dec_deg,
            src["coord_ra"], src["coord_dec"],
        )
        if sep < best_sep:
            best_sep = sep
            best_idx = i
    return best_idx


def _select_comparisons(sources, target_idx, aperture_col,
                        n_max=10, min_rel_mag=0.5, max_rel_mag=4.0):
    """Select comparison stars from a source catalog.

    Returns list of indices into sources.
    """
    target_flux = sources[target_idx][aperture_col]
    if target_flux <= 0:
        return []

    # Convert magnitude bounds to flux bounds
    # fainter by min_rel_mag mag → flux * 10^(-min_rel_mag/2.5)
    max_flux = target_flux * 10 ** (-min_rel_mag / 2.5)
    min_flux = target_flux * 10 ** (-max_rel_mag / 2.5)

    candidates = []
    for i, src in enumerate(sources):
        if i == target_idx:
            continue
        flux = src[aperture_col]
        if flux <= 0 or flux < min_flux or flux > max_flux:
            continue
        # Skip flagged sources
        if src.get("base_PixelFlags_flag_saturatedCenter", False):
            continue
        if src.get("base_PixelFlags_flag_edge", False):
            continue
        if src.get("deblend_nChild", 0) > 0:
            continue
        candidates.append((i, flux))

    # Sort by flux descending (brightest first = highest SNR)
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in candidates[:n_max]]
```

**Step 4: Run tests**

Run: `pytest packages/obs_nickel/tests/test_differential_phot.py -v -k "target or comparison"`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add packages/obs_nickel/python/lsst/obs/nickel/tasks/differentialPhot.py \
       packages/obs_nickel/tests/test_differential_phot.py
git commit -m "feat(diffphot): add target finding and comparison star selection"
```

---

### Task 3: Differential flux computation

**Files:**
- Modify: `packages/obs_nickel/python/lsst/obs/nickel/tasks/differentialPhot.py`
- Modify: `packages/obs_nickel/tests/test_differential_phot.py`

**Step 1: Write the failing tests**

```python
def test_compute_differential_flux():
    from lsst.obs.nickel.tasks.differentialPhot import _compute_differential_flux

    target_flux = 1e9
    target_err = 1e7
    comp_fluxes = [5e8, 3e8, 2e8]
    comp_errs = [5e6, 3e6, 2e6]

    diff, diff_err = _compute_differential_flux(
        target_flux, target_err, comp_fluxes, comp_errs,
    )
    expected_diff = target_flux / sum(comp_fluxes)
    assert abs(diff - expected_diff) < 1e-10
    assert diff_err > 0


def test_compute_differential_flux_empty_comps():
    from lsst.obs.nickel.tasks.differentialPhot import _compute_differential_flux

    diff, diff_err = _compute_differential_flux(1e9, 1e7, [], [])
    assert diff is None
    assert diff_err is None


def test_normalize_lightcurve():
    from lsst.obs.nickel.tasks.differentialPhot import _normalize_lightcurve

    fluxes = np.array([0.98, 1.0, 1.02, 0.99, 1.01])
    errors = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
    norm_flux, norm_err = _normalize_lightcurve(fluxes, errors)
    assert abs(np.median(norm_flux) - 1.0) < 1e-10
    assert len(norm_err) == 5


def test_transit_signal_preserved():
    """Verify a synthetic transit dip survives differential photometry."""
    from lsst.obs.nickel.tasks.differentialPhot import (
        _compute_differential_flux,
        _normalize_lightcurve,
    )

    rng = np.random.default_rng(42)
    n_visits = 100
    # Simulate target with 5% transit dip in middle 20 visits
    target_base = 1e9
    target_fluxes = np.full(n_visits, target_base)
    target_fluxes[40:60] *= 0.95  # 5% dip
    target_fluxes += rng.normal(0, 1e7, n_visits)  # 1% noise
    target_errs = np.full(n_visits, 1e7)

    # Simulate 5 comparison stars (constant)
    comp_base = [5e8, 3e8, 4e8, 2e8, 6e8]
    comp_sum_base = sum(comp_base)

    diffs = []
    diff_errs = []
    for i in range(n_visits):
        comp_f = [c + rng.normal(0, c * 0.005) for c in comp_base]
        comp_e = [c * 0.005 for c in comp_base]
        d, de = _compute_differential_flux(
            target_fluxes[i], target_errs[i], comp_f, comp_e,
        )
        diffs.append(d)
        diff_errs.append(de)

    norm, norm_err = _normalize_lightcurve(np.array(diffs), np.array(diff_errs))

    oot = np.concatenate([norm[:35], norm[65:]])  # out of transit
    it = norm[40:60]  # in transit
    assert np.median(oot) > np.median(it)
    depth = 1 - np.median(it) / np.median(oot)
    assert abs(depth - 0.05) < 0.02  # Within 2% of injected 5% dip
```

**Step 2: Run tests to verify they fail**

Run: `pytest packages/obs_nickel/tests/test_differential_phot.py -v -k "differential or normalize or transit_signal"`
Expected: FAIL with `ImportError`

**Step 3: Write implementation**

Add to `differentialPhot.py`:

```python
def _compute_differential_flux(target_flux, target_err, comp_fluxes, comp_errs):
    """Compute differential flux = target / sum(comparisons).

    Returns (diff_flux, diff_err) or (None, None) if no comparisons.
    """
    if not comp_fluxes:
        return None, None
    comp_sum = sum(comp_fluxes)
    if comp_sum <= 0:
        return None, None
    diff = target_flux / comp_sum
    # Error propagation: sigma_diff = diff * sqrt((sigma_t/t)^2 + (sigma_c/c_sum)^2)
    comp_err_sum = np.sqrt(sum(e**2 for e in comp_errs))
    diff_err = abs(diff) * np.sqrt(
        (target_err / target_flux) ** 2 + (comp_err_sum / comp_sum) ** 2
    )
    return diff, diff_err


def _normalize_lightcurve(diff_fluxes, diff_errors):
    """Normalize differential flux so median = 1.0.

    Returns (norm_flux, norm_err).
    """
    median = np.median(diff_fluxes)
    if median <= 0:
        median = np.mean(diff_fluxes[diff_fluxes > 0]) if np.any(diff_fluxes > 0) else 1.0
    return diff_fluxes / median, diff_errors / median
```

**Step 4: Run tests**

Run: `pytest packages/obs_nickel/tests/test_differential_phot.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add packages/obs_nickel/python/lsst/obs/nickel/tasks/differentialPhot.py \
       packages/obs_nickel/tests/test_differential_phot.py
git commit -m "feat(diffphot): add differential flux computation and normalization"
```

---

### Task 4: Full runQuantum implementation

**Files:**
- Modify: `packages/obs_nickel/python/lsst/obs/nickel/tasks/differentialPhot.py`
- Modify: `packages/obs_nickel/tests/test_differential_phot.py`

**Step 1: Write the failing test**

```python
def test_process_catalogs():
    """Test the core catalog processing logic (no Butler needed)."""
    from lsst.obs.nickel.tasks.differentialPhot import DifferentialPhotTask

    rng = np.random.default_rng(42)
    n_visits = 50

    # Build mock catalogs: 15 sources per visit, target at index 0
    target_ra, target_dec = 300.182, 22.711
    catalogs = []
    visit_ids = list(range(90000000, 90000000 + n_visits))
    for v in range(n_visits):
        sources = _make_mock_catalog(15, rng)
        # Plant target
        sources[0]["coord_ra"] = np.radians(target_ra)
        sources[0]["coord_dec"] = np.radians(target_dec)
        sources[0]["base_CircularApertureFlux_17_0_instFlux"] = 2e9 + rng.normal(0, 2e7)
        sources[0]["base_CircularApertureFlux_17_0_instFluxErr"] = 2e7
        catalogs.append((visit_ids[v], sources))

    # Build mock visit table
    from astropy.table import Table
    visit_table = Table({
        "visit": visit_ids,
        "expMidptMJD": np.linspace(60890.0, 60890.2, n_visits),
        "band": ["b"] * n_visits,
    })

    result = DifferentialPhotTask._process_catalogs_static(
        catalogs=catalogs,
        visit_table=visit_table,
        target_ra=target_ra,
        target_dec=target_dec,
        aperture_radius=17.0,
        match_radius=2.0,
        n_comparisons=6,
        min_comparisons=3,
        min_rel_mag=0.5,
        max_rel_mag=4.0,
        min_detection_fraction=0.5,
        band_filter="",
    )
    assert len(result) > 0
    assert "norm_flux" in result.colnames
    assert "mjd" in result.colnames
    assert abs(np.median(result["norm_flux"]) - 1.0) < 0.01
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/obs_nickel/tests/test_differential_phot.py::test_process_catalogs -v`
Expected: FAIL with `AttributeError: '_process_catalogs_static'`

**Step 3: Write implementation**

Add to `DifferentialPhotTask`:

```python
    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        """Load catalogs from Butler, process, write outputs."""
        visit_table = butlerQC.get(inputRefs.visitTable)

        # Load all star catalogs with visit IDs
        catalogs = []
        for ref in inputRefs.starCatalogs:
            visit_id = ref.dataId.get("visit")
            try:
                cat = butlerQC.get(ref)
                if isinstance(cat, DeferredDatasetHandle):
                    cat = cat.get()
            except Exception:
                _LOG.warning("Failed to load catalog for visit %s", visit_id)
                continue
            # Convert SourceCatalog to list of dicts for processing
            records = []
            for rec in cat:
                records.append({
                    "coord_ra": rec.get("coord_ra"),
                    "coord_dec": rec.get("coord_dec"),
                    f"base_CircularApertureFlux_{self._ap_key}_instFlux":
                        rec.get(f"base_CircularApertureFlux_{self._ap_key}_instFlux"),
                    f"base_CircularApertureFlux_{self._ap_key}_instFluxErr":
                        rec.get(f"base_CircularApertureFlux_{self._ap_key}_instFluxErr"),
                    "base_PixelFlags_flag_saturatedCenter":
                        rec.get("base_PixelFlags_flag_saturatedCenter"),
                    "base_PixelFlags_flag_edge":
                        rec.get("base_PixelFlags_flag_edge"),
                    "deblend_nChild": rec.get("deblend_nChild"),
                })
            catalogs.append((visit_id, records))

        if not catalogs:
            raise pipeBase.NoWorkFound("No star catalogs loaded.")

        result_table = self._process_catalogs_static(
            catalogs=catalogs,
            visit_table=visit_table,
            target_ra=self.config.targetRa,
            target_dec=self.config.targetDec,
            aperture_radius=self.config.apertureRadius,
            match_radius=self.config.matchRadius,
            n_comparisons=self.config.nComparisons,
            min_comparisons=self.config.minComparisons,
            min_rel_mag=self.config.minRelMag,
            max_rel_mag=self.config.maxRelMag,
            min_detection_fraction=self.config.minDetectionFraction,
            band_filter=self.config.bandFilter,
        )

        if len(result_table) == 0:
            raise pipeBase.NoWorkFound("No differential photometry measurements.")

        fig = self._make_plot(result_table)
        butlerQC.put(
            pipeBase.Struct(lightcurveTable=result_table, lightcurvePlot=fig),
            outputRefs,
        )

    @property
    def _ap_key(self):
        """Aperture radius formatted as column key fragment (e.g. '17_0')."""
        r = self.config.apertureRadius
        if r == int(r):
            return f"{int(r)}_0"
        return str(r).replace(".", "_")

    @staticmethod
    def _process_catalogs_static(
        catalogs, visit_table, target_ra, target_dec,
        aperture_radius, match_radius, n_comparisons, min_comparisons,
        min_rel_mag, max_rel_mag, min_detection_fraction, band_filter,
    ):
        """Core processing logic (static for testability without Butler)."""
        from astropy.table import Table

        r = aperture_radius
        ap_key = f"{int(r)}_0" if r == int(r) else str(r).replace(".", "_")
        ap_col = f"base_CircularApertureFlux_{ap_key}_instFlux"
        ap_err_col = f"base_CircularApertureFlux_{ap_key}_instFluxErr"

        # Build visit metadata lookup
        visit_mjd = {row["visit"]: row["expMidptMJD"] for row in visit_table}
        visit_band = {}
        if "band" in visit_table.colnames:
            visit_band = {row["visit"]: row.get("band", "") for row in visit_table}

        # Filter by band if specified
        if band_filter:
            catalogs = [
                (vid, cat) for vid, cat in catalogs
                if visit_band.get(vid, "") == band_filter
            ]

        if not catalogs:
            return Table()

        # Step 1: Pick reference visit (most sources)
        ref_vid, ref_cat = max(catalogs, key=lambda x: len(x[1]))

        # Step 2: Find target in reference catalog
        target_idx = _find_target(ref_cat, target_ra, target_dec, match_radius)
        if target_idx is None:
            _LOG.warning("Target not found in reference visit %s", ref_vid)
            return Table()

        # Step 3: Select comparison candidates from reference visit
        comp_indices = _select_comparisons(
            ref_cat, target_idx, ap_col,
            n_max=n_comparisons * 3,  # Over-select, prune by stability later
            min_rel_mag=min_rel_mag, max_rel_mag=max_rel_mag,
        )
        if len(comp_indices) < min_comparisons:
            _LOG.warning("Only %d comparisons found (need %d)",
                         len(comp_indices), min_comparisons)
            return Table()

        # Get comparison star positions from reference catalog
        comp_positions = [
            (ref_cat[ci]["coord_ra"], ref_cat[ci]["coord_dec"])
            for ci in comp_indices
        ]

        # Step 4: Cross-match across all visits, assess stability
        n_visits = len(catalogs)
        comp_detections = [0] * len(comp_indices)
        comp_flux_lists = [[] for _ in range(len(comp_indices))]

        for vid, cat in catalogs:
            for j, (cra, cdec) in enumerate(comp_positions):
                cra_deg = np.degrees(cra)
                cdec_deg = np.degrees(cdec)
                ci = _find_target(cat, cra_deg, cdec_deg, match_radius)
                if ci is not None:
                    comp_detections[j] += 1
                    comp_flux_lists[j].append(cat[ci][ap_col])

        # Filter by detection fraction and stability
        stable_comps = []
        for j in range(len(comp_indices)):
            frac = comp_detections[j] / n_visits
            if frac < min_detection_fraction:
                continue
            if len(comp_flux_lists[j]) < 2:
                continue
            rms = np.std(comp_flux_lists[j]) / np.mean(comp_flux_lists[j])
            stable_comps.append((j, rms))

        # Sort by RMS (most stable first), take top N
        stable_comps.sort(key=lambda x: x[1])
        final_comp_indices = [j for j, _ in stable_comps[:n_comparisons]]

        if len(final_comp_indices) < min_comparisons:
            _LOG.warning("Only %d stable comparisons (need %d)",
                         len(final_comp_indices), min_comparisons)
            return Table()

        final_comp_positions = [comp_positions[j] for j in final_comp_indices]
        _LOG.info("Selected %d comparison stars (RMS range: %.4f-%.4f)",
                  len(final_comp_indices),
                  stable_comps[0][1] if stable_comps else 0,
                  stable_comps[min(len(stable_comps)-1, n_comparisons-1)][1]
                  if stable_comps else 0)

        # Step 5: Compute differential flux per visit
        rows = []
        for vid, cat in catalogs:
            mjd = visit_mjd.get(vid, np.nan)
            band = visit_band.get(vid, "")
            # Find target
            ti = _find_target(cat, target_ra, target_dec, match_radius)
            if ti is None:
                continue
            target_flux = cat[ti][ap_col]
            target_err = cat[ti][ap_err_col]
            if target_flux is None or target_flux <= 0:
                continue
            # Find comparisons
            c_fluxes, c_errs = [], []
            for cra, cdec in final_comp_positions:
                ci = _find_target(cat, np.degrees(cra), np.degrees(cdec), match_radius)
                if ci is not None:
                    cf = cat[ci][ap_col]
                    ce = cat[ci][ap_err_col]
                    if cf is not None and cf > 0:
                        c_fluxes.append(cf)
                        c_errs.append(ce if ce else 0.0)
            if len(c_fluxes) < min_comparisons:
                continue
            diff, diff_err = _compute_differential_flux(
                target_flux, target_err, c_fluxes, c_errs,
            )
            if diff is None:
                continue
            rows.append({
                "mjd": mjd,
                "band": band,
                "visit": vid,
                "diff_flux": diff,
                "diff_flux_err": diff_err,
                "target_flux": target_flux,
                "comp_sum": sum(c_fluxes),
                "n_comps": len(c_fluxes),
                "aperture_radius_px": aperture_radius,
            })

        if not rows:
            return Table()

        table = Table(rows=rows)
        table.sort("mjd")

        # Step 6: Normalize
        norm, norm_err = _normalize_lightcurve(
            np.array(table["diff_flux"]),
            np.array(table["diff_flux_err"]),
        )
        table["norm_flux"] = norm
        table["norm_flux_err"] = norm_err
        return table

    def _make_plot(self, table):
        """Generate differential photometry lightcurve plot."""
        import matplotlib.pyplot as plt
        from lsst.obs.nickel.plotting import (
            FIGURE_SIZE,
            format_lightcurve_axes,
            plot_lightcurve_band,
            publication_style,
            set_title,
            sort_bands,
        )

        with publication_style():
            fig, ax = plt.subplots(figsize=FIGURE_SIZE)
            bands = sort_bands(set(table["band"]))
            for b in bands:
                mask = table["band"] == b
                if not np.any(mask):
                    continue
                plot_lightcurve_band(
                    ax,
                    table["mjd"][mask],
                    table["norm_flux"][mask],
                    table["norm_flux_err"][mask],
                    b,
                    count=int(np.sum(mask)),
                )
            ax.axhline(y=1.0, color="0.6", ls="--", lw=0.8, alpha=0.6, zorder=0)
            format_lightcurve_axes(ax, ylabel="Normalized Flux", invert_y=False)
            name = self.config.targetName or "Differential Photometry"
            set_title(ax, name, subtitle="Differential Aperture Photometry")
            ax.legend(loc="best")
            fig.tight_layout()
        return fig
```

Also add to the top of the file:

```python
from lsst.daf.butler import DeferredDatasetHandle
```

**Step 4: Run tests**

Run: `pytest packages/obs_nickel/tests/test_differential_phot.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add packages/obs_nickel/python/lsst/obs/nickel/tasks/differentialPhot.py \
       packages/obs_nickel/tests/test_differential_phot.py
git commit -m "feat(diffphot): implement runQuantum and catalog processing"
```

---

### Task 5: Pipeline YAML and task registration

**Files:**
- Create: `packages/obs_nickel/pipelines/DifferentialPhot.yaml`
- Modify: `packages/obs_nickel/python/lsst/obs/nickel/tasks/__init__.py`

**Step 1: Write YAML**

```yaml
# DifferentialPhot.yaml
description: |
  Differential aperture photometry pipeline for bright star time-domain science.
  Reads pre-computed aperture fluxes from calibrateImage star catalogs, selects
  a comparison star ensemble, and produces normalized differential flux lightcurves.
  Works for exoplanet transits and variable star monitoring.
instrument: lsst.obs.nickel.Nickel

tasks:
  makeVisitTable:
    class: lsst.pipe.tasks.postprocess.MakeVisitTableTask
    config:
      connections.visitSummaries: preliminary_visit_summary
      connections.outputCatalog: preliminary_visit_table

  differentialPhot:
    class: lsst.obs.nickel.tasks.DifferentialPhotTask
    config:
      connections.starCatalogName: single_visit_star_unstandardized
      connections.visitTableName: preliminary_visit_table
      connections.outputName: differential_phot_lightcurve
      apertureRadius: 17.0
      nComparisons: 10

subsets:
  lightcurve:
    subset:
      - makeVisitTable
      - differentialPhot
    description: |
      Generate differential photometry lightcurve from existing
      calibrateImage star catalogs.
```

**Step 2: Update `__init__.py`**

Add import and `__all__` entry:

```python
from .differentialPhot import (
    DifferentialPhotConfig,
    DifferentialPhotTask,
)

# Add to __all__:
    "DifferentialPhotTask",
    "DifferentialPhotConfig",
```

**Step 3: Verify import works**

Run: `python -c "from lsst.obs.nickel.tasks import DifferentialPhotTask; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add packages/obs_nickel/pipelines/DifferentialPhot.yaml \
       packages/obs_nickel/python/lsst/obs/nickel/tasks/__init__.py
git commit -m "feat(diffphot): add pipeline YAML and register task"
```

---

### Task 6: Integrate with run.py orchestrator

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py`

**Step 1: Update `_run_differential_phot_step()`**

Replace the current implementation that calls the standalone `differential_phot.py` with a `pipetask run` invocation of the new LSST pipeline:

```python
def _run_differential_phot_step(
    all_nights: list[str],
    run_cfg: RunConfig,
    config: "Config",
    result: RunResult,
    dry_run: bool,
) -> None:
    """Run LSST differential aperture photometry pipeline."""
    from obs_nickel_data_tools.core.stack import run_pipetask

    repo = config.repo
    obs_nickel = config.obs_nickel

    # Find the science collection
    science_coll = None
    for night in all_nights:
        coll_parent = Path(repo) / "Nickel" / "runs" / night / "processCcd"
        if coll_parent.exists():
            ts_dirs = sorted(
                [d for d in coll_parent.iterdir() if d.is_dir()], reverse=True
            )
            if ts_dirs:
                rel_path = ts_dirs[0].relative_to(Path(repo))
                science_coll = str(rel_path)
                break

    if not science_coll:
        log.warning("No science collection found, skipping differential photometry")
        return

    log.info(f"Running LSST differential photometry on {science_coll}")

    pipeline_yaml = Path(obs_nickel) / "pipelines" / "DifferentialPhot.yaml"
    input_colls = f"{science_coll},Nickel/calib/current,refcats,skymaps/nickelRings"
    output_coll = f"Nickel/runs/{all_nights[0]}/differentialPhot"

    bands = run_cfg.bands
    band_filter = bands[0] if len(bands) == 1 else ""
    aperture_radius = getattr(run_cfg, "aperture_radius", 17.0)

    config_overrides = [
        f"differentialPhot:targetRa={run_cfg.ra}",
        f"differentialPhot:targetDec={run_cfg.dec}",
        f"differentialPhot:apertureRadius={aperture_radius}",
        f"differentialPhot:targetName={run_cfg.object_name}",
    ]
    if band_filter:
        config_overrides.append(f"differentialPhot:bandFilter={band_filter}")

    if not dry_run:
        _get_step_log_file("differential_phot")
        try:
            run_pipetask(
                repo=repo,
                pipeline=str(pipeline_yaml),
                input_colls=input_colls,
                output_coll=output_coll,
                config_overrides=config_overrides,
                log_file=None,
            )
            log.info("  Differential photometry pipeline complete")
        except Exception as e:
            log.error(f"Differential photometry failed: {e}")
    else:
        log.info("  [DRY RUN] pipetask run -p DifferentialPhot.yaml")
```

Note: The exact `run_pipetask` call signature should match the existing pattern in `science.py` or `dia.py`. Check those files and adapt the call accordingly. The key config overrides are target RA/Dec and aperture radius.

**Step 2: Run existing tests**

Run: `pytest packages/obs_nickel/tests/test_transit.py -v`
Expected: All 24 PASS (existing transit tests unaffected)

**Step 3: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py
git commit -m "feat(diffphot): integrate LSST pipeline into run.py orchestrator"
```

---

### Task 7: End-to-end validation on HD 189733 b data

**Files:** None (validation only)

**Step 1: Run pipeline on existing HD 189733 b repo**

```bash
nickel run scripts/config/hd189733/pipeline_transit.yaml
```

Verify:
- Differential photometry step runs via `pipetask` (not standalone script)
- Output lightcurve table created in Butler
- RMS scatter similar to standalone script (~5%)
- Transit dip still detectable

**Step 2: Compare results**

Compare the new LSST-native lightcurve against the existing `differential_lightcurve.csv` from the standalone script. Key metrics:
- Number of measurements (should be >= 302)
- RMS of normalized flux (should be ~5%)
- Transit depth (should be ~5.4%)

**Step 3: Commit validation results**

If validation passes, remove the standalone script:

```bash
git rm packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/differential_phot.py
git commit -m "refactor(diffphot): remove standalone script, LSST pipeline validated"
```

---

### Task 8: Update MEMORY.md and CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (if pipeline docs need updating)
- Modify: MEMORY.md (note LSST-native approach)

Update the "Exoplanet Transit Detection" section in MEMORY.md to reflect:
- LSST-native differential photometry replaces standalone script
- Reads `single_visit_star_unstandardized` catalogs via Butler
- Pipeline: `DifferentialPhot.yaml`
- Task: `DifferentialPhotTask` at `dimensions=(instrument,)`

```bash
git add -A && git commit -m "docs: update memory and docs for LSST-native diffphot"
```
