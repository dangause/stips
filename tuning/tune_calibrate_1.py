#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tune calibrateImage using EXISTING ISR + latest calibs in the repo.

- Finds the newest collection that contains postISRCCD (your latest ISR run)
- Uses Nickel/calib/current and refcats
- Runs only calibrateImage from ProcessCcd.yaml
- Focuses knobs on source selection, aperture correction, astrometry, photometry
- Each visit is run independently; failures are logged and skipped
- Trials with no successful visits or NaN metrics are pruned
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
from datetime import datetime, UTC
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import numpy as np
import optuna

# LSST
from lsst.daf.butler import Butler

# ------------- Small helpers -------------
def run(cmd: List[str] | str, check=True, capture=False) -> subprocess.CompletedProcess:
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    if capture:
        return subprocess.run(cmd, check=check, text=True, capture_output=True)
    else:
        return subprocess.run(cmd, check=check)

def robust_rms(x, clip=3.0):
    x = np.asarray(x, float)
    if x.size == 0 or not np.isfinite(x).any():
        return np.nan
    m = np.nanmedian(x)
    s = 1.4826 * np.nanmedian(np.abs(x - m))
    sigma = s if s > 0 else np.nanstd(x)
    sel = np.abs(x - m) < clip * sigma if np.isfinite(sigma) else np.ones_like(x, dtype=bool)
    y = x[sel]
    return float(np.sqrt(np.nanmean((y - np.nanmean(y)) ** 2))) if y.size else np.nan

