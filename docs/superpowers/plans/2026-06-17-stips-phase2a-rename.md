# STIPS Phase 2a — Rename & Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the `data_tools` tooling into the existing `packages/stips` package and rename `obs_nickel_data_tools`→`stips` and the CLI `nickel`→`stips` (console scripts `obsn-*`→`stips-*`), with **zero behavior change** — the pipeline still hardcodes "Nickel" everywhere (that is Phase 2b).

**Architecture:** Move every tooling module (`core/`, `cli.py`, `pipeline_tools/`, `eda/`, `skymap/`, `dashboard/`) from `packages/data_tools/src/obs_nickel_data_tools/` into the existing `packages/stips/src/stips/` (which already holds `profile.py`). Mechanical namespace rewrite `obs_nickel_data_tools`→`stips`. The unified `stips` distribution gains the CLI entry points + base deps; the heavy FastAPI dashboard becomes an optional `stips[dashboard]` extra so `obs_stips` (which depends on `stips`) stays light. `packages/data_tools` is deleted. `stips/__init__.py` stays import-light (re-exports only the profile types, never `core`/`cli`).

**Tech Stack:** Python 3.12, uv workspace, pytest (unittest + pytest styles), ruff + black (pre-commit), Click CLI, LSST stack (imported lazily/at runtime by the tooling).

**Scope note:** This is **Phase 2a** of the spec (`docs/superpowers/specs/2026-06-17-stips-multi-instrument-framework-design.md`, §3.4/§6-phase-2). Phase 2b (the actual de-hardcode: profile-driven `CollectionNames`, `instrument='Nickel'` predicates, `SKYMAP_NAME`/`SKYMAPS_CHAIN`/`INSTRUMENT` constants, `night_to_day_obs` offset, config/pipeline path resolution) is a SEPARATE plan that runs after this. **Do not de-hardcode anything in 2a** — only rename/move. After 2a the `stips` CLI must behave byte-for-byte like the old `nickel` CLI.

**Branch/worktree:** Work in `/Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1` on branch `feature/stips-framework`. `cd` there for every command.

**Critical invariants:**
1. `from stips import InstrumentProfile, Site, Field, hook` must keep working and stay import-light (no LSST, no click pulled at import). `obs_stips` depends on it. **Never** add eager `core`/`cli` imports to `stips/__init__.py`.
2. The sed rewrite target is the EXACT string `obs_nickel_data_tools` — it must NOT touch `obs_nickel` (the obs package) or `obs_nickel_data` (the calib data package). The literal `obs_nickel_data_tools` is longer and unambiguous, so `s/obs_nickel_data_tools/stips/g` is safe.
3. Do NOT rewrite `obs_nickel_data_tools` inside `docs/superpowers/**` — those files describe the rename in prose and must keep the old name.

---

## Reference (read before starting)
- Spec: `docs/superpowers/specs/2026-06-17-stips-multi-instrument-framework-design.md`
- Current package: `packages/data_tools/src/obs_nickel_data_tools/` (modules: `cli.py`, `core/` ×~22, `pipeline_tools/` ×8, `eda/` ×3, `skymap/` ×2, `dashboard/`, `__init__.py`)
- Current tooling pyproject: `packages/data_tools/pyproject.toml` (`name = "obs-nickel-data-tools"`; `[project.scripts]` = `nickel` + 11 `obsn-*`)
- Existing core package: `packages/stips/` (`pyproject.toml` name=`stips`, `src/stips/profile.py`, `src/stips/__init__.py`)
- Tests that import the tooling (currently in `packages/obs_nickel/tests/`): `test_executor.py`, `test_run_config.py`, `test_bps_config.py`, `test_ps1_templates.py`, `test_transit.py`, `test_period.py`, `test_fphot_collection_selection.py`
- External refs: `docker/entrypoint.sh` (`from obs_nickel_data_tools.dashboard import create_app`), `scripts/utilities/with-stack.sh` (comment), several `docs/*.md`

