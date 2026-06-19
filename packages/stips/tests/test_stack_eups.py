import unittest
from pathlib import Path
from unittest import mock

from stips.core import stack as stack_module
from stips.core.config import Config


def _config(eups="obs_demo", data="obs_demo_data", instr="/tmp/pkgs/obs_demo"):
    c = Config(
        repo=Path("/tmp/repo"),
        stack_dir=Path("/tmp/stack"),
        instrument_dir=Path(instr),
        raw_parent_dir=Path("/tmp/raw"),
    )
    prof = mock.Mock()
    prof.eups_package = eups
    prof.obs_data_package = data
    prof.name = "Demo"
    c.profile = prof
    return c


class TestStackEups(unittest.TestCase):
    def test_setup_uses_profile_eups_package(self):
        with mock.patch.object(
            stack_module,
            "_find_stack_loader",
            return_value=Path("/tmp/stack/loadLSST.sh"),
        ):
            script = stack_module._build_setup_script(_config())
        self.assertIn("setup -r", script)
        self.assertIn("obs_demo", script)  # the profile's package
        self.assertNotIn("obs_nickel", script)  # NOT hardcoded to nickel
        self.assertIn(
            'export OBS_DEMO="/tmp/pkgs/obs_demo"', script
        )  # export name from eups_package.upper()

    def test_data_package_from_profile(self):
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(_config(data="obs_demo_data"))
        self.assertIn("obs_demo_data", script)

    def test_instrument_dir_export_fixed_name(self):
        # INSTRUMENT_DIR is the fixed export name (pipelines use $INSTRUMENT_DIR)
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(_config())
        self.assertIn('export INSTRUMENT_DIR="/tmp/pkgs/obs_demo"', script)

    def test_obs_stips_sibling_set_up(self):
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(_config())
        self.assertIn("obs_stips", script)

    def test_data_and_sibling_paths_from_packages_dir_not_instrument_parent(self):
        # The data-package and framework-sibling paths derive from the REAL
        # _PACKAGES_DIR (from __file__), NOT the synthetic instrument_dir.parent.
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(
                _config(data="obs_demo_data", instr="/tmp/pkgs/obs_demo")
            )
        pkgs = str(stack_module._PACKAGES_DIR)
        self.assertTrue(pkgs.endswith("/packages"), pkgs)
        # data-package setup path uses the real packages dir
        self.assertIn(f"{pkgs}/obs_demo_data", script)
        # obs_stips sibling path uses the real packages dir
        self.assertIn(f"{pkgs}/obs_stips", script)
        # NOT the synthetic instrument_dir.parent
        self.assertNotIn("/tmp/pkgs/obs_demo_data", script)

    def test_no_data_package_skips_setup(self):
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(_config(data=None))
        self.assertNotIn(
            "# Check for", script
        )  # no data-package setup block when unset

    def test_nickel_output_is_byte_identical_shape(self):
        # Nickel parity: eups_package=obs_nickel → export OBS_NICKEL + setup -r ... obs_nickel + data block
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/s/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(
                _config(
                    eups="obs_nickel",
                    data="obs_nickel_data",
                    instr="/p/packages/obs_nickel",
                )
            )
        self.assertIn('export OBS_NICKEL="/p/packages/obs_nickel"', script)
        self.assertIn('setup -r "/p/packages/obs_nickel" obs_nickel', script)
        self.assertIn("obs_nickel_data", script)
        self.assertIn("obs_stips", script)  # framework sibling still set up
        self.assertIn(
            'export INSTRUMENT_DIR="/p/packages/obs_nickel"', script
        )  # fixed export always present

    def test_missing_eups_package_no_raise_no_setup_line(self):
        # A declarative instrument has no EUPS product: eups_package=None must
        # NOT raise and must emit no `setup -r ... <eups>` instrument line and
        # no dynamic OBS_* export.
        cfg = _config(eups=None)
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(cfg)
        # No instrument EUPS setup line for a None eups package
        self.assertNotIn('/tmp/pkgs/obs_demo" obs_demo', script)
        self.assertNotIn("export OBS_DEMO=", script)
        # But INSTRUMENT_DIR is still exported and obs_stips still set up
        self.assertIn('export INSTRUMENT_DIR="/tmp/pkgs/obs_demo"', script)
        self.assertIn("obs_stips", script)
