"""Lock the Nickel filter alias table (raw FITS FILTNAM -> physical_filter).
Stack-free: exercises the new StipsTranslator-based NickelTranslator."""

import unittest

from lsst.obs.nickel.translator import NickelTranslator


def _phys(raw):
    return NickelTranslator({"INSTRUME": "Nickel", "FILTNAM": raw}).to_physical_filter()


class TestNickelFilterAliases(unittest.TestCase):
    def test_broadband(self):
        for raw in ("B", "V", "R", "I"):
            self.assertEqual(_phys(raw), raw)

    def test_clear_aliases(self):
        for raw in ("OPEN", "open", "C", "CLEAR", "clear"):
            self.assertEqual(_phys(raw), "clear")

    def test_sloan_aliases(self):
        for raw in ("GP", "gp", "G'", "g'"):
            self.assertEqual(_phys(raw), "gp")
        for raw in ("RP", "rp", "R'", "r'"):
            self.assertEqual(_phys(raw), "rp")

    def test_narrowband_aliases(self):
        for raw in ("HALPHA", "halpha", "H-ALPHA", "6563/100"):
            self.assertEqual(_phys(raw), "Halpha")
        for raw in ("OIII", "oiii", "[OIII]", "5000/100"):
            self.assertEqual(_phys(raw), "OIII")

    def test_unknown_falls_back_to_clear(self):
        self.assertEqual(_phys("ZZZ"), "clear")


if __name__ == "__main__":
    unittest.main()
