"""grant_check.py: the record's quotes are in the call, and the proposal, aims, timeline and budget agree."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "grant_check.py"
spec = importlib.util.spec_from_file_location("grant_check", SCRIPT)
gc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gc)

NS = "not_stated"

# An invented call from an invented funder. Page 2 starts at the form feed.
CALL = (
    "The Example Foundation (an invented funder). Discovery Grants, call EF-DISC-07.\n\n"
    "1. What to submit\n"
    "Applicants must submit a Summary of no more than 40 words.\n"
    "The Project description must not exceed 120 words; references and\n"
    "tables do not count towards this limit.\n"
    "An Impact statement is required and is limited to 300 char-\n"
    "acters including spaces. A Data plan may be added.\n"
    "The Work plan is limited to two pages.\n\n"
    "2. Review criteria\n"
    "Proposals are assessed on the importance of the question (40%), on the “feasibility of the plan” (40%)\n"
    "and on value for money – the budget must match the work.\n"
    "\f"
    "3. Budget\n"
    "The total budget may not exceed EUR 50,000 for a project of up to 24 months.\n"
    "Equipment items above EUR 5,000 are not eligible.\n\n"
    "4. Deadline and other rules\n"
    "Proposals must arrive by 17:00 on 1 March 2032. The applicant must hold a doctorate.\n"
    "Applicants must declare any use of generative AI tools.\n"
    "A letter of support from the host institution must be attached.\n"
)

RECORD = {
    "call": {"identifier": "EF-DISC-07", "funder": "The Example Foundation (invented)", "mechanism": "Discovery Grant",
             "source": "grant/call.txt", "date_read": "2026-11-12"},
    "sections": [
        {"name": "Summary", "required": True, "limit": {"value": 40, "unit": "words", "counts": NS},
         "quote": "Applicants must submit a Summary of no more than 40 words.", "locator": "section 1"},
        {"name": "Project description", "required": True,
         "limit": {"value": 120, "unit": "words", "counts": {"references": "excluded", "tables": "excluded"}},
         "quote": "The Project description must not exceed 120 words; references and tables do not count towards this limit.",
         "locator": "section 1"},
        {"name": "Impact statement", "required": True,
         "limit": {"value": 300, "unit": "characters", "counts": {"spaces": "included"},
                   "quote": "LIMITED to 300 characters   including spaces"},
         "quote": "An Impact statement is required", "locator": "section 1"},
        {"name": "Work plan", "required": True, "limit": {"value": 2, "unit": "pages"},
         "quote": "The Work plan is limited to two pages.", "locator": "section 1"},
        {"name": "Data plan", "required": False, "limit": NS, "quote": "A Data plan may be added.", "locator": "section 1"},
    ],
    "total_limit": NS,
    "criteria": [
        {"name": "Importance of the question", "weight": "40%", "quote": "assessed on the importance of the question (40%)",
         "locator": "section 2"},
        {"name": "Feasibility of the plan", "weight": "40%", "quote": "on the \"feasibility of the plan\" (40%)",
         "locator": "section 2"},
        {"name": "Value for money", "weight": NS, "quote": "value for money - the budget must match the work",
         "locator": "section 2"},
    ],
    "budget": {
        "cap": {"value": 50000, "quote": "The total budget may not exceed EUR 50,000", "locator": "section 3"},
        "currency": "EUR",
        "period": {"months": 24, "quote": "a project of up to 24 months", "locator": "section 3"},
        "rules": [{"rule": "No equipment item above EUR 5,000.", "quote": "Equipment items above EUR 5,000 are not eligible.",
                   "locator": "section 3"}],
    },
    "deadline": {"value": "1 March 2032, 17:00.", "quote": "Proposals must arrive by 17:00 on 1 March 2032.", "locator": "section 4"},
    "eligibility": {"value": "The applicant holds a doctorate.", "quote": "The applicant must hold a doctorate.", "locator": "section 4"},
    "formatting": NS,
    "ai_policy": {"value": "Use of generative AI tools must be declared.",
                  "quote": "Applicants must declare any use of generative AI tools.", "locator": "section 4"},
    "attachments": [{"name": "Letter of support", "required": True,
                     "quote": "A letter of support from the host institution must be attached.", "locator": "section 4"}],
}

PROPOSAL = """# Tracing plastic fragments in one river

## 1. Summary

We will measure how plastic fragments move through one river and test whether the bed traps them.
<!-- these ten words sit in a comment and are never counted -->

## 2. PROJECT DESCRIPTION (max. 120 words)

Rivers carry plastic fragments to the sea, but how much the river bed retains is not known.

### Aim 1

We will sample water at six sites each month.

| Site | Depth |
|---|---|
| Upper | 2 m |

### References

1. An invented reference, here only to be counted as a reference.

## Impact statement

Water managers will learn where fragments settle.

## Work plan

