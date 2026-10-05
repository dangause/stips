# Paper readiness: findings and decisions (2026-10-04)

What was checked before freezing STIPS for the paper, what changed, and what
is still a decision for the author. Numbers here were measured on the code in
PR #41 (three data-loss fixes), PR #42 (Nickel filter identity) and PR #43 (transit) and should be re-quoted from the frozen rebuild.

## Reproducing the paper's numbers

`scripts/paper/rebuild.py` rebuilds every target in `scripts/paper/targets.yaml`
from raw data, from the checkout it runs in, and writes:

- `products/<target>/` — calibration metrics, Landolt validation, every
  forced-photometry row (no S/N cut, so upper limits survive), lightcurves.
- `products/PROVENANCE.json` — `git describe`, commit, host, time, manifest.
- `configs/<target>/` — the exact configs that ran.

Figure scripts read `STIPS_PAPER_DATA=<out>/products` through
`scripts/analysis/paper_data.py`. `scripts/paper/compare_external.py` writes the
external-photometry comparison. Run the rebuild from a clean checkout of the
release tag, so `stips_describe` reads `v2.1.1` (or later) with no `-dirty`.

## SN 2023ixf: late-time epochs recovered

The August rebuild stopped at day 75 because every later night failed. Three
causes, all fixed in PR #41:

| Night | Day | Cause | Now |
|---|---|---|---|
| 20230817 | 91 | an 82x50 test subframe among the biases crashed ISR and failed the night | r 13.14, i 13.06 |
| 20230815 | 89 | never in the night list; OBJECT `sn2023ixf` missed by DIA's exact name match | r 13.05 |
| 20240828 | 468 | never in the night list; same name mismatch | r 18.15 (S/N 40) |

The day 75 to 91 drop (r 11.88 to 13.14) is the fall off the plateau.

Nights removed from the list, verified from raw headers: 20230905 and 20230910
have only 10 s frames on the SN with 1–3 stars (too few for a PSF model);
20231211 has no 2023ixf frames; 20250807 is a single frame in the newer `rp`
filter with no template mapping.

## SN 2009Y: wrong coordinates, not a non-detection

The two "non-detections" were measured at the wrong place. The TNS position is
~10" from the supernova. CBET 1684 puts it 9" E, 24.6" N of the NGC 5728
nucleus; centroiding the SN in three difference images gives
RA 220.602305, Dec −17.246289 (8.7" E, 24.4" N of the measured nucleus). At that
position, 5–7 days after discovery:

| MJD | Band | AB mag (pipeline system) | S/N |
|---|---|---|---|
| 54868.25 | r | 15.49 ± 0.01 | 146 |
| 54870.30 | r | 14.66 ± 0.01 | 226 |
| 54870.31 | i | 14.99 ± 0.01 | 138 |

Config: `scripts/config/sn2009y/pipeline_ps1_dia.yaml`.

## HD 189733 b: transit reproduced only after two fixes  (PR #43)

The pipeline could not reproduce the poster's transit. The transit search
read PSF forced photometry, which for a B = 8.6 host spans a factor of four,
and BLS returned a 72% "transit". The differential-photometry task that
exists for this case found no target, because the config gave the J2000
position and the star has since moved 6.4" (pmdec −250.8 mas/yr), outside
the 2" match radius. It still reported success.

With PR #43 (differential lightcurve exported and used; empty result fails;
position at the 2025-08-02 epoch), on 400 B visits from 20250802:

| | Value |
|---|---|
| Differential points | 332, 0.21% median error |
| Transit depth | 2.09 ± 0.03% |
| S/N | 83 |
| Mid-transit vs Agol+2010 ephemeris | −7.4 min |

One night cannot constrain the 2.22 d period; quote the single-transit depth
and time, not the BLS period.

## Variable stars: consistent with known periods, not recovered

Rebuilt through the driver (2026-10-04), the period search returns periods
that do not match the literature, and the reason is coverage, not the
pipeline. Each star has at most ~2 h per night, about one pulsation cycle
for the SX Phe stars and a fraction of AC And's 17 h fundamental. The
Lomb–Scargle main peak is as wide as the period itself:

| Star | Published P (d) | STIPS best P (d) | Peak FWHM in P (d) | Power at published P / peak |
|---|---|---|---|---|
| DY Peg | 0.07293 | 0.0668 | 0.05 | 0.96 |
| CY Aqr | 0.06104 | 0.0471 | 0.03 | 0.73 |
| AC And | 0.7112 | unconstrained | > 1 | 0.22 |

The lightcurves are real (DY Peg's 0.55 mag amplitude matches the
literature). For the paper, show them phase-folded at the published periods
and say "consistent with", not "recovered". The period module reports a
false-alarm probability of 0.0 and no period uncertainty, which overstates
single-night results; it should report the peak width.

## Landolt validation: BVRI good to ~0.01 mag in the SN calibration path

Rerun (2026-10-05) in `gaia_ps1` mode, the path every SN campaign uses, with
Gaia/PS1 refcats fetched per Landolt field and matches below S/N 5 dropped:

| Band | N | Standards | Mean (Vega) | Robust rms |
|---|---|---|---|---|
| B | 14 | 7 | +0.005 | 0.08 |
| V | 17 | 7 | +0.012 | 0.02 |
| R | 28 | 9 | +0.009 | 0.08 |
| I | 31 | 9 | −0.008 | 0.06 |

The earlier B −0.44 / V +0.27 offsets belong to MONSTER mode only, which the
paper no longer uses: the Landolt, transit and variable-star configs now run
`gaia_ps1` too (the extended-objects target has no single position and stays
MONSTER; it contributes astrometry and PSF metrics only). Two caveats for
the text: the sample is 11 standards (one per field), and two 20240625
"matches" were noise sources beside undetected standards — the validator now
requires S/N ≥ 5.

