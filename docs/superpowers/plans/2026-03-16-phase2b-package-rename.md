# Phase 2B: Package Rename and Config Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `obs_nickel_data_tools` to `small_tel_tools`, rename CLI from `nickel` to `stt`, clean Config to be telescope-agnostic, and remove the `.env` file system.

**Architecture:** Mechanical rename of the Python package directory and all imports (128 occurrences across 24 source files + ~70 in 7 test files), followed by Config dataclass cleanup (remove Lick-specific fields, backward-compat alias, .env parsing). Clean break — no backward compatibility.

**Tech Stack:** Python 3.12+, Click CLI, dataclasses, setuptools, pytest

**Spec:** `docs/superpowers/specs/2026-03-16-phase2b-package-rename-design.md`

---

## Chunk 1: Rename and Cleanup

### Task 1: Rename package directory and update pyproject.toml

**Files:**
- Rename: `packages/data_tools/src/obs_nickel_data_tools/` → `packages/data_tools/src/small_tel_tools/`
- Modify: `packages/data_tools/pyproject.toml`

- [ ] **Step 1: Rename the source directory**

```bash
cd packages/data_tools/src
git mv obs_nickel_data_tools small_tel_tools
```

- [ ] **Step 2: Update pyproject.toml**

Replace the full content of `packages/data_tools/pyproject.toml` with:

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "small-tel-tools"
version = "0.1.0"
description = "Pipeline orchestration and data tools for small telescope astronomy with LSST Science Pipelines."
authors = [{ name = "Dan Gause" }]
requires-python = ">=3.12"
dependencies = [
    "astropy",
    "numpy",
    "pandas",
    "pyyaml>=6.0",
    "rich>=13.0.0",
    "matplotlib>=3.5.0",
    "click>=8.0.0",
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "jinja2>=3.1.0",
    "sse-starlette>=1.8.0",
]
readme = "README.md"

[project.scripts]
# Main CLI
stt = "small_tel_tools.cli:main"

# Archive tools
stt-archive-fetch-night = "small_tel_tools.pipeline_tools.fetch_archive_night:main"
stt-archive-nights = "small_tel_tools.pipeline_tools.generate_nights_list:main"
stt-archive-ingest-ps1 = "small_tel_tools.pipeline_tools.ingest_ps1_template:main"
stt-archive-template-meta = "small_tel_tools.pipeline_tools.template_metadata:main"

# DIA tools
stt-dia-assess = "small_tel_tools.pipeline_tools.assess_dia_quality:main"
stt-dia-lightcurve = "small_tel_tools.pipeline_tools.extract_lightcurve:main"

# Skymap tools
stt-skymap-build-config = "small_tel_tools.skymap.build_discrete_skymap_config:main"
stt-skymap-make = "small_tel_tools.skymap.make_skymap_from_datasets:main"

# EDA tools
stt-eda-archive = "small_tel_tools.eda.archive_query:main"
stt-eda-butler = "small_tel_tools.eda.butler_inspect:main"

[project.entry-points."small_tel_tools.instruments"]
nickel = "small_tel_tools.instruments.nickel:NickelPlugin"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 3: Verify directory renamed and pyproject.toml updated**

```bash
ls packages/data_tools/src/small_tel_tools/__init__.py  # Should exist
grep 'name = "small-tel-tools"' packages/data_tools/pyproject.toml  # Should match
```

- [ ] **Step 4: Commit**

```bash
git add -A packages/data_tools/
git commit -m "refactor: rename obs_nickel_data_tools to small_tel_tools, update pyproject.toml"
```

---

### Task 2: Find-and-replace all `obs_nickel_data_tools` imports in source

**Files:**
- Modify: All 24 `.py` files under `packages/data_tools/src/small_tel_tools/`

- [ ] **Step 1: Replace all `obs_nickel_data_tools` with `small_tel_tools` in source files**

Use `replace_all` on each file that contains the old package name. The occurrences are in import statements, docstrings, and `__all__` declarations. Run this replacement across every `.py` file under `packages/data_tools/src/small_tel_tools/`:

