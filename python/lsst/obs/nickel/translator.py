# python/lsst/obs/nickel/translator.py
from __future__ import annotations

__all__ = ("NickelTranslator",)

import logging
from typing import Any

import astropy.time
import astropy.units as u
from astro_metadata_translator.translator import cache_translation
from astro_metadata_translator.translators.fits import FitsTranslator
from astro_metadata_translator.translators.helpers import (
    tracking_from_degree_headers,
)
from astropy.coordinates import Angle, EarthLocation

log = logging.getLogger(__name__)


class NickelTranslator(FitsTranslator):
    """Metadata translator for the Nickel telescope at Lick Observatory."""

    name = "Nickel"
    supported_instrument = {"Nickel"}

    # _const_map includes properties that you may not know, nor can calculate.
    _const_map = {
        "boresight_rotation_angle": Angle(0.0 * u.deg),
        "boresight_rotation_coord": "sky",
    }

    # _trivial_map includes properties that can be taken directly from header
    _trivial_map: dict[str, str | tuple[str, dict[str, Any]]] = {
        "exposure_time": ("EXPTIME", {"unit": u.s, "default": 0.0 * u.s}),
        "dark_time": ("EXPTIME", {"unit": u.s, "default": 0.0 * u.s}),
        "boresight_airmass": ("AIRMASS", {"default": float("nan")}),
        "observation_id": ("OBSNUM", {"default": "0"}),
        "object": ("OBJECT", {"default": "UNKNOWN"}),
        "telescope": ("TELESCOP", {"default": "Nickel 1m"}),
        "science_program": ("PROGRAM", {"default": "unknown"}),
        "relative_humidity": ("HUMIDITY", {"default": 0.0}),
    }

    # observing day boundary (no test cares, but fine to keep)
    _observing_day_offset = astropy.time.TimeDelta(12 * 3600, format="sec", scale="tai")

    @classmethod
    def can_translate(cls, header, filename=None):
        val = header.get("INSTRUME", "").strip().lower()
        return "nickel" in val

    @cache_translation
    def to_instrument(self) -> str:
        return "Nickel"

    @cache_translation
    def to_exposure_id(self) -> int:
        return int(self._header.get("OBSNUM", 0))

    @cache_translation
    def to_visit_id(self) -> int:
        return self.to_exposure_id()

    @cache_translation
    def to_datetime_begin(self):
        """Use DATE-BEG if present; otherwise fall back to DATE-OBS."""
        t = self._from_fits_date("DATE-BEG", scale="utc")
        if t is not None:
            return t
        return self._from_fits_date("DATE-OBS", scale="utc")

    @cache_translation
    def to_datetime_end(self):
        """Prefer DATE-END; if missing or earlier than begin, use begin + EXPTIME.

        This also handles EXPTIME==0 (bias) by returning 'begin'.
        """
        begin = self.to_datetime_begin()

        end = self._from_fits_date("DATE-END", scale="utc")
        if end is None or (begin is not None and end < begin):
            exptime = float(self._header.get("EXPTIME", 0.0) or 0.0)
            if begin is not None:
                if exptime > 0.0:
                    # Use TAI for a pure elapsed-time delta; choice doesn’t matter
                    # as long as begin and end are compared consistently.
                    end = begin + astropy.time.TimeDelta(
                        exptime, format="sec", scale="tai"
                    )
                else:
                    end = begin
        return end

    @cache_translation
    def to_observation_type(self) -> str:
        """Return one of: object | flat | bias | dark | focus."""
        obstype = self._header.get("OBSTYPE", "").strip().lower()
        obj = self._header.get("OBJECT", "").strip().lower()

        # Explicit types
        if obstype == "dark":
            return "bias" if "bias" in obj else "dark"
        if obstype == "flat" or "flat" in obj:
            return "flat"

        # Focus/pointing/tests
        if any(w in obj for w in ("focus", "focusing", "point")):
            return "focus"
        if "test" in obj or "post" in obj:
            return "focus"

        if "bias" in obj:
            return "bias"

        return "science"

    @cache_translation
    def to_observation_reason(self) -> str:
        object_str = self._header.get("OBJECT", "").strip().lower()
        if any(w in object_str for w in ("flat", "bias", "dark")):
            return "calibration"
        if "focus" in object_str:
            return "focus"
        if "test" in object_str or "post" in object_str:
            return "test"
        if object_str == "point":
            return "pointing"
        return "science"

    @cache_translation
    def to_physical_filter(self) -> str:
        return str(self._header.get("FILTNAM", "UNKNOWN")).strip()

    @cache_translation
    def to_location(self) -> EarthLocation:

        value = EarthLocation.of_site("Lick Observatory")
        return value

    @cache_translation
    def to_tracking_radec(self):
        # Use primary WCS center; RA/Dec in degrees; frame from RADECSYS/RADESYS.
        return tracking_from_degree_headers(
            self,
            ("RADECSYS", "RADESYS"),
            (("CRVAL1", "CRVAL2"),),
            unit=u.deg,
        )

    @cache_translation
    def to_temperature(self) -> u.Quantity:
        temp_celsius = self._header.get("TEMPDET", -999.0)
        return (temp_celsius + 273.15) * u.K

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
