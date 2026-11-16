"""polish_check.py: what a language polish may not change, and the change log against the real diff."""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "polish_check.py"
spec = importlib.util.spec_from_file_location("polish_check", SCRIPT)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

BASE = """## Discussion

Nurses who worked night shifts slept worse than day-shift nurses (PSQI 9.1 vs 6.4, P < 0.001) [3]. These results
may suggest that night work is associated with poor sleep [4, 5]. The intervention group showed slightly better
scores than the control group, but the difference was not significant (P = 0.21).

Mean sleep latency fell by −4.2 minutes after 12 weeks (Smith et al., 2020). Night work was associated with insomnia
in 38% of nurses. However, only 120 nurses were included.
"""

LIGHT_BEFORE = """In this study, sleep quality of nurses who works night shifts were worse than in day-shift nurses [3].
This results may suggest an association between night work and poor sleep.
"""
LIGHT_AFTER = """In this study, the sleep quality of nurses who work night shifts was worse than in day-shift nurses [3].
These results may suggest an association between night work and poor sleep.
"""

TEX = r"""\documentclass{article}
\begin{document}
\section{Results}
Adherence was high (Figure~\ref{fig:adherence}) and fell in winter (Table~\ref{tab:season}).
The model was $y = \beta x + \epsilon$ with $\alpha = 0.05$ \cite{buysse1989,liu2022}.
\label{sec:results}
\end{document}
"""


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "polish"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, text: str) -> str:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = pc.main([*argv, "--out", str(self.out)])
        return code, json.loads(out.getvalue())

    def diff(self, before: str, after: str, *flags, suffix: str = ".md"):
        code, _ = self.run_cli("diff", self.write("before" + suffix, before), self.write("after" + suffix, after), *flags)
        return code, json.loads((self.out / "polish-check.json").read_text(encoding="utf-8"))

    def codes(self, report: dict, severity: str = "error") -> list[str]:
        return [f["code"] for f in report["findings"] if f["severity"] == severity]

    def messages(self, report: dict, code: str) -> list[str]:
        return [f["message"] for f in report["findings"] if f["code"] == code]


class CleanControlTests(Case):
    def test_identical_texts_report_nothing(self):
        code, report = self.diff(BASE, BASE, "--level", "light")
        self.assertEqual((code, report["findings"], report["counts"]), (0, [], {"unchanged": 7}))
        self.assertIn("0 errors, 0 warnings", (self.out / "polish-check.md").read_text(encoding="utf-8"))

    def test_a_light_polish_of_articles_and_agreement_reports_nothing(self):
        code, report = self.diff(LIGHT_BEFORE, LIGHT_AFTER, "--level", "light")
        self.assertEqual((code, report["findings"], report["counts"]), (0, [], {"edited": 2}))

    def test_a_medium_polish_that_keeps_the_content_reports_nothing(self):
        after = (BASE.replace("Nurses who worked night shifts slept worse", "Night-shift nurses slept worse")
                 .replace("These results\nmay suggest", "These results might suggest")
                 .replace("but the difference was not significant", "although the difference was not significant")
                 .replace("of nurses. However, only", "of nurses, although only"))
        code, report = self.diff(BASE, after)
        self.assertEqual((code, report["findings"]), (0, []))
        self.assertEqual(report["counts"], {"unchanged": 2, "edited": 3, "merged": 1})

    def test_a_split_sentence_is_compared(self):
        after = BASE.replace(", but the difference was not significant (P = 0.21).",
                             ". However, the difference was not significant (P = 0.21).")
        code, report = self.diff(BASE, after)
        self.assertEqual((code, report["findings"], report["counts"]["split"]), (0, [], 1))
        code, report = self.diff(BASE, after.replace("(P = 0.21)", "(P = 0.12)"))
        self.assertEqual(self.messages(report, "number_changed"), ["0.21 → 0.12"])
        self.assertEqual([f["where"] for f in report["findings"]], ["¶2.3 → ¶2.3, ¶2.4"])


