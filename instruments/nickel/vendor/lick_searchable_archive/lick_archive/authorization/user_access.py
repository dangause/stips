import logging

logger = logging.getLogger(__name__)
import dataclasses
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Sequence

from lick_archive.authorization import override_access
from lick_archive.authorization.date_utils import (
    calculate_public_date,
    get_file_begin_end_times,
    get_observing_night,
)
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db.archive_schema import FileMetadata, UserDataAccess
from lick_archive.external import ScheduleDB, compute_ownerhint, get_keyword_ownerhints
from lick_archive.metadata.data_dictionary import MAX_PUBLIC_DATE, FrameType
from lick_archive.metadata.metadata_utils import parse_file_name
from lick_archive.utils.timed_cache import timed_cache

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


class Visibility(Enum):
    """The access visibility granted by an override access file "access" rule."""

    PUBLIC = "Public"
    PROPRIETARY = "Proprietary"
    UNKNOWN = "Unknown"
    DEFAULT = "DEFAULT"


@dataclasses.dataclass
class Access:
    """Class defining the access state of the file, i.e. who can see it and why."""

    observing_night: date
    """The observing night for the file, based on Pacific Standard Time (UTC-8)"""

    file_metadata: FileMetadata
    """The file metadata for the file"""

    visibility: Visibility
    """The file's visibility"""

    ownerids: list[int]
    """The observer id for the owners for the file"""

    coverids: list[str]
    """The coversheet ids for the file"""

    reason: list[str]
    """Why the file ended up with the access state it has"""

    public_date: date = None
    """The date the file becomes public."""


def reason(rule, description):
    return f"Rule {rule}: {description}"


def set_auth_metadata(file_metadata: FileMetadata) -> FileMetadata:
    try:
        access = identify_access(file_metadata)

        if access.visibility == Visibility.PROPRIETARY:
            # Set the public date for the file if it's proprietary
            public_date, reason_str, is_public = get_public_date(
                file_metadata, access.observing_night, access.ownerids
            )

            access.public_date = public_date
            access.reason.append(reason_str)
            if is_public:
                access.visibility = Visibility.PUBLIC

        elif access.visibility == Visibility.DEFAULT:
            # Rule 6 (called 7 in old Rules.txt). No observers could be found for the file,
            # so it's public
            access.visibility = Visibility.PUBLIC
            access.reason.append(reason("6", "No observers found for file"))

    except Exception:
        # Any failure should be marked as unknown
        logger.error(
            f"Unknown error ocurred in identifying the proprietary access period of the file '{file_metadata.filename}'",
            exc_info=True,
        )
        access = Access(
            file_metadata=file_metadata,
            observing_night=get_observing_night(datetime.now(timezone.utc)),
            visibility=Visibility.UNKNOWN,
            ownerids=[],
            coverids=[],
            reason=[
                reason(
                    "0z",
                    "Unknown error ocurred in identifying the proprietary access period of the file.",
                )
            ],
        )

    return set_access_metadata(file_metadata, access)


def get_public_date(
    file_metadata: FileMetadata, observing_night: date, ownerids: list[int]
) -> tuple[date, str, bool]:
    """Return the earliest public date for a file given it's ownerids"""

    # Get the public dates for all ownerids
    public_dates = ScheduleDB().get_public_dates(
        file_metadata.telescope, observing_night, ownerids
    )

    # Add default dates to public_dates if one isn't set
    default_public_date = calculate_public_date(
        observing_night, lick_archive_config.authorization.default_proprietary_period
    )
    public_dates = [
        (obid, d, False) if d is not None else (obid, default_public_date, True)
        for obid, d in public_dates
    ]
    if len(public_dates) == 0:
        # No public dates from the DB, treat all observers as having the default public_date
        public_dates = [(obid, default_public_date, True) for obid in ownerids]

    # Pick the earliest public_date
    public_dates.sort(key=lambda x: x[1])
    obid, earliest_date, is_default = public_dates[0]

    is_public = False

    # Make the file public if the earliest date has passed
    if get_observing_night(datetime.now(tz=timezone.utc)) >= earliest_date:
        # The file is public now
        is_public = True
        if is_default is False:
            reason = f"File has passed observer {obid}'s proprietary end date of {earliest_date}"
        else:
            reason = f"File has passed default proprietary end date of {earliest_date}"
    else:
        reason = f"File is not public, earliest public date is {earliest_date} from observer {obid}."

    return earliest_date, reason, is_public


