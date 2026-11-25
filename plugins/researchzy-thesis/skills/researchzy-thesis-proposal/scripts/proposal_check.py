#!/usr/bin/env python3
"""Check a thesis proposal or a research proposal against the school's own template, never against memory.

The agent records the school's template and rules in thesis-proposal/template.json, each rule with a quote, and
the student's period and questions in brief.json. The script does what is mechanical:

  proposal_check.py template school.docx text/rules.txt   every quote of template.json is in these files
  proposal_check.py check thesis-proposal/proposal.md     sections, order, limits, placeholders, citations against
                                                           the ledger, questions against matrix.csv and timeline.csv
  proposal_check.py timeline [timeline.csv]                dates, dependencies, period, milestones, overlaps, gaps

--dir (default: thesis-proposal) holds template.json, brief.json, matrix.csv, timeline.csv and the reports; check
takes --literature (default: <dir>/literature, the review_ledger.py folder) and --final (open placeholders fail).
template reads a .docx from its XML, writes its text to <dir>/text/ and prints each file's SHA-256 (exit 2 without template.json).

Rows are pass, fail, not_checked, not_stated (the school's files say nothing) or manual (a person must look);
not_checked and not_stated are never passes. Each command prints a JSON summary. Exit code 0 when nothing failed;
1 when (template) a quote is missing, too short or not in the files, a limit's quote lacks its number or is
approximate while the record is exact, or a file is not the one recorded, or (check, timeline) a row is fail;
2 when an input cannot be read or breaks the format of the references. Standard library only, no network.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import re
import sys
import unicodedata
import zipfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_ledger as rl  # noqa: E402

NS = "not_stated"
STATES = ("pass", "fail", "not_checked", NS, "manual")
UNITS = ("words", "characters", "pages", NS)
KINDS = ("table", "signature", "attachment", "ai_policy", "other")
RECORD_KEYS = ("document", "sources", "sections", "total_limit", "references_min", "milestones", "items", "conflicts")
MATRIX = ("question", "content", "method", "data", "phase", "output")
TIMELINE = ("phase", "start", "end", "questions", "depends_on", "deliverable")
FAILING = ("quote_not_found", "no_quote", "quote_too_short", "value_not_in_quote", "reading_differs", "not_in_record", "changed")
REFERENCES = {"template.json": "references/template-record.md", "brief.json": "references/feasibility-and-timeline.md"}
MIN_QUOTE_WORDS = 3     # a shorter quote is found in any template and proves nothing
CAP = 20                # sentences listed per lead
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
HAN_CLASS = "぀-ヿ㐀-䶿一-鿿豈-﫿"
HAN = re.compile(f"[{HAN_CLASS}]")
CJK_SPACE = re.compile(f" (?=[　-〿{HAN_CLASS}])|(?<=[　-〿{HAN_CLASS}]) ")
PLACEHOLDER = re.compile(r"\[\s*(?:Evidence|Citation|Author input) needed\b[^\]]*\]", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
NUMBERING = re.compile(r"^(?:第\s*[一二三四五六七八九十百\d]+\s*[章节部分篇]|[一二三四五六七八九十]+\s*[、.]"
                       r"|\(\s*[一二三四五六七八九十\d]+\s*\)|(?:section|part|chapter)?\s*\d+(?:\.\d+)*[、.):]?"
                       r"|[ivx]+[.)]|[a-z][.)])\s*", re.I)
NUMBER = re.compile(r"(?<![\d.])(\d{1,3}(?:[, ]\d{3})+(?!\d)|\d+(?:\.\d+)?)\s*(万)?")
ZH_NUMBER = re.compile(r"[零〇一二两三四五六七八九十百千万]+")
ZH_VALUE = dict(zip("零〇一二两三四五六七八九十百千万", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100, 1000, 10000)))
EN_NUMBER = {word: n for n, word in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                              "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
APPROX = re.compile(r"左右|上下|大约|大概|约|about|around|approximately|roughly|[~～]", re.I)
LITERATURE = re.compile(r"文献|综述|研究现状|literature|related work|state of the (?:art|research)|bibliography", re.I)
RESULT = re.compile(r"(?<![A-Za-z])(?:[rpntfdb]|β|χ2|χ²|or|rr|hr|auc|icc|r2|r²)\s*[=<>≤≥]\s*[-−]?\.?\d|\d\s*[%％]|显著"
                    r"|相关系数|提高了|降低了|增加了|减少了|结果(?:表明|显示)|预实验|预调查|前期研究|初步研究|pilot|we found"
                    r"|showed that|significant", re.I)
GAP = re.compile(r"尚无|尚未有|未见|鲜有|鲜见|很少有|空白|首次|没有.{0,8}(?:研究|文献|探讨)|little is known|few studies"
                 r"|no (?:prior |previous |existing |published )?(?:study|studies|research|work)|unexplored"
                 r"|ha(?:s|ve) not been (?:studied|examined|investigated|explored)|for the first time", re.I)
SEARCHED = re.compile(r"检索|搜索|数据库|search|database|quer", re.I)
SENTENCE = re.compile(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z\[])")
DATE = re.compile(r"(\d{4})[-/.年](\d{1,2})(?:[-/.月](\d{1,2})日?|月)?")
QUOTE_MARKS = dict.fromkeys(map(ord, "‘’‚‛“”„‟«»‹›´`\""), "'")
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
READINGS = {"words": ("words",), "characters": ("characters", "spaces"), NS: ("words", "characters", "spaces")}
LABELS = {"words": "words (a Han character is one)", "characters": "characters without spaces", "spaces": "characters with spaces"}


def fail(message: str):
    print(f"proposal_check: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_text(path: Path) -> str:
    """A UTF-8 text file, or the paragraphs of a .docx one per line (deleted text left out)."""
    if not path.is_file():
        fail(f"no such file: {path}")
    if path.read_bytes()[:4] == b"%PDF":
        fail(f"{path} is a PDF. Turn it into text first: pdftotext -layout {path} thesis-proposal/text/{path.stem}.txt")
    try:
        if path.suffix.lower() != ".docx":
            return path.read_bytes().decode("utf-8-sig")
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        return "\n".join("".join((n.text or "") if n.tag == W + "t" else "\t" for n in p.iter() if n.tag in (W + "t", W + "tab"))
                         for p in root.iter(W + "p"))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError, UnicodeDecodeError) as exc:
        fail(f"{path} is neither UTF-8 text nor a readable .docx ({exc}); save a .doc as .docx first.")


def read_csv(path: Path, required: tuple) -> list:
    """The rows of a CSV as dicts with lower-case column names. The delimiter may be , ; or a tab."""
    lines = read_text(path).splitlines()
    reader = csv.DictReader(lines, delimiter=max(",;\t", key=(lines[0] if lines else "").count))
    columns = {name: (name or "").strip().lower() for name in reader.fieldnames or []}
    missing = [name for name in required if name not in columns.values()]
    if missing:
        fail(f"{path} lacks the column(s) {', '.join(missing)}. It needs: {', '.join(required)}.")
    rows = [{columns[key]: str(row.get(key) or "").strip() for key in columns} for row in reader]
    return [row for row in rows if any(row.values())]


def write(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def table(header: tuple, rows: list) -> list:
    cell = lambda value: re.sub(r"\s+", " ", str(value)).replace("|", "/").strip()  # noqa: E731
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)]


def positive(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def objects(node) -> list:
    return [item for item in node if isinstance(item, dict)] if isinstance(node, list) else []


def named(node, field: str) -> bool:
    return isinstance(node, list) and bool(node) and all(isinstance(i, dict) and str(i.get(field, "")).strip() for i in node)


def ids_of(value) -> list:
    return [part.strip() for part in re.split(r"[;,，；、]", str(value or "")) if part.strip()]


def parse_date(text, end: bool = False):
    """YYYY-MM-DD, or YYYY-MM (its first day, or its last for an end), also with / . or 年 月 日; None if invalid."""
    match = DATE.fullmatch(re.sub(r"\s", "", unicodedata.normalize("NFKC", str(text or ""))))
    try:
        year, month = int(match[1]), int(match[2])
        return date(year, month, int(match[3]) if match[3] else calendar.monthrange(year, month)[1] if end else 1)
    except (TypeError, ValueError):
        return None


def span(start: date, end: date) -> str:
    months = (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day)
    year, month = start.year + (start.month - 1 + months) // 12, (start.month - 1 + months) % 12 + 1
    return f"{months} months and {(end - date(year, month, min(start.day, calendar.monthrange(year, month)[1]))).days} days"


def norm_quote(text: str) -> str:
    """Text as compared: case, spacing (also next to Han characters), line-break hyphens, quote marks and dashes do not count."""
    text = unicodedata.normalize("NFKC", text).translate(QUOTE_MARKS).translate(DASHES).replace("­", "")
    text = re.sub(r"(?<=\w)-(?=\w)", "", re.sub(r"(?<=\w)-[ \t]*\n\s*(?=\w)", "", text))
    return CJK_SPACE.sub("", " ".join(re.sub(r"[*`]", "", text).replace("|", " ").casefold().split()))


def numbers_in(text: str) -> set:
    """The numbers of a text: 2,000 · ２０００ · 1.5万 · 两千 or 三千五百 (Han numerals) · two."""
    text = unicodedata.normalize("NFKC", text)
    found = {float(re.sub(r"[, ]", "", m[1])) * (10000 if m[2] else 1) for m in NUMBER.finditer(text)}
    for match in ZH_NUMBER.finditer(text):
        total = section = digit = 0
        for value in map(ZH_VALUE.get, match[0]):
            if value < 10:
                digit = value
            elif value == 10000:
                total, section, digit = (total + section + digit) * value, 0, 0
            else:
                section, digit = section + (digit or 1) * value, 0
        found.add(float(total + section + digit))
    return found | {float(n) for word, n in EN_NUMBER.items() if re.search(rf"\b{word}\b", text, re.I)}


def count_words(text: str) -> int:
    """Words as a word processor counts them: each Han or kana character is one word."""
    return len(HAN.findall(text)) + sum(1 for token in HAN.sub(" ", text).split() if any(c.isalnum() for c in token))


def norm_name(text: str) -> str:
    """A section name as matched, without case, numbering (一、 （一） 第一章 1.2), a closing （…） and punctuation."""
    text = unicodedata.normalize("NFKC", text).casefold().replace("&", " and ")
    text = re.sub(r"\s*[(\[【][^)\]】]*[)\]】]\s*$", "", re.sub(r"[*_`]", " ", text).strip())
    return " ".join(re.findall(r"\w+", NUMBERING.sub("", text, count=1)) or re.findall(r"\w+", text))


def outline(text: str) -> tuple:
    """(lines, headings). A heading spans to the next heading of its own or a higher level."""
    lines, heads = text.splitlines(), []
    for number, line in enumerate(lines):
        match = HEADING.match(line)
        if match:
            heads.append({"level": len(match[1]), "title": match[2], "key": norm_name(match[2]), "start": number})
    for index, head in enumerate(heads):
        head["end"] = next((h["start"] for h in heads[index + 1:] if h["level"] <= head["level"]), len(lines))
        head["title_of_document"] = index == 0 and head["end"] == len(lines) and len(heads) > 1
    return lines, heads


def heading_at(heads: list, line: int) -> str:
    chain = [h["title"] for h in heads if h["start"] <= line < h["end"] and not h["title_of_document"]]
    return " > ".join(chain) or "(before the first section)"


def plain(text: str) -> str:
    """Markdown with its markup taken off, so that markup is not counted."""
    text = re.sub(r"(?m)^\s*(?:#{1,6}|[-*+]|\d+[.)]|>)\s+", "", re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text))
    return re.sub(r"[*`|]", " ", re.sub(r"(?m)^[\s|:-]+$", "", text))


def describe(limit: dict) -> str:
    low, high, about = (limit.get(key) for key in ("min", "max", "about"))
    words = f"about {about:g}" if about else f"{low:g} to {high:g}" if low and high else f"at least {low:g}" if low else f"at most {high:g}"
    return f"{words} {limit['unit']}" if limit["unit"] != NS else f"{words}, counting rule not stated"


def limit_errors(limit, where: str) -> list:
    if limit == NS:
        return []
    if not isinstance(limit, dict):
        return [f'{where} must be "not_stated" or an object']
    given = {key: limit[key] for key in ("min", "max", "about") if key in limit}
    return [f"{where} {message}" for bad, message in (
        (not given or not all(map(positive, given.values())), "needs min, max or about, each a positive number"),
        ("about" in given and len(given) > 1, "has about together with min or max"),
        (all(map(positive, given.values())) and given.get("min", 0) > given.get("max", float("inf")), "has min above max"),
        (limit.get("unit") not in UNITS or limit.get("spaces", NS) not in ("included", "excluded", NS),
         f"needs a unit, one of {', '.join(UNITS)}, and spaces, if given, included, excluded or not_stated"))
        if bad]


def record_errors(record: dict) -> list:
    """What keeps the record from being used. Silence is written "not_stated", unlike an item nobody looked for."""
    missing = [f'{key} is missing (write "not_stated" when the files are silent)' for key in RECORD_KEYS if key not in record]
    if missing:
        return missing
    errors = [] if named(record["sources"], "file") else ["sources must list the files read, each with a file"]
    errors += [f"sources[{s.get('file')}] needs date_read (YYYY-MM-DD) and sha256 (the template command prints it)"
               for s in objects(record["sources"]) if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(s.get("date_read")))
                                                         and re.fullmatch(r"[0-9a-f]{64}", str(s.get("sha256"))))]
    errors += [f'{key} must be "not_stated" or a list of objects, each with a name' for key in ("sections", "milestones", "items")
               if record[key] != NS and not named(record[key], "name")]
    for section in objects(record["sections"]):
        where = f"sections[{section.get('name')}]"
        errors += [] if section.get("required") in (True, False, NS) else [f'{where}.required must be true, false or "not_stated"']
        errors += limit_errors(section.get("limit"), f"{where}.limit")
    minimum = record["references_min"]
    errors += limit_errors(record["total_limit"], "total_limit") + ([] if minimum == NS or isinstance(minimum, dict) and positive(
        minimum.get("value")) else ['references_min must be "not_stated" or an object whose value is a positive number'])
    errors += [f'milestones[{m.get("name")}].date must be YYYY-MM-DD or "not_stated"' for m in objects(record["milestones"])
               if m.get("date", NS) != NS and not parse_date(m["date"])]
    return errors + [f"items[{i.get('name')}].kind must be one of {', '.join(KINDS)}" for i in objects(record["items"])
                     if i.get("kind") not in KINDS]


def load(directory: Path, name: str):
    """template.json, checked against the format of its reference, or brief.json (None when missing)."""
    path = directory / name
    if not path.is_file():
        return fail(f"no {name} in {directory}: write it first ({REFERENCES[name]}). Sections and limits come from the "
                    "school's files, never from memory.") if name == "template.json" else None
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")
    errors = ["it must hold a JSON object"] if not isinstance(data, dict) else record_errors(data) if name == "template.json" else []
    return fail(f"{path} is not in the format of {REFERENCES[name]}:\n  - " + "\n  - ".join(errors)) if errors else data


def period_of(brief):
    period = (brief or {}).get("period")
    days = (parse_date(period.get("start")), parse_date(period.get("end"), True)) if isinstance(period, dict) else (None,)
    return None if period is None else days if all(days) and days[0] <= days[1] else fail(
        f"brief.json: period needs a start and an end, each YYYY-MM-DD, the start first ({REFERENCES['brief.json']}).")


def entries(record: dict) -> list:
    """Every part of the record that a quote must back, with the numbers its quote must contain."""
    out = [{"entry": key, "state": NS} for key in ("sections", "total_limit", "references_min", "milestones", "items") if record[key] == NS]

    def add(label, node, says="", numbers=(), limit=None, parent=None):
        own = lambda key: str(node.get(key) or (parent or {}).get(key) or "").strip()  # noqa: E731
        out.append({"entry": label, "state": NS} if node == NS else {
            "entry": label, "says": says, "quote": own("quote"), "locator": own("locator"), "numbers": numbers, "limit": limit})

    values = lambda limit: tuple(limit[key] for key in ("min", "max", "about") if key in limit)  # noqa: E731
    for section in objects(record["sections"]):
        add(f"section: {section['name']}", section, {True: "required", False: "optional"}.get(section["required"], "required?"))
        limit = section["limit"]
        add(f"limit: {section['name']}", limit, *(() if limit == NS else (describe(limit), values(limit), limit, section)))
    if record["total_limit"] != NS:
        add("total_limit", record["total_limit"], describe(record["total_limit"]), values(record["total_limit"]), record["total_limit"])
    if record["references_min"] != NS:
        value = record["references_min"]["value"]
        add("references_min", record["references_min"], f"at least {value:g}", (value,))
    for item in objects(record["milestones"]):
        add(f"milestone: {item['name']}", item, str(item.get("date", NS)).replace(NS, "no date"))
    for item in objects(record["items"]):
        add(f"{item['kind']}: {item['name']}", item)
    return out


def cmd_template(args) -> int:
    directory, texts, hashes = Path(args.dir), {}, {}
    for path in map(Path, args.files):
        if path.name in texts:
            fail(f"two files are named {path.name}: rename one.")
        texts[path.name], hashes[path.name] = read_text(path), hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix.lower() == ".docx":
            write(directory / "text" / f"{path.name}.txt", [texts[path.name]])
    if not (directory / "template.json").is_file():
        print(json.dumps({"ok": False, "record": "missing", "sha256": hashes}, indent=2, ensure_ascii=False))
        fail(f"no template.json in {directory}. Read the files (the text of a .docx is in {directory / 'text'}), write the "
             "record (references/template-record.md) with the SHA-256 values above, and run this again.")
    record, period = load(directory, "template.json"), period_of(load(directory, "brief.json"))
    bodies, rows, states = {name: norm_quote(text) for name, text in texts.items()}, [], {}
    for entry in entries(record):
        state, where, quote, note = entry.get("state"), "", entry.get("quote", ""), "Not stated in the files."
        if state is None:
            where = ", ".join(name for name, body in bodies.items() if quote and norm_quote(quote) in body)
            missing = [f"{v:g}" for v in entry["numbers"] if float(v) not in numbers_in(quote)]
            state, note = (("no_quote", "") if not quote else
                           ("quote_too_short", f"Under {MIN_QUOTE_WORDS} words (a Han character is one).")
                           if count_words(quote) < MIN_QUOTE_WORDS else
                           ("quote_not_found", "Copy it again, word for word, from one paragraph.") if not where else
                           ("value_not_in_quote", f"{', '.join(missing)} is not in the quote.") if missing else
                           ("reading_differs", "The quote approximates (左右, 约, about): record the limit as about.")
                           if entry["limit"] and "about" not in entry["limit"] and APPROX.search(quote) else ("quote_found", ""))
        states.setdefault(state, []).append(entry["entry"])
        rows.append((entry["entry"], entry.get("says", ""), state, entry.get("locator", ""), where, note))
    listed = {Path(str(s["file"])).name: s["sha256"] for s in record["sources"]}
    for name in texts:
        state = "unchanged" if listed.get(name) == hashes[name] else "changed" if name in listed else "not_in_record"
        states.setdefault(state, []).append(name)
        rows.append((f"file: {name}", hashes[name][:16], state, "", "", "" if state == "unchanged" else
                     "Record this file in sources with the SHA-256 the JSON output gives; read it again if it changed."))
    limits = [(f"limit: {s['name']}", s["limit"]) for s in objects(record["sections"])] + [("total_limit", record["total_limit"])]
    ambiguous = [f"{label}: {describe(limit)}" for label, limit in limits if isinstance(limit, dict) and "about" in limit]
    conflicts = [f"{c.get('subject')}: {'; '.join(map(str, c.get('says') or []))}" for c in objects(record["conflicts"])
                 if str(c.get("decision") or NS).strip() in (NS, "not_decided")]
    ok = not any(states.get(state) for state in FAILING)
    lines = ["# Template record check", "", f"Document: {record['document']}." + (
        f" Period in brief.json: {period[0]} to {period[1]} ({span(*period)})." if period else ""), "",
        f"{len(rows)} rows: " + ", ".join(f"{len(v)} {k}" for k, v in states.items()) + f". Result: {'ok' if ok else 'failed'}.",
        "", *table(("Entry", "Says", "State", "Locator", "Found in", "Note"), rows)]
    for title, items, why in (("Ambiguous limits", ambiguous, "Approximate wording: check reports these as manual. Ask what counts."),
                              ("Open conflicts", conflicts, "The files disagree: the student decides which governs.")):
        lines += ["", f"## {title}", "", why, "", *[f"- {item}" for item in items]] if items else []
    output = {"ok": ok, "rows": len(rows), "states": states, "ambiguous_limits": ambiguous, "conflicts_open": conflicts,
              "sha256": hashes, "period": f"{period[0]} to {period[1]}: {span(*period)}" if period else NS,
              "template_sha256": hashlib.sha256((directory / "template.json").read_bytes()).hexdigest(),
              "report": str(directory / "template-check.md")}
    write(directory / "template-check.md", lines)
    write(directory / "template-check.json", [json.dumps(output, indent=2, ensure_ascii=False)])
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def limit_state(body: str, limit) -> tuple:
    squeezed = " ".join(plain(body).split())
    found = {"words": count_words(squeezed), "characters": len(squeezed.replace(" ", "")), "spaces": len(squeezed)}
    if limit == NS or limit["unit"] == "pages":
        return (NS, f"The template states no limit ({found['words']} words).") if limit == NS else (
            "not_checked", f"Limit {describe(limit)}: pages cannot be measured in Markdown; look at the exported file.")
    names = READINGS[limit["unit"]] if limit["unit"] != "characters" or limit.get("spaces", NS) == NS else (
        ("spaces",) if limit["spaces"] == "included" else ("characters",))
    told, says = "; ".join(f"{found[n]} {LABELS[n]}" for n in names), describe(limit)
    inside = [limit.get("min", 0) <= found[n] <= limit.get("max", float("inf")) for n in names]
    state = "manual" if "about" in limit else "pass" if all(inside) else "fail" if not any(inside) else "not_checked"
    return state, {"manual": f"The template says {says}, which is approximate; counted {told}. The student or supervisor decides.",
                   "pass": f"Within the limit ({says}): {told}.",
                   "fail": f"{'Below' if found[names[0]] < limit.get('min', 0) else 'Above'} the limit ({says}): {told}.",
                   "not_checked": f"In or out of {says} depending on what the template counts, which it does not say: {told}."}[state]


def rows_sections(record: dict, lines: list, heads: list) -> list:
    """Rows for the presence, order and limit of each section of the template."""
    if record["sections"] == NS:
        return [("sections", "proposal", NS, "The template prescribes no sections.", "")]
    first, rows, found = {head["key"]: head for head in reversed(heads)}, [], []
    for section in objects(record["sections"]):
        name, where, limit, head = section["name"], section.get("locator", ""), section["limit"], first.get(norm_name(section["name"]))
        if head is None:
            rows += [] if section["required"] is False else [("section_present", name, "fail" if section["required"] is True else NS,
                                                              "No heading with this name.", where)]
            continue
        found.append((head, name))
        rows.append(("section_present", name, "pass", f'Heading "{head["title"]}".', where))
        state, detail = limit_state("\n".join(lines[head["start"] + 1:head["end"]]), limit)
        rows.append(("section_limit", name, state, detail, (limit.get("locator") or where) if isinstance(limit, dict) else where))
    late = [name for index, (head, name) in enumerate(found) if any(head["start"] < h["start"] for h, _ in found[:index])]
    return rows + [("section_order", "proposal", "fail" if late else "pass", f"Out of the template's order: {'; '.join(late)}."
                    if late else "The sections follow the template's order.", "")]


def rows_citations(record: dict, path: Path, literature: Path) -> list:
    """Rows from the ledger's own check (review_ledger.py), and the reference minimum when the template states one."""
    minimum = record["references_min"]
    if not (literature / "ledger.json").is_file():
        why = f"No ledger at {literature / 'ledger.json'}: "
        return [("citations", "proposal", "not_checked", why + "citations were not compared with a ledger.", "")] + ([
            ("references_min", "proposal", "not_checked", why + "the cited papers were not counted.", minimum.get("locator", ""))
        ] if minimum != NS else [])
    try:
        ledger = rl.load(literature)
        found = rl.cmd_check(ledger, SimpleNamespace(review=str(path)))
        papers = {paper["key"]: paper for paper in ledger["papers"].values()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        fail(f"the ledger in {literature} cannot be read: {exc}")
    rows = [] if found["citations"] else [("citations", "proposal", "not_checked", "No [@key] citation in the draft; "
                                           "citations written another way are not checked.", "")]
    for check, key, says, good in (
            ("citations_in_ledger", "not_in_ledger", "Cited but not papers of the ledger", "papers of the ledger"),
            ("citations_included", "not_included", "Cited but excluded or undecided in the ledger", "included in the ledger"),
            ("citations_read", "cited_but_not_read", "Cited but not read (depth none or metadata)", "read in full or from the abstract"),
            ("citations_abstract_only", "cited_from_abstract_only", "Read from the abstract only; say no more than it reports", ""),
            ("citations_user_supplied", "not_from_the_index", "Supplied by the user, not from the index; the limitations say so", "")):
        bad = [k + (f" ({papers[k]['reason']})" if papers.get(k, {}).get("reason") else "") for k in found[key]]
        rows += [(check, "proposal", ("fail" if good else "manual") if bad else "pass", f"{says}: {', '.join(bad)}." if bad else
                  f"All {found['citations']} cited keys are {good}.", "")] if found["citations"] and (bad or good) else []
    if minimum != NS:
        cited = {k.rstrip("-") for k in rl.CITE_RE.findall(read_text(path)) if papers.get(k.rstrip("-"), {}).get("decision") == "included"}
        rows.append(("references_min", "proposal", "pass" if len(cited) >= minimum["value"] else "fail", f"{len(cited)} included "
                     f"papers cited; the template asks for at least {minimum['value']:g}.", minimum.get("locator", "")))
    return rows


def rows_questions(directory: Path, brief) -> list:
    """Every question of brief.json has a complete row in matrix.csv and a phase in timeline.csv."""
    ids = [str(q.get("id", "")).strip() for q in objects((brief or {}).get("questions"))]
    if not ids:
        return [("questions", "brief.json", "not_checked", "brief.json lists no research questions (step 4).", "")]
    if "" in ids or len(set(ids)) < len(ids):
        fail("brief.json: every question needs an id of its own.")
    matrix, timeline = (read_csv(directory / f"{name}.csv", columns) if (directory / f"{name}.csv").is_file() else None
                        for name, columns in (("matrix", MATRIX), ("timeline", TIMELINE)))
    rows = []
    for qid in ids:
        mine = [row for row in matrix or [] if row["question"] == qid]
        lacks = [c for c in MATRIX[1:] if any(not row[c] or PLACEHOLDER.fullmatch(row[c]) for row in mine)]
        phases = [row["phase"] for row in timeline or [] if qid in ids_of(row["questions"])]
        rows.append(("question_in_matrix", qid, "not_checked" if matrix is None else "fail" if lacks or not mine else "pass",
                     "matrix.csv not found." if matrix is None else "No row in matrix.csv." if not mine else
                     f"The row lacks: {', '.join(lacks)}." if lacks else "Content, method, data, phase and output stated.", ""))
        rows.append(("question_in_timeline", qid, "not_checked" if timeline is None else "pass" if phases else "fail",
                     "timeline.csv not found." if timeline is None else f"Phases: {'; '.join(phases)}." if phases
                     else "No phase of timeline.csv names it.", ""))
    return rows


def rows_leads(lines: list, heads: list) -> tuple:
    """Leads that never fail: result sentences with a number outside the literature, gap claims that name no search."""
    literature, results, gaps = [h for h in heads if LITERATURE.search(h["title"])], [], []
    for number, line in enumerate(lines):
        where, in_literature = heading_at(heads, number), any(h["start"] <= number < h["end"] for h in literature)
        for sentence in [] if HEADING.match(line) else filter(None, (part.strip() for part in SENTENCE.split(line))):
            gaps += [(where, sentence)] if GAP.search(sentence) and not SEARCHED.search(sentence) else []
            results += [(where, sentence)] if (not in_literature and "[@" not in sentence and not PLACEHOLDER.search(sentence)
                                               and re.search(r"\d", sentence) and RESULT.search(sentence)) else []
    rows, tail = [], []
    for check, found, says in (
            ("result_sentences", results, "report a result with a number outside the literature sections: the student "
             "confirms each is their own data, or it becomes a placeholder"),
            ("gap_claims", gaps, "say that something has not been studied and name no search: name the searches or reword")):
        rows.append((check, "proposal", "manual" if found else "pass", f"{len(found)} sentence(s) {says}." if found else "None found.", ""))
        tail += ["", f"## {check} (first {CAP})", "", *table(("Section", "Sentence"), found[:CAP])] if found else []
    return rows, tail


def cmd_check(args) -> int:
    directory, path = Path(args.dir), Path(args.proposal)
    record, brief = load(directory, "template.json"), load(directory, "brief.json")
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m[0].count("\n"), read_text(path), flags=re.S)
    lines, heads = outline(text)
    try:
        saved = json.loads((directory / "template-check.json").read_text(encoding="utf-8"))
        current = saved["template_sha256"] == hashlib.sha256((directory / "template.json").read_bytes()).hexdigest()
        verified = (("pass", "Every quote of the record is in the school's files.") if saved["ok"] else ("fail", "The last template "
                    "check failed.")) if current else ("not_checked", "template.json changed after the last template check: run it again.")
    except (OSError, ValueError, KeyError, TypeError):
        verified = ("not_checked", "The record has not been compared with the school's files: run the template command.")
    total = record["total_limit"]
    rows = [("record_verified", "template.json", *verified, ""), *rows_sections(record, lines, heads),
            ("total_limit", "whole proposal", *limit_state(text, total), total.get("locator", "") if isinstance(total, dict) else "")]
    open_items = [(heading_at(heads, text[:m.start()].count("\n")), m[0]) for m in PLACEHOLDER.finditer(text)]
    rows.append(("no_open_placeholders", "proposal", "pass" if not open_items else "fail" if args.final else "manual",
                 f"{len(open_items)} open placeholder(s), listed below; the student fills them." if open_items else "None left.", ""))
    lead_rows, tail = rows_leads(lines, heads)
    rows += rows_citations(record, path, Path(args.literature or directory / "literature")) + rows_questions(directory, brief) + lead_rows
    rows += [("template_item", f"{item['kind']}: {item['name']}", "manual", "Required by the template; the script cannot "
              "check it.", item.get("locator", "")) for item in objects(record["items"])]
    rows += [("template_item", "items", NS, "The template names no table, signature or other item.", "")] * (record["items"] == NS)
    rows += [("conflict", str(c.get("subject")), "manual", "Undecided between the files: " + "; ".join(map(str, c.get("says") or []))
              + ". The student decides which governs.", "") for c in objects(record["conflicts"])
             if str(c.get("decision") or NS).strip() in (NS, "not_decided")]
    tail = (["", "## Open placeholders", "", *table(("Section", "Placeholder"), open_items)] if open_items else []) + tail
    head = [f"Template: {record['document']}. Proposal: {path} ({count_words(plain(text))} words, headings included). "
            f"Run: {'final' if args.final else 'draft'}."]
    return finish(directory / "report.md", "Proposal check", head, rows, tail, {"final": bool(args.final), "placeholders": len(open_items)})


