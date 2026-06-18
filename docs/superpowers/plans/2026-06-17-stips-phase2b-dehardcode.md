# STIPS Phase 2b — De-hardcode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `stips` tooling instrument-agnostic by threading the active instrument `profile` through it and replacing every hardcoded Nickel literal (`"Nickel/"` collection prefixes, `instrument='Nickel'` queries, `INSTRUMENT`/`SKYMAP_NAME`/`SKYMAPS_CHAIN` constants, the `night_to_day_obs` `+1`, `define-visits "Nickel"`, the `obs_nickel`-relative config/pipeline paths) with profile-driven values — while keeping the Nickel fork's runtime output byte-for-byte identical.

**Architecture:** The CLI (running in the `.venv`, not the stack) loads the configured instrument's profile via `from <INSTRUMENT_PACKAGE>.profile import profile` (validated: this imports stack-free when `obs_nickel`+`obs_stips`+`stips` are editable-installed in the venv) and attaches it to the `Config` object as `config.profile`. Every collection name, Butler query, skymap reference, instrument-registration call, and day_obs conversion then reads from `config.profile` (`name`, `collection_prefix`, `skymap_name`, `skymap_collection`, `night_to_dayobs_offset_days`, `instrument_class`, `eups_package`). A new `stips/collections.py` holds the prefix-parameterized `CollectionNames`. For the Nickel profile every value resolves to today's literal, so behavior is unchanged; a synthetic profile proves the seam is real.

**Tech Stack:** Python 3.12, uv workspace, pytest (unittest + pytest), ruff+black, Click CLI, `stips` core (`InstrumentProfile`), LSST butler/pipetask (invoked via `run_with_stack` subprocesses).

**Scope note:** Phase 2b of the spec (`docs/superpowers/specs/2026-06-17-stips-multi-instrument-framework-design.md`, §3.4/§3.6/§6-phase-2). Phase 2a (rename/restructure) is DONE. Phase 3 = docs. This plan does NOT touch the LSST obs packages' internals (Phase 1) beyond adding one profile field; it de-hardcodes the `stips` tooling only.

**Branch/worktree:** Work in `/Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1` on branch `feature/stips-framework`. `cd` there for every command.

**Validated prerequisite:** With `uv pip install --python .venv -e packages/obs_stips -e packages/obs_nickel -e packages/stips`, `from lsst.obs.nickel.profile import profile` works in the venv stack-free and yields `name="Nickel"`, `collection_prefix="Nickel"`, `skymap_name="nickelRings-v1"`, `skymap_collection="skymaps/nickelRings"`, `night_to_dayobs_offset_days=1`. The plan relies on this.

**Core invariant (the safety net):** For the Nickel profile, EVERY generated collection name, query predicate, skymap value, instrument arg, and day_obs must be byte-for-byte identical before and after this phase. Task 1 captures these as golden literals; the final task re-asserts them. A synthetic non-Nickel profile proves genericity (different prefix/name/skymap flow through correctly).

---

## Reference — the de-hardcode surface (recon; file:line are pre-2b, verify before editing)

Profile fields available (`stips.InstrumentProfile`): `name`, `collection_prefix` (default=name), `skymap_name`, `skymap_collection`, `night_to_dayobs_offset_days`, `eups_package`, `package_dir`, `policy_name`. **Missing — added in Task 3:** `instrument_class` (e.g. `"lsst.obs.nickel.Nickel"`).

