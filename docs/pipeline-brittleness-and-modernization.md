# Pipeline / QGraph System: Brittleness Audit & Modernization Strategy

*Deep-dive analysis of the STIPS pipeline orchestration layer — complexity, over-engineering, and
robustness against LSST stack upgrades. Findings are backed by a multi-agent codebase audit and
LSST documentation research; every proposed replacement API was independently fact-checked against
Rubin source and `pipelines.lsst.io`.*

**Installed stack (gating fact):** **v30** — confirmed empirically (the conda env name
`lsst-scipipe-12.1.0` / rubin-env 12.1 is *not* the pipelines release number; importing `Report` /
`SeparablePipelineExecutor` from `lsst.ctrl.mpexec` emits "deprecated since v30, removed after v30"
FutureWarnings, and the canonical home is now `lsst.pipe.base.*`). This matters because the very APIs we
want to adopt were **mid-migration across v27→v28→v29→v30**: on v30 the executors / quantum-report classes
live under `lsst.pipe.base.*` (the `lsst.ctrl.mpexec` paths are deprecated shims that still work but warn).
Re-confirm on the processing host with `python -c "import lsst.daf.butler.version as v; print(v.__version__)"`
if it differs from this dev box.

**Implementation status (branch `feature/butler-query-api-migration`):** ✅ Phase-1 Butler-query migration
done — `stips.core.butler_query` replaced all `parse_butler_query_output`/`butler_query_has_results` call
sites (B5/B6 collection/dataset/existence queries) and the qgraph emptiness check (B2). ✅ B1 done —
`stips.core.quanta_report` replaced the `parse_quanta_summary` regex via `pipetask run --summary` JSON in
`dia.py`/`science.py`. ⏳ In progress: B3/B4 BPS-report parsing (`_parse_bps_report` columns + run_id scrape).
Remaining: `clean.py`, `executor.py:_check_output_collection`, the `run.py` decomposition, and the
`pipetask report --force-v2` provenance option.

---

## TL;DR

Your three worries are all justified, but to different degrees:

| Worry | Verdict | Core issue |
|-------|---------|------------|
| **Brittleness vs stack versions** | **Most serious** | ~6 places parse *human-readable CLI stdout* with regex/column-positions. Rubin explicitly does **not** treat CLI text as a stable API. These fail **silently** (wrong answer), not loudly. |
| **Too many files** | Partly real | The pipeline core is ~12 files (reasonable). The *sprawl* is 3 duplicate ways to read pipeline state and 3 duplicate Butler-access paths — fix the duplication, not the file count. |
| **Over-engineered** | Partly real | `run.py` is a 2095-line god-module with triplicated step bodies; the BPS executor pays heavy impedance-matching cost for a path used by only 3 test YAMLs. The *science fallback cascade* looks over-built but is solving a genuine Butler constraint. |

**The single highest-leverage change:** stop parsing CLI stdout. Replace it with the in-process
**Butler Python query API** + structured **`pipetask report --force-v2`** JSON. Both are the surfaces
Rubin's own CLI uses internally, and both are confirmed public/stable on v28+.

---

## Part 1 — Brittleness map (ranked)

Every item below couples STIPS correctness to the *textual output format* of a stack CLI tool. That
format is presentation-only and has already drifted across releases. Ranked by blast radius, with the
verified replacement.

### B1 — `parse_quanta_summary()` regex over "Executed N quanta successfully…"  🔴 HIGH
- **Where:** `core/pipeline.py:339-385` (regex `r"Executed (\d+) quanta successfully, (\d+) failed and (\d+) remain"`), consumed in `dia.py`, `science.py`, `executor.py`.
- **Why it breaks:** any rewording, pluralization, log-level, or stream change → returns `(0,0)` silently. The code *already* admits distrust: `science.py:571` forces `effective_ok = 1` when the parse returns 0 but exit code is 0. That workaround would **mask a genuine format change as success**.
- **Replace with (verified):** add `--summary <path.json>` to the existing `pipetask run` argv and load it:
  ```python
  # v29: from lsst.ctrl.mpexec import Report, ExecutionStatus
  # v30+: from lsst.pipe.base.quantum_reports import Report, ExecutionStatus  (moved DM-48909, w.2025.31+)
  report = Report.model_validate_json(summary_path.read_text())
  ok   = sum(q.status == ExecutionStatus.SUCCESS for q in report.quantaReports)
  fail = sum(q.status == ExecutionStatus.FAILURE for q in report.quantaReports)
  ```
  ⚠️ Rubin documents the `--summary` JSON structure as *"may not be stable"*, so **keep
  `parse_quanta_summary` as a guarded fallback** rather than deleting it. For a *stable* alternative see B6.

