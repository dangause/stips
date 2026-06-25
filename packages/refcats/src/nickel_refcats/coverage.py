"""Pure set helpers for HTM7 refcat coverage planning (no LSST imports)."""

from __future__ import annotations

from collections.abc import Iterable


def needed_trixels(htm_ids: Iterable[int]) -> set[int]:
    """Normalize an iterable of HTM7 ids into a set of ints."""
    return {int(x) for x in htm_ids}


def missing_trixels(needed: Iterable[int], present: Iterable[int]) -> set[int]:
    """Trixels needed for coverage that are not already present in the Butler."""
    return needed_trixels(needed) - needed_trixels(present)
