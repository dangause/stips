from __future__ import annotations
import optuna
from .bounds import suggest_params
from .runner import run_trial
from .io_utils import now_utc_iso, write_csv_row
from .context import Context, make_runs_headers

def make_objective(ctx: Context):
    def objective(trial: optuna.Trial) -> float:
        params = suggest_params(trial, ctx.cfg["parameters"])
        tag = f"t{trial.number:03d}"
        try:
            out_coll, score, metrics = run_trial(ctx, params, tag, trial.number)
            trial.set_user_attr("out_coll", out_coll)
            trial.set_user_attr("metrics", metrics)
            trial.set_user_attr("params", params)
            return score
        except Exception as e:
            headers = make_runs_headers(ctx)
            write_csv_row(ctx.workdir / "tuning_runs.csv", headers, {
                "time": now_utc_iso(), "trial_index": trial.number, "trial_tag": tag,
                "status": "fail", "out_coll": "",
                "read_from_collection": "", "postproc_out": "",
                "n_total": len(ctx.visits), "n_success": 0, "n_fail": len(ctx.visits), "success_rate": 0.0,
                **{m["name"]: "" for m in ctx.cfg["metrics"]},
                "score_base": "", "score": "",
                **{k: params.get(k, "") for k in ctx.cfg["parameters"].keys()},
                "overrides_path": "", "trial_dir": str(ctx.workdir / "trials" / tag)
            })
            raise optuna.TrialPruned(f"Trial error: {e}")
    return objective
