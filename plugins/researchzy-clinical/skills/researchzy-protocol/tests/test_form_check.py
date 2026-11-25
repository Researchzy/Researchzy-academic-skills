"""form_check.py: a filled copy of a Word form changed only its declared places (the form problems of task PR-1).

The forms are built from XML strings by form_fixture.py. The recipe test runs the python-docx code of
references/forms-and-amendments.md and skips without python-docx; the page count skips without LibreOffice.
"""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
SCRIPT = HERE.parent / "scripts" / "form_check.py"
spec = importlib.util.spec_from_file_location("form_check", SCRIPT)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)
sys.path.insert(0, str(HERE))
import form_fixture as fx  # noqa: E402

HAVE_DOCX = importlib.util.find_spec("docx") is not None
SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.form = fx.write_docx(self.dir / "form.docx", fx.document())
        self.fields = copy.deepcopy(fx.FIELDS)

    def tearDown(self):
        self.tmp.cleanup()

    def compare(self, filled_xml: str | None = None, filled: Path | None = None, pages: bool = False, **parts):
        """(exit code, JSON summary, {(check, subject): (state, detail)}) of compare form.docx and a filled copy."""
        path = filled or fx.write_docx(self.dir / "filled.docx", filled_xml or fx.document(fx.filled_values()), **parts)
        (self.dir / "form-fill.json").write_text(json.dumps({"fields": self.fields}, ensure_ascii=False), encoding="utf-8")
        out, self.err = io.StringIO(), io.StringIO()
        which = nullcontext() if pages else mock.patch.object(fc.shutil, "which", return_value=None)
        with which, redirect_stdout(out), redirect_stderr(self.err):
            code = fc.main(["compare", str(self.form), str(path), "--dir", str(self.dir)])
        rows = {}
        for line in (self.dir / "form-check.md").read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if line.startswith("| ") and len(cells) == 4 and cells[2] in fc.STATES:
                rows[(cells[0], cells[1])] = (cells[2], cells[3])
        return code, json.loads(out.getvalue()), rows

    def bad_input(self, *args) -> str:
        with self.assertRaises(SystemExit) as caught:
            self.compare(*args)
        self.assertEqual(caught.exception.code, 2)
        return self.err.getvalue()


class CarefulFill(Base):
    def test_a_careful_fill_passes_every_row(self):
        code, out, rows = self.compare()
        self.assertEqual((code, out["ok"], out["failed"], out["manual"]), (0, True, [], []))
        self.assertEqual(out["not_checked"], ["pages: both files"])
        self.assertEqual(rows[("label", "2. 联系电话(手机)")], ("pass", "Found once in the form."))   # trailing space, full-width brackets
        self.assertEqual(rows[("value", "2. 联系电话(手机)")], ("pass", "Reads “012345”."))           # not 12345
        self.assertEqual(rows[("value", "5. 是否涉及基因检测")], ("pass", "Reads “No”."))              # not False
        self.assertEqual(rows[("place", "4. 职称")], ("pass", "table 1, row 4, cell 3."))              # beside the merged label
        self.assertEqual(rows[("place", "6. 研究摘要")], ("pass", "table 1, row 7, cell 1."))           # below a spanning label
        self.assertEqual(rows[("place", "8. 风险与受益")], ("pass", "1 paragraph(s) after the label."))
        self.assertIn("Times New Roman, 宋体, 12.0 pt", rows[("fonts", "7. 研究背景")][1])
        for check in ("styles", "numbering"):
            self.assertEqual(rows[(check, f"word/{check}.xml")], ("pass", "Same as the form."))
        self.assertEqual(rows[("headers_footers", "2 part(s)")][0], "pass")
        self.assertEqual(rows[("outside", "body")], ("pass", "All 7 blocks outside the declared places are as in the form."))
        self.assertIn("LibreOffice (soffice) is not installed", rows[("pages", "both files")][1])

    def test_the_dry_run_finds_every_label_and_place_before_filling(self):
        code, out, rows = self.compare(filled=self.form)
        self.assertEqual(code, 1)
        self.assertEqual(out["failed"], [f"value: {n}. {f['label']}" for n, f in enumerate(self.fields, 1)])
        self.assertTrue(all(rows[("place", f"{n}. {f['label']}")][0] == "pass" for n, f in enumerate(self.fields, 1)))

    def test_session_ids_and_proofing_marks_are_not_changes(self):
        noisy = fx.document(fx.filled_values()).replace("<w:p>", '<w:p w:rsidR="00A1B2C3" w:rsidRDefault="00A1B2C3">')
        noisy = noisy.replace("<w:r><w:tab/></w:r>", '<w:proofErr w:type="spellStart"/><w:r><w:tab/></w:r>')
        self.assertEqual(self.compare(noisy)[0], 0)


