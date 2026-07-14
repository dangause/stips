"""Configuration loading and validation for Nickel pipelines."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stips.profile import InstrumentProfile

_log = logging.getLogger(__name__)


# Repo packages/ dir, derived from this file's location
# (packages/stips/src/stips/core/config.py -> parents[4] == packages/).
_PACKAGES_DIR = Path(__file__).resolve().parents[4]


def resolve_data_package_dir(
    profile: "InstrumentProfile", instrument_dir: str | Path
) -> Path | None:
    """Resolve the directory of the profile's curated-calibration data package.

    The active instrument declares an optional EUPS data package of curated
    calibrations via ``profile.obs_data_package`` (e.g. ``obs_nickel_data``).
    This locates that package on disk so callers can eups-setup / PYTHONPATH it,
    without assuming it lives under the framework's own ``packages/`` directory.

    Resolution precedence:

    1. ``profile.package_dir`` if set — an explicit override. An absolute path is
       used as-is; a relative path is resolved against ``instrument_dir`` so a
       fork can co-locate the package under its own ``instruments/<x>/`` tree
       (e.g. ``package_dir="obs_<x>_data"``). Honored even if the path does not
       yet exist, since it is an explicit declaration.
    2. ``<instrument_dir>/<obs_data_package>`` if it exists — the co-located
       layout, without needing an explicit ``package_dir``. This is the
       reference layout (``instruments/nickel/obs_nickel_data``).
    3. ``<framework packages/>/<obs_data_package>`` if it exists — a legacy
       fallback for a package still living under the framework ``packages/`` dir.
    4. ``None`` — the profile declares no data package, or a package is named but
       none of the candidate locations exist (caller skips data-package setup).

    Args:
        profile: The active instrument profile.
        instrument_dir: The active instrument directory (``INSTRUMENT_DIR``).

    Returns:
        The resolved data-package directory, or ``None`` if not resolvable.
    """
    instrument_dir = Path(instrument_dir)

    # (1) Explicit override wins, existence-independent.
    package_dir = getattr(profile, "package_dir", None)
    if package_dir:
        p = Path(package_dir).expanduser()
        return p if p.is_absolute() else (instrument_dir / p)

    data_pkg = getattr(profile, "obs_data_package", None)
    if not data_pkg:
        return None

    # (2) Co-located under the instrument dir.
    colocated = instrument_dir / data_pkg
    if colocated.exists():
        return colocated

    # (3) Reference layout: framework packages/ sibling.
    framework = _PACKAGES_DIR / data_pkg
    if framework.exists():
        return framework

    # (4) Named but not found anywhere.
    return None


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
        _log.warning(
            "CP_PIPE_DIR not discovered (no LSST loader script in %s); calib "
            "pipelines will fail — set CP_PIPE_DIR explicitly.",
            stack_dir,
        )
        return None

    # Query eups for cp_pipe location. The loader path is passed via the
    # environment and referenced as "$STIPS_LOADER" rather than interpolated
    # into the script text, so a path with shell metacharacters cannot expand
    # or inject (F-018).
    script = """
