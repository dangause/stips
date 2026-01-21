from ._instrument import Nickel
from ._version import __version__
from .translator import NickelTranslator

__all__ = [
    "Nickel",
    "NickelTranslator",
    "__version__",
]

# Import tasks submodule to make it available as lsst.obs.nickel.tasks
# This is required for LSST's doImport to find task classes like:
#   lsst.obs.nickel.tasks.DiaLightcurvePlotTask
# The try/except allows the package to be imported without the full LSST stack
# for basic operations like metadata translation.
try:
    from . import tasks  # noqa: F401

    __all__.append("tasks")
except ImportError:
    # Tasks require full LSST stack (pipe_base, etc.)
    # Package can still be used for basic instrument/translator functionality
    pass
