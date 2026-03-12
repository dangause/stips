"""Tests for ConfigurableTranslator base class."""


class TestTranslatorYamlLoading:
    """Test header_map.yaml loading (no LSST stack needed for these)."""

    def test_can_translate_matching_instrument(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        header = {"INSTRUME": "Nickel Direct Imager"}
        assert FakeTranslator.can_translate(header) is True

    def test_can_translate_non_matching(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        header = {"INSTRUME": "LRIS"}
        assert FakeTranslator.can_translate(header) is False

    def test_can_translate_case_insensitive(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        header = {"INSTRUME": "NICKEL Direct Imager"}
        assert FakeTranslator.can_translate(header) is True

    def test_const_map_loaded_from_yaml(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        assert "boresight_rotation_coord" in FakeTranslator._const_map

    def test_trivial_map_loaded_from_yaml(self):
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class FakeTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"

        assert "exposure_time" in FakeTranslator._trivial_map


class TestTranslatorMethods:
    """Test translator methods using mock headers."""

    def _make_translator(self, header_dict):
        """Create a translator subclass and instantiate with a mock header."""
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        class TestTranslator(ConfigurableTranslator):
            supported_instrument = "Nickel"
            config_dir = "nickel"
            name = "TestNickel"

        # FitsTranslator.__init__ expects a dict-like header
        return TestTranslator(header_dict)

    def test_to_physical_filter_standard(self):
        t = self._make_translator({"INSTRUME": "Nickel", "FILTNAM": "B"})
        assert t.to_physical_filter() == "B"

    def test_to_physical_filter_open_maps_to_clear(self):
        t = self._make_translator({"INSTRUME": "Nickel", "FILTNAM": "OPEN"})
        assert t.to_physical_filter() == "clear"

    def test_to_physical_filter_c_maps_to_clear(self):
        t = self._make_translator({"INSTRUME": "Nickel", "FILTNAM": "C"})
        assert t.to_physical_filter() == "clear"

    def test_to_physical_filter_unknown_passthrough(self):
        t = self._make_translator({"INSTRUME": "Nickel", "FILTNAM": "EXOTIC"})
        assert t.to_physical_filter() == "EXOTIC"

    def test_to_location_returns_earth_location(self):
        from astropy.coordinates import EarthLocation

        t = self._make_translator({"INSTRUME": "Nickel"})
        loc = t.to_location()
        assert isinstance(loc, EarthLocation)
        # Lick Observatory is roughly at lat 37.3, lon -121.6
        assert abs(loc.lat.deg - 37.3414) < 0.01
        assert abs(loc.lon.deg - (-121.6429)) < 0.01
