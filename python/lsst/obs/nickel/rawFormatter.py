# python/lsst/obs/nickel/rawFormatter.py

__all__ = ["NickelRawFormatter"]

from lsst.obs.base import FitsRawFormatterBase

from ._instrument import Nickel
from .nickelFilters import NICKEL_FILTER_DEFINITIONS
from .translator import NickelTranslator


class NickelRawFormatter(FitsRawFormatterBase):
    """Raw data formatter for the Nickel telescope."""

    translatorClass = NickelTranslator
    filterDefinitions = NICKEL_FILTER_DEFINITIONS

    def getDetector(self, id):
        return Nickel().getCamera()[id]
