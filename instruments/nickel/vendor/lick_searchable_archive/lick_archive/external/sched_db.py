"""Utilities for accessing the Lick Observatory schedule database."""

import logging

logger = logging.getLogger(__name__)

from collections.abc import Mapping
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.schema import MetaData, Table

from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db import db_utils
from lick_archive.metadata.data_dictionary import Telescope
from lick_archive.utils.timed_cache import timed_cache

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


class ScheduleDB:
    """A class for accessing the lick schedule database external to the archive. This is a singleton
    class that caches data it pulls from the schedule database.

    Args:
        cache_timeout: How long to cache data from the schedule database before expiring it. Defaults to 1
        hour.
    """

    _singleton_instance = None
    _initialized = False

    def __new__(cls):
        if cls._singleton_instance is None:
            cls._singleton_instance = super().__new__(cls)
        return cls._singleton_instance

    UNKNOWN_USER = -101
    PUBLIC_USER = -100

    def __init__(self):
        """Initializes a connection to the schedule database and reads the definition
        for the needed tables.
        """

        # Since this is a singleton, only do initialization on the first object creation
        if not ScheduleDB._initialized:
            ScheduleDB._initialized = True

            # Get connection information for the schedule database, and create a SQLAlchemy engine for it
            user_information = lick_archive_config.authorization.read_user_information()
            self.url = f"postgresql://{user_information}@{lick_archive_config.authorization.sched_db_host}/{lick_archive_config.authorization.sched_db_name}"
            self._sched_db_engine = db_utils.create_db_engine(url=self.url)

            # Use SQLAlchemy's reflection to get the database tables without having to
            # declare every column/type here
            self._sched_db_metadata = MetaData()
            self._observers_table = Table(
                "observers",
                self._sched_db_metadata,
                autoload_with=self._sched_db_engine,
            )
            self._runs_table = Table(
                "runs", self._sched_db_metadata, autoload_with=self._sched_db_engine
            )
            self._teledate_table = Table(
                "teledate", self._sched_db_metadata, autoload_with=self._sched_db_engine
            )
            self._telescopes_table = Table(
                "telescopes",
                self._sched_db_metadata,
                autoload_with=self._sched_db_engine,
            )

    def __hash__(self):
        """Define a hash value for this instance. This is required to use caching on some of the methods."""
        return hash(self.url)

    def get_observers(self) -> list[dict]:
        """Return all of the oberservers in the schedule database.

        Return:
            A list of dictionary objects for each observer, with each column being a key/value pair.
        """
        with db_utils.open_db_session(self._sched_db_engine) as session:
            return (
                db_utils.execute_db_statement(session, select(self._observers_table))
                .mappings()
                .all()
            )

    @timed_cache(timedelta(hours=1))
    def get_public_dates(
        self, telescope: Telescope, observing_night: date, observerids: list[int]
    ) -> list[tuple[int, date | None]]:
        """Return the dates that runs for given observvers during a given night become/became public.
        This method is cached and will only query the database once an hour.
        Args:
            telescope:       The telescope that was being observed with
            observing_night: The night of the observing runs.
            obserids:        The observer ids for the run.
        """
        with db_utils.open_db_session(self._sched_db_engine) as session:
            query = select(
                self._observers_table.c.obid, self._runs_table.c.publicdate
            ).where(
                and_(
                    self._observers_table.c.obid.in_(observerids),
                    self._telescopes_table.c.nickname == telescope.value,
                    self._teledate_table.c.date == observing_night,
                    self._runs_table.c.obid == self._observers_table.c.obid,
                    self._teledate_table.c.runid == self._runs_table.c.runid,
                    self._telescopes_table.c.teleid == self._teledate_table.c.teleid,
                )
            )
            return db_utils.execute_db_statement(session, query).all()

    @timed_cache(timedelta(hours=1))
    def get_telescope_info(self, telescope: Telescope) -> Mapping:
        """Return the schedule db's information about a telescope.
        This method is cached and will only call the database once an hour.

        Args:
            telescope: The telescope to return information on

        Return:
            A mapping of the known information from the telescope table.
        """
        with db_utils.open_db_session(self._sched_db_engine) as session:
            query = select(self._telescopes_table.c).where(
                self._telescopes_table.c.nickname == telescope.value
            )
            return db_utils.execute_db_statement(session, query).mappings().first()
