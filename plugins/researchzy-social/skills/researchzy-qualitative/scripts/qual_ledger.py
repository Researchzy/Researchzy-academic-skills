#!/usr/bin/env python3
"""The ledger of a qualitative analysis: every coding is a quote at recorded offsets in a transcript, every
code is in the current codebook, support is counted from the codings, and the model's coding is calibrated
against the user's blind coding.

  qual_ledger.py locate S03 "quoted words"            where the words stand in a source, in whose turn (- reads stdin)
  qual_ledger.py check [--findings draft.md]          sources, quotes, speakers, codes, themes, identifiers
  qual_ledger.py support                              participants and sources per code and theme; new codes per source
  qual_ledger.py sample --seed 20261118 [--size N]    draw units for a calibration round; write the model's file
  qual_ledger.py seal [--round N]                     record the SHA-256 of the model's filled file; write the user's
  qual_ledger.py score [--round N] [--boot 1000]      kappa and alpha per code; every disagreement with its text
  qual_ledger.py export                               export.csv, and export.xlsx when openpyxl is installed

Every command takes --dir (default qualitative), the folder with protocol.json, approach.md, sources.csv,
codebook.csv, codebook-changes.csv, codings.jsonl, themes.csv, negative-cases.csv and identifiers.txt in
the formats of references/. Offsets count Unicode characters from 0 in a transcript read as UTF-8 with its
line endings as \\n; the end is exclusive.

check: a quote must equal the text at its offsets after NFKC and white-space normalisation. Otherwise it is
looked for in its source (the right offsets are reported) and in the other sources (wrong source). A quote
verbatim nowhere is "altered" when it was cut from the text or quote_match grades it EXACT, INTERLEAVED or
PARTIAL (transcripts are the user's own text, not PDF extractions), and "not found" when it is ABSENT. A
quote with an ellipsis (…… ... [...]) matches part by part, in order, inside one speaker turn. Also: the
speaker of the turn; a code unknown, retired, renamed or merged, or redefined after the coding's codebook
version; themes; negative cases; quotations of a findings draft (verbatim, in the ledger, said by the
participant named); any line of identifiers.txt in a file of the folder, in the draft or in a transcript
marked de-identified, reported by line number, never by value. A transcript the user has not confirmed
de-identified is not_checked, which is never a pass.

sample draws participant turns not drawn before (paragraphs where a source has no speaker labels) with a
seed; the model fills the codes column of its file; seal records that file's SHA-256 and only then writes
the user's file; score refuses when the model's file changed after the seal, when the round was scored
before (a scored round is final) or when the codebook changed since the draw. Under reflexive analysis,
sample and score refuse. Thresholds and sizes are settings of protocol.json; defaults are conventions and
are labelled so in every output.

Exit codes: 0 done; 1 when check finds a failure, export is refused, a round is below its thresholds or not
assessable, or sample or score is refused under reflexive analysis; 2 when an input cannot be read or is
not in the documented format. Standard library only; export writes xlsx when openpyxl is installed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import random
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rz_agreement as ra  # noqa: E402
from quote_match import match_quality, tokens  # noqa: E402

APPROACHES = ("reflexive", "codebook", "grounded")
KINDS = ("interview", "focus_group", "fieldnote", "open_ended", "document")
CHANGES = ("added", "renamed", "merged", "retired", "redefined")
NEGATIVE = ("counter_example", "boundary_case", "dimensional_variation", "insufficient_data")
GRADES = ("ABSENT", "PARTIAL", "INTERLEAVED", "EXACT")
INTERVIEWER, MODEL = "interviewer", "model"
CODING_FIELDS = ("id", "source", "start", "end", "quote", "speaker", "code", "coder", "codebook_version")
DEFAULTS = {"min_participants": 2, "kappa_min": 0.6, "alpha_min": 0.667, "sample_size": 30, "min_unit_words": 5}
BLOCKING = ("source", "coding", "quote", "speaker", "code", "identifiers", "deidentified")
SCANNED = (".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".xlsx")
MIN_PIECE = 4               # a verbatim piece shorter than this many words (a CJK character is one) proves nothing
MIN_FINDINGS_QUOTE = 4      # a shorter quoted string in a draft is a term, not a participant's words
CJK = "぀-ヿ㐀-䶿一-鿿豈-﫿가-힯"
CJK_CHAR = re.compile(f"[{CJK}]")
ELLIPSIS = re.compile(r"\s*[\[(]?\s*\.{3,}\s*[\])]?\s*")       # after NFKC, … is ... and ［…］ is [...]
QUOTED = re.compile(r"“([^”]{2,800})”|「([^」]{2,800})」|『([^』]{2,800})』|\"([^\"\n]{2,800})\"")
PARAGRAPH = re.compile(r"\S[^\n]*(?:\n[ \t]*\S[^\n]*)*")
GENERAL = re.compile(r"普遍|大多数|大部分|几乎所有|所有受访者|全部受访者|一致认为|都认为|\b(?:all|most|the majority|generally|"
                     r"in general|widely|commonly|consistently|almost all|nearly all|everyone|every participant)\b", re.I)
REFLEXIVE = ("The approach in protocol.json is reflexive thematic analysis. There the codes are the researcher's "
             "interpretation and agreement between coders is not evidence of quality, so no coefficient is computed. "
             "Report instead how the researcher's position shaped the coding and how codes and themes developed "
             "(codebook-changes.csv, memos, support.md): see references/approach.md.")


def fail(message: str):
    print(f"qual_ledger: {message}", file=sys.stderr)
    raise SystemExit(2)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def at(base: Path, name: str) -> Path:
    """A path written in a file of the folder: absolute, or relative to the folder, else to the working directory."""
    path = Path(name)
    return path if path.is_absolute() or (not (base / path).exists() and path.exists()) else base / path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        fail(f"cannot read {path} as UTF-8 text: {exc}")


def read_csv(path: Path, required: tuple, optional: bool = False) -> list:
    """The rows as dicts with lower-case column names and stripped cells; [] for a missing optional file."""
    if not path.is_file():
        return [] if optional else fail(f"{path} does not exist: write it first (references/codebook-and-codings.md)")
    reader = csv.DictReader(io.StringIO(read_text(path)))
    names = {name: name.strip().lower() for name in reader.fieldnames or [] if name}
    missing = [column for column in required if column not in names.values()]
    if missing:
        fail(f"{path} lacks the column(s) {', '.join(missing)}; it needs {', '.join(required)}")
    rows = [{names[k]: v.strip() if isinstance(v, str) else "" for k, v in row.items() if k in names} for row in reader]
    return [row for row in rows if any(row.values())]


def read_json(path: Path, optional: bool = False) -> dict:
    if not path.is_file():
        return {} if optional else fail(f"{path} does not exist")
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")
    return data if isinstance(data, dict) else fail(f"{path} must hold a JSON object")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def show(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def read_codings(path: Path) -> list:
    codings = []
    for number, line in enumerate(read_text(path).splitlines() if path.is_file() else [], 1):
        if line.strip():
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(f"{path} line {number} is not valid JSON: {exc}")
            codings.append(item if isinstance(item, dict) else fail(f"{path} line {number} must be a JSON object"))
    return codings


def split(text: str) -> list:
    return [part.strip() for part in re.split("[;；]", text or "") if part.strip()]


def short(text: str, size: int = 70) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= size else text[:size - 1] + "…"


def table(header: tuple, rows: list) -> list:
    cell = lambda value: re.sub(r"\s+", " ", str(value)).replace("|", "/").strip()  # noqa: E731
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)]


def setting(protocol: dict, name: str) -> tuple:
    """(value, how it was set) of a named setting: the protocol's, or the default convention."""
    entry = (protocol.get("settings") or {}).get(name)
    if isinstance(entry, dict) and type(entry.get("value")) in (int, float):
        how = "default convention" if entry.get("default") else entry.get("source") or "no source given"
        return entry["value"], f"{entry['value']} ({how}, set {entry.get('date') or 'undated'})"
    return DEFAULTS[name], f"{DEFAULTS[name]} (default convention, not set in protocol.json)"


