"""manuscript_check.py: what the check and diff commands report, and what they leave alone."""
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

SCRIPT = Path(__file__).parents[1] / "scripts" / "manuscript_check.py"
spec = importlib.util.spec_from_file_location("manuscript_check", SCRIPT)
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)

CLEAN = """# Home monitoring after stroke

## Abstract

We followed 1,204 adults for 24 months. Recurrent stroke occurred in 48/602 (8.0%) monitored and
71/602 (11.8%) unmonitored patients (hazard ratio 0.66). The mean age was 67 years.

## Introduction

Stroke often recurs within two years [@adams2011]. Trials of home blood pressure (BP) monitoring
report lower BP [@baker2018], but routine care has not been studied.

## Methods

We analysed a registry cohort of 1204 adults with a follow-up visit at 24 months. Patients
without follow-up data were censored.

## Results

The mean age was 67.4 years. Recurrent stroke occurred in 48/602 (8.0%) monitored patients and
in 11.8% (71/602) of unmonitored patients ([@tbl:outcomes]; see https://example.org/v2/table3).

| Outcome | Monitored | Unmonitored |
|---|---|---|
| Hazard ratio | 0.662 | reference |

## Discussion

Monitoring was associated with fewer recurrent strokes, in line with trial evidence
[@baker2018, p. 12].

## References

1. Adams A. A journal. 2011;42(5):1489-1494. doi:10.1000/example.110.602615
"""
BIB = "@article{adams2011, title={A}, year={2011}}\n@article{baker2018,\n  title={B}, year={2018}}\n"


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "writing"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, text: str) -> str:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run_cli(self, *argv):
        old, out = sys.argv, io.StringIO()
        sys.argv = ["manuscript_check.py", *argv, "--out", str(self.out)]
        try:
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = mc.main()
        finally:
            sys.argv = old
        return code, json.loads(out.getvalue())

    def check(self, text: str, *flags, name: str = "paper.md"):
        code, summary = self.run_cli("check", self.write(name, text), *flags)
        report = json.loads((self.out / "manuscript-check.json").read_text(encoding="utf-8"))
        return code, summary, report

    def codes(self, report: dict, check: str | None = None) -> list[str]:
        return [f["code"] for f in report["findings"] if check in (None, f["check"])]

    def messages(self, report: dict, code: str) -> list[str]:
        return [f["message"] for f in report["findings"] if f["code"] == code]

    def diff(self, before: str, after: str, *flags):
        code, summary = self.run_cli("diff", self.write("before.md", before), self.write("after.md", after), *flags)
        report = json.loads((self.out / "revision-check.json").read_text(encoding="utf-8"))
        return code, summary, report


