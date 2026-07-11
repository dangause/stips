"""ctio1m-SPECIFIC fetch tests (NOIRLab Astro Data Archive backend).

The generic ``fetch_data`` status contract (backend code -> ok/not_found/failed)
is asserted by the shared auto-discovered suite
(``packages/stips/tests/test_instrument_contracts.py``) using the fixtures in
``contract_data.py``. What stays here is NOIRLab-specific: caldat conversion,
find-night filtering, ``_funpack`` handling, and which ``NOIRLAB_*`` env keys
map onto which ``_fetch_night`` kwargs. Stack-free (fetch.py is stdlib-only at
import time).
"""

import unittest
from pathlib import Path
from unittest import mock

from stips.testing.instrument_contract import (
    FetchConfigStub,
    InstrumentDirInfo,
    load_fetch,
)

# instruments/ctio1m/tests/... -> parents[1] == instruments/ctio1m
_INFO = InstrumentDirInfo(name="ctio1m", path=Path(__file__).resolve().parents[1])
fetch = load_fetch(_INFO)


class TestNightToCaldat(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(fetch._night_to_caldat("20070321"), "2007-03-21")

    def test_invalid(self):
        with self.assertRaises(ValueError):
            fetch._night_to_caldat("2007-03-21")


class TestFindNightFiltering(unittest.TestCase):
    ROWS = [
        {"md5sum": "a", "archive_filename": "/x/a.fits.fz", "obs_type": "object"},
        {"md5sum": "b", "archive_filename": "/x/b.fits.fz", "obs_type": "flat"},
        {"md5sum": "c", "archive_filename": "/x/c.fits.fz", "obs_type": "bias"},
    ]

    def test_drops_meta_and_keeps_rows(self):
        # The API prepends a META/HEADER dict without md5sum; it must be dropped.
        payload_rows = [{"META": {"endpoint": "find"}}] + self.ROWS
        with mock.patch.object(fetch, "_post_json", return_value=payload_rows):
            rows = fetch._find_night("http://api", "y4kcam", "2007-03-21", None, [])
        self.assertEqual({r["md5sum"] for r in rows}, {"a", "b", "c"})

    def test_obstype_restriction(self):
        with mock.patch.object(fetch, "_post_json", return_value=list(self.ROWS)):
            rows = fetch._find_night(
                "http://api", "y4kcam", "2007-03-21", None, ["object", "flat"]
            )
        self.assertEqual({r["obs_type"] for r in rows}, {"object", "flat"})

    def test_proposal_added_to_search(self):
        captured = {}

        def fake_post(url, payload, timeout=120):
            captured["payload"] = payload
            return []

        with mock.patch.object(fetch, "_post_json", side_effect=fake_post):
            fetch._find_night("http://api", "y4kcam", "2007-03-21", "2007A-0002", [])
        self.assertIn(["proposal", "2007A-0002"], captured["payload"]["search"])


class TestFunpack(unittest.TestCase):
    def test_passthrough_non_fz(self):
        p = Path("/tmp/x.fits")
        self.assertEqual(fetch._funpack(p), p)

    def test_skips_when_already_unpacked(self):
        import tempfile

        d = Path(tempfile.mkdtemp())
        fz = d / "y.fits.fz"
        fz.write_bytes(b"")
        (d / "y.fits").write_bytes(b"")  # already funpacked
        with mock.patch.object(fetch.subprocess, "run") as run:
            out = fetch._funpack(fz)
        run.assert_not_called()  # no funpack call needed
        self.assertEqual(out, d / "y.fits")
        self.assertFalse(fz.exists())  # stale .fz removed


class TestFetchEnvForwarding(unittest.TestCase):
    def test_forwards_env_and_overwrite(self):
        cfg = FetchConfigStub(
            {
                "NOIRLAB_API": "http://api/",
                "NOIRLAB_INSTRUMENT": "y4kcam",
                "NOIRLAB_PROPOSAL": "2007A-0002",
                "NOIRLAB_OBSTYPES": "object,flat",
            }
        )
        with mock.patch.object(fetch, "_fetch_night", return_value=0) as m:
            status = fetch.fetch_data("20070321", cfg, overwrite=True)
        self.assertEqual(status, "ok")
        args, kwargs = m.call_args
        self.assertEqual(args[0], "20070321")
        self.assertEqual(args[1], cfg.raw_parent_dir)
        self.assertEqual(kwargs["api"], "http://api")  # trailing slash stripped
        self.assertEqual(kwargs["instrument"], "y4kcam")
        self.assertEqual(kwargs["proposal"], "2007A-0002")
        self.assertEqual(kwargs["obstypes"], ["object", "flat"])
        self.assertTrue(kwargs["overwrite"])

    def test_env_defaults_when_keys_absent(self):
        cfg = FetchConfigStub({})
        with mock.patch.object(fetch, "_fetch_night", return_value=0) as m:
            fetch.fetch_data("20070321", cfg)  # no overwrite -> default False
        _args, kwargs = m.call_args
        self.assertEqual(kwargs["api"], fetch._DEFAULT_API)
        self.assertEqual(kwargs["instrument"], fetch._DEFAULT_INSTRUMENT)
        self.assertIsNone(kwargs["proposal"])
        self.assertEqual(kwargs["obstypes"], [])
        self.assertFalse(kwargs["overwrite"])


if __name__ == "__main__":
    unittest.main()
