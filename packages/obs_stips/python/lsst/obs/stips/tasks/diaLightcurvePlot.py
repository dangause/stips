"""Pipeline task for generating DIA lightcurve tables and plots.

WARNING: Photometric Calibration Issue
---------------------------------------
The zeroPoint config (default :data:`DEFAULT_DIA_ZEROPOINT`) assumes flux is in
nanojansky, but DIA source catalogs contain instrumental flux (ADU). This
results in magnitudes ~10-11 mag fainter than correct values. When the default
uncalibrated zeropoint is used, the task emits a runtime ``log.warning``.

For scientifically accurate magnitudes, use the extract_lightcurve.py tool
instead, which fetches photoCalib from the science exposure and applies
proper ADU → nJy → AB magnitude calibration.
"""

from __future__ import annotations

import logging

import astropy.coordinates as coord
import astropy.units as u
import lsst.pipe.base as pipeBase
import numpy as np
from astropy.table import Table
from lsst.pex.config import Field, ListField
from lsst.pipe.base import connectionTypes as ct

from ._refload import load_ref

_LOG = logging.getLogger(__name__)

#: Uncalibrated placeholder zeropoint shared by the DIA lightcurve plot tasks.
#: DIA source catalogs carry instrumental flux (ADU), not nanojansky, so
#: magnitudes computed with this default are ~10-11 mag offset from calibrated
#: values (see the module docstring). Its use triggers a runtime warning; supply
#: a real per-image zeropoint (or use extract_lightcurve.py) for science-grade
#: magnitudes.
DEFAULT_DIA_ZEROPOINT = 31.4


class DiaLightcurvePlotConnections(
    pipeBase.PipelineTaskConnections,
    dimensions=("instrument", "band"),
    defaultTemplates={
        "inputName": "dia_source_unfiltered",
        "outputName": "dia_lightcurve",
        "visitTableName": "preliminary_visit_table",
    },
):
    diaSources = ct.Input(
        doc="DIA source catalogs to search for the target coordinates.",
        name="{inputName}",
        storageClass="SourceCatalog",
        dimensions=("instrument", "visit", "detector", "band"),
        multiple=True,
        deferLoad=True,
    )
    visitTable = ct.Input(
        doc="Visit table containing per-visit metadata (including MJD).",
        name="{visitTableName}",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
    )
    lightcurveTable = ct.Output(
        doc="Lightcurve table for the target coordinates.",
        name="{outputName}_table",
        storageClass="ArrowAstropy",
        dimensions=("instrument", "band"),
    )
    lightcurvePlot = ct.Output(
        doc="Lightcurve plot for the target coordinates.",
        name="{outputName}_plot",
        storageClass="Plot",
        dimensions=("instrument", "band"),
    )


class DiaLightcurvePlotConfig(
    pipeBase.PipelineTaskConfig, pipelineConnections=DiaLightcurvePlotConnections
):
    ra = Field(dtype=float, default=None, optional=True, doc="Target RA in degrees.")
    dec = Field(dtype=float, default=None, optional=True, doc="Target Dec in degrees.")
    radiusArcsec = Field(
        dtype=float,
        default=1.0,
        doc="Match radius for DIA sources in arcseconds.",
    )
    minSnr = Field(
        dtype=float,
        default=3.0,
        doc="Minimum S/N for DIA sources to include in the lightcurve.",
    )
    zeroPoint = Field(
        dtype=float,
        default=DEFAULT_DIA_ZEROPOINT,
        doc="Zero point for converting flux to magnitude. The default is an "
        "uncalibrated placeholder (see module docstring); its use logs a warning.",
    )
    useMagnitude = Field(
        dtype=bool,
        default=True,
        doc="Convert fluxes to magnitudes for plotting.",
    )
    coordRaField = Field(
        dtype=str,
        default="coord_ra",
        doc="Column name for right ascension.",
    )
    coordDecField = Field(
        dtype=str,
        default="coord_dec",
        doc="Column name for declination.",
    )
    coordInRadians = Field(
        dtype=bool,
        default=True,
        doc="Interpret coord fields as radians when auto-detect is disabled.",
    )
    autoDetectCoordUnits = Field(
        dtype=bool,
        default=True,
        doc="Auto-detect degrees vs radians for coordinate columns.",
    )
    fluxFields = ListField(
        dtype=str,
        default=[
            "base_PsfFlux_instFlux",
            "psfFlux",
            "base_CircularApertureFlux_12_0_instFlux",
        ],
        doc="Flux column candidates to use in priority order.",
    )
    fluxErrFields = ListField(
        dtype=str,
        default=[
            "base_PsfFlux_instFluxErr",
            "psfFluxErr",
            "base_CircularApertureFlux_12_0_instFluxErr",
        ],
        doc="Flux error column candidates to use in priority order.",
    )
    plotTitle = Field(
        dtype=str,
        default="",
        doc="Optional plot title override.",
    )
    targetName = Field(
        dtype=str,
        default="",
        doc="Optional target name for labeling plots.",
    )

    def validate(self):
        super().validate()
        if len(self.fluxFields) != len(self.fluxErrFields):
            raise ValueError("fluxFields and fluxErrFields must have the same length.")
        # Fail fast at config time rather than deep inside runQuantum.
        if self.ra is None or self.dec is None:
            raise ValueError("DiaLightcurvePlotTask requires config.ra and config.dec.")


