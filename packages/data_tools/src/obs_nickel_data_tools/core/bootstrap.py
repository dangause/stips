"""Bootstrap Butler repository.

This module handles initializing a new Butler repository with:
- Creating the Butler repo directory
- Registering the Nickel instrument
- Ingesting reference catalogs (MONSTER)
- Registering the SkyMap
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


@dataclass
class BootstrapResult:
    """Result of bootstrap operation."""

    success: bool
    error: str | None = None
    repo_created: bool = False
    instrument_registered: bool = False
    refcats_ingested: bool = False
    skymap_registered: bool = False


def needs_bootstrap(config: Config) -> bool:
    """Check if the repository needs bootstrapping.

    Args:
        config: Pipeline configuration

    Returns:
        True if the repository doesn't exist or isn't initialized
    """
    butler_yaml = config.repo / "butler.yaml"
    return not butler_yaml.exists()


def find_bootstrap_script(config: Config) -> Path | None:
    """Find the bootstrap shell script.

    Args:
        config: Pipeline configuration

    Returns:
        Path to bootstrap script if found, None otherwise
    """
    script_candidates = [
        # From obs_nickel in monorepo
        config.obs_nickel.parent.parent / "scripts/pipeline/00_bootstrap_repo.sh",
        config.obs_nickel / "../../scripts/pipeline/00_bootstrap_repo.sh",
    ]

    # Also check current working directory
    cwd = Path.cwd()
    script_candidates.insert(0, cwd / "scripts/pipeline/00_bootstrap_repo.sh")

    for candidate in script_candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved

    return None


def run(
    config: Config,
    *,
    dry_run: bool = False,
    log_file: Path | None = None,
) -> BootstrapResult:
    """Bootstrap a Butler repository.

    Creates the repo, registers the instrument, ingests reference catalogs,
    and registers the skymap.

    Args:
        config: Pipeline configuration with REPO, STACK_DIR, etc.
        dry_run: Print commands without executing
        log_file: Optional path to write LSST pipeline logs

    Returns:
        BootstrapResult with status
    """
    from obs_nickel_data_tools.core.stack import run_with_stack

    result = BootstrapResult(success=False)

    # Check if already bootstrapped
    if not needs_bootstrap(config):
        log.info(f"Repository already initialized: {config.repo}")
        result.success = True
        result.repo_created = True
        result.instrument_registered = True
        result.refcats_ingested = True
        result.skymap_registered = True
        return result

    log.info(f"Bootstrapping repository: {config.repo}")

    if dry_run:
        log.info("[DRY RUN] Would run bootstrap script")
        result.success = True
        return result

    # Find the bootstrap script
    bootstrap_script = find_bootstrap_script(config)
    if not bootstrap_script:
        result.error = (
            "Bootstrap script not found. "
            "Run from the nickel_processing_suite directory."
        )
        log.error(result.error)
        return result

    log.info(f"Using bootstrap script: {bootstrap_script}")

    try:
        proc_result = run_with_stack(
            [str(bootstrap_script)],
            config,
            check=False,
        )

        if proc_result.returncode == 0:
            result.success = True
            result.repo_created = True
            result.instrument_registered = True
            result.refcats_ingested = True
            result.skymap_registered = True
            log.info("Bootstrap complete")
        else:
            result.error = (
                f"Bootstrap script failed with exit code {proc_result.returncode}"
            )
            log.error(result.error)

    except Exception as e:
        result.error = f"Bootstrap failed: {e}"
        log.error(result.error)

    return result
