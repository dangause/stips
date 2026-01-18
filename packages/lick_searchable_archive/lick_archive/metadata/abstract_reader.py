"""
Abstract base class that defines an interface for creating a SQL Alchemy
row from a file. Subclasses that implement this to add support for
instruments in the archive.

The steps to add a new instrument are:

1) Implement a subclass for this class.

2) Add an import for the subclass to reader.py.
"""


class AbstractReader:

    @classmethod
    def can_read(cls, file_path, hdul):
        """
        Determine if a file is supported by this MetadataReader.

        Args:

        file_path (pathlib.Path):
            Path to the file to check. This should be in the Lick Archive directory
            format (YYYY-MM/DD/<instrument>/<file>), as the directory name may be used
            to help identifying the instrument that created the file.

        hdul (None or astropy.io.fits.HDUList):
            An HDUList object if the file is a FITS file, None if it is non-FITS.

        Returns (bool): True if the file is supported, False if it is not.
        """
        return False

    def read_row(self, file_path, hdul, ingest_flags):
        """Read an SQL Alchemy row of metadata from a file.

        Args:

        file_path (pathlib.Path):
            The path of the file to read. This should be in the Lick Archive directory
            format (YYYY-MM/DD/<instrument>/<file>), as the directory name may be used
            to help identifying the instrument that created the file.

        hdul (None or astropy.io.fits.HDUList):
            An HDUList object if the file is a FITS file, None if it is non-FITS.

        ingest_flags (data_dictionary.IngestFlags):
            Any ingest bit flags that were set during the process of opening a FITS file.

        Returns (archive_schema.FileMetadata): A row of metadata read from the file.

        Raises: Exception raised if the file is corrupt or lacks required metadata.
        """

        return None
