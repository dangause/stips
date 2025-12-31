#!/usr/bin/env python3
"""
find_processable_nights.py - Find nights with complete single-visit processing per band

This script queries the Butler to find which nights have successfully completed
single-visit processing (with single_visit_star_footprints) for each band.
This is useful for determining which nights can be used for DIA processing.

Usage:
    python find_processable_nights.py --object 2020wnt --bands v,r,i --repo /path/to/repo
"""

import argparse
import os
import sys
from pathlib import Path

from lsst.daf.butler import Butler


def find_processable_nights(repo, object_name, bands, output_dir="scripts/config"):
    """Find nights with complete single-visit processing for each band."""

    butler = Butler(repo)
    output_path = Path(output_dir) / object_name
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"=== Finding processable nights for {object_name} ===")
    print(f"Repository: {repo}")
    print(f"Bands: {', '.join(bands)}")
    print()

    for band in bands:
        print(f"=== Band: {band} ===")

        # Query for single_visit_star_footprints datasets
        where = (
            f"instrument='Nickel' AND "
            f"exposure.observation_type='science' AND "
            f"exposure.target_name='{object_name}' AND "
            f"band='{band}'"
        )

        # Get all collections matching the pattern
        all_collections = list(butler.registry.queryCollections("Nickel/runs/*"))

        results = butler.query_datasets(
            "single_visit_star_footprints",
            collections=all_collections,
            where=where,
            with_dimension_records=True,
            find_first=False,
        )

        # Extract unique day_obs values
        nights = sorted(set(ref.dataId["day_obs"] for ref in results))

        # Write to file
        output_file = output_path / f"processable_nights_{band}.txt"
        with open(output_file, "w") as f:
            for night in nights:
                f.write(f"{night}\n")

        print(f"  Found {len(nights)} nights with complete processing")
        print(f"  Output: {output_file}")

        if nights:
            preview = nights[:5]
            if len(nights) > 5:
                preview_str = ", ".join(str(n) for n in preview) + ", ..."
            else:
                preview_str = ", ".join(str(n) for n in preview)
            print(f"  Nights: {preview_str}")
        print()

    print("=== Summary ===")
    print(f"Night lists created in: {output_path}/")
    for band in bands:
        output_file = output_path / f"processable_nights_{band}.txt"
        if output_file.exists():
            count = len(output_file.read_text().strip().split("\n"))
            print(f"  processable_nights_{band}.txt: {count} nights")


def main():
    parser = argparse.ArgumentParser(
        description="Find nights with complete single-visit processing per band"
    )
    parser.add_argument("--object", required=True, help="Target name (e.g., '2020wnt')")
    parser.add_argument(
        "--bands", required=True, help="Comma-separated bands to check (e.g., 'v,r,i')"
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Butler repository path (default: from $REPO environment variable)",
    )
    parser.add_argument(
        "--output-dir",
        default="scripts/config",
        help="Output directory for night lists (default: scripts/config)",
    )

    args = parser.parse_args()

    # Get repo from args or environment
    repo = args.repo or os.environ.get("REPO")
    if not repo:
        print("ERROR: --repo required or REPO environment variable must be set")
        sys.exit(1)

    # Parse bands
    bands = [b.strip() for b in args.bands.split(",")]

    find_processable_nights(repo, args.object, bands, args.output_dir)


if __name__ == "__main__":
    main()
