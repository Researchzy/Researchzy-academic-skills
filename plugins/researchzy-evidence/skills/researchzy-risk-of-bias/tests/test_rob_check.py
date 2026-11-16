"""rob_check.py: judgements rest on quotes found in the saved texts and follow the registered tool."""
from __future__ import annotations

import copy
import hashlib
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


rc = load("rob_check", HERE.parent / "scripts" / "rob_check.py")
fx = load("review_fixture", HERE / "review_fixture.py")
ALDER, BIRCH, CEDAR = 0, 1, 2


def domain(assessments: list, study: int, did: str) -> dict:
    return assessments[study]["results"][0]["domains"][did]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, edit=None, tool_edit=None, hashes=True) -> Path:
        tool, assessments = copy.deepcopy(fx.TOOL), copy.deepcopy(fx.ASSESSMENTS)
        if tool_edit:
            tool_edit(tool)
        if edit:
            edit(assessments["assessments"])
        return fx.build(self.dir, tool, assessments, hashes)

    def cli(self, *argv) -> tuple:
        out = io.StringIO()
        with redirect_stdout(out):
            code = rc.main([str(a) for a in argv])
        return code, json.loads(out.getvalue())

    def rows(self, edit=None, tool_edit=None, hashes=True) -> list:
        return rc.run_checks(self.build(edit, tool_edit, hashes))[0]

    def failed(self, rows: list, check: str) -> list:
        return [(r["where"], r["detail"]) for r in rows if r["status"] == "fail" and r["check"] == check]


