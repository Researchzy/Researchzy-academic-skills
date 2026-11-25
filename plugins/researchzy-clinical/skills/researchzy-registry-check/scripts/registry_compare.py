#!/usr/bin/env python3
"""Compare a trial report with its ClinicalTrials.gov record, and list what a search of the registry found.

The agent fetches from the registry's public API (version 2) and saves every response unchanged; this script
reads the saved JSON and never goes online.

  registry_compare.py search  [--dir registry-check]                   search-log.json and its pages
  registry_compare.py compare [--dir registry-check] [--earlier FILE]  items.json, the paper, the record

search   Each search with its parameters, date, the total the registry reported and the SHA-256 of every saved
         page; then one row per trial in the pages, whatever its status, with the model's relevance call shown
         as the model's. Writes search.md and candidates.csv.
compare  First whether the record is the paper's trial (title, condition, intervention, sponsor): when title,
         condition and intervention all disagree, or none is shown to agree, it stops before any item. Then each
         item is consistent, inconsistent with its types (role, timepoint, measure, added, omitted, value, timing)
         or not_checked with the reason. The record side is read from its field path, never typed; the paper side
         is a quote graded by quote_match.py. Time points and numbers are normalised first: "week 12", "12 weeks",
         "12-week" and "第12周" are one time point; "3 months" and "12 weeks" are not. Also the primary outcome as
         registered and as reported, registration timing from studyFirstSubmitDate against startDateStruct and its
         type, the version read, and with --earlier the outcomes against an earlier version in the same JSON
         shape. Writes compare.md (both texts side by side) and compare.json.

Paths inside the JSON files are read from --dir, then from the working directory; the formats are in
references/matching-and-items.md and references/prior-trial-search.md. Each command prints a JSON summary. Exit
code 0 when the report was written and nothing needs correcting. 1 when (search) the last saved page of a search
still has a nextPageToken, or a relevance call names a trial in no saved page; (compare) the record is not shown
to be the paper's trial, a quote is not in the paper (an item's as one passage) or too short, a value or date is not in its quote, a field
path is not in the record, or an inconsistent outcome does not say whether the paper states the change. 2 when
an input cannot be read or is not in the format. Standard library only, no network.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_match import match_quality, tokens  # noqa: E402

KINDS = ("outcome", "enrollment", "date", "registration_claim", "intervention", "other")
ROLES = {"primaryOutcomes": "primary", "secondaryOutcomes": "secondary", "otherOutcomes": "other"}
CHOICES = {"outcome": ("role", tuple(ROLES.values())), "enrollment": ("basis", ("planned", "actual")),
           "registration_claim": ("claim", ("prospective", "retrospective"))}
SAYS = {"primary": ("primary", "main", "主要"), "prospective": ("prospective", "前瞻"),
        "retrospective": ("retrospective", "回顾", "回顧")}     # a quote for these should contain one of the words
CALLS = ("similar", "partial", "unrelated")
IDENTITY = ("title", "condition", "intervention", "sponsor")
ENROLMENT = "protocolSection.designModule.enrollmentInfo"
PASSING = ("EXACT", "INTERLEAVED")
MIN_QUOTE_TOKENS = 4     # a shorter passage occurs in almost any paper
MIN_SHARE = 0.5          # convention: share of the paper's content words that must recur in the record's text
DATE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")
PATH = re.compile(r"[A-Za-z]\w*(?:\.[A-Za-z]\w*|\[\d+\])*")
PAGE_MARK = re.compile(r"^[ \t]*(?:\[\[page (\d+)\]\]|=+ PAGE (\d+) =+)[ \t]*$", re.M | re.I)
CJK = "぀-ヿ㐀-䶿一-鿿豈-﫿가-힯"
SMALL = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
WORD_NUMBER = rf"(?:{'|'.join(TENS)})(?:-(?:{'|'.join(SMALL[1:10])}))?|" + "|".join(sorted(SMALL, key=len, reverse=True))
NUMBER = rf"\d+(?:\.\d+)?|{WORD_NUMBER}"
SERIES = rf"(?<![a-z0-9.\-])(?:{NUMBER})(?:\s*(?:,|、|and|or|to|&|-|–|和|及|或|至)\s*(?:{NUMBER}))*"
UNITS = (("min", 1, r"minutes?|mins?|分钟|分鐘"), ("h", 1, r"hours?|hrs?|h|小时|小時"), ("d", 1, r"days?|d|天"),
         ("d", 7, r"weeks?|wks?|周|週|星期"), ("mo", 1, r"months?|mos?|mths?|个月|個月"), ("mo", 12, r"years?|yrs?|年"))
AFTER = re.compile(rf"(?P<n>{SERIES})\s*-?\s*(?P<u>{'|'.join(u for _, _, u in UNITS)})(?:(?<=[a-z])(?![a-z])|(?<![a-z]))")
BEFORE = re.compile(rf"(?<!\d)(?<!\d\s)(?<!\d-)(?<![a-z])(?P<u>weeks?|wks?|days?|months?|years?|hours?)\s*(?P<n>{SERIES})")
MONTHS = "january february march april may june july august september october november december".split()
MONTH = rf"({'|'.join(MONTHS)}|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)\.?"
STOP = frozenset("""
a an the and or nor of in on at to for with without by from as per into via than then that this these those its it their
there was were is are be been being has have had do does did which who whom whose what when where how all any each both
other such versus vs compared comparison against between among within during after before since until up study studie
trial randomised randomized controlled control pilot phase multicentre multicenter blind blinded double single open label
patient participant people person subject adult individual group arm cohort primary secondary main outcome endpoint
measure measured measurement assessed assessment change score scale total mean value number proportion rate level effect
efficacy effectiveness evaluate evaluation evaluating investigate impact baseline week month day year hour minute time
point frame follow""".split())


def die(message: str):
    print(f"registry_compare: {message}", file=sys.stderr)
    raise SystemExit(2)


def load(path: Path):
    if not path.is_file():
        die(f"{path} does not exist.")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        die(f"{path} is not valid JSON: {exc}")


def txt(value) -> str:
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


def num(value) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def row(*cells) -> str:
    return "| " + " | ".join(re.sub(r"\s+", " ", str(c)).replace("|", "/") for c in cells) + " |"


def label(state: str, types: list) -> str:
    return f"{state} ({', '.join(types)})" if types else state


def norm(text) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).casefold()


def norm_id(text) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or ""))).upper()


# ---------------------------------------------------------------------------------------------
# Numbers, time points, dates and words in English or Chinese prose


def to_number(text: str) -> float:
    if text[0].isdigit():
        return float(text)
    tens, _, unit = text.partition("-")
    return float(TENS[tens] + (SMALL.index(unit) if unit else 0)) if tens in TENS else float(SMALL.index(text))


def timepoints(text) -> set:
    """Time points as (unit, value). Weeks become days and years months, so "1 year" is "12 months"."""
    t, found = norm(text), set()
    for match in [*AFTER.finditer(t), *BEFORE.finditer(t)]:
        unit, factor = next((u, f) for u, f, pattern in UNITS if re.fullmatch(pattern, match["u"]))
        for number in re.findall(NUMBER, match["n"]):
            value = to_number(number) * factor
            if value and not (factor == 12 and value >= 1200):       # 0 is baseline; "2020年" is a calendar year
                u, v = ("h", value / 60) if unit == "min" and value % 60 == 0 else (unit, value)
                u, v = ("d", v / 24) if u == "h" and v % 24 == 0 else (u, v)
                found.add((u, int(v) if float(v).is_integer() else v))
    return found


def numbers(text) -> set:
    t = norm(text)
    found = {float(n.replace(",", "")) for n in re.findall(r"(?<![a-z0-9.,\-])(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+(?:\.\d+)?)", t)}
    return found | {to_number(w) for w in re.findall(rf"(?<![a-z\-])(?:{WORD_NUMBER})(?![a-z])", t)}


def quantities(text) -> set:
    """Time quantities, and the other numbers as ("", value)."""
    return timepoints(text) | {("", n) for n in numbers(BEFORE.sub(" ", AFTER.sub(" ", norm(text))))}


def show(values) -> str:
    def one(unit, n):
        if not unit:
            return num(n)
        n, name = (n // 7, "week") if unit == "d" and n % 7 == 0 else (n, {"min": "minute", "h": "hour", "d": "day", "mo": "month"}[unit])
        return f"{num(n)} {name}{'' if n == 1 else 's'}"
    return ", ".join(one(*v) for v in sorted(values, key=lambda v: (v[0], float(v[1])))) or "none"


def dates(text) -> set:
    """Every date written in the text with its month and year: "3 February 2020" gives 2020-02-03, 2020-02 and
    2020. ISO dates, day-month-year, month-day-year, month-year, and 2020年2月3日."""
    t, out = norm(text), set()

    def add(year, month=None, day=None):
        if 1900 <= int(year) <= 2100 and (not month or 1 <= int(month) <= 12) and (not day or 1 <= int(day) <= 31):
            out.update([f"{int(year):04d}"] + ([f"{int(year):04d}-{int(month):02d}"] if month else [])
                       + ([f"{int(year):04d}-{int(month):02d}-{int(day):02d}"] if month and day else []))

    month = lambda name: next(i for i, full in enumerate(MONTHS, 1) if full.startswith(name[:3]))  # noqa: E731
    for m in re.finditer(r"(?<!\d)(\d{4})-(\d{2})(?:-(\d{2}))?(?![\d-])", t):
        add(*m.groups())
    for m in re.finditer(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH},?\s+(\d{{4}})", t):
        add(m[3], month(m[2]), m[1])
    for m in re.finditer(rf"(?<![a-z]){MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", t):
        add(m[3], month(m[1]), m[2])
    for m in re.finditer(rf"(?<![a-z]){MONTH},?\s+(\d{{4}})", t):
        add(m[2], month(m[1]))
    for m in re.finditer(r"(\d{4})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*[日号號])?", t):
        add(*m.groups())
    return out


def differ(a: str, b: str) -> bool:
    """Two dates differ at the precision both have."""
    return a[:min(len(a), len(b))] != b[:min(len(a), len(b))]


def instruments(text) -> tuple:
    """(named instruments, the text without them): tokens with two or more capitals and no more lower-case
    letters than capitals, such as WOMAC, SF-36, EQ-5D-5L or HbA1c. A text in capitals names none."""
    raw = unicodedata.normalize("NFKC", str(text or ""))
    letters = [c for c in raw if c.isascii() and c.isalpha()]
    if letters and sum(c.isupper() for c in letters) > 0.6 * len(letters):
        return set(), raw
    named = set()

    def take(match):
        token = match.group(0)
        upper, lower = sum(c.isupper() for c in token), sum(c.islower() for c in token)
        if upper >= 2 and lower <= upper and not re.fullmatch(r"[IVXLC]+|NCT\d+", token):
            named.add(token.upper().replace("-", ""))
            return " "
        return token
    return named, re.sub(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", take, raw)


def words(text) -> set:
    found = set()
    for word in re.findall(rf"[a-z]+|[{CJK}]", norm(text)):
        if word not in STOP and len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        if word not in STOP and (len(word) > 1 or not word.isascii()):
            found.add(word)
    return found


def foreign(paper: set, record: set) -> bool:
    """The paper's words are mostly Chinese, Japanese or Korean characters and the record's are not."""
    return sum(not w.isascii() for w in paper) * 2 > len(paper) and all(w.isascii() for w in record)


def wording(quote: str, translation: str, record: str) -> tuple:
    """(state, detail): named instruments that differ are inconsistent; otherwise MIN_SHARE of the quote's
    content words, or of its translation's, must recur in the record's text."""
    named_p, rest_p = instruments(quote)
    named_r, rest_r = instruments(record)
    shared = {a for a in named_p for b in named_r if a.startswith(b) or b.startswith(a)}
    if named_p and named_r and not shared:
        return "inconsistent", f"the paper names {', '.join(sorted(named_p))}, the record {', '.join(sorted(named_r))}"
    lead = f"same instrument ({', '.join(sorted(shared))}); " if shared else ""
    paper, record_words = words(instruments(translation)[1] if translation else rest_p), words(rest_r)
    if not paper:
        return ("consistent", lead + "the quote names nothing else") if shared else ("not_checked", "the quote names nothing to compare")
    if foreign(paper, record_words):
        return "not_checked", lead + "the quote is in another language than the record: add translation"
    common = paper & record_words
    said = f"{lead}{len(common)} of {len(paper)} words of the quote recur in the record" + (
        " (through the model's translation)" if translation else "")
    return ("consistent", said) if len(common) >= MIN_SHARE * len(paper) else ("not_checked", said + ": read both texts")


# ---------------------------------------------------------------------------------------------
# The record and the paper


def resolve(record, path: str):
    node = record
    for key, index in re.findall(r"([A-Za-z]\w*)|\[(\d+)\]", path or ""):
        node = obj(node).get(key) if key else node[int(index)] if isinstance(node, list) and int(index) < len(node) else None
        if node is None:
            return None
    return node


def module(record: dict, name: str) -> dict:
    return obj(obj(record.get("protocolSection")).get(name))


def load_record(path: Path) -> dict:
    record = load(path)
    if not txt(module(obj(record), "identificationModule").get("nctId")):
        die(f"{path} is not a study record as the API v2 returns it (no protocolSection.identificationModule.nctId).")
    return record


def role_of(path):
    return next((role for key, role in ROLES.items() if f".{key}[" in (path or "")), None)


def registered_outcomes(record: dict) -> list:
    outcomes = module(record, "outcomesModule")
    return [(f"protocolSection.outcomesModule.{key}[{i}]", role, o) for key, role in ROLES.items()
            for i, o in enumerate(dicts(outcomes.get(key)))]


def outcome_text(outcome: dict) -> str:
    frame = txt(outcome.get("timeFrame"))
    return ". ".join(p for p in (txt(outcome.get("measure")), txt(outcome.get("description")), frame and f"Time frame: {frame}") if p)


def text_of(value) -> str:
    """A record value as text, without enumeration codes such as BEHAVIORAL."""
    if isinstance(value, (dict, list)):
        return ". ".join(t for t in map(text_of, value.values() if isinstance(value, dict) else value) if t)
    text = "" if value is None or isinstance(value, bool) else str(value)
    return "" if re.fullmatch(r"[A-Z][A-Z_]+", text) else text


def identity_text(record: dict, field: str) -> str:
    if field == "title":
        return ". ".join(t for t in map(txt, (module(record, "identificationModule").get(k) for k in ("briefTitle", "officialTitle", "acronym"))) if t)
    if field == "condition":
        found = module(record, "conditionsModule")
        return "; ".join(map(str, (found.get("conditions") or []) + (found.get("keywords") or [])))
    if field == "intervention":
        arms = module(record, "armsInterventionsModule")
        given = dicts(arms.get("interventions"))
        return "; ".join(dict.fromkeys([txt(i.get("name")) for i in given] + [str(n) for i in given for n in i.get("otherNames") or []]
                                       + [txt(g.get("label")) for g in dicts(arms.get("armGroups"))]))
    sponsors = module(record, "sponsorCollaboratorsModule")
    return "; ".join([txt(obj(sponsors.get("leadSponsor")).get("name"))] + [txt(c.get("name")) for c in dicts(sponsors.get("collaborators"))])


def read_paper(path: Path) -> dict:
    if not path.is_file():
        die(f"{path} does not exist.")
    raw = path.read_bytes()
    if raw.startswith(b"%PDF"):
        die(f"{path} is a PDF. Make a text file first: pdftotext -layout paper.pdf registry-check/paper.txt")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        die(f"{path} is not UTF-8 text.")
    marks = list(PAGE_MARK.finditer(text))
    pages = list(enumerate(text.split("\f"), 1)) if "\f" in text else [
        (int(m[1] or m[2]), text[m.end():end]) for m, end in zip(marks, [m.start() for m in marks[1:]] + [len(text)])]
    return {"path": str(path), "text": text, "pages": pages, "sha256": hashlib.sha256(raw).hexdigest()}


def find(entry: dict, paper: dict, problems: list, where: str, least: int = MIN_QUOTE_TOKENS, exact: bool = False) -> dict:
    """The quote graded against the paper, with the page it is on; what is wrong goes to problems. An item's values
    are read from its quote, so an item needs the quote as one passage (EXACT), not with other words inside it."""
    quote, locator = txt(entry.get("quote")), txt(entry.get("locator"))
    if not quote or not locator:
        problems.append(f"{where}: give a quote from the paper and its locator")
        return {"quote": quote, "locator": locator, "grade": "ABSENT", "page": None}
    if len(tokens(quote)) < least:
        problems.append(f"{where}: the quote has {len(tokens(quote))} words; quote at least {least}")
    grade = match_quality(quote, paper["text"])["grade"]
    page = next((n for n, part in paper["pages"] if match_quality(quote, part)["grade"] in PASSING), None) \
        if grade in PASSING and len(paper["pages"]) > 1 else None
    if grade not in PASSING or (exact and grade != "EXACT"):
        problems.append(f"{where}: " + {"PARTIAL": "the quote is only partly in the paper (PARTIAL): copy it again",
                                        "ABSENT": "the quote is not in the paper (ABSENT)",
                                        "INTERLEAVED": "the quote is in the paper only with other words inside it (INTERLEAVED): "
                                                       "copy one continuous passage"}[grade])
    return {"quote": quote, "locator": locator, "grade": grade, "page": page}


# ---------------------------------------------------------------------------------------------
# Comparisons: each gives facets (name, state, detail)


def combine(facets: list) -> tuple:
    bad = [name for name, state, _ in facets if state == "inconsistent"]
    return ("inconsistent", bad) if bad else ("consistent" if all(s == "consistent" for _, s, _ in facets) else "not_checked", [])


def outcome_facets(item: dict, outcome: dict, role: str) -> list:
    quote, frame = txt(item.get("quote")), txt(outcome.get("timeFrame"))
    text = f"{txt(outcome.get('measure'))}. {txt(outcome.get('description'))}"
    paper, record = timepoints(quote), timepoints(frame) or timepoints(text)
    timepoint = (("not_checked", "the paper's quote gives no time point") if not paper else
                 ("not_checked", f'no time point the script can read in the record: "{frame}"') if not record else
                 ("consistent" if paper <= record else "inconsistent", f"paper {show(paper)}; record {show(record)}"))
    return [("role", "consistent" if item["role"] == role else "inconsistent", f"{item['role']} in the paper, {role} in the record"),
            ("timepoint", *timepoint), ("measure", *wording(quote, txt(item.get("translation")), text))]


def enrollment_facets(item: dict, info) -> list:
    info = obj(info)
    if type(info.get("count")) not in (int, float):
        return [("value", "not_checked", "the record gives no enrolment count")]
    kind = txt(info.get("type")).upper() or "no type"
    said = f"record {num(info['count'])} ({kind}); paper {num(item['value'])} ({item['basis']})"
    expected = {"ESTIMATED": "planned", "ACTUAL": "actual"}.get(kind)
    if expected is None or item["basis"] != expected:
        return [("value", "not_checked", said + (": the record does not say whether its count is planned or actual" if expected is None
                                                 else ": an ESTIMATED count is the plan; compare it with the planned size the paper states"
                                                 if kind == "ESTIMATED" else ": the record now gives the ACTUAL enrolment, not the plan"))]
    return [("value", "consistent" if float(info["count"]) == float(item["value"]) else "inconsistent", said)]


def date_facets(item: dict, value) -> list:
    recorded, kind = (txt(obj(value).get("date")), txt(obj(value).get("type"))) if isinstance(value, dict) else (txt(value), "")
    if not DATE.fullmatch(recorded):
        return [("value", "not_checked", "the record gives no date there")]
    coarse = "" if len(recorded) == len(item["date"]) else ", compared to the " + (
        "month" if min(len(recorded), len(item["date"])) == 7 else "year")
    return [("value", "inconsistent" if differ(item["date"], recorded) else "consistent",
             f"paper {item['date']}; record {recorded}" + (f" ({kind})" if kind else "") + coarse)]


def registration_timing(status: dict) -> dict:
    """When the registration was first submitted, against the start of enrolment and its type."""
    submitted, start = txt(status.get("studyFirstSubmitDate")), obj(status.get("startDateStruct"))
    begun, kind = txt(start.get("date")), txt(start.get("type")).upper() or "no type"
    facts = {"first_submitted": submitted or None, "first_posted": txt(obj(status.get("studyFirstPostDateStruct")).get("date")) or None,
             "start": begun or None, "start_type": kind, "relation": None}
    if not (DATE.fullmatch(submitted) and DATE.fullmatch(begun)):
        facts["text"] = "the record lacks the first-submitted date or the start date"
    elif kind != "ACTUAL":
        facts["text"] = f"the start date {begun} is {kind}: whether registration came before enrolment cannot be told"
    elif not differ(submitted, begun) and len(submitted) != len(begun):
        facts["text"] = f"first submitted {submitted}, within the ACTUAL start {begun}: the order cannot be told"
    else:
        after = differ(submitted, begun) and submitted > begun
        gap = abs((date.fromisoformat(submitted) - date.fromisoformat(begun)).days) if len(submitted) == len(begun) == 10 else None
        facts["relation"] = "after" if after else "before"
        facts["text"] = (f"first submitted {submitted}, " + (f"{gap} days " if gap else "")
                         + ("after" if after else "before" if gap or gap is None else "on") + f" the ACTUAL start {begun}")
    return facts


def generic_facets(item: dict, text: str) -> list:
    quote = txt(item.get("quote"))
    paper, record = quantities(quote), quantities(text)
    state, detail = wording(quote, txt(item.get("translation")), text)
    return ([("value", "not_checked" if not record else "inconsistent" if paper - record else "consistent",
              f"paper {show(paper)}; record {show(record) if record else 'no number'}")] if paper else []) + [
        ("wording", "not_checked" if state == "inconsistent" else state, detail)]


def evaluate(item: dict, record: dict, paper: dict, timing: dict, problems: list) -> dict:
    kind, where, quote = item["kind"], f"item {item['id']}", txt(item.get("quote"))
    path = ENROLMENT if kind == "enrollment" else item.get("record")
    result = {"id": item["id"], "kind": kind, "role": item.get("role"), "paper": find(item, paper, problems, where, exact=True),
              "path": path, "record_text": "", "notes": []}
    if kind == "enrollment" and float(item["value"]) not in numbers(quote):
        problems.append(f"{where}: {num(item['value'])} is not in the quote")
    if kind == "date" and item["date"] not in dates(quote):
        problems.append(f"{where}: the date {item['date']} is not in the quote")
    wanted = SAYS.get(item.get("role")) or SAYS.get(item.get("claim"))
    if wanted and not any(re.search(rf"(?<![a-z]){w}" if w.isascii() else w, norm(quote)) for w in wanted):
        result["notes"].append(f"the quote does not say {item.get('role') or item.get('claim')}: check it against the paper")
    value = resolve(record, path) if path else None
    if kind == "registration_claim":
        result.update(path="statusModule: studyFirstSubmitDate, startDateStruct", record_text=timing["text"])
        facets = [("timing", "not_checked", timing["text"])] if timing["relation"] is None else [
            ("timing", "consistent" if (timing["relation"] == "after") == (item["claim"] == "retrospective") else "inconsistent",
             f"the paper says {item['claim']}; {timing['text']}")]
    elif kind == "outcome" and path is None:
        facets = [("added", "inconsistent", "reported in the paper; no registered outcome is paired with it")]
    elif value is None or (kind == "outcome" and not (isinstance(value, dict) and role_of(path))):
        if kind != "enrollment":
            problems.append(f"{where}: {path} is not " + ("a registered outcome" if value is not None else "in the record"))
        facets = [("record", "not_checked", f"the record has nothing usable at {path}")]
    elif kind == "outcome":
        result.update(record_role=role_of(path), record_text=outcome_text(value))
        facets = outcome_facets(item, value, role_of(path))
    elif kind == "enrollment":
        result["record_text"] = f"{value.get('count')} ({value.get('type') or 'no type'})" if isinstance(value, dict) else text_of(value)
        facets = enrollment_facets(item, value)
    elif kind == "date":
        result["record_text"] = text_of(value) if not isinstance(value, dict) else f"{value.get('date')} ({value.get('type') or 'no type'})"
        facets = date_facets(item, value)
    else:
        result["record_text"] = text_of(value)
        facets = generic_facets(item, result["record_text"])
    result["state"], result["types"] = combine(facets)
    result["facets"] = [{"facet": n, "state": s, "detail": d} for n, s, d in facets]
    return result


def as_registered(item: dict, result: dict, earlier, version: dict, problems: list):
    """(state, types, detail) of an outcome against the version from before enrolment, when there is one."""
    if item["kind"] != "outcome":
        return None
    if earlier is None:
        return (result["state"], result["types"], "the record has not changed since enrolment began") \
            if version["changed_since_start"] is False else ("not_checked", [], "no version from before enrolment was seen (see the top)")
    if "earlier" not in item:
        return "not_checked", [], "no pairing with the earlier version: add earlier (a path, or null)"
    if item["earlier"] is None:
        return "inconsistent", ["added"], "not in the earlier version"
    value, role = resolve(earlier, item["earlier"]), role_of(item["earlier"])
    if not isinstance(value, dict) or role is None:
        problems.append(f"item {item['id']}: {item['earlier']} is not a registered outcome of the earlier version")
        return "not_checked", [], f"the earlier version has no outcome at {item['earlier']}"
    result["earlier_text"] = outcome_text(value)
    facets = outcome_facets(item, value, role)
    return (*combine(facets), "; ".join(f"{name}: {detail}" for name, _, detail in facets))


def check_identity(spec: dict, record: dict, paper: dict, problems: list) -> dict:
    fields = []
    for field in IDENTITY:
        entry, text = obj(spec.get(field)), identity_text(record, field)
        state, detail = "not_checked", "no quote from the paper"
        if entry:
            find(entry, paper, problems, f"identity.{field}", least=2)
            paper_words, record_words = words(txt(entry.get("translation")) or txt(entry.get("quote"))), words(text)
            common = paper_words & record_words
            state, detail = (("not_checked", "nothing to compare") if not (paper_words and record_words) else
                             ("not_checked", "the quote is in another language than the record: add translation")
                             if foreign(paper_words, record_words) else
                             ("consistent" if len(common) >= MIN_SHARE * len(paper_words) else "inconsistent",
                              f"{len(common)} of {len(paper_words)} words recur: {', '.join(sorted(common)) or 'none'}"
                              + (" (through the model's translation)" if txt(entry.get("translation")) else "")))
        fields.append({"field": field, "state": state, "paper": txt(entry.get("quote")), "record": text, "detail": detail})
    core = [f["state"] for f in fields[:3]]
    return {"verdict": "same" if core.count("consistent") == 3 else "partial" if "consistent" in core else
            "different" if core.count("inconsistent") == 3 else "unconfirmed", "fields": fields}


# ---------------------------------------------------------------------------------------------
# compare


def format_errors(spec) -> list:
    if not isinstance(spec, dict):
        return ["items.json must hold a JSON object"]
    paper, record, items = obj(spec.get("paper")), obj(spec.get("record")), spec.get("items", [])
    checks = ((not txt(paper.get("text")), "paper.text must name the paper's text file"),
              ("published" in paper and not DATE.fullmatch(txt(obj(paper["published"]).get("date"))),
               "paper.published.date must be YYYY, YYYY-MM or YYYY-MM-DD"),
              (not txt(record.get("file")), "record.file must name the saved record"),
              (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt(record.get("read"))), "record.read must be the date it was fetched"),
              (not isinstance(spec.get("identity"), dict), "identity must be an object: title, condition, intervention, sponsor"),
              (not (isinstance(spec.get("registrations"), list) and all(
                  txt(obj(r).get("registry")) and txt(obj(r).get("id")) for r in spec["registrations"])),
               "registrations must be a list of objects with registry and id"),
              (not isinstance(spec.get("unreported", []), list) or not all(
                  PATH.fullmatch(txt(obj(u).get("record"))) and txt(obj(u).get("searched")) for u in spec.get("unreported") or []),
               "unreported must be a list of objects with a record path and searched"),
              (not isinstance(items, list) or not all(isinstance(i, dict) for i in items), "items must be a list of objects"))
    errors = [message for failed, message in checks if failed]
    items = dicts(items)
    if len({txt(i.get("id")) for i in items} - {""}) < len(items):
        errors.append("every item needs its own id")
    for item in items:
        where, kind = f"item {txt(item.get('id')) or '?'}", item.get("kind")
        key, allowed = CHOICES.get(kind, (None, ()))
        errors += [message for failed, message in (
            (kind not in KINDS, f"{where}: kind must be one of {', '.join(KINDS)}"),
            (bool(key) and item.get(key) not in allowed, f"{where}: {key} must be one of {', '.join(allowed)}"),
            (kind in ("outcome", "date", "intervention", "other") and not (item.get("record") is None and kind == "outcome" and "record" in item
                                                                           or PATH.fullmatch(txt(item.get("record")))),
             f"{where}: record must be a field path such as protocolSection.statusModule.startDateStruct" + (", or null" if kind == "outcome" else "")),
            (item.get("earlier") is not None and not PATH.fullmatch(txt(item.get("earlier"))), f"{where}: earlier must be a field path or null"),
            (kind == "enrollment" and type(item.get("value")) not in (int, float), f"{where}: value must be the number the quote gives"),
            (kind == "date" and not DATE.fullmatch(txt(item.get("date"))), f"{where}: date must be YYYY, YYYY-MM or YYYY-MM-DD")) if failed]
    return errors


def version_facts(record: dict, published: str) -> dict:
    status = module(record, "statusModule")
    last, start = txt(obj(status.get("lastUpdatePostDateStruct")).get("date")), txt(obj(status.get("startDateStruct")).get("date"))
    changed = None if not (DATE.fullmatch(last) and DATE.fullmatch(start)) or (not differ(last, start) and len(last) != len(start)) \
        else differ(last, start) and last > start
    return {"last_update_posted": last or None, "changed_since_start": changed,
            "after_publication": bool(published and DATE.fullmatch(last) and differ(last, published) and last > published),
            "why_not": f"The record was last updated on {last}, after enrolment began ({start}), and the API gives only the current "
                       "version, so the outcomes as registered before enrolment were not seen" if changed else
                       "The record's last update or start date is missing or too coarse to tell whether it changed after enrolment began"}


def disclosure(entry: dict, paper: dict, problems: list, where: str) -> str:
    said = obj(entry.get("disclosure"))
    if txt(said.get("quote")):
        return f'the paper states a change: "{find(said, paper, problems, where + " disclosure")["quote"]}" ({txt(said.get("locator"))})'
    if txt(said.get("searched")):
        return f"no statement of a change found; searched: {said['searched']}"
    problems.append(f"{where}: say whether the paper states this change: disclosure with a quote, or with searched")
    return "not recorded"


def cmd_compare(args) -> int:
    base = Path(args.dir)
    spec = load(base / "items.json")
    errors = format_errors(spec)
    if errors:
        die(f"{base / 'items.json'} is not in the format of references/matching-and-items.md:\n  - " + "\n  - ".join(errors))
    problems, published = [], obj(spec["paper"].get("published"))
    paper, record_path = read_paper(at(base, spec["paper"]["text"])), at(base, spec["record"]["file"])
    record, earlier = load_record(record_path), load_record(Path(args.earlier)) if args.earlier else None
    nct, status = txt(module(record, "identificationModule").get("nctId")), module(record, "statusModule")
    if published and published["date"] not in dates(find(published, paper, problems, "paper.published", least=2)["quote"]):
        problems.append(f"paper.published: the date {published['date']} is not in the quote")
    version, timing = version_facts(record, txt(published.get("date"))), registration_timing(status)
    early = txt(obj(module(earlier, "statusModule").get("lastUpdatePostDateStruct")).get("date")) if earlier is not None else ""
    if earlier is not None and txt(module(earlier, "identificationModule").get("nctId")) != nct:
        problems.append("--earlier is a version of another trial")
    elif DATE.fullmatch(early) and DATE.fullmatch(version["last_update_posted"] or "") and not differ(early, version["last_update_posted"]):
        problems.append(f"--earlier was last updated on {early}, as the current version: it is not an earlier version")
    identity, registrations = check_identity(spec["identity"], record, paper, problems), []
    for reg in spec["registrations"]:
        where, ctgov = f"registrations[{reg['id']}]", "clinicaltrials" in norm(reg["registry"]).replace(" ", "")
        find(reg, paper, problems, where, least=1)
        if norm_id(reg["id"]) not in norm_id(reg.get("quote")):
            problems.append(f"{where}: the number is not in its quote")
        state, detail = (("consistent", "the record compared") if norm_id(reg["id"]) == nct else
                         ("inconsistent", f"the paper prints {reg['id']}; the record compared is {nct}")) if ctgov else (
            "not_checked", "no record of this registry was compared")
        registrations.append({"registry": reg["registry"], "id": reg["id"], "state": state, "detail": detail})
    if not any("clinicaltrials" in norm(r["registry"]).replace(" ", "") for r in spec["registrations"]):
        problems.append("registrations: list the ClinicalTrials.gov number the paper prints")
    stop, results, unpaired = identity["verdict"] in ("different", "unconfirmed"), [], []
    for item in spec.get("items", []):
        if stop:
            results.append({"id": item["id"], "kind": item["kind"], "state": "not_checked", "types": [],
                            "reason": "not compared: the record is not shown to be the paper's trial"})
            continue
        result = evaluate(item, record, paper, timing, problems)
        result["as_registered"] = as_registered(item, result, earlier, version, problems)
        if item["kind"] == "outcome" and "inconsistent" in (result["state"], (result["as_registered"] or ("",))[0]):
            result["disclosure"] = disclosure(item, paper, problems, f"item {item['id']}")
        results.append(result)
    paired = {r["path"]: r for r in results if r["kind"] == "outcome" and r.get("path")}
    declared = {} if stop else {txt(u["record"]): u for u in spec.get("unreported") or []}
    for path in declared:
        if role_of(path) is None or not isinstance(resolve(record, path), dict) or path in paired:
            problems.append(f"unreported: {path} is not a registered outcome, or an item pairs it")
    for path, role, outcome in [] if stop else registered_outcomes(record):
        entry = declared.get(path)
        if path in paired:
            continue
        said = obj(obj(entry).get("disclosure"))
        why = f'the paper says: "{find(said, paper, problems, "unreported " + path)["quote"]}"' if txt(said.get("quote")) else "no explanation quoted"
        unpaired.append({"path": path, "role": role, "text": outcome_text(outcome), "state": "inconsistent" if entry else "not_checked",
                         "types": ["omitted"] if entry else [], "detail": f"not reported in the paper; searched: {entry['searched']}; {why}"
                         if entry else "no item pairs it and no search for it is recorded in unreported"})
    counts, ok = Counter(r["state"] for r in results), not problems and not stop
    context = {"paper": {"path": paper["path"], "sha256": paper["sha256"], "published": published or None},
               "record": {"nct": nct, "file": str(record_path), "sha256": sha256(record_path), "read": spec["record"]["read"],
                          "api": api_version(base), "version": version},
               "earlier": {"file": args.earlier, "sha256": sha256(Path(args.earlier)), "last_update_posted": early or None} if args.earlier else None,
               "timing": timing, "identity": identity, "primary": {} if stop else primary_outcome(results, record, unpaired),
               "items": results, "registered_not_paired": unpaired, "registrations": registrations, "problems": problems}
    (base / "compare.json").write_text(json.dumps(context, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (base / "compare.md").write_text("\n".join(compare_lines(context, stop)) + "\n", encoding="utf-8")
    print(json.dumps({"ok": ok, "identity": identity["verdict"], "record": nct, "items": len(results),
                      **{state: counts[state] for state in ("consistent", "inconsistent", "not_checked")},
                      "inconsistent_items": [f"{r['id']}: {', '.join(r['types'])}" for r in results if r["state"] == "inconsistent"],
                      "registered_not_paired": [u["path"] for u in unpaired], "problems": problems,
                      "report": str(base / "compare.md")}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def primary_outcome(results: list, record: dict, unpaired: list) -> dict:
    """The primary outcome as registered against the paper's primary outcome items."""
    registered = [(p, o) for p, role, o in registered_outcomes(record) if role == "primary"]
    reported = [r for r in results if r["kind"] == "outcome" and r.get("role") == "primary"]
    by_path = {r["path"]: r for r in results if r["kind"] == "outcome" and r["path"]}
    times_r = set().union(*(timepoints(o.get("timeFrame")) for _, o in registered))
    times_p = set().union(*(timepoints(r["paper"]["quote"]) for r in reported))
    types = [name for name, found in (
        ("added", any(r["path"] is None for r in reported)),
        ("role", any(r.get("record_role") not in (None, "primary") for r in reported)
         or any(by_path[p].get("role") != "primary" for p, _ in registered if p in by_path)),
        ("omitted", any(u["role"] == "primary" and u["state"] == "inconsistent" for u in unpaired)),
        ("timepoint", bool(times_r and times_p and not times_p <= times_r))) if found]
    agree = registered and reported and all(p in by_path and by_path[p]["state"] == "consistent" for p, _ in registered) \
        and all(r["state"] == "consistent" for r in reported)
    return {"state": "inconsistent" if types else "consistent" if agree else "not_checked", "types": types,
            "registered": [outcome_text(o) for _, o in registered] or ["none registered"],
            "reported": [f"{r['id']}: {r['paper']['quote']}" for r in reported] or ["no item is a primary outcome of the paper"],
            "detail": f"time points registered {show(times_r)}; reported {show(times_p)}"}


