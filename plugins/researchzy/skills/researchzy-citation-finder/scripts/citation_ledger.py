#!/usr/bin/env python3
"""The ledger of a citation search: which sentences need a source, what was searched, what was read.

The agent searches and reads; this script finds the sentences, keeps the record in
citations/ledger.json, and accepts a citation only when the record holds a quote that is in the
text it names.

  citation_ledger.py targets paper.md [--bib refs.bib] [--line 41]   placeholders, other markers, candidates
  citation_ledger.py confirm c3 c7                       candidate sentences become targets
  citation_ledger.py need t1 finding                     finding | method | number | background
  citation_ledger.py need t2 not_needed --reason "the authors' own result (Table 2)"
  citation_ledger.py search t1 --query '"sleep deprivation" recall' --total 412 --looked-at 20 \\
                     --sort citationCount --filter yearFrom=2010 --saved citations/results/t1-1.json
  citation_ledger.py search t1 --query "…" --failed "RATE_LIMITED: try again later"
  citation_ledger.py candidate t1 citations/results/t1-1.json --doi 10.1000/xyz    or --arxiv, --corpus-id
  citation_ledger.py text paper.pdf [--name okoro2019]   the PDF's text, written to citations/texts/
  citation_ledger.py verdict t1 supported --paper okoro2019sleep --grade full-text \\
                     --quote "…" --source citations/texts/okoro2019.txt [--locator "Results"]
  citation_ledger.py verdict t3 partial …  --wording "the narrower sentence the paper does support"
  citation_ledger.py verdict t4 not_found [--reason "…"] three logged keyword searches, or the reason
  citation_ledger.py bib [--bib refs.bib]                new-references.bib for the accepted papers
  citation_ledger.py check                               every rule; writes citation-map.md
  citation_ledger.py apply paper.md                      a copy with the supported placeholders replaced

All commands take --dir (default: citations) before the command name; paths are read as given, so
run every command from the same folder. Standard library only; `text` uses PyMuPDF when it is
installed, else the pdftotext binary, else it says that neither is there. No network.
Exit code 1: `check` found a broken rule (the JSON lists them), or a command was refused or given
bad input (one line on standard error). A malformed command line exits 2.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

NEEDS = ("finding", "method", "number", "background", "not_needed")
VERDICTS = ("supported", "partial", "contradicts", "not_found", "not_needed", "not_checked")
QUOTED = VERDICTS[:3]      # these rest on a quote from a paper that was read
ACCEPTED = VERDICTS[:2]    # the paper of these is cited and gets a BibTeX entry
GRADES = ("metadata", "abstract", "full-text")
MIN_SEARCHES = 3           # distinct completed keyword searches of the index behind a not_found
MIN_QUOTE_WORDS = 5        # a shorter quote can be found in most papers
MIN_FULL_TEXT_WORDS = 400  # below this a text is an abstract or a scan without a text layer
ITEM_FIELDS = ("line", "section", "sentence", "claim", "note", "why")
VERDICT_FIELDS = ("verdict", "paper", "grade", "quote", "source", "locator", "wording", "reason")

CITE = r"\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\])*"
PLACEHOLDER_RE = re.compile(r"\[\s*citation needed\s*:\s*([^\]]*)\]", re.I)
MARKER_RE = re.compile(r"\[\s*(?:citation|cite|ref|reference)s?(?:\s+needed)?\s*\]|\[\?+\]|\[@NEW:[^\]]*\]|"
                       + CITE + r"\{\s*\?+\s*\}", re.I)
CITATION_RE = re.compile(CITE + r"\{[^}]*\}"                                                  # \citep{key}
                         r"|\[[^\[\]]*@[A-Za-z][^\[\]]*\]|(?<![\w.@\\])@[A-Za-z][\w:.-]*"      # [@key], @key
                         r"|\[\d+(?:\s*[-–,;]\s*\d+)*\]"                                       # [12], [3-5]
                         r"|[A-Z][\w'’-]+(?:\s+et\s+al\.?|\s+(?:and|&)\s+[A-Z][\w'’-]+)?,?\s+"
                         r"\((?:1[5-9]|20)\d{2}[a-z]?[,;)]")                                   # Okoro et al. (2019)
PAREN_RE = re.compile(r"\(([^()]{4,300})\)")
AUTHOR_YEAR_RE = re.compile(                                                                 # (Okoro et al., 2019)
    r"(?<![\w-])(?!(?:In|Since|During|From|Until|By|After|Before|Between|Around|Circa|January|February|March|April|"
    r"May|June|July|August|September|October|November|December)\b)[A-Z][\w'’.-]+"
    r"(?:\s+(?:et\s+al\.?|and|&|[A-Z][\w'’.-]+))*,?\s+(?:1[5-9]|20)\d{2}[a-z]?\b")
STATISTIC_RE = re.compile(
    r"(?i:(?<![\d.])\d+(?:\.\d+)?\s?(?:\\?%|percent\b|per cent\b)|\bp\s*(?:[<>=≤≥]|\\[lg]eq?\b)\s*0?\.\d+|\bn\s*=\s*\d+"
    r"|\b(?:\d+(?:\.\d+)?|two|three|four|five|ten)[\s-]*fold\b|\b(?:odds|hazard|risk|rate|likelihood)\s+ratios?\b"
    r"|\bratio\s+of\s+\d[\d.:]*)|\b(?:a?OR|a?HR|RR)\s*(?:[=:]|of)?\s*\d[\d.]*")
PHRASE_RE = re.compile(
    r"\b(?:(?:studies|research|trials|experiments|reports|authors|researchers) (?:have|has) "
    r"(?:shown|found|demonstrated|reported|suggested|established|indicated)"
    r"|it (?:is|has been) (?:well[- ]known|well[- ]established|widely \w+|commonly \w+|generally \w+)"
    r"|(?:previous|prior|earlier|recent|several|many|numerous|existing) (?:works?|studies|research|reports|literature)"
    r"|(?:has|have) been (?:reported|shown|demonstrated|documented|described|established|linked|associated|"
    r"suggested|proposed)|(?:is|are) known to|evidence (?:suggests|indicates|shows)|according to|the literature)\b", re.I)
# Wording that makes a sentence a strong claim. With its numbers, this decides when the full text is required.
COMPARISON_RE = re.compile(r"\b(?:than|versus|vs|compared (?:with|to)|relative to|outperform\w*|exceed\w*|superior|"
                           r"inferior|higher|lower|greater|smaller|larger|better|worse|faster|slower|fewer|stronger|"
                           r"weaker|twice|doubl\w+|halv\w+|\w+fold)\b", re.I)
CAUSAL_RE = re.compile(r"\b(?:caus(?:e|es|ed|ing)|(?:leads?|led|leading) to|results? in|resulted in|induc(?:e|es|ed)|"
                       r"trigger(?:s|ed)?|driv(?:es|en)|rais(?:e|es|ed)|increas(?:e|es|ed)|decreas(?:e|es|ed)|reduc(?:e|es|ed)|"
                       r"improv(?:e|es|ed)|prevent(?:s|ed)?|promot(?:e|es|ed)|inhibit(?:s|ed)?|enhanc(?:e|es|ed)|"
                       r"impair(?:s|ed)?|protects? against|due to|because of|effects? of|affects?|"
                       r"contribut(?:e|es|ed) to|responsible for|mediat(?:e|es|ed))\b", re.I)
NUMBER_RE = re.compile(r"(?<![\w.])(?<![A-Za-z]-)(?:\d+(?:[.,]\d+)*|\.\d+)")
LABEL_BEFORE_RE = re.compile(r"\b(?:fig(?:ure)?s?|tables?|sections?|sec|eqs?|equations?|chapters?|appendix|types?|"
                             r"phases?|stages?|grades?|steps?|refs?)\.?[\s~]*$", re.I)
YEAR_BEFORE_RE = re.compile(r"\b(?:in|since|by|from|until|during|before|after|between|and|early|late|mid|years?)[\s-]+$", re.I)
ABBREVIATIONS = frozenset("al fig figs eq eqs vs cf ca approx dr prof mr mrs ms st no nos vol pp ref refs sec tab".split())
END_RE = re.compile(r"[.!?]+[\"'”’)\]}]*(?:\[\d+(?:\s*[-–,;]\s*\d+)*\])?(?=\s+(?:[\"'“‘(\[*_]*[A-Z0-9]|\\[A-Za-z])|\s*$)")
LEADING_RE = re.compile(r"\s*(?:\[\s*(?:citation needed|@|\d|\?)[^\]]*\]|" + CITE + r"\{[^}]*\})[.;,]?", re.I)
PAGE_RE = re.compile(r"^\[\[page (\d+)\]\][ \t]*$", re.M)
REFERENCES_RE = re.compile(r"(?:references?|bibliography|works cited|literature cited|reference list)", re.I)
CONFERENCE_RE = re.compile(r"\b(?:proceedings|conference|workshop|symposium|congress|meeting)\b|\b(?:proc|conf)\.", re.I)
TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s[^<>]*)?>")
STOPWORDS = frozenset("a an and are as at by for from in into is its of on or that the this to toward towards using via "
                      "with have has been were was which their these those such than also more most between during".split())
BREAK = "\x1f"   # put where a blanked block ends the sentence around it; Python counts it as white space
PLAIN = str.maketrans({**dict.fromkeys("'\"‘’‚‛′″`´“”„‟«»\u00ad"), **dict.fromkeys("‐‑‒–—―−", "-")})
FOLD = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "đ": "d", "ı": "i"})
TEX = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
       "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def squeeze(text) -> str:
    return re.sub(r"\s+", " ", str(text if text is not None else "")).strip()


def digest(text: str) -> str:
    return hashlib.sha1(squeeze(text).casefold().encode("utf-8")).hexdigest()[:12]


def ascii_fold(text) -> str:
    return unicodedata.normalize("NFKD", str(text or "").translate(FOLD)).encode("ascii", "ignore").decode("ascii").lower()


def cell(value) -> str:
    return squeeze(value).replace("|", "/")


def load(directory: Path) -> dict:
    path = directory / "ledger.json"
    if not path.exists():
        return {"tool": "researchzy-citation-finder", "schema_version": 1, "manuscripts": {}, "bib": "",
                "targets": {}, "papers": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON ({exc}). Restore it or move it aside.")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# The manuscript: what is skipped, where sentences end, what a sentence claims


def blank(text: str, pattern: str, flags: int = 0, brk: bool = False) -> str:
    """Turn every match into spaces, keeping line breaks, so that offsets and line numbers stay
    true. With brk the match also ends the sentence around it."""
    def spaces(match):
        out = re.sub(r"[^\n]", " ", match.group(0))
        return BREAK + out[1:] if brk and out[:1] == " " else out
    return re.sub(pattern, spaces, text, flags=flags)


def mask_markdown(text: str) -> tuple[str, list]:
    t = blank(text, r"\A---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*$", re.S | re.M, True)                     # front matter
    t = blank(t, r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[`~]*[ \t]*$|\Z)", re.S | re.M, True)    # fenced code
    t = blank(t, r"<!--.*?-->|\$\$.*?\$\$", re.S)                                                      # comments, display math
    t = blank(t, r"`[^`\n]+`|(?<![\\$\w])\$(?=[^\s$])[^$\n]*?(?<=[^\s$\\])\$(?![\d$])")                # inline code and math
    heading = r"^[ \t]{0,3}#{1,6}[ \t]+(.*)$"
    headings = [(m.start(), m.end(), m.group(1).strip(" #\t")) for m in re.finditer(heading, t, re.M)]
    for i, (_, end, title) in enumerate(headings):                                                   # the reference list
        if REFERENCES_RE.fullmatch(title.strip("*_ ")):
            stop = headings[i + 1][0] if i + 1 < len(headings) else len(t)
            t = t[:end] + blank(t[end:stop], r"\S[^\n]*", 0, True) + t[stop:]
    t = blank(t, heading + r"|^[ \t]*(?:=+|-{3,}|\*{3,}|_{3,})[ \t]*$", re.M, True)                    # headings, rules
    t = blank(t, r"^(?:[ \t]*\||[^\n|]*\|[^\n|]*\|).*$", re.M, True)                                   # tables
    t = blank(t, r"(?<=\])\([^()\s]*(?:\s+\"[^\"]*\")?\)|https?://[^\s)>\]]+")                         # link targets
    t = blank(t, r"^[ \t]*(?:>[ \t]?)*(?:[-*+]|\d+[.)])[ \t]+|^[ \t]*>+[ \t]?", re.M, True)            # list and quote marks
    return t, [(start, title) for start, _, title in headings]


def mask_latex(text: str) -> tuple[str, list]:
    skipped = "verbatim|Verbatim|lstlisting|minted|comment|tabular[xy]?|longtable|array|tikzpicture|thebibliography|filecontents"
    math = "equation|align|alignat|flalign|gather|multline|eqnarray|displaymath|math"
    t = blank(text, r"(?<!\\)%[^\n]*")                                                               # comments
    t = blank(t, r"\A.*?\\begin\{document\}|\\end\{document\}.*\Z", re.S, True)                        # preamble
    t = blank(t, rf"\\begin\{{({skipped})\*?\}}.*?\\end\{{\1\*?\}}", re.S, True)                       # verbatim, tables
    t = blank(t, rf"\\begin\{{({math})\*?\}}.*?\\end\{{\1\*?\}}|\$\$.*?\$\$|(?<!\\)\\\[.*?\\\]|\\\(.*?\\\)", re.S)
    t = blank(t, r"\\verb\*?([^A-Za-z\s]).*?\1|(?<!\\)\$[^$]*?(?<!\\)\$", re.S)                        # \verb, inline math
    heading = r"\\(?:part|chapter|(?:sub){0,2}section|paragraph)\*?(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}"
    headings = [(m.start(), m.group(1)) for m in re.finditer(heading, t)]
    t = blank(t, heading, 0, True)
    t = blank(t, r"\\(?:label|ref|eqref|autoref|[cC]ref|pageref|input|include|includegraphics|bibliography|"
                 r"bibliographystyle|addbibresource|url)\*?(?:\[[^\]]*\])*\{[^{}]*\}")
    t = blank(t, r"\\(?:begin|end)\{[^{}]*\}(?:\[[^\]]*\])?|\\item\b(?:\[[^\]]*\])?|"
                 r"\\(?:maketitle|tableofcontents|printbibliography)\b", 0, True)
    return t, headings


def sentence_spans(masked: str) -> list:
    spans, pos = [], 0
    for sep in [*re.finditer(rf"{BREAK}|\n[ \t]*\n", masked), None]:
        end = sep.start() if sep else len(masked)
        para, start, local = masked[pos:end], 0, []
        for m in END_RE.finditer(para):
            word = re.search(r"[A-Za-z][A-Za-z.]*$", para[start:m.start()])
            word = word.group(0) if word else ""
            if para[m.start()] == "." and (word.lower() in ABBREVIATIONS or "." in word or re.fullmatch("[A-Z]", word)):
                continue                                   # "et al.", "Fig.", "e.g.", an initial: not the end
            local.append([pos + start, pos + m.end()])
            start = m.end()
        if para[start:].strip():
            local.append([pos + start, end])
        for i in range(1, len(local)):   # a placeholder or citation after the full stop belongs to the sentence before
            lead = LEADING_RE.match(masked, local[i][0], local[i][1])
            if lead:
                local[i - 1][1] = local[i][0] = lead.end()
        spans += [tuple(s) for s in local if masked[s[0]:s[1]].strip()]
        pos = sep.end() if sep else end
    return spans


def parse(path: Path) -> dict:
    """A manuscript as sentences, with code, headings, tables, comments, verbatim and math blanked out."""
    suffix = path.suffix.lower()
    if suffix in (".docx", ".doc", ".pdf", ".odt", ".rtf"):
        raise SystemExit(f"{path.name}: give the Markdown or LaTeX source; a {suffix} file is not read here.")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"Cannot read {path}: {exc}")
    kind = "latex" if suffix in (".tex", ".ltx") else "markdown"
    masked, headings = (mask_latex if kind == "latex" else mask_markdown)(text)
    sentences = []
    for start, end in sentence_spans(masked):
        start += len(masked[start:end]) - len(masked[start:end].lstrip())
        end = start + len(masked[start:end].rstrip())
        section = next((title for pos, title in reversed(headings) if pos < start), "")
        sentences.append({"start": start, "end": end, "line": text.count("\n", 0, start) + 1,
                          "end_line": text.count("\n", 0, end) + 1, "section": squeeze(section),
                          "text": squeeze(text[start:end]), "masked": squeeze(masked[start:end])})
    return {"kind": kind, "text": text, "masked": masked, "sentences": sentences}


def claim_text(sentence: str) -> tuple[str, bool]:
    """(what a sentence claims: its text without placeholders, markers and citations; whether it cites a source)."""
    plain = MARKER_RE.sub(" ", PLACEHOLDER_RE.sub(" ", sentence))
    text = PAREN_RE.sub(lambda m: " " if AUTHOR_YEAR_RE.search(m.group(1)) else m.group(0), CITATION_RE.sub(" ", plain))
    return squeeze(text), text != plain


def numbers(text: str, everything: bool = False) -> set:
    """The quantities in a text. Unless everything is wanted, a year after a preposition and the number of a
    figure, table, section, type or phase are left out: a source does not have to state those."""
    found = set()
    for m in NUMBER_RE.finditer(text):
        raw, before = re.sub(r",(?=\d{3}(?!\d))", "", m.group(0)).replace(",", "."), text[:m.start()]
        label = LABEL_BEFORE_RE.search(before) or (re.fullmatch(r"(?:1[5-9]|20)\d\d", raw) and YEAR_BEFORE_RE.search(before))
        if raw.count(".") < 2 and (everything or not label):
            found.add(float(raw))
    return found


def find_items(doc: dict, lines=()) -> tuple[list, list, list]:
    """(placeholders and candidate sentences, other marker forms, placeholders inside skipped blocks)."""
    items, markers, seen = [], [], set()
    for s in doc["sentences"]:
        claim, cited = claim_text(s["masked"])
        common = {"line": s["line"], "section": s["section"], "sentence": s["text"], "claim": claim}
        other = [m.group(0) for m in MARKER_RE.finditer(s["masked"])]
        markers += [{"line": s["line"], "text": text} for text in other]
        holders = list(PLACEHOLDER_RE.finditer(doc["masked"], s["start"], s["end"]))
        for m in holders:
            note = squeeze(PLACEHOLDER_RE.match(doc["text"], m.start()).group(1))
            seen.add(m.start())
            items.append({**common, "kind": "placeholder", "note": note, "why": [], "span": m.span(),
                          "hash": digest(s["text"] + "|" + note)})
        why = [f"marker {text}" for text in other] + ["named with --line"] * any(s["line"] <= n <= s["end_line"] for n in lines)
        if not cited and len(claim.split()) >= 4:
            why += [f"{label}: {m.group(0)}" for label, rx in (("statistic", STATISTIC_RE), ("phrase", PHRASE_RE))
                    for m in [rx.search(claim)] if m]
        if why and not holders:
            items.append({**common, "kind": "candidate", "note": "", "why": why, "hash": digest(s["text"])})
    skipped = [{"line": doc["text"].count("\n", 0, m.start()) + 1, "text": squeeze(m.group(0))}
               for m in PLACEHOLDER_RE.finditer(doc["text"]) if m.start() not in seen]
    return items, markers, skipped


# ---------------------------------------------------------------------------------------------
# Papers, saved tool results, quotes, the rules


def records(path: Path) -> list:
    """The paper records in a saved search_papers or get_paper result."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{path} is not a saved tool result in JSON ({exc}).")
    if isinstance(data, dict):
        data = next((data[name] for name in ("results", "papers", "items") if isinstance(data.get(name), list)),
                    [data.get("paper") if isinstance(data.get("paper"), dict) else data])
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def identifiers(record: dict) -> dict:
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", squeeze(record.get("doi")), flags=re.I).lower()
    arxiv = re.sub(r"^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv:\s*)", "", squeeze(record.get("arxiv") or record.get("arxivId")),
                   flags=re.I).lower()
    return {"doi": doi, "arxiv": re.sub(r"(?:\.pdf)?(?:v\d+)?$", "", arxiv),
            "corpusId": squeeze(record.get("corpusId") or record.get("corpus_id"))}


