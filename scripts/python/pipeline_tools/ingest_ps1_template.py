#!/usr/bin/env python3
"""
Ingest Pan-STARRS1 (PS1) images as templates for DIA in obs_nickel.

This script downloads PS1 stacked images from the STScI MAST archive,
converts them to LSST Exposure format with proper WCS and PhotoCalib,
and ingests them into a Butler repository as template_coadd datasets.

Usage:
    python ingest_ps1_template.py \
        --repo $REPO \
        --ra 150.123 \
        --dec 2.456 \
        --band r \
        --size 0.2 \
        --collection templates/ps1/r \
        --output-dir ./ps1_templates

Requirements:
    - astropy
    - astroquery
    - requests
    - lsst.afw.image
    - lsst.daf.butler
    - lsst.geom
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

# Try importing required packages with helpful error messages
try:
    from astroquery.mast import Observations
except ImportError:
    print("ERROR: astroquery not found. Install with: pip install astroquery")
    sys.exit(1)

try:
    import lsst.afw.image as afwImage
    import lsst.daf.butler as dafButler
    import lsst.geom as geom
    from lsst.afw.image import PhotoCalib
except ImportError:
    print("ERROR: LSST stack not found. Make sure you've run 'setup lsst_distrib'")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# PS1 filter to Nickel filter mapping
PS1_TO_NICKEL_BANDS = {
    "g": "v",  # PS1 g is closest to Nickel V (Johnson V)
    "r": "r",  # PS1 r matches Nickel R (Cousins R)
    "i": "i",  # PS1 i matches Nickel I (Cousins I)
    "z": "i",  # PS1 z → Nickel I (no z in Nickel)
    "y": "i",  # PS1 y → Nickel I (no y in Nickel)
}

# PS1 approximate zeropoints (AB mag for 1 ADU/sec)
# From PS1 documentation: https://outerspace.stsci.edu/display/PANSTARRS/PS1+Image+Cutout+Service
PS1_ZEROPOINTS = {
    "g": 25.0,  # Approximate; actual varies per chip/epoch
    "r": 25.0,
    "i": 25.0,
    "z": 25.0,
    "y": 25.0,
}


def download_ps1_cutout(ra, dec, band, size_deg=0.2, output_dir="."):
    """
    Download PS1 image cutout from STScI MAST archive.

    Parameters
    ----------
    ra : float
        Right ascension in degrees
    dec : float
        Declination in degrees
    band : str
        PS1 band (g, r, i, z, y)
    size_deg : float
        Size of cutout in degrees
    output_dir : str
        Directory to save downloaded FITS file

    Returns
    -------
    str or None
        Path to downloaded FITS file, or None if download failed
    """
    log.info(f"Downloading PS1 {band}-band cutout for RA={ra:.4f}, Dec={dec:.4f}")

    coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")

    # Try PS1 via MAST
    try:
        # Query PS1 stacked images
        obs_table = Observations.query_criteria(
            coordinates=coord,
            radius=size_deg * u.deg,
            obs_collection="PS1",
            filters=band,
            dataproduct_type="image",
        )

        if len(obs_table) == 0:
            log.warning(f"No PS1 {band}-band images found at this position")
            return None

        log.info(f"Found {len(obs_table)} PS1 observations")

        # Get data products for the first observation
        products = Observations.get_product_list(obs_table[0])

        # Filter for stacked images (not warp or diff). The astroquery table
        # columns are MaskedColumn objects, so we cannot use the pandas-style
        # `.str.contains`; do the comparison with numpy instead.
        desc_col = products["description"]
        desc_values = desc_col.filled("") if hasattr(desc_col, "filled") else desc_col
        desc_text = np.asarray(desc_values, dtype=str)

        is_science = products["productType"] == "SCIENCE"
        has_stack = np.char.find(np.char.lower(desc_text), "stack") >= 0

        stack_products = products[is_science & has_stack]

        if len(stack_products) == 0:
            log.warning(
                "No stacked images found, trying alternative download method..."
            )
            return download_ps1_via_ps1images(ra, dec, band, size_deg, output_dir)

        # Download the first stacked image
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        manifest = Observations.download_products(
            stack_products[0:1], download_dir=str(output_path)
        )

        if len(manifest) > 0:
            downloaded_file = manifest["Local Path"][0]
            log.info(f"Downloaded: {downloaded_file}")
            return downloaded_file
        else:
            log.warning("Download failed via MAST, trying alternative...")
            return download_ps1_via_ps1images(ra, dec, band, size_deg, output_dir)

    except Exception as e:
        log.warning(f"MAST download failed: {e}")
        log.info("Trying alternative PS1 image service...")
        return download_ps1_via_ps1images(ra, dec, band, size_deg, output_dir)


def download_ps1_via_ps1images(ra, dec, band, size_deg=0.2, output_dir="."):
    """
    Alternative: Download PS1 cutout via direct image service.

    This uses the PS1 Image Cutout Service which provides on-the-fly cutouts.
    """
    import requests

    log.info(f"Using PS1 image cutout service for {band}-band")

    # Convert size to pixels (PS1 is 0.25"/pixel)
    size_arcsec = size_deg * 3600
    size_pixels = int(size_arcsec / 0.25)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / f"ps1_{band}_ra{ra:.4f}_dec{dec:.4f}.fits"

    # Method 1: Direct fitscut.cgi using getimages service (corrected API)
    try:
        log.info("Trying PS1 ps1filenames.py service...")

        # First get the filename from PS1
        import requests

        getim_url = "https://ps1images.stsci.edu/cgi-bin/ps1filenames.py"
        getim_params = {
            "ra": ra,
            "dec": dec,
            "size": int(size_arcsec),  # in arcsec, not pixels
            "format": "fits",
            "filters": band,
        }

        response = requests.get(getim_url, params=getim_params, timeout=60)

        if response.status_code == 200:
            # Parse response to get FITS URL
            lines = response.text.split("\n")
            fits_urls = [
                line for line in lines if ".fits" in line and "stack" in line.lower()
            ]

            if fits_urls:
                # Extract actual FITS URL (it's usually in format: shortname stack.fits URL)
                fits_url = fits_urls[0].split()[-1]  # Last column is URL

                log.info(f"Found PS1 stack URL: {fits_url}")

                # Download the FITS file
                fits_response = requests.get(fits_url, timeout=180)

                if (
                    fits_response.status_code == 200
                    and len(fits_response.content) > 1000
                ):
                    with open(output_file, "wb") as f:
                        f.write(fits_response.content)
                    log.info(
                        f"Downloaded PS1 stack: {output_file} ({len(fits_response.content)} bytes)"
                    )
                    return str(output_file)
                else:
                    log.warning(
                        f"FITS download failed: status {fits_response.status_code}"
                    )
            else:
                log.warning("No stack FITS files found in ps1filenames response")
        else:
            log.warning(f"ps1filenames.py returned status {response.status_code}")
    except Exception as e:
        log.warning(f"ps1filenames.py method failed: {e}")

    # Method 2: Try using urllib instead of requests (handles redirects better)
    try:
        import urllib.request

        log.info("Trying PS1 with urllib...")
        url = f"https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?ra={ra}&dec={dec}&size={size_pixels}&format=fits&filter={band}"

        with urllib.request.urlopen(url, timeout=180) as response:
            data = response.read()

        if len(data) > 1000:
            with open(output_file, "wb") as f:
                f.write(data)
            log.info(
                f"Downloaded PS1 cutout via urllib: {output_file} ({len(data)} bytes)"
            )
            return str(output_file)
        else:
            log.warning(f"urllib download too small: {len(data)} bytes")
    except Exception as e:
        log.warning(f"urllib method failed: {e}")

    # Method 3: Try wget as subprocess
    try:
        import subprocess

        log.info("Trying PS1 with wget...")
        url = f"https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?ra={ra}&dec={dec}&size={size_pixels}&format=fits&filter={band}"

        result = subprocess.run(
            ["wget", "-O", str(output_file), url], capture_output=True, timeout=180
        )

        if (
            result.returncode == 0
            and output_file.exists()
            and output_file.stat().st_size > 1000
        ):
            log.info(f"Downloaded PS1 cutout via wget: {output_file}")
            return str(output_file)
        else:
            log.warning(f"wget failed: {result.stderr.decode()}")
    except Exception as e:
        log.warning(f"wget method failed: {e}")

    # Method 4: Try curl as subprocess
    try:
        import subprocess

        log.info("Trying PS1 with curl...")
        url = f"https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?ra={ra}&dec={dec}&size={size_pixels}&format=fits&filter={band}"

        result = subprocess.run(
            ["curl", "-o", str(output_file), "-L", url],
            capture_output=True,
            timeout=180,
        )

        if (
            result.returncode == 0
            and output_file.exists()
            and output_file.stat().st_size > 1000
        ):
            log.info(f"Downloaded PS1 cutout via curl: {output_file}")
            return str(output_file)
        else:
            log.warning(f"curl failed: {result.stderr.decode()}")
    except Exception as e:
        log.warning(f"curl method failed: {e}")

    log.error("All PS1 download methods failed")
    log.info("You can manually download from:")
    log.info(
        f"  https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?ra={ra}&dec={dec}&size={size_pixels}&format=fits&filter={band}"
    )
    log.info(f"Save as: {output_file}")
    return None


def convert_ps1_to_lsst_exposure(ps1_fits_path, nickel_band):
    """
    Convert PS1 FITS image to LSST Exposure format.

    Parameters
    ----------
    ps1_fits_path : str
        Path to PS1 FITS file
    nickel_band : str
        Target Nickel band (b, v, r, i)

    Returns
    -------
    lsst.afw.image.ExposureF
        LSST Exposure with WCS and PhotoCalib set
    """
    log.info(f"Converting PS1 image to LSST Exposure (target band: {nickel_band})")

    # Read PS1 FITS and pick the first HDU that actually contains image data.
    with fits.open(ps1_fits_path) as hdul:
        image_hdu = None
        for idx, hdu in enumerate(hdul):
            data = getattr(hdu, "data", None)
            if data is not None and isinstance(data, np.ndarray) and data.ndim >= 2:
                image_hdu = hdu
                image_idx = idx
                break

        if image_hdu is None:
            raise ValueError(f"No image HDU found in PS1 file: {ps1_fits_path}")

        ps1_data = image_hdu.data
        ps1_header = image_hdu.header
        log.info(
            f"Using HDU {image_idx} ('{getattr(image_hdu, 'name', '')}') with shape {ps1_data.shape}"
        )

        # Extract WCS from the image HDU
        ps1_wcs = WCS(ps1_header)

        # Get PS1 filter from header (if available)
        ps1_filter = ps1_header.get("FILTER", ps1_header.get("FILTNAM", "r")).lower()
        if ps1_filter not in PS1_ZEROPOINTS:
            log.warning(f"Unknown PS1 filter '{ps1_filter}', assuming 'r'")
            ps1_filter = "r"

        log.info(f"PS1 filter: {ps1_filter}, image shape: {ps1_data.shape}")

        # Convert WCS to LSST format
        lsst_wcs = convert_astropy_wcs_to_lsst(ps1_wcs)

        # Handle NaN values (replace with 0 and mask)
        ps1_data = np.nan_to_num(ps1_data, nan=0.0, posinf=0.0, neginf=0.0)

        # Create LSST MaskedImage
        masked_image = afwImage.MaskedImageF(ps1_data.shape[1], ps1_data.shape[0])
        masked_image.image.array[:, :] = ps1_data.astype(np.float32)

        # Set mask for zero/bad pixels
        masked_image.mask.array[ps1_data == 0] = masked_image.mask.getPlaneBitMask(
            "BAD"
        )

        # Set variance (rough estimate from background)
        median_val = np.median(ps1_data[ps1_data > 0])
        variance_estimate = np.abs(median_val) if median_val > 0 else 1.0
        masked_image.variance.array[:, :] = variance_estimate

        # Create Exposure
        exposure = afwImage.ExposureF(masked_image)
        exposure.setWcs(lsst_wcs)

        # Set PhotoCalib from PS1 zeropoint
        # PS1 zeropoints are in AB mag for 1 DN/sec
        # Convert to flux calibration: flux = counts * calibration
        ps1_zp = PS1_ZEROPOINTS.get(ps1_filter, 25.0)

        # PhotoCalib expects calibration factor, not magnitude zeropoint
        # flux [nJy] = counts * 10^((23.9 - zeropoint) / 2.5) * 3631e6
        # For simplicity: calibrationMean = 10^(zp/2.5)
        calibration_mean = 10.0 ** (ps1_zp / 2.5)

        photo_calib = PhotoCalib(calibration_mean)
        exposure.setPhotoCalib(photo_calib)

        # Set filter
        filter_label = afwImage.FilterLabel(
            band=nickel_band, physical=nickel_band.upper()
        )
        exposure.setFilter(filter_label)

        log.info(f"Created LSST Exposure: {exposure.getBBox()}")
        log.info(f"  WCS: {lsst_wcs.getPixelOrigin()}")
        log.info(f"  PhotoCalib: {calibration_mean:.2e}")

        return exposure


def convert_astropy_wcs_to_lsst(astropy_wcs):
    """
    Convert Astropy WCS to LSST WCS.

    Parameters
    ----------
    astropy_wcs : astropy.wcs.WCS
        Astropy WCS object

    Returns
    -------
    lsst.afw.geom.SkyWcs
        LSST WCS object
    """
    from lsst.afw.geom import makeSkyWcs

    # Try to create from FITS header
    try:
        # Convert WCS to FITS header
        header = astropy_wcs.to_header()

        # Create metadata for makeSkyWcs
        from lsst.daf.base import PropertyList

        metadata = PropertyList()
        for key, value in header.items():
            if key and value is not None:
                # makeSkyWcs expects native Python scalars/strings
                if isinstance(value, (int, float, bool)):
                    metadata.set(key, value)
                elif isinstance(value, str):
                    metadata.set(key, str(value))

        # Create LSST WCS from metadata
        lsst_wcs = makeSkyWcs(metadata)

        return lsst_wcs

    except Exception as e:
        log.error(f"Failed to convert WCS: {e}")
        raise


def ingest_exposure_to_butler(butler, exposure, ra, dec, band, collection, tract=None):
    """
    Ingest LSST Exposure into Butler as template_coadd.

    Parameters
    ----------
    butler : lsst.daf.butler.Butler
        Butler instance
    exposure : lsst.afw.image.ExposureF
        Exposure to ingest
    ra : float
        Center RA in degrees
    dec : float
        Center Dec in degrees
    band : str
        Nickel band (b, v, r, i)
    collection : str
        Output collection name
    tract : int, optional
        Tract number (will auto-determine if None)

    Returns
    -------
    dict
        Data ID of ingested template
    """
    log.info(f"Ingesting exposure to Butler collection: {collection}")

    # Ensure the dataset type exists (fresh repos may not have template_coadd yet).
    from lsst.daf.butler import DatasetType

    dims = None
    try:
        dt = butler.registry.getDatasetType("template_coadd")
        dims = tuple(
            dt.dimensions.names
        )  # Use .names to get iterable list of dimension names
        log.info(f"Found existing template_coadd with dimensions: {dims}")
    except Exception:
        # Default to instrument-aware dimensions used by diffim templates
        # This matches the Nickel-built templates
        dims = ("instrument", "skymap", "tract", "patch", "band")
        log.info(
            "Dataset type 'template_coadd' not found; registering it with dims %s", dims
        )
        dt = DatasetType(
            name="template_coadd",
            dimensions=dims,
            storageClass="ExposureF",
            universe=butler.dimensions,
        )
        butler.registry.registerDatasetType(dt)

    # Ensure target run/collection exists (registerRun is idempotent).
    try:
        butler.registry.registerRun(collection)
    except Exception:
        # If it already exists (or is a chain), this will fail harmlessly.
        pass

    # Get skymap to determine tract/patch (allow env overrides)
    skymap_name = os.environ.get("SKYMAP_NAME", "nickelRings-v1")
    skymap_collections = os.environ.get("SKYMAPS_CHAIN", "skymaps/nickelRings,skymaps")
    skymap_collections = [
        c.strip() for c in skymap_collections.split(",") if c.strip()
    ] or ["skymaps"]
    try:
        skymap = butler.get(
            "skyMap", skymap=skymap_name, collections=skymap_collections
        )
    except Exception as e:
        log.error(f"Failed to get skymap '{skymap_name}': {e}")
        log.info("Available skymaps:")
        for ref in butler.registry.queryDatasets("skyMap"):
            log.info(f"  - {ref.dataId['skymap']}")
        raise

    # Find tract/patch from coordinates
    coord = geom.SpherePoint(ra, dec, geom.degrees)

    if tract is None:
        tract_info = skymap.findTract(coord)
        tract = tract_info.getId()
        log.info(f"Auto-determined tract: {tract}")
    else:
        tract_info = skymap[tract]

    patch_info = tract_info.findPatch(coord)
    patch = patch_info.getSequentialIndex()

    log.info(f"Target tract={tract}, patch={patch}")

    # Build data ID matching dataset type dimensions
    # Note: For PS1 templates, we don't include instrument dimension to match DIA pipeline expectations
    data_id = {
        "skymap": skymap_name,
        "tract": tract,
        "patch": patch,
        "band": band,
    }
    # Only add instrument/physical_filter if they're in the dataset type dimensions
    # (PS1 templates should NOT have these to work with DIA pipeline)
    if dims and "instrument" in dims:
        data_id["instrument"] = "Nickel"
    if dims and "physical_filter" in dims:
        data_id["physical_filter"] = band.upper()

    # Put exposure into Butler
    try:
        butler.put(exposure, "template_coadd", dataId=data_id, run=collection)
        log.info(f"Successfully ingested template_coadd with dataId: {data_id}")

    except Exception as e:
        log.error(f"Failed to ingest exposure: {e}")
        raise

    return data_id


def main():
    parser = argparse.ArgumentParser(
        description="Ingest PS1 images as templates for Nickel DIA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download and ingest PS1 r-band template
  python ingest_ps1_template.py \\
      --repo /path/to/butler/repo \\
      --ra 150.123 --dec 2.456 \\
      --band r \\
      --collection templates/ps1/r

  # Use existing PS1 FITS file
  python ingest_ps1_template.py \\
      --repo /path/to/butler/repo \\
      --ps1-fits ./ps1_r_myfield.fits \\
      --ra 150.123 --dec 2.456 \\
      --band r \\
      --collection templates/ps1/r \\
      --tract 1099
        """,
    )

    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument(
        "--ra", type=float, required=True, help="Right ascension (degrees)"
    )
    parser.add_argument(
        "--dec", type=float, required=True, help="Declination (degrees)"
    )
    parser.add_argument(
        "--band", required=True, choices=["b", "v", "r", "i"], help="Nickel filter band"
    )
    parser.add_argument(
        "--ps1-band",
        choices=["g", "r", "i", "z", "y"],
        help="PS1 band to download (default: auto-map from --band)",
    )
    parser.add_argument(
        "--size", type=float, default=0.2, help="Cutout size in degrees (default: 0.2)"
    )
    parser.add_argument(
        "--collection", required=True, help="Output collection (e.g., templates/ps1/r)"
    )
    parser.add_argument(
        "--tract", type=int, help="Sky tract (auto-determined if not provided)"
    )
    parser.add_argument(
        "--output-dir",
        default="./ps1_templates",
        help="Directory for downloaded FITS files",
    )
    parser.add_argument(
        "--ps1-fits", help="Use existing PS1 FITS file instead of downloading"
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download (use with --ps1-fits)",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Download only, do not ingest to Butler",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    # Map Nickel band to PS1 band if not specified
    if args.ps1_band is None:
        # Default mapping: r→r, i→i, v→g, b→g
        ps1_band_map = {"r": "r", "i": "i", "v": "g", "b": "g"}
        args.ps1_band = ps1_band_map.get(args.band, "r")
        log.info(f"Auto-mapped Nickel {args.band} → PS1 {args.ps1_band}")

    # Step 1: Download or use existing PS1 FITS
    if args.ps1_fits:
        ps1_fits_path = args.ps1_fits
        if not os.path.exists(ps1_fits_path):
            log.error(f"PS1 FITS file not found: {ps1_fits_path}")
            sys.exit(1)
    elif not args.skip_download:
        ps1_fits_path = download_ps1_cutout(
            args.ra, args.dec, args.ps1_band, args.size, args.output_dir
        )

        if ps1_fits_path is None:
            log.error("Failed to download PS1 image")
            sys.exit(1)
    else:
        log.error("Must provide --ps1-fits when using --skip-download")
        sys.exit(1)

    # Step 2: Convert to LSST Exposure
    exposure = convert_ps1_to_lsst_exposure(ps1_fits_path, args.band)

    # Optional: Save as LSST FITS for inspection
    lsst_fits_path = Path(args.output_dir) / f"lsst_template_{args.band}.fits"

    # Only write if it doesn't already exist (avoid overwriting when using --ps1-fits)
    if not lsst_fits_path.exists() or str(lsst_fits_path) != ps1_fits_path:
        exposure.writeFits(str(lsst_fits_path))
        log.info(f"Saved LSST Exposure to: {lsst_fits_path}")
    else:
        log.info(f"Using existing LSST Exposure: {lsst_fits_path}")

    if args.skip_ingest:
        log.info("Skipping Butler ingest (--skip-ingest)")
        log.info(f"Template FITS saved to: {lsst_fits_path}")
        return 0

    # Step 3: Ingest to Butler
    butler = dafButler.Butler(args.repo, writeable=True)

    data_id = ingest_exposure_to_butler(
        butler, exposure, args.ra, args.dec, args.band, args.collection, args.tract
    )

    log.info("=" * 60)
    log.info("SUCCESS: PS1 template ingested!")
    log.info(f"  Collection: {args.collection}")
    log.info(f"  Data ID: {data_id}")
    log.info(f"  FITS file: {lsst_fits_path}")
    log.info("")
    log.info("Next steps:")
    log.info(
        f"  1. Verify template: butler query-datasets {args.repo} template_coadd \\"
    )
    log.info(f"       --collections {args.collection}")
    log.info("  2. Run DIA: ./scripts/pipeline/40_diff_imaging.sh \\")
    log.info(f"       --night YYYYMMDD --template {args.collection}")
    log.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
