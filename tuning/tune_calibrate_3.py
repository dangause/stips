#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tune calibrateImage using EXISTING ISR + latest calibs.
Score each trial from the PostProcessing visitSummary table.

- Per-visit pipetask runs; failures are logged and skipped.
- PostProcessing writes to a NEW RUN *under* the trial's chain.
- Metrics come from visitSummary (robust medians, NaN-proof).
"""

# from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shlex
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict

import numpy as np
import optuna

from lsst.daf.butler import Butler

# ===========================
# subprocess + logging helpers
# ===========================

import shlex, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

def run(cmd, check=True, timeout=60*20):  # 20 min default
    """Run a command capturing output; raise CalledProcessError on failure.
    Prints the last ~40 lines of stderr on failure to help debugging.
    """
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    try:
        return subprocess.run(cmd, check=check, text=True, capture_output=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        tail = "\n".join((e.stderr or "").splitlines()[-40:])
        print("\n--- pipetask STDERR tail ---", file=sys.stderr)
        print(tail, file=sys.stderr)
        print("--- end STDERR tail ---\n", file=sys.stderr)
        raise
    except subprocess.TimeoutExpired as e:
        # Repackage as CalledProcessError so the rest of the code paths are uniform
        ce = subprocess.CalledProcessError(returncode=124, cmd=e.cmd, output=e.output, stderr="(timeout)")
        raise ce

_FAILURE_FIELDS = [
    "time","trial_tag","exception","message","visit","returncode","cmd","stdout","stderr","traceback",
]

def log_failure(workdir: Path, tag: str, error: BaseException, extra: dict | None = None) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    log_csv = workdir / "trial_failures.csv"
    row = {k: "" for k in _FAILURE_FIELDS}
    row["time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row["trial_tag"] = tag
    row["exception"] = type(error).__name__
    row["message"] = str(error)

    if isinstance(error, subprocess.CalledProcessError):
        row["returncode"] = error.returncode
        row["cmd"] = " ".join(error.cmd) if isinstance(error.cmd, list) else str(error.cmd)
        row["stdout"] = (error.stdout or "").strip()
        row["stderr"] = (error.stderr or "").strip()

    if extra:
        for k, v in extra.items():
            if k in row:
                row[k] = str(v)
            else:
                row["traceback"] = (row["traceback"] + "\n" + str(v)).strip()

    new_file = not log_csv.exists()
    with open(log_csv, "a", newline="") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=_FAILURE_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)


def robust_median(arr) -> float:
    arr = np.asarray(arr, float)
    arr = arr[np.isfinite(arr)]
    return float(np.nan) if arr.size == 0 else float(np.nanmedian(arr))

# ===========================
# Butler helpers
# ===========================

def _list_collections_cli(repo: Path) -> list[str]:
    cmd = f'butler query-collections "{repo}"'
    p = subprocess.run(shlex.split(cmd), text=True, capture_output=True)
    if p.returncode != 0:
        return []
    names: list[str] = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name") or line.startswith("---"):
            continue
        first = line.split()[0]
        if not re.match(r"^[A-Za-z0-9_./:-]+$", first):
            continue
        names.append(first)
    return names

def collection_exists(repo: Path, name: str) -> bool:
    return name in _list_collections_cli(repo)

def _all_collection_names(repo: Path) -> list[str]:
    b = Butler(repo)
    return [rec.name for rec in b.registry.queryCollections() if getattr(rec, "name", "")]

def find_latest_postisr_collection(repo: Path, instrument: str = "Nickel") -> str:
    """Newest run that contains postISRCCD for this instrument."""
    collections = _list_collections_cli(repo)
    if not collections:
        raise RuntimeError("No collections found in the repo.")
    b = Butler(repo)
    refs = list(b.registry.queryDatasets(
        "postISRCCD",
        collections=collections,
        where=f"instrument = '{instrument}'",
        findFirst=False,
    ))
    if not refs:
        raise RuntimeError("No postISRCCD found for this instrument.")
    run_names = []
    for ref in refs:
        run_name = ref.run if isinstance(ref.run, str) else getattr(ref.run, "collection", None)
        if run_name:
            run_names.append(run_name)
    run_names = sorted(set(run_names))
    def score(name: str):
        m = re.search(r"(\d{8}T?\d{6,})Z?$", name)
        ts = m.group(1) if m else ""
        return (name.startswith("Nickel/run/"), ts, name)
    run_names.sort(key=score, reverse=True)
    print("[postISR candidates] top 5:", run_names[:5])
    return run_names[0]

# ===========================
# Config overrides
# ===========================

def write_overrides(workdir: Path, params: dict, tag: str) -> Path:
    """Produce calibrateImage overrides for this trial."""
    lines: List[str] = []

    # Source detection on star pass
    thr  = float(params.get("star.det.threshold", 6.5))
    mult = float(params.get("star.det.incMult", 1.0))
    lines += [
        f"try:\n    config.star_detection.thresholdValue = {thr:.3f}\nexcept Exception:\n    pass",
        f"try:\n    config.star_detection.includeThresholdMultiplier = {mult:.3f}\nexcept Exception:\n    pass",
    ]

    # Star selection SNR
    star_snr = float(params.get("star.sel.snrMin", 10.0))
    lines += [
        "try:\n    config.star_selector['science'].doSignalToNoise = True\nexcept Exception:\n    pass",
        f"try:\n    config.star_selector['science'].signalToNoise.minimum = {star_snr:.3f}\nexcept Exception:\n    pass",
    ]

    # Aperture radii for star measurement (affects apcorr)
    radii_str = params.get("ap.radii.choice", "12,16")
    radii_vals = [float(x) for x in radii_str.split(",")]
    radii_list = ", ".join(f"{r:.1f}" for r in radii_vals)
    lines += [
        f"try:\n    config.star_measurement.plugins['base_CircularApertureFlux'].radii = [{radii_list}]\nexcept Exception:\n    pass",
    ]

    # Astrometry: be conservative; avoid setting non-existent attributes
    astro_doSNR = bool(params.get("astro.sel.doSNR", False))
    astro_snr   = float(params.get("astro.sel.snrMin", 10.0))
    lines += [
        "try:\n    config.astrometry.sourceSelector['science'].doRequirePrimary = False\nexcept Exception:\n    pass",
        f"try:\n    config.astrometry.sourceSelector['science'].doSignalToNoise = {str(astro_doSNR)}\nexcept Exception:\n    pass",
        f"try:\n    config.astrometry.sourceSelector['science'].signalToNoise.minimum = {astro_snr:.3f}\nexcept Exception:\n    pass",
    ]

    # Photometry (PhotoCal) — do not set order if field absent on this stack
    photo_snr = float(params.get("photo.sel.snrMin", 12.0))
    lines += [
        "try:\n    config.photometry.applyColorTerms = False\nexcept Exception:\n    pass",
        "try:\n    config.photometry.match.sourceSelection.doSignalToNoise = True\nexcept Exception:\n    pass",
        f"try:\n    config.photometry.match.sourceSelection.signalToNoise.minimum = {photo_snr:.3f}\nexcept Exception:\n    pass",
        "try:\n    config.photometry.match.sourceSelection.doRequirePrimary = False\nexcept Exception:\n    pass",
        "try:\n    config.photometry.match.sourceSelection.doUnresolved = False\nexcept Exception:\n    pass",
    ]

    # Persist matches (if supported) — safe to no-op if not present
    lines.append(
        'try:\n    config.optional_outputs = tuple(sorted(set(getattr(config, "optional_outputs", ())) | {"photometry_matches","astrometry_matches"}))\nexcept Exception:\n    pass'
    )

    out = workdir / f"calib_overrides_{tag}.py"
    out.write_text("\n".join(lines) + "\n")
    return out

# ===========================
# Trial + metric
# ===========================

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
    process_yaml: Path
    postproc_yaml: Path
    workdir: Path

def sample_params(trial: optuna.trial.Trial) -> dict:
    return {
        "star.det.threshold": trial.suggest_float("star.det.threshold", 5.0, 8.0),
        "star.det.incMult":  trial.suggest_float("star.det.incMult", 0.8, 3.5),
        "star.sel.snrMin":   trial.suggest_float("star.sel.snrMin", 8.0, 25.0),
        "ap.radii.choice":   trial.suggest_categorical("ap.radii.choice", ["8,12", "10,14", "12,16"]),
        "astro.sel.doSNR":   trial.suggest_categorical("astro.sel.doSNR", [False, True]),
        "astro.sel.snrMin":  trial.suggest_float("astro.sel.snrMin", 8.0, 25.0),
        "photo.sel.snrMin":  trial.suggest_float("photo.sel.snrMin", 10.0, 25.0),
    }

def run_postproc(ctx, trial_chain: str, tag: str, good_visits: list[int]) -> str:
    ts_run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_run = f"{trial_chain}/{ts_run}"

    where = (
        f"instrument='{ctx.instr}' AND detector={ctx.det} "
        f"AND exposure.observation_type='science' "
        f"AND visit IN ({','.join(map(str, good_visits))})"
    )
    cmd = [
        "pipetask","run",
        "-b", str(ctx.repo),
        "-i", trial_chain,          # <— only the trial chain
        "-o", out_run,              # <— fresh RUN under the chain
        "-p", str(ctx.postproc_yaml),
        "--register-dataset-types",
        "-j", str(ctx.jobs),
        "-d", where,
    ]
    try:
        run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        log_failure(ctx.workdir, f"{tag}-postproc", e, extra={"visit": "", "cmd": " ".join(e.cmd)})
        raise
    return out_run


def evaluate_from_visit_summary(repo: Path, coll: str, instr: str, det: int, visits: List[int]) -> Tuple[float, dict]:
    """Read visitSummary rows for the given visits and compute a score."""
    b = Butler(repo, collections=coll, instrument=instr)
    rows = []
    for v in visits:
        try:
            vs = b.get("visitSummary", dict(instrument=instr, visit=v))
        except Exception:
            continue
        # vs is a Catalog of 1 row (already consolidated across detectors)
        if len(vs) == 0:
            continue
        rec = vs[0]
        def get(field, default=np.nan):
            try:
                return float(rec.get(field))
            except Exception:
                return float(default)
        rows.append(dict(
            visit=v,
            psfSigma=get("psfSigma"),
            astromOffsetStd=get("astromOffsetStd"),
            skyBg=get("skyBg"),
            skyNoise=get("skyNoise"),
            zeroPoint=get("zeroPoint"),
            magLim=get("magLim"),
        ))

    if not rows:
        return float("nan"), {}

    # robust medians
    psf = robust_median([r["psfSigma"] for r in rows])
    astro = robust_median([r["astromOffsetStd"] for r in rows])   # arcsec
    m5 = robust_median([r["magLim"] for r in rows])               # mag (higher is better)
    sky = robust_median([r["skyNoise"] for r in rows])            # ADU

    # Score to MINIMIZE: lower psf + lower astrom + lower sky, reward higher m5
    # Weights tuned to be roughly comparable scale-wise.
    score = 2.0*psf + 200.0*astro + 0.02*sky - 0.5*m5

    metrics = dict(
        n_rows=len(rows),
        psfSigma_med=psf,
        astromOffsetStd_med=astro,
        skyNoise_med=sky,
        magLim_med=m5,
        score=score,
    )
    return float(score), metrics

def run_trial(ctx: Context, params: dict, tag: str) -> Tuple[str, float, dict]:
    """Run calibrateImage per-visit (skip failures), then postproc + metric from visitSummary."""
    workdir = ctx.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    overrides = write_overrides(workdir, params, tag)
    trial_chain = f"Nickel/run/calib_tune/{tag}"

    base_cmd = [
        "pipetask","run",
        "-b", str(ctx.repo),
        "-i", f"{ctx.postisr_coll},{ctx.calib_chain},refcats",
        "-o", trial_chain,
        "-p", f"{ctx.process_yaml}#calibrateImage",
        "-C", f"calibrateImage:{overrides}",
        "-j", str(ctx.jobs),
    ]

    # register once on first successful/attempted visit
    base_cmd_reg = base_cmd + ["--register-dataset-types"]

    visits_all = sorted(set(ctx.visits) - set(ctx.bad))
    good_visits: List[int] = []
    for i, v in enumerate(visits_all):
        where = (
            f"instrument='{ctx.instr}' AND detector={ctx.det} "
            f"AND exposure.observation_type='science' AND visit IN ({v})"
        )
        cmd = (base_cmd_reg if i == 0 else base_cmd) + ["-d", where]
        try:
            res = run(cmd, check=True)
            good_visits.append(v)
        except subprocess.CalledProcessError as e:
            log_failure(workdir, f"{tag}-v{v}", e, extra={"visit": v, "cmd": " ".join(e.cmd)})
            continue
        except Exception as e:
            log_failure(workdir, f"{tag}-v{v}", e, extra={"visit": v, "traceback": traceback.format_exc()})
            continue

    if not good_visits:
        raise optuna.TrialPruned("All visits failed in this trial")

    # Postprocess the successful visits into a fresh RUN under this chain
    post_run = run_postproc(ctx, trial_chain, tag, good_visits)

    # Evaluate from visitSummary in that postproc RUN
    score, metrics = evaluate_from_visit_summary(ctx.repo, post_run, ctx.instr, ctx.det, good_visits)
    if not np.isfinite(score):
        raise optuna.TrialPruned("Score NaN/inf after visitTable evaluation")

    # breadcrumb
    (workdir / f"{tag}.ok").write_text(f"{trial_chain} ; visits={good_visits} ; post_run={post_run}\n")
    return trial_chain, score, metrics

def make_objective(ctx: Context):
    def objective(trial: optuna.trial.Trial) -> float:
        params = sample_params(trial)
        tag = f"t{trial.number:03d}"
        try:
            out_coll, score, metrics = run_trial(ctx, params, tag)
            trial.set_user_attr("out_coll", out_coll)
            trial.set_user_attr("metrics", metrics)
            trial.set_user_attr("params", params)
            return float(score)
        except optuna.TrialPruned:
            raise
        except subprocess.CalledProcessError as e:
            log_failure(ctx.workdir, tag, e, extra={"cmd": " ".join(e.cmd)})
            raise optuna.TrialPruned(f"pipetask failed (returncode={getattr(e, 'returncode', '?')})")
        except Exception as e:
            log_failure(ctx.workdir, tag, e, extra={"traceback": traceback.format_exc()})
            raise optuna.TrialPruned("Trial failed")
    return objective

# ===========================
# CLI
# ===========================

def main():
    ap = argparse.ArgumentParser(description="Tune calibrateImage; score from visitSummary.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--obs-nickel", required=True)
    ap.add_argument("--instrument", default="Nickel")
    ap.add_argument("--det", type=int, default=0)
    ap.add_argument("--visits", type=int, nargs="+", required=True)
    ap.add_argument("--bad", type=int, nargs="*", default=[1032, 1051, 1052])
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--postproc-yaml", default=None, help="Path to PostProcessing.yaml; if omitted, try common defaults.")
    ap.add_argument("--workdir", default=None, help="Directory for overrides/logs (default: <repo>/tuning_runs)")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    obs  = Path(args.obs_nickel).expanduser().resolve()

    # Discover pipeline YAMLs
    proc_yaml = obs / "pipelines/ProcessCcd.yaml"
    if not proc_yaml.exists():
        raise FileNotFoundError(f"ProcessCcd.yaml not found at {proc_yaml}")

    if args.postproc_yaml:
        postproc_yaml = Path(args.postproc_yaml).expanduser().resolve()
    else:
        candidates = [
            obs / "tuning/pipelines/PostProcessing.yaml",
            obs / "pipelines/PostProcessing.yaml",
        ]
        postproc_yaml = next((p for p in candidates if p.exists()), None)
        if postproc_yaml is None:
            raise FileNotFoundError("Could not find PostProcessing.yaml (tried tuning/pipelines and pipelines).")

    # Inputs
    postisr = find_latest_postisr_collection(repo, instrument=args.instrument)
    calib_chain = "Nickel/calib/current"
    if not collection_exists(repo, calib_chain):
        raise RuntimeError("Expected Nickel/calib/current to exist.")

    print(f"[inputs] postISR: {postisr}")
    print(f"[inputs] calib  : {calib_chain}")
    print(f"[inputs] proc   : {proc_yaml}")
    print(f"[inputs] post   : {postproc_yaml}")

    workdir = Path(args.workdir).expanduser().resolve() if args.workdir else (repo / "tuning_runs")
    ctx = Context(
        repo=repo, obs_nickel=obs, instr=args.instrument, det=args.det,
        visits=args.visits, bad=args.bad, jobs=args.jobs,
        postisr_coll=postisr, calib_chain=calib_chain,
        process_yaml=proc_yaml, postproc_yaml=postproc_yaml,
        workdir=workdir,
    )

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(make_objective(ctx), n_trials=args.trials, show_progress_bar=True)

    if len(study.trials) == 0 or all(t.state != optuna.trial.TrialState.COMPLETE for t in study.trials):
        print("\nNo trials completed successfully (all pruned). Check trial_failures.csv for details.")
        return

    best = {
        "value": study.best_value,
        "params": study.best_trial.params,
        "metrics": study.best_trial.user_attrs.get("metrics", {}),
        "out_coll": study.best_trial.user_attrs.get("out_coll", ""),
    }
    print("\n=== BEST TRIAL ===")
    print(json.dumps(best, indent=2))
    (workdir / "best_params.json").write_text(json.dumps(best, indent=2) + "\n")

if __name__ == "__main__":
    main()
