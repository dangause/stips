#!/usr/bin/env python
"""Drop a night's intermediates, keeping only the end products.

KEEP  : forcedPhotRaDec (the campaign's end product), templates, refcats, skymap
DROP  : ingested raws, constructed calibs, processCcd outputs, DIA outputs

Raws are re-ingestable from RAW_PARENT_DIR and calibs are rebuildable, so the
only irreversible loss is compute time for that night.

Usage: prune_night.py REPO NIGHT [--dry-run]
"""

import sys

from lsst.daf.butler import Butler

KEEP_SUBSTRINGS = ("forcedPhotRaDec",)
DROP_PREFIXES = ("raw/", "cp/")
DROP_RUN_PARTS = ("/processCcd/", "/diff/", "/coadd/")


def targets(butler, night, prefix):
    """RUN collections belonging to `night` that are safe to drop."""
    out = []
    for c in butler.registry.queryCollections():
        if night not in c:
            continue
        if any(k in c for k in KEEP_SUBSTRINGS):
            continue
        if butler.registry.getCollectionType(c).name != "RUN":
            continue
        rest = c[len(prefix) + 1 :] if c.startswith(prefix + "/") else c
        if rest.startswith(DROP_PREFIXES) or any(p in c for p in DROP_RUN_PARTS):
            out.append(c)
    return sorted(out)


def main():
    repo, night = sys.argv[1], sys.argv[2]
    dry = "--dry-run" in sys.argv
    butler = Butler(repo, writeable=not dry)

    prefix = "Nickel"
    runs = targets(butler, night, prefix)
    if not runs:
        print(f"[prune {night}] nothing to drop")
        return

    print(f"[prune {night}] dropping {len(runs)} RUN collections:")
    for c in runs:
        print(f"    {c}")
    if dry:
        print("[prune] dry-run, nothing removed")
        return

    # unlink_from_chains so a CHAINED parent that still references the run does
    # not block removal; the parent is left behind empty and cleaned below.
    butler.removeRuns(runs, unstore=True, unlink_from_chains=True)

    # Sweep up chains/calibration collections for this night that are now empty.
    removed = 0
    for c in list(butler.registry.queryCollections()):
        if night not in c or any(k in c for k in KEEP_SUBSTRINGS):
            continue
        ctype = butler.registry.getCollectionType(c).name
        if ctype not in ("CHAINED", "CALIBRATION", "TAGGED"):
            continue
        try:
            if not list(butler.registry.queryDatasets(..., collections=c, limit=1)):
                butler.registry.removeCollection(c)
                removed += 1
        except Exception:
            pass
    print(f"[prune {night}] removed {len(runs)} runs, {removed} empty collections")


if __name__ == "__main__":
    main()
