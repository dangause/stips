import inspect
import unittest

from lsst.obs.nickel.calibCombine import (
    NickelCalibCombineByFilterTask,
    NickelCalibCombineTask,
)
from lsst.obs.stips.calibCombine import (
    StipsCalibCombineByFilterTask,
    StipsCalibCombineTask,
)


class TestCalibCombineParity(unittest.TestCase):
    def test_combineheaders_source_is_verbatim(self):
        # inspect.getsource of a METHOD returns only the method body (not the
        # class line), so the class rename doesn't affect equality.
        self.assertEqual(
            inspect.getsource(StipsCalibCombineTask.combineHeaders),
            inspect.getsource(NickelCalibCombineTask.combineHeaders),
        )

    def test_byfilter_combineheaders_source_is_verbatim(self):
        # ByFilter may or may not define its own combineHeaders; compare only if it does.
        s_has = "combineHeaders" in vars(StipsCalibCombineByFilterTask)
        n_has = "combineHeaders" in vars(NickelCalibCombineByFilterTask)
        self.assertEqual(s_has, n_has)
        if s_has and n_has:
            self.assertEqual(
                inspect.getsource(StipsCalibCombineByFilterTask.combineHeaders),
                inspect.getsource(NickelCalibCombineByFilterTask.combineHeaders),
            )


if __name__ == "__main__":
    unittest.main()
