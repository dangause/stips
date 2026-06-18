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
        return cls.profile.name.lower() in str(header.get("INSTRUME", "")).lower()

    def _hook(self, name):
        return self.profile.hooks.get(name)

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
        fmap = self.profile.filters
        if raw in fmap:
            return fmap[raw]
        if raw.upper() in fmap:
            return fmap[raw.upper()]
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
