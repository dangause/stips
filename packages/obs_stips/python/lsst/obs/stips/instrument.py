"""Generic STIPS instrument class driven by a bound :class:`InstrumentProfile`.

A binding subclass sets ``profile`` (and optionally ``translatorClass`` /
``rawFormatterClass``); everything instrument-specific is resolved from the
profile. The body of :meth:`register` is ported verbatim from the legacy
single-CCD ``Nickel`` instrument (raft ``R00`` / slot ``S00``).
"""

from __future__ import annotations

import os

from lsst.obs.base import (
    DefineVisitsTask,
    FilterDefinition,
    FilterDefinitionCollection,
    VisitSystem,
    yamlCamera,
)
from lsst.obs.base._instrument import Instrument
from lsst.utils.introspection import get_full_type_name

from .formatter import StipsRawFormatter

__all__ = ["StipsInstrument"]


class StipsInstrument(Instrument):
    """Generic LSST instrument driven by a bound ``InstrumentProfile``."""

    #: Bound by a forking subclass.
    profile = None
    #: Set by a binding subclass; defaults to the generic formatter.
    translatorClass = None
    rawFormatterClass = StipsRawFormatter

    # cache for the parsed camera
    _camera = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        profile = cls.__dict__.get("profile")
        if profile is None:
            return
        # Resolve class-level attributes from the bound profile so they are
        # readable without instantiating the subclass.
        cls.name = profile.name
        cls.policyName = profile.policy_name
        cls.obsDataPackage = profile.obs_data_package
        cls.filterDefinitions = cls._build_filter_definitions(profile)

    @staticmethod
    def _build_filter_definitions(profile) -> FilterDefinitionCollection:
        """Build a FilterDefinitionCollection from ``profile.filters``
        (physical_filter -> band), one ``FilterDefinition`` per physical_filter."""
        defs = [
            FilterDefinition(physical_filter, band=band)
            for physical_filter, band in profile.filters.items()
        ]
        return FilterDefinitionCollection(*defs)

    def __init__(self, collection_prefix: str | None = None):
        super().__init__(collection_prefix=collection_prefix)

    @classmethod
    def getName(cls):
        return cls.profile.name

    def getCamera(self):
        instrument_dir = os.environ.get("INSTRUMENT_DIR")
        if not instrument_dir:
            raise RuntimeError(
                "INSTRUMENT_DIR must be set to load the camera "
                "(it points at instruments/<name>/, containing the camera yaml)."
            )
        return yamlCamera.makeCamera(os.path.join(instrument_dir, self.profile.camera))

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
                        "name_in_raft": "S00",  # no raft, but need something stable
                        "raft": "R00",  # no raft, but need something stable
                        "purpose": det.getType().name,
                    },
                    update=update,
                )

            self._registerFilters(registry, update=update)

    def getRawFormatter(self, dataId):
        return self.rawFormatterClass

    def getDefineVisitsTask(self):
        """One exposure = one visit."""
        return DefineVisitsTask
