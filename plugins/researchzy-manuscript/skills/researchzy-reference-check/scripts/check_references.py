#!/usr/bin/env python3
"""Check the references of a manuscript or a bibliography.

For every reference the script answers, with evidence from public registries: does the work
exist, does the cited identifier belong to it, and are its authors and year right. It also flags
retractions, corrections, update notices cited as if they were papers, preprints that have a
published version, duplicates and placeholders.

Input: BibTeX, LaTeX, Markdown, DOCX, PDF, plain text or TSV. Output, under --out:

  references.json  every reference with its verdict, evidence, differences and flags
  report.md        the same for people
  lookups.json     the Researchzy searches that would settle what the registries could not
  fixes.bib        for a BibTeX input, the entries with only the disagreeing fields corrected

Registries (all free, no key): Crossref, the doi.org handle registry, DataCite, arXiv, PubMed.
Researchzy search results the agent has saved are merged with --researchzy.

Verdicts
  confirmed                  a registry or index record matches the reference
  mismatch                   the work exists, but its authors, title, year or identifier disagree
  unconfirmed                nothing confirmed or refuted it; a failed lookup is never a refutation
  identifier_not_registered  the DOI, PMID or arXiv number exists in no registry, and no lookup
                             found the work some other way

Standard library only; reading a PDF needs PyMuPDF. Portions are derived from MIT-licensed code:
see LICENSE-MIT.txt next to this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from xml.etree import ElementTree as ET

CONFIRMED = "confirmed"
MISMATCH = "mismatch"
UNCONFIRMED = "unconfirmed"
NOT_REGISTERED = "identifier_not_registered"
VERDICTS = (NOT_REGISTERED, MISMATCH, UNCONFIRMED, CONFIRMED)  # the report's order, worst first

# `<>` belong to legacy SICI DOIs (10.1002/(SICI)...17:8<857::AID-SIM777>3.0.CO;2-E), whose
# check character after `;2-` can also be `#`. Without them a text reference's DOI was cut
# short, and a cut DOI is not registered anywhere, which the doi.org check below would
# report as not registered.
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:<>A-Z0-9]+(?:(?<=;2-)#|\b)", re.I)
WELL_FORMED_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
PMID_RE = re.compile(r"\bPMID\s*:?\s*(\d{5,9})\b", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# arXiv numbers: 2101.00001 (optionally v2) and the older hep-th/9901001 form.
ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z][a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?"
ARXIV_RE = re.compile(r"(?:arxiv\s*:\s*|arxiv\.org/(?:abs|pdf)/)(" + ARXIV_ID + ")", re.I)
# The DOI arXiv registers for a preprint. It is a DataCite DOI, so Crossref does not know it.
ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(" + ARXIV_ID + ")$", re.I)
YEAR_RE_ALL = re.compile(r"\b((?:19|20)\d{2})\b")


@dataclass
class RefRecord:
    ref_id: str
    raw: str
    title_guess: str = ""
    doi: str = ""
    pmid: str = ""
    arxiv: str = ""
    year_guess: str = ""
    first_author_guess: str = ""  # = cited_authors[0] when a list was parsed
    cited_authors: list = field(default_factory=list)   # family names as cited
    actual_authors: list = field(default_factory=list)  # family names in the matching record
    cited_author_count: int = 0
    actual_author_count: int = 0
    # The BibTeX `and others` sentinel: the list is deliberately short, so a cited list shorter
    # than the record's is expected and is reported as a note, not as a difference.
    audit_truncated: bool = False
    # Collective author (a guideline body, working group, consortium). BibTeX double-braces
    # these and PubMed returns them as <CollectiveName>; the personal-name comparison does not
    # apply to them.
    corporate_author: bool = False
    # True when title_guess came from a title field (BibTeX `title`, a TSV title column). Only
    # such a title is compared with the record an identifier resolves to: a title guessed from a
    # plain-text reference line is often the author list.
    title_from_field: bool = False
    entry: str = ""  # the BibTeX entry as written; used for fixes.bib and not exported
    # Where a reference without a parsed author list names its authors: the start of a
    # plain-text line, or a TSV author column. Not exported.
    author_text: str = ""
    status: str = UNCONFIRMED
    evidence: str = ""
    note: str = ""
    flags: list = field(default_factory=list)        # [{"flag", "detail"}]
    differences: list = field(default_factory=list)  # [{"field", "severity", "detail", ...}]
    found: dict = field(default_factory=dict)        # the matching record
    candidates: list = field(default_factory=list)   # nearest real papers when nothing matched
    researchzy: dict = field(default_factory=dict)   # the matching Researchzy record, if any


@dataclass
class Lookup:
    """What one registry or index said about one reference."""
    source: str
    status: str = UNCONFIRMED
    evidence: str = ""
    families: list = field(default_factory=list)
    # False when the source has names without a family field ("First Last" strings): such a list
    # supports a tolerant first-author check, never the strict position-by-position one.
    structured: bool = True
    titles: list = field(default_factory=list)
    years: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    record: dict = field(default_factory=dict)
    candidates: list = field(default_factory=list)
    title_only: bool = False  # matched by title, not by an identifier


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Organization / collective-author signal in an author field. Used (a) when a
# brace survives in the parsed BibTeX author field (double-brace convention) and
# (b) as a keyword fallback for single-braced or plain-text collective names.
_ORG_AUTHOR_RE = re.compile(
    r"\b(?:Group|Committee|Society|Association|Collaborat\w+|Consortium|Network|"
    r"Panel|Initiative|Organization|Organisation|Investigators|Trialists|Task\s+Force|"
    r"Working\s+Group|Study\s+Group|Foundation|Institute|Council|Federation|College|"
    r"WHO|EASL|EASD|EASO|KDIGO|AHA|ACC|ESC|NICE|AASLD|KASL)\b", re.IGNORECASE)


def is_corporate_author_field(author_field: str) -> bool:
    """A collective/corporate author (a guideline body, working group, consortium)
    rather than a list of people.

    Braces alone do NOT make an author corporate. Better BibTeX brace-protects a
    hyphenated or particle SURNAME so BibTeX will not re-case or re-split it —
    `author = {{Eckel-Passow}, Jeanette E. and {von Deimling}, Andreas}` — and the
    old brace-only rule read those as organizations and *skipped* the author
    cross-check entirely. That is a false PASS, not a false alarm: the check this
    tool exists to perform was silently not performed, and nothing said so.

    A field is corporate when it carries an organizational keyword, or when it is a
    single braced blob with no personal-name structure at all (no comma separating a
    surname from a given name, no `and`-joined list).
    """
    if not author_field:
        return False
    if _ORG_AUTHOR_RE.search(author_field):
        return True

    braced = "{" in author_field or "}" in author_field
    if not braced:
        return False

    # Personal-name structure survives brace-stripping -> these are people.
    bare = author_field.replace("{", "").replace("}", "")
    if "," in bare or re.search(r"\band\b", bare):
        return False

    # A lone braced blob with no keyword and no name structure (e.g. `{{ADNI}}`):
    # still treat as collective — skipping is the conservative outcome there.
    return True


def clean_doi(doi: str) -> str:
    return doi.rstrip(".,;)].").lower()


def normalize_doi_for_dup(doi: str, keep_trailing_slash: bool = False) -> str:
    """Strict DOI normalization for duplicate detection.

    Beyond clean_doi(): strips common URL prefixes and trailing slashes so that
    `https://doi.org/10.1234/abc/` and `10.1234/abc` collapse to the same key.
    A trailing slash is legal in a DOI, so a registry lookup also needs the form
    that keeps it (`keep_trailing_slash=True`).
    """
    if not doi:
        return ""
    s = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.strip()
    if not keep_trailing_slash:
        s = s.rstrip("/")
    return clean_doi(s)


def _fold_accents(text: str) -> str:
    """LaTeX accents and special letters as their plain letter: \\"{o} -> o, \\'e -> e, \\ss -> ss."""
    text = re.sub(r"\\(?:[\"'`~^=.]|[uvHtcdbk](?![a-zA-Z]))\s*\{?\\?([A-Za-z])\}?", r"\1", text)
    # LaTeX swallows the space after a control word: `Stra\\ss e` is "Straße".
    text = re.sub(r"\\(ss|ae|AE|aa|AA|oe|OE|o|O|l|L|i|j)(?![a-zA-Z])\s*",
                  lambda m: m.group(1)[0] if m.group(1) in ("aa", "AA") else m.group(1), text)
    return text.replace("\\&", "&").replace("\\%", "%").replace("\\_", "_").replace("\\#", "#").replace("~", " ")


def delatex(text: str) -> str:
    """A BibTeX field value as plain text: accents folded to their letter, braces and simple
    commands removed. Braces go without leaving a space, so `{D}eep {L}earning` reads
    `Deep Learning` and not `D eep L earning`."""
    text = _fold_accents(text)
    text = re.sub(r"\\(?:textit|emph|textbf|textsc|textrm|mathrm|text|mbox)\b\s*", "", text)
    text = re.sub(r"\$([^$]*)\$", r"\1", text)
    text = re.sub(r"[{}]", "", text)
    return normalize_space(text)


