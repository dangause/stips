import unittest
from pathlib import Path

from stips.core.config import Config, load_active_profile

# Repo root: <root>/packages/stips/tests/test_config_profile.py -> up 3.
REPO_ROOT = Path(__file__).resolve().parents[3]
NICKEL_DIR = REPO_ROOT / "instruments" / "nickel"


class TestProfileLoad(unittest.TestCase):
    def test_loads_nickel_profile(self):
        p = load_active_profile(NICKEL_DIR)
        self.assertEqual(p.name, "Nickel")
        self.assertEqual(p.collection_prefix, "Nickel")
        self.assertEqual(p.skymap_name, "nickelRings-v1")
        self.assertEqual(p.skymap_collection, "skymaps/nickelRings")
        self.assertEqual(p.night_to_dayobs_offset_days, 1)

    def test_absent_profile_py_raises_file_not_found(self):
        # A genuinely-absent profile.py must raise FileNotFoundError so that
        # load() can leave profile=None (and require_profile() later gives an
        # actionable message).
        with self.assertRaises(FileNotFoundError):
            load_active_profile("/tmp/does_not_exist_instrument_dir")

    def test_config_instrument_class_is_derived_from_the_dir(self):
        cfg = Config(
            repo=Path("/tmp/repo"),
            stack_dir=Path("/tmp/stack"),
            instrument_dir=NICKEL_DIR,
            raw_parent_dir=Path("/tmp/raw"),
            profile=None,
        )
        self.assertEqual(
            cfg.instrument_class, "instruments.nickel.instrument.Instrument"
        )


class TestRequireProfile(unittest.TestCase):
    def test_require_profile_raises_actionable_message(self):
        # Config with profile=None (as load() leaves it when profile.py is
        # absent) must surface a clear, fixable error.
        cfg = Config(
            repo=Path("/tmp/repo"),
            stack_dir=Path("/tmp/stack"),
            instrument_dir=Path("/tmp/instrument_dir"),
            raw_parent_dir=Path("/tmp/raw"),
            profile=None,
        )
        with self.assertRaises(RuntimeError) as ctx:
            cfg.require_profile()
        msg = str(ctx.exception)
        self.assertIn("INSTRUMENT_DIR", msg)
        self.assertIn("profile.py", msg)
