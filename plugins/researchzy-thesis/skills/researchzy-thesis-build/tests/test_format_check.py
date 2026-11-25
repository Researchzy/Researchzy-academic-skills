"""format_check.py: quotes of the rules record are in the rules text; a .docx and a PDF are measured against it."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fc = load("format_check", HERE.parent / "scripts" / "format_check.py")
fx = load("thesis_fixture", HERE / "thesis_fixture.py")
PYMUPDF = fc.pymupdf()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "thesis-build"

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = fc.main([*argv, "--dir", str(self.out)])
            except SystemExit as exc:
                code = exc.code
        return code, (json.loads(out.getvalue()) if out.getvalue().strip() else None), err.getvalue()

    def table(self, name: str) -> list:
        """The rows of a report's first table as (check, where, state, detail)."""
        rows, inside = [], False
        for line in (self.out / name).read_text(encoding="utf-8").splitlines():
            if line.startswith("| Check |"):
                inside = True
            elif inside and line.startswith("| ") and not line.startswith("|---"):
                rows.append(tuple(cell.strip() for cell in line[2:-2].split(" | ")))
            elif inside and not line.startswith("|"):
                break
        return rows

    def find(self, rows: list, check: str, state: str = None) -> list:
        return [row for row in rows if row[0] == check and (state is None or row[2] == state)]


class ValueTests(unittest.TestCase):
    def test_sizes_lengths_and_spacing_as_the_record_writes_them(self):
        self.assertEqual(fc.size_pt("小四"), 12)
        self.assertEqual(fc.size_pt("小四号"), 12)
        self.assertEqual(fc.size_pt("五号"), 10.5)
        self.assertEqual(fc.size_pt("12 pt"), 12)
        self.assertAlmostEqual(fc.length_mm("2.5 cm"), 25)
        self.assertAlmostEqual(fc.length_mm("3厘米"), 30)
        self.assertAlmostEqual(fc.length_mm("1 in"), 25.4)
        self.assertEqual(fc.page_dims("210 x 297 mm"), (210, 297))
        self.assertEqual(fc.spacing("1.5 lines"), ("multiple", 1.5))
        self.assertEqual(fc.spacing("exactly 20 pt"), ("exact", 20))
        self.assertEqual(fc.indent("2 characters"), ("chars", 2))
        self.assertIsNone(fc.size_pt("large"))

    def test_font_names_match_across_chinese_and_postscript_names(self):
        self.assertTrue(fc.same_font("宋体", "SimSun"))
        self.assertTrue(fc.same_font("ABCDEF+SimSun", "宋体"))
        self.assertTrue(fc.same_font("TimesNewRomanPSMT", "Times New Roman"))
        self.assertTrue(fc.same_font("TimesNewRomanPS-BoldMT", "Times New Roman"))
        self.assertFalse(fc.same_font("黑体", "宋体"))
        self.assertFalse(fc.same_font("Times-Roman", "Times New Roman"))


class RulesTests(Base):
    def test_quotes_match_across_spaces_breaks_and_full_width_brackets(self):
        fx.write_rules(self.out)
        code, result, _ = self.cli("rules", str(self.out / "rules.txt"))
        self.assertEqual(code, 0)
        self.assertEqual(result["no_text_pages"], [3])
        self.assertEqual(sorted(result["conflicts_pending"]), ["citation_style", "reference_standard"])
        rows = self.table("rules-check.md")
        self.assertIn("page 1", self.find(rows, "margins", "pass")[0][3])
        self.assertIn("page 2", self.find(rows, "page_numbers", "pass")[0][3])
        self.assertTrue(self.find(rows, "line_spacing", "not_checked"))
        self.assertTrue(self.find(rows, "first_line_indent", "manual"))
        self.assertIn("Conflict", self.find(rows, "citation_style")[0][3])
        self.assertIn("Pages without a text layer: 3", (self.out / "rules-check.md").read_text(encoding="utf-8"))

    def test_a_quote_that_is_not_in_the_text_fails(self):
        record = fx.rules_record()
        record["rules"][3]["quote"] = "正文字号为五号字"
        fx.write_rules(self.out, record)
        code, result, _ = self.cli("rules", str(self.out / "rules.txt"))
        self.assertEqual(code, 1)
        self.assertEqual(result["failed"], ["body_size: p. 1, 第四条"])

    def test_a_quote_too_short_to_prove_anything_fails(self):
        record = fx.rules_record()
        record["rules"][3]["quote"] = "小四号"
        fx.write_rules(self.out, record)
        code, _, _ = self.cli("rules", str(self.out / "rules.txt"))
        self.assertEqual(code, 1)
        self.assertIn("Too short", self.find(self.table("rules-check.md"), "body_size", "fail")[0][3])

    def test_a_record_that_misses_a_topic_or_has_a_bad_value_is_refused(self):
        record = fx.rules_record()
        record["rules"] = [r for r in record["rules"] if r["topic"] != "citation_style"]
        record["rules"][1]["value"] = "3cm"
        fx.write_rules(self.out, record)
        code, _, err = self.cli("rules", str(self.out / "rules.txt"))
        self.assertEqual(code, 2)
        self.assertIn("topic citation_style is missing", err)
        self.assertIn("rules[margins].value", err)

    def test_a_pdf_given_as_the_rules_text_is_refused_with_the_command_to_convert_it(self):
        fx.write_rules(self.out)
        pdf = self.dir / "rules.pdf"
        pdf.write_bytes(b"%PDF-1.4\n\xff\xfe\x00binary")
        code, _, err = self.cli("rules", str(pdf))
        self.assertEqual(code, 2)
        self.assertIn("pdftotext", err)


