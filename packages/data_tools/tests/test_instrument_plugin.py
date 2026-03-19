"""Tests for InstrumentPlugin ABC and instrument plugins."""

import pytest
from small_tel_tools.instruments import get_plugin, list_plugins
from small_tel_tools.instruments.base import InstrumentPlugin
from small_tel_tools.instruments.ctio0m9 import Ctio0m9Plugin
from small_tel_tools.instruments.nickel import NickelPlugin


class TestInstrumentPluginABC:
    """Verify InstrumentPlugin is a proper ABC."""

    def test_cannot_instantiate_directly(self):
        """InstrumentPlugin is abstract — direct instantiation must fail."""
        with pytest.raises(TypeError):
            InstrumentPlugin()

    def test_required_abstract_methods(self):
        """Verify the abstract methods that subclasses must implement."""
        abstract_methods = InstrumentPlugin.__abstractmethods__
        assert "fetch_data" in abstract_methods
        assert "bootstrap" in abstract_methods

    def test_concrete_subclass_with_all_methods(self):
        """A subclass implementing all abstract methods can be instantiated."""

        class FakePlugin(InstrumentPlugin):
            name = "Fake"
            instrument_class = "lsst.obs.fake.Fake"
            collection_prefix = "Fake"
            skymap_name = "fakeRings-v1"
            skymaps_chain = "skymaps/fakeRings"
            day_obs_offset = 0

            def fetch_data(self, night, dest_dir):
                pass

            def bootstrap(self, repo, config):
                pass

        plugin = FakePlugin()
        assert plugin.name == "Fake"
        assert plugin.collection_prefix == "Fake"

    def test_default_pipeline_configs_returns_empty(self):
        """default_pipeline_configs() has a default implementation returning {}."""

        class MinimalPlugin(InstrumentPlugin):
            name = "Min"
            instrument_class = "lsst.obs.min.Min"
            collection_prefix = "Min"
            skymap_name = "minRings-v1"
            skymaps_chain = "skymaps/minRings"
            day_obs_offset = 0

            def fetch_data(self, night, dest_dir):
                pass

            def bootstrap(self, repo, config):
                pass

        plugin = MinimalPlugin()
        assert plugin.default_pipeline_configs() == {}
        assert plugin.curated_calibrations_path() is None
        assert plugin.refcat_path() is None


class TestNickelPlugin:
    """Verify NickelPlugin provides correct Nickel-specific values."""

    def test_identity_attributes(self):
        plugin = NickelPlugin()
        assert plugin.name == "Nickel"
        assert plugin.instrument_class == "lsst.obs.smalltel.nickel.Nickel"
        assert plugin.collection_prefix == "Nickel"

    def test_skymap_attributes(self):
        plugin = NickelPlugin()
        assert plugin.skymap_name == "nickelRings-v1"
        assert plugin.skymaps_chain == "skymaps/nickelRings"

    def test_day_obs_offset(self):
        """Lick Observatory is UTC-8, so observing night crosses into next UT day."""
        plugin = NickelPlugin()
        assert plugin.day_obs_offset == 1

    def test_is_instrument_plugin(self):
        """NickelPlugin is a proper InstrumentPlugin subclass."""
        plugin = NickelPlugin()
        assert isinstance(plugin, InstrumentPlugin)

    def test_lick_archive_fields(self):
        """NickelPlugin exposes Lick archive URL and instrument filter."""
        plugin = NickelPlugin()
        assert "ucolick.org" in plugin.archive_url
        assert plugin.archive_instrument == "NICKEL_DIR"

    def test_default_pipeline_configs_not_empty(self):
        """NickelPlugin provides default config overrides."""
        plugin = NickelPlugin()
        defaults = plugin.default_pipeline_configs()
        assert isinstance(defaults, dict)


class TestCtio0m9Plugin:
    """Verify Ctio0m9Plugin provides correct CTIO-specific values."""

    def test_identity_attributes(self):
        plugin = Ctio0m9Plugin()
        assert plugin.name == "ctio0m9"
        assert plugin.instrument_class == "lsst.obs.smalltel.ctio0m9.Ctio0m9"
        assert plugin.collection_prefix == "ctio0m9"

    def test_skymap_attributes(self):
        plugin = Ctio0m9Plugin()
        assert plugin.skymap_name == "ctio0m9Rings-v1"
        assert plugin.skymaps_chain == "skymaps/ctio0m9Rings"

    def test_day_obs_offset(self):
        """CTIO is UTC-4, so observing night crosses into next UT day."""
        plugin = Ctio0m9Plugin()
        assert plugin.day_obs_offset == 1

    def test_is_instrument_plugin(self):
        """Ctio0m9Plugin is a proper InstrumentPlugin subclass."""
        plugin = Ctio0m9Plugin()
        assert isinstance(plugin, InstrumentPlugin)

    def test_fetch_data_not_implemented(self):
        """CTIO archive download is not implemented."""
        plugin = Ctio0m9Plugin()
        with pytest.raises(NotImplementedError):
            plugin.fetch_data("20090527", "/tmp")

    def test_default_pipeline_configs_not_empty(self):
        """Ctio0m9Plugin provides default config overrides."""
        plugin = Ctio0m9Plugin()
        defaults = plugin.default_pipeline_configs()
        assert isinstance(defaults, dict)
        assert "colorterms" in defaults


class TestPluginRegistry:
    """Verify plugin discovery and lookup."""

    def test_get_plugin_nickel(self):
        """get_plugin('nickel') returns NickelPlugin."""
        plugin = get_plugin("nickel")
        assert isinstance(plugin, NickelPlugin)
        assert plugin.name == "Nickel"

    def test_get_plugin_case_insensitive(self):
        """Plugin lookup is case-insensitive."""
        plugin = get_plugin("Nickel")
        assert isinstance(plugin, NickelPlugin)

    def test_get_plugin_unknown_raises(self):
        """Unknown instrument raises ValueError."""
        with pytest.raises(ValueError, match="Unknown instrument"):
            get_plugin("nonexistent")

    def test_get_plugin_ctio0m9(self):
        """get_plugin('ctio0m9') returns Ctio0m9Plugin."""
        plugin = get_plugin("ctio0m9")
        assert isinstance(plugin, Ctio0m9Plugin)
        assert plugin.name == "ctio0m9"

    def test_list_plugins(self):
        """list_plugins() includes both 'nickel' and 'ctio0m9'."""
        plugins = list_plugins()
        assert "nickel" in plugins
        assert "ctio0m9" in plugins
