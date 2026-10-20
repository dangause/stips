# STIPS performance read-through (2026-10-20)

Phase 1 of a performance analysis: a code read of the orchestration layer plus
mining of the 167 existing run logs under `logs/` (2026-02 to 2026-10). No new
pipeline experiments were run; the only measurements taken were ~10 s of
stack-activation micro-timings. Phase 2 (controlled experiments) is planned at
the end.

Machine for all numbers: Apple M3 Max, 14 cores, 36 GiB, local SQLite Butler
registries (~500 MB each for ~1000 exposures).

## 1. Where the time goes today

### 1.1 Fixed per-process costs (micro-timed, warm cache)

| Operation | Wall |
|---|---|
| `bash -c "source loadLSST.bash; setup lsst_distrib; python -c pass"` | 0.6 s (1.3 s cold) |
| same + `import lsst.daf.butler` | 1.4 s (4.1 s cold) |
| `pipetask --help` | 1.8 s |
| `butler --help` (click loads every plugin subcommand) | **6.6 s** |
| `pipetask qgraph` on a small graph, launch to graph built (from logs) | ~10–12 s |
| `pipetask run -g` launch to graph loaded (from logs) | ~4.5 s |

Every `run_with_stack()` call pays the first row; every `run_butler()` (CLI
mutation: `collection-chain`, `certify-calibrations`, `define-visits`,
`ingest-raws`, `register-*`) pays the `butler --help` row; every
`run_butler_python_json()` snippet pays row two plus `Butler.from_config()` on a
500 MB registry.

### 1.2 Stage timings from logs

Reference night: 2023ixf 20230611, 57 science exposures, run `20260224_182933`
(`concurrent_nights: 3`, `jobs: 6`, so three `pipetask -j 6` were sharing 14
cores; the per-quantum worker-time below is therefore an upper bound).

| Stage | Wall | Inside pipetask | Notes |
|---|---|---|---|
| calibs | 241 s | bias 22 quanta / 27 s; flat 188 quanta / 159 s | ingest 222 raws 3.4 s; define-visits 3.5 s over **all 1214 visits** |
| science (one config attempt) | 265 s | 690 quanta for **18 tasks** | isr 3.0 s mean, calibrateImage 11.9 s (success) / 4.0 s (failure) |
| DIA (night 20230618, i) | ~40 s in orchestrator | 25 s; 18 quanta run in 13 s | ~15 s is orchestrator queries |
| fphot (night 20230519, i) | ~17 s in orchestrator | 5 s; 5 quanta | ~70 % overhead |

Per-quantum worker time versus logged in-task time (worker time = wall × jobs / quanta):

| Run | worker-s / quantum | in-task median | implied overhead |
|---|---|---|---|
| cpFlat (188 quanta) | 5.1 s | 1.0 s | ~4 s |
| cpBias (22 quanta) | 7.3 s | 1.7 s | ~5.5 s |
| DIA (18 quanta) | 4.3 s | 1.3 s | ~3 s |

Full-campaign shape (2020wnt, sequential, run `20260223_043201`, 280 min total):

| Step | Count | Wall | Per item |
|---|---|---|---|
| calibs, template nights | 14 | 45 min | 3.2 min (7 science exposures each) |
| calibs, science nights | 29 | 85 min | 2.9 min |
| science, template nights | 14 | 30 min | ~2 min for 7 exposures |
| science, science nights | 29 | 48 min | ~1.6 min for 1–9 exposures |
| DIA | 87 night-bands | 44 min | 30 s (12 s when skipped) |
| fphot | 56 night-bands | 16 min | 17 s |

For these small nights the pipelines are almost entirely fixed overhead: 7
exposures of real ISR + calibrateImage is ~100 CPU-seconds, yet a night costs
~5 minutes across calibs + science.

### 1.3 Fallback cascade frequency

