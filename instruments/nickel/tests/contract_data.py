"""Contract fixtures for the reference Nickel instrument.

Consumed by the framework's auto-discovered contract suite
(``packages/stips/tests/test_instrument_contracts.py`` via
``stips.testing.instrument_contract``). See ``docs/instrument-contract.md``.

The literals here are the SAME golden values pinned by
``test_translation_golden.py`` (the science header, captured VERBATIM from the
legacy ``NickelTranslator``) and ``test_fetch.py`` -- extracted once so the
shared contract can reproduce them without copy-pasting the assertions per
instrument. Do NOT edit the values; a change means the profile diverged.
"""

# Science header: Nickel keywords, including RA/DEC for the tracking hook.
SAMPLE_HEADER = {
    # IDs / instrument
    "INSTRUME": "Nickel Direct Camera",
    "OBSNUM": 1032,
    # Times
    "EXPTIME": 120.0,
    "DATE-BEG": "2024-06-25T05:15:49.25",
    "DATE-END": "2024-06-25T05:17:49.25",
    # WCS center (primary; degrees)
    "CRVAL1": 179.1170349121,
    "CRVAL2": 55.1252822876,
    "CRPIX1": 512.0,
    "CRPIX2": 512.0,
    "CUNIT1": "deg",
    "CUNIT2": "deg",
    "CTYPE1": "RA---TAN",
    "CTYPE2": "DEC--TAN",
    "RADECSYS": "FK5",
    "EQUINOX": 2000.0,
    # Misc used by trivial map and sanity checks
    "OBJECT": "NGC_3982",
    "AIRMASS": 1.281367778778,
    "TEMPDET": -109.7,
    "FILTNAM": "B",
    "TELESCOP": "Nickel 1m",
    # Telescope control system coordinates (stuck-DEC tracking path)
    "RA": "11:56:28.09",
    "DEC": "+55:07:31.0",
}

# Same frame with the sequence number (OBSNUM) bumped by one, for the
# monotonic-in-seq exposure-id assertion.
SAMPLE_HEADER_SEQ_PLUS_ONE = dict(SAMPLE_HEADER, OBSNUM=1033)

# Sequence number encoded in the low 4 digits of exposure_id.
EXPECTED_SEQ = 1032

# Pinned translator outputs for SAMPLE_HEADER (from the golden suite).
EXPECTED_TRANSLATION = {
    "observation_type": "science",
    "exposure_id": 89421032,
    "visit_id": 89421032,
    "day_obs": 20240625,
    "observation_id": "20240625_1032",
    # (RA deg, Dec deg); compared with 0.01 deg tolerance.
    "tracking_radec": (179.1170349121, 55.1252822876),
    "datetime_begin_mjd": 60486.21932002315,
    "datetime_end_mjd": 60486.220708912035,
}

# observation_type coverage across science / flat / bias frames.
OBSERVATION_TYPE_CASES = [
    (SAMPLE_HEADER, "science"),
    (dict(SAMPLE_HEADER, OBSTYPE="flat", OBJECT="dome flat"), "flat"),
    (dict(SAMPLE_HEADER, OBJECT="bias"), "bias"),
]

# Nickel has a 'clear' filter, so an unrecognized FILTNAM falls back (no raise).
UNKNOWN_FILTER = {"raw": "ZZZ", "raises": False, "result": "clear"}

# Fetch contract (Lick searchable archive env schema).
FETCH_NIGHT = "20230519"
FETCH_ENV = {
    "LICK_ARCHIVE_DIR": "/x",
    "LICK_ARCHIVE_URL": "u",
    "LICK_ARCHIVE_INSTR": "NICKEL_DIR",
}

# Camera-assembly contract (stack-dependent; see the contract module).
EXPECTED_DETECTORS = 1
EXPECTED_AMPS = 1
