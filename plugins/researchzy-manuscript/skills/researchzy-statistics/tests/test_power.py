"""power.py: refusals, and every power calculation checked against statsmodels or a simulation.

No formula is trusted unchecked: the noncentral t, the noncentral F and the proportions formula are
compared with statsmodels' solvers; Welch's test with unequal SDs and the correlation test, which
statsmodels does not cover, are compared with a seeded simulation of the test scipy runs.
"""
from __future__ import annotations

import importlib.util
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "power.py"
spec = importlib.util.spec_from_file_location("power_under_test", SCRIPT)
pw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pw)

try:
    import numpy as np
    from statsmodels.stats.power import FTestAnovaPower, TTestIndPower, TTestPower
    from statsmodels.stats.proportion import power_proportions_2indep
except ImportError:
    np = None

PRIOR = ["--effect-source", "prior-study", "--source-note", "doi:10.1000/xyz123, Table 2, SD of the control arm"]
NEEDS_SCIPY = unittest.skipIf(pw.stats is None, "scipy is not installed")
NEEDS_STATSMODELS = unittest.skipIf(pw.stats is None or np is None, "scipy, numpy or statsmodels is not installed")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = pw.main([*argv, "--outcome", "systolic pressure at 12 weeks", "--out", str(self.out)])
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue(), err.getvalue()


class RefusalTests(Base):
    """These run before scipy is needed, so they run with any Python."""

    def refused(self, message, *argv):
        code, _, err = self.run_cli(*argv)
        self.assertEqual(code, 2, err)
        self.assertIn(message, err)

    def test_observed_power_is_refused(self):
        self.refused("observed power is refused", "two-means", "--diff", "2", "--sd", "5", "--n", "30",
                     "--effect-source", "observed")

    def test_a_prior_study_needs_its_doi_and_the_place(self):
        base = ["two-means", "--diff", "5", "--sd", "10", "--effect-source", "prior-study"]
        self.refused("needs --source-note with the DOI", *base)
        self.refused("needs --source-note with the DOI", *base, "--source-note", "Smith et al. Table 2")
        self.refused("needs --source-note with the DOI", *base, "--source-note", "doi:10.1000/xyz123")

    def test_invalid_requests(self):
        self.refused("the effect is zero", "two-means", "--diff", "0", "--sd", "10", *PRIOR)
        self.refused("needs --sd", "two-means", "--diff", "5", *PRIOR)
        self.refused("needs --n", "two-means", "--sd", "10", "--solve", "effect", *PRIOR)
        self.refused("no one-sided form", "anova", "--means", "1,2,3", "--sd", "2", "--alternative", "one-sided", *PRIOR)
        self.refused("--icc and --cluster-size go together", "two-means", "--diff", "5", "--sd", "10", "--icc", "0.05", *PRIOR)
        self.refused("between alpha and 1", "two-means", "--diff", "5", "--sd", "10", "--power", "0.01", *PRIOR)
        self.refused("strictly between 0 and 1", "two-proportions", "--p1", "1.2", "--p2", "0.1", *PRIOR)

    @unittest.skipUnless(pw.stats is None, "scipy is installed")
    def test_missing_scipy_is_reported(self):
        code, out, _ = self.run_cli("two-means", "--diff", "5", "--sd", "10", *PRIOR)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["status"], "not_run")
        self.assertIn("needs scipy", json.loads(out)["message"])


