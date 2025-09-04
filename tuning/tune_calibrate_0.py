#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tune_calibrate_postISR.py

Tune calibrateImage using your EXISTING ISR (postISRCCD) + latest calibs in the repo,
focusing on source selection, aperture correction, astrometry, and photometry.

- Auto-discovers the newest run collection that contains postISRCCD
- Uses Nickel/calib/current and refcats
- Runs only calibrateImage from ProcessCcd.yaml
- Tolerates per-visit failures and continues with the next visit
- Computes simple metrics and minimizes a scalar score
- Writes failures to <repo>/tuning_runs/trial_failures.csv

Example:
  python tune_calibrate_postISR.py \
    --repo "/path/to/repo" \
    --obs-nickel "/path/to/obs_nickel" \
    --visits 1041 1047 1050 1052 \
    --bad 1032 1051 1052 \
    --jobs 1 \
    --trials 12
"""

from __future__ import annotations
import argparse
import csv
import json
import math
import os
import re
import shlex
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict, Any

import numpy as np
import optuna

from lsst.daf.butler import Butler


# ----------------------- small utilities -----------------------

def run(cmd: List[str] | str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    if capture:
        return subprocess.run(cmd, check=check, text=True, capture_output=True)
    return subprocess.run(cmd, check=check)


def robust_rms(x, clip=3.0) -> float:
    x = np.asarray(x, float)
    if x.size == 0 or not np.isfinite(x).any():
        return np.nan
    m = np.nanmedian(x)
    s = 1.4826 * np.nanmedian(np.abs(x - m))
    if not np.isfinite(s) or s == 0:
        s = np.nanstd(x)
    sel = np.abs(x - m) < clip * (s if np.isfinite(s) and s > 0 else 1.0e9)
    y = x[sel]
    return float(np.sqrt(np.nanmean((y - np.nanmean(y))**2))) if y.size else np.nan


def mag_from_njy(njy) -> np.ndarray:
    njy = np.asarray(njy, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 31.4 - 2.5 * np.log10(njy)


def log_failure(workdir: Path, tag: str, error: BaseException, extra: Optional[Dict[str, Any]] = None) -> None:
    log_csv = workdir / "trial_failures.csv"
    log_csv.parent.mkdir(parents=True, exist_ok=True)
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
        if new_file:
            # ensure stable field order
            fieldnames = list(row.keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        else:
            # reuse existing header
            # (simplify by re-reading header)
            f.seek(0)
            # but for append we can't easily read; just write with current row keys
            writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writerow(row)


# ----------------------- repo discovery -----------------------

def _list_collections_cli(repo: Path) -> list[str]:
    """List all collection names using CLI; avoids default-collection pitfalls."""
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
        raise RuntimeError("No collections found in the repo (cannot search for postISRCCD).")
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
        raise RuntimeError("No postISRCCD datasets found in any collection for this instrument.")

    # Convert to run-name strings
    run_names: list[str] = []
    for ref in refs:
        run_name = ref.run if isinstance(ref.run, str) else getattr(ref.run, "collection", None)
        if run_name:
            run_names.append(run_name)
    if not run_names:
        raise RuntimeError("Found postISRCCD refs but could not extract run names.")

    # Unique and sort, preferring Nickel/run/* and trailing timestamps
    run_names = sorted(set(run_names))

    def score(name: str) -> Tuple[int, str, str]:
        m = re.search(r"(\d{8}T?\d{6,})Z?$", name)
        ts = m.group(1) if m else ""
        return (1 if name.startswith("Nickel/run/") else 0, ts, name)

    run_names.sort(key=score, reverse=True)
    print("[postISR candidates] top 5:", run_names[:5])
    return run_names[0]


# ----------------------- metrics -----------------------

def _butler_get_first(butler: Butler, dataset_types: list[str], dataId: dict):
    for dt in dataset_types:
        try:
            return butler.get(dt, dataId=dataId)
        except Exception:
            continue
    return None


def measure_metrics(repo: Path, out_coll: str, instrument: str, visits: Iterable[int], det: int = 0) -> Dict[str, Any]:
    """Compute per-visit metrics from outputs and aggregate by mean (ignore NaNs)."""
    b = Butler(repo, instrument=instrument, collections=out_coll)
    results = []

    for visit in visits:
        dataId = dict(instrument=instrument, detector=det, visit=visit)

        # Basic source catalog
        try:
            src = b.get("src", dataId=dataId)
        except Exception:
            # no outputs for this visit in this trial
            continue

        # PSF star footprints (optional)
        psf_sc = _butler_get_first(
            b,
            ["psf_stars_footprints_detector", "psf_stars_footprints", "initial_psf_stars_footprints_detector"],
            dataId,
        )

        # Astrometry/photometry matches (dataset names vary by stack/config)
        astrom_matches = _butler_get_first(
            b,
            ["astrometry_matches", "initial_astrometry_match_detector", "initial_astrometry_match"],
            dataId,
        )
        phot_matches = _butler_get_first(
            b,
            ["photometry_matches", "initial_photometry_match_detector", "initial_photometry_match"],
            dataId,
        )

        # ApCorr RMS between 12px aperture and PSF fluxes (PSF stars and final stars)
        def apcorr_rms(cat) -> float:
            if cat is None:
                return np.nan
            ap = cat.schema.find("base_CircularApertureFlux_12_0_0_flux")
            psf = cat.schema.find("slot_PsfFlux_flux")
            if not ap or not psf:
                return np.nan
            a = cat.get(ap.key)
            p = cat.get(psf.key)
            good = np.isfinite(a) & np.isfinite(p) & (a > 0) & (p > 0)
            if not np.any(good):
                return np.nan
            return robust_rms(mag_from_njy(a[good]) - mag_from_njy(p[good]))

        ap1_rms = apcorr_rms(psf_sc)
        ap2_rms = apcorr_rms(src)

        # Astrometry RMS (mas) from matches
        astro_rms = np.nan
        astro_out = np.nan
        n_match = 0
        if astrom_matches is not None and len(astrom_matches) > 0:
            seps = []
            for m in astrom_matches:
                try:
                    s = m["src"]
                    r = m["ref"]
                    sep = s.getCoord().separation(r.getCoord()).asRadians()
                    seps.append(sep * (180.0 / math.pi) * 3600.0 * 1000.0)  # mas
                except Exception:
                    pass
            if seps:
                seps = np.array(seps, float)
                astro_rms = robust_rms(seps)
                med = np.nanmedian(seps)
                sigma = 1.4826 * np.nanmedian(np.abs(seps - med))
                astro_out = float(np.mean(np.abs(seps - med) > 3 * max(sigma, 1e-9)))
                n_match = int(len(seps))

        # Photometric ZP scatter from phot matches (using calibrated PSF mag - ref mag)
        zp_sigma = np.nan
        phot_spatial = np.nan
        if phot_matches is not None and len(phot_matches) > 0:
            # need PSF flux slot field from src schema
            psf_flux_key = src.schema.find("slot_PsfFlux_flux")
            if psf_flux_key:
                resid = []
                for m in phot_matches:
                    try:
                        s = m["src"]
                        r = m["ref"]
                        cal_flux = s.get(psf_flux_key.key)  # in nJy after PhotoCalib
                        src_mag = mag_from_njy(cal_flux)
                        # pick any plausible ref mag key
                        ref_mag = None
                        for k in ("photometry_gaap_aper0_mag", "r_mag", "i_mag", "g_mag", "phot_g_mean_mag"):
                            if k in r.schema:
                                ref_mag = r[k]
                                break
                        if ref_mag is None:
                            continue
                        if np.isfinite(src_mag) and np.isfinite(ref_mag):
                            resid.append(float(src_mag - ref_mag))
                    except Exception:
                        pass
                resid = np.array(resid, float)
                if resid.size > 10:
                    zp_sigma = robust_rms(resid)
                    # simple spatial trend proxy, if x/y exist
                    xk = src.schema.find("x")
                    yk = src.schema.find("y")
                    if xk and yk:
                        n = min(len(resid), len(src))
                        X = np.c_[np.ones(n), src.get(xk.key)[:n], src.get(yk.key)[:n]]
                        beta, *_ = np.linalg.lstsq(X, resid[:n], rcond=None)
                        fit = X @ beta
                        phot_spatial = robust_rms(resid[:n] - fit)

        results.append(dict(
            visit=visit,
            apcorr1_rms_mag=ap1_rms,
            apcorr2_rms_mag=ap2_rms,
            astrom_rms_mas=astro_rms,
            astrom_outlier_frac=astro_out,
            n_astrom_matches=n_match,
            zp_sigma_mag=zp_sigma,
            phot_spatial_rms_mag=phot_spatial,
        ))

    def mean(name):
        if not results:
            return np.nan
        arr = np.array([r[name] for r in results], float)
        return float(np.nanmean(arr)) if arr.size else np.nan

    agg = dict(
        N=len(results),
        apcorr1_rms_mag=mean("apcorr1_rms_mag"),
        apcorr2_rms_mag=mean("apcorr2_rms_mag"),
        astrom_rms_mas=mean("astrom_rms_mas"),
        astrom_outlier_frac=mean("astrom_outlier_frac"),
        n_astrom_matches=mean("n_astrom_matches"),
        zp_sigma_mag=mean("zp_sigma_mag"),
        phot_spatial_rms_mag=mean("phot_spatial_rms_mag"),
    )
    return agg


def evaluate_metric(metrics: Dict[str, Any]) -> Optional[float]:
    """Turn metrics dict into a scalar score (lower is better)."""
    if metrics.get("N", 0) <= 0:
        return None

    # penalties for missing values
    astrom = metrics.get("astrom_rms_mas", np.nan)
    zp = metrics.get("zp_sigma_mag", np.nan)
    ap2 = metrics.get("apcorr2_rms_mag", np.nan)
    spat = metrics.get("phot_spatial_rms_mag", np.nan)
    nm = metrics.get("n_astrom_matches", 0.0)

    # Replace NaNs with big penalties
    astrom = astrom if np.isfinite(astrom) else 1.0e6
    zp = zp if np.isfinite(zp) else 1.0
    ap2 = ap2 if np.isfinite(ap2) else 1.0
    spat = spat if np.isfinite(spat) else 1.0

    # Combine: astrom in mas + 1000x photometric scatters, reward matches
    score = (
        astrom
        + 1000.0 * (zp + ap2 + spat)
        - 0.1 * (nm if np.isfinite(nm) else 0.0)
    )
    return float(score)


# ----------------------- tuning core -----------------------

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
    workdir: Path  # <repo>/tuning_runs


def write_overrides(params: dict, out_dir: Path, tag: str) -> Path:
    """Create a calibrateImage override file for this trial."""
    out_dir.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []

    # ---------- SOURCE DETECTION (final star pass only) ----------
    thr = float(params.get("star.det.threshold", 5.0))
    mult = float(params.get("star.det.incMult", 2.0))
    lines += [
        f"try:\n    config.star_detection.thresholdValue = {thr:.3f}\nexcept Exception:\n    pass",
        f"try:\n    config.star_detection.includeThresholdMultiplier = {mult:.3f}\nexcept Exception:\n    pass",
    ]

    # ---------- SOURCE SELECTION (final catalog used downstream) ----------
    star_snr = float(params.get("star.sel.snrMin", 10.0))
    lines += [
        "try:\n    config.star_selector['science'].doSignalToNoise = True\nexcept Exception:\n    pass",
        f"try:\n    config.star_selector['science'].signalToNoise.minimum = {star_snr:.3f}\nexcept Exception:\n    pass",
    ]

    # ---------- APERTURE CHOICES ----------
    radii_str = params.get("ap.radii.choice", "12,16")
    try:
        radii_vals = [float(x) for x in str(radii_str).split(",")]
    except Exception:
        radii_vals = [12.0, 16.0]
    radii_list = ", ".join(f"{r:.1f}" for r in radii_vals)
    lines += [
        f"try:\n    config.star_measurement.plugins['base_CircularApertureFlux'].radii = [{radii_list}]\nexcept Exception:\n    pass",
    ]

    # ---------- APERTURE CORRECTION STAR SELECTOR ----------
    ap_do_snr = bool(params.get("apcorr.sel.doSNR", True))
    ap_snr_min = float(params.get("apcorr.sel.snrMin", 12.0))
    lines += [
        f"try:\n    config.measure_aperture_correction.sourceSelector['science'].doSignalToNoise = {str(ap_do_snr)}\nexcept Exception:\n    pass",
        f"try:\n    config.measure_aperture_correction.sourceSelector['science'].signalToNoise.minimum = {ap_snr_min:.3f}\nexcept Exception:\n    pass",
    ]

    # --- ASTROMETRY ---
    # remove: astro_doIso = bool(params.get("astro.sel.doIso", False))
    astro_doSNR = bool(params.get("astro.sel.doSNR", False))
    astro_snr   = float(params.get("astro.sel.snrMin", 10.0))
    wcs_order   = int(params.get("astro.wcs.order", 1))

    lines += [
        # harmless if attribute absent in this stack
        f"try:\n    config.astrometry.wcsFitter.order = {wcs_order}\nexcept Exception:\n    pass",
        # FORCE isolation off so we never require deblend_nChild
        "try:\n    config.astrometry.sourceSelector['science'].doIsolated = False\nexcept Exception:\n    pass",
        "try:\n    config.astrometry.sourceSelector['science'].doRequirePrimary = False\nexcept Exception:\n    pass",
        f"try:\n    config.astrometry.sourceSelector['science'].doSignalToNoise = {str(astro_doSNR)}\nexcept Exception:\n    pass",
        f"try:\n    config.astrometry.sourceSelector['science'].signalToNoise.minimum = {astro_snr:.3f}\nexcept Exception:\n    pass",
    ]


    # ---------- PHOTOMETRY (PhotoCal) ----------
    photo_order = int(params.get("photo.order", 0))
    photo_snr = float(params.get("photo.sel.snrMin", 10.0))
    lines += [
        # different stacks hang 'order' in different places; try a few
        (
            "try:\n"
            f"    config.photometry.photoCalibOrder = {photo_order}\n"
            "except Exception:\n"
            "    try:\n"
            f"        config.photometry.solver.order = {photo_order}\n"
            "    except Exception:\n"
            "        try:\n"
            f"            config.photometry.fit.order = {photo_order}\n"
            "        except Exception:\n"
            "            pass"
        ),
        # Disable color terms unless a photoCatName is provided; avoids validation error
        "try:\n    config.photometry.applyColorTerms = False\nexcept Exception:\n    pass",
        "try:\n    config.photometry.match.sourceSelection.doSignalToNoise = True\nexcept Exception:\n    pass",
        f"try:\n    config.photometry.match.sourceSelection.signalToNoise.minimum = {photo_snr:.3f}\nexcept Exception:\n    pass",
        "try:\n    config.photometry.match.sourceSelection.doRequirePrimary = False\nexcept Exception:\n    pass",
        "try:\n    config.photometry.match.sourceSelection.doUnresolved = False\nexcept Exception:\n    pass",
    ]

    # ---------- Ensure matches are persisted for metrics ----------
    lines.append(
        'try:\n'
        '    config.optional_outputs = list(sorted(set(list(getattr(config, "optional_outputs", [])) + '
        '        ["psf_stars","psf_stars_footprints","astrometry_matches","photometry_matches"])))\n'
        'except Exception:\n'
        '    pass'
    )

    out = out_dir / f"calib_overrides_{tag}.py"
    out.write_text("\n".join(lines) + "\n")
    return out


def run_trial(ctx: Context, params: dict, tag: str) -> Tuple[str, float, Dict[str, Any]]:
    """Run one trial; visits are run independently and failures are logged."""
    repo = str(ctx.repo)
    pipe = str(ctx.pipeline_yaml)
    postisr_coll = ctx.postisr_coll
    calib_chain = ctx.calib_chain
    jobs = ctx.jobs
    visits_all = sorted(set(ctx.visits) - set(ctx.bad))
    workdir = ctx.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    # 1) overrides for this trial
    override_py = write_overrides(params, workdir, tag)

    # 2) output collection per trial
    out_coll = f"Nickel/run/calib_tune/{tag}"

    # 3) base pipetask command (we add -d per visit)
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
        where = f"instrument='Nickel' AND exposure.observation_type='science' AND visit IN ({v})"
        cmd = (base_cmd_reg if i == 0 else base_cmd) + ["-d", where]
        try:
            run(cmd, check=True)
            good_visits.append(v)
        except subprocess.CalledProcessError as e:
            log_failure(workdir, f"{tag}-v{v}", e, extra={"visit": v, "cmd": " ".join(e.cmd)})
            continue
        except Exception as e:
            log_failure(workdir, f"{tag}-v{v}", e, extra={"visit": v, "traceback": traceback.format_exc()})
            continue

    if not good_visits:
        raise optuna.TrialPruned("All visits failed in this trial")

    # 4) compute metrics from whatever succeeded
    metrics = measure_metrics(ctx.repo, out_coll, ctx.instr, good_visits, det=ctx.det)
    score = evaluate_metric(metrics)
    if score is None or not np.isfinite(score):
        raise optuna.TrialPruned("Metric is None/NaN after successful visits")

    # breadcrumb
    (workdir / f"{tag}.ok").write_text(f"{out_coll} ; visits={good_visits}\n")

    return out_coll, float(score), metrics


def sample_params(trial: optuna.Trial) -> Dict[str, Any]:
    """Parameter space focused on selection, apcorr, astrometry, photometry."""
    params = {
        # Final star-detection thresholds
        "star.det.threshold": trial.suggest_float("star.det.threshold", 4.5, 7.5),
        "star.det.incMult": trial.suggest_float("star.det.incMult", 2.0, 4.0),

        # Star selection S/N
        "star.sel.snrMin": trial.suggest_float("star.sel.snrMin", 10.0, 25.0),

        # Aperture radii (affects apcorr & flux consistency)
        "ap.radii.choice": trial.suggest_categorical("ap.radii.choice", ["8,12", "12,16", "8,12,16"]),

        # Aperture-correction star selector
        "apcorr.sel.doSNR": trial.suggest_categorical("apcorr.sel.doSNR", [True, False]),
        "apcorr.sel.snrMin": trial.suggest_float("apcorr.sel.snrMin", 12.0, 30.0),

        # Astrometry selector
        "astro.wcs.order": trial.suggest_int("astro.wcs.order", 1, 3),  # skipped if not supported
        "astro.sel.doSNR": trial.suggest_categorical("astro.sel.doSNR", [True, False]),
        "astro.sel.snrMin": trial.suggest_float("astro.sel.snrMin", 8.0, 20.0),

        # Photometry
        "photo.order": trial.suggest_int("photo.order", 0, 1),
        "photo.sel.snrMin": trial.suggest_float("photo.sel.snrMin", 10.0, 20.0),
    }
    return params


def make_objective(ctx: Context):
    """Optuna objective that runs a trial and prunes on failure, while logging issues."""
    def objective(trial: optuna.Trial) -> float:
        params = sample_params(trial)
        tag = f"t{trial.number:03d}"
        try:
            out_coll, score, metrics = run_trial(ctx, params, tag)
            trial.set_user_attr("output_collection", out_coll)
            trial.set_user_attr("metrics", metrics)
            trial.set_user_attr("params", params)
            return score
        except optuna.TrialPruned:
            raise
        except subprocess.CalledProcessError as e:
            log_failure(ctx.workdir, tag, e, extra={"cmd": " ".join(e.cmd)})
            raise optuna.TrialPruned(f"pipetask failed (returncode={e.returncode})")
        except Exception as e:
            log_failure(ctx.workdir, tag, e, extra={"traceback": traceback.format_exc()})
            raise optuna.TrialPruned("Trial failed during preparation/execution")
    return objective


# ----------------------- CLI -----------------------

def main():
    ap = argparse.ArgumentParser(description="Tune calibrateImage using existing ISR + latest calibs.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--obs-nickel", required=True)
    ap.add_argument("--instrument", default="Nickel")
    ap.add_argument("--det", type=int, default=0)
    ap.add_argument("--visits", type=int, nargs="+", required=True)
    ap.add_argument("--bad", type=int, nargs="*", default=[1032, 1051, 1052])
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--trials", type=int, default=12)
    args = ap.parse_args()

    repo = Path(args.repo).expanduser()
    obs = Path(args.obs_nickel).expanduser()
    proc_yaml = obs / "pipelines/ProcessCcd.yaml"

    # Discover inputs
    postisr = find_latest_postisr_collection(repo, instrument=args.instrument)
    calib_chain = "Nickel/calib/current" if collection_exists(repo, "Nickel/calib/current") else ""
    if not calib_chain:
        raise RuntimeError("Expected Nickel/calib/current to exist. Please chain your curated/cp runs first.")

    print(f"[inputs] postISR: {postisr}")
    print(f"[inputs] calib  : {calib_chain}")
    print(f"[inputs] pipe   : {proc_yaml}")

    workdir = repo / "tuning_runs"
    workdir.mkdir(parents=True, exist_ok=True)

    ctx = Context(
        repo=repo,
        obs_nickel=obs,
        instr=args.instrument,
        det=args.det,
        visits=args.visits,
        bad=args.bad,
        jobs=args.jobs,
        postisr_coll=postisr,
        calib_chain=calib_chain,
        pipeline_yaml=proc_yaml,
        workdir=workdir,
    )

    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    study.optimize(make_objective(ctx), n_trials=args.trials, show_progress_bar=True)

    best = {
        "value": study.best_value,
        "params": study.best_trial.params,
        "metrics": study.best_trial.user_attrs.get("metrics", {}),
        "output_collection": study.best_trial.user_attrs.get("output_collection", ""),
    }
    print("\n=== BEST TRIAL ===")
    print(json.dumps(best, indent=2))

    (ctx.workdir / "best_params.json").write_text(json.dumps(best, indent=2) + "\n")


if __name__ == "__main__":
    main()
