"""Epoch-scoped 2006 boresight-offset regression (ctio1m).

The 2006 Y4KCam run carries a systematic telescope pointing error: the true field
center is +257" EAST and +320" NORTH of the header RA/DEC (measured by blind
astrometry.net solves on one science frame per night across all four 2006 nights;
camera scale/orientation/distortion confirmed correct). ``tracking_radec`` applies
this constant on-sky offset for the 2006 run ONLY and leaves 2010+ frames unchanged.

Stack-free: exercises the profile hook directly on synthetic headers.
"""

from pathlib import Path

import astropy.units as u
import pytest
from stips.testing.instrument_contract import InstrumentDirInfo, load_profile

_INFO = InstrumentDirInfo(name="ctio1m", path=Path(__file__).resolve().parents[1])
PROFILE = load_profile(_INFO)

# A TPheA-like pointing (RA 7.537 deg, Dec -46.523 deg) in header sexagesimal form.
_RA = "00:30:08.9"  # hours
_DEC = "-46:31:22.8"  # deg
_BASE = {"RA": _RA, "DEC": _DEC, "EQUINOX": 2000}

# Measured 2006 offset (mean over 4 nights); the fix applies the mean exactly.
_EXPECT_EAST_ARCSEC = 257.0
_EXPECT_NORTH_ARCSEC = 320.0


def _hdr_2006():
    # MJD-OBS 54010.2 == 2006-10-02T04:48 UT (a real 2006-run night).
    return dict(_BASE, **{"MJD-OBS": 54010.2, "DATE-OBS": "2006-10-02T04:48:00.0"})


def _hdr_2010():
    # MJD-OBS 55217.01 == 2010-01-21 UT (SA98 run; must be UNCHANGED).
    return dict(_BASE, **{"MJD-OBS": 55217.010694, "DATE-OBS": "2010-01-21T00:15:24.0"})


def _raw_coord():
    """The unshifted parsed header coord (via a 2010 header, which gets no offset)."""
    return PROFILE.hooks["tracking_radec"](_hdr_2010())


def test_2006_frame_is_shifted_east_and_north():
    raw = _raw_coord()
    shifted = PROFILE.hooks["tracking_radec"](_hdr_2006())
    d_east, d_north = raw.spherical_offsets_to(shifted)
    # Offset must be +257" East (RA*cosDec) and +320" North (Dec), within ~1".
    assert d_east.to_value(u.arcsec) == pytest.approx(_EXPECT_EAST_ARCSEC, abs=1.0)
    assert d_north.to_value(u.arcsec) == pytest.approx(_EXPECT_NORTH_ARCSEC, abs=1.0)
    # RA must INCREASE (East) and Dec must INCREASE (North).
    assert shifted.ra.deg > raw.ra.deg
    assert shifted.dec.deg > raw.dec.deg
    # Total offset ~412" (well beyond the ~115" matcher offset window).
    assert raw.separation(shifted).arcsec == pytest.approx(412.0, abs=5.0)


def test_2010_frame_is_unchanged():
    raw = _raw_coord()
    same = PROFILE.hooks["tracking_radec"](_hdr_2010())
    assert raw.separation(same).arcsec < 1e-6


def test_frame_and_units_preserved_for_2006():
    # The correction must not change the coordinate frame (FK5 via EQUINOX 2000).
    raw = _raw_coord()
    shifted = PROFILE.hooks["tracking_radec"](_hdr_2006())
    assert shifted.frame.name == raw.frame.name == "fk5"
