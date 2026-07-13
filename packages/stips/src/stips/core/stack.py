"""LSST stack activation and command execution."""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from stips.core.config import resolve_data_package_dir

if TYPE_CHECKING:
    from stips.core.config import Config

_log = logging.getLogger(__name__)


# Location of the framework `packages/` directory, derived from this file's own
# path (an invariant: stack.py lives at packages/stips/src/stips/core/stack.py).
# parents[0]=core, [1]=stips, [2]=src, [3]=stips(pkg), [4]=packages. We use this
# for the framework siblings (obs_stips, stips) and the instrument data package
# instead of instrument_dir.parent, because post-collapse the instrument dir
# moves to instruments/ while these packages stay in packages/.
_PACKAGES_DIR = Path(__file__).resolve().parents[4]


def _find_stack_loader(stack_dir: Path) -> Path:
    """Find the LSST stack loader script."""
    for name in ["loadLSST.zsh", "loadLSST.bash", "loadLSST.sh"]:
        loader = stack_dir / name
        if loader.exists():
            return loader
    raise FileNotFoundError(
        f"No loadLSST script found in {stack_dir}. "
        f"Check that STACK_DIR points to a valid LSST stack installation."
    )


def _build_setup_script(config: Config) -> tuple[str, dict[str, str]]:
    """Build the bash script prefix that activates the LSST stack.

    Returns everything EXCEPT the trailing command: the loader source, the
    config env exports, the data-package setup, and the STIPS framework sibling
    setup. The instrument is declarative (loaded by path from INSTRUMENT_DIR);
    only its data package is derived from the active profile so a fork's data
    package (not just obs_nickel_data) is set up correctly.

    Security (F-018): config paths and env-derived values are NEVER interpolated
    into the script text. Every such value is placed in the returned ``env``
    mapping (injected into the subprocess environment by :func:`run_with_stack`)
    and the script references it as ``"$VAR"``. Double-quoted bash does not
    protect against ``$``/backtick/quote metacharacters, so a path like
    ``/data/$USER/repo`` would silently expand — or a hostile value execute — if
    it were baked into the text. Referencing an environment variable is inert.

    Args:
        config: Pipeline configuration (must have a loaded profile).

    Returns:
        A ``(script, env)`` tuple: the bash script prefix (ending with a
        trailing newline) and the environment values it references. Callers must
        run the script with ``subprocess.run(..., env={**os.environ, **env})``.
    """
    loader = _find_stack_loader(config.stack_dir)

    prof = config.require_profile()
    data_pkg = prof.obs_data_package

    instrument_dir = config.instrument_dir

    # STIPS framework packages live in the framework `packages/` dir, derived
    # from this file's location — independent of where the instrument dir lives.
    obs_stips_dir = _PACKAGES_DIR / "obs_stips"
    stips_defaults = obs_stips_dir / "instrument_defaults"
    stips_src = _PACKAGES_DIR / "stips" / "src"

    # Values injected into the subprocess environment (never into script text).
    # The bash below references these as "$VAR"; the actual values travel via
    # env= so no metacharacter in a path/value can expand or inject.
    script_env: dict[str, str] = {
        "REPO": str(config.repo),
        "STACK_DIR": str(config.stack_dir),
        "INSTRUMENT_DIR": str(instrument_dir),
        "RAW_PARENT_DIR": str(config.raw_parent_dir),
        "STIPS_LOADER": str(loader),
        "OBS_STIPS": str(obs_stips_dir),
        "STIPS_DEFAULTS": str(stips_defaults),
        "STIPS_SRC": str(stips_src),
    }

    # Re-export the config-derived values (their values come from env=, so the
    # export lines are constant text). INSTRUMENT_DIR is the fixed export name
    # pipeline YAMLs reference ($INSTRUMENT_DIR/...); the instrument is
    # declarative (profile.py loaded by path), so there is no per-instrument
    # EUPS product to set up.
    env_exports = (
        'export REPO="$REPO"\n'
        'export STACK_DIR="$STACK_DIR"\n'
        'export INSTRUMENT_DIR="$INSTRUMENT_DIR"\n'
        'export RAW_PARENT_DIR="$RAW_PARENT_DIR"\n'
    )
    if config.cp_pipe_dir:
        script_env["CP_PIPE_DIR"] = str(config.cp_pipe_dir)
        env_exports += 'export CP_PIPE_DIR="$CP_PIPE_DIR"\n'
    if config.refcat_repo:
        script_env["REFCAT_REPO"] = str(config.refcat_repo)
        env_exports += 'export REFCAT_REPO="$REFCAT_REPO"\n'
    # On-chip binning: the camera build (getCamera, run inside the LSST
    # subprocess) reads CCD_BINNING from the environment, so the config's
    # env: value must be exported through to the subprocess shell.
    ccd_binning = (getattr(config, "env", None) or {}).get("CCD_BINNING")
    if ccd_binning:
        script_env["CCD_BINNING"] = str(ccd_binning)
        env_exports += 'export CCD_BINNING="$CCD_BINNING"\n'

    # Profile-derived skymap identity so the (instrument-neutral) bootstrap
    # script registers/chains the skymap under the active instrument's names
    # (e.g. ctio1mRings-v1 / skymaps/ctio1mRings) instead of a hardcoded one.
    skymap_name = getattr(prof, "skymap_name", None)
    skymap_collection = getattr(prof, "skymap_collection", None)
    if skymap_name:
        script_env["SKYMAP_NAME"] = str(skymap_name)
        env_exports += 'export SKYMAP_NAME="$SKYMAP_NAME"\n'
    if skymap_collection:
        script_env["SKYMAP_COLLECTION"] = str(skymap_collection)
        env_exports += 'export SKYMAP_COLLECTION="$SKYMAP_COLLECTION"\n'
    # SkyMap geometry config, resolved instrument-dir-first: a fork that wants its
    # own tract/patch geometry (e.g. its native pixel scale) drops a
    # configs/makeSkyMap.py into its instrument dir; otherwise the framework
    # reference geometry is used. resolve_config always returns a path (the
    # framework default when no override exists).
    script_env["SKYMAP_CFG"] = str(config.resolve_config("makeSkyMap.py"))
    env_exports += 'export SKYMAP_CFG="$SKYMAP_CFG"\n'

    # Profile ps1_band_map as JSON, for in-stack pex_config files
    # (refcats_gaia_ps1*.py). They must NOT import the profile during config
    # exec: pex_config records every module first imported while executing a
    # config and replays those imports when a saved quantum graph is loaded --
    # the path-loaded profile machinery (module name "fetch") is then
    # unimportable and pipetask run dies at graph deserialization.
    ps1_map = getattr(prof, "ps1_band_map", None)
    if isinstance(ps1_map, dict):
        import json as _json

        script_env["STIPS_PS1_BAND_MAP"] = _json.dumps(ps1_map)
        env_exports += 'export STIPS_PS1_BAND_MAP="$STIPS_PS1_BAND_MAP"\n'

    # Pass through RUN_ID so shell scripts log to the same directory. It is
    # already in os.environ (which run_with_stack merges), so only the export
    # line is needed here.
    if os.environ.get("RUN_ID"):
        env_exports += 'export RUN_ID="$RUN_ID"\n'

    # Instrument data package (e.g. obs_nickel_data) — only when the profile
    # declares one AND its directory resolves (explicit package_dir, co-located
    # under the instrument dir, or the reference packages/ layout).
    data_block = ""
    if data_pkg:
        data_dir = resolve_data_package_dir(prof, instrument_dir)
        if data_dir is None:
            _log.debug(
                "profile declares obs_data_package=%r but no directory resolved "
                "(checked package_dir, %s, and %s); skipping data-package setup",
                data_pkg,
                instrument_dir / data_pkg,
                _PACKAGES_DIR / data_pkg,
            )
        else:
            script_env["STIPS_DATA_DIR"] = str(data_dir)
            data_block = f"""
# Check for {data_pkg}
if [ -d "$STIPS_DATA_DIR" ]; then
    setup -r "$STIPS_DATA_DIR" {shlex.quote(data_pkg)} 2>/dev/null || true
fi
"""

    script = f"""
set -e
{env_exports}
cd "$STACK_DIR"
source "$STIPS_LOADER"
setup lsst_distrib
{data_block}
# STIPS framework: obs_stips (LSST glue) + stips (core, src-layout)
if [ -d "$OBS_STIPS" ]; then
    setup -r "$OBS_STIPS" obs_stips 2>/dev/null || true
fi
# Reference pipelines/configs; moved framework YAMLs import siblings via this.
export STIPS_DEFAULTS="$STIPS_DEFAULTS"
if [ -d "$STIPS_SRC" ]; then
    export PYTHONPATH="${{STIPS_SRC}}:${{PYTHONPATH:-}}"
fi

# Ensure we use the conda python by putting CONDA_PREFIX/bin first in PATH
# This overrides any local .venv or shell aliases
if [ -n "$CONDA_PREFIX" ]; then
    export PATH="${{CONDA_PREFIX}}/bin:${{PATH}}"
fi

"""
    return script, script_env