def api_version(base: Path) -> str:
    data = obj(load(base / "api-version.json")) if (base / "api-version.json").is_file() else {}
    return (f"API {data['apiVersion']}, data timestamp {data.get('dataTimestamp', 'not given')}" if txt(data.get("apiVersion"))
            else "API version not recorded: save the response of /api/v2/version as api-version.json")


def compare_lines(c: dict, stop: bool) -> list:
    rec, version, published, timing = c["record"], c["record"]["version"], c["paper"]["published"], c["timing"]
    lines = ["# Registry comparison", "", f"Paper: {c['paper']['path']} (SHA-256 {c['paper']['sha256']})"
             + (f", published {published['date']}." if published else "."),
             f"Record: {rec['nct']}, {rec['file']} (SHA-256 {rec['sha256']}), read {rec['read']}; {rec['api']}.",
             f"Version read: last update posted {version['last_update_posted'] or 'not given'}. Registration: {timing['text']}.", ""]
    if version["after_publication"]:
        lines.append(f"- The record was last updated on {version['last_update_posted']}, after the paper was published "
                     f"({published['date']}): this compares the record as it is now, not as the authors saw it.")
    if c["earlier"]:
        early = c["earlier"]["last_update_posted"] or ""
        lines.append(f"- Earlier version: {c['earlier']['file']} (SHA-256 {c['earlier']['sha256']}), last updated {early or 'on no given date'}; "
                     "outcomes are compared with it under As registered." + (
                         f" It too was posted after enrolment began ({timing['start']}), so it is not a version from before enrolment."
                         if DATE.fullmatch(early) and timing["start"] and differ(early, timing["start"]) and early > timing["start"] else ""))
    elif version["changed_since_start"] is not False:
        lines.append(f"- As registered before enrolment: not_checked. {version['why_not']}. An earlier version from the record's "
                     "history on the registry's website can be compared with --earlier.")
    counts = Counter(r["state"] for r in c["items"])
    lines += ["", f"{len(c['items'])} items: {counts['consistent']} consistent, {counts['inconsistent']} inconsistent, "
              f"{counts['not_checked']} not checked. Problems to correct in items.json: {len(c['problems'])}.", "",
              "## Is this record the paper's trial?", "", {
                  "same": "Title, condition and intervention agree with the record.",
                  "partial": "Only part of title, condition and intervention agrees: confirm with the user that this record is the "
                             "paper's trial before using the comparison.",
                  "different": "Title, condition and intervention all disagree with the record: the number in the paper may be "
                               "miswritten and lead to another trial. No item was compared; ask the user for the right record.",
                  "unconfirmed": "The record is not shown to be the paper's trial (see the details). No item was compared."}[
                  c["identity"]["verdict"]], "", row("Field", "State", "Paper", "Record", "Detail"), "|---" * 5 + "|"]
    lines += [row(f["field"], f["state"], f["paper"], f["record"], f["detail"]) for f in c["identity"]["fields"]]
    if not stop:
        p = c["primary"]
        lines += ["", "## Primary outcome", "", f"State: {label(p['state'], p['types'])}; {p['detail']}.", "",
                  row("Registered as primary", "Reported as primary"), "|---|---|"]
        lines += [row(p["registered"][i] if i < len(p["registered"]) else "", p["reported"][i] if i < len(p["reported"]) else "")
                  for i in range(max(len(p["registered"]), len(p["reported"])))]
        lines += ["", "## Items", "", row("Item", "Kind", "State", "As registered"), "|---" * 4 + "|"]
        lines += [row(r["id"], r["kind"], label(r["state"], r["types"]), label(*r["as_registered"][:2]) if r["as_registered"] else "")
                  for r in c["items"]]
        for r in c["items"]:
            found, earlier = r["paper"], [r["earlier_text"]] if r.get("earlier_text") else []
            heads = [f"Paper ({found['locator']}" + (f", page {found['page']}" if found["page"] else "") + f", {found['grade']})",
                     f"Record: {r['path'] or 'no registered outcome paired'}"] + ["Earlier version"] * len(earlier)
            lines += ["", f"### {r['id']}: {r['kind']}, {label(r['state'], r['types'])}", "", row(*heads), "|---" * len(heads) + "|",
                      row(found["quote"], r["record_text"] or "nothing", *earlier), ""]
            lines += [f"- {f['facet']}, {f['state']}: {f['detail']}." for f in r["facets"]] + [f"- Note: {n}." for n in r["notes"]]
            if r["as_registered"]:
                lines.append(f"- As registered, {label(*r['as_registered'][:2])}: {r['as_registered'][2]}.")
            if r.get("disclosure"):
                lines.append(f"- Change stated in the paper: {r['disclosure']}.")
            if r["kind"] == "outcome" and r["path"]:
                lines.append("- Pairing with the registered outcome: the model's judgement.")
        lines += ["", "## Registered outcomes no item pairs", ""] + ([row("Registered outcome", "Role", "State", "Detail"), "|---" * 4 + "|"] + [
            row(u["text"], u["role"], label(u["state"], u["types"]), u["detail"]) for u in c["registered_not_paired"]]
            if c["registered_not_paired"] else ["None."])
    lines += ["", "## Registration numbers in the paper", "", row("Registry", "Number", "State", "Detail"), "|---" * 4 + "|"]
    lines += [row(r["registry"], r["id"], r["state"], r["detail"]) for r in c["registrations"]]
    lines += ["", "## Problems to correct in items.json", ""] + [f"- {p}" for p in c["problems"]] if c["problems"] else []
    return lines + ["", "States describe what the paper and the record say. Inconsistent names a difference and its type, not its "
                    "cause; whether the paper states a change is given under each item. Pairings of reported with registered "
                    "outcomes, and translations, are the model's."]