def set_access_metadata(file_metadata: FileMetadata, access: Access) -> FileMetadata:

    if access.coverids is not None and len(access.coverids) > 0:
        file_metadata.coversheet = ";".join(access.coverids)

    if access.visibility == Visibility.PUBLIC:
        # Public,
        if access.public_date is None or access.public_date > get_observing_night(
            datetime.now(tz=timezone.utc)
        ):
            # The file should be public, but there's no public date, or the public date is in the future and
            # therefore the file would not be public.
            # Use the observing night as the public_date to force it to be public.
            file_metadata.public_date = access.observing_night
        else:
            # The calculated public_date allows the file to be public, so keep it
            file_metadata.public_date = access.public_date

        # Make sure there's at least one user (the public user) so that the reason
        # text is saved to the db
        if len(access.ownerids) == 0:
            access.ownerids = [ScheduleDB.PUBLIC_USER]

    elif access.visibility == Visibility.UNKNOWN:
        # Unknown should always have max public date
        file_metadata.public_date = MAX_PUBLIC_DATE
    elif access.public_date is not None:
        file_metadata.public_date = access.public_date
    else:
        # No publication date and not PUBLIC or UNKNOWN.
        # Treat it as UNKNOWN
        file_metadata.public_date = MAX_PUBLIC_DATE
        access.visibility = Visibility.UNKNOWN

    # Make sure unknown files have the UNKNOWN user as their owner
    if (
        access.visibility == Visibility.UNKNOWN
        and ScheduleDB.UNKNOWN_USER not in access.ownerids
    ):
        access.ownerids.append(ScheduleDB.UNKNOWN_USER)

    reason_string = "\n".join(access.reason)
    file_metadata.user_access.clear()
    for ownerid in access.ownerids:
        file_metadata.user_access.append(
            UserDataAccess(obid=ownerid, reason=reason_string)
        )

    logger.info(
        f"Setting access metadata for {file_metadata.filename}. Public date: {file_metadata.public_date}\nReason:\n{reason_string}"
    )
    return file_metadata


