"""Small-telescope CalibCombineTask that handles missing VisitInfo dates.

Small-telescope ISR pipelines do not always preserve VisitInfo dates in
their FITS output (the afw ExposureF writer does not serialize VisitInfo
for calibration ISR exposures). This causes the standard CalibCombineTask
to crash in combineHeaders() when it tries to format the date.

This subclass overrides combineHeaders() to gracefully handle invalid
dates by falling back to the merged FITS header DATE-BEG/DATE-END
values from the raw metadata.

PINNED VERBATIM COPY: combineHeaders() below is a pinned, verbatim fork of
cp_pipe's ``CalibCombineTask.combineHeaders`` (tracking the installed
``lsst_distrib`` as of 2026-06), with the date-fallback logic added. It must
be re-verified against cp_pipe on every stack upgrade — if the upstream
combineHeaders changes, this fork may drift out of sync.
"""

__all__ = ["StipsCalibCombineTask", "StipsCalibCombineByFilterTask"]

import astropy.time
import lsst.daf.base
from lsst.cp.pipe.cpCombine import CalibCombineByFilterTask, CalibCombineTask


class StipsCalibCombineTask(CalibCombineTask):
    """CalibCombineTask with robust date handling for small-telescope data."""

    def combineHeaders(
        self, expHandleList, calib=None, calibType="CALIB", scales=None, metadata=None
    ):
        """Combine input headers, handling invalid VisitInfo dates.

        Falls back to raw FITS header DATE-BEG/DATE-END when the
        VisitInfo date is invalid (common for Nickel ISR outputs).
        """
        from datetime import UTC, datetime

        import lsst.afw.image as afwImage
        from astro_metadata_translator import merge_headers
        from astro_metadata_translator.serialize import dates_to_fits
        from lsst.obs.base.utils import strip_provenance_from_fits_header

        # Header
        if calib is not None:
            header = calib.getMetadata()
        elif metadata is not None:
            header = metadata
        else:
            raise RuntimeError(
                "No calibration and no metadata passed to combineHeaders"
            )

        header.set("OBSTYPE", calibType)

        # Creation date
        now = datetime.now(tz=UTC)
        header.set(
            "CALIB_CREATION_DATETIME",
            now.strftime("%Y-%m-%dT%T"),
            comment="UTC of processing",
        )
        local_time = now.astimezone()
        header.set(
            "CALIB_CREATION_DATE",
            local_time.strftime("%Y-%m-%d"),
            comment="Local time day of creation",
        )
        header.set(
            "CALIB_CREATION_TIME",
            local_time.strftime("%X %Z"),
            comment="Local time in day of creation",
        )

        # Merge input headers (contains raw FITS keywords like DATE-BEG)
        inputHeaders = [
            expHandle.get(component="metadata") for expHandle in expHandleList
        ]
        merged = merge_headers(inputHeaders, mode="drop")
        strip_provenance_from_fits_header(merged)

        for k, v in merged.items():
            if k not in header:
                header.set(k, v, comment=merged.getComment(k))

        # Load VisitInfo and handle invalid dates gracefully
        visitInfoList = [
            expHandle.get(component="visitInfo") for expHandle in expHandleList
        ]

        for i, visit in enumerate(visitInfoList):
            if visit is None:
                continue
            header.set(f"CPP_INPUT_{i}", visit.id, comment="Input exposure ID")
            try:
                date_str = str(visit.getDate().toAstropy().to_value("fits"))
                header.set(
                    f"CPP_INPUT_DATE_{i}", date_str, comment=f"TAI date of input {i}"
                )
            except Exception:
                header.set(
                    f"CPP_INPUT_DATE_{i}",
                    "UNKNOWN",
                    comment=f"TAI date of input {i} (unavailable)",
                )
            header.set(
                f"CPP_INPUT_EXPT_{i}",
                visit.getExposureTime(),
                comment="Input exposure time",
            )
            if scales is not None:
                header.set(
                    f"CPP_INPUT_SCALE_{i}",
                    scales[i],
                    comment="Scaling applied to input",
                )

        # Determine date range from VisitInfo if possible, else from headers
        earliest = None
        newest = None

        # Try VisitInfo dates first
        valid_dates = []
        for vi in visitInfoList:
            if vi is None:
                continue
            try:
                at = vi.getDate().toAstropy()
                offset = vi.getExposureTime() / 2.0
                valid_dates.append((at, offset))
            except Exception:
                continue

        if valid_dates:
            valid_dates.sort(key=lambda x: x[0])
            earliest = valid_dates[0][0] - astropy.time.TimeDelta(
                valid_dates[0][1], format="sec"
            )
            newest = valid_dates[-1][0] + astropy.time.TimeDelta(
                valid_dates[-1][1], format="sec"
            )
        else:
            # Fall back to merged header DATE-BEG / DATE-END
            date_beg = None
            date_end = None
            for key in ("DATE-BEG", "DATE-OBS", "DATE"):
                if merged.exists(key):
                    try:
                        date_beg = astropy.time.Time(merged.get(key), scale="utc")
                        break
                    except Exception:
                        continue
            for key in ("DATE-END", "DATE"):
                if merged.exists(key):
                    try:
                        date_end = astropy.time.Time(merged.get(key), scale="utc")
                        break
                    except Exception:
                        continue

            if date_beg is not None:
                earliest = date_beg
                newest = date_end if date_end is not None else date_beg
                self.log.warning(
                    "VisitInfo dates unavailable for %s; using header DATE-BEG/DATE-END: %s to %s",
                    calibType,
                    earliest.iso,
                    newest.iso,
                )
            else:
                self.log.warning(
                    "No date information available for %s calibration; "
                    "using current time as placeholder.",
                    calibType,
                )
                earliest = astropy.time.Time(now)
                newest = earliest

        # Standard DATE header cards
        comments = {
            "TIMESYS": "Time scale for all dates",
            "DATE-OBS": "Start date of earliest input observation",
            "MJD-OBS": "[d] Start MJD of earliest input observation",
            "DATE-BEG": "Start date of earliest input observation",
            "MJD-BEG": "[d] Start MJD of earliest input observation",
            "DATE-END": "End date of oldest input observation",
            "MJD-END": "[d] End MJD of oldest input observation",
            "MJD-AVG": "[d] MJD midpoint of all input observations",
            "DATE-AVG": "Midpoint date of all input observations",
        }
        dateCards = dates_to_fits(earliest, newest)
        for k, v in dateCards.items():
            header.set(k, v, comment=comments.get(k, None))

        # Populate VisitInfo on the output calibration
        if calib:
            expTime = 1.0
            if self.config.connections.outputData.lower() == "bias":
                expTime = 0.0

            date_avg = earliest + (newest - earliest) / 2.0
            try:
                dt = lsst.daf.base.DateTime(date_avg.isot, lsst.daf.base.DateTime.TAI)
            except Exception:
                dt = lsst.daf.base.DateTime()

            instrumentLabel = ""
            for vi in visitInfoList:
                if vi is not None and vi.instrumentLabel:
                    instrumentLabel = vi.instrumentLabel
                    break

            visitInfo = afwImage.VisitInfo(
                exposureTime=expTime,
                darkTime=expTime,
                date=dt,
                instrumentLabel=instrumentLabel,
            )
            calib.getInfo().setVisitInfo(visitInfo)

        return header


class StipsCalibCombineByFilterTask(CalibCombineByFilterTask):
    """CalibCombineByFilterTask with robust date handling for small-telescope data.

    Inherits the same combineHeaders fix from StipsCalibCombineTask
    via method resolution. CalibCombineByFilterTask inherits from
    CalibCombineTask, so we just need to override combineHeaders.
    """

    combineHeaders = StipsCalibCombineTask.combineHeaders
