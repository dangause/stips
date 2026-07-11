"""Butler catalog and metric queries for the dashboard.

Queries source catalogs and pipeline metrics via subprocess.
"""

from __future__ import annotations

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

# Source catalog types
CATALOG_TYPES = {
    "dia_source_unfiltered": {
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
    "forced_phot_diffim_radec": {
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

# Metric dataset types and their key fields
METRIC_TYPES = {
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


def query_catalog(
    repo_path: str,
    catalog_type: str,
    night: str | None = None,
    band: str | None = None,
    limit: int = 200,
    offset: int = 0,
    *,
    instrument_name: str,
) -> dict:
    """Query a Butler catalog and return rows as JSON.

    Returns:
        {
            "available": bool,
            "error": str | None,
            "columns": [...],
            "rows": [{...}, ...],
            "total": int,
        }
    """
    if catalog_type not in CATALOG_TYPES:
        return {
            "available": False,
            "error": f"Unknown catalog: {catalog_type}",
            "columns": [],
            "rows": [],
            "total": 0,
        }

    script = _build_catalog_script(
        repo_path, catalog_type, night, band, limit, offset, instrument_name
    )

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return {
                "available": False,
                "error": result.stderr[:300],
                "columns": [],
                "rows": [],
                "total": 0,
            }

        data = json.loads(result.stdout)
        data["available"] = True
        data["error"] = None
        return data

    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "error": "Query timed out",
            "columns": [],
            "rows": [],
            "total": 0,
        }
    except (json.JSONDecodeError, Exception) as e:
        return {
            "available": False,
            "error": str(e),
            "columns": [],
            "rows": [],
            "total": 0,
        }


def query_metrics(repo_path: str) -> dict:
    """Query pipeline quality metrics grouped by night.

    Returns:
        {
            "available": bool,
            "error": str | None,
            "metric_groups": { group_label: { night: { metric: value } } },
            "thresholds": { ... },
        }
    """
    script = _build_metrics_script(repo_path)

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return {
                "available": False,
                "error": result.stderr[:300],
                "metric_groups": {},
                "thresholds": {},
            }

        data = json.loads(result.stdout)
        data["available"] = True
        data["error"] = None
        # Attach threshold definitions for client-side color coding
        data["thresholds"] = {dt: info["metrics"] for dt, info in METRIC_TYPES.items()}
        return data

    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "error": "Query timed out",
            "metric_groups": {},
            "thresholds": {},
        }
    except (json.JSONDecodeError, Exception) as e:
        return {
            "available": False,
            "error": str(e),
            "metric_groups": {},
            "thresholds": {},
        }


def _build_catalog_script(
    repo_path: str,
    catalog_type: str,
    night: str | None,
    band: str | None,
    limit: int,
    offset: int,
    instrument_name: str,
) -> str:
    """Build Python script to query a source catalog."""
    cols = json.dumps(CATALOG_TYPES[catalog_type]["columns"])
    where_parts = [f"instrument='{instrument_name}'"]
    if night:
        where_parts.append(f"day_obs={int(night)}")
    if band:
        where_parts.append(f"band='{band}'")
    where_clause = " AND ".join(where_parts)

    return f"""
import json, sys
try:
    from lsst.daf.butler import Butler
except ImportError:
    print(json.dumps({{"columns": [], "rows": [], "total": 0}}))
    sys.exit(0)

repo = "{repo_path}"
catalog_type = "{catalog_type}"
desired_cols = {cols}
limit = {limit}
offset = {offset}

try:
    butler = Butler(repo)
    refs = list(butler.registry.queryDatasets(catalog_type, where="{where_clause}"))
    total = len(refs)

    rows = []
    for ref in refs[offset:offset + limit]:
        try:
            cat = butler.get(ref)
            did = ref.dataId
            night = str(did.get("day_obs", ""))
            band = did.get("band", "?")

            # Extract columns from catalog
            if hasattr(cat, "columns"):
                available_cols = list(cat.columns)
            else:
                available_cols = []

            for i, record in enumerate(cat):
                if i >= 50:  # Limit rows per dataset ref
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

        except Exception:
            pass

    columns = ["night", "band"] + desired_cols
    print(json.dumps({{"columns": columns, "rows": rows[:limit], "total": total}}))

except Exception as e:
    print(json.dumps({{"columns": [], "rows": [], "total": 0, "error": str(e)}}))
    sys.exit(0)
"""


def _build_metrics_script(repo_path: str) -> str:
    """Build Python script to query pipeline metrics."""
    metric_types = json.dumps(list(METRIC_TYPES.keys()))
    metric_fields = json.dumps(
        {dt: list(info["metrics"].keys()) for dt, info in METRIC_TYPES.items()}
    )

    return f"""
import json, sys
try:
    from lsst.daf.butler import Butler
except ImportError:
    print(json.dumps({{"metric_groups": {{}}}}))
    sys.exit(0)

repo = "{repo_path}"
metric_types = {metric_types}
metric_fields = {metric_fields}

try:
    butler = Butler(repo)
    groups = {{}}

    for dt in metric_types:
        group_data = {{}}
        try:
            refs = list(butler.registry.queryDatasets(dt))
            for ref in refs:
                did = ref.dataId
                night = str(did.get("day_obs", ""))[:8]
                band = did.get("band", "?")
                key = f"{{night}}/{{band}}"

                try:
                    metrics = butler.get(ref)
                    row = {{}}
                    desired = metric_fields.get(dt, [])
                    for field in desired:
                        if hasattr(metrics, field):
                            val = getattr(metrics, field)
                            try:
                                row[field] = float(val)
                            except (TypeError, ValueError):
                                row[field] = str(val)
                        elif isinstance(metrics, dict) and field in metrics:
                            val = metrics[field]
                            try:
                                row[field] = float(val)
                            except (TypeError, ValueError):
                                row[field] = str(val)
                    if row:
                        group_data[key] = row
                except Exception:
                    pass

        except Exception:
            pass

        if group_data:
            groups[dt] = group_data

    print(json.dumps({{"metric_groups": groups}}))

except Exception as e:
    print(json.dumps({{"metric_groups": {{}}, "error": str(e)}}))
    sys.exit(0)
"""
