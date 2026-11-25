"""tei_text.py: GROBID's TEI becomes Markdown with page markers and linked citations, and a reference list."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).parent
SCRIPT = HERE.parent / "scripts" / "tei_text.py"
spec = importlib.util.spec_from_file_location("tei_text", SCRIPT)
tt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tt)

SAMPLE = HERE / "fixtures" / "sample.tei.xml"


def convert(path: Path = SAMPLE) -> tuple[str, dict, str]:
    out = Path(tempfile.mkdtemp())
    printed = io.StringIO()
    with redirect_stdout(printed):
        assert tt.main([str(path), "--out", str(out)]) == 0
    return ((out / "paper.md").read_text(encoding="utf-8"),
            json.loads((out / "references.json").read_text(encoding="utf-8")), printed.getvalue())


class TeiTextTests(unittest.TestCase):
    def test_header_has_title_authors_with_affiliations_keywords_and_abstract_but_no_emails(self):
        markdown, _, _ = convert()
        self.assertTrue(markdown.startswith("# Night Shifts and Recall in Hospital Nurses\n"))
        self.assertIn("- Ada Okoro (Nursing, Example University)\n- Ben J Lee", markdown)
        self.assertIn("Keywords: sleep; memory", markdown)
        self.assertIn("## Abstract\n\nWe followed 80 nurses", markdown)
        self.assertNotIn("ada@example.test", markdown)

    def test_headings_follow_section_numbers_and_pages_are_marked_where_they_change(self):
        markdown, _, _ = convert()
        self.assertIn("[[page 1]]\n\n## Abstract", markdown)
        self.assertIn("## 1 Introduction", markdown)
        self.assertIn("[[page 2]]\n\n### 2.1 Cohort", markdown)
        self.assertEqual(markdown.count("[[page 2]]"), 1)

    def test_citations_link_to_references_and_keep_their_printed_brackets(self):
        markdown, _, printed = convert()
        self.assertIn("attention [[1](#b0)] and memory [[2](#b1),[1](#b0)].", markdown)
        self.assertIn("night shifts ([Lee et al. 2019](#b1)).", markdown)
        self.assertIn("Rotating rosters are common [9].", markdown)  # GROBID found no reference for it
        self.assertIn("4 of 5 in-text citations linked", printed)

    def test_formulas_tables_footnotes_back_matter_and_funders(self):
        markdown, _, _ = convert()
        self.assertIn("$$ r = a + b n $$ (1)", markdown)
        self.assertIn("**Table 1.** Recall by shift pattern.", markdown)
        self.assertIn("| Pattern | Recall |\n|---|\n| Day | 0.81 |", markdown)
        self.assertIn("## Footnotes\n\n[[page 1]]\n\n[1] Rosters as of 2024.", markdown)
        self.assertNotIn("common [9].Rosters", markdown)
        self.assertIn("## Acknowledgements\n\n[[page 3]]\n\nWe thank the ward staff.", markdown)
        self.assertIn("- National Science Foundation (NSF): AST-1, AST-2", markdown)

    def test_references_carry_parsed_fields_their_page_and_how_often_they_are_cited(self):
        _, data, _ = convert()
        first, second = data["references"]
        self.assertEqual(first, {"id": "b0", "title": "Sleep deprivation and attention", "venue": "Sleep",
                                 "authors": ["C Diaz"], "year": 2018, "volume": "12", "pages": "1-9",
                                 "doi": "10.1000/sleep.1", "page": 3, "citedInText": 2})
        self.assertEqual(second["title"], "Memory at work")
        self.assertNotIn("venue", second)
        self.assertEqual(second["arxiv"], "arXiv:1901.00001")
        self.assertEqual(second["citedInText"], 2)
        self.assertEqual(data["source"], "sample.tei.xml")

    def test_text_listed_after_the_body_is_marked_with_its_own_page(self):
        markdown, _, _ = convert()
        pages = [int(line[7:-2]) for line in markdown.splitlines() if line.startswith("[[page ")]
        self.assertEqual(pages, [1, 2, 3, 1, 3])  # body, the table, the footnote, the acknowledgements

    def test_a_short_text_is_flagged_as_not_a_full_text(self):
        _, _, printed = convert()
        self.assertIn("not a full text", printed)

    def test_a_file_that_is_not_tei_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "bad.xml"
            for content in ("<html><body/></html>", "not xml"):
                bad.write_text(content, encoding="utf-8")
                with redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(tt.main([str(bad), "--out", folder]), 2)
                self.assertIn("bad.xml", error.getvalue())


if __name__ == "__main__":
    unittest.main()