Sampling runs in year one and analysis in year two.
"""

AIMS = {"aims": [
    {"id": "A1", "title": "Measure transport", "learned": "How far fragments travel, whether or not the bed retains them.",
     "success_criterion": "Monthly counts at six sites for twelve months.", "depends_on": [], "fallback": "",
     "risk": "Floods prevent sampling.", "alternative": "Sample from bridges.", "milestones": ["M1"], "budget_lines": ["B1"]},
    {"id": "A2", "title": "Test retention", "learned": "Whether the bed is a sink, a source or neither.",
     "success_criterion": "A retention estimate with its interval.", "depends_on": ["A1"],
     "fallback": "Use transport rates from the pilot season.", "risk": "Cores disturb the bed.",
     "alternative": "Use sediment traps.", "milestones": ["M2"], "budget_lines": ["B2"]},
]}
TIMELINE = ("milestone,aim,start_month,end_month,description\n"
            "M1,A1,1,12,Sampling complete\nM2,A2,10,24,Retention estimate\nM3,project,24,24,Final report\n")
BUDGET = ("line,category,year,amount,aim,quantity,unit_cost\n"
          "B1,consumables,1,12000,A1,12,1000\nB2,personnel,2,30000,A2,,\nB3,travel,1,2500,project,,\n")
CRITERIA = """# Review against the call's criteria

