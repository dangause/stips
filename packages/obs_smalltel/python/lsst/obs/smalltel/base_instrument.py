"""Generic instrument base class for single-CCD small telescopes."""

from __future__ import annotations

__all__ = ("GenericSmallTelInstrument",)

from pathlib import Path

import yaml

try:
    from lsst.obs.base import (
        DefineVisitsTask,
        FilterDefinition,
        FilterDefinitionCollection,
        VisitSystem,
        yamlCamera,
    )
    from lsst.obs.base._instrument import Instrument
    from lsst.utils.introspection import get_full_type_name

    _LSST_AVAILABLE = True
except ImportError:
    _LSST_AVAILABLE = False

# Conditional base class: use lsst.obs.base.Instrument if available
_Base = Instrument if _LSST_AVAILABLE else object


class GenericSmallTelInstrument(_Base):
    """Base instrument for single-CCD small telescopes.

    Subclasses set ``instrument_name`` and ``config_dir``.
    Everything else loads from YAML in instruments/{config_dir}/.
    """

    instrument_name: str  # e.g., "Nickel"
    config_dir: str  # subdirectory under instruments/

    def __init__(self, collection_prefix=None):
        if _LSST_AVAILABLE:
            super().__init__(collection_prefix=collection_prefix)

    @classmethod
    def getName(cls) -> str:
        return cls.instrument_name

    def getCamera(self):
        camera_yaml = self._config_path("camera.yaml")
        return yamlCamera.makeCamera(camera_yaml)

    @property
    def filterDefinitions(self):
        """Load filter definitions from filters.yaml. Cached after first access."""
        if not hasattr(self, "_filter_defs"):
            filters_config = self._load_yaml("filters.yaml")
            self._filter_defs = FilterDefinitionCollection(
                *[
                    FilterDefinition(
                        f["name"],
                        band=f.get("band"),
                        doc=f.get("doc", ""),
                    )
                    for f in filters_config["filters"]
                ]
            )
        return self._filter_defs

    def register(self, registry, update=False):
        instrument_config = self._load_yaml("instrument.yaml")
        camera = self.getCamera()
        with registry.transaction():
            registry.syncDimensionData(
                "instrument",
                {
                    "name": self.getName(),
                    "class_name": get_full_type_name(type(self)),
                    "detector_max": len(camera),
                    "visit_max": 2**31,
                    "visit_system": VisitSystem[
                        instrument_config.get("visit_system", "ONE_TO_ONE")
                    ].value,
                    "exposure_max": 2**31,
                },
                update=update,
            )
            for det in camera:
                registry.syncDimensionData(
                    "detector",
                    {
                        "instrument": self.getName(),
                        "id": int(det.getId()),
                        "full_name": det.getName(),
                        "name_in_raft": "S00",  # stable label for single-CCD
                        "raft": "R00",
                        "purpose": det.getType().name,
                    },
                    update=update,
                )
            self._registerFilters(registry, update=update)

    def getRawFormatter(self, dataId):
        raise NotImplementedError(
            f"{type(self).__name__} must implement getRawFormatter()"
        )

    def getDefineVisitsTask(self):
        return DefineVisitsTask

    @property
    def policyName(self):
        config = self._load_yaml("instrument.yaml")
        return config.get("policyName", self.instrument_name)

    @property
    def obsDataPackage(self):
        config = self._load_yaml("instrument.yaml")
        return config.get("obsDataPackage")

    @classmethod
    def _package_root(cls) -> Path:
        """Resolve the obs_smalltel package root directory."""
        try:
            from lsst.utils import getPackageDir

            return Path(getPackageDir("obs_smalltel"))
        except (ImportError, LookupError):
            return Path(__file__).parent.parent.parent.parent.parent

    def _config_path(self, filename: str) -> Path:
        """Resolve path to a YAML config in instruments/{config_dir}/."""
        return self._package_root() / "instruments" / self.config_dir / filename

    def _load_yaml(self, filename: str) -> dict:
        """Load and parse a YAML config file."""
        with open(self._config_path(filename)) as f:
            return yaml.safe_load(f)
