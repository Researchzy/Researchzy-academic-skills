#!/usr/bin/env python3
"""Check a submission package against the venue's requirements and the authors' record.

  check_package.py paper.md --package submission/example-journal          a draft run
  check_package.py paper.tex --package submission/example-journal --final  placeholders fail
  check_package.py --authors submission/example-journal/authors.json --author-block

The package folder holds requirements.json, authors.json and the documents, found by name:
cover-letter.*, title-page.*, highlights.*, and any other .md, .tex, .txt or .docx file, which is
read for statements. The manuscript is .md, .tex, .txt or .docx (paragraphs count as lines).

Every check is pass, fail or not_checked:

  limits        title, abstract and main-text words; title characters; keywords, figures,
                tables, display items and references; highlights and characters per highlight;
                FILE_words or FILE_characters for a package file. A limit without a source and
                a date read is not_checked. The main text runs from the first section heading
                after the abstract to the reference list, headings included, without tables,
                captions, end statements, appendices, citation markers and inline maths; a limit
                adds parts back with "include"
  statements    each required statement under one of its usual headings; empty or still a
                placeholder counts as missing
  files         required files with an allowed extension and size; deliverables required,
                optional or not_accepted
  placeholders  [Evidence needed: …], [Citation needed: …], [Author input needed: …]; they fail
                a --final run
  agreement     with authors.json: title, authors and their order, affiliations, corresponding
                email; CRediT roles; initials in the contributions statement; funders and grant
                numbers, ethics and registration ids; competing-interest statements
  letter        stated counts and sample sizes against the measured ones; sentences that repeat
                the abstract; priority words for the authors to justify or remove

Writes report.md (default: in the package folder) and prints JSON. Exit codes: 0; 1 when a check
fails; 2 for a usage error or a file that cannot be read. --author-block prints a title page's
author line with affiliations numbered in order of first appearance.

Standard library only. Portions are derived from MIT-licensed code: see LICENSE-MIT.txt next to
this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

TOOL = "researchzy-submission"
TEXT_SUFFIXES = (".md", ".markdown", ".txt", ".tex", ".docx")
WORKING_FILES = ("requirements.json", "authors.json", "report.md", "anonymity.md", "reviewer-candidates.json")
ROLES = {"letter": ("cover-letter", "coverletter"), "title_page": ("title-page", "titlepage"), "highlights": ("highlights",)}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
RUN_IN_LEVEL = 9                 # the "level" of a run-in label such as "**Funding:** …"
SPECIAL = {"abstract", "keywords", "statement", "references", "captions", "supplement"}
PARTS = {"abstract": "abstract", "captions": "captions", "statements": "statement", "tables": "tables",
         "references": "references"}
WORD_TOLERANCE = 0.05            # word counters disagree by a few per cent (at least 5 words); a working value
REPEAT = 0.8                     # share of the shorter sentence found, in order, in the other
MIN_SENTENCE = 6                 # shorter sentences ("Dear Editor,") are not compared

# The CRediT contributor roles: a published taxonomy (ANSI/NISO Z39.104), not a venue's rule.
CREDIT = ("Conceptualization", "Data curation", "Formal analysis", "Funding acquisition", "Investigation",
          "Methodology", "Project administration", "Resources", "Software", "Supervision", "Validation",
          "Visualization", "Writing – original draft", "Writing – review & editing")
NOT_CREDIT = {"statistical analysis": "Formal analysis", "data analysis": "Formal analysis",
              "study design": "Conceptualization or Methodology", "data collection": "Investigation or Data curation",
              "writing": "Writing – original draft or Writing – review & editing",
              "manuscript writing": "Writing – original draft", "editing": "Writing – review & editing",
              "critical revision": "Writing – review & editing", "figure preparation": "Visualization"}

# Headings under which each statement is found, matched against the whole heading in lower case.
STATEMENTS = {
    "author_contributions": r"authors?'? ?s?'? ?contributions?(?: statement)?|contributions of (?:the )?authors|"
                            r"credit(?: authorship)?(?: contributions?)?(?: statement| roles)?|"
                            r"contributor(?:ship)? (?:statement|roles?)|author statement",
    "competing_interests": r"(?:declarations?|statements?|disclosures?) of (?:competing |conflicting )?interests?|"
                           r"competing interests?(?: statement)?|conflicts? of interests?(?: statement| disclosures?)?|"
                           r"conflicting interests?|disclosures?",
    "funding": r"funding(?: sources?| statement| information)?|financial support|grant support|sources? of funding|"
               r"role of the funding source",
    "ethics": r"ethic(?:s|al)(?: approval| statement| considerations| declarations?)?(?: and (?:informed )?consent"
              r"(?: to participate)?)?|(?:informed )?consent(?: to participate| statement)?|"
              r"institutional review board statement",
    "data_availability": r"data(?: and (?:code|materials?))? availability(?: statement)?|data sharing(?: statement)?|"
                         r"availability of data(?: and (?:materials?|code))?|data access(?: statement)?",
    "code_availability": r"(?:code|software)(?: and data)? availability(?: statement)?|availability of code",
    "ai_use": r"(?=.*\b(?:ai|artificial intelligence|large language models?|llms?)\b)"
              r"(?=.*\b(?:use|usage|disclosure|statement|declaration)\b).{0,120}",
    "acknowledgements": r"acknowledge?ments?",
}
SECTION_KINDS = (
    ("abstract", r"abstract|summary"),
    ("keywords", r"key ?words?"),
    ("references", r"references?(?: list| and notes)?|bibliography|literature cited|works cited"),
    ("captions", r"(?:figures?|tables?)(?: and tables?)?(?: legends?| captions?| titles?)?|list of (?:figures|tables)"),
    ("supplement", r"(?:supplement(?:ary|al)?|supporting|extended data)\b.*|append(?:ix|ices)\b.*"),
    ("front", r"highlights|key points|significance(?: statement)?|graphical abstract|"
              r"(?:plain language|lay|author) summary|abbreviations"),
    ("statement", r"declarations?|statements and declarations|additional information|(?:end|back) ?matter"),
)
BODY_NAMES = re.compile(r"introduction|background|(?:(?:materials?|patients|subjects|participants) and )?methods?|"
                        r"methodology|results?(?: and discussion)?|discussion|conclusions?|related work|limitations")

FENCE = re.compile(r"^\s*(```|~~~)")
MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
RUN_IN = re.compile(r"^\s*(?:\*\*|__)\s*(.{3,80}?)\s*(?:\*\*|__)\s*(.*)$")
PLAIN_RUN_IN = re.compile(r"^\s*([A-Z][^:.!?*_|]{2,70}):\s+(\S.*)$")
CAPTION = re.compile(r"^\s*(?:\*\*|__)?\s*(Figure|Fig\.?|Table)\s+(S?\d+)\s*(?:[.:|]|\*\*|__)", re.I)
MENTION = re.compile(r"\b(Figure|Fig\.|Table)\s+(\d+)")
BULLET = re.compile(r"^\s*(?:[-*+•–]|\d+[.)]|\[\d+\]|\\item)\s+")
TEX_COMMENT = re.compile(r"(?<!\\)%.*$")
TEX_HEADING = re.compile(r"\\(section|subsection|subsubsection|paragraph)\*?\s*(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
TEX_LEVEL = {"section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}
TEX_ENV = re.compile(r"\\(begin|end)\{(\w+)\*?\}")
TEX_TITLE = re.compile(r"\\title\s*(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
TEX_CITE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?\s*(?:\[[^\]]*\]\s*)*\{([^{}]*)\}")
ENV_HEADINGS = {"abstract": "abstract", "keyword": "keywords", "keywords": "keywords", "thebibliography": "references",
                "acks": "acknowledgements", "acknowledgments": "acknowledgements", "acknowledgements": "acknowledgements"}
FLOATS = {"figure": "figure", "sidewaysfigure": "figure", "table": "table", "longtable": "table", "sidewaystable": "table"}
NOT_WORDS = re.compile(
    r"\\(?:[A-Za-z]*cite[A-Za-z]*|ref|eqref|autoref|[cC]ref|pageref|label|includegraphics|input|include|bibliography\w*"
    r"|begin|end|vspace|hspace)\*?(?:\s*\[[^\]]*\])*(?:\s*\{[^{}]*\})*|\$[^$]*\$|\[-?@[^\]]*\]|\[\d+(?:\s*[-–,]\s*\d+)*\]"
    r"|!\[[^\]]*\]\([^)]*\)|\]\([^)\s]*\)|https?://\S+|<!--.*?-->|\\[A-Za-z]+\*?")
WORD = re.compile(r"[^\W_]+(?:(?:[-'’./]|,(?=\d{3}))[^\W_]+)*")       # "1,240" is one word
NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'“(\[]?[A-Z0-9])")
PLACEHOLDER = re.compile(r"\[\s*(?:Evidence|Citation|Author input) needed\b[^\]]*\]", re.I)
STUB = re.compile(PLACEHOLDER.pattern + r"|\b(?:TODO|TBD)\b", re.I)
INITIALS = re.compile(r"(?<![\w.])(?:[A-Z]\.[ -]?){2,5}")
DOTLESS = re.compile(r"\b[A-Z]{2,4}\b")
ID_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9./_-]{2,}[A-Za-z0-9]")
COI_WORDS = re.compile(r"competing interests?|conflicts? of interests?|conflicting interests?", re.I)
COI_NONE = re.compile(r"\b(?:no|none|nil|nothing|not any|without)\b", re.I)
COI_DECLARES = re.compile(r"receiv|\bfees?\b|honorari|consult|employ|\bshares?\b|\bstock|equity|patent|royalt|advis"
                          r"|\bboard\b|founder|\bowns?\b|\bpaid\b|speaker|salary", re.I)
NUMBER_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
COUNT = r"\b(\d[\d,]*|" + "|".join(NUMBER_WORDS) + r")\s+(?:(\w+)\s+)?"
LETTER_COUNTS = [(what, re.compile(COUNT + pattern, re.I))
                 for what, pattern in (("figures", r"figures?\b"), ("tables", r"tables?\b"), ("references", r"references\b"))]
WORD_CLAIM = re.compile(r"\b(\d[\d,]*)[\s-]*words?\b", re.I)
SAMPLE = re.compile(r"\b[nN]\s*=\s*(\d[\d,]*)|\b(\d[\d,]*)\s+(?:participants|patients|subjects|respondents|individuals"
                    r"|volunteers|students|adults|children|people|cases|samples|specimens|households|observations)\b")
PRIORITY = re.compile(
    r"\bfor the first time\b|\b(?:the|a) first\b(?!\s+(?:authors?|submission|round|version|draft|step|stage|half|part"
    r"|section|reviewer|decision|place|year|month|week|day|wave|phase))|\bfirst(?:-ever| ever| to (?:show|demonstrate"
    r"|report|describe|identify|establish))\b|\bnovel(?:ty)?\b|\bunprecedented\b|\bground-?breaking\b|\bbreakthrough\b"
    r"|\brevolution(?:ary|i[sz]es?)\b|\bparadigm[- ]shift(?:ing)?\b|\bpioneer(?:ing)?\b|\blandmark\b"
    r"|\bgame-?chang(?:er|ing)\b|\bunique(?:ly)?\b|\bnever before\b", re.I)


class Problem(Exception):
    """Bad input: reported in one line, exit code 2."""


def check(name: str, state: str, detail: str, where=()) -> dict:
    return {"check": name, "state": state, "detail": detail, "where": list(dict.fromkeys(where))}


def load_json(path, what: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise Problem(f"cannot read {what} {path}: {exc.strerror or exc}") from None
    except ValueError as exc:
        raise Problem(f"{what} {path} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise Problem(f"{what} {path} must be a JSON object")
    return data


def load_record(path) -> dict:
    record = load_json(path, "the authors file")
    authors = record.get("authors")
    if not isinstance(authors, list) or not authors or \
            not all(isinstance(a, dict) and str(a.get("name") or "").strip() for a in authors):
        raise Problem(f"{path}: \"authors\" must be a list of objects, each with a \"name\", in byline order")
    return record


# ---------------------------------------------------------------------------------------------
# Reading documents


def docx_lines(path: Path) -> list:
    """The paragraphs and table rows of a .docx, each paragraph followed by an empty line;
    Title and Heading styles become Markdown headings."""
    try:
        with zipfile.ZipFile(path) as archive:
            body = ElementTree.fromstring(archive.read("word/document.xml")).find(W + "body")
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise Problem(f"cannot read {path} as a .docx file: {exc}") from None

    def text_of(element) -> str:
        return "".join(e.text or "" if e.tag == W + "t" else " " for e in element.iter()
                       if e.tag in (W + "t", W + "tab", W + "br"))

    out, n = [], 0
    for element in body if body is not None else ():
        if element.tag == W + "p":
            n += 1
            style = element.find(f"{W}pPr/{W}pStyle")
            name = (style.get(W + "val") or "").lower() if style is not None else ""
            level = 1 if name == "title" else int(name[-1]) + 1 if re.fullmatch(r"heading ?[1-5]", name) else 0
            out += [(n, "#" * level + " " * bool(level) + text_of(element).strip()), (n, "")]
        elif element.tag == W + "tbl":
            for row in element.iter(W + "tr"):
                n += 1
                out.append((n, "| " + " | ".join(text_of(cell).strip() for cell in row.iter(W + "tc")) + " |"))
            out.append((n, ""))
    return out


def read_lines(path: Path) -> list:
    if path.suffix.lower() == ".docx":
        return docx_lines(path)
    try:
        return list(enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1))
    except (OSError, UnicodeDecodeError) as exc:
        raise Problem(f"cannot read {path} as text: {exc}") from None


def front_matter(lines: list) -> tuple:
    """Title, abstract and keywords of a YAML front matter, read without a YAML parser."""
    end = next((i for i, (_, t) in enumerate(lines[1:], 1) if t.strip() in ("---", "...")), None)
    if not lines or lines[0][1].strip() != "---" or end is None:
        return {}, lines
    meta, key = {}, None
    for _, text in lines[1:end]:
        field = re.match(r"([A-Za-z_-]+):\s*(.*)$", text)
        if field:
            key = field.group(1).lower()
            meta[key] = field.group(2).strip().strip("|>-").strip().strip("\"'[]")
        elif key and text.strip():
            meta[key] += ("; " if text.strip().startswith("- ") else " ") + text.strip().lstrip("- ").strip("\"'")
    keep = ("title", "abstract", "keywords")
    return {k: v.strip("; ") for k, v in meta.items() if k in keep and v.strip("; ")}, lines[end + 1:]


def plain(text: str) -> str:
    """The visible words of a short Markdown or LaTeX string."""
    return " ".join(re.sub(r"\\\\|\\[A-Za-z]+\*?|[{}*_`#~]", " ", text).split())


def label_of(heading: str) -> str:
    text = re.sub(r"^\s*(?:\d+(?:\.\d+)*\.?|[IVX]+\.)\s+", "", plain(heading))
    return text.strip(" :.").lower().replace("’", "'")


def kind_of(label: str):
    for kind, pattern in SECTION_KINDS:
        if re.fullmatch(pattern, label):
            return kind
    return "statement" if any(re.fullmatch(p, label) for p in STATEMENTS.values()) else None


def is_section_name(label: str) -> bool:
    return kind_of(label) is not None or BODY_NAMES.fullmatch(label) is not None


def split_blocks(lines: list, tex: bool = False) -> tuple:
    """Cut a document into blocks: a heading or a run-in label ("**Funding:** …") with the lines
    under it, each line marked as a table row, a caption, other float content or plain text."""
    blocks = [{"label": "", "level": 0, "n": lines[0][0] if lines else 1, "heading": "", "lines": [], "cont": None}]
    floats = {"figure": 0, "table": 0}
    parent, floating, caption, depth, fence, comment, appendix, blank = blocks[0], None, False, 0, False, False, False, True

    def open_block(label, level, n, heading="", cont=None):
        blocks.append({"label": label, "level": level, "n": n, "heading": heading, "lines": [], "cont": cont})
        return blocks[-1]

    for n, raw in lines:
        line, mark = raw, ""
        if tex:
            line = re.sub(r"\\textbf\{([^{}]*)\}", r"**\1**", TEX_COMMENT.sub("", line))
            if "\\appendix" in line:
                appendix, parent = True, open_block("appendix", 1, n)
            inside = floating
            for edge, env in TEX_ENV.findall(line):
                if env in FLOATS:
                    floating = FLOATS[env] if edge == "begin" else None
                    inside = inside or floating
                    floats[FLOATS[env]] += edge == "begin" and not appendix
                elif env in ENV_HEADINGS:
                    parent = open_block(ENV_HEADINGS[env] if edge == "begin" else "", 1, n)
            if re.search(r"\\(?:bibliography|printbibliography)\b", line):
                parent = open_block("references", 1, n)
            heading = TEX_HEADING.search(line)
            if heading:
                parent = open_block(label_of(heading.group(2)), TEX_LEVEL[heading.group(1)], n, plain(heading.group(2)))
                line = line[heading.end():]
            line = re.sub(r"\\keywords?\s*\{", "Keywords: ", line).replace("\\sep", ";")
            if inside:                               # a line inside, or opening or closing, a float
                caption = caption or "\\caption" in line
                mark = "caption" if caption else "table" if inside == "table" else "float"
                depth = depth + line.count("{") - line.count("}") if caption else 0
                caption = caption and depth > 0 and floating is not None
        else:
            if FENCE.match(line):
                fence = not fence
            if fence or FENCE.match(line):
                continue
            if comment:
                line, comment = (line.split("-->", 1)[1], False) if "-->" in line else ("", True)
            line = re.sub(r"<!--.*?-->", "", line)
            if "<!--" in line:
                line, comment = line.split("<!--", 1)[0], True
            heading = MD_HEADING.match(line)
            name = label_of(heading.group(2) if heading else line)
            # A line without "#" is a heading when it is nothing but a usual section name.
            bare = re.fullmatch(r"[^.!?]{1,80}", line.strip().rstrip(":")) and is_section_name(name) \
                and (kind_of(name) != "supplement" or len(name.split()) <= 4)
            if heading or bare:
                parent = open_block(name, len(heading.group(1)) if heading else 1, n,
                                    plain(heading.group(2) if heading else line))
                blank, caption = True, False
                continue
            caption = bool(line.strip()) and (caption or (blank and CAPTION.match(line) is not None))
            mark = "table" if line.lstrip().startswith("|") else "caption" if caption else ""
        blank = not line.strip()
        run_in = RUN_IN.match(line) or PLAIN_RUN_IN.match(line)
        if run_in and kind_of(label_of(run_in.group(1))):
            open_block(label_of(run_in.group(1)), RUN_IN_LEVEL, n, plain(run_in.group(1)))
            line = run_in.group(2).lstrip(":. ")
        elif blank and blocks[-1]["level"] == RUN_IN_LEVEL:
            open_block(parent["label"], parent["level"], n, cont=parent)     # the paragraph after a run-in label
        blocks[-1]["lines"].append((n, line, mark))
    return blocks, floats


def classify(blocks: list, title_block=None) -> None:
    """Give every block its kind: front, abstract, keywords, body, statement, captions,
    references or supplement. A deeper heading inside a section stays in that section."""
    section, level, seen = "front", 0, set()
    for block in blocks:
        own = kind_of(block["label"])
        if own == "abstract" and block["label"] != "abstract" and seen & {"abstract", "body"}:
            own = None                                      # a closing "Summary" section is main text
        nested = block["level"] > level and (section in SPECIAL or (section == "body" and own == "statement"))
        if block["cont"] is not None:
            block["kind"] = block["cont"]["kind"]
        elif block["level"] == RUN_IN_LEVEL:
            block["kind"] = own or section
        elif nested and (own is None or section == "body"):  # "Ethics approval" inside the Methods is main text
            block["kind"] = section
        else:
            block["kind"] = "front" if block is title_block or not block["label"] else \
                own or ("supplement" if "references" in seen else "body")
            if not nested:
                section, level = block["kind"], block["level"]
        seen.add(block["kind"])


def count_words(text: str) -> int:
    return len(WORD.findall(NOT_WORDS.sub(" ", text)))


def norm(text) -> str:
    return " " + " ".join(re.findall(r"[^\W_]+", str(text).lower())) + " "


def has(text: str, phrase) -> bool:
    return norm(phrase) in norm(text)


def slug(text: str) -> str:
    return re.sub(r"[\s_]+", "-", text.strip().lower())


def sentences(lines: list) -> list:
    """(line, sentence) pairs; the sentences of a paragraph carry the paragraph's first line."""
    out, start, buffer = [], None, []
    for n, text in [*lines, (None, "")]:
        if text.strip():
            start = start if buffer else n
            buffer.append(plain(text))
        elif buffer:
            out += [(start, s) for s in SENTENCE_END.split(" ".join(buffer)) if s.strip()]
            buffer = []
    return out


