"""Raw data formatter for the CTIO/SMARTS 0.9m telescope."""

__all__ = ["Ctio0m9RawFormatter"]

from astropy.io import fits

from lsst.daf.base import PropertyList
from lsst.obs.base import FitsRawFormatterBase

from ._instrument import Ctio0m9
from .ctio0m9Filters import CTIO0M9_FILTER_DEFINITIONS
from .translator import Ctio0m9Translator


class Ctio0m9RawFormatter(FitsRawFormatterBase):
    """Raw data formatter for CTIO 0.9m single-amp data.

    NOIRLab archive FITS files are compressed (fpack), with metadata
    stored in the CompImageHDU (HDU 1) rather than the primary HDU.
    This formatter overrides readMetadata to merge headers from all HDUs.
    """

    translatorClass = Ctio0m9Translator
    filterDefinitions = CTIO0M9_FILTER_DEFINITIONS

    def getDetector(self, id):
        return Ctio0m9().getCamera()[id]

    def readMetadata(self):
        """Read metadata from all HDUs and merge.

        NOIRLab archive FITS files store headers in HDU 1 (CompImageHDU),
        not HDU 0 (PrimaryHDU). This method merges headers from all HDUs
        so the translator can find the required keywords.

        Returns
        -------
        metadata : `~lsst.daf.base.PropertyList`
            Merged header metadata.
        """
        file = self.fileDescriptor.location.path
        metadata = PropertyList()

        with fits.open(file) as hdu_list:
            # Merge headers from all HDUs, later HDUs override earlier
            for hdu in hdu_list:
                for key, value in hdu.header.items():
                    if key and key not in ("", "HISTORY", "COMMENT"):
                        # PropertyList requires scalar values
                        try:
                            metadata.set(key, value)
                        except (TypeError, ValueError):
                            # Skip complex/unsupported types
                            pass

        return metadata
