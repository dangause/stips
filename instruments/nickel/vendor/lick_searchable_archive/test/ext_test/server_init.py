import argparse
import sys
from pathlib import Path

from ext_test_common import PRIVATE_FILE, TEST_USER, add_user_access, enable_user
from lick_archive.config.archive_config import ArchiveConfigFile

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

# Setup django before importing any django classes
from lick_archive.utils.django_utils import setup_django, setup_django_logging

setup_django()


def main():
    parser = argparse.ArgumentParser(
        description="Setup external system tests by creating users, ingesting new metadata etc."
    )
    args = parser.parse_args()

    setup_django_logging(Path.cwd() / "server_init.log", "INFO")

    # Step 1: Enable the test_user account
    print("Enabling test_user")
    enable_user(TEST_USER)

    # Step 2: Allow test_user access to the file
    print("Allowing test_user to access proprietary test file")
    full_filename = str(lick_archive_config.ingest.archive_root_dir / PRIVATE_FILE)
    add_user_access(full_filename, TEST_USER)


if __name__ == "__main__":
    sys.exit(main())
