# CTIO date-characterized boresight offset table + uncharacterized-campaign diagnostics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `year == 2006` boresight-offset gate with a date-characterized offset table, and make an *uncharacterized* CTIO campaign announce itself (preflight warning + actionable post-run diagnostic) instead of failing silently.

**Architecture:** Two components. (1) `instruments/ctio1m/profile.py` gains a `_BORESIGHT_OFFSET_TABLE` of `(start_date, end_date, ΔEast″, ΔNorth″, provenance)` rows and a datetime→entry lookup; `tracking_radec` applies the matched offset (a `(0,0)` row is a no-op), and a `boresight_offset_covered` hook reports whether a date is characterized. (2) `packages/stips/src/stips/core/science.py` reads that hook to log a preflight WARNING for an uncovered night and, post-run, an actionable ERROR when an uncovered night's astrometry fails broadly (≥50% of visits).

**Tech Stack:** Python 3.12, astropy (`Time`, `SkyCoord`, units), pytest. Stack-free throughout except the final real-data validation (LSST `v30_0_3` via the existing single-visit harness).

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-21-ctio-boresight-offset-table-design.md`.
- **Branch:** work on `feature/ctio-boresight-offset-table` (already cut from `feature/ctio-cycle2-astrometry`). This branch merges back into `feature/ctio-cycle2-astrometry` before PR #34 lands in `dev`.
- **Behavior parity:** the 2006 correction must stay numerically identical (+257″ East / +320″ North) and 2010+ must stay byte-identical — only the *mechanism* changes (constant+`_is_2006_run` → table lookup). The existing `instruments/ctio1m/tests/test_boresight_offset_epoch.py` must keep passing unchanged.
- **Offset direction:** East = +RA·cosDec, North = +Dec; applied via `SkyCoord.spherical_offsets_by(ΔEast, ΔNorth)`. A 2006 header's RA and Dec both INCREASE.
- **Measured-extent ranges (verbatim from spec):** rows are bounded to the measured nights, NOT month/year-padded:
  - `("2006-09-27", "2006-12-16", 257.0, 320.0, ...)`
  - `("2010-01-17", "2010-01-22", 0.0, 0.0, ...)`
- **Coverage semantics:** a matching row → `covered=True` (offset may be 0); no matching row → `covered=False` (→ warn/diagnose). Range bounds are inclusive.
- **Diagnostic threshold:** post-run diagnostic fires only when a night is `covered=False` AND the astrometry failure fraction ≥ `0.50`. Covered nights and below-threshold failures get no special handling (no nagging 2010).
- **Out of scope:** on-the-fly blind-solve fallback; any `maxOffsetPix`/matcher change (tolerance approach was tested and rejected); other instruments; per-filter handling (offset is band-independent).
- **Fail-closed:** if an exposure's date cannot be determined, treat as uncovered / no offset (never crash, never mis-apply).
- **Git:** frequent commits. NEVER add `Co-Authored-By` or credit Claude. `docs/superpowers/` is gitignored — commit plan/spec with `git add -f`.

---

### Task 1: Offset table + datetime lookup in the profile

**Files:**
- Modify: `instruments/ctio1m/profile.py` (replace `_BORESIGHT_2006_DELTA_*` constants + `_is_2006_run`, lines ~192-217; update `tracking_radec` ~347-383)
- Test: `instruments/ctio1m/tests/test_boresight_offset_table.py` (new)

**Interfaces:**
- Consumes: existing `_datetime_begin(header) -> astropy.time.Time | None` (profile.py:165).
- Produces (module-level in `profile.py`):
  - `_BORESIGHT_OFFSET_TABLE: list[tuple[str, str, float, float, str]]`
  - `_boresight_offset_entry(dt) -> tuple[str, str, float, float, str] | None` — `dt` is a `datetime.date`/`datetime.datetime`/`astropy.time.Time` or `None`; returns the row whose `[start, end]` (inclusive, parsed as UT dates) contains `dt.date()`, else `None`. Returns `None` if `dt is None`.
  - `boresight_offset_arcsec(dt) -> tuple[float, float]` — matched `(ΔEast, ΔNorth)` in arcsec, else `(0.0, 0.0)`.
  - `boresight_offset_covered(dt) -> bool` — `True` iff `_boresight_offset_entry(dt) is not None`.
- `tracking_radec` now computes `dt = _datetime_begin(header)` and applies `boresight_offset_arcsec(dt)` (a `(0,0)` shift is a no-op).

- [ ] **Step 1: Write the failing test**

```python
# instruments/ctio1m/tests/test_boresight_offset_table.py
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
import importlib.util
_SPEC = importlib.util.spec_from_file_location(
    "ctio_profile", Path(__file__).resolve().parents[1] / "profile.py")
