#!/usr/bin/env python3
"""Check a grant proposal against the call it answers, never against memory.

The agent reads the call and writes what it demands into grant/requirements.json, every entry
with a quote and a locator. This script does the three checks that are mechanical:

  grant_check.py call grant/call.txt                    every quote of the record is in the call text
  grant_check.py check grant/proposal.md                sections, limits, placeholders, criteria, aims
  grant_check.py check grant/sections/ --pdf out.pdf    a folder of section files; total pages from the PDF
  grant_check.py check grant/proposal.md --final        before submission: open placeholders fail
  grant_check.py budget grant/budget.csv --proposal grant/proposal.md
                                                        sums, arithmetic, the cap, lines without an aim

All commands take --dir (default: grant), the folder that holds requirements.json, aims.json,
criteria.md, timeline.csv and budget.csv and receives the reports, and --requirements.

  call    writes call-check.md and call-check.json. Quotes are compared after removing differences
          of case, spacing, hyphenation at line breaks, and quote and dash characters.
  check   writes report.md, one row per check, in the states pass, fail, not_checked, not_stated.
  budget  writes budget-check.md. It adds up the amounts in the table and compares them; it never
          computes a rate, an overhead or a salary.

Each command prints a JSON summary. Exit code 0 when nothing failed. 1 when: (call) a quote is not
in the call text, or a limit, the budget cap or the project period has no quote; (check, budget)
any row is `fail`. 2 when an input cannot be read or is not in the format of the references.
`not_checked` and `not_stated` never fail and never pass: report them as they are.

Standard library only, no network. --pdf uses `pdfinfo` (poppler) when it is installed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

NOT_STATED = "not_stated"
STATES = ("pass", "fail", "not_checked", NOT_STATED)
UNITS = ("words", "characters", "pages")
COUNT_KEYS = ("references", "tables", "figure_captions", "spaces")
COUNT_RULES = ("included", "excluded", NOT_STATED)
PARTS = {"text": "main text", "references": "references", "tables": "tables", "figure_captions": "figure captions"}
RECORD_KEYS = ("call", "sections", "total_limit", "criteria", "budget", "deadline", "eligibility",
               "formatting", "ai_policy", "attachments")
CALL_KEYS = ("identifier", "funder", "mechanism", "source", "date_read")
BUDGET_KEYS = ("cap", "currency", "period", "rules")
RULE_KEYS = ("deadline", "eligibility", "formatting", "ai_policy")
AIM_FIELDS = {"learned": "what will be learned", "success_criterion": "a success criterion",
              "risk": "a risk", "alternative": "an alternative"}
TIMELINE_COLUMNS = ("milestone", "aim", "start_month", "end_month")
BUDGET_COLUMNS = ("line", "category", "year", "amount", "aim")
OWN_FILES = frozenset({"report.md", "budget-check.md", "call-check.md", "criteria.md"})
MIN_QUOTE_WORDS = 3     # a shorter quote is found in any call and proves nothing
ROUNDING = 0.5          # amounts may be rounded to a whole unit of the currency

PLACEHOLDER = re.compile(r"\[\s*(?:Evidence|Citation|Author input) needed\b[^\]]*\]", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
NUMBERING = re.compile(r"^\s*(?:(?:section|part)\s+)?(?:[a-z]?\d+(?:\.\d+)*[a-z]?[.):]?|[a-z][.):]|[ivxlc]+[.):])"
                       r"[\s–—:-]*")
REFERENCE_HEADING = frozenset({"references", "reference list", "bibliography", "works cited", "literature cited"})
CAPTION = re.compile(r"^\s*[*_]{0,2}(fig(?:ure)?\.?|table)\s+\d+", re.I)
HAN = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")
NUMBER = r"[1-9]\d{0,2}(?:[ \u00a0\u202f,.']\d{3}(?!\d))+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?"
SCALED = rf"(?:{NUMBER})(?:\s?(?:k|m|million|thousand)\b)?"
SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}
NUMBER_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                "sixteen seventeen eighteen nineteen twenty").split()
QUOTE_MARKS = dict.fromkeys(map(ord, "‘’‚‛“”„‟«»‹›´`\""), "'")
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")


def fail(message: str):
    print(f"grant_check: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_text(path: Path) -> str:
    if not path.is_file():
        fail(f"no such file: {path}")
    raw = path.read_bytes()
    if raw.startswith(b"%PDF"):
        fail(f"{path} is a PDF. Turn it into text first, for example: pdftotext -layout {path} grant/call.txt")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        fail(f"{path} is not UTF-8 text.")


def read_json(path: Path) -> dict:
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        fail(f"{path} must hold a JSON object.")
    return data


def read_csv(path: Path, required: tuple) -> list:
    """The rows of a CSV as dicts with lower-case column names. The delimiter may be , ; or a tab."""
    lines = read_text(path).splitlines()
    reader = csv.DictReader(lines, delimiter=max(",;\t", key=(lines[0] if lines else "").count))
    columns = {name: (name or "").strip().lower() for name in reader.fieldnames or []}
    missing = [name for name in required if name not in columns.values()]
    if missing:
        fail(f"{path} lacks the column(s) {', '.join(missing)}. It needs: {', '.join(required)}.")
    rows = [{columns[key]: (row.get(key) or "").strip() for key in columns} for row in reader]
    return [row for row in rows if any(row.values())]


def read_proposal(path: Path) -> str:
    """One Markdown file, or every .md file of a folder in name order. A file with no heading is
    a section named after the file. Comments are blanked so that they are not counted."""
    if path.is_dir():
        files = sorted(p for p in path.glob("*.md") if p.name not in OWN_FILES)
        if not files:
            fail(f"no .md section files in {path}")
        chunks = []
        for file in files:
            text = read_text(file)
            if not any(HEADING.match(line) for line in text.splitlines()):
                name = re.sub(r"^[\W\d_]+", "", file.stem).replace("-", " ").replace("_", " ")
                text = f"# {name}\n\n{text}"
            chunks.append(text)
        text = "\n\n".join(chunks)
    else:
        text = read_text(path)
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def num(value) -> str:
    """A number as the reports print it: 12,000 or 12,000.50."""
    text = f"{value:,.2f}"
    return text[:-3] if text.endswith(".00") else text


def table(header: tuple, rows: list) -> list:
    cell = lambda value: re.sub(r"\s+", " ", str(value)).replace("|", "/").strip()  # noqa: E731
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)]


def write(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def as_list(node) -> list:
    return node if isinstance(node, list) else []


def positive(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def named_list(node, field: str = "name") -> bool:
    return isinstance(node, list) and bool(node) and all(isinstance(i, dict) and str(i.get(field, "")).strip() for i in node)


def limit_errors(limit, where: str) -> list:
    if limit == NOT_STATED:
        return []
    if not isinstance(limit, dict):
        return [f'{where} must be "not_stated" or an object with value, unit and counts']
    errors = [] if positive(limit.get("value")) else [f"{where}.value must be a positive number"]
    if limit.get("unit") not in UNITS:
        errors.append(f"{where}.unit must be one of {', '.join(UNITS)}")
    counts = limit.get("counts", NOT_STATED)
    if counts != NOT_STATED and not (isinstance(counts, dict) and set(counts) <= set(COUNT_KEYS)
                                     and set(counts.values()) <= set(COUNT_RULES)):
        errors.append(f'{where}.counts must be "not_stated" or an object with the keys {", ".join(COUNT_KEYS)}, '
                      f'each {", ".join(COUNT_RULES)}')
    return errors


def record_errors(record: dict) -> list:
    """Everything that keeps the record from being used. A key the call is silent on must still be
    there, as "not_stated": that is what separates silence from an item nobody looked for."""
    errors = [f'{key} is missing (write "not_stated" when the call is silent)' for key in RECORD_KEYS if key not in record]
    call = record.get("call")
    if not isinstance(call, dict):
        return errors + (["call must be an object"] if "call" in record else [])
    errors += [f"call.{key} is missing" for key in CALL_KEYS if key not in call]
    if str(call.get("source") or NOT_STATED) == NOT_STATED:
        errors.append("call.source must name the file or URL that was read")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(call.get("date_read", ""))):
        errors.append("call.date_read must be the date the call was read, as YYYY-MM-DD")
    errors += [f'{key} must be "not_stated" or a list of objects, each with a name' for key in ("sections", "criteria", "attachments")
               if record.get(key, NOT_STATED) != NOT_STATED and not named_list(record[key])]
    for section in record["sections"] if named_list(record.get("sections")) else []:
        where = f"sections[{section['name']}]"
        if section.get("required") not in (True, False, NOT_STATED):
            errors.append(f'{where}.required must be true, false or "not_stated"')
        errors += limit_errors(section["limit"], f"{where}.limit") if "limit" in section else [
            f'{where}.limit is missing (write "not_stated")']
    errors += limit_errors(record.get("total_limit", NOT_STATED), "total_limit")
    budget = record.get("budget", NOT_STATED)
    if isinstance(budget, dict):
        errors += [f'budget.{key} is missing (write "not_stated")' for key in BUDGET_KEYS if key not in budget]
        errors += [f'budget.{key} must be "not_stated" or an object whose {field} is a positive number'
                   for key, field in (("cap", "value"), ("period", "months")) if budget.get(key, NOT_STATED) != NOT_STATED
                   and not (isinstance(budget[key], dict) and positive(budget[key].get(field)))]
        if budget.get("rules", NOT_STATED) != NOT_STATED and not named_list(budget["rules"], "rule"):
            errors.append('budget.rules must be "not_stated" or a list of objects, each with a rule')
    elif budget != NOT_STATED:
        errors.append('budget must be "not_stated" or an object')
    return errors + [f'{key} must be "not_stated" or an object with a value' for key in RULE_KEYS
                     if record.get(key, NOT_STATED) != NOT_STATED and not named_list([record[key]], "value")]


def load_record(args) -> tuple:
    path = Path(args.requirements) if args.requirements else Path(args.dir) / "requirements.json"
    if not path.is_file():
        fail(f"no requirements record at {path}. Read the call and write the record first "
             "(references/call-record.md): structure and limits come from the call.")
    record = read_json(path)
    errors = record_errors(record)
    if errors:
        fail(f"{path} is not in the format of references/call-record.md:\n  - " + "\n  - ".join(errors))
    return path, record


def call_line(record: dict) -> str:
    call = record["call"]
    return (f"Call: {call['identifier']}, {call['funder']}, {call['mechanism']}. "
            f"Source: {call['source']}, read {call['date_read']}.")


def entries(record: dict) -> list:
    """Every part of the record that a quote should back, in the record's order. `must` marks the
    numbers that later checks rest on (limits, the budget cap, the project period)."""
    out = []
    need = {True: "required", False: "optional"}

    def add(label, node, says="", number=None, must=False, parent=None):
        if node == NOT_STATED:
            return out.append({"entry": label, "state": NOT_STATED})
        own = lambda key: str(node.get(key) or (parent or {}).get(key) or "").strip()  # noqa: E731
        out.append({"entry": label, "says": says, "quote": own("quote"), "locator": own("locator"),
                    "number": number, "must": must})

    def number(label, node, field="value", unit=None, parent=None):
        value = None if node == NOT_STATED else node[field]
        add(label, node, "" if value is None else f"{num(value)} {unit or node['unit']}".strip(), value, True, parent)

    silent = [f"call.{key}" for key in ("identifier", "mechanism") if record["call"][key] == NOT_STATED]
    for key in silent + [key for key in ("sections", "criteria", "attachments", "budget") if record[key] == NOT_STATED]:
        add(key, NOT_STATED)
    for section in as_list(record["sections"]):
        add(f"section: {section['name']}", section, need.get(section["required"], "requirement not stated"))
        number(f"limit: {section['name']}", section["limit"], parent=section)
    number("total_limit", record["total_limit"])
    for criterion in as_list(record["criteria"]):
        weight = criterion.get("weight", NOT_STATED)
        add(f"criterion: {criterion['name']}", criterion, "" if weight == NOT_STATED else f"weight {weight}")
        if weight == NOT_STATED:
            add(f"weight: {criterion['name']}", NOT_STATED)
    budget = record["budget"]
    if budget != NOT_STATED:
        number("budget.cap", budget["cap"], unit="(currency not stated)" if budget["currency"] == NOT_STATED else budget["currency"])
        if budget["currency"] == NOT_STATED:
            add("budget.currency", NOT_STATED)
        number("budget.period", budget["period"], "months", "months")
        if budget["rules"] == NOT_STATED:
            add("budget.rules", NOT_STATED)
        for index, rule in enumerate(as_list(budget["rules"]), 1):
            add(f"budget rule {index}", rule, rule["rule"])
    for key in RULE_KEYS:
        add(key, record[key], "" if record[key] == NOT_STATED else str(record[key]["value"]))
    for attachment in as_list(record["attachments"]):
        add(f"attachment: {attachment['name']}", attachment, need.get(attachment.get("required"), "requirement not stated"))
    return out


def norm_quote(text: str) -> str:
    """Text as compared: case, spacing, a word split at a line break, quote and dash characters,
    hyphens inside words and Markdown emphasis make no difference."""
    text = unicodedata.normalize("NFKC", text).translate(QUOTE_MARKS).translate(DASHES).replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-[ \t]*\n\s*(?=\w)", "", text)
    text = re.sub(r"(?<=\w)-(?=\w)", "", text)
    return " ".join(re.sub(r"[*`]", "", text).replace("|", " ").casefold().split())


def parse_number(text: str):
    """12,000 · 12 000 · 12.000,50 · 12'000 · 1.5k as a float; None when the text is not a number.
    One separator followed by exactly three digits is read as a thousands separator."""
    match = re.fullmatch(r"\s*(\d[\d\s.,'\u00a0\u202f]*?)\s*(k|m|million|thousand)?\s*", text or "", re.I)
    if not match:
        return None
    digits = re.sub(r"[\s'\u00a0\u202f]", "", match.group(1))
    if "," in digits and "." in digits:
        cut = max(digits.rfind(","), digits.rfind("."))
        digits = re.sub(r"[.,]", "", digits[:cut]) + "." + digits[cut + 1:]
    elif re.fullmatch(r"[1-9]\d{0,2}(?:[.,]\d{3})+", digits):
        digits = re.sub(r"[.,]", "", digits)
    try:
        return float(digits.replace(",", ".")) * SCALE.get((match.group(2) or "").lower(), 1)
    except ValueError:
        return None


def numbers_in(text: str) -> set:
    found = {parse_number(m.group(0)) for m in re.finditer(SCALED, text, re.I)}
    found |= {float(n) for n, word in enumerate(NUMBER_WORDS) if re.search(rf"\b{word}\b", text, re.I)}
    return found - {None}


def norm_name(text: str) -> str:
    """A section, criterion or heading name as matched: case, numbering, emphasis, a closing
    bracket such as "(max. 500 words)" and punctuation make no difference."""
    text = unicodedata.normalize("NFKC", text).casefold().replace("&", " and ")
    text = re.sub(r"\s*[(\[][^)\]]*[)\]]\s*$", "", re.sub(r"[*_`]", " ", text).strip())
    return " ".join(re.findall(r"\w+", NUMBERING.sub("", text, count=1)) or re.findall(r"\w+", text))


def outline(text: str) -> tuple:
    """(lines, headings). A heading spans to the next heading of its own or a higher level."""
    lines, headings, fenced = text.splitlines(), [], False
    for number, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        match = None if fenced else HEADING.match(line)
        if match:
            headings.append({"level": len(match.group(1)), "title": match.group(2), "key": norm_name(match.group(2)),
                             "start": number})
    for index, heading in enumerate(headings):
        heading["end"] = next((later["start"] for later in headings[index + 1:] if later["level"] <= heading["level"]),
                              len(lines))
        heading["title_of_document"] = index == 0 and heading["end"] == len(lines) and len(headings) > 1
    return lines, headings


def heading_at(headings: list, line: int) -> str:
    """The headings that enclose a line, outermost first, without the document's title."""
    chain = [h["title"] for h in headings if h["start"] <= line < h["end"] and not h["title_of_document"]]
    return " > ".join(chain) or "(before the first section)"


