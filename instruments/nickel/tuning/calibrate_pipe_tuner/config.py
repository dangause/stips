from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    import yaml  # PyYAML
except Exception:
    yaml = None


def load_config(path: Path) -> Dict[str, Any]:
    """Load tuning config from YAML or JSON."""
    text = path.read_text()
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML not installed; install pyyaml or use JSON.")
        return yaml.safe_load(text) or {}
    return json.loads(text)


def get_parameters(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get("parameters", {})


def get_metrics(cfg: Dict[str, Any]) -> Any:
    return cfg.get("metrics", [])


def get_overrides_prelude(cfg: Dict[str, Any]) -> str:
    return cfg.get("overrides_prelude", "")