def load_doc(path: Path, role: str) -> dict:
    lines = read_lines(path)
    tex = path.suffix.lower() == ".tex"
    meta, body = ({}, lines) if tex else front_matter(lines)
    blocks, floats = split_blocks(body, tex)
    return {"name": path.name, "path": path, "role": role, "lines": lines, "blocks": blocks, "floats": floats,
            "meta": meta, "tex": tex}


def doc_text(doc: dict) -> str:
    return " ".join(t for _, t in doc["lines"])


def block_text(block: dict) -> str:
    return " ".join(t.strip() for _, t, _ in block["lines"] if t.strip())


def find_statement(doc: dict, name: str):
    return next((b for b in doc["blocks"] if b["cont"] is None and b["label"]
                 and re.fullmatch(STATEMENTS[name], b["label"])), None)


def is_stub(text: str) -> bool:
    return not text.strip() or STUB.search(text) is not None


def missing(value) -> bool:
    return value in (None, "", [], {}) or STUB.search(str(value)) is not None


# ---------------------------------------------------------------------------------------------
# Measuring the manuscript and the package


def measure(doc: dict, include=()) -> dict:
    """Classify the manuscript's blocks and count. "values" maps the name of a limit to
    (number or None, unit, how it was counted or why it could not be)."""
    blocks, tex = doc["blocks"], doc["tex"]
    full = "\n".join(TEX_COMMENT.sub("", t) if tex else t for _, t in doc["lines"])
    title, head = doc["meta"].get("title"), None
    if tex:
        found = TEX_TITLE.search(full)
        title = found.group(1) if found else None
    else:
        first = blocks[1] if len(blocks) > 1 else None
        if first and first["level"] < RUN_IN_LEVEL and not is_section_name(first["label"]) \
                and (not title or label_of(title) == first["label"]):
            head, title = first, title or first["heading"]
        title = title or next((t for _, t, _ in blocks[0]["lines"] if t.strip()), None)
    title = plain(title) if title else None
    classify(blocks, head)

    parts = dict.fromkeys(("abstract", "body", "statement", "captions", "tables", "references"), 0)
    abstract, keywords, numbers, captions, mentions, listed = [], [], set(), [], [], []
    for block in blocks:
        kind = block["kind"]
        parts["body"] += count_words(block["heading"]) if kind == "body" else 0
        for n, text, mark in block["lines"]:
            keywords += [text] if kind == "keywords" else []
            if kind in ("front", "keywords", "supplement") or mark == "float":
                continue
            key = {"table": "tables", "caption": "captions"}.get(mark, kind)
            parts[key] += count_words(text)
            abstract += [(n, text)] if key == "abstract" else []
            listed += [text] if key == "references" else []
            if key != "references":
                numbers.update(int(x.replace(",", "")) for x in NUMBER.findall(text))
                mentions += MENTION.findall(text) if key == "body" else []
            if mark == "caption" and CAPTION.match(text):
                captions.append(CAPTION.match(text).groups())
    if doc["meta"].get("abstract"):
        abstract = [(doc["lines"][0][0], doc["meta"]["abstract"])]
        parts["abstract"] = count_words(abstract[0][1])

    def floats(word: str) -> tuple:
        if tex:
            return doc["floats"][word], f"\\begin{{{word}}} environments before any appendix"
        numbered = {num for kind, num in captions if kind.lower().startswith(word[:3]) and num.isdigit()}
        if numbered:
            return len(numbered), f"numbered {word} captions"
        named = {num for kind, num in mentions if kind.lower().startswith(word[:3])}
        return len(named), f"{word}s named in the main text; no {word} caption found"

    if tex and "\\bibitem" in full:
        references = len(re.findall(r"\\bibitem\b", full)), "\\bibitem entries"
    elif tex and re.search(r"\\nocite\s*\{\s*\*\s*\}", full):
        references = None, "\\nocite{*} puts the whole .bib file in the list: count it in the built PDF"
    elif any(t.strip() for t in listed):
        marked = [t for t in listed if BULLET.match(t)]
        entries = marked or [p for p in re.split(r"\n\s*\n", "\n".join(listed)) if p.strip()]
        if len(entries) == 1:
            entries = [t for t in listed if t.strip()]
        references = len(entries), "entries of the reference list"
    else:
        keys = {k.strip() for g in TEX_CITE.findall(full) for k in g.split(",")} - {"", "*"} if tex else \
            set(re.findall(r"(?<![\w.])@([A-Za-z][\w:.-]*)", full))
        references = (len(keys), "distinct cited keys (no reference list in the file)") if keys \
            else (None, "no reference list and no citation keys found")

    first_body = next((b for b in blocks if b["kind"] == "body"), None)
    extra = [p for p in include if p in PARTS]
    left_out = ["title block", "keywords", *[p for p in PARTS if p not in extra], "appendices", "citation markers",
                "inline maths"]
    scope = (f"from \"{first_body['heading']}\" (line {first_body['n']}) to the reference list, headings included"
             + "".join(f", plus {p}" for p in extra) + "; not counted: " + ", ".join(left_out)) if first_body \
        else "no section heading found after the abstract, so the main text could not be told apart"
    items = [k for k in re.split(r"[;,\n·•|]", doc["meta"].get("keywords") or "\n".join(keywords)) if k.strip(" -*.}")]
    figures, tables = floats("figure"), floats("table")
    no_title = "no title found in the manuscript"
    values = {
        "title_characters": (len(title) if title else None, "characters", "the title, spaces included" if title else no_title),
        "title_words": (count_words(title) if title else None, "words", "the title" if title else no_title),
        "abstract_words": (parts["abstract"] or None, "words", "the abstract" if parts["abstract"] else "no abstract found"),
        "main_text_words": (parts["body"] + sum(parts[PARTS[p]] for p in extra) if first_body else None, "words", scope),
        "keywords": (len(items) or None, "keywords", "the keywords line" if items else "no keywords found"),
        "figures": (figures[0], "figures", figures[1]),
        "tables": (tables[0], "tables", tables[1]),
        "display_items": (figures[0] + tables[0], "figures and tables", f"{figures[1]}; {tables[1]}"),
        "references": (references[0], "references", references[1]),
    }
    if tex and re.search(r"\\(?:input|include|subfile)\s*\{", full):
        for key in ("main_text_words", "figures", "tables", "display_items"):
            values[key] = (None, values[key][1], "the file pulls in others with \\input or \\include, which are not read: "
                                                  "run on a flattened file (latexpand) or count in the built PDF")
    return {"title": title, "abstract": abstract, "numbers": numbers, "values": values}


