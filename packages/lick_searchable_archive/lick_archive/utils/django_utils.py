"""A set of utility functions related to django."""

import logging
import os
from pathlib import Path
from typing import Mapping

logger = logging.getLogger(__name__)

import unicodedata


def setup_django():
    """Setup the django environment when running from a command line script."""
    import sys

    django_root = Path(__file__).parent.parent
    sys.path.insert(0, str(django_root))
    import os

    os.environ["DJANGO_SETTINGS_MODULE"] = "lick_archive_site.settings"

    import django

    django.setup()


def setup_django_logging(
    log_file: Path | str, log_level: int | str, stdout_level=int | str | None
):
    """Override Django logging to use a new path and loggging level.
    Intended to allow command line scripts to use Django code but
    log to a different location than Django web apps."""

    from django.conf import settings
    from django.utils.log import configure_logging

    # Override logging setup to use a new path or logging level
    log_settings = settings.LOGGING
    if log_file is not None:
        log_settings["handlers"]["django_log"]["filename"] = str(log_file)

    if log_level is not None:
        log_settings["handlers"]["django_log"]["level"] = log_level
    if stdout_level is not None:
        log_settings["handlers"]["stdout"] = {"class": "logging.StreamHandler"}
        log_settings["handlers"]["stdout"]["level"] = stdout_level
        log_settings["loggers"][""]["handlers"].append("stdout")
    configure_logging(settings.LOGGING_CONFIG, settings.LOGGING)


def validate_username(username):
    """A Django validator for archive user names
    This validator is written to be used in Django forms and models,
    and is consistent with other django `Link validators <https://docs.djangoproject.com/en/4.2/ref/validators/>`_.
    Args:
        username (str): User name to validate

    Return:
        None if successfull.

    Raises:
        :obj:`django.core.exceptions.ValidationError` Raised if validation failed.
    """
    from django.core import validators
    from django.core.exceptions import ValidationError

    # First apply django validators
    validators.ProhibitNullCharactersValidator()(username)
    validators.MinLengthValidator(1)(username)
    validators.MaxLengthValidator(150)(username)

    # Now apply our own valiation
    for c in username:
        cat = unicodedata.category(c)
        if cat[0] in "LNP":
            # Allow letters, numbers, punctuation
            continue
        elif cat == "Zs":
            # Allow spaces
            continue
        else:
            # Disallow everything else:
            name = unicodedata.name(c, f"{ord(c):04}")
            raise ValidationError(
                message=f"Username has invalid character '{c}' ({name})"
            )
    return


def validate_chars(input, allowed_chars, error_label="string"):
    """Validator to validate that a string is composed of only an allowed set of characters"""

    from django.core import validators
    from django.core.exceptions import ValidationError

    # First apply django validators
    validators.ProhibitNullCharactersValidator()(input)

    for c in input:
        if c not in allowed_chars:
            raise ValidationError(message=f"{error_label} has invalid character {c}.")


def log_request_debug(request):
    """Log debug information about an incomming Django request."""
    if logger.isEnabledFor(logging.DEBUG):
        for key in request.META.keys():
            if "password" in key.lower():
                logger.debug(f"Header key '{key}' value: ***")
            else:
                logger.debug(f"Header key '{key}' value: {request.META[key]}")
        for key in os.environ:
            logger.debug(f"Environment variable '{key}' value: '{os.environ[key]}'")
        if hasattr(request, "session"):
            session = request.session
            if session is None:
                logger.debug("Session is None")
            else:
                logger.debug(f"Session key: {session.session_key}")
                logger.debug(f"Session expiry age: {session.get_expiry_age()}")
                for key, value in session.items():
                    logger.debug(f"Session[{key}] : '{value}'")
        else:
            logger.debug("Request has no session.")
        if hasattr(request, "user"):
            logger.debug(f"Request user: '{request.user.username}'")
        else:
            logger.debug("Request has no user.")
        if hasattr(request, "validated_query"):
            logger.debug("Validated query found")
            if request.validated_query is None:
                logger.debug("validated_query is None")
            elif isinstance(request.validated_query, Mapping):
                logger.debug("validated_query is a mapping")
                for key in request.validated_query:
                    logger.debug(f"{key} = {request.validated_query[key]}")
            else:
                logger.debug(f"validated_query: {request.validated_query}")
