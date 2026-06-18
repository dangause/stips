"""STIPS instrument profile: the single surface a forking telescope team edits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class Site:
    """Telescope location. If ``name`` is set, the translator uses
    ``EarthLocation.of_site(name)``; otherwise geodetic lat/lon/elev."""

    latitude: float
    longitude: float
    elevation: float
    name: Optional[str] = None


@dataclass(frozen=True)
class Field:
    """One FITS-header to metadata mapping. unit is an astropy unit name (e.g. "s")."""

    key: str
    unit: Optional[str] = None
    default: Any = None


@dataclass
class InstrumentProfile:
    """Everything instrument-specific, in one object."""

    name: str
    site: Site
    filters: dict[str, str]
    header_map: dict[str, Field]
    camera: str
    filter_key: str = "FILTNAM"
    eups_package: Optional[str] = None
    const_map: dict[str, Any] = field(default_factory=dict)
    night_to_dayobs_offset_days: int = 1
    policy_name: Optional[str] = None
    collection_prefix: Optional[str] = None
    skymap_name: Optional[str] = None
    skymap_collection: Optional[str] = None
    obs_data_package: Optional[str] = None
    package_dir: Optional[str] = None
    refcat_path: Optional[str] = None
    fetch_data: Optional[Callable] = None
    hooks: dict[str, Callable] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.policy_name is None:
            self.policy_name = self.name
        if self.collection_prefix is None:
            self.collection_prefix = self.name


def hook(profile: InstrumentProfile, name: Optional[str] = None) -> Callable:
    """Decorator: register a quirk override on a profile, keyed by function name."""

    def deco(fn: Callable) -> Callable:
        profile.hooks[name or fn.__name__] = fn
        return fn

    return deco
