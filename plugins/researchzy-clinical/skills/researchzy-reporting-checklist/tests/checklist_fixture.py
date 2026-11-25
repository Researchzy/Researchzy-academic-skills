"""A wholly fictional checklist, manuscript and supplement for the tests. The Example Observational
Reporting Checklist (EORC) does not exist: its twelve items, its version and its licence line were
written for these tests, and no sentence of the manuscript comes from a real paper."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

COHORT, CASE = "Cohort study", "Case-control study"
TITLE = "Example Observational Reporting Checklist (EORC), version 1.0. A fictional checklist made for tests."
LICENCE = "EORC version 1.0 (fictional). For non-commercial reproduction only."
# (section, id cell, the item cell's lines as the file prints them)
ROWS = [
    ("Title and abstract", "1", ["(a) Say in the title or the abstract what kind of study this is"]),
    ("", "", ["(b) Summarise in the abstract what was done and what was found"]),
    ("Introduction", "2", ["Describe what was already known and the gap this study fills"]),
    ("", "3", ["List each question the study set out to answer, with any hypothesis named in advance"]),
    ("Methods", "4", ["Name the place, the calendar period and the ethics body that approved the study"]),
    ("", "5", [f"(a) {COHORT}: Say who could join the cohort and how members were followed over time",
               f"{CASE}: Say how cases were found and how the comparison group was drawn",
               f"(b) {COHORT}: If members were matched, say on what and how many were in each exposure group",
               f"{CASE}: If cases were matched, say on what and how many comparison people each case had"]),
    ("", "6", ["Give a definition for each outcome, each exposure and each possible confounder"]),
    ("", "7", ["Say how the number of participants was decided"]),
    ("", "8a", ["Name the statistical methods used for each question, including any adjustment"]),
    ("", "8b", [f"{COHORT}: Say how people who left the cohort early were handled",
                f"{CASE}: Say how the matching was handled in the analysis"]),
    ("Results", "9", ["Give the number of people at each step from eligibility to analysis"]),
]
TOPICS = {"1a": "Design named", "1b": "Abstract", "2": "Background", "3": "Questions", "4": "Setting, period, approval",
          "5a": "Who took part", "5b": "Matching", "6": "Definitions", "7": "Study size", "8a": "Statistical methods",
          "8b": "Leaving early", "9": "Numbers at each step"}
COHORT_WORDING = {
    "1a": "Say in the title or the abstract what kind of study this is",
    "1b": "Summarise in the abstract what was done and what was found",
    "2": "Describe what was already known and the gap this study fills",
    "3": "List each question the study set out to answer, with any hypothesis named in advance",
    "4": "Name the place, the calendar period and the ethics body that approved the study",
    "5a": "Say who could join the cohort and how members were followed over time",
    "5b": "If members were matched, say on what and how many were in each exposure group",
    "6": "Give a definition for each outcome, each exposure and each possible confounder",
    "7": "Say how the number of participants was decided",
    "8a": "Name the statistical methods used for each question, including any adjustment",
    "8b": "Say how people who left the cohort early were handled",
    "9": "Give the number of people at each step from eligibility to analysis",
}
CASE_WORDING = {"5a": "Say how cases were found and how the comparison group was drawn",
                "5b": "If cases were matched, say on what and how many comparison people each case had",
                "8b": "Say how the matching was handled in the analysis"}
JOURNAL_TEXT = ("Journal of Invented Results: instructions for authors (fictional).\n"
                "Authors of observational studies must upload a completed EORC checklist (version 1.0) with page\n"
                "numbers for each item.\n")

MAIN = [
    ["Evening light at work and sleep duration in shift workers:",
     "a prospective cohort study (fictional, written for tests)",
     "",
     "Abstract",
     "We followed 412 hospital shift workers for two years and recorded how much",
     "evening light each received at work. Workers with the most evening light",
     "slept 34 minutes less per day than those with the least."],
    ["Introduction",
     "Light in the evening delays the body clock, but little is known about how",
     "much light shift workers receive on hospital wards and whether it shortens",
     "their sleep over months rather than days.",
     "",
     "We asked whether evening light at work predicts shorter sleep two years",
     "later, and we stated in advance that we expected a dose-response pattern."],
    ["Methods",
     "The study took place in three hospitals in the fictional city of Lakeport",
     "between March 2019 and February 2021.",
     "Each hospital named a coordinator who kept the list of wards."],
    ["Any nurse or porter working at least two night shifts a month could join",
     "the cohort, and members were followed with a sleep diary every three months.",
     "Diaries were returned by post or through a web form."],
    ["Light exposure was recorded with a wrist sensor during each shift.",
     "Sensors were checked against a reference meter before use.",
     "Sleep was taken from the diaries."],
    ["Data were stored on a secure server at each hospital.",
     "Only the coordinators could link diaries to names.",
     "The analysis files held study numbers only."],
    ["All eligible workers in the three hospitals were invited by letter.",
     "Reminders were sent once, after four weeks.",
     "No payment was offered."],
    ["We used mixed models with a random intercept for each worker and adjusted",
     "for age, sex and the number of night shifts.",
     "Workers who left the cohort early were kept in the analysis up to their",
     "last diary, and we compared them with those who stayed."],
    ["Results",
     "Of 530 eligible workers, 412 joined the cohort and 371 completed the",
     "final diary at two years.",
     "Their median age was 38 years."],
    ["The study was approved by the regional ethics board.",
     "References",
     "1. Example A, Example B. A fictional reference. J Fict Stud 2018;3:1-9."],
]
SUPPLEMENT = [
    ["Supplementary material (fictional)",
     "Table S1. Hospitals and wards",
     "Hospital A    4 wards",
     "Hospital B    3 wards"],
    ["Table S2. Definitions of exposure, outcome and confounders",
     "Evening light     lux measured by the wrist sensor between 18:00 and 23:00",
     "Sleep duration    hours of sleep per day in the diary, averaged over a week",
     "Confounders       age, sex and the number of night shifts a month"],
]
CHINESE = ("[[page 1]]\n夜间工作光照与轮班工人睡眠时长：一项前瞻性队列研究（为测试编写的虚构稿件）\n摘要\n"
           "我们随访了412名医院轮班工人两年，记录了每人在工作中受到的夜间光照。\n"
           "[[page 2]]\n方法\n研究在虚构城市湖港的三家医\n院进行，时间为2019年3月至2021年2月。\n"
           "每月至少上两个夜班的护士和护工均可加入队列，成员每三个月填写一次睡眠日记。\n"
           "[[page 3]]\n结果\n530名符合条件的工人中，共纳入412名工人，其中371名完成了两年时的最后一次日记。\n")


def render(pages: list) -> tuple:
    """The pages as pdftotext -layout gives a line-numbered PDF: a number before each line, the page
    number at the foot, a form feed after each page. Returns the text and {(page, index): line number}."""
    out, number, numbers = [], 0, {}
    for page, lines in enumerate(pages, 1):
        body = []
        for index, line in enumerate(lines):
            if line:
                number += 1
                numbers[(page, index)] = number
            body.append(f"{number:>3}   {line}" if line else "")
        out.append("\n".join(body) + f"\n\n{page:>40}\n")
    return "\f".join(out) + "\f", numbers


TEXT, LINE = render(MAIN)


def lines(page: int, first: int, last: int) -> str:
    return f"{LINE[(page, first)]}-{LINE[(page, last)]}"


def joined(page: int, first: int, last: int) -> str:
    return " ".join(MAIN[page - 1][first:last + 1])


def place(page, first, last, where="", quote=None, **more):
    return {"document": "manuscript", "page": page, "lines": lines(page, first, last), "where": where,
            "quote": joined(page, first, last) if quote is None else quote, **more}


def entry(item, status, places=(), **more):
    return {"id": item, "status": status, "locations": list(places), "missing": "", "suggestion": "", "reason": "",
            "assessor": "model", "checked_by": "", **more}


FILLED = {
    "documents": [{"id": "manuscript", "path": "manuscript.txt"},
                  {"id": "supplement", "path": "supplement.txt", "label": "Supplement"}],
    "items": [
        entry("1a", "reported", [place(1, 0, 1, "Title", quote="Evening light at work and sleep duration in shift "
                                                                 "workers: a prospective cohort study")]),
        entry("1b", "reported", [place(1, 4, 5, "Abstract")]),
        entry("2", "reported", [place(2, 1, 2, "Introduction")]),
        entry("3", "reported", [place(2, 5, 6, "Introduction")]),
        entry("4", "partly_reported", [place(3, 1, 2, "Methods")],
              missing="The name of the ethics body and the approval number",
              suggestion="Name the ethics body and give the approval number: "
                         "[Author input needed: name of the ethics body and approval number]"),
        entry("5a", "reported", [place(4, 0, 1, "Methods")]),
        entry("5b", "not_applicable", reason="The cohort was not matched on any characteristic"),
        entry("6", "reported", [{"document": "supplement", "page": 2, "where": "Table S2",
                                 "quote": "Evening light lux measured by the wrist sensor between 18:00 and 23:00"}]),
        entry("7", "not_reported", missing="How the number of participants was decided",
              suggestion="Say whether all 530 eligible workers were invited without a size set in advance: "
                         "[Author input needed: how the number of participants was decided]"),
        entry("8a", "reported", [place(8, 0, 1, "Statistical analysis")]),
        entry("8b", "reported", [place(8, 2, 3, "Statistical analysis")]),
        entry("9", "reported", [place(9, 1, 2, "Results")]),
    ],
}


def checklist(source: str = "source/eorc-1.0.docx") -> dict:
    return {
        "name": "Example Observational Reporting Checklist (EORC)", "version": "1.0",
        "variant": COHORT, "variant_labels": [COHORT, CASE], "extension_of": "none",
        "journal": {"name": "Journal of Invented Results", "quote": "a completed EORC checklist (version 1.0) with page "
                    "numbers", "version": "1.0", "source": "journal-instructions.txt", "read": "2026-11-18",
                    "user_decision": ""},
        "source": {"path": source, "read": "2026-11-18", "type": "file"},
        "licence": {"text": "For non-commercial reproduction only", "where": "footer"},
        "items": [{"id": i, "topic": TOPICS[i], "text": COHORT_WORDING[i]} for i in TOPICS],
    }


def docx_source(path: Path) -> None:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

    def para(text):
        return f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'

    def cell(lines):
        return "<w:tc>" + ("".join(para(line) for line in lines) or "<w:p/>") + "</w:tc>"

    rows = [["Section"], ["No."], ["Item"], ["Page"]], *([[s] if s else [], [i] if i else [], body, []] for s, i, body in ROWS)
    table = "<w:tbl>" + "".join("<w:tr>" + "".join(cell(c) for c in r) + "</w:tr>" for r in rows) + "</w:tbl>"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:document {ns}><w:body>'
                                              f"{para(TITLE)}{table}</w:body></w:document>")
        archive.writestr("word/footer1.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:ftr {ns}>{para(LICENCE)}</w:ftr>')


def html_source() -> str:
    """A saved web page: item 1's section and number span two rows, one row leaves out its end
    tags, and item 9 carries a footnote mark."""
    rows = []
    for section, rid, body in ROWS:
        text = "<br>".join(escape(line) for line in body) + ("<sup>*</sup>" if rid == "9" else "")
        if rid == "1":
            rows.append(f'<tr><td rowspan="2">{section}</td><td rowspan="2">1</td><td>{text}</td><td></td></tr>')
        elif not rid:
            rows.append(f"<tr><td>{text}</td><td></td></tr>")
        elif rid == "3":
            rows.append(f"<tr><td>{section}<td>{rid}<td>{text}<td>")
        else:
            rows.append(f"<tr><td>{section}</td><td>{rid}</td><td>{text}</td><td></td></tr>")
    return (f"<html><head><title>EORC</title><style>td {{padding: 2px}}</style></head><body><h1>{escape(TITLE)}</h1>"
            "<table><tr><th>Section</th><th>No.</th><th>Item</th><th>Page</th></tr>" + "".join(rows)
            + f"</table><p>{escape(LICENCE)}</p></body></html>")


def jats_source() -> str:
    """A JATS table: empty cells written as <td/>, line breaks as <break/>, a footnote cross-reference."""
    rows = "".join("<tr>" + (f"<td>{section}</td>" if section else "<td/>") + (f"<td>{rid}</td>" if rid else "<td/>")
                   + "<td>" + "<break/>".join(escape(line) for line in body)
                   + ('<xref ref-type="fn" rid="fn1">a</xref>' if rid == "9" else "") + "</td></tr>"
                   for section, rid, body in ROWS)
    return ('<?xml version="1.0" encoding="UTF-8"?><article><body><table-wrap id="t1"><label>Table 1</label>'
            f"<caption><p>{escape(TITLE)}</p></caption><table><thead><tr><th>Section</th><th>No.</th><th>Item</th></tr>"
            f'</thead><tbody>{rows}</tbody></table><table-wrap-foot><fn id="fn1"><p>{escape(LICENCE)}</p></fn>'
            "</table-wrap-foot></table-wrap></body></article>")


def csv_source() -> str:
    out = io.StringIO()
    csv.writer(out).writerows([[TITLE], ["Section", "No.", "Item", "Page"],
                               *([section, rid, "\n".join(body), ""] for section, rid, body in ROWS), [LICENCE]])
    return out.getvalue()


def text_source() -> str:
    """The checklist as pdftotext gives it from a PDF: no table rows to read."""
    lines = [TITLE, "", "Section              No.  Item"]
    for section, rid, body in ROWS:
        lines += [f"{section:<20} {rid:<4} {body[0]}", *(f"{'':<25} {line}" for line in body[1:])]
    return "\n".join(lines + ["", LICENCE]) + "\n"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(directory: Path, source: str = "docx", reg: dict | None = None, filled: dict | None = None,
          hashes: bool = True) -> Path:
    """Write the checklist file, the journal's instructions, the manuscript, the supplement,
    checklist.json and filled.json into directory/reporting-checklist; return that folder."""
    base = directory / "reporting-checklist"
    (base / "source").mkdir(parents=True, exist_ok=True)
    file = base / "source" / f"eorc-1.0.{source}"
    if source == "docx":
        docx_source(file)
    else:
        file.write_text({"html": html_source, "xml": jats_source, "csv": csv_source, "txt": text_source}[source](),
                        encoding="utf-8")
    (base / "journal-instructions.txt").write_text(JOURNAL_TEXT, encoding="utf-8")
    (base / "manuscript.txt").write_text(TEXT, encoding="utf-8")
    (base / "supplement.txt").write_text("\f".join("\n".join(page) for page in SUPPLEMENT) + "\f", encoding="utf-8")
    reg = copy.deepcopy(reg or checklist(f"source/eorc-1.0.{source}"))
    filled = copy.deepcopy(filled or FILLED)
    if hashes:
        reg["source"].setdefault("sha256", sha(base / reg["source"]["path"]))
        for document in filled["documents"]:
            document.setdefault("sha256", sha(base / document["path"]))
    (base / "checklist.json").write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
    (base / "filled.json").write_text(json.dumps(filled, indent=2, ensure_ascii=False), encoding="utf-8")
    return base
