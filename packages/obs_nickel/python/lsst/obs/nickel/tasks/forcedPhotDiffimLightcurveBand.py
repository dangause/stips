"""Pipeline tasks for per-band and combined forced photometry diffim lightcurves.

.. deprecated::
    These tasks use a fixed zeroPoint for flux-to-magnitude conversion, which
    does not account for per-visit photometric calibration. For scientifically
    accurate magnitudes, use the production lightcurve extraction tool::

        pipeline_tools/extract_lightcurve.py

    which fetches per-visit photoCalib from the Butler and applies proper
    ADU -> nJy -> AB magnitude calibration. See also ``nickel lightcurve``.

The per-band task (ForcedPhotDiffimLightcurveBandTask) produces one table and
plot per band. The combined task (ForcedPhotDiffimLightcurveCombinedTask) reads
those per-band tables and combines them onto a single multi-band figure.
"""

from __future__ import annotations

import logging

import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase
import matplotlib.pyplot as plt
import numpy as np
from astropy.table import Table, vstack
from lsst.daf.butler import DeferredDatasetHandle
from lsst.pipe.base import connectionTypes as ct

__all__ = [
    "ForcedPhotDiffimLightcurveBandConfig",
    "ForcedPhotDiffimLightcurveBandTask",
    "ForcedPhotDiffimLightcurveCombinedConfig",
    "ForcedPhotDiffimLightcurveCombinedTask",
]

_LOG = logging.getLogger(__name__)


# =============================================================================
# Per-Band Forced Photometry Diffim Lightcurve
# =============================================================================


class ForcedPhotDiffimLightcurveBandConnections(
    pipeBase.PipelineTaskConnections,
    dimensions=("instrument", "band"),
    defaultTemplates={
        "inputName": "forced_phot_diffim_radec",
        "outputName": "forced_phot_diffim_lightcurve_band",
        "visitTableName": "preliminary_visit_table",
    },
):
    """Connections for per-band forced photometry diffim lightcurve task."""

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
        doc="Per-band lightcurve table from difference image forced photometry.",
        name="{outputName}_table",
        storageClass="ArrowAstropy",
        dimensions=("instrument", "band"),
    )
    lightcurvePlot = ct.Output(
        doc="Per-band lightcurve plot from difference image forced photometry.",
        name="{outputName}_plot",
        storageClass="Plot",
        dimensions=("instrument", "band"),
    )


class ForcedPhotDiffimLightcurveBandConfig(
    pipeBase.PipelineTaskConfig,
    pipelineConnections=ForcedPhotDiffimLightcurveBandConnections,
):
    """Configuration for ForcedPhotDiffimLightcurveBandTask."""

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


