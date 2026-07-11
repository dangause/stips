"""Stack-free tests for the extracted, instrument-neutral defect tool.

Exercises the pure logic (detection thresholding, mask assembly, ECSV/CSV
emission, argument plumbing). The Butler/stack layer is not imported here; the
in-stack import is covered by a separate stack-gated one-off.
"""

import unittest
import warnings

import numpy as np

from stips.pipeline_tools import build_defects as bd


class TestDetectRectangles(unittest.TestCase):
    def test_flags_bright_and_dark_blobs_above_min_area(self):
        # Flat field of 1.0 with a bright 5x5 block and a dark 5x5 block.
        img = np.ones((64, 64), dtype=np.float32)
        img[10:15, 10:15] = 5.0  # bright defect (ratio > hi)
        img[40:45, 40:45] = 0.1  # dark defect (ratio < lo)
        rects = bd.detect_rectangles_from_flat(
            img, sigma_pix=3, ratio_hi=1.10, ratio_lo=0.90, min_area_px=8, open_kernel=2
        )
        self.assertGreaterEqual(len(rects), 2)
        # Every returned rect is a 4-int tuple within bounds.
        for x0, y0, w, h in rects:
            self.assertTrue(0 <= x0 < 64 and 0 <= y0 < 64)
            self.assertTrue(w > 0 and h > 0)

    def test_uniform_flat_yields_no_defects(self):
        img = np.ones((32, 32), dtype=np.float32)
        rects = bd.detect_rectangles_from_flat(img)
        self.assertEqual(rects, [])

    def test_min_area_drops_tiny_components(self):
        img = np.ones((64, 64), dtype=np.float32)
        img[20, 20] = 9.0  # single hot pixel -> area 1
        rects = bd.detect_rectangles_from_flat(
            img, sigma_pix=1, min_area_px=8, open_kernel=0
        )
        # A single pixel (area 1) is below min_area_px=8.
        self.assertTrue(all(w * h >= 8 for w, h in [(w, h) for _, _, w, h in rects]))


class TestClipAndDedupe(unittest.TestCase):
    def test_clip_box_to_bounds(self):
        # Box straddling the right/top edge is clipped.
        self.assertEqual(bd._clip_box_to_bounds(8, 8, 5, 5, 10, 10), (8, 8, 2, 2))
        # Fully out-of-bounds -> None.
        self.assertIsNone(bd._clip_box_to_bounds(20, 20, 5, 5, 10, 10))
        # Non-positive size -> None.
        self.assertIsNone(bd._clip_box_to_bounds(0, 0, 0, 5, 10, 10))

    def test_dedupe_preserves_order(self):
        rects = [(1, 1, 2, 2), (3, 3, 4, 4), (1, 1, 2, 2)]
        self.assertEqual(bd._dedupe_exact(rects), [(1, 1, 2, 2), (3, 3, 4, 4)])


class TestAssembleRectangles(unittest.TestCase):
    def test_manual_first_then_auto_deduped(self):
        auto = [(5, 5, 3, 3), (1, 1, 2, 2)]  # second dup of a manual box
        manual = [(1, 1, 2, 2, "manual")]
        final, valid_manual = bd.assemble_rectangles(auto, manual, nx=100, ny=100)
        self.assertEqual(valid_manual, [(1, 1, 2, 2)])
        # Manual comes first; the duplicate auto box is removed.
        self.assertEqual(final, [(1, 1, 2, 2), (5, 5, 3, 3)])

    def test_invert_manual_y(self):
        manual = [(10, 20, 4, 6, "manual")]
        final, valid_manual = bd.assemble_rectangles(
            [], manual, nx=100, ny=100, invert_manual_y=True
        )
        # y0_new = ny - (y0 + h) = 100 - (20 + 6) = 74
        self.assertEqual(valid_manual, [(10, 74, 4, 6)])
        self.assertEqual(final, [(10, 74, 4, 6)])

    def test_out_of_bounds_manual_dropped(self):
        manual = [(200, 200, 5, 5, "manual")]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            final, valid_manual = bd.assemble_rectangles([], manual, nx=100, ny=100)
        self.assertEqual(final, [])
        self.assertEqual(valid_manual, [])


class TestMaskedFraction(unittest.TestCase):
    def test_fraction(self):
        # A 2x2 box in a 10x10 image = 4/100.
        self.assertAlmostEqual(bd.masked_fraction((10, 10), [(0, 0, 2, 2)]), 0.04)


class TestEcsvContent(unittest.TestCase):
    def test_metadata_and_rows(self):
        content = bd.generate_ecsv_content(
            rects=[(1, 2, 3, 4), (5, 6, 7, 8)],
            instrument="Nickel",
            detector=0,
            detector_name="R00_S00",
            raft_name="R00",
            calib_date="1970-01-01T00:00:00",
        )
        self.assertTrue(content.startswith("# %ECSV 0.9"))
        self.assertIn("# - INSTRUME: Nickel", content)
        self.assertIn("# - DETECTOR: 0", content)
        self.assertIn("raftName=R00 detectorName=R00_S00", content)
        self.assertIn("# - CALIBDATE: '1970-01-01T00:00:00'", content)
        # Data rows appear after the header line.
        self.assertIn("1 2 3 4", content)
        self.assertIn("5 6 7 8", content)

    def test_instrument_is_parameterized(self):
        content = bd.generate_ecsv_content(rects=[], instrument="CTIO1m")
        self.assertIn("# - INSTRUME: CTIO1m", content)


class TestCsvRoundTrip(unittest.TestCase):
    def test_write_and_read_csv(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            csv_path = str(Path(d) / "rects.csv")
            manual = [(1, 1, 2, 2)]
            final = [(1, 1, 2, 2), (5, 5, 3, 3)]
            bd.write_rects_csv(csv_path, manual, final)
            back = bd.read_csv_defects(csv_path)
            self.assertEqual(back, final)

    def test_read_csv_requires_columns(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / "bad.csv"
            csv_path.write_text("a,b\n1,2\n")
            with self.assertRaises(ValueError):
                bd.read_csv_defects(str(csv_path))


class TestArgumentPlumbing(unittest.TestCase):
    def test_defaults_match_nickel_recipe(self):
        args = bd.build_parser().parse_args([])
        self.assertEqual(args.sigma, 7)
        self.assertEqual(args.ratio_hi, 1.10)
        self.assertEqual(args.ratio_lo, 0.90)
        self.assertEqual(args.min_area, 8)
        self.assertEqual(args.open_kernel, 2)
        self.assertEqual(args.detector_name, "R00_S00")
        self.assertEqual(args.raft_name, "R00")
        self.assertIsNone(args.instrument)

    def test_manual_box_repeatable(self):
        args = bd.build_parser().parse_args(
            ["--manual-box", "1", "2", "3", "4", "--manual-box", "5", "6", "7", "8"]
        )
        self.assertEqual(args.manual_box, [[1, 2, 3, 4], [5, 6, 7, 8]])


if __name__ == "__main__":
    unittest.main()
