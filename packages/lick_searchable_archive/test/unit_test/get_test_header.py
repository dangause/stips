#### Helper script to read a fits header into a text file for use
# by unit tests

import argparse
import sys

from astropy.io import fits


def get_parser():
    parser = argparse.ArgumentParser(
        description="Read the header from a fits file and write it to a text file for use in a unit test."
    )
    parser.add_argument("fits_file", type=str, help="The fits file to read")
    parser.add_argument(
        "output_base",
        type=str,
        help='Base ame of the output text file. A "_hduN.txt" will be added to it based on which hdu the header was read from',
    )
    return parser


def main(args):
    with fits.open(args.fits_file) as hdul:
        i = 0
        for hdu in hdul:
            hdu.header.tofile(
                f"{args.output_base}-hdu{i}.txt", sep="\n", endcard=False, padding=False
            )
            i += 1


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
