import json

from stips.core.provenance import RunRecord


def test_runrecord_roundtrip():
    rec = RunRecord(
        repo="extended_objects_repo",
        repo_path="/x/extended_objects_repo",
        target="extended_objects",
        instrument="nickel",
        night="20230815",
        step="science",
        final_status="partial",
        configs_tried=[
            {
                "config": "dense_strict.py",
                "is_fallback": False,
                "quanta_succeeded": 14,
                "quanta_failed": 28,
            }
        ],
        total_exposures=0,
        successful_exposures=25,
        output_collection="Nickel/runs/...",
        timestamp_end="20260313T185937Z",
    )
    assert RunRecord.from_dict(rec.to_dict()) == rec

    # key() is stable and identifies a run uniquely
    assert rec.key() == (
        "extended_objects_repo",
        "20230815",
        "science",
        "20260313T185937Z",
    )


def test_record_from_log_file(tmp_path):
    from stips.core.provenance import record_from_log_file

    repo = tmp_path / "lsst" / "data" / "nickel" / "extended_objects_repo"
    plog_dir = repo / "processing_log"
    plog_dir.mkdir(parents=True)
    (plog_dir / "20230815_science.json").write_text(
        json.dumps(
            {
                "night": "20230815",
                "step": "science",
                "timestamp": "20260313T185937Z",
                "configs_tried": [
                    {
                        "config": "dense_strict.py",
                        "is_fallback": False,
                        "quanta_succeeded": 14,
                        "quanta_failed": 28,
                    }
                ],
                "final_status": "partial",
                "output_collection": "Nickel/runs/x",
                "total_exposures": 0,
                "successful_exposures": 25,
            }
        )
    )
    rec = record_from_log_file(plog_dir / "20230815_science.json", repo)
    assert rec.target == "extended_objects"
    assert rec.instrument == "nickel"
    assert rec.night == "20230815"
    assert rec.final_status == "partial"
    assert rec.timestamp_end == "20260313T185937Z"


def test_rerun_recipe_and_duration():
    from stips.core.provenance import build_rerun_recipe, duration_from_stamps

    rec_recipe = build_rerun_recipe(
        instrument="nickel",
        step="science",
        night="20230815",
        config="dense_strict.py",
        sha="abc1234",
    )
    assert "nickel" in rec_recipe and "science" in rec_recipe
    assert (
        "20230815" in rec_recipe
        and "dense_strict.py" in rec_recipe
        and "abc1234" in rec_recipe
    )

    # duration from matching UTC stamps
    assert duration_from_stamps("20260313T185500Z", "20260313T185937Z") == 277
    assert duration_from_stamps(None, "20260313T185937Z") is None
