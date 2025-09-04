#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Nickel calibrateImage tuner (trial-wise overrides + failure-penalized scoring)
- Runs calibrateImage per-visit with per-trial overrides
- Reads visitSummary from the trial's output collection
- Computes metrics on successful visits only
- Penalizes score if any visit fails (configurable)
- Persists a unified history table (CSV) with params, metrics, and log paths
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Any

import optuna

# ----------------------------
# Utility dataclasses & helpers
# ----------------------------

@dataclass
class Context:
    repo: Path
    obs_nickel: Path
    proc_pipe: Path
    post_pipe: Path  # kept for reference (we read visitSummary directly)
    workdir: Path
    visits: List[int]
    bad: List[int]
    jobs: int
    inputs_postisr: str  # e.g., "Nickel/run/processCcd/2025..."
    calib_chain: str     # e.g., "Nickel/calib/current"
    refcats: str         # usually "refcats"
    fail_policy: str
    fail_weight: float

# CSV schemas
FAIL_LOG_HEADERS = ["time", "trial_tag", "exception", "message", "returncode", "cmd", "stdout_log", "stderr_log"]
RUNS_CSV_HEADERS = [
    # trial identity
    "time", "trial_index", "trial_tag", "status", "out_coll",
    # visits accounting
    "n_total", "n_success", "n_fail", "success_rate",
    # metrics
    "psfSigma_med", "astromOffsetStd_med", "skyNoise_med", "magLim_med",
    "score_base", "score",
    # parameters (flattened)
    "psf_det.threshold", "psf_det.incMult",
    "psfsel.snmin", "psfsel.widthStdMax",
    "match.maxOffsetPix", "match.maxRotationDeg", "match.matcherIterations",
    "match.minMatchDistPixels", "match.minMatchedPairs", "match.minFracMatchedPairs",
    "match.numBrightStars", "match.maxRefObjects", "match.numPatternConsensus",
    "astro_src.snmin",
    "apcorr.snmin", "apcorr.sigclip", "apcorr.niter",
    "ncf.snmin",
    # artifact paths
    "overrides_path", "trial_dir"
]

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