class ForcedPhotDiffimLightcurveBandTask(pipeBase.PipelineTask):
    """Generate per-band lightcurve from difference image forced photometry.

    This task produces one lightcurve table and plot per band, filtering
    the input catalogs to only include visits matching the quantum's band.
    """

    ConfigClass = ForcedPhotDiffimLightcurveBandConfig
    _DefaultName = "forcedPhotDiffimLightcurveBand"

    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        """Execute the task for a single band."""
        visit_table = butlerQC.get(inputRefs.visitTable)
        band = butlerQC.quantum.dataId.get("band", "unknown")

        # Build visit -> band lookup from visit table
        visit_band = {}
        if "band" in visit_table.colnames:
            for row in visit_table:
                visit_band[row["visit"]] = row.get("band", "unknown")

        rows = self._collect_measurements(
            visit_table, inputRefs.forcedPhotCatalogs, butlerQC, visit_band, band
        )

        if not rows:
            raise pipeBase.NoWorkFound(
                f"No difference image forced photometry measurements found for band {band}."
            )

        table = Table(rows=rows)
        if "mjd" in table.colnames:
            table.sort("mjd")

        fig = self._make_plot(table, band)
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
        target_band: str,
    ) -> list[dict]:
        """Collect measurements from catalogs matching the target band."""
        visit_mjd = {row["visit"]: row["expMidptMJD"] for row in visit_table}

        rows = []
        for ref in catalog_refs:
            visit_id = ref.dataId.get("visit")
            band = visit_band.get(visit_id, "unknown")

            # Only include visits matching the target band
            if band.lower() != target_band.lower():
                continue

            mjd = visit_mjd.get(visit_id, np.nan)

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
        """Generate single-band lightcurve plot."""
        from lsst.obs.nickel.plotting import (
            FIGURE_SIZE,
            format_lightcurve_axes,
            get_band_style,
            plot_lightcurve_band,
            publication_style,
            set_title,
        )

        with publication_style():
            fig, ax = plt.subplots(figsize=FIGURE_SIZE)
            x = table["mjd"] if "mjd" in table.colnames else np.arange(len(table))

            if self.config.useMagnitude:
                positive = table["diff_flux"] > 0
                if np.any(positive):
                    plot_lightcurve_band(
                        ax,
                        x[positive],
                        table["mag"][positive],
                        table["mag_err"][positive],
                        band,
                        count=int(np.sum(positive)),
                    )

                # Upper limits for negative flux
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
                if np.any(positive):
                    finite = table["mag"][positive]
                    finite = finite[np.isfinite(finite)]
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
                style = get_band_style(band)
                ax.errorbar(
                    x,
                    table["diff_flux"],
                    yerr=table["diff_flux_err"],
                    fmt=style["marker"],
                    color=style["color"],
                    label=f'{style["label"]} (N={len(table)})',
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

            target_label = self.config.targetName or "Target"
            if self.config.plotTitle:
                ax.set_title(self.config.plotTitle)
            else:
                set_title(
                    ax, target_label, subtitle="Difference Image Photometry", band=band
                )

            ax.legend(loc="best")
            fig.tight_layout()
        return fig


# =============================================================================
# Combined Multi-Band Forced Photometry Diffim Lightcurve
# =============================================================================


class ForcedPhotDiffimLightcurveCombinedConnections(
    pipeBase.PipelineTaskConnections,
    dimensions=("instrument",),
    defaultTemplates={
        "inputName": "forced_phot_diffim_lightcurve_band",
        "outputName": "forced_phot_diffim_lightcurve_combined",
    },
):
    """Connections for combined multi-band forced photometry diffim lightcurve."""

    lightcurveTables = ct.Input(
        doc="Per-band lightcurve tables produced by ForcedPhotDiffimLightcurveBandTask.",
        name="{inputName}_table",
        storageClass="ArrowAstropy",
        dimensions=("instrument", "band"),
        multiple=True,
        deferLoad=True,
    )
    combinedTable = ct.Output(
        doc="Combined multi-band lightcurve table.",
        name="{outputName}_table",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
    )
    combinedPlot = ct.Output(
        doc="Combined multi-band lightcurve plot.",
        name="{outputName}_plot",
        storageClass="Plot",
        dimensions=("instrument",),
    )


class ForcedPhotDiffimLightcurveCombinedConfig(
    pipeBase.PipelineTaskConfig,
    pipelineConnections=ForcedPhotDiffimLightcurveCombinedConnections,
):
    """Configuration for ForcedPhotDiffimLightcurveCombinedTask."""

    targetName = pexConfig.Field(
        dtype=str,
        default="",
        doc="Target name for the plot title.",
    )
    plotTitle = pexConfig.Field(
        dtype=str,
        default="",
        doc="Optional plot title override.",
    )
    useMagnitude = pexConfig.Field(
        dtype=bool,
        default=True,
        doc="Plot magnitudes (True) or fluxes (False).",
    )
    zeroPoint = pexConfig.Field(
        dtype=float,
        default=31.4,
        doc="Zero point for flux-to-magnitude conversion.",
    )
    showNegativeFlux = pexConfig.Field(
        dtype=bool,
        default=True,
        doc="Show negative flux points as upper limits when plotting magnitudes.",
    )


class ForcedPhotDiffimLightcurveCombinedTask(pipeBase.PipelineTask):
    """Combine per-band forced photometry diffim lightcurves into one plot."""

    ConfigClass = ForcedPhotDiffimLightcurveCombinedConfig
    _DefaultName = "forcedPhotDiffimLightcurveCombined"

    def runQuantum(self, butlerQC, inputRefs, outputRefs):
        tables = []
        for ref in inputRefs.lightcurveTables:
            if hasattr(ref, "get"):
                tbl = ref.get()
            else:
                tbl = butlerQC.get(ref)
            if isinstance(tbl, DeferredDatasetHandle):
                tbl = tbl.get()
            if tbl is not None and len(tbl) > 0:
                tables.append(tbl)

        if not tables:
            raise pipeBase.NoWorkFound(
                "No per-band forced photometry diffim lightcurve tables found to combine."
            )

        combined = vstack(tables)
        if "mjd" in combined.colnames:
            combined.sort("mjd")

        fig = self._make_plot(combined)
        butlerQC.put(
            pipeBase.Struct(combinedTable=combined, combinedPlot=fig),
            outputRefs,
        )

    def _make_plot(self, table: Table):
        """Generate combined multi-band lightcurve plot."""
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
                    mask = np.array(table["band"] == b)
                    if "mag" in table.colnames:
                        valid = mask & np.isfinite(table["mag"])
                    else:
                        valid = mask & (table["diff_flux"] > 0)
                    if not np.any(valid):
                        continue

                    if "mag" in table.colnames:
                        y = table["mag"][valid]
                        yerr = (
                            table["mag_err"][valid]
                            if "mag_err" in table.colnames
                            else None
                        )
                    else:
                        y = (
                            -2.5 * np.log10(table["diff_flux"][valid])
                            + self.config.zeroPoint
                        )
                        yerr = (
                            2.5
                            / np.log(10)
                            * table["diff_flux_err"][valid]
                            / table["diff_flux"][valid]
                            if "diff_flux_err" in table.colnames
                            else None
                        )
                    all_mag.append(np.asarray(y))
                    plot_lightcurve_band(
                        ax,
                        x[valid],
                        y,
                        yerr,
                        b,
                        count=int(np.sum(valid)),
                    )

                # Upper limits for negative flux
                if self.config.showNegativeFlux:
                    flux_col = "diff_flux" if "diff_flux" in table.colnames else "flux"
                    flux_err_col = (
                        "diff_flux_err"
                        if "diff_flux_err" in table.colnames
                        else "flux_err"
                    )
                    if flux_col in table.colnames:
                        negative = table[flux_col] <= 0
                        if np.any(negative):
                            flux_err_neg = table[flux_err_col][negative]
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
                flux_col = "diff_flux" if "diff_flux" in table.colnames else "flux"
                flux_err_col = (
                    "diff_flux_err" if "diff_flux_err" in table.colnames else "flux_err"
                )
                for b in bands_present:
                    mask = np.array(table["band"] == b)
                    if not np.any(mask):
                        continue
                    style = get_band_style(b)
                    yerr = (
                        table[flux_err_col][mask]
                        if flux_err_col in table.colnames
                        else None
                    )
                    ax.errorbar(
                        x[mask],
                        table[flux_col][mask],
                        yerr=yerr,
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
                bands_str = "+".join(b.upper() for b in bands_present)
                set_title(
                    ax,
                    "Forced Photometry (Diffim)",
                    subtitle=f"Combined ({bands_str})",
                )

            ax.legend(loc="best")
            fig.tight_layout()
        return fig
