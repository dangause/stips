"""Build a ``CrosstalkCalib`` from a declared coefficient matrix and put it in Butler.

Stack-side worker (runs inside the LSST environment via
``run_with_stack(["python", "-m", "stips.pipeline_tools.build_crosstalk_calib", ...])``).
Given an N×N coefficient matrix, it builds one ``lsst.ip.isr.CrosstalkCalib`` per
detector of the instrument's camera and ``butler.put``s each into a RUN collection.
Certification into the calib chain is done by the caller via ``butler
certify-calibrations`` (see ``stips.core.crosstalk``).

The matrix convention matches LSST: ``coeffs[i][j]`` is the fraction of amplifier
``j``'s signal appearing in amplifier ``i``; amp index ``i`` matches
``detector.getAmplifiers()[i]``; the diagonal is zero. Validation that
N == number of camera amps happens here, where the detector is available.

Output: a single JSON line to stdout, e.g.
``{"detectors": [0], "n_amp": 4, "run": "CTIO1m/calib/crosstalk/gen/<ts>"}``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

log = logging.getLogger("stips.build_crosstalk_calib")


def make_crosstalk_calib(detector, coeffs, units="adu"):
    """Build one ``CrosstalkCalib`` for ``detector`` from an N×N coefficient matrix.

    Validates that the matrix dimension equals the detector's amplifier count, sets
    the units, and stamps metadata. No Butler involved — this is the unit-testable
    core (the stack-gated test calls it against the real Y4KCam detector).
    """
    import numpy as np
    from lsst.ip.isr import CrosstalkCalib

    matrix = np.array(coeffs, dtype=float)
    n_amp = len(detector)
    if matrix.shape != (n_amp, n_amp):
        raise ValueError(
            f"crosstalk matrix is {matrix.shape[0]}x{matrix.shape[1]} but "
            f"detector {detector.getName()!r} (id={detector.getId()}) has "
            f"{n_amp} amplifiers; the matrix dimension must equal the amp count"
        )
    calib = CrosstalkCalib(nAmp=n_amp).fromDetector(
        detector, coeffVector=matrix.reshape(-1)
    )
    calib.crosstalkRatiosUnits = units
    calib.updateMetadata(setDate=True)
    return calib


def build_for_camera(butler, instrument, coeffs, units, run):
    """Build + put a CrosstalkCalib per detector. Returns the result dict.

    Imports of lsst.* happen in the caller's process (stack env). ``coeffs`` is a
    list-of-lists; ``butler`` is a writeable Butler.
    """
    import numpy as np
    from lsst.daf.butler import DatasetType
    from lsst.obs.base import Instrument

    instr = Instrument.fromName(instrument, butler.registry)
    camera = instr.getCamera()

    # Register the 'crosstalk' dataset type (idempotent) and the RUN collection.
    dataset_type = DatasetType(
        name="crosstalk",
        dimensions=["instrument", "detector"],
        storageClass="CrosstalkCalib",
        universe=butler.dimensions,
        isCalibration=True,
    )
    butler.registry.registerDatasetType(dataset_type)
    butler.registry.registerRun(run)

    detectors = []
    for detector in camera:
        calib = make_crosstalk_calib(detector, coeffs, units)
        butler.put(
            calib,
            "crosstalk",
            instrument=instrument,
            detector=detector.getId(),
            run=run,
        )
        detectors.append(detector.getId())

    return {"detectors": detectors, "n_amp": len(np.array(coeffs)), "run": run}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument("--instrument", required=True, help="Instrument name")
    parser.add_argument(
        "--run", required=True, help="RUN collection to put the calib into"
    )
    parser.add_argument(
        "--coeffs-json",
        required=True,
        help="N×N coefficient matrix as a JSON 2D array",
    )
    parser.add_argument(
        "--units", default="adu", help="Crosstalk ratio units (adu|electron)"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    import lsst.daf.butler as daf_butler

    coeffs = json.loads(args.coeffs_json)
    butler = daf_butler.Butler(args.repo, writeable=True)
    result = build_for_camera(butler, args.instrument, coeffs, args.units, args.run)
    log.info(
        "Built crosstalk calib for %d detector(s) into %s",
        len(result["detectors"]),
        args.run,
    )
    # Final JSON line for the caller to parse.
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
