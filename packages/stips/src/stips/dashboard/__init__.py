"""STIPS Pipeline Monitoring Dashboard.

Provides a browser-based dashboard for monitoring pipeline run progress,
viewing per-night status grids, and tailing live logs.

Usage:
    nickel dashboard                     # Auto-detect logs dir
    nickel dashboard --logs-dir ./logs   # Explicit logs directory
    nickel dashboard --port 9000         # Custom port
"""

from __future__ import annotations

from stips.dashboard.app import create_app

__all__ = ["create_app"]