def clean(text) -> str:
    """A title or venue without markup tags and character entities."""
    return squeeze(html.unescape(TAG_RE.sub("", str(text or ""))))


def title_id(title) -> str:
    return re.sub(r"[^a-z0-9]", "", ascii_fold(re.sub(r"\\[A-Za-z]+", "", clean(title))))


def make_key(paper: dict, taken: set) -> str:
    """First author's family name, year, first content word of the title: ASCII, lower case, not in taken."""
    first = (paper.get("authors") or [""])[0]
    parts = [p for p in (first.split(",")[0] if "," in first else first).split()
             if p.lower().rstrip(".") not in ("jr", "sr", "ii", "iii", "iv")]
    family = re.sub(r"[^a-z0-9]", "", ascii_fold(parts[-1])) if parts else ""
    words = (re.sub(r"[^a-z]", "", ascii_fold(w)) for w in re.findall(r"[^\W\d_]+", clean(paper.get("title"))))
    base = f"{family or 'anon'}{paper.get('year') or ''}{next((w for w in words if len(w) > 2 and w not in STOPWORDS), '')}"
    key, n = base, 0
    while key in taken:
        n += 1
        key = f"{base}{chr(96 + n) if n <= 26 else n}"
    return key


def normalise(text: str) -> str:
    """Text for comparing a quote with its source: Unicode forms, case, white space, dashes and hyphenation (at a
    line break or inside a word) are made the same on both sides, and quotation marks and apostrophes are dropped."""
    text = unicodedata.normalize("NFKC", text).translate(PLAIN)
    return re.sub(r"\s+", " ", re.sub(r"(?<=[^\W\d_])-\s*(?=[^\W\d_])", "", text)).casefold().strip()


