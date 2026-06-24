"""Unit tests for Gen3 Nickel raw data ingest.

Uses the generic synthesized instrument (``lsst.obs.stips.active.Instrument``,
bound to ``INSTRUMENT_DIR=instruments/nickel``) rather than the deleted
``lsst.obs.nickel.Nickel`` class. Gated on ``testdata_nickel`` so it skips when
that package is not set up.
"""

import os
import unittest
from pathlib import Path

import lsst.utils.tests
from lsst.afw.image import FilterLabel
from lsst.daf.butler import Butler, DataCoordinate
from lsst.obs.base.ingest_tests import IngestTestBase

# IngestTestBase re-imports instrumentClassName by FQN; the synthesized
# instrument resolves its profile from INSTRUMENT_DIR, so set it here.
# instruments/nickel/tests/test_ingest.py -> parents[1] == instruments/nickel
os.environ["INSTRUMENT_DIR"] = str(Path(__file__).resolve().parents[1])

testDataPackage = "testdata_nickel"
try:
    testDataDirectory = lsst.utils.getPackageDir(testDataPackage)
except Exception:
    testDataDirectory = None


@unittest.skipIf(testDataDirectory is None, "testdata_nickel must be set up")
class TestNickelIngest(IngestTestBase, lsst.utils.tests.TestCase):
    """Test ingestion of Nickel raw data."""

    ingestDir = os.path.dirname(__file__)
    instrumentClassName = "lsst.obs.stips.active.Instrument"
    filterLabel = FilterLabel(physical="B", band="b")

    # One raw
    dataIds = [dict(instrument="Nickel", exposure=89421032, detector=0)]

    @property
    def file(self):
        return os.path.join(testDataDirectory, "data", "nickel", "raw", "d1032.fits")

    @property
    def visits(self):
        # ONE_TO_ONE: each exposure becomes a visit with the same ID.
        # Build DataCoordinate keys using the repo’s universe to match the base test.
        butler = Butler(self.root, collections=[self.outputRun])
        visit_dc = DataCoordinate.standardize(
            instrument="Nickel", visit=89421032, universe=butler.dimensions
        )
        exposure_dc = DataCoordinate.standardize(
            instrument="Nickel", exposure=89421032, universe=butler.dimensions
        )
        return {visit_dc: [exposure_dc]}


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
