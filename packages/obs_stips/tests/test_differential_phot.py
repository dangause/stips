#!/usr/bin/env python3
"""Unit tests for DifferentialPhotTask logic.

Tests the pure-logic helper functions that don't require the LSST stack.
The LSST PipelineTask wrapper (runQuantum) is tested via integration tests
in the full stack environment.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

import numpy as np

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
    """Task/Config/Connections are None exactly when the LSST stack is absent."""
    has_lsst = _mod._HAS_LSST
    assert (_mod.DifferentialPhotTask is None) == (not has_lsst)
    assert (_mod.DifferentialPhotConfig is None) == (not has_lsst)
    assert (_mod.DifferentialPhotConnections is None) == (not has_lsst)


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
    """comp_signal is the flux-weighted ratio of sums Sum(c_i)/Sum(ref_i),
    not a raw sum or a mean of relative fluxes -- see _process_catalogs,
    which passes each comparison's raw per-visit flux alongside its own
    reference flux."""
    target_flux = 1e9
    target_err = 1e7
    comp_fluxes = [5e8, 3e8, 2e8]
    comp_errs = [5e6, 3e6, 2e6]
    comp_ref_fluxes = [4e8, 3.5e8, 2.5e8]

    diff, diff_err = _compute_differential_flux(
        target_flux, target_err, comp_fluxes, comp_errs, comp_ref_fluxes
    )
    expected_diff = target_flux / (sum(comp_fluxes) / sum(comp_ref_fluxes))
    assert abs(diff - expected_diff) < 1e-10
    assert diff_err > 0


def test_compute_differential_flux_empty_comps():
    diff, diff_err = _compute_differential_flux(1e9, 1e7, [], [], [])
    assert diff is None
    assert diff_err is None


def test_compute_differential_flux_known_diff_err():
    """diff_err for a hand-computable case with UNEQUAL per-star reference
    fluxes, so Sum(comp_fluxes)=1000 != Sum(comp_ref_fluxes)=800: this
    distinguishes the actual ratio-of-sums formula
    (comp_signal = Sum(c_i)/Sum(ref_i) = 1000/800 = 1.25) from a
    mean-of-relative-fluxes formula (mean(c_i/ref_i) = mean(1.6, 0.6667) =
    1.1333), which would give a different, wrong diff. Both diff and
    diff_err are asserted to their exact hand-computed values."""
    target_flux, target_err = 1000.0, 20.0  # 2% target error
    comp_fluxes = [800.0, 200.0]  # sum = 1000
    comp_errs = [6.0, 8.0]  # sqrt(6^2 + 8^2) = 10
    comp_ref_fluxes = [500.0, 300.0]  # sum = 800 != 1000

    diff, diff_err = _compute_differential_flux(
        target_flux, target_err, comp_fluxes, comp_errs, comp_ref_fluxes
    )
    # comp_signal = 1000/800 = 1.25; diff = 1000/1.25 = 800.0 exactly.
    assert abs(diff - 800.0) < 1e-9
    # comp_signal_err = 10/800 = 0.0125; comp_signal_err/comp_signal = 0.01
    # diff_err = 800 * sqrt((20/1000)^2 + 0.01^2) = 800*sqrt(0.0005)
    expected_diff_err = 800.0 * np.sqrt(0.02**2 + 0.01**2)
    assert abs(diff_err - expected_diff_err) < 1e-9


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
            target_fluxes[i], target_errs[i], comp_f, comp_e, comp_base
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


# ---------------------------------------------------------------------------
# Task 5: per-star comparison normalisation (incomplete ensembles)
# ---------------------------------------------------------------------------
def _make_catalogs_with_dropout(
    n_visits,
    comp_base_fluxes,
    target_flux,
    missing=None,
    target_ra=300.182,
    target_dec=22.711,
):
    """Deterministic catalogs: one target + len(comp_base_fluxes) comparison
    stars at fixed sky positions with EXACTLY constant fluxes (no noise), so
    any change in diff_flux/comp_sum across visits is purely due to the
    normalisation logic under test, not measurement noise.

    ``missing`` maps a 0-based visit index to a set of 0-based comparison
    indices (into ``comp_base_fluxes``) to omit entirely from that visit's
    catalog, simulating a star falling below the per-frame detection
    threshold.
    """
    missing = missing or {}
    n_comps = len(comp_base_fluxes)
    star_ras = [np.radians(target_ra)] + [
        np.radians(target_ra + 0.01 * (i + 1)) for i in range(n_comps)
    ]
    star_decs = [np.radians(target_dec)] + [
        np.radians(target_dec + 0.01 * (i + 1)) for i in range(n_comps)
    ]
    visit_ids = list(range(80000000, 80000000 + n_visits))
    catalogs = []
    for v in range(n_visits):
        drop = missing.get(v, set())
        sources = [
            {
                "coord_ra": star_ras[0],
                "coord_dec": star_decs[0],
                "base_CircularApertureFlux_17_0_instFlux": target_flux,
                "base_CircularApertureFlux_17_0_instFluxErr": target_flux * 0.01,
                "base_PixelFlags_flag_saturatedCenter": False,
                "base_PixelFlags_flag_edge": False,
                "deblend_nChild": 0,
            }
        ]
        for i, base in enumerate(comp_base_fluxes):
            if i in drop:
                continue
            sources.append(
                {
                    "coord_ra": star_ras[i + 1],
                    "coord_dec": star_decs[i + 1],
                    "base_CircularApertureFlux_17_0_instFlux": base,
                    "base_CircularApertureFlux_17_0_instFluxErr": base * 0.01,
                    "base_PixelFlags_flag_saturatedCenter": False,
                    "base_PixelFlags_flag_edge": False,
                    "deblend_nChild": 0,
                }
            )
        catalogs.append((visit_ids[v], sources))
    return catalogs, visit_ids


def _dropout_visit_table(visit_ids, n_visits):
    from astropy.table import Table

    return Table(
        {
            "visit": visit_ids,
            "expMidptMJD": np.linspace(60890.0, 60890.1, n_visits),
            "band": ["b"] * n_visits,
        }
    )


def test_missing_comparison_does_not_inflate_flux():
    """One comparison star absent from a single visit must not inflate that
    visit's diff_flux. The old code summed raw comparison fluxes, so a
    missing star shrank the denominator and inflated norm_flux; with
    per-star normalisation the light curve stays flat."""
    target_ra, target_dec = 300.182, 22.711
    comp_base_fluxes = [5e8, 3e8, 2e8, 1e8]
    n_visits = 6
    catalogs, visit_ids = _make_catalogs_with_dropout(
        n_visits,
        comp_base_fluxes,
        target_flux=2e9,
        missing={3: {2}},  # visit index 3 is missing comparison star 2
        target_ra=target_ra,
        target_dec=target_dec,
    )
    visit_table = _dropout_visit_table(visit_ids, n_visits)

    result = _process_catalogs(
        catalogs=catalogs,
        visit_table=visit_table,
        target_ra=target_ra,
        target_dec=target_dec,
        aperture_radius=17.0,
        match_radius=2.0,
        n_comparisons=4,
        min_comparisons=1,
        min_rel_mag=0.5,
        max_rel_mag=4.0,
        min_detection_fraction=0.5,
        band_filter="",
    )
    assert len(result) == n_visits
    assert np.max(np.abs(np.array(result["norm_flux"]) - 1.0)) < 1e-6


def test_visit_dropped_below_comparison_fraction():
    """A visit missing too large a fraction of the comparison ensemble is
    dropped entirely, per minComparisonFraction, rather than emitted with a
    degraded ensemble."""
    target_ra, target_dec = 300.182, 22.711
    comp_base_fluxes = [5e8, 3e8, 2e8, 1e8]
    n_visits = 6
    catalogs, visit_ids = _make_catalogs_with_dropout(
        n_visits,
        comp_base_fluxes,
        target_flux=2e9,
        missing={3: {1, 2}},  # 2 of 4 comparisons absent in visit index 3
        target_ra=target_ra,
        target_dec=target_dec,
    )
    visit_table = _dropout_visit_table(visit_ids, n_visits)
    common_kwargs = dict(
        catalogs=catalogs,
        visit_table=visit_table,
        target_ra=target_ra,
        target_dec=target_dec,
        aperture_radius=17.0,
        match_radius=2.0,
        n_comparisons=4,
        min_comparisons=1,
        min_rel_mag=0.5,
        max_rel_mag=4.0,
        min_detection_fraction=0.5,
        band_filter="",
    )

    strict = _process_catalogs(**common_kwargs, min_comparison_fraction=0.7)
    assert visit_ids[3] not in list(strict["visit"])

    loose = _process_catalogs(**common_kwargs, min_comparison_fraction=0.4)
    assert visit_ids[3] in list(loose["visit"])


def test_comp_sum_is_flux_weighted_ratio():
    """On a clean set of visits where every comparison has constant flux,
    comp_sum (Sum(c_i)/Sum(ref_i)) is 1.0 for every visit, since each
    star's raw flux equals its own reference flux exactly."""
    target_ra, target_dec = 300.182, 22.711
    comp_base_fluxes = [5e8, 3e8, 2e8, 1e8]
    n_visits = 5
    catalogs, visit_ids = _make_catalogs_with_dropout(
        n_visits,
        comp_base_fluxes,
        target_flux=2e9,
        missing={},
        target_ra=target_ra,
        target_dec=target_dec,
    )
    visit_table = _dropout_visit_table(visit_ids, n_visits)

    result = _process_catalogs(
        catalogs=catalogs,
        visit_table=visit_table,
        target_ra=target_ra,
        target_dec=target_dec,
        aperture_radius=17.0,
        match_radius=2.0,
        n_comparisons=4,
        min_comparisons=1,
        min_rel_mag=0.5,
        max_rel_mag=4.0,
        min_detection_fraction=0.5,
        band_filter="",
    )
    assert len(result) == n_visits
    assert np.max(np.abs(np.array(result["comp_sum"]) - 1.0)) < 1e-9


