from __future__ import annotations
from typing import Dict, Optional, List

# Targets / weights (lower score is better; ~1.0 means “on target”)
TARGETS = {
    "psfSigma_med":        2.0,    # pixels
    "astromOffsetStd_med": 0.035,  # arcsec
    "skyNoise_med":        9.0,    # ADU
    "magLim_med":          20.0,   # mag (higher is better)
}
WEIGHTS = {
    "psfSigma_med":        0.35,
    "astromOffsetStd_med": 0.35,
    "skyNoise_med":        0.15,
    "magLim_med":          0.15,
}

def compute_base_score(meds: Dict[str, Optional[float]]) -> float:
    """Combine per-visit medians into a single score (lower is better)."""
    terms: List[float] = []
    for k in ("psfSigma_med", "astromOffsetStd_med", "skyNoise_med"):
        v = meds.get(k)
        if v is None or v <= 0:
            return float("inf")
        terms.append(WEIGHTS[k] * (v / TARGETS[k]))
    v = meds.get("magLim_med")
    if v is None or v <= 0:
        return float("inf")
    terms.append(WEIGHTS["magLim_med"] * (TARGETS["magLim_med"] / v))
    return sum(terms)

def penalize_score(base: float, n_success: int, n_total: int, policy: str, weight: float) -> float:
    """Apply failure-aware penalty: 'hard' | 'frac' | 'linear'."""
    if n_total <= 0:
        return float("inf")
    n_fail = n_total - n_success
    if policy == "hard":
        return float("inf") if n_fail > 0 else base
    if policy == "frac":
        sr = n_success / n_total
        return float("inf") if sr <= 0 else base * (sr ** (-weight))
    if policy == "linear":
        return base * (1.0 + weight * n_fail)
    return base
