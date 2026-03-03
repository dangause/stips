#!/usr/bin/env python
"""Repair MONSTER refcat shards that were written with astropy instead of AFW.

The RSP dump script used astropy.Table.write() which produces plain FITS
binary tables without the AFW SimpleCatalog schema header. This causes
the Butler to load only 3 fields (id, coord_ra, coord_dec) instead of
the full 82-field schema.

This script:
1. Reads a "good" shard (with correct AFW schema) to get the template schema
2. For each "bad" shard, reads the binary table with astropy (all 82 columns),
   creates a new SimpleCatalog with the correct schema, copies data, and overwrites.

Usage:
    source loadLSST.zsh && setup lsst_distrib
    python scripts/repair_refcat_shards.py
"""
import sys
from pathlib import Path

import lsst.afw.table as afwTable
import numpy as np
from astropy.table import Table

SHARD_DIR = Path(
    "~/Developer/lick/lsst/lsst_stack/stack/refcats/data/refcats/the_monster_20250219_afw"
).expanduser()


def find_bad_shards(shard_dir: Path) -> tuple[list[Path], Path | None]:
    """Find shards with minimal schema and a good shard for reference."""
    bad = []
    good_ref = None

    for fn in sorted(shard_dir.glob("refcat_htm7_*.fits")):
        cat = afwTable.SimpleCatalog.readFits(str(fn))
        nfields = len(cat.schema.getNames())
        if nfields <= 3:
            bad.append(fn)
        elif good_ref is None:
            good_ref = fn

    return bad, good_ref


def repair_shard(bad_path: Path, template_schema: afwTable.Schema) -> int:
    """Repair a single shard by rewriting with correct AFW schema.

    Returns the number of rows written.
    """
    # Read the binary table data with astropy (sees all columns)
    astropy_table = Table.read(str(bad_path))
    nrows = len(astropy_table)

    # Create new SimpleCatalog with the correct schema
    new_cat = afwTable.SimpleCatalog(template_schema)
    new_cat.resize(nrows)

    # Copy data column by column
    for name in template_schema.getNames():
        if name == "id":
            # IDs are in the afw catalog's internal id column
            if "id" in astropy_table.colnames:
                for i in range(nrows):
                    new_cat[i].setId(int(astropy_table["id"][i]))
            continue

        # Try to find matching column in astropy table
        # AFW uses snake_case, astropy preserves FITS column names
        if name in astropy_table.colnames:
            col_data = astropy_table[name]
            field = template_schema.find(name)
            field_type = field.field.getTypeString()

            if field_type == "Flag":
                for i in range(nrows):
                    new_cat[i].set(field.key, bool(col_data[i]))
            elif field_type in ("F", "D"):  # float/double
                arr = np.asarray(col_data, dtype=float)
                for i in range(nrows):
                    new_cat[i].set(field.key, float(arr[i]))
            elif field_type in ("I", "L"):  # int/long
                arr = np.asarray(col_data, dtype=int)
                for i in range(nrows):
                    new_cat[i].set(field.key, int(arr[i]))
            elif "Angle" in field_type:
                # coord_ra, coord_dec are stored as Angle in radians
                import lsst.geom as geom

                arr = np.asarray(col_data, dtype=float)
                for i in range(nrows):
                    new_cat[i].set(field.key, geom.Angle(float(arr[i]), geom.radians))
            else:
                # Try generic set
                for i in range(nrows):
                    new_cat[i].set(field.key, col_data[i])

    # Write back with AFW format
    new_cat.writeFits(str(bad_path))
    return nrows


def main():
    if not SHARD_DIR.exists():
        print(f"Shard directory not found: {SHARD_DIR}")
        sys.exit(1)

    print(f"Scanning {SHARD_DIR} for bad shards...")
    bad_shards, good_ref = find_bad_shards(SHARD_DIR)

    if not bad_shards:
        print("No bad shards found — all shards have correct AFW schema.")
        return

    if good_ref is None:
        print("ERROR: No good shard found to use as schema template!")
        sys.exit(1)

    print(f"Found {len(bad_shards)} bad shards, using {good_ref.name} as template")

    # Read template schema
    template_cat = afwTable.SimpleCatalog.readFits(str(good_ref))
    template_schema = template_cat.schema
    print(f"Template schema: {len(template_schema.getNames())} fields")

    # Repair each bad shard
    for fn in bad_shards:
        try:
            nrows = repair_shard(fn, template_schema)
            print(f"  Repaired {fn.name}: {nrows} rows")
        except Exception as e:
            print(f"  FAILED {fn.name}: {e}")

    # Verify
    print("\nVerification:")
    for fn in bad_shards:
        cat = afwTable.SimpleCatalog.readFits(str(fn))
        print(f"  {fn.name}: {len(cat)} rows, {len(cat.schema.getNames())} fields")


if __name__ == "__main__":
    main()
