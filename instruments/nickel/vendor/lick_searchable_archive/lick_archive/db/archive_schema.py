"""Defines the schema used to store metadata for the Lick Archive.
Uses SQL Alchemy's ORM
"""

from datetime import date, datetime
from enum import Enum as PythonEnum
from typing import List

from astropy.coordinates import SkyCoord
from lick_archive.db.bitstring import BitString
from lick_archive.db.pgsphere import SPoint
from lick_archive.metadata.data_dictionary import (
    MAX_PUBLIC_DATE,
    IngestFlags,
    LargeInt,
    LargeStr,
    data_dictionary,
)
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Column,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy import Enum as SqlAlchemyEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship


class Base(DeclarativeBase):
    pass


# We build the FileMetadata table using SQL Alchemy's Core API so we can build it from the data dictionary

_primary_key = "id"
_unique = ["filename"]
_required = [
    "id",
    "filename",
    "telescope",
    "instrument",
    "obs_date",
    "frame_type",
    "public_date",
]

# Define a default publication date far into the future, for help migrating existing data without a date
_defaults = {"public_date": MAX_PUBLIC_DATE.isoformat()}


def _map_type(python_type):
    type_map = {
        int: Integer,
        str: String,
        float: Float,
        datetime: TIMESTAMP(timezone=True),
        date: Date,
        SkyCoord: SPoint,
        IngestFlags: BitString,
        LargeInt: BigInteger,
        LargeStr: Text,
    }

    if python_type in type_map:
        return type_map[python_type]
    elif issubclass(python_type, PythonEnum):
        return SqlAlchemyEnum(
            python_type, values_callable=lambda x: [y.value for y in x]
        )
    else:
        raise NotImplementedError(
            f"Python type {python_type} not supported when mapping to SQLAlchemy"
        )


main_columns = [
    Column(
        dd_row["db_name"],
        _map_type(dd_row["type"]),
        primary_key=True if dd_row["db_name"] in _primary_key else None,
        unique=True if dd_row["db_name"] in _unique else None,
        nullable=False if dd_row["db_name"] in _required else True,
        server_default=_defaults.get(dd_row["db_name"], None),
    )
    for dd_row in data_dictionary
]
file_metadata = Table("file_metadata", Base.metadata, *main_columns)


class FileMetadata(Base):
    __table__ = file_metadata
    user_access: Mapped[List["UserDataAccess"]] = relationship(
        back_populates="file_metadata", cascade="all, delete-orphan"
    )


Index("index_m_obs_date", FileMetadata.obs_date)
Index("index_m_instrument", FileMetadata.instrument)
Index("index_m_object", FileMetadata.object)
Index("index_m_frame", FileMetadata.frame_type)
Index("index_m_coord", FileMetadata.coord, postgresql_using="gist")


class UserDataAccess(Base):
    __tablename__ = "user_data_access"

    file_id = Column(ForeignKey("file_metadata.id"), primary_key=True)
    obid = Column(Integer, primary_key=True)
    reason = Column(Text)

    file_metadata: Mapped[FileMetadata] = relationship(
        back_populates="user_access", cascade="all"
    )
