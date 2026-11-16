"""check_causal.py: route, required diagnostics, clustering, IV strength, permutation floors, the failure rules,
the specification ledger, causal verbs, the script lint and robustness.md."""
from __future__ import annotations

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


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = load("check_causal", "check_causal_under_test")
ct = load("causal_tools", "causal_tools_for_check")

CLUSTER = {"level": "county", "basis": "assignment", "G": 60, "G_treated": 45}
PASSING = {"cohorts": {"status": "pass"}, "untreated_each_period": {"status": "pass"}, "event_study": {"status": "pass"},
           "sensitivity": {"status": "pass", "value": {"breakdown_M": 1.8}}}
IV_PASSING = {"first_stage": {"status": "pass"}, "reduced_form": {"status": "pass"}, "ols": {"status": "pass"},
              "first_stage_f": {"status": "pass", "value": 23.4, "statistic": {"name": "F", "value": 23.4, "df": [1, 59]}},
              "ar_set": {"status": "pass", "value": {"set": [[1.1, 4.0]], "bounded": True}}}
ANALYSIS = '''"""Analysis of the county panel."""
import sys
sys.path.insert(0, "skill/scripts")
import rz_results as rz
import causal_tools as ct
rz.OUT = "causal"
SEED = 1
DATA = "data.csv"
ct.spec(design="staggered_did", estimator="callaway_santanna", headline=True, id="att")
rz.finish(script=__file__, data=[DATA], seed=SEED)
'''


