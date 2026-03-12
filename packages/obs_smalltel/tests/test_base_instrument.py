"""Tests for GenericSmallTelInstrument base class."""


class TestConfigLoading:
    """Test YAML config loading helpers (no LSST stack needed)."""

    def test_config_path_resolves_to_instruments_dir(self):
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument

        class FakeInstrument(GenericSmallTelInstrument):
            instrument_name = "Fake"
            config_dir = "nickel"

            def getRawFormatter(self, dataId):
                return None

        inst = FakeInstrument.__new__(FakeInstrument)
        path = inst._config_path("instrument.yaml")
        assert path.exists(), f"Expected {path} to exist"
        assert path.name == "instrument.yaml"
        assert "instruments/nickel" in str(path)

    def test_load_yaml_returns_dict(self):
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument

        class FakeInstrument(GenericSmallTelInstrument):
            instrument_name = "Fake"
            config_dir = "nickel"

            def getRawFormatter(self, dataId):
                return None

        inst = FakeInstrument.__new__(FakeInstrument)
        data = inst._load_yaml("instrument.yaml")
        assert isinstance(data, dict)
        assert data["name"] == "Nickel"
