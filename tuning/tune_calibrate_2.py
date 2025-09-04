#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tune calibrateImage using EXISTING ISR + latest calibs in the repo,
and score from a post-processing visitTable (via initial_pvi).

Example:
  python tune_calibrate_postISR.py \
    --repo "/Users/dangause/Desktop/lick/lsst/data/nickel/062424" \
    --obs-nickel "/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/obs_nickel" \
    --visits 1041 1035 \
    --bad 1032 1051 1052 \
    --jobs 1 \
    --trials 10
"""

from __future__ import annotations
import argparse, json, math, os, re, shlex, subprocess, sys, traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import numpy as np
import optuna
from datetime import datetime, timezone
import csv

from lsst.daf.butler import Butler

# ---------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------
def run(cmd: List[str] | str, check=True, capture=False) -> subprocess.CompletedProcess:
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    if capture:
        return subprocess.run(cmd, check=check, text=True, capture_output=True)
    else:
        return subprocess.run(cmd, check=check)

def robust_rms(x, clip=3.0) -> float:
    x = np.asarray(x, float)
    if x.size == 0 or not np.isfinite(x).any():
        return np.nan
    m = np.nanmedian(x)
    s = 1.4826*np.nanmedian(np.abs(x-m))
    if s <= 0 or not np.isfinite(s):
        s = np.nanstd(x)
    sel = np.isfinite(x) & (np.abs(x-m) < clip*(s if s>0 else 1.0))
    y = x[sel]
    return float(np.sqrt(np.nanmean((y-np.nanmean(y))**2))) if y.size else np.nan

def mag_from_njy(njy):
    njy = np.asarray(njy, float)
    with np.errstate(divide='ignore', invalid='ignore'):
        return 31.4 - 2.5*np.log10(njy)

def log_failure(ctx: "Context", tag: str, error: BaseException, extra: dict | None = None):
    ctx.workdir.mkdir(parents=True, exist_ok=True)
    log_csv = ctx.workdir / "trial_failures.csv"
    row = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trial_tag": tag,
        "exception": type(error).__name__,
        "message": str(error),
    }
    if extra:
        row.update(extra)
    new_file = not log_csv.exists()
    with open(log_csv, "a", newline="") as f:
        # preserve column order across appends
        fieldnames = list(row.keys())
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            w.writeheader()
        w.writerow(row)

# ---------------------------------------------------------------------
# Repo discovery helpers
# ---------------------------------------------------------------------
def _list_collections_cli(repo: Path) -> list[str]:
    """List all collection names using CLI; skip headers/blank lines."""
    cmd = f'butler query-collections "{repo}"'
    p = subprocess.run(shlex.split(cmd), text=True, capture_output=True)
    if p.returncode != 0:
        return []
    names: list[str] = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("name") or line.startswith("---"):
            continue
        first = line.split()[0]
        if first.lower() in {"name", "type", "chains", "collection"}:
            continue
        if not re.match(r"^[A-Za-z0-9_./:-]+$", first):
            continue
        names.append(first)
    return names

def collection_exists(repo: Path, name: str) -> bool:
    return name in _list_collections_cli(repo)

def find_latest_postisr_collection(repo: Path, instrument: str = "Nickel") -> str:
    """Return newest run collection that contains postISRCCD for this instrument."""
    collections = _list_collections_cli(repo)
    if not collections:
        raise RuntimeError("No collections found in the repo.")

    b = Butler(repo)
    refs = list(
        b.registry.queryDatasets(
            "postISRCCD",
            collections=collections,
            where=f"instrument = '{instrument}'",
            findFirst=False,
        )
    )
    if not refs:
        raise RuntimeError("No postISRCCD datasets found for this instrument.")

    run_names = []
    for ref in refs:
        run_name = ref.run if isinstance(ref.run, str) else getattr(ref.run, "collection", None)
        if run_name:
            run_names.append(run_name)
    if not run_names:
        raise RuntimeError("Found postISRCCD refs but could not extract run names.")

    run_names = sorted(set(run_names))

    def score(name: str):
        m = re.search(r"(\d{8}T?\d{6,})Z?$", name)
        ts = m.group(1) if m else ""
        return (name.startswith("Nickel/run/"), ts, name)

    run_names.sort(key=score, reverse=True)
    print("[postISR candidates] top 5:", run_names[:5])
    return run_names[0]

# ---------------------------------------------------------------------
# Sampling space for Optuna
# ---------------------------------------------------------------------
def sample_params(trial: optuna.trial.Trial) -> dict:
    return {
        # Detection & selection knobs (kept conservative)
        "star.det.threshold": trial.suggest_float("star.det.threshold", 5.0, 8.0),
        "star.det.incMult":  trial.suggest_float("star.det.incMult",  2.0, 4.5),
        "star.sel.snrMin":   trial.suggest_float("star.sel.snrMin",   10.0, 30.0),

        # Aperture choices (string of radii pixels)
        "ap.radii.choice":   trial.suggest_categorical("ap.radii.choice", ["8,12", "10,14", "12,16"]),

        # Aperture-correction star selection
        "apcorr.sel.doSNR":  trial.suggest_categorical("apcorr.sel.doSNR", [True, False]),
        "apcorr.sel.snrMin": trial.suggest_float("apcorr.sel.snrMin", 12.0, 30.0),

        # Astrometry source selection
        "astro.sel.doSNR":   trial.suggest_categorical("astro.sel.doSNR", [True, False]),
        "astro.sel.snrMin":  trial.suggest_float("astro.sel.snrMin", 10.0, 30.0),

        # Photometry match selection
        "photo.sel.snrMin":  trial.suggest_float("photo.sel.snrMin", 10.0, 30.0),
    }

# ---------------------------------------------------------------------
# Context container
# ---------------------------------------------------------------------
@dataclass
class Context:
    repo: Path
    obs_nickel: Path
    instr: str
    det: int
    visits: List[int]
    bad: List[int]
    jobs: int
    postisr_coll: str
    calib_chain: str
    pipeline_yaml: Path
    postproc_yaml: Path
    workdir: Path

# ---------------------------------------------------------------------
# Overrides for calibrateImage (safe fields only)
# ---------------------------------------------------------------------
def write_overrides(ctx: Context, params: dict, tag: str) -> Path:
    lines = []

    # ----- Detection (PSF pass makes its own choices; final star pass here) -----
    thr  = float(params.get("star.det.threshold", 6.0))
    mult = float(params.get("star.det.incMult", 3.0))
    lines += [
        "try:\n    config.star_detection.thresholdValue = %.3f\nexcept Exception:\n    pass" % thr,
        "try:\n    config.star_detection.includeThresholdMultiplier = %.3f\nexcept Exception:\n    pass" % mult,
    ]

    # ----- Star selector for downstream (science) -----
    star_snr = float(params.get("star.sel.snrMin", 15.0))
    lines += [
        "try:\n    config.star_selector['science'].doSignalToNoise = True\nexcept Exception:\n    pass",
        "try:\n    config.star_selector['science'].signalToNoise.minimum = %.3f\nexcept Exception:\n    pass" % star_snr,
    ]

    # ----- Aperture radii (affects apcorr & consistency) -----
    radii_str = params.get("ap.radii.choice", "12,16")
    radii_vals = [float(x) for x in radii_str.split(",")]
    radii_list = ", ".join(f"{r:.1f}" for r in radii_vals)
    lines += [
        f"try:\n    config.star_measurement.plugins['base_CircularApertureFlux'].radii = [{radii_list}]\nexcept Exception:\n    pass",
    ]

    # ----- ApCorr selection -----
    ap_do_snr  = bool(params.get("apcorr.sel.doSNR", True))
    ap_snr_min = float(params.get("apcorr.sel.snrMin", 15.0))
    lines += [
        "try:\n    config.measure_aperture_correction.sourceSelector['science'].doSignalToNoise = %s\nexcept Exception:\n    pass" % ("True" if ap_do_snr else "False"),
        "try:\n    config.measure_aperture_correction.sourceSelector['science'].signalToNoise.minimum = %.3f\nexcept Exception:\n    pass" % ap_snr_min,
    ]

    # ----- Astrometry source selection (do NOT touch wcsFitter.order) -----
    astro_doSNR = bool(params.get("astro.sel.doSNR", True))
    astro_snr   = float(params.get("astro.sel.snrMin", 12.0))
    lines += [
        "try:\n    config.astrometry.sourceSelector['science'].doSignalToNoise = %s\nexcept Exception:\n    pass" % ("True" if astro_doSNR else "False"),
        "try:\n    config.astrometry.sourceSelector['science'].signalToNoise.minimum = %.3f\nexcept Exception:\n    pass" % astro_snr,
        "try:\n    config.astrometry.sourceSelector['science'].doRequirePrimary = False\nexcept Exception:\n    pass",
        "try:\n    config.astrometry.sourceSelector['science'].doIsolated = False\nexcept Exception:\n    pass",
    ]

    # ----- Photometry (do NOT set photoCalibOrder; Nickel uses PhotoCal) -----
    photo_snr   = float(params.get("photo.sel.snrMin", 12.0))
    lines += [
        "try:\n    config.photometry.applyColorTerms = False\nexcept Exception:\n    pass",
        "try:\n    config.photometry.match.sourceSelection.doSignalToNoise = True\nexcept Exception:\n    pass",
        "try:\n    config.photometry.match.sourceSelection.signalToNoise.minimum = %.3f\nexcept Exception:\n    pass" % photo_snr,
        "try:\n    config.photometry.match.sourceSelection.doRequirePrimary = False\nexcept Exception:\n    pass",
        "try:\n    config.photometry.match.sourceSelection.doUnresolved = False\nexcept Exception:\n    pass",
    ]

    # ----- Persist matches for metrics (names depend on task; harmless if absent) -----
    lines.append(
        'try:\n    config.optional_outputs = tuple(sorted(set(config.optional_outputs) | {"photometry_matches","astrometry_matches"}))\nexcept Exception:\n    pass'
    )

    out = ctx.workdir / f"calib_overrides_{tag}.py"
    out.write_text("\n".join(lines) + "\n")
    return out

# ---------------------------------------------------------------------
# Post-processing: build visitTable from initial_pvi + visitSummary
# ---------------------------------------------------------------------
def run_postproc(ctx, out_coll, tag):
    """Run PostProcessing.yaml once per trial into a fresh RUN under the chain."""
    repo      = ctx.repo
    pipe_post = ctx.postproc_yaml  # your PostProcessing.yaml path
    jobs      = ctx.jobs

    # fresh RUN under the trial chain (no rebase needed)
    ts_run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    post_run = f"{out_coll}/{ts_run}"   # e.g. Nickel/run/calib_tune/t000/20250904T065012Z

    # IMPORTANT: use the trial chain as an INPUT, not the OUTPUT.
    # You don’t need postISR here; you’re consolidating products from the trial.
    cmd = [
        "pipetask", "run",
        "-b", str(repo),
        "-i", f"{out_coll},refcats",         # include calib chain if your postproc needs it
        "-o", post_run,                      # fresh RUN; safe to rerun multiple times
        "-p", str(pipe_post),
        "--register-dataset-types",
        "-j", str(jobs),
        # Optional: restrict to the same visits used in the trial
        "-d", f"instrument='{ctx.instr}' AND detector={ctx.det} "
              f"AND exposure.observation_type='science' "
              f"AND visit IN ({','.join(map(str, sorted(set(ctx.visits) - set(ctx.bad))))})",
    ]
    run(cmd, check=True)
    return post_run


# ---------------------------------------------------------------------
# Metric from visitTable (robust: tolerate missing columns)
# ---------------------------------------------------------------------
def evaluate_metric_from_visit_table(ctx: Context, out_coll: str) -> Tuple[float, dict]:
    """
    Score = mean of normalized terms among available ones (lower is better):
      - psfFwhm_arcsec / 2.0
      - sky_background / 500.0
      - astrom_rms_mas / 50.0
      - zp_sigma_mag / 0.02
      - ap_psf_diff_rms_mag / 0.02
    """
    b = Butler(ctx.repo, instrument=ctx.instr, collections=out_coll)

    table = None
    try:
        table = b.get("visitTable")
    except Exception:
        pass

    if table is None:
        # Fallback: aggregate minimal info from visitSummary
        rows = []
        for v in sorted(set(ctx.visits) - set(ctx.bad)):
            dataId = dict(instrument=ctx.instr, detector=ctx.det, visit=v)
            try:
                vsum = b.get("visitSummary", dataId=dataId)
            except Exception:
                continue
            row = {"visit": v}
            for k in ("psfFwhm", "psfFwhmArcsec", "psf_fwhm", "seeing"):
                val = getattr(vsum, k, None)
                if val is not None:
                    row["psfFwhm"] = float(val)
                    break
            for k in ("skyBackground", "medianBackground", "skyMedian"):
                val = getattr(vsum, k, None)
                if val is not None:
                    row["sky"] = float(val)
                    break
            rows.append(row)
        if not rows:
            return float("nan"), dict(n_rows=0)
        table = rows  # list of dicts

    def get_col(names):
        try:
            if hasattr(table, "colnames"):  # Astropy Table
                for n in names:
                    if n in table.colnames:
                        return np.asarray(table[n], dtype=float)
        except Exception:
            pass
        if isinstance(table, list) and table and isinstance(table[0], dict):
            for n in names:
                vals = [r[n] for r in table if n in r and r[n] is not None]
                if vals:
                    return np.asarray(vals, dtype=float)
        try:
            if hasattr(table, "dtype") and table.dtype.names:
                for n in names:
                    if n in table.dtype.names:
                        return np.asarray(table[n], dtype=float)
        except Exception:
            pass
        return None

    psf_arcsec = get_col(["psfFwhm", "psfFwhmArcsec", "seeing_arcsec", "seeing"])
    sky_bg     = get_col(["sky", "skyBackground", "medianBackground", "skyMedian"])
    astrom_rms = get_col(["astromRmsMas", "astrometry_rms_mas", "wcsRmsMas"])
    zp_sigma   = get_col(["zpSigmaMag", "photZpSigmaMag", "photoZpSigma"])
    ap_psf_rms = get_col(["apPsfDiffRmsMag", "apcorrRmsMag", "ap_psf_diff_rms_mag"])

    def finite_mean(x):
        if x is None:
            return np.nan
        x = np.asarray(x, dtype=float)
        x = x[np.isfinite(x)]
        return float(np.mean(x)) if x.size else np.nan

    metrics = dict(
        psfFwhm_arcsec       = finite_mean(psf_arcsec),
        sky_background       = finite_mean(sky_bg),
        astrom_rms_mas       = finite_mean(astrom_rms),
        zp_sigma_mag         = finite_mean(zp_sigma),
        ap_psf_diff_rms_mag  = finite_mean(ap_psf_rms),
        n_rows               = (len(table) if hasattr(table, "__len__") else 0),
    )

    terms = []
    if np.isfinite(metrics["psfFwhm_arcsec"]):
        terms.append(metrics["psfFwhm_arcsec"] / 2.0)
    if np.isfinite(metrics["sky_background"]):
        terms.append(metrics["sky_background"] / 500.0)
    if np.isfinite(metrics["astrom_rms_mas"]):
        terms.append(metrics["astrom_rms_mas"] / 50.0)
    if np.isfinite(metrics["zp_sigma_mag"]):
        terms.append(metrics["zp_sigma_mag"] / 0.02)
    if np.isfinite(metrics["ap_psf_diff_rms_mag"]):
        terms.append(metrics["ap_psf_diff_rms_mag"] / 0.02)

    score = float(np.mean(terms)) if terms else float("nan")
    return score, metrics

# ---------------------------------------------------------------------
# Trial runner: run calibrateImage per-visit; skip failures; postproc; score
# ---------------------------------------------------------------------
def run_trial(ctx: Context, params: dict, tag: str) -> Tuple[str, float, dict]:
    repo         = str(ctx.repo)
    pipe         = str(ctx.pipeline_yaml)
    postisr_coll = ctx.postisr_coll
    calib_chain  = ctx.calib_chain
    jobs         = ctx.jobs
    visits_all   = sorted(set(ctx.visits) - set(ctx.bad))
    ctx.workdir.mkdir(parents=True, exist_ok=True)

    override_py = write_overrides(ctx, params, tag)
    out_coll = f"Nickel/run/calib_tune/{tag}"

    base_cmd = [
        "pipetask", "run",
        "-b", repo,
        "-i", f"{postisr_coll},{calib_chain},refcats",
        "-o", out_coll,
        "-p", f"{pipe}#calibrateImage",
        "-C", f"calibrateImage:{override_py}",
        "-j", str(jobs),
    ]
    base_cmd_reg = base_cmd + ["--register-dataset-types"]

    good_visits: list[int] = []

    for i, v in enumerate(visits_all):
        where = f"instrument='{ctx.instr}' AND exposure.observation_type='science' AND visit IN ({v})"
        cmd   = (base_cmd_reg if i == 0 else base_cmd) + ["-d", where]
        try:
            run(cmd, check=True)
            good_visits.append(v)
        except subprocess.CalledProcessError as e:
            log_failure(ctx, f"{tag}-v{v}", e, extra={"visit": v, "cmd": " ".join(e.cmd)})
            continue
        except Exception as e:
            log_failure(ctx, f"{tag}-v{v}", e, extra={"visit": v, "traceback": traceback.format_exc()})
            continue

    if not good_visits:
        raise optuna.TrialPruned("All visits failed in this trial")

    # Build visitTable in out_coll using initial_pvi
    try:
        run_postproc_visit_table(ctx, out_coll, good_visits)
    except subprocess.CalledProcessError as e:
        log_failure(ctx, f"{tag}-postproc", e, extra={"cmd": " ".join(e.cmd)})
    except Exception as e:
        log_failure(ctx, f"{tag}-postproc", e, extra={"traceback": traceback.format_exc()})

    # Score from visitTable
    score, metrics = evaluate_metric_from_visit_table(ctx, out_coll)

    if not np.isfinite(score):
        # Fallback: smaller PSF + lower sky
        psf = metrics.get("psfFwhm_arcsec", np.nan)
        sky = metrics.get("sky_background", np.nan)
        fallback_terms = []
        if np.isfinite(psf): fallback_terms.append(psf / 2.0)
        if np.isfinite(sky): fallback_terms.append(sky / 500.0)
        score = float(np.mean(fallback_terms)) if fallback_terms else float("inf")

    (ctx.workdir / f"{tag}.ok").write_text(f"{out_coll} ; visits={good_visits} ; score={score}\n")
    return out_coll, float(score), metrics

# ---------------------------------------------------------------------
# Optuna objective factory
# ---------------------------------------------------------------------
def make_objective(ctx: Context):
    def objective(trial: optuna.trial.Trial) -> float:
        params = sample_params(trial)
        tag = f"t{trial.number:03d}"
        try:
            out_coll, score, metrics = run_trial(ctx, params, tag)

            if not np.isfinite(score):
                raise optuna.TrialPruned("Score NaN/inf after visitTable evaluation")

            trial.set_user_attr("output_collection", out_coll)
            trial.set_user_attr("params", params)
            trial.set_user_attr("metrics", metrics)
            return float(score)

        except optuna.TrialPruned:
            raise
        except subprocess.CalledProcessError as e:
            log_failure(ctx, tag, e, extra={"cmd": " ".join(e.cmd)})
            raise optuna.TrialPruned(f"pipetask failed (returncode={e.returncode})")
        except Exception as e:
            log_failure(ctx, tag, e, extra={"traceback": traceback.format_exc()})
            raise optuna.TrialPruned("Trial failed during preparation/execution")
    return objective

# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Tune calibrateImage using existing ISR + visitTable scoring.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--obs-nickel", required=True)
    ap.add_argument("--instrument", default="Nickel")
    ap.add_argument("--det", type=int, default=0)
    ap.add_argument("--visits", type=int, nargs="+", required=True)
    ap.add_argument("--bad", type=int, nargs="*", default=[1032,1051,1052])
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--postproc-yaml", default="pipelines/PostProcessing.yaml",
                    help="YAML with ConsolidateVisitSummaryTask/MakeVisitTableTask (using initial_pvi).")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser()
    obs = Path(args.obs_nickel).expanduser()
    proc_yaml = obs / "pipelines/ProcessCcd.yaml"
    postproc_yaml = Path(args.postproc_yaml).expanduser()
    workdir = repo / "tuning_runs"
    workdir.mkdir(parents=True, exist_ok=True)

    postisr = find_latest_postisr_collection(repo, instrument=args.instrument)
    calib_chain = "Nickel/calib/current" if collection_exists(repo, "Nickel/calib/current") else ""
    if not calib_chain:
        raise RuntimeError("Expected Nickel/calib/current to exist. Please chain your curated/cp runs first.")

    print(f"[inputs] postISR: {postisr}")
    print(f"[inputs] calib  : {calib_chain}")
    print(f"[inputs] pipe   : {proc_yaml}")

    ctx = Context(
        repo=repo, obs_nickel=obs, instr=args.instrument, det=args.det,
        visits=args.visits, bad=args.bad, jobs=args.jobs,
        postisr_coll=postisr, calib_chain=calib_chain,
        pipeline_yaml=proc_yaml, postproc_yaml=postproc_yaml,
        workdir=workdir
    )

    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    study.optimize(make_objective(ctx), n_trials=args.trials, show_progress_bar=True)

    # Handle case where all trials were pruned
    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    if not completed:
        print("\nNo trials completed successfully (all pruned). Check", ctx.workdir / "trial_failures.csv", "for details.")
        return

    best = study.best_trial
    best_payload = {
        "value": float(best.value),
        "params": best.params,
        "metrics": best.user_attrs.get("metrics", {}),
        "out_coll": best.user_attrs.get("output_collection", ""),
    }
    print("\n=== BEST TRIAL ===")
    print(json.dumps(best_payload, indent=2))
    (ctx.workdir / "best_params.json").write_text(json.dumps(best_payload, indent=2) + "\n")

if __name__ == "__main__":
    main()