class NumberTests(Case):
    BEFORE = "The mean change was −2.4 points (P < 0.05) and the score was 18% lower than at baseline.\n"

    def test_sign_inequality_and_percentage_direction(self):
        code, report = self.diff(self.BEFORE, "The mean change was 2.4 points (P > 0.05) and the score was 18% higher "
                                              "than at baseline.\n")
        self.assertEqual(code, 1)
        self.assertEqual(self.messages(report, "number_changed"), ["-2.4, 18% (down), <0.05 → 18% (up), 2.4, >0.05"])
        self.assertEqual(self.messages(report, "direction_changed"), ["lower → higher"])

    def test_the_same_values_written_differently_are_clean(self):
        code, report = self.diff(self.BEFORE, "The mean change was -2.4 points (P<0.05), and the score fell by 18% from "
                                              "its baseline.\n")
        self.assertEqual((code, report["findings"]), (0, []))

    def test_a_unit_swap_is_an_error_and_a_dropped_unit_a_warning(self):
        before = "Patients received 5 mg daily for 12 weeks; those aged 65 years or older were excluded.\n"
        code, report = self.diff(before, before.replace("5 mg", "5 g"))
        self.assertEqual((code, self.messages(report, "unit_changed")), (1, ["5 mg → 5 g"]))
        code, report = self.diff(before, before.replace("for 12 weeks", "over a 12-week period"))
        self.assertEqual((code, report["findings"]), (0, []))
        code, report = self.diff(before, before.replace("65 years or older", "65 or older"))
        self.assertEqual((code, self.messages(report, "unit_dropped")), (0, ["65 yr → 65"]))

    def test_number_words_are_numbers(self):
        before = "Three groups of twenty-five patients were followed for 1.2 million person-hours.\n"
        code, report = self.diff(before, before.replace("Three", "Four"))
        self.assertEqual((code, self.messages(report, "number_changed")), (1, ["3 → 4"]))
        code, report = self.diff(before, "3 groups of 25 patients were followed for 1,200,000 person-hours.\n")
        self.assertEqual((code, report["findings"]), (0, []))

    def test_values_that_trade_places(self):
        before = "Sensitivity was 91% and specificity was 78%. The complication rate decreased from 12.4% to 8.1%.\n"
        swapped = "Sensitivity was 78% and specificity was 91%. The complication rate decreased from 8.1% to 12.4%.\n"
        code, report = self.diff(before, swapped)
        self.assertEqual(code, 1)
        self.assertEqual(self.messages(report, "values_traded_places"),
                         ["the places that held 91%, 78% now hold 78%, 91%", "the places that held 12.4%, 8.1% now hold 8.1%, 12.4%"])
        code, report = self.diff(before, before.replace("Sensitivity was 91% and specificity was 78%",
                                                        "Specificity was 78% and sensitivity was 91%"))
        self.assertEqual((code, report["findings"]), (0, []))


class CitationTests(Case):
    def test_a_dropped_author_year_citation_is_a_citation_not_a_year(self):
        code, report = self.diff(BASE, BASE.replace(" (Smith et al., 2020)", ""))
        self.assertEqual((code, self.codes(report)), (1, ["citation_dropped"]))
        self.assertEqual(self.messages(report, "citation_dropped"), ["smith 2020: cited 1× before, 0× after"])
        narrative = BASE.replace("Mean sleep latency fell by −4.2 minutes after 12 weeks (Smith et al., 2020).",
                                 "Smith et al. (2020) reported that mean sleep latency fell by −4.2 minutes after 12 weeks.")
        code, report = self.diff(BASE, narrative)
        self.assertEqual((code, report["findings"]), (0, []))

    def test_numeric_tex_and_pandoc_citations(self):
        code, report = self.diff(BASE, BASE.replace("[4, 5]", "[4]"))
        self.assertEqual(self.messages(report, "citation_dropped"), ["[5]: cited 1× before, 0× after"])
        code, report = self.diff(BASE, BASE.replace("[4, 5]", "[4–5]"))
        self.assertEqual((code, report["findings"]), (0, []))
        code, report = self.diff(TEX, TEX.replace("buysse1989,liu2022", "buysse1989"), suffix=".tex")
        self.assertEqual(self.messages(report, "citation_dropped"), ["liu2022: cited 1× before, 0× after"])
        before = "Agreement was high in an earlier cohort [@park2019, p. 4; @lee2021].\n"
        code, report = self.diff(before, before.replace("p. 4", "p. 9"))
        self.assertEqual(self.codes(report), ["citation_dropped", "citation_added"])

    def test_a_citation_moved_to_another_sentence(self):
        code, report = self.diff(BASE, BASE.replace("P < 0.001) [3]. These", "P < 0.001). These")
                                 .replace("poor sleep [4, 5]", "poor sleep [3, 4, 5]"))
        self.assertEqual((code, self.messages(report, "citation_moved")), (1, ["[3] left this sentence for another"]))


