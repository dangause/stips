"""Tests of the generic STIPS instrument class.

Stack-required: imports ``lsst.obs.base`` and builds an in-memory Butler
registry to exercise ``register()``. The test binds a profile that reuses the
real Nickel camera geometry; ``getCamera`` loads the camera yaml BY PATH from
INSTRUMENT_DIR (set in setUp to instruments/nickel).
"""

import os
import tempfile
import unittest
from pathlib import Path

from lsst.daf.butler import Butler
from lsst.obs.base import DefineVisitsTask
from lsst.obs.stips.formatter import StipsRawFormatter
from lsst.obs.stips.instrument import StipsInstrument
from stips import Field, InstrumentProfile, Site

# instruments/nickel/ holds the real camera yaml (camera/nickel.yaml). getCamera
# loads it by path from INSTRUMENT_DIR, so the camera-loading tests point
# INSTRUMENT_DIR here. tests/ -> obs_stips -> packages -> repo root => parents[3].
NICKEL_INSTRUMENT_DIR = Path(__file__).resolve().parents[3] / "instruments" / "nickel"

PROFILE = InstrumentProfile(
    name="DemoInst",
    site=Site(37.0, -121.0, 1000.0, name=None),
    filters={"B": "B", "V": "V", "OPEN": "clear"},
    header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
    camera="camera/nickel.yaml",  # reuse the real Nickel camera geometry
    obs_data_package="obs_demo_data",
)


class DemoInst(StipsInstrument):
    profile = PROFILE


class TestStipsInstrument(unittest.TestCase):
    def setUp(self):
        # getCamera fails loud without INSTRUMENT_DIR; point it at the real
        # instruments/nickel dir (whose camera/nickel.yaml matches profile.camera).
        self._old_instrument_dir = os.environ.get("INSTRUMENT_DIR")
        os.environ["INSTRUMENT_DIR"] = str(NICKEL_INSTRUMENT_DIR)

    def tearDown(self):
        if self._old_instrument_dir is None:
            os.environ.pop("INSTRUMENT_DIR", None)
        else:
            os.environ["INSTRUMENT_DIR"] = self._old_instrument_dir

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

    def test_getcamera_uses_instrument_dir_env(self):
        import shutil

        # getCamera loads the camera yaml BY PATH from INSTRUMENT_DIR. Build a
        # throwaway instrument dir containing the camera yaml at profile.camera
        # and prove getCamera resolves it.
        REAL_CAMERA = NICKEL_INSTRUMENT_DIR / "camera" / "nickel.yaml"
        assert REAL_CAMERA.is_file(), REAL_CAMERA
        d = Path(tempfile.mkdtemp())
        cam_dst = (
            d / DemoInst.profile.camera
        )  # match profile.camera so getCamera finds it
        cam_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL_CAMERA, cam_dst)

        os.environ["INSTRUMENT_DIR"] = str(d)
        cam = DemoInst().getCamera()
        self.assertGreaterEqual(len(cam), 1)

    def test_getcamera_requires_instrument_dir(self):
        # With INSTRUMENT_DIR unset, getCamera must fail loud (no EUPS fallback).
        os.environ.pop("INSTRUMENT_DIR", None)
        with self.assertRaises(RuntimeError):
            DemoInst().getCamera()

    def test_getcamera_dispatches_cameraspec(self):
        import os

        import lsst.afw.cameraGeom as cg
        from lsst.obs.stips.instrument import StipsInstrument
        from stips import CameraSpec, Field, InstrumentProfile, Site

        prof = InstrumentProfile(
            name="DemoCam",
            site=Site(0.0, 0.0, 0.0),
            filters={"clear": None},
            header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
            camera=CameraSpec(
                nx=1024,
                ny=1024,
                pixel_size_um=30.0,
                plate_scale_arcsec_per_pixel=0.368,
                flip_y=True,
            ),
        )

        class DemoCamInst(StipsInstrument):
            profile = prof

        # INSTRUMENT_DIR unset → would break the str path, but a CameraSpec
        # needs no file:
        old = os.environ.pop("INSTRUMENT_DIR", None)
        try:
            cam = DemoCamInst().getCamera()
        finally:
            if old is not None:
                os.environ["INSTRUMENT_DIR"] = old
        self.assertIsInstance(cam, cg.Camera)
        self.assertEqual(len(list(cam)), 1)


if __name__ == "__main__":
    unittest.main()
