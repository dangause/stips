"""Date-characterized boresight offset table (ctio1m), stack-free.

Replaces the hardcoded year==2006 gate: the 2006 correction and 2010 no-op are
now rows in _BORESIGHT_OFFSET_TABLE, bounded to each campaign's measured nights.
"""
import datetime as dt
from pathlib import Path

import astropy.units as u
import pytest
from stips.testing.instrument_contract import InstrumentDirInfo, load_profile

_INFO = InstrumentDirInfo(name="ctio1m", path=Path(__file__).resolve().parents[1])
PROFILE = load_profile(_INFO)

# Import the module under test directly for the pure table helpers.
# profile.py does `from fetch import fetch_data`, which only resolves if the
# instrument dir is on sys.path -- and that import caches ctio1m's fetch.py
# under the bare sys.modules["fetch"] key. Mirror load_profile()'s full
# handling (packages/stips/src/stips/testing/instrument_contract.py): save +
# restore BOTH sys.path and sys.modules["fetch"], so this load leaves no
# global state behind (nickel/profile.py has the same bare `from fetch
# import`, so a leaked sys.modules["fetch"] could silently resolve to the
# wrong instrument's fetch module later in the same pytest process).
import importlib.util
import sys as _sys
_CTIO_DIR = Path(__file__).resolve().parents[1]
_saved_path = list(_sys.path)
_saved_fetch = _sys.modules.get("fetch")
try:
    _sys.path.insert(0, str(_CTIO_DIR))
    _SPEC = importlib.util.spec_from_file_location(
        "ctio_profile", _CTIO_DIR / "profile.py")
    prof_mod = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(prof_mod)
finally:
    _sys.path[:] = _saved_path
    if _saved_fetch is not None:
        _sys.modules["fetch"] = _saved_fetch
    else:
        _sys.modules.pop("fetch", None)

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
    # 2008 (no campaign) AND a 2006 date OUTSIDE the measured Sep27-Dec16 window.
    for d in (dt.date(2008, 6, 1), dt.date(2006, 6, 1), dt.date(2011, 3, 1)):
        assert prof_mod.boresight_offset_covered(d) is False
        assert prof_mod.boresight_offset_arcsec(d) == (0.0, 0.0)


def test_window_boundaries_are_inclusive():
    for d in (dt.date(2006, 9, 27), dt.date(2006, 12, 16)):
        assert prof_mod.boresight_offset_covered(d) is True
        assert prof_mod.boresight_offset_arcsec(d) == (257.0, 320.0)


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


import datetime as _dt2


def test_boresight_offset_covered_registered_as_hook():
    hook = PROFILE.hooks["boresight_offset_covered"]
    assert hook(_dt2.date(2006, 10, 2)) is True     # in 2006 window
    assert hook(_dt2.date(2010, 1, 21)) is True      # covered, zero-offset
    assert hook(_dt2.date(2008, 6, 1)) is False      # uncharacterized
    assert hook(None) is False                        # fail-closed
