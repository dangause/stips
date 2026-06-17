# STIPS Multi-Instrument Framework — Design Spec

**Date:** 2026-06-17
**Status:** Approved (design)
**Author:** Dan Gause

## 1. Goal

Let a 1-meter–class telescope team use the LSST Science Pipelines by **forking the
repo and editing one Python profile file** — without ever touching
`lsst.obs.base.Instrument`, `astro_metadata_translator`, raw formatters, or Butler
collection wiring.

The central repo ships **the framework + Nickel as the reference instrument profile**.
Other telescopes (e.g. CTIO 0.9m) become **separate forks**, each containing exactly
one instrument profile — the central repo does not accumulate per-instrument
implementation packages.

"Multi-instrument support" therefore means *the framework can drive any instrument
through a profile*, not *the repo ships many instruments*.

### Non-goals

- No multi-instrument registry / plugin discovery (each fork has exactly one instrument).
- No backward compatibility with the existing Butler repo. The user will regenerate it;
  the refactor must **not** be contorted to preserve stored `class_name`, collection
  prefixes, or instrument names.
- No CTIO (or other second instrument) in the central repo this round.
- No rename of the instrument-specific *data* packages (`obs_nickel_data` and the
  `obs-nickel-*` helpers) — deferred, cosmetic, outside the abstraction seam.

## 2. Background

### Current state (main)

- `obs_nickel` — LSST obs package: `lsst.obs.nickel.Nickel(Instrument)` (83 lines),
  `NickelTranslator(FitsTranslator)` (312 lines), raw formatter, filter defs, camera YAML,
  pipelines, configs. All hand-written and nickel-specific.
- `obs_nickel_data_tools` — the tooling package; CLI entry point `nickel`. Hardcodes
  `"Nickel/"` collection prefixes, `INSTRUMENT = "lsst.obs.nickel.Nickel"`,
  `SKYMAP_NAME = "nickelRings-v1"` in `core/pipeline.py`.
- The project is already branded "STIPS — Small Telescope Image Processing Suite" in
  docs/README, but **no code carries the `stips` name yet**.

### Open PR #9 (`feature/obs-smalltel-phase1`) — reference only

PR #9 attempted multi-instrument support with a two-layer design: a YAML-driven
`obs_smalltel` LSST package + a `small_tel_tools` rename with an `InstrumentPlugin`
registry. It is ~3 months stale, 67 commits behind main, conflicts against both `dev`
and `main`, and its `smalltel`/`stt` naming collides with the chosen `stips` branding.

**Decision: treat PR #9 as a design reference and reimplement cleanly on `main`.** Two
lessons carried forward and two rejected:

- *Carried:* (a) a generic base Instrument/Translator parameterized per-instrument;
  (b) runtime identifiers (collection prefix, skymap, day-obs offset) sourced from the
  instrument definition rather than hardcoded.
- *Rejected:* (a) the YAML-driven config layer — its own code showed the YAML only
  absorbed the trivial ~30% while the genuinely instrument-specific logic stayed as a
  192-line Python subclass; the YAML loader/`__init_subclass__` machinery is net
  complexity for little payoff. (b) The `InstrumentPlugin` registry + entry-point
  discovery — unnecessary when each fork has one instrument.

## 3. Architecture

### 3.1 Three packages (clean layering)

```
stips/                            # distribution: "stips" — framework core + CLI
  src/stips/
    profile.py                    # InstrumentProfile, Site, hook — the PUBLIC API a fork uses
    collections.py                # collection-name derivation (prefix from profile)
    config.py, run.py, science.py, calibs.py, dia.py, ...   # today's core/ modules, de-nickel'd
    cli.py                        # `stips` command (was `nickel`)

obs_stips/                        # distribution: "obs-stips" — LSST glue, instrument-agnostic
  python/lsst/obs/stips/
    instrument.py                 # StipsInstrument(Instrument) — generic, reads a profile
    translator.py                 # StipsTranslator(FitsTranslator) — generic, reads a profile
    formatter.py                  # StipsRawFormatter

obs_nickel/                       # distribution: "obs-nickel" — the Nickel FORK package (slimmed)
  python/lsst/obs/nickel/
    profile.py                    # InstrumentProfile(name="Nickel", ...) + @hook quirks  ← THE fork file
    __init__.py                   # Nickel = bound instrument class; NickelTranslator = bound translator
    camera.yaml                   # standard LSST camera geometry (unchanged)
  pyproject.toml                  # entry point: Nickel = lsst.obs.nickel:NickelTranslator
```

