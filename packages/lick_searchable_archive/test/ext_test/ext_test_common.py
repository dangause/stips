TEST_USER = "test_user"
TEST_USER_OWNERHINT = "test user.testing user"
PUBLIC_FILE = "2019-05/23/shane/r33.fits"
PRIVATE_FILE = "2025-01/27/AO/s1000.fits"


def enable_user(user_name):
    from lick_archive.apps.archive_auth.models import ArchiveUser

    test_user = ArchiveUser.objects.filter(username=user_name)[0]
    test_user.is_active = True
    test_user.save()


def disable_user(user_name):
    from lick_archive.apps.archive_auth.models import ArchiveUser

    test_user = ArchiveUser.objects.filter(username=user_name)[0]
    test_user.is_active = False
    test_user.save()


def get_obid(user_name):
    from lick_archive.apps.archive_auth.models import ArchiveUser

    user = ArchiveUser.objects.filter(username=user_name)[0]
    return user.obid


def get_file_metadata(session, full_filename):
    from datetime import date

    from lick_archive.db import db_utils
    from lick_archive.db.archive_schema import FileMetadata
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    metadata = db_utils.find_file_metadata(
        session,
        select(FileMetadata)
        .options(selectinload(FileMetadata.user_access))
        .where(FileMetadata.filename == full_filename),
    )
    if metadata is not None:
        if metadata.public_date <= date.today():
            raise ValueError(
                "Error, propreitary file is no longer proprietary, you need to update these tests to use a new file."
            )

        return metadata
    else:
        raise (f"Error, could not find {full_filename}")


def add_user_access(filename, user):

    from lick_archive.db import db_utils
    from lick_archive.db.archive_schema import UserDataAccess

    engine = db_utils.create_db_engine()
    with db_utils.open_db_session(engine) as session:

        metadata = get_file_metadata(session, filename)
        obid = get_obid(user)
        access_list = []
        for uda in metadata.user_access:
            if uda.obid == obid:
                # Nothing to do
                return
            else:
                access_list.append(uda)

        access_list.append(
            UserDataAccess(file_id=metadata.id, obid=obid, reason="Added for testing")
        )

        db_utils.update_file_metadata(
            session=session, id=metadata.id, row=metadata, user_access=access_list
        )
        session.commit()


def remove_user_access(filename, user):

    from lick_archive.db import db_utils

    engine = db_utils.create_db_engine()
    with db_utils.open_db_session(engine) as session:
        metadata = get_file_metadata(session, filename)
        obid = get_obid(user)
        access_list = []
        for uda in metadata.user_access:
            if uda.obid != obid:
                # Don't remove this observer id
                access_list.append(uda)

        db_utils.update_file_metadata(
            session=session, id=metadata.id, row=metadata, user_access=access_list
        )
        session.commit()


def add_override_access(override_date, override_instr, user_ownerhint, filename):
    from lick_archive.apps.archive_auth.models import DBOverrideAccessFile

    db_oafs = list(
        DBOverrideAccessFile.objects.filter(
            night=override_date, instrument_dir=override_instr
        ).order_by("-sequence_id")
    )
    if len(db_oafs) > 0:
        oaf = db_oafs[0]
    else:
        # Make oaf
        oaf = DBOverrideAccessFile(
            night=override_date, instrument_dir=override_instr, sequence_id=0
        )
        oaf.save()

    oaf_rules = list(oaf.rules.filter(pattern=filename, access="ownerhints"))
    if len(oaf_rules) == 0:
        oaf_rule = oaf.rules.create(pattern=filename, access="ownerhints")
    else:
        oaf_rule = oaf_rules[0]

    db_ownerhints = list(oaf_rule.ownerhints.filter(ownerhint=user_ownerhint))
    if len(db_ownerhints) == 0:
        oaf_rule.ownerhints.create(ownerhint=user_ownerhint)


def remove_override_access(override_date, override_instr, user_ownerhint, filename):
    from lick_archive.apps.archive_auth.models import (
        DBOverrideAccessFile,
    )

    db_oafs = list(
        DBOverrideAccessFile.objects.filter(
            night=override_date, instrument_dir=override_instr
        ).order_by("-sequence_id")
    )
    if len(db_oafs) > 0:
        oaf = db_oafs[0]

        oaf_rules = list(oaf.rules.filter(pattern=filename, access="ownerhints"))
        if len(oaf_rules) > 0:
            for oaf_rule in oaf_rules:
                oaf_rule.ownerhints.filter(ownerhint=user_ownerhint).delete()
                if oaf_rule.ownerhints.count() == 0:
                    oaf_rule.delete()
        if oaf.rules.count() == 0:
            oaf.delete()


def replace_parsed_url_hostname(parsed_url, hostname):
    if parsed_url.port is not None:
        port = f":{parsed_url.port}"
    else:
        port = ""

    return parsed_url._replace(netloc=f"{hostname}{port}").geturl()