- `core/pipeline.py`: `CollectionNames(night, run_ts)` with 15 `"Nickel/"` properties (`raw_run`, `cp_bias`, `cp_flat`, `curated_run/chain`, `calib_out`, `calib_chain`, `science_parent/run`, `coadd_parent/run`, `diff_parent/run`); constants `REFCATS_CHAIN="refcats"` (generic — keep), `SKYMAPS_CHAIN="skymaps/nickelRings"`, `SKYMAP_NAME="nickelRings-v1"`, `INSTRUMENT="lsst.obs.nickel.Nickel"`; `night_to_day_obs(night)` hardcodes `+1 day`; `find_bad_coord_exposures()` query `instrument='Nickel' AND ...` (~line 181).
- `core/calibs.py`: `CollectionNames(...)` ×2; `INSTRUMENT` register-instrument (lines 73,185); `define-visits ... "Nickel"` (92,208); `write-curated-calibrations "Nickel"` (216); `instrument='Nickel'` (259,352).
- `core/science.py`: `CollectionNames(...)`; `INSTRUMENT` (418); `instrument='Nickel'` (149,393,816); `instrument='Nickel' AND skymap='{SKYMAP_NAME}'` (816); config/pipeline paths via `config.obs_nickel` (79-84).
- `core/dia.py`: `CollectionNames(...)`; `INSTRUMENT` (239); `instrument='Nickel'` (223,413,431); `"Nickel/..."`/`prefix_filter="Nickel/"` (172,177,253,258); `SKYMAPS_CHAIN` (263); pipeline path `config.obs_nickel/"pipelines/DIA.yaml"` (228).
- `core/coadd.py`: `INSTRUMENT` (430); `instrument='Nickel' AND skymap='{SKYMAP_NAME}'` (~455/459); `"Nickel/..."`/`prefix_filter` (154,163); `skymaps/nickelRings` in generated butler-python (77); `SKYMAPS_CHAIN`/`SKYMAP_NAME` imported ~23-24 (verify usage lines).
- `core/fphot.py`: `instrument='Nickel'` (45,172); `"Nickel/..."`/`prefix_filter` (79,88,145,150,185,255); calib chains w/ `Nickel/calib/current`+`REFCATS_CHAIN`+`SKYMAPS_CHAIN` (189,252).
- `core/run.py`: many `"Nickel/..."` + `prefix_filter="Nickel/"` (1618,1623,1643,1644,1733,1742,1751,1784,1793,1799); hardcoded `skymaps/nickelRings` + `Nickel/calib/current` chain (1644).
- `core/clean.py`: `RUN_PATTERNS`/`CALIB_PATTERNS`/`PRESERVED_PATTERNS` lists + `step_to_patterns` dict, all `"Nickel/..."` (27-46,127-131); `"Nickel/calib/current"` (46).
- `core/landolt.py`: default `collection="Nickel/runs/*/processCcd/*"` (32).
- `cli.py`: docstring examples + defaults `"Nickel/runs/*/processCcd/*"` (1186-1197,1264,1315,1364).
- `pipeline_tools/`: `assess_dia_quality.py` `instrument='Nickel'` (97,118); `extract_lightcurve.py` (396,446); `validate_landolt.py` (217,285,490); `extract_calib_metrics.py` (156,230,271); `ingest_ps1_template.py` `os.environ.get("SKYMAP_NAME","nickelRings-v1")` (1130) + `os.environ.get("SKYMAPS_CHAIN","skymaps")` (1131; note the SKYMAPS_CHAIN default is `"skymaps"`, not the nickelRings form).
- `dashboard/catalog_query.py`: `instrument='Nickel'` (233). **`dashboard/image_renderer.py`: ESCAPED `where="instrument=\'Nickel\' AND day_obs=..."` (142,151)** — easy to miss; neither file has a `config`/`profile` in scope (Task 9 Step 2 threads the name).
- `core/config.py`: `obs_nickel: Path` + derives `pipelines_dir`/`configs_dir` (74,87-88). `cli.py` discovers `OBS_NICKEL` env (227-244).

---

## File Structure (end state)

```
packages/stips/src/stips/
  collections.py        # NEW: prefix-parameterized CollectionNames (moved from core/pipeline.py)
  core/config.py        # Config gains `profile`; OBS_NICKEL path generalized to the instrument package dir
  core/pipeline.py      # constants/night_to_day_obs/queries become profile-driven helpers; re-exports CollectionNames
  core/*.py             # all collection/query/instrument literals → config.profile-driven
  pipeline_tools/*.py   # query predicates + ps1 skymap default → profile-driven
  dashboard/{catalog_query,image_renderer}.py  # threaded instrument_name (no config in scope)
packages/stips/tests/
  test_collections.py       # NEW: prefix parity (Nickel) + genericity (synthetic)
  test_config_profile.py    # NEW: Config loads the configured profile
  test_dehardcode_parity.py # NEW: golden — Nickel collection/query strings unchanged; synthetic profile differs
packages/obs_nickel/python/lsst/obs/nickel/profile.py   # add instrument_class="lsst.obs.nickel.Nickel"
packages/stips/src/stips/profile.py                     # add instrument_class field
README.md / Makefile  # dev-setup: editable-install obs packages alongside stips
```

