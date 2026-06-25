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
