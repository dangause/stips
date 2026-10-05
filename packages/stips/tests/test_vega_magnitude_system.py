"""Magnitude system per band: Cousins B/V/R/I are Vega in Nickel's gaia_ps1 path.

The pipeline stores calibrated fluxes in nJy everywhere, but the colour terms
decide which system those nJy realise. Nickel's Landolt-fitted PS1 terms carry
the Johnson-Cousins minus PS1 constants, so B/V/R/I come out Vega; the
Sloan-like rp/ip, and every band in MONSTER mode, stay AB. Lightcurves and the
Landolt validator must say so instead of labelling everything AB.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips import cli  # noqa: E402
from stips.core.config import load_active_profile  # noqa: E402
from stips.core.lightcurve import LightcurveConfig  # noqa: E402

NICKEL = Path(__file__).resolve().parents[3] / "instruments" / "nickel"


def test_nickel_declares_cousins_vega_in_gaia_ps1_only():
    prof = load_active_profile(NICKEL)
    assert set(prof.vega_bands["gaia_ps1"]) == {"b", "v", "r", "i"}
    assert "monster" not in prof.vega_bands
    assert "rp" not in prof.vega_bands["gaia_ps1"]


def _ctx(tmp_path, yaml_text):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(yaml_text)
    return SimpleNamespace(obj={"config_path": str(cfg)})


def test_cli_reads_refcat_mode_from_yaml(tmp_path):
    config = SimpleNamespace(
        profile=SimpleNamespace(vega_bands={"gaia_ps1": ("b", "r")})
    )
    assert cli._vega_bands_from_ctx(
        _ctx(tmp_path, "refcat: {mode: gaia_ps1}\n"), config
    ) == ("b", "r")
    # Default refcat mode is MONSTER, which declares no Vega bands.
    assert cli._vega_bands_from_ctx(_ctx(tmp_path, "env: {}\n"), config) == ()


def test_cli_without_a_yaml_reports_ab():
    config = SimpleNamespace(profile=SimpleNamespace(vega_bands={"gaia_ps1": ("b",)}))
    assert cli._vega_bands_from_ctx(SimpleNamespace(obj={}), config) == ()


def test_lightcurve_config_carries_vega_bands():
    assert LightcurveConfig().vega_bands == ()
    assert LightcurveConfig(vega_bands=("r",)).vega_bands == ("r",)


def test_plot_label_names_the_systems():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("numpy")
    import importlib.util

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
    label = mod._apparent_mag_label
    assert label(pd.DataFrame({"band": ["rp"], "mag_system": ["AB"]})).endswith("(AB)")
    mixed = pd.DataFrame({"band": ["r", "rp"], "mag_system": ["Vega", "AB"]})
    assert label(mixed) == "Apparent Magnitude (Vega: R; others AB)"
