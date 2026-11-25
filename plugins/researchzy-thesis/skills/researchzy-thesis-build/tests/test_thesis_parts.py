"""thesis_parts.py: published text is not changed silently, merged bibliographies and abbreviations agree."""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
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


tp = load("thesis_parts", HERE.parent / "scripts" / "thesis_parts.py")
fx = load("thesis_fixture", HERE / "thesis_fixture.py")

# Invented papers: no sentence comes from a published paper.
PAPER1_TEX = r"""\documentclass{article}
\usepackage{graphicx}
\begin{document}
\section{Method}
We surveyed 312 teachers in 2021 \citep{wang2021}. % a note to self
The partial least squares (PLS) model was estimated as in Figure~\ref{fig:model}.
Results are robust to the choice of priors, as \citet{li2020} also found, with 5\% missing.
\end{document}
"""
PAPER2_MD = """---
title: 第二篇论文（虚构）
---
# 研究设计

本研究采用技术接受模型（TAM）考察教师的使用意向[@wang2021]。样本量为312人。

如图3-2所示，感知有用性（PU）影响使用意向。
"""
CHAPTER2_TEX = r"""\chapter{Method}
We surveyed 321 teachers in 2021 \citep{wang2021}.
The partial least squares (PLS) model was estimated as in Figure~3.2.
Results are robust to the choice of priors, as \citet{li2020} also found, with 5\% missing.
This chapter reproduces the published paper with the publisher's permission.
"""
CHAPTER3_MD = """# 研究设计

本研究采用技术接受模型（TAM）考察教师的使用意向[@wang2021]。样本量为321人。

如图4-2所示，感知有用性（PU）影响使用意向。
"""


def paper3(shown: str) -> str:
    """A Word paper whose citation is a live Zotero field showing `shown`."""
    return (fx.para("本章使用感知易用性（PU）和结构方程模型（Structural Equation Modeling，SEM）进行分析。", "a")
            + fx.para(style="a", runs=fx.run("We measured perceived learning support (PLS) with five items ")
                      + fx.field(" ADDIN ZOTERO_ITEM CSL_CITATION {} ", shown) + fx.run(" in every school we visited."))
            + fx.sect())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "thesis-build"

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *argv, out_dir=True):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = tp.main([*argv, *(["--dir", str(self.out)] if out_dir else [])])
            except SystemExit as exc:
                code = exc.code
        return code, (json.loads(out.getvalue()) if out.getvalue().strip() else None), err.getvalue()

    def table(self, name: str) -> list:
        lines = (self.out / name).read_text(encoding="utf-8").splitlines()
        return [tuple(cell.strip() for cell in line[2:-2].split(" | ")) for line in lines
                if line.startswith("| ") and not line.startswith(("| Check", "|---"))]

    def write(self, relative: str, text: str) -> Path:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class SnapshotDiffTests(Base):
    def setUp(self):
        super().setUp()
        self.write("before/paper1.tex", PAPER1_TEX)
        self.write("before/paper2.md", PAPER2_MD)
        fx.make_docx(self.dir / "before" / "paper3.docx", paper3("(Wang, 2021)"))
        self.write("after/chapter2.tex", CHAPTER2_TEX)
        self.write("after/chapter3.md", CHAPTER3_MD)
        fx.make_docx(self.dir / "after" / "thesis.docx", paper3("[1]"))
        for name in ("before", "after"):
            code, _, _ = self.cli("snapshot", str(self.dir / name), "-o", str(self.out / f"{name}.json"), out_dir=False)
            self.assertEqual(code, 0)

    def test_changed_sentences_of_published_chapters_fail_and_renumbering_is_manual(self):
        code, result, _ = self.cli("diff", str(self.out / "before.json"), str(self.out / "after.json"))
        self.assertEqual(code, 1)
        self.assertEqual(sorted(result["failed"]), ["sentence: paper1.tex line 5", "sentence: paper2.md line 6"])
        rows = {row[1]: row for row in self.table("diff.md")}
        self.assertIn("样本量为321人", rows["paper2.md line 6"][3])
        self.assertEqual(rows["paper1.tex line 6"][2], "manual")       # Figure~\ref{...} became "Figure 3.2"
        self.assertEqual(rows["paper2.md line 8"][2], "manual")        # 图3-2 renumbered as 图4-2
        self.assertFalse([key for key in rows if key.startswith("paper3.docx")])   # only the citation field's text changed
        report = (self.out / "diff.md").read_text(encoding="utf-8")
        self.assertIn("## New text (1 sentences)", report)
        self.assertIn("reproduces the published paper", report)

    def test_a_file_named_unpublished_may_change(self):
        code, result, _ = self.cli("diff", str(self.out / "before.json"), str(self.out / "after.json"), "--unpublished", "paper2.md")
        self.assertEqual(code, 1)
        self.assertEqual(result["failed"], ["sentence: paper1.tex line 5"])
        self.assertIn("(unpublished file)", {row[1]: row for row in self.table("diff.md")}["paper2.md line 6"][3])

    def test_unchanged_text_passes(self):
        code, _, _ = self.cli("diff", str(self.out / "before.json"), str(self.out / "before.json"))
        self.assertEqual(code, 0)
        self.assertEqual(self.table("diff.md")[0][2], "pass")

    def test_a_snapshot_is_never_overwritten(self):
        code, _, err = self.cli("snapshot", str(self.dir / "before"), "-o", str(self.out / "before.json"), out_dir=False)
        self.assertEqual(code, 2)
        self.assertIn("exists", err)

    def test_numbers_next_to_chinese_characters_are_data_and_figure_numbers_are_not(self):
        self.assertNotEqual(tp.soft("样本量为312人。"), tp.soft("样本量为321人。"))
        self.assertEqual(tp.soft("如图3-2所示。"), tp.soft("如图4-2所示。"))
        self.assertEqual(tp.soft("见表 4.3 与第3章。"), tp.soft("见表5.1与第4章。"))
        self.assertEqual(tp.soft("As Figure 〔ref〕 shows (Wang, 2021)."), tp.soft("As Figure 3.2 shows [12]."))

    def test_extractors_drop_markup_and_keep_line_numbers(self):
        sentences = tp.sentences(tp.tex_blocks(PAPER1_TEX))
        self.assertEqual(sentences[0], ["line 5", "We surveyed 312 teachers in 2021 〔cite〕."])
        self.assertIn("with 5% missing", sentences[-1][1])
        self.assertFalse(any("note to self" in s for _, s in sentences))
        blocks = tp.docx_blocks(self.dir / "before" / "paper3.docx")
        self.assertEqual(blocks[1][0], "¶ 2")
        self.assertIn("〔cite〕", blocks[1][1])
        self.assertNotIn("Wang", blocks[1][1])


