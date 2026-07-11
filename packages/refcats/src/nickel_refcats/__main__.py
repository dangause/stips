"""Deprecated entry point for ``python -m nickel_refcats``.

Importing this triggers the :mod:`nickel_refcats` deprecation warning and
delegates to :func:`stips_refcats.cli.main`. Use ``python -m stips_refcats``
(or the ``stips-refcats`` console script) instead.
"""

from stips_refcats.cli import main

if __name__ == "__main__":
    main()