def find_quote(quote: str, text: str) -> tuple[bool, int | None]:
    """Whether the quote is in the text, and the page it is on when the text has [[page N]] marks."""
    wanted = normalise(quote)
    if not wanted or wanted not in normalise(PAGE_RE.sub("\n", text)):
        return False, None
    parts = PAGE_RE.split(text)
    return True, next((int(n) for n, body in zip(parts[1::2], parts[2::2]) if wanted in normalise(body)), None)


def source_text(ledger: dict, t: dict) -> tuple[str, str]:
    """(text, problem) for the file a verdict's quote is said to come from. A .json source is a saved
    record: its text is the abstract of the verdict's paper in that file."""
    path = Path(t["source"])
    if not t["source"] or not path.is_file():
        return "", f"the source {t['source'] or '(none given)'} does not exist"
    if path.suffix.lower() != ".json":
        return path.read_text(encoding="utf-8", errors="replace"), ""
    wanted = {k: v for k, v in identifiers(ledger["papers"][t["paper"]]).items() if v}
    try:
        found = [r for r in records(path) if any(identifiers(r)[k] == v for k, v in wanted.items())]
    except SystemExit as exc:
        return "", str(exc)
    abstract = squeeze(found[0].get("abstract") or found[0].get("abstractText")) if found else ""
    return abstract, "" if abstract else f"{t['source']} holds no abstract of this paper"


