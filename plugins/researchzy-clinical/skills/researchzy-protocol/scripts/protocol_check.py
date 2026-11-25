#!/usr/bin/env python3
"""Check that a study protocol, its registry draft and its analysis plan say what one core record says.

  protocol_check.py check [--dir protocol]          every core item in every document that should state it
  protocol_check.py definitions [--dir protocol]    definitions.csv: quoted sources, justified ad hoc rows, cutoffs
  protocol_check.py amendments [--dir protocol]     amendments.csv: dated, with reasons; changes after data were seen

check reads core.json, locations.json and protocol.md, registry.md and sap.md in --dir (formats in
references/core-and-documents.md). For each item and each document it names, the quote that locations.json
gives must be in the document (quote_match.py: EXACT or INTERLEAVED) and must state the core value: the
number of a number item; the time points, role and key terms of an outcome; the wording of a text item.
Time points are normalised first: "12 weeks", "week 12", "12-week", "12周", "第12周" are one; days and
weeks convert, and so do months and years, but months equal weeks or days only under the time_rule the user
stated in core.json. A number whose entry names the file it was computed in is compared with that file.
States: consistent, inconsistent (missing or different), quote_not_found, not_checked (the document does not
exist). Lines that announce a primary outcome no quote covers are listed as leads, which never fail.
Writes check.md, with the quotes of the documents side by side.

definitions reads definitions.csv and the saved texts in sources/ (references/definitions.md) and writes
definitions-check.md. amendments reads amendments.csv (references/forms-and-amendments.md) and writes
amendments-check.md.

Each command prints a JSON summary. Exit code 0 when nothing failed; 1 when an item is inconsistent, a quote
is not found, a recorded number differs from core.json, or a definition or amendment row fails; 2 when an
input cannot be read or is not in the documented format. Standard library only, no network.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_match import match_quality, normalize, tokens  # noqa: E402

DOCS = ("protocol", "registry", "sap")
STATES = ("consistent", "inconsistent", "quote_not_found", "not_checked")
ROLES = ("primary", "secondary", "exploratory", "other")
DEFINITION_ROLES = ("exposure", "intervention", "outcome", "covariate", "eligibility", "other")
DEFINITION_COLUMNS = ("variable", "role", "definition", "cutoff", "unit", "source_id", "quote", "locator", "ad_hoc",
                      "justification")
AMENDMENT_COLUMNS = ("date", "item", "before", "after", "reason", "impact", "prespecified", "data_seen")
PASSING = ("EXACT", "INTERLEAVED")
MIN_QUOTE = 3           # tokens (a Han character is one): a shorter quote is found almost anywhere
MIN_SOURCE_QUOTE = 5    # a definition rests on a longer passage
LEAD_CAP = 10           # leads listed per document
PLACEHOLDER = re.compile(r"\[\s*(?:Evidence|Citation|Author input) needed\b[^\]]*\]", re.I)
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
ROLE_WORDS = {role: re.compile(rf"\b{role}\s+(?:outcome|endpoint|end[- ]point|efficacy|measure)|{zh}(?:结局|终点|疗效|观察|评价|指标)",
                               re.I) for role, zh in (("primary", "主要"), ("secondary", "次要"), ("exploratory", "探索性"))}
WORDS = {w: n for n, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
ZH = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
NUM = r"\d+(?:\.\d+)?|[一二两三四五六七八九十]{1,3}|" + "|".join(sorted(WORDS, key=len, reverse=True))
SEP = r"\s*(?:,|，|、|&|\band\b|\bor\b|\bto\b|和|及|与|或|至|到|-|–|—)\s*(?:第\s*)?"
UNIT = r"(?P<d>days?|天)|(?P<w>weeks?|wks?|周|週|星期)|(?P<m>months?|mos?|个月|個月)|(?P<y>years?|yrs?|年)"
AFTER = re.compile(rf"(?<![\dA-Za-z.])(?P<n>(?:{NUM})(?:{SEP}(?:{NUM}))*)\s*-?\s*(?:{UNIT})(?![A-Za-z])", re.I)
BEFORE = re.compile(r"(?<![A-Za-z])(?:(?P<d>day)|(?P<w>week|wk)|(?P<m>month)|(?P<y>year))s?\s*-?\s*"
                    r"(?P<n>\d+(?:\.\d+)?(?:\s*(?:,|&|\band\b|\bor\b|-|–)\s*\d+(?:\.\d+)?)*)(?![\d.])", re.I)
FACTOR = {"d": ("d", 1), "w": ("d", 7), "m": ("m", 1), "y": ("m", 12)}
UNIT_NAME = {"d": "day", "w": "week", "m": "month", "y": "year"}
NUMBER = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?![\d,])|(?<![\d.])\d+(?:\.\d+)?")
OP_BEFORE = (r"(?:[≥≧⩾>≤≦⩽<]=?|\bat least|\bat most|\bmore than|\bgreater than|\bless than|\bfewer than|\babove|\bbelow|"
             r"不少于|不低于|不超过|至少|大于|小于|超过|高于|低于|达到)")
OP_AFTER = r"(?:or more|or greater|or higher|or above|or less|or lower|or below|及以上|以上|及以下|以下)"


def fail(message: str):
    print(f"protocol_check: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except OSError:
        fail(f"no such file: {path}")
    except UnicodeDecodeError:
        fail(f"{path} is not UTF-8 text.")


def read_json(path: Path):
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")


def read_csv(path: Path, required: tuple) -> list:
    """Rows as dicts with lower-case column names; the delimiter may be , ; or a tab."""
    lines = read_text(path).splitlines()
    reader = csv.DictReader(lines, delimiter=max(",;\t", key=(lines[0] if lines else "").count))
    columns = {name: (name or "").strip().lower() for name in reader.fieldnames or []}
    missing = [name for name in required if name not in columns.values()]
    if missing:
        fail(f"{path} lacks the column(s) {', '.join(missing)}. It needs: {', '.join(required)}.")
    rows = [{columns[k]: v.strip() if isinstance(v, str) else "" for k, v in row.items() if k in columns} for row in reader]
    return [row for row in rows if any(row.values())]


def table(header: tuple, rows: list) -> list:
    cell = lambda value: re.sub(r"\s+", " ", str(value)).replace("|", "/").strip()  # noqa: E731
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)]


def write(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def at(base: Path, name: str) -> Path:
    """A path as written in a record: from the working directory, else from --dir."""
    path = Path(name)
    return path if path.is_absolute() or path.exists() else base / path


def num(value: float) -> str:
    return f"{value:,.6g}" if abs(value) >= 1000 else f"{value:g}"


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def passes(quote: str, text: str) -> bool:
    return match_quality(quote, text)["grade"] in PASSING


def value_of(token: str):
    """12 · twelve · 十二 as a number; None when the token is none of these."""
    token = token.strip().lower()
    if not token:
        return None
    if token[0].isdigit():
        return float(token)
    if token in WORDS:
        return float(WORDS[token])
    tens, ten, ones = token.partition("十")
    if not ten:
        return float(ZH[token]) if token in ZH else None
    if (tens and tens not in ZH) or (ones and ones not in ZH):
        return None
    return float((ZH[tens] if tens else 1) * 10 + (ZH[ones] if ones else 0))


def timepoints(text: str, month: float | None = None) -> dict:
    """{(kind, amount): label} for every time point in text. Days and weeks are counted in days ("d"), months
    and years in months ("m"); with a month rule (days per month), months are counted in days too."""
    text, found = unicodedata.normalize("NFKC", text), {}

    def take(match):
        unit = next(k for k in "dwmy" if match.group(k))
        for token in re.split(SEP, match.group("n"), flags=re.I):
            amount = value_of(token)
            if amount is None or amount >= 1000:      # a year such as 2026, not a time point
                continue
            kind, value = FACTOR[unit][0], amount * FACTOR[unit][1]
            if kind == "m" and month:
                kind, value = "d", value * month
            found.setdefault((kind, round(value, 6)), f"{amount:g} {UNIT_NAME[unit]}" + "s" * (amount != 1))
        return " " * len(match.group(0))

    BEFORE.sub(take, AFTER.sub(take, text))
    return found


def numbers_in(text: str) -> list:
    """Numbers as written, including those that touch Han characters (随机120例) and 1,200."""
    return [float(m.replace(",", "")) for m in NUMBER.findall(unicodedata.normalize("NFKC", text))]


def squash(text: str) -> str:
    return "".join(normalize(text).split())


def items(core: dict) -> list:
    return [(kind, entry) for kind in ("outcomes", "numbers", "texts") for entry in core.get(kind) or []]


def core_errors(core: dict) -> list:
    """Everything that keeps core.json from being used (references/core-and-documents.md)."""
    errors = [f"{kind} must be a list of objects" for kind in ("outcomes", "numbers", "texts")
              if not isinstance(core.get(kind, []), list) or not all(isinstance(e, dict) for e in core.get(kind) or [])]
    if errors:
        return errors
    ids = [str(entry.get("id") or "").strip() for _, entry in items(core)]
    errors += [f"ids repeat: {', '.join(sorted({i for i in ids if ids.count(i) > 1}))}"] if len(set(ids)) < len(ids) else []
    for kind, entry in items(core):
        where, docs = f"{kind}[{entry.get('id') or '?'}]", entry.get("documents", list(DOCS))
        if not str(entry.get("id") or "").strip():
            errors.append(f"{kind}: every entry needs an id")
        if not (isinstance(docs, list) and docs and set(docs) <= set(DOCS)):
            errors.append(f"{where}.documents must list some of {', '.join(DOCS)}")
        if kind == "outcomes":
            points, terms = entry.get("timepoints", []), entry.get("key_terms", [])
            if entry.get("role") not in ROLES:
                errors.append(f"{where}.role must be one of {', '.join(ROLES)}")
            if not str(entry.get("measure") or "").strip():
                errors.append(f"{where}.measure is missing")
            if not isinstance(points, list) or any(not isinstance(p, str) or len(timepoints(p)) != 1 for p in points):
                errors.append(f'{where}.timepoints must be a list of single time points such as "12 weeks"')
            if not isinstance(terms, list) or not all(isinstance(t, str) and t.strip() for t in terms):
                errors.append(f"{where}.key_terms must be a list of words")
        elif kind == "numbers":
            source = entry.get("from")
            if not is_number(entry.get("value")):
                errors.append(f"{where}.value must be a number")
            if not (isinstance(source, dict) and ((source.get("file") and source.get("key")) or (
                    source.get("stated_by") == "user" and str(source.get("note") or "").strip()))):
                errors.append(f'{where}.from must name the file and key it was computed in, or be {{"stated_by": "user", '
                              f'"note": "…"}}')
            elif "factor" in source and not is_number(source["factor"]):
                errors.append(f"{where}.from.factor must be a number")
        elif not str(entry.get("text") or "").strip():
            errors.append(f"{where}.text is missing")
    rule = core.get("time_rule")
    if rule is not None:
        days = timepoints(str(rule.get("month", ""))) if isinstance(rule, dict) else {}
        if len(days) != 1 or next(iter(days))[0] != "d" or not str(rule.get("source") or "").strip():
            errors.append('time_rule must be {"month": "4 weeks" (or days), "source": "who stated it, and when"}')
    return errors


def outline(text: str) -> tuple:
    """(lines, the headings that enclose each line, innermost first)."""
    lines, chain, chains = text.splitlines(), [], []
    for line in lines:
        match = HEADING.match(line)
        if match:
            chain = [h for h in chain if h[0] < len(match.group(1))] + [(len(match.group(1)), match.group(2))]
        chains.append([h[1] for h in reversed(chain)])
    return lines, chains


def context(quote: str, lines: list, chains: list) -> tuple:
    """(the line that holds the quote, or "", and its headings): where to read the role the document gives."""
    for number, line in enumerate(lines):
        if passes(quote, line):
            return line, chains[number]
    start = 0
    for number in range(1, len(lines) + 1):
        if number == len(lines) or HEADING.match(lines[number]):
            if passes(quote, "\n".join(lines[start:number])):
                return "", chains[start]
            start = number
    return "", []


def stated_role(*texts):
    """The one role a text names, trying the quote, its line and its headings in turn."""
    for text in texts:
        found = {role for role, pattern in ROLE_WORDS.items() if pattern.search(text)}
        if len(found) == 1:
            return found.pop()
    return None


def has_term(term: str, quote: str) -> bool:
    return any(squash(alt) and squash(alt) in squash(quote) for alt in term.split("|"))


def labels(points: dict) -> str:
    return ", ".join(points[key] for key in sorted(points)) or "none"


def compare(kind: str, entry: dict, quote: str, lines: list, chains: list, month) -> tuple:
    """(problems, what was confirmed) for one quote against its core entry."""
    if kind == "numbers":
        found, value = numbers_in(quote), float(entry["value"])
        if any(abs(n - value) < 1e-9 * max(1.0, abs(value)) for n in found):
            return [], f"states {num(value)}"
        said = ", ".join(num(n) for n in found[:5]) if found else "no number"
        return [f"number: the quote states {said}; core.json: {num(value)}"], ""
    if kind == "texts":
        if passes(entry["text"], quote):
            return [], "contains the core wording"
        return ["wording: the quote does not contain the text of core.json"], ""
    problems, want = [], {k: v for p in entry.get("timepoints", []) for k, v in timepoints(p, month).items()}
    missing = [t for t in entry.get("key_terms", []) if not has_term(t, quote)]
    if missing:
        problems.append(f"measure: the quote lacks {', '.join(missing)}")
    line, chain = context(quote, lines, chains)
    role = stated_role(quote, line, *chain)
    if entry["role"] in ROLE_WORDS and role and role != entry["role"]:
        problems.append(f"role: the document gives it as {role}; core.json: {entry['role']}")
    have = timepoints(quote, month)
    if want and set(have) != set(want):
        problems.append(f"time point: the quote states {labels(have)}; core.json: {labels(want)}" + (
            ". Months equal weeks or days only under a time_rule the user states in core.json"
            if not month and {k[0] for k in have} | {k[0] for k in want} == {"d", "m"} else ""))
    return problems, f"time points {labels(have)}" + (f", given as {role}" if role else "")


def judge(kind: str, entry: dict, doc: str, parsed, where, month) -> tuple:
    """(state, detail, quote, locator) of one item in one document."""
    if parsed is None:
        return "not_checked", f"{doc}.md not found", "", ""
    quote = str((where or {}).get("quote") or "").strip()
    locator = str((where or {}).get("locator") or "").strip()
    if not quote:
        return "inconsistent", "missing: locations.json gives no quote from this document", "", ""
    if len(tokens(quote)) < MIN_QUOTE:
        return "quote_not_found", f"{len(tokens(quote))} word(s): quote at least {MIN_QUOTE}", quote, locator
    grade = match_quality(quote, parsed[0])["grade"]
    if grade not in PASSING:
        return "quote_not_found", f"not in {doc}.md ({grade}): copy the passage again from the document", quote, locator
    problems, confirmed = compare(kind, entry, quote, *parsed[1:], month)
    return ("inconsistent", "; ".join(problems), quote, locator) if problems else ("consistent", confirmed, quote, locator)


def dig(data, key: str):
    for part in key.split("."):
        if isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        elif isinstance(data, dict) and part in data:
            data = data[part]
        else:
            return None
    return data if is_number(data) else None


def source_state(entry: dict, base: Path) -> tuple:
    """(state, detail) of a number against the file it was computed in."""
    source = entry["from"]
    if source.get("stated_by") == "user":
        return "user", f"Given by the user, not computed here: {source['note']}"
    path = at(base, source["file"])
    if not path.is_file():
        return "not_checked", f"{source['file']} not found: run the calculation that writes it"
    try:
        found = dig(json.loads(path.read_text(encoding="utf-8-sig")), source["key"])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "inconsistent", f"{source['file']} cannot be read as JSON"
    if found is None:
        return "inconsistent", f"{source['file']} has no number at {source['key']}"
    found *= source.get("factor", 1)
    same = abs(found - entry["value"]) < 1e-9 * max(1.0, abs(found))
    return ("consistent" if same else "inconsistent"), f"{source['file']} {source['key']} = {num(found)}" + (
        "" if same else f"; core.json: {num(entry['value'])}. Copy the recorded number, never retype it")


def describe(kind: str, entry: dict) -> str:
    if kind == "outcomes":
        return f"{entry['role']} outcome: {entry['measure']}, " + (", ".join(entry.get("timepoints", [])) or "no time point")
    return f"{entry.get('label') or entry['id']}: " + (num(entry["value"]) if kind == "numbers" else entry["text"])


def cmd_check(args) -> int:
    base = Path(args.dir)
    core_path, locations_path = base / "core.json", base / "locations.json"
    for path, what in ((core_path, "the core record"), (locations_path, "the quotes of each item")):
        if not path.is_file():
            fail(f"no {path}: write {what} first (references/core-and-documents.md).")
    core = read_json(core_path)
    errors = core_errors(core) if isinstance(core, dict) else ["the file must hold a JSON object"]
    if errors:
        fail(f"{core_path} is not in the format of references/core-and-documents.md:\n  - " + "\n  - ".join(errors))
    known, locations = {entry["id"] for _, entry in items(core)}, read_json(locations_path)
    if not isinstance(locations, dict) or not all(isinstance(v, dict) and set(v) <= set(DOCS) and all(
            isinstance(x, dict) for x in v.values()) for v in locations.values()):
        fail(f'{locations_path} must map each item id to {{"protocol"|"registry"|"sap": {{"quote": …, "locator": …}}}}.')
    if set(locations) - known:
        fail(f"{locations_path} names {', '.join(sorted(set(locations) - known))}, which core.json does not have.")
    rule = core.get("time_rule")
    month = next(iter(timepoints(rule["month"])))[1] if rule else None
    texts = {doc: read_text(base / f"{doc}.md") if (base / f"{doc}.md").is_file() else None for doc in DOCS}
    parsed = {doc: None if text is None else (text, *outline(text)) for doc, text in texts.items()}
    cells, sources = [], []
    for kind, entry in items(core):
        for doc in entry.get("documents", DOCS):
            state, detail, quote, locator = judge(kind, entry, doc, parsed[doc], locations.get(entry["id"], {}).get(doc), month)
            cells.append({"item": entry["id"], "document": doc, "state": state, "detail": detail, "quote": quote,
                          "locator": locator})
        if kind == "numbers":
            sources.append((entry["id"], num(entry["value"]), entry["from"].get("file") or "user", *source_state(entry, base)))
    leads, placeholders = [], []
    for doc, text in texts.items():
        if text is None:
            continue
        mine = [c["quote"] for c in cells if c["document"] == doc and c["quote"] and c["state"] != "quote_not_found"
                and any(e["id"] == c["item"] and e.get("role") == "primary" for k, e in items(core) if k == "outcomes")]
        found = [(n, " ".join(re.sub(r"[|*_`>#]", " ", line).split())[:160]) for n, line in enumerate(text.splitlines(), 1)
                 if not HEADING.match(line) and ROLE_WORDS["primary"].search(line)
                 and not any(passes(q, line) or passes(line, q) for q in mine)]
        leads += [(f"{doc}.md", n, line) for n, line in found[:LEAD_CAP]]
        placeholders += [(f"{doc}.md", m.group(0)) for m in PLACEHOLDER.finditer(text)]
    counts = {s: sum(c["state"] == s for c in cells) for s in STATES}
    bad_sources = [f"{s[0]}: {s[4]}" for s in sources if s[3] == "inconsistent"]
    ok = not (counts["inconsistent"] or counts["quote_not_found"] or bad_sources)
    state_of = {(c["item"], c["document"]): c["state"] for c in cells}
    lines = ["# Protocol consistency check", "", f"Core record: {core_path} (SHA-256 "
             f"{hashlib.sha256(core_path.read_bytes()).hexdigest()[:12]}). " + (
                 f"Time rule: 1 month = {rule['month']} ({rule['source']})." if rule else
                 "No time rule: months never equal weeks or days."),
             "Documents: " + ", ".join(f"{d}.md" + ("" if texts[d] is not None else " (not found)") for d in DOCS) + ".", "",
             f"{len(cells)} checks: " + ", ".join(f"{counts[s]} {s}" for s in STATES) + f". Result: {'ok' if ok else 'failed'}.",
             "", *table(("Item", *(f"{d}.md" for d in DOCS)), [(e["id"], *(state_of.get((e["id"], d), "-") for d in DOCS))
                                                                for _, e in items(core)])]
    problems = [(c["item"], f"{c['document']}.md", c["state"], c["detail"]) for c in cells if c["state"] != "consistent"]
    lines += ["", "## Not consistent", "", *(table(("Item", "Document", "State", "Detail"), problems) if problems else ["None."])]
    lines += ["", "## The documents side by side"]
    for kind, entry in items(core):
        mine = [c for c in cells if c["item"] == entry["id"]]
        lines += ["", f"### {entry['id']}: {describe(kind, entry)}", "",
                  *table(("Document", "Locator", "Quote", "State"), [(f"{c['document']}.md", c["locator"] or "-",
                         f"“{c['quote']}”" if c["quote"] else "-", c["state"]) for c in mine])]
    lines += ["", "## Numbers and where they were computed", "",
              *(table(("Item", "Value", "From", "State", "Detail"), sources) if sources else ["No number items."])]
    lines += ["", "## Leads: lines that announce a primary outcome no quote covers", "",
              "Not failures. Read each: a second primary outcome, or a sentence about the declared one.", "",
              *([f"- {doc}, line {n}: {line}" for doc, n, line in leads] or ["None."])]
    lines += ["", "## Open placeholders", "", *([f"- {doc}: {p}" for doc, p in placeholders] or ["None."])]
    write(base / "check.md", lines)
    result = {"ok": ok, "counts": counts,
              "inconsistent": [f"{c['item']} / {c['document']}: {c['detail']}" for c in cells if c["state"] == "inconsistent"],
              "quote_not_found": [f"{c['item']} / {c['document']}" for c in cells if c["state"] == "quote_not_found"],
              "not_checked": [f"{c['item']} / {c['document']}: {c['detail']}" for c in cells if c["state"] == "not_checked"],
              "sources_inconsistent": bad_sources, "sources_not_checked": [s[0] for s in sources if s[3] == "not_checked"],
              "given_by_user": [s[0] for s in sources if s[3] == "user"], "leads": len(leads),
              "placeholders": len(placeholders), "report": str(base / "check.md")}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def load_source(base: Path, sid: str, cache: dict):
    """The saved text of a source, or a message saying why it cannot be used."""
    if sid not in cache:
        path = next((p for p in (base / "sources" / f"{sid}.txt", base / "sources" / f"{sid}.md") if p.is_file()), None)
        if path is None:
            cache[sid] = f"sources/{sid}.txt not found: save the source's text there, or write [Citation needed: …]"
        else:
            text = read_text(path)
            head = text.split("\n\n", 1)[0]
            source, read = re.search(r"^Source:\s*(\S.*)$", head, re.M), re.search(r"^Read:\s*(\d{4}-\d{2}-\d{2})", head, re.M)
            cache[sid] = {"file": f"sources/{path.name}", "text": text, "source": source.group(1) if source else "",
                          "read": read.group(1) if read else "", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            if not (source and read):
                cache[sid] = f"sources/{path.name} must begin with a Source: line and a Read: YYYY-MM-DD line"
    return cache[sid]


def definition_state(row: dict, base: Path, cache: dict) -> tuple:
    problems = [] if row["variable"] else ["no variable name"]
    problems += [] if row["role"].lower() in DEFINITION_ROLES else [f"role must be one of {', '.join(DEFINITION_ROLES)}"]
    problems += [] if row["definition"] else ["no definition"]
    ad_hoc = row["ad_hoc"].lower()
    problems += [] if ad_hoc in ("yes", "no", "") else ["ad_hoc must be yes or no"]
    if problems:
        return "fail", "; ".join(problems)
    if ad_hoc == "yes":
        reason = row["justification"]
        if reason and not PLACEHOLDER.fullmatch(reason):
            return "ok", f"Ad hoc: {reason}"
        return "fail", "An ad hoc definition needs its justification"
    sid = "" if PLACEHOLDER.search(row["source_id"]) else row["source_id"]
    if not sid:
        open_items = [m.group(0) for k in ("definition", "source_id", "quote") for m in PLACEHOLDER.finditer(row[k])]
        if open_items:
            return "open", "No source yet: " + "; ".join(open_items)
        return "fail", "No source, not ad hoc, and no [Citation needed: …]. Never write a definition from memory"
    source = load_source(base, sid, cache)
    if isinstance(source, str):
        return "fail", source
    if len(tokens(row["quote"])) < MIN_SOURCE_QUOTE:
        return "fail", f"{len(tokens(row['quote']))} word(s) of quote: copy at least {MIN_SOURCE_QUOTE} from {source['file']}"
    if not row["locator"]:
        return "fail", "No locator: give the page, section or table of the source"
    grade = match_quality(row["quote"], source["text"])["grade"]
    if grade in PASSING:
        return "ok", f"{grade} in {source['file']}, {row['locator']}"
    return "fail", f"The quote is not in {source['file']} ({grade}): copy it again; never edit the saved source"


def thresholds(line: str, unit: str) -> set:
    """Numbers that a comparison word or sign ties to the unit in one line (≥ 20%, 20%及以上, at least 20%)."""
    after_unit = rf"\s*{re.escape(unit)}" if unit else ""
    pattern = rf"{OP_BEFORE}\s*(\d+(?:\.\d+)?){after_unit}|(\d+(?:\.\d+)?){after_unit}\s*{OP_AFTER}"
    return {float(a or b) for a, b in re.findall(pattern, unicodedata.normalize("NFKC", line), re.I)}


def cutoff_rows(row: dict, docs: dict) -> list:
    """Each document that names the variable next to a threshold must give the table's cutoff."""
    want, rows = set(numbers_in(row["cutoff"])), []
    for doc, text in docs.items():
        if text is None:
            rows.append((row["variable"], f"cutoff in {doc}.md", "not_checked", f"{doc}.md not found"))
            continue
        seen = [(n, thresholds(line, row["unit"]), line) for n, line in enumerate(text.splitlines(), 1)
                if any(squash(name) and squash(name) in squash(line) for name in row["variable"].split("|"))]
        seen = [(n, found, line) for n, found, line in seen if found]
        bad = [f"line {n} gives {', '.join(num(x) for x in sorted(found))}: “{line.strip()[:100]}”" for n, found, line in seen
               if not want <= found]
        if bad:
            rows.append((row["variable"], f"cutoff in {doc}.md", "fail", f"The table gives {row['cutoff']} {row['unit']}; "
                         + "; ".join(bad[:3])))
        elif seen:
            rows.append((row["variable"], f"cutoff in {doc}.md", "ok", f"Line(s) {', '.join(str(s[0]) for s in seen[:5])}"))
        else:
            rows.append((row["variable"], f"cutoff in {doc}.md", "not_checked",
                         f"No line names “{row['variable']}” next to a threshold in {row['unit'] or 'any unit'}"))
    return rows


