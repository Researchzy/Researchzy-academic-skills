"""protocol_check.py: the three documents against core.json, definitions against their sources, the amendment log.

The documents are invented and carry the planted problems of task PR-1: the primary time point as 12 weeks,
3 months and 6 months; 120 randomised against 100; adverse events missing from the registry draft; a
responder cutoff without a source; diagnostic criteria named without their document.
"""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "protocol_check.py"
spec = importlib.util.spec_from_file_location("protocol_check", SCRIPT)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

CORE = {
    "study": "Supervised exercise versus usual care for knee osteoarthritis (invented)",
    "outcomes": [
        {"id": "O1", "role": "primary", "measure": "Knee pain, WOMAC pain subscale", "key_terms": ["WOMAC", "pain|疼痛"],
         "timepoints": ["12 weeks"]},
        {"id": "O2", "role": "secondary", "measure": "Function, WOMAC function subscale", "key_terms": ["function|功能"],
         "timepoints": ["12 weeks", "26 weeks"]},
        {"id": "O3", "role": "secondary", "measure": "Adverse events", "key_terms": ["adverse|不良"], "timepoints": [],
         "documents": ["protocol", "registry"]},
    ],
    "numbers": [
        {"id": "randomised", "label": "participants randomised", "value": 120,
         "from": {"file": "statistics/power.json", "key": "inflation.n_total"}},
        {"id": "per_arm", "label": "randomised per arm", "value": 60, "documents": ["protocol", "sap"],
         "from": {"file": "statistics/power.json", "key": "inflation.n_per_group.0"}},
        {"id": "analysed_pp", "label": "analysed per protocol", "value": 110, "documents": ["sap"],
         "from": {"stated_by": "user", "note": "expected completers, user's message"}},
    ],
    "texts": [{"id": "population", "label": "primary analysis population", "documents": ["protocol", "sap"],
               "text": "all randomised participants, analysed in the arm to which they were assigned"}],
}
POWER = {"result": {"n_per_group": [54, 54], "n_total": 108}, "inflation": {"attrition": 0.1, "n_per_group": [60, 60], "n_total": 120}}
PROTOCOL = """# Supervised exercise for knee osteoarthritis

## 6 Outcomes

### 6.1 Primary outcome

The primary outcome is knee pain on the WOMAC pain subscale at 12 weeks.

### 6.2 Secondary outcomes

Function on the WOMAC function subscale at 12 and 26 weeks. Adverse events are recorded at every visit.

## 8 Sample size

We will randomise 120 participants, 60 per arm. [Evidence needed: source of the expected effect]

## 9 Statistical methods

The primary analysis includes all randomised participants, analysed in the arm to which they were assigned.
"""
REGISTRY = """# Registry draft

| Field | Entry |
|---|---|
| Primary outcome | Knee pain (WOMAC pain subscale) at 6 months |
| Secondary outcome | WOMAC function subscale, weeks 12 and 26 |
| Target sample size | 100 |
"""
SAP = """# Statistical analysis plan

## 2 Outcomes

Primary outcome: WOMAC pain subscale at 3 months.

Secondary outcome: WOMAC function subscale at week 12 and week 26.

## 3 Populations

Primary analysis population: all randomised participants, analysed in the arm to which they were assigned.
120 participants will be randomised, 60 per arm; we expect 110 to be analysed per protocol.
"""
LOCATIONS = {
    "O1": {"protocol": {"quote": "The primary outcome is knee pain on the WOMAC pain subscale at 12 weeks", "locator": "6.1"},
           "registry": {"quote": "Knee pain (WOMAC pain subscale) at 6 months", "locator": "Primary outcome"},
           "sap": {"quote": "Primary outcome: WOMAC pain subscale at 3 months", "locator": "2"}},
    "O2": {"protocol": {"quote": "Function on the WOMAC function subscale at 12 and 26 weeks"},
           "registry": {"quote": "WOMAC function subscale, weeks 12 and 26"},
           "sap": {"quote": "Secondary outcome: WOMAC function subscale at week 12 and week 26"}},
    "O3": {"protocol": {"quote": "Adverse events are recorded at every visit"}},
    "randomised": {"protocol": {"quote": "We will randomise 120 participants"}, "registry": {"quote": "Target sample size | 100"},
                   "sap": {"quote": "120 participants will be randomised"}},
    "per_arm": {"protocol": {"quote": "We will randomise 120 participants, 60 per arm"},
                "sap": {"quote": "120 participants will be randomised, 60 per arm"}},
    "analysed_pp": {"sap": {"quote": "we expect 110 to be analysed per protocol"}},
    "population": {d: {"quote": "all randomised participants, analysed in the arm to which they were assigned"} for d in ("protocol", "sap")},
}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dir = self.root / "protocol"
        self.core, self.locations = copy.deepcopy(CORE), copy.deepcopy(LOCATIONS)
        self.docs = {"protocol": PROTOCOL, "registry": REGISTRY, "sap": SAP}
        self.put("../statistics/power.json", json.dumps(POWER))

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def run_cli(self, command: str):
        out, self.err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)                     # the user's working directory, where statistics/ sits beside protocol/
        try:
            with redirect_stdout(out), redirect_stderr(self.err):
                code = pc.main([command, "--dir", str(self.dir)])
        finally:
            os.chdir(here)
        return code, json.loads(out.getvalue())

    def check(self):
        self.put("core.json", json.dumps(self.core, ensure_ascii=False))
        self.put("locations.json", json.dumps(self.locations, ensure_ascii=False))
        for doc, text in self.docs.items():
            (self.dir / f"{doc}.md").unlink(missing_ok=True)
            if text is not None:
                self.put(f"{doc}.md", text)
        code, out = self.run_cli("check")
        report = (self.dir / "check.md").read_text(encoding="utf-8")
        cells = {}
        for line in report.split("## Not consistent")[1].splitlines():
            parts = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if line.startswith("| ") and len(parts) == 4 and parts[2] in pc.STATES:
                cells[(parts[0], parts[1][:-3])] = (parts[2], parts[3])
        return code, out, cells, report

    def bad_input(self, command: str = "check") -> str:
        with self.assertRaises(SystemExit) as caught:
            self.check() if command == "check" else self.run_cli(command)
        self.assertEqual(caught.exception.code, 2)
        return self.err.getvalue()


