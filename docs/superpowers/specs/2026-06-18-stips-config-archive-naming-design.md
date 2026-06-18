# STIPS Phase 4 — YAML-only Config, Optional Data Fetch, De-nickel the Framework

**Date:** 2026-06-18
**Status:** Approved (design)
**Author:** Dan Gause
**Branch:** `feature/stips-framework`

## 1. Goal

Finish making STIPS instrument-agnostic in its **config and plumbing** (the pipeline logic is
already generic after Phases 1–3). Three coupled parts:

- **A — YAML-only configuration.** Replace the `.env` files + `-p profile` mechanism with a
  single YAML config supplied via `stips -c/--config <file>`. The YAML is the **sole** config
  source — no `.env`, no `-p`, no `os.environ` fallback for config values.
- **B — Optional, instrument-provided data fetch.** Wire the dead `profile.fetch_data` hook so
  `stips download` is instrument-provided and optional; move the Lick-archive specifics out of
  the framework into the Nickel instrument.
- **C — De-nickel the framework + rename the repo.** Genericize the remaining framework-level
  "nickel" names (`OBS_NICKEL`→`INSTRUMENT_DIR`, `config.obs_nickel`→`config.instrument_dir`),
  fix the real fork-blocker bug (hardcoded `setup -r … obs_nickel` → driven by
  `profile.eups_package`), drop Nickel/Lick defaults, de-nickel framework docstrings, and
  update in-repo `nickel_processing_suite` references to `stips`.

## 2. Non-goals (explicitly deferred)

- **The full obs-package collapse is OUT of this spec.** Eliminating per-instrument
  `lsst.obs.<x>` packages in favor of declarative `instruments/<name>/` definitions consumed by
  a generic `obs_stips` (plus a friendly camera spec and generic-pipelines-with-config-overrides)
  is a SEPARATE, larger effort. Per the agreed sequencing it happens on a **fresh sub-feature
  branch off `feature/stips-framework`, AFTER A+B+C land and merge.** See §7.
- This spec keeps the current per-instrument `obs_nickel` package as-is structurally; it only
  de-nickels the *framework's references* to it.
- The physical filesystem rename of the repo directory (`nickel_processing_suite` → `stips`) and
  any git-remote change are manual ops steps (the GitHub remote is already `dangause/stips`);
  this spec only updates *in-repo references*.

## 3. Background (current state — verified)

- `stips/core/config.py:load()` reads config from `os.environ` + a `.env`/`.env.<profile>` file
  (default `.env`, or `ENV_FILE`), with layering (`extra_env`, `inline_env`, `prefer_inline`).
  Required keys: `REPO`, `STACK_DIR`, `OBS_NICKEL`, `RAW_PARENT_DIR`.
- `cli.py` has `-p/--profile` → `_resolve_env_file()` (maps to `.env.<profile>`) and
  `--env-file`. ~11 per-step commands (`calibs`, `science`, `dia`, `fphot`, `ps1-template`,
  `bps *`, `dashboard`, `env`) call `_load_config(ctx)` (env/profile only). 6 commands
  (`run`, `bootstrap`, `clean`, `calib-metrics`, `landolt-validate`, `download`) already extract
  a YAML `env:` block and call `_load_config(ctx, inline_env=…, prefer_inline=True)`.
- `get_env_from_yaml(path)` (`run.py`) already extracts the `env:` dict from a YAML.
- Lick archive: **already mostly optional** — `lick_archive_dir`/`LICK_ARCHIVE_*` are optional
  Config fields (not required), `lick_searchable_archive` is lazily imported (not a dependency),
  and no core step needs it. But the Lick defaults live in the framework `Config`, `stips
  download` is hardwired to the Lick client (`pipeline_tools/fetch_archive_night.py`), and
  `InstrumentProfile.fetch_data` (the intended seam) is declared but **never called**. Note:
  `config.lick_archive_instr="NICKEL_DIR"` is in fact a **dead/unused Config field** — the
  download path (`cli.py` argv build) never reads it; the tool's own filter default is `NICKEL`
  in `fetch_archive_night.py`. So dropping `lick_archive_instr`/`lick_archive_url` from the
  framework Config has **zero call-site rewiring**. `lick_searchable_archive` is itself an
  **in-repo package** (`packages/lick_searchable_archive/`), which informs where the Nickel-side
  Lick wrapper lives (§5.2).
