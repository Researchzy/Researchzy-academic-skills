"""survey_audit.py: indicators on the raw answers, not_checked columns, exclusion rules written before the data,
and the planted data problems of the real task SV-1."""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import io
import json
import random
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "survey_audit.py"
spec = importlib.util.spec_from_file_location("survey_audit", SCRIPT)
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)

try:
    import openpyxl
except ImportError:
    openpyxl = None
try:
    import pandas
    import pyreadstat
except ImportError:
    pyreadstat = None

A, B, C = [f"A{i}" for i in range(1, 10)], [f"B{i}" for i in range(1, 11)], [f"C{i}" for i in range(1, 9)]
HEADER = ["编号", "作答时长（秒）", *A, *B[:5], "注意力题", *B[5:], "开放题：建议", *C]
WORDING = {"编号": "编号", "作答时长（秒）": "作答时长", "注意力题": "本题请选择“不同意”", "开放题：建议": "您对本单位有什么建议？"}
ITEM_WORDING = {"A": "我可以自己决定工作的方法", "B": "我的主管支持我的决定", "C": "我在工作中充满活力"}
TEXT_ROW = [WORDING[n] if n in WORDING else ITEM_WORDING[n[0]] for n in HEADER]
SETTINGS = {"header_row": 1, "skip_rows": [2], "id": "编号", "duration": {"column": "作答时长（秒）", "unit": "seconds"},
            "blocks": [{"name": "autonomy", "items": A, "scale": [1, 5]},
                       {"name": "support", "items": B, "scale": [1, 5], "reversed": ["B4", "B8"]},
                       {"name": "engagement", "items": C, "scale": [1, 5]}],
            "attention": [{"item": "注意力题", "expected": [2]}], "open_text": ["开放题：建议"], "fielding_start": "2026-03-01"}
# The planted problems of SV-1, by data row k (spreadsheet row k + 3: one header row, one row of question text).
STRAIGHT, FAST_TOO, FAST = range(0, 12), range(0, 3), range(12, 17)
WRONG, BLANK, CONSISTENT, SAME_TEXT, BREAK_OFF = range(17, 22), 22, range(23, 33), range(33, 37), range(150, 250)
REPEAT_ID, SAME_ANSWERS = {295: 40, 296: 41, 297: 42}, {298: 50, 299: 51}
OPEN = HEADER.index("开放题：建议")


def row_of(k: int) -> int:
    return k + 3


def sv1() -> list:
    """300 rows as the platform exported them, before any reverse scoring."""
    rnd = random.Random(20261118)

    def varied(n: int) -> list:
        while True:
            values = [rnd.randint(1, 5) for _ in range(n)]
            if len(set(values)) > 1:
                return values

    rows = []
    for k in range(300):
        a, b, c = varied(9), varied(10), varied(8)
        if k in STRAIGHT:
            b = [4] * 10                                          # one value throughout, B4 and B8 included
        if k in CONSISTENT:
            b = [1 if name in ("B4", "B8") else 5 for name in B]  # high on regular items, low on reversed ones
        if k in BREAK_OFF:
            c[7] = ""
        attention = "" if k == BLANK else 4 if k in WRONG else 2
        seconds = rnd.randint(60, 150) if k in FAST or k in FAST_TOO else rnd.randint(420, 900)
        text = "这个问卷设计得很好，我没有其他意见。" if k in SAME_TEXT else f"希望第{k}组增加培训和交流的机会"
        row = [f"R{REPEAT_ID.get(k, k):03d}", seconds, *a, *b[:5], attention, *b[5:], text, *c]
        if k in SAME_ANSWERS:                                      # another ID, the same answers to every item
            row = [f"R{k:03d}", seconds, *rows[SAME_ANSWERS[k]][2:]]
            row[OPEN] = f"希望第{k}组增加培训和交流的机会"
        rows.append(row)
    return rows


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "survey"
        self.out.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def export(self, rows, header=HEADER, text=TEXT_ROW, name="export.csv", encoding="utf-8", delimiter=",") -> Path:
        path = self.dir / name
        with path.open("w", encoding=encoding, newline="") as handle:
            writer = csv.writer(handle, delimiter=delimiter)
            writer.writerows([header] + ([text] if text else []) + rows)
        return path

    def settings(self, base=SETTINGS, **changes) -> Path:
        path = self.out / "audit-settings.json"
        path.write_text(json.dumps({**copy.deepcopy(base), **changes}, ensure_ascii=False), encoding="utf-8")
        return path

    def rules(self, rules: list, **fields) -> Path:
        path = self.out / "exclusion-rules.json"
        path.write_text(json.dumps({**fields, "rules": rules}, ensure_ascii=False), encoding="utf-8")
        return path

    def audit(self, data, *argv) -> dict:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(sa.main(["audit", str(data), "--out", str(self.out), *map(str, argv)]), 0)
        self.summary = json.loads(out.getvalue())
        return json.loads((self.out / "audit.json").read_text(encoding="utf-8"))

    def flags(self) -> dict:
        with (self.out / "flags.csv").open(encoding="utf-8-sig", newline="") as handle:
            return {int(r["row"]): r for r in csv.DictReader(handle)}

    def bad(self, *argv) -> str:
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            sa.main([str(a) for a in argv])
        self.assertEqual(stop.exception.code, 2)
        return err.getvalue()

    def sv1_audit(self, **changes) -> dict:
        self.settings(**changes)
        return self.audit(self.export(sv1()))


