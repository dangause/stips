# Nickel Spline-Based Color Term Fitter

A sophisticated spline-based color term calculator for transforming Nickel telescope photometry to the Monster catalog system.

## Overview

This tool adapts the Monster catalog's rigorous spline-fitting methodology to compute accurate color transformations between:
- **Source**: Nickel telescope BVRI (Johnson/Bessell B,V + Cousins R,I)
- **Target**: Monster catalog grizy bands

### Why Spline-Based Color Terms?

Traditional linear color terms (c0 + c1×color + c2×color²) work well for normal stars but break down for:
- Very blue stars (e.g., hot white dwarfs)
- Very red stars (e.g., cool M-dwarfs)
- Stars at the extremes of your color range

Spline-based color terms use piecewise cubic functions with multiple nodes to capture non-linear color transformations across the full stellar locus.

## Features

- **Automatic throughput download**: Fetches Nickel filter curves from SVO Filter Profile Service
- **Stellar template library**: Uses FGCM's SDSS+Kurucz templates (Kelly 2014)
- **Synthetic photometry**: Integrates SEDs through realistic filter curves
- **Robust spline fitting**: Uses 4 nodes by default (configurable)
- **QA plots**: Visualizes color terms and residuals
- **YAML output**: Saves spline parameters for later use
- **LSST stack compatibility**: Includes polynomial approximations

## Requirements

```bash
# Python packages
pip install numpy scipy matplotlib astropy fitsio astroquery scikit-learn pyyaml

# LSST stack (for FGCM templates)
pip install fgcm
# OR provide your own stellar template file
```

## Installation

```bash
# Copy the fitter to your working directory
cp nickel_colorterm_fitter.py /path/to/your/analysis/

# Make executable
chmod +x nickel_colorterm_fitter.py
```

## Usage

### Basic Usage

```bash
python nickel_colorterm_fitter.py \
    --monster-throughput-dir /path/to/the_monster/data/throughputs \
    --output-dir ./nickel_colorterms \
    --plots \
    --overwrite
```

### Advanced Usage

```bash
# Custom number of spline nodes (more nodes = more flexible fit)
python nickel_colorterm_fitter.py \
    --monster-throughput-dir /path/to/monster/throughputs \
    --output-dir ./colorterms_6nodes \
    --n-nodes 6 \
    --plots

# Process only specific bands
python nickel_colorterm_fitter.py \
    --monster-throughput-dir /path/to/monster/throughputs \
    --bands B V R \
    --plots
```

### Arguments

- `--monster-throughput-dir` (required): Path to Monster throughput files
  - Should contain files like: `total_g.dat`, `total_r.dat`, etc.
  - Or `total_comcam_g.ecsv`, `total_comcam_r.ecsv`, etc.

- `--output-dir` (default: `./nickel_colorterms`): Output directory

- `--bands` (default: `B V R I`): Which Nickel bands to process

- `--n-nodes` (default: 4): Number of spline nodes
  - 4 nodes: Good for most cases
  - 6-8 nodes: Better for complex color terms
  - 10+ nodes: Risk of overfitting

- `--plots`: Generate QA plots (recommended!)

- `--overwrite`: Overwrite existing output files

## Output Files

The script generates several files per band:

### 1. YAML Files (Spline Parameters)
```
nickel_B_to_monster_g_colorterm.yaml
nickel_V_to_monster_g_colorterm.yaml
nickel_R_to_monster_r_colorterm.yaml
nickel_I_to_monster_i_colorterm.yaml
```

Contains:
- Spline node positions
- Spline values at each node
- Flux offset
- Metadata (source/target catalogs, color bands)

### 2. Config Files (Polynomial Approximations)
```
nickel_B_to_monster_g_config.txt
...
```

Contains polynomial coefficients that approximate the spline fit. These can be used with LSST stack's standard `Colorterm` class as a fallback.

### 3. QA Plots
```
nickel_B_to_monster_g_colorterm.png
...
```

Shows:
- Synthetic star flux ratios vs. color
- Fitted spline curve
- Spline node locations
- Useful for verifying the fit quality

### 4. Summary File
```
nickel_colorterms_summary.txt
```

Lists all generated files and usage instructions.

## Understanding the Output

### Example YAML File Structure

