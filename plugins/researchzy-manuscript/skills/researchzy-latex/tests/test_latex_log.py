"""latex_log.py: detect on small project trees, the log parser on real logs, PDF facts.

The logs in fixtures/ are excerpts of real pdfLaTeX, XeLaTeX, BibTeX and Biber runs on small broken
projects (paths replaced, package-loading noise removed, lines re-wrapped at 79 columns as TeX does),
so the parser tests need no TeX. The pdffonts and pdfinfo outputs were captured from Poppler; the
one test that runs Poppler skips when it is not installed.
"""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "latex_log.py"
spec = importlib.util.spec_from_file_location("latex_log", SCRIPT)
ll = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ll)

FIXTURES = Path(__file__).parent / "fixtures"
HAVE_POPPLER = bool(shutil.which("pdfinfo") and shutil.which("pdffonts"))


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ll.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def write(root: Path, files: dict) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def doc(preamble: str = "", body: str = "Text.") -> str:
    return f"\\documentclass{{article}}\n{preamble}\n\\begin{{document}}\n{body}\n\\end{{document}}\n"


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def parse(self, name, blg=None, extra=()):
        """Copy a fixture to main.log in a fresh folder and parse it; return (exit code, problems.json)."""
        work = self.dir / name.replace(".", "_")
        work.mkdir()
        shutil.copy(FIXTURES / name, work / "main.log")
        args = ["parse", str(work / "main.log"), "--out", str(work / "out"), *extra]
        if blg:
            shutil.copy(FIXTURES / blg, work / "main.blg")
        code, _, _ = run(*args)
        return code, json.loads((work / "out" / "problems.json").read_text(encoding="utf-8")), work

    def find(self, result, cls, text=""):
        return [p for p in result["problems"] if p["class"] == cls and text in p["message"]]

    def test_clean_build(self):
        code, result, work = self.parse("good.log", "good.blg")
        self.assertEqual((code, result["build"]["status"], result["problems"]), (0, "ok", []))
        self.assertEqual(result["build"]["pages"], 2)
        self.assertIn("No problems found", (work / "out" / "problems.md").read_text(encoding="utf-8"))

    def test_undefined_references_citations_duplicates_boxes_fonts(self):
        code, result, _ = self.parse("refs.log")
        self.assertEqual((code, result["build"]["status"]), (1, "incomplete"))
        cite = self.find(result, "undefined_citation", "nokey2020")[0]
        self.assertEqual((cite["count"], cite["locations"]), (2, ["main.tex:6", "main.tex:8"]))
        tab = self.find(result, "undefined_reference", "tab:missing")[0]
        self.assertEqual((tab["file"], tab["line"], tab["count"]), ("sections/method.tex", 3, 2))
        # A reference whose warning TeX wrapped over two lines keeps its whole key.
        self.assertTrue(self.find(result, "undefined_reference", "makes-the-warning-wrap-in-the-log"))
        self.assertTrue(self.find(result, "duplicate_label", "sec:intro"))
        boxes = self.find(result, "overfull")
        self.assertEqual(sorted(p["message"][:15] for p in boxes), ["Overfull \\hbox ", "Overfull \\vbox "])
        self.assertEqual(boxes[0]["file"], "sections/method.tex")       # the 1.2 pt box is under the threshold
        fonts = [p["message"] for p in self.find(result, "font")]
        self.assertTrue(any("OT1/cmr/bx/sc" in f for f in fonts) and any("Missing character" in f for f in fonts))

    def test_hbox_threshold_is_an_option(self):
        _, result, _ = self.parse("refs.log", extra=("--hbox-pt", "0.5"))
        self.assertEqual(len(self.find(result, "overfull")), 3)

    def test_duplicate_label_and_near_label_come_from_the_source(self):
        work = self.dir / "src"
        write(work, {"main.tex": "\\section{A}\\label{sec:intro}\n\\section{B}\n\\label{sec:intro}\n\\label{tab:mising}\n"})
        shutil.copy(FIXTURES / "refs.log", work / "main.log")
        run("parse", str(work / "main.log"), "--out", str(work / "out"))
        result = json.loads((work / "out" / "problems.json").read_text(encoding="utf-8"))
        self.assertEqual(self.find(result, "duplicate_label")[0]["locations"], ["main.tex:1", "main.tex:3"])
        self.assertIn("tab:mising", self.find(result, "undefined_reference", "tab:missing")[0]["hint"])

    def test_missing_package(self):
        code, result, _ = self.parse("missing-package.log")
        self.assertEqual((code, result["build"]["status"]), (1, "failed"))
        missing = self.find(result, "missing_file")[0]
        self.assertEqual((missing["kind"], missing["name"], missing["line"], missing.get("first")),
                         ("package", "lipsum.sty", 4, True))
        self.assertTrue(self.find(result, "error", "Emergency stop")[0]["possibly_caused_by_first"])

    def test_missing_figure_in_a_nested_file(self):
        _, result, _ = self.parse("missing-figure.log")
        missing = self.find(result, "missing_file")[0]
        self.assertEqual((missing["kind"], missing["file"], missing["line"]), ("graphics", "sections/results.tex", 4))

    def test_missing_figure_names_the_closest_file(self):
        work = self.dir / "fig"
        (work / "sections").mkdir(parents=True)
        (work / "figures").mkdir()
        (work / "figures" / "response_curve.pdf").write_bytes(b"%PDF")
        (work / "figures" / "plot.png").write_bytes(b"png")
        shutil.copy(FIXTURES / "missing-figure.log", work / "main.log")
        run("parse", str(work / "main.log"), "--out", str(work / "out"))
        result = json.loads((work / "out" / "problems.json").read_text(encoding="utf-8"))
        self.assertEqual(self.find(result, "missing_file")[0]["hint"], "closest existing file: figures/response_curve.pdf")
        (work / "figures" / "response-curves.png").write_bytes(b"png")
        run("parse", str(work / "main.log"), "--out", str(work / "out"))
        result = json.loads((work / "out" / "problems.json").read_text(encoding="utf-8"))
        self.assertIn("several close files", self.find(result, "missing_file")[0]["hint"])

    def test_include_of_a_missing_file_is_reported_but_not_the_first_error(self):
        _, result, _ = self.parse("include-input.log")
        include = self.find(result, "missing_file", "No file chapters/appendix.tex")[0]
        self.assertEqual(include["kind"], "input")
        self.assertNotIn("first", include)
        self.assertTrue(self.find(result, "missing_file", "sections/discussion.tex")[0]["first"])

    def test_undefined_control_sequences_and_their_cascade(self):
        for name in ("cascade.log", "cascade-no-file-line.log"):
            with self.subTest(name):
                code, result, _ = self.parse(name)
                errors = self.find(result, "error")
                self.assertEqual((code, result["build"]["status"]), (1, "failed"))
                self.assertEqual(errors[0]["message"], "Undefined control sequence \\SI")
                self.assertEqual((errors[0]["file"], errors[0]["line"], errors[0]["count"]), ("sections/method.tex", 2, 2))
                self.assertTrue(errors[0]["first"])
                self.assertIn("siunitx", errors[0]["hint"])
                self.assertTrue(all(e.get("possibly_caused_by_first") for e in errors[1:]))
                self.assertIn("booktabs", self.find(result, "error", "\\toprule")[0]["hint"])
                self.assertEqual(self.find(result, "error", "Missing $")[0]["line"], 8)
                self.assertEqual(sum(e["count"] for e in errors), 11)

    def test_runaway_argument(self):
        _, result, _ = self.parse("runaway.log")
        first = self.find(result, "error")[0]
        self.assertTrue(first["message"].startswith("Runaway argument: File ended while scanning use of \\textbf"))
        self.assertIn("dose was never closed", first["context"])

    def test_a_pdf_next_to_a_log_with_errors_is_a_failed_build(self):
        work = self.dir / "clash"
        work.mkdir()
        shutil.copy(FIXTURES / "clash-unicode.log", work / "main.log")
        (work / "main.pdf").write_bytes(b"%PDF-1.5\n")
        code, out, _ = run("parse", str(work / "main.log"), "--out", str(work / "out"))
        summary = json.loads(out)
        self.assertEqual((code, summary["build"]["status"]), (1, "failed"))
        self.assertIn("not a good build", " ".join(summary["build"]["notes"]))
        result = json.loads((work / "out" / "problems.json").read_text(encoding="utf-8"))
        self.assertIn("Option clash", self.find(result, "error")[0]["message"])
        self.assertIn("not set up for use with LaTeX", self.find(result, "error", "Unicode")[0]["message"])

    def test_xetex_missing_characters(self):
        _, result, _ = self.parse("xetex.log")
        self.assertEqual(len(self.find(result, "font", "Missing character")), 2)
        self.assertTrue(result["build"]["notes"][0].startswith("Engine: XeTeX"))

    def test_wrapped_paths_and_nested_files(self):
        _, result, _ = self.parse("wrapped.log")
        where = {p["key"]: p["file"] for p in self.find(result, "undefined_reference")}
        long_dir = "sections/a-rather-long-directory-name-for-the-methods-part/"
        self.assertEqual(where["tab:inner"], long_dir + "and-one-more-level/details.tex")
        self.assertEqual(where["fig:outer-after"], long_dir + "methods-overview.tex")
        self.assertEqual(where["sec:nowhere-either"], "main.tex")

    def test_an_unbalanced_parenthesis_in_an_overfull_line_does_not_break_the_file_stack(self):
        _, result, _ = self.parse("unbalanced-paren.log")
        where = {p["message"]: p["file"] for p in self.find(result, "undefined_reference")}
        self.assertEqual(where["Reference `sec:after-list' undefined"], "main.tex")
        self.assertEqual(self.find(result, "overfull")[0]["file"], "sections/list.tex")

    def test_bibtex_errors_from_the_blg(self):
        code, result, _ = self.parse("bibtex.log", "bibtex.blg")
        self.assertEqual((code, result["build"]["status"]), (1, "failed"))
        bib = {p["message"]: p for p in self.find(result, "bibliography")}
        expecting = next(p for m, p in bib.items() if "expecting a `,'" in m)
        self.assertEqual((expecting["file"], expecting["line"], expecting["severity"]), ("refs.bib", 9, "error"))
        self.assertTrue(any("Repeated entry" in m for m in bib))
        self.assertTrue(any("No file main.bbl" in m for m in bib))
        self.assertEqual(len(self.find(result, "undefined_citation")), 3)

    def test_biber_error_and_rerun(self):
        _, result, _ = self.parse("biber-error.log", "biber-error.blg")
        syntax = self.find(result, "bibliography", "Biber: syntax error")[0]
        self.assertEqual((syntax["file"], syntax["line"], syntax["severity"]), ("refs.bib", 10, "error"))
        rerun = self.find(result, "rerun_needed")
        self.assertEqual(len(rerun), 1)                      # the (biblatex) continuation lines are one warning
        self.assertIn("and rerun LaTeX afterwards", rerun[0]["message"])

    def test_biber_warnings(self):
        code, result, _ = self.parse("biber-warn.log", "biber-warn.blg")
        self.assertEqual((code, result["build"]["status"]), (1, "incomplete"))
        self.assertTrue(self.find(result, "bibliography", "Invalid format '2018-13-45'"))
        self.assertEqual([p["key"] for p in self.find(result, "undefined_citation")], ["nokey2020"])

    def test_no_log_is_not_checked(self):
        code, out, _ = run("parse", str(self.dir / "absent.log"), "--out", str(self.dir / "out"))
        self.assertEqual((code, json.loads(out)["build"]["status"]), (2, "not_checked"))
        self.assertIn("Nothing was checked", (self.dir / "out" / "problems.md").read_text(encoding="utf-8"))


class DetectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def detect(self, files, target=""):
        write(self.dir, files)
        code, out, _ = run("detect", str(self.dir / target))
        return code, json.loads(out)

    def test_main_file_is_the_one_nobody_inputs(self):
        code, result = self.detect({"main.tex": doc(body="\\input{sections/intro}"), "sections/intro.tex": "Intro.",
                                    "notes/old.tex": "\\section{Old}"})
        self.assertEqual((code, result["main"]), (0, "main.tex"))
        self.assertEqual(result["engine"]["value"], "pdflatex")
        self.assertEqual(result["latexmk"]["command"],
                         "latexmk -pdf -file-line-error -halt-on-error -interaction=nonstopmode main.tex")

    def test_several_candidates_are_listed_not_guessed(self):
        code, result = self.detect({"paper.tex": doc(), "response.tex": doc()})
        self.assertEqual((code, result["main"], result["latexmk"]), (1, None, None))
        self.assertEqual([c["file"] for c in result["candidates"]], ["paper.tex", "response.tex"])

    def test_a_figure_source_beside_the_paper_is_resolved_by_its_inputs(self):
        code, result = self.detect({"main.tex": doc(body="\\input{sec}\n\\bibliography{refs}"), "sec.tex": "Text.",
                                    "figures/plot-source.tex": doc(body="\\rule{1cm}{1cm}")})
        self.assertEqual((code, result["main"]), (0, "main.tex"))
        self.assertTrue(any("only it inputs other files" in n for n in result["notes"]))
        self.assertEqual(len(result["candidates"]), 2)

    def test_subfiles_and_standalone_are_not_the_paper(self):
        code, result = self.detect({"main.tex": doc(body="\\subfile{part}"), "part.tex": "\\documentclass[main]{subfiles}\n",
                                    "fig.tex": "\\documentclass{standalone}\n\\begin{document}x\\end{document}"})
        self.assertEqual((code, result["main"]), (0, "main.tex"))

    def test_engine_from_magic_comment_and_packages(self):
        _, result = self.detect({"main.tex": "% !TeX TS-program = xelatex\n" + doc("\\usepackage{fontspec}")})
        self.assertEqual((result["engine"]["value"], result["engine"]["conflict"]), ("xelatex", False))
        self.assertIn("-xelatex", result["latexmk"]["command"])

    def test_engine_from_package_alone(self):
        _, result = self.detect({"main.tex": doc("\\usepackage{luacode}")})
        self.assertEqual(result["engine"]["value"], "lualatex")

    def test_conflicting_signals_are_reported(self):
        code, result = self.detect({"main.tex": "% !TEX program = pdflatex\n" + doc("\\usepackage{unicode-math}")})
        self.assertEqual((code, result["engine"]["value"], result["engine"]["conflict"]), (1, None, True))
        self.assertIsNone(result["latexmk"])

    def test_latexmkrc_sets_engine_and_main_file(self):
        code, result = self.detect({"latexmkrc": "$pdf_mode = 5;  # xelatex\n@default_files = ('src/paper.tex');\n",
                                    "src/paper.tex": doc(), "other.tex": doc()})
        self.assertEqual((code, result["main"], result["engine"]["value"]), (0, "src/paper.tex", "xelatex"))
        self.assertEqual(result["latexmk"]["cwd"], str(self.dir.resolve()))
        self.assertTrue(result["latexmk"]["command"].endswith("src/paper.tex"))

    def test_bibliography_tools(self):
        cases = [(doc("\\usepackage[backend=biber]{biblatex}\n\\addbibresource{refs.bib}"), "biber"),
                 (doc("\\usepackage{biblatex}\n\\addbibresource{refs.bib}"), "biber"),
                 (doc("\\usepackage[backend=bibtex]{biblatex}\n\\addbibresource{refs.bib}"), "bibtex"),
                 (doc(body="\\bibliographystyle{plain}\n\\bibliography{refs}"), "bibtex"),
                 (doc(body="\\begin{thebibliography}{1}\\bibitem{a} A.\\end{thebibliography}"), None)]
        for index, (text, tool) in enumerate(cases):
            with self.subTest(tool=tool, index=index):
                folder = self.dir / f"case{index}"
                write(folder, {"main.tex": text, "refs.bib": "@misc{a, title={A}}"})
                result = json.loads(run("detect", str(folder))[1])
                self.assertEqual(result["bibliography"]["tool"], tool)

    def test_bbl_without_bib_is_used_as_it_is(self):
        _, result = self.detect({"ms.tex": doc(body="\\bibliographystyle{plain}\\bibliography{refs}"), "ms.bbl": "x"})
        self.assertEqual(result["bibliography"]["tool"], "bbl_only")
        self.assertIn("-bibtex-", result["latexmk"]["command"])

    def test_biblatex_with_natbib_is_a_conflict(self):
        code, result = self.detect({"main.tex": doc("\\usepackage{natbib}\n\\usepackage{biblatex}")})
        self.assertEqual((code, result["bibliography"]["conflict"]), (1, True))

    def test_shell_escape_is_named_not_added(self):
        _, result = self.detect({"main.tex": doc("\\usepackage{minted}")})
        self.assertNotIn("shell-escape", result["latexmk"]["command"])
        self.assertTrue(any("-shell-escape" in note for note in result["notes"]))

    def test_a_section_file_points_to_its_root(self):
        code, result = self.detect({"main.tex": doc(), "sec/a.tex": "% !TEX root = ../main.tex\n\\section{A}"}, "sec/a.tex")
        self.assertEqual(code, 0)
        self.assertTrue(result["main"].endswith("main.tex"))


class PdfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.pdf = self.dir / "paper.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pdffonts_rows_by_column_including_an_overflowing_name(self):
        rows = ll.parse_pdffonts((FIXTURES / "pdffonts-not-embedded.txt").read_text())
        self.assertEqual([r["emb"] for r in rows], ["no", "no", "no", "yes"])
        long_name = rows[1]
        self.assertEqual((long_name["name"], long_name["type"], long_name["encoding"]),
                         ("ArialNarrow-BoldItalicMT-WithAVeryLongPostScriptName", "TrueType", "WinAnsi"))
        self.assertEqual((rows[2]["type"], rows[2]["object ID"]), ("CID Type 0", "7  0"))

    def test_pdffonts_type3_rows(self):
        rows = ll.parse_pdffonts((FIXTURES / "pdffonts-type3.txt").read_text())
        self.assertEqual(sum(r["type"] == "Type 3" for r in rows), 7)
        self.assertEqual(rows[0]["name"], "[none]")

    def fake_tools(self, info="pdfinfo-two-sizes.txt", fonts="pdffonts-not-embedded.txt"):
        outputs = {"pdfinfo": (FIXTURES / info).read_text(), "pdffonts": (FIXTURES / fonts).read_text()}
        return mock.patch.object(ll, "run_tool", lambda name, pdf: (outputs[name], None))

    def facts(self, *args):
        code, out, err = run("pdf", str(self.pdf), "--out", str(self.dir / "out"), *args)
        return code, {f["fact"]: f for f in json.loads(out)["facts"]} if out else {}, err

    def test_facts_from_captured_output(self):
        with self.fake_tools():
            code, facts, _ = self.facts("--page-size", "a4")
        self.assertEqual(code, 1)
        self.assertEqual(facts["fonts_embedded"]["status"], "fail")
        self.assertIn("Helvetica (Type 1)", facts["fonts_embedded"]["detail"])
        self.assertEqual(facts["page_size"]["status"], "manual")      # page 2 is A4 turned sideways
        saved = json.loads((self.dir / "out" / "pdf-facts.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["facts"][0]["value"], 2)
        self.assertIn("Test Author", facts["properties"]["detail"])
        self.assertTrue((self.dir / "out" / "pdf-facts.md").is_file())

    def test_type3_is_manual(self):
        with self.fake_tools(fonts="pdffonts-type3.txt"):
            _, facts, _ = self.facts()
        self.assertEqual((facts["type3_fonts"]["status"], facts["fonts_embedded"]["status"]), ("manual", "pass"))

    def test_page_limit_needs_source_and_counted_pages(self):
        with self.fake_tools():
            code, _, err = self.facts("--max-pages", "1")
            self.assertEqual(code, 2)
            self.assertIn("--limit-source", err)
            _, facts, _ = self.facts("--max-pages", "1", "--limit-source", "kit guide, read 2026-11-13")
            self.assertEqual(facts["page_limit"]["status"], "manual")
            _, facts, _ = self.facts("--max-pages", "1", "--limit-source", "kit", "--content-pages", "2")
            self.assertEqual(facts["page_limit"]["status"], "fail")
            _, facts, _ = self.facts("--max-pages", "2", "--limit-source", "kit", "--content-pages", "2")
            self.assertEqual(facts["page_limit"]["status"], "pass")
            self.assertEqual(self.facts("--max-pages", "9", "--limit-source", "kit", "--content-pages", "3")[0], 2)

    def test_missing_poppler_is_not_checked_with_exit_2(self):
        with mock.patch.object(ll.shutil, "which", return_value=None):
            code, facts, _ = self.facts()
        self.assertEqual(code, 2)
        self.assertEqual({f["status"] for f in facts.values()}, {"not_checked"})

    def test_not_a_pdf(self):
        (self.dir / "x.pdf").write_text("hello")
        self.assertEqual(run("pdf", str(self.dir / "x.pdf"), "--out", str(self.dir / "out"))[0], 2)

    def test_page_size_argument(self):
        self.assertEqual(ll.expected_size("letter"), (612.0, 792.0))
        width, height = ll.expected_size("210x297")
        self.assertAlmostEqual(width, 595.28, places=1)
        self.assertAlmostEqual(height, 841.89, places=1)
        with self.assertRaises(ValueError):
            ll.expected_size("huge")

    @unittest.skipUnless(HAVE_POPPLER, "pdfinfo and pdffonts are not installed")
    def test_real_poppler_on_a_hand_made_pdf(self):
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
                   b"/Resources << /Font << /F1 5 0 R >> >> >>",
                   b"<< /Length 44 >>\nstream\nBT /F1 12 Tf 72 720 Td (Hello) Tj ET\nendstream",
                   b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        data, offsets = b"%PDF-1.4\n", []
        for number, body in enumerate(objects, 1):
            offsets.append(len(data))
            data += b"%d 0 obj\n%s\nendobj\n" % (number, body)
        xref = len(data)
        data += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
        data += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref
        self.pdf.write_bytes(data)
        code, facts, _ = self.facts("--page-size", "letter")
        self.assertEqual((code, facts["page_size"]["status"], facts["fonts_embedded"]["status"]), (1, "pass", "fail"))


if __name__ == "__main__":
    unittest.main()