def cmd_definitions(args) -> int:
    base = Path(args.dir)
    rows = read_csv(base / "definitions.csv", DEFINITION_COLUMNS)
    docs = {doc: read_text(base / f"{doc}.md") if (base / f"{doc}.md").is_file() else None for doc in ("protocol", "sap")}
    cache, out = {}, []
    for number, row in enumerate(rows, 2):
        out.append((row["variable"] or f"row {number}", row["role"] or "-", *definition_state(row, base, cache)))
        if row["cutoff"] and numbers_in(row["cutoff"]):
            out += cutoff_rows(row, docs)
    counts = {s: sum(r[2] == s for r in out) for s in ("ok", "fail", "open", "not_checked")}
    used = [(sid, s["file"], s["source"], s["read"], s["sha256"][:12]) for sid, s in cache.items() if isinstance(s, dict)]
    write(base / "definitions-check.md", ["# Definitions check", "", f"{len(rows)} definitions; {len(out)} rows: " + ", ".join(
        f"{n} {s}" for s, n in counts.items()) + ". `open` rows wait for a source; they are not passes.", "",
        *table(("Variable", "Check", "State", "Detail"), out), "", "## Sources", "",
        *(table(("Id", "File", "Source", "Read", "SHA-256"), used) if used else ["No saved source was used."])])
    result = {"ok": counts["fail"] == 0, "counts": counts, "failed": [f"{r[0]}: {r[3]}" for r in out if r[2] == "fail"],
              "open": [r[0] for r in out if r[2] == "open"], "report": str(base / "definitions-check.md")}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def valid_date(text: str) -> bool:
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text)) and bool(date.fromisoformat(text))
    except ValueError:
        return False


