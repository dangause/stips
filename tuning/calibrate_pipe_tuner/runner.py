from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Tuple

from .context import Context, RUNS_CSV_HEADERS
from .io_utils import now_utc_iso, run, tail_lines, write_csv_row
from .overrides import write_overrides
from .pipetask_cmds import build_calibrate_cmd, maybe_run_postproc, log_failure_row
from .butler_utils import read_visit_summaries, median_from_rows
from .scoring import compute_base_score, penalize_score

def run_trial(ctx: Context, params: Dict[str, float], tag: str, trial_index: int) -> Tuple[str, float, Dict[str, float]]:
    """Execute one parameter trial across all visits, compute metrics, score, and log artifacts."""
    trial_dir = ctx.workdir / "trials" / tag
    trial_dir.mkdir(parents=True, exist_ok=True)
    overrides = write_overrides(ctx.workdir, tag, params)

    out_coll = f"Nickel/run/calib_tune/{tag}"

    success_visits: List[int] = []
    failed_visits: List[int] = []

    # Run calibrateImage per-visit
    for v in ctx.visits:
        cmd = build_calibrate_cmd(ctx, overrides, v, out_coll)
        stdout_log = trial_dir / f"v{v}_stdout.log"
        stderr_log = trial_dir / f"v{v}_stderr.log"
        try:
            cp = run(cmd, check=True, stdout_log=stdout_log, stderr_log=stderr_log)
            if ctx.echo_logs:
                print(f"\n--- pipetask calibrateImage v{v} (rc={cp.returncode}) tail ---")
                if cp.stdout:
                    print(tail_lines(cp.stdout, ctx.tail))
                if cp.stderr:
                    print("\n--- STDERR tail ---")
                    print(tail_lines(cp.stderr, ctx.tail))
            success_visits.append(v)
        except Exception as e:
            log_failure_row(ctx.workdir, f"{tag}-v{v}", e, cmd, stdout_log, stderr_log)
            failed_visits.append(v)

    n_total = len(ctx.visits)
    n_success = len(success_visits)
    if n_success == 0:
        # Let the objective mark this trial as pruned/fail.
        raise RuntimeError("All visits failed in this trial")

    # Optional post-processing (visitSummary production)
    post_coll = None
    if ctx.run_postproc:
        post_coll = maybe_run_postproc(ctx, out_coll, trial_dir, success_visits)

    read_coll = post_coll if post_coll is not None else out_coll

    # Read visitSummary medians (successful visits only)
    rows = read_visit_summaries(read_coll, ctx.repo, success_visits)
    meds = {
        "psfSigma_med":        median_from_rows(rows, "psfSigma"),
        "astromOffsetStd_med": median_from_rows(rows, "astromOffsetStd"),
        "skyNoise_med":        median_from_rows(rows, "skyNoise"),
        "magLim_med":          median_from_rows(rows, "magLim"),
    }

    score_base = compute_base_score(meds)
    score = penalize_score(score_base, n_success, n_total, ctx.fail_policy, ctx.fail_weight)

    metrics = {
        "n_total": n_total,
        "n_success": n_success,
        "n_fail": n_total - n_success,
        "success_rate": n_success / n_total if n_total > 0 else 0.0,
        **meds,
        "score_base": score_base,
        "score": score,
    }

    # Per-trial JSON
    (trial_dir / "metrics.json").write_text(json.dumps({
        "time": now_utc_iso(),
        "trial_index": trial_index,
        "trial_tag": tag,
        "out_coll": out_coll,
        "read_from_collection": read_coll,
        "postproc_out": post_coll,
        "params": params,
        "metrics": metrics,
        "success_visits": success_visits,
        "failed_visits": failed_visits,
        "overrides_path": str(overrides),
    }, indent=2))

    # Append a row to global runs table
    row = {
        "time": now_utc_iso(),
        "trial_index": trial_index,
        "trial_tag": tag,
        "status": "ok" if n_success == n_total else ("partial" if n_success > 0 else "fail"),
        "out_coll": out_coll,
        "read_from_collection": read_coll,
        "postproc_out": post_coll or "",
        "n_total": n_total,
        "n_success": n_success,
        "n_fail": n_total - n_success,
        "success_rate": metrics["success_rate"],
        "psfSigma_med": metrics["psfSigma_med"] if metrics["psfSigma_med"] is not None else "",
        "astromOffsetStd_med": metrics["astromOffsetStd_med"] if metrics["astromOffsetStd_med"] is not None else "",
        "skyNoise_med": metrics["skyNoise_med"] if metrics["skyNoise_med"] is not None else "",
        "magLim_med": metrics["magLim_med"] if metrics["magLim_med"] is not None else "",
        "score_base": metrics["score_base"],
        "score": metrics["score"],
        # params
        **{k: params.get(k, "") for k in [
            "psf_det.threshold","psf_det.incMult",
            "psfsel.snmin","psfsel.widthStdMax",
            "match.maxOffsetPix","match.maxRotationDeg","match.matcherIterations",
            "match.minMatchDistPixels","match.minMatchedPairs","match.minFracMatchedPairs",
            "match.numBrightStars","match.maxRefObjects","match.numPatternConsensus",
            "astro_src.snmin",
            "apcorr.snmin","apcorr.sigclip","apcorr.niter",
            "ncf.snmin"
        ]},
        "overrides_path": str((ctx.workdir / "trials" / tag / f"calib_overrides_{tag}.py")),
        "trial_dir": str(trial_dir),
    }
    write_csv_row(ctx.workdir / "tuning_runs.csv", RUNS_CSV_HEADERS, row)

    return out_coll, score, metrics
