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

These move to `NickelPlugin` as attributes. The plugin already has `archive_url` and `archive_instrument` — `lick_archive_dir` joins them as `archive_dir`.

Code that currently reads `config.lick_archive_dir` will instead call `plugin.archive_dir`.

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

- `Config.from_env()` class method
- `Config.from_env_file()` class method
- `-p`/`--profile` CLI option
- `--env-file` CLI option
- All `.env.*` files in the repo root

### What Replaces It

**Pipeline runs (primary path):** YAML `env:` section already provides all configuration — no change needed.

**Ad-hoc CLI commands:** Environment variables set in the user's shell:
```bash
export REPO=/data/nickel/repo
export STACK_DIR=/opt/lsst
export OBS_SMALLTEL=/path/to/obs_smalltel
export RAW_PARENT_DIR=/data/nickel/raw

stt calibs 20230519
```

### Config Constructors

| Before | After |
|--------|-------|
| `Config.from_env()` | Deleted |
| `Config.from_env_file(path)` | Deleted |
| `Config.from_yaml(yaml_dict)` | Stays (primary constructor for pipeline runs) |
| — | `Config.from_env_vars()` (new — reads from environment variables for ad-hoc CLI) |

---

## Section 4: Update All `config.obs_nickel` References

Every reference to `config.obs_nickel` becomes `config.obs_package`. The backward-compat `@property` is deleted (Section 2), so any missed references become immediate `AttributeError`s.

Primary locations:
- `core/stack.py` — LSST stack activation (`setup -r {config.obs_package}`)
- `core/calibs.py` — calibration pipeline setup
- `core/science.py` — science processing setup
- `core/bootstrap.py` — repository initialization

---

## Section 5: Testing Strategy

**Approach:** Run existing 38+ test suite after each rename/cleanup step.

**Validation sequence:**
1. After package rename → all tests pass with new import paths
2. After CLI rename → `stt --help` works, old `nickel` entry point removed
3. After Config cleanup → tests construct Config via `obs_package` field
4. After .env removal → tests updated from `Config.from_env()` to `Config.from_yaml()` or `Config.from_env_vars()`
5. Final: dry-run one pipeline YAML to confirm end-to-end orchestration

**No pipeline re-runs needed** — all 7 pipelines validated the current code. Phase 2B is a rename/cleanup refactor that doesn't change pipeline logic.

---

## Out of Scope

- Phase 3 (new telescope integration) — sequential after Phase 2B
- New test files — existing suite covers all affected code paths
- YAML pipeline config changes beyond updating the `instrument:` field (already done in Phase 2)
- obs_smalltel LSST package changes (Phase 1, already complete)
