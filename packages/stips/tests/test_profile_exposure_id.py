"""Unit tests for the shared 31-bit exposure-id scheme.

``pack_exposure_id`` owns the packing and the guards; ``make_exposure_id`` is a
thin wrapper that derives the day term from an end-of-exposure ``Time``. The two
instruments differ ONLY in which day number they feed in (Nickel: the UT day of
``datetime_end``; CTIO: the local observing night from the frame filename), which
is exactly the seam these tests pin.
"""

import astropy.time
import pytest
from stips import EXPOSURE_ID_EPOCH, make_exposure_id, pack_exposure_id


def test_pack_exposure_id_packs_day_and_seq():
    assert pack_exposure_id(4178, 42) == 41780042


def test_pack_exposure_id_rejects_seqnum_at_or_above_10000():
    # A 5-digit seqnum would silently carry into the day term and alias onto a
    # different day's id. Y4KCam's 4-digit filename field makes this reachable.
    with pytest.raises(ValueError, match="seqnum"):
        pack_exposure_id(4178, 10000)


def test_pack_exposure_id_rejects_negative_seqnum():
    with pytest.raises(ValueError, match="seqnum"):
        pack_exposure_id(4178, -1)


def test_pack_exposure_id_rejects_ids_beyond_31_bits():
    with pytest.raises(ValueError, match="31-bit"):
        pack_exposure_id(300000, 1)


def test_make_exposure_id_delegates_to_pack():
    # 2011-06-10T00:00:00 UTC is 4178 days after the 2000-01-01 epoch.
    end = astropy.time.Time("2011-06-10T00:00:00", scale="utc")
    assert make_exposure_id(end, 42) == pack_exposure_id(4178, 42) == 41780042


def test_make_exposure_id_epoch_day_zero():
    end = astropy.time.Time(EXPOSURE_ID_EPOCH, scale="utc")
    assert make_exposure_id(end, 7) == 7
