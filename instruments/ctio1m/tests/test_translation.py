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
    # MJD-OBS is authoritative (per the profile); it resolves to 2011-06-10T08:58
    # UT. DATE-OBS/DTCALDAT are set consistent with it.
    "DATE-OBS": "2011-06-10T08:58:18.9",
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
    "DTCALDAT": "2011-06-10",
    "FILENAME": "y110610.0042.fits",
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
    # days_since_2000 of the LOCAL night (from FILENAME y110610) * 10000 + seqnum.
    # 2011-06-10 is 4178 days after 2000-01-01; seqnum 42. (Here the local night
    # equals the UT day, so the value is unchanged by the local-night keying.)
    assert exp_id == 4178 * 10000 + 42


def test_visit_id_matches_exposure_id():
    assert _hook("visit_id")(SCIENCE_HEADER) == _hook("exposure_id")(SCIENCE_HEADER)


def test_day_obs_is_ut_calendar_day():
    # day_obs is the UT calendar day (drives the Butler day_obs dimension via
    # to_observing_day), derived from the authoritative MJD-OBS (2011-06-10T08:58).
    assert _hook("day_obs")(SCIENCE_HEADER) == 20110610


def test_day_obs_follows_ut_not_dtcaldat():
    # Regression: a frame taken after UT midnight has DTCALDAT on the local night
    # (2007-03-21) but a UT calendar day one ahead (2007-03-22). day_obs MUST
    # follow UT (20070322) — using DTCALDAT here would disagree with the Butler
    # dimension and break the night_to_dayobs_offset_days=1 query mapping.
    hdr = dict(
        SCIENCE_HEADER,
        **{
            "MJD-OBS": 54181.189528,  # 2007-03-22T04:32:55 UTC
            "DATE-OBS": "2007-03-22T04:32:55.250",
            "DTCALDAT": "2007-03-21",
            "EXPTIME": 120.0,
            "FILENAME": "y070321.0042.fits",
        },
    )
    assert _hook("day_obs")(hdr) == 20070322


def test_observation_id():
    assert _hook("observation_id")(SCIENCE_HEADER) == "20110610_42"


def test_exposure_id_unique_across_consecutive_nights_sharing_ut_day():
    """Regression: ids must key on the LOCAL observing night, not the UT day.

    At CTIO (-70deg longitude) a local night straddles UT midnight, and the
    Y4KCam seqnum resets each local night. Keying exposure_id / observation_id on
    the UT day (datetime_end) therefore COLLIDES: the late frames of night N and
    the early frames of night N+1 share a UT day and overlapping reset seqnums,
    so they map to the same id and the second fails Butler exposure-sync on
    ingest. The y{YYMMDD}.{seq}.fits filename carries the local night, so
    (local-night, seqnum) is the natural globally-unique key.

    Real case: SA98 nights 20100120 & 20100121 both have frames on UT 2010-01-21
    with seqnum 69 -> identical ids before this fix (18 collisions/night-pair).
    """
    late_n20 = dict(
        SCIENCE_HEADER,
        **{
            "MJD-OBS": 55217.010694,  # 2010-01-21T00:15:24 UT, local night 2010-01-20
            "DATE-OBS": "2010-01-21T00:15:24.0",
            "EXPTIME": 6.0,
            "DARKTIME": 6.2,
            "DTCALDAT": "2010-01-20",
            "FILENAME": "y100120.0069.fits",
        },
    )
    early_n21 = dict(
        SCIENCE_HEADER,
        **{
            "MJD-OBS": 55217.973704,  # 2010-01-21T23:22:08 UT, local night 2010-01-21
            "DATE-OBS": "2010-01-21T23:22:08.0",
            "EXPTIME": 6.0,
            "DARKTIME": 6.2,
            "DTCALDAT": "2010-01-21",
            "FILENAME": "y100121.0069.fits",
        },
    )
    # Both land on the same UT calendar day: day_obs is shared (decoupled, OK).
    assert _hook("day_obs")(late_n20) == _hook("day_obs")(early_n21) == 20100121
    # ...but they are physically distinct exposures and MUST get distinct ids,
    # keyed on the local night parsed from the filename.
    assert _hook("exposure_id")(late_n20) != _hook("exposure_id")(early_n21)
    assert _hook("observation_id")(late_n20) == "20100120_69"
    assert _hook("observation_id")(early_n21) == "20100121_69"


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