def test_complete_ensemble_matches_flux_weighted_sum():
    """When every comparison star is present in every visit, Sum(ref_i) is
    the same constant on every visit (no star is ever missing), so the
    flux-weighted comp_signal = Sum(c_i)/Sum(ref_i) is just Sum(c_i)
    rescaled by that constant. _normalize_lightcurve's median normalisation
    removes any such per-visit-constant rescaling, so the normalised
    diff_flux sequence must equal normalise(target / Sum(c_i)) exactly --
    the pre-fix (sum-of-raw-flux) behaviour -- even though the per-visit
    comparison fluxes are arbitrary (not constant) from visit to visit."""
    target_ra, target_dec = 300.182, 22.711
    n_visits = 8
    n_comps = 4
    target_flux = 2e9  # constant target flux; only comparisons vary

    rng = np.random.default_rng(7)
    # Arbitrary per-visit comparison fluxes, within _select_comparisons'
    # magnitude bounds relative to target_flux (checked only at the
    # reference visit, visit index 0).
    comp_flux_vals = rng.uniform(1e8, 9e8, size=(n_visits, n_comps))

    star_ras = [np.radians(target_ra)] + [
        np.radians(target_ra + 0.01 * (i + 1)) for i in range(n_comps)
    ]
    star_decs = [np.radians(target_dec)] + [
        np.radians(target_dec + 0.01 * (i + 1)) for i in range(n_comps)
    ]
    visit_ids = list(range(82000000, 82000000 + n_visits))
    catalogs = []
    for v in range(n_visits):
        sources = [
            {
                "coord_ra": star_ras[0],
                "coord_dec": star_decs[0],
                "base_CircularApertureFlux_17_0_instFlux": target_flux,
                "base_CircularApertureFlux_17_0_instFluxErr": target_flux * 0.01,
                "base_PixelFlags_flag_saturatedCenter": False,
                "base_PixelFlags_flag_edge": False,
                "deblend_nChild": 0,
            }
        ]
        for i in range(n_comps):
            cf = float(comp_flux_vals[v, i])
            sources.append(
                {
                    "coord_ra": star_ras[i + 1],
                    "coord_dec": star_decs[i + 1],
                    "base_CircularApertureFlux_17_0_instFlux": cf,
                    "base_CircularApertureFlux_17_0_instFluxErr": cf * 0.01,
                    "base_PixelFlags_flag_saturatedCenter": False,
                    "base_PixelFlags_flag_edge": False,
                    "deblend_nChild": 0,
                }
            )
        catalogs.append((visit_ids[v], sources))

    visit_table = _dropout_visit_table(visit_ids, n_visits)

    result = _process_catalogs(
        catalogs=catalogs,
        visit_table=visit_table,
        target_ra=target_ra,
        target_dec=target_dec,
        aperture_radius=17.0,
        match_radius=2.0,
        n_comparisons=n_comps,
        min_comparisons=1,
        min_rel_mag=0.5,
        max_rel_mag=4.0,
        min_detection_fraction=0.5,
        band_filter="",
    )
    assert len(result) == n_visits
    # Visits are output sorted by mjd, which increases with visit index v
    # here, so row order matches comp_flux_vals' visit order directly.
    expected_raw = target_flux / comp_flux_vals.sum(axis=1)
    expected_norm, _ = _normalize_lightcurve(
        expected_raw, np.ones_like(expected_raw)
    )
    np.testing.assert_allclose(result["norm_flux"], expected_norm, atol=1e-9)