class DocxTests(Base):
    def setUp(self):
        super().setUp()
        self.docx = fx.make_docx(self.dir / "thesis.docx", fx.THESIS_BODY)
        fx.write_rules(self.out)

    def test_styles_resolve_through_defaults_the_based_on_chain_and_the_theme(self):
        d = fc.read_docx(self.docx)
        body_text = {**d["defaults"], **fc.chain(d["styles"], "BodyText")}
        self.assertEqual((body_text["east_asian"], body_text["latin"], body_text["size"]), ("宋体", "Times New Roman", 12))
        self.assertEqual((body_text["line"], body_text["indent"]), (("multiple", 1.5), ("chars", 2.0)))
        plain = {**d["defaults"], **fc.chain(d["styles"], "Plain")}
        self.assertEqual((plain["east_asian"], plain["latin"], plain["size"]), ("等线", "Calibri", 10.5))
        heading = {**d["defaults"], **fc.chain(d["styles"], "3")}
        self.assertEqual((heading["east_asian"], heading["outline"], heading["num"]), ("黑体", 2, ("1", 2)))

    def test_east_asian_and_latin_fonts_are_read_apart(self):
        paragraph = fc.read_docx(self.docx)["paras"][15]
        text, effective, direct = paragraph["runs"][0]
        self.assertEqual(direct, {"east_asian": "楷体"})
        self.assertEqual((effective["east_asian"], effective["latin"]), ("楷体", "Times New Roman"))

    def test_every_section_is_read(self):
        sections = fc.read_docx(self.docx)["sections"]
        self.assertEqual(len(sections), 5)
        self.assertEqual([round(s["mar"]["left"]) for s in sections], [30, 30, 30, 25, 30])
        self.assertEqual([s["shows"] for s in sections], [False, True, True, True, True])
        self.assertEqual([s["start"] for s in sections], [None, None, 1, 1, None])

    def test_the_planted_problems_of_tb1_fail_and_the_rest_does_not(self):
        code, result, _ = self.cli("docx", str(self.docx))
        self.assertEqual(code, 1)
        self.assertEqual(result["main_starts"], 7)
        rows = self.table("docx-check.md")
        # 1. 11 pt body text kept by direct formatting; the reference list in 10.5 pt is not body text
        size = self.find(rows, "body_size", "fail")
        self.assertEqual([row[1] for row in size], ["¶ 13–14"])
        self.assertTrue(self.find(rows, "body_size", "pass"))
        # East Asian font changed on its own; the Latin font of the same paragraph still agrees
        self.assertEqual([row[1] for row in self.find(rows, "body_font.east_asian", "fail")], ["¶ 16"])
        self.assertFalse(self.find(rows, "body_font.latin", "fail"))
        # 2. arabic front matter, and numbering that restarts in chapter 2
        self.assertIn("section 2: arabic", self.find(rows, "page_numbers.front", "fail")[0][3])
        main = self.find(rows, "page_numbers.main", "fail")[0][3]
        self.assertIn("section 4 (¶ 11–17) restarts at 1", main)
        self.assertNotIn("section 3 (", main)
        # 3. a typed "2.1" on automatic numbering, and a skipped level; the typed 第2章 without numbering is fine
        typed = self.find(rows, "typed_heading_numbers", "fail")[0][3]
        self.assertIn("2.1 研究设计", typed)
        self.assertNotIn("第2章", typed)
        self.assertIn("¶ 12", self.find(rows, "heading_levels", "fail")[0][3])
        # the narrower binding margin is in section 4 only
        self.assertEqual([row[1] for row in self.find(rows, "margins", "fail")], ["section 4 (¶ 11–17)"])
        self.assertIn("section 5 (¶ 18–19)", self.find(rows, "margins", "pass")[0][1])
        # a rule on the scanned page stays not_checked although the value was measured
        spacing = self.find(rows, "line_spacing")[0]
        self.assertEqual(spacing[2], "not_checked")
        self.assertIn("multiple 1.5", spacing[3])
        # a value seen only in the template passes as such, and is labelled so
        self.assertIn("which no written rule states", self.find(rows, "first_line_indent", "pass")[0][3])
        self.assertTrue(self.find(rows, "contents_field", "pass"))
        self.assertTrue(self.find(rows, "field_balance", "pass"))
        report = (self.out / "docx-check.md").read_text(encoding="utf-8")
        self.assertIn("| Normal (a) | 10 | 宋体 | Times New Roman | 12 pt | multiple 1.5 | 2 characters |  | ¶ 13–14, 16, 19 |", report)

    def test_front_matter_without_a_section_break_shares_the_arabic_numbering(self):
        body = (fx.para("摘要", "1", ppr='<w:numPr><w:numId w:val="0"/></w:numPr>') + fx.body_para("摘要正文，没有分节。")
                + fx.para("绪论", "1") + fx.body_para("第一章正文。") + fx.sect(footer="rIdFooter1"))
        code, _, _ = self.cli("docx", str(fx.make_docx(self.dir / "one-section.docx", body)))
        rows = self.table("docx-check.md")
        self.assertEqual(code, 1)
        self.assertEqual(self.find(rows, "page_numbers.front", "fail")[0][1], "sections 1")
        self.assertIn("chapter 1 shares section 1 with the front matter", self.find(rows, "page_numbers.main", "fail")[0][3])

    def test_a_field_whose_end_was_cut_fails(self):
        body = fx.THESIS_BODY.replace(fx.para("第一章的最后一段正文。", "a", ppr=fx.sect(start=1)), fx.para(
            style="a", ppr=fx.sect(start=1), runs=fx.field(" ADDIN ZOTERO_ITEM CSL_CITATION {} ", "(Wang, 2021)", end=False)))
        code, _, _ = self.cli("docx", str(fx.make_docx(self.dir / "cut.docx", body)))
        self.assertEqual(code, 1)
        self.assertIn("1 field mark(s) without a partner", self.find(self.table("docx-check.md"), "field_balance", "fail")[0][3])

    def test_without_rules_the_structure_is_still_checked(self):
        (self.out / "rules.json").unlink()
        code, _, _ = self.cli("docx", str(self.docx))
        rows = self.table("docx-check.md")
        self.assertEqual(code, 1)
        self.assertTrue(all(row[2] == "not_checked" for row in self.find(rows, "body_size")))
        self.assertIn("no rules.json", self.find(rows, "body_size")[0][3])
        self.assertTrue(self.find(rows, "heading_levels", "fail"))

    def test_inside_and_outside_margins_need_mirrored_margins(self):
        record = fx.rules_record()
        record["rules"][1]["value"] = {"top": "2.5 cm", "bottom": "2.5 cm", "inside": "3 cm", "outside": "2.5 cm"}
        fx.write_rules(self.out, record)
        body = fx.para("正文。", "a", ppr=fx.sect()) + fx.sect()
        self.cli("docx", str(fx.make_docx(self.dir / "plain.docx", body)))
        self.assertIn("does not mirror", self.find(self.table("docx-check.md"), "margins", "manual")[0][3])
        self.cli("docx", str(fx.make_docx(self.dir / "mirror.docx", body, settings="<w:mirrorMargins/>")))
        self.assertTrue(self.find(self.table("docx-check.md"), "margins", "pass"))

    def test_a_file_that_is_not_a_docx_is_refused(self):
        bad = self.dir / "bad.docx"
        bad.write_text("not a zip", encoding="utf-8")
        code, _, err = self.cli("docx", str(bad))
        self.assertEqual(code, 2)
        self.assertIn("cannot be read as a .docx", err)