prof_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(prof_mod)

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../stips-cycle2-wt && .venv/bin/python -m pytest instruments/ctio1m/tests/test_boresight_offset_table.py -v`
Expected: FAIL — `AttributeError: module 'ctio_profile' has no attribute 'boresight_offset_covered'` (helpers/table not defined yet).

- [ ] **Step 3: Replace the constants + `_is_2006_run` with the table + lookup**

In `instruments/ctio1m/profile.py`, delete `_BORESIGHT_2006_DELTA_EAST_ARCSEC`, `_BORESIGHT_2006_DELTA_NORTH_ARCSEC` (lines ~206-207) and `_is_2006_run` (lines ~210-217), and replace the whole `# --- 2006-run systematic boresight pointing offset ---` block (from ~192) with:

```python
# --- Date-characterized boresight pointing offsets (see tracking_radec) --------
# The CTIO Y4KCam mount carries a per-campaign systematic pointing offset: the
# TRUE field center is EAST/NORTH of the header RA/DEC by a campaign-specific
# amount (measured by BLIND astrometry.net solves). It is a pure boresight
# TRANSLATION -- camera plate scale (0.2889"/pix), orientation (PA~0) and
# distortion (negligible) were all confirmed correct -- NOT a parse/geometry bug.
#
# A row means the campaign has been CHARACTERIZED; the offset may be 0. Ranges are
# bounded to the MEASURED extent of each campaign (first/last night we have data
# for), NOT padded to month/year -- the range asserts what was VERIFIED, not mount
# stability across unmeasured time. An unmeasured night INSIDE a window inherits
# that offset (mild "stable within one run" interpolation); a night OUTSIDE every
# window is uncovered (offset 0) and is flagged by science.py's diagnostics.
#
# (start_date, end_date, delta_east_arcsec, delta_north_arcsec, provenance)
_BORESIGHT_OFFSET_TABLE = [
    ("2006-09-27", "2006-12-16", 257.0, 320.0,
     "blind astrometry.net solve, 4 nights 20060927-20061216 (2026-07); "
     "dRA*cosDec +257\" (std 24), dDec +320\" (std 57), ~412\" @ PA~39 E-of-N"),
    ("2010-01-17", "2010-01-22", 0.0, 0.0,
     "SA98 run; ~60\" offset already within matcher tolerance, no correction"),
]


def _as_date(dt):
    """Coerce a datetime/date/astropy.time.Time/None to a datetime.date (or None)."""
    import datetime as _d

    if dt is None:
        return None
    if isinstance(dt, _d.date) and not isinstance(dt, _d.datetime):
        return dt
    if isinstance(dt, _d.datetime):
        return dt.date()
    # astropy.time.Time
    to_dt = getattr(dt, "datetime", None)
    if to_dt is not None:
        return to_dt.date()
    return None


def _boresight_offset_entry(dt):
    """Row whose inclusive [start, end] UT-date range contains ``dt``, else None.

    Fail-closed: returns None if the date cannot be determined.
    """
    import datetime as _d

    d = _as_date(dt)
    if d is None:
        return None
    for row in _BORESIGHT_OFFSET_TABLE:
        start = _d.date.fromisoformat(row[0])
        end = _d.date.fromisoformat(row[1])
        if start <= d <= end:
            return row
    return None


def boresight_offset_arcsec(dt):
    """(delta_east_arcsec, delta_north_arcsec) for the campaign, else (0.0, 0.0)."""
    row = _boresight_offset_entry(dt)
    return (row[2], row[3]) if row is not None else (0.0, 0.0)


def boresight_offset_covered(dt):
    """True iff the observation date falls in a characterized campaign window."""
    return _boresight_offset_entry(dt) is not None
```

Then update `tracking_radec` (the `if _is_2006_run(header):` block, ~377-381) to:

