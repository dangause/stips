# Templates

Difference imaging subtracts a *template*, an image of the same field without
the transient, from each science image. The template sets how clean the
subtraction is, so choose it first. `template.type` selects it:

| `template.type` | Source | Bands | Use when |
|---|---|---|---|
| `ps1` | Pan-STARRS1 survey stacks | Those in the profile's `ps1_band_map` (Nickel: `r`, `i`, `rp`, `ip`) | The field is north of −30° and you observe in those bands |
| `coadd` | A coadd of your own nights without the transient | All | You have nights from before the transient or after it faded |
| `auto` | PS1 where available, coadd for the other bands | All | A mix of bands; needs `template.nights` |
| `skymapper` | SkyMapper DR4 frames | Those in the profile's `template_band_maps` (CTIO: `r`, `i`) | A southern field with no nights to coadd |
| `none` | | | No subtraction; also set `options.skip_dia: true` |

## Pan-STARRS1

```yaml
template:
  type: ps1
  size: 0.4            # cutout side in degrees (default 0.3)
  degrade_seeing: 2.0  # optional: blur the template to this seeing, in arcsec
```

- **Size:** make the cutout comfortably larger than the camera's field plus
  your dithers. Too small a cutout leaves dithered pointings without enough
  overlap to match PSFs. The Nickel field is 6.3′; the 2023ixf configs use
  0.4°.
- **Epoch:** the PS1 survey images were taken in 2010–2014, so they rarely
  contain the transient you are following. Check this for older events.
- **Subtraction config:** set `configs.dia.subtract_images:
  dia/subtractImages_ps1.py`, which is tuned for matching PS1 to Nickel.
- STIPS decodes PS1's compressed pixels and converts them to nJy when it
  ingests a template, so there is nothing to prepare by hand.

## Coadds of your own data

```yaml
template:
  type: coadd
  nights: [20240601, 20240615, 20240701]   # nights without the transient
```

`stips run` calibrates and processes the template nights, then coadds them.
Because the template comes from the same telescope, PSF matching is easiest
and every band works. Use only nights in which the transient is absent: any
of its light left in the template makes the measured flux too low.

For a variable star, coadd nights that span several cycles, so the template
approximates the mean brightness (see {doc}`time-series`).

## SkyMapper

```yaml
template:
  type: skymapper
configs:
  dia:
    subtract_images: dia/subtractImages_skymapper.py   # always set this
```

For southern fields where no nights are free of the transient. STIPS never
picks SkyMapper on its own; `auto` uses PS1 and coadds only. SkyMapper serves
single-epoch frames rather than deep stacks. Each request is limited to
0.17°, so STIPS assembles a larger `size` from several requests on the same
frame. Its *v* filter is violet, not Johnson V, so the CTIO profile leaves
*v* unmapped. The subtraction config matters because SkyMapper seeing is no
sharper than the science images. The {doc}`skymapper-template-validation`
report measures what to expect.

## No template

With `type: none` STIPS skips templates, but difference imaging still runs
unless `options.skip_dia: true` is also set, and then fails for every night.
Forced photometry runs only where difference imaging succeeded, so without
`skip_dia` it is skipped too, including the direct-image photometry of
transit campaigns.

## When the subtraction fails

- **"No template overlap", or no difference images:** the template does not
  cover the science pointings. Increase `template.size`.
- **`NoKernelCandidatesError`:** too few stars are shared between template and
  science image to match PSFs. This is usually the same coverage problem.
- **Negative or low supernova flux in a coadd template:** a template night
  still contained the transient.

See {doc}`troubleshooting` for more.
