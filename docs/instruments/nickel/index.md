# Nickel 1-m

The Nickel is the 1-meter telescope at Lick Observatory on Mount Hamilton,
California. It is STIPS's reference instrument: the framework was built on its
data, and every feature runs on it. Its profile is `instruments/nickel/`, and
its collections start with `Nickel/`.

## Camera

| | |
|---|---|
| Detector | One CCD, one amplifier, read out 2 × 2 binned |
| Imaging area | 1024 × 1024 binned pixels, plus 32 overscan columns |
| Pixel scale | 0.368″ per binned pixel |
| Field of view | 6.3′ × 6.3′ |
| Gain, read noise | 1.8 e⁻/ADU, 10.7 e⁻ |
| Saturation | 65,535 ADU |

## Filters

STIPS reads the filter from the `FILTNAM` header.

| Filter | Band | Notes |
|---|---|---|
| B, V | `b`, `v` | Johnson |
| R, I | `r`, `i` | Cousins |
| g′, r′, i′ | `gp`, `rp`, `ip` | Sloan-like |
| Hα, [OIII] | `halpha`, `oiii` | Narrow-band |
| clear | | No band; unrecognized `FILTNAM` values also map here |

Pan-STARRS templates are available for `r`, `i`, `rp`, and `ip`; B and V
need coadd templates (see {doc}`../../templates`).

## What STIPS provides

- Header translation for Nickel's FITS conventions, including guards against
  its known header problems ({doc}`data`).
- A curated defect mask ({doc}`calibration`).
- `calibrateImage` configs tuned for Nickel fields ({doc}`science-configs`).
- Colour terms fitted on Landolt standards ({doc}`photometry`).
- A download hook for the Lick archive ({doc}`data`).

Calibration, science processing, PS1 and coadd templates, difference imaging,
forced photometry, lightcurves, and the period and transit searches all run
on Nickel data; {doc}`campaigns` lists the campaigns that exercise them.

```{toctree}
:hidden:

Getting data <data>
Calibration <calibration>
Science configs <science-configs>
Photometry <photometry>
Example campaigns <campaigns>
PS1 template colour term <template-colorterm-fit>
```
