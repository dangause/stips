"""Shared profile-resolution helpers for standalone pipeline_tools CLIs.

These tools run in-stack as argparse ``main()``s and need the active
instrument name / collection prefix. Historically each carried a private
``_resolve_instrument`` that returned ``"Nickel"`` when the profile was
unavailable — silently masquerading as Nickel for any fork with a broken
``INSTRUMENT_DIR`` (F-043: queries against ``instrument='Nickel'`` yield empty
results or write to the wrong repo). These helpers fail loud instead, mirroring
``Config.require_profile()``'s actionable message. Tools that expose an
explicit ``--instrument`` flag keep that escape hatch: resolution fails only
when BOTH the flag and a loadable profile are absent.
"""

from __future__ import annotations

import sys

from stips.core.config import load_active_profile

_NO_PROFILE_HINT = (
    "set INSTRUMENT_DIR to instruments/<name>/ (containing profile.py) in your "
    "config env: block, or pass --instrument"
)


def resolve_instrument_name(instrument: str | None) -> str:
    """Return the instrument name from ``--instrument`` or the active profile.

    Exits with an actionable error when neither is available (was: ``"Nickel"``).
    """
    if instrument:
        return instrument
    try:
        return load_active_profile().name
    except Exception as exc:  # noqa: BLE001 - surface any load failure as a hint
        sys.exit(f"instrument profile not loaded ({exc}); {_NO_PROFILE_HINT}.")


def resolve_collection_prefix(instrument: str | None = None) -> str:
    """Return the collection prefix from the active profile.

    Falls back to an explicit ``--instrument`` name (``collection_prefix`` ==
    instrument name for these single-detector instruments) when the profile is
    unavailable; exits loud when neither the profile nor ``--instrument`` is
    available (was: ``"Nickel"``).
    """
    try:
        return load_active_profile().collection_prefix
    except Exception as exc:  # noqa: BLE001 - surface any load failure as a hint
        if instrument:
            return instrument
        sys.exit(f"instrument profile not loaded ({exc}); {_NO_PROFILE_HINT}.")
