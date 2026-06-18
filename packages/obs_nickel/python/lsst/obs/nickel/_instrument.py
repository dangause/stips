from lsst.obs.stips.instrument import StipsInstrument

from .profile import profile
from .translator import NickelTranslator

__all__ = ["Nickel"]


class Nickel(StipsInstrument):
    profile = profile
    translatorClass = NickelTranslator

    def getRawFormatter(self, dataId):
        # Local import to break the binding circular dependency
        # (rawFormatter imports _instrument).
        from .rawFormatter import NickelRawFormatter

        return NickelRawFormatter