The key files and their occurrence counts:
- `cli.py` (22 occurrences)
- `core/run.py` (24 occurrences)
- `core/science.py` (10 occurrences)
- `core/calibs.py` (7 occurrences)
- `core/dia.py` (6 occurrences)
- `core/fphot.py` (6 occurrences)
- `core/bps.py` (6 occurrences)
- `core/bootstrap.py` (6 occurrences)
- `core/coadd.py` (5 occurrences)
- `core/__init__.py` (7 occurrences)
- `core/clean.py` (4 occurrences)
- `core/executor.py` (3 occurrences)
- `core/ps1_template.py` (3 occurrences)
- `core/lightcurve.py` (2 occurrences)
- `core/stack.py` (2 occurrences — TYPE_CHECKING import)
- `core/pipeline.py` (2 occurrences)
- `core/processing_log.py` (1 occurrence)
- `instruments/__init__.py` (5 occurrences — imports + entry_points group string)
- `instruments/nickel.py` (2 occurrences)
- `pipeline_tools/ingest_ps1_template.py` (1 occurrence)
- `pipeline_tools/fetch_archive_night.py` (1 occurrence)
- `dashboard/__init__.py` (1 occurrence)
- `dashboard/app.py` (1 occurrence)
- `__init__.py` (1 occurrence — docstring)

For each file, use `replace_all=true` to change `obs_nickel_data_tools` → `small_tel_tools`.

- [ ] **Step 2: Update `__init__.py` docstring**

Replace the docstring in `packages/data_tools/src/small_tel_tools/__init__.py`:

```python
"""
Pipeline orchestration and data tools for small telescope astronomy.

Use the stt CLI or import modules from small_tel_tools.
"""

__all__ = ["pipeline_tools", "skymap"]
```

- [ ] **Step 3: Verify no remaining `obs_nickel_data_tools` references in source**

```bash
grep -r "obs_nickel_data_tools" packages/data_tools/src/ | head -20
```

Expected: no output (zero matches).

- [ ] **Step 4: Reinstall package in development mode**

```bash
pip install -e packages/data_tools/
```

- [ ] **Step 5: Verify `stt` CLI works**

```bash
stt --help
```

Expected: Click help output showing `stt` as the command name.

- [ ] **Step 6: Commit**

```bash
git add packages/data_tools/src/
git commit -m "refactor: replace all obs_nickel_data_tools imports with small_tel_tools"
```

---

### Task 3: Update test imports

**Files:**
- Modify: 7 test files under `packages/obs_nickel/tests/` that reference `obs_nickel_data_tools`

- [ ] **Step 1: Replace `obs_nickel_data_tools` with `small_tel_tools` in all test files**

Files to update (with occurrence counts):
- `test_executor.py` (30 occurrences — imports + `patch()` target strings)
- `test_run_config.py` (16 occurrences)
- `test_bps_config.py` (11 occurrences)
- `test_ps1_templates.py` (3 occurrences)
- `test_period.py` (1 occurrence)
- `test_transit.py` (1 occurrence)
- `test_fphot_collection_selection.py` (1 occurrence)

For each file, use `replace_all=true` to change `obs_nickel_data_tools` → `small_tel_tools`.

**Critical:** The `patch()` target strings in `test_executor.py` (e.g., `"obs_nickel_data_tools.core.executor.run_pipetask"`) MUST be updated to `"small_tel_tools.core.executor.run_pipetask"` or the mocks will silently fail to patch.

- [ ] **Step 2: Verify no remaining `obs_nickel_data_tools` references in tests**

```bash
grep -r "obs_nickel_data_tools" packages/obs_nickel/tests/ | head -10
```

Expected: no output.

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest packages/obs_nickel/tests/ -x -q 2>&1 | tail -10
```

Expected: All tests pass (125 collected, some may error due to LSST stack imports, but all `obs_nickel_data_tools`-dependent tests should pass).

- [ ] **Step 4: Commit**

```bash
git add packages/obs_nickel/tests/
git commit -m "refactor: update test imports from obs_nickel_data_tools to small_tel_tools"
```

---

### Task 4: Clean up Config — remove Lick-specific fields and obs_nickel alias

**Files:**
- Modify: `packages/data_tools/src/small_tel_tools/core/config.py`
- Modify: `packages/data_tools/src/small_tel_tools/instruments/nickel.py`
- Modify: `packages/data_tools/src/small_tel_tools/cli.py`

- [ ] **Step 1: Remove Lick-specific fields and obs_nickel alias from Config**

In `packages/data_tools/src/small_tel_tools/core/config.py`:

Remove from the `Config` dataclass:
```python
    lick_archive_dir: Path | None = None
    lick_archive_url: str = "https://archive.ucolick.org/archive"
    lick_archive_instr: str = "NICKEL_DIR"
