"""sr_ledger.py: every PRISMA count comes from the per-record ledger, and every rule of check holds.

All records in tests/fixtures are invented for these tests (DOIs use the 10.5555 test prefix)."""
from __future__ import annotations

import copy
import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).parent
SCRIPT = HERE.parent / "scripts" / "sr_ledger.py"
spec = importlib.util.spec_from_file_location("sr_ledger", SCRIPT)
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)
FIXTURES = HERE / "fixtures"

PROTOCOL = {
    "title": "Synthetic test review: evening meal timing and sleep",
    "question": "In adults, does an earlier evening meal improve sleep compared with a later one?",
    "framework": "PICO",
    "elements": {"population": "adults", "intervention": "earlier evening meal", "comparator": "later evening meal",
                 "outcome": "sleep quality"},
    "criteria": [{"code": "I1", "text": "randomised trial in adults"}, {"code": "E1", "text": "not a randomised trial"},
                 {"code": "E2", "text": "participants under 18"}, {"code": "E3", "text": "animal study"}],
    "exclusion_order": ["E3", "E1", "E2"],
    "outcomes": [{"name": "sleep quality", "role": "primary", "timepoints": ["end of intervention"]}],
    "designs": ["randomised controlled trial"],
    "sources": ["Researchzy index", "PubMed", "ClinicalTrials.gov", "Embase (the user's export)"],
    "limits": [],
    "calibration": {"kappa_min": 0.6, "recall_min": 1.0, "user_screens": True},
    "registration": {"status": "not_registered"},
    "seeds": [{"doi": "10.5555/fixture.001"}],
}
FULLTEXT_R0001 = ("[[page 1]]\nEvening meal timing and sleep quality. This full text is synthetic.\n[[page 3]]\nIn the "
                  "early-meal group the mean global score fell from 9.4 to 7.1 after eight weeks (n = 40). Poor sleep at "
                  "eight weeks: 12 of 40 in the early-meal group and 19 of 41 in the late-meal group; odds ratio 0.48 "
                  "(95% CI 0.19 to 1.21).\n")
