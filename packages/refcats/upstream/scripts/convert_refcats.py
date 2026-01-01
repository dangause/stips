#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Convert pre-fetched Gaia DR3 and PS1 DR2 CSVs into tiled refcats
(using LSST's convertReferenceCatalog CLI), without touching Butler.

Typical flow:
  1) Fetch catalogs (gaia_fetch.py, ps1_fetch_mast.py)
  2) Run this script to convert both into tiles under data/
  3) Let run_full.sh ingest the tiles into your Butler repo

Examples
--------
Convert both (default CSV locations), date-stamped output dirs:
    python scripts/convert_refcats.py

Force re-convert only Gaia with a custom date:
    python scripts/convert_refcats.py --only gaia --refdate 20250911 --force

Notes
-----
- Output dirs are:
    data/gaia-refcat-<REFDATE>/
    data/ps1-refcat-<REFDATE>/
- The ingestion map files are:
    data/.../filename_to_htm.ecsv
- This script *does not* register/ingest
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def convert_one(
    name: str, out_base: Path, config: Path, source_csv: Path, force: bool
) -> Path:
    """
    Run convertReferenceCatalog for one catalog if needed.

    Returns
    -------
    Path : the path to filename_to_htm.ecsv produced by the conversion.
    """
    out_base.mkdir(parents=True, exist_ok=True)
    fmap = out_base / "filename_to_htm.ecsv"

    if fmap.exists() and not force:
        print(f"[{name}] Using existing map: {fmap}")
        return fmap

    if not source_csv.exists():
        raise SystemExit(f"[{name}] Missing input CSV: {source_csv}")

    print(f"[{name}] Converting → {out_base}")
    _run(
        [
            "convertReferenceCatalog",
            str(out_base),
            str(config),
            str(source_csv),
        ]
    )
    if not fmap.exists():
        raise SystemExit(f"[{name}] Expected map not found after conversion: {fmap}")
    return fmap


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Convert fetched Gaia/PS1 CSVs into tiled refcats."
    )
    ap.add_argument(
        "--out-root",
        default="data",
        help="Root directory for tiled outputs (default: data)",
    )
    ap.add_argument(
        "--refdate",
        default=None,
        help="YYYYMMDD for output dir names; default=UTC today",
    )
    ap.add_argument(
        "--force", action="store_true", help="Re-run conversion even if map exists"
    )
    ap.add_argument(
        "--only", choices=["gaia", "ps1"], default=None, help="Convert only one catalog"
    )

    # Input CSVs (produced by your fetchers)
    ap.add_argument(
        "--gaia-csv", default="./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv"
    )
    ap.add_argument("--ps1-csv", default="./data/ps1_all_cones/merged_ps1_cones.csv")

    # Configs
    ap.add_argument("--gaia-config", default="scripts/gaia_dr3_config.py")
    ap.add_argument("--ps1-config", default="scripts/ps1_config.py")
    return ap.parse_args()


def main():
    args = parse_args()

    # Resolve date-stamp
    if args.refdate is None:
        refdate = dt.datetime.utcnow().strftime("%Y%m%d")
    else:
        refdate = args.refdate

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    # Paths
    gaia_out = out_root / f"gaia-refcat-{refdate}"
    ps1_out = out_root / f"ps1-refcat-{refdate}"

    gaia_map = ps1_map = None

    # GAIA
    if args.only in (None, "gaia"):
        gaia_map = convert_one(
            "GAIA",
            gaia_out,
            Path(args.gaia_config),
            Path(args.gaia_csv),
            args.force,
        )

    # PS1
    if args.only in (None, "ps1"):
        ps1_map = convert_one(
            "PS1",
            ps1_out,
            Path(args.ps1_config),
            Path(args.ps1_csv),
            args.force,
        )

    print("\n=== Conversion complete ===")
    if gaia_map:
        print(f"[GAIA] map: {gaia_map}")
    if ps1_map:
        print(f"[PS1 ] map: {ps1_map}")

    # Print ingest hints (BUTLER happens later in run_full.sh)
    print("\nUse run_full.sh to ingest the latest maps into Butler.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