```

Remove the backward-compat property:
```python
    @property
    def obs_nickel(self) -> Path:
        """Backward-compat alias for obs_package."""
        return self.obs_package
```

Update the docstring to remove Lick-specific field descriptions.

Update the `validate()` method error message from `"OBS_SMALLTEL/OBS_NICKEL does not exist"` to `"OBS_SMALLTEL does not exist"`.

- [ ] **Step 2: Add `archive_dir` to NickelPlugin**

In `packages/data_tools/src/small_tel_tools/instruments/nickel.py`, add the class attribute after the existing archive attributes:

```python
    archive_dir: str | None = None  # Path to lick_searchable_archive client
```

- [ ] **Step 3: Update CLI env command to use plugin for archive info**

In `packages/data_tools/src/small_tel_tools/cli.py`, in the `env` command function:

Replace:
```python
    click.echo(f"{'OBS_NICKEL:':<20} {config.obs_nickel}")
```
With:
```python
    click.echo(f"{'OBS_SMALLTEL:':<20} {config.obs_package}")
```

Replace the Lick archive display block:
```python
    if config.lick_archive_dir:
        click.echo(f"{'LICK_ARCHIVE_DIR:':<20} {config.lick_archive_dir}")
```
With:
```python
    plugin = _get_plugin(ctx)
    if plugin.archive_dir:
        click.echo(f"{'ARCHIVE_DIR:':<20} {plugin.archive_dir}")
```

- [ ] **Step 4: Update CLI download command to use plugin**

In `packages/data_tools/src/small_tel_tools/cli.py`, in the `download` command:

Replace:
```python
        if config.lick_archive_dir:
            sys.argv.extend(["--client-path", str(config.lick_archive_dir)])
```
With:
```python
        plugin = _get_plugin(ctx)
        if plugin.archive_dir:
            sys.argv.extend(["--client-path", str(plugin.archive_dir)])
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest packages/obs_nickel/tests/ -x -q 2>&1 | tail -10
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add packages/data_tools/src/small_tel_tools/core/config.py packages/data_tools/src/small_tel_tools/instruments/nickel.py packages/data_tools/src/small_tel_tools/cli.py
git commit -m "refactor: remove Lick-specific fields from Config, add archive_dir to NickelPlugin"
```

---

### Task 5: Replace all `config.obs_nickel` references with `config.obs_package`

**Files:**
- Modify: 10 files under `packages/data_tools/src/small_tel_tools/` (26 occurrences total)

- [ ] **Step 1: Replace `config.obs_nickel` with `config.obs_package` across all source files**

Use `replace_all=true` on each file. After Task 4, `cli.py` already has its 2 references updated, so 8 files remain:

| File | Occurrences |
|------|-------------|
| `core/run.py` | 6 |
| `core/stack.py` | 4 (see Step 2 for shell template) |
| `core/science.py` | 3 |
| `core/dia.py` | 3 |
| `core/calibs.py` | 2 |
| `core/bootstrap.py` | 2 |
| `core/bps.py` | 2 |
| `core/coadd.py` | 1 |
| `core/fphot.py` | 1 |

For each file, use `replace_all=true` to change `config.obs_nickel` → `config.obs_package`.

- [ ] **Step 2: Update the shell template in `core/stack.py`**

The shell template in `run_with_stack()` has eups-specific strings that need manual updating (not just `config.obs_nickel` → `config.obs_package`):

Replace:
```python
export OBS_NICKEL="{config.obs_nickel}"
```
With:
```python
export OBS_SMALLTEL="{config.obs_package}"
```

Replace:
```python
setup -r "{config.obs_nickel}" obs_nickel 2>/dev/null || true
```
With:
```python
setup -r "{config.obs_package}" obs_smalltel 2>/dev/null || true
```

Replace:
```python
# Check for obs_nickel_data
OBS_NICKEL_DATA="{config.obs_nickel.parent / 'obs_nickel_data'}"
if [ -d "$OBS_NICKEL_DATA" ]; then
    setup -r "$OBS_NICKEL_DATA" obs_nickel_data 2>/dev/null || true
