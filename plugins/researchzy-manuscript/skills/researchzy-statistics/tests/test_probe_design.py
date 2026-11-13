"""probe_design.py: rows per unit, pairs, n in units and rows, outcome type, sparse cells, the design."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_design.py"
spec = importlib.util.spec_from_file_location("probe_design", SCRIPT)
pdz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdz)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def table(self, header: str, rows: list, name: str = "data.csv") -> Path:
        path = self.dir / name
        path.write_text("\n".join([header] + [",".join(str(v) for v in row) for row in rows]) + "\n", encoding="utf-8")
        return path

    def probe(self, path, *argv) -> dict:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(pdz.main([str(path), "--out", str(self.dir / "statistics"), *argv]), 0)
        report = json.loads(out.getvalue())
        written = self.dir / "statistics" / f"{Path(path).stem}.design.json"
        self.assertEqual(report, json.loads(written.read_text(encoding="utf-8")))
        return report

    def ruled(self, report) -> str:
        return " | ".join(rule["method"] for rule in report["ruled_out"])

    def test_paired_with_an_incomplete_pair(self):
        rows = []
        for i in range(1, 13):
            rows += [(f"S{i:02d}", "placebo", 30 + i + 0.5), (f"S{i:02d}", "drug", "" if i == 7 else 20 + i + 0.25)]
        report = self.probe(self.table("subject,condition,latency_min", rows),
                            "--unit", "subject", "--group", "condition", "--outcome", "latency_min")
        self.assertEqual(report["design"], ["paired"])
        self.assertEqual(report["pairs"]["complete"], 11)
        self.assertEqual(report["pairs"]["incomplete"], 1)
        self.assertEqual(report["n_per_group"]["drug"],
                         {"rows": 12, "rows_with_outcome": 11, "units": 12, "units_with_outcome": 11})
        self.assertEqual(report["missing"]["latency_min"], 1)
        self.assertEqual(report["outcome"]["type"], "continuous")
        self.assertIn("independent-samples tests", self.ruled(report))
        self.assertIn("1 subject value(s) lack an outcome", report["ruled_out"][1]["because"])
        self.assertEqual(report["route"], {"table": "references/method-table.md", "row": "continuous / 2 groups",
                                           "column": "same unit measured again", "first": []})

    def test_repeated_over_time_with_groups_routes_to_a_model(self):
        rows = [(f"M{i}", "KO" if i % 2 else "WT", day, 20 + i + day * 0.5) for i in range(8) for day in (0, 7, 14)]
        report = self.probe(self.table("mouse,genotype,day,weight", rows),
                            "--unit", "mouse", "--group", "genotype", "--time", "day", "--outcome", "weight")
        self.assertEqual(report["design"], ["repeated"])
        self.assertEqual(report["repeated"][0]["levels"], 3)
        self.assertEqual(report["rows_per_unit"]["max"], 3)
        self.assertEqual(report["n_per_group"]["KO"]["units"], 4)
        self.assertEqual(report["n_per_group"]["KO"]["rows"], 12)
        self.assertEqual(report["route"]["row"], "model")
        self.assertIn("group * time", " ".join(report["route"]["first"]))

    def test_three_conditions_on_the_same_units_are_repeated(self):
        rows = [(f"P{i}", cond, 410.5 + i + 3 * j) for i in range(6) for j, cond in enumerate("ABC")]
        report = self.probe(self.table("participant,condition,rt", rows),
                            "--unit", "participant", "--group", "condition", "--outcome", "rt")
        self.assertEqual(report["design"], ["repeated"])
        self.assertEqual(report["route"]["row"], "continuous / 3+ groups")
        self.assertEqual(report["route"]["column"], "same unit measured again")

    def test_ids_reused_across_groups_are_named(self):
        rows = [(f"M{i}", diet, 4.5 + i) for diet in ("standard", "high_fat") for i in range(6)]
        rows += [(f"F{i}", "high_fibre", 4.25 + i) for i in range(6)]
        report = self.probe(self.table("mouse,diet,gain", rows), "--unit", "mouse", "--group", "diet", "--outcome", "gain")
        self.assertEqual(report["repeated"][0]["complete"], 0)
        self.assertIn("the same ids were probably given to different units", " ".join(report["notes"]))

    def test_replicates_are_not_units(self):
        rows = [(f"{g}{m}", g, c, 100 + m + c * 0.1) for g in ("WT", "KO") for m in range(4) for c in range(5)]
        report = self.probe(self.table("mouse,genotype,cell,area", rows),
                            "--unit", "mouse", "--group", "genotype", "--outcome", "area")
        self.assertEqual(report["design"], ["replicates"])
        self.assertEqual(report["replicates"], {"cells_with_several_rows": 8, "most_rows_per_cell": 5})
        self.assertEqual((report["n_per_group"]["WT"]["units"], report["n_per_group"]["WT"]["rows"]), (4, 20))
        self.assertIn("counts each row as an independent observation", self.ruled(report))
        self.assertIn("aggregate the rows", report["route"]["first"][0])

    def test_clusters_with_the_arm_assigned_per_cluster(self):
        rows = [(f"c{c}p{p}", f"clinic{c}", "treated" if c < 3 else "usual", round(50 + p + c * 0.5, 1))
                for c in range(6) for p in range(4)]
        report = self.probe(self.table("patient,clinic,arm,score", rows),
                            "--unit", "patient", "--cluster", "clinic", "--group", "arm", "--outcome", "score")
        self.assertEqual(report["design"], ["clustered"])
        self.assertEqual(report["clusters"]["clusters"], 6)
        self.assertTrue(report["clusters"]["group_constant_within_cluster"])
        self.assertIn("n is the number of clusters", report["route"]["first"][0])
        self.assertIn("same cluster as independent", self.ruled(report))

    def test_independent_units(self):
        rows = [(f"r{i}", "a" if i < 10 else "b", 3.5 + i) for i in range(20)]
        report = self.probe(self.table("id,group,y", rows), "--unit", "id", "--group", "group", "--outcome", "y")
        self.assertEqual(report["design"], ["independent"])
        self.assertEqual(report["ruled_out"], [])
        self.assertEqual(report["route"]["column"], "independent units")

    def test_no_unit_means_no_route(self):
        rows = [("a" if i < 10 else "b", 3.5 + i) for i in range(20)]
        report = self.probe(self.table("group,y", rows), "--group", "group", "--outcome", "y")
        self.assertEqual(report["design"], ["unit_not_declared"])
        self.assertIsNone(report["route"])
        self.assertEqual(report["ruled_out"][0]["method"], "every test")
        report = self.probe(self.table("group,y", rows), "--rows-are-units", "--group", "group", "--outcome", "y")
        self.assertEqual(report["design"], ["independent"])
        self.assertEqual(report["n_per_group"]["a"]["units"], 10)

    def test_sparse_cells_rule_out_chi_square(self):
        rows = [(f"u{i}", "drug", "yes" if i < 9 else "no") for i in range(10)]
        rows += [(f"v{i}", "control", "yes" if i < 2 else "no") for i in range(10)]
        report = self.probe(self.table("id,arm,responded", rows), "--unit", "id", "--group", "arm", "--outcome", "responded")
        self.assertEqual(report["outcome"]["type"], "binary")
        self.assertEqual(report["sparse_cells"]["cells_expected_under_5"], 2)
        self.assertIn("the chi-square test", self.ruled(report))
        self.assertIn("t tests, ANOVA and correlations on the category codes", self.ruled(report))
        self.assertEqual(report["route"]["row"], "binary / 2 groups")

    def test_outcome_types(self):
        cases = {"continuous": [1.25, 2.5, 3.75, 4.0], "count": [0, 3, 12, 25, 7, 40, 18, 2],
                 "ordinal": [1, 2, 3, 4, 5, 2, 3], "categorical": ["red", "green", "blue", "red"]}
        for expected, values in cases.items():
            self.assertEqual(pdz.outcome_type([str(v) for v in values], None)["type"], expected, expected)
        declared = pdz.outcome_type(["1", "2", "3"], "continuous")
        self.assertEqual((declared["type"], declared["declared"]), ("continuous", True))
        self.assertIn("look ordinal", declared["evidence"])

    def test_profile_from_the_figures_skill(self):
        data = self.table("subject,condition,latency_min",
                          [(f"S{i}", c, 10 + i + (c == "drug")) for i in range(6) for c in ("placebo", "drug")])
        profile = {"tool": "researchzy-figures", "file": {"path": str(data)}, "design": ["paired"],
                   "columns": [{"name": "subject", "role": "id", "role_from": "guess"},
                               {"name": "condition", "role": "group", "role_from": "user"},
                               {"name": "latency_min", "role": "measure", "role_from": "guess"}]}
        (self.dir / "trial.profile.json").write_text(json.dumps(profile), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            pdz.main(["--profile", str(self.dir / "trial.profile.json"), "--out", str(self.dir / "statistics")])
        report = json.loads(out.getvalue())
        self.assertEqual((report["columns"]["unit"], report["columns"]["group"]), ("subject", "condition"))
        self.assertEqual(report["design"], ["paired"])
        self.assertIn("--unit subject is a guess from the figures profile", " ".join(report["notes"]))

    def test_bad_input_exits_2(self):
        path = self.table("a,b", [(1, 2)])
        for argv in ([str(path), "--outcome", "nope"], [str(path), "--group", "a"], [str(self.dir / "none.csv"), "--outcome", "a"],
                     [str(path), "--outcome", "b", "--unit", "a", "--rows-are-units"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                pdz.main(argv + ["--out", str(self.dir / "statistics")])
            self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
