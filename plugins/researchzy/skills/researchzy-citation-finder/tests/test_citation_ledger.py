"""citation_ledger.py: targets are found, and a citation is accepted only on a quote from a paper that was read."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "citation_ledger.py"
spec = importlib.util.spec_from_file_location("citation_ledger", SCRIPT)
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)

MARKDOWN = """---
title: "Night shifts and recall"
---

# Introduction

Shift work is common among nurses. Night shifts reduce recall by 12% in nurses [Citation needed: recall after night shifts].
Previous studies have linked sleep loss to poorer attention (Okoro et al., 2019).
It is well known that sleep consolidates memory.
About 30% of nurses work rotating shifts.
Okoro et al. (2019) found 41% of nurses slept badly. Lee [12] reported p < 0.05 in a cohort of n = 80.
The hazard ratio was 1.4 [@smith2020]. Effects were larger in older staff [CITATION NEEDED].
We used the Pittsburgh index [citation needed: original PSQI paper]. Fig. 2 shows the design.
Error rates rose threefold after sleep restriction [?]. Cortisol rises after waking [@NEW:cortisol].
Daytime naps have been reported to help.

```python
x = 0.05  # 50% of runs [Citation needed: in code]
```

| Group | 35% [Citation needed: in a table] |
|---|---|

<!-- Many studies have shown 90% [Citation needed: in a comment] -->

## Results

In our sample, 41% of nurses reported poor sleep, and the odds ratio was 2.1 $p < 0.01$.

# References

Okoro, D. 2019. Studies have shown 99% of everything.
"""

LATEX = r"""\documentclass{article}
% 50% of comments say [Citation needed: in a comment]
\begin{document}
\section{Introduction}
Shift work is common among nurses \citep{lee2018}.
Night shifts reduce recall by 12\% in nurses [Citation needed: recall after night shifts].
It is well known that sleep consolidates memory.
We used the Pittsburgh index~\cite{?} to measure sleep.
The model fits with p-values below .05 throughout \citep[p.~3]{okoro2019}.
\begin{equation}
  r = 0.8 \text{[Citation needed: in math]}
