"""Import-time synthesis of the concrete, registerable instrument + translator
from the active profile (INSTRUMENT_DIR). Butler stores this module's class FQN
(lsst.obs.stips.active.Instrument) and re-imports it to re-instantiate — each
import re-resolves the profile from INSTRUMENT_DIR.

NOT imported by lsst.obs.stips.__init__ — importing the package stays
side-effect-free (plotting-only paths work with INSTRUMENT_DIR unset). Importing
THIS module requires INSTRUMENT_DIR (fail-loud).
"""

from __future__ import annotations

import os

from .formatter import StipsRawFormatter
from .instrument import StipsInstrument
from .profile_loader import load_profile_from_dir
from .translator import StipsTranslator

__all__ = ["Instrument", "Translator", "RawFormatter"]

_instrument_dir = os.environ.get("INSTRUMENT_DIR")
if not _instrument_dir:
    raise RuntimeError(
        "lsst.obs.stips.active requires INSTRUMENT_DIR to point at instruments/<name>/. "
        "It is set by the stips command paths and by Butler when re-instantiating the "
        "registered instrument; do not import this module directly without it."
    )

_profile = load_profile_from_dir(_instrument_dir)


class Translator(StipsTranslator):
    profile = _profile


class Instrument(StipsInstrument):
    profile = _profile
    translatorClass = Translator

    def getRawFormatter(self, dataId):
        return RawFormatter


class RawFormatter(StipsRawFormatter):
    instrumentClass = Instrument
    translatorClass = Translator
    filterDefinitions = Instrument.filterDefinitions