class CheckTests(Case):
    def test_a_clean_manuscript_has_no_findings(self):
        code, summary, report = self.check(CLEAN, "--bib", self.write("refs.bib", BIB), "--final",
                                           "--budget", "Abstract=250,Introduction=600,Total=3500")
        self.assertEqual(report["findings"], [])
        self.assertEqual((code, summary["errors"], summary["warnings"], summary["not_checked"]), (0, 0, 0, {}))
        self.assertEqual(set(report["checks"].values()), {"checked"})
        self.assertIn("Final check: 0 errors, 0 warnings", (self.out / "manuscript-check.md").read_text(encoding="utf-8"))
        self.assertEqual(len(report["files"][0]["sha256"]), 64)

    def test_placeholders_are_warnings_in_a_draft_and_errors_when_final(self):
        text = ("## Results\n\nSurvival improved [Evidence needed: table of survival by arm]. Others agree "
                "[Citation needed: a cohort study] and [@smith2020; @NEW: trial in adults]. "
                "[Author input needed: ethics approval number]\n\n"
                "TODO rewrite. The dose was XXX mg (TBD), see Figure ??. FIXME. [Citation needed: TBD]\n\n"
                "```\nTODO inside code is not a placeholder\n```\n\nChapter XXXI is not one, nor is a todo list.\n")
        code, summary, report = self.check(text)
        self.assertEqual(sorted(self.codes(report, "placeholders")),
                         ["author_input_needed", "citation_needed", "citation_needed", "evidence_needed",
                          "new_citation_marker", "todo", "todo", "todo", "todo", "unresolved_reference"])
        self.assertEqual((code, summary["errors"], summary["placeholders"]), (0, 0, 10))
        self.assertNotIn("citations", summary["by_check"])        # @NEW is a placeholder, not a missing key
        code, summary, report = self.check(text, "--final")
        self.assertEqual((code, summary["errors"]), (1, 10))
        self.assertEqual({f["severity"] for f in report["findings"] if f["check"] == "placeholders"}, {"error"})

    def test_a_percentage_must_agree_with_its_fraction(self):
        _, _, report = self.check(
            "## Results\n\nResponse in 12/40 (35%) and 12 of 40 patients (30%). Relapse in 35% (12/40) and "
            "in 30.0% (n = 12/40). Two thirds, 2/3 (66.7%) or 2/3 (67%), but not 2/3 (66%). "
            "Overall 1,204/2,000 (60.2%). Version 3/4 (2023) is not a percentage.\n\n"
            "| Arm | n/N (%) |\n|---|---|\n| A | 71/602 (12.8%) |\n| B | 48/602 (8.0%) |\n")
        self.assertEqual(self.messages(report, "percent_mismatch"),
                         ["12/40 is 30.0%, written as 35%", "2/3 is 66.7%, written as 66%",
                          "12/40 is 30.0%, written as 35%", "71/602 is 11.8%, written as 12.8%"])
        self.assertEqual({f["severity"] for f in report["findings"] if f["code"] == "percent_mismatch"}, {"error"})

    def test_abstract_numbers_must_be_in_the_main_text(self):
        text = ("## Abstract\n\nWe enrolled 120 adults in 3 centres. Adherence was 83% and the hazard ratio 0.66 "
                "(P < 0.01).\n\n"
                "## Results\n\nWe enrolled 124 adults in three centres. The hazard ratio was 0.662 (P = 0.004).\n")
        _, summary, report = self.check(text)
        self.assertEqual(self.messages(report, "abstract_number_not_in_body"),
                         ["120 is in the abstract but not in the main text or tables",
                          "83% is in the abstract but not in the main text or tables"])
        self.assertEqual(report["checks"]["abstract_numbers"], "checked")
        _, summary, report = self.check("## Results\n\nAdherence was 83%.\n")
        self.assertEqual(summary["not_checked"]["abstract_numbers"], "no Abstract section found")
        _, summary, report = self.check("Adherence was 83% in 120 adults.\n", name="abstract.md")
        self.assertEqual(summary["not_checked"]["abstract_numbers"], "no main text was given to compare the abstract with")
        self.assertEqual(report["findings"], [])

    def test_one_quantity_with_two_values(self):
        text = ("## Abstract\n\nThe mean age was 67.4 years (N = 120). Sensitivity was 91%.\n\n"
                "## Results\n\nThe mean age was 67.9 years (N = 120; n = 60 per arm). Sensitivity was 88% for "
                "model A and sensitivity was 91% for model B. The median follow-up was 24 months.\n\n"
                "| Model | Sensitivity |\n|---|---|\n| A | 88 |\n")
        _, _, report = self.check(text)
        self.assertEqual(self.messages(report, "value_conflict"), ['"mean age" is 67.4 in the abstract and 67.9 in the text'])
        self.assertEqual(self.codes(report, "abstract_numbers"), [])      # 67.4 is reported once, as a conflict

    def test_one_value_at_two_precisions(self):
        text = ("## Results\n\nThe ratio was 0.66 and later 0.660. Accuracy was 91.2% and, in the table, 91.20%. "
                "We used 12 sites for 12.0 months, and P < .05 or P < 0.05. Half is 50% or 50.0%.\n")
        _, _, report = self.check(text)
        self.assertEqual(self.messages(report, "precision_variant"),
                         ["one value at different precision: 0.66 (1×), 0.660 (1×)",
                          "one value at different precision: 91.2% (1×), 91.20% (1×)",
                          "one value at different precision: 50% (1×), 50.0% (1×)"])

    def test_numbers_in_markup_are_not_results(self):
        def tokens(text):
            return [n["token"] for n in mc.numbers_in(mc.to_plain(text))]
        self.assertEqual(tokens("As shown [@smith2020; @lee2021, p. 4] and \\citep[p. 3]{doe1999}, see [12] and [3-5]."), [])
        self.assertEqual(tokens("Figure~\\ref{fig:3}, \\includegraphics[width=0.8\\textwidth]{fig2.pdf}, "
                                "https://example.org/v2/3 and doi:10.1000/182."), [])
        self.assertEqual(tokens("COVID-19, IL-6 and top-5 are names; 3D too."), [])
        self.assertEqual(tokens("From 1,204 to -2.4 (95% CI 0.46-0.95), P < .05, 12 percent."),
                         ["1204", "-2.4", "95%", "0.46", "0.95", ".05", "12%"])
        self.assertEqual([n["bound"] for n in mc.numbers_in("P < 0.05, n >= 10, x ≤ -3")], ["<0.05", "≥10", "≤-3"])

    def test_term_variants(self):
        text = ("## Methods\n\nThe follow-up visit was at 24 months; patients without followup data were censored. "
                "The dataset is public and the data set is large. We treated COVID-19 and later Covid-19 cases. "
                "We fine-tuned BERT; Bert was frozen.\n\n"
                "In the long term, long-term outcomes matter. Any one of them may ask anyone. "
                "Pretraining helps. In the US, most of us agree. Transformers and transformers.\n")
        _, _, report = self.check(text)
        self.assertEqual(self.messages(report, "term_variant"),
                         ['one term, written "follow-up" (1×) and "followup" (1×)',
                          'one term, written "dataset" (1×) and "data set" (1×)',
                          'one term, written "COVID-19" (1×) and "Covid-19" (1×)',
                          'one term, written "BERT" (1×) and "Bert" (1×)'])

    def test_abbreviations(self):
        text = ("## Abstract\n\nA randomised controlled trial (RCT) of 120 adults. The RCT ran for a year. "
                "MRI was done once.\n\n"
                "## Introduction\n\nEvery RCT has limits, and this RCT too. The area under the curve (AUC) was the "
                "outcome. Body mass index (BMI) was recorded.\n\n"
                "## Methods\n\nAUC (area under the curve) was computed. HbA1c and DNA were measured, and two "
                "CNNs were trained; each CNN had five layers. LDL (low-density lipoprotein) and LDL particles. "
                "Stage II and stage III disease were pooled; stage II was common. CIFAR-10 and CIFAR-10-C are "
                "data sets, and IL-6 rose with IL-6 receptor blockade.\n")
        _, _, report = self.check(text)
        self.assertEqual(sorted(self.messages(report, "abbreviation_not_defined")),
                         ["CNN is used 2 times in the main text and never defined there",
                          "RCT is used 2 times in the main text and never defined there; it is defined only in the abstract"])
        self.assertEqual(self.messages(report, "abbreviation_defined_twice"), ["AUC is defined 2 times in the main text"])
        self.assertEqual(self.messages(report, "abbreviation_defined_not_used"),
                         ["BMI is defined in the main text and not used again there"])
        _, _, report = self.check("## Methods\n\nWe used OCT in all eyes. Optical coherence tomography (OCT) is fast.\n")
        self.assertEqual(self.messages(report, "abbreviation_used_before_definition"),
                         ["OCT is used in the main text before it is defined"])

    def test_mixed_spelling(self):
        _, _, report = self.check("## Methods\n\nWe analysed tumour samples and randomised mice. The colour was "
                                  "then analyzed. The World Health Organization was told.\n")
        self.assertEqual(self.messages(report, "mixed_spelling"), ["1 US and 4 UK spellings; the US ones are analyzed (1×)"])
        for text in ("We analysed the tumour and its colour for the World Health Organization.",
                     "We analyzed the tumor. Two analyses of one organism showed a characteristic colorectal pattern, "
                     "with optimism in the laboratory."):
            _, _, report = self.check("## Methods\n\n" + text + "\n")
            self.assertEqual(self.codes(report, "spelling"), [], text)

    def test_citation_keys_against_the_bib(self):
        text = ("## Introduction\n\nKnown \\cite{adams2011, baker2018} and \\citep[see][p. 3]{ghost1999}; "
                "also @adams2011 and [-@phantom2020; see @baker2018, p. 4]. Figure @fig:flow, mail a@b.org.\n")
        bib = self.write("refs.bib", BIB + "@string{x = {y}}\n@book{unused2015, title={C}}\n")
        code, summary, report = self.check(text, "--bib", bib, "--final")
        self.assertEqual(self.messages(report, "citation_not_in_bib"),
                         ["ghost1999 is cited but is not in the .bib", "phantom2020 is cited but is not in the .bib"])
        self.assertEqual(self.messages(report, "bib_entry_not_cited"), ["unused2015 is in the .bib but never cited"])
        self.assertEqual((code, summary["errors"], summary["warnings"]), (1, 2, 1))
        _, _, report = self.check(text + "\n\\nocite{*}\n", "--bib", bib)
        self.assertEqual(self.codes(report, "citations"), ["citation_not_in_bib", "citation_not_in_bib"])
        _, summary, report = self.check(text)
        self.assertEqual((summary["not_checked"]["citations"], self.codes(report, "citations")), ("no .bib given", []))
        _, summary, _ = self.check("## Results\n\nAs shown before [12] and by Smith et al. (2020).\n", "--bib", bib)
        self.assertIn("no \\cite or @key citations found", summary["not_checked"]["citations"])

    def test_word_budget(self):
        text = ("# Title\n\nAn Author\n\n## Abstract\n\n" + "word " * 30 + "\n\n## Methods\n\n" + "word " * 10
                + "[@key2020] \\cite{other}\n\n### Participants\n\n" + "word " * 5
                + "\n\n| not | counted |\n|---|---|\n| 1 | 2 |\n\n## References\n\n" + "reference " * 50 + "\n")
        code, summary, report = self.check(text, "--budget", "Abstract=25, Methods=15, Total=17, Conclusion=100", "--final")
        words = {s["title"]: (s["words"], s.get("budget")) for s in report["sections"]}
        self.assertEqual(words["Abstract"], (30, 25))
        self.assertEqual(words["Methods"], (15, 15))                # with its sub-section, without table and citations
        self.assertEqual(words["Participants"], (5, None))
        self.assertEqual(words["Total (main text)"], (17, 17))      # the author line and Methods; no abstract, no references
        self.assertEqual(self.messages(report, "over_budget"), ["Abstract has 30 words; the budget is 25 (5 over)"])
        self.assertEqual(self.messages(report, "budget_section_not_found"),
                         ['no section is called "Conclusion", so its budget of 100 words was not checked'])
        self.assertEqual((code, summary["errors"]), (1, 1))
        self.assertIn("Conclusion", summary["not_checked"]["word_budget"])
        _, summary, _ = self.check(text)
        self.assertEqual(summary["not_checked"]["word_budget"], "no --budget given")
        with self.assertRaises(SystemExit) as raised:
            self.check(text, "--budget", "Abstract:250")
        self.assertEqual(raised.exception.code, 2)

    def test_latex_input(self):
        text = "\n".join([
            r"\documentclass[11pt]{article}", r"\begin{document}", r"\begin{abstract}",
            r"We enrolled 120 participants; accuracy was 91.2\%. % TODO tighten this",
            r"\end{abstract}", r"\section{Introduction}\label{sec:intro}",
            r"Earlier work~\cite{smith2020} reports 90\% (Figure~\ref{fig:1}).",
            r"\section{Results}", r"We enrolled 124 participants ($n = 124$).",
            r"\begin{verbatim}", "TODO in code 99999", r"\end{verbatim}",
            r"\begin{tabular}{lc}", r"Model & Accuracy \\", r"CNN & 91.20\% \\", r"\end{tabular}",
            r"\begin{thebibliography}{9}", r"\bibitem{smith2020} Smith. Pages 1--20, 2020.", r"\end{thebibliography}",
            r"\end{document}"])
        code, summary, report = self.check(text, "--budget", "Abstract=5", name="main.tex")
        self.assertEqual(sorted(self.codes(report)),
                         ["abstract_number_not_in_body", "over_budget", "precision_variant", "todo"])
        self.assertEqual(self.messages(report, "abstract_number_not_in_body"),
                         ["120 is in the abstract but not in the main text or tables"])
        self.assertEqual([f["where"] for f in report["findings"] if f["code"] == "todo"], [[f"{self.dir / 'main.tex'}:4"]])
        self.assertEqual(report["checks"]["citations"], "checked")              # against the \bibitem list
        self.assertEqual({s["title"]: s["words"] for s in report["sections"]}["Abstract"], 7)

    def test_docx_input(self):
        w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

        def p(text, style=""):
            ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
            return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"

        body = (p("Abstract", "Heading1") + p("Response in 12/40 (30%) of adults.")
                + p("Results", "Heading1")
                + "<w:p><w:r><w:t>Response in 12/40 </w:t></w:r><w:del><w:r><w:delText>(99%) </w:delText></w:r></w:del>"
                  "<w:ins><w:r><w:t>(35%) of adults.</w:t></w:r></w:ins></w:p>"
                + "<w:tbl><w:tr><w:tc>" + p("Arm A") + "</w:tc><w:tc>" + p("5/10 (40%)") + "</w:tc></w:tr></w:tbl>")
        path = self.dir / "paper.docx"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
        code, summary = self.run_cli("check", str(path))
        report = json.loads((self.out / "manuscript-check.json").read_text(encoding="utf-8"))
        self.assertEqual(self.messages(report, "percent_mismatch"),
                         ["12/40 is 30.0%, written as 35%", "5/10 is 50.0%, written as 40%"])
        self.assertEqual([f["where"] for f in report["findings"] if f["code"] == "percent_mismatch"],
                         [[f"{path}:4"], [f"{path}:5"]])                        # paragraphs, not lines
        self.assertEqual(self.messages(report, "abstract_number_not_in_body"),
                         ["30% is in the abstract but not in the main text or tables"])   # 99% was a tracked deletion
        self.assertEqual([(s["title"], s["words"]) for s in report["sections"]], [("Abstract", 6), ("Results", 6)])

    def test_bad_input_exits_with_2(self):
        broken = self.dir / "broken.docx"
        broken.write_bytes(b"not a zip file")
        for argv in (["check", str(self.dir / "missing.md")], ["check", self.write("paper.pdf", "x")],
                     ["check", self.write("empty.md", "\n\n")], ["check", str(broken)],
                     ["check", self.write("ok.md", "Some text.\n"), "--bib", str(self.dir / "missing.bib")],
                     ["diff", self.write("ok2.md", "Some text.\n"), str(self.dir / "missing.md")]):
            with self.assertRaises(SystemExit) as raised:
                self.run_cli(*argv)
            self.assertEqual(raised.exception.code, 2, argv)