class SV1Tests(Base):
    def test_the_planted_data_problems_are_counted_and_nobody_is_excluded_without_rules(self):
        result = self.sv1_audit()
        ind = result["indicators"]
        self.assertEqual(result["counts"], {"received": 300, "excluded_a_priori": 0, "excluded_post_hoc": 0, "excluded_timing_not_known": 0,
                                            "undetermined": 0, "analysed": 300})
        self.assertEqual({f: ind[f]["flagged"] for f in ("straightline", "fast", "duplicate_id", "duplicate_answers",
                                                         "attention", "break_off", "open_text_identical")},
                         {"straightline": 12, "fast": 8, "duplicate_id": 3, "duplicate_answers": 2, "attention": 5,
                          "break_off": 100, "open_text_identical": 4})
        self.assertEqual(ind["attention"]["not_judged"], 1)                 # the blank answer is not a failure
        self.assertEqual(result["extra"]["attention_items"][0]["blank"], 1)
        self.assertIn("support (10 items, 2 reverse-keyed): 12", ind["straightline"]["detail"])
        self.assertEqual(result["extra"]["items_missing"], [{"item": "C8", "blank": 100, "share": 0.333}])
        self.assertEqual(result["extra"]["break_off_points"], {"C7": 100})
        self.assertEqual(result["extra"]["identical_open_text"][0]["rows"], [row_of(k) for k in SAME_TEXT])
        flags = self.flags()
        self.assertEqual({r for r, f in flags.items() if f["straightline"] == "1"}, {row_of(k) for k in STRAIGHT})
        self.assertEqual({r for r, f in flags.items() if f["fast"] == "1" and f["straightline"] == "1"}, {row_of(k) for k in FAST_TOO})
        self.assertEqual({row_of(k): flags[row_of(k)]["same_id_as"] for k in REPEAT_ID}, {row_of(k): str(row_of(v)) for k, v in REPEAT_ID.items()})
        self.assertEqual({row_of(k): flags[row_of(k)]["same_answers_as"] for k in SAME_ANSWERS},
                         {row_of(k): str(row_of(v)) for k, v in SAME_ANSWERS.items()})
        self.assertEqual(flags[row_of(BLANK)]["attention"], "")              # not judged, never 0
        self.assertEqual({f["excluded"] for f in flags.values()}, {"0"})
        report = (self.out / "data-quality.md").read_text(encoding="utf-8")
        self.assertIn("No exclusion rules were written, so nobody is excluded.", report)
        self.assertIn("| straightline | fast | 3 |", report)

    def test_consistent_respondents_are_not_straight_liners(self):
        self.sv1_audit()
        flags = self.flags()
        for k in CONSISTENT:
            self.assertEqual((flags[row_of(k)]["straightline"], flags[row_of(k)]["support_distinct"]), ("0", "2"), k)
        self.assertEqual(flags[row_of(0)]["support_distinct"], "1")

    def test_a_file_already_reverse_scored_is_undone_before_the_check(self):
        rows = sv1()
        for row in rows:                                                     # the user recoded B4 and B8 in the file
            for name in ("B4", "B8"):
                row[HEADER.index(name)] = 6 - int(row[HEADER.index(name)])
        self.settings(recoded=True)
        result = self.audit(self.export(rows))
        flags = self.flags()
        self.assertEqual(result["indicators"]["straightline"]["flagged"], 12)
        self.assertEqual({flags[row_of(k)]["straightline"] for k in CONSISTENT}, {"0"})

    def test_a_missing_ip_column_is_not_checked_and_never_passes(self):
        result = self.sv1_audit()
        self.assertEqual(result["indicators"]["duplicate_ip"], {"state": "not_checked", "detail": "no IP address column declared"})
        self.assertNotIn("duplicate_ip", next(iter(self.flags().values())))
        result = self.sv1_audit(ip="IP地址")
        self.assertEqual(result["indicators"]["duplicate_ip"]["detail"], "the IP address column IP地址 is not in the file")
        self.assertEqual(self.summary["columns_not_found"], ["IP地址"])
        self.rules([{"id": "R1", "when": ["duplicate_ip"]}], written="2026-02-20")
        result = self.audit(self.export(sv1()))
        self.assertEqual((result["rules"][0]["excluded"], result["rules"][0]["undetermined"]), (0, 300))
        self.assertEqual((result["counts"]["analysed"], result["counts"]["undetermined"]), (300, 300))
        self.assertIn("- duplicate_ip: the IP address column IP地址 is not in the file", (self.out / "data-quality.md").read_text(encoding="utf-8"))

    def test_the_data_is_only_read_and_its_hash_is_recorded(self):
        data = self.export(sv1())
        before = hashlib.sha256(data.read_bytes()).hexdigest()
        self.settings()
        result = self.audit(data)
        self.assertEqual((result["files"]["data"]["sha256"], hashlib.sha256(data.read_bytes()).hexdigest()), (before, before))
        self.assertEqual(len(result["files"]["settings"]["sha256"]), 64)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["audit-settings.json", "audit.json", "data-quality.md", "flags.csv"])
        report = (self.out / "data-quality.md").read_text(encoding="utf-8")
        for part in (before, "| straightline_min_items | 5 | default, a convention |", "| Rows received | 300 |",
                     "it cannot show who or what answered"):
            self.assertIn(part, report)
        self.assertIn("is one of this script's output files", self.bad("audit", self.out / "audit.json", "--out", self.out))


