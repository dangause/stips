from __future__ import annotations

import os
from lsst.obs.base._instrument import Instrument
from lsst.obs.base.yamlCamera import makeCamera
from lsst.obs.base import DefineVisitsTask, VisitSystem
from lsst.utils.introspection import get_full_type_name
from lsst.utils import getPackageDir

from .nickelFilters import NICKEL_FILTER_DEFINITIONS
from .rawFormatter import NickelRawFormatter
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
        if self._camera is None:
            path = os.path.join(getPackageDir("obs_nickel"), "camera", "nickel.yaml")
            self._camera = makeCamera(path)
        return self._camera

    @classmethod
    def getName(cls) -> str:
        return cls.name

    def register(self, registry, update: bool = False):
        camera = self.getCamera()
        with registry.transaction():
            registry.syncDimensionData(
                "instrument",
                {
                    "name": self.getName(),
                    "class_name": get_full_type_name(type(self)),
                    "detector_max": len(camera),
                    "visit_max": 2**25,
                    "visit_system": VisitSystem.ONE_TO_ONE.value,
                    "exposure_max": 2**25,
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
        return NickelRawFormatter

    def getDefineVisitsTask(self):
        """One exposure = one visit."""
        return DefineVisitsTask
