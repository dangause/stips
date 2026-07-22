# CTIO date-characterized boresight offsets + uncharacterized-campaign diagnostics (design)

**Date:** 2026-07-21
**Workstream:** CTIO 1.0m / Y4KCam astrometry robustness. Follow-up to the epoch-scoped
2006 boresight-offset fix (`ea396ab` on `feature/ctio-cycle2-astrometry`, PR #34).
**Branch:** `feature/ctio-boresight-offset-table`, cut from `feature/ctio-cycle2-astrometry`;
merges back into that branch before it lands in `dev`.
**Status:** design (approved) — ready for writing-plans.

## Problem

The committed 2006 fix corrects a systematic ~7′ telescope pointing offset in the 2006
Y4KCam run by shifting the seed WCS **+257″ East / +320″ North**, gated on a hardcoded
`year == 2006` check (`profile.py:_is_2006_run` + two module constants). This is correct
for all data on disk (2006 + 2010) but embeds an **unverified assumption** that only 2006
carries such an offset:

- The offset is a **mount pointing error**, not a fixed instrument property: it measured
  ~440″ in 2006 but ~60″ in 2010, so it varies per campaign.
- It is **not recoverable from the FITS header**: CTIO Y4KCam raws record only the
  *commanded* target `RA`/`DEC` (plus `LST`/`HA` derived from it) — there is no `TELRA`/
  `TELDEC`, WCS, or offset keyword giving the *actual* pointing. Verified on both epochs.
- A **tolerance-only workaround was tested and rejected**: with the correction disabled and
  `maxOffsetPix=2000`, the dense NGC2298 core converged (0.059″) but the sparse T Phe field
  false-matched (11.44″). Widening the matcher search leaves typical sparse/standard fields
  broken, so it is not a general fix.

Consequently any future pre-/post-2010 campaign with its own pointing offset would fail the
same way, and — because there is no metadata signal — fail **silently** (sparse fields die
with generic `BadAstrometryFit`, no indication that the cause is an uncharacterized offset).

## Goals

1. Replace the hardcoded `year == 2006` + constants with a **date-characterized offset
   table**, so a campaign's correction is a reviewed data row (measured once), not a code
   assumption.
2. Make an uncharacterized campaign **announce itself** rather than fail silently: a preflight
   warning, escalating to a specific, actionable error when astrometry actually fails broadly.
3. Preserve the committed behavior exactly for the data we have (2006 corrected, 2010
   unchanged).

**Non-goal:** the on-the-fly blind-solve fallback (measure the offset automatically when
astrometry fails). That is a larger, separate follow-up; this design deliberately stops at
the table + diagnostics.

## Design

### Component 1 — Profile: offset table + lookup (`instruments/ctio1m/profile.py`)

Replace `_is_2006_run` and the two `_BORESIGHT_2006_DELTA_*` constants with:

```python
# (start_date, end_date, delta_east_arcsec, delta_north_arcsec, provenance)
# A row means the campaign has been CHARACTERIZED; the offset may be 0.
# Ranges are bounded to the MEASURED extent of each campaign (the actual
# first/last night we have data for) — NOT padded to month/year boundaries.
# The range is a claim about what was VERIFIED, not about mount stability
# across unmeasured time.
_BORESIGHT_OFFSET_TABLE = [
    ("2006-09-27", "2006-12-16", 257.0, 320.0,
     "blind astrometry.net solve, 4 nights 20060927-20061216 (2026-07); offset stable ~257/320\""),
    ("2010-01-17", "2010-01-22",   0.0,   0.0,
     "SA98 run; ~60\" offset within matcher tolerance, no correction needed"),
]
```

**Why measured-extent ranges (not padded):** we have only two short campaigns, so we
cannot determine the true validity windows — a broad `year == 2006`-style range would
re-introduce exactly the unverified assumption this work removes. Each range therefore
spans only the campaign nights we actually measured. This leaves ONE residual,
explicitly-named assumption: an **unmeasured night *within* a window** (e.g. an October
2006 night between the measured endpoints) inherits that window's offset by interpolation —
a mild "mount stable within one observing run" assumption. It is far weaker than
"all of 2006," and if it is ever wrong the Component-2 diagnostic (below) flags it. Any
night **outside** every window is uncovered → warns → self-announces on broad failure.

- `_boresight_offset_entry(header)` → the row whose `[start, end]` UT-date range contains the
  exposure's observation date (from `_datetime_begin`, MJD-OBS preferred / DATE-OBS fallback),
  else `None`. Fail-closed: `None` if the date can't be determined.
- `boresight_offset_arcsec(header) -> tuple[float, float]` → the matched row's `(ΔE, ΔN)` in
  arcsec, else `(0.0, 0.0)`.
- `boresight_offset_covered(header) -> bool` → `True` iff a row matched.
- `tracking_radec` applies `boresight_offset_arcsec(header)` via
  `coord.spherical_offsets_by(ΔE * u.arcsec, ΔN * u.arcsec)`. A `(0, 0)` shift is a harmless
  no-op, so covered-but-zero campaigns (2010) and uncovered campaigns are both left in place;
  the difference between them is only the `covered` flag, used by Component 2.

Semantics: **covered** = "this campaign has been characterized (offset may be zero)";
**uncovered** = "never checked → warn/diagnose".

### Component 2 — Orchestration: warn + diagnose (`packages/stips/src/stips/core/science.py`)

Both hooks read the active profile's coverage helper (venv-side, via `load_active_profile`);
they map the observing night to a representative UT date to query the table.

- **Preflight** (per night, before processing): if `not covered`, log a prominent WARNING:
  *"Campaign `<date>` has no boresight-offset characterization for this instrument; if
  astrometry fails broadly it likely needs one (blind-solve one exposure, add a table row)."*
- **Post-run**: if the night is **uncovered** AND astrometry failed broadly — the fraction of
  science visits ending in `BadAstrometryFit`/`MatcherFailure` is **≥ 0.50** — surface a
  specific, actionable message in the failure summary naming the likely cause and the fix,
  instead of a generic error. If the night is covered, or the failure fraction is below
  threshold, no special handling (avoids nagging known-good campaigns like 2010).

The 0.50 threshold is a module constant, documented as "most visits failing on an uncovered
campaign is the uncharacterized-offset signature; a few failures are normal per-visit issues."

### Data flow

```
raw header --> tracking_radec (in-stack translator) --> boresight_offset_arcsec(header)
            --> spherical_offsets_by --> corrected seed WCS
science.py (venv) --> profile.boresight_offset_covered(night_date) --> preflight warning
                  --> after run: uncovered AND fail-fraction >= 0.5 --> actionable diagnostic
```

## Testing

- **Profile (stack-free):** an in-window 2006 date → `(257, 320)`, `covered=True`; a 2010
  date → `(0, 0)`, `covered=True`; a date outside every window (e.g. 2008, and a 2006 date
  *outside* the measured Sep 27–Dec 16 window such as 2006-06-01) → `(0, 0)`,
  `covered=False`. Boundary dates (the exact `start`/`end` of a window) are covered.
  `tracking_radec` shifts an in-window 2006 header +257″E/+320″N; leaves 2010 and an
  uncovered date unchanged.
- **Regression:** existing `test_boresight_offset_epoch.py` still passes unchanged (2006
  shifted, 2010 identical) with the value now sourced from the table.
- **Orchestration (stack-free):** preflight warning emitted for an uncovered night, not for a
  covered one; post-run diagnostic fires for `uncovered AND fail-fraction ≥ 0.5`, and does not
  fire when covered or below threshold. Exercised against a small fake `ScienceResult`.

## Validation (real data, cheap — no re-ingest; translator applies at read time)

- Re-run 2006 NGC2298 visit `24650220` → still converges (~0.069″), proving the table refactor
  preserves the fix.
- Confirm the 2010 SA98 seed WCS is byte-identical (the `(0, 0)` row is a true no-op).

## Scope

**In scope:** the offset table + lookup (Component 1), the preflight + post-run diagnostics
(Component 2), their tests, and the real-data validation.
**Files:** `instruments/ctio1m/profile.py` (+ its offset test), `packages/stips/src/stips/core/
science.py` (+ orchestration test).
**Out of scope:** the on-the-fly blind-solve fallback; any change to `maxOffsetPix`/matcher
config (tolerance approach was tested and rejected); other instruments.

## Risks

- The night→UT-date mapping for the coverage query must match the table's date convention
  (UT). Use the same `_datetime_begin`/`day_obs` basis the translator uses; unit-test a
  boundary date.
- The post-run failure-fraction needs a source of per-visit astrometry outcomes; use the
  science run's quanta success/failure counts already tracked in `ScienceResult`, and be
  explicit if that count conflates non-astrometry failures (document the approximation).
