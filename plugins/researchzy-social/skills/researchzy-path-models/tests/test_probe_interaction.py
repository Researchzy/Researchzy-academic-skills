"""probe_interaction.py: the t distribution, simple slopes on the moderator's own scale, Johnson-Neyman bounds, probes
outside the observed range, and the command line."""
from __future__ import annotations

import importlib.util
import io
import json
import math
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pi = load("probe_interaction", "probe_interaction_under_test")

# A first-stage moderation like PM-1's: support (the moderator) is skewed towards the top of a 1-7 scale.
INPUTS = {"b1": 0.40, "b3": 0.15, "var_b1": 0.0024, "var_b3": 0.0021, "cov_b13": -0.0002, "df": 344, "w_min": 1.0,
          "w_max": 7.0, "w_mean": 6.02, "w_sd": 1.31, "center": 6.02}


class DistributionTests(unittest.TestCase):
    def test_critical_values_and_p_values_match_published_constants(self):
        self.assertAlmostEqual(pi.critical(0.95, 10), 2.228138851986274, places=9)
        self.assertAlmostEqual(pi.critical(0.95, 30), 2.042272456301238, places=9)
        self.assertAlmostEqual(pi.critical(0.99, 5), 4.032142983557536, places=8)
        self.assertAlmostEqual(pi.critical(0.95, None), 1.959963984540054, places=9)
        self.assertAlmostEqual(pi.two_sided_p(2.0, 20), 0.059265535446570, places=9)
        self.assertAlmostEqual(pi.two_sided_p(1.0, 1), 0.5, places=12)          # Cauchy: P(|T| > 1) = 1/2
        self.assertEqual(pi.two_sided_p(0.0, 7), 1.0)
        self.assertAlmostEqual(pi.two_sided_p(1.959963984540054, None), 0.05, places=9)

    def test_incomplete_beta(self):
        self.assertAlmostEqual(pi.betainc(3.0, 3.0, 0.5), 0.5, places=12)      # symmetric case
        self.assertAlmostEqual(pi.betainc(1.0, 1.0, 0.3), 0.3, places=12)      # uniform
        self.assertAlmostEqual(pi.betainc(2.0, 1.0, 0.6), 0.36, places=12)     # x^2
        self.assertEqual((pi.betainc(2.0, 3.0, 0.0), pi.betainc(2.0, 3.0, 1.0)), (0.0, 1.0))