- Naming: `OBS_NICKEL` is a **required** env var (`config.py`), `config.obs_nickel: Path` is used
  for repo-root traversal + sibling-package finding; **`stack.py` hardcodes
  `setup -r "{config.obs_nickel}" obs_nickel`** (the EUPS *product name* is literal — a fork's
  `obs_<x>` would never get set up) and `setup -r "$OBS_NICKEL_DATA" obs_nickel_data`. The
  profile already carries `eups_package` and `obs_data_package`. In-repo `nickel_processing_suite`
  references appear in README badges/trees and doc prose.

## 4. Part A — YAML-only configuration

### 4.1 Mechanism
- Add a top-level Click option on the `cli` group: `-c/--config <PATH>` (a YAML file). It
  replaces `-p/--profile` and `--env-file`.
- A single helper (e.g. `_load_config(ctx)`) reads the YAML at `ctx.obj["config_path"]`, extracts
  its `env:` block via `get_env_from_yaml`, and builds the `Config` from **that block only**.
- **The YAML `env:` block is the sole source of config values.** No `.env` parsing, no
  `os.environ` fallback for config keys. (Runtime-only vars the orchestrator sets at execution —
  e.g. `RUN_ID` — are unaffected; they are not config.) The `env:` block's values are
  still **exported into the LSST stack subprocess** by `run_with_stack` (that is runtime env, not
  config-from-env).
- **No `-c` given → error**, with an actionable message: `"No config provided. Pass -c
  <config.yaml> (its env: block supplies REPO, STACK_DIR, INSTRUMENT_DIR, RAW_PARENT_DIR)."`
  (Decision: strict error, NOT auto-discovery — matches "YAML only, no fallback". A future
  optional `stips.yaml` auto-discovery can be added but is out of scope.)
- The YAML block stays named `env:` (minimal churn; semantically apt since values are exported to
  the stack env). The full self-contained YAMLs (`scripts/config/*`) already have it and keep
  working via `-c`.

### 4.1a One `-c` file, two roles (resolves the double-YAML question)
The same `-c <config.yaml>` is the SINGLE YAML input. Two distinct consumers read DIFFERENT parts
of it, and must not be conflated:
- **Config** (this spec): only the `env:` block → builds `Config` (every command).
- **Pipeline spec** (unchanged, `run.py`/`RunConfig`): the non-`env:` sections (`object`, `ra`,
  `dec`, `bands`, `template`, `science`, `configs`, `options`, `lightcurve`) → consumed by
  `run.py` exactly as today, independently of the config path.
Therefore: the 6 commands that today take a **positional `config_file`** pipeline YAML
(`run`, `bootstrap`, `clean`, `calib-metrics`, `landolt-validate`, `download`) DROP that positional
arg in favor of the group-level `-c`; they read both the `env:` block (config) and their needed
non-`env:` sections from that one `-c` file. The per-step commands (`calibs`, `science`, `dia`,
`fphot`, etc.) read only the `env:` block from `-c` (they take their night/coords as command
args). Net: exactly one YAML path (`-c`), no positional YAML, no double extraction.

### 4.2 Removed
`_parse_env_file`, `_resolve_env_file`, `_expand_env_vars` (if only used by .env parsing),
`-p/--profile`, `--env-file`, the default `.env` lookup, the `ENV_FILE` var, `extra_env`, and the
`prefer_inline` flag (YAML is now always the source, so the precedence machinery collapses).
Delete the committed `.env*` files if any are tracked (the real `.env*` are user-local/gitignored).

