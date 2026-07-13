"""Butler queries for the dashboard (in-stack JSON-snippet pattern).

This module replaces the dashboard's old parallel Butler stack
(``dashboard/butler_query.py`` + ``dashboard/catalog_query.py``), which ran bare
``python3 -c`` subprocess snippets with **no stack activation** and queried
**stale dataset-type names** (``goodSeeingDiff_differenceExp``,
``forced_diff_radec``, ``initial_pvi``) — so the monitoring dashboard silently
reported zeros for current runs (finding F-023).

Every query here now:

* runs inside the activated LSST stack via
  :func:`stips.core.stack.run_butler_python_json` (the house pattern used by
  ``core/butler_query.py``), so it gets stack setup + version gating for free;
* queries the **canonical** dataset-type names from
  :mod:`stips.core.dataset_types`;
* gates the in-stack API newest-first (``butler.query_datasets`` on v28+, falling
  back to ``registry.queryDatasets`` on v27) exactly like ``core/butler_query``.

The dashboard is launched with a base :class:`~stips.core.config.Config` (from
the ``-c`` YAML). Each monitored *run* points at its own Butler repo (recorded in
``logs/<run>/run_info.txt``); we derive a per-run ``Config`` from the base one by
swapping in that repo path, so all queries activate the same stack the launch
config selected. When the dashboard is launched without ``-c`` (``config`` is
None), in-stack queries report ``available: False`` rather than silently zeroing.

Query shapes that could be promoted to ``core/butler_query`` for reuse (noted
here for a follow-up; deliberately *not* added to core under PR-28 scope, which
forbids core edits):

* ``dataset_counts`` — counts grouped by ``day_obs`` + ``band`` across several
  dataset types at once (the dashboard night-grid shape).
* ``catalog_rows`` — pull selected columns from source-catalog datasets.
* ``metric_values`` — read scalar fields out of ``*_metrics`` metadata datasets.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from stips.core.dataset_types import (
    DIA_SOURCE_UNFILTERED,
    DIFFERENCE_IMAGE,
    FORCED_PHOT_DIFFIM_RADEC,
    PRELIMINARY_VISIT_IMAGE,
)
from stips.core.stack import run_butler_python_json

if TYPE_CHECKING:
    from stips.core.config import Config

logger = logging.getLogger(__name__)

# Dataset types the monitoring grid counts, in display order. These are the
# CURRENT canonical names — F-023 replaced the stale literals (``calexp`` /
# ``initial_pvi`` / ``goodSeeingDiff_differenceExp`` / ``forced_diff_radec``)
# with the core.dataset_types constants.
MONITORED_DATASET_TYPES: list[str] = [
    PRELIMINARY_VISIT_IMAGE,  # was "calexp" / "initial_pvi"
    DIFFERENCE_IMAGE,  # was "goodSeeingDiff_differenceExp"
    DIA_SOURCE_UNFILTERED,  # DIA source detections
    FORCED_PHOT_DIFFIM_RADEC,  # was "forced_diff_radec"
]

#: Per-visit warped template written by the DIA pipeline (rewarpTemplate's
#: ``connections.template`` in ``instrument_defaults/pipelines/DIA.yaml``).
#: Replaces the stale ``goodSeeingDiff_templateExp``. Not yet in
#: ``core.dataset_types`` — flagged for core adoption.
TEMPLATE_DETECTOR = "template_detector"

# Image dataset types offered by the FITS viewer (science / template /
# difference panels in the analysis tab), in display order.
IMAGE_DATASET_TYPES: list[str] = [
    PRELIMINARY_VISIT_IMAGE,  # was "calexp"
    TEMPLATE_DETECTOR,  # was "goodSeeingDiff_templateExp"
    DIFFERENCE_IMAGE,  # was "goodSeeingDiff_differenceExp"
]

# Source-catalog datasets browsable in the "data" tab. Names are current
# (dia_source_unfiltered / forced_phot_diffim_radec match core.dataset_types).
CATALOG_TYPES: dict[str, dict] = {
    DIA_SOURCE_UNFILTERED: {
        "label": "DIA Sources",
        "columns": [
            "coord_ra",
            "coord_dec",
            "band",
            "visit",
            "ip_diffim_forced_PsfFlux_instFlux",
            "ip_diffim_forced_PsfFlux_instFluxErr",
        ],
    },
    FORCED_PHOT_DIFFIM_RADEC: {
        "label": "Forced Photometry",
        "columns": [
            "coord_ra",
            "coord_dec",
            "band",
            "visit",
            "psfDiffFlux",
            "psfDiffFluxErr",
        ],
    },
}

# Metric datasets and their key fields (+ threshold bands for client colouring).
# These ``*_metrics`` metadata dataset names are current for the supported stack.
METRIC_TYPES: dict[str, dict] = {
    "calibrateImage_metadata_metrics": {
        "label": "Science Calibration",
        "metrics": {
            "psf_good_star_count": {
                "good": (10, None),
                "warn": (5, 10),
                "bad": (None, 5),
            },
            "astrometry_matches_count": {
                "good": (20, None),
                "warn": (10, 20),
                "bad": (None, 10),
            },
            "photometry_matches_count": {
                "good": (20, None),
                "warn": (10, 20),
                "bad": (None, 10),
            },
            "bad_mask_fraction": {
                "good": (None, 0.05),
                "warn": (0.05, 0.15),
                "bad": (0.15, None),
            },
            "cr_mask_fraction": {
                "good": (None, 0.03),
                "warn": (0.03, 0.10),
                "bad": (0.10, None),
            },
        },
    },
    "diffimMetadata_metrics": {
        "label": "DIA Quality",
        "metrics": {
            "spatialKernelSum": {
                "good": (0.8, 1.2),
                "warn_low": (0.5, 0.8),
                "warn_high": (1.2, 1.5),
            },
            "templateCoveragePercent": {
                "good": (90, None),
                "warn": (70, 90),
                "bad": (None, 70),
            },
            "spatialConditionNum": {
                "good": (None, 100),
                "warn": (100, 1000),
                "bad": (1000, None),
            },
        },
    },
    "detectAndMeasureDiaSource_metadata_metrics": {
        "label": "Detection Counts",
        "metrics": {
            "nMergedDiaSources": {},
            "nPixelsDetectedPositive": {},
            "nPixelsDetectedNegative": {},
        },
    },
}

# Per-repo cache for dataset counts (relatively expensive; keyed by repo path).
_counts_cache: dict[str, dict] = {}


# --------------------------------------------------------------------------- #
# Config / repo plumbing
# --------------------------------------------------------------------------- #
def repo_config(base_config: "Config", repo_path: str) -> "Config":
    """Return a per-run Config pointing at ``repo_path``.

    Reuses the launch config's ``stack_dir`` / ``instrument_dir`` / env (so the
    same stack activates) but swaps in this run's Butler repo.
    """
    return dataclasses.replace(base_config, repo=Path(repo_path))


def resolve_repo_path(logs_dir: Path, run_id: str) -> str | None:
    """Read the Butler repo path from ``logs/<run_id>/run_info.txt``.

    Returns None when the file or the ``Repository:`` line is absent, or when the
    recorded path no longer exists on disk.
    """
    run_info_path = logs_dir / run_id / "run_info.txt"
    if not run_info_path.exists():
        return None
    for line in run_info_path.read_text().splitlines():
        if line.startswith("Repository:"):
            repo_path = line.split(":", 1)[1].strip()
            if repo_path and Path(repo_path).exists():
                return repo_path
            return None
    return None


# --------------------------------------------------------------------------- #
# Snippet builders (pure string functions — unit-testable without a stack)
# --------------------------------------------------------------------------- #
def _query_refs_helper() -> str:
    """Newest-first ref-query helper shared by every snippet below.

    Defines ``_query_refs(dt, where="")`` preferring ``butler.query_datasets``
    (v28+) and falling back to ``registry.queryDatasets`` (v27). A missing
    dataset type yields ``[]`` instead of raising.
    """
    return """