def test_nan_flux_does_not_remove_star_or_empty_lightcurve():
    """A comparison star with a NaN flux in one visit and a non-positive
    flux in another must not be dropped from the ensemble (it has valid
    flux in the other visits) and must not empty either visit's output:
    with 4 comparisons, at most 1 missing per visit still meets the
    default minComparisonFraction=0.7 threshold (needs >= 3 of 4). The
    light curve must stay flat because the 3 always-good comparisons'
    flux equals their reference flux exactly in every visit."""
    target_ra, target_dec = 300.182, 22.711
    comp_base_fluxes = [5e8, 3e8, 2e8, 1e8]
    n_visits = 6
    catalogs, visit_ids = _make_catalogs_with_dropout(
        n_visits,
        comp_base_fluxes,
        target_flux=2e9,
        missing={},
        target_ra=target_ra,
        target_dec=target_dec,
    )
    # Comparison star index 2 (source index 1 + 2 = 3 in each visit's
    # source list: 0 is the target) stays positionally present in every
    # visit, but gets an unusable flux value in two of them.
    catalogs[1][1][3]["base_CircularApertureFlux_17_0_instFlux"] = float("nan")
    catalogs[4][1][3]["base_CircularApertureFlux_17_0_instFlux"] = -1e7

    visit_table = _dropout_visit_table(visit_ids, n_visits)

    result = _process_catalogs(
        catalogs=catalogs,
        visit_table=visit_table,
        target_ra=target_ra,
        target_dec=target_dec,
        aperture_radius=17.0,
        match_radius=2.0,
        n_comparisons=4,
        min_comparisons=1,
        min_rel_mag=0.5,
        max_rel_mag=4.0,
        min_detection_fraction=0.5,
        band_filter="",
    )
    assert len(result) == n_visits
    assert np.max(np.abs(np.array(result["norm_flux"]) - 1.0)) < 1e-6


