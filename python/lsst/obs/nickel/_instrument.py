from lsst.obs.base._instrument import Instrument
from lsst.obs.base.yamlCamera import makeCamera
from lsst.obs.base import FilterDefinition, FilterDefinitionCollection, DefineVisitsTask, VisitSystem
from lsst.utils.introspection import get_full_type_name
from .nickelFilters import NICKEL_FILTER_DEFINITIONS
from .rawFormatter import NickelRawFormatter
from .translator import NickelTranslator
from lsst.utils import getPackageDir
import os

__all__ = ["Nickel"]


class Nickel(Instrument):
    """Instrument class for the Nickel telescope at Lick Observatory."""

    # name = "Nickel"
    filterDefinitions = NICKEL_FILTER_DEFINITIONS
    translatorClass = NickelTranslator

    def __init__(self, collection_prefix=None):
        super().__init__(collection_prefix=collection_prefix)

    def getCamera(self):
        path = os.path.join(getPackageDir("obs_nickel"), "camera", "nickel.yaml")
        return makeCamera(path)

    @classmethod
    def getName(self):
        return "Nickel"

    def register(self, registry, update=False):
        camera = self.getCamera()
        with registry.transaction():
            registry.syncDimensionData("instrument", {
                "name": self.getName(),
                "class_name": get_full_type_name(type(self)),
                "detector_max": len(camera),
                "visit_max": 2**25,
                "visit_system": VisitSystem.ONE_TO_ONE.value,
                "exposure_max": 2**25,
            }, update=update)

            for det in camera:
                registry.syncDimensionData("detector", {
                    "instrument": self.getName(),
                    "id": det.getId(),
                    "full_name": det.getName(),
                    "name_in_raft": det.getName(),
                    "raft": det.getName(),        
                    "purpose": str(det.getType()).split(".")[-1],
                }, update=update)

            self._registerFilters(registry, update=update)


    @property
    def filterDefinitions(self):
        return NICKEL_FILTER_DEFINITIONS

    def getRawFormatter(self, dataId):
        return NickelRawFormatter

    def getDefineVisitsTask(self):
        """Use the default DefineVisitsTask (one exposure = one visit)."""
        return DefineVisitsTask

