"""Butler-facing LSST classes for this instrument. Do not edit: the identity
is the directory name, the logic lives in lsst.obs.stips (see
docs/forking-stips.md)."""

from lsst.obs.stips.binding import bind

Instrument, Translator, RawFormatter = bind(__name__)
