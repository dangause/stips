"""Tasks for the Nickel telescope obs package."""

from .diaLightcurveCombinedPlot import (
    DiaLightcurveCombinedPlotConfig,
    DiaLightcurveCombinedPlotTask,
)
from .diaLightcurvePlot import DiaLightcurvePlotConfig, DiaLightcurvePlotTask
from .forcedPhotDiffimLightcurveBand import (
    ForcedPhotDiffimLightcurveBandConfig,
    ForcedPhotDiffimLightcurveBandTask,
    ForcedPhotDiffimLightcurveCombinedConfig,
    ForcedPhotDiffimLightcurveCombinedTask,
)
from .forcedPhotLightcurve import (
    ForcedPhotDiffimLightcurveConfig,
    ForcedPhotDiffimLightcurveTask,
    ForcedPhotLightcurveConfig,
    ForcedPhotLightcurveTask,
)
from .forcedPhotRaDec import (
    ForcedPhotDiffimRaDecConfig,
    ForcedPhotDiffimRaDecTask,
    ForcedPhotRaDecConfig,
    ForcedPhotRaDecTask,
)

__all__ = [
    # Forced photometry measurement tasks
    "ForcedPhotRaDecTask",
    "ForcedPhotRaDecConfig",
    "ForcedPhotDiffimRaDecTask",
    "ForcedPhotDiffimRaDecConfig",
    # Forced photometry lightcurve tasks (instrument-level)
    "ForcedPhotLightcurveTask",
    "ForcedPhotLightcurveConfig",
    "ForcedPhotDiffimLightcurveTask",
    "ForcedPhotDiffimLightcurveConfig",
    # Forced photometry lightcurve tasks (per-band + combined)
    "ForcedPhotDiffimLightcurveBandTask",
    "ForcedPhotDiffimLightcurveBandConfig",
    "ForcedPhotDiffimLightcurveCombinedTask",
    "ForcedPhotDiffimLightcurveCombinedConfig",
    # DIA lightcurve tasks
    "DiaLightcurvePlotTask",
    "DiaLightcurvePlotConfig",
    "DiaLightcurveCombinedPlotTask",
    "DiaLightcurveCombinedPlotConfig",
]