| Criterion | Where addressed | Evidence | Weakness | Revision |
|---|---|---|---|---|
| Importance of the question | Project description | Gap paragraph | No figure for the size of the problem | Add the user's figure |
| Feasibility of the plan | Work plan; Project description | Timeline | None found | |
| Value for money | Work plan | Budget table | Travel is not tied to an aim | Justify it |
"""


def make_pdf(path: Path, pages: int) -> Path:
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % (3 + i) for i in range(pages)) + b"] /Count %d >>" % pages]
    objects += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>"] * pages
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, start)
    path.write_bytes(bytes(out))
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "grant"
        self.dir.mkdir()
        self.record = copy.deepcopy(RECORD)
        self.aims = copy.deepcopy(AIMS)
        for name, content in (("call.txt", CALL), ("proposal.md", PROPOSAL), ("timeline.csv", TIMELINE),
                              ("budget.csv", BUDGET), ("criteria.md", CRITERIA)):
            self.put(name, content)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name: str, content) -> Path:
        path = self.dir / name
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return path

    def run_cli(self, command: str, *argv):
        self.put("requirements.json", self.record)
        self.put("aims.json", self.aims) if self.aims is not None else None
        out, self.err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(self.err):
            code = gc.main([command, "--dir", str(self.dir), *[str(a) for a in argv]])
        return code, json.loads(out.getvalue())

    def bad_input(self, command: str, *argv) -> str:
        with self.assertRaises(SystemExit) as caught:
            self.run_cli(command, *argv)
        self.assertEqual(caught.exception.code, 2)
        return self.err.getvalue()

    def call(self):
        return self.run_cli("call", self.dir / "call.txt")

    def check(self, *argv):
        code, summary = self.run_cli("check", self.dir / "proposal.md", *argv)
        return code, summary, self.rows("report.md")

    def budget(self, *argv):
        code, summary = self.run_cli("budget", self.dir / "budget.csv", *argv)
        return code, summary, self.rows("budget-check.md")

    def rows(self, name: str) -> dict:
        """{(check, subject): (state, detail)} from the first table of a report."""
        found = {}
        for line in (self.dir / name).read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if line.startswith("| ") and len(cells) >= 4 and cells[2] in gc.STATES:
                found[(cells[0], cells[1])] = (cells[2], cells[3])
        return found


class CallTests(Base):
    def test_every_quote_is_found_despite_case_spacing_hyphenation_quotes_and_dashes(self):
        code, out = self.call()
        self.assertEqual((code, out["ok"], out["quote_not_found"], out["no_quote"], out["value_not_in_quote"]),
                         (0, True, [], [], []))
        self.assertEqual(out["not_stated"], ["limit: Data plan", "total_limit", "weight: Value for money", "formatting"])
        self.assertEqual(out["entries"], out["quote_found"] + len(out["not_stated"]))
        report = (self.dir / "call-check.md").read_text(encoding="utf-8")
        self.assertIn("Call: EF-DISC-07, The Example Foundation (invented), Discovery Grant. Source: grant/call.txt, "
                      "read 2026-11-12.", report)
        self.assertIn("| limit: Impact statement | 300 characters | quote_found | section 1 | 1 |", report)   # "char-\nacters"
        self.assertIn("| budget.cap | 50,000 EUR | quote_found | section 3 | 2 |", report)                    # after the form feed
        self.assertIn("| limit: Work plan | 2 pages | quote_found |", report)                                  # "two pages" holds 2
        self.assertIn("| formatting |  | not_stated |", report)

    def test_a_quote_that_is_not_in_the_call_fails(self):
        self.record["criteria"][0]["quote"] = "assessed on the originality of the question (40%)"
        self.record["deadline"]["quote"] = "Proposals must arrive ... on 1 March 2032."
        code, out = self.call()
        self.assertEqual((code, out["ok"]), (1, False))
        self.assertEqual(out["quote_not_found"], ["criterion: Importance of the question", "deadline"])
        report = (self.dir / "call-check.md").read_text(encoding="utf-8")
        self.assertIn("a quote is continuous, with no ellipsis", report)
        self.assertIn("Result: failed.", report)

    def test_a_limit_a_cap_or_a_period_without_a_quote_fails(self):
        for change in ("limit", "cap", "period"):
            with self.subTest(change):
                self.record = copy.deepcopy(RECORD)
                if change == "limit":           # neither the limit nor its section has a quote
                    self.record["sections"][0]["quote"] = ""
                    expected = ["section: Summary", "limit: Summary"]
                else:
                    del self.record["budget"][change]["quote"]
                    expected = [f"budget.{change}"]
                code, out = self.call()
                self.assertEqual((code, out["no_quote"], out["limits_without_quote"]), (1, expected, expected[-1:]))

    def test_an_entry_without_a_quote_is_listed_and_a_short_quote_counts_as_none(self):
        self.record["criteria"][2]["quote"] = ""
        self.record["attachments"][0]["quote"] = "letter"
        code, out = self.call()
        self.assertEqual((code, out["no_quote"], out["quote_too_short"]),
                         (0, ["criterion: Value for money"], ["attachment: Letter of support"]))
        self.record["budget"]["cap"]["quote"] = "EUR 50,000"                      # two words, on a number that must be backed
        code, out = self.call()
        self.assertEqual((code, out["limits_without_quote"]), (1, ["budget.cap"]))

    def test_a_value_that_its_quote_does_not_contain_is_flagged(self):
        self.record["sections"][0]["limit"]["value"] = 400                        # the call says 40
        self.record["budget"]["cap"]["value"] = 55000
        code, out = self.call()
        self.assertEqual((code, out["value_not_in_quote"]), (0, ["limit: Summary", "budget.cap"]))
        self.assertIn("The value 55,000 is not in the quote", (self.dir / "call-check.md").read_text(encoding="utf-8"))

    def test_silence_is_written_down_and_the_format_is_enforced(self):
        del self.record["formatting"]
        self.assertIn('formatting is missing (write "not_stated" when the call is silent)', self.bad_input("call", self.dir / "call.txt"))
        self.record = copy.deepcopy(RECORD)
        self.record["call"]["date_read"] = "last week"
        self.record["sections"][0]["limit"]["unit"] = "lines"
        self.record["sections"][1]["limit"]["counts"] = {"references": "no"}
        self.record["budget"]["cap"] = {"value": "50,000"}
        del self.record["sections"][4]["limit"]
        message = self.bad_input("call", self.dir / "call.txt")
        for part in ("call.date_read must be the date", "sections[Summary].limit.unit must be one of words, characters, pages",
                     "sections[Project description].limit.counts must be", "budget.cap must be",
                     "sections[Data plan].limit is missing"):
            self.assertIn(part, message)

    def test_whole_blocks_the_call_is_silent_on(self):
        self.record.update({"sections": NS, "criteria": NS, "attachments": NS, "budget": NS})
        self.record["call"]["identifier"] = NS
        code, out = self.call()
        self.assertEqual(code, 0)
        self.assertEqual(out["not_stated"], ["call.identifier", "sections", "criteria", "attachments", "budget",
                                             "total_limit", "formatting"])

    def test_unreadable_inputs_stop_with_a_message(self):
        pdf = make_pdf(self.dir / "call.pdf", 1)
        self.assertIn("is a PDF. Turn it into text first", self.bad_input("call", pdf))
        self.assertIn("no such file", self.bad_input("call", self.dir / "missing.txt"))
        (self.dir / "requirements.json").unlink()
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()) as err:
            gc.main(["call", "--dir", str(self.dir), str(self.dir / "call.txt")])
        self.assertIn("structure and limits come from the call", err.getvalue())


class TextTests(unittest.TestCase):
    def test_quote_normalisation(self):
        self.assertEqual(gc.norm_quote("The “Well-\n  Known” plan — a co-operative\u00a0one"),
                         gc.norm_quote("the 'wellknown' plan - a cooperative one"))
        self.assertEqual(gc.norm_quote("| **Summary** | 250 words |"), "summary 250 words")
        self.assertNotEqual(gc.norm_quote("must not exceed"), gc.norm_quote("must exceed"))

    def test_numbers(self):
        for text, value in (("12,000", 12000), ("12 000", 12000), ("12.000,50", 12000.5), ("12'000", 12000), ("1.5k", 1500),
                            ("2 million", 2e6), ("0.125", 0.125), ("1,5", 1.5), ("37.5", 37.5), ("abc", None), ("", None)):
            self.assertEqual(gc.parse_number(text), value, text)
        self.assertEqual(gc.numbers_in("no more than two pages in 11-point type, up to EUR 1,500"), {2.0, 11.0, 1500.0})

    def test_names_match_despite_numbering_case_and_brackets(self):
        for written in ("2. PROJECT DESCRIPTION (max. 120 words)", "Section 2: Project description", "B2 – **Project Description**",
                        "II. Project description", "2.1 Project description"):
            self.assertEqual(gc.norm_name(written), "project description", written)
        self.assertEqual(gc.norm_name("Impact & outreach"), "impact and outreach")
        self.assertNotEqual(gc.norm_name("Project summary"), gc.norm_name("Summary"))

    def test_counting(self):
        self.assertEqual(gc.count("Three plain words, and a number: 42 – done.", "words"), 8)
        self.assertEqual(gc.count("我们研究 plastic", "words"), 5)            # four Han characters and a word
        self.assertEqual((gc.count("a  b\nc", "characters"), gc.count("a  b\nc", "characters", spaces=False)), (5, 3))
        self.assertEqual(gc.count(gc.plain("## Head\n\n- **Bold** [link](http://x.org) `code`"), "words"), 4)

    def limit(self, body: str, **limit):
        return gc.limit_state(gc.split_parts(body.splitlines()), limit)

    def test_a_limit_counts_what_the_record_says_it_counts(self):
        body = ("One two three four five.\n\n| a | b |\n|---|---|\n| six | seven |\n\nTable 1. Eight nine.\n\n"
                "![ten eleven](fig.png)\n\nFigure 1. Twelve thirteen.\n\n### References\n\n1. Fourteen fifteen sixteen.\n")
        every = {"references": "included", "tables": "included", "figure_captions": "included"}
        state, detail = self.limit(body, value=20, unit="words", counts=every)
        self.assertEqual(state, "fail")
        self.assertIn("23 words, over the limit of 20. Counted: main text 5; references counted (4); tables counted (8); "
                      "figure captions counted (6).", detail)
        state, detail = self.limit(body, value=5, unit="words",
                                   counts={"references": "excluded", "tables": "excluded", "figure_captions": "excluded"})
        self.assertEqual(state, "pass")
        self.assertIn("5 words, limit 5. Counted: main text 5; references left out (4); tables left out (8)", detail)

    def test_a_limit_the_record_does_not_settle_is_counted_both_ways(self):
        body = "One two three four five.\n\n### References\n\n1. Six seven eight.\n"
        state, detail = self.limit(body, value=7, unit="words", counts=NS)
        self.assertEqual(state, "not_checked")
        self.assertIn("5 to 9 words depending on whether references count, which the record does not state; limit 7.", detail)
        self.assertEqual(self.limit(body, value=9, unit="words")[0], "pass")               # under the limit either way
        state, detail = self.limit(body, value=4, unit="words")
        self.assertEqual((state, "5 to 9 words, over the limit of 4." in detail), ("fail", True))   # over it either way

    def test_characters_with_and_without_spaces(self):
        body = "abc def ghi"                                                                # 11 with spaces, 9 without
        self.assertEqual(self.limit(body, value=10, unit="characters", counts={"spaces": "included"})[0], "fail")
        self.assertEqual(self.limit(body, value=10, unit="characters", counts={"spaces": "excluded"})[0], "pass")
        state, detail = self.limit(body, value=10, unit="characters")
        self.assertEqual(state, "not_checked")
        self.assertIn("9 to 11 characters depending on whether spaces count", detail)


class CheckTests(Base):
    def test_a_coherent_proposal_passes_and_says_what_was_not_checked(self):
        self.call()
        code, out, rows = self.check()
        self.assertEqual((code, out["ok"], out["failed"]), (0, True, []))
        self.assertEqual(rows[("record_verified", "requirements.json")][0], "pass")
        self.assertEqual(rows[("section_present", "Project description")], ("pass", 'Heading "2. PROJECT DESCRIPTION (max. 120 words)".'))
        self.assertEqual(rows[("section_limit", "Summary")][0], "pass")
        self.assertIn("17 words, limit 40. Counted: main text 17.", rows[("section_limit", "Summary")][1])  # no heading, no comment
        self.assertIn("main text 28; references left out (12); tables left out (5)", rows[("section_limit", "Project description")][1])
        self.assertEqual(rows[("section_limit", "Impact statement")][0], "pass")
        self.assertEqual(rows[("section_limit", "Work plan")][0], "not_checked")            # a page limit on one section
        self.assertEqual(rows[("total_limit", "whole proposal")][0], NS)
        self.assertEqual(rows[("no_open_placeholders", "proposal")][0], "pass")
        self.assertEqual(rows[("criterion_mapped", "Feasibility of the plan")], ("pass", "Addressed in: Work plan; Project description."))
        self.assertEqual(rows[("criteria_from_the_call", "criteria.md")][0], "pass")
        self.assertEqual(rows[("aim_fields", "A1")][0], "pass")
        self.assertNotIn(("aim_fallback", "A1"), rows)                                      # A1 depends on nothing
        self.assertEqual(rows[("aim_fallback", "A2")], ("pass", "Depends on the result of A1; a fallback is stated."))
        self.assertEqual((rows[("aim_milestone", "A1")], rows[("aim_budget_line", "A2")]), (("pass", "M1."), ("pass", "B2.")))
        self.assertEqual((rows[("timeline_aims", "timeline.csv")][0], rows[("budget_aims", "budget.csv")][0]), ("pass", "pass"))
        self.assertEqual(rows[("milestones_in_period", "timeline.csv")], ("pass", "All 3 milestones fall within months 1 to 24."))
        self.assertEqual(rows[("call_rule", "eligibility")][0], "not_checked")
        self.assertEqual(rows[("call_rule", "formatting")][0], NS)
        self.assertEqual(rows[("call_rule", "attachment: Letter of support")][0], "not_checked")
        self.assertEqual(out["optional_sections_left_out"], ["Data plan"])
        self.assertEqual(out["counts"]["not_checked"], len(out["not_checked"]))
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("read 2026-11-12", report)
        self.assertIn("Optional sections not in the proposal: Data plan.", report)

    def test_the_record_must_have_been_compared_with_the_call(self):
        self.assertEqual(self.check()[2][("record_verified", "requirements.json")][0], "not_checked")     # call never run
        self.call()
        self.record["sections"][0]["limit"]["value"] = 45                                                 # edited afterwards
        _, _, rows = self.check()
        self.assertEqual(rows[("record_verified", "requirements.json")],
                         ("not_checked", "requirements.json changed after the last call check: run the call command again."))
        self.record["sections"][0]["quote"] = "A summary of any length is welcome."
        self.call()
        code, out, rows = self.check()
        self.assertEqual((code, rows[("record_verified", "requirements.json")][0]), (1, "fail"))

    def test_missing_sections_and_sections_over_their_limit_fail(self):
        text = PROPOSAL.replace("## Impact statement", "## Benefits").replace(
            "the bed traps them.", "the bed traps them. " + "More words than the call allows. " * 5)
        self.put("proposal.md", text)
        self.record["sections"][4]["required"] = NS
        code, out, rows = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(rows[("section_present", "Impact statement")], ("fail", "Required by the call; no heading with this name."))
        self.assertNotIn(("section_limit", "Impact statement"), rows)
        self.assertEqual(rows[("section_present", "Data plan")][0], NS)
        self.assertEqual(rows[("section_limit", "Summary")][0], "fail")
        self.assertIn("47 words, over the limit of 40.", rows[("section_limit", "Summary")][1])
        self.assertEqual(out["failed"], ["section_limit: Summary", "section_present: Impact statement"])
        self.assertEqual(out["headings_not_in_record"], ["Benefits"])

    def test_a_call_that_prescribes_no_sections_or_criteria(self):
        self.record.update({"sections": NS, "criteria": NS})
        code, _, rows = self.check()
        self.assertEqual((code, rows[("sections", "proposal")][0], rows[("criterion_mapped", "criteria")][0]), (0, NS, NS))

    def test_placeholders_are_listed_with_their_sections_and_block_a_final_run(self):
        text = PROPOSAL.replace("Water managers will learn", "[Evidence needed: pilot counts] Water managers will learn").replace(
            "Sampling runs", "[Author input needed: start date] [citation needed: flood frequency]\nSampling runs").replace(
            "at six sites each month.", "at six sites each month. [Evidence needed: aim data]")
        self.put("proposal.md", text)
        code, out, rows = self.check()
        self.assertEqual((code, out["placeholders"], rows[("no_open_placeholders", "proposal")][0]), (0, 4, "not_checked"))
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("| Impact statement | [Evidence needed: pilot counts] |", report)
        self.assertIn("| Work plan | [citation needed: flood frequency] |", report)
        self.assertIn("| 2. PROJECT DESCRIPTION (max. 120 words) > Aim 1 | [Evidence needed: aim data] |", report)
        code, out, rows = self.check("--final")
        self.assertEqual((code, out["final"], out["failed"]), (1, True, ["no_open_placeholders: proposal"]))
        self.assertIn("Run: final.", (self.dir / "report.md").read_text(encoding="utf-8"))

    def test_every_criterion_of_the_call_is_mapped_to_a_section_that_exists(self):
        self.put("criteria.md", CRITERIA.replace("| Project description | Gap", "| Background | Gap")
                 .replace("| Feasibility of the plan | Work plan; Project description |", "| Feasibility of the plan | |")
                 .replace("| Value for money |", "| Track record of the team |"))
        code, _, rows = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(rows[("criterion_mapped", "Importance of the question")],
                         ("fail", "Names a section that is not a heading of the proposal: Background."))
        self.assertEqual(rows[("criterion_mapped", "Feasibility of the plan")], ("fail", '"Where addressed" is empty.'))
        self.assertEqual(rows[("criterion_mapped", "Value for money")], ("fail", "No row for this criterion in criteria.md."))
        self.assertEqual(rows[("criteria_from_the_call", "criteria.md")],
                         ("fail", "Rows for criteria that are not in the record: Track record of the team."))
        self.put("criteria.md", "Importance: see the description.\n")
        self.assertIn("No table whose header starts with", self.check()[2][("criterion_mapped", "criteria.md")][1])
        (self.dir / "criteria.md").unlink()
        code, _, rows = self.check()
        self.assertEqual((code, rows[("criterion_mapped", "criteria.md")][0]), (0, "not_checked"))

    def test_an_aim_needs_a_success_criterion_a_risk_and_an_alternative(self):
        self.aims["aims"][0].update({"success_criterion": "", "risk": "[Author input needed: main risk]"})
        del self.aims["aims"][0]["alternative"]
        code, _, rows = self.check()
        self.assertEqual((code, rows[("aim_fields", "A1")]), (1, ("fail", "Missing: a success criterion, a risk, an alternative.")))
        self.assertEqual(rows[("aim_fields", "A2")][0], "pass")

    def test_an_aim_that_depends_on_another_needs_a_fallback(self):
        self.aims["aims"][1]["fallback"] = " "
        code, _, rows = self.check()
        self.assertEqual((code, rows[("aim_fallback", "A2")]), (1, ("fail", "Depends on the result of A1 but states no fallback.")))
        self.aims["aims"][1].update({"fallback": "Use pilot rates.", "depends_on": ["A7"]})
        self.assertEqual(self.check()[2][("aim_fallback", "A2")], ("fail", "depends_on names A7, which is not another aim."))

    def test_aims_milestones_and_budget_lines_have_no_orphans_on_either_side(self):
        self.aims["aims"].append({"id": "A3", "title": "Model", "learned": "x", "success_criterion": "x", "risk": "x",
                                  "alternative": "x", "milestones": ["M9"], "budget_lines": []})
        self.put("timeline.csv", TIMELINE + "M4,A8,3,4,Stray\nM5,,5,6,No aim\nM6,A1,2,3,Unlisted\n")
        self.put("budget.csv", BUDGET + "B4,equipment,1,900,A9,,\nB5,fees,1,100,,,\nTotal,,,45500,,,\n")
        code, _, rows = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(rows[("aim_milestone", "A3")], ("fail", "No milestone in timeline.csv names this aim; aims.json lists M9, "
                                                                 "which timeline.csv does not have."))
        self.assertEqual(rows[("aim_budget_line", "A3")], ("fail", "No budget line in budget.csv names this aim."))
        self.assertEqual(rows[("aim_milestone", "A1")], ("fail", "M6 names this aim in timeline.csv but aims.json does not list it."))
        self.assertEqual(rows[("timeline_aims", "timeline.csv")], ("fail", "M4 (aim A8 does not exist); M5 (no aim)."))
        self.assertEqual(rows[("budget_aims", "budget.csv")], ("fail", "B4 (aim A9 does not exist); B5 (no aim)."))   # the total row is no line
        self.aims["aims"][2].update({"milestones": ["M1"], "budget_lines": ["B1"]})
        self.assertIn("M1 is listed in aims.json but names another aim in timeline.csv", self.check()[2][("aim_milestone", "A3")][1])

    def test_milestones_fall_inside_the_period_the_call_states(self):
        self.put("timeline.csv", TIMELINE.replace("M2,A2,10,24", "M2,A2,10,27").replace("M3,project,24,24", "M3,project,9,3"))
        code, _, rows = self.check()
        self.assertEqual((code, rows[("milestones_in_period", "timeline.csv")]),
                         (1, ("fail", "M2 ends in month 27, after the 24-month period; M3: months 9 to 3 are not a period.")))
        self.put("timeline.csv", TIMELINE.replace("M1,A1,1,12", "M1,A1,Q1,Q4"))
        self.assertIn("M1: start_month and end_month must be whole project months", self.check()[2][("milestones_in_period", "timeline.csv")][1])
        self.put("timeline.csv", TIMELINE.replace("M2,A2,10,24", "M2,A2,10,60"))
        self.record["budget"]["period"] = NS
        code, _, rows = self.check()
        self.assertEqual((code, rows[("milestones_in_period", "timeline.csv")][0]), (0, NS))

    def test_missing_project_files_are_not_checked_and_broken_ones_stop(self):
        (self.dir / "timeline.csv").unlink()
        code, _, rows = self.check()
        self.assertEqual((code, rows[("aim_milestone", "A1")], rows[("milestones_in_period", "timeline.csv")][0]),
                         (0, ("not_checked", "timeline.csv not found."), "not_checked"))
        self.assertEqual(rows[("aim_budget_line", "A1")][0], "pass")
        self.aims = None
        (self.dir / "aims.json").unlink()
        code, _, rows = self.check()
        self.assertEqual((code, rows[("aims", "aims.json")][0]), (0, "not_checked"))
        self.aims = {"aims": [{"id": "A1"}, {"id": "A1"}]}
        self.assertIn("two aims share an id", self.bad_input("check", self.dir / "proposal.md"))
        self.aims = {"aims": []}
        self.assertIn('must hold a non-empty list "aims"', self.bad_input("check", self.dir / "proposal.md"))
        self.aims = copy.deepcopy(AIMS)
        self.put("budget.csv", "line,category,amount\nB1,travel,10\n")
        self.assertIn("lacks the column(s) year, aim", self.bad_input("check", self.dir / "proposal.md"))

    def test_a_folder_of_section_files(self):
        folder = self.dir / "sections"
        folder.mkdir()
        (folder / "01-summary.md").write_text("We will measure how fragments move.\n", encoding="utf-8")       # no heading
        (folder / "02_project-description.md").write_text("Rivers carry fragments.\n", encoding="utf-8")
        (folder / "03-rest.md").write_text("## Impact statement\n\nManagers learn.\n\n## Work plan\n\nTwo years.\n", encoding="utf-8")
        (folder / "report.md").write_text("## Data plan\n\nA report of an earlier run is not a section.\n", encoding="utf-8")
        code, out = self.run_cli("check", folder)
        rows = self.rows("report.md")
        self.assertEqual((code, rows[("section_present", "Summary")], rows[("section_present", "Project description")][0]),
                         (0, ("pass", 'Heading "summary".'), "pass"))
        self.assertEqual(out["optional_sections_left_out"], ["Data plan"])
        empty = self.dir / "empty"
        empty.mkdir()
        self.assertIn("no .md section files", self.bad_input("check", empty))

    def test_a_total_limit_in_words(self):
        self.record["total_limit"] = {"value": 50, "unit": "words", "counts": {"references": "excluded", "tables": "excluded"},
                                      "quote": "The Work plan is limited to two pages."}
        code, _, rows = self.check()
        self.assertEqual((code, rows[("total_limit", "whole proposal")][0]), (1, "fail"))
        self.assertIn("words, over the limit of 50.", rows[("total_limit", "whole proposal")][1])

    def test_a_page_limit_is_not_checked_without_a_pdf(self):
        self.record["total_limit"] = {"value": 3, "unit": "pages", "counts": {"references": "included", "tables": "included",
                                                                             "figure_captions": "included"}}
        code, _, rows = self.check()
        self.assertEqual((code, rows[("total_limit", "whole proposal")]), (0, ("not_checked", "Limit 3 pages; no PDF was given (--pdf).")))
        pdf = make_pdf(self.dir / "proposal.pdf", 4)
        with mock.patch.object(gc.shutil, "which", return_value=None):           # the tool is missing: its own message
            code, _, rows = self.check("--pdf", pdf)
        self.assertEqual((code, rows[("total_limit", "whole proposal")]),
                         (0, ("not_checked", "Limit 3 pages; pdfinfo (poppler) is not installed, so the PDF's pages were not counted.")))
        self.assertIn("no such file", self.bad_input("check", self.dir / "proposal.md", "--pdf", self.dir / "none.pdf"))

    @unittest.skipUnless(shutil.which("pdfinfo"), "pdfinfo (poppler) is not installed")
    def test_the_total_page_limit_is_checked_on_the_pdf(self):
        every = {"references": "included", "tables": "included", "figure_captions": "included"}
        self.record["total_limit"] = {"value": 3, "unit": "pages", "counts": every}
        code, _, rows = self.check("--pdf", make_pdf(self.dir / "long.pdf", 4))
        self.assertEqual((code, rows[("total_limit", "whole proposal")]), (1, ("fail", "4 pages in the PDF, over the limit of 3.")))
        code, _, rows = self.check("--pdf", make_pdf(self.dir / "short.pdf", 3))
        self.assertEqual((code, rows[("total_limit", "whole proposal")]), (0, ("pass", "3 pages in the PDF, limit 3.")))
        self.record["total_limit"]["counts"] = {**every, "references": "excluded"}    # over, but references do not count
        code, _, rows = self.check("--pdf", self.dir / "long.pdf")
        self.assertEqual((code, rows[("total_limit", "whole proposal")][0]), (0, "not_checked"))
        self.assertIn("does not count references as certainly included", rows[("total_limit", "whole proposal")][1])
        self.record["total_limit"] = NS
        self.assertIn("The PDF has 4 pages.", self.check("--pdf", self.dir / "long.pdf")[2][("total_limit", "whole proposal")][1])


class BudgetTests(Base):
    def test_sums_by_year_and_category_and_the_cap(self):
        code, out, rows = self.budget()
        self.assertEqual((code, out["ok"], out["lines"], out["total"], out["cap"], out["currency"]), (0, True, 3, 44500.0, 50000, "EUR"))
        self.assertEqual(out["by_year"], {"1": 14500.0, "2": 30000.0})
        self.assertEqual(out["by_category"], {"consumables": 12000.0, "personnel": 30000.0, "travel": 2500.0})
        self.assertEqual(rows[("total_against_cap", "budget.csv")], ("pass", "Total 44,500 EUR, within the cap of 50,000."))
        self.assertEqual(rows[("quantity_x_unit_cost", "budget.csv")],
                         ("pass", "All 1 lines with a quantity and a unit cost multiply to their amount."))
        self.assertEqual(rows[("lines_without_aim", "budget.csv")][0], "pass")                  # "project" is an aim
        self.assertEqual(rows[("amounts_in_text", "proposal")], ("not_checked", "No proposal was given (--proposal)."))
        self.assertEqual(rows[("budget_rule", "rule 1")][0], "not_checked")
        report = (self.dir / "budget-check.md").read_text(encoding="utf-8")
        self.assertIn("| 1 | 14,500 |", report)
        self.assertIn("| personnel | 30,000 |", report)
        self.assertIn("Total: 44,500 EUR", report)
        self.assertIn("No rate, overhead or salary is computed.", report)

    def test_over_the_cap_and_a_call_without_a_cap(self):
        self.put("budget.csv", BUDGET + "B4,equipment,2,5500.50,A2,,\n")
        code, out, rows = self.budget()
        self.assertEqual((code, rows[("total_against_cap", "budget.csv")]),
                         (1, ("fail", "Total 50,000.50 EUR, over the cap of 50,000.")))
        self.record["budget"]["cap"] = NS
        code, out, rows = self.budget()
        self.assertEqual((code, out["cap"], rows[("total_against_cap", "budget.csv")]),
                         (0, NS, (NS, "The call states no budget cap. Total 50,000.50 EUR.")))
        self.record["budget"] = NS
        code, out, rows = self.budget()
        self.assertEqual((code, out["currency"], rows[("total_against_cap", "budget.csv")][1], rows[("budget_rule", "rules")][0]),
                         (0, NS, "The call states no budget cap. Total 50,000.50.", NS))

    def test_quantity_times_unit_cost_and_stated_totals(self):
        self.put("budget.csv", "line,category,year,amount,aim,quantity,unit_cost\n"
                               "B1,consumables,1,12500,A1,12,1000\n"          # 12 x 1000 is 12,000
                               "B2,travel,1,1000,A1,3,333.33\n"               # 999.99: rounding
                               "B3,personnel,2,30000,A2,,\n"
                               "Total,,1,13000,,,\n"                          # year 1 adds up to 13,500
                               "Total,,,43500,,,\n")
        code, out, rows = self.budget()
        self.assertEqual((code, out["total"], out["lines"]), (1, 43500.0, 3))                   # total rows are not lines
        self.assertEqual(rows[("quantity_x_unit_cost", "B1")], ("fail", "12 × 1,000 = 12,000; the table says 12,500."))
        self.assertNotIn(("quantity_x_unit_cost", "B2"), rows)
        self.assertEqual(rows[("stated_total", "Total (year 1)")], ("fail", "The lines add up to 13,500; the table says 13,000."))
        self.assertEqual(rows[("stated_total", "Total (all years)")][0], "pass")
        self.assertEqual(out["failed"], ["quantity_x_unit_cost: B1", "stated_total: Total (year 1)"])
        self.put("budget.csv", "line,category,year,amount,aim\nB1,travel,1,100,A1\n")
        self.assertEqual(self.budget()[2][("quantity_x_unit_cost", "budget.csv")],
                         ("not_checked", "No line gives both quantity and unit_cost."))

    def test_a_line_without_an_aim_and_an_amount_that_is_not_a_number(self):
        self.put("budget.csv", BUDGET + "B4,fees,1,about 300,A1,,\nB5,equipment,2,900,,,\n,software,2,100,,,\n")
        code, out, rows = self.budget()
        self.assertEqual(code, 1)
        self.assertEqual(rows[("amounts_numeric", "budget.csv")], ("fail", "Not a number: the amount of B4."))
        self.assertEqual(rows[("lines_without_aim", "budget.csv")],
                         ("fail", "No aim: B5, row 7. Name the aim the cost serves, or project."))
        self.assertEqual(out["total"], 45500.0)

    def test_amounts_in_the_text_must_be_in_the_table_or_its_sums(self):
        text = PROPOSAL + ("\n## Budget justification\n\nSampling consumables cost EUR 12,000 (12 months at €1,000). Year 1 comes to "
                           "14 500 EUR and personnel to EUR 30k. The total is EUR 44,500, under the cap of EUR 50,000; no item "
                           "is above EUR 5,000. We sample 12,000 litres at 6 sites in 2032.\n")
        proposal = self.put("proposal.md", text)
        code, _, rows = self.budget("--proposal", proposal)
        self.assertEqual((code, rows[("amounts_in_text", str(proposal))]),
                         (0, ("pass", "All 7 amounts in the text are lines or sums of the table, or figures of the call.")))
        self.put("proposal.md", text.replace("The total is EUR 44,500", "The total is EUR 45,400").replace("€1,000", "€1,100"))
        code, _, rows = self.budget("--proposal", proposal)
        self.assertEqual((code, rows[("amounts_in_text", str(proposal))]),
                         (1, ("fail", "Not a line or a sum of the table, nor a figure of the call: "
                                      '€1,100 (under "Budget justification"); EUR 45,400 (under "Budget justification").')))
        self.put("proposal.md", PROPOSAL)
        code, _, rows = self.budget("--proposal", proposal)
        self.assertEqual((code, rows[("amounts_in_text", str(proposal))][0]), (0, "not_checked"))   # nothing written as money

    def test_a_semicolon_table_with_european_numbers_and_a_missing_column(self):
        self.put("budget.csv", "Line;Category;Year;Amount;Aim\nB1;staff;1;30.000,00;A1\nB2;travel;1;2 500;A2\n")
        code, out, _ = self.budget()
        self.assertEqual((code, out["total"], out["by_category"]), (0, 32500.0, {"staff": 30000.0, "travel": 2500.0}))
        self.put("budget.csv", "line,category,year,cost,aim\nB1,travel,1,10,A1\n")
        self.assertIn("lacks the column(s) amount. It needs: line, category, year, amount, aim.", self.bad_input("budget", self.dir / "budget.csv"))


if __name__ == "__main__":
    unittest.main()
