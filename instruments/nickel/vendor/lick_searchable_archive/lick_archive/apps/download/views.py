"""The views that make up the lick archive query app."""

# ruff: noqa: E402
import logging

logger = logging.getLogger(__name__)

from pathlib import Path

from django.http import FileResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db.archive_schema import FileMetadata
from lick_archive.db.db_utils import create_db_engine
from lick_archive.metadata.metadata_utils import parse_file_name
from lick_archive.utils.django_utils import log_request_debug
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound, ParseError
from rest_framework.generics import GenericAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, JSONParser

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

from lick_archive.apps.download.tarfile_stream import TarFileStream
from lick_archive.apps.query.api import QueryAPIFilterBackend, QueryAPIView
from lick_archive.metadata.data_dictionary import MAX_FILENAME_BATCH, MAX_FILENAME_SIZE

# SQLAlchemy likes its engine to have a global lifetime.
_db_engine = create_db_engine(
    user=lick_archive_config.database.db_query_user,
    database=lick_archive_config.database.archive_db,
)


class DownloadSingleView(QueryAPIView, RetrieveAPIView):
    """A view for getting the header for a specific fits file in the archive."""

    filter_backends = [QueryAPIFilterBackend]
    lookup_url_kwarg = "file"
    lookup_field = "filename"
    required_attributes = ["filename"]
    allowed_result_attributes = ["filename", "instrument"]
    allowed_sort_attributes = ["id"]
    throttle_scope = "downloads"

    def __init__(self):
        super().__init__(_db_engine, FileMetadata)

    def retrieve(self, request, *args, **kwargs):
        log_request_debug(request)

        file_metadata = super().get_object()
        logger.debug(f"Using X-SendFile value of '{file_metadata.filename}'")
        xsendfile_headers = {
            "X-Sendfile": file_metadata.filename,
            "Content-Type": lick_archive_config.download.file_types[
                file_metadata["instrument"]
            ],
        }
        response = FileResponse()
        response.status_code = status.HTTP_200_OK
        response.headers = xsendfile_headers
        return response


class DownloadMultiSerializer(serializers.Serializer):
    download_files = serializers.JSONField()


