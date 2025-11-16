#!/usr/bin/env python
"""Fit Nickel color terms from matched photometry.

Two input modes are supported:

1. CSV mode (default): use existing exports such as
   ``notebooks/tables/all_matches_processCcd.csv``.
2. Repo mode (``--use-repo``): build matches directly from Butler outputs and the
   on-disk MONSTER reference catalog.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from astropy.table import Table
from lsst.daf.butler import Butler
from scipy.spatial import cKDTree

_REF_MAPPING: Dict[str, Tuple[str, str]] = {
    "B": ("ref_gMeanPSFMag_flux", "ref_rMeanPSFMag_flux"),
    "V": ("ref_gMeanPSFMag_flux", "ref_rMeanPSFMag_flux"),
    "R": ("ref_rMeanPSFMag_flux", "ref_iMeanPSFMag_flux"),
    "I": ("ref_iMeanPSFMag_flux", "ref_rMeanPSFMag_flux"),
}


@dataclass
class FitResult:
    band: str
    n_used: int
    slope: float
    slope_err: float
    intercept: float
    intercept_err: float
    rms: float
    color_span: float
    color_min: float
    color_max: float


def _load_obsnum_to_filter(repo: str, collection: str | None) -> Dict[int, str]:
    butler = Butler(repo, collections=[collection] if collection else None)
    records = butler.registry.queryDimensionRecords(
        "visit", where="instrument='Nickel'"
    )

    mapping: Dict[int, str] = {}
    for record in records:
        try:
            obsnum = int(str(record.name).split("_")[1])
        except Exception:
            continue
        mapping[obsnum] = record.physical_filter
    if not mapping:
        raise RuntimeError("Failed to resolve any Nickel visits from the repo.")
    return mapping


def _flux_to_mag(flux: np.ndarray) -> np.ndarray:
    return -2.5 * np.log10(flux)


def _weighted_linear_fit(
    x: np.ndarray, y: np.ndarray, w: np.ndarray
) -> Tuple[float, float, float, float]:
    """Weighted y = m x + b fit with analytic uncertainties."""
    Sw = np.sum(w)
    Swx = np.sum(w * x)
    Swy = np.sum(w * y)
    Swxx = np.sum(w * x * x)
    Swxy = np.sum(w * x * y)

    denom = Sw * Swxx - Swx**2
    if denom <= 0:
        raise RuntimeError("Degenerate weighted fit.")

    slope = (Sw * Swxy - Swx * Swy) / denom
    intercept = (Swxx * Swy - Swx * Swxy) / denom

    resid = y - (slope * x + intercept)
    chi2 = np.sum(w * resid**2)
    dof = max(len(x) - 2, 1)
    sigma2 = chi2 / dof
    slope_err = math.sqrt(Sw / denom * sigma2)
    intercept_err = math.sqrt(Swxx / denom * sigma2)
    return slope, intercept, slope_err, intercept_err


def _fit_band(
    df: pd.DataFrame,
    band: str,
    primary_col: str,
    secondary_col: str,
    max_sep: float,
    min_snr: float,
) -> FitResult | None:
    mask = (
        (df["sep_arcsec"] <= max_sep)
        & np.isfinite(df["src_flux"])
        & (df["src_flux"] > 0)
        & np.isfinite(df["src_fluxErr"])
        & (df["src_fluxErr"] > 0)
        & np.isfinite(df[primary_col])
        & (df[primary_col] > 0)
        & np.isfinite(df[secondary_col])
        & (df[secondary_col] > 0)
    )
    band_df = df.loc[mask].copy()
    if band_df.empty:
        return None

    band_df["snr"] = band_df["src_flux"] / band_df["src_fluxErr"]
    band_df = band_df[band_df["snr"] >= min_snr]
    if len(band_df) < 20:
        return None

    band_df["nickel_mag"] = _flux_to_mag(band_df["src_flux"])
    band_df["ref_primary_mag"] = _flux_to_mag(band_df[primary_col])
    band_df["ref_secondary_mag"] = _flux_to_mag(band_df[secondary_col])
    band_df["color"] = band_df["ref_primary_mag"] - band_df["ref_secondary_mag"]
    band_df["delta"] = band_df["nickel_mag"] - band_df["ref_primary_mag"]
    band_df = band_df[np.isfinite(band_df["color"]) & np.isfinite(band_df["delta"])]

    color_limits = {
        "B": (-0.4, 2.2),
        "V": (-0.4, 2.0),
        "R": (-0.2, 1.6),
        "I": (-0.5, 1.8),
    }.get(band, (-1.0, 3.0))
    band_df = band_df[
        (band_df["color"] >= color_limits[0]) & (band_df["color"] <= color_limits[1])
    ]
    if len(band_df) < 20:
        return None

    x = band_df["color"].to_numpy()
    y = band_df["delta"].to_numpy()
    w = (band_df["snr"].to_numpy() / 1.0857) ** 2

    clip_mask = np.ones_like(x, dtype=bool)
    for _ in range(3):
        if clip_mask.sum() < 3:
            break
        coeffs = np.polyfit(x[clip_mask], y[clip_mask], 1, w=w[clip_mask])
        resid = y - np.polyval(coeffs, x)
        sigma = np.nanstd(resid[clip_mask])
        new_mask = np.abs(resid) < 3 * sigma if sigma > 0 else np.ones_like(resid, bool)
        if new_mask.sum() == clip_mask.sum():
            clip_mask = new_mask
            break
        clip_mask &= new_mask

    x_fit = x[clip_mask]
    y_fit = y[clip_mask]
    w_fit = w[clip_mask]
    if len(x_fit) < 10:
        return None

    slope, intercept, slope_err, intercept_err = _weighted_linear_fit(
        x_fit, y_fit, w_fit
    )
    residuals = y_fit - (slope * x_fit + intercept)
    rms = float(np.std(residuals))

    return FitResult(
        band=band,
        n_used=len(x_fit),
        slope=float(slope),
        slope_err=float(slope_err),
        intercept=float(intercept),
        intercept_err=float(intercept_err),
        rms=rms,
        color_span=float(x_fit.max() - x_fit.min()),
        color_min=float(x_fit.min()),
        color_max=float(x_fit.max()),
    )


class ReferenceCatalog:
    """Load MONSTER refcat shards and support nearest-neighbour queries."""

    def __init__(self, root: Path):
        root = root.expanduser().resolve()
        files = sorted(root.glob("refcat_htm7_*.fits"))
        if not files:
            raise RuntimeError(f"No MONSTER shards found under {root}")

        cols = [
            "coord_ra",
            "coord_dec",
            "monster_ComCam_g_flux",
            "monster_ComCam_r_flux",
            "monster_ComCam_i_flux",
        ]
        ra_list: List[np.ndarray] = []
        dec_list: List[np.ndarray] = []
        g_list: List[np.ndarray] = []
        r_list: List[np.ndarray] = []
        i_list: List[np.ndarray] = []
        for path in files:
            tab = Table.read(path)[cols].to_pandas()
            mask = (
                np.isfinite(tab["monster_ComCam_g_flux"])
                & (tab["monster_ComCam_g_flux"] > 0)
                & np.isfinite(tab["monster_ComCam_r_flux"])
                & (tab["monster_ComCam_r_flux"] > 0)
                & np.isfinite(tab["monster_ComCam_i_flux"])
                & (tab["monster_ComCam_i_flux"] > 0)
            )
            if mask.sum() == 0:
                continue
            ra_list.append(np.array(tab.loc[mask, "coord_ra"], dtype=float))
            dec_list.append(np.array(tab.loc[mask, "coord_dec"], dtype=float))
            g_list.append(np.array(tab.loc[mask, "monster_ComCam_g_flux"], dtype=float))
            r_list.append(np.array(tab.loc[mask, "monster_ComCam_r_flux"], dtype=float))
            i_list.append(np.array(tab.loc[mask, "monster_ComCam_i_flux"], dtype=float))

        self.ra = np.concatenate(ra_list)
        self.dec = np.concatenate(dec_list)
        self.g = np.concatenate(g_list)
        self.r = np.concatenate(r_list)
        self.i = np.concatenate(i_list)

        cos_dec = np.cos(self.dec)
        points = np.column_stack(
            (cos_dec * np.cos(self.ra), cos_dec * np.sin(self.ra), np.sin(self.dec))
        )
        self.tree = cKDTree(points)

    def query(self, ra_rad: np.ndarray, dec_rad: np.ndarray, radius_arcsec: float):
        cos_dec = np.cos(dec_rad)
        vectors = np.column_stack(
            (cos_dec * np.cos(ra_rad), cos_dec * np.sin(ra_rad), np.sin(dec_rad))
        )
        radius = 2.0 * np.sin(np.deg2rad(radius_arcsec / 3600.0) / 2.0)
        dist, idx = self.tree.query(vectors, distance_upper_bound=radius)
        sep_arcsec = 2.0 * np.degrees(np.arcsin(np.clip(dist / 2.0, 0.0, 1.0))) * 3600.0
        return idx, sep_arcsec


def _build_matches_from_repo(
    repo: str,
    collection: str | None,
    refcat_root: Path,
    refcat_radius: float,
    match_distance_arcsec: float,
    build_min_snr: float,
) -> pd.DataFrame:
    refcat = ReferenceCatalog(refcat_root)
    butler = Butler(repo, collections=[collection] if collection else None)
    refs = list(
        butler.registry.queryDatasets(
            "single_visit_star_ref_match_photom",
            collections=[collection] if collection else None,
        )
    )

    records: List[Dict[str, float]] = []
    for dsref in refs:
        band = dsref.dataId.get("physical_filter")
        if band not in _REF_MAPPING:
            continue
        table = butler.get(dsref)
        flux = np.array(table["psfFlux_target"])
        err = np.array(table["psfFluxErr_target"])
        snr = flux / err

        flag_mask = (
            (~table["psfFlux_flag_target"])
            & (~table["pixelFlags_saturatedCenter_target"])
            & (~table["extendedness_flag_target"])
            & (~table["sky_source_target"])
        )
        good = (
            flag_mask
            & (flux > 0)
            & (err > 0)
            & np.isfinite(flux)
            & np.isfinite(err)
            & np.isfinite(table["matchDistance"])
            & (table["matchDistance"] <= match_distance_arcsec)
            & (snr >= build_min_snr)
        )
        if not np.any(good):
            continue

        ra_rad = np.deg2rad(np.array(table["ra_ref"][good]))
        dec_rad = np.deg2rad(np.array(table["dec_ref"][good]))
        idx, sep_arcsec = refcat.query(ra_rad, dec_rad, refcat_radius)
        valid = (idx < len(refcat.ra)) & np.isfinite(idx)
        if not np.any(valid):
            continue

        selected_rows = np.where(good)[0][valid]
        for row_id, ref_idx, sep in zip(selected_rows, idx[valid], sep_arcsec[valid]):
            records.append(
                {
                    "filter": band,
                    "src_flux": float(flux[row_id]),
                    "src_fluxErr": float(err[row_id]),
                    "ref_gMeanPSFMag_flux": float(refcat.g[ref_idx]),
                    "ref_rMeanPSFMag_flux": float(refcat.r[ref_idx]),
                    "ref_iMeanPSFMag_flux": float(refcat.i[ref_idx]),
                    "sep_arcsec": float(sep),
                }
            )

    if not records:
        raise RuntimeError("Failed to build any matches from the repo.")
    return pd.DataFrame.from_records(records)


def run(
    repo: str,
    collection: str | None,
    matches_csv: Path | None,
    max_sep: float,
    min_snr: float,
    use_repo: bool,
    refcat_root: Path,
    refcat_match_radius: float,
    match_distance_arcsec: float,
    build_min_snr: float,
) -> Iterable[FitResult]:
    if use_repo:
        df = _build_matches_from_repo(
            repo=repo,
            collection=collection,
            refcat_root=refcat_root,
            refcat_radius=refcat_match_radius,
            match_distance_arcsec=match_distance_arcsec,
            build_min_snr=build_min_snr,
        )
    else:
        if matches_csv is None:
            raise RuntimeError("CSV mode requested but --matches was not provided.")
        df = pd.read_csv(matches_csv)
        obsnum_to_filter = _load_obsnum_to_filter(repo, collection)
        df["filter"] = df["visit"].map(obsnum_to_filter)
        df = df.dropna(subset=["filter"])

    results: List[FitResult] = []
    for band, (primary, secondary) in _REF_MAPPING.items():
        band_df = df[df["filter"] == band]
        result = _fit_band(band_df, band, primary, secondary, max_sep, min_snr)
        if result:
            results.append(result)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit Nickel color terms from matched photometry."
    )
    parser.add_argument("--repo", required=True, help="Butler repo path.")
    parser.add_argument(
        "--collection",
        default=None,
        help="Collection with Nickel visits (used to map OBSNUM to filters).",
    )
    parser.add_argument(
        "--matches",
        type=Path,
        default=None,
        help="CSV file with matched photometry (ignored with --use-repo).",
    )
    parser.add_argument(
        "--use-repo",
        action="store_true",
        help="Build matches directly from Butler + MONSTER refcat.",
    )
    parser.add_argument(
        "--refcat-root",
        type=Path,
        default=None,
        help="Path to the_monster_20250219_afw directory (repo mode).",
    )
    parser.add_argument(
        "--refcat-match-radius",
        type=float,
        default=1.0,
        help="Maximum refcat match radius in arcsec (repo mode).",
    )
    parser.add_argument(
        "--match-distance",
        type=float,
        default=1.5,
        help="Maximum matchDistance from pipeline tables (arcsec, repo mode).",
    )
    parser.add_argument(
        "--build-min-snr",
        type=float,
        default=20.0,
        help="Minimum Nickel S/N when building repo matches.",
    )
    parser.add_argument(
        "--max-sep",
        type=float,
        default=2.0,
        help="Max separation for the fit (arcsec).",
    )
    parser.add_argument(
        "--min-snr", type=float, default=10.0, help="Minimum Nickel S/N for fitting."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    default_refcat_root = (
        Path(__file__).resolve().parents[3]
        / "refcats"
        / "data"
        / "refcats"
        / "the_monster_20250219_afw"
    )
    refcat_root = args.refcat_root or default_refcat_root

    results = run(
        repo=args.repo,
        collection=args.collection,
        matches_csv=args.matches,
        max_sep=args.max_sep,
        min_snr=args.min_snr,
        use_repo=args.use_repo,
        refcat_root=refcat_root,
        refcat_match_radius=args.refcat_match_radius,
        match_distance_arcsec=args.match_distance,
        build_min_snr=args.build_min_snr,
    )

    if not results:
        raise SystemExit("No usable bands; check your inputs.")

    print(
        f"{'Band':<3} {'N':>6} {'c0 (mag)':>12} {'c1':>10} {'rms':>8} {'color span':>12}"
    )
    print("-" * 60)
    for res in results:
        print(
            f"{res.band:<3} {res.n_used:6d} {res.intercept:12.4f} "
            f"{res.slope:10.4f} {res.rms:8.4f} {res.color_span:12.4f}"
        )


if __name__ == "__main__":
    main()
