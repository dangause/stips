# Photometry

`calibrateImage` sets each exposure's zero point by matching its stars to the
reference catalog (see {doc}`../../reference-catalogs`). Nickel's filters are
not the reference catalog's, so a *colour term* converts reference magnitudes
into each Nickel band first:

```text
m_Nickel = m_primary + c0 + c1 × (primary − secondary)
```

`c0` shifts every magnitude equally, so it sets the band's magnitude system;
`c1`, the colour slope, removes colour-dependent errors.

## Colour terms

The terms are in `instruments/nickel/configs/colorterms.py`. For the
Pan-STARRS reference catalog (`gaia_ps1` mode):

| Band | Primary − secondary | c0 | c1 | Fitted on |
|---|---|---|---|---|
| B | g − r | 0.215 | 0.589 | Landolt standards |
| V | g − r | −0.011 | −0.540 | Landolt standards |
| R | r − i | −0.180 | −0.243 | Landolt standards |
| I | i − r | −0.379 | 0.352 | Landolt standards |
| r′ (`rp`) | r − i | 0 | −0.033 | 13 SN 2020wnt visits against PS1 |
| i′ (`ip`) | i − r | 0 | 0.053 | 13 SN 2020wnt visits against PS1 |

The B, V, R, and I terms were fitted on 10 Landolt standards in June 2026.
The fit cut the I-band residual scatter from 0.22 to 0.08 mag, and its I
zero point matches Tonry et al. (2012). Separate blocks hold the terms for
the Gaia-only and MONSTER catalogs. To refit, follow
[`instruments/nickel/colorterms/README.md`](https://github.com/dangause/stips/blob/main/instruments/nickel/colorterms/README.md),
which runs `stips-colorterms-fit`.

## Magnitude systems

| Mode | B, V, R, I | r′, i′ and others |
|---|---|---|
| `gaia_ps1` | Vega, through the Landolt-fitted terms | AB |
| `monster` | AB | AB |

Each lightcurve row records its system in the `mag_system` column, and the
plot labels it.

## Accuracy

On four nights of Landolt standards (90 measurements, 7 to 9 standards per
band; checked 5 October 2026), `gaia_ps1` calibration agrees with the
published magnitudes to within 0.012 mag on average:

| Band | Mean, STIPS − Landolt | Robust scatter |
|---|---|---|
| B | +0.005 | 0.08 |
| V | +0.012 | 0.02 |
| R | +0.009 | 0.08 |
| I | −0.008 | 0.06 |

MONSTER mode does not reach this: it leaves B off by −0.44 mag and V by
+0.27 mag. Use `gaia_ps1` for Nickel photometry.

## Checking the calibration

- `stips calib-metrics -o metrics.csv` writes each visit's astrometric and
  photometric calibration metrics: zero point, scatter, and matched-star
  counts.
- `stips landolt-validate --catalog <csv> -o <csv>` compares calibrated
  magnitudes of Landolt standards with their published values. The
  [`landolt_validation`](https://github.com/dangause/stips/tree/main/scripts/config/landolt_validation)
  config processes standard-star nights for it.
- {doc}`template-colorterm-fit` measures the colour term between PS1
  templates and Nickel science images, which affects difference photometry.