```python
    east_arcsec, north_arcsec = boresight_offset_arcsec(_datetime_begin(header))
    if east_arcsec or north_arcsec:
        coord = coord.spherical_offsets_by(
            east_arcsec * u.arcsec,
            north_arcsec * u.arcsec,
        )
```

Also update `tracking_radec`'s docstring: replace the "For the 2006 Y4KCam run ONLY ..." sentence with "A campaign-specific boresight offset (see ``_BORESIGHT_OFFSET_TABLE``) is applied when the exposure date falls in a characterized window; uncharacterized dates get no shift."

- [ ] **Step 4: Run the new test + the existing regression test**

Run: `.venv/bin/python -m pytest instruments/ctio1m/tests/test_boresight_offset_table.py instruments/ctio1m/tests/test_boresight_offset_epoch.py -v`
Expected: all PASS — the new table tests AND the unchanged `test_boresight_offset_epoch.py` (proving numeric parity: 2006 shifted +257/+320, 2010 unchanged).

- [ ] **Step 5: Run the full ctio1m + contract suite (no regressions)**

Run: `.venv/bin/python -m pytest instruments/ctio1m/tests/ packages/stips/tests/test_instrument_contracts.py -q`
Expected: green (the 2011 `SAMPLE_HEADER` contract value is unchanged — 2011 is uncovered → no shift).

- [ ] **Step 6: Commit**

```bash
git add instruments/ctio1m/profile.py instruments/ctio1m/tests/test_boresight_offset_table.py
git commit -m "refactor(ctio1m): date-characterized boresight offset table (replaces year==2006 gate)"
```

---

### Task 2: Expose the coverage helper as a profile hook

**Files:**
- Modify: `instruments/ctio1m/profile.py` (register `boresight_offset_covered` as a hook, near the other `@hook(profile)` registrations ~253+)
- Test: `instruments/ctio1m/tests/test_boresight_offset_table.py` (add one test)

**Interfaces:**
- Consumes: `boresight_offset_covered(dt)` from Task 1.
- Produces: `profile.hooks["boresight_offset_covered"]` — callable `(dt) -> bool`, so venv-side `science.py` can query coverage via `config.require_profile().hooks`.

- [ ] **Step 1: Write the failing test**

Append to `instruments/ctio1m/tests/test_boresight_offset_table.py`:

```python
import datetime as _dt2


def test_boresight_offset_covered_registered_as_hook():
    hook = PROFILE.hooks["boresight_offset_covered"]
    assert hook(_dt2.date(2006, 10, 2)) is True     # in 2006 window
    assert hook(_dt2.date(2010, 1, 21)) is True      # covered, zero-offset
    assert hook(_dt2.date(2008, 6, 1)) is False      # uncharacterized
    assert hook(None) is False                        # fail-closed
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest "instruments/ctio1m/tests/test_boresight_offset_table.py::test_boresight_offset_covered_registered_as_hook" -v`
Expected: FAIL — `KeyError: 'boresight_offset_covered'` (hook not registered).

- [ ] **Step 3: Register the hook**

In `instruments/ctio1m/profile.py`, next to the other `@hook(profile)` functions (~253+), register the module-level `boresight_offset_covered` under an explicit hook name, using a DISTINCT function name to avoid rebinding the module symbol. The `hook` decorator is `hook(profile, name=None)` → `profile.hooks[name or fn.__name__] = fn` and returns `fn` unchanged, so passing `name=` registers under the string key while the Task-1 module function `boresight_offset_covered` stays intact:

```python
@hook(profile, name="boresight_offset_covered")
def _boresight_offset_covered_hook(dt):
    """Hook: True iff the observation date is in a characterized campaign window.

    Registered under the key ``boresight_offset_covered`` so science.py can query
    it via ``profile.hooks``. A thin wrapper over the module-level lookup (no
    duplicated logic); named distinctly so it does not shadow that function.
    """
    return boresight_offset_covered(dt)
```

Note: the module-level `boresight_offset_covered` (Task 1) remains the single source of logic and is what direct callers/tests use; `profile.hooks["boresight_offset_covered"]` is the registered entry point for venv-side `science.py`.

- [ ] **Step 4: Run the test + full ctio1m suite**

