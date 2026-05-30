# AAS 246 iPoster — STIPS Design Spec

**Author:** Dan Gause (NRAO)
**Meeting:** AAS 246, June 7-11 2026 (upload by 2026-06-08)
**Platform:** iPosterSessions.com (AAS 246 instance)
**Abstract number:** 287
**Status:** Brainstorm-approved design, ready for implementation planning.

---

## 1. Summary

A single-canvas iPoster presenting the **Small Telescope Image Processing Suite (STIPS)** — a package that brings the LSST Science Pipelines to 1-meter class telescopes. The poster pitches STIPS to a "we have small-telescope data, what reduction pipeline should we use" audience: community-oriented motivation up front, credibility evidence in the middle, install/contact at the close.

## 2. Goals

- **Primary takeaway (community pitch, "C"):** Small-telescope users can stop hand-rolling reduction pipelines. STIPS exists, it's open-source, and the LSST Science Pipelines do most of the heavy lifting.
- **Supporting takeaway (credibility, "B"):** STIPS produces LSST-Stack-quality calibration on real Nickel data: <0.1 mag R/I against Landolt standards, reproduces published ZTF lightcurves for SN 2023ixf and SN 2020wnt.
- **Tertiary takeaway (adoption, "A"):** Clear install path, link to repo, contact for collaboration.

## 3. Non-goals

- A complete tutorial. The poster points at the repo for documentation.
- An exhaustive feature list. Workflow breadth is shown via Panel 6's 4-tile showcase, not a feature-by-feature inventory.
- Deep dives into individual scientific results (SN 2023ixf physics, transit detection physics, etc.). The poster is about the *tool*.

## 4. Audience and framing

- Mixed observational/computational astronomy audience at AAS 246.
- "Comp/DS"-style poster session is the natural neighborhood (per the Pyscope/MAESTROeX/Castro precedent).
- Reader is assumed to be familiar with what "calibration" and "DIA" mean but not necessarily with the LSST Science Pipelines internals.

## 5. Format constraints

