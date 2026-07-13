"""Forced photometry tasks at user-specified RA/Dec coordinates.

This module provides pipeline tasks for performing forced photometry at
arbitrary sky coordinates on both calibrated visit images and difference images.

The tasks accept RA/Dec coordinates via an external catalog and perform
PSF flux measurements at those positions, regardless of whether sources
were detected there.

Both tasks share a common base (:class:`_ForcedPhotRaDecBaseConfig` /
:class:`_ForcedPhotRaDecBaseTask`) that owns coordinate loading, reference
catalog / footprint construction, and forced measurement. Each concrete task
subclasses only the image-specific bits (which exposure supplies the WCS, and
how the measurement catalog is converted to an output table).

Example usage in a pipeline:
    tasks:
      forcedPhotRaDec:
        class: lsst.obs.stips.tasks.ForcedPhotRaDecTask
        config:
          connections.exposure: preliminary_visit_image
          connections.inputCoordCatalog: my_target_catalog
"""

from __future__ import annotations

__all__ = [
    "ForcedPhotRaDecConfig",
    "ForcedPhotRaDecTask",
    "ForcedPhotDiffimRaDecConfig",
    "ForcedPhotDiffimRaDecTask",
]

import logging
from typing import Any

import astropy.table
import lsst.afw.detection as afwDet
import lsst.afw.geom as afwGeom
import lsst.afw.image as afwImage
import lsst.afw.table as afwTable
import lsst.geom as geom
import lsst.meas.base as measBase
import lsst.pex.config as pexConfig
import lsst.pex.exceptions as pexExceptions
import lsst.pipe.base as pipeBase
import lsst.pipe.base.connectionTypes as connTypes
import numpy as np
from lsst.pipe.base import PipelineTask, PipelineTaskConfig, PipelineTaskConnections

_LOG = logging.getLogger(__name__)


# ============================================================================
# Shared configuration
# ============================================================================


class _ForcedPhotRaDecBaseConnections(
    PipelineTaskConnections,
    dimensions=("instrument", "visit", "detector"),
):
    """Shared connection + config-conditional input handling.

    Both concrete connection classes subclass this to inherit the optional
    ``inputCoordCatalog`` input and the ``useConfigCoords`` removal logic; they
    add their own exposure inputs and output.
    """

    inputCoordCatalog = connTypes.Input(
        doc="Input catalog with RA/Dec coordinates (FITS or Parquet with 'ra', 'dec' columns in degrees)",
        name="forced_phot_input_coords",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
        minimum=0,  # Optional - can use config coordinates instead
    )

    def __init__(self, *, config=None):
        super().__init__(config=config)
        # If using config coordinates only, remove the input catalog connection
        if config is not None and config.useConfigCoords:
            self.inputs.remove("inputCoordCatalog")


