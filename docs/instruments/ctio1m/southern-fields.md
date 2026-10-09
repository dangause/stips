# Southern fields

Most CTIO targets lie south of Pan-STARRS's limit near −30° declination,
which changes both the reference catalog and the template.

## Reference catalogs

| Field | Use `refcat.mode` | Calibrated against |
|---|---|---|
| North of −30° (SN 2009Y at −17°) | `gaia_ps1` | Gaia for astrometry, Pan-STARRS for photometry |
| South of −30° (NGC 2298 at −36°) | `gaia` | Gaia for both |

The SA98 and other standard-field configs set no mode, so they use the
default, MONSTER.

With `gaia`, each band is calibrated against the nearest Gaia band (B against
BP, V against G, R and I against RP). Colour terms would correct for the
differences, but CTIO has none yet for any reference catalog, so treat its
absolute magnitudes as approximate. See {doc}`../../reference-catalogs`.

## Templates

1. **A coadd of your own nights** (`template.type: coadd`) is the validated
   choice. On NGC 2298, a coadd of September 2006 nights subtracted from a
   December 2006 night gave forced photometry consistent with zero at a
   non-varying position, as it should.
2. **Pan-STARRS** (`ps1`) works north of −30°. SN 2009Y was reduced this way,
   but a template from another telescope matches Y4KCam's PSF and pixel grid
   less well than a coadd of Y4KCam data, so subtraction residuals are larger.
3. **SkyMapper** (`skymapper`) is the fallback when no nights without the
   transient exist. See {doc}`skymapper-template-validation` for what to
   expect, and always set `configs.dia.subtract_images:
   dia/subtractImages_skymapper.py`.

## Choosing a field for testing subtraction

Use a field rich in moderately bright, unsaturated stars, such as a globular
cluster. Standard-star fields such as SA98 are poor tests: their bright
standards saturate, and the bleed trails corrupt the stars used to match the
template's PSF to the science image's.
