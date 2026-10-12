"""Generic STIPS instrument class driven by a bound :class:`InstrumentProfile`.

A binding subclass sets ``profile`` (and optionally ``translatorClass`` /
``rawFormatterClass``); everything instrument-specific is resolved from the
profile. The body of :meth:`register` derives from the legacy single-CCD
``Nickel`` instrument (one synthetic raft ``R00``; slots numbered by detector
order, so a single-CCD camera keeps its legacy ``S00`` label).
"""

from __future__ import annotations

import os
from functools import lru_cache

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


# Camera construction is expensive (YAML parsing + cameraGeom assembly) and the
# result is used read-only, so cache it. The cache key carries everything that
# affects the geometry (the camera file and the profile's ccd_binning).
@lru_cache(maxsize=None)
def _cached_spec_camera(instrument_class):
    """Build (once per binding class) the camera for a CameraSpec profile."""
    from .camera_builder import build_camera

    profile = instrument_class.profile
    return build_camera(profile.camera, profile.name)


@lru_cache(maxsize=None)
def _cached_yaml_camera(camera_file: str, binning: int):
    """Build (once per (file, binning)) the camera from a yaml definition."""
    if binning > 1:
        from .camera_builder import build_yaml_camera

        return build_yaml_camera(camera_file, binning=binning)
    return yamlCamera.makeCamera(camera_file)


class StipsInstrument(Instrument):
    """Generic LSST instrument driven by a bound ``InstrumentProfile``."""

    #: Bound by a forking subclass.
    profile = None
    #: Set by a binding subclass; defaults to the generic formatter.
    translatorClass = None
    rawFormatterClass = StipsRawFormatter
    #: Directory of the bound profile (instruments/<name>/); set by binding.bind.
    #: Camera YAML paths in the profile resolve against it.
    instrumentDir = None

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

    @classmethod
    def getName(cls):
        return cls.profile.name

    def getCamera(self):
        from stips import CameraSpec

        cam = self.profile.camera
        if isinstance(cam, CameraSpec):
            return _cached_spec_camera(type(self))
        if self.instrumentDir is None:
            raise RuntimeError(
                f"{type(self).__name__} has no instrumentDir: bind it through "
                "instruments/<name>/instrument.py (lsst.obs.stips.binding.bind)."
            )
        camera_file = os.path.join(str(self.instrumentDir), cam)
        # On-chip binning: profile.ccd_binning scales the camera geometry to
        # match binned raws. 1 == unbinned reproduces yamlCamera.makeCamera.
        return _cached_yaml_camera(camera_file, int(self.profile.ccd_binning))

    def register(self, registry, update: bool = False):
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

            # Small telescopes have no physical raft structure; use one
            # synthetic raft "R00" with slots numbered by detector order.
            # Detector 0 -> "S00", preserving the legacy single-CCD labels
            # while remaining unique for multi-detector forks.
            for i, det in enumerate(camera):
                registry.syncDimensionData(
                    "detector",
                    {
                        "instrument": self.getName(),
                        "id": int(det.getId()),
                        "full_name": det.getName(),
                        "name_in_raft": f"S{i:02d}",
                        "raft": "R00",
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
