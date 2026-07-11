"""
Service that watches for new ingests and notifies the Lick archive about them.
"""

import argparse
import configparser
import datetime
import logging
import os
import sys
import threading
from collections import OrderedDict, namedtuple
from functools import partial
from pathlib import Path
from time import sleep
from urllib.parse import urlparse

import watchdog
import watchdog.events
import watchdog.observers.api
import watchdog.observers.polling
from lick_archive.client.lick_archive_ingest_client import LickArchiveIngestClient
from lick_archive.utils.script_utils import setup_service_logging
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

# Keys from the config file
_CONFIG_KEY = "ingest_watchdog"
_CONFIG_DATA_ROOT = "data_root"
_CONFIG_METHOD = "method"
_CONFIG_POLLING_INTERVAL = "polling_interval"
_CONFIG_POLLING_SEARCHES = "polling_searches"
_CONFIG_WRITE_DELAY = "polling_write_delay"
_CONFIG_INOTIFY_AGE = "inotify_age"
_CONFIG_INGEST_URL = "ingest_url"
_CONFIG_INGEST_KEY = "ingest_key"
_CONFIG_INST_DIRS = "instrument_dirs"
_CONFIG_RETRY_MAX_DELAY = "ingest_retry_max_delay"
_CONFIG_RETRY_MAX_TIME = "ingest_retry_max_time"
_CONFIG_REQUEST_TIMEOUT = "ingest_request_timeout"
_CONFIG_STARTUP_RESYNC_AGE = "startup_resync_age"


def validate_int(parsed_config, section, key):
    """
    Validate that a given value in the config is an integer.

    Args:
    parsed_config (configparser.ConfigParser): Config parser with values to validate
    section (str): Name of the section containing the value
    key (str): Name of the value to validate.

    Returns (int): The validated value.

    Raises:
    ValueError: Raised if the value is not an integer.
    """
    try:
        value = parsed_config[section].getint(key)
        if value is None:
            raise ValueError(f"Config missing '{key}' setting under '[{section}]'.")
        return value
    except ValueError as e:
        raise ValueError(f"Config setting '{key}'  under '[{section}]': {e}.")


def validate_url(parsed_config, section, key):
    """
    Validate that a given value in a URL. Uses urllib.parse.urlparse to validate.

    Args:
    parsed_config (configparser.ConfigParser): Config parser with values to validate
    section (str): Name of the section containing the value
    key (str): Name of the value to validate.

    Returns (int): The validated URL.

    Raises:
    ValueError: Raised if the value is not a URL.
    """
    try:
        value = parsed_config[section].get(key)
        if value is None:
            raise ValueError(f"Config missing '{key}' setting under '[{section}]'.")

        result = urlparse(value)
        if (
            result.scheme not in ["http", "https"]
            or result.netloc == ""
            or result.path == ""
        ):
            raise ValueError(
                f"Config setting '{key}' under '[{section}] is not a valid http or https URL."
            )

        return value
    except Exception as e:
        raise ValueError(f"Config setting '{key}'  under '[{section}]': {e}.")


def validate_float(parsed_config, section, key):
    """
    Validate that a given value in the config is a float.

    Args:
    parsed_config (configparser.ConfigParser): Config parser with values to validate
    section (str): Name of the section containing the value
    key (str): Name of the value to validate.

    Returns (float): The validated value.

    Raises:
    ValueError: Raised if the value is not a floating point number.
    """

    try:
        value = parsed_config[section].getfloat(key)
        if value is None:
            raise ValueError(f"Config missing '{key}' setting under '[{section}]'.")
        return value
    except ValueError as e:
        raise ValueError(f"Config setting '{key}'  under '[{section}]': {e}.")


def validate_list(parsed_config, section, key):
    """
    Validate that a given value in the config is a list. This includes a single item
    which is treated as a one element list.

    Args:
    parsed_config (configparser.ConfigParser): Config parser with values to validate
    section (str): Name of the section containing the value
    key (str): Name of the value to validate.

    Returns (list): The validated value.

    Raises:
    ValueError: Raised if the value is not a list.
    """
    value = parsed_config[section].get(key)
    if value is None:
        raise ValueError(f"Config missing '{key}' setting under '[{section}]'.")

    l = [item.strip() for item in value.split(",")]
    for item in l:
        if len(item) == 0:
            raise ValueError(
                f"Config setting '{key}'  under '[{section}]' has empty values."
            )

    return l


