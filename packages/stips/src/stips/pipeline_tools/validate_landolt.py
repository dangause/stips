#!/usr/bin/env python
"""
validate_landolt.py - Cross-match pipeline source catalogs against Landolt standard stars

Cross-matches Landolt star positions against single_visit_star_unstandardized source
catalogs and compares calibrated magnitudes (nJy → AB → Vega) to published Landolt
values (B, V, R, I).

Usage:
    validate-landolt \\
        --repo $REPO \\
        --catalog landolt_catalog.csv \\
        --collection "Nickel/runs/*/processCcd/*" \\
        --output landolt_validation.csv

    # Dry-run: list matched stars per visit without computing residuals
    validate-landolt \\
        --repo $REPO \\
        --catalog landolt_catalog.csv \\
        --list-stars

Output CSV columns:
    star, night, visit, band, pipeline_mag_AB, pipeline_mag_vega, landolt_mag,
    residual, pipeline_mag_err, landolt_mag_err, color_BV, snr,
    airmass, exptime, match_dist_arcsec
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from lsst.daf.butler import Butler
from lsst.daf.butler.registry import MissingDatasetTypeError

from stips.core.config import load_profile


def _resolve_instrument(instrument: str | None) -> str:
    """Resolve the instrument name from a CLI arg or the active profile.

    Stays robust if the obs package is not importable (falls back to "Nickel").
    """
    if instrument:
        return instrument
    try:
        return load_profile(
            os.environ.get("INSTRUMENT_PACKAGE", "lsst.obs.nickel")
        ).name
    except Exception:
        return "Nickel"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Match radius in arcseconds
MATCH_RADIUS_ARCSEC = 10.0

# AB-to-Vega magnitude offsets: mVega = mAB + offset
# Derived from Blanton & Roweis (2007, AJ 133, 734) where ΔmAB = mAB - mVega,
# so offset = -ΔmAB.  Nickel uses Cousins Rc/Ic (confirmed in nickelFilters.py).
AB_TO_VEGA = {
    "b": +0.09,  # ΔmAB(B) = -0.09
    "v": -0.02,  # ΔmAB(V) = +0.02
    "r": -0.21,  # ΔmAB(Rc) = +0.21
    "i": -0.45,  # ΔmAB(Ic) = +0.45
}

# Map Nickel band -> Landolt catalog column
BAND_TO_LANDOLT_COL = {
    "b": "B",
    "v": "V",
    "r": "R",
    "i": "I",
}

# Flux zero-point: 0 AB mag = 3.631e12 nJy  (i.e. 3.631 Jy = 3631 mJy = 3.631e9 uJy = 3.631e12 nJy)
FLUX_ZERO_NJY = 3.631e12


# ---------------------------------------------------------------------------
# Angular separation
# ---------------------------------------------------------------------------


def angular_sep_arcsec(
    ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float
) -> float:
    """Compute angular separation in arcseconds between two sky positions."""
    r1, d1 = np.radians(ra1_deg), np.radians(dec1_deg)
    r2, d2 = np.radians(ra2_deg), np.radians(dec2_deg)
    cos_sep = np.sin(d1) * np.sin(d2) + np.cos(d1) * np.cos(d2) * np.cos(r1 - r2)
    cos_sep = np.clip(cos_sep, -1.0, 1.0)
    return np.degrees(np.arccos(cos_sep)) * 3600.0


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------


def load_landolt_catalog(path: str) -> list[dict]:
    """Load Landolt reference catalog from CSV.

    Expected columns: star, RA, Dec, B, V, R, I (plus optional B_err, V_err, R_err, I_err).
    Returns a list of dicts with all columns as strings/floats.
    """
    stars = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Normalize: strip whitespace from all values
            cleaned = {k.strip(): v.strip() for k, v in row.items()}
            # Convert numeric columns to float
            for col in (
                "ra_deg",
                "dec_deg",
                "B",
                "V",
                "R",
                "I",
                "V_err",
                "BV_err",
                "VR_err",
                "VI_err",
                "B_V",
                "V_R",
                "V_I",
            ):
                if col in cleaned and cleaned[col] not in ("", "nan", "NaN", "N/A"):
                    try:
                        cleaned[col] = float(cleaned[col])
                    except ValueError:
                        cleaned[col] = None
                else:
                    cleaned[col] = None
            # Normalize coordinate keys for cross-match
            cleaned["RA"] = cleaned.get("ra_deg")
            cleaned["Dec"] = cleaned.get("dec_deg")
            # Derive per-band errors from color errors for R, I, B
            v_err = cleaned.get("V_err") or 0.0
            bv_err = cleaned.get("BV_err") or 0.0
            vr_err = cleaned.get("VR_err") or 0.0
            vi_err = cleaned.get("VI_err") or 0.0
            cleaned["B_err"] = (v_err**2 + bv_err**2) ** 0.5
            cleaned["R_err"] = (v_err**2 + vr_err**2) ** 0.5
            cleaned["I_err"] = (v_err**2 + vi_err**2) ** 0.5
            stars.append(cleaned)
    return stars


# ---------------------------------------------------------------------------
# Butler helpers
# ---------------------------------------------------------------------------


def _resolve_collections(butler: Butler, pattern: str) -> list[str]:
    """Expand a collection glob into a concrete ordered list.

    findFirst=True in queryDatasets requires resolved collection names.
    Reverse-sort so the most recent timestamp wins for CHAINED parents.
    """
    resolved = sorted(
        butler.registry.queryCollections(
            pattern,
            includeChains=True,
        ),
        reverse=True,
    )
    return list(resolved)


def _get_flux_column(table) -> str | None:
    """Return the first available aperture flux column name, or None."""
    preferred = [
        "slot_ApFlux_instFlux",
        "base_CircularApertureFlux_12_0_instFlux",
        "base_CircularApertureFlux_9_0_instFlux",
        "base_PsfFlux_instFlux",
    ]
    col_names = (
        set(table.column_names)
        if hasattr(table, "column_names")
        else set(table.colnames)
    )
    for col in preferred:
        if col in col_names:
            return col
    return None


def _get_flux_err_column(table, flux_col: str) -> str | None:
    """Return the error column paired with flux_col, or None."""
    err_col = flux_col + "Err"
    col_names = (
        set(table.column_names)
        if hasattr(table, "column_names")
        else set(table.colnames)
    )
    return err_col if err_col in col_names else None


def _get_column_array(table, col: str):
    """Extract a column as a numpy array, handling ArrowAstropy and SourceCatalog."""
    try:
        return np.asarray(table[col])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Visit metadata
# ---------------------------------------------------------------------------


def load_visit_metadata(
    butler: Butler, collections: list[str], instrument: str
) -> dict[int, dict]:
    """Load preliminary_visit_summary metadata keyed by visit ID.

    Returns {visit: {"airmass": float, "exptime": float, "day_obs": int}}.
    """
    meta: dict[int, dict] = {}

    try:
        refs = list(
            butler.registry.queryDatasets(
                "preliminary_visit_summary",
                collections=collections,
                where=f"instrument='{instrument}'",
                findFirst=True,
            )
        )
    except MissingDatasetTypeError:
        print(
            "[warn] dataset type 'preliminary_visit_summary' not registered — "
            "airmass/exptime will be missing",
            file=sys.stderr,
        )
        return meta

    for ref in refs:
        visit = ref.dataId["visit"]
        try:
            table = butler.get(ref)
        except Exception as exc:
            print(
                f"[warn] failed to load preliminary_visit_summary for visit {visit}: {exc}",
                file=sys.stderr,
            )
            continue

        expanded = butler.registry.expandDataId(ref.dataId)
        day_obs = expanded.records["visit"].day_obs

        # Aggregate over rows (one per detector; Nickel has one detector)
        zenith_dist_vals = []
        exptime_val = None
        for row in table:
            try:
                zd = float(row["zenithDistance"])
                zenith_dist_vals.append(zd)
            except (KeyError, TypeError, ValueError):
                pass
            if exptime_val is None:
                try:
                    exptime_val = float(row["expTime"])
                except (KeyError, TypeError, ValueError):
                    pass

        airmass = None
        if zenith_dist_vals:
            zd_rad = math.radians(float(np.mean(zenith_dist_vals)))
            if abs(zd_rad) < math.pi / 2:
                airmass = 1.0 / math.cos(zd_rad)

        # Get band from the visit_summary table row
        band_val = None
        for row in table:
            try:
                band_val = str(row["band"]).strip().lower()
            except (KeyError, TypeError, ValueError):
                try:
                    band_val = str(row["physical_filter"]).strip().lower()
                except (KeyError, TypeError, ValueError):
                    pass
            if band_val:
                break

        # Load PhotoCalib calibration factor to convert instrumental ADU -> nJy
        # single_visit_star_unstandardized has instrumental fluxes, not calibrated nJy
        photocalib_mean = None
        try:
            pcal_refs = list(
                butler.registry.queryDatasets(
                    "initial_photoCalib_detector",
                    collections=collections,
                    where=f"instrument='{instrument}' AND visit={visit}",
                    findFirst=True,
                )
            )
            if pcal_refs:
                photocalib = butler.get(pcal_refs[0])
                photocalib_mean = photocalib.getCalibrationMean()
        except Exception as exc:
            print(
                f"[warn] could not load PhotoCalib for visit {visit}: {exc}",
                file=sys.stderr,
            )

        meta[visit] = {
            "airmass": airmass,
            "exptime": exptime_val,
            "day_obs": int(day_obs),
            "band": band_val,
            "photocalib_mean": photocalib_mean,
        }

    return meta


# ---------------------------------------------------------------------------
# Cross-match
# ---------------------------------------------------------------------------


def cross_match_visit(
    table,
    stars: list[dict],
    band: str,
    match_radius_arcsec: float = MATCH_RADIUS_ARCSEC,
    photocalib_mean: float | None = None,
) -> list[dict]:
    """Cross-match Landolt stars against one visit's source catalog.

    Returns a list of match dicts with keys:
        star, flux_nJy, flux_err_nJy, match_dist_arcsec, landolt_mag, landolt_mag_err,
        color_BV
    """
    # Identify flux column
    flux_col = _get_flux_column(table)
    if flux_col is None:
        print(
            "[warn] no suitable flux column found in source catalog — skipping visit",
            file=sys.stderr,
        )
        return []

    flux_err_col = _get_flux_err_column(table, flux_col)

    # Extract coordinates (in radians → convert to degrees)
    src_ra_rad = _get_column_array(table, "coord_ra")
    src_dec_rad = _get_column_array(table, "coord_dec")
    if src_ra_rad is None or src_dec_rad is None:
        print(
            "[warn] coord_ra/coord_dec not found in source catalog — skipping visit",
            file=sys.stderr,
        )
        return []

    src_ra_deg = np.degrees(src_ra_rad)
    src_dec_deg = np.degrees(src_dec_rad)

    fluxes = _get_column_array(table, flux_col)
    if fluxes is None:
        return []

    flux_errs = _get_column_array(table, flux_err_col) if flux_err_col else None

    landolt_col = BAND_TO_LANDOLT_COL.get(band)
    landolt_err_col = f"{landolt_col}_err" if landolt_col else None

    matches = []
    for star in stars:
        star_ra = star.get("RA")
        star_dec = star.get("Dec")
        if star_ra is None or star_dec is None:
            continue

        # Compute separation to all sources
        seps = np.array(
            [
                angular_sep_arcsec(star_ra, star_dec, ra, dec)
                for ra, dec in zip(src_ra_deg, src_dec_deg)
            ]
        )

        within = np.where(seps <= match_radius_arcsec)[0]
        if len(within) == 0:
            continue

        # Take the closest match
        best_idx = within[np.argmin(seps[within])]
        best_sep = seps[best_idx]
        flux_raw = float(fluxes[best_idx])
        flux_err_raw = float(flux_errs[best_idx]) if flux_errs is not None else None

        # Apply PhotoCalib to convert instrumental flux -> nJy
        # single_visit_star_unstandardized has instrumental fluxes (ADU-like),
        # not calibrated nJy. photocalib_mean is in nJy/ADU.
        if photocalib_mean is not None and photocalib_mean > 0:
            flux_nJy = flux_raw * photocalib_mean
            flux_err_nJy = (
                flux_err_raw * photocalib_mean if flux_err_raw is not None else None
            )
        else:
            flux_nJy = flux_raw
            flux_err_nJy = flux_err_raw

        # Look up Landolt magnitude for this band
        lmag = star.get(landolt_col) if landolt_col else None
        lerr = star.get(landolt_err_col) if landolt_err_col else None

        # color B-V
        b_mag = star.get("B")
        v_mag = star.get("V")
        color_bv = (
            (float(b_mag) - float(v_mag))
            if (b_mag is not None and v_mag is not None)
            else None
        )

        matches.append(
            {
                "star": star.get("star_name", star.get("star", "")),
                "flux_nJy": flux_nJy,
                "flux_err_nJy": flux_err_nJy,
                "match_dist_arcsec": float(best_sep),
                "landolt_mag": float(lmag) if lmag is not None else None,
                "landolt_mag_err": float(lerr) if lerr is not None else None,
                "color_BV": float(color_bv) if color_bv is not None else None,
            }
        )

    return matches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="Cross-match Landolt standard stars against Nickel pipeline source catalogs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument("--catalog", required=True, help="Path to landolt_catalog.csv")
    parser.add_argument(
        "--collection",
        default=None,
        help="Collection glob pattern "
        "(default: the instrument's processCcd collections from the active profile)",
    )
    parser.add_argument("--output", "-o", required=False, help="Output CSV path")
    parser.add_argument(
        "--list-stars",
        action="store_true",
        help="Dry-run: list matched stars per visit/band, then exit (no --output required)",
    )
    parser.add_argument(
        "--instrument",
        default=None,
        help="Instrument name (default: from INSTRUMENT_PACKAGE profile)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Resolve the collection glob from the active profile when not given,
    # so non-Nickel forks default to their own processCcd collections.
    collection = args.collection
    if collection is None:
        try:
            prefix = load_profile(
                os.environ.get("INSTRUMENT_PACKAGE", "lsst.obs.nickel")
            ).collection_prefix
        except Exception:
            prefix = "Nickel"
        collection = f"{prefix}/runs/*/processCcd/*"

    if not args.list_stars and not args.output:
        print(
            "[error] --output is required unless --list-stars is specified",
            file=sys.stderr,
        )
        return 1

    # Load Landolt catalog
    print(f"[info] loading Landolt catalog: {args.catalog}", file=sys.stderr)
    stars = load_landolt_catalog(args.catalog)
    print(f"[info] loaded {len(stars)} Landolt stars", file=sys.stderr)

    # Open Butler
    butler = Butler(args.repo)

    instrument = _resolve_instrument(args.instrument)

    # Resolve collections
    print(f"[info] querying collection: {collection}", file=sys.stderr)
    collections = _resolve_collections(butler, collection)
    if not collections:
        print(f"[error] no collections match pattern {collection!r}", file=sys.stderr)
        return 1
    print(f"[info] resolved {len(collections)} collection(s)", file=sys.stderr)

    # Load visit metadata once
    visit_meta = load_visit_metadata(butler, collections, instrument)
    print(f"[info] loaded visit metadata for {len(visit_meta)} visits", file=sys.stderr)

    # Query single_visit_star_unstandardized datasets
    try:
        refs = list(
            butler.registry.queryDatasets(
                "single_visit_star_unstandardized",
                collections=collections,
                where=f"instrument='{instrument}'",
                findFirst=True,
            )
        )
    except MissingDatasetTypeError:
        print(
            "[error] dataset type 'single_visit_star_unstandardized' not registered in repo. "
            "Run science processing first.",
            file=sys.stderr,
        )
        return 1

    if not refs:
        print(
            f"[warn] no single_visit_star_unstandardized datasets found in {collection}",
            file=sys.stderr,
        )
        return 1

    print(
        f"[info] found {len(refs)} single_visit_star_unstandardized dataset(s)",
        file=sys.stderr,
    )

    # --list-stars mode: just count matches per visit/band
    if args.list_stars:
        for ref in refs:
            visit = ref.dataId["visit"]
            band = visit_meta.get(visit, {}).get("band")
            if not band:
                print(
                    f"[warn] no band info for visit {visit}, skipping", file=sys.stderr
                )
                continue

            try:
                table = butler.get(ref)
            except Exception as exc:
                print(f"[warn] failed to load visit {visit}: {exc}", file=sys.stderr)
                continue

            pcal = visit_meta.get(visit, {}).get("photocalib_mean")
            matches = cross_match_visit(table, stars, band, photocalib_mean=pcal)
            star_names = [m["star"] for m in matches]
            print(
                f"  visit={visit}  band={band}  matched_stars={len(matches)}"
                + (f"  [{', '.join(star_names)}]" if star_names else ""),
                file=sys.stderr,
            )
        return 0

    # Full mode: compute residuals and write CSV
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    output_rows = []
    skipped_negative_flux = 0

    # Per-band accumulators for summary
    band_residuals: dict[str, list[float]] = defaultdict(list)
    band_stars: dict[str, set[str]] = defaultdict(set)

    for ref in refs:
        visit = ref.dataId["visit"]

        # Get band from visit metadata
        band = visit_meta.get(visit, {}).get("band")
        if not band:
            print(f"[warn] no band info for visit {visit}, skipping", file=sys.stderr)
            continue

        # Load source catalog
        try:
            table = butler.get(ref)
        except Exception as exc:
            print(f"[warn] failed to load visit {visit}: {exc}", file=sys.stderr)
            continue

        # Get visit metadata
        vmeta = visit_meta.get(visit, {})
        airmass = vmeta.get("airmass")
        exptime = vmeta.get("exptime")
        day_obs = vmeta.get("day_obs")

        # Cross-match
        pcal = vmeta.get("photocalib_mean")
        matches = cross_match_visit(table, stars, band, photocalib_mean=pcal)

        for match in matches:
            flux_nJy = match["flux_nJy"]

            # Skip non-positive flux
            if flux_nJy <= 0:
                skipped_negative_flux += 1
                continue

            flux_err_nJy = match["flux_err_nJy"]

            # Convert flux to AB magnitude
            pipeline_mag_ab = -2.5 * math.log10(flux_nJy / FLUX_ZERO_NJY)

            # Apply AB-to-Vega offset
            ab_to_vega_offset = AB_TO_VEGA.get(band, 0.0)
            pipeline_mag_vega = pipeline_mag_ab + ab_to_vega_offset

            # Magnitude error from flux error
            if flux_err_nJy is not None and flux_err_nJy > 0:
                mag_err = (2.5 / math.log(10)) * (flux_err_nJy / flux_nJy)
            else:
                mag_err = None

            # SNR
            snr = (
                flux_nJy / flux_err_nJy
                if (flux_err_nJy is not None and flux_err_nJy > 0)
                else None
            )

            # Residual vs Landolt
            landolt_mag = match["landolt_mag"]
            residual = (
                (pipeline_mag_vega - landolt_mag) if landolt_mag is not None else None
            )

            star_name = match["star"]

            output_rows.append(
                {
                    "star": star_name,
                    "night": day_obs,
                    "visit": visit,
                    "band": band,
                    "pipeline_mag_AB": _fmt(pipeline_mag_ab),
                    "pipeline_mag_vega": _fmt(pipeline_mag_vega),
                    "landolt_mag": _fmt(landolt_mag),
                    "residual": _fmt(residual),
                    "pipeline_mag_err": _fmt(mag_err),
                    "landolt_mag_err": _fmt(match["landolt_mag_err"]),
                    "color_BV": _fmt(match["color_BV"]),
                    "snr": _fmt(snr),
                    "airmass": _fmt(airmass),
                    "exptime": _fmt(exptime),
                    "match_dist_arcsec": _fmt(match["match_dist_arcsec"]),
                }
            )

            if residual is not None:
                band_residuals[band].append(residual)
                band_stars[band].add(star_name)

    if skipped_negative_flux > 0:
        print(
            f"[info] skipped {skipped_negative_flux} match(es) with non-positive flux",
            file=sys.stderr,
        )

    if not output_rows:
        print(
            "[error] no measurements to write. Check --catalog coordinates, "
            "--collection, and that science processing has been run.",
            file=sys.stderr,
        )
        return 1

    # Write CSV
    columns = [
        "star",
        "night",
        "visit",
        "band",
        "pipeline_mag_AB",
        "pipeline_mag_vega",
        "landolt_mag",
        "residual",
        "pipeline_mag_err",
        "landolt_mag_err",
        "color_BV",
        "snr",
        "airmass",
        "exptime",
        "match_dist_arcsec",
    ]

    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in output_rows:
            writer.writerow(row)

    # Per-band summary to stderr
    all_bands = sorted(set(list(band_residuals.keys())))
    for band in all_bands:
        resids = band_residuals[band]
        n_stars = len(band_stars[band])
        mean_resid = float(np.mean(resids)) if resids else float("nan")
        rms_resid = float(np.std(resids)) if resids else float("nan")
        print(
            f"[info] band={band}  N={len(resids)}  unique_stars={n_stars}  "
            f"mean_residual={mean_resid:+.4f}  RMS={rms_resid:.4f}",
            file=sys.stderr,
        )

    print(
        f"[ok] wrote {len(output_rows)} measurements -> {out_path}",
        file=sys.stderr,
    )
    return 0


def _fmt(value) -> str:
    """Format a scalar value for CSV output."""
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return repr(value)
    return str(value)


if __name__ == "__main__":
    sys.exit(main())
