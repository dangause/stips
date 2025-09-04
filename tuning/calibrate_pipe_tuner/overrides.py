from __future__ import annotations
from pathlib import Path
from typing import Dict
from .io_utils import ensure_parent

def write_overrides_from_config(workdir: Path, tag: str, params: Dict[str, float], param_cfg: Dict[str, dict], prelude: str = "") -> Path:
    """Emit per-trial overrides from config (one 'apply' snippet per parameter)."""
    trial_dir = workdir / "trials" / tag
    trial_dir.mkdir(parents=True, exist_ok=True)
    ov_path = trial_dir / f"calib_overrides_{tag}.py"

    lines = ["# Auto-generated overrides for " + tag, "# Executed with `config` in scope.", ""]
    if prelude.strip():
        lines.append("# ---- Prelude ----")
        lines.append(prelude.rstrip("\n"))
        lines.append("")

    lines.append("# ---- Tuned Parameters ----")
    for name, value in params.items():
        apply_line = param_cfg[name]["apply"]
        # substitute {value} with a representation that preserves ints/floats
        val_repr = repr(value) if not isinstance(value, float) else f"{value:.8g}"
        lines.append(f"# {name}")
        lines.append(apply_line.format(value=val_repr))

    ensure_parent(ov_path)
    ov_path.write_text("\n".join(lines) + "\n")
    return ov_path
