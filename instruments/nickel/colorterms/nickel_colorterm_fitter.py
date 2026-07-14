#!/usr/bin/env python3
"""
Spline-based color term fitter for Nickel telescope to Monster catalog.

This adapts the Monster's sophisticated spline fitting approach to compute
accurate color transformations from Nickel BVRI to Monster grizy bands.

Usage:
    python nickel_colorterm_fitter.py --output-dir ./colorterms --plots
"""

import argparse
import os
import warnings
from dataclasses import dataclass
from typing import List

import astropy.table
import fitsio
import matplotlib.pyplot as plt
import numpy as np
import scipy.integrate as integrate
import scipy.interpolate as interpolate
from astropy import units
from astroquery.svo_fps import SvoFps

# ============================================================================
# Spline Fitting Classes (adapted from Monster)
# ============================================================================


class ColortermSpline:
    """A spline-based color term transformation."""

    def __init__(
        self,
        source_name,
        target_name,
        primary_field,
        secondary_field,
        band_field,
        nodes,
        spline_values,
        flux_offset=0.0,
    ):
        self.source_name = source_name
        self.target_name = target_name
        self.primary_field = primary_field
        self.secondary_field = secondary_field
        self.band_field = band_field
        self.nodes = np.array(nodes)
        self.spline_values = np.array(spline_values)
        self.flux_offset = flux_offset

        # Create the spline interpolator
        from scipy.interpolate import CubicSpline

        self.spline = CubicSpline(self.nodes, self.spline_values, bc_type="clamped")

    def apply(self, flux_primary, flux_secondary, flux_band):
        """Apply the color term correction."""
        # Compute color
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            color = -2.5 * np.log10(flux_primary / flux_secondary)

        # Get correction factor from spline
        correction = self.spline(color)

        # Apply correction
        return (flux_band - self.flux_offset) / correction

    def save_yaml(self, filename, overwrite=False):
        """Save to YAML format compatible with LSST stack."""
        if os.path.exists(filename) and not overwrite:
            raise FileExistsError(f"{filename} exists. Use overwrite=True.")

        import yaml

        data = {
            "source_catalog": self.source_name,
            "target_catalog": self.target_name,
            "primary_field": self.primary_field,
            "secondary_field": self.secondary_field,
            "band_field": self.band_field,
            "nodes": self.nodes.tolist(),
            "spline_values": self.spline_values.tolist(),
            "flux_offset": float(self.flux_offset),
        }

        with open(filename, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        print(f"Saved color term to {filename}")

    def save_lsst_config(self, filename, overwrite=False):
        """Save in LSST config.py format for instruments/nickel/configs/colorterms.py"""
        if os.path.exists(filename) and not overwrite:
            raise FileExistsError(f"{filename} exists. Use overwrite=True.")

        # For now, we'll convert spline to polynomial approximation
        # A better approach would be to implement spline color terms in the stack
        color_range = [self.nodes[0], self.nodes[-1]]
        colors = np.linspace(color_range[0], color_range[1], 100)
        corrections = self.spline(colors)

        # Fit a 2nd order polynomial to the spline for LSST stack compatibility
        coeffs = np.polyfit(colors, corrections, 2)

        # Note: LSST colorterm is applied as: m_inst = m_ref - c0 - c1*color - c2*color^2
        # Our correction is multiplicative, so we convert to additive in mags
        # This is approximate!

        content = f"""# Color term for {self.band_field} from {self.source_name} to {self.target_name}
# Generated from spline fit with {len(self.nodes)} nodes
# Color range: {color_range[0]:.3f} to {color_range[1]:.3f}
# NOTE: This is a polynomial approximation to the spline fit
# Flux offset: {self.flux_offset:.6f}

# Polynomial coefficients (c0 + c1*color + c2*color^2)
# c0 = {coeffs[2]:.6f}
# c1 = {coeffs[1]:.6f}
# c2 = {coeffs[0]:.6f}

# Spline nodes and values for reference:
# nodes = {self.nodes.tolist()}
# values = {self.spline_values.tolist()}
"""

        with open(filename, "w") as f:
            f.write(content)

        print(f"Saved LSST config info to {filename}")

        return coeffs


class ColortermSplineFitter:
    """Fit a spline color term between two catalogs."""

    def __init__(
        self, mag_color, flux_target, flux_source, nodes, fit_flux_offset=True
    ):
        self.mag_color = np.array(mag_color)
        self.flux_target = np.array(flux_target)
        self.flux_source = np.array(flux_source)
        self.nodes = np.array(nodes)
        self.fit_flux_offset = fit_flux_offset

        # Check for valid data
        valid = (
            np.isfinite(mag_color)
            & np.isfinite(flux_target)
            & np.isfinite(flux_source)
            & (flux_target > 0)
            & (flux_source > 0)
        )

        self.mag_color = self.mag_color[valid]
        self.flux_target = self.flux_target[valid]
        self.flux_source = self.flux_source[valid]

        if len(self.mag_color) < len(nodes):
            raise ValueError(
                f"Not enough valid data points ({len(self.mag_color)}) "
                f"for {len(nodes)} nodes"
            )

    def estimate_p0(self):
        """Estimate initial parameters."""
        n_params = len(self.nodes)
        if self.fit_flux_offset:
            n_params += 1

        # Initial guess: correction factors near 1
        p0 = np.ones(n_params)

        # If fitting offset, initialize to median difference
        if self.fit_flux_offset:
            p0[-1] = np.median(self.flux_source - self.flux_target)

        return p0

    def _model(self, params):
        """Compute model fluxes."""
        if self.fit_flux_offset:
            spline_values = params[:-1]
            flux_offset = params[-1]
        else:
            spline_values = params
            flux_offset = 0.0

        from scipy.interpolate import CubicSpline

        spline = CubicSpline(self.nodes, spline_values, bc_type="clamped")

        correction = spline(self.mag_color)
        model_flux = (self.flux_source - flux_offset) * correction

        return model_flux

    def _residuals(self, params):
        """Compute residuals."""
        model_flux = self._model(params)
        residuals = (self.flux_target - model_flux) / self.flux_target
        return residuals

    def fit(self, p0):
        """Perform the fit."""
        from scipy.optimize import least_squares

        result = least_squares(
            self._residuals,
            p0,
            method="trf",
            loss="soft_l1",
            f_scale=0.1,
            verbose=0,
        )

        if not result.success:
            warnings.warn(f"Fit did not converge: {result.message}")

        return result.x


# ============================================================================
# Catalog Information Classes
# ============================================================================


@dataclass
class CatalogInfo:
    """Base class for catalog information."""

    name: str
    bands: List[str]

    def get_flux_field(self, band):
        """Get the flux field name for a band."""
        raise NotImplementedError

    def get_color_bands(self, band):
        """Get the two bands used to define color for this band."""
        raise NotImplementedError

    def get_color_range(self, band):
        """Get the valid color range for this band."""
        raise NotImplementedError


class NickelInfo(CatalogInfo):
    """Information about Nickel photometric system."""

    def __init__(self):
        super().__init__(name="Nickel", bands=["B", "V", "R", "I"])

        # Color definitions (primary - secondary)
        self.color_bands = {
            "B": ("B", "V"),
            "V": ("B", "V"),
            "R": ("V", "R"),
            "I": ("R", "I"),
        }

        # Color ranges for fitting (mag)
        self.color_ranges = {
            "B": (-0.5, 2.5),  # B-V color
            "V": (-0.5, 2.5),  # B-V color
            "R": (-0.5, 1.5),  # V-R color
            "I": (-0.5, 1.5),  # R-I color
        }

    def get_flux_field(self, band):
        return f"nickel_{band}_flux"

    def get_color_bands(self, band):
        return self.color_bands[band]

    def get_color_range(self, band):
        return self.color_ranges[band]

    def get_mag_colors(self, catalog, band):
        """Compute colors for this band."""
        band_1, band_2 = self.get_color_bands(band)
        flux_1 = catalog[self.get_flux_field(band_1)]
        flux_2 = catalog[self.get_flux_field(band_2)]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            color = -2.5 * np.log10(flux_1 / flux_2)

        return color


class MonsterInfo(CatalogInfo):
    """Information about Monster catalog."""

    def __init__(self):
        super().__init__(name="Monster", bands=["g", "r", "i", "z", "y"])

        # Map Nickel bands to Monster bands for color terms
        self.nickel_to_monster_map = {
            "B": "g",
            "V": "g",
            "R": "r",
            "I": "i",
        }

        # Use Monster g-r, r-i colors
        self.color_bands = {
            "B": ("g", "r"),
            "V": ("g", "r"),
            "R": ("r", "i"),
            "I": ("r", "i"),
        }

        self.color_ranges = {
            "B": (-0.5, 2.0),
            "V": (-0.5, 2.0),
            "R": (-0.5, 1.5),
            "I": (-0.5, 1.5),
        }

    def get_flux_field(self, band):
        return f"monster_ComCam_{band}_flux"

    def get_color_bands(self, band):
        """Get color bands - using same colors as Nickel for consistency."""
        # For transformation, we use Monster colors corresponding to Nickel colors
        nickel_band = band  # Assume band is the Nickel band
        return self.color_bands.get(nickel_band, ("g", "r"))

    def get_color_range(self, band):
        return self.color_ranges.get(band, (-0.5, 2.0))

    def get_mag_colors(self, catalog, band):
        """Compute colors for this band."""
        band_1, band_2 = self.get_color_bands(band)
        flux_1 = catalog[self.get_flux_field(band_1)]
        flux_2 = catalog[self.get_flux_field(band_2)]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            color = -2.5 * np.log10(flux_1 / flux_2)

        return color


# ============================================================================
# Synthetic Photometry Engine
# ============================================================================


class SyntheticPhotometry:
    """Perform synthetic photometry on stellar templates."""

    def __init__(self):
        self.templates = None
        self.nickel_throughputs = {}
        self.monster_throughputs = {}

    def load_stellar_templates(self, template_file=None):
        """Load stellar templates from FGCM package."""
        if template_file is None:
            # Try to find FGCM templates
            try:
                import importlib.resources

                template_file = importlib.resources.files(
                    "fgcm.data.templates"
                ).joinpath("stellar_templates_master.fits")
            except Exception:
                raise FileNotFoundError(
                    "Could not find stellar templates. "
                    "Please install fgcm package or provide template_file path."
                )

        print(f"Loading stellar templates from {template_file}")

        fits = fitsio.FITS(str(template_file))
        fits.update_hdu_list()

        ext_names = []
        for hdu in fits.hdu_list:
            ext_name = hdu.get_extname()
            if "TEMPLATE_" in ext_name:
                ext_names.append(ext_name)

        self.templates = {}
        for i in range(len(ext_names)):
            self.templates[i] = fits[ext_names[i]].read(lower=True)

        fits.close()

        print(f"Loaded {len(self.templates)} stellar templates")

        return self.templates

    def load_nickel_throughputs_from_svo(self):
        """Download Nickel throughputs from SVO Filter Profile Service."""
        svo_ids = {
            "B": "LICK/LICK.B",
            "V": "LICK/LICK.V",
            "R": "LICK/LICK.R",
            "I": "LICK/LICK.I",
        }

        print("Downloading Nickel filter throughputs from SVO...")

        for band, svo_id in svo_ids.items():
            print(f"  Downloading {band}...")
            tab = SvoFps.get_transmission_data(svo_id)

            # Convert to Angstroms (SVO returns Angstroms)
            wavelength = np.array(tab["Wavelength"], dtype=float)
            throughput = np.array(tab["Transmission"], dtype=float)

            # Clean data
            valid = (
                np.isfinite(wavelength) & np.isfinite(throughput) & (throughput >= 0)
            )
            wavelength = wavelength[valid]
            throughput = throughput[valid]

            # Sort by wavelength
            sort_idx = np.argsort(wavelength)
            wavelength = wavelength[sort_idx]
            throughput = throughput[sort_idx]

            self.nickel_throughputs[band] = astropy.table.Table(
                {
                    "wavelength": wavelength * units.Angstrom,
                    "throughput": throughput,
                }
            )

        print("Nickel throughputs loaded")

        return self.nickel_throughputs

    def load_monster_throughputs(self, throughput_dir):
        """Load Monster/ComCam throughputs."""
        bands = ["g", "r", "i", "z", "y"]

        print(f"Loading Monster throughputs from {throughput_dir}...")

        for band in bands:
            # Try multiple file patterns
            possible_files = [
                os.path.join(throughput_dir, f"total_{band}.dat"),
                os.path.join(throughput_dir, f"total_comcam_{band}.ecsv"),
                os.path.join(throughput_dir, f"total_comcam_{band}.dat"),
            ]

            loaded = False
            for filepath in possible_files:
                if os.path.exists(filepath):
                    print(f"  Loading {band} from {filepath}...")

                    if filepath.endswith(".ecsv"):
                        tput = astropy.table.Table.read(filepath, format="ascii.ecsv")
                    else:
                        tput = astropy.table.Table.read(filepath, format="ascii")
                        # Standardize column names
                        if "col1" in tput.colnames:
                            tput.rename_column("col1", "wavelength")
                        if "col2" in tput.colnames:
                            tput.rename_column("col2", "throughput")

                    # Ensure wavelength units
                    if not hasattr(tput["wavelength"], "unit"):
                        # Assume nm if no unit
                        tput["wavelength"] = tput["wavelength"] * units.nm

                    self.monster_throughputs[band] = tput
                    loaded = True
                    break

            if not loaded:
                warnings.warn(f"Could not find Monster throughput for band {band}")

        print("Monster throughputs loaded")

        return self.monster_throughputs

    def compute_synthetic_photometry(self):
        """Compute synthetic photometry for both Nickel and Monster."""
        if self.templates is None:
            raise ValueError("Must load templates first")

        n_templates = len(self.templates)

        # Initialize Nickel catalog
        nickel_info = NickelInfo()
        nickel_dtype = []
        for band in nickel_info.bands:
            flux_field = nickel_info.get_flux_field(band)
            nickel_dtype.append((flux_field, "f8"))
            nickel_dtype.append((flux_field + "Err", "f8"))

        synth_nickel_cat = np.zeros(n_templates, dtype=nickel_dtype)

        print("Computing Nickel synthetic photometry...")
        for i in range(n_templates):
            for band in nickel_info.bands:
                flux = self._integrate_sed(
                    self.templates[i], self.nickel_throughputs[band]
                )
                synth_nickel_cat[nickel_info.get_flux_field(band)][i] = flux

        # Initialize Monster catalog
        monster_info = MonsterInfo()
        monster_dtype = []
        for band in monster_info.bands:
            flux_field = monster_info.get_flux_field(band)
            monster_dtype.append((flux_field, "f8"))
            monster_dtype.append((flux_field + "Err", "f8"))

        synth_monster_cat = np.zeros(n_templates, dtype=monster_dtype)

        print("Computing Monster synthetic photometry...")
        for i in range(n_templates):
            for band in monster_info.bands:
                flux = self._integrate_sed(
                    self.templates[i], self.monster_throughputs[band]
                )
                synth_monster_cat[monster_info.get_flux_field(band)][i] = flux

        return synth_nickel_cat, synth_monster_cat

    def _integrate_sed(self, template, throughput):
        """Integrate SED through a filter."""
        # Template: lambda in Angstrom, flux in f_lambda
        template_lambda = template["lambda"]  # Angstrom
        template_f_lambda = template["flux"]

        # Convert to f_nu (for AB magnitudes)
        template_f_nu = template_f_lambda * template_lambda * template_lambda

        # Interpolate template onto throughput wavelength grid
        int_func = interpolate.interp1d(
            template_lambda,
            template_f_nu,
            bounds_error=False,
            fill_value=(template_f_nu[0], template_f_nu[-1]),
        )

        # Get throughput wavelength in Angstroms
        tput_lambda = throughput["wavelength"].to(units.Angstrom).value
        f_nu = int_func(tput_lambda)

        # Integrate
        num = integrate.simpson(
            y=f_nu * throughput["throughput"] / tput_lambda,
            x=tput_lambda,
        )
        denom = integrate.simpson(
            y=throughput["throughput"] / tput_lambda,
            x=tput_lambda,
        )

        # Return flux in arbitrary units (ratios matter, not absolute values)
        return num / denom


# ============================================================================
# Main Fitter
# ============================================================================


class NickelSplineMeasurer:
    """Measure spline-based color terms from Nickel to Monster."""

    def __init__(self, monster_throughput_dir, n_nodes=4):
        self.monster_throughput_dir = monster_throughput_dir
        self.n_nodes = n_nodes
        self.synth = SyntheticPhotometry()
        self.nickel_info = NickelInfo()
        self.monster_info = MonsterInfo()

    def measure_color_terms(
        self, bands=None, output_dir=".", do_plots=True, overwrite=False
    ):
        """Measure color terms for all Nickel bands.

        Parameters
        ----------
        bands : list, optional
            Nickel bands to process. Default is all: ["B", "V", "R", "I"]
        output_dir : str
            Directory to save outputs
        do_plots : bool
            Make QA plots
        overwrite : bool
            Overwrite existing files

        Returns
        -------
        colorterm_files : dict
            Dictionary mapping band to output filename
        """
        if bands is None:
            bands = self.nickel_info.bands

        os.makedirs(output_dir, exist_ok=True)

        # Load everything
        print("=" * 70)
        print("Loading stellar templates and throughputs...")
        print("=" * 70)

        self.synth.load_stellar_templates()
        self.synth.load_nickel_throughputs_from_svo()
        self.synth.load_monster_throughputs(self.monster_throughput_dir)

        print("\n" + "=" * 70)
        print("Computing synthetic photometry...")
        print("=" * 70)

        synth_nickel_cat, synth_monster_cat = self.synth.compute_synthetic_photometry()

        print(f"\nSynthesized {len(synth_nickel_cat)} stars")

        # Now fit color terms for each band
        colorterm_files = {}

        for nickel_band in bands:
            print("\n" + "=" * 70)
            print(f"Fitting color term for Nickel {nickel_band}")
            print("=" * 70)

            # Get corresponding Monster band
            monster_band = self.monster_info.nickel_to_monster_map[nickel_band]

            # Get color (using Monster colors for consistency)
            mag_color = self.monster_info.get_mag_colors(synth_monster_cat, nickel_band)

            # Get fluxes
            flux_nickel = synth_nickel_cat[self.nickel_info.get_flux_field(nickel_band)]
            flux_monster = synth_monster_cat[
                self.monster_info.get_flux_field(monster_band)
            ]

            # Get color range
            color_range = self.monster_info.get_color_range(nickel_band)

            # Select stars in color range
            selected = (
                (mag_color > color_range[0])
                & (mag_color < color_range[1])
                & np.isfinite(mag_color)
                & (flux_nickel > 0)
                & (flux_monster > 0)
            )

            print(
                f"Selected {np.sum(selected)} / {len(selected)} stars in color range "
                f"{color_range[0]:.2f} to {color_range[1]:.2f}"
            )

            # Normalize to match median flux over color range
            ratio = np.median(flux_nickel[selected] / flux_monster[selected])
            flux_nickel_norm = flux_nickel / ratio

            print(f"Normalization ratio: {ratio:.4f}")

            # Create nodes
            nodes = np.linspace(color_range[0], color_range[1], self.n_nodes)
            print(f"Using {self.n_nodes} nodes: {nodes}")

            # Fit spline
            fitter = ColortermSplineFitter(
                mag_color[selected],
                flux_nickel_norm[selected],
                flux_monster[selected],
                nodes,
                fit_flux_offset=True,
            )

            p0 = fitter.estimate_p0()
            pars = fitter.fit(p0)

            spline_values = pars[:-1]
            flux_offset = pars[-1]

            print(f"Flux offset: {flux_offset:.6f}")
            print(f"Spline values: {spline_values}")

            # Create colorterm object
            band_1, band_2 = self.monster_info.get_color_bands(nickel_band)

            colorterm = ColortermSpline(
                self.monster_info.name,
                self.nickel_info.name,
                self.monster_info.get_flux_field(band_1),
                self.monster_info.get_flux_field(band_2),
                self.nickel_info.get_flux_field(nickel_band),
                nodes,
                spline_values,
                flux_offset,
            )

            # Save outputs
            yaml_file = os.path.join(
                output_dir,
                f"nickel_{nickel_band}_to_monster_{monster_band}_colorterm.yaml",
            )
            colorterm.save_yaml(yaml_file, overwrite=overwrite)

            config_file = os.path.join(
                output_dir, f"nickel_{nickel_band}_to_monster_{monster_band}_config.txt"
            )
            colorterm.save_lsst_config(config_file, overwrite=overwrite)

            colorterm_files[nickel_band] = yaml_file

            # Make plot
            if do_plots:
                self._make_qa_plot(
                    mag_color[selected],
                    flux_monster[selected],
                    flux_nickel_norm[selected],
                    colorterm,
                    nickel_band,
                    monster_band,
                    output_dir,
                )

        # Create summary config file
        self._write_summary_config(colorterm_files, output_dir, overwrite)

        return colorterm_files

    def _make_qa_plot(
        self,
        mag_color,
        flux_monster,
        flux_nickel,
        colorterm,
        nickel_band,
        monster_band,
        output_dir,
    ):
        """Make QA plot showing the color term fit."""

        ratio = flux_monster / flux_nickel
        ratio_extent = np.nanpercentile(ratio, [0.5, 99.5])

        band_1, band_2 = self.monster_info.get_color_bands(nickel_band)
        xlabel = f"{band_1} - {band_2}"
        ylabel = f"Monster_{monster_band} / Nickel_{nickel_band}"

        # Evaluate spline
        xvals = np.linspace(colorterm.nodes[0], colorterm.nodes[-1], 1000)
        yvals = 1.0 / colorterm.spline(xvals)

        plt.figure(figsize=(10, 6))

        # Plot data
        plt.plot(mag_color, ratio, "k.", alpha=0.3, ms=4, label="Synthetic stars")

        # Plot spline fit
        plt.plot(xvals, yvals, "r-", lw=2, label="Spline fit")

        # Plot nodes
        node_corrections = colorterm.spline(colorterm.nodes)
        plt.plot(
            colorterm.nodes, 1.0 / node_corrections, "ro", ms=8, label="Spline nodes"
        )

        plt.xlim(colorterm.nodes[0], colorterm.nodes[-1])
        plt.ylim(ratio_extent[0], ratio_extent[1])
        plt.xlabel(xlabel, fontsize=12)
        plt.ylabel(ylabel, fontsize=12)
        plt.title(
            f"Nickel {nickel_band} → Monster {monster_band} Color Term",
            fontsize=14,
            fontweight="bold",
        )
        plt.legend(loc="best")
        plt.grid(alpha=0.3)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            plt.tight_layout()

        plot_file = os.path.join(
            output_dir, f"nickel_{nickel_band}_to_monster_{monster_band}_colorterm.png"
        )
        plt.savefig(plot_file, dpi=150)
        plt.close()

        print(f"Saved QA plot to {plot_file}")

    def _write_summary_config(self, colorterm_files, output_dir, overwrite):
        """Write a summary configuration file."""

        summary_file = os.path.join(output_dir, "nickel_colorterms_summary.txt")

        if os.path.exists(summary_file) and not overwrite:
            return

        with open(summary_file, "w") as f:
            f.write("Nickel to Monster Color Terms\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Generated with {self.n_nodes} spline nodes\n\n")

            f.write("YAML files (spline parameters):\n")
            for band, filepath in colorterm_files.items():
                f.write(f"  {band}: {filepath}\n")

            f.write("\n\nTo use these with STIPS:\n")
            f.write(
                "1. Keep the YAML files with this fitter (instruments/nickel/colorterms/)\n"
            )
            f.write("2. Implement spline color term reader in colorterm configs\n")
            f.write("3. Or use polynomial approximations in *_config.txt files\n")

        print(f"\nWrote summary to {summary_file}")


# ============================================================================
# Main Script
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Compute spline-based color terms from Nickel to Monster"
    )
    parser.add_argument(
        "--monster-throughput-dir",
        required=True,
        help="Directory containing Monster/ComCam throughput files",
    )
    parser.add_argument(
        "--output-dir",
        default="./nickel_colorterms",
        help="Output directory for color term files (default: ./nickel_colorterms)",
    )
    parser.add_argument(
        "--bands",
        nargs="+",
        default=["B", "V", "R", "I"],
        help="Nickel bands to process (default: B V R I)",
    )
    parser.add_argument(
        "--n-nodes", type=int, default=4, help="Number of spline nodes (default: 4)"
    )
    parser.add_argument("--plots", action="store_true", help="Generate QA plots")
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing files"
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("Nickel Telescope Spline-Based Color Term Fitter")
    print("=" * 70 + "\n")

    measurer = NickelSplineMeasurer(
        monster_throughput_dir=args.monster_throughput_dir, n_nodes=args.n_nodes
    )

    colorterm_files = measurer.measure_color_terms(
        bands=args.bands,
        output_dir=args.output_dir,
        do_plots=args.plots,
        overwrite=args.overwrite,
    )

    print("\n" + "=" * 70)
    print("SUCCESS!")
    print("=" * 70)
    print(f"\nColor term files written to {args.output_dir}/")
    for band, path in sorted(colorterm_files.items()):
        print(f"  {band}: {path}")
    print("\nNext steps:")
    print("1. Review the QA plots")
    print("2. Integrate color terms into instruments/nickel/configs/colorterms.py")
    print("3. Test on real Nickel data")
    print("")


if __name__ == "__main__":
    main()
