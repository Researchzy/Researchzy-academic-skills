#!/usr/bin/env python3
"""Mechanical checks on a manuscript, and on a revision of one.

The agent plans, drafts and revises; this script checks what needs no judgement.

  manuscript_check.py check FILE… [--bib refs.bib] [--final]
                            [--budget "Abstract=250,Introduction=600"] [--out writing]
  manuscript_check.py diff BEFORE AFTER [--strict] [--out writing]

check reads .md, .tex, .txt and .docx files (several files are one manuscript, in the order
given) and writes manuscript-check.md and manuscript-check.json under --out:

  placeholders   [Evidence needed: …], [Citation needed: …], [Author input needed: …], TODO, TBD,
                 FIXME, XXX, \\todo, [@NEW:…] and ?? (an unresolved LaTeX reference)
  numbers        a percentage that disagrees with its n/N ("12/40 (35%)"); a number in the
                 abstract that is nowhere in the main text or tables; a labelled quantity ("mean
                 age was 54.3") given one value in the abstract and another in the text or
                 tables; one value written at two precisions (0.91 and 0.910)
  terms          one term written two ways (follow-up/followup, data set/dataset,
                 COVID-19/Covid-19); abbreviations used before or without a definition, defined
                 twice, or defined and never used, in the abstract and in the main text
                 separately; US and UK spelling mixed
  citations      \\cite and Pandoc @keys that are missing from the .bib; .bib entries never cited
  words          words per section, against --budget. A name matches a section heading; Total
                 is everything outside the abstract, the tables and the reference list.

Errors are: a percentage that disagrees with its n/N, a cited key missing from the .bib, a
section over its budget and, with --final, any placeholder. Everything else is a warning to look
at. A check that could not run is reported as not checked, never as passed.

diff compares a text before and after a revision, sentence by sentence, and writes
revision-check.md and revision-check.json: numbers that changed, disappeared or appeared;
citations dropped, added or moved to another sentence; hedges removed, intensifiers added,
negations and directions that changed; sentences with no counterpart, which it cannot compare.

Exit codes: 0; 1 when check --final finds errors, or diff --strict finds a changed number or
citation; 2 for a usage error or a file that is missing or cannot be read.

Standard library only. Portions are derived from MIT-licensed code: see LICENSE-MIT.txt next to
this file and THIRD_PARTY_NOTICES.md in the plugin. Portions are derived, with changes, from
Apache-2.0-licensed code: see the licenses folder and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree

TOOL = "researchzy-writing"
SUFFIXES = (".md", ".markdown", ".tex", ".txt", ".docx")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# ---------------------------------------------------------------------------------------------
# Reading a manuscript
# ---------------------------------------------------------------------------------------------

FENCE = re.compile(r"^\s*(```|~~~)")
HEADING_MD = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
HEADING_TEX = re.compile(r"\\(section|subsection|subsubsection)\*?\s*(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
TEX_LEVEL = {"section": 1, "subsection": 2, "subsubsection": 3}
# A line that is nothing but a usual section name is a heading, also without "#" (.txt, .docx).
PLAIN_HEADING = re.compile(
    r"(?:\d+\.?\s+)?(?:abstract|summary|background|introduction|related work|methods?|materials and methods"
    r"|methodology|patients and methods|experiments?|results|results and discussion|discussion|conclusions?"
    r"|limitations|acknowledge?ments?|references|bibliography|funding|data availability|code availability"
    r"|author contributions|competing interests|conflicts? of interest|supplementary materials?|appendix"
    r"|keywords):?", re.I)
REFS_TITLE = re.compile(r"references?|bibliography|works cited|literature cited|reference list|refs")
ABSTRACT_TITLE = re.compile(r"(?:structured )?abstract|summary")
VERBATIM = re.compile(r"\\begin\{(verbatim\*?|lstlisting|minted|comment)\}")
TABLE_BEGIN = re.compile(r"\\begin\{(?:tabular[x*]?|longtable|array|tabu)\}")
TABLE_END = re.compile(r"\\end\{(?:tabular[x*]?|longtable|array|tabu)\}")
LIST_ITEM = re.compile(r"^\s*(?:[-*+•]|\d+[.)]|\\item\b)\s")
TEX_SUBS = [(re.compile(p), r) for p, r in (
    (r"\\\\(?:\[[^\]]*\])?", " "), (r"\\%", "%"), (r"\\&", "&"), (r"\\\$", ""),
    (r"(?<=\d)\\,(?=\d{3}(?!\d))", ","), (r"\\[,;:!]|~|\\ ", " "),
    (r"\\pm\b", "±"), (r"\\times\b", "×"), (r"\\(?:leq|le)\b", "≤"), (r"\\(?:geq|ge)\b", "≥"),
    (r"\\(?:approx|sim)\b", "≈"), (r"\$", " "))]

TEX_CITE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?\s*(?:\[[^\]]*\]\s*)*\{([^{}]*)\}")
PANDOC_GROUP = re.compile(r"\[[^\[\]]*@[^\[\]]*\]")
PANDOC_KEY = re.compile(r"(?<![\w.@\\/])-?@([A-Za-z0-9_](?:[\w:.+/-]*\w)?)")
NUMERIC_CITE = re.compile(r"\[\d{1,3}(?:\s*[-–,]\s*\d{1,3})*\]")
NOT_A_CITATION = ("fig:", "tbl:", "tab:", "eq:", "sec:", "lst:", "new:")
# Markup whose digits are not results: cross-references, file names, lengths, URLs, DOIs.
NOISE = re.compile(
    r"\\(?:ref|eqref|autoref|[cC]ref|pageref|nameref|label|includegraphics|input|include|bibliography"
    r"|bibliographystyle|usepackage|documentclass|vspace|hspace|setlength|setcounter|url|href|begin|end)\*?"
    r"(?:\s*\[[^\]]*\])*(?:\s*\{[^{}]*\})*"
    r"|https?://\S+|\bdoi:\s*\S+|\b10\.\d{4,9}/\S+|\]\([^)\s]*\)|\{[#.][^{}]*\}")
TEX_COMMAND = re.compile(r"\\[A-Za-z]+\*?")
MD_MARKS = re.compile(r"[*`]|(?<!\w)_|_(?!\w)|^\s*>+\s?")
WORD = re.compile(r"\w+(?:[-'’.,/]\w+)*")
PLACEHOLDERS = (
    ("evidence_needed", re.compile(r"\[\s*Evidence needed\b[^\]]*\]", re.I)),
    ("citation_needed", re.compile(r"\[\s*Citation needed\b[^\]]*\]", re.I)),
    ("author_input_needed", re.compile(r"\[\s*Author input needed\b[^\]]*\]", re.I)),
    ("new_citation_marker", re.compile(r"\[?@NEW:[^\];]*\]?", re.I)),
    # Case-sensitive, so that "tbd" inside a word or the numeral XXXI is not a marker.
    ("todo", re.compile(r"\b(?:TODO|FIXME|TBD|X{3,})\b|\\todo\b")),
    ("unresolved_reference", re.compile(r"\?\?+|\[\?\]")),
)


def fail(message: str):
    print(message, file=sys.stderr)
    raise SystemExit(2)


def docx_text(path: Path) -> str:
    """A .docx as plain paragraphs: headings as "#", table rows as "| a | b |". Text that a
    tracked change deleted is left out."""
    try:
        with zipfile.ZipFile(path) as zf:
            body = ElementTree.fromstring(zf.read("word/document.xml")).find(W + "body")
    except (OSError, zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        fail(f"{path}: not a readable .docx file")

    def blocks(parent):
        for child in parent if parent is not None else ():
            if child.tag in (W + "p", W + "tbl"):
                yield child
            elif child.tag == W + "sdt":
                yield from blocks(child.find(W + "sdtContent"))

    def paragraph(p) -> str:
        return "".join((node.text or "") if node.tag == W + "t" else " " if node.tag in (W + "tab", W + "br") else ""
                       for node in p.iter()).strip()

    out = []
    for block in blocks(body):
        if block.tag == W + "p":
            style = block.find(f"{W}pPr/{W}pStyle")
            level = re.match(r"(?i)heading\s*(\d)", style.get(W + "val", "")) if style is not None else None
            text = paragraph(block)
            out.append(("#" * int(level.group(1)) + " " if level and text else "") + text)
        else:
            for row in block.iter(W + "tr"):
                cells = [" ".join(filter(None, map(paragraph, cell.iter(W + "p")))) for cell in row.iter(W + "tc")]
                out.append("| " + " | ".join(cells) + " |")
    return "\n\n".join(out)


def read_text(path: Path) -> str:
    if not path.is_file():
        fail(f"No such file: {path}")
    if path.suffix.lower() not in SUFFIXES:
        fail(f"{path}: give a .md, .tex, .txt or .docx file")
    if path.suffix.lower() == ".docx":
        return docx_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def to_plain(text: str) -> str:
    """Prose without markup. Placeholders, citations, cross-references, URLs and LaTeX commands
    are blanked, so that the year in a citation key or the number of a figure is not read as a
    result and the words of a placeholder are not read as the manuscript's."""
    for pattern in (*(p for _, p in PLACEHOLDERS[:5]), TEX_CITE, PANDOC_GROUP, PANDOC_KEY, NUMERIC_CITE, NOISE,
                    TEX_COMMAND):
        text = pattern.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ").replace("\u2010", "-").replace("\u2011", "-")
    return MD_MARKS.sub("", text)


