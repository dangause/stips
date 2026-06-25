from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core.run import RunConfig  # noqa: E402


def _write(tmp_path, extra):
    cfg = {"object": "x", "ra": 1.0, "dec": 2.0, "bands": ["r"]}
    cfg.update(extra)
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_refcat_defaults_when_section_absent(tmp_path):
    cfg = RunConfig.from_yaml(_write(tmp_path, {}))
    assert cfg.refcat_mode == "gaia_ps1"
    assert cfg.refcat_radius_deg == 0.3
    assert cfg.refcat_gaia_quality is None


def test_refcat_section_parsed(tmp_path):
    cfg = RunConfig.from_yaml(
        _write(tmp_path, {"refcat": {"mode": "monster", "radius_deg": 0.5}})
    )
    assert cfg.refcat_mode == "monster"
    assert cfg.refcat_radius_deg == 0.5