# ---------------------------------------------------------------------------------------------
# Text: normalisation, turns, quotes


def norm_map(text: str) -> tuple:
    """(normalised text, starts, ends): NFKC per character with its combining marks, each run of white space
    as one space, none at the ends or between two CJK characters. Normalised character i comes from
    text[starts[i]:ends[i]], so that a match can be reported at the user's offsets."""
    chars, starts, ends, i = [], [], [], 0
    while i < len(text):
        j = i + 1
        while j < len(text) and (text[j].isspace() if text[i].isspace() else unicodedata.combining(text[j])):
            j += 1
        for ch in " " if text[i].isspace() else unicodedata.normalize("NFKC", text[i:j]):
            chars.append(" " if ch.isspace() else ch)
            starts.append(i)
            ends.append(j)
        i = j
    keep = [k for k, ch in enumerate(chars) if ch != " " or (0 < k < len(chars) - 1 and chars[k - 1] != " " and not (
            CJK_CHAR.match(chars[k - 1]) and CJK_CHAR.match(chars[k + 1])))]
    return "".join(chars[k] for k in keep), [starts[k] for k in keep], [ends[k] for k in keep]


def norm(text: str) -> str:
    return norm_map(text)[0]


def parts_of(quote: str) -> list:
    """The parts of a quote between ellipsis marks, normalised."""
    return [part.strip() for part in ELLIPSIS.split(norm(quote)) if part.strip()]


def words(text: str) -> int:
    return len(tokens(text))


def core(text: str) -> str:
    """Normalised text without the punctuation at its ends."""
    return re.sub(r"^\W+|\W+$", "", norm(text))


def in_order(parts: list, text: str) -> bool:
    pos = 0
    for part in parts:
        pos = text.find(part, pos)
        if pos < 0:
            return False
        pos += len(part)
    return bool(parts)


def same(quote: str, passage: str) -> bool:
    """The quote is the passage after normalisation; a quote with ellipsis marks is the passage when its parts
    stand in it in order, the first at its start and the last at its end."""
    text, parts = norm(passage), parts_of(quote)
    return text == norm(quote) or (len(parts) > 1 and text.startswith(parts[0]) and text.endswith(parts[-1])
                                   and in_order(parts, text))


def turns_of(text: str, labels: dict) -> list:
    """[(start, body start, end, speaker id or None)]. A turn opens at a line that begins with a declared label and
    a colon, after an optional time stamp; the text before the first label has no speaker."""
    names = "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
    marks = list(re.finditer(rf"(?m)^[ \t]*(?:[\[(]?\d{{1,2}}:\d{{2}}(?::\d{{2}})?[\])]?[ \t]*)?(?:\*\*)?({names})"
                             rf"(?:\*\*)?[ \t]*[:：](?:\*\*)?[ \t]*", text)) if labels else []
    ends = [m.start() for m in marks[1:]] + [len(text)]
    out = [(0, 0, marks[0].start() if marks else len(text), None)]
    out += [(m.start(), m.end(), end, labels[m.group(1)]) for m, end in zip(marks, ends)]
    return [turn for turn in out if turn[2] > turn[0]]


def speaker_at(src: dict, start: int, end: int) -> tuple:
    """(speaker id or None, whether the span stays inside one turn). Without labels, the one participant speaks."""
    for t0, _, t1, who in src["turns"]:
        if t0 <= start < t1:
            if who is None and not src["labels"] and len(src["participants"]) == 1:
                who = src["participants"][0]
            return who, end <= t1
    return None, False


def units_of(src: dict) -> list:
    """(start, end, speaker) of the units a calibration round draws from: participant turns, or paragraphs in a
    source without speaker labels; white space at either end left out."""
    text = src["text"]
    if src["labels"]:
        spans = [(b, e, who) for _, b, e, who in src["turns"] if who and who != INTERVIEWER]
    else:
        spans = [(m.start(), m.end(), speaker_at(src, m.start(), m.end())[0]) for m in PARAGRAPH.finditer(text)]
    out = []
    for s, e, who in spans:
        s, e = s + len(text[s:e]) - len(text[s:e].lstrip()), e - (len(text[s:e]) - len(text[s:e].rstrip()))
        if e > s:
            out.append((s, e, who))
    return out


def place(quote: str, src: dict) -> list:
    """Every (start, end) where the quote stands verbatim in a source after normalisation; a quote with ellipsis
    marks stands there when its parts follow each other inside one speaker turn."""
    if src["text"] is None:
        return []
    whole, parts, hay = norm(quote), parts_of(quote), src["norm"]
    every = lambda part: [m.start() for m in re.finditer(f"(?={re.escape(part)})", hay)] if part else []  # noqa: E731
    spans = [(p, p + len(whole)) for p in every(whole)]
    if not spans and len(parts) > 1:
        for p in every(parts[0]):
            end = p + len(parts[0])
            for part in parts[1:]:
                end = hay.find(part, end)
                if end < 0:
                    break
                end += len(part)
            else:
                spans.append((p, end))
    spans = [(src["starts"][a], src["ends"][b - 1]) for a, b in spans]
    return [(s, e) for s, e in spans if len(parts) < 2 or speaker_at(src, s, e)[1]]