### 4.3 `Config.load()` rewrite
`load()` simplifies to: take a YAML path (or an already-extracted `env` dict), read the `env:`
block, validate required keys (`REPO`, `STACK_DIR`, `INSTRUMENT_DIR`, `RAW_PARENT_DIR`), construct
`Config`.

**`lightcurve` (the `_load_lightcurve_config` path) — concrete decision (was a BLOCKING gap).**
`_load_lightcurve_config` (`cli.py:150-256`) is the largest `.env`/`os.environ` consumer today: it
loads from `.env`, and on failure auto-detects `STACK_DIR`/`OBS_NICKEL`/`RAW_PARENT_DIR` from
`os.environ` + cwd-walking, then builds `Config(...)` directly. Under YAML-only this whole
auto-detect block is **removed**. The `lightcurve` command becomes:
- It gains the group-level `-c` like every other command (its `env:` block is the config source), AND
- it keeps its existing **explicit** `--repo` / `--stack-dir` flags as a **sanctioned non-YAML
  override** (lightcurve is an analysis command often run ad-hoc against an arbitrary Butler repo;
  explicit flags are allowed, unlike implicit `.env`/`os.environ` discovery which is removed).
- Resolution: if `-c` is given, build `Config` from its `env:` block (with `--repo`/`--stack-dir`
  overriding those two keys if also passed); else require `--repo` (and resolve `--stack-dir` or
  error — no `os.environ`/cwd auto-detection). The active profile still comes from
  `INSTRUMENT_PACKAGE` (its default), not from cwd-walking for an obs package.
Keep `_load_lightcurve_config` small and explicit; delete the `os.environ`/auto-detect branches.

### 4.4 Tests
- `Config` built from a YAML fixture (a temp `config.yaml` with an `env:` block) — no `.env`.
- Missing-`-c` (and missing required key) raises the actionable error.
- The existing per-target YAMLs (`scripts/config/2023ixf/*.yaml`) still load via the new path.
- Existing config tests (`test_run_config`, `test_config_profile`) updated to the YAML path.

## 5. Part B — Optional, instrument-provided data fetch

### 5.1 The seam
- `InstrumentProfile.fetch_data` is a callable that downloads/places raw data under
  `config.raw_parent_dir/<night>/raw/`. To preserve the current 3-way "downloaded / not in
  archive / failed" UX (`cli.py:669-710`), it RETURNS a status rather than `None`:
  `fetch_data(night: str, config: Config) -> str` returning one of `"ok"`, `"not_found"`,
  `"failed"` (a tiny enum/`Literal`; `download` maps these to the existing messages/exit codes).
  Document the contract + the return values on the dataclass field.
- `stips download <night>` (and its YAML-config form) becomes:
  ```
  prof = config.require_profile()
  if prof.fetch_data is None:
      raise ClickException(f"Data download is not configured for instrument '{prof.name}'. "
                           f"Place raw FITS under {config.raw_parent_dir}/<night>/raw/.")
  status = prof.fetch_data(night, config)   # "ok" | "not_found" | "failed"
  # map status to the existing per-night success / not-in-archive / failed reporting + exit code
  ```
- `pipeline_tools/fetch_archive_night.py` (and the EDA `archive_query.py`) — the Lick-specific
  client wrapper — **moves to the Nickel instrument's concern** (see 5.2). The framework no
  longer hardwires the Lick client into the `download` command.

### 5.2 Nickel wires its own fetch
- The Nickel profile sets `fetch_data=<a Nickel function>` that lazily imports the Lick client
  (`lick_searchable_archive`) and performs the fetch, using Lick-specific settings (archive URL,
  the `NICKEL_DIR` instrument filter, the client path). Those Lick settings live with Nickel —
  either in the Nickel profile/instrument package, or read from the YAML `env:` block as
  Nickel-specific keys — **not** as framework `Config` defaults.
- The Lick client code itself (`fetch_archive_night.py` logic, `lick_searchable_archive`) stays
  Lick/Nickel-owned; the framework just calls the hook. (Where exactly the Lick wrapper lives —
  obs_nickel package vs a small `stips_lick`/Nickel-side module — is an implementation detail for
  the plan; the key constraint is it is NOT in the generic `stips`/`obs_stips` framework.)

