#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fetch Pan-STARRS1 DR2 'mean' objects for many cones using astroquery.mast.

Inputs (choose one):
  --fits-dir PATH        # scan FITS, use WCS headers or CRVAL1/2 for RA/Dec
  --csv PATH             # CSV with columns: ra, dec (degrees)
  --butler REPO          # Butler repo (visit.region centroid pointings)
  --ras/--decs           # comma-separated arrays (degrees)

Outputs:
  Per-batch CSV shards + merged Parquet/CSV:
    ./data/ps1_all_cones/merged_ps1_cones.parquet
    ./data/ps1_all_cones/merged_ps1_cones.csv

Requires:
  pip install astroquery astropy pandas pyarrow
"""

from __future__ import annotations

import argparse
import math
import re
import time
from pathlib import Path
from typing import Iterable, Optional, Tuple

import astropy.units as u
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord

# astroquery.mast + astropy
from astroquery.mast import Catalogs

# ------------ Defaults ------------
RADIUS_ARCMIN_DEFAULT = 5.4  # ≈0.09 deg (Nickel ~6' FOV + margin)
BATCH_SIZE_DEFAULT = 50  # cones per shard file
SLEEP_BETWEEN_DEFAULT = 0.5  # pause between HTTP calls (throttle)
MAX_RETRIES_DEFAULT = 3

# Columns needed by convert config (and useful extras)
PS1_COLUMNS = [
    "objID",
    "raMean",
    "decMean",
    "raMeanErr",
    "decMeanErr",
    "epochMean",
    "gMeanPSFMag",
    "rMeanPSFMag",
    "iMeanPSFMag",
    "zMeanPSFMag",
    "yMeanPSFMag",
    "gMeanPSFMagErr",
    "rMeanPSFMagErr",
    "iMeanPSFMagErr",
    "zMeanPSFMagErr",
    "yMeanPSFMagErr",
    "nDetections",
    "ng",
    "nr",
    "ni",
    "nz",
    "ny",
    "qualityFlag",
    "objInfoFlag",
]
# ----------------------------------


# ===========================
# Shared pointing helpers (Butler/FITS/CSV/arrays)
# ===========================


def uniq_pairs(
    ras: np.ndarray, decs: np.ndarray, round_ndp: int = 6
) -> Tuple[np.ndarray, np.ndarray]:
    arr = np.column_stack([ras, decs])
    uniq, _ = np.unique(np.round(arr, round_ndp), axis=0, return_inverse=True)
    return uniq[:, 0], uniq[:, 1]


def _unitvec_to_xyz(u) -> Tuple[float, float, float]:
    if hasattr(u, "getX"):
        return float(u.getX()), float(u.getY()), float(u.getZ())
    x = getattr(u, "x", None)
    x = x() if callable(x) else x
    y = getattr(u, "y", None)
    y = y() if callable(y) else y
    z = getattr(u, "z", None)
    z = z() if callable(z) else z
    return float(x), float(y), float(z)


def _region_centroid_radec(region) -> Tuple[float, float]:
    if hasattr(region, "getVertices"):
        verts = list(region.getVertices())
    elif hasattr(region, "getVerticesIter"):
        verts = list(region.getVerticesIter())
    else:
        raise RuntimeError("ConvexPolygon region has no getVertices*()")
    if not verts:
        raise RuntimeError("ConvexPolygon has no vertices")
    xyz = np.array([_unitvec_to_xyz(v) for v in verts], dtype=float)
    m = xyz.mean(axis=0)
    m /= np.linalg.norm(m)
    x, y, z = m
    ra = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    dec = math.degrees(math.asin(z))
    return ra, dec


def _normalize_where(registry_where: str | None) -> str | None:
    """Auto-prefix common visit fields if user omitted 'visit.'"""
    if not registry_where:
        return None
    fields = (
        "observation_reason",
        "physical_filter",
        "day_obs",
        "target_name",
        "science_program",
    )
    out = registry_where
    for f in fields:
        out = re.sub(rf"(?<!\.)\b{f}\b", f"visit.{f}", out)
    return out


def _pointings_from_visit_regions(
    butler, instrument: str, include_calibs: bool, registry_where: str | None
):
    """Yield (ra_deg, dec_deg) from visit.region centroid; optional WHERE and calibration inclusion."""
    instrument_clause = f"instrument='{instrument}'"
    if registry_where:
        where_clause = f"{instrument_clause} AND ({registry_where})"
    else:
        where_clause = instrument_clause

    recs = butler.registry.queryDimensionRecords("visit", where=where_clause)
    for v in recs:
        if not include_calibs:
            if getattr(v, "observation_reason", None) == "calibration":
                continue
            tn = (getattr(v, "target_name", "") or "").lower()
            if any(k in tn for k in ("flat", "bias", "dark")):
                continue
        region = getattr(v, "region", None)
        if region is None:
            continue
        try:
            yield _region_centroid_radec(region)
        except Exception:
            continue  # skip pathological regions


def _maybe_load_pointings_from_butler(
    repo: str,
    instrument: str = "Nickel",
    include_calibs: bool = False,
    registry_where: str | None = None,
) -> Iterable[Tuple[float, float]]:
    try:
        from lsst.daf.butler import Butler
    except ModuleNotFoundError as e:
        if getattr(e, "name", "") == "deprecated":
            raise SystemExit(
                "Missing dependency: install the PyPI package 'Deprecated' "
                "(e.g., `conda install -c conda-forge deprecated` or `pip install Deprecated`)."
            )
        raise
    b = Butler(repo)
    got = False
    for tup in _pointings_from_visit_regions(
        b,
        instrument=instrument,
        include_calibs=include_calibs,
        registry_where=registry_where,
    ):
        got = True
        yield tup
    if not got:
        raise RuntimeError(
            "No visit.region pointings found. Try --include-calibs or tweak --registry-where."
        )


# -------- FITS helpers (recursive scan, robust CRVAL1/2 and WCS) --------


def _fits_paths(root: str | Path, recursive: bool) -> Iterable[Path]:
    root = Path(root)
    exts = (".fits", ".fit", ".fz", ".fits.fz")
    it = root.rglob("*") if recursive else root.glob("**/*")
    for p in sorted(it):
        low = str(p).lower()
        if p.is_file() and (
            p.suffix.lower() in exts or any(low.endswith(e) for e in exts)
        ):
            yield p


def _parse_ra_dec_from_header(hdr) -> Tuple[float, float]:
    """Return (ra_deg, dec_deg) using WCS center if possible, else CRVAL1/2, else RA/DEC strings."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astropy.wcs import WCS

    # 1) WCS center
    try:
        w = WCS(hdr)
        nx = int(hdr.get("NAXIS1", 0))
        ny = int(hdr.get("NAXIS2", 0))
        if nx > 0 and ny > 0 and w.has_celestial:
            sky = w.pixel_to_world(nx / 2.0, ny / 2.0)
            return float(sky.ra.deg), float(sky.dec.deg)
    except Exception:
        pass

    # 2) CRVAL1/CRVAL2 (degrees)
    if "CRVAL1" in hdr and "CRVAL2" in hdr:
        try:
            return float(hdr["CRVAL1"]), float(hdr["CRVAL2"])
        except Exception:
            pass

    # 3) Sexagesimal strings
    for rkey, dkey in [("OBJCTRA", "OBJCTDEC"), ("RA", "DEC")]:
        if rkey in hdr and dkey in hdr:
            val_r = hdr[rkey]
            val_d = hdr[dkey]
            # Try hourangle/degrees then degrees/degrees
            try:
                sc = SkyCoord(val_r, val_d, unit=(u.hourangle, u.deg))
                return float(sc.ra.deg), float(sc.dec.deg)
            except Exception:
                try:
                    sc = SkyCoord(val_r, val_d, unit=(u.deg, u.deg))
                    return float(sc.ra.deg), float(sc.dec.deg)
                except Exception:
                    pass

    raise RuntimeError("No usable WCS/RA/DEC found in FITS header")


