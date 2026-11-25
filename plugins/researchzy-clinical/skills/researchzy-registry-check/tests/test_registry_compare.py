"""registry_compare.py: a trial paper against its ClinicalTrials.gov record, and a search of the registry."""
from __future__ import annotations

import copy
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rc = load("registry_compare", HERE.parent / "scripts" / "registry_compare.py")
fx = load("registry_fixture", HERE / "registry_fixture.py")
WITH_EARLIER = {"O1": "protocolSection.outcomesModule.secondaryOutcomes[0]", "O2": "protocolSection.outcomesModule.primaryOutcomes[0]",
                "O3": None, "O4": None}


def by_id(report: dict) -> dict:
    return {r["id"]: r for r in report["items"]}


def facet(result: dict, name: str) -> tuple:
    return next((f["state"], f["detail"]) for f in result["facets"] if f["facet"] == name)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv) -> tuple:
        out, self.err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(self.err):
            code = rc.main([str(a) for a in argv])
        return code, json.loads(out.getvalue())

    def compare(self, edit=None, items=None, earlier=None, **build) -> tuple:
        items = copy.deepcopy(fx.ITEMS if items is None else items)
        if edit:
            edit(items)
        base = fx.build(self.dir, items, **build)
        extra = ["--earlier", fx.write(self.dir / "earlier.json", earlier)] if earlier else []
        code, summary = self.run_cli("compare", "--dir", base, *extra)
        return (code, summary, json.loads((base / "compare.json").read_text(encoding="utf-8")),
                (base / "compare.md").read_text(encoding="utf-8"))

    def bad_input(self, *argv) -> str:
        with self.assertRaises(SystemExit) as stop:
            self.run_cli(*argv)
        self.assertEqual(stop.exception.code, 2)
        return self.err.getvalue()


class TextTests(unittest.TestCase):
    def test_time_points_written_differently_are_the_same(self):
        twelve = {("d", 84)}
        for text in ("Pain (WOMAC) at week 12", "WOMAC pain subscale, 12 weeks", "第12周WOMAC疼痛评分", "a 12-week programme",
                     "twelve weeks", "12周", "from week 0 to week 12"):
            self.assertEqual(rc.timepoints(text), twelve, text)
        self.assertEqual(rc.timepoints("Baseline, 6, 12 and 26 weeks"), {("d", 42), ("d", 84), ("d", 182)})
        self.assertEqual(rc.timepoints("weeks 6, 12 and 26"), rc.timepoints("twenty-six weeks") | {("d", 42), ("d", 84)})
        self.assertEqual(rc.timepoints("1 year"), rc.timepoints("12 months"))
        self.assertEqual(rc.timepoints("随访6个月"), {("mo", 6)})
        self.assertNotEqual(rc.timepoints("3 months"), twelve)                  # never converted between weeks and months
        for text in ("EQ-5D-5L", "2020年3月14日", "a 2-dose regimen", "SF-36"):
            self.assertEqual(rc.timepoints(text), set(), text)

    def test_numbers_beside_han_characters_and_full_width_digits(self):
        self.assertEqual(rc.numbers("样本量为312人"), {312.0})
        self.assertEqual(rc.numbers("共随机分配１５０例患者"), {150.0})
        self.assertEqual(rc.numbers("1,200 participants, two arms"), {1200.0, 2.0})
        self.assertEqual(rc.numbers("SF-36 and NCT99123456"), set())

    def test_dates_in_english_and_chinese(self):
        for text in ("Published online 14 March 2025", "March 14, 2025", "2025年3月14日在线发表", "2025-03-14"):
            self.assertIn("2025-03-14", rc.dates(text), text)
        self.assertEqual(rc.dates("from February 2020"), {"2020", "2020-02"})
        self.assertEqual(rc.dates("EudraCT 2019-004567-12"), set())
        self.assertTrue(rc.differ("2020-02-03", "2020-03") and not rc.differ("2020-02-03", "2020-02"))

    def test_named_instruments_and_words(self):
        self.assertEqual(rc.instruments("Pain (WOMAC) at week 12")[0], {"WOMAC"})
        self.assertEqual(rc.instruments("EQ-5D-5L, HbA1c and McMaster")[0], {"EQ5D5L", "HBA1C"})
        self.assertEqual(rc.instruments("CHANGE IN WOMAC PAIN SCORE")[0], set())   # a text in capitals names none
        self.assertEqual(rc.wording("Pain (VAS) at 12 weeks", "", "WOMAC pain subscale")[0], "inconsistent")
        self.assertEqual(rc.wording("Pain (WOMAC) at week 12", "", "WOMAC pain subscale")[0], "consistent")
        self.assertEqual(rc.wording("第12周WOMAC疼痛评分", "", "WOMAC pain subscale")[0], "not_checked")    # needs a translation