def _query_refs(dt, where=""):
    try:
        try:
            return list(butler.query_datasets(
                dt, find_first=False, where=where, explain=False))
        except (AttributeError, TypeError, ValueError):
            if where:
                return list(butler.registry.queryDatasets(dt, where=where))
            return list(butler.registry.queryDatasets(dt))
    except MissingDatasetTypeError:
        return []
    except Exception:
        return []
"""


def _preamble(repo: str) -> str:
    """Shared snippet preamble: imports + Butler + MissingDatasetTypeError shim."""
    return f"""
import json, sys
try:
    from lsst.daf.butler import Butler
except ImportError:
    print(json.dumps({{"__unavailable__": "lsst.daf.butler not importable"}}))
    sys.exit(0)
try:
    from lsst.daf.butler import MissingDatasetTypeError
except Exception:
    class MissingDatasetTypeError(Exception):
        pass

butler = Butler.from_config({repo!r}, writeable=False)
"""


def _build_counts_script(repo: str, dataset_types: list[str]) -> str:
    """Snippet printing ``{"dataset_types": [...], "nights": {night: {dt: {band: n}}}}``."""
    return (
        _preamble(repo)
        + _query_refs_helper()
        + f"""
dataset_types = {dataset_types!r}
nights = {{}}
for dt in dataset_types:
    for ref in _query_refs(dt):
        did = ref.dataId
        night = str(did.get("day_obs", did.get("visit", "")))[:8]
        band = did.get("band", did.get("physical_filter", "?"))
        nights.setdefault(night, {{}}).setdefault(dt, {{}})
        nights[night][dt][band] = nights[night][dt].get(band, 0) + 1
