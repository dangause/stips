import pandas as pd

from scripts.analysis.build_landolt_catalog_ctio import select_stars


def test_select_stars_assigns_fits_object_within_radius():
    landolt = pd.DataFrame(
        {
            "star_name": ["LSE 259", "FAR AWAY"],
            "ra_deg": [253.451, 100.0],
            "dec_deg": [-56.004, -56.0],
            "V": [12.0, 13.0],
            "B_V": [0.0, 0.5],
            "U_B": [-0.9, 0.0],
            "V_R": [0.0, 0.3],
            "V_I": [0.0, 0.6],
            "V_err": [0.01, 0.01],
            "BV_err": [0.01, 0.01],
            "VR_err": [0.01, 0.01],
            "VI_err": [0.01, 0.01],
        }
    )
    fields = [{"fits_object": "LSE259", "ra_deg": 253.45, "dec_deg": -56.0}]
    out = select_stars(landolt, fields, radius_arcmin=10.0)
    assert list(out["fits_object"]) == ["LSE259"]
    assert abs(out.loc[0, "B"] - 12.0) < 1e-9  # B = V + (B-V)
    assert abs(out.loc[0, "R"] - 12.0) < 1e-9  # R = V - (V-R)
    assert abs(out.loc[0, "I"] - 12.0) < 1e-9  # I = V - (V-I)
