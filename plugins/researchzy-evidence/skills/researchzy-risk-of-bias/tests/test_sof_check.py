"""sof_check.py: the certainty of each outcome follows its decisions, absolute effects come from a
sourced comparator risk, and the effect matches the meta-analysis record."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sc = load("sof_check", HERE.parent / "scripts" / "sof_check.py")
fx = load("review_fixture", HERE / "review_fixture.py")

RESULTS = {"tool": "researchzy-statistics", "results": [
    {"id": "w", "estimate": {"name": "risk ratio", "value": 0.8049, "units": "unitless"},
     "interval": {"low": 0.6012, "high": 1.0511, "level": 0.95}, "n": {"studies": 3, "participants": 240}}]}

OUTCOME = {
    "id": "weight", "name": "Body weight at 12 weeks", "studies": ["alder2021", "birch2022", "cedar2023"],
    "participants": 240, "design": "randomised", "start": "high",
    "effect": {"measure": "RR", "value": 0.80, "low": 0.60, "high": 1.05, "source": "meta-analysis/results.json#w"},
    "results_id": "w",
    "comparator_risks": [{"label": "control arms", "value": 0.2, "source": "median risk in the control arms"}],
    "downgrades": {"risk_of_bias": {"decision": "serious", "reason": "self-reported weight", "studies": ["cedar2023"]},
                   "inconsistency": {"decision": "none"}, "indirectness": {"decision": "none"},
                   "imprecision": {"decision": "serious", "reason": "the interval crosses no effect", "studies": "all"},
                   "publication_bias": {"decision": "not_assessable", "reason": "three studies"}},
    "certainty": "low", "decided_by": "model"}


class SofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.base = fx.build(self.dir)                     # the fictional review: assessments for outcome "weight"
        self.results(RESULTS)

    def tearDown(self):
        self.tmp.cleanup()

    def results(self, content: dict) -> None:
        (self.dir / "results.json").write_text(json.dumps(content), encoding="utf-8")

    def sof(self, edit=None, results=True, text=None) -> tuple:
        outcome = copy.deepcopy(OUTCOME)
        if edit:
            edit(outcome)
        (self.base / "sof.json").write_text(text or json.dumps({"question": "A fictional question", "outcomes": [outcome]}),
                                            encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            code = sc.main(["--dir", str(self.base), *(["--results", str(self.dir / "results.json")] if results else [])])
        return code, {(p["check"], p["status"]): p["detail"] for p in json.loads(out.getvalue())["problems"]}

    def report(self) -> str:
        return (self.base / "sof.md").read_text(encoding="utf-8")

    def test_a_sound_outcome_gets_its_level_and_absolute_effects(self):
        self.assertEqual(self.sof(), (0, {}))
        report = self.report()
        self.assertIn("| Body weight at 12 weeks | 240 (3) | RR 0.8 (0.6 to 1.05) | 200 per 1,000 (control arms) | "
                      "160 per 1,000 (120 to 210) | 40 fewer per 1,000 (80 fewer to 10 more) | ⊕⊕◯◯ Low |", report)
        self.assertIn("| Body weight at 12 weeks | 3 | randomised | serious (−1) [1] | not serious | not serious | "
                      "serious (−1) [2] | not assessable [3] | none | ⊕⊕◯◯ Low | model | not yet |", report)
        self.assertIn("1. Body weight at 12 weeks, risk of bias (cedar2023): self-reported weight", report)
        self.assertIn("2. Body weight at 12 weeks, imprecision (alder2021, birch2022, cedar2023): the interval crosses", report)
        self.assertIn("Comparator risks: Body weight at 12 weeks, control arms 0.2: median risk in the control arms.", report)

    def test_downgrades_need_a_decision_a_reason_and_their_studies(self):
        def edit(o):
            o["downgrades"]["risk_of_bias"] = {"decision": "serious", "studies": ["zeta2020"]}
            o["downgrades"]["imprecision"] = {"decision": "very_serious", "reason": "one small trial"}
            del o["downgrades"]["indirectness"]
            o["downgrades"]["precision"] = {"decision": "none"}
            o["certainty"] = "very low"
        code, problems = self.sof(edit)
        self.assertEqual(code, 1)
        self.assertEqual(problems[("certainty", "fail")],
                         "precision is not one of the five domains; risk_of_bias: serious needs a reason; "
                         "risk_of_bias: zeta2020 is not among the outcome's studies; indirectness: no decision "
                         "(none, not_assessable, serious, very_serious); imprecision: name the studies behind the downgrade")

    def test_the_starting_level_and_rating_up(self):
        upgrade = {"large_effect": {"levels": 1, "reason": "a large and consistent effect", "decided_by": "model"}}
        cases = [
            (lambda o: o.update(upgrades=upgrade), "large_effect: only observational evidence is rated up, for "
                                                   "large_effect, dose_response, plausible_confounding"),
            (lambda o: o.update(start="low", certainty="very low"), "randomised evidence starts high"),
            (lambda o: o.update(design="observational", certainty="low"),
             "observational evidence starting high needs start_reason, confirmed by the user"),
            (lambda o: o.update(design="observational", start="low", certainty="very low", upgrades=upgrade),
             "large_effect: rating up is the user's decision: decided_by names the person"),
        ]
        for edit, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.sof(edit)[1][("certainty", "fail")], expected)

        def by_the_user(o):
            o.update(design="observational", start="low", certainty="moderate", upgrades=copy.deepcopy(upgrade))
            o["upgrades"]["large_effect"]["decided_by"] = "J. Reviewer"
            o["downgrades"] = {d: {"decision": "none"} for d in sc.DOWNGRADES}
        self.assertEqual(self.sof(by_the_user), (0, {}))

    def test_the_label_is_the_computed_level_and_no_studies_is_no_evidence(self):
        self.assertEqual(self.sof(lambda o: o.update(certainty="moderate"))[1][("certainty", "fail")],
                         "certainty says moderate; the decisions give low")

        def floor(o):
            o["downgrades"]["inconsistency"] = {"decision": "very_serious", "reason": "opposite directions",
                                                "studies": "all"}
            o["certainty"] = "very low"
        self.assertEqual(self.sof(floor), (0, {}))
        none = {"studies": [], "certainty": "very low", "effect": {}, "comparator_risks": []}
        self.assertEqual(self.sof(lambda o: o.update(none))[1],
                         {("certainty", "fail"): "no studies: the certainty is no_evidence, not a level"})
        self.assertEqual(self.sof(lambda o: o.update(none, certainty="no_evidence")), (0, {}))
        self.assertIn("| Body weight at 12 weeks | 0 | randomised | - | - | - | - | - | none | No studies |", self.report())

    def test_a_ratio_needs_a_comparator_risk_with_its_source(self):
        self.assertEqual(self.sof(lambda o: o.pop("comparator_risks"))[1][("effect", "fail")],
                         "a risk ratio or odds ratio needs comparator_risks with their sources")
        for risk in ({"value": 0.2}, {"value": 20, "source": "per 100 in the control arms"}):
            with self.subTest(risk=risk):
                self.assertEqual(self.sof(lambda o: o.update(comparator_risks=[risk]))[1][("effect", "fail")],
                                 "each comparator risk needs a value between 0 and 1 and its source")
        self.assertEqual(self.sof(lambda o: o["effect"].update(low=0.9, value=0.8))[1][("effect", "fail")],
                         "effect needs value, low and high with low <= value <= high")

    def test_odds_ratios_and_mean_differences(self):
        self.assertAlmostEqual(sc.per_1000("OR", 2.0, 0.1), 1000 * 0.2 / 1.1)
        self.assertAlmostEqual(sc.per_1000("RR", 3.0, 0.5), 1000.0)          # a risk never exceeds 1,000 per 1,000

        def odds(o):
            o["effect"].update(measure="OR", value=2.0, low=1.5, high=2.5)
            o["comparator_risks"][0]["value"] = 0.1
        self.sof(odds, results=False)
        self.assertIn("| 100 per 1,000 (control arms) | 182 per 1,000 (143 to 217) | 82 more per 1,000 (43 more to 117 more) |",
                      self.report())
        code, _ = self.sof(lambda o: o.update(effect={"measure": "MD", "value": -1.2, "low": -2.4, "high": -0.1,
                                                      "units": "kg", "source": "user's table 2"}, comparator_risks=[]),
                           results=False)
        self.assertEqual(code, 0)
        self.assertIn("| MD -1.2 (-2.4 to -0.1) kg | - | - | - |", self.report())

    def test_the_effect_is_compared_with_the_meta_analysis_record_at_its_precision(self):
        exact = json.dumps({"outcomes": [OUTCOME]}).replace('"value": 0.8,', '"value": 0.80,')
        self.assertEqual(self.sof(text=exact), (0, {}))                                   # 0.80 against 0.8049
        changed = copy.deepcopy(RESULTS)
        changed["results"][0]["estimate"]["value"] = 0.8123
        changed["results"][0]["n"] = {"studies": 4}
        self.results(changed)
        self.assertEqual(self.sof(text=exact)[1][("results", "fail")],
                         "estimate 0.80 against 0.8123 in w; studies 3 against 4 in w; participants is not in record w")
        self.results(RESULTS)
        self.assertEqual(self.sof(lambda o: o.update(results_id="v"))[1],
                         {("results", "fail"): f"no record v in {self.dir / 'results.json'}"})
        self.assertEqual(self.sof(results=False)[1], {
            ("results", "not_checked"): "the effect was not compared with a results file: pass --results"})
        self.assertEqual(self.sof(lambda o: o.pop("results_id"))[1], {
            ("results", "not_checked"): "no results_id names the record to compare with"})

    def test_the_outcome_must_have_risk_of_bias_assessments(self):
        self.assertEqual(self.sof(lambda o: o.update(id="dropout"))[1], {
            ("risk_of_bias", "fail"): "assessments.json has no result 'dropout' for alder2021, birch2022, cedar2023"})
        (self.base / "assessments.json").unlink()
        self.assertEqual(self.sof()[1], {("risk_of_bias", "not_checked"): "no assessments.json beside sof.json"})

    def test_a_missing_or_unreadable_file_stops_with_code_2(self):
        for name, content in (("sof.json", None), ("sof.json", "{not json")):
            path = self.base / name
            path.unlink(missing_ok=True)
            if content:
                path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                sc.main(["--dir", str(self.base)])
            self.assertEqual(stop.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
