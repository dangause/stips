# The Instrument Contract (free test coverage by convention)

STIPS ships a framework-provided contract-test harness. Every directory under
`instruments/<name>/` that contains a `profile.py` is **auto-discovered** by
`packages/stips/tests/test_instrument_contracts.py` and run through a shared
set of assertions (`stips.testing.instrument_contract`). A new telescope gets
this coverage by dropping in the directory — no test code to copy.

## What a new instrument must provide

1. **`instruments/<name>/profile.py`** exposing a module-level
   `InstrumentProfile` object named `profile`. The profile contract asserts:
   - `name`, `policy_name`, `collection_prefix`, `instrument_class`,
     `filter_key` are set; `filters` and `header_map` are non-empty;
   - the `Site` lat/lon/elevation are physically plausible;
   - `profile.camera` resolves (a `CameraSpec`, or a yaml path that exists
     under the instrument dir);
   - if the instrument ships `fetch.py`, `profile.fetch_data` is wired.

2. **`instruments/<name>/tests/contract_data.py`** — a small fixtures module
   (loaded by path with a unique per-instrument module name, so the identical
   basename across instruments cannot collide) exporting:

   | Name | Required | Meaning |
   |------|----------|---------|
   | `SAMPLE_HEADER` | yes | A realistic raw-science FITS header dict |
   | `SAMPLE_HEADER_SEQ_PLUS_ONE` | yes | Same frame, sequence number + 1 (monotonicity check) |
   | `EXPECTED_SEQ` | yes | The sequence number encoded in `exposure_id`'s low digits |
   | `EXPECTED_TRANSLATION` | yes | Pinned hook outputs for `SAMPLE_HEADER` (see below) |
   | `OBSERVATION_TYPE_CASES` | optional | `[(header, expected_type), ...]` |
   | `UNKNOWN_FILTER` | optional | `{"raw": ..., "raises": True}` or `{"raw": ..., "raises": False, "result": ...}` |
   | `FETCH_NIGHT`, `FETCH_ENV` | if `fetch.py` exists | A valid night string + the env block the hook reads |
   | `EXPECTED_DETECTORS`, `EXPECTED_AMPS` | optional | Camera-assembly pins (stack-only contract) |

   `EXPECTED_TRANSLATION` keys (each optional; asserted when present):
   `observation_type`, `exposure_id`, `visit_id`, `day_obs`, `observation_id`,
   `tracking_radec` (an `(ra_deg, dec_deg)` tuple, 0.01 deg tolerance),
   `datetime_begin_mjd`, `datetime_end_mjd` (1e-6 day tolerance).

3. **Optional assets** — each enables further contracts; missing ones skip
   with a reason instead of failing:
   - `fetch.py` → fetch status contract (`fetch_data` returns
     `ok`/`not_found`/`failed`; mocked backend, network-free);
   - `camera/` + `EXPECTED_*` pins → camera-assembly contract (stack-only);
   - `testdata/` → testdata-layout contract (must contain at least one raw
     FITS; layout mirrors `instruments/nickel/testdata/`).

## What the contracts check

Stack-free (run in the plain `uv sync` venv):

- **profile** — required fields populated, filters non-empty, site sane.
- **exposure-id scheme** — positive, fits in 31 bits, `visit_id ==
  exposure_id`, low digits encode the sequence number, monotonic in seq. The
  reference scheme (`days_since_2000 * 10000 + seq`) is provided by
  `stips.make_exposure_id`; profiles should call it rather than re-implement
  the packing and the 31-bit guard.
- **translation** — the declarative hooks reproduce `EXPECTED_TRANSLATION`.
- **observation types / unknown-filter policy** — per the optional fixtures.
- **fetch** — status-code mapping contract, parameterized by the instrument's
  env schema.
- **asset layout** — camera path resolves; testdata ships raws.

Stack-dependent (skip in a plain venv; run under `scripts/with-stack.sh`, e.g.
via `tox`):

- **camera assembly** — `lsst.obs.stips.active.Instrument().getCamera()`
  yields the pinned detector/amplifier counts.
- **translator synthesis** — the generic `StipsTranslator` bound to the
  profile reproduces the pinned ids/types through the real `to_*` surface.

## What stays in the instrument's own `tests/`

Only genuinely instrument-specific behavior: e.g. Nickel's stuck-DEC
coordinate reconciliation and golden translation-parity gate
(`test_translation_golden.py`), ctio1m's NOIRLab `_funpack`/find-night backend
tests and measured-crosstalk pins, each side's env-key→kwarg forwarding.
Import shared helpers explicitly from `stips.testing.instrument_contract`
(`active_instrument_dir`, `load_fetch`, `FetchConfigStub`, ...) — never from a
`conftest.py` (bare `conftest` imports collide across test dirs).

## Future work (deferred)

- **Synthetic-raw generator**: fabricate a valid raw FITS from the camera
  spec + `SAMPLE_HEADER`, so every instrument gets ingest/formatter contract
  coverage without curating real frames (today only Nickel ships `testdata/`,
  and its ingest tests remain local).
