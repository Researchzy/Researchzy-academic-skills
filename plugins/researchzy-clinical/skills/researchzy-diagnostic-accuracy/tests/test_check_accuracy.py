"""check_accuracy.py on the DA-1 task: the record rules (intervals, clustering, calibration, predictive values, cut-off
sources, optimism, leakage), the text rules in English and Chinese, the number labels, and the lint of the user's
model.py. Results are written through rz_accuracy.record() from result dicts shaped like its functions' output, so
the tests need only the standard library."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).parent))
import da1_fixture  # noqa: E402


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ca = load("check_accuracy", "check_accuracy_under_test")
probe = load("probe_accuracy", "probe_for_check")

SEED = 20261118
AUC = {"kind": "auc", "level": 0.95, "units": 140, "patients": 120, "positives": 40,
       "method": "bootstrap by patient, percentile", "B": 2000, "B_used": 2000, "seed": SEED}
BIOMARKER = {**AUC, "value": 0.861, "low": 0.812, "high": 0.907}
SCORE = {**AUC, "value": 0.742, "low": 0.663, "high": 0.818}
MODEL_TEST = {**AUC, "value": 0.834, "low": 0.771, "high": 0.889}
DIFFERENCE = {**AUC, "kind": "auc_difference", "value": 0.119, "low": 0.041, "high": 0.198, "auc_a": 0.861,
              "auc_b": 0.742, "method": "bootstrap by patient, paired, percentile"}
CALIBRATION = {"kind": "calibration", "level": 0.95, "units": 140, "patients": 120, "positives": 40,
               "intercept": {"value": -0.12, "low": -0.48, "high": 0.24, "level": 0.95},
               "slope": {"value": 0.84, "low": 0.61, "high": 1.07, "level": 0.95}, "brier": 0.118,
               "mean_predicted": 0.30, "observed_rate": 0.286, "method": "intercept: logistic model with logit(p) as "
               "offset; slope: logistic regression on logit(p); Wald intervals, cluster-robust by patient",
               "curve_method": "lowess, frac 0.667, no robustness iterations"}
DEVELOPMENT = {**AUC, "units": 335, "patients": 239, "positives": 47, "value": 0.912, "low": 0.881, "high": 0.941}
OPTIMISM = {"kind": "optimism", "value": 0.873, "units": 335, "patients": 239, "positives": 47, "B": 200, "B_used": 200,
            "failures": 0, "seed": SEED, "resampled": "patients",
            "metrics": {"auc": {"apparent": 0.912, "optimism": 0.039, "corrected": 0.873},
                        "slope": {"apparent": 1.0, "optimism": 0.12, "corrected": 0.88}}}
NULL = {"kind": "null_label", "value": 0.497, "against_true_labels": 0.502, "range": [0.43, 0.56], "margin": 0.031,
        "status": "ok", "reason": "both means within the margin", "R": 10, "R_used": 10, "folds": 5, "seed": SEED,
        "units": 335, "patients": 239, "positives": 47}


def table(tp=37, fp=12, fn=3, tn=88, design="consecutive", ppv=True):
    measures = {"sensitivity": {"value": 0.925, "low": 0.7961, "high": 0.9843, "numerator": 37, "denominator": 40,
                                "method": "Clopper-Pearson", "level": 0.95},
                "specificity": {"value": 0.88, "low": 0.7998, "high": 0.9364, "numerator": 88, "denominator": 100,
                                "method": "Clopper-Pearson", "level": 0.95}}
    if ppv:
        measures["ppv"] = {"value": 0.7551, "low": 0.6113, "high": 0.8666, "numerator": 37, "denominator": 49,
                           "method": "Clopper-Pearson", "level": 0.95}
    else:
        measures["ppv"] = {"value": None, "reason": f"design {design}: predictive values need a stated prevalence"}
    return {"kind": "two_by_two", "design": design, "cells": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}, "level": 0.95,
            "measures": measures, "sample_prevalence": 40 / 140, "prevalence": None, "units": 140, "patients": 120,
            "positives": 40}


ANALYSIS = '''"""DA-1 analysis: every data-driven step inside the pipeline."""
import sys
sys.path.insert(0, "skill/scripts")
import rz_results as rz
import rz_accuracy as ra
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

rz.OUT, SEED, DATA = "diagnostic-accuracy", 20261118, "nodules.csv"


def pipeline(X, y):
    model = make_pipeline(StandardScaler(), LogisticRegression()).fit(X, y)
    return lambda new: model.predict_proba(new)[:, 1]


ra.record(ra.optimism(pipeline, X, y, groups=g, seed=SEED), id="opt", question="q", model="model", dataset="development")
rz.finish(script=__file__, data=[DATA], seed=SEED)
'''

GOOD = """# Results