def count_words(plain: str) -> int:
    return len(WORD.findall(plain))


def open_section(doc: dict, state: dict, name: str, title: str, level: int, n: int) -> None:
    title = re.sub(r"\s+", " ", re.sub(r"^\s*(?:\d+(?:\.\d+)*\.?|[IVX]+\.)\s+", "", to_plain(title))).strip(" :.")
    for flag, pattern in (("refs", REFS_TITLE), ("abstract", ABSTRACT_TITLE)):
        # A reference list or an abstract ends at the next heading of its own level or above. A
        # file named abstract.md is an abstract only until its first heading.
        if state[flag] is not None and (level <= state[flag] or state[flag] == 0):
            state[flag] = None
        if state[flag] is None and pattern.fullmatch(title.lower()):
            state[flag] = level
    doc["sections"].append({"title": title, "level": level, "file": name, "line": n, "own_words": 0,
                            "refs": state["refs"] is not None, "abstract": state["abstract"] is not None})


def add_line(doc: dict, name: str, n: int, text: str, table: bool = False, heading: bool = False) -> None:
    section = doc["sections"][-1]
    plain = to_plain(text)
    doc["lines"].append({"file": name, "n": n, "text": text, "plain": plain, "table": table, "heading": heading,
                         "refs": section["refs"], "abstract": section["abstract"]})
    if not (table or heading):
        section["own_words"] += count_words(plain)


def parse(paths: list[Path]) -> dict:
    """The manuscript as lines of visible text, each with its section. Code blocks and comments
    are left out of the text; "raw" keeps every line outside code for the placeholder search."""
    doc: dict = {"files": [], "lines": [], "sections": [], "raw": []}
    for path in paths:
        text = read_text(path)
        suffix = path.suffix.lower()
        tex, docx, name = suffix == ".tex", suffix == ".docx", str(path)
        doc["files"].append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        state = {"refs": None, "abstract": None}
        fence = comment = False
        skip_env, table_env = None, 0
        open_section(doc, state, name, path.stem, 0, 1)
        for number, raw in enumerate(text.splitlines(), 1):
            n = (number + 1) // 2 if docx else number          # in a .docx, the paragraph
            if not tex and FENCE.match(raw):
                fence = not fence
                continue
            if fence:
                continue
            line = re.sub(r"(?<!\\)%.*$", "", raw) if tex else raw
            if skip_env:
                skip_env = None if f"\\end{{{skip_env}}}" in line else skip_env
                continue
            if tex and VERBATIM.search(line):
                skip_env = VERBATIM.search(line).group(1)
                continue
            doc["raw"].append((name, n, raw))
            if tex:
                if "\\begin{abstract}" in line:
                    open_section(doc, state, name, "Abstract", 1, n)
                if "\\begin{thebibliography}" in line:
                    open_section(doc, state, name, "References", 1, n)
                closes = re.search(r"\\end\{(?:abstract|thebibliography)\}", line)
                table_env += len(TABLE_BEGIN.findall(line))
                table = table_env > 0
                table_env = max(0, table_env - len(TABLE_END.findall(line)))
                for pattern, replacement in TEX_SUBS:
                    line = pattern.sub(replacement, line)
                heading = HEADING_TEX.search(line)
                if heading:
                    add_line(doc, name, n, line[:heading.start()], table)
                    open_section(doc, state, name, heading.group(2), TEX_LEVEL[heading.group(1)], n)
                    add_line(doc, name, n, heading.group(2), heading=True)
                    line = line[heading.end():]
                add_line(doc, name, n, line, table)
                if closes:
                    open_section(doc, state, name, path.stem, 0, n)
                continue
            if comment:
                if "-->" not in line:
                    continue
                line, comment = line.split("-->", 1)[1], False
            line = re.sub(r"<!--.*?-->", "", line)
            if "<!--" in line:
                line, comment = line.split("<!--", 1)[0], True
            heading = HEADING_MD.match(line)
            named = None if heading else PLAIN_HEADING.fullmatch(re.sub(r"[*_#]", "", line).strip())
            if heading or named:
                title = heading.group(2) if heading else named.group(0)
                open_section(doc, state, name, title, len(heading.group(1)) if heading else 1, n)
                add_line(doc, name, n, title, heading=True)
            else:
                add_line(doc, name, n, line, line.lstrip().startswith("|"))
    if not any(line["plain"].strip() for line in doc["lines"]):
        fail("No text found in " + ", ".join(str(p) for p in paths))
    return doc


def where(line: dict) -> str:
    return f"{line['file']}:{line['n']}"


def finding(check: str, code: str, severity: str, message: str, places=()) -> dict:
    return {"check": check, "code": code, "severity": severity, "message": message, "where": list(places)}


