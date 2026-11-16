"""check_meta.py: the meta-analysis fields, labels and numbers, and the paragraph, small-study, methods and
wording rules, on top of the copied check_results.py."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
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


cm = load("check_meta", "check_meta_under_test")

MAIN = {"analysis": "main", "model": "random", "method": "inverse variance", "tau2_method": "REML",
        "ci_method": "Hartung-Knapp", "k": 6, "Q": 8.12, "Q_df": 5, "Q_p": 0.15, "I2": 38.4, "I2_raw": 38.4,
        "tau2": 0.042, "tau": 0.205, "pi": {"low": -2.9, "high": -0.2, "level": 0.95}, "pi_reason": None,
        "small_study": {"status": "not run", "reason": "k = 6, fewer than 10 studies (a convention)"}, "subgroups": [],
        "weights": {"A": 18.0, "B": 17.0, "C": 16.6, "D": 13.7, "E": 21.2, "F": 13.5}}
GOOD = """# Results

Six trials (k = 6; 436 participants) were pooled. The pooled mean difference was −1.55 kg (95% CI −2.27 to −0.83;
t(5) = −5.46, p = 0.0028), with a 95% prediction interval of −2.9 to −0.2 kg; τ² = 0.042, τ = 0.205 and I² = 38%
(Q = 8.12, df = 5, p = 0.15).

Leaving out trial A gave −1.47 kg (95% CI −2.34 to −0.60).

