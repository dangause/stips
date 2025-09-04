from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Tuple

from .context import Context, make_runs_headers
from .io_utils import now_utc_iso, run, tail_lines, write_csv_row
from .overrides import write_overrides_from_config
from .pipetask_cmds import build_calibrate_cmd, maybe_run_postproc, log_failure_row
from .butler_utils import read_visit_summaries, extract_metric_values
from .scoring import aggregate, compute_metrics_and_score
from .scoring import penalize_score  # reuse your existing penalty function if in scoring.py

def run_trial(ctx: Context, params: Dict[str, float], tag: str, trial_index: int) -> Tuple[str, float, Dict[str, float]]:
    trial_dir = ctx.workdir / "trials" / tag
    trial_dir.mkdir(parents=True, exist_ok=True)

    ov_path = write_overrides_from_config(
        ctx.workdir, tag, params, ctx.cfg["parameters"], ctx.cfg.get("overrides_prelude", "")
    )

    out_coll = f"Nickel/run/calib_tune/{tag}"

    success_visits: List[int] = []
    failed_visits: List[int] = []

    # Run calibrateImage per-visit
    for v in ctx.visits:
        cmd = build_calibrate_cmd(ctx, ov_path, v, out_coll)
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
        raise RuntimeError("All visits failed in this trial")

    # Optional post-processing
    post_coll = None
    if ctx.run_postproc:
        post_coll = maybe_run_postproc(ctx, out_coll, trial_dir, success_visits)
    read_coll = post_coll if post_coll is not None else out_coll

    # Build metric medians dynamically from config
    rows = read_visit_summaries(read_coll, ctx.repo, success_visits)
    meds: Dict[str, float] = {}
    for m in ctx.cfg["metrics"]:
        vals = extract_metric_values(rows, m["field"])
        meds[m["name"]] = aggregate(vals, m.get("aggregate", "median"))

    score_base, _ = compute_metrics_and_score(meds, ctx.cfg["metrics"])
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

    # Write per-trial JSON
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
        "overrides_path": str(ov_path),
    }, indent=2))

    # Runs CSV (dynamic headers)
    headers = make_runs_headers(ctx)
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
        **{m["name"]: metrics.get(m["name"], "") for m in ctx.cfg["metrics"]},
        "score_base": metrics["score_base"],
        "score": metrics["score"],
        **{k: params.get(k, "") for k in ctx.cfg["parameters"].keys()},
        "overrides_path": str(ov_path),
        "trial_dir": str(trial_dir),
    }
    write_csv_row(ctx.workdir / "tuning_runs.csv", headers, row)

    return out_coll, score, metrics
