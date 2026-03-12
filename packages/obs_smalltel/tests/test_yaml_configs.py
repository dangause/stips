"""Tests for YAML configuration loading (no LSST stack required)."""

from pathlib import Path

import pytest
import yaml

INSTRUMENTS_DIR = Path(__file__).parent.parent / "instruments"


class TestNickelInstrumentYaml:
    @pytest.fixture
    def config(self):
        with open(INSTRUMENTS_DIR / "nickel" / "instrument.yaml") as f:
            return yaml.safe_load(f)

    def test_required_fields(self, config):
        assert config["name"] == "Nickel"
        assert "location" in config
        assert "visit_system" in config

    def test_location_fields(self, config):
        loc = config["location"]
        assert "latitude" in loc
        assert "longitude" in loc
        assert "elevation" in loc
        assert -90 <= loc["latitude"] <= 90
        assert -180 <= loc["longitude"] <= 180
        assert loc["elevation"] > 0

    def test_day_obs_offset(self, config):
        assert config["day_obs_offset"] in (0, 1)
