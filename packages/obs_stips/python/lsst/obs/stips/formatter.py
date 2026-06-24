__all__ = ["StipsRawFormatter"]

from lsst.obs.base import FitsRawFormatterBase


class StipsRawFormatter(FitsRawFormatterBase):
    """Generic single-CCD raw formatter.

    A binding subclass sets ``instrumentClass`` and ``translatorClass``.
    """

    instrumentClass = None  # set by binding
    translatorClass = None  # set by binding

    def getDetector(self, id):
        return self.instrumentClass().getCamera()[id]