@NEEDS_STATSMODELS
class AgainstStatsmodels(unittest.TestCase):
    def test_two_means_equal_sds_and_groups(self):
        for d, n in ((0.2, 50), (0.5, 64), (0.8, 12), (1.2, 4)):
            ours = pw.power_of("two-means", n, {"diff": d * 7, "sd1": 7, "sd2": 7, "ratio": 1}, 0.05, 2)
            self.assertAlmostEqual(ours, TTestIndPower().power(d, n, 0.05, ratio=1), places=9)
        ours = pw.power_of("two-means", 40, {"diff": 3, "sd1": 6, "sd2": 6, "ratio": 1}, 0.025, 1)
        self.assertAlmostEqual(ours, TTestIndPower().power(0.5, 40, 0.025, alternative="larger"), places=9)

    def test_two_means_unequal_groups_equal_sds(self):
        # Welch's df is a little below n1 + n2 - 2, so the power is a little below Student's
        ours = pw.power_of("two-means", 30, {"diff": 3, "sd1": 6, "sd2": 6, "ratio": 2}, 0.05, 2)
        theirs = TTestIndPower().power(0.5, 30, 0.05, ratio=2)
        self.assertLess(ours, theirs)
        self.assertAlmostEqual(ours, theirs, delta=0.005)

    def test_paired(self):
        for dz, n in ((0.3, 90), (0.5, 34), (1.0, 8)):
            ours = pw.power_of("paired", n, {"diff": dz * 4, "sd_diff": 4}, 0.05, 2)
            self.assertAlmostEqual(ours, TTestPower().power(dz, n, 0.05), places=9)

    def test_two_proportions(self):
        for p1, p2, n, ratio in ((0.30, 0.15, 100, 1), (0.6, 0.45, 150, 1), (0.1, 0.25, 80, 1.5)):
            ours = pw.power_of("two-proportions", n, {"p1": p1, "p2": p2, "ratio": ratio}, 0.05, 2)
            theirs = power_proportions_2indep(p1 - p2, p2, n, ratio=ratio, alpha=0.05).power
            self.assertAlmostEqual(ours, theirs, places=9)

    def test_anova(self):
        for f, n, k in ((0.25, 20, 3), (0.1, 100, 4), (0.4, 10, 5)):
            ours = pw.power_of("anova", n, {"f": f, "k": k}, 0.05, 2)
            self.assertAlmostEqual(ours, FTestAnovaPower().power(f, n * k, 0.05, k_groups=k), places=9)

    def test_solved_n_against_statsmodels(self):
        e = {"diff": 5, "sd1": 10, "sd2": 10, "ratio": 1}
        self.assertEqual(pw.solve_n("two-means", e, 0.05, 2, 0.8), math.ceil(TTestIndPower().solve_power(0.5, power=0.8, alpha=0.05)))
        self.assertEqual(pw.solve_n("paired", {"diff": 2, "sd_diff": 5}, 0.05, 2, 0.9),
                         math.ceil(TTestPower().solve_power(0.4, power=0.9, alpha=0.05)))
        total = FTestAnovaPower().solve_power(0.25, power=0.8, alpha=0.05, k_groups=3)
        n = pw.solve_n("anova", {"f": 0.25, "k": 3}, 0.05, 2, 0.8)
        self.assertGreaterEqual(n * 3, total)
        self.assertLess((n - 1) * 3, total)


@NEEDS_STATSMODELS
class AgainstSimulation(unittest.TestCase):
    """Seeded simulations of the tests scipy runs; 20,000 data sets give a Monte Carlo SE under 0.004."""
    REPS = 20000

    def test_welch_with_unequal_sds_and_groups(self):
        from scipy import stats
        rng = np.random.default_rng(20261112)
        n1, n2, sd1, sd2, diff = 15, 30, 4.0, 8.0, 4.0
        a = rng.normal(diff, sd1, (self.REPS, n1))
        b = rng.normal(0.0, sd2, (self.REPS, n2))
        simulated = float(np.mean(stats.ttest_ind(a, b, axis=1, equal_var=False).pvalue < 0.05))
        ours = pw.power_of("two-means", n1, {"diff": diff, "sd1": sd1, "sd2": sd2, "ratio": 2}, 0.05, 2)
        self.assertAlmostEqual(ours, simulated, delta=0.015)

    def test_correlation(self):
        from scipy import stats
        rng = np.random.default_rng(20261113)
        n, rho = 30, 0.4
        x = rng.normal(size=(self.REPS, n))
        y = rho * x + math.sqrt(1 - rho ** 2) * rng.normal(size=(self.REPS, n))
        try:
            p = stats.pearsonr(x, y, axis=1).pvalue
        except TypeError:
            self.skipTest("this scipy's pearsonr has no axis argument")
        ours = pw.power_of("correlation", n, {"r": rho}, 0.05, 2)
        self.assertAlmostEqual(ours, float(np.mean(p < 0.05)), delta=0.015)


