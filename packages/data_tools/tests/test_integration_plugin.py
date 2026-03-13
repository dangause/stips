"""Integration tests for plugin-driven parameterization."""

import dataclasses
import inspect

from obs_nickel_data_tools.core.pipeline import CollectionNames
from obs_nickel_data_tools.instruments import get_plugin
from obs_nickel_data_tools.instruments.base import InstrumentPlugin


class TestPluginFlowIntegration:
    """Verify end-to-end plugin flow works correctly."""

    def test_plugin_creates_correct_collection_names(self):
        """Plugin properties flow through to CollectionNames."""
        plugin = get_plugin("nickel")
        cols = CollectionNames(
            "20230519",
            run_ts="20260312T120000Z",
            prefix=plugin.collection_prefix,
        )
        assert cols.raw_run == "Nickel/raw/20230519/20260312T120000Z"
        assert cols.calib_chain == "Nickel/calib/current"

    def test_custom_plugin_creates_custom_collections(self):
        """A hypothetical plugin with different prefix creates different names."""

        class FakePlugin(InstrumentPlugin):
            name = "FakeTel"
            instrument_class = "lsst.obs.smalltel.fakeTel.FakeTel"
            collection_prefix = "FakeTel"
            skymap_name = "fakeRings-v1"
            skymaps_chain = "skymaps/fakeRings"
            day_obs_offset = 0

            def fetch_data(self, night, dest_dir):
                pass

            def bootstrap(self, repo, config):
                pass

        plugin = FakePlugin()
        cols = CollectionNames(
            "20230519",
            run_ts="20260312T120000Z",
            prefix=plugin.collection_prefix,
        )
        assert cols.raw_run == "FakeTel/raw/20230519/20260312T120000Z"
        assert cols.calib_chain == "FakeTel/calib/current"
        assert (
            cols.science_parent == "FakeTel/runs/20230519/processCcd/20260312T120000Z"
        )

    def test_all_core_modules_accept_plugin(self):
        """Every core module's run() function accepts a plugin parameter."""
        from obs_nickel_data_tools.core import (
            bootstrap,
            calibs,
            clean,
            coadd,
            dia,
            fphot,
            science,
        )

        for module in [calibs, science, dia, fphot, coadd, clean, bootstrap]:
            sig = inspect.signature(module.run)
            assert (
                "plugin" in sig.parameters
            ), f"{module.__name__}.run() missing 'plugin' parameter"

    def test_run_config_has_instrument(self):
        """RunConfig has an instrument field."""
        from obs_nickel_data_tools.core.run import RunConfig

        fields = {f.name for f in dataclasses.fields(RunConfig)}
        assert "instrument" in fields

    def test_night_to_day_obs_with_offset(self):
        """night_to_day_obs respects day_obs_offset from plugin."""
        from obs_nickel_data_tools.core.pipeline import night_to_day_obs

        plugin = get_plugin("nickel")
        result = night_to_day_obs("20230519", day_obs_offset=plugin.day_obs_offset)
        assert result == "20230520"

    def test_zero_offset_same_day(self):
        """day_obs_offset=0 means same day (e.g. Hawaiian observatory)."""
        from obs_nickel_data_tools.core.pipeline import night_to_day_obs

        result = night_to_day_obs("20230519", day_obs_offset=0)
        assert result == "20230519"

    def test_config_obs_package_alias(self):
        """Config.obs_nickel property aliases obs_package for backward compat."""
        from pathlib import Path

        from obs_nickel_data_tools.core.config import Config

        config = Config(
            repo=Path("/tmp/repo"),
            stack_dir=Path("/tmp/stack"),
            obs_package=Path("/tmp/obs_smalltel"),
            raw_parent_dir=Path("/tmp/raw"),
        )
        assert config.obs_nickel == config.obs_package
