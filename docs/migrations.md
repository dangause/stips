# Migration notes

One-time migration notes for changes that affect the contents of *existing*
Butler repositories or existing instrument forks. Newest first.

## 2026-10: Instrument identity is the directory name (#59)

Every instrument now registers under its **own** Butler class path,
`instruments.<name>.instrument.Instrument`, instead of the shared
`lsst.obs.stips.active.Instrument`. The stored `class_name` identifies the
instrument on its own; `INSTRUMENT_DIR` no longer carries identity into the
stack, and several instruments can share one repo.

**Existing repositories migrate themselves.** The next `calibs`, `science`,
`dia`, `coadd` or `measure-crosstalk` step (or `stips bootstrap`) finds the
legacy `class_name` and rewrites the instrument record with `butler
register-instrument --update`; it logs one warning. `fphot`, `lightcurve`,
`ps1-template` and `clean` do not migrate a repo, but keep working unchanged
through the `lsst.obs.stips.active` shim. To do it by hand:

    butler register-instrument --update <REPO> instruments.<name>.instrument.Instrument

Run that in a stack shell with `setup -r packages/obs_stips obs_stips` and
`PYTHONPATH=<root>:<root>/packages/stips/src` set (the nameplate needs
`<root>`; `lsst.obs.stips.binding` imports `stips.profile`) — or just run
`stips bootstrap`, which does this for you.

`lsst.obs.stips.active` remains as a shim (it resolves `INSTRUMENT_DIR` and
re-exports the same classes) so raws ingested before this change, whose
datastore records name `lsst.obs.stips.active.RawFormatter`, stay readable.
Those legacy raws bind to whatever `INSTRUMENT_DIR` the reading process has, so
a hand-typed `butler` with no `INSTRUMENT_DIR` set cannot read them; only repos
that still hold raws (Docker/HPC) are affected.

**Instrument forks must:**

- add `instruments/<x>/instrument.py` (copy it from `instruments/nickel/`; it
  is three lines and identical for every instrument);
- import co-located modules relatively (`from .fetch import fetch_data`);
- delete `instrument_class=` from `profile.py` (the field is gone; it is
  derived from the directory name);
- live at `<root>/instruments/<x>/`. `stips` puts the configured instrument's
  root on `PYTHONPATH` automatically, in-tree or not; add `<root>` yourself
  only for stack commands run outside `stips`, or when a shared repo also
  holds an instrument from another root.

**`CCD_BINNING` is removed.** Binning is the profile field `ccd_binning`
(plus `binning_header`, the FITS keyword the translator checks). A config that
still sets `CCD_BINNING` fails with a message. Binned data of a camera that
is also used unbinned is its own instrument dir: see
`instruments/ctio1m_bin2/` (a `dataclasses.replace` of the base profile with a
new `name` and `ccd_binning=2`).

**`STIPS_PS1_BAND_MAP` is removed.** The in-stack refcat overlays import the
profile by name instead.

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