Of 640 nodules, 23 of 163 test-set nodules with a negative biomarker result had no biopsy (partial verification, 14.1%);
they are counted, not imputed.

In the test set (140 nodules from 120 patients; 40 malignant), the biomarker had an AUC of 0.861 (95% CI 0.812 to
0.907). At the planned cut-off of 2.5, sensitivity was 92.5% (37/40; 95% CI 79.6 to 98.4%) and specificity was 88.0%
(88/100; 95% CI 80.0% to 93.6%); the PPV was 75.5% (37/49; 95% CI 61.1% to 86.7%).

The biomarker's AUC (0.861) exceeded that of the clinical score (0.742, 95% CI 0.663 to 0.818): the paired difference
was 0.119 (95% CI 0.041 to 0.198).

The model's AUC in the development data was 0.912 (95% CI 0.881 to 0.941); corrected for optimism by 200 bootstrap
resamples of patients, it was 0.873. In the test set its AUC was 0.834 (95% CI 0.771 to 0.889), with a calibration
intercept of -0.12 (95% CI -0.48 to 0.24) and a calibration slope of 0.84 (95% CI 0.61 to 1.07).
"""
METHODS = """Intervals for proportions are exact (Clopper–Pearson). Because some patients contributed two nodules, AUC
intervals come from a bootstrap by patient (2000 resamples, seed 20261118).
"""
DRAFT = """# Results

Using the optimal cut-off of 2.31 chosen by the Youden index in the test set, sensitivity was 92.5% (37/40; 95% CI
84.3% to 100.7%).

The model achieved an AUC of 0.912 (95% CI 0.881 to 0.941) in the development set.

The AUC of the biomarker (0.861, 95% CI 0.812 to 0.907) was higher than that of the clinical score (0.742, 95% CI 0.663
to 0.818), and the confidence intervals did not overlap.

In the test set, the model's AUC was 0.834.
"""
GOOD_ZH = """# 结果

测试集中，生物标志物阴性的163个结节有23个未接受活检（部分验证，14.1%）。

测试集共140个结节（120名患者，40个恶性）。生物标志物的AUC为0.861（95% CI 0.812～0.907）。按计划的截断值2.5，灵敏度为92.5%
（37/40；95% CI 79.6%～98.4%），特异度为88.0%（88/100；95% CI 80.0%～93.6%）。

生物标志物与临床评分的AUC配对差值为0.119（95% CI 0.041～0.198）。

模型在开发集的AUC为0.912（95% CI 0.881～0.941），经200次按患者的自助重抽样校正乐观度后为0.873。测试集中模型的AUC为0.834
（95% CI 0.771～0.889），校准截距为-0.12（95% CI -0.48～0.24），校准斜率为0.84（95% CI 0.61～1.07）。
"""
METHODS_ZH = "比例的置信区间采用精确法（Clopper–Pearson）；AUC的置信区间采用按患者的自助法（bootstrap，2000次）。\n"
DRAFT_ZH = """# 结果

采用测试集ROC曲线约登指数确定的最佳截断值2.31，灵敏度为92.5%（37/40，95% CI 84.3%～100.7%）。

