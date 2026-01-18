from sqlalchemy.dialects.postgresql import BIT
from sqlalchemy.types import CHAR, TypeDecorator


class BitString(TypeDecorator):
    """Platform independent bit string type, using SQLAlchemy's TypeDecorator.
    This is used for unit testing, to allow the sqlite3 unit tests to use the
    postgres BIT type.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        """Load the implementation for a specific dialect. Currenlty only
        PostgreSQL's BIT type is supported, other platforms use a character string.

        Args: dialect: The dialect (i.e. database) being used.

        """
        if dialect.name == "postgresql":
            return dialect.type_descriptor(BIT(32))
        else:
            return dialect.type_descriptor(CHAR(32))
