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

    args = parser.parse_args()

    # Validate position args
    if args.ra is not None and args.dec is None:
        parser.error("--dec required when using --ra")

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


def plot_light_curves(df: pd.DataFrame, output_path: Path, target_name: str):
    """Generate a single multi-band light curve plot."""
    bands = sorted(df["band"].unique())

    # Band colors for plotting
    band_colors = {
        "b": "blue",
        "v": "green",
        "r": "red",
        "i": "darkred",
        "g": "cyan",
    }

    print("\n=== GENERATING PLOT ===")

    # Create multi-band plot with better styling
    fig, ax = plt.subplots(figsize=(12, 8))

    for band in bands:
        band_data = df[df["band"] == band].copy()
        color = band_colors.get(band, "black")

        ax.errorbar(
            band_data["mjd"],
            band_data["mag"],
            yerr=band_data["mag_err"],
            fmt="o",
            color=color,
            label=f"{band.upper()}-band (N={len(band_data)})",
            markersize=8,
            capsize=4,
            elinewidth=1.5,
            capthick=1.5,
            alpha=0.8,
        )

    # Formatting with units and improved labels
    ax.set_xlabel("Modified Julian Date (MJD)", fontsize=14, fontweight="bold")
    ax.set_ylabel("Apparent Magnitude (mag)", fontsize=14, fontweight="bold")
    ax.set_title(f"{target_name}", fontsize=16, fontweight="bold", pad=15)
    ax.invert_yaxis()  # Brighter objects (lower mag) at top
    ax.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)
    ax.legend(fontsize=11, framealpha=0.9, loc="best")

    # Improve tick labels
    ax.tick_params(axis="both", which="major", labelsize=11)

    # Add minor ticks
    ax.minorticks_on()
    ax.grid(True, which="minor", alpha=0.15, linestyle=":")

    # Save plot with tight layout
    plot_filename = output_path.parent / f"{output_path.stem}.png"
    plt.tight_layout()
    plt.savefig(plot_filename, dpi=200, bbox_inches="tight")
    plt.close()

    print(f"  Saved light curve plot: {plot_filename}")
    print()


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

    # Resolve collection wildcards
    try:
        resolved_collections = list(
            butler.registry.queryCollections(args.collection, flattenChains=True)
        )
        if not resolved_collections:
            print(
                f"ERROR: No collections found matching pattern '{args.collection}'",
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
                    # Older naming without prefix
                    flux = source["psfFlux"]
                    flux_err = source["psfFluxErr"]
                except KeyError:
                    try:
                        # Aperture flux fallback
                        flux = source["base_CircularApertureFlux_12_0_instFlux"]
                        flux_err = source["base_CircularApertureFlux_12_0_instFluxErr"]
                    except KeyError:
                        if args.verbose:
                            print("    WARNING: No flux measurements found")
                        continue

            # Calculate S/N
            if flux_err > 0:
                snr = flux / flux_err
            else:
                snr = 0.0

            # Apply S/N cut
            if snr < args.min_snr:
                if args.verbose:
                    print(f"    Source {j}: S/N={snr:.1f} < {args.min_snr} (skipped)")
                continue

            # Convert flux to magnitude (LSST zeropoint: 31.4)
            zp = 31.4
            if flux > 0:
                mag = -2.5 * np.log10(flux) + zp
                mag_err = 2.5 / np.log(10) * flux_err / flux
            else:
                mag = np.nan
                mag_err = np.nan

            # Extract metadata - use visit MJD from visit record
            mjd = visit_mjd

            try:
                band = ref.dataId["band"]
            except KeyError:
                band = "unknown"

            try:
                visit = ref.dataId["visit"]
            except KeyError:
                visit = -1

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
                    "flux": flux,
                    "flux_err": flux_err,
                    "mag": mag,
                    "mag_err": mag_err,
                    "snr": snr,
                    "separation_arcsec": sep[matches][j].arcsec,
                }
            )

            if args.verbose:
                print(
                    f"    Source {j}: S/N={snr:.1f}, mag={mag:.2f}±{mag_err:.2f}, "
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
    print(f"Magnitude range: {df['mag'].min():.2f} - {df['mag'].max():.2f}")
    print()

    # Per-band statistics
    for band in sorted(df["band"].unique()):
        band_data = df[df["band"] == band]
        print(
            f"  {band}-band: {len(band_data)} detections, "
            f"<mag>={band_data['mag'].mean():.2f}±{band_data['mag'].std():.2f}"
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