def pointings_from_fits_dir(
    fits_dir: str | Path,
    recursive: bool,
    debug: bool = False,
) -> Iterable[Tuple[float, float]]:
    """Yield (ra_deg, dec_deg) for each FITS file with usable WCS/headers."""
    from astropy.io import fits

    total = 0
    used_wcs = 0
    used_crval = 0
    failures: list[tuple[Path, str]] = []

    for p in _fits_paths(fits_dir, recursive=recursive):
        total += 1
        try:
            # Some Nickel files include BZERO/BSCALE that break memmap; open with memmap=False.
            with fits.open(p, memmap=False) as hdul:
                hdr = None
                # prefer first image HDU with data
                for hdu in hdul:
                    if getattr(hdu, "data", None) is not None:
                        hdr = hdu.header
                        break
                if hdr is None:
                    hdr = hdul[0].header

                # Quick probe of which path succeeded (for stats)
                try:
                    from astropy.wcs import WCS

                    w = WCS(hdr)
                    nx = int(hdr.get("NAXIS1", 0))
                    ny = int(hdr.get("NAXIS2", 0))
                    if nx > 0 and ny > 0 and w.has_celestial:
                        sky = w.pixel_to_world(nx / 2.0, ny / 2.0)
                        used_wcs += 1
                        yield float(sky.ra.deg), float(sky.dec.deg)
                        continue
                except Exception:
                    pass

                if "CRVAL1" in hdr and "CRVAL2" in hdr:
                    try:
                        ra = float(hdr["CRVAL1"])
                        dec = float(hdr["CRVAL2"])
                        used_crval += 1
                        yield ra, dec
                        continue
                    except Exception:
                        pass

                # Final attempt uses sexagesimal strings inside parser; if that fails, we record failure.
                ra, dec = _parse_ra_dec_from_header(hdr)  # will raise on failure
                yield ra, dec

        except Exception as e:
            if debug:
                failures.append((p, str(e)))
            continue

    if total == 0:
        print(f"No FITS found under: {fits_dir} (recursive={recursive})")
    elif used_wcs + used_crval == 0:
        msg = (
            f"Found {total} FITS under '{fits_dir}' (recursive={recursive}) "
            f"but none yielded RA/DEC. Headers with CRVAL1/2: {used_crval}; with celestial WCS: {used_wcs}."
        )
        if failures:
            samp = failures[0]
            msg += f"\nExample failure: {samp[0]}\nReason: {samp[1]}"
        print(msg)