Small-study effects were not assessed: fewer than 10 trials were pooled.
"""
METHODS = """A random-effects model was used because the trials differed in dose and population. τ² was estimated by
restricted maximum likelihood and the interval by the Hartung–Knapp method with its floor.
"""


class CheckMetaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("analysis.py").write_text("print('pooled')\n", encoding="utf-8")
        Path("effects.csv").write_text("pool,yi\nweight,-1.5\n", encoding="utf-8")

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def build(self, **changes):
        rz = load("rz_results", "rz_results_for_check")
        rz.OUT = "meta-analysis"
        meta = copy.deepcopy(MAIN)
        meta.update(changes)
        rz.record(id="weight", question="What is the pooled mean difference?", family="weight", role="primary",
                  test="random-effects inverse-variance meta-analysis", unit="study",
                  n={"studies": meta["k"], "participants": 436},
                  estimate={"name": "pooled mean difference", "value": -1.5459, "units": "kg"},
                  interval={"low": -2.2739, "high": -0.8263, "level": 0.95}, statistic={"name": "t", "value": -5.4587},
                  df=5, p=0.0028, effect_size="estimate", extra={"meta": meta})
        rz.record(id="weight | leave out A", question="What is the pooled mean difference?", family="weight",
                  role="secondary", test="sensitivity analysis: leave out A", unit="study",
                  n={"studies": 5, "participants": 354}, estimate={"name": "pooled mean difference", "value": -1.472,
                                                                     "units": "kg"},
                  interval={"low": -2.343, "high": -0.600, "level": 0.95},
                  extra={"meta": {"analysis": "sensitivity", "model": "random", "tau2_method": "REML",
                                  "ci_method": "Hartung-Knapp", "k": 5, "Q": 6.0, "Q_df": 4, "I2": 33.3, "tau2": 0.03,
                                  "tau": 0.173}})
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["effects.csv"], settings={"small_study_k": 10, "subgroup_k": 4})

    def check(self, results=GOOD, methods=METHODS, *argv):
        Path("results.md").write_text(results, encoding="utf-8")
        Path("methods.md").write_text(methods, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cm.main(["--text", "results.md", "methods.md", *argv])
        return code, json.loads(out.getvalue()), Path("meta-analysis/check.md").read_text()

    def test_a_good_text_passes_with_every_label_matched(self):
        self.build()
        code, summary, report = self.check()
        self.assertEqual(code, 0, summary["problems"])
        self.assertEqual(summary["text"], {"matched": 23})
        self.assertTrue(report.startswith("# Meta-analysis check\n"))
        for row in ("| results.md:3 | 6 | matched | weight.extra.meta.k = 6 |",
                    "| results.md:4 | 0.042 | matched | weight.extra.meta.tau2 = 0.042 |",
                    "| results.md:4 | 0.205 | matched | weight.extra.meta.tau = 0.205 |",
                    "| results.md:4 | 38% | matched | weight.extra.meta.I2 = 38.4 |",
                    "| results.md:5 | 8.12 | matched | weight.extra.meta.Q = 8.12 |",
                    "| results.md:5 | 0.15 | matched | weight.extra.meta.Q_p = 0.15 |",
                    "| results.md:9 | 10 | matched | record.settings.small_study_k = 10 |"):
            self.assertIn(row, report)
        for name in ("meta", "paragraphs", "small-study", "methods", "wording"):
            self.assertEqual(summary["checks"][name], "ok", name)

    def test_without_text_the_text_rules_are_not_checked(self):
        self.build()
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(cm.main([]), 0)                                  # --dir defaults to meta-analysis
        checks = json.loads(out.getvalue())["checks"]
        self.assertEqual((checks["meta"], checks["paragraphs"], checks["methods"]), ("ok", "not_checked", "not_checked"))
        with redirect_stdout(io.StringIO()) as shown:
            self.assertEqual(cm.main(["--help"]), 0)
        self.assertIn("paragraphs", shown.getvalue())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cm.main(["--dir", "nowhere"]), 2)

    def test_a_pooled_estimate_without_its_intervals_or_heterogeneity(self):
        self.build()
        code, summary, _ = self.check("The pooled mean difference was −1.55 kg (95% CI −2.27 to −0.83).\n")
        self.assertEqual((code, summary["checks"]["paragraphs"]), (1, "fail"))
        self.assertIn("results.md:1: weight is printed without both bounds of its prediction interval, a labelled τ², τ or I²",
                      " ".join(summary["problems"]))
        code, summary, _ = self.check("The pooled mean difference was −1.55 kg, with τ² = 0.042 and a 95% prediction "
                                      "interval of −2.9 to −0.2 kg.\n")
        self.assertIn("without both bounds of its interval", " ".join(summary["problems"]))

    def test_no_prediction_interval_needs_its_reason(self):
        self.build(pi=None, pi_reason="k = 2: a prediction interval needs at least 3 studies (k - 2 df)")
        text = "The pooled mean difference was −1.55 kg (95% CI −2.27 to −0.83; I² = 38%)."
        self.assertEqual(self.check(text + "\n")[1]["checks"]["paragraphs"], "fail")
        code, summary, _ = self.check(text + " No prediction interval was computed with two trials.\n")
        self.assertEqual(summary["checks"]["paragraphs"], "ok", summary["problems"])

    def test_table_rows_are_not_paragraphs(self):
        self.build()
        code, summary, report = self.check("| Outcome | MD (95% CI) |\n|---|---|\n| weight | −1.55 (−2.27 to −0.83) |\n")
        self.assertEqual(summary["checks"]["paragraphs"], "ok")
        self.assertIn("0 paragraph(s) with a pooled estimate", report)

    def test_small_study_tests_need_a_pool_that_ran_one(self):
        self.build()
        code, summary, _ = self.check(GOOD + "\nEgger's test showed no evidence of publication bias (p = 0.40).\n")
        self.assertEqual((code, summary["checks"]["small-study"]), (1, "fail"))
        for text in ("Egger's test was not run, as fewer than 10 trials were pooled.",
                     "A funnel-plot asymmetry test was planned only for pools of at least 10 trials."):
            self.assertEqual(self.check(GOOD + "\n" + text + "\n")[1]["checks"]["small-study"], "ok", text)
        self.build(k=12, small_study={"status": "run", "test": "Egger", "k": 12, "slope": 0.8, "se": 0.5, "t": 1.6,
                                      "df": 10, "p": 0.14})
        code, summary, report = self.check(GOOD.replace("k = 6", "k = 12").replace("Six", "Twelve") +
                                           "\nEgger's test gave t(10) = 1.6, p = 0.14.\n")
        self.assertEqual(summary["checks"]["small-study"], "ok")
        self.assertIn("| results.md:11 | 1.6 | matched | weight.extra.meta.small_study.t = 1.6 |", report)

    def test_methods_must_name_the_estimator_and_the_interval(self):
        self.build()
        code, summary, _ = self.check(methods="A random-effects model was used because the trials differed in dose.\n")
        self.assertEqual((code, summary["checks"]["methods"]), (1, "fail"))
        self.assertIn("no text names its τ² estimator REML", " ".join(summary["problems"]))
        self.assertIn("no text names its method Hartung-Knapp", " ".join(summary["problems"]))
        self.build(model="fixed", method="Mantel-Haenszel", tau2_method=None, tau2=None, tau=None, ci_method="Wald",
                   pi=None, pi_reason="fixed-effect model: no between-study variance, so no prediction interval")
        problems = " ".join(self.check(methods="Odds ratios were pooled with the Peto method.\n")[1]["problems"])
        self.assertIn("no text names its method Mantel-Haenszel", problems)

    def test_a_model_chosen_from_a_heterogeneity_statistic(self):
        self.build()
        for sentence in ("A random-effects model was used because I² was 38%.",
                         "If I² exceeded 50%, a random-effects model was chosen.",
                         "Given significant heterogeneity, the fixed-effect model was abandoned."):
            summary = self.check(methods=METHODS + sentence + "\n")[1]
            self.assertEqual(summary["checks"]["wording"], "fail", sentence)
        fine = "Heterogeneity was summarised as I² and τ²; a random-effects model was used because the trials differed in dose."
        self.assertEqual(self.check(methods=METHODS + fine + "\n")[1]["checks"]["wording"], "ok")

    def test_negative_heterogeneity_is_not_printed(self):
        self.build()
        code, summary, _ = self.check(GOOD + "\nThe untruncated I² = −24%.\n")
        self.assertEqual((code, summary["checks"]["wording"]), (1, "fail"))
        self.assertIn("a negative I² or τ²", " ".join(summary["problems"]))

    def test_meta_fields(self):
        self.build(small_study={"status": "run", "test": "Egger", "k": 6, "t": 1.0, "df": 4, "p": 0.4})
        self.assertIn("a small-study test was run with k = 6", " ".join(self.check()[1]["problems"]))
        self.build(pi=None, pi_reason=None, I2=-5.0)
        problems = " ".join(self.check()[1]["problems"])
        self.assertIn("no prediction interval and no reason", problems)
        self.assertIn("I2 is negative", problems)
        self.build(subgroups=[{"column": "dose", "test": {"status": "run", "Q_between": 2.0, "df": 1, "p": 0.16},
                               "groups": [{"value": "low", "k": 3}, {"value": "high", "k": 3}]}])
        self.assertIn("tested with a group under 4 studies", " ".join(self.check()[1]["problems"]))
        self.build(tau2_method=None)
        self.assertIn("lacks tau2_method", " ".join(self.check()[1]["problems"]))


if __name__ == "__main__":
    unittest.main()
