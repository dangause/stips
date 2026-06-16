# This file is part of obs_nickel.
#
# Developed for the LSST Data Management System.
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

"""Tests of the Nickel instrument class."""

import unittest

import lsst.obs.nickel
import lsst.utils.tests
from lsst.obs.base import DefineVisitsTask

# tests/test_instrument_extras.py
from lsst.obs.nickel import Nickel
from lsst.obs.nickel.nickelFilters import NICKEL_FILTER_DEFINITIONS


class TestNickelExtras(unittest.TestCase):
    def setUp(self):
        self.inst = Nickel()

    def test_name_consistency(self):
        # Class attribute and method should agree
        self.assertEqual(self.inst.name, "Nickel")
        self.assertEqual(self.inst.getName(), "Nickel")

    def test_camera_basics(self):
        cam = self.inst.getCamera()
        # One detector only
        self.assertEqual(len(list(cam)), 1)

        det = next(iter(cam))
        # ID and names from your nickel.yaml
        self.assertEqual(det.getId(), 0)
        self.assertEqual(det.getName(), "CCD0")

        # The detector bbox should be 1024x1024 (binned imaging area)
        bbox = det.getBBox()
        self.assertEqual(bbox.getWidth(), 1025)
        self.assertEqual(bbox.getHeight(), 1025)

        # One amplifier named A00
        amps = list(det)
        self.assertEqual(len(amps), 1)
        self.assertEqual(amps[0].getName(), "A00")

    def test_raw_formatter(self):
        # Should return the NickelRawFormatter class (not an instance)
        rf_cls = self.inst.getRawFormatter(dataId={"detector": 0})
        from lsst.obs.nickel.rawFormatter import NickelRawFormatter

        self.assertIs(rf_cls, NickelRawFormatter)

    def test_define_visits_task(self):
        # One exposure = one visit
        self.assertIs(self.inst.getDefineVisitsTask(), DefineVisitsTask)

    def test_filters_registered(self):
        # Broadband BVRI + clear, plus Sloan-like (gp/rp) and narrowband
        # (Halpha/OIII) filters used for extended-object workflows.
        pfs = {fd.physical_filter for fd in NICKEL_FILTER_DEFINITIONS}
        self.assertEqual(
            pfs,
            {"B", "V", "R", "I", "clear", "gp", "rp", "Halpha", "OIII"},
        )

        bands = {fd.band for fd in NICKEL_FILTER_DEFINITIONS if fd.band is not None}
        self.assertEqual(bands, {"b", "v", "r", "i", "gp", "rp", "halpha", "oiii"})

        # Ensure there are no duplicate physical_filter entries
        self.assertEqual(len(pfs), len(list(NICKEL_FILTER_DEFINITIONS)))


class MemoryTester(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
