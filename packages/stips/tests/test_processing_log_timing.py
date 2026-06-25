from stips.core.processing_log import ProcessingLog


def test_timing_fields_roundtrip_and_default_for_old_json():
    plog = ProcessingLog(night="20230815", step="science", timestamp="20260313T185937Z")
    plog.started_at = "2026-03-13T18:55:00Z"
    plog.ended_at = "2026-03-13T18:59:37Z"
    d = plog.to_dict()
    assert d["started_at"] == "2026-03-13T18:55:00Z"
    assert d["ended_at"] == "2026-03-13T18:59:37Z"

    # Old JSON without the new keys still loads, defaulting to None.
    old = {"night": "20230815", "step": "science", "timestamp": "20260313T185937Z"}
    loaded = ProcessingLog.from_dict(old)
    assert loaded.started_at is None
    assert loaded.ended_at is None