class RulesTests(Base):
    RULES = [{"id": "R1", "description": "failed the attention item", "when": ["attention"]},
             {"id": "R2", "when": ["fast", "straightline", "duplicate_answers", "open_text_identical"], "at_least": 2},
             {"id": "R3", "when": ["duplicate_id"]}]

    def test_rules_written_before_fielding_exclude_and_a_blank_attention_answer_stays_undecided(self):
        self.rules(self.RULES, written="2026-02-20", settings={"fast_share_of_median": 0.33})
        result = self.sv1_audit()
        self.assertEqual(result["counts"], {"received": 300, "excluded_a_priori": 11, "excluded_post_hoc": 0, "excluded_timing_not_known": 0,
                                            "undetermined": 1, "analysed": 289})
        self.assertEqual([(r["id"], r["status"], r["excluded"], r["undetermined"]) for r in result["rules"]],
                         [("R1", "a_priori", 5, 1), ("R2", "a_priori", 3, 0), ("R3", "a_priori", 3, 0)])
        flags = self.flags()
        self.assertEqual((flags[row_of(BLANK)]["excluded"], flags[row_of(BLANK)]["undetermined_by"]), ("", "R1"))
        self.assertEqual(flags[row_of(0)]["excluded_by"], "R2")
        self.assertEqual({flags[row_of(k)]["excluded"] for k in CONSISTENT}, {"0"})
        self.assertIn("| R2 | 2 of: fast; straightline; duplicate_answers; open_text_identical | 2026-02-20 | a_priori | 3 |",
                      (self.out / "data-quality.md").read_text(encoding="utf-8"))

    def test_rules_written_after_fielding_or_undated_are_post_hoc(self):
        rules = copy.deepcopy(self.RULES)
        rules[2]["written"] = "2026-04-02"
        self.rules(rules, written="2026-02-20")
        result = self.sv1_audit()
        self.assertEqual(result["rules"][2]["why"], ["written 2026-04-02, after fielding started on 2026-03-01"])
        self.assertEqual((result["counts"]["excluded_a_priori"], result["counts"]["excluded_post_hoc"]), (8, 3))
        self.rules(self.RULES)
        result = self.sv1_audit()
        self.assertEqual({(r["status"], tuple(r["why"])) for r in result["rules"]}, {("post_hoc", ("undated",))})

    def test_without_a_fielding_date_the_timing_of_dated_rules_is_not_known(self):
        self.rules(self.RULES, written="2026-02-20")
        base = {k: v for k, v in SETTINGS.items() if k != "fielding_start"}
        self.settings(base)
        result = self.audit(self.export(sv1()))
        self.assertTrue(result["fielding"].startswith("not known"))
        self.assertEqual({r["status"] for r in result["rules"]}, {"timing_not_known"})
        self.assertEqual((result["counts"]["excluded_a_priori"], result["counts"]["excluded_timing_not_known"]), (0, 11))

    def test_a_threshold_moved_after_the_rules_were_written_makes_them_post_hoc(self):
        self.rules(self.RULES, written="2026-02-20", settings={"fast_share_of_median": 0.33})
        result = self.sv1_audit(settings={"fast_share_of_median": {"value": 0.5, "source": "a methods paper the user read, p. 4",
                                                                   "date": "2026-04-03"}, "straightline_min_items": 4})
        self.assertEqual([r["status"] for r in result["rules"]], ["a_priori", "post_hoc", "a_priori"])
        self.assertEqual(result["rules"][1]["why"], ["straightline_min_items is 4 here and was 5 when the rules were written",
                                                     "fast_share_of_median is 0.5 here and was 0.33 when the rules were written"])
        self.assertEqual(result["settings"]["fast_share_of_median"]["default"], False)
        report = (self.out / "data-quality.md").read_text(encoding="utf-8")
        self.assertIn("| fast_share_of_median | 0.5 | audit-settings.json | a methods paper the user read, p. 4 | 2026-04-03 |", report)
        self.assertIn("| attention_fail_min | 1 | default, a convention |", report)

    def test_malformed_rules_stop(self):
        data = self.export(sv1())
        self.settings()
        for rule, message in ((["fast >= 2"], "is not a condition"), (["speed"], "is not a condition"),
                              (["missing_share"], "is not a condition"), (["automation"], "is not a condition")):
            self.rules([{"id": "R1", "when": rule}], written="2026-02-20")
            self.assertIn(message, self.bad("audit", data, "--out", self.out))
        self.rules([{"id": "R1", "when": ["fast", "slow"], "at_least": 3}], written="March 2026")
        message = self.bad("audit", data, "--out", self.out)
        self.assertIn("at_least must be a whole number", message)
        self.assertIn("written must be a date", message)
        self.assertIn("no rules file", self.bad("audit", data, "--out", self.out, "--rules", self.dir / "none.json"))


