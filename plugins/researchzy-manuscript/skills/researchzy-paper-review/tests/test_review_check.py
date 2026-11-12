"""review_check.py: a review is reported only when its findings keep the contract."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import re
import sys
import tempfile
import textwrap
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SKILL = Path(__file__).parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
spec = importlib.util.spec_from_file_location("review_check", SKILL / "scripts" / "review_check.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

MANUSCRIPT = """# Weekly quizzes and exam scores in an introductory statistics course

## Abstract
We tested whether weekly quizzes raise final exam scores in an introductory statistics course.
Students who took the quizzes scored 6.4 points higher on the final exam than students who did not.
We conclude that weekly quizzes cause better retention of the course material in undergraduates.
This is the first study of weekly quizzes in a statistics course.

## Methods
Participants were 212 students enrolled in two sections of the same course in autumn 2023.
Section A (n = 108) took a ten-minute quiz every week, and Section B (n = 104) kept the usual schedule.
Sections were not assigned at random: students chose their section at enrol-
ment, before the quizzes were announced.
The final exam was identical in both sections and was marked by two instructors.

## Results
Table 2 reports a mean final exam score of 71.2 in Section A and 64.8 in Section B.
The difference between the sections was 5.9 points (95% CI 3.1 to 8.7).
TODO check the attendance figures before submission.