def pieces(q: str, src: dict) -> list:
    """The normalised quote cut into 2 to 4 verbatim pieces of the source, [(start, end)] in normalised
    positions, or [] when it cannot be cut so. A piece has MIN_PIECE words and a quarter of the quote, unless
    it follows the previous piece within 40 characters (a few words left out)."""
    hay, rest, out = src["norm"], q, []
    least = max(MIN_PIECE, words(q) // 4)
    while rest and len(out) < 4:
        lo, hi = 0, len(rest)
        while lo < hi:                                          # the longest prefix of rest that is in the source
            mid = (lo + hi + 1) // 2
            lo, hi = (mid, hi) if rest[:mid] in hay else (lo, mid - 1)
        prev = out[-1][1] if out else 0
        near = hay.find(rest[:lo], prev, prev + 40 + lo) if out and lo else -1
        if not lo or (words(rest[:lo]) < least and near < 0):
            return []
        start = near if near >= 0 else hay.find(rest[:lo], prev)
        start = start if start >= 0 else hay.find(rest[:lo])
        out.append((start, start + lo))
        rest = re.sub(r"^\W+", "", rest[lo:])
    return out if len(out) > 1 and not rest else []


def closest(q: str, src: dict) -> tuple:
    """The user's offsets of the passage of a source that lines up best with a normalised quote."""
    hay = src["norm"]
    if not hay or not q:
        return 0, 0
    m = SequenceMatcher(None, hay, q, autojunk=False).find_longest_match(0, len(hay), 0, len(q))
    a, b = max(0, m.a - m.b), min(len(hay), m.a - m.b + len(q))
    return src["starts"][a], src["ends"][max(a, b - 1)]


def describe(quote: str, candidates: list) -> tuple:
    """("altered" or "not_found", why) for a quote that is verbatim in none of the candidate sources."""
    candidates, parts = [s for s in candidates if s["text"] is not None], parts_of(quote)
    if len(parts) > 1:
        for part in parts:
            if not any(part in src["norm"] for src in candidates):
                verdict, why = describe(part, candidates)
                return verdict, f"its part «{short(part, 40)}» is {verdict.replace('_', ' ')}: {why}"
        return "altered", "every part is in a transcript, but not in this order inside one speaker turn"
    q, best = (parts or [norm(quote)])[0], None
    for src in candidates:
        cut = pieces(q, src)
        if cut:
            spans = ", ".join(f"{src['starts'][a]}–{src['ends'][b - 1]}" for a, b in cut)
            gaps = [src["norm"][x[1]:y[0]] for x, y in zip(cut, cut[1:])]
            if all(x[1] <= y[0] and len(g) <= 40 for (x, y), g in zip(zip(cut, cut[1:]), gaps)):
                return "altered", f"{src['id']} has «{'», «'.join(gaps)}» inside the quote, left out with no ellipsis ({spans})"
            return "altered", f"joined from {len(cut)} separate passages of {src['id']} with no ellipsis ({spans})"
        grade = match_quality(q, src["text"])
        if best is None or GRADES.index(grade["grade"]) > GRADES.index(best[0]["grade"]):
            best = (grade, src)
    if best is None or best[0]["grade"] == "ABSENT":
        return "not_found", "in no transcript (quote_match ABSENT)"
    grade, src = best
    how = {"EXACT": "differs only in case, quotation marks or emphasis",
           "INTERLEAVED": "has the words in order, with other words or punctuation between them",
           "PARTIAL": f"has {grade['matched']} of its {grade['total']} words in order"}[grade["grade"]]
    start, end = closest(q, src)
    return "altered", f"{src['id']} {how} (quote_match {grade['grade']}; closest passage {start}–{end})"


# ---------------------------------------------------------------------------------------------
# The folder


def load_identifiers(d: Path) -> tuple:
    """([(line number, pattern)] or None without identifiers.txt, [lines too short to search]). Latin entries match
    as whole words, a CJK neighbour counting as a boundary; entries with CJK characters match anywhere."""
    path = d / "identifiers.txt"
    if not path.is_file():
        return None, []
    found, skipped = [], []
    for line_no, line in enumerate(read_text(path).splitlines(), 1):
        value = " ".join(unicodedata.normalize("NFKC", line).split())
        if not value or value.startswith("#"):
            continue
        if len(value) < 2:
            skipped.append(line_no)
            continue
        body = r"\s+".join(re.escape(w) for w in value.split())
        found.append((line_no, re.compile(body if CJK_CHAR.search(value) else rf"(?<![^\W{CJK}]){body}(?![^\W{CJK}])", re.I)))
    return found, skipped


def id_hits(ids, text) -> list:
    text = unicodedata.normalize("NFKC", text or "")
    return [line_no for line_no, pattern in ids or [] if pattern.search(text)]


def mask(ids, text: str) -> str:
    """Text for a report: every identifier replaced by its line number in identifiers.txt; unchanged without one."""
    if not id_hits(ids, text):
        return text
    text = unicodedata.normalize("NFKC", text)
    for line_no, pattern in ids:
        text = pattern.sub(f"[identifier {line_no}]", text)
    return text


def file_text(path: Path):
    """The text of a file searched for identifiers: a text file, or the cells of an .xlsx workbook; None if unreadable."""
    try:
        if path.suffix.lower() == ".xlsx":
            with zipfile.ZipFile(path) as book:
                return html.unescape(" ".join(re.sub(r"<[^>]+>", " ", book.read(n).decode("utf-8", "replace"))
                                              for n in book.namelist() if n.endswith(".xml")))
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile):
        return None


def load_sources(d: Path) -> dict:
    sources = {}
    columns = ("source", "participant", "file", "kind", "deidentified", "speaker_labels")
    for row_no, row in enumerate(read_csv(d / "sources.csv", columns), 2):
        sid, pairs = row["source"], [part.partition("=") for part in split(row["speaker_labels"])]
        if not sid or sid in sources:
            fail(f"sources.csv row {row_no}: every source needs its own id")
        if any(not label.strip() or not who.strip() for label, _, who in pairs):
            fail(f"sources.csv row {row_no}: speaker_labels takes label=id pairs separated by ; (I=interviewer; P3=P3)")
        src = {"id": sid, "row": row, "labels": {label.strip(): who.strip() for label, _, who in pairs},
               "participants": split(row["participant"]), "path": at(d, row["file"]), "text": None, "problem": "",
               "order": len(sources)}
        if not row["file"] or not src["path"].is_file():
            src["problem"] = f"{row['file'] or 'no file'} not found"
        elif src["path"].suffix.lower() in (".docx", ".doc", ".pdf", ".rtf", ".odt"):
            src["problem"] = f"{row['file']} is not plain text: convert it to UTF-8 text and register the copy"
        else:
            try:
                src["text"] = src["path"].read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                src["problem"] = f"{row['file']} is not UTF-8 text"
        if src["text"] is not None:
            src["sha256"] = sha256(src["path"])
            src["norm"], src["starts"], src["ends"] = norm_map(src["text"])
            src["turns"] = turns_of(src["text"], src["labels"])
        sources[sid] = src
    return sources


def everyone(sources: dict) -> set:
    """Every participant id that sources.csv names."""
    return {p for s in sources.values() for p in s["participants"] + list(s["labels"].values()) if p != INTERVIEWER}


def load_codebook(d: Path) -> dict:
    """{"book": {code: row}, "changes", "active": codes in use, "version": the current version, "problems"}."""
    book, problems = {}, []
    for row_no, row in enumerate(read_csv(d / "codebook.csv", ("code", "definition", "version")), 2):
        if not row["code"] or row["code"] in book or not row["version"].isdigit():
            fail(f"codebook.csv row {row_no}: every code needs its own row and a whole-number version")
        book[row["code"]] = dict(row, version=int(row["version"]))
        if not row["definition"]:
            problems.append(f"{row['code']}: no definition")
    changes = read_csv(d / "codebook-changes.csv", ("version", "date", "change", "code", "new_code", "reason", "decided_by"),
                       optional=True)
    for row_no, ch in enumerate(changes, 2):
        if not ch["version"].isdigit() or ch["change"] not in CHANGES or not ch["code"] or (
                ch["change"] in ("renamed", "merged") and not ch["new_code"]):
            fail(f"codebook-changes.csv row {row_no}: needs a whole-number version, a change ({', '.join(CHANGES)}), "
                 "the code, and new_code for renamed or merged")
        ch["version"] = int(ch["version"])
        if not ch["reason"] or not ch["decided_by"]:
            problems.append(f"change on row {row_no} ({ch['change']} {ch['code']}): give the reason and who decided")
        if ch["new_code"] and ch["new_code"] not in book:
            problems.append(f"change on row {row_no}: {ch['new_code']} is not in codebook.csv")
    active = {code for code, row in book.items() if row.get("status", "").lower() != "retired"}
    version = max([row["version"] for row in book.values()] + [ch["version"] for ch in changes] + [1])
    return {"book": book, "changes": changes, "active": active, "version": version, "problems": problems}


def resolve(code: str, version: int, cb: dict) -> tuple:
    """(state, detail) of a code applied under a codebook version: ok; recheck when it was redefined later;
    changed when it was renamed, merged or retired later; unknown when the codebook does not have it."""
    current, notes = code, []
    for ch in sorted((c for c in cb["changes"] if c["version"] > version), key=lambda c: c["version"]):
        if ch["code"] != current:
            continue
        if ch["change"] == "retired":
            return "changed", f"{code}: retired in version {ch['version']}"
        if ch["change"] in ("renamed", "merged"):
            notes.append(f"{ch['change']} {'to' if ch['change'] == 'renamed' else 'into'} {ch['new_code']} in version {ch['version']}")
            current = ch["new_code"]
        elif ch["change"] == "redefined":
            notes.append(f"redefined in version {ch['version']}")
    if current != code:
        return "changed", f"{code}: {'; '.join(notes)}: recode as {current}"
    if code not in cb["active"]:
        return "unknown", f"{code}: {'retired' if code in cb['book'] else 'not in the codebook'}"
    if notes:
        return "recheck", f"{code}: {'; '.join(notes)}: check the coding against version {cb['version']}, then record that version"
    return "ok", ""


