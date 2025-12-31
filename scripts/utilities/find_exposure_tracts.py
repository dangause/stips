#!/usr/bin/env python3
"""
find_exposure_tracts.py - Find which tract(s) exposures overlap

Given a target name and optional nights, determine which skymap tracts
the exposures overlap with.
"""

import argparse
import os
from collections import defaultdict

from lsst.daf.butler import Butler
from lsst.geom import SpherePoint, degrees


def find_exposure_tracts(
    repo, object_name, skymap_name="nickelRings-v1", nights_file=None
):
    """Find which tracts exposures overlap."""

    butler = Butler(repo)

    # Get the skymap
    try:
        skymap = butler.get("skyMap", skymap=skymap_name, collections=["skymaps"])
    except Exception as e:
        print(f"ERROR: Could not load skymap '{skymap_name}': {e}")
        return

    print(f"=== Finding tracts for {object_name} ===")
    print(f"Repository: {repo}")
    print(f"Skymap: {skymap_name}")
    print()

    # Read nights from file if provided
    if nights_file:
        with open(nights_file) as f:
            nights = [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]
        where = f"instrument='Nickel' AND exposure.target_name='{object_name}' AND day_obs IN ({','.join(nights)})"
    else:
        where = f"instrument='Nickel' AND exposure.target_name='{object_name}'"

    # Query exposures
    exposure_records = butler.registry.queryDimensionRecords("exposure", where=where)

    # Track which tracts each night/band overlaps
    night_band_tracts = defaultdict(lambda: defaultdict(set))
    all_tracts = set()

    for exp in exposure_records:
        # Get the pointing
        ra = exp.tracking_ra
        dec = exp.tracking_dec

        if ra is None or dec is None:
            print(f"WARNING: Exposure {exp.id} has no RA/Dec")
            continue

        # Convert to SpherePoint
        coord = SpherePoint(ra * degrees, dec * degrees)

        # Find overlapping tracts
        tract_info = skymap.findTractPatchList([coord])

        for tract_patch in tract_info:
            tract_id = tract_patch[0].getId()
            all_tracts.add(tract_id)
            night_band_tracts[exp.day_obs][exp.physical_filter].add(tract_id)

    # Print results
    print("=== Results ===")
    print(f"Found {len(all_tracts)} unique tracts: {sorted(all_tracts)}")
    print()

    # Group by night
    for night in sorted(night_band_tracts.keys()):
        print(f"Night {night}:")
        for band in sorted(night_band_tracts[night].keys()):
            tracts = sorted(night_band_tracts[night][band])
            print(f"  {band}: tracts {tracts}")

    return night_band_tracts, all_tracts


def main():
    parser = argparse.ArgumentParser(
        description="Find which skymap tracts exposures overlap"
    )
    parser.add_argument("--object", required=True, help="Target name (e.g., '2020wnt')")
    parser.add_argument(
        "--skymap",
        default="nickelRings-v1",
        help="Skymap name (default: nickelRings-v1)",
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

    find_exposure_tracts(repo, args.object, args.skymap, args.nights)


if __name__ == "__main__":
    main()