def test_nan_error_skips_star_for_that_visit():
    """A comparison star with a valid flux but a NaN error in one visit
    must be skipped for that visit (not included with its error coerced
    to 0.0, which would understate the propagated uncertainty) -- same
    treatment as a NaN/non-positive flux."""
    target_ra, target_dec = 300.182, 22.711
    comp_base_fluxes = [5e8, 3e8, 2e8, 1e8]
    n_visits = 6
    catalogs, visit_ids = _make_catalogs_with_dropout(
        n_visits,
        comp_base_fluxes,
        target_flux=2e9,
        missing={},
        target_ra=target_ra,
        target_dec=target_dec,
    )
    # Comparison star index 2 (source index 3) keeps a valid flux in visit
    # index 2 but gets a NaN error there.
    catalogs[2][1][3]["base_CircularApertureFlux_17_0_instFluxErr"] = float("nan")

    visit_table = _dropout_visit_table(visit_ids, n_visits)

    result = _process_catalogs(
        catalogs=catalogs,
        visit_table=visit_table,
        target_ra=target_ra,
        target_dec=target_dec,
        aperture_radius=17.0,
        match_radius=2.0,
        n_comparisons=4,
        min_comparisons=1,
        min_rel_mag=0.5,
        max_rel_mag=4.0,
        min_detection_fraction=0.5,
        band_filter="",
    )
    assert len(result) == n_visits
    by_visit = {int(r["visit"]): int(r["n_comps"]) for r in result}
    assert by_visit[visit_ids[2]] == 3  # the NaN-error star was skipped
    for v in range(n_visits):
        if v != 2:
            assert by_visit[visit_ids[v]] == 4
    assert np.max(np.abs(np.array(result["norm_flux"]) - 1.0)) < 1e-6


