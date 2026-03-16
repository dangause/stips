# Phase 2B: Package Rename and Config Cleanup

**Date:** 2026-03-16
**Status:** Draft
**Goal:** Rename `obs_nickel_data_tools` to `small_tel_tools`, rename CLI from `nickel` to `stt`, clean up Config to be telescope-agnostic, and remove the `.env` file system.

**Prerequisite:** Phase 1 (obs_smalltel LSST package) and Phase 2 (plugin architecture, Config refactoring, CLI --instrument flag, YAML instrument field) are complete and validated across all 7 pipeline workstreams.

**Approach:** Clean break — no backward compatibility shims, no deprecation warnings, no re-exports of old names.

---

## Section 1: Package Rename

### Python Package

| Before | After |
|--------|-------|
| `obs_nickel_data_tools` | `small_tel_tools` |
| `from obs_nickel_data_tools.core.run import run` | `from small_tel_tools.core.run import run` |
| `from obs_nickel_data_tools.instruments import get_plugin` | `from small_tel_tools.instruments import get_plugin` |

**Directory change:**
```
packages/data_tools/src/obs_nickel_data_tools/  →  packages/data_tools/src/small_tel_tools/
```

The `packages/data_tools/` parent directory stays — it's the installable package root with `pyproject.toml`.

### CLI Entry Point

| Before | After |
|--------|-------|
| `nickel` | `stt` |
| `nickel run config.yaml` | `stt run config.yaml` |
| `nickel calibs 20230519` | `stt calibs 20230519` |

Updated in `pyproject.toml`:
```toml
[project.scripts]
stt = "small_tel_tools.cli:main"
```

### Auxiliary `obsn-*` Script Entry Points

The 10 `obsn-*` entry points in `pyproject.toml` are renamed to `stt-*` with updated import paths:

| Before | After |
|--------|-------|
| `obsn-archive-fetch-night` | `stt-archive-fetch-night` |
| `obsn-archive-nights` | `stt-archive-nights` |
| `obsn-archive-ingest-ps1` | `stt-archive-ingest-ps1` |
| `obsn-archive-template-meta` | `stt-archive-template-meta` |
| `obsn-dia-assess` | `stt-dia-assess` |
| `obsn-dia-lightcurve` | `stt-dia-lightcurve` |
| `obsn-skymap-build-config` | `stt-skymap-build-config` |
| `obsn-skymap-make` | `stt-skymap-make` |
| `obsn-eda-archive` | `stt-eda-archive` |
| `obsn-eda-butler` | `stt-eda-butler` |

All import paths change from `obs_nickel_data_tools.*` to `small_tel_tools.*`.

### pyproject.toml Metadata

Update `project.name` from `"obs-nickel-data-tools"` to `"small-tel-tools"` and update `project.description` to reflect multi-telescope scope.

### Plugin Entry Point Group

| Before | After |
|--------|-------|
| `obs_nickel_data_tools.instruments` | `small_tel_tools.instruments` |

Updated in `pyproject.toml`:
```toml
[project.entry-points."small_tel_tools.instruments"]
nickel = "small_tel_tools.instruments.nickel:NickelPlugin"
```

The plugin discovery code in `instruments/__init__.py` changes its `group=` parameter to match.

### All Internal Imports

Every `from obs_nickel_data_tools.*` import across the codebase becomes `from small_tel_tools.*`. This includes:
- All `core/*.py` modules importing each other
- `cli.py` importing core modules
- `instruments/*.py` importing base classes
- `pipeline_tools/*.py` importing core utilities
- Test files importing the package

---

## Section 2: Config Cleanup

### Move Lick-Specific Fields off Config

The `Config` dataclass currently has three Lick-specific fields:
- `lick_archive_dir`
- `lick_archive_url`
- `lick_archive_instr`

These move to `NickelPlugin` as class attributes. The plugin already has `archive_url` and `archive_instrument` — a new `archive_dir` class attribute is added:

```python
class NickelPlugin(InstrumentPlugin):
    archive_url: str = "https://archive.ucolick.org/archive"
    archive_instrument: str = "NICKEL_DIR"
    archive_dir: str | None = None  # new — set from LICK_ARCHIVE_DIR env var
```

`NickelPlugin.fetch_data()` already reads `LICK_ARCHIVE_DIR` from `os.environ` (line 43 of `nickel.py`) — this stays as-is. The `archive_dir` attribute provides a programmatic API for commands that need the value without going through env vars.

**Specific migration points:**
- `cli.py` download command (line 685-686): gets plugin via `_get_plugin(ctx)`, passes `plugin.archive_dir` instead of `config.lick_archive_dir`
- `core/stack.py` (line 76-77): the `export LICK_ARCHIVE_DIR=...` line is removed from the generic shell template. `NickelPlugin.fetch_data()` already reads this env var directly when needed.
- `cli.py` env command (line 312-313): add `plugin = _get_plugin(ctx)` call to the `env` command (currently missing), display archive info via plugin attributes instead of Config fields

