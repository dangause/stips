"""Stack-free tests for coadd config-file label mapping."""

from pathlib import Path

from stips.core.config import Config
from stips.core.run import CoaddConfigs, RunConfig, _build_coadd_config_files


def _config(instrument_dir: Path) -> Config:
    return Config(
        repo=instrument_dir,
        stack_dir=instrument_dir,
        instrument_dir=instrument_dir,
        raw_parent_dir=instrument_dir,
    )


def _run_cfg(**coadd) -> RunConfig:
    return RunConfig(
        object_name="E2",
        ra=100.0,
        dec=-45.0,
        bands=["r"],
        coadd_configs=CoaddConfigs(**coadd),
    )


def test_no_coadd_configs_yields_empty(tmp_path):
    files = _build_coadd_config_files(_run_cfg(), _config(tmp_path))
    assert files == []


def test_each_config_maps_to_its_task_label(tmp_path):
    for rel in (
        "coadds/makeDirectWarp.py",
        "coadds/selectTemplateCoaddVisits.py",
        "coadds/selectDeepCoaddVisits.py",
    ):
        p = tmp_path / "configs" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# cfg\n")

    cfg = _config(tmp_path)
    run_cfg = _run_cfg(
        make_direct_warp="coadds/makeDirectWarp.py",
        select_template_coadd_visits="coadds/selectTemplateCoaddVisits.py",
        select_deep_coadd_visits="coadds/selectDeepCoaddVisits.py",
    )
    files = _build_coadd_config_files(run_cfg, cfg)

    labels = {entry.split(":", 1)[0] for entry in files}
    assert labels == {
        "makeDirectWarp",
        "selectTemplateCoaddVisits",
        "selectDeepCoaddVisits",
    }
    for entry in files:
        _, path = entry.split(":", 1)
        assert Path(path).is_file()
