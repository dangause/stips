#!/usr/bin/env python
"""
Standalone RSP script: dump MONSTER reference catalog shards.

Upload this script + htm7_list.txt (or cones.csv) to RSP and run:

    python dump_monster_shards.py --htm7-file htm7_list.txt
    python dump_monster_shards.py --cones-file cones.csv
    python dump_monster_shards.py --htm7-ids 197129,197131,200464

Optionally skip already-downloaded shards:

    python dump_monster_shards.py --htm7-file htm7_list.txt \\
        --skip-existing existing_htm7_ids.txt

Outputs:
    data/the_monster_20250219/refcat_htm7_<ID>.fits   (per-shard FITS)
    the_monster_20250219_new.tgz                      (tarball for download)
"""
from __future__ import annotations

import argparse
import os
import sys
import tarfile


def parse_args():
    p = argparse.ArgumentParser(
        description="Dump MONSTER refcat shards from dp1 Butler on RSP"
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--htm7-file",
        help="File with comma- or newline-separated HTM7 IDs",
    )
    src.add_argument(
        "--cones-file",
        help="cones.csv (ra_deg,dec_deg,radius_deg) — computes HTM7s on the fly",
    )
    src.add_argument(
        "--htm7-ids",
        help="Comma-separated HTM7 IDs (e.g. 197129,197131)",
    )
    p.add_argument(
        "--skip-existing",
        help="File listing HTM7 IDs already downloaded (skip these)",
    )
    p.add_argument(
        "--collection",
        default="refcats/DM-49042/the_monster_20250219",
        help="dp1 Butler collection name",
    )
    p.add_argument(
        "--dataset-type",
        default="the_monster_20250219",
        help="dp1 dataset type name",
    )
    p.add_argument(
        "--outdir",
        default="data/the_monster_20250219",
        help="Output directory for FITS files",
    )
    p.add_argument(
        "--tarball",
        default="the_monster_20250219_new.tgz",
        help="Output tarball name",
    )
    p.add_argument(
        "--no-tar",
        action="store_true",
        help="Skip tarball creation (just dump FITS)",
    )
    return p.parse_args()


def read_htm7_ids_from_file(path: str) -> list[int]:
    """Read HTM7 IDs from a file (comma- or newline-separated)."""
    text = open(path).read().strip()
    # Handle both comma-separated and newline-separated
    ids = []
    for token in text.replace(",", "\n").split("\n"):
        token = token.strip()
        if token and not token.startswith("#"):
            ids.append(int(token))
    return sorted(set(ids))


def compute_htm7_from_cones(cones_path: str, depth: int = 7) -> list[int]:
    """Compute HTM7 trixel IDs from a cones.csv file."""
    import csv

    from lsst.geom import SpherePoint, degrees
    from lsst.meas.algorithms.htmIndexer import HtmIndexer

    htm = HtmIndexer(depth=depth)
    ids = set()
    with open(cones_path) as f:
        reader = csv.DictReader(row for row in f if not row.startswith("#"))
        for r in reader:
            ra, dec, rad = float(r["ra_deg"]), float(r["dec_deg"]), float(r["radius_deg"])
            center = SpherePoint(ra * degrees, dec * degrees)
            shards, _ = htm.getShardIds(center, rad * degrees)
            ids.update(int(t) for t in shards)
    return sorted(ids)


def main():
    args = parse_args()

    # Resolve HTM7 IDs
    if args.htm7_file:
        all_ids = read_htm7_ids_from_file(args.htm7_file)
        print(f"Read {len(all_ids)} HTM7 IDs from {args.htm7_file}")
    elif args.cones_file:
        all_ids = compute_htm7_from_cones(args.cones_file)
        print(f"Computed {len(all_ids)} HTM7 IDs from {args.cones_file}")
    else:
        all_ids = sorted(int(x.strip()) for x in args.htm7_ids.split(","))
        print(f"Using {len(all_ids)} HTM7 IDs from command line")

    # Filter out already-existing shards
    if args.skip_existing:
        skip = set(read_htm7_ids_from_file(args.skip_existing))
        before = len(all_ids)
        all_ids = [i for i in all_ids if i not in skip]
        print(f"Skipping {before - len(all_ids)} existing shards, {len(all_ids)} to dump")

    if not all_ids:
        print("Nothing to dump — all shards already exist.")
        return

    # Dump from dp1
    # IMPORTANT: Write with SimpleCatalog.writeFits() to preserve the AFW
    # schema header. Using astropy Table.write() creates plain FITS binary
    # tables that lose the AFW schema metadata, causing the Butler to load
    # only 3 fields (id, coord_ra, coord_dec) instead of the full schema.
    from lsst.daf.butler import Butler

    os.makedirs(args.outdir, exist_ok=True)
    butler = Butler("dp1", collections=args.collection)

    written = []
    for i, tid in enumerate(all_ids, 1):
        fn = os.path.join(args.outdir, f"refcat_htm7_{tid}.fits")
        try:
            cat = butler.get(args.dataset_type, dataId={"htm7": tid})
            cat.writeFits(fn)
            written.append(fn)
            print(f"  [{i}/{len(all_ids)}] {fn} — {len(cat)} sources")
        except Exception as e:
            print(f"  [{i}/{len(all_ids)}] SKIP htm7={tid}: {e}", file=sys.stderr)

    print(f"\nDumped {len(written)}/{len(all_ids)} shards to {args.outdir}/")

    # Create tarball
    if not args.no_tar and written:
        with tarfile.open(args.tarball, "w:gz") as tar:
            for fn in written:
                tar.add(fn, arcname=os.path.basename(fn))
        print(f"Tarball: {args.tarball} ({len(written)} files)")
        print(f"\nDownload {args.tarball} and run on local machine:")
        print(f"  tar xzf {args.tarball} -C /path/to/refcats/the_monster_20250219_afw/")
    elif not written:
        print("No shards written — no tarball created.")


if __name__ == "__main__":
    main()
