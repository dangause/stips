"""Raw data formatter for the Nickel telescope."""

from __future__ import annotations

__all__ = ("NickelRawFormatter",)

from lsst.obs.smalltel.base_formatter import GenericRawFormatter

from .instrument import Nickel
from .translator import NickelTranslator


class NickelRawFormatter(GenericRawFormatter):
    instrument_class = Nickel
    translatorClass = NickelTranslator
