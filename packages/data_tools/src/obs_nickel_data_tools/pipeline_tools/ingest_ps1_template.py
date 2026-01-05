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
    import lsst.afw.detection as afwDetection
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

# PS1 zeropoints (AB mag for 1 DN/sec)
# From PS1 DR2: https://outerspace.stsci.edu/display/PANSTARRS/PS1+Stack+images
# These are typical values; actual zeropoints are in FITS headers (FPA.ZP or ZPT keywords)
PS1_ZEROPOINTS = {
    "g": 25.0,
    "r": 25.0,
    "i": 25.0,
    "z": 24.5,
    "y": 23.5,
}

# PS1 effective wavelengths (Angstroms) for colorterm calculations
PS1_EFFECTIVE_WAVELENGTHS = {
    "g": 4866,
    "r": 6215,
    "i": 7545,
    "z": 8679,
    "y": 9633,
}


def ps1_file_covers_target(ps1_fits_path, ra, dec):
    """
    Check whether a PS1 FITS file actually covers the requested sky position.
    """
    try:
        with fits.open(ps1_fits_path) as hdul:
            image_hdu = next(
                (
                    hdu
                    for hdu in hdul
                    if getattr(hdu, "data", None) is not None
                    and isinstance(hdu.data, np.ndarray)
                    and hdu.data.ndim >= 2
                ),
                None,
            )
            if image_hdu is None:
                log.warning(
                    f"  No image HDU found when checking coverage for {ps1_fits_path}"
                )
                return False

            wcs = WCS(image_hdu.header)
            x, y = wcs.all_world2pix(ra, dec, 0)
            ny, nx = image_hdu.data.shape

            inside = np.all(np.isfinite([x, y])) and (0 <= x < nx) and (0 <= y < ny)
            log.info(
                f"  Target pixel in PS1 image: x={x:.1f}, y={y:.1f} (image size {nx}x{ny})"
            )
            if not inside:
                log.warning(
                    "  Target is outside PS1 image footprint; will try another download method"
                )
            return inside
    except Exception as e:
        log.warning(f"  Coverage check failed for {ps1_fits_path}: {e}")
        return False


