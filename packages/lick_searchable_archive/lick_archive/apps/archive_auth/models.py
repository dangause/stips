import datetime
from pathlib import Path
from typing import Iterable

import django.utils
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from lick_archive.authorization import override_access
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.metadata.data_dictionary import FrameType
from lick_archive.metadata.metadata_utils import parse_file_name

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


class ArchiveUser(AbstractUser):
    obid = models.IntegerField(blank=True, null=True, unique=True)
    stamp = models.DateTimeField(default=django.utils.timezone.now)


class DBOverrideAccessFile(models.Model):
    """A Django ORM representation of an archive override.access file.

    Args:
        night          (date): The observation night the file is in.
        instrument_dir (str):  The instrument directory the file is in.
        sequence_id    (int):  The sequence number of the override access file,
                               as given by it's name. For example
                               'override.access' has a sequence number of 0.
                               'override.1.access' has a sequence nubmer of 1, etc.
    """

    night = models.DateField(default=datetime.date.today, blank=False)
    instrument_dir = models.CharField(
        max_length=80,
        choices=[
            (name, name)
            for name in lick_archive_config.authorization.telescope_names.keys()
        ],
        blank=False,
    )
    sequence_id = models.IntegerField(default=0, blank=False)

    class Meta:
        # Enforce uniqueness on the components of the path name of override access file.
        unique_together = ["night", "instrument_dir", "sequence_id"]

        # How to sort in the admin site
        ordering = ["night", "instrument_dir", "sequence_id"]

        # The object name in the admin site
        verbose_name = verbose_name_plural = "Override Access Files"

    def __str__(self):
        """Return a string representation of the access file suitable for use in the
        admin site."""
        return f"{self.night.strftime('%Y-%m/%d')}/{self.instrument_dir}/override{'' if self.sequence_id == 0 else '.' + str(self.sequence_id)}.access"


class DBOverrideAccessRule(models.Model):
    pattern = models.CharField(max_length=80, blank=False, null=False)
    type = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        default=None,
        verbose_name="Observation Type",
        choices=[(None, "Not Set")] + [(x.value, x.value.title()) for x in FrameType],
    )
    access = models.CharField(
        max_length=13,
        blank=True,
        null=True,
        default=None,
        verbose_name="Access",
        choices=[
            (None, "Not Set"),
            ("public", "Public"),
            ("all-observers", "All Observers from that night"),
            ("ownerhints", "Based on Ownerhints"),
        ],
    )
    file = models.ForeignKey(
        DBOverrideAccessFile,
        related_name="rules",
        on_delete=models.CASCADE,
        blank=False,
    )

    class Meta:
        # Make sure either type or access is set
        constraints = [
            models.CheckConstraint(
                check=models.Q(type__isnull=False) | models.Q(access__isnull=False),
                name="require_access_or_type",
                violation_error_message="Either 'Observation Type' or 'Access' must be set.",
            )
        ]

    def __str__(self):
        return f"Pattern: {self.pattern} {'' if self.type is None else 'Observation Type: ' + self.type} {'' if self.access is None else 'Access: ' + self.access}"


class DBOwnerhint(models.Model):
    ownerhint = models.CharField(max_length=150)
    rule = models.ForeignKey(
        DBOverrideAccessRule,
        related_name="ownerhints",
        on_delete=models.CASCADE,
        blank=False,
    )


@transaction.atomic
def save_oaf_to_db(override_access_file: override_access.OverrideAccessFile):

    existing_files = list(
        DBOverrideAccessFile.objects.filter(
            night=override_access_file.observing_night,
            instrument_dir=override_access_file.instrument_dir,
            sequence_id=override_access_file.sequence_id,
        ).all()
    )
    if len(existing_files) > 1:
        raise RuntimeError(
            f"Duplicate override access record found in database {existing_files[0]}"
        )
    elif len(existing_files) == 1:
        db_file = existing_files[0]
        # Clear previous rules to be replaced with new ones
        db_file.rules.all().delete()
    else:
        db_file = DBOverrideAccessFile.objects.create(
            night=override_access_file.observing_night,
            instrument_dir=override_access_file.instrument_dir,
            sequence_id=override_access_file.sequence_id,
        )

    for file_rule in override_access_file.override_rules:
        if file_rule.obstype is not None:
            DBOverrideAccessRule.objects.create(
                pattern=file_rule.pattern, type=file_rule.obstype.value, file=db_file
            )
        elif len(file_rule.ownerhints) == 0:
            raise RuntimeError(
                f"Override Access File without obstype of ownerhints provided: {db_file}"
            )
        else:
            db_rule = DBOverrideAccessRule.objects.create(
                pattern=file_rule.pattern, access="ownerhints", file=db_file
            )
            for ownerhint in file_rule.ownerhints:
                DBOwnerhint.objects.create(ownerhint=ownerhint, rule=db_rule)


def get_related_override_files(
    filepath: Path,
) -> list[override_access.OverrideAccessFile]:
    # TODO keep in here or different files?
    night, instrument_dir = parse_file_name(filepath)
    night = datetime.date.fromisoformat(night)
    converted_access_files = []
    for access_file in DBOverrideAccessFile.objects.filter(
        night=night, instrument_dir=instrument_dir
    ):
        rules = []
        for access_rule in access_file.rules.all():
            if access_rule.type is not None:
                rules.append(
                    override_access.OverrideAccessRule(
                        pattern=access_rule.pattern, obstype=FrameType(access_rule.type)
                    )
                )
            elif access_rule.access is not None:
                if access_rule.access == "ownerhints":
                    ownerhints = [oh.ownerhint for oh in access_rule.ownerhints.all()]
                else:
                    ownerhints = [access_rule.access]
                rules.append(
                    override_access.OverrideAccessRule(
                        pattern=access_rule.pattern, ownerhints=ownerhints
                    )
                )
            else:
                raise RuntimeError(
                    f"Rule with no obstype or access set for {access_file} {access_rule}"
                )

        converted_access_files.append(
            override_access.OverrideAccessFile(
                observing_night=access_file.night,
                instrument_dir=access_file.instrument_dir,
                sequence_id=access_file.sequence_id,
                override_rules=rules,
            )
        )
    return converted_access_files


def get_all_observers() -> Iterable:
    return ArchiveUser.objects.filter(obid__isnull=False)
