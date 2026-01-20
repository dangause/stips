from ._instrument import Nickel
from ._version import __version__
from .translator import NickelTranslator

__all__ = [
    "Nickel",
    "NickelTranslator",
    "__version__",
]


# Lazy imports for tasks that depend on full LSST stack
def __getattr__(name):
    if name in (
        "ForcedPhotRaDecTask",
        "ForcedPhotRaDecConfig",
        "ForcedPhotDiffimRaDecTask",
        "ForcedPhotDiffimRaDecConfig",
    ):
        from .tasks import (
            ForcedPhotDiffimRaDecConfig,
            ForcedPhotDiffimRaDecTask,
            ForcedPhotRaDecConfig,
            ForcedPhotRaDecTask,
        )

        return {
            "ForcedPhotRaDecTask": ForcedPhotRaDecTask,
            "ForcedPhotRaDecConfig": ForcedPhotRaDecConfig,
            "ForcedPhotDiffimRaDecTask": ForcedPhotDiffimRaDecTask,
            "ForcedPhotDiffimRaDecConfig": ForcedPhotDiffimRaDecConfig,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
