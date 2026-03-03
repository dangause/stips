#!/usr/bin/env python
"""
differential_phot.py - Differential aperture photometry for transit observations.

For bright stars where PSF-fitting forced photometry is unreliable (due to
extended wings or saturation), this script performs aperture photometry on
calibrated visit images (preliminary_visit_image) and computes differential
flux relative to an ensemble of comparison stars.

Usage (runs in LSST stack environment):
    python differential_phot.py \
        --repo /path/to/repo \
        --collection "Nickel/runs/20250802/processCcd/20260303T155824Z" \
        --ra 300.182125 --dec 22.710853 \
        --aperture-radius 20 \
        --n-comparisons 6 \
        --output /path/to/output.csv

The script:
1. Discovers all preliminary_visit_image datasets in the collection.
2. For the first image, detects bright stars to use as comparison ensemble.
3. For each image: measures aperture flux for target + comparison stars.
4. Computes differential flux = target_flux / sum(comparison_fluxes).
5. Outputs a lightcurve CSV compatible with transit.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from scipy import ndimage
from scipy.ndimage import maximum_filter


def parse_args():
    parser = argparse.ArgumentParser(
        description="Differential aperture photometry for transit observations",
    )
    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument(
        "--collection",
        required=True,
        help="Science processCcd CHAINED collection",
    )
    parser.add_argument("--ra", required=True, type=float, help="Target RA (degrees)")
    parser.add_argument("--dec", required=True, type=float, help="Target Dec (degrees)")
    parser.add_argument(
        "--aperture-radius",
        type=int,
        default=20,
        help="Aperture radius in pixels (default: 20)",
    )
    parser.add_argument(
        "--comp-aperture-radius",
        type=int,
        default=None,
        help="Comparison star aperture radius (default: same as target)",
    )
    parser.add_argument(
        "--n-comparisons",
        type=int,
        default=6,
        help="Number of comparison stars (default: 6)",
    )
    parser.add_argument(
        "--min-comp-distance",
        type=float,
        default=40.0,
        help="Minimum distance from target in pixels (default: 40)",
    )
    parser.add_argument("--output", required=True, help="Output CSV path")
    parser.add_argument("--band", default=None, help="Filter band (auto-detected)")
    parser.add_argument("--plot", action="store_true", help="Generate diagnostic plots")
    return parser.parse_args()


def find_pvi_files(repo_path: str, collection: str) -> list[dict]:
    """Find all preliminary_visit_image FITS files in the collection.

    Searches all RUN sub-collections (run, run_fb1, run_fb2, etc.) under the
    CHAINED parent collection.
    """
    from pathlib import Path as P

    repo = P(repo_path)
    # The collection name looks like: Nickel/runs/20250802/processCcd/20260303T155824Z
    # Sub-collections: run, run_fb1, run_fb2, run_fb3
    col_path = repo / collection.replace("/", "/")

    pvi_files = []
    for run_dir in sorted(col_path.iterdir()):
        if not run_dir.is_dir():
            continue
        pvi_dir = run_dir / "preliminary_visit_image"
        if not pvi_dir.exists():
            continue
        for fpath in sorted(pvi_dir.rglob("*.fits")):
            # Extract visit ID from path: .../93461311/preliminary_visit_image_...fits
            visit_id = int(fpath.parent.name)
            pvi_files.append({"path": str(fpath), "visit": visit_id})

    # Deduplicate by visit (prefer primary run over fallbacks)
    seen_visits = set()
    unique_files = []
    for pf in pvi_files:
        if pf["visit"] not in seen_visits:
            seen_visits.add(pf["visit"])
            unique_files.append(pf)

    return unique_files


def find_comparison_stars(
    img: np.ndarray,
    wcs: WCS,
    target_px: float,
    target_py: float,
    n_comparisons: int = 6,
    min_distance: float = 40.0,
    detection_threshold: float = 50000.0,
) -> list[dict]:
    """Detect bright stars in the image to use as comparison ensemble.

    Parameters
    ----------
    img : ndarray
        Calibrated image (nJy).
    wcs : WCS
        Image WCS.
    target_px, target_py : float
        Target pixel coordinates.
    n_comparisons : int
        Number of comparison stars to select.
    min_distance : float
        Minimum pixel distance from target.
    detection_threshold : float
        Minimum smoothed pixel value for detection.

    Returns
    -------
    list of dict with keys: x, y, ra, dec, flux_r10
    """
    smooth = ndimage.gaussian_filter(np.nan_to_num(img, nan=0.0), sigma=3)
    local_max = maximum_filter(smooth, size=15)
    peaks = (smooth == local_max) & (smooth > detection_threshold)
    peak_ys, peak_xs = np.where(peaks)

    # Exclude edges
    border = 35
    h, w_img = img.shape
    edge_ok = (
        (peak_xs > border)
        & (peak_xs < w_img - border)
        & (peak_ys > border)
        & (peak_ys < h - border)
    )
    peak_xs, peak_ys = peak_xs[edge_ok], peak_ys[edge_ok]

    # Measure aperture flux and filter by distance from target
    yy, xx = np.mgrid[: img.shape[0], : img.shape[1]]
    stars = []
    for sx, sy in zip(peak_xs, peak_ys):
        dist_from_target = np.sqrt((sx - target_px) ** 2 + (sy - target_py) ** 2)
        if dist_from_target < min_distance:
            continue
        dist = np.sqrt((xx - sx) ** 2 + (yy - sy) ** 2)
        ap_flux = np.nansum(img[dist <= 10])
        if ap_flux <= 0:
            continue
        coord = wcs.pixel_to_world(float(sx), float(sy))
        stars.append(
            {
                "x": float(sx),
                "y": float(sy),
                "ra": coord.ra.deg,
                "dec": coord.dec.deg,
                "flux_r10": ap_flux,
            }
        )

    # Sort by flux, take brightest
    stars.sort(key=lambda s: s["flux_r10"], reverse=True)
    return stars[:n_comparisons]


def aperture_flux(
    img: np.ndarray, cx: float, cy: float, radius: float
) -> tuple[float, float]:
    """Compute circular aperture flux and uncertainty.

    Parameters
    ----------
    img : ndarray
        Image in nJy.
    cx, cy : float
        Center pixel coordinates.
    radius : float
        Aperture radius in pixels.

    Returns
    -------
    flux, flux_err : float
        Sum of pixel values in aperture and Poisson-like uncertainty.
    """
    yy, xx = np.mgrid[: img.shape[0], : img.shape[1]]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    mask = dist <= radius
    pixels = img[mask]
    good = np.isfinite(pixels)
    flux = float(np.sum(pixels[good]))
    # Uncertainty: sqrt(sum of positive pixel values) as a rough Poisson estimate
    pos = pixels[good] > 0
    if np.any(pos):
        flux_err = float(np.sqrt(np.sum(pixels[good][pos])))
    else:
        flux_err = float(np.sqrt(np.sum(np.abs(pixels[good]))))
    return flux, flux_err


def measure_frame(
    fits_path: str,
    target_ra: float,
    target_dec: float,
    comp_stars: list[dict],
    target_radius: float,
    comp_radius: float,
) -> dict | None:
    """Measure aperture fluxes for target and comparison stars on one frame.

    Returns dict with mjd, target_flux, comp_flux, differential_flux, etc.
    Returns None if the frame cannot be measured.
    """
    from astropy.time import Time

    try:
        with fits.open(fits_path) as hdul:
            img = hdul["IMAGE"].data
            img_hdr = hdul["IMAGE"].header
            pri_hdr = hdul[0].header
            wcs = WCS(img_hdr)
    except Exception:
        return None

    # Get MJD from PRIMARY header (LSST PVI stores metadata there)
    mjd = None
    for key in ("MJD-BEG", "MJD-OBS", "MJD"):
        val = pri_hdr.get(key)
        if val is not None:
            mjd = float(val)
            break
    if mjd is None:
        # Convert DATE-AVG or DATE-BEG to MJD
        date_str = pri_hdr.get("DATE-AVG") or pri_hdr.get("DATE-BEG")
        if date_str is None:
            return None
        timesys = pri_hdr.get("TIMESYS", "UTC")
        scale = "tai" if timesys.upper() == "TAI" else "utc"
        try:
            mjd = Time(date_str, scale=scale, format="isot").utc.mjd
        except Exception:
            return None

    # Get filter from PRIMARY header
    band = pri_hdr.get("FILTNAM", "").strip().lower()
    if not band:
        band = pri_hdr.get("FILTER", "").strip().lower()
    if not band:
        band = "unknown"
    # Normalize band name
    band_map = {"b": "b", "v": "v", "r": "r", "i": "i"}
    band = band_map.get(band, band)

    # Target pixel coordinates
    target_coord = SkyCoord(ra=target_ra * u.deg, dec=target_dec * u.deg)
    tx, ty = wcs.world_to_pixel(target_coord)
    tx, ty = float(tx), float(ty)

    # Check target is on the image
    h, w = img.shape
    if not (
        target_radius < tx < w - target_radius
        and target_radius < ty < h - target_radius
    ):
        return None

    # Target aperture flux
    tgt_flux, tgt_err = aperture_flux(img, tx, ty, target_radius)

    # Comparison star fluxes
    comp_fluxes = []
    for cs in comp_stars:
        cs_coord = SkyCoord(ra=cs["ra"] * u.deg, dec=cs["dec"] * u.deg)
        cx, cy = wcs.world_to_pixel(cs_coord)
        cx, cy = float(cx), float(cy)
        if not (
            comp_radius < cx < w - comp_radius and comp_radius < cy < h - comp_radius
        ):
            continue
        cf, ce = aperture_flux(img, cx, cy, comp_radius)
        if cf > 0:
            comp_fluxes.append(cf)

    if len(comp_fluxes) < 2:
        return None

    comp_sum = sum(comp_fluxes)
    diff_flux = tgt_flux / comp_sum
    # Propagate errors (simplified: dominated by target Poisson noise)
    diff_err = (tgt_err / comp_sum) if comp_sum > 0 else 0.0

    return {
        "mjd": mjd,
        "band": band,
        "target_flux": tgt_flux,
        "target_flux_err": tgt_err,
        "comp_sum": comp_sum,
        "n_comps": len(comp_fluxes),
        "diff_flux": diff_flux,
        "diff_flux_err": diff_err,
    }


def run_differential_phot(
    repo: str,
    collection: str,
    ra: float,
    dec: float,
    aperture_radius: int = 20,
    comp_aperture_radius: int | None = None,
    n_comparisons: int = 6,
    min_comp_distance: float = 40.0,
    output: str = "differential_lightcurve.csv",
    band_filter: str | None = None,
    make_plots: bool = False,
) -> pd.DataFrame:
    """Run differential aperture photometry on all PVI frames.

    Parameters
    ----------
    repo : str
        Butler repository path.
    collection : str
        CHAINED science collection path.
    ra, dec : float
        Target coordinates (degrees).
    aperture_radius : int
        Target aperture radius in pixels.
    comp_aperture_radius : int or None
        Comparison star aperture (default: same as target).
    n_comparisons : int
        Number of comparison stars.
    min_comp_distance : float
        Minimum pixel distance from target for comparison stars.
    output : str
        Output CSV path.
    band_filter : str or None
        Only process this band.
    make_plots : bool
        Generate diagnostic plots.

    Returns
    -------
    DataFrame with differential photometry results.
    """
    if comp_aperture_radius is None:
        comp_aperture_radius = aperture_radius

    print(f"Finding PVI files in {collection}...")
    pvi_files = find_pvi_files(repo, collection)
    print(f"Found {len(pvi_files)} unique PVI files")

    if not pvi_files:
        print("ERROR: No PVI files found")
        sys.exit(1)

    # Use first frame to find comparison stars
    print("Detecting comparison stars from first frame...")
    with fits.open(pvi_files[0]["path"]) as hdul:
        img = hdul["IMAGE"].data
        hdr = hdul["IMAGE"].header
        wcs = WCS(hdr)

    target_coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
    tx, ty = wcs.world_to_pixel(target_coord)
    tx, ty = float(tx), float(ty)

    comp_stars = find_comparison_stars(
        img, wcs, tx, ty, n_comparisons, min_comp_distance
    )
    print(f"Selected {len(comp_stars)} comparison stars:")
    for i, cs in enumerate(comp_stars):
        mag = -2.5 * np.log10(max(cs["flux_r10"], 1)) + 31.4
        print(
            f"  #{i + 1}: RA={cs['ra']:.4f} Dec={cs['dec']:.4f} "
            f"mag~{mag:.1f} px=({cs['x']:.0f},{cs['y']:.0f})"
        )

    # Measure all frames
    print(f"\nMeasuring {len(pvi_files)} frames...")
    print(f"  Target aperture: r={aperture_radius}px")
    print(f"  Comparison aperture: r={comp_aperture_radius}px")

    results = []
    for i, pf in enumerate(pvi_files):
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(pvi_files)}...")
        row = measure_frame(
            pf["path"], ra, dec, comp_stars, aperture_radius, comp_aperture_radius
        )
        if row is not None:
            row["visit"] = pf["visit"]
            results.append(row)

    print(f"Successfully measured {len(results)}/{len(pvi_files)} frames")

    if not results:
        print("ERROR: No successful measurements")
        sys.exit(1)

    df = pd.DataFrame(results)
    df = df.sort_values("mjd").reset_index(drop=True)

    # Apply band filter
    if band_filter:
        df = df[df["band"] == band_filter].reset_index(drop=True)
        print(f"After band filter '{band_filter}': {len(df)} measurements")

    # Normalize differential flux to median
    median_diff = df["diff_flux"].median()
    df["norm_flux"] = df["diff_flux"] / median_diff
    df["norm_flux_err"] = df["diff_flux_err"] / median_diff

    # Compute statistics
    print("\nResults:")
    print(f"  MJD range: {df['mjd'].min():.6f} to {df['mjd'].max():.6f}")
    print(f"  Time span: {(df['mjd'].max() - df['mjd'].min()) * 24:.2f} hours")
    print(f"  Median target flux: {df['target_flux'].median():.0f} nJy")
    print(f"  Median comp sum: {df['comp_sum'].median():.0f} nJy")
    print(f"  Differential flux RMS: {df['norm_flux'].std() * 100:.2f}%")

    # Write output CSV in transit.py-compatible format
    out_df = pd.DataFrame(
        {
            "mjd": df["mjd"],
            "band": df["band"],
            "visit": df["visit"],
            "ra": ra,
            "dec": dec,
            "flux": df["diff_flux"],
            "flux_err": df["diff_flux_err"],
            "flux_nJy": df["target_flux"],
            "flux_nJy_err": df["target_flux_err"],
            "norm_flux": df["norm_flux"],
            "norm_flux_err": df["norm_flux_err"],
            "n_comps": df["n_comps"],
            "comp_sum": df["comp_sum"],
        }
    )

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    print(f"\nLightcurve written to {out_path}")

    if make_plots:
        _make_plots(df, out_path.parent, ra, dec)

    return df


def _make_plots(df: pd.DataFrame, out_dir: Path, ra: float, dec: float):
    """Generate diagnostic plots."""
    fig, axes = plt.subplots(4, 1, figsize=(12, 14), sharex=True)

    hours = (df["mjd"] - df["mjd"].min()) * 24

    # 1. Raw target flux
    ax = axes[0]
    ax.scatter(hours, df["target_flux"] / 1e9, s=3, alpha=0.5, color="blue")
    ax.set_ylabel("Target flux (10^9 nJy)")
    ax.set_title(f"Differential Aperture Photometry: RA={ra:.4f} Dec={dec:.4f}")

    # 2. Comparison ensemble flux
    ax = axes[1]
    ax.scatter(hours, df["comp_sum"] / 1e9, s=3, alpha=0.5, color="green")
    ax.set_ylabel("Comp sum (10^9 nJy)")

    # 3. Differential flux (normalized)
    ax = axes[2]
    ax.scatter(hours, df["norm_flux"], s=3, alpha=0.5, color="red")
    ax.axhline(1.0, color="gray", linestyle="--", alpha=0.5)
    ax.set_ylabel("Normalized diff flux")

    # 4. Binned differential flux
    ax = axes[3]
    n_bins = max(1, len(df) // 10)
    bin_edges = np.linspace(hours.min(), hours.max(), n_bins + 1)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    bin_means = []
    bin_stds = []
    for j in range(n_bins):
        in_bin = (hours >= bin_edges[j]) & (hours < bin_edges[j + 1])
        if in_bin.sum() > 0:
            bin_means.append(df["norm_flux"][in_bin].median())
            bin_stds.append(df["norm_flux"][in_bin].std() / np.sqrt(in_bin.sum()))
        else:
            bin_means.append(np.nan)
            bin_stds.append(np.nan)
    ax.errorbar(
        bin_centers, bin_means, yerr=bin_stds, fmt="o-", color="darkred", markersize=4
    )
    ax.axhline(1.0, color="gray", linestyle="--", alpha=0.5)
    ax.set_ylabel("Binned diff flux")
    ax.set_xlabel("Hours from start")

    plt.tight_layout()
    plot_path = out_dir / "differential_phot_diagnostic.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Diagnostic plot saved to {plot_path}")


def main():
    args = parse_args()
    run_differential_phot(
        repo=args.repo,
        collection=args.collection,
        ra=args.ra,
        dec=args.dec,
        aperture_radius=args.aperture_radius,
        comp_aperture_radius=args.comp_aperture_radius,
        n_comparisons=args.n_comparisons,
        min_comp_distance=args.min_comp_distance,
        output=args.output,
        band_filter=args.band,
        make_plots=args.plot,
    )


if __name__ == "__main__":
    main()
