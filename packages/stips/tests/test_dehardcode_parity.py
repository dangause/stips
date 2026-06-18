"""Golden: Nickel-generated collection names / day_obs BEFORE the Phase 2b de-hardcode.
After de-hardcode, the Nickel profile must reproduce these EXACT strings (byte-for-byte).
Do NOT change these literals to make a refactor pass — a difference means the de-hardcode
diverged from current Nickel behavior."""

import unittest

from stips.core.pipeline import CollectionNames, night_to_day_obs


class TestNickelCollectionGolden(unittest.TestCase):
    def setUp(self):
        self.c = CollectionNames("20230519", "ts1")

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


if __name__ == "__main__":
    unittest.main()
