import tempfile
import textwrap
import unittest
from pathlib import Path

from stips.core import config as cfg


def _write_yaml(body: str) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "config.yaml"
    p.write_text(textwrap.dedent(body))
    return p


ENVBLOCK = """
    env:
      REPO: /tmp/repo
      STACK_DIR: /tmp/stack
      INSTRUMENT_DIR: /tmp/instrument_dir
      RAW_PARENT_DIR: /tmp/raw
    object: demo
    """


class TestYamlConfig(unittest.TestCase):
    def test_load_from_yaml_path(self):
        c = cfg.load(_write_yaml(ENVBLOCK))
        self.assertEqual(str(c.repo), "/tmp/repo")
        self.assertEqual(str(c.stack_dir), "/tmp/stack")
        self.assertEqual(str(c.raw_parent_dir), "/tmp/raw")

    def test_load_from_env_dict(self):
        c = cfg.load(
            env={
                "REPO": "/r",
                "STACK_DIR": "/s",
                "INSTRUMENT_DIR": "/o",
                "RAW_PARENT_DIR": "/raw",
            }
        )
        self.assertEqual(str(c.repo), "/r")

    def test_expands_within_env_block(self):
        # ${VAR} expands using ONLY the env block (no os.environ)
        c = cfg.load(
            env={
                "STACK_DIR": "/s",
                "REPO": "/r",
                "INSTRUMENT_DIR": "/o",
                "RAW_PARENT_DIR": "/raw",
                "CP_PIPE_DIR": "${STACK_DIR}/cp_pipe",
            }
        )
        self.assertEqual(str(c.cp_pipe_dir), "/s/cp_pipe")

    def test_missing_required_key_errors(self):
        with self.assertRaises(ValueError) as ctx:
            cfg.load(_write_yaml("env:\n  REPO: /tmp/repo\n"))
        self.assertIn("STACK_DIR", str(ctx.exception))

    def test_no_config_errors(self):
        with self.assertRaises(ValueError):
            cfg.load()

    def test_env_block_exposed_and_expanded(self):
        p = _write_yaml(
            "env:\n"
            "  REPO: /tmp/repo\n"
            "  STACK_DIR: /tmp/stack\n"
            "  INSTRUMENT_DIR: /tmp/obs\n"
            "  RAW_PARENT_DIR: /tmp/raw\n"
            "  LICK_ARCHIVE_DIR: ${STACK_DIR}/lick\n"
        )
        c = cfg.load(p)
        # raw, expanded env block is exposed generically
        self.assertEqual(c.env["LICK_ARCHIVE_DIR"], "/tmp/stack/lick")
        self.assertEqual(c.env["REPO"], "/tmp/repo")
        # framework Config no longer carries Lick-specific typed fields
        self.assertFalse(hasattr(c, "lick_archive_dir"))
        self.assertFalse(hasattr(c, "lick_archive_url"))
        self.assertFalse(hasattr(c, "lick_archive_instr"))

    def test_instrument_dir_is_primary_key(self):
        p = _write_yaml(
            "env:\n  REPO: /tmp/repo\n  STACK_DIR: /tmp/stack\n"
            "  INSTRUMENT_DIR: /tmp/instr\n  RAW_PARENT_DIR: /tmp/raw\n"
        )
        c = cfg.load(p)
        self.assertEqual(str(c.instrument_dir), "/tmp/instr")

    def test_missing_instrument_dir_errors(self):
        p = _write_yaml(
            "env:\n  REPO: /tmp/repo\n  STACK_DIR: /tmp/stack\n  RAW_PARENT_DIR: /tmp/raw\n"
        )
        with self.assertRaises(ValueError) as ctx:
            cfg.load(p)
        self.assertIn("INSTRUMENT_DIR", str(ctx.exception))

    def test_profile_loaded_by_path_from_instrument_dir(self):
        import sys
        from pathlib import Path

        FIX = str(
            Path(__file__).resolve().parents[2]
            / "obs_stips"
            / "tests"
            / "data"
            / "demo_instrument"
        )
        # verify the hop reaches the fixture (adjust parents[N] if needed)
        assert (Path(FIX) / "profile.py").is_file(), FIX
        c = cfg.load(
            env={
                "REPO": "/r",
                "STACK_DIR": "/s",
                "INSTRUMENT_DIR": FIX,
                "RAW_PARENT_DIR": "/raw",
            }
        )
        self.assertIsNotNone(c.profile)
        self.assertEqual(c.profile.name, "DemoFix")
        self.assertIn(FIX, sys.path)  # by-path load also inserts on sys.path

    def test_self_referential_var_raises_labeled_error(self):
        # A self-referential ${A} used to infinite-loop with unbounded string
        # growth; the depth cap now makes it a deterministic, labeled error.
        with self.assertRaises(ValueError) as ctx:
            cfg.load(
                env={
                    "REPO": "/r",
                    "STACK_DIR": "/s",
                    "INSTRUMENT_DIR": "/o",
                    "RAW_PARENT_DIR": "/raw",
                    "A": "${A}/x",
                }
            )
        msg = str(ctx.exception)
        self.assertIn("did not terminate", msg)
        self.assertIn("'A'", msg)

    def test_mutually_recursive_vars_raise_labeled_error(self):
        with self.assertRaises(ValueError) as ctx:
            cfg.load(
                env={
                    "REPO": "/r",
                    "STACK_DIR": "/s",
                    "INSTRUMENT_DIR": "/o",
                    "RAW_PARENT_DIR": "/raw",
                    "A": "${B}",
                    "B": "${A}",
                }
            )
        self.assertIn("did not terminate", str(ctx.exception))

    def test_unterminated_brace_raises_labeled_error(self):
        with self.assertRaises(ValueError) as ctx:
            cfg.load(
                env={
                    "REPO": "/r",
                    "STACK_DIR": "/s",
                    "INSTRUMENT_DIR": "/o",
                    "RAW_PARENT_DIR": "/raw",
                    "CP_PIPE_DIR": "${STACK_DIR/cp_pipe",
                }
            )
        msg = str(ctx.exception)
        self.assertIn("Unterminated", msg)
        self.assertIn("CP_PIPE_DIR", msg)

    def test_unknown_var_raises_labeled_error(self):
        # A typo like ${RAW_PARNT_DIR} used to silently expand to "" (so
        # "${RAW_PARNT_DIR}/data" became "/data"); it now fails loud, naming the
        # unknown var and listing the available keys.
        with self.assertRaises(ValueError) as ctx:
            cfg.load(
                env={
                    "REPO": "/r",
                    "STACK_DIR": "/s",
                    "INSTRUMENT_DIR": "/o",
                    "RAW_PARENT_DIR": "${RAW_PARNT_DIR}/data",
                }
            )
        msg = str(ctx.exception)
        self.assertIn("RAW_PARNT_DIR", msg)  # the unknown name
        self.assertIn("Available env keys", msg)
        self.assertIn("STACK_DIR", msg)  # a real key is listed

    def test_validate_flags_missing_refcat_repo(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            real = Path(d)
            c = cfg.Config(
                repo=real,
                stack_dir=real,
                instrument_dir=real,
                raw_parent_dir=real,
                refcat_repo=real / "does_not_exist",
            )
            errors = c.validate()
            self.assertTrue(
                any("REFCAT_REPO" in e for e in errors),
                f"expected a REFCAT_REPO error, got: {errors}",
            )

    def test_validate_accepts_existing_refcat_repo(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            real = Path(d)
            c = cfg.Config(
                repo=real,
                stack_dir=real,
                instrument_dir=real,
                raw_parent_dir=real,
                refcat_repo=real,
            )
            errors = c.validate()
            self.assertEqual(errors, [])

    def test_validate_skips_unset_refcat_repo(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            real = Path(d)
            c = cfg.Config(
                repo=real,
                stack_dir=real,
                instrument_dir=real,
                raw_parent_dir=real,
                refcat_repo=None,
            )
            errors = c.validate()
            self.assertEqual(errors, [])

    def test_config_and_obs_stips_loaders_agree(self):
        import sys
        from pathlib import Path

        import pytest

        pytest.importorskip("lsst.obs.stips")

        from lsst.obs.stips.profile_loader import load_profile_from_dir

        FIX = str(
            Path(__file__).resolve().parents[2]
            / "obs_stips"
            / "tests"
            / "data"
            / "demo_instrument"
        )
        p1 = load_profile_from_dir(FIX)
        c = cfg.load(
            env={
                "REPO": "/r",
                "STACK_DIR": "/s",
                "INSTRUMENT_DIR": FIX,
                "RAW_PARENT_DIR": "/raw",
            }
        )
        self.assertEqual(p1.name, c.profile.name)
        self.assertIn(FIX, sys.path)  # both loaders insert


if __name__ == "__main__":
    unittest.main()
