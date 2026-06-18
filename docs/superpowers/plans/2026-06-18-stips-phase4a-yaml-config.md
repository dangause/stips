# STIPS Phase 4a — YAML-only Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a single YAML config file (`stips -c <config.yaml>`) the *sole* source of configuration, removing `.env` files, the `-p profile` mechanism, `--env-file`, and all `os.environ` fallback for config values.

**Architecture:** A top-level Click group option `-c/--config <yaml>` puts the config path on the context. `config.load()` is rewritten to read **only** the YAML's `env:` block (build `Config`, validate required keys, no `.env`, no `os.environ`). Every command resolves config via one helper that reads that path (clear error if absent). The same `-c` file's non-`env:` sections continue to be parsed independently by `run.py`/`RunConfig` (pipeline spec) — `-c` is one file with two independent consumers.

**Tech Stack:** Python 3.12, Click CLI, pyyaml, pytest, ruff+black.

**Scope:** Phase 4a of `docs/superpowers/specs/2026-06-18-stips-config-archive-naming-design.md` (Part A only). Parts B (archive via `fetch_data`) and C (de-nickel/rename) are SEPARATE plans after this. **Do not** rename `OBS_NICKEL`/`config.obs_nickel` here — that's Part C; Part A keeps the existing config keys (`REPO`, `STACK_DIR`, `OBS_NICKEL`, `RAW_PARENT_DIR`) and just changes *where they come from* (YAML, not .env).

**Branch/worktree:** `/Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1` on `feature/stips-framework`. `cd` there. The worktree `.venv` has stips + obs packages editable-installed; run stack-free tests with `.venv/bin/python -m pytest`.

**Verification note:** Config/CLI tests are stack-free (`config.py` + click). The full suite under the stack is the integration gate; run it at the end (recipe at the bottom).

---

## Current state (verified — file:line are pre-change)

- `config.py:223 load(env_file=None, extra_env=None, inline_env=None, prefer_inline=False)` — reads `os.environ` (the `env_keys` list at `:259`) as base, layers a `.env`/`$ENV_FILE` file (`:277-278`) parsed by `_parse_env_file` (`:195`) with `${VAR}` expansion (`_expand_env_vars`, `:175`), then `extra_env`, then `inline_env` per `prefer_inline`. Required keys at `:305` = `["REPO","STACK_DIR","OBS_NICKEL","RAW_PARENT_DIR"]`.
- `cli.py:72` group `cli(...)` has options `--env-file` and `-p/--profile`; `_resolve_env_file` (`:43`) maps a profile to `.env.<profile>`; the group stores `ctx.obj["env_file"]`/`["profile"]` (`:124-125`).
- `cli.py:128 _load_config(ctx, inline_env=None, prefer_inline=False)` calls `cfg_module.load(env_file=ctx.obj.get("env_file"), inline_env=…, prefer_inline=…)`.
- `cli.py:150 _load_lightcurve_config(...)` — loads from `.env`, else auto-detects STACK_DIR/OBS_NICKEL/RAW_PARENT_DIR from `os.environ` + cwd-walking, builds `Config(...)` directly.
- **Per-step commands using `_load_config(ctx)` (env-only, no YAML today):** `env` (269), `calibs` (336), `science` (415), `dia` (490), `ps1-template`, `fphot`, `bps submit/status/cancel/list`, `dashboard`.
- **Commands that already extract a YAML `env:` block + take a positional `config_file`:** `download` (537/580/615), `bootstrap` (723/756/776), `clean` (823/872/887), `calib-metrics`, `landolt-validate`, and `run`. They call `run_module.get_env_from_yaml(path)` (`run.py:555`) and `_load_config(ctx, inline_env=…, prefer_inline=True)`.
- **Option-name COLLISIONS with a group-level `-c/--config`:** `science` has a command option `--config` → dest `science_config` ("Override calibrateImage config") at `cli.py:371-376`; `ps1-template` has `-c/--collection` at `cli.py:963`. These must be disambiguated (Task 2).

---

## File structure (end state)

