"""Adds SQL Alchemy and psycopg2 support for the pgsphere custom data type.
This datatype allows sptial index support for RA/DEC cone searches.
"""

import logging
import math

import astropy.units
from astropy.coordinates import Angle
from sqlalchemy import func
from sqlalchemy.types import UserDefinedType

logger = logging.getLogger(__name__)


class SPoint(UserDefinedType):
    """SQLAlchemy user defined type for the pgsphere SPoint datatype. This
    type allows for spherical coordinates.
    """

    # Stop SQLAlchemy from complaining about cache_ok being None.
    # At one point we tried setting this to true but it got confused
    # about the identity between SCircle's with different radiuses,
    # So we disable it for both SPoint and SCircle now
    cache_ok = False

    def __init__(self, ra=None, dec=None, **kwargs):
        """Initialize the SPoint given ra and dec values.

        Args:
            ra (str or float): The RA value in decimal degrees
            dec (str or float): The dec value in decimal degrees
        """
        super().__init__(**kwargs)
        self.ra = None
        self.dec = None
        if ra is not None and dec is not None:
            try:
                self.ra, self.dec = SPoint.convert(ra, dec)
            except Exception as e:
                if isinstance(ra, str) and isinstance(dec, str):
                    # Try sexagesimal
                    try:
                        decimal_ra = self.convert_sexagesimal(ra, hours=True)
                        decimal_dec = self.convert_sexagesimal(dec)

                        self.ra, self.dec = SPoint.convert(decimal_ra, decimal_dec)
                    except Exception as e:
                        logger.error(
                            f"Could not convert RA/DEC {ra}/{dec} to an SPoint: {e}",
                            exc_info=True,
                        )
                else:
                    logger.error(
                        f"Could not convert RA/DEC {ra}/{dec} to an SPoint: {e}",
                        exc_info=True,
                    )

    @classmethod
    def convert(cls, ra, dec):
        """Convert ra/dec in decimal degrees to radians for use with pgsphere.
        Args:
            ra  (float or str): A right asscension in [+|-]DDD.DDD format.
            dec (float or str str): A declination in [+|-]DDD.DDD format. This must be between -90.0 and +90.0

        Returns (str):  The coordinates converted to floating point raidians, as used by the pgsphere plugin for PostgreSQL.

        Raises: (ValueError, TypeError) - Raised if the values cannot be converted to a valid spoint.
        """
        ra = float(ra)
        dec = float(dec)

        if dec < -90.0 or dec > 90.0:
            raise ValueError(f"Declination {dec} must be >= -90 and <= 90.")

        return ra * math.pi / 180.0, dec * math.pi / 180.0

    @classmethod
    def convert_sexagesimal(cls, value, hours=False):
        """Convert a sexagesimal angle to a floating point value in radians.
        Args:
            value (str):  A sexigesimal value
            hours (bool): True if value is an hour angle, false if it is in degrees. If the value
                          passed in is explicity in degrees (e.g."3d1m0s"), it will be treated as
                          degrees.

        Returns (float): - The value converted to a floating point value, or None if value was None.

        Raises (ValueError): - Raised if value could not be converted
        """

        if value is None:
            return None

        if hours is False or any([c in "hdms" for c in value.lower()]):
            # It either should be in degrees, or is explicitly giving its units
            # Use Astropy Angle to convert it to degrees.
            # Astropy Angle will also deal with weird coordinates, like 60 as the seconds
            angle = Angle(value, unit=astropy.units.deg)
        else:
            # It doesn't specify units, and should be in hours
            # Parse the angle as a hour angle, and covnert it to degrees
            angle = Angle(Angle(value, unit=astropy.units.hourangle), astropy.units.deg)

        return angle.value

    def coerce_compared_value(self, op, value):
        """Coerce the type of a value that is being compared against an SPoint.
        This overrides the method in TypeEngine to make sure that SCircles are
        left alone when compared with SPoints.

        Args:
            op    (OperatorType): The operator being used (not used)
            value (Any):          The value being compared with.

        Return (TypeEngine): The type to coerce the value to.
        """
        if isinstance(value, SCircle):
            result = SCircle()
        else:
            result = super().coerce_compared_value(op, value)

        logger.debug(
            f"point coerce op: {op} value: {value} self: {self} result: {result}"
        )
        return result

    def bind_expression(self, bindvalue):
        """Create the bind expression used for bound parameters in an SQLAlchemy statement.
        This overrides the TypeEngine implementation to wrap SPoint ra/dec in the "spoint"
        constructor from pgsphere.

        Args:
            bindvalue (BindParameter): The value being bound to the parameter.

        Return (Function): The parameter wrapped in a "spoint" function.
        """
        value = bindvalue.effective_value
        logger.debug(
            f"SPoint bindparam value: {value} type: {bindvalue.type} self: {self}"
        )
        if isinstance(value, SPoint) and value.ra is not None and value.dec is not None:
            return func.spoint(value.ra, value.dec)
        return func.spoint(bindvalue)

    def get_col_spec(self):
        """Return the type used in DDL to specify a column of this type.
        This overrides the UserDefinedType implementation.""

        Return (str): The column type for SPoint.
        """
        return "SPOINT"

    def __str__(self):
        """Create a string representaiton for displaying the SPoint."""
        if self.ra is None and self.dec is None:
            return "SPoint()"
        else:
            return f"SPoint({self.ra*180.0/math.pi:.6f},{self.dec*180.0/math.pi:.6f})"

    def literal_value(self):
        """Create a literal string representation for this SPoint in SQL. The
        caller is expected to wrap this in "spoint()" in SQL.

        Return (str): The literal representation for the SPoint.
        """
        return f"{self.ra},{self.dec}"

    def literal_processor(self, dialect):
        """Return a function to convert an SPoint to it's literal value.
        This overrides the TypeEngine implementation.

        Args:
            dialect (Dialect): The dialect object for the database being used.

        Return (Callable): A function that calls literal_value on an SPoint type."""

        def processor(value):
            return value.literal_value()

        return processor

    @staticmethod
    def process_result_value(value):
        """Function to process SPoint values returned from the database into
        SPoint objects.

        Args: value (str): The value returned from the database.

        Return (SPoint): The SPoint object converted from the result value.
        """
        # SPoint values are typically returned as "(x.xxx, y.yyy)"
        if value is None or len(value.strip("()")) == 0:
            return None
        ra, dec = value.strip("()").split(",")
        # The value is already in radians, so don't use the SPoint constructor
        # since it expects decimal degrees.
        point = SPoint()
        point.ra = float(ra)
        point.dec = float(dec)
        return point

    def result_processor(self, dialect, coltype):
        """Return a function to process SPoint values returned from the database.
        This overrides the TypeEngine implementation.

        Args:
            dialect (Dialect):    The dialect being used.
            coltype (TypeEngine): The type of the database column

        Return (Callable): A function to parse SPoint values from the database into
        SPoint objects
        """
        return SPoint.process_result_value


