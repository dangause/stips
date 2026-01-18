#!/usr/bin/env python
"""
create_forced_phot_catalog.py - Create a reference catalog for forced photometry

This script creates a simple reference catalog with specified target positions
that can be used with ForcedPhotCcdTask.

Usage:
    python create_forced_phot_catalog.py \\
        --repo /path/to/repo \\
        --ra 56.658125 \\
        --dec 43.22925 \\
        --id "SN2020wnt" \\
        --output-collection "forced_phot/ref_catalog"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lsst.afw.table import SimpleCatalog, SimpleTable
from lsst.geom import SpherePoint, degrees


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create reference catalog for forced photometry"
    )
    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument(
        "--ra", type=float, required=True, help="Right ascension (decimal degrees)"
    )
    parser.add_argument(
        "--dec", type=float, required=True, help="Declination (decimal degrees)"
    )
    parser.add_argument(
        "--id", required=True, help="Object ID/name (used as source ID)"
    )
    parser.add_argument(
        "--output-collection",
        default="forced_phot/ref_catalog",
        help="Output collection name",
    )
    parser.add_argument(
        "--dataset-type",
        default="forced_src_ref",
        help="Dataset type name (default: forced_src_ref)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("Creating forced photometry reference catalog")
    print(f"  Repository: {args.repo}")
    print(f"  Target: {args.id}")
    print(f"  Position: RA={args.ra:.6f}°, Dec={args.dec:.6f}°")
    print(f"  Output collection: {args.output_collection}")

    # Create a simple catalog schema with coordinate fields
    # makeMinimalSchema() already includes coord_ra and coord_dec
    schema = SimpleTable.makeMinimalSchema()
    # Add object_id field
    schema.addField("object_id", type=str, size=64, doc="Object identifier")

    # Create catalog
    catalog = SimpleCatalog(schema)
    record = catalog.addNew()

    # Convert coordinates using LSST geom types
    coord = SpherePoint(args.ra * degrees, args.dec * degrees)
    record.setCoord(coord)
    record["object_id"] = args.id

    print("\nCatalog created with 1 source:")
    print(f"  coord_ra: {record['coord_ra'].asRadians():.6f} rad")
    print(f"  coord_dec: {record['coord_dec'].asRadians():.6f} rad")
    print(f"  object_id: {record['object_id']}")

    # Save catalog as FITS file for now
    # Butler ingestion of custom reference catalogs is complex and requires
    # proper dataset type definitions. For forced photometry, it's simpler to
    # use existing DIA source catalogs or manually register the dataset type.

    output_path = Path(args.output_collection).with_suffix(".fits")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    catalog.writeFits(str(output_path))

    print(f"\nReference catalog saved to: {output_path}")
    print("\nNOTE: For forced photometry, you have two options:")
    print("  1. Use DIA sources (default): The pipeline will automatically use")
    print("     goodSeeingDiff_diaSrc as the reference catalog")
    print("  2. Manually ingest this catalog into butler (advanced)")
    print("\nFor now, the simplest approach is to use option 1 with DIA sources.")


if __name__ == "__main__":
    main()
