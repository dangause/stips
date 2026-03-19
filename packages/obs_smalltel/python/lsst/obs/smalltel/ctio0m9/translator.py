"""Metadata translator for the CTIO/SMARTS 0.9m telescope."""

from __future__ import annotations

__all__ = ("Ctio0m9Translator",)

import logging
from typing import Any

import astropy.time
import astropy.units as u
from astro_metadata_translator.translator import cache_translation
from astropy.coordinates import Angle, EarthLocation, SkyCoord
from lsst.obs.smalltel.base_translator import ConfigurableTranslator

log = logging.getLogger(__name__)

# Epoch for exposure ID calculation (2000-01-01)
EPOCH_MJD = 51544.0


class Ctio0m9Translator(ConfigurableTranslator):
    """Metadata translator for CTIO 0.9m with Tek2K CCD.

    The raw FITS header has INSTRUME="cfccd" (Cassegrain Focus CCD).
    This translator maps it to LSST instrument name "ctio0m9".
    """

    name = "ctio0m9"
    supported_instrument = "cfccd"
    config_dir = "ctio0m9"

    _const_map = {
        "boresight_rotation_angle": Angle(0.0 * u.deg),
        "boresight_rotation_coord": "sky",
    }

    _trivial_map: dict[str, str | list[str] | tuple[Any, ...]] = {
        "exposure_time": ("EXPTIME", {"unit": u.s, "default": 0.0 * u.s}),
        "dark_time": ("EXPTIME", {"unit": u.s, "default": 0.0 * u.s}),
        "boresight_airmass": ("AIRMASS", {"default": float("nan")}),
        "object": ("OBJECT", {"default": "UNKNOWN"}),
        "telescope": ("TELESCOP", {"default": "CTIO 0.9m"}),
        "science_program": ("PROPID", {"default": "unknown"}),
        "relative_humidity": ("HUMIDITY", {"default": 0.0}),
    }

    @classmethod
    def can_translate(cls, header, filename=None):
        """Check if this translator can handle the given header."""
        instrume = header.get("INSTRUME", "").strip().lower()
        return instrume == "cfccd"

    @cache_translation
    def to_instrument(self) -> str:
        """Return the LSST instrument name."""
        return "ctio0m9"

    @cache_translation
    def to_datetime_begin(self):
        """Parse DATE-OBS with sanitization for non-ISO8601 values.

        CTIO 0.9m data may have non-compliant DATE-OBS formats.
        This method handles various formats found in the archive.
        """
        value = self._header.get("DATE-OBS")
        if value is None:
            raise ValueError("DATE-OBS header is missing")

        # Try standard ISO8601 first
        try:
            return astropy.time.Time(value, format="isot", scale="utc")
        except ValueError:
            pass

        # Try other common formats
        try:
            # Handle YYYY/MM/DD format
            if "/" in value and "T" not in value:
                parts = value.split("/")
                if len(parts) == 3:
                    if len(parts[0]) == 4:  # YYYY/MM/DD
                        iso_date = f"{parts[0]}-{parts[1]}-{parts[2]}T00:00:00"
                    else:  # DD/MM/YY
                        year = int(parts[2])
                        if year < 50:
                            year += 2000
                        else:
                            year += 1900
                        iso_date = f"{year}-{parts[1]}-{parts[0]}T00:00:00"
                    return astropy.time.Time(iso_date, format="isot", scale="utc")
        except (ValueError, IndexError):
            pass

        raise ValueError(f"Cannot parse DATE-OBS value: {value!r}")

    @cache_translation
    def to_datetime_end(self):
        """Calculate end time from begin + EXPTIME."""
        begin = self.to_datetime_begin()
        exptime = float(self._header.get("EXPTIME", 0.0) or 0.0)
        if exptime > 0:
            return begin + astropy.time.TimeDelta(exptime, format="sec", scale="tai")
        return begin

    @cache_translation
    def to_day_obs(self) -> int:
        """Observing day as YYYYMMDD (UTC)."""
        return int(self.to_datetime_end().datetime.strftime("%Y%m%d"))

    @cache_translation
    def to_exposure_id(self) -> int:
        """Generate unique exposure ID from MJD.

        Algorithm:
        - Get MJD from DATE-OBS
        - Subtract MJD of 2000-01-01 (51544.0) as epoch
        - Multiply by 100000 to get integer with sub-day resolution
        - Result fits in 31-bit signed int for ~58 years from epoch
        """
        mjd = self.to_datetime_begin().mjd
        exposure_id = int((mjd - EPOCH_MJD) * 100000)
        if exposure_id >= 2**31:
            raise ValueError(f"exposure_id {exposure_id} is out of 31-bit range")
        return exposure_id

    @cache_translation
    def to_visit_id(self) -> int:
        """Visit ID equals exposure ID (one-to-one)."""
        return self.to_exposure_id()

    @cache_translation
    def to_observation_id(self) -> str:
        """String ID that must be globally unique for the instrument."""
        return f"ctio0m9_{self.to_exposure_id()}"

    @cache_translation
    def to_physical_filter(self) -> str:
        """Combine FILTER1 and FILTER2 for dual filter wheel.

        Examples:
        - FILTER1="V", FILTER2="OPEN" -> "V"
        - FILTER1="V", FILTER2="ND" -> "ND+V" (sorted)
        - FILTER1="OPEN", FILTER2="OPEN" -> "OPEN"
        - FILTER1="B", FILTER2="NONE" -> "B"
        """
        f1 = str(self._header.get("FILTER1", "OPEN")).strip().upper()
        f2 = str(self._header.get("FILTER2", "OPEN")).strip().upper()

        # Normalize empty/open values (OV = open variant used in archive)
        open_values = {"OPEN", "NONE", "CLEAR", "OV", ""}
        filters = sorted([f for f in [f1, f2] if f not in open_values])

        return "+".join(filters) if filters else "OPEN"

    @cache_translation
    def to_observation_type(self) -> str:
        """Map IMAGETYP to standard observation types."""
        imgtype = str(self._header.get("IMAGETYP", "")).strip().lower()
        mapping = {
            "object": "science",
            "flat": "flat",
            "bias": "bias",
            "dark": "dark",
            "focus": "focus",
            "zero": "bias",
            "dome flat": "flat",
            "sky flat": "flat",
        }
        return mapping.get(imgtype, "science")

    @cache_translation
    def to_observation_reason(self) -> str:
        """Return the reason for the observation."""
        obs_type = self.to_observation_type()
        if obs_type in ("flat", "bias", "dark"):
            return "calibration"
        if obs_type == "focus":
            return "focus"
        return "science"

    @cache_translation
    def to_tracking_radec(self):
        """Extract RA/DEC from headers.

        RA is in sexagesimal hours (HH:MM:SS.ss), DEC in degrees (DD:MM:SS.s).
        """
        ra_str = self._header.get("RA")
        dec_str = self._header.get("DEC")

        if not ra_str or not dec_str:
            raise ValueError("RA/DEC headers are missing")

        # Parse sexagesimal coordinates
        ra_angle = Angle(ra_str, unit=u.hourangle)
        dec_angle = Angle(dec_str, unit=u.deg)

        # Get reference frame from RADECSYS/RADESYS
        ref_system = (
            self._header.get("RADECSYS") or self._header.get("RADESYS") or "ICRS"
        )

        return SkyCoord(ra_angle, dec_angle, frame=ref_system.lower())

    @cache_translation
    def to_location(self) -> EarthLocation:
        """Return CTIO location."""
        return EarthLocation.from_geodetic(
            lon=-70.8148 * u.deg,
            lat=-30.1653 * u.deg,
            height=2207 * u.m,
        )

    @cache_translation
    def to_detector_num(self) -> int:
        """Single detector, ID 0."""
        return 0

    @cache_translation
    def to_detector_name(self) -> str:
        """Detector name matches camera.yaml."""
        return "SITE2K"

    @cache_translation
    def to_detector_unique_name(self) -> str:
        return "SITE2K"

    @cache_translation
    def to_detector_serial(self) -> str:
        return self._header.get("DETECTOR", "Tek2K_3")

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

    @cache_translation
    def to_temperature(self) -> u.Quantity:
        """Detector temperature if available."""
        temp = self._header.get("CCDTEMP")
        if temp is not None:
            return (float(temp) + 273.15) * u.K
        return 0.0 * u.K