def measure_limit(name: str, values: dict, package_docs: list) -> tuple:
    """(number, or a list of (number, item); unit; how it was counted or why not)."""
    if name in values:
        return values[name]
    if name in ("highlights_count", "highlight_characters"):
        doc = next((d for d in package_docs if d["role"] == "highlights"), None)
        if doc is None:
            return None, "", "no highlights file in the package"
        texts = [t.strip() for _, t in doc["lines"] if t.strip() and not MD_HEADING.match(t)]
        items = [plain(BULLET.sub("", t)) for t in texts if BULLET.match(t)] or [plain(t) for t in texts]
        if name == "highlights_count":
            return len(items), "highlights", f"the items of {doc['name']}"
        return [(len(i), i) for i in items], "characters", f"each item of {doc['name']}, spaces included"
    found = re.fullmatch(r"(.+)_(words|characters)", name)
    if not found:
        return None, "", f"this script does not measure \"{name}\": check it by hand"
    target = slug(found.group(1))
    doc = next((d for d in package_docs if slug(d["path"].stem).startswith(target) or target in ROLES.get(d["role"], ())), None)
    if doc is None:
        return None, "", f"no file named {target}.* in the package"
    if found.group(2) == "words":
        return sum(count_words(t) for _, t in doc["lines"]), "words", f"all the text of {doc['name']}"
    return len(plain(doc_text(doc))), "characters", f"all the text of {doc['name']}, spaces included"


