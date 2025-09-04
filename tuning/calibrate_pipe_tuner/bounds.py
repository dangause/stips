from __future__ import annotations
from typing import Any, Dict
import optuna

# Parameter search ranges
PARAM_BOUNDS = {
    # PSF detection
    "psf_det.threshold": (3.0, 8.0),
    "psf_det.incMult":   (1.0, 6.5),

    # PSF star selector (objectSize)
    "psfsel.snmin":       (8.0, 30.0),
    "psfsel.widthStdMax": (0.30, 0.45),

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

    # PSF Normalized Calibration Flux selector S/N
    "ncf.snmin": (15.0, 30.0),
}

def suggest_params(trial: optuna.Trial) -> Dict[str, Any]:
    """Sample a single parameter set from PARAM_BOUNDS using Optuna."""
    p: Dict[str, Any] = {}
    pf = trial.suggest_float
    pi = trial.suggest_int

    p["psf_det.threshold"]       = pf("psf_det.threshold", *PARAM_BOUNDS["psf_det.threshold"])
    p["psf_det.incMult"]         = pf("psf_det.incMult",   *PARAM_BOUNDS["psf_det.incMult"])
    p["psfsel.snmin"]            = pf("psfsel.snmin",      *PARAM_BOUNDS["psfsel.snmin"])
    p["psfsel.widthStdMax"]      = pf("psfsel.widthStdMax",*PARAM_BOUNDS["psfsel.widthStdMax"])
    p["match.maxOffsetPix"]      = pi("match.maxOffsetPix",*PARAM_BOUNDS["match.maxOffsetPix"])
    p["match.maxRotationDeg"]    = pf("match.maxRotationDeg", *PARAM_BOUNDS["match.maxRotationDeg"])
    p["match.matcherIterations"] = pi("match.matcherIterations", *PARAM_BOUNDS["match.matcherIterations"])
    p["match.minMatchDistPixels"]= pf("match.minMatchDistPixels", *PARAM_BOUNDS["match.minMatchDistPixels"])
    p["match.minMatchedPairs"]   = pi("match.minMatchedPairs", *PARAM_BOUNDS["match.minMatchedPairs"])
    p["match.minFracMatchedPairs"]=pf("match.minFracMatchedPairs", *PARAM_BOUNDS["match.minFracMatchedPairs"])
    p["match.numBrightStars"]    = pi("match.numBrightStars", *PARAM_BOUNDS["match.numBrightStars"])
    p["match.maxRefObjects"]     = pi("match.maxRefObjects", *PARAM_BOUNDS["match.maxRefObjects"])
    p["match.numPatternConsensus"]=pi("match.numPatternConsensus", *PARAM_BOUNDS["match.numPatternConsensus"])
    p["astro_src.snmin"]         = pf("astro_src.snmin", *PARAM_BOUNDS["astro_src.snmin"])
    p["apcorr.snmin"]            = pf("apcorr.snmin",    *PARAM_BOUNDS["apcorr.snmin"])
    p["apcorr.sigclip"]          = pf("apcorr.sigclip",  *PARAM_BOUNDS["apcorr.sigclip"])
    p["apcorr.niter"]            = pi("apcorr.niter",    *PARAM_BOUNDS["apcorr.niter"])
    p["ncf.snmin"]               = pf("ncf.snmin",       *PARAM_BOUNDS["ncf.snmin"])
    return p
