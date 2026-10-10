"""StipsTranslator.can_translate: binning_header makes an unbinned profile and
its binned variant mutually exclusive on the same INSTRUME value."""

from lsst.obs.stips.translator import StipsTranslator, _header_binning
from stips import Field, InstrumentProfile, Site


def _profile(name, binning, header="CCDSUM"):
    return InstrumentProfile(
        name=name,
        site=Site(0.0, 0.0, 0.0),
        filters={"B": "b"},
        header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
        camera="camera/x.yaml",
        instrument_header_value="Y4KTest",
        ccd_binning=binning,
        binning_header=header,
    )


class _Unbinned(StipsTranslator):
    profile = _profile("BinTestUnbinned", 1)


class _Binned(StipsTranslator):
    profile = _profile("BinTestBinned", 2)


class _NoCheck(StipsTranslator):
    profile = _profile("BinTestNoCheck", 1, header=None)


def test_header_binning_parses_first_integer():
    assert _header_binning("1 1") == 1
    assert _header_binning("2 2") == 2
    assert _header_binning(2) == 2
    assert _header_binning("x") is None


def test_unbinned_and_binned_are_mutually_exclusive():
    h1 = {"INSTRUME": "Y4KTest", "CCDSUM": "1 1"}
    h2 = {"INSTRUME": "Y4KTest", "CCDSUM": "2 2"}
    assert _Unbinned.can_translate(h1) and not _Binned.can_translate(h1)
    assert _Binned.can_translate(h2) and not _Unbinned.can_translate(h2)


def test_missing_binning_keyword_reads_as_unbinned():
    h = {"INSTRUME": "Y4KTest"}
    assert _Unbinned.can_translate(h)
    assert not _Binned.can_translate(h)


def test_no_binning_header_skips_the_check():
    assert _NoCheck.can_translate({"INSTRUME": "Y4KTest", "CCDSUM": "2 2"})


def test_instrume_mismatch_still_rejects():
    assert not _Unbinned.can_translate({"INSTRUME": "Other", "CCDSUM": "1 1"})
