"""Pipeline task for generating lightcurves from forced photometry outputs.

.. deprecated::
    For scientifically accurate magnitudes from difference images, use the
    production lightcurve extraction tool::

        pipeline_tools/extract_lightcurve.py

    which fetches per-visit photoCalib from the Butler and applies proper
    ADU -> nJy -> AB magnitude calibration. See also ``nickel lightcurve``.

This task consolidates per-visit forced photometry measurements into a single
lightcurve table and generates plots. It works with outputs from either
ForcedPhotRaDecTask (visit images) or ForcedPhotDiffimRaDecTask (difference images).
"""

from __future__ import annotations

import logging

import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase
import matplotlib.pyplot as plt
import numpy as np
from astropy.table import Table
from lsst.daf.butler import DeferredDatasetHandle
from lsst.pipe.base import connectionTypes as ct

__all__ = [
    "ForcedPhotLightcurveConfig",
    "ForcedPhotLightcurveTask",
    "ForcedPhotDiffimLightcurveConfig",
    "ForcedPhotDiffimLightcurveTask",
]

_LOG = logging.getLogger(__name__)

# AB magnitude zeropoint for nanojansky: m_AB = -2.5 * log10(f_nJy) + 31.4
_AB_NJY_ZEROPOINT = 31.4


class ForcedPhotLightcurveConnections(
    pipeBase.PipelineTaskConnections,
    dimensions=("instrument",),
    defaultTemplates={
        "inputName": "forced_phot_radec",
        "outputName": "forced_phot_lightcurve",
        "visitTableName": "preliminary_visit_table",
    },
):
    """Connections for ForcedPhotLightcurveTask.

    Note: This task operates at the instrument level, collecting all forced
    photometry catalogs across visits/bands and consolidating them into a
    single lightcurve. The band information is extracted from visit metadata.
    """

    forcedPhotCatalogs = ct.Input(
        doc="Forced photometry catalogs from ForcedPhotRaDecTask.",
        name="{inputName}",
        storageClass="ArrowAstropy",
        dimensions=("instrument", "visit", "detector"),
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
        doc="Consolidated lightcurve table from forced photometry.",
        name="{outputName}_table",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
    )
    lightcurvePlot = ct.Output(
        doc="Lightcurve plot from forced photometry.",
        name="{outputName}_plot",
        storageClass="Plot",
        dimensions=("instrument",),
    )


class ForcedPhotLightcurveConfig(
    pipeBase.PipelineTaskConfig,
    pipelineConnections=ForcedPhotLightcurveConnections,
):
    """Configuration for ForcedPhotLightcurveTask."""

    targetName = pexConfig.Field(
        dtype=str,
        default="",
        doc="Target name for plot title and labeling.",
    )
    minSnr = pexConfig.Field(
        dtype=float,
        default=0.0,
        doc="Minimum S/N for points to include (0 = include all, including negative).",
    )
    plotTitle = pexConfig.Field(
        dtype=str,
        default="",
        doc="Optional plot title override.",
    )
    useMagnitude = pexConfig.Field(
        dtype=bool,
        default=True,
        doc="Plot magnitudes (True) or fluxes (False). Only positive fluxes shown for mag.",
    )
    showNegativeFlux = pexConfig.Field(
        dtype=bool,
        default=True,
        doc="Show negative flux points as upper limits (arrows) when plotting magnitudes.",
    )
    fluxColumn = pexConfig.Field(
        dtype=str,
        default="psfFlux",
        doc="Flux column name in forced phot output.",
    )
    fluxErrColumn = pexConfig.Field(
        dtype=str,
        default="psfFluxErr",
        doc="Flux error column name in forced phot output.",
    )
    magColumn = pexConfig.Field(
        dtype=str,
        default="psfMag",
        doc="Magnitude column name in forced phot output (if available).",
    )
    magErrColumn = pexConfig.Field(
        dtype=str,
        default="psfMagErr",
        doc="Magnitude error column name in forced phot output (if available).",
    )


