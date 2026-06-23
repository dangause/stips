"""Generic PipelineTasks for the STIPS framework."""

from .diaLightcurveCombinedPlot import (
    DiaLightcurveCombinedPlotConfig,
    DiaLightcurveCombinedPlotTask,
)
from .diaLightcurvePlot import DiaLightcurvePlotConfig, DiaLightcurvePlotTask
from .differentialPhot import (
    DifferentialPhotConfig,
    DifferentialPhotTask,
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
    # DIA lightcurve tasks
    "DiaLightcurvePlotTask",
    "DiaLightcurvePlotConfig",
    "DiaLightcurveCombinedPlotTask",
    "DiaLightcurveCombinedPlotConfig",
    # Differential aperture photometry
    "DifferentialPhotTask",
    "DifferentialPhotConfig",
]