### B2 — `is_empty_qgraph()` string-match "QuantumGraph contains no quanta"  🔴 HIGH
- **Where:** `core/pipeline.py:409-411`, called `dia.py:308`. Sole signal distinguishing "no data this night" from a real build failure.
- **Replace with (verified, stable, drop-in):** load the `.qgraph` STIPS just wrote and check length.
  ```python
  from lsst.pipe.base import QuantumGraph        # top-level public, stable v27→main
  qg = QuantumGraph.loadUri(str(qg_path))
  empty = len(qg) == 0                            # no isEmpty()/numberOfQuanta() exists; len() is the idiom
  ```
  This is the cleanest win in the whole audit: removes a HIGH brittleness item with a 2-line change and
  no version gating. `coadd.py:483` has *no* emptiness check at all — add the same guard there for consistency.

### B3 — `_parse_bps_report()` positional column split  🔴 HIGH
- **Where:** `executor.py:126-162` — finds the `summary` row, `parts[1..7]` by index. Any added/reordered/localized column → `UNKNOWN`/zeros → forced `returncode=1` regardless of real state.
- **Replace with (verified):** `lsst.ctrl.bps.WmsStates` (public, stable enum) + `WmsRunReport`:
  ```python
  from lsst.ctrl.bps import WmsStates                       # top-level, stable
  from lsst.ctrl.bps.report import retrieve_report          # NOTE: submodule, not top-level; v28+
  reports, _ = retrieve_report(wms_service_fqn, run_id=run_id)
  r = reports[0]
  ok   = r.job_state_counts.get(WmsStates.SUCCEEDED, 0)
  fail = r.job_state_counts.get(WmsStates.FAILED, 0)
  failed_run = r.state is not WmsStates.SUCCEEDED
  ```
  ⚠️ Compare by **enum identity**, never numeric value — the integer values changed between v29 and main.
  `retrieve_report` is **not** re-exported at `lsst.ctrl.bps` top level (import from `.report`).

### B4 — BPS `run_id` scraped from stdout (`split(":")`)  🔴 HIGH
- **Where:** `bps.py:330-341`. Worse than a lost ID: presence/absence of `run_id` *switches the entire success-determination strategy* (`executor.py:343` — missing id ⇒ "synchronous Parsl, already done" ⇒ butler-collection probe; present id ⇒ HTCondor poll).
- **Replace with (verified, but unstable internal):** in-process submit returns a workflow object.
  ```python
  from lsst.ctrl.bps.drivers import prepare_driver
  from lsst.ctrl.bps.submit import submit                   # both submodules; NOT top-level
  wms_cfg, wms_wf = prepare_driver(config_file)
  wf = submit(wms_cfg, wms_wf)
  run_id, name = wf.run_id, wf.name
  ```
  These are unstable internal driver APIs — **confine to a single adapter** (see B-strategy below).

### B5 — Butler tabular stdout parsing (`parse_butler_query_output`)  🔴 HIGH (most call sites)
- **Where:** `pipeline.py:290`/`stack.py:307` define it; ~10 consumers in `dia.py` (74,172,256,421,439), `coadd.py` (114,156,194,379), `fphot.py` (67,94,162), `science.py` (270,774), `crosstalk.py`, `clean.py`, `run.py`, `executor.py:187`. Counts datasets / detects collections / checks existence by counting non-header text rows.
- **Replace with (verified, confirmed-public-stable, the recommended surface):**
  ```python
  from lsst.daf.butler import Butler, MissingDatasetTypeError
  butler = Butler.from_config(str(repo), writeable=False)   # one shared read-only handle

  # count / existence — explain=False returns [] instead of raising on empty
  refs = butler.query_datasets("goodSeeingDiff_differenceExp",
                               collections=run, find_first=False, explain=False)
  diff_count = len(refs)                                     # DatasetRef objects, no text

  # collections by glob — empty Sequence on no match, no exception
  names = butler.collections.query("templates/*")
  ```
  - `query_datasets` / `butler.collections.query` / `from_config` are **confirmed public & stable v28+**;
    they are what Rubin's own CLI now calls under the hood.
  - **Caveat:** wrap in `try/except MissingDatasetTypeError` for never-registered types on a fresh repo
    (`explain=False` suppresses the *empty* exception but **not** the missing-type one).
  - **v27 floor:** these don't exist before v28 — on v27 fall back to `butler.registry.queryDatasets`.
    You're on v30, so you're clear; gate it anyway (the `butler_query` snippets already do, for portability).

