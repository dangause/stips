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


def test_exposure_id_unique_across_consecutive_nights_sharing_ut_day():
    """Regression: ids must key on the LOCAL observing night, not the UT day.

    At CTIO (-70deg longitude) a local night straddles UT midnight, and the
    Y4KCam seqnum resets each local night. Keying exposure_id / observation_id on
    the UT day (datetime_end) therefore COLLIDES: the late frames of night N and
    the early frames of night N+1 share a UT day and overlapping reset seqnums,
    so they map to the same id and the second fails Butler exposure-sync on
    ingest. The y{YYMMDD}.{seq}.fits filename carries the local night, so
    (local-night, seqnum) is the natural globally-unique key.

    Real case: SA98 nights 20100120 & 20100121 both have frames on UT 2010-01-21
    with seqnum 69 -> identical ids (36730069) before this fix.
    """
    late_n20 = dict(
        SAMPLE_HEADER,
        **{
            "MJD-OBS": 55217.010694,  # 2010-01-21T00:15:24 UT, local night 2010-01-20
            "DATE-OBS": "2010-01-21T00:15:24.0",
            "EXPTIME": 6.0,
            "DARKTIME": 6.2,
            "DTCALDAT": "2010-01-20",
            "FILENAME": "y100120.0069.fits",
        },
    )
    early_n21 = dict(
        SAMPLE_HEADER,
        **{
            "MJD-OBS": 55217.973704,  # 2010-01-21T23:22:08 UT, local night 2010-01-21
            "DATE-OBS": "2010-01-21T23:22:08.0",
            "EXPTIME": 6.0,
            "DARKTIME": 6.2,
            "DTCALDAT": "2010-01-21",
            "FILENAME": "y100121.0069.fits",
        },
    )
    # Both land on the same UT calendar day: day_obs is shared (decoupled, OK).
    assert (
        PROFILE.hooks["day_obs"](late_n20)
        == PROFILE.hooks["day_obs"](early_n21)
        == 20100121
    )
    # ...but they are physically distinct exposures and MUST get distinct ids,
    # keyed on the local night parsed from the filename.
    assert PROFILE.hooks["exposure_id"](late_n20) != PROFILE.hooks["exposure_id"](
        early_n21
    )
    assert PROFILE.hooks["observation_id"](late_n20) == "20100120_69"
    assert PROFILE.hooks["observation_id"](early_n21) == "20100121_69"
