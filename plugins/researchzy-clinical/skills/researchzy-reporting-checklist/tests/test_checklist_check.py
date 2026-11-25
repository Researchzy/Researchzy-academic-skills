"""checklist_check.py: the checklist is registered from its own file, and every place in the filled
checklist is a quote found on its page. The planted problems of real task RC-1, on a fictional
checklist (checklist_fixture.py), are marked RC-1/n."""
from __future__ import annotations

import copy
import csv
import hashlib
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


cc = load("checklist_check", HERE.parent / "scripts" / "checklist_check.py")
fx = load("checklist_fixture", HERE / "checklist_fixture.py")
ADD = "Put a fact only the authors have in a placeholder, [Author input needed: ...]"


def item(container: dict, iid: str) -> dict:
    return next(i for i in container["items"] if i["id"] == iid)


def found(rows: list, check: str, status: str = "fail") -> list:
    return [(r["where"], r["detail"]) for r in rows if r["check"] == check and r["status"] == status]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *argv) -> tuple:
        out = io.StringIO()
        with redirect_stdout(out):
            code = cc.main([str(a) for a in argv])
        return code, json.loads(out.getvalue())

    def build(self, edit=None, reg_edit=None, source="docx", register=True) -> Path:
        """The fixture with filled.json and checklist.json edited; registered unless asked not to."""
        reg, filled = fx.checklist(f"source/eorc-1.0.{source}"), copy.deepcopy(fx.FILLED)
        for change, data in ((edit, filled), (reg_edit, reg)):
            if change:
                change(data)
        base = fx.build(self.dir, source, reg=reg, filled=filled)
        if register:
            self.cli("register", "--dir", base)
        return base

    def rerecord(self, base: Path, name: str = "manuscript") -> None:
        """Record the current SHA-256 of a document in filled.json, as the agent does after rereading."""
        filled = json.loads((base / "filled.json").read_text(encoding="utf-8"))
        document = next(d for d in filled["documents"] if d["id"] == name)
        document["sha256"] = hashlib.sha256((base / document["path"]).read_bytes()).hexdigest()
        (base / "filled.json").write_text(json.dumps(filled, ensure_ascii=False), encoding="utf-8")


