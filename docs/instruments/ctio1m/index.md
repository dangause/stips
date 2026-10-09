# CTIO 1.0-m / Y4KCam

The CTIO 1.0-m, the Yale/SMARTS 1-meter at Cerro Tololo in Chile, carried
Y4KCam from 2003 to 2013. Its data are archival and public in the NOIRLab
Astro Data Archive. CTIO is STIPS's second instrument and its southern one,
and the first with a multi-amplifier camera. Its profile is
`instruments/ctio1m/`, and its collections start with `CTIO1m/`.

## Camera

| | |
|---|---|
| Detector | One ITL 4K CCD, four amplifiers (one per quadrant, read out toward the centre) |
| Imaging area | 4064 × 4064 pixels, or 2032 × 2032 binned 2 × 2 |
| Pixel scale | 0.289″ per pixel (0.578″ binned) |
| Field of view | About 20′ × 20′ |
| Gain | 1.38–1.48 e⁻/ADU, measured per amplifier |
| Read noise | 7 e⁻ (placeholder, not yet measured) |
| Saturation | 65,535 ADU |

The camera is mounted rotated by 180°, which the profile records so the
first astrometric guess is right.

## Filters

STIPS reads the filter from the `FILTERID` header.

| Filter | Band |
|---|---|
| U, U+CuSO4 | `u` |
| B, V | `b`, `v` |
| R, I | `r`, `i` |

There is no clear position, so an unknown filter is an error rather than a
fallback. Pan-STARRS and SkyMapper templates are available for `r` and `i`.

## What STIPS provides

- Header translation for Y4KCam, including per-campaign pointing corrections
  ({doc}`data`).
- Four-amplifier geometry, overscan and saturation handling, measured
  crosstalk, and defect masks ({doc}`calibration`).
- Configs for calibration, subtraction, and coadds tuned on CTIO data.
- A download hook for the NOIRLab archive ({doc}`data`).
- Guidance for southern fields outside Pan-STARRS ({doc}`southern-fields`).

CTIO is validated on archival standard fields and on the southern cluster
NGC 2298, and has been used for SN 2009Y. It has no fitted colour terms yet;
{doc}`campaigns` lists what has been run and what is still open.

```{toctree}
:hidden:

Getting data <data>
Calibration <calibration>
Southern fields <southern-fields>
Example campaigns and status <campaigns>
SkyMapper templates <skymapper-template-validation>
```
