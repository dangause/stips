"""Shared test helpers for the CTIO 1.0m (Y4KCam) test suite.

These tests exercise the GENERIC STIPS machinery (``lsst.obs.stips.active``,
synthesized from ``INSTRUMENT_DIR``) bound to the CTIO 1.0m profile at
``instruments/ctio1m/profile.py``. The golden/parity assertions are unchanged
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
import importlib.util
import os
from contextlib import contextmanager
from pathlib import Path

# instruments/ctio1m/tests/conftest.py -> parents[1] == instruments/ctio1m
INSTRUMENT_DIR_PATH = Path(__file__).resolve().parents[1]


def load_ctio1m_profile():
    """Load the CTIO 1.0m profile object directly from ``../profile.py``.

    Stack-free: loads the co-located ``profile.py`` by file path (with its
    directory on ``sys.path`` so co-located hooks resolve) and returns the
    module-level ``profile`` object.
    """
    p = INSTRUMENT_DIR_PATH / "profile.py"
    import sys

    if str(p.parent) not in sys.path:
        sys.path.append(
            str(p.parent)
        )  # so co-located hooks resolve (append: don't shadow stdlib)
    spec = importlib.util.spec_from_file_location("ctio1m_profile", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.profile


@contextmanager
def active_instrument_dir():
    """Set ``INSTRUMENT_DIR`` to the CTIO 1.0m dir, reload
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