class RegisterTests(Base):
    def rows(self, reg_edit=None, source="docx") -> list:
        return cc.run_register(self.build(reg_edit=reg_edit, source=source, register=False))[0]

    def test_every_table_format_gives_the_same_twelve_items(self):
        for source in ("docx", "html", "xml", "csv"):
            with self.subTest(source=source):
                base = fx.build(self.dir / source, source)
                found_items = dict(cc.items_from(cc.read_source(base / "source" / f"eorc-1.0.{source}")[1]))
                self.assertEqual(list(found_items), list(fx.TOPICS))
                self.assertTrue(found_items["9"].endswith("from eligibility to analysis"))   # footnote mark left out
                code, summary = self.cli("register", "--dir", base)
                self.assertEqual((code, summary["fail"], summary["not_checked"], summary["file_rows"]), (0, 0, 0, 12))
        report = (base / "register.md").read_text(encoding="utf-8")
        self.assertIn('Licence printed on the file: "For non-commercial reproduction only" (footer).', report)   # RC-1/11
        self.assertIn('Journal: "a completed EORC checklist (version 1.0) with page numbers"', report)

    def test_a_row_left_out_and_a_version_from_memory_fail(self):     # RC-1/1 and RC-1/2
        def edit(reg):
            reg["items"] = [i for i in reg["items"] if i["id"] != "8b"]
            reg["version"] = "2.0"
            item(reg, "7")["text"] = "Say how the sample size was calculated and justified"
        rows = self.rows(edit)
        self.assertEqual(found(rows, "count"), [("items", "the file has 12 item rows; checklist.json registers 11")])
        self.assertEqual(found(rows, "ids"), [("items", "in the file, not registered: 8b")])
        self.assertEqual(found(rows, "version"), [("version", "'2.0' is not printed in the file: write it as the file "
                                                              "prints it")])
        self.assertEqual(found(rows, "wording"), [("item 7", 'differs from the file at word 4: the file has "number of '
                                                             'participants was decided", the registration "sample size was '
                                                             'calculated and"')])

    def test_the_journal_version_is_compared_and_never_replaced(self):    # RC-1/1
        def asks(version, decision="", source="journal-instructions.txt"):
            def edit(reg):
                reg["journal"].update(version=version, user_decision=decision, source=source,
                                      quote=f"a completed EORC checklist (version {version}) with page numbers")
            return edit

        def rows(edit, instructions="0.9"):
            base = self.build(reg_edit=edit, register=False)
            (base / "journal-instructions.txt").write_text(fx.JOURNAL_TEXT.replace("1.0", instructions), encoding="utf-8")
            return cc.run_register(base)[0]

        older = rows(asks("0.9"))
        self.assertEqual(found(older, "journal_version"), [("journal", "the journal asks for 0.9; the file prints 1.0. Tell "
                         "the user and replace neither; record their decision in journal.user_decision")])
        self.assertEqual(found(older, "version") + found(older, "wording"), [])
        decided = rows(asks("0.9", "Use the 1.0 file: the editor confirmed it on 2026-11-18"))
        self.assertIn("The user decided: Use the 1.0 file", found(decided, "journal_version", "ok")[0][1])
        self.assertEqual(found(rows(asks("0.9"), instructions="1.0"), "journal"),
                         [("journal", "the quote is not in journal-instructions.txt: copy the journal's words again")])

        def no_version_in_quote(reg):
            reg["journal"]["version"] = "0.9"
        self.assertEqual(found(rows(no_version_in_quote), "journal"),
                         [("journal", "the version '0.9' is not in the journal's quote")])
        web = rows(asks("1.0", source="https://journal.example.org/authors"), instructions="1.0")
        self.assertEqual(found(web, "journal", "not_checked"), [("journal", "https://journal.example.org/authors is not a "
                                                                            "saved text file: the quote was not compared")])
        silent = rows(lambda reg: reg.update(journal="not_stated"))
        self.assertEqual([r["status"] for r in silent if r["check"].startswith("journal")], ["not_checked"])

    def test_cohort_items_must_not_carry_case_control_wording(self):     # RC-1/10
        def edit(reg):
            item(reg, "5a")["text"] = fx.CASE_WORDING["5a"]
            item(reg, "8b")["text"] = f"{fx.COHORT}: {fx.COHORT_WORDING['8b']} {fx.CASE}: {fx.CASE_WORDING['8b']}"
            item(reg, "5b")["text"] = f"{fx.COHORT}: {fx.COHORT_WORDING['5b']}"      # the label may stay
        self.assertEqual(found(self.rows(edit), "wording"), [
            ("item 5a", "has the wording for Case-control study; this registration is for Cohort study"),
            ("item 8b", "has the wording of every design: register only the Cohort study part")])

        def case_control(reg):
            reg["variant"] = fx.CASE
            for entry in reg["items"]:
                entry["text"] = fx.CASE_WORDING.get(entry["id"], entry["text"])
        self.assertEqual(found(self.rows(case_control), "wording"), [])
        self.assertEqual(found(self.rows(lambda reg: reg.update(variant="Cross-sectional study")), "fields"),
                         [("checklist.json", "variant must be one of variant_labels")])

    def test_the_licence_is_recorded_as_printed(self):      # RC-1/11
        rows = self.rows(lambda reg: reg["licence"].update(text="Free to copy and adapt"))
        self.assertEqual(found(rows, "licence"), [("licence", "not in the file: copy the statement as the file prints it")])
        rows = self.rows(lambda reg: reg.update(licence="not_stated"))
        self.assertEqual(found(rows, "licence", "not_checked"),
                         [("licence", "no licence statement recorded: the wording is not cleared for sharing")])

    def test_a_text_file_has_no_rows_so_only_the_wording_is_compared(self):
        rows = self.rows(source="txt")
        self.assertEqual(found(rows, "ids", "not_checked"),
                         [("items", "no item rows in the text file: ids, count and design wording not compared")])
        self.assertEqual(len(found(rows, "wording", "ok")), 12)
        rows = self.rows(lambda reg: item(reg, "7").update(text="Say how the sample size was calculated"), "txt")
        self.assertEqual(found(rows, "wording"), [("item 7", "not in the file: copy the wording as printed")])

    def test_the_source_file_and_the_fields(self):
        base = fx.build(self.dir, hashes=False)
        digest = hashlib.sha256((base / "source" / "eorc-1.0.docx").read_bytes()).hexdigest()
        self.assertEqual(found(cc.run_register(base)[0], "source_file"),
                         [("source/eorc-1.0.docx", f"no SHA-256 recorded: record {digest}")])

        def edit(reg):
            reg["source"]["read"] = "18/11/2026"
            item(reg, "3")["topic"] = "A topic that runs on well past the sixty characters allowed for it"
            item(reg, "7")["topic"] = "Say how the number of participants"
            reg["items"].append({"id": "1(a)", "topic": "Again", "text": ""})
            del reg["extension_of"]
        self.assertEqual(found(self.rows(edit), "fields"), [("checklist.json", "extension_of must be \"none\" or the base "
                         "guideline's name and version; source.read must be the date read (YYYY-MM-DD); item 3: needs a "
                         "topic of at most 60 characters and its text as printed; item 7: the topic repeats the item's "
                         "wording; name the item in your own words; every item needs its own id: 1a")])

    def test_a_chinese_checklist_with_full_width_design_labels(self):
        rows = [["报告规范示例（虚构），版本 1.0"], ["部分", "编号", "条目"],
                ["方法", "5", "(a) 队列研究：说明谁可以加入队列以及如何随访\n病例对照研究：说明如何找到病例以及如何选择对照"],
                ["", "6", "给出每个结局和暴露的定义"]]

        def register(text_5a):
            base = fx.build(self.dir)
            out = io.StringIO()
            csv.writer(out).writerows(rows)
            (base / "source" / "zh.csv").write_text(out.getvalue(), encoding="utf-8")
            reg = {"name": "报告规范示例", "version": "1.0", "variant": "队列研究", "variant_labels": ["队列研究", "病例对照研究"],
                   "extension_of": "none", "journal": "not_stated", "licence": "not_stated",
                   "source": {"path": "source/zh.csv", "read": "2026-11-18", "type": "file",
                              "sha256": hashlib.sha256((base / "source" / "zh.csv").read_bytes()).hexdigest()},
                   "items": [{"id": "5a", "topic": "研究对象", "text": text_5a}, {"id": "6", "topic": "定义", "text": "给出每个结局和暴露的定义"}]}
            (base / "checklist.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
            return cc.run_register(base)[0]

        clean = register("队列研究：说明谁可以加入队列以及如何随访")
        self.assertEqual([r for r in clean if r["status"] == "fail"], [])
        self.assertEqual(found(register("说明如何找到病例以及如何选择对照"), "wording"),
                         [("item 5a", "has the wording for 病例对照研究; this registration is for 队列研究")])


class CheckTests(Base):
    def rows(self, edit=None) -> list:
        return cc.run_check(self.build(edit))[0]

    def test_a_sound_checklist_passes(self):      # RC-1/7: an item reported only in Table S2
        base = self.build()
        code, summary = self.cli("check", "--dir", base)
        self.assertEqual((code, summary["fail"], summary["not_checked"], summary["not_reviewed"]), (0, 0, 1, 12))
        self.assertEqual(summary["by_status"], {"reported": 9, "partly_reported": 1, "not_applicable": 1, "not_reported": 1})
        rows = cc.run_check(base)[0]
        self.assertIn(("item 6", "EXACT in the supplement"), found(rows, "quote", "ok"))
        self.assertIn(("item 6", "page 2"), found(rows, "page", "ok"))
        self.assertIn(("item 1a", "lines 1-2"), found(rows, "lines", "ok"))    # the page number at the foot is no line
        report = (base / "check.md").read_text(encoding="utf-8")
        self.assertIn("Items by status: 9 reported, 1 partly reported, 1 not reported, 1 not applicable. No score.", report)
        self.assertIn("- lines: the supplement carries no line numbers (item 6)", report)

    def test_a_reported_item_needs_a_page_and_a_place(self):     # RC-1/3
        def edit(filled):
            item(filled, "3")["locations"][0].update(page="", lines="", where="Introduction, paragraph 3")
            item(filled, "2")["locations"][0].update(page="p. 2")
            item(filled, "9")["locations"] = []
        rows = self.rows(edit)
        self.assertEqual(found(rows, "page"), [
            ("item 2", "page 'p. 2' is not a number or a range such as 8-9; the quote is on page 2"),
            ("item 3", "no page: give the page number of the document; the quote is on page 2")])
        self.assertEqual(found(rows, "complete"), [("item 9", "a reported item needs a place: document, page and quote")])

    def test_a_paraphrase_or_a_short_quote_is_not_a_quote(self):     # RC-1/4
        def edit(filled):
            item(filled, "2")["locations"][0]["quote"] = "Little is known about the light that shift workers get on wards"
            item(filled, "3")["locations"][0]["quote"] = ("We asked whether evening light at work predicts poorer sleep two "
                                                          "years later")
            item(filled, "1a")["locations"][0]["quote"] = "a prospective cohort study"
            item(filled, "1b")["locations"][0]["quote"] = "We followed 412 hospital shift workers ... than those with the least"
        self.assertEqual(found(self.rows(edit), "quote"), [
            ("item 1a", "quote at least 5 words or 12 CJK characters, word for word"),
            ("item 1b", "a quote is one passage, without an ellipsis: give each passage as its own place"),
            ("item 2", "not in the manuscript (ABSENT)"),
            ("item 3", "only partly found (PARTIAL): copy the passage word for word; a paraphrase is not a quote")])

    def test_the_quote_must_be_on_the_page_given(self):     # RC-1/5
        across = "later, and we stated in advance that we expected a dose-response pattern. Methods The study took place"

        def edit(filled):
            item(filled, "9")["locations"][0].update(page=6, lines="")
            item(filled, "3")["locations"][0].update(quote=across, page=2, lines="")
        rows = self.rows(edit)
        self.assertEqual(found(rows, "page"), [
            ("item 3", "not on page 2; no single page holds it: give the range, as 8-9"),
            ("item 9", "not on page 6; the quote is on page 9")])
        span = f"{fx.LINE[(2, 6)]}-{fx.LINE[(3, 1)]}"
        rows = self.rows(lambda filled: item(filled, "3")["locations"][0].update(quote=across, page="2-3", lines=span))
        self.assertEqual(found(rows, "page") + found(rows, "lines"), [])

    def test_lines_are_checked_when_the_document_has_them(self):
        def lines(value):
            return lambda filled: item(filled, "1b")["locations"][0].update(lines=value)
        self.assertEqual(found(self.rows(lines("20-21")), "lines"), [("item 1b", "not at lines 20-21: the quote is at lines 4-5")])
        self.assertEqual(found(self.rows(lines("")), "lines"), [("item 1b", "the page carries line numbers: give them as a "
                                                                            "number or a range such as 112-118 (the quote is at lines 4-5)")])
        self.assertEqual(found(self.rows(lines("3-6")), "lines"), [])
        base = self.build()
        (base / "manuscript.txt").write_text("\f".join("\n".join(page) for page in fx.MAIN), encoding="utf-8")
        self.rerecord(base)
        rows = cc.run_check(base)[0]
        self.assertEqual(found(rows, "lines"), [])
        self.assertIn(("item 1b", "the manuscript carries no line numbers"), found(rows, "lines", "not_checked"))

    def test_not_applicable_needs_a_reason(self):     # RC-1/6
        for reason in ("", "N/A", "[Author input needed: why it does not apply]"):
            with self.subTest(reason=reason):
                rows = self.rows(lambda filled: item(filled, "5b").update(reason=reason))
                self.assertEqual(found(rows, "reason"), [("item 5b", "give the reason this item does not apply to this study")])
        self.assertEqual(found(self.rows(), "reason", "ok"), [("item 5b", "")])

    def test_suggestions_hold_no_fact_that_is_not_in_the_documents(self):     # RC-1/8
        def suggest(text):
            return lambda filled: item(filled, "4").update(suggestion=text)
        rows = self.rows(suggest("Give the 95% confidence interval for each estimate."))
        self.assertEqual([w for w, _ in found(rows, "suggestion", "not_checked")], ["item 4"])
        self.assertEqual(found(rows, "suggestion"), [])          # a convention is not a failure
        rows = self.rows(suggest("State that the Riverside ethics committee approved the study (approval 2023-114)."))
        self.assertEqual(found(rows, "suggestion"), [("item 4", f"not in the documents: 2023-114. {ADD}")])
        rows = self.rows(suggest("Give the registration, NCT01234567, and the date of approval, 12 March 2019."))
        self.assertEqual(found(rows, "suggestion"), [("item 4", f"not in the documents: 12 March 2019; NCT01234567. {ADD}")])
        for fine in ("State that the [Author input needed: name of the ethics committee and approval number] approved it.",
                     "Say for item 8b and in Table S2 that all 530 eligible workers from March 2019 were invited.",
                     "Give the period in the abstract as well: 2019年3月 to February 2021."):
            with self.subTest(suggestion=fine):
                self.assertEqual(found(self.rows(suggest(fine)), "suggestion"), [])

    def test_a_changed_manuscript_must_be_reread(self):     # RC-1/9
        base = self.build()
        with open(base / "manuscript.txt", "a", encoding="utf-8") as handle:
            handle.write("A paragraph added after the checklist was filled.\n")
        self.assertEqual(found(cc.run_check(base)[0], "document"), [("document manuscript", "changed after filled.json was "
                         "written: reread every item against this version, statuses as well as quotes, then record the new hash")])
        self.assertEqual(self.cli("export", "--dir", base)[0], 1)
        self.assertFalse((base / "checklist-filled.md").exists())
        rows = cc.run_check(fx.build(self.dir / "unhashed", hashes=False))[0]
        self.assertIn(("document manuscript", "no SHA-256 recorded: run hash and record it"), found(rows, "document"))

    def test_every_registered_item_is_filled_once(self):
        def edit(filled):
            filled["items"] = [e for e in filled["items"] if e["id"] != "7"]
            filled["items"] += [copy.deepcopy(item(filled, "9")), dict(item(filled, "1a"), id="12z")]
        self.assertEqual(found(self.rows(edit), "items"), [("item 7", "not in filled.json"), ("item 9", "filled 2 times"),
                                                           ("item 12z", "not an item of the registered checklist")])

    def test_the_registration_must_pass_on_the_files_as_they_are(self):
        message = ("checklist.json", "run register: it has not passed on checklist.json as it is now")
        self.assertEqual(found(cc.run_check(self.build(register=False))[0], "registration"), [message])
        base = self.build()
        reg = json.loads((base / "checklist.json").read_text(encoding="utf-8"))
        item(reg, "2")["topic"] = "Known and unknown"
        (base / "checklist.json").write_text(json.dumps(reg), encoding="utf-8")
        self.assertEqual(found(cc.run_check(base)[0], "registration"), [message])
        base = self.build()
        with open(base / "source" / "eorc-1.0.docx", "ab") as handle:
            handle.write(b"\0")
        self.assertEqual(found(cc.run_check(base)[0], "source_file"), [("checklist source", "missing, or changed after "
                         "registration: register the checklist again from the file as it is now")])

    def test_a_chinese_manuscript_with_chinese_quotes(self):
        def place(page, quote):
            return [{"document": "manuscript", "page": page, "quote": quote}]

        def edit(filled):
            item(filled, "4").update(locations=place(2, "研究在虚构城市湖港的三家医院进行"),          # a line break inside
                                     suggestion="写明伦理委员会批准号2023-114和批准日期２０２３年３月１日")
            item(filled, "1b")["locations"] = place(1, "我们随访了412名医院轮班工人两年")
            item(filled, "9")["locations"] = place(2, "530名符合条件的工人中，共纳入412名工人")
            item(filled, "1a")["locations"] = place(1, "一项前瞻性队列研究")
            item(filled, "7")["suggestion"] = "补充说明412名工人是如何确定的：［Author input needed：确定人数的方法］"
            item(filled, "5b")["reason"] = "不适用"
        base = self.build(edit)
        (base / "manuscript.txt").write_text(fx.CHINESE, encoding="utf-8")
        self.rerecord(base)
        rows = [r for r in cc.run_check(base)[0] if r["where"] in ("item 1a", "item 1b", "item 4", "item 5b", "item 7", "item 9")]
        self.assertEqual(found(rows, "quote"), [("item 1a", "quote at least 5 words or 12 CJK characters, word for word")])
        self.assertEqual(found(rows, "page"), [("item 9", "not on page 2; the quote is on page 3")])
        self.assertEqual(found(rows, "page", "ok"), [("item 1b", "page 1"), ("item 4", "page 2")])
        self.assertEqual(found(rows, "lines", "not_checked"), [("item 1b", "the manuscript carries no line numbers"),
                                                               ("item 4", "the manuscript carries no line numbers")])
        self.assertEqual(found(rows, "suggestion"), [("item 4", f"not in the documents: 2023年3月1日; 2023-114. {ADD}")])
        self.assertEqual(found(rows, "suggestion", "ok"), [("item 7", "")])
        self.assertEqual(found(rows, "reason"), [("item 5b", "give the reason this item does not apply to this study")])
        filled = json.loads((base / "filled.json").read_text(encoding="utf-8"))
        item(filled, "5b")["reason"] = "本队列未按任何特征匹配"
        (base / "filled.json").write_text(json.dumps(filled, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(found(cc.run_check(base)[0], "reason", "ok"), [("item 5b", "")])


class ExportTests(Base):
    def test_export_waits_for_a_clean_check(self):
        base = self.build(lambda filled: item(filled, "9")["locations"][0].update(page=6))
        code, summary = self.cli("export", "--dir", base)
        self.assertEqual((code, summary["exported"]), (1, False))
        self.assertFalse(any((base / name).exists() for name in ("checklist-filled.md", "checklist-filled.csv", "gaps.md")))

    def test_the_upload_list_carries_places_but_never_the_wording(self):     # RC-1/11
        base = self.build()
        code, summary = self.cli("export", "--dir", base)
        self.assertEqual((code, summary["gaps"], summary["by_status"]["reported"]), (0, 2, 9))
        filled = (base / "checklist-filled.md").read_text(encoding="utf-8")
        for line in (f"| 9 | Numbers at each step | Reported | p. 9, lines {fx.lines(9, 1, 2)} (Results) |",
                     "| 6 | Definitions | Reported | Supplement p. 2 (Table S2) |", "| 5b | Matching | Not applicable | Not applicable |",
                     'Licence printed on the checklist file: "For non-commercial reproduction only".'):
            self.assertIn(line, filled)
        rows = list(csv.reader(io.StringIO((base / "checklist-filled.csv").read_text(encoding="utf-8"))))
        self.assertEqual(rows[0], ["item", "topic", "status", "where_reported"])
        self.assertEqual(rows[8], ["6", "Definitions", "Reported", "Supplement p. 2 (Table S2)"])
        gaps = (base / "gaps.md").read_text(encoding="utf-8")
        self.assertIn("- 7: [Author input needed: how the number of participants was decided]", gaps)
        self.assertIn("- 5b (Matching): The cohort was not matched on any characteristic", gaps)
        for name in ("checklist-filled.md", "checklist-filled.csv", "gaps.md"):
            text = (base / name).read_text(encoding="utf-8")
            for wording in [*fx.COHORT_WORDING.values(), *fx.CASE_WORDING.values()]:
                self.assertNotIn(wording, text, name)


class InputTests(Base):
    def test_hash_and_inputs_that_cannot_be_read(self):
        base = self.build()
        path = base / "manuscript.txt"
        code, summary = self.cli("hash", path)
        self.assertEqual((code, summary["sha256"][str(path)]), (0, hashlib.sha256(path.read_bytes()).hexdigest()))
        for argv, broken, message in (
                (["hash", base / "none.txt"], None, "no such file"),
                (["check", "--dir", self.dir / "empty"], None, "does not exist"),
                (["check", "--dir", base], ("manuscript.txt", b"%PDF-1.7"), "is a PDF. Make it text first"),
                (["check", "--dir", base], ("filled.json", b"{not json"), "is not valid JSON"),
                (["register", "--dir", base], ("source/eorc-1.0.docx", b"\xd0\xcf\x11\xe0 old"), "is not a readable .docx")):
            if broken:
                (base / broken[0]).write_bytes(broken[1])
            err = io.StringIO()
            with self.subTest(argv=argv), redirect_stderr(err), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as stop:
                cc.main([str(a) for a in argv])
            self.assertEqual(stop.exception.code, 2)
            self.assertIn(message, err.getvalue())
        (base / "eorc.doc").write_bytes(b"\xd0\xcf\x11\xe0 an old Word file")
        with redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            cc.read_source(base / "eorc.doc")
        self.assertIn("is an old Word .doc file. Save it as .docx", err.getvalue())


if __name__ == "__main__":
    unittest.main()