source "$STIPS_LOADER" 2>/dev/null
setup lsst_distrib 2>/dev/null
eups list -d cp_pipe 2>/dev/null | head -1 | awk '{print $1}'
"""
    try:
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "STIPS_LOADER": str(loader)},
        )
        if result.returncode == 0 and result.stdout.strip():
            path = Path(result.stdout.strip())
            if path.exists():
                return path
    except Exception as e:
        _log.warning(
            "CP_PIPE_DIR auto-discovery failed (%s: %s); calib pipelines will "
            "fail — set CP_PIPE_DIR explicitly.",
            type(e).__name__,
            e,
        )
        return None

    _log.warning(
        "CP_PIPE_DIR not discovered from the LSST stack; calib pipelines will "
        "fail — set CP_PIPE_DIR explicitly."
    )
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

    # Framework reference pipelines/configs root (set in __post_init__).
    _defaults_root: Path = field(init=False, repr=False)

    def __post_init__(self):
        # Framework-shipped reference pipelines/configs. A fork overrides any one
        # by dropping a same-named file into its own instruments/<x>/{pipelines,
        # configs}/; the resolver below picks instrument-dir-first, else this.
        self._defaults_root = _PACKAGES_DIR / "obs_stips" / "instrument_defaults"

    def resolve_pipeline(self, name: str) -> Path:
        """Resolve a pipeline YAML by name, instrument-dir-first else framework.

        e.g. config.resolve_pipeline("DIA.yaml")
        """
        return self._first_existing("pipelines", name)

    def resolve_config(self, name: str) -> Path:
        """Resolve a config .py by name, instrument-dir-first else framework.

        e.g. config.resolve_config("dia/subtractImages.py")
        """
        return self._first_existing("configs", name)

    def _first_existing(self, kind: str, name: str) -> Path:
        p = self.instrument_dir / kind / name
        return p if p.exists() else self._defaults_root / kind / name

    def require_profile(self) -> "InstrumentProfile":
        """Return the active instrument profile, or raise an actionable error.

        Use this from commands that genuinely need the profile. If
        INSTRUMENT_DIR/profile.py was absent at config-load time, ``profile`` is
        None and this surfaces a clear, fixable error instead of an opaque
        AttributeError.
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
        if self.refcat_repo and not self.refcat_repo.exists():
            errors.append(f"REFCAT_REPO does not exist: {self.refcat_repo}")
        return errors


# Max ${VAR} expansion passes before we declare a reference cycle. Config env
# blocks are shallow (a value referencing a value referencing a value), so a
# legitimate chain resolves in a handful of passes; 10 is generous headroom
# while still terminating deterministically on a self-referential cycle.
_MAX_EXPANSION_PASSES = 10


def _expand_within(value: str, env: dict[str, str], *, key: str | None = None) -> str:
    """Expand ${VAR} references using ONLY the given env dict (no os.environ).

    Args:
        value: String potentially containing ${VAR} references
        env: The config env block — the sole substitution source
        key: The env key ``value`` came from (for error messages), if known

    Returns:
        String with all ${VAR} references fully expanded.

    Raises:
        ValueError: If a ``${`` is unterminated (no closing ``}``), if a
            referenced variable is not defined in the env block, or if the
            expansion does not terminate within ``_MAX_EXPANSION_PASSES``
            (a self-referential or mutually-recursive cycle).
    """
    where = f" (env key '{key}')" if key else ""
    passes = 0
    while "${" in value:
        passes += 1
        if passes > _MAX_EXPANSION_PASSES:
            raise ValueError(
                f"${{VAR}} expansion did not terminate after "
                f"{_MAX_EXPANSION_PASSES} passes{where}; this indicates a "
                f"self-referential or mutually-recursive reference. Last value: "
                f"{value!r}. Remove the cycle in the config env: block."
            )
        start = value.index("${")
        end = value.find("}", start)
        if end == -1:
            raise ValueError(
                f"Unterminated '${{' in config value{where}: {value!r}. "
                f"Every ${{VAR}} must have a closing '}}'."
            )
        var_name = value[start + 2 : end]
        if var_name not in env:
            available = ", ".join(sorted(env)) or "(none)"
            raise ValueError(
                f"Unknown variable '${{{var_name}}}' referenced in config "
                f"value{where}: {value!r}. Available env keys: {available}. "
                f"Check for a typo, or define '{var_name}' in the env: block."
            )
        var_value = env[var_name]
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
    merged = {k: _expand_within(v, env, key=k) for k, v in env.items()}

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

    instrument_dir_val = merged.get("INSTRUMENT_DIR")
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

    # instrument_dir_val resolved above (INSTRUMENT_DIR); the missing-check has
    # already guaranteed it is set.
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
