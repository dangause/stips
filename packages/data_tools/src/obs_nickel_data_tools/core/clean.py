"""Clean processing runs from a Butler repository.

Removes science, DIA, forced photometry, and coadd runs while preserving
raws, calibrations (cp, calib), reference catalogs, and skymaps.

Uses ``pipetask purge`` (the recommended LSST approach) to remove CHAINED
collections and all their child RUN collections in one operation.  Falls back
to ``butler remove-runs`` / ``butler remove-collections`` for individual
RUN-type collections that have no parent chain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from obs_nickel_data_tools.core.stack import run_butler, run_pipetask

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)

# Collection glob patterns for processing runs (safe to delete).
# These are all under Nickel/runs/ and contain derived products.
RUN_PATTERNS = [
    "Nickel/runs/*/processCcd/*",
    "Nickel/runs/*/diff/*",
    "Nickel/runs/*/forcedPhotRaDec/*",
    "Nickel/runs/*/coadd/*",
    "Nickel/runs/*/science/*",
]

# Patterns that are preserved (never touched by clean)
PRESERVED_PATTERNS = [
    "Nickel/raw/*",
    "Nickel/cp/*",
    "Nickel/calib/*",
    "refcats",
    "skymaps/*",
    "templates/*",
]


@dataclass
class CleanResult:
    """Result of cleaning a Butler repository."""

    success: bool
    collections_removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _query_collections(
    config: Config,
    patterns: list[str],
) -> list[str]:
    """Query Butler for collections matching the given patterns.

    Returns all matching collection names (both CHAINED and RUN types).
    """
    repo = str(config.repo)
    collections: list[str] = []

    for pattern in patterns:
        try:
            result = run_butler(
                ["query-collections", repo, pattern],
                config,
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    col = line.strip()
                    if col and col.startswith("Nickel/runs/"):
                        collections.append(col)
        except Exception as e:
            log.debug(f"Error querying pattern {pattern}: {e}")

    return sorted(set(collections))


def _build_patterns(
    nights: list[str] | None = None,
    steps: list[str] | None = None,
) -> list[str]:
    """Build collection glob patterns from filter options."""
    # Map step names to collection path components
    step_to_patterns = {
        "science": ["Nickel/runs/{night}/processCcd/*"],
        "dia": ["Nickel/runs/{night}/diff/*"],
        "fphot": ["Nickel/runs/{night}/forcedPhotRaDec/*"],
        "coadd": ["Nickel/runs/{night}/coadd/*", "Nickel/runs/{night}/science/*"],
    }

    # Determine which patterns to use
    if steps:
        patterns = []
        for step in steps:
            patterns.extend(step_to_patterns[step])
    else:
        # Use a single pattern that covers everything under Nickel/runs/
        patterns = RUN_PATTERNS

    # Substitute night or use wildcard
    if nights:
        expanded = []
        for pattern in patterns:
            for night in nights:
                expanded.append(pattern.replace("{night}", night))
        patterns = expanded
    else:
        patterns = [p.replace("{night}", "*") for p in patterns]

    return list(dict.fromkeys(patterns))


def run(
    config: Config,
    *,
    nights: list[str] | None = None,
    steps: list[str] | None = None,
    dry_run: bool = False,
) -> CleanResult:
    """Remove processing runs from the Butler repository.

    Deletes science, DIA, forced photometry, and per-night coadd runs.
    Preserves raws, calibrations, reference catalogs, skymaps, and templates.

    Uses ``pipetask purge`` for CHAINED collections (removes the chain and
    all child RUNs in one operation) and ``butler remove-runs`` for any
    remaining individual RUN collections.

    Args:
        config: Pipeline configuration
        nights: Only clean these nights (default: all nights)
        steps: Only clean these steps, e.g. ["science", "dia", "fphot"]
            (default: all steps)
        dry_run: List what would be removed without deleting

    Returns:
        CleanResult with removed collections and any errors
    """
    valid_steps = {"science", "dia", "fphot", "coadd"}
    if steps:
        bad = [s for s in steps if s not in valid_steps]
        if bad:
            return CleanResult(
                success=False,
                errors=[f"Unknown step(s): {bad}. Valid: {sorted(valid_steps)}"],
            )

    repo = str(config.repo)
    result = CleanResult(success=True)

    patterns = _build_patterns(nights, steps)
    collections_to_remove = _query_collections(config, patterns)

    if not collections_to_remove:
        log.info("No processing runs found to remove")
        return result

    log.info(f"Found {len(collections_to_remove)} collections to remove")

    if dry_run:
        result.collections_removed = collections_to_remove
        return result

    # Separate CHAINED parents from individual RUN collections.
    # CHAINED collections are the timestamped parents (e.g., .../processCcd/20250210T...),
    # while RUN collections end in /run.
    # Use pipetask purge on the parents, which removes the chain + all child runs.
    chains: list[str] = []
    runs: list[str] = []
    for col in collections_to_remove:
        if col.endswith("/run"):
            runs.append(col)
        else:
            chains.append(col)

    removed: list[str] = []

    # First, purge CHAINED collections using pipetask purge
    for chain in chains:
        try:
            purge_result = run_pipetask(
                ["purge", "-b", repo, chain, "--no-confirm"],
                config,
                capture_output=True,
                check=False,
            )
            if purge_result.returncode == 0:
                removed.append(chain)
                # Also mark any child /run collections as removed
                child_run = f"{chain}/run"
                if child_run in runs:
                    removed.append(child_run)
                log.info(f"  Purged: {chain}")
            else:
                stderr = purge_result.stderr or ""
                if "not found" in stderr.lower() or "does not exist" in stderr.lower():
                    log.debug(f"  Already gone: {chain}")
                    removed.append(chain)
                else:
                    error_msg = f"Failed to purge {chain}: {stderr.strip()}"
                    log.warning(error_msg)
                    result.errors.append(error_msg)
        except Exception as e:
            error_msg = f"Error purging {chain}: {e}"
            log.warning(error_msg)
            result.errors.append(error_msg)

    # Then remove any RUN collections not already handled by purge
    remaining_runs = [r for r in runs if r not in removed]
    for run_col in remaining_runs:
        try:
            remove_result = run_butler(
                ["remove-runs", repo, run_col, "--no-confirm"],
                config,
                capture_output=True,
                check=False,
            )
            if remove_result.returncode == 0:
                removed.append(run_col)
                log.info(f"  Removed: {run_col}")
            else:
                stderr = remove_result.stderr or ""
                if "not found" in stderr.lower() or "does not exist" in stderr.lower():
                    log.debug(f"  Already gone: {run_col}")
                    removed.append(run_col)
                else:
                    error_msg = f"Failed to remove {run_col}: {stderr.strip()}"
                    log.warning(error_msg)
                    result.errors.append(error_msg)
        except Exception as e:
            error_msg = f"Error removing {run_col}: {e}"
            log.warning(error_msg)
            result.errors.append(error_msg)

    result.collections_removed = removed

    if result.errors:
        result.success = False

    return result
