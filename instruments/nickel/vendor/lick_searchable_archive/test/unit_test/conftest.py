import copy
import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def block_script_util_djangop_setup(monkeypatch):
    """Prevent script_utils from setting up django differently that what the tests want"""

    def mock_func(*args, **kwargs):
        return

    import lick_archive.utils.django_utils

    monkeypatch.setattr(lick_archive.utils.django_utils, "setup_django", mock_func)
    monkeypatch.setattr(
        lick_archive.utils.django_utils, "setup_django_logging", mock_func
    )


@pytest.fixture(scope="session", autouse=True)
def archive_config():
    # Force archive config to load the test version rather than the default config
    from lick_archive.config.archive_config import ArchiveConfigFile

    return ArchiveConfigFile.from_file(
        Path(__file__).parent.parent / "archive_test_config.ini"
    )


@pytest.fixture(scope="session")
def django_setup():
    """Test fixture to do initial django initialization"""
    os.environ["DJANGO_SETTINGS_MODULE"] = "django_test_settings"
    import django

    django.setup()


@pytest.fixture()
def django_log_to_tmp_path(django_setup, tmp_path):
    """Test fixture to make sure logging goes to a temporary path specific to the test."""

    # Get the current settings
    from django.conf import settings

    new_log_settings = copy.deepcopy(settings.LOGGING)

    # Create new settings using tmp_path
    # We assume a "django_log" handler here and "archive_log_formatter"
    # from the test settings
    logfile = str(tmp_path / "django_test_log.txt")
    new_log_settings["handlers"]["django_log"] = {
        "class": "logging.FileHandler",
        "filename": logfile,
        "level": "DEBUG",
        "formatter": "archive_log_formatter",
    }
    # Use override_settings to set/restore the settings
    # This won't update the logging though so we need to call configure_logging
    from django.test import override_settings
    from django.utils.log import configure_logging

    with override_settings(LOGGING=new_log_settings):
        configure_logging(settings.LOGGING_CONFIG, settings.LOGGING)

    # Reset logging to original settings
    configure_logging(settings.LOGGING_CONFIG, settings.LOGGING)


@pytest.fixture()
def django_db(django_setup):
    """Setup an in-memory test django database"""

    from django.test.utils import (
        setup_databases,
        setup_test_environment,
        teardown_databases,
        teardown_test_environment,
    )

    setup_test_environment()
    test_db_info = setup_databases(verbosity=2, interactive=False, debug_sql=True)
    yield
    teardown_databases(verbosity=2, old_config=test_db_info)
    teardown_test_environment()


@pytest.fixture(autouse=True)
def mock_external():
    # Mock external imports that don't work on dev machines
    import sys

    import test_utils

    sys.modules["schedule"] = test_utils.mock_external_schedule