def download_ps1_cutout(
    ra, dec, band, size_deg=0.2, output_dir=".", force_service=None
):
    """
    Download PS1 image cutout from STScI MAST archive or PS1 image service.

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
    force_service : str, optional
        Force specific download method: 'mast', 'fitscut', or 'ps1filenames'

    Returns
    -------
    str or None
        Path to downloaded FITS file, or None if download failed
    """
    log.info(f"Downloading PS1 {band}-band cutout for RA={ra:.4f}, Dec={dec:.4f}")
    log.info(f"  Cutout size: {size_deg:.3f} degrees ({size_deg*60:.1f} arcmin)")

    coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / f"ps1_{band}_ra{ra:.4f}_dec{dec:.4f}.fits"

    # Check if file already exists
    if output_file.exists() and output_file.stat().st_size > 10000:
        if ps1_file_covers_target(output_file, ra, dec):
            log.info(f"Using existing file: {output_file}")
            return str(output_file)
        log.warning(
            f"Existing PS1 file {output_file} does not cover target; re-downloading"
        )
        try:
            output_file.unlink()
        except Exception as e:
            log.warning(f"  Could not remove stale PS1 file: {e}")

    # Method 1: Try PS1 via MAST (most reliable for stacked images)
    if force_service is None or force_service == "mast":
        try:
            log.info("Method 1: Trying MAST archive...")
            # Query PS1 stacked images with more specific criteria
            obs_table = Observations.query_criteria(
                coordinates=coord,
                radius=size_deg * u.deg,
                obs_collection="PS1",
                filters=band,
                dataproduct_type="image",
            )

            if len(obs_table) > 0:
                log.info(f"  Found {len(obs_table)} PS1 observations")

                # Get data products for the first observation
                products = Observations.get_product_list(obs_table[0])

                # Filter for stacked images (not warp or diff)
                desc_col = products["description"]
                desc_values = (
                    desc_col.filled("") if hasattr(desc_col, "filled") else desc_col
                )
                desc_text = np.asarray(desc_values, dtype=str)

                is_science = products["productType"] == "SCIENCE"
                has_stack = np.char.find(np.char.lower(desc_text), "stack") >= 0

                stack_products = products[is_science & has_stack]

                if len(stack_products) > 0:
                    log.info(f"  Found {len(stack_products)} stack products")

                    # Download to temporary location
                    temp_dir = output_path / "temp_mast"
                    temp_dir.mkdir(exist_ok=True)

                    manifest = Observations.download_products(
                        stack_products[0:1], download_dir=str(temp_dir)
                    )

                    if len(manifest) > 0 and Path(manifest["Local Path"][0]).exists():
                        downloaded_file = manifest["Local Path"][0]
                        # Move to final location
                        import shutil

                        shutil.copy(downloaded_file, output_file)
                        log.info(f"  Successfully downloaded via MAST: {output_file}")
                        if ps1_file_covers_target(output_file, ra, dec):
                            return str(output_file)
                        log.warning(
                            "  MAST download does not cover target; trying alternate service"
                        )
                        try:
                            output_file.unlink()
                        except Exception:
                            pass
                else:
                    log.warning("  No stack products found in MAST results")
            else:
                log.warning(f"  No PS1 {band}-band observations found at this position")

        except Exception as e:
            log.warning(f"  MAST download failed: {e}")

    # Method 2: Try PS1 image service (fitscut) - more reliable for cutouts
    if force_service is None or force_service == "fitscut":
        result = download_ps1_via_fitscut(ra, dec, band, size_deg, output_file)
        if result and ps1_file_covers_target(result, ra, dec):
            return result
        if result:
            try:
                Path(result).unlink()
            except Exception:
                pass

    # Method 3: Try ps1filenames service for full stack URLs
    if force_service is None or force_service == "ps1filenames":
        result = download_ps1_via_ps1filenames(ra, dec, band, size_deg, output_file)
        if result and ps1_file_covers_target(result, ra, dec):
            return result
        if result:
            try:
                Path(result).unlink()
            except Exception:
                pass

    log.error("All PS1 download methods failed")
    log.info("You can manually download from:")
    size_pixels = int(size_deg * 3600 / 0.25)
    log.info(
        f"  https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?ra={ra}&dec={dec}&size={size_pixels}&format=fits&filter={band}"
    )
    log.info(f"Save as: {output_file}")
    return None


def download_ps1_via_fitscut(ra, dec, band, size_deg, output_file):
    """
    Download PS1 cutout via fitscut.cgi service (on-the-fly cutouts).

    This is the most reliable method for custom-sized cutouts.
    """
    import requests

    log.info("Method 2: Trying PS1 fitscut.cgi service...")

    # Convert size to pixels (PS1 is 0.25"/pixel)
    requested_pixels = int(size_deg * 3600 / 0.25)
    max_pixels = 10000  # fitscut returns 400 for very large cutouts; cap to keep requests successful

    sizes_to_try = []
    capped = min(requested_pixels, max_pixels)
    if capped < requested_pixels:
        log.warning(
            f"  Requested cutout {requested_pixels}px exceeds fitscut limit {max_pixels}px; using {capped}px instead"
        )
    sizes_to_try.append(capped)
    # Add a couple of fallback sizes in case the first request is still too big for the service
    for fallback in (8000, 6000):
        if fallback < sizes_to_try[-1]:
            sizes_to_try.append(fallback)

    url = "https://ps1images.stsci.edu/cgi-bin/fitscut.cgi"

    for idx, size_pixels in enumerate(sizes_to_try):
        params = {
            "ra": ra,
            "dec": dec,
            "size": size_pixels,
            "format": "fits",
            "filter": band,
        }

        try:
            log.info(f"  Requesting cutout: {size_pixels}x{size_pixels} pixels")
            response = requests.get(url, params=params, timeout=180)

            if response.status_code == 200 and len(response.content) > 10000:
                with open(output_file, "wb") as f:
                    f.write(response.content)
                log.info(
                    f"  Successfully downloaded via fitscut: {output_file} ({len(response.content)} bytes)"
                )
                return str(output_file)

            log.warning(
                f"  fitscut failed: status {response.status_code}, size {len(response.content)} bytes"
            )
        except Exception as e:
            log.warning(f"  fitscut method failed: {e}")

        if idx < len(sizes_to_try) - 1:
            log.info("  Retrying fitscut with a smaller cutout...")

    return None