class CompareTests(Base):
    def test_styles_in_use_and_sections_that_differ_from_the_template_are_manual(self):
        template = fx.make_docx(self.dir / "template.docx", fx.para("模板正文。", "a") + fx.sect())
        styles = fx.STYLES.replace('<w:sz w:val="24"/></w:rPr></w:style>\n<w:style w:type="paragraph" w:styleId="BodyText">',
                                   '<w:sz w:val="22"/></w:rPr></w:style>\n<w:style w:type="paragraph" w:styleId="BodyText">')
        styles = styles.replace("</w:styles>", '<w:style w:type="paragraph" w:styleId="Normal1"><w:name w:val="Normal1"/></w:style>'
                                               "</w:styles>")
        thesis = fx.make_docx(self.dir / "thesis.docx", fx.para("论文正文。", "a") + fx.para("粘贴来的段落。", "Normal1")
                              + fx.sect(left=1418), styles=styles)
        code, _, _ = self.cli("compare", str(template), str(thesis))
        rows = self.table("compare.md")
        self.assertEqual(code, 0)
        self.assertIn("size 12 pt → 11 pt", self.find(rows, "style", "manual")[0][3])
        self.assertEqual(self.find(rows, "style_added", "manual")[0][1], "Normal1 (1 ¶)")
        self.assertIn("not a page setup of the template", self.find(rows, "section", "manual")[0][3])