---

## Task 1: Capture the Nickel parity golden (BEFORE any de-hardcode)

Pin today's generated collection names + query predicates so the de-hardcode is provably behavior-preserving for Nickel.

**Files:** Create `packages/stips/tests/test_dehardcode_parity.py`

- [ ] **Step 1: Write golden assertions against the CURRENT code** (stack-free — these are pure string builders). Import the current `CollectionNames` and pin its properties for a fixed `(night="20230519", run_ts="ts1")`, plus the current `night_to_day_obs("20230519")`:
```python
# packages/stips/tests/test_dehardcode_parity.py
"""Golden: Nickel-generated collection names / day_obs BEFORE the Phase 2b de-hardcode.
After de-hardcode, the Nickel profile must reproduce these EXACT strings."""
import unittest
from stips.core.pipeline import CollectionNames, night_to_day_obs

class TestNickelCollectionGolden(unittest.TestCase):
    def setUp(self):
        self.c = CollectionNames("20230519", "ts1")  # current signature

    def test_collection_strings(self):
        self.assertEqual(self.c.raw_run, "Nickel/raw/20230519/ts1")
        self.assertEqual(self.c.calib_chain, "Nickel/calib/current")
        self.assertEqual(self.c.science_parent, "Nickel/runs/20230519/processCcd/ts1")
        self.assertEqual(self.c.diff_parent, "Nickel/runs/20230519/diff/ts1")
        self.assertEqual(self.c.coadd_parent, "Nickel/runs/20230519/coadd/ts1")
        # ...pin ALL 15 properties with their exact current values...

    def test_day_obs(self):
        self.assertEqual(night_to_day_obs("20230519"), "20230520")  # +1 day
```
RUN it to capture the EXACT current values (read each property; do not guess). Fill in every property literal.

- [ ] **Step 2: Run — confirm PASS against current code.** `cd <worktree>; uv pip install --python .venv -e packages/stips -e packages/obs_stips -e packages/obs_nickel; .venv/bin/python -m pytest packages/stips/tests/test_dehardcode_parity.py -v`. All literals green.

- [ ] **Step 3: Commit.** `git add packages/stips/tests/test_dehardcode_parity.py && git commit -m "test(stips): pin Nickel collection/day_obs golden before de-hardcode"`

(Note: this test imports from the CURRENT `stips.core.pipeline`. Task 2 moves `CollectionNames` to `stips.collections` and re-exports it from `core.pipeline`, so this import keeps working; the parity test is EXTENDED in the final task to also drive it via a profile.)

---

## Task 2: `stips/collections.py` — prefix-parameterized CollectionNames

**Files:** Create `packages/stips/src/stips/collections.py`, `packages/stips/tests/test_collections.py`; modify `packages/stips/src/stips/core/pipeline.py` (move the class out, re-export).

- [ ] **Step 1: Write failing tests** (parity + genericity):
```python
# packages/stips/tests/test_collections.py
import unittest
from stips.collections import CollectionNames

class TestCollectionNames(unittest.TestCase):
    def test_nickel_prefix_parity(self):
        c = CollectionNames("20230519", "ts1", prefix="Nickel")
        self.assertEqual(c.raw_run, "Nickel/raw/20230519/ts1")
        self.assertEqual(c.calib_chain, "Nickel/calib/current")
        self.assertEqual(c.science_parent, "Nickel/runs/20230519/processCcd/ts1")

    def test_other_prefix(self):
        c = CollectionNames("20240101", "tsX", prefix="ctio0m9")
        self.assertEqual(c.raw_run, "ctio0m9/raw/20240101/tsX")
        self.assertEqual(c.calib_chain, "ctio0m9/calib/current")

    def test_prefix_defaults_to_nickel_for_backcompat(self):
        # back-compat: old 2-arg callers still work (default prefix)
        self.assertEqual(CollectionNames("20230519", "ts1").calib_chain, "Nickel/calib/current")
```
(Decide the default: to keep the Task 1 golden + existing 2-arg call sites compiling mid-refactor, give `prefix` a default of `"Nickel"`. Task 5-7 then thread the real `config.profile.collection_prefix` into every call site, and the default is removed in the final task once no caller relies on it. Document this as a temporary scaffold.)

