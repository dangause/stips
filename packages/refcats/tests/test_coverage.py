from nickel_refcats.coverage import missing_trixels


def test_missing_trixels_returns_needed_not_present():
    needed = {100, 101, 102}
    present = {101}
    assert missing_trixels(needed, present) == {100, 102}


def test_missing_trixels_empty_when_all_present():
    assert missing_trixels({1, 2}, {1, 2, 3}) == set()


def test_missing_trixels_handles_empty_needed():
    assert missing_trixels(set(), {1}) == set()