def validate_not_empty(parsed_config, section, key):
    """
    Validate that a given value in the config is not empty.

    Args:
    parsed_config (configparser.ConfigParser): Config parser with values to validate
    section (str): Name of the section containing the value
    key (str): Name of the value to validate.

    Returns (str): The validated value.

    Raises:
    ValueError: Raised if the value does not exist or is blank.
    """

    value = parsed_config[section].get(key)
    if value is None:
        raise ValueError(f"Config missing '{key}' setting under '[{section}]'.")
    if len(value) == 0:
        raise ValueError(f"Config setting '{key}'  under '[{section}]' is empty.")
    return value


def validate_path(parsed_config, section, key, exists=False, is_dir=False):
    """
    Validate that a given value in the config is an path.

    Args:
    parsed_config (configparser.ConfigParser): Config parser with values to validate
    section (str): Name of the section containing the value
    key (str): Name of the value to validate.
    exists (bool): If set to true, the path will be validated to exist in the file system.
                   Defaults to false.
    is_dir (bool): If set to true, the path will be validated to be a directory that exists in the file system.
                   Defaults to false.

    Returns (pathlib.Path): The validated value.

    Raises:
    ValueError: Raised if the value is not a path or doesn't pass the requested exists/is_dir tests.
    """

    value = parsed_config[section].get(key)
    if value is None:
        raise ValueError(f"Config missing '{key}' setting under '[{section}]'.")
    if len(value) == 0:
        raise ValueError(f"Config setting '{key}'  under '[{section}]' is empty.")

    path = Path(value)

    if exists:
        if not path.exists():
            raise ValueError(
                f"Config setting '{key}'  under '[{section}]' must be a file that exists"
            )

    if is_dir:
        if not path.is_dir():
            raise ValueError(
                f"Config setting '{key}'  under '[{section}]' must be a directory that exists"
            )

    return path


def parse_and_validate_polling_config(parsed_config, section):
    """
    Validate the polling related configuration options. These include 'polling_interval',
    'polling_searches', and 'polling_write_delay'.

    Args:
    parsed_config (configparser.ConfigParser): Config parser with values to validate
    section (str): Name of the section containing the polling values to validate.

    Returns (namedtuple): A named tuple with validated values for "interval", "searches",
    and "write_delay".

    Raises:
    ValueError: Raised if one of the values wasn't set or wasn't the appropriate type.
    """

    polling_fields = ["interval", "searches", "write_delay"]

    PollingConfig = namedtuple("PollingConfig", polling_fields)

    polling_interval = validate_int(parsed_config, section, _CONFIG_POLLING_INTERVAL)

    unparsed_searches = validate_list(parsed_config, section, _CONFIG_POLLING_SEARCHES)

    # A "search" is the name for one of the date ranges to periodically search.
    # They are comprised of an interval in seconds, and an age in days
    # indicating how far back to search. See the ingest watchdog documentation for more
    # information.

    polling_searches = []
    Search = namedtuple("Search", ["interval", "age"])

    for search in unparsed_searches:
        search_contents = search.split(":")
        if len(search_contents) != 2:
            raise ValueError(
                f"Invalid search value {search} for '{_CONFIG_POLLING_SEARCHES}' setting under '[{_CONFIG_KEY}]'."
            )

        try:
            polling_searches.append(
                Search(int(search_contents[0]), int(search_contents[1]))
            )
        except ValueError:
            raise ValueError(
                f"Invalid search value '{search}' for '{_CONFIG_POLLING_SEARCHES}' setting under '[{_CONFIG_KEY}]'."
            )

    polling_write_delay = validate_int(parsed_config, section, _CONFIG_WRITE_DELAY)

    return PollingConfig(polling_interval, polling_searches, polling_write_delay)