class SCircle(UserDefinedType):
    """SQLAlchemy user defined type for the pgsphere SCircle datatype. This
    type allows for spherical coordinates.
    """

    cache_ok = False

    def __init__(self, center=None, radius=None):
        """Construct a circle in spherical coordinates.
        Args:
            center  (SkyCoord): An Astropy SkyCoord representing the ra/dec of the center.
            radius (Angle):     An Astropy Angle representing the angular radius of the circle.

        """
        self.ra = None
        self.dec = None
        self.radius = None
        if center is not None:
            # Convert incomming values to radians for pgsphere
            self.ra = Angle(center.ra, unit=astropy.units.rad)
            self.dec = Angle(center.dec, unit=astropy.units.rad)

        if radius is not None:
            self.radius = Angle(radius, unit=astropy.units.rad)

    def get_col_spec(self):
        """Return the type used in DDL to specify a column of this type.
        This overrides the UserDefinedType implementation.""

        Return (str): The column type for SPoint.
        """
        return "SCIRCLE"

    def bind_expression(self, bindvalue):
        """Create the bind expression used for bound parameters in an SQLAlchemy statement.
        This overrides the TypeEngine implementation to wrap SPoint ra/dec in the "scircle"
        constructor from pgsphere.

        Args:
            bindvalue (BindParameter): The value being bound to the parameter.

        Return (Function): The parameter wrapped in a "scircle" function.
        """
        value = bindvalue.effective_value
        logger.debug(
            f"SCircle bindparam value: {value} type: {bindvalue.type} self: {self}"
        )
        return func.scircle(bindvalue)

    def __str__(self):
        """Create a string representaiton for displaying the SCircle."""
        if self.ra is None and self.dec is None and self.radius is None:
            return "SCircle()"
        else:
            deg_ra = self.ra.to_string(
                decimal=True, unit=astropy.units.deg, precision=6
            )
            deg_dec = self.dec.to_string(
                decimal=True, unit=astropy.units.deg, precision=6
            )
            deg_radius = self.radius.to_string(
                decimal=True, unit=astropy.units.deg, precision=6
            )
            return f"SCircle(({deg_ra},{deg_dec}),{deg_radius})"

    def literal_value(self):
        """Create a literal string representation for this SCircle in SQL. The
        caller is expected to wrap this in "scircle()" in SQL.

        Return (str): The literal representation for the SCircle.
        """
        return f"spoint({self.ra.value},{self.dec.value}),{self.radius.value}"

    def literal_processor(self, dialect):
        """Return a function to convert an SCircle to it's literal value.
        This overrides the TypeEngine implementation.

        Args:
            dialect (Dialect): The dialect object for the database being used.

        Return (Callable): A function that calls literal_value on an SCircle type."""

        def processor(value):
            return value.literal_value()

        return processor

    @staticmethod
    def process_result_value(value):
        """Function to process scircle values returned from the database into
        SCircle objects.

        Args: value (str): The value returned from the database.

        Return (SCircle): The object converted from the result value.
        """
        # The result string returned from the database is in the format:
        # < (center ra, center dec), radius >
        if value is None or len(value.strip("<>")) == 0:
            return None
        value = value.strip("<>").replace("(", "").replace(")", "")
        ra, dec, radius = value.split(",")

        # The values returned are already in radians, so don't convert
        # with the SCircle constructor
        result = SCircle()
        result.ra = Angle(ra, unit=astropy.units.rad)
        result.dec = Angle(dec, unit=astropy.units.rad)
        result.radius = Angle(radius, unit=astropy.units.rad)
        return result

    def result_processor(self, dialect, coltype):
        """Return a function to process SCircle values returned from the database.
        This overrides the TypeEngine implementation.

        Args:
            dialect (Dialect):    The dialect being used.
            coltype (TypeEngine): The type of the database column

        Return (Callable): A function to parse scirlce values from the database into
        SCircle objects
        """
        return SCircle.process_result_value


# Register custom types with the psycopg2 DBAPI driver it is' installed
try:
    from psycopg2.extensions import AsIs, register_adapter

    def adapt_spoint_for_postgresql(spoint):
        asis_value = AsIs(spoint.literal_value())
        logger.debug(f"spoint quoted value: {asis_value.getquoted()}")
        return asis_value

    register_adapter(SPoint, adapt_spoint_for_postgresql)

    def adapt_scircle_for_postgresql(scircle):
        asis_value = AsIs(scircle.literal_value())
        logger.debug(f"scircle quoted value: {asis_value.getquoted()}")
        return asis_value

    register_adapter(SCircle, adapt_scircle_for_postgresql)

except Exception:
    pass
