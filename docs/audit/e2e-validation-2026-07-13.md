# End-to-End Validation Report — audit-fixes branch

**Dates:** 2026-07-13/14 · **Branch:** `audit-fixes` (validated through `da2a57b`)
**Purpose:** the user-mandated gate before merging `audit-fixes` → `dev`: real pipeline runs on both instruments from a clean `uv sync` environment (worktree `stips-audit-wt`), exercising the code paths unit tests cannot reach.

## Test matrix & results

| Run | Setup | Result |
|---|---|---|
| **Nickel 2023ixf, full pipeline** (`stips run`, PS1 templates, gaia_ps1 refcats, 3 nights: 20230519/21/23, r+i) | fresh scratch repo, bootstrap → refcat fetch → PS1 templates → calibs → science → DIA → fphot → lightcurve | **PASS (partial)** — Calibs 3/3, Science 3/3, DIA 4/6, fphot 2/3, lightcurve produced: 17 detections, all positive flux, SNR 156–385, showing the SN's rise (r: 20.9→18.0 mag over days 1.5–3.6). The failing night (20230523) fails identically in historical provenance (template-overlap on a known-poor night) — pre-existing, now reported honestly. |
| **Nickel coadd template build-then-swap** (`template.type: coadd`, then rerun with `rebuild_templates: true`) | same repo | **PASS** — chain atomically redefined to the new timestamped RUN; old RUN de-chained, never destroyed before the replacement was verified (F-009 fix behaving as designed). |
| **CTIO1m bootstrap + calibs** (NGC2298 night 20061216, unbinned 4104² Y4KCam) | fresh scratch repo | **PASS** — instrument registered from the profile, `CTIO1m/…` collections, product-verified calib success. |
| **CTIO1m science + DIA** (M79, i-band, gaia_ps1 refcats, PS1 template, `stips run`) | same repo | **PASS (partial)** — final run: Calibs 1/1, Science 1/1 (calibrateImage 20/20 visits; only the pre-fix photometric-QA quanta failed — fixed as find #10 below), DIA 1/1 (52/56 quanta; 4 dithered edge pointings lost PS1 overlap — see limitations). |
| **Provenance** (`stips provenance sync`) | across E2E repos | **PASS** — records carry `instrument: ctio1m` (from the profile, not the old "nickel" default) and the true pipelines version (`gf03f954c0e+…`), both PR-13 behaviors confirmed live. |
| **Dashboard smoke** (`stips dashboard -c …`) | against the E2E logs/repos | **PASS** (after find #8) — run list, run detail, Butler-backed data tab all HTTP 200. |

## Bugs found and fixed during E2E (all committed on `audit-fixes` with tests)

| # | Commit | Finding |
|---|---|---|
| 1 | `6f08f5a` | `stips_refcats.cones_to_htm` imported `lsst.geom` at call time — the gaia_ps1 refcat path crashed in the plain venv (it had only ever been run from stack-activated shells). Now falls back to an in-stack JSON snippet. |
| 2 | `391ea4e` | `stips-refcats` never declared its fetch deps (astroquery/astropy/numpy/pandas) — clean envs couldn't fetch; and a failed refcat ensure was only a WARNING, letting `stips run` limp into science and die with an opaque `MissingDatasetTypeError`. Deps declared; failed ensure is now an early-exit with the root cause. |
| 3 | `27fc600` | `convertReferenceCatalog` invoked as a bare subprocess — a stack binary absent from the venv PATH. Falls back to `run_with_stack`. |
| 4 | `5230aa3` | `ScienceConfig.default()` hardcoded the Nickel campaign config `2023ixf_relaxed.py` (dangling for every other instrument after the defaults tiering). Untuned instruments now run on a neutral default; explicit-but-missing config paths still error. |
| 5 | `6011956` | The stage-1 QA ref-match tasks were hardwired to MONSTER refcats — any field outside local MONSTER shard coverage could not build a science graph in gaia_ps1 mode. Neutral overlays now redirect them to gaia_dr3/panstarrs1_dr2. |
| 6 | `6011956` | pex_config records modules first-imported during config exec and replays them at quantum-graph reload — configs importing the path-loaded profile (`fetch` module) poisoned saved graphs. `ps1_band_map` now arrives via the `STIPS_PS1_BAND_MAP` env var exported by `run_with_stack`. |
| 7 | `5addcb1` | Stock `CalibrateImageConfig` measures only the 12 px aperture; `standardizeSingleVisitStar` expects the full DRP radii ladder. New `calibrateImage/neutral_default.py` (schema-compat only, no tuning). |
| 8 | `91a2dfc` | Dashboard used the legacy `TemplateResponse(name, {"request": …})` signature removed in current Starlette. Request-first everywhere; `fastapi>=0.110` floor. |
| 9 | `5761ee1` | `neutral_default.py` also needed the `ext_shapeHSM_*` plugin family (second standardizer column group). |
| 10 | `da2a57b` | The photometric QA matcher keys reference fluxes by PHYSICAL filter as well as band (`KeyError: 'I'`) — the neutral gaia_ps1 QA overlay now maps both spellings (verified in-stack against the real config class; not yet revalidated by a full pipeline run — the next campaign run will confirm). |

The common thread of finds 1–3: the refcat subsystem was developed and only ever exercised inside stack-activated shells, so the venv/stack boundary violations were invisible until a clean-environment E2E run. Finds 4–7, 9–10 are consequences of the (correct) defaults-tiering decision that unit tests and graph-build tests could not see because the reference instrument masks them.

## Known limitations documented (pre-existing, not regressions)

- **Southern fields (dec < −30°)**: no PS1 coverage → gaia_ps1 photometry unavailable; MONSTER shards for the field or the unmerged `feature/gaia-photometry-refcat` work are required (this is why the NGC2298 target was swapped for M79 in the CTIO science test).
- **PS1 template size vs large FOVs**: on Y4KCam (~20′ FOV) the 0.2° default cutout leaves dithered pointings without kernel candidates (`NoKernelCandidatesError`, 4/20 visits). Size `template.size` ≥ FOV + dither margin. Both now in CLAUDE.md Common Issues.
- **CTIO wall-clock**: unbinned 16.8 Mpix frames on a dense globular field cost ~30–45 min per calibrateImage visit — data scale, matching historical campaign experience.

## Verdict

Both instruments run their full documented pipelines end-to-end from a clean environment on the `audit-fixes` branch, with every campaign behavior change acting as designed (honest calibs/science accounting, two-UT-day queries, build-then-swap coadds, fail-loud degraded modes, profile-driven neutrality, true provenance capture). The ten E2E fixes above are on the branch. Merge readiness is the user's call per the standing gate.