Run: `.venv/bin/python -m pytest instruments/ctio1m/tests/ -q`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add instruments/ctio1m/profile.py instruments/ctio1m/tests/test_boresight_offset_table.py
git commit -m "feat(ctio1m): register boresight_offset_covered profile hook"
```

---

### Task 3: Preflight warning for an uncharacterized campaign

**Files:**
- Modify: `packages/stips/src/stips/core/science.py` (add a helper + call it in `run()` after `prof`/`night` are resolved, ~1015)
- Test: `packages/stips/tests/test_science_boresight_diagnostics.py` (new)

**Interfaces:**
- Consumes: `night_to_day_obs(night, offset_days)` (`stips.core.pipeline:82`); the active profile's `hooks.get("boresight_offset_covered")` and `night_to_dayobs_offset_days`.
- Produces:
  - `_night_is_boresight_covered(prof, night) -> bool | None` — maps the observing night to its UT `day_obs` date and calls the profile's `boresight_offset_covered` hook. Returns `None` if the profile has no such hook (non-CTIO instruments), so callers can no-op.
  - `_warn_if_uncharacterized_campaign(prof, night) -> None` — logs a WARNING when coverage is explicitly `False`.

- [ ] **Step 1: Write the failing test**

```python
# packages/stips/tests/test_science_boresight_diagnostics.py
"""science.py boresight-coverage preflight warning + post-run diagnostic (stack-free)."""
import datetime as dt
import logging
import types

import pytest

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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest packages/stips/tests/test_science_boresight_diagnostics.py -v`
Expected: FAIL — `AttributeError: module 'stips.core.science' has no attribute '_coerce_date'` / `_night_is_boresight_covered`.

- [ ] **Step 3: Implement the coverage helpers + preflight warning**

Add to `packages/stips/src/stips/core/science.py` (near the top-level helpers, after `log = logging.getLogger(__name__)` ~33). Add `import datetime as _date_mod` and `from stips.core.pipeline import night_to_day_obs` (extend the existing `stips.core.pipeline` import block):

```python
def _coerce_date(d):
    """datetime/date/astropy.Time/ISO-str -> datetime.date (or None). Fail-closed."""
    import datetime as _d

    if d is None:
        return None
    if isinstance(d, _d.date) and not isinstance(d, _d.datetime):
        return d
    if isinstance(d, _d.datetime):
        return d.date()
    to_dt = getattr(d, "datetime", None)     # astropy.time.Time
    if to_dt is not None:
        return to_dt.date()
    if isinstance(d, str):
        try:
            return _d.date.fromisoformat(d[:10])
        except ValueError:
            return None
    return None


def _night_is_boresight_covered(prof, night):
    """Whether the night's campaign has a characterized boresight offset.

    Maps the observing night (local) to its UT day_obs date and queries the
    profile's ``boresight_offset_covered`` hook. Returns None if the profile has
    no such hook (e.g. a non-CTIO instrument) so callers can no-op.

    The night->UT-date mapping uses ``night_to_dayobs_offset_days`` (CTIO: 1);
    the ~1-day slop is immaterial to coverage because the table windows have
    multi-day margin from real observing nights.
    """
    hook = getattr(prof, "hooks", {}).get("boresight_offset_covered")
    if hook is None:
        return None
    offset = getattr(prof, "night_to_dayobs_offset_days", 1)
    day_obs = night_to_day_obs(night, offset)          # 'YYYYMMDD'
    ut_date = _coerce_date(f"{day_obs[:4]}-{day_obs[4:6]}-{day_obs[6:8]}")
    return bool(hook(ut_date))


def _warn_if_uncharacterized_campaign(prof, night):
    """Log a WARNING when the night's campaign has no boresight characterization."""
    covered = _night_is_boresight_covered(prof, night)
    if covered is False:
        log.warning(
            "Night %s: this campaign has no boresight-offset characterization for "
            "this instrument. If astrometry fails broadly it likely needs one "
            "(blind-solve one exposure, measure the RA/Dec offset, add a row to the "
            "instrument profile's boresight-offset table).",
            night,
        )
```

Then call the preflight warning inside `run()` right after `cols = CollectionNames(...)` (~1015):

```python
    _warn_if_uncharacterized_campaign(prof, night)
