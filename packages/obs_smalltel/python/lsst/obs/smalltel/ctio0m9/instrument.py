"""CTIO 0.9m telescope instrument definition."""

from __future__ import annotations

__all__ = ("Ctio0m9",)

from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument


class Ctio0m9(GenericSmallTelInstrument):
    """Instrument class for the CTIO/SMARTS 0.9m telescope at Cerro Tololo."""

    instrument_name = "ctio0m9"
    config_dir = "ctio0m9"

    def getRawFormatter(self, dataId):
        from .formatter import Ctio0m9RawFormatter

        return Ctio0m9RawFormatter
