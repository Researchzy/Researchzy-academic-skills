"""case_check.py: identifiers reported by category and position only; a sourced timeline; consent from the
record; similar cases from saved searches. Every patient, place and number below is invented."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "case_check.py"
spec = importlib.util.spec_from_file_location("case_check", SCRIPT)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
IDS = {"names": ["Jana Novák", "诺娃克"], "initials": ["J.N."], "record_numbers": ["4471203"], "test_numbers": ["RX-2025-00881"],
       "hospitals": ["Riverside General Hospital", "滨江总医院"], "towns": ["Lakeport"], "employers": ["Lakeport Ferry Company"],
       "dates": ["2025-03-14"], "age_threshold": 90}
# Real task CR-1, rebuilt with invented content: bilingual dermatology notes of a drug reaction that resolved.
NOTES = """# Dermatology notes (synthetic test case; no real patient)

Day 0: widespread itchy eruption on both forearms and the trunk, four weeks after starting drug X 20 mg daily.
第0天：服用药物X（每日20 mg）四周后，双前臂及躯干出现泛发性瘙痒性皮疹。2025年3月14日入院。
Day 2: punch biopsy from the left forearm showed a superficial perivascular infiltrate with eosinophils.
第2天：左前臂钻孔活检示浅层血管周围炎症细胞浸润，可见嗜酸性粒细胞。
Day 3: drug X stopped; topical corticosteroid started.
第3天：停用药物X，开始外用糖皮质激素。
Week 6: eruption fully resolved without scarring.
第6周：皮疹完全消退，未留瘢痕。
Mrs Jana Novak, 92-year-old retired ferry captain, MRN 4471203, Riverside General Hospital, Lakeport.
岛上唯一的渡轮船长。
"""
TIMELINE = """time,event,where,quote,exact_date,approved_by
Day 0,admitted on 14 March 2025 with an itchy eruption,notes.md line 3,"widespread itchy eruption on both forearms and the trunk",,
Day 3,drug X stopped,notes.md line 7,"drug X stopped; topical corticosteroid started",,
Day 2,biopsy,notes.md line 5,"punch biopsy from the left forearm",,
第6周,皮疹消退,notes.md 第10行,皮疹完全消退，未留瘢痕,,
"""
CAPTIONS = "Figure 1. J.N.'s forearm on day 0.\nFigure 2. Biopsy, haematoxylin and eosin.\nFigure 3. The forearm at week 6.\n"
ABSTRACTS = ("We describe a 67-year-old man who developed an eczematous eruption six weeks after starting drug X. "
             "The eruption cleared within a month of withdrawal.",
             "A woman developed a lichenoid rash on drug X; the rash resolved after the drug was stopped.",
             "An 81-year-old woman presented with a generalised exanthem two weeks after starting drug X.",
             "A 59-year-old man had a photosensitive eruption on drug X that recurred on rechallenge.")
SAVED = {"total": 4, "data": [{"corpusId": 100 + i, "title": f"Report {i} of an eruption with drug X", "doi": f"10.1000/case.{i}",
                               "abstract": text} for i, text in enumerate(ABSTRACTS, 1)]}
SEARCHES = {"searches": [{"id": "s1", "tool": "search_papers", "query": "drug X eruption case report", "filters": {},
                          "total": 4, "date": "2026-11-18", "file": "searches/s1.json"}]}
TABLE = {"columns": ["age", "onset"], "rows": [
    {"id": "r1", "search": "s1", "doi": "10.1000/case.1", "cells": {
        "age": {"value": "67", "quote": "We describe a 67-year-old man"},
        "onset": {"value": "6 weeks", "quote": "six weeks after starting drug X"}}},
    {"id": "r2", "search": "s1", "doi": "https://doi.org/10.1000/CASE.2", "cells": {        # CR-1 problem 10: no age given
        "age": {"value": "70", "quote": "A 70-year-old woman developed a lichenoid rash"}, "onset": "not reported"}},
    {"id": "r3", "search": "s1", "title": "Report 3 of an eruption with drug X", "cells": {
        "age": {"value": "81", "quote": "An 81-year-old woman presented"}, "onset": {"value": "2 weeks", "quote": "two weeks after"}}},
    {"id": "r4", "search": "s1", "title": "The famous index case of the drug X eruption",           # CR-1 problem 9: from memory
     "cells": {"age": "not reported", "onset": "not reported"}}]}
DRAFT = """# Eruption associated with drug X in an older woman: a case report

