"""Stack-free: CTIO coadd config overrides exist and resolve instrument-first."""

from pathlib import Path

from conftest import INSTRUMENT_DIR_PATH
from stips.core.config import Config


def _config() -> Config:
    d = INSTRUMENT_DIR_PATH
    return Config(repo=d, stack_dir=d, instrument_dir=d, raw_parent_dir=d)


def test_ctio_coadd_select_configs_resolve_to_instrument_dir():
    cfg = _config()
    for rel in (
        "coadds/makeDirectWarp.py",
        "coadds/selectTemplateCoaddVisits.py",
        "coadds/selectDeepCoaddVisits.py",
    ):
        resolved = cfg.resolve_config(rel)
        assert resolved == INSTRUMENT_DIR_PATH / "configs" / rel
        assert Path(resolved).is_file()
