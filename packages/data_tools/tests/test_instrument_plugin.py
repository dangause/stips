"""Tests for InstrumentPlugin ABC and NickelPlugin."""

import pytest
from obs_nickel_data_tools.instruments.base import InstrumentPlugin


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
