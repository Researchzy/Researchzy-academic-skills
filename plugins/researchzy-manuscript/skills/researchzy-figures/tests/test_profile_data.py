"""profile_data.py: column roles, n per group, pairing, and the charts a profile rules out."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "profile_data.py"
spec = importlib.util.spec_from_file_location("profile_data", SCRIPT)
pd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pd)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def table(self, name: str, header: str, rows: list, delimiter: str = ",") -> Path:
        path = self.dir / name
        path.write_text("\n".join([header] + [delimiter.join(str(v) for v in row) for row in rows]) + "\n", encoding="utf-8")
        return path

    def run_cli(self, path, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = pd.main([str(path), "--out", str(self.dir / "figures"), *argv])
        return code, json.loads(out.getvalue())

    def profile(self, path, *argv) -> tuple:
        code, summary = self.run_cli(path, *argv)
        self.assertEqual(code, 0)
        return summary, json.loads(Path(summary["profile"]).read_text(encoding="utf-8"))

    def ruled_out(self, summary: dict) -> str:
        return " | ".join(rule["chart"] for rule in summary["ruled_out"])

    def groups(self, n: int, name: str = "groups.csv") -> Path:
        rows = [(f"m{g}{i}", g, 20 + i + (3 if g == "KO" else 0)) for g in ("WT", "KO") for i in range(n)]
        return self.table(name, "mouse_id,genotype,weight_g", rows)

    def test_paired_data_rule_out_independent_group_plots(self):
        rows = []
        for i in range(1, 13):
            rows += [(f"S{i:02d}", "placebo", 30 + i), (f"S{i:02d}", "drug", "" if i == 7 else 20 + i)]
        summary, profile = self.profile(self.table("trial.csv", "subject,condition,latency_min", rows))
        self.assertEqual(summary["roles"], {"subject": "id", "condition": "group", "latency_min": "measure"})
        self.assertEqual((summary["design"], summary["smallest_n_per_group"]), (["paired"], {"latency_min": 11}))
        first = summary["ruled_out"][0]
        self.assertIn("independent-groups plots", first["chart"])
        self.assertIn("12 of 12 subject values occur in several levels of condition", first["because"])
        self.assertIn("1 of 12 lack a value of latency_min", first["instead"])       # the incomplete pair is named
        self.assertIn("latency_min: 1 of 24 missing. Missing is not zero", " ".join(summary["notes"]))

        self.assertEqual(Path(summary["profile"]).name, "trial.profile.json")
        self.assertEqual(profile["n_per_group"]["condition"]["drug"], {"rows": 12, "units": 12, "n": {"latency_min": 11}})
        self.assertEqual(profile["structure"]["paired"]["condition"],
                         {"levels": 2, "ids": 12, "ids_in_several_levels": 12, "ids_complete": {"latency_min": 11}})
        self.assertEqual(len(profile["file"]["sha256"]), 64)
        measure = profile["columns"][2]
        self.assertEqual((measure["n"], measure["missing"], measure["stats"]["min"], measure["stats"]["max"]), (23, 1, 21.0, 42.0))

    def test_small_groups_rule_out_summaries_that_hide_the_points(self):
        cases = {3: "bars of means, box plots, violins and density curves",
                 6: "bars of means (with or without error bars), violins and density curves",
                 12: "violins and density curves"}
        for n, chart in cases.items():
            summary, _ = self.profile(self.groups(n))
            self.assertEqual((summary["design"], summary["smallest_n_per_group"]), (["independent"], {"weight_g": n}))
            self.assertEqual(self.ruled_out(summary), chart, n)
            self.assertIn(f"n = {n}", summary["ruled_out"][0]["because"])
        self.assertEqual(self.profile(self.groups(40))[0]["ruled_out"], [])

    def test_roles_can_be_set_by_the_user(self):
        rows = [(i, 1 + i % 3, 10 * (1 + i % 3) + i) for i in range(30)]
        path = self.table("dose.csv", "animal,dose,response", rows)
        guessed, _ = self.profile(path)
        self.assertEqual(guessed["roles"], {"animal": "id", "dose": "measure", "response": "measure"})
        self.assertIn("dose: only 3 distinct whole numbers", " ".join(guessed["notes"]))
        chosen, profile = self.profile(path, "--group", "dose", "--id", "animal", "--name", "by-dose")
        self.assertEqual(chosen["roles"], {"animal": "id (set by user)", "dose": "group (set by user)", "response": "measure"})
        self.assertEqual(sorted(profile["n_per_group"]["dose"]), ["1", "2", "3"])
        self.assertEqual(Path(chosen["profile"]).name, "by-dose.profile.json")

    def test_without_an_id_column_the_unit_is_an_assumption(self):
        rows = [(g, 5 + i) for g in ("a", "b") for i in range(12)]
        summary, _ = self.profile(self.table("plain.csv", "arm,score", rows))
        self.assertEqual(summary["design"], ["no_id_column"])
        self.assertIn("name that column with --id", " ".join(summary["notes"]))

    def test_pair_column_links_different_subjects(self):
        rows = [(f"p{i}", f"pair{i // 2}", "case" if i % 2 else "control", 50 + i) for i in range(24)]
        summary, profile = self.profile(self.table("matched.csv", "patient,matched_set,status,marker", rows),
                                        "--pair", "matched_set")
        self.assertEqual(summary["design"], ["paired"])
        self.assertEqual(profile["structure"]["linked_by"]["column"], "matched_set")
        # Without it the patients are simply two independent groups.
        self.assertEqual(self.profile(self.dir / "matched.csv")[0]["design"], ["independent"])

    def test_repeated_measures_replicates_and_decimal_commas(self):
        rows = [(f"P{s}", "A" if s <= 3 else "B", week, f"{s + week},{rep}")
                for s in range(1, 7) for week in (0, 2, 4, 8) for rep in (1, 2)]
        summary, profile = self.profile(self.table("long.csv", "patient;arm;week;crp", rows, ";"))
        self.assertEqual(summary["roles"], {"patient": "id", "arm": "group", "week": "time", "crp": "measure"})
        self.assertEqual(summary["design"], ["repeated_over_time", "replicates"])
        self.assertEqual(summary["smallest_n_per_group"], {"crp": 3})                 # patients, not the 24 rows per arm
        self.assertEqual(profile["n_per_group"]["arm"]["A"]["rows"], 24)
        chart = self.ruled_out(summary)
        self.assertIn("one pooled line or scatter", chart)
        self.assertIn("counts each row as an independent observation", chart)
        self.assertIn("bars of means, box plots", chart)
        self.assertEqual(profile["structure"]["replicates"], {"cells_with_several_rows": 24, "most_rows_per_cell": 2})
        self.assertEqual(profile["columns"][2]["levels"], ["0", "2", "4", "8"])
        self.assertIn("decimal comma", " ".join(summary["notes"]))
        self.assertEqual(profile["columns"][3]["stats"]["max"], 14.2)

    def test_values_that_are_not_numbers_and_codes_for_missing(self):
        rows = [(f"s{i}", ["<0.1", "NA", "-999", "3.5", "12", "40", "8", "9.5", "11", "2"][i % 10]) for i in range(20)]
        path = self.table("titer.tsv", "sample\ttiter", rows, "\t")
        summary, profile = self.profile(path)
        column = profile["columns"][1]
        self.assertEqual((column["role"], column["n"], column["missing"], column["not_numbers"]), ("measure", 16, 4, 2))
        notes = " ".join(summary["notes"])
        self.assertIn("2 value(s) are not numbers (<0.1)", notes)
        self.assertIn("the value -999 occurs 2 time(s)", notes)
        self.assertIn("run again with --na -999", notes)
        cleaned, profile = self.profile(path, "--na", "-999")
        self.assertEqual((profile["columns"][1]["n"], profile["columns"][1]["stats"]["min"]), (14, 2.0))
        self.assertNotIn("-999 occurs", " ".join(cleaned["notes"]))

    def test_a_table_of_summaries_is_recognised(self):
        rows = [("ours", 0.91, 0.01), ("baseline A", 0.88, 0.02), ("baseline B", 0.86, 0.03)]
        summary, _ = self.profile(self.table("results.csv", "method,accuracy,sd", rows))
        self.assertEqual(summary["roles"], {"method": "group", "accuracy": "measure", "sd": "measure"})
        self.assertIn("box plots, violins, histograms and error bars computed from this file", self.ruled_out(summary))
        self.assertIn("only 6 numbers to show", " ".join(summary["notes"]))
        # A text column without repeats is the row label when nothing else groups the rows.
        other, _ = self.profile(self.table("named.csv", "variant,score", [("alpha", 1), ("beta", 2), ("gamma", 4)]))
        self.assertEqual(other["roles"]["variant"], "group")

    def test_skewed_measures_and_zeros(self):
        values = [0, 0, 1, 1, 2, 2, 3, 3, 4, 5, 8, 20, 300, 4000]
        rows = [(f"site{k}", v) for k in range(10) for v in values]
        summary, profile = self.profile(self.table("counts.csv", "site,count", rows))
        rule = next(r for r in summary["ruled_out"] if r["chart"].startswith("mean with SD or SEM bars for count"))
        self.assertIn("positive values span 1 to 4000", rule["because"])
        self.assertIn("a log axis cannot show the 20 zero or negative value(s)", rule["instead"])
        self.assertIn("one colour per level of site", self.ruled_out(summary))            # ten levels, eight colours
        self.assertGreater(profile["columns"][1]["stats"]["skew"], 1)

    def test_statistics(self):
        stats = pd.describe([1.0, 2.0, 3.0, 4.0, 10.0])
        self.assertEqual((stats["n"], stats["median"], stats["q1"], stats["q3"], stats["outside_1_5_iqr"]), (5, 3.0, 2.0, 4.0, 1))
        self.assertAlmostEqual(stats["skew"], 1.69706, places=4)
        self.assertEqual(pd.describe([2.0, 4.0, 6.0])["skew"], 0.0)
        self.assertNotIn("skew", pd.describe([5.0, 5.0, 5.0]))
        self.assertEqual(pd.tokens("subjectID"), {"subject", "id"})
        self.assertEqual(pd.tokens("Sample_Type"), {"sample", "type"})

    def test_bad_input_stops_with_exit_code_2(self):
        path = self.groups(6)
        for argv in ([str(self.dir / "missing.csv")], [str(path), "--id", "nope"], [str(path), "--measure", "genotype"],
                     [str(self.table("empty.csv", "a,b", []))]):
            with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()) as err:
                pd.main(argv + ["--out", str(self.dir / "figures")])
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("profile_data:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
