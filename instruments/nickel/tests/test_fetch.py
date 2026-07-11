"""Nickel-SPECIFIC fetch tests (Lick searchable-archive env schema).

The generic ``fetch_data`` status contract (backend code -> ok/not_found/failed)
is asserted by the shared auto-discovered suite
(``packages/stips/tests/test_instrument_contracts.py``) using the fixtures in
``contract_data.py``. Only the Lick-specific env plumbing stays here: which
``LICK_ARCHIVE_*`` keys map onto which ``_fetch_night`` kwargs, and their
defaults. Stack-free (fetch.py is stdlib-only at import time).
"""

import unittest
from pathlib import Path
from unittest import mock

from stips.testing.instrument_contract import (
    FetchConfigStub,
    InstrumentDirInfo,
    load_fetch,
)

# instruments/nickel/tests/test_fetch.py -> parents[1] == instruments/nickel
_INFO = InstrumentDirInfo(name="nickel", path=Path(__file__).resolve().parents[1])
fetch = load_fetch(_INFO)


class TestFetchEnvForwarding(unittest.TestCase):
    def test_forwards_env_and_overwrite(self):
        # fetch_data must unpack the env block + overwrite into _fetch_night.
        cfg = FetchConfigStub(
            {
                "LICK_ARCHIVE_DIR": "/x",
                "LICK_ARCHIVE_URL": "u",
                "LICK_ARCHIVE_INSTR": "NICKEL_DIR",
            }
        )
        with mock.patch.object(fetch, "_fetch_night", return_value=0) as m:
            status = fetch.fetch_data("20230519", cfg, overwrite=True)
        self.assertEqual(status, "ok")
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], "20230519")
        self.assertEqual(args[1], cfg.raw_parent_dir)
        self.assertEqual(kwargs["client_path"], "/x")
        self.assertEqual(kwargs["archive_url"], "u")
        self.assertEqual(kwargs["instrument"], "NICKEL_DIR")
        self.assertTrue(kwargs["overwrite"])

    def test_env_defaults_when_keys_absent(self):
        # Missing URL/INSTR fall back to the Nickel defaults; absent client_path is None.
        cfg = FetchConfigStub({})
        with mock.patch.object(fetch, "_fetch_night", return_value=0) as m:
            fetch.fetch_data("20230519", cfg)
        _args, kwargs = m.call_args
        self.assertIsNone(kwargs["client_path"])
        self.assertEqual(kwargs["archive_url"], fetch._DEFAULT_ARCHIVE_URL)
        self.assertEqual(kwargs["instrument"], fetch._DEFAULT_INSTR)
        self.assertFalse(kwargs["overwrite"])


if __name__ == "__main__":
    unittest.main()
