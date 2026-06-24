"""Forced photometry tasks at user-specified RA/Dec coordinates.

This module provides pipeline tasks for performing forced photometry at
arbitrary sky coordinates on both calibrated visit images and difference images.

The tasks accept RA/Dec coordinates via an external catalog and perform
PSF flux measurements at those positions, regardless of whether sources
were detected there.

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
import lsst.pipe.base as pipeBase
import lsst.pipe.base.connectionTypes as connTypes
import numpy as np
from lsst.pipe.base import PipelineTask, PipelineTaskConfig, PipelineTaskConnections

_LOG = logging.getLogger(__name__)


class ForcedPhotRaDecConnections(
    PipelineTaskConnections,
    dimensions=("instrument", "visit", "detector"),
):
    """Connections for ForcedPhotRaDecTask."""

    exposure = connTypes.Input(
        doc="Calibrated exposure to measure",
        name="preliminary_visit_image",
        storageClass="ExposureF",
        dimensions=("instrument", "visit", "detector"),
    )

    inputCoordCatalog = connTypes.Input(
        doc="Input catalog with RA/Dec coordinates (FITS or Parquet with 'ra', 'dec' columns in degrees)",
        name="forced_phot_input_coords",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
        minimum=0,  # Optional - can use config coordinates instead
    )

    outputCatalog = connTypes.Output(
        doc="Forced photometry measurements at input coordinates",
        name="forced_phot_radec",
        storageClass="ArrowAstropy",
        dimensions=("instrument", "visit", "detector"),
    )

    def __init__(self, *, config=None):
        super().__init__(config=config)
        # If using config coordinates only, remove the input catalog connection
        if config is not None and config.useConfigCoords:
            self.inputs.remove("inputCoordCatalog")


class ForcedPhotRaDecConfig(
    PipelineTaskConfig,
    pipelineConnections=ForcedPhotRaDecConnections,
):
    """Configuration for ForcedPhotRaDecTask."""

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
        # Configure measurement plugins for forced photometry
        # Note: Use only plugins available in ForcedMeasurementTask
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
            if len(self.sourceIds) > 0 and len(self.sourceIds) != len(self.ra):
                raise pexConfig.FieldValidationError(
                    self.__class__.sourceIds,
                    self,
                    "sourceIds must have the same length as ra/dec if provided",
                )


class ForcedPhotRaDecTask(PipelineTask):
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

    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        """Run the task on a single quantum."""
        inputs = butlerQC.get(inputRefs)

        # Get coordinates either from config or input catalog
        if self.config.useConfigCoords:
            coords = self._getCoordsFromConfig()
        else:
            if "inputCoordCatalog" not in inputs:
                raise RuntimeError(
                    "No input coordinate catalog provided and useConfigCoords=False"
                )
            coords = self._getCoordsFromCatalog(inputs["inputCoordCatalog"])

        outputs = self.run(
            exposure=inputs["exposure"],
            coords=coords,
        )

        butlerQC.put(outputs, outputRefs)

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
        bbox = exposure.getBBox()

        # Create the reference catalog for forced measurement
        refCat = afwTable.SourceCatalog(self.refSchema)

        # Track which input coords are within the image
        validCoords = []

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
            # Return empty table with proper columns
            return pipeBase.Struct(outputCatalog=self._createEmptyOutputTable())

        # Create the measurement catalog from the reference catalog
        measCat = self.measurement.generateMeasCat(exposure, refCat, wcs)

        # Copy reference sources to measurement catalog with footprints
        for measRecord, refRecord, validCoord in zip(measCat, refCat, validCoords):
            measRecord.setFootprint(refRecord.getFootprint())
            measRecord.set(self.inputIdKey, validCoord["id"])
            measRecord.set(self.raKey, np.radians(validCoord["ra"]))
            measRecord.set(self.decKey, np.radians(validCoord["dec"]))

        # Run forced measurement
        self.measurement.run(measCat, exposure, refCat, wcs)

        # Convert to Astropy table for output
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
            try:
                psfFlux = record.get("base_PsfFlux_instFlux")
                psfFluxErr = record.get("base_PsfFlux_instFluxErr")
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
            except Exception:
                row["psfFlux"] = np.nan
                row["psfFluxErr"] = np.nan
                row["psfMag"] = np.nan
                row["psfMagErr"] = np.nan

            # Get aperture flux
            try:
                row["apFlux_12_0"] = record.get(
                    "base_CircularApertureFlux_12_0_instFlux"
                )
                row["apFluxErr_12_0"] = record.get(
                    "base_CircularApertureFlux_12_0_instFluxErr"
                )
            except Exception:
                row["apFlux_12_0"] = np.nan
                row["apFluxErr_12_0"] = np.nan

            # Get local background
            try:
                row["localBackground"] = record.get("base_LocalBackground_instFlux")
                row["localBackgroundErr"] = record.get(
                    "base_LocalBackground_instFluxErr"
                )
            except Exception:
                row["localBackground"] = np.nan
                row["localBackgroundErr"] = np.nan

            # Collect flags
            flags = []
            try:
                if record.get("base_PsfFlux_flag"):
                    flags.append("psfFlux_flag")
                if record.get("base_PixelFlags_flag_edge"):
                    flags.append("edge")
                if record.get("base_PixelFlags_flag_saturated"):
                    flags.append("saturated")
                if record.get("base_PixelFlags_flag_bad"):
                    flags.append("bad")
            except Exception:
                pass
            row["flags"] = ",".join(flags)

            rows.append(row)

        return astropy.table.Table(rows=rows)


# ============================================================================
# Difference Image Forced Photometry Task
# ============================================================================


class ForcedPhotDiffimRaDecConnections(
    PipelineTaskConnections,
    dimensions=("instrument", "visit", "detector"),
):
    """Connections for ForcedPhotDiffimRaDecTask."""

    differenceExposure = connTypes.Input(
        doc="Difference image to measure",
        name="difference_image",
        storageClass="ExposureF",
        dimensions=("instrument", "visit", "detector"),
    )

    scienceExposure = connTypes.Input(
        doc="Science exposure (for WCS and photo calibration)",
        name="preliminary_visit_image",
        storageClass="ExposureF",
        dimensions=("instrument", "visit", "detector"),
    )

    inputCoordCatalog = connTypes.Input(
        doc="Input catalog with RA/Dec coordinates (FITS or Parquet with 'ra', 'dec' columns in degrees)",
        name="forced_phot_input_coords",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
        minimum=0,
    )

    outputCatalog = connTypes.Output(
        doc="Forced photometry measurements on difference image",
        name="forced_phot_diffim_radec",
        storageClass="ArrowAstropy",
        dimensions=("instrument", "visit", "detector"),
    )

    def __init__(self, *, config=None):
        super().__init__(config=config)
        if config is not None and config.useConfigCoords:
            self.inputs.remove("inputCoordCatalog")


class ForcedPhotDiffimRaDecConfig(
    PipelineTaskConfig,
    pipelineConnections=ForcedPhotDiffimRaDecConnections,
):
    """Configuration for ForcedPhotDiffimRaDecTask."""

    useConfigCoords = pexConfig.Field(
        dtype=bool,
        default=False,
        doc="If True, use coordinates from config instead of input catalog",
    )

    ra = pexConfig.ListField(
        dtype=float,
        default=[],
        doc="List of RA coordinates in degrees",
    )

    dec = pexConfig.ListField(
        dtype=float,
        default=[],
        doc="List of Dec coordinates in degrees",
    )

    sourceIds = pexConfig.ListField(
        dtype=int,
        default=[],
        doc="Optional list of source IDs for config coordinates",
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
        doc="Name of ID column in input catalog",
    )

    footprintRadius = pexConfig.Field(
        dtype=float,
        default=10.0,
        doc="Radius of circular footprint in pixels",
    )

    measurement = pexConfig.ConfigurableField(
        target=measBase.ForcedMeasurementTask,
        doc="Subtask to perform forced measurement",
    )

    def setDefaults(self):
        super().setDefaults()
        # Note: Use only plugins available in ForcedMeasurementTask
        self.measurement.plugins.names = [
            "base_TransformedCentroidFromCoord",
            "base_PsfFlux",
            "base_LocalBackground",
            "base_PixelFlags",
        ]
        self.measurement.slots.centroid = "base_TransformedCentroidFromCoord"
        self.measurement.slots.shape = None
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


class ForcedPhotDiffimRaDecTask(PipelineTask):
    """Perform forced photometry on difference images at specified RA/Dec.

    This task measures flux at user-specified sky coordinates on a difference
    image. This is useful for extracting light curves of transients at known
    positions, especially when the source may be below detection threshold
    in individual epochs.

    The difference image flux represents the change in brightness relative
    to the template. Positive flux indicates the source is brighter in the
    science image, negative flux indicates it was brighter in the template.

    WARNING: Do not convert negative difference fluxes directly to magnitudes!
    Use the flux values directly for light curve analysis.
    """

    ConfigClass = ForcedPhotDiffimRaDecConfig
    _DefaultName = "forcedPhotDiffimRaDec"

    def __init__(self, schema=None, **kwargs):
        super().__init__(**kwargs)

        # Reference schema for forced measurement inputs
        self.refSchema = afwTable.SourceTable.makeMinimalSchema()
        self.refSchema.addField("centroid_x", type="D", doc="x pixel coordinate")
        self.refSchema.addField("centroid_y", type="D", doc="y pixel coordinate")

        self.measurement = measBase.ForcedMeasurementTask(
            refSchema=self.refSchema,
            config=self.config.measurement,
        )

        if schema is None:
            self.schema = self.measurement.schema
        else:
            if not schema.contains(self.measurement.schema):
                raise RuntimeError(
                    "Provided schema does not include measurement schema"
                )
            self.schema = schema

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

    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        """Run the task on a single quantum."""
        inputs = butlerQC.get(inputRefs)

        if self.config.useConfigCoords:
            coords = self._getCoordsFromConfig()
        else:
            if "inputCoordCatalog" not in inputs:
                raise RuntimeError(
                    "No input coordinate catalog provided and useConfigCoords=False"
                )
            coords = self._getCoordsFromCatalog(inputs["inputCoordCatalog"])

        outputs = self.run(
            differenceExposure=inputs["differenceExposure"],
            scienceExposure=inputs["scienceExposure"],
            coords=coords,
        )

        butlerQC.put(outputs, outputRefs)

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
            Science exposure (for WCS and photometric calibration).
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

        # Use photo calibration from science exposure for magnitude conversion
        photoCalib = scienceExposure.getPhotoCalib()
        bbox = differenceExposure.getBBox()

        # Create reference catalog
        refCat = afwTable.SourceCatalog(self.refSchema)

        validCoords = []

        for coord in coords:
            ra_deg = coord["ra"]
            dec_deg = coord["dec"]
            source_id = coord["id"]

            skyCoord = geom.SpherePoint(ra_deg * geom.degrees, dec_deg * geom.degrees)
            try:
                pixelCoord = wcs.skyToPixel(skyCoord)
            except Exception as e:
                _LOG.debug(f"Could not convert ({ra_deg}, {dec_deg}) to pixels: {e}")
                continue

            if not bbox.contains(geom.Point2I(pixelCoord)):
                _LOG.debug(
                    f"Coordinate ({ra_deg}, {dec_deg}) outside difference image bounds"
                )
                continue

            refRecord = refCat.addNew()
            refRecord.setId(source_id)
            refRecord.set("centroid_x", pixelCoord.x)
            refRecord.set("centroid_y", pixelCoord.y)
            refRecord.setCoord(skyCoord)

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
            f"Performing forced diffim photometry on {len(validCoords)} of "
            f"{len(coords)} coordinates"
        )

        if len(refCat) == 0:
            _LOG.warning("No valid coordinates within difference image bounds")
            return pipeBase.Struct(outputCatalog=self._createEmptyOutputTable())

        # Create measurement catalog from the reference catalog
        measCat = self.measurement.generateMeasCat(differenceExposure, refCat, wcs)

        for measRecord, refRecord, validCoord in zip(measCat, refCat, validCoords):
            measRecord.setFootprint(refRecord.getFootprint())
            measRecord.set(self.inputIdKey, validCoord["id"])
            measRecord.set(self.raKey, np.radians(validCoord["ra"]))
            measRecord.set(self.decKey, np.radians(validCoord["dec"]))

        # Run measurement on difference image
        self.measurement.run(measCat, differenceExposure, refCat, wcs)

        # Convert to output table
        outputTable = self._sourceCatalogToAstropy(measCat, photoCalib, validCoords)

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
        photoCalib: Any,
        validCoords: list[dict],
    ) -> astropy.table.Table:
        """Convert measurement catalog to Astropy table.

        Note: For difference images, we report flux values directly.
        Magnitude conversion is not appropriate for difference fluxes
        which can be negative.
        """
        rows = []

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
            try:
                row["diffFlux"] = record.get("base_PsfFlux_instFlux")
                row["diffFluxErr"] = record.get("base_PsfFlux_instFluxErr")
            except Exception:
                row["diffFlux"] = np.nan
                row["diffFluxErr"] = np.nan

            # Get aperture flux
            try:
                row["apDiffFlux_12_0"] = record.get(
                    "base_CircularApertureFlux_12_0_instFlux"
                )
                row["apDiffFluxErr_12_0"] = record.get(
                    "base_CircularApertureFlux_12_0_instFluxErr"
                )
            except Exception:
                row["apDiffFlux_12_0"] = np.nan
                row["apDiffFluxErr_12_0"] = np.nan

            # Get local background
            try:
                row["localBackground"] = record.get("base_LocalBackground_instFlux")
                row["localBackgroundErr"] = record.get(
                    "base_LocalBackground_instFluxErr"
                )
            except Exception:
                row["localBackground"] = np.nan
                row["localBackgroundErr"] = np.nan

            # Collect flags
            flags = []
            try:
                if record.get("base_PsfFlux_flag"):
                    flags.append("psfFlux_flag")
                if record.get("base_PixelFlags_flag_edge"):
                    flags.append("edge")
                if record.get("base_PixelFlags_flag_saturated"):
                    flags.append("saturated")
                if record.get("base_PixelFlags_flag_bad"):
                    flags.append("bad")
            except Exception:
                pass
            row["flags"] = ",".join(flags)

            rows.append(row)

        return astropy.table.Table(rows=rows)
