import importlib.util
import sys
import unittest
from pathlib import Path

from stips.core.config import Config, load_profile

# Repo root: <root>/packages/stips/tests/test_config_profile.py -> up 3.
REPO_ROOT = Path(__file__).resolve().parents[3]
NICKEL_PROFILE = REPO_ROOT / "instruments" / "nickel" / "profile.py"


def _load_nickel_profile_by_path():
    """Load the migrated Nickel profile BY PATH (post-obs_nickel-collapse).

    Mirrors ``stips.core.config.load()``: insert the instrument dir on sys.path
    so the profile's co-located ``fetch`` hook module resolves, then exec the
    file. The old ``load_profile("lsst.obs.nickel")`` package import no longer
    exists — the profile now lives in ``instruments/nickel/profile.py``.
    """
    if str(NICKEL_PROFILE.parent) not in sys.path:
        sys.path.insert(0, str(NICKEL_PROFILE.parent))
    spec = importlib.util.spec_from_file_location(
        "_stips_nickel_profile", NICKEL_PROFILE
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.profile


class TestProfileLoad(unittest.TestCase):
    def test_loads_nickel_profile(self):
        p = _load_nickel_profile_by_path()
        self.assertEqual(p.name, "Nickel")
        self.assertEqual(p.collection_prefix, "Nickel")
        self.assertEqual(p.instrument_class, "lsst.obs.stips.active.Instrument")
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
            instrument_dir=Path("/tmp/obs_nickel"),
            raw_parent_dir=Path("/tmp/raw"),
            profile=None,
            instrument_package="lsst.obs.does_not_exist",
        )
        with self.assertRaises(RuntimeError) as ctx:
            cfg.require_profile()
        msg = str(ctx.exception)
        self.assertIn("lsst.obs.does_not_exist", msg)
        self.assertIn("pip install", msg)