### B6 — DIA `diff_count==0` cascade needs 3 post-hoc butler queries  🔴 HIGH
- **Where:** `dia.py:371-463` — can't trust exit code *or* quanta summary, so it re-queries collections + 2 dataset types and treats `diff_count==0` as "template didn't overlap".
- **Best replacement (verified, confirmed-public-stable):** the **quantum provenance graph** answers both
  "what succeeded" *and* "were any diffs written" authoritatively, and is Rubin's blessed machine interface.
  Simplest form — call the CLI that writes JSON, load the JSON:
  ```
  pipetask report --force-v2 <repo> <qgraph> --collections <run> --full-output-filename report.json
  ```
  ```python
  # report.json → Summary model:  summary.tasks[label].n_successful / .n_failed / .n_blocked
  #                               summary.datasets["goodSeeingDiff_differenceExp"].n_visible  > 0
  ```
  `n_visible` for the diff dataset type *directly* replaces the diff_count heuristic. In-process the class
  is `lsst.pipe.base.quantum_provenance_graph.QuantumProvenanceGraph` (note: it's a **class** —
  `assemble_quantum_provenance_graph` is an instance method, not a module function — and `to_summary()`
  returns the pydantic `Summary`). `pipetask report` + `--force-v2` is documented and stable v27+/v28+.

### B-minor (still real)
- `science.py:699` regex `r"connection (\S+)"` over an error string to recover a failed dataset connection name.
- `ps1_template.py:127-128` regex `'tract':\s*(\d+)` / `'patch':\s*(\d+)` over butler stdout → use `query_data_ids`.
- `calibs.py:281` discards exit-code semantics (`returncode != 0` ⇒ "partial, certify anyway") with no quanta parse → use B1/B6.
- `bps.py:341` `success = (returncode == 0)` conflates "submission accepted" with "work succeeded".
- `dashboard/collector.py` (lines 246-602) re-parses `summary.txt`/`pipeline.log` with ~15 regexes — see D2.

---

## Part 2 — Over-engineering & complexity

### O1 — `run.py` is a 2095-line god-module  🔴 HIGH
Owns orchestration **+** RUN_ID/log setup **+** regex log re-splitting **+** ~50-field `RunConfig` YAML parsing
**+** executor creation **+** thread dispatch **+** 6 `_run_*_step` orchestrators **+** 3 collection-discovery
helpers **+** 3 *inline* analysis pipelines (period/transit/differential-phot that build pipetask argv directly
instead of delegating to a stage module).
- **Fix:** split into `run/orchestrator.py`, `run/logging.py`, `run/config.py`; move period/transit/diff-phot into
  their own `core/*.py` stage modules matching the `dia.run()` signature.

### O2 — Each `_run_*_step` triplicates its body  🔴 HIGH
`calibs/science/dia/fphot` each implement the same shape **three times**: dry-run loop, `concurrent_nights>1`
branch with an inner `_one()` closure, and an `else` sequential branch that re-inlines the closure
(`run.py:845-1446`).
- **Fix:** always route through `_dispatch_concurrent(max_workers=max(1, concurrent_nights))` (1 worker ==
  sequential, so the sequential path disappears), fold dry-run into the per-item function as an early return,
  and add one shared `_run_per_night_step(name, run_one, nights, skip_predicate)`. **~600 lines → ~150.** Low
  risk, high payoff.

### O3 — Brittle, redundant log re-splitting  🟡 MEDIUM
150+ lines (`run.py:92-260`) regex-parse `--long-log` text to regroup logs per exposure, run **twice**
(`_maybe_split_log` per step + `_split_step_logs` re-walking everything at the end). The regex
`\((\w+):\{([^}]+)\}\)` silently breaks if LSST changes dataId rendering.
- **Fix:** pass a per-exposure `--log-file` at pipetask-invocation time (LSST writes the split for you), or drop
  per-exposure splitting and grep the combined log. Removes 4 functions and a format dependency.

