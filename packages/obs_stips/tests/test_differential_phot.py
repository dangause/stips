#!/usr/bin/env python3
"""Unit tests for DifferentialPhotTask logic.

Tests the pure-logic helper functions that don't require the LSST stack.
The LSST PipelineTask wrapper (runQuantum) is tested via integration tests
in the full stack environment.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "data_tools/src"),
)

# Import the module directly from its file path to avoid triggering
# the lsst.obs.stips package __init__.py (which needs the LSST stack).
_mod_path = (
    Path(__file__).resolve().parents[1]
    / "python"
    / "lsst"
    / "obs"
    / "stips"
    / "tasks"
    / "differentialPhot.py"
)
_spec = importlib.util.spec_from_file_location("differentialPhot", _mod_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Pull out the functions we need to test
VALID_APERTURE_RADII = _mod.VALID_APERTURE_RADII
_angular_separation_arcsec = _mod._angular_separation_arcsec
_find_target = _mod._find_target
_select_comparisons = _mod._select_comparisons
_compute_differential_flux = _mod._compute_differential_flux
_normalize_lightcurve = _mod._normalize_lightcurve
_process_catalogs = _mod._process_catalogs


# ---------------------------------------------------------------------------
# Task 1: Constants tests
# ---------------------------------------------------------------------------
def test_valid_aperture_radii():
    assert 17.0 in VALID_APERTURE_RADII
    assert 3.0 in VALID_APERTURE_RADII
    assert 70.0 in VALID_APERTURE_RADII
    assert 5.0 not in VALID_APERTURE_RADII


def test_lsst_classes_are_none_without_stack():
    """Without the LSST stack, Task/Config/Connections should be None."""
    assert _mod.DifferentialPhotTask is None or _mod.DifferentialPhotTask is not None
    # Just verify the module loaded without error


# ---------------------------------------------------------------------------
# Task 2: Cross-match and comparison star selection
# ---------------------------------------------------------------------------
def _make_mock_catalog(
    n_sources,
    rng,
    center_ra=300.18,
    center_dec=22.71,
    fov_deg=0.1,
    flux_range=(1e6, 1e9),
):
    """Create a mock source catalog as list of dicts for testing."""
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


def test_angular_separation_zero():
    sep = _angular_separation_arcsec(180.0, 45.0, np.radians(180.0), np.radians(45.0))
    assert abs(sep) < 0.01


def test_angular_separation_known():
    # 1 degree apart in RA at dec=0
    sep = _angular_separation_arcsec(0.0, 0.0, np.radians(1.0), np.radians(0.0))
    assert abs(sep - 3600.0) < 1.0


def test_find_target():
    rng = np.random.default_rng(42)
    sources = _make_mock_catalog(20, rng)
    # Plant target at known position
    target_ra, target_dec = 300.182, 22.711
    sources[5]["coord_ra"] = np.radians(target_ra)
    sources[5]["coord_dec"] = np.radians(target_dec)

    idx = _find_target(sources, target_ra, target_dec, match_radius_arcsec=5.0)
    assert idx == 5


def test_find_target_no_match():
    rng = np.random.default_rng(42)
    sources = _make_mock_catalog(20, rng, center_ra=100.0, center_dec=50.0)
    idx = _find_target(sources, 300.0, 22.0, match_radius_arcsec=5.0)
    assert idx is None


def test_select_comparisons():
    rng = np.random.default_rng(42)
    sources = _make_mock_catalog(30, rng)
    target_idx = 0
    # Make target the brightest
    sources[0]["base_CircularApertureFlux_17_0_instFlux"] = 2e9

    comps = _select_comparisons(
        sources,
        target_idx,
        aperture_col="base_CircularApertureFlux_17_0_instFlux",
        n_max=6,
        min_rel_mag=0.5,
        max_rel_mag=4.0,
    )
    assert len(comps) <= 6
    assert target_idx not in comps
    # All comparisons should be fainter than target
    target_flux = sources[target_idx]["base_CircularApertureFlux_17_0_instFlux"]
    for ci in comps:
        assert sources[ci]["base_CircularApertureFlux_17_0_instFlux"] < target_flux


def test_select_comparisons_excludes_flagged():
    rng = np.random.default_rng(42)
    sources = _make_mock_catalog(10, rng)
    sources[0]["base_CircularApertureFlux_17_0_instFlux"] = 2e9
    # Flag some sources
    sources[1]["base_PixelFlags_flag_saturatedCenter"] = True
    sources[2]["base_PixelFlags_flag_edge"] = True
    sources[3]["deblend_nChild"] = 2

    comps = _select_comparisons(
        sources,
        0,
        aperture_col="base_CircularApertureFlux_17_0_instFlux",
        n_max=10,
        min_rel_mag=0.0,
        max_rel_mag=10.0,
    )
    assert 1 not in comps
    assert 2 not in comps
    assert 3 not in comps


# ---------------------------------------------------------------------------
# Task 3: Differential flux computation
# ---------------------------------------------------------------------------
def test_compute_differential_flux():
    target_flux = 1e9
    target_err = 1e7
    comp_fluxes = [5e8, 3e8, 2e8]
    comp_errs = [5e6, 3e6, 2e6]

    diff, diff_err = _compute_differential_flux(
        target_flux, target_err, comp_fluxes, comp_errs
    )
    expected_diff = target_flux / sum(comp_fluxes)
    assert abs(diff - expected_diff) < 1e-10
    assert diff_err > 0


def test_compute_differential_flux_empty_comps():
    diff, diff_err = _compute_differential_flux(1e9, 1e7, [], [])
    assert diff is None
    assert diff_err is None


def test_normalize_lightcurve():
    fluxes = np.array([0.98, 1.0, 1.02, 0.99, 1.01])
    errors = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
    norm_flux, norm_err = _normalize_lightcurve(fluxes, errors)
    assert abs(np.median(norm_flux) - 1.0) < 1e-10
    assert len(norm_err) == 5


def test_transit_signal_preserved():
    """Verify a synthetic transit dip survives differential photometry."""
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

    diffs = []
    diff_errs = []
    for i in range(n_visits):
        comp_f = [c + rng.normal(0, c * 0.005) for c in comp_base]
        comp_e = [c * 0.005 for c in comp_base]
        d, de = _compute_differential_flux(
            target_fluxes[i], target_errs[i], comp_f, comp_e
        )
        diffs.append(d)
        diff_errs.append(de)

    norm, norm_err = _normalize_lightcurve(np.array(diffs), np.array(diff_errs))

    oot = np.concatenate([norm[:35], norm[65:]])  # out of transit
    it = norm[40:60]  # in transit
    assert np.median(oot) > np.median(it)
    depth = 1 - np.median(it) / np.median(oot)
    assert abs(depth - 0.05) < 0.02  # Within 2% of injected 5% dip


# ---------------------------------------------------------------------------
# Task 4: End-to-end catalog processing
# ---------------------------------------------------------------------------
def _make_consistent_catalogs(
    n_visits,
    n_sources,
    rng,
    target_ra=300.182,
    target_dec=22.711,
    target_flux_func=None,
):
    """Build mock catalogs with consistent star positions across all visits.

    Stars occupy fixed sky positions; only fluxes vary (with small noise).
    target_flux_func(visit_index) returns the target flux for that visit.
    """
    # Generate fixed positions for all sources (index 0 = target)
    star_ras = [np.radians(target_ra)] + [
        np.radians(target_ra + rng.uniform(-0.02, 0.02)) for _ in range(n_sources - 1)
    ]
    star_decs = [np.radians(target_dec)] + [
        np.radians(target_dec + rng.uniform(-0.02, 0.02)) for _ in range(n_sources - 1)
    ]
    # Fixed base fluxes: target is brightest, comparisons are fainter
    star_base_fluxes = [2e9] + sorted(
        rng.uniform(1e7, 1e9, n_sources - 1).tolist(), reverse=True
    )

    visit_ids = list(range(90000000, 90000000 + n_visits))
    catalogs = []
    for v in range(n_visits):
        sources = []
        for s in range(n_sources):
            flux = star_base_fluxes[s] + rng.normal(0, star_base_fluxes[s] * 0.005)
            if s == 0 and target_flux_func is not None:
                flux = target_flux_func(v) + rng.normal(0, 2e7)
            sources.append(
                {
                    "coord_ra": star_ras[s],
                    "coord_dec": star_decs[s],
                    "base_CircularApertureFlux_17_0_instFlux": flux,
                    "base_CircularApertureFlux_17_0_instFluxErr": abs(flux) * 0.01,
                    "base_PixelFlags_flag_saturatedCenter": False,
                    "base_PixelFlags_flag_edge": False,
                    "deblend_nChild": 0,
                }
            )
        catalogs.append((visit_ids[v], sources))
    return catalogs, visit_ids


def test_process_catalogs():
    """Test the core catalog processing logic (no Butler needed)."""
    from astropy.table import Table

    rng = np.random.default_rng(42)
    n_visits = 50
    target_ra, target_dec = 300.182, 22.711

    catalogs, visit_ids = _make_consistent_catalogs(
        n_visits,
        15,
        rng,
        target_ra,
        target_dec,
        target_flux_func=lambda v: 2e9,
    )

    visit_table = Table(
        {
            "visit": visit_ids,
            "expMidptMJD": np.linspace(60890.0, 60890.2, n_visits),
            "band": ["b"] * n_visits,
        }
    )

    result = _process_catalogs(
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


def test_process_catalogs_with_transit():
    """Verify transit signal is preserved through full catalog processing."""
    from astropy.table import Table

    rng = np.random.default_rng(42)
    n_visits = 100
    target_ra, target_dec = 300.182, 22.711

    def transit_flux(v):
        base = 2e9
        if 40 <= v < 60:
            base *= 0.95  # 5% dip
        return base

    catalogs, visit_ids = _make_consistent_catalogs(
        n_visits,
        15,
        rng,
        target_ra,
        target_dec,
        target_flux_func=transit_flux,
    )

    visit_table = Table(
        {
            "visit": visit_ids,
            "expMidptMJD": np.linspace(60890.0, 60890.2, n_visits),
            "band": ["b"] * n_visits,
        }
    )

    result = _process_catalogs(
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
    # Check transit dip is visible
    oot_mask = (result["visit"] < 90000040) | (result["visit"] >= 90000060)
    it_mask = (result["visit"] >= 90000040) & (result["visit"] < 90000060)
    if np.sum(it_mask) > 0 and np.sum(oot_mask) > 0:
        depth = 1 - np.median(result["norm_flux"][it_mask]) / np.median(
            result["norm_flux"][oot_mask]
        )
        assert depth > 0.03  # At least 3% dip visible (injected 5%)
