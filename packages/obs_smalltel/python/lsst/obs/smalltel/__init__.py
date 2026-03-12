from .nickel.instrument import Nickel
from .nickel.translator import NickelTranslator

__all__ = [
    "Nickel",
    "NickelTranslator",
]

# Import tasks submodule for LSST doImport discovery
try:
    from . import tasks  # noqa: F401

    __all__.append("tasks")
except ImportError:
    pass