FULLTEXT_R0002 = ("[[page 2]]\nThe partici-\npants were allocated by alternation, so the trial was not ran-\ndomised. The "
                  "\ufb01nal analysis kept everyone.\n")


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.dir = self.base / "systematic-review"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = sl.main(["--dir", str(self.dir), *argv])
        return code, json.loads(out.getvalue())

    def fails(self, *argv) -> str:
        err = io.StringIO()
        with self.assertRaises(SystemExit) as raised, redirect_stderr(err), redirect_stdout(io.StringIO()):
            sl.main(["--dir", str(self.dir), *argv])
        self.assertEqual(raised.exception.code, 2)
        return err.getvalue()

    def write(self, name: str, content) -> Path:
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return path

    def decide(self, *decisions):
        path = self.write(f"decisions-{len(list(self.base.glob('decisions-*')))}.jsonl",
                          "\n".join(json.dumps(d) for d in decisions) + "\n")
        return self.run_cli("decide", str(path))

    def protocol(self, proto=None):
        return self.run_cli("protocol", str(self.write("protocol.json", proto or PROTOCOL)))

    def build(self, calibration="passed"):
        """A small, complete review: four sources, ten records, seven after duplicates."""
        self.protocol()
        self.run_cli("search", "--source", "Researchzy index", "--kind", "database", "--interface", "search_papers",
                     "--query", '"evening meal" sleep', "--filter", "yearFrom=2015", "--total", "4", "--pages", "1",
                     "--last-page", "--date", "2026-11-10T09:00Z")
        self.run_cli("records", str(FIXTURES / "researchzy.json"), "--search", "s1", "--format", "researchzy")
        self.run_cli("search", "--source", "PubMed", "--kind", "database", "--interface", "E-utilities",
                     "--query", "meal timing[tiab] AND sleep[tiab]", "--total", "2", "--pages", "1", "--date", "2026-11-10")
        self.run_cli("records", str(FIXTURES / "pubmed.xml"), "--search", "s2", "--format", "pubmed")
        self.run_cli("search", "--source", "ClinicalTrials.gov", "--kind", "register", "--interface", "API v2",
                     "--query", "meal timing AND sleep", "--total", "2", "--pages", "1", "--date", "2026-11-11")
        self.run_cli("records", str(FIXTURES / "ctgov.json"), "--search", "s3", "--format", "ctgov")
        self.run_cli("search", "--source", "Embase", "--kind", "database", "--interface", "the user's institutional export",
                     "--query", "'meal timing'/exp AND sleep", "--total", "2", "--exported", "2", "--date", "2026-11-09")
        self.run_cli("records", str(FIXTURES / "export.ris"), "--search", "s4", "--format", "ris")
        self.run_cli("dedup", "--merge", "R0002", "R0003")
        self.decide(
            {"record": "R0001", "stage": "ta", "decision": "include", "reviewer": "model"},
            {"record": "R0002", "stage": "ta", "decision": "include", "reviewer": "model"},
            {"record": "R0004", "stage": "ta", "decision": "exclude", "code": "E3", "quote": "male mice received a late snack",
             "reviewer": "model"},
            {"record": "R0006", "stage": "ta", "decision": "exclude", "code": "E2",
             "quote": "Participants aged 12 to 17 years", "reviewer": "user"},
            {"record": "R0007", "stage": "ta", "decision": "unsure", "reviewer": "model"},
            {"record": "R0008", "stage": "ta", "decision": "exclude", "code": "E3", "quote": "Snack Timing in Mice",
             "reviewer": "model"},
            {"record": "R0010", "stage": "ta", "decision": "include", "reviewer": "model"})
        self.write("systematic-review/fulltext/R0001.txt", FULLTEXT_R0001)
        self.write("systematic-review/fulltext/R0002.txt", FULLTEXT_R0002)
        self.decide(
            {"record": "R0001", "stage": "ft", "decision": "include", "study": "NCT09999901", "reviewer": "model"},
            {"record": "R0007", "stage": "ft", "decision": "include", "study": "NCT09999901", "reviewer": "model"},
            {"record": "R0002", "stage": "ft", "decision": "exclude", "code": "E1", "locator": "p. 2", "reviewer": "model",
             "quote": "The participants were allocated by alternation, so the trial was not randomised"},
            {"record": "R0010", "stage": "ft", "decision": "not_retrieved", "reviewer": "model",
             "note": "conference abstract only; get_pdf_download had no file and the user had none"})
        if calibration:
            self.write("systematic-review/calibration/round1-score.json",
                       {"round": 1, "status": calibration, "scored": "2026-11-11T10:00:00Z", "records": []})

    def codes(self) -> list:
        return [f["code"] for f in sl.findings(sl.load(self.dir), self.dir)]