def run(cmd: List[str], check: bool, stdout_log: Path | None = None, stderr_log: Path | None = None) -> subprocess.CompletedProcess:
    """Run a subprocess, tee stdout/stderr into files (if provided), and return CompletedProcess."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    if stdout_log:
        ensure_parent(stdout_log)
        stdout_log.write_text(out or "")
    if stderr_log:
        ensure_parent(stderr_log)
        stderr_log.write_text(err or "")
    if check and proc.returncode != 0:
        ex = subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
        raise ex
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)

def write_csv_row(csv_path: Path, headers: List[str], row: Dict[str, Any]) -> None:
    ensure_parent(csv_path)
    new_file = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if new_file:
            w.writeheader()
        # ensure all keys present
        safe = {h: row.get(h, "") for h in headers}
        w.writerow(safe)

def log_failure(ctx: Context, tag: str, exc: BaseException, cmd: List[str],
                stdout_log: Path | None, stderr_log: Path | None) -> None:
    row = {
        "time": now_utc_iso(),
        "trial_tag": tag,
        "exception": exc.__class__.__name__,
        "message": str(exc),
        "returncode": getattr(exc, "returncode", ""),
        "cmd": " ".join(cmd),
        "stdout_log": str(stdout_log) if stdout_log else "",
        "stderr_log": str(stderr_log) if stderr_log else "",
    }
    write_csv_row(ctx.workdir / "trial_failures.csv", FAIL_LOG_HEADERS, row)

def latest_run_name(butler, prefix: str) -> str | None:
    names = [str(rec) for rec in butler.registry.queryCollections() if str(rec).startswith(prefix)]
    return sorted(names)[-1] if names else None

# ---------------------------------------
# Trial parameter handling & overrides I/O
# ---------------------------------------

PARAM_BOUNDS = {
    # PSF detection
    "psf_det.threshold": (3.0, 8.0),
    "psf_det.incMult":   (1.0, 6.5),

    # PSF star selector (objectSize)
    "psfsel.snmin":      (8.0, 30.0),
    "psfsel.widthStdMax":(0.30, 0.45),

    # Astrometry matcher (pessimisticB)
    "match.maxOffsetPix":        (80, 300),
    "match.maxRotationDeg":      (0.5, 3.0),
    "match.matcherIterations":   (6, 12),
    "match.minMatchDistPixels":  (1.0, 3.0),
    "match.minMatchedPairs":     (8, 25),
    "match.minFracMatchedPairs": (0.02, 0.08),
    "match.numBrightStars":      (150, 300),
    "match.maxRefObjects":       (4000, 6500),
    "match.numPatternConsensus": (2, 3),

    # Astrometry source S/N
    "astro_src.snmin": (8.0, 25.0),

    # ApCorr (science selector + clipping)
    "apcorr.snmin":   (25.0, 45.0),
    "apcorr.sigclip": (3.0, 5.0),
    "apcorr.niter":   (3, 6),

    # PSF Normalized Calibration Flux (N.C.F.) selector S/N
    "ncf.snmin": (15.0, 30.0),
}

def suggest_params(trial: optuna.Trial) -> Dict[str, Any]:
    p = {}
    p["psf_det.threshold"] = trial.suggest_float("psf_det.threshold", *PARAM_BOUNDS["psf_det.threshold"])
    p["psf_det.incMult"]   = trial.suggest_float("psf_det.incMult",   *PARAM_BOUNDS["psf_det.incMult"])
    p["psfsel.snmin"]      = trial.suggest_float("psfsel.snmin",      *PARAM_BOUNDS["psfsel.snmin"])
    p["psfsel.widthStdMax"]= trial.suggest_float("psfsel.widthStdMax",*PARAM_BOUNDS["psfsel.widthStdMax"])
    p["match.maxOffsetPix"]= trial.suggest_int  ("match.maxOffsetPix",*PARAM_BOUNDS["match.maxOffsetPix"])
    p["match.maxRotationDeg"]    = trial.suggest_float("match.maxRotationDeg", *PARAM_BOUNDS["match.maxRotationDeg"])
    p["match.matcherIterations"] = trial.suggest_int  ("match.matcherIterations", *PARAM_BOUNDS["match.matcherIterations"])
    p["match.minMatchDistPixels"]= trial.suggest_float("match.minMatchDistPixels", *PARAM_BOUNDS["match.minMatchDistPixels"])
    p["match.minMatchedPairs"]   = trial.suggest_int  ("match.minMatchedPairs", *PARAM_BOUNDS["match.minMatchedPairs"])
    p["match.minFracMatchedPairs"]=trial.suggest_float("match.minFracMatchedPairs", *PARAM_BOUNDS["match.minFracMatchedPairs"])
    p["match.numBrightStars"]    = trial.suggest_int  ("match.numBrightStars", *PARAM_BOUNDS["match.numBrightStars"])
    p["match.maxRefObjects"]     = trial.suggest_int  ("match.maxRefObjects", *PARAM_BOUNDS["match.maxRefObjects"])
    p["match.numPatternConsensus"]=trial.suggest_int  ("match.numPatternConsensus", *PARAM_BOUNDS["match.numPatternConsensus"])
    p["astro_src.snmin"] = trial.suggest_float("astro_src.snmin", *PARAM_BOUNDS["astro_src.snmin"])
    p["apcorr.snmin"]    = trial.suggest_float("apcorr.snmin",    *PARAM_BOUNDS["apcorr.snmin"])
    p["apcorr.sigclip"]  = trial.suggest_float("apcorr.sigclip",  *PARAM_BOUNDS["apcorr.sigclip"])
    p["apcorr.niter"]    = trial.suggest_int  ("apcorr.niter",    *PARAM_BOUNDS["apcorr.niter"])
    p["ncf.snmin"]       = trial.suggest_float("ncf.snmin",       *PARAM_BOUNDS["ncf.snmin"])
    return p

def write_overrides(ctx: Context, params: Dict[str, Any], tag: str) -> Path:
    """
    Emit a calibrateImage overrides .py matching your requested loosened settings.
    """
    trial_dir = ctx.workdir / "trials" / tag
    trial_dir.mkdir(parents=True, exist_ok=True)
    ov_path = trial_dir / f"calib_overrides_{tag}.py"

    txt = f"""# Auto-generated overrides for {tag}
