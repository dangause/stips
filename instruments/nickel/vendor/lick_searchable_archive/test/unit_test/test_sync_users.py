import copy
import datetime

import pytest
from django.utils.crypto import RANDOM_STRING_CHARS, get_random_string
from lick_archive.apps.archive_auth.hashers import APR_MD5PasswordHasher
from passlib.hash import apr_md5_crypt
from test_utils import basic_django_setup, create_test_request, django_db_setup


def get_password_hash(password):
    salt = get_random_string(8, RANDOM_STRING_CHARS)
    return apr_md5_crypt.using(salt=salt).hash(password)


# Note all passwords here are the hased form of "password".
hashed_password = get_password_hash("password")
expected_hashed_password = APR_MD5PasswordHasher.algorithm + hashed_password

test_sched_db_users = [  # Minimum # of fields
    {"obid": 1, "lastname": "example"},
    # Minimum # of fields with passwords
    {"obid": 8, "lastname": "Smith", "webpass": hashed_password},
    # First/lastname but no email
    {"obid": 9, "lastname": "Smith", "firstname": "John", "webpass": hashed_password},
    # All of the fields
    {
        "obid": 4,
        "lastname": "Doe",
        "firstname": "John",
        "email": "john.doe@example.org",
        "stamp": datetime.datetime.fromisoformat("1969-07-20 20:17:00+00:00"),
        "webpass": hashed_password,
    },
    {
        "obid": 5,
        "lastname": "Smith",
        "firstname": "Jane",
        "email": "jane.smith@example.org",
        "stamp": datetime.datetime.fromisoformat("1969-07-20 20:17:00+00:00"),
        "webpass": hashed_password,
    },
    # Obligatory xkcd ref. Also no timezone on date
    {
        "obid": 2,
        "lastname": "'); DROP TABLE Students;--",
        "firstname": "Robert",
        "email": "bobby.tables@example.org",
        "stamp": datetime.datetime.fromisoformat("1969-07-20 20:17:00"),
        "webpass": hashed_password,
    },
    # Throw in some special characters, string date
    {
        "obid": 7,
        "lastname": "Smith\"'(){}\0;'/%.\\>?< ee",
        "firstname": "JonÆ\n🦀\nth∅n",
        "email": "smithee.j@example.org",
        "stamp": "1969-07-20 20:17:00+00:00",
        "webpass": hashed_password,
    },
]


def compare_maps(map1, map2, keys, error_string):
    for key in keys:
        assert map1[key] == map2[key], error_string + f" mismatch for {key}"