```
packages/stips/src/stips/core/config.py   # load() → YAML-only; delete _parse_env_file/_resolve_env_file/_expand_env_vars/ENV_FILE/extra_env/prefer_inline
packages/stips/src/stips/cli.py           # group gains -c/--config (drops -p/--env-file); _load_config reads YAML; collisions renamed; 6 YAML-commands simplified; _load_lightcurve_config rewritten
packages/stips/src/stips/core/run.py      # callers of config.load() updated to the new signature (it already has the env dict via get_env_from_yaml)
packages/stips/tests/test_config_yaml.py  # NEW: load() from a YAML fixture; missing-key + missing-config errors
packages/stips/tests/test_run_config.py   # updated if it constructs/loads config
scripts/config/2023ixf/*.yaml, 2020wnt/*.yaml  # already have env: blocks — keep (used via -c); no key rename in 4a
```

---

## Task 1: `config.load()` → YAML-only

**Files:** `core/config.py`; `tests/test_config_yaml.py` (new).

- [ ] **Step 1: Write the failing test** (`tests/test_config_yaml.py`):
```python
import textwrap, unittest
from pathlib import Path
import tempfile
from stips.core import config as cfg

def _write_yaml(body: str) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "config.yaml"
    p.write_text(textwrap.dedent(body))
    return p

ENVBLOCK = """
    env:
      REPO: /tmp/repo
      STACK_DIR: /tmp/stack
      OBS_NICKEL: /tmp/obs_nickel
      RAW_PARENT_DIR: /tmp/raw
    object: demo
    """

class TestYamlConfig(unittest.TestCase):
    def test_load_from_yaml_path(self):
        p = _write_yaml(ENVBLOCK)
        c = cfg.load(p)
        self.assertEqual(str(c.repo), "/tmp/repo")
        self.assertEqual(str(c.stack_dir), "/tmp/stack")
        self.assertEqual(str(c.raw_parent_dir), "/tmp/raw")

    def test_load_from_env_dict(self):
        c = cfg.load(env={"REPO": "/r", "STACK_DIR": "/s", "OBS_NICKEL": "/o", "RAW_PARENT_DIR": "/raw"})
        self.assertEqual(str(c.repo), "/r")

    def test_missing_required_key_errors(self):
        p = _write_yaml("env:\n  REPO: /tmp/repo\n")
        with self.assertRaises(ValueError) as ctx:
            cfg.load(p)
        self.assertIn("STACK_DIR", str(ctx.exception))  # names the missing key(s)

    def test_no_config_errors(self):
        with self.assertRaises(ValueError):
            cfg.load()  # neither path nor env

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run → FAIL** (`load()` has the old signature). `.venv/bin/python -m pytest packages/stips/tests/test_config_yaml.py -v`

- [ ] **Step 3: Rewrite `load()`** to the YAML-only signature:
```python
def load(config_path: Path | str | None = None, *, env: dict[str, str] | None = None) -> Config:
    """Build Config from a YAML config file's `env:` block (the SOLE config source).
    Pass either config_path (a YAML file) or an already-extracted env dict. No .env, no os.environ."""
    if env is None:
        if config_path is None:
            raise ValueError("No config provided. Pass -c <config.yaml> (its env: block supplies "
                             "REPO, STACK_DIR, OBS_NICKEL, RAW_PARENT_DIR).")
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        env = data.get("env") or {}
        if not isinstance(env, dict):
            raise ValueError(f"{config_path}: 'env:' must be a mapping")
        env = {str(k): str(v) for k, v in env.items()}
    # expand ${VAR} within the env block only (no os.environ)
    merged = {k: _expand_within(v, env) for k, v in env.items()}
    required = ["REPO", "STACK_DIR", "OBS_NICKEL", "RAW_PARENT_DIR"]
    missing = [k for k in required if not merged.get(k)]
    if missing:
        raise ValueError(f"Missing required config key(s): {', '.join(missing)} "
                         f"(set them in the config YAML's env: block)")
    # ... build and return Config from merged exactly as before (repo/stack_dir/obs_nickel/raw_parent_dir,
    #     optional refcat/cp_pipe/lick_*; cp_pipe auto-discovery; instrument_package default; profile load) ...