## Introduction

This is the first reported case of an eruption of this kind with drug X.

## Case presentation

A 92-year-old woman, the only ferry captain on the island, presented with an itchy eruption. Mrs Novak's rash spread.
She was treated at Riverside General Hospital, Lakeport, and took drug X at 20 mg daily.

## Discussion

This case proves that drug X causes eruptions. Elderly patients should not use drug X.
The search in Table S1 (Researchzy index, 18 November 2026) found 4 reports of similar eruptions.

## 摘要

本文为首例报告。本病例证明药物X可引起皮疹。老年患者不应使用药物X。

## Consent

Written informed consent was obtained from the patient.

## References

1. Example A. Eruption after drug X. J Example Dermatol. 2019;12:345-350. doi:10.1000/case.1 PMID: 31234567
"""
JPEG = (b"\xff\xd8\xff\xe1\x00\x40Exif\x00\x00MM\x00\x2a\x00\x00\x00\x08\x00\x01\x88\x25\x00\x04\x00\x00\x00\x01"
        b"\x00\x00\x00\x1a2025:03:14 10:22:01\x00\xff\xd9")      # an EXIF date and a GPS directory


def ctx(ids=None, threshold=90, approved=(), searched=()):
    return {"list": cc.list_matchers(IDS if ids is None else ids), "threshold": threshold, "approved": set(approved),
            "search_dates": set(searched), "bound": 0, "allow": [], "missed": []}


def found(text, context=None, refs=False) -> list:
    hits = cc.find(text, context or ctx(), refs)
    return sorted((h["category"], text[h["column"] - 1:h["column"] - 1 + h["length"]], h["state"]) for h in hits)


def docx(paragraphs, comments=(), core="", app="") -> bytes:
    run = lambda text: f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"  # noqa: E731
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        body = "".join(map(run, paragraphs))
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
        if comments:
            archive.writestr("word/comments.xml", f'<w:comments xmlns:w="{W_NS}">' + "".join(
                f'<w:comment w:id="{i}" w:author="{a}" w:initials="{n}">{run(t)}</w:comment>' for i, (a, n, t) in enumerate(comments))
                + "</w:comments>")
        for name, body in (("docProps/core.xml", core), ("docProps/app.xml", app)):
            archive.writestr(name, body) if body else None
    return buffer.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dir = self.root / "case-report"
        self.put("private/identifiers.json", IDS)
        self.notes = self.root / "notes.md"
        self.notes.write_text(NOTES, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name: str, content) -> Path:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False), encoding="utf-8")
        return path

    def cr1(self):
        for name, content in (("timeline.csv", TIMELINE), ("captions.md", CAPTIONS), ("draft.md", DRAFT), ("searches.json", SEARCHES),
                              ("searches/s1.json", SAVED), ("similar-cases.json", TABLE), ("figures/IMG_4471203.jpg", JPEG),
                              ("figures/biopsy.png", b"\x89PNG\r\n\x1a\n"), ("figures/week6.jpg", b"\xff\xd8\xff\xd9")):
            self.put(name, content)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = cc.main([argv[0], "--dir", str(self.dir), *map(str, argv[1:])])
            except SystemExit as exc:
                code = exc.code
        self.out, self.err = out.getvalue(), err.getvalue()
        return code, json.loads(self.out) if self.out else None

    def check(self, *argv):
        code, result = self.run_cli("check", "--notes", self.notes, *argv)
        return code, result, {(r.split(": ", 1)[0]) for r in result["failed"]}, self.rows()

    def rows(self) -> dict:
        found_rows = {}
        for line in (self.dir / "check.md").read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if line.startswith("| ") and len(cells) == 4 and cells[2] in cc.STATES:
                found_rows[(cells[0], cells[1].rsplit("/", 1)[-1])] = (cells[2], cells[3])
        return found_rows


class IdentifierTests(unittest.TestCase):
    def test_list_entries_ignore_case_accents_separators_and_full_stops(self):
        self.assertEqual(found("Mrs NOVAK's rash; Jana Novak; jana novák; Novakova"),
                         [("name", "Jana Novak", "hit"), ("name", "NOVAK", "hit"), ("name", "jana novák", "hit")])
        self.assertEqual(found("J.N.'s forearm, J. N. and JN; JNK is a kinase"),
                         [("initials", "J. N.", "hit"), ("initials", "J.N.", "hit"), ("initials", "JN", "hit")])
        self.assertEqual([x[:2] for x in found("MRN 447 1203, 447-1203, ４４７１２０３, IMG_4471203.jpg, 94471203")],
                         [("long_number", "94471203"), ("record_number", "447 1203"), ("record_number", "447-1203"),
                          ("record_number", "4471203"), ("record_number", "４４７１２０３")])
        self.assertEqual(found("accession rx 2025 00881"), [("test_number", "rx 2025 00881", "hit")])
        self.assertEqual(found("The Lakeport ferry; Lakeport Ferry Company"), [("employer", "Lakeport Ferry Company", "hit"),
                                                                               ("town", "Lakeport", "hit")])

    def test_chinese_entries_and_numbers_next_to_han_characters(self):
        self.assertEqual(found("患者诺娃克女士于2025年3月14日入住滨江总医院，病历号4471203，年龄：92"),
                         [("age", "年龄：92", "hit"), ("date", "2025年3月14日", "hit"), ("hospital", "滨江总医院", "hit"),
                          ("name", "诺娃克", "hit"), ("record_number", "4471203", "hit")])
        self.assertEqual(found("检查号RX202500881，另一份记录14472039"), [("long_number", "14472039", "hit"),
                                                                        ("test_number", "RX202500881", "hit")])

    def test_dates_with_a_day_and_a_month_in_every_form(self):
        text = "on 14 March 2025, March 14, 2025, 14-Mar-25, 14/03/2025, 2025.3.14, 3月14日, 2025년 3월 14일; in May 2025 we may 3"
        self.assertEqual([x[1] for x in found(text, ctx({}))],
                         ["14 March 2025", "14-Mar", "14/03/2025", "2025.3.14", "2025년 3월 14일", "3月14日", "March 14, 2025"])
        dated = ctx({}, approved={(3, 14, 25)}, searched={(11, 18, 26)})
        self.assertEqual(found("searched 18 November 2026; admitted 2025-03-14", dated),
                         [("date", "18 November 2026", "search_date"), ("date", "2025-03-14", "approved")])

    def test_ages_only_at_or_above_the_users_threshold(self):
        text = "a 92-year-old woman, aged 92, 92 yrs, 89-year-old son, 92岁, 九十二岁, 92歳, 92세, a nonagenarian, 八十九岁"
        self.assertEqual([x[1] for x in found(text, ctx({}))],
                         ["92 yrs", "92-year-old", "92岁", "92歳", "92세", "aged 92", "nonagenarian", "九十二岁"])
        self.assertEqual(found(text, ctx({}, threshold=None)), [])            # no threshold: not checked, reported as such
        self.assertEqual([x[1] for x in found(text, ctx({}, threshold=95))], [])
        self.assertEqual(found("aged 90 or over; 92 years or older; 90+ years; 90岁及以上; 九十岁以上", ctx({})), [])   # bands

    def test_contact_details_numbers_codes_titles_and_institutions(self):
        text = ("call +44 20 7946 0958 or (020) 7946 0958, mail jn@example.org, see https://example.org/jn, 192.0.2.44; "
                "platelets 150000/μL, 250000 IU; code AB123456; mRNA-1273; CD4 520; doi:10.1000/12345678 PMID: 34567890")
        self.assertEqual([x[:2] for x in found(text, ctx({}))],
                         [("code", "AB123456"), ("email", "jn@example.org"), ("ip", "192.0.2.44"), ("phone", "(020) 7946 0958"),
                          ("phone", "+44 20 7946 0958"), ("url", "https://example.org/jn")])
        text = ("Dr. Hale saw Mrs Brook; 王女士 and 该女士 and 患者女士. Brookfield Memorial Hospital, the University of Westmere, "
                "General Hospital, the Hospital Anxiety and Depression Scale, 转至上级医院, 入住滨海第一人民医院")
        self.assertEqual([x[:2] for x in found(text, ctx({}))],
                         [("institution", "Brookfield Memorial Hospital"), ("institution", "University of Westmere"),
                          ("institution", "滨海第一人民医院"), ("titled_name", "Dr. Hale"), ("titled_name", "Mrs Brook"),
                          ("titled_name", "王女士")])

    def test_reference_lists_and_exempt_phrases(self):
        line = "Brookfield Memorial Hospital, 2019-04-02, Novak J"
        self.assertEqual(found(line, refs=True), [("name", "Novak", "hit")])           # patterns are not applied in references
        context = ctx({})
        context["allow"] = [cc.re.compile("brookfield memorial hospital")]
        self.assertEqual(found(line, context)[1], ("institution", "Brookfield Memorial Hospital", "exempt"))


class ScanTests(Base):
    def test_the_notes_are_reported_by_category_and_position_only(self):
        code, result = self.run_cli("scan", self.notes)
        self.assertEqual(code, 1)
        self.assertEqual(sorted((h["category"], h["line"], h["column"], h["length"]) for h in result["hits"]),
                         [("age", 11, 17, 11), ("date", 4, 40, 10), ("hospital", 11, 65, 26), ("name", 11, 5, 10),
                          ("record_number", 11, 56, 7), ("town", 11, 93, 8)])
        self.assertEqual([(Path(x["file"]).name, x["line"], x["column"], x["length"]) for x in result["quasi_identifiers"]],
                         [("notes.md", 12, 1, 5)])
        report = (self.dir / "scan.md").read_text(encoding="utf-8")
        self.assertIn("Ages: 90 years and over (the user's threshold).", report)
        self.assertIn("notes.md | 11 | 5 | 10 |", report)
        self.notes.write_text("Day 0: eruption on both forearms.\n", encoding="utf-8")
        self.assertEqual(self.run_cli("scan", self.notes)[0], 0)

    def test_phrases_the_clinician_marks_as_identifying_nobody(self):
        self.notes.write_text("Scored on the Brookfield Memorial Hospital scale; seen at Westmere General Hospital.\n",
                              encoding="utf-8")
        self.assertEqual([h["category"] for h in self.run_cli("scan", self.notes)[1]["hits"]], ["institution", "institution"])
        self.put("not-identifiers.txt", "# a rating scale, not a place\n\n  Brookfield Memorial   Hospital scale \n")
        self.assertEqual([h["column"] for h in self.run_cli("scan", self.notes)[1]["hits"]], [59])

    def test_word_files_paragraphs_comments_authors_and_properties(self):
        core = ('<cp:coreProperties xmlns:cp="x" xmlns:dc="y"><dc:creator>Dermatology, Riverside General Hospital</dc:creator>'
                "<dc:title>Case of Jana Novak</dc:title><created>2025-03-14T09:00:00Z</created></cp:coreProperties>")  # a timestamp
        self.put("notes.docx", docx(["Day 0: eruption.", "Seen at 滨江总医院。"], comments=[("J. Novak", "JN", "ask 诺娃克 about 92岁")],
                                    core=core, app="<Properties><Company>Lakeport Ferry Company</Company></Properties>"))
        code, result = self.run_cli("scan", self.dir / "notes.docx")
        self.assertEqual(sorted((h["line"], h["category"]) for h in result["hits"]), [
            ("comments author", "initials"), ("comments author", "name"), ("comments paragraph 1", "age"),
            ("comments paragraph 1", "name"), ("paragraph 2", "hospital"), ("property Company", "employer"),
            ("property creator", "hospital"), ("property title", "name")])

    def test_images_file_name_metadata_and_gps_and_the_pixels_are_not_checked(self):
        self.put("figures/IMG_4471203.jpg", JPEG)
        self.put("figures/plain.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0ctEXtTitle\x00Jana Novak")
        code, result = self.run_cli("scan", self.dir / "figures")
        self.assertEqual(sorted((h["file"].rsplit("/", 1)[-1], h["line"], h["category"]) for h in result["hits"]), [
            ("IMG_*******.jpg", "file name", "record_number"), ("IMG_*******.jpg", "metadata", "date"),
            ("IMG_*******.jpg", "metadata", "location"), ("plain.png", "metadata", "name")])
        self.assertEqual(sum("the picture itself was not looked at" in x for x in result["not_checked"]), 2)

    def test_bad_input_stops_with_a_message_and_names_no_identifier(self):
        self.assertEqual(self.run_cli("scan", self.root / "notes" / "Novak_visit.md")[0], 2)
        self.assertIn("no such file or folder", self.err)
        self.assertNotIn("Novak", self.err)
        for ids, message in (({"name": ["x"]}, "the keys are names"), ({"age_threshold": "90"}, "age_threshold, a whole number")):
            self.put("private/identifiers.json", ids)
            self.assertEqual(self.run_cli("scan", self.notes)[0], 2)
            self.assertIn(message, self.err)
        (self.dir / "private" / "identifiers.json").unlink()
        self.assertEqual(self.run_cli("scan", self.notes)[0], 2)
        self.assertIn("no identifiers file", self.err)
        self.put("private/identifiers.json", IDS)
        self.put("timeline.csv", "time,event\nDay 0,eruption\n")
        self.assertEqual(self.run_cli("check")[0], 2)
        self.assertIn("lacks the column(s) where, quote", self.err)


class CheckTests(Base):
    def test_the_planted_problems_of_cr1(self):
        self.cr1()
        code, result, failed, rows = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(failed, {"identifiers", "timeline_order", "consent_statement", "similar_case_rows", "similar_case_cells"})
        self.assertEqual(rows[("identifiers", "draft.md")], ("fail", "4 hit(s): name 1, age 1, hospital 1, town 1."))  # 1, 4, 6
        self.assertEqual(rows[("identifiers", "captions.md")], ("fail", "1 hit(s): initials 1."))                     # 2
        self.assertEqual(rows[("identifiers", "timeline.csv")], ("fail", "1 hit(s): date 1."))                        # 3
        self.assertEqual(rows[("identifiers", "IMG_*******.jpg")], ("fail", "3 hit(s): record_number 1, date 1, location 1."))  # 5
        self.assertEqual(rows[("consent_statement", "draft")][0], "fail")                                            # 8
        self.assertEqual(rows[("consent_record", "consent.json (missing)")][0], "not_checked")
        self.assertEqual(rows[("similar_case_rows", "similar-cases.json")],                                            # 9
                         ("fail", "r4: not among the papers of the saved result of s1."))
        self.assertEqual(rows[("similar_case_cells", "similar-cases.json")],                                           # 10
                         ("fail", "r2 / age: the quote is not in the source (ABSENT)."))
        self.assertEqual(rows[("timeline_order", "timeline.csv")], ("fail", "line 4 (Day 2) comes after line 3 (Day 3)."))  # 13
        self.assertEqual(rows[("timeline_quotes", "timeline.csv")][0], "pass")              # English and Chinese quotes found
        leads = sorted((x["lead"], x["line"]) for x in result["leads"])
        self.assertEqual(leads, [("advice", 14), ("advice", 19), ("cause", 14), ("cause", 19), ("dose", 10), ("proof", 14),
                                 ("proof", 19), ("rarity", 5), ("rarity", 19), ("unique_description", 9)])        # 7, 11, 12
        self.assertEqual(result["rarity_bound_to_a_search"], 0)
        self.assertNotIn(("date", 15), [(h["category"], h["line"]) for h in result["hits"]])     # the search date is no hit
        draft_lines = sorted(h["line"] for h in result["hits"] if h["file"].endswith("draft.md"))
        self.assertEqual(draft_lines, [9, 9, 10, 10])                                          # none in the reference list
        self.assertTrue(any("the picture itself" in x for x in result["not_checked"]))

    def test_the_fixed_cr1_draft_passes(self):
        self.cr1()
        draft = (DRAFT.replace("Mrs Novak's rash", "The rash").replace("92-year-old", "older").replace(
                 "Riverside General Hospital, Lakeport", "a regional hospital").replace(
                 "This is the first reported case", "The search of 18 November 2026 found no earlier report").replace(
                 "Written informed consent was obtained from the patient.", cc.CONSENT_PLACEHOLDER).replace("4 reports", "3 reports"))
        self.put("draft.md", draft)
        table = copy.deepcopy(TABLE)
        table["rows"] = table["rows"][:3]
        table["rows"][1]["cells"]["age"] = "未报告"
        self.put("similar-cases.json", table)
        self.put("timeline.csv", TIMELINE.replace("admitted on 14 March 2025 with", "admitted with").replace(
            "Day 3,drug X stopped,notes.md line 7,\"drug X stopped; topical corticosteroid started\",,\n", "").replace(
            "Day 2,biopsy,notes.md line 5,\"punch biopsy from the left forearm\",,\n", "Day 2,biopsy,notes.md line 5,\"punch biopsy "
            "from the left forearm\",,\nDay 3,drug X stopped,notes.md line 7,\"drug X stopped; topical corticosteroid started\",,\n"))
        self.put("captions.md", CAPTIONS.replace("J.N.'s forearm", "Forearm"))
        (self.dir / "figures" / "IMG_4471203.jpg").rename(self.dir / "figures" / "figure1.jpg")
        self.put("figures/figure1.jpg", b"\xff\xd8\xff\xd9")
        code, result, failed, rows = self.check()
        self.assertEqual((code, failed), (0, set()))
        self.assertEqual(rows[("similar_case_count", "draft")], ("pass", "The draft's count equals the 3 rows."))
        self.assertEqual(result["rarity_bound_to_a_search"], 1)                  # "earlier report" is bound to the dated search
        self.assertEqual(rows[("placeholders", "draft")][0], "not_checked")
        code, _, failed, rows = self.check("--final")                            # an unknown consent fails a final run
        self.assertEqual((code, failed), (1, {"consent_record", "placeholders"}))

    def test_timeline_relative_times_quotes_and_exact_dates(self):
        self.put("timeline.csv", "time;event;where;quote;exact_date;approved_by\n"
                                 "3天前;皮疹出现;notes 第4行;双前臂及躯干出现泛发性瘙痒性皮疹;;\n"
                                 "第0天;入院;notes 第4行;患者自述既往无药物过敏史;2025年3月14日;corresponding author, consent form\n"
                                 "Week 6;resolved;notes line 9;eruption fully resolved without any scarring;;\n"
                                 "when admitted;x;notes;biopsy from the left forearm;15/03/2025;\n"
                                 "Month 2;x;;drug X stopped;;\n")
        self.put("draft.md", "Admitted on 14 March 2025 (Day 0).\n")
        code, result, failed, rows = self.check()
        self.assertEqual(rows[("timeline_times", "timeline.csv")][1], "line 5: not a relative time (Day 0, Week 6, 第6周, 3天前).")
        self.assertEqual(rows[("timeline_order", "timeline.csv")][0], "pass")                    # 3 days before day 0 comes first
        self.assertEqual(rows[("timeline_quotes", "timeline.csv")][1],
                         "line 3: not found in the notes (ABSENT); line 4: not found in the notes (PARTIAL); "
                         "line 6: no location in the notes.")
        self.assertEqual(rows[("exact_dates", "timeline.csv")][1], "line 5: an exact date that no one approved (approved_by is empty).")
        self.assertEqual({(h["file"].rsplit("/", 1)[-1], h["state"]) for h in result["hits"]},
                         {("draft.md", "approved"), ("timeline.csv", "approved"), ("timeline.csv", "hit")})
        self.run_cli("check")                                                    # without notes, only the form is checked
        self.assertEqual(self.rows()[("timeline_quotes", "timeline.csv")], ("fail", "line 6: no location in the notes."))
        self.put("timeline.csv", "time,event,where,quote\nDay 0,eruption,notes line 3,widespread itchy eruption\n")
        self.run_cli("check")
        self.assertEqual(self.rows()[("timeline_quotes", "timeline.csv")][0], "not_checked")

    def test_consent_statements_come_from_the_record(self):
        self.put("draft.md", "A case.\n\nFigure 1. The forearm.\n")
        cases = (
            ({"status": "obtained", "given_by": "patient", "scope": ["text", "images"], "form": "written", "source": "clinic file"},
             "Written informed consent for publication of this case report and the accompanying images was obtained from the patient."),
            ({"status": "obtained", "given_by": "next_of_kin", "relationship": "daughter", "scope": ["text"],
              "form": "verbal_documented", "source": "ward record"},
             "Verbal informed consent for publication of this case report was obtained from the patient's daughter and recorded "
             "in the medical record."),
            ({"status": "obtained", "given_by": "parent_or_guardian", "scope": ["text", "images", "video"], "form": "written",
              "source": "x", "language": "zh"}, "已获得患者的父母或监护人的书面知情同意，同意发表本病例报告及所附图片和视频。"),
            ({"status": "waived", "waived_by": "the research ethics committee", "reason": "the patient died and no relative could be "
              "traced", "source": "committee letter"}, "The requirement to obtain consent for publication was waived by the research "
                                                       "ethics committee (the patient died and no relative could be traced)."),
            ({"status": "not_obtained", "reason": "the patient declined", "language": "zh"}, "未获得发表本病例报告的知情同意（the patient declined）。"))
        for record, sentence in cases:
            with self.subTest(sentence):
                self.put("consent.json", record)
                code, result, failed, rows = self.check()
                self.assertEqual(result["consent_statement"], sentence)
                self.assertEqual(rows[("consent_statement", "draft")][0], "fail")             # not yet in the draft
                self.assertEqual("consent_scope" in failed, record.get("scope") == ["text"])   # figures need images in the scope
                self.put("draft.md", f"A case.\n\nFigure 1. The forearm.\n\n{sentence}\n")
                self.assertEqual(self.check()[3][("consent_statement", "draft")][0], "pass")
        self.put("consent.json", {"status": "obtained", "given_by": "the patient", "scope": "all", "form": "written"})
        rows = self.check()[3]
        self.assertEqual(rows[("consent_record", "consent.json")], ("fail", "source is missing (references/consent.md)."))
        self.put("consent.json", {"status": "unknown"})
        self.put("draft.md", "Consent: we obtained written consent from the patient.\n")
        self.assertEqual(self.check()[3][("consent_statement", "draft")],
                         ("fail", "The draft says that consent was obtained; consent.json says unknown."))

    def test_similar_cases_come_only_from_saved_searches(self):
        self.cr1()
        searches = copy.deepcopy(SEARCHES)
        searches["searches"].append({"id": "s2", "query": "drug X exanthem case reports", "total": 9, "date": "18 Nov",
                                     "file": "searches/s1.json"})
        searches["searches"].append({"id": "s3", "query": "drug X rash case report", "total": 5, "date": "2026-11-18",
                                     "file": "searches/s1.json"})
        self.put("searches.json", searches)
        table = copy.deepcopy(TABLE)
        table["rows"][0]["cells"]["onset"] = {"value": "8 weeks", "quote": "six weeks after starting drug X"}
        table["rows"][2]["cells"]["onset"] = {"value": "2 weeks"}
        table["rows"][3].update({"search": "s9"})
        table["rows"].append({"id": "r5", "search": "s1", "doi": "10.1000/case.4", "cells": ["not", "an", "object"]})
        self.put("similar-cases.json", table)
        self.put("draft.md", "The searches in Table S1 found five case reports. 检索共找到五篇报告。\n")
        code, result, failed, rows = self.check()
        self.assertEqual(rows[("searches", "searches.json")][1], "s2: total must be the number the search returned, date YYYY-MM-DD; "
                                                                 "s3: total 5 in the log, 4 in the saved result.")
        self.assertEqual(rows[("similar_case_rows", "similar-cases.json")][1],
                         "r4: its search is not a logged search with a saved result.")
        self.assertEqual(rows[("similar_case_cells", "similar-cases.json")][1],
                         "r1 / onset: a number of the value is not in its quote; r2 / age: the quote is not in the source (ABSENT); "
                         "r3 / onset: the quote is missing; r5 / age: no value (write \"not reported\" when the source does not "
                         "give it); r5 / onset: no value (write \"not reported\" when the source does not give it).")
        self.assertEqual(rows[("similar_case_count", "draft")], ("pass", "The draft's count equals the 5 rows."))
        self.put("draft.md", "The search (Table S1) found 3 similar case reports, so only 3 cases have been reported.\n")
        code, result, failed, rows = self.check()
        self.assertEqual(rows[("similar_case_count", "draft")], ("fail", "The table has 5 rows; line 1 says 3; line 1 says 3."))
        self.assertIn("rarity", [x["lead"] for x in result["leads"]])                               # "only 3 cases"
        (self.dir / "similar-cases.json").unlink()
        self.assertEqual(self.check()[3][("similar_cases", "similar-cases.json")][0], "not_checked")


class NoValueLeaksTests(Base):
    PLANTED = ("Jana", "Novak", "Novák", "J.N.", "4471203", "00881", "Riverside", "Lakeport", "诺娃克", "滨江", "92-year-old", "92岁",
               "14 March", "2025年3月14日", "2025:03:14", "7946", "jana.novak", "192.0.2.44", "Ferry Company", "lakeport.example")

    def test_no_planted_value_reaches_stdout_stderr_or_any_report(self):
        self.cr1()
        loaded = ("Mrs Jana Novák (J.N., 92-year-old, 92岁) of Lakeport, MRN 4471203, test RX-2025-00881, 诺娃克, 滨江总医院, "
                  "Riverside General Hospital, Lakeport Ferry Company, admitted 14 March 2025 / 2025年3月14日, tel +44 20 7946 0958, "
                  "jana.novak@lakeport.example, https://lakeport.example/jana, 192.0.2.44.\n")
        self.notes.write_text(NOTES + loaded, encoding="utf-8")
        self.put("draft.md", DRAFT + loaded)
        self.put("captions.md", CAPTIONS + loaded)
        self.put("timeline.csv", TIMELINE + f'Week 7,"{loaded.strip()}",notes.md,"{loaded.strip()}",14 March 2025,\n')
        self.put("figures/Novak_2025-03-14_4471203.png", b"\x89PNG\r\n\x1a\n" + loaded.encode())
        self.put("notes2.docx", docx([loaded], comments=[("Jana Novak", "JN", loaded)], core=f"<p><creator>{loaded}</creator></p>"))
        outputs = []
        for argv in (("scan", self.notes, self.dir / "notes2.docx", self.dir / "figures"),
                     ("check", "--notes", self.notes), ("check", "--notes", self.notes, "--final"),
                     ("check", "--draft", self.dir / "notes2.docx"), ("scan", self.root / "Novak 4471203.md")):
            code, _ = self.run_cli(*argv)
            self.assertIn(code, (1, 2))
            outputs += [self.out, self.err]
        outputs += [(self.dir / name).read_text(encoding="utf-8") for name in ("scan.md", "check.md", "check.json")]
        self.assertGreater(sum(len(json.loads(o)["hits"]) for o in outputs[:6:2] if o), 40)   # the identifiers were found...
        for value in self.PLANTED:
            for output in outputs:
                self.assertNotIn(value, output)                                            # ...and never printed


if __name__ == "__main__":
    unittest.main()