@basic_django_setup
def test_validate_sched_db_users():

    # Test on valid users
    from scripts.admin_scripts.sync_archive_users import parse_sched_db_users

    sched_db_map = parse_sched_db_users(test_sched_db_users)

    # Make sure optional columns are None or correctly defaulted
    assert sched_db_map[1] != test_sched_db_users[0]
    assert sched_db_map[1]["obid"] == 1
    assert sched_db_map[1]["lastname"] == "example"
    assert sched_db_map[1]["firstname"] == ""
    assert sched_db_map[1]["email"] == ""
    assert isinstance(sched_db_map[1]["stamp"], datetime.datetime)
    assert sched_db_map[1]["webpass"] is None

    assert sched_db_map[8] != test_sched_db_users[1]
    assert sched_db_map[8]["obid"] == 8
    assert sched_db_map[8]["lastname"] == "Smith"
    assert sched_db_map[8]["firstname"] == ""
    assert sched_db_map[8]["email"] == ""
    assert isinstance(sched_db_map[8]["stamp"], datetime.datetime)
    assert sched_db_map[8]["webpass"] == expected_hashed_password

    compare_maps(
        sched_db_map[9],
        test_sched_db_users[2],
        ["obid", "lastname", "firstname"],
        "Error comparing users",
    )
    assert sched_db_map[9]["webpass"] == expected_hashed_password

    compare_maps(
        sched_db_map[4],
        test_sched_db_users[3],
        ["obid", "lastname", "firstname", "email", "stamp"],
        "Error comparing users",
    )
    assert sched_db_map[4]["webpass"] == expected_hashed_password

    compare_maps(
        sched_db_map[5],
        test_sched_db_users[4],
        ["obid", "lastname", "firstname", "email", "stamp"],
        "Error comparing users",
    )
    assert sched_db_map[5]["webpass"] == expected_hashed_password

    # The last two have dates that won't be the same string
    expected_date = datetime.datetime.fromisoformat("1969-07-20 20:17:00+00:00")

    compare_maps(
        sched_db_map[2],
        test_sched_db_users[5],
        ["obid", "lastname", "firstname", "email"],
        "Error comparing users",
    )
    assert sched_db_map[2]["webpass"] == expected_hashed_password
    # has the timezone added
    assert sched_db_map[2]["stamp"] == expected_date

    compare_maps(
        sched_db_map[7],
        test_sched_db_users[6],
        ["obid", "lastname", "firstname", "email"],
        "Error comparing users",
    )
    assert sched_db_map[7]["webpass"] == expected_hashed_password
    # Converted from string
    assert sched_db_map[7]["stamp"] == expected_date

    # Test with some invalid users missing required keys
    invalid_users = [  # No obid
        {"lastname": "Nope"},
        # No lastname
        {
            "obid": 1,
            "firstname": "John",
            "email": "john@example.com",
            "stamp": datetime.datetime.fromisoformat("1969-07-20 20:17:00+00:00"),
        },
        # Bad date, should get current time instead
        {
            "obid": 5,
            "lastname": "Smith",
            "firstname": "Janet",
            "email": "janet.smith@example.com",
            "stamp": "meow",
            "webpass": hashed_password,
        },
        # One good one to make sure it goes through
        {
            "obid": 9,
            "lastname": "Smith",
            "firstname": "Janet",
            "email": "janet.smith@example.com",
            "stamp": datetime.datetime.fromisoformat("1969-07-20 20:17:00+00:00"),
            "webpass": hashed_password,
        },
        # Duplicate obids
        {
            "obid": 2,
            "lastname": "Smith",
            "firstname": "John",
            "email": "john.smith@example.com",
            "stamp": datetime.datetime.fromisoformat("1969-07-20 20:17:00+00:00"),
        },
        {
            "obid": 2,
            "lastname": "Smith",
            "firstname": "Jason",
            "email": "jason.smith@example.com",
            "stamp": datetime.datetime.fromisoformat("1969-07-20 20:17:00+00:00"),
        },
        {
            "obid": 2,
            "lastname": "Smith",
            "firstname": "Jane",
            "email": "jane.smith@example.com",
            "stamp": datetime.datetime.fromisoformat("1969-07-20 20:17:00+00:00"),
        },
    ]

    sched_db_map = parse_sched_db_users(invalid_users)

    assert len(sched_db_map) == 2
    assert sched_db_map[5]["email"] == invalid_users[2]["email"]
    assert isinstance(sched_db_map[5]["stamp"], datetime.datetime)
    assert sched_db_map[9]["email"] == invalid_users[3]["email"]


@basic_django_setup
def test_generate_username():
    from scripts.admin_scripts.sync_archive_users import (
        generate_username_from_sched_db,
        parse_sched_db_users,
    )

    sched_db_map = parse_sched_db_users(test_sched_db_users)
    names = [
        generate_username_from_sched_db(sched_db_map[obid]) for obid in sched_db_map
    ]

    # The two lastname only users
    for i in range(2):
        assert names[i] == test_sched_db_users[i]["lastname"]

    # First, last name but no email
    assert (
        names[2]
        == test_sched_db_users[2]["firstname"]
        + " "
        + test_sched_db_users[2]["lastname"]
    )

    # Rest should use e-mail address
    for i in range(3, len(test_sched_db_users)):
        assert names[i] == test_sched_db_users[i]["email"]


@django_db_setup
def test_create_user():
    from django.contrib.auth import authenticate
    from lick_archive.apps.archive_auth.models import ArchiveUser
    from scripts.admin_scripts.sync_archive_users import (
        create_user,
        parse_sched_db_users,
    )

    sched_db_map = parse_sched_db_users(test_sched_db_users)

    new_user = create_user(sched_db_map[4])
    # make sure the user can be saved
    new_user.save()

    queried_user = ArchiveUser.objects.all()[0]

    assert queried_user.obid == 4
    assert queried_user.last_name == sched_db_map[4]["lastname"]
    assert queried_user.first_name == sched_db_map[4]["firstname"]
    assert queried_user.email == sched_db_map[4]["email"]
    assert queried_user.stamp == sched_db_map[4]["stamp"]
    assert queried_user.username == sched_db_map[4]["email"]
    assert queried_user.password == expected_hashed_password

    # Make sure the password can be validated
    assert queried_user.is_active is True

    mock_request = create_test_request(path="archive/login", data={})
    auth_user = authenticate(
        request=mock_request, username=queried_user.username, password="password"
    )
    assert auth_user is not None