def counted(t: dict) -> set:
    """The searches that count toward not_found: distinct, completed keyword searches of the index."""
    return {(squeeze(s["query"]).casefold(), s["sort"] or "relevance", json.dumps(s["filters"], sort_keys=True))
            for s in t["searches"] if s["tool"] == "search_papers" and s["by"] == "query" and not s["failed"]}


def inspect(ledger: dict, t: dict, bib: bool = True) -> tuple[list, int | None]:
    """The rules a target breaks, and the page its quote was found on."""
    verdict, reason, problems, page = t["verdict"], squeeze(t["reason"]), [], None
    if verdict not in VERDICTS:
        return [f"unknown verdict {verdict!r}" if verdict else "no verdict"], None
    if verdict in ("not_needed", "not_checked") and not reason:
        problems.append(f"{verdict} without a reason")
    if verdict == "not_found" and len(counted(t)) < MIN_SEARCHES and not reason:
        problems.append(f"not_found after {len(counted(t))} of {MIN_SEARCHES} keyword searches of the index, and no reason")
    if verdict not in ("not_needed", "not_found") and not t["searches"] and not reason:
        problems.append("no search is logged for this target")
    if verdict not in QUOTED:
        return problems, None
    paper = ledger["papers"].get(t["paper"])
    if paper is None:
        return problems + ["no paper is recorded for this verdict"], None
    if not any(identifiers(paper).values()):
        problems.append("the paper has no DOI, arXiv id or corpusId")
    grade, quote = t["grade"], squeeze(t["quote"])
    if grade not in GRADES[1:]:
        problems.append(f"grade {grade or 'not set'}: a paper known only by its metadata is never support")
    text, trouble = source_text(ledger, t)
    if trouble:
        problems.append(trouble)
    elif len(quote.split()) < MIN_QUOTE_WORDS:
        problems.append(f"the quote has fewer than {MIN_QUOTE_WORDS} words")
    else:
        found, page = find_quote(quote, text)
        if not found:
            problems.append(f"the quote is not in {t['source']}")
    if grade == "full-text" and not trouble:
        words = len(PAGE_RE.sub("", text).split())
        if t["source"].lower().endswith(".json"):
            problems.append("grade full-text rests on a saved record, which holds only the abstract")
        elif words < MIN_FULL_TEXT_WORDS:
            problems.append(f"{t['source']} has {words} words: too short to be a full text, so the grade is abstract")
    if verdict == "partial" and not squeeze(t["wording"]):
        problems.append("partial without a narrower wording")
    if verdict in ACCEPTED:
        claim = claim_text(t["wording"])[0] if verdict == "partial" else t["claim"]
        wanted = numbers(claim)
        strong = [f"the number {n:g}" for n in sorted(wanted)] + [f'"{m.group(0)}"' for rx in (COMPARISON_RE, CAUSAL_RE)
                                                                  for m in [rx.search(claim)] if m]
        if strong and grade != "full-text" and not (wanted and wanted <= numbers(quote, True)):
            problems.append(f"the {'suggested wording' if verdict == 'partial' else 'sentence'} carries {', '.join(strong)}: "
                            "it needs grade full-text" + (", or every number inside the quote" if wanted else ""))
        if bib and not paper.get("bib"):
            problems.append("the citation key is not final: run bib")
    return problems, page


# ---------------------------------------------------------------------------------------------
# BibTeX


def braced(text: str, start: int) -> int:
    """The index just after the brace group that opens at start."""
    depth = 0
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return i + 1
    return len(text)


