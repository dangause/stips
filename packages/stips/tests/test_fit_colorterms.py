"""Stack-free tests for the extracted, instrument-neutral colorterm fitter.

Exercises the pure logic (least-squares fit math, spline->polynomial
conversion, config-file emission, argument plumbing). The money test fabricates
photometry with known color terms and proves the fitter -> emitted config
round-trips those coefficients. The Butler/PS1-query layer is not imported here.
"""

import unittest

import numpy as np
from stips.pipeline_tools import fit_colorterms as fc


def _fake_config_namespace():
    """A namespace exposing Colorterm/ColortermDict + a config with .data.

    Lets us ``exec`` an emitted colorterms.py (which ends with
    ``config.data = {...}``) without the LSST stack, and read the coefficients
    back out.
    """

    class Colorterm:
        def __init__(self, primary, secondary, c0, c1, c2):
            self.primary = primary
            self.secondary = secondary
            self.c0 = c0
            self.c1 = c1
            self.c2 = c2

    class ColortermDict:
        def __init__(self, data):
            self.data = data

    class _Config:
        pass

    return Colorterm, ColortermDict, _Config()


def _exec_config(text):
    """Exec an emitted colorterms.py, returning its ``config.data`` mapping."""
    Colorterm, ColortermDict, config = _fake_config_namespace()
    ns = {"Colorterm": Colorterm, "ColortermDict": ColortermDict, "config": config}
    # Drop the stack import line; provide the symbols ourselves.
    body = "\n".join(
        ln
        for ln in text.splitlines()
        if not ln.startswith("from lsst.pipe.tasks.colorterms")
    )
    exec(body, ns)  # noqa: S102 - trusted, self-generated text
    return config.data


class TestLinearFit(unittest.TestCase):
    def test_recovers_known_linear_coeffs(self):
        rng = np.random.default_rng(1)
        g = rng.uniform(14, 18, 300)
        r = g - rng.uniform(0.2, 1.8, 300)
        # target = primary + c0 + c1*(primary-secondary), exactly.
        c0_true, c1_true = 0.215, 0.589
        target = g + c0_true + c1_true * (g - r)
        c0, c1, c2 = fc.fit_linear_colorterm(g, r, target, degree=1)
        self.assertAlmostEqual(c0, c0_true, places=6)
        self.assertAlmostEqual(c1, c1_true, places=6)
        self.assertEqual(c2, 0.0)

    def test_recovers_known_quadratic_coeffs(self):
        rng = np.random.default_rng(2)
        r = rng.uniform(14, 18, 400)
        i = r - rng.uniform(0.1, 1.4, 400)
        c0_true, c1_true, c2_true = -0.18, -0.243, 0.05
        color = r - i
        target = r + c0_true + c1_true * color + c2_true * color**2
        c0, c1, c2 = fc.fit_linear_colorterm(r, i, target, degree=2)
        self.assertAlmostEqual(c0, c0_true, places=5)
        self.assertAlmostEqual(c1, c1_true, places=5)
        self.assertAlmostEqual(c2, c2_true, places=5)

    def test_rms_zero_for_perfect_fit(self):
        g = np.linspace(14, 18, 50)
        r = g - 0.7
        target = g + 0.1 + 0.5 * (g - r)
        c0, c1, c2 = fc.fit_linear_colorterm(g, r, target, degree=1)
        self.assertAlmostEqual(
            fc.colorterm_rms(g, r, target, c0, c1, c2), 0.0, places=8
        )

    def test_too_few_points_raises(self):
        with self.assertRaises(ValueError):
            fc.fit_linear_colorterm([1.0], [0.5], [1.2], degree=1)


class TestConfigEmission(unittest.TestCase):
    def test_render_format_and_key(self):
        e = fc.ColortermEntry("I", "iMeanPSFMag", "rMeanPSFMag", -0.379, 0.352, 0.0)
        text = fc.render_colorterms_config([e], "ps1*", "Nickel", "hdr line")
        self.assertIn("from lsst.pipe.tasks.colorterms import Colorterm", text)
        self.assertIn('"ps1*": ColortermDict(', text)
        self.assertIn('"I": Colorterm(', text)
        self.assertIn("c1=0.352000,", text)
        self.assertIn("# ruff: noqa: F821", text)
        self.assertIn("# hdr line", text)

    def test_render_execs_back_to_coefficients(self):
        entries = [
            fc.ColortermEntry("B", "gMeanPSFMag", "rMeanPSFMag", 0.215, 0.589, 0.0),
            fc.ColortermEntry("R", "rMeanPSFMag", "iMeanPSFMag", -0.18, -0.243, 0.0),
        ]
        text = fc.render_colorterms_config(entries, "ps1*", "Nickel")
        data = _exec_config(text)
        ct = data["ps1*"].data
        self.assertAlmostEqual(ct["B"].c0, 0.215)
        self.assertAlmostEqual(ct["B"].c1, 0.589)
        self.assertEqual(ct["B"].primary, "gMeanPSFMag")
        self.assertAlmostEqual(ct["R"].c1, -0.243)