def identify_access(file_metadata: FileMetadata) -> Access:

    # Use the directory as the observing night used for determining who can access the file
    try:
        dir_date, dir_instr = parse_file_name(file_metadata.filename)
        observing_night = date.fromisoformat(dir_date)
    except Exception:
        logger.error("Failed to parse date out of file's path.", exc_info=True)
        access = Access(
            file_metadata=file_metadata,
            observing_night=get_observing_night(datetime.now(timezone.utc)),
            visibility=Visibility.UNKNOWN,
            ownerids=[],
            coverids=[],
            reason=[reason("0", "Failed to parse observing night from pathname")],
        )
        return access

    # The access data for the file
    access = Access(
        file_metadata=file_metadata,
        observing_night=observing_night,
        visibility=Visibility.DEFAULT,
        ownerids=[],
        coverids=[],
        reason=[],
    )

    filepath = Path(file_metadata.filename)
    instr = file_metadata.instrument

    # Rule 1: Check for override access rules
    try:
        from lick_archive.apps.archive_auth.api import get_related_override_files

        override_files = get_related_override_files(filepath)
    except Exception:
        access.reason.append(reason("1z", "Failed when querying for override access."))
        access.visibility = Visibility.UNKNOWN
        logger.error("Failed to read override access files.", exc_info=True)
        return access

    override_rule = override_access.find_matching_rules(override_files, filepath)

    if override_rule is not None:
        # There were rules in the override access file(s) that matched this file
        # Rule 1a: Apply any type overrides
        if override_rule.obstype is not None:
            # Override the database's frame type with the new value.
            file_metadata.frame_type = override_rule.obstype

            if override_rule.obstype not in [FrameType.science, FrameType.unknown]:
                access.reason.append(
                    reason(
                        "1a",
                        f"All observers from the night included because override access set file type to {override_rule.obstype.value}.",
                    )
                )
                apply_ownerhints(access, "1a", ["all-observers"])
            else:
                access.reason.append(
                    reason(
                        "1a",
                        f"No special rule for obstype: {override_rule.obstype.value}",
                    )
                )

        # Rule 1b,c,d: Apply any ownerhints from the override access
        if len(override_rule.ownerhints) > 0:
            if "public" in override_rule.ownerhints:
                access.visibility = Visibility.PUBLIC
                access.reason.append(
                    reason("1b", "Override access file gave public visibility.")
                )
            else:
                apply_ownerhints(
                    access, "1b/c/d", override_rule.ownerhints, allow_unscheduled=True
                )
        if access.visibility != Visibility.DEFAULT:
            # The override access had enough information to set the access, so return those results
            return access

    # Rule 2a: Check for always public files

    public_suffixes = lick_archive_config.authorization.public_suffixes[instr.value]
    for suffix in public_suffixes:
        if filepath.name.endswith(suffix):
            access.visibility = Visibility.PUBLIC
            access.reason.append(
                reason("2a", f"Suffix {suffix} is public for instrument: {instr.value}")
            )
            return access

    # Rule 2b: Check for fixed owners
    fixed_owner = lick_archive_config.authorization.fixed_owners[instr.value]
    if fixed_owner is not None:
        if fixed_owner in lick_archive_config.authorization.public_observers:
            access.visibility = Visibility.PUBLIC
            access.reason.append(
                reason(
                    "2b",
                    f"Fixed public owner {fixed_owner} for instrument {instr.value}.",
                )
            )
        else:
            apply_ownerhints(access, "2b", [fixed_owner])

            if access.visibility == Visibility.DEFAULT:
                # This shouldn't happen, the fixed owner in the config file must not match what apply_ownerhints expects,
                # which is probably an error
                access.visibility = Visibility.UNKNOWN
                access.reason.append(
                    reason(
                        "2z",
                        f"Unknown fixed owner {fixed_owner}, this is likely an archive mis-configuration.",
                    )
                )
        # The fixed owner determined ownership
        return access

    # Rule 3: Calibration/focus frame type shoud be viewable to all observers on that night
    if file_metadata.frame_type not in [FrameType.science, FrameType.unknown]:
        access.reason.append(
            reason(
                "3",
                f"All observers from the night can access frame type: {file_metadata.frame_type.value}",
            )
        )
        apply_ownerhints(access, "3", ["all-observers"])
        return access

    # Rule 4: Look for ownerhints from the schedule keyword history

    # This returns tuples [time, ownerhint], sorted by time, time is returned as a datetime
    try:
        schedule_ownerhints = get_keyword_ownerhints(
            file_metadata.telescope, access.observing_night
        )
    except Exception as e:
        logger.error(
            f"Failed to query for OWNERHINT for {instr.value} on {access.observing_night.isoformat()}",
            exc_info=True,
        )
        access.reason.append(
            reason(
                "4z",
                f"Failed to query for OWNRHINT for {instr.value} on {access.observing_night.isoformat()}: {e}",
            )
        )
        access.visibility = Visibility.UNKNOWN
        return access

    # Get beg/end_times from the file's header information
    beg_time, end_time = get_file_begin_end_times(file_metadata)

    # 4a: First look for ownerhints between the beginning/end time of the file
    ownerhints = []
    ownerhint_search_rule = "4a"
    if beg_time is not None and end_time is not None:
        ownerhints = [
            so[1]
            for so in schedule_ownerhints
            if beg_time <= so[0] and end_time >= so[0]
        ]

    # 4b: If there is no beg/end times, or nothing was found in the beginning/end times, find the latest entry before the file's mtime
    if len(ownerhints) == 0:
        ownerhint_search_rule = "4b"
        if file_metadata.mtime is None:
            access.visibility = Visibility.UNKNOWN
            access.reason.append(reason("4v", "No mtime information in db."))
            return access

        ownerhints = [
            so[1] for so in schedule_ownerhints if so[0] < file_metadata.mtime
        ]
        if len(ownerhints) > 1:
            ownerhints = [ownerhints[-1]]

    if len(ownerhints) == 1:
        apply_ownerhints(access, ownerhint_search_rule, ownerhints)

        if access.visibility == Visibility.DEFAULT:
            access.visibility = Visibility.UNKNOWN
            access.reason.append(
                reason("4y", f"No owner found for ownerhint: {ownerhints[0]}")
            )
            return access

    elif len(ownerhints) > 1:
        access.visibility = Visibility.UNKNOWN
        access.reason.append(
            reason("4w", f"Multiple ownerhints for file: {','.join(ownerhints)}")
        )
        return access
    else:
        access.reason.append(reason(ownerhint_search_rule, "No ownerhints found."))

    # Rule 5 Look for all observers on that night.
    apply_ownerhints(access, "5", ["all-observers"])

    return access


