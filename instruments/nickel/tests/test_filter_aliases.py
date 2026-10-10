"""Lock the Nickel filter alias table (raw FITS FILTNAM -> physical_filter).

Exercises the generic ``StipsTranslator`` bound to the Nickel profile through
the nameplate ``instruments.nickel.instrument.Translator``. The alias golden
values are unchanged from the legacy suite.
"""

import unittest
from pathlib import Path

import pytest

# The translator is bound through the nameplate, which requires the LSST
# stack; skip cleanly in a plain venv.
pytest.importorskip("lsst.daf.butler")

# instruments/nickel/tests/test_filter_aliases.py -> parents[1] == instruments/nickel
_INSTRUMENT_DIR = str(Path(__file__).resolve().parents[1])


def _load_translator():
    from stips.profile import import_instrument_module

    return import_instrument_module(_INSTRUMENT_DIR).Translator


NickelTranslator = _load_translator()


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
        for raw in ("IP", "ip", "I'", "i'"):
            self.assertEqual(_phys(raw), "ip")

    def test_malformed_sloan_card_as_the_stack_reads_it(self):
        """2020-2023 headers carry FILTNAM = 'r'                ' . The stack's
        FITS reader (used by ingest) returns "r", not "r'". It must still be
        the Sloan-like filter, while uppercase stays Cousins."""
        self.assertEqual(_phys("r"), "rp")
        self.assertEqual(_phys("i"), "ip")
        self.assertEqual(_phys("R"), "R")
        self.assertEqual(_phys("I"), "I")

    def test_narrowband_aliases(self):
        for raw in ("HALPHA", "halpha", "H-ALPHA", "6563/100"):
            self.assertEqual(_phys(raw), "Halpha")
        for raw in ("OIII", "oiii", "[OIII]", "5000/100"):
            self.assertEqual(_phys(raw), "OIII")

    def test_unknown_falls_back_to_clear(self):
        self.assertEqual(_phys("ZZZ"), "clear")


if __name__ == "__main__":
    unittest.main()
