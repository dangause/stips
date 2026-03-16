"""Tests for parameterized CollectionNames and night_to_day_obs."""

from small_tel_tools.core.pipeline import CollectionNames, night_to_day_obs


class TestCollectionNamesParameterized:
    """Verify CollectionNames uses the prefix parameter."""

    def test_default_prefix_is_nickel(self):
        """Backward compat: no prefix arg defaults to 'Nickel'."""
        cols = CollectionNames("20230519", run_ts="20260312T120000Z")
        assert cols.raw_run == "Nickel/raw/20230519/20260312T120000Z"
        assert cols.calib_chain == "Nickel/calib/current"

    def test_custom_prefix(self):
        """Custom prefix replaces 'Nickel' in all collection names."""
        cols = CollectionNames("20230519", run_ts="20260312T120000Z", prefix="NewTel")
        assert cols.raw_run == "NewTel/raw/20230519/20260312T120000Z"
        assert cols.calib_chain == "NewTel/calib/current"
        assert cols.science_parent == "NewTel/runs/20230519/processCcd/20260312T120000Z"
        assert cols.diff_parent == "NewTel/runs/20230519/diff/20260312T120000Z"
        assert cols.calib_out == "NewTel/calib/20230519"
        assert cols.curated_chain == "NewTel/calib/curated"
        assert cols.cp_bias.startswith("NewTel/cp/20230519/bias/")
        assert cols.cp_flat.startswith("NewTel/cp/20230519/flat/")

    def test_all_properties_use_prefix(self):
        """Every collection name property should contain the prefix."""
        cols = CollectionNames("20230519", run_ts="20260312T120000Z", prefix="Test")
        properties = [
            cols.raw_run,
            cols.cp_bias,
            cols.cp_bias_run,
            cols.cp_flat,
            cols.cp_flat_run,
            cols.curated_run,
            cols.curated_chain,
            cols.calib_out,
            cols.calib_chain,
            cols.science_parent,
            cols.science_run,
            cols.coadd_parent,
            cols.coadd_run,
            cols.diff_parent,
            cols.diff_run,
        ]
        for prop in properties:
            assert prop.startswith("Test/"), f"{prop} doesn't start with 'Test/'"

    def test_backward_compat_positional_only(self):
        """Existing code calling CollectionNames('night') still works."""
        cols = CollectionNames("20230519")
        assert cols.raw_run.startswith("Nickel/raw/20230519/")


class TestNightToDayObs:
    """Verify night_to_day_obs with configurable offset."""

    def test_default_offset_is_1(self):
        """Default offset (+1 day) is backward compatible."""
        assert night_to_day_obs("20230519") == "20230520"

    def test_offset_zero(self):
        """Offset 0 means night == day_obs."""
        assert night_to_day_obs("20230519", day_obs_offset=0) == "20230519"

    def test_offset_one(self):
        """Offset 1 adds one day (Lick Observatory convention)."""
        assert night_to_day_obs("20230519", day_obs_offset=1) == "20230520"

    def test_offset_across_month_boundary(self):
        """Verify offset works across month boundaries."""
        assert night_to_day_obs("20230131", day_obs_offset=1) == "20230201"


class TestFindBadCoordExposuresParam:
    """Verify find_bad_coord_exposures accepts instrument_name."""

    def test_accepts_instrument_name_param(self):
        """Function signature accepts instrument_name keyword arg."""
        import inspect

        from small_tel_tools.core.pipeline import find_bad_coord_exposures

        sig = inspect.signature(find_bad_coord_exposures)
        assert "instrument_name" in sig.parameters

    def test_accepts_day_obs_offset_param(self):
        """Function signature accepts day_obs_offset keyword arg."""
        import inspect

        from small_tel_tools.core.pipeline import find_bad_coord_exposures

        sig = inspect.signature(find_bad_coord_exposures)
        assert "day_obs_offset" in sig.parameters
