"""sr_agreement.py: kappa from the full table, seeded samples, thresholds from the protocol, exact audit bounds."""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import math
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("sr_agreement", SCRIPTS / "sr_agreement.py")
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)
sl = sa.sl

PROTOCOL = {
    "title": "Synthetic test review", "question": "Invented question for tests?", "framework": "PCC",
    "elements": {"population": "adults", "concept": "meal timing", "context": "any setting"},
    "criteria": [{"code": "I1", "text": "adults"}, {"code": "E1", "text": "children only"}], "exclusion_order": ["E1"],
    "outcomes": [{"name": "sleep", "role": "primary", "timepoints": ["any"]}], "designs": ["any"], "sources": ["test"],
    "limits": [], "calibration": {"kappa_min": 0.6, "recall_min": 1.0, "user_screens": True},
    "registration": {"status": "not_registered"}, "seeds": [],
}


def table(a, b, c, d):
    """(user includes, model includes) pairs for a 2x2 table."""
    return [(True, True)] * a + [(True, False)] * b + [(False, True)] * c + [(False, False)] * d


class AgreementStatisticsTests(unittest.TestCase):
    def test_kappa_comes_from_the_full_table(self):
        stats = sa.agreement(table(20, 5, 10, 15))      # a textbook table: observed 0.70, chance 0.50
        self.assertAlmostEqual(stats["kappa"], 0.4)
        self.assertAlmostEqual(stats["agreement"], 0.7)
        self.assertAlmostEqual(stats["include_recall"], 0.8)
        # 90 of 100 agree and each reviewer includes 10: assuming 50/50 margins would give 0.80; the truth is 0.44.
        stats = sa.agreement(table(5, 5, 5, 85))
        self.assertAlmostEqual(stats["kappa"], 0.08 / 0.18)
        self.assertAlmostEqual(stats["include_recall"], 0.5)
        self.assertIsNone(sa.agreement(table(0, 0, 0, 30))["kappa"])          # one category: kappa is undefined
        self.assertIsNone(sa.agreement(table(0, 0, 2, 28))["include_recall"])  # the user included nothing

    def test_the_audit_bound_is_exact(self):
        def brute(population, audited):
            return max(m for m in range(population - audited + 1)
                       if math.comb(population - m, audited) / math.comb(population, audited) >= 0.05)
        for population, audited in ((600, 59), (600, 30), (120, 120), (40, 10), (1000, 1)):
            self.assertEqual(sa.upper_bound(population, audited), brute(population, audited), (population, audited))
        self.assertEqual(sa.upper_bound(120, 120), 0)


class SampleAndScoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.dir = self.base / "systematic-review"
        (self.base / "protocol.json").write_text(json.dumps(PROTOCOL))
        self.ledger("protocol", str(self.base / "protocol.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self, *argv):
        with redirect_stdout(io.StringIO()) as out:
            code = sl.main(["--dir", str(self.dir), *argv])
        return code, json.loads(out.getvalue())

    def run_cli(self, *argv):
        with redirect_stdout(io.StringIO()) as out:
            code = sa.main(["--dir", str(self.dir), *argv])
        return code, json.loads(out.getvalue())

    def fails(self, *argv) -> str:
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()) as err, redirect_stdout(io.StringIO()):
            sa.main(["--dir", str(self.dir), *argv])
        self.assertEqual(raised.exception.code, 2)
        return err.getvalue()

    def add_records(self, n: int):
        papers = [{"corpusId": 700000 + i, "title": f"Invented record number {i} on topic {i * 7919 % 1009}",
                   "year": 2020, "abstract": f"Synthetic abstract {i}."} for i in range(n)]
        (self.base / "papers.json").write_text(json.dumps({"papers": papers}))
        self.ledger("search", "--source", "Researchzy index", "--kind", "database", "--interface", "search_papers",
                    "--query", "q", "--total", str(n), "--last-page")
        self.ledger("records", str(self.base / "papers.json"), "--search", "s1", "--format", "researchzy")

    def fill(self, name: str, include: set, unsure: set = frozenset()):
        path = self.dir / "calibration" / name
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            row["decision"] = "unsure" if row["record"] in unsure else "include" if row["record"] in include else "exclude"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=sa.COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def test_sample_sizes_seeds_and_rounds(self):
        self.add_records(30)
        code, out = self.run_cli("sample", "--seed", "11")
        self.assertEqual((code, out["sample"], out["size"], out["population"]), (0, "round1", 30, 30))   # all, under 50
        sample = json.loads((self.dir / "calibration" / "round1-sample.json").read_text())
        with open(self.dir / "calibration" / "round1-user.csv", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["record"] for r in rows], sample["records"])
        self.assertEqual({r["decision"] for r in rows}, {""})                    # no decision shown to the user
        self.assertTrue((self.dir / "calibration" / "round1-model.csv").exists())
        self.assertIn("no records left", self.fails("sample", "--seed", "12"))   # sampled records are not drawn again

    def test_default_size_and_determinism(self):
        self.add_records(700)
        first = self.run_cli("sample", "--seed", "5")[1]
        self.assertEqual(first["size"], 70)                                       # 10% of 700
        again = sa.random.Random(5).sample(sorted({f"R{i:04d}" for i in range(1, 701)}, key=sl.num), 70)
        self.assertEqual(json.loads((self.dir / "calibration" / "round1-sample.json").read_text())["records"],
                         sorted(again, key=sl.num))
        self.assertEqual(self.run_cli("sample", "--seed", "5", "--size", "20")[1]["sample"], "round2")
        self.assertIn("exists already", self.fails("sample", "--seed", "6", "--round", "2"))

    def test_scoring_against_the_protocol_thresholds(self):
        self.add_records(80)
        self.run_cli("sample", "--seed", "3")
        ids = json.loads((self.dir / "calibration" / "round1-sample.json").read_text())["records"]
        self.assertIn("write include, exclude or unsure", self.fails("score"))    # nothing filled in yet
        self.fill("round1-model.csv", set(ids[:5]), {ids[5]})
        self.fill("round1-user.csv", set(ids[:4]), {ids[5]})
        os.utime(self.dir / "calibration" / "round1-model.csv", (1, 1))
        code, out = self.run_cli("score")
        self.assertEqual((code, out["status"], out["table"]["both_include"], out["user_includes"]), (0, "passed", 5, 5))
        self.assertAlmostEqual(out["kappa"], 1 - 1 / 50 / (1 - (5 * 6 + 45 * 44) / 2500))
        self.assertEqual(out["thresholds_from"], "protocol")
        score = json.loads((self.dir / "calibration" / "round1-score.json").read_text())
        self.assertEqual(score["disagreements"][0]["record"], ids[4])
        self.assertIn("| User: include or unsure | 5 | 0 |", (self.dir / "calibration" / "round1-score.md").read_text())
        self.assertEqual(self.ledger("check")[1]["by_finding"].get("CALIBRATION_MISSING"), None)
        self.assertIn("scored round is final", self.fails("score", "--round", "1"))

        self.run_cli("sample", "--seed", "4", "--size", "20")
        self.fill("round2-model.csv", set())
        self.fill("round2-user.csv", set(json.loads((self.dir / "calibration" / "round2-sample.json").read_text())["records"][:2]))
        code, out = self.run_cli("score")
        self.assertEqual((code, out["status"], out["include_recall"]), (1, "below_threshold", 0.0))
        self.assertEqual(self.ledger("check")[1]["by_finding"].get("CALIBRATION_BELOW_THRESHOLD"), 1)

    def test_an_unassessable_round_and_a_late_model_file(self):
        self.add_records(50)
        self.run_cli("sample", "--seed", "8", "--size", "10")
        self.fill("round1-user.csv", set())
        self.fill("round1-model.csv", set())                  # written after the user's file
        os.utime(self.dir / "calibration" / "round1-user.csv", (1, 1))
        code, out = self.run_cli("score")
        self.assertEqual((code, out["status"], out["kappa"], out["include_recall"]), (1, "not_assessable", None, None))
        self.assertIn("before seeing the user's decisions", out["warning"])
        self.assertIn("cannot be computed", (self.dir / "calibration" / "round1-score.md").read_text())

    def test_an_audit_of_the_model_exclusions(self):
        self.add_records(60)
        lines = [json.dumps({"record": f"R{i:04d}", "stage": "ta", "decision": "exclude", "code": "E1",
                             "quote": f"Synthetic abstract {i - 1}", "reviewer": "model" if i <= 40 else "user"})
                 for i in range(1, 61)]
        (self.base / "ta.jsonl").write_text("\n".join(lines) + "\n")
        self.assertEqual(self.ledger("decide", str(self.base / "ta.jsonl"))[1]["accepted"], 60)
        self.assertIn("needs --size", self.fails("sample", "--audit", "--seed", "1"))
        code, out = self.run_cli("sample", "--audit", "--seed", "1", "--size", "10")
        self.assertEqual((code, out["sample"], out["population"]), (0, "audit1", 40))   # the model's exclusions only
        self.assertFalse((self.dir / "calibration" / "audit1-model.csv").exists())
        self.fill("audit1-user.csv", set())
        code, out = self.run_cli("score", "--audit")
        self.assertEqual((code, out["status"], out["upper_bound"]), (0, "none_found", sa.upper_bound(40, 10)))
        self.assertIn("cannot prove there are none", (self.dir / "calibration" / "audit1-score.md").read_text())
        self.run_cli("sample", "--audit", "--seed", "2", "--size", "5")
        wrong = json.loads((self.dir / "calibration" / "audit2-sample.json").read_text())["records"][0]
        self.fill("audit2-user.csv", {wrong})
        code, out = self.run_cli("score", "--audit")
        self.assertEqual((code, out["status"], out["wrong_exclusions"], "upper_bound" in out),
                         (1, "wrong_exclusions_found", [wrong], False))

    def test_inputs_that_cannot_be_used(self):
        self.add_records(5)
        self.assertIn("no round sample", self.fails("score"))
        self.run_cli("sample", "--seed", "1")
        with open(self.dir / "calibration" / "round1-user.csv", "a", encoding="utf-8") as fh:
            fh.write("R9999,an extra row,,,include,,\n")
        self.assertIn("exactly the 5 sampled records", self.fails("score"))
        self.dir = self.base / "elsewhere"
        self.assertIn("no ledger", self.fails("sample", "--seed", "1"))


if __name__ == "__main__":
    unittest.main()
