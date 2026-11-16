"""probe_causal.py: cohorts, timing, untreated periods, clusters against assignment, SC, RD, IV, weighting, the route."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_causal.py"
spec = importlib.util.spec_from_file_location("probe_causal", SCRIPT)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

HEADER = "county,state,year,policy,first_year,jobs"


def panel(cohorts, never, years=range(2010, 2016), per_state=2):
    """One row per county and year; cohorts maps an adoption year to its number of counties."""
    rows, i = [], 0
    for g, n in list(cohorts.items()) + [(None, never)]:
        for _ in range(n):
            for y in years:
                rows.append((f"C{i:02d}", f"S{i // per_state}", y, int(g is not None and y >= g), g or "", f"{50 + i:.1f}"))
            i += 1
    return rows


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def table(self, rows, header=HEADER, name="data.csv") -> Path:
        path = self.dir / name
        path.write_text("\n".join([header] + [",".join(str(v) for v in row) for row in rows]) + "\n", encoding="utf-8")
        return path

    def probe(self, path, *argv) -> dict:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(pc.main([str(path), "--out", str(self.dir / "causal"), *argv]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report, json.loads((self.dir / "causal" / f"{Path(path).stem}.design.json").read_text()))
        return report

    def did(self, rows, *argv):
        return self.probe(self.table(rows), "--design", "did", "--unit", "county", "--time", "year", "--treat", "policy",
                          "--outcome", "jobs", *argv)

    def test_staggered_adoption_routes_to_callaway_santanna(self):
        rows = panel({2012: 3, 2014: 3}, never=6)
        rows[0] = rows[0][:5] + ("not a number",)            # outcome values are never read, only missingness
        rows[1] = rows[1][:5] + ("",)
        report = self.did(rows)
        facts = report["facts"]
        self.assertEqual((facts["cohorts"], facts["never_treated"], facts["timing"]), ({"2012": 3, "2014": 3}, 6, "staggered"))
        self.assertEqual(report["missing"]["jobs"], 1)
        self.assertEqual(facts["untreated_per_period"]["2013"], 9)
        self.assertEqual(facts["untreated_per_period"]["2015"], 6)
        self.assertEqual((facts["event_times"]["min"], facts["event_times"]["max"]), (-4, 3))
        self.assertEqual((facts["event_times"]["cohorts_per_event_time"]["-3"],
                          facts["event_times"]["cohorts_per_event_time"]["-2"]), (1, 2))
        self.assertEqual(facts["control_groups"], ["never_treated", "not_yet_treated"])
        self.assertEqual(report["route"]["outcome"], "matched")
        self.assertEqual((report["route"]["design"], report["route"]["headline"], report["route"]["benchmark"]),
                         ("staggered_did", ["callaway_santanna"], ["twfe"]))
        clusters = report["clustering"]
        self.assertEqual((clusters["levels"]["county"]["G"], clusters["levels"]["county"]["G_treated"]), (12, 6))
        self.assertEqual(clusters["flags"], ["G = 12 <= 12", "treated G = 6 <= 6", "untreated G = 6 <= 6"])

    def test_one_adoption_date_is_a_2x2(self):
        report = self.did(panel({2013: 4}, never=4))
        self.assertEqual((report["facts"]["timing"], report["route"]["design"]), ("common", "did_2x2"))
        self.assertIn("twfe", report["route"]["headline"])

    def test_reversals_and_continuous_treatments_are_not_attempted(self):
        rows = panel({2012: 2}, never=2)
        rows[4] = rows[4][:3] + (0,) + rows[4][4:]             # C00 is treated in 2012, untreated again in 2014
        report = self.did(rows)
        self.assertEqual((report["route"]["outcome"], report["facts"]["reversals"]), ("not_attempted", 1))
        self.assertIn("turns on and off", report["route"]["why"][0])
        rows = [r[:3] + (r[3] * 2.5,) + r[4:] for r in panel({2012: 2}, never=2)]
        self.assertEqual(self.did(rows)["route"]["outcome"], "not_attempted")

    def test_duplicate_unit_periods_are_not_identifiable_yet(self):
        rows = panel({2012: 2}, never=2)
        report = self.did(rows + [rows[0]])
        self.assertEqual((report["route"]["outcome"], report["facts"]["duplicates"]["count"]), ("not_identifiable_yet", 1))

    def test_everyone_treated_eventually(self):
        report = self.did(panel({2012: 3, 2014: 3}, never=0))
        self.assertEqual(report["route"]["design"], "staggered_did")
        self.assertEqual(report["facts"]["periods_without_untreated"], [2014, 2015])
        self.assertEqual(report["facts"]["control_groups"], ["not_yet_treated"])
        self.assertIn("not identified there", " ".join(report["route"]["next"]))
        report = self.did(panel({2012: 3}, never=0))
        self.assertEqual(report["route"]["outcome"], "not_identifiable_yet")
        self.assertIn("no comparison group", report["route"]["why"][0])

    def test_always_treated_units_are_counted_and_dropped(self):
        report = self.did(panel({2010: 2, 2013: 2}, never=2))
        self.assertEqual((report["facts"]["always_treated"], report["facts"]["cohorts"]), (2, {"2013": 2}))
        self.assertIn("always-treated", " ".join(report["route"]["next"]))

    def test_clusters_finer_than_the_assignment_level(self):
        rows = panel({2012: 2, 2014: 2}, never=4)              # two counties per state share a cohort
        report = self.did(rows, "--assign", "state", "--cluster", "county")
        levels = report["clustering"]["levels"]
        self.assertTrue(report["clustering"]["finer_than_assignment"])
        self.assertFalse(levels["county"]["at_or_above_assignment"])
        self.assertTrue(levels["state"]["at_or_above_assignment"])
        self.assertEqual((levels["state"]["G"], levels["state"]["G_treated"]), (4, 2))
        self.assertIn("finer than the assignment level state", " ".join(report["route"]["next"]))
        hint = self.did(rows, "--cluster", "state")
        self.assertIn("run again with --assign state", " ".join(hint["route"]["next"]))
        self.assertFalse(hint["clustering"]["finer_than_assignment"])

    def test_treatment_varying_within_assignment_groups_is_ambiguous(self):
        rows = panel({2012: 1, 2014: 1}, never=2)              # one state holds a 2012 and a 2014 county
        report = self.did(rows, "--assign", "state")
        self.assertEqual(report["route"]["outcome"], "ambiguous")
        self.assertIn("at which level treatment was assigned", report["route"]["why"][0])

    def test_cohort_column_and_treatment_must_agree(self):
        rows = panel({2012: 2}, never=2)
        rows = [r[:4] + ((2013,) if r[0] == "C00" else (r[4],)) + r[5:] for r in rows]
        report = self.did(rows, "--cohort", "first_year")
        self.assertEqual((report["route"]["outcome"], report["facts"]["cohort_mismatch"]), ("ambiguous", 1))
        only = self.probe(self.table(panel({2012: 2, 2014: 1}, never=2)), "--design", "did", "--unit", "county",
                          "--time", "year", "--cohort", "first_year")
        self.assertEqual(only["facts"]["cohorts"], {"2012": 2, "2014": 1})

    def test_panel_design(self):
        rows = [(f"F{i}", "S", y, round(0.5 * i * (y - 2010), 2) if i else 1.5, "", 1) for i in range(5) for y in range(2010, 2014)]
        report = self.probe(self.table(rows), "--design", "panel", "--unit", "county", "--time", "year", "--treat", "policy")
        self.assertEqual((report["route"]["design"], report["route"]["headline"]), ("panel_fe", ["within"]))
        self.assertEqual(report["facts"]["units_without_within_variation"], 1)
        staggered = self.probe(self.table(panel({2012: 2, 2014: 2}, never=2)), "--design", "panel", "--unit", "county",
                               "--time", "year", "--treat", "policy")
        self.assertEqual(staggered["route"]["design"], "staggered_did")
        self.assertIn("this is difference-in-differences", staggered["route"]["next"][0])

    def test_synthetic_control(self):
        report = self.probe(self.table(panel({2013: 1}, never=5)), "--design", "sc", "--unit", "county", "--time",
                            "year", "--treat", "policy")
        self.assertEqual((report["route"]["design"], report["route"]["outcome"]), ("sc", "matched"))
        self.assertIn("1/(J+1) = 0.1667", report["route"]["next"][0])
        two = self.probe(self.table(panel({2013: 2}, never=5)), "--design", "sc", "--unit", "county", "--time", "year",
                         "--treat", "policy")
        self.assertEqual(two["route"]["outcome"], "ambiguous")
        few = self.probe(self.table(panel({2013: 1}, never=2)), "--design", "sc", "--unit", "county", "--time", "year",
                         "--treat", "policy")
        self.assertEqual(few["route"]["outcome"], "not_identifiable_yet")

    def test_regression_discontinuity(self):
        scores = [40 + i * 0.5 for i in range(40)] + [60.0] * 6 + [70, 75]
        rows = [(f"P{i}", s, int(s >= 55)) for i, s in enumerate(scores)]
        path = self.table(rows, header="pupil,score,admitted", name="exam.csv")
        argv = ("--design", "rd", "--running", "score", "--cutoff", "55", "--treat", "admitted", "--unit", "pupil")
        with mock.patch.object(pc, "find_spec", return_value=None):
            missing = self.probe(path, *argv)
        self.assertEqual(missing["route"]["outcome"], "not_attempted")
        self.assertIn("rdrobust and rddensity", missing["route"]["why"][0])
        with mock.patch.object(pc, "find_spec", return_value=object()):
            report = self.probe(path, *argv)
        facts = report["facts"]
        self.assertEqual((report["route"]["outcome"], report["route"]["headline"]), ("matched", ["rdrobust"]))
        self.assertEqual((facts["below"], facts["at_or_above"], facts["sharp"]), (30, 18, True))
        self.assertEqual(facts["binomial"][0], {"nearest": 20, "below": 10, "at_or_above": 10, "p": 1.0})
        self.assertEqual(facts["most_common_values"][0], {"value": 60, "count": 6, "share": 0.125})
        self.assertEqual(report["route"]["next"], [])
        discrete = self.table([(f"P{i}", 50 + i % 11, int(50 + i % 11 >= 55)) for i in range(66)],
                              header="pupil,score,admitted", name="discrete.csv")
        with mock.patch.object(pc, "find_spec", return_value=object()):
            report = self.probe(discrete, *argv)
        self.assertEqual(report["facts"]["distinct_values"]["all"], 11)
        self.assertIn("extrapolates between mass points", " ".join(report["route"]["next"]))

    def test_instrumental_variables(self):
        rows = [(i, z, int(i % 10 < (8 if z else 2)), f"{z}{i % 3}") for z in (0, 1) for i in range(20)]
        path = self.table(rows, header="id,lottery,attended,school", name="iv.csv")
        report = self.probe(path, "--design", "iv", "--instrument", "lottery", "--treat", "attended", "--cluster", "school",
                            "--assign", "school")
        share = report["facts"]["compliance"]
        self.assertEqual((share["treated_if_instrument_1"], share["treated_if_instrument_0"]), (0.8, 0.2))
        self.assertAlmostEqual(share["compliers"], 0.6)
        self.assertEqual((report["route"]["design"], report["route"]["headline"], report["route"]["benchmark"]),
                         ("iv", ["2sls"], ["ols"]))
        school = report["clustering"]["levels"]["school"]                # the lottery ran per school: 3 of 6 won
        self.assertEqual((school["G"], school["G_treated"], school["treatment_constant"]), (6, 3, True))
        flat = self.table([(i, 1, i % 2, 0) for i in range(10)], header="id,lottery,attended,school", name="flat.csv")
        self.assertEqual(self.probe(flat, "--design", "iv", "--instrument", "lottery", "--treat", "attended")
                         ["route"]["outcome"], "not_identifiable_yet")

    def test_weighting(self):
        rows = [(i, i % 2, 30 + i, "" if i == 3 else 2.5 * i) for i in range(12)]
        path = self.table(rows, header="id,program,age,income", name="w.csv")
        report = self.probe(path, "--design", "weighting", "--treat", "program", "--covariates", "age,income")
        self.assertEqual((report["route"]["design"], report["facts"]["treated"], report["facts"]["control"]),
                         ("weighting", 6, 6))
        self.assertEqual(report["facts"]["rows_missing_a_covariate"], 1)
        three = self.table([(i, i % 3, 30 + i, 1) for i in range(12)], header="id,program,age,income", name="w3.csv")
        self.assertEqual(self.probe(three, "--design", "weighting", "--treat", "program", "--covariates", "age")
                         ["route"]["outcome"], "not_attempted")

    def test_bad_input_exits_2(self):
        path = self.table(panel({2012: 1}, never=1))
        text_time = self.table([("C1", "S", "spring", 0, "", 1)], name="t.csv")
        rd = self.table([("P1", "high", 1)], header="pupil,score,admitted", name="rd.csv")
        for argv in ([str(path), "--design", "did", "--unit", "county", "--time", "year", "--treat", "nope"],
                     [str(path), "--design", "did", "--unit", "county", "--treat", "policy"],
                     [str(path), "--design", "did", "--unit", "county", "--time", "year"],
                     [str(self.dir / "none.csv"), "--design", "weighting", "--treat", "a", "--covariates", "b"],
                     [str(text_time), "--design", "did", "--unit", "county", "--time", "year", "--treat", "policy"],
                     [str(rd), "--design", "rd", "--running", "score", "--cutoff", "1"]):
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
                pc.main(argv + ["--out", str(self.dir / "causal")])
            self.assertEqual(caught.exception.code, 2, argv)


if __name__ == "__main__":
    unittest.main()
