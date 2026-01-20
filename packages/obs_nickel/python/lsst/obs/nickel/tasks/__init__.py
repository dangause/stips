"""Tasks for the Nickel telescope obs package."""

from .forcedPhotRaDec import (
    ForcedPhotDiffimRaDecConfig,
    ForcedPhotDiffimRaDecTask,
    ForcedPhotRaDecConfig,
    ForcedPhotRaDecTask,
)

__all__ = [
    "ForcedPhotRaDecTask",
    "ForcedPhotRaDecConfig",
    "ForcedPhotDiffimRaDecTask",
    "ForcedPhotDiffimRaDecConfig",
]
