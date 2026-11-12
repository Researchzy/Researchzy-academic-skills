"""review_ledger.py: the counts add up and only included, read papers can be cited."""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "review_ledger.py"
spec = importlib.util.spec_from_file_location("review_ledger", SCRIPT)
rl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rl)

PAPERS = [
    {"corpusId": 1, "title": "The Role of Sleep in Memory Consolidation", "authors": ["Björn Rasch", "Jan Born"],
     "authorCount": 2, "year": 2013, "venue": "Physiological Reviews", "doi": "10.1152/physrev.00032.2012",
     "citationCount": 2500, "abstract": "Over more than a century…", "hasReadablePdf": True,
     "readerUrl": "https://app.researchzy.com/read/c/1"},
    {"corpusId": 2, "title": "Sleep deprivation & hippocampal function", "authors": [{"name": "Seung-Schik Yoo"}],
     "authorCount": 5, "year": 2007, "venue": "Nature Neuroscience", "arxiv": "0701.00001"},
    {"corpusId": 3, "title": "A study of sleep in mice", "authors": ["A. Researcher"], "year": 2013},
]


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "literature-review"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        old, out = sys.argv, io.StringIO()
        sys.argv = ["review_ledger.py", "--dir", str(self.dir), *argv]
        try:
            with redirect_stdout(out):
                code = rl.main()
        finally:
            sys.argv = old
        return code, json.loads(out.getvalue())

    def add(self, papers, *flags):
        path = Path(self.tmp.name) / "papers.json"
        path.write_text(json.dumps(papers), encoding="utf-8")
        return self.run_cli("add", str(path), *flags)[1]

    def test_a_review_from_brief_to_checked_draft(self):
        self.run_cli("brief", "--topic", "Sleep and memory", "--question", "Does sleep loss impair encoding?",
                     "--question", "Which sleep stage matters?", "--criteria", "human studies")
        _, s1 = self.run_cli("search", "--query", '"sleep deprivation" memory', "--total", "412", "--fetched", "20",
                             "--pass", "relevance", "--question", "1", "--filter", "yearFrom=2000")
        self.assertEqual(s1, {"search": "s1"})
        self.assertEqual(self.add(PAPERS, "--search", "s1"), {"new": 3, "already_in_ledger": 0, "papers": 3})
        self.run_cli("search", "--query", "sleep memory consolidation", "--total", "9000", "--sort", "citationCount",
                     "--pass", "foundational")
        # The same paper from a second search is one paper, found twice.
        self.assertEqual(self.add({"results": PAPERS[:1]}, "--search", "s2"),
                         {"new": 0, "already_in_ledger": 1, "papers": 3})
        self.assertEqual(self.add([{"corpusId": 9, "title": "A seed nobody found", "authors": ["Q. Seed"], "year": 2001}],
                                  "--seed")["new"], 1)

        self.run_cli("decide", "1", "yoo2007sleep", "--include", "--core")
        self.run_cli("decide", "3", "--exclude", "--reason", "animal study")
        self.assertEqual(self.run_cli("decide", "9", "--include")[1]["decision"], "included")
        self.run_cli("read", "1", "--depth", "full_text", "--source", "sources/1.pdf")
        self.run_cli("read", "2", "--depth", "abstract")
        self.run_cli("extract", "1", "method=review", "result=sleep after learning stabilises memory", "locator=p. 690")
        extraction = Path(self.tmp.name) / "extraction.json"
        extraction.write_text(json.dumps({"yoo2007sleep": {"method": "fMRI, n = 28", "theme": "encoding"}}))
        self.run_cli("extract", str(extraction))

        _, status = self.run_cli("status")
        self.assertEqual((status["searches"], status["results_reported"], status["results_looked_at"]), (2, 9412, 21))
        self.assertEqual((status["papers"], status["included"], status["core"], status["excluded"], status["undecided"]),
                         (4, 3, 2, 1, 0))
        self.assertEqual(status["excluded_by_reason"], {"animal study": 1})
        self.assertEqual(status["included_read"], {"none": 1, "metadata": 0, "abstract": 1, "full_text": 1})
        self.assertEqual(status["seeds_not_found_by_any_search"], ["seed2001seed"])
        self.assertEqual(status["included_without_extraction"], ["seed2001seed"])
        self.assertEqual(status["core_not_read_in_full"], ["yoo2007sleep"])
        self.assertEqual(status["passes_not_run"], ["recent", "reviews", "contrary"])
        self.assertIn("2 searches reported 9412 results, of which 21 were looked at.", status["flow"])
        self.assertIn("(animal study: 1)", status["flow"])

        _, exported = self.run_cli("export")
        self.assertEqual(exported["included"], 3)
        rows = list(csv.DictReader(io.StringIO((self.dir / "papers.csv").read_text(encoding="utf-8"))))
        self.assertEqual([r["key"] for r in rows], ["rasch2013role", "yoo2007sleep", "seed2001seed"])
        self.assertEqual((rows[0]["result"], rows[0]["locator"], rows[0]["read"]),
                         ("sleep after learning stabilises memory", "p. 690", "full_text"))
        self.assertEqual(rows[1]["authors"], "Seung-Schik Yoo et al.")
        bibliography = (self.dir / "references.bib").read_text(encoding="utf-8")
        self.assertIn("@article{rasch2013role,", bibliography)
        self.assertIn("author = {Björn Rasch and Jan Born}", bibliography)
        self.assertIn("author = {Seung-Schik Yoo and others}", bibliography)   # five authors, one returned
        self.assertIn("title = {{Sleep deprivation \\& hippocampal function}}", bibliography)
        self.assertIn("eprint = {0701.00001}", bibliography)
        log = (self.dir / "search-log.md").read_text(encoding="utf-8")
        self.assertIn('| s1 | relevance | 1 | `"sleep deprivation" memory` | relevance | yearFrom=2000 | 412 | 20 | 3 |', log)
        self.assertIn("| s2 | foundational |", log)

        review = Path(self.tmp.name) / "review.md"
        review.write_text("Sleep stabilises memory [@rasch2013role; @yoo2007sleep]. Mice too [@researcher2013study]. "
                          "And [@nobody1999ghost], and the seed [@seed2001seed]. Mail a@b.org.")
        code, check = self.run_cli("check", str(review))
        self.assertEqual(code, 1)
        self.assertEqual(check["not_in_ledger"], ["nobody1999ghost"])
        self.assertEqual(check["not_included"], ["researcher2013study"])
        self.assertEqual(check["cited_but_not_read"], ["seed2001seed"])
        self.assertEqual(check["cited_from_abstract_only"], ["yoo2007sleep"])
        review.write_text("Sleep stabilises memory [@rasch2013role; @yoo2007sleep].")
        code, check = self.run_cli("check", str(review))
        self.assertEqual((code, check["ok"], check["included_but_never_cited"]), (0, True, ["seed2001seed"]))

    def test_keys_are_unique_and_plain(self):
        taken: set = set()
        first = rl.make_key({"authors": ["Łukasz Kaiser"], "year": 2017, "title": "On the Æther of Attention"}, taken)
        taken.add(first)
        self.assertRegex(first, r"^kaiser2017[a-z]+$")
        self.assertEqual(rl.make_key({"authors": ["Łukasz Kaiser"], "year": 2017, "title": "On the Æther of Attention"}, taken),
                         first + "a")
        self.assertEqual(rl.make_key({"authors": ["Born, Jan"], "year": 2010, "title": "The memory function of sleep"}, set()),
                         "born2010memory")
        self.assertEqual(rl.make_key({"title": "3D printing"}, set()), "anonprinting")

    def test_an_exclusion_needs_a_reason_and_a_paper_must_exist(self):
        self.add(PAPERS)
        with self.assertRaises(SystemExit):
            self.run_cli("decide", "3", "--exclude")
        with self.assertRaises(SystemExit):
            self.run_cli("decide", "404", "--include")
        with self.assertRaises(SystemExit):
            self.add(PAPERS, "--search", "s7")

    def test_a_paper_outside_the_index_is_kept_apart(self):
        self.add([{"title": "A report with no record", "authors": ["R. Port"], "year": 2020}])
        self.run_cli("decide", "port2020report", "--include")
        self.run_cli("read", "port2020report", "--depth", "full_text")
        review = Path(self.tmp.name) / "review.md"
        review.write_text("As reported [@port2020report].")
        code, check = self.run_cli("check", str(review))
        self.assertEqual((code, check["not_from_the_index"]), (0, ["port2020report"]))


if __name__ == "__main__":
    unittest.main()