def test_all_nan_comparison_dropped_with_warning(caplog):
    """A comparison candidate with no finite, positive flux in ANY visit
    cannot be ranked (rms over an empty/all-NaN list is undefined) and is
    dropped from consideration entirely, logging a warning naming it --
    rather than poisoning the reference-flux median or the stability
    ranking, or sorting with an undefined NaN key."""
    target_ra, target_dec = 300.182, 22.711
    comp_base_fluxes = [5e8, 3e8, 2e8, 1e8]
    n_visits = 6
    catalogs, visit_ids = _make_catalogs_with_dropout(
        n_visits,
        comp_base_fluxes,
        target_flux=2e9,
        missing={},
        target_ra=target_ra,
        target_dec=target_dec,
    )
    # Comparison star index 3 (source index 4) is unusable in every visit.
    for v in range(n_visits):
        catalogs[v][1][4]["base_CircularApertureFlux_17_0_instFlux"] = float("nan")

    visit_table = _dropout_visit_table(visit_ids, n_visits)

    with caplog.at_level(logging.WARNING):
        result = _process_catalogs(
            catalogs=catalogs,
            visit_table=visit_table,
            target_ra=target_ra,
            target_dec=target_dec,
            aperture_radius=17.0,
            match_radius=2.0,
            n_comparisons=4,
            min_comparisons=1,
            min_rel_mag=0.5,
            max_rel_mag=4.0,
            min_detection_fraction=0.5,
            band_filter="",
        )
    assert any(
        "Dropping comparison candidate" in rec.message for rec in caplog.records
    )
    # The remaining 3 always-good comparisons meet minComparisonFraction
    # (default 0.7, ceil(0.7*3)=3) in every visit.
    assert len(result) == n_visits
    assert np.max(np.abs(np.array(result["norm_flux"]) - 1.0)) < 1e-6


def test_too_few_usable_comparisons_returns_early_with_warning(caplog):
    """If dropping fully-unusable candidates (each logged individually,
    see test_all_nan_comparison_dropped_with_warning) leaves fewer than
    min_comparisons, _process_catalogs must return an empty table with a
    warning up front -- mirroring the pre-existing "too few comparisons"
    branch -- instead of silently failing the min_present check on every
    single visit with no diagnostic. Because the NaN-safety fix excludes
    unusable candidates at the ranking stage (Step 2) rather than only
    after it, this is already covered by that pre-existing check once the
    candidate count it sees reflects the drops."""
    target_ra, target_dec = 300.182, 22.711
    comp_base_fluxes = [5e8, 3e8, 2e8, 1e8]
    n_visits = 6
    catalogs, visit_ids = _make_catalogs_with_dropout(
        n_visits,
        comp_base_fluxes,
        target_flux=2e9,
        missing={},
        target_ra=target_ra,
        target_dec=target_dec,
    )
    # Comparison stars at index 2 and 3 (source indices 3, 4) are unusable
    # in every visit, leaving only 2 usable stars -- below min_comparisons=3.
    for v in range(n_visits):
        catalogs[v][1][3]["base_CircularApertureFlux_17_0_instFlux"] = float("nan")
        catalogs[v][1][4]["base_CircularApertureFlux_17_0_instFlux"] = float("nan")

    visit_table = _dropout_visit_table(visit_ids, n_visits)

    with caplog.at_level(logging.WARNING):
        result = _process_catalogs(
            catalogs=catalogs,
            visit_table=visit_table,
            target_ra=target_ra,
            target_dec=target_dec,
            aperture_radius=17.0,
            match_radius=2.0,
            n_comparisons=4,
            min_comparisons=3,
            min_rel_mag=0.5,
            max_rel_mag=4.0,
            min_detection_fraction=0.5,
            band_filter="",
        )
    assert len(result) == 0
    assert any("stable comparisons" in rec.message for rec in caplog.records)


