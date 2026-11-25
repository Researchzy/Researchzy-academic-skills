"""score_items.py: scoring from the declared map, keying leads, missing codes, range problems, Chinese names."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "score_items.py"
spec = importlib.util.spec_from_file_location("score_items", SCRIPT)
si = importlib.util.module_from_spec(spec)
spec.loader.exec_module(si)

try:
    import pyreadstat
    HAS_PYREADSTAT = True
except ImportError:
    HAS_PYREADSTAT = False


def rows(reverse_stored=True, n=15):
    """a1, a2, a4 follow a respondent's level; a3 is worded the other way (stored as answered unless told)."""
    out = []
    for i in range(n):
        level = 1 + i % 5
        out.append({"id": str(i + 1), "a1": level, "a2": min(5, level + (i % 3 == 0)), "a3": 6 - level if reverse_stored
                    else level, "a4": max(1, level - (i % 4 == 0)), "b1": 1 + (i * 2) % 5, "b2": 1 + (i * 2 + 1) % 5})
    return out


def item_map(**changes):
    spec = {"data": "survey.csv", "missing": ["-99"], "reversed_in_data": False, "confirmed": "2026-11-18",
            "constructs": {"AUT": {"items": ["a1", "a2", "a3", "a4"], "reverse": [], "min": 1, "max": 5,
                                   "source": "invented test scale", "licence": "open"},
                           "OTH": {"items": ["b1", "b2"], "reverse": [], "min": 1, "max": 5, "source": "invented",
                                   "licence": "unknown"}}}
    spec.update(changes)
    return spec


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("psychometrics").mkdir()

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def write(self, table, spec, name="survey.csv"):
        with open(name, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(table[0]))
            writer.writeheader()
            writer.writerows(table)
        Path("psychometrics/items.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = si.main(["psychometrics/items.json", *argv])
            except SystemExit as stop:
                code = stop.code
        self.err = err.getvalue()
        return code, (json.loads(out.getvalue()) if out.getvalue() else None)

    def scored(self, column):
        with open("psychometrics/survey.scored.csv", encoding="utf-8") as stream:
            return [row[column] for row in csv.DictReader(stream)]

    def test_an_undeclared_reverse_worded_item_is_a_lead(self):
        self.write(rows(), item_map())
        code, out = self.run_cli()
        self.assertEqual((code, out["problems"]), (0, []))
        lead = " ".join(out["leads"]["negative item-rest r"])
        self.assertIn("a3 (AUT): item-rest r -", lead)
        self.assertIn('not declared reverse: a reverse-worded item missing from "reverse"', lead)
        self.assertEqual(self.scored("a3"), [str(r["a3"]) for r in rows()])      # nothing reversed

    def test_declared_reverse_items_are_scored_and_the_data_file_is_untouched(self):
        self.write(rows(), item_map())
        before = hashlib.sha256(Path("survey.csv").read_bytes()).hexdigest()
        spec = item_map()
        spec["constructs"]["AUT"]["reverse"] = ["a3"]
        Path("psychometrics/items.json").write_text(json.dumps(spec), encoding="utf-8")
        code, out = self.run_cli()
        self.assertEqual((code, out["leads"]), (0, {}))
        self.assertEqual(self.scored("a3"), [str(1 + 5 - r["a3"]) for r in rows()])      # (min + max) - x
        aut = out["constructs"]["AUT"]
        self.assertLess(aut["alpha_in_data"], 0.3)
        self.assertGreater(aut["alpha_scored"], 0.8)
        self.assertEqual(hashlib.sha256(Path("survey.csv").read_bytes()).hexdigest(), before)
        record = json.loads(Path("psychometrics/scoring.json").read_text())
        self.assertEqual(record["data"]["sha256"], before)
        self.assertGreater(record["constructs"]["AUT"]["items"]["a3"]["item_rest_r_scored"], 0)

    def test_an_item_reversed_twice_is_a_lead(self):
        spec = item_map()
        spec["constructs"]["AUT"]["reverse"] = ["a3"]
        self.write(rows(reverse_stored=False), spec)          # the file already holds a3 reversed
        code, out = self.run_cli()
        self.assertIn("a3 (AUT): declared reverse, item-rest r -", " ".join(out["leads"]["negative item-rest r"]))
        self.assertIn("reversed twice", " ".join(out["leads"]["negative item-rest r"]))
        Path("psychometrics/items.json").write_text(json.dumps(dict(spec, reversed_in_data=True)), encoding="utf-8")
        code, out = self.run_cli()
        self.assertEqual((code, out["leads"]), (0, {}))

    def test_missing_codes_and_values_outside_the_scale(self):
        table = rows()
        table[0]["a1"], table[1]["a2"], table[2]["a4"], table[3]["b1"] = "-99", "8", "abc", "-98"
        self.write(table, item_map())
        code, out = self.run_cli()
        self.assertEqual(code, 1)
        problems = " ".join(out["problems"])
        self.assertIn("a2: 1 value(s) outside 1 to 5 or not numbers: 8 (1)", problems)
        self.assertIn("a4: 1 value(s) outside 1 to 5 or not numbers: abc (1)", problems)
        self.assertIn("b1: 1 value(s) outside 1 to 5 or not numbers: -98 (1)", problems)       # undeclared code
        self.assertNotIn("a1:", problems)                                                      # -99 is declared
        self.assertEqual((self.scored("a1")[0], self.scored("a2")[1]), ("", ""))
        self.assertEqual(out["constructs"]["AUT"]["n"], 12)

    def test_a_constant_item_is_a_problem_and_few_categories_a_lead(self):
        table = rows()
        for r in table:
            r["b1"], r["b2"] = 3, 1 + int(r["id"]) % 2
        self.write(table, item_map())
        code, out = self.run_cli("--few-categories", "4")
        self.assertEqual(code, 1)
        self.assertIn("b1: every answer is 3", out["problems"][0])
        self.assertIn("b2 (OTH) uses 2 of its response categories", " ".join(out["leads"]["few categories"]))

    def test_an_item_map_without_a_confirmed_date_is_a_lead(self):
        spec = item_map()
        del spec["confirmed"]
        self.write(rows(), spec)
        self.assertIn("not confirmed", self.run_cli()[1]["leads"])

    def test_an_item_map_that_cannot_be_used_exits_2(self):
        cases = ((dict(reversed_in_data=None), "reversed_in_data"), (dict(missing="-99"), '"missing" must be a list'))
        for change, message in cases:
            self.write(rows(), item_map(**change))
            self.assertEqual(self.run_cli()[0], 2)
            self.assertIn(message, self.err)
        for key, value, message in (("reverse", ["b1"], '"reverse" must list items'), ("items", ["a1"], "two or more"),
                                    ("licence", "free", '"licence"'), ("min", 5, "min < max"), ("items", ["a1", "zz"],
                                                                                              "not columns of survey.csv: zz")):
            spec = item_map()
            spec["constructs"]["AUT"][key] = value
            self.write(rows(), spec)
            self.assertEqual(self.run_cli()[0], 2, key)
            self.assertIn(message, self.err)
        self.write(rows(), item_map())
        self.assertEqual(self.run_cli("--data", "nowhere.csv")[0], 2)

    def test_chinese_column_and_construct_names(self):
        table = [{"编号": r["id"], "自主1": r["a1"], "自主2": r["a2"], "自主3（反向）": r["a3"], "自主4": r["a4"]} for r in rows()]
        spec = {"data": "问卷.csv", "missing": ["-99"], "reversed_in_data": False, "confirmed": "2026-11-18",
                "constructs": {"自主性": {"items": ["自主1", "自主2", "自主3（反向）", "自主4"], "reverse": [], "min": 1,
                                          "max": 5, "source": "用户的编码表第2页", "licence": "open"}}}
        self.write(table, spec, name="问卷.csv")
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("自主3（反向） (自主性): item-rest r -", " ".join(out["leads"]["negative item-rest r"]))
        self.assertTrue(Path("psychometrics/问卷.scored.csv").is_file())
        self.assertIn("## 自主性", Path("psychometrics/scoring.md").read_text(encoding="utf-8"))

    @unittest.skipUnless(HAS_PYREADSTAT, "pyreadstat is not installed")
    def test_a_sav_file_with_user_missing_values_and_value_labels(self):
        import pandas as pd
        table = pd.DataFrame(rows()).drop(columns="id").astype(float)
        table.loc[0, "a1"] = -97.0                                       # user-missing in the file, not in items.json
        labels = {c: {1.0: "disagree", 5.0: "agree"} for c in table.columns}
        labels["a4"] = {1.0: "agree", 5.0: "disagree"}                   # this item's scale runs the other way
        pyreadstat.write_sav(table, "survey.sav", missing_ranges={"a1": [-97]}, variable_value_labels=labels)
        spec = item_map(data="survey.sav")
        spec["constructs"]["AUT"]["reverse"] = ["a3"]
        Path("psychometrics/items.json").write_text(json.dumps(spec), encoding="utf-8")
        code, out = self.run_cli()
        self.assertEqual((code, out["problems"]), (0, []))
        self.assertIn("a4 (AUT): its value labels run the other way from a1", " ".join(out["leads"]["value labels"]))
        self.assertEqual(self.scored("a1")[0], "")
        self.assertEqual(json.loads(Path("psychometrics/scoring.json").read_text())["file_missing_ranges"]["a1"],
                         [[-97.0, -97.0]])


if __name__ == "__main__":
    unittest.main()
