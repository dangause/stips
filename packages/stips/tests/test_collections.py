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

    def test_prefix_defaults_to_nickel(self):
        # temporary back-compat scaffold so existing 2-arg call sites still work
        self.assertEqual(
            CollectionNames("20230519", "ts1").calib_chain, "Nickel/calib/current"
        )


if __name__ == "__main__":
    unittest.main()
