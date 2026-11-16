"""check_package.py: limits only from a sourced requirements file, statements, files, agreement, the letter."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_package.py"
spec = importlib.util.spec_from_file_location("check_package", SCRIPT)
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SOURCE = {"source": "guidelines.pdf p. 2", "date_read": "2026-11-13"}

MANUSCRIPT = """# Soil moisture memory shapes seedling survival

Mira Okafor, Tomas Lindqvist and Wen Hao

## Abstract

We tracked 1,240 oak seedlings across 18 plots for three seasons. Survival was 41% in plots with short memory and 68% in plots with long memory.

Keywords: drought; seedlings; soil moisture

## Introduction

Plantings fail in dry years [@smith2020] (Figure 1).

## Methods

We followed 1,240 seedlings in 18 plots (Table 1), approved by the Invented Ethics Board (IEB-2023-044).

Figure 1. Survival by plot.

| Plot | Memory |
|---|---|
| 1 | 4 |

Table 1. Plot characteristics of the eighteen plots.

## Results

Survival differed (Figure 2).

Figure 2. Survival against memory.

## Author contributions

M.O.: Conceptualization. T.L.: Formal analysis. W.H.: Writing – review & editing.

## Funding

Invented Science Foundation, grant ISF-2024-0117.

## Competing interests

The authors declare no competing interests.

## References

1. Smith A. Planting in dry years. 2020.
2. Doe J. Soil water. 2019.
3. Roe K. Memory. 2018.
"""

AUTHORS = {
    "authors": [
        {"name": "Mira Okafor", "initials": "M.O.", "affiliations": ["Department of Ecology, Invented University, Northtown"],
         "email": "m.okafor@invented.example", "corresponding": True, "roles": ["Conceptualization"],
         "competing_interests": "none"},
        {"name": "Tomas Lindqvist", "affiliations": ["Department of Ecology, Invented University, Northtown"],
         "roles": ["Formal analysis"], "competing_interests": "none"},
        {"name": "Wen Hao", "affiliations": ["Institute of Soils, Example Institute, Southport"],
         "roles": ["Writing – review & editing"], "competing_interests": "none"},
    ],
    "funding": [{"funder": "Invented Science Foundation", "grant_number": "ISF-2024-0117"}],
    "ethics": [{"body": "Invented Ethics Board", "approval_id": "IEB-2023-044"}],
    "registrations": [],
    "ai_use": "No AI tools were used (confirmed by all authors on 2026-11-12).",
}

TITLE_PAGE = """# Soil moisture memory shapes seedling survival

Mira Okafor^1,\\*^, Tomas Lindqvist^1^, Wen Hao^2^

^1^ Department of Ecology, Invented University, Northtown
^2^ Institute of Soils, Example Institute, Southport

\\* Corresponding author: m.okafor@invented.example

Funding: Invented Science Foundation, grant ISF-2024-0117.
"""

LETTER = """Dear Editor,

Please consider "Soil moisture memory shapes seedling survival" as a research article.

The manuscript has 2 figures and 1 table, and the abstract has 26 words.

