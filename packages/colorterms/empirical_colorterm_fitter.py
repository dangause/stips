#!/usr/bin/env python3
"""
Empirical color term fitter using matched Nickel + Monster photometry.

This approach doesn't need throughputs - it fits color terms directly
from matched star catalogs.

Usage:
    python empirical_colorterm_fitter.py \
        --butler-repo /path/to/repo \
        --nickel-visit 12345 \
        --nickel-band R \
        --output-dir ./empirical_colorterms
"""

import argparse
import os
import warnings

import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import least_squares

try:
    from lsst.daf.butler import Butler

    LSST_AVAILABLE = True
except ImportError:
    LSST_AVAILABLE = False
    print("Warning: LSST stack not available. Using simplified mode.")


class EmpiricalColortermFitter:
    """Fit color terms empirically from matched catalogs."""

    def __init__(self, n_nodes=4):
        self.n_nodes = n_nodes

        # Mapping from Nickel to Monster bands
        self.nickel_to_monster = {
            "B": "g",
            "V": "g",
            "R": "r",
            "I": "i",
        }

        # Color definitions (for Monster)
        self.color_bands = {
            "B": ("g", "r"),
            "V": ("g", "r"),
            "R": ("r", "i"),
            "I": ("r", "i"),
        }

    def load_matched_catalog(self, butler_repo, visit, detector=0):
        """Load matched Nickel + Monster photometry from Butler.

        Parameters
        ----------
        butler_repo : str
            Path to Butler repository
        visit : int
            Nickel visit ID
        detector : int
            Detector ID (default 0 for Nickel)

        Returns
        -------
        matched_table : astropy.table.Table
            Table with matched photometry
        """
        if not LSST_AVAILABLE:
            raise RuntimeError("LSST stack required for Butler access")

        butler = Butler(butler_repo)

        # Load the matched photometry catalog
        dataId = {"visit": visit, "detector": detector, "instrument": "Nickel"}

        # Find the collection automatically
        from lsst.daf.butler import CollectionType

        collections = list(
            butler.registry.queryCollections(
                "Nickel/*/processCcd/*/run", collectionTypes={CollectionType.RUN}
            )
        )
        if not collections:
            raise RuntimeError("No Nickel processCcd collections found")

        sources = butler.get(
            "single_visit_star_ref_match_photom", dataId, collections=collections[0]
        )

        matched_table = sources

        return matched_table

    def load_from_files(self, nickel_file, monster_file, match_radius=1.0):
        """Load and match catalogs from FITS/CSV files.

        Parameters
        ----------
        nickel_file : str
            Path to Nickel catalog
        monster_file : str
            Path to Monster catalog
        match_radius : float
            Match radius in arcsec

        Returns
        -------
        matched_table : astropy.table.Table
            Table with matched photometry
        """
        from astropy import units as u
        from astropy.coordinates import SkyCoord
        from astropy.table import Table

        # Load catalogs
        nickel_cat = Table.read(nickel_file)
        monster_cat = Table.read(monster_file)

        # Match
        nickel_coords = SkyCoord(
            ra=nickel_cat["ra"] * u.deg, dec=nickel_cat["dec"] * u.deg
        )
        monster_coords = SkyCoord(
            ra=monster_cat["coord_ra"] * u.deg, dec=monster_cat["coord_dec"] * u.deg
        )

        idx, d2d, _ = nickel_coords.match_to_catalog_sky(monster_coords)

        # Select matches within radius
        matched = d2d < match_radius * u.arcsec

        # Create matched table
        matched_table = Table()

        # Copy Nickel data
        for col in nickel_cat.colnames:
            matched_table[f"nickel_{col}"] = nickel_cat[col][matched]

        # Copy matched Monster data
        for col in monster_cat.colnames:
            matched_table[f"monster_{col}"] = monster_cat[col][idx[matched]]

        matched_table["match_distance"] = d2d[matched].arcsec

        print(f"Matched {len(matched_table)} / {len(nickel_cat)} sources")

        return matched_table

    def fit_colorterm(self, matched_table, nickel_band, color_range=None):
        """Fit color term from matched photometry.

        Parameters
        ----------
        matched_table : astropy.table.Table
            Matched catalog
        nickel_band : str
            Nickel band (B, V, R, or I)
        color_range : tuple, optional
            (min, max) color for fitting

        Returns
        -------
        result : dict
            Fitting results including spline parameters
        """
        monster_band = self.nickel_to_monster[nickel_band]
        color_band1, color_band2 = self.color_bands[nickel_band]

        # Extract photometry
        # Adapt column names based on what's in your table
        possible_nickel_cols = [
            f"nickel_{nickel_band}_flux",
            "base_PsfFlux_instFlux",
            "instFlux",
            "psfFlux",
            "calibFlux",
        ]

        possible_monster_cols = [
            f"monster_ComCam_{monster_band}_flux",
            f"monster_{monster_band}_flux",
            f"ref_{monster_band}_flux",
            "refFlux",
        ]

        # Find the right columns
        nickel_flux_col = None
        for col in possible_nickel_cols:
            if col in matched_table.colnames:
                nickel_flux_col = col
                break

        monster_band_col = None
        for col in possible_monster_cols:
            if col in matched_table.colnames:
                monster_band_col = col
                break

        if nickel_flux_col is None or monster_band_col is None:
            print("Available columns:", matched_table.colnames)
            raise ValueError("Could not find flux columns in matched table")

        # Get fluxes
        flux_nickel = np.array(matched_table[nickel_flux_col])
        flux_monster_band = np.array(matched_table[monster_band_col])

        # Get color bands for Monster
        flux_monster_1 = np.array(matched_table[f"monster_ComCam_{color_band1}_flux"])
        flux_monster_2 = np.array(matched_table[f"monster_ComCam_{color_band2}_flux"])

        # Compute color
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            color = -2.5 * np.log10(flux_monster_1 / flux_monster_2)

        # Select good measurements
        good = (
            np.isfinite(flux_nickel)
            & np.isfinite(flux_monster_band)
            & np.isfinite(color)
            & (flux_nickel > 0)
            & (flux_monster_band > 0)
        )

        flux_nickel = flux_nickel[good]
        flux_monster_band = flux_monster_band[good]
        color = color[good]

        if len(color) < 50:
            warnings.warn(f"Only {len(color)} good matches - need more for robust fit!")

        # Determine color range
        if color_range is None:
            color_range = (np.percentile(color, 5), np.percentile(color, 95))

        # Select stars in color range
        in_range = (color >= color_range[0]) & (color <= color_range[1])

        print(f"Using {np.sum(in_range)} / {len(color)} stars")
        print(f"Color range: {color_range[0]:.2f} to {color_range[1]:.2f}")

        color_fit = color[in_range]
        flux_nickel_fit = flux_nickel[in_range]
        flux_monster_fit = flux_monster_band[in_range]

        # Normalize fluxes
        ratio = np.median(flux_nickel_fit / flux_monster_fit)
        flux_nickel_norm = flux_nickel_fit / ratio

        # Create spline nodes
        nodes = np.linspace(color_range[0], color_range[1], self.n_nodes)

        # Fit spline
        def model(params):
            spline_values = params[:-1]
            flux_offset = params[-1]

            spline = CubicSpline(nodes, spline_values, bc_type="clamped")
            correction = spline(color_fit)

            model_flux = (flux_monster_fit - flux_offset) * correction
            return model_flux

        def residuals(params):
            model_flux = model(params)
            resid = (flux_nickel_norm - model_flux) / flux_nickel_norm
            return resid

        # Initial guess
        p0 = np.ones(self.n_nodes + 1)
        p0[-1] = 0.0  # flux offset

        # Fit
        result = least_squares(
            residuals,
            p0,
            method="trf",
            loss="soft_l1",
            f_scale=0.1,
        )

        spline_values = result.x[:-1]
        flux_offset = result.x[-1]

        # Compute RMS
        final_model = model(result.x)
        rms = np.sqrt(
            np.mean((flux_nickel_norm - final_model) ** 2)
            / np.mean(flux_nickel_norm**2)
        )

        print(f"Fit RMS: {rms*100:.2f}%")
        print(f"Flux offset: {flux_offset:.6f}")

        return {
            "nickel_band": nickel_band,
            "monster_band": monster_band,
            "color_bands": (color_band1, color_band2),
            "nodes": nodes,
            "spline_values": spline_values,
            "flux_offset": flux_offset,
            "color_range": color_range,
            "rms": rms,
            "n_stars": len(color_fit),
            # Save data for plotting
            "color": color_fit,
            "flux_nickel": flux_nickel_norm,
            "flux_monster": flux_monster_fit,
        }

    def plot_colorterm(self, result, output_file):
        """Make QA plot of color term fit."""

        ratio = result["flux_monster"] / result["flux_nickel"]

        # Evaluate spline
        spline = CubicSpline(
            result["nodes"], result["spline_values"], bc_type="clamped"
        )
        xvals = np.linspace(result["nodes"][0], result["nodes"][-1], 1000)
        yvals = 1.0 / spline(xvals)

        plt.figure(figsize=(10, 6))

        # Plot data
        plt.scatter(
            result["color"], ratio, alpha=0.3, s=20, c="k", label="Matched stars"
        )

        # Plot fit
        plt.plot(xvals, yvals, "r-", lw=2, label="Spline fit")

        # Plot nodes
        node_corrections = spline(result["nodes"])
        plt.plot(
            result["nodes"], 1.0 / node_corrections, "ro", ms=8, label="Spline nodes"
        )

        plt.xlabel(
            f"{result['color_bands'][0]} - {result['color_bands'][1]} (Monster)",
            fontsize=12,
        )
        plt.ylabel(
            f"Monster_{result['monster_band']} / Nickel_{result['nickel_band']}",
            fontsize=12,
        )
        plt.title(
            f"Empirical Color Term: Nickel {result['nickel_band']}",
            fontsize=14,
            fontweight="bold",
        )
        plt.legend(loc="best")
        plt.grid(alpha=0.3)

        # Add stats
        text = f"N = {result['n_stars']}\nRMS = {result['rms']*100:.2f}%"
        plt.text(
            0.02,
            0.98,
            text,
            transform=plt.gca().transAxes,
            verticalalignment="top",
            fontsize=10,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

        plt.tight_layout()
        plt.savefig(output_file, dpi=150)
        plt.close()

        print(f"Saved plot: {output_file}")

    def save_results(self, result, yaml_file):
        """Save results to YAML."""
        import yaml

        data = {
            "source_catalog": "Monster",
            "target_catalog": "Nickel",
            "primary_field": f"monster_ComCam_{result['color_bands'][0]}_flux",
            "secondary_field": f"monster_ComCam_{result['color_bands'][1]}_flux",
            "band_field": f"nickel_{result['nickel_band']}_flux",
            "nodes": result["nodes"].tolist(),
            "spline_values": result["spline_values"].tolist(),
            "flux_offset": float(result["flux_offset"]),
            "fit_rms": float(result["rms"]),
            "n_stars_used": int(result["n_stars"]),
            "color_range": result["color_range"],
            "method": "empirical_from_matched_catalogs",
        }

        with open(yaml_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        print(f"Saved YAML: {yaml_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Fit empirical color terms from matched Nickel + Monster photometry"
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--butler-repo", help="Butler repository path")
    input_group.add_argument(
        "--files",
        nargs=2,
        metavar=("NICKEL", "MONSTER"),
        help="Nickel and Monster catalog files",
    )

    parser.add_argument(
        "--nickel-visit", type=int, help="Nickel visit ID (for Butler mode)"
    )
    parser.add_argument(
        "--nickel-band",
        required=True,
        choices=["B", "V", "R", "I"],
        help="Nickel band to fit",
    )
    parser.add_argument("--detector", type=int, default=0, help="Detector ID")
    parser.add_argument(
        "--match-radius",
        type=float,
        default=1.0,
        help="Match radius in arcsec (file mode)",
    )
    parser.add_argument("--n-nodes", type=int, default=4, help="Number of spline nodes")
    parser.add_argument(
        "--output-dir", default="./empirical_colorterms", help="Output directory"
    )
    parser.add_argument("--plot", action="store_true", help="Make QA plots")

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Create fitter
    fitter = EmpiricalColortermFitter(n_nodes=args.n_nodes)

    # Load data
    if args.butler_repo:
        if args.nickel_visit is None:
            parser.error("--nickel-visit required with --butler-repo")
        print(f"Loading from Butler: visit {args.nickel_visit}")
        matched_table = fitter.load_matched_catalog(
            args.butler_repo, args.nickel_visit, args.detector
        )
    else:
        nickel_file, monster_file = args.files
        print(
            f"Loading from files:\n  Nickel: {nickel_file}\n  Monster: {monster_file}"
        )
        matched_table = fitter.load_from_files(
            nickel_file, monster_file, args.match_radius
        )

    # Fit color term
    print(f"\nFitting color term for band {args.nickel_band}...")
    result = fitter.fit_colorterm(matched_table, args.nickel_band)

    # Save results
    yaml_file = os.path.join(
        args.output_dir, f"empirical_nickel_{args.nickel_band}_colorterm.yaml"
    )
    fitter.save_results(result, yaml_file)

    # Plot
    if args.plot:
        plot_file = os.path.join(
            args.output_dir, f"empirical_nickel_{args.nickel_band}_colorterm.png"
        )
        fitter.plot_colorterm(result, plot_file)

    print("\nDone!")
    print(f"Results saved to: {args.output_dir}/")


if __name__ == "__main__":
    main()
