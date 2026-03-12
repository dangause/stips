"""Nickel telescope instrument definition."""

from __future__ import annotations

__all__ = ("Nickel",)

from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument


class Nickel(GenericSmallTelInstrument):
    """Instrument class for the Nickel 1-meter telescope at Lick Observatory."""

    instrument_name = "Nickel"
    config_dir = "nickel"

    def getRawFormatter(self, dataId):
        from .formatter import NickelRawFormatter

        return NickelRawFormatter
