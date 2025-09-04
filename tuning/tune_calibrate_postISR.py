#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tune calibrateImage using EXISTING ISR + latest calibs in the repo.

What it does:
- Finds the newest collection that contains postISRCCD (your latest ISR run)
- Uses Nickel/calib/current and refcats
- Runs only calibrateImage from ProcessCcd.yaml
- Measures PSF/Astrom/Photom metrics and optimizes a simple score

Usage (example):
  python tune_calibrate_existing_isr.py \
    --repo "/Users/dangause/Desktop/lick/lsst/data/nickel/062424" \
    --obs-nickel "/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/obs_nickel" \
    --visits 1041 1047 1050 \
    --bad 1032 1051 1052 \
    --jobs 1 \
    --trials 15
"""

from __future__ import annotations
import argparse, json, math, os, re, shlex, subprocess, sys, tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
import optuna


from lsst.daf.butler import Butler
from lsst.pipe.base import Struct

# ---------- Small helpers ----------
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
    s = 1.4826*np.nanmedian(np.abs(x-m))
    sel = np.abs(x-m) < clip*(s if s>0 else np.nanstd(x))
    y = x[sel]
    return float(np.sqrt(np.nanmean((y-np.nanmean(y))**2))) if y.size else np.nan

def mag_from_njy(njy):
    njy = np.asarray(njy, float)
    with np.errstate(divide='ignore', invalid='ignore'):
        return 31.4 - 2.5*np.log10(njy)

# ---------- Repo discovery ----------
from lsst.daf.butler import Butler

def _all_collection_names(repo: Path) -> list[str]:
    """Return all collection names in the repo."""
    butler = Butler(repo)
    # Each record has .name; filter out weird empties defensively
    return [rec.name for rec in butler.registry.queryCollections() if getattr(rec, "name", "")]

def find_latest_postisr_collection(repo: Path, instrument: str = "Nickel") -> str:
    """
    Return newest run collection that contains postISRCCD for this instrument.

    - Enumerates all collections via CLI (avoids default-collection issues)
    - Queries all postISRCCD DatasetRefs across those collections
    - Collapses to unique run names (strings), then sorts by timestamp
    """
    import re
    from lsst.daf.butler import Butler

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

    # Normalize to run-name strings (DatasetRef.run may already be a str)
    run_names = []
    for ref in refs:
        run_name = ref.run if isinstance(ref.run, str) else getattr(ref.run, "collection", None)
        if run_name:
            run_names.append(run_name)

    if not run_names:
        raise RuntimeError("Found postISRCCD refs but could not extract run names.")

    # Unique the run names
    run_names = sorted(set(run_names))

    # Sort: prefer Nickel/run/* and by trailing timestamp if present
    def score(name: str):
        # matches 20250829T042520Z or 20250829042520 at end
        m = re.search(r"(\d{8}T?\d{6,})Z?$", name)
        ts = m.group(1) if m else ""
        return (name.startswith("Nickel/run/"), ts, name)

    run_names.sort(key=score, reverse=True)

    # Optional: print a few candidates for sanity
    print("[postISR candidates] top 5:", run_names[:5])

    return run_names[0]


# --- replace existing helpers with these ---

import shlex, subprocess
from pathlib import Path

import re, shlex, subprocess
from pathlib import Path

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
        # table header or separators (handle 'Name', 'NAME', etc.)
        if line.lower().startswith("name") or line.startswith("---"):
            continue
        # first column is the collection name
        first = line.split()[0]
        # skip stray headers/labels
        if first.lower() in {"name", "type", "chains", "collection"}:
            continue
        # basic sanity: looks like a collection token (no spaces, allowed chars)
        if not re.match(r"^[A-Za-z0-9_./:-]+$", first):
            continue
        names.append(first)
    return names


def collection_exists(repo: Path, name: str) -> bool:
    return name in _list_collections_cli(repo)


# ---------- Metrics ----------
def measure_metrics(repo: Path, out_coll: str, instrument="Nickel", visits: Iterable[int]=(), det=0):
    """Read outputs from a run (out_coll) and compute metrics aggregated over visits."""
    b = Butler(repo, instrument=instrument, collections=out_coll)
    from lsst.afw.table import SourceCatalog
    results = []

    for visit in visits:
        dataId = dict(instrument=instrument, detector=det, visit=visit)
        # src + optional matches
        try:
            src: SourceCatalog = b.get("src", dataId=dataId)
        except Exception:
            continue

        # PSF star footprints (initial)
        try:
            psf_sc: SourceCatalog = b.get("initial_psf_stars_footprints_detector", dataId=dataId)
        except Exception:
            psf_sc = None

        # astrometry / photometry matches (optional names depend on your pipeline)
        try:
            astrom_matches = b.get("initial_astrometry_match_detector", dataId=dataId)
        except Exception:
            astrom_matches = None
        try:
            phot_matches = b.get("initial_photometry_match_detector", dataId=dataId)
        except Exception:
            phot_matches = None

        # ApCorr #1 RMS on PSF stars
        ap1_rms = np.nan
        if psf_sc is not None:
            ap = psf_sc.schema.find("base_CircularApertureFlux_12_0_0_flux")
            psf = psf_sc.schema.find("slot_PsfFlux_flux")
            if ap and psf:
                a = psf_sc.get(ap.key)
                p = psf_sc.get(psf.key)
                good = np.isfinite(a) & np.isfinite(p) & (a>0) & (p>0)
                ap1_rms = robust_rms(mag_from_njy(a[good]) - mag_from_njy(p[good]))

        # ApCorr #2 RMS on final stars (use src with same columns)
        ap2_rms = np.nan
        ap = src.schema.find("base_CircularApertureFlux_12_0_0_flux")
        psf = src.schema.find("slot_PsfFlux_flux")
        if ap and psf:
            a = src.get(ap.key)
            p = src.get(psf.key)
            good = np.isfinite(a) & np.isfinite(p) & (a>0) & (p>0)
            ap2_rms = robust_rms(mag_from_njy(a[good]) - mag_from_njy(p[good]))

        # Astrometry RMS (mas) from matches
        astro_rms = np.nan
        astro_out = np.nan
        n_match = 0
        if astrom_matches is not None and len(astrom_matches)>0:
            seps = []
            for m in astrom_matches:
                try:
                    s = m["src"]
                    r = m["ref"]
                    sep = s.getCoord().separation(r.getCoord()).asRadians()
                    seps.append(sep * (180/np.pi)*3600*1000.0)
                except Exception:
                    pass
            if seps:
                seps = np.array(seps, float)
                astro_rms = robust_rms(seps)
                med = np.nanmedian(seps)
                sigma = 1.4826*np.nanmedian(np.abs(seps-med))
                astro_out = float(np.mean(np.abs(seps-med) > 3*max(sigma, 1e-9)))
                n_match = int(len(seps))

        # Photometric ZP sigma from phot matches (residual calibrated PSF mag - ref mag)
        zp_sigma = np.nan
        phot_spatial = np.nan
        if phot_matches is not None and len(phot_matches)>0 and psf:
            resid = []
            for m in phot_matches:
                try:
                    s = m["src"]
                    r = m["ref"]
                    cal_flux = s.get(psf.key)  # already nJy after PhotoCalib apply
                    src_mag = mag_from_njy(cal_flux)
                    # choose a ref mag column that exists
                    ref_mag = None
                    for k in ("photometry_gaap_aper0_mag","i_mag","r_mag","g_mag"):
                        if k in r.schema:
                            ref_mag = r[k]; break
                    if ref_mag is None: 
                        continue
                    if np.isfinite(src_mag) and np.isfinite(ref_mag):
                        resid.append(float(src_mag - ref_mag))
                except Exception:
                    pass
            resid = np.array(resid, float)
            if resid.size > 10:
                zp_sigma = robust_rms(resid)
                # crude spatial trend using src x,y if present
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

    # Aggregate means (ignore NaNs)
    def mean(name):
        arr = np.array([r[name] for r in results], float)
        return float(np.nanmean(arr)) if arr.size else np.nan

    return dict(
        N=len(results),
        apcorr1_rms_mag=mean("apcorr1_rms_mag"),
        apcorr2_rms_mag=mean("apcorr2_rms_mag"),
        astrom_rms_mas=mean("astrom_rms_mas"),
        astrom_outlier_frac=mean("astrom_outlier_frac"),
        n_astrom_matches=mean("n_astrom_matches"),
        zp_sigma_mag=mean("zp_sigma_mag"),
        phot_spatial_rms_mag=mean("phot_spatial_rms_mag"),
    )

# ---------- Trial runner (pipetask calibrateImage only) ----------
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

def write_overrides(ctx: Context, params: Dict[str, Any], tag: str) -> Path:
    """Emit a calibrateImage overrides .py with top-level assignments (required for -C)."""
    trial_dir = ctx.workdir / "trials" / tag
    trial_dir.mkdir(parents=True, exist_ok=True)
    ov_path = trial_dir / f"calib_overrides_{tag}.py"

    txt = f"""# Auto-generated overrides for {tag}
