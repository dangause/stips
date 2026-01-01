# calibrate_pipe_tuner/scoring.py
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple


def aggregate(values: List[float], how: str) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    if how == "median":
        n = len(v)
        return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])
    if how == "mean":
        return sum(v) / len(v)
    raise ValueError(f"Unknown aggregate: {how}")


def compute_metrics_and_score(
    meds: Dict[str, Optional[float]],
    metrics_cfg: List[dict],
) -> Tuple[float, float]:
    """
    Compute a base score from metrics using config-driven targets/weights/directions.

    Parameters
    ----------
    meds : Dict[str, Optional[float]]
        Metric medians keyed by metric name.
    metrics_cfg : List[dict]
        Each item must include: name, target, weight, direction ('min'|'max').

    Returns
    -------
    (score_base, score_base)
        Legacy pair; first is the base score (no failure penalty),
        second is the same value (penalty is applied outside this function).
    """
    total = 0.0
    for m in metrics_cfg:
        name = m["name"]
        target = float(m["target"])
        weight = float(m["weight"])
        direction = m["direction"]  # 'min' or 'max'
        val = meds.get(name)
        if val is None or val <= 0 or target <= 0:
            return math.inf, math.inf
        if direction == "min":
            term = weight * (val / target)
        elif direction == "max":
            term = weight * (target / val)
        else:
            raise ValueError(f"direction must be 'min' or 'max' for {name}")
        total += term
    return total, total


def penalize_score(
    base_score: float,
    n_success: int,
    n_total: int,
    policy: str = "frac",
    weight: float = 1.0,
) -> float:
    """
    Apply failure-penalization to a base score.

    Policies
    --------
    hard   : any failure => +inf
    frac   : base * (success_rate ** -weight)
    linear : base * (1 + weight * n_fail)
    """
    if n_total <= 0:
        return math.inf

    n_fail = n_total - n_success

    if policy == "hard":
        return math.inf if n_fail > 0 else base_score

    if policy == "frac":
        sr = n_success / n_total
        if sr <= 0:
            return math.inf
        return base_score * (sr ** (-weight))

    if policy == "linear":
        return base_score * (1.0 + weight * n_fail)

    # Unknown policy -> no extra penalty
    return base_score