fi
```
With:
```python
# Check for obs_smalltel_data
OBS_SMALLTEL_DATA="{config.obs_package.parent / 'obs_smalltel_data'}"
if [ -d "$OBS_SMALLTEL_DATA" ]; then
    setup -r "$OBS_SMALLTEL_DATA" obs_smalltel_data 2>/dev/null || true
fi
```

Also replace in the same function:
```python
    data_tools_src = config.obs_nickel.parent / "data_tools" / "src"
```
With:
```python
    data_tools_src = config.obs_package.parent / "data_tools" / "src"
```

Remove the `LICK_ARCHIVE_DIR` export block:
```python
    if config.lick_archive_dir:
        env_exports += f'export LICK_ARCHIVE_DIR="{config.lick_archive_dir}"\n'
```

- [ ] **Step 3: Update remaining `OBS_NICKEL` references in cli.py**

In `cli.py`, there are additional `OBS_NICKEL` references that are NOT `config.obs_nickel`:

In `_load_lightcurve_config()`:
- Replace error message `"Set REPO, STACK_DIR, OBS_NICKEL in environment"` → `"Set REPO, STACK_DIR, OBS_SMALLTEL in environment"`
- Replace `os.environ["OBS_NICKEL"]` → `os.environ["OBS_SMALLTEL"]`
- Replace local variable `obs_nickel` → `obs_package` (and its usage `obs_package=obs_nickel` → `obs_package=obs_package`)

In the `run_pipeline` command docstring YAML example:
- Replace `OBS_NICKEL: "/path/to/obs_nickel"` → `OBS_SMALLTEL: "/path/to/obs_smalltel"`

- [ ] **Step 4: Verify no remaining `config.obs_nickel` or `OBS_NICKEL` references**

```bash
grep -r "config\.obs_nickel\b" packages/data_tools/src/ | head -10
grep -r "OBS_NICKEL" packages/data_tools/src/ | head -10
```

Expected: no output for either grep.

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest packages/obs_nickel/tests/ -x -q 2>&1 | tail -10
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add packages/data_tools/src/small_tel_tools/
git commit -m "refactor: replace all config.obs_nickel with config.obs_package, update eups names"
```

---

### Task 6: Simplify `config.load()` — remove .env file support

**Files:**
- Modify: `packages/data_tools/src/small_tel_tools/core/config.py`

- [ ] **Step 1: Remove `_parse_env_file()` function**

Delete the entire `_parse_env_file()` function (lines 135-160 in current file).

- [ ] **Step 2: Simplify `load()` function signature and body**

Replace the entire `load()` function with:

```python
def load(inline_env: dict[str, str] | None = None) -> Config:
    """Load configuration from environment variables or inline YAML env section.

    Args:
        inline_env: Dict of environment variables (from YAML 'env' section).
                    When provided, these override os.environ values.

    Returns:
        Validated Config object

    Raises:
        ValueError: If required configuration is missing
    """
    merged: dict[str, str] = {}

    # Start with OS environment
    env_keys = [
        "REPO",
        "STACK_DIR",
        "OBS_SMALLTEL",
        "RAW_PARENT_DIR",
        "REFCAT_REPO",
        "CP_PIPE_DIR",
    ]
    for key in env_keys:
        if key in os.environ:
            merged[key] = os.environ[key]

    # Inline env (from YAML) overrides os.environ
    if inline_env:
        for k, v in inline_env.items():
            merged[k] = _expand_env_vars(v, inline_env)

    # Validate required fields
    required = ["REPO", "STACK_DIR", "OBS_SMALLTEL", "RAW_PARENT_DIR"]
    missing = [k for k in required if not merged.get(k)]
    if missing:
        raise ValueError(
            f"Missing required configuration: {', '.join(missing)}. "
            f"Set these as environment variables or in your YAML env: section."
        )

    stack_dir = Path(merged["STACK_DIR"]).expanduser()

    # Resolve CP_PIPE_DIR - use provided value if valid, otherwise auto-discover
    cp_pipe_dir: Path | None = None
    if merged.get("CP_PIPE_DIR"):
        candidate = Path(merged["CP_PIPE_DIR"]).expanduser()
        if candidate.exists():
            cp_pipe_dir = candidate

    # Auto-discover from stack if not set or invalid
    if cp_pipe_dir is None:
        cp_pipe_dir = _discover_cp_pipe_dir(stack_dir)

    return Config(
        repo=Path(merged["REPO"]).expanduser(),
        stack_dir=stack_dir,
        obs_package=Path(merged["OBS_SMALLTEL"]).expanduser(),
        raw_parent_dir=Path(merged["RAW_PARENT_DIR"]).expanduser(),
        refcat_repo=(
            Path(merged["REFCAT_REPO"]).expanduser()
            if merged.get("REFCAT_REPO")
            else None
        ),
        cp_pipe_dir=cp_pipe_dir,
    )
```