---

## File Structure (end state)

```
packages/stips/
  pyproject.toml                 # name="stips"; gains [project.scripts] (stips + stips-*) + base deps + [project.optional-dependencies].dashboard
  src/stips/
    __init__.py                  # UNCHANGED light profile re-exports (+ package docstring)
    profile.py                   # unchanged (Phase 1)
    cli.py                       # moved from data_tools (stips.cli:main)
    core/                        # moved (config, stack, bootstrap, calibs, science, dia, fphot, coadd, run, pipeline, executor, bps, clean, lightcurve, ps1_template, landolt, transit, period, processing_log, calib_metrics, dia, __init__)
    pipeline_tools/              # moved (fetch_archive_night, generate_nights_list, ingest_ps1_template, template_metadata, assess_dia_quality, extract_lightcurve, extract_calib_metrics, validate_landolt, __init__)
    eda/                         # moved (archive_query, butler_inspect, formatters, __init__)
    skymap/                      # moved (build_discrete_skymap_config, make_skymap_from_datasets, __init__)
    dashboard/                   # moved (app, analysis, butler_query, catalog_query, collector, image_renderer, static/, templates/, __init__)
  tests/                         # gains the moved tooling tests (test_executor, test_run_config, test_bps_config, test_ps1_templates, test_transit, test_period, test_fphot_collection_selection) + the existing test_profile.py
packages/data_tools/             # DELETED entirely
pyproject.toml (root)            # remove "packages/data_tools" from [tool.ruff].src; ensure "packages/stips/tests" in testpaths (already there)
docker/entrypoint.sh             # from stips.dashboard import create_app
docs/*.md, README.md             # path/name updates (NOT docs/superpowers/**)
```

---

## Task 1: Move the tooling modules into `packages/stips` and rewrite the namespace