**Layering rule:** `obs_stips` depends on `stips` (for the profile dataclasses) and
`lsst.obs.base`; it must **not** import the CLI. The Nickel fork package depends on
`obs_stips`. The `stips` *core* (profile types, collection naming) is import-light; the
heavy LSST imports stay lazy inside the CLI/core modules as they are today.

Profile dataclasses live in `stips` core so both the LSST glue and the tooling can read
them with correct layering (`from stips import InstrumentProfile, Site, hook`).

### 3.2 The profile — the single instrument surface

`profile.py` in a fork holds **everything** instrument-specific in one place:

**Declarative config (data):**
- `name` — instrument name (e.g. `"Nickel"`); also the default `collection_prefix`.
- `site` — `Site(latitude, longitude, elevation)`.
- `filters` — raw FITS filter name → canonical band, e.g. `{"OPEN": "clear", "G'": "gp"}`.
- `header_map` — metadata field → FITS keyword (+ unit/default), e.g.
  `{"exposure_time": ("EXPTIME", "s"), "object": ("OBJECT", "UNKNOWN")}`.
- `day_obs_offset_hours` — local-night → UT day_obs offset (Nickel: 12).
- `camera` — path to the standard LSST `camera.yaml`.

**Operational config (consumed by the tooling):**
- `collection_prefix` — defaults to `name`.
- `skymap_name` — e.g. `"nickelRings-v1"`.
- `obs_data_package` — curated-calib data package name (e.g. `"obs_nickel_data"`).
- `refcat_path` — optional.
- `fetch_data` — optional archive-download hook (Nickel: Lick archive client).