```
Keep the existing post-merge body (Path conversions, cp_pipe auto-discovery, `INSTRUMENT_PACKAGE`/profile loading, `lick_*` optional fields — Parts B/C remove those later). Add a small `_expand_within(value, env)` that expands `${VAR}` using ONLY the `env` dict (port the no-os.environ subset of `_expand_env_vars`). Do NOT yet delete `_parse_env_file`/`_resolve_env_file`/the old helpers (Task 5 removes dead code once cli.py is migrated) — but the NEW `load()` no longer uses them.

- [ ] **Step 4: Update internal `load()` callers** so nothing imports the removed params. `grep -rn "cfg_module.load(\|config.load(\|\.load(env_file" packages/stips/src/stips` — update `run.py` (it has the YAML env via `get_env_from_yaml`; change to `config.load(env=yaml_env)` or `config.load(config_path)`). Leave `cli.py`'s `_load_config` for Task 2 (it'll temporarily be broken until Task 2 — so do Task 1 and Task 2 in immediate succession; if you must keep green between them, have `_load_config` call `cfg_module.load(config_path=ctx.obj.get("config_path"))` already in this task by adding the group option early — but cleanest is to land T1+T2 together).

- [ ] **Step 5: Run the new test → PASS.** `.venv/bin/python -m pytest packages/stips/tests/test_config_yaml.py -v`

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat(stips): config.load() reads config from a YAML env: block (YAML-only)"`

---

## Task 2: CLI group `-c/--config`; rewrite `_load_config`; drop `-p`/`--env-file`; resolve option collisions

**Files:** `cli.py`.

- [ ] **Step 1: Add the group option, remove the old ones.** In the `cli` group: remove `--env-file` and `-p/--profile`; add:
```python
@click.option("-c", "--config", "config_path",
              type=click.Path(exists=True, path_type=Path),
              help="YAML config file (its env: block supplies REPO/STACK_DIR/OBS_NICKEL/RAW_PARENT_DIR)")
```
In `cli(...)`: drop the `env_file`/`profile` params + the "Cannot use both" check + `_resolve_env_file` call; store `ctx.obj["config_path"] = config_path`. Update the group docstring examples (`-p 2023ixf` → `-c scripts/config/2023ixf/pipeline_ps1_template.yaml`).

- [ ] **Step 2: Rewrite `_load_config(ctx)`** to YAML-only:
```python
def _load_config(ctx) -> cfg_module.Config:
    config_path = ctx.obj.get("config_path")
    if not config_path:
        _print_error("No config provided. Pass -c <config.yaml> before the command, e.g. "
                     "stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml calibs 20230519")
        sys.exit(1)
    try:
        return cfg_module.load(config_path)
    except ValueError as e:
        _print_error(str(e)); sys.exit(1)
```
Remove the `inline_env`/`prefer_inline` params from `_load_config` (the YAML is now the group `-c`; no command passes inline_env anymore — Task 3 simplifies the callers).

- [ ] **Step 3: Resolve the option-name collisions.**
  - `science`: rename its command option `--config` → **`--calibrate-config`** (keep dest `science_config`, keep the help "Override calibrateImage config").
  - `ps1-template`: change its `-c/--collection` to just **`--collection`** (drop the `-c` short, which now belongs to the group). Update any usage/help.
  - Grep to be sure nothing else has a command-level `-c`/`--config`: `grep -n '"--config"\|"-c"' packages/stips/src/stips/cli.py`.

- [ ] **Step 4: Run the CLI smoke + suite.** `.venv/bin/stips --help | head` (group shows `-c/--config`, not `-p`); `.venv/bin/python -m pytest packages/stips/tests/test_config_yaml.py packages/stips/tests/test_run_config.py -v`. (Some command tests may need the YAML path — update in Task 6.) Fix import/usage breaks. Do NOT commit until the per-step commands compile (`.venv/bin/python -c "import stips.cli"`).

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(stips): group -c/--config replaces -p/.env; _load_config reads the YAML; rename colliding command options"`

---

