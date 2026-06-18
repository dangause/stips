import unittest

from stips import Field, InstrumentProfile, Site, hook


def make_profile(**over):
    base = dict(
        name="Test",
        site=Site(0.0, 0.0, 0.0),
        filters={"B": "B", "OPEN": "clear"},
        header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
        camera="camera/test.yaml",
    )
    base.update(over)
    return InstrumentProfile(**base)


class TestProfileDefaults(unittest.TestCase):
    def test_policy_and_prefix_default_to_name(self):
        p = make_profile()
        self.assertEqual(p.policy_name, "Test")
        self.assertEqual(p.collection_prefix, "Test")

    def test_explicit_prefix_overrides(self):
        self.assertEqual(make_profile(collection_prefix="X").collection_prefix, "X")

    def test_night_offset_default_is_one(self):
        self.assertEqual(make_profile().night_to_dayobs_offset_days, 1)

    def test_const_map_defaults_empty(self):
        self.assertEqual(make_profile().const_map, {})


class TestHookRegistration(unittest.TestCase):
    def test_hook_registers_by_function_name(self):
        p = make_profile()

        @hook(p)
        def observation_type(header):
            return "science"

        self.assertIn("observation_type", p.hooks)
        self.assertEqual(p.hooks["observation_type"]({}), "science")


if __name__ == "__main__":
    unittest.main()