- [ ] **Step 3: Update Config docstring**

Replace the `Config` class docstring:

```python
    """Pipeline configuration loaded from environment variables or YAML env section.

    Attributes:
        repo: Path to Butler repository
        stack_dir: Path to LSST stack installation
        obs_package: Path to instrument obs package (e.g. obs_smalltel)
        raw_parent_dir: Parent directory for raw data
        refcat_repo: Path to reference catalog repository
        cp_pipe_dir: Path to cp_pipe pipelines
    """
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest packages/obs_nickel/tests/ -x -q 2>&1 | tail -10
```

Expected: All tests pass. Some tests that previously used `config.load(env_file=...)` may need updating in the next task.

- [ ] **Step 5: Commit**

```bash
git add packages/data_tools/src/small_tel_tools/core/config.py
git commit -m "refactor: simplify config.load() — remove .env file support, keep inline_env for YAML"
```

---

### Task 7: Remove CLI profile/env-file options and update callers

**Files:**
- Modify: `packages/data_tools/src/small_tel_tools/cli.py`
- Modify: `packages/data_tools/src/small_tel_tools/core/run.py`
- Delete: `.env.example`

- [ ] **Step 1: Remove `_resolve_env_file()` function from cli.py**

Delete the entire `_resolve_env_file()` function.

- [ ] **Step 2: Remove `--env-file` and `--profile` options from the `cli` group**

Remove these Click option decorators from the `cli` group function:
```python
@click.option(
    "--env-file",
    ...
)
@click.option(
    "--profile",
    "-p",
    ...
)
```

Remove `env_file` and `profile` parameters from the `cli()` function signature.

Remove the body code that handles profile/env-file resolution:
```python
    if env_file and profile:
        _print_error("Cannot use both --env-file and --profile")
        ...
    resolved = _resolve_env_file(env_file, profile)
    ctx.obj["env_file"] = resolved
    ctx.obj["profile"] = profile
```

- [ ] **Step 3: Update `_load_config()` helper to not pass env_file**

Find the helper that loads config and remove `env_file` passing:

Replace any:
```python
    env_file = ctx.obj.get("env_file")
    ...
    config = cfg_module.load(env_file=env_file, ...)
```
With:
```python
    config = cfg_module.load(inline_env=inline_env)
```

Also update `_load_lightcurve_config()` to remove env_file usage.

- [ ] **Step 4: Remove profile display from `env` command**

Remove:
```python
    profile = ctx.obj.get("profile")
    env_file = ctx.obj.get("env_file")
    if profile:
        click.echo(f"\n{'Profile:':<20} {profile}")
    if env_file:
        click.echo(f"{'Env file:':<20} {env_file}")
```

- [ ] **Step 5: Remove profile resolution from `run`, `bps`, `run_pipeline` commands**

In the `run_pipeline`, `bps`, and any other commands that look up `yaml_profile` and call `_resolve_env_file()`:

Remove blocks like:
```python
            cli_profile = ctx.obj.get("profile")
            if not cli_profile:
                yaml_profile = run_module.get_profile_from_yaml(config_file)
                if yaml_profile:
                    resolved = _resolve_env_file(None, yaml_profile)
                    ...
```