## Task 3: Simplify the 6 already-YAML commands (one `-c`, no positional / inline extraction)

**Files:** `cli.py` (`download`, `bootstrap`, `clean`, `calib-metrics`, `landolt-validate`, `run`).

- [ ] **Step 1:** For `bootstrap`, `clean`, `calib-metrics`, `landolt-validate`, `run`: **remove the positional `config_file` argument** and the per-command `get_env_from_yaml`/`inline_env`/`prefer_inline` block. They now get config via `config = _load_config(ctx)` (the group `-c`). The non-`env:` pipeline sections they need (e.g. `run`'s `object`/`science`/`template`, `clean`'s patterns) are still read from the **same** `-c` file: pass `ctx.obj["config_path"]` to the code that parses those sections (e.g. `run.py`/`RunConfig.from_yaml(config_path)`). So replace "positional config_file" with "the group config_path" everywhere those sections are consumed.

- [ ] **Step 2:** `download` (`cli.py:537-619`) is the messiest — it has a nights-from-YAML path + a config path. Simplify: config via `_load_config(ctx)` (group `-c`); the nights come from the CLI `night` arg(s) and/or the `-c` YAML's `science:`/`template:` sections (read via the same config_path). Keep the actual fetch call as-is for now (Part B rewires it through `profile.fetch_data`; 4a only changes config delivery). Ensure `download` errors clearly if no `-c` and no night.

- [ ] **Step 3:** Update these commands' docstring examples (`stips --env-file .env.X bootstrap` etc.) → `stips -c <config.yaml> bootstrap`.