class ForcedPhotLightcurveTask(pipeBase.PipelineTask):
    """Consolidate forced photometry outputs into a lightcurve.

    This task reads per-visit forced photometry catalogs, matches them with
    visit metadata (MJD), and produces a consolidated lightcurve table and plot.
    """

    ConfigClass = ForcedPhotLightcurveConfig
    _DefaultName = "forcedPhotLightcurve"

    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        """Execute the task."""
        visit_table = butlerQC.get(inputRefs.visitTable)

        # Build visit -> band lookup from visit table
        visit_band = {}
        if "band" in visit_table.colnames:
            for row in visit_table:
                visit_band[row["visit"]] = row.get("band", "unknown")

        rows = self._collect_measurements(
            visit_table, inputRefs.forcedPhotCatalogs, butlerQC, visit_band
        )

        if not rows:
            raise pipeBase.NoWorkFound(
                "No forced photometry measurements found for lightcurve."
            )

        table = Table(rows=rows)
        if "mjd" in table.colnames:
            table.sort("mjd")

        # Determine band for plot title (use most common or "multi")
        bands = list(set(row.get("band", "unknown") for row in rows))
        band_label = bands[0] if len(bands) == 1 else "multi-band"

        fig = self._make_plot(table, band_label)
        butlerQC.put(
            pipeBase.Struct(lightcurveTable=table, lightcurvePlot=fig),
            outputRefs,
        )

    def _collect_measurements(
        self,
        visit_table: Table,
        catalog_refs: list,
        butlerQC,
        visit_band: dict,
    ) -> list[dict]:
        """Collect measurements from all forced phot catalogs.

        Parameters
        ----------
        visit_table : `astropy.table.Table`
            Visit table with MJD information.
        catalog_refs : `list`
            List of deferred dataset references for forced phot catalogs.
        butlerQC : `ButlerQuantumContext`
            Butler quantum context for loading data.
        visit_band : `dict`
            Mapping from visit ID to band name.

        Returns
        -------
        rows : `list` of `dict`
            Collected measurements as list of row dictionaries.
        """
        # Build visit -> MJD lookup
        visit_mjd = {row["visit"]: row["expMidptMJD"] for row in visit_table}

        rows = []
        for ref in catalog_refs:
            visit_id = ref.dataId.get("visit")
            mjd = visit_mjd.get(visit_id, np.nan)
            band = visit_band.get(visit_id, "unknown")

            # Load catalog (may be DeferredDatasetHandle)
            if hasattr(ref, "get"):
                catalog = ref.get()
            else:
                catalog = butlerQC.get(ref)
            if isinstance(catalog, DeferredDatasetHandle):
                catalog = catalog.get()

            if len(catalog) == 0:
                continue

            # Process each row in the forced phot catalog
            for record in catalog:
                flux = self._get_value(record, self.config.fluxColumn)
                flux_err = self._get_value(record, self.config.fluxErrColumn)
                mag = self._get_value(record, self.config.magColumn)
                mag_err = self._get_value(record, self.config.magErrColumn)

                if flux is None or flux_err is None:
                    continue

                # Calculate S/N
                snr = flux / flux_err if flux_err > 0 else 0.0

                # Apply S/N filter (but keep negative flux if minSnr=0)
                if self.config.minSnr > 0 and abs(snr) < self.config.minSnr:
                    continue

                # Get coordinates
                ra = self._get_value(record, "ra")
                dec = self._get_value(record, "dec")
                input_id = self._get_value(record, "input_id", default=0)

                rows.append(
                    {
                        "mjd": mjd,
                        "band": band,
                        "visit": visit_id,
                        "input_id": input_id,
                        "ra": ra,
                        "dec": dec,
                        "flux": flux,
                        "flux_err": flux_err,
                        "mag": mag if mag is not None else np.nan,
                        "mag_err": mag_err if mag_err is not None else np.nan,
                        "snr": snr,
                    }
                )

        return rows

    def _get_value(self, record, column: str, default=None):
        """Safely get a value from a record."""
        try:
            val = record[column]
            if hasattr(val, "item"):
                val = val.item()
            return val
        except (KeyError, IndexError):
            return default

    def _make_plot(self, table: Table, band: str):
        """Generate multi-band lightcurve plot with publication styling."""
        from lsst.obs.nickel.plotting import (
            FIGURE_SIZE,
            format_lightcurve_axes,
            plot_lightcurve_band,
            publication_style,
            set_title,
            sort_bands,
        )

        with publication_style():
            fig, ax = plt.subplots(figsize=FIGURE_SIZE)
            x = table["mjd"] if "mjd" in table.colnames else np.arange(len(table))
            bands_present = sort_bands(set(table["band"]))

            if self.config.useMagnitude:
                all_mag = []
                for b in bands_present:
                    mask = (table["band"] == b) & (table["flux"] > 0)
                    if not np.any(mask):
                        continue
                    mag_vals = table["mag"][mask]
                    all_mag.append(mag_vals)
                    plot_lightcurve_band(
                        ax,
                        x[mask],
                        mag_vals,
                        table["mag_err"][mask],
                        b,
                        count=int(np.sum(mask)),
                    )

                # Upper limits for negative flux
                if self.config.showNegativeFlux:
                    negative = table["flux"] <= 0
                    if np.any(negative):
                        flux_err_neg = table["flux_err"][negative]
                        upper_flux = 3 * flux_err_neg
                        # AB magnitude zeropoint for nJy: m = -2.5*log10(f_nJy) + 31.4
                        with np.errstate(divide="ignore", invalid="ignore"):
                            upper_mag = -2.5 * np.log10(upper_flux) + _AB_NJY_ZEROPOINT
                            upper_mag = np.where(
                                np.isfinite(upper_mag),
                                upper_mag,
                                np.nan,
                            )
                        valid = np.isfinite(upper_mag)
                        if np.any(valid):
                            ax.scatter(
                                x[negative][valid],
                                upper_mag[valid],
                                marker="v",
                                s=40,
                                alpha=0.4,
                                color="0.5",
                                zorder=0,
                                edgecolors="0.3",
                                linewidths=0.5,
                                label=r"Upper limit (3$\sigma$)",
                            )

                # Set y-limits from mag values only (ignore error bars);
                # use normal order — format_lightcurve_axes will invert.
                if all_mag:
                    all_mag = np.concatenate(all_mag)
                    finite = all_mag[np.isfinite(all_mag)]
                    if len(finite) > 0:
                        mag_min, mag_max = np.min(finite), np.max(finite)
                        pad = 0.15 * (mag_max - mag_min) if mag_max > mag_min else 0.5
                        ax.set_ylim(mag_min - pad, mag_max + pad)

                format_lightcurve_axes(
                    ax,
                    ylabel="Apparent Magnitude (mag)",
                    invert_y=True,
                )
            else:
                for b in bands_present:
                    mask = table["band"] == b
                    if not np.any(mask):
                        continue
                    plot_lightcurve_band(
                        ax,
                        x[mask],
                        table["flux"][mask],
                        table["flux_err"][mask],
                        b,
                        count=int(np.sum(mask)),
                    )
                ax.axhline(
                    y=0,
                    color="0.6",
                    linestyle="--",
                    linewidth=0.8,
                    alpha=0.6,
                    zorder=0,
                )
                format_lightcurve_axes(
                    ax,
                    ylabel="Flux (counts)",
                    invert_y=False,
                )

            if self.config.plotTitle:
                ax.set_title(self.config.plotTitle)
            elif self.config.targetName:
                set_title(ax, self.config.targetName, subtitle="Forced Photometry")
            else:
                set_title(ax, "Forced Photometry Lightcurve")

            ax.legend(loc="best")
            fig.tight_layout()
        return fig