## SN 2009Y: first epoch differs between repos

A fresh rebuild gives r = 14.86, 14.57 and i = 14.97; the original repo gave
r = 15.49, 14.66 and i = 14.99. The 20090205 r point moved 0.63 mag; the
other two agree within 0.1. Quote the fresh-rebuild values (a 0.3 mag rise
over two days is the more plausible pre-maximum slope), and check that
night's calibration before relying on it.

## PSF photometry is not biased low

The poster stated that PSF forced photometry under-reports bright-source flux
and used an aperture re-measurement instead. On current code it does not. On
the 20230817 difference images the aperture curve of growth converges onto the
PSF flux: aperture/PSF = 0.80 (8 px), 0.94 (12 px), 0.99 (17 px), 1.02 (25 px).
The paper can quote PSF photometry. The earlier deficit predates the PS1
template fixes (asinh decode, PSF pixel scale).

Separately, the forced-photometry `apDiffFlux_12_0` column is NaN on every row
in both repos checked. It is unused by the paper but should be fixed or dropped.

## Photometric system: two Nickel filter families  (PR #42; Vega/AB decided)

Comparing STIPS with independent photometry exposed a systematic offset: STIPS
i was 0.57 mag brighter than an independent reduction of the same 2023ixf
frames, and 0.59 mag brighter than Tinyanont et al. 2023 for 2020wnt.

**Cause.** 2020–2023 headers write the Sloan-like filters as a malformed card,
`FILTNAM = 'r'                '`. The stack's FITS reader returns `r`, which
ingest mapped to Cousins R, so those frames were calibrated with the Cousins
colour terms. They are not Cousins filters. Against PS1 on 13 2020wnt visits:

| Filter | STIPS − PS1 colour slope | Cousins expectation | Offset from PS1 AB (old) | (fixed) |
|---|---|---|---|---|
| r′ (`rp`) | −0.033 ± 0.006 | −0.24 | −0.23 | +0.008 |
| i′ (`ip`) | −0.053 ± 0.006 | −0.35 | −0.47 | +0.013 |

On the same two i′ visits the fixed magnitudes are 0.49 mag fainter, which
removes most of the offset against Tinyanont. PR #42 maps the lowercase
labels to their own `rp`/`ip` physical filters and bands.

**What the paper should say.** Nickel observed in two filter families, and
STIPS now keeps them as separate bands:

- `rp`, `ip` — Sloan-like r′/i′, most 2020–2023 nights. Calibrated to PS1
  with near-zero colour terms; **AB**.
- `r`, `i` — Cousins R/I (and B, V), all 2024+ nights, the Landolt fields, and
  a few 2023 nights. Calibrated with Landolt-fitted terms whose constants
  (−0.18 for R, −0.379 for I) match Tonry et al. 2012's Cousins − PS1 offsets,
  so these magnitudes are effectively **Vega** Cousins R/I. The pipeline still
  stores them as nJy and the lightcurve tool labels them "AB".

**Decided (2026-10-05): Cousins B/V/R/I in Vega, Sloan-like rp/ip in AB**,
the convention SN papers use. The Cousins terms already produce Vega, so this
was a labelling fix: `InstrumentProfile.vega_bands` declares it per refcat
mode, lightcurves carry a `mag_system` column, plots name the systems, and
the Landolt validator no longer shifts Vega bands a second time.

**Flats.** 8 of 84 nights have science in one family with flats only in the
other (for example 2023ixf 20230714 i′, 2020wnt 20220208 r′). Those frames were
previously flat-fielded through the wrong filter; after PR #42 they fail
instead. A cross-family flat fallback would recover them if needed.

## DIA residual floor from the PS1 colour term  (documented limitation)

After the asinh fix, about four 5–10σ DIA candidates per visit remain on
2023ixf. They are real stars with a per-star flux-scale error from the
PS1-r to Nickel-R bandpass difference: 64% recur at the same position across
visits, and negatives sit at science/template = 0.79 against 1.07 for
positives. A template-vs-science fit gives k1 = −0.070 ± 0.015 mag per mag of
Gaia BP−RP, but on 18 stars with the two nights disagreeing at ~2σ, so it is
not applied. Ruled out: misregistration, seeing, PS1 stack masks, noise.

Recommendation for the paper: state it as a limitation of single-band external
templates, with these numbers. Removing it needs a template synthesised from
PS1 r and i through the R colour term, which is a feature, not a fix.

## CTIO magnitudes  (DECISION NEEDED)

CTIO has no colour terms in any refcat mode (`instruments/ctio1m/configs/`
ships none, so `applyColorTerms` is off). Its magnitudes, including SN 2009Y
above, are therefore on the PS1 AB zeropoint with the Y4KCam-versus-PS1
bandpass difference uncorrected: for Cousins-like R/I that is a few tenths of
a magnitude plus a colour term, the same size as the Nickel offsets fixed in
#42. Detection, astrometry and difference imaging do not depend on it.

Options: fit CTIO PS1 colour terms on the SA98 Landolt field, which is
already reduced (`sa98_v2_repo`, `scripts/config/ctio1m/pipeline_sa98.yaml`;
`stips-colorterms-fit` exists for this), then declare CTIO `vega_bands`; or
quote SN 2009Y's magnitudes as PS1-calibrated with a stated ~0.2–0.5 mag
systematic.

## Still for the author

- **Zenodo DOI:** connect the GitHub repo at zenodo.org so each release gets a
  DOI; `CITATION.cff` is in place for it to read.
- **Citation metadata:** add affiliation and ORCID to `CITATION.cff`, and
  confirm the license is GPL-3.0-only rather than -or-later.
- **Data deposit:** archive `products/` with the release.
