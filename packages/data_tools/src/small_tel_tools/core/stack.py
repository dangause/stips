"""LSST stack activation and command execution."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from small_tel_tools.core.config import Config


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
    loader = _find_stack_loader(config.stack_dir)

    # Build the wrapper script
    # We need to source the stack, setup packages, then run the command
    # Quote arguments that contain spaces or special shell characters
    import shlex

    cmd_str = " ".join(shlex.quote(c) for c in cmd)

    # Build environment exports from config
    # These override any .env file sourcing in scripts
    env_exports = f"""
export REPO="{config.repo}"
export STACK_DIR="{config.stack_dir}"
export OBS_SMALLTEL="{config.obs_package}"
export RAW_PARENT_DIR="{config.raw_parent_dir}"
"""
    if config.cp_pipe_dir:
        env_exports += f'export CP_PIPE_DIR="{config.cp_pipe_dir}"\n'
    if config.refcat_repo:
        env_exports += f'export REFCAT_REPO="{config.refcat_repo}"\n'

    # Pass through RUN_ID so shell scripts log to the same directory
    run_id = os.environ.get("RUN_ID")
    if run_id:
        env_exports += f'export RUN_ID="{run_id}"\n'

    # Path to data_tools package (this package)
    data_tools_src = config.obs_package.parent / "data_tools" / "src"

    script = f"""
set -e
{env_exports}
cd "{config.stack_dir}"
source "{loader}"
setup lsst_distrib
setup -r "{config.obs_package}" obs_smalltel 2>/dev/null || true

# Check for obs_smalltel_data
OBS_SMALLTEL_DATA="{config.obs_package.parent / 'obs_smalltel_data'}"
if [ -d "$OBS_SMALLTEL_DATA" ]; then
    setup -r "$OBS_SMALLTEL_DATA" obs_smalltel_data 2>/dev/null || true
fi

# Add data_tools to PYTHONPATH so small_tel_tools is importable
DATA_TOOLS_SRC="{data_tools_src}"
if [ -d "$DATA_TOOLS_SRC" ]; then
    export PYTHONPATH="${{DATA_TOOLS_SRC}}:${{PYTHONPATH:-}}"
fi

# Ensure we use the conda python by putting CONDA_PREFIX/bin first in PATH
# This overrides any local .venv or shell aliases
if [ -n "$CONDA_PREFIX" ]; then
    export PATH="${{CONDA_PREFIX}}/bin:${{PATH}}"
fi

{cmd_str}
"""

    return subprocess.run(
        ["bash", "-c", script],
        capture_output=capture_output,
        check=check,
        cwd=cwd or config.stack_dir,
        text=True,
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


_log = logging.getLogger(__name__)


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
    except Exception as e:
        _log.debug(f"run_butler_python failed: {e}")
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
    return None