def download_ps1_via_ps1filenames(ra, dec, band, size_deg, output_file):
    """
    Download PS1 full stack image via ps1filenames.py service.

    This gets the full stacked image URL and downloads it (no custom cutout).
    """
    import requests

    log.info("Method 3: Trying PS1 ps1filenames.py service...")

    size_arcsec = int(size_deg * 3600)

    getim_url = "https://ps1images.stsci.edu/cgi-bin/ps1filenames.py"
    getim_params = {
        "ra": ra,
        "dec": dec,
        "size": size_arcsec,
        "format": "fits",
        "filters": band,
    }

    try:
        response = requests.get(getim_url, params=getim_params, timeout=60)

        if response.status_code == 200:
            # Parse response to get FITS URL
            lines = [line.strip() for line in response.text.split("\n") if line.strip()]
            if len(lines) <= 1:
                log.warning("  No stack FITS files found in ps1filenames response")
                return None

            header = lines[0].split()
            filename_idx = header.index("filename") if "filename" in header else 7
            type_idx = header.index("type") if "type" in header else None
            bad_idx = header.index("badflag") if "badflag" in header else None

            fits_path = None
            for line in lines[1:]:
                parts = line.split()
                if len(parts) <= filename_idx:
                    continue
                if type_idx is not None and parts[type_idx].lower() != "stack":
                    continue
                if bad_idx is not None and parts[bad_idx] != "0":
                    continue
                fits_path = parts[filename_idx]
                break

            if fits_path is None:
                log.warning("  No suitable stack entries in ps1filenames response")
                return None

            fits_url = f"https://ps1images.stsci.edu{fits_path}"
            log.info(f"  Found PS1 stack URL: {fits_url}")

            # Download the FITS file
            fits_response = requests.get(fits_url, timeout=180)

            if fits_response.status_code == 200 and len(fits_response.content) > 10000:
                with open(output_file, "wb") as f:
                    f.write(fits_response.content)
                log.info(
                    f"  Successfully downloaded via ps1filenames: {output_file} ({len(fits_response.content)} bytes)"
                )
                return str(output_file)
            else:
                log.warning(
                    f"  FITS download failed: status {fits_response.status_code}"
                )
        else:
            log.warning(f"  ps1filenames.py returned status {response.status_code}")
    except Exception as e:
        log.warning(f"  ps1filenames.py method failed: {e}")

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
        center = ps1_wcs.all_pix2world(ps1_data.shape[1] / 2, ps1_data.shape[0] / 2, 0)
        log.info(f"  PS1 image center (WCS): RA={center[0]:.4f}, Dec={center[1]:.4f}")

        # Get PS1 filter from header (if available)
        ps1_filter = ps1_header.get("FILTER", ps1_header.get("FILTNAM", "r")).lower()
        if ps1_filter not in PS1_ZEROPOINTS:
            log.warning(f"Unknown PS1 filter '{ps1_filter}', assuming 'r'")
            ps1_filter = "r"

        # Extract PS1 zeropoint from FITS header (various possible keywords)
        ps1_zp_keywords = ["ZPT", "FPA.ZP", "MAGZERO", "MAGZPT"]
        ps1_zp = None
        for keyword in ps1_zp_keywords:
            if keyword in ps1_header:
                ps1_zp = float(ps1_header[keyword])
                log.info(f"Found PS1 zeropoint in header[{keyword}]: {ps1_zp:.3f}")
                break

        if ps1_zp is None:
            ps1_zp = PS1_ZEROPOINTS.get(ps1_filter, 25.0)
            log.warning(
                f"No zeropoint in FITS header, using default for {ps1_filter}: {ps1_zp:.3f}"
            )

        log.info(f"PS1 filter: {ps1_filter}, image shape: {ps1_data.shape}")
        log.info(f"PS1 zeropoint (AB mag): {ps1_zp:.3f}")

        # Convert WCS to LSST format
        lsst_wcs = convert_astropy_wcs_to_lsst(ps1_wcs)

        # Handle NaN and bad values
        # NOTE: Do NOT mask negative pixels - sky-subtracted images legitimately have negative values
        bad_mask = ~np.isfinite(ps1_data)
        ps1_data = np.nan_to_num(ps1_data, nan=0.0, posinf=0.0, neginf=0.0)

        # Create LSST MaskedImage
        masked_image = afwImage.MaskedImageF(ps1_data.shape[1], ps1_data.shape[0])
        masked_image.image.array[:, :] = ps1_data.astype(np.float32)

        # Set mask for zero/bad pixels
        masked_image.mask.array[bad_mask] = masked_image.mask.getPlaneBitMask("BAD")

        # Set variance (improved estimate from image statistics)
        good_pixels = ps1_data[~bad_mask]
        if len(good_pixels) > 100:
            # Use median absolute deviation for robust variance estimate
            median_val = np.median(good_pixels)
            mad = np.median(np.abs(good_pixels - median_val))
            variance_estimate = (1.4826 * mad) ** 2  # Convert MAD to std dev
            # Add Poisson noise estimate
            variance_estimate = np.maximum(variance_estimate, np.abs(good_pixels))
            masked_image.variance.array[:, :] = variance_estimate.mean()
            log.info(f"Variance estimate: {variance_estimate.mean():.2f} (from MAD)")
        else:
            variance_estimate = 1.0
            masked_image.variance.array[:, :] = variance_estimate
            log.warning("Too few good pixels for variance estimate, using 1.0")

        # Create Exposure
        exposure = afwImage.ExposureF(masked_image)
        exposure.setWcs(lsst_wcs)

        # Set PhotoCalib to unity to match Nickel calibrated images.
        # Record PS1 zeropoint in metadata instead of scaling counts.
        calibration_mean = 1.0
        exposure.setPhotoCalib(PhotoCalib(calibration_mean))

        # Set filter
        filter_label = afwImage.FilterLabel(band=nickel_band)
        exposure.setFilter(filter_label)

        # Attach a simple Gaussian PSF so downstream warping/subtraction have a PSF
        fwhm_arcsec = 1.2  # typical PS1 stack seeing
        sigma_pix = 1.3
        try:
            exp_bbox = exposure.getBBox()
            center = geom.Point2D(exp_bbox.getCenterX(), exp_bbox.getCenterY())
            pix_scale = exposure.getWcs().getPixelScale(center).asArcseconds()
            if pix_scale > 0:
                sigma_pix = (fwhm_arcsec / pix_scale) / 2.3548
        except Exception as e:
            log.warning(
                f"Could not compute pixel scale for PSF; using default sigma {sigma_pix:.2f} ({e})"
            )

        psf = afwDetection.GaussianPsf(21, 21, sigma_pix)
        exposure.setPsf(psf)
        log.info(
            f'  Set synthetic PSF: FWHM~{fwhm_arcsec:.2f}" -> sigma={sigma_pix:.2f} pix'
        )

        # Add metadata
        exposure_info = exposure.getInfo()
        exposure_info.setMetadata(exposure.getMetadata())
        metadata = exposure.getMetadata()
        metadata.set("PS1_FILTER", ps1_filter)
        metadata.set("PS1_ZEROPOINT", ps1_zp)
        metadata.set("PS1_SOURCE", ps1_fits_path)

        log.info(f"Created LSST Exposure: {exposure.getBBox()}")
        log.info(f"  WCS: {lsst_wcs.getPixelOrigin()}")
        log.info(f"  PhotoCalib mean: {calibration_mean:.2e}")
        log.info(f"  Masked pixels: {np.sum(bad_mask)} / {bad_mask.size}")

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