def load(d: Path, need_protocol: bool = False) -> dict:
    if not d.is_dir():
        fail(f"no folder {d}: run from the working directory that holds it, or pass --dir")
    ids, skipped = load_identifiers(d)
    return {"dir": d, "protocol": read_json(d / "protocol.json", optional=not need_protocol), "sources": load_sources(d),
            "cb": load_codebook(d), "codings": read_codings(d / "codings.jsonl"), "ids": ids, "ids_skipped": skipped,
            "themes": read_csv(d / "themes.csv", ("theme", "codes", "decided_by"), optional=True)}


# ---------------------------------------------------------------------------------------------
# Checks


def speaker_row(src: dict, start: int, end: int, speaker: str) -> tuple:
    who, one_turn = speaker_at(src, start, end)
    if not one_turn:
        return "speaker", "fail", "the passage runs across speaker turns: quote one turn, or make two codings"
    if who is None:
        return "speaker", "not_checked", "no declared speaker label comes before the passage"
    if who == INTERVIEWER and speaker != INTERVIEWER:
        return "speaker", "fail", f"the passage is in the interviewer's turn, so these are not {speaker}'s words"
    return ("speaker", "fail", f"the turn is {who}'s, but the coding says {speaker}") if who != speaker else ("speaker", "pass", "")


def misplaced(quote: str, src: dict, sources: dict, start, end) -> str:
    """What is wrong with a quote that is not at its offsets."""
    here = place(quote, src)
    if here:
        more = f" (and {len(here) - 1} more places)" if len(here) > 1 else ""
        return f"the words are at {here[0][0]}–{here[0][1]}{more}, not at {start}–{end}"
    for other in sources.values():
        found = place(quote, other) if other is not src else []
        if found:
            who = speaker_at(other, *found[0])[0] or "no declared speaker"
            return f"the words are in {other['id']} ({who}) at {found[0][0]}–{found[0][1]}, not in {src['id']}"
    verdict, why = describe(quote, [src] + [s for s in sources.values() if s is not src])
    return f"{verdict.replace('_', ' ')}: {why}"


def verify(ctx: dict) -> list:
    """For each coding {"id", "rows": [(check, state, detail)], "counted"}: counted when every row passes and the
    words are a participant's."""
    sources, cb = ctx["sources"], ctx["cb"]
    seen, known = Counter(str(c.get("id", "")) for c in ctx["codings"]), everyone(sources) | {INTERVIEWER}
    out = []
    for c in ctx["codings"]:
        cid, src = str(c.get("id") or "?"), sources.get(str(c.get("source", "")))
        speaker, version, start, end = str(c.get("speaker") or ""), c.get("codebook_version"), c.get("start"), c.get("end")
        problems = [f"{key} is missing" for key in CODING_FIELDS if c.get(key) in (None, "")]
        problems += ["the id is used more than once"] if seen[cid] > 1 else []
        problems += [f"source {c['source']!r} is not in sources.csv"] if c.get("source") and not src else []
        problems += [f"speaker {speaker!r} is neither a participant of sources.csv nor {INTERVIEWER}"] if speaker and speaker not in known else []
        if version not in (None, "") and not (type(version) is int and 1 <= version <= cb["version"]):
            problems.append(f"codebook_version must be a whole number from 1 to {cb['version']}")
        rows, quote = [("coding", "fail" if problems else "pass", "; ".join(problems))], str(c.get("quote") or "")
        if not src or src["text"] is None or not quote:
            why = src["problem"] if src and src["text"] is None else "no source or quote to check"
            rows += [("quote", "not_checked", why), ("speaker", "not_checked", why)]
        elif type(start) is int and type(end) is int and 0 <= start < end <= len(src["text"]) and same(quote, src["text"][start:end]):
            rows += [("quote", "pass", ""), speaker_row(src, start, end, speaker)]
        else:
            rows += [("quote", "fail", misplaced(quote, src, sources, start, end)),
                     ("speaker", "not_checked", "the quote is not at its offsets")]
        if c.get("code") in (None, "") or type(version) is not int:
            rows.append(("code", "not_checked", "no code or codebook version"))
        else:
            state, detail = resolve(str(c["code"]), version, cb)
            rows.append(("code", "pass" if state == "ok" else "fail", detail))
        out.append({"id": cid, "rows": rows, "counted": all(r[1] == "pass" for r in rows) and speaker != INTERVIEWER})
    return out


def tally(ctx: dict, results: list) -> dict:
    """Participants, sources and codings per code and per theme, from the counted codings."""
    codes = {}
    for c, r in zip(ctx["codings"], results):
        if r["counted"]:
            entry = codes.setdefault(str(c["code"]), {"participants": set(), "sources": set(), "codings": 0})
            entry["participants"].add(str(c["speaker"]))
            entry["sources"].add(str(c["source"]))
            entry["codings"] += 1
    themes = {}
    for row in ctx["themes"]:
        members = [codes.get(code, {}) for code in split(row["codes"])]
        themes[row["theme"]] = {"codes": split(row["codes"]),
                                "participants": set().union(*(m.get("participants", set()) for m in members)),
                                "sources": set().union(*(m.get("sources", set()) for m in members))}
    return {"codes": codes, "themes": themes, "everyone": everyone(ctx["sources"])}


def quotes_in(text: str) -> list:
    """(start, end, quote, where an attribution may begin) for each quotation of a draft: “…”, 「…」, 『…』, "…", and
    Markdown block quotes without such marks, whose closing attribution is set aside."""
    found = [(m.start(), m.end(), next(g for g in m.groups() if g is not None), m.end()) for m in QUOTED.finditer(text)]
    for m in re.finditer(r"(?m)(?:^[ \t]*>.*(?:\n|$))+", text):
        if not any(m.start() <= s < m.end() for s, *_ in found):
            body = re.sub(r"(?m)^[ \t]*>[ \t]?", "", m.group(0)).strip()
            body = re.sub(r"\s*(?:[—–]+|--|[(（\[])[^()（）\[\]\n]{0,40}[)）\]]?\s*$", "", body)
            found.append((m.start(), m.end(), body, max(m.start(), m.end() - 50)))
    return sorted(found)


def sentence_at(text: str, pos: int) -> str:
    left = max(text.rfind(ch, 0, pos) for ch in "。！？.!?\n") + 1
    rights = [i for i in (text.find(ch, pos) for ch in "。！？.!?\n") if i >= 0]
    return short(text[left:min(rights) + 1 if rights else len(text)], 90)


