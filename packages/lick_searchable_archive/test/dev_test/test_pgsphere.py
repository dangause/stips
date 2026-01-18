from lick_archive.archive_config import ArchiveConfigFile

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


def test_spoint_select():
    """Test generating select statements using SPoint"""
    from lick_archive.db.archive_schema import FileMetadata
    from lick_archive.db.pgsphere import SPoint
    from sqlalchemy import select

    p = SPoint(45.5, 45.5)
    stmt = select(FileMetadata).where(FileMetadata.coord == p)
    s = str(stmt)
    assert "coord = spoint(:spoint_1, :spoint_2)" in s

    s = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "coord = spoint(0.7941248096574199,0.7941248096574199)"

    from lick_archive.db import db_utils

    engine = db_utils.create_db_engine()
    session = db_utils.open_db_session(engine)
    results = session.execute(stmt).all()


def test_spoint_insert_result_delete():
    """Test inserting an SPoint, retrieving it from the database,
    and deleting it."""
    from lick_archive.data_dictionary import FrameType
    from lick_archive.db import db_utils
    from lick_archive.db.archive_schema import FileMetadata
    from lick_archive.db.pgsphere import SPoint
    from sqlalchemy import delete, select

    engine = db_utils.create_db_engine()
    session = db_utils.open_db_session(engine)
    p = SPoint(45.5, 45.5)

    # Delete any rows prior to re-adding them
    del_stmt = delete(FileMetadata).where(
        FileMetadata.coord == p,
        FileMetadata.filename == "data/2023-09/26/shane/dev_test.fits",
    )
    session.execute(del_stmt)
    session.commit()
    # Add a test row
    test_row = FileMetadata(
        telescope="Shane",
        instrument="Kast Blue",
        obs_date="2023-09-26 12:00:00",
        frame_type=FrameType.unknown,
        filename="data/2023-09/26/shane/dev_test.fits",
        ingest_flags="00000000000000000000000000000001",
        coord=p,
    )

    session.add(test_row)
    session.commit()

    # Test returning an SPoint from a select
    stmt2 = select(FileMetadata.id, FileMetadata.filename, FileMetadata.coord).where(
        FileMetadata.coord == p,
        FileMetadata.filename == "data/2023-09/26/shane/dev_test.fits",
    )
    results = session.execute(stmt2).all()
    assert len(results) == 1
    assert isinstance(results[0][2], SPoint)
    assert round(results[0][2].ra, 8) == round(p.ra, 8)
    assert round(results[0][2].dec, 8) == round(p.dec, 8)

    result = session.execute(del_stmt)
    session.commit()
    assert result.rowcount == 1


def test_cone_search():
    """Test a cone search for known Feige110 data."""
    import os
    from pathlib import Path

    from astropy.coordinates import Angle, SkyCoord
    from lick_archive.data_dictionary import Instrument
    from lick_archive.db import db_utils
    from lick_archive.db.archive_schema import FileMetadata
    from lick_archive.db.pgsphere import SCircle
    from sqlalchemy import select

    os.environ["DJANGO_SETTINGS_MODULE"] = (
        "lick_searchable_archive.lick_searchable_archive.settings"
    )

    engine = db_utils.create_db_engine()
    session = db_utils.open_db_session(engine)

    c = SCircle(
        center=SkyCoord(ra=349.9933320184400, dec=-05.1656030952400, unit="deg"),
        radius=Angle("1 arcmin"),
    )
    stmt3 = select(FileMetadata).where(
        FileMetadata.coord.op("<@")(c),
        FileMetadata.instrument.in_([Instrument.KAST_RED, Instrument.KAST_BLUE]),
    )
    # Make sure the SCircle converts to SQL correctly
    assert (
        "scircle(spoint(6.108536003747469,-0.09015678186314822),0.0002908882086657216)"
        in str(stmt3.compile(compile_kwargs={"literal_binds": True}))
    )

    results = session.execute(stmt3).all()
    assert len(results) == 2
    files = [
        Path(result[0].filename).relative_to(
            lick_archive_config.ingest.archive_root_dir
        )
        for result in results
    ]
    assert Path("2019-05/24/shane/b27.fits") in files
    assert Path("2019-05/24/shane/r102.fits") in files


def test_spoint_ddl_gen():
    """Test DDL generates the SPOINT column correctly"""
    from lick_archive.db import db_utils
    from lick_archive.db.archive_schema import FileMetadata
    from sqlalchemy.schema import CreateTable

    engine = db_utils.create_db_engine()

    assert "SPOINT" in str(CreateTable(FileMetadata.__table__).compile(engine))