def run_with_stack(
    cmd: list[str],
    config: Config,
    *,
    capture_output: bool = False,
    check: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a command within the LSST stack environment.

    This wraps the command in a bash script that sources the stack
    before executing. This is necessary because the LSST stack uses
    conda/eups which modify the shell environment.

    Args:
        cmd: Command and arguments to run
        config: Pipeline configuration
        capture_output: If True, capture stdout/stderr
        check: If True, raise on non-zero exit
        cwd: Working directory (default: stack_dir)

    Returns:
        CompletedProcess with return code and output

    Raises:
        subprocess.CalledProcessError: If check=True and command fails
    """
    cmd_str = " ".join(shlex.quote(c) for c in cmd)
    setup_script, script_env = _build_setup_script(config)
    script = setup_script + cmd_str + "\n"

    # Config-derived values are injected here (never interpolated into the
    # script text); the script references them as "$VAR". See F-018.
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=capture_output,
        check=check,
        cwd=cwd or config.stack_dir,
        text=True,
        env={**os.environ, **script_env},
    )


def run_pipetask(
    args: list[str],
    config: Config,
    *,
    capture_output: bool = False,
    check: bool = True,
    log_file: Path | None = None,
    log_level: str = "INFO",
) -> subprocess.CompletedProcess:
    """Run pipetask with the given arguments.

    Args:
        args: Arguments to pass to pipetask (e.g., ["qgraph", "-b", repo, ...])
        config: Pipeline configuration
        capture_output: If True, capture stdout/stderr
        check: If True, raise on non-zero exit
        log_file: Optional path to write pipetask log output (appends if exists)
        log_level: Logging level (CRITICAL|ERROR|WARNING|INFO|VERBOSE|DEBUG|TRACE)

    Returns:
        CompletedProcess with return code and output

    Note:
        When using parallel execution (-j > 1), LSST's logging system writes
        log messages with timestamps in --long-log format. While multiple workers
        may write simultaneously, the timestamped entries allow chronological
        reconstruction. For perfectly ordered logs, consider using -j 1 or
        post-processing the log file to sort by timestamp.
    """
    # Build pipetask command with logging options
    pipetask_args = ["pipetask"]

    # Add logging options before the subcommand
    if log_file:
        # Ensure parent directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        pipetask_args.extend(["--log-file", str(log_file)])

        # Disable terminal logging when writing to file to avoid duplicate output
        # and to ensure all log messages go to the file
        pipetask_args.append("--no-log-tty")

    # Set log level (affects LSST default loggers)
    pipetask_args.extend(["--log-level", log_level])

    # Use long format for better readability and to enable timestamp-based sorting
    pipetask_args.append("--long-log")

    # Add the actual command arguments
    pipetask_args.extend(args)

    return run_with_stack(
        pipetask_args,
        config,
        capture_output=capture_output,
        check=check,
    )


def run_butler(
    args: list[str],
    config: Config,
    *,
    capture_output: bool = False,
    check: bool = True,
    log_file: Path | None = None,
    log_level: str = "INFO",
) -> subprocess.CompletedProcess:
    """Run butler with the given arguments.

    For mutation commands (register-instrument, collection-chain, etc.) that
    don't need stdout parsed. Adds LSST logging flags for diagnostics.

    For query commands where stdout needs to be parsed, use run_butler_query()
    instead -- it runs butler without logging flags so stdout is clean.

    Args:
        args: Arguments to pass to butler (e.g., ["register-instrument", repo, ...])
        config: Pipeline configuration
        capture_output: If True, capture stdout/stderr
        check: If True, raise on non-zero exit
        log_file: Optional path to write butler log output (appends if exists)
        log_level: Logging level (CRITICAL|ERROR|WARNING|INFO|VERBOSE|DEBUG|TRACE)

    Returns:
        CompletedProcess with return code and output
    """
    # Build butler command with logging options
    butler_args = ["butler"]

    # Add logging options before the subcommand
    if log_file:
        # Ensure parent directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        butler_args.extend(["--log-file", str(log_file)])

        # Disable terminal logging when writing to file
        butler_args.append("--no-log-tty")

    # Set log level
    butler_args.extend(["--log-level", log_level])

    # Use long format for better readability
    butler_args.append("--long-log")

    # Add the actual command arguments
    butler_args.extend(args)

    return run_with_stack(
        butler_args,
        config,
        capture_output=capture_output,
        check=check,
    )


def run_butler_query(
    args: list[str],
    config: Config,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a butler query command with clean stdout (no logging flags).

    Use this for query-collections, query-datasets, query-data-ids, etc.
    where stdout needs to be parsed. Unlike run_butler(), this does NOT
    add --no-log-tty, --long-log, or --log-level flags, so stdout
    contains only the tabular query output.

    Args:
        args: Arguments to pass to butler (e.g., ["query-collections", repo, ...])
        config: Pipeline configuration
        check: If True, raise on non-zero exit

    Returns:
        CompletedProcess with return code and captured output
    """
    butler_args = ["butler"] + list(args)

    return run_with_stack(
        butler_args,
        config,
        capture_output=True,
        check=check,
    )


def check_stack(config: Config) -> bool:
    """Verify the LSST stack is accessible.

    Args:
        config: Pipeline configuration

    Returns:
        True if stack is working, False otherwise
    """
    try:
        result = run_with_stack(
            ["python", "-c", "import lsst.daf.butler; print('ok')"],
            config,
            capture_output=True,
            check=True,
        )
        return "ok" in result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def run_butler_python(
    script: str,
    config: Config,
) -> str | None:
    """Run a Python script in the LSST stack environment and return its stdout.

    The script should print its result to stdout (preferably as JSON).
    Lines from LSST stack setup chatter are filtered out.

    Args:
        script: Python script body to execute
        config: Pipeline configuration

    Returns:
        Stripped stdout from the script, or None if execution failed.
    """
    try:
        result = run_with_stack(
            ["python", "-c", script],
            config,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        if len(stderr) > 2000:
            stderr = "…" + stderr[-2000:]
        _log.warning(
            "run_butler_python: in-stack script exited %s; stderr: %s",
            e.returncode,
            stderr or "<empty>",
        )
        return None
    except Exception as e:
        # Spawn/setup failure (e.g. missing bash or loader). Still return None
        # for callers, but make the cause visible.
        _log.warning(
            "run_butler_python: unexpected failure: %s: %s", type(e).__name__, e
        )
        return None

    # Return stripped stdout (may contain setup chatter before the real output)
    return result.stdout.strip() if result.stdout else None


def run_butler_python_json(
    script: str,
    config: Config,
) -> Any:
    """Run a Python script in the LSST stack environment and parse JSON output.

    Like run_butler_python() but automatically finds and parses the last
    JSON line from the output, skipping any LSST stack setup chatter.

    Args:
        script: Python script body that prints a JSON line to stdout
        config: Pipeline configuration

    Returns:
        Parsed JSON result, or None if no JSON found or execution failed.
    """
    output = run_butler_python(script, config)
    if not output:
        return None

    # Find the JSON line (could be a list or dict) — scan from end
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith(("[", "{")):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    # The script ran and printed output, but no parseable JSON line was found.
    # Surface a snippet so the operator can see what was printed instead.
    snippet = output.strip()
    if len(snippet) > 500:
        snippet = "…" + snippet[-500:]
    _log.warning(
        "run_butler_python_json: no JSON line found in in-stack output; "
        "last output was: %s",
        snippet or "<empty>",
    )
    return None


def stack_pipelines_version(config: Config) -> str | None:
    """Return the active LSST *pipelines* version string, or None.

    This is the actual pipelines / EUPS package version (e.g.
    ``"gf03f954c0e+3d14ea8aaf"``) captured from ``lsst.daf.butler.version`` in
    the activated stack — NOT the rubin-env / conda env name (``lsst-scipipe-*``)
    that only identifies the runtime, which two different pipelines releases can
    share. See ``docs/pipeline-brittleness-and-modernization.md``.

    STIPS itself runs in a plain venv and never imports ``lsst.*``, so the value
    is read via a short in-stack snippet (the house pattern; see
    ``core/butler_query.py``). Returns None when the snippet cannot run (e.g. no
    stack configured), so callers can distinguish "unknown" from a real value.
    """
    script = (
        "import json\n"
        "_ver = None\n"
        "try:\n"
        "    import lsst.daf.butler.version as _v\n"
        "    _ver = getattr(_v, '__version__', None)\n"
        "except Exception:\n"
        "    _ver = None\n"
        "if not _ver:\n"
        "    try:\n"
        "        import lsst.daf.butler as _b\n"
        "        _ver = getattr(_b, '__version__', None)\n"
        "    except Exception:\n"
        "        _ver = None\n"
        "print(json.dumps({'version': _ver}))\n"
    )
    result = run_butler_python_json(script, config)
    if isinstance(result, dict):
        version = result.get("version")
        if isinstance(version, str) and version:
            return version
    return None
