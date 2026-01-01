import getpass
import os
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--archive_host", type=str, default=None, help="Host of the archive server."
    )
    parser.addoption(
        "--ssl_ca_bundle",
        type=str,
        default=None,
        help="Optional ssl ca bundle for self signed certs.",
    )


# def pytest_generate_tests(metafunc):
#    if "archive_backend" in metafunc.fixturenames:
#        metafunc.parametrize("archive_backend", pytest.param(metafunc.config.getoption("archive_backend"),marks=pytest.mark.skipif('metafunc.config.getoption("archive_backend") is None',reason="No backend specified on command line.")))


@pytest.fixture
def archive_host(request):
    backend = request.config.getoption("--archive_host")
    if backend is None:
        pytest.skip()
    return backend


@pytest.fixture
def ssl_ca_bundle(request):
    ssl_ca_bundle = request.config.getoption("--ssl_ca_bundle")
    if ssl_ca_bundle == "False":
        # Disables SSL cert checking
        ssl_ca_bundle = False
    return ssl_ca_bundle


@pytest.fixture
def test_user_password_env():
    """Returns an environment variable name with the archive password to use for testing.
    Will prompt for the password if it has not already been saved.

    We don't return the actual password as a fixture because pytest will print it out.
    """
    if os.environ.get("EXT_TEST_PASSWORD", None) is None:
        os.environ["EXT_TEST_PASSWORD"] = getpass.getpass(
            prompt="Enter test_user password: "
        )
    return "EXT_TEST_PASSWORD"


@pytest.fixture()
def archive_config():
    # Force archive config to load the test version rather than the default config
    from lick_archive.config.archive_config import ArchiveConfigFile

    return ArchiveConfigFile.from_file(
        Path(__file__).parent.parent / "archive_test_config.ini"
    )