The authors declare no competing interests.
"""


def requirements(**extra) -> dict:
    data = {"venue": "Journal of Invented Ecology (invented)", "article_type": "Research article",
            "stage": "initial submission", "source": "guidelines.pdf", "date_read": "2026-11-13",
            "review_model": "single-blind", "limits": [], "required_statements": [], "required_files": [],
            "deliverables": []}
    data.update(extra)
    return data


def docx(paragraphs, tables=(), core: str = "") -> bytes:
    """A .docx from (style, text) pairs and tables given as lists of rows."""
    def para(style, text):
        props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f"<w:p>{props}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"
    body = "".join(para(s, t) for s, t in paragraphs)
    body += "".join("<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc>{para('', c)}</w:tc>" for c in row) + "</w:tr>"
                                         for row in table) + "</w:tbl>" for table in tables)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
        if core:
            archive.writestr("docProps/core.xml", core)
    return buffer.getvalue()


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.package = self.root / "submission" / "invented"
        self.package.mkdir(parents=True)
        self.manuscript = self.root / "paper.md"
        self.manuscript.write_text(MANUSCRIPT, encoding="utf-8")
        self.write("authors.json", json.dumps(AUTHORS))
        self.write("requirements.json", json.dumps(requirements()))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        path = self.package / name
        path.write_bytes(content) if isinstance(content, bytes) else path.write_text(content, encoding="utf-8")
        return path

    def run_check(self, *extra, manuscript=None, reqs=None, authors=None):
        if reqs is not None:
            self.write("requirements.json", json.dumps(reqs))
        if authors is not None:
            self.write("authors.json", json.dumps(authors))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cp.main([str(manuscript or self.manuscript), "--package", str(self.package), *extra])
        self.err = err.getvalue()
        return code, (json.loads(out.getvalue()) if out.getvalue() else None)

    def row(self, result, name):
        return next(r for r in result["checks"] if r["check"] == name)

    # ---- limits -------------------------------------------------------------------------------

    def test_a_limit_is_applied_only_with_its_source_and_date(self):
        limits = [{"name": "abstract_words", "value": 20, **SOURCE},
                  {"name": "keywords", "value": 5, **SOURCE},
                  {"name": "title_characters", "value": 30, "source": ""},
                  {"name": "references", "value": 2, "source": "guidelines.pdf"},          # date from the file
                  {"name": "figures", "min": 1, "value": 4, **SOURCE},
                  {"name": "abstract_words", "source": "guidelines.pdf p. 2", "date_read": "2026-11-13"},
                  {"name": "pages", "value": 10, **SOURCE}]
        code, result = self.run_check(reqs=requirements(limits=limits))
        self.assertEqual(code, 1)
        rows = [r for r in result["checks"] if r["check"].startswith("limit:")]
        self.assertEqual([r["state"] for r in rows], ["fail", "pass", "not_checked", "fail", "pass", "not_checked", "not_checked"])
        self.assertIn("26 words", rows[0]["detail"])
        self.assertIn("no source", rows[2]["detail"])
        self.assertIn("3 references", rows[3]["detail"])
        self.assertIn("gives no number", rows[5]["detail"])
        self.assertIn("does not measure", rows[6]["detail"])
        no_date = requirements(limits=[{"name": "keywords", "value": 5, "source": "guidelines.pdf"}], date_read="")
        _, result = self.run_check(reqs=no_date)
        self.assertEqual(self.row(result, "limit: keywords")["state"], "not_checked")
        self.assertEqual(self.row(result, "requirements")["state"], "not_checked")

    def test_main_text_scope_and_counts(self):
        _, result = self.run_check()
        measured = result["measured"]
        # headings Introduction, Methods, Results and their prose; not the caption, table or statements
        self.assertEqual(measured["main_text_words"], 1 + 7 + 1 + 16 + 1 + 4)
        self.assertEqual((measured["figures"], measured["tables"], measured["references"], measured["keywords"]),
                         (2, 1, 3, 3))
        self.assertEqual((measured["abstract_words"], measured["title_characters"]), (26, 45))
        limits = [{"name": "main_text_words", "value": 1000, "include": ["captions"], **SOURCE}]
        _, result = self.run_check(reqs=requirements(limits=limits))
        self.assertEqual(result["measured"]["main_text_words"], 30 + 5 + 8 + 5)
        self.assertIn("plus captions", self.row(result, "limit: main_text_words")["detail"])
        code, _ = self.run_check(reqs=requirements(limits=[{"name": "main_text_words", "include": ["figures"], **SOURCE}]))
        self.assertEqual(code, 2)

    def test_highlights_and_package_file_limits(self):
        self.write("highlights.md", "- Short one\n- A highlight that is far too long for the limit given here\n")
        self.write("cover-letter.md", LETTER)
        limits = [{"name": "highlights_count", "min": 3, "value": 5, **SOURCE},
                  {"name": "highlight_characters", "value": 30, **SOURCE},
                  {"name": "cover_letter_words", "value": 20, **SOURCE}]
        _, result = self.run_check(reqs=requirements(limits=limits))
        self.assertEqual(self.row(result, "limit: highlights_count")["state"], "fail")
        chars = self.row(result, "limit: highlight_characters")
        self.assertEqual(chars["state"], "fail")
        self.assertEqual(len(chars["where"]), 1)
        self.assertEqual(self.row(result, "limit: cover_letter_words")["state"], "fail")

    def test_a_latex_manuscript(self):
        tex = self.root / "paper.tex"
        tex.write_text(r"""\documentclass{article}
