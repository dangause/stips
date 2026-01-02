#!/usr/bin/env python3
"""Check if we have sufficient MONSTER refcat coverage for 2023ixf."""
import sys

import lsst.geom as geom
from lsst.meas.algorithms.htmIndexer import HtmIndexer

# 2023ixf coordinates
ra = 210.910542
dec = 54.311389

# Check various radii
radii_arcmin = [6.0, 10.0, 15.0, 20.0]

htm = HtmIndexer(depth=7)
center = geom.SpherePoint(ra * geom.degrees, dec * geom.degrees)

print(f"2023ixf field at RA={ra:.4f}, Dec={dec:.4f}")
print()

current_shards = {218512, 218515}

for radius_arcmin in radii_arcmin:
    shards, _ = htm.getShardIds(center, radius_arcmin * geom.degrees / 60.0)
    shards_set = set(shards)
    missing = sorted(shards_set - current_shards)

    print(f"Radius = {radius_arcmin:.1f} arcmin:")
    print(f"  Needed HTM shards: {sorted(shards)}")
    print(f"  Total: {len(shards)} shards")
    print(f"  Have: {sorted(current_shards & shards_set)}")
    print(f"  Missing: {missing if missing else 'None'}")
    print()

# Also check what a Nickel field of view needs (about 10.5 arcmin)
fov_arcmin = 10.5
shards, _ = htm.getShardIds(center, fov_arcmin * geom.degrees / 60.0)
shards_set = set(shards)
missing = sorted(shards_set - current_shards)

print(f"Nickel FOV ({fov_arcmin} arcmin radius):")
print(f"  Needed HTM shards: {sorted(shards)}")
print(f"  Have: {sorted(current_shards & shards_set)}")
print(f"  Missing: {missing if missing else 'None'}")

if missing:
    print()
    print(f"⚠️  You need to download {len(missing)} more HTM shards:")
    print(f"   {missing}")
    sys.exit(1)
else:
    print()
    print("✓ You have all needed HTM shards for this field")