class _ForcedPhotRaDecBaseConfig(
    PipelineTaskConfig,
    pipelineConnections=_ForcedPhotRaDecBaseConnections,
):
    """Shared configuration fields for RA/Dec forced photometry tasks.

    Concrete configs re-specify ``pipelineConnections`` for their own I/O; the
    coordinate-selection fields and validation live here so the two tasks
    cannot silently diverge (they did, historically — see audit finding F-029).
    """

    useConfigCoords = pexConfig.Field(
        dtype=bool,
        default=False,
        doc="If True, use coordinates from config (ra/dec fields) instead of input catalog",
    )

    ra = pexConfig.ListField(
        dtype=float,
        default=[],
        doc="List of RA coordinates in degrees (used if useConfigCoords=True)",
    )

    dec = pexConfig.ListField(
        dtype=float,
        default=[],
        doc="List of Dec coordinates in degrees (used if useConfigCoords=True)",
    )

    sourceIds = pexConfig.ListField(
        dtype=int,
        default=[],
        doc="Optional list of source IDs for config coordinates (if empty, auto-generated)",
    )

    raColumn = pexConfig.Field(
        dtype=str,
        default="ra",
        doc="Name of RA column in input catalog (degrees)",
    )

    decColumn = pexConfig.Field(
        dtype=str,
        default="dec",
        doc="Name of Dec column in input catalog (degrees)",
    )

    idColumn = pexConfig.Field(
        dtype=str,
        default="id",
        doc="Name of ID column in input catalog (optional)",
    )

    footprintRadius = pexConfig.Field(
        dtype=float,
        default=10.0,
        doc="Radius of circular footprint in pixels for forced measurement",
    )

    measurement = pexConfig.ConfigurableField(
        target=measBase.ForcedMeasurementTask,
        doc="Subtask to perform forced measurement",
    )

    def setDefaults(self):
        super().setDefaults()
        # Configure measurement plugins for forced photometry.
        # Note: Use only plugins available in ForcedMeasurementTask.
        self.measurement.plugins.names = [
            "base_TransformedCentroidFromCoord",
            "base_PsfFlux",
            "base_LocalBackground",
            "base_PixelFlags",
        ]
        self.measurement.slots.centroid = "base_TransformedCentroidFromCoord"
        self.measurement.slots.shape = None
        # Reference catalogs only include minimal fields, so avoid copying
        # optional deblend columns that are not present.
        self.measurement.copyColumns = {
            "id": "objectId",
            "coord_ra": "coord_ra",
            "coord_dec": "coord_dec",
        }

    def validate(self):
        super().validate()
        if self.useConfigCoords:
            if len(self.ra) == 0 or len(self.dec) == 0:
                raise pexConfig.FieldValidationError(
                    self.__class__.ra,
                    self,
                    "ra and dec lists must be non-empty when useConfigCoords=True",
                )
            if len(self.ra) != len(self.dec):
                raise pexConfig.FieldValidationError(
                    self.__class__.ra,
                    self,
                    "ra and dec lists must have the same length",
                )
            # Guards _getCoordsFromConfig against an IndexError when a short
            # sourceIds list is paired with useConfigCoords=True.
            if len(self.sourceIds) > 0 and len(self.sourceIds) != len(self.ra):
                raise pexConfig.FieldValidationError(
                    self.__class__.sourceIds,
                    self,
                    "sourceIds must have the same length as ra/dec if provided",
                )


# ============================================================================
# Shared task base
# ============================================================================


