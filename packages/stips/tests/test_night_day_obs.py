"""Unit tests for the shared two-UT-day ``day_obs`` helper (finding F-007).

A single local observing night spans two UT days (pre-/post-midnight). The
helpers ``night_day_obs_values`` / ``night_day_obs_expr`` centralize that logic
so every Butler query (science, DIA, forced photometry, coordinate validation)
selects BOTH days instead of silently dropping pre-midnight exposures.
"""

import inspect
from types import SimpleNamespace

from stips.core import dia, fphot
from stips.core.pipeline import night_day_obs_expr, night_day_obs_values


def _profile(offset_days: int = 1):
    return SimpleNamespace(night_to_dayobs_offset_days=offset_days)


class TestNightDayObsValues:
    def test_default_offset_emits_two_distinct_days(self):
        # profile=None -> default offset of 1 (Nickel-correct).
        assert night_day_obs_values("20230519") == (20230519, 20230520)

    def test_profile_offset_used(self):
        assert night_day_obs_values("20230519", _profile(1)) == (20230519, 20230520)

    def test_offset_two_spans_correct_days(self):
        assert night_day_obs_values("20230519", _profile(2)) == (20230519, 20230521)

    def test_zero_offset_collapses_to_single_day(self):
        assert night_day_obs_values("20230519", _profile(0)) == (20230519,)

    def test_explicit_offset_overrides_profile(self):
        assert night_day_obs_values("20230519", _profile(1), offset_days=0) == (
            20230519,
        )

    def test_year_boundary(self):
        assert night_day_obs_values("20231231") == (20231231, 20240101)


class TestNightDayObsExpr:
    def test_two_day_in_clause(self):
        assert (
            night_day_obs_expr("20230519", _profile(1))
            == "day_obs IN (20230519, 20230520)"
        )

    def test_custom_column(self):
        assert (
            night_day_obs_expr("20230519", _profile(1), column="exposure.day_obs")
            == "exposure.day_obs IN (20230519, 20230520)"
        )

    def test_single_day_when_offset_collapses(self):
        assert night_day_obs_expr("20230519", _profile(0)) == "day_obs=20230519"

    def test_default_profile_none(self):
        assert night_day_obs_expr("20230519") == "day_obs IN (20230519, 20230520)"


class TestCallSitesUseHelper:
    """Guard against regressing to a single-day ``day_obs={day_obs}`` query."""

    def test_dia_emits_two_day_clause_via_helper(self):
        src = inspect.getsource(dia.run)
        assert "night_day_obs_expr(night, prof)" in src
        assert "day_obs={day_obs}" not in src

    def test_fphot_emits_two_day_clause_via_helper(self):
        src = inspect.getsource(fphot.run)
        assert "night_day_obs_expr(night, prof)" in src
        assert "day_obs={day_obs}" not in src