class TimePointsAndNumbers(unittest.TestCase):
    def test_one_time_point_however_it_is_written(self):
        week12 = {("d", 84.0)}
        for text in ("12 weeks", "week 12", "Week-12", "a 12-week visit", "twelve weeks", "12周", "第12周", "第十二周", "day 84",
                     "１２周"):
            self.assertEqual(set(pc.timepoints(text)), week12, text)
        for text in ("at 12 and 26 weeks", "weeks 12 and 26", "第12周和第26周", "12、26周", "at week 12 and week 26"):
            self.assertEqual(set(pc.timepoints(text)), {("d", 84.0), ("d", 182.0)}, text)
        self.assertEqual(set(pc.timepoints("1 year")), set(pc.timepoints("12 months")))
        self.assertEqual(pc.timepoints("2026年11月18日入院, every week"), {})

    def test_months_equal_weeks_only_under_the_users_rule(self):
        self.assertNotEqual(set(pc.timepoints("3 months")), set(pc.timepoints("12 weeks")))
        self.assertEqual(set(pc.timepoints("3 months", month=28)), set(pc.timepoints("12 weeks")))
        self.assertEqual(set(pc.timepoints("3个月", month=28)), set(pc.timepoints("第12周")))
        self.assertNotEqual(set(pc.timepoints("6 months", month=28)), set(pc.timepoints("12 weeks")))

    def test_numbers_that_touch_han_characters(self):
        self.assertEqual(pc.numbers_in("随机120例，每组60例"), [120.0, 60.0])
        self.assertEqual(pc.numbers_in("样本量为312人"), [312.0])
        self.assertEqual(pc.numbers_in("１２０名; N=1,200; 10%"), [120.0, 1200.0, 10.0])