### Remove `obs_nickel` Backward-Compat Alias

`Config` currently has:
```python
@property
def obs_nickel(self):
    return self.obs_package
```

This property is deleted. All references become `config.obs_package`.

### Remove `OBS_NICKEL` Env Var Fallback

Config currently reads `OBS_SMALLTEL` first, falls back to `OBS_NICKEL`. With clean break, only `OBS_SMALLTEL` is recognized.

---

## Section 3: Remove .env File System

### What Gets Deleted

- The module-level `config.load()` function's `.env` file parsing logic (env_file/extra_env parameters, dotenv reading)
- `-p`/`--profile` CLI option
- `--env-file` CLI option
- `.env.example` in the repo root (deleted — serves no purpose without `.env` file support)

### What Replaces It

**Pipeline runs (primary path):** YAML `env:` section already provides all configuration — no change needed. `RunConfig.from_yaml()` in `core/run.py` calls `config.load(inline_env=..., prefer_inline=True)`.

**Ad-hoc CLI commands:** Environment variables set in the user's shell:
```bash
export REPO=/data/nickel/repo
export STACK_DIR=/opt/lsst
export OBS_SMALLTEL=/path/to/obs_smalltel
export RAW_PARENT_DIR=/data/nickel/raw

stt calibs 20230519
```

### Config Loading

The current `config.load()` function (module-level, not a class method) handles both `.env` file parsing and env var reading. It is refactored:

| Before | After |
|--------|-------|
| `config.load(env_file=path)` | Deleted — no `.env` file support |
| `config.load(inline_env=dict, prefer_inline=True)` | Stays — used by `RunConfig.from_yaml()` for YAML `env:` section |
| `config.load()` (no args, reads env vars + default `.env`) | Simplified to `config.load()` reading only `os.environ` (no dotenv) |

The `load()` function signature simplifies to:
```python
def load(inline_env: dict[str, str] | None = None) -> Config:
```

When `inline_env` is provided (YAML pipeline runs), it merges with `os.environ` (inline wins). When not provided (ad-hoc CLI), it reads only from `os.environ`.

---

## Section 4: Update All `config.obs_nickel` References

Every reference to `config.obs_nickel` becomes `config.obs_package`. The backward-compat `@property` is deleted (Section 2), so any missed references become immediate `AttributeError`s.

**Complete reference list (26 occurrences across 10 files, verified by grep):**

| File | Count | Usage pattern |
|------|-------|---------------|
| `core/run.py` | 6 | Pipeline/config path resolution |
| `core/science.py` | 3 | DRP.yaml pipeline path, config paths |
| `core/dia.py` | 2 | DIA.yaml pipeline path, config paths |
| `core/stack.py` | 4 | Shell env export, eups setup, data_tools_src path |
| `core/calibs.py` | 2 | NickelCpBias.yaml, NickelCpFlat.yaml paths |
| `core/bootstrap.py` | 2 | Bootstrap script path |
| `core/bps.py` | 2 | BPS pipeline dir, template vars |
| `core/coadd.py` | 1 | DRP.yaml pipeline path |
| `core/fphot.py` | 1 | ForcedPhotRaDec.yaml path |
| `cli.py` | 2 | Env display, dashboard repo_root |

**Special case — `core/stack.py` shell template:**

The shell template has LSST eups-specific references:
```bash
export OBS_NICKEL="{config.obs_nickel}"     # → export OBS_SMALLTEL="{config.obs_package}"
setup -r "{config.obs_nickel}" obs_nickel   # → setup -r "{config.obs_package}" obs_smalltel
OBS_NICKEL_DATA="..."                       # → OBS_SMALLTEL_DATA="..."
setup -r "$OBS_NICKEL_DATA" obs_nickel_data # → setup -r "$OBS_SMALLTEL_DATA" obs_smalltel_data
```

The eups package names (`obs_nickel` → `obs_smalltel`, `obs_nickel_data` → `obs_smalltel_data`) match the Phase 1 LSST package rename.

---

## Section 5: Testing Strategy

**Approach:** Run existing 47 tests (across 4 test files) after each rename/cleanup step.

**Validation sequence:**
1. After package rename → all tests pass with new import paths
2. After CLI rename → `stt --help` works, old `nickel` entry point removed
3. After Config cleanup → tests construct Config via `obs_package` field
4. After .env removal → tests updated to use `config.load(inline_env=...)` or `config.load()` (env vars only)
5. Final: dry-run `scripts/config/2023ixf/pipeline_ps1_template.yaml` to confirm end-to-end orchestration

**No pipeline re-runs needed** — all 7 pipelines validated the current code. Phase 2B is a rename/cleanup refactor that doesn't change pipeline logic.

---

## Out of Scope

- Phase 3 (new telescope integration) — sequential after Phase 2B
- New test files — existing suite covers all affected code paths
- YAML pipeline config changes beyond updating the `instrument:` field (already done in Phase 2)
- obs_smalltel LSST package changes (Phase 1, already complete)
