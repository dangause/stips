import os

import pytest
from astropy.io.fits import Header
from ext_test_common import (
    PRIVATE_FILE,
    PUBLIC_FILE,
    TEST_USER,
    replace_parsed_url_hostname,
)
from lick_archive.client.lick_archive_client import LickArchiveClient
from requests import HTTPError

expected_metadata = {
    "PROGRAM": "Shane",
    "EXPTIME": 40.0,
    "RA": "21:51:11.01",
    "DEC": "28:51:50.3",
    "OBJECT": "BD+28 4211",
    "PROGRAM": "NEWCAM",
    "OBSTYPE": "OBJECT",
    "DATE-OBS": "2019-05-24T12:00:01.49",
}

expected_private_metadata = {
    "TRUITIME": 1.45479,
    "RA": "06:11:36.61",
    "DEC": "48:42:40.2",
    "OBJECT": "AurA",
    "PROGRAM": "2024B_S026i0",
    "DATE-BEG": "2025-01-28T03:46:54.079",
}


def test_header_public(archive_host, archive_config, ssl_ca_bundle):

    archive_backend = replace_parsed_url_hostname(
        archive_config.host.api_url.parsed_url, archive_host
    )
    archive_frontend = replace_parsed_url_hostname(
        archive_config.host.frontend_url.parsed_url, archive_host
    )

    client = LickArchiveClient(archive_backend, 1, 30, 5, ssl_verify=ssl_ca_bundle)

    # Make sure we are not logged in at first
    assert client.get_login_status() is True
    assert client.logged_in_user is None

    # Login is done through the backend API, but we want to test the external api, so switch the URL
    client.archive_url = archive_frontend

    # Get the header for the publically available file
    header_str = client.header(PUBLIC_FILE)

    header = Header.fromstring(header_str, sep="\n")

    for key in expected_metadata:
        assert key in header, f"{key} not found in query results"
        assert (
            header[key] == expected_metadata[key]
        ), f"Exepcted results for {key}: '{expected_metadata[key]}' != actual results '{header[key]}'"


def test_header_private(
    archive_host, archive_config, ssl_ca_bundle, test_user_password_env
):

    archive_backend = replace_parsed_url_hostname(
        archive_config.host.api_url.parsed_url, archive_host
    )
    archive_frontend = replace_parsed_url_hostname(
        archive_config.host.frontend_url.parsed_url, archive_host
    )

    client = LickArchiveClient(archive_backend, 1, 30, 5, ssl_verify=ssl_ca_bundle)

    # Login as test user
    assert client.login(TEST_USER, os.environ[test_user_password_env]) is True
    assert client.logged_in_user == TEST_USER

    # Login is done through the backend API, but we want to test the external api, so switch the URL
    client.archive_url = archive_frontend

    # Make sure public file's header can still be seen when logged in
    # Get the header for the publically available file
    header_str = client.header(PUBLIC_FILE)

    header = Header.fromstring(header_str, sep="\n")

    for key in expected_metadata:
        assert key in header, f"{key} not found in query results"
        assert (
            header[key] == expected_metadata[key]
        ), f"Exepcted results for {key}: '{expected_metadata[key]}' != actual results '{header[key]}'"

    # Get the header for the privately available file
    header_str = client.header(PRIVATE_FILE)

    header = Header.fromstring(header_str, sep="\n")

    for key in expected_private_metadata:
        assert key in header, f"{key} not found in query results"
        assert (
            header[key] == expected_private_metadata[key]
        ), f"Exepcted results for {key}: '{expected_private_metadata[key]}' != actual results '{header[key]}'"

    # Switch URLs again to log out
    client.archive_url = archive_backend

    # Now log out, and verify the file can't be seen publically
    assert client.logout() is True
    assert client.logged_in_user is None
    assert client.get_login_status() is True
    assert client.logged_in_user is None

    # Switch URLs again to log out
    client.archive_url = archive_frontend

    # Get the header for the privately available file
    with pytest.raises(HTTPError):
        header_str = client.header(PRIVATE_FILE)
