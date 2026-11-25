"""item_screen.py: wording candidates in Chinese and English, scales without source or permission, the design
problems of the real task SV-1, and words that only look like a problem."""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "item_screen.py"
spec = importlib.util.spec_from_file_location("item_screen", SCRIPT)
its = importlib.util.module_from_spec(spec)
spec.loader.exec_module(its)

# SV-1: three constructs measured in one sitting, the support scale "from a 2004 paper" with unknown permission
# and its wording typed in, predictor and outcome in one block, no marker variable, no exclusion rules yet.
SV1 = [["构念", "题项编号", "题项文字", "方向", "出处", "授权", "改动", "区块", "角色", "期望答案"],
       ["自主性", "A1", "我可以自己决定工作的方法和时间安排", "正向", "用户自编", "开放", "", "第一页", "自变量", ""],
       ["自主性", "A2", "难道你不认为自主安排工作能提高效率吗", "正向", "用户自编", "开放", "", "第一页", "自变量", ""],
       ["自主性", "A3", "我的工作环境非常和谐", "正向", "用户自编", "开放", "", "第一页", "自变量", ""],
       ["自主性", "A4", "我参与部门的决策", "正向", "用户自编", "开放", "", "第一页", "自变量", ""],
       ["支持", "B1", "My supervisor listens to me and gives useful feedback.", "forward", "a 2004 paper", "unknown", "",
        "第一页", "因变量", ""],
       ["支持", "B2", "I do not think that my supervisor never helps me.", "forward", "a 2004 paper", "unknown", "", "第一页", "因变量", ""],
       ["支持", "B3", "我的主管并非不关心我的发展", "反向", "a 2004 paper", "unknown", "", "第一页", "因变量", ""],
       ["投入", "C1", "我总是对工作充满热情", "正向", "用户自编", "开放", "", "第一页", "因变量", ""],
       ["投入", "C2", "我知道是否需要加班", "正向", "用户自编", "开放", "", "第一页", "因变量", ""],
       ["注意力", "ATT", "本题请选择“不同意”", "", "", "", "", "第一页", "注意力", "2"]]


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "survey"
        self.dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def screen(self, rows, *argv) -> dict:
        path = self.dir / "items.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(rows)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(its.main([str(path), *argv]), 0)
        result = json.loads(out.getvalue())
        result["pairs"] = {(c["check"], c["subject"]) for c in result["candidates"]}
        return result

    def test_the_design_problems_of_sv1_are_listed(self):
        result = self.screen(SV1)
        for pair in (("conjunction", "A1"), ("conjunction", "B1"),                       # two double-barrelled items
                     ("leading", "A2"),                                                   # one leading item
                     ("double_negation", "B2"), ("double_negation", "B3"),               # 并非不, not ... never
                     ("absolute", "C1"), ("few_items", "投入"),
                     ("source_without_page", "支持"), ("permission_unknown", "支持"), ("text_without_permission", "支持"),
                     ("predictor_outcome_same_block", "第一页"), ("one_wave", "questionnaire"),
                     ("no_marker", "questionnaire"), ("no_exclusion_rules", "questionnaire")):
            self.assertIn(pair, result["pairs"])
        self.assertNotIn(("no_attention", "questionnaire"), result["pairs"])
        self.assertNotIn(("attention_without_expected", "ATT"), result["pairs"])
        self.assertNotIn("ATT", {s for _, s in result["pairs"]})                         # an attention item is not reworded
        report = (self.dir / "item-screen.md").read_text(encoding="utf-8")
        self.assertIn("| conjunction | A1 | 自主性 | words: 和 |", report)
        self.assertIn("| double_negation | B3 | 支持 | words: 非, 不 |", report)

    def test_words_that_only_look_like_problems_are_left_alone(self):
        result = self.screen(SV1)
        for item in ("A3", "A4", "C2"):                       # 非常, 和谐, 参与, 是否
            self.assertNotIn(item, {s for _, s in result["pairs"]}, item)
        self.assertNotIn(("source_without_page", "自主性"), result["pairs"])   # the user's own items have no page

    def test_a_well_formed_design_and_the_limits(self):
        rows = [["construct", "item_id", "text", "keying", "source", "permission", "changes", "block", "role", "wave", "expected"]]
        rows += [["climate", f"K{i}", "People here share information freely", "forward", "Author (2019), Table 3, p. 210",
                  "open", "", "page 1", "predictor", "1", ""] for i in range(1, 12)]
        rows += [["burnout", "U1", "I feel tired at the end of a working day", "", "Author (2020), p. 5", "licensed",
                  "anchors changed from 7 to 5 points", "page 2", "outcome", "2", ""],
                 ["marker", "M1", "I like the colour blue", "forward", "user's own", "open", "", "page 2", "marker", "2", ""],
                 ["check", "AC1", "Select 'agree' for this row", "", "", "", "", "page 2", "attention", "2", ""]]
        (self.dir / "exclusion-rules.json").write_text("{}", encoding="utf-8")
        result = self.screen(rows, "--max-block", "10")
        self.assertEqual(result["pairs"], {("long_block", "page 1"), ("few_items", "burnout"), ("keying", "U1"),
                                           ("modified", "U1"), ("attention_without_expected", "AC1")})
        self.assertEqual(result["limits"], {"max_words": 20, "max_han": 30, "min_items": 3, "max_block": 10})
        long_text = "I would describe the way that people in my team share what they know with each other as open and generous"
        rows[1][2] = long_text
        self.assertIn(("long", "K1"), self.screen(rows)["pairs"])

    def test_missing_columns_are_not_checked_and_a_table_without_ids_stops(self):
        result = self.screen([["构念", "题项编号", "题项文字"], ["自主性", "A1", "我能决定工作方法"]])
        self.assertIn("attention, marker and predictor-outcome checks: no role column", result["not_checked"])
        self.assertIn("permission_unknown: no permission column", result["not_checked"])
        path = self.dir / "bad.csv"
        path.write_text("text\nOnly wording\n", encoding="utf-8")
        with redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as stop:
            its.main([str(path)])
        self.assertEqual(stop.exception.code, 2)
        self.assertIn("needs the columns construct and item_id", err.getvalue())


if __name__ == "__main__":
    unittest.main()
