#!/usr/bin/env python
"""Re-derive Landolt astrometric residuals with rigorous proper-motion correction.

Pipeline:
  1. Query Gaia DR3 once per Landolt standard → (ra, dec, pmra, pmdec, ref_epoch).
  2. For each (visit, star) row in landolt_validation_4nights.csv:
     a. Read MJD from preliminary_visit_summary FITS for that visit.
     b. Compute PM-corrected Gaia position at the observation MJD using
        Δ_RA  = pmra  · Δt / cos(dec)   [proper handling of cos(dec) factor]
        Δ_Dec = pmdec · Δt
     c. Load the matching single_visit_star_unstandardized parquet for the
        same (night, run-timestamp, band, visit).
     d. Find the LSST-detected source nearest the PM-corrected Gaia position
        (within 2″) and record the vector residual
        Δα_mas = (LSST_RA − Gaia_RA_pm) · cos(dec) · 3.6e6
        Δδ_mas = (LSST_Dec − Gaia_Dec_pm) · 3.6e6
        and total |Δ| via the haversine separation.

Output: analysis/landolt_pm_corrected.csv with columns
  star, night, visit, band,
  obs_mjd, obs_epoch, dt_yr,
  gaia_ra_J2016, gaia_dec_J2016, pmra_mas_yr, pmdec_mas_yr, gaia_sep_arcsec_J2000,
  pm_corrected_ra_deg, pm_corrected_dec_deg,
  lsst_ra_deg, lsst_dec_deg,
  delta_ra_mas, delta_dec_mas, residual_mas,
  raw_match_dist_mas

Re-running the validation match against the *PM-corrected* catalog position
(instead of the J2000.0 Landolt position) removes the systematic per-star
offset and exposes the true LSST astrometric residual.
"""

from __future__ import annotations

import csv
import glob
import os
import warnings
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from astropy.io import fits
from astropy.time import Time
from astroquery.gaia import Gaia

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_CSV = REPO_ROOT / "analysis" / "landolt_validation_4nights.csv"
OUT_CSV = REPO_ROOT / "analysis" / "landolt_pm_corrected.csv"
LANDOLT_CATALOG = (
    REPO_ROOT / "scripts" / "config" / "landolt_validation" / "landolt_catalog.csv"
)
LANDOLT_REPO = Path(
    "/Users/dangause/Developer/lick/lsst/data/nickel/landolt_validation_repo"
)

GAIA_CONE_RADIUS_ARCSEC = 6.0  # generous enough for high-PM stars over ~22 yr
RE_MATCH_RADIUS_ARCSEC = 2.0  # tighter once we've PM-corrected
RAW_VALIDATION_MATCH_RADIUS_ARCSEC = 10.0  # what validate_landolt.py used


# ---------------------------------------------------------------------------
# Gaia lookup (once per star)
# ---------------------------------------------------------------------------


def query_gaia_for_landolt(ra: float, dec: float, radius_arcsec: float) -> dict | None:
    """Cone-search Gaia DR3 and return the brightest source within radius.

    Returns a dict with Gaia DR3 fields, or None if no match found.
    """
    job = Gaia.launch_job(
        f"""
        SELECT TOP 1 source_id, ra, dec, pmra, pmdec, ref_epoch, phot_g_mean_mag,
            DISTANCE(POINT('ICRS', {ra}, {dec}),
                     POINT('ICRS', ra, dec)) * 3600 AS sep_arcsec
        FROM gaiadr3.gaia_source
        WHERE 1 = CONTAINS(POINT('ICRS', ra, dec),
                           CIRCLE('ICRS', {ra}, {dec}, {radius_arcsec / 3600.0}))
        ORDER BY phot_g_mean_mag ASC
        """
    )
    r = job.get_results()
    if len(r) == 0:
        return None
    row = r[0]
    if row["pmra"] is None or row["pmdec"] is None:
        return None
    return {
        "source_id": int(row["source_id"]),
        "gaia_ra": float(row["ra"]),
        "gaia_dec": float(row["dec"]),
        "pmra": float(row["pmra"]),  # mas/yr, already includes cos(dec)
        "pmdec": float(row["pmdec"]),  # mas/yr
        "ref_epoch": float(row["ref_epoch"]),
        "gaia_g": float(row["phot_g_mean_mag"]),
        "sep_arcsec_J2000": float(row["sep_arcsec"]),
    }