def prose(doc: dict, tables: bool = True) -> list[dict]:
    """The lines the content checks read: no headings, no reference list."""
    return [line for line in doc["lines"] if not (line["heading"] or line["refs"]) and (tables or not line["table"])]


# ---------------------------------------------------------------------------------------------
# check: placeholders
# ---------------------------------------------------------------------------------------------

def check_placeholders(doc: dict, final: bool) -> list[dict]:
    out = []
    for name, n, raw in doc["raw"]:
        for code, pattern in PLACEHOLDERS:
            for m in pattern.finditer(raw):
                out.append(finding("placeholders", code, "error" if final else "warning",
                                   m.group(0).strip()[:160], [f"{name}:{n}"]))
            raw = pattern.sub(" ", raw)      # "[Citation needed: TBD]" is one placeholder, not two
    return out


# ---------------------------------------------------------------------------------------------
# check: numbers
# ---------------------------------------------------------------------------------------------

# An integer, a decimal (also ".05") or a percentage. Thousands separators are dropped, so 1,204
# and 1204 are one value. A digit glued to a word (COVID-19, top-5, 3D) is a name, not a number.
NUMBER = re.compile(
    r"(?<![\w.,])(?<![A-Za-z][-–])(?P<sign>[-−])?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
    r"(?P<pct>\s?%|\s+percent\b)?(?![\w]|[.,]\d)")
INEQUALITY = re.compile(r"(<=|>=|[≤≥⩽⩾]|(?<![-=<>])[<>])\s*$")
INEQUALITY_NORM = {"<=": "≤", ">=": "≥", "⩽": "≤", "⩾": "≥"}
INT = r"\d{1,3}(?:,\d{3})+|\d+"
FRACTION = rf"(?P<n>{INT})\s*(?:/|\bof\b|\bout of\b)\s*(?P<d>{INT})(?![\w/]|[.,]\d)"
FRACTION_THEN_PERCENT = re.compile(
    rf"(?<![\w.,/]){FRACTION}(?:\s+[A-Za-z][A-Za-z-]*){{0,3}}\s*[(\[,;]\s*(?P<p>\d+(?:\.\d+)?)\s?%")
PERCENT_THEN_FRACTION = re.compile(
    rf"(?<![\w.,])(?P<p>\d+(?:\.\d+)?)\s?%\s*(?:[A-Za-z][A-Za-z-]*\s+){{0,3}}[(\[]\s*(?:n\s*=\s*)?{FRACTION}")
LABEL = re.compile(r"((?:[A-Za-z][A-Za-z'’-]*\s+){0,2}[A-Za-z][A-Za-z'’-]*)\s*(?:=|:|\b(?:of|was|were|is|are)\b)\s*$")
LABEL_STOP = frozenset(
    "the a an of in on at to for with by from and or but as that which who this these those there it its their "
    "our we they when while where whereas than then also only both each all any some was were is are be been "
    "had has have after before during between among per vs versus respectively out one p".split())


def numbers_in(plain: str) -> list[dict]:
    out = []
    for m in NUMBER.finditer(plain):
        digits = m.group("num").replace(",", "")
        start, sign = m.start("num"), ""
        if m.group("sign"):
            # A hyphen after a number, a percent sign or a bracket joins a range: "0.91 -0.97".
            before = plain[:m.start("sign")].rstrip()
            if not before or not (before[-1].isdigit() or before[-1] in "%)"):
                start, sign = m.start("sign"), "-"
        ineq = INEQUALITY.search(plain[max(0, start - 4):start])
        token = sign + digits + ("%" if m.group("pct") else "")
        out.append({"token": token, "value": Decimal(sign + digits), "places": len(digits.partition(".")[2]),
                    "pct": bool(m.group("pct")), "start": start,
                    "bound": (INEQUALITY_NORM.get(ineq.group(1), ineq.group(1)) if ineq else "") + token})
    return out


def label_of(plain: str, start: int) -> str:
    """The words that name a number: "mean age" in "the mean age was 54.3"."""
    lead = plain[max(0, start - 60):start]
    if start > 60:
        lead = lead.partition(" ")[2]
    m = LABEL.search(lead)
    if not m:
        return ""
    words = m.group(1).split()
    if len(words) == 1 and len(words[0]) == 1:
        return "" if words[0].lower() == "p" else words[0]      # N and n are different quantities
    words = [w.lower() for w in words]
    while words and words[0] in LABEL_STOP:
        words.pop(0)
    while words and words[-1] in LABEL_STOP:
        words.pop()
    return " ".join(words)


def rounds_to(fine: dict, coarse: dict) -> bool:
    """Is `coarse` the value `fine`, rounded to the precision `coarse` is written at?"""
    return abs(fine["value"] - coarse["value"]) <= Decimal(5).scaleb(-coarse["places"] - 1)


def check_numbers(doc: dict) -> tuple[list[dict], dict]:
    out, states = [], {"numbers": "checked"}
    found = []                          # (line, number, place)
    for line in prose(doc):
        for pattern in (FRACTION_THEN_PERCENT, PERCENT_THEN_FRACTION):
            for m in pattern.finditer(line["plain"]):
                n, d = (int(m.group(g).replace(",", "")) for g in ("n", "d"))
                stated = m.group("p")
                digits = len(stated.partition(".")[2])
                if d and n <= d and abs(Decimal(100 * n) / d - Decimal(stated)) > Decimal(5).scaleb(-digits - 1):
                    actual = f"{Decimal(100 * n) / d:.{max(digits, 1)}f}"
                    out.append(finding("numbers", "percent_mismatch", "error",
                                       f"{n}/{d} is {actual}%, written as {stated}%", [where(line)]))
        place = "abstract" if line["abstract"] else "table" if line["table"] else "text"
        found += [(line, number, place) for number in numbers_in(line["plain"])]

    # One value at two precisions. An integer and a decimal (12 and 12.0) are compared only as
    # percentages, because a bare integer is usually a count.
    by_value: dict = {}
    for line, number, _ in found:
        if number["pct"] or number["places"]:
            by_value.setdefault((number["value"], number["pct"]), {}).setdefault(number["places"], []).append((number, line))
    for forms in by_value.values():
        if len(forms) > 1:
            out.append(finding("numbers", "precision_variant", "warning", "one value at different precision: "
                               + ", ".join(f"{items[0][0]['token']} ({len(items)}×)" for items in forms.values()),
                               [where(items[0][1]) for items in forms.values()]))

    # A labelled quantity that has one value in one place and another value in another place. A
    # label with several values in one place (sensitivity of three models) is not compared.
    labelled: dict = {}
    for line, number, place in found:
        label = label_of(line["plain"], number["start"])
        if label:
            labelled.setdefault(label, {}).setdefault(place, []).append((line, number))
    conflicting = set()
    for label, places in labelled.items():
        single = [(place, items[0]) for place, items in places.items() if len({n["value"] for _, n in items}) == 1]
        for i, (place_a, (line_a, a)) in enumerate(single):
            for place_b, (line_b, b) in single[i + 1:]:
                if not (rounds_to(a, b) or rounds_to(b, a)):
                    conflicting.update({(where(line_a), a["token"]), (where(line_b), b["token"])})
                    out.append(finding("numbers", "value_conflict", "warning",
                                       f'"{label}" is {a["token"]} in the {place_a} and {b["token"]} in the {place_b}',
                                       [where(line_a), where(line_b)]))

    # Every number in the abstract should be in the main text or a table, at the same value or
    # as the value it was rounded from. Integers below 10 are skipped, because the text often
    # spells them, and so is a bound such as P < 0.01, which is not a value.
    abstract = [(line, n) for line, n, place in found if place == "abstract"]
    body = [n for _, n, place in found if place != "abstract"]
    if not any(s["abstract"] for s in doc["sections"]):
        states["abstract_numbers"] = "not_checked: no Abstract section found"
    elif not any(line["plain"].strip() for line in prose(doc) if not line["abstract"]):
        states["abstract_numbers"] = "not_checked: no main text was given to compare the abstract with"
    else:
        states["abstract_numbers"] = "checked"
        for line, number in abstract:
            if (not number["pct"] and not number["places"] and abs(number["value"]) < 10) \
                    or number["bound"] != number["token"] or (where(line), number["token"]) in conflicting:
                continue
            if not any(rounds_to(other, number) for other in body):
                out.append(finding("abstract_numbers", "abstract_number_not_in_body", "warning",
                                   f'{number["token"]} is in the abstract but not in the main text or tables',
                                   [where(line)]))
    return out, states


