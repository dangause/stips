import unittest

from stips.core.config import load_profile


class TestProfileLoad(unittest.TestCase):
    def test_loads_nickel_profile(self):
        p = load_profile("lsst.obs.nickel")
        self.assertEqual(p.name, "Nickel")
        self.assertEqual(p.collection_prefix, "Nickel")
        self.assertEqual(p.instrument_class, "lsst.obs.nickel.Nickel")
        self.assertEqual(p.skymap_name, "nickelRings-v1")
        self.assertEqual(p.skymap_collection, "skymaps/nickelRings")
        self.assertEqual(p.night_to_dayobs_offset_days, 1)
