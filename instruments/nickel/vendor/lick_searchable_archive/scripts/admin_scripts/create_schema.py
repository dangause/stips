#!/usr/bin/env python
"""Create the Lick Archive schema in an existing empty database."""
import argparse
import sys

from lick_archive.db.archive_schema import Base
from lick_archive.db.db_utils import create_db_engine, open_db_session
from sqlalchemy import text


def get_parser():
    """
    Parse bulk_ingest_metadata command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Create the lick archive database tables/indexes in a blank database.",
        exit_on_error=True,
    )
    parser.add_argument(
        "database_name", type=str, help="Name of the database to create the schema in."
    )
    parser.add_argument(
        "database_user",
        type=str,
        help="Name of the database user that has create privileges.",
    )
    parser.add_argument(
        "--read_only_user",
        type=str,
        help="Name of the database user that should have read only privileges for the new database.",
    )
    parser.add_argument(
        "--read_write_user",
        type=str,
        help="Name of the database user that should have read/write privileges for the new database (but no create/delete/drop).",
    )

    return parser


def main(args):

    engine = create_db_engine(user=args.database_user, database=args.database_name)

    Base.metadata.create_all(engine)

    session = open_db_session(engine)

    if args.read_write_user is not None:
        session.execute(
            text("GRANT CONNECT ON DATABASE archive TO " + args.read_write_user)
        )
        session.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE ON file_metadata TO "
                + args.read_write_user
            )
        )
        session.execute(
            text(
                "GRANT SELECT, UPDATE ON file_metadata_id_seq TO "
                + args.read_write_user
            )
        )
        session.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON user_data_access TO "
                + args.read_write_user
            )
        )
    if args.read_only_user is not None:
        session.execute(
            text("GRANT CONNECT ON DATABASE archive TO " + args.read_only_user)
        )
        session.execute(text("GRANT SELECT ON file_metadata TO " + args.read_only_user))
        session.execute(
            text("GRANT SELECT ON user_data_access TO " + args.read_only_user)
        )

    session.commit()


print("Schema created successfully.")

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
