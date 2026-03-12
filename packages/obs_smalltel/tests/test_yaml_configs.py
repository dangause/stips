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


class TestNickelCameraYaml:
    @pytest.fixture
    def config(self):
        with open(INSTRUMENTS_DIR / "nickel" / "camera.yaml") as f:
            return yaml.safe_load(f)

    def test_has_ccds(self, config):
        assert "CCDs" in config
        assert len(config["CCDs"]) >= 1

    def test_has_plate_scale(self, config):
        assert "plateScale" in config
        assert config["plateScale"] > 0

    def test_single_detector(self, config):
        """Small telescopes have a single CCD."""
        assert len(config["CCDs"]) == 1


class TestNickelFiltersYaml:
    @pytest.fixture
    def config(self):
        with open(INSTRUMENTS_DIR / "nickel" / "filters.yaml") as f:
            return yaml.safe_load(f)

    def test_has_filters(self, config):
        assert "filters" in config
        assert len(config["filters"]) >= 4  # at minimum B, V, R, I

    def test_filter_fields(self, config):
        for f in config["filters"]:
            assert "name" in f, f"Filter missing 'name': {f}"
            assert "band" in f or f.get("band") is None

    def test_standard_bvri_present(self, config):
        names = {f["name"] for f in config["filters"]}
        assert {"B", "V", "R", "I"}.issubset(names)
