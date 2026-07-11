#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Batch-fetch Gaia DR3 cones for LSST refcats (Nickel-friendly).

Inputs (choose one):
  1) --fits-dir PATH...     # one or more directories; use --fits-recursive to descend into subdirs
  2) --csv PATH             # CSV with columns: ra, dec (degrees)
  3) --butler REPO          # Butler repo, read visit.region centroids
  4) --ras/--decs           # comma-separated arrays of degrees

Key features:
  - TAP-uploaded table of cone centers → single query per batch (fallback to plain ADQL if server 500s).
  - Selects only needed Gaia DR3 columns (fast/light) incl. flux & flux_over_error for LSST converter.
  - Optional G-band magnitude cuts (--g-min/--g-max) to cap result volume.
  - Writes Parquet shards per batch + a single merged Parquet and CSV.
  - Robust Butler path (no visitSummary required): computes RA/Dec from visit.region centroid.
  - FITS mode supports multiple roots and recursive scanning; prefers CRVAL1/CRVAL2, otherwise WCS center.
  - Helpful debug with --debug-fits.

Examples:
  python scripts/gaia_fetch.py --butler /path/to/repo --instrument Nickel --radius-deg 0.09
  python scripts/gaia_fetch.py --fits-dir /top/dir --fits-recursive --radius-deg 0.12
  python scripts/gaia_fetch.py --csv ./data/nickel_pointings.csv --radius-deg 0.09
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
import pandas as pd

# --- External deps (install if missing) ---
# pip install astroquery astropy pandas pyarrow
from astroquery.gaia import Gaia

Gaia.MAIN_GAIA_TABLE = "gaiadr3.gaia_source"
Gaia.TIMEOUT = 600  # seconds

# ------------ Defaults ------------
RADIUS_DEG_DEFAULT = 0.09  # ~5.4' (6' FOV w/ margin)
BATCH_SIZE_DEFAULT = 200  # cones per TAP upload batch
SLEEP_BETWEEN_DEFAULT = 2.0  # seconds between TAP jobs
MAX_RETRIES_DEFAULT = 4

# Columns required by convertReferenceCatalog ConvertGaiaManager + some extras.
# Single source of truth lives in the importable library module.
from stips_refcats.gaia import COLS_SQL  # noqa: E402

# ----------------------------------


# ===========================
# Utilities
# ===========================


def uniq_pairs(
    ras: np.ndarray, decs: np.ndarray, round_ndp: int = 6
) -> Tuple[np.ndarray, np.ndarray]:
    arr = np.column_stack([ras, decs])
    uniq, _ = np.unique(np.round(arr, round_ndp), axis=0, return_inverse=True)
    return uniq[:, 0], uniq[:, 1]


def make_batches(
    ras: np.ndarray,
    decs: np.ndarray,
    rdeg: float,
    batch_size: int,
) -> Iterable[Tuple[int, int, np.ndarray, np.ndarray, np.ndarray]]:
    n = len(ras)
    for i in range(0, n, batch_size):
        j = min(i + batch_size, n)
        yield i, j, ras[i:j], decs[i:j], np.full(j - i, rdeg, dtype=float)


def _build_mag_clause(g_min: float | None, g_max: float | None) -> str:
    """Return ADQL clause limiting G magnitude, or empty string."""
    terms = []
    if g_min is not None:
        terms.append(f"g.phot_g_mean_mag >= {float(g_min):.3f}")
    if g_max is not None:
        terms.append(f"g.phot_g_mean_mag <= {float(g_max):.3f}")
    if terms:
        return " AND " + " AND ".join(terms)
    return ""