class PlantedProblems(Base):
    def test_values_are_kept_as_typed(self):
        values = {**fx.filled_values(), 2: "12345", 5: "False"}
        code, _, rows = self.compare(fx.document(values))
        self.assertEqual(code, 1)
        self.assertIn("Reads “12345”; form-fill.json: “012345”. The value was converted on the way", rows[("value", "2. 联系电话(手机)")][1])
        self.assertIn("Reads “False”; form-fill.json: “No”. The value was converted", rows[("value", "5. 是否涉及基因检测")][1])

    def test_a_line_break_typed_into_the_text_fails(self):
        code, out, rows = self.compare(fx.document(fx.filled_values(), raw=True))
        self.assertEqual(code, 1)
        self.assertEqual([r for r in out["failed"] if r.startswith("raw_newline")], ["raw_newline: 6. 研究摘要", "raw_newline: 7. 研究背景"])
        self.assertIn("1 text element(s) hold a typed line break", rows[("raw_newline", "6. 研究摘要")][1])
        self.assertEqual(rows[("value", "6. 研究摘要")][0], "pass")       # the text reads right; Word would show a space

    def test_a_korean_default_font_written_into_a_chinese_form_fails(self):
        code, _, rows = self.compare(fx.document(fx.filled_values(), rpr=fx.KOREAN))
        self.assertEqual(code, 1)
        state, detail = rows[("fonts", "7. 研究背景")]
        self.assertEqual(state, "fail")
        self.assertIn("East Asian font 맑은 고딕, the form has 宋体", detail)
        self.assertIn("Latin font 맑은 고딕, the form has Times New Roman", rows[("fonts", "6. 研究摘要")][1])
        self.assertEqual(rows[("outside", "body")][0], "pass")

    def test_a_run_added_without_the_places_formatting_takes_the_style_and_fails(self):
        _, _, rows = self.compare(fx.document(fx.filled_values(), rpr=""))
        detail = rows[("fonts", "1. 项目名称")][1]
        self.assertIn("East Asian font 等线, the form has 宋体", detail)          # the theme's minor East Asian font
        self.assertIn("size 10.5, the form has 12.0", detail)
        self.assertIn("Latin font Calibri, the form has Times New Roman", rows[("fonts", "2. 联系电话(手机)")][1])

    def test_the_merged_label_cell_must_survive(self):
        code, _, rows = self.compare(fx.document(fx.filled_values()).replace(">研究者<", ">王某<", 1))
        self.assertEqual((code, rows[("outside", "body")][0]), (1, "fail"))
        self.assertIn("“研究者” → “王某”", rows[("outside", "body")][1])

    def test_the_signature_line_after_the_last_section_stays(self):
        signature = fx.para(fx.run("申请人签字：") + "<w:r><w:tab/></w:r>" + fx.run("日期："))
        filled = fx.document(fx.filled_values()).replace(signature, "")
        self.assertNotIn("申请人签字", filled)
        code, _, rows = self.compare(filled)
        self.assertEqual(code, 1)
        self.assertIn("is not after the label: what followed the place is gone", rows[("value", "8. 风险与受益")][1])
        self.assertIn("Missing from the filled form: “申请人签字： 日期：”", rows[("outside", "body")][1])

    def test_styles_numbering_sections_header_and_footer_stay(self):
        styles = fx.STYLES.replace('<w:name w:val="Normal"/>', '<w:name w:val="Normal"/><w:rPr><w:rFonts w:eastAsia="SimHei"/></w:rPr>')
        numbering = fx.NUMBERING.replace("%1、", "%1.")
        code, out, rows = self.compare(**{"word/styles.xml": styles, "word/numbering.xml": numbering,
                                          "word/media/image1.png": fx.png() + b"another logo"})
        self.assertEqual(code, 1)
        self.assertIn("Changed: style Normal.", rows[("styles", "word/styles.xml")][1])
        self.assertIn("Changed: abstractNum 0.", rows[("numbering", "word/numbering.xml")][1])
        self.assertIn("section 1 headerReference (default)", rows[("headers_footers", "2 part(s)")][1])
        self.assertNotIn("footerReference", rows[("headers_footers", "2 part(s)")][1])
        no_header = fx.document(fx.filled_values()).replace('<w:headerReference w:type="default" r:id="rId4"/>', "")
        code, _, rows = self.compare(no_header)
        self.assertEqual((code, rows[("sections", "1 section(s)")][0]), (1, "fail"))

    def test_a_paragraph_added_outside_the_places_fails(self):
        filled = fx.document(fx.filled_values()).replace("<w:tbl>", fx.para(fx.run("由AI生成的说明")) + "<w:tbl>", 1)
        code, _, rows = self.compare(filled)
        self.assertEqual(code, 1)
        self.assertIn("Added outside the declared places: “由AI生成的说明”", rows[("outside", "body")][1])


