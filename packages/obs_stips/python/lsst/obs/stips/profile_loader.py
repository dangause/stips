"""Stack-side profile loader: load instruments/<name>/profile.py by PATH.

Used by the synthesis submodule (active.py) at LSST-stack import time, where the
`stips` package may not be importable. Mirrors stips.core.config's by-path load;
keep the two in sync (test_dehardcode_parity.py guards parity). Stdlib-only
imports so it works in the bare stack env.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

__all__ = ["load_profile_from_dir"]


def load_profile_from_dir(instrument_dir: str):
    """Load the InstrumentProfile from <instrument_dir>/profile.py by path.

    Also inserts <instrument_dir> on sys.path (once) so an optional co-located
    hook/task module (e.g. fetch.py) is importable by name.
    """
    d = Path(instrument_dir)
    profile_py = d / "profile.py"
    if not profile_py.is_file():
        raise FileNotFoundError(f"No profile.py in INSTRUMENT_DIR: {instrument_dir}")
    # APPEND (not insert(0)): the instrument dir holds generically-named modules
    # (profile.py, camera/, an optional fetch.py) that would SHADOW stdlib /
    # installed modules if placed at the front of sys.path — e.g. galsim's
    # `import profile` would resolve to instruments/<name>/profile.py. Appending
    # makes stdlib/installed packages win, while a non-stdlib co-located hook
    # (e.g. `fetch`) still resolves because nothing else provides it.
    if str(d) not in sys.path:
        sys.path.append(str(d))
    spec = importlib.util.spec_from_file_location("_stips_active_profile", profile_py)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.profile
