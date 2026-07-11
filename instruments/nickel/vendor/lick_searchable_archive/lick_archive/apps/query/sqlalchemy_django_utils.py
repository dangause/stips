"""Utilities for using the SQLAlchemy ORM with Django. These are specialized for the needs of the
lick archive and do not fully support all Django ORM operations with SQLAlchemy."""

import logging

logger = logging.getLogger(__name__)

import copy
import enum
from collections.abc import Mapping

from django.db.models import F, Q
from lick_archive.db.db_utils import execute_db_statement, open_db_session
from rest_framework.exceptions import APIException
from rest_framework.serializers import BaseSerializer, ValidationError
from sqlalchemy import func, not_, or_, select
from sqlalchemy.orm import Relationship


class SQLAlchemyORMSerializer(BaseSerializer):
    """Serializer for SQLAlchemy objects and dictionaries."""

    def _convert_orm_value(self, value):
        """Convert SQLAlchemy values into JSON suitable datatypes.
        Currently only Python enums are supported.

        Args:
        value: The value to convert.

        Return: A JSON suitable version of value.
        """
        if isinstance(value, enum.Enum):
            return value.value
        else:
            return value

    def to_representation(self, instance):
        """Converts an SQLAlchemy ORM instance into a dictionary of JSON suitable types.
            None values are ommitted from the result.

        Args:
        instance (collections.abc.Mapping):  The instance to convert. Currently only Mapping types
                                             as returned by SQLAlchemyQuerySet are supported.
        Return (dict):  A dict version of instance, using only JSON suitable types.
        """
        logger.debug("converting SQLAlchemy ORM instance")

        result = dict()

        # A mapping, convert any python/sql alchemy types that can't be mapped to JSON to a value that can
        if isinstance(instance, Mapping):
            for col_name in instance.keys():
                value = self._convert_orm_value(instance[col_name])
                if value is not None:
                    # We leave empty columns out of the dict for a cleaner output and also to skip any
                    # attributes that aren't allowed as results
                    result[col_name] = value
        else:
            # To fully SQLAlchemy we should support SQLAlchemy ORM objects, but we don't need that for the
            # lick archive
            logger.error(f"Failed to serialize {instance}")
            raise ValueError("Error serializing database results.")

        logger.debug(f"Result: {result}")
        return result


