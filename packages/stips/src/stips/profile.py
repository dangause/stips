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


@dataclass(frozen=True)
class CameraSpec:
    """Friendly single-CCD camera description. obs_stips builds the afw Camera
    from this at runtime (alternative to a raw camera/<name>.yaml)."""

    nx: int
    ny: int
    pixel_size_um: float
    plate_scale_arcsec_per_pixel: float
    flip_x: bool = False
    flip_y: bool = False
    name: str | None = None
    serial: str | None = None
    gain: float = 1.0
    read_noise: float = 0.0
    saturation: float = 65535.0


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
    # Either a path to a raw LSST camera/<name>.yaml, or a friendly CameraSpec
    # (obs_stips builds the afw Camera from a CameraSpec at runtime).
    camera: str | CameraSpec
    filter_key: str = "FILTNAM"
    # Substring matched (case-insensitive) against the FITS INSTRUME header to
    # decide whether this profile's translator handles a file. Defaults to
    # `name`; set it when the instrument name differs from INSTRUME (e.g. name
    # "CTIO1m" but INSTRUME "Y4KCam").
    instrument_header_value: Optional[str] = None
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
