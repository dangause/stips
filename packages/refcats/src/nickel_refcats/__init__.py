"""Deprecated alias for :mod:`stips_refcats`.

The reference-catalog helpers were renamed from ``nickel_refcats`` to the
instrument-neutral ``stips_refcats`` (audit finding F-010). Importing this
package (or any of its submodules) emits a :class:`DeprecationWarning` and
transparently redirects to ``stips_refcats``. This compatibility shim will be
removed in a future release — import ``stips_refcats`` directly instead.
"""

from __future__ import annotations

import importlib
import sys
import warnings

warnings.warn(
    "'nickel_refcats' has been renamed to 'stips_refcats'; import "
    "'stips_refcats' instead. This compatibility shim will be removed in a "
    "future release.",
    DeprecationWarning,
    stacklevel=2,
)

import stips_refcats as _stips_refcats  # noqa: E402

# Redirect submodule imports so ``nickel_refcats.<sub>`` *is*
# ``stips_refcats.<sub>`` (same module object). This keeps ``from
# nickel_refcats.convert import convert_catalog`` and
# ``mock.patch("nickel_refcats.convert.subprocess.run")`` working against the
# renamed implementation.
_SUBMODULES = ("cli", "convert", "coverage", "gaia", "htm", "pointings", "ps1")
for _name in _SUBMODULES:
    _mod = importlib.import_module(f"stips_refcats.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _mod
    setattr(sys.modules[__name__], _name, _mod)

__all__ = list(getattr(_stips_refcats, "__all__", []))
