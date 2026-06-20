"""Golden: Nickel-generated collection names / day_obs BEFORE the Phase 2b de-hardcode.
After de-hardcode, the Nickel profile must reproduce these EXACT strings (byte-for-byte).
Do NOT change these literals to make a refactor pass — a difference means the de-hardcode
diverged from current Nickel behavior."""

import importlib.util
import sys
import unittest
from pathlib import Path

from stips.collections import CollectionNames
from stips.core.pipeline import night_to_day_obs

# Repo root: <root>/packages/stips/tests/test_dehardcode_parity.py -> up 3.
REPO_ROOT = Path(__file__).resolve().parents[3]
NICKEL_PROFILE = REPO_ROOT / "instruments" / "nickel" / "profile.py"


def _load_nickel_profile_by_path():
    """Load the migrated Nickel profile BY PATH (post-obs_nickel-collapse).

    The obs_nickel package was collapsed into ``instruments/nickel/``; the
    profile is now loaded by path (mirroring ``stips.core.config.load()``)
    rather than via ``load_profile("lsst.obs.nickel")``.
    """
    if str(NICKEL_PROFILE.parent) not in sys.path:
        sys.path.insert(0, str(NICKEL_PROFILE.parent))
    spec = importlib.util.spec_from_file_location(
        "_stips_nickel_profile", NICKEL_PROFILE
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.profile


class TestNickelCollectionGolden(unittest.TestCase):
    def setUp(self):
        self.c = CollectionNames("20230519", "ts1", prefix="Nickel")

    def test_input_attrs(self):
        # Inputs echoed back unchanged.
        self.assertEqual(self.c.night, "20230519")
        self.assertEqual(self.c.run_ts, "ts1")

    def test_collection_strings(self):
        # Raw ingest.
        self.assertEqual(self.c.raw_run, "Nickel/raw/20230519/ts1")

        # Calibration production (cp_pipe bias/flat).
        self.assertEqual(self.c.cp_bias, "Nickel/cp/20230519/bias/ts1")
        self.assertEqual(self.c.cp_bias_run, "Nickel/cp/20230519/bias/ts1/run")
        self.assertEqual(self.c.cp_flat, "Nickel/cp/20230519/flat/ts1")
        self.assertEqual(self.c.cp_flat_run, "Nickel/cp/20230519/flat/ts1/run")

        # Curated calibrations.
        self.assertEqual(self.c.curated_run, "Nickel/calib/curated/ts1")
        self.assertEqual(self.c.curated_chain, "Nickel/calib/curated")

        # Certified calib outputs + unified chain.
        self.assertEqual(self.c.calib_out, "Nickel/calib/20230519")
        self.assertEqual(self.c.calib_chain, "Nickel/calib/current")

        # Science (processCcd) parent CHAINED + primary RUN.
        self.assertEqual(self.c.science_parent, "Nickel/runs/20230519/processCcd/ts1")
        self.assertEqual(self.c.science_run, "Nickel/runs/20230519/processCcd/ts1/run")

        # Coadd template building.
        self.assertEqual(self.c.coadd_parent, "Nickel/runs/20230519/coadd/ts1")
        self.assertEqual(self.c.coadd_run, "Nickel/runs/20230519/coadd/ts1/run")

        # Difference imaging.
        self.assertEqual(self.c.diff_parent, "Nickel/runs/20230519/diff/ts1")
        self.assertEqual(self.c.diff_run, "Nickel/runs/20230519/diff/ts1/run")

    def test_day_obs(self):
        # Local observing night -> UT day_obs (+1 day), returned as a str.
        self.assertEqual(night_to_day_obs("20230519"), "20230520")

    def test_day_obs_offset_param(self):
        # default offset preserves current Nickel behavior
        self.assertEqual(night_to_day_obs("20230519"), "20230520")
        # explicit offset is honored (genericity)
        self.assertEqual(night_to_day_obs("20230519", offset_days=0), "20230519")
        self.assertEqual(night_to_day_obs("20230519", offset_days=2), "20230521")


class TestProfileDrivenParity(unittest.TestCase):
    def test_nickel_profile_reproduces_golden(self):
        prof = _load_nickel_profile_by_path()
        c = CollectionNames("20230519", "ts1", prefix=prof.collection_prefix)
        # SAME literals as the golden (proves the threaded profile yields identical Nickel output):
        self.assertEqual(c.raw_run, "Nickel/raw/20230519/ts1")
        self.assertEqual(c.calib_chain, "Nickel/calib/current")
        self.assertEqual(c.science_parent, "Nickel/runs/20230519/processCcd/ts1")
        self.assertEqual(c.diff_parent, "Nickel/runs/20230519/diff/ts1")
        self.assertEqual(c.coadd_parent, "Nickel/runs/20230519/coadd/ts1")

    def test_synthetic_profile_is_generic(self):
        c = CollectionNames("20240101", "tsX", prefix="ctio0m9")
        self.assertEqual(c.raw_run, "ctio0m9/raw/20240101/tsX")
        self.assertEqual(c.calib_chain, "ctio0m9/calib/current")
        self.assertEqual(c.science_parent, "ctio0m9/runs/20240101/processCcd/tsX")


if __name__ == "__main__":
    unittest.main()