def check_limit(limit: dict, top: dict, values: dict, package_docs: list) -> dict:
    name = str(limit.get("name") or "").strip()
    row, high, low = f"limit: {name or '?'}", limit.get("value"), limit.get("min")
    source, date = str(limit.get("source") or "").strip(), str(limit.get("date_read") or top.get("date_read") or "").strip()
    value, unit, how = measure_limit(name, values, package_docs)
    items = value if isinstance(value, list) else None
    most = max((v for v, _ in items), default=0) if items is not None else value
    least = min((v for v, _ in items), default=0) if items is not None else value
    shown = "not measured" if value is None else f"longest of {len(items)} items: {most} {unit}" if items is not None \
        else f"{value:,} {unit}"
    has_high, has_low = (isinstance(x, (int, float)) and not isinstance(x, bool) for x in (high, low))
    bounds = f"{low:,} to {high:,}" if has_high and has_low else f"at most {high:,}" if has_high else \
        f"at least {low:,}" if has_low else "no value"
    if not source or not date:
        return check(row, "not_checked", f"{shown}; the limit ({bounds}) has no {'source' if not source else 'date read'} "
                                         "in the requirements file, so it is not applied")
    if not (has_high or has_low):
        return check(row, "not_checked", f"{shown}; the requirements file gives no number for this limit ({source})")
    if value is None:
        return check(row, "not_checked", f"{how}; limit {bounds} ({source}, read {date})")

    def outside(v):
        return (has_high and v > high) or (has_low and v < low)

    where = [f"{v} characters: {text}" for v, text in items or [] if outside(v)]
    state = "fail" if outside(most) or outside(least) else "pass"
    return check(row, state, f"{shown}; limit {bounds} ({source}, read {date}); counted: {how}", where)


