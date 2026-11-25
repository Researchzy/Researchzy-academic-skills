"""check_psychometrics.py: the measurement records, the conventions, and the claims and numbers of the text."""
from __future__ import annotations

import copy
import hashlib
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


cp = load("check_psychometrics", "check_psychometrics_under_test")

LOADINGS = {"AUT": {"aut1": 0.81, "aut2": 0.74, "aut3": 0.79, "aut4": 0.77, "aut5": 0.30},
            "MEA": {"mea1": 0.86, "mea2": 0.76, "mea3": 0.84, "mea4": 0.76},
            "ENG": {"eng1": 0.66, "eng2": 0.72, "eng3": 0.63, "eng4": 0.73}}
SAMPLE = [[1.0, 0.42, 0.35], [0.42, 1.2, 0.5], [0.35, 0.5, 0.9]]
IMPLIED = [[1.0, 0.40, 0.31], [0.40, 1.2, 0.47], [0.31, 0.47, 0.9]]
CORR = [[1, .62, .55, .50], [.62, 1, .52, .48], [.55, .52, 1, .58], [.50, .48, .58, 1]]
HU = {"name": "Hu-Bentler 1999", "rule": "CFI >= .95 and SRMR <= .08", "source": "user's PDF, p. 27",
      "date": "2026-11-18", "default": False}
CHEN = {"name": "Chen 2007", "max_cfi_drop": 0.01, "max_rmsea_rise": 0.015, "source": "user's PDF, Table 4",
        "date": "2026-11-18"}
LEVELS = [{"level": "configural", "chi2": 160.2, "df": 124, "cfi": 0.935, "rmsea": 0.063, "decision": "holds"},
          {"level": "metric", "chi2": 171.9, "df": 134, "cfi": 0.933, "rmsea": 0.061, "delta_cfi": -0.002,
           "delta_rmsea": -0.002, "decision": "holds"},
          {"level": "scalar", "chi2": 230.4, "df": 144, "cfi": 0.905, "rmsea": 0.072, "delta_cfi": -0.028,
           "delta_rmsea": 0.011, "decision": "fails"},
          {"level": "scalar", "freed": ["mea2", "eng3"], "chi2": 180.1, "df": 142, "cfi": 0.929, "rmsea": 0.062,
           "delta_cfi": -0.004, "delta_rmsea": 0.001, "decision": "holds"}]


def srmr(s, sigma):
    k = len(s)
    return math.sqrt(sum(((s[i][j] - sigma[i][j]) / math.sqrt(s[i][i] * s[j][j])) ** 2 for i in range(k)
                         for j in range(i + 1)) / (k * (k + 1) / 2))


def saved(name: str, **matrices) -> dict:
    Path(name).write_text(json.dumps(matrices), encoding="utf-8")
    return {"path": name, "sha256": hashlib.sha256(Path(name).read_bytes()).hexdigest()}


def records():
    """The extra["psy"] of each result: an alpha, an EFA, a CFA with validity, invariance in lavaan, Harman's test."""
    validity = {"omega": {}, "cr": {}, "ave": {}}
    for factor, items in LOADINGS.items():
        lam = list(items.values())
        s = sum(lam)
        validity["cr"][factor] = validity["omega"][factor] = s * s / (s * s + sum(1 - x * x for x in lam))
        validity["ave"][factor] = sum(x * x for x in lam) / len(lam)
    mean_between = (.55 + .50 + .52 + .48) / 4
    validity["htmt"] = {"matrix": {"MEA": {"ENG": mean_between / math.sqrt(.62 * .58)}},
                        "items": {"MEA": ["mea1", "mea2"], "ENG": ["eng1", "eng2"]},
                        "matrices": saved("htmt.json", items=["mea1", "mea2", "eng1", "eng2"], corr=CORR)}
    observed = [4.21, 2.03, 1.61, 1.12, 0.81, 0.7, 0.64, 0.6]
    return {
        "alpha_MEA": {"kind": "reliability", "construct": "MEA", "items": list(LOADINGS["MEA"]), "alpha": 0.8634,
                      "ci": "feldt", "low": 0.8412, "high": 0.8838, "level": 0.95, "n": 398, "k": 4},
        "efa": {"kind": "efa", "correlation": "pearson", "method": "pa", "rotation": "oblimin", "n_factors": 3, "reason": "",
                "parallel": {"observed": observed, "random_mean": [1.32, 1.24, 1.18, 1.13, 1.08, 1.04, 1.0, 0.96],
                             "random_percentile": [1.4, 1.3, 1.22, 1.17, 1.12, 1.07, 1.03, 0.99], "percentile": 95,
                             "criterion": "percentile", "n_sets": 500, "seed": 20261118, "eigen": "pca", "suggested": 3},
                "kaiser": {"eigenvalues": observed, "count": 4}},
        "cfa": {"kind": "cfa", "engine": "semopy", "estimator": "MLW", "converged": True, "df": 62, "n_free": 29,
                "identification": "marker", "ordinal": "seven-point items treated as continuous; ENG uses four "
                "categories, reported as a limitation", "loadings": copy.deepcopy(LOADINGS),
                "errors": {i: 1 - v * v for items in LOADINGS.values() for i, v in items.items()},
                "factor_corr": {"AUT": {"MEA": 0.42, "ENG": 0.39}, "MEA": {"ENG": 0.92}}, "heywood": [],
                "fit": {"chi2": 98.7549, "df": 62, "p": 0.002, "cfi": 0.931, "tli": 0.913, "rmsea": 0.061,
                        "srmr": srmr(SAMPLE, IMPLIED), "srmr_formula": "Bentler's, sample covariance with divisor n"},
                "matrices": saved("cfa.json", sample_cov=SAMPLE, implied_cov=IMPLIED), "validity": validity,
                "conventions": [HU]},
        "invariance": {"kind": "invariance", "engine": "lavaan", "group": "sector", "group_terms": ["sector", "部门"],
                       "levels": copy.deepcopy(LEVELS), "rule": dict(CHEN)},
        "cmv": {"kind": "cmv", "tests": [{"test": "harman", "share": 0.32, "items": 14, "n": 400}],
                "limits": "Harman's test cannot show that common-method variance is absent"}}


