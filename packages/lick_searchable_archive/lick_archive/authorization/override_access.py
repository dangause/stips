"""
Classes and data types related to Parsing and saving Override Access files.

The Lick archive supports override access files used to override who can view files.
These files are named "override.access" or "override.n.access", and are applied in order
with override.access applied first.
"""

from __future__ import annotations  # To allow a class to return itself

import logging

logger = logging.getLogger(__name__)

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional, Sequence

from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.metadata.data_dictionary import FrameType
from lick_archive.metadata.metadata_utils import parse_file_name

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


class OverrideAccessRule:
    """Represents a single rule (line) from an override access file.

    Args:
        pattern:    The globpat that determines which files match this rule.  If it is of the form "aaa.xxx",
                    with no '.'s in aaa and aaa does not end in '*' and xxx is not empty, then it will also match "aaa.*.xxx".

                    Example 1: globpat b1024.fits expands to b1024.fits and b1024.*.fits.
                    Example 2: globpat b102*.fits is not changed.

        obstype:    The observation type (aka frame_type) that will be applied to the file instead of what the archive would
                    normally deduce. If the obstype is for a calibration type, the file is accessible to all observers on the
                    night it was taken.

        ownerhints: Ownerhints that should be applied to the file to determine who should be able to access it.

    One of either obstype or ownerhints *must* be specified.
    """

    class Keywords(Enum):
        """The allowed keywords in an override access file. Currently ''obstype'' and ''access''"""

        OBSTYPE = "obstype"
        ACCESS = "access"

    def __init__(
        self,
        pattern: str,
        obstype: Optional[FrameType] = None,
        ownerhints: Optional[list[str]] = [],
    ):

        if obstype is None and (ownerhints is None or len(ownerhints) == 0):
            raise ValueError(
                "Either an obstype value or non-empty access list must be specified."
            )

        self.pattern = pattern
        self.obstype = obstype
        self.ownerhints = ownerhints

        # There's a special case where a glob pat like aaa.xxx,
        # can be expanded to ``aaa.*.xxx``, if aaa does not end in a ``*``
        # We use a list of patterns to deal with this

        # The way Rules.txt is written aaa or xxx could be empty. e.g. ``.xxx`` or ``aaa.`` or
        # ``.``.  These will match ``.*.xxx``, ``aaa.*.``, and ``.*.`` respectively.
        # I don't know if this is intentional but the below code supports it.
        split_pattern = self.pattern.split(".", maxsplit=1)
        if len(split_pattern) > 1 and not split_pattern[0].endswith("*"):
            self._patterns = [self.pattern, split_pattern[0] + ".*." + split_pattern[1]]
        else:
            self._patterns = [self.pattern]

    @classmethod
    def from_str(cls, line: str) -> OverrideAccessRule:
        found_keyword = None
        for keyword in cls.Keywords:
            start_keyword = line.find(keyword.value)
            if start_keyword != -1:
                pattern = line[0:start_keyword].strip()
                value_str = line[start_keyword + len(keyword.value) :].strip()
                found_keyword = keyword
                break

        if found_keyword == cls.Keywords.OBSTYPE:
            # Convert the value to a Frame type. This will raise an exception
            # if the value isn't a known file type
            lower_case_value = value_str.lower()
            if lower_case_value.lower() == "cal":
                obstype = FrameType.calib
            else:
                obstype = FrameType(lower_case_value)
            return OverrideAccessRule(pattern=pattern, obstype=obstype)
        elif found_keyword == cls.Keywords.ACCESS:
            ownerhints = value_str.split()
        else:
            raise ValueError(f"Unparseable line in override access file: {line}")

        try:
            return OverrideAccessRule(pattern=pattern, ownerhints=ownerhints)
        except Exception as e:
            raise ValueError(f"Unparseable line in override access file: {line}: {e}")

    def matches(self, filename: str | Path) -> bool:
        """Check whether a rule matches a given filename"""
        name = Path(filename).name

        return any([fnmatch(name, pat) for pat in self._patterns])

    def __str__(self):
        return f"Pattern: {self.pattern} {'' if self.obstype is None else 'obstype ' + self.obstype.value} {'' if self.ownerhints is None else 'access' + ','.join(self.ownerhints)}"


