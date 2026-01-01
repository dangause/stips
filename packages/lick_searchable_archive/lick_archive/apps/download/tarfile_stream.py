"""
Class for streaming a tarball of multiple files.
"""

import gzip
import io
import logging
import stat
import tarfile
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# Tar file block size
BLOCKSIZE = 512


class TarFileStream:
    """Class for generating a tarball of multiple files in a way suitable for streaming. The class implements the iterator protocol to allow
    iterating through byte strings of the generated tarball.

    The python tarfile.TarFile class also supports this, but it doesn't have a way to iterate over chunks of a generated tarball as needed for a django StreamingResponse.
    So we use the tarfile.TarInfo class to create a iterable tar file.

    Args:
        name:     The name of the resulting tarball. This is only used in the gzip header when using gzip compression.
        files:    A list of files to include in the tarball
        arcfiles: A list of the names that will appear in the tarball for each file. If specified it must be the same length
                  as files. If not specified the file's own name will be used, including the path. Any leading "/" will be stripped.
        enable_gzip: Enables creation of a gzipped tarball.
        format:      The format (as defined in the tarfile module) of the tar file to generate. Defaults to the GNU format.
        chunk_size:  The size (in bytes) of each chunk of data returned by the iterator. Defaults to 100k
    """

    def __init__(
        self,
        name: Path | str,
        files: list[Path | str],
        arcfiles: Optional[list[Path | str]] = None,
        enable_gzip: bool = False,
        format=tarfile.DEFAULT_FORMAT,
        chunk_size: int = 4 * 1024,
    ):
        self.name = Path(name)
        self.files = [Path(file) for file in files]
        if arcfiles is None:
            # If the user didn't specify the archive file names, use the relative form of the input files path
            self.arcfiles = [
                p.relative_to("/") if p.is_absolute() else p for p in self.files
            ]
        elif len(arcfiles) != len(self.files):
            raise ValueError(
                f"When specifying 'arcfiles' the length ({len(arcfiles)}) must match the length of 'files' ({len(self.files)})."
            )
        else:
            self.arcfiles = arcfiles

        self.gzip = enable_gzip
        self.chunk_size = chunk_size
        self.format = format

        # The index of the file within self.files that is currently being read
        self.current_file = -1
        # The fileobject of the file currently being read
        self.current_file_obj = None
        # The size of the file currently being read
        self.current_file_size = 0

        # The buffer that will hold data to be returned by the iterator
        self.stream_buffer = io.BytesIO()

        # If gzipping, create a gzip file object to write the tar file data to.
        # The gzip file writes to the stream buffer
        if self.gzip:
            # Strip gz off name for use in gzip file header if needed
            name = self.name if self.name.suffix != ".gz" else self.name.name[0:-3]

            self.tar_file_stream = gzip.GzipFile(
                filename=self.name, mode="wb", fileobj=self.stream_buffer
            )

            # The gzip header was written to the buffer
            # Set the buffer to be ready to read that data, as expected by __next__
            self.buffer_size = self.stream_buffer.tell()
            self.stream_buffer.seek(0)

        else:
            # Not gzipping, write tar data directly to the stream buffer
            self.tar_file_stream = self.stream_buffer
            self.buffer_size = 0

    def __iter__(self) -> Iterator:
        """Return an iterator for the tar file. Part of the iterator protocol."""
        return self

    def __next__(self) -> bytes:
        """Return the next byte string from the tarball, or raise a StopIteration exception.
        Part of the iterator protocol."""
        amount_in_buffer = self._fill_buffer()

        if amount_in_buffer == 0:
            raise StopIteration()

        if amount_in_buffer >= self.chunk_size:
            return self.stream_buffer.read(self.chunk_size)
        else:
            return self.stream_buffer.read(amount_in_buffer)

    def _fill_buffer(self) -> int:
        """Fill the buffer with a chunk of data, if possible.

        Return:
            int: The amount of unread data in the buffer.
        """
        amount_left_in_buffer = self.buffer_size - self.stream_buffer.tell()
        if self.current_file >= len(self.files):
            # There's nothing left to put in the buffer, let it drain
            return amount_left_in_buffer

        if amount_left_in_buffer < self.chunk_size:
            # Need to fill the buffer, but don't overwrite the current contents
            # I wish there were a deque or similar class that implemented a file object
            # interface bug there isn't and I was too lazy to write one.
            # So I ended up doing the following  to move left over data back to
            # the beginning of the stream buffer
            remainder = self.stream_buffer.read(amount_left_in_buffer)
            self.stream_buffer.seek(0)
            self.stream_buffer.write(remainder)

            while (
                self.stream_buffer.tell() < self.chunk_size
                and self.current_file < len(self.files)
            ):
                self._generate_tarfile_chunk()
            self.buffer_size = self.stream_buffer.tell()
            self.stream_buffer.seek(0)
        return self.buffer_size - self.stream_buffer.tell()

    def _generate_tarfile_chunk(self):
        """Generate the next chunk of tarball data and write it to the internal stream buffer."""

        # Loop until we run out of files or have filled a chunk.
        amount_read = 0
        while amount_read < self.chunk_size and self.current_file < len(self.files):
            if self.current_file_obj is None:
                self._open_next_file()

            # If there was a zero length file, or we've run out of files, there won't be any data to read
            if self.current_file_obj is None:
                return

            source_chunk = self.current_file_obj.read(self.chunk_size)
            if source_chunk is None or len(source_chunk) == 0:

                # Finished with the file
                self.current_file_obj.close()
                self.current_file_obj = None

                # Pad out the file to tarfile block size
                mod, remainder = divmod(self.current_file_size, BLOCKSIZE)
                if remainder != 0:
                    padding = b"\0" * (BLOCKSIZE - remainder)
                    self.tar_file_stream.write(padding)
                continue
            else:
                amount_read = len(source_chunk)
                self.tar_file_stream.write(source_chunk)

    def _open_next_file(self):
        """Open the next file in our file list. This
        will write a header out for the next file, and (if we've reached the end of our file list)
        close out the tar file.

        """
        self.current_file += 1
        if self.current_file >= len(self.files):
            # We're done, close out the tar file with two NUL filled blocks,
            # and the gzip file
            end_of_tar_file = b"\0" * (BLOCKSIZE * 2)
            self.tar_file_stream.write(end_of_tar_file)
            if self.gzip:
                self.tar_file_stream.close()
            self.tar_file_stream = None
            return

        # Generate tar_info for the next file and write it
        tar_info = self._create_tar_info(
            self.files[self.current_file], self.arcfiles[self.current_file]
        )
        self.current_file_size = tar_info.size
        self.tar_file_stream.write(tar_info.tobuf(format=self.format))

        # Don't open a zero length file
        if self.current_file_size > 0:
            # Open the next file
            logger.debug(
                f"Opening {self.files[self.current_file]} for tar file stream."
            )
            self.current_file_obj = open(self.files[self.current_file], "rb")
        else:
            self.current_file_obj = None
            logger.debug(
                f"Not opening zero length file {self.files[self.current_file]}"
            )

    def _create_tar_info(self, file_path: Path, dest_path: Path) -> tarfile.TarInfo:
        logger.debug(
            f"Creating file {dest_path} in tarfile for source file {file_path}"
        )
        stat_info = file_path.stat()
        tar_info = tarfile.TarInfo(name=str(dest_path))
        tar_info.type = tarfile.REGTYPE
        tar_info.size = stat_info.st_size
        tar_info.mtime = stat_info.st_mtime
        tar_info.mode = stat.S_IMODE(stat_info.st_mode)
        tar_info.uid = stat_info.st_uid
        tar_info.gid = stat_info.st_gid
        tar_info.uname = file_path.owner()
        tar_info.gname = file_path.group()
        return tar_info