@NEEDS_SCIPY
class CommandTests(Base):
    def test_sample_size_with_a_table_inflation_and_the_five_elements(self):
        code, out, err = self.run_cli("two-means", "--diff", "5", "--sd", "10", "--units", "mmHg", "--unit", "patients",
                                      "--attrition", "0.1", "--icc", "0.05", "--cluster-size", "20", *PRIOR)
        self.assertEqual(code, 0, err)
        record = json.loads((self.out / "power.json").read_text())
        self.assertEqual(record["result"]["n_per_group"], [64, 64])
        self.assertAlmostEqual(record["inflation"]["design_effect"], 1.95)
        self.assertEqual(record["inflation"]["n_per_group"], [139, 139])       # 64 * 1.95 / 0.9 = 138.7
        self.assertEqual(record["inflation"]["clusters_per_group"], [7, 7])
        data = record["table"]["data"]
        self.assertEqual(len(data), 5)
        self.assertEqual(list(data[2]["n_per_group"]), ["0.8", "0.85", "0.9", "0.95"])
        self.assertEqual(data[2]["n_per_group"]["0.8"], 64)
        text = record["justification"]
        for element in ("systolic pressure at 12 weeks", "a difference in means of 5 mmHg", "doi:10.1000/xyz123, Table 2",
                        "two-sided alpha of 0.05", "power of 80%", "Welch two-sample t test", "64 patients per group",
                        "10% attrition", "design effect of 1.95", "139 patients per group", "SciPy"):
            self.assertIn(element, text)
        self.assertIn("| difference in means 5 mmHg, d 0.5 (planned) | 64 | 73 | 86 | 105 |", (self.out / "power.md").read_text())

    def test_a_convention_is_labelled(self):
        code, _, err = self.run_cli("two-means", "--diff", "0.5", "--sd", "1", "--effect-source", "convention")
        self.assertEqual(code, 0, err)
        record = json.loads((self.out / "power.json").read_text())
        self.assertTrue(record["effect_source"]["convention"])
        self.assertIn("which is a convention and not an estimate", record["justification"])
        self.assertIn("(a convention)", (self.out / "power.md").read_text())
        self.assertTrue(any("is a convention" in w for w in record["warnings"]))

    def test_a_missing_source_note_leaves_a_placeholder(self):
        code, _, _ = self.run_cli("paired", "--diff", "3", "--sd", "6", "--corr", "0.5", "--effect-source", "pilot")
        self.assertEqual(code, 0)
        record = json.loads((self.out / "power.json").read_text())
        self.assertIn("[Author input needed:", record["justification"])
        self.assertIn("needs 34 participants.", record["justification"])      # one group: no "per group", no total
        self.assertAlmostEqual(record["inputs"]["corr"], 0.5)

    def test_solve_for_effect_is_a_sensitivity_analysis(self):
        code, _, err = self.run_cli("two-means", "--sd", "10", "--n", "64", "--solve", "effect", *PRIOR)
        self.assertEqual(code, 0, err)
        record = json.loads((self.out / "power.json").read_text())
        self.assertEqual(record["purpose"], "sensitivity analysis")
        self.assertTrue(record["justification"].startswith("Sensitivity analysis, not a sample-size justification"))
        self.assertIn("power to detect a difference in means of 4.991 (d = 0.4991)", record["justification"])
        self.assertAlmostEqual(record["result"]["detectable_effect"]["higher"]["difference in means"], 4.991, delta=0.001)
        self.assertEqual([row["n"] for row in record["table"]["data"]], [32, 48, 64, 96, 128])

    def test_proportions_power_and_both_directions(self):
        code, _, _ = self.run_cli("two-proportions", "--p1", "0.30", "--p2", "0.15", "--n", "100", *PRIOR)
        self.assertEqual(code, 0)
        self.assertAlmostEqual(json.loads((self.out / "power.json").read_text())["result"]["power"], 0.7223, places=4)
        code, _, _ = self.run_cli("two-proportions", "--p2", "0.15", "--n", "100", "--solve", "effect", *PRIOR)
        found = json.loads((self.out / "power.json").read_text())["result"]["detectable_effect"]
        self.assertGreater(found["higher"]["p1"], 0.15)
        self.assertLess(found["lower"]["p1"], 0.15)

    def test_anova_and_correlation_run(self):
        self.assertEqual(self.run_cli("anova", "--means", "10,12,15", "--sd", "6", *PRIOR)[0], 0)
        self.assertGreater(json.loads((self.out / "power.json").read_text())["result"]["n_per_group"][0], 10)
        self.assertEqual(self.run_cli("correlation", "--r", "0.3", *PRIOR)[0], 0)
        self.assertEqual(json.loads((self.out / "power.json").read_text())["result"]["n_per_group"], [85])


if __name__ == "__main__":
    unittest.main()