def load_gaia_lookup(stars: list[str]) -> dict[str, dict]:
    """Look up each Landolt standard in Gaia DR3 once."""
    catalog = {r["star_name"]: r for r in csv.DictReader(open(LANDOLT_CATALOG))}
    out: dict[str, dict] = {}
    for star in stars:
        if star not in catalog:
            print(f"  [warn] {star} not in Landolt catalog file")
            continue
        ra = float(catalog[star]["ra_deg"])
        dec = float(catalog[star]["dec_deg"])
        gaia = query_gaia_for_landolt(ra, dec, GAIA_CONE_RADIUS_ARCSEC)
        if gaia is None:
            print(
                f"  [warn] {star}: no Gaia DR3 source within {GAIA_CONE_RADIUS_ARCSEC}″"
            )
            continue
        out[star] = {"landolt_ra": ra, "landolt_dec": dec, **gaia}
        print(
            f"  {star:20s}  Gaia G={gaia['gaia_g']:.2f}  "
            f"PM=({gaia['pmra']:+6.2f}, {gaia['pmdec']:+6.2f}) mas/yr  "
            f"sep(J2000.0)={gaia['sep_arcsec_J2000']*1000:.0f} mas"
        )
    return out


# ---------------------------------------------------------------------------
# Visit metadata: MJD per visit from preliminary_visit_summary FITS
# ---------------------------------------------------------------------------

_MJD_OF_UNIX_EPOCH = 40587  # MJD for 1970-01-01T00:00:00


def build_visit_mjd_map() -> dict[str, float]:
    """Return {visit_id_str: MJD (UTC)} from all visit_summary FITS in the repo.

    The visit_summary FITS does not carry DATE-AVG in the primary header; the
    timestamp lives in the VisitInfo bin-table column 'tai', stored as TAI
    nanoseconds since the Unix epoch (1970-01-01). Convert to TAI-MJD then
    transform to UTC-MJD via astropy.
    """
    pat = f"{LANDOLT_REPO}/Nickel/runs/*/processCcd/*/run/" "preliminary_visit_summary/"
    visit_mjd: dict[str, float] = {}
    for d in glob.glob(pat + "*"):
        for root, _, files in os.walk(d):
            for f in files:
                if not f.endswith(".fits"):
                    continue
                full = os.path.join(root, f)
                try:
                    with fits.open(full) as hdul:
                        # Pull the TAI timestamp from VisitInfo.tai
                        tai_ns = None
                        for hd in hdul:
                            if hd.name != "VisitInfo":
                                continue
                            if hd.data is None or "tai" not in hd.columns.names:
                                continue
                            tai_ns = float(hd.data["tai"][0])
                            break
                        if tai_ns is None:
                            continue
                        mjd_tai = _MJD_OF_UNIX_EPOCH + tai_ns / 1e9 / 86400.0
                        mjd_utc = float(
                            Time(mjd_tai, format="mjd", scale="tai").utc.mjd
                        )
                        # Visit id from the main bin table.
                        for hd in hdul:
                            if hd.data is None or not hasattr(hd, "columns"):
                                continue
                            if "visit" not in hd.columns.names:
                                continue
                            for row in hd.data:
                                visit_mjd[str(row["visit"])] = mjd_utc
                            break
                except Exception:
                    continue
    return visit_mjd


# ---------------------------------------------------------------------------
# Source catalog lookup: parquet path for (visit, band)
# ---------------------------------------------------------------------------


