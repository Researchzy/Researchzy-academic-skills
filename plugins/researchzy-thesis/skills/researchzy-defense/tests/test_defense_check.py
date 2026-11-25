"""defense_check.py: printed page numbers, anchors, numbers, sources, coverage and the mock-defence log, on an
invented thesis built here as a text with page marks and, when PyMuPDF is installed, as a PDF. Offline."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "defense_check.py"
spec = importlib.util.spec_from_file_location("defense_check", SCRIPT)
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)
fitz = dc.pymupdf()

ROMAN = "i ii iii iv v vi vii viii ix x xi xii".split()
FILLER = ("Volunteers in community sports clubs give their time for many reasons, and the clubs depend on "
          "them for coaching, refereeing and running events through the season.")
# An invented master's thesis: PDF page 1 is the title page, 2-12 are printed ii-xii, 13-100 are printed 1-88.
# PDF page 25 (printed 13) opens chapter 2 without a printed number.
SPECIAL = {
    3: "Abstract\nThis thesis surveys club volunteers. The response rate was 85.7%.\n"
       "Hypotheses H1 and H2 were supported, while the third was not.",
    6: "List of Tables\nTable 4.1 Sample characteristics ........ 70\nTable 4.3 Regression results for H1 to H3 ........ 76",
    13: "Chapter 1 Introduction\nThis chapter sets out why clubs lose volunteers.",
    25: "Chapter 2 Literature review\nStudies of sport volunteering have examined motives but rarely retention over time.",
    45: "Chapter 3 Method\nThe sampling frame was the 2023 membership register of 14 clubs.",
    57: "Of the 364 questionnaires distributed, 312 were returned, a response rate of 85.7%.",
    70: "Chapter 4 Results\nThis chapter reports the survey results.",
    79: "The coefficients for the three hypotheses are reported in\nTable 4.3, which follows the descriptive statistics.",
    82: "Table 4.1 Sample characteristics\nWomen made up 41.2% of the sample.",
    88: "Table 4.3 Regression results for H1 to H3\nH1 was supported (beta = 0.42, p < 0.001).\n"
        "H3 was not supported (beta = 0.04, p = 0.61).",
    92: "Chapter 5 Discussion\nThis chapter discusses the results.",
    95: "No robustness analysis with alternative measures of commitment was carried out, because the survey "
        "had a single measure.",
}


def english_pages() -> list:
    """[(body, printed number or "")] for PDF pages 1-100."""
    pages = []
    for pdf in range(1, 101):
        body = SPECIAL.get(pdf, "") + ("\n" if pdf in SPECIAL else "") + FILLER
        foot = "" if pdf in (1, 25) else ROMAN[pdf - 1] if pdf <= 12 else str(pdf - 12)
        pages.append(("Volunteer retention in community sports clubs\nA thesis for the degree of Master of Science"
                      if pdf == 1 else body, foot))
    return pages


CHINESE = [("社区体育俱乐部志愿者的保留研究\n硕士学位论文", ""),
           ("摘要\n本研究调查了俱乐部志愿者，样本量为312人，有效问卷回收率为85.7%。\n" + "志愿者是俱乐部运行的基础。" * 8, "i"),
           ("目录\n第1章 绪论 ........ 1\n第3章 研究方法 ........ 2\n" + "本章介绍研究背景。" * 8, "ii"),
           ("第1章 绪论\n" + "志愿者流失是俱乐部面临的主要问题之一。" * 8, "1"),
           ("表3-2 样本的描述统计\n样本量为312人，其中女性占41.2%。\n" + "问卷通过俱乐部发放。" * 8, "2"),
           ("假设3（H3）未得到支持（β=0.04）。如表3-2所示，样本以年轻会员为主。\n" + "讨论部分将进一步说明原因。" * 8, "3")]


def as_text(pages: list) -> str:
    return "".join(f"[[page {n}]]\nRunning head\n{body}\n{foot}\n" for n, (body, foot) in enumerate(pages, 1))


def as_pdf(pages: list, path: Path, font: str) -> None:
    doc = fitz.open()
    for body, foot in pages:
        page = doc.new_page()
        page.insert_text((72, 50), "Running head", fontsize=8, fontname=font)
        page.insert_textbox(fitz.Rect(72, 72, 523, 760), body, fontsize=10, fontname=font)
        if foot:
            page.insert_text((290, 800), foot, fontsize=10, fontname=font)
    doc.save(path)


CLAIMS = {
    "chapters": [{"id": "1", "title": "Introduction", "first_page": "1", "last_page": "12"},
                 {"id": "2", "title": "Literature review", "first_page": "13", "last_page": "32"},
                 {"id": "3", "title": "Method", "first_page": "33", "last_page": "57"},
                 {"id": "4", "title": "Results", "first_page": "58", "last_page": "79"},
                 {"id": "5", "title": "Discussion", "first_page": "80", "last_page": "88"}],
    "claims": [{"id": "C1", "kind": "claim", "quote": "Hypotheses H1 and H2 were supported", "page": "iii"},
               {"id": "H3", "kind": "hypothesis", "label": "H3", "result": "not_supported",
                "quote": "H3 was not supported (beta = 0.04, p = 0.61)", "page": "76"}]}
TITLE = "Retention of volunteers in a community football club — a panel study"
LIMIT = "No robustness analysis with alternative measures of commitment was carried out"


def question(qid, category, text, anchors, points=(), level="defend", outline=None, **extra) -> dict:
    """A question of the bank; extra fields (source, claims, chapter) go on the question, outline on its outline."""
    return {"id": qid, "category": category, "question": text, "source": {"type": "thesis"}, **extra,
            "outline": {"opening": "One sentence that answers.", "points": list(points), "anchors": anchors,
                        "level": level, **(outline or {})}}


BANK = {"questions": [
    question("Q1", "method", "Why was the sampling frame limited to the membership register?",
             [{"page": "33", "quote": "The sampling frame was the 2023 membership register of 14 clubs"}],
             ["The register covered 14 clubs."], "bound",
             source={"type": "reviewer", "file": "reviews/r1.txt", "ref": "Reviewer 1, point 2",
                     "quote": "The sampling frame excludes volunteers who are not registered members"}),
    question("Q2", "data", "How many questionnaires came back?",
             [{"page": "45", "quote": "Of the 364 questionnaires distributed, 312 were returned"}],
             ["312 of 364 came back, a response rate of 85.7%."]),
    question("Q3", "contribution", "H3 was not supported. What does that mean for the model?",
             [{"page": "76", "display": "Table 4.3"}], ["beta = 0.04 with p = 0.61."], "bound", claims=["H3"]),
    question("Q4", "limitation", "Did you test an alternative measure of commitment?",
             [{"page": "83", "quote": LIMIT}], [], "adopt",
             outline={"not_done": {"analysis": "a robustness check with another measure",
                                   "because": "the survey had a single measure of commitment"}}),
    question("Q5", "opening", "Summarise your thesis.",
             [{"page": "iii", "quote": "Hypotheses H1 and H2 were supported"}], ["A response rate of 85.7%."],
             claims=["C1"], chapter="1"),
    question("Q6", "application", "What should clubs do with this?",
             [{"page": "76", "quote": "H1 was supported (beta = 0.42, p < 0.001)"}], ["beta = 0.42 for H1."]),
    question("Q7", "closing", "What would you do differently?", [{"page": "83", "quote": LIMIT}], [], "adopt"),
    question("Q8", "contribution", f"How does your work differ from “{TITLE}” (2025)?",
             [{"page": "13", "quote": "Studies of sport volunteering have examined motives but rarely retention"}],
             ["That study followed one club; this thesis surveyed volunteers once, in 2023."],
             source={"type": "search", "record": "search/retention.json", "paper": {"title": TITLE}},
             outline={"allow": []}),
]}


def run(*argv) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = dc.main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, (json.loads(out.getvalue()) if out.getvalue().strip() else {}), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dir = self.root / "defense"

    def tearDown(self):
        self.tmp.cleanup()

    def thesis(self, pages=None, name="thesis.txt") -> Path:
        path = self.root / name
        path.write_text(as_text(pages or english_pages()), encoding="utf-8")
        code, out, _ = run("pages", str(path), "--dir", str(self.dir))
        self.assertEqual(code, 0, out)
        return path

    def bank(self, bank=None, claims=CLAIMS) -> None:
        (self.dir / "reviews").mkdir(parents=True, exist_ok=True)
        (self.dir / "search").mkdir(exist_ok=True)
        (self.dir / "reviews" / "r1.txt").write_text(
            "Point 2. The sampling frame excludes volunteers who are not\nregistered members, so the results may "
            "not generalise.", encoding="utf-8")
        (self.dir / "search" / "retention.json").write_text(json.dumps(   # saved with \\u escapes
            {"query": "volunteer retention sports clubs", "yearFrom": 2024,
             "results": [{"title": TITLE, "year": 2025, "doi": "10.1234/example.2025.17"}]}), encoding="utf-8")
        bank = copy.deepcopy(BANK if bank is None else bank)
        (self.dir / "questions.json").write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")
        if claims is not None:
            (self.dir / "claims.json").write_text(json.dumps(claims, ensure_ascii=False), encoding="utf-8")

    def check(self) -> tuple:
        code, out, err = run("check", "--dir", str(self.dir))
        self.report = (self.dir / "check.md").read_text(encoding="utf-8") if (self.dir / "check.md").is_file() else ""
        return code, out, err

    def edit(self, qid: str, change) -> dict:
        bank = copy.deepcopy(BANK)
        change(next(q for q in bank["questions"] if q["id"] == qid))
        return bank


class NumberTests(unittest.TestCase):
    def values(self, text):
        return [(t["written"], str(t["value"]), t["negative"], t["percent"]) for t in dc.numbers_of(text)]

    def test_numbers_that_touch_han_characters(self):
        self.assertEqual(self.values("样本量为312人，回收率为85.7%。"), [("312", "312", False, False),
                                                              ("85.7%", "85.7", False, True)])
        self.assertEqual(self.values("共纳入37名"), [("37", "37", False, False)])
        self.assertEqual(self.values("８５．７％"), [("85.7%", "85.7", False, True)])

    def test_names_and_references_are_not_numbers(self):
        text = ("H2a, p53, COVID-19, Table 4.3 on p. 67, pp. 76-78, Figure 3.2, 第76页的表4-3和图 3.2, 假设3, "
                "Hypothesis 2, Chapter 4, Section 3.2, 第4章, 3.2节, [12], [3, 4], Eq. (3), 式(3)")
        self.assertEqual(self.values(text), [])

    def test_ranges_signs_and_separators(self):
        self.assertEqual(self.values("aged 18–65, a change of −0.15, 16,384 tokens"),
                         [("18", "18", False, False), ("65", "65", False, False), ("-0.15", "0.15", True, False),
                          ("16,384", "16384", False, False)])

    def test_page_numbers_and_labels(self):
        self.assertEqual([dc.parse_label(x) for x in ("76", "vii", "XII", "page", "")],
                         [("arabic", 76), ("roman", 7), ("roman", 12), None, None])
        self.assertEqual([dc.page_refs(x) for x in ("p. 76", "第76页", "76–77", "vii", "seventy")],
                         [["76"], ["76"], ["76", "77"], ["vii"], None])
        for line, number in (("- 76 -", "76"), ("Page 76 of 120", "76"), ("第 12 页 共 120 页", "12"), ("·12·", "12")):
            self.assertEqual(dc.PAGE_LINE.match(line)["n"], number)
        self.assertIsNone(dc.PAGE_LINE.match("Results 76"))

    def test_captions_and_mentions(self):
        def caption(line):
            m = dc.DISPLAY.search(line)
            return bool(not line[:m.start()].strip() and dc.CAPTION_END.match(line, m.end())
                        and not dc.LEADER.search(line))
        for line in ("Table 4.3 Regression results", "Table 4.3: Regression", "表4-3 样本描述统计", "图3-2 研究框架",
                     "Fig. 3 (continued)"):
            self.assertTrue(caption(line), line)
        for line in ("Table 4.3, the mean", "Table 4.3 shows", "表4-3所示，", "表 4.3 所示", "see Table 4.3",
                     "Table 4.3 Regression results ........ 76"):
            self.assertFalse(caption(line), line)
        self.assertIsNone(dc.DISPLAY.search("发表3篇论文"))


class PagesTests(Base):
    def test_printed_page_numbers_from_a_text_with_page_marks(self):
        self.thesis()
        T = dc.load_thesis(self.dir)
        self.assertEqual(T["runs"], "ii–xii (PDF 2–12), 1–88 (PDF 13–100)")
        label = {p["pdf"]: (p["label"], p["how"]) for p in T["pages"]}
        self.assertEqual(label[1], ("", ""))
        self.assertEqual(label[3], ("iii", "printed"))
        self.assertEqual(label[25], ("13", "inferred"))          # the unnumbered chapter opening
        self.assertEqual(label[88], ("76", "printed"))
        self.assertEqual(T["displays"][("table", "4.3")]["captions"], [88])      # not the list of tables
        self.assertIn(79, T["displays"][("table", "4.3")]["mentions"])          # nor the wrapped mention
        text = (self.dir / "thesis-pages.txt").read_text(encoding="utf-8")
        self.assertIn("===== PDF page 88: printed page 76 (arabic) =====", text)
        self.assertIn("#   Table 4.3: printed page 76 (PDF page 88)", text)

    def test_printed_number_is_not_a_number_of_the_thesis(self):
        self.thesis()
        T = dc.load_thesis(self.dir)
        self.assertNotIn(88, [t["page"]["pdf"] for t in T["index"].get(dc.Decimal("76"), [])])

    def test_a_number_between_two_pages_of_a_run_is_corrected(self):
        pages = english_pages()
        pages[49] = (pages[49][0] + "\nX", "")       # an axis label instead of the printed 38
        self.thesis(pages)
        T = dc.load_thesis(self.dir)
        self.assertEqual(T["by_pdf"][50]["label"], "38")

    def test_text_without_pages_and_pdf_without_tools(self):
        path = self.root / "plain.txt"
        path.write_text(FILLER * 10, encoding="utf-8")
        code, out, _ = run("pages", str(path), "--dir", str(self.dir))
        self.assertEqual((code, out["status"]), (0, "ok"))
        self.assertFalse(dc.load_thesis(self.dir)["paged"])
        pdf = self.root / "thesis.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        with mock.patch.object(dc, "pymupdf", return_value=None), mock.patch.object(dc.shutil, "which", return_value=None):
            code, out, _ = run("pages", str(pdf), "--dir", str(self.dir))
        self.assertEqual((code, out["status"]), (0, "not_checked"))
        self.assertIn("PyMuPDF", out["reason"])
        self.assertIn("pdftotext", out["reason"])
        self.assertFalse(dc.load_thesis(self.dir)["ok"])

    def test_a_scan_is_not_checked(self):
        path = self.root / "scan.txt"
        path.write_text("[[page 1]]\n1\n[[page 2]]\n2\n", encoding="utf-8")
        code, out, _ = run("pages", str(path), "--dir", str(self.dir))
        self.assertEqual((code, out["status"]), (0, "not_checked"))
        self.assertIn("scan", out["reason"])


@unittest.skipUnless(fitz, "PyMuPDF is not installed")
class PdfTests(Base):
    def test_pdf_gives_the_same_printed_numbers_as_the_text(self):
        as_pdf(english_pages(), self.root / "thesis.pdf", "helv")
        code, out, _ = run("pages", str(self.root / "thesis.pdf"), "--dir", str(self.dir))
        self.assertEqual((code, out["reader"]), (0, "PyMuPDF"))
        from_pdf = {p["pdf"]: p["label"] for p in dc.load_thesis(self.dir)["pages"]}
        self.thesis()
        from_text = {p["pdf"]: p["label"] for p in dc.load_thesis(self.dir)["pages"]}
        self.assertEqual(from_pdf, from_text)

    def test_planted_table_page_in_a_pdf(self):
        as_pdf(english_pages(), self.root / "thesis.pdf", "helv")
        run("pages", str(self.root / "thesis.pdf"), "--dir", str(self.dir))
        self.bank(self.edit("Q3", lambda q: q["outline"]["anchors"][0].update(page="67")))
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("Q3 anchor 1: Table 4.3 is on printed page 76 (PDF page 88), not on page 67", out["fails"])

    def test_chinese_pdf(self):
        try:
            as_pdf(CHINESE, self.root / "zh.pdf", "china-s")
        except Exception as exc:  # a PyMuPDF built without its CJK fonts
            self.skipTest(f"no CJK font: {exc}")
        run("pages", str(self.root / "zh.pdf"), "--dir", str(self.dir))
        T = dc.load_thesis(self.dir)
        self.assertEqual(T["runs"], "i–ii (PDF 2–3), 1–3 (PDF 4–6)")
        self.assertEqual(T["displays"][("table", "3.2")]["captions"], [5])
        self.assertTrue(dc.find_number(dc.numbers_of("样本量为312人")[0], T))


class CheckTests(Base):
    def setUp(self):
        super().setUp()
        self.thesis()

    def fails(self, bank=None, claims=CLAIMS) -> list:
        self.bank(bank, claims)
        code, out, _ = self.check()
        self.assertEqual(code, 1 if out["fails"] else 0, out)
        return out["fails"]

    def test_the_example_bank_passes(self):
        self.assertEqual(self.fails(), [])
        self.assertIn("| 85.7% | 45 | 57 |", self.report)          # numbers to know, at their printed page
        self.assertIn("Q8 anchor 1, quote: the quote is on printed page 13 (PDF page 25)", self.report)

    def test_table_cited_on_the_wrong_page(self):                 # DF-1: "Table 4.3, p. 67"
        fails = self.fails(self.edit("Q3", lambda q: q["outline"]["anchors"][0].update(page="67")))
        self.assertIn("Q3 anchor 1: Table 4.3 is on printed page 76 (PDF page 88), not on page 67", fails)

    def test_a_number_that_differs_from_the_thesis_is_not_found(self):   # DF-1: 87.5% against 85.7%
        fails = self.fails(self.edit("Q2", lambda q: q["outline"]["points"].append("A response rate of 87.5%.")))
        self.assertEqual(len(fails), 1)
        self.assertTrue(fails[0].startswith("Q2: NOT_FOUND: `87.5%`"), fails)
        self.assertIn("`85.7%` on printed page 45 (PDF page 57)", self.report)

    def test_rounded_and_elsewhere_numbers(self):
        self.assertEqual(self.fails(self.edit("Q2", lambda q: q["outline"]["points"].append(
            "About 86% answered; women were 41.2%."))), [])
        self.assertIn("`86%` on printed page 45 (PDF page 57), rounded from 85.7%", self.report)
        self.assertIn("Q2, number: `41.2%` not on a cited page but on printed page 70 (PDF page 82)", self.report)

    def test_hypothesis_without_a_question(self):                # DF-1: H3 not supported
        fails = self.fails(self.edit("Q3", lambda q: q.pop("claims")))
        self.assertIn("coverage: no question on hypothesis H3 (not_supported, page 76): add one, or give the "
                      "reason in not_asked", fails)

    def test_category_without_a_question(self):
        bank = copy.deepcopy(BANK)
        bank["questions"] = [q for q in bank["questions"] if q["category"] != "application"]
        self.assertIn("coverage: no question on category application: add one, or give the reason in not_asked",
                      self.fails(bank))
        bank["not_asked"] = {"application": "the user has a separate practice chapter"}
        self.assertEqual(self.fails(bank), [])

    def test_chapter_without_a_question(self):
        bank = copy.deepcopy(BANK)
        bank["questions"] = [q for q in bank["questions"] if q["id"] != "Q8"]
        self.assertIn("coverage: no question on chapter 2 (Literature review): add one, or give the reason in "
                      "not_asked", self.fails(bank))

    def test_a_number_from_outside_needs_allow(self):
        point = "Smith et al. report a rate of 0.71 in clubs abroad."
        fails = self.fails(self.edit("Q6", lambda q: q["outline"]["points"].append(point)))
        self.assertTrue(any(f.startswith("Q6: NOT_FOUND: `0.71`") for f in fails), fails)
        self.assertEqual(self.fails(self.edit("Q6", lambda q: q["outline"].update(points=[point], allow=[
            "0.71 | Smith et al. (2024), Table 2, supplied by the user"]))), [])

    def test_an_analysis_not_done(self):                         # DF-1: no robustness analysis
        fails = self.fails(self.edit("Q4", lambda q: q["outline"].update(
            not_done={"analysis": "robustness check"}, points=["The result held with the other measure (beta = 0.31)."])))
        self.assertIn("Q4: not_done says what was not done and why: {analysis, because}", fails)
        self.assertTrue(any("NOT_FOUND: `0.31`" in f for f in fails), fails)

    def test_a_page_alone_is_no_anchor(self):
        fails = self.fails(self.edit("Q7", lambda q: q["outline"].update(anchors=[{"page": "82"}])))
        self.assertIn("Q7 anchor 1: a page alone anchors nothing: name the table or figure on it, quote it, or "
                      "use a number printed on it", fails)
        self.assertEqual(self.fails(self.edit("Q7", lambda q: q["outline"].update(
            anchors=[{"page": "70"}], points=["Women were 41.2% of the sample."]))), [])

    def test_quotes_pages_and_tables_that_are_not_there(self):
        bank = self.edit("Q1", lambda q: q["outline"]["anchors"].extend([
            {"page": "34", "quote": "The sampling frame was the 2023 membership register of 14 clubs"},
            {"page": "33", "quote": "Every club in the region took part in the survey"},
            {"page": "130", "display": "Table 9.9"}]))
        fails = self.fails(bank)
        self.assertIn("Q1 anchor 2: the quote is on printed page 33 (PDF page 45), not on page 34", fails)
        self.assertIn("Q1 anchor 3: NOT_FOUND: the quote is not in the thesis", fails)
        self.assertIn("Q1 anchor 4: there is no printed page 130; the thesis has ii–xii (PDF 2–12), 1–88 (PDF 13–100)",
                      fails)
        self.assertIn("Q1 anchor 4: NOT_FOUND: no table or figure Table 9.9 in the thesis", fails)

    def test_reviewer_questions_are_quoted_and_come_first(self):
        bank = copy.deepcopy(BANK)
        bank["questions"][0]["source"]["quote"] = "The response rate is too low for any conclusion"
        bank["questions"].append(bank["questions"].pop(0))
        fails = self.fails(bank)
        self.assertIn("Q1: a reviewer's question quotes the objection (source.quote) from the report in source.file",
                      fails)
        self.assertIn("Q1: the reviewers' questions come before all others", fails)

    def test_a_searched_paper_must_be_in_the_saved_record(self):
        fails = self.fails(self.edit("Q8", lambda q: q["source"]["paper"].update(title="A paper from memory")))
        self.assertTrue(any("never name a paper that no search returned" in f for f in fails), fails)

    def test_claims_are_quoted_on_their_page(self):
        claims = copy.deepcopy(CLAIMS)
        claims["claims"][0]["page"] = "iv"
        claims["claims"][1]["result"] = "rejected"
        fails = self.fails(claims=claims)
        self.assertIn("claim C1: the quote is on printed page iii (PDF page 3), not on page iv", fails)
        self.assertTrue(any(f.startswith("claim H3: a claim has its own id") for f in fails), fails)

    def test_without_pages_the_anchors_are_not_checked(self):
        (self.dir / "thesis-pages.txt").unlink()
        self.bank()
        code, out, _ = self.check()
        self.assertEqual((code, out["fail"]), (0, 0))
        self.assertGreater(out["not_checked"], 10)
        self.assertIn("run `defense_check.py pages` on the thesis first", self.report)

    def test_unreadable_questions(self):
        self.bank()
        (self.dir / "questions.json").write_text("{not json", encoding="utf-8")
        code, _, err = self.check()
        self.assertEqual(code, 2)
        self.assertIn("is not valid JSON", err)


class ChineseCheckTests(Base):
    def test_chinese_outline(self):
        self.thesis(CHINESE, "zh.txt")
        bank = {"questions": [question("Q1", "data", "样本量是多少？", [{"page": "2", "display": "表 3.2"}],
                                       ["样本量为312人，女性占41.2%。"]),
                              question("Q2", "contribution", "假设3为什么没有得到支持？",
                                       [{"page": "3", "quote": "假设3（H3）未得到支持（β=0.04）。如表3-2所示，样本以年轻会员为主"}],
                                       ["回收率为87.5%。"])],
                "not_asked": {c: "示例" for c in dc.CATEGORIES if c not in ("data", "contribution")}}
        self.bank(bank, claims=None)
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(len(out["fails"]), 1, out["fails"])
        self.assertTrue(out["fails"][0].startswith("Q2: NOT_FOUND: `87.5%`"))
        self.assertIn("`312` on printed page 2 (PDF page 5)", self.report)
        self.assertIn("Q1 anchor 1, display: 表 3.2 is on printed page 2 (PDF page 5)", self.report)


class SessionTests(Base):
    def setUp(self):
        super().setUp()
        self.thesis()
        self.bank()

    def turn(self, question, verdict, answer, gap=""):
        path = self.root / "answer.txt"
        path.write_text(answer, encoding="utf-8")
        return run("session", "--dir", str(self.dir), "--question", question, "--verdict", verdict,
                   "--answer-file", str(path), "--gap", gap)

    def test_a_solid_verdict_with_a_number_not_in_the_thesis_is_refused(self):     # DF-1: a number the thesis lacks
        code, out, _ = self.turn("Q2", "solid", "The response rate was about 90%, from 312 returns.")
        self.assertEqual((code, out["not_in_thesis"]), (1, ["90%"]))
        self.assertFalse((self.dir / "session.jsonl").exists())

    def test_a_weak_turn_is_logged_and_listed(self):
        code, out, _ = self.turn("Q2", "shaky", "The response rate was about 90%.", "used 90%; the thesis has 85.7%")
        self.assertEqual((code, out["turn"]), (0, 1))
        logged = json.loads((self.dir / "session.jsonl").read_text(encoding="utf-8"))
        self.assertEqual((logged["verdict"], logged["numbers"][0]["result"]), ("shaky", "not_in_thesis"))
        revision = (self.dir / "revision-list.md").read_text(encoding="utf-8")
        self.assertIn("## Chapter 3: Method", revision)
        self.assertIn("- **Q2** (data) How many questionnaires came back?", revision)
        self.assertIn("Gap: used 90%; the thesis has 85.7%", revision)
        self.assertIn("Numbers not in the thesis: 90%", revision)
        self.assertIn("| 85.7% | 45 | 57 |", revision)
        self.turn("Q2", "solid", "312 of 364 came back: 85.7%.")
        revision = (self.dir / "revision-list.md").read_text(encoding="utf-8")
        self.assertIn("2 turn(s) on 1 question(s) in session.jsonl; 0 still weak", revision)

    def test_a_weak_turn_needs_a_gap_and_a_known_question(self):
        self.assertEqual(self.turn("Q2", "stuck", "I do not remember.")[0], 1)
        self.assertEqual(self.turn("Q99", "stuck", "-", "gap")[0], 2)

    def test_chinese_answer(self):
        code, out, _ = self.turn("Q2", "wrong", "回收率约为90%，样本量为312人。", "回收率说错")
        self.assertEqual((code, out["not_in_thesis"]), (0, ["90%"]))
        self.assertEqual(out["numbers"][1]["result"], "in_thesis")


if __name__ == "__main__":
    unittest.main()
