"""science.py boresight-coverage preflight warning (stack-free)."""

import datetime as dt
import logging
import types

from stips.core import science


def _prof(coverage_by_date=None, offset_days=1):
    """Fake profile exposing a boresight_offset_covered hook keyed by UT date."""
    hooks = {}
    if coverage_by_date is not None:

        def _covered(d):
            key = science._coerce_date(d)  # helper defined in Task 3 Step 3
            return bool(coverage_by_date.get(key, False))

        hooks["boresight_offset_covered"] = _covered
    return types.SimpleNamespace(
        hooks=hooks,
        night_to_dayobs_offset_days=offset_days,
    )


def test_night_covered_true_for_in_window_night():
    prof = _prof({dt.date(2006, 10, 2): True})  # night 20061001 -> UT day_obs 20061002
    assert science._night_is_boresight_covered(prof, "20061001") is True


def test_night_covered_false_for_uncovered_night():
    prof = _prof({dt.date(2006, 10, 2): True})
    assert science._night_is_boresight_covered(prof, "20080601") is False


def test_night_covered_none_when_hook_absent():
    prof = _prof(coverage_by_date=None)  # no hook -> not a CTIO-style profile
    assert science._night_is_boresight_covered(prof, "20061001") is None


def test_night_covered_via_evening_ut_at_window_trailing_edge():
    # Boundary: a night whose day_obs (night+1) is OUTSIDE the window but whose
    # own (evening) UT date IS inside must still read covered -- else the trailing
    # 2010 SA98 night (day_obs 20100123, outside [01-17,01-22]) would spuriously
    # warn. Coverage checks BOTH UT dates the night spans.
    prof = _prof({dt.date(2010, 1, 22): True})  # covered; 2010-01-23 NOT in dict
    assert science._night_is_boresight_covered(prof, "20100122") is True


def test_preflight_warns_on_uncovered(caplog):
    prof = _prof({dt.date(2006, 10, 2): True})
    with caplog.at_level(logging.WARNING, logger="stips.core.science"):
        science._warn_if_uncharacterized_campaign(prof, "20080601")
    assert any(
        "no boresight-offset characterization" in r.message.lower()
        for r in caplog.records
    )


def test_preflight_silent_on_covered(caplog):
    prof = _prof({dt.date(2006, 10, 2): True})
    with caplog.at_level(logging.WARNING, logger="stips.core.science"):
        science._warn_if_uncharacterized_campaign(prof, "20061001")
    assert not any(
        "boresight-offset characterization" in r.message.lower() for r in caplog.records
    )