| Run | science invocations | fallback attempts | quanta rescued |
|---|---|---|---|
| 2023ixf `20260223_153335` | 22 | 63 | 4803 |
| 2023ixf `20260224_182933` (partial) | 6 | 10 | 176 |
| 2020wnt `20260223_043201` | 41 | 18 | 44 |

On 2023ixf nearly every night ran all four configs. On 20230611 the primary
`dense_strict` failed 49 of 57 calibrateImage quanta (PsfexTooFewGoodStars,
ObjectSizeNoGoodSources, MeasureApCorr). Each extra attempt re-pays a qgraph
build (~10 s), a pipetask launch, and 4 s per failing exposure. The sequential
2023ixf run spent 903 s on that night versus 265 s for a single attempt.

## 2. Pain points, ranked by expected wall-time win

### P1. One fresh interpreter per quantum (`pipetask -j`)

`lsst.pipe.base.mp_graph_executor` starts a new `multiprocessing.Process` for
every quantum; the start method defaults to `spawn` and `fork` is rejected by
`pipetask run` ("unsafe and no longer supported"). Each child re-imports the
stack (1.4–4 s) and constructs its own Butler before doing ~1 s of work.
Measured: 4–5 s of worker time per quantum against ~1 s of task time (section
1.2). This caps the benefit of `-j` and multiplies with `concurrent_nights`.

Levers (to test in Phase 2): `--start-method forkserver` (available; `pipe_base`
does not preload modules so the gain is uncertain), fewer quanta (P2), and
confirming how much of the gap is CPU contention from `concurrent_nights`.

### P2. 16 of the 18 science tasks are QA / consolidation

`DRP.yaml#stage1-single-visit` runs isr + calibrateImage plus 16
analysis_tools / consolidation tasks. On 20230611: 576 of 690 quanta were QA
and consolidation, consuming ~7 % of in-task time but each paying the P1
startup. Estimated ~40 % of science wall time. Several are global quanta
(`makeAnalysisSingleVisitStarAssociationWholeSkyPlot`, `...MetricTable`,
`associateIsolatedStar` over the tract) that only run after every visit.

Downstream needs are small: DIA reads `preliminary_visit_image` and
`single_visit_star_footprints`; forced phot reads `preliminary_visit_image`;
coadds need `preliminary_visit_summary` (so `consolidateVisitSummary`).

Lever: a `science-core` subset (isr, calibrateImage, standardizeSingleVisitStar,
consolidateVisitSummary) as the default, QA opt-in via `options.science_qa` or
run once per campaign over all nights. Also drop `--long-log --log-level INFO`
for QA tasks or lower their level.

### P3. The calibrateImage fallback cascade

`science._run_config_attempts` runs up to four full qgraph+run cycles per night
per band group, each with `--skip-existing-in` graph builds. Costs: 3× extra
qgraph builds (~30 s), 3× pipetask launches, re-running calibrateImage on every
still-failing exposure (4 s each), and the cascade continues after a fallback
rescues zero quanta (20230611: `sparse_strict` rescued 0, `sparse_relaxed`
still ran).

Levers: choose config order per night from a cheap proxy (exposure count,
`psf_available_star_count` from the first attempt's metadata, or the config
that won on this night last time, which `processing_log` already records);
stop the cascade when a fallback rescues nothing; or fold the retry into the
task so one quantum tries the config list in-process.

### P4. Orchestrator stack launches around every stage

Static count of `run_with_stack`-backed calls per module: calibs 16, crosstalk
10, dia 9, coadd 9, pipeline 8, bootstrap 8, science 7, run 6, refcat 6,
fphot 4. Per night in practice:

- **science**: `latest_raw_run`, `resolve_object_filter`,
  `find_bad_coord_exposures`, `_count_matching_exposures` are four separate
  in-stack processes each running `queryDimensionRecords("exposure")` over the
  same night (~10 s before the first qgraph), then per attempt qgraph + run,
  then `collection_exists` per RUN + `redefine_chain` (butler CLI, 6.6 s).
