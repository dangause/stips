import importlib
import os
import sys
import unittest
from pathlib import Path

FIX = str(Path(__file__).parent / "data" / "demo_instrument")


class TestActive(unittest.TestCase):
    def setUp(self):
        # Snapshot INSTRUMENT_DIR; tearDown restores it so NO test leaks it
        # (an unset/altered INSTRUMENT_DIR breaks later tests that resolve the
        # camera/pipeline includes from it).
        self._prev_instr_dir = os.environ.get("INSTRUMENT_DIR")

    def tearDown(self):
        if self._prev_instr_dir is None:
            os.environ.pop("INSTRUMENT_DIR", None)
        else:
            os.environ["INSTRUMENT_DIR"] = self._prev_instr_dir
        # Don't leave a profile-bound, INSTRUMENT_DIR-cached `active` in
        # sys.modules — a later plain `import active` (expecting fail-loud)
        # would otherwise get the cached module and pass for the wrong reason.
        sys.modules.pop("lsst.obs.stips.active", None)

    def test_synthesizes_concrete_instrument(self):
        os.environ["INSTRUMENT_DIR"] = FIX
        import lsst.obs.stips.active as active

        importlib.reload(active)
        cls = active.Instrument
        self.assertEqual(cls.getName(), "DemoFix")
        self.assertTrue(len(cls.filterDefinitions) >= 1)
        self.assertEqual(
            cls.__module__ + "." + cls.__qualname__,
            "lsst.obs.stips.active.Instrument",
        )

    def test_package_import_without_instrument_dir_is_safe(self):
        os.environ.pop("INSTRUMENT_DIR", None)
        import lsst.obs.stips  # must NOT trigger synthesis / raise

        self.assertTrue(hasattr(lsst.obs.stips, "StipsInstrument"))

    def test_active_import_without_instrument_dir_fails_loud(self):
        os.environ.pop("INSTRUMENT_DIR", None)
        # Drop any cached module so a fresh import re-executes synthesis. The
        # initial import (module-exec) raises just like a reload would, so guard
        # both forms.
        sys.modules.pop("lsst.obs.stips.active", None)
        with self.assertRaises(RuntimeError):
            import lsst.obs.stips.active as active

            importlib.reload(active)


if __name__ == "__main__":
    unittest.main()
