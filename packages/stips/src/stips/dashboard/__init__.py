"""STIPS Pipeline Monitoring Dashboard.

Provides a browser-based dashboard for monitoring pipeline run progress,
viewing per-night status grids, and tailing live logs.

Usage:
    stips dashboard                     # Auto-detect logs dir
    stips dashboard --logs-dir ./logs   # Explicit logs directory
    stips dashboard --port 9000         # Custom port
"""

from __future__ import annotations

__all__ = ["create_app"]


def __getattr__(name: str):
    # Lazy re-export so importing lightweight submodules (e.g. collector) does
    # not pull in the optional FastAPI dependency that app.py requires.
    if name == "create_app":
        from stips.dashboard.app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