print(json.dumps({{"dataset_types": dataset_types, "nights": nights}}))
"""
    )


def _build_catalog_script(
    repo: str,
    catalog_type: str,
    columns: list[str],
    where: str,
    limit: int,
    offset: int,
) -> str:
    """Snippet printing ``{"columns": [...], "rows": [...], "total": N}``."""
    return (
        _preamble(repo)
        + _query_refs_helper()
        + f"""
catalog_type = {catalog_type!r}
desired_cols = {columns!r}
limit = {limit!r}
offset = {offset!r}

refs = _query_refs(catalog_type, {where!r})
total = len(refs)
rows = []
for ref in refs[offset:offset + limit]:
    try:
        cat = butler.get(ref)
    except Exception:
        continue
    did = ref.dataId
    night = str(did.get("day_obs", ""))
    band = did.get("band", "?")
    available_cols = list(cat.columns) if hasattr(cat, "columns") else []
    for i, record in enumerate(cat):
        if i >= 50:  # cap rows per dataset ref
            break
        row = {{"night": night, "band": band}}
        for col in desired_cols:
            if col in available_cols:
                val = record[col]
                try:
                    row[col] = float(val)
                except (TypeError, ValueError):
                    row[col] = str(val)
        rows.append(row)

columns = ["night", "band"] + desired_cols
print(json.dumps({{"columns": columns, "rows": rows[:limit], "total": total}}))
"""
    )


def _build_metrics_script(repo: str, metric_fields: dict[str, list[str]]) -> str:
    """Snippet printing ``{"metric_groups": {dt: {"night/band": {field: value}}}}``."""
    return (
        _preamble(repo)
        + _query_refs_helper()
        + f"""
metric_fields = {metric_fields!r}
groups = {{}}
for dt, desired in metric_fields.items():
    group_data = {{}}
    for ref in _query_refs(dt):
        did = ref.dataId
        night = str(did.get("day_obs", ""))[:8]
        band = did.get("band", "?")
        key = f"{{night}}/{{band}}"
        try:
            metrics = butler.get(ref)
        except Exception:
            continue
        row = {{}}
        for field in desired:
            if hasattr(metrics, field):
                val = getattr(metrics, field)
            elif isinstance(metrics, dict) and field in metrics:
                val = metrics[field]
            else:
                continue
            try:
                row[field] = float(val)
            except (TypeError, ValueError):
                row[field] = str(val)
        if row:
            group_data[key] = row
    if group_data:
        groups[dt] = group_data