# ---------------------------------------------------------------------------------------------
# check: terms, abbreviations, spelling
# ---------------------------------------------------------------------------------------------

TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*")
# "data set" beside "dataset" is a variant; "any one" beside "anyone" is two different things.
FUNCTION_WORDS = frozenset(
    "the and for but nor not all any can may how now our its his her him them they with from into over under "
    "after more most some such than that this these those there where here when what which who whom whose "
    "every each both also only very much many few own same then once again further between through during "
    "before above below while about against because been being have has had does did would should could "
    "might must shall will were was are out off per via one two".split())
# Capital letters only: a name with a digit (CIFAR-10, IL-6, GPT-4) is not defined in brackets.
ABBR = r"[a-z]?[A-Z]{2,8}"
ABBR_DEFINED = re.compile(rf"\(\s*({ABBR})s?\s*\)")
ABBR_EXPANDED = re.compile(rf"(?<![A-Za-z0-9\\-])({ABBR})s?\s+\(([a-z][^()\d]{{5,80}})\)")
ABBR_USED = re.compile(rf"(?<![A-Za-z0-9\\-])({ABBR})s?(?![A-Za-z0-9]|-[A-Z0-9])")
# So common that no journal asks for a definition.
ABBR_KNOWN = frozenset("DNA RNA PCR USA UK EU UN WHO FDA HIV AIDS PDF URL HTML API CPU GPU ID OK AM PM BC AD "
                       "USD EUR GBP ISO IEEE ACM NA AND OR NOT".split())

_IZE = ("random standard character optim general normal minim maxim util summar organ recogn emphas hypothes "
        "categor visual real special local central priorit parameter regular stabil initial token penal synthes "
        "harmon hospital immun steril crystall polar").split()
_OR = "color behavior favor tumor labor neighbor honor vapor odor flavor".split()
_WORDS = (("center", "centre"), ("centers", "centres"), ("centered", "centred"), ("fiber", "fibre"),
          ("fibers", "fibres"), ("modeling", "modelling"), ("modeled", "modelled"), ("labeling", "labelling"),
          ("labeled", "labelled"), ("signaling", "signalling"), ("fetal", "foetal"), ("fetus", "foetus"),
          ("anemia", "anaemia"), ("hemoglobin", "haemoglobin"), ("hemorrhage", "haemorrhage"),
          ("pediatric", "paediatric"), ("leukemia", "leukaemia"), ("edema", "oedema"), ("estrogen", "oestrogen"),
          ("diarrhea", "diarrhoea"), ("aging", "ageing"), ("artifact", "artefact"), ("artifacts", "artefacts"),
          ("sulfur", "sulphur"))
_ENDINGS = "(?:e|ed|es|ing|ation|ations|er|ers)"
_OR_ENDINGS = "(?:s|ed|ing|al|able|ably|hood|ite|ites)?"
# The suffixes are listed one by one because "analyses", "organism", "characteristic" and
# "optimism" are spelled alike everywhere and must not count as UK spelling.
SPELLING = {
    "US": re.compile(rf"\b(?:(?:{'|'.join(_IZE)})iz{_ENDINGS}|(?:analy|cataly|paraly)z(?:e|ed|es|ing|er|ers)"
                     rf"|(?:{'|'.join(_OR)}){_OR_ENDINGS}|{'|'.join(us for us, _ in _WORDS)})\b", re.I),
    "UK": re.compile(rf"\b(?:(?:{'|'.join(_IZE)})is{_ENDINGS}|(?:analy|cataly|paraly)s(?:e|ed|ing|er|ers)"
                     rf"|(?:{'|'.join(w + 'u' + 'r' for w in (x[:-1] for x in _OR))}){_OR_ENDINGS}"
                     rf"|{'|'.join(uk for _, uk in _WORDS)})\b", re.I),
}


def starts_sentence(plain: str, start: int) -> bool:
    lead = plain[:start].rstrip(" \t\"'“‘([")
    return not lead.strip("-*•>#0123456789.) \t") or lead[-1] in ".!?:|&"


def check_terms(doc: dict) -> list[dict]:
    lines = prose(doc, tables=False)
    forms: dict = {}        # hyphenation: letters only -> {form as written, lower case: [lines]}
    cases: dict = {}        # capitalisation: lower case -> {form as written: [lines]}
    tokens = [(line, list(TOKEN.finditer(line["plain"]))) for line in lines]
    for line, found in tokens:
        for m in found:
            word = m.group(0)
            forms.setdefault(word.lower().replace("-", ""), {}).setdefault(word.lower(), []).append(line)
            if not starts_sentence(line["plain"], m.start()):
                cases.setdefault(word.lower(), {}).setdefault(word, []).append(line)
    for line, found in tokens:
        for a, b in zip(found, found[1:]):
            first, second = a.group(0).lower(), b.group(0).lower()
            if line["plain"][a.end():b.start()] == " " and first + second in forms \
                    and first.isalpha() and second.isalpha() and min(len(first), len(second)) >= 3 \
                    and not {first, second} & FUNCTION_WORDS:
                forms[first + second].setdefault(f"{first} {second}", []).append(line)
    out = []

    def report(variants: dict) -> None:
        ordered = sorted(variants.items(), key=lambda item: -len(item[1]))
        out.append(finding("terms", "term_variant", "warning",
                           "one term, written " + " and ".join(f'"{form}" ({len(at)}×)' for form, at in ordered),
                           [where(at[0]) for _, at in ordered]))

    for key, variants in forms.items():
        # The solid form beside a hyphenated or a spaced one. A spaced and a hyphenated form
        # alone are grammar ("in the long term", "long-term outcome"), not a variant.
        if key in variants and len(variants) > 1 and len(key) >= 5:
            report(variants)
    for variants in cases.values():
        capitals = {form: sum(c.isupper() for c in form) for form in variants}
        if len(variants) > 1 and max(capitals.values()) >= 2 \
                and all(capitals[form] or len(form) >= 5 for form in variants):
            report(variants)
    return out