class _ForcedPhotRaDecBaseTask(PipelineTask):
    """Shared implementation for forced photometry at RA/Dec coordinates.

    Owns the reference-schema setup, coordinate loading, and the reference
    catalog / footprint / measurement machinery. Subclasses supply the concrete
    ``run``/``runQuantum`` wiring (which exposure provides the WCS and which is
    measured) and the ``_sourceCatalogToAstropy`` / ``_createEmptyOutputTable``
    conversion appropriate to their output.
    """

    def __init__(self, schema=None, **kwargs):
        super().__init__(**kwargs)

        # Reference schema for forced measurement inputs
        self.refSchema = afwTable.SourceTable.makeMinimalSchema()
        self.refSchema.addField("centroid_x", type="D", doc="x pixel coordinate")
        self.refSchema.addField("centroid_y", type="D", doc="y pixel coordinate")

        # Set up the measurement task
        self.measurement = measBase.ForcedMeasurementTask(
            refSchema=self.refSchema,
            config=self.config.measurement,
        )

        # Use provided schema if it contains the measurement schema
        if schema is None:
            self.schema = self.measurement.schema
        else:
            if not schema.contains(self.measurement.schema):
                raise RuntimeError(
                    "Provided schema does not include measurement schema"
                )
            self.schema = schema

        # Add fields for the input coordinates
        self.raKey = self.schema.addField(
            "coord_ra_input",
            type="D",
            doc="Input RA coordinate (radians)",
            units="rad",
        )
        self.decKey = self.schema.addField(
            "coord_dec_input",
            type="D",
            doc="Input Dec coordinate (radians)",
            units="rad",
        )
        self.inputIdKey = self.schema.addField(
            "input_id",
            type="L",
            doc="ID from input catalog",
        )

    # -- coordinate loading --------------------------------------------------

    def _loadCoords(self, inputs: dict) -> list[dict[str, Any]]:
        """Resolve coordinates from config or the optional input catalog."""
        if self.config.useConfigCoords:
            return self._getCoordsFromConfig()
        if "inputCoordCatalog" not in inputs:
            raise RuntimeError(
                "No input coordinate catalog provided and useConfigCoords=False"
            )
        return self._getCoordsFromCatalog(inputs["inputCoordCatalog"])

    def _getCoordsFromConfig(self) -> list[dict[str, Any]]:
        """Extract coordinates from config parameters."""
        coords = []
        for i, (ra, dec) in enumerate(zip(self.config.ra, self.config.dec)):
            source_id = self.config.sourceIds[i] if self.config.sourceIds else i + 1
            coords.append({"id": source_id, "ra": ra, "dec": dec})
        return coords

    def _getCoordsFromCatalog(
        self, catalog: astropy.table.Table
    ) -> list[dict[str, Any]]:
        """Extract coordinates from input catalog."""
        ra_col = self.config.raColumn
        dec_col = self.config.decColumn
        id_col = self.config.idColumn

        coords = []
        for i, row in enumerate(catalog):
            source_id = row[id_col] if id_col in catalog.colnames else i + 1
            coords.append(
                {
                    "id": int(source_id),
                    "ra": float(row[ra_col]),
                    "dec": float(row[dec_col]),
                }
            )
        return coords

    # -- forced measurement --------------------------------------------------

    def _runForcedMeasurement(
        self,
        measExposure: afwImage.ExposureF,
        wcs,
        coords: list[dict[str, Any]],
    ) -> tuple[afwTable.SourceCatalog | None, list[dict]]:
        """Build the reference catalog, run forced measurement, and return it.

        Parameters
        ----------
        measExposure : `lsst.afw.image.ExposureF`
            Image the forced measurement is performed on (its bbox bounds the
            valid coordinates). For difference imaging this is the difference
            image; the WCS is passed separately.
        wcs : `lsst.afw.geom.SkyWcs`
            World coordinate system used to project the sky coordinates.
        coords : `list` of `dict`
            Coordinate dictionaries with 'id', 'ra', 'dec' keys (deg).

        Returns
        -------
        measCat : `lsst.afw.table.SourceCatalog` or `None`
            Measurement catalog, or ``None`` when no coordinate fell within the
            image bounds.
        validCoords : `list` of `dict`
            Per-source metadata (id, ra, dec, pixel_x, pixel_y) aligned with
            ``measCat`` rows.
        """
        bbox = measExposure.getBBox()

        refCat = afwTable.SourceCatalog(self.refSchema)
        validCoords: list[dict] = []

        for coord in coords:
            ra_deg = coord["ra"]
            dec_deg = coord["dec"]
            source_id = coord["id"]

            # Convert RA/Dec to pixel coordinates
            skyCoord = geom.SpherePoint(ra_deg * geom.degrees, dec_deg * geom.degrees)
            try:
                pixelCoord = wcs.skyToPixel(skyCoord)
            except Exception as e:
                _LOG.debug(
                    f"Could not convert coords ({ra_deg}, {dec_deg}) to pixels: {e}"
                )
                continue

            # Check if within image bounds
            if not bbox.contains(geom.Point2I(pixelCoord)):
                _LOG.debug(
                    f"Coordinate ({ra_deg}, {dec_deg}) -> pixel ({pixelCoord.x}, {pixelCoord.y}) "
                    f"outside image bounds {bbox}"
                )
                continue

            # Create a reference source at this position
            refRecord = refCat.addNew()
            refRecord.setId(source_id)
            refRecord.set("centroid_x", pixelCoord.x)
            refRecord.set("centroid_y", pixelCoord.y)
            refRecord.setCoord(skyCoord)

            # Create a circular footprint at this position
            footprint = afwDet.Footprint(
                afwGeom.SpanSet.fromShape(
                    int(self.config.footprintRadius),
                    afwGeom.Stencil.CIRCLE,
                    geom.Point2I(pixelCoord),
                ),
                bbox,
            )
            refRecord.setFootprint(footprint)

            validCoords.append(
                {
                    "id": source_id,
                    "ra": ra_deg,
                    "dec": dec_deg,
                    "pixel_x": pixelCoord.x,
                    "pixel_y": pixelCoord.y,
                }
            )

        _LOG.info(
            f"Performing forced photometry on {len(validCoords)} of {len(coords)} "
            f"input coordinates (within image bounds)"
        )

        if len(refCat) == 0:
            _LOG.warning("No valid coordinates within image bounds")
            return None, []

        # Create the measurement catalog from the reference catalog
        measCat = self.measurement.generateMeasCat(measExposure, refCat, wcs)

        # Copy reference sources to measurement catalog with footprints
        for measRecord, refRecord, validCoord in zip(measCat, refCat, validCoords):
            measRecord.setFootprint(refRecord.getFootprint())
            measRecord.set(self.inputIdKey, validCoord["id"])
            measRecord.set(self.raKey, np.radians(validCoord["ra"]))
            measRecord.set(self.decKey, np.radians(validCoord["dec"]))

        # Run forced measurement
        self.measurement.run(measCat, measExposure, refCat, wcs)

        return measCat, validCoords

    @staticmethod
    def _recordGet(record, column: str, missing: set, default=np.nan):
        """Read ``column`` from ``record``, warning once per call on absence.

        A missing column (renamed plugin output, disabled plugin) historically
        produced silent NaN with zero log output — the hardest failure mode to
        debug downstream (an all-NaN lightcurve). Only genuinely-missing-column
        errors are caught; anything else propagates.
        """
        try:
            return record.get(column)
        except (KeyError, pexExceptions.NotFoundError):
            if column not in missing:
                _LOG.warning(
                    "Column %r not found in forced measurement catalog; "
                    "filling %s. Check the measurement plugin configuration.",
                    column,
                    default,
                )
                missing.add(column)
            return default

    @classmethod
    def _flagsToString(cls, record, missing: set) -> str:
        """Collect set pixel/PSF flags into a comma-joined string."""
        flags = []
        for column, label in (
            ("base_PsfFlux_flag", "psfFlux_flag"),
            ("base_PixelFlags_flag_edge", "edge"),
            ("base_PixelFlags_flag_saturated", "saturated"),
            ("base_PixelFlags_flag_bad", "bad"),
        ):
            if cls._recordGet(record, column, missing, default=False):
                flags.append(label)
        return ",".join(flags)