# ---------------------------------------------------------------------------------------------
# Required statements, files, deliverables, placeholders


def check_statements(required: list, docs: list) -> list:
    rows = []
    for entry in required:
        name = entry if isinstance(entry, str) else str((entry or {}).get("name") or "?")
        if name not in STATEMENTS:
            rows.append(check(f"statement: {name}", "not_checked", "not a statement this script knows: give its "
                                                                   "\"headings\" in the requirements file, or check it by hand"))
            continue
        found = [(d, b) for d in docs if (b := find_statement(d, name)) is not None]
        good = [f"{d['name']}:{b['n']}" for d, b in found if not is_stub(block_text(b))]
        if good:
            rows.append(check(f"statement: {name}", "pass", "found at " + ", ".join(good)))
        elif found:
            rows.append(check(f"statement: {name}", "fail", "present but empty or still a placeholder, which counts as missing",
                              [f"{d['name']}:{b['n']}: {block_text(b)[:140] or '(empty)'}" for d, b in found]))
        else:
            rows.append(check(f"statement: {name}", "fail", "not found under any of its usual headings, in the manuscript "
                                                            "or the package"))
    return rows


def check_files(required: list, package: Path) -> list:
    rows = []
    for entry in required:
        pattern = str(entry.get("pattern") or entry.get("name") or "?")
        allowed = ["." + str(e).lower().lstrip(".") for e in entry.get("extensions") or []]
        cap = entry.get("max_mb")
        try:
            files = [p for p in sorted(package.glob(pattern)) if p.is_file()]
        except (ValueError, NotImplementedError):
            raise Problem(f"required_files: \"{pattern}\" is not a pattern relative to the package folder") from None
        notes, good = [], []
        for path in files:
            size = path.stat().st_size / 1e6
            if allowed and path.suffix.lower() not in allowed:
                notes.append(f"{path.name}: extension {path.suffix or '(none)'} is not one of {', '.join(allowed)}")
            elif isinstance(cap, (int, float)) and size > cap:
                notes.append(f"{path.name}: {size:.1f} MB is over the maximum of {cap} MB")
            else:
                good.append(f"{path.name} ({size:.2f} MB)")
        row = f"file: {entry.get('name') or pattern}"
        rows.append(check(row, "pass", "present: " + ", ".join(good)) if good else
                    check(row, "fail", f"no acceptable file matching {pattern} in {package.name}/", notes))
    return rows


def check_deliverables(entries: list, package: Path) -> list:
    rows = []
    for entry in entries:
        name, status = str(entry.get("name") or "?"), slug(str(entry.get("status") or "")).replace("-", "_")
        present = ", ".join(p.name for p in sorted(package.iterdir()) if p.is_file() and p.name not in WORKING_FILES and (
            fnmatch.fnmatch(p.name, str(entry["file"])) if entry.get("file") else slug(p.stem).startswith(slug(name))))
        row = f"deliverable: {name}"
        if status == "required":
            rows.append(check(row, "pass" if present else "fail",
                              f"required; {'present: ' + present if present else 'no file found'}"))
        elif status == "optional":
            rows.append(check(row, "pass", f"optional; {'present: ' + present if present else 'not in the package'}"))
        elif status == "not_accepted":
            rows.append(check(row, "fail" if present else "pass",
                              f"not accepted by the venue; {'remove ' + present if present else 'absent'}"))
        else:
            rows.append(check(row, "not_checked", f"status \"{entry.get('status')}\" is not required, optional or not_accepted"))
    return rows


def check_placeholders(docs: list, final: bool) -> dict:
    where = [f"{d['name']}:{n}: {m.group(0)}" for d in docs for n, text in d["lines"] for m in PLACEHOLDER.finditer(text)]
    if not where:
        return check("placeholders", "pass", "no [Evidence needed], [Citation needed] or [Author input needed] is left")
    if final:
        return check("placeholders", "fail", f"{len(where)} placeholder(s) remain in a --final run", where)
    return check("placeholders", "not_checked", f"{len(where)} placeholder(s) remain; they fail a --final run", where)


# ---------------------------------------------------------------------------------------------
# Agreement with authors.json and between documents


def initials_of(author: dict) -> str:
    given = author.get("initials") or "".join(p[0] for p in re.split(r"[\s.-]+", author["name"]) if p)
    return "".join(c for c in str(given) if c.isalpha()).upper()


def check_title(title, doc, row: str, what: str) -> dict:
    if doc is None:
        return check(row, "not_checked", f"no {what} in the package")
    if not title:
        return check(row, "not_checked", "no title found in the manuscript")
    if has(doc_text(doc), title):
        return check(row, "pass", f"the manuscript's title is in the {what}, word for word")
    start = next((t.strip() for _, t in doc["lines"] if t.strip()), "")
    return check(row, "fail", f"the manuscript's title is not in the {what}: one of the two is out of date",
                 [f"manuscript: {title}", f"{doc['name']} begins: {start[:140]}"])


def name_problems(authors: list, text: str, place: str) -> tuple:
    """Whether any author is named in the text, and the authors missing or out of order."""
    spots = [(norm(text).find(norm(a["name"])), a["name"]) for a in authors]
    there = [name for spot, name in spots if spot >= 0]
    order = [name for _, name in sorted(s for s in spots if s[0] >= 0)]
    problems = [f"not {place}: {name}" for spot, name in spots if spot < 0]
    if order != there:
        problems.append(f"the order differs: authors.json has {', '.join(there)}; {place} they are {', '.join(order)}")
    return bool(there), problems


def check_title_page(authors: list, page) -> dict:
    row = "agreement: authors on the title page"
    if page is None:
        return check(row, "not_checked", "no title page in the package")
    text = doc_text(page)
    _, problems = name_problems(authors, text, "on the title page")
    problems += [f"affiliation not on the title page: {x}"
                 for x in dict.fromkeys(str(x) for a in authors for x in a.get("affiliations") or []) if not has(text, x)]
    corresponding = [a for a in authors if a.get("corresponding")]
    problems += [] if corresponding else ["authors.json marks no corresponding author"]
    problems += [f"the corresponding author's email {a['email']} is not on the title page" for a in corresponding
                 if not missing(a.get("email")) and str(a["email"]).lower() not in text.lower()]
    equal = [a["name"] for a in authors if a.get("equal_contribution")]
    if len(equal) == 1:
        problems.append(f"only {equal[0]} is marked as contributing equally: it takes two")
    elif equal and not re.search(r"\bequal", text, re.I):
        problems.append("authors are marked as contributing equally, but the title page has no note saying so")
    if problems:
        return check(row, "fail", f"{page['name']} disagrees with authors.json", problems)
    return check(row, "pass", f"{len(authors)} author(s) in the order of authors.json, with affiliations and the "
                              "corresponding author's email")


