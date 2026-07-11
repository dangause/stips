"""Framework-level tests for the shared fetch scaffolding (``stips.fetch``).

These pin the single-source pieces the per-instrument ``fetch.py`` modules were
hoisted onto: the ``YYYYMMDD`` night validation message, the backend-code ->
status mapping, and the ``make_fetch_data`` wrapper (env read, kwargs forwarding,
and monkeypatch-transparent backend resolution). The per-instrument suites keep
only their backend-specific env-schema assertions.
"""

import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock

from stips.fetch import make_fetch_data, parse_night, status_for_code


class TestStatusForCode(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(status_for_code(0), "ok")
        self.assertEqual(status_for_code(2), "not_found")
        self.assertEqual(status_for_code(1), "failed")

    def test_unknown_codes_are_failed(self):
        for code in (-1, 3, 99):
            self.assertEqual(status_for_code(code), "failed")


class TestParseNight(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_night("20230519"), dt.date(2023, 5, 19))

    def test_invalid_message_is_single_source(self):
        # The exact message every instrument backend now shares.
        for bad in ("2023-05-19", "abc", "202305"):
            with self.assertRaises(ValueError) as ctx:
                parse_night(bad)
            self.assertEqual(str(ctx.exception), f"Invalid night '{bad}' (use YYYYMMDD)")


# Module-level backend so ``_fetch_night.__globals__`` is this test module's
# namespace and ``mock.patch.object`` on it is visible to the built wrapper.
def _fetch_night(night, raw_root, *, overwrite=False, **kwargs):  # pragma: no cover
    raise AssertionError("real backend should be mocked in these tests")


def _build_kwargs(env: dict) -> dict:
    return {"token": env.get("TOKEN", "default"), "flag": env.get("FLAG") == "1"}


_fetch_data = make_fetch_data(_fetch_night, _build_kwargs)


class _Cfg:
    def __init__(self, env, raw_parent_dir="/tmp/raw"):
        self.raw_parent_dir = Path(raw_parent_dir)
        self.env = dict(env)


class TestMakeFetchData(unittest.TestCase):
    def test_signature_and_status_mapping(self):
        cfg = _Cfg({})
        this = sys.modules[__name__]
        for code, expected in ((0, "ok"), (2, "not_found"), (1, "failed"), (7, "failed")):
            with mock.patch.object(this, "_fetch_night", return_value=code):
                self.assertEqual(_fetch_data("20230519", cfg, overwrite=True), expected)

    def test_forwards_raw_root_env_kwargs_and_overwrite(self):
        cfg = _Cfg({"TOKEN": "abc", "FLAG": "1"}, raw_parent_dir="/data/raw")
        this = sys.modules[__name__]
        with mock.patch.object(this, "_fetch_night", return_value=0) as m:
            _fetch_data("20230519", cfg, overwrite=True)
        args, kwargs = m.call_args
        self.assertEqual(args[0], "20230519")
        self.assertEqual(args[1], Path("/data/raw"))
        self.assertTrue(kwargs["overwrite"])
        self.assertEqual(kwargs["token"], "abc")
        self.assertTrue(kwargs["flag"])

    def test_overwrite_defaults_false(self):
        cfg = _Cfg({})
        this = sys.modules[__name__]
        with mock.patch.object(this, "_fetch_night", return_value=0) as m:
            _fetch_data("20230519", cfg)
        _args, kwargs = m.call_args
        self.assertFalse(kwargs["overwrite"])

    def test_wrapper_is_defined_in_framework(self):
        # The hoisted wrapper's closure lives in stips.fetch (the contract relies
        # on this to prove an instrument uses the shared wrapper).
        self.assertEqual(_fetch_data.__module__, "stips.fetch")


if __name__ == "__main__":
    unittest.main()
