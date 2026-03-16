"""Configuration loading and validation for small telescope pipelines."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


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
    """Pipeline configuration loaded from environment variables or YAML env section.

    Attributes:
        repo: Path to Butler repository
        stack_dir: Path to LSST stack installation
        obs_package: Path to instrument obs package (e.g. obs_smalltel)
        raw_parent_dir: Parent directory for raw data
        refcat_repo: Path to reference catalog repository
        cp_pipe_dir: Path to cp_pipe pipelines
    """

    repo: Path
    stack_dir: Path
    obs_package: Path
    raw_parent_dir: Path
    refcat_repo: Path | None = None
    cp_pipe_dir: Path | None = None

    # Derived paths (set in __post_init__)
    pipelines_dir: Path = field(init=False)
    configs_dir: Path = field(init=False)

    def __post_init__(self):
        self.pipelines_dir = self.obs_package / "pipelines"
        self.configs_dir = self.obs_package / "configs"

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
        if not self.obs_package.exists():
            errors.append(f"OBS_SMALLTEL does not exist: {self.obs_package}")
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
