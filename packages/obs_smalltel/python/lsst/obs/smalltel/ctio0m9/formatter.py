"""Raw data formatter for the CTIO 0.9m telescope."""

from __future__ import annotations

__all__ = ("Ctio0m9RawFormatter",)

from lsst.obs.smalltel.base_formatter import GenericRawFormatter

from .instrument import Ctio0m9
from .translator import Ctio0m9Translator


class Ctio0m9RawFormatter(GenericRawFormatter):
    instrument_class = Ctio0m9
    translatorClass = Ctio0m9Translator
