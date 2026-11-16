"""tr_units.py: what is masked, how a text is split, and when a translated unit is put back."""
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

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("tr_units", SCRIPTS / "tr_units.py")
tu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tu)

W = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
     'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')


def masked(text: str, tex: bool = False) -> tuple[str, list]:
    out, tokens, _ = tu.mask(text, tex)
    return out, list(tokens.values())


class MaskTests(unittest.TestCase):
    def test_formulas_citations_links_and_code_become_tokens(self):
        out, tokens = masked("共纳入37名患者[@liu2022calorie]，见\\cite{buysse1989pittsburgh}，$\\alpha = 0.05$，"
                             "详见 https://example.org/a。doi:10.1000/xyz123，代码`x = 1`，文献[3]与[1–3]。")
        self.assertEqual(out, "共纳入37名患者⟦T0001⟧，见⟦T0002⟧，⟦T0003⟧，详见 ⟦T0004⟧。⟦T0005⟧，代码⟦T0006⟧，文献⟦T0007⟧与⟦T0008⟧。")
        self.assertEqual(tokens, ["[@liu2022calorie]", "\\cite{buysse1989pittsburgh}", "$\\alpha = 0.05$",
                                  "https://example.org/a", "doi:10.1000/xyz123", "`x = 1`", "[3]", "[1–3]"])
        out, tokens = masked("We enrolled 37 patients \\citep[p.~3]{liu2022} (see \\(x^2\\) and https://x.org/a).")
        self.assertEqual(tokens, ["\\citep[p.~3]{liu2022}", "\\(x^2\\)", "https://x.org/a"])     # ")." is not part of the URL
        self.assertIn("37 patients", out)

    def test_a_citation_key_glued_to_han_is_found_and_an_email_is_not_a_citation(self):
        self.assertEqual(masked("见@liu2022calorie的研究")[1], ["@liu2022calorie"])
        self.assertEqual(masked("Write to a@b.org or see @smith2020.")[1], ["@smith2020"])

    def test_prose_arguments_and_placeholders_become_pairs(self):
        out, tokens = masked("我们用\\textbf{匹兹堡睡眠质量指数}评估\\footnote{见附录。}。")
        self.assertEqual(out, "我们用⟦T0001⟧匹兹堡睡眠质量指数⟦/T0001⟧评估⟦T0002⟧见附录。⟦/T0002⟧。")
        self.assertEqual(tokens, [["\\textbf{", "}"], ["\\footnote{", "}"]])
        out, tokens = masked("[Author input needed: 伦理批准号] and [Citation needed: a trial of TRE [@x]]")
        self.assertEqual(out, "⟦T0001⟧伦理批准号⟦/T0001⟧ and ⟦T0002⟧a trial of TRE ⟦T0003⟧⟦/T0002⟧")
        self.assertEqual(tokens[0], ["[Author input needed: ", "]"])
        out, tokens = masked("See \\href{https://x.org}{the protocol}.", tex=True)
        self.assertEqual((out, tokens), ("See ⟦T0001⟧the protocol⟦/T0001⟧.", [["\\href{https://x.org}{", "}"]]))

    def test_latex_comments_groups_and_escaped_characters(self):
        out, tokens = masked("37\\%的患者\\,{\\bf 粗体} % 作者注\n下一行", tex=True)
        self.assertEqual(out, "37%的患者\u2009⟦T0001⟧⟦T0002⟧ 粗体⟦/T0001⟧ ⟦T0003⟧下一行")
        self.assertEqual(tokens, [["{", "}"], "\\bf", "% 作者注\n"])          # the comment takes its line end
        self.assertEqual(masked("a \\LaTeX [3] b", tex=True)[1], ["\\LaTeX", "[3]"])  # no argument swallowed
        self.assertEqual(masked("\\footnote{第一段", tex=True), ("⟦T0001⟧⟦T0002⟧第一段", ["\\footnote", "{"]))  # closes later

    def test_dollars_follow_the_markdown_rule(self):
        self.assertEqual(masked("It costs $5 and $6.")[1], [])
        self.assertEqual(masked("显著性水平为$\\alpha$。")[1], ["$\\alpha$"])
        self.assertEqual(masked("$p(\\text{time $t$})$ holds")[1], ["$p(\\text{time $t$})$"])   # nested formula
        self.assertEqual(masked("a $ b $ c", tex=True)[1], ["$ b $"])                           # LaTeX: every $ counts