GOOD_EN = """# Results

Cronbach's α was .86 for meaning (95% CI .84 to .88). The three-factor model converged; χ²(62) = 98.75, CFI = .93,
TLI = .91, RMSEA = .061 and SRMR = .022, so CFI falls short of the Hu-Bentler 1999 convention. Standardized loadings
ranged from .30 to .86. Partial scalar invariance held across sectors after freeing the intercepts of mea2 and eng3,
and the sector means were compared with those intercepts free. Harman's first component explained 32% of the variance,
a test that cannot show the absence of common-method bias. Two-sided tests used α = .05.
"""
BAD_EN = """Internal consistency was good (α = .91). All loadings were above .70 and the model fit the data well (CFI = .97).

Common method variance was not a concern (Harman 32%).

Employees in the private sector reported higher engagement scores than those in the public sector. Scalar invariance
across sectors was supported.
"""
GOOD_ZH = """意义感的α系数为0.86（95% CI为0.84～0.88）。三因子模型收敛，χ²（62）＝98.75，CFI＝0.93，TLI＝0.91，RMSEA＝0.061，
SRMR＝0.022，CFI低于Hu-Bentler 1999约定的要求。标准化载荷在0.30到0.86之间。释放mea2和eng3的截距后部分标量等值性成立，
在此基础上比较了两个部门的均值。Harman检验中第一个成分解释了32%的方差，该检验不能说明不存在共同方法偏差。
"""
BAD_ZH = """量表的内部一致性信度良好（α系数为0.91）。所有载荷均大于0.70，模型拟合良好（CFI＝0.97）。

共同方法偏差不是问题（Harman单因子检验，32%）。

私营部门员工的投入得分高于公共部门员工。标量等值性得到支持。
"""


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("data.csv").write_text("id,mea1\n1,4\n", encoding="utf-8")
        Path("analysis.py").write_text("x = 1\n", encoding="utf-8")
        self.psy = records()

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def build(self):
        rz = load("rz_results", f"rz_results_{id(self)}_{len(os.listdir('.'))}")
        rz.OUT = "psychometrics"
        for rid, p in self.psy.items():
            rz.record(id=rid, question=f"{rid}?", family="measurement", role="primary", test=p["kind"], unit="respondent",
                      n={"respondents": 398}, estimate={"name": p["kind"], "value": 1.0, "units": "unitless"},
                      extra={"psy": p})
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["data.csv"], seed=20261118, settings={"alpha": 0.05})

    def check(self, *texts, build=True):
        if build:
            self.build()
        for name, content in texts:
            Path(name).write_text(content, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cp.main(["--text", *[name for name, _ in texts]] if texts else [])
        self.report = Path("psychometrics/check.md").read_text(encoding="utf-8") if code != 2 else ""
        return code, (json.loads(out.getvalue()) if out.getvalue() else None)

    def problems(self, summary, check):
        return " ".join(p for p in summary["problems"] if p.startswith(check + ":"))

    def test_a_complete_record_passes(self):
        code, summary = self.check()
        self.assertEqual(code, 0, summary["problems"])
        for name in ("reliability", "factors", "cfa", "validity", "invariance", "cmv", "conventions"):
            self.assertEqual(summary["checks"][name], "ok", name)
        self.assertEqual(summary["checks"]["wording"], "not_checked")
        self.assertIn("efa: parallel analysis 3, Kaiser 4, retained 3", self.report)
        self.assertIn("AVE of MEA (0.65) is below the squared MEA-ENG correlation (0.85)", self.report)
        self.assertIn("configural holds, metric holds, scalar fails, scalar (partial) holds", self.report)

    def test_parallel_analysis_against_kaiser_is_a_recorded_decision(self):
        self.psy["efa"]["n_factors"] = 4
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["factors"]), (1, "fail"))
        self.assertIn("4 factors retained, parallel analysis suggests 3: record the reason", self.problems(summary, "factors"))
        self.psy["efa"]["reason"] = "the user's theory names four facets; the fourth is reported as tentative"
        self.assertEqual(self.check()[1]["checks"]["factors"], "ok")
        self.psy["efa"].update(n_factors=3, reason="")
        self.psy["efa"]["parallel"]["suggested"] = 4
        self.psy["efa"]["kaiser"]["count"] = 3
        problems = self.problems(self.check()[1], "factors")
        self.assertIn("parallel analysis suggests 4, its eigenvalues give 3", problems)
        self.assertIn("Kaiser's rule gives 4 from the recorded eigenvalues, recorded 3", problems)
        del self.psy["efa"]["parallel"]["seed"]
        self.assertIn("not recorded: parallel.seed", self.problems(self.check()[1], "factors"))

    def test_a_cfa_without_convergence_or_with_a_heywood_case_fails(self):
        cfa = self.psy["cfa"]
        del cfa["converged"]
        cfa["loadings"]["ENG"]["eng2"] = 1.04
        cfa["errors"]["mea3"] = -0.02
        del cfa["ordinal"]
        cfa["loadings"]["AUT"] = {"aut1": 0.8, "aut2": 0.7}
        code, summary = self.check()
        self.assertEqual(code, 1)
        problems = self.problems(summary, "cfa")
        for expected in ("cfa: no record that the model converged", "the standardized loading of eng2 on ENG is 1.040",
                         "negative error variance of mea3", "cfa: ordinal is not recorded",
                         "AUT has 2 indicator(s): use three or more"):
            self.assertIn(expected, problems)
        self.psy = records()
        self.psy["cfa"]["df"] = 0
        self.psy["cfa"]["fit"].pop("srmr")
        problems = self.problems(self.check()[1], "cfa")
        self.assertIn("df must be a whole number above 0", problems)
        self.assertIn("no SRMR and no reason for none", problems)

    def test_srmr_and_validity_are_recomputed(self):
        self.psy["cfa"]["fit"]["srmr"] = 0.08
        self.psy["cfa"]["validity"]["cr"]["AUT"] = 0.91
        self.psy["cfa"]["validity"]["htmt"]["matrix"]["MEA"]["ENG"] = 0.70
        code, summary = self.check()
        self.assertEqual(code, 1)
        self.assertIn("SRMR is 0.0800, the saved matrices give 0.0", self.problems(summary, "cfa"))
        self.assertIn("cr of AUT is 0.9100, its loadings give 0.8237", self.problems(summary, "validity"))
        self.assertIn("HTMT MEA-ENG is 0.7000, the saved correlations give 0.8546", self.problems(summary, "validity"))
        self.psy = records()
        self.build()
        Path("cfa.json").write_text(json.dumps({"sample_cov": SAMPLE, "implied_cov": SAMPLE}), encoding="utf-8")
        summary = self.check(build=False)[1]
        self.assertIn("cfa.json changed after the run", self.problems(summary, "cfa"))

    def test_invariance_levels_deltas_and_engine(self):
        levels = self.psy["invariance"]["levels"]
        levels[1]["delta_cfi"] = -0.02
        levels[2]["decision"] = "holds"
        del self.psy["invariance"]["rule"]["source"]
        problems = self.problems(self.check()[1], "invariance")
        self.assertIn("metric: delta_cfi is -0.02, against configural it is -0.0020", problems)
        self.assertIn("scalar is recorded as holds; the rule Chen 2007 gives fails", problems)
        self.assertIn("the invariance rule needs its name, source and date", problems)
        self.psy = records()
        self.psy["invariance"]["levels"] = [LEVELS[0], dict(LEVELS[1], decision="fails"), LEVELS[2]]
        self.assertIn("scalar was tested after metric failed", self.problems(self.check()[1], "invariance"))
        self.psy["invariance"].update(engine="semopy", levels=[LEVELS[0], LEVELS[1]])
        self.assertIn("metric invariance needs lavaan's constrained model", self.problems(self.check()[1], "invariance"))
        self.psy["invariance"]["levels"] = [LEVELS[0], {"level": "metric", "decision": "not_checked", "reason": "no R"},
                                            {"level": "scalar", "decision": "not_checked"}]
        self.assertIn("scalar is not_checked without its reason", self.problems(self.check()[1], "invariance"))

    def test_a_text_written_from_the_record_passes(self):
        code, summary = self.check(("results.md", GOOD_EN), ("results-zh.md", GOOD_ZH))
        self.assertEqual(code, 0, summary["problems"])
        for name in ("wording", "group_means", "cmv_claims", "invariance_claims", "loadings_claims"):
            self.assertEqual(summary["checks"][name], "ok", name)
        self.assertEqual(summary["text"].get("mismatch", 0), 0)
        self.assertIn("| results.md:7 | .05 | matched | record.settings.alpha = 0.05 |", self.report)
        self.assertIn("| results-zh.md:1 | 0.86 | matched | alpha_MEA.extra.psy.alpha = 0.8634 |", self.report)

    def test_the_planted_problems_of_a_draft(self):
        for name, text in (("draft.md", BAD_EN), ("draft-zh.md", BAD_ZH)):
            code, summary = self.check((name, text))
            self.assertEqual(code, 1)
            for check in ("wording", "group_means", "cmv_claims", "invariance_claims", "loadings_claims"):
                self.assertEqual(summary["checks"][check], "fail", f"{name} {check}")
            self.assertIn("name the freed parameters (mea2, eng3)", self.problems(summary, "group_means"))
            self.assertIn("held only partially: say partial", self.problems(summary, "invariance_claims"))
            self.assertIn("on Harman's test alone", self.problems(summary, "cmv_claims"))
            self.assertIn("but the loading of aut5 on AUT is 0.30", self.problems(summary, "loadings_claims"))
            self.assertEqual(len(summary["problems"]) - sum(1 for p in summary["problems"] if p.startswith("text:")), 6)
            self.assertIn("mismatch (nearest: alpha_MEA.extra.psy.alpha = 0.8634)", self.problems(summary, "text"))
            self.assertRegex(self.problems(summary, "text"), r"prints 0?\.97: mismatch \(nearest: [^)]*cfi = ")

    def test_group_means_without_scalar_invariance_in_lavaan(self):
        self.psy["invariance"].update(engine="semopy", levels=[
            LEVELS[0], {"level": "metric", "decision": "not_checked", "reason": "lavaan is not installed"},
            {"level": "scalar", "decision": "not_checked", "reason": "lavaan is not installed"}])
        text = ("The two sectors did not differ in mean engagement.\n\n两个部门的投入均值差异不显著。\n\n"
                "Sector means were not compared, because scalar invariance could not be tested.\n")
        summary = self.check(("results.md", text))[1]
        problems = self.problems(summary, "group_means")
        self.assertIn("results.md:1: compares groups, but scalar invariance did not hold in lavaan", problems)
        self.assertIn("results.md:3: compares groups", problems)
        self.assertNotIn("results.md:5", problems)

    def test_common_method_claims(self):
        text = ("Common-method bias was not a concern (Harman 32%).\n\nThere was no common method bias.\n\n"
                "The marker adjustment changed no correlation by more than .02, so common-method variance is unlikely "
                "to explain them.\n")
        problems = self.problems(self.check(("cmv.md", text))[1], "cmv_claims")
        self.assertIn("cmv.md:1: claims common-method bias is absent on Harman's test alone", problems)
        self.assertIn("cmv.md:3: states that there is no common-method bias", problems)
        self.assertIn("cmv.md:5", problems)                           # only Harman's test is recorded
        self.psy["cmv"]["tests"].append({"test": "marker", "marker": "mk1", "r_m": 0.04, "max_change": 0.02})
        problems = self.problems(self.check(("cmv.md", text))[1], "cmv_claims")
        self.assertIn("cmv.md:1", problems)                           # still cites Harman alone
        self.assertNotIn("cmv.md:5", problems)

    def test_judgements_without_any_recorded_convention(self):
        self.psy["cfa"]["conventions"] = []
        summary = self.check(("results.md", "Fit was acceptable by Hu-Bentler 1999 (CFI = .93).\n"))[1]
        self.assertEqual(summary["checks"]["conventions"], "not_checked")
        self.assertIn("'Fit was acceptable' names no recorded convention", self.problems(summary, "wording"))
        self.psy["cfa"]["conventions"] = [dict(HU, source="")]
        self.assertIn("lacks source", self.problems(self.check()[1], "conventions"))

    def test_unreadable_results_exit_2(self):
        self.assertEqual(self.check(build=False)[0], 2)


if __name__ == "__main__":
    unittest.main()