class Check(Base):
    def test_the_planted_disagreements_of_pr1(self):
        code, out, cells, report = self.check()
        self.assertEqual((code, out["ok"]), (1, False))
        self.assertEqual(cells[("O1", "registry")], ("inconsistent", "time point: the quote states 6 months; core.json: 12 weeks. "
                                                     "Months equal weeks or days only under a time_rule the user states in core.json"))
        self.assertEqual(cells[("O1", "sap")][0], "inconsistent")
        self.assertIn("the quote states 3 months; core.json: 12 weeks", cells[("O1", "sap")][1])
        self.assertEqual(cells[("O3", "registry")], ("inconsistent", "missing: locations.json gives no quote from this document"))
        self.assertEqual(cells[("randomised", "registry")], ("inconsistent", "number: the quote states 100; core.json: 120"))
        self.assertEqual(sorted(k for k in cells), [("O1", "registry"), ("O1", "sap"), ("O3", "registry"), ("randomised", "registry")])
        self.assertEqual(out["counts"], {"consistent": 12, "inconsistent": 4, "quote_not_found": 0, "not_checked": 0})
        self.assertIn("| analysed_pp | - | - | consistent |", report)              # the analysed number is its own item
        self.assertIn("| randomised | 120 | statistics/power.json | consistent | statistics/power.json inflation.n_total = 120 |", report)
        self.assertIn("| analysed_pp | 110 | user | user | Given by the user, not computed here", report)
        self.assertIn("| registry.md | Primary outcome | “Knee pain (WOMAC pain subscale) at 6 months” | inconsistent |", report)
        self.assertIn("- protocol.md: [Evidence needed: source of the expected effect]", report)
        self.assertEqual((out["given_by_user"], out["placeholders"]), (["analysed_pp"], 1))

    def test_three_months_is_twelve_weeks_only_under_a_stated_rule(self):
        self.core["time_rule"] = {"month": "4 weeks", "source": "the user, 2026-11-18"}
        _, _, cells, report = self.check()
        self.assertNotIn(("O1", "sap"), cells)
        self.assertIn("time point: the quote states 6 months; core.json: 12 weeks", cells[("O1", "registry")][1])
        self.assertIn("Time rule: 1 month = 4 weeks (the user, 2026-11-18).", report)

    def test_agreeing_documents_pass_and_a_missing_one_is_not_checked(self):
        self.docs["registry"] = None
        self.locations["O1"]["sap"]["quote"] = "Primary outcome: WOMAC pain subscale at 3 months"
        self.core["time_rule"] = {"month": "4 weeks", "source": "the user"}
        code, out, cells, _ = self.check()
        self.assertEqual((code, out["counts"]["inconsistent"], out["counts"]["not_checked"]), (0, 0, 4))
        self.assertEqual(cells[("O1", "registry")], ("not_checked", "registry.md not found"))

    def test_role_and_measure_are_read_from_the_quote_its_line_and_its_headings(self):
        self.docs["protocol"] = PROTOCOL.replace("### 6.1 Primary outcome\n\nThe primary outcome is knee pain",
                                                 "### 6.1 Secondary outcomes\n\nKnee pain")
        self.locations["O1"]["protocol"]["quote"] = "Knee pain on the WOMAC pain subscale at 12 weeks"
        self.locations["O2"]["sap"]["quote"] = "Secondary outcome: WOMAC function subscale at week 12"
        self.docs["sap"] = SAP.replace("Primary outcome: WOMAC pain subscale", "Primary outcome: pain on a 0-10 scale")
        self.locations["O1"]["sap"]["quote"] = "Primary outcome: pain on a 0-10 scale at 3 months"
        self.core["time_rule"] = {"month": "4 weeks", "source": "the user"}
        _, _, cells, _ = self.check()
        self.assertEqual(cells[("O1", "protocol")], ("inconsistent", "role: the document gives it as secondary; core.json: primary"))
        self.assertEqual(cells[("O1", "sap")], ("inconsistent", "measure: the quote lacks WOMAC"))
        self.assertEqual(cells[("O2", "sap")][1], "time point: the quote states 12 weeks; core.json: 12 weeks, 26 weeks")

    def test_a_quote_that_is_not_in_the_document(self):
        self.locations["O2"]["registry"]["quote"] = "WOMAC function subscale, weeks 12, 26 and 52"
        self.locations["per_arm"]["sap"]["quote"] = "per arm"
        code, out, cells, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("not in registry.md", cells[("O2", "registry")][1])
        self.assertEqual(cells[("per_arm", "sap")], ("quote_not_found", "2 word(s): quote at least 3"))
        self.assertEqual(out["quote_not_found"], ["O2 / registry", "per_arm / sap"])

    def test_a_number_differs_from_the_file_it_was_computed_in(self):
        self.core["numbers"][0]["value"] = 100
        self.core["numbers"][1]["from"]["key"] = "inflation.n_per_arm"
        code, out, _, report = self.check()
        self.assertEqual(code, 1)
        self.assertIn("statistics/power.json inflation.n_total = 120; core.json: 100. Copy the recorded number, never retype it", report)
        self.assertEqual(out["sources_inconsistent"], ["randomised: statistics/power.json inflation.n_total = 120; core.json: 100. "
                                                       "Copy the recorded number, never retype it",
                                                       "per_arm: statistics/power.json has no number at inflation.n_per_arm"])
        (self.root / "statistics" / "power.json").unlink()
        code, out, _, _ = self.check()
        self.assertEqual(out["sources_not_checked"], ["randomised", "per_arm"])

    def test_a_line_that_announces_another_primary_outcome_is_a_lead(self):
        self.docs["registry"] = REGISTRY + "| Primary outcome | Knee function at 26 weeks |\n"
        _, out, _, report = self.check()
        self.assertEqual(out["leads"], 1)
        self.assertIn("- registry.md, line 8: Primary outcome Knee function at 26 weeks", report)

    def test_chinese_documents(self):
        self.docs = {"protocol": "# 研究方案\n\n## 6 结局\n\n主要结局为第12周的WOMAC疼痛评分。次要结局为第12周和第26周的WOMAC功能评分。\n\n"
                                 "不良事件在每次随访时记录。\n\n## 8 样本量\n\n计划随机120例受试者，每组60例。\n",
                     "registry": "| 字段 | 内容 |\n|---|---|\n| 主要结局指标 | WOMAC疼痛评分，12周 |\n| 次要结局指标 | WOMAC功能评分，12、26周 |\n"
                                 "| 次要结局指标 | 不良事件发生率 |\n| 样本量 | 120例 |\n",
                     "sap": None}
        self.locations = {"O1": {"protocol": {"quote": "主要结局为第12周的WOMAC疼痛评分"}, "registry": {"quote": "WOMAC疼痛评分，12周"}},
                          "O2": {"protocol": {"quote": "次要结局为第12周和第26周的WOMAC功能评分"}, "registry": {"quote": "WOMAC功能评分，12、26周"}},
                          "O3": {"protocol": {"quote": "不良事件在每次随访时记录"}, "registry": {"quote": "不良事件发生率"}},
                          "randomised": {"protocol": {"quote": "计划随机120例受试者"}, "registry": {"quote": "样本量 | 120例"}},
                          "per_arm": {"protocol": {"quote": "计划随机120例受试者，每组60例"}}}
        self.core["texts"] = []
        code, out, cells, _ = self.check()
        self.assertEqual((code, out["counts"]["inconsistent"], out["counts"]["consistent"]), (0, 0, 9))
        self.docs["registry"] = self.docs["registry"].replace("WOMAC疼痛评分，12周", "WOMAC疼痛评分，6个月")
        self.locations["O1"]["registry"]["quote"] = "WOMAC疼痛评分，6个月"
        _, _, cells, _ = self.check()
        self.assertIn("the quote states 6 months; core.json: 12 weeks", cells[("O1", "registry")][1])

    def test_the_core_record_and_locations_must_be_in_the_documented_format(self):
        self.core["outcomes"][0].update({"role": "main", "timepoints": ["soon"]})
        self.core["numbers"][0].pop("from")
        self.core["texts"][0]["id"] = "O2"
        self.core["time_rule"] = {"month": "4 weeks"}
        message = self.bad_input()
        for part in ("outcomes[O1].role must be one of", 'outcomes[O1].timepoints must be a list of single time points',
                     "numbers[randomised].from must name the file and key", "ids repeat: O2",
                     'time_rule must be {"month": "4 weeks" (or days), "source"'):
            self.assertIn(part, message)
        self.core = copy.deepcopy(CORE)
        self.locations["O9"] = {"protocol": {"quote": "anything at all here"}}
        self.assertIn("names O9, which core.json does not have", self.bad_input())


