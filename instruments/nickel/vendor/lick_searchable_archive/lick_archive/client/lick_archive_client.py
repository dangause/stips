"""
This is an example Python client wrapping the Lick Archive's API.

Requirements:
-------------
Reqires the tenacity and requests packages from PyPi.

astropy is also required to query by coordinates.

Examples:
---------
Query by date:

    >>> import datetime
    >>> from lick_archive_client import LickArchiveClient, QueryTerm

    >>> client = LickArchiveClient("https://archive.ucolick.org/archive")

    >>> term = QueryTerm(field="obs_date", value = datetime.date(2019, 5, 24))
    >>> client.query(term, page=1, page_size=5)
    (80,
    [{'filename': '2019-05/23/shane/r7.fits', 'id': 108742},
    {'filename': '2019-05/23/shane/b37.fits', 'id': 108743},
    {'filename': '2019-05/23/shane/b8.fits', 'id': 108744},
    {'filename': '2019-05/23/shane/r34.fits', 'id': 108745},
    {'filename': '2019-05/23/shane/r19.fits', 'id': 108746}],
    None,
    'https://archive.ucolick.org/archive/data/?obs_date=eq%2C2019-05-24&page=2&page_size=5&results=filename')

Note that the dates above appear to be from 2019-05-23. That's because the query parameters are assumed to be UTC.
The observation dates in the archive are stored from Noon to Noon PST to represent an observing night.

Also the above query has 80 results, only the first 5 were retrieved because of the passed in page_size. To
retrieve additional pages, increment the "page" argument to the query method.  The items in the results returned are:

    Number of Results (80 in the above example)
    A list of JSON objects representing each result. The integer 'id' of each file is always returned, in addition to requested resutls.
    A link to the previous page of results (None above as this was the first page)
    A link to the next page of results.


Query by date time range (including timezone):

    The below uses a full date range to query for files on the night of May 23-24 2019. It also requests the "object" field.

    >>> PST = datetime.timezone(datetime.timedelta(hours=-8))
    >>> term = QueryTerm(field="obs_date", value=[datetime.datetime(2019, 5, 23, 12, 0, 0, tzinfo=PST),
    ...                                           datetime.datetime(2019, 5, 24, 12, 0, 0, tzinfo=PST)])
    >>> client.query(term, results=["filename", "object"], page=1, page_size=5)
    (68,
    [{'filename': '2019-05/23/shane/r7.fits', 'object': 'bias', 'id': 108742},
    {'filename': '2019-05/23/shane/b37.fits', 'object': 'HeHgCdArNe','id': 108743},
    {'filename': '2019-05/23/shane/b8.fits', 'object': 'bias', 'id': 108744},
    {'filename': '2019-05/23/shane/r34.fits', 'object': 'BD+28 4211', 'id': 108745},
    {'filename': '2019-05/23/shane/r19.fits', 'object': 'flat', 'id': 108746}],
    None,
    'https://archive.ucolick.org/archive/data/?obs_date=in%2C2019-05-23T12%3A00%3A00-08%3A00%2C2019-05-24T12%3A00%3A00-08%3A00&page=2&page_size=5&results=filename%2Cobject')

Query by filename:
    The below queries by the prefix of the filename:

    >>> term = QueryTerm(field="filename", value="2019-05/23/shane", prefix=True)
    >>> client.query(term,page=1,page_size=5)
    (68,
    [{'filename': '2019-05/23/shane/r7.fits',
    'obs_date': '2019-05-23T18:20:57.980000-07:00',
    'id': 108742},
    {'filename': '2019-05/23/shane/b37.fits',
    'obs_date': '2019-05-24T05:14:37.630000-07:00',
    'id': 108743},
    {'filename': '2019-05/23/shane/b8.fits',
    'obs_date': '2019-05-23T18:20:47.630000-07:00',
    'id': 108744},
    {'filename': '2019-05/23/shane/r34.fits',
    'obs_date': '2019-05-24T05:01:05.900000-07:00',
    'id': 108745},
    {'filename': '2019-05/23/shane/r19.fits',
    'obs_date': '2019-05-23T18:41:45.050000-07:00',
    'id': 108746}],
    None,
    'https://archive.ucolick.org/archive/data/?filename=sw%2C2019-05%2F23%2Fshane&page=2&page_size=5&results=filename%2Cobs_date')

Query by Object:

    The below queries by object, using a case insensitive search for any object values that contain the search value.

    >>> term = QueryTerm(field="object", value="Feige110", match_case=False, contains=True)
    >>> client.query(term, results=["filename", "object"], page=1, page_size=5)
    (901,
    [{'filename': '2022-07/20/shane/r102.fits', 'object': 'feige110', 'id': 289},
    {'filename': '2022-07/20/shane/b33.fits', 'object': 'feige110', 'id': 293},
    {'filename': '2022-07/05/shane/b23.fits', 'object': 'feige110', 'id': 876},
    {'filename': '2022-07/05/shane/r84.fits', 'object': 'feige110', 'id': 968},
    {'filename': '2022-07/07/shane/b1079.fits', 'object': 'Feige110', 'id': 1065}],
    None,
    'https://archive.ucolick.org/archive/data/?object=cni%2CFeige110&page=2&page_size=5&results=filename%2Cobject')

Query by Coordinate:

    The below queries by coordinate, using astropy Angles to represent the coordinate.  It also filters on an instrument (the only filter currently allowed).

    from astropy.coordinates import Angle

    >>> coord = {"ra":  Angle("23h19m58.4s"),
    ...          "dec": Angle("-5d09m56.171s"),
    ...          "radius": Angle("60s")}
    >>> term = QueryTerm(field="coord", value=coord)

    >>> client.query(term, results=["filename","object","obs_date"], filters={"instrument": "KAST_BLUE,KAST_RED"},page=1, page_size=5)
    (881,
    [{'filename': '2022-07/20/shane/b33.fits',
    'object': 'feige110',
    'obs_date': '2022-07-21T05:00:07.080000-07:00',
    'id': 293},
    {'filename': '2022-07/05/shane/b23.fits',
    'object': 'feige110',
    'obs_date': '2022-07-06T04:57:06.670000-07:00',
    'id': 876},
    {'filename': '2022-07/07/shane/b1079.fits',
    'object': 'Feige110',
    'obs_date': '2022-07-08T04:50:24.300000-07:00',
    'id': 1065},
    {'filename': '2022-06/29/shane/b27.fits',
    'object': 'feige110',
    'obs_date': '2022-06-30T04:38:47.360000-07:00',
    'id': 7253},
    {'filename': '2022-06/02/shane/b28.fits',
    'object': 'feige110',
    'obs_date': '2022-06-03T04:45:37.050000-07:00',
    'id': 7503}],
    None,
    'https://archive.ucolick.org/archive/data/?coord=in%2C349.993%2C-5.1656%2C60&filters=instrument%2CKAST_BLUE%2CKAST_RED&page=2&page_size=5&results=filename%2Cobject%2Cobs_date')

    Query with multiple terms:

        It's possible to query by multiple terms, with the results being ANDed together for the results.

        >>> PST = datetime.timezone(datetime.timedelta(hours=-8))
        >>> term1 = QueryTerm(field="obs_date", value=[datetime.datetime(2019, 5, 23, 12, 0, 0, tzinfo=PST),
        ...                                            datetime.datetime(2019, 5, 24, 12, 0, 0, tzinfo=PST)])
        >>> term2 = QueryTerm(field="object", value="BD+", contains=True, match_case=False)
        >>> client.query([term1, term2], results=["filename","object","obs_date"], page=1, page_size=5)
        (4,
        [{'filename': '2019-05/23/shane/r34.fits',
        'object': 'BD+28 4211',
        'obs_date': '2019-05-24T05:01:05.900000-07:00',
        'id': 108745},
        {'filename': '2019-05/23/shane/b33.fits',
        'object': 'BD+28 4211',
        'obs_date': '2019-05-24T05:00:02.550000-07:00',
        'id': 108747},
        {'filename': '2019-05/23/shane/r35.fits',
        'object': 'BD+28 4211',
        'obs_date': '2019-05-24T05:02:10.300000-07:00',
        'id': 108772},
        {'filename': '2019-05/23/shane/r33.fits',
        'object': 'BD+28 4211',
        'obs_date': '2019-05-24T05:00:01.490000-07:00',
        'id': 108791}],
        None,
        None)

"""

