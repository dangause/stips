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
    plotting.py                   # shared publication-style plotting helpers (see §3.5)
    tasks/                        # GENERIC framework PipelineTasks (see §3.5)
      __init__.py                 #   ForcedPhotRaDecTask, ForcedPhotDiffimRaDecTask,
      forcedPhotRaDec.py          #   DiaLightcurvePlotTask, DiaLightcurveCombinedPlotTask,
      diaLightcurvePlot.py        #   DifferentialPhotTask — instrument-agnostic, every fork uses them
      diaLightcurveCombinedPlot.py
      differentialPhot.py

obs_nickel/                       # distribution: "obs-nickel" — the Nickel FORK package (slimmed)
  python/lsst/obs/nickel/
    profile.py                    # InstrumentProfile(name="Nickel", ...) + @hook quirks  ← THE fork file
    __init__.py                   # Nickel = bound instrument class; NickelTranslator = bound translator
    visitInfo.py                  # NickelVisitInfo(MakeRawVisitInfoViaObsInfo) — binds NickelTranslator
    calibCombine.py               # NickelCalibCombineTask/...ByFilterTask — Nickel ISR quirk (see §3.5)
    camera.yaml                   # standard LSST camera geometry (unchanged)
  pipelines/                      # FORK assets: instrument-tuned pipeline YAMLs (see §3.6)
  configs/                        # FORK assets: calibrateImage tunings, colorterms, dia, coadd configs
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
- `name` — instrument name (e.g. `"Nickel"`); also the default `collection_prefix` and
  the value used in Butler data-query predicates (`instrument='Nickel'`).
- `policy_name` — LSST `policyName` for curated-calib lookups; defaults to `name`.
- `site` — `Site(latitude, longitude, elevation)`.
- `filters` — raw FITS filter name → canonical band, e.g. `{"OPEN": "clear", "G'": "gp"}`.
- `header_map` — metadata field → FITS keyword (+ unit/default), e.g.
  `{"exposure_time": ("EXPTIME", "s"), "object": ("OBJECT", "UNKNOWN")}`.
- `night_to_dayobs_offset_days` — calendar offset the **tooling** applies to convert a
  local observing night → UT `day_obs` (Nickel/Lick: `+1`; see §3.4 for why this is
  distinct from any translator-side observing-day boundary).
- `camera` — path to the standard LSST `camera.yaml`.

**Operational config (consumed by the tooling):**
- `collection_prefix` — defaults to `name`.
- `skymap_name` — the skymap dimension value, e.g. `"nickelRings-v1"`.
- `skymap_collection` — the skymap collection, e.g. `"skymaps/nickelRings"` (today's
  `SKYMAPS_CHAIN`); defaults derivable from `skymap_name`.
- `obs_data_package` — curated-calib data package name (e.g. `"obs_nickel_data"`).
- `package_dir` — import path of the fork's obs package, so the tooling can locate that
  package's `pipelines/` and `configs/` (replaces today's hardcoded
  "relative to `obs_nickel/configs/`"; see §3.6).
- `refcat_path` — optional.
- `fetch_data` — optional archive-download hook (Nickel: Lick archive client).