class SQLAlchemyQuerySet:
    """An implementation of the Django QuerySet API for the SQLAlchemy ORM. It only supports the subset
    of the DJango QuerySet API needed for the lick archive

    Args:
    db_engine (sqlalchemy.engine.Engine):
    The DB engine to use to connect to the database.

    sql_alchemy_table (sqlalchemy.schema.Table):
    The Table being queried (multiple tables are not currently supported).

    result_attributes (list of sqlalchemy.schema.Column):
    The result attributes to return from the query.

    where_filters (list of sqlalchemy.sql.expression.ClauseElement):
    SQLAlchemy expressions to filter the query on.

    sort_attributes (list of sqlalchemy.schema.Column):
    The attributes to sort the results of the query by.

    """

    def __init__(
        self,
        db_engine,
        sql_alchemy_table,
        result_attributes=[],
        where_filters=[],
        sort_attributes=[],
        joins=set(),
    ):
        self._db_engine = db_engine
        self._sql_alchemy_table = sql_alchemy_table

        # The SQL Alchemy attributes to return as results
        self.result_attributes = result_attributes

        # The SQL Alchemy expressions to use to filter the query results
        self.where_filters = where_filters

        # The SQL Alchemy attributes to sort the query results by
        self.sort_attributes = sort_attributes

        # The joins needed for the query
        self.joins = joins

    def _get_orm_attrib(self, name, error_field_name):
        """
        Convert a string name of an attribute into an SQL ALchemy Attribute object.

        Args:
            name (str): The name of the attribute
            error_field_name (str): The key name to use in the dict included in any exceptions.

        Return:
            (tuple[set[sqlalchemy.orm.InstrumentedAttribute],sqlalchemy.orm.InstrumentedAttribute)):
                A tuple containing a set of the joins needed to reach the attribute and
                the attribute itself.

        Raises:
            ValidationError: Thrown for unknown attribute names.
        """
        if "." in name:
            # A compound name
            attr_names = name.split(".")
        else:
            attr_names = [name]
        joins = set()
        # Start with the base table and descend down the references if this is a compound name
        table = self._sql_alchemy_table
        attr = None
        for attr_name in attr_names:
            if not hasattr(table, attr_name):
                raise ValidationError(
                    {
                        error_field_name: f"Unknown field {attr_name} in {table.__table__.name}."
                    }
                )
            attr = getattr(table, attr_name)
            # Follow relationships
            if isinstance(attr.property, Relationship):
                joins.add(attr)
                table = attr.property.entity.entity

        # The last reference should not be a table but rather the the desired attribute
        return joins, attr

    def _parse_filter_keyword_argument(self, filter):
        """Parse the Django keyword argument style of query filter into an SQLAlchemy
        expression.

        Args:
            filter (tuple): A tuple containing the keyword argument name and value.
                                For example: ('id__gt', 100)

        Return: A tuple containing a list of joins (if any) needed for the expression followed by
                An SQLAlchemy query expression.
        """
        # The expression should have a keyword argument name and a value
        if not isinstance(filter, tuple) and len(filter) != 2:
            logger.error(f"Unknown filter expression {filter}")
            raise APIException("Failed building query.")

        key, value = filter

        # Split the field and operator from the keyword argument name
        filter_expression = key.split("__")
        if len(filter_expression) == 3:
            # A table join, we only support two levels deep
            # e.g. Parent.child.attribute
            field = ".".join(filter_expression[0:2])

        elif len(filter_expression) == 2:
            field = filter_expression[0]
        else:
            logger.error(f"Unknown filter expression {key} on value {value}")
            raise APIException("Failed building query.")
        logger.debug(
            f"Adding filter {filter_expression[0]} {filter_expression[1]} {value}"
        )

        # Convert the field name to an SQLAlchemy attribute
        joins, sql_alchemy_field = self._get_orm_attrib(field, "building query")

        # Convert the operation to an SQL Alchemy expression
        op = filter_expression[-1]

        if op == "lt":
            return joins, sql_alchemy_field < value
        elif op == "lte":
            return joins, sql_alchemy_field <= value
        elif op == "gt":
            return joins, sql_alchemy_field > value
        elif op == "in":
            return joins, sql_alchemy_field.in_(value)
        elif op == "exact" or op == "iexact":
            # Look for NULL entries if the value is None or an empty string
            if value is None or (isinstance(value, str) and len(value.strip()) == 0):
                return joins, sql_alchemy_field.is_(None)
            elif op == "iexact":
                return joins, func.lower(sql_alchemy_field) == func.lower(value)
            else:
                return joins, sql_alchemy_field == value
        elif op == "startswith":
            return joins, sql_alchemy_field.startswith(value, autoescape=True)
        elif op == "istartswith":
            return joins, sql_alchemy_field.istartswith(value, autoescape=True)
        elif op == "contains":
            return joins, sql_alchemy_field.contains(value, autoescape=True)
        elif op == "icontains":
            return joins, sql_alchemy_field.icontains(value, autoescape=True)
        elif op == "range":
            return joins, sql_alchemy_field.between(value[0], value[1])
        elif op == "contained_in":
            return joins, sql_alchemy_field.op("<@")(value)
        else:
            logger.error(f"Unknown filter op {op} in key {key} on value {value}")
            raise APIException("Failed building query.")

    def _parse_q_expression(self, expression):

        # Recursively parse the child expressions
        subexpressions = []
        joins = set()

        for child in expression.children:
            if isinstance(child, tuple):
                # Not a recursive expression
                child_joins, child_expression = self._parse_filter_keyword_argument(
                    child
                )
            else:
                child_joins, child_expression = self._parse_q_expression(child)

            joins |= child_joins
            subexpressions.append(child_expression)

        if len(subexpressions) == 0:
            logger.error("Empty Q expression")
            raise APIException("Failed building query.")

        elif len(subexpressions) == 1:
            # If there's one child just return it, possibly negated
            if expression.negated:
                return joins, not_(subexpressions[0])
            else:
                return joins, subexpressions[0]

        else:
            if expression.connector != "OR":
                logger.error("Only OR is currently supported in Q expressions.")
                raise APIException("Failed building query.")
            return joins, or_(*subexpressions)

    def order_by(self, sort_fields=[]):
        """Returns a new QuerySet ordered by the given sort fields.

        Args:
        sort_fields (list of str): Optional. The fields to sort by. Defaults to an empty list.
                                   The field can be preceeded by a "-" to indicate descending order.

        Return (SQLAlchemyQuerySet): A copy of this QuerySet that sorts by sort_fields.
        """

        return_queryset = SQLAlchemyQuerySet(
            db_engine=self._db_engine,
            sql_alchemy_table=self._sql_alchemy_table,
            result_attributes=self.result_attributes,
            where_filters=self.where_filters,
            joins=self.joins,
            sort_attributes=[],
        )

        logger.debug(f"Ordering by {sort_fields}")
        if isinstance(sort_fields, str):
            sort_fields = [sort_fields]

        for sort_field in sort_fields:
            # Check for a "reverse" sort aka descending
            if sort_field.startswith("-"):
                # Descending sort
                asc = False
                sort_field = sort_field[1:]
            elif sort_field.startswith("+"):
                # Ascending sort
                asc = True
                sort_field = sort_field[1:]
            else:
                # We assume ascending sort by default
                asc = True

            joins, sort_attr = self._get_orm_attrib(sort_field, "sort")

            if asc:
                sort_attr = sort_attr.asc()
            else:
                sort_attr = sort_attr.desc()

            return_queryset.sort_attributes.append(sort_attr)
            return_queryset.joins = return_queryset.joins | joins
        return return_queryset

    @property
    def ordered(self):
        """bool: Whether the query sort is ordered, i.e. whether it has sort attributes."""
        if len(self.sort_attributes) > 0:
            return True
        else:
            return False

    def filter(self, *args, **kwargs):
        """Return a copy of this QuerySet with the passed in filters applied.

        Args:
        args (list):    Django Q expressions used for a more complex query. These are
                        AND'd alongside the other filters, although the individual expressions
                        can contain an OR.
        kwargs (dict):  This method supports a subset of the Django filter keyword arguments. Specifically
                        <field>__lt, <field>__gt, <field>__exact, <field>__startswith,
                        and <field>__range.

        Return (SQLAlchemyQuerySet): A copy of this query set with the passed in filters applied.

        Raises:
        APIException: Thrown for unsupported filter expressions or unknown fields.
        """
        return_queryset = SQLAlchemyQuerySet(
            db_engine=self._db_engine,
            sql_alchemy_table=self._sql_alchemy_table,
            result_attributes=self.result_attributes,
            where_filters=copy.copy(self.where_filters),
            sort_attributes=self.sort_attributes,
            joins=copy.copy(self.joins),
        )
        for expression in args:
            if not isinstance(expression, Q):
                logger.error(f"Unknown Q expression {expression}")
                raise APIException("Failed building query.")

            expr_joins, expr_filter = self._parse_q_expression(expression)
            return_queryset.where_filters.append(expr_filter)
            return_queryset.joins |= expr_joins

        for key, value in kwargs.items():
            filter_joins, filter = self._parse_filter_keyword_argument((key, value))
            return_queryset.where_filters.append(filter)
            return_queryset.joins |= filter_joins

        return return_queryset

    def values(self, *fields, **expressions):
        """Returns a copy of this QuerySet that only returns the specified fields and expressions.
        The resulting queryset will return results as a dict instead of an SQLAlchemy ORM object.

        Args:
        fields:  A list of the field names to return.

        expressions: A dict of the django expressions to return. Currently only F expressions are supported,
                     which allow for aliasing a column as different name in the results.

        Return (SQLAlchemyQuerySet): A copy of this QuerySet that only returns the given fields/expressions.

        Raises:
        APIException: Raised when an unsupported expression is passed in expressions.

        """
        return_queryset = SQLAlchemyQuerySet(
            db_engine=self._db_engine,
            sql_alchemy_table=self._sql_alchemy_table,
            result_attributes=[],
            where_filters=self.where_filters,
            sort_attributes=self.sort_attributes,
        )

        joins = set()
        for field in fields:
            field_joins, orm_attr = self._get_orm_attrib(field, "results")
            return_queryset.result_attributes.append(orm_attr)
            joins |= field_joins

        # Convert any Django query expressions into SQLAlchemy expressions.
        # This is a very limited converter that does only what is needed for the
        # lick archive FilesAPI. Specifically it handles field references (F), constant
        # values (Value), and a + combination of those values. This is used by
        # the FilesAPI to build the header URL.
        for expr_name in expressions:
            expression = expressions[expr_name]
            if isinstance(expression, F):
                logger.debug(f"Processing django field reference {expression.name}")
                expr_joins, expr = self._get_orm_attrib(expression.name, "results")
                return_queryset.result_attributes.append(expr.label(expr_name))
                joins |= expr_joins
            else:
                # An expression that's too complex for us
                logger.error(
                    f"Expression {expr_name} not supported. Expression value is: {expression}"
                )
                raise APIException("Internal error processing results")
        return_queryset.joins = self.joins | joins
        return return_queryset

    def __getitem__(self, key):
        """Implements indexing the queryset. This implementation does not cache results,
        and so is very inefficient. For example:

        for i in range(200):
            queryset[i]

        Re-runs the query against the database 200 times. The reason I don't cache the results is that the
        lick archive doesn't do this.

        For slicing, only a step of 1 is supported.

        Args:
        key (int or slice): The key or slice used to index the queryset

        Returns:
        Either a single item (if key is an int) or a list of items queried from the dataset.

        Raises:
        APIException: Thrown for errors building the query statement or running the query against the database.
        """
        limit = None
        slicing = False
        if isinstance(key, int):
            slicing = False
            logger.debug(f"Getting query results at index {key}")
        elif isinstance(key, slice):
            slicing = True

            # Limit the number of results based on the slice "stop" value
            if key.stop is not None:
                limit = key.stop

            if key.step is not None and key.step != 1:
                logger.error(
                    f"SQLAlchemyQuerySet does not implement step {slice.step} when slicing "
                )
                raise APIException(detail="Failed to build query archive database.")

            logger.debug(
                f"Getting {limit} query results starting at index {key.start if key.start is not None else 0}"
            )

        # Start building the SLQAlchemy query statement to be run against the database.
        try:
            # Result attributes
            if len(self.result_attributes) > 0:
                stmt = select(*self.result_attributes)
            else:
                stmt = select(self._sql_alchemy_table)

            if len(self.joins) > 0:
                logger.debug(f"SQL Before joins: {stmt.compile()}")
                # We always do outer joins now because that's correct for UserDataAccess, which
                # is the only join we need for the archive. But if other tables are added in the
                # future it might be wrong.
                for join_relationship in self.joins:
                    stmt = stmt.outerjoin(join_relationship)

            logger.debug(f"SQL Before where: {stmt.compile()}")
            # Build up the where statement, joined by ANDs
            for filter in self.where_filters:
                stmt = stmt.where(filter)
                logger.debug(f"SQL after adding where clause: {stmt.compile()}")

            # Add the order by clause
            stmt = stmt.order_by(*self.sort_attributes)

            # Add a limit for pagination
            if limit is not None:
                stmt = stmt.limit(limit)
            logger.debug(f"SQL after adding limit: {stmt.compile()}")
        except Exception as e:
            logger.error(f"Error when building query: {e}", exc_info=True)
            raise APIException(detail="Failed to build query.")

        # Run the statement
        try:
            with open_db_session(self._db_engine) as session:
                rows = execute_db_statement(session, stmt).all()
        except Exception as e:
            logger.error(f"Failed to run archive database query: {e}", exc_info=True)
            raise APIException(detail="Failed to query archive database.")

        if len(self.result_attributes) == 0:
            # Return the SQLAlchemy mapped object if there were no result attributes
            if slicing:
                return [row[0] for row in rows[key]]
            else:
                return rows[key][0]
        else:
            # Otherwise return as a dict as per the "values" API in QuerySet
            if slicing:
                return [row._mapping for row in rows[key]]
            else:
                return rows[key]._mapping

    def count(self):
        """Immediately execute a count on the database and return the results

        Return (int): The count returned from the database.

        Raises:
        APIException: Thrown for errors building the query statement or running the query against the database.
        """
        try:
            # Build the count statement
            stmt = select(func.count())

            if len(self.joins) > 0:
                logger.debug(f"SQL Before joins: {stmt.compile()}")
                for join_relationship in self.joins:
                    stmt = stmt.outerjoin(join_relationship)

            logger.debug(f"SQL Before where: {stmt.compile()}")

            if len(self.where_filters) == 0:
                # SQL Alchemy can't infer the table if there are no filters.
                stmt = stmt.select_from(self._sql_alchemy_table)
            else:
                # Build up the where statement, joined by ANDs
                for filter in self.where_filters:
                    stmt = stmt.where(filter)
            logger.debug(f"SQL after adding where clause: {stmt.compile()}")
        except Exception as e:
            logger.error(f"Error when building count query: {e}", exc_info=True)
            raise APIException(detail="Failed to build count query.")

        # Run the count statement
        try:
            with open_db_session(self._db_engine) as session:
                result = execute_db_statement(session, stmt).scalar()
                return result
        except Exception as e:
            logger.error(
                f"Failed to run archive database count query: {e}", exc_info=True
            )
            raise APIException(detail="Failed to run count query on archive database.")
