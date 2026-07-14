from django.contrib.auth.hashers import BasePasswordHasher
from django.utils.crypto import RANDOM_STRING_CHARS, get_random_string
from passlib.context import CryptContext


class APR_MD5PasswordHasher(BasePasswordHasher):
    """A django password hasher for verifying Apache2 apr1_md5 hashes.
    It uses passlib to do all of the work."""

    passlib_algorithm = "apr_md5_crypt"
    algorithm = "apr1md5"

    def salt(self):
        """Return a salt value for this algorithm"""
        # Return salt 8 characters long, to prevent failures since this algorithm only supports 8 characters of salt
        result = get_random_string(8, RANDOM_STRING_CHARS)
        return result

    def encode(self, password, salt):
        """
        Create an encoded database value.

        The result is normally formatted as "algorithm$salt$hash" and
        must be fewer than 128 characters.

        apr1_md5 is a bit strange in that the algorithm is "$apr1", containing a $,
        so we prepend a different algorithm string to make django happy.
        """
        self._check_encode_args(password, salt)
        ctx = CryptContext(self.passlib_algorithm)
        result = self.algorithm + ctx.hash(password, salt=salt)
        return result

    def verify(self, password, encoded):
        """Verify if a password matches a given encoded hash."""
        ctx = CryptContext(self.passlib_algorithm)
        if encoded.startswith(self.algorithm):
            hash = encoded[len(self.algorithm) :]
            result = ctx.verify(password, hash)
        else:
            result = False
        return result

    def safe_summary(self, encoded):
        """
        Return a summary of safe values.

        The result is a dictionary and will be used where the password field
        must be displayed to construct a safe representation of the password.
        """
        split_hash = encoded.split("$", 3)
        assert split_hash[0] == self.algorithm and split_hash[1] == "apr1"

        # The other hashers in django seem to return a small # of characters
        # from the salt and hash but mask the rest. I have no idea why showing
        # any of the salt / hash in a log would be a good idea, so I just return
        # *'s
        return {"algorithm": self.algorithm, "salt": "***", "hash": "******"}

    def harden_runtime(self, password, encoded):
        """This method is not applicalbe to MD5,
        as it does not encode a number of iterations."""
        pass