- [ ] **Step 2: Run → FAIL** (`No module named stips.collections`).

- [ ] **Step 3: Implement `stips/collections.py`** by moving the `CollectionNames` class from `core/pipeline.py` verbatim, adding a `prefix: str = "Nickel"` constructor param and replacing the literal `"Nickel"` in every property f-string with `{self.prefix}`:
```python
"""Butler collection-name builder, parameterized by instrument collection prefix."""
class CollectionNames:
    def __init__(self, night: str, run_ts: str | None = None, prefix: str = "Nickel"):
        from stips.core.pipeline import generate_run_timestamp  # keep existing ts helper
        self.night = night
        self.run_ts = run_ts or generate_run_timestamp()
        self.prefix = prefix

    @property
    def raw_run(self) -> str:
        return f"{self.prefix}/raw/{self.night}/{self.run_ts}"
    # ...all 15 properties, "Nickel/" -> f"{self.prefix}/"...
```
(If importing `generate_run_timestamp` from `core.pipeline` risks a cycle, move that helper into `collections.py` too, or into a small shared module — pick the lower-coupling option.)

- [ ] **Step 4: Re-export from `core/pipeline.py`** so existing `from stips.core.pipeline import CollectionNames` imports keep working: delete the class body there, add `from stips.collections import CollectionNames`. Keep the constants (`SKYMAP_NAME` etc.) for now (Task 4 handles them).

- [ ] **Step 5: Run both test files + the Task 1 golden → PASS.** `.venv/bin/python -m pytest packages/stips/tests/test_collections.py packages/stips/tests/test_dehardcode_parity.py -v`.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat(stips): add prefix-parameterized CollectionNames in stips.collections"`

---

## Task 3: Add `instrument_class` to the profile; load `profile` into `Config`

**Files:** `packages/stips/src/stips/profile.py` (field), `packages/obs_nickel/python/lsst/obs/nickel/profile.py` (set it), `packages/stips/src/stips/core/config.py` (+`profile`), `cli.py` (env), tests; dev-setup (README/Makefile).

- [ ] **Step 1: Add `instrument_class` to `InstrumentProfile`** (`stips/profile.py`): `instrument_class: Optional[str] = None` with a comment `# FQ instrument class path for butler register-instrument, e.g. "lsst.obs.nickel.Nickel"`. In `__post_init__`, no default derivation (leave None unless set). Update the Nickel profile (`lsst/obs/nickel/profile.py`) to set `instrument_class="lsst.obs.nickel.Nickel"`. (Confirm against the current `INSTRUMENT` constant value.)

- [ ] **Step 2: Write a failing test** `packages/stips/tests/test_config_profile.py`:
```python
import unittest
from stips.core.config import load_profile   # new helper

class TestProfileLoad(unittest.TestCase):
    def test_loads_nickel_profile(self):
        p = load_profile("lsst.obs.nickel")
        self.assertEqual(p.name, "Nickel")
        self.assertEqual(p.collection_prefix, "Nickel")
        self.assertEqual(p.instrument_class, "lsst.obs.nickel.Nickel")
        self.assertEqual(p.skymap_name, "nickelRings-v1")
```

- [ ] **Step 3: Implement `load_profile` + thread into `Config`.** In `core/config.py`:
```python
def load_profile(instrument_package: str):
    """Import the active instrument's profile (stack-free import path)."""
    import importlib
    mod = importlib.import_module(f"{instrument_package}.profile")
    return mod.profile
```
Add a `profile` field to the `Config` dataclass. Where `Config` is built (config loading from .env in `config.py`/`cli.py`), read `INSTRUMENT_PACKAGE` from env (default `"lsst.obs.nickel"`), call `load_profile(...)`, and set `config.profile`. Keep `config.obs_nickel` working (Task 8 generalizes the path). **Do NOT make config import fail when the obs package isn't installed** — if `load_profile` raises ImportError, surface a clear message ("instrument package <X> not importable; pip install it") but only when a command actually needs the profile.