def setDefaults(config):
    # --- PSF detection ---
    config.psf_detection.thresholdValue = {params["psf_det.threshold"]:.6g}
    config.psf_detection.includeThresholdMultiplier = {params["psf_det.incMult"]:.6g}

    # --- PSF star selector: objectSize ---
    cfg = config.psf_measure_psf.starSelector["objectSize"]
    cfg.doSignalToNoiseLimit = True
    cfg.signalToNoiseMin = {params["psfsel.snmin"]:.6g}
    cfg.doFluxLimit = False
    cfg.widthMin = 0.8
    cfg.widthMax = 8.0
    cfg.widthStdAllowed = {params["psfsel.widthStdMax"]:.6g}
    cfg.nSigmaClip = 3.0
    config.psf_measure_psf.reserve.fraction = 0.0

    # --- Astrometry matcher (pessimisticB) ---
    m = config.astrometry.matcher
    m.maxOffsetPix = {int(params["match.maxOffsetPix"])}
    m.maxRotationDeg = {params["match.maxRotationDeg"]:.6g}
    m.matcherIterations = {int(params["match.matcherIterations"])}
    m.minMatchDistPixels = {params["match.minMatchDistPixels"]:.6g}
    m.minMatchedPairs = {int(params["match.minMatchedPairs"])}
    m.minFracMatchedPairs = {params["match.minFracMatchedPairs"]:.6g}
    m.numBrightStars = {int(params["match.numBrightStars"])}
    m.maxRefObjects = {int(params["match.maxRefObjects"])}
    m.numPatternConsensus = {int(params["match.numPatternConsensus"])}

    # --- Astrometry source selector ---
    ss = config.astrometry.sourceSelector["science"]
    ss.doSignalToNoise = True
    ss.signalToNoise.minimum = {params["astro_src.snmin"]:.6g}

    # --- Aperture correction selector ---
    c = config.measure_aperture_correction
    c.sourceSelector.name = "science"
    css = c.sourceSelector["science"]
    css.doSignalToNoise = True
    css.signalToNoise.minimum = {params["apcorr.snmin"]:.6g}
    css.signalToNoise.maximum = None
    c.numSigmaClip = {params["apcorr.sigclip"]:.6g}
    c.numIter = {int(params["apcorr.niter"])}

    # --- PSF Normalized Calibration Flux selector ---
    ncf = config.psf_normalized_calibration_flux.measure_ap_corr
    ncf.sourceSelector.name = "science"
    nss = ncf.sourceSelector["science"]
    nss.doSignalToNoise = True
    nss.signalToNoise.minimum = {params["ncf.snmin"]:.6g}
    nss.doUnresolved = False
    nss.doIsolated = False
