"""Stack-free tests for ISR crosstalk wiring (doCrosstalk injection)."""

import unittest

from stips import CrosstalkSpec, InstrumentProfile, Site
from stips.core.pipeline import isr_config_args


def _profile(*, crosstalk=None, isr_overrides=None):
    return InstrumentProfile(
        name="Demo",
        site=Site(0.0, 0.0, 0.0),
        filters={"clear": None},
        header_map={},
        camera="camera/demo.yaml",
        isr_overrides=isr_overrides or {},
        crosstalk=crosstalk,
    )


_CT = CrosstalkSpec(coeffs=[[0.0, 1e-4], [1e-4, 0.0]])


class TestIsrCrosstalkWiring(unittest.TestCase):
    def test_no_crosstalk_no_docrosstalk_arg(self):
        args = isr_config_args(_profile())
        self.assertNotIn("isr:doCrosstalk=True", args)
        self.assertNotIn("isr:doCrosstalk=False", args)

    def test_crosstalk_enables_docrosstalk(self):
        args = isr_config_args(_profile(crosstalk=_CT))
        self.assertIn("--config", args)
        self.assertIn("isr:doCrosstalk=True", args)

    def test_label_is_applied_to_docrosstalk(self):
        args = isr_config_args(_profile(crosstalk=_CT), "cpBiasIsr")
        self.assertIn("cpBiasIsr:doCrosstalk=True", args)

    def test_explicit_override_wins_and_is_not_duplicated(self):
        # An instrument that explicitly disables crosstalk keeps doCrosstalk=False
        # and does NOT also get the auto-injected True.
        args = isr_config_args(
            _profile(crosstalk=_CT, isr_overrides={"doCrosstalk": False})
        )
        self.assertIn("isr:doCrosstalk=False", args)
        self.assertNotIn("isr:doCrosstalk=True", args)
        self.assertEqual(
            sum("doCrosstalk" in a for a in args), 1, f"duplicated in {args}"
        )

    def test_include_crosstalk_false_suppresses_injection(self):
        # Crosstalk MEASUREMENT ISR must not auto-enable doCrosstalk (it is
        # measuring crosstalk, not applying it).
        args = isr_config_args(
            _profile(crosstalk=_CT), "cpCrosstalkIsr", include_crosstalk=False
        )
        self.assertNotIn("cpCrosstalkIsr:doCrosstalk=True", args)

    def test_include_crosstalk_false_keeps_other_overrides(self):
        args = isr_config_args(
            _profile(crosstalk=_CT, isr_overrides={"doDefect": False}),
            "cpCrosstalkIsr",
            include_crosstalk=False,
        )
        self.assertIn("cpCrosstalkIsr:doDefect=False", args)
        self.assertNotIn("cpCrosstalkIsr:doCrosstalk=True", args)

    def test_other_overrides_still_present(self):
        args = isr_config_args(
            _profile(crosstalk=_CT, isr_overrides={"doDefect": False})
        )
        self.assertIn("isr:doDefect=False", args)
        self.assertIn("isr:doCrosstalk=True", args)


if __name__ == "__main__":
    unittest.main()