### 5.3 Remove Lick from the framework `Config`
Drop `lick_archive_url`, `lick_archive_instr` (the `"NICKEL_DIR"` default), and the
framework-level `lick_archive_dir` requirement/handling from `Config`. Any Lick value the Nickel
fetch needs comes from the YAML `env:` block (Nickel-specific keys) or the Nickel profile.

### 5.4 Tests
- `download` with a profile whose `fetch_data is None` → the clean ClickException (no crash, no
  Lick import).
- `download` dispatches to `profile.fetch_data` when present (assert the hook is called; mock it).
- The framework `Config` no longer carries `LICK_*` fields.

## 6. Part C — De-nickel the framework + rename repo references

### 6.1 Env/field genericization
- The required config key `OBS_NICKEL` → **`INSTRUMENT_DIR`** (path to the active instrument
  package dir). Accept `OBS_NICKEL` as a **deprecated alias** in the YAML `env:` block for one
  release (warn), so the existing `scripts/config/*` YAMLs keep working; update those YAMLs to
  `INSTRUMENT_DIR`.
- **Config field rename (was a BLOCKING gap).** Today `Config.obs_nickel: Path` is the PRIMARY
  required field and `instrument_dir` is *derived from it* in `__post_init__`. Invert that: make
  **`instrument_dir`** the real field (populated from the `INSTRUMENT_DIR` YAML key, falling back
  to the deprecated `OBS_NICKEL` key with a warning), and keep **`obs_nickel` as a deprecated
  read-only `@property` returning `self.instrument_dir`** for one release (so any external/holdout
  caller doesn't break). Update the INTERNAL direct constructors (`cli.py:254`, `config.py:361`)
  and ALL tests that build `Config(obs_nickel=…)` (`test_config_profile.py:29`, `test_executor.py`,
  `test_bps_config.py`) to use `instrument_dir=…`. Migrate the repo-root traversal + sibling-package
  finding (`bootstrap.py`, `bps.py`, `run.py`, `cli.py` dashboard, `stack.py`) onto
  `config.instrument_dir`.
- `stips env` output and any display strings use `INSTRUMENT_DIR`/`instrument_dir`.

### 6.2 The real bug: profile-driven EUPS setup
- `stack.py` currently does `setup -r "{config.obs_nickel}" obs_nickel` and
  `setup -r "$OBS_NICKEL_DATA" obs_nickel_data` with **hardcoded product names**. Drive them from
  the profile: `setup -r "{config.instrument_dir}" {profile.eups_package}` and the data package
  from `profile.obs_data_package` (skip if unset). This is required for any non-Nickel fork's
  instrument package to actually be set up in the stack subprocess.

### 6.3 Drop Nickel-specific defaults
`LICK_ARCHIVE_INSTR="NICKEL_DIR"` and other Lick defaults leave the framework (folds into Part B).
The `INSTRUMENT_PACKAGE` default `"lsst.obs.nickel"` **stays** (a reasonable default; a fork
overrides it in the YAML).

### 6.4 De-nickel framework docstrings/help
`stips/core/__init__.py` ("for obs_nickel" → generic), `stips/eda/__init__.py`, the `cli.py`
`ps1-template` "Nickel band" help (→ profile/band-aware or generic), the dashboard default
instrument name (→ `config.profile.name`). Surgical; framework only.

### 6.5 Repo-name references → `stips`
Update in-repo references to the repo identity: README badge URLs (→ `dangause/stips`), monorepo
structure trees showing `nickel_processing_suite/`, and any doc prose/path strings using the repo
dir name. **Also update `CLAUDE.md`** (which still says `cd nickel_processing_suite`, documents
`-p`/`.env` profiles, and `uv pip install -e packages/stips`) to YAML-only config + the new
naming — note `CLAUDE.md` is **gitignored** (repo policy), so it's a LOCAL working-tree edit, not
a commit. Do NOT attempt the physical directory `mv` (manual ops step; would disrupt the active
worktree). Code uses relative traversal (`config.instrument_dir.parent…`), not the literal repo
name, so reference updates are safe ahead of the physical rename.

### 6.6 Tests
- A synthetic profile with `eups_package="obs_demo"` produces a stack-setup script containing
  `setup -r … obs_demo` (proves the EUPS-name bug is fixed).
- `INSTRUMENT_DIR` is read; `OBS_NICKEL` alias still accepted (with a deprecation warning).
- Nickel still resolves identical paths/behavior.

## 7. Sequencing & the deferred full-collapse

1. **This spec (A+B+C)** is implemented (likely as 3 plans, A → B → C), reviewed, and **merged
   into `feature/stips-framework`.**
2. **Then**, on a **fresh sub-feature branch off `feature/stips-framework`**, the **full
   obs-package collapse** is designed + built and merged back into `feature/stips-framework`:
   - Eliminate per-instrument `lsst.obs.<x>` packages; a fork defines a telescope in a root-level
     `instruments/<name>/` directory (Python profile + camera spec + optional config tuning).
   - The generic `obs_stips` synthesizes the LSST instrument/translator/formatter + Butler
     registration from the active profile, and ships generic pipelines.
   - A friendly camera spec (CCD size, pixel scale, orientation) that generates the LSST
     `camera.yaml`; forks override only a few pipeline config values.
   - `obs_nickel` becomes `instruments/nickel/` (the reference *definition*, not a package).
   This is explicitly a separate spec/plan cycle; keeping streams sequential (no concurrent
   work).

## 8. Risks

- **A breaks every per-step command's config path at once.** Mitigation: the YAML `env:`
  extraction already exists for 6 commands; A generalizes it to all via the group-level `-c`.
  Stage A so the suite stays green; update the per-target YAMLs + tests together.
- **Field rename breaks direct `Config(...)` constructors + tests.** `Config(obs_nickel=…)` is
  built directly at `cli.py:254`, `config.py:361`, and in `test_config_profile.py:29`,
  `test_executor.py`, `test_bps_config.py`. §6.1 handles this (rename field → `instrument_dir`,
  keep `obs_nickel` as a deprecated property, update all internal constructors + tests in the same
  change) — but it MUST be done atomically or the suite goes red.
- **~28 per-target YAMLs carry `OBS_NICKEL`, none carry `INSTRUMENT_DIR`** (`scripts/config/**`,
  plus Docker/HPC variants). The deprecated-`OBS_NICKEL`-alias path (§6.1) is what lets A/C land
  without rewriting all 28 at once; migrate them to `INSTRUMENT_DIR` opportunistically. Update at
  least the canonical 2023ixf/2020wnt ones used by tests.
- **The Lick client is an in-repo package** (`packages/lick_searchable_archive/`). Part B's
  "move Lick out of the framework" → the Nickel-side `fetch_data` wrapper (a Nickel module that
  lazily imports the in-repo `lick_archive`) is the path of least resistance; it must NOT live in
  `stips`/`obs_stips`.
- **B's "where does the Lick wrapper live" choice** affects whether `lick_searchable_archive`
  leaks into the framework. Constraint: it must end up Nickel-owned; the plan picks the concrete
  home (obs_nickel package vs a Nickel-side module) without putting it in `stips`/`obs_stips`.
- **C's `OBS_NICKEL`→`INSTRUMENT_DIR` rename + the deprecated alias** must not silently double-read
  both; precedence is `INSTRUMENT_DIR` then `OBS_NICKEL` (deprecated, warn).
- **Repo-name reference updates without the physical rename** could read oddly (refs say `stips`,
  dir is still `nickel_processing_suite`). Acceptable and intended; the physical mv is a later
  manual step.
- The deferred full-collapse will revisit `instrument_dir` semantics (no obs package), so keep
  Part C's `instrument_dir` abstraction clean (a single field/accessor) to ease that follow-on.