def strip_latex(text: str) -> str:
    """Readable text of a LaTeX fragment (a \\bibitem body): comments and command names go,
    their arguments stay."""
    text = re.sub(r"(?<!\\)%.*", "", text)
    text = _fold_accents(text.replace("}{", "} {"))
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = re.sub(r"[{}$]", "", text)
    return normalize_space(text)


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for p in root.findall(".//w:p", ns):
        parts = [t.text or "" for t in p.findall(".//w:t", ns)]
        if parts:
            paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def read_pdf(path: Path) -> str:
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            raise SystemExit("Reading a PDF needs PyMuPDF (pip install pymupdf). "
                             "Or save the reference list as text, one reference per line.")
    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def read_input(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return read_docx(path)
    if suffix == ".pdf":
        return read_pdf(path)
    return path.read_text(encoding="utf-8", errors="replace")


def brace_field(entry: str, name: str) -> str:
    """Read a brace-delimited BibTeX field by counting braces, not by regex.

    A non-greedy `{(.+?)}` stops at the first `}`, which truncates any brace-protected inner group
    (`title = {A multisociety {Delphi} consensus}`). Anchoring the match on a trailing comma avoids
    that but silently returns nothing when the field is the entry's LAST one, where BibTeX makes the
    comma optional. Counting depth is correct in both cases. Returns "" when the field is absent or
    is not brace-delimited.
    """
    m = re.search(rf"(?<![\w-]){name}\s*=\s*\{{", entry, re.I)
    if not m:
        return ""
    start = m.end()
    depth, j = 1, start
    while j < len(entry) and depth > 0:
        if entry[j] == "{":
            depth += 1
        elif entry[j] == "}":
            depth -= 1
        j += 1
    return entry[start : j - 1]


def bib_field(entry: str, name: str) -> str:
    """A BibTeX field's value, brace- or quote-delimited or bare (`year = 2020`)."""
    value = brace_field(entry, name)
    if value:
        return value
    m = re.search(rf'(?<![\w-]){name}\s*=\s*(?:"([^"]*)"|([^\s,{{}}"]+))', entry, re.I)
    return (m.group(1) or m.group(2) or "") if m else ""


# An entry opens with `@type{` or `@type(`. BibTeX allows whitespace before the `@`, between the
# type and the delimiter, and the parenthesised form; splitting only at a column-0 `@type{` merged
# every such entry into the one before it, so only the first was ever looked up.
BIB_ENTRY_HEAD_RE = re.compile(r"@[ \t]*(\w+)\s*([{(])")
# Not references: string macros, preamble, and comments. They are skipped, not audited.
BIB_NON_ENTRY_TYPES = ("comment", "string", "preamble")


def _bib_entry_end(text: str, i: int, opener: str) -> int:
    """Index just past the delimiter that closes the entry body starting at text[i].

    `@` inside a field value is text to BibTeX ("{Hospital} @ Home ({HaH})", an e-mail address),
    so the body is walked by brace depth and only its own closing delimiter ends the entry.
    Returns -1 when the body never closes.
    """
    depth, quoted, n = 0, False, len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return i + 1 if opener == "{" else -1
            depth -= 1
        elif opener == "(" and depth == 0:
            if c == '"':
                quoted = not quoted
            elif c == ")" and not quoted:
                return i + 1
        i += 1
    return -1


def _bib_entry_starts(text: str) -> list[int]:
    """Offsets of the entry headers in `text`, in order.

    Between entries a header counts when only whitespace precedes it on its line, or only
    whitespace separates it from the previous entry's closing delimiter (`} @article{b,`).
    Inside an entry's body an `@` is field text, never a header. One exception keeps what the
    old column-0 split always did: a `@type{` at column 0 starts an entry even inside a body
    that has not closed yet, so one unbalanced brace cannot swallow the rest of the file.
    """
    col0 = [m.start() for m in re.finditer(r"^@\w+\{", text, re.M)]
    starts: list[int] = []
    pos, prev_end = 0, -1
    while True:
        m = BIB_ENTRY_HEAD_RE.search(text, pos)
        if not m:
            return starts
        line_start = text.rfind("\n", 0, m.start()) + 1
        after_prev = prev_end >= 0 and not text[prev_end:m.start()].strip()
        if text[line_start:m.start()].strip() and not after_prev:
            pos = m.start() + 1
            continue
        starts.append(m.start())
        end = _bib_entry_end(text, m.end(), m.group(2))
        nxt = next((c for c in col0 if c > m.start()), -1)
        if end < 0 or 0 <= nxt < end:
            # The body has not closed before the next column-0 header: resume there.
            if nxt < 0:
                return starts
            pos, prev_end = nxt, -1
            continue
        pos, prev_end = end, end


def bib_arxiv(entry: str) -> str:
    """The arXiv number of a BibTeX entry: an `eprint` field, an arXiv URL or `arXiv:` text."""
    eprint = bib_field(entry, "eprint").strip()
    kind = (bib_field(entry, "archiveprefix") or bib_field(entry, "eprinttype")).strip().lower()
    if eprint and kind in ("", "arxiv") and re.fullmatch(ARXIV_ID, eprint, re.I):
        return eprint
    m = ARXIV_RE.search(entry)
    return m.group(1) if m else ""


def parse_bib(text: str) -> list[RefRecord]:
    records: list[RefRecord] = []
    starts = _bib_entry_starts(text)
    entries = [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]
    for entry in entries:
        entry = entry.strip()
        kind = re.match(r"@[ \t]*(\w+)", entry)
        if not kind or kind.group(1).lower() in BIB_NON_ENTRY_TYPES:
            continue
        key_match = re.match(r"@[ \t]*\w+\s*[{(]\s*([^,]+?)\s*,", entry)
        author_field = bib_field(entry, "author")
        title_text = bib_field(entry, "title")
        doi = bib_field(entry, "doi")
        pmid_match = re.search(r"(?<![\w-])pmid\s*=\s*[\{\"]?(\d{5,9})", entry, re.I)
        # biblatex writes `date = {2020-05-01}` where BibTeX writes `year`.
        year_match = (re.search(r"(?<![\w-])year\s*=\s*[\{\"]?((?:19|20)\d{2})", entry, re.I)
                      or re.search(r"(?<![\w-])date\s*=\s*[\{\"]?((?:19|20)\d{2})", entry, re.I))
        cited = parse_bib_authors(author_field)
        records.append(
            RefRecord(
                ref_id=key_match.group(1) if key_match else f"ref_{len(records)+1}",
                raw=normalize_space(entry),
                title_guess=delatex(title_text),
                title_from_field=bool(title_text.strip()),
                doi=normalize_doi_for_dup(delatex(doi)) if doi else "",
                pmid=pmid_match.group(1) if pmid_match else "",
                arxiv=bib_arxiv(entry),
                year_guess=year_match.group(1) if year_match else "",
                first_author_guess=cited[0] if cited else (parse_first_author(author_field) if author_field else ""),
                cited_authors=cited,
                cited_author_count=len(cited),
                audit_truncated=has_bibtex_et_al(author_field),
                corporate_author=is_corporate_author_field(author_field),
                entry=entry,
            )
        )
    return records


def parse_tsv(text: str) -> list[RefRecord]:
    rows = list(csv.DictReader(text.splitlines(), delimiter="\t"))
    records: list[RefRecord] = []
    for i, row in enumerate(rows, 1):
        low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        joined = " ".join(v for v in low.values() if v)
        title = low.get("title", "")
        author_field = low.get("author") or low.get("authors") or ""
        arxiv = ARXIV_RE.search(joined)
        year = YEAR_RE.search(low.get("year", ""))
        records.append(
            RefRecord(
                ref_id=low.get("id") or low.get("key") or f"ref_{i}",
                raw=normalize_space(joined),
                title_guess=title,
                title_from_field=bool(title),
                doi=normalize_doi_for_dup(low.get("doi", "")),
                pmid=re.sub(r"\D", "", low.get("pmid", "")),
                arxiv=low.get("arxiv") or (arxiv.group(1) if arxiv else ""),
                year_guess=year.group(0) if year else "",
                first_author_guess=parse_first_author(author_field) if author_field else "",
                corporate_author=is_corporate_author_field(author_field),
                author_text=author_field,
            )
        )
    return records


# A bare "References" line, or a Markdown heading ("## References", "**References**",
# Quarto's "# References {.unnumbered}"). Missing the heading form parsed the whole .md/.qmd,
# so body paragraphs and bullets became references (all unconfirmed).
REFERENCE_HEADING_RE = re.compile(
    r"(?im)^[ \t]*(#{1,6})?[ \t]*\**[ \t]*(?:references|bibliography|reference list)"
    r"[ \t]*\**[ \t]*:?[ \t]*(?:\{[^}\n]*\})?[ \t]*$"
)


def reference_section(text: str) -> str:
    match = REFERENCE_HEADING_RE.search(text)
    if not match:
        return text
    section = text[match.end() :]
    # The list ends at the next heading of the same or a higher level (Tables, Figure
    # Legends); after a bare "References" line, at any Markdown heading.
    level = len(match.group(1) or "") or 6
    end = re.search(rf"(?m)^[ \t]*#{{1,{level}}}[ \t]", section)
    return section[: end.start()] if end else section


def reference_line_record(ref_id: str, raw: str) -> RefRecord:
    raw = normalize_space(raw)
    doi_match = DOI_RE.search(raw)
    pmid_match = PMID_RE.search(raw)
    arxiv_match = ARXIV_RE.search(raw)
    year_match = YEAR_RE.search(raw)
    return RefRecord(
        ref_id=ref_id,
        raw=raw,
        title_guess=guess_title(raw),
        doi=clean_doi(doi_match.group(0)) if doi_match else "",
        pmid=pmid_match.group(1) if pmid_match else "",
        arxiv=arxiv_match.group(1) if arxiv_match else "",
        year_guess=year_match.group(0) if year_match else "",
        first_author_guess=parse_first_author(raw),
        author_text=re.sub(r"^(\[\d+\]|\d+[\.\)]|\-\s+)\s*", "", raw)[:250],
    )


def parse_reference_lines(text: str) -> list[RefRecord]:
    section = reference_section(text)
    lines = [normalize_space(line) for line in section.splitlines()]
    candidates: list[str] = []
    current = ""
    for line in lines:
        if not line:
            continue
        starts_ref = bool(re.match(r"^(\[\d+\]|\d+[\.\)]|\-\s+)", line))
        if starts_ref and current:
            candidates.append(current)
            current = line
        else:
            current = f"{current} {line}".strip() if current else line
    if current:
        candidates.append(current)

    if len(candidates) < 2:
        candidates = [line for line in lines if DOI_RE.search(line) or PMID_RE.search(line) or len(line) > 60]

    # A numbered list keeps its own numbers, so that [12] in the text finds reference 12.
    numbers = [re.match(r"^\[?(\d+)[\]\.\)]\s", raw) for raw in candidates]
    own = all(numbers) and len({m.group(1) for m in numbers}) == len(numbers)
    return [reference_line_record(f"ref_{numbers[i].group(1) if own else i + 1}", raw)
            for i, raw in enumerate(candidates)]


def parse_bibitems(tex: str) -> list[RefRecord]:
    """The entries of a LaTeX `thebibliography` environment."""
    body = re.search(r"\\begin\{thebibliography\}(.*?)\\end\{thebibliography\}", tex, re.S)
    if not body:
        return []
    parts = re.split(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", body.group(1))
    records = []
    for key, text in zip(parts[1::2], parts[2::2]):
        record = reference_line_record(key.strip() or f"ref_{len(records)+1}", strip_latex(text))
        records.append(record)
    return records


def tex_bib_files(tex: str, base: Path) -> list[Path]:
    """The .bib files a LaTeX source names with \\bibliography or \\addbibresource."""
    names: list[str] = []
    for m in re.finditer(r"\\(?:bibliography|addbibresource)(?:\[[^\]]*\])?\{([^}]+)\}",
                         re.sub(r"(?<!\\)%.*", "", tex)):
        names += [n.strip() for n in m.group(1).split(",") if n.strip()]
    paths = []
    for name in names:
        path = base / (name if name.lower().endswith(".bib") else name + ".bib")
        if path.exists() and path not in paths:
            paths.append(path)
    return paths


_NAME_PARTICLES = {"von", "van", "de", "del", "della", "dos", "da", "le", "la", "du", "den", "der", "ten"}


def has_bibtex_et_al(author_field: str) -> bool:
    """True when the author field ends in the BibTeX `and others` sentinel.

    `and others` is BibTeX's own way of saying "et al." — it is what Zotero,
    Mendeley, JabRef and a hand-written .bib all emit for a list the author chose
    not to type out, and what BibTeX and CSL both render as an et-al. It is a
    declaration that the list is deliberately short, so a cited-vs-source count
    difference is expected and must not be reported as a mismatch.

    Matched only in the trailing position, where BibTeX defines it. A real surname
    "Others" mid-list (or a first name "Others") is not this sentinel and is left
    to the ordinary family cross-check.
    """
    if not author_field:
        return False
    return bool(re.search(r"\s+and\s+others\s*$", re.sub(r"\s+", " ", author_field).strip(), re.I))


def parse_bib_authors(author_field: str) -> list:
    """Parse BibTeX author field into a list of family-name strings.

    Handles "Last, First and Last, First" and "First Last and First Last" forms.
    Strips simple LaTeX accents and braces.
    """
    if not author_field:
        return []
    raw = re.sub(r"\s+", " ", author_field).strip()
    parts = re.split(r"\s+and\s+", raw)
    families: list[str] = []
    for name in parts:
        n = name.strip()
        if not n:
            continue
        if "," in n:
            family = n.split(",", 1)[0].strip()
        else:
            toks = n.split()
            family = toks[-1] if toks else ""
        # Strip simple LaTeX accents: \~{n}, \"{o}, \`{a} → underlying char
        family = re.sub(r"\\[\"'`~^=.]?\{?([A-Za-zà-ÿ])\}?", r"\1", family)
        family = re.sub(r"[{}]", "", family).strip()
        if family and family != "others":
            families.append(family)
    return families


def parse_first_author(raw: str) -> str:
    """Extract first-author surname from a Vancouver/AMA/BibTeX-style citation.

    Conservative: returns "" when the format is ambiguous so author-mismatch
    checks degrade gracefully rather than reporting false mismatches.
    """
    text = re.sub(r"^\s*(\[\d+\]|\d+[\.\)])\s*", "", raw).strip()
    bib_m = re.search(r"author\s*=\s*[{\"]([^}\"]+)", text, re.I)
    if bib_m:
        text = bib_m.group(1)
    text = re.split(r"\s+and\s+", text, maxsplit=1)[0]
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return ""
    # "Lastname, Firstname H." style (BibTeX expanded)
    if len(parts) >= 2 and re.match(r"^[A-Z][a-zA-Z .\-']*$", parts[1]) and not re.search(r"\d", parts[1]):
        if re.match(r"^[A-Z][a-zA-Zà-ÿ'\- ]+$", parts[0]):
            return parts[0].strip()
    first = parts[0]
    # "Surname Initials" — strip trailing initials block (e.g., "DH", "J", "F.D.")
    m = re.match(
        r"^((?:(?:" + "|".join(_NAME_PARTICLES) + r")\s+)?[A-Zà-ÿ][\wà-ÿ'\-]*(?:\s+[A-Zà-ÿ][\wà-ÿ'\-]*)?)\s+(?:[A-Z]\.?\s*){1,4}$",
        first,
    )
    if m:
        return m.group(1).strip()
    tokens = first.split()
    if tokens and tokens[0].lower() in _NAME_PARTICLES and len(tokens) >= 2:
        return f"{tokens[0]} {tokens[1]}"
    return tokens[0] if tokens else ""


def _normalize_surname(name: str) -> str:
    """Strip diacritics + lowercase for surname comparison.

    Coverage: Latin-with-accents (NFKD decomposes), Turkish
    (ş→s, ğ→g, ı→i), Polish/Czech (ł, đ — not NFKD-decomposable, handled below),
    German ß→ss, Nordic ø/æ/œ → o/ae/oe. Motivation: a Turkish surname
    `Çolakoğlu` vs PubMed `Colakoglu` was a false mismatch.

    Unicode dashes are folded to ASCII `-` FIRST. The final filter keeps `[a-z\\s-]`
    and deletes everything else, so a publisher-supplied U+2010 in a hyphenated
    surname was *deleted* rather than matched: CrossRef `Foltyn‐Dumitru` normalized
    to `foltyndumitru` while the identical ASCII bib entry gave `foltyn-dumitru`,
    and a clean reference was reported as a mismatch.
    """
    import unicodedata
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower().strip()
    # Unicode dash/hyphen variants -> ASCII hyphen. Publisher metadata uses these
    # freely in hyphenated surnames (U+2010 HYPHEN, U+2011 NON-BREAKING HYPHEN,
    # U+2012 FIGURE DASH, U+2013 EN DASH, U+2014 EM DASH, U+2212 MINUS).
    n = re.sub(r"[‐‑‒–—―−﹘﹣－]", "-", n)
    # Multi-char + non-NFKD-decomposable mappings
    multi = {
        "ß": "ss", "þ": "th", "ł": "l", "đ": "d", "ı": "i",
        "ø": "o", "æ": "ae", "œ": "oe",
    }
    for k, v in multi.items():
        n = n.replace(k, v)
    n = re.sub(r"[^a-z\s\-]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def author_surnames_match(cited: str, actual: str) -> bool:
    """Tolerant comparison: handles particle variants and hyphenation."""
    if not cited or not actual:
        return True  # cannot judge → do not flag
    a = _normalize_surname(cited)
    b = _normalize_surname(actual)
    if not a or not b:
        return True
    if a == b:
        return True
    # Particle-stripped variants ("von elm" vs "elm")
    a_core = re.sub(r"^(?:" + "|".join(_NAME_PARTICLES) + r")\s+", "", a)
    b_core = re.sub(r"^(?:" + "|".join(_NAME_PARTICLES) + r")\s+", "", b)
    if a_core and b_core and a_core == b_core:
        return True
    # One name is a whole-word part of the other ("Garcia" vs "Garcia-Lopez", "Berg" vs
    # "van der Berg"). Containment is accepted only at a space or hyphen boundary: raw substring
    # containment let any short surname match any longer one that spells it ("Li" vs
    # "Williams", "Kim" vs "Kimura"), so a fabricated co-author passed the positional check.
    a_words = [w for w in re.split(r"[\s-]+", a_core) if w]
    b_words = [w for w in re.split(r"[\s-]+", b_core) if w]
    if a_words and b_words and (set(a_words) <= set(b_words) or set(b_words) <= set(a_words)):
        return True
    # Hyphen vs space vs run-together ("Abd-alrazaq" vs "abd alrazaq", "Dela Cruz" vs "De la Cruz")
    if re.sub(r"[\s-]", "", a) == re.sub(r"[\s-]", "", b):
        return True
    return False


def guess_title(raw: str) -> str:
    no_prefix = re.sub(r"^(\[\d+\]|\d+[\.\)]|\-\s+)\s*", "", raw)
    parts = [p.strip() for p in re.split(r"\.\s+", no_prefix) if p.strip()]
    for part in parts:
        words = part.split()
        if 4 <= len(words) <= 30 and not re.search(r"\b(doi|pmid|journal|vol)\b", part, re.I):
            return part.strip('"')
    return ""


# ---------------------------------------------------------------------------------------------
# HTTP


class Client:
    """GET with a courtesy User-Agent, a pause per host, one retry on 429/503, and a cache of
    definite answers (200 and 404), so an interrupted run resumes without asking again."""

    PAUSE = {"export.arxiv.org": 3.0}  # arXiv asks for three seconds between requests
    DEFAULT_PAUSE = 0.2

    def __init__(self) -> None:
        self.timeout = 15
        self.contact = ""
        self.cache: dict = {}
        self.calls = 0
        self.sleep = time.sleep
        self.opener = self._open
        self._last: dict = {}

    def user_agent(self) -> str:
        agent = "researchzy-reference-check/1.0 (https://github.com/Researchzy/Researchzy-academic-skills"
        return agent + (f"; mailto:{self.contact})" if self.contact else ")")

    def _open(self, url: str, timeout: int):
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent()})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as err:
            try:
                body = err.read()
            except Exception:
                body = b""
            return err.code, body, dict(err.headers or {})
        except Exception:
            return None, b"", {}

    def get(self, url: str) -> tuple[int | None, str]:
        """(HTTP status, body text). The status is None when no response arrived. A 404 is an
        answer ("no such record"), so it is returned and cached like a 200."""
        hit = self.cache.get(url)
        if hit:
            return hit["status"], hit["body"]
        host = urllib.parse.urlsplit(url).netloc
        status, body = None, b""
        for attempt in (1, 2):
            wait = self._last.get(host, 0.0) + self.PAUSE.get(host, self.DEFAULT_PAUSE) - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            status, body, headers = self.opener(url, self.timeout)
            self._last[host] = time.monotonic()
            self.calls += 1
            if status in (429, 503) and attempt == 1:
                try:
                    delay = float(headers.get("Retry-After") or 5)
                except (TypeError, ValueError):
                    delay = 5.0
                self.sleep(min(delay, 30.0))
                continue
            break
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) else (body or "")
        if status in (200, 404):
            self.cache[url] = {"status": status, "body": text}
        return status, text

    def load_cache(self, path: Path) -> None:
        try:
            self.cache = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.cache = {}

    def save_cache(self, path: Path) -> None:
        path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")