def expands(abbreviation: str, phrase: str) -> bool:
    """Could `phrase` be the long form of `abbreviation`: same first letter, letters in order?"""
    letters = iter(re.sub(r"[^a-z]", "", phrase.lower()))
    wanted = re.sub(r"[^a-z]", "", abbreviation.lower())
    return len(phrase.split()) >= 2 and phrase[0].lower() == wanted[:1] and all(c in letters for c in wanted)


def check_abbreviations(doc: dict) -> list[dict]:
    """An abbreviation is defined by "(ABC)" after its long form, or by "ABC (long form)". The
    abstract and the main text are checked apart, because each has to define its own."""
    defined: dict = {"abstract": {}, "main": {}}
    used: dict = {"abstract": {}, "main": {}}
    for index, line in enumerate(prose(doc, tables=False)):
        scope, text = "abstract" if line["abstract"] else "main", line["plain"]
        for pattern in (ABBR_DEFINED, ABBR_EXPANDED):
            for m in pattern.finditer(text):
                if pattern is ABBR_DEFINED or expands(m.group(1), m.group(2)):
                    defined[scope].setdefault(m.group(1), []).append(((index, m.start()), line))
                    text = text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]
        for m in ABBR_USED.finditer(text):
            used[scope].setdefault(m.group(1), []).append(((index, m.start()), line))
    out = []
    for scope in ("abstract", "main"):
        place = "the abstract" if scope == "abstract" else "the main text"
        for abbr in sorted(set(defined[scope]) | set(used[scope])):
            if abbr in ABBR_KNOWN or re.fullmatch(r"[IVX]+", abbr):
                continue
            defs = sorted(defined[scope].get(abbr, []), key=lambda d: d[0])
            uses = used[scope].get(abbr, [])
            if not defs:
                if len(uses) >= 2:
                    only = "; it is defined only in the abstract" if scope == "main" and abbr in defined["abstract"] else ""
                    out.append(finding("abbreviations", "abbreviation_not_defined", "warning",
                                       f"{abbr} is used {len(uses)} times in {place} and never defined there{only}",
                                       [where(uses[0][1])]))
                continue
            if len(defs) > 1:
                out.append(finding("abbreviations", "abbreviation_defined_twice", "warning",
                                   f"{abbr} is defined {len(defs)} times in {place}", [where(d[1]) for d in defs]))
            if uses and uses[0][0] < defs[0][0]:
                out.append(finding("abbreviations", "abbreviation_used_before_definition", "warning",
                                   f"{abbr} is used in {place} before it is defined",
                                   [where(uses[0][1]), where(defs[0][1])]))
            if not uses and len(defs) == 1:
                out.append(finding("abbreviations", "abbreviation_defined_not_used", "warning",
                                   f"{abbr} is defined in {place} and not used again there", [where(defs[0][1])]))
    return out


def check_spelling(doc: dict) -> list[dict]:
    hits: dict = {"US": [], "UK": []}
    for line in prose(doc, tables=False):
        for side, pattern in SPELLING.items():
            for m in pattern.finditer(line["plain"]):
                # A capitalised word inside a sentence is part of a name: World Health Organization.
                if m.group(0)[0].islower() or starts_sentence(line["plain"], m.start()):
                    hits[side].append((m.group(0), line))
    if not (hits["US"] and hits["UK"]):
        return []
    minority = "UK" if len(hits["UK"]) <= len(hits["US"]) else "US"
    words = Counter(word.lower() for word, _ in hits[minority])
    return [finding("spelling", "mixed_spelling", "warning",
                    f"{len(hits['US'])} US and {len(hits['UK'])} UK spellings; the {minority} ones are "
                    + ", ".join(f"{word} ({count}×)" for word, count in words.most_common(12)),
                    list(dict.fromkeys(where(line) for _, line in hits[minority]))[:20])]


# ---------------------------------------------------------------------------------------------
# check: citations and word budget
# ---------------------------------------------------------------------------------------------

def citations_in(text: str, numeric: bool = False) -> list[str]:
    keys = [key.strip() for m in TEX_CITE.finditer(text) for key in m.group(1).split(",") if key.strip()]
    rest = TEX_CITE.sub(" ", text)
    keys += [m.group(1) for m in PANDOC_KEY.finditer(rest)
             if m.group(1).lower() != "new" and not m.group(1).lower().startswith(NOT_A_CITATION)]
    if numeric:
        keys += [re.sub(r"\s+", "", m.group(0)) for m in NUMERIC_CITE.finditer(PANDOC_GROUP.sub(" ", rest))]
    return keys


def check_citations(doc: dict, bib_paths: list[Path]) -> tuple[list[dict], str]:
    cited: dict = {}
    for line in doc["lines"]:
        if not line["refs"]:
            for key in citations_in(line["text"]):
                cited.setdefault(key, []).append(line)
    everything = cited.pop("*", None) is not None                       # \nocite{*}
    known, source = [], "the .bib"
    for path in bib_paths:
        if not path.is_file():
            fail(f"No such file: {path}")
        entries = re.finditer(r"@(\w+)\s*\{\s*([^,\s{}]+)\s*,", path.read_text(encoding="utf-8", errors="replace"))
        known += [m.group(2) for m in entries if m.group(1).lower() not in ("comment", "string", "preamble")]
    if not bib_paths:
        known = [key.strip() for _, _, raw in doc["raw"] for key in re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^{}]+)\}", raw)]
        source = "the \\bibitem list"
        if not known:
            return [], "not_checked: no .bib given"
    if not cited and not everything:
        return [], "not_checked: no \\cite or @key citations found; numbered and author-year citations cannot be matched"
    out = [finding("citations", "citation_not_in_bib", "error", f"{key} is cited but is not in {source}",
                   [where(line) for line in lines[:3]]) for key, lines in cited.items() if key not in set(known)]
    if not everything:
        out += [finding("citations", "bib_entry_not_cited", "warning", f"{key} is in {source} but never cited")
                for key in dict.fromkeys(known) if key not in cited]
    return out, "checked"


def section_words(doc: dict) -> tuple[list[dict], int]:
    """Words per heading, sub-sections included, and the total of the main text: everything
    outside the abstract and the reference list, and after a file's first heading (what comes
    before it is the title page or the LaTeX preamble)."""
    sections, out = doc["sections"], []
    with_headings = {s["file"] for s in sections if s["level"]}
    for i, section in enumerate(sections):
        words = section["own_words"]
        for later in sections[i + 1:] if section["level"] else ():
            if later["file"] != section["file"] or later["level"] <= section["level"]:
                break
            words += later["own_words"]
        if (words or section["level"]) and not section["refs"]:
            out.append({"title": section["title"], "level": section["level"], "file": section["file"],
                        "line": section["line"], "words": words})
    return out, sum(s["own_words"] for s in sections
                    if not (s["abstract"] or s["refs"] or (not s["level"] and s["file"] in with_headings)))


