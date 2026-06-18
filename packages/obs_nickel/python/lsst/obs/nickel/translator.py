from lsst.obs.stips.translator import StipsTranslator

from .profile import profile

__all__ = ["NickelTranslator"]


class NickelTranslator(StipsTranslator):
    profile = profile