@django_db_setup
def test_update_user():
    from django.contrib.auth import authenticate
    from lick_archive.apps.archive_auth.models import ArchiveUser
    from scripts.admin_scripts.sync_archive_users import (
        create_user,
        parse_sched_db_users,
        update_user,
    )

    sched_db_map = parse_sched_db_users(test_sched_db_users)

    # Create a user to update
    new_user = create_user(sched_db_map[4])
    new_user.save()

    new_dict = copy.deepcopy(sched_db_map[4])

    # Test disabling user
    new_dict["webpass"] = None
    assert update_user(new_user, new_dict) is True
    new_user.save()

    all_users = ArchiveUser.objects.all()
    queried_user = all_users[0]
    assert len(all_users) == 1
    assert queried_user.is_active is False
    assert queried_user.has_usable_password() is False

    # Test re-enabling
    new_dict["webpass"] = expected_hashed_password
    assert update_user(queried_user, new_dict) is True
    queried_user.save()

    all_users = ArchiveUser.objects.all()
    queried_user = all_users[0]
    assert len(all_users) == 1
    assert queried_user.is_active is True
    assert queried_user.has_usable_password() is True

    # Test updating last name
    new_dict["lastname"] = "Poe"
    assert update_user(queried_user, new_dict) is True
    queried_user.save()

    all_users = ArchiveUser.objects.all()
    assert len(all_users) == 1
    queried_user = ArchiveUser.objects.all()[0]
    assert queried_user.last_name == "Poe"

    # Test updating first name
    new_dict["firstname"] = "Jane"
    assert update_user(queried_user, new_dict) is True
    queried_user.save()

    all_users = ArchiveUser.objects.all()
    assert len(all_users) == 1
    queried_user = ArchiveUser.objects.all()[0]
    assert queried_user.first_name == "Jane"

    # Test updating e-mail
    new_dict["email"] = "jane.poe@example.org"

    assert update_user(queried_user, new_dict) is True
    queried_user.save()

    all_users = ArchiveUser.objects.all()
    assert len(all_users) == 1
    queried_user = ArchiveUser.objects.all()[0]
    assert queried_user.username == "jane.poe@example.org"
    assert queried_user.email == "jane.poe@example.org"

    # Test updating the timestamp
    new_dict["stamp"] = datetime.datetime.fromisoformat("1972-12-14T22:54:00+00:00")

    assert update_user(queried_user, new_dict) is True
    queried_user.save()

    all_users = ArchiveUser.objects.all()
    assert len(all_users) == 1
    queried_user = ArchiveUser.objects.all()[0]

    assert queried_user.stamp == new_dict["stamp"]

    # Test updating password
    new_hashed_password = get_password_hash("super new password")
    new_expected_hashed_password = APR_MD5PasswordHasher.algorithm + new_hashed_password
    new_dict["webpass"] = new_expected_hashed_password

    assert update_user(queried_user, new_dict) is True
    queried_user.save()

    all_users = ArchiveUser.objects.all()
    assert len(all_users) == 1
    queried_user = ArchiveUser.objects.all()[0]

    assert queried_user.password == new_expected_hashed_password

    # Make sure the password can be validated
    assert queried_user.is_active is True

    mock_request = create_test_request(path="archive/login", data={})
    auth_user = authenticate(
        request=mock_request,
        username=queried_user.username,
        password="super new password",
    )
    assert auth_user is not None

    # Make sure nothing was reverted
    assert queried_user.last_name == "Poe"
    assert queried_user.first_name == "Jane"
    assert queried_user.email == "jane.poe@example.org"
    assert queried_user.username == "jane.poe@example.org"
    assert queried_user.stamp == new_dict["stamp"]

    # Test no update
    assert update_user(queried_user, new_dict) is False


