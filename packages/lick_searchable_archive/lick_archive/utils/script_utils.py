"""Utility functions for command line interface scripts."""

import logging
import time
from datetime import datetime, timezone
from logging.handlers import WatchedFileHandler
from pathlib import Path


def get_std_log_formatter(log_tid=False, log_pid=False):
    """Return a log formatter with the "standard" for the lick searchable archive.
    This format includes the log level, time, the thread id, line of code + the message.
    The time is always UTC and is to the millisecond.

    In Python 3.10+ this method may no longer be needed as the special '.' entry in configuration
    dicts should be able to set the additional attributes.

    Args:
    log_pid (bool):  Whether or not to log process ids. Defaults to False.
    log_tid (bool):  Whether or not to log thread ids. Defaults to False.

    Return (logging.Formatter): A formatter for the Python built in logging facility.
    """
    optional_format = ""
    if log_pid:
        optional_format += "pid:{process} "
    if log_tid:
        optional_format += "tid:{thread} "

    formatter = logging.Formatter(
        fmt="{levelname:8} {asctime} "
        + optional_format
        + "{module}:{funcName}:{lineno} {message}",
        style="{",
    )
    # If these two attributes
    formatter.converter = time.gmtime
    formatter.default_msec_format = "%s.%03d"
    return formatter


def get_log_path(log_name: str, log_dir: str | Path | None = None) -> Path:
    """Generate a log file name with a timestamp.

    Args:
        log_name: The name of the application creating the log.
        log_dir:  The path where the log should go. If None, only the filename is generated.

    Return:
        The generated path for for the log file.
    """
    log_timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    log_path = Path(f"{log_name}_{log_timestamp}.log")
    if log_dir is not None:
        log_path = Path(log_dir) / log_path
    return log_path


def setup_logging(log_path, log_name, log_level, log_tid=False, log_pid=False):
    """Setup loggers to send some information to stderr and some to a file. The logging level for stderr is
    always set to INFO, but for the log file it is configurable. This logging is intended for command line
    scripts that are run manually.

    Args:
    log_path (str or None): Directory to place a log file. The log will be in the current directory if this is None.

    log_name (str):  Name of the log file. The full name will be <log_path>/<log_name>_<timestamp>.log

    log_level (str): The logging level of messages to send to the log file. One of CRITICAL, ERROR, WARNING, INFO
                     DEBUG, NOTSET.

    log_tid (bool):  Whether or not to log thread ids. Defaults to False.

    Return:
        Path: The path of the log file.
    """

    log_file = get_log_path(log_name, log_dir=log_path)

    # Configure a file handler to write detailed information to the log file
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(get_std_log_formatter(log_tid))

    # Setup a basic formatter for output to stderr
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter())

    logging.basicConfig(handlers=[stream_handler, file_handler], level=logging.DEBUG)

    return log_file


def setup_service_logging(log_path, log_name, log_level, log_tid=False):
    """Setup loggers for services. Services log everything to a file, and logrotate will rotate out the log file
    periodically.

    Args:
    log_path (str or None): Directory to place a log file. The log will be in the current directory if this is None.

    log_name (str):  Name of the log file. The full name will be <log_path>/<log_name>_<timestamp>.log

    log_level (str): The logging level of messages to send to the log file. One of CRITICAL, ERROR, WARNING, INFO
                     DEBUG, NOTSET.

    log_tid (bool):  Whether or not to log thread ids. Defaults to False.
    """

    log_file = f"{log_name}.log"
    if log_path is not None:
        log_file = Path(log_path).joinpath(log_file)

    # Configure a watched file handler to write to the log file
    file_handler = WatchedFileHandler(log_file)
    file_handler.setLevel(log_level)
    tid_format = " tid:{thread}" if log_tid else ""
    file_handler.setFormatter(
        logging.Formatter(
            fmt="{levelname:8} {asctime}"
            + tid_format
            + " {module}:{funcName}:{lineno} {message}",
            style="{",
        )
    )

    logging.basicConfig(handlers=[file_handler], level=logging.DEBUG)


def get_unique_file(path, prefix, extension=""):
    """
    Return a unique filename.

    Args:
    path (pathlib.Path): Path where the unique file will be located.
    prefix (str):  Prefix name for the file.
    extension (str): File extension for the file. Defaults to empty.

    Returns:
    A filename starting with prefix, ending with extension, that does not currently
    exist.
    """
    if extension != "" and not extension.startswith("."):
        extension = "." + extension

    unique_file = path.joinpath(prefix + extension)
    n = 1
    while unique_file.exists():
        unique_file = path.joinpath(prefix + f".{n}" + extension)
        n += 1
    return unique_file
