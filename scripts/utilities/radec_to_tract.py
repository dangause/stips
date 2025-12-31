#!/usr/bin/env python3
"""
radec_to_tract.py - Convert RA/Dec to tract number(s)

Given RA/Dec coordinates, determine which skymap tract(s) contain that position.
"""

import argparse
import os
import sys

from lsst.daf.butler import Butler
from lsst.geom import SpherePoint, degrees


def radec_to_tract(repo, ra, dec, skymap_name="nickelRings-v1"):
    """Find which tract(s) contain the given RA/Dec coordinates."""

    butler = Butler(repo)

    # Get the skymap
    try:
        skymap = butler.get("skyMap", skymap=skymap_name, collections=["skymaps"])
    except Exception as e:
        print(f"ERROR: Could not load skymap '{skymap_name}': {e}", file=sys.stderr)
        return []

    # Convert to SpherePoint
    coord = SpherePoint(ra * degrees, dec * degrees)

    # Find overlapping tracts
    tract_info = skymap.findTractPatchList([coord])

    tracts = sorted(set(tract_patch[0].getId() for tract_patch in tract_info))

    return tracts


def main():
    parser = argparse.ArgumentParser(
        description="Convert RA/Dec coordinates to tract number(s)"
    )
    parser.add_argument("ra", type=float, help="Right Ascension in degrees")
    parser.add_argument("dec", type=float, help="Declination in degrees")
    parser.add_argument(
        "--skymap",
        default="nickelRings-v1",
        help="Skymap name (default: nickelRings-v1)",
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
        print(
            "ERROR: --repo required or REPO environment variable must be set",
            file=sys.stderr,
        )
        return 1

    tracts = radec_to_tract(repo, args.ra, args.dec, args.skymap)

    if not tracts:
        print(
            f"ERROR: No tracts found for RA={args.ra}, Dec={args.dec}", file=sys.stderr
        )
        return 1

    # Output tract numbers, one per line
    for tract in tracts:
        print(tract)

    return 0


if __name__ == "__main__":
    sys.exit(main())
