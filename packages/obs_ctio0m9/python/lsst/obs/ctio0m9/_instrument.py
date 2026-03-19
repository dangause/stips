"""Instrument class for the CTIO/SMARTS 0.9m telescope."""

from __future__ import annotations

__all__ = ["Ctio0m9"]

import os

from lsst.obs.base import DefineVisitsTask, Instrument, VisitSystem, yamlCamera
from lsst.utils import getPackageDir
from lsst.utils.introspection import get_full_type_name

from .ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS
from .translator import Ctio0m9Translator


class Ctio0m9(Instrument):
    """Instrument class for the CTIO/SMARTS 0.9m telescope with Tek2K CCD.

    This instrument supports single-amplifier readout mode only.
    The raw FITS header has INSTRUME="cfccd" (Cassegrain Focus CCD).
    """

    name = "ctio0m9"
    policyName = "ctio0m9"
    obsDataPackage = "obs_ctio0m9_data"  # Curated calibrations (defects)
    filterDefinitions = CTIO0M9_FILTER_DEFINITIONS
    translatorClass = Ctio0m9Translator

    _camera = None  # Cache for parsed camera

    def __init__(self, collection_prefix: str | None = None):
        super().__init__(collection_prefix=collection_prefix)

    def getCamera(self):
        """Return the camera geometry from YAML."""
        path = os.path.join(getPackageDir("obs_ctio0m9"), "camera", "ctio0m9.yaml")
        return yamlCamera.makeCamera(path)

    @classmethod
    def getName(cls):
        """Return the instrument name."""
        return "ctio0m9"

    def getRawFormatter(self, dataId):
        """Return the raw formatter class."""
        from .rawFormatter import Ctio0m9RawFormatter

        return Ctio0m9RawFormatter

    def getDefineVisitsTask(self):
        """One exposure = one visit."""
        return DefineVisitsTask

    def register(self, registry, update: bool = False):
        """Register the instrument with a Butler registry."""
        camera = self.getCamera()
        obsMax = 2**31

        with registry.transaction():
            registry.syncDimensionData(
                "instrument",
                {
                    "name": self.getName(),
                    "class_name": get_full_type_name(type(self)),
                    "detector_max": len(camera),
                    "visit_max": obsMax,
                    "visit_system": VisitSystem.ONE_TO_ONE.value,
                    "exposure_max": obsMax,
                },
                update=update,
            )

            # Single-CCD camera
            for det in camera:
                registry.syncDimensionData(
                    "detector",
                    {
                        "instrument": self.getName(),
                        "id": int(det.getId()),
                        "full_name": det.getName(),
                        "name_in_raft": "S00",
                        "raft": "R00",
                        "purpose": det.getType().name,
                    },
                    update=update,
                )

            self._registerFilters(registry, update=update)
