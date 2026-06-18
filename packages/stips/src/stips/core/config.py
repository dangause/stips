"""Configuration loading and validation for Nickel pipelines."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stips.profile import InstrumentProfile


def load_profile(instrument_package: str):
    """Import the active instrument's profile (stack-free import path).

    Args:
        instrument_package: Importable package providing a ``.profile`` module
            exposing a ``profile`` object (e.g. ``"lsst.obs.nickel"``).

    Returns:
        The instrument's ``InstrumentProfile`` object.

    Raises:
        ModuleNotFoundError: If the instrument package (or its ``profile``
            module) is not installed/importable.
        AttributeError: If the ``profile`` module is importable but does not
            expose a ``profile`` attribute.
        ImportError: If a transitive import inside the profile module fails.
    """
    import importlib

    return importlib.import_module(f"{instrument_package}.profile").profile


def _discover_cp_pipe_dir(stack_dir: Path) -> Path | None:
    """Auto-discover CP_PIPE_DIR from the LSST stack.

    Queries the stack's eups to find the cp_pipe package location.

    Args:
        stack_dir: Path to LSST stack installation

    Returns:
        Path to cp_pipe, or None if not found
    """
    # Find the loader script
    loader = None
    for name in ["loadLSST.zsh", "loadLSST.bash", "loadLSST.sh"]:
        candidate = stack_dir / name
        if candidate.exists():
            loader = candidate
            break

    if not loader:
        return None

    # Query eups for cp_pipe location
    script = f"""
source "{loader}" 2>/dev/null
setup lsst_distrib 2>/dev/null
eups list -d cp_pipe 2>/dev/null | head -1 | awk '{{print $1}}'
"""
    try:
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            path = Path(result.stdout.strip())
            if path.exists():
                return path
    except (subprocess.TimeoutExpired, Exception):
        pass

    return None


@dataclass
class Config:
    """Pipeline configuration loaded from environment/.env files.

    Attributes:
        repo: Path to Butler repository
        stack_dir: Path to LSST stack installation
        obs_nickel: Path to obs_nickel package
        raw_parent_dir: Parent directory for raw data
        refcat_repo: Path to reference catalog repository
        cp_pipe_dir: Path to cp_pipe pipelines
        lick_archive_dir: Path to lick_searchable_archive (optional)
        lick_archive_url: Lick archive API URL
        lick_archive_instr: Instrument filter for archive queries
        profile: Active instrument's InstrumentProfile (None if obs package
            not importable; use require_profile() for an actionable error)
        instrument_package: Importable package the profile is loaded from
    """

    repo: Path
    stack_dir: Path
    obs_nickel: Path
    raw_parent_dir: Path
    refcat_repo: Path | None = None
    cp_pipe_dir: Path | None = None
    lick_archive_dir: Path | None = None
    lick_archive_url: str = "https://archive.ucolick.org/archive"
    lick_archive_instr: str = "NICKEL_DIR"

    # Active instrument's InstrumentProfile (loaded from INSTRUMENT_PACKAGE).
    # May be None if the obs package is not importable; commands that need it
    # should call require_profile() to surface an actionable error.
    profile: "InstrumentProfile | None" = None
    # Importable package the profile was (or would be) loaded from.
    instrument_package: str = "lsst.obs.nickel"

    # Derived paths (set in __post_init__)
    pipelines_dir: Path = field(init=False)
    configs_dir: Path = field(init=False)

    def __post_init__(self):
        self.pipelines_dir = self.obs_nickel / "pipelines"
        self.configs_dir = self.obs_nickel / "configs"

    def require_profile(self) -> "InstrumentProfile":
        """Return the active instrument profile, or raise an actionable error.

        Use this from commands that genuinely need the profile. If the obs
        package was not importable at config-load time, ``profile`` is None and
        this surfaces a clear, fixable error instead of an opaque AttributeError.
        """
        if self.profile is None:
            raise RuntimeError(
                f"instrument package {self.instrument_package!r} not importable; "
                f"pip install it and set INSTRUMENT_PACKAGE."
            )
        return self.profile

    def validate(self) -> list[str]:
        """Check that required paths exist.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        if not self.repo.exists():
            errors.append(f"REPO does not exist: {self.repo}")
        if not self.stack_dir.exists():
            errors.append(f"STACK_DIR does not exist: {self.stack_dir}")
        if not self.obs_nickel.exists():
            errors.append(f"OBS_NICKEL does not exist: {self.obs_nickel}")
        if not self.raw_parent_dir.exists():
            errors.append(f"RAW_PARENT_DIR does not exist: {self.raw_parent_dir}")
        if self.cp_pipe_dir and not self.cp_pipe_dir.exists():
            errors.append(f"CP_PIPE_DIR does not exist: {self.cp_pipe_dir}")
        return errors


