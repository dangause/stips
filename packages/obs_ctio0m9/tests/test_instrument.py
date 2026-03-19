"""Unit tests for obs_ctio0m9 instrument package."""

import unittest

import lsst.utils.tests


class TestCtio0m9Filters(unittest.TestCase):
    """Test filter definitions."""

    def test_filter_collection_exists(self):
        """Filter collection should be importable."""
        from lsst.obs.ctio0m9.ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS

        self.assertIsNotNone(CTIO0M9_FILTER_DEFINITIONS)

    def test_filter_count(self):
        """Should have 18 filters defined (UBVRI + calibration + combos)."""
        from lsst.obs.ctio0m9.ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS

        self.assertEqual(len(CTIO0M9_FILTER_DEFINITIONS), 18)

    def test_broadband_filters(self):
        """Should have UBVRI broadband filters."""
        from lsst.obs.ctio0m9.ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS

        names = {f.physical_filter for f in CTIO0M9_FILTER_DEFINITIONS}
        self.assertIn("U", names)
        self.assertIn("B", names)
        self.assertIn("V", names)
        self.assertIn("R", names)
        self.assertIn("I", names)


class TestCtio0m9Translator(unittest.TestCase):
    """Test metadata translator."""

    def setUp(self):
        """Create a mock FITS header."""
        self.header = {
            "INSTRUME": "cfccd",
            "DETECTOR": "Tek2K_3",
            "DATE-OBS": "2020-06-15T03:45:30.5",
            "EXPTIME": 120.0,
            "FILTER1": "V",
            "FILTER2": "OPEN",
            "IMAGETYP": "object",
            "RA": "12:34:56.78",
            "DEC": "-45:23:12.3",
            "AIRMASS": 1.234,
            "OBJECT": "test_field",
        }

    def test_can_translate(self):
        """Translator should recognize cfccd instrument."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        self.assertTrue(Ctio0m9Translator.can_translate(self.header))

    def test_cannot_translate_other(self):
        """Translator should not recognize other instruments."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        other_header = {"INSTRUME": "other_camera"}
        self.assertFalse(Ctio0m9Translator.can_translate(other_header))

    def test_to_instrument(self):
        """Should return 'ctio0m9' as instrument name."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        translator = Ctio0m9Translator(self.header)
        self.assertEqual(translator.to_instrument(), "ctio0m9")

    def test_to_physical_filter_single(self):
        """Single filter should return filter name."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        translator = Ctio0m9Translator(self.header)
        self.assertEqual(translator.to_physical_filter(), "V")

    def test_to_physical_filter_dual(self):
        """Dual filters should be concatenated and sorted."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        header = dict(self.header)
        header["FILTER1"] = "V"
        header["FILTER2"] = "ND"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_physical_filter(), "ND+V")

    def test_to_physical_filter_both_open(self):
        """Both filters open should return 'OPEN'."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        header = dict(self.header)
        header["FILTER1"] = "OPEN"
        header["FILTER2"] = "OPEN"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_physical_filter(), "OPEN")

    def test_to_physical_filter_ov_variant(self):
        """OV (open variant) should be treated as open."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        # OV alone = OPEN
        header = dict(self.header)
        header["FILTER1"] = "ov"
        header["FILTER2"] = "ov"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_physical_filter(), "OPEN")

        # CB + OV = CB (OV is ignored as open)
        header["FILTER1"] = "cb"
        header["FILTER2"] = "ov"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_physical_filter(), "CB")

    def test_to_observation_type(self):
        """Should map IMAGETYP to observation type."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        # object -> science
        translator = Ctio0m9Translator(self.header)
        self.assertEqual(translator.to_observation_type(), "science")

        # flat -> flat
        header = dict(self.header)
        header["IMAGETYP"] = "flat"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_observation_type(), "flat")

        # bias -> bias
        header["IMAGETYP"] = "bias"
        translator = Ctio0m9Translator(header)
        self.assertEqual(translator.to_observation_type(), "bias")

    def test_to_detector_name(self):
        """Should return SITE2K."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        translator = Ctio0m9Translator(self.header)
        self.assertEqual(translator.to_detector_name(), "SITE2K")

    def test_to_exposure_id_range(self):
        """Exposure ID should fit in 31 bits."""
        from lsst.obs.ctio0m9.translator import Ctio0m9Translator

        translator = Ctio0m9Translator(self.header)
        exp_id = translator.to_exposure_id()
        self.assertLess(exp_id, 2**31)
        self.assertGreater(exp_id, 0)


class TestCtio0m9Camera(unittest.TestCase):
    """Test camera geometry loading."""

    def test_camera_loads(self):
        """Camera YAML should load without error."""
        from lsst.obs.ctio0m9 import Ctio0m9

        camera = Ctio0m9().getCamera()
        self.assertIsNotNone(camera)

    def test_single_detector(self):
        """Camera should have exactly one detector."""
        from lsst.obs.ctio0m9 import Ctio0m9

        camera = Ctio0m9().getCamera()
        self.assertEqual(len(camera), 1)

    def test_detector_name(self):
        """Detector should be named SITE2K."""
        from lsst.obs.ctio0m9 import Ctio0m9

        camera = Ctio0m9().getCamera()
        det = camera[0]
        self.assertEqual(det.getName(), "SITE2K")

    def test_detector_dimensions(self):
        """Active area should be 2049x2047 (2048x2046 science + 1 pixel LSST bbox convention)."""
        from lsst.obs.ctio0m9 import Ctio0m9

        camera = Ctio0m9().getCamera()
        det = camera[0]
        bbox = det.getBBox()
        # Camera YAML defines 2048x2046 extent; LSST bbox is inclusive so adds 1
        self.assertEqual(bbox.getWidth(), 2049)
        self.assertEqual(bbox.getHeight(), 2047)


class TestCtio0m9Instrument(unittest.TestCase):
    """Test instrument class."""

    def test_instrument_name(self):
        """Instrument name should be 'ctio0m9'."""
        from lsst.obs.ctio0m9 import Ctio0m9

        self.assertEqual(Ctio0m9.getName(), "ctio0m9")

    def test_obs_data_package(self):
        """Should have curated calibrations package for defects."""
        from lsst.obs.ctio0m9 import Ctio0m9

        self.assertEqual(Ctio0m9.obsDataPackage, "obs_ctio0m9_data")

    def test_get_raw_formatter(self):
        """Should return Ctio0m9RawFormatter."""
        from lsst.obs.ctio0m9 import Ctio0m9
        from lsst.obs.ctio0m9.rawFormatter import Ctio0m9RawFormatter

        inst = Ctio0m9()
        formatter = inst.getRawFormatter({})
        self.assertEqual(formatter, Ctio0m9RawFormatter)


class MemoryTester(lsst.utils.tests.MemoryTestCase):
    """Check for memory leaks."""

    pass


def setup_module(module):
    """Set up LSST test environment."""
    lsst.utils.tests.init()


if __name__ == "__main__":
    unittest.main()
