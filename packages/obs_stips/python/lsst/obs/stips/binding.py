"""Bind an instrument profile onto the generic LSST classes.

Every ``instruments/<name>/`` dir ships a three-line nameplate module,
``instrument.py``::

    from lsst.obs.stips.binding import bind
    Instrument, Translator, RawFormatter = bind(__name__)

``bind`` imports the sibling ``profile`` module and builds the three concrete
subclasses with that profile bound, setting their ``__module__`` to the
nameplate so Butler stores ``instruments.<name>.instrument.Instrument`` — a
real, importable path that identifies the instrument on its own. The nameplate
carries no instrument logic; everything lives in the generic bases.

Not imported by ``lsst.obs.stips.__init__`` (it needs the stack); only
nameplates and the ``active`` shim import it.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from stips.profile import INSTRUMENTS_PACKAGE, instrument_dir_name

from .formatter import StipsRawFormatter
from .instrument import StipsInstrument
from .translator import StipsTranslator

__all__ = ["bind"]


def bind(nameplate: str):
    """Return ``(Instrument, Translator, RawFormatter)`` bound to the profile
    that is a sibling of the nameplate module ``nameplate``.

    ``nameplate`` must be ``instruments.<name>.instrument`` (pass ``__name__``).
    """
    package, _, leaf = nameplate.rpartition(".")
    if leaf != "instrument" or not package.startswith(f"{INSTRUMENTS_PACKAGE}."):
        raise ValueError(
            "bind() must be called as bind(__name__) from "
            f"{INSTRUMENTS_PACKAGE}/<name>/instrument.py; got {nameplate!r}"
        )
    profile_module = importlib.import_module(f"{package}.profile")
    profile = profile_module.profile
    instrument_dir = Path(profile_module.__file__).resolve().parent
    instrument_dir_name(instrument_dir)  # validates the dir name / layout

    translator = type(
        "Translator",
        (StipsTranslator,),
        {"__module__": nameplate, "profile": profile},
    )
    instrument = type(
        "Instrument",
        (StipsInstrument,),
        {
            "__module__": nameplate,
            "profile": profile,
            "translatorClass": translator,
            "instrumentDir": instrument_dir,
        },
    )
    formatter = type(
        "RawFormatter",
        (StipsRawFormatter,),
        {
            "__module__": nameplate,
            "instrumentClass": instrument,
            "translatorClass": translator,
            "filterDefinitions": instrument.filterDefinitions,
        },
    )
    instrument.rawFormatterClass = formatter
    return instrument, translator, formatter