class CompareTests(Base):
    def test_the_planted_problems_of_a_trial_report(self):
        code, summary, report, md = self.compare()
        items = by_id(report)
        self.assertEqual((code, summary["identity"], summary["problems"]), (0, "same", []))
        self.assertEqual(summary["inconsistent_items"], ["O1: role", "O2: role", "O3: added", "R1: timing"])
        self.assertEqual(facet(items["O1"], "timepoint"), ("consistent", "paper 26 weeks; record 26 weeks"))
        self.assertEqual(facet(items["O2"], "timepoint"), ("consistent", "paper 12 weeks; record 12 weeks"))   # week 12 = 12 weeks
        self.assertEqual(facet(items["O2"], "measure")[0], "consistent")
        self.assertEqual((report["primary"]["state"], report["primary"]["types"]), ("inconsistent", ["role", "timepoint"]))
        self.assertEqual(items["O4"]["state"], "consistent")
        self.assertEqual(report["registered_not_paired"][0]["types"], ["omitted"])                   # Timed Up and Go
        self.assertIn("(ESTIMATED)", facet(items["N1"], "value")[1])
        self.assertEqual(items["N1"]["state"], "consistent")
        self.assertIn("an ESTIMATED count is the plan", facet(items["N2"], "value")[1])
        self.assertEqual(items["N2"]["state"], "not_checked")
        self.assertEqual(items["D1"]["state"], "consistent")
        self.assertIn("98 days after the ACTUAL start 2020-02-03", facet(items["R1"], "timing")[1])
        self.assertEqual(items["I1"]["state"], "consistent")
        self.assertEqual([(r["id"], r["state"]) for r in report["registrations"]],
                         [("NCT99123456", "consistent"), ("2019-004567-12", "not_checked")])        # EudraCT: no record
        self.assertEqual({r["as_registered"][0] for r in report["items"] if r["kind"] == "outcome"}, {"not_checked"})
        self.assertIn("after the paper was published (2025-03-14)", md)
        self.assertIn("As registered before enrolment: not_checked", md)
        self.assertIn("| The primary outcome was knee function (WOMAC physical function subscale) at 26 weeks | WOMAC physical "
                      "function subscale.", md)                                                    # both texts side by side
        self.assertIn("no statement of a change found; searched: Methods, Discussion and the supplement", md)
        self.assertNotIn("switch", (md + json.dumps(report)).lower())

    def test_actual_enrolment_is_compared_with_the_number_enrolled(self):
        _, _, report, _ = self.compare(rec=fx.record(count=180, kind="ACTUAL"))
        items = by_id(report)
        self.assertEqual(facet(items["N2"], "value"), ("inconsistent", "record 180 (ACTUAL); paper 150 (actual)"))
        self.assertEqual(items["N1"]["state"], "not_checked")

    def test_a_swapped_digit_that_leads_to_another_trial_stops_before_the_outcomes(self):
        def swap(items):
            items["record"]["file"] = f"record-{fx.SWAPPED}.json"
            items["registrations"][0].update(id=fx.SWAPPED, quote=f"ClinicalTrials.gov {fx.SWAPPED}")
        code, summary, report, md = self.compare(swap, rec=fx.other_trial(), paper=fx.PAPER.replace(fx.NCT, fx.SWAPPED))
        self.assertEqual((code, summary["identity"], summary["not_checked"], summary["items"]), (1, "different", 9, 9))
        self.assertEqual([f["state"] for f in report["identity"]["fields"][:3]], ["inconsistent"] * 3)
        self.assertIn("No item was compared", md)
        self.assertNotIn("### O1", md)

    def test_a_chinese_paper(self):
        code, summary, report, md = self.compare(items=fx.ITEMS_ZH, paper=fx.PAPER_ZH)
        items = by_id(report)
        self.assertEqual((code, summary["identity"], summary["inconsistent_items"]), (0, "same", ["R1: timing"]))
        self.assertEqual(facet(items["O1"], "timepoint"), ("consistent", "paper 12 weeks; record 12 weeks"))   # 第12周
        self.assertIn("through the model's translation", facet(items["O1"], "measure")[1])
        self.assertEqual([items[i]["state"] for i in ("O1", "O2", "N1", "D1")], ["consistent"] * 4)
        self.assertEqual(items["N2"]["state"], "not_checked")                     # １５０ randomised against an estimate
        self.assertEqual(items["O1"]["paper"]["page"], 2)

        def untranslated(zh):
            for entry in [*zh["identity"].values(), *zh["items"]]:
                entry.pop("translation", None)
        code, summary, report, _ = self.compare(untranslated, items=fx.ITEMS_ZH, paper=fx.PAPER_ZH)
        self.assertEqual((code, summary["identity"]), (1, "unconfirmed"))
        self.assertIn("add translation", report["identity"]["fields"][0]["detail"])

    def test_an_earlier_version_is_compared_as_registered(self):
        def pair(items):
            for item in items["items"]:
                if item["id"] in WITH_EARLIER:
                    item["earlier"] = WITH_EARLIER[item["id"]]
        earlier = fx.record(last="2020-05-14", secondary=fx.SECONDARY[:2])
        code, summary, report, md = self.compare(pair, earlier=earlier)
        self.assertEqual(by_id(report)["O4"]["as_registered"][:2], ["inconsistent", ["added"]])   # adverse events came later
        self.assertEqual(by_id(report)["O1"]["as_registered"][:2], ["inconsistent", ["role"]])
        self.assertEqual((code, summary["problems"]), (1, ["item O4: say whether the paper states this change: disclosure with "
                                                            "a quote, or with searched"]))
        self.assertIn("It too was posted after enrolment began (2020-02-03)", md)

        def disclosed(items):
            pair(items)
            items["items"][3]["disclosure"] = fx.SEARCHED
        self.assertEqual(self.compare(disclosed, earlier=earlier)[0], 0)
        other = fx.other_trial()
        self.assertIn("--earlier is a version of another trial", self.compare(disclosed, earlier=other)[1]["problems"])

    def test_a_record_unchanged_since_enrolment_began(self):
        _, _, report, md = self.compare(rec=fx.record(last="2020-05-20", start="2020-06-01"))
        items = by_id(report)
        self.assertEqual(facet(items["R1"], "timing")[0], "consistent")                     # submitted before the start
        self.assertEqual(items["O4"]["as_registered"][0], items["O4"]["state"])
        self.assertEqual(facet(items["D1"], "value"), ("inconsistent", "paper 2020-02-03; record 2020-06-01 (ACTUAL)"))
        self.assertNotIn("As registered before enrolment", md)

    def test_what_items_json_must_correct(self):
        def break_items(items):
            first, second = items["items"][0], items["items"][1]
            first["quote"] = "The primary outcome was knee pain at 12 weeks"         # its words are there, scattered
            items["items"][7]["quote"] = "The trial was registered before enrolment began"
            del first["disclosure"]
            second["quote"] = "Pain (WOMAC) at week twelve weeks"                   # partly there
            items["items"][3]["record"] = "protocolSection.outcomesModule.secondaryOutcomes[7]"
            items["items"][4]["value"] = 210
            items["items"][6]["date"] = "2020-03-01"
            items["registrations"][1]["quote"] = "EudraCT number in the abstract"
            items["unreported"].append({"record": "protocolSection.outcomesModule.primaryOutcomes[0]", "searched": "Results"})
        code, summary, _, md = self.compare(break_items)
        problems = "\n".join(summary["problems"])
        self.assertEqual(code, 1)
        for part in ("item O1: the quote is in the paper only with other words inside it (INTERLEAVED)",
                     "item R1: the quote is not in the paper (ABSENT)", "item O2: the quote is only partly in the paper (PARTIAL)",
                     "item O4: protocolSection.outcomesModule.secondaryOutcomes[7] is not in the record",
                     "item N1: 210 is not in the quote", "item D1: the date 2020-03-01 is not in the quote",
                     "registrations[2019-004567-12]: the number is not in its quote",
                     "unreported: protocolSection.outcomesModule.primaryOutcomes[0] is not a registered outcome, or an item pairs it"):
            self.assertIn(part, problems)
        self.assertIn("## Problems to correct in items.json", md)

    def test_an_inconsistent_outcome_must_say_whether_the_paper_states_the_change(self):
        def silent(items):
            del items["items"][0]["disclosure"]
        code, summary, _, _ = self.compare(silent)
        self.assertEqual((code, summary["problems"]), (1, ["item O1: say whether the paper states this change: disclosure with a "
                                                            "quote, or with searched"]))

        def stated(items):
            items["items"][0]["disclosure"] = {"quote": "the steering committee made knee function at 26 weeks the primary outcome",
                                               "locator": "p. 3, Discussion"}
        code, _, report, md = self.compare(stated)
        self.assertEqual(code, 0)
        self.assertIn('the paper states a change: "the steering committee made knee function', md)

    def test_named_instruments_that_differ_and_unpaired_outcomes(self):
        def vas(items):
            items["items"][1]["quote"] = "Pain (VAS) at week 12"
            items["unreported"] = []
        _, _, report, _ = self.compare(vas, paper=fx.PAPER.replace("Pain (WOMAC)", "Pain (VAS)"))
        self.assertEqual(by_id(report)["O2"]["types"], ["role", "measure"])
        self.assertEqual(report["registered_not_paired"][0]["state"], "not_checked")      # no search recorded for it

    def test_only_part_of_the_identity_agrees(self):
        def other_words(items):
            items["identity"]["intervention"] = {"quote": "Participants in the intervention", "locator": "p. 2"}
        code, summary, report, md = self.compare(other_words)
        self.assertEqual((code, summary["identity"]), (0, "partial"))
        self.assertIn("confirm with the user that this record is the paper's trial", md)

    def test_unreadable_or_malformed_input_stops(self):
        base = fx.build(self.dir)
        self.assertIn("does not exist", self.bad_input("compare", "--dir", self.dir / "nowhere"))
        for change, message in ((lambda i: i["items"][0].update(kind="secondary_outcome"), "kind must be one of"),
                                (lambda i: i["items"][6].update(date="3 Feb 2020"), "date must be YYYY"),
                                (lambda i: i["record"].update(read="today"), "record.read must be"),
                                (lambda i: i["items"][0].update(record="outcomes, first"), "record must be a field path")):
            items = copy.deepcopy(fx.ITEMS)
            change(items)
            fx.write(base / "items.json", items)
            with self.subTest(message):
                self.assertIn(message, self.bad_input("compare", "--dir", base))
        fx.write(base / "items.json", fx.ITEMS)
        fx.write(base / f"record-{fx.NCT}.json", {"studies": []})
        self.assertIn("is not a study record", self.bad_input("compare", "--dir", base))
        (base / "paper.txt").write_bytes(b"%PDF-1.4\n")
        fx.write(base / f"record-{fx.NCT}.json", fx.record())
        self.assertIn("is a PDF", self.bad_input("compare", "--dir", base))
        (base / "items.json").write_text("{not json", encoding="utf-8")
        self.assertIn("is not valid JSON", self.bad_input("compare", "--dir", base))