# ---------------------------------------------------------------------------------------------
# search


def candidate(study: dict) -> dict:
    sec = obj(study.get("protocolSection"))
    ident, status, design = (obj(sec.get(m)) for m in ("identificationModule", "statusModule", "designModule"))

    def dated(key):
        found = status.get(key)
        return f"{found.get('date', 'no date')} ({found.get('type', 'no type')})" if isinstance(found, dict) else "not in page"

    def listed(name, values):
        return ("; ".join(v for v in values if v) or "none listed") if name in sec else "not in page"
    enrolment, arms = obj(design.get("enrollmentInfo")), obj(sec.get("armsInterventionsModule"))
    return {"nct": norm_id(ident.get("nctId")), "title": txt(ident.get("briefTitle")) or txt(ident.get("officialTitle")) or "not in page",
            "status": txt(status.get("overallStatus")) or "not in page", "start": dated("startDateStruct"),
            "primary_completion": dated("primaryCompletionDateStruct"),
            "enrollment": f"{enrolment['count']} ({enrolment.get('type', 'no type')})" if "count" in enrolment else "not in page",
            "has_results": {True: "yes", False: "no"}.get(study.get("hasResults"), "not in page"),
            "conditions": listed("conditionsModule", [str(x) for x in obj(sec.get("conditionsModule")).get("conditions") or []]),
            "interventions": listed("armsInterventionsModule", [txt(i.get("name")) for i in dicts(arms.get("interventions"))]),
            "found_by": []}


