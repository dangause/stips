__all__ = ["StipsRawFormatter"]

from lsst.obs.base import FitsRawFormatterBase


class StipsRawFormatter(FitsRawFormatterBase):
    """Generic single-CCD raw formatter.

    A binding subclass sets ``instrumentClass`` and ``translatorClass``.
    """

    instrumentClass = None  # set by binding
    translatorClass = None  # set by binding

    def getDetector(self, detectorId):
        # getCamera() is cached at the instrument level (see instrument.py),
        # so per-detector fetches during bulk ingest don't rebuild the camera
        # (and re-parse its yaml) every time.
        return self.instrumentClass().getCamera()[detectorId]
