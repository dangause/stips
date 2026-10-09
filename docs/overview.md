# What is STIPS?

STIPS, the Small Telescope Image Processing Suite, reduces imaging from
1-meter class telescopes with the [LSST Science
Pipelines](https://pipelines.lsst.io/), the software [Rubin
Observatory](https://rubinobservatory.org/) wrote to process the Legacy Survey
of Space and Time (LSST). You describe your telescope once, in a short Python
profile, and write one YAML file per target. STIPS takes it from raw frames to
calibrated lightcurves: bias and flat calibration, astrometric and photometric
calibration, image subtraction, forced photometry, and period or transit
searches.

## Why STIPS exists

Telescopes of about a meter do much of the follow-up in time-domain astronomy:
supernova lightcurves, variable-star monitoring, exoplanet transits. Their
images are usually reduced with scripts written for one instrument and one
project. Such scripts are hard to reuse, hard to compare between telescopes,
and rarely record exactly how a number was measured. Difference imaging, which
a transient sitting on a galaxy needs, is especially hard to do well.

The LSST Science Pipelines solve these problems, but at survey scale: they are
built for Rubin's 8.4-m telescope and its 3.2-gigapixel camera. Adding another
camera means writing an *obs package* (an instrument class, a FITS header
translator, the camera geometry, curated calibrations) and learning the stack's
data management, pipeline definitions, and configuration system before the
first image is processed. For a small observatory that is a large investment.

STIPS makes that investment once. It began as an LSST instrument package for
the Nickel 1-m at Lick Observatory, written to measure supernova lightcurves,
and was generalized so that another telescope is added by writing a profile
rather than a package.

## Why the Rubin Science Pipelines

- **Survey-grade algorithms.** Instrument signature removal, PSF modeling,
  astrometric and photometric calibration against Gaia and Pan-STARRS, image
  subtraction, and forced photometry, developed for LSST and used to process
  the Hyper Suprime-Cam surveys on Subaru
  ([Bosch et al. 2018](https://doi.org/10.1093/pasj/psx080)).
- **Provenance.** The [Butler](https://pipelines.lsst.io/modules/lsst.daf.butler/index.html)
  data repository records every dataset together with the inputs and
  configuration that produced it, so a point on a lightcurve traces back to its
  raw frames and can be reproduced.
- **Laptop to cluster.** The same pipeline definition runs on a laptop with
  `pipetask` or on a Slurm or HTCondor cluster through the [Batch Processing
  Service](https://pipelines.lsst.io/modules/lsst.ctrl.bps/index.html).
- **Open and maintained.** The pipelines are open source and maintained by
  Rubin for its ten-year survey, with documentation and a
  [community forum](https://community.lsst.org/).

## What STIPS adds

**Instrument profiles**
: A telescope is a directory, `instruments/<name>/`, whose `profile.py`
  describes the camera, FITS headers, filters, and site. STIPS builds the LSST
  instrument from it at run time, so there is no obs package to write.

**Small-telescope tuning**
: A 1-m field can have fewer than ten good PSF stars and 1.5–2.5″ seeing.
  STIPS ships calibration configs tuned for such fields, retries a failed
  exposure with progressively relaxed configs, and tunes coaddition and
  subtraction for small fields of view.

**Templates**
: Reference images for subtraction come from Pan-STARRS1 in the north,
  SkyMapper in the south, or a coadd of your own nights without the transient.

**One command per campaign**
: `stips -c target.yaml run` sets up a data repository, builds calibrations,
  processes every night, subtracts, measures, and extracts the lightcurve.
  Nights and bands run independently, so one bad night does not stop the rest.

**Time-series tools**
: Forced photometry at fixed coordinates, lightcurve extraction, a
  Lomb–Scargle period search for variable stars, and differential photometry
  with a box least-squares (BLS) search for transits.

## What it has been used for

- **Supernovae:** SN 2023ixf and SN 2020wnt with the Nickel 1-m.
- **Variable stars:** CY Aqr, DY Peg, and AC And.
- **Exoplanet transits:** HD 189733 b.
- **Calibration checks:** Landolt standard fields.

The configs for these campaigns are in
[`scripts/config/`](https://github.com/dangause/stips/tree/main/scripts/config)
and make good starting points for your own.

## Supported instruments

| Telescope | Camera | Raw data |
|---|---|---|
| [Nickel 1-m](instruments/nickel/index.md), Lick Observatory (reference) | Single-amplifier 1024 × 1024 CCD, 0.37″/pixel | [Lick archive](https://archive.ucolick.org/archive/) |
| [CTIO 1.0-m with Y4KCam](instruments/ctio1m/index.md) | Four-amplifier 4064 × 4064 CCD, unbinned or 2 × 2 binned | [NOIRLab Astro Data Archive](https://astroarchive.noirlab.edu/) |

Another telescope can be added with a profile directory; see
{doc}`forking-stips`.

## What STIPS does not do

- It reduces nights after they are observed. It does not produce real-time
  alerts.
- It runs the Rubin stack rather than replacing it, so you need the stack
  installed, or the STIPS container, which includes it.
- Photometric calibration needs reference-catalog coverage. Pan-STARRS covers
  declinations above about −30°; further south, calibrate against Gaia or
  MONSTER instead (see {doc}`reference-catalogs`).

## Next steps

- {doc}`how-it-works` walks through the processing steps and the pieces
  involved.
- {doc}`install-rubin-stack` and {doc}`installation` set up the software.
- {doc}`quickstart` processes a first night.