class DiaLightcurvePlotTask(pipeBase.PipelineTask):
    ConfigClass = DiaLightcurvePlotConfig
    _DefaultName = "diaLightcurvePlot"

    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        if self.config.useMagnitude and self.config.zeroPoint == DEFAULT_DIA_ZEROPOINT:
            _LOG.warning(
                "DiaLightcurvePlotTask: using the default uncalibrated "
                "zeroPoint=%s. DIA fluxes are instrumental (ADU), so the "
                "resulting magnitudes are ~10-11 mag offset from calibrated "
                "values. Set config.zeroPoint or use extract_lightcurve.py "
                "for science-grade magnitudes.",
                DEFAULT_DIA_ZEROPOINT,
            )
        visit_table = butlerQC.get(inputRefs.visitTable)
        rows, band = self._collect_detections(
            visit_table, inputRefs.diaSources, butlerQC
        )

        if not rows:
            raise pipeBase.NoWorkFound(
                "No DIA sources matched the lightcurve criteria."
            )

        table = Table(rows=rows)
        if "mjd" in table.colnames:
            table.sort("mjd")

        fig = self._make_plot(table, band)
        butlerQC.put(
            pipeBase.Struct(lightcurveTable=table, lightcurvePlot=fig),
            outputRefs,
        )

    def _collect_detections(self, visit_table, dia_source_refs, butlerQC):
        # config.ra/dec presence is enforced in DiaLightcurvePlotConfig.validate.
        target = coord.SkyCoord(ra=self.config.ra * u.deg, dec=self.config.dec * u.deg)
        search_radius = self.config.radiusArcsec * u.arcsec

        visit_mjd = {row["visit"]: row["expMidptMJD"] for row in visit_table}

        rows = []
        band_value = "unknown"
        for ref in dia_source_refs:
            band_value = ref.dataId.get("band", band_value)
            visit_id = ref.dataId.get("visit")
            mjd = visit_mjd.get(visit_id, np.nan)

            catalog = load_ref(butlerQC, ref)
            if len(catalog) == 0:
                continue

            coords = self._build_coords(catalog)
            if coords is None:
                continue

            sep = target.separation(coords)
            matches = sep < search_radius
            if not np.any(matches):
                continue

            for idx in np.where(matches)[0]:
                record = catalog[idx]
                flux, flux_err = self._extract_flux(record)
                if flux is None or flux_err is None:
                    continue

                snr = flux / flux_err if flux_err > 0 else 0.0
                if snr < self.config.minSnr:
                    continue

                mag, mag_err = self._flux_to_mag(flux, flux_err)
                src_ra = coords[idx].ra.deg
                src_dec = coords[idx].dec.deg

                rows.append(
                    {
                        "mjd": mjd,
                        "band": band_value,
                        "visit": visit_id,
                        "ra": src_ra,
                        "dec": src_dec,
                        "flux": flux,
                        "flux_err": flux_err,
                        "mag": mag,
                        "mag_err": mag_err,
                        "snr": snr,
                        "separation_arcsec": sep[idx].arcsec,
                    }
                )

        return rows, band_value

    def _build_coords(self, catalog):
        for ra_field, dec_field in (
            (self.config.coordRaField, self.config.coordDecField),
            ("ra", "dec"),
        ):
            try:
                ra_vals = np.asarray(catalog[ra_field], dtype=float)
                dec_vals = np.asarray(catalog[dec_field], dtype=float)
            except KeyError:
                continue

            if self.config.autoDetectCoordUnits:
                use_degrees = np.nanmax(np.abs(dec_vals)) > 1.6
                unit = u.deg if use_degrees else u.rad
            else:
                unit = u.rad if self.config.coordInRadians else u.deg

            return coord.SkyCoord(ra=ra_vals * unit, dec=dec_vals * unit)

        return None

    def _extract_flux(self, record):
        for flux_field, err_field in zip(
            self.config.fluxFields, self.config.fluxErrFields
        ):
            try:
                return record[flux_field], record[err_field]
            except KeyError:
                continue
        return None, None

    def _flux_to_mag(self, flux, flux_err):
        if not self.config.useMagnitude:
            return np.nan, np.nan
        if flux > 0:
            mag = -2.5 * np.log10(flux) + self.config.zeroPoint
            mag_err = 2.5 / np.log(10) * flux_err / flux
            return mag, mag_err
        return np.nan, np.nan

    def _make_plot(self, table, band):
        # Deferred: matplotlib is only needed when a plot is actually produced
        # (keeps module import cheap and stackless-import friendly).
        import matplotlib.pyplot as plt
        from lsst.obs.stips.plotting import (
            FIGURE_SIZE,
            format_lightcurve_axes,
            plot_lightcurve_band,
            publication_style,
            set_title,
        )

        with publication_style():
            fig, ax = plt.subplots(figsize=FIGURE_SIZE)
            x = table["mjd"] if "mjd" in table.colnames else np.arange(len(table))

            if self.config.useMagnitude:
                plot_lightcurve_band(
                    ax,
                    x,
                    table["mag"],
                    table["mag_err"],
                    band,
                    count=len(table),
                )
                format_lightcurve_axes(
                    ax,
                    ylabel="Apparent Magnitude (mag)",
                    invert_y=True,
                )
            else:
                plot_lightcurve_band(
                    ax,
                    x,
                    table["flux"],
                    table["flux_err"],
                    band,
                    count=len(table),
                )
                format_lightcurve_axes(
                    ax,
                    ylabel="Flux (counts)",
                    invert_y=False,
                )

            target_label = (
                self.config.targetName
                or f"RA={self.config.ra:.6f}, Dec={self.config.dec:.6f}"
            )
            if self.config.plotTitle:
                ax.set_title(self.config.plotTitle)
            else:
                set_title(ax, target_label, subtitle="DIA Photometry", band=band)

            ax.legend(loc="best")
            fig.tight_layout()
        return fig
