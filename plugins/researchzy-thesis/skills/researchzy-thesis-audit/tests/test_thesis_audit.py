"""thesis_audit.py: a whole thesis checked against what audit.json declares, in LaTeX and in .docx.

The fixture is the real task TA-1 of the design: a Chinese social-science thesis with Chinese and
English abstracts, given as LaTeX (main.tex with \\include, .bib, .aux) and as .docx, with a blind
copy. Every planted problem must be caught; subgroup sizes that add up to the total and a cited
study's own sample size must not fail."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from xml.sax.saxutils import escape

SCRIPTS = Path(__file__).parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ta = load("thesis_audit")
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# ---------------------------------------------------------------------------------------------
# TA-1 as LaTeX

TEX = {
    "main.tex": "\\documentclass{ctexbook}\n\\usepackage{natbib}\n\\begin{document}\n\\include{abstract}\n"
                "\\include{ch1}\n\\include{chapters/ch2}\n\\include{ch3}\n\\include{conclusion}\n\\nocite{zhao2019}\n"
                "\\bibliography{refs}\n\\end{document}\n",
    "abstract.tex": "\\chapter*{摘要}\n本文基于技术接受模型（TAM），以312份有效问卷为样本，检验感知有用性对使用意愿的影响。"
                    "结果显示，感知有用性的标准化路径系数$\\beta = 0.24$（$p < 0.001$）。\n\\chapter*{Abstract}\n"
                    "Drawing on the technology acceptance model (TAM), this study analyses 312 valid responses. "
                    "Perceived usefulness predicts intention ($\\beta = 0.42$, $p < 0.001$).\n",
    "ch1.tex": "\\chapter{绪论}\n移动支付的普及引起了学界关注\\citep{davis1989,wang2020}。 % 待补充\n",
    "chapters/ch2.tex": "\\chapter{文献综述与研究假设}\n\\section{理论基础}\n本文采用技术接受模型（TAM）作为理论框架"
                        "\\citep{davis1989}。感知有用性（PU）是指个体认为使用某一系统能够提高绩效的程度。\n"
                        "已有研究多采用SEM检验此类模型，SEM能够同时估计测量模型和结构模型。也有研究发现相反的结果（Wang，2021）。\n"
                        "据此提出假设。H1：PU正向影响使用意愿。H2：感知易用性正向影响PU。H3：社会影响正向影响使用意愿。\n",
    "ch3.tex": "\\chapter{研究设计与实证结果}\n本研究共发放问卷350份，样本量为321人，其中男性148人，女性164人。"
               "与\\citet{davis1989}报告的样本量（107人）相比，样本更大。\n"
               "如表~\\ref{tab:desc}所示，样本结构合理；表~\\ref{tab:group}按性别分组；图~\\ref{fig:frame}展示了研究框架。\n"
               "感知效用（PU）对使用意愿有显著正向影响，表~\\ref{tab:sem}报告了SEM结果，表4-3给出了稳健性检验。H1和H2得到支持。\n"
               "\\begin{figure}\n\\caption{研究框架}\\label{fig:frame}\n\\end{figure}\n"
               "\\begin{table}\n\\caption{样本描述性统计}\\label{tab:desc}\n\\begin{tabular}{ll}\n变量 & 均值 \\\\\n"
               "使用意愿 & 3.86 \\\\\nN & 312 \\\\\n\\end{tabular}\n\\end{table}\n"
               "\\begin{table}\n\\caption{性别分组}\n\\label{tab:group}\n\\begin{tabular}{ll}\n男（$n = 148$） & 女（$n = 164$） \\\\\n"
               "合计 & $N = 312$ \\\\\n\\end{tabular}\n\\end{table}\n"
               "\\begin{table}\n\\caption{结构模型结果}\\label{tab:sem}\n\\begin{tabular}{lll}\n假设 & $\\beta$ & 结论 \\\\\n"
               "H1 & 0.24 & 支持 \\\\\nH2 & 0.31 & 支持 \\\\\nN & 298 & \\\\\n\\end{tabular}\n\\end{table}\n"
               "\\begin{figure}\n\\caption{路径系数}\\label{fig:path}\n\\end{figure}\n",
    "conclusion.tex": "\\chapter*{结论}\n本文验证了H1和H2，感知有用性显著影响使用意愿。\n",
    "refs.bib": "@article{davis1989, author = {Davis, Fred D.}, title = {Perceived usefulness}, year = {1989}}\n"
                "@article{wang2020, author = {王明}, title = {移动支付使用意愿研究}, year = {2020}}\n"
                "@article{zhao2019, author = {赵强}, title = {数字金融与消费}, year = {2019}}\n"
                "@article{li2018, author = {Li, Hua}, title = {Never cited, never printed}, year = {2018}}\n",
    "main.aux": "\\relax\n\\citation{davis1989}\n\\citation{wang2020}\n\\@input{ch3.aux}\n\\citation{zhao2019}\n",
    "ch3.aux": "\\newlabel{fig:frame}{{3-1}{18}}\n\\newlabel{tab:desc}{{3-2}{19}}\n\\newlabel{tab:group}{{3-3}{20}}\n"
               "\\newlabel{tab:sem}{{3-5}{22}}\n\\newlabel{fig:path}{{3-4}{23}}\n",
}
KEY_NUMBERS = [{"id": "N", "value": "312", "meaning": "有效问卷", "labels": ["有效问卷", "样本量", "valid responses"],
                "appears_in": ["abstract-zh", "abstract-en", "chapter 3 text", "table 3-2"]}]
TABLE_N = [{"table": "3-2", "n": 312}, {"table": "3-5", "n": 312}]

# ---------------------------------------------------------------------------------------------
# TA-1 as .docx, built from XML strings


def run(text):
    return f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(*parts, style=None):
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}{''.join(run(p) if isinstance(p, str) else p[0] for p in parts)}</w:p>"


def seq(text):        # a number made by a SEQ field
    return (f'<w:fldSimple w:instr=" SEQ 表 \\* ARABIC \\s 1 ">{run(text)}</w:fldSimple>',)


def ref(text):        # a cross-reference made by a REF field
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> REF _Ref1 \\h </w:instrText>'
            f'</w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>{run(text)}<w:r><w:fldChar w:fldCharType="end"/></w:r>',)


def inserted(author, text):
    return (f'<w:ins w:id="9" w:author="{author}" w:date="2026-03-01T00:00:00Z">{run(text)}</w:ins>',)


def footnote_ref(number):
    return (f'<w:r><w:footnoteReference w:id="{number}"/></w:r>',)


def table(rows):
    return "<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc>{para(c)}</w:tc>" for c in r) + "</w:tr>" for r in rows) + "</w:tbl>"


STYLES = (f'<w:styles xmlns:w="{W_NS}">'
          '<w:style w:type="paragraph" w:styleId="1"><w:name w:val="论文一级标题"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>'
          '<w:style w:type="paragraph" w:styleId="2"><w:name w:val="标题 2"/></w:style>'
          '<w:style w:type="paragraph" w:styleId="a5"><w:name w:val="题注"/></w:style></w:styles>')


def thesis_docx(blind=False):
    h1 = lambda text: para(text, style="1")                                                  # noqa: E731
    cap = lambda *parts: para(*parts, style="a5")                                            # noqa: E731
    body = [
        h1("摘  要"),
        para("本文基于技术接受模型（TAM），以312份有效问卷为样本，检验感知有用性对使用意愿的影响。结果显示，感知有用性的标准化路径系数β = 0.24（p < 0.001）。"),
        h1("Abstract"),
        para("Drawing on the technology acceptance model (TAM), this study analyses 312 valid responses. "
             "Perceived usefulness predicts intention (β = 0.42, p < 0.001)."),
        h1("缩略语表"), table([["TAM", "技术接受模型", "Technology Acceptance Model"], ["PU", "感知有用性", "Perceived Usefulness"]]),
        h1("第1章 绪论"), para("移动支付的普及引起了学界关注（Davis，1989；王明，2020）。"),
        h1("第2章 文献综述与研究假设"), para("2.1 理论基础", style="2"),
        para("本文采用技术接受模型（TAM）作为理论框架（Davis，1989）。感知有用性（PU）是指个体认为使用某一系统能够提高绩效的程度。"),
        para("已有研究多采用SEM检验此类模型，SEM能够同时估计测量模型和结构模型。也有研究发现相反的结果（Wang，2021）。"),
        para("表2-1汇总了已有研究，其中Davis（1989）的样本量为107人。"),
        cap("表2-1 已有研究汇总"), table([["研究", "样本"], ["Davis（1989）", "N = 107"]]),
        para("据此提出假设。H1：PU正向影响使用意愿。H2：感知易用性正向影响PU。H3：社会影响正向影响使用意愿。"),
        h1("第3章 研究设计与实证结果"),
        para(f"本研究共发放问卷350份，样本量为321人，其中男性{146 if blind else 148}人，女性164人。"
             "与Davis（1989）报告的样本量（107人）相比，样本更大。", footnote_ref(1)),
        para("如", ref("表3-2"), "所示，样本结构合理；表3-3按性别分组；图3-1展示了研究框架。"),
        para("感知效用（PU）对使用意愿有显著正向影响，表3-5报告了SEM结果，表4-3给出了稳健性检验。H1和H2得到支持。"),
        cap("图3-", seq("1"), " 研究框架"), cap("表3-", seq("2"), " 样本描述性统计"),
        table([["变量", "均值"], ["使用意愿", "3.86"], ["N", "312"]]),
        cap("表3-3 性别分组"), table([["男（n = 148）", "女（n = 164）"], ["合计", "N = 312"]]),
        cap("表3-", seq("5"), " 结构模型结果"), table([["假设", "β", "结论"], ["H1", "0.24", "支持"], ["H2", "0.31", "支持"], ["N", "298", ""]]),
        cap("图3-", seq("4"), " 路径系数"),
        h1("结论"), para("本文验证了H1和H2，", inserted("张明远", "感知有用性显著影响使用意愿。") if blind else "感知有用性显著影响使用意愿。"),
        h1("参考文献"),
        para("Davis F D. Perceived usefulness, perceived ease of use, and user acceptance of information technology[J]. "
             "MIS Quarterly, 1989, 13(3): 319-340."),
        para("王明. 移动支付使用意愿研究[J]. 管理世界, 2020, 36(5): 1-10."),
        para("赵强. 数字金融与消费[J]. 经济研究, 2019, 54(2): 20-30."),
        h1("致  谢"), para("感谢导师李国强教授的悉心指导。"),
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{"".join(body)}</w:body></w:document>')
        archive.writestr("word/styles.xml", STYLES)
        archive.writestr("word/footnotes.xml", f'<w:footnotes xmlns:w="{W_NS}"><w:footnote w:type="separator" w:id="0">'
                                              f'{para("")}</w:footnote><w:footnote w:id="1">{para("SEM的估计采用最大似然法。")}'
                                              "</w:footnote></w:footnotes>")
        if blind:
            archive.writestr("word/header1.xml", f'<w:hdr xmlns:w="{W_NS}">{para("清华大学硕士学位论文")}</w:hdr>')
            archive.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
                                                  'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                                                  "<dc:creator>张明远</dc:creator></cp:coreProperties>")
    return buffer.getvalue()


class AuditCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "thesis-audit"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content) if isinstance(content, bytes) else path.write_text(content, encoding="utf-8")
        return path

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ta.main([*map(str, argv), "--out", str(self.out)])
        return code, (json.loads(out.getvalue()) if out.getvalue() else None), err.getvalue()

    def audit(self, files, **extra):
        audit = {"files": files, "abbreviations": {"convention": "once"}, "key_numbers": KEY_NUMBERS, "table_n": TABLE_N,
                 **extra}
        return self.write("thesis-audit/audit.json", json.dumps(audit, ensure_ascii=False))

    def check(self, audit, *extra):
        code, summary, err = self.run_cli("check", "--audit", audit, *extra)
        self.assertNotEqual(code, 2, err)
        report = json.loads((self.out / "report.json").read_text(encoding="utf-8"))
        return code, report

    def rows(self, report, check, status=None):
        return [r for r in report["rows"] if r["check"] == check and (status is None or r["status"] == status)]

    def messages(self, report, check=None):
        return [f["message"] for r in report["rows"] if check in (None, r["check"]) for f in r["findings"]
                if r["status"] == "fail"]

    def leads(self, report, check):
        return [item for g in report["leads"] if g["check"] == check for item in g["items"]]

    def assert_ta1(self, report):
        """The planted problems common to the LaTeX and the .docx form."""
        # 1. 312 in the abstracts and Table 3-2, 321 in chapter 3 (no space before the Han characters)
        key = {r["rule"].split(" in ")[-1]: r for r in self.rows(report, "key_numbers")}
        self.assertEqual({k: r["status"] for k, r in key.items()},
                         {"abstract-zh": "pass", "abstract-en": "pass", "chapter 3 text": "fail", "table 3-2": "pass"})
        self.assertIn("321", key["chapter 3 text"]["detail"])
        self.assertNotIn("107", key["chapter 3 text"]["detail"])            # a cited study's own sample size
        # 2. Table 3-5 gives N = 298: a failure where declared, a lead in the ledger
        table_n = {r["rule"]: r["status"] for r in self.rows(report, "table_n")}
        self.assertEqual(table_n, {"N of table 3-2": "pass", "N of table 3-5": "fail"})
        self.assertTrue(any("298" in x and "3-5" in x for x in self.leads(report, "table_n")))
        ledger = (self.out / "n-ledger.csv").read_text(encoding="utf-8")
        self.assertIn("subgroup,148", ledger)
        self.assertIn("subgroup,164", ledger)
        # 3. SEM never defined (a lead), PU with two long forms (a failure), TAM defined correctly
        self.assertTrue(any("PU" in m and "感知有用性" in m and "感知效用" in m for m in self.messages(report, "abbreviations")))
        self.assertTrue(any(x.startswith("SEM:") for x in self.leads(report, "abbreviations")))
        everything = json.dumps(report["rows"] + report["leads"], ensure_ascii=False)
        self.assertNotIn("TAM:", everything)
        self.assertNotIn("TAM has", everything)
        # 5. Figure 3-4 never called; Table 4-3 called and absent
        floats = self.messages(report, "floats")
        self.assertTrue(any("4-3" in m and "no caption" in m for m in floats))
        self.assertTrue(any("figure 3-4 is never called" in m for m in floats))
        # 6. (Wang, 2021) has no entry; one entry is never cited
        citations = self.messages(report, "citations")
        self.assertTrue(any(m.startswith("Wang 2021") for m in citations))
        self.assertTrue(any(("zhao2019" in m or "赵强" in m) and "never cited" in m for m in citations))
        # 7. H3 is missing from the results and the conclusion
        hyp = {r["rule"]: r["status"] for r in self.rows(report, "hypotheses")}
        self.assertEqual((hyp["H1 in the results"], hyp["H3 in the results"], hyp["H3 in the conclusion"]),
                         ("pass", "fail", "fail"))
        self.assertEqual(hyp["no undeclared hypothesis in the results"], "pass")
        # Must not fail: subgroups adding up to 312, a cited study's sample size
        failing = json.dumps([r["detail"] for r in report["rows"] if r["status"] == "fail"] + self.messages(report),
                             ensure_ascii=False)
        for number in ("148", "164", "107"):
            self.assertNotIn(number, failing)

    def assert_abstracts(self):
        code, summary, _ = self.run_cli("abstracts", self.out / "abstract-zh.txt", self.out / "abstract-en.txt")
        self.assertEqual(code, 1)
        self.assertEqual([r["status"] for r in summary["rows"]], ["fail", "fail"])
        text = (self.out / "abstracts.md").read_text(encoding="utf-8")
        self.assertIn("0.24 is in", text)
        self.assertIn("0.42 is in", text)
        self.assertNotIn("312 is in", text)


class LatexTests(AuditCase):
    def setUp(self):
        super().setUp()
        for name, content in TEX.items():
            self.write(name, content)
        self.files = [{"path": str(self.dir / "main.tex"), "role": "thesis"},
                      {"path": str(self.dir / "conclusion.tex"), "role": "conclusion"}]
        self.hyp = {"labels": ["H1", "H2", "H3"], "results": ["chapter 3"]}

    def test_ta1_latex_with_aux(self):
        audit = self.audit(self.files, hypotheses=self.hyp)
        code, report = self.check(audit, "--bib", self.dir / "refs.bib", "--aux", self.dir / "main.aux")
        self.assertEqual(code, 1)
        self.assert_ta1(report)
        self.assertEqual(report["files"][:3], [str(self.dir / n) for n in ("main.tex", "abstract.tex", "ch1.tex")])
        self.assertEqual(self.rows(report, "abbreviations")[1]["status"], "not_checked")        # no list of abbreviations
        self.assertTrue(any("\\.bib entries are not printed" in r["detail"] or ".bib entries are not printed" in r["detail"]
                            for r in self.rows(report, "citations")))
        self.assert_abstracts()

    def test_without_aux_counted_numbers_are_leads_not_failures(self):
        audit = self.audit(self.files, hypotheses=self.hyp)
        code, report = self.check(audit, "--bib", self.dir / "refs.bib")
        floats = self.messages(report, "floats")
        self.assertFalse(any("4-3" in m for m in floats))
        self.assertTrue(any("4-3" in x for x in self.leads(report, "floats")))
        self.assertTrue(any("figure 3-2" in m and "never called" in m for m in floats))   # \ref-less and no typed callout

    def test_newacronym_list_and_ac_uses(self):
        self.write("glossary.tex", "\\documentclass{ctexbook}\n\\newacronym{tam}{TAM}{技术接受模型}\n"
                                   "\\newacronym{pls}{PLS}{偏最小二乘法}\n\\begin{document}\n\\chapter{绪论}\n"
                                   "本文以\\ac{tam}为框架，\\ac{tam}已被广泛检验。\n\\end{document}\n")
        code, report = self.check(self.audit([{"path": str(self.dir / "glossary.tex")}], key_numbers=[], table_n=[]))
        listed = self.rows(report, "abbreviations")[1]
        self.assertEqual(listed["status"], "fail")
        self.assertEqual([f["message"] for f in listed["findings"]], ["PLS is in the list of abbreviations and never used in the text"])

    def test_missing_include_and_bad_audit_exit_2(self):
        self.write("ch1.tex", "\\chapter{绪论}\n\\input{missing-section}\n")
        code, _, err = self.run_cli("check", "--audit", self.audit(self.files))
        self.assertEqual(code, 2)
        self.assertIn("missing-section", err)
        self.assertEqual(self.run_cli("check", "--audit", self.write("bad.json", "{"))[0], 2)
        self.assertEqual(self.run_cli("check", "--audit", self.audit([{"path": "nope.tex"}]))[0], 2)
        bad_place = [{"id": "N", "value": "312", "appears_in": ["chpater 3"]}]
        self.write("ch1.tex", TEX["ch1.tex"])
        self.assertEqual(self.run_cli("check", "--audit", self.audit(self.files, key_numbers=bad_place))[0], 2)


class DocxTests(AuditCase):
    def setUp(self):
        super().setUp()
        self.full = self.write("thesis.docx", thesis_docx())
        self.files = [{"path": str(self.full), "role": "thesis"}]
        self.hyp = {"labels": ["H1", "H2", "H3"], "results": ["chapter 3"], "conclusion": ["chapter 4"]}

    def test_ta1_docx(self):
        code, report = self.check(self.audit(self.files, hypotheses=self.hyp))
        self.assertEqual(code, 1)
        self.assert_ta1(report)
        self.assertEqual(self.rows(report, "abbreviations")[1]["status"], "pass")              # 缩略语表 against the text
        typed = self.leads(report, "floats")
        self.assertTrue(any("表3-3 性别分组" in x for x in typed))                            # typed caption
        self.assertFalse(any("callout 表3-2" in x for x in typed))                           # made by a REF field
        ledger = (self.out / "n-ledger.csv").read_text(encoding="utf-8")
        self.assertIn("cited study,107", ledger)
        self.assert_abstracts()

    def test_blind_copy_numbers_and_identity(self):
        blind_dir = self.dir / "thesis-audit" / "blind"
        blind = self.write("thesis-audit/blind/thesis-blind.docx", thesis_docx(blind=True))
        code, summary, _ = self.run_cli("blind", "--full", self.full, "--blind", blind)
        self.assertEqual(code, 1)
        numbers = summary["rows"][0]
        self.assertEqual((numbers["rule"], numbers["status"]), ("numbers agree with the full copy", "fail"))
        self.assertIn("148 -> blind copy 146", (self.out / "blind.md").read_text(encoding="utf-8"))
        self.assertEqual(summary["rows"][1]["status"], "pass")                               # headings
        # The identity list of a thesis, written into the authors.json format of check_anonymity.py
        ca = load("check_anonymity")
        identity = {"authors": [{"name": "张明远", "role": "author", "affiliations": ["清华大学", "经济管理学院"]},
                                {"name": "李国强", "role": "supervisor", "affiliations": ["清华大学"]}],
                    "funding": [{"grant_number": "71872001"}],
                    "anonymity": {"other": ["2021210345", "移动支付使用意愿的影响因素研究"]}}
        authors = self.write("thesis-audit/authors.json", json.dumps(identity, ensure_ascii=False))
        out = io.StringIO()
        with redirect_stdout(out):
            code = ca.main([str(blind_dir), "--authors", str(authors), "--out", str(self.out)])
        hits = {(h["kind"], h["where"], h["found"]) for h in json.loads(out.getvalue())["hits"]}
        self.assertEqual(code, 1)
        self.assertTrue(any(k == "identifier" and "李国强" in f for k, _, f in hits))           # supervisor in 致谢
        self.assertTrue(any(k == "section" and "致" in f for k, _, f in hits))
        self.assertIn(("identifier", "word/header1.xml", "institution: 清华大学"), hits)        # school in the header
        self.assertIn(("metadata", "docProps/core.xml", "creator: 张明远"), hits)
        self.assertIn(("metadata", "word/document.xml", "tracked-change or comment author: 张明远"), hits)

    def test_pdf_is_refused_for_comparison(self):
        pdf = self.write("thesis.pdf", b"%PDF-1.4\n")
        code, _, err = self.run_cli("blind", "--full", self.full, "--blind", pdf)
        self.assertEqual(code, 2)
        self.assertIn("PDF", err)


class PatternTests(unittest.TestCase):
    def test_numbers_next_to_han_characters(self):
        found = [(n["token"], str(n["value"]), n["pct"]) for n in ta.numbers_in(ta.norm("样本量为321人，β＝0.24，回收率85.7%，共3.12万条"))]
        self.assertEqual(found[:3], [("321", "321", False), ("0.24", "0.24", False), ("85.7%", "85.7", True)])
        one = lambda text: ta.numbers_in(text)[0]                                                   # noqa: E731
        self.assertTrue(ta.same(one("31200"), one("3.12万")))
        self.assertTrue(ta.same(one("0.42"), one("0.416")))
        self.assertFalse(ta.same(one("0.42"), one("0.24")))

    def test_definitions_with_full_width_brackets(self):
        defs = {(a, lang, long) for a, lang, long, *_ in ta.definitions(ta.norm(
            "本文采用技术接受模型（TAM）；感知有用性（Perceived Usefulness，PU）；TAM（技术接受模型）；perceived ease of use (PEOU)"))}
        self.assertTrue({("TAM", "zh", "本文采用技术接受模型"), ("PU", "en", "Perceived Usefulness"), ("PU", "zh", "感知有用性"),
                         ("TAM", "zh", "技术接受模型"), ("PEOU", "en", "perceived ease of use")} <= defs)
        self.assertTrue(ta.same_long("zh", "本文采用技术接受模型", "基于技术接受模型"))
        self.assertFalse(ta.same_long("zh", "感知有用性", "感知易用性"))
        self.assertTrue(ta.same_long("en", "structural equation modelling", "Structural Equation Modeling"))

    def test_callouts_captions_and_hypotheses(self):
        calls = [(k, n) for k, n, *_ in ta.callouts(ta.norm("如图3-2和表 4.3所示，见Figure 3.2；量表3与代表5不是表格；图3-1至3-3"))]
        self.assertEqual(calls, [("fig", "3-2"), ("tab", "4-3"), ("fig", "3-2"), ("fig", "3-1"), ("fig", "3-2"), ("fig", "3-3")])
        self.assertEqual(ta.caption_of(ta.norm("表3-2 样本描述性统计"), False), ("tab", "3-2"))
        self.assertIsNone(ta.caption_of(ta.norm("表3-2显示了样本结构。"), False))
        self.assertEqual(ta.hypotheses("H1、假设2、H2a–H2c得到支持；H1-H3；Hypothesis 4；H0被拒绝"),
                         {"H1", "H2", "H2a", "H2b", "H2c", "H3", "H4"})

    def test_author_year_citations(self):
        cites = ta.author_year(ta.norm("（Davis，1989；王明等，2020）表明……此外王明（2020）认为，Venkatesh et al. (2003) 与 (N = 312)"))
        self.assertEqual(cites, [("Davis", "1989"), ("王明", "2020"), ("Venkatesh", "2003"), ("此外王明", "2020")])
        self.assertTrue(ta.name_match("此外王明", "王明"))
        self.assertTrue(ta.name_match("Davis", "DAVIS F D"))


class MarkdownTests(AuditCase):
    def test_pandoc_keys_markdown_tables_and_chapter_files(self):
        self.write("refs.bib", "@book{smith2020, author = {Smith, Ann}, year = {2020}}\n"
                               "@book{lee2019, author = {Lee, Bo}, year = {2019}}\n")
        self.write("ch1.md", "# 第1章 绪论\n\n结构方程模型（SEM）被广泛使用 [@smith2020]，见表1-1和表1-2。\n\n"
                             "表1-1 样本\n\n| 指标 | 值 |\n|---|---|\n| N | 200 |\n\n注：N = 200。\n")
        self.write("ch2.md", "# 研究结果\n\nSEM结果见表1-1，H1得到支持 [@missing2021]。\n")
        audit = self.write("thesis-audit/audit.json", json.dumps({
            "files": [{"path": str(self.dir / "ch1.md"), "role": "chapter"}, {"path": str(self.dir / "ch2.md"), "role": "results"}],
            "key_numbers": [{"value": "200", "appears_in": ["table 1-1", "chapter 2"]}],
            "hypotheses": {"labels": ["H1"]}}, ensure_ascii=False))
        code, report = self.check(audit, "--bib", self.dir / "refs.bib")
        self.assertEqual(code, 1)
        self.assertEqual([r["status"] for r in self.rows(report, "key_numbers")], ["pass", "fail"])
        citations = self.messages(report, "citations")
        self.assertIn("missing2021 is cited but not in the .bib or \\bibitem list", citations)
        self.assertFalse(any("lee2019" in m for m in citations))                                # not printed
        self.assertTrue(any("表1-2 is called" in m for m in self.messages(report, "floats")))
        self.assertEqual({r["rule"]: r["status"] for r in self.rows(report, "hypotheses")}["H1 in the results"], "pass")
        self.assertEqual(self.rows(report, "abbreviations")[0]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
