# Refcat Validation Runbook: Gaia/PS1 vs MONSTER

Validate the automated Gaia DR3 (astrometry) + PS1 DR2 (photometry) reference
catalogs against the MONSTER baseline **before** flipping the default. Requires
the LSST stack + a night of real Nickel data.

## Background

The Gaia/PS1 path is wired but staged: `refcat.mode` defaults to `monster`, so
nothing changes until you opt in. This runbook confirms the new path produces
equivalent (or better) astrometry/photometry, after which the default can be
flipped (see "Flipping the default" below).

## Prerequisites

- LSST stack set up (`convertReferenceCatalog`, `butler` on PATH).
- A bootstrapped Butler repo with at least one processed 2023ixf r/i night.
- Network access to the Gaia TAP and MAST PS1 services.

## Step 1 — Pre-warm + inspect coverage (optional)

```bash
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml \
  refcat fetch --ra 210.910750 --dec 54.311694 --radius 0.3
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml \
  refcat status --ra 210.910750 --dec 54.311694
```

Expect `gaia_dr3` and `panstarrs1_dr2` to report full trixel coverage.

## Step 2 — Run one night each way

Pick a single r/i night (e.g. 20230519). Run it twice into separate repos (or
re-process), once per mode:

```bash
# MONSTER baseline
stips -c <config-with-refcat.mode=monster> science 20230519 --object 2023ixf \
  --ra 210.910750 --dec 54.311694

# Gaia/PS1
stips -c <config-with-refcat.mode=gaia_ps1> science 20230519 --object 2023ixf \
  --ra 210.910750 --dec 54.311694
```

(Or use `stips run` with the `refcat:` block toggled.)

## Step 3 — Compare metrics

From each run's `visit_summary` / calibration outputs, compare:

| Metric | Source | Acceptance |
|--------|--------|------------|
| Astrometric residual (`astromOffsetMean`) | visit_summary | Gaia ≲ MONSTER (Gaia DR3 positions are the gold standard) |
| Astrometric scatter (`astromOffsetStd`) | visit_summary | comparable or better |
| Photometric zeropoint | calibrateImage logs / photoCalib | within instrument scatter of MONSTER (~few %) |
| N reference matches | astrometry/photometry logs | sufficient (not degenerate; see degenerate-WCS notes) |
| Forced-phot flux sign at SN | forced_phot_diffim | no new systematic negative-flux regression |

Key checks:

- **Color terms applied:** confirm `photoCatName` resolves to the `ps1*`
  colorterm block (B/V from PS1 g−r, R/I from r−i). A zeropoint that is wildly
  off in b/v usually means the color term did not apply.
- **nJy fluxes:** the converted refcat must be in nanojansky (format_version
  ≥ 1). The integration test `test_refcat_integration.py` asserts this when run
  under the stack (`make test`).
- **PM correction:** Gaia positions are propagated to the visit epoch
  automatically (refcat carries `epoch`/`pm_ra`/`pm_dec`). A systematic
  position offset that grows with epoch baseline indicates PM is not applied.

## Step 4 — Decide

If Gaia/PS1 meets the acceptance criteria on the validation night (ideally a
few nights spanning the campaign), proceed to flip the default.

## Flipping the default

After validation:

1. `packages/stips/src/stips/core/run.py`: change `RunConfig.refcat_mode`
   default and the `from_yaml` fallback from `"monster"` to `"gaia_ps1"`; change
   `template_type` default to `"auto"` if desired.
2. Optionally bake Gaia/PS1 into `DRP.yaml` and invert the overlay
   (`refcat_overlay_config` returns an overlay for `monster`, `None` for
   `gaia_ps1`), so MONSTER becomes the opt-in path.
3. Re-run the test suite (`make test`) and one night end to end.

The MONSTER scripts/configs remain available as an opt-in fallback throughout.