# ============================================================================
# Calibrated Visit Image Forced Photometry Task
# ============================================================================


class ForcedPhotRaDecConnections(_ForcedPhotRaDecBaseConnections):
    """Connections for ForcedPhotRaDecTask."""

    exposure = connTypes.Input(
        doc="Calibrated exposure to measure",
        name="preliminary_visit_image",
        storageClass="ExposureF",
        dimensions=("instrument", "visit", "detector"),
    )

    outputCatalog = connTypes.Output(
        doc="Forced photometry measurements at input coordinates",
        name="forced_phot_radec",
        storageClass="ArrowAstropy",
        dimensions=("instrument", "visit", "detector"),
    )


class ForcedPhotRaDecConfig(
    _ForcedPhotRaDecBaseConfig,
    pipelineConnections=ForcedPhotRaDecConnections,
):
    """Configuration for ForcedPhotRaDecTask."""


class ForcedPhotRaDecTask(_ForcedPhotRaDecBaseTask):
    """Perform forced photometry at specified RA/Dec coordinates.

    This task measures PSF flux at user-specified sky coordinates on a
    calibrated exposure, regardless of whether sources were detected there.

    The coordinates can be provided either:
    1. Via an input catalog with RA/Dec columns (recommended for many sources)
    2. Via config parameters (convenient for a few specific targets)

    The output is a catalog containing the measured fluxes and associated
    errors for each input coordinate.
    """

    ConfigClass = ForcedPhotRaDecConfig
    _DefaultName = "forcedPhotRaDec"

    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        """Run the task on a single quantum."""
        inputs = butlerQC.get(inputRefs)
        coords = self._loadCoords(inputs)
        outputs = self.run(exposure=inputs["exposure"], coords=coords)
        butlerQC.put(outputs, outputRefs)

    def run(
        self,
        exposure: afwImage.ExposureF,
        coords: list[dict[str, Any]],
    ) -> pipeBase.Struct:
        """Perform forced photometry at specified coordinates.

        Parameters
        ----------
        exposure : `lsst.afw.image.ExposureF`
            Calibrated exposure to measure.
        coords : `list` of `dict`
            List of coordinate dictionaries with 'id', 'ra', 'dec' keys.
            RA and Dec should be in degrees.

        Returns
        -------
        result : `lsst.pipe.base.Struct`
            Result struct with:
            - outputCatalog: Astropy table with forced photometry measurements
        """
        wcs = exposure.getWcs()
        if wcs is None:
            _LOG.warning("Exposure has no WCS; skipping quantum")
            raise pipeBase.NoWorkFound("Exposure has no WCS")

        photoCalib = exposure.getPhotoCalib()

        measCat, validCoords = self._runForcedMeasurement(exposure, wcs, coords)
        if measCat is None:
            return pipeBase.Struct(outputCatalog=self._createEmptyOutputTable())

        outputTable = self._sourceCatalogToAstropy(measCat, photoCalib, validCoords)
        return pipeBase.Struct(outputCatalog=outputTable)

    def _createEmptyOutputTable(self) -> astropy.table.Table:
        """Create an empty output table with the correct columns."""
        return astropy.table.Table(
            names=[
                "id",
                "input_id",
                "ra",
                "dec",
                "x",
                "y",
                "psfFlux",
                "psfFluxErr",
                "psfMag",
                "psfMagErr",
                "apFlux_12_0",
                "apFluxErr_12_0",
                "localBackground",
                "localBackgroundErr",
                "flags",
            ],
            dtype=[
                "i8",
                "i8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "U256",
            ],
        )

    def _sourceCatalogToAstropy(
        self,
        measCat: afwTable.SourceCatalog,
        photoCalib: Any,
        validCoords: list[dict],
    ) -> astropy.table.Table:
        """Convert measurement catalog to Astropy table with calibrated magnitudes."""
        rows = []
        missing: set = set()  # missing-column names, warned once per call

        for record, validCoord in zip(measCat, validCoords):
            row = {
                "id": record.getId(),
                "input_id": validCoord["id"],
                "ra": validCoord["ra"],
                "dec": validCoord["dec"],
                "x": validCoord["pixel_x"],
                "y": validCoord["pixel_y"],
            }

            # Get PSF flux
            psfFlux = self._recordGet(record, "base_PsfFlux_instFlux", missing)
            psfFluxErr = self._recordGet(record, "base_PsfFlux_instFluxErr", missing)
            row["psfFlux"] = psfFlux
            row["psfFluxErr"] = psfFluxErr

            # Calibrate to magnitude if possible
            if photoCalib is not None and psfFlux > 0:
                try:
                    mag = photoCalib.instFluxToMagnitude(psfFlux, psfFluxErr)
                    row["psfMag"] = mag.value
                    row["psfMagErr"] = mag.error
                except Exception:
                    row["psfMag"] = np.nan
                    row["psfMagErr"] = np.nan
            else:
                row["psfMag"] = np.nan
                row["psfMagErr"] = np.nan

            # Get aperture flux
            row["apFlux_12_0"] = self._recordGet(
                record, "base_CircularApertureFlux_12_0_instFlux", missing
            )
            row["apFluxErr_12_0"] = self._recordGet(
                record, "base_CircularApertureFlux_12_0_instFluxErr", missing
            )

            # Get local background
            row["localBackground"] = self._recordGet(
                record, "base_LocalBackground_instFlux", missing
            )
            row["localBackgroundErr"] = self._recordGet(
                record, "base_LocalBackground_instFluxErr", missing
            )

            row["flags"] = self._flagsToString(record, missing)

            rows.append(row)

        return astropy.table.Table(rows=rows)