Per [AAS 245/246 iPoster guidance](https://aas.org/meetings/aas245/presenter-instructions) and [iPoster Editor Quick Guide](https://ipostersessions.com/iposter-quick-guide/):

- Landscape canvas, target aspect ratio 16:9.
- Body text minimum 28 pt; sans-serif (Helvetica/Arial) or Georgia.
- No background images.
- Total file under 25 MB.
- Vertical column flow inside the landscape canvas.

## 6. Layout

**Header band (full width):**
1. Institutional-logo strip — NRAO, Lick, LSST (top of canvas).
2. Title bar — full title + author + affiliation.

**Body (4-column × 2-row grid; merged middle in bottom row):**

| Row | Slot 1 | Slot 2 | Slot 3 | Slot 4 |
|---|---|---|---|---|
| Top | 1. Hook | 2. STIPS Architecture | 3. Landolt Validation | 4. SN vs ZTF |
| Bottom | 5. Portability | 6. Workflows | (Panel 6 cont.) | 7. Get STIPS |

Panel 6 spans columns 2-3 of the bottom row (merged into one wide panel). Total panel count: 7. Color/role key throughout: hook (yellow), architecture (purple), evidence (blue), portability (orange), workflow showcase (pink), CTA (green).

## 7. Panel content specifications

### Panel 1 — Hook (motivation/gap)
- **Headline:** "1-meter telescopes hold decades of archives but lack actively maintained reduction pipelines."
- **Body:** 60-80 words. The niche (long-running archives, accessible scale, used by amateur + professional astronomers), the gap (no LSST-quality pipeline), STIPS as the answer in 1-2 sentences.
- **Visual:** Stylized motivation mini-infographic (matplotlib): a "decades of data / 0 pipelines" representation or similar minimal vector graphic. No telescope photo (none available).
- **Existing assets:** None; new infographic to be drafted.

### Panel 2 — STIPS Architecture (centerpiece)
- **Headline:** "STIPS = LSST Science Pipelines + a thin small-telescope abstraction layer"
- **Body:** ~40 words caption explaining the layered structure.
- **Visual:** Custom block diagram showing: instrument plugins (Nickel, CTIO 0.9m) ↔ STIPS core (CLI, YAML configs, Butler ingestion, multi-instrument abstraction) ↔ LSST Science Pipelines (calibrateImage, DIA, forced photometry, lightcurve extraction). Inputs (raw FITS) on the left edge, outputs (calibrated images, difference images, lightcurves) on the right.
- **Existing assets:** None; vector diagram to be drafted (matplotlib + arrows, exported to SVG/PNG).

### Panel 3 — Landolt Validation
- **Headline:** "R and I bands calibrated to <0.1 mag against Landolt standards"
- **Body:** ~70 words. Method (cross-match `single_visit_star` against Landolt catalog, 76 measurements across 10 stars, B-V −0.19 to +1.74). Headline numbers: R: −0.005 ± 0.062 mag; I: −0.038 ± 0.062 mag; B/V color terms +0.080 and +0.099 mag/(B-V).
- **Visual:** `analysis/landolt_residuals.png` as the primary; `landolt_color_terms.png` as a zoom-in popup if iPosterSessions supports interactive expansions.
- **Existing assets:** Both PNGs in `analysis/`.

### Panel 4 — SN Cross-Validation
- **Headline:** "Reproduces published lightcurves: SN 2023ixf and SN 2020wnt vs ZTF"
- **Body:** ~60 words. 141 R/I points for 2023ixf (early plateau, days 1.4-75.5); 65 for 2020wnt (peak through late decline). Agreement with ZTF r at sub-tenth-mag near peak; Nickel campaign extends past ZTF's coverage of the source.
- **Visual:** `analysis/sn_vs_ztf_comparison.png` (already a side-by-side 2-panel figure).
- **Existing assets:** PNG already in `analysis/`.

### Panel 5 — Portability (multi-instrument + multi-platform)
- **Headline:** "Portable across telescopes and compute environments"
- **Body:** Two stacked sub-sections, ~40 words each.
  - **Multi-instrument:** CTIO 0.9m added in 1 week via the InstrumentPlugin system (Phase 1 + 2 complete, see PR #9). Single ISR validation passed.
  - **Multi-platform:** Same code runs locally, in Docker, or via BPS on a Slurm cluster. Validated end-to-end on a 22-night concurrent test (memory note: "Docker Slurm Test Cluster (VALIDATED 2026-02-27)").
- **Visual:** Two small images stacked: CTIO 0.9m thumbnail (icon or NOIRLab CTIO photo if available under free use) + Docker/Slurm icon-stack.
- **Existing assets:** None; will source CTIO icon and Docker/Slurm logos (free-use).

### Panel 6 — Supported Science Workflows (merged centerpiece, bottom)
- **Headline:** "End-to-end workflows for diverse science cases"
- **Body:** 2×2 grid of mini-tiles inside the panel. Each tile: ~25-word caption + a small thumbnail figure.
  - **Transients (DIA):** SN 2023ixf early-plateau mini-lightcurve.
  - **Exoplanets:** HD 189733 differential aperture photometry transit (from `hd189733_repo`).
  - **Variable stars:** CY Aqr / DY Peg / AC And folded period detection.
  - **Extended objects:** narrowband/Sloan workflow on a Hα target (extended_objects repo).
- **Existing assets:** Source data exists in the per-target butler repos. Thumbnails to be generated as part of implementation.

### Panel 7 — Get STIPS (CTA)
- **Headline:** "Try STIPS"
- **Body:** GitHub URL (post-rename: `github.com/danpgause/stips`), install one-liner (`uv pip install -e .` or `pip install -e .`), QR code linking to repo, contact email/ORCID.
- **Visual:** Large QR code as the visual anchor (~50% of panel area).
- **Existing assets:** None; QR generated at implementation time.

## 8. Repo identity

The package will be re-branded from `nickel_processing_suite` to **STIPS** for poster purposes. Plan:

- **GitHub-side rename only:** rename the `nickel_processing_suite` repo to `stips` via GitHub's Settings → repository name UI. Preserves all commits, branches, tags, PRs, issues, stars. GitHub auto-redirects old clone URLs for ~1 year.
- **Local directory + internal references stay as `nickel_processing_suite`** for this sprint. A future cleanup (out of scope for poster work) can rename the local checkout, `obs-nickel-data-tools` package metadata, env var names, etc.
- **CTA URL on the poster:** `github.com/<owner>/stips` (replace `<owner>` with `danpgause` or the org if moved).

## 9. Assets — existing and to-be-created

### Existing (reuse)
- `analysis/landolt_residuals.png` — Panel 3
- `analysis/landolt_color_terms.png` — Panel 3 popup (if supported)
- `analysis/sn_vs_ztf_comparison.png` — Panel 4
- `docs/calibration_metrics_assessment.md` — reference document for numbers

### To create
- Panel 1 mini-infographic (matplotlib vector graphic)
- Panel 2 architecture diagram (matplotlib block diagram → SVG/PNG)
- Panel 5 Docker/Slurm composite icon
- Panel 5 CTIO 0.9m thumbnail (icon or free-use photo)
- Panel 6 four mini-lightcurve / detection thumbnails (transients, exoplanets, variables, extended objects) — generated from existing butler repos
- Panel 7 QR code linking to the renamed GitHub repo

### Logo assets (find or request)
- NRAO logo (high-res, official)
- Lick Observatory logo
- LSST Discovery Alliance / Rubin Observatory logo

## 10. Open risks

- **STIPS repo rename:** GitHub rename is low risk for the repo itself but breaks any external links (publications, slides, etc.) that already cite the old URL — none expected for an unpublished tool, but worth noting. Local references in env files, configs, README still say `nickel_processing_suite`. They'll work because Python/Butler don't depend on directory name, but it's cosmetically inconsistent post-rename.
- **iPoster Plus features:** The "click to expand" popups assumed for the Landolt color-term zoom-in depend on the AAS 246 iPoster license tier. If the basic tier only supports a static canvas, Panel 3 needs to fit both plots in one cell. Worth confirming on the iPosterSessions side before final layout.
- **CTIO 0.9m integration not yet merged** (PR #9, open since March on the `dev` branch). The poster claims "extended to a second instrument" — if reviewers ask for evidence beyond ISR validation, we don't have full-pipeline CTIO results yet. Worth either landing the PR before June 8 or hedging the panel copy to match what we've actually demonstrated.
- **Panel 6 thumbnails are the largest implementation risk.** Each requires pulling data from a different butler repo and generating a small clean figure. If time runs short, Panel 6 falls back to a text+icon grid with no figures.

## 11. Implementation outline (the plan will detail)

1. Rename GitHub repo (or defer until just before final upload).
2. Draft Panel 2 architecture diagram (highest-stakes asset).
3. Draft Panel 1 motivation infographic.
4. Generate Panel 6 thumbnails from existing repos (one per workflow).
5. Source/finalize logos (NRAO, Lick, LSST) and CTIO icon.
6. Generate Panel 7 QR code.
7. Write final panel copy to the word budgets above.
8. Assemble the canvas in iPosterSessions's editor.
9. Test on the published preview link; iterate on font sizes and figure cropping at the canvas resolution.
10. Final upload by 2026-06-08.

## 12. Timeline

- 2026-05-30 to 2026-06-02: assets (architecture diagram, infographic, thumbnails, logos, QR code).
- 2026-06-03 to 2026-06-05: assemble in iPosterSessions, iterate on copy.
- 2026-06-06 to 2026-06-07: review, polish, repo rename.
- 2026-06-08: upload.

## 13. References

- AAS 245 presenter instructions (formatting baseline): https://aas.org/meetings/aas245/presenter-instructions
- iPoster Editor Quick Guide: https://ipostersessions.com/iposter-quick-guide/
- Pyscope iPoster, AAS 244 (closest analog): https://aas244-aas.ipostersessions.com/?s=A7-C9-50-E4-C6-A2-BF-1D-A0-2D-89-F3-8E-FF-27-00
- iPoster Plus / Radcliffe Wave precedent: https://ipostersessions.com/iposter-plus-and-the-radcliffe-wave-at-aas-235/
- Calibration metrics assessment (numbers source): `docs/calibration_metrics_assessment.md`