class ProbeTests(unittest.TestCase):
    def test_simple_slopes_by_hand(self):
        result = pi.probe(**INPUTS, probes=[4.5])
        u = 4.5 - 6.02
        slope = result["slopes"][0]
        self.assertAlmostEqual(slope["slope"], 0.40 + 0.15 * u, places=12)
        self.assertAlmostEqual(slope["se"], math.sqrt(0.0024 + 2 * u * -0.0002 + u * u * 0.0021), places=12)
        self.assertAlmostEqual(slope["t"], slope["slope"] / slope["se"], places=12)
        self.assertAlmostEqual(slope["low"], slope["slope"] - pi.critical(0.95, 344) * slope["se"], places=12)
        self.assertTrue(slope["in_range"])

    def test_centring_moves_b1_but_not_the_slope_at_a_moderator_value(self):
        centred = pi.probe(**INPUTS, probes=[5.0])["slopes"][0]
        # The same model fitted on the raw moderator: b1 is then the slope at w = 0, var and cov change with it.
        b1, c = 0.40 - 0.15 * 6.02, 6.02
        var_b1 = 0.0024 - 2 * c * -0.0002 + c * c * 0.0021
        raw = pi.probe(**{**INPUTS, "b1": b1, "var_b1": var_b1, "cov_b13": -0.0002 - c * 0.0021, "center": 0.0},
                       probes=[5.0])["slopes"][0]
        for key in ("slope", "se", "t", "p"):
            self.assertAlmostEqual(centred[key], raw[key], places=10)

    def test_plus_one_sd_of_a_skewed_moderator_lies_outside_the_range(self):
        result = pi.probe(**INPUTS, probes=["mean-1sd", "mean", "mean+1sd", 7])
        self.assertEqual([s["label"] for s in result["slopes"]], ["mean-1sd", "mean", "mean+1sd", "7"])
        self.assertAlmostEqual(result["slopes"][2]["w"], 7.33, places=12)
        self.assertEqual(result["out_of_range"], ["mean+1sd"])
        self.assertEqual([s["in_range"] for s in result["slopes"]], [True, True, False, True])

    def test_johnson_neyman_roots_sit_at_the_critical_value(self):
        result = pi.probe(**INPUTS, probes=[6.02])
        jn, crit = result["jn"], result["t_crit"]
        self.assertEqual(len(jn["roots"]), 2)
        for w in jn["roots"]:
            u = w - 6.02
            t = (0.40 + 0.15 * u) / math.sqrt(0.0024 + 2 * u * -0.0002 + u * u * 0.0021)
            self.assertAlmostEqual(abs(t), crit, places=8)
        self.assertEqual(jn["roots_in_range"], [False, True])
        self.assertEqual(len(jn["significant_in_range"]), 1)
        region = jn["significant_in_range"][0]
        self.assertAlmostEqual(region["from"], jn["roots"][1], places=12)
        self.assertEqual((region["to"], region["sign"]), (7.0, "positive"))
        self.assertEqual(jn["significant"], [[None, jn["roots"][0]], [jn["roots"][1], None]])
        self.assertIn("excludes zero from", jn["summary"])

    def test_johnson_neyman_cases_without_two_roots(self):
        # a slope that never crosses zero (b3 = 0 with no variance): it differs from zero everywhere
        everywhere = pi.johnson_neyman(5.0, 0.0, 0.01, 0.0, 0.0, 1.96, 0.0, -10.0, 10.0)
        self.assertEqual((everywhere["roots"], everywhere["significant"]), ([], [[None, None]]))
        # b3 imprecise and b1 small: nowhere
        nowhere = pi.johnson_neyman(0.01, 0.01, 1.0, 1.0, 0.0, 1.96, 0.0, -1.0, 1.0)
        self.assertEqual((nowhere["significant"], nowhere["significant_in_range"]), ([], []))
        self.assertIn("includes zero everywhere", nowhere["summary"])
        # b3 imprecise, b1 precise: significant only between the roots
        between = pi.johnson_neyman(1.0, 0.05, 0.01, 0.04, 0.0, 1.96, 0.0, -100.0, 100.0)
        self.assertEqual(len(between["significant"]), 1)
        low, high = between["significant"][0]
        self.assertLess(low, 0)
        self.assertGreater(high, 0)

    def test_resolve_and_refusals(self):
        self.assertEqual(pi.resolve(["mean", "mean - 0.5 sd", "4.25", 5], 6.0, 1.0),
                         [("mean", 6.0), ("mean-0.5sd", 5.5), ("4.25", 4.25), ("5", 5.0)])
        for bad in (["high"], [], [float("nan")]):
            with self.assertRaises(ValueError):
                pi.resolve(bad, 6.0, 1.0)
        for change in ({"var_b1": -1.0}, {"w_min": 8.0}, {"level": 1.5}, {"df": 0}, {"b1": float("inf")}):
            with self.assertRaises(ValueError):
                pi.probe(**{**INPUTS, **change}, probes=[5.0])
        with self.assertRaises(ValueError):                 # a covariance that makes the slope variance negative
            pi.probe(**{**INPUTS, "cov_b13": -0.5}, probes=[7.0])


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = pi.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def options(self, *probes):
        return ["--b1", "0.40", "--b3", "0.15", "--var-b1", "0.0024", "--var-b3", "0.0021", "--cov", "-0.0002", "--df",
                "344", "--min", "1", "--max", "7", "--mean", "6.02", "--sd", "1.31", "--center", "6.02", "--probe", *probes]

    def test_inside_the_range_exits_0_and_writes_the_table(self):
        code, out, _ = self.run_cli(*self.options("4.5", "6.25", "7"))
        self.assertEqual(code, 0)
        self.assertEqual([s["w"] for s in json.loads(out)["slopes"]], [4.5, 6.25, 7.0])
        table = Path("paths/probe.md").read_text(encoding="utf-8")
        self.assertIn("| 6.25 | 6.25 | 0.4345 |", table)
        self.assertIn("Johnson-Neyman roots:", table)

    def test_outside_the_range_exits_1_and_says_so(self):
        code, out, _ = self.run_cli(*self.options("mean+1sd"), "--out", "paths/probe-support.md")
        self.assertEqual((code, json.loads(out)["out_of_range"]), (1, ["mean+1sd"]))
        self.assertIn("Outside the observed range: mean+1sd", Path("paths/probe-support.md").read_text(encoding="utf-8"))

    def test_json_input_and_bad_input(self):
        Path("in.json").write_text(json.dumps({**INPUTS, "probes": ["mean"]}), encoding="utf-8")
        code, out, _ = self.run_cli("--json", "in.json", "--level", "0.9")
        self.assertEqual((code, json.loads(out)["level"]), (0, 0.9))
        code, _, err = self.run_cli("--b1", "0.4")
        self.assertEqual(code, 2)
        self.assertIn("missing: b3", err)
        Path("bad.json").write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(self.run_cli("--json", "bad.json")[0], 2)
        self.assertEqual(self.run_cli("--json", "absent.json")[0], 2)
        code, _, err = self.run_cli(*self.options("4"), "--var-b1", "-1")
        self.assertEqual(code, 2)
        self.assertIn("negative", err)


if __name__ == "__main__":
    unittest.main()