class Definitions(Base):
    SOURCE = ("Source: Data dictionary of the trial database, version 2 (the user's file)\nRead: 2026-11-18\n\n"
              "Baseline pain was recorded on the WOMAC pain subscale at the first visit.\n基线疼痛采用WOMAC疼痛分量表在首次访视时记录。\n")
    HEADER = "variable,role,definition,cutoff,unit,source_id,quote,locator,ad_hoc,justification\n"

    def definitions(self, rows: str, protocol: str = PROTOCOL):
        self.put("definitions.csv", self.HEADER + rows)
        self.put("sources/dict-v2.txt", self.SOURCE)
        self.put("protocol.md", protocol)
        code, out = self.run_cli("definitions")
        found = {}
        for line in (self.dir / "definitions-check.md").read_text(encoding="utf-8").splitlines():
            parts = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if line.startswith("| ") and len(parts) == 4 and parts[2] in ("ok", "fail", "open", "not_checked"):
                found[(parts[0], parts[1])] = (parts[2], parts[3])
        return code, out, found

    def test_sources_ad_hoc_rows_and_open_rows(self):
        rows = ('Pain at baseline,covariate,WOMAC pain at the first visit,,,dict-v2,"Baseline pain was recorded on the WOMAC pain '
                'subscale",sheet 2 row 14,no,\n'
                "基线疼痛,covariate,首次访视时的WOMAC疼痛,,,dict-v2,基线疼痛采用WOMAC疼痛分量表在首次访视时记录,第2页,no,\n"
                'Responder,outcome,Improvement of WOMAC pain from baseline to 12 weeks,≥ 20,%,,,,yes,"Chosen with the user, '
                '2026-11-18; continuous score as sensitivity analysis"\n'
                "Knee osteoarthritis,eligibility,[Citation needed: the diagnostic criteria the user names],,,,,,no,\n")
        code, out, found = self.definitions(rows)
        self.assertEqual((code, out["ok"], out["open"]), (0, True, ["Knee osteoarthritis"]))
        self.assertEqual(found[("Pain at baseline", "covariate")], ("ok", "EXACT in sources/dict-v2.txt, sheet 2 row 14"))
        self.assertEqual(found[("基线疼痛", "covariate")][0], "ok")
        self.assertEqual(found[("Responder", "outcome")][0], "ok")
        self.assertEqual(found[("Responder", "cutoff in protocol.md")][0], "not_checked")
        self.assertIn("| dict-v2 | sources/dict-v2.txt | Data dictionary of the trial database", (self.dir / "definitions-check.md")
                      .read_text(encoding="utf-8"))

    def test_rows_without_support_fail(self):
        rows = ("Responder,outcome,Improvement of 20% or more,≥ 20,%,,,,yes,\n"                       # ad hoc, no reason
                "Knee osteoarthritis,eligibility,ACR clinical criteria,,,,,,no,\n"                    # named, no source
                "Pain,outcome,WOMAC pain,,,acr-1986,some words copied from somewhere else,p. 3,no,\n"   # no saved source
                'Baseline,covariate,WOMAC at visit 1,,,dict-v2,"Baseline pain was recorded on the VAS scale",row 14,no,\n'
                "Age,covariate,Age in years,,,dict-v2,Baseline pain was recorded,,no,\n"
                "Sex,predictor,Sex at birth,,,,,,yes,The user's choice\n")
        code, out, found = self.definitions(rows)
        self.assertEqual(code, 1)
        self.assertEqual(found[("Responder", "outcome")], ("fail", "An ad hoc definition needs its justification"))
        self.assertIn("No source, not ad hoc, and no [Citation needed: …]", found[("Knee osteoarthritis", "eligibility")][1])
        self.assertIn("sources/acr-1986.txt not found", found[("Pain", "outcome")][1])
        self.assertIn("The quote is not in sources/dict-v2.txt", found[("Baseline", "covariate")][1])
        self.assertEqual(found[("Age", "covariate")], ("fail", "4 word(s) of quote: copy at least 5 from sources/dict-v2.txt"))
        self.assertIn("role must be one of", found[("Sex", "predictor")][1])
        self.put("sources/bare.txt", "Baseline pain was recorded on the WOMAC pain subscale\n")
        self.put("definitions.csv", self.HEADER + 'Pain,covariate,x,,,bare,"Baseline pain was recorded on the WOMAC",p. 1,no,\n')
        code, _ = self.run_cli("definitions")
        self.assertIn("must begin with a Source: line and a Read: YYYY-MM-DD line",
                      (self.dir / "definitions-check.md").read_text(encoding="utf-8"))

    def test_the_documents_give_the_tables_cutoff(self):
        row = 'Responder,outcome,Improvement of WOMAC pain,≥ 20,%,,,,yes,"Chosen with the user, 2026-11-18"\n'
        protocol = PROTOCOL + "\nA responder improves by at least 20% from baseline; non-responders are analysed too.\n"
        self.assertEqual(self.definitions(row, protocol)[2][("Responder", "cutoff in protocol.md")][0], "ok")
        code, _, found = self.definitions(row, protocol + "\nResponder: improvement ≥ 30% at 12 weeks.\n")
        self.assertEqual(code, 1)
        self.assertIn("gives 30: “Responder: improvement ≥ 30% at 12 weeks.”", found[("Responder", "cutoff in protocol.md")][1])
        row_zh = "应答者,outcome,WOMAC疼痛改善,≥ 20,%,,,,yes,与用户商定\n"
        self.assertEqual(self.definitions(row_zh, "应答者定义为疼痛改善≥20%。\n")[2][("应答者", "cutoff in protocol.md")][0], "ok")
        code, _, found = self.definitions(row_zh, "应答者：疼痛改善30%及以上，随访12周。\n")
        self.assertEqual((code, found[("应答者", "cutoff in protocol.md")][0]), (1, "fail"))

    def test_a_table_without_its_columns_stops(self):
        self.put("definitions.csv", "variable,definition\nPain,x\n")
        self.assertIn("lacks the column(s) role, cutoff", self.bad_input("definitions"))


