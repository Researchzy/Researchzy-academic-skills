"""check_claims.py: a verdict is accepted only when its quote is in the source."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("check_claims", SCRIPTS / "check_claims.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)
from quote_match import match_quality  # noqa: E402

FILLER = " ".join(f"Sentence {i} of the methods describes the training schedule in detail." for i in range(60))
PAPER = (
    "[[page 1]]\nDeep residual learning. We present a residual learning framework.\n" + FILLER + "\n"
    "[[page 2]]\nAn ensemble of these residual nets achieves 3.57% error on the ImageNet\n"
    "17 test set. This result won the 1st place on the ILSVRC 2015 classifi-\ncation task.\n"
)


class QuoteMatchTests(unittest.TestCase):
    def test_grades(self):
        source = "The method was\n86 performed on all assess-\nments before seeing the output of the model."
        self.assertEqual(match_quality("performed on all assessments before seeing", source)["grade"], "EXACT")
        self.assertEqual(match_quality("the method was performed on all assessments", source)["grade"], "INTERLEAVED")
        self.assertEqual(match_quality("the method was carefully performed on all assessments before seeing the output",
                                       source)["grade"], "PARTIAL")
        self.assertEqual(match_quality("an entirely different sentence about protein folding", source)["grade"], "ABSENT")


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "he2016.txt").write_text(PAPER, encoding="utf-8")
        (self.dir / "abstract.txt").write_text("We present a residual learning framework to ease the training.", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def claim(self, **fields):
        base = {"id": "c1", "ref_id": "he2016", "location": "main.tex:3", "sentence": "Error fell to 3.57%.",
                "verdict": "supported", "source": "he2016.txt", "read": "full_text"}
        base.update(fields)
        return cc.check_claim(base, self.dir, {})

    def test_a_quote_in_the_source_is_accepted_with_the_page_it_is_on(self):
        out = self.claim(quote="achieves 3.57% error on the ImageNet test set", page=1)
        self.assertEqual((out["check"], out["accepted"], out["page_found"]), ("quote_found", True, 2))
        self.assertEqual(out["grade"], "INTERLEAVED")  # the line number 17 sits inside the sentence

    def test_a_word_split_at_a_line_break_still_matches(self):
        out = self.claim(quote="won the 1st place on the ILSVRC 2015 classification task")
        self.assertEqual((out["check"], out["grade"]), ("quote_found", "EXACT"))

    def test_a_quote_that_is_not_there_is_not_accepted(self):
        out = self.claim(quote="reduces the error to 2.1% on every benchmark we tried")
        self.assertEqual((out["check"], out["accepted"]), ("quote_not_found", False))

    def test_supported_needs_a_quote_and_a_source(self):
        self.assertEqual(self.claim()["check"], "needs_quote")
        self.assertEqual(self.claim(quote="achieves 3.57% error on the ImageNet test set", source="missing.txt")["check"],
                         "no_source")
        self.assertEqual(self.claim(quote="3.57% error")["check"], "quote_too_short")

    def test_other_verdicts(self):
        self.assertTrue(self.claim(verdict="not_supported")["accepted"])
        self.assertTrue(self.claim(verdict="cannot_tell")["accepted"])
        self.assertEqual(self.claim(verdict="definitely")["check"], "unknown_verdict")

    def test_a_short_source_is_not_a_full_text(self):
        out = self.claim(source="abstract.txt", quote="a residual learning framework to ease the training")
        self.assertEqual((out["check"], out["read"]), ("quote_found", "abstract"))
        self.assertIsNone(out["page_found"])

    def test_the_command_writes_both_reports(self):
        claims = {"claims": [
            {"id": "c1", "ref_id": "he2016", "location": "main.tex:3", "sentence": "Error fell to 3.57%.",
             "verdict": "supported", "quote": "achieves 3.57% error on the ImageNet test set", "page": 1,
             "source": "he2016.txt", "read": "full_text"},
            {"id": "c2", "ref_id": "he2016", "location": "main.tex:9", "sentence": "It beats every model.",
             "verdict": "supported", "quote": "our model beats every other model ever published", "source": "he2016.txt"},
        ]}
        (self.dir / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
        old, out = sys.argv, io.StringIO()
        sys.argv = ["check_claims.py", "check", str(self.dir / "claims.json"), "--strict"]
        try:
            with redirect_stdout(out):
                code = cc.main()
        finally:
            sys.argv = old
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["not_accepted"], [{"id": "c2", "ref_id": "he2016", "check": "quote_not_found"}])
        table = (self.dir / "claims.md").read_text(encoding="utf-8")
        self.assertIn("| 2 (given as 1) | quote found in the source |", table)
        self.assertIn("quote is not in the source: verdict not accepted", table)
        self.assertEqual(len(json.loads((self.dir / "claims-checked.json").read_text())["claims"]), 2)


if __name__ == "__main__":
    unittest.main()