@dataclass
class OverrideAccessFile:
    """A representation of an archive override.access file."""

    observing_night: date
    """The day the override access file is from"""

    instrument_dir: str
    """The instrument directory the override access file is from"""

    sequence_id: int
    """The sequence number of the override access file, as given by it's name. For example 'override.access' has
       a sequence number of 0. 'override.1.access' has a sequence nubmer of 1, etc.
    """

    override_rules: list[OverrideAccessRule] = field(default_factory=list)

    _filename_pattern = re.compile(r"^override(\.\d+)?\.access$")

    @classmethod
    def check_filename(cls, file: str | Path) -> bool:
        """Check whether a filename is for an override acces file

        Args:
            file: The filename to check

        Return:
            True if the filename is an override access file, false if it is not.

        """
        if not isinstance(file, Path):
            file = Path(file)

        return cls._filename_pattern.match(file.name) is not None

    @classmethod
    def from_file(cls, file: str | Path) -> OverrideAccessFile:
        """Parse an override access file.

        Args:
            file: The file to parse.

        Return: The OverrideAccessFile object. Raises a ValueError if the file is invalid.
        """
        logger.info(f"Parsing override access file {file}")
        if isinstance(file, str):
            file = Path(file)

        # Parse the date string from the filename (This will raise an exception if the
        # date could not be parsed from the path)
        file = file.resolve()
        date_str, instr_dir = parse_file_name(file)
        night = date.fromisoformat(date_str)

        # Check the file's name and get the sequence id
        match = cls._filename_pattern.match(file.name)
        if match is None:
            raise ValueError(f"Invalid override access file name '{file}'.")

        if match.groups()[0] is None:
            # No sequence number, e.g. "override.access"
            seq_id = 0
        else:
            # A sequence number, e.g. "override.1.access". The group will have the "." in it.
            seq_id = int(match.groups()[0].strip("."))

        try:
            override_rules = []
            with open(file, "r") as f:
                for line in f:
                    # Skip blank or comments
                    line = line.strip()
                    if line.strip() == "" or line.startswith("#"):
                        continue
                    else:
                        rule = OverrideAccessRule.from_str(line)
                        if rule is not None:
                            override_rules.append(rule)
        except Exception as e:
            raise ValueError(f"Error reading file {file}: {e}")

        return OverrideAccessFile(night, instr_dir, seq_id, override_rules)

    def __str__(self):
        """Return a string representation of the override access file as its pathname"""
        return str(
            lick_archive_config.ingest.archive_root_dir
            / self.observing_night.strftime("%Y-%m/%d")
            / self.instrument_dir
            / f"override{'' if self.sequence_id == 0 else '.' + str(self.sequence_id)}.access"
        )


def find_matching_rules(
    access_files: Sequence[OverrideAccessFile], filename: str | Path
) -> OverrideAccessRule:
    # Per rules, each rule within an access file is matched in order, and the first
    # one found is used
    # But only the most recent override file is used

    matching_rule = None
    if len(access_files) > 0:
        # Sort by sequence id and only use the most recent file
        access_files_sorted = sorted(
            access_files, reverse=True, key=lambda x: x.sequence_id
        )
        access_file = access_files_sorted[0]
        for access_rule in access_file.override_rules:
            if access_rule.matches(filename):
                if matching_rule is None:
                    matching_rule = access_rule
                    # We could break here, but out of curiosity
                    # I want to log when a file *does* match duplicate rules
                    logger.debug(
                        f"{filename} matches access rule {access_rule} from {access_file}"
                    )
                else:
                    logger.debug(
                        f"File matched multiple access rules. Rule {access_rule} from {access_file} ignored."
                    )

    return matching_rule