print(json.dumps({{"metric_groups": groups}}))
"""
    )


# --------------------------------------------------------------------------- #
# Public query helpers
# --------------------------------------------------------------------------- #
def _reason(result) -> str:
    """Extract an error reason from a failed/absent snippet result."""
    if isinstance(result, dict) and "__unavailable__" in result:
        return str(result["__unavailable__"])
    return "Butler query failed"


def query_dataset_counts(config: "Config | None", run_id: str, logs_dir: Path) -> dict:
    """Count monitored datasets grouped by night and band for a run.

    Returns ``{"available", "error", "dataset_types", "nights"}`` where
    ``nights`` maps ``night -> {dataset_type -> {band -> count}}``. Uses the
    CURRENT dataset-type names and runs inside the activated stack.
    """
    if config is None:
        return {
            "available": False,
            "error": "no stack configuration (launch with -c config.yaml)",
            "dataset_types": [],
            "nights": {},
        }

    repo_path = resolve_repo_path(logs_dir, run_id)
    if repo_path is None:
        return {
            "available": False,
            "error": "Repository not found (run_info.txt missing or stale)",
            "dataset_types": [],
            "nights": {},
        }

    if repo_path in _counts_cache:
        return _counts_cache[repo_path]

    script = _build_counts_script(repo_path, MONITORED_DATASET_TYPES)
    result = run_butler_python_json(script, repo_config(config, repo_path))
    if not isinstance(result, dict) or "__unavailable__" in result:
        return {
            "available": False,
            "error": _reason(result),
            "dataset_types": [],
            "nights": {},
        }

    data = {
        "available": True,
        "error": None,
        "dataset_types": result.get("dataset_types", MONITORED_DATASET_TYPES),
        "nights": result.get("nights", {}),
    }
    _counts_cache[repo_path] = data
    return data


def query_catalog(
    config: "Config | None",
    repo_path: str,
    catalog_type: str,
    night: str | None = None,
    band: str | None = None,
    limit: int = 200,
    offset: int = 0,
    *,
    instrument_name: str,
) -> dict:
    """Query a Butler source catalog and return selected columns as rows."""
    if catalog_type not in CATALOG_TYPES:
        return {
            "available": False,
            "error": f"Unknown catalog: {catalog_type}",
            "columns": [],
            "rows": [],
            "total": 0,
        }
    if config is None:
        return {
            "available": False,
            "error": "no stack configuration (launch with -c config.yaml)",
            "columns": [],
            "rows": [],
            "total": 0,
        }

    where_parts = [f"instrument='{instrument_name}'"]
    if night:
        where_parts.append(f"day_obs={int(night)}")
    if band:
        where_parts.append(f"band='{band}'")
    where = " AND ".join(where_parts)

    script = _build_catalog_script(
        repo_path,
        catalog_type,
        CATALOG_TYPES[catalog_type]["columns"],
        where,
        limit,
        offset,
    )
    result = run_butler_python_json(script, repo_config(config, repo_path))
    if not isinstance(result, dict) or "__unavailable__" in result:
        return {
            "available": False,
            "error": _reason(result),
            "columns": [],
            "rows": [],
            "total": 0,
        }

    return {
        "available": True,
        "error": None,
        "columns": result.get("columns", []),
        "rows": result.get("rows", []),
        "total": result.get("total", 0),
    }


def query_metrics(config: "Config | None", repo_path: str) -> dict:
    """Query pipeline quality metrics grouped by night/band.

    Returns ``{"available", "error", "metric_groups", "thresholds"}``. Threshold
    bands come from ``METRIC_TYPES`` for client-side colour coding.
    """
    thresholds = {dt: info["metrics"] for dt, info in METRIC_TYPES.items()}
    if config is None:
        return {
            "available": False,
            "error": "no stack configuration (launch with -c config.yaml)",
            "metric_groups": {},
            "thresholds": thresholds,
        }

    metric_fields = {
        dt: list(info["metrics"].keys()) for dt, info in METRIC_TYPES.items()
    }
    script = _build_metrics_script(repo_path, metric_fields)
    result = run_butler_python_json(script, repo_config(config, repo_path))
    if not isinstance(result, dict) or "__unavailable__" in result:
        return {
            "available": False,
            "error": _reason(result),
            "metric_groups": {},
            "thresholds": thresholds,
        }

    return {
        "available": True,
        "error": None,
        "metric_groups": result.get("metric_groups", {}),
        "thresholds": thresholds,
    }
