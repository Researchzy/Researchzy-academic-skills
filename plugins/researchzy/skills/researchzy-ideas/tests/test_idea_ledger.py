"""idea_ledger.py: novelty belongs to one wording of an idea, and only a checked idea can be recommended."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "idea_ledger.py"
spec = importlib.util.spec_from_file_location("idea_ledger", SCRIPT)
il = importlib.util.module_from_spec(spec)
spec.loader.exec_module(il)

CARD = {
    "title": "Interleaved homework and method choice",
    "question": "Does interleaving homework problems across topics raise first-year calculus scores on problems "
                "where the student must choose the method?",
    "claim_type": "causal",
    "hypothesis": "Interleaved homework raises scores on method-choice problems more than on method-given problems.",
    "if_true": "Interleaved sections score higher on method-choice items; the gap on method-given items is near zero.",
    "if_rival": "If the gain is extra time on task, both item types improve alike and the gain shrinks at equal time.",
    "refuted_by": "No difference on method-choice items, with an interval that excludes a gain of 0.2 SD.",
    "undetermined_if": "Fewer than 80% of the interleaved sections complete the homework.",
    "data": "Two sections per condition, item-level exam scores, homework logs.",
    "first_test": "Two raters code last year's exam items as method-choice or method-given.",
    "origin": "Gap 2 of literature-review/review.md (searches s4, s9).",
}
CLOSEST = [
    {"corpusId": 11, "title": "Interleaved practice in a calculus course", "authors": ["Dana Okoro", "Li Wei"],
     "authorCount": 2, "year": 2019, "venue": "Journal of Invented Results", "readerUrl": "https://app.researchzy.com/read/c/11",
     "what_it_solved": "Interleaving raised exam scores in one course.", "overlap": "Same intervention and population.",
     "difference": "It did not separate method-choice items from method-given items.",
     "why_it_matters": "Only the split can tell method choice from time on task.", "read": "abstract"},
    {"corpusId": 12, "title": "Spacing and time on task", "authors": [{"name": "Ruiz, Ana"}], "year": 2015,
     "what_it_solved": "Equal-time comparison of spaced and massed practice.", "overlap": "The rival explanation.",
     "difference": "Spacing, not interleaving.", "why_it_matters": "Its design shows how to hold time equal.", "read": "metadata"},
]
GATES = ("data=confirmed", "ethics=plausible", "equipment=confirmed", "skills=confirmed", "time=unknown")
RATINGS = ("value=2:changes how homework is set", "difference=2:the item split is new, see Okoro 2019",
           "testability=3:the two explanations predict different item patterns", "feasibility=2:one gate unknown",
           "information_gain=2:either result rules out one explanation")


class IdeaLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "ideas"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = il.main(["--dir", str(self.dir), "--date", "2026-11-12", *argv])
        return code, json.loads(out.getvalue())

    def refused(self, *argv) -> str:
        """The one-line message of a command that stops on bad input."""
        with self.assertRaises(SystemExit) as caught, redirect_stderr(io.StringIO()):
            self.run_cli(*argv)
        return str(caught.exception)

    def write(self, name, data) -> str:
        path = Path(self.tmp.name) / name
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return str(path)

    def add(self, **changes) -> str:
        return self.run_cli("add", self.write("card.json", {**CARD, **changes}))[1]["added"][0]

    def closest(self, idea, works):
        return self.run_cli("closest", idea, self.write("closest.json", works))[1]

    def differentiate(self, idea="i1"):
        self.run_cli("search", idea, "--intent", "duplicate", "--query", '"interleaved practice" calculus', "--total", "37",
                     "--sort", "year", "--filter", "yearFrom=2023")
        self.run_cli("search", idea, "--intent", "mechanism", "--query", '"method selection" practice', "--total", "0",
                     "--sort", "citationCount")
        self.closest(idea, CLOSEST)
        return self.run_cli("novelty", idea, "--status", "differentiated")

    def pass_every_check(self, idea="i1"):
        self.differentiate(idea)
        self.closest(idea, [{"corpusId": 11, "title": CLOSEST[0]["title"], "read": "full_text", "decisive": True}])
        self.run_cli("gate", idea, *GATES)
        self.run_cli("rate", idea, *RATINGS)
        return self.run_cli("recommend", idea)

    def test_cards_come_from_a_file_or_from_flags(self):
        two = [CARD, {**CARD, "question": "Does the gain last to the next course?", "title": ""}]
        self.assertEqual(self.run_cli("add", self.write("cards.json", two))[1], {"added": ["i1", "i2"], "ideas": 2})
        code, result = self.run_cli("add", "--question", "Is the effect larger for weaker students?", "--claim-type",
                                    "associational", "--hypothesis", "The gain falls as the entry score rises.")
        self.assertEqual((code, result["added"]), (0, ["i3"]))
        ideas = json.loads((self.dir / "ideas.json").read_text(encoding="utf-8"))["ideas"]
        self.assertEqual(ideas["i2"]["title"], "Does the gain last to the next course?")
        self.assertEqual((ideas["i3"]["version"], ideas["i3"]["novelty"]["status"]), (1, "unsearched"))

        self.assertIn("A card needs: hypothesis", self.refused("add", "--question", "Q?", "--claim-type", "causal"))
        self.assertIn("Unknown card field(s): falsifier", self.refused("add", self.write("bad.json", {**CARD, "falsifier": "x"})))
        self.assertIn("claim_type is one of", self.refused("add", self.write("bad.json", {**CARD, "claim_type": "proven"})))
        self.assertIn("i1 already has this question", self.refused("add", self.write("twin.json", CARD)))
        self.assertIn("not valid JSON", self.refused("add", self.write("broken.json", "{not json")))
        self.assertIn("No idea 'i9'", self.refused("recommend", "i9"))
        # A list with one bad card adds nothing.
        self.refused("add", self.write("mixed.json", [{**CARD, "question": "A new question?"}, {"question": "No hypothesis?"}]))
        self.assertEqual(self.run_cli("status")[1]["ideas"], 3)

    def test_a_search_is_logged_for_the_current_version_and_a_failure_is_not_a_result(self):
        self.add()
        self.assertEqual(self.run_cli("search", "base", "--query", "interleaved practice", "--total", "240")[1],
                         {"search": "s1", "outcome": "ok"})
        _, logged = self.run_cli("search", "i1", "--intent", "duplicate", "--query", '"interleaved practice" calculus',
                                 "--total", "37", "--sort", "year", "--filter", "yearFrom=2023")
        self.assertEqual(logged, {"search": "s2", "outcome": "ok", "idea": "i1", "version": 1, "novelty": "inconclusive",
                                  "intents_completed": ["duplicate"]})
        _, failed = self.run_cli("search", "i1", "--intent", "skeptic", "--query", "interleaving null",
                                 "--failed", "RATE_LIMITED: try again later")
        self.assertEqual((failed["outcome"], failed["intents_completed"]), ("failed", ["duplicate"]))
        self.add(question="Does the gain last to the next course?")
        self.assertEqual(self.run_cli("search", "i2", "--intent", "duplicate", "--query", "x", "--failed", "TIMEOUT")[1]["novelty"],
                         "unsearched")   # nothing was searched
        # The user's library is not the index.
        _, library = self.run_cli("search", "i1", "--intent", "mechanism", "--query", "interleaving", "--total", "3",
                                  "--tool", "list_library_papers")
        self.assertEqual(library["intents_completed"], ["duplicate"])
        self.assertEqual(library["novelty"], "inconclusive")
        entry = json.loads((self.dir / "ideas.json").read_text(encoding="utf-8"))["searches"][1]
        self.assertEqual((entry["date"], entry["version"], entry["filters"], entry["total"]),
                         ("2026-11-12", 1, {"yearFrom": "2023"}, 37))

        self.assertIn("no cited-by search", self.refused("search", "i1", "--intent", "citation", "--query", "x", "--total", "1"))
        self.assertIn("A failed search is not zero results", self.refused("search", "i1", "--intent", "skeptic", "--query", "x"))
        self.assertIn("--total N", self.refused("search", "i1", "--intent", "skeptic", "--query", "x", "--total", "1", "--failed", "e"))
        self.assertIn("takes no --intent", self.refused("search", "base", "--intent", "duplicate", "--query", "x", "--total", "1"))
        self.assertIn("needs --intent", self.refused("search", "i1", "--query", "x", "--total", "1"))

    def test_differentiated_needs_two_intents_with_duplicate_and_a_closest_work(self):
        self.add()
        code, result = self.run_cli("novelty", "i1", "--status", "differentiated")
        self.assertEqual((code, result["novelty"], result["refused"]), (1, "unsearched", "differentiated"))
        self.assertEqual(result["missing"], ["no completed search_papers search with intent duplicate for version 1",
                                             "completed searches cover 0 intent(s) for version 1; two are needed",
                                             "no closest work is recorded for version 1"])
        self.assertEqual(self.run_cli("novelty", "i1", "--status", "inconclusive")[0], 1)   # nothing searched yet
        self.assertEqual(self.run_cli("novelty", "i1", "--status", "overlap_found")[0], 1)  # no named paper

        self.run_cli("search", "i1", "--intent", "mechanism", "--query", "a", "--total", "5")
        self.run_cli("search", "i1", "--intent", "adjacent", "--query", "b", "--total", "0")
        self.run_cli("search", "i1", "--intent", "duplicate", "--query", "c", "--failed", "TIMEOUT")
        self.assertEqual(self.closest("i1", [{"corpusId": 11, "title": "Interleaved practice in a calculus course"}]),
                         {"idea": "i1", "version": 1, "closest_works": 1, "read_in_full_text": 0, "decisive": None,
                          "incomplete": {"Interleaved practice in a calculus course": list(il.COMPARISON)}})
        code, result = self.run_cli("novelty", "i1", "--status", "differentiated")
        self.assertEqual((code, result["missing"]), (1, [
            "no completed search_papers search with intent duplicate for version 1",
            "closest work 'Interleaved practice in a calculus course' has no stated difference"]))
        self.assertEqual(self.run_cli("novelty", "i1", "--status", "inconclusive")[0], 0)

        self.run_cli("search", "i1", "--intent", "duplicate", "--query", "c", "--total", "0")   # zero results is a result
        self.closest("i1", CLOSEST)                                                             # fills the same record
        self.assertEqual(self.run_cli("novelty", "i1", "--status", "overlap_found")[0], 0)
        code, result = self.run_cli("novelty", "i1", "--status", "differentiated", "--note", "Okoro 2019 is the nearest.")
        self.assertEqual((code, result["novelty"], result["means"]),
                         (0, "differentiated", "differentiated within the searches logged"))
        self.assertEqual(result["intents_completed"], ["duplicate", "mechanism", "adjacent"])
        self.assertIn("citation", result["not_available"])
        self.assertIn("read is one of", self.refused("closest", "i1", self.write("c.json", [{"title": "T", "read": "skimmed"}])))
        self.assertIn("Only one closest work is decisive",
                      self.refused("closest", "i1", self.write("c.json", [{**w, "decisive": True} for w in CLOSEST])))

    def test_a_changed_hypothesis_is_a_new_version_and_its_novelty_starts_again(self):
        self.add()
        self.assertEqual(self.pass_every_check()[1]["recommended"], True)
        _, same_version = self.run_cli("revise", "i1", "--data", "Three sections per condition.", "--hypothesis",
                                       CARD["hypothesis"].upper())
        self.assertEqual((same_version["new_version"], same_version["version"], same_version["novelty"]),
                         (False, 1, "differentiated"))
        self.assertEqual(self.run_cli("status")[1]["recommended"], ["i1"])

        _, revised = self.run_cli("revise", "i1", "--hypothesis", "The gain appears only when topics share a surface form.",
                                  "--note", "After the second attack.")
        self.assertEqual((revised["new_version"], revised["version"], revised["novelty"]), (True, 2, "unsearched"))
        self.assertIn("Run the novelty check again for version 2", revised["search_again"])
        _, status = self.run_cli("status")
        now = status["detail"][0]
        self.assertEqual((status["recommended"], status["open"], now["state"]), ([], ["i1"], "open"))
        self.assertEqual((now["intents_completed"], now["closest_works"], now["read_in_full_text"]), ([], 0, 0))
        self.assertEqual(now["ratings"], {"value": 2, "difference": None, "testability": 3, "feasibility": 2, "information_gain": 2})
        self.assertEqual(now["missing_for_recommendation"], ["novelty is unsearched for version 2, not differentiated",
                                                             "no closest work is marked decisive and read in full text",
                                                             "not rated: difference"])
        # The searches and closest works of version 1 do not carry over.
        self.assertEqual(self.run_cli("novelty", "i1", "--status", "differentiated")[0], 1)
        self.assertIn("Run the novelty check for version 2", self.refused("rate", "i1", "difference=2:as before"))
        self.assertEqual(self.run_cli("recommend", "i1")[0], 1)
        self.assertEqual(self.differentiate()[0], 0)
        self.assertIn("Nothing to change", self.refused("revise", "i1", "--data", "Three sections per condition."))

        self.run_cli("export")
        log = (self.dir / "novelty-log.md").read_text(encoding="utf-8")
        self.assertIn("- Version 1, replaced 2026-11-12 (novelty then: differentiated within the searches logged). Question: Does", log)
        self.assertIn("MORE THAN ON METHOD-GIVEN PROBLEMS. Note: After the second attack.", log)
        self.assertIn("| s1 | 2026-11-12 | 1 | duplicate |", log)
        self.assertIn("| s3 | 2026-11-12 | 2 | duplicate |", log)

    def test_gates_come_before_ratings_and_every_score_has_a_reason(self):
        self.add()
        self.assertIn("Gates come before ratings", self.refused("rate", "i1", *RATINGS))
        self.assertIn("gate takes name=value", self.refused("gate", "i1", "funding=confirmed"))
        self.assertIn("A gate is one of", self.refused("gate", "i1", "data=fine"))
        self.assertIn("says what blocks it", self.refused("gate", "i1", "data=blocked"))
        _, gates = self.run_cli("gate", "i1", "data=blocked:the registry releases no item-level scores", *GATES[1:4])
        self.assertEqual(gates["not_assessed"], ["time"])
        self.assertIn("Not assessed yet: time", self.refused("rate", "i1", "value=2:reason"))
        self.run_cli("gate", "i1", "time=plausible")

        self.assertIn("a score from 0 to 3 and a reason", self.refused("rate", "i1", "value=2"))
        self.assertIn("a score from 0 to 3 and a reason", self.refused("rate", "i1", "value=4:too good"))
        self.assertIn("rate takes name=value", self.refused("rate", "i1", "novelty=3:new"))
        self.assertIn("difference is judged against the closest works", self.refused("rate", "i1", "difference=3:feels new"))
        self.assertIn("feasibility is 0 while a gate is blocked (data)", self.refused("rate", "i1", "feasibility=2:fine"))
        _, rated = self.run_cli("rate", "i1", "value=2:changes how homework is set", "feasibility=0:the data gate is blocked")
        self.assertEqual(rated, {"idea": "i1", "ratings": {"value": 2, "feasibility": 0},
                                 "not_rated": ["difference", "testability", "information_gain"]})

    def test_recommend_lists_exactly_what_is_missing(self):
        self.add(refuted_by="")
        code, result = self.run_cli("recommend", "i1")
        self.assertEqual(code, 1)
        self.assertEqual(result, {"idea": "i1", "version": 1, "recommended": False, "missing": [
            "novelty is unsearched for version 1, not differentiated",
            "no closest work is marked decisive and read in full text",
            "not rated: value, difference, testability, feasibility, information_gain",
            "the card has no refuting result (refuted_by)"]})

        self.differentiate()
        self.run_cli("gate", "i1", *GATES)
        self.run_cli("rate", "i1", *RATINGS)
        self.assertEqual(self.run_cli("recommend", "i1")[1]["missing"],
                         ["no closest work is marked decisive and read in full text",
                          "the card has no refuting result (refuted_by)"])
        self.run_cli("revise", "i1", "--refuted-by", CARD["refuted_by"])
        # Reading another work in full does not stand in for the decisive one.
        self.closest("i1", [{"corpusId": 12, "title": CLOSEST[1]["title"], "read": "full_text"}])
        self.assertEqual(self.run_cli("recommend", "i1")[1]["missing"], ["no closest work is marked decisive and read in full text"])
        marked = self.closest("i1", [{"corpusId": 11, "title": CLOSEST[0]["title"], "decisive": True}])
        self.assertEqual(marked["decisive"], "Okoro et al. 2019: Interleaved practice in a calculus course (read: abstract)")
        self.assertEqual(self.run_cli("recommend", "i1")[1]["missing"], [
            "the decisive closest work was read from the abstract only: Okoro et al. 2019: Interleaved practice in a calculus course"])
        self.closest("i1", [{"corpusId": 11, "title": CLOSEST[0]["title"], "read": "full_text"}])
        self.run_cli("gate", "i1", "ethics=blocked:no approval route for course data")
        self.assertEqual(self.run_cli("recommend", "i1")[1]["missing"], ["gate ethics is blocked"])
        self.run_cli("gate", "i1", "ethics=plausible")
        code, result = self.run_cli("recommend", "i1")
        self.assertEqual((code, result["recommended"]), (0, True))
        self.assertEqual(result["open_points"], ["gate time is unknown", "no assumption is recorded", "no attack is recorded",
                                                 "the first study lacks: " + ", ".join(n for n, _ in il.STUDY_FIELDS)])

        # A recommendation holds only while the record supports it.
        self.run_cli("gate", "i1", "data=blocked:access was withdrawn")
        _, status = self.run_cli("status")
        self.assertEqual((status["recommended"], status["open"], status["no_candidate_qualifies"]), ([], ["i1"], True))
        self.run_cli("export")
        self.assertIn("The earlier recommendation no longer holds. Not recommended: gate data is blocked.",
                      (self.dir / "ideas.md").read_text(encoding="utf-8"))

    def test_assumptions_attacks_and_the_first_study(self):
        self.add()
        _, first = self.run_cli("assume", "i1", "--text", "Raters can tell the two item types apart", "--risk", "4",
                                "--months", "6", "--test", "Double-code 60 items")
        self.assertIn("the brief gives no months to judge", first["cannot_be_tested_early"])
        self.run_cli("brief", "--field", "Mathematics education", "--months", "12", "--data", "Course records")
        _, late = self.run_cli("assume", "i1", "--text", "Sections are comparable at entry", "--risk", "2", "--months", "1")
        self.assertEqual((late["assumptions"], late["cannot_be_tested_early"]),
                         (2, "the riskiest assumption (risk 4: Raters can tell the two item types apart) takes 6 months "
                             "to test, more than a quarter of the 12 months available"))
        _, early = self.run_cli("assume", "i1", "--text", "raters can tell the two item types apart", "--risk", "4", "--months", "1")
        self.assertEqual((early["assumptions"], early["cannot_be_tested_early"]), (2, ""))   # the same text replaces

        self.assertIn('Write "none"', self.refused("attack", "i1", "--attack", "Okoro 2019 did this", "--basis", "closest work",
                                                   "--change", " ", "--residual", "none"))
        self.assertEqual(self.run_cli("attack", "i1", "--attack", "Okoro 2019 did this", "--basis", "closest work 11",
                                      "--change", "none", "--residual", "Their appendix may hold the item split")[1]["attacks"], 1)
        self.assertIn("study takes name=value", self.refused("study", "i1", "plan=run it"))
        _, study = self.run_cli("study", "i1", "decision=Run the full trial or drop the idea", "budget=3 weeks")
        self.assertEqual(study["not_set"], ["support", "refute", "undetermined", "null_value", "first_action"])
        self.assertEqual(self.run_cli("study", "i1", self.write("study.json", {"first_action": "Ask for last year's items"}))
                         [1]["study"]["budget"], "3 weeks")

    def test_export_keeps_recommended_open_and_rejected_ideas_and_has_no_total(self):
        self.add()
        self.add(question="Does the gain last to the next course?", title="Does it last")
        self.add(question="Is interleaving better than blocked practice at all?", title="Interleaving at all")
        self.assertEqual(self.run_cli("export")[1]["no_candidate_qualifies"], True)
        self.assertIn("**No candidate qualifies for a recommendation.**", (self.dir / "ideas.md").read_text(encoding="utf-8"))

        self.run_cli("brief", "--field", "Mathematics education", "--question-type", "causal", "--months", "12")
        self.run_cli("search", "base", "--query", "interleaved practice", "--total", "240", "--sort", "citationCount")
        self.pass_every_check("i1")
        self.run_cli("search", "i2", "--intent", "skeptic", "--query", "interleaving retention null", "--failed", "TIMEOUT")
        self.assertIn("--restart-if", self.refused("reject", "i3", "--reason", "Okoro 2019 answers it", "--restart-if", " "))
        self.run_cli("reject", "i3", "--reason", "Okoro 2019 answers it.", "--restart-if", "A replication fails.")
        code, exported = self.run_cli("export")
        self.assertEqual((code, exported["recommended"], exported["open"], exported["rejected"],
                          exported["no_candidate_qualifies"]), (0, 1, 1, 1, False))

        ideas = (self.dir / "ideas.md").read_text(encoding="utf-8")
        self.assertLess(ideas.index("## Recommended"), ideas.index("## Open"))
        self.assertLess(ideas.index("## Open"), ideas.index("## Rejected"))
        self.assertIn("Field: Mathematics education; Question type: causal; Time: 12 months.", ideas)
        self.assertIn("3 ideas: 1 recommended, 1 open, 1 rejected.", ideas)
        self.assertIn("### i1 · Interleaved homework and method choice (version 1)\n\nRecommended. Still open: gate time is unknown", ideas)
        self.assertIn("| Refuted by | No difference on method-choice items", ideas)
        self.assertIn("Novelty of version 1: **differentiated within the searches logged** (set 2026-11-12). Intents with a "
                      "completed search: duplicate, mechanism. No completed search: adjacent, skeptic. Not available: citation", ideas)
        self.assertIn("| [Okoro et al. 2019: Interleaved practice in a calculus course](https://app.researchzy.com/read/c/11) |", ideas)
        self.assertIn("| Ruiz 2015: Spacing and time on task |", ideas)
        self.assertIn("| full text, decisive |", ideas)
        self.assertIn("Gates: data confirmed; ethics plausible; equipment confirmed; skills confirmed; time unknown.", ideas)
        self.assertIn("| information gain | 2 | either result rules out one explanation |", ideas)
        self.assertIn("Not recommended: novelty is unsearched for version 1, not differentiated; no closest work is "
                      "marked decisive and read in full text; not rated: value, difference", ideas)
        self.assertIn("the searches for skeptic failed and were not repeated (a failed search is not zero results)", ideas)
        self.assertIn("Rejected: Okoro 2019 answers it. Restart if: A replication fails.", ideas)
        self.assertNotRegex(ideas, r"(?i)\b(total|sum|average|overall)\b")
        self.assertNotRegex(json.dumps(self.run_cli("status")[1]), r"(?i)\"(total|sum|average|overall)")

        log = (self.dir / "novelty-log.md").read_text(encoding="utf-8")
        self.assertIn("Not available for any idea: `citation` (the index has no cited-by search", log)
        self.assertIn("## Evidence base", log)
        self.assertIn("| s1 | 2026-11-12 | search_papers | `interleaved practice` | citationCount | — | 240 | completed |", log)
        self.assertIn('| s2 | 2026-11-12 | 1 | duplicate | search_papers | `"interleaved practice" calculus` | year | yearFrom=2023 | 37 | completed |', log)
        self.assertIn("| — | failed, not zero results: TIMEOUT |", log)
        self.assertIn("No search is logged for this idea.", log)
        self.assertIn("Closest works for version 1:", log)

    def test_a_damaged_ledger_stops_with_a_message(self):
        self.dir.mkdir(parents=True)
        (self.dir / "ideas.json").write_text("{", encoding="utf-8")
        self.assertIn("is not valid JSON", self.refused("status"))


if __name__ == "__main__":
    unittest.main()