class CheckTests(Base):
    def test_a_sound_review_passes_and_unmapped_domains_stay_not_checked(self):
        base = self.build()
        code, summary = self.cli("check", "--dir", base)
        self.assertEqual((code, summary["fail"], summary["not_checked"], summary["not_reviewed_by_a_person"]), (0, 0, 6, 3))
        rows = rc.run_checks(base)[0]
        self.assertEqual(sum(r["check"] == "mapping" and r["status"] == "ok" for r in rows), 3)
        quotes = {r["where"] + " " + r["detail"] for r in rows if r["check"] == "quote"}
        self.assertIn("alder2021 / weight / D3 EXACT in texts/alder2021.txt, page 2", quotes)      # "assign-\nment"
        self.assertIn("cedar2023 / weight / D3 INTERLEAVED in texts/cedar2023.txt, page 4", quotes)  # a line number inside
        report = (base / "check.md").read_text(encoding="utf-8")
        self.assertIn("- mapping: no mapping registered for this domain: 6 (D2, D3)", report)
        self.assertIn("- cedar2023 / weight", report)

    def test_quotes_must_be_found_in_the_saved_text(self):
        def edit(a):
            domain(a, ALDER, "D1")["support"][0]["quote"] = "the trial pharmacist kept the list in a locked cabinet"
            domain(a, ALDER, "D2")["support"][0]["quote"] = "Of 120 randomised participants, 9 did not attend the closing visit"
            domain(a, BIRCH, "D3")["support"][0]["quote"] = "did not know"
            del domain(a, BIRCH, "D2")["support"][0]["locator"]
            domain(a, CEDAR, "D1")["support"][0]["text"] = "texts/other.txt"
        rows = self.rows(edit)
        self.assertEqual(sorted(self.failed(rows, "quote")), [
            ("alder2021 / weight / D1", "not in the study's texts (ABSENT)"),
            ("alder2021 / weight / D2", "only partly found (PARTIAL): reread the passage and copy it again"),
            ("birch2022 / weight / D2", "no locator: give the page, section, table or figure"),
            ("birch2022 / weight / D3", "3 words: quote at least 5"),
            ("cedar2023 / weight / D1", "names texts/other.txt, which is not a text of this study")])
        # Alder's D1 keeps a second quote that is found; the others have nothing left.
        self.assertEqual([w for w, _ in self.failed(rows, "support")],
                         ["alder2021 / weight / D2", "birch2022 / weight / D2", "birch2022 / weight / D3",
                          "cedar2023 / weight / D1"])

    def test_a_judgement_needs_a_quote_or_a_stated_search(self):
        def no_quote(a):
            del domain(a, ALDER, "D3")["support"]
        self.assertEqual(self.failed(self.rows(no_quote), "support"), [
            ("alder2021 / weight / D3", "no quote passed the quote check and no no_information.searched was given")])

        def search_instead(a):
            no_quote(a)
            domain(a, ALDER, "D3")["no_information"] = {"searched": "Methods and the protocol"}
        self.assertEqual(self.failed(self.rows(search_instead), "support"), [])

        def ni_without_search(a):
            del domain(a, CEDAR, "D2")["no_information"]
        self.assertEqual(self.failed(self.rows(ni_without_search), "support"), [
            ("cedar2023 / weight / D2", "a judgement of no information needs no_information.searched")])

    def test_the_overall_judgement_follows_the_rule(self):
        def overall(study, judgement, reason=""):
            def edit(a):
                a[study]["results"][0]["overall"] = {"judgement": judgement, "reason": reason}
            return edit

        def rule(name):
            def edit(tool):
                tool["overall"]["rule"] = name
            return edit

        cases = [
            (overall(BIRCH, "low"), None, ["better than the worst domain (Some concerns)"]),
            (overall(BIRCH, "high"), None, ["worse than the worst domain (Some concerns): give the reason"]),
            (overall(BIRCH, "high", "two domains with concerns that add up"), None, []),
            (overall(BIRCH, "high", "a reason"), rule("worst"),
             ["worse than the worst domain (Some concerns), which the rule worst does not allow"]),
            (overall(ALDER, "ni", "a reason"), None, ["an overall of no information needs such a domain and a reason"]),
            (overall(CEDAR, "ni", "the missing data could change everything"), None, []),
            (overall(ALDER, "moderate"), None, ["overall 'moderate' is not a ranked judgement of the tool"]),
            (None, rule("none"), ["the tool defines no overall judgement"] * 3),
        ]
        for edit, tool_edit, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual([d for _, d in self.failed(self.rows(edit, tool_edit), "overall")], expected)

        def drop_overall(a):
            for study in a:
                del study["results"][0]["overall"]
        rows = self.rows(drop_overall, rule("none"))
        self.assertEqual([r for r in rows if r["check"] == "overall"], [])

    def test_the_registered_mapping_checks_judgements_against_answers(self):
        def contradict(a):
            domain(a, ALDER, "D1")["answers"]["1b"] = "N"
        self.assertEqual(self.failed(self.rows(contradict), "mapping"), [
            ("alder2021 / weight / D1", "the registered mapping gives High for these answers, not Low")])

        def depart(a):
            contradict(a)
            domain(a, ALDER, "D1")["departs_from_mapping"] = "the guidance allows it when the list was held off site"
        base = self.build(depart)
        code, summary = self.cli("check", "--dir", base)
        self.assertEqual((code, summary["departures"]), (0, 1))
        self.assertIn("alder2021 / weight / D1: the mapping gives High; departs because:",
                      (base / "check.md").read_text(encoding="utf-8"))

        def no_default(tool):
            tool["mapping"]["D1"]["rules"].pop()
        self.assertEqual(self.failed(self.rows(tool_edit=no_default), "mapping"), [
            ("birch2022 / weight / D1", "no rule of the registered mapping matches these answers")])

        def a_choice(tool):
            tool["mapping"]["D1"]["rules"].insert(0, {"if": {"1b": "NI"}, "then": ["some", "high"]})
        self.assertEqual(self.failed(self.rows(tool_edit=a_choice), "mapping"), [])

        def no_mapping(tool):
            del tool["mapping"]
        rows = self.rows(tool_edit=no_mapping)
        self.assertEqual({r["status"] for r in rows if r["check"] == "mapping"}, {"not_checked"})

    def test_the_tool_must_be_registered_from_a_source(self):
        def edit_source(**fields):
            def edit(tool):
                tool["source"].update(fields)
                tool["source"] = {k: v for k, v in tool["source"].items() if v is not None}
            return edit

        def failed_tool(tool_edit):
            rows = self.rows(tool_edit=tool_edit)
            return [d for _, d in self.failed(rows, "tool")], [(r["status"], r["detail"]) for r in rows if r["check"] == "tool_file"]

        self.assertEqual(failed_tool(lambda t: t.pop("version"))[0], ["version is missing"])
        self.assertEqual(failed_tool(edit_source(read="13/11/2026"))[0], ["source.read must be the date read (YYYY-MM-DD)"])
        self.assertEqual(failed_tool(edit_source(file=None, url="https://tool.example.org/form"))[1], [
            ("not_checked", "read from a web page with no saved copy: not comparable with its source")])
        self.assertEqual(failed_tool(edit_source(file=None))[0], ["source needs the file or web address it was read from"])
        self.assertEqual(failed_tool(edit_source(sha256="0" * 64))[1], [
            ("fail", "tool-source/demo-tool.txt changed after it was registered: register the tool again")])
        problems = failed_tool(lambda t: t.update(judgements=t["judgements"][:1] + t["judgements"][3:]))[0]
        self.assertTrue(problems[0].startswith("judgements need unique ids and two ranked levels; mapping D1:"))
        self.assertEqual(failed_tool(lambda t: t["overall"].update(rule="max"))[0],
                         ["overall needs a rule (worst, worst_or_higher, none) and its locator"])
        problems = failed_tool(lambda t: t["mapping"]["D1"]["rules"].insert(0, {"if": {"1c": ["Y"]}, "then": "low"}))[0]
        self.assertEqual(len(problems), 1)
        self.assertIn("mapping D1: ", problems[0])

        rows = self.rows(hashes=False)
        self.assertIn(("fail", "no SHA-256 recorded for tool-source/demo-tool.txt: run hash and record it"),
                      [(r["status"], r["detail"]) for r in rows if r["check"] == "tool_file"])

    def test_several_tools_and_a_study_whose_tool_is_not_registered(self):
        base = self.build(lambda a: a[CEDAR].update(tool="other"))
        tool = json.loads((base / "tool.json").read_text(encoding="utf-8"))
        (base / "tool.json").write_text(json.dumps({"tools": [tool]}), encoding="utf-8")
        rows = rc.run_checks(base)[0]
        self.assertEqual(self.failed(rows, "complete"), [("cedar2023", "tool 'other' is not registered in tool.json")])
        self.assertFalse([r for r in rows if r["where"].startswith("cedar2023 /")])

    def test_texts_keep_their_hash_and_length(self):
        base = self.build()
        with open(base / "texts" / "birch2022.txt", "a", encoding="utf-8") as handle:
            handle.write("A sentence added after the assessment.\n")
        problems = [d for _, d in self.failed(rc.run_checks(base)[0], "text")]
        self.assertEqual(len(problems), 1)
        self.assertIn("changed after its SHA-256 was recorded", problems[0])

        short = {"path": "texts/short.txt", "kind": "full_text"}
        (self.dir / "risk-of-bias" / "texts").mkdir(parents=True, exist_ok=True)
        (self.dir / "risk-of-bias" / "texts" / "short.txt").write_text("A conference abstract of forty words.", encoding="utf-8")
        rows = self.rows(lambda a: a[BIRCH]["texts"].append(dict(short)))
        self.assertIn("6 words is an abstract or a failed extraction", self.failed(rows, "text")[0][1])
        self.assertEqual(self.failed(self.rows(lambda a: a[BIRCH]["texts"].append(dict(short, kind="abstract"))), "text"), [])

        def missing(a):
            a[BIRCH]["texts"] = [{"path": "texts/nowhere.txt", "sha256": "0" * 64}]
        self.assertEqual(self.failed(self.rows(missing), "text"), [
            ("birch2022", "text texts/nowhere.txt is missing"),
            ("birch2022", "no text of this study could be read: save its full text first")])
        self.assertIn("no SHA-256 recorded: run hash and record it", self.failed(self.rows(hashes=False), "text")[0][1])

    def test_every_study_outcome_and_domain_is_complete(self):
        def edit(a):
            del a[ALDER]["results"][0]["domains"]["D2"]
            domain(a, BIRCH, "D1")["answers"].update({"1a": "Maybe", "9z": "Y"})
            domain(a, BIRCH, "D3")["judgement"] = "moderate"
            del a[CEDAR]["results"][0]["target"]
        self.assertEqual(sorted(self.failed(self.rows(edit), "complete")), [
            ("alder2021 / weight / D2", "no judgement for this domain"),
            ("birch2022 / weight / D1", "9z is not a question of D1; 1a: 'Maybe' is not in the answer vocabulary"),
            ("birch2022 / weight / D3", "judgement 'moderate' is not in the vocabulary"),
            ("cedar2023 / weight", "target is missing")])

        def duplicates(a):
            a.append(copy.deepcopy(a[ALDER]))
            a[BIRCH]["results"].append(copy.deepcopy(a[BIRCH]["results"][0]))
        self.assertEqual(sorted(set(self.failed(self.rows(duplicates), "complete"))), [
            ("alder2021", "every study needs its own id, used once"), ("birch2022", "results need one entry per outcome")])

    def test_export_writes_tables_only_after_a_clean_check(self):
        def broken(a):
            domain(a, ALDER, "D1")["judgement"] = "high"
        base = self.build(broken)
        code, summary = self.cli("export", "--dir", base)
        self.assertEqual((code, summary["exported"]), (1, False))
        self.assertFalse((base / "robvis-demo-weight.csv").exists())

        base = self.build()
        code, summary = self.cli("export", "--dir", base)
        self.assertEqual(code, 0)
        self.assertEqual((base / "robvis-demo-weight.csv").read_text(encoding="utf-8"),
                         "Study,D1,D2,D3,Overall,Weight\nalder2021,Low,Low,Low,Low,40.0\n"
                         "birch2022,Some concerns,Low,Low,Some concerns,25.0\ncedar2023,Low,No information,High,High,35.0\n")
        table = (base / "table.md").read_text(encoding="utf-8")
        self.assertIn("| cedar2023 | Low | No information | High | High | model | not yet |", table)
        self.assertIn("D1: Assignment; D2: Missing outcome data; D3: Outcome measurement.", table)
        quotes = (base / "quotes.md").read_text(encoding="utf-8")
        self.assertIn("| birch2022 | D1 | 1a Y; 1b NI | Some concerns | \"Assignment followed a random number table prepared "
                      "before recruitment\" | p. 2 (page 2 of texts/birch2022.txt) | EXACT |", quotes)
        self.assertIn("|  |  |  |  | No information | Searched: Methods, supplementary appendix and the trial registration |  |",
                      quotes)

        base = self.build(lambda a: a[BIRCH]["results"][0].pop("weight"))
        self.cli("export", "--dir", base)
        self.assertTrue((base / "robvis-demo-weight.csv").read_text(encoding="utf-8").startswith("Study,D1,D2,D3,Overall\n"))

    def test_hash_and_unreadable_input(self):
        base = self.build()
        path = base / "texts" / "alder2021.txt"
        code, summary = self.cli("hash", path)
        self.assertEqual((code, summary["sha256"][str(path)]), (0, hashlib.sha256(path.read_bytes()).hexdigest()))
        for argv, broken in ((["hash", base / "none.txt"], None), (["check", "--dir", self.dir / "empty"], None),
                             (["check", "--dir", base], "assessments.json")):
            if broken:
                (base / broken).write_text("{not json", encoding="utf-8")
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                rc.main([str(a) for a in argv])
            self.assertEqual(stop.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