# ===========================
# PS1 via astroquery.mast
# ===========================


def _fetch_one_cone(
    ra: float, dec: float, r_arcmin: float, sleep: float, max_retries: int
) -> pd.DataFrame:
    coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            tab = Catalogs.query_region(
                coordinates=coord,
                radius=r_arcmin * u.arcmin,
                catalog="Panstarrs",
                data_release="dr2",
                table="mean",
                columns=PS1_COLUMNS,
                pagesize=50000,
            )
            return tab.to_pandas()
        except Exception as e:
            last_err = e
            if attempt == max_retries:
                raise
            time.sleep(sleep * attempt)
    raise RuntimeError(f"PS1 query failed: {last_err}")


# ===========================
# Main
# ===========================


def main():
    ap = argparse.ArgumentParser(
        description="PS1 DR2 (mean) cones via astroquery.mast, batched."
    )
    # Inputs
    ap.add_argument(
        "--fits-dir",
        default=None,
        help="Directory of FITS files to read pointings from",
    )
    ap.add_argument(
        "--fits-recursive",
        action="store_true",
        help="Recurse into subdirectories when scanning FITS",
    )
    ap.add_argument(
        "--debug-fits",
        action="store_true",
        help="Print a summary if FITS headers cannot provide RA/DEC",
    )
    ap.add_argument("--csv", default=None, help="CSV with columns ra,dec (degrees)")
    ap.add_argument(
        "--butler", default=None, help="Butler repo to read visit.region pointings"
    )
    ap.add_argument(
        "--instrument",
        default="Nickel",
        help="Instrument name in the Butler repo (default: Nickel)",
    )
    ap.add_argument(
        "--registry-where",
        default=None,
        help="Extra WHERE for registry (SQL-like), e.g. \"physical_filter = 'I' AND day_obs>=20240601\"",
    )
    ap.add_argument(
        "--include-calibs",
        action="store_true",
        help="Include calibration visits when reading from Butler",
    )
    # Arrays
    ap.add_argument("--ras", default=None, help="Comma-separated RAs in degrees")
    ap.add_argument("--decs", default=None, help="Comma-separated Decs in degrees")
    # Mag limits (client-side)
    ap.add_argument(
        "--mag-band",
        choices=["g", "r", "i", "z", "y"],
        default="r",
        help="PS1 band for mag cut (MeanPSFMag)",
    )
    ap.add_argument("--mag-min", type=float, default=12.0, help="Bright cut (mag)")
    ap.add_argument("--mag-max", type=float, default=20.5, help="Faint cut (mag)")
    # Query/IO
    ap.add_argument(
        "--radius-arcmin",
        type=float,
        default=RADIUS_ARCMIN_DEFAULT,
        help="Cone radius in arcmin",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE_DEFAULT,
        help="Cones per shard file",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=SLEEP_BETWEEN_DEFAULT,
        help="Pause between HTTP requests (s)",
    )
    ap.add_argument(
        "--max-retries",
        type=int,
        default=MAX_RETRIES_DEFAULT,
        help="Max retries per cone",
    )
    ap.add_argument(
        "--outdir",
        default="./data/ps1_cones_batched",
        help="Directory for per-batch CSVs",
    )
    ap.add_argument(
        "--merged-parquet",
        default="./data/ps1_all_cones/merged_ps1_cones.parquet",
        help="Path for merged Parquet",
    )
    ap.add_argument(
        "--merged-csv",
        default="./data/ps1_all_cones/merged_ps1_cones.csv",
        help="Path for merged CSV",
    )
    ap.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing shard files"
    )

    args = ap.parse_args()
    args.registry_where = _normalize_where(args.registry_where)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    Path(args.merged_parquet).parent.mkdir(parents=True, exist_ok=True)
    Path(args.merged_csv).parent.mkdir(parents=True, exist_ok=True)

    # Resolve pointings
    if args.fits_dir:
        pts = list(
            pointings_from_fits_dir(
                args.fits_dir, recursive=args.fits_recursive, debug=args.debug_fits
            )
        )
        if not pts:
            raise SystemExit("No pointings could be derived from FITS headers.")
        ras, decs = zip(*pts)
        ras = np.array(ras, float)
        decs = np.array(decs, float)
    elif args.csv and Path(args.csv).exists():
        df = pd.read_csv(args.csv)
        ras = df["ra"].to_numpy(float)
        decs = df["dec"].to_numpy(float)
    elif args.butler:
        ras, decs = zip(
            *_maybe_load_pointings_from_butler(
                args.butler,
                instrument=args.instrument,
                include_calibs=args.include_calibs,
                registry_where=args.registry_where,
            )
        )
        ras = np.array(ras, float)
        decs = np.array(decs, float)
    elif args.ras and args.decs:
        ras = np.array([float(x) for x in args.ras.split(",")], float)
        decs = np.array([float(x) for x in args.decs.split(",")], float)
    else:
        raise SystemExit(
            "No pointings provided. Use --fits-dir, --csv, --butler, or --ras/--decs."
        )

    ras, decs = uniq_pairs(ras, decs)
    print(
        f"Unique pointings: {len(ras)} | radius={args.radius_arcmin:.2f} arcmin | batch={args.batch_size}"
    )

    # Loop by batches; one HTTP call per cone
    shards: list[Path] = []
    n = len(ras)
    mcol = f"{args.mag_band}MeanPSFMag"
    for k, i0 in enumerate(range(0, n, args.batch_size), start=1):
        i1 = min(i0 + args.batch_size, n)
        rr, dd = ras[i0:i1], decs[i0:i1]
        outfile = outdir / f"ps1_batch_{k:04d}.csv"
        if outfile.exists() and not args.overwrite:
            print(f"[{k}] SKIP existing shard: {outfile.name}")
            shards.append(outfile)
            continue

        frames = []
        for j, (ra, dec) in enumerate(zip(rr, dd), start=1):
            print(f"[{k}] ({j}/{len(rr)}) RA={ra:.6f}, Dec={dec:.6f}")
            df = _fetch_one_cone(
                ra, dec, args.radius_arcmin, args.sleep, args.max_retries
            )

            # Ensure expected columns exist (add missing as NaN so convert won't crash)
            for col in PS1_COLUMNS:
                if col not in df.columns:
                    df[col] = np.nan

            # Client-side mag cut
            if mcol in df.columns:
                df = df[df[mcol].between(args.mag_min, args.mag_max, inclusive="both")]
            else:
                # If the mag column is missing, drop all rows for safety
                df = df.iloc[0:0]

            frames.append(df)
            time.sleep(args.sleep)

        df_batch = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=PS1_COLUMNS)
        )
        # Keep only the columns we care about (order-stable)
        df_batch = df_batch.reindex(columns=PS1_COLUMNS)
        df_batch.to_csv(outfile, index=False)
        shards.append(outfile)
        print(f"[{k}] rows={len(df_batch)} → {outfile.name}")

    if not shards:
        raise SystemExit("No shards created. Nothing to merge.")

    # Merge + dedup
    frames = [pd.read_csv(p) for p in shards]
    merged = pd.concat(frames, ignore_index=True).drop_duplicates(subset="objID")

    # Ensure required columns exist
    for col in PS1_COLUMNS:
        if col not in merged.columns:
            merged[col] = np.nan
    merged = merged.reindex(columns=PS1_COLUMNS)

    merged.to_parquet(args.merged_parquet, index=False)
    merged.to_csv(args.merged_csv, index=False)

    print(f"\nSaved merged Parquet: {args.merged_parquet}  (rows={len(merged)})")
    print(f"Saved merged CSV:     {args.merged_csv}      (rows={len(merged)})")
    print("Done.")


if __name__ == "__main__":
    main()
