#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os, math, json, warnings
from dataclasses import dataclass
from typing import Dict, List, Tuple

# ---- LSST imports (run inside your lsst-scipipe env) ----
from lsst.daf.butler import Butler
from lsst.pipe.base import Struct
from lsst.afw.table import SourceCatalog
from lsst.afw.geom import degrees
from lsst.meas.astrom import denormalizeMatches

# CalibrateImageTask lives here in the modern stack:
from lsst.pipe.tasks.calibrateImage import CalibrateImageTask, CalibrateImageTaskConfig

# ---- Optimization (Optuna) ----
import optuna
import numpy as np

# ---------------- CONFIG ----------------
REPO   = os.environ.get("REPO", "/path/to/repo")
INPUT  = os.environ.get("INPUT", "raws+calibs_collection")
OUTPUT = os.environ.get("OUTPUT", "tuning_tmp")
INSTR  = os.environ.get("INSTR", "Nickel")
DET    = int(os.environ.get("DET", "0"))
# Keep this small & representative
VISITS = [int(v) for v in os.environ.get("VISITS", "1041,1047,1050,1052").split(",")]

# Hard gates for viability (tweak to your field)
GATES = dict(
    min_psf_stars     = 40,
    min_astrom_matches= 500,
    max_zp_sigma_mag  = 0.015,   # 0.01–0.02 mag typical
)

# --------------- Utilities ---------------
def robust_rms(x, clip=3.0):
    x = np.asarray(x)
    if x.size == 0:
        return np.nan
    m = np.nanmedian(x)
    s = 1.4826 * np.nanmedian(np.abs(x - m))
    sel = np.abs(x - m) < clip * (s if s > 0 else np.nanstd(x))
    return np.sqrt(np.nanmean((x[sel] - np.nanmean(x[sel]))**2))

@dataclass
class TrialMetrics:
    n_psf_stars: int
    apcorr1_rms_mag: float
    astrom_rms_mas: float
    astrom_outlier_frac: float
    n_astrom_matches: int
    zp_sigma_mag: float
    phot_spatial_rms_mag: float
    apcorr2_rms_mag: float

