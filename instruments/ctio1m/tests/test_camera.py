# This file is part of the STIPS CTIO 1.0m (Y4KCam) test suite.
#
# Developed for the LSST Data Management System.
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

"""Under-stack tests that the Y4KCam camera yaml builds a 4-amplifier Camera.

Y4KCam is the first MULTI-AMPLIFIER camera in STIPS: a single CCD read out
through four amplifiers (2x2 quadrants). These tests exercise the GENERIC STIPS
machinery (``lsst.obs.stips.active.Instrument`` synthesized from
``INSTRUMENT_DIR=instruments/ctio1m``) and assert the assembled afw ``Camera``
has exactly one detector with FOUR amplifiers.
"""

import unittest

import pytest

pytest.importorskip("lsst.utils.tests")

import lsst.utils.tests  # noqa: E402
from ctio1m_helpers import active_instrument_dir  # noqa: E402


class TestY4KCamCamera(unittest.TestCase):
    def test_camera_builds_with_four_amps(self):
        with active_instrument_dir() as active:
            cam = active.Instrument().getCamera()

            dets = list(cam)
            self.assertEqual(len(dets), 1)

            det = dets[0]
            self.assertEqual(det.getId(), 0)
            self.assertEqual(det.getName(), "CCD0")

            # The key new assertion: FOUR amplifiers (codebase idiom: list(det)).
            amps = list(det)
            self.assertEqual(len(amps), 4)
            self.assertEqual([a.getName() for a in amps], ["A00", "A01", "A02", "A03"])

            # LSST bbox max-corner is inclusive, so a [[0,0],[4064,4064]] yaml may
            # yield width/height 4064 or 4065 depending on stack version.
            bbox = det.getBBox()
            self.assertIn(bbox.getWidth(), (4064, 4065))
            self.assertIn(bbox.getHeight(), (4064, 4065))


class MemoryTester(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
