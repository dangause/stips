#!/usr/bin/env python3
"""
Validate and refine color terms using calibrated photometry from real data.

This script compares synthetic color terms (from SEDs) with empirical color
terms derived from actual Nickel observations matched to reference catalogs.

Usage:
    python validate_colorterms.py --repo /path/to/repo --collection Nickel/run/processCcd/YYYYMMDD

Requirements:
    - Butler repo with calibrated photometry
    - Reference catalog with multi-band photometry (PS1 or Gaia)
    - Successfully processed visits in B, V, R, I
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.stats import sigma_clip
from lsst.daf.butler import Butler
from scipy.stats import linregress


def get_matched_photometry(butler, collection, bands=None, min_sources=100):
    """
    Get Nickel photometry matched to reference catalog.

    Returns dict of {band: DataFrame} with columns:
    - nickel_mag: Calibrated Nickel magnitude
    - ref_mag_primary: Reference magnitude in primary band
    - ref_mag_secondary: Reference magnitude in secondary band
    - color: ref_primary - ref_secondary
    - snr: Signal-to-noise ratio
    """
    print(f"Querying matched photometry from: {collection}")

    if bands is None:
        bands = ["B", "V", "R", "I"]

    data_by_band = {}

    for band in bands:
        print(f"\nProcessing band {band}...")

        try:
            # Query sourceTable_visit datasets
            refs = butler.registry.queryDatasets(
                "sourceTable_visit",
                collections=collection,
                where=f"instrument='Nickel' AND band='{band}'",
            )

            all_sources = []
            n_visits = 0

            for ref in refs:
                try:
                    sources = butler.get(ref)

                    # Filter for good sources with reference matches
                    good = (
                        sources["calib_photometry_used"]
                        & ~sources["sky_source"]
                        & np.isfinite(sources["apFlux_17_0_instFlux"])
                        & (sources["apFlux_17_0_instFlux"] > 0)
                        & np.isfinite(sources["apFlux_17_0_instFluxErr"])
                        & (sources["apFlux_17_0_instFluxErr"] > 0)
                        & np.isfinite(sources["refMag"])
                        & np.isfinite(sources["refMag_g"])  # Need ref catalog colors
                        & np.isfinite(sources["refMag_r"])
                        & np.isfinite(sources["refMag_i"])
                    )

                    if np.sum(good) > 0:
                        all_sources.append(sources[good])
                        n_visits += 1

                except Exception as e:
                    print(f"  Warning: Failed to load visit: {e}")
                    continue

            if len(all_sources) == 0:
                print(f"  No valid sources found for band {band}")
                continue

            # Concatenate all sources
            import astropy.table

            sources_table = astropy.table.vstack(all_sources)

            print(f"  Found {len(sources_table)} sources from {n_visits} visits")

            if len(sources_table) < min_sources:
                print(f"  Too few sources (need at least {min_sources})")
                continue

            # Extract photometry
            # Calibrated Nickel magnitude
            nickel_flux = sources_table["apFlux_17_0_instFlux"]
            nickel_flux_err = sources_table["apFlux_17_0_instFluxErr"]

            # Get photoCalib from first visit to convert to magnitude
            # (Assuming all visits have similar calibration - may need refinement)
            nickel_mag = -2.5 * np.log10(nickel_flux)  # Instrumental

            # If we have calibrated magnitudes in the catalog, use those
            if "apFlux_17_0_mag" in sources_table.columns:
                nickel_mag = sources_table["apFlux_17_0_mag"]

            snr = nickel_flux / nickel_flux_err

            # Reference catalog magnitudes (PS1 or Gaia)
            # Map to appropriate reference bands based on Nickel band
            ref_mapping = {
                "B": ("g", "r"),  # B ~ g, color = g-r
                "V": ("g", "r"),  # V ~ g, color = g-r
                "R": ("r", "i"),  # R ~ r, color = r-i
                "I": ("i", "r"),  # I ~ i, color = i-r
            }

            primary, secondary = ref_mapping[band]
            ref_mag_primary = sources_table[f"refMag_{primary}"]
            ref_mag_secondary = sources_table[f"refMag_{secondary}"]
            color = ref_mag_primary - ref_mag_secondary

            # Store data
            data_by_band[band] = {
                "nickel_mag": np.array(nickel_mag),
                "ref_mag_primary": np.array(ref_mag_primary),
                "ref_mag_secondary": np.array(ref_mag_secondary),
                "color": np.array(color),
                "snr": np.array(snr),
                "primary_band": primary,
                "secondary_band": secondary,
                "n_sources": len(sources_table),
                "n_visits": n_visits,
            }

            print(f"  Stored {len(sources_table)} matched sources")
            print(f"  Reference bands: {primary} (primary), {secondary} (secondary)")
            print(f"  Color range: {np.min(color):.2f} to {np.max(color):.2f}")

        except Exception as e:
            print(f"  ERROR processing band {band}: {e}")
            continue

    return data_by_band


def fit_colorterm(nickel_mag, ref_mag_primary, color, snr_weight=True, snr=None):
    """
    Fit color term: nickel_mag = ref_mag_primary + c1 * color

    Returns dict with slope (c1), intercept (c0), RMS, and fit quality metrics.
    """
    # Filter for good photometry (high S/N)
    if snr is not None:
        good = snr > 10
    else:
        good = np.ones(len(nickel_mag), dtype=bool)

    # Also filter for reasonable colors (avoid outliers)
    good &= np.isfinite(nickel_mag) & np.isfinite(ref_mag_primary) & np.isfinite(color)
    good &= np.abs(color) < 3.0  # Reasonable stellar colors

    # Sigma clip to remove outliers
    residual_initial = nickel_mag[good] - ref_mag_primary[good]
    clipped = sigma_clip(residual_initial, sigma=3, maxiters=3)
    good[good] = ~clipped.mask

    if np.sum(good) < 50:
        return None

    # Fit: Δmag = c1 * color (+ c0 but we ignore intercept as it's handled by ZP)
    y = nickel_mag[good] - ref_mag_primary[good]
    x = color[good]

    # Weighted fit if S/N available
    if snr_weight and snr is not None:
        weights = snr[good] ** 2
        weights /= np.sum(weights)
    else:
        weights = None

    # Linear regression
    if weights is not None:
        # Weighted least squares
        W = np.sqrt(weights)
        x_w = x * W
        y_w = y * W
        slope, intercept, r_value, p_value, std_err = linregress(x_w, y_w)
    else:
        slope, intercept, r_value, p_value, std_err = linregress(x, y)

    # Compute residuals
    y_pred = slope * x + intercept
    residuals = y - y_pred
    rms = np.std(residuals)

    # Color span (for assessing fit quality)
    color_min, color_max = np.percentile(x, [5, 95])
    color_span = color_max - color_min

    return {
        "c1": slope,
        "c0": intercept,
        "c1_err": std_err,
        "rms": rms,
        "r_squared": r_value**2,
        "n_sources": np.sum(good),
        "color_span": color_span,
        "color_range": (float(np.min(x)), float(np.max(x))),
    }


def plot_colorterm_diagnostics(data_by_band, fits_by_band, output_dir):
    """Create diagnostic plots for color term validation."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    for band in data_by_band.keys():
        if band not in fits_by_band or fits_by_band[band] is None:
            continue

        data = data_by_band[band]
        fit = fits_by_band[band]

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            f"Band {band} - Color Term Validation", fontsize=14, fontweight="bold"
        )

        # Filter for plotting (high S/N)
        good = (
            (data["snr"] > 10)
            & np.isfinite(data["nickel_mag"])
            & np.isfinite(data["ref_mag_primary"])
            & np.isfinite(data["color"])
        )
        good &= np.abs(data["color"]) < 3.0

        nickel = data["nickel_mag"][good]
        ref_primary = data["ref_mag_primary"][good]
        color = data["color"][good]
        snr = data["snr"][good]

        # Plot 1: Color-magnitude diagram
        ax = axes[0, 0]
        scatter = ax.scatter(
            color,
            nickel - ref_primary,
            c=snr,
            cmap="viridis",
            alpha=0.3,
            s=2,
            vmin=10,
            vmax=50,
        )

        # Overplot fit
        color_grid = np.linspace(np.min(color), np.max(color), 100)
        fit_line = fit["c1"] * color_grid + fit["c0"]
        ax.plot(
            color_grid,
            fit_line,
            "r-",
            linewidth=2,
            label=f"c1={fit['c1']:.3f}±{fit['c1_err']:.3f}",
        )

        ax.set_xlabel(f"Color: {data['primary_band']} - {data['secondary_band']}")
        ax.set_ylabel(f"Δmag: Nickel_{band} - {data['primary_band']}")
        ax.set_title("Color Term Fit")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.colorbar(scatter, ax=ax, label="S/N")

        # Plot 2: Residuals vs color
        ax = axes[0, 1]
        residuals = (nickel - ref_primary) - (fit["c1"] * color + fit["c0"])
        ax.scatter(color, residuals, alpha=0.3, s=2, c="black")
        ax.axhline(0, color="red", linestyle="--", linewidth=2)
        ax.axhline(fit["rms"], color="red", linestyle=":", linewidth=1)
        ax.axhline(-fit["rms"], color="red", linestyle=":", linewidth=1)
        ax.set_xlabel(f"Color: {data['primary_band']} - {data['secondary_band']}")
        ax.set_ylabel("Residual (mag)")
        ax.set_title(f"Residuals (RMS={fit['rms']:.3f})")
        ax.grid(True, alpha=0.3)

        # Plot 3: Residual histogram
        ax = axes[1, 0]
        ax.hist(residuals, bins=50, alpha=0.7, edgecolor="black")
        ax.axvline(0, color="red", linestyle="--", linewidth=2)
        ax.set_xlabel("Residual (mag)")
        ax.set_ylabel("Number of Sources")
        ax.set_title(f"Residual Distribution (σ={fit['rms']:.3f})")
        ax.grid(True, alpha=0.3)

        # Plot 4: Summary
        ax = axes[1, 1]
        ax.axis("off")

        summary = f"""
Band: {band}
Reference: {data["primary_band"]} - {data["secondary_band"]}

COLOR TERM RESULTS:
  c1 (slope): {fit["c1"]:.4f} ± {fit["c1_err"]:.4f}
  c0 (offset): {fit["c0"]:.4f}
  RMS: {fit["rms"]:.3f} mag
  R²: {fit["r_squared"]:.4f}

FIT QUALITY:
  N sources: {fit["n_sources"]}
  N visits: {data["n_visits"]}
  Color span: {fit["color_span"]:.2f} mag
  Color range: [{fit["color_range"][0]:.2f}, {fit["color_range"][1]:.2f}]

FOR configs/colorterms.py:
  "{band}": Colorterm(
      primary="{data["primary_band"]}",
      secondary="{data["secondary_band"]}",
      c0={fit["c0"]:.6f},
      c1={fit["c1"]:.6f},
      c2=0.0,
  ),
        """

        ax.text(
            0.05,
            0.5,
            summary,
            fontsize=9,
            family="monospace",
            verticalalignment="center",
        )

        plt.tight_layout()
        plt.savefig(output_dir / f"colorterm_validation_{band}.png", dpi=150)
        print(f"\nSaved: {output_dir / f'colorterm_validation_{band}.png'}")
        plt.close()


