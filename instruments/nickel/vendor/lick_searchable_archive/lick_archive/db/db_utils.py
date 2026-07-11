"""
Helper functions for working with databases via SQL Alchemy
"""

import logging
from collections.abc import Sequence

import psycopg2
from lick_archive.db.archive_schema import FileMetadata, UserDataAccess
from sqlalchemy import (
    Engine,
    Result,
    create_engine,
    delete,
    func,
    insert,
    inspect,
    select,
    update,
)
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import Select
from tenacity import (
    after_log,
    retry,
    retry_if_not_exception_type,
    stop_after_delay,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class BatchedDBOperation:
    def __init__(self, engine: Engine, batch_size: int):
        self.engine = engine
        self.batch_size = batch_size
        self._batch = []
        self.success = 0
        self.success_retries = 0
        self.total = 0
        self.failures = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()
        return False

    def insert(self, new_metadata):
        self.total += 1
        self._batch.append((insert_file_metadata, {"row": new_metadata}, "insert"))
        if len(self._batch) >= self.batch_size:
            self.flush()

    def update(self, id, new_metadata, new_user_access=None):
        self.total += 1
        self._batch.append(
            (
                update_file_metadata,
                {"id": id, "row": new_metadata, "user_access": new_user_access},
                "update",
            )
        )
        if len(self._batch) >= self.batch_size:
            self.flush()

    def flush(self):
        retry = False
        with open_db_session(self.engine) as session:
            try:
                for callable, kwargs, op_type in self._batch:
                    callable(session, **kwargs)
                session.commit()
                self.success += len(self._batch)
            except Exception:
                try:
                    session.rollback()
                except Exception:
                    logger.error(
                        "Failed rolling back batch, continuing to retry.", exc_info=True
                    )
                retry = True

        if retry:
            self._retry_batch()

        self._batch = []

    def _retry_batch(self):
        # Start with a new session
        try:
            for callable, kwargs, op_type in self._batch:
                with open_db_session(self.engine) as session:
                    try:
                        callable(session, **kwargs)
                        session.commit()
                        self.success += 1
                        self.success_retries += 1
                    except Exception as e:
                        self.failures.append(
                            (
                                kwargs["row"].filename,
                                op_type,
                                f"{e.__class__.__name__}: {e}",
                            )
                        )
                        logger.error(
                            "Failed retrying individual operation.", exc_info=True
                        )
                        session.rollback()
        except Exception:
            logger.error("Failed retrying entire batch.", exc_info=True)


@retry(
    reraise=True,
    stop=stop_after_delay(60),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.DEBUG),
)
def create_db_engine(user="archive", database="archive", url=None):
    """Create a database engine object for the Lick archive database.
    Uses exponential backoff to deal with connection issues.
    """
    if url is None:
        connection_url = f"postgresql://{user}@/{database}"
    else:
        connection_url = url

    logger.debug("Connecting to database")
    engine = create_engine(connection_url)
    logger.debug("Connected to database")
    return engine


@retry(
    reraise=True,
    stop=stop_after_delay(60),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.DEBUG),
)
def open_db_session(engine):
    """Open a database session object for the Lick archive database.
    Uses exponential backoff to deal with connection issues.
    """
    logger.debug("Opening session")
    session = Session(engine)
    logger.debug("Session opened")
    return session


@retry(
    retry=retry_if_not_exception_type(psycopg2.IntegrityError)
    & retry_if_not_exception_type(psycopg2.ProgrammingError),
    reraise=True,
    stop=stop_after_delay(60),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.DEBUG),
)
def insert_file_metadata(session: Session, row: FileMetadata):
    """
    Insert one row of metadata using a new database session. This function uses exponential backoff
    retries for deailing with database issues. We do not retry UniqueViolations because such a failure
    will never succeed.
    """
    logger.debug("Inserting row.")
    session.add(row)
    logger.debug("Row inserted")


