"""Tests for GenericSmallTelInstrument base class."""

import pytest


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


# LSST-dependent tests — skip if stack not available
try:
    import lsst.obs.base as obs_base

    _HAS_LSST = True
except ImportError:
    _HAS_LSST = False


@pytest.mark.skipif(not _HAS_LSST, reason="LSST stack not available")
class TestGenericSmallTelInstrumentLSST:
    """Tests that require the LSST stack."""

    def _make_nickel_subclass(self):
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument

        class TestNickel(GenericSmallTelInstrument):
            instrument_name = "Nickel"
            config_dir = "nickel"

            def getRawFormatter(self, dataId):
                return None

        return TestNickel

    def test_get_name(self):
        cls = self._make_nickel_subclass()
        assert cls.getName() == "Nickel"

    def test_get_camera_returns_camera(self):
        cls = self._make_nickel_subclass()
        inst = cls()
        camera = inst.getCamera()
        assert len(camera) == 1  # single CCD

    def test_filter_definitions_loaded_from_yaml(self):
        cls = self._make_nickel_subclass()
        inst = cls()
        filt_defs = inst.filterDefinitions
        names = {f.physical_filter for f in filt_defs}
        assert {"B", "V", "R", "I", "clear"}.issubset(names)

    def test_is_lsst_instrument(self):
        cls = self._make_nickel_subclass()
        assert issubclass(cls, obs_base.Instrument)
