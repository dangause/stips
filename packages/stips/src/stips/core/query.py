"""Helpers for safely building Butler query (WHERE) expressions.

Butler WHERE strings are interpolated with user- and header-derived values
(``--object`` target names, FITS ``target_name`` headers, Landolt catalog
names, filter bands). Those values must never be able to break out of the
surrounding string literal or inject additional query terms.

Rather than attempt to escape Butler's (under-specified) expression grammar, we
validate every value against a conservative allow-list and *reject* anything
outside it with a clear error. The allow-list was chosen to cover every real
target/band value in the repo:

  * SN designations (``2023ixf``, ``2020wnt``)
  * catalog identifiers (``HAT-P-32``, ``PG1047+003``, ``PG1633+099``,
    ``AC_Andromedae``, ``V0678-Oph``)
  * Landolt ``fits_object`` names (``107_458``, ``PG1323-086``)
  * single-letter photometric bands (``b``, ``v``, ``r``, ``i``)

i.e. letters, digits, underscore, space, ``.``, ``+`` and ``-``. Reject-with-
error is safer than escaping here because Butler's literal-quoting rules are not
clearly specified; a target name containing a quote is far more likely to be a
mistake (or an attack) than a legitimate value.
"""

from __future__ import annotations

import re

# Word chars (letters/digits/underscore), space, dot, plus, hyphen.
_SAFE_LITERAL = re.compile(r"[\w .+-]+")


def butler_str_literal(value: str) -> str:
    """Return ``value`` as a validated, single-quoted Butler string literal.

    Args:
        value: The value to embed in a Butler WHERE expression (e.g. a target
            name or band). Coerced to ``str``.

    Returns:
        The value wrapped in single quotes, ready to interpolate into a WHERE
        clause (e.g. ``'2023ixf'``).

    Raises:
        ValueError: If the value is empty or contains any character outside the
            conservative allow-list (which could break out of the string
            literal or inject additional query terms).
    """
    text = str(value)
    if not _SAFE_LITERAL.fullmatch(text):
        raise ValueError(
            f"Unsafe value for a Butler query literal: {value!r}. "
            "Allowed characters: letters, digits, underscore, space, '.', "
            "'+', '-'. Reject rather than risk WHERE-clause injection."
        )
    return f"'{text}'"