def cmd_amendments(args) -> int:
    base = Path(args.dir)
    rows, out, after = read_csv(base / "amendments.csv", AMENDMENT_COLUMNS), [], []
    for number, row in enumerate(rows, 1):
        problems = [] if valid_date(row["date"]) else ["date must be YYYY-MM-DD"]
        problems += [f"{k} is empty" for k in ("before", "after") if not row[k]]
        problems += [] if row["reason"] and not PLACEHOLDER.fullmatch(row["reason"]) else ["no reason"]
        problems += [] if row["prespecified"].lower() in ("yes", "no") else ["prespecified must be yes or no"]
        seen = row["data_seen"].lower()
        if seen not in ("yes", "no", "unknown"):
            problems.append("data_seen must be yes, no or unknown")
        elif seen != "no":
            after.append(f"{row['date']}, {row['item'] or 'no item'}: {row['before']} → {row['after']}. Reason: {row['reason']}"
                         + (" (whether data had been seen is not known: report it as seen)" if seen == "unknown" else ""))
        out.append((number, row["date"], row["item"] or "-", "fail" if problems else "ok", "; ".join(problems) or
                    f"{row['before']} → {row['after']}"))
    failed = [f"amendment {r[0]}: {r[4]}" for r in out if r[3] == "fail"]
    write(base / "amendments-check.md", ["# Amendment log check", "", f"{len(out)} amendments, {len(failed)} failing.", "",
                                         *table(("#", "Date", "Item", "State", "Detail"), out), "",
                                         "## Changes made after data were seen, or not known", "",
                                         *([f"- {a}" for a in after] or ["None."])])
    result = {"ok": not failed, "amendments": len(out), "failed": failed, "after_data_seen": len(after),
              "report": str(base / "amendments-check.md")}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a protocol, registry draft and analysis plan against core.json.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, about in (("check", "Every core item in every document, with time points normalised; writes check.md"),
                        ("definitions", "definitions.csv against the saved sources and the documents' cutoffs"),
                        ("amendments", "amendments.csv: dates, reasons, changes after data were seen")):
        sub.add_parser(name, help=about).add_argument("--dir", default="protocol", help="The folder (default: protocol)")
    args = parser.parse_args(argv)
    return {"check": cmd_check, "definitions": cmd_definitions, "amendments": cmd_amendments}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
