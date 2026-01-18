#!/usr/bin/env python3
"""
fix_exposure_coords.py - Fix incorrect RA/Dec in Butler exposure records

This script updates the tracking_ra and tracking_dec values for exposures
that have incorrect WCS information in their FITS headers.

WARNING: This modifies the Butler registry database directly. Make a backup first!

Usage:
    # Dry run (show what would be changed):
    python fix_exposure_coords.py --object 2020wnt --correct-ra 56.66 --correct-dec 43.23 --dry-run

    # Actually fix the coordinates:
    python fix_exposure_coords.py --object 2020wnt --correct-ra 56.66 --correct-dec 43.23
"""

import argparse
import os
import sys
from collections import defaultdict

from lsst.daf.butler import Butler


def fix_exposure_coords(
    repo, object_name, correct_ra, correct_dec, tolerance_deg=5.0, dry_run=True
):
    """Fix exposure coordinates in Butler registry."""

    butler = Butler(repo, writeable=not dry_run)

    print(f"=== Fixing coordinates for {object_name} ===")
    print(f"Repository: {repo}")
    print(f"Correct coordinates: RA={correct_ra}°, Dec={correct_dec}°")
    print(f"Tolerance: ±{tolerance_deg}° (exposures outside this will be updated)")
    print(
        f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE (will modify database)'}"
    )
    print()

    # Query exposures
    exposure_records = list(
        butler.registry.queryDimensionRecords(
            "exposure",
            where=f"instrument='Nickel' AND exposure.target_name='{object_name}'",
        )
    )

    to_fix = []

    for exp in exposure_records:
        if exp.tracking_ra is None or exp.tracking_dec is None:
            continue

        ra = exp.tracking_ra
        dec = exp.tracking_dec

        # Check if needs fixing
        ra_diff = abs(ra - correct_ra)
        dec_diff = abs(dec - correct_dec)

        # Handle RA wrap-around
        if ra_diff > 180:
            ra_diff = 360 - ra_diff

        needs_fix = ra_diff >= tolerance_deg or dec_diff >= tolerance_deg

        if needs_fix:
            to_fix.append(
                {
                    "id": exp.id,
                    "day_obs": exp.day_obs,
                    "band": exp.physical_filter,
                    "old_ra": ra,
                    "old_dec": dec,
                    "ra_diff": ra - correct_ra,
                    "dec_diff": dec - correct_dec,
                }
            )

    if not to_fix:
        print("No exposures need fixing!")
        return

    print(f"Found {len(to_fix)} exposures with incorrect coordinates:")
    print()

    # Group by day_obs
    by_night = defaultdict(list)
    for exp in to_fix:
        by_night[exp["day_obs"]].append(exp)

    for night in sorted(by_night.keys()):
        exps = by_night[night]
        print(f"Night {night}: {len(exps)} exposures")
        for exp in exps[:3]:  # Show first 3 as examples
            print(
                f"  Visit {exp['id']} ({exp['band']}): "
                f"RA={exp['old_ra']:.4f}° → {correct_ra}°, "
                f"Dec={exp['old_dec']:.4f}° → {correct_dec}°"
            )
        if len(exps) > 3:
            print(f"  ... and {len(exps) - 3} more")

    print()
    print(f"Total: {len(to_fix)} exposures across {len(by_night)} nights")
    print()

    if dry_run:
        print("DRY RUN - No changes made.")
        print()
        print("To actually fix these coordinates, run without --dry-run:")
        print(
            f"  python {sys.argv[0]} --object {object_name} --correct-ra {correct_ra} --correct-dec {correct_dec}"
        )
        return

    # Actually update the database
    print("Updating exposure records...")

    # Note: Direct modification of Butler registry is not officially supported
    # This is accessing internal APIs and may break in future versions
    print()
    print("ERROR: Direct Butler registry modification is not implemented.")
    print()
    print(
        "The Butler API doesn't provide a way to update exposure coordinates directly."
    )
    print("You have two options:")
    print()
    print("1. Re-ingest the raw data after fixing the FITS headers:")
    print(
        "   - Use `fitsheader` or `astropy` to update CRVAL1/CRVAL2 in raw FITS files"
    )
    print("   - Delete the incorrect ingestion from Butler")
    print("   - Re-run ingest-raws")
    print()
    print("2. Manually update the SQLite/PostgreSQL database:")
    print("   - Locate the exposure table in the registry database")
    print("   - UPDATE exposure SET tracking_ra=..., tracking_dec=... WHERE ...")
    print("   - This is risky and not recommended")
    print()
    print(f"Exposures that need fixing are on nights: {sorted(by_night.keys())}")


def main():
    parser = argparse.ArgumentParser(
        description="Fix incorrect RA/Dec in Butler exposure records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be changed:
  python fix_exposure_coords.py --object 2020wnt --correct-ra 56.66 --correct-dec 43.23 --dry-run

  # Show which nights have incorrect coordinates:
  python fix_exposure_coords.py --object 2020wnt --correct-ra 56.66 --correct-dec 43.23 --dry-run
""",
    )
    parser.add_argument("--object", required=True, help="Target name (e.g., '2020wnt')")
    parser.add_argument(
        "--correct-ra", type=float, required=True, help="Correct RA in degrees"
    )
    parser.add_argument(
        "--correct-dec", type=float, required=True, help="Correct Dec in degrees"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=5.0,
        help="Tolerance in degrees - exposures outside this range will be updated (default: 5.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying the database",
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

    fix_exposure_coords(
        repo,
        args.object,
        args.correct_ra,
        args.correct_dec,
        args.tolerance,
        args.dry_run,
    )


if __name__ == "__main__":
    main()