### O4 — BPS executor impedance-matching  🟡 MEDIUM (decision-gated)
`BPSExecutor` re-parses the argv the stage module just built (`_parse_pipetask_args`, a positional parser that
doesn't handle `--flag=value`), then **fabricates a fake `CompletedProcess`** whose stdout is a hand-formatted
"Executed N quanta…" string *purely so the caller's regex re-matches it* — and the fabricated string
(`"failed out of total"`) doesn't even match the real regex (`"failed and N remain"`). Used by only 3 test/hpc YAMLs.
- **Fix (pick one based on whether HPC is a committed target):**
  - **Not near-term:** delete `BPSExecutor` + the Protocol; `LocalExecutor` is a pure passthrough today. Call `stack.run_pipetask` directly.
  - **Real target:** have `executor.run_pipetask` return a **typed `RunOutcome(returncode, ok, fail)`** so neither
    side string-formats/re-parses; route `site=="local"` to `SeparablePipelineExecutor.run_pipeline(qg, num_proc=jobs)`
    (no submit/poll/report round-trip) and reserve the `ctrl_bps` adapter for true batch sites.

### O5 — Leaky abstraction: `needs_datastore_records` checked in 5 stage modules  🟡 MEDIUM
Defeats the point of the executor abstraction — `if executor.needs_datastore_records:
qgraph_args.append("--qgraph-datastore-records")` is duplicated in `dia.py`, `science.py` (×2), `calibs.py`,
`crosstalk.py`.
- **Fix:** move the qgraph-flag augmentation *into* `executor.run_pipetask` (it already parses argv); stage
  modules pass plain args.

### O6 — Smaller items
- `_get_bands_for_night()` (`run.py:634`) is `return list(run_cfg.bands)` ignoring its `night` arg — vestigial, threaded through 22 call sites. Delete.
- `RunConfig` conflates supernova + variable-star + transit + BPS fields (~50) with mode-defaulting branches. Group into nested dataclasses.
- **Science fallback cascade** (`science.py:443-760`) is intricate but **mostly intrinsic** — the separate-RUN-per-config design is *forced* by Butler's per-RUN config-consistency rule (documented in CLAUDE.md). Don't "simplify" the collection split. The fragile part is the bespoke success accounting (`effective_ok = quanta_ok if quanta_ok>0 else 1`, substring error classification) — extract a typed per-attempt result and **unit-test the math**.

---

## Part 3 — File sprawl / duplication

The pipeline core (~12 files) is reasonably sized. The real problem is **three duplicate subsystems**:

### D1 — Three Butler-access paths  🔴 HIGH
`core/stack.py` (`run_with_stack`, canonical), `eda/butler_inspect.py` (in-stack explorer), and the dashboard
(`dashboard/butler_query.py` / `catalog_query.py` build Python *as strings* and run `python3 -c`). The dashboard
**doesn't import `core.stack` at all** — a second, fragile Butler contract.
- **Fix:** the Tier-1 in-process Butler helper (B5) becomes the single seam; point the dashboard at it. Removes two files of embedded-script glue.

### D2 — Three pipeline-status models  🔴 HIGH
`processing_log.py` persists structured JSON; `provenance.py` aggregates it into `runs.json` + `RUNS.md`
(*"source of truth"*); the dashboard **ignores both** and regex-scans `summary.txt`/`pipeline.log`
(`collector.py` + `analysis.py`).
- **Fix:** dashboard consumes `provenance/runs.json`. Deletes ~15 regexes and a whole class of "log line changed → dashboard wrong" bugs.

### D3 — `core/X.py` ↔ `pipeline_tools/extract_X.py` 1:1 wrappers  🟡 MEDIUM
`lightcurve`, `calib_metrics`, `landolt` each exist as a thin `core/*.py` wrapper around a matching
`pipeline_tools/extract_*.py`. Defensible split (orchestration vs in-stack), but triples file count and
duplicates plumbing. One generic "run a pipeline_tools script in the stack, parse its CSV" helper collapses them.

### D4 — Analysis modules misfiled under `core/`  🟡 MEDIUM
`period.py` (478 lines, Lomb-Scargle) and `transit.py` (611 lines, BLS) just read CSV output and are unrelated to
DIA — yet sit in `core/` making it look far larger/entangled than it is. Move to an `analysis/` subpackage
(~1700 lines out of `core/`).

---

## Part 4 — Recommended strategy & sequencing

The unifying principle, confirmed by the stability research: **the CLI (butler/pipetask/bps stdout) is a Click
app under active restructuring and carries no stability guarantee. The Python objects and the structured
report files (JSON) are the supported machine interfaces.** Rank of durability for what to build on:

1. **Butler Python query API** — most stable; what the CLI itself uses.
2. **`ctrl_mpexec` executors** (`SeparablePipelineExecutor`) — public, sanctioned, but lower-level & mid-relocation to `pipe_base` (v30).
3. **`QuantumGraph` API** — public but low-level, churning with the `PipelineGraph`/`TaskDef` transition.
4. **`ctrl_bps` API** — most environment/version-sensitive; treat purely as a submission backend, never couple correctness to it.

### Phase 1 — Kill the silent-failure brittleness (high value, low risk)
- **`core/butler_query.py`** (new): one read-only `Butler.from_config` handle + typed helpers (`count_datasets`,
  `collection_exists`, `has_datasets`, `list_collections`). Replace all `parse_butler_query_output` /
  `butler_query_has_results` call sites (B5). Delete the subprocess+regex path for *reads*.
- **`is_empty_qgraph` → `QuantumGraph.loadUri` + `len()==0`** (B2). Trivial, no version gate.
- **`pipetask run --summary` JSON** (B1) for quanta counts, *keeping* the regex as a guarded fallback; and/or
  **`pipetask report --force-v2`** (B6) for authoritative per-task + per-dataset outcomes that also subsume the
  DIA `diff_count==0` cascade.

### Phase 2 — Consolidate the duplicate subsystems
- Dashboard → `provenance/runs.json` (D2) and → the Phase-1 Butler helper (D1).
- Collapse the `core/X.py`↔`extract_X.py` wrappers (D3); move `period`/`transit` to `analysis/` (D4).

### Phase 3 — Decompose the orchestrator
- Split `run.py` (O1); unify the triplicated step bodies (O2); fix the log-splitting (O3); delete `_get_bands_for_night` (O6); de-leak the executor (O5).

### Phase 4 — Decide the execution backend (gated on whether HPC is real)
- If not: delete `BPSExecutor` (O4).
- If yes: typed `RunOutcome`, `SeparablePipelineExecutor` for local, `ctrl_bps` Python adapter (B3/B4) for batch.

### Cross-cutting — make the stack boundary version-aware
Because the APIs themselves migrate between releases, **confine every `import lsst.*` to thin adapter modules**
(`butler_query.py`, a `quanta_report.py`, a `bps_adapter.py`) that branch on the detected stack version. Then:
- **Add a CI smoke test** that runs STIPS against the pinned weekly with **`-W error::FutureWarning`**, so
  deprecations surface as actionable failures instead of silent regex misses. (Today, CLI-scraping *hides*
  deprecation warnings — they go to stderr, unparsed.)
- **Pin the stack per campaign** and read each module's `CHANGES.rst` (`daf_butler`, `pipe_base`,
  `ctrl_mpexec`) before bumping. Rubin's policy: removals land no earlier than the next major release **or**
  8 weeks after a deprecation notice (whichever is longer) — a real but workable window.