def build_sources_path_map() -> dict[tuple[str, str], Path]:
    """Return {(visit, band): parquet_path} for all source catalogs in any run."""
    pat = f"{LANDOLT_REPO}/Nickel/runs/*/processCcd/*/run*/single_visit_star_unstandardized/"
    out: dict[tuple[str, str], Path] = {}
    for d in glob.glob(pat + "*"):
        for root, _, files in os.walk(d):
            for f in files:
                if not f.endswith(".parq"):
                    continue
                full = Path(root) / f
                # path .../{ut_date}/{band}/{phys_filter}/{visit}/{name}.parq
                parts = full.parts
                try:
                    visit = parts[-2]
                    band = parts[-4]
                except IndexError:
                    continue
                # Prefer primary "/run/" over fallback runs ("/run_fb1/").
                key = (visit, band)
                if (
                    key in out
                    and "/run_fb" in str(full)
                    and "/run_fb" not in str(out[key])
                ):
                    continue
                out[key] = full
    return out


# ---------------------------------------------------------------------------
# Vector residual at an obs epoch
# ---------------------------------------------------------------------------


def pm_correct_position(gaia: dict, mjd_obs: float) -> tuple[float, float]:
    """Propagate Gaia position by PM from ref_epoch to obs epoch.

    Returns (ra_deg, dec_deg) at the observation epoch. Uses linear
    propagation in a tangent plane, which is sufficient at sub-degree
    distances and sub-arcsec precision for ~10-20 yr baselines.

    Δ_dec_mas    = pmdec · Δt_yr
    Δ_ra_mas     = pmra  · Δt_yr        (already in cos(dec)-corrected form)
    Δ_ra_deg     = Δ_ra_mas / 3.6e6 / cos(dec_rad)
    Δ_dec_deg    = Δ_dec_mas / 3.6e6
    """
    ref_mjd = float(Time(gaia["ref_epoch"], format="jyear", scale="tcb").utc.mjd)
    dt_yr = (mjd_obs - ref_mjd) / 365.25
    dec_rad = np.radians(gaia["gaia_dec"])
    d_ra_mas = gaia["pmra"] * dt_yr
    d_dec_mas = gaia["pmdec"] * dt_yr
    d_ra_deg = d_ra_mas / 3.6e6 / np.cos(dec_rad)
    d_dec_deg = d_dec_mas / 3.6e6
    return gaia["gaia_ra"] + d_ra_deg, gaia["gaia_dec"] + d_dec_deg


def haversine_arcsec(ra1, dec1, ra2, dec2) -> float:
    r1, d1 = np.radians(ra1), np.radians(dec1)
    r2, d2 = np.radians(ra2), np.radians(dec2)
    sd = np.sin((d2 - d1) / 2)
    sa = np.sin((r2 - r1) / 2)
    a = sd**2 + np.cos(d1) * np.cos(d2) * sa**2
    return float(2 * np.arcsin(np.sqrt(a))) * 206264.80624709636


def find_nearest_lsst_source(
    parquet: Path, ra_deg: float, dec_deg: float, radius_arcsec: float
) -> tuple[float, float, float] | None:
    """Return (lsst_ra_deg, lsst_dec_deg, sep_arcsec) for the closest source
    in `parquet` to (ra_deg, dec_deg) within `radius_arcsec`. None otherwise.
    """
    tbl = pq.read_table(parquet, columns=["coord_ra", "coord_dec"])
    ras = np.degrees(tbl["coord_ra"].to_numpy())
    decs = np.degrees(tbl["coord_dec"].to_numpy())
    if ras.size == 0:
        return None
    # Cheap planar pre-filter then haversine for survivors.
    pre = (ras - ra_deg) ** 2 * np.cos(np.radians(dec_deg)) ** 2 + (decs - dec_deg) ** 2
    cand_idx = np.where(pre <= (radius_arcsec / 3600.0) ** 2)[0]
    if cand_idx.size == 0:
        return None
    best_idx, best_sep = -1, float("inf")
    for i in cand_idx:
        s = haversine_arcsec(ra_deg, dec_deg, ras[i], decs[i])
        if s < best_sep:
            best_sep = s
            best_idx = int(i)
    if best_sep > radius_arcsec or best_idx < 0:
        return None
    return float(ras[best_idx]), float(decs[best_idx]), float(best_sep)


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------