def parse_budget(text: str | None) -> list[tuple[str, int]]:
    out = []
    for part in filter(None, (p.strip() for p in (text or "").split(","))):
        name, _, limit = part.partition("=")
        if not name.strip() or not limit.strip().isdigit():
            fail(f'--budget: "{part}" is not NAME=WORDS; write it like "Abstract=250,Introduction=600"')
        out.append((name.strip(), int(limit)))
    return out


def check_budget(sections: list[dict], total: int, budget: list[tuple[str, int]]) -> tuple[list[dict], str]:
    if not budget:
        return [], "not_checked: no --budget given"
    out, state = [], "checked"
    for name, limit in budget:
        key = name.lower()
        if key in ("total", "main text"):
            title, words = "Main text", total
            sections.append({"title": "Total (main text)", "level": 0, "file": "", "line": 0, "words": total, "budget": limit})
        else:
            hits = sorted((s for s in sections if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", s["title"].lower())),
                          key=lambda s: (s["title"].lower() != key, s["level"], -s["words"]))
            if not hits:
                out.append(finding("word_budget", "budget_section_not_found", "warning",
                                   f'no section is called "{name}", so its budget of {limit} words was not checked'))
                state = f'not_checked: no section called "{name}"; the other budgets were checked'
                continue
            hits[0]["budget"] = limit
            title, words = hits[0]["title"], hits[0]["words"]
        if words > limit:
            out.append(finding("word_budget", "over_budget", "error",
                               f"{title} has {words} words; the budget is {limit} ({words - limit} over)"))
    return out, state


# ---------------------------------------------------------------------------------------------
# check: command and report
# ---------------------------------------------------------------------------------------------

CHECKS = (("placeholders", "Placeholders"), ("numbers", "Numbers"), ("abstract_numbers", "Abstract against main text"),
          ("terms", "Terms"), ("abbreviations", "Abbreviations"), ("spelling", "Spelling"),
          ("citations", "Citation keys"), ("word_budget", "Word budget"))


def cell(value) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).replace("|", "/")