@retry(
    retry=retry_if_not_exception_type(psycopg2.IntegrityError)
    & retry_if_not_exception_type(psycopg2.ProgrammingError),
    reraise=True,
    stop=stop_after_delay(60),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.DEBUG),
)
def update_file_metadata(
    session: Session, id: int, row: FileMetadata, user_access: Sequence[UserDataAccess]
):
    """
    Updates one row of metadata using a database session. This function uses exponential backoff
    retries for deailing with database issues. We do not retry UniqueViolations because such a failure
    will never succeed.
    """
    logger.debug(f"Updating row {id}.")

    attributes = [
        c.name for c in FileMetadata.__table__.columns if c.name not in ("id")
    ]
    values = {attr: getattr(row, attr) for attr in attributes}
    try:
        stmt = update(FileMetadata).where(FileMetadata.id == id).values(values)
        logger.debug(f"Running SQL: {stmt.compile()}")
        session.execute(stmt)
    except Exception:
        logger.error(f"Failed to update id {id}", exc_info=True)
        valuestr = "\n".join(
            [
                f"{key}: {value}" if key != "header" else "header: ..."
                for key, value in values.items()
            ]
        )
        logger.error(f"Values for failed update are: {valuestr}")
        raise

    logger.debug("row updated.")

    if user_access is not None:
        logger.debug("Deleting old user access information...")
        stmt = delete(UserDataAccess).where(UserDataAccess.file_id == id)
        logger.debug(f"Running SQL: {stmt.compile()}")
        session.execute(stmt)
        logger.debug(
            f"Deleted old user access information, now adding  {len(user_access)} entries..."
        )

        for user_data_access in user_access:
            try:
                stmt = insert(UserDataAccess).values(
                    file_id=id,
                    obid=user_data_access.obid,
                    reason=user_data_access.reason,
                )
                logger.debug(f"Running SQL: {stmt.compile()}")
                session.execute(stmt)
            except Exception:
                logger.error(
                    f"Failed to insert new user data access for id {id}", exc_info=True
                )
                logger.error(
                    f"Values for failed isert are: file_id: '{id}' obid: '{user_data_access.obid}' reason: '{user_data_access.reason}'"
                )
                raise
        logger.debug("User access information updated.")


@retry(
    retry=retry_if_not_exception_type(psycopg2.IntegrityError)
    & retry_if_not_exception_type(psycopg2.ProgrammingError),
    reraise=True,
    stop=stop_after_delay(60),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.DEBUG),
)
def check_exists(engine, column, expression, session=None):
    """
    Check if a file has already been inserted.
    """
    if session is None:
        session = open_db_session(engine)

    # We do a select count()... and see if the result is one. There's a unique constraint
    # on filename so it should always be 1 or 0
    stmt = select(func.count(column)).where(expression)

    logger.debug(f"Running Exists SQL: {stmt.compile()}")
    result = session.execute(stmt).scalar() == 1
    logger.debug(f"Exists SQL complete. Result {result}")
    return result


@retry(
    retry=retry_if_not_exception_type(psycopg2.IntegrityError)
    & retry_if_not_exception_type(psycopg2.ProgrammingError),
    reraise=True,
    stop=stop_after_delay(60),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.DEBUG),
)
def execute_db_statement(session, stmt):

    logger.debug(f"Running SQL: {stmt.compile()}")

    in_outside_transaction = session.in_transaction()

    if in_outside_transaction:
        logger.debug("Running in outside transaction")

    try:
        result = session.execute(stmt)
    except Exception:
        # Python DB stuff always starts a transaction. But if something fails it can't be retried
        # without rolling back the entire transaction.
        # If we're in an outside transaction, this must be done by the caller, as they know what
        # other statements need to be retried. Otherwise we can do the rollback here to allow the
        # tenacity retries to work (or at least consistently give the same failure).
        if not in_outside_transaction:
            session.rollback()
        raise

    if not in_outside_transaction:
        # Commit the automatically started transaction. The session is left in the same state it
        # was as when this function was called
        session.commit()

    logger.debug("SQL complete.")
    return result


def convert_object_to_dict(mapped_object):
    """Convert an SQLAlchemy ORM object instance to a dict.
    Args:
        mapped_object (Any): The SQLAlchemy mapped object instance.
    Return:
        dict: A dictionary of the mapped attributes and their values.
    """
    i = inspect(mapped_object)
    return {key: getattr(mapped_object, key) for key in i.attrs.keys()}


@retry(
    retry=retry_if_not_exception_type(psycopg2.IntegrityError)
    & retry_if_not_exception_type(psycopg2.ProgrammingError),
    reraise=True,
    stop=stop_after_delay(60),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.DEBUG),
)
def get_single_result(results: Result) -> FileMetadata:
    """Wraps fetching a result from a query in a retryable function"""

    result = results.fetchone()
    return None if result is None else result[0]


def find_file_metadata(session: Session, query: Select) -> FileMetadata | None:
    """Return the metadata for files matching a query.

    Args:
        session: The SQLAlchemy session to use for querying the database.
        query:   An SQL Alchemy query to query with.

    Return: The metadata object in the database, or None if it could not be found.
    """

    with execute_db_statement(session, query) as results:
        return get_single_result(results)