class SplitTests(unittest.TestCase):
    def blocks(self, text: str, tex: bool = False) -> list:
        return [(u["type"], text[u["start"]:u["end"]]) for u in tu.units_of(text, tex)]

    def test_markdown(self):
        text = ("# 方法\n\n第一段，\n续行。\n\n- 年龄 18-65 岁；\n- 无睡眠障碍。\n\n| 指标 | 组 |\n|---|---|\n| 年龄 | 45.2 |\n"
                "| 1 | 2 |\n\n```python\nx = 1  # 代码\n```\n\n$$\ny = x\n$$\n\n> 引用一句。\n")
        self.assertEqual(self.blocks(text), [
            ("heading", "方法"), ("paragraph", "第一段，\n续行。"), ("item", "年龄 18-65 岁；"), ("item", "无睡眠障碍。"),
            ("row", "指标 | 组"), ("row", "年龄 | 45.2"), ("kept", "1 | 2"), ("kept", "```python\nx = 1  # 代码\n```"),
            ("kept", "$$\ny = x\n$$"), ("item", "引用一句。")])

    def test_latex(self):
        text = ("\\documentclass{article}\n\\title{限时进食}\n\\begin{document}\n\\maketitle\n\\section{引言}\\label{s}\n"
                "第一段\\cite{a}。\n% 注释行\n续行。\n\n\\begin{itemize}\n  \\item 年龄；\n\\end{itemize}\n"
                "\\begin{figure}[t]\n\\centering\n\\caption{流程图}\n\\end{figure}\n"
                "\\begin{table}\n\\begin{tabular}{lc}\n年龄 & 45.2 \\\\\n\\end{tabular}\n\\end{table}\n"
                "\\begin{equation}\ny = x\n\\end{equation}\n其中$y$为总分。\n\\end{document}\n")
        blocks = self.blocks(text, tex=True)
        self.assertEqual([b for b in blocks if b[0] != "kept"], [
            ("heading", "限时进食"), ("heading", "引言"), ("paragraph", "\\label{s}\n第一段\\cite{a}。\n% 注释行\n续行。"),
            ("item", "年龄；"), ("caption", "流程图"), ("paragraph", "其中$y$为总分。")])
        kept = [b[1] for b in blocks if b[0] == "kept"]
        self.assertTrue(any("\\centering" in k for k in kept) and any("年龄 & 45.2" in k for k in kept))
        self.assertIn("\\begin{equation}\ny = x\n\\end{equation}", kept)
        self.assertNotIn("documentclass", " ".join(b[1] for b in blocks))       # the preamble is not a block


class UnmaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "translation"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = tu.main([*argv])
        return code, json.loads(out.getvalue()) if out.getvalue() else None

    def split(self, name: str, text: str):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        code, summary = self.run_cli("split", str(path), "--out", str(self.out))
        self.assertEqual(code, 0)
        return path, {u["id"]: u for u in json.loads((self.out / "units.json").read_text(encoding="utf-8"))["units"]}

    def unmask(self, translations: dict, *extra):
        (self.out / "units.translated.json").write_text(json.dumps(translations, ensure_ascii=False), encoding="utf-8")
        return self.run_cli("unmask", "--out", str(self.out), *extra)

    def test_a_translation_is_put_back_with_its_tokens_in_any_order(self):
        path, units = self.split("m.md", "# 方法\n\n共纳入37名患者[@a]，显著性水平为$\\alpha$（见\\cite{b}）。\n")
        self.assertEqual(units["u0002"]["masked"], "共纳入37名患者⟦T0001⟧，显著性水平为⟦T0002⟧（见⟦T0003⟧）。")
        code, summary = self.unmask({"u0001": "Methods", "u0002": "Significance was set at ⟦T0002⟧ (see ⟦T0003⟧); "
                                                                   "37 patients were enrolled ⟦T0001⟧."})
        self.assertEqual((code, summary["restored"], summary["kept_source"]), (0, 2, []))
        self.assertEqual((self.out / "m.translated.md").read_text(encoding="utf-8"),
                         "# Methods\n\nSignificance was set at $\\alpha$ (see \\cite{b}); 37 patients were enrolled [@a].\n")

    def test_latex_text_is_escaped_and_a_command_before_a_letter_gets_a_space(self):
        self.split("p.tex", "\\noindent 我们用\\LaTeX 排版，费用为\\$5。\n")
        code, _ = self.unmask({"u0001": "⟦T0001⟧我们用⟦T0002⟧排版 costs $5 & 50% of a_b."})
        self.assertEqual(code, 0)
        self.assertEqual((self.out / "p.translated.tex").read_text(encoding="utf-8"),
                         "\\noindent 我们用\\LaTeX 排版 costs \\$5 \\& 50\\% of a\\_b.\n")

    def test_a_unit_with_broken_tokens_keeps_its_source_text(self):
        self.split("b.md", "第一段[@a]和$x$。\n\n第二段\\textbf{粗体}。\n\n第三段。\n\n第四段[1]。\n")
        cases = {"u0001": "First ⟦T0001⟧.",                                   # ⟦T0002⟧ missing
                 "u0002": "Second ⟦/T0003⟧bold⟦T0003⟧.",                       # pair out of order
                 "u0003": "Third \\emph{x}.",                                  # a backslash outside the tokens
                 "u0004": "Fourth ⟦T0004⟧ ⟦T0004⟧ ⟦T0009⟧ ⟦T0004."}            # duplicated, foreign, broken
        code, summary = self.unmask(cases)
        self.assertEqual(code, 1)
        problems = {u["id"]: " ".join(u["problems"]) for u in summary["kept_source"]}
        self.assertIn("⟦T0002⟧ missing", problems["u0001"])
        self.assertIn("comes before its ⟦T0003⟧", problems["u0002"])
        self.assertIn("backslash outside the tokens", problems["u0003"])
        for words in ("⟦T0004⟧ duplicated", "⟦T0009⟧ is not a token", "broken token"):
            self.assertIn(words, problems["u0004"])
        self.assertEqual((self.out / "b.translated.md").read_text(encoding="utf-8"),
                         "第一段[@a]和$x$。\n\n第二段\\textbf{粗体}。\n\n第三段。\n\n第四段[1]。\n")

    def test_tables_with_words_are_reported_and_untouched_units_are_listed(self):
        path = self.dir / "t.tex"
        path.write_text("第一段。\n\n\\begin{table}\n\\caption{基线}\n\\begin{tabular}{lc}\n年龄 & 45.2 \\\\\n\\end{tabular}\n"
                        "\\end{table}\n", encoding="utf-8")
        code, summary = self.run_cli("split", str(path), "--out", str(self.out))
        self.assertEqual((code, [k["line"] for k in summary["kept_with_text"]]), (0, [4]))
        self.assertIn("年龄 & 45.2", summary["kept_with_text"][0]["text"])
        code, summary = self.unmask({"u0001": "第一段。", "u0002": "Baseline"})
        self.assertEqual((code, summary["unchanged"]), (0, ["u0001"]))      # likely left untranslated

    def test_missing_units_and_the_third_failed_attempt(self):
        self.split("c.md", "第一段$x$。\n\n第二段。\n")
        for attempt in (1, 2, 3):
            code, summary = self.unmask({"u0001": "First.", "x9": "?"})
            self.assertEqual((code, summary["missing"], summary["kept_source"][0]["attempts"]), (1, ["u0002"], attempt))
        self.assertEqual((summary["tell_user"], summary["unknown_ids"]), (["u0001"], ["x9"]))

    def test_nothing_is_overwritten(self):
        path, _ = self.split("d.md", "一段。\n")
        self.assertEqual(self.unmask({"u0001": "A paragraph."})[0], 0)
        target = self.out / "d.translated.md"
        target.write_text("edited by hand\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            self.unmask({"u0001": "A paragraph."})
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "edited by hand\n")
        with self.assertRaises(SystemExit):
            self.unmask({"u0001": "A paragraph."}, "--output", str(path))
        path.write_text("改过的原文。\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.unmask({"u0001": "A paragraph."}, "--output", str(self.dir / "new.md"))

    def test_a_docx_is_read_as_text_and_comes_back_as_markdown(self):
        body = (f'<w:document {W}><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>方法</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>共纳入3</w:t></w:r><w:r><w:t>7名患者</w:t></w:r><w:del><w:r><w:delText>删去</w:delText></w:r></w:del>'
                '<w:r><w:t>，按</w:t></w:r><m:oMath><m:r><m:t>x=1</m:t></m:r></m:oMath><w:r><w:t>计算。</w:t></w:r></w:p>'
                '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>指标</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>均值</w:t></w:r></w:p></w:tc></w:tr>'
                '<w:tr><w:tc><w:p><w:r><w:t>年龄</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>45.2</w:t></w:r></w:p></w:tc></w:tr>'
                '</w:tbl></w:body></w:document>')
        path = self.dir / "m.docx"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("word/document.xml", body)
        self.assertEqual(tu.docx_text(path), "# 方法\n\n共纳入37名患者，按[Author input needed: equation 1 of the .docx "
                                             "goes here]计算。\n\n| 指标 | 均值 |\n|---|---|\n| 年龄 | 45.2 |")
        code, summary = self.run_cli("split", str(path), "--out", str(self.out))
        self.assertEqual((code, summary["by_type"]), (0, {"heading": 1, "paragraph": 1, "row": 2}))
        code, _ = self.unmask({"u0001": "Methods", "u0002": "We enrolled 37 patients, computed as ⟦T0001⟧equation 1 of "
                                                            "the .docx goes here⟦/T0001⟧.",
                               "u0003": "Measure ⟦T0002⟧ Mean", "u0004": "Age ⟦T0003⟧ 45.2"})
        self.assertEqual((self.out / "m.translated.md").read_text(encoding="utf-8"),
                         "# Methods\n\nWe enrolled 37 patients, computed as [Author input needed: equation 1 of the .docx "
                         "goes here].\n\n| Measure | Mean |\n|---|---|\n| Age | 45.2 |")
        (self.dir / "bad.docx").write_text("not a zip", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            tu.main(["split", str(self.dir / "bad.docx"), "--out", str(self.out)])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