class KeyAndTermTests(Case):
    def test_reference_keys_labels_and_formulas(self):
        cases = {"fig:adherence}": ("fig:sleep}", "key_changed"), "{sec:results}": ("{sec:res}", "key_changed"),
                 r"\alpha = 0.05": (r"\alpha = 0.01", "formula_changed")}
        for old, (new, code) in cases.items():
            status, report = self.diff(TEX, TEX.replace(old, new), suffix=".tex")
            self.assertEqual((status, self.codes(report)), (1, [code]), old)
        status, report = self.diff(TEX, TEX.replace(r"\ref{fig:adherence}", r"\cref{fig:adherence}"), suffix=".tex")
        self.assertEqual((status, report["findings"]), (0, []))

    def test_the_order_of_keys_counts_below_the_heavy_level(self):
        moved = TEX.replace(r"Adherence was high (Figure~\ref{fig:adherence}) and fell in winter (Table~\ref{tab:season}).",
                            r"In winter (Table~\ref{tab:season}) adherence fell; it was high (Figure~\ref{fig:adherence}).")
        status, report = self.diff(TEX, moved, suffix=".tex")
        self.assertIn("order_changed", self.codes(report))
        status, report = self.diff(TEX, moved, "--level", "heavy", suffix=".tex")
        self.assertIn("order_changed", self.codes(report, "warning"))

    def test_protected_terms(self):
        terms = self.write("protect.txt", "# terms\nPSQI\nday-shift\n")
        code, report = self.diff(BASE, BASE.replace("PSQI 9.1", "index 9.1"), "--protect", terms)
        self.assertEqual(self.messages(report, "protected_term_changed"), ["PSQI: 1× before, 0× after"])
        code, report = self.diff(BASE, BASE)
        self.assertTrue(report["checks"]["terms"].startswith("not_checked"))

    def test_a_new_capitalised_term_is_a_warning(self):
        code, report = self.diff(BASE, BASE.replace("with poor sleep [4, 5]", "with poor sleep on the Pittsburgh index [4, 5]"))
        self.assertEqual((code, self.messages(report, "new_term")), (0, ["Pittsburgh is not in the original"]))


