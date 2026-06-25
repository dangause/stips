import unittest

from stips.collections import CollectionNames


class TestCollectionNames(unittest.TestCase):
    def test_nickel_prefix_parity(self):
        c = CollectionNames("20230519", "ts1", prefix="Nickel")
        self.assertEqual(c.raw_run, "Nickel/raw/20230519/ts1")
        self.assertEqual(c.calib_chain, "Nickel/calib/current")
        self.assertEqual(c.science_parent, "Nickel/runs/20230519/processCcd/ts1")
        self.assertEqual(c.diff_parent, "Nickel/runs/20230519/diff/ts1")

    def test_other_prefix(self):
        c = CollectionNames("20240101", "tsX", prefix="ctio0m9")
        self.assertEqual(c.raw_run, "ctio0m9/raw/20240101/tsX")
        self.assertEqual(c.calib_chain, "ctio0m9/calib/current")
        self.assertEqual(c.science_parent, "ctio0m9/runs/20240101/processCcd/tsX")

    def test_crosstalk_collections(self):
        c = CollectionNames("20230519", "ts1", prefix="CTIO1m")
        # RUN holding the freshly built/measured calib, before certification.
        self.assertEqual(c.crosstalk_gen, "CTIO1m/calib/crosstalk/gen/ts1")
        # CALIBRATION collection the calib is certified into (chained into curated).
        self.assertEqual(c.crosstalk_calib, "CTIO1m/calib/crosstalk")
        # The crosstalk calib is reachable via the existing curated chain.
        self.assertEqual(c.curated_chain, "CTIO1m/calib/curated")

    def test_prefix_is_required(self):
        # The transitional prefix="Nickel" default has been removed; prefix is now
        # a required keyword-only arg. Omitting it must raise TypeError.
        with self.assertRaises(TypeError):
            CollectionNames("20230519", "ts1")


if __name__ == "__main__":
    unittest.main()
