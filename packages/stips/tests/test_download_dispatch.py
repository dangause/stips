import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner
from stips import cli as cli_module
from stips.core.config import Config


def _make_config(profile):
    c = Config(
        repo=Path("/tmp/repo"),
        stack_dir=Path("/tmp/stack"),
        obs_nickel=Path("/tmp/obs"),
        raw_parent_dir=Path("/tmp/raw"),
    )
    c.profile = profile  # plain (non-frozen) dataclass — direct assignment
    return c


def _stub_profile(fetch_data):
    p = mock.Mock()
    p.name = "TestCam"
    p.fetch_data = fetch_data
    return p


class TestDownloadDispatch(unittest.TestCase):
    def test_no_fetch_data_errors_cleanly(self):
        cfg = _make_config(_stub_profile(None))
        with mock.patch.object(cli_module, "_load_config", return_value=cfg):
            res = CliRunner().invoke(cli_module.cli, ["download", "20230519"])
        self.assertNotEqual(res.exit_code, 0)
        self.assertIn("not configured", res.output.lower())

    def test_dispatches_to_fetch_data(self):
        hook = mock.Mock(return_value="ok")
        cfg = _make_config(_stub_profile(hook))
        with mock.patch.object(cli_module, "_load_config", return_value=cfg):
            res = CliRunner().invoke(
                cli_module.cli, ["download", "20230519", "--overwrite"]
            )
        hook.assert_called_once()
        args, kwargs = hook.call_args
        self.assertEqual(args[0], "20230519")
        self.assertTrue(kwargs.get("overwrite"))
        self.assertEqual(res.exit_code, 0)

    def test_not_found_status_exits_2(self):
        hook = mock.Mock(return_value="not_found")
        cfg = _make_config(_stub_profile(hook))
        with mock.patch.object(cli_module, "_load_config", return_value=cfg):
            res = CliRunner().invoke(cli_module.cli, ["download", "20230519"])
        self.assertEqual(res.exit_code, 2)


if __name__ == "__main__":
    unittest.main()
