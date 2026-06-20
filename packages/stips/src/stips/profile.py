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
    """Everything instrument-specific, in one object.

    The two filter fields point in opposite directions: ``filters`` maps
    physical_filter->band; ``filter_aliases`` maps raw header values->physical_filter.
    """

    name: str
    site: Site
    # physical_filter -> band (canonical registry; drives FilterDefinitionCollection)
    filters: dict[str, str | None]
    header_map: dict[str, Field]
    camera: str
    filter_key: str = "FILTNAM"
    # raw FITS filter value -> physical_filter (case-insensitive lookup; drives to_physical_filter)
    filter_aliases: dict[str, str] = field(default_factory=dict)
    const_map: dict[str, Any] = field(default_factory=dict)
    night_to_dayobs_offset_days: int = 1
    # FQ instrument class path for butler register-instrument,
    # e.g. "lsst.obs.stips.active.Instrument"
    instrument_class: Optional[str] = None
    policy_name: Optional[str] = None
    collection_prefix: Optional[str] = None
    skymap_name: Optional[str] = None
    skymap_collection: Optional[str] = None
    obs_data_package: Optional[str] = None
    package_dir: Optional[str] = None
    refcat_path: Optional[str] = None
    # Optional data-fetch hook. Signature:
    #   fetch_data(night: str, config: Config, *, overwrite: bool = False) -> str
    # Returns one of "ok" | "not_found" | "failed". When None, `stips download`
    # reports that download is not configured for this instrument (no crash).
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