class Amendments(Base):
    HEADER = "date,item,before,after,reason,impact,prespecified,data_seen\n"

    def test_dated_reasoned_rows_and_changes_after_data_were_seen(self):
        self.put("amendments.csv", self.HEADER +
                 "2027-01-10,O2,12 and 26 weeks,12 and 52 weeks,Funder extended follow-up,Longer follow-up,no,no\n"
                 "2027-06-02,analysed_pp,110,104,Higher dropout than planned,Power lower,no,yes\n"
                 "2027-07-01,population,ITT,ITT,Clarified wording,None,yes,unknown\n")
        code, out = self.run_cli("amendments")
        self.assertEqual((code, out["ok"], out["after_data_seen"]), (0, True, 2))
        report = (self.dir / "amendments-check.md").read_text(encoding="utf-8")
        self.assertIn("- 2027-06-02, analysed_pp: 110 → 104. Reason: Higher dropout than planned", report)
        self.assertIn("(whether data had been seen is not known: report it as seen)", report)

    def test_a_row_without_a_date_or_a_reason_fails(self):
        self.put("amendments.csv", self.HEADER + "June 2027,O1,12 weeks,16 weeks,,,maybe,later\n2027-02-30,O2,a,,b,,no,no\n")
        code, out = self.run_cli("amendments")
        self.assertEqual(code, 1)
        self.assertEqual(out["failed"], ["amendment 1: date must be YYYY-MM-DD; no reason; prespecified must be yes or no; data_seen "
                                         "must be yes, no or unknown", "amendment 2: date must be YYYY-MM-DD; after is empty"])


if __name__ == "__main__":
    unittest.main()