class Labels(Base):
    def test_a_label_not_in_the_form_is_reported_with_the_closest(self):
        self.fields[1]["label"] = "联系电话(手机号)"
        code, out, rows = self.compare()
        self.assertEqual(code, 1)
        self.assertIn("Not in the form; the closest: “联系电话（手机）”", rows[("label", "2. 联系电话(手机号)")][1])
        self.assertIn("“” → “012345”", rows[("outside", "body")][1])          # an undeclared place is a change outside

    def test_a_label_that_appears_twice_needs_occurrence(self):
        self.form = fx.write_docx(self.dir / "form.docx", fx.document().replace(">职称<", ">姓名<"))
        filled = fx.document(fx.filled_values()).replace(">职称<", ">姓名<")
        del self.fields[3]
        code, _, rows = self.compare(filled)
        self.assertEqual((code, rows[("label", "3. 姓名")][1]), (1, "The label appears 2 time(s): set occurrence to one of 1 to 2."))
        self.fields[2]["occurrence"] = 1
        code, _, rows = self.compare(filled)
        self.assertEqual(rows[("label", "3. 姓名")], ("pass", "Occurrence 1."))
        self.assertEqual(rows[("value", "3. 姓名")][0], "pass")

    def test_a_place_on_another_label_or_on_the_hidden_part_of_a_merge_fails(self):
        self.fields.append({"label": "研究者", "place": "right", "value": "王某"})
        self.fields.append({"label": "研究者", "place": "below", "value": "王某"})
        _, _, rows = self.compare()
        self.assertEqual(rows[("place", "9. 研究者")], ("fail", "table 1, row 3, cell 2 holds “姓名”, the label of another field: "
                                                               "check place and label."))
        self.assertIn("hidden part of a vertical merge", rows[("place", "10. 研究者")][1])

    def test_text_the_form_had_in_the_place_is_for_a_person_to_confirm(self):
        self.form = fx.write_docx(self.dir / "form.docx", fx.document({1: "（请填写）"}))
        code, out, rows = self.compare()
        self.assertEqual((code, out["manual"]), (0, ["place: 1. 项目名称"]))
        self.assertIn("holds “（请填写）” in the form, which the value replaces", rows[("place", "1. 项目名称")][1])


class Inputs(Base):
    def test_values_must_be_strings_and_the_fields_complete(self):
        self.fields[1]["value"] = 12345
        self.fields[4]["value"] = False
        self.fields[0]["place"] = "left"
        del self.fields[7]["until"]
        self.fields[2]["occurrence"] = 0
        message = self.bad_input()
        for part in ('fields[2].value must be a string written as the form shows it: "012345", not 12345',
                     "fields[5].value must be a string", "fields[1].place must be one of right, below, after",
                     "fields[8].until must name the paragraph", "fields[3].occurrence must be a whole number"):
            self.assertIn(part, message)

    def test_files_that_cannot_be_read_stop_with_a_message(self):
        broken = self.dir / "broken.docx"
        broken.write_bytes(b"not a zip")
        self.assertIn("cannot be read as a .docx", self.bad_input(None, broken))
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()) as err:
            fc.main(["compare", str(self.form), str(self.form), "--fill", str(self.dir / "none.json")])
        self.assertIn("no fill map", err.getvalue())

    @unittest.skipUnless(SOFFICE, "LibreOffice is not installed")
    def test_the_pages_are_counted_with_libreoffice(self):
        _, _, rows = self.compare(pages=True)
        self.assertEqual(rows[("pages", "both files")][0], "manual")
        self.assertIn("The form renders as 1 page(s), the filled copy as 1", rows[("pages", "both files")][1])


@unittest.skipUnless(HAVE_DOCX, "python-docx is not installed")
class Recipe(Base):
    def test_the_python_docx_recipe_of_the_reference_fills_the_form_cleanly(self):
        reference = (HERE.parent / "references" / "forms-and-amendments.md").read_text(encoding="utf-8")
        code = re.search(r"## The recipe.*?```python\n(.*?)```", reference, re.S).group(1)
        script, filled = self.dir / "fill_form.py", self.dir / "form-filled.docx"
        script.write_text(code, encoding="utf-8")
        shutil.copyfile(self.form, filled)
        (self.dir / "form-fill.json").write_text(json.dumps({"fields": self.fields}, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run([sys.executable, "-I", str(script), str(filled), str(self.dir / "form-fill.json")],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        code, out, _ = self.compare(filled=filled)
        self.assertEqual((code, out["failed"], out["manual"]), (0, [], []))


if __name__ == "__main__":
    unittest.main()
