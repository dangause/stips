import unittest
from pathlib import Path
from unittest import mock

from stips.core import stack as stack_module
from stips.core.config import Config


def _config(data="obs_demo_data", instr="/tmp/pkgs/obs_demo"):
    c = Config(
        repo=Path("/tmp/repo"),
        stack_dir=Path("/tmp/stack"),
        instrument_dir=Path(instr),
        raw_parent_dir=Path("/tmp/raw"),
    )
    prof = mock.Mock()
    prof.obs_data_package = data
    # Explicit override unset: a bare Mock would auto-create a truthy
    # package_dir attribute, so pin it to None to exercise the obs_data_package
    # resolution path (co-located, then the reference packages/ layout).
    prof.package_dir = None
    prof.name = "Demo"
    c.profile = prof
    return c


class TestStackSetup(unittest.TestCase):
    def test_no_per_instrument_eups_setup(self):
        # The instrument is declarative (profile.py loaded by path): there is no
        # per-instrument EUPS product, so no `setup -r ... <eups>` instrument
        # line and no dynamic OBS_* export.
        with mock.patch.object(
            stack_module,
            "_find_stack_loader",
            return_value=Path("/tmp/stack/loadLSST.sh"),
        ):
            script = stack_module._build_setup_script(_config())
        self.assertNotIn('/tmp/pkgs/obs_demo" obs_demo', script)
        self.assertNotIn("export OBS_DEMO=", script)

    def test_data_package_from_profile(self):
        # Uses obs_nickel_data (which exists under the reference packages/ layout)
        # so precedence (3) resolves and the data-package block is emitted.
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(_config(data="obs_nickel_data"))
        self.assertIn("obs_nickel_data", script)

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
        # The data-package (reference layout) and framework-sibling paths derive
        # from the REAL _PACKAGES_DIR (from __file__), NOT the synthetic
        # instrument_dir.parent. obs_nickel_data exists under packages/, so the
        # reference-layout fallback (precedence 3) resolves to it.
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(
                _config(data="obs_nickel_data", instr="/tmp/pkgs/obs_demo")
            )
        pkgs = str(stack_module._PACKAGES_DIR)
        self.assertTrue(pkgs.endswith("/packages"), pkgs)
        # data-package setup path uses the real packages dir
        self.assertIn(f"{pkgs}/obs_nickel_data", script)
        # obs_stips sibling path uses the real packages dir
        self.assertIn(f"{pkgs}/obs_stips", script)
        # NOT the synthetic instrument_dir.parent
        self.assertNotIn("/tmp/pkgs/obs_demo/obs_nickel_data", script)

    def test_no_data_package_skips_setup(self):
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(_config(data=None))
        self.assertNotIn(
            "# Check for", script
        )  # no data-package setup block when unset

    def test_nickel_data_block_and_instrument_dir(self):
        # Nickel: obs_nickel_data data block + INSTRUMENT_DIR export + obs_stips
        # sibling, with NO per-instrument EUPS setup.
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/s/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(
                _config(
                    data="obs_nickel_data",
                    instr="/p/packages/obs_nickel",
                )
            )
        self.assertIn("obs_nickel_data", script)
        self.assertIn("obs_stips", script)  # framework sibling still set up
        self.assertIn(
            'export INSTRUMENT_DIR="/p/packages/obs_nickel"', script
        )  # fixed export always present
        self.assertNotIn("export OBS_NICKEL=", script)  # no dynamic OBS_* export
