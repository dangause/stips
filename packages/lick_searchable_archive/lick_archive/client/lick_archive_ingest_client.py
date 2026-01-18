import logging

import requests
from tenacity import Retrying, stop_after_delay, wait_exponential

logger = logging.getLogger(__name__)


class LickArchiveIngestClient:
    """Client for the Lick Searchable Archive's Ingest REST API

    Args:
    ingest_url (str):              The URL of the Ingest REST API
    ingest_retry_max_delay (int):  The maximum delay between retrying an API call in seconds.
                                   The actual delay will be an exponential backoff starting at 5s.
    ingest_retry_max_time (int):   The maximum time to spend retrying a call.
    request_timeout (int):         The maximum time to wait for an API call to return before
                                   timing out and assuming it failed.
    ssl_verify (str):              Optional. Path to a public key or CA bundle for SSL vberification.

    """

    def __init__(
        self,
        ingest_url,
        ingest_retry_max_delay,
        ingest_retry_max_time,
        request_timeout,
        ssl_verify=None,
    ):

        # The ingest URLs should have a / on it so the sync_query, or ingest_new_files part can be appended
        if ingest_url[-1] == "/":
            self.ingest_url = ingest_url
        else:
            self.ingest_url = ingest_url + "/"

        self.ingest_retry_max_delay = ingest_retry_max_delay
        self.ingest_retry_max_time = ingest_retry_max_time
        self.request_timeout = request_timeout
        self.ssl_verify = ssl_verify

    def sync_query(self, data_dir):
        """
        Find the number of images the archive has for a given date and instrument directory. The
        ingest_watchdog service uses this to see if the archive database is missing any files.

        Args;
            data_dir (pathlib.Path): The data directory to sync.
        Return:
            int : The number of files found for that date in that instrument directory.

        Raises:
            requests.RequestException on failure contacting the archive server.
            ValueError If an invalid result is returned from the archive server.

        """
        # Use a retry to run the get request. Retrying a random amount between 5s and the configured max delay
        # The retries will stop after the configured max time
        retryer = Retrying(
            stop=stop_after_delay(self.ingest_retry_max_time),
            wait=wait_exponential(multiplier=1, min=5, max=self.ingest_retry_max_delay),
        )

        # We run the request using slightly over the TCP timeout of 3 seconds for the socket connect.
        # The request_timeout is the timeout between bytes sent from the server
        result = retryer(
            requests.get,
            self.ingest_url + "ingest/counts/" + str(data_dir),
            verify=self.ssl_verify,
            timeout=(3.1, self.request_timeout),
        )
        result.raise_for_status()

        result_json = result.json()
        if "count" in result_json:
            if isinstance(result_json["count"], int):
                return result_json["count"]
            else:
                raise ValueError(
                    "Archive server did not return an integer count value for a sync query."
                )
        else:
            raise ValueError(
                "Archive server did not return an count value for a sync query."
            )

    def add_ingest_notifications(self, file):
        """
        Ingest metadata for one or more files into the archive database.

        Args:
            file (list or str or Path-like): The file or files to ingest. A string or Path-like object is accepted.

        Return:
            None

        Raises:
            requests.RequestException on failure contacting the archive server.
        """
        if isinstance(file, list):
            # A list was passed in.
            # We limit it's max size to be less than 1MB for safety, although if needed we could probably do more.
            # 1MB is approximately 16Ki files (depending on the length of file name). We use 16,0000 max.
            while len(file) > 16000:
                file_list1 = file[0:16000]
                file_list2 = file[16000:]
                self._ingest_new_files(file_list1)
                file = file_list2

            if len(file) > 0:
                self._ingest_new_files(file)

        else:
            # Otherwise a single file
            self._ingest_new_files([file])

    def _ingest_new_files(self, files):

        # Builld the payload. The list could be of strings of Path objects, so we convert to
        # string.
        payload = [{"filename": str(f)} for f in files]
        logger.debug(f"Ingest payload: {payload}")
        # Use a retry to run the post request. Retrying a random amount between 5s and the configured max delay
        # The retries will stop after the configured max time
        retryer = Retrying(
            stop=stop_after_delay(self.ingest_retry_max_time),
            wait=wait_exponential(multiplier=1, min=5, max=self.ingest_retry_max_delay),
        )

        # We run the request using slightly over the TCP timeout of 3 seconds for the socket connect.
        # The request_timeout is the timeout between bytes sent from the server
        result = retryer(
            requests.post,
            self.ingest_url + "ingest/notifications/",
            json=payload,
            verify=self.ssl_verify,
            timeout=(3.1, self.request_timeout),
        )

        result.raise_for_status()

        # We don't need the response for this, as long as its not a failure
        return
