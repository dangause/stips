import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from astropy.coordinates import Angle, IllegalSecondWarning
from astropy.logger import AstropyUserWarning
from lick_archive.metadata.data_dictionary import FrameType, Instrument, Telescope
from lick_archive.metadata.metadata_utils import get_hdul_from_text
from lick_archive.metadata.shane_kast import ShaneKastReader


def test_not_shane_kast():
    test_data_dir = Path(__file__).parent / "test_data"

    file = "2019-11_09_AO_s1303-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is False

    reader = ShaneKastReader()
    with pytest.raises(ValueError, match="Version was: 'None'"):
        row = reader.read_row(path, hdul)


def test_red_headers():
    test_data_dir = Path(__file__).parent / "test_data"

    file = "2012-01_02_shane_r36-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_RED
    assert row.filename == str(path)
    assert row.obs_date == datetime(2012, 1, 3, 6, 12, 31, 110000, tzinfo=timezone.utc)
    assert row.ingest_flags == "00000000000000000000000000000001"
    assert row.exptime == 1.0
    assert row.ra == "01:42:48.5"
    assert row.dec == "29:22:13.0"
    assert row.object == "IR flat"
    assert row.program == "NEWCAM"
    assert row.observer == "Silverman"
    assert row.frame_type == FrameType.flat
    assert row.slit_name == "2.0 arcsec"
    assert row.beam_splitter_pos == "d55"
    assert row.grism == "600/4310"
    assert row.grating_name == "300/7500"
    assert row.grating_tilt == 5099

    assert row.apername is None
    assert row.filter1 is None
    assert row.filter2 is None
    assert row.sci_filter is None

    file = "2018-11_16_shane_r1011-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_RED
    # This image uses WCS to store coordinates, so its in decimal degrees
    # instead of hms
    assert row.ra == 343.1081542969
    assert row.dec == 37.27479171753
    assert row.frame_type == FrameType.arc

    assert row.ingest_flags == "00000000000000000000000000000000"

    file = "2019-12_16_shane_r5079-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_RED

    assert row.frame_type == FrameType.unknown
    assert row.ingest_flags == "00000000000000000000001000011001"
    assert row.object is None
    assert row.obs_date == datetime(
        2019, 12, 16, 12, 0, 0, 0, tzinfo=timezone(offset=timedelta(hours=-8))
    )

    file = "2019-05_02_shane_r684-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_RED

    assert row.frame_type == FrameType.bias
    assert row.ingest_flags == "00000000000000000000000000000000"

    file = "2019-05_02_shane_r650-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_RED

    assert row.frame_type == FrameType.science
    assert row.ingest_flags == "00000000000000000000000000000000"

    file = "2012-01_20_shane_r104-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_RED

    assert row.frame_type == FrameType.unknown
    assert row.ingest_flags == "00000000000000000000000000010001"
    assert row.object == ""

    # Older product, no VERSION but INSTRUME and SPSIDE
    file = "2006-08_17_shane_r96-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".ccd"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_RED

    assert row.frame_type == FrameType.arc
    assert row.ingest_flags == "00000000000000000000000000000001"
    assert row.object == "IR arc R2"

    # Older, had "60" as seconds in RA
    with pytest.warns(IllegalSecondWarning):
        file = "2007-08_10_shane_r1014-hdu0.txt"
        hdul = get_hdul_from_text([test_data_dir / file])
        path = Path(file.replace("_", os.sep).replace(".txt", ".ccd"))

        assert ShaneKastReader.can_read(path, hdul) is True

        reader = ShaneKastReader()
        row = reader.read_row(path, hdul)
        assert row.telescope == Telescope.SHANE
        assert row.instrument == Instrument.KAST_RED

        assert row.frame_type == FrameType.flat
        assert row.ingest_flags == "00000000000000000000000000000001"
        assert row.object == "flat"
        assert row.program == "KAST"
        assert row.ra == "14:11:60.0"
        assert row.dec == "+37:25:57.0"
        assert row.coord.ra == Angle("213 deg", unit="rad").value
        assert row.coord.dec == Angle("37.4325 deg", unit="rad").value

    # Older, had no INSTRUME but program and SPSIDE
    file = "2007-08_20_shane_r90-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".ccd"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_RED

    assert row.frame_type == FrameType.flat
    assert row.ingest_flags == "00000000000000000000000000000001"
    assert row.object == "Vis2S flat"
    assert row.program == "KAST"

    # Invalid ra/dec
    file = "2008-03_11_shane_r814-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".ccd"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_RED

    assert row.frame_type == FrameType.science
    assert row.ingest_flags == "00000000000000000000001000000001"
    assert row.object == "test"
    assert row.ra == "29829:03:39.4"
    assert row.dec == "+00:00:00.0"
    assert row.coord is None


def test_blue_headers():
    test_data_dir = Path(__file__).parent / "test_data"

    file = "2012-01_02_shane_b808-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_BLUE
    assert row.ingest_flags == "00000000000000000000000000000001"
    assert row.frame_type == FrameType.science

    file = "2018-11_16_shane_b1004-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_BLUE
    assert row.frame_type == FrameType.arc

    assert row.ingest_flags == "00000000000000000000000000000000"

    file = "2019-05_04_shane_b2-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_BLUE

    assert row.frame_type == FrameType.unknown
    assert row.ingest_flags == "00000000000000000000001000011001"
    assert row.object is None
    assert row.obs_date == datetime(
        2019, 5, 4, 12, 0, 0, 0, tzinfo=timezone(offset=timedelta(hours=-8))
    )

    file = "2019-05_02_shane_b607-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_BLUE

    assert row.frame_type == FrameType.flat
    assert row.ingest_flags == "00000000000000000000000000000000"

    file = "2012-01_18_shane_b1011-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_BLUE

    assert row.frame_type == FrameType.bias
    assert row.ingest_flags == "00000000000000000000000000000001"

    file = "2006-08_17_shane_b100-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".ccd"))

    assert ShaneKastReader.can_read(path, hdul) is True

    reader = ShaneKastReader()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.KAST_BLUE

    assert row.frame_type == FrameType.science
    assert row.ingest_flags == "00000000000000000000000000000001"
    assert row.object == "sn2006eb uv"

    # Has invalid \x00 chars in header
    with pytest.warns(AstropyUserWarning):
        file = "2008-09_16_shane_b7993-hdu0.txt"
        hdul = get_hdul_from_text([test_data_dir / file])
        path = Path(file.replace("_", os.sep).replace(".txt", ".ccd"))

        assert ShaneKastReader.can_read(path, hdul) is True

        reader = ShaneKastReader()
        row = reader.read_row(path, hdul)
        assert row.telescope == Telescope.SHANE
        assert row.instrument == Instrument.KAST_BLUE

        assert row.frame_type == FrameType.dark
        assert row.ingest_flags == "00000000000000000000010000000001"
        assert row.object == "KAST BLUE -108c dark ARAL s8g1"
        assert row.header.find("\x00") == -1