- [ ] **Step 4:** Run: `.venv/bin/python -c "import stips.cli"` + `.venv/bin/python -m pytest packages/stips/tests/test_run_config.py -v`. Confirm `run`/`bootstrap`/`clean` still parse a self-contained YAML via `-c`.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "refactor(stips): YAML commands use group -c (drop positional config_file + inline extraction)"`

---

## Task 4: Rewrite `_load_lightcurve_config`

**Files:** `cli.py` (`_load_lightcurve_config`, the `lightcurve` command).

- [ ] **Step 1:** Replace `_load_lightcurve_config` (`cli.py:150-256`). New behavior (per spec §4.3):
  - If `ctx.obj.get("config_path")`: `config = cfg_module.load(config_path)`; then apply explicit `--repo`/`--stack-dir` overrides if passed (`dataclasses.replace`).
  - Else: require `--repo` (error if absent: "lightcurve needs -c <config.yaml> or --repo"); resolve `--stack-dir` from the flag or error — **no** `os.environ`/cwd auto-detection. Build a minimal `Config` from `--repo`/`--stack-dir` (+ the profile from `INSTRUMENT_PACKAGE` default).
  - Delete the entire `os.environ`/cwd-walking auto-detect block.
- [ ] **Step 2:** Ensure the `lightcurve` command takes the group `-c` (it does, via the group) and keeps its `--repo`/`--stack-dir` flags.
- [ ] **Step 3:** Run: `.venv/bin/python -c "import stips.cli"`; `.venv/bin/stips lightcurve --help` resolves. Add a small test if feasible (lightcurve config from a YAML fixture).
- [ ] **Step 4: Commit.** `git add -A && git commit -m "refactor(stips): lightcurve config via -c or explicit --repo/--stack-dir (no .env/os.environ auto-detect)"`

---

## Task 5: Delete the dead `.env` machinery

**Files:** `config.py`, `cli.py`; tracked `.env*` if any.

- [ ] **Step 1:** Remove from `config.py`: `_parse_env_file`, `_resolve_env_file` (if it lived here — it's in cli.py), `_expand_env_vars` (replaced by the env-only `_expand_within`), the `extra_env`/`inline_env`/`prefer_inline`/`env_file` params and the `ENV_FILE`/`os.environ` base-population from `load()` (confirm `load()` no longer references `os.environ` for config keys). Remove `cli.py`'s `_resolve_env_file`.
- [ ] **Step 2:** `grep -rn "_parse_env_file\|_resolve_env_file\|_expand_env_vars\|prefer_inline\|inline_env\|env_file\|ENV_FILE\|\.env\b" packages/stips/src/stips` → only legitimate remnants (e.g. a docstring) remain; no dead code/params.
- [ ] **Step 3:** Delete any TRACKED `.env*` files (`git ls-files | grep -E '(^|/)\.env'` — the real `.env*` are user-local/gitignored; only remove tracked ones, e.g. a committed `.env.example`). Leave `packages/lick_searchable_archive`'s own `.env*` alone if unrelated.
- [ ] **Step 4:** Run the stack-free suite: `.venv/bin/python -m pytest packages/stips/tests -v 2>&1 | tail -20` (pre-existing scipy/astroquery skips OK). `uvx ruff check packages/stips`.
- [ ] **Step 5: Commit.** `git add -A && git commit -m "refactor(stips): remove dead .env machinery (parse/resolve/expand/ENV_FILE/prefer_inline)"`

---

## Task 6: Update tests, canonical YAMLs, docstrings; full-suite gate

**Files:** `tests/*`, `scripts/config/2023ixf/*.yaml`, `scripts/config/2020wnt/*.yaml`, cli/docstrings.

- [ ] **Step 1:** Update tests that loaded config via `.env`/the old `load()` signature (e.g. `test_run_config.py`, any test calling `cfg_module.load(env_file=…)`) to the YAML path (`load(config_path)` / `load(env=…)`). `grep -rn "load(env_file\|\.env\b\|inline_env\|prefer_inline\|--profile\|env_file" packages/stips/tests` and fix each.
- [ ] **Step 2:** Confirm the canonical per-target YAMLs (`scripts/config/2023ixf/pipeline_ps1_template.yaml`, `2020wnt/...`) have complete `env:` blocks (REPO/STACK_DIR/OBS_NICKEL/RAW_PARENT_DIR) so `stips -c <them>` works. (They already do; just verify.)
- [ ] **Step 3:** De-`.env` the CLI help/docstrings (group + commands): every `-p <profile>` / `--env-file` / `.env` mention → `-c <config.yaml>`. Update `README.md`'s config/usage sections (the `nickel -p` → `stips -c` examples) and the local gitignored `CLAUDE.md` config section.
- [ ] **Step 4: Full suite under the stack:**
```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.claude/worktrees/stips-framework-phase1
source /Users/dangause/Developer/lick/lsst/lsst_stack/loadLSST.zsh; setup lsst_distrib
setup -r packages/obs_nickel obs_nickel 2>/dev/null || true; setup -r packages/obs_stips obs_stips 2>/dev/null || true
export OBS_NICKEL="$PWD/packages/obs_nickel"; export PYTHONPATH="$PWD/packages/stips/src:$PWD/packages/obs_stips/python:$PYTHONPATH"
python -m pytest packages/stips/tests packages/obs_stips/tests packages/obs_nickel/tests -q
uvx ruff check packages/stips
```
Expect green (pre-existing scipy/astroquery skips aside).
- [ ] **Step 5: Smoke** the new config path end-to-end (dry-run, no real run): `.venv/bin/stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml env` prints the resolved config from the YAML; `.venv/bin/stips env` (no `-c`) errors with the actionable message.
- [ ] **Step 6: Commit.** `git add -A && git commit -m "test/docs(stips): migrate tests + help to -c YAML config"`

---

## Done criteria (Phase 4a)

- [ ] `stips -c <config.yaml> <command>` is the only config path; `.env`, `-p/--profile`, `--env-file`, `ENV_FILE`, and `os.environ` config fallback are gone.
- [ ] No `-c` → clear actionable error; missing required key → names the key.
- [ ] One `-c` file serves both config (`env:`) and the pipeline spec (`run.py` non-`env:` sections); no positional config-file args; no double extraction.
- [ ] `science --config`→`--calibrate-config`, `ps1-template -c` dropped (no group/command `-c` collision).
- [ ] `lightcurve` uses `-c` or explicit `--repo/--stack-dir`; no auto-detect.
- [ ] Full suite green; ruff clean. Config keys unchanged (`OBS_NICKEL` etc. — renamed in Part C, not here).