# IMPORTANT: This file is executed by pipetask with `config` in scope.
# Do NOT wrap in a function; use top-level assignments only.

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





def run_trial(ctx: Context, params: dict, tag: str) -> tuple[str, dict]:
    """Run pipetask calibrateImage only, return (output_collection, metrics)."""
    out_coll = f"Nickel/run/calib_tune/{tag}"
    overrides = write_overrides(params, Path(tempfile.mkdtemp(prefix="calib_tune_")))
    # Build query: science, not in BAD, subset by visits
    bad_set = set(ctx.bad)
    use_visits = [v for v in ctx.visits if v not in bad_set]
    if not use_visits:
        raise RuntimeError("No visits to run after excluding BAD.")
    visit_list = ",".join(str(v) for v in use_visits)
    # Input collections: latest ISR run + calibs + refcats
    inputs = ",".join([ctx.postisr_coll, ctx.calib_chain, "refcats"])

    # Run *only* calibrateImage from ProcessCcd.yaml
    cmd = [
        "pipetask","run",
        "-b", str(ctx.repo),
        "-i", inputs,
        "-o", out_coll,
        "-p", f"{ctx.pipeline_yaml}#calibrateImage",
        "-C", f"calibrateImage:{overrides}",
        "-d", f"instrument='{ctx.instr}' AND exposure.observation_type='science' AND visit IN ({visit_list})",
        "-j", str(ctx.jobs),
        "--register-dataset-types",
    ]
    run(cmd, check=True)

    metrics = measure_metrics(ctx.repo, out_coll, instrument=ctx.instr, visits=use_visits, det=ctx.det)
    return out_coll, metrics