class DownloadMultiView(QueryAPIView, GenericAPIView):
    """A view for downloading a tarball of multiple files in the archive."""

    filter_backends = [QueryAPIFilterBackend]
    required_attributes = ["filename"]
    allowed_result_attributes = ["filename", "file_size"]
    allowed_sort_attributes = ["filename"]
    batch_size = MAX_FILENAME_BATCH
    parser_classes = [JSONParser, FormParser]
    serializer_class = DownloadMultiSerializer
    throttle_scope = "downloads"

    def __init__(self):
        super().__init__(_db_engine, FileMetadata)

    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        """Handle a post request to download files. The API expects a JSON list
        of archive filenames."""

        log_request_debug(request)
        logger.debug(f"Request data: {request.data}")
        logger.info("Received download request.")
        # Valiadate the incomming request.
        file_list = self._validate_json(request)
        logger.info(f"Request contained {len(file_list)} files.")
        # Validate that the the files in request, and return their full paths.
        valid_files = self._get_validated_files(file_list)
        archive_names = self._get_archive_names(valid_files)
        tarfile_name = self.get_filename(valid_files[0], valid_files[-1])
        logger.info(
            f"Validated {len(valid_files)} files for download, starting tarball stream..."
        )
        tarball_stream = TarFileStream(
            tarfile_name, valid_files, arcfiles=archive_names, enable_gzip=True
        )

        headers = {
            "Content-Type": "application/gzip",
            "Content-Disposition": f"attachment; filename={tarfile_name}",
        }
        return StreamingHttpResponse(
            streaming_content=tarball_stream, status=status.HTTP_200_OK, headers=headers
        )

    def get_filename(self, first_file: Path, last_file: Path):
        """Create the filename to use for the tarball.

        Args:
        first_file: The first file in the sorted list of filenames.
        last_file:   The last file in the sorted list of filenames.
        """

        date1, instr1 = parse_file_name(first_file)
        date2, instr2 = parse_file_name(last_file)

        if date1 == date2:
            date_portion = date1
        else:
            date_portion = date1 + "-" + date2

        if instr1 == instr2:
            instr_portion = instr1
        else:
            instr_portion = instr1 + "-" + instr2
        return f"data-{date_portion}-{instr_portion}.tar.gz"

    def _get_archive_names(self, files: list[Path]):
        """Create the filenames that will be used in the resulting archive file.
        These are a single level directory name that will preserve the uniqueness of each file,
        even if they are from different nights or instruments.
        """
        archive_names = []
        for file in files:
            date_str, instr = parse_file_name(file)
            archive_names.append(f"data-{date_str}-{instr}/{file.name}")
        return archive_names

    def _validate_json(self, request):
        """Validate the passed in JSON.
        The DRF JSONParser will validate that the request is JSON formatted,
        but this validates that it contains the expected data.
        """

        # Make sure the input is either a JSON or a form with a "download_files" list
        file_list = None
        if isinstance(request.data, list):
            # We were sent JSON data directly
            file_list = request.data

        else:
            # The data was submitted as form data, use our serializer to parse it
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid(raise_exception=True):
                if "download_files" in serializer.data and isinstance(
                    serializer.data["download_files"], list
                ):
                    file_list = serializer.data["download_files"]
                else:
                    raise ParseError(detail="Expected a JSON list of filenames.")

        if not isinstance(file_list, list):
            raise ParseError(detail="Expected list of filenames as JSON or form data.")

        # Make sure the list doesn't exceed our maximum allowed number of files
        if len(file_list) > lick_archive_config.download.max_tarball_files:
            raise ParseError(
                detail=f"List of filenames exceeds maximum length of {lick_archive_config.download.max_tarball_files}."
            )

        # Make sure each entry is a string, that it's not emtpy, and not too long.
        for i, file in enumerate(file_list):
            if not isinstance(file, str):
                raise ParseError(
                    detail=f"List of filename contained non-string value at index {i}"
                )
            if len(file) > MAX_FILENAME_SIZE:
                raise ParseError(
                    detail=f"List of filename contained filename longer than {MAX_FILENAME_SIZE} characters at index {i}"
                )
            if len(file) < 0:
                raise ParseError(
                    detail=f"List of filename contained empty filename at index {i}"
                )
        return file_list

    def _get_validated_files(self, files: list[str]) -> list[Path]:
        """Validate the incomming list of files. This ensures that the files exist,
        that the user is authorized to receive them, and that maximum size
        constraints are met."""

        next_index = 0
        resulting_files = []
        total_size = 0
        # The maximum size in the config file is specified in MiB
        maximum_size = lick_archive_config.download.max_tarball_size * (2**20)

        # Go through the passed in files in batches, sorting each batch for comparison against
        # a sorted query on the file names.
        while next_index < len(files):
            next_batch = files[next_index : next_index + self.batch_size]
            if len(next_batch) > 0:

                # Prepare a queryset to find the given files, using the Query app's API
                # to properly filter and handle proprietary access
                self.request.validated_query = {
                    "filename": ["in", next_batch],
                    "sort": ["id"],
                    "count": False,
                }

                queryset = self.filter_queryset(self.get_queryset())
                queryset = queryset.values(*self.allowed_result_attributes)

                # Get the next batch of results
                logger.debug(f"querying {next_index}:{next_index+self.batch_size}")
                results = queryset[0 : self.batch_size]
                logger.debug(f"Results: {results}")

                # Make sure each desired file was found, and make sure we don't exceed the maximum allowed combined file size

                # Map of filenames returned from the db with their file sizes
                found_file_sizes = {
                    Path(result["filename"]): result["file_size"] for result in results
                }

                for file in next_batch:
                    full_path = Path(lick_archive_config.ingest.archive_root_dir, file)
                    logger.debug(f"Looking for {full_path}")
                    if full_path not in found_file_sizes:
                        logger.info(f"Could not find {full_path} in results.")
                        raise NotFound(
                            detail=f"Filename {file} was not found in the archive or the user does not have permissions to download it."
                        )

                    total_size += found_file_sizes[full_path]
                    if total_size > maximum_size:
                        logger.info(
                            f"Total file sizes {total_size} exceeded maximum size {maximum_size}"
                        )
                        raise APIException(
                            detail=f"Total size of all files exceeded maximum of {lick_archive_config.download.max_tarball_size} MiB"
                        )
                    resulting_files.append(full_path)
            next_index += self.batch_size

        return resulting_files
