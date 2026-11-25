#!/usr/bin/env python3
"""Check a reporting checklist filled for a manuscript against the checklist's own file and the
manuscript's text, never against memory. Formats: references/registering.md, references/filling.md.

  checklist_check.py hash FILE...          SHA-256 of files, to record in the JSON files
  checklist_check.py register [--dir D]    checklist.json against its source file: register.md, .json
  checklist_check.py check [--dir D]       filled.json against the registration and the texts: check.md
  checklist_check.py export [--dir D]      checklist-filled.md, checklist-filled.csv and gaps.md

--dir holds checklist.json and filled.json (default: reporting-checklist); a relative path in them
is read from --dir, then from the working directory.

register  hash, version, journal quote and version, licence; then the item rows of the source (table
          rows of a .docx, saved .html, JATS .xml or .csv whose id cell reads like 1, 1a, 5.2 or S3;
          "(b) ..." under item 1 is 1b) against the registered ids, count and wording, typography set
          aside. With design labels ("Cohort study:"), the wording is the common part plus the
          registered design's part. A .txt has no rows: each wording is looked for in it instead.
check     the registration passed and nothing changed since the hashes were recorded; each item once;
          reported items give a page and a quote (5 words or 12 CJK characters) graded EXACT or
          INTERLEAVED on that page, and lines when the document has line numbers (else not_checked);
          not applicable has a reason; a suggestion has no date or code (registry-shaped ids, ethics
          references) that is neither in the documents nor inside a placeholder, and a plain number
          not in the documents is not_checked (it may be a convention such as 95%).
export    only after a clean check; ids, topics, statuses and places, never an item's wording.

Pages: [[page N]] or ===== PAGE N ===== lines, or pdftotext's form feeds. Line numbers: those that
pdftotext -layout keeps at the left margin. Prints a JSON summary. Exit code 0 when nothing failed,
1 when a check failed (export then writes nothing), 2 when an input is missing or unreadable.
not_checked is never a pass. Standard library only, no network.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_match import match_quality, tokens  # noqa: E402

STATUSES = {"reported": "Reported", "partly_reported": "Partly reported", "not_reported": "Not reported",
            "not_applicable": "Not applicable"}
QUOTED, GAPS, PASSING = ("reported", "partly_reported"), ("partly_reported", "not_reported"), ("EXACT", "INTERLEAVED")
MIN_QUOTE = (5, 12)       # words, or CJK characters: a shorter quote is found somewhere in most manuscripts
MIN_REASON = (3, 6)       # "not applicable" or "N/A" is not a reason
MAX_TOPIC = 60            # characters: a topic names the item; the wording stays in checklist.json
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CJK = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")   # kana, Han, Hangul
PAGE_MARK = re.compile(r"^[ \t]*(?:\[\[page (\d+)\]\]|=+ PAGE (\d+) =+)[ \t]*$", re.M | re.I)
LINE_MARK = re.compile(r"[ \t]*(\d{1,5})(?=\s|$)")
ITEM_ID = re.compile(r"(?:item\s*)?#?\s*([a-z]{0,2}\d{1,3}(?:\.\d{1,2})?)\s*\(?([a-z]?)\)?\s*[.*†‡]?", re.I)
SUB_POINT = re.compile(r"\(?([a-z])\)\s+")
SPAN = re.compile(r"\s*(\d+)\s*(?:[-–—]\s*(\d+))?\s*")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
PLACEHOLDER = re.compile(r"\[\s*(?:Evidence|Citation|Author input) needed\b[^\]]*\]", re.I)
FACT = re.compile(r"[A-Za-z0-9]+(?:[-/.,:][A-Za-z0-9]+)*")
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
MONTH = (r"\b(january|february|march|april|may|june|july|august|september|october|november|december"
         r"|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)\b\.?")
DATE_FORMS = ((re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH},?\s+(\d{{4}})(?!\d)", re.I), (3, 2, 1)),
              (re.compile(rf"{MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)", re.I), (3, 1, 2)),
              (re.compile(rf"{MONTH},?\s+(\d{{4}})(?!\d)", re.I), (2, 1, 0)),
              (re.compile(r"(?<!\d)(\d{4})\s*[年년]\s*(\d{1,2})\s*[月월](?:\s*(\d{1,2})\s*[日일])?"), (1, 2, 3)),
              (re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)"), (1, 2, 3)))


def die(message: str):
    print(f"checklist_check: {message}", file=sys.stderr)
    raise SystemExit(2)


def load(path: Path) -> dict:
    if not path.is_file():
        die(f"{path} does not exist.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        die(f"{path} is not valid JSON: {exc}")
    return data if isinstance(data, dict) else die(f"{path} must hold a JSON object.")


def txt(value) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value.strip() if isinstance(value, str) else ""


def obj(value) -> dict:
    return value if isinstance(value, dict) else {}


def dicts(value) -> list:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def at(base: Path, name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() or (not (base / path).exists() and path.exists()) else base / path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def norm_id(value) -> str:
    return re.sub(r"^item|[\s()#*†‡]|\.$", "", fold(txt(value)))


def size(text: str) -> tuple:
    """(words, CJK characters) of a text."""
    return len(tokens(CJK.sub(" ", text))), len(CJK.findall(text))


def holds(quote: str, text: str) -> bool:
    return match_quality(quote, text)["grade"] in PASSING


def row(*values) -> str:
    return "| " + " | ".join(re.sub(r"\s+", " ", str(v)).replace("|", "/") for v in values) + " |"


def write(path: Path, lines: list) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collector() -> tuple:
    """A list of check rows, and the function that adds one."""
    rows = []

    def add(check, status, where, detail=""):
        rows.append({"check": check, "status": status, "where": where, "detail": detail})

    return rows, add


# ---------------------------------------------------------------------------------------------
# Reading files


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"%PDF"):
        die(f"{path} is a PDF. Make it text first: pdftotext -layout {path} {path.with_suffix('.txt')}")
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        die(f"{path} is an old Word .doc file. Save it as .docx: soffice --headless --convert-to docx {path}")
    try:
        return data.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        die(f"{path} is not UTF-8 text.")


def para(p) -> str:
    return "".join(e.text or "" if e.tag == W + "t" else "\t" if e.tag == W + "tab" else "\n"
                   for e in p.iter() if e.tag in (W + "t", W + "tab", W + "br", W + "cr"))


def read_docx(path: Path) -> tuple:
    """(the body's tables as rows of cells of lines, all text with headers, footers and notes)."""
    try:
        with zipfile.ZipFile(path) as archive:
            trees = {n: ElementTree.fromstring(archive.read(n)) for n in archive.namelist()
                     if re.fullmatch(r"word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml", n)}
    except (zipfile.BadZipFile, ElementTree.ParseError, OSError) as exc:
        die(f"{path} is not a readable .docx file ({exc}).")
    if "word/document.xml" not in trees:
        die(f"{path} is not a readable .docx file (no word/document.xml).")
    text = "\n".join(para(p) for n in sorted(trees, key=lambda n: n != "word/document.xml") for p in trees[n].iter(W + "p"))
    return [[[[para(p) for p in cell.iter(W + "p")] for cell in tr.findall(W + "tc")] for tr in tbl.findall(W + "tr")]
            for tbl in trees["word/document.xml"].iter(W + "tbl")], text


def read_markup(text: str) -> tuple:
    """(tables, text) of a saved web page or JATS XML. Superscripts and cross-references (footnote
    marks) are left out. A cell runs to the next cell, so end tags left out do no harm."""
    text = re.sub(r"(?is)<(script|style|sup|xref)\b[^>]*(?<!/)>.*?</\1\s*>", "", text)

    def lines(part):
        part = re.sub(r"(?i)<(?:br|break|/?(?:p|div|li|list-item|h\d|caption|title|label|t[dhr]|table))\b[^>]*>", "\n", part)
        return html.unescape(re.sub(r"<[^>]*>", "", part)).split("\n")

    tables = [re.split(r"(?i)</table\s*>", part)[0] for part in re.split(r"(?i)<table\b[^>]*>", text)[1:]]
    return [[[lines(cell) for cell in re.split(r"(?i)<t[dh]\b[^>]*>", tr)[1:]] for tr in re.split(r"(?i)<tr\b[^>]*>", t)[1:]]
            for t in tables], "\n".join(lines(text))


def read_source(path: Path) -> tuple:
    """(format, tables as rows of cells of lines, all text) of a checklist file."""
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "docx":
        return ("docx", *read_docx(path))
    text = read_text(path)
    if suffix in ("html", "htm", "xhtml", "xml"):
        return (suffix, *read_markup(text))
    if suffix in ("csv", "tsv"):
        first = text.splitlines()[0] if text.strip() else ""
        rows = csv.reader(io.StringIO(text), delimiter=max(",;\t", key=first.count))
        return "csv", [[[cell.splitlines() for cell in r] for r in rows]], text
    return "text", [], text


def points(number: str, lines: list, after: str = "") -> list:
    """(id, wording) for each sub-point (a), (b) ... that starts a line, in sequence after the letter
    `after`; words before (a) belong to (a). A cell without sub-points is one item."""
    out, lead, want = [], [], chr(ord(after) + 1) if after else "a"
    for line in lines:
        mark = SUB_POINT.match(line)
        if mark and mark.group(1).lower() == want:
            out.append([number + want, " ".join(lead + [line[mark.end():]])])
            lead, want = [], chr(ord(want) + 1)
        elif out:
            out[-1][1] += " " + line
        else:
            lead.append(line)
    return [tuple(p) for p in out] or [(number, " ".join(lead))]


def items_from(tables: list) -> list:
    """(id, wording) of every item row: the first cell that reads as an id and the longest cell after
    it. A row without an id whose cell starts with the next sub-point continues the last item."""
    found, number = [], ""
    for table in tables:
        for cells in ([[line.strip() for line in cell if line.strip()] for cell in r] for r in table):
            head = next((i for i, c in enumerate(cells) if len(c) == 1 and ITEM_ID.fullmatch(c[0])), None)
            if head is not None:
                number, letter = ITEM_ID.fullmatch(cells[head][0]).groups()
                body = max(cells[head + 1:], key=lambda c: len(" ".join(c)), default=[])
                found += ([(number + letter, " ".join(body))] if letter else points(number, body)) if body else []
            elif number:
                last = found[-1][0][len(number):] if found and found[-1][0].startswith(number) else ""
                body = next((c for c in cells if c and SUB_POINT.match(c[0])), [])
                found += [p for p in points(number, body, last if len(last) == 1 else "") if p[0] != number]
    return [(norm_id(i), " ".join(t.split())) for i, t in found]


def line_numbers(page: str):
    """[(line number or None, text)] when the longest run of left-margin numbers that grow by 1 to 5
    covers half the page's lines, else None. A stray number (a page number) stays in the text."""
    lines = page.splitlines()
    nums = [int(m.group(1)) if (m := LINE_MARK.match(line)) else None for line in lines]
    chain = {}
    for i, n in enumerate(nums):
        if n is not None:
            chain[i] = max(((chain[j][0] + 1, j) for j in chain if 0 < n - nums[j] <= 5), default=(1, None))
    end, run = max(chain, key=lambda i: chain[i][0], default=None), set()
    while end is not None:
        run.add(end)
        end = chain[end][1]
    if len(run) < max(3, sum(1 for line in lines if line.strip()) / 2):
        return None
    out, current = [], None
    for i, line in enumerate(lines):
        current, line = (nums[i], LINE_MARK.sub("", line, count=1)) if i in run else (current, line)
        out.append((current, line))
    return out


def read_document(path: Path) -> dict:
    """The pages (marks and line numbers taken out), the numbered lines of each page, and the text."""
    text = read_docx(path)[1] if path.suffix.lower() == ".docx" else read_text(path)
    marks, parts = list(PAGE_MARK.finditer(text)), text.split("\f")
    if marks:
        pages = [(int(m.group(1) or m.group(2)), text[m.end():end]) for m, end in zip(marks, [m.start() for m in marks[1:]] + [None])]
    else:
        pages = list(enumerate(parts[:-1] if not parts[-1].strip() else parts, 1)) if len(parts) > 1 else []
    numbered = {n: line_numbers(page) for n, page in pages}
    if sum(rows is not None for rows in numbered.values()) * 2 <= len(pages):
        numbered = {}                       # most pages carry no line numbers: the document has none
    clean = {n: "\n".join(t for _, t in numbered[n]) if numbered.get(n) else page for n, page in pages}
    return {"pages": clean, "lines": numbered, "plain": "\n".join(clean.values()) if pages else text}


# ---------------------------------------------------------------------------------------------
# Registering the checklist


def label_mark(labels: list):
    """A design label as printed before that design's wording: "Cohort study:" or "Cohort study—"."""
    return re.compile("(" + "|".join(map(re.escape, labels)) + r")\s*[—–:：-]", re.I) if labels else None


def unlabelled(text: str, labels: list) -> str:
    return label_mark(labels).sub(" ", text) if labels else text


def designs(text: str, labels: list) -> tuple:
    """(the common part, {label: that design's part}) of an item's wording."""
    cuts, parts = list(label_mark(labels).finditer(text)) if labels else [], {}
    for cut, after in zip(cuts, cuts[1:] + [None]):
        label = next(label for label in labels if label.casefold() == cut.group(1).casefold())
        parts[label] = parts.get(label, "") + " " + text[cut.end():after.start() if after else None]
    return (text[:cuts[0].start()] if cuts else text), parts


def wording_problem(mine: str, printed: str, labels: list, variant: str) -> str:
    (common, parts), have = designs(printed, labels), tokens(unlabelled(mine, labels))
    want = tokens(common + " " + parts.get(variant, ""))
    other = next((label for label in parts if label != variant and have == tokens(common + " " + parts[label])), None)
    if have == want:
        return ""
    if other:
        return f"has the wording for {other}; this registration is for {variant}"
    if len(parts) > 1 and have == tokens(unlabelled(printed, labels)):
        return f"has the wording of every design: register only the {variant} part"
    i = next((k for k, (a, b) in enumerate(zip(have, want)) if a != b), min(len(have), len(want)))
    return (f"differs from the file at word {i + 1}: the file has \"{' '.join(want[i:i + 5]) or '(end)'}\", "
            f"the registration \"{' '.join(have[i:i + 5]) or '(end)'}\"")


def printed(value: str, text: str) -> bool:
    return bool(re.search(rf"(?<![\w.]){re.escape(fold(value))}(?!\w|\.\d)", fold(text)))


def field_problems(reg: dict) -> list:
    source, labels, ext, items = obj(reg.get("source")), reg.get("variant_labels"), reg.get("extension_of"), dicts(reg.get("items"))
    problems = [f"{k} is missing" for k in ("name", "version", "variant") if not txt(reg.get(k))]
    if not (isinstance(labels, list) and all(txt(label) for label in labels)):
        problems.append("variant_labels must list the design labels printed in the file, or be []")
    elif labels and txt(reg.get("variant")) not in labels:
        problems.append("variant must be one of variant_labels")
    if ext != "none" and not (txt(obj(ext).get("name")) and txt(obj(ext).get("version"))):
        problems.append('extension_of must be "none" or the base guideline\'s name and version')
    problems += [] if DAY.fullmatch(txt(source.get("read"))) else ["source.read must be the date read (YYYY-MM-DD)"]
    if txt(source.get("type")) not in ("file", "web_page") or (source.get("type") == "web_page" and not txt(source.get("url"))):
        problems.append("source.type must be file, or web_page with its url")
    problems += [f"item {txt(i.get('id')) or '?'}: needs a topic of at most {MAX_TOPIC} characters and its text as printed"
                 for i in items if not 0 < len(txt(i.get("topic"))) <= MAX_TOPIC or not isinstance(i.get("text"), str)]
    problems += [f"item {txt(i.get('id'))}: the topic repeats the item's wording; name the item in your own words"
                 for i in items if size(txt(i.get("topic")))[0] >= MIN_QUOTE[0] and isinstance(i.get("text"), str)
                 and match_quality(txt(i.get("topic")), i["text"])["grade"] == "EXACT"]
    twice = [i or "(empty)" for i, n in Counter(norm_id(i.get("id")) for i in items).items() if n > 1 or not i]
    return problems + ["items is empty"] * (not items) + ["every item needs its own id: " + ", ".join(twice)] * bool(twice)


def check_journal(base: Path, reg: dict, add) -> None:
    journal, version = reg.get("journal"), txt(reg.get("version"))
    if journal == "not_stated":
        return add("journal", "not_checked", "journal", "no journal requirement recorded: the version asked for is unknown")
    journal = obj(journal)
    asked, quote, source, decision = (txt(journal.get(k)) for k in ("version", "quote", "source", "user_decision"))
    problems = [f"journal.{k} is missing" for k in ("name", "quote", "source", "version") if not txt(journal.get(k))]
    problems += [] if DAY.fullmatch(txt(journal.get("read"))) else ["journal.read must be the date read (YYYY-MM-DD)"]
    problems += [f"the version {asked!r} is not in the journal's quote"] * (asked not in ("", "not_stated") and not printed(asked, quote))
    saved = at(base, source).is_file() and at(base, source).suffix.lower() != ".pdf"
    if not problems and saved and not holds(quote, read_source(at(base, source))[2]):
        problems.append(f"the quote is not in {source}: copy the journal's words again")
    add("journal", "fail" if problems else "ok" if saved else "not_checked", "journal", "; ".join(problems) or (
        f"the quote is in {source}" if saved else f"{source} is not a saved text file: the quote was not compared"))
    if asked == "not_stated":
        return add("journal_version", "not_checked", "journal", f"the journal names no version; the file prints {version}")
    same = fold(asked) == fold(version)
    add("journal_version", "ok" if same or decision else "fail", "journal", f"the journal asks for {asked}, as the file prints"
        if same else f"the journal asks for {asked}; the file prints {version}. " + (f"The user decided: {decision}" if decision
        else "Tell the user and replace neither; record their decision in journal.user_decision"))


def compare_items(reg: dict, kind: str, tables: list, text: str, add) -> int:
    """Rows for the registered items against the item rows of the file; returns how many rows it has."""
    labels = [txt(label) for label in reg["variant_labels"] if txt(label)] if isinstance(reg.get("variant_labels"), list) else []
    items, found = [(norm_id(i.get("id")), i) for i in dicts(reg.get("items"))], items_from(tables)
    if not found:
        add("ids", "not_checked", "items", f"no item rows in the {kind} file: ids, count and design wording not compared")
        for _, item in items:
            grade = match_quality(unlabelled(txt(item.get("text")), labels) or "-", text)["grade"]
            state = "ok" if grade in PASSING else "not_checked" if grade == "PARTIAL" else "fail"
            add("wording", state, f"item {txt(item.get('id'))}", {"ok": "", "not_checked": "only partly found: compare it "
                "with the file by eye", "fail": "not in the file: copy the wording as printed"}[state])
        return 0
    in_file, in_reg = Counter(i for i, _ in found), Counter(i for i, _ in items)
    only_file, only_reg = [i for i in in_file if i not in in_reg], [i for i in in_reg if i not in in_file]
    add("count", "ok" if len(in_file) == len(in_reg) else "fail", "items",
        f"the file has {len(in_file)} item rows; checklist.json registers {len(in_reg)}")
    add("ids", "fail" if only_file or only_reg else "ok", "items", "; ".join(
        [f"in the file, not registered: {', '.join(only_file)}"] * bool(only_file)
        + [f"registered, not in the file: {', '.join(only_reg)}"] * bool(only_reg)))
    twice = [i for i, n in in_file.items() if n > 1]
    if twice:
        add("ids", "not_checked", "items", f"the file prints {', '.join(twice)} more than once: compare by eye")
    wording = dict(reversed(found))
    for nid, item in items:
        if nid in wording:
            problem = wording_problem(txt(item.get("text")), wording[nid], labels, txt(reg.get("variant")))
            add("wording", "fail" if problem else "ok", f"item {txt(item.get('id'))}", problem)
    return len(found)


def run_register(base: Path) -> tuple:
    """(rows, the report's head, summary fields) of checklist.json against its source file."""
    (rows, add), path = collector(), base / "checklist.json"
    reg = load(path)
    source = obj(reg.get("source"))
    file, version, licence = at(base, txt(source.get("path"))), txt(reg.get("version")), reg.get("licence")
    if not txt(source.get("path")) or not file.is_file():
        die(f"the checklist file {txt(source.get('path')) or '(source.path is empty)'} does not exist. Copy the user's file "
            f"into {base}/source/ and name it in source.path.")
    kind, tables, text = read_source(file)
    digest, recorded, problems = sha256(file), txt(source.get("sha256")), field_problems(reg)
    add("fields", "fail" if problems else "ok", "checklist.json", "; ".join(problems))
    add("source_file", "ok" if recorded == digest else "fail", txt(source.get("path")), "" if recorded == digest else
        f"no SHA-256 recorded: record {digest}" if not recorded else "changed after it was registered: register it again")
    add("version", "ok" if version and printed(version, text) else "fail", "version", f"{version!r} is printed in the file"
        if version and printed(version, text) else f"{version!r} is not printed in the file: write it as the file prints it")
    check_journal(base, reg, add)
    if licence == "not_stated":
        add("licence", "not_checked", "licence", "no licence statement recorded: the wording is not cleared for sharing")
    elif not txt(obj(licence).get("text")):
        add("licence", "fail", "licence", 'licence must be "not_stated" or {"text": the statement as printed, "where": ...}')
    else:
        found = holds(licence["text"], text)
        add("licence", "ok" if found else "fail", "licence", f"printed: \"{licence['text']}\"" if found else
            "not in the file: copy the statement as the file prints it")
    count = compare_items(reg, kind, tables, text, add)
    journal, licence = obj(reg.get("journal")), obj(licence)
    head = [f"Checklist: {txt(reg.get('name'))}, version {version}, variant {txt(reg.get('variant'))}.",
            f"Source: {txt(source.get('path'))} ({kind}, {count} item rows), SHA-256 {digest}, read {txt(source.get('read'))}.",
            f"Journal: \"{txt(journal.get('quote'))}\" ({txt(journal.get('source'))}, read {txt(journal.get('read'))})."
            if journal else "Journal: no requirement recorded.",
            f"Licence printed on the file: \"{txt(licence.get('text'))}\" ({txt(licence.get('where'))})."
            if txt(licence.get("text")) else "Licence: none recorded; the wording is not cleared for sharing."]
    return rows, head, {"checklist_sha256": sha256(path), "source_sha256": digest, "format": kind, "file_rows": count,
                        "items": len(dicts(reg.get("items")))}


def cmd_register(base: Path) -> dict:
    rows, head, fields = run_register(base)
    result = {**report(base, "register.md", "Checklist registration", head, rows, []), **fields}
    write(base / "register.json", [json.dumps(result, indent=2, ensure_ascii=False)])
    return result


# ---------------------------------------------------------------------------------------------
# Checking the filled checklist


def span(value):
    match = SPAN.fullmatch(txt(value))
    first, last = (int(match.group(1)), int(match.group(2) or match.group(1))) if match else (1, 0)
    return (first, last) if first <= last else None


def shortest(quote: str, rows: list):
    """(first, last) line of the shortest run of numbered lines that holds the quote, or None."""
    rows = [(n, t) for n, t in rows if n is not None]

    def within(a, b):
        return holds(quote, "\n".join(t for n, t in rows if a <= n <= b))

    lo, hi = (rows[0][0], rows[-1][0]) if rows else (1, 0)
    if not rows or not within(lo, hi):
        return None
    while lo < hi and within(lo + 1, hi):
        lo += 1
    while hi > lo and within(lo, hi - 1):
        hi -= 1
    return lo, hi


def check_place(loc: dict, docs: dict, where: str, add) -> None:
    name, quote = txt(loc.get("document")) or "manuscript", txt(loc.get("quote"))
    doc, (words, cjk) = docs.get(name), size(quote)
    if doc is None:
        return add("quote", "fail", where, f"document {name!r} is not a readable document of filled.json")
    if words < MIN_QUOTE[0] and cjk < MIN_QUOTE[1]:
        return add("quote", "fail", where, f"quote at least {MIN_QUOTE[0]} words or {MIN_QUOTE[1]} CJK characters, word for word")
    if re.search(r"\.\.\.|…", quote):
        return add("quote", "fail", where, "a quote is one passage, without an ellipsis: give each passage as its own place")
    grade = match_quality(quote, doc["plain"])["grade"]
    if grade not in PASSING:
        return add("quote", "fail", where, f"not in the {name} (ABSENT)" if grade == "ABSENT" else
                   "only partly found (PARTIAL): copy the passage word for word; a paraphrase is not a quote")
    add("quote", "ok", where, f"{grade} in the {name}")
    if not doc["pages"]:
        return add("page", "not_checked", where, f"the {name} has no page marks or form feeds: use the text of its PDF")
    pages = span(loc.get("page"))
    chosen = [n for n in doc["pages"] if pages and pages[0] <= n <= pages[1]]
    if not chosen or not holds(quote, "\n".join(doc["pages"][n] for n in chosen)):
        on = [str(n) for n, page in doc["pages"].items() if holds(quote, page)]
        return add("page", "fail", where, ("no page: give the page number of the document" if not txt(loc.get("page")) else
                                           f"page {txt(loc.get('page'))!r} is not a number or a range such as 8-9"
                                           if pages is None else f"not on page {txt(loc.get('page'))}")
                   + (f"; the quote is on page {', '.join(on)}" if on else "; no single page holds it: give the range, as 8-9"))
    add("page", "ok", where, f"page {txt(loc.get('page'))}")
    rows = [r for n in chosen for r in doc["lines"].get(n) or []]
    if not rows:
        return add("lines", "not_checked", where, f"the {name} carries no line numbers" if not doc["lines"]
                   else "this page carries no line numbers")
    lines, stated = shortest(quote, rows), span(loc.get("lines"))
    shown = (f"{lines[0]}-{lines[1]}" if lines[0] != lines[1] else str(lines[0])) if lines else ""
    if lines is None:
        add("lines", "not_checked", where, "the quote is not within the numbered lines of the page")
    elif stated is None:
        add("lines", "fail", where, f"the page carries line numbers: give them as a number or a range such as 112-118 "
                                    f"(the quote is at lines {shown})")
    else:
        inside = stated[0] <= lines[0] and lines[1] <= stated[1]
        add("lines", "ok" if inside else "fail", where, f"lines {shown}" if inside else
            f"not at lines {txt(loc.get('lines'))}: the quote is at lines {shown}")


def dates(text: str) -> tuple:
    """({(year, month, day or 0): as written}, the text with those dates blanked out)."""
    found = {}

    def take(match, order):
        y, m, d = (match.group(i) if i else None for i in order)
        found[(int(y), int(m) if m.isdigit() else 1 + MONTHS.index(m[:3].lower()), int(d or 0))] = " ".join(match.group(0).split())
        return " " * len(match.group(0))

    for pattern, order in DATE_FORMS:
        text = pattern.sub(lambda match, order=order: take(match, order), text)
    return found, text


def facts(text: str, parts: bool = False) -> dict:
    """{as compared: as written} for the numbers and codes that carry digits: "12-week" gives 12,
    "IRB-2023-114" gives 2023-114, "NCT01234567" stays whole, "1,234" is 1234. With parts, each
    piece of a run too."""
    out = []
    for token in FACT.findall(unicodedata.normalize("NFKC", text).translate(DASHES)):
        pieces, run = re.split(r"([-/.,:])", token), ""
        for i in range(0, len(pieces), 2):
            if pieces[i].isalpha():
                out.append(run)
                run = ""
            else:
                run += (pieces[i - 1] if run else "") + pieces[i]
                out += [pieces[i]] * parts
        out.append(run)
    return {re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", f.casefold()): f for f in out if re.search(r"\d", f)}


def check_item(entry: dict, docs: dict, known: tuple, add) -> None:
    """known: (facts in the documents, dates in the documents, item ids that carry a letter)."""
    where, status, places = f"item {txt(entry.get('id'))}", txt(entry.get("status")), dicts(entry.get("locations"))
    problems = [] if status in STATUSES else [f"status must be one of {', '.join(STATUSES)}"]
    problems += [] if txt(entry.get("assessor")) else ["assessor is missing"]
    problems += ["a reported item needs a place: document, page and quote"] * (status in QUOTED and not places)
    problems += [f"{k} is missing" for k in ("missing", "suggestion") if status in GAPS and not txt(entry.get(k))]
    add("complete", "fail" if problems else "ok", where, "; ".join(problems))
    if status == "not_applicable":
        words, cjk = size(PLACEHOLDER.sub(" ", txt(entry.get("reason"))))
        short = words < MIN_REASON[0] and cjk < MIN_REASON[1]
        add("reason", "fail" if short else "ok", where, "give the reason this item does not apply to this study" * short)
    for k, loc in enumerate(places, 1):
        check_place(loc, docs, f"{where}, place {k}" if len(places) > 1 else where, add)
    suggestion = unicodedata.normalize("NFKC", txt(entry.get("suggestion")))
    if suggestion:
        said, rest = dates(PLACEHOLDER.sub(" ", suggestion))
        new = [shown for (y, m, d), shown in said.items() if (y, m, d) not in known[1]
               and (d or not any(k[:2] == (y, m) for k in known[1]))]
        loose = []
        for f, shown in facts(rest).items():
            if f not in known[0] and f not in known[2]:
                # a plain number may be a convention (95%); a code or a date is a fact about this study
                (loose if re.fullmatch(r"[-+]?\d+(?:\.\d+)?%?", f) else new).append(shown)
        if new:
            add("suggestion", "fail", where, f"not in the documents: {'; '.join(new)}. Put a fact only the authors "
                "have in a placeholder, [Author input needed: ...]")
        elif loose:
            add("suggestion", "not_checked", where, f"numbers not in the documents: {'; '.join(loose)}. A number about "
                "this study goes in a placeholder; a convention such as 95% may stay")
        else:
            add("suggestion", "ok", where, "")


def documents(base: Path, filled: dict, add) -> dict:
    docs, entries = {}, dicts(filled.get("documents"))
    names = Counter(txt(d.get("id")) for d in entries)
    if names["manuscript"] != 1:
        add("document", "fail", "documents", "list the manuscript once, with the id manuscript")
    for entry in entries:
        name, file, recorded = txt(entry.get("id")), txt(entry.get("path")), txt(entry.get("sha256"))
        path, where = at(base, file), f"document {name or '?'}"
        if not name or names[name] > 1 or not file or not path.is_file():
            add("document", "fail", where, "needs its own id and a path to a file that exists")
            continue
        label = txt(entry.get("label")) or ("" if name == "manuscript" else name)
        docs[name] = dict(read_document(path), path=file, label=label, sha256=sha256(path))
        add("document", "ok" if recorded == docs[name]["sha256"] else "fail", where, file if recorded == docs[name]["sha256"] else
            "no SHA-256 recorded: run hash and record it" if not recorded else "changed after filled.json was written: "
            "reread every item against this version, statuses as well as quotes, then record the new hash")
    return docs


def run_check(base: Path) -> tuple:
    (rows, add), path = collector(), base / "checklist.json"
    reg, filled = load(path), load(base / "filled.json")
    try:
        saved = obj(json.loads((base / "register.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        saved = {}
    passed = saved.get("ok") and saved.get("checklist_sha256") == sha256(path)
    add("registration", "ok" if passed else "fail", "checklist.json", "" if passed else
        "run register: it has not passed on checklist.json as it is now")
    source = obj(reg.get("source"))
    file = at(base, txt(source.get("path")))
    same = bool(txt(source.get("path"))) and file.is_file() and txt(source.get("sha256")) == sha256(file)
    add("source_file", "ok" if same else "fail", "checklist source", txt(source.get("path")) if same else
        "missing, or changed after registration: register the checklist again from the file as it is now")
    docs, items, entries = documents(base, filled, add), dicts(reg.get("items")), dicts(filled.get("items"))
    ids, seen = [norm_id(i.get("id")) for i in items], Counter(norm_id(e.get("id")) for e in entries)
    for item, nid in zip(items, ids):
        add("items", "ok" if seen[nid] == 1 else "fail", f"item {txt(item.get('id'))}",
            "" if seen[nid] == 1 else f"filled {seen[nid]} times" if seen[nid] else "not in filled.json")
    for entry in entries:
        if norm_id(entry.get("id")) not in ids:
            add("items", "fail", f"item {txt(entry.get('id')) or '?'}", "not an item of the registered checklist")
    known = (set(), set(), {i for i in ids if re.search("[a-z]", i)})
    for doc in docs.values():
        known[0].update(facts(doc["plain"], parts=True))
        known[1].update(dates(doc["plain"])[0])
    for entry in entries:
        check_item(entry, docs, known, add)
    return rows, {"reg": reg, "entries": {norm_id(e.get("id")): e for e in entries}, "docs": docs}


def counts(entries) -> str:
    found = Counter(txt(e.get("status")) for e in entries)
    return ", ".join(f"{found[s]} {label.lower()}" for s, label in STATUSES.items())


def report(base: Path, name: str, title: str, head: list, rows: list, tail: list) -> dict:
    states = Counter((r["check"], r["status"]) for r in rows)
    failed, unchecked = [r for r in rows if r["status"] == "fail"], {}
    for r in rows:
        if r["status"] == "not_checked":
            unchecked.setdefault(f"{r['check']}: {r['detail']}", []).append(r["where"])
    lines = [f"# {title}", "", *head, "", row("Check", "ok", "fail", "not checked"), "|---" * 4 + "|"]
    lines += [row(c, states[c, "ok"], states[c, "fail"], states[c, "not_checked"]) for c in dict.fromkeys(r["check"] for r in rows)]
    lines += ["", f"## Failures ({len(failed)})", ""] + ([row("Check", "Where", "Problem"), "|---" * 3 + "|"]
                                                          + [row(r["check"], r["where"], r["detail"]) for r in failed]
                                                          if failed else ["None."])
    lines += ["", "## Not checked (never a pass)", ""] + ([f"- {k} ({', '.join(w)})" for k, w in unchecked.items()] or ["None."])
    write(base / name, lines + tail)
    return {"ok": not failed, "fail": len(failed), "not_checked": sum(map(len, unchecked.values())),
            "report": str(base / name), "failures": [{k: r[k] for k in ("check", "where", "detail")} for r in failed[:40]]}


def cmd_check(base: Path) -> dict:
    rows, ctx = run_check(base)
    entries = list(ctx["entries"].values())
    unreviewed = [txt(e.get("id")) for e in entries if not txt(e.get("checked_by"))]
    tail = ["", "## Not yet reviewed by a person (checked_by is empty)", "", ", ".join(unreviewed) or "None."]
    result = report(base, "check.md", "Reporting checklist check", [f"Items by status: {counts(entries)}. No score."], rows, tail)
    return {**result, "by_status": dict(Counter(txt(e.get("status")) for e in entries)), "not_reviewed": len(unreviewed)}


# ---------------------------------------------------------------------------------------------
# Export


def place(entry: dict, docs: dict) -> str:
    if txt(entry.get("status")) not in QUOTED:
        return STATUSES[txt(entry.get("status"))]
    out = []
    for loc in dicts(entry.get("locations")):
        page, lines, part = txt(loc.get("page")), txt(loc.get("lines")), txt(loc.get("where"))
        bits = (" ".join(x for x in (docs[txt(loc.get("document")) or "manuscript"]["label"], page and f"p. {page}") if x),
                lines and f"lines {lines}")
        out.append(", ".join(b for b in bits if b) + (f" ({part})" if part else ""))
    return "; ".join(out)


def cmd_export(base: Path) -> dict:
    rows, ctx = run_check(base)
    failures = sum(r["status"] == "fail" for r in rows)
    if failures:
        return {"exported": False, "fail": failures, "message": "check fails: run check and correct filled.json first"}
    reg, docs, source, licence = ctx["reg"], ctx["docs"], obj(ctx["reg"].get("source")), ctx["reg"].get("licence")
    items = [(txt(i.get("id")), txt(i.get("topic")), ctx["entries"][norm_id(i.get("id"))]) for i in dicts(reg.get("items"))]
    title, state = f"{txt(reg.get('name'))} {txt(reg.get('version'))}", lambda e: txt(e.get("status"))
    table = [(i, topic, STATUSES[state(e)], place(e, docs)) for i, topic, e in items]
    head = [f"Variant: {txt(reg.get('variant'))}. Checklist file: {txt(source.get('path'))}, read {txt(source.get('read'))}.",
            "Licence printed on the checklist file: " + (f"\"{txt(obj(licence).get('text'))}\"." if licence != "not_stated"
                                                         else "none found; the item wording is not cleared for sharing."),
            "Documents: " + "; ".join(f"{d['path']} ({d['label'] or name}, SHA-256 {d['sha256'][:12]})" for name, d in docs.items()) + ".",
            f"Items by status: {counts(e for _, _, e in items)}. Places checked by checklist_check.py; "
            f"{sum(r['status'] == 'not_checked' for r in rows)} not checked (check.md). The item wording is not repeated here."]
    write(base / "checklist-filled.md", [f"# {title}: filled checklist", "", *head, "",
                                         row("Item", "Topic", "Status", "Where reported"), "|---" * 4 + "|", *(row(*t) for t in table)])
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([("item", "topic", "status", "where_reported"), *table])
    (base / "checklist-filled.csv").write_text(out.getvalue(), encoding="utf-8")
    gaps = [row(i, t, STATUSES[state(e)], txt(e.get("missing")), txt(e.get("suggestion"))) for i, t, e in items if state(e) in GAPS]
    reasons = [f"- {i} ({t}): {txt(e.get('reason'))}" for i, t, e in items if state(e) == "not_applicable"]
    holes = [f"- {i}: {hole}" for i, _, e in items for hole in PLACEHOLDER.findall(txt(e.get("suggestion")))]
    unreviewed = ", ".join(i for i, _, e in items if not txt(e.get("checked_by")))
    write(base / "gaps.md", [f"# Gaps against {title}", "", "Not for upload: what to add, decided with the authors.", "",
                             *([row("Item", "Topic", "Status", "What is missing", "Suggestion"), "|---" * 5 + "|", *gaps]
                               if gaps else ["None."]),
                             "", "## Not applicable", "", *(reasons or ["None."]),
                             "", "## Placeholders for the authors", "", *(holes or ["None."]),
                             "", "## Not yet reviewed by a person", "", unreviewed or "None."])
    return {"exported": True, "files": [str(base / f) for f in ("checklist-filled.md", "checklist-filled.csv", "gaps.md")],
            "by_status": dict(Counter(state(e) for _, _, e in items)), "gaps": len(gaps)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Register a reporting checklist from its file, check the filled "
                                                 "checklist against the manuscript, and export it.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hash", help="Print the SHA-256 of files").add_argument("files", nargs="+")
    for name, about in (("register", "Compare checklist.json with its source file; write register.md"),
                        ("check", "Check filled.json against the registration and the texts; write check.md"),
                        ("export", "Write checklist-filled.md, checklist-filled.csv and gaps.md, when check passes")):
        sub.add_parser(name, help=about).add_argument("--dir", default="reporting-checklist",
                                                      help="Folder with checklist.json and filled.json (default: reporting-checklist)")
    args = parser.parse_args(argv)
    if args.command == "hash":
        missing = [f for f in args.files if not Path(f).is_file()]
        result = {"sha256": {f: sha256(Path(f)) for f in args.files}} if not missing else die("no such file: " + ", ".join(missing))
    else:
        result = {"register": cmd_register, "check": cmd_check, "export": cmd_export}[args.command](Path(args.dir))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result.get("fail") or result.get("exported") is False else 0


if __name__ == "__main__":
    sys.exit(main())