def compare_with_synthetic(fits_by_band, synthetic_colorterms_file):
    """Compare empirical fits with synthetic color terms."""
    print("\n" + "=" * 80)
    print("COMPARING WITH SYNTHETIC COLOR TERMS")
    print("=" * 80)

    if not Path(synthetic_colorterms_file).exists():
        print(f"Synthetic color terms file not found: {synthetic_colorterms_file}")
        return

    # Load synthetic color terms
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "colorterms", synthetic_colorterms_file
    )
    ct_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ct_module)

    # Extract PS1 color terms
    synthetic_cts = {}
    if hasattr(ct_module, "config") and hasattr(ct_module.config, "data"):
        for catalog_name, catalog_data in ct_module.config.data.items():
            if "ps1" in catalog_name.lower():
                for band, ct in catalog_data.data.items():
                    synthetic_cts[band] = {
                        "c1": ct.c1,
                        "c0": ct.c0,
                        "primary": ct.primary,
                        "secondary": ct.secondary,
                    }

    if not synthetic_cts:
        print("Could not parse synthetic color terms")
        return

    # Compare
    print(
        f"\n{'Band':<6} {'Synthetic c1':<15} {'Empirical c1':<15} {'Difference':<12} {'Status'}"
    )
    print("-" * 70)

    for band in ["B", "V", "R", "I"]:
        if band in synthetic_cts and band in fits_by_band and fits_by_band[band]:
            syn_c1 = synthetic_cts[band]["c1"]
            emp_c1 = fits_by_band[band]["c1"]
            emp_err = fits_by_band[band]["c1_err"]
            diff = emp_c1 - syn_c1

            # Check if empirical is within 3-sigma of synthetic
            status = "✓ AGREE" if abs(diff) < 3 * emp_err else "✗ DIFFER"

            print(
                f"{band:<6} {syn_c1:>13.4f} {emp_c1:>13.4f}±{emp_err:.4f} {diff:>11.4f}   {status}"
            )
        else:
            print(f"{band:<6} {'N/A':<15} {'N/A':<15} {'N/A':<12}   -")


