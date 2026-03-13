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
