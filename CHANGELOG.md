# Changelog

All notable changes to STIPS (the Small Telescope Image Processing Suite) are documented here.

## [Unreleased]

### Added
- A documentation site for Read the Docs (MkDocs + Material, `mkdocs.yml`,
  `.readthedocs.yaml`): new home, configuration, troubleshooting and citing
  pages, a CLI reference generated from `stips <command> --help`, and API pages
  for the profile, collection-name, config and dataset-type modules. Internal
  notes in `docs/` stay out of the build. `make docs` builds it as Read the
  Docs does, failing on warnings; `make docs-serve` previews it, and a CI job
  runs the same build.

### Fixed
- The container image can fetch refcats on demand and run every instrument.
  It installs `stips-refcats` (which `refcat.mode: gaia_ps1` and `gaia` need)
  and `tenacity` (the Nickel download's archive client), and it ships all of
  `instruments/`, so `INSTRUMENT_DIR=/opt/stips/instruments/ctio1m` works.
  Nickel stays the default. `stips-exec` keeps the container's
  `INSTRUMENT_DIR`. The image is labelled GPL-3.0-or-later (it said
  BSD-3-Clause, and published images said GPL-3.0). A failed `pip install`
  now fails the image build. The HPC and Slurm images ship every instrument
  too.
- The Slurm compute-node image (`docker/Dockerfile.slurm`) ships the `stips`
  source. Every instrument profile imports `stips`, which
  `bps/sites/docker-slurm.yaml` expects at `/opt/stips/packages/stips/src`, so
  a compute node could not load the instrument (`ModuleNotFoundError: No
  module named 'stips'`). The build now loads each instrument as a compute
  node does, and a failed `pip install` fails it.
- Containerized BPS runs the configured instrument. The `docker-slurm` and
  `singularity-slurm` sites exported `INSTRUMENT_DIR=/opt/stips/instruments/nickel`
  on every compute node, so a CTIO run's quanta got the Nickel profile. They
  now export the config's `INSTRUMENT_DIR` (a path inside the container), as
  the `slurm` site does.
- `make declare-eups` failed with ``syntax error near unexpected token `then'``:
  the `envsource` macro lost its trailing `;` when it began wrapping
  `load_envs`. (`make stack-install` parsed only because `export` took its
  next assignment as another variable.)
- Stale text: the Apptainer definition's help gives commands the required
  `-c <config.yaml>` and drops the removed `STIPS_PROFILE`/`.env` mechanism;
  it and the publish workflow name the current images (`ghcr.io/dangause/stips`,
  `oras://ghcr.io/dangause/stips-sif:<tag>`); the image description is no
  longer Nickel-only; and step 1 of the stack-bump runbook installs
  `lsst_distrib`, which step 2's tests set up.

### Changed
- The paper material — the rebuild driver (`scripts/paper/`), the paper's
  figure scripts, `docs/paper-readiness.md` and the nightly-median test —
  moved to a separate `stips-paper` repository, which also archives the
  rebuild's products. The rebuild driver now runs a STIPS checkout given by
  `--stips`. The diagnostic scripts in `scripts/analysis/` stay here.

## [2.2.4] — 2026-10-08

The first release archived on Zenodo with a DOI; it is the version the paper
cites. Nothing here changes a paper product: those were produced on 2.2.2 and
2.2.3 (see `docs/paper-readiness.md`).

### Fixed
- `stips refcat fetch` exits non-zero when a catalogue fails to fetch, so the
  paper rebuild driver retries the step instead of continuing without refcats.
  (#56)

### Changed
- Paper figure scripts write to `<rebuild>/figures` when `STIPS_PAPER_DATA` is
  set, and label each band with its magnitude system. (#56)
- The paper's supernova lightcurve figures (`scripts/analysis/plot_sn_vs_ztf.py`)
  plot nightly robust medians per band instead of every visit, and write
  `products/<sn>/lightcurve_nightly.csv` for the paper's tables (`--per-visit`
  restores the old plots). Per (night, band): S/N >= 5, median, reject beyond
  max(3 MAD, 0.15 mag), re-median, error of the median. The rule lives in
  `scripts/paper/nightly.py`, which `compare_external.py` now shares; the
  external-comparison offsets are unchanged. No pipeline product changes.
  (#57)
- Citation metadata for Zenodo: `.zenodo.json`; `CITATION.cff` gains author
  affiliations, ORCIDs and a second author (Kyle B. Westfall).
- License declared as GPL-3.0-or-later (was GPL-3.0-only in `CITATION.cff`),
  matching the LSST Science Pipelines. The license text is unchanged.

## [2.2.3] — 2026-10-07

### Fixed
- HD 189733 and the variable-star targets (AC And, CY Aqr, DY Peg) calibrate
  with MONSTER refcats again. In `gaia_ps1` mode these crowded Galactic fields
  got worse astrometry: HD 189733's host dropped out of the fallback config's
  star catalogue (a 646% "transit"), and 14 of 186 AC And visits had wrong WCS
  solutions. Their transit depth, periods and amplitudes are relative
  photometry. Landolt stays `gaia_ps1`, which it validates. (#53)
- The transit search no longer runs on PSF forced photometry after the
  differential-photometry step fails. (#53)

The transit and variable-star results are rebuilt on this release.

## [2.2.2] — 2026-10-06

### Fixed
- **Forced photometry read only one band group's science.** Science runs per
  band group (r,i / rp / ip), each into its own processCcd parent; forced
  photometry used the newest only, so since 2.2.0 the Sloan-like rp frames
  were never measured on most nights. It now joins every parent, as DIA does.
  The differential-photometry step had the same flaw and also read only the
  first night. (#51)
- Paper rebuild driver: a whole-mode target with a failed step is retried on
  rerun instead of being marked done; provenance ignores the run log under
  `provenance/`. (#51)

The paper's numbers are rebuilt on this release.

## [2.2.1] — 2026-10-05

### Fixed
- `stips calib-metrics --night` filtered `exposure.day_obs == <night>`, but
  Lick's `day_obs` is the UT date (night 20230618 is UT 20230619), so every
  per-night extraction matched nothing. It now selects the night's UT
  `day_obs` values. The paper rebuild driver no longer prunes a night whose
  extraction failed; it marks it for retry instead. (#48)

The paper's numbers are rebuilt on this release; v2.2.0's rebuild lost the
per-night calibration metrics to this bug.

## [2.2.0] — 2026-10-05

The paper-freeze release. A pre-freeze audit found and fixed calibration and
data-loss bugs that affected published-grade numbers; every paper result is
rebuilt from raw on this tag by `scripts/paper/rebuild.py`.
**Migration:** re-ingest Nickel repos (r′/i′ frames now ingest as `rp`/`ip`),
and add `rp`/`ip` to campaign `bands:`. Cousins B/V/R/I magnitudes from the
`gaia_ps1` path are Vega; lightcurves say so in `mag_system`.

### Fixed
- **Nickel 2020–2023 r′/i′ frames were calibrated as Cousins R/I.** Their
  headers carry a malformed card (`FILTNAM = 'r'                '`) that the
  stack's FITS reader returns as `r`, which upper-cased to Cousins `R`. The
  filters are Sloan-like (colour slope vs PS1 −0.03/−0.05 against −0.24/−0.35
  for Cousins), and the Cousins terms put those magnitudes 0.23 (r) / 0.47 (i)
  mag off PS1 AB. They are now the `rp`/`ip` physical filters and bands. **Re-
  ingest Nickel repos.** (#42)
- A sub-frame test readout (82×50, 57×25) in a night's raw directory crashed
  ISR and failed the whole night; a pre-ingest screen now drops subframes,
  truncated and unreadable files. (#41)
- `stips fphot` without `--band` measured only the newest per-band diff run. (#41)
- DIA matched `--object` exactly while science matched substrings, so frames
  whose OBJECT differs in form were calibrated but never differenced. (#41)
- The transit search ran on PSF forced photometry instead of the differential
  lightcurve, and an empty differential result counted as success. (#43)
- `landolt-validate` applied the AB→Vega shift to bands already on Vega, and
  accepted sub-S/N-5 matches (noise beside an undetected standard).

### Added
- `InstrumentProfile.vega_bands` and a `mag_system` lightcurve column: Nickel
  Cousins B/V/R/I are Vega in the `gaia_ps1` path; rp/ip and MONSTER-mode bands
  are AB.
- `scripts/paper/`: rebuild-from-raw driver with provenance, forced-phot
  export, external-photometry comparison, per-filter colour-slope test. (#44)
- `CITATION.cff`. (#44)

### Changed
- Landolt, HD 189733 and the variable-star configs calibrate with `gaia_ps1`,
  like the SN campaigns. The Landolt target now validates that path (BVRI mean
  offsets ≤ 0.012 mag); MONSTER mode leaves B/V 0.3–0.4 mag off.

## [2.1.0] — 2026-10-03

A science-quality release. The headline is the PS1 asinh decode: every PS1
template ingested before it was brightness-compressed, so both Nickel campaigns
(2023ixf, 2020wnt) were rebuilt on this code. It also adds the external-template
framework (PS1 + SkyMapper, multi-patch ingest), Gaia-only refcats and validated
DIA for southern CTIO fields, and fixes Nickel ingest for 2020+ data.
**Migration:** re-ingest every external template with `--overwrite` and rerun the
DIA that used it; re-ingest existing ctio1m repos (exposure ids changed).

### Fixed
- **SkyMapper templates ingested saturated bright stars unmasked.** SkyMapper's
  SIA serves single-epoch ~100 s frames, not deep stacks, so bright stars reach
  the detector ceiling — and the frames say so. Measured on the NGC2298 i-band
  frame: `SATURATE = 65435`, with real cores pinned at 64539 and flat-topped
  over 5+ pixels, negative bleed undershoot (−97, −98) immediately adjacent, and
  893 pixels in 35 blobs above 0.9× the level. Nothing read that card:
  `fits_to_lsst_exposure()` masked only non-finite pixels, so clipped cores were
  ingested as if they were valid flux, corrupting the template's noise estimate
  and offering the kernel fit candidates built on clipped data.
  `imaging.saturation_mask()` now reads an adapter-supplied saturation card,
  flags pixels at or above 0.9× the declared level, grows the footprint by 2 px
  to cover the bleed artifacts, sets the LSST `SAT` plane, and excludes those
  pixels from the variance estimate. Ingested templates record
  `TEMPLATE_SAT_PIXELS` / `TEMPLATE_SAT_LEVEL`. `SkyMapperSource` declares
  `SATURATE`; `PS1Source` deliberately declares **none** — PS1 stacks coadd ~27
  dithered exposures, their bright-star cores measure as clean un-clipped PSFs,
  and the header's `CELL.SATURATION` describes a single input cell rather than
  the stack.

  **This does not currently change DIA output, and is not claimed to.** Measured
  on NGC2298 (18 visits, same science runs and DIA configs, template collection
  the only variable), against the coadd-template truth run
  `20260726T150523Z`:

  | | before | after |
  |---|---|---|
  | purity vs truth | 32.4% | 32.4% |
  | recall vs truth | 35.1% | 35.1% |
  | false positives | 5836 | 5843 |

  The reason is traceable: the `SAT` plane is set on `template_coadd` (4738 px)
  and survives the rewarp to `template_detector` (7773 px), but
  `template_matched` carries **0** SAT pixels — the PSF-matching convolution in
  `AlardLuptonSubtractTask` drops it, so the template's saturation flag never
  reaches the difference image. Independently, only 1 of 2753 DIA sources sits
  within 3 px of a SAT pixel, so saturated stars are not what drives the CTIO
  false-positive population anyway. The fix is kept because it closes a real
  latent defect in what gets ingested; making it *act* on detection needs the
  mask-propagation gap above resolved first.
- **PS1 stack templates were ingested asinh-compressed, never decoded.** PS1
  stores stack pixels asinh-scaled, with the softening in `BSOFTEN`/`BOFFSET`
  (`flux = BOFFSET + BSOFTEN·2·sinh(stored·ln10/2.5)`); nothing in STIPS applied
  the inverse. The `fitscut` service returns already-decoded pixels and strips
  `BSOFTEN`, so the bug only bit when fitscut lost the race to the MAST or
  `ps1filenames` paths — which is what happened in practice: every cached PS1
  template on disk was a raw 6302×6283 skycell spanning `[-2.86, 9.47]` with
  `BSOFTEN` still set. The effect is a ~1e6:1 dynamic range crushed to ~10:1.
  Because asinh is nearly linear near sky, faint stars still subtracted cleanly
  (the DIA kernel just absorbs the constant scale) while the deficit grew with
  brightness — measured encoded/true aperture flux on the 2023ixf skycell ran
  0.86 at 20–50σ down to 0.02 above 1600σ, which is the brightness-dependent
  template deficit previously read as template saturation. It is **not**
  saturation: the PS1 stack mask flags no pixels in that field, the stack's
  bright-star cores are unclipped, and Nickel science stars peak ~20k ADU
  against a 65535 rail. Decoding now happens in `fits_to_lsst_exposure()`, the
  single point where any source's FITS becomes an `Exposure`, so it covers all
  three PS1 download methods and any future source using the same convention;
  it runs before the `PhotoCalib` scaling (the zeropoint describes decoded
  counts) and before the finite check. Ingested templates record
  `TEMPLATE_ASINH_DECODED`. **Re-ingest existing PS1 templates and rerun the DIA
  that used them.** Measured on `nickel_smoketest_repo` (same science runs, same
  default DIA configs, template collection the only variable):

  | metric | 20230521 before → after | 20230519 before → after |
  |---|---|---|
  | difference images | 15 → 15 | **2 → 10** |
  | median star residual, 20–50σ | +11.1% → **+3.7%** | +20.5% → **+1.0%** |
  | median star residual, 50–100σ | +71.3% → **+5.7%** | +74.4% → **+1.7%** |
  | median star residual, 100–200σ | +78.7% → **+0.7%** | +87.0% → **+1.9%** |
  | SN 2023ixf detected | 1/15 → **14/15** visits | 2/2 → **7/10** visits |
  | SN median SNR | 446 → **700** | 189 → **768** |
  | dia sources / visit | 410 → 340 | 274 → 263 |

  The SN itself keeps a ~100% residual, which is correct — a transient has no
  template flux. The 20230519 gain indicates the `NoKernelCandidatesError`
  starvation on that night was largely this bug: a template whose bright stars
  are suppressed ~50× offers little for the kernel fit to lock onto.
- **nickel: frames with `OBSNUM` ≥ 10,000 could not be ingested.** Nickel's
  `OBSNUM` is an observatory-wide running counter, not a per-night sequence; it
  exceeds 10,000 on many nights (already by 2018, though it also resets, so some
  nights stay 4-digit) — but the profile fed it straight to
  `pack_exposure_id`, which only accepts a 4-digit sequence. Every frame of both
  documented campaigns died at ingest with `seqnum 228041 is out of range
  [0, 10000)`: `stips calibs 20230519` extracted metadata from 0 of 176 files and
  aborted, so the pipeline was unreachable for 2020wnt (OBSNUM 12001+) and 2023ixf
  (228001+). `exposure_id` now packs `OBSNUM % 10000`; that same night now ingests
  176/176. **No migration is needed:** the fold is the identity below 10,000, so
  every id already in a repo is unchanged, and ids at or above it never made it
  into a repo to begin with. `observation_id` deliberately keeps the full OBSNUM,
  so it still names the source frame (`20230520_228001` → `d228001.fits`).
- **External templates were truncated to a single skymap patch.**
  `ingest_exposure_to_butler()` reprojected the survey cutout onto the one patch
  containing the target coordinate and discarded everything outside it, while
  the self-coadd template path has always ingested every patch the field
  overlaps and let `rewarpTemplate` gather them at DIA time. Same field, same
  tract, i band: the validated CTIO self-coadd covers 4 patches (142, 143, 156,
  157 of tract 444); the external ingest wrote 1 (156). On NGC2298 the assembled
  SkyMapper mosaic spans 17.0′ × 25.5′ but the ingested `template_coadd` kept
  only 10.0′ × 15.3′ of it — the target sits 6.2′, −8.7′ off the centre of patch
  156 — leaving 39.0% science-field coverage and a template edge running through
  the field. The ingest now traces the exposure's sky footprint from its WCS and
  bbox, asks the skymap (`findTractPatchList`) which patches that footprint
  overlaps, and writes one `template_coadd` per patch, skipping any whose
  reprojection carries no usable data (an all-`NO_DATA` template is worse than an
  absent one, since `rewarpTemplate` would still gather it). This is shared
  PS1-inherited code, so **PS1 templates are affected too**: any PS1 cutout wider
  than one patch was being clipped the same way. Re-ingest existing external
  templates and rerun the DIA that used them. `ingest_exposure_to_butler()` now
  returns a list of data IDs (target patch first) and `ExternalTemplateResult`
  gained a `patches` field.
- **`stips external-template` never reported which tract/patch it wrote.**
  `ingest.py` configures `logging` with the default handler, which writes to
  *stderr*, so under `capture_output=True` every `Data ID:` line lands in
  `result.stderr` while `result.stdout` is empty — and the parse only looked at
  stdout. `tract`/`patch` came back `None` on every real run and the CLI silently
  omitted the line. Both streams are scanned now, which is also what surfaces the
  new multi-patch `Patches: [...]` summary.
- **`stips dia` ignored the YAML's `configs.dia.*` overrides.**
  `dia.run()` has accepted `subtract_config_file`/`detect_config_file` since the
  YAML-driven `stips run` path started wiring them from
  `configs.dia.subtract_images`/`detect_and_measure`, but the `stips dia` CLI
  subcommand exposed neither flag and passed neither — so the documented
  `stips dia <night> -b i --template ...` workflow silently fell back to the
  instrument-dir default DIA config instead of the one the YAML specified.
  Caught on a SkyMapper DIA run: the ctio1m default (`mode='convolveTemplate'`,
  `spatialKernelOrder=2`) applied instead of `subtractImages_skymapper.py`'s
  `mode="auto"`, forcing a deconvolution that drove the spatial condition
  number to 2.4e10. `stips dia` now has `--subtract-config`/`--detect-config`
  (resolved instrument-dir-first via the same `config.resolve_config()` as
  `stips run`), falls back to the `-c` YAML's `configs.dia.*` when a flag is
  omitted, and always prints which config file is in effect so this failure
  mode is visible instead of silent.
  **Migration: this is a behaviour change, not only a fix.** Every previous
  `stips dia` result was produced with the instrument-dir defaults while its YAML
  declared something else, so `stips dia` output from before and after this
  change is NOT comparable. Measured on Nickel 2023ixf 20230519 with a probe
  config (`kernelSize` 21→19, plus `nSigmaForKernel` reverting to the stack
  default 7.0 because a `-C` file replaces the default wholesale): 548 → 583
  DIA sources, a 6.4% change. Real configs differ by more still. Rerun any
  `stips dia` results you intend to compare against new ones.
- **External templates attached a PSF at the wrong pixel scale.**
  `reproject_to_patch()` warped a survey cutout onto the skymap patch grid but
  copied the `GaussianPsf` across unchanged — and `GaussianPsf` stores its width
  in *pixels*, so the attached PSF silently misrepresented the seeing by the
  ratio of the two pixel scales. For a SkyMapper frame (0.4976 ″/px → 0.2887
  ″/px) a real 1.68″ FWHM read as 0.98″, understating the seeing by 1.72×, which
  makes `subtractImages` `mode="auto"` pick the wrong convolution direction. The
  bug predates the SkyMapper work and is WORSE for PS1 on Nickel, not milder:
  measured end-to-end on 2023ixf, a PS1 template (0.25 ″/px native) reprojected
  onto a Nickel patch (0.3998 ″/px) attached a **1.920″** PSF where PS1's assumed
  seeing is **1.2″** — 60% too wide, on every PS1 template Nickel has ever
  ingested. The same fix restores the
  `TEMPLATE_*` provenance keys, which reprojection also dropped. **Migration:
  this changes the PSF attached to every PS1 template.** Re-ingest existing
  templates and rerun any DIA that used them. Only an end-to-end ingest
  exercises this code (it needs a real skymap and the stack), so a regression
  test now pins the rescaling.
- **A mistyped `template.type` silently built nothing.** The dispatch was an
  if/elif chain with no `else`, so `template: {type: skymappper}` ingested no
  template and then failed every band in DIA with "no template available" —
  after the run had already spent hours on calibs and science. `RunConfig` now
  rejects an unrecognised value when the YAML is parsed, naming the valid ones.
- **External-survey cutouts were only validated for PS1.** The coverage and
  angular-size checks ran inside PS1's downloader, so an edge-trimmed SkyMapper
  frame — a well-formed FITS that clears the response-size floor but misses the
  target or leaves no DIA overlap margin — was converted and ingested silently,
  surfacing much later as a `NoKernelCandidatesError`. Both checks now run
  post-fetch for every source.
- **ctio1m: `exposure_id`/`observation_id` collided across consecutive nights.**
  CTIO straddles UT midnight and Y4KCam seqnums reset each local night, so the
  UT-day-keyed id mapped night N's post-midnight frames and night N+1's afternoon
  calibs to the same value (real: `36730069` on SA98 20100120/20100121), failing
  Butler exposure-sync on ingest and yielding an empty calib qgraph. Both ids now
  key on the local night parsed from the `y{YYMMDD}.{seq}.fits` filename. This
  changes ingested ids for ctio1m — existing ctio1m repos must be re-ingested.
- **crosstalk:** certification is idempotent; re-certifying a static calib raised
  `ConflictingDefinitionError` and broke every night after the first.
- **ctio1m:** the U+CuSO4 near-UV filter is recognised; nights whose biases sat at
  that wheel slot had zero ingestable biases (real: 20100120).
- **ctio1m: 2006 astrometry failed on every field** (NGC2298: 0/45 visits at
  ~8.8″ residual). The 2006 run's seed WCS carries a stable ~7′ pointing offset
  (+257″ E / +320″ N), far outside the matcher's search radius. The profile's
  `tracking_radec` now applies that offset for 2006 observations only (fail-closed
  on missing dates); 2010+ data is byte-identical. A dense-field matcher config
  (`ctio_dense.py`) caps bright-star and reference counts for crowded cores.
- **ctio1m: amp A01 was hardware-dead for the whole Jan-2010 run** and left a
  hard-edged block in SA98 difference images. A new `obs_ctio1m_data` curated
  defect package masks the A01 quadrant for exposures from 2010-01-01 on, via
  calib validity ranges; 2006 data keeps all four amps. ctio1m now runs
  `doDefect: True`.

### Added
- **SkyMapper templates are now mosaicked, lifting the 10.2′ ceiling.** The
  DR4 SIA's 0.17° cap is per REQUEST, not per frame: several offset requests
  against the same `image=` id come back as exact sub-arrays of one CCD pixel
  grid — identical `CRVAL`, identical `CD`, identical `PV` distortion terms,
  differing only in `CRPIX`. `fetch` now issues a small overlapping grid of
  requests against the single selected frame whenever `--size` exceeds the cap
  and pastes the tiles together at integer pixel offsets (`CRPIX_ref −
  CRPIX_tile`), so there is **no reprojection, no resampling, and hence no
  interpolation error, no PSF change and no photometric change** — the assembled
  header keeps the frame's `CRVAL`/`CD`/`PV` and only shifts `CRPIX` to the new
  origin. Tiles that disagree on `CRVAL`/`CD`, or that are offset by a
  fractional pixel, raise `TemplateSourceError` rather than being pasted
  misaligned. This was the binding constraint on the whole SkyMapper path: a
  single 10.2′ cutout covers ~16% of a ~20′ Y4KCam field, which is why 85% of
  every NGC2298 difference image came back flagged `NO_DATA`. Measured on that
  same field at `--size 0.4`: nine tiles assemble to 17.0′ × 25.5′ and the
  ingested `template_coadd` covers **37% of the science patch, up from 14%**.
  The remaining limit is the detector, not the service — a SkyMapper CCD is
  2048 × 4096 px at 0.4976″/px = 17′ × 34′, so a square request wider than 17′
  comes back truncated on the short axis and says so explicitly in the log
  (`max_assembled_deg` records the ceiling). A `--size` at or under 0.17° still
  issues exactly one request and is byte-for-byte unchanged.
- **`stips external-template --source {ps1,skymapper} --ra --dec -b <band>`** —
  one command for every external-survey DIA template, replacing the
  source-specific `stips ps1-template` (retained as a working alias). Adds
  `--mjd-start`/`--mjd-end` so a template frame can be chosen from epochs that
  exclude the transient. `--source` choices, the `template.type` dispatch, and
  DIA's explicit-collection lookup all read the adapter registry, so a new
  survey is one `sources/*.py` file — see `docs/architecture.md`.
- **`template.type: skymapper`** in the run YAML — SkyMapper DR4 as an external
  template source for southern fields (Dec ≲ −30°) with no PS1 coverage. It is
  deliberately **Tier-2 and explicit-only**: `template.type: auto` never selects
  it. DR4 serves single-epoch 100 s frames (5 s frames are rejected outright),
  capped at 0.17° (10.2′) per request — see the mosaicking entry above — at ~2″
  seeing. Validated against
  a CTIO self-coadd on NGC2298: DIA succeeds on every visit but recovers 36% of
  the difference-image sources and leaves an ~8× larger systematic residual, so
  prefer `template.type: coadd` whenever SN-free epochs exist. Full comparison
  in `docs/skymapper-template-validation.md`.
- profile `template_band_maps` — per-source external-template band policy
  (`SOURCE -> (LOCAL band -> that survey's band)`), additive alongside
  `ps1_band_map`, which stays because it also builds the PS1 refcat filterMap
  via `STIPS_PS1_BAND_MAP`. Band names are **not** interchangeable across
  surveys: SkyMapper's `v` is a ~384 nm violet filter, not Johnson V (~551 nm),
  so ctio1m maps only `{"r": "r", "i": "i"}` and excludes `v` rather than
  silently fetching a near-UV template for a green science image.
- profile `fov_arcmin` — approximate science field of view, the input to the
  template-coverage warning (a cutout narrower than the field leaves dithered
  pointings with no PSF-matching kernel candidates). Nickel `6.3`, ctio1m
  `20.0`; unset means no warning.
- `stips.pack_exposure_id(days_since_2000, seqnum)` — the low-level id packer, for
  profiles whose local night does not map 1:1 onto a UT day. `make_exposure_id`
  now delegates to it and is unchanged for callers.
- `stips.core.pipeline.find_aliasing_exposure_ids()` — a pre-ingest scan, run by
  `stips calibs`, that aborts naming the offending files when two frames in a
  night would claim one `exposure_id`. A profile that folds a wide sequence
  keyword into the packed id's 4-digit field (Nickel: `OBSNUM % 10000`) is only
  injective within one window, and neither the `exposure_id` hook (one header at
  a time) nor `pack_exposure_id`'s range guard (the folded value is in range by
  construction) can see a fold collision. The night-wide scan can.
- ctio1m Y4KCam DIA tuning (bleed masking, SAT-excluded detection, spatial kernel)
  and coadd visit-selection/warp configs; SA98 validation pipeline configs.
- refcat: synchronous Gaia TAP fallback for async result-storage outages.
- **`refcat.mode: gaia`** — astrometry and photometry from Gaia DR3 alone, for
  fields south of PS1's −30° floor. The on-demand refcat ensure skips the PS1
  fetch in this mode, and the science QA photometric ref-match follows the mode.
  Validated end-to-end on NGC2298 (Dec −36) with a coadd-template DIA config.
  The Gaia colour terms are not yet populated, so final magnitudes are uncorrected.
- `scripts/utilities/prune_night.py` — drops a night's intermediates (raws,
  constructed calibs, processCcd, DIA) once its forced photometry is written.
  Keeps a multi-night campaign repo at ~1.7 GB on a nearly-full disk; everything
  dropped is rebuildable by re-running the night.

### Changed
- **External-template exposure metadata keys are source-namespaced:**
  `PS1_FILTER`/`PS1_ZEROPOINT` are now `TEMPLATE_SOURCE`/`TEMPLATE_ZEROPOINT`
  (joined by `TEMPLATE_FWHM_ARCSEC`), since one converter now serves every
  survey. Templates ingested before this carry the old keys; anything reading
  them must handle both or re-ingest.
- **The default external-template download directory moved** from
  `<repo>/ps1_templates` to `<repo>/external_templates`. The old directory is
  not read, so the first run after upgrading re-downloads each cutout once;
  delete the stale directory afterwards, or pass `--output-dir`.
- ctio1m pipeline configs use the neutral `calibrateImage` default instead of
  Nickel's fitted `tuned_configs/` (which are fitted for Nickel's CCD and now live
  under `instruments/nickel/configs/`). A Y4KCam-fitted config is future work.
- ctio1m DIA uses a reduced 9-function Alard–Lupton kernel basis instead of the
  stack's 27. On NGC2298 this drops the median kernel condition number from
  ~3e6 to ~1e3 with no loss of subtraction quality.

## [2.0.1] — 2026-07-14

### Fixed
- Singularity release publication works end-to-end: fuse build deps on current
  runners, v-less image tag, ORAS publication to `ghcr.io/<owner>/stips-sif`
  (the 3.2 GB .sif exceeds GitHub's 2 GiB release-asset cap), `registry login`
  for Singularity 4.x, and `packages: write` job permissions. A
  `test-singularity` PR label runs the publish end-to-end inside a PR.
- `make test` stack harness: `packages/refcats/src` was missing from
  PYTHONPATH (refcats tests could not import outside with-stack.sh).

### Changed
- Shared exec tooling (Makefile, with-stack.sh, bootstrap, docker images, BPS
  sites) discovers instrument data packages generically under
  `$INSTRUMENT_DIR` (any `ups/`-bearing subdir) instead of hardcoding
  `obs_nickel_data`/`testdata_nickel`; retired stale `obs_nickel` references
  (CI step name, fitter guidance strings, test mock paths).

## [2.0.0] — 2026-07-14

A large documentation-and-correctness audit campaign. The grouped summary below
is at user level; the finding-tagged subsections that follow it keep the detailed
per-area notes.

### Added
- **Generic calibration tooling** as console scripts, so a fork produces its own
  fitted assets instead of copying Nickel's: `stips-defects-build` (defect maps
  from master calibs), `stips-colorterms-fit` (Landolt-fit color terms), and
  `stips-tune-calibrate-image` (searches `calibrateImage` parameters to produce
  `tuned_configs/`). Recipes under `instruments/nickel/{defects,colorterms,tuning}/README.md`.
- **`stips measure-crosstalk`** and declarative `CrosstalkSpec` for multi-amp
  cameras (detailed below).
- **Shared framework modules** a fork builds on: `stips.fetch`
  (`make_fetch_data` wrapper + `parse_night`; a fork's `fetch.py` implements only
  `_fetch_night` + `build_kwargs`), `stips.make_exposure_id` (the reference
  31-bit-safe exposure-id scheme), `stips.testing.instrument_contract` (the
  auto-discovered contract-test harness — see `docs/instrument-contract.md`),
  `core/dataset_types.py` (central Butler dataset-type constants, pinned by a
  contract test), `core/download.py` (download orchestration), `core/query.py`
  (a Butler string-literal sanitizer), and `core/pipeline.PipetaskStage` (shared
  pipetask/butler choreography).
- **Profile `ps1_band_map`** — declares which local science bands are
  PS1-template eligible and the PS1 band each maps to (drives `template.type: auto`).
- **New docs**: `docs/stack-bump-runbook.md`, `docs/instrument-contract.md`,
  `docs/migrations.md`, and `packages/obs_stips/instrument_defaults/README.md`
  (the tiering contract).

### Changed
- **Packaging is framework-only.** `packages/` now holds just `stips`,
  `obs_stips`, and `refcats`; **all** Nickel assets moved under
  `instruments/nickel/` (`obs_nickel_data`, `testdata`, `defects/`,
  `colorterms/`, `tuning/`, and the vendored `lick_searchable_archive`, marked
  with a `VENDORED.md`).
- **`refcats` is now the `stips-refcats` distribution** (import `stips_refcats`);
  the old `nickel_refcats` import remains as a thin re-export shim.
- **`obs_data_package` resolution precedence** clarified: `package_dir` overrides
  the location; otherwise STIPS looks under `<INSTRUMENT_DIR>/<obs_data_package>`
  first, then the reference `packages/<name>` layout.
- **CLI handlers thinned** — they delegate to core modules: `download`
  orchestration lives in `core/download.py`, `clean` is a plan/execute flow,
  lightcurve display options flow only through `LightcurveConfig`, and
  `dashboard` requires and threads the `-c` config.
- **Ops**: the scheduled stack canary runs the pipeline graph-build tests so
  config-field breakage surfaces before the pin moves; CI validates pushes on the
  active development branches. Supported release `v30_0_3`, CI weekly pinned at
  `w_2025_32` (see `docs/stack-bump-runbook.md`).

### Fixed
- **Calibs success is verified against products**, not just the pipetask exit
  code — a run that exits 0 but writes no bias/flat is now reported as a failure
  (or partial), not a success.
- **DIA and forced photometry query both UT `day_obs` values** a local observing
  night can span (pre-/post-midnight), so exposures near UT midnight are no
  longer silently dropped.
- **Coadd template rebuild is build-then-swap** (F-009): a rebuild writes to a
  fresh RUN and the parent chain is repointed only on success, so a failed
  rebuild can't leave a half-built template in place.
- **Provenance records the true LSST *pipelines* (EUPS) version and the profile's
  instrument**, distinct from the conda/rubin-env name.
- **`filter_map.py` covers CTIO 1.0m's uppercase `U`** physical filter
  (previously a live KeyError for analysis tasks on U-band data).

### Deprecated
- The `nickel_refcats` import path — use `stips_refcats`; importing it emits a
  `DeprecationWarning`.
- The `nights: {YYYYMMDD: {band: [...]}}` mapping form in run configs — only its
  night keys are read now; use the `science: nights: [...]` list.

### Migration notes
- **QA task labels renamed `...Nickel` → `...Visit`** (F-013): task labels become
  Butler dataset-type names, so dashboards/queries referencing the old
  `...Nickel_metadata`/`_log`/`_config` names must update. No data loss and
  nothing to migrate on disk. See `docs/migrations.md`.

### E2E validation fixes
End-to-end runs on real Nickel and CTIO/Y4KCam data hardened the venv/stack
boundary and the forking path:
- **Refcat fetch runs from a plain venv.** The HTM cone-coverage math and
  `convertReferenceCatalog` now fall back to in-stack execution automatically, so
  `stips run` with `refcat.mode: gaia_ps1` works without a stack-activated shell
  (previously it only ran from inside the stack).
- **`stips-refcats` declares its fetch dependencies** (`astroquery`, `astropy`,
  `numpy`, `pandas`), so a clean `uv sync --group dev` can fetch Gaia/PS1.
- **A failed refcat ensure aborts `stips run` early** with the root cause, instead
  of warning and limping into science where every night died with an opaque
  `MissingDatasetTypeError('panstarrs1_dr2')`.
- **Instruments with no tuned `calibrateImage` config now run science** on a
  neutral schema-compatibility default (measurement plugins/radii/slots only, no
  instrument tuning) — a fork no longer needs to fit `calibrateImage` before
  processing. An explicitly-configured-but-missing config path still errors (typo
  protection).
- **gaia_ps1 mode now covers the stage-1 QA ref-match tasks** via two neutral
  overlays (`refcats_gaia_ps1_qa_astrom.py`, `refcats_gaia_ps1_qa_photom.py`), so
  fields outside local MONSTER shard coverage no longer fail quantum-graph
  construction.
- **Instrument config overrides no longer import the profile.** The PS1 band map
  reaches the `refcats_gaia_ps1*.py` overlays through the new `STIPS_PS1_BAND_MAP`
  env var (exported by `run_with_stack`), fixing saved-quantum-graph replay, which
  re-imports every module a pex_config file touched during config exec.
- **PS1 templates must exceed the camera FOV plus dither margin.** On a large
  (~20′) FOV like Y4KCam, too small a `template.size` left dithered pointings with
  no PSF-matching kernel candidates (`NoKernelCandidatesError`).
- **Dashboard requires `fastapi>=0.110`** (request-first `TemplateResponse`).

### Defaults tiering: Nickel-fitted science calibration moved out of the framework tier (F-012)
- **Moved to `instruments/nickel/configs/`** (behavior for Nickel unchanged —
  instrument-dir-first resolution finds them there): the Landolt-fit
  `colorterms.py`, all `calibrateImage/tuned_configs/*.py`, and the Nickel-band
  `refcats_gaia_ps1.py`.
- **Neutral framework defaults** in `obs_stips/instrument_defaults/configs/`:
  `colorterms.py` is now an **empty** library; `apply_colorterms.py`,
  `analysisToolsPhotometricCatalogMatchVisit.py`, and `refcats_gaia_ps1.py` are
  instrument-aware — they load the active instrument's `configs/colorterms.py`
  / `configs/filter_map.py` via `$INSTRUMENT_DIR` when present and enable color
  terms **only when the resolved library is non-empty** (an empty library with
  `applyColorTerms=True` fails LSST config validation). The neutral
  `refcats_gaia_ps1.py` derives its PS1 filterMap from the profile's
  `ps1_band_map`.
- `filter_map.py` now covers CTIO 1.0m's uppercase `U` physical filter
  (previously a live KeyError for analysis tasks on U-band data).
- DRP.yaml/dia/coadd/skymap threshold comments relabeled honestly as
  "reference tuning from the Nickel 1-m"; new
  `packages/obs_stips/instrument_defaults/README.md` documents the tiering
  contract (what a fork inherits vs MUST review — photometric calibration!).

### QA task-label rename: `...Nickel` → `...Visit` (F-013)
- Renamed 5 analysis/QA task labels in DRP.yaml /
  analysis-visit-single-visit.yaml / visit-quality-detector.yaml
  (`analyzeCalibrateImageMetadataNickel` → `...MetadataVisit`,
  `*SingleVisitStar{Astrometric,Photometric}RefMatchNickel` → `...RefMatchVisit`).
  Task labels become dataset-type names in every fork's Butler repo.
- **Migration:** no data loss; reruns write under the new label-derived dataset
  names; dashboards/queries referencing the old `..Nickel_metadata/_log/_config`
  names must update. See `docs/migrations.md`.

### Crosstalk for multi-amplifier instruments
- **Declarative crosstalk**: instrument profiles can carry a `CrosstalkSpec`
  (N×N coefficient matrix + units). STIPS builds a `CrosstalkCalib`, certifies it
  into `{prefix}/calib/crosstalk` (chained into the curated calib chain), and
  auto-enables ISR `doCrosstalk` — no forked pipelines.
- **Measurement** (`stips measure-crosstalk <nights…>`): derives coefficients from
  exposures via cp_pipe's `cpCrosstalk` pipeline (reusing the profile's
  `isr_overrides` on the measurement ISR), certifies the result, and exports the
  matrix (ECSV) for inspection. Run once when no coefficients are known.
- **CTIO1m / Y4KCam** ships a **measured** 4×4 matrix (derived with
  `measure-crosstalk` on the E2 standard field, night 20111113; ~0.1–0.4%,
  largest between adjacent quadrants). Re-measure on a denser field to tighten.
- See `docs/crosstalk.md`.

## [1.0.0] — 2026-06-24

### Framework refactor (instrument-neutral)
- Renamed the suite to **STIPS**; split into `stips` (CLI + core) and `obs_stips` (generic LSST glue)
- **Declarative instrument profiles** under `instruments/<name>/` (`profile.py` + camera + hooks), loaded by path via `INSTRUMENT_DIR` — no per-instrument `obs_` package or EUPS product
- Single `-c <config.yaml>` is the sole config source (removed `.env`, `-p/--profile`, and `os.environ` fallbacks)
- Profile-driven collection prefix, skymap name/geometry, filters, header translation, ISR overrides, `boresight_rotation_angle`, and `fetch_data`
- Generic reference pipelines/configs shipped from `obs_stips/instrument_defaults/` with an instrument-dir-first resolver

### CTIO 1.0m / Y4KCam — second instrument
- First **multi-amplifier** camera (4-amp, central-cross overscan); measured per-amp gains; amp-flip + parallel-overscan ISR fixes (seam-free assembly)
- **On-chip binning** support (`CCD_BINNING`): one profile reduces unbinned 4064² and 2×2-binned 2072² raws (imaging scales, overscan fixed)
- **NOIRLab Astro Data Archive** `fetch_data` hook (funpack + integer-`FILTER` normalization)
- Astrometry fix: profile `boresight_rotation_angle=180°` (Y4KCam mounted rotated) — median residual 13.5″ → 0.12″
- Validated end-to-end: unbinned 2007 PG1047 (sub-arcsec astrometry, ~46 mmag photometry) and 2×2-binned 2011 B/V/R/I standard fields (0.578″/px, sub-arcsec V/R/I)

### Extended Objects & Narrowband Filters

- Per-filter narrowband isolation for Halpha, [OIII], g', r' filters
- Per-band-group processing (broadband and narrowband processed separately)
- 12-night extended objects survey configuration (2023B-2025B)
- 9 supported filters: B, V, R, I, g', r', Halpha, [OIII], clear

## [0.1.0] — 2026-03-03

### Exoplanet Transit Detection
- First exoplanet transit detection with the Nickel 1-meter telescope
- HD 189733 b detected at 13-sigma from 400 B-band exposures (4s cadence)
- LSST-native `DifferentialPhotTask` for ensemble differential aperture photometry
- BLS transit search module with configurable period/duration grids

### Variable Star Period Recovery
- Lomb-Scargle period analysis module for pulsating variables
- CY Aqr, DY Peg, AC And periods recovered from single-night V-band observations
- Example variable star campaign templates

### BPS / HPC Integration
- Full pipeline validated end-to-end through BPS, Parsl, and Slurm
- Docker Slurm test cluster (AlmaLinux 9, Slurm 22.05)
- Singularity `.def` for HPC deployment
- Conditional `--qgraph-datastore-records` for BPS vs. local execution

### Supernova Lightcurves
- SN 2023ixf (Type IIP): 22-night monitoring campaign, classic plateau lightcurve
- SN 2020wnt (SLSN-I): multi-epoch detections at z=0.032
- PS1 and Nickel coadd template strategies for DIA
- Configurable lightcurve display: apparent/absolute mag, flux, days-since-explosion

### Pipeline Architecture
- YAML-driven full pipeline orchestration (`nickel run`)
- Four-tier calibrateImage fallback chain (99.4% science processing success)
- Per-band DIA and forced photometry for partial-failure resilience
- Degenerate WCS detection and exclusion for coadd templates
- FastAPI real-time monitoring dashboard

### Infrastructure
- `nickel` CLI with 16 commands covering the full pipeline lifecycle
- Profile-based configuration system for multi-target campaigns
- CI with LSST Science Pipelines container, pre-commit, and ruff/black
- Docker images published to GHCR (`stips`, `stips-slurm`, `stips-hpc`)

## [0.0.1] — 2025-06-08

- Initial commit: obs_nickel instrument package (camera geometry, translator, ISR)
- NickelTranslator for FITS header metadata extraction
- Single-CCD detector layout, visit_system ONE_TO_ONE
- Basic test suite for instrument registration and raw ingestion
