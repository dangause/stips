"""Shared test helpers for the reference-instrument (Nickel) test suite.

These tests exercise the GENERIC STIPS machinery (``lsst.obs.stips.active``,
synthesized from ``INSTRUMENT_DIR``) bound to the reference Nickel profile at
``instruments/nickel/profile.py``. The golden/parity assertions are unchanged
from the legacy ``lsst.obs.nickel`` suite; only HOW the instrument/translator/
formatter is obtained changed.

``INSTRUMENT_DIR_PATH`` is computed relative to this file so the tests do not
depend on the caller exporting ``INSTRUMENT_DIR`` (the shell recipe still does,
but the helpers below set it themselves and restore the prior value).
"""

from __future__ import annotations

# NOTE: the instrument dir holds generically-named files (profile.py, camera/,
# fetch.py). The profile loaders (lsst.obs.stips.profile_loader and
# stips.core.config) APPEND it to sys.path (not insert(0)), so stdlib/installed
# modules of the same name win and are not shadowed — no pre-caching needed here.
import importlib
import os
from contextlib import contextmanager
from pathlib import Path

# instruments/nickel/tests/conftest.py -> parents[1] == instruments/nickel
INSTRUMENT_DIR_PATH = Path(__file__).resolve().parents[1]


@contextmanager
def active_instrument_dir():
    """Set ``INSTRUMENT_DIR`` to the reference Nickel dir, reload
    ``lsst.obs.stips.active``, and yield the freshly-synthesized module.

    Restores the prior ``INSTRUMENT_DIR`` on exit so tests do not leak it.
    """
    prev = os.environ.get("INSTRUMENT_DIR")
    os.environ["INSTRUMENT_DIR"] = str(INSTRUMENT_DIR_PATH)
    try:
        import lsst.obs.stips.active as active

        active = importlib.reload(active)
        yield active
    finally:
        if prev is None:
            os.environ.pop("INSTRUMENT_DIR", None)
        else:
            os.environ["INSTRUMENT_DIR"] = prev
