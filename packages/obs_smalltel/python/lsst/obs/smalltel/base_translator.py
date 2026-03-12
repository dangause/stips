"""Configurable FITS translator driven by YAML keyword mappings."""

from __future__ import annotations

__all__ = ("ConfigurableTranslator",)

import logging
import math
from pathlib import Path

import astropy.units as u
import yaml
from astro_metadata_translator.translator import cache_translation
from astro_metadata_translator.translators.fits import FitsTranslator
from astropy.coordinates import Angle, EarthLocation

log = logging.getLogger(__name__)


class ConfigurableTranslator(FitsTranslator):
    """FITS header translator driven by YAML keyword mappings.

    Subclasses set ``supported_instrument`` and ``config_dir``.
    Override individual ``to_*`` methods only for telescope-specific quirks.
    """

    supported_instrument: str
    config_dir: str

    def __init_subclass__(cls, **kwargs):
        """Load header mappings from YAML when subclass is defined."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "config_dir") and cls.config_dir is not None:
            try:
                mappings = cls._load_header_map()
                cls._const_map = cls._build_const_map(mappings.get("const_map", {}))
                cls._trivial_map = cls._build_trivial_map(
                    mappings.get("trivial_map", {})
                )
            except FileNotFoundError:
                # Config not yet created — allow class definition to proceed
                pass

    @classmethod
    def can_translate(cls, header, filename=None):
        instrume = header.get("INSTRUME", "").strip().lower()
        return cls.supported_instrument.lower() in instrume

    @classmethod
    def _package_root(cls) -> Path:
        """Resolve obs_smalltel package root (same logic as base_instrument)."""
        try:
            from lsst.utils import getPackageDir

            return Path(getPackageDir("obs_smalltel"))
        except (ImportError, LookupError):
            return Path(__file__).parent.parent.parent.parent.parent

    @classmethod
    def _instruments_dir(cls) -> Path:
        return cls._package_root() / "instruments" / cls.config_dir

    @classmethod
    def _load_header_map(cls) -> dict:
        config_path = cls._instruments_dir() / "header_map.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

    @classmethod
    def _load_instrument_config(cls) -> dict:
        config_path = cls._instruments_dir() / "instrument.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

    @classmethod
    def _build_const_map(cls, raw_map: dict) -> dict:
        """Convert YAML const_map to LSST format (with Angle wrapping)."""
        result = {}
        for key, value in raw_map.items():
            if key == "boresight_rotation_angle":
                result[key] = Angle(float(value) * u.deg)
            else:
                result[key] = value
        return result

    @classmethod
    def _build_trivial_map(cls, raw_map: dict) -> dict:
        """Convert YAML trivial_map to LSST's expected format.

        LSST trivial_map entries can be:
          - str: just the header keyword name
          - tuple: (keyword, {unit: ..., default: ...})
        """
        result = {}
        for prop, spec in raw_map.items():
            if isinstance(spec, str):
                result[prop] = spec
            elif isinstance(spec, dict):
                key = spec["key"]
                kwargs = {}
                if "unit" in spec:
                    unit = getattr(u, spec["unit"])
                    kwargs["unit"] = unit
                if "default" in spec:
                    default = spec["default"]
                    if isinstance(default, float) and math.isnan(default):
                        default = float("nan")
                    if "unit" in spec:
                        unit = getattr(u, spec["unit"])
                        default = default * unit
                    kwargs["default"] = default
                result[prop] = (key, kwargs) if kwargs else key
        return result

    # --- Default to_* methods from YAML ---

    def to_physical_filter(self) -> str:
        """Map FITS filter keyword to canonical name via filter_name_map."""
        mappings = self._load_header_map()
        filter_map = mappings.get("filter_name_map", {})
        raw_filter = str(self._header.get("FILTNAM", "UNKNOWN")).strip()
        # Try exact match, then uppercase match
        if raw_filter in filter_map:
            return filter_map[raw_filter]
        upper = raw_filter.upper()
        if upper in filter_map:
            return filter_map[upper]
        return raw_filter

    @cache_translation
    def to_location(self) -> EarthLocation:
        """Return telescope EarthLocation from instrument.yaml."""
        inst_config = self._load_instrument_config()
        loc = inst_config["location"]
        return EarthLocation.from_geodetic(
            lon=loc["longitude"], lat=loc["latitude"], height=loc["elevation"]
        )

    # --- Single-CCD defaults ---

    @cache_translation
    def to_detector_num(self) -> int:
        return 0

    @cache_translation
    def to_detector_name(self) -> str:
        return "0"

    @cache_translation
    def to_detector_unique_name(self) -> str:
        return "0"

    @cache_translation
    def to_detector_serial(self) -> str:
        return ""

    @cache_translation
    def to_detector_group(self) -> str:
        return ""

    @cache_translation
    def to_detector_exposure_id(self) -> int:
        return self.to_exposure_id()

    @cache_translation
    def to_focus_z(self) -> u.Quantity:
        return 0.0 * u.m

    @cache_translation
    def to_altaz_begin(self):
        return None

    @cache_translation
    def to_pressure(self):
        return None