class ParserTests(LedgerTestCase):
    def test_the_four_formats(self):
        researchzy = sl.parse_researchzy((FIXTURES / "researchzy.json").read_bytes())
        self.assertEqual([r["corpus_id"] for r in researchzy], ["900001", "900002", "900003", "900004"])
        self.assertEqual((researchzy[0]["doi"], researchzy[0]["authors"]), ("10.5555/fixture.001", ["Ada Fixture"]))
        pubmed = sl.parse_pubmed((FIXTURES / "pubmed.xml").read_bytes())
        self.assertEqual(pubmed[0]["doi"], "10.5555/fixture.001")            # not the DOI of the cited work
        self.assertEqual((pubmed[0]["pmid"], pubmed[0]["links"], pubmed[0]["year"]), ("99000001", ["NCT09999901"], 2021))
        self.assertIn("METHODS: Adults were randomly assigned", pubmed[0]["abstract"])
        self.assertEqual(pubmed[0]["title"], "Evening meal timing and sleep quality: a synthetic randomised trial")
        self.assertEqual(pubmed[0]["authors"], ["Ada Fixture", "Test Data Collaborative"])
        self.assertEqual((pubmed[1]["year"], "doi" in pubmed[1]), (2019, False))   # from "2019 Dec-2020 Jan"
        ctgov = sl.parse_ctgov((FIXTURES / "ctgov.json").read_bytes())
        self.assertEqual((ctgov[0]["nct"], ctgov[0]["year"], ctgov[0]["links"]), ("NCT09999901", 2020, ["99000001"]))
        self.assertIn("Allocation: RANDOMIZED.", ctgov[0]["abstract"])
        self.assertEqual(ctgov[1]["title"], "Snack Timing in Mice (Synthetic)")
        ris = sl.parse_ris((FIXTURES / "export.ris").read_bytes())
        self.assertEqual(ris[0]["title"], "Evening meal timing and sleep quality: a synthetic randomised trial")
        self.assertEqual((ris[0]["doi"], ris[0]["year"], ris[1]["year"]), ("10.5555/fixture.001", 2021, 2020))
        self.assertEqual(ris[1]["abstract"], "An invented conference abstract about an early evening meal in adults.")

    def test_quotes_survive_extraction_but_not_changed_words(self):
        text = sl.joined("The \ufb01nal analy-\nsis of time-\nrestricted eating showed p < 0.05 and \u22120.5 units.")
        for quote in ("the final analysis", "time-restricted eating", "showed p<0.05", "THE FINAL ANALYSIS OF"):
            self.assertTrue(sl.contains(text, quote), quote)
        for quote in ("showed p > 0.05", "the first analysis", "and 0.6 units", "final analysis of eating"):
            self.assertFalse(sl.contains(text, quote), quote)
        self.assertEqual(sl.quote_words("p < 0.05"), 2)
        self.assertEqual(sl.norm_doi("https://doi.org/10.5555/ABC."), "10.5555/abc")
        self.assertEqual(sl.norm_doi("not a doi"), "")


class ProtocolTests(LedgerTestCase):
    def test_a_valid_protocol_is_recorded_and_changes_need_an_amendment(self):
        code, out = self.protocol()
        self.assertEqual((code, out["recorded"], out["version"]), (0, True, 1))
        self.assertEqual(self.protocol()[1]["note"], "the same as the recorded version")
        changed = copy.deepcopy(PROTOCOL)
        changed["criteria"][3]["text"] = "animal or cell study"
        self.assertIn("--amend", self.fails("protocol", str(self.write("protocol.json", changed))))
        code, out = self.run_cli("protocol", str(self.base / "protocol.json"), "--amend", "E3 also excludes cell studies",
                                 "--results-seen", "yes")
        self.assertEqual((code, out["version"]), (0, 2))
        history = sl.load(self.dir)["protocol_history"]
        self.assertEqual((history[1]["change"], history[1]["results_seen"]), ("E3 also excludes cell studies", True))
        self.assertEqual(json.loads((self.dir / "protocol.json").read_text())["version"], 2)

    def test_protocol_problems(self):
        bad = copy.deepcopy(PROTOCOL)
        bad["criteria"].append({"code": "E2", "text": "duplicate code"})
        bad["criteria"].append({"code": "E4", "text": "not in the order"})
        bad["calibration"]["kappa_min"] = "0.6"
        bad["limits"] = [{"limit": "English only"}]
        bad["registration"] = {"status": "registered", "registry": "a registry"}
        bad["framework"] = "PICOS"
        code, out = self.run_cli("protocol", str(self.write("bad.json", bad)))
        self.assertEqual((code, out["recorded"]), (1, False))
        problems = " | ".join(out["problems"])
        for part in ("codes used twice: E2", "exclusion_order must list every E code", "kappa_min and recall_min",
                     "every limit needs a reason", "registered (with registry, id, date", "framework must be one of"):
            self.assertIn(part, problems)
        declined = copy.deepcopy(PROTOCOL)
        declined["calibration"]["user_screens"] = False
        self.assertIn("declined_reason", " ".join(self.run_cli("protocol", str(self.write("d.json", declined)))[1]["problems"]))
        self.assertFalse((self.dir / "protocol.json").exists())