**Quirk hooks (Python that can't reduce to data):** `@hook` functions in the same file
override generic translator behavior. Nickel needs:
- `tracking_radec` — stuck-DEC CRVAL-vs-RA/DEC cross-validation.
- `observation_type` / `observation_reason` — heuristics over `OBSTYPE` + `OBJECT`.
- `exposure_id` / `visit_id` — `days_since_2000 * 10000 + OBSNUM` scheme.
- `temperature` — `TEMPDET` °C → K.
- `physical_filter` fallback — unknown filter → `clear`.

A hook receives the FITS `header` and, where relevant, a `default` callable for the
framework's normal path, so a hook can wrap rather than replace.

### 3.3 Generic LSST glue (`lsst.obs.stips`)

- `StipsInstrument(Instrument)` — generic. Reads its bound `profile` for `getName`,
  filter definitions (built from `profile.filters`), camera (`yamlCamera.makeCamera` on
  `profile.camera`), single-CCD detector registration, and `translatorClass`. A fork
  binds it: `class Nickel(StipsInstrument): profile = profile`.
- `StipsTranslator(FitsTranslator)` — generic. Builds LSST `_trivial_map` / `_const_map`
  from `profile.header_map`, applies `profile.filters` for `to_physical_filter`, sources
  `to_location` from `profile.site`, and dispatches to `@hook` overrides when present.
  Single-CCD defaults (`detector_num=0`, etc.) live here. A fork binds it:
  `class NickelTranslator(StipsTranslator): profile = profile`.
- `StipsRawFormatter` — generic single-CCD formatter.

### 3.4 Tooling (`stips`)

- Rename `obs_nickel_data_tools` → `stips`; CLI command `nickel` → `stips`.
- Replace hardcoded constants in `core/pipeline.py` with profile-driven values:
  `"Nickel/"` → `f"{profile.collection_prefix}/"`; `INSTRUMENT` → `profile`'s bound
  instrument class path; `SKYMAP_NAME` → `profile.skymap_name`; day-obs conversion uses
  `profile.day_obs_offset_hours`.
- The CLI learns which instrument it drives from existing config (`.env`/YAML) naming the
  obs package (e.g. `INSTRUMENT_PACKAGE=lsst.obs.nickel`); it imports that package's
  `profile`. **No registry, no discovery.**
- All `obsn-*` / `nickel-*` console-script names → `stips-*` equivalents.

## 4. Data flow

1. CLI / `run.py` reads config → imports the configured obs package → obtains its `profile`.
2. `profile.collection_prefix` / `skymap_name` / `day_obs_offset_hours` drive collection
   naming and date conversion. For the Nickel fork these resolve to `Nickel`,
   `nickelRings-v1`, `12` → clean, human-readable `Nickel/...` collections from a fully
   `stips`-named codebase.
3. Butler instantiates `lsst.obs.nickel.Nickel` (a `StipsInstrument` subclass) for
   registration/ISR. `NickelTranslator` (registered via the package entry point) reads
   `profile.header_map` + hooks to translate FITS headers.

## 5. Testing strategy

- **Unit (in `stips` core):** profile construction/validation; `header_map` → trivial/const
  map conversion; hook dispatch (hook present vs absent → default); collection-name
  derivation. Parametrize with the real Nickel profile **and** a synthetic minimal "test"
  profile, so the seam is proven generic, not nickel-shaped.
- **Translation parity (in the obs package):** run the obs-package tests against the
  existing FITS test fixtures and assert the reimplemented `NickelTranslator` produces the
  **same translation outputs** as the current `NickelTranslator` for every `to_*` value
  the fixtures exercise. This guarantees the refactor does not change the science.
- **Instrument registration:** `StipsInstrument`-bound `Nickel` registers the same
  instrument/detector/filter dimension records as today.
- **End-to-end smoke:** fresh bootstrap + one Nickel night (`stips -p 2023ixf calibs
  <night>`) completes and produces `Nickel/...` collections. (Not compared against any
  pre-existing repo.)

## 6. Phasing

Each phase is independently shippable.

1. **Framework + Nickel-as-profile.** Build `obs_stips` generic
   `StipsInstrument`/`StipsTranslator`/`StipsRawFormatter`; reimplement `lsst.obs.nickel`
   as `profile.py` + thin bindings + `camera.yaml`; pass translation-parity and
   registration tests. Tooling not yet renamed (it still imports `lsst.obs.nickel` as
   today). Delete the old hand-written `obs_nickel` Python once parity is green.
2. **Tooling rename + de-hardcode.** `obs_nickel_data_tools` → `stips`; CLI `nickel` →
   `stips`; console scripts `*-` → `stips-*`; replace hardcoded
   prefix/instrument/skymap/day-offset with profile-driven values; CLI selects the
   instrument via config. No alias kept.
3. **Docs / cleanup.** README, CLAUDE.md, and a "Fork STIPS for your telescope" guide that
   walks through the Nickel `profile.py` as the worked example.

### Deferred (not this round)

- `stips new-instrument <name>` scaffold command (stamps a fork package from the Nickel
  template). Good onboarding nicety; build later.
- Renaming `obs_nickel_data` and the `obs-nickel-*` helper packages.
- A second in-repo instrument (CTIO) — belongs in its own fork.

## 7. Open risks

- **Dynamic vs explicit bound classes.** The instrument `class_name` Butler stores and the
  `astro_metadata_translator` entry point both need concrete, importable classes. The fork
  binds them explicitly (3-line subclasses) rather than generating them dynamically, to
  keep import paths stable and tracebacks clear. To be validated under TDD in phase 1.
- **Hook signature surface.** The set of hookable `to_*` points must cover every Nickel
  quirk listed in §3.2 without becoming an open-ended framework. Phase 1 fixes the hook
  list to exactly those points; new hooks are added only when a real instrument needs one.
- **Import-lightness of `stips` core.** Profile dataclasses must not pull heavy LSST
  imports into `obs_stips` at module import time; keep LSST imports lazy/local as today.
