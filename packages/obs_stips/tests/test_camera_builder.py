import math
import os
import tempfile
import textwrap
import unittest

import lsst.afw.cameraGeom as cg
import lsst.geom as geom
from lsst.obs.stips.camera_builder import (
    _axis_map,
    build_camera,
    build_yaml_camera,
)
from stips import CameraSpec

# Minimal 2-amp-per-axis (4-amp) yaml with central-cross overscan, mirroring
# the Y4KCam layout: 2032 imaging + 20 overscan per amp -> 4104 raw / 4064 trimmed.
_FOURAMP_YAML = textwrap.dedent(
    """
    name: TestCam
    plateScale: 19.27
    transforms:
      nativeSys: FocalPlane
      FieldAngle: {transformType: radial, coeffs: [0.0, 1.0, 0.0]}
    CCDs:
      CCD0:
        detectorType: 0
        physicalType: SCIENCE
        id: 0
        serial: TestCam-1
        refpos: [2032.0, 2032.0]
        offset: [0.0, 0.0, 0.0]
        bbox: [[0, 0], [4064, 4064]]
        pixelSize: [0.015, 0.015]
        transformDict: {nativeSys: Pixels, transforms: {}}
        transposeDetector: false
        pitch: 0.0
        yaw: 0.0
        roll: 0.0
        amplifiers:
          A00:
            perAmpData: true
            dataExtent: [2032, 2032]
            readCorner: UR
            ixy: [0, 0]
            rawBBox: [[0, 0], [2052, 2052]]
            rawDataBBox: [[0, 0], [2032, 2032]]
            rawSerialPrescanBBox: [[0, 0], [0, 0]]
            rawSerialOverscanBBox: [[2032, 0], [20, 2032]]
            rawParallelPrescanBBox: [[0, 0], [0, 0]]
            rawParallelOverscanBBox: [[0, 2032], [2032, 20]]
            gain: 1.4
            readNoise: 7.0
            saturation: 65535
            linearityType: PROPORTIONAL
            linearityThreshold: 0
            linearityMax: 60000
            linearityCoeffs: [0.0, 1.0]
            hdu: 0
            flipXY: [false, false]
          A01:
            perAmpData: true
            dataExtent: [2032, 2032]
            readCorner: UL
            ixy: [1, 0]
            rawBBox: [[2052, 0], [2052, 2052]]
            rawDataBBox: [[2072, 0], [2032, 2032]]
            rawSerialPrescanBBox: [[0, 0], [0, 0]]
            rawSerialOverscanBBox: [[2052, 0], [20, 2032]]
            rawParallelPrescanBBox: [[0, 0], [0, 0]]
            rawParallelOverscanBBox: [[2072, 2032], [2032, 20]]
            gain: 1.4
            readNoise: 7.0
            saturation: 65535
            linearityType: PROPORTIONAL
            linearityThreshold: 0
            linearityMax: 60000
            linearityCoeffs: [0.0, 1.0]
            hdu: 0
            flipXY: [false, false]
          A02:
            perAmpData: true
            dataExtent: [2032, 2032]
            readCorner: LR
            ixy: [0, 1]
            rawBBox: [[0, 2052], [2052, 2052]]
            rawDataBBox: [[0, 2072], [2032, 2032]]
            rawSerialPrescanBBox: [[0, 0], [0, 0]]
            rawSerialOverscanBBox: [[2032, 2072], [20, 2032]]
            rawParallelPrescanBBox: [[0, 0], [0, 0]]
            rawParallelOverscanBBox: [[0, 2052], [2032, 20]]
            gain: 1.4
            readNoise: 7.0
            saturation: 65535
            linearityType: PROPORTIONAL
            linearityThreshold: 0
            linearityMax: 60000
            linearityCoeffs: [0.0, 1.0]
            hdu: 0
            flipXY: [false, false]
          A03:
            perAmpData: true
            dataExtent: [2032, 2032]
            readCorner: LL
            ixy: [1, 1]
            rawBBox: [[2052, 2052], [2052, 2052]]
            rawDataBBox: [[2072, 2072], [2032, 2032]]
            rawSerialPrescanBBox: [[0, 0], [0, 0]]
            rawSerialOverscanBBox: [[2052, 2072], [20, 2032]]
            rawParallelPrescanBBox: [[0, 0], [0, 0]]
            rawParallelOverscanBBox: [[2072, 2052], [2032, 20]]
            gain: 1.4
            readNoise: 7.0
            saturation: 65535
            linearityType: PROPORTIONAL
            linearityThreshold: 0
            linearityMax: 60000
            linearityCoeffs: [0.0, 1.0]
            hdu: 0
            flipXY: [false, false]
    """
)