def probe(design="staggered_did", outcome="matched", headline=("callaway_santanna",), levels=None, assignment="county"):
    return {"route": {"outcome": outcome, "design": design, "headline": list(headline), "benchmark": [],
                      "why": ["3 adoption cohorts"], "next": []}, "facts": {"periods_without_untreated": []},
            "clustering": {"assignment": assignment, "cluster": "county", "levels": levels or
                           {"county": {"G": 60, "G_treated": 45, "at_or_above_assignment": True}}}}


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("data.csv").write_text("county,year,jobs\nC1,2010,1\n", encoding="utf-8")
        Path("analysis.py").write_text(ANALYSIS, encoding="utf-8")
        self.write_probe(probe())

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def write_probe(self, content):
        Path("probe.json").write_text(json.dumps(content), encoding="utf-8")

    def build(self, *, design="staggered_did", estimator="callaway_santanna", diagnostics=None, cluster=CLUSTER,
              estimand="ATT", interval=(1.8044, 2.9181), benchmark=(1.1, 2.3), dropped=(2.1, 3.7), permutation=None,
              raw=False):
        rz = load("rz_results", "rz_results")
        rz.OUT = "causal"
        sys.modules["rz_results"] = rz

        def spec(**fields):
            ct.spec(**{"question": "Did the policy change jobs?", "family": "jobs", "unit": "county", "test": "estimator",
                       "n": {"counties": 60}, "design": design, "cluster": cluster, **fields})

        spec(estimator=estimator, headline=True, estimand=estimand, permutation=permutation, id="att",
             diagnostics=PASSING if diagnostics is None else diagnostics,
             estimate={"name": "ATT", "value": 2.3612, "units": "jobs"},
             interval=None if interval is None else {"low": interval[0], "high": interval[1], "level": 0.95})
        spec(estimator="twfe", id="twfe", estimate={"name": "TWFE coefficient", "value": 1.7031, "units": "jobs"},
             interval={"low": benchmark[0], "high": benchmark[1], "level": 0.95})
        spec(estimator=estimator, id="no_2018", n={"counties": 45}, kept=False, reason="decided after the event study",
             estimate={"name": "ATT", "value": 2.9, "units": "jobs"}, interval={"low": dropped[0], "high": dropped[1],
                                                                                "level": 0.95})
        if raw:                                                           # a dropped specification without ct.spec()
            rz.record(id="raw", question="Did the policy change jobs?", family="jobs", role="secondary", test="t",
                      unit="county", n=60, kept=False, reason="tried a log outcome",
                      estimate={"name": "ATT", "value": 2.0, "units": "jobs"})
            rz.record(id="baseline_mean", question="What was the untreated mean?", family="descriptives",
                      role="secondary", test="mean", unit="county", n=15, estimate={"name": "mean", "value": 51.2,
                                                                                    "units": "jobs"})
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["data.csv"], seed=1)

    def check(self, *argv, text=None):
        if text is not None:
            Path("results.md").write_text(text, encoding="utf-8")
            argv += ("--text", "results.md")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cc.main(["--probe", "probe.json", *argv])
        return code, json.loads(out.getvalue()) if out.getvalue() else None

    def problems(self, summary, name):
        return " ".join(p for p in summary["problems"] if p.startswith(name + ":"))

    def test_a_clean_staggered_analysis_passes(self):
        self.build()
        code, summary = self.check("--script", "analysis.py")
        self.assertEqual(code, 0, summary["problems"])
        for name in ("route", "diagnostics", "clustering", "rules", "specifications", "script", "robustness"):
            self.assertEqual(summary["checks"][name], "ok", name)
        self.assertEqual(summary["checks"]["verbs"], "not_checked")
        table = Path("causal/robustness.md").read_text().splitlines()
        rows = [line for line in table if line.startswith("| ") and not line.startswith("| Specification")]
        self.assertTrue(rows[0].startswith("| att | callaway_santanna | 2.361 | 1.804 to 2.918 (95%) | counties 60 | headline"))
        self.assertIn("| counties 45 (differs from the headline) | dropped: decided after the event study |", rows[2])

    def test_a_twfe_headline_on_staggered_data_fails(self):
        self.build(estimator="twfe")
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["route"]), (1, "fail"))
        self.assertIn("twfe is not a headline for staggered_did", self.problems(summary, "route"))
        self.assertIn("weighs some comparisons negatively", self.problems(summary, "route"))

    def test_no_headline_unless_the_route_is_matched(self):
        self.write_probe(probe(outcome="not_identifiable_yet"))
        self.build()
        code, summary = self.check()
        self.assertEqual(code, 1)
        self.assertIn("route is not_identifiable_yet (3 adoption cohorts): report no headline", self.problems(summary, "route"))
        code, summary = self.check(text="Adoption caused the gains.\n")
        self.assertIn("'caused' where the probe's route is not_identifiable_yet", self.problems(summary, "verbs"))

    def test_required_diagnostics(self):
        self.build(diagnostics={k: v for k, v in PASSING.items() if k != "sensitivity"})
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["diagnostics"]), (1, "fail"))
        self.assertIn("the required diagnostic sensitivity is not recorded", self.problems(summary, "diagnostics"))
        self.build(diagnostics={**PASSING, "sensitivity": {"status": "not_checked", "reason": "two pre-periods only"}})
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["diagnostics"]), (0, "not_checked"))
        self.assertIn("sensitivity not_checked (two pre-periods only)", Path("causal/check.md").read_text())
        path = Path("causal/results.json")
        content = json.loads(path.read_text())
        content["results"][0]["extra"]["causal"]["diagnostics"]["sensitivity"].pop("reason")
        path.write_text(json.dumps(content))
        self.assertEqual(self.check()[1]["checks"]["diagnostics"], "fail")

    def test_clustering_against_the_probe(self):
        levels = {"county": {"G": 60, "G_treated": 45, "at_or_above_assignment": False},
                  "state": {"G": 20, "G_treated": 15, "at_or_above_assignment": True}}
        self.write_probe(probe(levels=levels, assignment="state"))
        self.build()
        code, summary = self.check()
        self.assertEqual(code, 1)
        self.assertIn("clustered by county, finer than the assignment level state", self.problems(summary, "clustering"))
        self.write_probe(probe())
        self.build(cluster={**CLUSTER, "G": 70})
        self.assertIn("G = 70, the probe counts 60", self.problems(self.check()[1], "clustering"))
        self.build(cluster={**CLUSTER, "G": 58})
        code, summary = self.check()
        self.assertEqual((code, summary["checks"]["clustering"]), (0, "ok"))
        self.assertIn("say in the text which clusters dropped out", Path("causal/check.md").read_text())
        self.build(cluster={**CLUSTER, "level": "district"})
        self.assertEqual(self.check()[1]["checks"]["clustering"], "not_checked")
        self.build(cluster={"level": "county", "G": 60, "G_treated": 45})
        self.assertIn("basis must be", self.problems(self.check()[1], "clustering"))

    def test_iv_strength(self):
        self.write_probe(probe(design="iv", headline=("2sls",)))
        weak = {**IV_PASSING, "first_stage_f": {"status": "fail", "value": 6.2}}
        self.build(design="iv", estimator="2sls", diagnostics={**weak, "ar_set": {"status": "not_checked", "reason": "slow"}})
        code, summary = self.check()
        self.assertIn("F = 6.2 < 10: record the Anderson-Rubin set", self.problems(summary, "iv_strength"))
        self.build(design="iv", estimator="2sls", diagnostics=weak, interval=(1.1, 4.0))
        self.assertEqual(self.check()[1]["checks"]["iv_strength"], "ok")
        self.build(design="iv", estimator="2sls", diagnostics=weak, interval=(1.5, 3.2))
        self.assertIn("must be the Anderson-Rubin set", self.problems(self.check()[1], "iv_strength"))
        self.build(design="iv", estimator="2sls", diagnostics={**weak, "first_stage_f": {"status": "fail", "value": 2.0}})
        self.assertIn("report no IV estimate", self.problems(self.check()[1], "iv_strength"))
        self.build(design="iv", estimator="2sls", diagnostics=IV_PASSING)
        code, summary = self.check(text="The first-stage F(1, 59) = 23.4 (cluster-robust).\n")
        self.assertEqual((code, summary["checks"]["iv_strength"], summary["text"]), (0, "ok", {"matched": 3}))

    def test_permutation_floors(self):
        self.build(permutation={"B": 99, "p": 0.001})
        self.assertIn("p = 0.001 is below 1/(B + 1) = 0.01", self.problems(self.check()[1], "permutation"))
        self.build(permutation={"B": 99, "p": 0.01})
        self.assertEqual(self.check()[1]["checks"]["permutation"], "ok")
        self.write_probe(probe(design="sc", headline=("synthetic_control",)))
        self.build(design="sc", estimator="synthetic_control", cluster=None,
                   diagnostics={"pre_fit": {"status": "pass"}, "placebos": {"status": "pass", "value": {"J": 9, "p": 0.05}}})
        code, summary = self.check()
        self.assertIn("placebos p = 0.05 is below 1/(J + 1) = 0.1", self.problems(summary, "permutation"))

    def test_the_specification_ledger(self):
        self.build(benchmark=(-0.2, 0.8), dropped=(-0.1, 1.5))
        code, summary = self.check()
        self.assertEqual(code, 1)
        self.assertIn("the headline is the only one of 3 specifications", self.problems(summary, "specifications"))
        code, summary = self.check(text="Only the headline, one of 3 specifications, excludes zero.\n")
        self.assertEqual(summary["checks"]["specifications"], "ok")
        self.assertEqual(summary["text"], {"matched": 1})              # the count is a known number
        self.build(raw=True)
        problems = self.problems(self.check()[1], "specifications")
        self.assertIn("raw: dropped without the causal fields", problems)
        self.assertNotIn("baseline_mean", problems)                      # a kept descriptive result needs no causal fields

    def test_causal_verbs(self):
        failed = {**PASSING, "event_study": {"status": "fail", "cohorts": [2018]}}
        self.build(diagnostics=failed)
        text = ("The policy raised employment by 2.36 jobs (95% CI 1.80 to 2.92).\n\n"
                "The 2018 cohort fails the pre-trend test.\n")
        code, summary = self.check(text=text)
        self.assertEqual((code, summary["checks"]["verbs"], summary["checks"]["rules"]), (1, "fail", "ok"))
        self.assertIn("results.md:1: 'raised' where required diagnostics not passed: event_study",
                      self.problems(summary, "verbs"))
        self.build()
        code, summary = self.check(text=text.replace("fails", "passes") + "\nTWFE says it increased jobs by 1.70.\n")
        self.assertEqual(self.problems(summary, "verbs").count("results.md"), 1)
        self.assertIn("twfe is not a headline estimator", self.problems(summary, "verbs"))
        code, summary = self.check(text="The estimate was 2.36 jobs (95% CI 1.80 to 2.92).\n")
        self.assertEqual((code, summary["checks"]["verbs"]), (0, "ok"))

    def test_fragile_wording_and_named_cohorts(self):
        self.build(diagnostics={**PASSING, "sensitivity": {"status": "pass", "value": {"breakdown_M": 0.6}}})
        self.assertEqual(self.check()[1]["checks"]["rules"], "not_checked")
        code, summary = self.check(text="The estimate was 2.36 jobs (95% CI 1.80 to 2.92).\n")
        self.assertIn("breakdown M = 0.6 < 1: say in the text that the result is fragile", self.problems(summary, "rules"))
        code, summary = self.check(text="The estimate was 2.36 jobs (95% CI 1.80 to 2.92); the result is fragile.\n")
        self.assertEqual(summary["checks"]["rules"], "ok")
        self.build(diagnostics={**PASSING, "event_study": {"status": "fail", "value": {"cohorts": [2018.0]}}})
        code, summary = self.check(text="The estimate was 2.36 jobs (95% CI 1.80 to 2.92).\n")
        self.assertIn("event_study failed for cohort 2018: name it", self.problems(summary, "rules"))

    def test_failure_rules_of_other_designs(self):
        self.write_probe(probe(design="rd", headline=("rdrobust",)))
        rd = {"density": {"status": "fail"}, "covariate_balance": {"status": "pass"}, "bandwidths": {"status": "pass"},
              "placebo_cutoffs": {"status": "pass"}}
        self.build(design="rd", estimator="rdrobust", diagnostics=rd)
        self.assertIn("the density test rejected", self.problems(self.check()[1], "rules"))
        self.write_probe(probe(design="weighting", headline=("ipw", "aipw")))
        weighting = {"overlap": {"status": "pass"}, "balance": {"status": "pass"}, "max_weight": {"status": "pass"},
                     "trimming": {"status": "pass", "value": {"method": "clip", "trimmed_share": 0.0}}}
        self.build(design="weighting", estimator="ipw", diagnostics=weighting)
        self.assertIn("never clip scores", self.problems(self.check()[1], "rules"))
        weighting["trimming"]["value"] = {"method": "drop", "trimmed_share": 0.7}
        self.build(design="weighting", estimator="ipw", diagnostics=weighting, estimand="ATE")
        self.assertIn("70% of the units were trimmed", self.problems(self.check()[1], "rules"))
        self.build(design="weighting", estimator="ipw", diagnostics=weighting, estimand="ATT")
        self.assertEqual(self.check()[1]["checks"]["rules"], "ok")
        self.write_probe(probe(design="panel_fe", headline=("within",),
                               levels={"county": {"G": 60, "G_treated": 4, "at_or_above_assignment": True}}))
        within = {"within_variation": {"status": "pass"}}
        self.build(design="panel_fe", estimator="within", diagnostics=within, cluster={**CLUSTER, "G_treated": 4})
        self.assertIn("4 treated clusters (at most 6)", self.problems(self.check()[1], "rules"))
        self.build(design="panel_fe", estimator="within", cluster={**CLUSTER, "G_treated": 4},
                   diagnostics={**within, "randomization_inference": {"status": "pass", "B": 999, "p": 0.004}})
        self.assertEqual(self.check()[1]["checks"]["rules"], "ok")

    def test_script_lint_counts_spec_as_recording(self):
        self.build()
        Path("bare.py").write_text(ANALYSIS.replace('ct.spec(design="staggered_did", estimator="callaway_santanna", '
                                                    'headline=True, id="att")\n', ""), encoding="utf-8")
        code, summary = self.check("--script", "bare.py")
        self.assertIn("never calls rz_results.record()", self.problems(summary, "script"))
        self.assertIn("changed after the run", self.problems(summary, "script"))
        self.assertEqual(self.check("--script", "analysis.py")[1]["checks"]["script"], "ok")

    def test_unreadable_probe_exits_2(self):
        self.build()
        Path("probe.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.check()[0], 2)


if __name__ == "__main__":
    unittest.main()