This is one atomic refactor (the package won't import until the move + rewrite are both done), guarded by the existing test suite.

**Files:** `git mv` the tooling tree; rewrite imports across the moved files + the tooling tests; edit `stips/core/stack.py` PYTHONPATH; preserve `stips/__init__.py`.

- [ ] **Step 1: Move the tooling modules with `git mv` (preserve history)**

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1
SRC=packages/data_tools/src/obs_nickel_data_tools
DST=packages/stips/src/stips
git mv "$SRC/cli.py" "$DST/cli.py"
for d in core pipeline_tools eda skymap dashboard; do
  git mv "$SRC/$d" "$DST/$d"
done
# The old top-level package __init__.py is just a docstring; do NOT overwrite the
# existing stips/__init__.py (which has the profile re-exports). Inspect both first:
git show HEAD:packages/data_tools/src/obs_nickel_data_tools/__init__.py
cat "$DST/__init__.py"
# Then remove the old one (its content is not needed — stips/__init__.py stays as-is, light):
git rm "$SRC/__init__.py"
```
After this, `packages/data_tools/src/obs_nickel_data_tools/` should be empty of modules.

- [ ] **Step 2: Move the tooling tests into `packages/stips/tests`**

```bash
mkdir -p packages/stips/tests
for t in test_executor test_run_config test_bps_config test_ps1_templates test_transit test_period test_fphot_collection_selection; do
  git mv "packages/obs_nickel/tests/$t.py" "packages/stips/tests/$t.py" 2>/dev/null || echo "skip $t (not found)"
done
```
(If any of those test files don't exist or don't actually import the tooling, leave them in obs_nickel/tests — verify with `grep -l obs_nickel_data_tools packages/obs_nickel/tests/*.py` BEFORE moving, and only move the ones that match.)

- [ ] **Step 2b: Repath the `sys.path` bootstrap in the moved test files (CRITICAL — the sed misses this)**

Each of the 7 moved test files contains a self-bootstrap line like:
```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_tools/src"))
```
This is how they import the tooling today (it is NOT installed in the test venv via this path — the literal is `"data_tools/src"`, which the `obs_nickel_data_tools`→`stips` sed does NOT touch). After the `git mv` to `packages/stips/tests/`, `parents[2]` is still `packages/`, and `packages/data_tools/src` is deleted in Task 2. Fix every occurrence so it points at the new source tree (from `packages/stips/tests/`, `parents[1]` is `packages/stips`):
```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1
grep -rln 'data_tools/src' packages/stips/tests
grep -rln 'data_tools/src' packages/stips/tests | xargs sed -i '' 's#parents\[2\] / "data_tools/src"#parents[1] / "src"#g'
grep -rn 'data_tools/src' packages/stips/tests || echo "bootstrap repathed ✓"
```
Also fix the now-false docstring in `test_fphot_collection_selection.py` ("Import fphot module from data_tools source tree." → "...from the stips source tree.") and any similar stale comment surfaced by `grep -rn "data_tools" packages/stips/tests`.

- [ ] **Step 3: Rewrite the namespace `obs_nickel_data_tools` → `stips` everywhere it's an import/module ref**

Scope: all `.py` under `packages/stips/` and the moved tests, plus `docker/entrypoint.sh` and `scripts/utilities/with-stack.sh`. EXCLUDE `docs/superpowers/**` (prose), `.git`, build artifacts.

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1
# Find every file still referencing the old namespace, excluding docs/superpowers and build dirs:
grep -rl "obs_nickel_data_tools" packages/stips docker scripts \
  --include="*.py" --include="*.sh" 2>/dev/null
# Rewrite them (macOS sed needs the empty -i arg):
grep -rl "obs_nickel_data_tools" packages/stips docker scripts \
  --include="*.py" --include="*.sh" 2>/dev/null \
  | xargs sed -i '' 's/obs_nickel_data_tools/stips/g'
# Verify NONE remain in code (docs/superpowers intentionally still has the old name):
grep -rn "obs_nickel_data_tools" packages/stips docker scripts --include="*.py" --include="*.sh" || echo "clean ✓"
```
**Sanity:** confirm the rewrite did NOT touch `obs_nickel` / `obs_nickel_data`:
```bash
grep -rn "import stips" packages/stips/src/stips/core/__init__.py   # should show stips.core.* style imports now
grep -rn "lsst.obs.nickel" packages/stips/src/stips | head          # these must be UNCHANGED (still lsst.obs.nickel — that's the obs package, Phase 2b de-hardcodes)
```

- [ ] **Step 4: Fix the PYTHONPATH block in the moved `stips/core/stack.py`**

`run_with_stack()` had a block adding `data_tools/src` to PYTHONPATH so `obs_nickel_data_tools` was importable. The tooling now lives in `packages/stips/src`, which Phase 1 ALREADY put on PYTHONPATH (the `STIPS_SRC` block). So the `data_tools_src` block is now stale. In `packages/stips/src/stips/core/stack.py`:
- Remove the `data_tools_src = config.obs_nickel.parent / "data_tools" / "src"` computation and the corresponding `DATA_TOOLS_SRC` shell block.
- Confirm the existing `STIPS_SRC = config.obs_nickel.parent / "stips" / "src"` block remains (it makes the tooling importable now).
Read the function and make this surgical edit only.

- [ ] **Step 5: Make `stips/__init__.py` is still light + add a package docstring**

Confirm `packages/stips/src/stips/__init__.py` still only does `from .profile import Field, InstrumentProfile, Site, hook` (+ `__all__`). It must NOT import `cli`, `core`, etc. Optionally prepend a one-line module docstring `"""STIPS — Small Telescope Image Processing Suite."""`. Verify import-lightness:
```bash
.venv/bin/python -c "import stips; print(sorted(stips.__all__))"   # works without LSST/click
```
(Use the worktree `.venv`; `stips` core needs only astropy.)

- [ ] **Step 6: Run the moved tooling tests + the import-light check**

Most tooling tests are stack-free (they mock subprocess/stack). Run them with the worktree venv after installing the merged package:
```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1
uv pip install --python .venv -e packages/stips
.venv/bin/python -m pytest packages/stips/tests -v
```
Expected: the moved tests (test_executor, test_run_config, test_bps_config, test_ps1_templates, test_transit, test_period, test_fphot_collection_selection) + test_profile PASS, same as before the move. If a test genuinely needs the LSST stack, run it under the stack instead (source loadLSST; setup lsst_distrib; `setup -r packages/obs_nickel obs_nickel`; `setup -r packages/obs_stips obs_stips`; `export PYTHONPATH="$PWD/packages/stips/src:$PWD/packages/obs_stips/python:$PYTHONPATH"`) and report which. **No test logic changes** — only the import path moved.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(stips): merge data_tools tooling into stips package; rewrite namespace obs_nickel_data_tools->stips"
```
(Pre-commit may reformat; re-stage/re-commit until clean. Renames should show as `R`.)

---

## Task 2: Merge pyproject (CLI entry points + deps), delete `data_tools`, fix root config

**Files:** `packages/stips/pyproject.toml`, delete `packages/data_tools/`, root `pyproject.toml`.

- [ ] **Step 1: Read both pyprojects**

```bash
cat packages/data_tools/pyproject.toml
cat packages/stips/pyproject.toml
```
Note from data_tools: the `[project.dependencies]`, the `[project.scripts]` (12 entries), any `[project.optional-dependencies]`, and the dashboard deps (fastapi/jinja2/sse-starlette etc.).

- [ ] **Step 2: Update `packages/stips/pyproject.toml`**

- Keep `name = "stips"`, `where = ["src"]`.
- Merge data_tools `[project.dependencies]` into stips's (union; keep `astropy`; add click, pyyaml, numpy, requests, etc. — whatever data_tools required). **Move the dashboard-only heavy deps (fastapi, jinja2, sse-starlette, uvicorn, any web-only libs) OUT of base deps into:**
  ```toml
  [project.optional-dependencies]
  dashboard = ["fastapi", "jinja2", "sse-starlette", "uvicorn"]   # use the exact names/versions from data_tools
  ```
- Add `[project.scripts]` renaming every entry point: `nickel`→`stips`, every `obsn-*`→`stips-*`, all pointing at `stips.*` modules:
  ```toml
  [project.scripts]
  stips = "stips.cli:main"
  stips-archive-fetch-night = "stips.pipeline_tools.fetch_archive_night:main"
  stips-archive-nights = "stips.pipeline_tools.generate_nights_list:main"
  stips-archive-ingest-ps1 = "stips.pipeline_tools.ingest_ps1_template:main"
  stips-archive-template-meta = "stips.pipeline_tools.template_metadata:main"
  stips-dia-assess = "stips.pipeline_tools.assess_dia_quality:main"
  stips-dia-lightcurve = "stips.pipeline_tools.extract_lightcurve:main"
  stips-skymap-build-config = "stips.skymap.build_discrete_skymap_config:main"
  stips-skymap-make = "stips.skymap.make_skymap_from_datasets:main"
  stips-eda-archive = "stips.eda.archive_query:main"
  stips-eda-butler = "stips.eda.butler_inspect:main"
  ```
  (Cross-check the exact set against data_tools `[project.scripts]` — there were 11 `obsn-*` + the `nickel` main. If a `dashboard` console script existed, map it to `stips-dashboard`.)
- If `obs_stips`/`obs_nickel` pyproject reference `obs-nickel-data-tools` as a dep anywhere, remove it (they shouldn't). Grep: `grep -rn "obs-nickel-data-tools\|obs_nickel_data_tools" packages/*/pyproject.toml`.

- [ ] **Step 2.5: Confirm `obs_stips` does NOT gain the CLI/dashboard deps**

`obs_stips` depends on `stips`. Confirm `stips`'s BASE (non-optional) deps don't include fastapi/jinja (they're in the `dashboard` extra). This keeps obs packages light. (No code change — just verify the dep split is correct.)

- [ ] **Step 3: Delete the `data_tools` package**

```bash
git rm -r packages/data_tools
ls packages/   # data_tools gone; stips, obs_stips, obs_nickel, obs_nickel_data, defects, etc. remain
```

- [ ] **Step 4: Root `pyproject.toml`**

- Remove `"packages/data_tools"` from `[tool.ruff].src`.
- Remove `"packages/data_tools"` from `[tool.pyright].include` (it's a second stale reference, ~line 111), and add `"packages/stips"` + `"packages/obs_stips"` there for consistency with ruff `src`.
- Confirm `"packages/stips/tests"` is in `[tool.pytest.ini_options].testpaths` (added in Phase 1) and `"packages/obs_nickel/tests"` remains. Fix the now-false comment near `testpaths` (~line 77: "All tests (including data_tools unit tests) live in obs_nickel/tests/") and drop the commented-out `# "packages/data_tools/tests"` line.
- The `[tool.uv.workspace].members = ["packages/*"]` glob auto-drops the deleted dir — no change needed.

- [ ] **Step 5: Reinstall + verify the `stips` console script exists and runs**

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1
uv pip install --python .venv -e packages/stips
.venv/bin/stips --help            # the renamed CLI; prints the command group help, exit 0
.venv/bin/stips env --help        # a subcommand resolves
# a renamed console script resolves (may error on missing args, but must not be "command not found"):
.venv/bin/stips-eda-butler --help 2>&1 | head -3
```
Expected: `stips --help` works (this proves the entry-point rename + package import path). `nickel` should no longer exist as a console script.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(stips): move CLI entry points into stips pyproject (nickel->stips, obsn-*->stips-*); delete data_tools package; dashboard as optional extra"
```

---

## Task 3: Update external references (obs_nickel tests already moved; docker, scripts, docs)

**Files:** `docker/entrypoint.sh`, `scripts/utilities/with-stack.sh`, `docs/*.md`, `packages/data_tools/README.md` (deleted in Task 2 — skip), `packages/obs_nickel/tests/` leftovers.

- [ ] **Step 1: Confirm no obs_nickel test still imports the old namespace**

```bash
grep -rln "obs_nickel_data_tools" packages/obs_nickel/tests || echo "none ✓"
```
If any remain (a test that imports the tooling but wasn't moved in Task 1), either move it to `packages/stips/tests` (`git mv`) or rewrite its import to `stips` in place — choose move if it's purely a tooling test. Re-run `pytest packages/stips/tests packages/obs_nickel/tests -q` (stack as needed).

- [ ] **Step 2: Update docker + shell + docs (code/path refs, not the spec)**

`docker/entrypoint.sh` line ~117 was rewritten by Task 1's sed (it was in the sed scope) → confirm it now reads `from stips.dashboard import create_app`:
```bash
grep -n "stips.dashboard\|obs_nickel_data_tools" docker/entrypoint.sh
```
Update the remaining human-readable docs (`docs/architecture.md`, `docs/architecture-bps-docker-slurm.md`, `docs/calibration_metrics_assessment.md`, `scripts/config/landolt_validation/EXPANDING_COVERAGE.md`, top-level `README.md` if it references the tree) to use `packages/stips/src/stips/...` paths and the `stips`/`python -m stips.cli` invocations. **Do NOT touch `docs/superpowers/**`.** These are doc-only edits; keep them minimal and accurate.

- [ ] **Step 3: Full verification**

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1
# Full suite under the stack (the tooling tests + obs packages):
source /Users/dangause/Developer/lick/lsst/lsst_stack/loadLSST.zsh; setup lsst_distrib
setup -r packages/obs_nickel obs_nickel 2>/dev/null || true
setup -r packages/obs_stips obs_stips 2>/dev/null || true
export OBS_NICKEL="$PWD/packages/obs_nickel"
export PYTHONPATH="$PWD/packages/stips/src:$PWD/packages/obs_stips/python:$PYTHONPATH"
python -m pytest packages/stips/tests packages/obs_stips/tests packages/obs_nickel/tests -q
# Lint:
uvx ruff check packages/stips packages/obs_stips packages/obs_nickel
# Final namespace sweep (only docs/superpowers should still mention the old name):
grep -rn "obs_nickel_data_tools" packages docker scripts --include="*.py" --include="*.sh" --include="*.toml" || echo "code clean ✓"
```
Expected: full suite at its prior count (the Phase-1 185 + the moved tooling tests, all passing), lint clean, no `obs_nickel_data_tools` left in code/config.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: update docker/docs/test references from obs_nickel_data_tools to stips"
```

---

## Task 4: Rename user-facing `nickel` CLI strings → `stips`

**Files:** `packages/stips/src/stips/cli.py` (help text/docstrings only).

- [ ] **Step 1: Update CLI help text and examples**

In `cli.py`:
- Root group docstring: `"Nickel Processing Suite - LSST pipeline tools for Nickel telescope data."` → `"STIPS - Small Telescope Image Processing Suite. LSST pipeline tools."` (or similar).
- All example lines in command docstrings that show `nickel <subcommand>` → `stips <subcommand>` (env, calibs, science, dia, download, ps1-template, fphot, lightcurve, bps examples).
Grep first to find them, then edit ONLY the docstring/example lines. **Tighten the grep to exclude `obs_nickel`** so you don't accidentally touch the `obs_nickel` env/path-discovery logic (e.g. `obs_nickel = Path(os.environ["OBS_NICKEL"])`, the `# If cwd is obs_nickel itself` comment) — those must stay:
```bash
grep -n "nickel " packages/stips/src/stips/cli.py | grep -v "obs_nickel"
```
Edit only the lines that are user-facing CLI examples/help (`nickel <subcommand>` → `stips <subcommand>`) and the group docstring branding. Do NOT change any `obs_nickel` path/env logic.
**Also leave alone:** the BPS `--project default="nickel"` option value (it's a runtime account/submission label, not the CLI name — Phase 2b decides whether/what to rebrand it). Do NOT change any `lsst.obs.nickel` strings, any `"Nickel/..."` collection literals, or `instrument='Nickel'` (all Phase 2b). This task is ONLY the CLI command name in human-facing help.

- [ ] **Step 2: Verify help renders the new name**

```bash
.venv/bin/stips --help | head -5            # shows STIPS branding, not "Nickel Processing Suite"
.venv/bin/stips calibs --help | grep -i "stips calibs" && echo "examples updated ✓"
```

- [ ] **Step 3: Commit**

```bash
git add packages/stips/src/stips/cli.py
git commit -m "docs(cli): rename user-facing nickel CLI examples/branding to stips"
```

---

## Done criteria (Phase 2a)

- [ ] `packages/data_tools` is gone; all its modules live under `packages/stips/src/stips/` (renames preserved in git history).
- [ ] `obs_nickel_data_tools` appears NOWHERE in code/config (only in `docs/superpowers/**` prose). `lsst.obs.nickel` / `"Nickel/"` / `instrument='Nickel'` literals are UNCHANGED (Phase 2b).
- [ ] `from stips import InstrumentProfile` still works and is import-light (no LSST/click pulled); `obs_stips` import + tests unaffected.
- [ ] `stips` is the CLI command (`stips --help` works); `obsn-*` are now `stips-*`; `nickel` is gone. Dashboard deps are an optional `stips[dashboard]` extra (not pulled by `obs_stips`).
- [ ] Full test suite green at its prior count; ruff clean. Behavior unchanged (still Nickel-hardcoded).
- [ ] The pipeline still runs exactly as before under the new command name (Phase 2b makes it instrument-agnostic).