- **DIA per band**: `resolve_processccd_collections`, `resolve_object_filter`
  (again, per band), `latest_raw_run`, qgraph, `quantum_graph_is_empty` (a
  fresh process just to load the graph), run, `collection_exists`,
  `redefine_chain` (CLI), 2× `count_datasets`: ~10 launches, ~15 s of the 40 s.
- **fphot per band**: `resolve_processccd_collections`, `list_collections`,
  then `has_datasets` **per candidate diff run** (grows with every rerun), run.
- **calibs**: 5 `butler` CLI mutations per night (ingest, define-visits, 2×
  collection-chain, 2× certify) at ~6.6 s floor each, plus 2× `count_datasets`.
- **define-visits** runs over the whole instrument every night ("1214 visits:
  1009 unchanged, 205 new"); cost grows with the repo. `butler define-visits`
  accepts `--collections` to restrict to the night's raw RUN.

Across a 30-night × 3-band campaign this is ~90 DIA and ~90 fphot invocations,
on the order of 45 minutes of pure process startup.

Levers: (a) a persistent in-stack query helper (one Python process per `stips
run`, JSON requests over stdin/stdout) behind the existing `butler_query`
API; (b) one combined per-night snippet returning raw run, processCcd parents,
target names and exposure records; (c) replace CLI mutations with in-stack
Python (`butler.collections.redefine_chain`, `registry.certify`,
`DefineVisitsTask`) to avoid the 6.6 s click startup; (d) memoise per-run
results (object resolution, raw run, processCcd parents) across bands.

### P5. qgraph and run as two processes

Every stage does `pipetask qgraph --save-qgraph` then `pipetask run -g`; the
second launch costs ~4.5 s. `pipetask run -p ... -d ... --save-qgraph` does
both in one process; emptiness can be checked afterwards from the saved graph
or the `--summary` file. Saves ~5 s × (2 calibs + N science attempts + DIA +
coadd) per night.

### P6. Concurrency model

`concurrent_nights` is a thread pool over whole nights; with `jobs: 6` and
`concurrent_nights: 3` the machine runs up to 18 interpreters on 14 cores and
all of them write to one SQLite registry. Logs show no "database is locked"
errors (one log mentions `OperationalError`, not yet examined). The existing
logs cannot separate contention from P1 because the sequential and concurrent
runs of the same night differ in attempt count. This needs the Phase 2 grid.

### P7. Logging volume and double splitting

`logs/` holds 4.8 GB: 2.4 GB of raw step logs plus 2.2 GB of per-exposure
splits. `_maybe_split_log` splits each step log when it finishes, then
`_split_step_logs` at the end of the run re-reads and rewrites every log
again (no "already split" check). `_split_single_log` loads whole files with
`readlines()`. pipetask also stores `_log` and `_metadata` datasets per
quantum (690 quanta → ~1400 extra registry rows and files per night).

### P8. Ingest copies raws; registry size

`ingest-raws --transfer copy` duplicates every raw into the repo (CTIO
4k×4k frames are ~64 MB each). `link`, `symlink` or `direct` avoid the I/O.
Registries reach ~500 MB for ~1000 exposures; worth checking `VACUUM` / WAL
state and whether dataset-type sprawl from the QA tasks dominates.

### P9. BPS path

- `bps/base.yaml` sets `preScript`, `saveExecutionButler` and
  `executionButlerQueryStep`. None of these keys appears anywhere in the
  installed `ctrl_bps`, `ctrl_bps_parsl` or `ctrl_bps_htcondor`, so they are
  ignored. Environment setup actually comes from the submitting shell (local
  site) or Parsl `worker_init` (Slurm); an HTCondor site would get no stack
  setup from this config.
- `BPSExecutor` submits one workflow per stage per night per band. Each
  `bps submit` builds a clustered graph, runs an init job, one `pipetask
  run-qbb` job per quantum (`single_quantum_clustering`, each a fresh
  interpreter, so P1 again plus Parsl dispatch), then a final
  `transfer-from-graph` job, and the executor polls at 5 s backing off to
  60 s. For an 18-quantum DIA graph this is minutes of overhead for 13 s of
  compute. BPS only pays off with one graph spanning many nights and bands,
  which the per-night RUN collections and the fallback cascade currently
  prevent.
- The standalone `bps/pipelines/*.yaml` are stale relative to the
  orchestrator: `science.yaml` points at `ProcessCcd.yaml` (not `DRP.yaml`),
  clusters a `characterizeImage` task that does not exist, and hardcodes
  `Nickel/...` collections and `gaia_dr3`/`panstarrs1_dr2` refcats.
- No `logs/` entry contains a BPS submission; the BPS path has not been
  exercised on this machine's real campaigns.

Lever: a campaign-graph mode for BPS (one qgraph per stage across all nights,
`day_obs IN (...)`, `dimension_clustering` by visit) and dropping the dead
config keys; otherwise treat BPS as an HPC-only path and optimise the local
executor.

### P10. Smaller items

- `_select_diff_collection` probes every historical diff run with a stack
  launch each; a single `query_datasets` over all candidates would do.
- `quantum_graph_is_empty` spends a process to load a graph the qgraph
  command just printed a count for; `pipetask qgraph --summary` or parsing
  the saved file in-venv (it is a zip of JSON/pickle) avoids it.
- `check_stack` runs only on `stips env`; fine.
- `extract_lightcurve.py` does one `butler.get` per visit catalog; fine at
  campaign scale.

## 3. Throughput summary

| Quantity | Value |
|---|---|
| Raw ingest | 222 Nickel frames in 3.4 s (~65 files/s) |
| Science compute floor per exposure | isr 3 s + calibrateImage 12 s ≈ 15 CPU-s |
| Science observed, one attempt, `-j 6` contended | 4.6 s wall / exposure |
| Science observed, full cascade, sequential run | ~16 s wall / exposure (903 s / 57) |
| Small nights (≤ 7 exposures), calibs + science | ~5 min wall for ~100 CPU-s of work |
| DIA / fphot | 13 s / 5 s of compute inside 40 s / 17 s of wall |

## 4. Phase 2 experiment plan

Instrument first, then measure. Zero-risk step: time every `run_with_stack`
call (first three argv tokens, wall, return code) into `pipeline.log` and a
per-run CSV. That alone gives the per-stage overhead budget for everything
below.

1. **Micro-benchmarks**: stack activation; `butler` CLI vs in-stack snippet
   for `collection-chain` and `certify`; `Butler.from_config()` on a 500 MB
   registry; `pipetask qgraph` for `DRP.yaml#stage1-single-visit` vs a core
   subset.
2. **Per-quantum overhead (P1/P2)**: one 57-exposure night, `-j` in
   {1, 2, 4, 6, 8, 12}, `spawn` vs `forkserver`, full stage1 vs
   `science-core`. Record wall, worker-s/quantum, peak RSS.
3. **Fallback cost (P3)**: same night with `use_fallbacks: false`, default
   order, reversed order, and "stop on zero rescue".
4. **Concurrency grid (P6)**: six nights, `concurrent_nights` × `jobs` in
   {1,2,3,4} × {2,4,6}; total wall, SQLite errors, peak RSS, CPU utilisation.
5. **Orchestrator overhead (P4/P5)**: prototype a persistent query process and
   single-process qgraph+run; measure DIA and fphot per night-band before and
   after.
6. **BPS local site (P9)**: same six nights with `execution: bps`, `site:
   local` vs the local executor; then a campaign-graph prototype.

Logs mined for this report: `logs/20260224_182933_4866` (2023ixf, concurrent),
`logs/20260223_153335_34396` (2023ixf, sequential), `logs/20260223_043201_1937`
(2020wnt, sequential), `logs/20260223_220546_81426` (2023ixf DIA/fphot).