def _expand_env_vars(value: str, local_env: dict[str, str] | None = None) -> str:
    """Expand ${VAR} references in a string.

    Args:
        value: String potentially containing ${VAR} references
        local_env: Local environment dict to check first

    Returns:
        String with all ${VAR} references expanded
    """
    local_env = local_env or {}
    while "${" in value:
        start = value.index("${")
        end = value.index("}", start)
        var_name = value[start + 2 : end]
        var_value = local_env.get(var_name, os.environ.get(var_name, ""))
        value = value[:start] + var_value + value[end + 1 :]
    return value


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict."""
    env = {}
    if not path.exists():
        return env

    with open(path) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Handle KEY=VALUE (with optional quotes)
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                # Expand ${VAR} references
                value = _expand_env_vars(value, env)
                env[key] = value
    return env


def load(
    env_file: str | Path | None = None,
    extra_env: list[str | Path] | None = None,
    inline_env: dict[str, str] | None = None,
    prefer_inline: bool = False,
) -> Config:
    """Load configuration from environment and .env files.

    Args:
        env_file: Primary .env file (default: .env or $ENV_FILE)
        extra_env: Additional .env files to layer on top
        inline_env: Dict of environment variables (from YAML 'env' section)
        prefer_inline: If True, inline_env overrides os.environ (for nickel run YAML configs)

    Returns:
        Validated Config object

    Raises:
        ValueError: If required configuration is missing

    Priority (when prefer_inline=False, default):
        1. os.environ (highest)
        2. inline_env
        3. env_file
        4. extra_env (lowest)

    Priority (when prefer_inline=True, for YAML configs):
        1. inline_env (highest - YAML 'env' section)
        2. env_file (if keys not in inline_env)
        3. extra_env
        4. os.environ (lowest - only for keys not in inline_env)
    """
    # Load env files in order (later files override earlier)
    merged: dict[str, str] = {}

    # Start with OS environment as base (will be overridden if prefer_inline=True)
    env_keys = [
        "REPO",
        "STACK_DIR",
        "OBS_NICKEL",
        "RAW_PARENT_DIR",
        "REFCAT_REPO",
        "CP_PIPE_DIR",
        "LICK_ARCHIVE_DIR",
        "LICK_ARCHIVE_URL",
        "LICK_ARCHIVE_INSTR",
        "INSTRUMENT_PACKAGE",
    ]
    for key in env_keys:
        if key in os.environ:
            merged[key] = os.environ[key]

    # Determine primary env file
    if env_file is None and not inline_env:
        env_file = os.environ.get("ENV_FILE", ".env")

    if env_file:
        env_file = Path(env_file)
        if env_file.exists():
            file_env = _parse_env_file(env_file)
            merged.update(file_env)

    if extra_env:
        for extra in extra_env:
            extra_path = Path(extra)
            if extra_path.exists():
                merged.update(_parse_env_file(extra_path))

    # Handle inline_env based on priority mode
    if inline_env:
        if prefer_inline:
            # For YAML configs: inline_env has highest priority
            for k, v in inline_env.items():
                merged[k] = _expand_env_vars(v, inline_env)
        else:
            # For CLI: only use inline_env for keys not in os.environ
            for k, v in inline_env.items():
                if k not in os.environ:
                    merged[k] = _expand_env_vars(v, inline_env)

    # Validate required fields
    required = ["REPO", "STACK_DIR", "OBS_NICKEL", "RAW_PARENT_DIR"]
    missing = [k for k in required if not merged.get(k)]
    if missing:
        raise ValueError(
            f"Missing required configuration: {', '.join(missing)}. "
            f"Set these in your .env file or environment."
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

    # Load the active instrument profile. Robustness: if the obs package is not
    # installed in this environment, do NOT crash config loading — leave
    # profile=None. Commands that need it call Config.require_profile() for a
    # clear, actionable error. (INSTRUMENT_PACKAGE is already in env_keys, so
    # it is merged from os.environ above.)
    instrument_package = merged.get("INSTRUMENT_PACKAGE", "lsst.obs.nickel")
    try:
        profile = load_profile(instrument_package)
    except ModuleNotFoundError as e:
        top = instrument_package.split(".")[0]
        # Only treat as "not installed" if the configured package itself is
        # missing — not a broken/missing import *inside* an otherwise-present
        # profile.py (which must surface, not be silenced as "not installed").
        if e.name and (
            e.name == top
            or e.name.startswith(top + ".")
            or e.name == f"{instrument_package}.profile"
        ):
            profile = None
        else:
            raise

    return Config(
        repo=Path(merged["REPO"]).expanduser(),
        stack_dir=stack_dir,
        obs_nickel=Path(merged["OBS_NICKEL"]).expanduser(),
        raw_parent_dir=Path(merged["RAW_PARENT_DIR"]).expanduser(),
        refcat_repo=(
            Path(merged["REFCAT_REPO"]).expanduser()
            if merged.get("REFCAT_REPO")
            else None
        ),
        cp_pipe_dir=cp_pipe_dir,
        lick_archive_dir=(
            Path(merged["LICK_ARCHIVE_DIR"]).expanduser()
            if merged.get("LICK_ARCHIVE_DIR")
            else None
        ),
        lick_archive_url=merged.get(
            "LICK_ARCHIVE_URL", "https://archive.ucolick.org/archive"
        ),
        lick_archive_instr=merged.get("LICK_ARCHIVE_INSTR", "NICKEL_DIR"),
        profile=profile,
        instrument_package=instrument_package,
    )
