import importlib.util
import unittest
from pathlib import Path
from unittest import mock


def _load_fetch():
    """Load the Nickel fetch hook module from instruments/nickel/fetch.py by path.

    The fetch implementation moved out of the deleted ``lsst.obs.nickel`` package
    into ``instruments/nickel/fetch.py`` (loaded by the profile's ``fetch_data``
    hook). It is stdlib-only at import time, so this stays stack-free.
    """
    # instruments/nickel/tests/test_fetch.py -> parents[1] == instruments/nickel
    fetch_py = Path(__file__).resolve().parents[1] / "fetch.py"
    spec = importlib.util.spec_from_file_location("_nickel_fetch", fetch_py)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = _load_fetch()


class _Cfg:
    def __init__(self, env):
        self.raw_parent_dir = Path("/tmp/raw")
        self.env = env


class TestFetchData(unittest.TestCase):
    def _run(self, code):
        cfg = _Cfg(
            {
                "LICK_ARCHIVE_DIR": "/x",
                "LICK_ARCHIVE_URL": "u",
                "LICK_ARCHIVE_INSTR": "NICKEL_DIR",
            }
        )
        with mock.patch.object(fetch, "_fetch_night", return_value=code) as m:
            status = fetch.fetch_data("20230519", cfg, overwrite=True)
        return status, m

    def test_ok(self):
        status, m = self._run(0)
        self.assertEqual(status, "ok")
        m.assert_called_once()

    def test_not_found(self):
        status, _ = self._run(2)
        self.assertEqual(status, "not_found")

    def test_failed(self):
        status, _ = self._run(1)
        self.assertEqual(status, "failed")

    def test_forwards_env_and_overwrite(self):
        # fetch_data must unpack the env block + overwrite into _fetch_night.
        status, m = self._run(0)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], "20230519")
        self.assertEqual(args[1], Path("/tmp/raw"))
        self.assertEqual(kwargs["client_path"], "/x")
        self.assertEqual(kwargs["archive_url"], "u")
        self.assertEqual(kwargs["instrument"], "NICKEL_DIR")
        self.assertTrue(kwargs["overwrite"])

    def test_env_defaults_when_keys_absent(self):
        # Missing URL/INSTR fall back to the Nickel defaults; absent client_path is None.
        cfg = _Cfg({})
        with mock.patch.object(fetch, "_fetch_night", return_value=0) as m:
            fetch.fetch_data("20230519", cfg)
        _args, kwargs = m.call_args
        self.assertIsNone(kwargs["client_path"])
        self.assertEqual(kwargs["archive_url"], fetch._DEFAULT_ARCHIVE_URL)
        self.assertEqual(kwargs["instrument"], fetch._DEFAULT_INSTR)
        self.assertFalse(kwargs["overwrite"])


if __name__ == "__main__":
    unittest.main()
