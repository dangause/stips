import unittest

from stips import CameraSpec, InstrumentProfile, Site


class TestCameraSpec(unittest.TestCase):
    def test_fields_and_defaults(self):
        s = CameraSpec(
            nx=1024, ny=1024, pixel_size_um=30.0, plate_scale_arcsec_per_pixel=0.368
        )
        self.assertEqual((s.nx, s.ny), (1024, 1024))
        self.assertEqual(s.pixel_size_um, 30.0)
        self.assertEqual(s.plate_scale_arcsec_per_pixel, 0.368)
        self.assertFalse(s.flip_x)
        self.assertFalse(s.flip_y)
        self.assertEqual(s.gain, 1.0)
        self.assertEqual(s.read_noise, 0.0)
        self.assertEqual(s.saturation, 65535.0)
        self.assertIsNone(s.name)

    def test_profile_accepts_cameraspec(self):
        p = InstrumentProfile(
            name="Demo",
            site=Site(0.0, 0.0, 0.0),
            filters={"clear": None},
            header_map={},
            camera=CameraSpec(
                nx=10, ny=10, pixel_size_um=15.0, plate_scale_arcsec_per_pixel=0.2
            ),
        )
        self.assertIsInstance(p.camera, CameraSpec)
