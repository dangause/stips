import unittest
from pathlib import Path

from stips.core.config import Config, load_profile


class TestProfileLoad(unittest.TestCase):
    def test_loads_nickel_profile(self):
        p = load_profile("lsst.obs.nickel")
        self.assertEqual(p.name, "Nickel")
        self.assertEqual(p.collection_prefix, "Nickel")
        self.assertEqual(p.instrument_class, "lsst.obs.nickel.Nickel")
        self.assertEqual(p.skymap_name, "nickelRings-v1")
        self.assertEqual(p.skymap_collection, "skymaps/nickelRings")
        self.assertEqual(p.night_to_dayobs_offset_days, 1)

    def test_absent_package_raises_module_not_found(self):
        # A genuinely-absent obs package must raise ModuleNotFoundError so that
        # load() can map it to profile=None (and require_profile() later gives
        # an actionable message).
        with self.assertRaises(ModuleNotFoundError):
            load_profile("lsst.obs.does_not_exist")


class TestRequireProfile(unittest.TestCase):
    def test_require_profile_raises_actionable_message(self):
        # Config with profile=None (as load() leaves it when the obs package is
        # not installed) must surface a clear, fixable error.
        cfg = Config(
            repo=Path("/tmp/repo"),
            stack_dir=Path("/tmp/stack"),
            obs_nickel=Path("/tmp/obs_nickel"),
            raw_parent_dir=Path("/tmp/raw"),
            profile=None,
            instrument_package="lsst.obs.does_not_exist",
        )
        with self.assertRaises(RuntimeError) as ctx:
            cfg.require_profile()
        msg = str(ctx.exception)
        self.assertIn("lsst.obs.does_not_exist", msg)
        self.assertIn("pip install", msg)
