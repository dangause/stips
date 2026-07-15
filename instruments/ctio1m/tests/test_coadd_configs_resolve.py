"""Stack-free: CTIO coadd config overrides exist and resolve instrument-first."""

from pathlib import Path

from stips.core.config import Config
from stips.testing.instrument_contract import InstrumentDirInfo

# instruments/ctio1m/tests/... -> parents[1] == instruments/ctio1m
_INFO = InstrumentDirInfo(name="ctio1m", path=Path(__file__).resolve().parents[1])


def _config() -> Config:
    d = _INFO.path
    return Config(repo=d, stack_dir=d, instrument_dir=d, raw_parent_dir=d)


def test_ctio_coadd_select_configs_resolve_to_instrument_dir():
    cfg = _config()
    for rel in (
        "coadds/makeDirectWarp.py",
        "coadds/selectTemplateCoaddVisits.py",
        "coadds/selectDeepCoaddVisits.py",
    ):
        resolved = cfg.resolve_config(rel)
        assert resolved == _INFO.path / "configs" / rel
        assert Path(resolved).is_file()


def test_ctio_dia_select_configs_resolve_to_instrument_dir():
    cfg = _config()
    for rel in (
        "dia/subtractImages.py",
        "dia/detectAndMeasure.py",
    ):
        resolved = cfg.resolve_config(rel)
        assert resolved == _INFO.path / "configs" / rel
        assert Path(resolved).is_file()
