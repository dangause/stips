#!/usr/bin/env python
"""
Sync users from the lick observatory schedule database and the archive's django
database
"""
import argparse
import datetime
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# Read archive config
from lick_archive.config.archive_config import ArchiveConfigFile

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

from lick_archive.external.sched_db import ScheduleDB

# Setup django before importing any django classes
from lick_archive.utils.django_utils import setup_django, setup_django_logging

setup_django()

from django.db import transaction
from lick_archive.apps.archive_auth.hashers import APR_MD5PasswordHasher
from lick_archive.apps.archive_auth.models import ArchiveUser


def get_parser():
    """
    Parse command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Sync users from the lick observatory schedule database to the archive's Django database",
        exit_on_error=True,
    )
    parser.add_argument(
        "--log_path", "-l", type=Path, help="Directory to write log file to."
    )
    parser.add_argument(
        "--log_level",
        "-L",
        type=str,
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        default="DEBUG",
        help="Logging level to use.",
    )
    return parser


def main(args):

    start_time = datetime.datetime.now()
    return_code = 0

    setup_django_logging(args.log_path / "sync_archive_users.log", args.log_level)

    logger.debug("User resync starting...")

    # Get the users from the schedule database
    try:
        sched_db_client = ScheduleDB()
        sched_users = sched_db_client.get_observers()
    except Exception:
        logger.error("Failed to connect to schedule db.", exc_info=True)
        return 1

    # Sanity check the users and convert to a obid->user_dict map
    sched_db_user_map = parse_sched_db_users(sched_users)

    # Make sure we got some users
    if len(sched_db_user_map) == 0:
        logger.error(
            "Found zero valid users in the schedule db. That doesn't seem right!",
            exc_info=True,
        )
        return 1

    # Get the users in the django database
    try:
        django_users = ArchiveUser.objects.all()
        django_user_map = {u.obid: u for u in django_users}
    except Exception:
        logger.error(
            "Failed to get user observer ids from Django's database.", exc_info=True
        )
        return 1

    # Compare the two sets of observer ids
    sched_db_obids = set(sched_db_user_map.keys())
    django_obids = set(django_user_map.keys())

    common_obids = django_obids & sched_db_obids
    new_obids = sched_db_obids - django_obids
    django_only_obids = django_obids - sched_db_obids

    users_to_save = []

    # Update existing observers
    for obid in common_obids:
        django_user = django_user_map[obid]
        sched_db_user = sched_db_user_map[obid]
        try:
            if update_user(django_user, sched_db_user):
                users_to_save.append(django_user)
        except Exception as e:
            logger.error(
                f"Failed to update user obid:{obid}/{django_user.username}: {e.__class__.__name__}:{e}",
                exc_info=True,
            )
            return_code = 1

    # Create new users
    for obid in new_obids:
        sched_db_user = sched_db_user_map[obid]

        # Don't create users that don't have passwords
        if sched_db_user["webpass"] is not None and len(sched_db_user["webpass"]) > 0:
            try:
                django_user = create_user(sched_db_user)
                users_to_save.append(django_user)
            except Exception as e:
                logger.error(
                    f"Failed to create new account for obid:{sched_db_user['obid']}: {e.__class__.__name__}:{e}"
                )
                return_code = 1

    # Disable users that may have been deleted.
    # Staff/superusers are left alone
    for obid in django_only_obids:
        django_user = django_user_map[obid]

        if (django_user.is_active or django_user.has_usable_password()) and (
            not django_user.is_staff and not django_user.is_superuser
        ):

            logger.info(f"Disabling deleted user obid:{obid}/{django_user.username}")
            django_user.is_active = False
            django_user.set_unusable_password()
            users_to_save.append(django_user)

    # Update the users in a single transaction
    if len(users_to_save) > 0:
        try:
            with transaction.atomic():
                for user in users_to_save:
                    user.save()
            logger.info(f"Committed {len(users_to_save)} users.")
        except Exception:
            logger.error(f"Failed to update {len(users_to_save)} users.", exc_info=True)
            return_code = 1

    duration = datetime.datetime.now() - start_time
    logger.info(f"Completed syncing users. Duration: {duration}.")
    return return_code


def parse_sched_db_users(users: list) -> dict:
    """Parse and validate the users returned from the schedule db to verify they have
    the minimum required set of fields.

    Args:
        users: A list of dictionary objects with the user information.

    Returns: A dictionary mapping observerid (aka obid) to a dict of the user's information.
    Any optional items will be set to None in the returned information. Any invalid
    users are removed.
    """

    required_keys = ["obid", "lastname"]
    require_blank_keys = ["firstname", "email"]
    optional_keys = ["firstname", "email", "webpass"]
    obid_map = {}
    dup_obids = set()

    # Don't modify the original list of RowMapping objects
    new_users = [{key: value for key, value in u.items()} for u in users]

    for user in new_users:

        if any(
            [
                (
                    True
                    if user.get(key, None) is None
                    or (isinstance(user[key], str) and len(user[key]) == 0)
                    else False
                )
                for key in required_keys
            ]
        ):
            logger.error(
                f"Required columns {required_keys} were not found for schedule db observers row {user}. Ignoring this row."
            )
            continue

        # Prepend the required algorithm for django to recognize the password hash
        if "webpass" in user and user["webpass"] is not None:
            user["webpass"] = APR_MD5PasswordHasher.algorithm + user["webpass"]

        # Make sure stamp is populated
        if "stamp" in user and user["stamp"] is not None:

            if not isinstance(user["stamp"], datetime.datetime):
                # Try to parse a string into a datetime
                try:
                    user["stamp"] = datetime.datetime.fromisoformat(user["stamp"])
                except Exception:
                    logger.warning(
                        f"Failed to convert timestamp {user['stamp']} to datetime for user '{user['obid']}', setting it to the current time."
                    )
                    user["stamp"] = datetime.datetime.now(tz=datetime.timezone.utc)

            # Use UTC if there is no timezone
            if user["stamp"] is not None and user["stamp"].tzinfo is None:
                user["stamp"] = user["stamp"].replace(tzinfo=datetime.timezone.utc)
        else:
            user["stamp"] = datetime.datetime.now(tz=datetime.timezone.utc)

        # Make sure any missing optional keys are None
        for key in optional_keys:
            if key not in user:
                user[key] = "" if key in require_blank_keys else None
            elif user[key] is None and key in require_blank_keys:
                user[key] = ""

        # Shouldn't happen, but look for duplicate obids just in case.
        # If it does happen, we'll ignore both rows as we don't know which is correct.
        obid = user["obid"]
        if obid in dup_obids:
            # We've already found this duplicate
            logger.error(
                f"More than 2 duplicate obids of '{obid}', all will be ignored."
            )
            continue
        elif obid in obid_map:
            logger.error(f"Duplicate obid: '{obid}'. Ignoring both.")
            dup_obids.add(obid)
            del obid_map[obid]
            continue

        obid_map[obid] = user
    return obid_map


def update_user(django_user: ArchiveUser, sched_db_user: dict) -> bool:
    """Update a django user to match the user information from the schedule db.

    Args:
        django_user:   The django user object to update.
        sched_db_user: The user information from the scheduler db.

    Return: True if the user object has been updated, False if it is unchanged.
    """

    update = False  # Whether to update the user

    obid = django_user.obid

    # Handle password updates
    if sched_db_user["webpass"] is None or len(sched_db_user["webpass"]) == 0:
        # Disabled user
        django_user.is_active = False
        django_user.set_unusable_password()
        logger.info(
            f"Disabling observerid obid:{obid}/{django_user.username} with no password in schedule db."
        )
        update = True
    elif django_user.is_active is False or django_user.has_usable_password() is False:
        # Enabling a previously disabled user
        logger.info(f"Enabling previously disabled obid:{obid}/{django_user.username}.")
        django_user.is_active = True
        django_user.password = sched_db_user["webpass"]
        update = True
    elif sched_db_user["webpass"] != django_user.password:
        # Password update
        django_user.password = sched_db_user["webpass"]
        update = True

    # Regenerate the username to see if it should change
    new_username = generate_username_from_sched_db(sched_db_user)
    if new_username != django_user.username:

        # Check for a duplicate username
        if ArchiveUser.objects.filter(username=new_username).count() > 0:
            raise RuntimeError(
                f"New username '{new_username}' for obid:{obid} is not unique."
            )

        django_user.username = new_username
        update = True

    # Check attributes for changes
    if sched_db_user["firstname"] != django_user.first_name:
        django_user.first_name = sched_db_user["firstname"]
        update = True

    if sched_db_user["lastname"] != django_user.last_name:
        django_user.last_name = sched_db_user["lastname"]
        update = True

    if django_user.email != sched_db_user["email"]:
        django_user.email = sched_db_user["email"]
        update = True

    if django_user.stamp != sched_db_user["stamp"]:
        django_user.stamp = sched_db_user["stamp"]
        update = True

    return update


def create_user(sched_db_user: dict) -> ArchiveUser:
    """Create a django user based on user information from the schedule db.

    Args:
        sched_db_user: The user information from the scheduler db.

    Return: The newly created user object.
    """

    username = generate_username_from_sched_db(sched_db_user)

    if ArchiveUser.objects.filter(username=username).count() > 0:
        raise RuntimeError(
            f"New username '{username}' for new user obid:{sched_db_user['obid']} is not unique."
        )

    new_user = ArchiveUser(
        username=username,
        password=sched_db_user["webpass"],
        email=sched_db_user["email"],
        first_name=sched_db_user["firstname"],
        last_name=sched_db_user["lastname"],
        obid=sched_db_user["obid"],
        stamp=sched_db_user["stamp"],
    )
    logger.info(f"Creating user obid:{new_user.obid}/{new_user.username}")

    return new_user


def generate_username_from_sched_db(sched_db_user: dict) -> str:
    """Generate archive usernames from schedule db user information.

    The user name is their e-mail address or "Firstname<space>LastName".

    Args:
        sched_db_user: The user information from the schedule db.

    Return: The username.
    """
    email = sched_db_user["email"]
    first_name = sched_db_user["firstname"]
    last_name = sched_db_user["lastname"]

    # Assign username
    if len(email) > 0:
        username = email
    elif len(first_name) > 0:
        # Firstname is not always set
        username = f"{first_name} {last_name}"
    else:
        username = last_name

    return username


if __name__ == "__main__":
    # Make sure any crashes get logged instead of being lost to /dev/null
    try:
        args = get_parser().parse_args()
        sys.exit(main(args))
    except Exception:
        logger.error("Crashed", exc_info=True)
