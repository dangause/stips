import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: test requires the LSST stack (skipped when unavailable)",
    )


@pytest.fixture(autouse=True)
def _reset_registration_memo():
    """Every test starts with an empty ``ensure_instrument_registered`` memo.

    The guard remembers verified ``(repo, class)`` pairs per process; tests that
    stub ``butler_query.list_instruments`` and assert on the guard's calls must
    not inherit a verification from an earlier test.
    """
    from stips.core.pipeline import reset_registration_memo

    reset_registration_memo()
    yield
    reset_registration_memo()