def parse_and_validate_ingest_config(parsed_config, section):
    """
    Validate the ingest notification related configuration options. These include
    'ingest_url', 'ingest_retry_max_delay', 'ingest_retry_max_time',  and
    'ingest_request_timeout'.

    Args:
    parsed_config (configparser.ConfigParser): Config parser with values to validate
    section (str): Name of the section containing the ingest notification values to validate.

    Returns (namedtuple): A named tuple with validated values for "url", "retry_max_delay",
                          "retry_max_time", "request_timeout"

    Raises:
    ValueError: Raised if one of the values wasn't set or wasn't the appropriate type.
    """

    ingest_fields = [
        "url",
        "retry_max_delay",
        "retry_max_time",
        "request_timeout",
        "key",
    ]

    IngestConfig = namedtuple("IngestConfig", ingest_fields)

    url = validate_url(parsed_config, _CONFIG_KEY, _CONFIG_INGEST_URL)
    retry_max_delay = validate_int(parsed_config, _CONFIG_KEY, _CONFIG_RETRY_MAX_DELAY)
    retry_max_time = validate_int(parsed_config, _CONFIG_KEY, _CONFIG_RETRY_MAX_TIME)
    request_timeout = validate_float(
        parsed_config, _CONFIG_KEY, _CONFIG_REQUEST_TIMEOUT
    )

    # The key is optional, first check to see if it's not empty
    try:
        key = validate_not_empty(parsed_config, _CONFIG_KEY, _CONFIG_INGEST_KEY)
    except ValueError:
        key = None

    # If it succeeeds, verify it's a path that exists
    if key is not None:
        key = validate_path(parsed_config, _CONFIG_KEY, _CONFIG_INGEST_KEY, exists=True)

    return IngestConfig(url, retry_max_delay, retry_max_time, request_timeout, key)


def parse_and_validate_config(parsed_config):
    """
    Parse and validate the ingest_watchdog's configuration file. See the
    ingest_watchdog documentation for more information on the configuration values.

    Args:
    parsed_config (configparser.ConfigParser): Config parser for the ingest_watchdog.conf file.

    Returns (namedtuple): A named tuple with the ingest_watchdog configuration values.

    Raises:
    ValueError: Raised if one of the values wasn't set or wasn't the appropriate type.
    """

    config_fields = (
        "data_root",
        "startup_resync_age",
        "method",
        "polling",
        "inotify_age",
        "instrument_dirs",
        "ingest",
    )

    if _CONFIG_KEY not in parsed_config:
        raise ValueError(f"Config missing {_CONFIG_KEY} section.")

    data_root = validate_path(
        parsed_config, _CONFIG_KEY, _CONFIG_DATA_ROOT, is_dir=True
    )

    method = validate_not_empty(parsed_config, _CONFIG_KEY, _CONFIG_METHOD)
    if method == "polling":
        polling_config = parse_and_validate_polling_config(parsed_config, _CONFIG_KEY)
        inotify_age = None
    elif method == "inotify":
        polling_config = None
        inotify_age = validate_int(parsed_config, _CONFIG_KEY, _CONFIG_INOTIFY_AGE)
    else:
        raise ValueError(
            f"Unknown watchdog method '{method}' for '{_CONFIG_METHOD}' setting under '[{_CONFIG_KEY}]'."
        )

    instrument_dirs = validate_list(parsed_config, _CONFIG_KEY, _CONFIG_INST_DIRS)

    ingest_config = parse_and_validate_ingest_config(parsed_config, _CONFIG_KEY)

    IngestWatchdogConfig = namedtuple("IngestWatchdogConfig", config_fields)

    startup_age = validate_int(parsed_config, _CONFIG_KEY, _CONFIG_STARTUP_RESYNC_AGE)

    return IngestWatchdogConfig(
        data_root,
        startup_age,
        method,
        polling_config,
        inotify_age,
        instrument_dirs,
        ingest_config,
    )


def sorted_logging_scandir(path):
    """
    A scandir wrapper to log debug information about when the watchdog scans a directory and to sort the results from scandir.

    Args:
        path (str): The path to scan.

    Return:
        list[os.DirEntry]: A sorted list of the entries in the scanned directory.
    """
    logger.debug(f"Scanning {path}")
    return sorted(os.scandir(path), key=lambda x: x.name)


def logging_stat(path):
    """
    A stat wrapper to log debug information about when the watchdog scans a directory.

    Args:
    path (str): The path to scan.
    """

    logger.debug(f"Stating {path}")
    result = os.stat(path)
    return result