class ClaimTests(Case):
    def test_moves_up_and_down_the_ladder(self):
        code, report = self.diff(BASE, BASE.replace("is associated with poor sleep", "causes poor sleep"))
        self.assertEqual(code, 1)
        self.assertEqual(self.messages(report, "claim_strength"),
                         ["moved up the ladder: rung 3 (associated) associated → nothing; rung 5 (cause) nothing → causes"])
        code, report = self.diff(BASE, BASE.replace("results\nmay suggest", "results suggest"))
        self.assertEqual(self.messages(report, "claim_strength"), ["moved up the ladder: rung 1 (may) may → nothing"])
        code, report = self.diff(BASE, BASE.replace("group showed slightly", "group suggested slightly"))
        self.assertEqual(self.messages(report, "claim_strength"),
                         ["moved down the ladder: rung 2 (suggest) nothing → suggested; rung 4 (show) showed → nothing"])

    def test_a_word_on_the_same_rung_is_clean(self):
        after = BASE.replace("may suggest", "might indicate").replace("is associated with poor", "is linked to poor")
        code, report = self.diff(BASE, after.replace("results\nmay suggest", "results might indicate"))
        self.assertEqual((code, report["findings"]), (0, []))

    def test_other_words_that_change_a_claim(self):
        cases = {
            ("Adherence did not differ between groups.", "Adherence differed between groups."): "negation_changed",
            ("Some nurses slept poorly.", "Most nurses slept poorly."): "quantifier_changed",
            ("Only 120 nurses were included.", "In all, 120 nurses were included."): "scope_changed",
            ("Scores were significantly higher.", "Scores were markedly higher."): "significance_changed",
            ("Night work is a cause of poor sleep.", "Night work is the cause of poor sleep."): "article_changed",
            ("Night work was associated with poor sleep.", "Night work is associated with poor sleep."): "past_to_present",
            ("Mortality was lower in the monitored group.", "Mortality was higher in the monitored group."): "direction_changed",
            ("The effect may not persist.", "The effect cannot persist."): "modal_changed",
            ("The sample was small. However, it was diverse.", "The sample was small. Moreover, it was diverse."): "contrast_changed",
            ("Sleep was poor. Mood was low.", "Sleep was poor. Mood was therefore low."): "consequence_changed",
            ("About 17% of nurses stopped.", "Of the nurses, 17% stopped."): "approximation_changed",
        }
        for (before, after), code in cases.items():
            status, report = self.diff(before + "\n", after + "\n")
            self.assertEqual(status, 1, before)
            self.assertIn(code, self.codes(report), before)
        status, report = self.diff("Table 2 showed the scores.\n", "Table 2 shows the scores.\n")
        self.assertEqual((status, report["findings"]), (0, []))

    def test_a_rewritten_sentence_is_compared_not_skipped(self):
        after = BASE.replace("These results\nmay suggest that night work is associated with poor sleep [4, 5].",
                             "Shift work at night is linked to worse rest, as the findings imply [4, 5].")
        code, report = self.diff(BASE, after)
        self.assertEqual(report["not_compared"], {"before": [], "after": []})
        self.assertEqual(self.messages(report, "claim_strength"), ["moved up the ladder: rung 1 (may) may → nothing"])


class LevelTests(Case):
    def test_light_keeps_sentences_and_paragraphs(self):
        after = BASE.replace(", but the difference was not significant", ". But the difference was not significant")
        code, report = self.diff(BASE, after, "--level", "light")
        self.assertEqual((code, self.codes(report)), (1, ["split_or_merged"]))
        replaced = BASE.replace("However, only 120 nurses were included.", "Recruitment ended early.")
        code, report = self.diff(BASE, replaced, "--level", "light")
        self.assertEqual(self.codes(report).count("not_compared"), 2)
        code, report = self.diff(BASE, replaced)
        self.assertNotIn("not_compared", self.codes(report))
        self.assertEqual(report["not_compared"], {"before": ["However, only 120 nurses were included."],
                                                  "after": ["Recruitment ended early."]})
        self.assertIn("number_disappeared", self.codes(report))
        joined = BASE.replace("(P = 0.21).\n\nMean", "(P = 0.21). Mean")
        self.assertIn("paragraph_count", self.codes(self.diff(BASE, joined, "--level", "light")[1]))
        self.assertIn("paragraph_count", self.codes(self.diff(BASE, joined)[1], "warning"))

    def test_only_heavy_reorders_and_only_inside_a_paragraph(self):
        swapped = BASE.replace("Night work was associated with insomnia\nin 38% of nurses. However, only 120 nurses were included.",
                               "However, only 120 nurses were included. Night work was associated with insomnia in 38% of nurses.")
        code, report = self.diff(BASE, swapped)
        self.assertEqual((code, self.codes(report)), (1, ["sentence_moved"]))
        code, report = self.diff(BASE, swapped, "--level", "heavy")
        self.assertEqual((code, report["findings"], report["counts"]["moved"]), (0, [], 1))
        across = BASE.replace(" However, only 120 nurses were included.", "").replace(
            "(P = 0.21).\n", "(P = 0.21). However, only 120 nurses were included.\n")
        code, report = self.diff(BASE, across, "--level", "heavy")
        self.assertEqual(self.messages(report, "sentence_moved"), ["the sentence moved to another paragraph"])

    def test_the_share_of_changed_words_is_judged_against_the_level(self):
        after = BASE.replace("Nurses who worked night shifts slept worse", "Night-shift nurses slept worse")
        code, report = self.diff(BASE, after, "--max-footprint", "0.05")
        self.assertEqual((code, self.codes(report, "warning")), (0, ["large_footprint"]))
        self.assertEqual(report["footprint_limit"], 0.05)