def _run_one_batch(
    df_upload: pd.DataFrame,
    cols_sql: str = COLS_SQL,
    max_retries: int = MAX_RETRIES_DEFAULT,
    g_min: float | None = None,
    g_max: float | None = None,
) -> pd.DataFrame:
    """
    Try TAP upload via temp CSV. If the server 500s, fall back to a plain
    ADQL WHERE with an OR of CIRCLE() predicates (no uploads).
    """
    import os
    import tempfile

    from requests import HTTPError

    mag_clause = _build_mag_clause(g_min, g_max)
    upload_name = "user_cones"

    query_upload = f"""
      SELECT {cols_sql}
      FROM {Gaia.MAIN_GAIA_TABLE} AS g
      JOIN TAP_UPLOAD.{upload_name} AS uc
        ON 1 = CONTAINS(
             POINT('ICRS', g.ra, g.dec),
             CIRCLE('ICRS', uc.ra, uc.dec, uc.rdeg)
           ){mag_clause}
    """

    # 1) Try upload path (older astroquery requires CSV on disk)
    last_err = None
    for attempt in range(1, max_retries + 1):
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False
            ) as tmp:
                df_upload.to_csv(tmp.name, index=False)
                tmp_path = tmp.name

            job = Gaia.launch_job_async(
                query=query_upload,
                upload_resource=tmp_path,
                upload_table_name=upload_name,
                dump_to_file=False,
                output_format="votable",
            )
            res = job.get_results()
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            df = res.to_pandas()
            df.columns = [c.lower() for c in df.columns]
            return df

        except Exception as e:
            last_err = e
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            # If it's an HTTP 500 (common), break to fallback immediately
            if isinstance(e, HTTPError) or "500" in str(e):
                break
            if attempt < max_retries:
                time.sleep(3 * attempt)
            else:
                break  # fall through to fallback

    # 2) Fallback: no upload — build OR-of-CIRCLE query
    #    Split into chunks so the WHERE clause isn’t too long.
    circles = [
        f"CONTAINS(POINT('ICRS', g.ra, g.dec), CIRCLE('ICRS', {ra:.8f}, {dec:.8f}, {r:.6f}))=1"
        for ra, dec, r in zip(
            df_upload["ra"].to_numpy(float),
            df_upload["dec"].to_numpy(float),
            df_upload["rdeg"].to_numpy(float),
        )
    ]

    chunk_size = 50  # conservative length
    frames = []
    for k in range(0, len(circles), chunk_size):
        where_core = " OR ".join(circles[k : k + chunk_size])
        # attach mag_clause (already starts with " AND ..." if non-empty)
        query_plain = f"SELECT {cols_sql} FROM {Gaia.MAIN_GAIA_TABLE} AS g WHERE ({where_core}){mag_clause}"
        got = None
        for attempt in range(1, max_retries + 1):
            try:
                job = Gaia.launch_job_async(
                    query=query_plain,
                    dump_to_file=False,
                    output_format="votable",
                )
                got = job.get_results().to_pandas()
                break
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(3 * attempt)
                else:
                    raise RuntimeError(
                        f"Plain ADQL fallback failed after {max_retries} attempts: {e}"
                    )
        got.columns = [c.lower() for c in got.columns]
        frames.append(got)

    if not frames:
        # if we land here, neither path worked
        raise RuntimeError(f"TAP upload failed with: {last_err}")

    return pd.concat(frames, ignore_index=True)


# ===========================
# Butler helpers (no visitSummary required)
# ===========================


def _unitvec_to_xyz(u) -> Tuple[float, float, float]:
    """Extract (x, y, z) from lsst.sphgeom.UnitVector3d (supports getX/getY/getZ or attributes)."""
    if hasattr(u, "getX"):
        x = u.getX()
        y = u.getY()
        z = u.getZ()
    else:
        x = getattr(u, "x", None)
        y = getattr(u, "y", None)
        z = getattr(u, "z", None)
        x = x() if callable(x) else x
        y = y() if callable(y) else y
        z = z() if callable(z) else z
    return float(x), float(y), float(z)


def _region_centroid_radec(region) -> Tuple[float, float]:
    """Compute (ra_deg, dec_deg) from a ConvexPolygon by averaging vertex unit vectors."""
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
    norm = np.linalg.norm(m)
    if not np.isfinite(norm) or norm == 0.0:
        raise RuntimeError("Degenerate region centroid (norm=0)")
    x, y, z = m / norm

    ra = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    dec = math.degrees(math.asin(z))
    return ra, dec


def _pointings_from_visit_regions(
    butler, instrument: str, include_calibs: bool, registry_where: str | None
):
    """Yield (ra_deg, dec_deg) from visit.region centroid; optional WHERE filter and calibration inclusion."""
    instrument_clause = f"instrument='{instrument}'"
    where_clause = (
        f"{instrument_clause} AND ({registry_where})"
        if registry_where
        else instrument_clause
    )

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
            continue


def _maybe_load_pointings_from_butler(
    repo: str,
    instrument: str = "Nickel",
    include_calibs: bool = False,
    registry_where: str | None = None,
) -> Iterable[Tuple[float, float]]:
    """Open repo and yield pointings from visit.region. Raises if none found."""
    from lsst.daf.butler import Butler

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
            "No visit.region pointings found in Butler registry. "
            "Try --include-calibs or adjust --registry-where."
        )


