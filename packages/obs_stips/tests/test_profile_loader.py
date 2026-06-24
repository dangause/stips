import unittest
from pathlib import Path

from lsst.obs.stips import profile_loader

FIX = Path(__file__).parent / "data" / "demo_instrument"


class TestProfileLoader(unittest.TestCase):
    def test_load_profile_from_dir(self):
        p = profile_loader.load_profile_from_dir(str(FIX))
        self.assertEqual(p.name, "DemoFix")

    def test_inserts_on_sys_path(self):
        import sys

        profile_loader.load_profile_from_dir(str(FIX))
        self.assertIn(str(FIX), sys.path)

    def test_missing_profile_errors_clearly(self):
        with self.assertRaises(FileNotFoundError):
            profile_loader.load_profile_from_dir("/nonexistent")


if __name__ == "__main__":
    unittest.main()