# ============================================================================
# Difference Image Forced Photometry Task
# ============================================================================


class ForcedPhotDiffimRaDecConnections(_ForcedPhotRaDecBaseConnections):
    """Connections for ForcedPhotDiffimRaDecTask."""

    differenceExposure = connTypes.Input(
        doc="Difference image to measure",
        name="difference_image",
        storageClass="ExposureF",
        dimensions=("instrument", "visit", "detector"),
    )

    scienceExposure = connTypes.Input(
        doc="Science exposure (for WCS)",
        name="preliminary_visit_image",
        storageClass="ExposureF",
        dimensions=("instrument", "visit", "detector"),
    )

    outputCatalog = connTypes.Output(
        doc="Forced photometry measurements on difference image",
        name="forced_phot_diffim_radec",
        storageClass="ArrowAstropy",
        dimensions=("instrument", "visit", "detector"),
    )


class ForcedPhotDiffimRaDecConfig(
    _ForcedPhotRaDecBaseConfig,
    pipelineConnections=ForcedPhotDiffimRaDecConnections,
):
    """Configuration for ForcedPhotDiffimRaDecTask."""


class ForcedPhotDiffimRaDecTask(_ForcedPhotRaDecBaseTask):
    """Perform forced photometry on difference images at specified RA/Dec.

    This task measures flux at user-specified sky coordinates on a difference
    image. This is useful for extracting light curves of transients at known
    positions, especially when the source may be below detection threshold
    in individual epochs.

    The difference image flux represents the change in brightness relative
    to the template. Positive flux indicates the source is brighter in the
    science image, negative flux indicates it was brighter in the template.

    Fluxes are reported uncalibrated (instrumental) by design: difference
    fluxes can be negative and must not be converted to magnitudes here. Use
    the flux values directly for light curve analysis.
    """

    ConfigClass = ForcedPhotDiffimRaDecConfig
    _DefaultName = "forcedPhotDiffimRaDec"

    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        """Run the task on a single quantum."""
        inputs = butlerQC.get(inputRefs)
        coords = self._loadCoords(inputs)
        outputs = self.run(
            differenceExposure=inputs["differenceExposure"],
            scienceExposure=inputs["scienceExposure"],
            coords=coords,
        )
        butlerQC.put(outputs, outputRefs)

    def run(
        self,
        differenceExposure: afwImage.ExposureF,
        scienceExposure: afwImage.ExposureF,
        coords: list[dict[str, Any]],
    ) -> pipeBase.Struct:
        """Perform forced photometry on difference image.

        Parameters
        ----------
        differenceExposure : `lsst.afw.image.ExposureF`
            Difference image to measure.
        scienceExposure : `lsst.afw.image.ExposureF`
            Science exposure (supplies the WCS; the difference image WCS should
            match).
        coords : `list` of `dict`
            List of coordinate dictionaries with 'id', 'ra', 'dec' keys.

        Returns
        -------
        result : `lsst.pipe.base.Struct`
            Result struct with outputCatalog containing measurements.
        """
        # Use WCS from science exposure (difference image WCS should match)
        wcs = scienceExposure.getWcs()
        if wcs is None:
            _LOG.warning("Science exposure has no WCS; skipping quantum")
            raise pipeBase.NoWorkFound("Science exposure has no WCS")

        measCat, validCoords = self._runForcedMeasurement(
            differenceExposure, wcs, coords
        )
        if measCat is None:
            return pipeBase.Struct(outputCatalog=self._createEmptyOutputTable())

        outputTable = self._sourceCatalogToAstropy(measCat, validCoords)
        return pipeBase.Struct(outputCatalog=outputTable)

    def _createEmptyOutputTable(self) -> astropy.table.Table:
        """Create an empty output table."""
        return astropy.table.Table(
            names=[
                "id",
                "input_id",
                "ra",
                "dec",
                "x",
                "y",
                "diffFlux",
                "diffFluxErr",
                "apDiffFlux_12_0",
                "apDiffFluxErr_12_0",
                "localBackground",
                "localBackgroundErr",
                "flags",
            ],
            dtype=[
                "i8",
                "i8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "f8",
                "U256",
            ],
        )

    def _sourceCatalogToAstropy(
        self,
        measCat: afwTable.SourceCatalog,
        validCoords: list[dict],
    ) -> astropy.table.Table:
        """Convert measurement catalog to Astropy table.

        Difference-image fluxes are reported directly (instrumental, uncalibrated):
        magnitude conversion is deliberately not applied because difference
        fluxes can be negative.
        """
        rows = []
        missing: set = set()  # missing-column names, warned once per call

        for record, validCoord in zip(measCat, validCoords):
            row = {
                "id": record.getId(),
                "input_id": validCoord["id"],
                "ra": validCoord["ra"],
                "dec": validCoord["dec"],
                "x": validCoord["pixel_x"],
                "y": validCoord["pixel_y"],
            }

            # Get PSF flux on difference image
            row["diffFlux"] = self._recordGet(record, "base_PsfFlux_instFlux", missing)
            row["diffFluxErr"] = self._recordGet(
                record, "base_PsfFlux_instFluxErr", missing
            )

            # Get aperture flux
            row["apDiffFlux_12_0"] = self._recordGet(
                record, "base_CircularApertureFlux_12_0_instFlux", missing
            )
            row["apDiffFluxErr_12_0"] = self._recordGet(
                record, "base_CircularApertureFlux_12_0_instFluxErr", missing
            )

            # Get local background
            row["localBackground"] = self._recordGet(
                record, "base_LocalBackground_instFlux", missing
            )
            row["localBackgroundErr"] = self._recordGet(
                record, "base_LocalBackground_instFluxErr", missing
            )

            row["flags"] = self._flagsToString(record, missing)

            rows.append(row)

        return astropy.table.Table(rows=rows)
