# ruff: noqa: E402
from contextlib import closing

from celery import shared_task
from celery.utils.log import get_task_logger

from .models import IngestNotification

logger = get_task_logger(__name__)

from lick_archive.apps.archive_auth.api import save_oaf_to_db
from lick_archive.authorization.override_access import OverrideAccessFile
from lick_archive.authorization.user_access import set_auth_metadata
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db.archive_schema import FileMetadata
from lick_archive.db.db_utils import (
    BatchedDBOperation,
    check_exists,
    create_db_engine,
    execute_db_statement,
    open_db_session,
)
from lick_archive.metadata.reader import read_file
from sqlalchemy import select
from sqlalchemy.orm import selectinload

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


_db_engine = create_db_engine(
    user=lick_archive_config.database.db_ingest_user,
    database=lick_archive_config.database.archive_db,
)


@shared_task
def ingest_new_files(new_ingests):
    """Celery task used to ingest the metadata for new files in the archive.
    Files that already exist in the metadata DB are ignored

    A new override.access file will cause all of the files in that directory to
    be-evaluated for authorization.

    Args:
        new_ingests: A list of new files to ingest."""
    logger.info(f"Starting ingest of {len(new_ingests)} files.")
    added_files = []
    logger.info(repr(new_ingests))

    # Process any override access files first
    remaining_files, good_files, failed_files = process_oafs(new_ingests)

    with BatchedDBOperation(
        _db_engine, lick_archive_config.ingest.insert_batch_size
    ) as insert_batch:
        with closing(open_db_session(_db_engine)) as session:
            for file in remaining_files:
                try:
                    if not check_exists(
                        _db_engine,
                        FileMetadata.id,
                        FileMetadata.filename == file,
                        session=session,
                    ):
                        logger.info(f"Reading metadata for {file}.")
                        file_metadata = read_file(file)
                        insert_batch.insert(file_metadata)
                        added_files.append(file_metadata)
                    else:
                        logger.info(
                            f"{file} is already in the archive database, skipping."
                        )
                        good_files.append(file)
                except Exception:
                    logger.error(f"Failed ingesting file {file}.", exc_info=True)
                    failed_files.append(file)

    if len(added_files) > 0:
        logger.info(f"Addded {len(added_files)} to archive database.")
    else:
        logger.info("No files to insert.")

    # Gather failures
    failed_files += [failure[0] for failure in insert_batch.failures]
    for file in added_files:
        if file not in failed_files:
            good_files.append(file)

    logger.info(
        f"Updating status on {len(good_files)} successful ingests and {len(failed_files)} failed ingests."
    )
    if len(good_files) > 0:
        results = IngestNotification.objects.filter(filename__in=good_files).update(
            status="COMPLETE"
        )
        logger.info(f"Update found {results} rows")

    if len(failed_files) > 0:
        results = IngestNotification.objects.filter(filename__in=failed_files).update(
            status="FAILED"
        )
        logger.info(f"Update found {results} rows")


def process_oafs(new_ingests):

    remaining_files = []
    parsed_files = []
    good_files = []
    failed_files = []

    # Separate the override files from the rest
    for ingest in new_ingests:
        if OverrideAccessFile.check_filename(ingest["filename"]):
            try:
                oaf = OverrideAccessFile.from_file(ingest["filename"])
                parsed_files.append(oaf)
            except Exception as e:
                logger.error(
                    f"Failed to read override access file {ingest['filename']}: {e}",
                    exc_info=True,
                )
                failed_files.append(ingest["filename"])
                continue
        else:
            remaining_files.append(ingest["filename"])

    # Process them in order
    parsed_files.sort(key=lambda x: x.sequence_id)
    unique_dirs = set()
    for oaf in parsed_files:
        try:
            save_oaf_to_db(oaf)
            good_files.append(str(oaf))
            logger.info(f"Successfully ingested override access file {oaf}")
        except Exception as e:
            logger.error(
                f"Failed to save override access file {oaf} to db: {e}", exc_info=True
            )
            failed_files.append(ingest["filename"])
            continue

        # Save the directory information in a set to re-run authentication
        # A set is used in case multiple files are detected in a directlry, in which case
        # we only have to re-authenticate once
        # Note celery (using the default json serialization) can't send dates so we convert
        # it to a string first
        unique_dirs.add((oaf.observing_night.strftime("%Y-%m/%d"), oaf.instrument_dir))

    # Re-authenticate affected directories
    for dir in unique_dirs:
        logger.info(f"Starting task to re-authenticate {dir[0]}, {dir[1]}")
        rerun_auth.s(*dir).apply_async()

    return remaining_files, good_files, failed_files


@shared_task
def rerun_auth(observing_night, instrument_dir):
    """Re-determine authorization for existing files in the metadata database for a given
    directory."""

    directory = (
        lick_archive_config.ingest.archive_root_dir / observing_night / instrument_dir
    )
    if not directory.exists() or not directory.is_dir():
        logger.error(f"Could not find directory {directory}")

    logger.info(f"Re-running auth on {directory}")

    # Find the files in that directory already in the database
    # The "selectinload" forces it to pull the related user_data_access rows immediately.
    # If we let SQLAlchemy do a lazy load of those rows, it would keep a lock on the rows
    # preventing us from updating them.
    query = (
        select(FileMetadata)
        .options(selectinload(FileMetadata.user_access))
        .where(FileMetadata.filename.startswith(str(directory)))
    )

    try:

        # Find all of the matching files. We have to make sure all of the results are returned
        # to make sure the database releases its lock on them
        with open_db_session(_db_engine) as session:
            results = list(execute_db_statement(session, query).scalars())

        with BatchedDBOperation(
            _db_engine, lick_archive_config.ingest.insert_batch_size
        ) as batch:
            for file_metadata in results:

                try:
                    new_metadata = set_auth_metadata(file_metadata)
                except Exception:
                    msg = f"Failed to regenerate auth metadata for file {file_metadata.filename}"
                    logger.error(msg, exc_info=True)
                    continue

                batch.update(file_metadata.id, new_metadata, new_metadata.user_access)

            logger.info(
                f"Successfully updated {batch.success} files of {batch.total} with {batch.total - batch.success} failures and {batch.success_retries} successful retries."
            )
    except Exception:
        logger.error(f"Error updating authentication for {directory}.", exc_info=True)

    return