**Quirk hooks (Python that can't reduce to data):** `@hook` functions in the same file
override generic translator behavior. A hook receives the FITS `header` and, where
relevant, a `default` callable for the framework's normal path, so a hook can wrap rather
than replace. Nickel needs:
- `tracking_radec` — stuck-DEC CRVAL-vs-RA/DEC cross-validation.
- `observation_type` / `observation_reason` — heuristics over `OBSTYPE` + `OBJECT`.
- `exposure_id` / `visit_id` — `days_since_2000 * 10000 + OBSNUM` scheme.
- `temperature` — `TEMPDET` °C → K.
- `unknown_filter` — fallback **policy only** for a filter not found in `profile.filters`
  (Nickel: → `clear`, with a warning). The generic translator resolves `to_physical_filter`
  from `profile.filters` first and invokes this hook **only on a lookup miss**, so the
  declarative map and the hook never overlap.

**Hook contract:** the generic translator/instrument define the closed set of hookable
`to_*` points listed above. A fork only fills in the hooks it needs; absent hooks fall to
the generic path. New hook points are added to the framework only when a real instrument
demonstrably needs one — not speculatively.

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
- The CLI learns which instrument it drives from existing config (`.env`/YAML) naming the
  obs package (e.g. `INSTRUMENT_PACKAGE=lsst.obs.nickel`); it imports that package's
  `profile`. **No registry, no discovery.**
- All `obsn-*` / `nickel-*` console-script names → `stips-*` equivalents.

**De-hardcoding is a repo-wide pass, not three constants.** Nickel-specific literals are
spread across ~23 files under `data_tools/src`, in three forms, all of which must become
profile-driven:
1. **Module constants** in `core/pipeline.py`: the `"Nickel/"` prefix in `CollectionNames`,
   `INSTRUMENT = "lsst.obs.nickel.Nickel"`, `SKYMAP_NAME = "nickelRings-v1"`, and
   `SKYMAPS_CHAIN = "skymaps/nickelRings"` (a fourth constant) →
   `profile.collection_prefix`, the bound instrument class path, `profile.skymap_name`,
   `profile.skymap_collection`.
2. **Butler data-query predicates** embedded in query strings, e.g.
   `instrument='Nickel' AND skymap='nickelRings-v1'` in `core/science.py`,
   `core/coadd.py`, and input-collection strings like
   `"...,Nickel/calib/current,refcats,skymaps/nickelRings"` in `core/run.py`.
3. **Literals inside generated Butler-python snippets**, e.g.
   `collections='skymaps/nickelRings'` in `core/coadd.py`, and the independent
   `os.environ.get("SKYMAP_NAME", "nickelRings-v1")` default in
   `pipeline_tools/ingest_ps1_template.py` (a separate source of truth that must be
   unified onto the profile).

The phase-2 de-hardcode pass explicitly covers all three forms. A grep gate
(`grep -rin "nickel\|Nickel/" data_tools/src` returning only comments/docstrings) is the
phase-2 done-condition.

### 3.5 PipelineTask placement (generic vs. fork)

The current `obs_nickel` ships custom PipelineTasks. They split by whether the logic is
instrument-agnostic:

- **Generic → move to `obs_stips` as `lsst.obs.stips.tasks.*`:** `ForcedPhotRaDecTask`,
  `ForcedPhotDiffimRaDecTask`, `DiaLightcurvePlotTask`, `DiaLightcurveCombinedPlotTask`,
  `DifferentialPhotTask`. Every fork wants these; nothing in them is Nickel-specific.
  **`plotting.py` moves with them** → `lsst.obs.stips.plotting`: the three plot/diff tasks
  import it (`differentialPhot.py`, `diaLightcurveCombinedPlot.py`, `diaLightcurvePlot.py`),
  so leaving it in the fork would force `obs_stips` to import a fork — violating §3.1
  layering. Repoint those imports to `lsst.obs.stips.plotting`.
- **Instrument-tuned config defaults stay out of the moved tasks.** Where a generic task
  carries a Nickel-flavored default (e.g. `DifferentialPhotTask`'s `matchRadius=10.0″`,
  justified by Nickel's 5–7″ WCS residuals), the generic `ConfigClass` keeps an
  instrument-neutral default and the Nickel value is set in the fork's config tree (§3.6),
  so the moved task is truly instrument-agnostic.
- **Quirk → stay in the fork (`lsst.obs.nickel`):** `NickelCalibCombineTask` /
  `NickelCalibCombineByFilterTask` (`calibCombine.py`) — exists only because the Nickel
  ISR pipeline does not preserve VisitInfo dates; and `NickelVisitInfo` (`visitInfo.py`),
  which binds the Nickel translator.

Consequently, pipeline-YAML `class:` paths for the generic tasks change from
`lsst.obs.nickel.tasks.*` → `lsst.obs.stips.tasks.*`; the calibCombine override keeps a
fork-local path. **Phase 1 must update these YAML task paths and must NOT delete
`calibCombine.py` / `visitInfo.py` when retiring the old hand-written package** (correcting
the naive "delete old obs_nickel Python" step).

### 3.6 Pipelines and configs are fork assets

`obs_nickel/pipelines/*.yaml` (DRP/DIA/ForcedPhotRaDec/DifferentialPhot, with Nickel-tuned
relaxed thresholds) and `obs_nickel/configs/` (calibrateImage tunings, colorterms, dia,
coadd) are deeply instrument-tuned and **stay in the fork package**. The framework
contributes the *tasks* (§3.5), not the tuned pipeline/config trees. The tooling locates a
fork's pipelines/configs via `profile.package_dir` instead of the current hardcoded
"relative to `obs_nickel/configs/`", so each fork supplies its own tuned set. (Optionally,
`obs_stips` may ship minimal *reference* pipeline skeletons referencing
`lsst.obs.stips.tasks.*`; not required for phase 1.)

## 4. Data flow

1. CLI / `run.py` reads config → imports the configured obs package → obtains its `profile`.
2. `profile.collection_prefix` / `skymap_name` / `skymap_collection` drive collection
   naming and the Butler data-query predicates; `profile.night_to_dayobs_offset_days`
   drives the tooling's local-night → UT `day_obs` conversion. For the Nickel fork these
   resolve to `Nickel`, `nickelRings-v1`, `skymaps/nickelRings`, `+1` → clean,
   human-readable `Nickel/...` collections from a fully `stips`-named codebase.
3. Butler instantiates `lsst.obs.nickel.Nickel` (a `StipsInstrument` subclass) for
   registration/ISR. `NickelTranslator` (registered via the package entry point) reads
   `profile.header_map` + hooks to translate FITS headers.

**Two distinct "day" semantics — do not conflate them.** (a) The *tooling* converts a
human-entered local observing night to a UT `day_obs` for Butler queries; today this is a
hardcoded `+1 calendar day` in `pipeline.py:night_to_day_obs()`, generalized to
`profile.night_to_dayobs_offset_days`. (b) The *translator's* `to_day_obs()` derives the
day_obs straight from `to_datetime_end()` and needs no offset parameter (the current
`_observing_day_offset = 12h` in the translator is effectively unused by `to_day_obs`).
The profile therefore carries only the tooling-side calendar offset; the translator stays
parameter-free here.

## 5. Testing strategy

- **Unit (in `stips` core):** profile construction/validation; `header_map` → trivial/const
  map conversion; hook dispatch (hook present vs absent → default); collection-name
  derivation. Parametrize with the real Nickel profile **and** a synthetic minimal "test"
  profile, so the seam is proven generic, not nickel-shaped.
- **Translation parity (in the obs package):** capture **golden values** from the current
  `NickelTranslator` for every `to_*` output the FITS fixtures exercise *before* deleting
  it, then assert the reimplemented `StipsTranslator`-bound `NickelTranslator` reproduces
  them. The two translators cannot run side-by-side via normal discovery — they share the
  same `astro_metadata_translator.translators` entry-point name `Nickel` and overlapping
  `can_translate` — so the baseline is a recorded fixture, not a live second translator.
- **Instrument registration:** `StipsInstrument`-bound `Nickel` registers the same
  instrument/detector/filter dimension records as today.
- **End-to-end smoke:** fresh bootstrap + one Nickel night (`stips -p 2023ixf calibs
  <night>`) completes and produces `Nickel/...` collections. (Not compared against any
  pre-existing repo.)

## 6. Phasing

Each phase is independently shippable.

1. **Framework + Nickel-as-profile.** Build `obs_stips` generic
   `StipsInstrument`/`StipsTranslator`/`StipsRawFormatter` **and the generic
   `lsst.obs.stips.tasks.*` plus `lsst.obs.stips.plotting`** (§3.5). Reimplement
   `lsst.obs.nickel` as `profile.py` + thin
   bindings + `camera.yaml`, **keeping the fork-local `visitInfo.py` and `calibCombine.py`
   quirk modules**. Repoint generic-task `class:` paths in the fork's pipeline YAMLs to
   `lsst.obs.stips.tasks.*`. Pass translation-parity (golden values) and registration
   tests. Retire only the old hand-written instrument/translator/formatter/filters Python
   once parity is green — **not** `tasks/` (moved), `calibCombine.py`, or `visitInfo.py`.
   Tooling not yet renamed (it still imports `lsst.obs.nickel` as today).
2. **Tooling rename + de-hardcode.** `obs_nickel_data_tools` → `stips`; CLI `nickel` →
   `stips`; console scripts `*-` → `stips-*`; profile-drive all Nickel literals across the
   three forms in §3.4 (constants, query predicates, generated-snippet literals); resolve
   pipelines/configs via `profile.package_dir`; CLI selects the instrument via config. No
   alias kept. Done-condition: the §3.4 grep gate is clean.
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
- **Pipelines/configs path resolution.** Generalizing the tooling's hardcoded
  "relative to `obs_nickel/configs/`" to `profile.package_dir` touches every place the
  tooling reads a pipeline or config path. If one path stays hardcoded, a non-Nickel fork
  silently loads Nickel configs. The phase-2 grep gate must include `pipelines`/`configs`
  path literals, not only collection/instrument names.
