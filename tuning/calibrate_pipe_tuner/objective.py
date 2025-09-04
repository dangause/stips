from __future__ import annotations
import optuna
from .bounds import suggest_params
from .runner import run_trial
from .io_utils import now_utc_iso, write_csv_row
from .context import RUNS_CSV_HEADERS
from .context import Context

def make_objective(ctx: Context):
    """Create an Optuna objective function that runs one tuning trial."""
    def objective(trial: optuna.Trial) -> float:
        params = suggest_params(trial)
        tag = f"t{trial.number:03d}"
        try:
            out_coll, score, metrics = run_trial(ctx, params, tag, trial.number)
            trial.set_user_attr("out_coll", out_coll)
            trial.set_user_attr("metrics", metrics)
            trial.set_user_attr("params", params)
            return score
        except Exception as e:
            # Log a fail row (no metrics), then re-raise to let Optuna prune
            write_csv_row(ctx.workdir / "tuning_runs.csv", RUNS_CSV_HEADERS, {
                "time": now_utc_iso(), "trial_index": trial.number, "trial_tag": tag,
                "status": "fail", "out_coll": "",
                "read_from_collection": "", "postproc_out": "",
                "n_total": len(ctx.visits), "n_success": 0, "n_fail": len(ctx.visits), "success_rate": 0.0,
                "psfSigma_med": "", "astromOffsetStd_med": "", "skyNoise_med": "", "magLim_med": "",
                "score_base": "", "score": "",
                **{k: params.get(k, "") for k in [
                    "psf_det.threshold","psf_det.incMult","psfsel.snmin","psfsel.widthStdMax",
                    "match.maxOffsetPix","match.maxRotationDeg","match.matcherIterations",
                    "match.minMatchDistPixels","match.minMatchedPairs","match.minFracMatchedPairs",
                    "match.numBrightStars","match.maxRefObjects","match.numPatternConsensus",
                    "astro_src.snmin","apcorr.snmin","apcorr.sigclip","apcorr.niter","ncf.snmin"
                ]},
                "overrides_path": "", "trial_dir": str(ctx.workdir / "trials" / tag)
            })
            raise optuna.TrialPruned(f"Trial error: {e}")
    return objective