"""
    ov_path.write_text(txt)
    return ov_path

# -----------------
# Score & penalties
# -----------------

# Targets / weights (tweak as desired)
TARGETS = {
    "psfSigma_med":        2.0,    # pixels, lower better
    "astromOffsetStd_med": 0.035,  # arcsec, lower better
    "skyNoise_med":        9.0,    # ADU,   lower better
    "magLim_med":          20.0,   # mag,   higher better
}
WEIGHTS = {
    "psfSigma_med":        0.35,
    "astromOffsetStd_med": 0.35,
    "skyNoise_med":        0.15,
    "magLim_med":          0.15,
}

def compute_base_score(meds: Dict[str, float]) -> float:
    """
    Lower is better. Score near 1 is "on target".
    Uses ratio to TARGETS with signed sense (magLim inverted).
    """
    terms = []
    # Lower-is-better metrics: ratio to target
    for k in ("psfSigma_med", "astromOffsetStd_med", "skyNoise_med"):
        if meds.get(k) is None or meds[k] <= 0:
            return float("inf")
        r = meds[k] / TARGETS[k]
        terms.append(WEIGHTS[k] * r)
    # Higher-is-better: use target / value
    k = "magLim_med"
    if meds.get(k) is None or meds[k] <= 0:
        return float("inf")
    r = TARGETS[k] / meds[k]
    terms.append(WEIGHTS[k] * r)
    return sum(terms)

def penalize_score(base_score: float, n_success: int, n_total: int, policy: str, weight: float) -> float:
    if n_total <= 0:
        return float("inf")
    n_fail = n_total - n_success
    if policy == "hard":
        return float("inf") if n_fail > 0 else base_score
    if policy == "frac":
        sr = n_success / n_total
        if sr <= 0:
            return float("inf")
        return base_score * (sr ** (-weight))
    if policy == "linear":
        return base_score * (1.0 + weight * n_fail)
    return base_score

# --------------------------
# Butler interaction (Gen3)
# --------------------------

def read_visit_summaries(out_coll: str, repo: Path, visits: List[int]) -> List[Any]:
    from lsst.daf.butler import Butler
    butler = Butler(str(repo), collections=out_coll, instrument="Nickel")
    rows = []
    for v in visits:
        try:
            vs = butler.get("visitSummary", {"instrument": "Nickel", "visit": int(v)})
            # convert to astropy Table row 0 (one detector)
            tbl = vs.asAstropy()
            if len(tbl) > 0:
                rows.append(tbl[0])
        except Exception:
            # skip missing visitSummary (failed visit)
            pass
    return rows

def med_from_rows(rows: List[Any], field: str) -> float | None:
    vals = []
    for r in rows:
        try:
            vals.append(float(r[field]))
        except Exception:
            pass
    if not vals:
        return None
    vals.sort()
    n = len(vals)
    if n % 2 == 1:
        return vals[n // 2]
    else:
        return 0.5 * (vals[n // 2 - 1] + vals[n // 2])

# --------------------------
# Command builders per visit
# --------------------------

def build_calibrate_cmd(ctx: Context, overrides: Path, visit: int, out_coll: str) -> List[str]:
    # Note: Do not pass unsupported flags like --log-level (your ctrl_mpexec doesn’t accept it).
    return [
        "pipetask", "run",
        "-b", str(ctx.repo),
        "-i", ",".join([ctx.inputs_postisr, ctx.calib_chain, ctx.refcats]),
        "-o", out_coll,
        "-p", str(ctx.proc_pipe) + "#calibrateImage",
        "-C", f"calibrateImage:{overrides}",
        "-j", str(ctx.jobs),
        "--register-dataset-types",
        "-d", f"instrument='Nickel' AND exposure.observation_type='science' AND visit IN ({int(visit)})",
    ]

# ---------------
# Trial execution
# ---------------

def run_trial(ctx: Context, params: Dict[str, Any], tag: str, trial_index: int) -> Tuple[str, float, Dict[str, Any]]:
    trial_dir = ctx.workdir / "trials" / tag
    trial_dir.mkdir(parents=True, exist_ok=True)
    overrides = write_overrides(ctx, params, tag)

    # Output collection is a CHAINED collection we keep appending runs to via timestamped child runs.
    out_coll = f"Nickel/run/calib_tune/{tag}"

    success_visits: List[int] = []
    failed_visits: List[int] = []

    for v in ctx.visits:
        cmd = build_calibrate_cmd(ctx, overrides, v, out_coll)
        stdout_log = trial_dir / f"v{v}_stdout.log"
        stderr_log = trial_dir / f"v{v}_stderr.log"
        try:
            run(cmd, check=True, stdout_log=stdout_log, stderr_log=stderr_log)
            success_visits.append(v)
        except subprocess.CalledProcessError as e:
            failed_visits.append(v)
            log_failure(ctx, f"{tag}-v{v}", e, cmd, stdout_log, stderr_log)

    n_total = len(ctx.visits)
    n_success = len(success_visits)

    if n_success == 0:
        raise optuna.TrialPruned("All visits failed in this trial")

    # Metrics from visitSummary on successful visits only
    rows = read_visit_summaries(out_coll, ctx.repo, success_visits)
    meds = {
        "psfSigma_med":        med_from_rows(rows, "psfSigma"),
        "astromOffsetStd_med": med_from_rows(rows, "astromOffsetStd"),
        "skyNoise_med":        med_from_rows(rows, "skyNoise"),
        "magLim_med":          med_from_rows(rows, "magLim"),
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

    # Persist per-trial summary JSON
    (trial_dir / "metrics.json").write_text(json.dumps({
        "time": now_utc_iso(),
        "trial_index": trial_index,
        "trial_tag": tag,
        "out_coll": out_coll,
        "params": params,
        "metrics": metrics,
        "success_visits": success_visits,
        "failed_visits": failed_visits,
        "overrides_path": str(overrides),
    }, indent=2))

    # Append a row to the global runs table
    runs_csv = ctx.workdir / "tuning_runs.csv"
    runs_row = {
        "time": now_utc_iso(),
        "trial_index": trial_index,
        "trial_tag": tag,
        "status": "ok" if n_success == n_total else ("partial" if n_success > 0 else "fail"),
        "out_coll": out_coll,
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
        "overrides_path": str(overrides),
        "trial_dir": str(trial_dir),
    }
    write_csv_row(runs_csv, RUNS_CSV_HEADERS, runs_row)

    return out_coll, score, metrics

# --------------
# Optuna objective
# --------------

def make_objective(ctx: Context):
    def objective(trial: optuna.Trial) -> float:
        params = suggest_params(trial)
        tag = f"t{trial.number:03d}"
        try:
            out_coll, score, metrics = run_trial(ctx, params, tag, trial.number)
            trial.set_user_attr("out_coll", out_coll)
            trial.set_user_attr("metrics", metrics)
            trial.set_user_attr("params", params)
            return score
        except optuna.TrialPruned as e:
            # still log a runs row with fail status (no metrics)
            runs_csv = ctx.workdir / "tuning_runs.csv"
            write_csv_row(runs_csv, RUNS_CSV_HEADERS, {
                "time": now_utc_iso(), "trial_index": trial.number, "trial_tag": tag,
                "status": "fail", "out_coll": "",
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
            raise
        except Exception as e:
            # fatal trial failure -> log & prune
            log_failure(ctx, tag, e, cmd=[], stdout_log=None, stderr_log=None)
            raise optuna.TrialPruned(f"Trial error: {e}")
    return objective

# ------
#  Main
# ------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tune Nickel calibrateImage with failure-penalized scoring")
    p.add_argument("--repo", required=True, help="Butler repo path")
    p.add_argument("--obs-nickel", required=True, help="obs_nickel package root")
    p.add_argument("--visits", nargs="+", type=int, required=True, help="visit IDs to process")
    p.add_argument("--bad", nargs="*", type=int, default=[], help="visits to exclude")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--trials", type=int, default=20)
    p.add_argument("--workdir", required=True, help="directory to store trial artifacts & tables")
    p.add_argument("--proc-pipe", default=None, help="ProcessCcd.yaml path; default uses obs-nickel/pipelines/ProcessCcd.yaml")
    p.add_argument("--post-pipe", default=None, help="PostProcessing.yaml path; kept for reference")
    p.add_argument("--inputs-postisr", default=None, help="postISR input collection (e.g., Nickel/run/processCcd/...)")
    p.add_argument("--calib-chain", default="Nickel/calib/current")
    p.add_argument("--refcats", default="refcats")
    p.add_argument("--fail-policy", choices=["hard","frac","linear"], default="frac")
    p.add_argument("--fail-weight", type=float, default=1.0)
    return p.parse_args()

def discover_postisr(repo: Path) -> str:
    # naive: pick the most recent Nickel/run/processCcd/* collection
    from lsst.daf.butler import Butler
    b = Butler(str(repo))
    cands = [str(rec) for rec in b.registry.queryCollections() if str(rec).startswith("Nickel/run/processCcd/")]
    return sorted(cands)[-1] if cands else ""

def main() -> None:
    args = parse_args()
    repo = Path(args.repo)
    obs = Path(args.obs_nickel)
    proc_pipe = Path(args.proc_pipe) if args.proc_pipe else obs / "pipelines" / "ProcessCcd.yaml"
    post_pipe = Path(args.post_pipe) if args.post_pipe else obs / "pipelines" / "PostProcessing.yaml"
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    inputs_postisr = args.inputs_postisr or discover_postisr(repo)
    if not inputs_postisr:
        print("[inputs] Could not discover postISR collection automatically; specify --inputs-postisr", file=sys.stderr)
        sys.exit(2)

    visits = [v for v in args.visits if v not in set(args.bad)]
    print(f"[inputs] postISR: {inputs_postisr}")
    print(f"[inputs] calib  : {args.calib_chain}")
    print(f"[inputs] proc   : {proc_pipe}")
    print(f"[inputs] post   : {post_pipe}")
    print(f"[inputs] visits : {visits} (excluded {args.bad})")

    ctx = Context(
        repo=repo,
        obs_nickel=obs,
        proc_pipe=proc_pipe,
        post_pipe=post_pipe,
        workdir=workdir,
        visits=visits,
        bad=args.bad,
        jobs=args.jobs,
        inputs_postisr=inputs_postisr,
        calib_chain=args.calib_chain,
        refcats=args.refcats,
        fail_policy=args.fail_policy,
        fail_weight=args.fail_weight,
    )

    study = optuna.create_study(direction="minimize")
    study.optimize(make_objective(ctx), n_trials=args.trials, show_progress_bar=True)

    best = study.best_trial
    print("\n=== BEST TRIAL ===")
    out = {
        "value": best.value,
        "params": best.user_attrs.get("params", best.params),
        "metrics": best.user_attrs.get("metrics", {}),
        "out_coll": best.user_attrs.get("out_coll", ""),
    }
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
