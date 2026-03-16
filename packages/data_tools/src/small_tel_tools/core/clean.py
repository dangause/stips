"""Clean processing runs from a Butler repository.

Removes science, DIA, forced photometry, coadd, and (optionally) calibration
runs while preserving raws, reference catalogs, and skymaps.

Uses ``butler remove-collections --remove-from-parents`` for non-RUN
collections and ``butler remove-runs --force`` for RUN collections, so cleanup
works even when collections are still linked from parent chains.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from small_tel_tools.core.stack import run_butler, run_butler_query

if TYPE_CHECKING:
    from small_tel_tools.core.config import Config
    from small_tel_tools.instruments.base import InstrumentPlugin

log = logging.getLogger(__name__)


def _run_patterns(prefix: str) -> list[str]:
    """Return collection glob patterns for processing runs (safe to delete)."""
    return [
        f"{prefix}/runs/*/processCcd/*",
        f"{prefix}/runs/*/diff/*",
        f"{prefix}/runs/*/forcedPhotRaDec/*",
        f"{prefix}/runs/*/coadd/*",
        f"{prefix}/runs/*/science/*",
    ]


def _calib_patterns(prefix: str) -> list[str]:
    """Return collection glob patterns for calibration collections."""
    return [f"{prefix}/cp/*", f"{prefix}/calib/*"]


def _preserved_patterns(prefix: str) -> list[str]:
    """Return patterns for collections that are never touched by clean."""
    return [
        f"{prefix}/raw/*",
        "refcats/*",
        "skymaps/*",
        "skymaps",
        f"{prefix}/calib/current",
    ]


@dataclass
class CleanResult:
    """Result of cleaning a Butler repository."""

    success: bool
    collections_removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _is_preserved(name: str, prefix: str = "Nickel") -> bool:
    """Check if a collection name should never be deleted."""
    import fnmatch

    for pattern in _preserved_patterns(prefix):
        if fnmatch.fnmatch(name, pattern):
            return True
    # Also protect the top-level infrastructure names
    if name in ("skymaps", "refcats"):
        return True
    return False


def _query_collections(
    config: Config,
    patterns: list[str],
    prefix: str = "Nickel",
) -> dict[str, str]:
    """Query Butler for collections matching the given patterns.

    Returns a dict mapping collection name -> collection type
    (e.g., "RUN", "CHAINED", "CALIBRATION").

    Uses run_butler_query() (not run_butler()) to keep stdout clean
    of LSST log messages that would corrupt the table parsing.
    """
    repo = str(config.repo)
    collections: dict[str, str] = {}

    for pattern in patterns:
        try:
            result = run_butler_query(
                ["query-collections", repo, pattern],
                config,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    # Skip table formatting (header, separator lines)
                    if line.startswith("-") or line.startswith("="):
                        continue
                    if line.lower().startswith("name"):
                        continue
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    col = parts[0]
                    col_type = parts[-1]  # Type is the last column
                    # Never touch preserved collections
                    if _is_preserved(col, prefix):
                        continue
                    collections[col] = col_type
        except Exception as e:
            log.debug(f"Error querying pattern {pattern}: {e}")

    return dict(sorted(collections.items()))


def _build_patterns(
    nights: list[str] | None = None,
    steps: list[str] | None = None,
    prefix: str = "Nickel",
) -> list[str]:
    """Build collection glob patterns from filter options."""
    # Map step names to collection path components
    # Patterns with {night} are per-night; patterns without are global.
    step_to_patterns = {
        "calibs": [f"{prefix}/cp/{{night}}/*", f"{prefix}/calib/{{night}}"],
        "science": [f"{prefix}/runs/{{night}}/processCcd/*"],
        "dia": [f"{prefix}/runs/{{night}}/diff/*"],
        "fphot": [f"{prefix}/runs/{{night}}/forcedPhotRaDec/*"],
        "coadd": [
            f"{prefix}/runs/{{night}}/coadd/*",
            f"{prefix}/runs/{{night}}/science/*",
        ],
    }

    # Determine which patterns to use
    if steps:
        patterns = []
        for step in steps:
            patterns.extend(step_to_patterns[step])
    else:
        # Default: processing runs only (not calibs — calibs must be explicit)
        patterns = _run_patterns(prefix)

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
    plugin: InstrumentPlugin | None = None,
) -> CleanResult:
    """Remove processing runs from the Butler repository.

    Deletes science, DIA, forced photometry, and per-night coadd runs.
    Calibrations are only removed when explicitly requested via
    ``steps=["calibs"]``.  Preserves raws, reference catalogs, and skymaps.

    Uses ``butler remove-collections --remove-from-parents`` for non-RUN
    collections and ``butler remove-runs --force`` for RUN collections.

    Args:
        config: Pipeline configuration
        nights: Only clean these nights (default: all nights)
        steps: Only clean these steps, e.g. ["calibs", "science", "dia"]
            (default: all processing steps except calibs)
        dry_run: List what would be removed without deleting
        plugin: Instrument plugin (default: NickelPlugin)

    Returns:
        CleanResult with removed collections and any errors
    """
    if plugin is None:
        from small_tel_tools.instruments.nickel import NickelPlugin

        plugin = NickelPlugin()
    prefix = plugin.collection_prefix

    valid_steps = {"calibs", "science", "dia", "fphot", "coadd"}
    if steps:
        bad = [s for s in steps if s not in valid_steps]
        if bad:
            return CleanResult(
                success=False,
                errors=[f"Unknown step(s): {bad}. Valid: {sorted(valid_steps)}"],
            )

    repo = str(config.repo)
    result = CleanResult(success=True)

    patterns = _build_patterns(nights, steps, prefix)
    col_map = _query_collections(config, patterns, prefix)

    if not col_map:
        log.info("No collections found to remove")
        return result

    log.info(f"Found {len(col_map)} collections to remove")

    if dry_run:
        result.collections_removed = list(col_map.keys())
        return result

    # Group collections by type for correct removal strategy:
    #   CHAINED/CALIBRATION -> butler remove-collections --remove-from-parents
    #   RUN                 -> butler remove-runs --force
    chains: list[str] = []
    runs: list[str] = []
    calibrations: list[str] = []
    for col, col_type in col_map.items():
        if col_type == "CHAINED":
            chains.append(col)
        elif col_type == "RUN":
            runs.append(col)
        elif col_type == "CALIBRATION":
            calibrations.append(col)
        else:
            # Unknown non-RUN types are safest to remove as collections.
            calibrations.append(col)

    removed: list[str] = []

    # 1. Remove CHAINED collections (detach from parent chains first).
    chains.sort()
    for chain in chains:
        if chain in removed:
            continue
        try:
            remove_result = run_butler(
                [
                    "remove-collections",
                    repo,
                    chain,
                    "--no-confirm",
                    "--remove-from-parents",
                ],
                config,
                capture_output=True,
                check=False,
            )
            if remove_result.returncode == 0:
                removed.append(chain)
                log.info(f"  Removed: {chain}")
            else:
                stderr = remove_result.stderr or ""
                if "not found" in stderr.lower() or "does not exist" in stderr.lower():
                    log.debug(f"  Already gone: {chain}")
                    removed.append(chain)
                else:
                    error_msg = f"Failed to remove {chain}: {stderr.strip()}"
                    log.warning(error_msg)
                    result.errors.append(error_msg)
        except Exception as e:
            error_msg = f"Error removing {chain}: {e}"
            log.warning(error_msg)
            result.errors.append(error_msg)

    # 2. Remove CALIBRATION collections
    for cal_col in calibrations:
        if cal_col in removed:
            continue
        try:
            remove_result = run_butler(
                [
                    "remove-collections",
                    repo,
                    cal_col,
                    "--no-confirm",
                    "--remove-from-parents",
                ],
                config,
                capture_output=True,
                check=False,
            )
            if remove_result.returncode == 0:
                removed.append(cal_col)
                log.info(f"  Removed: {cal_col}")
            else:
                stderr = remove_result.stderr or ""
                if "not found" in stderr.lower() or "does not exist" in stderr.lower():
                    log.debug(f"  Already gone: {cal_col}")
                    removed.append(cal_col)
                else:
                    error_msg = f"Failed to remove {cal_col}: {stderr.strip()}"
                    log.warning(error_msg)
                    result.errors.append(error_msg)
        except Exception as e:
            error_msg = f"Error removing {cal_col}: {e}"
            log.warning(error_msg)
            result.errors.append(error_msg)

    # 3. Remove RUN collections
    remaining_runs = [r for r in runs if r not in removed]
    for run_col in remaining_runs:
        try:
            remove_result = run_butler(
                ["remove-runs", repo, run_col, "--no-confirm", "--force"],
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
