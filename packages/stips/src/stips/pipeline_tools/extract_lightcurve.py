#!/usr/bin/env python
"""
extract_lightcurve.py - Extract light curve from DIA source catalogs

This script extracts a light curve for a specific object from difference imaging
source catalogs, producing a CSV file with photometry over time.

Usage (collection globs use the instrument's prefix, e.g. ``Nickel``):
    stips-dia-lightcurve \\
        --repo /path/to/repo \\
        --collection "<prefix>/runs/*/diff/*/run" \\
        --ra 123.456 --dec +12.345 \\
        --radius 1.0 \\
        --output lightcurve.csv

Example with object name (looks up coordinates):
    stips-dia-lightcurve \\
        --repo $REPO \\
        --collection "<prefix>/runs/202406*/diff/*/run" \\
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

from stips.core.config import load_active_profile


def _resolve_instrument(instrument):
    """Resolve the instrument name from a CLI arg or the active profile.

    Stays robust if the obs package is not importable (falls back to "Nickel").
    """
    if instrument:
        return instrument
    try:
        return load_active_profile().name
    except Exception:
        return "Nickel"


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
        help="Collection(s) to search (supports wildcards, e.g. '<prefix>/runs/*/diff/*/run')",
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
    parser.add_argument(
        "--max-mag-err",
        type=float,
        default=None,
        help="Maximum magnitude error for plot filtering (points with larger errors are excluded from plot)",
    )
    parser.add_argument(
        "--instrument",
        default=None,
        help="Instrument name (default: from the INSTRUMENT_DIR profile)",
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


def _clamp_ylim(ax, df: pd.DataFrame, y_col: str = "mag"):
    """Clamp y-axis limits to value range with 15% padding.

    Prevents extreme error bars from stretching the axes.
    Uses the same approach as the forced photometry lightcurve tasks.
    """
    finite_vals = df[y_col][np.isfinite(df[y_col])]
    if len(finite_vals) == 0:
        return
    val_min, val_max = finite_vals.min(), finite_vals.max()
    pad = 0.15 * (val_max - val_min) if val_max > val_min else 0.5
    # Axes are inverted (brighter = lower mag = higher on plot)
    ax.set_ylim(val_max + pad, val_min - pad)


def plot_light_curves(
    df: pd.DataFrame,
    output_path: Path,
    target_name: str,
    y_axis: str = "apparent_mag",
    x_axis: str = "mjd",
):
    """Generate a single multi-band light curve plot with publication styling."""
    try:
        from lsst.obs.stips.plotting import (
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

    # Determine which columns to plot based on display config
    if y_axis == "absolute_mag":
        y_col, y_err_col = "abs_mag", "abs_mag_err"
        ylabel = "Absolute Magnitude"
        invert_y = True
    elif y_axis == "flux_nJy":
        y_col, y_err_col = "flux_nJy", "flux_nJy_err"
        ylabel = "Flux (nJy)"
        invert_y = False
    elif y_axis == "flux_adu":
        y_col, y_err_col = "flux", "flux_err"
        ylabel = "Flux (ADU)"
        invert_y = False
    else:  # apparent_mag (default)
        y_col, y_err_col = "mag", "mag_err"
        ylabel = "Apparent Magnitude (AB)"
        invert_y = True

    if x_axis == "days_since_explosion" and "days_since_explosion" in df.columns:
        x_col = "days_since_explosion"
        xlabel = "Days Since Explosion"
    else:
        x_col = "mjd"
        xlabel = "Modified Julian Date (MJD)"

    print("\n=== GENERATING PLOT ===")

    if _has_plotting:
        apply_publication_style()
        bands = sort_bands(df["band"].unique())

        fig, ax = plt.subplots(figsize=FIGURE_SIZE)

        for band in bands:
            band_data = df[df["band"] == band]
            plot_lightcurve_band(
                ax,
                band_data[x_col].values,
                band_data[y_col].values,
                band_data[y_err_col].values,
                band,
                count=len(band_data),
            )

        format_lightcurve_axes(ax, ylabel=ylabel, xlabel=xlabel, invert_y=invert_y)
        set_title(ax, target_name)
        ax.legend(loc="best")

        # Clamp ylim for magnitude modes only
        if invert_y:
            _clamp_ylim(ax, df, y_col=y_col)

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
                band_data[x_col],
                band_data[y_col],
                yerr=band_data[y_err_col],
                fmt="o",
                color=band_colors.get(band, "black"),
                label=f"{band.upper()}-band (N={len(band_data)})",
                markersize=7,
                capsize=3,
                alpha=0.8,
            )

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(target_name)
        if invert_y:
            ax.invert_yaxis()
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(loc="best")

        # Clamp ylim for magnitude modes only
        if invert_y:
            _clamp_ylim(ax, df, y_col=y_col)

    plot_filename = output_path.parent / f"{output_path.stem}.png"
    fig.tight_layout()
    plt.savefig(plot_filename)  # dpi and bbox from rcParams (or default)
    plt.close()

    print(f"  Saved light curve plot: {plot_filename}")
    print()


def get_photocalib_for_visit(
    butler: Butler, visit: int, band: str, photocalib_cache: dict, instrument: str
) -> tuple:
    """Fetch photoCalib for a visit, with caching.

    The photoCalib is stored in initial_photoCalib_detector (from the
    DRP calibrateImage task), not in calexp. This function queries processCcd
    collections to find the calibration for the given visit.

    Parameters:
        butler: Butler instance
        visit: Visit ID to fetch calibration for
        band: Band name (for cache key)
        photocalib_cache: Dictionary cache for photoCalib objects
        instrument: Instrument name (used for the dataId and the
            processCcd collection-glob prefix)

    Returns:
        (photoCalib, instFluxToNanojansky_factor) or (None, None) if not available.
        The factor converts 1 ADU to nJy, allowing flux_nJy = flux_adu * factor.
    """
    cache_key = (visit, band)
    if cache_key in photocalib_cache:
        return photocalib_cache[cache_key]

    # Check if we've already cached the processCcd collections
    if "_processccd_collections" not in photocalib_cache:
        # The collection prefix is the instrument's collection_prefix. For these
        # single-CCD instruments collection_prefix == instrument name (Nickel),
        # but resolve it from the profile to stay correct for non-Nickel forks.
        try:
            prefix = load_active_profile().collection_prefix
        except Exception:
            prefix = instrument
        try:
            photocalib_cache["_processccd_collections"] = list(
                butler.registry.queryCollections(f"{prefix}/runs/*/processCcd/*")
            )
        except Exception:
            photocalib_cache["_processccd_collections"] = []

    processccd_collections = photocalib_cache["_processccd_collections"]
    if not processccd_collections:
        photocalib_cache[cache_key] = (None, None)
        return None, None

    try:
        # The DRP produces initial_photoCalib_detector from calibrateImage,
        # not calexp.photoCalib. This is the photometric calibration we need.
        photocalib = butler.get(
            "initial_photoCalib_detector",
            dataId={"instrument": instrument, "visit": visit, "detector": 0},
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

    instrument = _resolve_instrument(args.instrument)

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
    where_parts = [f"instrument='{instrument}'"]
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
                    "visit", where=f"instrument='{instrument}' AND visit={visit_id}"
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

            # Convert flux to calibrated nJy units.
            #
            # IMPORTANT: The Nickel DRP's calibrateImage task bakes the
            # photometric calibration into preliminary_visit_image pixels
            # (BUNIT=nJy, PhotoCalib=1.0 identity). DIA difference images
            # inherit this nJy scale, so forced photometry / DIA source
            # fluxes measured on difference images are ALREADY in nJy.
            #
            # We must NOT multiply by initial_photoCalib_detector again —
            # that factor was already applied to the pixel values by
            # calibrateImage. Doing so would double-calibrate.
            #
            # For non-DIA dataset types (measured on uncalibrated images),
            # the initial_photoCalib_detector conversion is still needed.
            flux_nJy = np.nan
            flux_nJy_err = np.nan
            mag = np.nan
            mag_err = np.nan

            # Dataset types where flux is already calibrated to nJy:
            # - DIA types: measured on difference images (PVI in nJy)
            # - forced_phot_radec: measured on preliminary_visit_image (nJy)
            # For these, DO NOT multiply by initial_photoCalib_detector
            # (that factor was already applied to image pixels by calibrateImage).
            _CALIBRATED_DATASET_TYPES = {
                "forced_phot_diffim_radec",
                "forced_phot_radec",
                "dia_source_unfiltered",
                "dia_source",
                "forced_diff",
                "forced_diff_radec",
            }
            is_calibrated = args.dataset_type in _CALIBRATED_DATASET_TYPES

            if is_calibrated:
                # Flux is already in nJy — use directly
                flux_nJy = flux
                flux_nJy_err = flux_err
            else:
                # Flux is in instrumental ADU — apply photoCalib
                photocalib, calib_factor = get_photocalib_for_visit(
                    butler, visit, band, photocalib_cache, instrument
                )
                if photocalib is not None and calib_factor is not None:
                    flux_nJy = flux * calib_factor
                    flux_nJy_err = flux_err * calib_factor
                else:
                    if args.verbose:
                        print(f"    Source {j}: no photoCalib for visit {visit}")

            if np.isfinite(flux_nJy):
                # Convert nJy to AB magnitude (ZP=31.4 for nJy)
                # Only valid for positive flux; negative flux has no magnitude
                if flux_nJy > 0:
                    mag = -2.5 * np.log10(flux_nJy) + 31.4
                    mag_err = 2.5 / np.log(10) * flux_nJy_err / flux_nJy

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

    # Add days_since_explosion column if explosion_mjd is provided
    if args.explosion_mjd is not None:
        df["days_since_explosion"] = df["mjd"] - args.explosion_mjd

    # Add absolute magnitude column if distance_modulus is provided
    if args.distance_modulus is not None:
        df["abs_mag"] = df["mag"] - args.distance_modulus
        df["abs_mag_err"] = df["mag_err"]  # Error propagation: same error

    print("\n=== LIGHT CURVE SUMMARY ===")
    print(f"Total detections: {len(df)}")
    print(f"Bands: {sorted(df['band'].unique())}")
    print(f"MJD range: {df['mjd'].min():.3f} - {df['mjd'].max():.3f}")
    if "days_since_explosion" in df.columns:
        print(
            f"Days since explosion: {df['days_since_explosion'].min():.1f} - "
            f"{df['days_since_explosion'].max():.1f}"
        )

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
        # Filter for plotting only (CSV keeps all data)
        plot_df = df
        if args.max_mag_err is not None:
            before = len(plot_df)
            plot_df = plot_df[plot_df["mag_err"] <= args.max_mag_err]
            print(
                f"Plot filter: mag_err <= {args.max_mag_err} "
                f"({before - len(plot_df)} points excluded, {len(plot_df)} remaining)"
            )

        # Use custom name if provided, otherwise use object name or coordinates
        plot_title = args.name or args.object or f"RA={ra_deg:.4f}, Dec={dec_deg:.4f}"
        plot_light_curves(
            plot_df, output_path, plot_title, y_axis=args.y_axis, x_axis=args.x_axis
        )


if __name__ == "__main__":
    main()
