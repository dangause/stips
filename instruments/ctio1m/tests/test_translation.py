"""Stack-free translation tests for the CTIO 1.0m Y4KCam hooks.

Mirrors the structure of ``instruments/nickel/tests/test_translation_golden.py``
but, because the hooks here only depend on ``stips`` (no LSST stack), they are
called directly off ``profile.hooks[...]`` with minimal dict headers built from
real Y4KCam keywords.
"""

import astropy.units as u
from astropy.time import Time
from conftest import load_ctio1m_profile

PROFILE = load_ctio1m_profile()


def _hook(name):
    return PROFILE.hooks[name]


# Real Y4KCam science header keys (from a 2011-06-09 raw frame).
SCIENCE_HEADER = {
    "OBSERVAT": "CTIO",
    "TELESCOP": "ct1m",
    "INSTRUME": "Y4KCam",
    "DETECTOR": "ITL SN3671",
    "FILTER": 3,
    "FILTERID": "V",
    "DATE-OBS": "2011-06-09T08:58:18.9",
    "MJD-OBS": 55722.373831,
    "TIMESYS": "UTC",
    "RA": "16:54:17.40",
    "DEC": "-39:51:54.9",
    "EQUINOX": 2000,
    "SECZ": 1.02,
    "EXPTIME": 120.0,
    "DARKTIME": 121.0,
    "OBSTYPE": "OBJECT",
    "IMGTYPE": "OBJECT",
    "OBJECT": "some_target",
    "DTCALDAT": "2011-06-09",
    "FILENAME": "y110609.0042.fits",
}

BIAS_HEADER = dict(
    SCIENCE_HEADER,
    OBSTYPE="bias",
    IMGTYPE="bias",
    OBJECT="bias",
    EXPTIME=0.0,
    FILENAME="y110609.0003.fits",
)

FLAT_HEADER = dict(
    SCIENCE_HEADER,
    OBSTYPE="flat",
    IMGTYPE="flat",
    OBJECT="dome flat",
    FILENAME="y110609.0010.fits",
)


def test_observation_type_science():
    # OBJECT frames map to the LSST "science" observation_type (not "object"),
    # which the pipeline's science/calibrateImage selection filters on.
    assert _hook("observation_type")(SCIENCE_HEADER) == "science"


def test_observation_type_bias():
    assert _hook("observation_type")(BIAS_HEADER) == "bias"


def test_observation_type_flat():
    assert _hook("observation_type")(FLAT_HEADER) == "flat"


def test_tracking_radec_parses_hours_and_degrees():
    coord = _hook("tracking_radec")(SCIENCE_HEADER)
    # 16h54m17.40s -> 253.5725 deg; -39:51:54.9 -> -39.8652 deg.
    assert abs(coord.ra.to_value(u.deg) - 253.5725) < 0.01
    assert abs(coord.dec.to_value(u.deg) - (-39.8652)) < 0.01


def test_exposure_id_positive_and_31bit_safe():
    exp_id = _hook("exposure_id")(SCIENCE_HEADER)
    assert isinstance(exp_id, int)
    assert 0 < exp_id < 2**31
    # days_since_2000 (end-of-exposure UTC) * 10000 + seqnum 42.
    # 2011-06-09T08:58:18.9 + 120s -> day 4178 since 2000-01-01.
    assert exp_id == 4178 * 10000 + 42


def test_visit_id_matches_exposure_id():
    assert _hook("visit_id")(SCIENCE_HEADER) == _hook("exposure_id")(SCIENCE_HEADER)


def test_day_obs_from_dtcaldat():
    assert _hook("day_obs")(SCIENCE_HEADER) == 20110609


def test_observation_id():
    assert _hook("observation_id")(SCIENCE_HEADER) == "20110609_42"


def test_datetime_begin_from_mjd():
    t0 = _hook("datetime_begin")(SCIENCE_HEADER)
    assert isinstance(t0, Time)
    assert abs(t0.mjd - 55722.373831) < 1e-6


def test_datetime_end_is_begin_plus_exptime():
    t0 = _hook("datetime_begin")(SCIENCE_HEADER)
    t1 = _hook("datetime_end")(SCIENCE_HEADER)
    assert isinstance(t1, Time)
    # 120 s after begin.
    assert abs((t1.mjd - t0.mjd) - (120.0 / 86400.0)) < 1e-9


def test_unknown_filter_raises():
    import pytest

    with pytest.raises(ValueError):
        _hook("unknown_filter")({}, "ZZZ")