# =============================================================================
# Difference Image Forced Photometry Lightcurve
# =============================================================================


class ForcedPhotDiffimLightcurveConnections(
    pipeBase.PipelineTaskConnections,
    dimensions=("instrument",),
    defaultTemplates={
        "inputName": "forced_phot_diffim_radec",
        "outputName": "forced_phot_diffim_lightcurve",
        "visitTableName": "preliminary_visit_table",
    },
):
    """Connections for ForcedPhotDiffimLightcurveTask.

    Note: This task operates at the instrument level, collecting all forced
    photometry catalogs across visits/bands and consolidating them into a
    single lightcurve. The band information is extracted from visit metadata.
    """

    forcedPhotCatalogs = ct.Input(
        doc="Forced photometry catalogs from ForcedPhotDiffimRaDecTask.",
        name="{inputName}",
        storageClass="ArrowAstropy",
        dimensions=("instrument", "visit", "detector"),
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
        doc="Consolidated lightcurve table from difference image forced photometry.",
        name="{outputName}_table",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
    )
    lightcurvePlot = ct.Output(
        doc="Lightcurve plot from difference image forced photometry.",
        name="{outputName}_plot",
        storageClass="Plot",
        dimensions=("instrument",),
    )


class ForcedPhotDiffimLightcurveConfig(
    pipeBase.PipelineTaskConfig,
    pipelineConnections=ForcedPhotDiffimLightcurveConnections,
):
    """Configuration for ForcedPhotDiffimLightcurveTask."""

    targetName = pexConfig.Field(
        dtype=str,
        default="",
        doc="Target name for plot title and labeling.",
    )
    minSnr = pexConfig.Field(
        dtype=float,
        default=0.0,
        doc="Minimum |S/N| for points to include (0 = include all).",
    )
    plotTitle = pexConfig.Field(
        dtype=str,
        default="",
        doc="Optional plot title override.",
    )
    useMagnitude = pexConfig.Field(
        dtype=bool,
        default=True,
        doc="Plot apparent magnitudes (True) or difference fluxes (False).",
    )
    zeroPoint = pexConfig.Field(
        dtype=float,
        default=31.4,
        doc="Instrumental zero point for flux-to-magnitude conversion.",
    )
    showNegativeFlux = pexConfig.Field(
        dtype=bool,
        default=True,
        doc="Show negative flux points as upper limits when plotting magnitudes.",
    )
    fluxColumn = pexConfig.Field(
        dtype=str,
        default="diffFlux",
        doc="Flux column name in forced phot diffim output.",
    )
    fluxErrColumn = pexConfig.Field(
        dtype=str,
        default="diffFluxErr",
        doc="Flux error column name in forced phot diffim output.",
    )


