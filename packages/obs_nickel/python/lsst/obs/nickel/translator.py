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


EPOCH0 = astropy.time.Time("2000-01-01T00:00:00", scale="utc")


class NickelTranslator(FitsTranslator):
    """Metadata translator for the Nickel telescope at Lick Observatory."""

    name = "Nickel"
    supported_instrument = "Nickel"

    # _const_map includes properties that you may not know, nor can calculate.
    _const_map = {
        "boresight_rotation_angle": Angle(0.0 * u.deg),
        "boresight_rotation_coord": "sky",
    }

    # _trivial_map includes properties that can be taken directly from header
    _trivial_map: dict[str, str | list[str] | tuple[Any, ...]] = {
        "exposure_time": ("EXPTIME", {"unit": u.s, "default": 0.0 * u.s}),
        "dark_time": ("EXPTIME", {"unit": u.s, "default": 0.0 * u.s}),
        "boresight_airmass": ("AIRMASS", {"default": float("nan")}),
        # "observation_id": ("OBSNUM", {"default": "0"}),
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
    def to_day_obs(self) -> int:
        """Observing day as YYYYMMDD (UTC), using only DATE."""
        return int(self.to_datetime_end().datetime.strftime("%Y%m%d"))

    @cache_translation
    def to_observation_id(self) -> str:
        """String ID that must be globally unique for the instrument."""
        return f"{self.to_day_obs():08d}_{int(self._header.get('OBSNUM', 0))}"

    @cache_translation
    def to_exposure_id(self) -> int:
        """Unique exposure/visit ID that fits in 31 bits.

        ID = (days_since_2000 * 10000) + OBSNUM
        """
        obsnum = int(self._header["OBSNUM"])
        t = self.to_datetime_end()
        days = int((t - EPOCH0).to_value("day"))
        exposure_id = days * 10000 + obsnum
        if exposure_id >= 2**31:
            raise ValueError(f"exposure_id {exposure_id} is out of 31-bit range")
        return exposure_id

        # """Unique exposure integer for Nickel using only DATE and OBSNUM.

        # exposure_id = day_obs + OBSNUM
        # """
        # day_obs = self._to_day_obs()
        # obs_num = self._header.get("OBSNUM", 0)
        # return day_obs * 10000 + obs_num

    # @cache_translation
    # def to_exposure_id(self) -> int:
    #     obs_num = self._header.get("OBSNUM", 0)
    #     dt = self.to_datetime_end()
    #     return ""
    #     # return int(self._header.get("OBSNUM", 0))

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

    def to_physical_filter(self) -> str:
        raw = str(self._header.get("FILTNAM", "UNKNOWN")).strip()
        val = raw.upper()
        if val in {"OPEN", "C", "CLEAR"}:
            return "clear"
        if val in {"B", "V", "R", "I"}:
            return val
        # Sloan filters (FILTNAM: gp, g', GP, G')
        if val in {"GP", "G'"}:
            return "gp"
        if val in {"RP", "R'"}:
            return "rp"
        # Narrowband (FILTNAM: Halpha, OIII, 6563/100, 5000/100)
        if val in {"HALPHA", "H-ALPHA", "6563/100"}:
            return "Halpha"
        if val in {"OIII", "[OIII]", "5000/100"}:
            return "OIII"
        log.warning("Unrecognized FILTNAM %r, falling back to 'clear'", raw)
        return "clear"

    @cache_translation
    def to_location(self) -> EarthLocation:
        value = EarthLocation.of_site("Lick Observatory")
        return value

    @cache_translation
    def to_tracking_radec(self):
        """Get tracking RA/Dec with validation against telescope position.

        Nickel telescope has a known issue where CRVAL1/CRVAL2 (WCS keywords)
        sometimes disagree with RA/DEC (telescope control system keywords).
        This implements a tiered approach:

        1. Try CRVAL1/CRVAL2 (preferred WCS solution)
        2. If available, compare with RA/DEC keywords
        3. If they disagree by more than tolerance, use RA/DEC instead
        4. Log a warning when coordinates are corrected

        Tolerance is set to 1 degree to catch major discrepancies while
        allowing for small pointing adjustments or proper motion.
        """
        from astropy.coordinates import SkyCoord

        tolerance_deg = 1.0  # Degree tolerance for coordinate agreement

        # Try to get CRVAL coordinates (WCS solution)
        crval_coord = None
        try:
            crval_coord = tracking_from_degree_headers(
                self,
                ("RADECSYS", "RADESYS"),
                (("CRVAL1", "CRVAL2"),),
                unit=u.deg,
            )
        except Exception as e:
            log.warning(f"Failed to read CRVAL1/CRVAL2: {e}")

        # Try to get RA/DEC coordinates (telescope control system)
        radec_coord = None
        try:
            # RA/DEC are in sexagesimal format, need to parse them
            ra_str = self._header.get("RA")
            dec_str = self._header.get("DEC")

            if ra_str and dec_str:
                # Parse sexagesimal coordinates (HH:MM:SS.SS format)
                ra_angle = Angle(ra_str, unit=u.hourangle)
                dec_angle = Angle(dec_str, unit=u.deg)

                # Get reference frame from RADECSYS/RADESYS
                ref_system = (
                    self._header.get("RADECSYS")
                    or self._header.get("RADESYS")
                    or "ICRS"
                )

                # Create SkyCoord to match the format from tracking_from_degree_headers
                radec_coord = SkyCoord(ra_angle, dec_angle, frame=ref_system.lower())
        except Exception as e:
            log.debug(f"Failed to read RA/DEC keywords: {e}")

        # If we have both, validate they agree
        if crval_coord and radec_coord:
            # Extract RA/Dec values from SkyCoord objects
            crval_ra = crval_coord.ra.to(u.deg).value
            crval_dec = crval_coord.dec.to(u.deg).value
            radec_ra = radec_coord.ra.to(u.deg).value
            radec_dec = radec_coord.dec.to(u.deg).value

            # Calculate angular separation
            ra_diff = abs(crval_ra - radec_ra)
            dec_diff = abs(crval_dec - radec_dec)

            # Handle RA wrap-around at 0/360 degrees
            if ra_diff > 180:
                ra_diff = 360 - ra_diff

            # Check if coordinates disagree
            if ra_diff > tolerance_deg or dec_diff > tolerance_deg:
                log.warning(
                    f"CRVAL1/CRVAL2 ({crval_ra:.4f}, {crval_dec:.4f}) "
                    f"disagrees with RA/DEC ({radec_ra:.4f}, {radec_dec:.4f}) "
                    f"by ΔRA={ra_diff:.2f}°, ΔDec={dec_diff:.2f}°. "
                    f"Using RA/DEC from telescope control system."
                )
                return radec_coord

        # Use CRVAL if available and validated (or RA/DEC not available)
        if crval_coord:
            return crval_coord

        # Fall back to RA/DEC if CRVAL not available
        if radec_coord:
            log.info("CRVAL1/CRVAL2 not available, using RA/DEC keywords")
            return radec_coord

        # If we get here, we have no coordinates at all
        raise ValueError("No valid tracking coordinates found in FITS header")

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
