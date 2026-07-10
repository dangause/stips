# This file is part of the STIPS reference-instrument (Nickel) test suite.
#
# Developed for the LSST Data Management System.
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

"""Tests of the synthesized STIPS instrument bound to the Nickel profile.

These run against the GENERIC machinery: ``lsst.obs.stips.active.Instrument``
synthesized from ``INSTRUMENT_DIR=instruments/nickel`` (not the deleted
``lsst.obs.nickel.Nickel`` class). The assertions on name/camera/filters/
detectors are unchanged from the legacy suite.
"""

import importlib
import os
import unittest
from pathlib import Path

import pytest

pytest.importorskip("lsst.obs.base")

import lsst.utils.tests  # noqa: E402
from lsst.obs.base import DefineVisitsTask  # noqa: E402

# instruments/nickel/tests/test_instrument.py -> parents[1] == instruments/nickel
_INSTRUMENT_DIR = str(Path(__file__).resolve().parents[1])


def _load_active():
    """Set INSTRUMENT_DIR to the reference Nickel dir and (re)load active."""
    os.environ["INSTRUMENT_DIR"] = _INSTRUMENT_DIR
    import lsst.obs.stips.active as active

    return importlib.reload(active)


class TestNickelInstrument(unittest.TestCase):
    def setUp(self):
        self._prev_instrument_dir = os.environ.get("INSTRUMENT_DIR")
        self.active = _load_active()
        self.Instrument = self.active.Instrument
        self.inst = self.Instrument()

    def tearDown(self):
        if self._prev_instrument_dir is None:
            os.environ.pop("INSTRUMENT_DIR", None)
        else:
            os.environ["INSTRUMENT_DIR"] = self._prev_instrument_dir

    def test_name_consistency(self):
        # Class attribute and method should agree
        self.assertEqual(self.inst.name, "Nickel")
        self.assertEqual(self.inst.getName(), "Nickel")

    def test_camera_basics(self):
        cam = self.inst.getCamera()
        # One detector only
        self.assertEqual(len(list(cam)), 1)

        det = next(iter(cam))
        # ID and names from nickel.yaml
        self.assertEqual(det.getId(), 0)
        self.assertEqual(det.getName(), "CCD0")

        # The detector bbox should be 1025x1025 (binned imaging area)
        bbox = det.getBBox()
        self.assertEqual(bbox.getWidth(), 1025)
        self.assertEqual(bbox.getHeight(), 1025)

        # One amplifier named A00
        amps = list(det)
        self.assertEqual(len(amps), 1)
        self.assertEqual(amps[0].getName(), "A00")

    def test_raw_formatter(self):
        # Should return the synthesized RawFormatter class (not an instance)
        rf_cls = self.inst.getRawFormatter(dataId={"detector": 0})
        self.assertIs(rf_cls, self.active.RawFormatter)

    def test_define_visits_task(self):
        # One exposure = one visit
        self.assertIs(self.inst.getDefineVisitsTask(), DefineVisitsTask)

    def test_filters_registered(self):
        # Broadband BVRI + clear, plus Sloan-like (gp/rp) and narrowband
        # (Halpha/OIII) filters used for extended-object workflows.
        filter_definitions = self.Instrument.filterDefinitions
        pfs = {fd.physical_filter for fd in filter_definitions}
        self.assertEqual(
            pfs,
            {"B", "V", "R", "I", "clear", "gp", "rp", "Halpha", "OIII"},
        )

        bands = {fd.band for fd in filter_definitions if fd.band is not None}
        self.assertEqual(bands, {"b", "v", "r", "i", "gp", "rp", "halpha", "oiii"})

        # Ensure there are no duplicate physical_filter entries
        self.assertEqual(len(pfs), len(list(filter_definitions)))


class MemoryTester(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
