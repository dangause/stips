"""Configuration loading and validation for Nickel pipelines."""

from __future__ import annotations

import subprocess
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stips.profile import InstrumentProfile


def load_active_profile(instrument_dir: str | Path | None = None):
    """Load the active instrument profile by path from INSTRUMENT_DIR.

    The collapsed framework defines a telescope as instruments/<name>/profile.py
    loaded by path (no importable obs package). Reads INSTRUMENT_DIR from the env
    if not given. APPENDS the instrument dir to sys.path (so co-located hook
    modules like fetch.py resolve) WITHOUT shadowing stdlib/installed modules.

    NOTE: this mirrors lsst.obs.stips.profile_loader.load_profile_from_dir — the
    intentional dual-loader (stips-side here for the CLI/tools; obs_stips-side
    for the stack-import path). Keep the two in sync.
    """
    import importlib.util
    import os
    import sys

    d = instrument_dir or os.environ.get("INSTRUMENT_DIR")
    if not d:
        raise RuntimeError(
            "INSTRUMENT_DIR is not set; it must point at instruments/<name>/ "
            "(containing profile.py)."
        )
    profile_py = Path(d) / "profile.py"
    if not profile_py.is_file():
        raise FileNotFoundError(f"No profile.py in INSTRUMENT_DIR: {d}")
    if str(profile_py.parent) not in sys.path:
        sys.path.append(str(profile_py.parent))
    spec = importlib.util.spec_from_file_location("_stips_profile", profile_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.profile


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
    """Pipeline configuration loaded from a YAML config file's ``env:`` block.

    Attributes:
        repo: Path to Butler repository
        stack_dir: Path to LSST stack installation
        instrument_dir: Active instrument package directory containing
            pipelines/ and configs/ (the primary required instrument field;
            base of all pipeline/config path joins)
        obs_nickel: Deprecated read-only alias for instrument_dir (kept one
            release; see the ``obs_nickel`` property)
        raw_parent_dir: Parent directory for raw data
        refcat_repo: Path to reference catalog repository
        cp_pipe_dir: Path to cp_pipe pipelines
        env: The raw, ${VAR}-expanded YAML env: block (instrument-specific keys
            read by profile hooks, e.g. fetch_data).
        profile: Active instrument's InstrumentProfile (None if
            instruments/<name>/profile.py is absent; use require_profile() for
            an actionable error)
    """

    repo: Path
    stack_dir: Path
    instrument_dir: Path
    raw_parent_dir: Path
    refcat_repo: Path | None = None
    cp_pipe_dir: Path | None = None
    env: dict[str, str] = field(default_factory=dict)

    # Active instrument's InstrumentProfile (loaded by path from INSTRUMENT_DIR).
    # May be None if instruments/<name>/profile.py is absent; commands that need
    # it should call require_profile() to surface an actionable error.
    profile: "InstrumentProfile | None" = None

    # Derived paths (set in __post_init__)
    pipelines_dir: Path = field(init=False)
    configs_dir: Path = field(init=False)

    def __post_init__(self):
        # instrument_dir is the generic base for pipeline/config path joins.
        self.pipelines_dir = self.instrument_dir / "pipelines"
        self.configs_dir = self.instrument_dir / "configs"

    @property
    def obs_nickel(self) -> Path:
        """Deprecated alias for instrument_dir (kept one release; read-only)."""
        return self.instrument_dir

    def require_profile(self) -> "InstrumentProfile":
        """Return the active instrument profile, or raise an actionable error.

        Use this from commands that genuinely need the profile. If the obs
        package was not importable at config-load time, ``profile`` is None and
        this surfaces a clear, fixable error instead of an opaque AttributeError.
        """
        if self.profile is None:
            raise RuntimeError(
                "instrument profile not loaded; set INSTRUMENT_DIR to "
                "instruments/<name>/ containing profile.py."
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
        if not self.instrument_dir.exists():
            errors.append(f"INSTRUMENT_DIR does not exist: {self.instrument_dir}")
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
                "REPO, STACK_DIR, INSTRUMENT_DIR, RAW_PARENT_DIR)."
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

    # INSTRUMENT_PACKAGE is removed: the profile is loaded BY PATH from
    # INSTRUMENT_DIR. A lingering INSTRUMENT_PACKAGE in the env block is a stale
    # config; fail loud so it gets migrated.
    if merged.get("INSTRUMENT_PACKAGE"):
        raise ValueError(
            "INSTRUMENT_PACKAGE is removed; set INSTRUMENT_DIR to "
            "instruments/<name>/ (containing profile.py) instead."
        )

    # Validate required fields
    required = ["REPO", "STACK_DIR", "RAW_PARENT_DIR"]
    missing = [k for k in required if not merged.get(k)]

    # Resolve the instrument directory: INSTRUMENT_DIR is the documented key;
    # OBS_NICKEL is a deprecated alias (warn). A missing one is reported as
    # INSTRUMENT_DIR via the standard missing-key error below.
    instrument_dir_val = merged.get("INSTRUMENT_DIR")
    if not instrument_dir_val and merged.get("OBS_NICKEL"):
        warnings.warn(
            "OBS_NICKEL is deprecated; rename it to INSTRUMENT_DIR in the config env: block.",
            DeprecationWarning,
            stacklevel=2,
        )
        instrument_dir_val = merged["OBS_NICKEL"]
    if not instrument_dir_val:
        missing.append("INSTRUMENT_DIR")

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

    # Load the active instrument profile BY PATH from INSTRUMENT_DIR
    # (post-collapse: a telescope is instruments/<name>/profile.py, loaded by
    # path — there is no importable obs package). NOTE: the `instrument_dir`
    # Path object isn't built until later in load() — only the string
    # `instrument_dir_val` exists here, so use Path(instrument_dir_val). This
    # mirrors lsst.obs.stips.profile_loader.load_profile_from_dir (load by path +
    # insert the dir on sys.path so co-located hook modules — e.g. `from fetch
    # import fetch_data` — resolve); keep the two in sync.
    #
    # Robustness: if profile.py is absent, do NOT crash config loading — leave
    # profile=None. Commands that need it call Config.require_profile() for a
    # clear, actionable error.
    profile = None
    candidate = Path(instrument_dir_val).expanduser() / "profile.py"
    if candidate.is_file():
        profile = load_active_profile(Path(instrument_dir_val).expanduser())

    # instrument_dir_val resolved above (INSTRUMENT_DIR, or deprecated
    # OBS_NICKEL alias). The missing-check has already guaranteed it is set.
    instrument_dir = Path(instrument_dir_val).expanduser()

    return Config(
        repo=Path(merged["REPO"]).expanduser(),
        stack_dir=stack_dir,
        instrument_dir=instrument_dir,
        raw_parent_dir=Path(merged["RAW_PARENT_DIR"]).expanduser(),
        refcat_repo=(
            Path(merged["REFCAT_REPO"]).expanduser()
            if merged.get("REFCAT_REPO")
            else None
        ),
        cp_pipe_dir=cp_pipe_dir,
        env=dict(merged),
        profile=profile,
    )
