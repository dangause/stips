import configparser
import contextlib

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker

basic_django_setup = pytest.mark.usefixtures("archive_config", "django_log_to_tmp_path")
django_db_setup = pytest.mark.usefixtures(
    "archive_config", "django_log_to_tmp_path", "django_db"
)


def MockDatabase(base_class, rows=None):

    # This functions wraps a MockDatabaseClass so that the below imports
    # aren't made until after the archive configuration is set
    from lick_archive.db.archive_schema import FileMetadata, UserDataAccess

    class MockDatabaseClass(contextlib.AbstractContextManager):

        def __init__(self, base_class, rows=None):

            self.base_class = base_class

            # Create an in memory engine
            self.engine = create_engine("sqlite://")

            # Create the schema
            self.base_class.metadata.create_all(self.engine)

            # Insert any rows.
            if rows is not None:
                # Session for inserting rows
                self.Session = sessionmaker(bind=self.engine)
                session = self.Session()

                # Because sqllite doesn't support SPoint, we directly insert
                # without id and coord, and then insert any UserDataAccess entires separately
                columns_to_insert = [
                    c.name
                    for c in FileMetadata.__table__.c
                    if c.name not in ("id", "coord")
                ]
                fm_insert_stmt = insert(FileMetadata).returning(FileMetadata.id)
                uda_insert_stmt = insert(UserDataAccess)
                for row in rows:
                    values = {col: getattr(row, col) for col in columns_to_insert}
                    result_id = session.execute(fm_insert_stmt, values).scalar_one()
                    uda_values = [
                        {"file_id": result_id, "obid": uda.obid, "reason": uda.reason}
                        for uda in row.user_access
                    ]
                    if len(uda_values) > 0:
                        session.execute(uda_insert_stmt, uda_values)
                session.commit()
                session.close()

        def __exit__(self, exc_type, exc_value, traceback):
            self.base_class.metadata.drop_all(self.engine)
            return False

    return MockDatabaseClass(base_class, rows)


def create_mock_view(engine, request=None):

    # We define the view in a function so the below imports happen after Django is initialized by the test case
    from lick_archive.apps.query.api import SQLAlchemyORMSerializer, SQLAlchemyQuerySet
    from lick_archive.apps.query.views import (
        QueryAPIFilterBackend,
        QueryAPIPagination,
        QueryView,
    )
    from lick_archive.db.archive_schema import FileMetadata
    from lick_archive.metadata.data_dictionary import api_capabilities

    class MockView(QueryView):
        """A test view for testing the query api"""

        pagination_class = QueryAPIPagination
        filter_backends = [QueryAPIFilterBackend]
        serializer_class = SQLAlchemyORMSerializer
        allowed_sort_attributes = ["id", "filename", "object", "obs_date"]
        allowed_result_attributes = [
            "filename",
            "obs_date",
            "object",
            "frame_type",
            "header",
            "download_link",
        ]
        required_attributes = list(api_capabilities["required"]["db_name"])
        serializer_class = SQLAlchemyORMSerializer

        def __init__(self, engine, request=None):
            self.engine = engine
            self.request = request
            self.format_kwarg = "json"

        def get_queryset(self):
            return SQLAlchemyQuerySet(self.engine, FileMetadata)

    return MockView(engine, request)


# Helper to create a request for testing
def create_test_request(path, data, user=None, obid=None, is_superuser=None):
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    request_factory = APIRequestFactory()
    request = Request(request_factory.get(path, data=data))

    if user is not None:
        from lick_archive.apps.archive_auth.models import ArchiveUser

        user_object = ArchiveUser(
            username=user,
            obid=obid,
            email=user + "@example.org",
            is_superuser=is_superuser,
        )
        request.user = user_object

    return request


# Helper to validate a test request to build the needed "validated_query" request attribute
def create_validated_request(path, data, view):
    request = create_test_request(path, data)

    from lick_archive.apps.query.query_api import QuerySerializer

    serializer = QuerySerializer(data=request.query_params, view=view)
    try:
        serializer.is_valid(raise_exception=True)
    except Exception:
        raise

    # Store the validated results in the request to be passed to paginators and filters
    request.validated_query = serializer.validated_data
    return request


class mock_external_schedule:
    schedconfig = configparser.ConfigParser()

    def ownercompute(*args, **kwargs):
        pass