# ===========================
# FITS directory helpers
# ===========================


def _fits_paths(root: str | Path, recursive: bool = True) -> Iterable[Path]:
    """Yield FITS-like files under `root`. Supports multi-suffix and recursion."""
    root = Path(root)
    patterns = [
        "*.fits",
        "*.fit",
        "*.fts",
        "*.fits.gz",
        "*.fit.gz",
        "*.fts.gz",
        "*.fits.fz",
        "*.fit.fz",
        "*.fts.fz",
        "*.fz",
    ]
    it = root.rglob if recursive else root.glob
    for pat in patterns:
        for p in it(pat):
            if p.is_file():
                yield p


def _parse_ra_dec_from_header(hdr) -> tuple[float, float]:
    """Return (ra_deg, dec_deg). Prefer CRVAL1/CRVAL2; fall back to WCS or other header keys."""
    import astropy.units as u
    import numpy as np
    from astropy.coordinates import SkyCoord
    from astropy.wcs import WCS

    # 0) Fast path: CRVAL1/CRVAL2 (degrees)
    if "CRVAL1" in hdr and "CRVAL2" in hdr:
        try:
            ra = float(str(hdr["CRVAL1"]).strip())
            dec = float(str(hdr["CRVAL2"]).strip())
            if np.isfinite(ra) and np.isfinite(dec):
                ra = (ra + 360.0) % 360.0
                dec = max(min(dec, 90.0), -90.0)
                return ra, dec
        except Exception:
            pass

    # 1) WCS center
    try:
        w = WCS(hdr)
        nx = int(hdr.get("NAXIS1", 0))
        ny = int(hdr.get("NAXIS2", 0))
        if nx > 0 and ny > 0 and getattr(w, "has_celestial", False):
            sky = w.pixel_to_world(nx / 2.0, ny / 2.0)
            return float(sky.ra.deg), float(sky.dec.deg)
    except Exception:
        pass

    # 2) Other degree keys (normalized)
    def norm(k: str) -> str:  # RA_DEG -> RADEG
        return "".join(ch for ch in k.upper() if ch.isalnum())

    hk = {norm(k): v for k, v in hdr.items()}
    deg_pairs = [
        ("CRVAL1", "CRVAL2"),
        ("RADEG", "DECDEG"),
        ("RADEGREE", "DECDEGREE"),
        ("RA2000", "DEC2000"),
        ("RAJ2000", "DEJ2000"),
        ("RA_DEG", "DEC_DEG"),
    ]
    for rk, dk in deg_pairs:
        rk_n, dk_n = norm(rk), norm(dk)
        if rk_n in hk and dk_n in hk:
            try:
                ra = float(str(hk[rk_n]).strip())
                dec = float(str(hk[dk_n]).strip())
                ra = (ra + 360.0) % 360.0
                dec = max(min(dec, 90.0), -90.0)
                return ra, dec
            except Exception:
                pass

    # 3) Sexagesimal strings
    sexa_pairs = [
        ("OBJCTRA", "OBJCTDEC"),
        ("RA", "DEC"),
        ("TELRA", "TELDEC"),
        ("OBJRA", "OBJDEC"),
        ("RAHMS", "DECDMS"),
    ]
    for rk, dk in sexa_pairs:
        rk_n, dk_n = norm(rk), norm(dk)
        if rk_n in hk and dk_n in hk:
            val_r, val_d = str(hk[rk_n]).strip(), str(hk[dk_n]).strip()
            for units in ((u.hourangle, u.deg), (u.deg, u.deg)):
                try:
                    sc = SkyCoord(val_r, val_d, unit=units)
                    return float(sc.ra.deg), float(sc.dec.deg)
                except Exception:
                    continue

    raise RuntimeError("No usable WCS/RA/DEC found in FITS header")


