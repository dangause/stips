#!/usr/bin/env python
"""Compute MONSTER HTM7 shards needed for Landolt validation but missing locally.

For each star in landolt_catalog.csv, enumerate the HTM7 level-7 cells
overlapping a 0.5° circle around its position. Subtract the shards already
present in REFCAT_REPO/data/refcats/the_monster_20250219_afw/. Write the
remaining IDs (one per line) to missing_htm7_ids.txt, ready to upload to RSP
for use with dump_monster_shards.py --htm7-file.

Requires the LSST stack (lsst.sphgeom). Run via:

    bash -c 'source /Users/.../loadLSST.bash && setup lsst_distrib && \
      python scripts/config/landolt_validation/compute_missing_shards.py'
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import lsst.sphgeom as sg


# Adjust if REFCAT_REPO lives elsewhere.
SHARD_DIR = Path(
    "/Users/dangause/Developer/lick/lsst/lsst_stack/stack/refcats/data/refcats/the_monster_20250219_afw"
)

# 0.5° radius gives ~5x Nickel FOV (6.3'), generous for qgraph footprint matching.
SEARCH_RADIUS_DEG = 0.5


def main() -> None:
    here = Path(__file__).resolve().parent
    catalog = here / "landolt_catalog.csv"
    output = here / "missing_htm7_ids.txt"

    available = {
        int(f.split("_")[2].replace(".fits", ""))
        for f in os.listdir(SHARD_DIR)
        if f.startswith("refcat_htm7_") and f.endswith(".fits")
    }

    pix = sg.HtmPixelization(7)
    needed: set[int] = set()
    with open(catalog, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ra = float(row["ra_deg"])
            dec = float(row["dec_deg"])
            center = sg.UnitVector3d(sg.LonLat.fromDegrees(ra, dec))
            region = sg.Circle(center, sg.Angle.fromDegrees(SEARCH_RADIUS_DEG))
            for begin, end in pix.envelope(region):
                needed.update(range(begin, end))

    missing = sorted(needed - available)
    with open(output, "w") as fh:
        for shard_id in missing:
            fh.write(f"{shard_id}\n")

    print(f"Catalog stars:     {sum(1 for _ in open(catalog)) - 1}")
    print(f"Shards needed:     {len(needed)}")
    print(f"  Present locally: {len(needed & available)}")
    print(f"  Missing:         {len(missing)} -> {output}")


if __name__ == "__main__":
    main()