class BibTests(Base):
    A = """@article{wang2021,
  author = {Wang, Wei and Li, Na},
  title = {Teacher Acceptance of Learning Platforms},
  year = {2021},
  doi = {10.1000/xyz1}
}
@article{li2020, author = {李娜}, title = {教师技术接受研究}, journal = {教育研究}, year = 2020}
@article{zhang2019, title = {Self-efficacy and platform use}, year = {2019}}
@inproceedings{zhou2022, title = {A {Bayesian} model of {TAM}}, year = {2022}}
@article{chen2018, title = {Shared entry}, year = {2018}, doi = {10.1000/same}}
"""
    B = """@article{wang2021a, title = {Teacher acceptance of learning platforms}, year = {2021}, doi = {https://doi.org/10.1000/XYZ1}}
@article{li2020b, title = {{教师技术接受研究}}, year = {2020}}
@article{zhang2019, title = {Workload and burnout among teachers}, year = {2020}}
@article{zhou2023, title = {A Bayesian model of TAM}, year = {2023}}
@article{chen2018, title = {Shared entry}, year = {2018}, doi = {10.1000/same}}
"""

    def test_one_work_under_two_keys_and_one_key_for_two_works_fail(self):
        code, result, _ = self.cli("bib", str(self.write("a.bib", self.A)), str(self.write("b.bib", self.B)))
        self.assertEqual(code, 1)
        rows = {row[1]: row for row in self.table("bib-check.md")}
        self.assertEqual(rows["wang2021, wang2021a"][2], "fail")                      # the same DOI, written two ways
        self.assertIn("Same title and year", rows["li2020, li2020b"][3])              # a Chinese title, braces aside
        self.assertEqual(rows["li2020, li2020b"][2], "fail")
        self.assertEqual(rows[f"zhang2019 ({self.dir / 'a.bib'}, {self.dir / 'b.bib'})"][2], "fail")
        self.assertEqual(rows[f"chen2018 ({self.dir / 'a.bib'}, {self.dir / 'b.bib'})"][2], "pass")
        self.assertEqual(rows["zhou2022, zhou2023"][2], "manual")                     # same title, other year
        self.assertEqual(result["entries"], 10)

    def test_a_key_repeated_in_one_file_fails_and_clean_files_pass(self):
        code, _, _ = self.cli("bib", str(self.write("c.bib", "@book{x, title={One}, year={2001}}\n@book{x, title={Two}, year={2002}}\n")))
        self.assertEqual(code, 1)
        self.assertEqual(self.table("bib-check.md")[0][0], "key_repeated")
        code, _, _ = self.cli("bib", str(self.write("d.bib", "@book{y, title={Only one}, year={2001}}\n")))
        self.assertEqual(code, 0)


