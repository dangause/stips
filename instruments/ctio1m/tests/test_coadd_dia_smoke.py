"""Under-stack smoke test: CTIO coadd template builds and DIA produces a diff.

Skipped unless the LSST stack is importable AND a prepared E2 coadd repo exists
(env CTIO_SMOKE_REPO). This is a path/regression guard, not a science check. The
dataset-type names / collection globs are confirmed against core/coadd.py,
core/dia.py and DRP.yaml; if a future stack version renames them, adjust here.
"""

import os
import unittest

try:
    import lsst.daf.butler  # noqa: F401

    HAVE_STACK = True
except ImportError:
    HAVE_STACK = False

SMOKE_REPO = os.environ.get("CTIO_SMOKE_REPO")


@unittest.skipUnless(HAVE_STACK and SMOKE_REPO, "needs LSST stack + CTIO_SMOKE_REPO")
class TestCtioCoaddDiaSmoke(unittest.TestCase):
    def test_template_and_diff_exist(self):
        from lsst.daf.butler import Butler

        from stips.core.dataset_types import DIFFERENCE_IMAGE, TEMPLATE_COADD

        butler = Butler(SMOKE_REPO)
        templates = list(
            butler.registry.queryDatasets(
                TEMPLATE_COADD, collections="templates/deep/*", findFirst=True
            )
        )
        self.assertGreater(len(templates), 0, "no coadd template assembled")
        diffs = list(
            butler.registry.queryDatasets(
                DIFFERENCE_IMAGE,
                collections="CTIO1m/runs/*/diff/*",
                findFirst=True,
            )
        )
        self.assertGreater(len(diffs), 0, "no difference image produced")
