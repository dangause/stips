"""Generic raw formatter for single-CCD small telescopes."""

from __future__ import annotations

__all__ = ("GenericRawFormatter",)

from lsst.obs.base import FitsRawFormatterBase


class GenericRawFormatter(FitsRawFormatterBase):
    """Raw data formatter for small telescopes.

    Subclasses MUST set:
      - instrument_class: the GenericSmallTelInstrument subclass
      - translatorClass: the ConfigurableTranslator subclass
    """

    instrument_class = None
    translatorClass = None

    @property
    def filterDefinitions(self):
        return self.instrument_class().filterDefinitions

    def getDetector(self, id):
        return self.instrument_class().getCamera()[id]