def mag_from_njy(njy):
    njy = np.asarray(njy, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 31.4 - 2.5 * np.log10(njy)

def log_failure(ctx: "Context", tag: str, error: BaseException, extra: dict | None = None):
    log_csv = ctx.workdir / "trial_failures.csv"
    log_csv.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "trial_tag": tag,
        "exception": type(error).__name__,
        "message": str(error),
    }
    if extra:
        for k, v in extra.items():
            row[str(k)] = str(v)
    new_file = not log_csv.exists()
    with open(log_csv, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if new_file:
            w.writeheader()
        w.writerow(row)

# ------------- Repo discovery -------------
def _list_collections_cli(repo: Path) -> list[str]:
    """List all collection names using the CLI, skipping headers/blank lines."""
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
    """
    Return newest run collection that contains postISRCCD for this instrument.
    """
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

# ------------- Metrics -------------
def _get_first_key(schema, names: list[str]):
    for n in names:
        try:
            f = schema.find(n)
            if f is not None:
                return f.key
        except Exception:
            pass
    return None

def _get_col_from_source_catalog(cat, name: str):
    try:
        f = cat.schema.find(name)
        if f is not None:
            return cat.get(f.key)
    except Exception:
        pass
    return None

def _get_col(cat, name: str):
    """Return a numpy array column for either SourceCatalog or Astropy Table; else None."""
    # SourceCatalog path
    if hasattr(cat, "schema"):
        arr = _get_col_from_source_catalog(cat, name)
        if arr is not None:
            return np.asarray(arr, dtype=float)
    # Astropy Table (or dict-like) path
    try:
        if hasattr(cat, "colnames"):
            if name in cat.colnames:
                return np.asarray(cat[name], dtype=float)
        else:
            # Very defensive: treat as mapping
            if name in cat:
                return np.asarray(cat[name], dtype=float)
    except Exception:
        pass
    return None

def _first_existing_col(cat, names: list[str]):
    for n in names:
        arr = _get_col(cat, n)
        if arr is not None:
            return arr
    return None

def _pick_ap_and_psf(cat):
    """Return (ap_flux_array, psf_flux_array) or (None, None)."""
    ap_candidates = [
        "base_CircularApertureFlux_12_0_0_instFlux",
        "base_CircularApertureFlux_12_0_0_flux",
        # Common fallbacks (any circular aperture flux)
        "base_CircularApertureFlux_12_instFlux",
        "base_CircularApertureFlux_12_flux",
    ]
    psf_candidates = [
        "slot_PsfFlux_instFlux",
        "slot_PsfFlux_flux",
        "base_PsfFlux_instFlux",
        "base_PsfFlux_flux",
    ]
    ap = _first_existing_col(cat, ap_candidates)
    ps = _first_existing_col(cat, psf_candidates)
    return ap, ps

def _try_get(butler, dsname, dataId):
    try:
        return butler.get(dsname, dataId=dataId)
    except Exception:
        return None

def _prefer_one(butler, dataId, names: list[str]):
    for n in names:
        obj = _try_get(butler, n, dataId)
        if obj is not None:
            return obj
    return None

def evaluate_metric(ctx: "Context", out_coll: str):
    """
    Build metrics ONLY from initial_* products when present:
      - ap_psf_diff_rms_mag  from initial_stars_detector (or fallbacks)
      - astrom_rms_mas       from initial_* astrometry matches (fallback to non-initial)
      - zp_sigma_mag         from initial_* photometry matches (fallback to non-initial)
      - seeing_arcsec        optional, from initial_pvi (ignored in score)

    Score = mean of available scaled terms:
      ap_psf_diff_rms_mag/0.02, astrom_rms_mas/50, zp_sigma_mag/0.02
    """
    b = Butler(ctx.repo, instrument=ctx.instr, collections=out_coll)
    visits = sorted(set(ctx.visits) - set(ctx.bad))

    ap_diffs, astro_rmss, zp_sigmas = [], [], []
    seeing_vals = []

    for v in visits:
        dataId = dict(instrument=ctx.instr, detector=ctx.det, visit=v)

        # ---- stars catalog (prefer initial_stars_detector) ----
        stars = _prefer_one(
            b, dataId,
            ["initial_stars_detector", "initial_stars",
             "star_stars_detector", "star_stars"]
        )

        if stars is not None:
            ap, ps = _pick_ap_and_psf(stars)
            if ap is not None and ps is not None:
                good = np.isfinite(ap) & np.isfinite(ps) & (ap > 0) & (ps > 0)
                if np.any(good):
                    dmag = 2.5 * np.log10(ap[good] / ps[good])
                    ap_diffs.append(robust_rms(dmag))

        # ---- astrometry matches (prefer initial_*) ----
        astrom = _prefer_one(
            b, dataId,
            ["initial_astrometry_matches", "initial_astrometry_match_detector",
             "astrometry_matches", "astrometry_match_detector"]
        )
        if astrom is not None:
            seps = []
            for m in astrom:
                try:
                    s = m["src"]; r = m["ref"]
                    sep = s.getCoord().separation(r.getCoord()).asRadians()
                    seps.append(sep * (180/np.pi)*3600*1000.0)
                except Exception:
                    pass
            if seps:
                astro_rmss.append(robust_rms(np.asarray(seps, dtype=float)))

        # ---- photometry matches (prefer initial_*) ----
        phot = _prefer_one(
            b, dataId,
            ["initial_photometry_matches", "initial_photometry_match_detector",
             "photometry_matches", "photometry_match_detector"]
        )
        if phot is not None and stars is not None:
            ps = _first_existing_col(
                stars,
                ["slot_PsfFlux_instFlux", "slot_PsfFlux_flux",
                 "base_PsfFlux_instFlux", "base_PsfFlux_flux"]
            )
            if ps is not None:
                resid = []
                for m in phot:
                    try:
                        s = m["src"]; r = m["ref"]
                        f = s.get(m["src"].schema.find("slot_PsfFlux_instFlux").key) if hasattr(s, "schema") else None
                        # if the match src is not the same object type as 'stars', fall back to 'ps' via name
                        if f is None:
                            # try generic access via known names on the matched src
                            f = None
                            for nm in ("slot_PsfFlux_instFlux", "slot_PsfFlux_flux", "base_PsfFlux_instFlux", "base_PsfFlux_flux"):
                                try:
                                    if hasattr(s, "schema"):
                                        k = s.schema.find(nm).key
                                        f = s.get(k)
                                        break
                                    elif hasattr(s, "get"):
                                        # if ref-like row; skip
                                        pass
                                except Exception:
                                    pass
                        if f is None or not (np.isfinite(f) and f > 0):
                            continue

                        # pick a reference magnitude
                        ref_mag = None
                        for kname in ("photometry_gaap_aper0_mag","i_mag","r_mag","g_mag","Vmag","Imag"):
                            try:
                                if hasattr(r, "schema"):
                                    if r.schema.find(kname) is not None:
                                        ref_mag = r[kname]; break
                                elif kname in r.schema:  # some ref tables expose dict-like
                                    ref_mag = r[kname]; break
                            except Exception:
                                pass
                        if ref_mag is None or not np.isfinite(ref_mag):
                            continue

                        m_rel = -2.5 * math.log10(float(f))
                        resid.append(float(m_rel - float(ref_mag)))
                    except Exception:
                        pass
                if len(resid) >= 8:
                    zp_sigmas.append(robust_rms(np.asarray(resid, dtype=float)))

        # ---- optional seeing from initial_pvi ----
        try:
            exp = b.get("initial_pvi", dataId=dataId)
            psf = exp.getPsf()
            if psf is not None:
                import lsst.afw.geom as afwGeom
                shape = psf.computeShape(afwGeom.Point2D(exp.getBBox().getCenter()))
                sigma_pix = float(shape.getDeterminantRadius())
                fwhm_pix = 2.355 * sigma_pix
                scale_as_per_pix = float(exp.getWcs().pixelScale().asArcseconds()) if exp.getWcs() else 1.0
                seeing_vals.append(fwhm_pix * scale_as_per_pix)
        except Exception:
            pass

    def mean_or_nan(x):
        x = np.asarray(x, float)
        return float(np.nanmean(x)) if x.size else np.nan

    metrics = dict(
        ap_psf_diff_rms_mag = mean_or_nan(ap_diffs),
        astrom_rms_mas      = mean_or_nan(astro_rmss),
        zp_sigma_mag        = mean_or_nan(zp_sigmas),
        seeing_arcsec       = mean_or_nan(seeing_vals),
        n_visits_used       = len(visits),
    )

    # Build score from whatever is available
    terms = []
    if np.isfinite(metrics["ap_psf_diff_rms_mag"]):
        terms.append(metrics["ap_psf_diff_rms_mag"] / 0.02)
    if np.isfinite(metrics["astrom_rms_mas"]):
        terms.append(metrics["astrom_rms_mas"] / 50.0)
    if np.isfinite(metrics["zp_sigma_mag"]):
        terms.append(metrics["zp_sigma_mag"] / 0.02)

    score = float(np.nanmean(terms)) if terms else np.nan

    # If still NaN, dump a quick debug file but do NOT crash the trial runner.
    if not np.isfinite(score) and hasattr(ctx, "workdir"):
        try:
            (ctx.workdir / "last_metric_debug.json").write_text(json.dumps({
                "ap_terms": [float(x) for x in np.asarray(ap_diffs, float)],
                "astro_terms": [float(x) for x in np.asarray(astro_rmss, float)],
                "phot_terms": [float(x) for x in np.asarray(zp_sigmas, float)],
                "seeing_vals": [float(x) for x in np.asarray(seeing_vals, float)],
            }, indent=2))
        except Exception:
            pass

    return score, metrics


# ------------- Config + Trial Runner -------------
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
    workdir: Path

def write_overrides(out_dir: Path, params: dict, tag: str) -> Path:
    """
    Overrides focused on source selection, apcorr, astrometry, and photometry.
    Avoids attributes that caused earlier crashes.
    """
    lines: list[str] = []

    # ---------- SOURCE DETECTION (final star pass only) ----------
    thr = float(params.get("star.det.threshold", 5.0))
    mult = float(params.get("star.det.incMult", 2.0))
    lines += [
        f"config.star_detection.thresholdValue = {thr:.3f}",
        f"config.star_detection.includeThresholdMultiplier = {mult:.3f}",
    ]

    # ---------- SOURCE SELECTION (final catalog used downstream) ----------
    star_snr = float(params.get("star.sel.snrMin", 10.0))
    lines += [
        "config.star_selector['science'].doSignalToNoise = True",
        f"config.star_selector['science'].signalToNoise.minimum = {star_snr:.3f}",
    ]

    # ---------- APERTURE CHOICES (impacts apcorr and PSF/Calib flux consistency) ----------
    radii_str = params.get("ap.radii.choice", "12")
    try:
        radii_vals = [float(x) for x in str(radii_str).split(",") if x.strip()]
    except Exception:
        radii_vals = [12.0]
    radii_list = ", ".join(f"{r:.1f}" for r in radii_vals)
    lines += [
        f"config.star_measurement.plugins['base_CircularApertureFlux'].radii = [{radii_list}]",
        # leave psf_source_measurement apertures as defaults per CalibrateImageConfig
    ]

    # ---------- APERTURE CORRECTION STAR SELECTOR ----------
    ap_do_snr = bool(params.get("apcorr.sel.doSNR", True))
    ap_snr_min = float(params.get("apcorr.sel.snrMin", 12.0))
    lines += [
        f"config.measure_aperture_correction.sourceSelector['science'].doSignalToNoise = {str(bool(ap_do_snr))}",
        f"config.measure_aperture_correction.sourceSelector['science'].signalToNoise.minimum = {ap_snr_min:.3f}",
        # keep flags.good/bad as per defaults (uses calib_psf_used)
    ]

    # ---------- ASTROMETRY SELECTOR ----------
    # Do NOT touch wcsFitter.order (FitAffineWcs has no 'order'); leave retarget as default.
    # astro_do_iso = bool(params.get("astro.sel.doIso", False))  # deblend_nChild may be missing → default False
    astro_do_snr = bool(params.get("astro.sel.doSNR", False))
    astro_snr = float(params.get("astro.sel.snrMin", 10.0))
    lines += [
        # f"config.astrometry.sourceSelector['science'].doIsolated = {str(bool(astro_do_iso))}",
        "config.astrometry.sourceSelector['science'].doRequirePrimary = False",
        f"config.astrometry.sourceSelector['science'].doSignalToNoise = {str(bool(astro_do_snr))}",
        f"config.astrometry.sourceSelector['science'].signalToNoise.minimum = {astro_snr:.3f}",
    ]

    # ---------- PHOTOMETRY (PhotoCal) ----------
    # Avoid applyColorTerms=True unless photoCatName is set; force False.
    photo_snr = float(params.get("photo.sel.snrMin", 10.0))
    lines += [
        "config.photometry.applyColorTerms = False",
        "config.photometry.match.sourceSelection.doSignalToNoise = True",
        f"config.photometry.match.sourceSelection.signalToNoise.minimum = {photo_snr:.3f}",
        "config.photometry.match.sourceSelection.doRequirePrimary = False",
        "config.photometry.match.sourceSelection.doUnresolved = False",
    ]

    # ---------- Persist matches for metrics ----------
    lines.append(
        'config.optional_outputs = list(sorted(set(config.optional_outputs) | {"photometry_matches","astrometry_matches"}))'
    )

    out = out_dir / f"calib_overrides_{tag}.py"
    out.write_text("\n".join(lines) + "\n")
    return out

def run_trial(ctx: Context, params: dict, tag: str) -> Tuple[str, float, dict]:
    """
    Run one trial by looping over visits independently.
    Failures on a visit are logged and skipped; successes are accumulated
    into the same output run collection, then we compute a metric
    over whatever was produced.
    """
    repo = ctx.repo
    pipe = ctx.pipeline_yaml
    postisr_coll = ctx.postisr_coll
    calib_chain = ctx.calib_chain
    jobs = ctx.jobs
    visits_all = sorted(set(ctx.visits) - set(ctx.bad))
    workdir = ctx.workdir

    override_py = write_overrides(workdir, params, tag)
    out_coll = f"Nickel/run/calib_tune/{tag}"

    base_cmd = [
        "pipetask", "run",
        "-b", str(repo),
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
            log_failure(ctx, f"{tag}-v{v}", e, extra={"visit": v, "cmd": " ".join(e.cmd)})
            continue
        except Exception as e:
            log_failure(ctx, f"{tag}-v{v}", e, extra={"visit": v, "traceback": traceback.format_exc()})
            continue

    if not good_visits:
        raise optuna.TrialPruned("All visits failed in this trial")

    score, metrics = evaluate_metric(ctx, out_coll)
    if not (isinstance(score, (int, float)) and np.isfinite(score)):
        raise optuna.TrialPruned("Metric is None/NaN after successful visits")

    (workdir / f"{tag}.ok").write_text(f"{out_coll} ; visits={good_visits}\n")
    return out_coll, float(score), metrics

# ------------- Search space + Objective -------------
def sample_params(trial: optuna.Trial) -> dict:
    return {
        # Source detection (final star pass)
        "star.det.threshold": trial.suggest_float("star.det.threshold", 4.5, 7.5),
        "star.det.incMult": trial.suggest_float("star.det.incMult", 2.0, 4.5),

        # Star selection S/N
        "star.sel.snrMin": trial.suggest_float("star.sel.snrMin", 10.0, 25.0),

        # Aperture radii choices for star_measurement
        "ap.radii.choice": trial.suggest_categorical("ap.radii.choice", ["12", "8,12", "12,16"]),

        # ApCorr selector
        "apcorr.sel.doSNR": trial.suggest_categorical("apcorr.sel.doSNR", [True, False]),
        "apcorr.sel.snrMin": trial.suggest_float("apcorr.sel.snrMin", 10.0, 30.0),

        # Astrometry selector (avoid doIsolated=True by default)
        # "astro.sel.doIso": trial.suggest_categorical("astro.sel.doIso", [False, True]),
        "astro.sel.doSNR": trial.suggest_categorical("astro.sel.doSNR", [False, True]),
        "astro.sel.snrMin": trial.suggest_float("astro.sel.snrMin", 8.0, 25.0),

        # Photometry selector
        "photo.sel.snrMin": trial.suggest_float("photo.sel.snrMin", 10.0, 25.0),
    }

def make_objective(ctx: Context):
    def objective(trial: optuna.Trial):
        params = sample_params(trial)
        tag = f"t{trial.number:03d}"
        try:
            out_coll, score, metrics = run_trial(ctx, params, tag)
            if not np.isfinite(score):
                raise optuna.TrialPruned("Metric is None/NaN after successful visits")
            trial.set_user_attr("output_collection", out_coll)
            trial.set_user_attr("params", params)
            trial.set_user_attr("metrics", metrics)
            trial.set_user_attr("score", float(score))
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

# ------------- CLI -------------
def main():
    ap = argparse.ArgumentParser(description="Tune calibrateImage using existing ISR + latest calibs.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--obs-nickel", required=True)
    ap.add_argument("--instrument", default="Nickel")
    ap.add_argument("--det", type=int, default=0)
    ap.add_argument("--visits", type=int, nargs="+", required=True)
    ap.add_argument("--bad", type=int, nargs="*", default=[1032, 1051, 1052])
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--trials", type=int, default=15)
    args = ap.parse_args()

    repo = Path(args.repo).expanduser()
    obs = Path(args.obs_nickel).expanduser()
    proc_yaml = obs / "pipelines" / "ProcessCcd.yaml"

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

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(make_objective(ctx), n_trials=args.trials, show_progress_bar=True)

    try:
        best = {
            "value": study.best_value,
            "params": study.best_trial.params,
            "metrics": study.best_trial.user_attrs.get("metrics", {}),
            "out_coll": study.best_trial.user_attrs.get("output_collection", ""),
        }
        print("\n=== BEST TRIAL ===")
        print(json.dumps(best, indent=2))
        (workdir / "best_params.json").write_text(json.dumps(best, indent=2) + "\n")
    except ValueError:
        print("\nNo trials completed successfully (all pruned). Check trial_failures.csv for details.", file=sys.stderr)

if __name__ == "__main__":
    main()