class AbbreviationTests(Base):
    def test_definitions_in_full_width_and_ascii_brackets(self):
        self.assertEqual(tp.definitions("本研究采用技术接受模型（TAM）考察使用意向。"), [("TAM", "技术接受模型", 0)])
        self.assertEqual(tp.definitions("We fit a partial least squares (PLS) model."), [("PLS", "partial least squares", 0)])
        self.assertEqual(tp.definitions("frames it (technology acceptance model, TAM)"), [("TAM", "technology acceptance model", 0)])
        self.assertEqual(tp.definitions("The TAM (technology acceptance model) helps."), [("TAM", "technology acceptance model", 0)])
        self.assertEqual(tp.definitions("样本量为312人（n = 312），见(Wang, 2021)。"), [])

    def test_one_abbreviation_with_two_long_forms_is_listed_in_each_script(self):
        self.write("papers/paper1.tex", PAPER1_TEX)
        self.write("papers/paper2.md", PAPER2_MD)
        fx.make_docx(self.dir / "papers" / "paper3.docx", paper3("(Wang, 2021)"))
        code, result, _ = self.cli("abbreviations", str(self.dir / "papers"))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(result["two_long_forms"]), ["PLS", "PU"])
        rows = {row[1]: row for row in self.table("abbreviations.md")}
        self.assertIn("partial least squares (paper1.tex line 6)", rows["PLS"][3])
        self.assertIn("perceived learning support (paper3.docx ¶ 2)", rows["PLS"][3])
        self.assertIn("感知有用性 (paper2.md line 8)", rows["PU"][3])
        self.assertEqual(rows["TAM"][2], "pass")
        self.assertIn("技术接受模型", rows["TAM"][3])
        self.assertEqual(rows["SEM"][2], "pass")          # a Chinese and an English long form are not two meanings


DEPENDENT = """<?xml version="1.0" encoding="utf-8"?>
<style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" version="1.0">
 <info><title>Invented dependent style</title><id>http://example.org/dependent</id>
  <link href="http://example.org/parent" rel="independent-parent"/><updated>2026-01-01T00:00:00+00:00</updated></info>
</style>"""
MINIMAL = """<?xml version="1.0" encoding="utf-8"?>
<style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" version="1.0">
 <info><title>Invented minimal style</title><id>http://example.org/minimal</id><updated>2026-01-01T00:00:00+00:00</updated></info>
 <citation><layout prefix="(" suffix=")" delimiter="; "><text variable="title"/><date variable="issued" prefix=", ">
  <date-part name="year"/></date></layout></citation>
 <bibliography><layout><text variable="title"/></layout></bibliography>
</style>"""


class CslTests(Base):
    def setUp(self):
        super().setUp()
        self.bib = self.write("refs.bib", BibTests.A)

    def test_without_pandoc_the_sample_is_not_checked(self):
        with mock.patch.object(tp.shutil, "which", return_value=None):
            code, result, _ = self.cli("csl-sample", str(self.bib), str(self.write("minimal.csl", MINIMAL)))
        self.assertEqual(code, 0)
        self.assertEqual(result["style"]["title"], "Invented minimal style")
        self.assertIn("pandoc is not installed", self.table("csl-sample.md")[0][3])

    def test_a_dependent_style_names_its_parent_and_is_not_checked(self):
        code, result, _ = self.cli("csl-sample", str(self.bib), str(self.write("dependent.csl", DEPENDENT)))
        self.assertEqual((code, result["parent"]), (0, "http://example.org/parent"))
        self.assertEqual(self.table("csl-sample.md")[0][2], "not_checked")

    def test_unknown_keys_are_refused(self):
        code, _, err = self.cli("csl-sample", str(self.bib), str(self.write("minimal.csl", MINIMAL)), "--keys", "wang2021,nobody")
        self.assertEqual(code, 2)
        self.assertIn("nobody", err)

    @unittest.skipUnless(shutil.which("pandoc"), "pandoc is not installed")
    def test_pandoc_renders_the_sample(self):
        code, _, _ = self.cli("csl-sample", str(self.bib), str(self.write("minimal.csl", MINIMAL)), "--keys", "wang2021,li2020")
        self.assertEqual(code, 0)
        self.assertEqual(self.table("csl-sample.md")[0][2], "manual")
        # The style decides the case of the title; the sample only has to contain the work.
        self.assertIn("teacher acceptance of learning platforms", (self.out / "csl-sample.md").read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
