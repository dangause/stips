#!/usr/bin/env python3
"""
Convert spline-based color terms to LSST stack Colorterm format.

This reads the YAML spline files and generates a properly formatted
obs_nickel/configs/colorterms.py file.

Usage:
    python convert_to_lsst_colorterms.py \
        --input-dir ./nickel_colorterms_output \
        --output colorterms_monster.py
"""

import argparse
import os

import numpy as np
import yaml
from scipy.interpolate import CubicSpline


def load_spline_colorterm(yaml_file):
    """Load a spline color term from YAML."""
    with open(yaml_file, "r") as f:
        data = yaml.safe_load(f)

    return data


def fit_polynomial_to_spline(nodes, values, degree=2):
    """Fit polynomial to spline for LSST stack compatibility."""
    # Evaluate spline at many points
    spline = CubicSpline(nodes, values, bc_type="clamped")
    colors = np.linspace(nodes[0], nodes[-1], 100)
    corrections = spline(colors)

    # Convert multiplicative corrections to additive magnitudes
    # correction_flux = flux_source * correction_factor
    # mag_correction = -2.5 * log10(correction_factor)
    mag_corrections = -2.5 * np.log10(corrections)

    # Fit polynomial: mag_correction = c0 + c1*color + c2*color^2
    coeffs = np.polyfit(colors, mag_corrections, degree)

    # Return in LSST order: [c2, c1, c0]
    return coeffs[::-1]  # Reverse for LSST format


def generate_colorterms_config(input_dir, output_file, use_polynomial=True):
    """Generate colorterms.py file for obs_nickel."""

    bands = ["B", "V", "R", "I"]
    monster_bands = {"B": "g", "V": "g", "R": "r", "I": "i"}

    # Collect color term data
    colorterm_data = {}

    for band in bands:
        monster_band = monster_bands[band]
        yaml_file = os.path.join(
            input_dir, f"nickel_{band}_to_monster_{monster_band}_colorterm.yaml"
        )

        if not os.path.exists(yaml_file):
            print(f"Warning: {yaml_file} not found, skipping band {band}")
            continue

        data = load_spline_colorterm(yaml_file)

        if use_polynomial:
            # Fit polynomial approximation
            coeffs = fit_polynomial_to_spline(
                data["nodes"], data["spline_values"], degree=2
            )
            c0, c1, c2 = coeffs
        else:
            # Would need to implement spline color terms in stack
            c0, c1, c2 = 0.0, 0.0, 0.0

        colorterm_data[band] = {
            "primary": data["primary_field"].replace("monster_ComCam_", ""),
            "secondary": data["secondary_field"].replace("monster_ComCam_", ""),
            "c0": c0,
            "c1": c1,
            "c2": c2,
            "nodes": data["nodes"],
            "spline_values": data["spline_values"],
        }

    # Write config file
    with open(output_file, "w") as f:
        f.write('"""\n')
        f.write("Color terms for Nickel telescope to Monster catalog.\n")
        f.write("\n")
        f.write("Generated from spline-based synthetic photometry.\n")
        f.write("These use polynomial approximations to the spline fits.\n")
        f.write("\n")
        f.write("For best accuracy, consider implementing spline color terms.\n")
        f.write('"""\n')
        f.write("\n")
        f.write("from lsst.pipe.tasks.colorterms import Colorterm, ColortermDict\n")
        f.write("\n")
        f.write("config.data = {\n")
        f.write('    "*monster*": ColortermDict(\n')
        f.write("        data={\n")

        for band in bands:
            if band not in colorterm_data:
                continue

            ct = colorterm_data[band]

            f.write(f"            # Nickel {band} -> Monster {monster_bands[band]}\n")
            f.write(f'            # Color: {ct["primary"]}-{ct["secondary"]}\n')
            f.write(f'            # Spline nodes: {ct["nodes"]}\n')
            f.write(f'            "{band}": Colorterm(\n')
            f.write(f'                primary="monster_ComCam_{ct["primary"]}",\n')
            f.write(f'                secondary="monster_ComCam_{ct["secondary"]}",\n')
            f.write(f'                c0={ct["c0"]:.6f},\n')
            f.write(f'                c1={ct["c1"]:.6f},\n')
            f.write(f'                c2={ct["c2"]:.6f},\n')
            f.write("            ),\n")

        f.write("        }\n")
        f.write("    ),\n")
        f.write("}\n")

    print(f"\nGenerated {output_file}")
    print("\nTo use:")
    print("  1. Review the file")
    print("  2. Copy to obs_nickel/configs/colorterms.py")
    print("  3. Or merge with existing colorterms.py")

    # Print summary
    print("\n" + "=" * 70)
    print("Color Term Summary")
    print("=" * 70)
    for band in bands:
        if band not in colorterm_data:
            continue
        ct = colorterm_data[band]
        print(f"\n{band} band:")
        print(f"  Color: {ct['primary']}-{ct['secondary']}")
        print(f"  c0 = {ct['c0']:+.6f}")
        print(f"  c1 = {ct['c1']:+.6f}")
        print(f"  c2 = {ct['c2']:+.6f}")
        print(
            f"  Nodes: {len(ct['nodes'])} ({ct['nodes'][0]:.2f} to {ct['nodes'][-1]:.2f})"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Convert spline color terms to LSST stack format"
    )
    parser.add_argument(
        "--input-dir", required=True, help="Directory containing YAML color term files"
    )
    parser.add_argument(
        "--output",
        default="colorterms_monster.py",
        help="Output filename (default: colorterms_monster.py)",
    )
    parser.add_argument(
        "--no-polynomial",
        action="store_true",
        help="Do not fit polynomial approximation (requires spline implementation)",
    )

    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"Error: Input directory not found: {args.input_dir}")
        return 1

    generate_colorterms_config(
        args.input_dir, args.output, use_polynomial=not args.no_polynomial
    )

    return 0


if __name__ == "__main__":
    exit(main())