\title{Soil moisture memory shapes seedling survival}
\author{Mira Okafor \and Tomas Lindqvist \and Wen Hao}
\begin{document}
\maketitle
\begin{abstract}
We tracked oak seedlings in plots. % a comment that is not counted at all here
\end{abstract}
\section{Introduction}
Plantings fail in dry years \cite{smith2020,doe2019}.
\begin{figure}\includegraphics{f1}\caption{Survival by plot.}\end{figure}
\begin{table}\caption{Plots.}\begin{tabular}{l}A\end{tabular}\end{table}
\section*{Funding}
Invented Science Foundation, grant ISF-2024-0117.
\begin{thebibliography}{9}
\bibitem{smith2020} Smith. 2020.
\bibitem{doe2019} Doe. 2019.
\end{thebibliography}
\appendix
\section{Extra}
\begin{figure}\caption{Not counted.}\end{figure}
\end{document}
""", encoding="utf-8")
        _, result = self.run_check(manuscript=tex, reqs=requirements(required_statements=["funding"]))
        measured = result["measured"]
        self.assertEqual((measured["abstract_words"], measured["main_text_words"]), (6, 1 + 5))
        self.assertEqual((measured["figures"], measured["tables"], measured["references"]), (1, 1, 2))
        self.assertEqual(measured["title_characters"], 45)
        self.assertEqual(self.row(result, "statement: funding")["state"], "pass")
        tex.write_text(tex.read_text(encoding="utf-8").replace("\\section{Introduction}", "\\input{intro}"), encoding="utf-8")
        _, result = self.run_check(manuscript=tex, reqs=requirements(limits=[{"name": "main_text_words", "value": 9, **SOURCE}]))
        self.assertEqual(self.row(result, "limit: main_text_words")["state"], "not_checked")
        self.assertIn("\\input", self.row(result, "limit: main_text_words")["detail"])

    def test_a_docx_manuscript(self):
        paper = self.root / "paper.docx"
        paper.write_bytes(docx([("Title", "Soil moisture memory shapes seedling survival"), ("", "Mira Okafor"),
                                ("Heading1", "Abstract"), ("", "We tracked oak seedlings in plots."),
                                ("Heading1", "Introduction"), ("", "Plantings fail in dry years."),
                                ("", "Table 1. Plots."), ("Heading1", "Funding"), ("", "None.")],
                               tables=[[["Plot", "Memory"], ["1", "4"]]]))
        _, result = self.run_check(manuscript=paper, reqs=requirements(required_statements=["funding", "ethics"]))
        measured = result["measured"]
        self.assertEqual((measured["abstract_words"], measured["main_text_words"], measured["tables"]), (6, 1 + 5, 1))
        self.assertEqual(self.row(result, "statement: funding")["state"], "pass")
        self.assertEqual(self.row(result, "statement: ethics")["state"], "fail")

    # ---- statements, files, deliverables, placeholders -----------------------------------------

    def test_statements_by_heading_or_run_in_label(self):
        self.write("declarations.md", "**Data availability:** [Author input needed: repository and accession]\n\n"
                                      "**Declaration of generative AI use:** None was used.\n")
        required = ["funding", "competing_interests", "data_availability", "ai_use", "code_availability",
                    {"name": "patient_consent", "headings": ["Patient consent"]}, "made_up"]
        _, result = self.run_check(reqs=requirements(required_statements=required))
        states = {r["check"]: r["state"] for r in result["checks"] if r["check"].startswith("statement:")}
        self.assertEqual(states, {"statement: funding": "pass", "statement: competing_interests": "pass",
                                  "statement: data_availability": "fail", "statement: ai_use": "pass",
                                  "statement: code_availability": "fail", "statement: patient_consent": "fail",
                                  "statement: made_up": "not_checked"})
        self.assertIn("placeholder", self.row(result, "statement: data_availability")["detail"])

    def test_required_files_and_deliverables(self):
        self.write("cover-letter.md", LETTER)
        self.write("figure1.tiff", b"x" * 2_000_000)
        self.write("graphical-abstract.png", b"png")
        files = [{"name": "cover letter", "pattern": "cover-letter.*", "extensions": ["docx", "pdf"]},
                 {"name": "figures", "pattern": "figure*", "extensions": ["tiff"], "max_mb": 1},
                 {"name": "letter", "pattern": "cover-letter.*", "extensions": [".MD"]}]
        deliverables = [{"name": "cover-letter", "status": "required"}, {"name": "highlights", "status": "required"},
                        {"name": "graphical-abstract", "status": "not_accepted"},
                        {"name": "video", "status": "optional"}, {"name": "x", "status": "maybe"}]
        _, result = self.run_check(reqs=requirements(required_files=files, deliverables=deliverables))
        self.assertEqual([r["state"] for r in result["checks"] if r["check"].startswith("file:")], ["fail", "fail", "pass"])
        self.assertIn("over the maximum", self.row(result, "file: figures")["where"][0])
        self.assertEqual([r["state"] for r in result["checks"] if r["check"].startswith("deliverable:")],
                         ["pass", "fail", "fail", "pass", "not_checked"])

    def test_placeholders_fail_only_a_final_run(self):
        self.write("cover-letter.md", LETTER + "\n[Author input needed: the editor's name]\n")
        code, result = self.run_check()
        placeholders = self.row(result, "placeholders")
        self.assertEqual((code, placeholders["state"]), (0, "not_checked"))
        self.assertEqual(placeholders["where"], ["cover-letter.md:9: [Author input needed: the editor's name]"])
        code, result = self.run_check("--final")
        self.assertEqual((code, self.row(result, "placeholders")["state"]), (1, "fail"))
        report = (self.package / "report.md").read_text(encoding="utf-8")
        self.assertIn("Fill or remove the placeholder at cover-letter.md:9", report)

    # ---- agreement ------------------------------------------------------------------------------

    def test_a_consistent_package_passes(self):
        self.write("title-page.md", TITLE_PAGE)
        self.write("cover-letter.md", LETTER)
        code, result = self.run_check(reqs=requirements(required_statements=["author_contributions", "funding"]))
        failed = [r for r in result["checks"] if r["state"] == "fail"]
        self.assertEqual((code, failed), (0, []))
        for name in ("agreement: title on the title page", "agreement: title in the letter",
                     "agreement: authors on the title page", "agreement: byline of the manuscript",
                     "agreement: CRediT roles", "agreement: initials in the contributions statement",
                     "agreement: funders and grant numbers", "agreement: ethics approval ids",
                     "agreement: competing interests", "letter: numbers about the manuscript",
                     "letter: sentences repeating the abstract", "letter: priority words"):
            self.assertEqual(self.row(result, name)["state"], "pass", name)
        self.assertEqual(self.row(result, "agreement: registration ids")["state"], "not_checked")

    def test_title_authors_and_order_disagree(self):
        page = TITLE_PAGE.replace("Tomas Lindqvist^1^, Wen Hao^2^", "Wen Hao^2^, Tomas Lindqvist^1^")
        page = page.replace("m.okafor@invented.example", "someone@else.example").replace("Example Institute", "Other")
        self.write("title-page.md", page)
        self.write("cover-letter.md", LETTER.replace("Soil moisture memory shapes", "Soil memory shapes"))
        self.manuscript.write_text(MANUSCRIPT.replace("Tomas Lindqvist and Wen Hao", "Wen Hao and Tomas Lindqvist"),
                                   encoding="utf-8")
        _, result = self.run_check()
        self.assertEqual(self.row(result, "agreement: title in the letter")["state"], "fail")
        where = self.row(result, "agreement: authors on the title page")["where"]
        self.assertTrue(any("order differs" in w for w in where))
        self.assertTrue(any("Institute of Soils, Example Institute, Southport" in w for w in where))
        self.assertTrue(any("email" in w for w in where))
        self.assertEqual(self.row(result, "agreement: byline of the manuscript")["state"], "fail")

    def test_credit_roles_and_initials(self):
        authors = json.loads(json.dumps(AUTHORS))
        authors["authors"][1]["roles"] = ["Statistical analysis"]
        authors["authors"][2]["roles"] = []
        authors["authors"].append({"name": "Mark Owens", "roles": ["Writing – original draft preparation"]})
        self.manuscript.write_text(MANUSCRIPT.replace("T.L.: Formal analysis.", "T.L. and J.Q.: Formal analysis."),
                                   encoding="utf-8")
        _, result = self.run_check(authors=authors)
        credit = self.row(result, "agreement: CRediT roles")
        self.assertEqual(credit["state"], "fail")
        self.assertIn('Tomas Lindqvist: "Statistical analysis" is not one of the 14 CRediT terms; the closest is '
                      "Formal analysis", credit["where"])
        self.assertIn("Wen Hao has no role", credit["where"])
        self.assertFalse(any("Mark Owens" in w for w in credit["where"]))      # "… preparation" is the same term
        initials = self.row(result, "agreement: initials in the contributions statement")
        self.assertEqual(initials["state"], "fail")
        self.assertTrue(any("M.O. fits 2 authors" in w for w in initials["where"]))
        self.assertTrue(any("J.Q. fits no author" in w for w in initials["where"]))

    def test_an_author_missing_from_the_contributions(self):
        self.manuscript.write_text(MANUSCRIPT.replace(" W.H.: Writing – review & editing.", ""), encoding="utf-8")
        _, result = self.run_check()
        where = self.row(result, "agreement: initials in the contributions statement")["where"]
        self.assertEqual(where, ["paper.md:33: Wen Hao (WH) has no contribution in the statement"])

    def test_grant_number_and_ids_must_match(self):
        self.write("title-page.md", TITLE_PAGE.replace("ISF-2024-0117", "ISF-2024-0171"))
        self.write("cover-letter.md", LETTER + "\nThe study was approved (IEB-2023-04).\n")
        authors = dict(AUTHORS, registrations=[{"registry": "OSF", "id": "OSF-REG-7781"}])
        _, result = self.run_check(authors=authors)
        funding = self.row(result, "agreement: funders and grant numbers")
        self.assertEqual(funding["state"], "fail")
        self.assertIn("title-page.md:10: grant number ISF-2024-0117 is not in this funding statement", funding["where"])
        self.assertIn("title-page.md:10: ISF-2024-0171 differs from ISF-2024-0117 in authors.json", funding["where"])
        ethics = self.row(result, "agreement: ethics approval ids")
        self.assertIn("cover-letter.md:9: IEB-2023-04 differs from IEB-2023-044 in authors.json", ethics["where"])
        self.assertIn("OSF-REG-7781 is in authors.json but in no document",
                      self.row(result, "agreement: registration ids")["where"])

    def test_competing_interests_that_contradict(self):
        self.write("cover-letter.md", LETTER.replace("The authors declare no competing interests.",
                                                     "Competing interests: T.L. received consulting fees from Example Corp."))
        _, result = self.run_check()
        row = self.row(result, "agreement: competing interests")
        self.assertEqual(row["state"], "fail")
        self.assertIn("cover-letter.md:7: declares an interest", row["where"])
        self.assertIn("paper.md:41: says there is none", row["where"])

    # ---- the letter -----------------------------------------------------------------------------

    def test_letter_numbers_repeats_and_priority_words(self):
        letter = LETTER.replace("2 figures and 1 table", "3 figures, 2 supplementary tables and 4 tables")
        letter = letter.replace("26 words", "40 words")
        letter += ("\nWe tracked 1,240 oak seedlings across 18 plots for three seasons. In total 1,300 participants "
                   "took part. This is the first study of its kind and a novel result.\n")
        self.write("cover-letter.md", letter)
        _, result = self.run_check()
        numbers = self.row(result, "letter: numbers about the manuscript")
        self.assertEqual(numbers["state"], "fail")
        text = " ".join(numbers["where"])
        for expected in ("states 3 figures; measured 2", "states 4 tables; measured 1",
                         "states 40 words in the abstract; measured 26", "sample size of 1,300"):
            self.assertIn(expected, text)
        self.assertNotIn("2 tables", text)                 # supplementary tables are not the manuscript's tables
        repeats = self.row(result, "letter: sentences repeating the abstract")
        self.assertEqual(repeats["state"], "fail")
        self.assertEqual(len(repeats["where"]), 1)
        self.assertIn("1 of the letter's", repeats["detail"])
        priority = self.row(result, "letter: priority words")
        self.assertEqual(priority["state"], "not_checked")
        self.assertEqual([w.split('"')[1] for w in priority["where"]], ["the first", "novel"])

    def test_a_quoted_limit_is_not_a_count(self):
        self.write("cover-letter.md", LETTER.replace("the abstract has 26 words", "the abstract is under 250 words"))
        _, result = self.run_check()
        self.assertEqual(self.row(result, "letter: numbers about the manuscript")["state"], "pass")

    # ---- report, gaps, usage --------------------------------------------------------------------

    def test_report_and_what_the_authors_still_owe(self):
        authors = json.loads(json.dumps(AUTHORS))
        authors["authors"][2]["competing_interests"] = "[Author input needed: W.H.'s interests]"
        authors["ai_use"] = ""
        _, result = self.run_check(authors=authors, reqs=requirements(review_model="double-blind"))
        self.assertIn("Wen Hao: competing interests, or confirmation that there are none", result["for_authors"])
        self.assertTrue(any(item.startswith("AI use:") for item in result["for_authors"]))
        self.assertEqual(self.row(result, "anonymity")["state"], "not_checked")
        report = (self.package / "report.md").read_text(encoding="utf-8")
        self.assertIn("Internal working report. Do not upload it", report)
        self.assertIn("| agreement: CRediT roles | `pass` |", report)
        self.assertIn("## For the authors: still to supply or confirm", report)

    def test_bad_input_exits_2(self):
        self.write("requirements.json", "{not json")
        code, _ = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", self.err)
        self.write("requirements.json", json.dumps(requirements()))
        self.write("authors.json", json.dumps({"authors": [{"email": "x@y"}]}))
        self.assertEqual(self.run_check()[0], 2)
        self.assertEqual(self.run_check(manuscript=self.root / "missing.md")[0], 2)

    def test_author_block_numbers_affiliations_by_first_appearance(self):
        block = cp.author_block([{"name": "A One", "affiliations": ["Uni B", "Uni A"], "corresponding": True,
                                  "email": "a@b.example"},
                                 {"name": "B Two", "affiliations": ["Uni A", "Uni C"], "equal_contribution": True},
                                 {"name": "C Three", "affiliations": ["Uni C"], "equal_contribution": True}])
        lines = block.splitlines()
        self.assertEqual(lines[0], "A One^1,2,\\*^, B Two^2,3,†^, C Three^3,†^")
        self.assertEqual(lines[2:5], ["^1^ Uni B", "^2^ Uni A", "^3^ Uni C"])
        self.assertIn("\\* Corresponding author: A One, a@b.example", lines)


if __name__ == "__main__":
    unittest.main()
