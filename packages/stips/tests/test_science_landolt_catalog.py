from pathlib import Path

from stips.core.science import _read_landolt_target_names


def _write(tmp_path: Path, rows: str) -> Path:
    p = tmp_path / "cat.csv"
    p.write_text("star_name,fits_object,ra_deg,dec_deg,V,B_V,U_B,V_R,V_I,B,R,I,V_err,BV_err,VR_err,VI_err\n" + rows)
    return p


def test_explicit_catalog_path(tmp_path):
    p = _write(tmp_path, "LSE 259,LSE259,253.45,-56.0,12.5,0.1,0.0,0.05,0.1,12.6,12.45,12.4,0.01,0.01,0.01,0.01\n")
    assert _read_landolt_target_names(p) == ["LSE259"]


def test_env_var_selects_catalog(tmp_path, monkeypatch):
    p = _write(tmp_path, "SA 92-I,SA92 I,13.0,0.9,11.0,0.5,0.0,0.3,0.6,11.5,10.7,10.4,0.01,0.01,0.01,0.01\n")
    monkeypatch.setenv("STIPS_LANDOLT_CATALOG", str(p))
    assert _read_landolt_target_names() == ["SA92 I"]


def test_duplicate_fits_object_listed_once(tmp_path):
    p = _write(tmp_path, "A,LSE259,1,1,1,0,0,0,0,1,1,1,0,0,0,0\nB,LSE259,1,1,1,0,0,0,0,1,1,1,0,0,0,0\n")
    assert _read_landolt_target_names(p) == ["LSE259"]