def check_byline(authors: list, manuscript: dict) -> dict:
    row = "agreement: byline of the manuscript"
    front = " ".join(t for b in manuscript["blocks"] if b["kind"] == "front" for _, t, _ in b["lines"])
    named, problems = name_problems(authors, front, "in the manuscript's title block")
    if not named:
        return check(row, "not_checked", "no author is named in the manuscript's title block (right for a blinded file)")
    if problems:
        return check(row, "fail", f"{manuscript['name']} disagrees with authors.json", problems)
    return check(row, "pass", "the manuscript names the authors in the order of authors.json")


def roles_of(author: dict) -> list:
    roles = author.get("roles")
    return [] if missing(roles) else [roles] if isinstance(roles, str) else list(roles)


def role_key(role: str) -> str:
    text = re.sub(r"[^a-z ]", " ", role.lower())
    return re.sub(r" preparation$", "", " ".join(w for w in text.split() if w != "and"))


def check_credit(authors: list, statement_required: bool) -> dict:
    row, known = "agreement: CRediT roles", {role_key(term) for term in CREDIT}
    if not statement_required and not any(roles_of(a) for a in authors):
        return check(row, "not_checked", "authors.json records no roles and no contributions statement is required")
    problems = [f"{a['name']} has no role" for a in authors if not roles_of(a)]
    problems += [f"{a['name']}: \"{role}\" is not one of the 14 CRediT terms"
                 + (f"; the closest is {NOT_CREDIT[role_key(str(role))]}" if role_key(str(role)) in NOT_CREDIT else "")
                 for a in authors for role in roles_of(a) if role_key(str(role)) not in known]
    if problems:
        return check(row, "fail", "every author needs at least one role, and every role must be a CRediT term", problems)
    return check(row, "pass", f"all {len(authors)} author(s) have roles, and every role is a CRediT term")


def check_initials(authors: list, docs: list) -> dict:
    row = "agreement: initials in the contributions statement"
    found = [(d, b) for d in docs if (b := find_statement(d, "author_contributions")) is not None
             and not is_stub(block_text(b))]
    if not found:
        return check(row, "not_checked", "no author contributions statement found")
    owners: dict = {}
    for author in authors:
        owners.setdefault(initials_of(author), []).append(author["name"])
    problems, unjudged = [], set()
    for doc, block in found:
        text, place, used, tokens = block_text(block), f"{doc['name']}:{block['n']}", set(), []
        for token in INITIALS.findall(text) + DOTLESS.findall(text):
            key = "".join(c for c in token if c.isalpha())
            # "M.O. A.L." is read as one run of four letters: split it where both halves are authors
            cut = next((i for i in range(2, len(key) - 1) if key[:i] in owners and key[i:] in owners), None)
            tokens += [(token.strip(), key)] if key in owners or cut is None else \
                [(token.strip(), key[:cut]), (token.strip(), key[cut:])]
        for token, key in dict.fromkeys(tokens):
            names = owners.get(key, [])
            used.add(key)
            if len(names) > 1:
                problems.append(f"{place}: {token} fits {len(names)} authors ({', '.join(names)}): write the names out")
            elif not names and "." in token:
                problems.append(f"{place}: {token} fits no author in authors.json")
            elif not names:
                unjudged.add(token)
        problems += [f"{place}: {a['name']} ({initials_of(a)}) has no contribution in the statement" for a in authors
                     if initials_of(a) not in used and not has(text, a["name"])]
    note = (f"; not judged: {', '.join(sorted(unjudged))} (capital letters that fit no author: abbreviations, or "
            "initials left from an earlier author list)") if unjudged else ""
    if problems:
        return check(row, "fail", "the statement and the author list do not match" + note, problems)
    return check(row, "pass", "every set of initials resolves to exactly one author and every author is named" + note)


def squash(text: str) -> str:
    return " ".join(text.split()).casefold()


def id_variants(docs: list, known: list) -> list:
    """Tokens that are nearly, but not exactly, a known identifier: a typing error or an old number."""
    keys = {k.casefold(): k for k in known if " " not in k}
    return [f"{doc['name']}:{n}: {token} differs from {shown} in authors.json"
            for doc in docs for n, text in doc["lines"] for token in ID_TOKEN.findall(text)
            if token.casefold() not in keys and any(c.isdigit() for c in token)
            for key, shown in keys.items() if abs(len(token) - len(key)) <= 1
            and difflib.SequenceMatcher(None, token.casefold(), key).ratio() >= 0.8]


def check_funding(record: dict, docs: list) -> dict:
    row, funding = "agreement: funders and grant numbers", record.get("funding")
    if missing(funding):
        return check(row, "not_checked", "authors.json has no funding record to compare with")
    statements = [(d, b) for d in docs if (b := find_statement(d, "funding")) is not None and not is_stub(block_text(b))]
    if not statements:
        return check(row, "not_checked", "no funding statement found in any document")
    if isinstance(funding, str):
        if not re.match(r"\s*(?:none|no funding|not funded|unfunded)\b", funding, re.I):
            return check(row, "not_checked", "\"funding\" in authors.json must be a list of funders, or the word none")
        problems = [f"{d['name']}:{b['n']}: authors.json says \"{funding}\", but this statement carries a number ({token})"
                    for d, b in statements for token in ID_TOKEN.findall(block_text(b))
                    if any(c.isdigit() for c in token) and not re.fullmatch(r"(?:19|20)\d\d", token)]
    else:
        entries = [f for f in funding if isinstance(f, dict)]
        grants = [str(f["grant_number"]).strip() for f in entries if not missing(f.get("grant_number"))]
        funders = list(dict.fromkeys(str(f["funder"]).strip() for f in entries if not missing(f.get("funder"))))
        problems = [f"{d['name']}:{b['n']}: {what} {x} is not in this funding statement" for d, b in statements
                    for what, xs in (("grant number", grants), ("funder", funders)) for x in xs
                    if squash(x) not in squash(block_text(b))] + id_variants(docs, grants)
    if problems:
        return check(row, "fail", "funding is not stated the same way everywhere", problems)
    return check(row, "pass", "the funding statements carry the funders and grant numbers of authors.json: "
                 + ", ".join(f"{d['name']}:{b['n']}" for d, b in statements))


def check_ids(row: str, what: str, known: list, docs: list) -> dict:
    if not known:
        return check(row, "not_checked", f"authors.json gives no {what} to compare with")
    places = {k: [d["name"] for d in docs if squash(k) in squash(doc_text(d))] for k in known}
    problems = [f"{k} is in authors.json but in no document" for k, names in places.items() if not names]
    problems += id_variants(docs, known)
    if problems:
        return check(row, "fail", f"a {what} is missing or written differently", problems)
    return check(row, "pass", "; ".join(f"{k} appears unchanged in {', '.join(names)}" for k, names in places.items()))


def coi_class(text: str):
    """"none" when every sentence denies an interest, "declared" when one does not."""
    said = [s for _, s in sentences([(0, text)])]
    if not said or is_stub(text):
        return None
    return "none" if all(COI_NONE.search(s) and not COI_DECLARES.search(s) for s in said) else "declared"


