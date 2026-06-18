__all__ = ["NickelRawFormatter"]

from lsst.obs.stips.formatter import StipsRawFormatter

from ._instrument import Nickel
from .translator import NickelTranslator


class NickelRawFormatter(StipsRawFormatter):
    instrumentClass = Nickel
    translatorClass = NickelTranslator
    filterDefinitions = Nickel.filterDefinitions