def check_findings(path: Path, ctx: dict, counts: dict, add, leads: list) -> None:
    """Each quotation of a draft: verbatim in a transcript, a participant's words, said by the participant named
    beside it, in the ledger. General wording ("most", "普遍") is listed with the support of the themes nearby."""
    text, sources = read_text(path), [s for s in ctx["sources"].values() if s["text"] is not None]
    ledger = [norm(str(c.get("quote") or "")) for c in ctx["codings"]]
    names = {core(name) for name in list(ctx["cb"]["book"]) + list(counts["themes"])}
    people = sorted(counts["everyone"], key=len, reverse=True)
    tag = re.compile("(?<![A-Za-z0-9])(" + "|".join(map(re.escape, people)) + ")(?![A-Za-z0-9])") if people else None
    quoted = quotes_in(text)
    for start, end, quote, tail in quoted:
        if words(quote) < MIN_FINDINGS_QUOTE or core(quote) in names:
            continue
        where, said = f"{path.name} line {text.count(chr(10), 0, start) + 1}", f"«{short(quote)}»"
        after = tag.search(text, tail, end + 40) if tag else None
        before = list(tag.finditer(text, max(0, start - 30), start)) if tag else []
        named = after.group(1) if after else before[-1].group(1) if before else ""
        found = [(src, s, e) for src in sources for s, e in place(quote, src)]
        if not found:
            verdict, why = describe(quote, sources)
            add("findings", "fail", where, f"{said} is {verdict.replace('_', ' ')}: {why}")
            continue
        speakers = [speaker_at(src, s, e)[0] for src, s, e in found]
        spot = f"{found[0][0]['id']} {found[0][1]}–{found[0][2]}"
        if all(who == INTERVIEWER for who in speakers):
            add("findings", "fail", where, f"{said} is the interviewer's words ({spot})")
        elif named and named not in speakers:
            who = next((w for w in speakers if w and w != INTERVIEWER), None)
            add("findings", "fail", where, f"{said} is attributed to {named}, but " +
                (f"{who} said it ({spot})" if who else f"its turn has no declared speaker ({spot})"))
        elif not any(in_order([core(part) for part in parts_of(quote)], q) for q in ledger):
            add("findings", "fail", where, f"{said} is in {spot}, but in no coding of the ledger: code the passage first")
        else:
            add("findings", "pass", where, f"{said}: {spot}")
    total, least, listed = len(counts["everyone"]), setting(ctx["protocol"], "min_participants")[0], 0
    for m in PARAGRAPH.finditer(text):
        for g in GENERAL.finditer(m.group(0)):
            if any(s <= m.start() + g.start() < e for s, e, *_ in quoted):
                continue
            themes = [f"{theme}: {len(v['participants'])} of {total} participants" + (" (low support)" if len(v["participants"]) < least else "")
                      for theme, v in counts["themes"].items() if norm(theme) and norm(theme) in norm(m.group(0))]
            if listed < 20:
                leads.append(f"{path.name} line {text.count(chr(10), 0, m.start() + g.start()) + 1}: general wording «{g.group(0)}» in "
                             f"«{sentence_at(m.group(0), g.start())}»; " + ("; ".join(themes) or "no theme is named in this paragraph"))
                listed += 1


def run_checks(ctx: dict, findings: Path | None = None) -> dict:
    """{"rows": [(check, state, where, detail)], "leads", "results", "tally"} for the whole folder."""
    d, sources, cb, ids = ctx["dir"], ctx["sources"], ctx["cb"], ctx["ids"]
    rows, leads = [], []
    add = lambda check, state, where, detail="": rows.append((check, state, where, detail))  # noqa: E731
    approach, problems = ctx["protocol"].get("approach"), []
    if approach not in APPROACHES:
        problems.append(f"approach must be one of {', '.join(APPROACHES)}, recorded before coding")
    if not (d / "approach.md").is_file():
        problems.append("approach.md is missing: write the approach and what it implies")
    for name, entry in (ctx["protocol"].get("settings") or {}).items():
        if name not in DEFAULTS or not isinstance(entry, dict) or type(entry.get("value")) not in (int, float):
            problems.append(f"setting {name}: use a known name ({', '.join(DEFAULTS)}) with a numeric value")
        elif not entry.get("default") and not entry.get("source"):
            problems.append(f"setting {name}: a value the user chose needs its source")
    add("protocol", "fail" if problems else "pass", "protocol.json", "; ".join(problems) or str(approach))
    if approach == "reflexive" and any((d / "calibration").glob("round*-score.json")):
        leads.append("The approach is now reflexive: the calibration scores in calibration/ were made under another approach; "
                     "do not present them as evidence of quality.")
    for src in sources.values():
        row, problems = src["row"], [src["problem"]] if src["problem"] else []
        problems += [] if row["kind"] in KINDS else [f"kind must be one of {', '.join(KINDS)}"]
        named = sorted(set(src["labels"].values()) - {INTERVIEWER})
        if src["labels"] and named != sorted(src["participants"]):
            problems.append(f"speaker_labels name {', '.join(named) or 'no participant'}; the participant column "
                            f"{', '.join(src['participants']) or 'nobody'}")
        recorded = row.get("sha256", "")
        if recorded and src["text"] is not None and recorded != src["sha256"]:
            problems.append("the file changed after its SHA-256 was recorded: locate its codings again")
        add("source", "fail" if problems else "pass" if recorded else "not_checked", src["id"],
            "; ".join(problems) or ("" if recorded else "no SHA-256 recorded (see the sources table)"))
        hits = ", ".join(map(str, id_hits(ids, src["text"])))
        if row["deidentified"].lower() != "yes":
            add("deidentified", "not_checked", src["id"], "not confirmed de-identified by the user"
                + (f"; it contains identifiers.txt line(s) {hits}" if hits else ""))
        else:
            add("deidentified", "fail" if hits else "pass", src["id"], f"marked de-identified, but it contains identifiers.txt "
                f"line(s) {hits}" if hits else "confirmed by the user")
    for problem in cb["problems"]:
        add("codebook", "fail", "codebook", problem)
    if not cb["problems"]:
        add("codebook", "pass", "codebook", f"version {cb['version']}, {len(cb['active'])} codes in use")
    results = verify(ctx)
    for c, r in zip(ctx["codings"], results):
        for check, state, detail in r["rows"]:
            add(check, state, f"{r['id']} ({c.get('source', '?')})", detail)
        if str(c.get("speaker")) == INTERVIEWER and r["rows"][1][1] == "pass":
            leads.append(f"{r['id']} codes the interviewer's words; never quote them as a participant's.")
    counts = tally(ctx, results)
    names = Counter(row["theme"] for row in ctx["themes"])
    for row_no, row in enumerate(ctx["themes"], 2):
        codes, problems = split(row["codes"]), []
        problems += [] if row["theme"] and names[row["theme"]] == 1 else ["every theme needs its own name"]
        problems += [] if codes else ["no codes: a theme rests on codes"]
        problems += [f"includes {resolve(code, 0, cb)[1]}" for code in codes if code not in cb["active"]]
        if codes and not counts["themes"][row["theme"]]["participants"]:
            problems.append("no coding that passes check supports any of its codes")
        if not row["decided_by"]:
            problems.append("decided_by is empty: write who decided the theme")
        elif row["decided_by"].lower() == MODEL:
            leads.append(f"Theme {row['theme']} was suggested by the model and is not yet decided by the researcher.")
        add("theme", "fail" if problems else "pass", row["theme"] or f"themes.csv row {row_no}", "; ".join(problems))
    unused = sorted(cb["active"] - set(counts["codes"]))
    if unused:
        leads.append(f"Codes with no coding that passes check: {', '.join(unused)}.")
    located = {r["id"] for r in results if r["rows"][1][1] == "pass"}
    for row_no, row in enumerate(read_csv(d / "negative-cases.csv", ("theme", "type", "coding", "note"), optional=True), 2):
        problems = [] if row["theme"] in names else [f"theme {row['theme']!r} is not in themes.csv"]
        if row["type"] not in NEGATIVE:
            problems.append(f"type must be one of {', '.join(NEGATIVE)}")
        elif row["type"] == "insufficient_data" and not row["note"]:
            problems.append("say in note which data are missing and where to sample next")
        elif row["type"] != "insufficient_data" and row["coding"] not in located:
            problems.append("name the coding whose passage shows the case; its quote must pass check")
        add("negative_case", "fail" if problems else "pass", f"negative-cases.csv row {row_no}", "; ".join(problems))
    if findings:
        check_findings(findings, ctx, counts, add, leads)
    if ids is None:
        add("identifiers", "not_checked", "identifiers.txt", "no identifiers.txt, so no file was searched for names and places")
    else:
        own = {src["path"].resolve() for src in sources.values()}
        files = [p for p in sorted(d.rglob("*")) if p.is_file() and p.suffix.lower() in SCANNED
                 and p.resolve() not in own and p.name not in ("identifiers.txt", "check.md")]
        files += [findings] if findings and findings.resolve() not in {p.resolve() for p in files} else []
        flagged = 0
        for path in files:
            text = file_text(path)
            hits = id_hits(ids, text)
            if text is None or hits:
                flagged += 1
                add("identifiers", "not_checked" if text is None else "fail", str(path), "could not be read" if text is None
                    else f"contains identifiers.txt line(s) {', '.join(map(str, hits))}")
        if not flagged:
            add("identifiers", "pass", str(d), f"no line of identifiers.txt in the {len(files)} files searched")
        for line_no in ctx["ids_skipped"]:
            add("identifiers", "not_checked", f"identifiers.txt line {line_no}", "one character: too short to search for")
    return {"rows": rows, "leads": leads, "results": results, "tally": counts}