def test_nan_in_best_candidate_does_not_change_selection():
    """Step 2's stability ranking must stay NaN-safe: one bad measurement
    in the single most stable candidate must not rank it (or the genuinely
    stable candidates sorted after it) out of the final ensemble via an
    undefined NaN sort key.

    6 candidates, ordered brightest-first in the reference visit so that
    _select_comparisons' flux-descending sort yields comp_indices position
    j == array index directly:
    - j=0,1,2 (brightest three) oscillate by +-8-10% visit to visit: NOT
      stable, must not be selected.
    - j=3,4,5 (faintest three) are stable (<=0.3% rms); j=3 is the
      genuinely most stable (constant flux) and gets a NaN in one visit.

    With nComparisons=3, only one of these two groups can be selected.
    If the NaN sorts j=3 (and anything sorted after it) out of the top 3,
    the noisy group gets selected instead and comp_sum swings by ~10%
    instead of staying within ~1% of 1.0."""
    target_ra, target_dec = 300.182, 22.711
    n_visits = 10
    target_flux = 2e9

    base_fluxes = [9e8, 8e8, 7e8, 6e8, 5e8, 4e8]
    noisy_pattern = [1.10, 0.90, 1.08, 0.92, 1.10, 0.90, 1.08, 0.92, 1.10, 0.90]
    stable_patterns = {
        3: [1.0] * n_visits,
        4: [1.0, 1.001, 0.999, 1.001, 0.999, 1.001, 0.999, 1.001, 0.999, 1.001],
        5: [1.0, 1.003, 0.997, 1.003, 0.997, 1.003, 0.997, 1.003, 0.997, 1.003],
    }

    def _make_catalogs(inject_nan):
        star_ras = [np.radians(target_ra)] + [
            np.radians(target_ra + 0.01 * (i + 1)) for i in range(6)
        ]
        star_decs = [np.radians(target_dec)] + [
            np.radians(target_dec + 0.01 * (i + 1)) for i in range(6)
        ]
        visit_ids = list(range(84000000, 84000000 + n_visits))
        catalogs = []
        for v in range(n_visits):
            sources = [
                {
                    "coord_ra": star_ras[0],
                    "coord_dec": star_decs[0],
                    "base_CircularApertureFlux_17_0_instFlux": target_flux,
                    "base_CircularApertureFlux_17_0_instFluxErr": target_flux * 0.01,
                    "base_PixelFlags_flag_saturatedCenter": False,
                    "base_PixelFlags_flag_edge": False,
                    "deblend_nChild": 0,
                }
            ]
            for i, base in enumerate(base_fluxes):
                mult = (
                    stable_patterns[i][v] if i in stable_patterns else noisy_pattern[v]
                )
                flux = base * mult
                if inject_nan and i == 3 and v == 2:
                    flux = float("nan")
                sources.append(
                    {
                        "coord_ra": star_ras[i + 1],
                        "coord_dec": star_decs[i + 1],
                        "base_CircularApertureFlux_17_0_instFlux": flux,
                        "base_CircularApertureFlux_17_0_instFluxErr": abs(base)
                        * 0.01,
                        "base_PixelFlags_flag_saturatedCenter": False,
                        "base_PixelFlags_flag_edge": False,
                        "deblend_nChild": 0,
                    }
                )
            catalogs.append((visit_ids[v], sources))
        return catalogs, visit_ids

    def _run(inject_nan):
        catalogs, visit_ids = _make_catalogs(inject_nan)
        visit_table = _dropout_visit_table(visit_ids, n_visits)
        return _process_catalogs(
            catalogs=catalogs,
            visit_table=visit_table,
            target_ra=target_ra,
            target_dec=target_dec,
            aperture_radius=17.0,
            match_radius=2.0,
            n_comparisons=3,
            min_comparisons=3,
            min_rel_mag=0.5,
            max_rel_mag=4.0,
            min_detection_fraction=0.5,
            band_filter="",
        )

    baseline = _run(inject_nan=False)
    with_nan = _run(inject_nan=True)

    # Both runs must select the stable ensemble (indices 3,4,5): comp_sum
    # stays within ~1% of 1.0. If the NaN had ranked the stable stars out
    # of the ensemble, the noisy candidates (0-2, ~10% rms) would be
    # selected instead and comp_sum would swing by ~10%.
    assert np.max(np.abs(np.array(baseline["comp_sum"]) - 1.0)) < 0.01
    assert np.max(np.abs(np.array(with_nan["comp_sum"]) - 1.0)) < 0.01

    # The NaN only removes star j=3 from visit index 2's own ensemble (the
    # other two stable stars are still present there); every other
    # visit's ensemble -- and hence diff_flux -- is identical between the
    # two runs, i.e. the selected set of three stars did not change.
    baseline_by_visit = {int(r["visit"]): float(r["diff_flux"]) for r in baseline}
    for row in with_nan:
        v = int(row["visit"])
        if v == 84000002:
            continue
        assert abs(float(row["diff_flux"]) - baseline_by_visit[v]) < 1e-6
