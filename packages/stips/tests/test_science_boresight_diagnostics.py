"""science.py boresight-coverage preflight warning + post-run diagnostic (stack-free)."""
import datetime as dt
import logging
import types

from stips.core import science


def _prof(coverage_by_date=None, offset_days=1):
    """Fake profile exposing a boresight_offset_covered hook keyed by UT date."""
    hooks = {}
    if coverage_by_date is not None:
        def _covered(d):
            key = science._coerce_date(d)   # helper defined in Task 3 Step 3
            return bool(coverage_by_date.get(key, False))
        hooks["boresight_offset_covered"] = _covered
    return types.SimpleNamespace(
        hooks=hooks, night_to_dayobs_offset_days=offset_days,
    )


def test_night_covered_true_for_in_window_night():
    prof = _prof({dt.date(2006, 10, 2): True})   # night 20061001 -> UT day_obs 20061002
    assert science._night_is_boresight_covered(prof, "20061001") is True


def test_night_covered_false_for_uncovered_night():
    prof = _prof({dt.date(2006, 10, 2): True})
    assert science._night_is_boresight_covered(prof, "20080601") is False


def test_night_covered_none_when_hook_absent():
    prof = _prof(coverage_by_date=None)          # no hook -> not a CTIO-style profile
    assert science._night_is_boresight_covered(prof, "20061001") is None


def test_preflight_warns_on_uncovered(caplog):
    prof = _prof({dt.date(2006, 10, 2): True})
    with caplog.at_level(logging.WARNING, logger="stips.core.science"):
        science._warn_if_uncharacterized_campaign(prof, "20080601")
    assert any("no boresight-offset characterization" in r.message.lower()
               for r in caplog.records)


def test_preflight_silent_on_covered(caplog):
    prof = _prof({dt.date(2006, 10, 2): True})
    with caplog.at_level(logging.WARNING, logger="stips.core.science"):
        science._warn_if_uncharacterized_campaign(prof, "20061001")
    assert not any("boresight-offset characterization" in r.message.lower()
                   for r in caplog.records)


def test_diagnostic_fires_uncovered_and_broad_failure(caplog):
    prof = _prof({dt.date(2006, 10, 2): True})
    with caplog.at_level(logging.ERROR, logger="stips.core.science"):
        science._diagnose_uncharacterized_failure(prof, "20080601", succeeded=2, failed=40)
    msgs = " ".join(r.message.lower() for r in caplog.records)
    assert "uncharacterized" in msgs and "blind-solve" in msgs


def test_diagnostic_silent_when_covered(caplog):
    prof = _prof({dt.date(2006, 10, 2): True})
    with caplog.at_level(logging.ERROR, logger="stips.core.science"):
        science._diagnose_uncharacterized_failure(prof, "20061001", succeeded=0, failed=45)
    assert not any("uncharacterized" in r.message.lower() for r in caplog.records)


def test_diagnostic_silent_when_failure_below_threshold(caplog):
    prof = _prof({dt.date(2006, 10, 2): True})
    with caplog.at_level(logging.ERROR, logger="stips.core.science"):
        science._diagnose_uncharacterized_failure(prof, "20080601", succeeded=40, failed=5)
    assert not any("uncharacterized" in r.message.lower() for r in caplog.records)


def test_diagnostic_silent_when_no_attempts(caplog):
    prof = _prof({dt.date(2006, 10, 2): True})
    with caplog.at_level(logging.ERROR, logger="stips.core.science"):
        science._diagnose_uncharacterized_failure(prof, "20080601", succeeded=0, failed=0)
    assert not any("uncharacterized" in r.message.lower() for r in caplog.records)
