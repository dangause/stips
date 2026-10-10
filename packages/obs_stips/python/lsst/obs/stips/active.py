"""Backward-compatibility shim: the instrument selected by ``INSTRUMENT_DIR``.

Repos created before the by-name layout stamped
``lsst.obs.stips.active.RawFormatter`` into their raw datastore records and
``lsst.obs.stips.active.Instrument`` into the instrument record. This module
keeps those importable: it resolves ``INSTRUMENT_DIR`` to its nameplate
(``instruments.<name>.instrument``) and re-exports THE SAME class objects, so
nothing is registered twice and ``get_full_type_name(Instrument)`` already
yields the new path. New registrations never use this module; the
registration guard (stips.core.pipeline.ensure_instrument_registered)
migrates legacy instrument records with ``register-instrument --update``.
"""

from __future__ import annotations

import os

from stips.profile import import_instrument_module

__all__ = ["Instrument", "Translator", "RawFormatter"]

_instrument_dir = os.environ.get("INSTRUMENT_DIR")
if not _instrument_dir:
    raise RuntimeError(
        "lsst.obs.stips.active requires INSTRUMENT_DIR to point at instruments/<name>/. "
        "New code should import instruments.<name>.instrument directly."
    )

_module = import_instrument_module(_instrument_dir)
Instrument = _module.Instrument
Translator = _module.Translator
RawFormatter = _module.RawFormatter