\end{equation}
\begin{verbatim}
p < 0.001 [Citation needed: in verbatim]
\end{verbatim}
\begin{tabular}{ll} n = 20 & 35\% \\ \end{tabular}
\subsection{Results}
In our sample, 41\% of nurses reported poor sleep.
\end{document}
"""

FILLER = " ".join(f"Paragraph {i} describes the ward schedule and the consent procedure." for i in range(60))
FULL_TEXT = ("[[page 1]]\nNight shift work and recall. " + FILLER + "\n[[page 2]]\nResults. After three night "
             "shifts, recall accu-\nracy fell by 12% relative to “day” shifts (95% CI 7–17).\n")
OKORO = {"corpusId": 101, "title": "Night shift work and <i>episodic</i> recall", "authors": ["Dana Okoro", {"name": "Li Wei"}],
         "authorCount": 3, "year": 2019, "venue": "Journal of Shift Studies", "doi": "https://doi.org/10.5555/JSS.2019.12",
         "abstract": "After three night shifts, recall accuracy fell by 12% relative to day shifts.", "hasReadablePdf": True}
RUIZ = {"corpusId": 102, "title": "Naps & vigilance: 100% of the_evidence", "authors": ["Ana Ruiz"], "year": 2015,
        "venue": "Proceedings of the Workshop on Sleep", "doi": "10.5555/nap.2015.7",
        "abstract": "Night workers who took a nap before the shift were more vigilant on a reaction-time task."}
CHEN = {"corpusId": 103, "title": "Recall after night shifts", "authors": ["Wei Chen"], "year": 2024, "venue": "arXiv",
        "arxiv": "2401.01234v2", "abstract": "Recall was lower after night shifts."}


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_cwd = os.getcwd()
        os.chdir(self.root)            # the ledger's paths are relative, as when the agent runs it
        Path("paper.md").write_text(MARKDOWN, encoding="utf-8")
        Path("main.tex").write_text(LATEX, encoding="utf-8")
        Path("full.txt").write_text(FULL_TEXT, encoding="utf-8")
        self.save("r1.json", {"total": 57, "results": [OKORO, RUIZ]})
        self.save("r2.json", [CHEN])
        self.save("r3.json", {"papers": []})

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def save(self, name, data):
        Path(name).write_text(json.dumps(data), encoding="utf-8")

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cl.main(["--dir", "citations", *argv])
        return code, json.loads(out.getvalue())

    def ledger(self):
        return json.loads(Path("citations/ledger.json").read_text(encoding="utf-8"))

    def searched(self, target, n=1):
        for i in range(n):
            self.run_cli("search", target, "--query", f"night shift recall {i}", "--total", "57", "--saved", "r1.json")


class TargetTests(LedgerTestCase):
    def test_markdown_placeholders_markers_and_candidates(self):
        _, out = self.run_cli("targets", "paper.md")
        self.assertEqual([(t["id"], t["line"], t["note"]) for t in out["targets"]],
                         [("t1", 7, "recall after night shifts"), ("t2", 13, "original PSQI paper")])
        self.assertEqual(out["targets"][0]["sentence"],
                         "Night shifts reduce recall by 12% in nurses [Citation needed: recall after night shifts].")
        self.assertEqual(out["targets"][0]["section"], "Introduction")
        self.assertEqual([m["text"] for m in out["other_markers"]], ["[CITATION NEEDED]", "[?]", "[@NEW:cortisol]"])
        why = {c["sentence"][:24]: c["why"] for c in out["candidates"]}
        self.assertEqual(why, {
            "It is well known that sl": ["phrase: It is well known"],
            "About 30% of nurses work": ["statistic: 30%"],
            "Effects were larger in o": ["marker [CITATION NEEDED]"],
            "Error rates rose threefo": ["marker [?]", "statistic: threefold"],
            "Cortisol rises after wak": ["marker [@NEW:cortisol]"],
            "Daytime naps have been r": ["phrase: have been reported"],
            "In our sample, 41% of nu": ["statistic: 41%"]})
        # Cited sentences ("(Okoro et al., 2019)", "Okoro et al. (2019)", "[12]", "[@smith2020]") are not candidates;
        # code, tables, comments, inline math and the reference list are skipped.
        self.assertEqual([p["line"] for p in out["placeholders_in_skipped_blocks"]], [18, 21, 24])
        self.assertTrue(all(c["id"].startswith("c") for c in out["candidates"]))
        self.assertIn("| t1 | target | paper.md:7 | Introduction |", Path("citations/targets.md").read_text(encoding="utf-8"))

    def test_latex_citations_comments_verbatim_and_math(self):
        _, out = self.run_cli("targets", "main.tex")
        self.assertEqual([(t["id"], t["line"]) for t in out["targets"]], [("t1", 6)])
        self.assertEqual(out["other_markers"], [{"line": 8, "text": "\\cite{?}"}])
        self.assertEqual({c["line"]: c["why"] for c in out["candidates"]},
                         {7: ["phrase: It is well known"], 8: ["marker \\cite{?}"], 18: ["statistic: 41\\%"]})
        self.assertEqual([p["line"] for p in out["placeholders_in_skipped_blocks"]], [2, 11, 14])

    def test_ids_are_stable_and_a_removed_target_is_kept(self):
        self.run_cli("targets", "paper.md")
        self.run_cli("confirm", "c1")
        text = MARKDOWN.replace("Shift work is common among nurses. ", "New first sentence [Citation needed: new one].\n")
        Path("paper.md").write_text(text.replace("[citation needed: original PSQI paper]", "[@buysse1989]"), encoding="utf-8")
        _, out = self.run_cli("targets", "paper.md")
        self.assertEqual([(t["id"], t["line"]) for t in out["targets"]], [("t3", 7), ("t1", 8), ("c1", 10)])
        self.assertEqual(out["no_longer_in_the_manuscript"], ["t2"])

    def test_a_candidate_is_a_target_only_once_confirmed(self):
        self.run_cli("targets", "paper.md")
        with self.assertRaises(SystemExit):
            self.run_cli("need", "c1", "background")
        with self.assertRaises(SystemExit):
            self.run_cli("confirm", "c99")
        self.assertEqual(self.run_cli("confirm", "c1")[1], {"confirmed": ["c1"]})
        self.assertEqual(self.run_cli("need", "c1", "background")[1]["need"], "background")

    def test_a_sentence_the_user_points_at(self):
        _, out = self.run_cli("targets", "paper.md", "--line", "13")
        named = [c for c in out["candidates"] if "named with --line" in c["why"]]
        self.assertEqual([c["sentence"] for c in named], ["Fig. 2 shows the design."])

    def test_the_bib_entries_that_may_cover_a_target(self):
        Path("refs.bib").write_text("@article{buysse1989, title = {The {Pittsburgh} sleep quality index, original paper}}\n")
        _, out = self.run_cli("targets", "paper.md", "--bib", "refs.bib")
        self.assertEqual(out["targets"][1]["in_bib"][0]["key"], "buysse1989")
        self.assertNotIn("in_bib", out["targets"][0])


class RecordTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli("targets", "paper.md")

    def test_need_not_needed_takes_a_reason(self):
        with self.assertRaises(SystemExit):
            self.run_cli("need", "t1", "not_needed")
        self.run_cli("need", "t1", "not_needed", "--reason", "our own result")
        self.assertEqual(self.ledger()["targets"]["t1"]["verdict"], "not_needed")

    def test_searches_that_count_toward_not_found(self):
        with self.assertRaises(SystemExit):     # a completed search needs its total and the saved result
            self.run_cli("search", "t1", "--query", "night recall", "--total", "3")
        with self.assertRaises(SystemExit):
            self.run_cli("search", "t1", "--query", "night recall", "--total", "3", "--saved", "missing.json")
        self.run_cli("search", "t1", "--query", "night recall", "--total", "57", "--saved", "r1.json")
        _, out = self.run_cli("search", "t1", "--query", "Night  recall", "--total", "57", "--saved", "r1.json")
        self.assertEqual(out["keyword_searches_counted"], 1)                       # the same query twice counts once
        self.run_cli("search", "t1", "--query", "night recall", "--failed", "RATE_LIMITED: try later")
        self.run_cli("search", "t1", "--doi", "10.5555/x", "--total", "0", "--saved", "r3.json")
        self.run_cli("search", "t1", "--tool", "list_library_papers", "--query", "recall", "--total", "1", "--saved", "r2.json")
        _, out = self.run_cli("search", "t1", "--query", "night recall", "--sort", "year", "--total", "57", "--saved", "r1.json")
        self.assertEqual(out["keyword_searches_counted"], 2)
        with self.assertRaises(SystemExit):
            self.run_cli("verdict", "t1", "not_found")
        self.run_cli("search", "t1", "--query", "shift memory", "--total", "0", "--saved", "r3.json")
        self.assertEqual(self.run_cli("verdict", "t1", "not_found")[1]["problems"], [])
        search = self.ledger()["targets"]["t1"]["searches"][0]
        self.assertEqual((search["total"], search["looked_at"], search["saved"]), (57, 2, "r1.json"))

    def test_not_found_with_a_reason(self):
        self.run_cli("search", "t2", "--query", "PSQI", "--total", "0", "--saved", "r3.json")
        self.assertEqual(self.run_cli("verdict", "t2", "not_found", "--reason", "an instrument named by the user")[1]["problems"],
                         [])

    def test_a_candidate_comes_only_from_a_saved_tool_result(self):
        self.searched("t1")
        _, out = self.run_cli("candidate", "t1", "r1.json", "--doi", "10.5555/jss.2019.12")
        self.assertEqual((out["paper"], out["grade"], out["has_abstract"]), ("okoro2019night", "metadata", True))
        self.assertEqual(self.run_cli("candidate", "t1", "r2.json", "--arxiv", "arXiv:2401.01234")[1]["paper"], "chen2024recall")
        self.save("one.json", {"paper": RUIZ})
        self.assertEqual(self.run_cli("candidate", "t1", "one.json", "--corpus-id", "102")[1]["paper"], "ruiz2015naps")
        self.save("items.json", {"items": [OKORO]})
        self.run_cli("candidate", "t1", "items.json", "--corpus-id", "101")
        self.assertEqual(len(self.ledger()["targets"]["t1"]["candidates"]), 3)
        paper = self.ledger()["papers"]["101"]
        self.assertEqual((paper["authors"], paper["doi"], paper["authorCount"]), (["Dana Okoro", "Li Wei"], "10.5555/jss.2019.12", 3))
        self.assertEqual(self.ledger()["targets"]["t1"]["candidates"][0], {"paper": "101", "grade": "metadata", "search": "s1"})
        with self.assertRaises(SystemExit):
            self.run_cli("candidate", "t1", "r1.json", "--doi", "10.9999/invented")
        with self.assertRaises(SystemExit):
            self.run_cli("candidate", "t1", "paper.md", "--doi", "10.5555/jss.2019.12")

    def test_what_each_verdict_needs(self):
        self.searched("t1")
        self.run_cli("candidate", "t1", "r1.json", "--corpus-id", "101")
        base = ("--paper", "okoro2019night", "--grade", "full-text", "--source", "full.txt")
        quote = ("--quote", "recall accuracy fell by 12% relative to day shifts")
        for argv in (("t1", "supported", *base),                                  # no quote
                     ("t1", "supported", "--grade", "abstract", "--source", "r1.json", *quote),   # no paper
                     ("t1", "supported", *base, "--quote", "fell by 12%"),         # quote too short
                     ("t1", "supported", *base[:4], "--source", "nowhere.txt", *quote),
                     ("t1", "supported", *base[:4], "--source", "r1.json", *quote),   # full-text from a saved record
                     ("t1", "partial", *base, *quote),                            # partial without wording
                     ("t1", "contradicts", *base),                                # a contradiction needs its quote too
                     ("t1", "supported", "--paper", "ruiz2015naps", *base[2:], *quote),   # not a candidate of t1
                     ("t1", "not_checked"), ("t1", "not_needed"), ("t1", "not_found")):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                self.run_cli("verdict", *argv)
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):   # metadata is not a grade for a verdict
            self.run_cli("verdict", "t1", "supported", "--paper", "okoro2019night", "--grade", "metadata",
                         "--source", "r1.json", *quote)
        _, out = self.run_cli("verdict", "t1", "supported", *base, *quote, "--locator", "Results")
        self.assertEqual(out, {"target": "t1", "verdict": "supported", "paper": "okoro2019night", "problems": []})
        self.assertEqual(self.ledger()["targets"]["t1"]["candidates"][0]["grade"], "full-text")
        self.assertEqual(self.run_cli("verdict", "t1", "not_checked", "--reason", "no full text")[1]["problems"], [])


class QuoteTests(unittest.TestCase):
    def test_normalised_comparison(self):
        source = "The ﬁrst “night” shift—and the second—cut recall: accu-\n racy fell   by 12%."
        for quote in ('the first "night" shift-and the second-cut recall', "recall: accuracy fell by 12%",
                      "THE FIRST ‘NIGHT’ SHIFT", "accu­racy fell by 12%"):
            with self.subTest(quote=quote):
                self.assertTrue(cl.find_quote(quote, source)[0])
        self.assertFalse(cl.find_quote("recall accuracy rose by 12%", source)[0])
        self.assertFalse(cl.find_quote("", source)[0])

    def test_the_page_of_a_quote(self):
        self.assertEqual(cl.find_quote("relative to day shifts", FULL_TEXT), (True, 2))
        self.assertEqual(cl.find_quote("ward schedule", "no pages here: the ward schedule"), (True, None))

    def test_the_numbers_a_sentence_carries(self):
        self.assertEqual(cl.numbers("In 2019, 1,200 nurses (Table 2, Fig. 3) lost 12.5% in phase 2"), {1200.0, 12.5})
        self.assertEqual(cl.numbers("In 2019 they lost 12.5%", everything=True), {2019.0, 12.5})


class CheckTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli("targets", "paper.md")
        self.searched("t1")
        self.searched("t2")
        self.run_cli("candidate", "t1", "r1.json", "--corpus-id", "101")
        self.run_cli("candidate", "t2", "r1.json", "--corpus-id", "102")

    def verdict(self, target, verdict, *argv):
        return self.run_cli("verdict", target, verdict, *argv)[1]["problems"]

    def check(self):
        return self.run_cli("check")

    def test_every_target_needs_a_verdict_and_nothing_is_silent(self):
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(out["problems"], [{"target": "t1", "problem": "no verdict"}, {"target": "t2", "problem": "no verdict"}])
        self.assertEqual(len(out["candidates_not_confirmed"]), 7)

    def test_a_strong_sentence_needs_the_full_text_or_its_number_in_the_quote(self):
        abstract = ("--paper", "101", "--grade", "abstract", "--source", "r1.json")
        problems = self.verdict("t1", "supported", *abstract, "--quote", "After three night shifts, recall accuracy fell")
        self.assertEqual(problems, ['the sentence carries the number 12, "reduce": it needs grade full-text, '
                                    "or every number inside the quote"])
        self.assertEqual(self.verdict("t1", "supported", *abstract, "--quote", "recall accuracy fell by 12% relative"), [])
        self.assertEqual(self.verdict("t1", "supported", "--paper", "101", "--grade", "full-text", "--source", "full.txt",
                                      "--quote", "After three night shifts, recall accuracy fell"), [])

    def test_partial_is_judged_on_its_narrower_wording(self):
        abstract = ("--paper", "ruiz2015naps", "--grade", "abstract", "--source", "r1.json",
                    "--quote", "were more vigilant on a reaction-time task")
        self.assertEqual(self.verdict("t2", "partial", *abstract, "--wording", "One study found napping workers more vigilant."), [])
        self.assertEqual(self.verdict("t2", "partial", *abstract, "--wording", "Naps improve vigilance by 20%."),
                         ['the suggested wording carries the number 20, "improve": it needs grade full-text, '
                          "or every number inside the quote"])

    def test_the_quote_must_be_in_the_named_text(self):
        problems = self.verdict("t1", "supported", "--paper", "101", "--grade", "full-text", "--source", "full.txt",
                                "--quote", "recall accuracy fell by 20% relative to day shifts")
        self.assertEqual(problems, ["the quote is not in full.txt"])
        problems = self.verdict("t2", "supported", "--paper", "102", "--grade", "abstract", "--source", "r2.json",
                                "--quote", "were more vigilant on a reaction-time task")
        self.assertEqual(problems, ["r2.json holds no abstract of this paper"])

    def test_a_short_text_is_not_a_full_text(self):
        Path("short.txt").write_text("After three night shifts, recall accuracy fell by 12% relative to day shifts.")
        problems = self.verdict("t1", "supported", "--paper", "101", "--grade", "full-text", "--source", "short.txt",
                                "--quote", "recall accuracy fell by 12% relative to day shifts")
        self.assertEqual(problems, ["short.txt has 13 words: too short to be a full text, so the grade is abstract"])

    def test_metadata_is_never_support(self):
        self.verdict("t1", "supported", "--paper", "101", "--grade", "full-text", "--source", "full.txt",
                     "--quote", "recall accuracy fell by 12% relative to day shifts")
        ledger = self.ledger()
        ledger["targets"]["t1"]["grade"] = "metadata"           # a hand edit of the ledger
        Path("citations/ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        self.run_cli("bib")
        problems = [p["problem"] for p in self.check()[1]["problems"] if p["target"] == "t1"]
        self.assertIn("grade metadata: a paper known only by its metadata is never support", problems)

    def test_a_complete_record_passes_and_the_map_says_what_was_done(self):
        self.verdict("t1", "supported", "--paper", "101", "--grade", "full-text", "--source", "full.txt",
                     "--quote", "recall accuracy fell by 12% relative to “day” shifts", "--locator", "Results")
        self.verdict("t2", "not_found", "--reason", "only one search: the user withdrew the sentence")
        code, out = self.check()
        self.assertEqual((code, out["problems"]), (1, [{"target": "t1", "problem": "the citation key is not final: run bib"}]))
        self.run_cli("bib")
        Path("citations/new-references.bib").unlink()
        self.assertEqual(self.check()[1]["problems"], [{"target": None, "problem": "new-references.bib is missing: run bib"}])
        self.run_cli("bib")
        code, out = self.check()
        self.assertEqual((code, out["ok"], out["verdicts"]), (0, True, {"supported": 1, "not found": 1}))
        page = Path("citations/citation-map.md").read_text(encoding="utf-8")
        self.assertIn("| t1 | paper.md:7 | supported | `okoro2019night` | full-text | none |", page)
        self.assertIn('- Quote: "recall accuracy fell by 12% relative to “day” shifts" (p. 2, Results, `full.txt`)', page)
        self.assertIn("Not found in the index with the searches below. That is not a statement that no such paper exists.", page)
        self.assertIn("- Search s2 (search_papers): `night shift recall 0`, 57 reported, 2 looked at", page)
        self.assertIn("retraction status", page)


class BibTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli("targets", "paper.md")
        self.run_cli("confirm", "c1", "c2")
        for target, record, quote in (("t1", "101", "After three night shifts, recall accuracy fell by 12%"),
                                      ("t2", "102", "Night workers who took a nap before the shift"),
                                      ("c1", "103", "Recall was lower after night shifts")):
            self.searched(target)
            self.run_cli("candidate", target, "r2.json" if record == "103" else "r1.json", "--corpus-id", record)
            self.run_cli("verdict", target, "supported", "--paper", record, "--grade", "abstract",
                         "--source", "r2.json" if record == "103" else "r1.json", "--quote", quote)

    def test_entries_from_returned_fields_only(self):
        _, out = self.run_cli("bib")
        self.assertEqual(out["new_entries"], ["okoro2019night", "ruiz2015naps", "chen2024recall"])
        bib = Path("citations/new-references.bib").read_text(encoding="utf-8")
        self.assertIn("@article{okoro2019night,\n  author = {Dana Okoro and Li Wei and others},\n"
                      "  title = {{Night shift work and episodic recall}},\n  year = {2019},\n"
                      "  journal = {Journal of Shift Studies},\n  doi = {10.5555/jss.2019.12}\n}", bib)
        self.assertIn("@inproceedings{ruiz2015naps,", bib)
        self.assertIn("title = {{Naps \\& vigilance: 100\\% of the\\_evidence}}", bib)
        self.assertIn("booktitle = {Proceedings of the Workshop on Sleep}", bib)
        self.assertIn("@misc{chen2024recall,\n  author = {Wei Chen},\n  title = {{Recall after night shifts}},\n"
                      "  year = {2024},\n  eprint = {2401.01234},\n  archivePrefix = {arXiv}\n}", bib)
        for field in ("volume", "number", "pages", "abstract"):
            self.assertNotIn(field + " =", bib)

    def test_a_paper_in_the_users_bib_keeps_its_key(self):
        theirs = ("@Article{Okoro19,\n  title = {Night Shift Work and {Episodic} Recall},\n  doi = {10.1000/other}\n}\n"
                  "@inproceedings{nap,\n  title = \"Something else\",\n  doi = \"10.5555/NAP.2015.7\"\n}\n"
                  "@article{chen2024recall, title = {A different paper by Chen}}\n")
        Path("refs.bib").write_text(theirs, encoding="utf-8")
        _, out = self.run_cli("bib", "--bib", "refs.bib")
        self.assertEqual([(r["key"], r["matched_by"]) for r in out["reused_keys"]],
                         [("Okoro19", "the same title"), ("nap", "the same DOI")])
        self.assertEqual(out["new_entries"], ["chen2024recalla"])   # the key is taken in the user's file
        self.assertEqual(Path("refs.bib").read_text(encoding="utf-8"), theirs)
        bib = Path("citations/new-references.bib").read_text(encoding="utf-8")
        self.assertNotIn("{Okoro19,", bib)
        self.assertIn("@misc{chen2024recalla,", bib)

    def test_keys(self):
        self.assertEqual(cl.make_key({"authors": ["Łukasz Kaiser-Żak Jr."], "year": 2017, "title": "The Æther of 3D attention"},
                                     set()), "kaiserzak2017aether")
        self.assertEqual(cl.make_key({"authors": ["Born, Jan"], "year": 2010, "title": "On the memory function"}, {"born2010memory"}),
                         "born2010memorya")
        self.assertEqual(cl.make_key({"title": "<i>An</i> 3D map"}, set()), "anonmap")


class ApplyTests(LedgerTestCase):
    def finish(self, manuscript):
        self.run_cli("targets", manuscript)
        self.searched("t1")
        self.run_cli("candidate", "t1", "r1.json", "--corpus-id", "101")
        self.run_cli("verdict", "t1", "supported", "--paper", "101", "--grade", "full-text", "--source", "full.txt",
                     "--quote", "recall accuracy fell by 12% relative to day shifts")
        self.run_cli("bib")

    def test_markdown_copy(self):
        self.finish("paper.md")
        _, out = self.run_cli("apply", "paper.md")
        copy = Path(out["copy"]).read_text(encoding="utf-8")
        self.assertIn("reduce recall by 12% in nurses [@okoro2019night].", copy)
        self.assertIn("[citation needed: original PSQI paper]", copy)
        self.assertEqual(out["placeholders_left"], [{"target": "t2", "line": 13, "why": "verdict not set"}])
        self.assertEqual(Path("paper.md").read_text(encoding="utf-8"), MARKDOWN)
        self.assertEqual(out["copy"], str(Path("citations") / "paper.cited.md"))

    def test_latex_copy_uses_the_manuscripts_command(self):
        self.finish("main.tex")
        _, out = self.run_cli("apply", "main.tex")
        self.assertIn("by 12\\% in nurses \\citep{okoro2019night}.", Path(out["copy"]).read_text(encoding="utf-8"))
        self.assertEqual(Path("main.tex").read_text(encoding="utf-8"), LATEX)


def tiny_pdf(lines) -> bytes:
    """A one-page PDF with Helvetica text, built by hand."""
    content = "BT /F1 11 Tf 72 720 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               f"<< /Length {len(content)} >>\nstream\n{content}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    return out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


class TextTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        Path("paper.pdf").write_bytes(tiny_pdf(["Results. Recall accuracy fell by 12 percent", "after three night shifts."]))
        self.have_mupdf = any(importlib.util.find_spec(name) for name in ("pymupdf", "fitz"))

    def test_with_pymupdf(self):
        if not self.have_mupdf:
            self.skipTest("PyMuPDF is not installed")
        _, out = self.run_cli("text", "paper.pdf", "--name", "ruiz")
        self.assertEqual((out["extractor"], out["pages"], out["long_enough_for_a_full_text"]), ("PyMuPDF", 1, False))
        text = Path("citations/texts/ruiz.txt").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("[[page 1]]\n"))
        self.assertTrue(cl.find_quote("recall accuracy fell by 12 percent after three", text)[0])

    def test_with_pdftotext(self):
        if not shutil.which("pdftotext"):
            self.skipTest("pdftotext is not installed")
        with mock.patch.object(cl.importlib.util, "find_spec", return_value=None):
            _, out = self.run_cli("text", "paper.pdf")
        self.assertEqual((out["extractor"], out["text"]), ("pdftotext", str(Path("citations/texts/paper.txt"))))
        self.assertTrue(cl.find_quote("recall accuracy fell by 12 percent", Path(out["text"]).read_text(encoding="utf-8"))[0])

    def test_without_either(self):
        with mock.patch.object(cl.importlib.util, "find_spec", return_value=None), \
                mock.patch.object(cl.shutil, "which", return_value=None):
            code, out = self.run_cli("text", "paper.pdf")
        self.assertEqual((code, out["text"]), (0, None))
        self.assertIn("Neither PyMuPDF nor the pdftotext binary is available", out["message"])
        self.assertFalse(Path("citations/texts").exists())

    def test_not_a_pdf(self):
        with self.assertRaises(SystemExit):
            self.run_cli("text", "paper.md")


if __name__ == "__main__":
    unittest.main()
