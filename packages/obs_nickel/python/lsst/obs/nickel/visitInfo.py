from lsst.obs.base import MakeRawVisitInfoViaObsInfo

from .translator import NickelTranslator


class NickelVisitInfo(MakeRawVisitInfoViaObsInfo):
    metadataTranslator = NickelTranslator