def cmd_check(args) -> int:
    d, findings = Path(args.dir), Path(args.findings) if args.findings else None
    if findings and not findings.is_file():
        fail(f"no such findings draft: {findings}")
    ctx = load(d)
    out = run_checks(ctx, findings)
    rows, hide = out["rows"], lambda text: mask(ctx["ids"], str(text))  # noqa: E731
    states = Counter(state for _, state, _, _ in rows)
    failed = [r for r in rows if r[1] == "fail"]
    groups = Counter((r[0], r[3]) for r in failed)
    repeated = [{"check": check, "detail": hide(detail), "count": n, "where": [r[2] for r in failed if (r[0], r[3]) == (check, detail)]}
                for (check, detail), n in groups.items() if n > 1]
    unreviewed = [str(c.get("id")) for c in ctx["codings"] if str(c.get("coder", "")).lower() == MODEL and not c.get("checked_by")]
    lines = ["# Qualitative check", "",
             f"Approach: {ctx['protocol'].get('approach', 'not recorded')}. Codebook version {ctx['cb']['version']}. "
             f"{len(ctx['sources'])} sources, {len(ctx['codings'])} codings, {len(ctx['themes'])} themes"
             + (f". Findings draft: {findings}." if findings else "."),
             f"Result: {states['fail']} failed, {states['not_checked']} not checked, {states['pass']} passed. "
             "Not checked is never a pass.", ""]
    lines += table(("Check", "pass", "fail", "not checked"), [(check, *(sum(1 for r in rows if r[:2] == (check, s)) for s in
                                                                        ("pass", "fail", "not_checked"))) for check in dict.fromkeys(r[0] for r in rows)])
    lines += ["", f"## Failures ({len(failed)})", ""]
    lines += [f"- {g['count']} × {g['check']}: {g['detail']} ({', '.join(g['where'][:12])}{' …' if g['count'] > 12 else ''})"
              for g in repeated] + ([""] if repeated else [])
    lines += table(("Check", "Where", "Problem"), [(c, w, hide(dt)) for c, _, w, dt in failed]) if failed else ["None."]
    unchecked = [(c, w, hide(dt)) for c, s, w, dt in rows if s == "not_checked"]
    lines += ["", "## Not checked", ""] + (table(("Check", "Where", "Why"), unchecked) if unchecked else ["None."])
    lines += ["", "## Leads and orphans (never failures)", ""] + ([f"- {hide(lead)}" for lead in out["leads"]] or ["None."])
    lines += ["", f"## Model codings no person has checked ({len(unreviewed)})", "", ", ".join(unreviewed) or "None."]
    lines += ["", "## Sources", ""] + table(("Source", "Participant", "File", "SHA-256 now", "De-identified"), [
        (s["id"], ", ".join(s["participants"]), s["row"]["file"], s.get("sha256", s["problem"]), s["row"]["deidentified"] or "not confirmed")
        for s in ctx["sources"].values()])
    (d / "check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    show({"ok": not failed, "counts": {s: states[s] for s in ("pass", "fail", "not_checked")},
          "failures": [{"check": c, "where": w, "detail": hide(dt)} for c, _, w, dt in failed[:60]], "repeated": repeated,
          "not_checked": [f"{c}: {w}: {dt}" for c, w, dt in unchecked[:30]], "leads": [hide(x) for x in out["leads"]],
          "unreviewed_model_codings": len(unreviewed), "report": str(d / "check.md")})
    return 1 if failed else 0


def cmd_support(args) -> int:
    d = Path(args.dir)
    ctx = load(d)
    results = verify(ctx)
    t, (least, how) = tally(ctx, results), setting(ctx["protocol"], "min_participants")
    total, counted = len(t["everyone"]), sum(r["counted"] for r in results)
    themes = {theme: {"participants": len(v["participants"]), "of": total, "low_support": len(v["participants"]) < least}
              for theme, v in t["themes"].items()}
    lines = ["# Support and saturation", "", f"Counted: the {counted} of {len(results)} codings that pass every check, the "
             f"interviewer's words left out. Participants in sources.csv: {total}. Low support: fewer than {least} participants "
             f"(min_participants {how}); it is reported, never dropped.", "", "## Themes", ""]
    lines += table(("Theme", "Codes", "Participants", "Sources", "Flag"), [
        (theme, "; ".join(v["codes"]), f"{len(v['participants'])} of {total}: {', '.join(sorted(v['participants'])) or 'none'}",
         ", ".join(sorted(v["sources"])) or "none", "low support" if themes[theme]["low_support"] else "")
        for theme, v in t["themes"].items()]) if t["themes"] else ["No themes.csv yet."]
    lines += ["", "## Codes", ""] + table(("Code", "Participants", "Sources", "Codings", "Flag"), [
        (code, f"{len(v['participants'])} of {total}: {', '.join(sorted(v['participants']))}", ", ".join(sorted(v["sources"])),
         v["codings"], "low support" if len(v["participants"]) < least else "") for code, v in sorted(t["codes"].items())])
    seen, rows = set(), []
    for src in ctx["sources"].values():
        here = [str(c["code"]) for c, r in zip(ctx["codings"], results) if r["counted"] and str(c["source"]) == src["id"]]
        new = sorted(set(here) - seen)
        seen |= set(here)
        rows.append((src["order"] + 1, src["id"], ", ".join(src["participants"]), len(here), ", ".join(new) or "none", len(seen)))
    lines += ["", "## New codes per source, in the order of sources.csv", ""] + table(
        ("Order", "Source", "Participant", "Codings", "New codes", "Codes so far"), rows)
    lines += ["", "Saturation is the researcher's judgement. This table is its evidence; it does not decide it."]
    reasons = Counter(next((f"{check} {state}" for check, state, _ in r["rows"] if state != "pass"), "interviewer's words")
                      for r in results if not r["counted"])
    if reasons:
        lines += ["", "Not counted: " + "; ".join(f"{n} ({why})" for why, n in reasons.items()) + ". Run check for the details."]
    (d / "support.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    show({"participants": total, "min_participants": how, "themes": themes, "codes": len(t["codes"]), "counted": counted,
          "not_counted": dict(reasons), "new_codes_per_source": {r[1]: r[4] for r in rows}, "report": str(d / "support.md")})
    return 0