class SearchAndRecordTests(LedgerTestCase):
    def test_searches_are_logged_and_incomplete_exports_caught(self):
        self.protocol()
        code, out = self.run_cli("search", "--source", "Researchzy index", "--kind", "database", "--interface",
                                 "search_papers", "--query", "meal sleep", "--total", "120", "--pages", "1")
        self.assertEqual((code, out), (0, {"search": "s1", "round": 1}))
        self.run_cli("records", str(FIXTURES / "researchzy.json"), "--search", "s1", "--format", "researchzy")
        self.run_cli("search", "--source", "PubMed", "--kind", "database", "--interface", "E-utilities", "--query", "x",
                     "--exported", "5")
        self.run_cli("records", str(FIXTURES / "pubmed.xml"), "--search", "s2", "--format", "pubmed")
        found = {(f["code"], f["where"]): f["severity"] for f in sl.findings(sl.load(self.dir), self.dir)}
        self.assertEqual(found[("SEARCH_INCOMPLETE", "s1")], "error")       # 4 of 120, last page not reached
        self.assertEqual(found[("EXPORT_COUNT_MISMATCH", "s2")], "error")   # 5 logged, 2 added
        self.assertEqual(found[("SEARCH_TOTAL_UNKNOWN", "s2")], "warning")
        self.run_cli("search", "--id", "s1", "--incomplete-reason", "the remaining hits were off topic after page 1")
        self.run_cli("search", "--id", "s2", "--exported", "2", "--total", "2")
        found = {(f["code"], f["where"]): f["severity"] for f in sl.findings(sl.load(self.dir), self.dir)}
        self.assertEqual(found[("SEARCH_INCOMPLETE", "s1")], "warning")
        self.assertNotIn(("EXPORT_COUNT_MISMATCH", "s2"), found)
        self.run_cli("search", "--id", "s1", "--last-page")
        self.assertNotIn("SEARCH_INCOMPLETE", self.codes())

    def test_bad_input_stops_with_exit_code_2(self):
        self.protocol()
        self.assertIn("log it first", self.fails("records", str(FIXTURES / "export.ris"), "--search", "s9", "--format", "ris"))
        self.run_cli("search", "--source", "Embase", "--kind", "database", "--interface", "export", "--query", "q")
        self.assertIn("cannot be read as pubmed", self.fails("records", str(FIXTURES / "export.ris"), "--search", "s1",
                                                            "--format", "pubmed"))
        self.assertIn("no ris records", self.fails("records", str(FIXTURES / "ctgov.json"), "--search", "s1", "--format", "ris"))
        self.run_cli("records", str(FIXTURES / "export.ris"), "--search", "s1", "--format", "ris")
        self.assertIn("added before", self.fails("records", str(FIXTURES / "export.ris"), "--search", "s1", "--format", "ris"))
        self.assertIn("cannot read", self.fails("records", str(self.base / "missing.ris"), "--search", "s1", "--format", "ris"))
        self.assertIn("a new search needs", self.fails("search", "--query", "only a query"))
        self.assertIn("--date must be", self.fails("search", "--id", "s1", "--date", "13/11/2026"))
        self.assertIn("no record", self.fails("dedup", "--merge", "R0001", "R0999"))


