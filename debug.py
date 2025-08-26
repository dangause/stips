# debug.py
import lsst.afw.display as afwDisplay
import lsst.display.ds9
afwDisplay.setDefaultBackend("ds9")

# Also enable Matplotlib for scatter/diagnostic plots (star selector)
import matplotlib
try:
    matplotlib.use("MacOSX", force=True)   # macOS
except Exception:
    matplotlib.use("TkAgg", force=True)
from matplotlib import pyplot as plt
plt.ion()

import lsstDebug
print("Importing lsstDebug settings...")

def _autocontinue(prompt):
    print(prompt, "(auto-continue)")
    return "c"
lsstDebug.input = _autocontinue


def DebugInfo(name):
    di = lsstDebug.getInfo(name)

    # # MeasurePsfTask-level toggles
    # if name in ("lsst.pipe.tasks.measurePsf",):
    #     di.display = True
    #     di.displayExposure = False
    #     di.displayResiduals = True
    #     di.normalizeResiduals = True
    #     di.showBadCandidates = True
    #     di.pause = False

    # # PSFEx determiner: KEEP diagnostics, DISABLE mosaics/cutouts
    # if name in ("lsst.meas.extensions.psfex.psfexPsfDeterminer",):
    #     di.display = False
    #     di.displayIterations = False
    #     di.displayResiduals = False
    #     di.normalizeResiduals = False
    #     di.displayPsfComponents = False
    #     di.displayPsfMosaic = False        # <- must be False
    #     di.displayPsfCandidates = False    # <- must be False
    #     di.keepMatplotlibPlots = False
    #     di.showBadCandidates = False
    #     di.pause = False

    # # Star selector: mag–size plot + overlays
    # if name in ("lsst.meas.algorithms.objectSizeStarSelector",):
    #     di.display = True
    #     di.displayExposure = True
    #     di.plotMagSize = True

    return di

lsstDebug.Info = DebugInfo
