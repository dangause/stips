"""Unit tests for resolve_data_package_dir precedence (F-020).

The profile's curated-calibration data package must be resolvable outside the
framework's own packages/ directory so a fork can co-locate it under its own
instruments/<x>/ tree. These stack-free tests cover each precedence branch.
"""

import types
from pathlib import Path

import stips.core.config as config_mod
from stips.core.config import resolve_data_package_dir


def _profile(**kw):
    """Minimal profile stub exposing obs_data_package / package_dir."""
    kw.setdefault("obs_data_package", None)
    kw.setdefault("package_dir", None)
    return types.SimpleNamespace(**kw)


def test_no_data_package_returns_none(tmp_path):
    prof = _profile(obs_data_package=None)
    assert resolve_data_package_dir(prof, tmp_path) is None


def test_package_dir_absolute_used_as_is(tmp_path):
    explicit = tmp_path / "elsewhere" / "obs_x_data"
    prof = _profile(obs_data_package="obs_x_data", package_dir=str(explicit))
    # Absolute override honored even if it doesn't exist yet (explicit intent).
    assert resolve_data_package_dir(prof, tmp_path / "instruments" / "x") == explicit


def test_package_dir_relative_resolved_against_instrument_dir(tmp_path):
    instrument_dir = tmp_path / "instruments" / "x"
    prof = _profile(obs_data_package="obs_x_data", package_dir="obs_x_data")
    got = resolve_data_package_dir(prof, instrument_dir)
    assert got == instrument_dir / "obs_x_data"


def test_package_dir_takes_precedence_over_colocated(tmp_path):
    instrument_dir = tmp_path / "instruments" / "x"
    # Both a co-located dir AND an explicit package_dir exist; explicit wins.
    (instrument_dir / "obs_x_data").mkdir(parents=True)
    explicit = tmp_path / "custom_data"
    explicit.mkdir()
    prof = _profile(obs_data_package="obs_x_data", package_dir=str(explicit))
    assert resolve_data_package_dir(prof, instrument_dir) == explicit


def test_colocated_under_instrument_dir(tmp_path):
    instrument_dir = tmp_path / "instruments" / "x"
    colocated = instrument_dir / "obs_x_data"
    colocated.mkdir(parents=True)
    prof = _profile(obs_data_package="obs_x_data")
    assert resolve_data_package_dir(prof, instrument_dir) == colocated


def test_reference_packages_layout(tmp_path, monkeypatch):
    # No package_dir, not co-located, but present in the framework packages/ dir.
    fake_packages = tmp_path / "packages"
    (fake_packages / "obs_x_data").mkdir(parents=True)
    monkeypatch.setattr(config_mod, "_PACKAGES_DIR", fake_packages)
    instrument_dir = tmp_path / "instruments" / "x"
    instrument_dir.mkdir(parents=True)
    prof = _profile(obs_data_package="obs_x_data")
    assert resolve_data_package_dir(prof, instrument_dir) == fake_packages / "obs_x_data"


def test_colocated_wins_over_reference_packages(tmp_path, monkeypatch):
    fake_packages = tmp_path / "packages"
    (fake_packages / "obs_x_data").mkdir(parents=True)
    monkeypatch.setattr(config_mod, "_PACKAGES_DIR", fake_packages)
    instrument_dir = tmp_path / "instruments" / "x"
    colocated = instrument_dir / "obs_x_data"
    colocated.mkdir(parents=True)
    prof = _profile(obs_data_package="obs_x_data")
    # Co-located (precedence 2) beats the reference layout (precedence 3).
    assert resolve_data_package_dir(prof, instrument_dir) == colocated


def test_named_but_nowhere_returns_none(tmp_path, monkeypatch):
    fake_packages = tmp_path / "packages"
    fake_packages.mkdir()
    monkeypatch.setattr(config_mod, "_PACKAGES_DIR", fake_packages)
    instrument_dir = tmp_path / "instruments" / "x"
    instrument_dir.mkdir(parents=True)
    prof = _profile(obs_data_package="obs_x_data")
    assert resolve_data_package_dir(prof, instrument_dir) is None


def test_missing_package_dir_attr_falls_through(tmp_path):
    # A partial stub without a package_dir attribute must not raise (getattr).
    instrument_dir = tmp_path / "instruments" / "x"
    colocated = instrument_dir / "obs_x_data"
    colocated.mkdir(parents=True)
    prof = types.SimpleNamespace(obs_data_package="obs_x_data")
    assert resolve_data_package_dir(prof, instrument_dir) == colocated


def test_returns_path_type(tmp_path):
    prof = _profile(obs_data_package="obs_x_data", package_dir=str(tmp_path))
    assert isinstance(resolve_data_package_dir(prof, tmp_path), Path)