The YAML `env:` section already provides all config via `inline_env` — no profile resolution needed.

- [ ] **Step 6: Remove profile support from `core/run.py`**

In `packages/data_tools/src/small_tel_tools/core/run.py`:

- Delete `RunConfig.profile: str | None = None` field from the dataclass
- Delete the `get_profile_from_yaml()` function
- In `RunConfig.from_yaml()`, remove the line `profile=data.get("profile")`
- Remove any YAML example docstrings that show `profile: "2023ixf"`

- [ ] **Step 7: Update help text and docstrings**

Update the `cli` group docstring to remove references to profiles and .env files. Replace with guidance to use environment variables or YAML `env:` section.

- [ ] **Step 8: Delete `.env.example`**

```bash
git rm .env.example
```

- [ ] **Step 9: Run tests**

```bash
.venv/bin/python -m pytest packages/obs_nickel/tests/ -x -q 2>&1 | tail -10
```

Expected: All tests pass.

- [ ] **Step 10: Verify `stt --help` shows no --profile/--env-file**

```bash
stt --help
```

Expected: No `--profile` or `--env-file` options listed.

- [ ] **Step 11: Commit**

```bash
git add packages/data_tools/src/small_tel_tools/cli.py packages/data_tools/src/small_tel_tools/core/run.py
git rm .env.example 2>/dev/null || true
git commit -m "refactor: remove --profile and --env-file CLI options, delete .env.example"
```

---

### Task 8: Update test files that use config.load() with old parameters

**Files:**
- Modify: Test files in `packages/obs_nickel/tests/` that call `config.load()` with removed parameters

- [ ] **Step 1: Find tests using old `config.load()` parameters**

```bash
grep -rn "config\.load\|cfg_module\.load\|from_env\|env_file" packages/obs_nickel/tests/ | head -20
```

Identify tests that pass `env_file=`, `extra_env=`, or `prefer_inline=` and update them to use the new signature: `config.load(inline_env=...)`.

- [ ] **Step 2: Update test calls to use new config.load() signature**

For any test that builds a Config with specific env vars, use:
```python
config = config_module.load(inline_env={
    "REPO": str(tmp_path / "repo"),
    "STACK_DIR": "/opt/lsst",
    "OBS_SMALLTEL": str(tmp_path / "obs_smalltel"),
    "RAW_PARENT_DIR": str(tmp_path / "raw"),
})
```

For tests that reference `OBS_NICKEL`, update to `OBS_SMALLTEL`.

- [ ] **Step 3: Run full test suite**

```bash
.venv/bin/python -m pytest packages/obs_nickel/tests/ -x -q 2>&1 | tail -10
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add packages/obs_nickel/tests/
git commit -m "test: update tests for simplified config.load() signature"
```

---

### Task 9: Final validation — dry-run pipeline

**Files:** None (read-only validation)

- [ ] **Step 1: Verify no `obs_nickel_data_tools` references remain anywhere**

```bash
grep -r "obs_nickel_data_tools" packages/data_tools/ packages/obs_nickel/tests/ | head -20
```

Expected: no output.

- [ ] **Step 2: Verify no `config.obs_nickel` references remain**

```bash
grep -r "config\.obs_nickel\b" packages/data_tools/ | head -10
```

Expected: no output.

- [ ] **Step 3: Verify no `OBS_NICKEL` references in source (except maybe old env var comments)**

```bash
grep -r "OBS_NICKEL" packages/data_tools/src/ | head -10
```

Expected: no output.

- [ ] **Step 4: Run full test suite one final time**

```bash
.venv/bin/python -m pytest packages/obs_nickel/tests/ -x -q 2>&1 | tail -10
```

Expected: All tests pass.

- [ ] **Step 5: Verify `stt` CLI end-to-end**

```bash
stt --help
stt --version 2>/dev/null || true
```

Expected: Help shows `stt` as command name, all subcommands listed.

- [ ] **Step 6: Dry-run a pipeline YAML**

```bash
stt run scripts/config/2023ixf/pipeline_ps1_template.yaml --dry-run
```

Expected: Dry-run output showing pipeline steps without executing them. Confirms YAML loading, config resolution, and plugin system all work end-to-end.
