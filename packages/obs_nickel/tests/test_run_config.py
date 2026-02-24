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


@pytest.fixture
def transit_yaml(tmp_path):
    """Transit YAML config with BLS search enabled."""
    cfg = {
        "object": "HAT-P-32",
        "ra": 30.456,
        "dec": 46.789,
        "bands": ["r", "i"],
        "template": {"type": "coadd", "nights": [20230601, 20230615]},
        "science": {"nights": [20230701]},
        "options": {
            "pipeline_type": "transit",
            "transit_search": True,
            "period_min": 1.0,
            "period_max": 5.0,
            "transit_duration_min": 1.0,
            "transit_duration_max": 4.0,
        },
    }
    path = tmp_path / "transit.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return path


@pytest.fixture
def transit_defaults_yaml(tmp_path):
    """Transit config relying on pipeline_type defaults."""
    cfg = {
        "object": "WASP-12",
        "ra": 97.637,
        "dec": 29.672,
        "bands": ["r"],
        "science": {"nights": [20230901]},
        "options": {"pipeline_type": "transit"},
    }
    path = tmp_path / "transit_defaults.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return path


class TestRunConfigTransitFields:
    """Test transit extension fields in RunConfig."""

    def test_transit_config_parses_all_fields(self, transit_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(transit_yaml)
        assert cfg.pipeline_type == "transit"
        assert cfg.transit_search is True
        assert cfg.search_method == "bls"
        assert cfg.period_min == 1.0
        assert cfg.period_max == 5.0
        assert cfg.transit_duration_min == 1.0
        assert cfg.transit_duration_max == 4.0

    def test_transit_type_defaults_forced_phot_to_visit(self, transit_defaults_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(transit_defaults_yaml)
        assert cfg.pipeline_type == "transit"
        assert cfg.forced_phot_image_type == "visit"

    def test_transit_type_defaults_search_method_to_bls(self, transit_defaults_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(transit_defaults_yaml)
        assert cfg.search_method == "bls"
        assert cfg.transit_search is True

    def test_transit_type_defaults_duration_range(self, transit_defaults_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(transit_defaults_yaml)
        assert cfg.transit_duration_min == 0.5
        assert cfg.transit_duration_max == 6.0

    def test_explicit_search_method_overrides_transit_default(self, tmp_path):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = {
            "object": "test",
            "ra": 100.0,
            "dec": 10.0,
            "bands": ["r"],
            "science": {"nights": [20230101]},
            "options": {
                "pipeline_type": "transit",
                "search_method": "both",
            },
        }
        path = tmp_path / "override.yaml"
        with open(path, "w") as f:
            yaml.dump(cfg, f)
        rc = RunConfig.from_yaml(path)
        assert rc.search_method == "both"

    def test_sn_config_has_transit_defaults(self, sn_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(sn_yaml)
        assert cfg.search_method == "lomb_scargle"
        assert cfg.transit_search is False
        assert cfg.transit_duration_min == 0.5
        assert cfg.transit_duration_max == 6.0
