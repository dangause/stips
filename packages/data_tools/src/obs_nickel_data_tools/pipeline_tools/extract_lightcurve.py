#!/opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python
"""
extract_lightcurve.py - Extract light curve from DIA source catalogs

This script extracts a light curve for a specific object from difference imaging
source catalogs, producing a CSV file with photometry over time.

Usage:
    obsn-dia-lightcurve \\
        --repo /path/to/repo \\
        --collection "Nickel/runs/*/diff/*/run" \\
        --ra 123.456 --dec +12.345 \\
        --radius 1.0 \\
        --output lightcurve.csv

Example with object name (looks up coordinates):
    obsn-dia-lightcurve \\
        --repo $REPO \\
        --collection "Nickel/runs/202406*/diff/*/run" \\
        --object "2020wnt" \\
        --output lightcurve_2020wnt.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import astropy.coordinates as coord
import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lsst.daf.butler import Butler


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract light curve from DIA source catalogs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument(
        "--collection",
        required=True,
        help="Collection(s) to search (supports wildcards, e.g., 'Nickel/runs/*/diff/*/run')",
    )

    # Position specification (one of these is required)
    pos_group = parser.add_mutually_exclusive_group(required=True)
    pos_group.add_argument("--object", help="Object name (resolves via SIMBAD/NED)")
    pos_group.add_argument(
        "--ra", type=float, help="Right ascension in decimal degrees"
    )

    parser.add_argument(
        "--dec", type=float, help="Declination in decimal degrees (required if --ra)"
    )
    parser.add_argument(
        "--radius",
        type=float,
        default=1.0,
        help="Match radius in arcseconds (default: 1.0)",
    )
    parser.add_argument("--output", "-o", required=True, help="Output CSV file path")
    parser.add_argument(
        "--band", help="Filter to specific band (b, v, r, i)", default=None
    )
    parser.add_argument(
        "--min-snr",
        type=float,
        default=3.0,
        help="Minimum S/N for detections (default: 3.0)",
    )
    parser.add_argument(
        "--dataset-type",
        default="dia_source_unfiltered",
        help="DIA source dataset type (default: dia_source_unfiltered)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate light curve plots (one per band)",
    )
    parser.add_argument(
        "--name",
        help="Custom name for plot title (if not specified, uses object name or coordinates)",
    )
    parser.add_argument(
        "--y-axis",
        default="apparent_mag",
        choices=["apparent_mag", "absolute_mag", "flux_nJy", "flux_adu"],
        help="Y-axis display mode (default: apparent_mag)",
    )
    parser.add_argument(
        "--x-axis",
        default="mjd",
        choices=["mjd", "days_since_explosion"],
        help="X-axis display mode (default: mjd)",
    )
    parser.add_argument(
        "--explosion-mjd",
        type=float,
        default=None,
        help="Explosion MJD (required when --x-axis=days_since_explosion)",
    )
    parser.add_argument(
        "--distance-modulus",
        type=float,
        default=None,
        help="Distance modulus (required when --y-axis=absolute_mag)",
    )

    args = parser.parse_args()

    # Validate position args
    if args.ra is not None and args.dec is None:
        parser.error("--dec required when using --ra")

    # Validate display mode dependencies
    if args.x_axis == "days_since_explosion" and args.explosion_mjd is None:
        parser.error(
            "--explosion-mjd required when using --x-axis=days_since_explosion"
        )
    if args.y_axis == "absolute_mag" and args.distance_modulus is None:
        parser.error("--distance-modulus required when using --y-axis=absolute_mag")

    return args


def resolve_object_name(object_name: str) -> coord.SkyCoord:
    """Resolve object name to coordinates using astropy."""
    print(f"Resolving object name '{object_name}' via SIMBAD/NED...")
    try:
        target = coord.SkyCoord.from_name(object_name)
        print(f"  → RA={target.ra.deg:.6f}°, Dec={target.dec.deg:.6f}° (J2000)")
        return target
    except Exception as e:
        print(f"ERROR: Failed to resolve object name: {e}", file=sys.stderr)
        sys.exit(1)


def _clamp_ylim(ax, df: pd.DataFrame):
    """Clamp y-axis limits to magnitude range with 15% padding.

    Prevents extreme error bars from stretching the axes.
    Uses the same approach as the forced photometry lightcurve tasks.
    """
    finite_mags = df["mag"][np.isfinite(df["mag"])]
    if len(finite_mags) == 0:
        return
    mag_min, mag_max = finite_mags.min(), finite_mags.max()
    pad = 0.15 * (mag_max - mag_min) if mag_max > mag_min else 0.5
    # Axes are inverted (brighter = lower mag = higher on plot)
    ax.set_ylim(mag_max + pad, mag_min - pad)


def plot_light_curves(df: pd.DataFrame, output_path: Path, target_name: str):
    """Generate a single multi-band light curve plot with publication styling."""
    try:
        from lsst.obs.nickel.plotting import (
            FIGURE_SIZE,
            apply_publication_style,
            format_lightcurve_axes,
            plot_lightcurve_band,
            set_title,
            sort_bands,
        )

        _has_plotting = True
    except ImportError:
        _has_plotting = False

    print("\n=== GENERATING PLOT ===")

    if _has_plotting:
        apply_publication_style()
        bands = sort_bands(df["band"].unique())

        fig, ax = plt.subplots(figsize=FIGURE_SIZE)

        for band in bands:
            band_data = df[df["band"] == band]
            plot_lightcurve_band(
                ax,
                band_data["mjd"].values,
                band_data["mag"].values,
                band_data["mag_err"].values,
                band,
                count=len(band_data),
            )

        format_lightcurve_axes(ax, invert_y=True)
        set_title(ax, target_name)
        ax.legend(loc="best")

        # Clamp ylim to magnitude range (ignoring extreme error bars)
        _clamp_ylim(ax, df)

    else:
        # Fallback: basic styling when obs_nickel.plotting is unavailable
        band_colors = {
            "b": "blue",
            "v": "green",
            "r": "red",
            "i": "darkred",
            "g": "cyan",
        }
        bands = sorted(df["band"].unique())
        fig, ax = plt.subplots(figsize=(8, 5))

        for band in bands:
            band_data = df[df["band"] == band]
            ax.errorbar(
                band_data["mjd"],
                band_data["mag"],
                yerr=band_data["mag_err"],
                fmt="o",
                color=band_colors.get(band, "black"),
                label=f"{band.upper()}-band (N={len(band_data)})",
                markersize=7,
                capsize=3,
                alpha=0.8,
            )

        ax.set_xlabel("Modified Julian Date (MJD)")
        ax.set_ylabel("Apparent Magnitude (mag)")
        ax.set_title(target_name)
        ax.invert_yaxis()
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(loc="best")

        # Clamp ylim to magnitude range (ignoring extreme error bars)
        _clamp_ylim(ax, df)

    plot_filename = output_path.parent / f"{output_path.stem}.png"
    fig.tight_layout()
    plt.savefig(plot_filename)  # dpi and bbox from rcParams (or default)
    plt.close()

    print(f"  Saved light curve plot: {plot_filename}")
    print()


def get_photocalib_for_visit(
    butler: Butler, visit: int, band: str, photocalib_cache: dict
) -> tuple:
    """Fetch photoCalib for a visit, with caching.

    The photoCalib is stored in initial_photoCalib_detector (from the Nickel
    DRP calibrateImage task), not in calexp. This function queries processCcd
    collections to find the calibration for the given visit.

    Parameters:
        butler: Butler instance
        visit: Visit ID to fetch calibration for
        band: Band name (for cache key)
        photocalib_cache: Dictionary cache for photoCalib objects

    Returns:
        (photoCalib, instFluxToNanojansky_factor) or (None, None) if not available.
        The factor converts 1 ADU to nJy, allowing flux_nJy = flux_adu * factor.
    """
    cache_key = (visit, band)
    if cache_key in photocalib_cache:
        return photocalib_cache[cache_key]

    # Check if we've already cached the processCcd collections
    if "_processccd_collections" not in photocalib_cache:
        try:
            photocalib_cache["_processccd_collections"] = list(
                butler.registry.queryCollections("Nickel/runs/*/processCcd/*")
            )
        except Exception:
            photocalib_cache["_processccd_collections"] = []

    processccd_collections = photocalib_cache["_processccd_collections"]
    if not processccd_collections:
        photocalib_cache[cache_key] = (None, None)
        return None, None

    try:
        # The Nickel DRP produces initial_photoCalib_detector from calibrateImage,
        # not calexp.photoCalib. This is the photometric calibration we need.
        photocalib = butler.get(
            "initial_photoCalib_detector",
            dataId={"instrument": "Nickel", "visit": visit, "detector": 0},
            collections=processccd_collections,
        )
        # Get the calibration factor (converts 1 ADU to nJy)
        factor = photocalib.instFluxToNanojansky(1.0)
        photocalib_cache[cache_key] = (photocalib, factor)
        return photocalib, factor
    except Exception:
        # photoCalib not available for this visit
        photocalib_cache[cache_key] = (None, None)
        return None, None


def main():
    args = parse_args()

    # Resolve target position
    if args.object:
        target = resolve_object_name(args.object)
        ra_deg, dec_deg = target.ra.deg, target.dec.deg
    else:
        ra_deg, dec_deg = args.ra, args.dec
        target = coord.SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg)

    print(f"\nTarget position: RA={ra_deg:.6f}°, Dec={dec_deg:.6f}°")
    print(f"Match radius: {args.radius} arcsec")
    print(f"Min S/N: {args.min_snr}")
    print(f"Butler repo: {args.repo}")
    print(f"Collection: {args.collection}\n")

    # Open Butler
    # Note: wildcards must be resolved before passing to Butler constructor
    butler = Butler(args.repo)

    # Cache for photoCalib objects (keyed by visit, band)
    photocalib_cache = {}

    # Resolve collection wildcards
    # The --collection argument may be comma-separated (from the orchestrator)
    # or a single glob pattern (from CLI usage). Split on commas and resolve each.
    collection_patterns = [c.strip() for c in args.collection.split(",") if c.strip()]
    try:
        resolved_collections = []
        seen = set()
        for pattern in collection_patterns:
            for coll in butler.registry.queryCollections(pattern, flattenChains=True):
                if coll not in seen:
                    resolved_collections.append(coll)
                    seen.add(coll)
        if not resolved_collections:
            print(
                f"ERROR: No collections found matching {len(collection_patterns)} pattern(s)",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.verbose:
            print(f"Resolved collections ({len(resolved_collections)}):")
            for coll in resolved_collections:
                print(f"  - {coll}")
            print()
    except Exception as e:
        print(f"ERROR: Failed to resolve collections: {e}", file=sys.stderr)
        sys.exit(1)

    # Build data ID query
    where_parts = ["instrument='Nickel'"]
    if args.band:
        where_parts.append(f"band='{args.band}'")
    where_clause = " AND ".join(where_parts)

    if args.verbose:
        print(f"Query: dataset_type={args.dataset_type}, where={where_clause}")

    # Query all DIA source catalogs
    try:
        dataset_refs = list(
            butler.registry.queryDatasets(
                args.dataset_type,
                collections=resolved_collections,
                where=where_clause,
            )
        )
    except Exception as e:
        print(f"ERROR: Failed to query datasets: {e}", file=sys.stderr)
        sys.exit(1)

    if not dataset_refs:
        print(
            f"ERROR: No {args.dataset_type} datasets found matching query",
            file=sys.stderr,
        )
        print(f"  where={where_clause}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(dataset_refs)} DIA source catalogs to search\n")

    # Extract sources near target
    all_detections = []
    search_radius = args.radius * u.arcsec

    for i, ref in enumerate(dataset_refs, 1):
        if args.verbose:
            print(f"[{i}/{len(dataset_refs)}] {ref.dataId}")

        try:
            catalog = butler.get(ref)
        except Exception as e:
            print(f"  WARNING: Failed to load catalog: {e}")
            continue

        # Get visit MJD from visit record
        try:
            visit_id = ref.dataId["visit"]
            visit_records = list(
                butler.registry.queryDimensionRecords(
                    "visit", where=f"instrument='Nickel' AND visit={visit_id}"
                )
            )
            if visit_records:
                visit_mjd = visit_records[0].timespan.begin.mjd
            else:
                visit_mjd = np.nan
        except Exception:
            visit_mjd = np.nan

        if len(catalog) == 0:
            if args.verbose:
                print("  (empty catalog)")
            continue

        # Get coordinates from catalog
        try:
            # Try coord_ra/coord_dec first (DIA sources use radians)
            ra_vals = catalog["coord_ra"]
            dec_vals = catalog["coord_dec"]

            # Check if values are in reasonable radian range (-pi to pi for dec)
            # If dec values are > 90, they're likely degrees being stored in radian columns
            if np.max(np.abs(dec_vals)) > 1.6:  # ~90 degrees in radians
                # Values are in degrees, not radians
                cat_coords = coord.SkyCoord(
                    ra=ra_vals * u.deg,
                    dec=dec_vals * u.deg,
                )
            else:
                # Values are in radians (DIA sources)
                cat_coords = coord.SkyCoord(
                    ra=ra_vals * u.rad,
                    dec=dec_vals * u.rad,
                )
        except KeyError:
            # Try alternative column names
            try:
                cat_coords = coord.SkyCoord(
                    ra=catalog["ra"] * u.deg,
                    dec=catalog["dec"] * u.deg,
                )
            except KeyError:
                print("  WARNING: Cannot extract coordinates from catalog")
                continue

        # Match to target
        sep = target.separation(cat_coords)
        matches = sep < search_radius

        if not matches.any():
            if args.verbose:
                print(f'  (no matches within {args.radius}")')
            continue

        # Extract matched sources
        matched_catalog = catalog[matches]
        n_matches = len(matched_catalog)

        if args.verbose:
            print(f'  → {n_matches} match(es) within {args.radius}"')

        # Extract photometry for each match
        for j, source in enumerate(matched_catalog):
            # Get flux and error - try different column naming conventions
            try:
                # LSST Gen3 naming (with base_ prefix and _instFlux suffix)
                flux = source["base_PsfFlux_instFlux"]
                flux_err = source["base_PsfFlux_instFluxErr"]
            except KeyError:
                try:
                    # Forced photometry on difference images
                    flux = source["diffFlux"]
                    flux_err = source["diffFluxErr"]
                except KeyError:
                    try:
                        # Older naming without prefix
                        flux = source["psfFlux"]
                        flux_err = source["psfFluxErr"]
                    except KeyError:
                        try:
                            # Aperture flux fallback
                            flux = source["base_CircularApertureFlux_12_0_instFlux"]
                            flux_err = source[
                                "base_CircularApertureFlux_12_0_instFluxErr"
                            ]
                        except KeyError:
                            if args.verbose:
                                print("    WARNING: No flux measurements found")
                            continue

            # Calculate S/N
            if flux_err > 0:
                snr = flux / flux_err
            else:
                snr = 0.0

            # Apply S/N cut (use abs for diffim where negative flux is meaningful)
            if abs(snr) < args.min_snr:
                if args.verbose:
                    print(f"    Source {j}: S/N={snr:.1f} < {args.min_snr} (skipped)")
                continue

            # Extract metadata - use visit MJD from visit record.
            # Skip sources where MJD couldn't be determined (invalid timestamps
            # would produce scientifically unusable lightcurve points).
            mjd = visit_mjd
            if np.isnan(mjd):
                if args.verbose:
                    print(f"    Source {j}: skipped (no valid MJD for visit)")
                continue

            try:
                band = ref.dataId["band"]
            except KeyError:
                band = "unknown"

            try:
                visit = ref.dataId["visit"]
            except KeyError:
                visit = -1

            # Convert instrumental flux to calibrated units using photoCalib.
            # DIA source catalogs contain instrumental flux (ADU). We need to:
            # 1. Fetch the science exposure's photoCalib (converts ADU → nJy)
            # 2. Convert nJy to AB magnitude using ZP=31.4
            # For difference images, negative flux is meaningful (template brighter
            # than science), so we report flux_nJy for all detections but mag only
            # when flux is positive.
            flux_nJy = np.nan
            flux_nJy_err = np.nan
            mag = np.nan
            mag_err = np.nan

            photocalib, calib_factor = get_photocalib_for_visit(
                butler, visit, band, photocalib_cache
            )

            if photocalib is not None and calib_factor is not None:
                # Convert instrumental flux to nanojansky
                flux_nJy = flux * calib_factor
                flux_nJy_err = flux_err * calib_factor

                # Convert nJy to AB magnitude (ZP=31.4 for nJy)
                # Only valid for positive flux; negative flux has no magnitude
                if flux_nJy > 0:
                    mag = -2.5 * np.log10(flux_nJy) + 31.4
                    mag_err = 2.5 / np.log(10) * flux_nJy_err / flux_nJy
            else:
                # No photoCalib available - report instrumental flux only
                if args.verbose:
                    print(f"    Source {j}: no photoCalib for visit {visit}")
                # Keep flux_nJy and mag as NaN

            # Get source coordinates - use the already-parsed cat_coords to get degrees
            # This avoids the radians vs degrees confusion
            src_idx = np.where(matches)[0][j]
            src_ra = cat_coords[src_idx].ra.deg
            src_dec = cat_coords[src_idx].dec.deg

            all_detections.append(
                {
                    "mjd": mjd,
                    "band": band,
                    "visit": visit,
                    "ra": src_ra,
                    "dec": src_dec,
                    "flux": flux,  # Instrumental flux (ADU)
                    "flux_err": flux_err,  # Instrumental flux error (ADU)
                    "flux_nJy": flux_nJy,  # Calibrated flux (nanojansky)
                    "flux_nJy_err": flux_nJy_err,  # Calibrated flux error (nanojansky)
                    "mag": mag,  # AB magnitude (from calibrated flux)
                    "mag_err": mag_err,
                    "snr": snr,
                    "separation_arcsec": sep[matches][j].arcsec,
                }
            )

            if args.verbose:
                mag_str = f"{mag:.2f}±{mag_err:.2f}" if np.isfinite(mag) else "N/A"
                print(
                    f"    Source {j}: S/N={snr:.1f}, flux_nJy={flux_nJy:.1f}, mag={mag_str}, "
                    f'sep={sep[matches][j].arcsec:.2f}"'
                )

    # Create DataFrame
    if not all_detections:
        print("\nERROR: No detections found matching criteria", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(all_detections)
    df = df.sort_values("mjd")

    print("\n=== LIGHT CURVE SUMMARY ===")
    print(f"Total detections: {len(df)}")
    print(f"Bands: {sorted(df['band'].unique())}")
    print(f"MJD range: {df['mjd'].min():.3f} - {df['mjd'].max():.3f}")

    # Report calibration statistics
    n_calibrated = df["flux_nJy"].notna().sum()
    n_with_mag = df["mag"].notna().sum()
    print(f"Calibrated flux (nJy): {n_calibrated}/{len(df)} detections")
    print(f"Valid magnitudes: {n_with_mag}/{len(df)} (negative flux → NaN mag)")

    # Report magnitude range only for valid magnitudes
    valid_mags = df["mag"].dropna()
    if len(valid_mags) > 0:
        print(f"Magnitude range: {valid_mags.min():.2f} - {valid_mags.max():.2f}")
    print()

    # Per-band statistics
    for band in sorted(df["band"].unique()):
        band_data = df[df["band"] == band]
        valid_band_mags = band_data["mag"].dropna()
        if len(valid_band_mags) > 0:
            print(
                f"  {band}-band: {len(band_data)} detections, "
                f"<mag>={valid_band_mags.mean():.2f}±{valid_band_mags.std():.2f}"
            )
        else:
            print(
                f"  {band}-band: {len(band_data)} detections, "
                f"<flux_nJy>={band_data['flux_nJy'].mean():.1f} (all negative flux)"
            )

    # Write output
    output_path = Path(args.output)
    df.to_csv(output_path, index=False, float_format="%.6f")
    print(f"\nLight curve saved to: {output_path}")
    print(f"Columns: {', '.join(df.columns)}\n")

    # Generate plots if requested
    if args.plot:
        # Use custom name if provided, otherwise use object name or coordinates
        plot_title = args.name or args.object or f"RA={ra_deg:.4f}, Dec={dec_deg:.4f}"
        plot_light_curves(df, output_path, plot_title)


if __name__ == "__main__":
    main()