- [ ] **Step 4: Run test → PASS** (the venv has the obs packages editable-installed per the prerequisite).

- [ ] **Step 5: Dev setup.** Update the README "Development Setup" and/or `Makefile` so the editable install includes the obs packages: `uv pip install -e packages/stips -e packages/obs_stips -e packages/obs_nickel`. Add a one-line note that a fork installs its own `obs_<instrument>` here and sets `INSTRUMENT_PACKAGE`.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat(stips): load instrument profile into Config (INSTRUMENT_PACKAGE); add profile.instrument_class"`

---

## Task 4: De-hardcode `core/pipeline.py` (constants, night offset, query)

**Files:** `packages/stips/src/stips/core/pipeline.py`

- [ ] **Step 1: Keep the constants as a transitional shim (do NOT delete them yet).** `INSTRUMENT`, `SKYMAP_NAME`, `SKYMAPS_CHAIN` are imported by FIVE modules (calibs, science, dia, coadd, fphot) and the test suite imports those modules transitively — deleting the constants now would break imports and redden the suite at this commit. **Definitive staging:** LEAVE the three constants in place (and `REFCATS_CHAIN="refcats"`, which is generic and stays permanently). Tasks 5-9 migrate each USAGE to `config.profile.{instrument_class,skymap_name,skymap_collection}`. The now-unused constants are deleted in Task 10 Step 2, once a grep confirms no module imports them. Do NOT introduce a `_NICKEL = load_profile(...)` shim — the existing constants already serve as the transitional values; just don't remove them until the end. (Optionally add a `# DEPRECATED: migrating to config.profile in Phase 2b; removed in Task 10` comment above them.)
- [ ] **Step 2: `night_to_day_obs(night, offset_days=1)`** — add an `offset_days` param (default 1 preserves behavior), replace the hardcoded `timedelta(days=1)` with `timedelta(days=offset_days)`. Update internal callers in pipeline.py to pass `config.profile.night_to_dayobs_offset_days`. Test: `night_to_day_obs("20230519")` still `"20230520"`; `night_to_day_obs("20230519", offset_days=0)` == `"20230519"`.
- [ ] **Step 3: `find_bad_coord_exposures` query** — replace `instrument='Nickel'` with `f"instrument='{profile.name}'"` (the function already receives target/coords; add `profile` or `instrument_name` param). Update its caller (`science.py`).
- [ ] **Step 4: Run the parity + collections + config tests → green.** Commit: `git commit -am "refactor(stips): profile-drive pipeline.py constants/night_offset/query"`

---

## Task 5: De-hardcode `core/calibs.py` + `core/science.py`

**Files:** `core/calibs.py`, `core/science.py`. Pattern (apply throughout): thread `config.profile`; the real call sites are 1-arg `CollectionNames(night)` (run_ts defaults internally) → `CollectionNames(night, prefix=config.profile.collection_prefix)` (pass `prefix` as a keyword so any run_ts default is preserved); `INSTRUMENT` → `config.profile.instrument_class`; `"Nickel"` in `define-visits`/`write-curated-calibrations` → `config.profile.name`; `instrument='Nickel'` → `f"instrument='{config.profile.name}'"`; `skymap='{SKYMAP_NAME}'` → `f"skymap='{config.profile.skymap_name}'"`.

- [ ] **Step 1:** Edit `calibs.py` — both `CollectionNames` calls, register-instrument (73,185), define-visits (92,208), write-curated-calibrations (216), the two `instrument='...'` queries (259,352).
- [ ] **Step 2:** Edit `science.py` — `CollectionNames`, register-instrument (418), the three `instrument='Nickel'` (149,393,816) incl. `skymap='{SKYMAP_NAME}'` (816), and the `find_bad_coord_exposures` call (pass profile).
- [ ] **Step 3:** Run the existing calibs/science tests (test_run_config, test_fphot_collection_selection, etc.) + parity tests under the stack-free venv where possible; full check under the stack. Grep these two files: `grep -n "Nickel\|SKYMAP_NAME\|INSTRUMENT" core/calibs.py core/science.py` → only profile-driven refs / comments remain.
- [ ] **Step 4:** Commit `refactor(stips): profile-drive calibs.py + science.py collections/queries/instrument`.

