"""Light-curve times are mid-exposure MJDs on the TAI scale."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _extractor():
    pytest.importorskip("pandas")
    spec = importlib.util.spec_from_file_location(
        "extract_lightcurve",
        Path(__file__).resolve().parents[1]
        / "src/stips/pipeline_tools/extract_lightcurve.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError:
        pytest.skip("extract_lightcurve needs the LSST stack")
    return mod


def _span(begin, end):
    return SimpleNamespace(
        begin=SimpleNamespace(mjd=begin) if begin is not None else None,
        end=SimpleNamespace(mjd=end) if end is not None else None,
    )


def test_mid_exposure_mjd_is_the_midpoint():
    mod = _extractor()
    # A 330 s exposure: the midpoint is 165 s after the start.
    begin = 59191.0
    end = begin + 330.0 / 86400.0
    assert mod._mid_exposure_mjd(_span(begin, end)) == pytest.approx(
        begin + 165.0 / 86400.0
    )


def test_mid_exposure_mjd_without_end_falls_back_to_start():
    mod = _extractor()
    assert mod._mid_exposure_mjd(_span(59191.0, None)) == 59191.0


def test_mid_exposure_mjd_without_timespan_is_nan():
    import math

    mod = _extractor()
    assert math.isnan(mod._mid_exposure_mjd(None))
    assert math.isnan(mod._mid_exposure_mjd(_span(None, None)))


def test_time_scale_is_tai():
    assert _extractor().TIME_SCALE == "TAI"
