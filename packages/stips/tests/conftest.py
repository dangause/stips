def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: test requires the LSST stack (skipped when unavailable)",
    )