class InputTests(Case):
    def test_docx_and_bad_input(self):
        w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        body = ('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Results</w:t></w:r></w:p>'
                "<w:p><w:r><w:t>Response was seen in 12 of 40 adults </w:t></w:r><w:del><w:r><w:delText>(99%)"
                "</w:delText></w:r></w:del><w:r><w:t>[3].</w:t></w:r></w:p>")
        path = self.dir / "paper.docx"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
        code, _ = self.run_cli("diff", str(path), self.write("p.md", "# Results\n\nResponse was seen in 12 of 41 adults [3].\n"))
        report = json.loads((self.out / "polish-check.json").read_text(encoding="utf-8"))
        self.assertEqual((code, self.messages(report, "number_changed")), (1, ["40 → 41"]))
        broken = self.dir / "broken.docx"
        broken.write_bytes(b"not a zip file")
        for argv in (["diff", str(self.dir / "missing.md"), self.write("x.md", "Text.\n")], ["diff", self.write("a.pdf", "x"),
                     self.write("y.md", "Text.\n")], ["diff", self.write("empty.md", "\n\n"), self.write("z.md", "Text.\n")],
                     ["diff", str(broken), self.write("w.md", "Text.\n")], ["diff", "a.md", "b.md", "--level", "deep"]):
            with self.assertRaises(SystemExit) as raised:
                self.run_cli(*argv)
            self.assertEqual(raised.exception.code, 2, argv)


class SurveyTests(Case):
    def test_candidates_claim_words_and_query_leads(self):
        text = BASE + "\nIL-6 and the Pittsburgh index were measured; the Pittsburgh index is widely used. Scores were " \
                      "significantly higher in women.\n"
        code, summary = self.run_cli("survey", self.write("paper.md", text), "--protect", self.write("t.txt", "PSQI\n"))
        report = json.loads((self.out / "survey.json").read_text(encoding="utf-8"))
        kinds = {c["term"]: c["kind"] for c in report["candidates"]}
        self.assertEqual((kinds["PSQI"], kinds["IL-6"], kinds["Pittsburgh"]),
                         ("abbreviation", "symbol or name with digits or capitals", "capitalised word, used twice or more"))
        self.assertNotIn("P", kinds)
        self.assertEqual(report["protected_terms"], [{"term": "PSQI", "count": 1}])
        self.assertEqual(report["claims"][0]["rungs"], ["rung 1 (may): may", "rung 2 (suggest): suggest",
                                                        "rung 3 (associated): associated"])
        self.assertEqual([q["where"] for q in report["queries"]], ["¶2.3", "¶4.2"])
        self.assertEqual((code, summary["query_leads"]), (0, 2))


