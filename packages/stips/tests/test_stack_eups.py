import unittest
from pathlib import Path
from unittest import mock

from stips.core import stack as stack_module
from stips.core.config import Config

# The reference Nickel instrument dir, which co-locates its curated-calibration
# data package at instruments/nickel/obs_nickel_data (resolver precedence (2)).
# test_stack_eups.py -> parents[3] == repo root.
_NICKEL_DIR = Path(__file__).resolve().parents[3] / "instruments" / "nickel"


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
        # Uses obs_nickel_data co-located under the real instruments/nickel dir
        # so precedence (2) resolves and the data-package block is emitted.
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(
                _config(data="obs_nickel_data", instr=str(_NICKEL_DIR))
            )
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

    def test_sibling_from_packages_dir_data_from_instrument_dir(self):
        # The framework-sibling (obs_stips) path derives from the REAL
        # _PACKAGES_DIR (from __file__), independent of INSTRUMENT_DIR. The
        # co-located data package (precedence (2)) resolves UNDER the instrument
        # dir, not _PACKAGES_DIR — the reference fork layout after repackaging.
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/x/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(
                _config(data="obs_nickel_data", instr=str(_NICKEL_DIR))
            )
        pkgs = str(stack_module._PACKAGES_DIR)
        self.assertTrue(pkgs.endswith("/packages"), pkgs)
        # obs_stips sibling path uses the real framework packages dir
        self.assertIn(f"{pkgs}/obs_stips", script)
        # data-package setup path uses the co-located instrument-dir location
        self.assertIn(f"{_NICKEL_DIR}/obs_nickel_data", script)
        # NOT the framework packages dir (obs_nickel_data no longer lives there)
        self.assertNotIn(f"{pkgs}/obs_nickel_data", script)

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
        # sibling, with NO per-instrument EUPS setup. The data package is
        # co-located under the real instruments/nickel dir (precedence (2)).
        with mock.patch.object(
            stack_module, "_find_stack_loader", return_value=Path("/s/loadLSST.sh")
        ):
            script = stack_module._build_setup_script(
                _config(
                    data="obs_nickel_data",
                    instr=str(_NICKEL_DIR),
                )
            )
        self.assertIn("obs_nickel_data", script)
        self.assertIn("obs_stips", script)  # framework sibling still set up
        self.assertIn(
            f'export INSTRUMENT_DIR="{_NICKEL_DIR}"', script
        )  # fixed export always present
        self.assertNotIn("export OBS_NICKEL=", script)  # no dynamic OBS_* export
