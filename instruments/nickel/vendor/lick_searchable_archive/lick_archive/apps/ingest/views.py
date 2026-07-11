# ruff: noqa: E402
import logging

logger = logging.getLogger(__name__)


from lick_archive.config.archive_config import ArchiveConfigFile
from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from sqlalchemy import func, select

from .models import IngestCount
from .serializers import IngestCountsSerializer, IngestNotificationSerializer
from .tasks import ingest_new_files

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config
from lick_archive.db import db_utils
from lick_archive.db.archive_schema import FileMetadata
from lick_archive.utils.django_utils import log_request_debug

# SQLAlchemy likes its engine to have a global lifetime.
_db_engine = db_utils.create_db_engine(
    user=lick_archive_config.database.db_query_user,
    database=lick_archive_config.database.archive_db,
)


class IngestNotifications(generics.CreateAPIView):
    serializer_class = IngestNotificationSerializer

    def create(self, request, *args, **kwargs):
        log_request_debug(request)
        serializer = self.get_serializer(
            data=request.data, many=isinstance(request.data, list)
        )
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        logger.info(repr(serializer))
        # Create celery tasks to ingest the metadata
        if isinstance(serializer.validated_data, list):
            ingests = serializer.validated_data
        else:
            ingests = [serializer.validated_data]

        ingest_new_files.s(ingests).apply_async()

        headers = self.get_success_headers(serializer.validated_data)
        return Response(
            serializer.validated_data, status=status.HTTP_201_CREATED, headers=headers
        )


class IngestCounts(generics.RetrieveAPIView):
    serializer_class = IngestCountsSerializer

    def get_object(self):
        """Returns a count object containing the number of files in an archive ingest path.
        Overrides the version from :class:`rest_framework.generics.GenericAPIView` to
        directly query the SQLAlchemy managed metadata database.
        """
        log_request_debug(self.request)

        # The django URL dispatcher should pass this through to the GenericAPIView get() method
        ingest_path = self.kwargs.get("ingest_path", "")
        if len(ingest_path) == 0:
            logger.error("Recieved empty ingest_path.")
            raise APIException(
                detail="Recieved empty ingest_path", status=status.HTTP_400_BAD_REQUEST
            )
        else:
            count = self.get_ingest_counts(ingest_path)
        return IngestCount(ingest_path=ingest_path, count=count)

    def get_ingest_counts(self, ingest_path: str) -> int:
        """Count the number of ingested files in a path"""
        stmt = select(func.count()).where(
            FileMetadata.filename.startswith(ingest_path, autoescape=True)
        )

        try:
            with db_utils.open_db_session(_db_engine) as session:
                result = db_utils.execute_db_statement(session, stmt).scalar()
                return result
        except Exception as e:
            logger.error(
                f"Failed to run archive ingest count query: {e}", exc_info=True
            )
            raise APIException(detail="Failed to run count query on archive database.")
