# colorterms

Color-term fitting utilities for Nickel BVRI photometry against the Monster reference catalog (or other griz-based catalogs). Two complementary approaches are provided:

- **Synthetic fitting** (`nickel_colorterm_fitter.py`): integrates stellar SED templates through Nickel and Monster filter passbands, then fits a cubic spline to the resulting color-color relation. Useful when no on-sky photometry is yet available and when the goal is a smooth, physically-motivated transformation.
- **Empirical fitting** (`empirical_colorterm_fitter.py`): fits a color term directly from matched Nickel-vs-Monster catalogs read via the LSST Butler. Useful when on-sky measurements exist and capture instrumental effects the synthetic approach cannot.

The output is then converted to the LSST stack's `Colorterm` configuration format with `convert_to_lsst_colorterms.py` and dropped into `packages/obs_stips/instrument_defaults/configs/colorterms.py`.

## Layout

```
colorterms/
├── nickel_colorterm_fitter.py        Synthetic spline fitter
├── empirical_colorterm_fitter.py     Empirical fitter from matched catalogs
├── convert_to_lsst_colorterms.py     YAML spline → LSST Colorterm config
├── example_run_nickel_colorterms.sh  Driver for the synthetic workflow
└── pyproject.toml
```

## Synthetic workflow

Filter curves are pulled from the [SVO Filter Profile Service](http://svo2.cab.inta-csic.es/theory/fps/); stellar templates come from the FGCM library (SDSS + Kurucz, ~100 SEDs). For each template the script integrates the SED through the Nickel filter and the chosen Monster band, then fits a cubic spline through the resulting flux-ratio-vs-color points. Default is 4 spline nodes.

```bash
python nickel_colorterm_fitter.py \
    --monster-throughput-dir /path/to/the_monster/data/throughputs \
    --output-dir ./nickel_colorterms_output \
    --bands B V R I \
    --n-nodes 4 \
    --plots
```

Or, for convenience:

```bash
# Edit MONSTER_THROUGHPUT_DIR at the top of the script, then:
./example_run_nickel_colorterms.sh
```

### Arguments

| Flag | Default | Notes |
|---|---|---|
| `--monster-throughput-dir` | — (required) | Directory containing `total_*.dat` or `total_comcam_*.ecsv` for the Monster bands |
| `--output-dir` | `./nickel_colorterms` | Output directory |
| `--bands` | `B V R I` | Which Nickel bands to fit |
| `--n-nodes` | `4` | Number of spline nodes. 3 for under-constrained ranges; 6+ for more flexibility (overfits past ~8) |
| `--plots` | off | Emit per-band QA PNGs |
| `--overwrite` | off | Replace existing output files |

### Per-band color choice

The color used as the spline x-axis is fixed per band:

| Nickel band | Color |
|---|---|
| B | `monster_g − monster_r` |
| V | `monster_g − monster_r` |
| R | `monster_r − monster_i` |
| I | `monster_r − monster_i` |

## Empirical workflow

For Nickel data already processed through the LSST pipeline, the empirical fitter reads matched source catalogs from a Butler repo and regresses the Nickel/Monster magnitude residual against color. This captures real instrumental effects (CCD response, atmosphere, vignetting) that synthetic fitting cannot.

```bash
python empirical_colorterm_fitter.py \
    --butler-repo /path/to/repo \
    --nickel-visit 12345 \
    --nickel-band R \
    --output-dir ./empirical_colorterms
```

## Conversion to LSST format

Both fitters write per-band YAML files containing the spline nodes and values. To use them in the pipeline, convert to the `lsst.pipe.tasks.colorterms.Colorterm` configuration class:

```bash
python convert_to_lsst_colorterms.py \
    --input-dir nickel_colorterms_output \
    --output colorterms_monster.py
```

The output is a drop-in replacement for the `*monster*` block in `packages/obs_stips/instrument_defaults/configs/colorterms.py`. The conversion approximates each spline with a low-order polynomial (`c0 + c1·color + c2·color²`), since the LSST stack's `Colorterm` class does not support arbitrary splines.

## Output files

Per-band, the synthetic fitter produces:

```
nickel_<band>_to_monster_<color>_colorterm.yaml    Spline parameters
nickel_<band>_to_monster_<color>_colorterm.png     QA plot (with --plots)
nickel_<band>_to_monster_<color>_config.txt        Polynomial approximation
```

Plus a `nickel_colorterms_summary.txt` listing all generated files.

YAML structure:

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

The spline values are multiplicative flux-ratio corrections at each node position in color space.

## Dependencies

```
numpy, scipy, matplotlib, astropy, fitsio, astroquery, pyyaml, scikit-learn
fgcm                       (synthetic workflow: stellar templates)
lsst.daf.butler            (empirical workflow: catalog access)
```

The LSST stack (`lsst.daf.butler`) is only required by the empirical fitter; the synthetic fitter is standalone.

## References

- [The Monster reference catalog](https://github.com/lsst-dm/the_monster)
- Burke et al. 2018, AJ 155, 41 — FGCM methodology
- Kelly et al. 2014, MNRAS 439, 28 — stellar templates
- [SVO Filter Profile Service](http://svo2.cab.inta-csic.es/theory/fps/)
- [LSST `Colorterm` API](https://pipelines.lsst.io/modules/lsst.pipe.tasks/lsst.pipe.tasks.colorterms.html)