---

## Task 6: De-hardcode `core/dia.py` + `core/coadd.py` + `core/fphot.py`

**Files:** `core/dia.py`, `core/coadd.py`, `core/fphot.py`. Same patterns as Task 5, plus the `prefix_filter="Nickel/"` → `f"{config.profile.collection_prefix}/"` and the inline `Nickel/calib/current`/`skymaps/nickelRings` chain strings (fphot 189,252; coadd 77; run uses these too in Task 7). For coadd's generated butler-python snippet (line 77 `collections='skymaps/nickelRings'`) substitute `config.profile.skymap_collection`.

- [ ] **Step 1:** `dia.py` — CollectionNames, INSTRUMENT (239), instrument= (223,413,431), the 4 `"Nickel/..."`/`prefix_filter` sites (172,177,253,258), SKYMAPS_CHAIN (263).
- [ ] **Step 2:** `coadd.py` — INSTRUMENT (430), `instrument='...' AND skymap='...'` (459), the `"Nickel/..."`/`prefix_filter` (154,163), the generated-snippet `skymaps/nickelRings` (77), SKYMAPS_CHAIN/SKYMAP_NAME (23,59).
- [ ] **Step 3:** `fphot.py` — instrument= (45,172), the 6 `"Nickel/..."`/`prefix_filter` (79,88,145,150,185,255), the two calib-chain strings (189,252) → `f"...,{prefix}/calib/current,{REFCATS_CHAIN},{config.profile.skymap_collection}"`.
- [ ] **Step 4:** Run full suite under the stack; grep the three files for residual `Nickel`/`nickelRings` (only profile-driven/comments allowed). Commit.

---

## Task 7: De-hardcode `core/run.py` + `core/clean.py` + `core/landolt.py` + `cli.py` defaults

**Files:** `core/run.py`, `core/clean.py`, `core/landolt.py`, `cli.py`.

- [ ] **Step 1:** `run.py` — the ~10 `"Nickel/..."`/`prefix_filter` sites (1618,1623,1643,1644,1733,1742,1751,1784,1793,1799) → `config.profile.collection_prefix`; the inline `f"{science_coll},Nickel/calib/current,refcats,skymaps/nickelRings"` (1644) → profile prefix + `config.profile.skymap_collection`.
- [ ] **Step 2:** `clean.py` — the `RUN_PATTERNS`/`CALIB_PATTERNS`/`PRESERVED_PATTERNS` lists and `step_to_patterns` dict (27-46,127-131): these are module-level constants (referenced ONLY within clean.py — `cli.py:865` imports the module and calls its functions, so converting them is safe, no external breakage). Convert them to functions that take a `prefix` (e.g. `def run_patterns(prefix): return [f"{prefix}/runs/*/processCcd/*", ...]`) and thread `config.profile.collection_prefix` from the `clean` command. **Also thread `prefix` into `_is_preserved()` (lines ~59-69)** — it uses `PRESERVED_PATTERNS` and currently has no prefix/config param; give it a `prefix` argument so its preserved-pattern check is profile-driven too. Keep behavior identical for `prefix="Nickel"`.
- [ ] **Step 3:** `landolt.py` — default `collection="Nickel/runs/*/processCcd/*"` (32): make the default `None` and resolve from `config.profile.collection_prefix` at the call site, OR require the caller to pass it. Don't bake "Nickel" into the default.
- [ ] **Step 4:** `cli.py` — the docstring examples (1186-1197,1315) keep generic prose but replace `Nickel/...` example collection strings with neutral placeholders or `<prefix>/...`; the option `default=...` values (1264,1364) that hardcode `"Nickel/runs/*/processCcd/*"` → default `None` resolved from `config.profile.collection_prefix` when the command runs.
- [ ] **Step 5:** Run full suite; grep these files. Commit.

---

