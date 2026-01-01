# src/nickel_refcats/cli.py
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from .htm import (
    cones_to_htm as cones_to_htm_ids,
)  # or cones_to_htm7 if you kept that name
from .pointings import (
    normalize_where,
    pointings_from_butler,
    pointings_from_fits_dir,
    uniq_pairs,
)


def run_cones(ns: argparse.Namespace) -> None:
    # gather pointings
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
        raise SystemExit("Provide --fits-dir or --csv or --butler or --ras/--decs")

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
        f"Unique pointings: {len(cones)} | radius={ns.radius_arcmin:.2f} arcmin | HTM depth={ns.depth}"
    )
    print(f"Wrote {cones_path} and {htm_path} (n_htm={len(htm_ids)})")


def main() -> None:
    ap = argparse.ArgumentParser(prog="nickel-refcats")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # cones subcommand (defines ALL flags)
    cones = sub.add_parser(
        "cones", help="Make cones.csv + htm7_list.txt from Butler/FITS/CSV/arrays"
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
        "--radius-arcmin", type=float, default=6.0, help="Cone radius in arcmin"
    )
    cones.add_argument("--depth", type=int, default=7, help="HTM depth (default 7)")
    cones.add_argument("--outdir", default="./data/monster_plan")
    cones.set_defaults(func=run_cones)

    ns = ap.parse_args()
    ns.func(ns)
