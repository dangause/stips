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