def check_competing(authors: list, docs: list) -> dict:
    row, seen = "agreement: competing interests", []
    classes = [None if missing(a.get("competing_interests")) else coi_class(str(a["competing_interests"])) for a in authors]
    if "declared" in classes or None not in classes:
        seen.append(("authors.json", "declared" if "declared" in classes else "none"))
    for doc in docs:
        block = find_statement(doc, "competing_interests")
        hits = [] if block or doc["role"] == "manuscript" else \
            [(n, s) for n, s in sentences(doc["lines"]) if COI_WORDS.search(s)]
        text, n = (block_text(block), block["n"]) if block else (" ".join(s for _, s in hits), hits[0][0] if hits else 0)
        if text and coi_class(text):
            seen.append((f"{doc['name']}:{n}", coi_class(text)))
    said = {c for _, c in seen}
    where = [f"{place}: {'declares an interest' if c == 'declared' else 'says there is none'}" for place, c in seen]
    if said == {"none", "declared"}:
        return check(row, "fail", "one place declares an interest and another says there is none", where)
    if len(seen) < 2:
        return check(row, "not_checked", "fewer than two competing-interest statements found: nothing to compare")
    agreed = "none declared" if said == {"none"} else "an interest is declared"
    return check(row, "pass", f"{len(seen)} statements agree ({agreed}): " + ", ".join(place for place, _ in seen))


# ---------------------------------------------------------------------------------------------
# The cover letter


def check_letter_numbers(letter, measured: dict) -> dict:
    row = "letter: numbers about the manuscript"
    if letter is None:
        return check(row, "not_checked", "no cover letter in the package")
    values, agree, wrong, unknown = measured["values"], [], [], []

    def compare(n, said, what, key, exact=True):
        value, _, how = values[key]
        place = f"{letter['name']}:{n}: the letter states {said:,} {what}"
        if value is None:
            unknown.append(f"{place}; not compared ({how})")
        elif said == value or (not exact and abs(said - value) <= max(5, WORD_TOLERANCE * value)):
            agree.append(f"{said:,} {what}")
        else:
            wrong.append(f"{place}; measured {value:,} ({how})")

    for n, text in letter["lines"]:
        for what, pattern in LETTER_COUNTS:
            for found in pattern.finditer(text):
                if not (found.group(2) or "").lower().startswith(("supplement", "extended", "additional", "online")):
                    said = found.group(1).lower()
                    compare(n, NUMBER_WORDS[said] if said in NUMBER_WORDS else int(said.replace(",", "")), what, what)
        for found in WORD_CLAIM.finditer(text):
            said, before = int(found.group(1).replace(",", "")), text[:found.start()][-30:].lower()
            if re.search(r"limit|maximum|at most|up to|no more than|fewer than|under|below|within", before):
                continue                                    # a limit the letter quotes, not a count
            if "abstract" in before or re.match(r"[\s-]*abstract", text[found.end():].lower()):
                compare(n, said, "words in the abstract", "abstract_words", exact=False)
            elif said >= 500:
                compare(n, said, "words of main text", "main_text_words", exact=False)
        for found in SAMPLE.finditer(text):
            said = int((found.group(1) or found.group(2)).replace(",", ""))
            if said in measured["numbers"]:
                agree.append(f"sample size {said:,}")
            else:
                wrong.append(f"{letter['name']}:{n}: the letter gives a sample size of {said:,}, a number the manuscript "
                             "does not contain")
    if wrong:
        return check(row, "fail", "the letter states numbers the manuscript does not have", wrong + unknown)
    if unknown:
        return check(row, "not_checked", "a number in the letter could not be compared", unknown)
    return check(row, "pass", ("agree with the manuscript: " + ", ".join(dict.fromkeys(agree))) if agree
                 else "the letter states no counts about the manuscript")


def check_letter_repeats(letter, abstract: list) -> dict:
    row = "letter: sentences repeating the abstract"
    if letter is None or not abstract:
        return check(row, "not_checked", "no cover letter in the package" if letter is None else "no abstract found")

    def tokens(sentence):
        return re.findall(r"[^\W_]+", sentence.lower())

    def overlap(a, b):
        return sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()) / min(len(a), len(b))

    ours = [w for _, s in sentences(abstract) if len(w := tokens(s)) >= MIN_SENTENCE]
    theirs = [(n, s, w) for n, s in sentences(letter["lines"]) if len(w := tokens(s)) >= MIN_SENTENCE]
    repeated = [f"{letter['name']}:{n}: {s}" for n, s, w in theirs if any(overlap(w, a) >= REPEAT for a in ours)]
    if repeated:
        share = round(100 * len(repeated) / len(theirs))
        return check(row, "fail", f"{len(repeated)} of the letter's {len(theirs)} sentences ({share}%) repeat a sentence "
                                  "of the abstract; the letter should say what the abstract does not", repeated)
    return check(row, "pass", f"none of the letter's {len(theirs)} sentences repeats a sentence of the abstract "
                              "(copies are found, paraphrases are not)")


def check_priority(letter) -> dict:
    row = "letter: priority words"
    if letter is None:
        return check(row, "not_checked", "no cover letter in the package")
    where = [f"{letter['name']}:{n}: \"{m.group(0)}\" in: {s}" for n, s in sentences(letter["lines"]) for m in PRIORITY.finditer(s)]
    if not where:
        return check(row, "pass", "the letter claims no priority (\"first\", \"novel\", \"unprecedented\" and the like)")
    return check(row, "not_checked", f"{len(where)} priority word(s): the authors justify each one with a search or "
                                     "remove it", where)


# ---------------------------------------------------------------------------------------------
# What the authors still owe, the author block, the report


def gaps(record: dict) -> list:
    """Facts only the authors can supply that authors.json does not have yet."""
    out = []
    for author in record["authors"]:
        lacking = [what for key, what in (("affiliations", "affiliation"), ("roles", "contribution roles"),
                                          ("competing_interests", "competing interests, or confirmation that there are none"))
                   if missing(author.get(key))]
        lacking += ["email address"] if author.get("corresponding") and missing(author.get("email")) else []
        out += [f"{author['name']}: {'; '.join(lacking)}"] if lacking else []
    out += [] if any(a.get("corresponding") for a in record["authors"]) else ["Which author is the corresponding author"]
    return out + [what for key, what in (
        ("funding", "Funding: each funder with its grant number, or confirmation that there was none"),
        ("ethics", "Ethics: each approving body with its approval id, or confirmation that none was needed"),
        ("registrations", "Registration: registry and id, or confirmation that the study was not registered"),
        ("ai_use", "AI use: which tools were used, for what, and how the output was checked, or confirmation that none "
                   "was used. Drafting this package with an AI assistant counts as use"),
    ) if missing(record.get(key))]


def author_block(authors: list) -> str:
    """The author line and affiliations of a title page, numbered in order of first appearance."""
    numbers: dict = {}
    for author in authors:
        for affiliation in author.get("affiliations") or []:
            numbers.setdefault(str(affiliation), len(numbers) + 1)
    names = []
    for author in authors:
        marks = [str(numbers[str(x)]) for x in author.get("affiliations") or []]
        marks += ["†"] * bool(author.get("equal_contribution")) + ["\\*"] * bool(author.get("corresponding"))
        names.append(author["name"] + (f"^{','.join(marks)}^" if marks else ""))
    lines = [", ".join(names), "", *[f"^{n}^ {text}" for text, n in numbers.items()], ""]
    lines += ["† These authors contributed equally."] if any(a.get("equal_contribution") for a in authors) else []
    lines += [f"\\* Corresponding author: {a['name']}, {a.get('email') or '[Author input needed: email]'}"
              for a in authors if a.get("corresponding")]
    return "\n".join(lines).rstrip() + "\n"