def main():
    parser = argparse.ArgumentParser(
        description="Validate and refine color terms from real data"
    )
    parser.add_argument("--repo", required=True, help="Butler repository")
    parser.add_argument(
        "--collection", required=True, help="Collection with calibrated data"
    )
    parser.add_argument("--bands", nargs="+", default=["B", "V", "R", "I"])
    parser.add_argument(
        "--output-dir", default="./colorterm_validation", help="Output directory"
    )
    parser.add_argument(
        "--synthetic-colorterms",
        default="./configs/colorterms.py",
        help="Path to synthetic colorterms.py for comparison",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("NICKEL COLOR TERM VALIDATION")
    print("=" * 80)
    print(f"Repository: {args.repo}")
    print(f"Collection: {args.collection}")
    print(f"Bands: {', '.join(args.bands)}")
    print()

    # Initialize butler
    try:
        butler = Butler(args.repo, collections=args.collection)
    except Exception as e:
        print(f"ERROR: Failed to open butler: {e}")
        sys.exit(1)

    # Get matched photometry
    data_by_band = get_matched_photometry(butler, args.collection, args.bands)

    if not data_by_band:
        print("\nERROR: No matched photometry found!")
        sys.exit(1)

    # Fit color terms
    print("\n" + "=" * 80)
    print("FITTING COLOR TERMS")
    print("=" * 80)

    fits_by_band = {}
    for band, data in data_by_band.items():
        print(f"\nFitting band {band}...")
        fit = fit_colorterm(
            data["nickel_mag"],
            data["ref_mag_primary"],
            data["color"],
            snr_weight=True,
            snr=data["snr"],
        )

        if fit:
            fits_by_band[band] = fit
            print(f"  c1 = {fit['c1']:.4f} ± {fit['c1_err']:.4f}")
            print(f"  RMS = {fit['rms']:.3f} mag")
            print(f"  R² = {fit['r_squared']:.4f}")
            print(f"  N sources = {fit['n_sources']}")
        else:
            print("  Failed to fit (insufficient data)")

    # Create plots
    print("\n" + "=" * 80)
    print("CREATING DIAGNOSTIC PLOTS")
    print("=" * 80)
    plot_colorterm_diagnostics(data_by_band, fits_by_band, args.output_dir)

    # Compare with synthetic
    if Path(args.synthetic_colorterms).exists():
        compare_with_synthetic(fits_by_band, args.synthetic_colorterms)

    # Print summary
    print("\n" + "=" * 80)
    print("RECOMMENDED COLOR TERMS FOR configs/colorterms.py")
    print("=" * 80)
    print("\ndata={")
    for band in args.bands:
        if band in fits_by_band and fits_by_band[band]:
            fit = fits_by_band[band]
            data = data_by_band[band]
            print(f'    "{band}": Colorterm(')
            print(f'        primary="{data["primary_band"]}",')
            print(f'        secondary="{data["secondary_band"]}",')
            print(f"        c0={fit['c0']:.6f},")
            print(f"        c1={fit['c1']:.6f},  # ±{fit['c1_err']:.6f}")
            print("        c2=0.0,")
            print("    ),")
    print("}")

    print("\n" + "=" * 80)
    print("DONE!")
    print("=" * 80)


if __name__ == "__main__":
    main()
