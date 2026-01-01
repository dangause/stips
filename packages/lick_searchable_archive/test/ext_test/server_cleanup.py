import argparse
import sys
from pathlib import Path

from ext_test_common import PRIVATE_FILE, TEST_USER, disable_user, remove_user_access
from lick_archive.config.archive_config import ArchiveConfigFile

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


# Setup django before importing any django classes
from lick_archive.utils.django_utils import setup_django, setup_django_logging

setup_django()


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup data left over from external system tests."
    )
    args = parser.parse_args()

    setup_django_logging(Path.cwd() / "server_init.log", "INFO")

    # Step 1: Disable the test_user account
    print("Disabling test_user")
    disable_user(TEST_USER)

    # Step 2: Stop test_user access to the file
    print("Removing test_user access to proprietary test file")
    full_filename = str(lick_archive_config.ingest.archive_root_dir / PRIVATE_FILE)
    remove_user_access(full_filename, TEST_USER)


if __name__ == "__main__":
    sys.exit(main())