## Task 8: Generalize config/pipeline path resolution

**Files:** `core/config.py`, `cli.py`, and the per-module pipeline/config path joins (`calibs.py:249`, `dia.py:228-231`, `science.py:79-84`, etc.).

- [ ] **Step 1:** In `Config`, keep the instrument package directory but name it generically (e.g. add `config.instrument_dir` resolved from the configured instrument package — derive from `config.profile.eups_package` via the same env the CLI already reads as `OBS_NICKEL`, or from the installed package location). Keep `config.obs_nickel` as a back-compat alias pointing at the same path so existing joins keep working, then migrate the joins to `config.instrument_dir`.
- [ ] **Step 2:** Migrate the pipeline/config path joins from `config.obs_nickel / "pipelines/..."` / `"configs/..."` to `config.instrument_dir / ...`. Pipelines/configs stay fork assets (spec §3.6), so a CTIO fork would set its own instrument dir. Do NOT change which YAML/config files are referenced for Nickel (same relative paths).
- [ ] **Step 3:** Run; confirm Nickel still resolves the same pipeline/config paths. Commit.

---

## Task 9: De-hardcode `pipeline_tools/` + `dashboard/`

**Files:** `pipeline_tools/{assess_dia_quality,extract_lightcurve,validate_landolt,extract_calib_metrics,ingest_ps1_template}.py`, `dashboard/catalog_query.py`, **`dashboard/image_renderer.py`** (it has the easily-missed ESCAPED predicate `where="instrument=\'Nickel\' AND day_obs=..."` at lines 142,151).

- [ ] **Step 1 (pipeline_tools standalones):** these are argparse `main()` scripts with NO `config` object. Add an explicit `--instrument NAME` CLI option (default resolved by loading the profile via the `INSTRUMENT_PACKAGE` env, e.g. `default=load_profile(os.environ.get("INSTRUMENT_PACKAGE","lsst.obs.nickel")).name`), and replace each `instrument='Nickel'` with `f"instrument='{args.instrument}'"`. For `ingest_ps1_template.py:1130-1131`, unify the `os.environ.get("SKYMAP_NAME", "nickelRings-v1")` / `os.environ.get("SKYMAPS_CHAIN","skymaps")` defaults with the profile (load the profile and use `profile.skymap_name`/`profile.skymap_collection`, falling back to env only if no profile).
- [ ] **Step 2 (dashboard):** `dashboard/catalog_query.py` and `dashboard/image_renderer.py` have NO `config`/`profile` in scope — their query-builder functions take primitive args (repo_path, night, band). Thread the instrument name as an explicit parameter: add an `instrument_name: str` argument to the relevant `_build_*`/render functions and pass it down from where the dashboard is created. The dashboard is launched by `stips dashboard` (cli.py), which HAS `config.profile` — pass `config.profile.name` into `create_app(...)`, store it on the app/collector, and forward it to the query builders. Replace `instrument='Nickel'` (catalog_query.py:233) and the two escaped `instrument=\'Nickel\'` predicates (image_renderer.py:142,151) with the threaded `instrument_name`. **Both the plain and escaped forms must be handled** — grep `grep -rn "instrument=.*Nickel" packages/stips/src/stips/dashboard` and fix every hit.
- [ ] **Step 3:** Run the pipeline_tools + dashboard-importable tests under the stack (and stack-free where possible); `grep -rn "Nickel" packages/stips/src/stips/dashboard packages/stips/src/stips/pipeline_tools` → only docstrings/help-defaults remain. Commit.

---

## Task 10: Final verification — Nickel parity + genericity + grep gate

**Files:** `packages/stips/tests/test_dehardcode_parity.py` (extend), and a cleanup sweep.

- [ ] **Step 1: Extend the parity golden to drive via the profile.** Add assertions that `CollectionNames(night, ts, prefix=load_profile("lsst.obs.nickel").collection_prefix)` reproduces the EXACT golden strings from Task 1 (proves the threaded profile yields identical Nickel output), AND that a synthetic profile (`name="demo", collection_prefix="demo", skymap_name="demoRings", ...`) produces `demo/...` collections + `instrument='demo'` predicates (proves genericity). For the query-builders that became functions, assert both Nickel-parity and demo-genericity on a representative sample.