class DedupTests(LedgerTestCase):
    def test_identifiers_merge_titles_propose_and_reports_stay_apart(self):
        self.build(calibration=None)
        grp = sl.groups(sl.load(self.dir))
        self.assertEqual({grp["R0001"], grp["R0005"], grp["R0009"]}, {"R0001"})   # one DOI, three sources
        self.assertEqual(grp["R0007"], "R0007")    # the registration of the trial is another report, not a duplicate
        self.assertEqual(grp["R0003"], "R0002")    # merged by hand

    def test_candidate_pairs_must_be_settled(self):
        self.protocol()
        self.run_cli("search", "--source", "Researchzy index", "--kind", "database", "--interface", "search_papers",
                     "--query", "q", "--total", "4", "--last-page")
        self.run_cli("records", str(FIXTURES / "researchzy.json"), "--search", "s1", "--format", "researchzy")
        code, out = self.run_cli("dedup")
        self.assertEqual((code, out["groups"], out["candidate_pairs"]), (0, 4, 1))
        self.assertIn("| R0002 | R0003 |", (self.dir / "duplicates.md").read_text())
        self.assertIn("DUPLICATE_CANDIDATES_PENDING", self.codes())
        self.assertEqual(self.run_cli("dedup", "--distinct", "R0002", "R0003", "--reviewer", "user")[1]["candidate_pairs"], 0)
        self.assertNotIn("DUPLICATE_CANDIDATES_PENDING", self.codes())
        self.assertEqual(sl.load(self.dir)["distinct"][0]["reviewer"], "user")


class DecideTests(LedgerTestCase):
    def test_each_decision_is_checked(self):
        self.build(calibration=None)
        code, out = self.decide(
            {"record": "R0404", "stage": "ta", "decision": "include", "reviewer": "model"},
            {"record": "R0006", "stage": "ta", "decision": "maybe", "reviewer": "model"},
            {"record": "R0006", "stage": "ta", "decision": "include"},
            {"record": "R0006", "stage": "ta", "decision": "exclude", "code": "E9", "quote": "aged 12 to 17", "reviewer": "model"},
            {"record": "R0006", "stage": "ta", "decision": "exclude", "code": "E2", "quote": "aged 12", "reviewer": "model"},
            {"record": "R0004", "stage": "ft", "decision": "include", "reviewer": "model"},
            {"record": "R0001", "stage": "ft", "decision": "exclude", "code": "E1", "quote": "the mean global score fell",
             "reviewer": "model"},
            {"record": "R0001", "stage": "ft", "decision": "not_retrieved", "reviewer": "model"},
            {"record": "R0002", "stage": "pre", "decision": "remove", "reviewer": "model"})
        self.assertEqual((code, out["accepted"]), (1, 0))
        problems = [r["problem"] for r in out["rejected"]]
        for line, part in enumerate(("unknown record", "stage and decision must be", "reviewer is missing",
                                     "not an exclusion code", "at least 3 words", "not included at ta", "needs a locator",
                                     "note of what was tried", "a removal needs a reason")):
            self.assertIn(part, problems[line])
        self.write("not-json.jsonl", 'not json\n["a list"]\n')
        self.assertEqual([r["problem"] for r in self.run_cli("decide", str(self.base / "not-json.jsonl"))[1]["rejected"]],
                         ["not a JSON object", "not a JSON object"])

    def test_the_last_decision_is_final_and_repeats_change_nothing(self):
        self.build(calibration=None)
        same = {"record": "R0001", "stage": "ta", "decision": "include", "reviewer": "model"}
        self.assertEqual(self.decide(same)[1], {"accepted": 0, "unchanged": 1, "rejected": []})
        code, out = self.decide(same, dict(same, reviewer="user"))
        self.assertEqual((code, out["rejected"][0]["problem"]), (1, "line 1 of this file decides the same record and stage"))
        # A duplicate's id resolves to its group; a later decision replaces the final one and keeps the history.
        self.decide({"record": "R0005", "stage": "ta", "decision": "include", "reviewer": "user"})
        ledger = sl.load(self.dir)
        self.assertEqual(sl.finals(ledger, sl.groups(ledger))[("R0001", "ta")]["reviewer"], "user")
        self.assertEqual(sum(1 for d in ledger["decisions"] if d["stage"] == "ta" and d["record"] in ("R0001", "R0005")), 2)


