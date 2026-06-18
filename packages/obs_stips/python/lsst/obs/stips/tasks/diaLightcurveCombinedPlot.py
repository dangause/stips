"""Pipeline task for generating a combined multi-band DIA lightcurve plot.

The per-band ``DiaLightcurvePlotTask`` produces one table and plot per band.
This task reads those per-band tables and combines them onto a single
multi-band figure, matching the style used by ``ForcedPhotLightcurveTask``.

WARNING: Photometric Calibration Issue
---------------------------------------
When falling back to flux-to-magnitude conversion (no 'mag' column), the
hardcoded zeroPoint (31.4) assumes flux is in nanojansky, but DIA sources
contain instrumental flux (ADU). This results in magnitudes ~10-11 mag
fainter than correct values.

For scientifically accurate magnitudes, use the extract_lightcurve.py tool
instead, which fetches photoCalib from the science exposure and applies
proper ADU → nJy → AB magnitude calibration.
"""

from __future__ import annotations

import logging

import lsst.pipe.base as pipeBase
import matplotlib.pyplot as plt
import numpy as np
from astropy.table import Table, vstack
from lsst.daf.butler import DeferredDatasetHandle
from lsst.pex.config import Field
from lsst.pipe.base import connectionTypes as ct

__all__ = [
    "DiaLightcurveCombinedPlotConfig",
    "DiaLightcurveCombinedPlotTask",
]

_LOG = logging.getLogger(__name__)


class DiaLightcurveCombinedPlotConnections(
    pipeBase.PipelineTaskConnections,
    dimensions=("instrument",),
    defaultTemplates={
        "inputName": "dia_lightcurve",
        "outputName": "dia_lightcurve_combined",
    },
):
    lightcurveTables = ct.Input(
        doc="Per-band DIA lightcurve tables produced by DiaLightcurvePlotTask.",
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


class DiaLightcurveCombinedPlotConfig(
    pipeBase.PipelineTaskConfig,
    pipelineConnections=DiaLightcurveCombinedPlotConnections,
):
    targetName = Field(
        dtype=str,
        default="",
        doc="Target name for the plot title.",
    )
    plotTitle = Field(
        dtype=str,
        default="",
        doc="Optional plot title override.",
    )
    useMagnitude = Field(
        dtype=bool,
        default=True,
        doc="Plot magnitudes (True) or fluxes (False).",
    )


class DiaLightcurveCombinedPlotTask(pipeBase.PipelineTask):
    """Combine per-band DIA lightcurve tables into one multi-band plot."""

    ConfigClass = DiaLightcurveCombinedPlotConfig
    _DefaultName = "diaLightcurveCombinedPlot"

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
                "No per-band DIA lightcurve tables found to combine."
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
        from lsst.obs.stips.plotting import (
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
                for b in bands_present:
                    mask = np.array(table["band"] == b)
                    if "mag" in table.colnames:
                        valid = mask & np.isfinite(table["mag"])
                    else:
                        valid = mask & (table["flux"] > 0)
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
                        y = -2.5 * np.log10(table["flux"][valid]) + 31.4
                        yerr = (
                            2.5
                            / np.log(10)
                            * table["flux_err"][valid]
                            / table["flux"][valid]
                            if "flux_err" in table.colnames
                            else None
                        )
                    plot_lightcurve_band(
                        ax,
                        x[valid],
                        y,
                        yerr,
                        b,
                        count=int(np.sum(valid)),
                    )
                format_lightcurve_axes(
                    ax,
                    ylabel="Apparent Magnitude (mag)",
                    invert_y=True,
                )
            else:
                for b in bands_present:
                    mask = np.array(table["band"] == b)
                    if not np.any(mask):
                        continue
                    yerr = (
                        table["flux_err"][mask]
                        if "flux_err" in table.colnames
                        else None
                    )
                    plot_lightcurve_band(
                        ax,
                        x[mask],
                        table["flux"][mask],
                        yerr,
                        b,
                        count=int(np.sum(mask)),
                    )
                format_lightcurve_axes(
                    ax,
                    ylabel="Flux (counts)",
                    invert_y=False,
                )

            if self.config.plotTitle:
                ax.set_title(self.config.plotTitle)
            elif self.config.targetName:
                set_title(ax, self.config.targetName, subtitle="DIA Photometry")
            else:
                bands_str = "+".join(b.upper() for b in bands_present)
                set_title(
                    ax,
                    "DIA Lightcurve",
                    subtitle=f"Combined ({bands_str})",
                )

            ax.legend(loc="best")
            fig.tight_layout()
        return fig