class ForcedPhotDiffimLightcurveTask(pipeBase.PipelineTask):
    """Consolidate difference image forced photometry into a lightcurve.

    This task is specifically for difference image forced photometry, where
    flux values can be negative (source fainter than template) or positive
    (source brighter than template).

    By default, positive difference fluxes are converted to apparent
    magnitudes for plotting. Negative fluxes (source fainter than template)
    are shown as upper limits. Set ``useMagnitude=False`` to plot raw
    difference fluxes instead.
    """

    ConfigClass = ForcedPhotDiffimLightcurveConfig
    _DefaultName = "forcedPhotDiffimLightcurve"

    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        """Execute the task."""
        visit_table = butlerQC.get(inputRefs.visitTable)

        # Build visit -> band lookup from visit table
        visit_band = {}
        if "band" in visit_table.colnames:
            for row in visit_table:
                visit_band[row["visit"]] = row.get("band", "unknown")

        rows = self._collect_measurements(
            visit_table, inputRefs.forcedPhotCatalogs, butlerQC, visit_band
        )

        if not rows:
            raise pipeBase.NoWorkFound(
                "No difference image forced photometry measurements found."
            )

        table = Table(rows=rows)
        if "mjd" in table.colnames:
            table.sort("mjd")

        # Determine band for plot title (use most common or "multi")
        bands = list(set(row.get("band", "unknown") for row in rows))
        band_label = bands[0] if len(bands) == 1 else "multi-band"

        fig = self._make_plot(table, band_label)
        butlerQC.put(
            pipeBase.Struct(lightcurveTable=table, lightcurvePlot=fig),
            outputRefs,
        )

    def _collect_measurements(
        self,
        visit_table: Table,
        catalog_refs: list,
        butlerQC,
        visit_band: dict,
    ) -> list[dict]:
        """Collect measurements from all forced phot diffim catalogs.

        Parameters
        ----------
        visit_table : `astropy.table.Table`
            Visit table with MJD information.
        catalog_refs : `list`
            List of deferred dataset references for forced phot catalogs.
        butlerQC : `ButlerQuantumContext`
            Butler quantum context for loading data.
        visit_band : `dict`
            Mapping from visit ID to band name.

        Returns
        -------
        rows : `list` of `dict`
            Collected measurements as list of row dictionaries.
        """
        visit_mjd = {row["visit"]: row["expMidptMJD"] for row in visit_table}

        rows = []
        for ref in catalog_refs:
            visit_id = ref.dataId.get("visit")
            mjd = visit_mjd.get(visit_id, np.nan)
            band = visit_band.get(visit_id, "unknown")

            # Load catalog (may be DeferredDatasetHandle)
            if hasattr(ref, "get"):
                catalog = ref.get()
            else:
                catalog = butlerQC.get(ref)
            if isinstance(catalog, DeferredDatasetHandle):
                catalog = catalog.get()

            if len(catalog) == 0:
                continue

            for record in catalog:
                flux = self._get_value(record, self.config.fluxColumn)
                flux_err = self._get_value(record, self.config.fluxErrColumn)

                if flux is None or flux_err is None:
                    continue

                snr = flux / flux_err if flux_err > 0 else 0.0

                # For diffim, filter by |S/N|
                if self.config.minSnr > 0 and abs(snr) < self.config.minSnr:
                    continue

                ra = self._get_value(record, "ra")
                dec = self._get_value(record, "dec")
                input_id = self._get_value(record, "input_id", default=0)

                # Convert positive fluxes to apparent magnitude
                zp = self.config.zeroPoint
                if flux > 0:
                    mag = -2.5 * np.log10(flux) + zp
                    mag_err = 2.5 / np.log(10) * flux_err / flux
                else:
                    mag = np.nan
                    mag_err = np.nan

                rows.append(
                    {
                        "mjd": mjd,
                        "band": band,
                        "visit": visit_id,
                        "input_id": input_id,
                        "ra": ra,
                        "dec": dec,
                        "diff_flux": flux,
                        "diff_flux_err": flux_err,
                        "mag": mag,
                        "mag_err": mag_err,
                        "snr": snr,
                    }
                )

        return rows

    def _get_value(self, record, column: str, default=None):
        """Safely get a value from a record."""
        try:
            val = record[column]
            if hasattr(val, "item"):
                val = val.item()
            return val
        except (KeyError, IndexError):
            return default

    def _make_plot(self, table: Table, band: str):
        """Generate multi-band lightcurve plot from difference image photometry."""
        from lsst.obs.nickel.plotting import (
            FIGURE_SIZE,
            format_lightcurve_axes,
            get_band_style,
            plot_lightcurve_band,
            publication_style,
            set_title,
            sort_bands,
        )

        with publication_style():
            fig, ax = plt.subplots(figsize=FIGURE_SIZE)
            x = table["mjd"] if "mjd" in table.colnames else np.arange(len(table))
            bands_present = sort_bands(set(table["band"]))

            if self.config.useMagnitude:
                all_mag = []
                for b in bands_present:
                    mask = (table["band"] == b) & (table["diff_flux"] > 0)
                    if not np.any(mask):
                        continue
                    mag_vals = table["mag"][mask]
                    all_mag.append(mag_vals)
                    plot_lightcurve_band(
                        ax,
                        x[mask],
                        mag_vals,
                        table["mag_err"][mask],
                        b,
                        count=int(np.sum(mask)),
                    )

                # Upper limits for negative flux (source fainter than template)
                if self.config.showNegativeFlux:
                    negative = table["diff_flux"] <= 0
                    if np.any(negative):
                        flux_err_neg = table["diff_flux_err"][negative]
                        upper_flux = 3 * flux_err_neg
                        with np.errstate(divide="ignore", invalid="ignore"):
                            upper_mag = (
                                -2.5 * np.log10(upper_flux) + self.config.zeroPoint
                            )
                            upper_mag = np.where(
                                np.isfinite(upper_mag),
                                upper_mag,
                                np.nan,
                            )
                        valid = np.isfinite(upper_mag)
                        if np.any(valid):
                            ax.scatter(
                                x[negative][valid],
                                upper_mag[valid],
                                marker="v",
                                s=40,
                                alpha=0.4,
                                color="0.5",
                                zorder=0,
                                edgecolors="0.3",
                                linewidths=0.5,
                                label=r"Upper limit (3$\sigma$)",
                            )

                # Set y-limits from mag values only (ignore error bars);
                # use normal order — format_lightcurve_axes will invert.
                if all_mag:
                    all_mag = np.concatenate(all_mag)
                    finite = all_mag[np.isfinite(all_mag)]
                    if len(finite) > 0:
                        mag_min, mag_max = np.min(finite), np.max(finite)
                        pad = 0.15 * (mag_max - mag_min) if mag_max > mag_min else 0.5
                        ax.set_ylim(mag_min - pad, mag_max + pad)

                format_lightcurve_axes(
                    ax,
                    ylabel="Apparent Magnitude (mag)",
                    invert_y=True,
                )
            else:
                # Plot raw difference fluxes
                y = table["diff_flux"]
                yerr = table["diff_flux_err"]
                for b in bands_present:
                    mask = table["band"] == b
                    if not np.any(mask):
                        continue
                    style = get_band_style(b)
                    ax.errorbar(
                        x[mask],
                        y[mask],
                        yerr=yerr[mask],
                        fmt=style["marker"],
                        color=style["color"],
                        label=f'{style["label"]} (N={int(np.sum(mask))})',
                        markersize=7,
                        capsize=3,
                        elinewidth=1.2,
                        capthick=1.0,
                        alpha=0.85,
                        zorder=style["zorder"],
                        markeredgecolor="black",
                        markeredgewidth=0.4,
                    )

                ax.axhline(
                    y=0,
                    color="0.4",
                    linestyle="--",
                    linewidth=0.8,
                    alpha=0.7,
                    zorder=0,
                    label="Template level",
                )
                format_lightcurve_axes(
                    ax,
                    ylabel=r"Difference Flux (science $-$ template)",
                    invert_y=False,
                )

            if self.config.plotTitle:
                ax.set_title(self.config.plotTitle)
            elif self.config.targetName:
                set_title(
                    ax, self.config.targetName, subtitle="Difference Image Photometry"
                )
            else:
                set_title(ax, "Difference Image Forced Photometry")

            ax.legend(loc="best")
            fig.tight_layout()
        return fig
