"""probe_accuracy.py: the DA-1 data (patients in both splits, partial verification, two nodules per patient), the
corrected split, empty ids and splits, the reference values, dates, identical rows and events with Chinese headers and
values, separation by linear programming, and the exit codes."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).parent))
import da1_fixture  # noqa: E402


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pa = load("probe_accuracy", "probe_accuracy_under_test")
try:
    import scipy.optimize  # noqa: F401
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False

DA1 = ["--id", "patient_id", "--unit", "nodule_id", "--reference", "biopsy", "--positive", "1", "--index", "biomarker",
       "--threshold", str(da1_fixture.CUTOFF), "--split", "split", "--development", "development", "--test", "test",
       "--predictors", ",".join(da1_fixture.PREDICTORS), "--design", "consecutive"]


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def probe(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = pa.main(list(argv))
            except SystemExit as exc:                  # bad input ends the script with exit code 2
                code = exc.code
        return code, (json.loads(out.getvalue()) if out.getvalue() else None), err.getvalue()

    def csv(self, name, text):
        Path(name).write_text(text, encoding="utf-8")
        return name

    def test_da1_as_received(self):
        da1_fixture.write(Path("."))
        code, report, _ = self.probe("nodules.csv", *DA1)
        checks = report["checks"]
        self.assertEqual(code, 1)                                                  # planted problem 1
        self.assertEqual((checks["overlap"]["status"], checks["overlap"]["patients"]), ("problem", 31))
        self.assertEqual(report["leakage"]["status"], "problem")
        negative = checks["verification"]["by"]["test"]["index_negative"]          # planted problem 8
        self.assertEqual((negative["rows"], negative["missing"], negative["share"]), (181, 25, 0.1381))   # 14% of 181
        self.assertEqual(checks["verification"]["by"]["test"]["index_positive"]["missing"], 0)
        self.assertEqual(checks["verification"]["status"], "problem")
        repeated = checks["repeated_ids"]                                          # planted problem 10
        self.assertEqual((repeated["status"], repeated["patients"], repeated["units"], repeated["patients_with_several_rows"]),
                         ("problem", 450, 640, 190))
        counts = checks["splits"]["counts"]
        self.assertEqual((counts["development"]["units"], counts["test"]["units"]), (359, 281))
        self.assertEqual((checks["events"]["events"], checks["events"]["parameters"]), (49, 8))
        self.assertEqual(checks["index_missing"]["status"], "ok")
        self.assertNotIn("P0", json.dumps(report, ensure_ascii=False))             # patient ids are never printed
        self.assertEqual(json.loads(Path("diagnostic-accuracy/nodules.probe.json").read_text(encoding="utf-8")), report)

    def test_the_corrected_split_passes(self):
        rows = da1_fixture.rows()
        crossing = {r["patient_id"] for r in rows if r["split"] == "test"} & \
            {r["patient_id"] for r in rows if r["split"] == "development"}
        for r in rows:
            if r["patient_id"] in crossing:
                r["split"] = "development"
        da1_fixture.write(Path("."), table=rows)
        code, report, _ = self.probe("nodules.csv", *DA1)
        self.assertEqual((code, report["checks"]["overlap"]["status"], report["leakage"]["status"]), (0, "ok", "ok"))
        self.assertEqual(report["checks"]["identical_rows"]["status"], "ok")

    def test_empty_ids_and_splits_are_counted_not_skipped(self):
        self.csv("t.csv", "pid,y,split\n1,1,dev\n2,0,dev\n,1,test\n4,0,\n5,1,test\n6,0,test\n")
        code, report, _ = self.probe("t.csv", "--id", "pid", "--reference", "y", "--positive", "1", "--split", "split")
        overlap = report["checks"]["overlap"]
        self.assertEqual(code, 0)                                                  # no patient crosses
        self.assertEqual((overlap["status"], overlap["empty_id_rows"]["rows"], overlap["empty_split_rows"]["rows"]),
                         ("problem", [4], [5]))
        self.assertEqual(report["leakage"]["status"], "problem")
        self.assertIn("(empty)", report["checks"]["splits"]["counts"])

    def test_the_reference_standard_must_have_two_values_one_positive(self):
        self.csv("t.csv", "pid,y\n1,benign\n2,benign\n3,malignant\n")
        self.assertEqual(self.probe("t.csv", "--id", "pid", "--reference", "y", "--positive", "malignant")[0], 0)
        code, report, _ = self.probe("t.csv", "--id", "pid", "--reference", "y", "--positive", "cancer")
        self.assertEqual((code, report["checks"]["reference"]["status"]), (1, "problem"))
        self.csv("t.csv", "pid,y\n1,benign\n2,borderline\n3,malignant\n")
        code, report, _ = self.probe("t.csv", "--id", "pid", "--reference", "y", "--positive", "malignant")
        self.assertEqual(code, 1)
        self.assertIn("multiclass", report["checks"]["reference"]["reason"])

    def test_chinese_values_dates_identical_rows_and_events(self):
        self.csv("t.csv", "病人编号,活检,划分,日期,年龄,吸烟\n"
                          "A1,恶性,开发,2019年3月5日,６１,是\nA2,良性,开发,2019/7/1,55,否\nA3,良性,开发,2021-06-20,48,戒烟\n"
                          "A4,恶性,开发,2019-02-11,70,是\nB1,良性,测试,2021年6月1日,48,戒烟\nB2,恶性,测试,2021-08-09,66,是\n"
                          "B3,良性,测试,2021-12-30,52,否\n")
        code, report, _ = self.probe("t.csv", "--id", "病人编号", "--reference", "活检", "--positive", "恶性", "--split",
                                     "划分", "--development", "开发", "--test", "测试", "--date", "日期",
                                     "--predictors", "年龄,吸烟")
        checks = report["checks"]
        self.assertEqual(code, 0)
        self.assertEqual(checks["reference"]["counts"], {"positive": 3, "negative": 4})
        self.assertEqual((checks["date_order"]["status"], checks["date_order"]["late"]["rows"]), ("problem", [4]))
        self.assertEqual(checks["date_order"]["development"], "2019-02-11 to 2021-06-20")
        self.assertEqual(report["leakage"]["status"], "problem")
        self.assertEqual((checks["identical_rows"]["status"], checks["identical_rows"]["rows"]), ("problem", [4, 6]))
        self.assertEqual((checks["events"]["events"], checks["events"]["parameters"]), (2, 3))     # 年龄 1, 吸烟 3 - 1
        self.assertEqual(checks["events"]["categorical"], {"吸烟": 3})

    def test_a_temporal_split_in_order(self):
        self.csv("t.csv", "pid,y,split,date\n1,1,dev,2020-01-05\n2,0,dev,2020-03-01\n3,1,test,2021-01-02\n4,0,test,2021-02-03\n")
        argv = ["--id", "pid", "--reference", "y", "--positive", "1", "--split", "split", "--development", "dev", "--test",
                "test", "--date", "date"]
        code, report, _ = self.probe("t.csv", *argv)
        self.assertEqual((code, report["checks"]["date_order"]["status"], report["leakage"]["status"]), (0, "ok", "ok"))
        self.csv("t.csv", "pid,y,split,date\n1,1,dev,2020-01-05\n2,0,dev,soon\n3,1,test,2021-01-02\n4,0,test,2021-02-03\n")
        report = self.probe("t.csv", *argv)[1]
        self.assertIn("could not be read", report["checks"]["date_order"]["reason"])

    @unittest.skipUnless(HAVE_SCIPY, "scipy is not installed")
    def test_separation_by_linear_programming(self):
        cases = {"complete": "pid,y,x\n1,1,2.0\n2,1,1.5\n3,1,0.5\n4,0,-0.5\n5,0,-1.0\n6,0,-2.0\n",
                 "quasi-complete": "pid,y,x\n1,1,2.0\n2,1,0.0\n3,1,0.5\n4,0,0.0\n5,0,-1.0\n6,0,-2.0\n",
                 None: "pid,y,x\n1,1,2.0\n2,1,-1.0\n3,1,0.5\n4,0,1.0\n5,0,-1.5\n6,0,0.2\n"}
        for kind, text in cases.items():
            self.csv("t.csv", text)
            check = self.probe("t.csv", "--id", "pid", "--reference", "y", "--positive", "1", "--predictors", "x")[1][
                "checks"]["separation"]
            self.assertEqual((check["status"], check.get("kind")), ("problem" if kind else "ok", kind), kind)

    @unittest.skipIf(HAVE_SCIPY, "scipy is installed")
    def test_separation_without_scipy_is_not_checked(self):
        self.csv("t.csv", "pid,y,x\n1,1,2.0\n2,0,-1.0\n3,1,0.5\n4,0,1.0\n")
        check = self.probe("t.csv", "--id", "pid", "--reference", "y", "--positive", "1", "--predictors", "x")[1]["checks"]
        self.assertEqual(check["separation"]["status"], "not_checked")
        self.assertIn("scipy", check["separation"]["reason"])

    def test_bad_input_exits_2(self):
        self.csv("t.csv", "pid,y,score\n1,1,3\n2,0,1\n")
        base = ["--id", "pid", "--reference", "y", "--positive", "1"]
        for argv in (["missing.csv", *base], ["t.csv", *base, "--index", "nope"], ["t.csv", *base, "--threshold", "2"],
                     ["t.csv", *base, "--index", "score", "--threshold", "2", "--index-positive", "1"],
                     ["t.csv", *base, "--date", "score"]):
            code, _, err = self.probe(*argv)
            self.assertEqual(code, 2, argv)
            self.assertTrue(err.startswith("probe_accuracy: "), err)


if __name__ == "__main__":
    unittest.main()