# ---------- Optuna objective ----------
def make_objective(ctx: Context):
    gates = dict(min_psf=40, min_matches=500, max_zp_sigma=0.015)
    def objective(trial: optuna.Trial) -> float:
        # Focused knobs
        params = {
            # ---- Source detection & selection (final star pass) ----
            "star.det.threshold":  trial.suggest_float("star.det.threshold", 4.0, 8.0),
            "star.det.incMult":   trial.suggest_float("star.det.incMult",   1.5, 3.5),
            "star.sel.snrMin":    trial.suggest_float("star.sel.snrMin",   8.0, 16.0),

            # ---- Aperture choices (for star measurement; affects apcorr) ----
            # choose via string to avoid Optuna tuple warning
            "ap.radii.choice":    trial.suggest_categorical("ap.radii.choice", ["8,12", "12,16", "8,12,16"]),

            # ---- Aperture-correction star selector ----
            "apcorr.sel.doSNR":   trial.suggest_categorical("apcorr.sel.doSNR", [True, False]),
            "apcorr.sel.snrMin":  trial.suggest_float("apcorr.sel.snrMin", 8.0, 30.0),

            # ---- Astrometry ----
            "astro.wcs.order":    trial.suggest_int("astro.wcs.order", 1, 2),
            "astro.sel.doIso":    trial.suggest_categorical("astro.sel.doIso", [True, False]),
            "astro.sel.doSNR":    trial.suggest_categorical("astro.sel.doSNR", [True, False]),
            "astro.sel.snrMin":   trial.suggest_float("astro.sel.snrMin", 8.0, 20.0),
            
            # ---- Photometry ----            
            "photo.order":        trial.suggest_int("photo.order", 0, 1),
            # "photo.colorTerms":   trial.suggest_categorical("photo.colorTerms", [False, True]),
            "photo.sel.snrMin":   trial.suggest_float("photo.sel.snrMin", 8.0, 20.0),
        }


        tag = f"t{trial.number:03d}"
        out_coll, m = run_trial(ctx, params, tag)

        # guardrails
        n_match = m.get("n_astrom_matches", np.nan)
        zp_sig  = m.get("zp_sigma_mag", np.nan)
        if (not np.isnan(n_match) and n_match < 300) or \
        (not np.isnan(zp_sig) and zp_sig > 0.03):
            return 1e8

        # score (lower is better)
        J = 0.0
        if not math.isnan(m.get("astrom_rms_mas", np.nan)):
            J += m["astrom_rms_mas"] * 1.5           # emphasize astrometry RMS
        if not math.isnan(m.get("astrom_outlier_frac", np.nan)):
            J += m["astrom_outlier_frac"] * 200.0    # penalize bad matches
        if not math.isnan(m.get("zp_sigma_mag", np.nan)):
            J += m["zp_sigma_mag"] * 2500.0          # photometric scatter is critical
        if not math.isnan(m.get("phot_spatial_rms_mag", np.nan)):
            J += m["phot_spatial_rms_mag"] * 2500.0  # spatial residuals (flat/colorterms)
        # aperture-correction consistency (both early and final)
        if not math.isnan(m.get("apcorr1_rms_mag", np.nan)):
            J += m["apcorr1_rms_mag"] * 1200.0
        if not math.isnan(m.get("apcorr2_rms_mag", np.nan)):
            J += m["apcorr2_rms_mag"] * 1800.0       # final catalog consistency most important

        trial.set_user_attr("metrics", m)
        trial.set_user_attr("out_coll", out_coll)
        return float(J)
    return objective

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="Tune calibrateImage using existing ISR + latest calibs.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--obs-nickel", required=True)
    ap.add_argument("--instrument", default="Nickel")
    ap.add_argument("--det", type=int, default=0)
    ap.add_argument("--visits", type=int, nargs="+", required=True)
    ap.add_argument("--bad", type=int, nargs="*", default=[1032,1051,1052])
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--trials", type=int, default=20)
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

    ctx = Context(
        repo=repo, obs_nickel=obs, instr=args.instrument, det=args.det,
        visits=args.visits, bad=args.bad, jobs=args.jobs,
        postisr_coll=postisr, calib_chain=calib_chain, pipeline_yaml=proc_yaml
    )

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(make_objective(ctx), n_trials=args.trials, show_progress_bar=True)

    best = {
        "value": study.best_value,
        "params": study.best_trial.params,
        "metrics": study.best_trial.user_attrs.get("metrics", {}),
        "out_coll": study.best_trial.user_attrs.get("out_coll", ""),
    }
    print("\n=== BEST TRIAL ===")
    print(json.dumps(best, indent=2))

    # Save for reproducibility
    Path("best_params.json").write_text(json.dumps(best, indent=2) + "\n")

if __name__ == "__main__":
    main()