def finish(path: Path, title: str, head: list, rows: list, tail: list, extra: dict) -> int:
    tally = {state: sum(1 for row in rows if row[2] == state) for state in STATES}
    summary = (f"{len(rows)} checks: {tally['pass']} pass, {tally['fail']} fail, {tally['not_checked']} not checked, "
               f"{tally[NS]} not stated in the school's files, {tally['manual']} for a person to look at.")
    write(path, [f"# {title}", "", *head, "", summary, "", *table(("Check", "Subject", "State", "Detail", "Template"), rows), *tail])
    result = {"ok": tally["fail"] == 0, "counts": tally, **{name: [f"{r[0]}: {r[1]}" for r in rows if r[2] == state] for name, state in
                                                           (("failed", "fail"), ("not_checked", "not_checked"), ("manual", "manual"))},
              **extra, "report": str(path)}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def cmd_timeline(args) -> int:
    directory = Path(args.dir)
    path = Path(args.timeline) if args.timeline else directory / "timeline.csv"
    data = read_csv(path, TIMELINE) if path.is_file() else fail(f"no timeline at {path} (references/feasibility-and-timeline.md).")
    period = period_of(load(directory, "brief.json"))
    record = load(directory, "template.json") if (directory / "template.json").is_file() else None
    names, spans, undated, backwards = [row["phase"] for row in data], {}, [], []
    for number, row in enumerate(data, 2):
        name, start, end = row["phase"] or f"row {number}", parse_date(row["start"]), parse_date(row["end"], True)
        if start is None or end is None:
            undated.append(f"{name}: " + ", ".join(f"{k} {row[k]!r}" for k, day in (("start", start), ("end", end)) if day is None))
        elif start > end:
            backwards.append(f"{name} starts {start}, after it ends ({end})")
        else:
            spans[name] = (start, end)
    outside = [f"{n} starts {s}, before the period begins ({period[0]})" if s < period[0] else f"{n} ends {e}, after the "
               f"submission date ({period[1]})" for n, (s, e) in spans.items() if s < period[0] or e > period[1]] if period else []
    problems = [f"{row['phase']} depends on {dep}, which is not another phase" if dep not in names or dep == row["phase"]
                else f"{row['phase']} starts {spans[row['phase']][0]}, before {dep} ends ({spans[dep][1]})"
                for row in data for dep in ids_of(row["depends_on"]) if dep not in names or dep == row["phase"]
                or (row["phase"] in spans and dep in spans and spans[row["phase"]][0] < spans[dep][1])]
    rows = [(check, "timeline.csv", "fail" if found else "pass", lead + "; ".join(found) + "." if found else good, "")
            for check, found, lead, good in (
                ("date", undated, "Not a calendar date (write YYYY-MM-DD or YYYY-MM): ", "Every start and end is a calendar date."),
                ("start_before_end", backwards, "", "Every phase starts before it ends."),
                ("in_period", outside, "", f"Every phase falls within {period[0]} to {period[1]}." if period else ""),
                ("dependencies", problems, "", "Every phase starts after the phases it depends on end."))]
    rows[2] = rows[2] if period else ("in_period", "timeline.csv", "not_checked", "brief.json gives no period (step 3).", "")
    if record is None or record["milestones"] == NS:
        rows.append(("milestone", "template.json", "not_checked" if record is None else NS,
                     "template.json not found." if record is None else "The template requires no milestones.", ""))
    for milestone in objects(record["milestones"]) if record else []:
        key, due = norm_name(milestone["name"]), parse_date(milestone.get("date"), True)
        hits = [r["phase"] for r in data if key and (key in norm_name(r["phase"]) or key in norm_name(r["deliverable"]))]
        late = [h for h in hits if due and h in spans and spans[h][1] > due]
        rows.append(("milestone", milestone["name"], "fail" if late or not hits else "pass", "No phase or deliverable names it."
                     if not hits else f"{', '.join(late)} ends after the template's date {due}." if late else f"Phase: {', '.join(hits)}.",
                     milestone.get("locator", "")))
    ordered = sorted(spans.items(), key=lambda item: item[1])
    overlaps = [(a, b, f"{max(sa, sb)} to {min(ea, eb)}") for i, (a, (sa, ea)) in enumerate(ordered)
                for b, (sb, eb) in ordered[i + 1:] if sb <= ea]
    gaps, reach, day = [], None, timedelta(days=1)
    for _, (start, end) in ordered:
        gaps += [("no phase", f"{reach + day} to {start - day}")] if reach and start > reach + day else []
        reach = max(reach, end) if reach else end
    if period and reach and reach < period[1]:
        gaps.append(("after the last phase, before the submission date", f"{reach + day} to {period[1]} ({(period[1] - reach).days} days)"))
    tail = ["", "## Overlaps and gaps", "", "Listed, not judged: discuss them with the student. Phases with failed dates are left out.", ""]
    tail += [*table(("Phase", "Phase", "Overlap"), overlaps), ""] if overlaps else ["No phases overlap.", ""]
    tail += table(("Gap", "Dates"), gaps) if gaps else ["No gap between phases."]
    head = [f"Timeline: {path} ({len(data)} phases)." + (f" Period in brief.json: {period[0]} to {period[1]} ({span(*period)})."
                                                         if period else "")]
    return finish(directory / "timeline-check.md", "Timeline check", head, rows, tail, {
        "phases": len(data), "period": f"{period[0]} to {period[1]}: {span(*period)}" if period else NS,
        "overlaps": [f"{a} / {b}: {when}" for a, b, when in overlaps], "gaps": [f"{a}: {b}" for a, b in gaps]})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a thesis proposal against the school's own template.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="thesis-proposal", help="Folder of the record, tables and reports (default: thesis-proposal)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("template", parents=[common], help="Check that every quote of template.json is in the school's files")
    p.add_argument("files", nargs="+", help="The template and rules as .docx, .txt or .md (a PDF goes through pdftotext first)")
    p = sub.add_parser("check", parents=[common], help="Check the draft against the record, the ledger and the tables")
    p.add_argument("proposal", help="proposal.md")
    p.add_argument("--literature", help="The ledger's folder (default: <dir>/literature)")
    p.add_argument("--final", action="store_true", help="Before hand-in: open placeholders fail")
    p = sub.add_parser("timeline", parents=[common], help="Check timeline.csv against the period and the template's milestones")
    p.add_argument("timeline", nargs="?", help="timeline.csv (default: <dir>/timeline.csv)")
    args = parser.parse_args(argv)
    return {"template": cmd_template, "check": cmd_check, "timeline": cmd_timeline}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
