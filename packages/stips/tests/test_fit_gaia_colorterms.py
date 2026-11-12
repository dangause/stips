import numpy as np
import pytest

from scripts.analysis.fit_gaia_colorterms_landolt import (
    GAIA_AB_ZEROPOINTS,
    fit_band,
    gaia_ab_mag,
)


def test_gaia_ab_zeropoints_match_lsst_converter():
    # ConvertGaiaManager._getFluxes (meas_algorithms convertRefcatManager.py).
    assert GAIA_AB_ZEROPOINTS == {
        "phot_g_mean": 25.7934,
        "phot_bp_mean": 25.3806,
        "phot_rp_mean": 25.1161,
    }


def test_gaia_ab_mag_unit_flux_gives_zero_point():
    for zp in GAIA_AB_ZEROPOINTS.values():
        assert gaia_ab_mag(1.0, zp) == pytest.approx(zp)


def test_gaia_ab_mag_is_pogson_and_vectorised():
    zp = GAIA_AB_ZEROPOINTS["phot_g_mean"]
    mags = gaia_ab_mag([100.0, 1.0e4], zp)
    assert mags == pytest.approx([zp - 5.0, zp - 10.0])


def test_gaia_ab_mag_non_positive_flux_is_nan():
    zp = GAIA_AB_ZEROPOINTS["phot_rp_mean"]
    assert np.all(np.isnan(gaia_ab_mag([0.0, -1.0, np.nan], zp)))


def test_fit_band_recovers_known_terms():
    rng = np.random.default_rng(1)
    primary = rng.uniform(10, 15, 200)
    secondary = primary - rng.uniform(0.2, 1.8, 200)
    landolt = (
        primary + 0.35 + (-0.42) * (primary - secondary) + rng.normal(0, 0.005, 200)
    )
    c0, c1, rms = fit_band(landolt, primary, secondary)
    assert abs(c0 - 0.35) < 0.01
    assert abs(c1 + 0.42) < 0.01
    assert rms < 0.01


def test_fit_band_clips_outliers():
    # NOTE: the brief's literal version of this test used a constant
    # `secondary = primary - 1.0`, which makes the colour term
    # `primary - secondary` identical for every star. That collapses the
    # design matrix in np.polyfit(x, y, 1) (the slope and intercept columns
    # become identical), so fit_band's sigma-clip discards every point on
    # the first iteration and np.polyfit crashes on an empty array -- this
    # is a data bug in the test, not a bug in fit_band. Varying the colour
    # across stars (as the first test already does) keeps the same "one bad
    # star among otherwise-perfect photometry" intent while making the
    # linear fit well-posed.
    primary = np.linspace(10, 15, 50)
    secondary = primary - np.linspace(0.5, 1.5, 50)
    landolt = primary + 0.1 - 0.3 * (primary - secondary)
    landolt[3] += 2.0  # one bad star
    c0, c1, rms = fit_band(landolt, primary, secondary)
    assert abs(c1 + 0.3) < 1e-6
