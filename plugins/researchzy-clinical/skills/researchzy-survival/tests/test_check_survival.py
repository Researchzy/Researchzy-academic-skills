"""check_survival.py: the survival fields, a PH result per Cox model, RMST within follow-up, and the text rules
(not reached, HR with its interval, methods, reversed reference) in English and Chinese, on top of check_results.py."""
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


cs = load("check_survival", "check_survival_under_test")

CONTEXT = {"time_unit": "months", "time_zero": "date of diagnosis (plan, section 2)", "subject": "patient",
           "event_mapping": {"1": 0, "2": 1}, "entry": None,
           "excluded": [{"row": 11, "reason": "negative time (user)"}, {"row": 181, "reason": "duplicate of row 8 (user)"}]}
MEDIAN = "first time below 0.5; Brookmeyer-Crowley interval on the log(-log) scale"


def km(group, n, events, median, lowest, at_risk, followup):
    return {"kind": "km", **CONTEXT, "group_column": "arm", "level": 0.95, "band": "pointwise, log(-log)",
            "times": [0, 12, 24, 36], "group": {"column": "arm", "value": group}, "n": n, "events": events,
            "censored": n - events, "median": dict(median, level=0.95, method=MEDIAN), "lowest": lowest,
            "below_half": lowest < 0.5, "at_risk": {"times": [0, 12, 24, 36], "counts": at_risk},
            "followup": {"median": followup, "longest": 58.2 if group == "surgery" else 55.0, "method": "reverse KM"},
            "labels": {"surgery": ["surgery", "surgical", "手术"], "chemoradiation": ["chemoradiation", "放化疗"]}[group]}


COX = {"kind": "cox", **CONTEXT, "ties": "efron", "missing": "listed and left out", "strata": None, "level": 0.95,
       "n": 171, "events": 37, "events_per_parameter": {"events": 37, "parameters": 2, "ratio": 18.5},
       "excluded": CONTEXT["excluded"] + [{"row": 4, "reason": "missing ecog"}],
       "parameters": [{"name": "arm[chemoradiation]", "variable": "arm", "level": "chemoradiation", "reference": "surgery",
                       "hr": 1.6102, "low": 1.0513, "high": 2.4662, "p": 0.0287, "coef": 0.4764, "se": 0.2174},
                      {"name": "age", "variable": "age", "level": None, "reference": None, "hr": 1.0213, "low": 0.9987,
                       "high": 1.0444, "p": 0.0648, "coef": 0.0211, "se": 0.0114}], "reported": "arm[chemoradiation]"}
PH = {"kind": "ph_test", **CONTEXT, "model": "cox_arm", "n": 171, "events": 37, "transform": "km",
      "transform_text": "1 - KM", "method": "Grambsch-Therneau", "global": {"statistic": 3.614, "df": 2, "p": 0.1641},
      "parameters": [{"name": "arm[chemoradiation]", "statistic": 2.871, "df": 1, "p": 0.0902},
                     {"name": "age", "statistic": 0.733, "df": 1, "p": 0.3919}], "plot": "survival/ph-cox_arm.png"}
LOGRANK = {"kind": "logrank", **CONTEXT, "group_column": "arm", "strata": None, "weights": "log-rank", "statistic": 6.418,
           "df": 1, "p": 0.0113, "groups": {"chemoradiation": {"n": 88, "events": 26}, "surgery": {"n": 90, "events": 12}}}
RMST = {"kind": "rmst", **CONTEXT, "group_column": "arm", "reference": "surgery", "tau": 36.0, "level": 0.95,
        "method": "area under the KM curve", "reported": "chemoradiation",
        "groups": {"chemoradiation": {"n": 88, "events": 26, "rmst": 25.9, "se": 1.4, "longest": 55.0},
                   "surgery": {"n": 90, "events": 12, "rmst": 30.1, "se": 1.2, "longest": 58.2}},
        "differences": {"chemoradiation": {"value": -4.2, "se": 1.85, "low": -7.83, "high": -0.57, "p": 0.0232}}}

