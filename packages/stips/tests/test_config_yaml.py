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
      INSTRUMENT_DIR: /tmp/obs_nickel
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
        self.assertEqual(str(c.obs_nickel), "/tmp/instr")  # deprecated read-only alias
        self.assertEqual(str(c.pipelines_dir), "/tmp/instr/pipelines")

    def test_obs_nickel_key_is_deprecated_alias(self):
        p = _write_yaml(
            "env:\n  REPO: /tmp/repo\n  STACK_DIR: /tmp/stack\n"
            "  OBS_NICKEL: /tmp/obs\n  RAW_PARENT_DIR: /tmp/raw\n"
        )
        with self.assertWarns(DeprecationWarning):
            c = cfg.load(p)
        self.assertEqual(str(c.instrument_dir), "/tmp/obs")

    def test_missing_instrument_dir_errors(self):
        p = _write_yaml(
            "env:\n  REPO: /tmp/repo\n  STACK_DIR: /tmp/stack\n  RAW_PARENT_DIR: /tmp/raw\n"
        )
        with self.assertRaises(ValueError) as ctx:
            cfg.load(p)
        self.assertIn("INSTRUMENT_DIR", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