class ReaderTests(Base):
    SMALL = {"id": "编号", "duration": {"column": "用时", "unit": "seconds"}, "open_text": ["意见"],
             "blocks": [{"name": "满意度", "items": ["q1", "q2", "q3", "q4", "q5"], "scale": [1, 5]}],
             "missing": ["-99"], "value_labels": {"非常不同意": 1, "不同意": 2, "一般": 3, "同意": 4, "非常同意": 5},
             "fielding_start": "2026-03-01"}
    HEAD = ["编号", "用时", "q1", "q2", "q3", "q4", "q5", "意见"]
    ROWS = [["P1", "300秒", "非常同意", "非常同意", "非常同意", "非常同意", "非常同意", "第一行\n第二行：换行也是同一个回答"],
            ["P2", "420", "４", "2", "-99", "3", "5", "无"],
            ["P3", "380", "1", "2", "9", "4", "5", "希望增加带薪休假的天数"]]

    def test_quoted_cells_spanning_lines_chinese_encodings_and_semicolons(self):
        self.settings(self.SMALL)
        data = self.export(self.ROWS, header=self.HEAD, text=None, encoding="gb18030", delimiter=";")
        result = self.audit(data)
        self.assertEqual((result["files"]["data"]["encoding"], result["files"]["data"]["delimiter"]), ("gb18030", ";"))
        self.assertEqual(result["counts"]["received"], 3)
        flags = self.flags()
        self.assertEqual([flags[n]["id"] for n in sorted(flags)], ["P1", "P2", "P3"])
        self.assertEqual(flags[2]["duration_s"], "300.0")                     # "300秒"
        self.assertEqual(flags[2]["straightline"], "1")                       # labels read as numbers
        self.assertEqual((flags[3]["straightline"], flags[3]["满意度_distinct"]), ("", "4"))   # -99 is blank: 4 answers < 5
        self.assertEqual(flags[3]["open_text_short"], "1")
        self.assertEqual(result["extra"]["problems"], {"q3": {"out of range": 1}})

    def test_xlsx_and_sav_without_their_packages_are_not_checked(self):
        self.settings(self.SMALL)
        for name, package in (("export.xlsx", "openpyxl"), ("export.sav", "pyreadstat")):
            (self.dir / name).write_bytes(b"not read")
            with mock.patch.dict(sys.modules, {package: None}):
                result = self.audit(self.dir / name)
            self.assertEqual(self.summary["not_read"], f"{package} is not installed")
            self.assertEqual({i["state"] for i in result["indicators"].values()}, {"not_checked"})
            self.assertFalse((self.out / "flags.csv").exists())
            self.assertIn(f"The data file was not read: {package} is not installed.",
                          (self.out / "data-quality.md").read_text(encoding="utf-8"))

    @unittest.skipUnless(openpyxl, "openpyxl is not installed")
    def test_xlsx_with_two_header_rows(self):
        book = openpyxl.Workbook()
        for row in [self.HEAD, ["编号", "用时（秒）", "题1", "题2", "题3", "题4", "题5", "意见"], *self.ROWS]:
            book.active.append(row)
        book.save(self.dir / "export.xlsx")
        self.settings(self.SMALL, skip_rows=[2])
        result = self.audit(self.dir / "export.xlsx")
        self.assertEqual((result["files"]["data"]["format"], result["counts"]["received"]), ("xlsx", 3))
        self.assertEqual(self.flags()[3]["straightline"], "1")

    @unittest.skipUnless(pyreadstat, "pyreadstat and pandas are not installed")
    def test_sav(self):
        frame = pandas.DataFrame({"rid": ["S1", "S2", "S1"], "secs": [300.0, 20.0, 310.0], "q1": [3.0, 1.0, 2.0],
                                  "q2": [3.0, 2.0, 4.0], "q3": [3.0, 5.0, 1.0], "q4": [3.0, 4.0, 2.0], "q5": [3.0, 3.0, 5.0]})
        pyreadstat.write_sav(frame, str(self.dir / "export.sav"))
        self.settings({"id": "rid", "duration": {"column": "secs"}, "fielding_start": "2026-03-01",
                       "blocks": [{"name": "s", "items": ["q1", "q2", "q3", "q4", "q5"], "scale": [1, 5]}]})
        result = self.audit(self.dir / "export.sav")
        flags = self.flags()
        self.assertEqual((result["files"]["data"]["format"], flags[2]["straightline"], flags[4]["duplicate_id"]), ("sav", "1", "1"))

    def test_columns_lists_the_names_and_the_question_text_below(self):
        out = io.StringIO()
        with redirect_stdout(out):
            sa.main(["columns", str(self.export(sv1())), "--skip-rows", "2"])
        listing = json.loads(out.getvalue())
        found = {c["name"]: c for c in listing["columns"]}
        self.assertEqual((listing["rows"], listing["skipped_rows"]), (300, [2]))
        self.assertEqual((found["编号"]["looks_like"], found["作答时长（秒）"]["looks_like"], found["开放题：建议"]["looks_like"]),
                         ("id", "duration", "open_text"))
        self.assertEqual(found["注意力题"]["text_below"], "本题请选择“不同意”")


