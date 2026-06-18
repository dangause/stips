import unittest
from pathlib import Path
from unittest import mock

from lsst.obs.nickel import fetch


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


if __name__ == "__main__":
    unittest.main()