def write_report(path: Path, requirements: dict, manuscript: dict, measured: dict, rows: list, todo: list,
                 final: bool) -> dict:
    def cell(value) -> str:
        return " ".join(str(value).split()).replace("|", "\\|")

    def field(key: str) -> str:
        return cell(requirements.get(key) or "not recorded")

    counts = {state: sum(r["state"] == state for r in rows) for state in ("pass", "fail", "not_checked")}
    digest = hashlib.sha256(manuscript["path"].read_bytes()).hexdigest()[:12]
    lines = [f"# Submission package check: {field('venue')}", "",
             "Internal working report. Do not upload it with the submission.", "",
             f"- Manuscript: `{manuscript['name']}` (SHA-256 {digest}…)",
             f"- Article type: {field('article_type')}. Stage: {field('stage')}. Review: {field('review_model')}.",
             f"- Requirements built from: {field('source')}, read {field('date_read')}",
             f"- Run: {'final' if final else 'draft (placeholders are listed and do not fail)'}", "",
             f"**{counts['fail']} fail, {counts['not_checked']} not checked, {counts['pass']} pass.** "
             "A `not_checked` row was not verified: it is not a pass.", "",
             "## Checks", "", "| Check | State | Detail |", "|---|---|---|"]
    lines += [f"| {cell(r['check'])} | `{r['state']}` | {cell(r['detail'])} |" for r in rows]
    for row in (r for r in rows if r["where"]):
        lines += ["", f"### {row['check']} (`{row['state']}`)", "", *[f"- {cell(w)}" for w in row["where"]]]
    lines += ["", "## Measured", "", f"Title: {measured['title'] or 'not found'}", "",
              "| Quantity | Value | How it was counted |", "|---|---|---|"]
    lines += [f"| {name} | {'not measured' if value is None else f'{value:,}'} | {cell(how)} |"
              for name, (value, _, how) in measured["values"].items()]
    lines += ["", "## For the authors: still to supply or confirm", ""]
    lines += [f"{i}. {cell(item)}" for i, item in enumerate(todo, 1)] or ["Nothing is open."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return counts


# ---------------------------------------------------------------------------------------------


def run(args) -> int:
    if args.author_block:
        if not args.authors:
            raise Problem("--author-block needs --authors FILE")
        print(author_block(load_record(args.authors)["authors"]), end="")
        return 0
    if not args.manuscript or not args.package:
        raise Problem("give the manuscript and --package DIR (or --author-block with --authors)")
    package, path = Path(args.package), Path(args.manuscript)
    if not package.is_dir():
        raise Problem(f"the package folder {package} does not exist")
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        raise Problem(f"the manuscript {path} must be an existing .md, .tex, .txt or .docx file")
    requirements = load_json(args.requirements or package / "requirements.json", "the requirements file")
    record = load_record(args.authors or package / "authors.json")
    authors = record["authors"]

    def entries(key: str) -> list:
        value = requirements.get(key) or []
        if not isinstance(value, list):
            raise Problem(f"\"{key}\" in the requirements file must be a list")
        return [x for x in value if isinstance(x, dict)] if key != "required_statements" else value

    limits, required = entries("limits"), entries("required_statements")
    for entry in required:                  # a statement the venue names itself, with the headings to look for
        if isinstance(entry, dict) and entry.get("name") and entry.get("headings"):
            STATEMENTS[str(entry["name"])] = "|".join(re.escape(label_of(str(h))) for h in entry["headings"])
    include = next((x.get("include") or [] for x in limits if x.get("name") == "main_text_words"), [])
    if any(p not in PARTS for p in include):
        raise Problem(f"\"include\" of main_text_words takes {', '.join(PARTS)}; got {', '.join(map(str, include))}")

    manuscript = load_doc(path, "manuscript")
    measured = measure(manuscript, include)
    package_docs, roles = [], {}
    order = {s: i for i, s in enumerate(TEXT_SUFFIXES)}
    for file in sorted(package.iterdir(), key=lambda p: (order.get(p.suffix.lower(), 9), p.name)):
        if file.is_file() and file.suffix.lower() in order and file.name not in WORKING_FILES \
                and file.resolve() != path.resolve():
            role = next((r for r, stems in ROLES.items() if r not in roles and slug(file.stem).startswith(stems)), "other")
            package_docs.append(load_doc(file, role))
            roles.setdefault(role, package_docs[-1])
    docs = [manuscript, *package_docs]
    letter, page = roles.get("letter"), roles.get("title_page")

    lacking = [k for k in ("venue", "article_type", "stage", "source", "date_read") if not str(requirements.get(k) or "").strip()]
    rows = [check("requirements", "not_checked", "the requirements file does not record: " + ", ".join(lacking)) if lacking
            else check("requirements", "pass", f"built from {requirements['source']}, read {requirements['date_read']}; "
                                               "whether it matches the guidelines is for the authors to confirm")]
    rows += [check_limit(x, requirements, measured["values"], package_docs) for x in limits]
    rows += check_statements(required, docs)
    rows += check_files(entries("required_files"), package)
    rows += check_deliverables(entries("deliverables"), package)
    rows.append(check_placeholders(docs, args.final))
    rows.append(check_title(measured["title"], page, "agreement: title on the title page", "title page"))
    rows.append(check_title(measured["title"], letter, "agreement: title in the letter", "cover letter"))
    rows += [check_title_page(authors, page), check_byline(authors, manuscript)]
    names = [e if isinstance(e, str) else (e or {}).get("name") for e in required]
    rows += [check_credit(authors, "author_contributions" in names), check_initials(authors, docs),
             check_funding(record, docs)]
    for row, what, key, field in (("agreement: ethics approval ids", "ethics approval id", "ethics", "approval_id"),
                                  ("agreement: registration ids", "registration id", "registrations", "id")):
        value = record.get(key) if isinstance(record.get(key), list) else []
        rows.append(check_ids(row, what, [str(e[field]).strip() for e in value
                                          if isinstance(e, dict) and not missing(e.get(field))], docs))
    rows.append(check_competing(authors, docs))
    rows += [check_letter_numbers(letter, measured), check_letter_repeats(letter, measured["abstract"]), check_priority(letter)]
    model = str(requirements.get("review_model") or "").lower()
    if re.search(r"double|triple|anonym|blind", model) and "single" not in model:
        rows.append(check("anonymity", "not_checked", f"the review is {model}: run check_anonymity.py on the files the "
                                                      "reviewers will see"))

    todo = gaps(record) + [f"Fill or remove the placeholder at {w}" for r in rows if r["check"] == "placeholders"
                           for w in r["where"]]
    todo += [f"Confirm by hand ({r['check']}): {r['detail']}" for r in rows
             if r["state"] == "not_checked" and r["check"] != "placeholders"]
    out = Path(args.out) if args.out else package
    out.mkdir(parents=True, exist_ok=True)
    counts = write_report(out / "report.md", requirements, manuscript, measured, rows, todo, args.final)
    print(json.dumps({"tool": TOOL, "venue": requirements.get("venue"), "final": args.final, "counts": counts,
                      "ok": counts["fail"] == 0, "report": str(out / "report.md"),
                      "measured": {name: value for name, (value, _, _) in measured["values"].items()},
                      "checks": rows, "for_authors": todo}, indent=2, ensure_ascii=False))
    return 1 if counts["fail"] else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a submission package against the requirements and the authors' record.")
    parser.add_argument("manuscript", nargs="?", help="The manuscript: .md, .tex, .txt or .docx")
    parser.add_argument("--package", help="The package folder, submission/<venue-slug>")
    parser.add_argument("--requirements", help="Requirements file (default: requirements.json in the package)")
    parser.add_argument("--authors", help="Authors file (default: authors.json in the package)")
    parser.add_argument("--final", action="store_true", help="The package is meant to be complete: placeholders fail")
    parser.add_argument("--out", help="Folder for report.md (default: the package folder)")
    parser.add_argument("--author-block", action="store_true",
                        help="Print a title page's author line and numbered affiliations from --authors, and stop")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Problem as problem:
        print(f"check_package: {problem}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
