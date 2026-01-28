"""Pipeline task for generating lightcurves from forced photometry outputs.

This task consolidates per-visit forced photometry measurements into a single
lightcurve table and generates plots. It works with outputs from either
ForcedPhotRaDecTask (visit images) or ForcedPhotDiffimRaDecTask (difference images).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase
import matplotlib.pyplot as plt
import numpy as np
from astropy.table import Table
from lsst.pipe.base import connectionTypes as ct

if TYPE_CHECKING:
    pass

__all__ = [
    "ForcedPhotLightcurveConfig",
    "ForcedPhotLightcurveTask",
    "ForcedPhotDiffimLightcurveConfig",
    "ForcedPhotDiffimLightcurveTask",
]

_LOG = logging.getLogger(__name__)


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

            # Load catalog
            if hasattr(ref, "get"):
                catalog = ref.get()
            else:
                catalog = butlerQC.get(ref)

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
        """Generate lightcurve plot."""
        fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

        x = table["mjd"] if "mjd" in table.colnames else np.arange(len(table))

        if self.config.useMagnitude:
            # Separate positive and negative flux
            positive = table["flux"] > 0
            negative = ~positive

            # Plot positive flux as magnitudes
            if np.any(positive):
                y_pos = table["mag"][positive]
                yerr_pos = table["mag_err"][positive]
                x_pos = x[positive]
                ax.errorbar(
                    x_pos,
                    y_pos,
                    yerr=yerr_pos,
                    fmt="o",
                    capsize=3,
                    alpha=0.8,
                    label="Detection",
                )

            # Plot negative flux as upper limits
            if self.config.showNegativeFlux and np.any(negative):
                # For negative flux, show 3-sigma upper limit
                flux_neg = table["flux"][negative]  # noqa: F841
                flux_err_neg = table["flux_err"][negative]
                # Upper limit: 3 * flux_err (or |flux| + 3*err)
                upper_flux = 3 * flux_err_neg
                # Convert to magnitude (approximate upper limit)
                with np.errstate(divide="ignore", invalid="ignore"):
                    upper_mag = (
                        -2.5 * np.log10(upper_flux) + 31.4
                    )  # Approximate zeropoint
                    upper_mag = np.where(np.isfinite(upper_mag), upper_mag, np.nan)

                x_neg = x[negative]
                valid = np.isfinite(upper_mag)
                if np.any(valid):
                    ax.scatter(
                        x_neg[valid],
                        upper_mag[valid],
                        marker="v",
                        s=50,
                        alpha=0.5,
                        color="gray",
                        label="Upper limit (3σ)",
                    )

            ax.invert_yaxis()
            ax.set_ylabel("Magnitude")
        else:
            y = table["flux"]
            yerr = table["flux_err"]
            ax.errorbar(x, y, yerr=yerr, fmt="o", capsize=3, alpha=0.8)
            ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
            ax.set_ylabel("Flux")

        ax.set_xlabel("MJD")
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend()

        # Title
        if self.config.plotTitle:
            title = self.config.plotTitle
        elif self.config.targetName:
            title = f"{self.config.targetName} - Forced Photometry ({band})"
        else:
            title = f"Forced Photometry Lightcurve ({band})"
        ax.set_title(title)

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

    WARNING: Do not convert difference fluxes to magnitudes! The flux values
    represent the difference between science and template, not absolute flux.
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

            if hasattr(ref, "get"):
                catalog = ref.get()
            else:
                catalog = butlerQC.get(ref)

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
        """Generate difference flux lightcurve plot."""
        fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

        x = table["mjd"] if "mjd" in table.colnames else np.arange(len(table))
        y = table["diff_flux"]
        yerr = table["diff_flux_err"]

        # Color by sign of flux
        positive = y > 0
        negative = y < 0

        if np.any(positive):
            ax.errorbar(
                x[positive],
                y[positive],
                yerr=yerr[positive],
                fmt="o",
                capsize=3,
                alpha=0.8,
                color="C0",
                label="Brighter than template",
            )
        if np.any(negative):
            ax.errorbar(
                x[negative],
                y[negative],
                yerr=yerr[negative],
                fmt="s",
                capsize=3,
                alpha=0.8,
                color="C1",
                label="Fainter than template",
            )

        ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5, label="Template level")
        ax.set_xlabel("MJD")
        ax.set_ylabel("Difference Flux (science - template)")
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend()

        # Title
        if self.config.plotTitle:
            title = self.config.plotTitle
        elif self.config.targetName:
            title = f"{self.config.targetName} - Difference Flux ({band})"
        else:
            title = f"Difference Image Forced Photometry ({band})"
        ax.set_title(title)

        fig.tight_layout()
        return fig