class IndicatorTests(Base):
    HEAD = ["id", "start", "end", "order", "p1", "p2", "p3", "q1", "q2", "q3", "q4", "q5", "q6"]
    CFG = {"id": "id", "duration": {"start": "start", "end": "end"},
           "page_times": {"columns": ["p1", "p2", "p3"], "kind": "timestamps"},
           "blocks": [{"name": "b", "items": ["q1", "q2", "q3", "q4", "q5", "q6"], "scale": [1, 5]}],
           "pairs": [{"items": ["q1", "q6"], "reversed": True, "max_difference": 0}]}

    def rows(self) -> list:
        day = "2026-03-02 10:{:02d}:00"
        out = [[f"u{k}", day.format(0), day.format(10 + k % 5), "q1|q3|q2|q4|q5|q6", day.format(1), day.format(3),
                day.format(6), 5, 2, 3, 4, 3, 1] for k in range(8)]
        out[0][2], out[0][6] = "2026-03-02 12:00:00", "2026-03-02 11:30:00"          # slow, and a pause of 87 minutes
        out[1][7:] = [2, 2, 5, 5, 5, 5]                                               # q1 = 2, q6 = 5, read as 1
        return out

    def test_pauses_slow_durations_from_timestamps_and_pairs(self):
        self.settings(self.CFG)
        result = self.audit(self.export(self.rows(), header=self.HEAD, text=None))
        flags = self.flags()
        self.assertEqual((flags[2]["slow"], flags[2]["pause"], flags[2]["longest_pause_s"], flags[3]["pause"]),
                         ("1", "1", "5220.0", "0"))
        self.assertEqual(flags[3]["duration_s"], "660.0")
        self.assertEqual((flags[3]["inconsistent"], flags[2]["inconsistent"]), ("1", "0"))     # q6 reversed before comparing
        self.assertIn("the earliest start time in the data", result["fielding"])

    def test_the_longest_run_needs_the_presentation_order(self):
        self.settings(self.CFG, settings={"long_run_min": 3})
        rows = self.rows()
        self.audit(self.export(rows, header=self.HEAD, text=None))
        self.assertEqual((self.flags()[3]["b_run"], self.flags()[3]["long_run"]), ("4", "1"))  # declared order: 2 2 5 5 5 5
        cfg = copy.deepcopy(self.CFG)
        cfg["blocks"][0]["randomised"] = True
        self.settings(cfg)
        result = self.audit(self.export(rows, header=self.HEAD, text=None))
        self.assertEqual(result["indicators"]["long_run"]["state"], "not_checked")
        cfg["blocks"][0]["order_column"] = "order"
        self.settings(cfg, settings={"long_run_min": 3})
        self.audit(self.export(rows, header=self.HEAD, text=None))
        self.assertEqual((self.flags()[3]["b_run"], self.flags()[3]["long_run"]), ("3", "1"))  # shown: 2 5 2 5 5 5

    def test_malformed_settings_stop(self):
        data = self.export(sv1())
        for change, message in (({"attenion": []}, "unknown key(s) attenion"), ({"settings": {"fast_share": 0.3}}, "must be an object of known settings"),
                                ({"settings": {"fast_share_of_median": "a third"}}, "must be a number of 0 or more, or null"),
                                ({"blocks": [{"name": "x", "items": ["A1"], "scale": [5, 1]}]}, "needs \"scale\": [lowest, highest]"),
                                ({"attention": [{"item": "注意力题"}]}, "needs \"item\" and \"expected\""),
                                ({"duration": {"column": "作答时长（秒）", "unit": "hours"}}, "duration needs")):
            self.settings(**change)
            self.assertIn(message, self.bad("audit", data, "--out", self.out))
        (self.out / "audit-settings.json").unlink()
        self.assertIn("no settings file", self.bad("audit", data, "--out", self.out))
        self.settings()
        self.assertIn("no such file", self.bad("audit", self.dir / "none.csv", "--out", self.out))


if __name__ == "__main__":
    unittest.main()
