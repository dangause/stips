"""Tests for the stips_refcats rename and the nickel_refcats deprecation shim.

Covers audit finding F-010: the reference-catalog package was renamed from the
instrument-branded ``nickel_refcats`` to the neutral ``stips_refcats``, with a
compatibility shim kept under the old name. Also verifies that the
convertReferenceCatalog config files ship as ``stips_refcats`` package data and
resolve via ``importlib.resources`` (no LSST stack required).
"""

from __future__ import annotations

import importlib
import sys

import pytest


def test_stips_refcats_importable():
    import stips_refcats  # noqa: F401

    for sub in ("cli", "convert", "coverage", "gaia", "htm", "pointings", "ps1"):
        importlib.import_module(f"stips_refcats.{sub}")


def test_nickel_refcats_shim_warns_on_import():
    # Drop any cached shim modules so the package __init__ (and its warning)
    # actually re-runs for this assertion.
    for name in list(sys.modules):
        if name == "nickel_refcats" or name.startswith("nickel_refcats."):
            del sys.modules[name]

    with pytest.warns(DeprecationWarning):
        importlib.import_module("nickel_refcats")


def test_nickel_refcats_submodules_redirect():
    import stips_refcats.convert as real_convert
    from nickel_refcats import convert as shim_convert
    from nickel_refcats.convert import convert_catalog

    # The shim submodule IS the renamed implementation (same module object),
    # so monkeypatching ``nickel_refcats.convert.*`` still affects the real code.
    assert shim_convert is real_convert
    assert convert_catalog is real_convert.convert_catalog


def test_convert_config_paths_resolve_as_package_data():
    from stips.core.refcat import _convert_config_path

    for name in ("gaia_dr3_config.py", "ps1_config.py"):
        path = _convert_config_path(name)
        assert path.name == name
        assert path.exists(), f"convert config not shipped as package data: {path}"
