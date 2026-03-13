"""Tests verifying core modules accept plugin parameter."""

import inspect


class TestCalibsPluginParam:
    """Verify calibs.run() accepts and uses plugin parameter."""

    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.calibs import run

        sig = inspect.signature(run)
        assert "plugin" in sig.parameters

    def test_write_curated_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.calibs import write_curated_calibrations

        sig = inspect.signature(write_curated_calibrations)
        assert "plugin" in sig.parameters


class TestSciencePluginParam:
    """Verify science.run() and resolve_object_filter() accept plugin parameter."""

    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.science import run

        sig = inspect.signature(run)
        assert "plugin" in sig.parameters

    def test_resolve_object_filter_accepts_instrument_name(self):
        from obs_nickel_data_tools.core.science import resolve_object_filter

        sig = inspect.signature(resolve_object_filter)
        assert "instrument_name" in sig.parameters


class TestDiaPluginParam:
    """Verify dia.run() accepts plugin parameter."""

    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.dia import run

        sig = inspect.signature(run)
        assert "plugin" in sig.parameters


class TestFphotPluginParam:
    """Verify fphot.run() accepts plugin parameter."""

    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.fphot import run

        sig = inspect.signature(run)
        assert "plugin" in sig.parameters


class TestCoaddPluginParam:
    """Verify coadd.run() and find_tract_for_coords() accept plugin parameters."""

    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.coadd import run

        sig = inspect.signature(run)
        assert "plugin" in sig.parameters

    def test_find_tract_accepts_skymap_params(self):
        from obs_nickel_data_tools.core.coadd import find_tract_for_coords

        sig = inspect.signature(find_tract_for_coords)
        assert "skymap_name" in sig.parameters
        assert "skymaps_chain" in sig.parameters


class TestCleanPluginParam:
    """Verify clean.run() accepts plugin parameter."""

    def test_run_accepts_plugin_param(self):
        from obs_nickel_data_tools.core.clean import run

        sig = inspect.signature(run)
        assert "plugin" in sig.parameters


class TestRunConfigInstrument:
    def test_run_config_has_instrument_field(self):
        """RunConfig dataclass has an instrument field."""
        import dataclasses

        from obs_nickel_data_tools.core.run import RunConfig

        fields = {f.name for f in dataclasses.fields(RunConfig)}
        assert "instrument" in fields

    def test_run_config_instrument_defaults_to_nickel(self):
        """RunConfig.instrument defaults to 'nickel'."""
        import dataclasses

        from obs_nickel_data_tools.core.run import RunConfig

        for f in dataclasses.fields(RunConfig):
            if f.name == "instrument":
                assert f.default == "nickel"


class TestConfigObsPackage:
    def test_config_has_obs_package(self):
        """Config has obs_package field."""
        import dataclasses

        from obs_nickel_data_tools.core.config import Config

        fields = {f.name for f in dataclasses.fields(Config)}
        assert "obs_package" in fields

    def test_obs_nickel_alias(self):
        """config.obs_nickel is a backward-compat alias for obs_package."""
        from pathlib import Path

        from obs_nickel_data_tools.core.config import Config

        config = Config(
            repo=Path("/tmp/repo"),
            stack_dir=Path("/tmp/stack"),
            obs_package=Path("/tmp/obs_smalltel"),
            raw_parent_dir=Path("/tmp/raw"),
        )
        assert config.obs_package == Path("/tmp/obs_smalltel")
        assert config.obs_nickel == config.obs_package

    def test_derived_paths_use_obs_package(self):
        """pipelines_dir and configs_dir derive from obs_package."""
        from pathlib import Path

        from obs_nickel_data_tools.core.config import Config

        config = Config(
            repo=Path("/tmp/repo"),
            stack_dir=Path("/tmp/stack"),
            obs_package=Path("/tmp/obs_smalltel"),
            raw_parent_dir=Path("/tmp/raw"),
        )
        assert config.pipelines_dir == Path("/tmp/obs_smalltel/pipelines")
        assert config.configs_dir == Path("/tmp/obs_smalltel/configs")