def and_list(items: list) -> str:
    return " and ".join([", ".join(items[:-1]), items[-1]] if len(items) > 1 else items)


def plain(text: str) -> str:
    """Markdown with its markup taken off, so that markup is not counted."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}|[-*+]|\d+[.)]|>)\s+", "", text)
    text = re.sub(r"(?m)^[\s|:-]+$", "", text)
    return re.sub(r"[*`|]", " ", text)


def split_parts(lines: list) -> dict:
    """A section's lines sorted into main text, references (under a sub-heading such as
    "References"), tables (pipe rows and "Table N" caption lines) and figure captions (image lines
    and "Figure N" caption lines)."""
    parts = {name: [] for name in PARTS}
    reference_level = None
    for line in lines:
        heading = HEADING.match(line)
        if heading and reference_level is not None and len(heading.group(1)) <= reference_level:
            reference_level = None
        if heading and reference_level is None and norm_name(heading.group(2)) in REFERENCE_HEADING:
            reference_level = len(heading.group(1))
        caption = CAPTION.match(line)
        if reference_level is not None:
            name = "references"
        elif line.lstrip().startswith("|") or (caption and caption.group(1).lower() == "table"):
            name = "tables"
        elif caption or line.lstrip().startswith("!["):
            name = "figure_captions"
        else:
            name = "text"
        parts[name].append(line)
    return {name: plain("\n".join(chunk)) for name, chunk in parts.items()}


def count(text: str, unit: str, spaces: bool = True) -> int:
    """Words as a word processor counts them (a Han or kana character is one word), or characters."""
    if unit == "words":
        return len(HAN.findall(text)) + sum(1 for token in HAN.sub(" ", text).split() if any(c.isalnum() for c in token))
    text = " ".join(text.split())
    return len(text) if spaces else len(text.replace(" ", ""))


def limit_state(parts: dict, limit: dict) -> tuple:
    """(state, detail) for a word or character limit. What the record does not settle (do references
    count, do spaces count) is counted both ways; when the two counts fall on different sides of
    the limit, the state is not_checked."""
    unit, value = limit["unit"], limit["value"]
    counts = limit.get("counts") if isinstance(limit.get("counts"), dict) else {}
    spaces = counts.get("spaces", NOT_STATED) if unit == "characters" else "included"
    low = high = 0
    told, unsettled = [], []
    for name, label in PARTS.items():
        rule = "included" if name == "text" else counts.get(name, NOT_STATED)
        most, least = count(parts[name], unit, spaces != "excluded"), count(parts[name], unit, spaces == "included")
        if rule != "excluded":
            high += most
            low += least if rule == "included" else 0
        if name == "text":
            told.append(f"main text {most}")
        elif most:
            told.append(f"{label} {'left out' if rule == 'excluded' else 'counted' if rule == 'included' else 'not settled'} ({most})")
            unsettled += [label] if rule == NOT_STATED else []
    if spaces == NOT_STATED:
        unsettled.append("spaces")
    if spaces != "included" and unit == "characters":
        told.append("spaces " + ("left out" if spaces == "excluded" else "not settled"))
    counted = "; ".join(told)
    if high <= value:
        return "pass", f"{high} {unit}, limit {num(value)}. Counted: {counted}."
    if low > value:
        amount = f"{high} {unit}" if low == high else f"{low} to {high} {unit}"
        return "fail", f"{amount}, over the limit of {num(value)}. Counted: {counted}."
    return "not_checked", (f"{low} to {high} {unit} depending on whether {' and '.join(unsettled)} count, which the "
                           f"record does not state; limit {num(value)}. Counted: {counted}.")


def amounts_in_text(text: str, currency: str) -> list:
    """(position, value, as written) for each number written next to a currency symbol or the
    record's currency. Bare numbers are not amounts."""
    symbols = "|".join(re.escape(symbol) for symbol in "€$£¥₹₩")
    before = symbols + (rf"|(?<![A-Za-z]){re.escape(currency)}" if currency else "")
    after = symbols + (rf"|{re.escape(currency)}(?![A-Za-z])" if currency else "")
    found = []

    def take(match):
        found.append((match.start(), parse_number(match.group(1)), " ".join(match.group(0).split())))
        return " " * len(match.group(0))

    rest = re.sub(rf"(?:{before})\s?({SCALED})", take, text, flags=re.I)   # "EUR 12,000" before "12,000 EUR"
    re.sub(rf"({SCALED})\s?(?:{after})", take, rest, flags=re.I)
    return sorted(found)


