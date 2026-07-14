"""Shared dataset-reference loading for obs_stips PipelineTasks.

This module deliberately has no hard LSST import so it stays importable in a
plain venv (mirroring ``differentialPhot``'s stackless-import contract).
"""

from __future__ import annotations

__all__ = ["load_ref"]

try:
    from lsst.daf.butler import DeferredDatasetHandle
except ImportError:  # pragma: no cover - exercised only outside the stack
    DeferredDatasetHandle = None


def load_ref(butlerQC, ref):
    """Load the in-memory dataset behind ``ref``.

    API contract: depending on the middleware version and whether the input
    connection was declared with ``deferLoad=True``, ``ref`` may be

    1. a ``DeferredDatasetHandle`` (has ``.get()``),
    2. a plain ``DatasetRef`` that must go through ``butlerQC.get(ref)``, and
    3. either path may itself yield a ``DeferredDatasetHandle`` that needs one
       more ``.get()``.

    This helper normalizes all three so tasks don't have to copy the
    triple-fallback dance.
    """
    obj = ref.get() if hasattr(ref, "get") else butlerQC.get(ref)
    if DeferredDatasetHandle is not None and isinstance(obj, DeferredDatasetHandle):
        obj = obj.get()
    return obj