def write_check_report(path: Path, result: dict) -> None:
    findings, summary = result["findings"], result["summary"]
    lines = ["# Manuscript check", "",
             ("Final check" if result["final"] else "Draft check") + f": {summary['errors']} errors, "
             f"{summary['warnings']} warnings, {summary['words']} words in "
             + ", ".join(f"`{f['path']}`" for f in result["files"]) + ".",
             "", "| Check | State | Errors | Warnings |", "|---|---|---|---|"]
    for key, title in CHECKS:
        mine = [f for f in findings if f["check"] == key]
        lines.append(f"| {title} | {result['checks'][key].replace('_', ' ')} | "
                     f"{sum(f['severity'] == 'error' for f in mine)} | {sum(f['severity'] == 'warning' for f in mine)} |")
    lines += ["", "An error has to be fixed. A warning has to be looked at: it may be intended. A check that is "
              "not checked says nothing about the manuscript. Locations are file:line; in a .docx, file:paragraph."]
    for key, title in CHECKS:
        mine = [f for f in findings if f["check"] == key]
        if mine:
            lines += ["", f"## {title}", "", "| | Finding | Where |", "|---|---|---|"]
            lines += [f"| {f['severity']} | {cell(f['message'])} | {cell(', '.join(f['where']))} |" for f in mine]
    lines += ["", "## Words per section", "", "| Section | Words | Budget |", "|---|---|---|"]
    lines += [f"| {'– ' * max(s['level'] - 1, 0)}{cell(s['title'])} | {s['words']} | {s.get('budget', '')} |"
              for s in result["sections"]]
    lines += ["", "Words are counted without tables, headings, citation markers and the reference list; a "
              "section includes its sub-sections. Total also leaves out the abstract and what precedes a file's "
              "first heading. Venues count differently, so compare with the venue's own rule.",
              "", "Not checked by this script: whether a number is right, whether a table and the text that "
              "describes it agree, whether a cited paper supports its sentence, and anything about meaning."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_check(args) -> int:
    doc = parse([Path(p) for p in args.files])
    budget = parse_budget(args.budget)
    findings = check_placeholders(doc, args.final)
    number_findings, states = check_numbers(doc)
    citation_findings, states["citations"] = check_citations(doc, [Path(p) for p in args.bib or []])
    sections, total = section_words(doc)
    budget_findings, states["word_budget"] = check_budget(sections, total, budget)
    findings += number_findings + check_terms(doc) + check_abbreviations(doc) + check_spelling(doc) \
        + citation_findings + budget_findings
    states.update({key: "checked" for key, _ in CHECKS if key not in states})
    errors = sum(f["severity"] == "error" for f in findings)
    summary = {"errors": errors, "warnings": len(findings) - errors,
               "placeholders": sum(f["check"] == "placeholders" for f in findings),
               "words": sum(s["own_words"] for s in doc["sections"] if not s["refs"]),
               "by_check": dict(Counter(f["check"] for f in findings)),
               "not_checked": {key: state.partition(": ")[2] for key, state in states.items() if state != "checked"}}
    result = {"tool": TOOL, "command": "check", "final": args.final, "files": doc["files"], "checks": states,
              "summary": summary, "sections": sections, "findings": findings}
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manuscript-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_check_report(out_dir / "manuscript-check.md", result)
    print(json.dumps({"mode": "final" if args.final else "draft", **summary,
                      "report": str(out_dir / "manuscript-check.md")}, indent=2, ensure_ascii=False))
    return 1 if args.final and errors else 0


# ---------------------------------------------------------------------------------------------
# diff: a text before and after a revision
# ---------------------------------------------------------------------------------------------

SENTENCE_END = re.compile(r"[.!?][\"')\]}”’]*\s+(?=[\"'“‘(\[]?[A-Z0-9\\@])")
NO_SENTENCE_END = re.compile(r"\b(?:e\.g|i\.e|et al|vs|cf|Figs?|Eqs?|Refs?|Tab|Dr|Prof|approx|resp|ca|St|Mr|Mrs|Ms)\.$")
ALPHA = re.compile(r"[A-Za-z][A-Za-z'’-]*")
HEDGE = re.compile(
    r"\b(?:may|might|could|suggests?|suggested|suggesting|appears?|appeared|seems?|seemed|likely|possibly|possible"
    r"|probably|probable|perhaps|potentially|potential|approximately|roughly|nearly|almost|around(?=\s+\d)"
    r"|about(?=\s+\d)|some(?=\s+\d)|partly|partially|in part|to some extent|tends? to|tended to|preliminary|presumably"
    r"|apparently|generally|typically|often|usually|sometimes|largely|mostly|relatively|somewhat|indicates?"
    r"|indicated|consistent with|speculate|hypothesi[sz]ed?)\b|[~≈](?=\s*\d)")
INTENSIFIER = re.compile(
    r"\b(?:clearly|strongly|significantly|substantially|dramatically|remarkably|markedly|highly|very|extremely"
    r"|greatly|considerably|robustly|definitively|conclusively|undoubtedly|certainly|unequivocally|always"
    r"|proves?|proved|proven|demonstrates?|demonstrated|confirms?|confirmed|establish(?:es|ed)?|novel"
    r"|unprecedented|superior|state-of-the-art|groundbreaking|crucial|pivotal|vital|the first to)\b")
NEGATION = re.compile(r"\b(?:not|no|never|none|neither|nor|without|cannot|fail(?:s|ed)? to|lack(?:s|ed|ing)?"
                      r"|absence of|absent)\b|n['’]t\b")
UP = re.compile(r"\b(?:higher|greater|larger|more|above|increas(?:e|es|ed|ing)|rise|rises|rose|risen|gain(?:s|ed)?"
                r"|improv(?:e|es|ed|ing|ement)|better|longer|faster|outperform(?:s|ed)?|exceed(?:s|ed)?|superior)\b")
DOWN = re.compile(r"\b(?:lower|less|fewer|smaller|below|decreas(?:e|es|ed|ing)|reduc(?:e|es|ed|ing|tion)"
                  r"|declin(?:e|es|ed|ing)|drop(?:s|ped)?|fell|falls?|worse|worsen(?:s|ed|ing)?|shorter|slower"
                  r"|inferior|underperform(?:s|ed)?)\b")


def sentences(doc: dict) -> list[dict]:
    """The text as sentences. A heading, a table row and a list item are each one unit. The
    reference list is left out."""
    texts, paragraph = [], []

    def flush() -> None:
        text = re.sub(r"\s+", " ", " ".join(paragraph)).strip()
        paragraph.clear()
        start = 0
        for m in SENTENCE_END.finditer(text):
            if not NO_SENTENCE_END.search(text[start:m.start() + 1]):
                texts.append(text[start:m.end()].strip())
                start = m.end()
        texts.append(text[start:].strip())

    for line in doc["lines"]:
        if line["refs"]:
            continue
        if line["heading"] or line["table"] or not line["text"].strip():
            flush()
            texts.append(re.sub(r"\s+", " ", line["text"]).strip())
        else:
            if LIST_ITEM.match(line["text"]):
                flush()
            paragraph.append(line["text"])
    flush()
    out = []
    for text in filter(None, texts):
        plain = to_plain(text)
        words = tuple(w.lower() for w in ALPHA.findall(plain))
        out.append({"text": text, "low": plain.lower(), "words": words, "set": frozenset(words),
                    "numbers": [n["bound"] for n in numbers_in(plain)], "cites": citations_in(text, numeric=True)})
    return out


def align(before: list[dict], after: list[dict]) -> list:
    """For each sentence before, the index of the sentence it became: one with the same words
    first, then the one sharing most words (at least half of all the words of the two). None when
    nothing is close enough to compare."""
    match: list = [None] * len(before)
    same: dict = {}
    for j, unit in enumerate(after):
        same.setdefault(unit["words"], []).append(j)
    for i, unit in enumerate(before):
        if same.get(unit["words"]):
            match[i] = same[unit["words"]].pop(0)
    taken = {j for j in match if j is not None}
    free = [j for j in range(len(after)) if j not in taken]
    for i, unit in enumerate(before):
        if match[i] is not None or not unit["set"]:
            continue
        best, best_score = None, 0.0
        for j in free:
            shared = len(unit["set"] & after[j]["set"])
            score = shared / len(unit["set"] | after[j]["set"]) if shared else 0.0
            if score > best_score or (score and score == best_score and abs(j - i) < abs(best - i)):
                best, best_score = j, score
        if best is not None and best_score >= 0.5:
            match[i] = best
            free.remove(best)
    return match


def compare(before: list[dict], after: list[dict]) -> dict:
    match = align(before, after)
    matched = {j for j in match if j is not None}
    alone_before = [u for i, u in enumerate(before) if match[i] is None]
    alone_after = [u for j, u in enumerate(after) if j not in matched]
    numbers: dict = {"changed": [], "reordered": [], "disappeared": [], "appeared": []}
    citations: dict = {"dropped": [], "added": [], "moved": []}
    wording: dict = {"hedges_removed": [], "intensifiers_added": [], "negation_changed": [], "direction_changed": []}
    gone_values, new_values, lost, gained = Counter(), Counter(), [], []
    edited = 0
    for i, j in enumerate(match):
        if j is None:
            continue
        b, a = before[i], after[j]
        pair = {"before": b["text"], "after": a["text"]}
        edited += b["text"] != a["text"]
        if b["numbers"] != a["numbers"]:
            gone = sorted((Counter(b["numbers"]) - Counter(a["numbers"])).elements())
            new = sorted((Counter(a["numbers"]) - Counter(b["numbers"])).elements())
            if gone or new:
                numbers["changed"].append({"before_values": gone, "after_values": new, **pair})
                gone_values.update(gone)
                new_values.update(new)
            else:                        # the same values in another order: they may have traded places
                numbers["reordered"].append({"before_values": b["numbers"], "after_values": a["numbers"], **pair})
        lost += [(key, pair) for key in (Counter(b["cites"]) - Counter(a["cites"])).elements()]
        gained += [(key, pair) for key in (Counter(a["cites"]) - Counter(b["cites"])).elements()]
        if b["words"] == a["words"]:
            continue
        low_b, low_a = b["low"], a["low"]
        hedges, strong = (HEDGE.findall(low_b), HEDGE.findall(low_a)), (INTENSIFIER.findall(low_b), INTENSIFIER.findall(low_a))
        if len(hedges[1]) < len(hedges[0]):
            wording["hedges_removed"].append({"words": sorted((Counter(hedges[0]) - Counter(hedges[1])).elements()), **pair})
        if len(strong[1]) > len(strong[0]):
            wording["intensifiers_added"].append({"words": sorted((Counter(strong[1]) - Counter(strong[0])).elements()), **pair})
        negations = NEGATION.findall(low_b), NEGATION.findall(low_a)
        if len(negations[0]) != len(negations[1]):
            wording["negation_changed"].append({"words": [*negations[0], "→", *negations[1]], **pair})
        up, down = (UP.findall(low_b), UP.findall(low_a)), (DOWN.findall(low_b), DOWN.findall(low_a))
        # Only a clean flip counts: "higher" became "lower", with no word of the other kind beside it.
        if (up[0] and down[1] and not up[1] and not down[0]) or (down[0] and up[1] and not down[1] and not up[0]):
            wording["direction_changed"].append({"words": [*(up[0] or down[0]), "→", *(up[1] or down[1])], **pair})

    def first_with(units: list[dict], field: str, value: str) -> str:
        return next((u["text"] for u in units if value in u[field]), "")

    count_before = Counter(x for u in before for x in u["numbers"])
    count_after = Counter(x for u in after for x in u["numbers"])
    for value in sorted(set(count_before) | set(count_after)):
        net = count_after[value] - count_before[value]
        if -net - gone_values[value] > 0:
            numbers["disappeared"].append({"value": value, "times": -net - gone_values[value], "before":
                                           first_with(alone_before, "numbers", value) or first_with(before, "numbers", value)})
        if net - new_values[value] > 0:
            numbers["appeared"].append({"value": value, "times": net - new_values[value], "after":
                                        first_with(alone_after, "numbers", value) or first_with(after, "numbers", value)})
    cited_before = Counter(k for u in before for k in u["cites"])
    cited_after = Counter(k for u in after for k in u["cites"])
    for key in sorted(set(cited_before) | set(cited_after)):
        entry = {"citation": key, "times_before": cited_before[key], "times_after": cited_after[key]}
        if cited_after[key] < cited_before[key]:
            citations["dropped"].append({**entry, "before": next((p["before"] for k, p in lost if k == key), "")
                                         or first_with(alone_before, "cites", key)})
        elif cited_after[key] > cited_before[key]:
            citations["added"].append({**entry, "after": next((p["after"] for k, p in gained if k == key), "")
                                       or first_with(alone_after, "cites", key)})
    for key, pair in lost:
        if cited_after[key] >= cited_before[key]:       # cited as often as before, but not in this sentence
            now_in = next((p["after"] for k, p in gained if k == key), "") or first_with(alone_after, "cites", key)
            citations["moved"].append({"citation": key, **pair, "now_in": now_in})
    return {"sentences": {"before": len(before), "after": len(after), "unchanged": len(matched) - edited, "edited": edited,
                          "without_counterpart_before": len(alone_before), "without_counterpart_after": len(alone_after)},
            "numbers": numbers, "citations": citations, "wording": wording,
            "not_compared": {"before": [u["text"] for u in alone_before], "after": [u["text"] for u in alone_after]}}


DIFF_REPORT = (
    ("numbers", "Numbers", "No number changed.", (
        ("changed", "Changed in a sentence", "The values on the left left the sentence; those on the right entered it."),
        ("reordered", "Same values, other order", "Check that each value still belongs to the same quantity."),
        ("disappeared", "Disappeared", "Values that are in the text less often than before."),
        ("appeared", "Appeared", "Values that are in the text more often than before."))),
    ("citations", "Citations", "No citation changed.", (
        ("dropped", "Dropped", "Cited less often than before."),
        ("added", "Added", "Cited more often than before."),
        ("moved", "Moved to another sentence", "Still cited, but no longer in the sentence it supported. "
                                               "Before: where it was. After: where it is now."))),
    ("wording", "Wording that can change the meaning", "None found in the sentences that could be compared.", (
        ("hedges_removed", "Hedges removed", "The sentence claims more than before."),
        ("intensifiers_added", "Intensifiers added", "The sentence claims more than before."),
        ("negation_changed", "Negation changed", "Read both sentences: one may say the opposite."),
        ("direction_changed", "Direction changed", "An increase became a decrease, or the reverse."))),
)


def write_diff_report(path: Path, result: dict) -> None:
    def clip(text: str) -> str:
        text = cell(text)
        return text if len(text) <= 240 else text[:237] + "…"

    def what(row: dict) -> str:
        if "before_values" in row:
            return f"{', '.join(row['before_values']) or 'nothing'} → {', '.join(row['after_values']) or 'nothing'}"
        if "value" in row:
            return f"{row['value']} ({row['times']}×)"
        if "times_before" in row:
            return f"{row['citation']} ({row['times_before']} → {row['times_after']})"
        return row.get("citation") or (" " if "→" in row["words"] else ", ").join(row["words"])

    s = result["sentences"]
    lines = ["# Revision check", "", f"`{result['before']['path']}` → `{result['after']['path']}`", "",
             f"{s['before']} sentences before, {s['after']} after: {s['unchanged']} unchanged, {s['edited']} edited, "
             f"{s['without_counterpart_before']} removed or rewritten too far to compare, "
             f"{s['without_counterpart_after']} new."]
    for group, title, nothing, parts in DIFF_REPORT:
        lines += ["", f"## {title}"] + ([] if any(result[group].values()) else ["", nothing])
        for key, subtitle, note in parts:
            rows = result[group][key]
            if rows:
                lines += ["", f"### {subtitle} ({len(rows)})", "", note, "", "| What | Before | After |", "|---|---|---|"]
            for row in rows:
                after = (row["now_in"] or "(not in a sentence that could be compared)") if "now_in" in row else row.get("after", "")
                lines.append(f"| {cell(what(row))} | {clip(row.get('before', ''))} | {clip(after)} |")
    for title, rows in (("Sentences before with no counterpart after", result["not_compared"]["before"]),
                        ("Sentences after with no counterpart before", result["not_compared"]["after"])):
        if rows:
            lines += ["", f"## {title} ({len(rows)})", "", "Not compared: read these yourself.", ""]
            lines += [f"- {clip(text)}" for text in rows[:40]]
            lines += [f"- … and {len(rows) - 40} more, in the JSON file"] if len(rows) > 40 else []
    lines += ["", "Not checked by this script: numbers written as words, units, and any change of meaning that "
              "keeps the numbers, the citations and the listed words. The reference list is not compared."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_diff(args) -> int:
    docs = [parse([Path(p)]) for p in (args.before, args.after)]
    result = {"tool": TOOL, "command": "diff", "before": docs[0]["files"][0], "after": docs[1]["files"][0],
              **compare(sentences(docs[0]), sentences(docs[1]))}
    counts = {group: {key: len(rows) for key, rows in result[group].items()} for group in ("numbers", "citations", "wording")}
    result["numbers_or_citations_changed"] = sum(counts["numbers"].values()) + sum(counts["citations"].values())
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "revision-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_diff_report(out_dir / "revision-check.md", result)
    print(json.dumps({"sentences": result["sentences"], **counts,
                      "numbers_or_citations_changed": result["numbers_or_citations_changed"],
                      "report": str(out_dir / "revision-check.md")}, indent=2, ensure_ascii=False))
    return 1 if args.strict and result["numbers_or_citations_changed"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Mechanical checks on a manuscript and on a revision of one.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="Placeholders, numbers, terms, citation keys and words per section")
    p.add_argument("files", nargs="+", help="The manuscript: .md, .tex, .txt or .docx, in reading order")
    p.add_argument("--bib", action="append", help="The bibliography the citation keys must be in (repeatable)")
    p.add_argument("--final", action="store_true", help="Placeholders are errors; exit 1 when there is any error")
    p.add_argument("--budget", help='Word limits per section: "Abstract=250,Introduction=600,Total=3500"')
    p.add_argument("--out", default="writing", help="Output folder (default: writing)")
    p = sub.add_parser("diff", help="What a revision changed: numbers, citations, hedges, negations")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--strict", action="store_true", help="Exit 1 when a number or a citation changed")
    p.add_argument("--out", default="writing", help="Output folder (default: writing)")
    args = parser.parse_args()
    return cmd_check(args) if args.command == "check" else cmd_diff(args)


if __name__ == "__main__":
    sys.exit(main())