RESULTS = """# Results

Median follow-up was 31.0 months after surgery and 29.5 months after chemoradiation (reverse Kaplan-Meier).

The median overall survival was not reached in the surgery arm and was 23.1 months (95% CI 18.0 to 30.2) in the chemoradiation arm; log-rank χ2 = 6.42, df = 1, p = 0.011. At 36 months, 31 patients were at risk after surgery.

In the Cox model (n = 171, 37 events), chemoradiation carried a higher hazard of death than surgery (HR 1.61, 95% CI 1.05 to 2.47; p = 0.029). Up to 36 months, restricted mean survival was 4.2 months shorter after chemoradiation (95% CI 0.57 to 7.83).
"""
METHODS = """Survival was estimated with the Kaplan-Meier method and compared with the log-rank test. Hazard ratios came from a
Cox model with tied event times handled by Efron's method; proportional hazards were assessed with the Grambsch-Therneau
test on scaled Schoenfeld residuals (time transform 1 - KM).
"""
RESULTS_ZH = """# 结果

手术组中位随访31.0个月。手术组的中位总生存期未达到，放化疗组为23.1个月（95% CI 18.0–30.2）；log-rank检验χ2 = 6.42，P = 0.011。Cox模型（n = 171，事件数为37）中，放化疗组相对手术组的风险比为1.61（95% CI 1.05–2.47，P = 0.029）。36个月时手术组在险人数为31。
"""
METHODS_ZH = "采用Kaplan-Meier法估计生存率；Cox模型用Efron法处理并列时间，用基于标度化Schoenfeld残差的Grambsch-Therneau检验评价比例风险假定。\n"


class CheckSurvivalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("analysis.py").write_text("print('survival')\n", encoding="utf-8")
        Path("cohort.csv").write_text("days,status\n30,1\n", encoding="utf-8")

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def build(self, cox=None, ph=PH, rmst=RMST, surgery=None, logrank=LOGRANK):
        rz = load("rz_results", "rz_results_for_check")
        rz.OUT = "survival"
        common = dict(question="Overall survival by arm", unit="patient")
        surgery = surgery or km("surgery", 90, 12, {"estimate": "not_reached", "low": "not_reached",
                                                     "high": "not_reached"}, 0.81, [90, 74, 52, 31], 31.0)
        chemo = km("chemoradiation", 88, 26, {"estimate": 23.1, "low": 18.0, "high": 30.2}, 0.31, [88, 61, 33, 17], 29.5)
        for name, s in (("surgery", surgery), ("chemoradiation", chemo)):
            reached = isinstance(s["median"]["estimate"], float)
            rz.record(id=f"km_{name}", family="km", role="secondary", test="Kaplan-Meier estimate", n={"patients": s["n"]},
                      estimate={"name": "median survival time", "value": s["median"]["estimate"], "units": "months"}
                      if reached else {"name": "lowest Kaplan-Meier estimate", "value": s["lowest"], "units": "proportion"},
                      extra={"survival": s}, **common)
        rz.record(id="logrank_arm", family="logrank", role="secondary", test="log-rank",
                  n={"surgery": 90, "chemoradiation": 88},
                  estimate={"name": "chi-square statistic", "value": logrank["statistic"], "units": "unitless"},
                  statistic={"name": "chi2", "value": logrank["statistic"]}, df=logrank["df"],
                  extra={"survival": logrank}, **common)
        cox = cox or COX
        p = cox["parameters"][0]
        rz.record(id="cox_arm", family="os", role="primary", test="Cox, Efron ties", n={"patients": 171, "events": 37},
                  estimate={"name": "hazard ratio", "value": p["hr"], "units": "ratio"},
                  interval={"low": p["low"], "high": p["high"], "level": 0.95}, statistic={"name": "z", "value": 2.19},
                  p=p["p"], effect_size="estimate", extra={"survival": cox}, **common)
        if ph:
            rz.record(id="cox_arm_ph", family="ph", role="secondary", test="Grambsch-Therneau", n={"patients": 171},
                      estimate={"name": "chi-square statistic", "value": ph["global"]["statistic"], "units": "unitless"},
                      statistic={"name": "chi2", "value": ph["global"]["statistic"]}, df=ph["global"]["df"],
                      extra={"survival": ph}, **common)
        if rmst:
            d = rmst["differences"]["chemoradiation"]
            rz.record(id="rmst_arm", family="rmst", role="secondary", test="RMST", n={"surgery": 90, "chemoradiation": 88},
                      estimate={"name": "RMST difference", "value": d["value"], "units": "months"},
                      interval={"low": d["low"], "high": d["high"], "level": 0.95}, statistic={"name": "z", "value": -2.27},
                      p=d["p"], effect_size="estimate", extra={"survival": rmst}, **common)
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["cohort.csv"])

    def check(self, results=RESULTS, methods=METHODS, *argv):
        Path("results.md").write_text(results, encoding="utf-8")
        Path("methods.md").write_text(methods, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cs.main(["--text", "results.md", "methods.md", *argv])
        return code, json.loads(out.getvalue()), Path("survival/check.md").read_text(encoding="utf-8")

    def problems(self, summary, name) -> str:
        return " ".join(p for p in summary["problems"] if p.startswith(name + ":"))

    def test_good_texts_pass_in_english_and_chinese(self):
        self.build()
        expected = {RESULTS: ("| results.md:3 | 31.0 | matched | km_surgery.extra.survival.followup.median = 31 |",
                              "| results.md:5 | 0.011 | matched | logrank_arm.extra.survival.p = 0.0113 |",
                              "| results.md:5 | 31 | matched | km_surgery.extra.survival.at_risk.counts = 31 |",
                              "| results.md:7 | 1.61 | matched | cox_arm.extra.survival.parameters.hr = 1.6102 |",
                              "| results.md:7 | 4.2 | matched | rmst_arm.extra.survival.differences.chemoradiation.value"
                              " = -4.2 |"),
                    RESULTS_ZH: ("| results.md:3 | 31.0 | matched | km_surgery.extra.survival.followup.median = 31 |",
                                 "| results.md:3 | 37 | matched | cox_arm.extra.survival.events = 37 |",
                                 "| results.md:3 | 1.61 | matched | cox_arm.extra.survival.parameters.hr = 1.6102 |",
                                 "| results.md:3 | 31 | matched | km_surgery.extra.survival.at_risk.counts = 31 |")}
        for results, methods in ((RESULTS, METHODS), (RESULTS_ZH, METHODS_ZH)):
            code, summary, report = self.check(results, methods, "--strict")
            self.assertEqual(code, 0, summary["problems"])
            self.assertEqual({k: v for k, v in summary["checks"].items() if v != "ok"}, {"script": "not_checked"})
            self.assertTrue(report.startswith("# Survival check\n"))
            for row in expected[results]:
                self.assertIn(row, report)

    def test_a_median_printed_for_a_group_that_did_not_reach_it(self):
        self.build()
        for text in ("The median overall survival was 41 months in the surgery arm and 23.1 months (95% CI 18.0 to not "
                     "reached) in the chemoradiation arm.",
                     "In the surgical arm, median survival was 41 months, compared with 23.1 months after chemoradiation.",
                     "手术组的中位生存时间为41个月，放化疗组为23.1个月（95% CI 18.0至未达到）。"):
            code, summary, _ = self.check(RESULTS + "\n" + text + "\n")
            self.assertEqual((code, summary["checks"]["not_reached"]), (1, "fail"), text)
            self.assertIn("prints a median for surgery, whose median was not reached", self.problems(summary, "not_reached"))
            self.assertIn("prints 41: mismatch", self.problems(summary, "text"))
        for text in ("Median follow-up was 31.0 months in the surgery arm.", "手术组中位随访31.0个月，中位生存期未达到。",
                     "The median was not reached after surgery and was 23.1 months after chemoradiation."):
            self.assertEqual(self.check(RESULTS + "\n" + text + "\n")[1]["checks"]["not_reached"], "ok", text)

    def test_an_hr_without_its_interval(self):
        self.build()
        for text in ("Chemoradiation had an HR of 1.61 (p = 0.029).", "放化疗组的风险比为1.61，P = 0.029。"):
            code, summary, _ = self.check(RESULTS + "\n" + text + "\n")
            self.assertEqual((code, summary["checks"]["hr_interval"]), (1, "fail"), text)
            self.assertIn("HR 1.61 is printed without its interval", self.problems(summary, "hr_interval"))
        table = "| Arm | HR (95% CI) |\n|---|---|\n| chemoradiation | 1.61 (1.05 to 2.47) |\n"
        self.assertEqual(self.check(RESULTS + "\n" + table)[1]["checks"]["hr_interval"], "ok")

    def test_an_hr_with_the_reference_group_reversed(self):
        self.build()
        for text in ("Surgery was associated with lower mortality (HR 0.62, 95% CI 0.41 to 0.95).",
                     "手术组的风险比为0.62（95% CI 0.41–0.95）。"):
            code, summary, _ = self.check(RESULTS + "\n" + text + "\n")
            self.assertEqual((code, summary["checks"]["reference"]), (1, "fail"), text)
            self.assertIn("HR 0.62 is the reciprocal of the recorded 1.61 (arm[chemoradiation], reference surgery)",
                          self.problems(summary, "reference"))
            self.assertIn("prints 0.62: mismatch", self.problems(summary, "text"))

    def test_methods_name_the_tie_method_and_the_ph_test(self):
        self.build()
        for methods in ("Hazard ratios came from a Cox proportional hazards model.\n",
                        "风险比由Cox比例风险模型估计。\n"):
            code, summary, _ = self.check(methods=methods)
            self.assertEqual((code, summary["checks"]["methods"]), (1, "fail"))
            found = self.problems(summary, "methods")
            self.assertIn("no text names the tie method (efron)", found)
            self.assertIn("no text names the test of proportional hazards", found)

    def test_every_cox_result_has_its_ph_result_and_rmst_stays_in_follow_up(self):
        self.build(ph=None)
        code, summary, _ = self.check()
        self.assertEqual((code, summary["checks"]["ph"]), (1, "fail"))
        self.assertIn("cox_arm: no proportional-hazards result names it", self.problems(summary, "ph"))
        late = copy.deepcopy(RMST)
        late["tau"] = 57.0
        self.build(rmst=late)
        summary = self.check()[1]
        self.assertEqual(summary["checks"]["rmst"], "fail")
        self.assertIn("tau 57 lies beyond the follow-up of a group (longest 55)", self.problems(summary, "rmst"))
        self.build(rmst=None)
        self.assertEqual(self.check()[1]["checks"]["rmst"], "not_checked")

    def test_the_survival_fields(self):
        breslow = copy.deepcopy(COX)
        breslow["ties"] = "breslow"
        del breslow["parameters"][0]["reference"]
        wrong = dict(LOGRANK, df=2)
        reached = km("surgery", 90, 12, {"estimate": "not_reached", "low": "not_reached", "high": 61.0}, 0.81,
                     [90, 74, 52, 31], 31.0)
        del reached["time_zero"]
        self.build(cox=breslow, logrank=wrong, surgery=reached)
        code, summary, _ = self.check()
        found = self.problems(summary, "survival")
        for part in ("cox_arm: ties is 'breslow': fit with Efron's method",
                     "cox_arm: parameter arm[chemoradiation] is a level without its reference",
                     "logrank_arm: df is 2, but 2 groups give 1", "km_surgery: lacks time_zero",
                     "km_surgery: the median is not reached but its upper bound is a number"):
            self.assertIn(part, found)
        self.assertEqual(code, 1)

    def test_labels_and_the_runs_without_text(self):
        self.build()
        code, summary, report = self.check(RESULTS + "\nThe adjusted HR = 1.70 (95% CI 1.05 to 2.47).\n")
        self.assertIn("| results.md:9 | 1.70 | mismatch | nearest: cox_arm.extra.survival.parameters.hr = 1.6102 |", report)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(cs.main([]), 0)                                   # --dir defaults to survival
        checks = json.loads(out.getvalue())["checks"]
        self.assertEqual([checks[k] for k in ("survival", "not_reached", "methods")], ["ok", "not_checked", "not_checked"])
        with redirect_stdout(io.StringIO()) as shown:
            self.assertEqual(cs.main(["--help"]), 0)
        self.assertIn("not_reached", shown.getvalue())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cs.main(["--dir", "nowhere"]), 2)


if __name__ == "__main__":
    unittest.main()
