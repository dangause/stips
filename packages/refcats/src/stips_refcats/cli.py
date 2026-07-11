# src/stips_refcats/cli.py
from __future__ import annotations

import argparse
import csv
import glob as globmod
import os
import re
import tarfile
from pathlib import Path

import numpy as np

from .htm import cones_to_htm as cones_to_htm_ids
from .pointings import (
    normalize_where,
    pointings_from_butler,
    pointings_from_fits_dir,
    pointings_from_pipeline_configs,
    uniq_pairs,
)

# ---------------------------------------------------------------------------
# cones subcommand
# ---------------------------------------------------------------------------


def _read_existing_cones(cones_path: Path) -> list[tuple[float, float, float]]:
    """Read existing cones.csv, skipping comment lines."""
    cones = []
    if not cones_path.exists():
        return cones
    with open(cones_path) as f:
        reader = csv.DictReader(row for row in f if not row.strip().startswith("#"))
        for r in reader:
            cones.append(
                (float(r["ra_deg"]), float(r["dec_deg"]), float(r["radius_deg"]))
            )
    return cones


def _cone_key(ra: float, dec: float, ndp: int = 5) -> tuple[float, float]:
    """Round to ndp decimals for deduplication (~0.04 arcsec at ndp=5)."""
    return (round(ra, ndp), round(dec, ndp))