class TestMoneyRoundTrip(unittest.TestCase):
    """Fabricate photometry with known color terms -> fit -> emitted config
    contains those coefficients (the end-to-end proof)."""

    def test_matched_table_to_config(self):
        rng = np.random.default_rng(7)
        g = rng.uniform(14, 18, 250)
        r = g - rng.uniform(0.2, 1.8, 250)
        i = r - rng.uniform(0.1, 1.2, 250)
        known = {
            "B": (0.215, 0.589, ("gMeanPSFMag", "rMeanPSFMag")),
            "V": (-0.011, -0.540, ("gMeanPSFMag", "rMeanPSFMag")),
            "R": (-0.180, -0.243, ("rMeanPSFMag", "iMeanPSFMag")),
            "I": (-0.379, 0.352, ("iMeanPSFMag", "rMeanPSFMag")),
        }
        table = {"gMeanPSFMag": g, "rMeanPSFMag": r, "iMeanPSFMag": i}
        for band, (c0, c1, (pcol, scol)) in known.items():
            prim = table[pcol]
            sec = table[scol]
            table[band] = prim + c0 + c1 * (prim - sec)

        entries = fc.fit_from_matched(
            table, ["B", "V", "R", "I"], fc.DEFAULT_PS1_COLORS, degree=1
        )
        text = fc.render_colorterms_config(entries, "ps1*", "Nickel")
        data = _exec_config(text)["ps1*"].data
        for band, (c0, c1, _) in known.items():
            self.assertAlmostEqual(data[band].c0, c0, places=5, msg=f"{band} c0")
            self.assertAlmostEqual(data[band].c1, c1, places=5, msg=f"{band} c1")


class TestSplineToPolynomial(unittest.TestCase):
    def test_flat_spline_gives_flat_polynomial(self):
        # A constant multiplicative correction => constant additive magnitude,
        # zero color slope.
        nodes = [-0.5, 0.0, 0.5, 1.0]
        values = [1.0, 1.0, 1.0, 1.0]
        c0, c1, c2 = fc.polynomial_from_spline(nodes, values, degree=2)
        self.assertAlmostEqual(c0, 0.0, places=6)
        self.assertAlmostEqual(c1, 0.0, places=6)
        self.assertAlmostEqual(c2, 0.0, places=6)


class TestColorOverrides(unittest.TestCase):
    def test_parse_color_overrides(self):
        m = fc._parse_color_overrides(["B:gMag:rMag", "R:rMag:iMag"])
        self.assertEqual(m["B"], ("gMag", "rMag"))
        self.assertEqual(m["R"], ("rMag", "iMag"))

    def test_bad_color_override_raises(self):
        with self.assertRaises(ValueError):
            fc._parse_color_overrides(["B:onlyone"])


class TestArgumentPlumbing(unittest.TestCase):
    def test_defaults(self):
        args = fc.build_parser().parse_args(["--matched", "x.csv"])
        self.assertEqual(args.ref_catalog, "ps1")
        self.assertEqual(args.bands, ["B", "V", "R", "I"])
        self.assertEqual(args.degree, 1)
        self.assertIsNone(args.instrument)

    def test_input_sources_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            fc.build_parser().parse_args(
                ["--matched", "a.csv", "--from-spline-dir", "d"]
            )

    def test_ref_catalog_keys(self):
        self.assertEqual(fc.REF_CATALOG_KEYS["ps1"], "ps1*")
        self.assertEqual(fc.REF_CATALOG_KEYS["gaia"], "gaia*")
        self.assertEqual(fc.REF_CATALOG_KEYS["monster"], "*monster*")


if __name__ == "__main__":
    unittest.main()
