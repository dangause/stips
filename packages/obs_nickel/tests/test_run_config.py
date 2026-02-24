"""Tests for RunConfig variable star extensions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_tools/src"))


@pytest.fixture
def sn_yaml(tmp_path):
    cfg = {
        "object": "2023ixf",
        "ra": 210.91,
        "dec": 54.32,
        "bands": ["r", "i"],
        "science": {"nights": [20230519]},
        "options": {"jobs": 4},
    }
    path = tmp_path / "sn.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return path


@pytest.fixture
def variable_yaml(tmp_path):
    cfg = {
        "object": "V0678-Oph",
        "ra": 257.123,
        "dec": -18.456,
        "bands": ["b", "v", "r", "i"],
        "template": {"type": "coadd", "nights": [20230601, 20230615]},
        "science": {"nights": [20230701]},
        "options": {
            "pipeline_type": "variable",
            "period_search": True,
            "period_min": 0.5,
            "period_max": 50.0,
            "period_samples": 8000,
            "forced_phot_image_type": "both",
        },
    }
    path = tmp_path / "variable.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return path


@pytest.fixture
def variable_defaults_yaml(tmp_path):
    cfg = {
        "object": "RR-Lyr",
        "ra": 286.0,
        "dec": 42.0,
        "bands": ["r"],
        "science": {"nights": [20230801]},
        "options": {"pipeline_type": "variable"},
    }
    path = tmp_path / "var_defaults.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return path


class TestRunConfigNewFields:
    def test_sn_config_has_defaults(self, sn_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(sn_yaml)
        assert cfg.pipeline_type == "supernova"
        assert cfg.period_search is False
        assert cfg.period_min == 0.1
        assert cfg.period_max == 100.0
        assert cfg.period_samples == 10_000
        assert cfg.forced_phot_image_type == "diffim"

    def test_variable_config_parses_all_fields(self, variable_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(variable_yaml)
        assert cfg.pipeline_type == "variable"
        assert cfg.period_search is True
        assert cfg.period_min == 0.5
        assert cfg.period_max == 50.0
        assert cfg.period_samples == 8000
        assert cfg.forced_phot_image_type == "both"

    def test_variable_type_defaults_forced_phot_to_both(self, variable_defaults_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(variable_defaults_yaml)
        assert cfg.pipeline_type == "variable"
        assert cfg.forced_phot_image_type == "both"

    def test_explicit_forced_phot_overrides_variable_default(self, tmp_path):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = {
            "object": "test",
            "ra": 100.0,
            "dec": 10.0,
            "bands": ["r"],
            "science": {"nights": [20230101]},
            "options": {
                "pipeline_type": "variable",
                "forced_phot_image_type": "diffim",
            },
        }
        path = tmp_path / "override.yaml"
        with open(path, "w") as f:
            yaml.dump(cfg, f)
        rc = RunConfig.from_yaml(path)
        assert rc.forced_phot_image_type == "diffim"
