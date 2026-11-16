"""check_results.py: completeness, families, ledger, hashes, the script lint and the numbers in the text."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import platform
import re
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


cr = load("check_results", "check_results_under_test")

GOOD_SCRIPT = '''"""Analysis of the trial."""
import sys
import numpy as np
import pandas as pd
from scipy import stats
sys.path.insert(0, "skill/scripts")
import rz_results as rz

SEED = 20261112
rng = np.random.default_rng(SEED)
DATA = "data.csv"
table = pd.read_csv(DATA)
res = stats.ttest_ind(table.a, table.b, equal_var=False)
boot = stats.bootstrap((table.a,), np.mean, rng=rng)
table.to_csv("statistics/clean.csv")
rz.record(id="x")
rz.finish(script=__file__, data=[DATA], seed=SEED)
'''

RESULTS_MD = """# Results 2

In 2024 we enrolled the participants (Figure 2, Table 1 and Section 3.2); IL-6 was measured in a 2 x 2 design.

Sleep latency was shorter on the drug than on placebo (mean 21.4 vs 30.6 min; mean difference -9.1 min, 95% CI -10.8 to -7.4; t(10) = -11.6, p < 0.001; d_z = -3.5, n = 11 pairs).

Group A differed from group B by 2.3 points (95% CI 0.6 to 4.0; p = 0.012, Holm-adjusted p = 0.036).
The same difference to two decimals is 2.31, and to three 2.312.
Group A differed from group C by 1.05 points (95% CI -0.01 to 2.11; p = 0.0471, adjusted p = 0.094).
"""

METHODS_MD = """Analyses used Python {python} with a two-sided alpha of 0.05, 10,000 bootstrap resamples and the seed 20261112.
"""


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("data.csv").write_text("subject,condition,latency\nS1,drug,20.5\n", encoding="utf-8")
        Path("analysis.py").write_text(GOOD_SCRIPT, encoding="utf-8")

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def build(self, correct=True, finish=True, drop_bc=True):
        rz = load("rz_results", "rz_results_fresh")
        rz.record(id="latency", question="Does the drug shorten latency?", family="primary", role="primary",
                  test="paired t test", unit="subject", n={"pairs": 11},
                  estimate={"name": "mean difference, drug minus placebo", "value": -9.1243, "units": "min"},
                  interval={"low": -10.8362, "high": -7.4124, "level": 0.95}, statistic={"name": "t", "value": -11.632},
                  df=10, p=4.1e-7, effect_size={"name": "d_z", "value": -3.507, "low": -5.12, "high": -1.89, "level": 0.95},
                  descriptives={"drug": {"mean": 21.43, "sd": 3.1}, "placebo": {"mean": 30.55, "sd": 3.62}})
        for test_id, est, low, high, p in (("ab", 2.3124, 0.61, 3.98, 0.012), ("ac", 1.0517, -0.012, 2.1131, 0.0471),
                                           ("bc", -1.26, -3.1, 0.58, 0.3)):
            rz.record(id=test_id, question="Which groups differ?", family="pairwise", role="secondary",
                      test="Welch t test", unit="patient", n={"A": 20, "B": 21},
                      estimate={"name": "difference in means", "value": est, "units": "points"},
                      interval={"low": low, "high": high, "level": 0.95}, statistic={"name": "t", "value": 2.0}, df=38.2,
                      p=p, effect_size={"name": "Hedges g", "value": 0.4, "low": 0.01, "high": 0.8, "level": 0.95},
                      kept=not (drop_bc and test_id == "bc"), reason="not planned for the paper" if drop_bc else None)
        if correct:
            rz.correct("pairwise", "holm")
        if finish:
            with redirect_stdout(io.StringIO()):
                rz.finish(script="analysis.py", data=["data.csv"], seed=20261112,
                          settings={"alpha": 0.05, "resamples": 10000})

    def check(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cr.main(list(argv))
        return code, (json.loads(out.getvalue()) if out.getvalue() else None)

    def edit(self, change):
        path = Path("statistics/results.json")
        content = json.loads(path.read_text())
        change(content)
        path.write_text(json.dumps(content))

    def test_a_clean_run_passes(self):
        self.build()
        code, summary = self.check("--script", "analysis.py")
        self.assertEqual(code, 0, summary["problems"])
        self.assertEqual(summary["checks"], {"complete": "ok", "families": "ok", "ledger": "ok", "hashes": "ok",
                                             "script": "ok", "text": "not_checked"})
        report = Path("statistics/check.md").read_text()
        self.assertIn("pairwise: holm over 3 tests, recomputed", report)
        self.assertIn("run 1: 3 kept, 1 dropped (bc)", report)

    def test_a_missing_field_fails(self):
        self.build()
        self.edit(lambda c: c["results"][0].pop("unit"))
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["complete"]), (1, "fail"))
        self.edit(lambda c: c["results"][0].update(unit="subject", effect_size=None))
        code, summary = self.check()
        self.assertIn("latency: a p-value without an effect size or the reason", summary["problems"][0])

    def test_a_family_without_correction_fails(self):
        self.build(correct=False)
        code, summary = self.check()
        self.assertEqual(code, 1)
        self.assertIn("family pairwise: 3 tests and no correction", " ".join(summary["problems"]))

    def test_the_number_corrected_over_must_equal_the_tests_run(self):
        self.build()
        def two(c):
            c["families"]["pairwise"].update(m=2, ids=["ab", "ac"])
            c["families"]["pairwise"]["p_adjusted"].pop("bc")
        self.edit(two)
        code, summary = self.check()
        self.assertEqual(code, 1)
        self.assertIn("corrected over 2 tests, the ledger holds 3 (ab, ac, bc)", " ".join(summary["problems"]))

    def test_adjusted_p_values_are_recomputed(self):
        self.build()
        self.edit(lambda c: c["families"]["pairwise"]["p_adjusted"].update(ab=0.024))
        code, summary = self.check()
        self.assertIn("adjusted p of ab is 0.024, holm gives 0.036", " ".join(summary["problems"]))

    def test_ledger_and_results_must_agree(self):
        self.build()
        self.edit(lambda c: c["results"].pop(1))
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["ledger"]), (1, "fail"))
        lines = Path("statistics/ledger.jsonl").read_text().splitlines()
        Path("statistics/ledger.jsonl").write_text("\n".join(l.replace('"reason": "not planned for the paper"', '"reason": null')
                                                             for l in lines) + "\n")
        code, summary = self.check()
        self.assertIn("bc: dropped without a reason", " ".join(summary["problems"]))

    def test_analyses_of_earlier_runs_are_listed(self):
        self.build()
        rz = load("rz_results", "rz_results_second_run")
        rz.record(id="latency", question="q", family="primary", role="primary", test="paired t test", unit="subject",
                  n=11, estimate={"name": "mean difference", "value": -9.1, "units": "min"})
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["data.csv"])
        code, summary = self.check()
        self.assertEqual(code, 0, summary["problems"])
        self.assertIn("in earlier runs only: ab, ac, bc", Path("statistics/check.md").read_text())

    def test_hashes(self):
        self.build()
        Path("data.csv").write_text("subject,condition,latency\nS1,drug,25.5\n", encoding="utf-8")
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["hashes"]), (1, "drift"))
        Path("data.csv").unlink()
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["hashes"]), (0, "not_checked"))

    def test_a_run_that_did_not_finish(self):
        self.build(finish=False)
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["hashes"]), (1, "fail"))

    def test_script_lint(self):
        record = {"seed": 20261112, "data": [{"path": "data.csv"}]}
        cases = {
            "rng = np.random.default_rng(SEED)": ("np.random.seed(1)\nrng = np.random.default_rng()",
                                                  ["sets a global seed", "creates a generator without a seed"]),
            "boot = stats.bootstrap((table.a,), np.mean, rng=rng)": ("boot = stats.bootstrap((table.a,), np.mean)",
                                                                     ["bootstrap() without rng="]),
            "DATA = \"data.csv\"": ("DATA = \"data.csv\"\nx = np.random.normal(size=3)", ["draws from the global random state"]),
            ", equal_var=False": ("", ["ttest_ind() without equal_var"]),
            "table = pd.read_csv(DATA)": ("table = pd.read_csv(DATA)\nvalues = [1.2, 3.4, 5.6, 7.8, 9.1, 2.3, 4.5, 6.7]",
                                          ["a literal with 8 numbers"]),
            'table.to_csv("statistics/clean.csv")': ("table.to_csv(DATA)", ["writes to data.csv, a file the analysis reads"]),
            'rz.record(id="x")': ("", ["never calls rz_results.record()"]),
        }
        for old, (new, expected) in cases.items():
            Path("bad.py").write_text(GOOD_SCRIPT.replace(old, new), encoding="utf-8")
            state, findings = cr.lint_script(Path("bad.py"), record)
            self.assertEqual(state, "fail", old)
            for text in expected:
                self.assertIn(text, " ".join(findings), old)
        self.assertEqual(cr.lint_script(Path("analysis.py"), record), ("ok", []))
        state, findings = cr.lint_script(Path("analysis.py"), {"seed": None})
        self.assertIn("finish() recorded no seed", findings[0])
        Path("broken.py").write_text("def broken(:\n", encoding="utf-8")
        self.assertEqual(cr.lint_script(Path("broken.py"), record)[0], "not_checked")

    def test_numbers_in_the_text(self):
        self.build()
        Path("results.md").write_text(RESULTS_MD, encoding="utf-8")
        Path("methods.md").write_text(METHODS_MD.format(python=platform.python_version()), encoding="utf-8")
        code, summary = self.check("--text", "results.md", "methods.md")
        self.assertEqual(code, 0, summary["problems"])
        self.assertEqual(summary["text"], {"matched": 29})
        report = Path("statistics/check.md").read_text()
        self.assertIn("Ignored by rule: 3 figure, table or section number, 1 part of a name, 2 table size, 1 year.", report)
        self.assertIn("| results.md:5 | 0.001 | matched | latency.p = 4.1e-07 |", report)
        self.assertIn("| results.md:8 | 2.312 | matched | ab.estimate.value = 2.3124 |", report)   # three roundings of one value
        self.assertIn("| methods.md:1 | 20261112 | matched | record.seed = 20261112 |", report)

    def test_wrong_numbers_and_p_equals_zero(self):
        self.build()
        Path("results.md").write_text(
            "The mean difference was -9.4 min (95% CI -10.8 to -7.4; t(10) = -11.6, p = 0.000).\n\n"
            "Group A and B differed by 2.32 points (95% CI 0.6 to 4.0; p = 0.012).\n\n"
            "Group A and C: p < 0.05, n = 20.\n\nThe mean age was 54.3 years.\n\nAnalyses used Python 2.7.1.\n",
            encoding="utf-8")
        code, summary = self.check("--text", "results.md")
        self.assertEqual(code, 1)
        report = Path("statistics/check.md").read_text()
        self.assertIn("| results.md:1 | -9.4 | mismatch | nearest: latency.estimate.value = -9.1243 |", report)
        self.assertIn("| results.md:1 | 0.000 | mismatch | nearest: latency.p = 4.1e-07 (a p-value is never zero: print p < 0.001) |", report)
        self.assertIn("| results.md:3 | 2.32 | mismatch |", report)
        self.assertIn("| results.md:5 | 0.05 | matched | ", report)
        self.assertIn("(print the exact p-value)", report)
        self.assertIn("| results.md:7 | 54.3 | not_found |", report)
        self.assertIn("| results.md:9 | python 2.7.1 | mismatch |", report.lower())
        self.assertEqual(summary["text"], {"mismatch": 4, "matched": 11, "not_found": 1})

    def test_a_flipped_sign_is_a_mismatch(self):
        self.build()
        Path("results.md").write_text(
            "Group A scored 2.31 points higher than group B (95% CI 0.61 to 3.98).\n\n"
            "The drug shortened latency by 9.12 min, t(10) = -11.63.\n\n"
            "Group A minus group C was -1.05 points.\n\n"
            "Group A minus group B was -2.31 points (95% CI -3.98 to -0.61; p = 0.012).\n",
            encoding="utf-8")
        code, summary = self.check("--text", "results.md")
        self.assertEqual(code, 1)
        report = Path("statistics/check.md").read_text()
        flipped = "(the recorded value has the opposite sign) |"
        self.assertIn(f"| results.md:5 | -1.05 | mismatch | nearest: ac.estimate.value = 1.0517 {flipped}", report)
        self.assertIn(f"| results.md:7 | -2.31 | mismatch | nearest: ab.estimate.value = 2.3124 {flipped}", report)
        self.assertIn(f"| results.md:7 | -0.61 | mismatch | nearest: ab.interval.low = 0.61 {flipped}", report)
        self.assertEqual(summary["text"], {"matched": 9, "mismatch": 4})

    def test_extend_adds_a_title_checks_numbers_and_labels(self):
        rz = load("rz_results", "rz_results_extra")
        rz.record(id="pool", question="Does the drug shorten latency?", family="primary", role="primary",
                  test="random-effects meta-analysis", unit="study", n={"studies": 6},
                  estimate={"name": "SMD", "value": -0.42, "units": "SD"},
                  interval={"low": -0.61, "high": -0.23, "level": 0.95}, extra={"tau2": 0.0, "i2": 0.0})
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["data.csv"])
        Path("results.md").write_text("The pooled SMD was -0.42 (95% CI -0.61 to -0.23; k = 6; tau^2 = 0.04; I^2 = 0%).\n",
                                      encoding="utf-8")

        def extend(content, args):
            pool = content["results"][0]
            return {"title": "Meta-analysis check", "checks": [("pooling", "ok", [], "1 pooled result")],
                    "numbers": [(6.0, "k", "pool", "n.studies"), (pool["extra"]["tau2"], "tau2", "pool", "extra.tau2")],
                    "labels": (("k", re.compile(r"\bk\s*=\s*$")), ("tau2", re.compile(r"\btau\^?2\s*=\s*$")))}

        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cr.main(["--text", "results.md"], extend=extend)
        summary = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(summary["checks"]["pooling"], "ok")
        self.assertEqual(summary["text"], {"matched": 6, "mismatch": 1})
        report = Path("statistics/check.md").read_text()
        self.assertTrue(report.startswith("# Meta-analysis check\n"))
        self.assertIn("| results.md:1 | 6 | matched | pool.n.studies = 6 |", report)
        self.assertIn("| results.md:1 | 0.04 | mismatch | nearest: pool.extra.tau2 = 0 |", report)

    def test_strict_fails_on_a_number_not_found(self):
        self.build()
        Path("results.md").write_text("The mean age was 54.3 years.\n", encoding="utf-8")
        self.assertEqual(self.check("--text", "results.md")[0], 0)
        self.assertEqual(self.check("--text", "results.md", "--strict")[0], 1)

    def test_unreadable_input_exits_2(self):
        self.assertEqual(self.check("--dir", "nowhere")[0], 2)


if __name__ == "__main__":
    unittest.main()
