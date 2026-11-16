"""style_profile.py: counts and sources, never text; too few texts are not a profile; notes, not errors."""
from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("style_profile", SCRIPTS / "style_profile.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

AUTHOR = """# Paper {i}

We recruited nurses from three hospitals and analysed their sleep with actigraphy for {days} days. The analysis was
prespecified, and the data were checked twice.

Our results suggest that rotating shifts may disturb sleep. However, the effect was small, and it was not seen in
older nurses. Schedules, rosters, and staffing deserve attention.
"""
DRAFT = """## Discussion

The present findings clearly demonstrate that rotating shift schedules organize sleep in a markedly different way
from fixed schedules, and the differences were significantly larger in younger nurses than in older nurses, which is a
pattern that has been reported repeatedly in the literature on occupational health and hospital management.
"""
ABSTRACT = ("Background: Shift work disturbs sleep. Methods: We followed {n} nurses for 12 months with diaries. "
            "Results: Night shifts were associated with shorter sleep. Conclusions: Rosters may matter for sleep.")


def five_grams(text: str) -> set:
    words = re.findall(r"[a-z]+", text.lower())
    return {" ".join(words[i:i + 5]) for i in range(len(words) - 4)}


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, text: str) -> str:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = sp.main(list(argv))
        return code, json.loads(out.getvalue())

    def authors(self, n: int) -> list[str]:
        return [self.write(f"paper{i}.md", AUTHOR.format(i=i, days=7 + i)) for i in range(n)]

    def hits(self, kept: int) -> str:
        results = [{"corpusId": 100 + i, "title": f"Night shifts and sleep in nurses: a cohort of {200 + i}",
                    "year": 2024, "venue": "Journal of Sleep Research" if i % 2 else "J. Sleep Res.",
                    "doi": f"10.1111/jsr.{i}", "abstract": ABSTRACT.format(n=100 + i)} for i in range(kept)]
        results += [{"corpusId": 900, "title": "Elsewhere", "venue": "Sleep Medicine", "abstract": "Other text here."},
                    {"corpusId": 901, "title": "Bare", "venue": "Journal of Sleep Research", "abstract": ""},
                    dict(results[0])]
        search = {"query": "night shift sleep nurses", "filters": {"venue": "Journal of Sleep Research", "yearFrom": 2022},
                  "sort": "year", "date": "2026-11-13", "results": results}
        return self.write("hits.json", json.dumps({"searches": [search]}))

    def test_an_author_profile_keeps_counts_and_sources_never_text(self):
        files = self.authors(3)
        code, summary = self.run_cli("build", *files, "--out", str(self.dir / "polish" / "profile-author.json"))
        self.assertEqual((code, summary["status"], summary["texts"], summary["minimum"]), (0, "ok", 3, 3))
        stored = (self.dir / "polish" / "profile-author.json").read_text(encoding="utf-8")
        profile = json.loads(stored)
        self.assertEqual([s["file"] for s in profile["sources"]], ["paper0.md", "paper1.md", "paper2.md"])
        self.assertEqual(len(profile["sources"][0]["sha256"]), 64)
        values = profile["profile"]["values"]
        self.assertGreater(values["hedges"], 0)
        self.assertGreater(values["we"], 0)
        self.assertEqual(profile["profile"]["spelling"], {"US": 0, "UK": 3})
        self.assertEqual(profile["profile"]["serial_comma"], {"with": 3, "without": 0})
        self.assertEqual(set(profile["profile"]["ranges"]), set(values))
        leaked = five_grams(stored) & set().union(*(five_grams(Path(f).read_text()) for f in files))
        self.assertEqual(leaked, set())

    def test_too_few_texts_are_not_a_profile(self):
        code, summary = self.run_cli("build", *self.authors(2), "--out", str(self.dir / "p.json"))
        profile = json.loads((self.dir / "p.json").read_text())
        self.assertEqual((code, summary["status"], profile["profile"]), (0, "not enough texts", {}))
        self.assertEqual(profile["minimum_is"], "a convention; --min changes it")
        self.assertEqual(self.run_cli("build", *self.authors(2), "--min", "2", "--out", str(self.dir / "q.json"))[1]["status"], "ok")
        code, summary = self.run_cli("build", *self.authors(4), "--kind", "journal", "--out", str(self.dir / "j.json"))
        self.assertEqual((summary["status"], summary["minimum"]), ("not enough texts", 5))   # journal papers

    def test_a_journal_profile_from_saved_search_results(self):
        hits = self.hits(22)
        code, summary = self.run_cli("build", "--search-json", hits, "--venue", "Journal of Sleep Research",
                                     "--venue", "J Sleep Res", "--out", str(self.dir / "journal.json"))
        stored = (self.dir / "journal.json").read_text(encoding="utf-8")
        profile = json.loads(stored)
        self.assertEqual((code, summary["status"], summary["hits"], summary["kept"]), (0, "ok", 25, 22))
        sample = profile["sample"]
        self.assertEqual((sample["duplicates"], sample["other_venue"], sample["no_abstract"]), (1, 1, 1))
        self.assertEqual(sample["venues_dropped"], {"Sleep Medicine": 1})
        self.assertEqual(sample["searches"], [{"query": "night shift sleep nurses", "sort": "year", "date": "2026-11-13",
                                               "filters": {"venue": "Journal of Sleep Research", "yearFrom": 2022}}])
        self.assertIn("not a random sample", profile["note"])
        self.assertEqual((profile["profile"]["structured_share"], profile["profile"]["title_colon_share"]), (1.0, 1.0))
        self.assertEqual(profile["profile"]["title_words"]["median"], 10.0)
        self.assertEqual(profile["sources"][0]["corpusId"], 100)
        texts = [h["title"] + " " + h["abstract"] for h in json.loads(Path(hits).read_text())["searches"][0]["results"]]
        self.assertEqual(five_grams(stored) & set().union(*(five_grams(t) for t in texts)), set())
        code, summary = self.run_cli("build", "--search-json", self.hits(19), "--venue", "Journal of Sleep Research",
                                     "--venue", "J Sleep Res", "--out", str(self.dir / "few.json"))
        self.assertEqual((summary["kept"], summary["status"]), (19, "not enough texts"))

    def test_compare_writes_notes_not_errors(self):
        self.run_cli("build", *self.authors(3), "--out", str(self.dir / "author.json"))
        code, summary = self.run_cli("compare", self.write("draft.md", DRAFT), str(self.dir / "author.json"),
                                     "--out", str(self.dir / "polish"))
        notes = {n["feature"]: n for n in json.loads((self.dir / "polish" / "profile-compare.json").read_text())["notes"]}
        self.assertEqual(code, 0)
        self.assertEqual(notes["sentence median"]["note"], "higher than in every text of the profile")
        self.assertEqual(notes["we per 1,000 words"]["note"], "lower than in every text of the profile")
        self.assertEqual((notes["spelling"]["draft"], notes["spelling"]["profile"]), ("US", "UK"))
        self.assertTrue(notes["spelling"]["note"].startswith("different: ask the author"))
        self.assertEqual(notes["'significant' without a test in the sentence"]["draft"], 1)
        report = (self.dir / "polish" / "profile-compare.md").read_text(encoding="utf-8")
        self.assertIn("They are not errors and not instructions", report)
        self.run_cli("build", *self.authors(1), "--out", str(self.dir / "thin.json"))
        code, summary = self.run_cli("compare", str(self.dir / "draft.md"), str(self.dir / "thin.json"), "--out", str(self.dir / "t"))
        self.assertEqual((code, summary["notes"]), (0, 0))
        self.assertIn("Not compared: the profile has 1 texts", (self.dir / "t" / "profile-compare.md").read_text())

    def test_measure(self):
        counts = sp.measure([["We may see that the effect was clearly shown to be strong.",
                              "Groups were compared; scores differed significantly (p = 0.01).",
                              "Age, sex and site were recorded — and the BMI was analyzed."]])["counts"]
        self.assertEqual((counts["hedges"], counts["boosters"], counts["we"]), (1, 1, 1))
        self.assertEqual((counts["passive_sentences"], counts["dashes"], counts["abbreviations"]), (3, 1, 1))
        self.assertEqual((counts["serial_comma"], counts["no_serial_comma"]), (0, 1))
        self.assertEqual((counts["significant_with_test"], counts["significant_without_test"]), (1, 0))
        self.assertEqual((counts["us_spellings"], counts["uk_spellings"]), (1, 0))

    def test_bad_input_exits_with_2(self):
        not_profile = self.write("other.json", json.dumps({"tool": "something else"}))
        for argv in (["build"], ["build", self.write("a.md", "Text here.\n"), "--search-json", "x.json"],
                     ["build", "--search-json", self.hits(3)], ["build", str(self.dir / "missing.md")],
                     ["compare", self.write("d.md", "Text here.\n"), not_profile]):
            with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
                sp.main(argv + (["--out", str(self.dir / "x.json")] if argv[0] == "build" else []))
            self.assertEqual(raised.exception.code, 2, argv)


if __name__ == "__main__":
    unittest.main()