def pointings_from_fits_dir(
    fits_dir: str | Path, recursive: bool = True, debug: bool = False
) -> Iterable[Tuple[float, float]]:
    """Yield (ra_deg, dec_deg) for each FITS with usable WCS/headers."""
    from astropy.io import fits

    total = good = have_crval = have_wcs = 0
    first_fail_reason = None
    first_fail_path = None

    for p in _fits_paths(fits_dir, recursive=recursive):
        total += 1
        try:
            # Avoid memmap/scaling issues; we do not need .data at all.
            with fits.open(p, memmap=False, do_not_scale_image_data=True) as hdul:
                # Pick first image-type HDU *without* touching .data.
                hdr = None
                for hdu in hdul:
                    # Prefer any image class header (Primary, Image, Compressed)
                    if isinstance(
                        hdu,
                        (
                            fits.PrimaryHDU,
                            fits.ImageHDU,
                            getattr(fits, "CompImageHDU", tuple()),
                        ),
                    ):
                        hdr = hdu.header
                        break
                if hdr is None:
                    hdr = hdul[0].header

                if "CRVAL1" in hdr and "CRVAL2" in hdr:
                    have_crval += 1
                try:
                    from astropy.wcs import WCS

                    w = WCS(hdr)
                    if getattr(w, "has_celestial", False):
                        have_wcs += 1
                except Exception:
                    pass

                ra, dec = _parse_ra_dec_from_header(hdr)
                good += 1
                if debug and good <= 3:
                    print(f"[fits] OK  {p}  -> RA={ra:.6f}, Dec={dec:.6f}")
                yield ra, dec
        except Exception as e:
            if first_fail_reason is None:
                first_fail_reason = str(e)
                first_fail_path = str(p)
            if debug:
                print(f"[fits] SKIP {p}  ({e})")
            continue

    if total > 0 and good == 0:
        msg = (
            f"Found {total} FITS under '{fits_dir}' (recursive={recursive}) "
            f"but none yielded RA/DEC. "
            f"Headers with CRVAL1/2: {have_crval}; with celestial WCS: {have_wcs}."
        )
        if first_fail_path:
            msg += f"\nExample failure: {first_fail_path}\nReason: {first_fail_reason}"
        raise SystemExit(msg)


# ===========================
# Input selection
# ===========================


def load_pointings(args) -> Tuple[np.ndarray, np.ndarray]:
    """Resolve RA/Dec inputs based on CLI args; returns degrees arrays."""
    # Priority: FITS dir(s) → CSV → Butler → ras/decs
    if args.fits_dir:
        roots = (
            args.fits_dir
            if isinstance(args.fits_dir, (list, tuple))
            else [args.fits_dir]
        )
        ras_list, decs_list = [], []
        scanned = 0
        for root in roots:
            for ra, dec in pointings_from_fits_dir(
                root, recursive=args.fits_recursive, debug=args.debug_fits
            ):
                ras_list.append(ra)
                decs_list.append(dec)
                scanned += 1
        if not ras_list:
            raise SystemExit(
                f"No usable RA/Dec extracted from FITS under: {', '.join(map(str, roots))} "
                f"(recursive={args.fits_recursive}). If these are raws without RA/DEC headers, use --butler or --csv."
            )
        return np.array(ras_list, float), np.array(decs_list, float)

    if args.csv and Path(args.csv).exists():
        df = pd.read_csv(args.csv)
        return df["ra"].to_numpy(float), df["dec"].to_numpy(float)

    if args.butler:
        ras, decs = zip(
            *_maybe_load_pointings_from_butler(
                args.butler,
                instrument=args.instrument,
                include_calibs=args.include_calibs,
                registry_where=args.registry_where,
            )
        )
        return np.array(ras, float), np.array(decs, float)

    if args.ras and args.decs:
        ras = np.array([float(x) for x in args.ras.split(",")], float)
        decs = np.array([float(x) for x in args.decs.split(",")], float)
        return ras, decs

    raise SystemExit(
        "No pointings provided. Use --fits-dir (with optional --fits-recursive), --csv, --butler, or --ras/--decs."
    )


# ===========================
# Main
# ===========================


