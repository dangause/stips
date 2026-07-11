"""Contract fixtures for the CTIO 1.0m (Y4KCam) instrument.

Consumed by the framework's auto-discovered contract suite
(``packages/stips/tests/test_instrument_contracts.py`` via
``stips.testing.instrument_contract``). See ``docs/instrument-contract.md``.

The literals here are the SAME pinned values exercised by
``test_translation.py`` (real Y4KCam keywords from a 2011-06-09 raw frame) and
``test_fetch_ctio1m.py`` -- extracted once so the shared contract can reproduce
them without copy-pasting the assertions per instrument. Do NOT edit the
values; a change means the profile diverged.
"""

# Real Y4KCam science header keys (from a 2011-06-09 raw frame).
SAMPLE_HEADER = {
    "OBSERVAT": "CTIO",
    "TELESCOP": "ct1m",
    "INSTRUME": "Y4KCam",
    "DETECTOR": "ITL SN3671",
    "FILTER": 3,
    "FILTERID": "V",
    # MJD-OBS is authoritative (per the profile); it resolves to 2011-06-10T08:58
    # UT. DATE-OBS/DTCALDAT are set consistent with it.
    "DATE-OBS": "2011-06-10T08:58:18.9",
    "MJD-OBS": 55722.373831,
    "TIMESYS": "UTC",
    "RA": "16:54:17.40",
    "DEC": "-39:51:54.9",
    "EQUINOX": 2000,
    "SECZ": 1.02,
    "EXPTIME": 120.0,
    "DARKTIME": 121.0,
    "OBSTYPE": "OBJECT",
    "IMGTYPE": "OBJECT",
    "OBJECT": "some_target",
    "DTCALDAT": "2011-06-10",
    "FILENAME": "y110610.0042.fits",
}

# Same frame with the filename sequence number bumped by one, for the
# monotonic-in-seq exposure-id assertion.
SAMPLE_HEADER_SEQ_PLUS_ONE = dict(SAMPLE_HEADER, FILENAME="y110610.0043.fits")

# Sequence number (parsed from FILENAME) encoded in the low 4 digits of
# exposure_id.
EXPECTED_SEQ = 42

# Pinned hook outputs for SAMPLE_HEADER (from test_translation.py).
EXPECTED_TRANSLATION = {
    # OBJECT frames map to the LSST "science" observation_type (not "object").
    "observation_type": "science",
    # days_since_2000 (end-of-exposure UTC day 4178) * 10000 + seqnum 42.
    "exposure_id": 4178 * 10000 + 42,
    "visit_id": 4178 * 10000 + 42,
    # UT calendar day (NOT DTCALDAT), from the authoritative MJD-OBS.
    "day_obs": 20110610,
    "observation_id": "20110610_42",
    # 16h54m17.40s -> 253.5725 deg; -39:51:54.9 -> -39.8652 deg
    # (RA deg, Dec deg); compared with 0.01 deg tolerance.
    "tracking_radec": (253.5725, -39.8652),
    "datetime_begin_mjd": 55722.373831,
    # begin + 120 s.
    "datetime_end_mjd": 55722.37521988888,
}

# observation_type coverage across science / bias / flat frames.
OBSERVATION_TYPE_CASES = [
    (SAMPLE_HEADER, "science"),
    (
        dict(
            SAMPLE_HEADER,
            OBSTYPE="bias",
            IMGTYPE="bias",
            OBJECT="bias",
            EXPTIME=0.0,
            FILENAME="y110609.0003.fits",
        ),
        "bias",
    ),
    (
        dict(
            SAMPLE_HEADER,
            OBSTYPE="flat",
            IMGTYPE="flat",
            OBJECT="dome flat",
            FILENAME="y110609.0010.fits",
        ),
        "flat",
    ),
]

# Y4KCam has no 'clear' filter: an unrecognized FILTERID is a hard error.
UNKNOWN_FILTER = {"raw": "ZZZ", "raises": True}

# Fetch contract (NOIRLab Astro Data Archive env schema).
FETCH_NIGHT = "20070321"
FETCH_ENV = {
    "NOIRLAB_API": "http://api/",
    "NOIRLAB_INSTRUMENT": "y4kcam",
    "NOIRLAB_PROPOSAL": "2007A-0002",
    "NOIRLAB_OBSTYPES": "object,flat",
}

# Camera-assembly contract (stack-dependent; see the contract module).
# Y4KCam: single CCD read out through FOUR amplifiers (2x2 quadrants).
EXPECTED_DETECTORS = 1
EXPECTED_AMPS = 4
