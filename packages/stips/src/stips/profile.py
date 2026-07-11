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


@dataclass(frozen=True)
class CrosstalkSpec:
    """Declarative intra-detector crosstalk coefficients for a multi-amp camera.

    ``coeffs`` is an N×N matrix (N = number of amplifiers) where ``coeffs[i][j]``
    is the fraction of amplifier ``j``'s signal that appears, spuriously, in
    amplifier ``i`` — the LSST ``CrosstalkCalib`` convention (amp index ``i``
    matches ``detector.getAmplifiers()[i]``). The diagonal is zero (an amp does
    not cross-talk into itself). ``units`` maps to
    ``CrosstalkCalib.crosstalkRatiosUnits`` ("adu" or "electron").

    This is stack-free and validates only structure (square, zero diagonal, N≥2).
    The N == camera-amp-count check happens at build time, where the camera is
    available.
    """

    coeffs: list[list[float]]
    units: str = "adu"

    def __post_init__(self) -> None:
        n = len(self.coeffs)
        if n < 2:
            raise ValueError(f"crosstalk needs at least 2 amplifiers, got {n}x{n}")
        for i, row in enumerate(self.coeffs):
            if len(row) != n:
                raise ValueError(
                    f"crosstalk matrix must be square; row {i} has "
                    f"{len(row)} entries, expected {n}"
                )
            if row[i] != 0.0:
                raise ValueError(
                    f"crosstalk diagonal must be zero; coeffs[{i}][{i}]={row[i]}"
                )

    @property
    def n_amp(self) -> int:
        """Number of amplifiers (matrix dimension)."""
        return len(self.coeffs)


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
    # ISR config overrides applied (as `pipetask -c <isr_label>:<key>=<value>`) to
    # every ISR invocation — calib build (`cpBiasIsr`/`cpFlatIsr`) and science
    # (`isr`) — so the master bias/flat and the science frames they correct stay
    # consistent. Lets an instrument toggle ISR steps without forking the shared
    # pipelines, e.g. `{"doDefect": False}` (no defect maps) or
    # `{"overscan.doParallelOverscan": True}` (multi-amp parallel overscan).
    isr_overrides: dict[str, Any] = field(default_factory=dict)
    # Declarative intra-detector crosstalk for multi-amp cameras. When set, STIPS
    # builds a CrosstalkCalib from this matrix, certifies it into the calib chain,
    # and enables ISR crosstalk correction. None disables crosstalk entirely.
    crosstalk: Optional["CrosstalkSpec"] = None
    # Name of an optional EUPS data package of curated calibrations (defects,
    # crosstalk, ...), e.g. "obs_nickel_data". STIPS eups-setup's it into the
    # stack environment when its directory resolves (see ``package_dir``).
    obs_data_package: Optional[str] = None
    # Explicit override for where ``obs_data_package`` lives on disk. Absolute
    # paths are used as-is; a relative path is resolved against the active
    # instrument dir (INSTRUMENT_DIR), so a fork can co-locate the data package
    # under its own instruments/<x>/ tree (e.g. package_dir="obs_<x>_data").
    # When None, STIPS looks for <instrument_dir>/<obs_data_package> and then the
    # reference packages/<obs_data_package> layout. See
    # ``stips.core.config.resolve_data_package_dir`` for the full precedence.
    package_dir: Optional[str] = None
    refcat_path: Optional[str] = None
    # PS1-template policy: maps a LOCAL science band name -> the PS1 band name to
    # download for it (orientation is LOCAL -> PS1, the direction the framework
    # asks in: "given this local science band, is it PS1-eligible and which PS1
    # cutout do I fetch?"). The map's KEYS are the local bands eligible for
    # external PS1 templates; every other band falls back to a coadd template in
    # "auto" mode. PS1 serves grizy, so a Johnson-Cousins instrument like Nickel
    # maps only its r/i bands (``{"r": "r", "i": "i"}``); a Sloan fork could add
    # ``{"g": "g"}``. The default (empty dict) means "no PS1 templates" — the safe
    # choice for an unknown fork, which then uses coadd templates for every band.
    ps1_band_map: dict[str, str] = field(default_factory=dict)
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