BEFORE = """## Results

Recurrent stroke occurred in 48 of 602 monitored patients (8.0%) and in 71 of 602 unmonitored
patients (11.8%) [@registry2021]. The hazard ratio was 0.66 (95% CI 0.46 to 0.95), which suggests
that monitoring may be associated with fewer recurrent strokes [@baker2018]. Systolic pressure
fell from 148.2 mmHg to 136.5 mmHg in the monitored group. Adherence did not differ between men
and women (P = 0.41). Mortality was lower in the monitored group, although the difference was small.

## Discussion

Our findings are consistent with trial evidence [@baker2018; @clark2017]. Approximately 17% of
patients stopped monitoring within a year. Residual confounding is likely, because sicker patients
were less often offered a monitor. The effect was not seen in patients older than 80 years.
"""


class DiffTests(Case):
    def test_identical_texts_have_no_changes(self):
        code, summary, report = self.diff(BEFORE, BEFORE, "--strict")
        self.assertEqual(code, 0)
        self.assertEqual(summary["sentences"], {"before": 11, "after": 11, "unchanged": 11, "edited": 0,
                                                "without_counterpart_before": 0, "without_counterpart_after": 0})
        for group in ("numbers", "citations", "wording"):
            self.assertEqual(set(summary[group].values()), {0}, group)
        self.assertIn("No number changed.", (self.out / "revision-check.md").read_text(encoding="utf-8"))

    def test_a_polish_that_keeps_numbers_citations_and_claims_is_clean(self):
        after = (BEFORE.replace("occurred in 48 of 602 monitored patients", "was recorded in 48 of 602 monitored patients")
                 .replace("which suggests\nthat monitoring may be", "suggesting\nthat monitoring might be")
                 .replace("Approximately 17% of", "About 17% of").replace("Mortality was lower", "Mortality was reduced"))
        code, summary, report = self.diff(BEFORE, after, "--strict")
        self.assertEqual((code, summary["numbers_or_citations_changed"]), (0, 0))
        self.assertEqual(summary["sentences"]["edited"], 4)
        self.assertEqual(set(summary["wording"].values()), {0})
        self.assertEqual(report["not_compared"], {"before": [], "after": []})

    def test_numbers_changed_reordered_disappeared_and_appeared(self):
        after = (BEFORE.replace("(11.8%)", "(11.3%)")
                 .replace("from 148.2 mmHg to 136.5 mmHg", "from 136.5 mmHg to 148.2 mmHg").replace("(P = 0.41)", "(P = 0.410)")
                 .replace("Residual confounding is likely, because sicker patients\nwere less often offered a monitor. ", "")
                 + "\nIn a further 212 patients the monitor was never switched on.\n")
        before = BEFORE.replace("Residual confounding is likely", "Residual confounding in 30 clinics is likely")
        code, summary, report = self.diff(before, after)
        self.assertEqual(code, 0)                                        # not strict
        self.assertEqual([(c["before_values"], c["after_values"]) for c in report["numbers"]["changed"]],
                         [(["11.8%"], ["11.3%"]), (["0.41"], ["0.410"])])
        self.assertEqual([(c["before_values"], c["after_values"]) for c in report["numbers"]["reordered"]],
                         [(["148.2", "136.5"], ["136.5", "148.2"])])
        self.assertEqual([(d["value"], d["times"]) for d in report["numbers"]["disappeared"]], [("30", 1)])
        self.assertIn("Residual confounding in 30 clinics", report["numbers"]["disappeared"][0]["before"])
        self.assertEqual([(a["value"], a["times"]) for a in report["numbers"]["appeared"]], [("212", 1)])
        code, summary, _ = self.diff(before, after, "--strict")
        self.assertEqual((code, summary["numbers_or_citations_changed"]), (1, 5))

    def test_a_sign_or_an_inequality_is_part_of_the_number(self):
        _, _, report = self.diff("The change was -2.4 points (P < 0.05) in 1,204 adults.\n",
                                 "The change was 2.4 points (P > 0.05) in 1204 adults.\n")
        self.assertEqual([(c["before_values"], c["after_values"]) for c in report["numbers"]["changed"]],
                         [(["-2.4", "<0.05"], ["2.4", ">0.05"])])

    def test_citations_dropped_added_and_moved(self):
        after = (BEFORE.replace(" [@registry2021]", "")
                 .replace("[@baker2018]. Systolic", "[@baker2018; @registry2021]. Systolic")
                 .replace("[@baker2018; @clark2017]", "[@baker2018]").replace("within a year.", "within a year [@new2024]."))
        code, summary, report = self.diff(BEFORE, after, "--strict")
        self.assertEqual(code, 1)
        self.assertEqual([(d["citation"], d["times_before"], d["times_after"]) for d in report["citations"]["dropped"]],
                         [("clark2017", 1, 0)])
        self.assertEqual([a["citation"] for a in report["citations"]["added"]], ["new2024"])
        moved = report["citations"]["moved"]
        self.assertEqual([m["citation"] for m in moved], ["registry2021"])
        self.assertTrue(moved[0]["before"].startswith("Recurrent stroke occurred"))
        self.assertTrue(moved[0]["now_in"].startswith("The hazard ratio was 0.66"))
        _, _, report = self.diff("Shown before \\cite{a2020,b2021}. Also true [3-5].\n", "Shown before \\cite{a2020}. Also true [3, 4].\n")
        self.assertEqual([d["citation"] for d in report["citations"]["dropped"]], ["[3-5]", "b2021"])
        self.assertEqual([a["citation"] for a in report["citations"]["added"]], ["[3,4]"])

    def test_hedges_intensifiers_negation_and_direction(self):
        after = (BEFORE.replace("which suggests\nthat monitoring may be", "which demonstrates\nthat monitoring is")
                 .replace("are consistent with", "are clearly consistent with")
                 .replace("did not differ", "differed").replace("Mortality was lower", "Mortality was higher")
                 .replace("was not seen", "was seen"))
        code, summary, report = self.diff(BEFORE, after, "--strict")
        self.assertEqual((code, summary["numbers_or_citations_changed"]), (0, 0))     # wording alone is not a strict failure
        wording = report["wording"]
        self.assertEqual([h["words"] for h in wording["hedges_removed"]], [["may", "suggests"]])
        self.assertEqual([i["words"] for i in wording["intensifiers_added"]], [["demonstrates"], ["clearly"]])
        self.assertEqual([n["words"] for n in wording["negation_changed"]], [["not", "→"], ["not", "→"]])
        self.assertEqual([d["words"] for d in wording["direction_changed"]], [["lower", "→", "higher"]])
        self.assertTrue(wording["direction_changed"][0]["after"].startswith("Mortality was higher"))
        text = (self.out / "revision-check.md").read_text(encoding="utf-8")
        self.assertIn("### Hedges removed (1)", text)
        self.assertIn("### Negation changed (2)", text)

    def test_sentences_without_a_counterpart_are_listed_not_judged(self):
        after = BEFORE.replace("Residual confounding is likely, because sicker patients\nwere less often offered a monitor.",
                               "Unmeasured differences between the groups cannot be excluded.")
        _, summary, report = self.diff(BEFORE, after)
        counts = summary["sentences"]
        self.assertEqual((counts["without_counterpart_before"], counts["without_counterpart_after"]), (1, 1))
        self.assertEqual(report["not_compared"]["before"],
                         ["Residual confounding is likely, because sicker patients were less often offered a monitor."])
        self.assertEqual(report["not_compared"]["after"], ["Unmeasured differences between the groups cannot be excluded."])
        self.assertEqual(report["wording"]["hedges_removed"], [])
        self.assertIn("Not compared: read these yourself.", (self.out / "revision-check.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
