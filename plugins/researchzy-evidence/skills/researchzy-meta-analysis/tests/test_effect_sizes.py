"""effect_sizes.py: conversions, effect sizes, what it refuses and warns about, and the files it writes.

Reference values are textbook formulas worked by hand (the literals were computed independently with
scipy); statsmodels, when installed, is a second oracle for Hedges' g and the 2x2 measures.
"""
from __future__ import annotations

import csv
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


es = load("effect_sizes", "effect_sizes_under_test")
try:
    from scipy import special
except ImportError:
    special = None
try:
    from statsmodels.stats.meta_analysis import effectsize_2proportions, effectsize_smd
except ImportError:
    effectsize_smd = effectsize_2proportions = None

HEADER = ["study", "outcome", "timepoint", "arm", "n", "design", "reported_as", "value", "spread", "low", "high",
          "ci_level", "events", "cluster_size", "icc", "icc_source", "corr", "corr_source", "units", "reverse",
          "locator", "notes"]


def arm(study, name, n, form, **cells):
    base = {"study": study, "outcome": "weight", "timepoint": "12 weeks", "arm": name, "n": str(n), "reported_as": form,
            "units": "kg", "locator": "Table 2"}
    base.update({key: str(value) for key, value in cells.items()})
    return base


def parsed(form, measure="MD", **cells):
    return es.parse(2, arm("A", "treatment", cells.pop("n", 40), form, **cells), measure)


class QuantileTests(unittest.TestCase):
    def test_t_quantile_without_scipy(self):
        saved, es._stats = es._stats, None
        try:
            for p, df, expected in ((0.975, 19, 2.093024054408263), (0.975, 9, 2.2621571628540993),
                                    (0.975, 1, 12.706204736432095), (0.995, 5, 4.032142983557536),
                                    (0.975, 200, 1.9718962236316089)):
                self.assertAlmostEqual(es.t_quantile(p, df), expected, places=9)
            self.assertAlmostEqual(es.t_quantile(0.025, 19), -2.093024054408263, places=9)
        finally:
            es._stats = saved

    def test_incomplete_beta_against_scipy(self):
        if special is None:
            self.skipTest("scipy is not installed")
        for a, b, x in ((0.5, 9.5, 0.3), (2.0, 3.0, 0.7), (10.0, 0.5, 0.95), (50.0, 0.5, 0.99), (1.5, 1.5, 0.5)):
            self.assertAlmostEqual(es.beta_reg(a, b, x), float(special.betainc(a, b, x)), places=12)

    def test_hedges_correction(self):
        self.assertAlmostEqual(es.hedges_j(10), 0.9227456080530874, places=12)
        self.assertAlmostEqual(es.hedges_j(38), 0.9801104021309504, places=12)
        self.assertAlmostEqual(es.hedges_j(10, exact=False), 1 - 3 / 39, places=12)