import logging
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import requests
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_delay,
    wait_exponential,
)

logger = logging.getLogger(__name__)


@dataclass
class QueryTerm:
    """A single query term for for the archive. These care ANDed together when using LickArchiveClient.query().

    Args:
        field (str):  The field name to query on. Currently the archive only supports "filename", "obs_date", "object" and "coord".
        value (Any):  The value to query for. Type depens on the field being queried:
                         "filename", A string with the path and name to a file. For Example: "2019-05/23/shane/b23.fits".
                         "object": A string with the name of the object being observed, as set in the FITS "OBJECT" header keyword.
                         "coord": A dict with keys "ra", "dec", and "radius" with astropy.coordinates.Angle objects as values.
                                  A sequence of these three values is also accepted.
                         "obs_date": A datetime.date, a datetime.datetime, or a sequence of two date/datetime objects. One date is for an exact match and two for the start and end of a date range.

        contains   (bool): If True, search for values that contain the QueryTerm value.
        match_case (bool): If True, search for strings that exactly match the case of the QueryTerm value. If False, queries are case insensitive.
        prefix:    (bool): If True, search for strings that start with the QueryTerm value.

    The contains, match_case, and prefix values are defaulted for an exact match query.
    """

    field: str
    value: Any
    contains: bool = False
    match_case: bool = True
    prefix: bool = False