生物标志物的AUC（0.861，95% CI 0.812～0.907）高于临床评分（0.742，95% CI 0.663～0.818），两者的置信区间不重叠。
"""


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        rows = da1_fixture.rows()
        moved = {r["patient_id"] for r in rows if r["split"] == "test"} & {r["patient_id"] for r in rows
                                                                          if r["split"] == "development"}
        for r in rows:                 # the user's fix after the probe: a crossing patient's nodules all go to development
            if r["patient_id"] in moved:
                r["split"] = "development"
        da1_fixture.write(Path("."), table=rows)
        da1_fixture.write(Path("."), name="as_received.csv")
        Path("analysis.py").write_text(ANALYSIS, encoding="utf-8")
        Path("model.py").write_text(da1_fixture.MODEL_PY, encoding="utf-8")
        common = ["--id", "patient_id", "--unit", "nodule_id", "--reference", "biopsy", "--positive", "1", "--index",
                  "biomarker", "--threshold", "2.5", "--split", "split", "--development", "development", "--test", "test",
                  "--design", "consecutive"]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(probe.main(["nodules.csv", *common]), 0)
            self.assertEqual(probe.main(["as_received.csv", *common]), 1)
        self.probe = "diagnostic-accuracy/nodules.probe.json"

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def rz(self):
        rz = load("rz_results", "rz_results")
        rz.OUT = "diagnostic-accuracy"
        sys.modules["rz_results"] = rz
        return rz, load("rz_accuracy", "rz_accuracy_for_check")

    def build(self, *, skip=(), changes=None, extra=None):
        """The DA-1 results as they should be; skip leaves records out, changes alters result dicts by name."""
        rz, ra = self.rz()
        changes = changes or {}
        records = [("biomarker", BIOMARKER, dict(model="biomarker", dataset="test", probe=self.probe,
                                                 no_calibration="a biomarker value, not a predicted risk")),
                   ("score", SCORE, dict(model="clinical score", dataset="test", probe=self.probe,
                                         no_calibration="a points score, not a predicted risk")),
                   ("difference", DIFFERENCE, dict(models=("biomarker", "clinical score"), dataset="test", probe=self.probe)),
                   ("table", table(), dict(model="biomarker", dataset="test", probe=self.probe,
                                           threshold={"value": 2.5, "source": "plan"})),
                   ("model_test", MODEL_TEST, dict(model="model", dataset="test", probe=self.probe)),
                   ("calibration", CALIBRATION, dict(model="model", dataset="test", probe=self.probe)),
                   ("model_development", DEVELOPMENT, dict(model="model", dataset="development",
                                                           no_calibration="calibration in the development data is 1 by fit")),
                   ("optimism", OPTIMISM, dict(model="model", dataset="internal_validation")),
                   ("null", NULL, dict(model="model", dataset="development"))]
        for name, result, fields in records:
            if name in skip:
                continue
            result = copy.deepcopy(result)
            result.update(changes.get(name, {}))
            ra.record(result, id=name, question="How accurate is it?", design="consecutive", **fields)
        for entry in extra or ():
            rz.record(**entry)
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["nodules.csv"], seed=SEED)

    def check(self, *argv, text=None, methods=None, probe_path=None):
        args = ["--probe", probe_path or self.probe, *argv]
        if text is not None:
            Path("results.md").write_text(text, encoding="utf-8")
            Path("methods.md").write_text(methods or "", encoding="utf-8")
            args += ["--text", "results.md", "methods.md"]
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = ca.main(args)
        return code, json.loads(out.getvalue())

    def problems(self, summary, name):
        return " ".join(p for p in summary["problems"] if p.startswith(name))

    def test_a_complete_analysis_and_its_text_pass_in_english_and_chinese(self):
        self.build()
        for text, methods in ((GOOD, METHODS), (GOOD_ZH, METHODS_ZH)):
            code, summary = self.check("--script", "analysis.py", text=text, methods=methods)
            self.assertEqual(code, 0, summary["problems"])
            self.assertEqual(summary["text"].get("mismatch", 0), 0)
            for name in ("fields", "intervals", "calibration", "predictive", "thresholds", "internal", "leakage",
                         "paragraphs", "apparent", "comparison", "cutoff_text", "verification", "methods", "script"):
                self.assertEqual(summary["checks"][name], "ok", f"{name}: {summary['problems']}")
            self.assertEqual(summary["checks"]["lint"], "ok")          # every fit sits inside the pipeline function
        report = Path("diagnostic-accuracy/check.md").read_text(encoding="utf-8")
        self.assertTrue(report.startswith("# Diagnostic accuracy check\n"))
        self.assertRegex(report, r"\| results\.md:\d+ \| 92\.5% \| matched \| table\.sensitivity\.estimate")   # 灵敏度为92.5%

    def test_the_draft_of_da1_fails_on_each_planted_problem(self):
        self.build()
        code, summary = self.check(text=DRAFT, methods=METHODS)
        self.assertEqual(code, 1)
        report = Path("diagnostic-accuracy/check.md").read_text(encoding="utf-8")
        for printed in ("84.3%", "100.7%", "2.31"):                     # a Wald interval above 1; a test-set cut-off
            self.assertRegex(report, rf"\| results\.md:\d+ \| {printed} \| mismatch \|")
        self.assertIn("a cut-off chosen on the test data", self.problems(summary, "cutoff_text"))
        self.assertIn("without its optimism-corrected value 0.873", self.problems(summary, "apparent"))
        comparison = self.problems(summary, "comparison")
        self.assertIn("without their paired difference: print difference with its interval", comparison)
        self.assertIn("overlapping intervals are no test of a difference", comparison)
        self.assertIn("model_test is printed without both bounds", self.problems(summary, "paragraphs"))
        self.assertIn("25 row(s) have no reference standard", self.problems(summary, "verification"))
        code, summary = self.check(text=GOOD, methods="AUC intervals come from DeLong's method.\n")
        methods = self.problems(summary, "methods")                    # results.md names the bootstrap, nothing names the
        self.assertIn("Clopper-Pearson, the interval method of table.sensitivity and 2 more", methods)   # exact interval
        self.assertNotIn("bootstrap", methods)

    def test_the_chinese_draft_fails_too(self):
        self.build()
        code, summary = self.check(text=DRAFT_ZH, methods=METHODS_ZH)
        self.assertEqual(code, 1)
        report = Path("diagnostic-accuracy/check.md").read_text(encoding="utf-8")
        for printed in ("84.3%", "100.7%", "2.31"):
            self.assertRegex(report, rf"\| results\.md:\d+ \| {printed} \| mismatch \|")
        self.assertEqual(summary["checks"]["cutoff_text"], "fail")
        self.assertIn("overlapping intervals", self.problems(summary, "comparison"))
        self.assertEqual(summary["checks"]["verification"], "fail")

    def test_an_auc_without_interval_or_calibration_and_delong_on_clustered_units(self):
        self.build(changes={"model_test": {"low": None, "high": None}}, skip=("calibration",))
        code, summary = self.check()
        self.assertEqual(code, 1)
        self.assertIn("model_test: an AUC without an interval", self.problems(summary, "intervals"))
        self.assertIn("model_test: no calibration result for model on test", self.problems(summary, "calibration"))
        self.build(changes={"biomarker": {"method": "DeLong, logit scale"}})
        problems = self.problems(self.check()[1], "intervals")
        self.assertIn("140 units from 120 patients are not independent", problems)

    def test_predictive_values_need_a_cohort_or_a_sourced_prevalence(self):
        rz, ra = self.rz()
        refused = table(design="case_control", ppv=False)
        with self.assertRaisesRegex(ValueError, "predictive values need a stated prevalence"):
            ra.record(refused, id="cc", question="q", model="biomarker", dataset="external", measures=("ppv",))
        entry = {"id": "cc.ppv", "question": "q", "family": "cc", "role": "primary", "test": "PPV", "unit": "patient",
                 "n": {"patients": 240}, "estimate": {"name": "positive predictive value", "value": 0.88,
                                                      "units": "proportion"},
                 "interval": {"low": 0.80, "high": 0.93, "level": 0.95},
                 "extra": {"accuracy": {"kind": "two_by_two", "model": "biomarker", "dataset": "external",
                                        "design": "case_control", "units": 240, "patients": 240, "positives": 120,
                                        "measure": "ppv", "numerator": 106, "denominator": 120,
                                        "method": "Clopper-Pearson"}}}
        self.build(extra=[entry])
        self.assertIn("cc.ppv: a case_control sample fixes the share of positives",
                      self.problems(self.check()[1], "predictive"))
        stated = copy.deepcopy(entry)
        stated["extra"]["accuracy"]["prevalence"] = {"value": 0.12, "source": "Screening registry 2024, table 3"}
        self.build(extra=[stated])
        self.assertEqual(self.check()[1]["checks"]["predictive"], "ok")

    def test_cut_off_sources(self):
        rz, ra = self.rz()
        with self.assertRaisesRegex(ValueError, "never the test data"):
            ra.record(table(), id="t", question="q", model="biomarker", dataset="study",
                      threshold={"value": 2.31, "source": "test"})
        with self.assertRaisesRegex(ValueError, "citation"):
            ra.record(table(), id="t", question="q", model="biomarker", dataset="study",
                      threshold={"value": 2.31, "source": "published"})
        self.build(skip=("table",), extra=[{
            "id": "table.sensitivity", "question": "q", "family": "table", "role": "primary", "test": "sensitivity",
            "unit": "patient", "n": {"patients": 120, "units": 140},
            "estimate": {"name": "sensitivity", "value": 0.925, "units": "proportion"},
            "interval": {"low": 0.7961, "high": 0.9843, "level": 0.95},
            "extra": {"accuracy": {"kind": "two_by_two", "model": "biomarker", "dataset": "study", "design": "consecutive",
                                   "units": 140, "patients": 120, "positives": 40, "measure": "sensitivity",
                                   "numerator": 37, "denominator": 40, "method": "Clopper-Pearson",
                                   "threshold": {"value": 2.31, "source": "test"}}}}])
        self.assertIn("the cut-off's source is 'test'", self.problems(self.check()[1], "thresholds"))
        self.build(skip=("table",), extra=[{
            "id": "bare.sensitivity", "question": "q", "family": "bare", "role": "primary", "test": "sensitivity",
            "unit": "patient", "n": {"patients": 120}, "estimate": {"name": "sensitivity", "value": 0.925,
                                                                    "units": "proportion"},
            "interval": {"low": 0.7961, "high": 0.9843, "level": 0.95},
            "extra": {"accuracy": {"kind": "two_by_two", "model": "biomarker", "dataset": "study", "design": "consecutive",
                                   "units": 140, "patients": 120, "positives": 40, "measure": "sensitivity",
                                   "numerator": 37, "denominator": 40, "method": "Clopper-Pearson"}}}])
        self.assertIn("biomarker is a score (it has an AUC): name the cut-off", self.problems(self.check()[1], "thresholds"))

    def test_an_apparent_auc_needs_its_optimism(self):
        self.build(skip=("optimism",))
        self.assertIn("model_development: an apparent AUC of model", self.problems(self.check()[1], "internal"))
        self.build(changes={"optimism": {"seed": None}})
        self.assertIn("optimism needs the apparent, optimism and corrected AUC, B and the seed",
                      self.problems(self.check()[1], "internal"))

    def test_leakage_blocks_test_set_results(self):
        rz, ra = self.rz()
        with self.assertRaisesRegex(ValueError, "leakage status is ok"):
            ra.record(BIOMARKER, id="b", question="q", model="biomarker", dataset="test", design="consecutive",
                      probe="diagnostic-accuracy/as_received.probe.json")
        with self.assertRaisesRegex(ValueError, "leakage status is ok"):
            ra.record(BIOMARKER, id="b", question="q", model="biomarker", dataset="test", design="consecutive")
        self.build()
        code, summary = self.check(probe_path="diagnostic-accuracy/as_received.probe.json")
        self.assertEqual(code, 1)
        leakage = self.problems(summary, "leakage")
        self.assertIn("the probe is of a file this run did not read", leakage)
        self.assertIn("the probe's leakage status is problem", leakage)
        self.build(changes={"null": {"status": "problem", "reason": "risks predict the true outcome"}})
        self.assertIn("the null-label check null found a problem", self.problems(self.check()[1], "leakage"))
        self.build()
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            ca.main([])
        self.assertEqual(json.loads(out.getvalue())["checks"]["leakage"], "not_checked")

    def test_lint_leads_on_the_users_model_script(self):
        self.build()
        code, summary = self.check("--lint", "model.py")
        self.assertEqual((code, summary["checks"]["lint"]), (0, "lead"))       # a lead never fails
        report = Path("diagnostic-accuracy/check.md").read_text(encoding="utf-8")
        self.assertIn("model.py:9: StandardScaler is fitted on all rows before the split (line 12)", report)
        self.assertIn("model.py:11: SelectKBest is fitted on all rows before the split (line 12)", report)
        Path("plain.py").write_text("from sklearn.model_selection import train_test_split\n"
                                    "from sklearn.model_selection import GroupKFold\n\n"
                                    "train, test = train_test_split(df, test_size=0.3)\n"
                                    "folds = GroupKFold(5).split(X, y, groups=df.patient_id)\n", encoding="utf-8")
        self.check("--lint", "plain.py")
        report = Path("diagnostic-accuracy/check.md").read_text(encoding="utf-8")
        self.assertIn("plain.py:4: train_test_split() splits rows, not patients", report)
        self.assertNotIn("plain.py:5", report)                                     # a grouped split is no lead
        Path("broken.py").write_text("def (:\n", encoding="utf-8")
        self.assertEqual(self.check("--lint", "broken.py")[1]["checks"]["lint"], "not_checked")

    def test_results_outside_rz_accuracy_and_unreadable_inputs(self):
        self.build(extra=[{"id": "stray", "question": "q", "family": "stray", "role": "primary", "test": "t",
                           "unit": "patient", "n": 5, "estimate": {"name": "x", "value": 1.0, "units": "unitless"}}])
        self.assertIn("stray: no extra['accuracy']", self.problems(self.check()[1], "fields"))
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(ca.main(["--probe", "missing.json"]), 2)
            self.assertEqual(ca.main(["--dir", "nowhere"]), 2)
        with redirect_stdout(io.StringIO()) as shown:
            self.assertEqual(ca.main(["--help"]), 0)
        self.assertIn("cutoff_text", shown.getvalue())


if __name__ == "__main__":
    unittest.main()