def run_cones(ns: argparse.Namespace) -> None:
    # ----- scan-configs mode: read YAML pipeline configs -----
    if ns.scan_configs:
        config_paths = []
        for pattern in ns.scan_configs:
            config_paths.extend(globmod.glob(pattern, recursive=True))
        if not config_paths:
            raise SystemExit(f"No config files matched: {ns.scan_configs}")

        new_targets = list(pointings_from_pipeline_configs(config_paths))
        if not new_targets:
            raise SystemExit("No ra/dec found in any config file")

        outdir = Path(ns.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        cones_path = outdir / "cones.csv"
        htm_path = outdir / "htm7_list.txt"
        radius = ns.radius_arcmin / 60.0

        # Read existing cones for deduplication
        existing = _read_existing_cones(cones_path)
        existing_keys = {_cone_key(ra, dec) for ra, dec, _ in existing}

        # Filter to truly new targets
        added = []
        for ra, dec, cfg_path in new_targets:
            if _cone_key(ra, dec) not in existing_keys:
                added.append((ra, dec, cfg_path))
                existing_keys.add(_cone_key(ra, dec))

        if not added:
            print(f"All {len(new_targets)} targets already in {cones_path}")
            # Refresh htm7_list.txt if LSST stack is available
            try:
                all_cones = [(ra, dec, rad) for ra, dec, rad in existing]
                htm_ids = cones_to_htm_ids(all_cones, depth=ns.depth)
                htm_path.write_text(",".join(map(str, htm_ids)) + "\n")
                print(f"Refreshed {htm_path} (n_htm={len(htm_ids)})")
            except ImportError:
                print(f"(LSST stack not available — {htm_path.name} not refreshed)")
            return

        # Append new targets to cones.csv (preserves existing content + comments)
        with open(cones_path, "a") as f:
            for ra, dec, cfg_path in added:
                target_name = Path(cfg_path).parent.name
                f.write(f"# {target_name} (from {Path(cfg_path).name})\n")
                f.write(f"{ra},{dec},{radius}\n")

        for ra, dec, cfg_path in added:
            print(f"  + ({ra:.6f}, {dec:.6f}) from {cfg_path}")
        print(
            f"\nAdded {len(added)} new targets "
            f"({len(new_targets) - len(added)} already existed)"
        )

        # Regenerate htm7_list.txt from full cones.csv
        all_cones = _read_existing_cones(cones_path)
        try:
            htm_ids = cones_to_htm_ids(all_cones, depth=ns.depth)
            htm_path.write_text(",".join(map(str, htm_ids)) + "\n")
            print(f"Total cones: {len(all_cones)} | HTM7 trixels: {len(htm_ids)}")
            print(f"Updated {cones_path} and {htm_path}")
        except ImportError:
            print(f"Total cones: {len(all_cones)}")
            print(f"Updated {cones_path}")
            print(
                f"(LSST stack not available — run with LSST env to regenerate {htm_path.name})"
            )
        return

    # ----- existing input sources -----
    if ns.fits_dir:
        pts = list(
            pointings_from_fits_dir(
                ns.fits_dir,
                ns.fits_recursive,
                include_pattern=ns.fits_include,
                exclude_pattern=ns.fits_exclude,
            )
        )
        if not pts:
            raise SystemExit("No pointings from FITS")
        ras, decs = zip(*pts)
    elif ns.csv and Path(ns.csv).exists():
        import pandas as pd

        df = pd.read_csv(ns.csv)
        ras = df["ra"].to_numpy(float)
        decs = df["dec"].to_numpy(float)
    elif ns.butler:
        pts = list(
            pointings_from_butler(
                ns.butler,
                ns.instrument,
                ns.include_calibs,
                normalize_where(ns.registry_where),
            )
        )
        if not pts:
            raise SystemExit("No visits from Butler query")
        ras, decs = zip(*pts)
    elif ns.ras and ns.decs:
        ras = [float(x) for x in ns.ras.split(",")]
        decs = [float(x) for x in ns.decs.split(",")]
    else:
        raise SystemExit(
            "Provide --fits-dir or --csv or --butler or --ras/--decs or --scan-configs"
        )

    ras = np.asarray(ras, float)
    decs = np.asarray(decs, float)
    ras, decs = uniq_pairs(ras, decs)
    cones = [(float(r), float(d), ns.radius_arcmin / 60.0) for r, d in zip(ras, decs)]

    outdir = Path(ns.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cones_path = outdir / "cones.csv"
    htm_path = outdir / "htm7_list.txt"

    with open(cones_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ra_deg", "dec_deg", "radius_deg"])
        w.writerows(cones)

    htm_ids = cones_to_htm_ids(cones, depth=ns.depth)
    htm_path.write_text(",".join(map(str, htm_ids)) + "\n")

    print(
        f"Unique pointings: {len(cones)} | radius={ns.radius_arcmin:.2f} arcmin "
        f"| HTM depth={ns.depth}"
    )
    print(f"Wrote {cones_path} and {htm_path} (n_htm={len(htm_ids)})")


# ---------------------------------------------------------------------------
# merge subcommand
# ---------------------------------------------------------------------------

_DEFAULT_SHARD_DIR = os.path.expanduser(
    "~/Developer/lick/lsst/lsst_stack/stack/refcats/data/refcats/the_monster_20250219_afw"
)


def run_merge(ns: argparse.Namespace) -> None:
    tarball = Path(ns.tarball)
    shard_dir = Path(ns.shard_dir)

    if not tarball.exists():
        raise SystemExit(f"Tarball not found: {tarball}")
    if not shard_dir.exists():
        shard_dir.mkdir(parents=True, exist_ok=True)

    # Count existing shards
    existing = set()
    for fn in shard_dir.glob("refcat_htm7_*.fits"):
        m = re.search(r"refcat_htm7_(\d+)\.fits$", fn.name)
        if m:
            existing.add(int(m.group(1)))

    # Extract tarball
    added = []
    with tarfile.open(tarball, "r:*") as tar:
        for member in tar.getmembers():
            basename = os.path.basename(member.name)
            m = re.search(r"refcat_htm7_(\d+)\.fits$", basename)
            if not m:
                continue
            htm_id = int(m.group(1))
            dest = shard_dir / basename
            f = tar.extractfile(member)
            if f is None:
                continue
            dest.write_bytes(f.read())
            status = "updated" if htm_id in existing else "new"
            added.append((htm_id, status))

    if not added:
        print("No refcat_htm7_*.fits files found in tarball")
        return

    new_count = sum(1 for _, s in added if s == "new")
    updated_count = sum(1 for _, s in added if s == "updated")

    # Invalidate stale ECSV map (bootstrap regenerates it)
    ecsv_path = shard_dir / "filename_to_htm.ecsv"
    if ecsv_path.exists():
        ecsv_path.unlink()
        print(f"Removed stale {ecsv_path.name}")

    total = len(list(shard_dir.glob("refcat_htm7_*.fits")))

    for htm_id, status in sorted(added):
        print(f"  [{status}] refcat_htm7_{htm_id}.fits")
    print(f"\nMerged {len(added)} shards ({new_count} new, {updated_count} updated)")
    print(f"Total shards in {shard_dir.name}: {total}")
    print(
        "\nNext: re-run your pipelines — bootstrap will re-ingest all shards automatically"
    )


# ---------------------------------------------------------------------------
# status subcommand
# ---------------------------------------------------------------------------


def run_status(ns: argparse.Namespace) -> None:
    shard_dir = Path(ns.shard_dir)

    if not shard_dir.exists():
        print(f"Shard directory not found: {shard_dir}")
        return

    shards = sorted(shard_dir.glob("refcat_htm7_*.fits"))
    htm_ids = set()
    for fn in shards:
        m = re.search(r"refcat_htm7_(\d+)\.fits$", fn.name)
        if m:
            htm_ids.add(int(m.group(1)))

    ecsv_path = shard_dir / "filename_to_htm.ecsv"
    ecsv_status = (
        "present" if ecsv_path.exists() else "missing (will be rebuilt on bootstrap)"
    )

    plan_dir = shard_dir.parent.parent / "monster_plan"
    htm_path = plan_dir / "htm7_list.txt"

    needed_ids = set()
    if htm_path.exists():
        text = htm_path.read_text().strip()
        for token in text.replace(",", "\n").split("\n"):
            token = token.strip()
            if token:
                needed_ids.add(int(token))

    missing = sorted(needed_ids - htm_ids) if needed_ids else []

    print(f"Shard directory: {shard_dir}")
    print(f"  FITS shards:   {len(shards)}")
    print(f"  ECSV map:      {ecsv_status}")
    if needed_ids:
        print(f"  HTM7 needed:   {len(needed_ids)} (from {htm_path})")
        print(f"  HTM7 present:  {len(htm_ids & needed_ids)}/{len(needed_ids)}")
        if missing:
            print(f"  MISSING:       {missing}")
    else:
        print(f"  HTM7 list:     not found at {htm_path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(prog="stips-refcats")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # cones subcommand
    cones = sub.add_parser(
        "cones", help="Make cones.csv + htm7_list.txt from Butler/FITS/CSV/configs"
    )
    cones.add_argument(
        "--fits-dir",
        default=None,
        help="Directory with FITS files to scan for WCS centers",
    )
    cones.add_argument(
        "--fits-recursive", action="store_true", help="Recurse into subdirectories"
    )
    cones.add_argument(
        "--fits-include", default=None, help="Regex: only include FITS paths that match"
    )
    cones.add_argument(
        "--fits-exclude", default=None, help="Regex: exclude FITS paths that match"
    )
    cones.add_argument(
        "--save-used-fits", default=None, help="(reserved) write list of files used"
    )
    cones.add_argument("--csv", default=None, help="CSV with columns ra,dec (degrees)")
    cones.add_argument(
        "--butler",
        default=None,
        help="Local Butler repo to read visit.region centroids",
    )
    cones.add_argument("--instrument", default="Nickel")
    cones.add_argument("--registry-where", default=None)
    cones.add_argument("--include-calibs", action="store_true")
    cones.add_argument("--ras", default=None)
    cones.add_argument("--decs", default=None)
    cones.add_argument(
        "--scan-configs",
        nargs="+",
        metavar="GLOB",
        help="Pipeline YAML config glob(s) to scan for ra/dec",
    )
    cones.add_argument(
        "--radius-arcmin", type=float, default=6.0, help="Cone radius in arcmin"
    )
    cones.add_argument("--depth", type=int, default=7, help="HTM depth (default 7)")
    cones.add_argument("--outdir", default="./data/monster_plan")
    cones.set_defaults(func=run_cones)

    # merge subcommand
    merge = sub.add_parser(
        "merge", help="Merge new MONSTER shards from tarball into shard directory"
    )
    merge.add_argument("tarball", help="Path to tarball with refcat_htm7_*.fits files")
    merge.add_argument(
        "--shard-dir",
        default=_DEFAULT_SHARD_DIR,
        help=f"Target shard directory (default: {_DEFAULT_SHARD_DIR})",
    )
    merge.set_defaults(func=run_merge)

    # status subcommand
    status = sub.add_parser("status", help="Show refcat shard coverage status")
    status.add_argument(
        "--shard-dir",
        default=_DEFAULT_SHARD_DIR,
        help=f"Shard directory (default: {_DEFAULT_SHARD_DIR})",
    )
    status.set_defaults(func=run_status)

    ns = ap.parse_args()
    ns.func(ns)