CLIENT = Client()


def get_json(url: str) -> tuple[int | None, dict | None]:
    status, text = CLIENT.get(url)
    try:
        data = json.loads(text) if text else None
    except ValueError:
        data = None
    return status, data if isinstance(data, dict) else None


def _ncbi_extras() -> dict:
    """NCBI's courtesy parameters. NCBI_API_KEY, when set, raises PubMed's rate limit; the
    lookups work without it."""
    extra = {"tool": "researchzy-reference-check"}
    if CLIENT.contact:
        extra["email"] = CLIENT.contact
    if os.environ.get("NCBI_API_KEY"):
        extra["api_key"] = os.environ["NCBI_API_KEY"]
    return extra


# ---------------------------------------------------------------------------------------------
# Registries


def crossref_year(msg: dict) -> str:
    """The year to show for a CrossRef record: print, then online, then issued.

    `issued` is the EARLIEST publication date, so an article published online in December
    and in a print issue the next January reports the online year there, while journals
    cite the issue year. Showing `issued` alone invites "correcting" a bib year that was
    right. When the candidates disagree, both are shown, e.g. "2023 (print; online 2022)".
    """
    years: list[tuple[str, str]] = []
    for field_name, label in (("published-print", "print"), ("published-online", "online"),
                              ("issued", "issued")):
        parts = ((msg.get(field_name) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            years.append((label, str(parts[0])))
    if not years:
        return ""
    primary_label, primary = years[0]
    others: list[tuple[str, str]] = []
    for label, value in years[1:]:
        if value != primary and all(value != seen for _, seen in others):
            others.append((label, value))
    if not others:
        return primary
    return f"{primary} ({primary_label}; " + "; ".join(f"{l} {v}" for l, v in others) + ")"


def crossref_titles(msg: dict) -> list:
    """Every title a CrossRef record answers to.

    CrossRef keeps a subtitle in its own field, so the cited "Main: Sub" is matched against
    the joined form as well as the bare title; a translated work carries `original-title`; and
    a chapter DOI cited by its book's title is not a different work.
    """
    main = [t for t in (msg.get("title") or []) if t]
    out = list(main)
    out += [f"{m}: {sub}" for m in main for sub in (msg.get("subtitle") or []) if sub]
    out += [t for t in (msg.get("original-title") or []) + (msg.get("short-title") or []) if t]
    if msg.get("type") in ("book-chapter", "book-section", "book-part", "reference-entry"):
        out += [t for t in (msg.get("container-title") or []) if t]
    return out


# Crossref's update types (its Crossmark vocabulary, which also carries Retraction Watch data).
UPDATE_FLAGS = {
    "retraction": "retracted", "removal": "retracted", "withdrawal": "retracted",
    "partial_retraction": "partly_retracted",
    "expression_of_concern": "expression_of_concern",
    "correction": "corrected", "corrigendum": "corrected", "erratum": "corrected",
    "addendum": "corrected", "clarification": "corrected",
}


def _update_date(update: dict) -> str:
    parts = ((update.get("updated") or {}).get("date-parts") or [[]])[0]
    return "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts) if p)


def crossref_flags(msg: dict) -> list:
    flags: list = []
    for update in msg.get("updated-by") or []:
        kind = re.sub(r"[\s-]+", "_", (update.get("type") or "").lower())
        flag = UPDATE_FLAGS.get(kind)
        if flag:
            when = _update_date(update)
            flags.append({"flag": flag, "detail": f"{update.get('label') or kind} notice "
                          f"doi:{(update.get('DOI') or '').lower()}" + (f" ({when})" if when else "")})
    for update in msg.get("update-to") or []:
        kind = re.sub(r"[\s-]+", "_", (update.get("type") or "").lower())
        flags.append({"flag": "update_notice", "detail": f"this DOI is a {kind or 'update'} notice "
                      f"for doi:{(update.get('DOI') or '').lower()}, not the paper itself"})
    published = [r.get("id", "") for r in (msg.get("relation") or {}).get("is-preprint-of") or []
                 if r.get("id")]
    if published:
        flags.append({"flag": "preprint_published",
                      "detail": "published version: doi:" + ", doi:".join(p.lower() for p in published)})
    title = " ".join(msg.get("title") or [])
    if re.match(r"\s*(RETRACTED|WITHDRAWN)\b", title) and not any(f["flag"] == "retracted" for f in flags):
        flags.append({"flag": "retracted", "detail": "the registry title is marked " + title.split(":")[0].strip()})
    return flags


def crossref_record(msg: dict, how: str, source: str = "crossref") -> Lookup:
    """A Crossref work as a Lookup. Crossref has a family field for every personal author; its
    given names are less reliable than PubMed's."""
    authors = []
    for a in msg.get("author") or []:
        family = (a.get("family") or a.get("name") or "").strip()
        if family:
            authors.append({"family": family, "given": (a.get("given") or "").strip(),
                            "corporate": not a.get("family")})
    years = set()
    for key in ("published-print", "published-online", "issued", "published"):
        parts = ((msg.get(key) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            years.add(int(parts[0]))
    doi = (msg.get("DOI") or "").lower()
    titles = crossref_titles(msg)
    look = Lookup(source, CONFIRMED)
    look.families = [a["family"] for a in authors]
    look.titles = titles
    look.years = sorted(years)
    look.flags = crossref_flags(msg)
    look.record = {
        "source": source, "doi": doi, "url": f"https://doi.org/{doi}" if doi else "",
        "title": clean_markup(titles[0]) if titles else "", "year": crossref_year(msg),
        "container": clean_markup(" ".join((msg.get("container-title") or [])[:1])),
        "type": msg.get("type") or "", "authors": authors,
    }
    look.evidence = how
    if titles:
        look.evidence += f"; title={look.record['title'][:120]}"
    if look.record["year"]:
        look.evidence += f"; year={look.record['year']}"
    if authors:
        look.evidence += f"; authors={len(authors)} (first={authors[0]['family']})"
    return look


def lookup_crossref(doi: str) -> Lookup:
    status, data = get_json("https://api.crossref.org/works/" + urllib.parse.quote(doi))
    if status == 404:
        return lookup_doi_handle(doi)
    if status != 200 or not data or data.get("status") != "ok":
        return Lookup("crossref", UNCONFIRMED, "Crossref DOI lookup failed")
    return crossref_record(data.get("message") or {}, "Crossref DOI found")


def lookup_doi_handle(doi: str) -> Lookup:
    """A DOI Crossref answered 404 for: ask the DOI handle registry whether it exists at all.

    Crossref is one of several registration agencies (DataCite, mEDRA, JaLC, ...), so its 404
    alone proves nothing. doi.org's handle API resolves across all of them: HTTP 404 with
    responseCode 100 means the DOI is registered nowhere. A DOI registered elsewhere is passed
    to DataCite; any other answer (5xx, unexpected JSON), a network error, or a string that is
    not a well-formed DOI (a placeholder such as "n/a") leaves the reference unconfirmed. A DOI
    may legally end in "/", which normalization strips, so the cited form is looked up too: the
    DOI is unregistered only when every form is. A legacy SICI DOI that is not found stays
    unconfirmed: its punctuation is easily cut in extraction.
    """
    handle = normalize_doi_for_dup(doi)
    if not WELL_FORMED_DOI_RE.match(handle):
        return Lookup("doi.org", UNCONFIRMED, "Crossref 404; not a well-formed DOI, doi.org not consulted")
    answers = []
    for form in dict.fromkeys([handle, normalize_doi_for_dup(doi, keep_trailing_slash=True)]):
        status, data = get_json("https://doi.org/api/handles/" + urllib.parse.quote(form))
        code = data.get("responseCode") if data else None
        answers.append("found" if (status, code) == (200, 1)
                       else "not_found" if (status, code) == (404, 100) else "failed")
    if "found" in answers:
        return lookup_datacite(handle)
    if "failed" in answers:
        return Lookup("doi.org", UNCONFIRMED, "Crossref 404; doi.org handle lookup failed")
    if "(sici)" in handle:
        return Lookup("doi.org", UNCONFIRMED, "Crossref 404; doi.org handle not found, but a legacy "
                      "SICI DOI; extraction may be incomplete")
    return Lookup("doi.org", NOT_REGISTERED,
                  "DOI does not exist in any registry (Crossref 404; doi.org handle not found)")


def lookup_datacite(doi: str) -> Lookup:
    """A DOI that doi.org knows and Crossref does not: datasets, software, theses and preprint
    servers mostly register with DataCite."""
    elsewhere = "Crossref 404; DOI registered with another agency (doi.org handle found)"
    status, data = get_json("https://api.datacite.org/dois/" + urllib.parse.quote(doi))
    attrs = ((data or {}).get("data") or {}).get("attributes") or {}
    if status != 200 or not attrs:
        return Lookup("doi.org", UNCONFIRMED, elsewhere + ("; DataCite has no record of it" if status == 404
                                                           else "; DataCite lookup failed"))
    authors = []
    for c in attrs.get("creators") or []:
        corporate = (c.get("nameType") or "") == "Organizational"
        family = (c.get("familyName") or "").strip()
        name = (c.get("name") or "").strip()
        if not family and name:
            family = name if corporate or "," not in name else name.split(",", 1)[0].strip()
        if family:
            authors.append({"family": family, "given": (c.get("givenName") or "").strip(),
                            "corporate": corporate or not c.get("familyName") and "," not in name})
    titles = [t.get("title") for t in attrs.get("titles") or [] if t.get("title")]
    year = attrs.get("publicationYear")
    look = Lookup("datacite", CONFIRMED)
    look.families = [a["family"] for a in authors]
    look.titles = titles
    look.years = [int(year)] if str(year or "").isdigit() else []
    look.record = {
        "source": "datacite", "doi": doi, "url": f"https://doi.org/{doi}",
        "title": titles[0] if titles else "", "year": str(year or ""),
        "container": attrs.get("publisher") if isinstance(attrs.get("publisher"), str) else "",
        "type": (attrs.get("types") or {}).get("resourceTypeGeneral") or "", "authors": authors,
    }
    look.evidence = "DataCite DOI found" + (f"; title={titles[0][:120]}" if titles else "") \
        + (f"; year={year}" if year else "") \
        + (f"; authors={len(authors)} (first={authors[0]['family']})" if authors else "")
    return look


def lookup_arxiv(arxiv_id: str) -> Lookup:
    """arXiv's own record of a preprint. A version suffix names the same paper."""
    base = re.sub(r"v\d+$", "", arxiv_id.strip(), flags=re.I)
    status, text = CLIENT.get("https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(base))
    if status != 200 or "<feed" not in text:
        return Lookup("arxiv", UNCONFIRMED, "arXiv lookup failed")
    entries = re.findall(r"<entry>(.*?)</entry>", text, re.S)
    if entries and "api/errors" in entries[0]:
        return Lookup("arxiv", UNCONFIRMED, "arXiv did not accept this identifier")
    if not entries:
        return Lookup("arxiv", NOT_REGISTERED, "arXiv has no paper with this number")
    entry = entries[0]

    def first(tag: str) -> str:
        m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", entry, re.S)
        return normalize_space(html.unescape(m.group(1))) if m else ""

    names = [normalize_space(html.unescape(n)) for n in re.findall(r"<name>(.*?)</name>", entry, re.S)]
    title, published = first("title"), first("published")
    journal_doi, journal_ref = first("arxiv:doi"), first("arxiv:journal_ref")
    look = Lookup("arxiv", CONFIRMED, structured=False)
    look.families = [n for n in names if n]
    look.titles = [title] if title else []
    look.years = sorted({int(y) for y in [published[:4]] + YEAR_RE_ALL.findall(journal_ref) if y.isdigit()})
    if journal_doi or journal_ref:
        look.flags.append({"flag": "preprint_published", "detail": "published version: "
                           + (f"doi:{journal_doi.lower()}" if journal_doi else journal_ref)})
    look.record = {"source": "arxiv", "arxiv": base, "doi": journal_doi.lower(),
                   "url": f"https://arxiv.org/abs/{base}", "title": title, "year": published[:4],
                   "container": journal_ref, "type": "preprint",
                   "authors": [{"name": n} for n in look.families]}
    look.evidence = f"arXiv {base} found; title={title[:120]}; year={published[:4]}; authors={len(names)}"
    return look


def _esummary_families(item: dict) -> list[str]:
    """Family names from one esummary record ("Surname Initials" -> "Surname"), personal authors only."""
    families: list[str] = []
    for a in item.get("authors") or []:
        if a.get("authtype") not in (None, "Author"):
            continue
        full = (a.get("name") or "").strip()
        # esummary "name" is "Surname Initials" e.g. "Reichheld FF"
        m = re.match(r"^(.+?)\s+[A-Z]{1,4}$", full)
        fam = m.group(1).strip() if m else full
        if fam:
            families.append(fam)
    return families


PUBMED_NOTICE_TYPES = {"Retraction of Publication": "retraction", "Published Erratum": "correction",
                       "Expression of Concern": "expression of concern"}
PUBMED_COMMENT_FLAGS = {"RetractionIn": "retracted", "ErratumIn": "corrected",
                        "ExpressionOfConcernIn": "expression_of_concern"}


def lookup_pubmed(pmid: str) -> Lookup:
    """PubMed's record of a PMID. esummary decides whether the PMID exists (its "error" item is
    decisive); efetch supplies the structured author list, which is the most reliable one for
    biomedical papers, and the retraction and erratum links."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    status, data = get_json(base + "esummary.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": pmid, "retmode": "json", **_ncbi_extras()}))
    if status != 200 or not data:
        return Lookup("pubmed", UNCONFIRMED, "PubMed PMID lookup failed")
    item = (data.get("result") or {}).get(pmid)
    if not item or item.get("error"):
        return Lookup("pubmed", NOT_REGISTERED, "PMID not found in PubMed")
    title = html.unescape(item.get("title", ""))
    look = Lookup("pubmed", CONFIRMED)
    look.titles = [t for t in (title, html.unescape(item.get("vernaculartitle") or ""),
                               html.unescape(item.get("booktitle") or "")) if t]
    look.families = _esummary_families(item)
    look.years = sorted({int(y) for y in YEAR_RE_ALL.findall(
        f"{item.get('pubdate', '')} {item.get('epubdate', '')}")})
    for kind in item.get("pubtype") or []:
        if kind == "Retracted Publication":
            look.flags.append({"flag": "retracted", "detail": "PubMed marks this record Retracted Publication"})
        elif kind in PUBMED_NOTICE_TYPES:
            look.flags.append({"flag": "update_notice", "detail": f"this PMID is a "
                               f"{PUBMED_NOTICE_TYPES[kind]} notice, not the paper itself"})
    doi = next((i.get("value", "") for i in item.get("articleids") or [] if i.get("idtype") == "doi"), "")
    authors = [{"family": f, "given": ""} for f in look.families]

    status, xml_text = CLIENT.get(base + "efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": pmid, "retmode": "xml", **_ncbi_extras()}))
    if status == 200:
        fetched = []
        for am in re.finditer(r'<Author\s+ValidYN="Y"[^>]*>(.*?)</Author>', xml_text, re.S):
            lm = re.search(r"<LastName>([^<]+)</LastName>", am.group(1))
            fm = re.search(r"<ForeName>([^<]+)</ForeName>", am.group(1))
            if lm:
                fetched.append({"family": html.unescape(lm.group(1)).strip(),
                                "given": html.unescape(fm.group(1)).strip() if fm else ""})
        if fetched:
            authors, look.families = fetched, [a["family"] for a in fetched]
        for tag in ("ArticleTitle", "VernacularTitle", "BookTitle"):
            for tm in re.finditer(rf"<{tag}\b[^>]*>(.*?)</{tag}>", xml_text, re.S):
                look.titles.append(html.unescape(tm.group(1)))
        for kind in re.findall(r'<CommentsCorrections\s+RefType="(\w+)"', xml_text):
            flag = PUBMED_COMMENT_FLAGS.get(kind)
            if flag and not any(f["flag"] == flag for f in look.flags):
                look.flags.append({"flag": flag, "detail": f"PubMed links a notice to this record ({kind})"})
    look.record = {"source": "pubmed", "pmid": pmid, "doi": doi.lower(),
                   "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "title": title,
                   "year": str(look.years[0]) if look.years else "",
                   "container": item.get("fulljournalname") or item.get("source") or "",
                   "type": "journal-article", "authors": authors}
    look.evidence = f"PubMed PMID found; title={title[:120]}; authors={len(look.families)}" \
        + (f" (first={look.families[0]})" if look.families else "")
    return look


# Minimum _title_similarity for a title-search hit to count as the cited work (the Crossref
# and Researchzy title searches share it).
TITLE_MATCH_MIN = 0.8


# Connective words ignored by _title_similarity. Other short tokens stay: CT, MR, US, AI, HR
# and single digits are what tells two otherwise identical titles apart.
_TITLE_STOPWORDS = frozenset(
    "a an the of in on to for and or by with at as is vs from".split())


def _title_similarity(a: str, b: str) -> float:
    """Token Jaccard on normalized titles (stdlib-only).

    Guards title-search matches: a made-up title must not be confirmed just because a
    search returned some unrelated work. Connective
    stopwords are dropped so they do not inflate similarity, and a possessive "'s" is
    removed first so "Alzheimer's" and "Alzheimer" agree. Every other token counts, however
    short: dropping tokens of <=2 characters made "... in CT" match "... in MR", and dropping
    single letters made "hepatitis B" match "hepatitis C".
    """
    def toks(s: str) -> set:
        s = re.sub(r"['\u2019]s\b", "", s.lower())
        s = re.sub(r"[^a-z0-9 ]", " ", s)
        return {w for w in s.split() if w not in _TITLE_STOPWORDS}
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# A DOI or PMID that resolves verifies the work it resolves to, not the title cited with it. The
# cited title is compared with every title the record answers to: fewer than half of the cited
# title's words found in any of them is a different work. Measuring the cited side tolerates a
# cited title that leaves out the record's subtitle, without letting a short title of a related
# paper match a longer cited one because most of its few words are in it.
IDENTIFIER_TITLE_MIN = 0.5


def _us_spelling(w: str) -> str:
    """Fold British spellings onto American ones, so that a title differing only in spelling
    (paediatric/pediatric, tumour/tumor, randomised/randomized, centre/center) is not counted
    as a different title."""
    if len(w) > 4 and w.endswith("our"):
        w = w[:-3] + "or"
    if len(w) >= 5:  # an acronym (MAE, OE) is not a spelling
        w = w.replace("ae", "e").replace("oe", "e")
    w = re.sub(r"(?<=[a-z]{3})is(e|ed|ing|ation)$", r"iz\1", w)
    w = re.sub(r"(?<=[a-z]{2})yse$", "yze", w)
    w = re.sub(r"(?<=[a-z]{3}[aeiou])ll(ed|ing|er)$", r"l\1", w)  # modelled, labelling
    w = re.sub(r"(?<=[a-z]{2})(t|b)red$", r"\1ered", w)  # centred -> centered
    return re.sub(r"(?<=[a-z]{2})(t|b)re$", r"\1er", w)  # centre, metre, theatre, fibre


def _title_words(s: str) -> set | None:
    """Content words of a title, or None when it is not readable as Latin script.

    The tokenizer folds to ASCII, so a title mostly in another script (Chinese, Korean,
    Cyrillic) would shrink to its few Latin acronyms and be compared on those alone.
    """
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)          # publisher markup: <i>, <sub>, MathML
    s = re.sub(r"\\[a-zA-Z]+", " ", s)      # LaTeX commands in a BibTeX title
    letters = sum(ch.isalpha() for ch in s)
    s = re.sub(r"['\u2019]s\b", "", s.lower())
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    if not letters or sum(ch.isalpha() for ch in s) < letters / 2:
        return None
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    words = set()
    for w in s.split():
        if w in _TITLE_STOPWORDS:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "is", "us")):
            w = w[:-1]
        words.add(_us_spelling(w))
    return words or None


def _same_title(a: str, b: str) -> bool:
    """Near-identical titles (Jaccard >= TITLE_MATCH_MIN): the same title in two records."""
    wa, wb = _title_words(a), _title_words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= TITLE_MATCH_MIN


def cited_title_agrees(cited: str, resolved: list) -> bool | None:
    """Does the cited title name the record its DOI/PMID resolved to?

    True when some resolved title contains at least IDENTIFIER_TITLE_MIN of the cited title's
    words, False when none does, None when there is nothing to compare: no cited title, or no
    title on either side readable as Latin script.
    """
    cited_words = _title_words(cited)
    if not cited_words:
        return None
    verdict = None
    for title in resolved:
        words = _title_words(title)
        if not words:
            continue
        if len(cited_words & words) / len(cited_words) >= IDENTIFIER_TITLE_MIN:
            return True
        verdict = False
    return verdict


# A reference line also carries author and journal words, which can supply half of a short
# title by chance ("Cancer research priorities" in a line citing the journal Cancer Research),
# so a line must contain most of the resolved title, or of its part before a colon.
LINE_TITLE_MIN = 0.8


def _non_latin_letters(s: str) -> int:
    """Letters outside the Latin and Greek scripts (CJK, Hangul, Cyrillic, ...). Greek is common
    in scientific titles (beta-amyloid), and accented Latin letters (o-slash, sharp s) are Latin."""
    return sum(1 for ch in s if ch.isalpha()
               and not unicodedata.name(ch, "").startswith(("LATIN", "GREEK")))


def resolved_title_in_text(text: str, resolved: list) -> bool | None:
    """Is the resolved title written in a plain-text reference line?

    A line's guessed title is often its author list, so the line itself is searched: True when
    at least LINE_TITLE_MIN of the words of some resolved title (or of its main title before a
    colon) occur in it, False when none does, None when there is nothing to compare: a line
    holding a letter of another script (its title may be written in it), or no resolved title
    readable as Latin script. A record title of two or three words that happen to stand in the
    line's journal name or author list still matches; the check cannot tell them apart.
    """
    if _non_latin_letters(text):
        return None
    text_words = _title_words(text)
    if not text_words:
        return None
    verdict = None
    for title in resolved:
        for candidate in dict.fromkeys([title, title.split(":")[0]]):
            words = _title_words(candidate)
            if not words or (candidate != title and len(words) < 3):
                continue
            if len(words & text_words) / len(words) >= LINE_TITLE_MIN:
                return True
            verdict = False
    return verdict


# A search hit below TITLE_MATCH_MIN and at least this close is shown as a "nearest real paper".
NEAR_TITLE_MIN = 0.7


def clean_markup(text: str) -> str:
    """A registry title without publisher markup (<i>, <sub>, MathML) and entities."""
    return normalize_space(re.sub(r"<[^>]+>", " ", html.unescape(text or "")))


def _plain_words(text: str) -> list:
    text = unicodedata.normalize("NFKD", clean_markup(text)).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z0-9]+", text.lower())


def title_phrase_in_line(line: str, titles: list) -> bool:
    """Does a search hit's title stand in a plain-text reference line, word for word?

    A search hit has no identifier behind it, so sharing words is not enough: the three words
    of "Stochastic Optimization Methods" all occur in a line that cites "Adam: A method for
    stochastic optimization". The title, or its part before a colon, must appear as a phrase.
    """
    hay = " " + " ".join(_plain_words(line)) + " "
    for title in titles:
        for candidate in dict.fromkeys([title, title.split(":")[0]]):
            words = _plain_words(candidate)
            if len(words) >= 2 and " " + " ".join(words) + " " in hay:
                return True
    return False


def first_author_named(text: str, name: str, structured: bool) -> bool | None:
    """Is a record's first author named in the author part of a plain-text reference?

    Author lists are written in too many styles to parse ("He K", "K. He", "Kaiming He",
    "He, Kaiming"), so the record's name is looked for in the text instead of the other way
    round. `name` is a family name when `structured`, otherwise a full name, any word of which
    may be the family name. None when it cannot be told (a name in another script).
    """
    if not text or not name or _non_latin_letters(text) or _non_latin_letters(name):
        return None
    words = {w for w in re.split(r"[\s-]+", _normalize_surname(text)) if w}
    parts = [w for w in re.split(r"[\s-]+", _normalize_surname(name)) if w and w not in _NAME_PARTICLES]
    if not parts:
        return None
    if structured:
        return parts[0] in words or parts[-1] in words
    return any(part in words for part in parts if len(part) > 1)


def search_similarity(cited: str, titles: list) -> float:
    """How well the best of a search hit's titles matches the cited title (token Jaccard)."""
    return max((_title_similarity(cited, clean_markup(t)) for t in titles if t), default=0.0)


def _candidate(title: str, year, doi: str, authors: list, similarity, source: str, **extra) -> dict:
    out = {"title": clean_markup(title), "year": str(year or ""), "doi": doi,
           "authors": authors[:3], "source": source}
    if similarity is not None:
        out["similarity"] = round(similarity, 2)
    out.update({k: v for k, v in extra.items() if v not in (None, "")})
    return out


def lookup_crossref_title(record: RefRecord) -> Lookup:
    """Search Crossref for a reference that no identifier settled.

    A search returns something for any words, so a hit proves nothing on its own: it counts only
    when its title matches the cited one. A title from a title field is compared as a title; a
    plain-text reference line is sent whole (Crossref's bibliographic query is made for that)
    and must contain the hit's title as a phrase. The caller still compares the authors.
    """
    if record.title_from_field:
        query = f"{record.title_guess} {record.first_author_guess}".strip()
    else:
        query = re.sub(r"^(\[\d+\]|\d+[\.\)]|\-\s+)\s*", "", record.raw)[:400]
    if len(query.split()) < 3:
        return Lookup("crossref_title", UNCONFIRMED, "No identifier and no usable title")
    status, data = get_json("https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": query, "rows": "5"}))
    items = ((data or {}).get("message") or {}).get("items")
    if status != 200 or items is None:
        return Lookup("crossref_title", UNCONFIRMED, "Crossref title search failed")
    best, best_sim, near = None, 0.0, []
    for item in items:
        titles = crossref_titles(item)
        if record.title_from_field:
            sim = search_similarity(record.title_guess, titles)
        else:
            sim = 1.0 if title_phrase_in_line(record.raw, titles) else 0.0
        if sim > best_sim:
            best, best_sim = item, sim
        if sim >= NEAR_TITLE_MIN:
            year = ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            near.append(_candidate(titles[0] if titles else "", year, (item.get("DOI") or "").lower(),
                                   [a.get("family") or a.get("name") or "" for a in item.get("author") or []],
                                   sim if record.title_from_field else None, "crossref"))
    if best is not None and best_sim >= TITLE_MATCH_MIN:
        look = crossref_record(best, f"Crossref title match (similarity {best_sim:.2f})", "crossref_title")
        look.title_only = True
        return look
    look = Lookup("crossref_title", UNCONFIRMED,
                  f"No confident Crossref title match (best similarity {best_sim:.2f})")
    look.candidates = sorted(near, key=lambda c: -c.get("similarity", 0))[:3]
    return look


# ---------------------------------------------------------------------------------------------
# Researchzy results


def _arxiv_base(value: str) -> str:
    value = re.sub(r"^arxiv\s*:\s*", "", (value or "").strip(), flags=re.I)
    return re.sub(r"v\d+$", "", value, flags=re.I).lower()


def load_researchzy(path: Path) -> dict:
    """The papers Researchzy returned for each reference, as the agent saved them:
    {"results": {"<ref_id>": [paper, ...]}}. An empty list means searched and nothing found."""
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results", data) if isinstance(data, dict) else data
    if isinstance(results, list):
        results = {str(r.get("ref_id")): r.get("results") or r.get("papers") or [] for r in results
                   if isinstance(r, dict)}
    out: dict = {}
    for ref_id, papers in (results or {}).items():
        out[str(ref_id)] = [_researchzy_paper(p) for p in papers or [] if isinstance(p, dict)]
    return out


def _researchzy_paper(p: dict) -> dict:
    authors = [normalize_space(a.get("name", "") if isinstance(a, dict) else str(a))
               for a in p.get("authors") or []]
    authors = [a for a in authors if a]
    year = p.get("year") or str(p.get("publicationDate") or "")[:4]
    return {
        "corpusId": p.get("corpusId"), "title": normalize_space(str(p.get("title") or "")),
        "authors": authors, "authorCount": p.get("authorCount") or len(authors),
        "year": int(year) if str(year).isdigit() else None, "venue": p.get("venue") or "",
        "doi": normalize_doi_for_dup(str(p.get("doi") or "")), "arxiv": _arxiv_base(str(p.get("arxiv") or "")),
        "hasReadablePdf": bool(p.get("hasReadablePdf")), "readerUrl": p.get("readerUrl") or "",
    }


def lookup_researchzy(record: RefRecord, papers: list) -> tuple[str, Lookup]:
    """Match a reference to the papers Researchzy returned for it.

    Returns (identifier kind, lookup). A paper carrying the cited DOI or arXiv number confirms
    that the identifier is real; otherwise a paper counts only when its title matches, under the
    same guard as any title search.
    """
    if not papers:
        return "", Lookup("researchzy", UNCONFIRMED, "Researchzy search returned no papers")

    def as_lookup(paper: dict, evidence: str, title_only: bool) -> Lookup:
        look = Lookup("researchzy", CONFIRMED, structured=False, title_only=title_only)
        look.families = paper["authors"]
        look.titles = [paper["title"]] if paper["title"] else []
        look.years = [paper["year"]] if paper["year"] else []
        look.record = {"source": "researchzy", "corpusId": paper["corpusId"], "doi": paper["doi"],
                       "arxiv": paper["arxiv"], "url": paper["readerUrl"], "title": paper["title"],
                       "year": str(paper["year"] or ""), "container": paper["venue"],
                       "authors": [{"name": a} for a in paper["authors"]],
                       "authorCount": paper["authorCount"],
                       "hasReadablePdf": paper["hasReadablePdf"], "readerUrl": paper["readerUrl"]}
        look.evidence = f"{evidence}; corpusId={paper['corpusId']}; title={paper['title'][:120]}"
        return look

    doi, arxiv = normalize_doi_for_dup(record.doi), _arxiv_base(record.arxiv)
    for paper in papers:
        if doi and paper["doi"] == doi:
            return "DOI", as_lookup(paper, "Researchzy record with this DOI", False)
    for paper in papers:
        if arxiv and paper["arxiv"] == arxiv:
            return "arXiv", as_lookup(paper, "Researchzy record with this arXiv number", False)
    best, best_sim, near = None, 0.0, []
    for paper in papers:
        if record.title_from_field:
            sim = search_similarity(record.title_guess, [paper["title"]])
        else:
            sim = 1.0 if title_phrase_in_line(record.raw, [paper["title"]]) else 0.0
        if sim > best_sim:
            best, best_sim = paper, sim
        if sim >= NEAR_TITLE_MIN:
            near.append(_candidate(paper["title"], paper["year"], paper["doi"], paper["authors"],
                                   sim if record.title_from_field else None, "researchzy",
                                   corpusId=paper["corpusId"], readerUrl=paper["readerUrl"]))
    if best is not None and best_sim >= TITLE_MATCH_MIN:
        return "", as_lookup(best, f"Researchzy title match (similarity {best_sim:.2f})", True)
    look = Lookup("researchzy", UNCONFIRMED,
                  f"No confident Researchzy title match (best similarity {best_sim:.2f})")
    look.candidates = sorted(near, key=lambda c: -c.get("similarity", 0))[:3]
    return "", look


# ---------------------------------------------------------------------------------------------
# Verdict


def author_cross_check(
    cited_authors: list,
    actual_authors: list,
    cited_author_count: int,
    actual_author_count: int,
    *,
    corporate: bool = False,
    soft: bool = False,
    audit_truncated: bool = False,
    first_author_guess: str = "",
) -> tuple[list, list]:
    """Family-by-family and author-count comparison (no network, no RefRecord).

    Compares every cited author family with the record's list by position, reports any cited
    author beyond the record's list, and compares the totals (a shorter cited list is only a
    note when ``audit_truncated``: BibTeX's ``and others``). When no cited list was parsed
    (TSV, plain text) it degrades to a first-author check. Collective authors and ``soft``
    lists are exempt.

    Returns ``(mismatches, notes)``: ``mismatches`` are human-readable differences (empty =
    clean); ``notes`` are remarks that are not differences (the truncation note).
    """
    mismatches: list = []
    notes: list = []
    if not corporate and cited_authors and actual_authors and not soft:
        compare_n = min(len(cited_authors), len(actual_authors))
        for i in range(compare_n):
            cited = cited_authors[i]
            if not author_surnames_match(cited, actual_authors[i]):
                mismatches.append(
                    f"#{i+1} family: cited='{cited}' vs source='{actual_authors[i]}'"
                )
        # cited has more authors than source — always flag (cannot be intentional)
        for i in range(compare_n, len(cited_authors)):
            mismatches.append(
                f"#{i+1} extra cited='{cited_authors[i]}' (source has only {len(actual_authors)} authors)"
            )
        # source has more authors than cited — a count mismatch, unless the bib declares
        # the truncation with BibTeX's `and others` sentinel.
        if cited_author_count != actual_author_count:
            if audit_truncated and cited_author_count < actual_author_count:
                notes.append(
                    f"authors: {cited_author_count} of {actual_author_count} cited "
                    f"(the entry ends in `and others`)"
                )
            else:
                mismatches.append(
                    f"AUTHOR COUNT: cited={cited_author_count} vs source={actual_author_count}"
                )
    elif not corporate and first_author_guess and actual_authors:
        # No parsed cited author list (TSV / plain-text input): compare the first author only.
        if not any(author_surnames_match(first_author_guess, a) for a in actual_authors):
            mismatches.append(
                f"#1 family: cited='{first_author_guess}' vs source='{actual_authors[0]}'"
            )
    return mismatches, notes


def _name_tokens(name: str) -> list:
    """The words of a full name, with a "Family, Given" form reduced to its family part."""
    name = name.split(",", 1)[0] if "," in name else name
    return [t for t in re.split(r"\s+", name.strip()) if t]


def soft_first_author_agrees(first_cited: str, names: list) -> bool | None:
    """Is the cited first author among a record's authors, when the record has full-name strings
    and no family field? Any word of a name may be the family name ("Wei Zhang", "Zhang Wei"),
    and a name particle goes with the word after it. None when there is nothing to compare."""
    if not first_cited or not names:
        return None
    for name in names:
        tokens = _name_tokens(name)
        for i, token in enumerate(tokens):
            joined = " ".join(tokens[i:i + 2]) if token.lower() in _NAME_PARTICLES else token
            if len(_normalize_surname(token)) < 2 and joined == token:
                continue  # an initial
            if author_surnames_match(first_cited, joined) and _normalize_surname(joined):
                return True
    return False


def _author_names(record: dict) -> list:
    return [a.get("name") or " ".join(p for p in (a.get("given", ""), a.get("family", "")) if p)
            for a in record.get("authors") or []]


def _bibtex_authors(record: dict) -> str:
    """A BibTeX author field for a record whose authors have family and given names."""
    authors = record.get("authors") or []
    if not authors or not all(a.get("family") for a in authors):
        return ""
    parts = []
    for a in authors:
        if a.get("corporate"):
            parts.append("{" + a["family"] + "}")
        elif a.get("given"):
            parts.append(f"{a['family']}, {a['given']}")
        else:
            return ""
    return " and ".join(parts)


IDENTIFIER_ORDER = {"PMID": 0, "DOI": 1, "arXiv": 2}


def verify_record(record: RefRecord, offline: bool, researchzy: list | None = None) -> RefRecord:
    """Look one reference up and give it a verdict.

    Lookups: PubMed for a PMID, Crossref for a DOI (then doi.org and DataCite), arXiv for an
    arXiv number or arXiv DOI, the Researchzy papers the agent saved for this reference, and a
    Crossref title search when none of those found the cited work.

    A record reached through an identifier must carry the cited title: an identifier that
    resolves confirms the work it resolves to, so a real DOI attached to another paper is
    reported and that record is not used for anything else. A record reached by title alone
    counts only when its authors could be compared and agree and its year is within one of the
    cited year.

    The author list of the best record is compared with the cited one: position by position and
    by count when the record has family names (PubMed, Crossref, DataCite), by the first author
    only when it has plain name strings (arXiv, Researchzy). A reference without a parsed
    author list (plain text, TSV) is checked the other way round: the record's first author
    must be named in it.
    """
    lookups: list[tuple[str, Lookup]] = []
    if not offline:
        arxiv_id = record.arxiv
        if record.pmid:
            lookups.append(("PMID", lookup_pubmed(record.pmid)))
        if record.doi:
            arxiv_doi = ARXIV_DOI_RE.match(normalize_doi_for_dup(record.doi))
            if arxiv_doi:
                arxiv_id = arxiv_id or arxiv_doi.group(1)
            else:
                lookups.append(("DOI", lookup_crossref(record.doi)))
        if arxiv_id:
            lookups.append(("arXiv", lookup_arxiv(arxiv_id)))
    if researchzy is not None:
        lookups.append(lookup_researchzy(record, researchzy))

    # Which identifiers resolve to a work that does not carry the cited title?
    by_kind: dict = {}
    for kind, look in lookups:
        if kind and look.status == CONFIRMED and look.titles:
            by_kind.setdefault(kind, []).extend(clean_markup(t) for t in look.titles)
    agreement = {
        kind: (cited_title_agrees(record.title_guess, titles) if record.title_from_field
               else resolved_title_in_text(record.raw, titles))
        for kind, titles in by_kind.items()
    }
    # Two identifiers may hold one work under different titles (a translated title in one
    # registry): when another identifier's record agrees and carries this title too, both name
    # the same work.
    elsewhere = [
        kind for kind, agrees in agreement.items()
        if agrees is False and not any(
            agreement.get(other) is True and any(_same_title(x, y) for x in by_kind[kind] for y in by_kind[other])
            for other in by_kind if other != kind)
    ]
    if not offline and not any(look.status == CONFIRMED and kind not in elsewhere for kind, look in lookups):
        lookups.append(("", lookup_crossref_title(record)))

    if record.cited_authors and not record.cited_author_count:
        record.cited_author_count = len(record.cited_authors)
    cited_year = int(record.year_guess) if record.year_guess.isdigit() else None
    first_cited = record.cited_authors[0] if record.cited_authors else record.first_author_guess
    evidence = [look.evidence for _, look in lookups if look.evidence]
    candidates = [c for _, look in lookups for c in look.candidates]

    def is_collective(look: Lookup) -> bool:
        return record.corporate_author or any(_ORG_AUTHOR_RE.search(f) for f in look.families)

    def authors_differ(look: Lookup) -> tuple[list, list, bool]:
        """(differences, notes, whether anything was compared) for one record's author list."""
        if is_collective(look) or not look.families:
            return [], [], False
        if not record.cited_authors and record.author_text:
            named = first_author_named(record.author_text, look.families[0], look.structured)
            if named is False:
                return [f"#1 family: the record's first author '{look.families[0]}' is not named "
                        "in the reference"], [], True
            return [], [], named is True
        if look.structured:
            diffs, notes = author_cross_check(
                record.cited_authors, look.families, record.cited_author_count, len(look.families),
                audit_truncated=record.audit_truncated, first_author_guess=record.first_author_guess)
            return diffs, notes, bool(record.cited_authors or record.first_author_guess)
        agrees = soft_first_author_agrees(first_cited, look.families)
        if agrees is False:
            return [f"#1 family: cited='{first_cited}' is not among the record's authors "
                    f"({', '.join(look.families[:3])})"], [], True
        return [], [], agrees is True

    confirmed: list[tuple[str, Lookup]] = []
    for kind, look in lookups:
        if look.status != CONFIRMED or kind in elsewhere:
            continue
        if look.title_only:
            # A title match says a work with a similar title exists, not that it is the cited one.
            diffs, _notes, compared = authors_differ(look)
            year_far = bool(cited_year and look.years and min(abs(cited_year - y) for y in look.years) > 1)
            if diffs or year_far or not (compared or is_collective(look)):
                why = ("its authors differ from the cited ones" if diffs else
                       "its year is not the cited one" if year_far else
                       "its authors could not be compared")
                evidence.append(f"{look.source}: title match not accepted, {why}")
                candidates.insert(0, _candidate(
                    look.record.get("title", ""), look.record.get("year"), look.record.get("doi", ""),
                    _author_names(look.record), None, look.record.get("source", look.source),
                    corpusId=look.record.get("corpusId"), readerUrl=look.record.get("readerUrl"),
                    why_not=why))
                continue
        confirmed.append((kind, look))
    confirmed.sort(key=lambda kl: (IDENTIFIER_ORDER.get(kl[0], 3), kl[1].source == "researchzy"))
    not_registered = [look for _, look in lookups if look.status == NOT_REGISTERED]

    differences: list = []
    notes: list = []
    for kind in elsewhere:
        target = next(look for k, look in lookups if k == kind and look.status == CONFIRMED)
        differences.append({
            "field": "identifier_points_elsewhere", "severity": "major", "identifier": kind,
            "detail": f"the {kind} resolves to a work whose title shares under half its words "
                      "with the cited reference",
            "found": f"{by_kind[kind][0]} ({target.record.get('url') or target.source})",
            "summary": f"the {kind} belongs to a different work"})
    for look in not_registered:
        kind = {"doi.org": "DOI", "pubmed": "PMID", "arxiv": "arXiv number"}.get(look.source, "identifier")
        differences.append({
            "field": "identifier_not_registered", "severity": "major", "identifier": kind,
            "detail": look.evidence, "summary": f"the cited {kind} does not exist"})

    best = next((look for _, look in confirmed if look.families), confirmed[0][1] if confirmed else None)
    if best is not None:
        record.found = dict(best.record)
        record.actual_authors = list(best.families)
        record.actual_author_count = best.record.get("authorCount") or len(best.families)
        diffs, author_notes, _compared = authors_differ(best)
        notes.extend(author_notes)
        if diffs:
            first_bad = diffs[0].startswith("#1 family")
            differences.append({
                "field": "author", "severity": "major", "source": best.source,
                "detail": " | ".join(diffs),
                "cited": ", ".join(record.cited_authors) or first_cited or record.author_text[:80],
                "found": ", ".join(_author_names(best.record)),
                "summary": ("the first author differs from the record" if first_bad else
                            "an author after the first, or the number of authors, differs from the record"),
            })
        if is_collective(best):
            notes.append("collective author: personal names not compared")
        registry_years = sorted({y for kind, look in confirmed if kind in ("PMID", "DOI") for y in look.years})
        if cited_year and registry_years:
            gap = min(abs(cited_year - y) for y in registry_years)
            shown = next((look.record.get("year") for kind, look in confirmed
                          if kind in ("PMID", "DOI") and look.record.get("year")), str(registry_years[0]))
            if gap >= 2:
                differences.append({"field": "year", "severity": "minor", "cited": str(cited_year),
                                    "found": shown, "detail": f"cited {cited_year}, the record says {shown}",
                                    "summary": "the year differs from the record"})
            elif gap == 1:
                notes.append(f"year: cited {cited_year}, the record says {shown} "
                             "(online and print years can differ)")
        if differences and differences[0]["field"].startswith("identifier_"):
            notes.insert(0, "the work itself was found" + (f": doi:{record.found['doi']}" if record.found.get("doi") else ""))
        elif not record.doi and record.found.get("doi") and not differences:
            notes.append(f"DOI of the record: {record.found['doi']}")

    if confirmed:
        record.status = MISMATCH if differences else CONFIRMED
    elif elsewhere:
        record.status = MISMATCH
        notes.insert(0, "the cited work itself was not found")
    elif not_registered:
        record.status = NOT_REGISTERED
    else:
        record.status = UNCONFIRMED

    record.differences = differences
    record.candidates = candidates[:5]
    by_flag: dict = {}
    for _, look in confirmed:  # a notice on another work is not a notice on this one
        for flag in look.flags:
            details = by_flag.setdefault(flag["flag"], [])
            if flag["detail"] not in details:
                details.append(flag["detail"])
    record.flags = [{"flag": name, "detail": "; ".join(details)} for name, details in by_flag.items()]
    for _, look in confirmed:
        if look.source == "researchzy":
            record.researchzy = {k: look.record.get(k) for k in ("corpusId", "readerUrl", "hasReadablePdf", "doi")}
    if record.corporate_author and not any("collective author" in n for n in notes):
        notes.append("collective author: personal names not compared")
    if offline and not lookups:
        evidence.append("offline: identifiers extracted, nothing looked up")
    record.note = "; ".join([d["summary"] for d in differences] + notes)
    record.evidence = " | ".join(evidence)
    return record


def detect_duplicates(records: list[RefRecord]) -> list[dict]:
    """Detect verbatim PMID or DOI duplicates within the reference list.

    Verbatim duplicates (same PMID or normalized DOI) are a common LLM
    citation-compilation artifact and require cite renumbering before
    submission.
    """
    seen_pmids: dict[str, str] = {}
    seen_dois: dict[str, str] = {}
    findings: list[dict] = []
    for rec in records:
        rec_id = rec.ref_id or "<unknown>"
        pmid = (rec.pmid or "").strip()
        if pmid:
            if pmid in seen_pmids:
                findings.append({
                    "severity": "MAJOR",
                    "category": "duplicate_pmid",
                    "ref_ids": [seen_pmids[pmid], rec_id],
                    "pmid": pmid,
                    "note": "Same identifier. Keep one entry and point every citation to it.",
                })
            else:
                seen_pmids[pmid] = rec_id
        doi = normalize_doi_for_dup(rec.doi or "")
        if doi:
            if doi in seen_dois:
                findings.append({
                    "severity": "MAJOR",
                    "category": "duplicate_doi",
                    "ref_ids": [seen_dois[doi], rec_id],
                    "doi": doi,
                    "note": "Same identifier. Keep one entry and point every citation to it.",
                })
            else:
                seen_dois[doi] = rec_id
    return findings


def detect_title_duplicates(records: list[RefRecord]) -> list[dict]:
    """Two entries with the same title and first author under different keys: usually one work
    entered twice, once with a DOI and once without."""
    seen: dict = {}
    findings: list[dict] = []
    for rec in records:
        if not (rec.title_from_field and rec.title_guess):
            continue
        words = _title_words(rec.title_guess)
        if not words or len(words) < 3:
            continue
        key = (frozenset(words), _normalize_surname(rec.first_author_guess))
        if key in seen:
            findings.append({"severity": "MINOR", "category": "duplicate_title",
                             "ref_ids": [seen[key], rec.ref_id],
                             "note": "Same title and first author. Keep one entry."})
        else:
            seen[key] = rec.ref_id
    return findings


PLACEHOLDER_RE = re.compile(r"e0{3}.{0,3}e0{3}|\bin[ .]?press\b|\bTBD\b|\bforthcoming\b|\bto appear\b", re.I)


def flag_placeholder(record: RefRecord) -> None:
    """A reference still carrying "in press", "forthcoming" or e000-e000 pages is not yet a
    complete citation, whatever its verdict."""
    text = record.raw
    if record.entry:  # not in a title that happens to contain the words
        text = " ".join(bib_field(record.entry, name) for name in
                        ("pages", "note", "year", "date", "volume", "number", "journal", "howpublished", "pubstate"))
    if PLACEHOLDER_RE.search(text or ""):
        record.flags.append({"flag": "placeholder",
                             "detail": "publication status or pages still a placeholder"})


# ---------------------------------------------------------------------------------------------
# Citations in the manuscript


LATEX_CITE_RE = re.compile(r"\\([a-zA-Z]*cite[a-zA-Z]*)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]+)\}")
PANDOC_CITE_RE = re.compile(r"(?<![\w.@\\])@\{?([A-Za-z0-9_][\w:.#$%&+?<>~/-]*)")
NUMERIC_CITE_RE = re.compile(r"\[(\d+(?:\s*[-–,;]\s*\d+)*)\]")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]*(?:[A-Z0-9]|\\[a-zA-Z]))")

# What makes a citing sentence worth checking against the source: a number, a comparison, a
# claim of priority, or quoted words.
CHECKWORTHY = (
    ("number", re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent|fold|times)|\b[nNpP]\s*[=<>]\s*\d|\b\d+\.\d+\b")),
    ("comparison", re.compile(r"\b(?:outperform\w*|better than|worse than|higher than|lower than|more than|"
                              r"less than|compared (?:with|to)|significant(?:ly)?|increas\w+|decreas\w+|"
                              r"reduc\w+|improv\w+|superior|inferior)\b", re.I)),
    ("priority", re.compile(r"\b(?:first|only|novel|state[- ]of[- ]the[- ]art|best|largest|never)\b", re.I)),
    ("quotation", re.compile(r"[\"“][^\"”]{25,}[\"”]")),
)


ABBREVIATION_END_RE = re.compile(
    r"(?:\bet al|\be\.g|\bi\.e|\bFigs?|\bEqs?|\bRefs?|\bSecs?|\bTabs?|\bvs|\bcf|\bNo|\bDr|\bProf|\bapprox|\bca)\.$")
MARKDOWN_SUFFIXES = (".md", ".qmd", ".rmd", ".markdown")
# pandoc-crossref labels (@fig:setup, @eq:loss) look like citations and are not.
PANDOC_CROSSREF_RE = re.compile(r"^(?:fig|tbl|eq|sec|lst|thm|def):", re.I)


def _sentence_at(paragraph: str, offset: int) -> str:
    """The sentence of `paragraph` that contains position `offset`."""
    start = 0
    for m in SENTENCE_END_RE.finditer(paragraph):
        if ABBREVIATION_END_RE.search(paragraph[max(0, m.start() - 12):m.start()]):
            continue  # "et al. (2020)", "Fig. 3": not the end of a sentence
        if m.end() <= offset:
            start = m.end()
        else:
            return paragraph[start:m.start()].strip()
    return paragraph[start:].strip()


def _expand_numbers(spec: str) -> list:
    numbers: list = []
    for part in re.split(r"[,;]", spec):
        bounds = [int(n) for n in re.findall(r"\d+", part)]
        if len(bounds) == 2 and 0 < bounds[1] - bounds[0] <= 50:
            numbers.extend(range(bounds[0], bounds[1] + 1))
        else:
            numbers.extend(bounds)
    return numbers


def _blocks(text: str, each_line: bool) -> list:
    """(number of the first line, lines) of every paragraph: a run of non-blank lines, or each
    non-blank line when the source has one paragraph per line (DOCX)."""
    blocks: list = []
    current: list = []
    start = 0
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip() and not each_line:
            if not current:
                start = number
            current.append(line)
            continue
        if current:
            blocks.append((start, current))
            current = []
        if line.strip():
            blocks.append((number, [line]))
    if current:
        blocks.append((start, current))
    return blocks


def find_citations(path: Path, text: str, ref_ids: set) -> tuple[list, set]:
    """Every place the manuscript cites a reference: (citations, cited keys).

    Understands LaTeX cite commands, Pandoc `@key` citations and numeric `[12]` citations of a
    numbered list. Author-year citations in running text are not located; the agent finds those
    by reading. Each citation carries its sentence and whether that sentence is worth checking
    against the source.
    """
    suffix = path.suffix.lower()
    # The reference list is not running text.
    if suffix == ".tex":
        begin = re.search(r"\\begin\{document\}", text)
        if begin:  # keep the line numbers: blank the preamble instead of cutting it
            text = re.sub(r"[^\n]", "", text[:begin.end()]) + text[begin.end():]
        end = re.search(r"\\begin\{thebibliography\}|\\bibliography\{|\\printbibliography|\\end\{document\}", text)
    else:
        end = REFERENCE_HEADING_RE.search(text)
    if end:
        text = text[:end.start()]
    numeric = bool(ref_ids) and all(re.fullmatch(r"ref_\d+", r) for r in ref_ids)
    citations: list = []
    cited: set = set()
    for start, block in _blocks(text, each_line=suffix == ".docx"):
        if suffix == ".tex":
            block = [re.sub(r"(?<!\\)%.*", "", line) for line in block]
        paragraph = "\n".join(block)
        hits: list = []  # (offset, key, counted as cited without a sentence)
        if suffix == ".tex":
            for m in LATEX_CITE_RE.finditer(paragraph):
                keys = [k.strip() for k in m.group(2).split(",") if k.strip()]
                hits += [(m.start(), k, m.group(1).lower() == "nocite") for k in keys]
        elif suffix in MARKDOWN_SUFFIXES:
            for m in PANDOC_CITE_RE.finditer(paragraph):
                key = m.group(1).rstrip(".,;:)]}")
                if key and not PANDOC_CROSSREF_RE.match(key):
                    hits.append((m.start(), key, False))
        if numeric and not hits:
            for m in NUMERIC_CITE_RE.finditer(paragraph):
                hits += [(m.start(), f"ref_{n}", False) for n in _expand_numbers(m.group(1))]
        for offset, key, silent in hits:
            if key == "*":  # \nocite{*}
                cited.update(ref_ids)
                continue
            cited.add(key)
            if silent:
                continue
            sentence = normalize_space(_sentence_at(paragraph, offset))
            reasons = [name for name, pattern in CHECKWORTHY if pattern.search(sentence)]
            citations.append({
                "ref_id": key, "file": path.name,
                "line": start + paragraph.count("\n", 0, offset),
                "sentence": sentence[:700], "check": bool(reasons), "why": reasons,
            })
    return citations, cited


# ---------------------------------------------------------------------------------------------
# Output


def set_bib_field(entry: str, name: str, value: str) -> str:
    """The entry with one field replaced, or added when it is absent."""
    m = re.search(rf"(?<![\w-]){name}\s*=\s*", entry, re.I)
    if not m:
        end = entry.rstrip().rfind("}") if entry.rstrip().endswith("}") else entry.rstrip().rfind(")")
        if end < 0:
            return entry
        head = entry[:end].rstrip()
        return head + ("" if head.endswith(",") else ",") + f"\n  {name} = {{{value}}}\n" + entry[end:]
    i = m.end()
    if i < len(entry) and entry[i] == "{":
        depth, j = 1, i + 1
        while j < len(entry) and depth > 0:
            depth += {"{": 1, "}": -1}.get(entry[j], 0)
            j += 1
    elif i < len(entry) and entry[i] == '"':
        j = entry.find('"', i + 1)
        j = len(entry) if j < 0 else j + 1
    else:
        j = i
        while j < len(entry) and entry[j] not in ",\n}":
            j += 1
    return entry[:i] + "{" + value + "}" + entry[j:]


def bib_fixes(record: RefRecord) -> list:
    """The field corrections a registry record supports for a BibTeX entry: (field, value, why).

    The record is the cited work itself (its title and authors were matched), never the other
    work a wrong identifier points at.
    """
    if not record.entry or not record.found or record.status != MISMATCH:
        return []
    fixes = []
    source = f"{SOURCE_NAMES.get(record.found.get('source'), record.found.get('source'))} {record.found.get('url') or ''}".strip()
    for d in record.differences:
        if d["field"] == "author":
            authors = _bibtex_authors(record.found)
            if authors:
                fixes.append(("author", authors, f"authors from {source}"))
        elif d["field"] == "year" and re.match(r"(?:19|20)\d{2}", d.get("found", "")):
            fixes.append(("year", d["found"][:4], f"year from {source}"))
        elif d["field"].startswith("identifier_") and d["identifier"] == "DOI" and record.found.get("doi") \
                and not any(name == "doi" for name, _, _ in fixes):
            fixes.append(("doi", record.found["doi"], f"DOI of the work found at {source}"))
    return fixes


def exported(record: RefRecord) -> dict:
    data = asdict(record)
    data.pop("entry", None)
    data.pop("author_text", None)
    return data


SOURCE_NAMES = {"crossref": "Crossref", "crossref_title": "Crossref title search", "datacite": "DataCite",
                "arxiv": "arXiv", "pubmed": "PubMed", "researchzy": "Researchzy", "doi.org": "doi.org"}


def _short(record: RefRecord, width: int = 110) -> str:
    text = record.title_guess if record.title_from_field else record.raw
    text = re.sub(r"\s+", " ", text).replace("|", "/")
    return text if len(text) <= width else text[: width - 1] + "…"


def write_report(path: Path, audit: dict, records: list[RefRecord]) -> None:
    lines = ["# Reference check", ""]
    lines.append(f"Input: `{audit['source']}` · {audit['total_references']} references · "
                 f"checked {audit['checked_on']}")
    lines.append("")
    lines += ["| Verdict | References |", "|---|---|"]
    for verdict in VERDICTS:
        lines.append(f"| {verdict.replace('_', ' ')} | {audit['counts'].get(verdict, 0)} |")
    lines.append("")
    if audit["flag_counts"]:
        lines.append("Flags: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in audit["flag_counts"].items()))
        lines.append("")
    for item in audit["not_done"]:
        lines.append(f"- Not done in this run: {item}")
    if audit["not_done"]:
        lines.append("")

    def block(record: RefRecord) -> list:
        out = [f"### `{record.ref_id}` — {record.status.replace('_', ' ')}", "", f"- Cited: {_short(record, 300)}"]
        for d in record.differences:
            extra = f" Cited: {d['cited']}. Record: {d['found']}." if d.get("cited") and d.get("found") else \
                (f" It resolves to: {d['found']}." if d.get("found") else "")
            out.append(f"- {d['severity'].capitalize()}: {d['summary']}.{extra}")
        summaries = {d["summary"] for d in record.differences}
        for note in [n for n in record.note.split("; ") if n and n not in summaries]:
            out.append(f"- Note: {note}")
        for flag in record.flags:
            out.append(f"- Flag: {flag['flag'].replace('_', ' ')} — {flag['detail']}")
        if record.found.get("url"):
            out.append(f"- Record: {SOURCE_NAMES.get(record.found.get('source'), record.found.get('source'))} "
                       f"<{record.found['url']}>")
        for c in record.candidates:
            sim = f", similarity {c['similarity']}" if "similarity" in c else ""
            where = f" doi:{c['doi']}" if c.get("doi") else ""
            out.append(f"- Nearest real paper ({SOURCE_NAMES.get(c['source'], c['source'])}{sim}): {c['title']} "
                       f"({', '.join(c['authors'])}{', ' if c['authors'] else ''}{c['year']}){where}")
        out.append(f"- Evidence: {record.evidence or 'none'}")
        return out + [""]

    attention = [r for r in records if r.status in (NOT_REGISTERED, MISMATCH)
                 or any(f["flag"] in ("retracted", "partly_retracted", "update_notice", "expression_of_concern")
                        for f in r.flags)]
    if attention:
        lines += ["## Needs attention", ""]
        for record in sorted(attention, key=lambda r: VERDICTS.index(r.status)):
            lines += block(record)
    unconfirmed = [r for r in records if r.status == UNCONFIRMED and r not in attention]
    if unconfirmed:
        lines += ["## Unconfirmed", "",
                  "Nothing confirmed or refuted these. That is not evidence that they are invented: "
                  "books, reports, theses and web pages are often in no registry.", ""]
        for record in unconfirmed:
            lines += block(record)
    confirmed = [r for r in records if r.status == CONFIRMED and r not in attention]
    if confirmed:
        lines += ["## Confirmed", "", "| Reference | Cited | Record | Flags and notes |", "|---|---|---|---|"]
        for record in confirmed:
            notes = "; ".join([f["flag"].replace("_", " ") for f in record.flags]
                              + ([record.note] if record.note else []))
            name = SOURCE_NAMES.get(record.found.get("source"), record.found.get("source", ""))
            link = f"[{name}]({record.found['url']})" if record.found.get("url") else name
            lines.append(f"| `{record.ref_id}` | {_short(record, 90)} | {link} | {notes.replace('|', '/')} |")
        lines.append("")
    if audit["duplicate_findings"]:
        lines += ["## Duplicates", ""]
        for dup in audit["duplicate_findings"]:
            lines.append(f"- `{'`, `'.join(dup['ref_ids'])}`: {dup['category'].replace('_', ' ')}. {dup['note']}")
        lines.append("")
    keys = audit.get("citation_keys")
    if keys and (keys["missing"] or keys["uncited"]):
        lines += ["## Citation keys", ""]
        if keys["missing"]:
            lines.append("- Cited in the text but not in the reference list: `" + "`, `".join(keys["missing"]) + "`")
        if keys["uncited"]:
            lines.append("- In the reference list but never cited: `" + "`, `".join(keys["uncited"]) + "`")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def researchzy_lookups(records: list[RefRecord], have: dict | None) -> dict:
    """The Researchzy searches worth making: `needed` would settle a reference the registries
    left open; `for_full_text` finds the record (and its PDF) of a settled one, for the claim
    check. References already looked up are left out."""
    def calls(record: RefRecord) -> list:
        out = []
        if record.doi and WELL_FORMED_DOI_RE.match(record.doi) and not ARXIV_DOI_RE.match(record.doi):
            out.append({"tool": "search_papers", "arguments": {"doi": record.doi}})
        arxiv = record.arxiv or (ARXIV_DOI_RE.match(record.doi).group(1) if ARXIV_DOI_RE.match(record.doi or "") else "")
        if arxiv:
            out.append({"tool": "search_papers", "arguments": {"arxiv": arxiv}})
        title = record.title_guess if record.title_from_field else (record.found.get("title") or "")
        if title:
            title = title.replace('"', "")
            out.append({"tool": "search_papers", "arguments": {"query": f'"{title}"'}})
            out.append({"tool": "search_papers", "arguments": {"query": title}})
        return out

    needed, full_text = [], []
    for record in records:
        if have is not None and record.ref_id in have:
            continue
        item = {"ref_id": record.ref_id, "reference": _short(record, 400), "calls": calls(record)}
        if record.status in (UNCONFIRMED, NOT_REGISTERED) or not record.found:
            if record.status != UNCONFIRMED:  # the identifier is known not to lead to this work
                item["calls"] = [c for c in item["calls"] if "query" in c["arguments"]]
            if not item["calls"]:
                item["instruction"] = ("No title field: search with the title as written in `reference`, "
                                       "first in double quotes, then without.")
            needed.append(item)
        elif item["calls"]:
            item["calls"] = item["calls"][:1]
            full_text.append(item)
    return {
        "how": ("Run each call with the Researchzy search_papers tool. Stop at the first call of a "
                "reference that returns papers. Save what came back under the reference's ref_id in "
                "researchzy-results.json as {\"results\": {\"<ref_id>\": [papers]}}, copying corpusId, "
                "title, authors, authorCount, year, venue, doi, arxiv, hasReadablePdf and readerUrl "
                "exactly as returned; write an empty list when nothing came back. Then run the "
                "script again with --researchzy researchzy-results.json."),
        "needed": needed,
        "for_full_text": full_text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a manuscript's or bibliography's references.")
    parser.add_argument("input", help="A .bib, .tex, .md, .docx, .pdf, .txt or .tsv file")
    parser.add_argument("--out", default="reference-check", help="Output folder (default: reference-check)")
    parser.add_argument("--manuscript", action="append", default=[],
                        help="A manuscript file whose citations to locate (repeatable); "
                             "a .tex, .md, .docx or .pdf input is read for citations by itself")
    parser.add_argument("--researchzy", help="Researchzy search results saved by the agent (JSON)")
    parser.add_argument("--offline", action="store_true", help="Call no registry; parse, merge and report only")
    parser.add_argument("--contact", default=os.environ.get("RESEARCHZY_CONTACT_EMAIL", ""),
                        help="Your e-mail for the registries' courtesy header (optional)")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    parser.add_argument("--refresh", action="store_true", help="Ignore the cache of earlier answers")
    parser.add_argument("--strict", action="store_true", help="Exit 1 unless every reference is confirmed")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 2
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    text = read_input(input_path)
    suffix = input_path.suffix.lower()
    manuscripts = [Path(p).resolve() for p in args.manuscript]
    hashed = [input_path]
    if suffix == ".bib":
        records = parse_bib(text)
    elif suffix == ".tsv":
        records = parse_tsv(text)
    elif suffix == ".tex":
        records = parse_bibitems(text)
        if not records:
            for bib in tex_bib_files(text, input_path.parent):
                records += parse_bib(bib.read_text(encoding="utf-8", errors="replace"))
                hashed.append(bib)
        manuscripts.insert(0, input_path)
    else:
        records = parse_reference_lines(text)
        if suffix in MARKDOWN_SUFFIXES + (".docx", ".pdf"):
            manuscripts.insert(0, input_path)
    if not records:
        print("No references detected.", file=sys.stderr)
        return 3

    CLIENT.timeout, CLIENT.contact = args.timeout, args.contact.strip()
    cache_path = out_dir / "cache.json"
    if not args.refresh:
        CLIENT.load_cache(cache_path)
    researchzy = load_researchzy(Path(args.researchzy)) if args.researchzy else None

    for i, record in enumerate(records, 1):
        try:
            verify_record(record, args.offline, None if researchzy is None else researchzy.get(record.ref_id))
        except Exception as error:  # one unexpected registry answer must not lose the whole run
            record.status = UNCONFIRMED
            record.evidence = f"the check of this reference failed ({type(error).__name__}: {error})"
        flag_placeholder(record)
        if i % 10 == 0 or i == len(records):
            print(f"{i}/{len(records)} references", file=sys.stderr)
            if not args.offline:
                CLIENT.save_cache(cache_path)

    duplicates, pairs = [], set()
    for dup in detect_duplicates(records) + detect_title_duplicates(records):
        if tuple(dup["ref_ids"]) not in pairs:
            pairs.add(tuple(dup["ref_ids"]))
            duplicates.append(dup)
    for dup in duplicates:
        for record in records:
            if record.ref_id == dup["ref_ids"][-1] and not any(f["flag"] == "duplicate" for f in record.flags):
                record.flags.append({"flag": "duplicate", "detail": f"same work as `{dup['ref_ids'][0]}`"})

    ref_ids = {r.ref_id for r in records}
    citations, cited = [], set()
    for path in dict.fromkeys(manuscripts):
        if not path.exists():
            print(f"Manuscript not found: {path}", file=sys.stderr)
            continue
        found, keys = find_citations(path, text if path == input_path else read_input(path), ref_ids)
        citations += found
        cited |= keys
    citation_keys = None
    if manuscripts:
        citation_keys = {"missing": sorted(cited - ref_ids), "uncited": sorted(ref_ids - cited) if cited else []}

    counts: dict = {}
    flag_counts: dict = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
        for flag in record.flags:
            flag_counts[flag["flag"]] = flag_counts.get(flag["flag"], 0) + 1
    lookups = researchzy_lookups(records, researchzy)
    not_done = []
    if args.offline:
        not_done.append("registry lookups (offline run)")
    if lookups["needed"]:
        not_done.append(f"Researchzy lookup of {len(lookups['needed'])} references the registries did "
                        "not settle (see lookups.json)")
    audit = {
        "tool": "researchzy-reference-check",
        "schema_version": 1,
        "source": input_path.name,
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashed},
        "checked_on": datetime.date.today().isoformat(),
        "total_references": len(records),
        "counts": counts,
        "flag_counts": flag_counts,
        "all_confirmed": counts.get(CONFIRMED, 0) == len(records),
        "not_done": not_done,
        "duplicate_findings": duplicates,
        "citation_keys": citation_keys,
        "citations": citations,
        "records": [exported(r) for r in records],
    }
    (out_dir / "references.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "lookups.json").write_text(json.dumps(lookups, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(out_dir / "report.md", audit, records)

    fixed = []
    for record in records:
        fixes = bib_fixes(record)
        if fixes:
            entry = record.entry
            for name, value, _why in fixes:
                entry = set_bib_field(entry, name, value)
            fixed.append("% " + record.ref_id + ": " + "; ".join(why for _, _, why in fixes) + "\n" + entry)
    fixes_path = out_dir / "fixes.bib"
    if fixed:
        fixes_path.write_text("% Entries with only the disagreeing fields corrected. Review before use.\n\n"
                              + "\n\n".join(fixed) + "\n", encoding="utf-8")
    elif fixes_path.exists():
        fixes_path.unlink()

    print(json.dumps({
        "total": len(records), "counts": counts, "flags": flag_counts,
        "duplicates": len(duplicates), "citations_found": len(citations),
        "citations_worth_checking": sum(1 for c in citations if c["check"]),
        "researchzy_lookups_needed": len(lookups["needed"]),
        "fixes": len(fixed), "registry_calls": CLIENT.calls,
        "report": str(out_dir / "report.md"),
    }, indent=2))
    if args.strict and counts.get(CONFIRMED, 0) != len(records):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
