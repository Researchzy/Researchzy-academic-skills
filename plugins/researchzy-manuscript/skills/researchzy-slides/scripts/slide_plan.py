#!/usr/bin/env python3
"""Check a slide plan before the deck is built, and the built deck against the plan.

  slide_plan.py check slides/plan.md --paper paper.pdf
  slide_plan.py check slides/plan.md --paper paper.txt --slides-per-minute 1.2 --words-per-minute 150
  slide_plan.py deck slides/deck.tex slides/deck.pdf slides/deck.pptx --plan slides/plan.md

The plan is one Markdown file, the single source of the deck: references/plan-format.md.

check   slides   the title frame and the slides before `# Backup`, against minutes x slides per
                 minute for the talk type: a convention, which --slides-per-minute replaces
        time, speech   the Seconds: of those slides, and the words of their notes at
                 --words-per-minute (default 140, a convention), against the slot
        words, bullets, titles, empty   words and bullets per slide; filing labels ("Results")
                 and titles of one or two words; slides with neither a bullet nor a figure
        figures  every Figure: id is a row of figures/manifest.json and its file is that crop
        numbers  every numeral in titles, bullets and notes, searched in the paper's text: found,
                 NOT_FOUND, or allowed by an Allow: line of its slide. Thousands separators, the
                 minus sign and the space before % are normalised; a numeral that rounds one the
                 paper prints with more decimals is found. Without the paper's text the check is
                 NOT_CHECKED, never passed.
        Writes plan-check.md and plan-check.json beside the plan; prints a summary as JSON.
        Exit code 1: slides, planned time or spoken time exceed the slot by more than the slack
        (25%, 5%, 10%); a figure is missing or is not the recorded crop; a number is NOT_FOUND;
        a line of the plan cannot be read. Words, bullets, titles and empty slides are flags:
        reported, exit code 0.
deck    .tex   frames before and after \\appendix against the plan, graphics that are missing,
               and from the .log beside it: errors, missing files, undefined references,
               overfull boxes (above 5 pt they fail)
        .pdf   the page count (needs PyMuPDF or pdfinfo)
        .pptx  read as a zip: slide count, words per slide, the smallest type and body text under
               20 pt, shapes beyond the slide, text in boxes of zero size, notes, pictures against
               the manifest. Its layout is NOT_RENDERED, always.
        Writes deck-check.md beside the plan. Exit code 1: a count differs from the plan, the
        plan changed after the build, or one of the failures above.
Exit code 2: a file that cannot be read, or a plan without a usable front block.

Standard library only; text from a PDF needs PyMuPDF or pdftotext. Portions are derived from
MIT-licensed code: see LICENSE-MIT.txt next to this file and THIRD_PARTY_NOTICES.md in the plugin.
Portions are derived from Apache-2.0-licensed code: see LICENSE-APACHE-2.0.txt next to this file
and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import sys
import zipfile
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

TOOL = "researchzy-slides"
# Conventions, not rules of any venue: slides per minute, then words on a slide (the median over
# the deck, and the most on one slide).
TALKS = {"conference": (1.0, 40, 60), "seminar": (1.0, 40, 60), "journal-club": (1.0, 50, 70),
         "lightning": (1.5, 25, 40), "lecture": (0.7, 40, 70), "defence": (0.8, 45, 65)}
SLIDE_SLACK = 0.25       # some slides are a divider or a single number
TIME_SLACK = 0.05        # planned seconds over the slot
SPEECH_SLACK = 0.10      # the spoken time is an estimate
UNDER_SLOT = 0.75        # a plan that fills less of the slot than this is flagged
SHORT_NOTES = 0.5        # notes that take less than this share of the planned time to say
WORDS_PER_MINUTE = 140   # prepared speech
MAX_BULLETS = 6
MIN_PAPER_WORDS = 200    # less text than this is a scan or a failed extraction
OVERFULL_PT = 5.0        # an overfull box larger than this shows on a slide
BODY_FLOOR_PT = 20.0     # on a 13.33 x 7.5 inch slide
SMALL_PICTURE = 0.08     # share of the slide under which a picture is hard to read
EDGE_EMU = 9144          # 0.01 inch of tolerance at the slide's edge
FURNITURE = ("Source label", "Slide number")    # shapes build_deck.py sets below the body floor
NOT_RENDERED = "NOT_RENDERED: no office suite drew this file. Open it and look at every slide."
# A title made only of these words files the slide under a heading instead of saying what it shows.
LABEL_WORDS = frozenset(
    "overview introduction background motivation related work method methods methodology approach "
    "materials study design data result results main key experiments evaluation analysis discussion "
    "conclusion conclusions summary takeaways points take-home message limitations strengths future "
    "directions next steps agenda outline contents objectives aims contributions acknowledgements "
    "acknowledgments references questions answers thank you thanks outlook q&a and the of".split())

FRONT_KEYS = ("title", "subtitle", "presenter", "affiliation", "event", "minutes", "talk", "paper",
              "doi", "aspect")
FIELD_RE = re.compile(r"^(figure|source|seconds|notes|allow|kind)\s*:\s*(.*)$", re.I)
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
PAGE_MARK_RE = re.compile(r"^\[\[page (\d+)\]\]\s*$", re.M)
NUM_RE = re.compile(
    r"(?<![\w.])(?P<sign>-)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
    r"(?P<exp>[eE][-+]?\d+)?(?P<pct>\s?(?:%|percent\b|per cent\b))?")


class PlanError(Exception):
    """A plan or a file that cannot be used at all (exit code 2)."""


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def words(text: str) -> int:
    return sum(1 for token in text.split() if re.search(r"\w", token))


def pymupdf():
    try:
        import pymupdf as module
    except ImportError:
        try:
            import fitz as module
        except ImportError:
            return None
    return module


# ---------------------------------------------------------------------------------------------
# The plan


def parse_plan(path) -> dict:
    """The front block and the slides of a plan. Slide 1 is the title frame, built from the
    front block; the `## ` slides follow, and those after `# Backup` are off the clock."""
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise PlanError(f"Cannot read the plan {path}: {exc}")
    start = next((i for i, line in enumerate(lines) if line.strip()), None)
    end = None if start is None else next(
        (i for i in range(start + 1, len(lines)) if lines[i].strip() == "---"), None)
    if start is None or lines[start].strip() != "---" or end is None:
        raise PlanError(f"{path} must start with a front block between two `---` lines "
                        "(references/plan-format.md).")
    front, problems = {}, []
    for i in range(start + 1, end):
        key, sep, value = lines[i].strip().partition(":")
        key, value = key.strip().lower(), value.strip()
        if sep and key in FRONT_KEYS:
            quoted = len(value) > 1 and value[0] == value[-1] and value[0] in "\"'"
            front[key] = value[1:-1] if quoted else value
        elif key or sep:
            problems.append(f"line {i + 1}: the front block takes `key: value` lines with the keys "
                            + ", ".join(FRONT_KEYS))
    try:
        front["minutes"] = float(front.get("minutes", ""))
    except ValueError:
        front["minutes"] = 0
    talk = re.sub(r"[\s_]+", "-", front.get("talk", "").lower())
    front["talk"] = "defence" if talk == "defense" else talk
    if not front.get("title") or front["minutes"] <= 0 or front["talk"] not in TALKS:
        raise PlanError("The front block needs `title:`, `minutes:` (the time you speak, a number "
                        "above 0) and `talk:` (one of " + ", ".join(TALKS) + ").")
    if front.setdefault("aspect", "16:9") not in ("16:9", "4:3"):
        problems.append(f"front block: aspect is 16:9 or 4:3, not {front['aspect']!r}; 16:9 is used")
        front["aspect"] = "16:9"

    def slide(title: str, kind: str = "content") -> dict:
        return {"title": title, "kind": kind, "backup": False, "bullets": [], "figure": None,
                "source": "", "seconds": None, "note_lines": [], "allow": []}

    slides = [slide(front["title"], "title")]
    current, in_notes, backup = slides[0], False, False
    for i in range(end + 1, len(lines)):
        raw, text, where = lines[i].rstrip(), lines[i].strip(), f"line {i + 1}"
        field, bullet = FIELD_RE.match(text), BULLET_RE.match(raw)
        if raw.startswith("## "):
            current, in_notes = slide(text[3:].strip()), False
            current["backup"] = backup
            slides.append(current)
        elif re.match(r"#\s+backup\b", raw, re.I):
            backup, current, in_notes = True, None, False
        elif raw.startswith("#"):
            problems.append(f"{where}: the only headings are `## ` for a slide and `# Backup`")
        elif not text:
            if in_notes:
                current["note_lines"].append("")
        elif current is None:
            problems.append(f"{where}: text after `# Backup` belongs under a `## ` slide heading")
        elif field:
            in_notes = field[1].lower() == "notes"
            set_field(current, field[1].lower(), field[2].strip(), where, problems)
        elif bullet and current["kind"] != "title":
            in_notes = False
            current["bullets"].append(bullet[1].strip())
        elif in_notes and not bullet:
            current["note_lines"].append(text)
        else:
            problems.append(f"{where}: not a bullet under a `## ` heading, a field (Figure:, Source:, "
                            "Seconds:, Notes:, Allow:, Kind:) or part of the notes")
    for n, s in enumerate(slides, 1):
        paragraphs = "\n".join(s.pop("note_lines")).split("\n\n")
        s["notes"] = "\n\n".join(" ".join(p.split()) for p in paragraphs if p.strip())
        s["n"] = n
        if s["source"] and not s["figure"]:
            problems.append(f"slide {n}: Source: without Figure:")
    clock = [s for s in slides[1:] if not s["backup"]]
    if clock and clock[-1]["kind"] == "content" and not any(s["kind"] == "closing" for s in clock):
        clock[-1]["kind"] = "closing"     # by rule: the last slide before `# Backup`
    return {"path": str(path), "sha256": sha256(path), "front": front, "slides": slides,
            "problems": problems}


def set_field(slide: dict, name: str, value: str, where: str, problems: list) -> None:
    clock = re.fullmatch(r"(?:(\d+):)?(\d+)", value)
    text, sep, reason = value.partition("|")
    if slide["kind"] == "title" and name in ("figure", "source", "kind"):
        problems.append(f"{where}: the title frame takes Seconds:, Notes: and Allow: only")
    elif name == "figure" and slide["figure"]:
        problems.append(f"{where}: a slide takes one figure; this is its second Figure: line")
    elif name == "figure" and not re.fullmatch(r"[A-Za-z0-9][\w-]*", value):
        problems.append(f"{where}: Figure: takes an id of figures/manifest.json, not {value!r}")
    elif name in ("figure", "source"):
        slide[name] = value
    elif name == "seconds" and clock:
        slide["seconds"] = int(clock[1] or 0) * 60 + int(clock[2])
    elif name == "seconds":
        problems.append(f"{where}: Seconds: takes seconds (75) or minutes:seconds (1:15)")
    elif name == "notes":
        slide["note_lines"].append(value)
    elif name == "allow" and sep and reason.strip() and find_numerals(normalise(text)):
        slide["allow"].append({"text": text.strip(), "reason": reason.strip()})
    elif name == "allow":
        problems.append(f"{where}: Allow: takes `the number as written | whose number it is`")
    elif value.lower() in ("closing", "section"):
        slide["kind"] = value.lower()
    else:
        problems.append(f"{where}: Kind: is closing or section")


def load_manifest(plan_path) -> dict:
    """figures/manifest.json beside the plan as {id: row}; each row gains the path of its file."""
    folder = Path(plan_path).parent / "figures"
    if not (folder / "manifest.json").is_file():
        return {}
    try:
        rows = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["figures"]
        return {row["id"]: {**row, "path": folder / row["file"]} for row in rows}
    except (ValueError, KeyError, TypeError) as exc:
        raise PlanError(f"{folder / 'manifest.json'} is not a figure manifest: {exc!r}")


def title_problem(title: str) -> str:
    tokens = re.sub(r"[^\w&' -]", " ", title.lower()).split()
    if tokens and all(token in LABEL_WORDS for token in tokens):
        return "is a filing label: say what the slide shows"
    return f"has {words(title)} word(s): too short to be a claim" if words(title) <= 2 else ""


# ---------------------------------------------------------------------------------------------
# Numbers


def normalise(text: str) -> str:
    """One minus sign, no separators inside a number, plain spaces."""
    text = re.sub(r"(?<=\d)[\u00a0\u2009\u202f](?=\d{3}(?!\d))", "", text.replace("\u2212", "-"))
    return re.sub(r"[\u00a0\u2009\u202f]", " ", text)


def find_numerals(text: str) -> list:
    """The numerals of a normalised text. A digit glued to a letter before it (p53) is a name."""
    out = []
    for m in NUM_RE.finditer(text):
        try:
            value = Decimal(m["num"].replace(",", "") + (m["exp"] or ""))
        except InvalidOperation:
            continue
        suffix = "" if m["pct"] else (re.match(r"[^\W\d_]{1,3}\b", text[m.end():]) or [""])[0]
        out.append({"written": " ".join(m[0].split()) + suffix, "value": abs(value),
                    "decimals": max(0, -value.as_tuple().exponent), "percent": bool(m["pct"]),
                    "negative": bool(m["sign"]), "start": m.start(), "end": m.end()})
    return out


def snippet(text: str, start: int, end: int, pad: int = 30) -> str:
    left, right = max(0, start - pad), min(len(text), end + pad)
    return ("…" if left else "") + " ".join(text[left:right].split()) + ("…" if right < len(text) else "")


def read_paper(path: Path):
    """([(page number or None, text)], "") or (None, why the paper's text could not be had)."""
    if not path.is_file():
        return None, f"paper not found: {path}"
    if path.suffix.lower() == ".pdf":
        fitz = pymupdf()
        try:
            if fitz:
                with fitz.open(path) as doc:
                    texts = [page.get_text() for page in doc]
            elif shutil.which("pdftotext"):
                texts = subprocess.run(["pdftotext", "-q", str(path), "-"], capture_output=True,
                                       text=True, check=True).stdout.split("\f")
            else:
                return None, ("reading a PDF needs PyMuPDF or pdftotext: install one, or give the "
                              "paper's text with --paper paper.txt")
        except Exception as exc:    # a damaged or encrypted file: say so, do not crash
            return None, f"cannot read {path}: {exc}"
        pages = list(enumerate(texts, 1))
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        marks = list(PAGE_MARK_RE.finditer(text))
        ends = [m.start() for m in marks[1:]] + [len(text)]
        parts = text.split("\f")
        pages = ([(int(m[1]), text[m.end():stop]) for m, stop in zip(marks, ends)] if marks
                 else list(enumerate(parts, 1)) if len(parts) > 1 else [(None, text)])
    if sum(words(text) for _, text in pages) < MIN_PAPER_WORDS:
        return None, f"{path} has almost no text (a scan?): numbers cannot be searched in it"
    return pages, ""


def match_number(tok: dict, index: dict, tokens: list):
    """(how, the paper's numeral, whether the percent sign agrees), or None when it is not there.
    An unsigned numeral matches either sign; a negative one needs the paper's to be negative."""
    unit = Decimal(1).scaleb(-tok["decimals"])
    hits = [("exact", p) for p in index.get(tok["value"], [])]
    for p in tokens:
        if p["decimals"] > tok["decimals"]:
            try:
                rounded = (p["value"].quantize(unit, ROUND_HALF_UP), p["value"].quantize(unit, ROUND_HALF_EVEN))
            except InvalidOperation:
                continue
            if tok["value"] in rounded:
                hits.append(("rounded", p))
    hits = [(how, p) for how, p in hits if p["negative"] or not tok["negative"]]
    agreeing = [(how, p) for how, p in hits if p["percent"] or not tok["percent"]]
    return (*agreeing[0], True) if agreeing else (*hits[0], False) if hits else None


def check_numbers(slides: list, pages) -> tuple:
    """One row per numeral of the plan, and the Allow: numbers that no slide text uses."""
    tokens, index = None, {}
    for page, text in pages or []:
        text = normalise(text)
        for tok in find_numerals(text):
            tok.update(page=page, context=snippet(text, tok["start"], tok["end"]))
            index.setdefault(tok["value"], []).append(tok)
    if pages is not None:
        tokens = [tok for group in index.values() for tok in group]
    rows, unused = [], []
    for s in slides:
        allowed = {tok["value"]: entry["reason"] for entry in s["allow"]
                   for tok in find_numerals(normalise(entry["text"]))}
        used = set()
        for where, text in [("title", s["title"]), *[("bullet", b) for b in s["bullets"]], ("notes", s["notes"])]:
            text = normalise(text)
            for tok in find_numerals(text):
                row = {"slide": s["n"], "in": where, "number": tok["written"],
                       "context": snippet(text, tok["start"], tok["end"])}
                hit = None if tokens is None else match_number(tok, index, tokens)
                if tok["value"] in allowed:
                    row.update(result="allowed", reason=allowed[tok["value"]])
                    used.add(tok["value"])
                elif hit:
                    row.update(result="found", how=hit[0], percent_sign=hit[2], page=hit[1]["page"],
                               paper_number=hit[1]["written"], paper=hit[1]["context"])
                else:
                    row["result"] = "NOT_CHECKED" if tokens is None else "NOT_FOUND"
                rows.append(row)
        unused += [(s["n"], f"{value:f}") for value in allowed if value not in used]
    return rows, unused


# ---------------------------------------------------------------------------------------------
# check


def check_plan(plan: dict, paper, per_minute=None, wpm: float = WORDS_PER_MINUTE) -> dict:
    front, slides = plan["front"], plan["slides"]
    minutes, (rate, median_limit, max_limit) = front["minutes"], TALKS[front["talk"]]
    clock = [s for s in slides if not s["backup"]]
    found = {"errors": [], "not_checked": [], "flags": []}
    detail = {"bullets": f"at most {MAX_BULLETS} a slide (a convention)",
              "titles": "no filing label, no title of one or two words",
              "empty": "every slide has a bullet or a figure"}

    def add(level: str, check: str, message: str, slide=None) -> None:
        found[level].append({"check": check, "slide": slide, "message": message})

    for problem in plan["problems"]:
        add("errors", "format", problem)

    basis = "--slides-per-minute" if per_minute else f"a convention for a {front['talk']} talk"
    per_minute = per_minute or rate
    budget = max(1, round(minutes * per_minute))
    detail["slides"] = (f"{len(clock)} on the clock, {len(slides) - len(clock)} backup; budget {budget} at "
                        f"{per_minute:g} a minute ({basis}), slack {SLIDE_SLACK:.0%}")
    if len(clock) > budget * (1 + SLIDE_SLACK):
        add("errors", "slides", detail["slides"] + ". Cut slides or move them behind `# Backup`.")

    slot = minutes * 60
    planned = sum(s["seconds"] or 0 for s in clock)
    unplanned = ", ".join(str(s["n"]) for s in clock if s["seconds"] is None)
    detail["time"] = f"{planned} s planned, slot {slot:g} s, slack {TIME_SLACK:.0%}"
    if planned > slot * (1 + TIME_SLACK):
        add("errors", "time", detail["time"] + ". Cut content; do not plan to talk faster.")
    elif unplanned:
        add("not_checked", "time", f"no Seconds: on slide(s) {unplanned}: the {planned} s planned so "
            "far are not the whole talk.")
    elif planned < slot * UNDER_SLOT:
        add("flags", "time", f"{planned} s planned fill {planned / slot:.0%} of the {slot:g} s slot.")

    note_words = sum(words(s["notes"]) for s in clock)
    silent = ", ".join(str(s["n"]) for s in clock if not s["notes"] and s["kind"] != "section")
    detail["speech"] = (f"{note_words} words of notes = {note_words / wpm:.1f} min at {wpm:g} words a minute "
                        f"(a convention), slot {minutes:g} min, slack {SPEECH_SLACK:.0%}")
    if note_words / wpm > minutes * (1 + SPEECH_SLACK):
        add("errors", "speech", detail["speech"] + ". Shorten the notes or cut a slide.")
    elif silent:
        add("not_checked", "speech", f"no Notes: on slide(s) {silent}: the spoken time counts the "
            "other slides only.")
    elif planned and note_words / wpm * 60 < planned * SHORT_NOTES:
        add("flags", "speech", f"the notes take {note_words / wpm:.1f} minutes to say and {planned / 60:.1f} "
            "are planned: write what you will say on each slide, or plan less time.")

    count = {s["n"]: words(s["title"]) + sum(words(b) for b in s["bullets"]) for s in slides[1:]}
    ranked = sorted(count[s["n"]] for s in clock[1:] if s["kind"] != "section")
    median = ranked[len(ranked) // 2] if ranked else 0
    detail["words"] = (f"most {max(count.values(), default=0)} (allowed {max_limit}), median {median} "
                       f"(working figure {median_limit}); conventions for a {front['talk']} talk")
    if median > median_limit:
        add("flags", "words", f"the median slide has {median} words (working figure {median_limit}). "
            "Move explanation into the notes.")
    for s in slides[1:]:
        n = s["n"]
        if count[n] > max_limit:
            add("flags", "words", f"{count[n]} words (most allowed: {max_limit}). Split the slide or "
                "move text into the notes.", n)
        if len(s["bullets"]) > MAX_BULLETS:
            add("flags", "bullets", f"{len(s['bullets'])} bullets (most allowed: {MAX_BULLETS}).", n)
        if not s["backup"] and s["kind"] == "content" and title_problem(s["title"]):
            add("flags", "titles", f"the title \"{s['title']}\" {title_problem(s['title'])}.", n)
        if not s["bullets"] and not s["figure"] and s["kind"] != "section":
            add("flags", "empty", "neither a bullet nor a figure.", n)

    manifest = load_manifest(plan["path"])
    detail["figures"] = f"{sum(1 for s in slides if s['figure'])} slide(s) with a figure, {len(manifest)} row(s) in the manifest"
    for s in slides:
        row = manifest.get(s["figure"])
        if not s["figure"]:
            continue
        if row is None:
            add("errors", "figures", f"figure `{s['figure']}` is not in figures/manifest.json: crop "
                "it with paper_figure.py.", s["n"])
        elif not row["path"].is_file():
            add("errors", "figures", f"the file of figure `{s['figure']}` is missing: {row['path']}", s["n"])
        elif sha256(row["path"]) != row.get("sha256"):
            add("errors", "figures", f"{row['path']} is not the crop the manifest records: it was "
                "changed after paper_figure.py wrote it.", s["n"])
        elif not (s["source"] or row.get("label")):
            add("flags", "figures", f"figure `{s['figure']}` has no source label: add a Source: line.", s["n"])

    pages, why = (None, "no paper given: pass --paper, or name the file in the front block")
    if paper is not None:
        pages, why = read_paper(Path(paper))
    rows, unused = check_numbers(slides, pages)
    tally = {key: sum(1 for r in rows if r["result"] == key) for key in ("found", "NOT_FOUND", "allowed", "NOT_CHECKED")}
    tally["found_by_rounding"] = sum(1 for r in rows if r.get("how") == "rounded")
    tally["found_without_percent_sign"] = sum(1 for r in rows if r.get("percent_sign") is False)
    detail["numbers"] = (f"{tally['found']} found ({tally['found_by_rounding']} by rounding, "
                         f"{tally['found_without_percent_sign']} without the percent sign), {tally['NOT_FOUND']} "
                         f"NOT_FOUND, {tally['allowed']} allowed, {tally['NOT_CHECKED']} NOT_CHECKED")
    if pages is None:
        add("not_checked", "numbers", f"{why}. The {tally['NOT_CHECKED']} numeral(s) of the plan were "
            "not compared with the paper.")
    for r in rows:
        if r["result"] == "NOT_FOUND":
            add("errors", "numbers", f"`{r['number']}` ({r['in']}: \"{r['context']}\") is not in the "
                "paper's text. Correct it, or mark it as your own with an Allow: line.", r["slide"])
    for n, value in unused:
        add("flags", "numbers", f"Allow: names {value}, which is not on the slide or in its notes.", n)

    status = {"errors": "FAIL", "not_checked": "NOT_CHECKED", "flags": "FLAG", None: "PASS"}
    checks = {name: {"status": status[next((level for level in found if any(
        item["check"] == name for item in found[level])), None)], "detail": text}
        for name, text in detail.items()}
    checks["numbers"].update(tally, paper=None if paper is None else str(paper))
    table = [{"n": s["n"], "kind": "backup" if s["backup"] else s["kind"], "title": s["title"],
              "words": count.get(s["n"], 0), "bullets": len(s["bullets"]), "seconds": s["seconds"],
              "note_words": words(s["notes"]), "figure": s["figure"]} for s in slides]
    return {"tool": TOOL, "plan": plan["path"], "plan_sha256": plan["sha256"], "talk": front["talk"],
            "minutes": minutes, "ok": not found["errors"], **found, "checks": checks, "slides": table,
            "numbers": rows}


def cell(value) -> str:
    return re.sub(r"\s+", " ", str("" if value is None else value)).replace("|", "/")


def write_plan_report(path: Path, r: dict) -> None:
    order = ("slides", "time", "speech", "words", "bullets", "titles", "empty", "figures", "numbers")
    lines = ["# Plan check", "", f"Plan `{r['plan']}`: a {r['talk']} talk of {r['minutes']:g} minutes. "
             f"Paper text: `{r['checks']['numbers']['paper'] or 'none'}`.", "",
             f"**{len(r['errors'])} error(s), {len(r['flags'])} flag(s), {len(r['not_checked'])} not checked.** "
             "Errors must be fixed. Flags are fixed or explained to the user. Not checked is not passed.",
             "", "| Check | Status | Detail |", "|---|---|---|"]
    lines += [f"| {name} | {r['checks'][name]['status']} | {r['checks'][name]['detail']} |" for name in order]
    for heading, level in (("Errors", "errors"), ("Flags", "flags"), ("Not checked", "not_checked")):
        if r[level]:
            lines += ["", f"## {heading}", ""] + [
                f"- {'slide ' + str(i['slide']) + ', ' if i['slide'] else ''}{i['check']}: {i['message']}"
                for i in r[level]]
    lines += ["", "## Slides", "", "| # | Kind | Title | Words | Bullets | Seconds | Note words | Figure |",
              "|---|---|---|---|---|---|---|---|"]
    lines += ["| " + " | ".join(cell(v) for v in s.values()) + " |" for s in r["slides"]]
    if r["numbers"]:
        lines += ["", "## Numbers", "", "A number that is found occurs in the paper's text; whether it means "
                  "the same thing there is for you to read. Look first at the rows found by rounding or "
                  "without the percent sign.", "", "| Slide | In | Number | Result | In the paper |",
                  "|---|---|---|---|---|"]
    for n in sorted(r["numbers"], key=lambda n: (n["result"] != "NOT_FOUND", n.get("how") != "rounded",
                                                 n.get("percent_sign", True), n["slide"])):
        result, where = n["result"], n.get("reason", "")
        if result == "found":
            result += f", rounded from {n['paper_number']}" if n["how"] == "rounded" else ""
            result += "" if n["percent_sign"] else ", no percent sign in the paper"
            where = (f"p. {n['page']}: " if n["page"] else "") + f"\"{n['paper']}\""
        lines.append(f"| {n['slide']} | {n['in']} | `{cell(n['number'])}` in \"{cell(n['context'])}\" "
                     f"| {result} | {cell(where)} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_check(args) -> int:
    plan = parse_plan(args.plan)
    folder = Path(plan["path"]).parent
    paper = Path(args.paper) if args.paper else None
    if paper is None and plan["front"].get("paper"):      # relative to here, or to the plan
        named = Path(plan["front"]["paper"])
        paper = next((p for p in (named, folder / named, folder.parent / named) if p.is_file()), named)
    result = check_plan(plan, paper, args.slides_per_minute, args.words_per_minute)
    result["report"] = str(folder / "plan-check.md")
    (folder / "plan-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_plan_report(folder / "plan-check.md", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("slides", "numbers")},
                     indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------------------------------------
# deck

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


def relations(z: zipfile.ZipFile, part: str) -> dict:
    """{relationship id: (type, target part)} of a part of the package."""
    folder, base = posixpath.split(part)
    name, out = posixpath.join(folder, "_rels", base + ".rels"), {}
    if name in z.namelist():
        for rel in ET.fromstring(z.read(name)).iter(REL):
            target = rel.get("Target", "")
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
            out[rel.get("Id")] = (rel.get("Type", ""), target)
    return out


def shapes_of(node, transform: tuple, rels: dict, z: zipfile.ZipFile, out: list) -> None:
    """The shapes under a shape tree, with their boxes in slide coordinates. A group maps its
    children's coordinates by scale and offset; rotation is not followed."""
    sx, sy, dx, dy = transform
    for child in node:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "grpSp":
            x, inner = child.find(f"{P}grpSpPr/{A}xfrm"), transform
            parts = [x.find(A + k) for k in ("off", "ext", "chOff", "chExt")] if x is not None else [None]
            if all(p is not None for p in parts):
                off, ext, choff, chext = parts
                gx = int(ext.get("cx", 0)) / (int(chext.get("cx", 0)) or 1)
                gy = int(ext.get("cy", 0)) / (int(chext.get("cy", 0)) or 1)
                inner = (sx * gx, sy * gy, dx + sx * (int(off.get("x", 0)) - gx * int(choff.get("x", 0))),
                         dy + sy * (int(off.get("y", 0)) - gy * int(choff.get("y", 0))))
            shapes_of(child, inner, rels, z, out)
        elif tag in ("sp", "pic", "graphicFrame"):
            x = child.find(f"{P}xfrm") if tag == "graphicFrame" else child.find(f"{P}spPr/{A}xfrm")
            off, ext = (x.find(f"{A}off"), x.find(f"{A}ext")) if x is not None else (None, None)
            box = None
            if off is not None and ext is not None:
                box = (dx + sx * int(off.get("x", 0)), dy + sy * int(off.get("y", 0)),
                       sx * int(ext.get("cx", 0)), sy * int(ext.get("cy", 0)))
            name, blip = child.find(f".//{P}cNvPr"), child.find(f".//{A}blip")
            media = rels.get(blip.get(f"{R}embed"), ("", ""))[1] if blip is not None else ""
            out.append({
                "kind": tag, "name": name.get("name", "") if name is not None else "", "box": box,
                "text": "\n".join("".join(t.text or "" for t in p.iter(f"{A}t")) for p in child.iter(f"{A}p")).strip(),
                "sizes": [int(r.get("sz")) / 100 for r in child.iter(f"{A}rPr") if r.get("sz")],
                "sha256": hashlib.sha256(z.read(media)).hexdigest() if media in z.namelist() else None})


def read_pptx(path: Path) -> tuple:
    """(slides in the order they are shown, slide width, slide height), sizes in EMU. The order
    is the slide list of presentation.xml, not the numbers in the part names."""
    with zipfile.ZipFile(path) as z:
        pres = ET.fromstring(z.read("ppt/presentation.xml"))
        size, listed = pres.find(f"{P}sldSz"), pres.find(f"{P}sldIdLst")
        width, height = (int(size.get("cx")), int(size.get("cy"))) if size is not None else (12192000, 6858000)
        pres_rels, slides = relations(z, "ppt/presentation.xml"), []
        for sid in (listed if listed is not None else []):
            part = pres_rels[sid.get(f"{R}id")][1]
            rels, shapes, notes = relations(z, part), [], ""
            tree = ET.fromstring(z.read(part)).find(f"{P}cSld/{P}spTree")
            shapes_of(tree if tree is not None else [], (1, 1, 0, 0), rels, z, shapes)
            for kind, target in rels.values():
                if kind.endswith("/notesSlide") and target in z.namelist():
                    for sp in ET.fromstring(z.read(target)).iter(f"{P}sp"):
                        ph = sp.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
                        if ph is not None and ph.get("type") == "body":
                            notes += "".join(t.text or "" for t in sp.iter(f"{A}t"))
            slides.append({"shapes": shapes, "notes": notes.strip()})
    return slides, width, height


def check_pptx(path: Path, plan: dict, manifest: dict, errors: list, flags: list) -> dict:
    try:
        slides, width, height = read_pptx(path)
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError) as exc:
        raise PlanError(f"{path} is not a readable .pptx: {exc!r}")
    expected, known = len(plan["slides"]), {row.get("sha256") for row in manifest.values()}
    if len(slides) != expected:
        errors.append(f"{path.name}: {len(slides)} slides, the plan has {expected}")
    counts, sizes, pictures = [], [], [0, 0]
    for n, slide in enumerate(slides, 1):
        body = [s for s in slide["shapes"] if s["text"] and not s["name"].startswith(FURNITURE)]
        counts.append(sum(words(s["text"]) for s in body))
        for s in slide["shapes"]:
            sizes += s["sizes"]
            label = f"{path.name} slide {n}: {s['name'] or s['kind']}"
            left, top, w, h = s["box"] or (0, 0, 1, 1)
            if s["text"] and (w == 0 or h == 0):
                errors.append(f"{label} holds text in a box of zero size: the text is not on the slide")
            elif left < -EDGE_EMU or top < -EDGE_EMU or left + w > width + EDGE_EMU or top + h > height + EDGE_EMU:
                errors.append(f"{label} extends beyond the slide")
            if s["kind"] == "pic":
                pictures[0] += 1
                pictures[1] += s["sha256"] not in known
                if s["sha256"] not in known:
                    flags.append(f"{label} is not a figure of figures/manifest.json")
                if s["box"] and w * h < SMALL_PICTURE * width * height:
                    flags.append(f"{label} covers {w * h / (width * height):.0%} of the slide: hard to read")
            if s in body and s["sizes"] and min(s["sizes"]) < BODY_FLOOR_PT:
                flags.append(f"{label} has text at {min(s['sizes']):g} pt, under the {BODY_FLOOR_PT:g} pt floor")
        if n <= expected and plan["slides"][n - 1]["notes"] and not slide["notes"]:
            flags.append(f"{path.name} slide {n} has no notes; the plan has notes for it")
    ranked = sorted(counts)
    return {"slides": len(slides), "expected": expected, "words_most": max(counts, default=0),
            "words_median": ranked[len(ranked) // 2] if ranked else 0,
            "smallest_pt": min(sizes) if sizes else None,
            "slides_with_notes": sum(1 for s in slides if s["notes"]), "pictures": pictures[0],
            "pictures_not_in_manifest": pictures[1], "layout": NOT_RENDERED}


def read_log(path: Path) -> dict:
    """What a LaTeX log says went wrong. TeX breaks log lines at 79 characters: join them first."""
    raw, lines, i = path.read_text(encoding="utf-8", errors="replace").splitlines(), [], 0
    while i < len(raw):
        line = raw[i]
        while len(raw[i]) == 79 and i + 1 < len(raw):
            i += 1
            line += raw[i]
        lines.append(line)
        i += 1
    log = {"errors": [], "missing_files": [], "undefined": [], "overfull": [], "missing_characters": 0,
           "rerun_needed": False, "pages": None}
    for n, line in enumerate(lines):
        missing = re.search(r"File `([^']+)' not found", line)
        undefined = re.search(r"(Reference|Citation) `([^']+)' .*undefined", line)
        box = re.search(r"Overfull \\([hv])box \(([\d.]+)pt too (?:wide|high)\)(.*)", line)
        pages = re.search(r"Output written on .*\((\d+) pages?", line)
        if missing:
            log["missing_files"] += [missing[1]] if missing[1] not in log["missing_files"] else []
        elif line.startswith("!") or re.match(r"\S*\.tex:\d+: ", line):     # -file-line-error form
            at = re.match(r"\S*\.tex:(\d+): ", line) or next(
                (m for m in (re.match(r"l\.(\d+)", later) for later in lines[n + 1:n + 12]) if m), None)
            message = re.sub(r"^(!|\S*\.tex:\d+:)\s*", "", line)
            log["errors"].append({"message": message, "line": int(at[1]) if at else None})
        elif undefined:
            entry = f"{undefined[1].lower()} {undefined[2]}"
            log["undefined"] += [entry] if entry not in log["undefined"] else []
        elif box:
            at = re.search(r"lines? (\d+)", box[3])
            log["overfull"].append({"box": box[1] + "box", "pt": float(box[2]), "line": int(at[1]) if at else None})
        elif pages:
            log["pages"] = int(pages[1])
        log["missing_characters"] += line.startswith("Missing character:")
        log["rerun_needed"] = log["rerun_needed"] or "Rerun to get" in line or "Rerun LaTeX" in line
    return log


def log_is_current(tex: Path, log: Path) -> bool:
    """latexmk records the MD5 of the source it compiled, and skips a run when nothing changed, so
    its log can be older than an unchanged .tex. Without latexmk's record, compare times."""
    fdb = tex.with_suffix(".fdb_latexmk")
    if fdb.is_file():
        found = re.search(rf'^\s*"{re.escape(tex.name)}" \S+ \d+ ([0-9a-f]{{32}})', fdb.read_text(errors="replace"), re.M)
        if found:
            return found[1] == hashlib.md5(tex.read_bytes()).hexdigest()
    return log.stat().st_mtime >= tex.stat().st_mtime


def check_tex(path: Path, plan: dict, errors: list, not_checked: list) -> dict:
    frames, graphics, appendix = [], [], False        # a frame: [first line, last line, backup]
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = line.strip()
        if line.startswith("%"):
            continue
        appendix = appendix or bool(re.match(r"\\appendix\b", line))
        if line.startswith(r"\begin{frame}"):
            frames.append([i, i, appendix])
        if r"\end{frame}" in line and frames:
            frames[-1][1] = i
        graphics += re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", line)
    backup = sum(1 for f in frames if f[2])
    want_backup = sum(1 for s in plan["slides"] if s["backup"])
    if (len(frames) - backup, backup) != (len(plan["slides"]) - want_backup, want_backup):
        errors.append(f"{path.name}: {len(frames) - backup} frames and {backup} backup frames; the plan "
                      f"has {len(plan['slides']) - want_backup} and {want_backup}")
    errors += [f"{path.name}: \\includegraphics of a missing file: {name}"
               for name in graphics if not (path.parent / name).is_file()]
    out = {"frames": len(frames) - backup, "backup_frames": backup, "graphics": len(graphics), "log": "NOT_CHECKED"}
    log_path = path.with_suffix(".log")
    if not log_path.is_file():
        not_checked.append(f"{path.name}: no {log_path.name} beside it: compile the deck, then run this again")
    elif not log_is_current(path, log_path):
        not_checked.append(f"{path.name}: {log_path.name} is from an earlier version of the .tex: compile again")
    else:
        log = read_log(log_path)

        def where(line) -> str:
            n = next((k for k, f in enumerate(frames, 1) if line and f[0] <= line <= f[1]), None)
            return f" (slide {n}, line {line})" if n else f" (line {line})" if line else ""

        errors += [f"{log_path.name}: {e['message']}{where(e['line'])}" for e in log["errors"][:10]]
        errors += [f"{log_path.name}: file not found: {name}" for name in log["missing_files"]]
        errors += [f"{log_path.name}: undefined {entry}" for entry in log["undefined"]]
        large = [b for b in log["overfull"] if b["pt"] > OVERFULL_PT]
        errors += [f"{log_path.name}: overfull {b['box']}, {b['pt']:g} pt{where(b['line'])}: content runs "
                   "past the frame; shorten the slide in the plan" for b in large]
        if log["missing_characters"]:
            errors.append(f"{log_path.name}: {log['missing_characters']} character(s) the font lacks were dropped")
        if log["rerun_needed"]:
            not_checked.append(f"{log_path.name} asks for another run: compile again with latexmk")
        out.update(log="read", pages_in_log=log["pages"], overfull_boxes=len(log["overfull"]),
                   overfull_above_limit=len(large))
    return out


def check_pdf(path: Path, plan: dict, errors: list, not_checked: list) -> dict:
    fitz, pages = pymupdf(), None
    try:
        if fitz:
            with fitz.open(path) as doc:
                pages = doc.page_count
        elif shutil.which("pdfinfo"):
            found = re.search(r"^Pages:\s+(\d+)", subprocess.run(
                ["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout, re.M)
            pages = int(found[1]) if found else None
        else:
            not_checked.append(f"{path.name}: counting pages needs PyMuPDF or pdfinfo")
    except Exception as exc:
        raise PlanError(f"cannot read {path}: {exc}")
    if pages is not None and pages != len(plan["slides"]):
        errors.append(f"{path.name}: {pages} pages, the plan has {len(plan['slides'])} slides")
    return {"pages": pages, "expected": len(plan["slides"])}


def cmd_deck(args) -> int:
    plan = parse_plan(args.plan)
    manifest, folder = load_manifest(plan["path"]), Path(plan["path"]).parent
    errors, flags, not_checked, files = [], [], [], {}
    record = folder / "build.json"
    if not record.is_file():
        not_checked.append("no build.json beside the plan: whether the deck was built from this plan is unknown")
    elif json.loads(record.read_text(encoding="utf-8")).get("plan_sha256") != plan["sha256"]:
        errors.append("the plan changed after the deck was built: run build_deck.py again")
    for name in args.files:
        path, kind = Path(name), Path(name).suffix.lower()
        if not path.is_file() or kind not in (".tex", ".pdf", ".pptx"):
            raise PlanError(f"{path}: not a .tex, .pdf or .pptx file that exists")
        if kind == ".tex":
            files[name] = check_tex(path, plan, errors, not_checked)
        elif kind == ".pdf":
            files[name] = check_pdf(path, plan, errors, not_checked)
        else:
            files[name] = check_pptx(path, plan, manifest, errors, flags)
            not_checked.append(f"{path.name}: {NOT_RENDERED}")
    result = {"tool": TOOL, "plan": plan["path"], "ok": not errors, "errors": errors, "flags": flags,
              "not_checked": not_checked, "files": files, "report": str(folder / "deck-check.md")}
    lines = ["# Deck check", "", f"Against `{plan['path']}`: {len(plan['slides'])} slides, "
             f"{sum(1 for s in plan['slides'] if s['backup'])} of them backup.", "",
             f"**{len(errors)} error(s), {len(flags)} flag(s), {len(not_checked)} not checked.**"]
    for heading, items in (("Errors", errors), ("Flags", flags), ("Not checked", not_checked)):
        lines += ["", f"## {heading}", ""] + ([f"- {item}" for item in items] or ["None."])
    lines += ["", "## Files", ""] + [
        f"- `{name}`: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in facts.items() if k != "layout")
        for name, facts in files.items()]
    (folder / "deck-check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a slide plan, and the deck built from it.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="Check the plan before the deck is built")
    p.add_argument("plan")
    p.add_argument("--paper", help="The paper as .pdf or .txt (default: `paper:` of the front block)")
    p.add_argument("--slides-per-minute", type=float, help="Replaces the convention of the talk type")
    p.add_argument("--words-per-minute", type=float, default=WORDS_PER_MINUTE,
                   help=f"Speaking rate for the notes (default {WORDS_PER_MINUTE}, a convention)")
    p = sub.add_parser("deck", help="Check deck.tex (with its .log), deck.pdf or deck.pptx against the plan")
    p.add_argument("files", nargs="+")
    p.add_argument("--plan", required=True)
    args = parser.parse_args()
    try:
        return cmd_check(args) if args.command == "check" else cmd_deck(args)
    except PlanError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
