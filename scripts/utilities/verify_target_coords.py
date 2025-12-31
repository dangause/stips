#!/usr/bin/env python3
"""
verify_target_coords.py - Verify that exposures are pointing at the correct target coordinates

This script checks if exposures labeled with a target name actually have RA/Dec
values matching that target's known coordinates.
"""

import argparse
import os
import sys
from collections import defaultdict

from lsst.daf.butler import Butler


def verify_target_coords(
    repo, object_name, expected_ra=None, expected_dec=None, tolerance_deg=5.0
):
    """Verify that exposures match expected target coordinates."""

    butler = Butler(repo)

    print(f"=== Verifying coordinates for {object_name} ===")
    print(f"Repository: {repo}")
    if expected_ra and expected_dec:
        print(f"Expected: RA={expected_ra}°, Dec={expected_dec}°")
        print(f"Tolerance: ±{tolerance_deg}°")
    print()

    # Query exposures
    exposure_records = butler.registry.queryDimensionRecords(
        "exposure",
        where=f"instrument='Nickel' AND exposure.target_name='{object_name}'",
    )

    # Group by unique RA/Dec
    coords_by_pointing = defaultdict(list)

    for exp in exposure_records:
        if exp.tracking_ra is None or exp.tracking_dec is None:
            print(f"WARNING: Exposure {exp.id} ({exp.day_obs}) has no RA/Dec")
            continue

        ra = exp.tracking_ra
        dec = exp.tracking_dec

        # Round to group similar pointings
        coord_key = (round(ra, 2), round(dec, 2))
        coords_by_pointing[coord_key].append(
            {
                "day_obs": exp.day_obs,
                "visit": exp.id,
                "band": exp.physical_filter,
                "ra": ra,
                "dec": dec,
            }
        )

    # Analyze pointings
    print(f"Found {len(coords_by_pointing)} distinct pointing(s):")
    print()

    for (ra_rounded, dec_rounded), exposures in sorted(coords_by_pointing.items()):
        # Get exact values from first exposure
        first_exp = exposures[0]
        ra = first_exp["ra"]
        dec = first_exp["dec"]

        nights = sorted(set(exp["day_obs"] for exp in exposures))

        # Check if matches expected
        matches_expected = True
        if expected_ra and expected_dec:
            ra_diff = abs(ra - expected_ra)
            dec_diff = abs(dec - expected_dec)
            # Handle RA wrap-around
            if ra_diff > 180:
                ra_diff = 360 - ra_diff
            matches_expected = ra_diff < tolerance_deg and dec_diff < tolerance_deg

        status = "✓ MATCHES" if matches_expected else "✗ MISMATCH"

        print(f"Pointing: RA={ra:.4f}°, Dec={dec:.4f}° [{status}]")
        print(f"  Nights: {len(nights)} nights from {nights[0]} to {nights[-1]}")
        print(f"  Exposures: {len(exposures)} total")

        if expected_ra and expected_dec and not matches_expected:
            ra_offset = ra - expected_ra
            dec_offset = dec - expected_dec
            print(f"  Offset: ΔRA={ra_offset:+.4f}°, ΔDec={dec_offset:+.4f}°")

        # Show first few nights
        sample_nights = nights[:5]
        if len(nights) > 5:
            print(f"  Sample nights: {', '.join(str(n) for n in sample_nights)}, ...")
        else:
            print(f"  All nights: {', '.join(str(n) for n in sample_nights)}")
        print()

    return coords_by_pointing


def main():
    parser = argparse.ArgumentParser(
        description="Verify exposure coordinates match expected target position"
    )
    parser.add_argument("--object", required=True, help="Target name (e.g., '2020wnt')")
    parser.add_argument("--ra", type=float, default=None, help="Expected RA in degrees")
    parser.add_argument(
        "--dec", type=float, default=None, help="Expected Dec in degrees"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=5.0,
        help="Tolerance in degrees for coordinate matching (default: 5.0)",
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

    verify_target_coords(repo, args.object, args.ra, args.dec, args.tolerance)


if __name__ == "__main__":
    main()
