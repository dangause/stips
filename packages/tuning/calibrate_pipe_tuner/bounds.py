from __future__ import annotations

from typing import Any, Dict

import optuna


def suggest_params(trial: optuna.Trial, param_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Sample params based on config."""
    out: Dict[str, Any] = {}
    for name, spec in param_cfg.items():
        typ = spec["type"]
        if typ == "float":
            out[name] = trial.suggest_float(
                name, float(spec["low"]), float(spec["high"])
            )
        elif typ == "int":
            out[name] = trial.suggest_int(name, int(spec["low"]), int(spec["high"]))
        elif typ == "categorical":
            out[name] = trial.suggest_categorical(name, list(spec["choices"]))
        else:
            raise ValueError(f"Unknown param type for {name}: {typ}")
    return out
