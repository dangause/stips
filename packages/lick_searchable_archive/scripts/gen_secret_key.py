"""
Script to generate secret keys suitable for Django.

Arguments: The output file to hold the secret key

The file created will have 660 permissions (read/writable to the owner and group only).
"""

import os
import secrets
import sys

if __name__ == "__main__":
    # Make sure there's an ouptut file given
    if len(sys.argv) < 2:
        print("Output file required.", file=sys.stderr)
        sys.exit(1)

    # Open the output file with the desired 660 permissions
    fd = os.open(sys.argv[1], flags=os.O_WRONLY | os.O_CREAT, mode=0o660)

    key = secrets.token_urlsafe()
    os.write(fd, bytes(key, "UTF-8"))

    os.close(fd)