class TestCameraBuilder(unittest.TestCase):
    def test_builds_single_ccd_camera_with_correct_scale(self):
        spec = CameraSpec(
            nx=1024,
            ny=1024,
            pixel_size_um=30.0,
            plate_scale_arcsec_per_pixel=0.368,
            flip_y=True,
            gain=1.8,
        )
        cam = build_camera(spec, "Demo")
        self.assertIsInstance(cam, cg.Camera)
        dets = list(cam)
        self.assertEqual(len(dets), 1)
        det = dets[0]
        # bbox max-corner parity (inclusive), matching the Nickel yaml convention
        self.assertEqual(det.getBBox().getMax(), geom.Point2I(1024, 1024))
        # on-sky scale: step 1 pixel in the focal plane, read the field angle
        tr = det.getTransform(cg.PIXELS, cg.FIELD_ANGLE)
        p0 = tr.applyForward(geom.Point2D(0.0, 0.0))
        p1 = tr.applyForward(geom.Point2D(1.0, 0.0))
        scale_arcsec = math.degrees(math.hypot(p1[0] - p0[0], p1[1] - p0[1])) * 3600.0
        self.assertAlmostEqual(scale_arcsec, 0.368, places=3)


class TestBinning(unittest.TestCase):
    def test_axis_map_imaging_compresses_overscan_fixed(self):
        # 2032 imaging + 20 overscan per amp, 2x2 binned.
        t = _axis_map(2032, 20, 2)
        self.assertEqual(t(0), 0)
        self.assertEqual(t(2032), 1016)  # end of left imaging -> /2
        self.assertEqual(t(2052), 1036)  # + left overscan (fixed 20)
        self.assertEqual(t(2072), 1056)  # + right overscan (fixed 20)
        self.assertEqual(t(4104), 2072)  # full raw axis -> binned NAXIS

    def test_axis_map_rejects_indivisible_imaging(self):
        with self.assertRaises(ValueError):
            _axis_map(2033, 20, 2)

    def _build(self, binning):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(_FOURAMP_YAML)
            path = fh.name
        try:
            return build_yaml_camera(path, binning=binning)
        finally:
            os.unlink(path)

    def test_unbinned_matches_yaml_geometry(self):
        det = list(self._build(1))[0]
        amps = list(det)
        raw_x = max(a.getRawBBox().getMaxX() for a in amps) + 1
        self.assertEqual(raw_x, 4104)
        self.assertEqual(len(amps), 4)

    def test_binned_geometry(self):
        det = list(self._build(2))[0]
        amps = list(det)
        # raw frame tiles to the binned NAXIS (2072), not a naive 4104/2=2052.
        raw_x = max(a.getRawBBox().getMaxX() for a in amps) + 1
        raw_y = max(a.getRawBBox().getMaxY() for a in amps) + 1
        self.assertEqual((raw_x, raw_y), (2072, 2072))
        # A01: 20px overscan preserved at the inner (left) edge, 1016 imaging.
        a01 = amps[1]
        self.assertEqual(a01.getRawSerialOverscanBBox().getWidth(), 20)
        self.assertEqual(a01.getRawDataBBox().getWidth(), 1016)


if __name__ == "__main__":
    unittest.main()