def reproject_to_patch(exposure, patch_info):
    """
    Reproject exposure to match patch WCS and bounding box.

    This ensures the PS1 template has the exact geometry expected by the DIA pipeline.

    Parameters
    ----------
    exposure : lsst.afw.image.ExposureF
        Input exposure (PS1 template)
    patch_info : lsst.skymap.PatchInfo
        Target patch from skymap

    Returns
    -------
    lsst.afw.image.ExposureF
        Reprojected exposure matching patch geometry
    """
    from lsst.afw.math import WarpingControl, warpExposure

    log.info("Reprojecting PS1 template to match patch geometry...")

    # Get patch WCS and bounding box
    patch_wcs = patch_info.getWcs()
    patch_bbox = patch_info.getOuterBBox()

    log.info(f"  Patch bbox: {patch_bbox}")
    log.info(f"  Input exposure bbox: {exposure.getBBox()}")

    # Create output exposure with patch geometry
    reprojected = afwImage.ExposureF(patch_bbox)
    reprojected.setWcs(patch_wcs)
    reprojected.setFilter(exposure.getFilter())
    reprojected.setPhotoCalib(exposure.getPhotoCalib())
    # Preserve PSF if present (we add a synthetic PSF earlier)
    try:
        if exposure.getPsf() is not None:
            reprojected.setPsf(exposure.getPsf())
            log.info("  Carried PSF onto reprojected exposure")
    except Exception as e:
        log.warning(f"  Could not copy PSF to reprojected exposure: {e}")

    # Warp input exposure onto patch geometry
    warping_control = WarpingControl("lanczos4")
    # Set growth to allow proper interpolation at edges
    warping_control.setGrowFullMask(0)  # Don't grow mask during warping
    warping_control.setMaskWarpingKernelName("bilinear")  # Faster mask warping

    # Perform the warp
    warpExposure(reprojected, exposure, warping_control)

    log.info(f"  Reprojected exposure bbox: {reprojected.getBBox()}")

    # Check mask statistics
    mask = reprojected.mask.array
    valid_mask = mask == 0
    edge_bit = reprojected.mask.getPlaneBitMask("EDGE")
    no_data_bit = reprojected.mask.getPlaneBitMask("NO_DATA")

    log.info(f"  Valid pixels (mask==0): {np.sum(valid_mask)} / {mask.size}")
    log.info(f"  Pixels with EDGE set: {np.sum((mask & edge_bit) != 0)}")
    log.info(f"  Pixels with NO_DATA set: {np.sum((mask & no_data_bit) != 0)}")
    log.info(f"  Finite image pixels: {np.sum(np.isfinite(reprojected.image.array))}")

    # CRITICAL FIX: Clear EDGE and NO_DATA for pixels with actual warped data
    # After warping:
    #   - EDGE is set on interpolated pixels (we want to use these!)
    #   - NO_DATA is set on pixels outside the input footprint (correctly!)
    # Strategy: Any pixel with finite non-zero image data came from the warp and should be usable
    has_warped_data = np.isfinite(reprojected.image.array) & (
        reprojected.image.array != 0
    )

    # Clear both EDGE and NO_DATA for pixels that actually have warped data
    # These are legitimate pixels from the PS1 image, just interpolated during warping
    reprojected.mask.array[has_warped_data] &= ~edge_bit  # Clear EDGE
    reprojected.mask.array[has_warped_data] &= ~no_data_bit  # Clear NO_DATA

    valid_after = reprojected.mask.array == 0
    log.info(
        f"  Valid pixels after mask clearing: {np.sum(valid_after)} / {mask.size} ({100*np.sum(valid_after)/mask.size:.1f}%)"
    )

    # Also log what fraction of the patch has coverage
    log.info(
        f"  Patch coverage: {100*np.sum(has_warped_data)/mask.size:.1f}% of pixels have warped data"
    )

    return reprojected


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
        # Default to dimensions without instrument (matches DIA pipeline expectations)
        # PS1 templates are external, so they shouldn't have instrument dimension
        dims = ("skymap", "tract", "patch", "band")
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
        log.info(f"Registered collection: {collection}")
    except Exception as e:
        # If it already exists (or is a chain), this will fail harmlessly.
        log.debug(f"Collection registration note: {e}")
        pass

    # Get skymap to determine tract/patch (allow env overrides)
    skymap_name = os.environ.get("SKYMAP_NAME", "nickelRings-v1")
    skymap_collections = os.environ.get("SKYMAPS_CHAIN", "skymaps")
    skymap_collections = [
        c.strip() for c in skymap_collections.split(",") if c.strip()
    ] or ["skymaps"]

    log.info(f"Looking for skymap '{skymap_name}' in collections: {skymap_collections}")

    try:
        skymap = butler.get(
            "skyMap", skymap=skymap_name, collections=skymap_collections
        )
        log.info(f"Successfully loaded skymap: {skymap_name}")
    except Exception as e:
        log.error(f"Failed to get skymap '{skymap_name}': {e}")
        log.info("Available skymaps:")
        try:
            for ref in butler.registry.queryDatasets("skyMap"):
                log.info(f"  - {ref.dataId['skymap']}")
        except Exception:
            log.warning("Could not query available skymaps")
        raise RuntimeError(
            f"Skymap '{skymap_name}' not found. Set SKYMAP_NAME environment variable or create skymap."
        )

    # Find tract/patch from coordinates
    coord = geom.SpherePoint(ra, dec, geom.degrees)

    if tract is None:
        tract_info = skymap.findTract(coord)
        tract = tract_info.getId()
        log.info(f"Auto-determined tract: {tract}")
    else:
        tract_info = skymap[tract]
        log.info(f"Using specified tract: {tract}")

    patch_info = tract_info.findPatch(coord)
    patch = patch_info.getSequentialIndex()

    log.info(f"Target tract={tract}, patch={patch}")

    # Verify the exposure WCS covers the patch
    exp_bbox = exposure.getBBox()
    exp_wcs = exposure.getWcs()
    if exp_wcs is not None:
        center_pixel = geom.Point2D(exp_bbox.getCenterX(), exp_bbox.getCenterY())
        center_sky = exp_wcs.pixelToSky(center_pixel)
        log.info(
            f"Input exposure center: RA={center_sky.getRa().asDegrees():.4f}, "
            f"Dec={center_sky.getDec().asDegrees():.4f}"
        )
    else:
        log.warning("Exposure has no WCS!")

    # CRITICAL: Reproject PS1 exposure to match patch geometry
    # This ensures the template has the exact WCS and bounding box expected by DIA pipeline
    log.info("Reprojecting PS1 template to patch geometry...")
    exposure = reproject_to_patch(exposure, patch_info)

    # Build data ID matching dataset type dimensions
    data_id = {
        "skymap": skymap_name,
        "tract": tract,
        "patch": patch,
        "band": band,
    }

    # Only add instrument/physical_filter if they're in the dataset type dimensions
    if dims and "instrument" in dims:
        data_id["instrument"] = "Nickel"
        log.info("Including 'instrument' dimension in data ID")
    if dims and "physical_filter" in dims:
        data_id["physical_filter"] = band.upper()
        log.info("Including 'physical_filter' dimension in data ID")

    # Check if template already exists
    try:
        existing_refs = list(
            butler.registry.queryDatasets(
                "template_coadd", collections=[collection], dataId=data_id
            )
        )
        if existing_refs:
            log.warning(f"Template already exists for {data_id} in {collection}")
            log.warning("This will overwrite the existing template")
    except Exception as e:
        log.debug(f"Could not check for existing template: {e}")

    # Put exposure into Butler
    try:
        butler.put(exposure, "template_coadd", dataId=data_id, run=collection)
        log.info(f"Successfully ingested template_coadd with dataId: {data_id}")

        # Verify ingestion
        try:
            retrieved = butler.get(
                "template_coadd", dataId=data_id, collections=[collection]
            )
            log.info(f"Verified: template is retrievable (bbox: {retrieved.getBBox()})")
        except Exception as e:
            log.error(f"WARNING: Failed to verify ingestion: {e}")

    except Exception as e:
        log.error(f"Failed to ingest exposure: {e}")
        log.error(f"Data ID: {data_id}")
        log.error(f"Collection: {collection}")
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
        if lsst_fits_path.exists():
            try:
                lsst_fits_path.unlink()
            except Exception as e:
                log.warning(f"Could not remove existing LSST Exposure: {e}")
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

    # Record PS1 template metadata
    try:
        from obs_nickel_data_tools.pipeline_tools.template_metadata import (
            TemplateMetadata,
        )

        metadata_mgr = TemplateMetadata(args.repo)
        metadata_mgr.record_template(
            collection=args.collection,
            start_date="PS1",
            end_date="PS1",
            tract=str(data_id["tract"]) if "tract" in data_id else None,
            band=args.band,
            description=f"PS1 {args.ps1_band}-band template",
            source="ps1",
            ps1_filter=args.ps1_band,
            ps1_ra=args.ra,
            ps1_dec=args.dec,
            ps1_cutout_size=args.size,
        )
        log.info("Recorded PS1 template metadata")
    except Exception as e:
        log.warning(f"Failed to record metadata (non-fatal): {e}")

    log.info("=" * 60)
    log.info("SUCCESS: PS1 template ingested!")
    log.info(f"  Collection: {args.collection}")
    log.info(f"  Data ID: {data_id}")
    log.info(f"  FITS file: {lsst_fits_path}")
    log.info(f"  PS1 filter: {args.ps1_band} → Nickel {args.band}")
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
