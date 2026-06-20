import math
import unittest

import lsst.afw.cameraGeom as cg
import lsst.geom as geom
from lsst.obs.stips.camera_builder import build_camera
from stips import CameraSpec


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


if __name__ == "__main__":
    unittest.main()
