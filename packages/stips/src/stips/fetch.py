"""Shared scaffolding for instrument raw-data fetch hooks.

An instrument's ``fetch.py`` implements only its backend
``_fetch_night(night, raw_root, *, overwrite, **kwargs) -> int`` (the archive
client / REST calls) and a small ``build_kwargs(env) -> dict`` that declares how
the generic config ``env`` block maps onto that backend's keyword arguments (the
instrument's env schema). Everything the two reference instruments duplicated --
reading ``config.env``, resolving ``raw_parent_dir``, ``YYYYMMDD`` night
validation, and the backend-code -> status mapping consumed by
``stips download`` -- lives here, once.

The backend return codes are a fixed contract:

  0 -> "ok"        data downloaded and/or already present
  1 -> "failed"    hard failure (one or more download errors)
  2 -> "not_found" no data found in the archive for this night

so ``fetch_data(night, config, *, overwrite=False) -> "ok" | "not_found" |
"failed"`` (the ``InstrumentProfile.fetch_data`` hook signature) is identical for
every instrument.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Callable

# Backend ``_fetch_night`` return codes -> the public ``fetch_data`` status
# strings. Anything not listed (e.g. ``1`` hard failure) maps to ``"failed"``.
_STATUS_BY_CODE = {0: "ok", 2: "not_found"}


def status_for_code(code: int) -> str:
    """Map a backend ``_fetch_night`` return code to the public status string.

    ``0 -> "ok"``, ``2 -> "not_found"``, everything else -> ``"failed"``. This is
    the single source of the mapping every instrument's ``fetch_data`` returns.
    """
    return _STATUS_BY_CODE.get(code, "failed")


def parse_night(night: str) -> dt.date:
    """Parse a ``YYYYMMDD`` observing-night string into a :class:`datetime.date`.

    Raises ``ValueError("Invalid night '{night}' (use YYYYMMDD)")`` -- the single
    source of that message for every instrument backend (Nickel's date-range
    window and CTIO's ``caldat`` conversion both go through here).
    """
    try:
        return dt.datetime.strptime(night, "%Y%m%d").date()
    except ValueError as err:
        raise ValueError(f"Invalid night '{night}' (use YYYYMMDD)") from err


def make_fetch_data(
    fetch_night: Callable[..., int],
    build_kwargs: Callable[[dict], dict],
) -> Callable[..., str]:
    """Build an ``InstrumentProfile.fetch_data`` hook from a backend fetch fn.

    ``fetch_night(night, raw_root, *, overwrite, **kwargs) -> int`` is the
    instrument's backend (``0`` ok / ``1`` hard-failure / ``2`` not-found).
    ``build_kwargs(env)`` maps the generic config ``env`` block onto that
    backend's keyword arguments (the instrument's env schema).

    The returned hook has the frozen public signature
    ``fetch_data(night, config, *, overwrite=False) -> str`` and returns
    ``"ok" | "not_found" | "failed"``.

    ``fetch_night`` is re-resolved from its defining module's namespace on every
    call (via ``fetch_night.__globals__``) so tests can monkeypatch the backend
    with ``mock.patch.object(<fetch module>, "_fetch_night", ...)`` and have the
    hook pick up the patch -- exactly as when the wrapper lived in the module.
    """
    backend_ns = fetch_night.__globals__
    backend_name = fetch_night.__name__

    def fetch_data(night: str, config: Any, *, overwrite: bool = False) -> str:
        env = getattr(config, "env", {}) or {}
        code = backend_ns[backend_name](
            night,
            Path(config.raw_parent_dir),
            overwrite=overwrite,
            **build_kwargs(env),
        )
        return status_for_code(code)

    return fetch_data
