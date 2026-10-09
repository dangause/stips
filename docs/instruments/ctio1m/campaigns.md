# Example campaigns and status

## Configs

These configs, in
[`scripts/config/ctio1m/`](https://github.com/dangause/stips/tree/main/scripts/config/ctio1m)
and `scripts/config/sn2009y/`, were run on archival Y4KCam data.

| Config | Field | Shows |
|---|---|---|
| `pipeline_calibs_science.yaml` | PG1047+003, 21 Mar 2007 | Calibration and science on a standard field, V band |
| `pipeline_sa98.yaml` | SA98 and other standards, four nights in Jan 2010 | B, V, R, I calibration and science |
| `pipeline_coadd_dia.yaml`, `pipeline_ps1_dia.yaml` | SA98 | Coadd and PS1 templates on the same night, for comparison |
| `pipeline_ngc2298.yaml` | NGC 2298, four nights in 2006 | Calibration and science south of Pan-STARRS |
| `pipeline_ngc2298_gaia.yaml` | NGC 2298 | Coadd-template difference imaging with Gaia calibration |
| `pipeline_skymapper_dia.yaml` | NGC 2298 | A SkyMapper template on the same field |
| `pipeline_bin2_e2.yaml` | E2, 13 Nov 2011 | 2 × 2-binned data in B, V, R, I; the crosstalk measurement |
| `sn2009y/pipeline_ps1_dia.yaml` | SN 2009Y, Type Ia in NGC 5728 | PS1 templates and Pan-STARRS calibration for a supernova |

The calibration-and-science configs are run step by step (`bootstrap`,
`calibs`, `science`) rather than with `run`, which would also try to build
templates; each file's header lists its commands.

For SN 2009Y, use the position in the config rather than the TNS one, which
lies about 10″ from the supernova; the config documents how it was measured.

## Status

**Validated:** calibration and science on standard fields, binned and
unbinned; astrometry, including the 2006 pointing correction; coadd-template
subtraction and forced photometry on NGC 2298; SkyMapper templates on the
same field.

**Still open:**

- **Colour terms.** None are fitted for Y4KCam, so absolute magnitudes are
  approximate (see {doc}`southern-fields`).
- **Read noise** is a 7 e⁻ placeholder, not a measurement.
- **Crosstalk** coefficients come from one binned night and are indicative.
- **Amplifier A01** is masked from 2010 onward; see {doc}`calibration`.