def apply_ownerhints(
    access: Access,
    rule: str,
    ownerhints: Sequence[str],
    allow_multiple=False,
    allow_unscheduled=False,
):
    """Apply ownerhints to a file to find it's owners"""

    if len(ownerhints) == 0:
        ownerhints = ["all-observers"]

    if "all-observers" in ownerhints:
        allow_multiple = True

    # Convert public ownerhints to be "public"
    public_ownerhint_pattern = (
        lick_archive_config.authorization.public_ownerhint_pattern
    )
    if public_ownerhint_pattern is not None:
        ownerhints = [
            oh if not re.match(public_ownerhint_pattern, oh) else "public"
            for oh in ownerhints
        ]

    all_obids = set()
    all_coverids = set()

    for ownerhint in ownerhints:
        try:
            # Query the schedule database for matching observer ids and cover ids
            obids, coverids = compute_ownerhint(
                access.observing_night, access.file_metadata.telescope, ownerhint
            )
        except Exception as e:
            logger.error(
                f"Failed to query schedule db for date {access.observing_night}, telescope: {access.file_metadata.telescope}: {e}",
                exc_info=True,
            )
            access.reason.append(
                reason(rule, f"Observing calendar ownerhint query failed: {e}")
            )
            access.visibility = Visibility.UNKNOWN
            return

        # Use sets to eliminate duplicate ids
        unique_obids = set(obids)
        unique_coverids = set(coverids)

        if ScheduleDB.UNKNOWN_USER in unique_obids:
            if allow_unscheduled:
                # No observer found for that ownerhint on that night, check for an unscheduled observer
                try:
                    unscheduled_obid = _getOwnerhintMap().get(ownerhint, None)
                except Exception as e:
                    logger.error(
                        f"Failed to query archive db for unscheduled ownerhint {ownerhint}: {e}",
                        exc_info=True,
                    )
                    access.reason.append(
                        reason(rule, f"Unscheduled ownerhint query failed: {e}")
                    )
                    access.visibility = Visibility.UNKNOWN
                    return

                if unscheduled_obid is not None:
                    # Replace unknown ids with the unscheduled id
                    unique_obids.remove(ScheduleDB.UNKNOWN_USER)
                    unique_obids.add(unscheduled_obid)
                    access.reason.append(
                        reason(
                            rule,
                            f"Unscheduled observer {ownerhint} found. obsid {unscheduled_obid}",
                        )
                    )
                else:
                    access.reason.append(
                        reason(rule, f"Could not find observer for {ownerhint}")
                    )
            else:
                access.reason.append(
                    reason(rule, f"Could not find observer for {ownerhint}")
                )
        else:
            if len(unique_obids) > 0:
                access.reason.append(
                    reason(
                        rule,
                        f"Scheduled observer for {ownerhint}. obids {','.join([str(id) for id in unique_obids])}",
                    )
                )

        if (
            len(unique_obids) > 1
            and not allow_multiple
            and ScheduleDB.PUBLIC_USER not in unique_obids
        ):
            access.reason.append(
                reason(
                    rule,
                    f"Observing calendar ownerhint query returned multiple users for ownerhint {ownerhint}, ignoring it.",
                )
            )
            continue

        # Combine the observer ids and cover ids from each ownerhint
        all_obids |= set(unique_obids)
        all_coverids |= set(unique_coverids)

    if len(all_obids) > 0:
        if ScheduleDB.PUBLIC_USER in all_obids:
            access.visibility = Visibility.PUBLIC
            access.reason.append(
                reason(rule, "Observing calendar ownerhint query returned public user.")
            )

        else:
            # Eliminate any unknown users
            if ScheduleDB.UNKNOWN_USER in all_obids:
                all_obids.remove(ScheduleDB.UNKNOWN_USER)

            if len(all_obids) == 0:
                # There were no known users, leave visibility at it's default value in case another rule can assign a value
                access.visibility = Visibility.DEFAULT
                access.reason.append(
                    reason(
                        rule,
                        "Observing calendar ownerhint query returned unknown user.",
                    )
                )
            else:
                access.ownerids = list(all_obids)
                access.visibility = Visibility.PROPRIETARY

    if len(all_coverids) > 0:
        access.coverids = list(all_coverids)

    access.reason.append(
        reason(
            rule,
            f"Found {len(all_obids)} observers and {len(all_coverids)} coverids from override access ownerhints: {','.join(ownerhints)}",
        )
    )


@timed_cache(timedelta(hours=1))
def _getOwnerhintMap() -> Mapping:
    """Return a map of all unique ownerhints to observer ids.
    This method is cached and will only query the db and build the map once an hour"""

    from lick_archive.apps.archive_auth.api import get_all_observers

    observers = get_all_observers()

    result = dict()
    duplicates = set()
    for observer in observers:
        first_name = (
            observer.first_name.lower() if observer.first_name is not None else None
        )
        last_name = (
            observer.last_name.lower() if observer.last_name is not None else None
        )

        if last_name is not None and len(last_name) > 0:
            # Add the last name ownerhint
            if last_name in result:
                duplicates.add(last_name)
            else:
                result[last_name] = observer.obid

            # Add the fi_lastname and firstname_lastname ownerhints
            if first_name is not None and len(first_name) > 0:
                fi_last = first_name[0] + "." + last_name
                if fi_last in result:
                    duplicates.add(fi_last)
                else:
                    result[fi_last] = observer.obid

                first_last = first_name + "." + last_name
                if first_last in result:
                    duplicates.add(first_last)
                else:
                    result[first_last] = observer.obid

    # Remove duplicates
    for dup in duplicates:
        del result[dup]

    return result
