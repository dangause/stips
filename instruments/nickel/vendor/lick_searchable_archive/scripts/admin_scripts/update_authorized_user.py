#!/usr/bin/env python
"""Modify what users may access one or more files."""
import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


from lick_archive.authorization.date_utils import get_observing_night
from lick_archive.authorization.user_access import get_public_date
from lick_archive.db.archive_schema import UserDataAccess
from lick_archive.db.db_utils import BatchedDBOperation, create_db_engine
from lick_archive.external import ScheduleDB
from lick_archive.metadata.data_dictionary import MAX_PUBLIC_DATE

# Setup django before importing any django classes
from lick_archive.utils.django_utils import setup_django, setup_django_logging
from lick_archive.utils.script_utils import get_log_path

setup_django()


from django.core.exceptions import ObjectDoesNotExist
from lick_archive.apps.archive_auth.models import ArchiveUser
from lick_archive.utils.resync_utils import get_metadata_from_command_line


def get_parser():
    """
    Parse command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Modify what users may access one or more files."
    )

    parser.add_argument(
        "command",
        type=str,
        choices=["add", "remove", "set"],
        help="The specific command to run.\nadd\tAdd a user to the list of users that can access files.\nremove\tRemove a user from the list of users that can access files.\nset\tSet the list of user that can access files to the given user (removing any other users).",
    )
    parser.add_argument(
        "user",
        type=str,
        help='The user to assign the file to. This can be the string "public" to make the file public, or an integer observer id, an email address, or full name (firstname.lastname).',
    )
    parser.add_argument(
        "--id_file",
        type=Path,
        help="A file containing database ids separated by whitespace. Any of these files assigned to an unknown user are updated.",
    )
    parser.add_argument(
        "--ids",
        type=int,
        nargs="+",
        help="A list of database ids. Any of these files assigned to an unknown user are updated.",
    )
    parser.add_argument(
        "--files",
        type=str,
        help="A list of filenames. Any of these files assigned to an unknown user are updated.",
    )
    parser.add_argument(
        "--date_range",
        type=str,
        help='Date range of files to ingest. Examples: "2010-01-04", "2010-01-01:2011-12-31". Defaults to all. Any files within this date range that are assigned to an unknown user are updated.',
    )
    parser.add_argument(
        "--instruments",
        type=str,
        default="all",
        nargs="*",
        help="Which instrument subdirectories to get metadata from. Defaults to all.",
    )

    parser.add_argument(
        "--db_name",
        default="archive",
        type=str,
        help='Name of the database to update. Defaults to "archive"',
    )
    parser.add_argument(
        "--db_user",
        default="archive",
        type=str,
        help='Name of the database user. Defaults to "archive"',
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=10000,
        help="Number of rows to update in the database at once, defaults to 10,000",
    )
    parser.add_argument(
        "--log_path", "-l", type=str, help="Directory to write log file to."
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

    try:
        # Setup logging and an ingest_failures file.
        start_time = datetime.now(timezone.utc)
        log_path = get_log_path("update_authorized_users")
        setup_django_logging(log_path, args.log_level, stdout_level="INFO")

        obid = parse_and_validate_obid(args)
        if obid is None:
            return 2

        # Do sanity checking with special users
        if args.command == "add":
            if obid == ScheduleDB.PUBLIC_USER or obid == ScheduleDB.UNKNOWN_USER:
                # Unknown/Public user superseed other users, so "add" doesn't make sense
                print(
                    f"Can't 'add' special user id {obid}, use set instead",
                    file=sys.stderr,
                )
                return 3

        # Setup the database connection
        db_engine = create_db_engine(args.db_user, args.db_name)

        # Get the metadata specified on command line
        metadata = get_metadata_from_command_line(db_engine, args)

        if metadata is None:
            return 1

        # Update the files information in batches
        with BatchedDBOperation(db_engine, args.batch_size) as batch:
            for file_metadata in metadata:
                # Generatea the new list of user_data_access rows for the file,
                # which will include existing rows if the command "remove" or "add" was used
                new_user_access = []
                update_needed = False
                found_user = False
                for user_access_info in file_metadata.user_access:
                    if user_access_info.obid == obid:
                        found_user = True
                        if args.command == "remove":
                            # When removing a user, filter them out of the new list
                            update_needed = True
                            continue
                        else:
                            # The user already has access, do not filter them out, however no update
                            # will be needed
                            new_user_access.append(user_access_info)
                    else:
                        if args.command == "set":
                            # When setting access to be a specific user, filter other users out
                            update_needed = True
                            continue
                        elif args.command == "add":
                            if (
                                user_access_info.obid == ScheduleDB.PUBLIC_USER
                                or user_access_info.obid == ScheduleDB.UNKNOWN_USER
                            ):
                                # We're adding a new user, this will supersede any previous "PUBLIC" or "UNKNOWN" settings
                                # so filter these out
                                update_needed = True
                                continue

                        # Keep existing users when adding or removing a user to the list
                        new_user_access.append(user_access_info)

                if len(new_user_access) == 0:
                    # No remaining user access rows, we need to ad done
                    if args.command == "remove":
                        # If we were removing a user, and there's no additiona users, add an UNKNOWN entry
                        new_user_access.append(
                            create_new_user_access_row(
                                ScheduleDB.UNKNOWN_USER, file_metadata
                            )
                        )
                        update_needed = True
                    else:
                        new_user_access.append(
                            create_new_user_access_row(obid, file_metadata)
                        )
                        update_needed = True
                else:
                    if args.command == "add" and found_user is False:
                        new_user_access.append(
                            create_new_user_access_row(obid, file_metadata)
                        )
                        update_needed = True

                if update_needed:
                    logger.info(
                        f"Updating {file_metadata.filename} / {file_metadata.id}"
                    )
                    for ua in new_user_access:
                        logger.info(f"obid: {ua.obid} reason:\n{ua.reason}")

                    batch.update(file_metadata.id, file_metadata, new_user_access)

        logger.info(
            f"Updated {batch.success} of {batch.total} files with {batch.total - batch.success} failures and {batch.success_retries} successful retries."
        )
        logger.info(f"Duration: {datetime.now(timezone.utc) - start_time}")

    except Exception:
        logging.error("Caught exception at end of main.", exc_info=True)
        return 1

    return 0


def create_new_user_access_row(obid, file_metadata):

    now = datetime.now(tz=timezone.utc)
    reason_attribution = f"by update_authorized_user.py on {now.isoformat()}"
    if obid == ScheduleDB.PUBLIC_USER:
        # Force public date to the current date
        public_date = get_observing_night(now)
        new_reason = "File set to public " + reason_attribution
    elif obid == ScheduleDB.UNKNOWN_USER:
        # Force public date to max flag value
        public_date = MAX_PUBLIC_DATE
        new_reason = "File set to UNKNOWN by " + reason_attribution
    else:
        # Get the new public_date based on the user
        public_date, reason, public = get_public_date(
            file_metadata, get_observing_night(file_metadata.obs_date), [obid]
        )
        if public:
            new_reason = "File access set to public "
        else:
            new_reason = f"File access added for user {obid} "
        new_reason += reason_attribution + "\n" + reason

    file_metadata.public_date = public_date
    new_user_access_info = UserDataAccess(
        file_id=file_metadata.id, obid=obid, reason=new_reason
    )
    return new_user_access_info


def parse_and_validate_obid(args: argparse.Namespace):
    """Get the observer id and public date to use for unknown files given our command line arguments."""

    try:
        if args.user is not None and len(args.user) > 0:
            if args.user.lower() == "public":
                logger.info("Using public user")
                return ScheduleDB.PUBLIC_USER
            elif args.user.lower() == "unknown":
                logger.info("Using UNKNOWN user")
                return ScheduleDB.UNKNOWN_USER
            try:
                obid = int(args.user)
                is_int = True
            except ValueError:
                is_int = False

            if is_int:
                # It converted to an integer, is it valid, and does it exist in the DB
                if obid >= 0:
                    try:
                        user = ArchiveUser.objects.get(obid=obid)
                        logger.info(f"Setting to obid {obid}")
                        return obid
                    except ObjectDoesNotExist:
                        # We'll tr the string as a username/email before giving upo
                        pass

            else:
                # Maybe it's a username/e-mail address?
                users = list(ArchiveUser.objects.filter(username=args.user))
                if len(users) == 1:
                    # Found one user, return it's id
                    obid = users[0].obid
                    logger.info(f"Setting to obid {obid} based on email: {args.user}")
                    return obid

                # Maybe it's a first.lastname
                if "." in args.user:
                    split_name = args.user.lower().rsplit(".", maxsplit=1)
                    if len(split_name) == 2:
                        first_name, last_name = split_name
                        users = list(
                            ArchiveUser.objects.filter(
                                first_name__iexact=first_name,
                                last_name__iexact=last_name,
                            )
                        )
                        if len(users) == 1:
                            obid = users[0].obid
                            logger.info(
                                f"Setting to obid {obid} based on first name {first_name} last name: {last_name}"
                            )
                            return obid
    except Exception:
        logger.error("Caught exception parsing user argument.", exc_info=True)

    logger.error(f"Failed to resolve user argument '{args.user}' into an observer id.")
    return None


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