class LogTests(Case):
    ENTRIES = [{"id": "c1", "location": "¶1.1", "before": "sleep quality of nurses who works night shifts were worse",
                "after": "the sleep quality of nurses who work night shifts was worse", "reason": "article, agreement"},
               {"id": "c2", "location": "¶1.2", "before": "This results", "after": "These results", "reason": "agreement"}]

    def log(self, entries, before=LIGHT_BEFORE, after=LIGHT_AFTER, *flags, suffix=".md"):
        changes = self.write("changes.json", json.dumps({"changes": entries}))
        return self.run_cli("log", self.write("o" + suffix, before), self.write("p" + suffix, after), changes, *flags)

    def test_a_complete_log_passes_and_writes_a_redline(self):
        code, summary = self.log(self.ENTRIES, LIGHT_BEFORE, LIGHT_AFTER, "--level", "light")
        self.assertEqual((code, summary["entries_with_problems"], summary["changes_without_entry"]), (0, 0, 0))
        self.assertEqual(summary["latexdiff"], "not applicable: the files are not LaTeX")
        redline = (self.out / "redline.md").read_text(encoding="utf-8")
        self.assertIn("study, **the** sleep quality of nurses who ~~works~~ **work** night shifts ~~were~~ **was** worse", redline)
        self.assertIn("~~This~~ **These** results", redline)

    def test_entries_must_match_the_texts_and_use_the_reasons(self):
        code, summary = self.log(self.ENTRIES[:1])
        self.assertEqual((code, summary["changes_without_entry"]), (1, 1))
        wrong = [dict(self.ENTRIES[0], before="sleep quality of nurse who works night shifts were worse"),
                 dict(self.ENTRIES[1], reason="style")]
        code, _ = self.log(wrong)
        problems = [e["problems"] for e in json.loads((self.out / "log-check.json").read_text())["entries"]]
        self.assertTrue(problems[0][0].startswith("before text is not in"), problems)
        self.assertIn('(closest: "In this study, sleep quality', problems[0][0])
        self.assertEqual(problems[1], ['"style" is not on the list of reasons'])
        code, _ = self.log([dict(self.ENTRIES[0], reason="clarity"), self.ENTRIES[1]], LIGHT_BEFORE, LIGHT_AFTER, "--level", "light")
        problems = [e["problems"] for e in json.loads((self.out / "log-check.json").read_text())["entries"]]
        self.assertEqual((code, problems[0]), (1, ['"clarity" is not allowed at the light level']))

    def test_a_moved_sentence_needs_a_reorder_entry(self):
        swapped = BASE.replace("Night work was associated with insomnia\nin 38% of nurses. However, only 120 nurses were included.",
                               "However, only 120 nurses were included. Night work was associated with insomnia in 38% of nurses.")
        entry = {"id": "r1", "before": "However, only 120 nurses were included.", "after": "However, only 120 nurses were included."}
        code, summary = self.log([dict(entry, reason="clarity")], BASE, swapped, "--level", "heavy")
        self.assertEqual((code, summary["changes_without_entry"]), (1, 1))
        code, summary = self.log([dict(entry, reason="reorder")], BASE, swapped, "--level", "heavy")
        self.assertEqual((code, summary["entries_with_problems"], summary["changes_without_entry"]), (0, 0, 0))
        code, _ = self.log([dict(entry, reason="reorder")], BASE, swapped, "--level", "medium")
        self.assertEqual(code, 1)

    def test_latexdiff_is_used_only_when_installed(self):
        after = TEX.replace("Adherence was high", "Adherence was very high")
        entry = [{"id": "c1", "before": "Adherence was high", "after": "Adherence was very high", "reason": "word choice"}]
        with mock.patch.object(pc.shutil, "which", return_value=None):
            code, summary = self.log(entry, TEX, after, suffix=".tex")
        self.assertEqual(summary["latexdiff"], "not installed: no latexdiff redline was produced")
        self.assertIn("latexdiff: not installed: no latexdiff redline was produced",
                      (self.out / "log-check.md").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("latexdiff"), "latexdiff is not installed")
    def test_latexdiff_writes_a_tex_redline(self):
        after = TEX.replace("Adherence was high", "Adherence was very high")
        entry = [{"id": "c1", "before": "Adherence was high", "after": "Adherence was very high", "reason": "word choice"}]
        code, summary = self.log(entry, TEX, after, suffix=".tex")
        self.assertEqual(summary["latexdiff"], "written: redline-latexdiff.tex")
        self.assertIn("\\DIFadd", (self.out / "redline-latexdiff.tex").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
