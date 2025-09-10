from __future__ import annotations

import os
from lsst.obs.base._instrument import Instrument
# imports
from lsst.obs.base import yamlCamera
from lsst.obs.base import DefineVisitsTask, VisitSystem
from lsst.utils.introspection import get_full_type_name
from lsst.utils import getPackageDir

from .nickelFilters import NICKEL_FILTER_DEFINITIONS
from .translator import NickelTranslator


__all__ = ["Nickel"]


class Nickel(Instrument):
    """Instrument class for the Nickel telescope at Lick Observatory."""

    name = "Nickel"
    filterDefinitions = NICKEL_FILTER_DEFINITIONS
    translatorClass = NickelTranslator

    # cache for the parsed camera
    _camera = None

    def __init__(self, collection_prefix: str | None = None):
        super().__init__(collection_prefix=collection_prefix)

    def getCamera(self):
        path = os.path.join(getPackageDir("obs_nickel"), "camera", "nickel.yaml")
        return yamlCamera.makeCamera(path)


    @classmethod
    def getName(cls):
        return "Nickel"

    def register(self, registry, update: bool = False):
        camera = self.getCamera()
        obsMax = 2**31
        with registry.transaction():
            registry.syncDimensionData(
                "instrument",
                {
                    "name": self.getName(),
                    "class_name": get_full_type_name(type(self)),
                    "detector_max": len(camera),  # single-CCD camera
                    "visit_max": obsMax,
                    "visit_system": VisitSystem.ONE_TO_ONE.value,
                    "exposure_max": obsMax,
                },
                update=update,
            )

            # Single-CCD camera; choose stable raft/slot labels
            for det in camera:
                registry.syncDimensionData(
                    "detector",
                    {
                        "instrument": self.getName(),
                        "id": int(det.getId()),
                        "full_name": det.getName(),
                        "name_in_raft": "S00",   # there is no raft, but need something stable
                        "raft": "R00",           # there is no raft, but need something stable
                        "purpose": det.getType().name,
                    },
                    update=update,
                )

            self._registerFilters(registry, update=update)

    def getRawFormatter(self, dataId):
        # local import to prevent circular dependency

        from .rawFormatter import NickelRawFormatter
        return NickelRawFormatter

    def getDefineVisitsTask(self):
        """One exposure = one visit."""
        return DefineVisitsTask