def make_pdf(path: Path, pages: list) -> Path:
    """Each page: (lines, label); a line is (x, y, text, size). A running head and the label are added."""
    doc = PYMUPDF.open()
    for lines, label in pages:
        page = doc.new_page(width=595.28, height=841.89)
        page.insert_text((230, 45), "示例大学博士学位论文", fontname="china-s", fontsize=9)
        for x, y, text, size in lines:
            page.insert_text((x, y), text, fontname="china-s", fontsize=size)
        page.insert_text((294, 812), label, fontname="tiro", fontsize=9)
    doc.save(str(path))
    return path


def body(first: float, count: int, size: float, x: float = 85.04, tag: str = "") -> list:
    return [(x, first + i * size * 1.5, f"这是第{i + 1}行正文{tag}，用于检查版心、字号与页码的位置。", size) for i in range(count)]


@unittest.skipUnless(PYMUPDF, "PyMuPDF is not installed")
class PdfTests(Base):
    def setUp(self):
        super().setUp()
        fx.write_rules(self.out)
        toc = [(85.04, 120 + i * 24, f"第{i + 1}章 标题……{i * 10 + 1}", 12) for i in range(3)]
        self.pdf = make_pdf(self.dir / "thesis.pdf", [
            ([(85.04, 100, "摘要", 16)] + body(130, 8, 12), "1"),                                # front matter numbered in arabic
            ([(85.04, 100, "目录", 16)] + toc, "2"),
            ([(85.04, 100, "第1章 绪论", 16)] + body(130, 14, 12, tag="A"), "1"),
            (body(100, 14, 12, tag="B") + [(60, 400, "这一行伸进了装订侧的页边距。", 12)], "2"),  # into the 30 mm margin
            ([(85.04, 100, "第2章 研究方法", 16)] + body(130, 9, 11, tag="C"), "1"),            # restarts; 11 pt chapter
            (body(100, 9, 11, tag="D"), "2"),
        ])

    def test_the_planted_problems_show_in_the_exported_pdf(self):
        code, result, _ = self.cli("pdf", str(self.pdf))
        self.assertEqual(code, 1)
        self.assertEqual(result["main_starts"], 3)
        rows = self.table("pdf-check.md")
        self.assertTrue(self.find(rows, "page_size", "pass"))
        self.assertEqual(self.find(rows, "margins.left", "fail")[0][1], "p. 4")
        self.assertTrue(self.find(rows, "body_size", "pass"))
        self.assertEqual(self.find(rows, "body_size", "manual")[0][1], "pp. 5–6")
        self.assertIn("arabic", self.find(rows, "page_numbers.front", "fail")[0][3])
        self.assertIn("pp. 5–6 show 1–2 where the sequence from p. 3 gives 3–4", self.find(rows, "page_numbers.main", "fail")[0][3])
        self.assertTrue(self.find(rows, "page_numbers.position", "pass"))
        self.assertTrue(self.find(rows, "fonts_embedded", "fail"))
        # a font of another name is a question for the user, not a failure
        self.assertEqual(self.find(rows, "body_font.east_asian")[0][2], "manual")

    def test_a_margin_wider_than_the_rule_is_manual(self):
        record = fx.rules_record()
        record["rules"][1]["value"] = {"left": "2 cm", "right": "2.5 cm"}
        fx.write_rules(self.out, record)
        self.cli("pdf", str(self.pdf))
        left = self.find(self.table("pdf-check.md"), "margins.left")[0]
        self.assertEqual(left[2], "manual")
        self.assertIn("lower bound", left[3])


class MissingPyMuPDFTests(Base):
    def test_every_pdf_row_is_not_checked_and_names_the_package(self):
        fx.write_rules(self.out)
        pdf = self.dir / "thesis.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        with mock.patch.dict(sys.modules, {"pymupdf": None, "fitz": None}):
            code, result, _ = self.cli("pdf", str(pdf))
        rows = self.table("pdf-check.md")
        self.assertEqual(code, 0)
        self.assertEqual({row[2] for row in rows}, {"not_checked"})
        self.assertEqual({row[0] for row in rows}, {"page_size", "margins", "body_size", "body_font", "page_numbers", "fonts_embedded"})
        self.assertIn("PyMuPDF is not installed", rows[0][3])
        self.assertFalse(result["pymupdf"])


if __name__ == "__main__":
    unittest.main()