```yaml
source_catalog: Monster
target_catalog: Nickel
primary_field: monster_ComCam_g_flux
secondary_field: monster_ComCam_r_flux
band_field: nickel_B_flux
nodes: [-0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
spline_values: [0.98, 1.01, 1.03, 1.05, 1.08, 1.12, 1.15]
flux_offset: 0.000234
```

The spline values represent multiplicative correction factors at each node position in color space.

### Interpreting QA Plots

The QA plots show `Monster_flux / Nickel_flux` vs. color:
- **Horizontal line at 1.0**: Perfect match, no color term needed
- **Slope**: Linear color term component
- **Curvature**: Non-linear color term (captured by spline)
- **Scatter**: Intrinsic differences + measurement uncertainties

## Integration with obs_nickel

### Option 1: Implement Spline Color Terms (Recommended)

Extend LSST stack to support spline-based color terms:

```python
# In obs_nickel/python/lsst/obs/nickel/colorterms.py

class ColortermSpline:
    """Spline-based color term."""
    def __init__(self, yaml_file):
        # Load spline parameters
        pass

    def apply(self, primary_flux, secondary_flux, band_flux):
        # Compute color
        # Interpolate spline
        # Apply correction
        pass
```

### Option 2: Use Polynomial Approximation (Quick Start)

Use the polynomial coefficients from `*_config.txt` files:

```python
# obs_nickel/configs/colorterms.py

config.data = {
    "*monster*": ColortermDict(
        data={
            "B": Colorterm(
                primary="monster_ComCam_g",
                secondary="monster_ComCam_r",
                c0=0.012,    # From polynomial fit
                c1=0.523,    # From polynomial fit
                c2=0.089,    # From polynomial fit
            ),
            # ... etc
        }
    ),
}
```

## Troubleshooting

### "Could not find stellar templates"

**Solution 1**: Install fgcm
```bash
pip install fgcm
```

**Solution 2**: Provide custom template file
```python
# Modify the script
self.synth.load_stellar_templates(template_file='/path/to/templates.fits')
```

### "Could not find Monster throughput for band X"

Check that your throughput directory contains files matching these patterns:
- `total_X.dat`
- `total_comcam_X.ecsv`
- `total_comcam_X.dat`

Where X is g, r, i, z, or y.

### "Not enough valid data points for N nodes"

Your color range is too narrow or templates don't span it well. Try:
- Reducing `--n-nodes`
- Checking throughput files are valid
- Verifying stellar templates loaded correctly

### Poor Fit Quality

Indicated by:
- Large scatter in QA plots
- Spline oscillating wildly between nodes

Solutions:
- Reduce number of nodes (`--n-nodes 4` or `--n-nodes 3`)
- Check that filter throughputs are correct
- Verify stellar templates are appropriate

## Technical Details

### Synthetic Photometry Method

For each stellar template:
1. Load SED: F_λ(λ) from template
2. Convert to F_ν: F_ν = F_λ × λ²
3. Interpolate onto filter wavelength grid
4. Integrate: flux = ∫ F_ν(λ) T(λ) / λ dλ / ∫ T(λ) / λ dλ

### Spline Fitting

1. Compute colors for all synthetic stars
2. Select stars in valid color range
3. Normalize fluxes to median ratio
4. Fit cubic spline with clamped boundary conditions
5. Optimize spline node values + flux offset using least squares

### Color Choices

- **B, V**: Use g-r color (Monster)
- **R**: Use r-i color (Monster)
- **I**: Use r-i color (Monster)

These match the typical color spaces used in the literature.

## Validation

To validate color terms:

1. **Check QA plots**: Smooth curves, no oscillations
2. **Residual analysis**: Compute residuals on real star matches
3. **Compare to literature**: Check against published Nickel transformations
4. **Test on calibrators**: Apply to standard star fields

## References

- Kelly et al. 2014 (MNRAS 439, 28): Stellar template library
- Burke et al. 2018: FGCM color terms
- Monster catalog: https://github.com/lsst-dm/the_monster
- SVO Filter Profile Service: http://svo2.cab.inta-csic.es/svo/theory/fps/

## Citation

If you use this code, please cite:
- The Monster catalog paper (when published)
- Kelly et al. 2014 (for stellar templates)
- SVO Filter Profile Service

## Support

For questions or issues:
1. Check the troubleshooting section
2. Review QA plots carefully
3. Consider testing with different `--n-nodes` values
4. Open an issue in your obs_nickel repository

## License

GPL-3.0 (matching obs_nickel)