# ---------------------------------------------------------------------------------------------
# Calibration


def refused(ctx: dict) -> bool:
    approach = ctx["protocol"].get("approach")
    if approach not in APPROACHES:
        fail(f"protocol.json must record the approach ({', '.join(APPROACHES)}) before a calibration round")
    if approach == "reflexive":
        show({"status": "refused", "approach": approach, "reason": REFLEXIVE})
    return approach == "reflexive"


def rounds(folder: Path) -> list:
    return sorted(int(m.group(1)) for m in (re.fullmatch(r"round(\d+)-sample\.json", p.name)
                                            for p in folder.glob("round*-sample.json")) if m)


def round_files(d: Path, wanted) -> tuple:
    """(number, {kind: path}) of a round; the latest when none is named."""
    folder = d / "calibration"
    found = wanted or (rounds(folder) or [None])[-1]
    if found is None or not (folder / f"round{found}-sample.json").is_file():
        fail("no such calibration round: run sample first")
    return found, {kind: folder / f"round{found}-{kind}" for kind in ("sample.json", "model.csv", "seal.json", "user.csv",
                                                                     "score.json", "score.md")}


def write_round(path: Path, units: list, ctx: dict) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        out = csv.writer(handle)
        out.writerow(("unit", "source", "speaker", "text", "codes", "note"))
        for u in units:
            text = ctx["sources"][u["source"]]["text"][u["start"]:u["end"]]
            out.writerow((u["unit"], u["source"], u["speaker"] or "", mask(ctx["ids"], text), "", ""))


def read_round(path: Path, units: list, cb: dict) -> dict:
    """{unit: set of codes} from a filled round file: every unit has codes of the current codebook, or none."""
    got = {row["unit"]: row["codes"] for row in read_csv(path, ("unit", "codes"))}
    if set(got) != set(units):
        fail(f"{path.name} must hold exactly the {len(units)} units of the round, as written")
    blank = [u for u in units if not got[u]]
    if blank:
        fail(f"{path.name}: write codes separated by ;, or none, for {', '.join(blank[:5])}" + (" and more" if len(blank) > 5 else ""))
    out = {u: set(split(got[u])) - {"none"} for u in units}
    unknown = set().union(*out.values()) - cb["active"]
    if unknown:
        fail(f"{path.name} uses codes that are not in codebook version {cb['version']}: {', '.join(sorted(unknown))}. "
             "Suggest a new code in the note column instead.")
    return out