```

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m pytest packages/stips/tests/test_science_boresight_diagnostics.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/stips/src/stips/core/science.py packages/stips/tests/test_science_boresight_diagnostics.py
git commit -m "feat(science): preflight warning for uncharacterized CTIO boresight campaign"
```

---

### Task 4: Post-run actionable diagnostic on broad astrometry failure

**Files:**
- Modify: `packages/stips/src/stips/core/science.py` (add a diagnostic helper + call it in `run()` after `_final_counts`, ~1108)
- Test: `packages/stips/tests/test_science_boresight_diagnostics.py` (add tests)

**Interfaces:**
- Consumes: `_night_is_boresight_covered(prof, night)` (Task 3); the per-night counts `total_succeeded` and `last_attempt_failed` computed by `_final_counts` (`science.py:868/1108`); the pre-processing `match_count` (~1067).
- Produces:
  - `_BORESIGHT_FAIL_FRACTION_THRESHOLD = 0.50` (module constant).
  - `_diagnose_uncharacterized_failure(prof, night, succeeded, failed) -> None` — when the night is `covered=False` AND `failed / (succeeded + failed) >= 0.50` (guard against divide-by-zero: no attempts → no diagnostic), log an ERROR naming the likely cause + fix.

- [ ] **Step 1: Write the failing test**

Append to `packages/stips/tests/test_science_boresight_diagnostics.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest "packages/stips/tests/test_science_boresight_diagnostics.py::test_diagnostic_fires_uncovered_and_broad_failure" -v`
Expected: FAIL — `AttributeError: ... '_diagnose_uncharacterized_failure'`.

- [ ] **Step 3: Implement the post-run diagnostic**

Add to `science.py` (next to the Task-3 helpers):

```python
_BORESIGHT_FAIL_FRACTION_THRESHOLD = 0.50


def _diagnose_uncharacterized_failure(prof, night, succeeded, failed):
    """Actionable ERROR when an uncharacterized night's astrometry failed broadly.

    Most visits failing on an uncharacterized campaign is the signature of an
    uncorrected boresight pointing offset (the 2006 failure mode). A few failures
    are normal per-visit issues, so only fire at/above the fraction threshold.
    """
    total = succeeded + failed
    if total == 0:
        return
    if _night_is_boresight_covered(prof, night) is not False:
        return
    if failed / total < _BORESIGHT_FAIL_FRACTION_THRESHOLD:
        return
    log.error(
        "Night %s: %d/%d science visits failed astrometry on a campaign with NO "
        "boresight-offset characterization. This is the signature of an "
        "uncorrected telescope pointing offset (cf. the 2006 CTIO run, ~7' off). "
        "Fix: blind-solve one exposure (e.g. astrometry.net), measure the RA/Dec "
        "offset vs the header pointing, and add a row to the instrument profile's "
        "boresight-offset table; then re-run.",
        night, failed, total,
    )
```

Then call it in `run()` immediately after `total_succeeded, last_attempt_failed = _final_counts(attempts, plog)` (~1108), BEFORE the `if not attempts.any_success:` branch, so it fires on both the all-fail and partial-fail paths:

