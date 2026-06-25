"""Stack-free tests for crosstalk command/argument construction."""

import json
import unittest

from stips.core import crosstalk as ct


class TestBuildWorkerArgs(unittest.TestCase):
    def test_invokes_worker_module_with_coeffs_json(self):
        coeffs = [[0.0, 1e-4], [1e-4, 0.0]]
        args = ct.build_worker_args(
            repo="/repo",
            instrument="CTIO1m",
            run="CTIO1m/calib/crosstalk/gen/ts1",
            coeffs=coeffs,
            units="adu",
        )
        self.assertEqual(args[:3], ["python", "-m", ct.WORKER_MODULE])
        self.assertIn("--repo", args)
        self.assertEqual(args[args.index("--repo") + 1], "/repo")
        self.assertEqual(args[args.index("--instrument") + 1], "CTIO1m")
        self.assertEqual(
            args[args.index("--run") + 1], "CTIO1m/calib/crosstalk/gen/ts1"
        )
        # Coeffs round-trip as JSON.
        self.assertEqual(json.loads(args[args.index("--coeffs-json") + 1]), coeffs)
        self.assertEqual(args[args.index("--units") + 1], "adu")


class TestCertifyArgs(unittest.TestCase):
    def test_certifies_crosstalk_with_wide_window(self):
        args = ct.certify_args("/repo", "gen/ts1", "CTIO1m/calib/crosstalk")
        self.assertEqual(args[0], "certify-calibrations")
        self.assertEqual(args[1], "/repo")
        self.assertEqual(args[2], "gen/ts1")
        self.assertEqual(args[3], "CTIO1m/calib/crosstalk")
        self.assertEqual(args[4], "crosstalk")
        self.assertEqual(args[args.index("--begin-date") + 1], ct.WIDE_BEGIN)
        self.assertEqual(args[args.index("--end-date") + 1], ct.WIDE_END)


class TestChainArgs(unittest.TestCase):
    def test_prepends_calib_into_chain(self):
        args = ct.chain_prepend_args(
            "/repo", "CTIO1m/calib/curated", "CTIO1m/calib/crosstalk"
        )
        self.assertEqual(
            args,
            [
                "collection-chain",
                "/repo",
                "CTIO1m/calib/curated",
                "CTIO1m/calib/crosstalk",
                "--mode",
                "prepend",
            ],
        )


class TestMeasureArgs(unittest.TestCase):
    def test_qgraph_args_include_pipeline_inputs_and_isr(self):
        args = ct.measure_qgraph_args(
            repo="/repo",
            pipeline="/cp/cpCrosstalk.yaml",
            inputs="CTIO1m/calib/current,CTIO1m/raw/20070321/ts1",
            output="CTIO1m/calib/crosstalk/gen",
            output_run="CTIO1m/calib/crosstalk/gen/ts1",
            qgraph_path="/q/ct.qg",
            where="instrument='CTIO1m'",
            isr_args=["--config", "cpCrosstalkIsr:doDefect=False"],
            datastore_records=False,
        )
        self.assertEqual(args[0], "qgraph")
        self.assertEqual(args[args.index("-p") + 1], "/cp/cpCrosstalk.yaml")
        self.assertEqual(
            args[args.index("-i") + 1], "CTIO1m/calib/current,CTIO1m/raw/20070321/ts1"
        )
        self.assertEqual(
            args[args.index("--output-run") + 1], "CTIO1m/calib/crosstalk/gen/ts1"
        )
        self.assertIn("cpCrosstalkIsr:doDefect=False", args)
        self.assertNotIn("--qgraph-datastore-records", args)

    def test_qgraph_args_add_datastore_records_when_needed(self):
        args = ct.measure_qgraph_args(
            repo="/repo",
            pipeline="/p.yaml",
            inputs="a,b",
            output="o",
            output_run="o/ts",
            qgraph_path="/q.qg",
            where="x",
            isr_args=[],
            datastore_records=True,
        )
        self.assertIn("--qgraph-datastore-records", args)

    def test_run_args(self):
        args = ct.measure_run_args("/repo", "/q/ct.qg", jobs=4)
        self.assertEqual(args[0], "run")
        self.assertEqual(args[args.index("-g") + 1], "/q/ct.qg")
        self.assertEqual(args[args.index("-j") + 1], "4")
        self.assertIn("--register-dataset-types", args)


if __name__ == "__main__":
    unittest.main()
