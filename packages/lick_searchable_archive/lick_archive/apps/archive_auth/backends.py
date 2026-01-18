# ruff: noqa: E402
import logging

logger = logging.getLogger(__name__)

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import check_password

UserModel = get_user_model()


class NonUpgradingBackend(ModelBackend):
    """An authentication backend like Django's default backend except that it doesn't
    automatically upgrade the password hash when authenticating a user."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Authenticate a user's credentials against what's stored in the database.

        Args:
            request (django.http.request.HttpRequest):
                Web requesting asking to authenticate. Required by the API but not used by this class.

            username (str):
                Username to authenticate

            password (str):
                Password to authenticate

            kwargs (dict):
                Additional keyword arguments. Used in case a custom user model uses a different
                name for its username field.

        Return:
            django.contrib.auth.models.AbstractBaseUser: The authenticated user, or None of the user
                                                         failed Authentication
        """
        if username is None:
            # Try the model's username field if username is not set
            username = kwargs.get(UserModel.USERNAME_FIELD, None)

        if username is None:
            logger.error("None user passed to authenticate")
            return None

        if password is None:
            logger.error("None password passed to authenticate")
            return None

        logger.info(f"Authenticating {username}")

        try:
            user = UserModel.objects.get_by_natural_key(username)
            logger.info(f"Found user {user.username} in db")
            # Like the base class, we allow authentication of the user model doesn't have a "is_active" member
            if getattr(user, "is_active", True):
                logger.info("user is active")
                if check_password(password, user.password):
                    logger.info("Password okay")
                    return user
                logger.info("password not okay")
        except UserModel.DoesNotExist:
            logger.info(f"Could not find user '{username}'")
            # Run the password hasher on a dummy user so the performance doesn't give away whether a user exists.
            UserModel().set_password(password)
            return None

        return None
