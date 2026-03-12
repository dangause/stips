#!/usr/bin/env python
"""Recompute missing MONSTER refcat shards from Butler visit centroids.

Queries the extended_objects_repo Butler for all ingested visit centroids,
computes the HTM7 shard IDs needed to cover those positions, and reports
which shards are missing from the local MONSTER refcat directory.

Usage (run inside LSST stack environment):
    python scripts/utilities/recompute_missing_shards.py --repo /path/to/repo \\
        --shard-dir /path/to/refcats/the_monster_20250219_afw \\
        --plan-dir /path/to/monster_plan
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CONE_RADIUS_DEG = 6.0 / 60.0  # 6 arcmin in degrees
HTM_DEPTH = 7


def get_visit_centroids(repo: str) -> list[tuple[float, float]]:
    """Query Butler for all science visit centroids."""
    import math

    from lsst.daf.butler import Butler

    b = Butler(repo)
    centroids = []

    for v in b.registry.queryDimensionRecords("visit", where="instrument='Nickel'"):
        # Skip calibration frames
        obs_reason = getattr(v, "observation_reason", None)
        target_name = (getattr(v, "target_name", "") or "").lower()
        if obs_reason == "calibration" and any(
            k in target_name for k in ("flat", "bias", "dark")
        ):
            continue

        region = getattr(v, "region", None)
        if region is None:
            continue

        # Compute centroid from region vertices
        try:
            verts = list(region.getVertices())
            if not verts:
                continue
            import numpy as np

            xyz = np.array(
                [(float(vt.x()), float(vt.y()), float(vt.z())) for vt in verts],
                float,
            )
            m = xyz.mean(axis=0)
            m /= np.linalg.norm(m)
            x, y, z = m
            ra = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
            dec = math.degrees(math.asin(z))
            centroids.append((ra, dec))
        except Exception:
            continue

    return centroids


def compute_htm7_ids(
    centroids: list[tuple[float, float]], radius_deg: float, depth: int
) -> set[int]:
    """Compute all HTM7 shard IDs needed for cone searches around centroids."""
    import lsst.geom as geom
    from lsst.meas.algorithms.htmIndexer import HtmIndexer

    htm = HtmIndexer(depth=depth)
    ids: set[int] = set()

    for ra, dec in centroids:
        center = geom.SpherePoint(ra * geom.degrees, dec * geom.degrees)
        shards, _ = htm.getShardIds(center, radius_deg * geom.degrees)
        ids.update(shards)

    return ids


def get_existing_shard_ids(shard_dir: Path) -> set[int]:
    """Get HTM7 IDs of existing FITS shards on disk."""
    ids: set[int] = set()
    for fn in shard_dir.glob("refcat_htm7_*.fits"):
        m = re.search(r"refcat_htm7_(\d+)\.fits$", fn.name)
        if m:
            ids.add(int(m.group(1)))
    return ids


def main() -> None:
    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument(
        "--shard-dir", required=True, type=Path, help="MONSTER refcat shard directory"
    )
    parser.add_argument(
        "--plan-dir", required=True, type=Path, help="Output plan directory"
    )
    args = parser.parse_args()

    REPO = args.repo
    SHARD_DIR = args.shard_dir
    PLAN_DIR = args.plan_dir

    print(f"Butler repo: {REPO}")
    print(f"Shard dir:   {SHARD_DIR}")
    print()

    # Step 1: Get visit centroids from Butler
    print("Querying Butler for visit centroids...")
    centroids = get_visit_centroids(REPO)
    print(f"  Found {len(centroids)} science visit centroids")

    if not centroids:
        print("No visits found in Butler. Has raw data been ingested?")
        sys.exit(1)

    # Deduplicate by rounding to ~0.04 arcsec
    arr = np.array(centroids, float)
    uniq = np.unique(np.round(arr, 5), axis=0)
    centroids_deduped = [(float(r[0]), float(r[1])) for r in uniq]
    print(f"  Unique sky positions: {len(centroids_deduped)}")

    # Step 2: Compute needed HTM7 IDs
    print(
        f"\nComputing HTM7 shard IDs (radius={CONE_RADIUS_DEG*60:.1f} arcmin, depth={HTM_DEPTH})..."
    )
    needed_ids = compute_htm7_ids(centroids_deduped, CONE_RADIUS_DEG, HTM_DEPTH)
    print(f"  HTM7 shards needed: {len(needed_ids)}")

    # Step 3: Compare against existing shards
    existing_ids = get_existing_shard_ids(SHARD_DIR)
    print(f"  HTM7 shards on disk: {len(existing_ids)}")

    missing = sorted(needed_ids - existing_ids)
    extra = sorted(existing_ids - needed_ids)

    print(f"\n{'='*60}")
    print("COVERAGE SUMMARY")
    print(f"{'='*60}")
    print(f"  Needed:  {len(needed_ids)}")
    print(f"  Present: {len(needed_ids & existing_ids)}")
    print(f"  Missing: {len(missing)}")
    if extra:
        print(f"  Extra (not needed by current visits): {len(extra)}")

    if missing:
        print(f"\nMISSING HTM7 SHARD IDS ({len(missing)}):")
        print(",".join(str(i) for i in missing))

        # Write to plan directory
        PLAN_DIR.mkdir(parents=True, exist_ok=True)

        # Update missing_htm7_ids.txt
        missing_file = PLAN_DIR / "missing_htm7_ids.txt"
        missing_file.write_text(",".join(str(i) for i in missing) + "\n")
        print(f"\nWrote: {missing_file}")

        # Update full htm7_list.txt with all needed IDs
        htm_file = PLAN_DIR / "htm7_list.txt"
        htm_file.write_text(",".join(str(i) for i in sorted(needed_ids)) + "\n")
        print(f"Wrote: {htm_file}")

        # Write cones.csv for the RSP download workflow
        cones_file = PLAN_DIR / "cones.csv"
        with open(cones_file, "w") as f:
            f.write("ra_deg,dec_deg,radius_deg\n")
            for ra, dec in centroids_deduped:
                f.write(f"{ra},{dec},{CONE_RADIUS_DEG}\n")
        print(f"Wrote: {cones_file}")

        print("\nNext steps:")
        print("  1. Download missing shards from RSP using dump_monster_shards.py")
        print(f"  2. Run: nickel-refcats merge <tarball> --shard-dir {SHARD_DIR}")
        print(f"  3. Delete {SHARD_DIR}/filename_to_htm.ecsv to force rebuild")
        print("  4. Re-bootstrap the extended_objects_repo")
    else:
        print("\nAll needed shards are present! No downloads required.")


if __name__ == "__main__":
    main()
