"""DIA selects exposures by the same object-name resolution science uses.

Science resolves ``--object`` with a case-insensitive substring match; DIA used
to match the raw string exactly. On 2023ixf 20230815 the FITS OBJECT is
"sn2023ixf", so science calibrated those frames and DIA then found none
("empty quantum graph"), silently losing the epoch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core import dia, science  # noqa: E402


def test_no_object_filter_adds_nothing():
    assert dia._object_expr(None, object(), "20230815") == ""


def test_uses_the_name_science_resolves():
    with patch.object(science, "resolve_object_filter", return_value="sn2023ixf") as r:
        expr = dia._object_expr("2023ixf", "cfg", "20230815")
    r.assert_called_once_with("2023ixf", "cfg", "20230815")
    assert expr == " AND exposure.target_name='sn2023ixf'"


def test_falls_back_to_the_raw_filter_when_unresolved():
    with patch.object(science, "resolve_object_filter", return_value=None):
        assert (
            dia._object_expr("2023ixf", "cfg", "20230815")
            == " AND exposure.target_name='2023ixf'"
        )