def main():
    ap = argparse.ArgumentParser(description="Batch Gaia DR3 cones for LSST refcats.")
    # Inputs
    ap.add_argument(
        "--fits-dir",
        nargs="+",
        default=None,
        help="One or more directories containing FITS files. Use --fits-recursive to search subdirectories.",
    )
    ap.add_argument(
        "--fits-recursive",
        action="store_true",
        help="Recurse into subdirectories of each --fits-dir.",
    )
    ap.add_argument(
        "--debug-fits",
        action="store_true",
        help="Verbose logging for FITS discovery and header parsing.",
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
        help="Include calibration visits (flats/bias/darks) when reading from Butler",
    )

    # Direct arrays (fallback)
    ap.add_argument("--ras", default=None, help="Comma-separated RAs in degrees")
    ap.add_argument("--decs", default=None, help="Comma-separated Decs in degrees")

    # Query/IO params
    ap.add_argument(
        "--radius-deg",
        type=float,
        default=RADIUS_DEG_DEFAULT,
        help="Cone radius in degrees",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE_DEFAULT,
        help="Cones per TAP batch (upload table size)",
    )
    ap.add_argument(
        "--g-min",
        type=float,
        default=None,
        help="Minimum Gaia G mag (inclusive) for TAP query",
    )
    ap.add_argument(
        "--g-max",
        type=float,
        default=None,
        help="Maximum Gaia G mag (inclusive) for TAP query",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=SLEEP_BETWEEN_DEFAULT,
        help="Pause between TAP jobs (seconds)",
    )
    ap.add_argument(
        "--max-retries",
        type=int,
        default=MAX_RETRIES_DEFAULT,
        help="Max retries per TAP batch",
    )

    ap.add_argument(
        "--outdir",
        default="./data/gaia_dr3_cones_batched",
        help="Directory for Parquet shards",
    )
    ap.add_argument(
        "--merged-parquet",
        default="./data/gaia_dr3_all_cones/gaia_dr3_all_cones.parquet",
        help="Path for merged Parquet",
    )
    ap.add_argument(
        "--merged-csv",
        default="./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv",
        help="Path for merged CSV (for convertReferenceCatalog)",
    )
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing shard files if present",
    )

    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    Path(args.merged_parquet).parent.mkdir(parents=True, exist_ok=True)
    Path(args.merged_csv).parent.mkdir(parents=True, exist_ok=True)

    # Load/prepare pointings
    ras, decs = load_pointings(args)
    ras, decs = uniq_pairs(ras, decs)

    mag_desc = []
    if args.g_min is not None:
        mag_desc.append(f"G≥{args.g_min}")
    if args.g_max is not None:
        mag_desc.append(f"G≤{args.g_max}")
    mag_str = f" | mag cut: {' & '.join(mag_desc)}" if mag_desc else ""

    print(
        f"Unique pointings: {len(ras)} | radius={args.radius_deg:.5f} deg | batch={args.batch_size}{mag_str}"
    )

    # Process in batches
    shards: list[Path] = []
    pid0 = 0
    for k, (i, j, rr, dd, radii) in enumerate(
        make_batches(ras, decs, args.radius_deg, args.batch_size), start=1
    ):
        up = pd.DataFrame(
            {
                "ra": rr,
                "dec": dd,
                "rdeg": radii,
                "pid": np.arange(pid0, pid0 + len(rr), dtype=np.int64),
            }
        )
        pid0 += len(rr)

        shard_path = outdir / f"gaia_dr3_batch_{k:04d}.parquet"
        if shard_path.exists() and not args.overwrite:
            shards.append(shard_path)
            print(f"[{k}] SKIP existing shard: {shard_path.name}")
            continue

        df = _run_one_batch(
            up,
            cols_sql=COLS_SQL,
            max_retries=args.max_retries,
            g_min=args.g_min,
            g_max=args.g_max,
        )
        df.to_parquet(shard_path, index=False)
        shards.append(shard_path)
        print(f"[{k}] rows={len(df)} → {shard_path.name}")
        time.sleep(args.sleep)

    # Merge + dedup once
    if not shards:
        raise SystemExit("No shards created. Nothing to merge.")
    frames = [pd.read_parquet(p) for p in shards]
    merged = pd.concat(frames, ignore_index=True).drop_duplicates(subset="source_id")

    # Sanity check: columns expected by your gaia_dr3_config.py
    need = {
        "source_id",
        "ra",
        "dec",
        "ra_error",
        "dec_error",
        "parallax",
        "parallax_error",
        "pmra",
        "pmra_error",
        "pmdec",
        "pmdec_error",
        "ref_epoch",
        "phot_g_mean_mag",
        "phot_bp_mean_mag",
        "phot_rp_mean_mag",
        "phot_g_mean_flux",
        "phot_bp_mean_flux",
        "phot_rp_mean_flux",
        "phot_g_mean_flux_over_error",
        "phot_bp_mean_flux_over_error",
        "phot_rp_mean_flux_over_error",
    }
    missing = need - set(merged.columns)
    if missing:
        raise SystemExit(f"Missing expected columns: {sorted(missing)}")

    # Write outputs
    merged.to_parquet(args.merged_parquet, index=False)
    merged.to_csv(args.merged_csv, index=False)

    print(f"\nSaved merged Parquet: {args.merged_parquet}  (rows={len(merged)})")
    print(f"Saved merged CSV:     {args.merged_csv}      (rows={len(merged)})")
    print("Done.")


if __name__ == "__main__":
    main()
