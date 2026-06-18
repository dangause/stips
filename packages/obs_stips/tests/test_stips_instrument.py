"""Tests of the generic STIPS instrument class.

Stack-required: imports ``lsst.obs.base`` and builds an in-memory Butler
registry to exercise ``register()``. The test binds a profile that reuses the
real Nickel camera geometry so ``getCamera`` resolves under the stack.
"""

import tempfile
import unittest

from lsst.daf.butler import Butler
from lsst.obs.base import DefineVisitsTask
from lsst.obs.stips.formatter import StipsRawFormatter
from lsst.obs.stips.instrument import StipsInstrument
from stips import Field, InstrumentProfile, Site

PROFILE = InstrumentProfile(
    name="DemoInst",
    site=Site(37.0, -121.0, 1000.0, name=None),
    filters={"B": "B", "V": "V", "OPEN": "clear"},
    header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
    camera="camera/nickel.yaml",  # reuse the real Nickel camera geometry
    eups_package="obs_nickel",  # so getPackageDir resolves under the stack
    obs_data_package="obs_demo_data",
)


class DemoInst(StipsInstrument):
    profile = PROFILE


class TestStipsInstrument(unittest.TestCase):
    def test_getName(self):
        self.assertEqual(DemoInst.getName(), "DemoInst")
        self.assertEqual(DemoInst().getName(), "DemoInst")
        # Class-level name attribute mirrors the profile.
        self.assertEqual(DemoInst.name, "DemoInst")

    def test_policy_and_obs_data_package(self):
        inst = DemoInst()
        self.assertEqual(inst.policyName, "DemoInst")
        self.assertEqual(inst.obsDataPackage, "obs_demo_data")

    def test_filter_definitions_class_level(self):
        # Must be a class attribute available WITHOUT instantiation.
        fdefs = DemoInst.filterDefinitions
        bands = {f.band for f in fdefs}
        self.assertIn("clear", bands)
        # De-duplicated: three mappings -> three definitions.
        pfs = {f.physical_filter for f in fdefs}
        self.assertEqual(pfs, {"B", "V", "OPEN"})
        self.assertEqual(len(list(fdefs)), 3)

    def test_camera_single_ccd(self):
        cam = DemoInst().getCamera()
        self.assertEqual(len(list(cam)), 1)

    def test_raw_formatter(self):
        rf_cls = DemoInst().getRawFormatter(dataId={"detector": 0})
        self.assertIs(rf_cls, StipsRawFormatter)

    def test_define_visits_task(self):
        self.assertIs(DemoInst().getDefineVisitsTask(), DefineVisitsTask)

    def test_register_writes_instrument_and_detector(self):
        with tempfile.TemporaryDirectory() as root:
            config = Butler.makeRepo(root)
            butler = Butler(config, writeable=True)
            registry = butler.registry

            DemoInst().register(registry)

            instruments = list(registry.queryDimensionRecords("instrument"))
            self.assertEqual(len(instruments), 1)
            self.assertEqual(instruments[0].name, "DemoInst")

            detectors = list(
                registry.queryDimensionRecords("detector", instrument="DemoInst")
            )
            self.assertGreaterEqual(len(detectors), 1)
            det = detectors[0]
            self.assertEqual(det.raft, "R00")
            self.assertEqual(det.name_in_raft, "S00")


if __name__ == "__main__":
    unittest.main()
