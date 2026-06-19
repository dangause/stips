from __future__ import annotations

import astropy.units as u
from astro_metadata_translator.translator import cache_translation
from astro_metadata_translator.translators.fits import FitsTranslator
from astropy.coordinates import Angle, EarthLocation


class StipsTranslator(FitsTranslator):
    """Generic FITS translator; subclass binds a ``profile``."""

    profile = None  # set by subclass binding

    def __init_subclass__(cls, **kw):
        p = getattr(cls, "profile", None)
        if p is not None:
            cls.name = p.name
            cls.supported_instrument = p.name
            cls._trivial_map = _build_trivial_map(p.header_map)
            cls._const_map = _build_const_map(p.const_map)
        super().__init_subclass__(**kw)

    @classmethod
    def can_translate(cls, header, filename=None):
        if cls.profile is None:
            return False
        return cls.profile.name.lower() in str(header.get("INSTRUME", "")).lower()

    def _hook(self, name):
        return self.profile.hooks.get(name)

    @cache_translation
    def to_instrument(self):
        return self.profile.name

    @cache_translation
    def to_datetime_begin(self):
        h = self._hook("datetime_begin")
        return h(self._header) if h else super().to_datetime_begin()

    @cache_translation
    def to_datetime_end(self):
        h = self._hook("datetime_end")
        return h(self._header) if h else super().to_datetime_end()

    @cache_translation
    def to_day_obs(self):
        h = self._hook("day_obs")
        return h(self._header) if h else super().to_day_obs()

    @cache_translation
    def to_observation_id(self):
        h = self._hook("observation_id")
        return h(self._header) if h else super().to_observation_id()

    @cache_translation
    def to_location(self):
        s = self.profile.site
        if s.name:
            return EarthLocation.of_site(s.name)
        return EarthLocation.from_geodetic(
            lon=s.longitude, lat=s.latitude, height=s.elevation
        )

    def to_physical_filter(self):
        raw = str(self._header.get(self.profile.filter_key, "UNKNOWN")).strip()
        aliases = self.profile.filter_aliases
        if raw in aliases:
            return aliases[raw]
        if raw.upper() in aliases:
            return aliases[raw.upper()]
        h = self._hook("unknown_filter")
        return h(self._header, raw) if h else raw

    @cache_translation
    def to_observation_type(self):
        h = self._hook("observation_type")
        return h(self._header) if h else "science"

    @cache_translation
    def to_observation_reason(self):
        h = self._hook("observation_reason")
        return h(self._header) if h else "science"

    @cache_translation
    def to_temperature(self):
        h = self._hook("temperature")
        return h(self._header) if h else None

    @cache_translation
    def to_pressure(self):
        # Small-telescope headers usually carry no barometric pressure. Default
        # to None (a fork with a barometer can supply a "pressure" hook) so
        # ObservationInfo succeeds instead of raising NotImplementedError.
        h = self._hook("pressure")
        return h(self._header) if h else None

    @cache_translation
    def to_altaz_begin(self):
        # Not in the headers; mirrors the base to_altaz_end (also None). A fork
        # can override via an "altaz_begin" hook.
        h = self._hook("altaz_begin")
        return h(self._header) if h else None

    @cache_translation
    def to_exposure_id(self):
        h = self._hook("exposure_id")
        return h(self._header) if h else None

    @cache_translation
    def to_visit_id(self):
        h = self._hook("visit_id")
        return h(self._header) if h else self.to_exposure_id()

    @cache_translation
    def to_tracking_radec(self):
        h = self._hook("tracking_radec")
        if h:
            return h(self._header, default=self._default_tracking_radec)
        return self._default_tracking_radec()

    def _default_tracking_radec(self):
        from astro_metadata_translator.translators.helpers import (
            tracking_from_degree_headers,
        )

        return tracking_from_degree_headers(
            self, ("RADECSYS", "RADESYS"), (("CRVAL1", "CRVAL2"),), unit=u.deg
        )

    # --- single-CCD defaults ---
    @cache_translation
    def to_detector_num(self):
        return 0

    @cache_translation
    def to_detector_name(self):
        return "0"

    @cache_translation
    def to_detector_serial(self):
        return ""

    @cache_translation
    def to_detector_group(self):
        return ""

    @cache_translation
    def to_detector_exposure_id(self):
        return self.to_exposure_id()


def _build_trivial_map(header_map):
    result = {}
    for prop, f in header_map.items():
        kwargs = {}
        if f.unit is not None:
            unit = getattr(u, f.unit)
            kwargs["unit"] = unit
            if f.default is not None:
                kwargs["default"] = f.default * unit
        elif f.default is not None:
            kwargs["default"] = f.default
        result[prop] = (f.key, kwargs) if kwargs else f.key
    return result


def _build_const_map(raw):
    result = {}
    for k, v in raw.items():
        result[k] = Angle(float(v) * u.deg) if k == "boresight_rotation_angle" else v
    return result