---

## Appendix — Version-gating cheat-sheet (v27–v29 vs v30 — **your stack is v30**)

On the installed v30 stack, prefer the **v30+ column** (right). The v27–v29 column is kept for the processing
host / other deployments; on v30 those `lsst.ctrl.mpexec` paths still import but emit removal-after-v30 warnings.

| API | v27–v29 import | v30+ import (**your stack**) | Stability |
|-----|------------------------|-------------|-----------|
| `Butler.query_datasets`, `butler.collections.query`, `Butler.from_config` | `lsst.daf.butler` | same | ✅ stable v28+ (absent v27) |
| `QuantumGraph.loadUri`, `len(qg)`, `get_task_quanta(label)` | `lsst.pipe.base` | same | ✅ stable (TaskDef accessors churning) |
| `AllDimensionsQuantumGraphBuilder` | `lsst.pipe.base.all_dimensions_quantum_graph_builder` (submodule — intentionally not top-level) | same | ✅ stable v27+ (`data_id_tables` kwarg is v29.1+ only) |
| `SeparablePipelineExecutor` | `lsst.ctrl.mpexec` | `lsst.pipe.base.separable_pipeline_executor` | ⚠️ public, mid-rename (ctrl_mpexec shim removed after v30) |
| `Report`/`ExecutionStatus` (`--summary` JSON) | `lsst.ctrl.mpexec` | `lsst.pipe.base.quantum_reports` (moved w.2025.31/DM-48909) | ⚠️ JSON structure "may not be stable" — keep fallback |
| `QuantumProvenanceGraph` / `pipetask report --force-v2` | `lsst.pipe.base.quantum_provenance_graph` (class, not free fn) | same | ✅ stable; v2/JSON is the forward path |
| `WmsStates`, `WmsRunReport` | `lsst.ctrl.bps` (top-level) | same | ✅ enum stable — **compare by identity, never numeric value** |
| `retrieve_report`, `submit`, `prepare_driver` | `lsst.ctrl.bps.report` / `.submit` / `.drivers` (submodules) | same | ⚠️ internal, no stability promise — isolate in one adapter |

*Fact-check note: a research pass proposed several of these as top-level imports (`lsst.ctrl.bps.submit`,
`lsst.ctrl.bps.retrieve_report`) and one fabricated symbol (`lsst.utils.deprecate_for_removal`). Verification
caught them; the table above reflects the **corrected** import paths. Confirm against the processing host before
implementing.*