def cmd_sample(args) -> int:
    d = Path(args.dir)
    ctx = load(d, need_protocol=True)
    if refused(ctx):
        return 1
    folder = d / "calibration"
    taken = {u["unit"] for p in folder.glob("round*-sample.json") for u in read_json(p).get("units", [])}
    by_person = [(str(c.get("source")), c["start"], c["end"]) for c in ctx["codings"] if str(c.get("coder", "")).lower() != MODEL
                 and type(c.get("start")) is int and type(c.get("end")) is int]
    least, pool = setting(ctx["protocol"], "min_unit_words")[0], []
    for src in ctx["sources"].values():
        if src["text"] is None or src["row"]["deidentified"].lower() != "yes":
            continue
        for s, e, who in units_of(src):
            unit, text = f"{src['id']}:{s}-{e}", src["text"][s:e]
            if unit not in taken and words(text) >= least and not any(sid == src["id"] and a < e and s < b for sid, a, b in by_person):
                pool.append({"unit": unit, "source": src["id"], "start": s, "end": e, "speaker": who,
                             "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    size, how = setting(ctx["protocol"], "sample_size")
    size, wanted = min(len(pool), args.size or int(size)), args.round or (rounds(folder) or [0])[-1] + 1
    if not size:
        fail("no unit is left to draw: every participant turn of a confirmed source was drawn before or coded by the user")
    if (folder / f"round{wanted}-sample.json").exists():
        fail(f"round {wanted} exists already: choose another --round")
    order = {sid: src["order"] for sid, src in ctx["sources"].items()}
    picked = sorted(random.Random(args.seed).sample(pool, size), key=lambda u: (order[u["source"]], u["start"]))
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / f"round{wanted}-sample.json", {"round": wanted, "seed": args.seed, "population": len(pool), "size": size,
                                                      "codebook_version": ctx["cb"]["version"], "created": now(), "units": picked})
    write_round(folder / f"round{wanted}-model.csv", picked, ctx)
    show({"round": wanted, "seed": args.seed, "population": len(pool), "size": size,
          "size_setting": "--size" if args.size else how, "model_file": str(folder / f"round{wanted}-model.csv"),
          "next": "fill the codes column of the model's file, then run seal"})
    return 0


def cmd_seal(args) -> int:
    d = Path(args.dir)
    ctx = load(d, need_protocol=True)
    if refused(ctx):
        return 1
    found, f = round_files(d, args.round)
    sample = read_json(f["sample.json"])
    if f["seal.json"].exists():
        fail(f"round {found} is sealed already")
    if f["user.csv"].exists():
        fail(f"{f['user.csv'].name} exists before the seal, so the order of coding cannot be shown: draw a new round")
    if sample.get("codebook_version") != ctx["cb"]["version"]:
        fail(f"the codebook changed after round {found} was drawn: draw a new round")
    read_round(f["model.csv"], [u["unit"] for u in sample["units"]], ctx["cb"])
    write_json(f["seal.json"], {"round": found, "model_file": f["model.csv"].name, "sha256": sha256(f["model.csv"]), "sealed": now()})
    write_round(f["user.csv"], sample["units"], ctx)
    show({"round": found, "seal": str(f["seal.json"]), "user_file": str(f["user.csv"]),
          "next": "the user codes this file; show them none of the model's codes before score has run"})
    return 0


def cmd_score(args) -> int:
    d = Path(args.dir)
    ctx = load(d, need_protocol=True)
    if refused(ctx):
        return 1
    found, f = round_files(d, args.round)
    sample, seal = read_json(f["sample.json"]), read_json(f["seal.json"], optional=True)
    if f["score.json"].exists():
        fail(f"round {found} has been scored, and a scored round is final: draw a new round with a new seed")
    if not seal:
        fail(f"round {found} is not sealed: run seal after the model has coded and before the user codes")
    if sha256(f["model.csv"]) != seal.get("sha256"):
        fail(f"the model's file of round {found} changed after the seal, so the round cannot be scored: draw a new round")
    if sample.get("codebook_version") != ctx["cb"]["version"]:
        fail(f"the codebook changed after round {found} was drawn: draw a new round")
    units = [u["unit"] for u in sample["units"]]
    model, user = read_round(f["model.csv"], units, ctx["cb"]), read_round(f["user.csv"], units, ctx["cb"])
    (kmin, khow), (amin, ahow) = setting(ctx["protocol"], "kappa_min"), setting(ctx["protocol"], "alpha_min")
    per = {}
    for code, k in ra.kappa_by_code(units, model, user, sorted(ctx["cb"]["active"])).items():
        a = ra.krippendorff_alpha_nominal([[code in model[u], code in user[u]] for u in units], args.boot, sample["seed"])
        per[code] = {"status": "not_estimable" if k["kappa"] is None or a["alpha"] is None else
                     "passed" if k["kappa"] >= kmin and a["alpha"] >= amin else "below_threshold", "kappa": k, "alpha": a}
    states = [p["status"] for p in per.values()]
    status = "below_threshold" if "below_threshold" in states else "passed" if "passed" in states else "not_assessable"
    differ = [u for u in sample["units"] if model[u["unit"]] != user[u["unit"]]]
    write_json(f["score.json"], {"round": found, "status": status, "approach": ctx["protocol"]["approach"], "units": units,
                                 "seed": sample["seed"], "thresholds": {"kappa_min": khow, "alpha_min": ahow}, "codes": per,
                                 "disagreements": [{"unit": u["unit"], "model": sorted(model[u["unit"]]),
                                                    "user": sorted(user[u["unit"]])} for u in differ], "scored": now()})
    value = lambda v: "not estimable" if v is None else f"{v:.2f}"  # noqa: E731

    def interval(boot) -> str:
        if not boot or boot["low"] is None:
            return ""
        lost = f"; {boot['not_estimable_draws']} of {boot['n_boot']} resamples not estimable" if boot["not_estimable_draws"] else ""
        return f"{boot['low']:.2f} to {boot['high']:.2f} ({boot['level']:.0%}{lost})"
    lines = [f"# Calibration round {found}", "", f"Status: {status.replace('_', ' ')}. {len(units)} units drawn with seed "
             f"{sample['seed']} from {sample['population']}, codebook version {sample['codebook_version']}. The model's file "
             f"was sealed at {seal['sealed']}, before the user's file was written.",
             f"Thresholds: kappa {khow}; alpha {ahow}. Kappa and alpha are per code, on present or absent.",
             "They measure agreement between the model and this user on these units. They do not show that the model "
             "codes as a person would, and they say nothing about the user's own consistency.", ""]
    lines += table(("Code", "Model", "User", "Both", "Kappa", "Alpha", "Bootstrap interval", "Status"), [
        (code, p["kappa"]["a_present"], p["kappa"]["b_present"], p["kappa"]["both_present"], value(p["kappa"]["kappa"]),
         value(p["alpha"]["alpha"]), interval(p["alpha"]["bootstrap"]), p["status"].replace("_", " ")) for code, p in per.items()])
    lines += ["", "## Not estimable in this round", ""] + ([f"- {code}: {p['kappa']['detail'] or p['alpha']['detail']}"
                                                          for code, p in per.items() if p["status"] == "not_estimable"] or ["None."])
    lines += ["", f"## Disagreements ({len(differ)} unit{'' if len(differ) == 1 else 's'})", ""]
    for u in differ:
        text = ctx["sources"][u["source"]]["text"][u["start"]:u["end"]]
        lines += [f"### {u['unit']} ({u['speaker'] or 'no speaker'})", "", "> " + mask(ctx["ids"], " ".join(text.split())), "",
                  f"Model: {'; '.join(sorted(model[u['unit']])) or 'none'}. User: {'; '.join(sorted(user[u['unit']])) or 'none'}.", ""]
    f["score.md"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    show({"round": found, "status": status, "per_code": {code: p["status"] for code, p in per.items()},
          "disagreements": len(differ), "report": str(f["score.md"])})
    return 0 if status == "passed" else 1


# ---------------------------------------------------------------------------------------------
# Export and locate


def cmd_export(args) -> int:
    d = Path(args.dir)
    ctx = load(d)
    out = run_checks(ctx)
    used = {str(c.get("source")) for c in ctx["codings"]}
    blocking = [r for r in out["rows"] if r[0] in BLOCKING and (r[1] == "fail" or (r[0] == "deidentified" and r[1] != "pass"
                                                                                    and r[2] in used))]
    if blocking:
        show({"exported": False, "blocking": len(blocking), "first": [mask(ctx["ids"], f"{c}: {w}: {dt}") for c, _, w, dt in blocking[:10]],
              "message": "nothing was written: run check and fix these first; every source with codings must be confirmed de-identified"})
        return 1
    themes_of = {}
    for theme, v in out["tally"]["themes"].items():
        for code in v["codes"]:
            themes_of.setdefault(code, []).append(theme)
    header = ("coding", "source", "participant", "code", "themes", "start", "end", "excerpt", "coder", "checked_by",
              "codebook_version", "memo")
    order = {sid: src["order"] for sid, src in ctx["sources"].items()}
    rows = [[c["id"], c["source"], c["speaker"], c["code"], "; ".join(themes_of.get(str(c["code"]), [])), c["start"], c["end"],
             c["quote"], c["coder"], c.get("checked_by", ""), c["codebook_version"], c.get("memo", "")]
            for c in sorted(ctx["codings"], key=lambda c: (order[str(c["source"])], c["start"], str(c["id"])))]
    with open(d / "export.csv", "w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerows([header, *rows])
    try:
        import openpyxl
    except ImportError:
        xlsx = "not written: openpyxl is not installed"
    else:
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "codings"
        for row in [header, *rows]:
            sheet.append(list(row))
            for item in sheet[sheet.max_row]:
                if isinstance(item.value, str) and item.value.startswith("="):
                    item.data_type = "s"                    # a quote that starts with = stays text, never a formula
        book.save(d / "export.xlsx")
        xlsx = str(d / "export.xlsx")
    show({"exported": True, "rows": len(rows), "csv": str(d / "export.csv"), "xlsx": xlsx,
          "unreviewed_model_codings": sum(1 for c in ctx["codings"] if str(c.get("coder", "")).lower() == MODEL and not c.get("checked_by"))})
    return 0


def cmd_locate(args) -> int:
    d = Path(args.dir)
    src = load_sources(d).get(args.source) or fail(f"{args.source} is not a source of {d / 'sources.csv'}")
    if src["text"] is None:
        fail(f"{args.source}: {src['problem']}")
    quote = sys.stdin.read() if args.quote == "-" else args.quote
    found = [dict(zip(("start", "end", "speaker", "one_turn"), (s, e, *speaker_at(src, s, e)))) for s, e in place(quote, src)]
    result = {"source": src["id"], "found": found}
    if not found:
        verdict, why = describe(quote, [src])
        result.update(verdict=verdict, detail=mask(load_identifiers(d)[0], why))
    show(result)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check, count and calibrate the ledger of a qualitative analysis.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="qualitative", help="The analysis folder (default: qualitative)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("locate", parents=[common], help="Offsets and speaker of a passage in one source")
    p.add_argument("source", help="The source id of sources.csv")
    p.add_argument("quote", help="The words, or - to read them from standard input")
    p = sub.add_parser("check", parents=[common], help="Check the folder and write check.md")
    p.add_argument("--findings", help="A findings draft whose quotations are checked as well")
    sub.add_parser("support", parents=[common], help="Participants per code and theme, new codes per source: support.md")
    p = sub.add_parser("sample", parents=[common], help="Draw a calibration round and write the model's file")
    p.add_argument("--seed", type=int, required=True, help="The seed of the draw; record it")
    p.add_argument("--size", type=int, help="Units to draw (default: the sample_size setting)")
    p.add_argument("--round", type=int, help="The round number (default: the next one)")
    p = sub.add_parser("seal", parents=[common], help="Seal the model's filled file, then write the user's file")
    p.add_argument("--round", type=int, help="The round number (default: the latest)")
    p = sub.add_parser("score", parents=[common], help="Score a sealed round, once")
    p.add_argument("--round", type=int, help="The round number (default: the latest)")
    p.add_argument("--boot", type=int, default=1000, help="Bootstrap resamples for alpha's interval (default 1000; 0 for none)")
    sub.add_parser("export", parents=[common], help="Write export.csv, and export.xlsx when openpyxl is installed")
    args = parser.parse_args(argv)
    if getattr(args, "size", None) is not None and args.size < 1 or getattr(args, "boot", 0) < 0:
        fail("--size must be at least 1 and --boot at least 0")
    commands = {"locate": cmd_locate, "check": cmd_check, "support": cmd_support, "sample": cmd_sample, "seal": cmd_seal,
                "score": cmd_score, "export": cmd_export}
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