def cmd_call(args) -> int:
    directory = Path(args.dir)
    record_path, record = load_record(args)
    text = read_text(Path(args.call))
    pages = [norm_quote(page) for page in text.split("\f")]
    whole = norm_quote(text.replace("\f", "\n"))
    result = {name: [] for name in ("quote_not_found", "no_quote", "quote_too_short", "limits_without_quote",
                                    "value_not_in_quote", NOT_STATED)}
    rows, found = [], 0
    for entry in entries(record):
        state, page, note = entry.get("state"), "", ""
        if state == NOT_STATED:
            result[NOT_STATED].append(entry["entry"])
            rows.append((entry["entry"], "", state, "", "", "The call does not state this."))
            continue
        quote = entry["quote"]
        key = norm_quote(quote)
        if not quote:
            state = "no_quote"
        elif len(quote.split()) < MIN_QUOTE_WORDS:
            state, note = "quote_too_short", f"Fewer than {MIN_QUOTE_WORDS} words: counts as no quote."
        elif key in whole:
            state, found = "quote_found", found + 1
            page = next((n for n, body in enumerate(pages, 1) if key in body), "") if len(pages) > 1 else ""
            if entry["number"] is not None and float(entry["number"]) not in numbers_in(quote):
                note = f"The value {num(entry['number'])} is not in the quote: compare them by eye."
                result["value_not_in_quote"].append(entry["entry"])
        else:
            state = "quote_not_found"
            note = "Copy the passage again, word for word, from one place" + (
                "; a quote is continuous, with no ellipsis." if re.search(r"\.\.\.|…", quote) else ".")
        if state != "quote_found":
            result[state].append(entry["entry"])
            if entry["must"] and state != "quote_not_found":
                result["limits_without_quote"].append(entry["entry"])
                note = (note + " A limit, cap or period needs the call's own words.").strip()
        rows.append((entry["entry"], entry["says"], state, entry["locator"], page, note))
    ok = not (result["quote_not_found"] or result["limits_without_quote"])
    summary = (f"{len(rows)} entries: {found} quote found, {len(result['quote_not_found'])} quote not found, "
               f"{len(result['no_quote']) + len(result['quote_too_short'])} without a usable quote, "
               f"{len(result[NOT_STATED])} not stated in the call. Result: {'ok' if ok else 'failed'}.")
    write(directory / "call-check.md", ["# Call record check", "", call_line(record), "", summary, "",
                                        *table(("Entry", "Says", "State", "Locator", "Page found", "Note"), rows)])
    result = {"ok": ok, "call": record["call"], "entries": len(rows), "quote_found": found, **result,
              "requirements_sha256": sha256(record_path), "report": str(directory / "call-check.md")}
    write(directory / "call-check.json", [json.dumps(result, indent=2, ensure_ascii=False)])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def record_verified(directory: Path, record_path: Path) -> tuple:
    path = directory / "call-check.json"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "not_checked", "The record has not been compared with the call text: run the call command."
    if not isinstance(saved, dict) or saved.get("requirements_sha256") != sha256(record_path):
        return "not_checked", "requirements.json changed after the last call check: run the call command again."
    if saved.get("ok"):
        return "pass", "Every quote of the record was found in the call text."
    return "fail", "The last call check failed: a quote is not in the call text, or a limit has no quote."


