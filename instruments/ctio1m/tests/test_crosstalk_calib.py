# This file is part of the STIPS CTIO 1.0m (Y4KCam) test suite.
#
# Developed for the LSST Data Management System.
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

"""Under-stack tests that a CrosstalkCalib builds from the Y4KCam camera.

Exercises the declarative-crosstalk build core (``make_crosstalk_calib``) against
the real assembled 4-amplifier Y4KCam detector: the matrix dimension must match
the amp count, the amp ordering is preserved, and the calib round-trips through
ECSV (the format ``butler write/certify`` uses).
"""

import functools
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("lsst.utils.tests")

import lsst.utils.tests  # noqa: E402
from stips.pipeline_tools.build_crosstalk_calib import (
    make_crosstalk_calib,
)  # noqa: E402
from stips.testing.instrument_contract import (  # noqa: E402
    active_instrument_dir as _active_instrument_dir,
)

# instruments/ctio1m/tests/... -> parents[1] == instruments/ctio1m
active_instrument_dir = functools.partial(
    _active_instrument_dir, Path(__file__).resolve().parents[1]
)


def _y4kcam_detector(active):
    return list(active.Instrument().getCamera())[0]


class TestY4KCamCrosstalkCalib(unittest.TestCase):
    def test_builds_4x4_calib_from_detector(self):
        coeffs = [
            [0.0, 1e-4, 2e-4, 3e-4],
            [3e-4, 0.0, 2e-4, 1e-4],
            [4e-4, 5e-4, 0.0, 6e-4],
            [7e-4, 8e-4, 9e-4, 0.0],
        ]
        with active_instrument_dir() as active:
            calib = make_crosstalk_calib(_y4kcam_detector(active), coeffs, "adu")

        self.assertTrue(calib.hasCrosstalk)
        self.assertEqual(calib.nAmp, 4)
        self.assertEqual(calib.crosstalkShape, (4, 4))
        self.assertEqual(calib.crosstalkRatiosUnits, "adu")
        np.testing.assert_allclose(calib.coeffs, np.array(coeffs))

    def test_zero_placeholder_is_a_valid_noop(self):
        zeros = [[0.0] * 4 for _ in range(4)]
        with active_instrument_dir() as active:
            calib = make_crosstalk_calib(_y4kcam_detector(active), zeros)
        np.testing.assert_array_equal(calib.coeffs, np.zeros((4, 4)))

    def test_wrong_amp_count_is_rejected(self):
        # A 2x2 matrix against the 4-amp detector must fail loudly.
        with active_instrument_dir() as active:
            det = _y4kcam_detector(active)
            with self.assertRaises(ValueError):
                make_crosstalk_calib(det, [[0.0, 1e-4], [1e-4, 0.0]])

    def test_ecsv_round_trip_preserves_matrix(self):
        coeffs = [
            [0.0, 1e-4, 2e-4, 3e-4],
            [3e-4, 0.0, 2e-4, 1e-4],
            [4e-4, 5e-4, 0.0, 6e-4],
            [7e-4, 8e-4, 9e-4, 0.0],
        ]
        from lsst.ip.isr import CrosstalkCalib

        with active_instrument_dir() as active:
            calib = make_crosstalk_calib(_y4kcam_detector(active), coeffs)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "crosstalk.ecsv")
            calib.writeText(path)
            restored = CrosstalkCalib.readText(path)

        np.testing.assert_allclose(restored.coeffs, np.array(coeffs))
        self.assertEqual(restored.nAmp, 4)


class MemoryTester(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
