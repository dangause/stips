"""Instrument plugin system for multi-telescope support."""

from __future__ import annotations

from obs_nickel_data_tools.instruments.base import InstrumentPlugin

__all__ = ("get_plugin", "list_plugins", "InstrumentPlugin")

# Hardcoded registry (fallback when entry_points aren't installed)
_BUILTIN_PLUGINS: dict[str, type[InstrumentPlugin]] = {}


def _ensure_builtins() -> None:
    """Lazily populate builtin plugins on first access."""
    if not _BUILTIN_PLUGINS:
        from obs_nickel_data_tools.instruments.nickel import NickelPlugin

        _BUILTIN_PLUGINS["nickel"] = NickelPlugin


def get_plugin(name: str) -> InstrumentPlugin:
    """Look up an instrument plugin by name (case-insensitive).

    Discovery order:
    1. Builtin plugins (hardcoded in this module)
    2. Entry points (``obs_nickel_data_tools.instruments`` group)

    Args:
        name: Instrument name (e.g. "nickel", "Nickel")

    Returns:
        Instantiated InstrumentPlugin

    Raises:
        ValueError: If no plugin found for the given name
    """
    key = name.lower()

    # Try builtins first
    _ensure_builtins()
    if key in _BUILTIN_PLUGINS:
        return _BUILTIN_PLUGINS[key]()

    # Try entry_points
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="obs_nickel_data_tools.instruments")
        for ep in eps:
            if ep.name.lower() == key:
                cls = ep.load()
                return cls()
    except Exception:
        pass

    available = list(list_plugins())
    raise ValueError(f"Unknown instrument: '{name}'. Available: {', '.join(available)}")


def list_plugins() -> list[str]:
    """List all available instrument plugin names."""
    _ensure_builtins()
    names = set(_BUILTIN_PLUGINS.keys())

    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="obs_nickel_data_tools.instruments")
        for ep in eps:
            names.add(ep.name.lower())
    except Exception:
        pass

    return sorted(names)