def cmd_search(args) -> int:
    base = Path(args.dir)
    log = obj(load(base / "search-log.json"))
    searches = log.get("searches") if isinstance(log.get("searches"), list) else []
    errors = [] if searches else ["searches must be a non-empty list"]
    errors += [f"search {txt(obj(s).get('id')) or '?'}: needs id, url (as sent), date (YYYY-MM-DD) and pages" for s in searches
               if not (txt(obj(s).get("id")) and txt(s.get("url")) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt(s.get("date")))
                       and isinstance(s.get("pages"), list) and s["pages"] and all(txt(p) for p in s["pages"]))]
    errors += ["every search needs its own id"] if len({txt(obj(s).get("id")) for s in searches}) < len(searches) else []
    errors += [f"relevance {txt(r.get('nct')) or '?'}: needs nct, call ({', '.join(CALLS)}) and reason"
               for r in dicts(log.get("relevance")) if not (txt(r.get("nct")) and r.get("call") in CALLS and txt(r.get("reason")))]
    if errors:
        die(f"{base / 'search-log.json'} is not in the format of references/prior-trial-search.md:\n  - " + "\n  - ".join(errors))
    problems, rows, pages, found = [], [], [], {}
    for s in searches:
        total, saved, last = None, 0, {}
        for name in s["pages"]:
            path = at(base, name)
            page = load(path)
            if not isinstance(page, dict) or not isinstance(page.get("studies"), list):
                die(f"{path} is not a page of an API v2 study search (it has no list of studies).")
            total = page["totalCount"] if total is None and isinstance(page.get("totalCount"), int) else total
            pages.append((s["id"], name, sha256(path), len(page["studies"])))
            saved, last = saved + len(page["studies"]), page
            for trial in map(candidate, dicts(page["studies"])):
                entry = found.setdefault(trial["nct"], trial) if trial["nct"] else {"found_by": [s["id"]]}
                entry["found_by"] += [] if s["id"] in entry["found_by"] else [s["id"]]
        if last.get("nextPageToken"):
            problems.append(f"{s['id']}: the last saved page has a nextPageToken: fetch the remaining pages, or narrow the query")
        rows.append((s["id"], s["date"], "; ".join(f"{k}={v}" for k, v in parse_qsl(urlsplit(s["url"]).query) if k not in ("format", "pageToken"))
                     or "none", "not reported" if total is None else total, saved, "no" if last.get("nextPageToken") else "yes"))
    calls = {norm_id(r["nct"]): r for r in dicts(log.get("relevance"))}
    problems += [f"relevance: {nct} is in no saved page" for nct in calls if nct not in found]
    columns = ("nct", "title", "status", "start", "primary_completion", "enrollment", "has_results", "conditions",
               "interventions", "found_by", "relevance", "reason", "judged_by")
    table = [[*(t[k] for k in columns[:9]), "; ".join(t["found_by"]), calls.get(n, {}).get("call", "not judged"),
              txt(calls.get(n, {}).get("reason")), "model" if n in calls else ""] for n, t in found.items()]
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([columns, *table])
    (base / "candidates.csv").write_text(out.getvalue(), encoding="utf-8")
    days, statuses = ", ".join(sorted({s["date"] for s in searches})), Counter(t["status"] for t in found.values())
    lines = ["# Registry search", "", f"Question: {txt(log.get('question')) or 'not stated'}",
             f"Registry: ClinicalTrials.gov; {api_version(base)}.", "", "## Searches", "",
             row("Search", "Date", "Parameters as sent", "Reported total", "Records in saved pages", "Last page reached"),
             "|---" * 6 + "|", *(row(*r) for r in rows), "", "## Saved pages", "", row("Search", "File", "SHA-256", "Records"),
             "|---" * 4 + "|", *(row(*p) for p in pages), "", f"## Trials found: {len(found)}, whatever their status", ""]
    if found:
        lines += ["Statuses as the registry gives them: " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())) + ".", "",
                  row("NCT", "Title", "Status", "Start", "Primary completion", "Enrolment", "Results posted", "Conditions",
                      "Interventions", "Found by", "Relevance (model)"), "|---" * 11 + "|", *(row(*t[:11]) for t in table), "",
                  "Relevance is the model's judgement from the record's text; the reasons are in candidates.csv. These are the records "
                  f"these queries returned from ClinicalTrials.gov on {days}. They are not every trial on the question: other wordings, "
                  "other registries and trials never registered are not in them."]
    else:
        lines.append(f"None of the {len(searches)} searches returned a record. This shows only that these queries found no record in "
                     f"ClinicalTrials.gov on {days}; it does not show that the question has not been studied.")
    lines += ["", "## Problems to correct", ""] + [f"- {p}" for p in problems] if problems else []
    (base / "search.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": not problems, "searches": len(searches), "trials": len(found), "statuses": dict(statuses),
                      "not_judged": [n for n in found if n not in calls], "problems": problems,
                      "report": str(base / "search.md"), "table": str(base / "candidates.csv")}, indent=2, ensure_ascii=False))
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare a trial report with its ClinicalTrials.gov record, or tabulate a search.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, about in (("search", "Tabulate the saved pages listed in search-log.json; write search.md and candidates.csv"),
                        ("compare", "Compare items.json, the paper and the saved record; write compare.md and compare.json")):
        p = sub.add_parser(name, help=about)
        p.add_argument("--dir", default="registry-check", help="The output folder (default: registry-check)")
        if name == "compare":
            p.add_argument("--earlier", help="An earlier version of the record, in the shape the API returns")
    args = parser.parse_args(argv)
    return cmd_search(args) if args.command == "search" else cmd_compare(args)


if __name__ == "__main__":
    sys.exit(main())
