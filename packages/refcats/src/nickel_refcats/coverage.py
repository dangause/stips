"""Pure set helpers for HTM7 refcat coverage planning (no LSST imports)."""

from __future__ import annotations

from collections.abc import Iterable


def missing_trixels(needed: Iterable[int], present: Iterable[int]) -> set[int]:
    """Trixels needed for coverage that are not already present in the Butler."""
    return {int(x) for x in needed} - {int(x) for x in present}
