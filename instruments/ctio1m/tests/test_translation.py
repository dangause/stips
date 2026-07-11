"""ctio1m-SPECIFIC translation regressions.

The standard translation contract (observation_type mapping, tracking_radec,
exposure_id 31-bit scheme + exact value, visit_id, day_obs, observation_id,
datetime begin/end, unknown-filter policy) is asserted by the shared
auto-discovered suite (``packages/stips/tests/test_instrument_contracts.py``)
against the pinned literals in ``contract_data.py``. Only regressions that need
Y4KCam-specific alternate headers stay here.
"""

from pathlib import Path

from stips.testing.instrument_contract import (
    InstrumentDirInfo,
    load_contract_data,
    load_profile,
)

# instruments/ctio1m/tests/... -> parents[1] == instruments/ctio1m
_INFO = InstrumentDirInfo(name="ctio1m", path=Path(__file__).resolve().parents[1])
PROFILE = load_profile(_INFO)
SAMPLE_HEADER = load_contract_data(_INFO).SAMPLE_HEADER


def test_day_obs_follows_ut_not_dtcaldat():
    # Regression: a frame taken after UT midnight has DTCALDAT on the local night
    # (2007-03-21) but a UT calendar day one ahead (2007-03-22). day_obs MUST
    # follow UT (20070322) — using DTCALDAT here would disagree with the Butler
    # dimension and break the night_to_dayobs_offset_days=1 query mapping.
    hdr = dict(
        SAMPLE_HEADER,
        **{
            "MJD-OBS": 54181.189528,  # 2007-03-22T04:32:55 UTC
            "DATE-OBS": "2007-03-22T04:32:55.250",
            "DTCALDAT": "2007-03-21",
            "EXPTIME": 120.0,
            "FILENAME": "y070321.0042.fits",
        },
    )
    assert PROFILE.hooks["day_obs"](hdr) == 20070322
