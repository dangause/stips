"""Tasks for the Nickel telescope obs package."""

from .diaLightcurvePlot import DiaLightcurvePlotConfig, DiaLightcurvePlotTask
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
    # Forced photometry lightcurve tasks
    "ForcedPhotLightcurveTask",
    "ForcedPhotLightcurveConfig",
    "ForcedPhotDiffimLightcurveTask",
    "ForcedPhotDiffimLightcurveConfig",
    # DIA lightcurve task
    "DiaLightcurvePlotTask",
    "DiaLightcurvePlotConfig",
]