class CheckTests(LedgerTestCase):
    def test_a_complete_review_passes(self):
        self.build()
        code, out = self.run_cli("check")
        self.assertEqual((code, out["errors"], out["warnings"], out["by_finding"]), (0, 0, 0, {}))
        self.assertIn("0 errors, 0 warnings", (self.dir / "check.md").read_text())

    def test_quotes_codes_and_stage_losses(self):
        self.build()
        self.decide({"record": "R0006", "stage": "ta", "decision": "exclude", "code": "E2", "reviewer": "model",
                     "quote": "participants aged 18 to 25 years"},
                    {"record": "R0002", "stage": "ft", "decision": "exclude", "code": "E1", "locator": "p. 2",
                     "reviewer": "model", "quote": "allocated at random by a computer"})
        (self.dir / "fulltext" / "R0002.txt").unlink()
        self.decide({"record": "R0001", "stage": "ta", "decision": "exclude", "code": "E1", "reviewer": "model",
                     "quote": "randomly assigned to an early"},
                    {"record": "R0004", "stage": "ta", "decision": "exclude", "code": "E3", "reviewer": "model",
                     "quote": "Snack timing in mice: an invented laboratory study"})
        found = {(f["code"], f["where"]) for f in sl.findings(sl.load(self.dir), self.dir)}
        self.assertIn(("TITLE_AS_QUOTE", "R0004 ta"), found)    # in the record, but it does not say why
        self.assertIn(("QUOTE_NOT_FOUND", "R0006 ta"), found)
        self.assertIn(("FULLTEXT_MISSING", "R0002 ft"), found)
        self.assertIn(("NOT_AT_STAGE", "R0001"), found)       # excluded at ta, but it has a full-text decision
        self.write("systematic-review/fulltext/R0002.txt", FULLTEXT_R0002)
        self.assertIn(("QUOTE_NOT_FOUND", "R0002 ft"), {(f["code"], f["where"]) for f in sl.findings(sl.load(self.dir), self.dir)})
        code, _ = self.run_cli("check")
        self.assertEqual(code, 1)

    def test_missing_decisions_are_reported(self):
        self.build()
        self.run_cli("search", "--source", "PubMed", "--kind", "database", "--interface", "E-utilities", "--query", "more",
                     "--total", "1", "--date", "2026-11-12")
        self.write("one.ris", "TY  - JOUR\nTI  - A further invented record about meal timing in adults\nPY  - 2024\nER  - \n")
        self.run_cli("records", str(self.base / "one.ris"), "--search", "s5", "--format", "ris")
        self.decide({"record": "R0011", "stage": "ta", "decision": "include", "reviewer": "model"})
        self.assertIn(("error", "STAGE_TRANSFER_LOSS", "R0011"),
                      {(f["severity"], f["code"], f["where"]) for f in sl.findings(sl.load(self.dir), self.dir)})
        self.assertEqual(self.run_cli("check")[0], 1)
        self.write("two.ris", "TY  - JOUR\nTI  - Yet another invented record on breakfast and alertness\nPY  - 2024\nER  - \n")
        self.run_cli("records", str(self.base / "two.ris"), "--search", "s5", "--format", "ris")
        found = {(f["severity"], f["code"], f["where"]) for f in sl.findings(sl.load(self.dir), self.dir)}
        self.assertIn(("error", "NO_DECISION", "R0012"), found)

    def test_seeds_calibration_amendments_and_study_labels(self):
        self.build(calibration="below_threshold")
        self.assertIn("CALIBRATION_BELOW_THRESHOLD", self.codes())
        (self.dir / "calibration" / "round1-score.json").unlink()
        self.assertIn("CALIBRATION_MISSING", self.codes())
        proto = copy.deepcopy(PROTOCOL)
        proto["calibration"] = {"kappa_min": 0.6, "recall_min": 1.0, "user_screens": False, "declined_reason": "no time"}
        proto["seeds"].append({"title": "A known paper that no search returned"})
        proto["criteria"][3]["text"] = "animal or cell study"
        self.run_cli("protocol", str(self.write("protocol.json", proto)), "--amend", "user declined; E3 widened",
                     "--results-seen", "yes")
        found = {(f["code"], f["where"]) for f in sl.findings(sl.load(self.dir), self.dir)}
        self.assertIn(("MODEL_ONLY_SCREENING", "calibration"), found)
        self.assertIn(("SEED_NOT_FOUND", "A known paper that no search returned"), found)
        self.assertIn(("CODE_CHANGED_SINCE_DECISION", "R0004 ta"), found)
        self.assertNotIn("CALIBRATION_MISSING", {code for code, _ in found})
        on_disk = json.loads((self.dir / "protocol.json").read_text())
        on_disk["exclusion_order"] = ["E1", "E2", "E3"]
        (self.dir / "protocol.json").write_text(json.dumps(on_disk))
        self.assertIn("PROTOCOL_CHANGED_UNRECORDED", self.codes())
        self.decide({"record": "R0007", "stage": "ft", "decision": "include", "study": "registration-only", "reviewer": "model"})
        self.assertIn("POSSIBLE_SAME_STUDY", self.codes())   # the article lists the trial's NCT number

    def test_extraction_rows_need_quotes_from_the_full_text(self):
        self.build()
        base = dict.fromkeys(sl.EXTRACTION, "")
        good = dict(base, study="NCT09999901", outcome="sleep quality", timepoint="end of intervention", arm="early meal",
                    n="40", design="parallel", reported_as="mean_sd", value="7.1", spread="2.0", locator="p. 3",
                    quote="the mean global score fell from 9.4 to 7.1 after eight weeks")
        rows = [good,
                dict(good, value="7.4"),
                dict(good, quote="the mean global score rose from 9.4 to 7.1 after eight weeks"),
                dict(good, study="R0002", arm="control"),
                dict(good, arm="control", value="9.0", locator="", quote=""),
                dict(good, reported_as="mean_sd_or_se"),
                dict(base, study="NCT09999901", outcome="poor sleep", timepoint="8 weeks", arm="early meal", n="40",
                     reported_as="events", events="12", locator="p. 3", quote="12 of 40 in the early-meal group"),
                dict(base, study="NCT09999901", outcome="poor sleep", timepoint="8 weeks", n="81", reported_as="ratio_ci",
                     value="0.48", low="0.19", high="1.21", locator="p. 3", quote="odds ratio 0.48 (95% CI 0.19 to 1.21)")]
        path = self.dir / "extraction.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=[c.capitalize() if c == "study" else c for c in sl.EXTRACTION] + ["region"])
            writer.writeheader()                                # header case does not matter; extra columns are kept
            writer.writerows([{("Study" if k == "study" else k): v for k, v in dict(r, region="north").items()} for r in rows])
        found = {(f["code"], f["where"]) for f in sl.findings(sl.load(self.dir), self.dir)}
        lines = {where for _, where in found}
        for line in (2, 8, 9):                                 # a clean row, an events row, a study-level ratio row
            self.assertNotIn(f"extraction.csv:{line}", lines)
        self.assertIn(("EXTRACTION_VALUE_NOT_IN_QUOTE", "extraction.csv:3"), found)
        self.assertIn(("EXTRACTION_QUOTE_NOT_FOUND", "extraction.csv:4"), found)
        self.assertIn(("EXTRACTION_STUDY_NOT_INCLUDED", "extraction.csv:5"), found)
        self.assertIn(("EXTRACTION_NO_SOURCE", "extraction.csv:6"), found)
        self.assertIn(("EXTRACTION_FORMAT", "extraction.csv:7"), found)
        self.write("systematic-review/extraction.csv", "study,outcome\nNCT09999901,sleep\n")
        self.assertIn("EXTRACTION_FORMAT", self.codes())


if __name__ == "__main__":
    unittest.main()