```python
    _diagnose_uncharacterized_failure(
        prof, night, total_succeeded, last_attempt_failed
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest packages/stips/tests/test_science_boresight_diagnostics.py -v`
Expected: all PASS (Task 3 + Task 4 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/stips/src/stips/core/science.py packages/stips/tests/test_science_boresight_diagnostics.py
git commit -m "feat(science): actionable diagnostic when uncharacterized campaign fails astrometry broadly"
```

---

### Task 5: Real-data validation + suite + lint + merge to the feature branch

**Files:** none new (validation via the existing single-visit harness `.superpowers/sdd/harness/one_visit_isr.sh`).

**Interfaces:** consumes the committed Tasks 1-4.

- [ ] **Step 1: Validate the 2006 correction still works (parity via the table)**

The offset now comes from the table, not `_is_2006_run` — confirm behavior is unchanged on real data. No re-ingest needed (translator applies at read time).

```bash
# from the worktree, detached; poll the log
nohup zsh .superpowers/sdd/harness/one_visit_isr.sh 24650220 \
  instruments/ctio1m/configs/calibrateImage/ctio_dense.py tablecheck \
  > tablecheck.log 2>&1 < /dev/null & disown
# poll: grep -iE 'iteration [0-9]+: found|BadAstrom|Succeeded' tablecheck.log
```
Expected: NGC2298 24650220 astrometry converges sub-arcsec (~0.069″), matching the pre-refactor result. If it does NOT, the table lookup differs from the old constant — stop and fix Task 1.

- [ ] **Step 2: Confirm 2010 seed is still a no-op**

Run a stack-free check that the 2010 header yields no shift (already covered by `test_boresight_offset_epoch.py::test_2010_frame_is_unchanged` and the table tests). Record in the ledger that 2010 parity holds by unit test (no separate stack run needed — 2010 is `(0,0)` by table row + covered).

- [ ] **Step 3: Full plain-venv suite + lint on changed files**

```bash
.venv/bin/python -m pytest instruments/ctio1m/tests/ packages/stips/tests/ scripts/analysis/tests/ packages/obs_stips/tests/ -q
.venv/bin/ruff check instruments/ctio1m/profile.py \
  instruments/ctio1m/tests/test_boresight_offset_table.py \
  packages/stips/src/stips/core/science.py \
  packages/stips/tests/test_science_boresight_diagnostics.py
```
Expected: green; lint clean on the changed files (repo-wide ruff has a large pre-existing baseline — ignore unrelated files).

- [ ] **Step 4: Request code review**

Use `superpowers:requesting-code-review` on the branch diff (`feature/ctio-cycle2-astrometry..feature/ctio-boresight-offset-table`). Focus: numeric parity with the old gate, coverage semantics (covered-but-zero vs uncovered), the night→UT-date mapping, the divide-by-zero guard, fail-closed on missing dates. Fix any Critical/Important findings.

- [ ] **Step 5: Merge the sub-branch back into the feature branch**

```bash
git checkout feature/ctio-cycle2-astrometry
git merge --no-ff feature/ctio-boresight-offset-table \
  -m "merge: date-characterized boresight offset table + uncharacterized-campaign diagnostics"
.venv/bin/python -m pytest instruments/ctio1m/tests/ packages/stips/tests/ -q   # post-merge sanity
git push origin feature/ctio-cycle2-astrometry
```
Expected: fast, clean merge (sub-branch was cut from this branch's HEAD; only additive changes). PR #34 now includes the generalization. Update `.superpowers/sdd/progress.md` noting the merge.

---

## Self-Review

**Spec coverage:**
- Offset table + measured-extent ranges + lookup (`_BORESIGHT_OFFSET_TABLE`, `_boresight_offset_entry`, `boresight_offset_arcsec`, `boresight_offset_covered`) → Task 1. ✓
- `tracking_radec` applies table offset; `(0,0)` no-op; numeric parity + 2010 unchanged → Task 1 (Steps 3-5) + Task 5 (Steps 1-2). ✓
- Coverage exposed to orchestration (hook) → Task 2. ✓
- Preflight WARNING for uncovered campaign → Task 3. ✓
- Post-run actionable diagnostic gated on `uncovered AND fail-fraction ≥ 0.50` (with covered/below-threshold/no-attempt silence) → Task 4. ✓
- Within-window interpolation + fail-closed semantics → Task 1 (comment + `test_none_date_is_uncovered_no_crash`, `test_out_of_window_dates_are_uncovered`). ✓
- Real-data validation + regression + suite + review + merge-back → Task 5. ✓
- Per-filter handling excluded; matcher/`maxOffsetPix` untouched; blind-solve fallback out of scope → Global Constraints. ✓

**Placeholder scan:** none — every step has concrete code/commands. The night→UT date and the threshold are concrete (`night_to_day_obs`, `0.50`).

**Type consistency:** `_boresight_offset_entry`/`boresight_offset_arcsec`/`boresight_offset_covered` signatures defined in Task 1 and reused verbatim in Tasks 2-4. `_night_is_boresight_covered`/`_coerce_date`/`_diagnose_uncharacterized_failure` defined in Task 3/4 and used in their tests. `night_to_day_obs(night, offset_days)` matches `pipeline.py:82`. The `boresight_offset_covered` module-function vs hook name collision is called out explicitly in Task 2 Step 3.

**Scope check:** single focused feature (generalize the offset gate + add diagnostics), one sub-branch, merges back into the feature branch before the existing PR. No unrelated refactoring.
