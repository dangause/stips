"""Configuration loading and validation for Nickel pipelines."""

from __future__ import annotations

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
        obs_nickel: Path to obs_nickel package (back-compat alias for
            instrument_dir; kept populated during migration)
        instrument_dir: Active instrument package directory containing
            pipelines/ and configs/ (generic; defaults to obs_nickel path)
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
    # Active instrument package directory (contains pipelines/ and configs/).
    # Generic replacement for obs_nickel as the base of pipeline/config path
    # joins. Populated from INSTRUMENT_DIR env if set, else falls back to the
    # obs_nickel path (so Nickel resolves identical paths). field(default=None)
    # keeps it optional for callers that construct Config directly; load()
    # always sets it, and __post_init__ derives it from obs_nickel otherwise.
    instrument_dir: Path | None = None
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
        # instrument_dir is the generic base for pipeline/config path joins.
        # Default to the obs_nickel path when not explicitly provided so Nickel
        # (and any caller that only sets obs_nickel) resolves identical paths.
        if self.instrument_dir is None:
            self.instrument_dir = self.obs_nickel
        self.pipelines_dir = self.instrument_dir / "pipelines"
        self.configs_dir = self.instrument_dir / "configs"

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


def _expand_within(value: str, env: dict[str, str]) -> str:
    """Expand ${VAR} references using ONLY the given env dict (no os.environ).

    Args:
        value: String potentially containing ${VAR} references
        env: The config env block — the sole substitution source

    Returns:
        String with all ${VAR} references expanded; unknown vars expand to "".
    """
    while "${" in value:
        start = value.index("${")
        end = value.index("}", start)
        var_name = value[start + 2 : end]
        var_value = env.get(var_name, "")
        value = value[:start] + var_value + value[end + 1 :]
    return value


def load(
    config_path: Path | str | None = None, *, env: dict[str, str] | None = None
) -> Config:
    """Build Config from a YAML config file's ``env:`` block — the SOLE config source.

    Pass either ``config_path`` (a YAML file with an ``env:`` mapping) or an already-extracted
    ``env`` dict. There is no ``.env`` file and no ``os.environ`` fallback for config values.

    Args:
        config_path: Path to a YAML config file containing an ``env:`` mapping
        env: An already-extracted env dict (alternative to ``config_path``)

    Returns:
        Validated Config object

    Raises:
        ValueError: If no config is provided or required configuration is missing
    """
    if env is None:
        if config_path is None:
            raise ValueError(
                "No config provided. Pass -c <config.yaml> (its env: block supplies "
                "REPO, STACK_DIR, OBS_NICKEL, RAW_PARENT_DIR)."
            )
        import yaml

        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        raw_env = data.get("env") or {}
        if not isinstance(raw_env, dict):
            raise ValueError(f"{config_path}: 'env:' must be a mapping")
        env = {str(k): str(v) for k, v in raw_env.items()}
    else:
        env = {str(k): str(v) for k, v in env.items()}

    # ${VAR} expansion using ONLY the env block (no os.environ)
    merged = {k: _expand_within(v, env) for k, v in env.items()}

    # Validate required fields
    required = ["REPO", "STACK_DIR", "OBS_NICKEL", "RAW_PARENT_DIR"]
    missing = [k for k in required if not merged.get(k)]
    if missing:
        raise ValueError(
            f"Missing required config key(s): {', '.join(missing)} "
            f"(set them in the config YAML's env: block)."
        )

    stack_dir = Path(merged["STACK_DIR"]).expanduser()

    # Resolve CP_PIPE_DIR - use the value from the env block if set, otherwise
    # auto-discover from the stack. The env block is authoritative, so an
    # explicitly-set CP_PIPE_DIR is trusted (no on-disk existence gate).
    cp_pipe_dir: Path | None = None
    if merged.get("CP_PIPE_DIR"):
        cp_pipe_dir = Path(merged["CP_PIPE_DIR"]).expanduser()

    # Auto-discover from stack if not set
    if cp_pipe_dir is None:
        cp_pipe_dir = _discover_cp_pipe_dir(stack_dir)

    # Load the active instrument profile. Robustness: if the obs package is not
    # installed in this environment, do NOT crash config loading — leave
    # profile=None. Commands that need it call Config.require_profile() for a
    # clear, actionable error. (INSTRUMENT_PACKAGE comes from the config YAML's
    # env: block, defaulting to lsst.obs.nickel when unset.)
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

    obs_nickel_path = Path(merged["OBS_NICKEL"]).expanduser()
    # Generic instrument package directory: prefer INSTRUMENT_DIR, else fall
    # back to the obs_nickel path (back-compat — Nickel resolves identical
    # pipeline/config paths when only OBS_NICKEL is set).
    instrument_dir = (
        Path(merged["INSTRUMENT_DIR"]).expanduser()
        if merged.get("INSTRUMENT_DIR")
        else obs_nickel_path
    )

    return Config(
        repo=Path(merged["REPO"]).expanduser(),
        stack_dir=stack_dir,
        obs_nickel=obs_nickel_path,
        instrument_dir=instrument_dir,
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
