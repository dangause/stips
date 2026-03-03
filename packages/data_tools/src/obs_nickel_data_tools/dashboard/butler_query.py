"""Butler dataset queries for the dashboard.

Queries the LSST Butler to count datasets per night/band.
Requires the LSST stack to be available.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Dataset types we care about for monitoring
DATASET_TYPES = [
    "calexp",
    "initial_pvi",
    "goodSeeingDiff_differenceExp",
    "forced_diff_radec",
]

# Cache for Butler query results (keyed by run_id)
_cache: dict[str, dict] = {}


def query_butler_counts(
    run_id: str,
    logs_dir: Path,
) -> dict:
    """Query Butler for dataset counts grouped by night and band.

    Returns:
        {
            "available": bool,
            "error": str | None,
            "dataset_types": ["calexp", ...],
            "nights": {
                "20230519": {
                    "calexp": {"r": 5, "i": 3},
                    ...
                },
                ...
            }
        }
    """
    if run_id in _cache:
        return _cache[run_id]

    # Find repo path from run_info.txt
    run_info_path = logs_dir / run_id / "run_info.txt"
    if not run_info_path.exists():
        return {
            "available": False,
            "error": "run_info.txt not found",
            "dataset_types": [],
            "nights": {},
        }

    repo_path = None
    for line in run_info_path.read_text().splitlines():
        if line.startswith("Repository:"):
            repo_path = line.split(":", 1)[1].strip()
            break

    if not repo_path or not Path(repo_path).exists():
        return {
            "available": False,
            "error": "Repository not found",
            "dataset_types": [],
            "nights": {},
        }

    query_script = _build_query_script(repo_path)

    try:
        result = subprocess.run(
            ["bash", "-c", query_script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning("Butler query failed: %s", result.stderr[:500])
            return {
                "available": False,
                "error": f"Butler query failed: {result.stderr[:200]}",
                "dataset_types": [],
                "nights": {},
            }

        data = json.loads(result.stdout)
        data["available"] = True
        data["error"] = None
        _cache[run_id] = data
        return data

    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "error": "Butler query timed out (120s)",
            "dataset_types": [],
            "nights": {},
        }
    except (json.JSONDecodeError, Exception) as e:
        return {
            "available": False,
            "error": str(e),
            "dataset_types": [],
            "nights": {},
        }


def _build_query_script(repo_path: str) -> str:
    """Build a Python script that queries Butler and outputs JSON."""
    dataset_types_str = json.dumps(DATASET_TYPES)
    return f"""
python3 -c "
import json, sys
try:
    from lsst.daf.butler import Butler
except ImportError:
    print(json.dumps({{'dataset_types': [], 'nights': {{}}}}))
    sys.exit(0)

repo = '{repo_path}'
try:
    butler = Butler(repo)
except Exception as e:
    print(json.dumps({{'dataset_types': [], 'nights': {{}}, 'error': str(e)}}))
    sys.exit(0)

dataset_types = {dataset_types_str}
nights = {{}}

for dt in dataset_types:
    try:
        refs = list(butler.registry.queryDatasets(dt))
        for ref in refs:
            did = ref.dataId
            night = str(did.get('day_obs', did.get('visit', '')))[:8]
            band = did.get('band', did.get('physical_filter', '?'))
            if night not in nights:
                nights[night] = {{}}
            if dt not in nights[night]:
                nights[night][dt] = {{}}
            nights[night][dt][band] = nights[night][dt].get(band, 0) + 1
    except Exception:
        pass

print(json.dumps({{'dataset_types': dataset_types, 'nights': nights}}))
"
"""