- [ ] **Step 2: Remove the transitional scaffolds** — the `prefix="Nickel"` default on `CollectionNames` and any `_NICKEL = load_profile(...)` crutch in pipeline.py — now that all call sites pass the profile. Re-run tests to confirm nothing relied on them. (If a call site still needs the default, that's a missed de-hardcode — fix it.)

- [ ] **Step 3: Grep gate (two-part — broadened to catch escaped predicates; tolerant of docstring examples).** The naive `'Nickel'` gate both MISSES escaped query forms (`instrument=\'Nickel\'` in generated render scripts) and FALSE-POSITIVES on legitimate docstring/usage-example lines (e.g. `core/__init__.py`, `core/calib_metrics.py`, `eda/butler_inspect.py`, `skymap/make_skymap_from_datasets.py`, `skymap/build_discrete_skymap_config.py`). So run two greps:

  **(a) LOGIC gate — must return NOTHING.** Use SIMPLE, permissive patterns that catch every escape form (the on-disk predicate is `instrument=\\'Nickel\\'` with doubled backslashes inside a generated subprocess script — a narrow `'Nickel'` regex misses it; `instrument=.*Nickel` does not). Run BOTH greps; each must be empty after excluding docstring/comment lines:
  ```bash
  # (a1) query predicates — ANY quoting/escaping form:
  grep -rnE "instrument=.*Nickel" packages/stips/src/stips --include=*.py | grep -vE '#|"""|Usage:|Example'
  # (a2) collection prefixes / skymap / instrument class in logic:
  grep -rnE "Nickel/|nickelRings|lsst\\.obs\\.nickel\\.Nickel" packages/stips/src/stips --include=*.py | grep -vE '#|"""|Usage:|Example'
  ```
  SANITY: before migrating image_renderer.py, confirm the (a1) grep DOES fire on `dashboard/image_renderer.py:142,151` (proves the gate catches the escaped form); after migration both greps must be empty. Any hit is an un-migrated logic site → fix it (a code line that legitimately must keep "Nickel" is a miss, not an exclude).

  **(b) RESIDUAL audit — review, don't fail.** List every remaining `Nickel`/`nickelRings` mention and confirm each is one of the ALLOWED categories: (i) the Nickel-specific profile/test fixtures, (ii) a docstring/usage example, (iii) a comment. Enumerate the allowed remainders explicitly in the commit message (the known docstring-example files above are Phase-3 doc cleanup, intentionally left):
  ```bash
  grep -rn "Nickel\|nickelRings" packages/stips/src/stips --include=*.py
  ```
  Document the allowed list; anything not in (i)-(iii) is a miss to fix.

- [ ] **Step 4: Full suite + lint + an end-to-end smoke.** Run the whole suite under the stack (expect ~185+ passed). Then a profile-threading smoke: a `--dry-run` of `stips run` (or `stips science <night> --dry-run`) on the Nickel config and confirm the printed collection names/queries are byte-identical to a pre-2b dry-run (capture before/after). Lint clean.

- [ ] **Step 5: Commit** `refactor(stips): complete de-hardcode — tooling fully profile-driven`.

---

## Done criteria (Phase 2b)

- [ ] `stips.collections.CollectionNames` is prefix-parameterized; `Config.profile` carries the active instrument profile loaded from `INSTRUMENT_PACKAGE`.
- [ ] No `"Nickel/"`, `instrument='Nickel'`, `nickelRings`, `lsst.obs.nickel.Nickel`, or `night+1`-hardcode remains in `stips/src` logic — all profile-driven (grep gate clean).
- [ ] Nickel parity golden unchanged (byte-identical collections/queries/day_obs); synthetic profile proves genericity.
- [ ] Config/pipeline paths resolve via the configured instrument dir (not hardcoded `obs_nickel`), pipelines/configs remain fork assets.
- [ ] Full suite green; `stips run --dry-run` on Nickel produces identical output to pre-2b.
- [ ] Dev setup installs the obs packages alongside `stips`; a fork sets `INSTRUMENT_PACKAGE` + installs its `obs_<x>`.
```
