# Migration notes

One-time migration notes for changes that affect the contents of *existing*
Butler repositories or existing instrument forks. Newest first.

## 2026-07: QA task-label rename — `...Nickel` → `...Visit` (F-013)

Five analysis/QA task labels in the framework-default pipelines were renamed
from a Nickel-branded suffix to a neutral one. In LSST pipelines, **task labels
become dataset-type names** (`<label>_metadata`, `<label>_log`,
`<label>_config`, and metric-bundle outputs) in every repo that runs them — so
the old names would have been branded into every fork's Butler repo.

| Old label | New label |
|-----------|-----------|
| `analyzeCalibrateImageMetadataNickel` | `analyzeCalibrateImageMetadataVisit` |
| `makeAnalysisSingleVisitStarAstrometricRefMatchNickel` | `makeAnalysisSingleVisitStarAstrometricRefMatchVisit` |
| `analyzeSingleVisitStarAstrometricRefMatchNickel` | `analyzeSingleVisitStarAstrometricRefMatchVisit` |
| `makeAnalysisSingleVisitStarPhotometricRefMatchNickel` | `makeAnalysisSingleVisitStarPhotometricRefMatchVisit` |
| `analyzeSingleVisitStarPhotometricRefMatchNickel` | `analyzeSingleVisitStarPhotometricRefMatchVisit` |

(The `Visit` suffix — not the bare upstream name — is required because DRP.yaml
also imports drp_pipe's `analysis-visit-single-visit.yaml` ingredient, which
defines tasks with the exact base names; the suffix keeps STIPS's variants
distinct in the same graph.)

Files changed: `instrument_defaults/pipelines/DRP.yaml` (subsets
`step1a-single-visit-detectors`, `step1b-single-visit-visits`,
`stage1-single-visit`), `analysis-visit-single-visit.yaml`,
`visit-quality-detector.yaml`.

### What this means for an existing repo

- **No data loss.** Datasets already written under the old label-derived names
  (e.g. `analyzeCalibrateImageMetadataNickel_metadata`,
  `...RefMatchNickel_log`, `...RefMatchNickel_config`) remain in the repo,
  registered and queryable, untouched by the upgrade.
- **Reruns after upgrading write under the NEW names.** A night reprocessed
  with the new pipelines produces `...Visit_*` dataset types alongside any old
  `...Nickel_*` ones from earlier runs. Science outputs are unaffected — the
  renamed tasks are QA/analysis tasks; their *science* connections
  (`single_visit_star_ref_match_astrom`, `calibrateImage_metadata_metrics`,
  etc.) are explicit `connections.*` settings and did not change.
- **Dashboards / queries referencing old metadata dataset names must update**
  to the new names (or query both during the transition), e.g.
  `butler query-datasets ... analyzeCalibrateImageMetadataNickel_metadata` →
  `...MetadataVisit_metadata`.
- No Butler schema or dimension change is involved; there is nothing to
  migrate on disk.