## Discussion
Our results show that weekly quizzes work in undergraduate courses of every subject.
The grade point average at entry was higher in Section A, as Table 1 shows.
"""
CAUSAL = "We conclude that weekly quizzes cause better retention of the course material in undergraduates."


def finding(fid="F1", **fields) -> dict:
    base = {"id": fid, "severity": "major", "evidence_status": "confirmed", "blocking": True,
            "fixability": "existing_data", "location": "Abstract, sentence 3", "quote": CAUSAL,
            "observation": "The abstract states a causal effect, but students chose their own section.",
            "basis": "A causal claim needs a comparison in which only the quizzes differ between the groups.",
            "why_it_matters": "The headline conclusion rests on it, and the sections differed at entry.",
            "fix": "State the result as a difference between sections and name self-selection as a limit.",
            "closure_test": "No sentence says that the quizzes cause the difference.",
            "verification": {"outcome": "confirmed",
                             "note": "Reread Methods and Discussion: no adjustment for entry grades."}}
    base.update(fields)
    return base


def review(*findings, **fields) -> dict:
    base = {"title": "Weekly quizzes and exam scores", "target": "not stated",
            "summary": "A two-section comparison of final exam scores with and without weekly quizzes.",
            "coverage": [{"item": "manuscript", "status": "read", "note": "paper.md"},
                         {"item": "supplement", "status": "not_provided"},
                         {"item": "data", "status": "not_provided"},
                         {"item": "code", "status": "not_read", "note": "A repository is linked; it was not opened."}],
            "checks": {"novelty": {"status": "skipped", "note": "Researchzy is not connected."},
                       "references": {"status": "skipped", "note": "researchzy-reference-check was not run."},
                       "statistics": {"status": "done", "note": "The interval matches the reported difference."}},
            "findings": list(findings),
            "verdicts": {"scientific": {"verdict": "revise", "reason": "The causal claim outruns the design."},
                         "submission": {"verdict": "revise", "reason": "One blocking finding, fixable by rewording."}}}
    base.update(fields)
    return base


def ready(data: dict, *names) -> dict:
    data = copy.deepcopy(data)
    for name in names or ("scientific", "submission"):
        data["verdicts"][name] = {"verdict": "ready", "reason": "Nothing found that should delay it."}
    return data


class ContractTests(unittest.TestCase):
    texts = [(MANUSCRIPT, rc.squeeze(MANUSCRIPT))]

    def problems(self, data: dict, referee: bool = False) -> list:
        return [(e["where"], e["problem"]) for e in rc.check(data, self.texts, referee)[0]]

    def test_a_review_without_findings_is_a_legitimate_result(self):
        self.assertEqual(self.problems(ready(review())), [])

    def test_a_finding_needs_every_field_and_legal_values(self):
        self.assertEqual(self.problems(review(finding())), [])
        broken = finding(severity="serious", fix="", blocking="yes")
        del broken["closure_test"], broken["evidence_status"]
        self.assertEqual(self.problems(review(broken)), [
            ("findings[F1].severity", "unknown_value"), ("findings[F1].evidence_status", "missing_field"),
            ("findings[F1].blocking", "missing_field"), ("findings[F1].fix", "missing_field"),
            ("findings[F1].closure_test", "missing_field")])
        self.assertEqual(self.problems(review(finding(fixability="easy"))), [("findings[F1].fixability", "unknown_value")])
        self.assertEqual(self.problems(review(finding(id=""))), [("findings[1].id", "missing_field")])

    def test_a_quote_must_be_in_the_manuscript(self):
        cases = {
            "We conclude that weekly quizzes double the retention of every student in the course.": "quote_not_found",
            "We conclude that weekly quizzes clearly cause better retention of the course material": "quote_partly_found",
            "scored 6.4 points": "quote_too_short",
        }
        for quote, problem in cases.items():
            self.assertEqual(self.problems(review(finding(quote=quote))), [("findings[F1].quote", problem)], quote)

    def test_a_quote_survives_line_breaks_and_case(self):
        quote = "students chose their section at enrolment, before the quizzes were announced"
        self.assertEqual(self.problems(review(finding(quote=quote.upper()))), [])
        self.assertEqual(rc.locate("Table 2 reports a mean final exam score of 71.2", self.texts), "found")

    def test_text_without_spaces_between_words_is_matched_by_characters(self):
        text = "摘要\n我们用 BERT 检验了每周测验是否提高统计学入门课程的\n期末考试成绩 (n = 212, p < 0.05)。"
        texts = [(text, rc.squeeze(text))]
        self.assertEqual(rc.locate("每周测验是否提高统计学入门课程的期末考试成绩", texts), "found")
        self.assertEqual(rc.locate("每周测验显著降低了统计学入门课程的期末考试成绩", texts), "absent")
        # Latin words inside such a sentence do not make it a five-word match on those words alone.
        self.assertEqual(rc.locate("我们用 BERT 否定了每周测验提高统计学入门课程的成绩 (n = 212, p < 0.05)", texts), "absent")
        self.assertEqual(rc.locate("期末考试成绩", texts), "too_short")

    def test_something_missing_needs_where_it_was_looked_for(self):
        missing = finding(quote="", evidence_status="reporting_gap")
        self.assertEqual(self.problems(review(missing)), [("findings[F1].where_looked", "needs_where_looked")])
        missing["where_looked"] = "Methods, Results, Tables 1 and 2: no analysis adjusted for entry grades."
        self.assertEqual(self.problems(review(missing)), [])

    def test_a_major_or_critical_finding_needs_a_verification(self):
        for verification in (None, {"outcome": "confirmed"}, {"outcome": "sure", "note": "Reread the Methods."}):
            self.assertEqual(self.problems(review(finding(verification=verification))),
                             [("findings[F1].verification", "needs_verification")])
        self.assertEqual(self.problems(review(finding(severity="minor", blocking=False, verification=None))), [])
        self.assertEqual(self.problems(review(finding(severity="minor", verification={"outcome": "sure"}))),
                         [("findings[F1].verification", "unknown_value")])

    def test_a_refuted_finding_is_dropped_and_no_longer_blocks(self):
        refuted = finding(quote="This sentence is not in the paper at all, the reviewer misread.", severity="critical",
                          verification={"outcome": "refuted", "note": "The Discussion already says so."})
        errors, state = rc.check(ready(review(refuted)), self.texts, False)
        self.assertEqual((errors, state["standing"], [f["id"] for f in state["withdrawn"]]), ([], [], ["F1"]))

    def test_ready_is_refused_beside_a_blocking_finding(self):
        data = review(finding())
        self.assertEqual(self.problems(ready(data)), [("verdicts.scientific", "ready_refused"),
                                                      ("verdicts.submission", "ready_refused")])
        # A blocking reporting gap holds the submission back, not the science.
        gap = review(finding(evidence_status="reporting_gap"))
        self.assertEqual(self.problems(ready(gap)), [("verdicts.submission", "ready_refused")])
        self.assertEqual(self.problems(ready(gap, "scientific")), [])
        unresolved = review(finding(evidence_status="unresolved"))
        self.assertEqual(len(self.problems(ready(unresolved))), 2)   # what cannot be settled is not ready either
        self.assertEqual(self.problems(ready(review(finding(blocking=False)))), [])

    def test_ready_is_refused_for_a_manuscript_not_read_in_full_or_a_failed_claim(self):
        partly = review(coverage=[{"item": "manuscript", "status": "partly_read", "note": "Pages 1 to 8 of 20."},
                                  *review()["coverage"][1:]])
        self.assertEqual(self.problems(ready(partly)), [("verdicts.scientific", "ready_refused"),
                                                        ("verdicts.submission", "ready_refused")])
        claim = {"id": "C1", "claim": "Quizzes cause better retention.", "location": "Abstract", "type": "causal",
                 "evidence": "Table 2", "support": "unsupported", "mismatch": ["causal_language"]}
        self.assertEqual(self.problems(ready(review(claims=[claim]))), [("verdicts.scientific", "ready_refused")])
        self.assertEqual(self.problems(ready(review(claims=[dict(claim, support="supported", mismatch=[])]))), [])

    def test_a_critical_finding_is_blocking(self):
        self.assertEqual(self.problems(review(finding(severity="critical", blocking=False))),
                         [("findings[F1].blocking", "critical_not_blocking")])

    def test_ids_are_unique_and_claims_exist(self):
        self.assertEqual(self.problems(review(finding(), finding())), [("findings[F1]", "duplicate_id")])
        claim = {"id": "C1", "claim": "Quizzes raise scores.", "location": "Abstract", "type": "improvement",
                 "support": "limited", "mismatch": ["magnitude"]}
        self.assertEqual(self.problems(review(finding(claims=["C1", "C9"]), claims=[claim, dict(claim)])),
                         [("claims[C1]", "duplicate_id"), ("findings[F1].claims", "unknown_claim")])
        self.assertEqual(self.problems(review(claims=[dict(claim, type="strong", support="weak", mismatch=["size"])])),
                         [("claims[C1].type", "unknown_value"), ("claims[C1].support", "unknown_value"),
                          ("claims[C1].mismatch", "unknown_value")])

    def test_placeholders_are_errors_except_inside_a_quote(self):
        data = review(finding(fix="TODO", basis="<basis>", closure_test="…", why_it_matters="[insert reason]"))
        self.assertEqual(self.problems(data), [
            ("findings[F1].basis", "placeholder"), ("findings[F1].why_it_matters", "placeholder"),
            ("findings[F1].fix", "placeholder"), ("findings[F1].closure_test", "placeholder")])
        leftover = finding(quote="TODO check the attendance figures before submission.", severity="minor", blocking=False)
        self.assertEqual(self.problems(review(leftover)), [])

    def test_coverage_says_what_was_read_and_what_was_not(self):
        data = review(coverage=[{"item": "manuscript", "status": "skimmed"}, {"item": "data", "status": "partly_read"}])
        self.assertEqual(self.problems(data), [
            ("coverage[manuscript].status", "unknown_value"), ("coverage[data].note", "missing_field"),
            ("coverage[supplement]", "missing_field"), ("coverage[code]", "missing_field")])
        self.assertEqual(self.problems(review(summary="")), [("review.summary", "missing_field")])

    def test_a_named_work_must_come_from_a_logged_search(self):
        work = {"corpusId": 77, "title": "Quizzes in a calculus course", "year": 2019, "cited": False,
                "differs": "Calculus, randomised by classroom."}
        checks = review()["checks"]
        skipped = dict(checks, novelty={"status": "skipped", "note": "Not connected.", "closest_works": [work]})
        self.assertEqual(self.problems(review(checks=skipped)), [("checks.novelty.closest_works[1]", "work_not_retrieved")])
        done = dict(checks, novelty={"status": "done", "closest_works": [dict(work, corpusId=None, cited="no")]})
        self.assertEqual(self.problems(review(checks=done)), [
            ("checks.novelty.searches", "missing_field"), ("checks.novelty.closest_works[1]", "work_not_retrieved"),
            ("checks.novelty.closest_works[1].cited", "missing_field")])
        good = dict(checks, novelty={"status": "done", "searches": [{"query": '"weekly quizzes" statistics', "total": 41}],
                                     "closest_works": [work]})
        self.assertEqual(self.problems(review(checks=good)), [])
        self.assertEqual(self.problems(review(checks={"novelty": {"status": "skipped"}, "statistics": {"status": "ok"}})), [
            ("checks.novelty.note", "missing_field"), ("checks.references.status", "missing_field"),
            ("checks.statistics.status", "unknown_value")])

    def test_a_referee_report_needs_the_venue_policy_and_keeps_the_recommendation_from_the_authors(self):
        data = review(finding())
        self.assertEqual(self.problems(data, referee=True), [
            ("referee.ai_use_confirmed", "ai_use_not_confirmed"), ("referee.venue", "missing_field"),
            ("referee.recommendation", "missing_field")])
        data["referee"] = {"venue": "A journal", "ai_use_confirmed": True, "recommendation": "major revision"}
        self.assertEqual(self.problems(data, referee=True), [])
        data["findings"][0]["why_it_matters"] = "Without this the manuscript should be rejected."
        data["summary"] += " I recommend rejection."
        self.assertEqual(self.problems(data, referee=True), [("summary", "decision_in_author_comments"),
                                                             ("findings[F1].why_it_matters", "decision_in_author_comments")])
        self.assertEqual(self.problems(data), [])   # the author's own draft may be told anything

    def test_resolved_must_show_in_the_revised_text(self):
        revised = MANUSCRIPT.replace(CAUSAL, "Scores were higher in the section with weekly quizzes.")
        texts = [(revised, rc.squeeze(revised))]
        resolved = finding(recheck={"status": "resolved", "note": "The causal sentence was replaced."})
        self.assertEqual(rc.recheck_finding(finding(), texts)["passage"], "gone")
        self.assertEqual(rc.recheck_finding(finding(), self.texts)["status"], "not_rechecked")
        self.assertEqual(rc.recheck_finding(resolved, texts)["problem"], "")
        # Against the unrevised text, "resolved" rests on the author's word alone.
        self.assertEqual(rc.recheck_finding(resolved, self.texts)["problem"], "resolved_not_shown")
        self.assertEqual(self.problems(review(resolved)), [("findings[F1].recheck", "resolved_not_shown")])
        shown = finding(quote="", where_looked="Methods and Results", recheck={
            "status": "resolved", "quote": "students chose their section at enrolment, before the quizzes were announced"})
        self.assertEqual(rc.recheck_finding(shown, self.texts)["problem"], "")
        shown["recheck"]["quote"] = "an analysis adjusted for the grade point average at entry is reported"
        self.assertEqual(rc.recheck_finding(shown, self.texts)["problem"], "new_quote_not_found")
        self.assertEqual(rc.recheck_finding(finding(recheck={"status": "fixed"}), texts)["problem"], "unknown_status")
        # A resolved finding no longer stands; an open one must still be quotable from the revised text.
        errors, state = rc.check(ready(review(resolved)), texts, False)
        self.assertEqual((errors, state["standing"], [f["id"] for f in state["resolved"]]), ([], [], ["F1"]))
        still_open = rc.check(review(finding(recheck={"status": "open"})), texts, False)[0]
        self.assertEqual([(e["where"], e["problem"]) for e in still_open], [("findings[F1].quote", "quote_not_found")])


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "paper.md").write_text(MANUSCRIPT, encoding="utf-8")
        self.out = self.dir / "paper-review"
        self.out.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, data, *argv, command="check", manuscript="paper.md"):
        (self.out / "findings.json").write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        old, out = sys.argv, io.StringIO()
        sys.argv = ["review_check.py", command, str(self.out / "findings.json"),
                    "--manuscript", str(self.dir / manuscript), *argv]
        try:
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = rc.main()
        finally:
            sys.argv = old
        return code, json.loads(out.getvalue())

    def full_review(self) -> dict:
        claim = {"id": "C1", "claim": "Weekly quizzes cause better retention.", "location": "Abstract", "type": "causal",
                 "evidence": "Table 2", "support": "limited", "mismatch": ["causal_language", "scope"]}
        gap = finding("F2", quote="", evidence_status="reporting_gap", blocking=False, fixability="new_work",
                      location="Results", where_looked="Methods, Results, Tables 1 and 2")
        numbers = finding("F3", severity="minor", blocking=False, location="Abstract and Results", verification=None,
                          quote="The difference between the sections was 5.9 points (95% CI 3.1 to 8.7).")
        refuted = finding("F4", observation="The exam differed between sections.",
                          verification={"outcome": "refuted", "note": "Methods: the exam was identical."})
        return review(numbers, finding(claims=["C1"]), gap, refuted, claims=[claim], strengths=["The exam was the same."])

    def test_the_report_has_coverage_claims_findings_by_severity_and_two_verdicts(self):
        code, summary = self.run_cli(self.full_review())
        self.assertEqual((code, summary["ok"], summary["errors"]), (0, True, []))
        self.assertEqual((summary["findings"], summary["standing"], summary["by_severity"]),
                         (4, 3, {"critical": 0, "major": 2, "minor": 1}))
        self.assertEqual((summary["blocking"], summary["withdrawn"], summary["not_checked"]),
                         (["F1"], ["F4"], ["novelty", "references"]))
        self.assertEqual(summary["written"], [str(self.out / "review.md")])
        text = (self.out / "review.md").read_text(encoding="utf-8")
        self.assertIn("Scientific readiness: **revise**. Submission readiness: **revise**. Findings: 0 critical, 2 major, "
                      "1 minor; blocking: F1.", text)
        self.assertIn("| code | not read | A repository is linked; it was not opened. |", text)
        self.assertIn("| C1. Weekly quizzes cause better retention. | Abstract | causal | Table 2 | limited | "
                      "causal language, scope | F1 |", text)
        self.assertIn("No critical findings.", text)
        self.assertIn("major · confirmed · blocking · fixable with what the authors have", text)
        self.assertIn(f"> {CAUSAL}", text)
        self.assertIn("Not found in: Methods, Results, Tables 1 and 2", text)
        self.assertLess(text.index("#### F1."), text.index("#### F2."))
        self.assertLess(text.index("#### F2."), text.index("#### F3."))   # major before minor, whatever the file order
        self.assertIn("F4: refuted when checked against the manuscript.", text)
        self.assertNotIn("The exam differed between sections.", text)
        self.assertIn("Not checked: Researchzy is not connected.", text)
        self.assertIn("| Submission | revise | One blocking finding, fixable by rewording. |", text)
        self.assertIn("Not checked, so not covered by these verdicts: novelty, references.", text)
        self.assertFalse((self.out / "referee-report.md").exists())

    def test_a_clean_review_passes_and_says_so(self):
        code, summary = self.run_cli(ready(review()))
        self.assertEqual((code, summary["ok"], summary["standing"]), (0, True, 0))
        text = (self.out / "review.md").read_text(encoding="utf-8")
        self.assertIn("No major findings.", text)
        self.assertIn("This review gives no score and does not predict acceptance.", text)

    def test_a_broken_contract_exits_1_and_writes_no_report(self):
        code, summary = self.run_cli(review(finding(quote="A sentence that the manuscript does not contain anywhere.")))
        self.assertEqual((code, summary["ok"], summary["written"]), (1, False, []))
        self.assertEqual(summary["errors"][0]["problem"], "quote_not_found")
        self.assertFalse((self.out / "review.md").exists())

    def test_the_referee_files_keep_the_recommendation_for_the_editor(self):
        data = self.full_review()
        data["checks"]["novelty"] = {
            "status": "done", "searches": [{"query": "weekly quizzes statistics course", "total": 41}],
            "closest_works": [{"corpusId": 77, "title": "Quizzes in a calculus course", "year": 2019, "cited": False,
                               "differs": "Calculus, randomised by classroom."},
                              {"corpusId": 78, "title": "Testing effects in lectures", "year": 2011, "cited": True,
                               "differs": "A review; no statistics course."}]}
        data["referee"] = {"venue": "Journal of Course Design", "ai_use_confirmed": True,
                           "recommendation": "major revision", "to_editor": "The design cannot carry the causal claim."}
        code, summary = self.run_cli(data, "--referee")
        self.assertEqual((code, len(summary["written"])), (0, 3))
        report = (self.out / "referee-report.md").read_text(encoding="utf-8")
        self.assertIn("**F1. Abstract, sentence 3** (Concern)", report)
        self.assertIn("**F2. Results** (Missing information)", report)
        self.assertIn("- **Requested change.** State the result as a difference", report)
        self.assertIn("- Quizzes in a calculus course (2019): Calculus, randomised by classroom.", report)
        self.assertNotIn("Testing effects in lectures", report)   # already cited, so not suggested
        for private in ("major revision", "Verification", "blocking", "revise", "F4", "cannot carry"):
            self.assertNotIn(private, report)
        editor = (self.out / "to-editor.md").read_text(encoding="utf-8")
        self.assertIn("Recommendation (a draft; the reviewer decides): major revision", editor)
        self.assertIn("| Scientific soundness | revise |", editor)
        self.assertIn("- references: not checked. researchzy-reference-check was not run.", editor)
        self.assertIn("| `weekly quizzes statistics course` | 41 |", (self.out / "review.md").read_text(encoding="utf-8"))

    def test_recheck_reports_each_passage_against_the_revision(self):
        revised = MANUSCRIPT.replace(CAUSAL, "Scores were higher in the section with weekly quizzes.").replace(
            "5.9 points", "6.4 points")
        (self.dir / "revised.md").write_text(revised, encoding="utf-8")
        code, summary = self.run_cli(self.full_review(), command="recheck", manuscript="revised.md")
        self.assertEqual((code, summary["findings"]), (0, 3))   # the refuted finding is not carried over
        self.assertEqual(summary["passage"], {"unchanged": [], "changed": ["F3"], "gone": ["F1"], "no_quote": ["F2"],
                                              "unknown": []})
        self.assertEqual(summary["status"]["not_rechecked"], ["F3", "F1", "F2"])
        data = self.full_review()
        data["findings"][2]["recheck"] = {"status": "resolved", "note": "The authors say an adjusted analysis was added."}
        code, summary = self.run_cli(data, command="recheck", manuscript="revised.md")
        self.assertEqual((code, [(p["id"], p["problem"]) for p in summary["problems"]]), (1, [("F2", "resolved_not_shown")]))
        self.assertIn("| F2 | major | Results | no quote | resolved | none | marked resolved, but",
                      (self.out / "recheck.md").read_text(encoding="utf-8"))

    def test_a_docx_manuscript_is_read_without_its_tracked_deletions(self):
        body = ("<w:document><w:body><w:p><w:r><w:t>We conclude that weekly quizzes cause better reten</w:t></w:r>"
                "<w:r><w:t>tion of the course material</w:t></w:r>"
                "<w:del><w:r><w:delText> in every student</w:delText></w:r></w:del>"
                "<w:r><w:t xml:space=\"preserve\"> in undergraduates &amp; others.</w:t></w:r></w:p>"
                "</w:body></w:document>")
        with zipfile.ZipFile(self.dir / "paper.docx", "w") as archive:
            archive.writestr("word/document.xml", body)
        text = rc.read_manuscript(self.dir / "paper.docx")
        self.assertEqual(text.strip(), "We conclude that weekly quizzes cause better retention of the course material "
                                       "in undergraduates & others.")
        self.assertEqual(self.run_cli(review(finding()), manuscript="paper.docx")[0], 0)

    def test_a_pdf_manuscript_is_read_when_pymupdf_is_installed(self):
        try:
            import pymupdf as fitz
        except ImportError:
            try:
                import fitz
            except ImportError:
                self.skipTest("PyMuPDF is not installed")
        doc = fitz.open()
        doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 750), MANUSCRIPT, fontsize=8)
        doc.save(self.dir / "paper.pdf")
        self.assertEqual(self.run_cli(review(finding()), manuscript="paper.pdf")[0], 0)

    def test_unreadable_input_exits_2_with_a_message(self):
        for data, manuscript in ((review(), "missing.md"), ("{not json", "paper.md"), ({"claims": []}, "paper.md")):
            with self.assertRaises(SystemExit) as stopped:
                self.run_cli(data, manuscript=manuscript)
            self.assertEqual(stopped.exception.code, 2)


class SchemaTests(unittest.TestCase):
    def test_the_schema_is_the_same_in_the_script_and_in_the_reference(self):
        def block(text: str, start: str, end: str) -> str:
            return textwrap.dedent(text[text.index(start):text.index(end, text.index(start))]).strip()

        in_script = block(rc.__doc__, '  {"title"', "\n\nStandard library only")
        in_reference = block((SKILL / "references" / "findings.md").read_text(encoding="utf-8"), '{"title"', "\n```")
        self.assertEqual(in_script, in_reference)
        for name in ("SEVERITIES", "EVIDENCE", "FIXABILITY", "OUTCOMES", "VERDICTS", "RECHECK", "COVERAGE", "CLAIM_TYPES",
                     "SUPPORT", "MISMATCH"):
            for value in getattr(rc, name):
                self.assertRegex(in_script, rf"(?<![\w]){re.escape(value)}(?![\w])")


if __name__ == "__main__":
    unittest.main()
