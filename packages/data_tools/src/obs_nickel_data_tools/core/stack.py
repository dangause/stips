"""LSST stack activation and command execution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config


def _find_stack_loader(stack_dir: Path) -> Path:
    """Find the LSST stack loader script."""
    for name in ["loadLSST.zsh", "loadLSST.bash", "loadLSST.sh"]:
        loader = stack_dir / name
        if loader.exists():
            return loader
    raise FileNotFoundError(f"No loadLSST script found in {stack_dir}")


def build_stack_env(config: Config) -> dict[str, str]:
    """Build environment variables needed for LSST stack commands.

    This sets up PYTHONPATH and other vars needed to run pipetask/butler
    without fully sourcing the stack (which requires bash).

    Args:
        config: Pipeline configuration

    Returns:
        Environment dict with stack paths configured
    """
    env = os.environ.copy()

    # Add obs_nickel to PYTHONPATH
    obs_nickel_python = config.obs_nickel / "python"
    existing_pythonpath = env.get("PYTHONPATH", "")
    if existing_pythonpath:
        env["PYTHONPATH"] = f"{obs_nickel_python}:{existing_pythonpath}"
    else:
        env["PYTHONPATH"] = str(obs_nickel_python)

    # Set standard env vars
    env["REPO"] = str(config.repo)
    env["STACK_DIR"] = str(config.stack_dir)
    env["OBS_NICKEL"] = str(config.obs_nickel)
    env["RAW_PARENT_DIR"] = str(config.raw_parent_dir)

    if config.cp_pipe_dir:
        env["CP_PIPE_DIR"] = str(config.cp_pipe_dir)
    if config.refcat_repo:
        env["REFCAT_REPO"] = str(config.refcat_repo)

    return env


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
export OBS_NICKEL="{config.obs_nickel}"
export RAW_PARENT_DIR="{config.raw_parent_dir}"
"""
    if config.cp_pipe_dir:
        env_exports += f'export CP_PIPE_DIR="{config.cp_pipe_dir}"\n'
    if config.refcat_repo:
        env_exports += f'export REFCAT_REPO="{config.refcat_repo}"\n'
    if config.lick_archive_dir:
        env_exports += f'export LICK_ARCHIVE_DIR="{config.lick_archive_dir}"\n'

    # Path to data_tools package (this package)
    data_tools_src = config.obs_nickel.parent / "data_tools" / "src"

    script = f"""
set -e
{env_exports}
cd "{config.stack_dir}"
source "{loader}"
setup lsst_distrib
setup -r "{config.obs_nickel}" obs_nickel 2>/dev/null || true

# Check for obs_nickel_data
OBS_NICKEL_DATA="{config.obs_nickel.parent / 'obs_nickel_data'}"
if [ -d "$OBS_NICKEL_DATA" ]; then
    setup -r "$OBS_NICKEL_DATA" obs_nickel_data 2>/dev/null || true
fi

# Add data_tools to PYTHONPATH so obs_nickel_data_tools is importable
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
) -> subprocess.CompletedProcess:
    """Run pipetask with the given arguments.

    Args:
        args: Arguments to pass to pipetask (e.g., ["qgraph", "-b", repo, ...])
        config: Pipeline configuration
        capture_output: If True, capture stdout/stderr
        check: If True, raise on non-zero exit

    Returns:
        CompletedProcess with return code and output
    """
    return run_with_stack(
        ["pipetask"] + args,
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
) -> subprocess.CompletedProcess:
    """Run butler with the given arguments.

    Args:
        args: Arguments to pass to butler (e.g., ["query-collections", repo])
        config: Pipeline configuration
        capture_output: If True, capture stdout/stderr
        check: If True, raise on non-zero exit

    Returns:
        CompletedProcess with return code and output
    """
    return run_with_stack(
        ["butler"] + args,
        config,
        capture_output=capture_output,
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
