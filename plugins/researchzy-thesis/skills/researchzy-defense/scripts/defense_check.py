#!/usr/bin/env python3
"""Check the answer outlines of a thesis defence against the thesis, and record a mock defence.

  defense_check.py pages thesis.pdf        (or thesis.txt with [[page N]] lines or form feeds)
  defense_check.py check
  defense_check.py session --question Q7 --verdict shaky --answer-file answer.txt --gap "..."

Each takes --dir (default: defense). What they write and check: references/files.md. A PDF needs
PyMuPDF or pdftotext, else thesis-pages.txt says not_checked and why. Exit code 1: check found a fail,
or session refused the turn (solid with a number neither in the thesis nor allowed; not solid without
--gap). Exit code 2: an input cannot be read. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_match import match_quality, normalize, tokens  # noqa: E402

TOOL = "researchzy-defense"
CATEGORIES = ("opening", "contribution", "method", "data", "limitation", "application", "closing")
SOURCES = ("reviewer", "audit", "review", "thesis", "search", "user")
LEVELS, VERDICTS = ("defend", "bound", "adopt"), ("solid", "shaky", "stuck", "wrong", "dodged")
RESULTS = ("supported", "partly_supported", "not_supported", "not_tested")
MIN_QUOTE_TOKENS, MIN_QUOTE_CHARS = 5, 12   # a shorter quote matches somewhere in most theses
MIN_TEXT_CHARS = 500                        # less text than this is a scan or a failed extraction
FULL_WIDTH = str.maketrans("０１２３４５６７８９％．＜＞＝～－＋−", "0123456789%.<>=~-+-")
MARK = re.compile(r"^[ \t]*(?:\[\[page (\d+)\]\]|=+ PAGE (\d+) =+)[ \t]*$", re.M | re.I)
HEADER = re.compile(r"^===== PDF page (\d+): (?:printed page (\S+) \((roman|arabic)(?:, (inferred|PDF page number))?\)"
                    r"|no printed page number) =====$", re.M)
PAGE_LINE = re.compile(r"^[-–—·•\s]*(?:page\s+|p\.\s*|第\s*)?(?P<n>\d{1,4}|[ivxlcdm]{1,8})(?:\s*页)?"
                       r"(?:\s*(?:of|/|共)\s*\d+\s*页?)?[-–—·•\s]*$", re.I)
ROMAN = re.compile(r"m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})", re.I)
# CJK-aware, as in researchzy-translate: a Han character beside a number is a boundary (样本量为312人); a
# Latin letter before it makes it part of a name (H2, p53); an uppercase name before a hyphen hides it (COVID-19).
NUM = re.compile(r"(?<![A-Za-z0-9_.,])(?<![A-Z][-–])(?P<sign>[-–](?=[\d.]))?"
                 r"(?P<num>\d{1,3}(?:[,   ]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
                 r"(?P<pct>\s?(?:%|‰|percent(?![A-Za-z])|per cent(?![A-Za-z])))?(?!\d|[.,]\d)")
# Table 4.3, Fig. 2, 表4-3, 图 3.2; the character before 表 or 图 rules out words such as 发表 and 地图.
DISPLAY = re.compile(r"(?:(?<![A-Za-z])(?P<en>(?i:tables?|tab\.|figures?|figs?\.?))|(?<![试意地企代发列量])"
                     r"(?P<zh>[表图]))\s*(?P<num>[A-Z]?\d+(?:[.\-–—．]\d+)*)(?:[a-z](?![A-Za-z]))?")
STOP = "所示|中|显示|可见|表明|列出|给出|的|和|与|及|为|是|说明|反映|报告|呈现|对|在|则|分别|进一步"
# After a label that starts a line, a caption goes on with its title; a sentence that wrapped there does not.
CAPTION_END = re.compile(r"\s*(?:$|[:：.．|—–-]|(?<=\s)(?=[A-Z0-9(（\[“\"])|(?=(?!" + STOP + r")[一-鿿]))")
LEADER = re.compile(r"(?:[.·…]\s*){3,}[ivxlcdm\d]+\s*$", re.I)    # a line of a contents page or a list of tables
PAGE_REF = re.compile(r"(?<![A-Za-z])(?i:pp?\.|pages?)\s*[ivxlcdm\d]+(?:\s*[-–—]\s*[ivxlcdm\d]+)?"
                      r"|(?:第\s*)?\d+\s*(?:[-–—~～至]\s*\d+\s*)?页")
OTHER_REF = re.compile(r"(?<![A-Za-z])(?i:chapters?|sections?|sect\.|§|eqs?\.|equations?|appendix|hypothes[ie]s)"
                       r"\s*\(?[A-Z]?\d+(?:\.\d+)*[a-z]?\)?|第\s*[\d一二三四五六七八九十]+\s*[章节]|\d+(?:\.\d+)*\s*节"
                       r"|(?:公式|方程|式)\s*[（(]\s*[\d.\-]+\s*[)）]|假设\s*\d+[a-z]?|\[\d+(?:\s*[,，\-–]\s*\d+)*\]")
HYPO = re.compile(r"(?<![A-Za-z0-9])(?:H|(?i:hypothes[ie]s)\s*|假设\s*)[1-9]\d*[a-z]?(?![A-Za-z0-9])")
QUOTE_PROBLEM = {"partly": "only part of the quote is in the thesis: copy it again from the thesis",
                 "absent": "NOT_FOUND: the quote is not in the thesis",
                 "too_short": "quote at least five words, or twelve characters of Chinese"}


def die(message: str):
    print(message, file=sys.stderr)
    raise SystemExit(2)


def load_json(path: Path, required: bool = True):
    if not path.is_file():
        return die(f"{path} does not exist (references/files.md).") if required else None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        die(f"{path} is not valid JSON: {exc}")


def pymupdf():
    for name in ("pymupdf", "fitz"):
        try:
            return __import__(name)
        except ImportError:
            pass


def read_thesis(path: Path):
    """([(PDF page, text)], reader, why there is no text); a text without page marks is page 0: no pages."""
    fitz = pymupdf() if (pdf := path.suffix.lower() == ".pdf") else None
    try:
        if fitz:
            with fitz.open(path) as doc:
                return [(pg.number + 1, pg.get_text("text", sort=True)) for pg in doc], "PyMuPDF", ""
        if pdf and not shutil.which("pdftotext"):
            return [], "none", "reading a PDF needs PyMuPDF (pip install pymupdf) or pdftotext (poppler-utils)"
        text = subprocess.run(["pdftotext", "-q", str(path), "-"], capture_output=True, text=True,
                              check=True).stdout if pdf else path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # a damaged, encrypted or unreadable file: say so, do not crash
        die(f"cannot read {path}: {exc}")
    marks = list(MARK.finditer(text))
    ends = [m.start() for m in marks[1:]] + [len(text)]
    pages = ([(int(m[1] or m[2]), text[m.end():end]) for m, end in zip(marks, ends)] if marks else
             list(enumerate(text.rstrip("\f\n").split("\f"), 1)) if "\f" in text else [(0, text)])
    return pages, "pdftotext" if pdf else "text", ""


def parse_label(text):
    """(style, value) of a printed page number, or None."""
    text = str(text).strip()
    if text.isdigit() and 0 < int(text) < 10000:
        return "arabic", int(text)
    if text and ROMAN.fullmatch(text):
        values = [dict(zip("ivxlcdm", (1, 5, 10, 50, 100, 500, 1000)))[c] for c in text.lower()]
        return "roman", sum(-v if v < nxt else v for v, nxt in zip(values, values[1:] + [0]))
    return None


def roman(n: int, upper: bool) -> str:
    out = ""
    for value, letters in zip((1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1),
                              "m cm d cd c xc l xl x ix v iv i".split()):
        out, n = out + letters * (n // value), n % value
    return out.upper() if upper else out


def assign_labels(texts: list) -> list:
    """The printed number of each page: a line of its own among the first and last two; the run decides."""
    pages, last = [], None                      # last: (index, style, value) of the last numbered page
    for i, (pdf, text) in enumerate(texts):
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(line.strip() for line in text.splitlines())).strip("\n")
        lines = [line for line in text.splitlines() if line]
        found = [(*parse_label(m["n"]), m["n"]) for m in map(PAGE_LINE.match, dict.fromkeys(
            lines[-2:][::-1] + lines[:2])) if m and parse_label(m["n"])]
        want = last and (last[1], last[2] + i - last[0])
        pick = next((c for c in found if c[:2] == want), found[0] if found else None)
        pages.append({"pdf": pdf, "text": text, "how": "printed" if pick else "",
                      **dict(zip(("style", "value", "label"), pick or ("", None, "")))})
        last = (i, pick[0], pick[1]) if pick else last

    def neighbour(i: int, step: int) -> tuple:
        j = i + step
        while 0 <= j < len(pages) and not pages[j]["label"]:
            j += step
        return (pages[j] if 0 <= j < len(pages) else None), j

    for i, page in enumerate(pages):            # a page between two pages of one run carries the run's number
        (a, j), (b, k) = neighbour(i, -1), neighbour(i, 1)
        if a and b and a["style"] == b["style"] and a["value"] + k - j == b["value"] \
                and (page["style"], page["value"]) != (a["style"], a["value"] + i - j):
            value = a["value"] + i - j
            page.update(style=a["style"], value=value, how="inferred",
                        label=str(value) if a["style"] == "arabic" else roman(value, a["label"].isupper()))
    for p in pages if not any(p["label"] for p in pages) else []:
        p.update(label=str(p["pdf"]), style="arabic", value=p["pdf"], how="PDF page number")
    return pages


def runs(pages: list) -> str:
    """'i–xii (PDF 1–12), 1–120 (PDF 13–132)': the runs of printed numbers."""
    out = []
    for p in (p for p in pages if p["label"]):
        a, b = out[-1] if out else ({}, {})
        if (b.get("style"), b.get("value", -9) + 1, b.get("pdf", -9) + 1) == (p["style"], p["value"], p["pdf"]):
            out[-1] = (a, p)
        else:
            out.append((p, p))
    return ", ".join(f"{a['label']}–{b['label']} (PDF {a['pdf']}–{b['pdf']})" if a is not b else
                     f"{a['label']} (PDF {a['pdf']})" for a, b in out) or "none"


def display_key(m) -> tuple:
    kind = "table" if m["zh"] == "表" or (m["en"] or "").lower().startswith("tab") else "figure"
    return kind, re.sub(r"[\-–—．]", ".", m["num"]).upper()


def displays(pages: list) -> dict:
    """{(kind, number): {name, captions: [PDF page], mentions: [PDF page]}}."""
    found = {}
    for p in pages:
        for line in p["text"].splitlines():
            for m in DISPLAY.finditer(line):
                entry = found.setdefault(display_key(m), {"name": m[0].strip(), "captions": [], "mentions": []})
                caption = not line[:m.start()].strip() and CAPTION_END.match(line, m.end()) and not LEADER.search(line)
                entry["captions" if caption else "mentions"].append(p["pdf"])
    return found


def at(by_pdf: dict, pdfs) -> str:
    """'printed page 76 (PDF page 88)' for up to four PDF pages."""
    pdfs = sorted(set(pdfs))
    return ", ".join(f"PDF page {n}" if by_pdf[n]["how"] in ("", "PDF page number") else f"printed page "
                     f"{by_pdf[n]['label']} (PDF page {n})" for n in pdfs[:4]) + " and more" * (len(pdfs) > 4)


def cmd_pages(args) -> int:
    path, folder = Path(args.thesis), Path(args.dir)
    if not path.is_file():
        die(f"{path} does not exist.")
    texts, reader, why = read_thesis(path)
    paged = bool(texts) and texts[0][0] != 0
    if not why and sum(len(re.sub(r"\s", "", t)) for _, t in texts) < MIN_TEXT_CHARS:
        why = f"{path} has almost no text (a scan?): the page checks cannot run on it"
    pages = [] if why else assign_labels(texts) if paged else [
        {"pdf": 1, "text": texts[0][1].strip(), "label": "", "style": "", "value": None, "how": ""}]
    by_pdf, found, span = {p["pdf"]: p for p in pages}, displays(pages), runs(pages) if paged else "none"
    lines = ["# thesis-pages.txt, written by defense_check.py pages: do not edit it; run pages again.",
             f"# source: {path}", f"# sha256: {hashlib.sha256(path.read_bytes()).hexdigest()}",
             f"# date: {datetime.date.today()}", f"# reader: {reader}", f"# paged: {'yes' if paged else 'no'}",
             f"# status: {'not_checked: ' + why if why else 'ok'}", f"# printed pages: {span}",
             "# Tables and figures, at the page of their caption:"]
    for _, e in sorted(found.items(), key=lambda kv: (kv[0][0], [int(x) for x in re.findall(r"\d+", kv[0][1])])):
        lines.append(f"#   {e['name']}: " + (at(by_pdf, e["captions"]) if e["captions"] else
                                             "no caption; mentioned on " + at(by_pdf, e["mentions"])))
    for p in pages:
        how = f" ({p['style']}" + ("" if p["how"] == "printed" else f", {p['how']}") + ")"
        lines += [f"===== PDF page {p['pdf']}: " + (f"printed page {p['label']}{how}" if p["label"] else
                                                   "no printed page number") + " =====", p["text"]]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "thesis-pages.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"tool": TOOL, "status": "not_checked" if why else "ok", "reason": why, "reader": reader,
                      "pages": len(pages), "printed": span, "output": str(folder / "thesis-pages.txt")},
                     indent=2, ensure_ascii=False))
    return 0


def load_thesis(folder: Path) -> dict:
    path = folder / "thesis-pages.txt"
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    meta, heads = dict(re.findall(r"^# (source|date|status|paged): (.*)$", text, re.M)), list(HEADER.finditer(text))
    if meta.get("status") != "ok" or not heads:
        return {"ok": False, "paged": False, "meta": meta, "why": meta.get("status") or
                f"no pages in {path}: run `defense_check.py pages` on the thesis first"}
    T = {"ok": True, "why": "", "meta": meta, "paged": meta.get("paged") != "no", "pages": [],
         "by_label": defaultdict(list), "index": defaultdict(list), "floor": defaultdict(list)}
    for m, nxt in zip(heads, heads[1:] + [None]):
        p = {"pdf": int(m[1]), "label": m[2] or "", "style": m[3] or "", "how": m[4] or ("printed" if m[2] else ""),
             "value": (parse_label(m[2]) or ("", None))[1], "text": text[m.end():nxt and nxt.start()].strip("\n")}
        T["pages"].append(p)
        T["by_label"][p["label"].lower()].append(p)
        p["bare"], lines = squeeze(p["text"]), p["text"].splitlines()
        edge = [i for i, line in enumerate(lines) if line.strip()]
        drop = next((i for i in edge[-2:][::-1] + edge[:2] if p["label"] and (n := PAGE_LINE.match(lines[i].strip()))
                     and n["n"].lower() == p["label"].lower()), None)   # the page number is no number of the thesis
        for tok in numbers_of("\n".join(line for i, line in enumerate(lines) if i != drop)):
            tok["page"] = p
            T["index"][tok["value"]].append(tok)
            T["floor"][int(tok["value"])] += [tok] if tok["decimals"] else []
    T.update(by_pdf={p["pdf"]: p for p in T["pages"]}, displays=displays(T["pages"]), runs=runs(T["pages"]),
             bare="".join(p["bare"] for p in T["pages"]))
    return T


def numbers_of(text: str) -> list:
    """The numerals of a text, after blanking references to pages, tables, chapters and the like."""
    raw = text = text.translate(FULL_WIDTH)            # the context is shown from the text before blanking
    for pattern in (DISPLAY, PAGE_REF, OTHER_REF):
        text = pattern.sub(lambda m: " " * len(m[0]), text)
    out = []
    for m in NUM.finditer(text):
        sign = bool(m["sign"]) and not re.search(r"[0-9%)）]\s*$", text[:m.start()])   # 18 –65 is a range
        value, start = Decimal(re.sub(r"[^\d.]", "", m["num"])), m.start() if sign or not m["sign"] else m.start("num")
        left, right = max(0, m.start() - 30), min(len(text), m.end() + 30)
        out.append({"written": " ".join(text[start:m.end()].split()), "value": value, "negative": sign,
                    "decimals": max(0, -value.as_tuple().exponent), "percent": bool(m["pct"]),
                    "context": "…" * bool(left) + " ".join(raw[left:right].split()) + "…" * (right < len(text))})
    return out


def find_number(tok: dict, T: dict, cited=frozenset()):
    value, half = tok["value"], Decimal(1).scaleb(-tok["decimals"]) / 2      # 86 is 85.7 rounded; 0.4 is 0.42
    near = (p for b in (int(value) - 1, int(value), int(value) + 1) for p in T["floor"].get(b, []))
    hits = [("exact", p) for p in T["index"].get(value, [])] + [
        ("rounded", p) for p in near if p["decimals"] > tok["decimals"] and abs(p["value"] - value) <= half]
    hits = [h for h in hits if h[1]["negative"] or not tok["negative"]]
    hits.sort(key=lambda h: (h[1]["page"]["pdf"] not in cited, tok["percent"] and not h[1]["percent"], h[0] != "exact"))
    return hits[0] if hits else None


def squeeze(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text))


def quote_grade(quote: str, spans: list) -> tuple:
    """(found | partly | absent | too_short, index of the first (text, unspaced text) span that holds it)."""
    bare = squeeze(quote)
    letters = [c for c in bare if c.isalnum()]
    cjk = bool(letters) and sum(not c.isascii() for c in letters) >= len(letters) / 2
    if len(letters) < MIN_QUOTE_CHARS if cjk else len(tokens(quote)) < MIN_QUOTE_TOKENS:
        return "too_short", None
    best = "absent"
    for n, (text, flat) in enumerate(spans):
        g = ("EXACT" if bare in flat else "ABSENT") if cjk else match_quality(quote, text)["grade"]
        if g in ("EXACT", "INTERLEAVED"):
            return "found", n
        best = "partly" if g == "PARTIAL" else best
    return best, None


def page_refs(value):
    """The printed pages an anchor cites ("76", "vii", "p. 76", both ends of "76-77"), or None."""
    text = re.sub(r"(?i)^\s*(?:pp?\.|pages?)\s*|^\s*第\s*|\s*页\s*$", "", str(value)).strip()
    ends = [e.strip() for e in re.split(r"\s*[-–—~～至]\s*", text)]
    parsed = [parse_label(e) for e in ends]
    return ends if 1 <= len(ends) <= 2 and None not in parsed else None


def check_anchor(anchor, where: str, T: dict, add) -> tuple:
    """(PDF pages the anchor points at, whether it is a page alone); one row per finding."""
    anchor = anchor if isinstance(anchor, dict) else {}
    page, disp, quote, pages = anchor.get("page"), anchor.get("display"), anchor.get("quote"), set()
    if not (page or disp or quote) or not T["ok"]:
        add(where, "anchor", "not_checked" if page or disp or quote else "fail", T["why"] if page or disp or quote
            else "an anchor names a printed page, a table or figure, or a quote")
        return set(), False
    labels, by_pdf = page_refs(page) if page else [], T["by_pdf"]
    if labels is None or labels and not T["paged"]:
        add(where, "page", "not_checked" if labels else "fail", "the thesis text has no pages: give the PDF and run "
            "pages again" if labels else f"{page!r} is not a printed page number such as 76, vii or 76-78")
    labels = labels if labels and T["paged"] else []
    for label in labels:
        pages |= {p["pdf"] for p in T["by_label"].get(label.lower(), [])}
        if not T["by_label"].get(label.lower()):
            add(where, "page", "fail", f"there is no printed page {label}; the thesis has {T['runs']}")
    m = DISPLAY.search(str(disp)) if disp else None
    entry = T["displays"].get(display_key(m)) if m else None
    if disp:
        caps = set(entry["captions"]) if entry else set()
        state = "fail" if not entry or labels and caps and not pages & caps else "pass" if caps else "manual"
        add(where, "display", state, f"NOT_FOUND: no table or figure {disp} in the thesis" if not entry else f"{disp} "
            f"is on {at(by_pdf, caps)}" + f", not on page {page}" * (state == "fail") if caps else
            f"no caption of {disp} found; it is mentioned on {at(by_pdf, entry['mentions'])}")
        pages |= set() if labels else caps
    if quote:
        order = [p for p in T["pages"] if p["pdf"] in pages] + T["pages"]
        spans = [[p] for p in order] + [[p, by_pdf[p["pdf"] + 1]] for p in order if p["pdf"] + 1 in by_pdf]
        state, n = quote_grade(str(quote), [("\n".join(s["text"] for s in sp), "".join(s["bare"] for s in sp))
                                            for sp in spans])
        found = {s["pdf"] for s in spans[n]} if state == "found" else set()
        elsewhere = labels and found and not found & pages
        add(where, "quote", "pass" if found and not elsewhere else "fail", QUOTE_PROBLEM.get(state) or
            f"the quote is on {at(by_pdf, found)}" + (f", not on page {page}" if elsewhere else ""))
        pages |= set() if labels else found
    return pages, bool(labels) and not (disp or quote)


def parse_allow(entries, where: str, add) -> dict:
    allowed = {}
    for entry in entries if isinstance(entries, list) else []:
        text, sep, source = str(entry).partition("|")
        found = numbers_of(text)
        if not (sep and source.strip() and found):
            add(where, "allow", "fail", f"{entry!r}: an allow entry is `number | where it comes from`")
        allowed.update((tok["value"], source.strip()) for tok in found)
    return allowed


def check_numbers(texts: list, cited: set, allowed: dict, T: dict, where: str, add) -> list:
    """One row per numeral of an outline; returns [(numeral, the thesis's numeral)] for those found."""
    found = []
    for tok in (tok for text in texts for tok in numbers_of(str(text))):
        hit, shown = find_number(tok, T, cited) if T["ok"] else None, f"`{tok['written']}`"
        state = "pass" if T["ok"] else "not_checked"
        if tok["value"] in allowed or not T["ok"]:
            add(where, "number", state, shown + ": " + allowed.get(tok["value"], T["why"]))
        elif not hit:
            add(where, "number", "fail", f"NOT_FOUND: {shown} (\"{tok['context']}\") is not in the thesis. Correct it, "
                "say it without the number, or give its source in allow")
        else:
            on = hit[1]["page"]["pdf"] in cited or not T["paged"]
            add(where, "number", "pass" if on else "manual", f"{shown} {'on' if on else 'not on a cited page but on'} "
                f"{at(T['by_pdf'], [hit[1]['page']['pdf']])}" + (f", rounded from {hit[1]['written']}" if hit[0] ==
                "rounded" else "") + (", no percent sign in the thesis" if tok["percent"] and not hit[1]["percent"]
                                      else "") + f": \"{hit[1]['context']}\"")
            found.append((tok, hit[1]))
    return found


def chapter_pages(claims, T: dict, add) -> tuple:
    ranges, titles = {}, {}
    for ch in (claims.get("chapters") or []) if isinstance(claims, dict) else []:
        ch = ch if isinstance(ch, dict) else {}
        cid, ends = str(ch.get("id", "")).strip(), [T["by_label"].get(str(ch.get(k)).lower()) for k in (
            "first_page", "last_page")] if T["paged"] else []
        if not cid or ends and not all(ends):
            add(f"chapter {cid or '?'}", "chapter", "fail", "a chapter has an id, a title, and a first_page and a "
                "last_page that are printed pages of the thesis")
        if cid:
            titles[cid] = str(ch.get("title", ""))
            ranges[cid] = set(range(ends[0][0]["pdf"], ends[1][-1]["pdf"] + 1)) if ends and all(ends) else set()
    return ranges, titles


def cmd_check(args) -> int:
    folder = Path(args.dir)
    bank, claims = load_json(folder / "questions.json"), load_json(folder / "claims.json", required=False)
    bank, T = bank if isinstance(bank, dict) else {}, load_thesis(folder)
    rows, numbers, covered = [], [], defaultdict(set)

    def add(where, check, status, detail):
        rows.append({"where": where, "check": check, "status": status, "detail": detail})

    if not T["ok"]:
        add("thesis", "pages", "not_checked", T["why"])
    chapters, titles = chapter_pages(claims, T, add)
    known = {}
    for c in (claims.get("claims") or []) if isinstance(claims, dict) else []:
        c = c if isinstance(c, dict) else {}
        cid = str(c.get("id", "")).strip()
        if not cid or cid in known or not (c.get("quote") and c.get("page")) or c.get("kind") == "hypothesis" and not (
                HYPO.search(str(c.get("label"))) and c.get("result") in RESULTS):
            add(f"claim {cid or '?'}", "claim", "fail", "a claim has its own id, a quote and its printed page; a "
                "hypothesis also a label (H3, 假设3) and a result: " + ", ".join(RESULTS))
        else:
            known[cid] = c
            check_anchor({"page": c["page"], "quote": c["quote"]}, f"claim {cid}", T, add)
    if claims is None:
        add("claims.json", "coverage", "not_checked", "no claims.json: claims, hypotheses and chapters are not covered")
    questions = [q for q in bank.get("questions") or [] if isinstance(q, dict)]
    ids, others_began = [str(q.get("id")) for q in questions], False
    for n, q in enumerate(questions, 1):
        qid, src = str(q.get("id") or f"question {n}"), q.get("source") if isinstance(q.get("source"), dict) else {}
        outline = q.get("outline") if isinstance(q.get("outline"), dict) else {}
        kind, paper, not_done = src.get("type"), src.get("paper"), outline.get("not_done")
        name = src.get("record" if kind == "search" else "file")
        report = next((p.read_text(encoding="utf-8", errors="replace") for p in (Path(str(name)), folder / str(name))
                       if name and p.is_file()), None)      # a report or search record: from here, else from --dir
        names = [str(paper[k]) for k in ("doi", "title") if paper.get(k)] if isinstance(paper, dict) else []
        listed = bool(report and names) and all(squeeze(n) in squeeze(report) or squeeze(json.dumps(n)[1:-1])
                                                in squeeze(report) for n in names)   # also with \\u escapes
        problems = [
            ("format", "every question has its own id and its text", not q.get("id") or ids.count(qid) > 1
             or not str(q.get("question", "")).strip()),
            ("category", "category is one of " + ", ".join(CATEGORIES), q.get("category") not in CATEGORIES),
            ("source", "source.type is one of " + ", ".join(SOURCES), kind not in SOURCES),
            ("source", "a reviewer's question quotes the objection (source.quote) from the report in source.file",
             kind == "reviewer" and (report is None or quote_grade(str(src.get("quote", "")), [(report, squeeze(
                 report))])[0] != "found")),
            ("order", "the reviewers' questions come before all others", kind == "reviewer" and others_began),
            ("source", "a search question names its saved record (source.record) and a paper in it (source.paper, "
             "doi or title): never name a paper that no search returned", kind == "search" and not listed),
            ("chapter", f"chapter {q.get('chapter')} is not in claims.json",
             q.get("chapter") is not None and str(q.get("chapter")) not in chapters),
            ("outline", "an outline has an opening sentence, a level (" + ", ".join(LEVELS) + ") and an anchor",
             not str(outline.get("opening", "")).strip() or outline.get("level") not in LEVELS
             or not outline.get("anchors")),
            ("outline", "not_done says what was not done and why: {analysis, because}", not_done is not None
             and not (isinstance(not_done, dict) and str(not_done.get("because", "")).strip()))]
        problems += [("claim", f"claim {cid} is not in claims.json", str(cid) not in known)
                     for cid in q.get("claims") or []]
        for check, message, failed in problems:
            if failed:
                add(qid, check, "fail", message)
        others_began = others_began or kind != "reviewer"
        cited, alone = set(), []
        for i, anchor in enumerate(outline.get("anchors") or [], 1):
            got, page_only = check_anchor(anchor, f"{qid} anchor {i}", T, add)
            cited |= got
            alone += [(i, got)] if page_only else []
        texts = [outline.get("opening", ""), *(outline.get("points") or [])]
        texts += [not_done.get("analysis", ""), not_done.get("because", "")] if isinstance(not_done, dict) else []
        found = check_numbers(texts, cited, parse_allow(outline.get("allow"), qid, add), T, qid, add)
        numbers += [(qid, tok, p) for tok, p in found]
        for i, got in alone:
            if not any(p["page"]["pdf"] in got for _, p in found):
                add(f"{qid} anchor {i}", "anchor", "fail", "a page alone anchors nothing: name the table or figure "
                    "on it, quote it, or use a number printed on it")
        covered["category"].add(q.get("category"))
        covered["claim"] |= {str(cid) for cid in q.get("claims") or []}
        covered["chapter"] |= {str(q.get("chapter"))} | {cid for cid, pages in chapters.items() if pages & cited}
    not_asked = bank.get("not_asked") if isinstance(bank.get("not_asked"), dict) else {}
    gaps = [(c, f"category {c}") for c in CATEGORIES if c not in covered["category"]]
    gaps += [(c, f"chapter {c} ({titles[c]})") for c in chapters if c not in covered["chapter"]]
    gaps += [(cid, f"hypothesis {c.get('label')} ({c.get('result')}, page {c.get('page')})" if c.get("kind") ==
              "hypothesis" else f"claim {cid}") for cid, c in known.items() if cid not in covered["claim"]]
    for key, label in gaps:     # without the pages, a chapter may be covered by an anchor no one could place
        reason, unknown = str(not_asked.get(key, "")).strip(), label.startswith("chapter") and not T["paged"]
        add("coverage", "coverage", "pass" if reason else "not_checked" if unknown else "fail", f"no question on "
            f"{label}" + (f", because {reason}" if reason else ": add one, or give the reason in not_asked"))
    status = {s: [r for r in rows if r["status"] == s] for s in ("fail", "manual", "not_checked", "pass")}
    count = {s: len(v) for s, v in status.items()}
    lines = ["# Defence check", "", f"Thesis `{T['meta'].get('source', '-')}` read on {T['meta'].get('date', '-')}; "
             f"printed pages: {T.get('runs', 'not read')}.", "", f"**{count['fail']} fail, {count['manual']} manual, "
             f"{count['not_checked']} not checked.** Not checked is not passed.", ""]
    for name, items in status.items():
        lines += [f"## {name.replace('_', ' ').capitalize()}", ""] + [
            f"- {r['where']}, {r['check']}: {r['detail']}" for r in items] + [""] if items else []
    (folder / "check.md").write_text("\n".join(lines + ["## Numbers to know", ""] + numbers_table(numbers)) + "\n",
                                     encoding="utf-8")
    fails = [f"{r['where']}: {r['detail']}" for r in status["fail"]][:30]
    print(json.dumps({"tool": TOOL, "ok": not fails, **count, "report": str(folder / "check.md"), "fails": fails},
                     indent=2, ensure_ascii=False))
    return 1 if fails else 0


def numbers_table(numbers: list) -> list:
    rows = {}
    for qid, tok, p in numbers:
        rows.setdefault((p["page"]["pdf"], p["written"]), [p, []])[1].append(qid)
    return ["| Number | Printed page | PDF page | In the thesis | Questions |", "|---|---|---|---|---|"] + [
        f"| {written} | {p['page']['label'] or '-'} | {pdf} | {p['context'].replace('|', '/')} | "
        f"{', '.join(dict.fromkeys(qids))} |" for (pdf, written), (p, qids) in sorted(rows.items())]


def cmd_session(args) -> int:
    folder, log = Path(args.dir), Path(args.dir) / "session.jsonl"
    bank = load_json(folder / "questions.json")
    qmap = {str(q.get("id")): q for q in (bank.get("questions") or [] if isinstance(bank, dict) else [])
            if isinstance(q, dict)}
    if args.question not in qmap:
        die(f"{args.question} is not a question of {folder / 'questions.json'}")
    try:
        answer = Path(args.answer_file).read_text(encoding="utf-8")
        turns = [json.loads(x) for x in (log.read_text(encoding="utf-8") if log.is_file() else "").splitlines()
                 if x.strip()]
    except (OSError, ValueError) as exc:
        die(f"cannot read the answer or {log}: {exc}")
    T, q, numbers = load_thesis(folder), qmap[args.question], []
    allowed = parse_allow((q.get("outline") or {}).get("allow"), "", lambda *a: None)
    for tok in numbers_of(answer):
        hit = find_number(tok, T) if T["ok"] else None
        result = ("in_thesis" if hit else "allowed" if tok["value"] in allowed else
                  "not_in_thesis" if T["ok"] else "not_checked")
        numbers.append({"number": tok["written"], "result": result, "context": tok["context"], "where":
                        at(T["by_pdf"], [hit[1]["page"]["pdf"]]) if hit else allowed.get(tok["value"], T["why"])})
    missing = [n["number"] for n in numbers if n["result"] == "not_in_thesis"]
    problem = ("an answer with a number that is neither in the thesis nor allowed is not solid: record shaky or "
               "wrong, and name the gap" if args.verdict == "solid" and missing else "a turn that is not solid "
               "needs --gap: what was missing or wrong" if args.verdict != "solid" and not args.gap.strip() else "")
    result = {"tool": TOOL, "question": args.question, "verdict": args.verdict, "numbers": numbers,
              "not_in_thesis": missing, "ok": not problem, **({"error": problem} if problem else {})}
    if not problem:
        turn = {"turn": len(turns) + 1, "time": datetime.datetime.now().isoformat(timespec="seconds"),
                "question": args.question, "asked": q.get("question", ""), "answer": answer.strip(),
                "verdict": args.verdict, "gap": args.gap.strip(), "numbers": numbers}
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(turn, ensure_ascii=False) + "\n")
        write_revision(folder, qmap, turns + [turn], T)
        result.update(turn=turn["turn"], log=str(log), revision_list=str(folder / "revision-list.md"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if problem else 0


def write_revision(folder: Path, qmap: dict, turns: list, T: dict) -> None:
    quiet = lambda *a: None  # noqa: E731
    ranges, titles = chapter_pages(load_json(folder / "claims.json", required=False), T, quiet)
    latest, history, numbers, cited, groups = {}, defaultdict(list), [], {}, defaultdict(list)
    for t in turns:
        latest[t["question"]] = t
        history[t["question"]].append(t["verdict"])
    for qid, q in qmap.items():
        outline = q.get("outline") if isinstance(q.get("outline"), dict) else {}
        cited[qid] = set().union(*[check_anchor(a, qid, T, quiet)[0] for a in outline.get("anchors") or []])
        numbers += [(qid, tok, p) for tok, p in check_numbers([outline.get("opening", ""), *(
            outline.get("points") or [])], cited[qid], {}, T, qid, quiet)] if T["ok"] else []
    for qid, t in latest.items():
        chapter = str(qmap.get(qid, {}).get("chapter"))
        if t["verdict"] != "solid" and qid in qmap:      # the declared chapter, else the chapter of an anchor
            chapter = chapter if chapter in ranges else next((c for c, p in ranges.items() if p & cited[qid]), None)
            groups[chapter].append(t)
    lines = ["# Revision list", "", f"{len(turns)} turn(s) on {len(latest)} question(s) in session.jsonl; "
             f"{sum(map(len, groups.values()))} still weak. This was a typed drill: say the weak answers aloud.", ""]
    for chapter in [c for c in ranges if c in groups] + ([None] if None in groups else []):
        lines += [f"## Chapter {chapter}: {titles[chapter]}" if chapter else "## Not tied to a chapter", ""]
        for t in groups[chapter]:
            q = qmap[t["question"]]
            anchors = [a for a in (q.get("outline") or {}).get("anchors") or [] if isinstance(a, dict)]
            gone = [n["number"] for n in t.get("numbers", []) if n["result"] == "not_in_thesis"]
            reread = "; ".join(", ".join(f"{'p. ' * (k == 'page')}{a[k]}" for k in ("page", "display", "quote")
                                         if a.get(k))[:90] for a in anchors)
            lines += [f"- **{q.get('id')}** ({q.get('category')}) {q.get('question', '')}",
                      f"  - Verdicts: {', '.join(history[t['question']])}. Gap: {t.get('gap') or '-'}"]
            lines += [f"  - Numbers not in the thesis: {', '.join(gone)}"] if gone else []
            lines += [f"  - Reread: {reread or 'no anchor'}", ""]
    lines += ["## Numbers to know", ""] + (numbers_table(numbers) if T["ok"] else [f"Not checked: {T['why']}"])
    (folder / "revision-list.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="defense", help="Folder of questions.json and the outputs (default: defense)")
    parser = argparse.ArgumentParser(description="Check defence answer outlines against the thesis; record mock turns.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pages", parents=[common], help="Write thesis-pages.txt: printed number and text of each page")
    p.add_argument("thesis", help="The thesis as .pdf, or as .txt with [[page N]] lines or form feeds")
    sub.add_parser("check", parents=[common], help="Check every anchor and number of the outlines, and the coverage")
    p = sub.add_parser("session", parents=[common], help="Record one mock-defence turn; rewrite revision-list.md")
    p.add_argument("--question", required=True, help="The id of the question in questions.json")
    p.add_argument("--verdict", required=True, choices=VERDICTS)
    p.add_argument("--answer-file", required=True, help="The user's answer as a UTF-8 text file")
    p.add_argument("--gap", default="", help="What was missing or wrong; required unless the verdict is solid")
    args = parser.parse_args(argv)
    return {"pages": cmd_pages, "check": cmd_check, "session": cmd_session}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