class SearchTests(Base):
    def search(self, **build) -> tuple:
        base = fx.build_search(self.dir, **build)
        code, summary = self.run_cli("search", "--dir", base)
        rows = list(csv.DictReader(io.StringIO((base / "candidates.csv").read_text(encoding="utf-8"))))
        return code, summary, rows, (base / "search.md").read_text(encoding="utf-8")

    def test_every_trial_is_listed_whatever_its_status(self):
        code, summary, rows, md = self.search()
        self.assertEqual((code, summary["trials"], summary["not_judged"]), (0, 3, ["NCT99000102"]))
        self.assertEqual({r["nct"]: r["status"] for r in rows},
                         {"NCT99000101": "COMPLETED", "NCT99000102": "WITHDRAWN", "NCT99000103": "RECRUITING"})
        first = rows[0]
        self.assertEqual((first["has_results"], first["found_by"], first["relevance"], first["judged_by"]),
                         ("yes", "s1; s2", "similar", "model"))
        self.assertEqual((rows[1]["start"], rows[1]["enrollment"]), ("2021-01 (ESTIMATED)", "0 (ACTUAL)"))
        self.assertIn("| s1 | 2026-11-18 | countTotal=true; pageSize=100; query.cond=knee osteoarthritis; query.intr=exercise | 3 | 3 | yes |", md)
        self.assertIn("COMPLETED 1, RECRUITING 1, WITHDRAWN 1", md)
        self.assertRegex(md, r"\| s1 \| search/s1-p1.json \| [0-9a-f]{64} \| 3 \|")
        self.assertNotIn("not been studied", md)

    def test_an_empty_search_says_only_what_was_searched(self):
        empty = {"totalCount": 0, "studies": []}
        code, summary, rows, md = self.search(first=empty, second=empty, log={**fx.LOG, "relevance": []})
        self.assertEqual((code, summary["trials"], rows), (0, 0, []))
        self.assertIn("these queries found no record in ClinicalTrials.gov on 2026-11-18; it does not show that the question "
                      "has not been studied", md)

    def test_an_unfinished_search_and_a_relevance_call_for_a_trial_not_found(self):
        log = copy.deepcopy(fx.LOG)
        log["relevance"].append({"nct": "NCT99000999", "call": "similar", "reason": "remembered, not found"})
        code, summary, _, md = self.search(log=log, first={"totalCount": 250, "studies": fx.TRIALS, "nextPageToken": "abc"})
        self.assertEqual(code, 1)
        self.assertEqual(summary["problems"], ["s1: the last saved page has a nextPageToken: fetch the remaining pages, or narrow "
                                               "the query", "relevance: NCT99000999 is in no saved page"])
        self.assertIn("| 250 | 3 | no |", md)

    def test_fields_left_out_of_a_page_are_said_to_be_missing(self):
        bare = copy.deepcopy(fx.TRIALS[1])
        del bare["protocolSection"]["conditionsModule"], bare["hasResults"]
        _, _, rows, _ = self.search(first={"totalCount": 1, "studies": [bare]}, log={**fx.LOG, "relevance": []})
        self.assertEqual((rows[0]["conditions"], rows[0]["has_results"]), ("not in page", "not in page"))

    def test_a_malformed_log_or_page_stops(self):
        base = fx.build_search(self.dir, log={"searches": [{"id": "s1", "url": fx.URL, "pages": []}],
                                              "relevance": [{"nct": "NCT99000101", "call": "relevant"}]})
        message = self.bad_input("search", "--dir", base)
        self.assertIn("needs id, url (as sent), date (YYYY-MM-DD) and pages", message)
        self.assertIn("relevance NCT99000101: needs nct, call (similar, partial, unrelated) and reason", message)
        base = fx.build_search(self.dir, first=[])
        self.assertIn("is not a page of an API v2 study search", self.bad_input("search", "--dir", base))


if __name__ == "__main__":
    unittest.main()
