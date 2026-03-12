"""Metadata translator for the Nickel telescope at Lick Observatory."""

from __future__ import annotations

__all__ = ("NickelTranslator",)

import logging

import astropy.time
import astropy.units as u
from astro_metadata_translator.translator import cache_translation
from astro_metadata_translator.translators.helpers import (
    tracking_from_degree_headers,
)
from astropy.coordinates import Angle
from lsst.obs.smalltel.base_translator import ConfigurableTranslator

log = logging.getLogger(__name__)

EPOCH0 = astropy.time.Time("2000-01-01T00:00:00", scale="utc")


class NickelTranslator(ConfigurableTranslator):
    """Metadata translator for the Nickel 1-meter telescope."""

    name = "Nickel"
    supported_instrument = "Nickel"
    config_dir = "nickel"

    _observing_day_offset = astropy.time.TimeDelta(12 * 3600, format="sec", scale="tai")

    @cache_translation
    def to_instrument(self) -> str:
        return "Nickel"

    @cache_translation
    def to_day_obs(self) -> int:
        return int(self.to_datetime_end().datetime.strftime("%Y%m%d"))

    @cache_translation
    def to_observation_id(self) -> str:
        return f"{self.to_day_obs():08d}_{int(self._header.get('OBSNUM', 0))}"

    @cache_translation
    def to_exposure_id(self) -> int:
        """Unique exposure/visit ID: (days_since_2000 * 10000) + OBSNUM."""
        obsnum = int(self._header["OBSNUM"])
        t = self.to_datetime_end()
        days = int((t - EPOCH0).to_value("day"))
        exposure_id = days * 10000 + obsnum
        if exposure_id >= 2**31:
            raise ValueError(f"exposure_id {exposure_id} is out of 31-bit range")
        return exposure_id

    @cache_translation
    def to_visit_id(self) -> int:
        return self.to_exposure_id()

    @cache_translation
    def to_datetime_begin(self):
        t = self._from_fits_date("DATE-BEG", scale="utc")
        if t is not None:
            return t
        return self._from_fits_date("DATE-OBS", scale="utc")

    @cache_translation
    def to_datetime_end(self):
        begin = self.to_datetime_begin()
        end = self._from_fits_date("DATE-END", scale="utc")
        if end is None or (begin is not None and end < begin):
            exptime = float(self._header.get("EXPTIME", 0.0) or 0.0)
            if begin is not None:
                if exptime > 0.0:
                    end = begin + astropy.time.TimeDelta(
                        exptime, format="sec", scale="tai"
                    )
                else:
                    end = begin
        return end

    def to_physical_filter(self) -> str:
        """Override base class to fall back to 'clear' for unknown filters.

        The base class passes through unrecognized filter names, but Nickel
        convention is to treat any unrecognized filter as 'clear' (unfiltered).
        """
        result = super().to_physical_filter()
        known = {"B", "V", "R", "I", "clear", "gp", "rp", "Halpha", "OIII"}
        if result not in known:
            log.warning(f"Unknown filter '{result}', mapping to 'clear'")
            return "clear"
        return result

    @cache_translation
    def to_observation_type(self) -> str:
        obstype = self._header.get("OBSTYPE", "").strip().lower()
        obj = self._header.get("OBJECT", "").strip().lower()
        if obstype == "dark":
            return "bias" if "bias" in obj else "dark"
        if obstype == "flat" or "flat" in obj:
            return "flat"
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
    def to_tracking_radec(self):
        """Get tracking RA/Dec with CRVAL vs RA/DEC cross-validation.

        Handles Nickel's known stuck-DEC bug where CRVAL2 freezes at a
        previous pointing's value.
        """
        from astropy.coordinates import SkyCoord

        tolerance_deg = 1.0

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

        radec_coord = None
        try:
            ra_str = self._header.get("RA")
            dec_str = self._header.get("DEC")
            if ra_str and dec_str:
                ra_angle = Angle(ra_str, unit=u.hourangle)
                dec_angle = Angle(dec_str, unit=u.deg)
                ref_system = (
                    self._header.get("RADECSYS")
                    or self._header.get("RADESYS")
                    or "ICRS"
                )
                radec_coord = SkyCoord(ra_angle, dec_angle, frame=ref_system.lower())
        except Exception as e:
            log.debug(f"Failed to read RA/DEC keywords: {e}")

        if crval_coord and radec_coord:
            crval_ra = crval_coord.ra.to(u.deg).value
            crval_dec = crval_coord.dec.to(u.deg).value
            radec_ra = radec_coord.ra.to(u.deg).value
            radec_dec = radec_coord.dec.to(u.deg).value

            ra_diff = abs(crval_ra - radec_ra)
            dec_diff = abs(crval_dec - radec_dec)
            if ra_diff > 180:
                ra_diff = 360 - ra_diff

            if ra_diff > tolerance_deg or dec_diff > tolerance_deg:
                log.warning(
                    f"CRVAL1/CRVAL2 ({crval_ra:.4f}, {crval_dec:.4f}) "
                    f"disagrees with RA/DEC ({radec_ra:.4f}, {radec_dec:.4f}) "
                    f"by ΔRA={ra_diff:.2f}°, ΔDec={dec_diff:.2f}°. "
                    f"Using RA/DEC from telescope control system."
                )
                return radec_coord

        if crval_coord:
            return crval_coord
        if radec_coord:
            log.info("CRVAL1/CRVAL2 not available, using RA/DEC keywords")
            return radec_coord

        raise ValueError("No valid tracking coordinates found in FITS header")

    @cache_translation
    def to_temperature(self) -> u.Quantity:
        temp_celsius = self._header.get("TEMPDET", -999.0)
        return (temp_celsius + 273.15) * u.K
