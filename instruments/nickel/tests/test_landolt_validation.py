"""Tests for Landolt validation helpers (no LSST stack required)."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

# --- AB-to-Vega offset constants (from spec) ---

# mVega = mAB + offset; offset = -ΔmAB where ΔmAB from Blanton & Roweis (2007)
AB_TO_VEGA = {"b": +0.09, "v": -0.02, "r": -0.21, "i": -0.45}


def nJy_to_AB(flux_nJy: float) -> float:
    """Convert nanojansky flux to AB magnitude."""
    return -2.5 * math.log10(flux_nJy / 3.631e12)


def ab_to_vega(mag_ab: float, band: str) -> float:
    """Convert AB magnitude to Vega magnitude."""
    return mag_ab + AB_TO_VEGA[band]


class TestABToVega:
    def test_known_flux_v_band(self):
        # Vega is ~3631 Jy = 3.631e12 nJy, should be 0.0 AB
        mag = nJy_to_AB(3.631e12)
        assert abs(mag) < 0.001

    def test_v_band_offset_near_zero(self):
        mag_ab = 12.0
        mag_vega = ab_to_vega(mag_ab, "v")
        assert abs(mag_vega - 11.98) < 0.001  # V offset = -0.02

    def test_i_band_offset(self):
        mag_ab = 15.0
        mag_vega = ab_to_vega(mag_ab, "i")
        assert abs(mag_vega - 14.55) < 0.001  # I offset = -0.45

    def test_b_band_offset_positive(self):
        mag_ab = 14.0
        mag_vega = ab_to_vega(mag_ab, "b")
        assert mag_vega > mag_ab  # B offset = +0.09 (Vega fainter than AB in B)


class TestDerivedMagnitudes:
    def test_b_from_v_and_bv(self):
        V, B_V = 12.5, 0.6
        mag_b = V + B_V
        assert abs(mag_b - 13.1) < 0.001

    def test_r_from_v_and_vr(self):
        V, V_R = 12.5, 0.4
        mag_r = V - V_R
        assert abs(mag_r - 12.1) < 0.001

    def test_i_from_v_and_vi(self):
        V, V_I = 12.5, 0.8
        mag_i = V - V_I
        assert abs(mag_i - 11.7) < 0.001


class TestAngularSeparation:
    def test_same_position_zero_sep(self):
        ra1, dec1 = math.radians(180.0), math.radians(45.0)
        ra2, dec2 = ra1, dec1
        cos_sep = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(
            dec2
        ) * math.cos(ra1 - ra2)
        sep_arcsec = math.degrees(math.acos(min(1.0, cos_sep))) * 3600
        assert sep_arcsec < 0.001

    def test_10arcsec_threshold(self):
        ra1 = math.radians(180.0)
        dec1 = math.radians(45.0)
        # Offset by ~10 arcsec in RA (at dec=45, 1 arcsec RA = 1/cos(45) arcsec on sky)
        offset_deg = 10.0 / 3600.0  # 10 arcsec
        ra2 = ra1 + math.radians(offset_deg / math.cos(dec1))
        dec2 = dec1
        cos_sep = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(
            dec2
        ) * math.cos(ra1 - ra2)
        sep_arcsec = math.degrees(math.acos(min(1.0, cos_sep))) * 3600
        assert abs(sep_arcsec - 10.0) < 0.5  # within 0.5 arcsec tolerance


class TestCatalogCSV:
    def test_catalog_file_exists(self):
        # tests/ is at instruments/nickel/tests/, repo root is 3 levels up
        catalog = (
            Path(__file__).resolve().parents[3]
            / "scripts"
            / "config"
            / "landolt_validation"
            / "landolt_catalog.csv"
        )
        if not catalog.exists():
            pytest.skip("landolt_catalog.csv not yet created")
        with open(catalog) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) >= 10
        for row in rows:
            assert float(row["V"]) > 0
            # Derived B = V + B_V
            assert abs(float(row["B"]) - (float(row["V"]) + float(row["B_V"]))) < 0.01