def _mag_from_flux(flux_nJy):
    # 1 nJy = 31.4 AB mag (exactly 31.4 - 2.5 log10(f_nJy))
    # Use AB conversion: m_AB = 31.4 - 2.5*log10(f_nJy)
    flux = np.asarray(flux_nJy, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        mag = 31.4 - 2.5*np.log10(flux)
    return mag

# --------- Metric extraction per visit ----------
def measure_metrics_from_result(result: Struct) -> TrialMetrics:
    # PSF/ApCorr #1
    psf_sc: SourceCatalog = result.psf_stars_footprints
    n_psf = len(psf_sc)

    # ApCorr #1 RMS: use difference between large aperture and PSF flux on PSF stars
    # The exact plugin names can vary; fall back gracefully.
    def _safe(name):
        return name if name in psf_sc.schema else None

    ap_psf_delta_mag_1 = []
    ap_name = _safe("base_CircularApertureFlux_12_0_0_flux")
    psf_name = _safe("slot_PsfFlux_flux")
    if ap_name and psf_name:
        ap = psf_sc[ap_name]
        psf = psf_sc[psf_name]
        good = np.isfinite(ap) & np.isfinite(psf) & (ap > 0) & (psf > 0)
        ap_psf_delta_mag_1 = _mag_from_flux(ap[good]) - _mag_from_flux(psf[good])
    apcorr1_rms = robust_rms(ap_psf_delta_mag_1)

    # Astrometry metrics
    # result.astrometry_matches is optional; if missing, compute via denormalizeMatches if available
    n_astrom = 0
    astrom_r = []
    if hasattr(result, "astrometry_matches") and result.astrometry_matches is not None:
        matches = result.astrometry_matches
    else:
        matches = []
    # matches can be list[ReferenceMatch] or BaseCatalog; handle both
    try:
        iterable = matches
    except Exception:
        iterable = []

    outlier = 0
    for m in iterable:
        try:
            s = m.first  # SourceRecord
            r = m.second # Ref record
            # angular sep in mas
            sep_rad = s.getCoord().separation(r.getCoord()).asRadians()
            sep_mas = sep_rad * (180.0/np.pi) * 3600.0 * 1000.0
            astrom_r.append(sep_mas)
        except Exception:
            continue
    n_astrom = len(astrom_r)
    astrom_r = np.asarray(astrom_r)
    if astrom_r.size > 0:
        rms_mas = robust_rms(astrom_r)
        med = np.nanmedian(astrom_r)
        # crude outlier fraction (>3σ from median)
        sigma = 1.4826*np.nanmedian(np.abs(astrom_r - med))
        outlier = float(np.mean(np.abs(astrom_r - med) > 3*max(sigma, 1e-9)))
    else:
        rms_mas = np.nan
        outlier = np.nan

    # Photometry + ApCorr #2 metrics (use result.stars_footprints)
    stars_sc: SourceCatalog = result.stars_footprints
    ap_psf_delta_mag_2 = []
    ap_name2 = ap_name if ap_name in stars_sc.schema else None
    psf_name2 = psf_name if psf_name in stars_sc.schema else None
    if ap_name2 and psf_name2:
        ap2 = stars_sc[ap_name2]
        psf2 = stars_sc[psf_name2]
        good2 = np.isfinite(ap2) & np.isfinite(psf2) & (ap2 > 0) & (psf2 > 0)
        ap_psf_delta_mag_2 = _mag_from_flux(ap2[good2]) - _mag_from_flux(psf2[good2])
    apcorr2_rms = robust_rms(ap_psf_delta_mag_2)

    # Zeropoint scatter from the photometric fit:
    # If the task fits & applies a PhotoCalib, we can compare calibrated PSF mags to ref mags via
    # the photometry matches saved in result.photometry_matches. If missing, fall back to
    # summary stats on photoCalib metadata when available.
    zp_sigma = np.nan
    phot_spatial_rms = np.nan
    if hasattr(result, "photometry_matches") and result.photometry_matches is not None:
        resid = []
        for m in result.photometry_matches:
            try:
                s = m.first
                r = m.second
                # calibrated flux from source (nJy) -> mag
                cal_flux = s["slot_PsfFlux_flux"]
                src_mag = _mag_from_flux(cal_flux)
                ref_mag = r["photometry_gaap_aper0_mag"] if "photometry_gaap_aper0_mag" in r.schema else r["i_mag"]
                if np.isfinite(src_mag) and np.isfinite(ref_mag):
                    resid.append(src_mag - ref_mag)
            except Exception:
                continue
        resid = np.asarray(resid, float)
        if resid.size > 10:
            # overall ZP sigma
            zp_sigma = robust_rms(resid)
            # crude spatial RMS: regress residual ~ x+y and take RMS of residuals
            x = stars_sc["x"]
            y = stars_sc["y"]
            # align lengths conservatively
            n = min(len(resid), len(x), len(y))
            if n > 20:
                A = np.c_[np.ones(n), x[:n], y[:n]]
                beta, *_ = np.linalg.lstsq(A, resid[:n], rcond=None)
                fit = A @ beta
                phot_spatial_rms = robust_rms(resid[:n] - fit)
    # Package
    return TrialMetrics(
        n_psf_stars = int(n_psf),
        apcorr1_rms_mag = float(apcorr1_rms) if apcorr1_rms is not None else np.nan,
        astrom_rms_mas = float(rms_mas),
        astrom_outlier_frac = float(outlier),
        n_astrom_matches = int(n_astrom),
        zp_sigma_mag = float(zp_sigma),
        phot_spatial_rms_mag = float(phot_spatial_rms),
        apcorr2_rms_mag = float(apcorr2_rms) if apcorr2_rms is not None else np.nan,
    )

# --------- Build a task with trial params ----------
def build_task(trial: optuna.Trial) -> CalibrateImageTask:
    cfg = CalibrateImageTaskConfig()

    # === Tunables (start small) ===
    # Detection threshold
    cfg.detection.thresholdValue = trial.suggest_float("det.threshold", 4.5, 6.0)

    # Cosmic ray aggressiveness
    cfg.repair.cosmicray.nCrPixelMax = trial.suggest_int("cr.nCrPixelMax", 40000, 120000, step=20000)

    # PSFEx model complexity
    cfg.psf.psfexComponents = trial.suggest_int("psf.components", 3, 5)
    cfg.psf.psfexBasisSize  = trial.suggest_int("psf.basis", 29, 39, step=4)

    # WCS model order
    cfg.astrometry.wcsFitter.order = trial.suggest_int("wcs.order", 1, 2)

    # Photometric spatial order
    cfg.photoCalib.photoCalibOrder = trial.suggest_int("phot.order", 0, 1)
    cfg.photoCalib.applyColorTerms = trial.suggest_categorical("phot.colorTerms", [False, True])

    # Aperture radii (pixels) shared for #1/#2 to start; you can split later
    radii = trial.suggest_categorical("ap.radii", [[6.0, 12.0], [8.0, 12.0]])
    cfg.measurement.plugins["base_CircularApertureFlux"].radii = radii

    # Persist optional matches so metrics can use them
    optouts = set(cfg.optional_outputs)
    optouts.update({"astrometry_matches", "photometry_matches"})
    cfg.optional_outputs = tuple(sorted(optouts))

    return CalibrateImageTask(config=cfg)

# --------- One trial across VISITS ----------
def run_trial(trial: optuna.Trial) -> float:
    butler = Butler(REPO, instrument=INSTR, collections=INPUT)
    task = build_task(trial)

    visit_metrics: List[TrialMetrics] = []

    for visit in VISITS:
        dataId = dict(instrument=INSTR, detector=DET, visit=visit)
        # Pull post-ISR exposure
        exp = butler.get("postISRCCD", dataId=dataId) if butler.datasetExists("postISRCCD", dataId=dataId) \
              else butler.get("postISRCCD", dataId={**dataId, "physical_filter": butler.get("raw", dataId=dataId).getFilter().getName()})
        # Run task
        try:
            res: Struct = task.run(exposures=exp)
        except Exception as e:
            # Bad trial—return a huge loss
            trial.set_user_attr("failed_visit", visit)
            return 1e9

        # Compute metrics
        m = measure_metrics_from_result(res)
        visit_metrics.append(m)

    # Aggregate (mean across visits)
    def agg(name):
        arr = np.array([getattr(m, name) for m in visit_metrics], float)
        return np.nanmean(arr)

    n_psf_mean      = agg("n_psf_stars")
    n_match_mean    = agg("n_astrom_matches")
    zp_sigma_mean   = agg("zp_sigma_mag")

    # ----- Hard gates -----
    if not (n_psf_mean >= GATES["min_psf_stars"] and
            n_match_mean >= GATES["min_astrom_matches"] and
            (not np.isnan(zp_sigma_mean)) and zp_sigma_mean <= GATES["max_zp_sigma_mag"]):
        return 1e8

    # ----- Score (minimize) -----
    J = (
        agg("astrom_rms_mas") * 1.0
        + agg("astrom_outlier_frac") * 100.0
        + (agg("phot_spatial_rms_mag") * 1000.0 if not math.isnan(agg("phot_spatial_rms_mag")) else 0.0)
        + (agg("apcorr1_rms_mag") * 1000.0 if not math.isnan(agg("apcorr1_rms_mag")) else 0.0)
        + (agg("apcorr2_rms_mag") * 800.0  if not math.isnan(agg("apcorr2_rms_mag")) else 0.0)
        + zp_sigma_mean * 2000.0
    )
    # helpful attrs
    trial.set_user_attr("n_psf_mean", float(n_psf_mean))
    trial.set_user_attr("n_match_mean", float(n_match_mean))
    trial.set_user_attr("zp_sigma_mean", float(zp_sigma_mean))
    return float(J)

def main():
    study = optuna.create_study(
        study_name="calibrateImage_tuning",
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(run_trial, n_trials=25, show_progress_bar=True)

    print("\nBest trial:")
    t = study.best_trial
    print("  value(J):", t.value)
    print("  params  :", json.dumps(t.params, indent=2))
    print("  attrs   :", {k: t.user_attrs[k] for k in t.user_attrs})
    # Save a JSON for later reproducibility
    with open("best_params.json", "w") as f:
        json.dump(dict(value=t.value, params=t.params, attrs=t.user_attrs), f, indent=2)

if __name__ == "__main__":
    main()
