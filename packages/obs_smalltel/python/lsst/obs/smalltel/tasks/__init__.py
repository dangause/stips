"""Shared pipeline tasks for small-telescope obs packages."""

from .calibCombine import (
    NickelCalibCombineByFilterTask,
    NickelCalibCombineTask,
)
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
    # Calibration combination tasks
    "NickelCalibCombineTask",
    "NickelCalibCombineByFilterTask",
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
