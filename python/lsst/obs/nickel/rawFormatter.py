# python/lsst/obs/nickel/rawFormatter.py

__all__ = ["NickelRawFormatter"]

from astro_metadata_translator import FitsTranslator
from lsst.obs.base import FitsRawFormatterBase
from .translator import NickelTranslator
from .nickelFilters import NICKEL_FILTER_DEFINITIONS
from ._instrument import Nickel


class NickelRawFormatter(FitsRawFormatterBase):
    """Raw data formatter for the Nickel telescope."""

    translatorClass = NickelTranslator
    filterDefinitions = NICKEL_FILTER_DEFINITIONS

    def getDetector(self, id):
        return Nickel().getCamera()[id]