class LickArchiveClient:
    """Client for the Lick Searchable Archive's REST API

    Args:
    archive_url (str):                 The URL of the Archive REST API
    retry_max_delay (int):             The maximum delay between retrying an API call in seconds.
                                       The actual delay will be an exponential backoff starting at 5s.
    retry_max_time (int):              The maximum time to spend retrying a call.
    request_timeout (int):             The maximum time to wait for an API call to return before
                                       timing out and assuming it failed.
    ssl_verify (str, Optional):        Path to a public key or CA bundle for SSL certificate verification.
                                       False disables all cert verification, and True enables default verification.
                                       Defaults to True.
    rate_limit_delay (float, Optional): Delay in seconds between requests to avoid rate limiting.
                                       Set to 0 to disable. Defaults to 0.1 seconds.

    """

    def __init__(
        self,
        archive_url: str,
        retry_max_delay: int | float = 10,
        retry_max_time: int | float = 60,
        request_timeout: int | float = 30,
        ssl_verify: bool | str = True,
        rate_limit_delay: float = 0.1,
    ):

        # The ingest URLs should have a / on it so that other path components can be appended
        if archive_url[-1] == "/":
            self.archive_url = archive_url
        else:
            self.archive_url = archive_url + "/"

        self.retry_max_delay = retry_max_delay
        self.retry_max_time = retry_max_time
        self.request_timeout = request_timeout
        self.ssl_verify = ssl_verify
        self.rate_limit_delay = rate_limit_delay
        self._csrf_middleware_token = None
        self.logged_in_user = None
        self._session = requests.Session()
        self._last_request_time = 0

    def _should_retry_request(self, exception):
        """Determine if a request should be retried based on the exception.

        Args:
            exception: The exception raised during the request

        Returns:
            bool: True if the request should be retried
        """
        if isinstance(exception, requests.exceptions.RequestException):
            if hasattr(exception, "response") and exception.response is not None:
                # Retry on 429 (Too Many Requests) and 5xx server errors
                return (
                    exception.response.status_code == 429
                    or exception.response.status_code >= 500
                )
            # Retry on connection errors, timeouts, etc.
            return True
        return False

    def _wait_for_rate_limit(self):
        """Apply rate limiting delay between requests."""
        if self.rate_limit_delay > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.rate_limit_delay:
                sleep_time = self.rate_limit_delay - elapsed
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.3f} seconds")
                time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _get_retry_after_delay(self, response):
        """Extract retry delay from Retry-After header if present.

        Args:
            response: The HTTP response object

        Returns:
            int: Number of seconds to wait, or None if header not present
        """
        if response is not None and "Retry-After" in response.headers:
            try:
                return int(response.headers["Retry-After"])
            except (ValueError, TypeError):
                logger.warning(
                    f"Invalid Retry-After header: {response.headers['Retry-After']}"
                )
        return None

    def login(self, username: str, password: str) -> bool:
        """
        login to the archive API as a user.

        Args:
            username (str): The username to login as
            password (str): The password to login with

        Return:
            bool: True if the login was accepted, false otherwise

        """

        raise NotImplementedError()

    def logout(self):
        raise NotImplementedError()

    def get_login_status(self) -> bool:
        """Determine the login status of the current session. If successful the
        logged_in_user attribute is set to the current user name or None if not logged in.


        Return:
            bool: True if successfull getting the login status. False if there was a failure
        """
        raise NotImplementedError()

    def query(
        self,
        query_terms: QueryTerm | list[QueryTerm],
        filters: Mapping[str, str | Sequence[str]] = {},
        count: bool = False,
        results: list[str] = ["filename"],
        sort: list[str] = [],
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list, str | None, str | None]:
        """
        Find the files in the archive that match a query.

        Args:
            query_terms (QueryTerm or list[QueryTerms]):
                One or more QueryTerms to query on. Each QueryTerm is ANDed together.

            filters (dict):
                Additional filters to apply to the query. The key is the name of the
                field to filter on, the value is one or more values to query for.
                Currently only "instrument" is supported. For example: {"instrument": "NICKEL"}

            count (int):
                Whether to return a count of how many files match the query instead of the
                metadata from the files. Defaults to False.

            results (list of str):
                The list of metadata fields to return. Defaults to ["filename"]. This is ignored
                if count is True. Regardless of what results are passed in "id" is always returned.

            sort (list of str):
                The list of metadata fields to sort by. Prefix an attribute with "-" for a
                descending sort. Defaults to ["id"].

            page_size (int):
                How many items to return per page. Defaults to 50.

            page (int):
                Which page of the query to retrieve. For multipage queries, passing the same arguments
                with increasing page numbers will go through all pages of the query. Defaults to 1.
        Return (tuple):
            int : The number of files that match the query
            list: A list of dict objects containing the resulting metadata. The keys are the attributes provided in results.
                  This will be empty if count was True.
            str: The URL to the previous page of results. None if there is no previous page.
            str: The URL to the next page of results. None if there is no next page.

        Raises:
            requests.RequestException on failure contacting the archive server.
            ValueError If an invalid value passed into query, or invalid result is returned from the archive server.
        """
        # Validate the field being queried on

        if not isinstance(query_terms, Sequence):
            query_terms = [query_terms]
        else:
            if len(query_terms) == 0:
                raise ValueError("At least one query term must be supplied.")

        query_params = {}

        for term in query_terms:

            if term.field not in ["filename", "object", "obs_date", "coord"]:
                raise ValueError(f"Unknown query field '{term.field}'")

            if term.prefix:
                operator = "sw"
            elif term.contains:
                operator = "cn"
            else:
                operator = "eq"

            # Build query parameters
            if term.field == "obs_date":
                # Convert the date range tuple to a comma separated list
                if isinstance(term.value, datetime) or isinstance(term.value, date):
                    # Strip timezone info - archive API expects naive datetime strings
                    if (
                        isinstance(term.value, datetime)
                        and term.value.tzinfo is not None
                    ):
                        value = term.value.replace(tzinfo=None).isoformat()
                    else:
                        value = term.value.isoformat()
                else:
                    # Strip timezone info from each datetime in the range
                    iso_values = []
                    for date_value in term.value:
                        if (
                            isinstance(date_value, datetime)
                            and date_value.tzinfo is not None
                        ):
                            iso_values.append(
                                date_value.replace(tzinfo=None).isoformat()
                            )
                        else:
                            iso_values.append(date_value.isoformat())
                    value = ",".join(iso_values)
                    operator = "in"

            elif term.field == "coord":
                # ra, dec, and radius, all are converted to decimal degrees
                if isinstance(term.value, Mapping):
                    if "ra" not in term.value:
                        raise ValueError('Invalid coord value, no "ra" key.')
                    if "dec" not in term.value:
                        raise ValueError('Invalid coord value, no "dec" key.')
                    if "radius" not in term.value:
                        raise ValueError('Invalid coord value, no "radius" key.')

                    ra = term.value["ra"]
                    dec = term.value["dec"]
                    radius = term.value["radius"]

                elif isinstance(term.value, Sequence):
                    if len(term.value) != 3:
                        raise ValueError(
                            "Invalid coord value. coord should be a list of ra,dec,radius"
                        )

                    ra, dec, radius = term.value

                else:
                    raise ValueError(
                        "Invalid coord value, coord should be list or dict of ra,dec,radius Astropy Angle objects"
                    )
                value = f'{ra.to_string(unit="deg",decimal=True)},{dec.to_string(unit="deg",decimal=True)},{radius.to_string(unit="arcsec",decimal=True)}'
                operator = "in"
            else:
                value = str(term.value)
                if not term.match_case:
                    operator += "i"

            query_params[term.field] = operator + "," + value

        for field, value in filters.items():
            if field != "instrument":
                raise ValueError(f"Cannot filter by field named {field}")
            filter_values = ["instrument"]
            if isinstance(value, str):
                filter_values.append(value)
            else:
                filter_values += [str(x) for x in value]
            query_params["filters"] = ",".join(filter_values)

        if count is True:
            query_params["count"] = True
        else:
            query_params["results"] = ",".join(results)
            query_params["page_size"] = page_size
            query_params["page"] = page
            if len(sort) != 0:
                query_params["sort"] = ",".join(sort)

        logger.debug(f"Querying archive: url:{self.archive_url} params: {query_params}")

        return self._process_results(self._run_query(query_params), count)

    def _run_query(
        self, query_params: dict
    ) -> tuple[int, list, str | None, str | None]:
        """Helper method to send the query request to the archive server.

        Args:
            query_params (dict): The query parameters to send.

        Return:
            The query results (see the query method)
        """
        # We run the request using slightly over the TCP timeout of 3 seconds for the socket connect.
        # The request_timeout is the timeout between bytes sent from the server
        logger.debug(f"Querying archive: url:{self.archive_url} params: {query_params}")

        def _make_request():
            self._wait_for_rate_limit()
            response = self._session.get(
                self.archive_url + "data/",
                params=query_params,
                verify=self.ssl_verify,
                timeout=(3.1, self.request_timeout),
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = self._get_retry_after_delay(response)
                if retry_after:
                    logger.warning(
                        f"Rate limited (429). Server requested {retry_after}s delay. Retrying..."
                    )
                    time.sleep(retry_after)
                else:
                    logger.warning(
                        "Rate limited (429). Retrying with exponential backoff..."
                    )
                response.raise_for_status()

            response.raise_for_status()
            return response

        retryer = Retrying(
            stop=stop_after_delay(self.retry_max_time),
            wait=wait_exponential(multiplier=1, min=5, max=self.retry_max_delay),
            retry=retry_if_exception(self._should_retry_request),
        )
        result = retryer(_make_request)

        return result.json()

    def _process_results(self, result_json, count=False):
        logger.debug(f"Results from archive: {result_json}")

        # Get the number of results from the query as an integer
        if "count" in result_json:
            query_count = int(result_json["count"])
        else:
            raise ValueError(
                "Archive server did not return an count value for a query requesting a count."
            )

        if count:
            # The count was all that was requested
            return query_count, [], None, None
        else:
            # Return a list of results for non-count queries
            if "results" in result_json:
                # Get next/previous page links
                if "next" in result_json:
                    next_page = result_json["next"]
                else:
                    next_page = None

                if "previous" in result_json:
                    prev_page = result_json["previous"]
                else:
                    prev_page = None

                return query_count, result_json["results"], prev_page, next_page
            else:
                raise ValueError("Archive server did not return results for a query.")

    def header(self, filename):
        """Retrieve the header for a file in the archive.

        Args:
            filename (str): The (relative) name of the file in the archive. (e.g. 2019-05/23/shane/b33.fits)

        Return:
            str:  The file's header, as a single text string.
        """
        if not isinstance(filename, str):
            filename = str(filename)
        if filename[0] != "/":
            filename = "/" + filename

        header_url = self.archive_url + "data" + filename + "/header"
        logger.debug(f"Getting header for {header_url}")

        def _make_request():
            self._wait_for_rate_limit()
            response = self._session.get(
                header_url, verify=self.ssl_verify, timeout=(3.1, self.request_timeout)
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = self._get_retry_after_delay(response)
                if retry_after:
                    logger.warning(
                        f"Rate limited (429) for header {filename}. Server requested {retry_after}s delay."
                    )
                    time.sleep(retry_after)
                else:
                    logger.warning(
                        f"Rate limited (429) for header {filename}. Retrying with exponential backoff..."
                    )
                response.raise_for_status()

            response.raise_for_status()
            return response

        retryer = Retrying(
            stop=stop_after_delay(self.retry_max_time),
            wait=wait_exponential(multiplier=1, min=5, max=self.retry_max_delay),
            retry=retry_if_exception(self._should_retry_request),
        )
        result = retryer(_make_request)
        return result.text

    def download(self, filename, destination):
        """Retrieve a file in the archive.

        Args:
            filename (str): The (relative) name of the file in the archive. (e.g. 2019-05/23/shane/b33.fits)
            destination (str): The destination file to receive the file's contents
        Return:
            bool: True if download successful, False otherwise.
        """
        if not isinstance(filename, str):
            filename = str(filename)
        if filename[0] != "/":
            filename = "/" + filename

        download_url = self.archive_url + "data" + filename
        logger.info(f"Downloading {download_url}")

        def _make_request():
            self._wait_for_rate_limit()
            response = self._session.get(
                download_url,
                verify=self.ssl_verify,
                timeout=(3.1, self.request_timeout),
                stream=True,
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = self._get_retry_after_delay(response)
                if retry_after:
                    logger.warning(
                        f"Rate limited (429) downloading {filename}. Server requested {retry_after}s delay."
                    )
                    time.sleep(retry_after)
                else:
                    logger.warning(
                        f"Rate limited (429) downloading {filename}. Retrying with exponential backoff..."
                    )
                response.raise_for_status()

            response.raise_for_status()
            return response

        retryer = Retrying(
            stop=stop_after_delay(self.retry_max_time),
            wait=wait_exponential(multiplier=1, min=5, max=self.retry_max_delay),
            retry=retry_if_exception(self._should_retry_request),
        )
        result = retryer(_make_request)

        with open(destination, "wb") as dest_file:
            for chunk in result.iter_content(chunk_size=64 * 1024):
                logger.debug("Writing chunk")
                dest_file.write(chunk)

        stat_info = os.stat(destination)
        logger.debug(f"Response headers: {result.headers}")
        if "Content-Length" in result.headers:
            if stat_info.st_size == int(result.headers["Content-Length"]):
                logger.info(
                    f"Successfully downloaded {stat_info.st_size} bytes to {destination}"
                )
                return True
            else:
                logger.error(
                    f"Download of {destination} failed, only received {stat_info.st_size} bytes of {result.headers['Content-Length']}"
                )
                return False
        logger.info(
            f"Downloaded {stat_info.st_size} bytes to {destination}. Cannot verify size of file."
        )
        return True
