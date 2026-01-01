import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lick_archive.metadata.data_dictionary import FrameType, Instrument, Telescope
from lick_archive.metadata.metadata_utils import get_hdul_from_text
from lick_archive.metadata.shane_ao_sharcs import ShaneAO_ShARCS


def test_ao_sharcs():
    test_data_dir = Path(__file__).parent / "test_data"

    # Test flats
    # Flat in object name, lamps in header but none set
    file = "2014-05_20_AO_s0002-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(
        2014, 5, 20, 22, 49, 25, 515000, tzinfo=timezone.utc
    )
    assert row.ingest_flags == "00000000000000000000000000000110"
    assert row.exptime == 0.9797
    assert row.ra == "08:37:44.74"
    assert row.dec == "37:22:13.2"
    assert row.object == "domeflats"
    assert row.program == "Keplertargets"
    assert row.observer == "Wolfgang"
    assert row.airmass == 1.00097284
    assert row.frame_type == FrameType.flat
    assert row.slit_name == None
    assert row.beam_splitter_pos == None
    assert row.grism == None
    assert row.grating_name == None
    assert row.grating_tilt == None

    assert row.apername == "Slit-100um-H"
    assert row.filter1 == "CaF-Kgrism"
    assert row.filter2 == "K"
    assert row.sci_filter is None

    # Test date from directory name
    file = "2014-05_20_AO_s0051-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(
        2014, 5, 20, 12, 0, 0, 0, tzinfo=timezone(timedelta(hours=-8))
    )
    assert row.ingest_flags == "00000000000000000000000000001010"
    assert row.exptime == 29.0958
    assert row.frame_type == FrameType.flat

    # Date from date-obs/time-obs
    # frame type frame from lamps set to 'T', not object
    file = "2014-04_16_AO_m140417-1203-1-modified-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(2014, 4, 16, 22, 32, 10, 4000, tzinfo=timezone.utc)
    assert row.ingest_flags == "00000000000000000000001000000110"
    assert row.frame_type == FrameType.flat

    # frame type frame from lamps set to 'on', not object
    file = "2014-05_19_AO_m140520-0441-modified-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.ingest_flags == "00000000000000000000000000000110"
    assert row.frame_type == FrameType.flat

    # Test arcs

    # Date from date-obs/time-obs
    # frame type arc from CALYNAM, not object
    file = "2014-04_16_AO_m140417-1203-1-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(2014, 4, 16, 22, 32, 10, 4000, tzinfo=timezone.utc)
    assert row.ingest_flags == "00000000000000000000001000000110"
    assert row.frame_type == FrameType.arc

    # Does not have the CALYNAM value for arcs, but has arc in the object,
    # this should not be an arc
    file = "2014-04_16_AO_m140417-1202-modified-2-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.ingest_flags == "00000000000000000000001000000110"
    assert row.frame_type == FrameType.flat

    # Does not have CALYNAM at all in header, but has arc in the object,
    # this should be an arc
    file = "2014-04_16_AO_m140417-1202-modified-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.ingest_flags == "00000000000000000000001000000110"
    assert row.frame_type == FrameType.arc

    # Test darks
    # This has FILT2NAM set to indicate a dark, but no dark in the object name
    file = "2019-04_16_AO_s0545-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.ingest_flags == "00000000000000000000000000000000"
    assert row.frame_type == FrameType.dark

    # This has dark in the object name, but doesn't have the FILT2NAM value to indicate it is one.
    # This should not be a dark
    file = "2019-11_09_AO_s1303-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.ingest_flags == "00000000000000000000000000000000"
    assert row.frame_type == FrameType.science

    # This has dark in the object name, but doesn't have the FILT2NAM at all in the header.
    # This should be a dark
    file = "2019-11_09_AO_s1303-modified-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.ingest_flags == "00000000000000000000000000000000"
    assert row.frame_type == FrameType.dark

    # Test files missing most metadata
    file = "2014-05_20_AO_s0010-001-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(
        2014, 5, 20, 12, 0, 0, 0, tzinfo=timezone(offset=timedelta(hours=-8))
    )
    assert row.ingest_flags == "00000000000000000000001000011011"
    assert row.exptime == None
    assert row.ra == None
    assert row.dec == None
    assert row.object == None
    assert row.program == None
    assert row.observer == None
    assert row.frame_type == FrameType.unknown
    assert row.slit_name == None
    assert row.beam_splitter_pos == None
    assert row.grism == None
    assert row.grating_name == None
    assert row.grating_tilt == None

    assert row.apername is None
    assert row.filter1 is None
    assert row.filter2 is None
    assert row.sci_filter is None

    file = "2014-05_20_AO_s0011-1-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(2014, 5, 20, 23, 15, 39, 78000, tzinfo=timezone.utc)
    assert row.ingest_flags == "00000000000000000000001000010111"
    assert row.exptime == (0.09797 * 2)
    assert row.frame_type == FrameType.unknown

    # Test assignment of science frame type

    file = "2018-11_20_AO_s0066-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(
        2018, 11, 21, 7, 56, 19, 755000, tzinfo=timezone.utc
    )
    assert row.ingest_flags == "00000000000000000000000000000000"
    assert row.ra == 41.843781
    assert row.dec == 43.401867
    assert row.frame_type == FrameType.science

    assert row.apername == "Open"
    assert row.filter1 == "BrG-2.16"
    assert row.filter2 == "Open"
    assert row.sci_filter is None

    # Test empty object = unknown frame type
    file = "2019-04_21_AO_s0180-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.ingest_flags == "00000000000000000000000000010000"
    assert row.object == ""
    assert row.frame_type == FrameType.unknown

    # Test no object in header = unknown frame type
    file = "2019-07_18_AO_s1173-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(
        2019, 7, 18, 22, 52, 14, 273000, tzinfo=timezone.utc
    )
    assert row.ingest_flags == "00000000000000000000001000010001"
    assert row.object is None
    assert row.frame_type == FrameType.unknown

    # Test invalid DATE-BEG
    file = "2014-07_16_AO_s0196-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(
        2014, 7, 16, 21, 55, 15, 624000, tzinfo=timezone.utc
    )
    assert row.ingest_flags == "00000000000000000000001000010111"
    assert row.frame_type == FrameType.unknown

    # Test invalid TIME-OBS with no DATE-BEG
    file = "2014-07_16_AO_s0196-modified-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))

    assert ShaneAO_ShARCS.can_read(path, hdul) is True

    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    assert row.telescope == Telescope.SHANE
    assert row.instrument == Instrument.SHARCS
    assert row.obs_date == datetime(
        2014, 7, 16, 12, 0, 0, 0, tzinfo=timezone(offset=timedelta(hours=-8))
    )
    assert row.ingest_flags == "00000000000000000000001000011011"
    assert row.frame_type == FrameType.unknown
