"""Date-characterized boresight offset table (ctio1m), stack-free.

Replaces the hardcoded year==2006 gate: the 2006 correction and 2010 no-op are
now rows in _BORESIGHT_OFFSET_TABLE, bounded to each campaign's measured nights.
"""

import datetime as dt
from pathlib import Path

import astropy.units as u
import pytest
from stips.profile import import_instrument_submodule
from stips.testing.instrument_contract import InstrumentDirInfo, load_profile

_CTIO_DIR = Path(__file__).resolve().parents[1]
_INFO = InstrumentDirInfo(name="ctio1m", path=_CTIO_DIR)
PROFILE = load_profile(_INFO)
# The module under test, imported by name like everything else in the dir.
prof_mod = import_instrument_submodule(_CTIO_DIR, "profile")

_BASE = {"RA": "00:30:08.9", "DEC": "-46:31:22.8", "EQUINOX": 2000}


def _hdr(mjd, iso):
    return dict(_BASE, **{"MJD-OBS": mjd, "DATE-OBS": iso})


def test_2006_in_window_offset():
    # 2006-10-02 UT — inside the measured 2006 window.
    d = dt.date(2006, 10, 2)
    assert prof_mod.boresight_offset_covered(d) is True
    east, north = prof_mod.boresight_offset_arcsec(d)
    assert east == pytest.approx(257.0)
    assert north == pytest.approx(320.0)


def test_2010_in_window_zero_offset_but_covered():
    d = dt.date(2010, 1, 21)
    assert prof_mod.boresight_offset_covered(d) is True
    assert prof_mod.boresight_offset_arcsec(d) == (0.0, 0.0)


def test_out_of_window_dates_are_uncovered():
    # 2008 (no campaign) AND a 2006 date OUTSIDE the measured Sep27-Dec17 window.
    for d in (dt.date(2008, 6, 1), dt.date(2006, 6, 1), dt.date(2011, 3, 1)):
        assert prof_mod.boresight_offset_covered(d) is False
        assert prof_mod.boresight_offset_arcsec(d) == (0.0, 0.0)


def test_window_boundaries_are_inclusive():
    for d in (dt.date(2006, 9, 27), dt.date(2006, 12, 17)):
        assert prof_mod.boresight_offset_covered(d) is True
        assert prof_mod.boresight_offset_arcsec(d) == (257.0, 320.0)


def test_2006_window_end_covers_last_local_nights_ut_morning_frames():
    # Regression: the last measured local night (20061216) spans UT 2006-12-16
    # (evening) AND UT 2006-12-17 (morning). An end bound of 2006-12-16 silently
    # dropped the 12-17 morning frames (no offset applied -> astrometry
    # regression; science.py's day_obs diagnostic also wrongly flagged them
    # "uncovered"). Both UT dates of that local night must be covered.
    for d in (dt.date(2006, 12, 16), dt.date(2006, 12, 17)):
        assert prof_mod.boresight_offset_covered(d) is True
        assert prof_mod.boresight_offset_arcsec(d) == (257.0, 320.0)
    # One UT day past the window end is correctly uncovered.
    assert prof_mod.boresight_offset_covered(dt.date(2006, 12, 18)) is False
    assert prof_mod.boresight_offset_arcsec(dt.date(2006, 12, 18)) == (0.0, 0.0)


def test_none_date_is_uncovered_no_crash():
    assert prof_mod.boresight_offset_covered(None) is False
    assert prof_mod.boresight_offset_arcsec(None) == (0.0, 0.0)


def test_tracking_radec_shifts_2006_header_via_table():
    raw = PROFILE.hooks["tracking_radec"](_hdr(55217.010694, "2010-01-21T00:15:24.0"))
    shifted = PROFILE.hooks["tracking_radec"](_hdr(54010.2, "2006-10-02T04:48:00.0"))
    d_east, d_north = raw.spherical_offsets_to(shifted)
    assert d_east.to_value(u.arcsec) == pytest.approx(257.0, abs=1.0)
    assert d_north.to_value(u.arcsec) == pytest.approx(320.0, abs=1.0)
    assert shifted.ra.deg > raw.ra.deg and shifted.dec.deg > raw.dec.deg


def test_2009_wasp18_in_window_offset():
    # 2009-10-30T02:29:26 UT -- a WASP-18 TraMoS frame inside the measured window.
    d = "2009-10-30T02:29:26"
    assert prof_mod.boresight_offset_covered(d) is True
    east, north = prof_mod.boresight_offset_arcsec(d)
    assert east == pytest.approx(192.0)
    assert north == pytest.approx(308.0)


def test_2009_wasp18_window_boundaries_are_inclusive():
    for d in ("2009-10-28", "2009-10-31"):
        assert prof_mod.boresight_offset_covered(d) is True
        assert prof_mod.boresight_offset_arcsec(d) == (192.0, 308.0)


def test_2009_wasp18_adjacent_dates_are_uncovered():
    # One UT day on either side of the measured window (2009-10-27: the night
    # before the WASP-18 run's first measured night; 2009-11-01: one day past
    # the window end) must NOT inherit the WASP-18 offset.
    for d in ("2009-10-27", "2009-11-01"):
        assert prof_mod.boresight_offset_covered(d) is False
        assert prof_mod.boresight_offset_arcsec(d) == (0.0, 0.0)


def test_2011_wasp19_april_night_in_window_offset():
    # 2011-04-23T02:22:31 UT -- a WASP-19 "test" frame of local night 20110422,
    # one of the two frames the offset was measured on.
    d = "2011-04-23T02:22:31"
    assert prof_mod.boresight_offset_covered(d) is True
    east, north = prof_mod.boresight_offset_arcsec(d)
    assert east == pytest.approx(157.0)
    assert north == pytest.approx(-148.0)


def test_2011_wasp19_april_window_boundaries_are_inclusive():
    for d in ("2011-04-22", "2011-04-23"):
        assert prof_mod.boresight_offset_covered(d) is True
        assert prof_mod.boresight_offset_arcsec(d) == (157.0, -148.0)


def test_2011_landolt_and_december_nights_stay_uncovered():
    # The surrounding April/May 2011 Landolt nights and the December WASP-19
    # night were measured at <=99" and must NOT inherit the 20110422 offset.
    for d in ("2011-04-13", "2011-04-21", "2011-04-24", "2011-05-03", "2011-12-25"):
        assert prof_mod.boresight_offset_covered(d) is False
        assert prof_mod.boresight_offset_arcsec(d) == (0.0, 0.0)


def test_table_windows_do_not_overlap():
    import datetime as _d

    rows = sorted(
        prof_mod._BORESIGHT_OFFSET_TABLE,
        key=lambda row: _d.date.fromisoformat(row[0]),
    )
    for prev, cur in zip(rows, rows[1:]):
        prev_end = _d.date.fromisoformat(prev[1])
        cur_start = _d.date.fromisoformat(cur[0])
        assert prev_end < cur_start, f"overlapping windows: {prev[:2]} vs {cur[:2]}"


def test_boresight_offset_covered_registered_as_hook():
    hook = PROFILE.hooks["boresight_offset_covered"]
    assert hook(dt.date(2006, 10, 2)) is True  # in 2006 window
    assert hook(dt.date(2010, 1, 21)) is True  # covered, zero-offset
    assert hook(dt.date(2008, 6, 1)) is False  # uncharacterized
    assert hook(None) is False  # fail-closed
