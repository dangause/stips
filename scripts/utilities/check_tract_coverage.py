#!/usr/bin/env python3
"""
check_tract_coverage.py - Check which nights have exposures overlapping a tract

This helps debug DIA failures by identifying which nights actually have data
that overlaps with the specified tract.
"""

import argparse
import os
from collections import defaultdict

from lsst.daf.butler import Butler


def check_tract_coverage(repo, object_name, bands, tract, nights_file=None):
    """Check which nights have exposures in the specified tract."""

    butler = Butler(repo)

    # Read nights from file if provided
    if nights_file:
        with open(nights_file) as f:
            nights = [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]
    else:
        # Query all nights for this object
        nights_query = butler.registry.queryDimensionRecords(
            "exposure",
            where=f"instrument='Nickel' AND exposure.target_name='{object_name}'",
        )
        nights = sorted(set(rec.day_obs for rec in nights_query))

    print(f"=== Checking tract {tract} coverage for {object_name} ===")
    print(f"Repository: {repo}")
    print(f"Bands: {', '.join(bands)}")
    print(f"Checking {len(nights)} nights")
    print()

    results = defaultdict(lambda: defaultdict(list))

    for band in bands:
        print(f"=== Band: {band} ===")

        for night in nights:
            # Try to find preliminary_visit_image datasets for this night/band/tract
            try:
                where = (
                    f"instrument='Nickel' AND "
                    f"exposure.observation_type='science' AND "
                    f"exposure.target_name='{object_name}' AND "
                    f"day_obs={night} AND "
                    f"band='{band}' AND "
                    f"tract={tract}"
                )

                # Get all collections
                all_collections = list(
                    butler.registry.queryCollections("Nickel/runs/*")
                )

                refs = list(
                    butler.query_datasets(
                        "preliminary_visit_image",
                        collections=all_collections,
                        where=where,
                        find_first=False,
                    )
                )

                if refs:
                    results[band][night] = len(refs)
                    print(f"  {night}: {len(refs)} exposures in tract {tract}")

            except Exception as e:
                print(f"  {night}: Error - {e}")

        print()

    # Summary
    print("=== Summary ===")
    for band in bands:
        nights_with_data = list(results[band].keys())
        print(
            f"\nBand {band}: {len(nights_with_data)} nights with tract {tract} coverage"
        )
        if nights_with_data:
            print(
                f"  Nights: {', '.join(str(n) for n in sorted(nights_with_data)[:10])}"
            )
            if len(nights_with_data) > 10:
                print(f"  ... and {len(nights_with_data) - 10} more")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Check which nights have exposures in a specific tract"
    )
    parser.add_argument("--object", required=True, help="Target name (e.g., '2020wnt')")
    parser.add_argument(
        "--bands", required=True, help="Comma-separated bands to check (e.g., 'v,r,i')"
    )
    parser.add_argument(
        "--tract", required=True, type=int, help="Tract number to check"
    )
    parser.add_argument(
        "--nights",
        default=None,
        help="Optional file with nights to check (one per line)",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Butler repository path (default: from $REPO environment variable)",
    )

    args = parser.parse_args()

    # Get repo from args or environment
    repo = args.repo or os.environ.get("REPO")
    if not repo:
        print("ERROR: --repo required or REPO environment variable must be set")
        return 1

    # Parse bands
    bands = [b.strip() for b in args.bands.split(",")]

    check_tract_coverage(repo, args.object, bands, args.tract, args.nights)


if __name__ == "__main__":
    main()
