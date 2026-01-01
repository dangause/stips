import os
from collections import namedtuple

from ext_test_common import replace_parsed_url_hostname
from lick_archive.client.lick_archive_client import LickArchiveClient


def test_backend_login(
    archive_host, archive_config, ssl_ca_bundle, test_user_password_env
):

    archive_backend = replace_parsed_url_hostname(
        archive_config.host.api_url.parsed_url, archive_host
    )

    # First make sure we default to logged out
    client = LickArchiveClient(archive_backend, 1, 30, 5, ssl_verify=ssl_ca_bundle)
    assert client.get_login_status() is True
    assert client.logged_in_user is None

    # Login with bad password
    assert client.login("test_user", "badpassword") is False
    assert client.logged_in_user is None

    # login with valid password
    assert client.login("test_user", os.environ[test_user_password_env]) is True
    assert client.logged_in_user == "test_user"


def test_backend_logout(
    archive_host, archive_config, ssl_ca_bundle, test_user_password_env
):
    archive_backend = replace_parsed_url_hostname(
        archive_config.host.api_url.parsed_url, archive_host
    )

    # First make sure we default to logged out
    client = LickArchiveClient(archive_backend, 1, 30, 5, ssl_verify=ssl_ca_bundle)
    assert client.get_login_status() is True
    assert client.logged_in_user is None

    # login with valid password
    assert client.login("test_user", os.environ[test_user_password_env]) is True
    assert client.logged_in_user == "test_user"

    # logout
    assert client.logout() is True
    assert client.logged_in_user is None

    # Make sure the server agrees we're logged out
    assert client.get_login_status() is True
    assert client.logged_in_user is None


def test_session_persist(
    archive_host, archive_config, ssl_ca_bundle, test_user_password_env
):

    archive_backend = replace_parsed_url_hostname(
        archive_config.host.api_url.parsed_url, archive_host
    )

    # First make sure we default to logged out
    client = LickArchiveClient(archive_backend, 1, 30, 5, ssl_verify=ssl_ca_bundle)
    assert client.get_login_status() is True
    assert client.logged_in_user is None

    # login with valid password
    assert client.login("test_user", os.environ[test_user_password_env]) is True
    assert client.logged_in_user == "test_user"

    # Persist logged in session
    MockRequest = namedtuple("MockRequest", ["session"])
    mock_request = MockRequest(session=dict())
    client.persist(mock_request.session)

    # Get status from previous session, and persist again
    client2 = LickArchiveClient(
        archive_backend, 1, 30, 5, request=mock_request, ssl_verify=ssl_ca_bundle
    )
    assert client2.get_login_status() is True
    assert client2.logged_in_user == "test_user"
    client2.persist(mock_request.session)

    # Get status from previous session, logout, persist again
    client3 = LickArchiveClient(
        archive_backend, 1, 30, 5, request=mock_request, ssl_verify=ssl_ca_bundle
    )
    assert client3.get_login_status() is True
    assert client3.logged_in_user == "test_user"
    assert client3.logout() is True
    assert client3.logged_in_user is None
    assert client3.get_login_status() is True
    assert client3.logged_in_user is None
    client3.persist(mock_request.session)

    # make sure session was persisted as logged out
    client4 = LickArchiveClient(
        archive_backend, 1, 30, 5, request=mock_request, ssl_verify=ssl_ca_bundle
    )
    assert client4.logged_in_user is None
