#!/opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python
"""
query_night_metadata.py - Query Butler for exposure metadata for a specific night

This is a helper for build_nights_reference.sh that queries Butler using Python
instead of the shell butler command (which can have issues in subshells).
"""

import argparse
import sys

# Add LSST packages to path
sys.path.insert(
    0,
    "/opt/anaconda3/envs/lsst-scipipe-12.0.0/share/eups/Darwin/daf_butler/gdbafb5446b+33b4eb5b28/python",
)

from lsst.daf.butler import Butler


def query_night(repo, object_name, day_obs):
    """Query Butler for exposures on a specific day_obs.

    Returns: dict with visit IDs, bands, and count, or None if no data found.
    """
    try:
        butler = Butler(repo)

        where = f"instrument='Nickel' AND exposure.day_obs={day_obs} AND exposure.target_name='{object_name}'"

        exposure_records = list(
            butler.registry.queryDimensionRecords("exposure", where=where)
        )

        if not exposure_records:
            return None

        # Extract visit IDs and bands
        visits = sorted(set(exp.id for exp in exposure_records))
        bands = sorted(set(exp.physical_filter for exp in exposure_records))

        return {
            "day_obs": day_obs,
            "visits": visits,
            "bands": bands,
            "count": len(exposure_records),
        }

    except Exception as e:
        # Print error to stderr, return None
        print(f"ERROR: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Query Butler for exposure metadata for a specific night"
    )
    parser.add_argument("repo", help="Butler repository path")
    parser.add_argument("object", help="Target object name")
    parser.add_argument("day_obs", type=int, help="Day of observation (YYYYMMDD)")
    parser.add_argument(
        "--format",
        choices=["json", "shell"],
        default="shell",
        help="Output format (default: shell)",
    )

    args = parser.parse_args()

    result = query_night(args.repo, args.object, args.day_obs)

    if result is None:
        sys.exit(1)

    if args.format == "json":
        import json

        print(json.dumps(result))
    else:
        # Shell-parseable format
        print(f"DAY_OBS={result['day_obs']}")
        print(f"VISITS={','.join(str(v) for v in result['visits'])}")
        print(f"BANDS={','.join(result['bands'])}")
        print(f"COUNT={result['count']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
