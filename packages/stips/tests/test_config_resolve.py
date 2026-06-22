"""Stack-free tests for Config's instrument-first-else-framework path resolver."""

from pathlib import Path

from stips.core.config import Config


def _make_config(instrument_dir: Path) -> Config:
    # Minimal Config; only instrument_dir matters for resolution. Other required
    # paths can point anywhere (resolution does not touch them).
    return Config(
        repo=instrument_dir,
        stack_dir=instrument_dir,
        instrument_dir=instrument_dir,
        raw_parent_dir=instrument_dir,
    )


def test_resolve_pipeline_prefers_instrument_dir(tmp_path):
    (tmp_path / "pipelines").mkdir()
    pipe = tmp_path / "pipelines" / "DIA.yaml"
    pipe.write_text("description: x\n")
    cfg = _make_config(tmp_path)
    assert cfg.resolve_pipeline("DIA.yaml") == pipe


def test_resolve_pipeline_falls_back_to_framework(tmp_path):
    cfg = _make_config(tmp_path)  # no pipelines/ in instrument dir
    resolved = cfg.resolve_pipeline("DIA.yaml")
    assert resolved == cfg._defaults_root / "pipelines" / "DIA.yaml"


def test_resolve_config_nested_name_both_branches(tmp_path):
    rel = "dia/subtractImages.py"
    cfg = _make_config(tmp_path)
    # absent -> framework
    assert cfg.resolve_config(rel) == cfg._defaults_root / "configs" / rel
    # present -> instrument dir
    target = tmp_path / "configs" / rel
    target.parent.mkdir(parents=True)
    target.write_text("# cfg\n")
    assert cfg.resolve_config(rel) == target


def test_defaults_root_points_at_obs_stips_instrument_defaults(tmp_path):
    cfg = _make_config(tmp_path)
    assert cfg._defaults_root.name == "instrument_defaults"
    assert cfg._defaults_root.parent.name == "obs_stips"


def test_minimal_fork_resolves_to_existing_framework_files(tmp_path):
    # A fork dir with NO pipelines/ or configs/ must inherit real framework files.
    cfg = _make_config(tmp_path)
    dia = cfg.resolve_pipeline("DIA.yaml")
    sub = cfg.resolve_config("dia/subtractImages.py")
    assert dia == cfg._defaults_root / "pipelines" / "DIA.yaml"
    assert dia.is_file(), f"framework DIA.yaml missing: {dia}"
    assert sub.is_file(), f"framework subtractImages.py missing: {sub}"