def main() -> None:
    src_rows = list(csv.DictReader(open(SRC_CSV)))
    unique_stars = sorted({r["star"] for r in src_rows})
    print(f"loaded {len(src_rows)} validation rows · {len(unique_stars)} unique stars")

    print("\n[1/3] Querying Gaia DR3 for each Landolt standard ...")
    gaia_lookup = load_gaia_lookup(unique_stars)
    print(f"  → {len(gaia_lookup)}/{len(unique_stars)} stars resolved")

    print("\n[2/3] Building visit-MJD lookup from preliminary_visit_summary ...")
    visit_mjd = build_visit_mjd_map()
    print(f"  → {len(visit_mjd)} visits with MJD")

    print("\n[3/3] Building source-catalog lookup ...")
    src_map = build_sources_path_map()
    print(f"  → {len(src_map)} (visit, band) source catalogs")

    out_rows = []
    skipped = {"no_gaia": 0, "no_mjd": 0, "no_parquet": 0, "no_match": 0}
    for r in src_rows:
        star = r["star"]
        visit = r["visit"]
        band = r["band"]
        night = r["night"]
        raw_dist_mas = float(r["match_dist_arcsec"]) * 1000.0

        gaia = gaia_lookup.get(star)
        if gaia is None:
            skipped["no_gaia"] += 1
            continue
        mjd = visit_mjd.get(visit)
        if mjd is None:
            skipped["no_mjd"] += 1
            continue
        parquet = src_map.get((visit, band))
        if parquet is None:
            skipped["no_parquet"] += 1
            continue

        ra_corr, dec_corr = pm_correct_position(gaia, mjd)
        match = find_nearest_lsst_source(
            parquet, ra_corr, dec_corr, RE_MATCH_RADIUS_ARCSEC
        )
        if match is None:
            skipped["no_match"] += 1
            continue
        lsst_ra, lsst_dec, sep = match

        # Vector residual (cos(dec)-correct).
        dec_rad = np.radians(dec_corr)
        delta_ra_mas = (lsst_ra - ra_corr) * np.cos(dec_rad) * 3.6e6
        delta_dec_mas = (lsst_dec - dec_corr) * 3.6e6
        residual_mas = sep * 1000.0  # |delta| via haversine in mas

        out_rows.append(
            {
                "star": star,
                "night": night,
                "visit": visit,
                "band": band,
                "obs_mjd": mjd,
                "obs_epoch": float(Time(mjd, format="mjd", scale="utc").jyear),
                "dt_yr": (
                    mjd
                    - float(
                        Time(gaia["ref_epoch"], format="jyear", scale="tcb").utc.mjd
                    )
                )
                / 365.25,
                "gaia_ra_J2016": gaia["gaia_ra"],
                "gaia_dec_J2016": gaia["gaia_dec"],
                "pmra_mas_yr": gaia["pmra"],
                "pmdec_mas_yr": gaia["pmdec"],
                "gaia_sep_arcsec_J2000": gaia["sep_arcsec_J2000"],
                "pm_corrected_ra_deg": ra_corr,
                "pm_corrected_dec_deg": dec_corr,
                "lsst_ra_deg": lsst_ra,
                "lsst_dec_deg": lsst_dec,
                "delta_ra_mas": delta_ra_mas,
                "delta_dec_mas": delta_dec_mas,
                "residual_mas": residual_mas,
                "raw_match_dist_mas": raw_dist_mas,
            }
        )

    fieldnames = list(out_rows[0].keys()) if out_rows else []
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    print(f"\nwrote {OUT_CSV}  ({len(out_rows)} matches)")
    print("skipped:", skipped)
    if out_rows:
        resids = np.array([r["residual_mas"] for r in out_rows])
        print(
            f"\nresidual_mas  N={len(resids)}  median={np.median(resids):.1f}  "
            f"mean={resids.mean():.1f}  std={resids.std():.1f}"
        )


if __name__ == "__main__":
    main()