class PollingWithSimulatedCloseEmitter(watchdog.observers.polling.PollingEmitter):
    """
    Extends the watchdog package's PollingEmitter class with the ability to send a "Close" event
    a configurable delay after a file has been created (or modified). This allows time for a file to be fully
    written to disk, and allows clients to treat the events from polling like they would from an
    inotify observer.

    Args:
    event_queue:    Event queue that receives events.
    watch:          Watch object representing the path being watched.
    timeout:        Polling interval between scans of the watched directory.
    writing_delay:  How long to wait (in seconds) after a file is created to send a close event.
    stat:           Function used to stat files.
    listdir:        Function used to scan directories.
    event_filter:   Optional collection of :class:`watchdog.events.FileSystemEvent` to watch
    """

    def __init__(
        self,
        event_queue,
        watch,
        timeout,
        writing_delay,
        stat=os.stat,
        listdir=os.scandir,
        event_filter=None,
    ):
        super().__init__(
            event_queue,
            watch,
            timeout=timeout,
            stat=stat,
            listdir=listdir,
            event_filter=event_filter,
        )
        self._writing_delay = datetime.timedelta(seconds=writing_delay)
        self._file_modify_map = OrderedDict()
        self._file_modify_lock = threading.Lock()

    def queue_events(self, timeout):
        """
        Scan the watched directory and issue events.

        This overridden version calls the superclass method to do the scan, and then
        sends a close event for each file in its own internal map older than the writing delay.

        Args:
        timeout (int): From the watchdog framework, this is the time the superclass method sleeps before
                       scanning the directory.
        """
        super().queue_events(timeout)

        try:
            # Make sure nothing has stopped this thread while the scan was happening
            with self._lock:
                if not self.should_keep_running():
                    return

            # Go through the _file_modify_map and find any files older than the writing delay
            # Multiple threads can call queue_event, which also uses the file_modify_map.
            # So we protect the map with _file_modify_lock
            current_time = datetime.datetime.now(tz=datetime.timezone.utc)
            files_to_queue = []
            with self._file_modify_lock:

                # Get a list of files in the map. We don't directly iterate over keys
                # because we'll be removing files from the map as we go which would invalidate
                # iteration
                file_list = list(self._file_modify_map.keys())
                for file in file_list:
                    if current_time - self._file_modify_map[file] > self._writing_delay:
                        files_to_queue.append(file)
                        del self._file_modify_map[file]

            # Now queue the close events for files older than the writing delay
            for file in files_to_queue:
                self.queue_event(watchdog.events.FileClosedEvent(file))
        except Exception as e:
            # Letting exceptions escape this method will kill this thread, preventing future
            # scans of the directory
            logger.error(f"Exception in queue_events {e}", exc_info=True)

    def queue_event(self, event):
        """
        Queue a file system event for this emitter. This method keeps track of new files
        (or new modifications to files) that will need a close event sent for them before
        calling the superclass method to queue the event.

        Args:
        event: The file system event to queue.
        """
        current_time = datetime.datetime.now(tz=datetime.timezone.utc)

        if not event.is_directory:
            # Update the _file_modify_map with new and modified files, and delete any files
            # that were deleted before _writing_delay seconds passed.
            with self._file_modify_lock:
                if event.event_type in (
                    watchdog.events.EVENT_TYPE_CREATED,
                    watchdog.events.EVENT_TYPE_MODIFIED,
                ):
                    self._file_modify_map[event.src_path] = current_time
                elif event.src_path in self._file_modify_map:
                    if event.event_type in (
                        watchdog.events.EVENT_TYPE_DELETED,
                        watchdog.events.EVENT_TYPE_MOVED,
                    ):
                        # File was deleted
                        del self._file_modify_map[event.src_path]

        super().queue_event(event)


class PollingWithSimulatedCloseObserver(watchdog.observers.api.BaseObserver):
    """Extends the watchdog packages Observer interface with a polling observer that emits close events a
    configurable delay after finding a new file.

    Args:
    timeout:        Polling interval between scans of the watched directory.
    writing_delay:  How long to wait (in seconds) after a file is created to send a close event.
    stat:           Function used to stat files.
    listdir:        Function used to scan directories.
    """

    def __init__(self, timeout, writing_delay, stat, listdir):
        emitter_cls = partial(
            PollingWithSimulatedCloseEmitter,
            writing_delay=writing_delay,
            timeout=timeout,
            stat=stat,
            listdir=listdir,
        )
        super().__init__(emitter_cls, timeout=timeout)

    def start(self):
        logger.debug("Starting")
        super().start()


