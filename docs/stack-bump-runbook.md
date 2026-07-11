# Stack-bump runbook

A concrete checklist for moving STIPS to a new LSST Science Pipelines version.
It exists because the supported version lives in several places that drift out
of sync (finding **F-025** in [`docs/audit/findings-2026-07-10.md`](audit/findings-2026-07-10.md),
"Version-bump runbook" section).

## Version-truth statement

There are three coordinates, and they are deliberately different:

| Coordinate | Value | Meaning |
| --- | --- | --- |
| **Supported release** | `v30_0_3` | Production. What the Docker images build on and the docs are validated against. |
| **CI pin** | `w_2025_32` | The weekly that every push is validated against in `.github/workflows/ci.yml`. |
| **Canary** | `w_latest` | The scheduled `stack-canary.yml` job that tracks the newest weekly so upcoming breakage surfaces before the pin moves. |

Note: `rubin-env` versions (e.g. `12.1.0`, the conda-environment number) are **not**
stack releases. Do not put a `rubin-env` number in any "supported stack" statement.

## Every pin location (keep these in sync)

When the supported release moves, update **all** of these together:

| File / line | Pin |
| --- | --- |
| `.github/workflows/ci.yml:17` | `image: ghcr.io/lsst/scipipe:al9-w_2025_32` (CI weekly) |
| `docker/Dockerfile:24` | `ARG LSST_TAG=v30_0_3` |
| `docker/Dockerfile.hpc:30` | `ARG LSST_TAG=v30_0_3` |
| `docker/Dockerfile.slurm:12` | `ARG LSST_TAG=v30_0_3` |
| `README.md` (Supported LSST stack blockquote) | release + CI weekly + canary |
| `docs/getting-started.md` (Prerequisites, item 2) | release + CI weekly |

The `stack-canary.yml` default (`al9-w_latest`) is intentionally floating and is
**not** bumped by hand.

Also note: `docker/Dockerfile.slurm` used to hardcode the `rubin-env` conda-env
path (`.../envs/lsst-scipipe-12.1.0/bin`). That is now resolved at build time via
a version-independent `current` symlink, so it is no longer a pin — do not
reintroduce a hardcoded env number there.

## Pre-bump signals

- Watch the **`stack-canary`** workflow (`.github/workflows/stack-canary.yml`,
  scheduled against `al9-w_latest`). A red canary is the early warning that the
  next weekly breaks something before you move the CI pin.
- Skim the LSST release notes for renamed dataset types and config fields. STIPS
  concentrates dataset-type names in
  [`packages/stips/src/stips/core/dataset_types.py`](../packages/stips/src/stips/core/dataset_types.py)
  and asserts them in `packages/stips/tests/test_dataset_types.py`; a rename is a
  single edit there.

## Bump day

1. **Install the new stack side-by-side** (does not touch your current env):

   ```bash
   scripts/utilities/install_stack_version.sh --release <tag>
   # installs into $LSST_STACKS_ROOT/<tag> (or ~/lsst_stacks/<tag>)
   ```

2. **Run the test suite against the new stack**, treating future-deprecation
   warnings as errors so upstream removals surface now rather than later:

   ```bash
   STACK_DIR=<new-stack> tox            # standard suite (tox.ini -> scripts/with-stack.sh)
   # or, to fail on FutureWarnings:
   ./scripts/with-stack.sh -S <new-stack> --setup-testdata -- \
       pytest -q -W error::FutureWarning
   ```

   This includes the **pipeline graph-build test**
   (`instruments/nickel/tests/test_drp_pipeline_config.py`), which loads the
   shipped `DRP.yaml` and calls `Pipeline.fromFile(...).to_graph()` — converting
   config-field breakage from a runtime surprise into a CI failure — and the
   **dataset-type contract test** (`packages/stips/tests/test_dataset_types.py`).

3. **Sanity-check activation:** `stips env` (exercises `check_stack()` in
   `packages/stips/src/stips/core/stack.py`) against the new `STACK_DIR`.

4. **End-to-end smoke on `packages/testdata`.** Run bootstrap → calibs → science
   → dia on one night and assert `diff_image_count > 0` — the single assertion
   that transits every coupling class (ingest, ISR, WCS, coadd/template,
   subtraction, dataset-type names). Use the `stips` CLI stages (or `stips run`)
   pointed at the testdata repo, with the new `STACK_DIR`.

5. **Bump the pins.** Update every row in the table above in one commit, using
   this file as the checklist.

## Post-bump validation

1. `stips provenance sync` (see `packages/stips/src/stips/cli.py`, the
   `provenance sync` subcommand) to refresh `provenance/runs.json`.
2. Re-run one historical night per instrument through the pipeline.
3. Diff the resulting lightcurves against the previously recorded results in
   `provenance/runs.json` — a photometric shift is the signal that a stack change
   altered results, not just interfaces.

## After merge

Confirm the `w_latest` canary is green on the new baseline; if it is already red
on a weekly *newer* than the one you pinned, open a tracking issue so the next
bump starts from a known state.
