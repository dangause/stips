"""Raw data formatter for the CTIO/SMARTS 0.9m telescope."""

__all__ = ["Ctio0m9RawFormatter"]

from lsst.obs.base import FitsRawFormatterBase

from ._instrument import Ctio0m9
from .ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS
from .translator import Ctio0m9Translator


class Ctio0m9RawFormatter(FitsRawFormatterBase):
    """Raw data formatter for CTIO 0.9m single-amp data."""

    translatorClass = Ctio0m9Translator
    filterDefinitions = CTIO0M9_FILTER_DEFINITIONS

    def getDetector(self, id):
        return Ctio0m9().getCamera()[id]
