"""Stack-free unit tests for the declarative crosstalk schema."""

import unittest

from stips import CrosstalkSpec, InstrumentProfile, Site


class TestCrosstalkSpec(unittest.TestCase):
    def test_valid_matrix_is_accepted_and_exposed(self):
        coeffs = [
            [0.0, 1e-4, 2e-4, 3e-4],
            [3e-4, 0.0, 2e-4, 1e-4],
            [4e-4, 5e-4, 0.0, 6e-4],
            [7e-4, 8e-4, 9e-4, 0.0],
        ]
        spec = CrosstalkSpec(coeffs=coeffs)
        self.assertEqual(spec.coeffs, coeffs)
        self.assertEqual(spec.units, "adu")  # default
        self.assertEqual(spec.n_amp, 4)

    def test_units_override(self):
        spec = CrosstalkSpec(coeffs=[[0.0, 1e-4], [1e-4, 0.0]], units="electron")
        self.assertEqual(spec.units, "electron")

    def test_zero_matrix_is_valid_placeholder(self):
        # A zero matrix is the documented no-op placeholder.
        spec = CrosstalkSpec(coeffs=[[0.0, 0.0], [0.0, 0.0]])
        self.assertEqual(spec.n_amp, 2)

    def test_non_square_is_rejected(self):
        with self.assertRaises(ValueError):
            CrosstalkSpec(coeffs=[[0.0, 1e-4, 2e-4], [1e-4, 0.0, 3e-4]])

    def test_nonzero_diagonal_is_rejected(self):
        with self.assertRaises(ValueError):
            CrosstalkSpec(coeffs=[[1e-3, 1e-4], [1e-4, 0.0]])

    def test_single_amp_is_rejected(self):
        # Crosstalk needs at least two amplifiers to be meaningful.
        with self.assertRaises(ValueError):
            CrosstalkSpec(coeffs=[[0.0]])

    def test_empty_is_rejected(self):
        with self.assertRaises(ValueError):
            CrosstalkSpec(coeffs=[])

    def test_profile_crosstalk_defaults_none(self):
        p = InstrumentProfile(
            name="Demo",
            site=Site(0.0, 0.0, 0.0),
            filters={"clear": None},
            header_map={},
            camera="camera/demo.yaml",
        )
        self.assertIsNone(p.crosstalk)

    def test_profile_accepts_crosstalk(self):
        spec = CrosstalkSpec(coeffs=[[0.0, 1e-4], [1e-4, 0.0]])
        p = InstrumentProfile(
            name="Demo",
            site=Site(0.0, 0.0, 0.0),
            filters={"clear": None},
            header_map={},
            camera="camera/demo.yaml",
            crosstalk=spec,
        )
        self.assertIs(p.crosstalk, spec)


if __name__ == "__main__":
    unittest.main()
