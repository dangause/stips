"""Build an afw Camera in-memory from a friendly CameraSpec (no yaml file).

Constructs the same cameraParams dict that lsst.obs.base.yamlCamera.makeCamera
builds from a file (mirroring a single-CCD camera/<name>.yaml), then runs
makeCamera's body on it. Used by StipsInstrument.getCamera when the profile's
`camera` is a CameraSpec (vs a raw yaml path).
"""

from __future__ import annotations

import lsst.afw.cameraGeom as cameraGeom
import lsst.geom as geom
from lsst.obs.base.yamlCamera import (
    makeAmplifierList,
    makeCameraFromCatalogs,
    makeDetectorConfigList,
    makeTransformDict,
)

__all__ = ["build_camera"]


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
