"""Stack-free tests for the CTIO 1.0m Y4KCam profile + hooks.

Only ctio1m-SPECIFIC pins live here (identity strings, filter table, measured
crosstalk matrix). Generic profile validity / exposure-id / translation /
fetch contracts are covered by the shared auto-discovered suite
(``packages/stips/tests/test_instrument_contracts.py``).
"""

from pathlib import Path

from stips.testing.instrument_contract import InstrumentDirInfo, load_profile

# instruments/ctio1m/tests/... -> parents[1] == instruments/ctio1m
_INFO = InstrumentDirInfo(name="ctio1m", path=Path(__file__).resolve().parents[1])


def load_ctio1m_profile():
    return load_profile(_INFO)


def test_identity():
    prof = load_ctio1m_profile()
    assert prof.name == "CTIO1m"
    assert prof.collection_prefix == "CTIO1m"
    assert prof.instrument_class == "lsst.obs.stips.active.Instrument"
    assert prof.filter_key == "FILTERID"


def test_filters_broadband():
    prof = load_ctio1m_profile()
    for phys, band in [("V", "v"), ("B", "b"), ("R", "r"), ("I", "i")]:
        assert prof.filters.get(phys) == band


def test_filter_aliases_map_raw_filterid():
    prof = load_ctio1m_profile()
    assert prof.filter_aliases.get("V") == "V"
    assert prof.filter_aliases.get("B") == "B"


def test_camera_is_yaml_path():
    prof = load_ctio1m_profile()
    assert prof.camera == "camera/y4kcam.yaml"


def test_crosstalk_is_measured_4x4():
    # Y4KCam ships a MEASURED 4x4 crosstalk matrix (E2 field, night 20111113).
    # Structure: 4 amps, zero diagonal, all off-diagonals populated (non-zero).
    prof = load_ctio1m_profile()
    assert prof.crosstalk is not None
    assert prof.crosstalk.n_amp == 4
    assert prof.crosstalk.units == "adu"
    coeffs = prof.crosstalk.coeffs
    for i in range(4):
        assert coeffs[i][i] == 0.0  # diagonal must be zero
        for j in range(4):
            if i != j:
                assert coeffs[i][j] > 0.0  # all off-diagonals measured/populated
    # Largest measured term is the adjacent A03<-A02 coupling (~4.4e-3).
    assert coeffs[3][2] == 4.400683e-03