class IngestWatcher(watchdog.events.FileSystemEventHandler):
    """
    Watch the events emitted from the watchdog package about
    the archive file system, and act on those events.

    The lick archive directory structure is
    "/root_path/year_month/day/instrument/data_file".

    If new data files are found, the lick archive ingest
    service is notified.

    Since the physical archive file system may not
    have the directory for a particular day and instrument yet,
    this class also watches directories along the directory hierarchy
    until the instrument directories are created.

    Args:
    config (namedtuple):   The ingest_watchdog configuration values.
    path (logging.Logger): The logger to use.
    client (lick_archive.LickArchiveIngestClient): The client to use when communicating with the
                                                   archive metadata ingest software.

    """

    class PathInfo:
        """
        Internal class holding information on a path being watched.

        Args:
        path (pathlib.Path):     The path being watched.
        is_ingest_dir(bool):     Whether or not this path contains files to ingest.
        observer (BaseObserver): The watchdog API observer watching this path.
        watch (ObservedWatch):   The watchdog API watch object for this path.
        """

        def __init__(self, path, is_ingest_dir, observer=None, watch=None):
            self.path = path
            self.observer = observer
            self.watch = watch
            self.is_ingest_dir = is_ingest_dir

        def __eq__(self, other):
            return self.path == other.path

        def __hash__(self):
            return self.path.__hash__()

    def __init__(self, config, logger, client):
        self.logger = logger
        self.config = config
        self.ingest_client = client

        self._path_info_map = dict()
        self._observer_list = []
        self._lock = threading.Lock()

    def start_observers(self, current_date):
        """
        Start observing the archive file system.

        Args:
        current_date (datetime): The current date. Used to determine
                                 which directories to watch.
        """
        self.restart_observers(current_date, startup=True)

    def restart_observers(self, current_date, startup=False):
        """
        Reset observing of the archive file system with a new current date.

        Args:
        current_date (datetime): The current date. Used to determine
                                 which directories to watch.
        startup (bool): Whether this is the initial startup of the ingest_watchdog.
        """
        with self._lock:
            self._path_info_map.clear()
            self._observer_list.clear()

            if self.config.method == "polling":
                self._reset_polling_observers(current_date)
            else:
                self._reset_inotify_observers(current_date)

        # Start the observer event threads
        self.start()

        # If we're not on initial startup, do a resync for today and yesterday as a sanity check for
        # any files that arrived at the very end of yesterday and haven't been synced,
        # and for any files created in today's directory before we noticed the new date
        # This is not needed for initial startup because the startup resync handles this.
        if not startup:
            self.resync(current_date, 2)

    def _reset_polling_observers(self, current_date):
        """
        Reset the observers when using the "polling" method.

        Args:
        current_date (datetime): The current date. Used to determine
                                 which directories to watch.

        """

        # We create one observer per "search". We also want to avoid having more than one observer watching the same
        # path. So we sort the searches by interval so that any paths covered by two searches are watched
        # by the observer wtih the shortest interval
        for search in sorted(self.config.polling.searches, key=lambda x: x.interval):

            # For polling observers we use a sorted list of directory entries, so that override.*.access files are returned
            # in the correct order.
            observer = PollingWithSimulatedCloseObserver(
                search.interval,
                self.config.polling.write_delay,
                os.stat,
                sorted_logging_scandir,
            )
            self._observer_list.append(observer)
            path_info_list = self._get_paths_for_age(current_date, search.age)
            for path_info in path_info_list:
                if path_info.path in self._path_info_map:
                    # Don't watch a path with more than one observer
                    continue
                path_info.observer = observer
                self._path_info_map[path_info.path] = path_info
                self._watch(path_info)

    def _reset_inotify_observers(self, current_date):
        """
        Reset the observers when using the "inotify" method.

        Args:
        current_date (datetime): The current date. Used to determine
                                 which directories to watch.

        """

        observer = watchdog.observers.inotify.InotifyObserver(generate_full_events=True)
        self._observer_list.append(observer)

        path_info_list = self._get_paths_for_age(current_date, self.config.inotify_age)
        for path_info in path_info_list:
            path_info.observer = observer
            self._path_info_map[path_info.path] = path_info
            self._watch(path_info)

    def _get_paths_for_age(self, current_date, age_in_days):
        """
        Builds PathInfo objects for all the paths age_in_days away from current_date.

        Args:
        current_date (datetime): The current date.
        age_in_days (int): How many days in the past to search for files.

        Returns (set): The paths to watch for new data files, including parent directories to watch for
        new child directoreis.

        """
        paths = set()
        paths.add(IngestWatcher.PathInfo(self.config.data_root, False))

        # Start from tommorrow in case of timezone weirdness causing a path for tomorrow is created before we think
        # it is tommorrow
        start_date = current_date + datetime.timedelta(days=1)
        for age in range(age_in_days + 1):
            d = start_date - datetime.timedelta(days=age)
            date_path = self.config.data_root / Path(d.strftime("%Y-%m/%d"))
            paths.add(IngestWatcher.PathInfo(date_path, False))
            paths.add(IngestWatcher.PathInfo(date_path.parent, False))
            for instrument in self.config.instrument_dirs:
                paths.add(IngestWatcher.PathInfo(date_path / instrument, True))

        return paths

    def _watch(self, path_info):
        """
        Watch a path using the watchdog API.

        Args:
        path_info (PathInfo): The path to watch. This will be updated with the observer and
                              watch object from the watchdog API.
        """
        if path_info.path.exists():
            self.logger.info(f"Watching path {path_info.path}")
            if path_info.watch is not None:
                path_info.observer.unschedule(path_info.watch)
            path_info.watch = path_info.observer.schedule(self, path_info.path)
        else:
            self.logger.info(
                f"Path {path_info.path} does not exist (yet). Will wait for it to be created."
            )

    def start(self):
        """
        Start all observer threads.
        """
        self.logger.debug("Starting...")
        with self._lock:
            for observer in self._observer_list:
                observer.start()
        self.logger.debug("Started.")

    def stop(self):
        """
        Stop all observer threads.
        """
        self.logger.debug("Stopping...")
        with self._lock:
            for observer in self._observer_list:
                observer.stop()
                observer.join()
        self.logger.debug("Stopped...")

    def is_alive(self):
        """
        Determine if all observer threads are still alive.
        """
        with self._lock:
            result = all([o.is_alive() for o in self._observer_list])
            self.logger.debug(f"Alive: {result}")
            return result

    def on_any_event(self, event):
        """
        Event handler method called by the watchdog API for any events.

        Args:
        event (FileSystemEvent): The event that ocurred.
        """
        self.logger.debug(repr(event))

    def on_created(self, event):
        """
        Event handler method called when a new file or directory is found.

        Args:
        event (FileSystemEvent): The event object with information about what was created.
        """
        try:
            if event.is_directory:
                self.logger.info("New directory created " + event.src_path)
                resync_paths = []
                # A new directory, is it one we're waiting for?
                with self._lock:
                    # When directories are created together (as in mkdir -p) we won't always get the
                    # create for the lower level directory. So we ignore the source in the event and just
                    # check to see if any of the directories we want to watch now exist
                    for path_info in self._path_info_map.values():
                        self.logger.debug(
                            f"pi.path {path_info.path} pi.watch {path_info.watch}"
                        )
                        try:
                            if path_info.watch is None and path_info.path.exists():
                                self._watch(path_info)
                                if path_info.is_ingest_dir:
                                    resync_paths.append(path_info.path)
                        except PermissionError:
                            # Sometimes path.exists() gets a permission error
                            # when has just been created, but eventually
                            # that gets fixed. So treat it as not existing (yet)
                            logger.debug(
                                f"Permission error reading {path_info.path}, assuming it's not done being created."
                            )

                for path in resync_paths:
                    self.resync_path(path)
        except Exception:
            self.logger.error("Exception in on_created", exc_info=True)
            # Don't let the exception escape, as it will cause ingest_watchdog to exit

    def on_closed(self, event):
        """
        Event handler method called when a new file or directory is closed.
        If this happens on a file in an instrument directory, the file is
        considered completed and a notification is sent to the lick archive ingest
        service.

        Args:
        event (FileSystemEvent): The event object with information about what was closed.
        """
        # A new file is done writing, is it in one of our lowest level paths?
        new_file = Path(event.src_path)
        notify = False
        with self._lock:
            if new_file.parent in self._path_info_map:
                notify = self._path_info_map[new_file.parent].is_ingest_dir

        if notify:
            try:
                logger.info(f"Notifying archive of '{new_file}'")
                self.ingest_client.add_ingest_notifications(new_file)
            except RequestException as e:
                logger.error(
                    f"Failed to ingest {new_file} due to failure contacting archive server: {e}"
                )

    def on_moved(self, event):
        """
        Event handler method called when a file or directory is moved
        into or out of the archive filesystem.
        If a new file is moved to an instrument directory, a notification is sent to the
        lick archive ingest service.

        Args:
        event (FileSystemEvent): The event object with information about what was moved.
        """

        # check for a file moved into our lowest level paths
        if event.dest_path is None:
            # We'll get move-in and move-out events sometimes. move-out events will only
            # have a source. Since we only care about new things in the archive,
            # we reutrn if there is no dest path
            return
        if not event.is_directory:
            new_file = Path(event.dest_path)
            notify = False
            with self._lock:
                if new_file.parent in self._path_info_map:
                    notify = self._path_info_map[new_file.parent].is_ingest_dir

            if notify:
                try:
                    logger.info(f"Notifying archive of '{new_file}'")
                    self.ingest_client.add_ingest_notifications(new_file)
                except RequestException as e:
                    logger.error(
                        f"Failed to ingest {new_file} due to failure contacting archive server: {e}"
                    )
        else:
            new_path = Path(event.dest_path)
            resync = False
            with self._lock:
                if new_path in self._path_info_map:
                    path_info = self._path_info_map[new_path]

                    # A directory we want to watch was  was moved into the archive. Weird but we can support it.
                    if path_info.watch is None:
                        self._watch(path_info)
                        if path_info is not None and path_info.is_ingest_dir:
                            resync = True

            if resync:
                self.resync_path(new_path)

    def resync(self, current_date, age):
        """
        Resync all paths age days older than current_date.

        Args:
        current_date (datetime):
        """
        for path_info in self._get_paths_for_age(current_date, age):
            if path_info.is_ingest_dir and path_info.path.exists():
                self.resync_path(path_info.path)

    def resync_path(self, path):
        """
        Resync the contents of a given path with what's in the archive database. This
        is done by querying the archive software for how many files it has for the path.
        If this doesn't match how many files are actually in the path, all the files are
        sent to the lick archive ingest service.

        Args:
        path (pathlib.Path): The path to resync.
        """
        self.logger.info(f"Resyncing {path}")
        archive_count = 0
        try:
            archive_count = self.ingest_client.sync_query(path)
        except RequestException as e:
            logging.error(
                f"Failed to resync {path} due to failure querying archive server: {e}"
            )
        except ValueError as e:
            logging.error(f"Failed to resync {path}: {e}")

        actual_count = 0
        files_to_sync = []
        for child in path.iterdir():
            if child.is_file():
                files_to_sync.append(child)
                actual_count += 1
        self.logger.info(
            f"Resync found {archive_count} files, {actual_count} are in the directory."
        )
        if actual_count > archive_count:
            # We need to resync.
            try:
                self.logger.info(f"Resyncing {len(files_to_sync)} files.")
                self.ingest_client.add_ingest_notifications(files_to_sync)
            except RequestException as e:
                logging.error(
                    f"Failed to resync {path} due to failure ingesting into archive server: {e}"
                )


