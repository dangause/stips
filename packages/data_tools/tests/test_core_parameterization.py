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
