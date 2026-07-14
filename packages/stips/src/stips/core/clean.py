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

from stips.collections import CollectionNames
from stips.core import butler_query
from stips.core.stack import run_butler

if TYPE_CHECKING:
    from stips.core.config import Config

log = logging.getLogger(__name__)


# Collection glob patterns for processing runs (safe to delete).
# These are all under <prefix>/runs/ and contain derived products.
def run_patterns(prefix: str) -> list[str]:
    """Processing-run glob patterns (safe to delete) for an instrument prefix."""
    return [
        CollectionNames.science_glob(prefix),
        f"{prefix}/runs/*/diff/*",
        CollectionNames.forced_phot_glob(prefix),
        f"{prefix}/runs/*/coadd/*",
    ]


def calib_patterns(prefix: str) -> list[str]:
    """Calibration collection patterns (cp_pipe outputs + certified calibs)."""
    return [
        f"{prefix}/cp/*",
        f"{prefix}/calib/*",
    ]


def preserved_patterns(prefix: str) -> list[str]:
    """Patterns that are always preserved (never touched by clean)."""
    return [
        f"{prefix}/raw/*",
        "refcats/*",
        "skymaps/*",
        "skymaps",
        f"{prefix}/calib/current",
    ]


def step_patterns(prefix: str) -> dict[str, list[str]]:
    """Map step names to per-night collection glob patterns (with {night})."""
    return {
        "calibs": [f"{prefix}/cp/{{night}}/*", f"{prefix}/calib/{{night}}"],
        "science": [f"{prefix}/runs/{{night}}/processCcd/*"],
        "dia": [f"{prefix}/runs/{{night}}/diff/*"],
        "fphot": [CollectionNames.forced_phot_glob(prefix, night="{night}")],
        "coadd": [f"{prefix}/runs/{{night}}/coadd/*"],
    }


@dataclass
class CleanPlan:
    """A captured plan of exactly which collections ``execute()`` will remove.

    Discovery runs once in :func:`plan`; :func:`execute` deletes precisely the
    collections recorded here. This closes the race where preview and deletion
    each re-query the Butler and could act on different collection sets.
    """

    #: Mapping of collection name -> collection type (RUN/CHAINED/CALIBRATION/...).
    collections: dict[str, str] = field(default_factory=dict)
    #: Validation error (e.g. unknown step); when set the plan is not executable.
    error: str | None = None

    @property
    def names(self) -> list[str]:
        """Collection names slated for removal (sorted, as discovered)."""
        return list(self.collections.keys())

    @property
    def is_empty(self) -> bool:
        return not self.collections


@dataclass
class CleanResult:
    """Result of cleaning a Butler repository."""

    success: bool
    collections_removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _is_preserved(name: str, prefix: str) -> bool:
    """Check if a collection name should never be deleted."""
    import fnmatch

    for pattern in preserved_patterns(prefix):
        if fnmatch.fnmatch(name, pattern):
            return True
    # Also protect the top-level infrastructure names
    if name in ("skymaps", "refcats"):
        return True
    return False


def _query_collections(
    config: Config,
    patterns: list[str],
) -> dict[str, str]:
    """Query Butler for collections matching the given patterns.

    Returns a dict mapping collection name -> collection type
    (e.g., "RUN", "CHAINED", "CALIBRATION").

    Uses run_butler_query() (not run_butler()) to keep stdout clean
    of LSST log messages that would corrupt the table parsing.
    """
    prefix = config.require_profile().collection_prefix
    collections: dict[str, str] = {}

    for pattern in patterns:
        try:
            for col, col_type in (
                butler_query.list_collection_types(config, pattern) or {}
            ).items():
                # Never touch preserved collections
                if _is_preserved(col, prefix):
                    continue
                collections[col] = col_type
        except Exception as e:
            log.debug(f"Error querying pattern {pattern}: {e}")

    return dict(sorted(collections.items()))


def _build_patterns(
    prefix: str,
    nights: list[str] | None = None,
    steps: list[str] | None = None,
) -> list[str]:
    """Build collection glob patterns from filter options."""
    # Map step names to collection path components
    # Patterns with {night} are per-night; patterns without are global.
    step_to_patterns = step_patterns(prefix)

    # Determine which patterns to use
    if steps:
        patterns = []
        for step in steps:
            patterns.extend(step_to_patterns[step])
    else:
        # Default: processing runs only (not calibs — calibs must be explicit)
        patterns = run_patterns(prefix)

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


def plan(
    config: Config,
    *,
    nights: list[str] | None = None,
    steps: list[str] | None = None,
) -> CleanPlan:
    """Discover exactly which collections would be removed (no deletion).

    Runs Butler discovery a single time and captures the result in a
    :class:`CleanPlan`. Callers preview the plan, confirm, then pass the *same*
    plan to :func:`execute` — so the set that is deleted is provably the set the
    user saw.

    Args:
        config: Pipeline configuration
        nights: Only clean these nights (default: all nights)
        steps: Only clean these steps, e.g. ["calibs", "science", "dia"]
            (default: all processing steps except calibs)

    Returns:
        CleanPlan of collections to remove, or one carrying ``error`` on an
        invalid step selection.
    """
    valid_steps = {"calibs", "science", "dia", "fphot", "coadd"}
    if steps:
        bad = [s for s in steps if s not in valid_steps]
        if bad:
            return CleanPlan(
                error=f"Unknown step(s): {bad}. Valid: {sorted(valid_steps)}"
            )

    prefix = config.require_profile().collection_prefix
    patterns = _build_patterns(prefix, nights, steps)
    col_map = _query_collections(config, patterns)

    if not col_map:
        log.info("No collections found to remove")
    else:
        log.info(f"Found {len(col_map)} collections to remove")

    return CleanPlan(collections=col_map)


def execute(config: Config, clean_plan: CleanPlan) -> CleanResult:
    """Remove exactly the collections captured in ``clean_plan``.

    Uses ``butler remove-collections --remove-from-parents`` for non-RUN
    collections and ``butler remove-runs --force`` for RUN collections, so
    cleanup works even when collections are still linked from parent chains.

    Args:
        config: Pipeline configuration
        clean_plan: The plan produced by :func:`plan` (deletion targets are read
            from it, not re-discovered).

    Returns:
        CleanResult with removed collections and any errors.
    """
    if clean_plan.error:
        return CleanResult(success=False, errors=[clean_plan.error])

    repo = str(config.repo)
    result = CleanResult(success=True)

    col_map = clean_plan.collections
    if not col_map:
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