class RowTests(unittest.TestCase):
    def test_conversions_to_mean_and_sd(self):
        self.assertAlmostEqual(parsed("mean_se", value=5, spread=0.5)["sd"], 0.5 * math.sqrt(40))
        r = parsed("mean_ci", n=20, value=10, low=7.5, high=12.5, ci_level=95)
        self.assertAlmostEqual(r["sd"], 5.3417159081145105, places=9)       # t(19), not z (which gives 5.70)
        self.assertIn("t(19) = 2.0930", r["conv"][0])
        r = parsed("median_iqr", n=30, value=15, low=10, high=20)
        self.assertEqual((r["mean"], r["estimated"]), (15, True))
        self.assertAlmostEqual(r["sd"], 7.78420218787042, places=9)         # Wan 2014, IQR / 1.2847
        r = parsed("change_median_range", n=40, value=15, low=3, high=27)
        self.assertAlmostEqual(r["mean"], 15)
        self.assertAlmostEqual(r["sd"], 5.564944582708583, places=9)
        self.assertTrue(r["change"])
        self.assertEqual(parsed("mean_sd", value=5, spread=2, reverse="yes")["mean"], -5)

    def test_study_level_rows(self):
        r = parsed("ratio_ci", measure="OR", value="0.62", low="0.45", high="0.85")
        self.assertAlmostEqual(r["yi"], math.log(0.62))
        self.assertAlmostEqual(r["vi"], 0.16224501361672847 ** 2, places=12)
        self.assertEqual(r["warn"], [])
        r = parsed("r", measure="Z", n=50, value=0.3)
        self.assertAlmostEqual(r["yi"], math.atanh(0.3))
        self.assertAlmostEqual(r["vi"], 1 / 47)
        self.assertAlmostEqual(parsed("yi_se", value=-0.2, spread=0.1)["vi"], 0.01)

    def test_ratio_cis_that_are_impossible_or_asymmetric(self):
        self.assertIn("impossible ratio CI", parsed("ratio_ci", measure="OR", value="1.50", low="1.60", high="2.10")["refused"])
        self.assertIn("no logarithm", parsed("ratio_ci", measure="RR", value="0.5", low="0.0", high="1.2")["refused"])
        r = parsed("ratio_ci", measure="OR", value="1.50", low="1.10", high="3.96")
        self.assertIsNone(r["refused"])
        self.assertIn("asymmetric on the log scale", r["warn"][0])
        # rounding alone never warns: 1.5 (1.1 to 2.0) is symmetric within its printed decimals
        self.assertEqual(parsed("ratio_ci", measure="OR", value="1.5", low="1.1", high="2.0")["warn"], [])

    def test_cluster_and_crossover_rows(self):
        r = parsed("mean_sd", n=100, value=5, spread=2, design="cluster", cluster_size=21, icc=0.05,
                   icc_source="pilot study, Table 1")
        self.assertAlmostEqual(r["n_eff"], 50)                               # design effect 1 + 20 x 0.05 = 2
        self.assertIn("design effect", r["conv"][0])
        self.assertIn("cluster_size, icc and icc_source",
                      parsed("mean_sd", value=5, spread=2, design="cluster", cluster_size=21, icc=0.05)["refused"])
        r = parsed("yi_se", value=0.3, spread=0.1, design="cluster", icc_source="adjusted")
        self.assertIsNone(r["refused"])
        self.assertAlmostEqual(r["vi"], 0.01)
        self.assertIn("icc_source 'adjusted' only", parsed("mean_sd", value=5, spread=2, design="cluster",
                                                            icc_source="adjusted")["refused"])
        self.assertIn("needs corr", parsed("mean_sd", value=5, spread=2, design="crossover")["refused"])
        self.assertIn("paired analysis", parsed("events", measure="OR", events=3, design="crossover",
                                                corr=0.5, corr_source="x")["refused"])

    def test_bad_rows_are_refused(self):
        self.assertIn("needs low, high", parsed("mean_ci", value=10)["refused"])
        self.assertIn("is not one of", parsed("mean_sem", value=10, spread=1)["refused"])
        self.assertIn("cannot enter a MD pool", parsed("events", events=3)["refused"])
        self.assertIn("events must lie between", parsed("events", measure="OR", events=41)["refused"])
        self.assertIn("must lie between low", parsed("median_iqr", value=25, low=10, high=20)["refused"])
        self.assertIn("is not a number", parsed("mean_sd", value="5,2", spread=1)["refused"])
        self.assertIn("no --measure", es.parse(2, arm("A", "control", 10, "mean_sd", value=1, spread=1), None)["refused"])
        self.assertIn("no locator", parsed("mean_sd", value=5, spread=2, locator="")["warn"][0])


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def run_es(self, rows, *options):
        columns = HEADER + [k for r in rows for k in r if k not in HEADER]
        with open("extraction.csv", "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(columns)))
            writer.writeheader()
            writer.writerows(rows)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = es.main(["extraction.csv", *options])
        effects = list(csv.DictReader(io.StringIO(Path("effects.csv").read_text(encoding="utf-8")))) \
            if Path("effects.csv").exists() else []
        return code, (json.loads(out.getvalue()) if out.getvalue().strip() else None), effects

    def pair(self, study, t, c, form="mean_sd", **common):
        return [arm(study, "treatment", t[0], form, value=t[1], spread=t[2], **common),
                arm(study, "control", c[0], form, value=c[1], spread=c[2], **common)]


class EffectTests(Run):
    def test_mean_difference_uses_each_groups_own_variance(self):
        code, summary, effects = self.run_es(self.pair("A", (100, 5, 4), (20, 2, 12)), "--measure", "MD")
        self.assertEqual(code, 0, summary)
        self.assertAlmostEqual(float(effects[0]["yi"]), 3)
        self.assertAlmostEqual(float(effects[0]["se"]), math.sqrt(16 / 100 + 144 / 20), places=9)   # 2.71, not 1.48

    def test_hedges_g(self):
        code, summary, effects = self.run_es(self.pair("A", (20, 10, 2), (22, 8, 2.5)), "--measure", "SMD")
        d = 2 / math.sqrt((19 * 4 + 21 * 6.25) / 40)
        g = es.hedges_j(40) * d
        self.assertAlmostEqual(float(effects[0]["yi"]), g, places=10)
        self.assertAlmostEqual(float(effects[0]["vi"]), 42 / 440 + g ** 2 / (2 * (42 - 3.94)), places=10)
        if effectsize_smd is None:
            self.skipTest("statsmodels is not installed")
        g_sm, var_sm = effectsize_smd(10.0, 2.0, 20, 8.0, 2.5, 22)              # uses J = 1 - 3/(4N - 9)
        self.assertAlmostEqual(g * es.hedges_j(40, exact=False) / es.hedges_j(40), float(g_sm), places=10)
        self.assertAlmostEqual(float(var_sm), 42 / 440 + float(g_sm) ** 2 / (2 * 38.06), places=10)

    def test_two_by_two_measures(self):
        rows = [arm("A", "treatment", 100, "events", events=15), arm("A", "control", 100, "events", events=25)]
        expected = {"OR": (math.log(15 * 75 / (85 * 25)), 1 / 15 + 1 / 85 + 1 / 25 + 1 / 75),
                    "RR": (math.log(0.6), 1 / 15 - 1 / 100 + 1 / 25 - 1 / 100),
                    "RD": (-0.10, 0.15 * 0.85 / 100 + 0.25 * 0.75 / 100)}
        for measure, (yi, vi) in expected.items():
            code, summary, effects = self.run_es(rows, "--measure", measure)
            self.assertEqual(code, 0, summary)
            self.assertAlmostEqual(float(effects[0]["yi"]), yi, places=10)
            self.assertAlmostEqual(float(effects[0]["vi"]), vi, places=10)
            if effectsize_2proportions is not None:
                statistic = {"OR": "odds-ratio", "RR": "risk-ratio", "RD": "diff"}[measure]
                theirs = effectsize_2proportions(15, 100, 25, 100, statistic=statistic)
                self.assertAlmostEqual(float(theirs[0]), yi, places=10)
                self.assertAlmostEqual(float(theirs[1]), vi, places=10)

    def test_crossover_uses_the_within_person_correlation(self):
        rows = [arm("A", "treatment", 24, "mean_sd", value=12, spread=5, design="crossover", corr=0.6, corr_source="Table 3"),
                arm("A", "control", 24, "mean_sd", value=10, spread=6, design="crossover", corr=0.6, corr_source="Table 3")]
        code, summary, effects = self.run_es(rows, "--measure", "MD")
        self.assertEqual((code, float(effects[0]["yi"])), (0, 2.0))
        self.assertAlmostEqual(float(effects[0]["vi"]), (25 + 36 - 2 * 0.6 * 5 * 6) / 24)

    def test_several_arms_combined_split_or_dropped(self):
        rows = [arm("A", "low", 20, "mean_sd", value=10, spread=2), arm("A", "high", 30, "mean_sd", value=12, spread=3),
                arm("A", "control", 40, "mean_sd", value=9, spread=2.5)]
        code, summary, effects = self.run_es(rows, "--measure", "MD")
        self.assertEqual(code, 1)
        self.assertIn("2 arms against one control", effects[0]["refused"])
        code, summary, effects = self.run_es(rows, "--measure", "MD", "--combine", "A")
        self.assertEqual((code, len(effects), effects[0]["comparison"]), (0, 1, "low + high vs control"))
        self.assertAlmostEqual(float(effects[0]["yi"]), 11.2 - 9)              # (20 x 10 + 30 x 12) / 50
        self.assertAlmostEqual(float(effects[0]["vi"]), 2.8030595529069404 ** 2 / 50 + 2.5 ** 2 / 40, places=10)
        code, summary, effects = self.run_es(rows, "--measure", "MD", "--split", "A")
        self.assertEqual((code, [e["n2"] for e in effects]), (0, ["20", "20"]))
        self.assertEqual(sum(float(e["participants"]) for e in effects), 90)
        code, summary, effects = self.run_es(rows, "--measure", "MD", "--drop", "A=low")
        self.assertEqual((code, effects[0]["comparison"]), (0, "high vs control"))
        self.assertIn("arm 'low' left out", effects[0]["conversions"])


class PoolRuleTests(Run):
    def test_a_study_twice_in_one_pool(self):
        rows = self.pair("A", (20, 5, 2), (20, 4, 2)) + [arm("A", "treatment", 20, "mean_sd", value=6, spread=2)]
        code, summary, effects = self.run_es(rows + self.pair("B", (30, 5, 2), (30, 4, 2)), "--measure", "MD")
        self.assertEqual(code, 1)
        self.assertIn("appears twice", summary["refused"][0])
        rows = self.pair("A", (20, 5, 2), (20, 4, 2)) + [arm("A", "", 40, "yi_se", value=1, spread=0.5)]
        self.assertIn("appears twice", self.run_es(rows, "--measure", "MD")[1]["refused"][0])

    def test_units_and_change_scores(self):
        rows = self.pair("A", (20, 5, 2), (20, 4, 2)) + self.pair("B", (30, 5, 2), (30, 4, 2), units="lb")
        code, summary, _ = self.run_es(rows, "--measure", "MD")
        self.assertEqual(code, 1)
        self.assertIn("needs one unit", summary["refused"][0])
        self.assertEqual(self.run_es(rows, "--measure", "SMD")[0], 0)           # an SMD may mix scales
        rows = self.pair("A", (20, -2, 2), (20, -1, 2), form="change_sd") + self.pair("B", (30, 70, 9), (30, 72, 9))
        code, summary, _ = self.run_es(rows, "--measure", "SMD")
        self.assertEqual(code, 1)
        self.assertIn("mixes change-from-baseline and final values", summary["refused"][0])
        code, summary, _ = self.run_es(rows, "--measure", "MD")
        self.assertEqual(code, 0)
        self.assertIn("mixes change and final values", summary["pools"][0]["notes"][0])

    def test_zero_cells_are_never_corrected_silently(self):
        rows = [arm("A", "treatment", 50, "events", events=0), arm("A", "control", 50, "events", events=4),
                arm("B", "treatment", 60, "events", events=6), arm("B", "control", 60, "events", events=11),
                arm("C", "treatment", 40, "events", events=0), arm("C", "control", 40, "events", events=0)]
        code, summary, effects = self.run_es(rows, "--measure", "OR")
        self.assertEqual(code, 1)
        self.assertIn("1 study has a zero cell (A): choose --sparse weight=mh", summary["refused"][0])
        code, summary, effects = self.run_es(rows, "--measure", "OR", "--sparse", "cc")
        self.assertEqual((code, summary["pools"][0]["k"], summary["pools"][0]["excluded"]), (0, 2, 1))
        a = next(e for e in effects if e["study"] == "A")
        self.assertAlmostEqual(float(a["yi"]), math.log(0.5 * 46.5 / (50.5 * 4.5)))
        self.assertIn("no events, or only events, in both arms", next(e for e in effects if e["study"] == "C")["excluded"])
        code, summary, effects = self.run_es(rows, "--measure", "OR", "--sparse", "mh")
        self.assertIn("the pool uses the counts", next(e for e in effects if e["study"] == "A")["conversions"])
        self.assertEqual(self.run_es(rows, "--measure", "RD", "--sparse", "mh")[1]["pools"][0]["excluded"], 0)
        self.assertIn("only for an OR pool", self.run_es(rows, "--measure", "RR", "--sparse", "peto")[1]["refused"][0])
        self.assertIn("only for a sparse pool without zero cells",
                      self.run_es(rows, "--measure", "OR", "--sparse", "iv")[1]["refused"][0])

    def test_rare_events_without_zero_cells(self):
        rows = [arm("A", "treatment", 900, "events", events=3), arm("A", "control", 900, "events", events=6),
                arm("B", "treatment", 800, "events", events=2), arm("B", "control", 800, "events", events=5)]
        code, summary, _ = self.run_es(rows, "--measure", "OR")
        self.assertEqual(code, 1)
        self.assertIn("pooled event rate is 0.47%, below 1%", summary["refused"][0])        # 16 / 3400
        self.assertEqual(self.run_es(rows, "--measure", "OR", "--sparse", "iv")[0], 0)
        rows.append(arm("C", "", 500, "ratio_ci", value="0.80", low="0.40", high="1.60"))
        self.assertIn("needs 2x2 counts", self.run_es(rows, "--measure", "OR", "--sparse", "mh")[1]["refused"][0])

    def test_an_sd_that_looks_like_an_se(self):
        rows = (self.pair("A", (42, -3.1, 2.9), (40, -1.2, 3.2)) + self.pair("B", (38, -2.6, 0.45), (37, -0.9, 0.52))
                + self.pair("C", (55, -1.6, 3.4), (57, -1.0, 3.1)) + self.pair("D", (28, -3.8, 3.0), (29, -1.4, 2.7)))
        code, summary, effects = self.run_es(rows, "--measure", "MD")
        self.assertEqual(code, 0)
        self.assertEqual(len(summary["warnings"]), 2)
        self.assertIn("line 4: the SD 0.45 is far below the other studies' median SD", summary["warnings"][0])
        rows = self.pair("A", (100, 5, 2.0), (100, 4, 2.2)) + self.pair("B", (30, 5, 3), (30, 4, 3)) + \
            self.pair("C", (30, 5, 3.2), (30, 4, 2.9))
        self.assertEqual(self.run_es(rows, "--measure", "MD")[1]["warnings"], [])  # small, but not an SE
        rows = [arm("A", "treatment", 25, "mean_sd", value=10, spread=1.02, low=8, high=12), arm("A", "control", 25, "mean_sd",
                value=9, spread=4, low=7.3, high=10.7)] + self.pair("B", (30, 5, 3), (30, 4, 3))
        warnings = self.run_es(rows, "--measure", "MD")[1]["warnings"]
        self.assertIn("equals the CI half-width / t", warnings[0])

    def test_files_and_bad_input(self):
        rows = [dict(r, dose=d) for r, d in zip(self.pair("A", (20, 5, 2), (20, 4, 2)) +
                                                  self.pair("B", (30, 5, 2), (30, 4, 2)), ("high", "high", "low", "low"))]
        code, summary, effects = self.run_es(rows, "--measure", "weight=MD")
        self.assertEqual((code, summary["exit"]), (0, 0))
        self.assertEqual([e["dose"] for e in effects], ["high", "low"])           # study columns travel along
        self.assertEqual(effects[0]["pool"], "weight @ 12 weeks")
        self.assertIn("## weight @ 12 weeks: MD, k = 2 (ok)", Path("effects.md").read_text())
        code, summary, _ = self.run_es(rows, "--measure", "MD", "--combine", "Zed 2020")
        self.assertIn("'zed 2020', which is not a study in the table", summary["warnings"][0])
        Path("extraction.csv").write_text("study,outcome,arm,n\nA,w,control,10\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(es.main(["extraction.csv", "--measure", "MD"]), 2)
            for bad in (["--measure", "MEAN"], ["--measure", "MD", "--drop", "A"]):
                with self.assertRaises(SystemExit) as caught:
                    es.main(["extraction.csv", *bad])
                self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