def get_parser():
    """
    Parse bulk_ingest_metadata command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Ingest metadata for Lick data into the archive database.\n"
        "A log file of the ingest is created in bulk_ingest_<timestamp>.log.\n"
        "A separate ingest_failures.n.txt is also created listing files that failed ingesting."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="/etc/lick_archive.conf",
        help="Config file to read. Defaults to /etc/lick_archive.conf.",
    )
    parser.add_argument(
        "--log_path",
        "-l",
        type=Path,
        default=Path.cwd(),
        help="Directory to write log file to. Defaults to current directory",
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

    setup_service_logging(args.log_path, "ingest_watchdog", args.log_level)

    try:
        logger.info(f"Reading configuration from '{args.config}'.")
        config_parser = configparser.ConfigParser()
        config_parser.read(args.config)

        config = parse_and_validate_config(config_parser)

    except ValueError as e:
        logger.error(e)
        return 1

    try:
        client = LickArchiveIngestClient(
            config.ingest.url,
            config.ingest.retry_max_delay,
            config.ingest.retry_max_time,
            config.ingest.request_timeout,
            config.ingest.key,
        )
        watcher = IngestWatcher(config, logger, client)

        current_date = datetime.date.today()
        watcher.start_observers(current_date)
        watcher.resync(current_date, config.startup_resync_age)

        done = False
        while not done:

            # Reset again when the date changes
            while datetime.date.today() == current_date and watcher.is_alive():
                sleep(5)

            if not watcher.is_alive():
                # Something happened to the observer threads, probably a signal, so its time to exit
                done = True

            watcher.stop()
            if not done:
                current_date = datetime.date.today()
                watcher.restart_observers(current_date)

    except Exception as e:
        logger.critical(f"ingest_watchdog failed with exception: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
