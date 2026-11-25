"""probe_survival.py: event codes, times, ties, ids, groups, complete cases, parameters, follow-up, time zero, route.

su1_rows() builds the retrospective cohort of the skill's real task: status 1 = censored and 2 = died, times in whole
days at monthly visits, two negative and four zero times, three patients entered twice, seven missing ecog values,
adjuvant treatment that starts up to six months after diagnosis, and a surgery arm that stays above 0.5.
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import math
import random
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_survival.py"
spec = importlib.util.spec_from_file_location("probe_survival", SCRIPT)
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)

HEADER = ["patient_id", "days", "status", "arm", "age", "sex", "stage", "ecog", "adjuvant", "smoking", "histology",
          "bmi", "albumin", "weight_loss", "charlson", "diagnosis_date", "adjuvant_start"]
COVARIATES = "age,sex,stage,ecog,adjuvant,smoking,histology,bmi,albumin,weight_loss,charlson"


def su1_rows(seed=20261118, n=180):
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        arm = "surgery" if i % 2 == 0 else "chemoradiation"
        stage = "I II III IV".split()[int(rnd.random() * 4)]
        rate = (0.00006 if arm == "surgery" else 0.00022) * (1.6 if stage in ("III", "IV") else 1.0)
        died_at = -math.log(1 - rnd.random()) / rate
        last = 100 + 2400 * rnd.random()
        days, status = (died_at, 2) if died_at <= last else (last, 1)
        days = int(round(days / 30) * 30) or 30
        diagnosed = date(2015, 1, 1) + timedelta(days=int(1500 * rnd.random()))
        adjuvant = "yes" if arm == "surgery" and rnd.random() < 0.45 else "no"
        rows.append({"patient_id": f"P{i + 1:03d}", "days": days, "status": status, "arm": arm,
                     "age": round(45 + 35 * rnd.random()), "sex": "F" if rnd.random() < 0.45 else "M", "stage": stage,
                     "ecog": int(rnd.random() * 4), "adjuvant": adjuvant,
                     "smoking": "never former current".split()[int(rnd.random() * 3)],
                     "histology": "squamous" if rnd.random() < 0.6 else "adeno", "bmi": round(19 + 12 * rnd.random(), 1),
                     "albumin": round(30 + 15 * rnd.random(), 1), "weight_loss": "yes" if rnd.random() < 0.3 else "no",
                     "charlson": int(rnd.random() * 5), "diagnosis_date": diagnosed.isoformat(),
                     "adjuvant_start": (diagnosed + timedelta(days=30 + int(150 * rnd.random()))).isoformat()
                     if adjuvant == "yes" else ""})
    for i, value in zip((10, 41), (-12, -3)):
        rows[i]["days"] = value
    for i in (5, 66, 97, 150):
        rows[i]["days"] = 0
    for i in (3, 20, 33, 47, 88, 120, 171):
        rows[i]["ecog"] = ""
    return rows + [dict(rows[i]) for i in (7, 70, 133)]


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def table(self, rows: list, name: str = "cohort.csv", header=None) -> Path:
        path = self.dir / name
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, header or list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return path

    def probe(self, path, *argv, code=0) -> dict:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(ps.main([str(path), "--out", str(self.dir / "survival"), *argv]), code)
        report = json.loads(out.getvalue())
        self.assertEqual(report, json.loads((self.dir / "survival" / f"{Path(path).stem}.probe.json").read_text("utf-8")))
        return report

    def su1(self, *argv, code=1) -> dict:
        return self.probe(self.table(su1_rows(), header=HEADER), "--time", "days", "--event", "status", "--group", "arm",
                          "--id", "patient_id", "--covariates", COVARIATES, "--categorical", "stage,ecog", *argv, code=code)

    def test_codes_one_and_two_are_never_guessed(self):
        report = self.su1()
        checks = report["checks"]
        self.assertEqual(checks["event_codes"]["status"], "problem")
        self.assertIn("codes 1, 2 have no meaning yet", checks["event_codes"]["detail"])
        self.assertIn("only the user can say", checks["event_codes"]["detail"])
        self.assertEqual(checks["event_codes"]["codes"]["2"]["means"], None)
        for name in ("ties", "groups", "followup", "parameters"):
            self.assertEqual(checks[name]["status"], "not_checked", name)
        self.assertEqual(checks["parameters"]["parameters"], 17)
        self.assertEqual(checks["time_unit"]["status"], "not_checked")
        self.assertEqual(report["route"]["route"], "stop_and_ask")
        self.assertTrue(any(why.startswith("event_codes") for why in report["route"]["why"]))

    def test_the_planted_problems_of_the_cohort(self):
        report = self.su1("--time-unit", "days", "--map", "1=0,2=1", "--zero-date", "diagnosis_date",
                          "--known-date", "adjuvant=adjuvant_start", "--known-at-zero", "arm")
        checks = report["checks"]
        self.assertEqual(checks["event_codes"]["status"], "ok")
        self.assertEqual(checks["times"]["negative_time"], [11, 42])
        self.assertEqual(checks["times"]["zero_time"], [6, 67, 98, 151])
        self.assertIn("never drop them silently", checks["times"]["detail"])
        self.assertEqual((checks["ids"]["status"], checks["ids"]["repeated_ids"]), ("problem", 3))
        self.assertIn("rows 8, 71, 134, 181, 182, 183", checks["ids"]["detail"])
        self.assertIn("in 3 of them the rows are identical: duplicates", checks["ids"]["detail"])
        self.assertEqual(checks["complete_cases"]["missing"]["ecog"], 7)
        self.assertIn("ecog 7 (rows 4, 21, 34, 48, 89, 121, 172)", checks["complete_cases"]["detail"])
        self.assertEqual((checks["parameters"]["events"], checks["parameters"]["parameters"]), (38, 17))
        self.assertEqual(checks["parameters"]["per_variable"]["stage"], 3)
        self.assertIn("not a pass mark", checks["parameters"]["detail"])
        self.assertGreater(checks["ties"]["events_at_shared_times"], 10)
        self.assertIn("Efron", checks["ties"]["detail"])
        surgery = checks["followup"]["groups"]["surgery"]
        self.assertFalse(surgery["below_half"])
        self.assertTrue(checks["followup"]["groups"]["chemoradiation"]["below_half"])
        self.assertIn("surgery: the Kaplan-Meier estimate stays at", checks["followup"]["detail"])
        adjuvant = checks["time_zero"]["variables"]["adjuvant"]
        self.assertEqual((adjuvant["status"], adjuvant["late"], adjuvant["longest_days"]), ("problem", 44, 179))
        self.assertEqual(checks["time_zero"]["variables"]["arm"]["status"], "ok")
        self.assertEqual(report["route"], {"route": "stop_and_ask", "why": report["route"]["why"],
                                           "then": "landmark_or_start_stop"})
        self.assertEqual([why.split(":")[0] for why in report["route"]["why"]], ["times", "ids"])

    def test_no_value_of_a_row_is_printed(self):
        text = json.dumps(self.su1("--time-unit", "days", "--map", "1=0,2=1", "--zero-date", "diagnosis_date",
                                   "--known-date", "adjuvant=adjuvant_start"))
        for value in ("P008", "P071", "2015-", "2016-", "adeno"):
            self.assertNotIn(value, text)

    def test_a_clean_cohort_takes_the_standard_route(self):
        rows = [r for r in su1_rows()[:180] if r["days"] > 0 and r["ecog"] != ""]
        report = self.probe(self.table(rows, header=HEADER), "--time", "days", "--event", "status", "--map", "1=0,2=1",
                            "--time-unit", "days", "--group", "arm", "--id", "patient_id", "--covariates", "age,ecog",
                            "--known-at-zero", "arm")
        self.assertEqual(report["route"], {"route": "standard", "why": []})
        self.assertEqual({c["status"] for c in report["checks"].values()}, {"ok"})
        self.assertEqual(report["checks"]["groups"]["counts"]["arm=surgery"]["events"], 5)

    def test_start_stop_rows(self):
        rows = [{"id": "A", "start": 0, "stop": 100, "event": 0, "adjuvant": "no"},
                {"id": "A", "start": 100, "stop": 400, "event": 1, "adjuvant": "yes"},
                {"id": "B", "start": 0, "stop": 250, "event": 1, "adjuvant": "no"},
                {"id": "C", "start": 0, "stop": 300, "event": 0, "adjuvant": "no"}]
        argv = ("--time", "stop", "--start", "start", "--event", "event", "--id", "id", "--time-unit", "days")
        report = self.probe(self.table(rows), *argv)
        self.assertEqual((report["checks"]["ids"]["status"], report["route"]["route"]), ("ok", "start_stop"))
        rows[1]["start"] = 50
        report = self.probe(self.table(rows), *argv, code=1)
        self.assertIn("intervals of the same id overlap (rows 1, 2)", report["checks"]["ids"]["detail"])
        rows[1]["start"] = 500
        report = self.probe(self.table(rows), *argv)                             # a problem that stops, not exit 1
        self.assertEqual(report["checks"]["times"]["start_time_missing,_negative_or_not_before_the_time"], [2])
        self.assertEqual(report["route"]["route"], "stop_and_ask")

    def test_competing_events_route(self):
        rows = [{"months": m, "status": s, "arm": "AB"[i % 2]} for i, (m, s) in
                enumerate(((3, 1), (5, 2), (8, 0), (9, 1), (12, 2), (14, 0), (15, 1), (20, 0)))]
        report = self.probe(self.table(rows), "--time", "months", "--event", "status", "--time-unit", "months",
                            "--map", "0=0", "--map", "1=1", "--map", "2=2", "--group", "arm", "--known-at-zero", "arm")
        self.assertEqual(report["route"]["route"], "competing_risks")
        self.assertEqual(report["checks"]["groups"]["counts"]["arm=A"],
                         {"rows": 4, "events": 2, "competing": 1, "censored": 1})
        self.assertIn("any event", report["checks"]["followup"]["method"])

    def test_words_and_unmapped_codes(self):
        rows = [{"t": t, "outcome": o} for t, o in ((3, "dead"), (5, "alive"), (8, "dead"), (9, "alive"))]
        report = self.probe(self.table(rows), "--time", "t", "--event", "outcome", "--time-unit", "weeks", code=1)
        self.assertIn("codes alive, dead have no meaning yet", report["checks"]["event_codes"]["detail"])
        report = self.probe(self.table(rows), "--time", "t", "--event", "outcome", "--time-unit", "weeks",
                            "--map", "alive=0,dead=1")
        self.assertEqual(report["route"]["route"], "standard")

    def test_chinese_headers_and_labels(self):
        path = self.dir / "队列.csv"
        path.write_bytes("﻿生存天数,状态,组别\n30,1,手术\n60,0,放化疗\n90,1,放化疗\n120,0,手术\n".encode("utf-8"))
        report = self.probe(path, "--time", "生存天数", "--event", "状态", "--group", "组别", "--time-unit", "天",
                            "--known-at-zero", "组别")
        self.assertEqual(sorted(report["checks"]["followup"]["groups"]), ["手术", "放化疗"])
        self.assertEqual(report["route"]["route"], "standard")
        self.assertEqual(report["checks"]["time_unit"]["detail"], "天, as the user said")

    def test_unreadable_input(self):
        path = self.table([{"t": 1, "e": 1}])
        for argv in ([str(self.dir / "absent.csv"), "--time", "t", "--event", "e"],
                     [str(path), "--time", "time", "--event", "e"],
                     [str(path), "--time", "t", "--event", "e", "--map", "1=x"],
                     [str(path), "--time", "t", "--event", "e", "--known-date", "arm"]):
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
                ps.main(argv + ["--out", str(self.dir / "survival")])
            self.assertEqual(caught.exception.code, 2, argv)


if __name__ == "__main__":
    unittest.main()