def pdf_pages(path: Path) -> tuple:
    """(pages, "") from pdfinfo, or (None, why the pages were not counted)."""
    if not path.is_file():
        fail(f"no such file: {path}")
    tool = shutil.which("pdfinfo")
    if not tool:
        return None, "pdfinfo (poppler) is not installed, so the PDF's pages were not counted"
    try:
        output = subprocess.run([tool, str(path)], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"pdfinfo failed ({exc})"
    match = re.search(r"^Pages:\s+(\d+)", output, re.M)
    return (int(match.group(1)), "") if match else (None, "pdfinfo did not report a page count")


def rows_sections(record: dict, lines: list, headings: list) -> tuple:
    """Rows for presence and limits, and two lists: optional sections left out, stray headings."""
    sections = record["sections"]
    if sections == NOT_STATED:
        return [("sections", "proposal", NOT_STATED, "The call prescribes no sections.", "")], [], []
    first = {}
    for heading in headings:
        first.setdefault(heading["key"], heading)
    rows, left_out, matched = [], [], []
    for section in sections:
        name, where = section["name"], section.get("locator", "")
        heading = first.get(norm_name(name))
        if heading is None:
            if section["required"] is True:
                rows.append(("section_present", name, "fail", "Required by the call; no heading with this name.", where))
            elif section["required"] == NOT_STATED:
                rows.append(("section_present", name, NOT_STATED,
                             "The call does not say whether it is required; it is not in the proposal.", where))
            else:
                left_out.append(name)
            continue
        matched.append(heading)
        rows.append(("section_present", name, "pass", f'Heading "{heading["title"]}".', where))
        limit, parts = section["limit"], split_parts(lines[heading["start"] + 1:heading["end"]])
        if limit == NOT_STATED:
            words = count(" ".join(parts.values()), "words")
            rows.append(("section_limit", name, NOT_STATED, f"The call states no limit for this section ({words} words).", where))
        elif limit["unit"] == "pages":
            rows.append(("section_limit", name, "not_checked", f"Limit {num(limit['value'])} pages. Pages cannot be "
                         "measured per section from Markdown: look at the rendered file.", limit.get("locator") or where))
        else:
            rows.append(("section_limit", name, *limit_state(parts, limit), limit.get("locator") or where))
    stray = [h["title"] for h in headings if h not in matched and not any(
        m["start"] < h["start"] < m["end"] or h["start"] < m["start"] < h["end"] for m in matched)]
    return rows, left_out, stray


def row_total(record: dict, lines: list, pdf) -> tuple:
    total = record["total_limit"]
    pages, why = pdf_pages(Path(pdf)) if pdf else (None, "no PDF was given (--pdf)")
    seen = f" The PDF has {pages} pages." if pages is not None else ""
    if total == NOT_STATED:
        return "total_limit", "whole proposal", NOT_STATED, "The call states no limit for the whole proposal." + seen, ""
    where, value = total.get("locator", ""), total["value"]
    if total["unit"] != "pages":
        return ("total_limit", "whole proposal", *limit_state(split_parts(lines), total), where)
    if pages is None:
        return "total_limit", "whole proposal", "not_checked", f"Limit {num(value)} pages; {why}.", where
    counts = total.get("counts") if isinstance(total.get("counts"), dict) else {}
    apart = [label for name, label in PARTS.items() if name != "text" and counts.get(name, NOT_STATED) != "included"]
    if pages <= value:
        return "total_limit", "whole proposal", "pass", f"{pages} pages in the PDF, limit {num(value)}.", where
    if not apart:
        return "total_limit", "whole proposal", "fail", f"{pages} pages in the PDF, over the limit of {num(value)}.", where
    return ("total_limit", "whole proposal", "not_checked", f"{pages} pages in the PDF, limit {num(value)}; the record "
            f"does not count {', '.join(apart)} as certainly included, and they cannot be told apart in a PDF.", where)


def rows_criteria(directory: Path, record: dict, headings: list) -> list:
    criteria = record["criteria"]
    if criteria == NOT_STATED:
        return [("criterion_mapped", "criteria", NOT_STATED, "The call states no review criteria.", "")]
    path = directory / "criteria.md"
    if not path.is_file():
        return [("criterion_mapped", "criteria.md", "not_checked", f"{path} not found: no criterion is mapped yet.", "")]
    mapped, in_table = {}, False
    for line in read_text(path).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        if not in_table:
            in_table = [norm_name(c) for c in cells[:2]] == ["criterion", "where addressed"]
        elif not cells:
            break
        elif len(cells) > 1 and not set("".join(cells)) <= set("-: "):
            mapped[norm_name(cells[0])] = (cells[0], [part.strip() for part in cells[1].split(";") if part.strip()])
    if not in_table:
        return [("criterion_mapped", "criteria.md", "fail",
                 "No table whose header starts with | Criterion | Where addressed | (references/review.md).", "")]
    keys, rows = {h["key"] for h in headings}, []
    for criterion in criteria:
        name, where = criterion["name"], criterion.get("locator", "")
        _, places = mapped.pop(norm_name(name), ("", None))
        unknown = [place for place in places or [] if norm_name(place) not in keys]
        if places is None:
            rows.append(("criterion_mapped", name, "fail", "No row for this criterion in criteria.md.", where))
        elif not places:
            rows.append(("criterion_mapped", name, "fail", '"Where addressed" is empty.', where))
        elif unknown:
            rows.append(("criterion_mapped", name, "fail", f"Names a section that is not a heading of the proposal: "
                         f"{'; '.join(unknown)}.", where))
        else:
            rows.append(("criterion_mapped", name, "pass", "Addressed in: " + "; ".join(places) + ".", where))
    extra = [written for written, _ in mapped.values()]
    rows.append(("criteria_from_the_call", "criteria.md", "fail" if extra else "pass",
                 f"Rows for criteria that are not in the record: {'; '.join(extra)}." if extra
                 else "Every row is a criterion of the record.", ""))
    return rows


def ids_of(value) -> list:
    items = value if isinstance(value, list) else re.split(r"[;,]", str(value or ""))
    return [str(item).strip() for item in items if str(item).strip()]


def blank(value) -> bool:
    text = str(value or "").strip()
    return not text or bool(PLACEHOLDER.fullmatch(text))


def is_total(row: dict) -> bool:
    return bool({row.get("line", "").casefold(), row.get("category", "").casefold()} & {"total", "subtotal", "grand total"})


def load_aims(path: Path) -> list:
    aims = read_json(path).get("aims")
    if not isinstance(aims, list) or not aims or not all(isinstance(a, dict) and str(a.get("id", "")).strip() for a in aims):
        fail(f'{path} must hold a non-empty list "aims" of objects, each with an "id" (references/aims.md).')
    ids = [str(aim["id"]).strip() for aim in aims]
    if len(set(ids)) != len(ids):
        fail(f"{path}: two aims share an id.")
    return aims


def rows_aims(directory: Path, record: dict) -> list:
    path = directory / "aims.json"
    if not path.is_file():
        return [("aims", "aims.json", "not_checked", f"{path} not found: aims, milestones and budget lines were not checked.", "")]
    aims = load_aims(path)
    ids = [str(aim["id"]).strip() for aim in aims]
    links = []      # (key in aims.json, file, id column, noun, rows or None)
    for key, name, column, noun, required in (("milestones", "timeline.csv", "milestone", "milestone", TIMELINE_COLUMNS),
                                              ("budget_lines", "budget.csv", "line", "budget line", BUDGET_COLUMNS)):
        file = directory / name
        links.append((key, name, column, noun,
                      [row for row in read_csv(file, required) if not is_total(row)] if file.is_file() else None))
    rows = []
    for aim, aim_id in zip(aims, ids):
        missing = [label for field, label in AIM_FIELDS.items() if blank(aim.get(field))]
        rows.append(("aim_fields", aim_id, "fail" if missing else "pass", "Missing: " + ", ".join(missing) + "." if missing
                     else "States what will be learned, a success criterion, a risk and an alternative.", ""))
        needs = ids_of(aim.get("depends_on"))
        unknown = [other for other in needs if other not in ids or other == aim_id]
        if unknown:
            rows.append(("aim_fallback", aim_id, "fail", f"depends_on names {', '.join(unknown)}, which is not another aim.", ""))
        elif needs:
            lacks = blank(aim.get("fallback"))
            rows.append(("aim_fallback", aim_id, "fail" if lacks else "pass", f"Depends on the result of {and_list(needs)}"
                         + (" but states no fallback." if lacks else "; a fallback is stated."), ""))
        for key, name, column, noun, data in links:
            check = f"aim_{noun.replace(' ', '_')}"
            if data is None:
                rows.append((check, aim_id, "not_checked", f"{name} not found.", ""))
                continue
            listed, known = set(ids_of(aim.get(key))), {row[column] for row in data}
            named = {row[column] for row in data if aim_id in ids_of(row["aim"])}
            problems = [f"No {noun} in {name} names this aim"] if not named else []
            if listed - known:
                problems.append(f"aims.json lists {', '.join(sorted(listed - known))}, which {name} does not have")
            if (listed & known) - named:
                problems.append(f"{', '.join(sorted((listed & known) - named))} is listed in aims.json but names another aim in {name}")
            if named - listed:
                problems.append(f"{', '.join(sorted(named - listed))} names this aim in {name} but aims.json does not list it")
            rows.append((check, aim_id, "fail" if problems else "pass",
                         "; ".join(problems) + "." if problems else ", ".join(sorted(named)) + ".", ""))
    for key, name, column, noun, data in links:
        if data is None:
            continue
        bad = []
        for row in data:
            unknown = [a for a in ids_of(row["aim"]) if a not in ids and a.casefold() != "project"]
            if unknown or not ids_of(row["aim"]):
                bad.append(f"{row[column] or '(no id)'} ({'aim ' + ', '.join(unknown) + ' does not exist' if unknown else 'no aim'})")
        rows.append((f"{name.split('.')[0]}_aims", name, "fail" if bad else "pass", "; ".join(bad) + "." if bad
                     else f"Every {noun} names an aim of aims.json, or project.", ""))
    timeline = links[0][4]
    period = NOT_STATED if record["budget"] == NOT_STATED else record["budget"]["period"]
    if timeline is None:
        return rows + [("milestones_in_period", "timeline.csv", "not_checked", "timeline.csv not found.", "")]
    bad = []
    for row in timeline:
        try:
            start, end = int(row["start_month"]), int(row["end_month"])
        except ValueError:
            bad.append(f"{row['milestone']}: start_month and end_month must be whole project months")
            continue
        if start < 1 or end < start:
            bad.append(f"{row['milestone']}: months {start} to {end} are not a period")
        elif period != NOT_STATED and end > period["months"]:
            bad.append(f"{row['milestone']} ends in month {end}, after the {num(period['months'])}-month period")
    if bad:
        state, detail = "fail", "; ".join(bad) + "."
    elif period == NOT_STATED:
        state, detail = NOT_STATED, "The call states no project period. The months of every milestone are well formed."
    else:
        state, detail = "pass", f"All {len(timeline)} milestones fall within months 1 to {num(period['months'])}."
    return rows + [("milestones_in_period", "timeline.csv", state, detail, "" if period == NOT_STATED else period.get("locator", ""))]


def rows_call_rules(record: dict) -> list:
    """What the call demands and no script can verify: listed so that it is not forgotten."""
    rows = []
    for key in RULE_KEYS:
        node = record[key]
        rows.append(("call_rule", key, NOT_STATED, "The call does not state this.", "") if node == NOT_STATED else
                    ("call_rule", key, "not_checked", f"{node['value']} (Not checked by the script.)", node.get("locator", "")))
    if record["attachments"] == NOT_STATED:
        rows.append(("call_rule", "attachments", NOT_STATED, "The call lists no attachments.", ""))
    for item in as_list(record["attachments"]):
        need = {True: "Required", False: "Optional"}.get(item.get("required"), "Requirement not stated")
        rows.append(("call_rule", f"attachment: {item['name']}", "not_checked",
                     f"{need}. The script does not look for attachments.", item.get("locator", "")))
    return rows


def finish(directory: Path, name: str, title: str, head: list, rows: list, tail: list, result: dict) -> int:
    counts = {state: sum(1 for row in rows if row[2] == state) for state in STATES}
    summary = (f"{len(rows)} checks: {counts['pass']} pass, {counts['fail']} fail, {counts['not_checked']} not checked, "
               f"{counts[NOT_STATED]} not stated in the call.")
    write(directory / name, [f"# {title}", "", *head, "", summary, "",
                             *table(("Check", "Subject", "State", "Detail", "Call"), rows), *tail])
    result = {"ok": counts["fail"] == 0, "counts": counts,
              "failed": [f"{row[0]}: {row[1]}" for row in rows if row[2] == "fail"],
              "not_checked": [f"{row[0]}: {row[1]}" for row in rows if row[2] == "not_checked"],
              **result, "report": str(directory / name)}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def cmd_check(args) -> int:
    directory = Path(args.dir)
    record_path, record = load_record(args)
    text = read_proposal(Path(args.proposal))
    lines, headings = outline(text)
    rows = [("record_verified", "requirements.json", *record_verified(directory, record_path), "")]
    section_rows, left_out, stray = rows_sections(record, lines, headings)
    rows += section_rows + [row_total(record, lines, args.pdf)]
    open_items = [(heading_at(headings, text[:m.start()].count("\n")), m.group(0)) for m in PLACEHOLDER.finditer(text)]
    if not open_items:
        rows.append(("no_open_placeholders", "proposal", "pass", "No placeholder is left in the proposal.", ""))
    else:
        rows.append(("no_open_placeholders", "proposal", "fail" if args.final else "not_checked",
                     f"{len(open_items)} open placeholder(s), listed below. "
                     + ("A final run fails on them." if args.final else "This is a draft run; a --final run fails on them."), ""))
    rows += rows_criteria(directory, record, headings) + rows_aims(directory, record) + rows_call_rules(record)
    tail = []
    if open_items:
        tail += ["", "## Open placeholders", "", *table(("Section", "Placeholder"), open_items)]
    if left_out:
        tail += ["", "Optional sections not in the proposal: " + "; ".join(left_out) + "."]
    if stray:
        tail += ["", "Headings that are not sections of the record: " + "; ".join(stray) + "."]
    tail += ["", "Budget arithmetic is in budget-check.md (the budget command). `not_checked` and `not_stated` are not passes."]
    head = [call_line(record), f"Proposal: {args.proposal} ({count(plain(text), 'words')} words, headings included). "
                               f"Run: {'final' if args.final else 'draft'}."]
    return finish(directory, "report.md", "Proposal check", head, rows, tail,
                  {"final": bool(args.final), "placeholders": len(open_items), "optional_sections_left_out": left_out,
                   "headings_not_in_record": stray})


def cmd_budget(args) -> int:
    directory = Path(args.dir)
    _, record = load_record(args)
    budget = record["budget"]
    cap = NOT_STATED if budget == NOT_STATED else budget["cap"]
    rules = NOT_STATED if budget == NOT_STATED else budget["rules"]
    currency = "" if budget == NOT_STATED or budget["currency"] == NOT_STATED else str(budget["currency"])
    lines, totals, bad = [], [], []
    for number, row in enumerate(read_csv(Path(args.budget), BUDGET_COLUMNS), 2):
        amount = parse_number(row["amount"])
        row = {**row, "line": row["line"] or f"row {number}", "amount": amount}
        if amount is None:
            bad.append(row["line"])
        else:
            (totals if is_total(row) else lines).append(row)
    sums = {"year": {}, "category": {}, "other": {}}
    for line in lines:
        keys = [("year", line["year"]), ("category", line["category"]), ("other", (line["category"], line["year"]))]
        for group, key in keys + [("other", aim) for aim in ids_of(line["aim"])]:
            sums[group][key] = sums[group].get(key, 0) + line["amount"]
    total = round(sum(line["amount"] for line in lines), 2)
    money = f"{num(total)} {currency}".strip()
    rows = [("amounts_numeric", "budget.csv", "fail" if bad else "pass",
             f"Not a number: the amount of {', '.join(bad)}." if bad
             else f"All amounts are numbers ({len(lines)} lines, {len(totals)} stated totals).", "")]
    products = wrong = 0
    for line in lines:
        quantity, unit_cost = parse_number(line.get("quantity", "")), parse_number(line.get("unit_cost", ""))
        if quantity is None or unit_cost is None:
            continue
        products += 1
        if abs(quantity * unit_cost - line["amount"]) > ROUNDING:
            wrong += 1
            rows.append(("quantity_x_unit_cost", line["line"], "fail", f"{num(quantity)} × {num(unit_cost)} = "
                         f"{num(quantity * unit_cost)}; the table says {num(line['amount'])}.", ""))
    if not products:
        rows.append(("quantity_x_unit_cost", "budget.csv", "not_checked", "No line gives both quantity and unit_cost.", ""))
    elif not wrong:
        rows.append(("quantity_x_unit_cost", "budget.csv", "pass",
                     f"All {products} lines with a quantity and a unit cost multiply to their amount.", ""))
    for stated in totals:
        expected = sums["year"].get(stated["year"], 0) if stated["year"] else total
        agrees = abs(expected - stated["amount"]) <= ROUNDING
        rows.append(("stated_total", f"{stated['line']} ({'year ' + stated['year'] if stated['year'] else 'all years'})",
                     "pass" if agrees else "fail", f"The lines add up to {num(expected)}; the table says {num(stated['amount'])}.", ""))
    if cap == NOT_STATED:
        rows.append(("total_against_cap", "budget.csv", NOT_STATED, f"The call states no budget cap. Total {money}.", ""))
    else:
        over = total > cap["value"]
        rows.append(("total_against_cap", "budget.csv", "fail" if over else "pass", f"Total {money}, "
                     f"{'over' if over else 'within'} the cap of {num(cap['value'])}.", cap.get("locator", "")))
    orphans = [line["line"] for line in lines if not ids_of(line["aim"])]
    rows.append(("lines_without_aim", "budget.csv", "fail" if orphans else "pass", f"No aim: {', '.join(orphans)}. Name the aim "
                 "the cost serves, or project." if orphans else "Every line names an aim, or project.", ""))
    if not args.proposal:
        rows.append(("amounts_in_text", "proposal", "not_checked", "No proposal was given (--proposal).", ""))
    else:
        text = read_proposal(Path(args.proposal))
        _, headings = outline(text)
        known = {line["amount"] for line in lines} | {parse_number(line.get("unit_cost", "")) for line in lines} | {total}
        known |= {value for group in sums.values() for value in group.values()}
        for node in [cap, *as_list(rules)]:
            known |= numbers_in(str(node.get("quote", ""))) | {node.get("value")} if isinstance(node, dict) else set()
        found = amounts_in_text(text, currency)
        strays = [f'{shown} (under "{heading_at(headings, text[:position].count(chr(10)))}")' for position, value, shown in found
                  if not any(isinstance(k, (int, float)) and abs(k - value) <= ROUNDING for k in known)]
        if not found:
            rows.append(("amounts_in_text", args.proposal, "not_checked", "No amount written with a currency symbol or the "
                         "record's currency was found in the text. Bare numbers are not read as amounts.", ""))
        else:
            rows.append(("amounts_in_text", args.proposal, "fail" if strays else "pass",
                         "Not a line or a sum of the table, nor a figure of the call: " + "; ".join(strays) + "." if strays
                         else f"All {len(found)} amounts in the text are lines or sums of the table, or figures of the call.", ""))
    if rules == NOT_STATED:
        rows.append(("budget_rule", "rules", NOT_STATED, "The call states no budget rules.", ""))
    for index, rule in enumerate(as_list(rules), 1):
        rows.append(("budget_rule", f"rule {index}", "not_checked", f"{rule['rule']} (Not checked by the script: read the "
                     "table against it.)", rule.get("locator", "")))
    tail = ["", "## Sums", "", "Added up from the amounts in the table. No rate, overhead or salary is computed.", ""]
    for group in ("year", "category"):
        tail += [*table((group.capitalize(), f"Amount {currency}".strip()),
                        [(key or "(none)", num(value)) for key, value in sorted(sums[group].items())]), ""]
    tail.append(f"Total: {money}")
    head = [call_line(record), f"Table: {args.budget} ({len(lines)} lines)."]
    return finish(directory, "budget-check.md", "Budget check", head, rows, tail,
                  {"lines": len(lines), "total": total, "currency": currency or NOT_STATED,
                   "cap": NOT_STATED if cap == NOT_STATED else cap["value"],
                   "by_year": {key: round(value, 2) for key, value in sorted(sums["year"].items())},
                   "by_category": {key: round(value, 2) for key, value in sorted(sums["category"].items())}})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a grant proposal against the text of the call it answers.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="grant", help="Folder with the record, the tables and the reports (default: grant)")
    common.add_argument("--requirements", help="The requirements record (default: <dir>/requirements.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("call", parents=[common], help="Check that every quote of the record is in the call text")
    p.add_argument("call", help="The call as text (.txt, .md, or text extracted from a PDF)")
    p = sub.add_parser("check", parents=[common], help="Check the proposal against the record and aims.json")
    p.add_argument("proposal", help="proposal.md, or a folder of section files")
    p.add_argument("--pdf", help="The rendered proposal, for the total page limit")
    p.add_argument("--final", action="store_true", help="Before submission: open placeholders fail")
    p = sub.add_parser("budget", parents=[common], help="Check the arithmetic of the budget table")
    p.add_argument("budget", help="budget.csv: line, category, year, amount, aim (optional quantity, unit_cost)")
    p.add_argument("--proposal", help="Compare the amounts written in this text with the table")
    args = parser.parse_args(argv)
    return {"call": cmd_call, "check": cmd_check, "budget": cmd_budget}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
