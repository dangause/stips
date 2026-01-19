import os
import unittest

import lsst.afw.fits
import lsst.afw.geom
import lsst.afw.image
import lsst.obs.nickel  # Your obs package
import lsst.utils
import lsst.utils.tests
from lsst.daf.butler import (
    DataCoordinate,
    DatasetRef,
    DatasetType,
    DimensionUniverse,
    FileDescriptor,
    Location,
    StorageClassFactory,
)
from lsst.obs.nickel.rawFormatter import NickelRawFormatter  # Adjust path if needed

testDataPackage = "testdata_nickel"
try:
    testDataDirectory = lsst.utils.getPackageDir(testDataPackage)
except LookupError:
    testDataDirectory = None

storageClass = StorageClassFactory().getStorageClass("Exposure")


def make_dataset_ref(detector="CCD0"):
    universe = DimensionUniverse()
    dataset_type = DatasetType(
        "raw", ("instrument", "detector"), storageClass, universe=universe
    )
    data_id = DataCoordinate.standardize(
        instrument="Nickel", detector=detector, universe=universe
    )
    return DatasetRef(dataset_type, data_id, "test")


@unittest.skipIf(testDataDirectory is None, "testdata_nickel must be set up")
class NickelRawFormatterTestCase(lsst.utils.tests.TestCase):
    def setUp(self):
        relpath = "data/nickel/raw/d1032.fits"
        self.filename = os.path.join(testDataDirectory, relpath)
        location = Location(testDataDirectory, relpath)
        self.fileDescriptor = FileDescriptor(location, storageClass)

    def test_read_metadata(self):
        expected = lsst.afw.fits.readMetadata(self.filename, hdu=0)

        formatter = NickelRawFormatter(self.fileDescriptor, ref=make_dataset_ref())
        metadata = formatter.read(component="metadata")

        self.assertEqual(metadata["EXPTIME"], expected["EXPTIME"])
        self.assertEqual(metadata["FILTNAM"], expected["FILTNAM"])
        self.assertEqual(metadata["INSTRUME"], expected["INSTRUME"])

    def test_read_image(self):
        expected = lsst.afw.image.ImageF(self.filename, hdu=0)

        formatter = NickelRawFormatter(self.fileDescriptor, ref=make_dataset_ref())
        image = formatter.read(component="image")

        self.assertImagesEqual(image, expected)


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