@django_db_setup
def test_duplicate_username():

    from scripts.admin_scripts.sync_archive_users import (
        create_user,
        parse_sched_db_users,
        update_user,
    )

    sched_db_map = parse_sched_db_users(test_sched_db_users)

    # Create a user to update
    new_user = create_user(sched_db_map[4])
    new_user.save()

    new_dict = copy.deepcopy(sched_db_map[4])

    # Try to create a duplicate user
    new_dict["obid"] = 100
    with pytest.raises(
        RuntimeError,
        match="New username 'john.doe@example.org' for new user obid:100 is not unique.",
    ):
        dup_user = create_user(new_dict)

    # Create a second user
    second_user = create_user(sched_db_map[5])
    second_user.save()

    # Try updating the first user to have an identical username as the second
    new_dict["email"] = "jane.smith@example.org"
    with pytest.raises(
        RuntimeError,
        match="New username 'jane.smith@example.org' for obid:4 is not unique",
    ):
        update_user(new_user, new_dict)


@django_db_setup
def test_sync_users_main(monkeypatch, tmp_path):
    from lick_archive.external.sched_db import ScheduleDB

    def mock_init(*args, **kwargs):
        return

    test_observers = copy.deepcopy(test_sched_db_users)

    def mock_get_observers(self):
        return test_observers

    def mock_fail_get_observers(self):
        raise RuntimeError("Test")

    def mock_setup_logging(path, loglevel):
        return True

    with monkeypatch.context() as m:
        m.setattr(ScheduleDB, "__init__", mock_init)
        m.setattr(ScheduleDB, "get_observers", mock_get_observers)
        from lick_archive.apps.archive_auth.models import ArchiveUser
        from scripts.admin_scripts.sync_archive_users import get_parser, main

        parser = get_parser()
        args = parser.parse_args(["--log_path", str(tmp_path)])

        assert main(args) == 0
        users = ArchiveUser.objects.all()
        assert len(users) == 6

        # Make sure only the users with passwords were created
        all_obids = [user.obid for user in users]
        for user_dict in test_sched_db_users:
            if "webpass" in user_dict:
                assert user_dict["obid"] in all_obids
            else:
                assert user_dict["obid"] not in all_obids

        # Make sure all the users can login
        for user in users:
            assert user.is_active
            assert user.check_password("password")

        # Update a user
        test_observers[1]["firstname"] = "Jenny"
        test_observers[1]["email"] = "jsmith@example.org"
        # Create a user
        test_observers.append(
            {
                "obid": 10,
                "lastname": "Smithson",
                "firstname": "Pat",
                "email": "smithsonp@example.org",
                "webpass": hashed_password,
            }
        )

        # Delete a user
        del test_observers[2]
        assert main(args) == 0

        # Make sure the changes took effect
        users = ArchiveUser.objects.all()
        assert len(users) == 7

        user_map = {u.obid: u for u in users}
        assert user_map[8].first_name == "Jenny"
        assert user_map[8].email == "jsmith@example.org"
        assert user_map[8].username == "jsmith@example.org"

        assert user_map[10].username == "smithsonp@example.org"
        assert user_map[10].check_password("password")

        assert user_map[9].is_active is False

        # Now throw in a user that will generate an errror (dup user name)
        test_observers.append(
            {
                "obid": 11,
                "firstname": "John",
                "lastname": "Smith",
                "email": "jsmith@example.org",
                "webpass": hashed_password,
            }
        )
        assert main(args) == 1

        # Make sure the new user wasn't created
        users = ArchiveUser.objects.all()
        assert len(users) == 7

        # Test no users, indicating an error
        test_observers.clear()
        assert main(args) == 1

        # Make sure it didn't try to disable the users
        users = ArchiveUser.objects.all()
        assert len(users) == 7
        for user in users:
            if user.obid == 9:
                assert user.is_active is False
                assert user.has_usable_password() is False
            else:
                assert user.is_active is True
                assert user.check_password("password")

        # Finally test an error querying the ScheduleDB database
        m.setattr(ScheduleDB, "get_observers", mock_fail_get_observers)
        assert main(args) == 1

        # Make sure it didn't try to disable the users
        users = ArchiveUser.objects.all()
        assert len(users) == 7
        for user in users:
            if user.obid == 9:
                assert user.is_active is False
                assert user.has_usable_password() is False
            else:
                assert user.is_active is True
                assert user.check_password("password")
