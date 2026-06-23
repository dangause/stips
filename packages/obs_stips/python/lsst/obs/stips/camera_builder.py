"""Build an afw Camera in-memory from a friendly CameraSpec (no yaml file).

Constructs the same cameraParams dict that lsst.obs.base.yamlCamera.makeCamera
builds from a file (mirroring a single-CCD camera/<name>.yaml), then runs
makeCamera's body on it. Used by StipsInstrument.getCamera when the profile's
`camera` is a CameraSpec (vs a raw yaml path).
"""

from __future__ import annotations

import lsst.afw.cameraGeom as cameraGeom
import lsst.geom as geom
import yaml
from lsst.obs.base.yamlCamera import (
    makeAmplifierList,
    makeCameraFromCatalogs,
    makeDetectorConfigList,
    makeTransformDict,
)

__all__ = ["build_camera", "build_yaml_camera"]


# ---------------------------------------------------------------------------
# On-chip binning support (CCD_BINNING env knob).
#
# LSST cameraGeom has no input-binning parameter — the camera is defined in
# physical (unbinned) pixels and ISR reads the fixed amp bboxes, so a binned
# raw needs camera geometry that matches its pixel grid. Binning is NOT a
# uniform divide: the imaging pixels bin (÷N) but the serial/parallel overscan
# strips stay a fixed width (e.g. a 2x2-binned Y4KCam frame is 2072 = 4064/2
# imaging + 40 overscan, NOT 4104/2). So we transform every *raw* coordinate
# through a piecewise axis map (imaging segments ÷N, overscan segments fixed),
# while *trimmed* fields (detector bbox, refpos, dataExtent) divide by N and the
# physical pixelSize multiplies by N. This is exact for the single-CCD,
# 2-amps-per-axis, overscan-toward-centre layout that obs_stips synthesises.
# ---------------------------------------------------------------------------


def _axis_map(imaging: int, overscan: int, binning: int):
    """Piecewise map for a 2-amp axis with overscan toward the centre.

    Segments along a raw axis of width ``2*imaging + 2*overscan``:
    ``[0,img) imaging | [img,img+os) os | [img+os,img+2os) os | [.., 2img+2os) imaging``.
    Imaging pixels compress by ``binning``; overscan pixels are preserved.
    Returns ``T(c)`` mapping an unbinned raw coordinate to the binned frame.
    """
    if imaging % binning:
        raise ValueError(
            f"imaging extent {imaging} not divisible by CCD_BINNING={binning}"
        )
    seg_img1 = imaging
    seg_os1 = imaging + overscan
    seg_os2 = imaging + 2 * overscan

    def _clamp(v, hi):
        return max(0, min(v, hi))

    def T(c: int) -> int:
        c = int(round(c))
        img_px = _clamp(c, seg_img1)  # first imaging segment
        os_px = _clamp(c - seg_img1, overscan)  # left-amp overscan strip
        os_px += _clamp(c - seg_os1, overscan)  # right-amp overscan strip
        img_px += _clamp(c - seg_os2, imaging)  # second imaging segment
        return img_px // binning + os_px

    return T


def _map_raw_bbox(bbox, tx, ty):
    """Map a raw [[ox,oy],[w,h]] bbox through axis maps tx/ty."""
    (ox, oy), (w, h) = bbox
    nox, noy = tx(ox), ty(oy)
    return [[nox, noy], [tx(ox + w) - nox, ty(oy + h) - noy]]


