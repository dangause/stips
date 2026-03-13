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