def parse_bib(path: Path) -> list:
    """The key, title and DOI of each entry of a .bib file: enough to recognise a paper that is already in it."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SystemExit(f"Cannot read {path}: {exc}")
    entries = []
    for m in re.finditer(r"@(?!comment|string|preamble)\w+\s*(\{)\s*([^\s,{}]+)\s*,", text, re.I):
        body, entry = text[m.end():braced(text, m.start(1))], {"key": m.group(2)}
        for name in ("title", "doi"):
            field = re.search(rf'(?<![\w-]){name}\s*=\s*(?:(\{{)|"([^"]*)"|([^\s,}}]+))', body, re.I)
            if field:
                value = body[field.end(1):braced(body, field.start(1)) - 1] if field.group(1) else None
                entry[name] = value if value is not None else field.group(2) or field.group(3)
        entries.append(entry)
    return entries


def bib_entry(paper: dict) -> str:
    """One BibTeX entry from the fields the index returned. Nothing is filled in: no volume, number or pages."""
    def tex(text) -> str:
        return "".join(TEX.get(ch, ch) for ch in str(text))

    venue, arxiv = clean(paper.get("venue")), paper.get("arxiv")
    kind, where = "misc", ""
    if venue and not (arxiv and re.search(r"arxiv|preprint", venue, re.I)):
        kind, where = ("inproceedings", "booktitle") if CONFERENCE_RE.search(venue) else ("article", "journal")
    names = ["{" + tex(n) + "}" if " and " in n else tex(n) for n in paper.get("authors") or []]
    if names and (paper.get("authorCount") or 0) > len(names):
        names.append("others")
    fields = [("author", " and ".join(names)), ("title", "{" + tex(clean(paper.get("title"))) + "}"),
              ("year", paper.get("year")), (where, tex(venue)), ("doi", paper.get("doi")), ("eprint", arxiv),
              ("archivePrefix", "arXiv" if arxiv else "")]
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields if name and value not in ("", None))
    return f"@{kind}{{{paper['key']},\n{body}\n}}"


# ---------------------------------------------------------------------------------------------
# Commands


def target(ledger: dict, ref: str) -> dict:
    t = ledger["targets"].get(ref)
    if t is None:
        raise SystemExit(f"No target {ref!r}. Run targets first; it lists the ids.")
    if not t["confirmed"]:
        raise SystemExit(f"{ref} is a candidate sentence, not a target. If it needs a citation: confirm {ref}")
    return t


def write_targets(directory: Path, ledger: dict) -> None:
    rows = sorted(ledger["targets"].values(), key=lambda t: (not t["confirmed"], t["file"], t["line"]))
    lines = ["# Citation targets", "", "A candidate is a sentence the script flagged. It becomes a target only with `confirm`.",
             "", "| Id | Status | Where | Section | Sentence | Source wanted for, or why listed |", "|---|---|---|---|---|---|"]
    lines += [f"| {t['id']} | {'target' if t['confirmed'] else 'candidate'}{', no longer in the manuscript' * t['gone']} | "
              f"{Path(t['file']).name}:{t['line']} | {cell(t['section'])} | {cell(t['sentence'])} | "
              f"{cell(t['note'] or '; '.join(t['why']))} |" for t in rows]
    for name, m in ledger["manuscripts"].items():
        lines += [""] + [f"- `{name}`, line {x['line']}: marker `{x['text']}` is not the house form `[Citation needed: …]`; "
                         "its sentence is listed as a candidate" for x in m["markers"]]
        lines += [f"- `{name}`, line {x['line']}: `{x['text']}` is inside a heading, table, code block, comment or formula "
                  "and is not a target; look at it by hand" for x in m["skipped"]]
    write(directory / "targets.md", "\n".join(lines) + "\n")


def cmd_targets(ledger: dict, args) -> dict:
    path, directory = Path(args.manuscript), Path(args.dir)
    doc = parse(path)
    items, markers, skipped = find_items(doc, args.line or ())
    ledger["bib"] = args.bib or ledger["bib"]
    titles = [(e["key"], squeeze(e.get("title")), set(re.findall(r"[a-z]{4,}", ascii_fold(e.get("title")))))
              for e in (parse_bib(Path(ledger["bib"])) if ledger["bib"] else [])]
    mine = {t["hash"]: t for t in ledger["targets"].values() if Path(t["file"]).name == path.name}
    seen = set()
    for item in items:
        t = mine.get(item["hash"])
        if t is None:
            prefix = "t" if item["kind"] == "placeholder" else "c"
            name = f"{prefix}{1 + max([int(k[1:]) for k in ledger['targets'] if k[0] == prefix], default=0)}"
            t = mine[item["hash"]] = ledger["targets"][name] = {
                "id": name, "file": str(path), "kind": item["kind"], "confirmed": prefix == "t", "hash": item["hash"],
                "need": "", "searches": [], "candidates": [], **dict.fromkeys(VERDICT_FIELDS, "")}
        t.update({k: item[k] for k in ITEM_FIELDS}, gone=False)
        words = set(re.findall(r"[a-z]{4,}", ascii_fold(t["note"] + " " + t["claim"]))) - STOPWORDS
        t["in_bib"] = [{"key": key, "title": title} for key, title, has in titles if len(words & has) >= 2][:3]
        seen.add(t["id"])
    present = {digest(s["text"]): s["line"] for s in doc["sentences"]}
    for t in [t for t in mine.values() if t["id"] not in seen]:
        if t["confirmed"] and t["kind"] == "candidate" and t["hash"] in present:
            t["line"] = present[t["hash"]]            # confirmed earlier; no longer flagged, still in the text
        elif t["confirmed"]:
            t["gone"] = True                          # kept, with what was found for it
        else:
            del ledger["targets"][t["id"]]
    ledger["manuscripts"][path.name] = {"path": str(path), "kind": doc["kind"], "markers": markers, "skipped": skipped}
    write_targets(directory, ledger)
    here = sorted((t for t in mine.values() if t["id"] in ledger["targets"]), key=lambda t: t["line"])
    shown = ("id", "line", "section", "sentence", "note", "why", "need", "verdict", "in_bib")
    return {"manuscript": str(path), "style": doc["kind"],
            "targets": [{k: t[k] for k in shown if t.get(k)} for t in here if t["confirmed"] and not t["gone"]],
            "candidates": [{k: t[k] for k in ("id", "line", "why", "sentence")} for t in here if not t["confirmed"]],
            "other_markers": markers, "placeholders_in_skipped_blocks": skipped,
            "no_longer_in_the_manuscript": [t["id"] for t in here if t["gone"]], "file": str(directory / "targets.md")}


def cmd_confirm(ledger: dict, args) -> dict:
    for ref in args.ids:
        if ref not in ledger["targets"]:
            raise SystemExit(f"No candidate {ref!r}. Run targets first; it lists the ids.")
        ledger["targets"][ref]["confirmed"] = True
    write_targets(Path(args.dir), ledger)
    return {"confirmed": args.ids}


def cmd_need(ledger: dict, args) -> dict:
    t = target(ledger, args.target)
    if args.type == "not_needed":
        if not args.reason:
            raise SystemExit("not_needed takes --reason: whose result it is, or why it is common knowledge.")
        t.update(dict.fromkeys(VERDICT_FIELDS, ""), verdict="not_needed", reason=args.reason)
    elif t["verdict"] == "not_needed":
        t.update(verdict="", reason="")
    t["need"] = args.type
    return {"target": t["id"], "need": t["need"]}


def cmd_search(ledger: dict, args) -> dict:
    t = target(ledger, args.target)
    bad = [item for item in args.filter or [] if "=" not in item]
    if bad:
        raise SystemExit(f"--filter takes name=value, got {bad[0]!r}")
    looked_at = args.looked_at
    if not args.failed:
        if args.total is None or not args.saved:
            raise SystemExit("A completed search takes --total and --saved (the tool result, saved as returned). "
                             "A search the tool did not answer takes --failed with its code and message.")
        if not Path(args.saved).is_file():
            raise SystemExit(f"{args.saved} does not exist. Save the tool result first.")
        looked_at = len(records(Path(args.saved))) if looked_at is None else looked_at
    search = {"id": f"s{1 + sum(len(x['searches']) for x in ledger['targets'].values())}", "tool": args.tool,
              "by": "doi" if args.doi else "arxiv" if args.arxiv else "query", "query": args.query or args.doi or args.arxiv,
              "sort": args.sort or "", "filters": dict(item.split("=", 1) for item in args.filter or []),
              "total": args.total, "looked_at": looked_at, "saved": args.saved or "", "failed": args.failed or ""}
    t["searches"].append(search)
    return {"target": t["id"], "search": search["id"], "keyword_searches_counted": len(counted(t))}


def cmd_candidate(ledger: dict, args) -> dict:
    t = target(ledger, args.target)
    asked = identifiers({"doi": args.doi, "arxiv": args.arxiv, "corpusId": args.corpus_id})
    name, value = next(((n, v) for n, v in asked.items() if v), ("identifier", ""))
    record = next((r for r in records(Path(args.file)) if value and identifiers(r)[name] == value), None)
    if record is None or not clean(record.get("title")):
        raise SystemExit(f"No record with {name} {value} and a title in {args.file}. Only a record that a tool returned in "
                         "this session can be cited: save the search_papers or get_paper result and name that file.")
    ids = identifiers(record)
    pid = ids["corpusId"] or "x" + digest(ids["doi"] or ids["arxiv"])
    paper = ledger["papers"].setdefault(pid, {})
    names = [squeeze(a.get("name") if isinstance(a, dict) else a) for a in record.get("authors") or []]
    fields = {"title": squeeze(record["title"]), "authors": [n for n in names if n], "authorCount": record.get("authorCount"),
              "year": record.get("year"), "venue": squeeze(record.get("venue")), "readerUrl": record.get("readerUrl"),
              "hasReadablePdf": record.get("hasReadablePdf"), **ids}
    paper.update({k: v for k, v in fields.items() if v not in (None, "", [])})
    abstract = squeeze(record.get("abstract") or record.get("abstractText"))
    if abstract or "record" not in paper:
        paper.update(record=args.file, has_abstract=bool(abstract))
    if "key" not in paper:
        paper["key"] = make_key(paper, {p.get("key", "").lower() for p in ledger["papers"].values()})
    if pid not in [c["paper"] for c in t["candidates"]]:
        found_by = args.search or next((s["id"] for s in t["searches"] if s["saved"] == args.file), "")
        t["candidates"].append({"paper": pid, "grade": "metadata", "search": found_by})
    return {"target": t["id"], "paper": paper["key"], "grade": "metadata", "title": paper["title"],
            "has_abstract": paper["has_abstract"], "has_pdf": paper.get("hasReadablePdf")}


def cmd_text(ledger: dict, args) -> dict:
    pdf = Path(args.pdf)
    if not pdf.is_file() or pdf.read_bytes()[:5] != b"%PDF-":
        raise SystemExit(f"{pdf} is not a PDF file.")
    module = next((name for name in ("pymupdf", "fitz") if importlib.util.find_spec(name)), None)
    if module:
        try:
            with importlib.import_module(module).open(pdf) as doc:
                pages = [page.get_text() for page in doc]
        except Exception as exc:   # a damaged or encrypted file
            raise SystemExit(f"Could not read {pdf}: {exc}")
    elif shutil.which("pdftotext"):
        run = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"], capture_output=True)
        if run.returncode:
            raise SystemExit(f"pdftotext could not read {pdf}: {run.stderr.decode('utf-8', 'replace').strip()}")
        pages = run.stdout.decode("utf-8", "replace").rstrip("\f").split("\f")
    else:
        return {"text": None, "extractor": None,
                "message": "Neither PyMuPDF nor the pdftotext binary is available, so the PDF was not read. Ask the user "
                           "before installing either; until one is there, the grade can be abstract at most."}
    out = Path(args.dir) / "texts" / f"{args.name or pdf.stem}.txt"
    write(out, "".join(f"[[page {i}]]\n{page.strip()}\n" for i, page in enumerate(pages, 1)))
    words = sum(len(page.split()) for page in pages)
    return {"text": str(out), "extractor": "PyMuPDF" if module else "pdftotext", "pages": len(pages), "words": words,
            "long_enough_for_a_full_text": words >= MIN_FULL_TEXT_WORDS}


def cmd_verdict(ledger: dict, args) -> dict:
    t, verdict, quote, pid = target(ledger, args.target), args.verdict, squeeze(args.quote), ""
    if verdict in QUOTED:
        missing = [name for name in ("paper", "grade", "quote", "source") if not getattr(args, name)]
        missing += ["wording"] * (verdict == "partial" and not args.wording)
        if missing:
            raise SystemExit(f"{verdict} needs " + ", ".join("--" + m for m in missing)
                             + ". A paper that was not read against the sentence gives not_checked, not support.")
        if len(quote.split()) < MIN_QUOTE_WORDS:
            raise SystemExit(f"The quote has fewer than {MIN_QUOTE_WORDS} words: quote the sentence that carries the claim.")
        if not Path(args.source).is_file():
            raise SystemExit(f"{args.source} does not exist. Name the saved text file or the saved record the quote is from.")
        if args.grade == "full-text" and args.source.lower().endswith((".json", ".pdf")):
            raise SystemExit("Grade full-text needs the text file of the paper: make it with the text command.")
    elif verdict == "not_found" and len(counted(t)) < MIN_SEARCHES and not args.reason:
        raise SystemExit(f"not_found needs {MIN_SEARCHES} logged keyword searches of the index ({len(counted(t))} so far), "
                         "or --reason.")
    elif verdict in ("not_needed", "not_checked") and not args.reason:
        raise SystemExit(f"{verdict} needs --reason.")
    if args.paper:
        asked = identifiers({"doi": args.paper, "arxiv": args.paper})
        pid = next((c["paper"] for c in t["candidates"] for p in [ledger["papers"][c["paper"]]] if args.paper in
                    (c["paper"], p["key"]) or asked["doi"] == p.get("doi") or asked["arxiv"] == p.get("arxiv")), "")
        if not pid:
            raise SystemExit(f"{args.paper!r} is not a candidate of {t['id']}. Record it first with the candidate command.")
    t.update(verdict=verdict, paper=pid, grade=(args.grade or "") if verdict in QUOTED else "", quote=quote,
             source=args.source or "", locator=args.locator or "", wording=args.wording or "", reason=args.reason or "")
    t["need"] = "not_needed" if verdict == "not_needed" else t["need"]
    if verdict in QUOTED:
        next(c for c in t["candidates"] if c["paper"] == pid)["grade"] = args.grade
    return {"target": t["id"], "verdict": verdict, "paper": ledger["papers"][pid]["key"] if pid else None,
            "problems": inspect(ledger, t, bib=False)[0]}


def cmd_bib(ledger: dict, args) -> dict:
    ledger["bib"] = args.bib or ledger["bib"]
    theirs = parse_bib(Path(ledger["bib"])) if ledger["bib"] else []
    by_doi = {identifiers(e)["doi"]: e["key"] for e in theirs if e.get("doi")}
    by_title = {title_id(e["title"]): e["key"] for e in theirs if title_id(e.get("title"))}
    accepted = sorted({t["paper"] for t in ledger["targets"].values()
                       if t["verdict"] in ACCEPTED and t["paper"] in ledger["papers"]})
    reused, new = [], []
    for pid in accepted:
        paper = ledger["papers"][pid]
        key, how = by_doi.get(paper.get("doi") or ""), "the same DOI"
        if not key:
            key, how = by_title.get(title_id(paper["title"])), "the same title"
        if key:
            paper.update(key=key, bib="in_user_bib")
            reused.append({"key": key, "matched_by": how, "title": paper["title"]})
            continue
        taken = {e["key"].lower() for e in theirs} | {p["key"].lower() for q, p in ledger["papers"].items() if q != pid}
        if paper["key"].lower() in taken or paper.get("bib") == "in_user_bib":
            paper["key"] = make_key(paper, taken)
        paper["bib"] = "new"
        new.append(paper)
    head = ["% new-references.bib, written by researchzy-citation-finder. Do not edit: run bib again.",
            f"% {len(new)} {'entry' if len(new) == 1 else 'entries'}, from fields Researchzy's index returned in this session.",
            "% The index returns no volume, issue or pages, so the entries have none. Retraction status was not checked.",
            "% researchzy-reference-check (plugin researchzy-manuscript) completes and verifies these entries."]
    head += [f"% Already in {ledger['bib']}, cited under their keys there: " + ", ".join(r["key"] for r in reused)] * bool(reused)
    out = Path(args.dir) / "new-references.bib"
    write(out, "\n".join(head) + "\n" + "".join("\n" + bib_entry(p) + "\n" for p in new))
    return {"file": str(out), "new_entries": [p["key"] for p in new], "reused_keys": reused,
            "compared_with": ledger["bib"] or None, "not_in_the_entries": ["volume", "number", "pages"],
            "not_checked": "retraction status"}


def cmd_check(ledger: dict, args) -> dict:
    directory = Path(args.dir)
    rows = sorted(ledger["targets"].values(), key=lambda t: (t["file"], t["line"]))
    targets, waiting = [t for t in rows if t["confirmed"]], [t["id"] for t in rows if not t["confirmed"]]
    found = {t["id"]: inspect(ledger, t) for t in targets}
    problems = [{"target": tid, "problem": p} for tid, (broken, _) in found.items() for p in broken]
    if any(p.get("bib") == "new" for p in ledger["papers"].values()) and not (directory / "new-references.bib").is_file():
        problems.append({"target": None, "problem": "new-references.bib is missing: run bib"})
    counts = Counter((t["verdict"] or "no verdict").replace("_", " ") for t in targets)
    lines = ["# Citation map", "",
             f"{len(targets)} targets: " + ", ".join(f"{n} {v}" for v, n in counts.items()) + ". "
             + (f"Broken rules: {len(problems)}, each listed with its target." if problems else "No rule is broken.")
             + f" Candidate sentences never confirmed as targets (targets.md): {', '.join(waiting)}." * bool(waiting), "",
             "Not checked here: retraction status (the index holds no retraction data), and volume, issue and pages (the "
             "index does not return them). `researchzy-reference-check` (plugin `researchzy-manuscript`), when installed, "
             "completes and verifies the entries.", "",
             "| Target | Where | Verdict | Citation key | Grade | Rules broken |", "|---|---|---|---|---|---|"]
    details = []
    for t in targets:
        (broken, page), verdict, paper = found[t["id"]], t["verdict"], ledger["papers"].get(t["paper"])
        name, key = verdict.replace("_", " ") or "no verdict", f"`{paper['key']}`" if paper and verdict in ACCEPTED else ""
        lines.append(f"| {t['id']} | {Path(t['file']).name}:{t['line']} | {name} | {key} | {t['grade']} | "
                     f"{len(broken) or 'none'} |")
        details += ["", f"## {t['id']}: {name}", "",
                    f"- Where: `{t['file']}`, line {t['line']}" + (f", section \"{t['section']}\"" if t["section"] else "")
                    + " (the sentence is no longer in the manuscript)" * t["gone"],
                    f"- Sentence: {t['sentence']}", f"- Needs: {t['need'].replace('_', ' ') or 'not set'}"]
        if paper:
            names = paper.get("authors") or ["no author returned"]
            who = names[0] + " et al." * ((paper.get("authorCount") or len(names)) > 1)
            ident = next((f"{label}{paper[k]}" for k, label in (("doi", "doi:"), ("arxiv", "arXiv:"), ("corpusId", "corpusId "))
                          if paper.get(k)), "no identifier")
            details.append(f"- {'Paper' if verdict in QUOTED else 'Lead, not accepted as support'}: {who} "
                           f"({paper.get('year') or 'no year'}). {clean(paper['title']).rstrip('.')}. "
                           + f"{clean(paper.get('venue'))}. " * bool(paper.get("venue")) + ident)
        if key:
            where = {"in_user_bib": "the key it already has in the author's .bib", "new": "a new entry in new-references.bib"}
            details.append(f"- Citation key: {key}, " + where.get(paper.get("bib"), "not final: run bib"))
        if verdict in QUOTED:
            place = ", ".join(x for x in (f"p. {page}" if page else "", t["locator"], f"`{t['source']}`") if x)
            details += [f"- Grade: {t['grade']}", f"- Quote: \"{t['quote']}\" ({place})"]
        details += [f"- {label}: {t[k]}" for k, label in (("wording", "Suggested wording"), ("reason", "Reason")) if t[k]]
        if verdict == "not_found":
            details.append("- Not found in the index with the searches below. That is not a statement that no such paper exists.")
        details += [f"- Search {s['id']} ({s['tool']}{'' if s['by'] == 'query' else ', ' + s['by'] + ' look-up'}): `{s['query']}`"
                    + (f", failed: {s['failed']}" if s["failed"] else f", {s['total']} reported, {s['looked_at']} looked at"
                       + "".join(f", {k}={v}" for k, v in {"sort": s["sort"], **s["filters"]}.items() if v)
                       + f", saved as `{s['saved']}`") for s in t["searches"]]
        others = [f"`{ledger['papers'][c['paper']]['key']}` ({c['grade']})" for c in t["candidates"] if c["paper"] != t["paper"]]
        details += ["- Other candidates recorded: " + ", ".join(others)] * bool(others)
        details += [f"- **Rule broken:** {p}" for p in broken]
    write(directory / "citation-map.md", "\n".join(lines + details) + "\n")
    return {"targets": len(targets), "verdicts": dict(counts), "problems": problems, "candidates_not_confirmed": waiting,
            "no_longer_in_the_manuscript": [t["id"] for t in targets if t["gone"]],
            "not_checked_here": ["retraction status", "volume, issue and pages"],
            "file": str(directory / "citation-map.md"), "ok": not problems}


def cmd_apply(ledger: dict, args) -> dict:
    path, doc = Path(args.manuscript), parse(Path(args.manuscript))
    mine = {t["hash"]: t for t in ledger["targets"].values() if Path(t["file"]).name == path.name}
    used = Counter(re.findall(r"\\(citep|parencite|autocite|cite)\*?(?:\[[^\]]*\])*\{(?!\s*\?)", doc["masked"])).most_common(1)
    text, replaced, left = doc["text"], [], []
    for item in reversed([i for i in find_items(doc)[0] if i["kind"] == "placeholder"]):
        t = mine.get(item["hash"])
        broken = inspect(ledger, t)[0] if t else ["not in the ledger: run targets again"]
        if t and t["verdict"] == "supported" and not broken:
            key = ledger["papers"][t["paper"]]["key"]
            cite = f"\\{used[0][0] if used else 'cite'}{{{key}}}" if doc["kind"] == "latex" else f"[@{key}]"
            text = text[:item["span"][0]] + cite + text[item["span"][1]:]
            replaced.append({"target": t["id"], "line": item["line"], "citation": cite})
        else:
            left.append({"target": t["id"] if t else None, "line": item["line"],
                         "why": broken[0] if not t or t["verdict"] == "supported" else f"verdict {t['verdict'] or 'not set'}"})
    out = Path(args.dir) / f"{path.stem}.cited{path.suffix}"
    write(out, text)
    return {"copy": str(out), "original": str(path), "original_changed": False, "replaced": replaced[::-1],
            "placeholders_left": left[::-1]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The ledger of a citation search.")
    parser.add_argument("--dir", default="citations", help="The output folder (default: citations)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("targets", help="Find placeholders, other markers and candidate sentences in a manuscript")
    p.add_argument("manuscript", help="A .md or .tex file")
    p.add_argument("--bib", help="The author's .bib: entries that may already cover a target are listed with it")
    p.add_argument("--line", type=int, action="append", help="List the sentence on this line as a candidate (repeatable)")

    p = sub.add_parser("confirm", help="Make candidate sentences targets")
    p.add_argument("ids", nargs="+")

    p = sub.add_parser("need", help="Record what kind of source a target needs")
    p.add_argument("target")
    p.add_argument("type", choices=NEEDS)
    p.add_argument("--reason", help="Required for not_needed")

    p = sub.add_parser("search", help="Log one search made for a target")
    p.add_argument("target")
    group = p.add_mutually_exclusive_group(required=True)
    for flag, text in (("--query", "The keywords searched"), ("--doi", "A look-up by DOI"), ("--arxiv", "A look-up by arXiv id")):
        group.add_argument(flag, help=text)
    p.add_argument("--total", type=int, help="How many results the tool reported in all")
    p.add_argument("--looked-at", dest="looked_at", type=int, help="How many were looked at (default: the records saved)")
    p.add_argument("--sort", choices=("relevance", "citationCount", "year", "influency"))
    p.add_argument("--filter", action="append", help="name=value, e.g. yearFrom=2015 (repeatable)")
    p.add_argument("--saved", help="The file the tool result was saved to, as returned")
    p.add_argument("--failed", help="The tool's code and message when the search did not complete")
    p.add_argument("--tool", choices=("search_papers", "list_library_papers"), default="search_papers")

    p = sub.add_parser("candidate", help="Record a paper for a target from a saved tool result; it starts at grade metadata")
    p.add_argument("target")
    p.add_argument("file", help="A saved search_papers or get_paper result")
    group = p.add_mutually_exclusive_group(required=True)
    for flag in ("--doi", "--arxiv", "--corpus-id"):
        group.add_argument(flag)
    p.add_argument("--search", help="The search that returned it (default: the one saved to this file)")

    p = sub.add_parser("text", help="Write a PDF's text, with page marks, to the texts folder")
    p.add_argument("pdf")
    p.add_argument("--name", help="Name of the text file (default: the PDF's name)")

    p = sub.add_parser("verdict", help="Record the verdict for a target")
    p.add_argument("target")
    p.add_argument("verdict", choices=VERDICTS)
    p.add_argument("--grade", choices=GRADES[1:], help="How far the paper was read")
    for flag, text in (("--paper", "Citation key, DOI, arXiv id or corpusId of a recorded candidate"),
                       ("--quote", "The words of the paper that carry the claim, copied exactly"),
                       ("--source", "The text file (for an abstract, the saved record) the quote is from"),
                       ("--locator", "Section or page of the quote"),
                       ("--wording", "For partial: the narrower sentence the paper supports"),
                       ("--reason", "For not_needed and not_checked, and for not_found with fewer than three searches")):
        p.add_argument(flag, help=text)

    p = sub.add_parser("bib", help="Write new-references.bib for the accepted papers")
    p.add_argument("--bib", help="The author's .bib: a paper already in it keeps its key and gets no new entry")
    sub.add_parser("check", help="Check every rule and write citation-map.md")
    p = sub.add_parser("apply", help="Write a copy of the manuscript with the supported placeholders replaced by citations")
    p.add_argument("manuscript")

    args = parser.parse_args(argv)
    ledger = load(Path(args.dir))
    result = globals()[f"cmd_{args.command}"](ledger, args)
    if args.command not in ("check", "apply", "text"):
        write(Path(args.dir) / "ledger.json", json.dumps(ledger, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if args.command == "check" and not result["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