def _binned_camera_params(params: dict, binning: int) -> dict:
    """Scale a parsed camera-params dict for ``binning`` (>=2)."""
    for ccd in params["CCDs"].values():
        amps = ccd["amplifiers"]
        ref = next(iter(amps.values()))
        img_w, img_h = ref["rawDataBBox"][1]
        os_w = ref["rawSerialOverscanBBox"][1][0]
        os_h = ref["rawParallelOverscanBBox"][1][1]
        tx = _axis_map(img_w, os_w, binning)
        ty = _axis_map(img_h, os_h, binning)
        for amp in amps.values():
            for key in (
                "rawBBox",
                "rawDataBBox",
                "rawSerialPrescanBBox",
                "rawSerialOverscanBBox",
                "rawParallelPrescanBBox",
                "rawParallelOverscanBBox",
            ):
                amp[key] = _map_raw_bbox(amp[key], tx, ty)
            ew, eh = amp["dataExtent"]
            amp["dataExtent"] = [ew // binning, eh // binning]
        # Trimmed detector fields divide by binning; physical pixel grows.
        (bx, by), (bw, bh) = ccd["bbox"]
        ccd["bbox"] = [[bx // binning, by // binning], [bw // binning, bh // binning]]
        ccd["refpos"] = [ccd["refpos"][0] / binning, ccd["refpos"][1] / binning]
        ccd["pixelSize"] = [
            ccd["pixelSize"][0] * binning,
            ccd["pixelSize"][1] * binning,
        ]
    return params


def build_yaml_camera(camera_file: str, binning: int = 1):
    """Build an afw Camera from a yaml file, optionally on-chip binned.

    ``binning == 1`` reproduces ``lsst.obs.base.yamlCamera.makeCamera``; for
    ``binning >= 2`` the geometry is transformed to match a binned raw (see the
    module note on binning).
    """
    with open(camera_file) as fd:
        cameraParams = yaml.safe_load(fd)
    if binning and binning > 1:
        cameraParams = _binned_camera_params(cameraParams, binning)

    plateScale = geom.Angle(cameraParams["plateScale"], geom.arcseconds)
    nativeSys = cameraGeom.CameraSys(cameraParams["transforms"].pop("nativeSys"))
    transforms = makeTransformDict(nativeSys, cameraParams["transforms"], plateScale)
    ccdParams = cameraParams["CCDs"]
    detectorConfigList = makeDetectorConfigList(ccdParams)
    focalPlaneParity = cameraParams.get("focalPlaneParity", False)
    amplifierDict = {
        ccdName: makeAmplifierList(ccdValues)
        for ccdName, ccdValues in ccdParams.items()
    }
    return makeCameraFromCatalogs(
        cameraParams["name"],
        detectorConfigList,
        nativeSys,
        transforms,
        amplifierDict,
        focalPlaneParity=focalPlaneParity,
    )


def _camera_params(spec, instrument_name):
    pixel_mm = spec.pixel_size_um / 1000.0
    plate_scale_arcsec_per_mm = spec.plate_scale_arcsec_per_pixel / pixel_mm
    amp = {
        "perAmpData": True,
        "dataExtent": [spec.nx, spec.ny],
        "readCorner": "LL",
        "rawBBox": [[0, 0], [spec.nx, spec.ny]],
        "rawDataBBox": [[0, 0], [spec.nx, spec.ny]],
        "rawSerialPrescanBBox": [[0, 0], [0, 0]],
        "rawSerialOverscanBBox": [[0, 0], [0, 0]],
        "rawParallelPrescanBBox": [[0, 0], [0, 0]],
        "rawParallelOverscanBBox": [[0, 0], [0, 0]],
        "gain": spec.gain,
        "readNoise": spec.read_noise,
        "saturation": spec.saturation,
        "linearityType": "PROPORTIONAL",
        "linearityThreshold": 0,
        "linearityMax": spec.saturation,
        "linearityCoeffs": [0.0, 1.0],
        "hdu": 0,
        "ixy": [0, 0],
        "flipXY": [spec.flip_x, spec.flip_y],
    }
    ccd = {
        "detectorType": 0,
        "physicalType": "SCIENCE",
        "refpos": [spec.nx / 2.0, spec.ny / 2.0],
        "offset": [0.0, 0.0, 0.0],
        "bbox": [[0, 0], [spec.nx, spec.ny]],
        "pixelSize": [pixel_mm, pixel_mm],
        "transformDict": {"nativeSys": "Pixels", "transforms": {}},
        "transposeDetector": False,
        "pitch": 0.0,
        "yaw": 0.0,
        "roll": 0.0,
        "id": 0,
        "name": spec.name or "CCD0",
        "serial": spec.serial or f"{instrument_name}-1",
        "amplifiers": {"A00": amp},
    }
    return {
        "name": instrument_name,
        "plateScale": plate_scale_arcsec_per_mm,
        "transforms": {
            "nativeSys": "FocalPlane",
            "FieldAngle": {"transformType": "radial", "coeffs": [0.0, 1.0, 0.0]},
        },
        "CCDs": {"CCD0": ccd},
    }


def build_camera(spec, instrument_name: str):
    """Return an lsst.afw.cameraGeom.Camera built from `spec`.

    Mirrors the body of lsst.obs.base.yamlCamera.makeCamera, sourcing
    ``cameraParams`` from a freshly built dict (``.pop`` below mutates, so a
    fresh dict is built per call).
    """
    cameraParams = _camera_params(spec, instrument_name)

    cameraName = cameraParams["name"]

    plateScale = geom.Angle(cameraParams["plateScale"], geom.arcseconds)
    nativeSys = cameraGeom.CameraSys(cameraParams["transforms"].pop("nativeSys"))
    transforms = makeTransformDict(nativeSys, cameraParams["transforms"], plateScale)

    ccdParams = cameraParams["CCDs"]
    detectorConfigList = makeDetectorConfigList(ccdParams)
    focalPlaneParity = cameraParams.get("focalPlaneParity", False)

    amplifierDict = {}
    for ccdName, ccdValues in ccdParams.items():
        amplifierDict[ccdName] = makeAmplifierList(ccdValues)

    return makeCameraFromCatalogs(
        cameraName,
        detectorConfigList,
        nativeSys,
        transforms,
        amplifierDict,
        focalPlaneParity=focalPlaneParity,
    )
