#!/usr/bin/env python3
"""Measure a finished thesis against the school's written rules, never against a preset.

  format_check.py rules thesis-build/rules.txt          every quote of rules.json is in the rules text
  format_check.py docx thesis.docx [--main-starts 57]   sections and paragraph styles, read from the XML
  format_check.py pdf thesis.pdf [--main-starts 9]      every page of the PDF the user exported (PyMuPDF)
  format_check.py compare template.docx thesis.docx     styles in use and sections that differ

--dir (default thesis-build) receives the report; --rules defaults to <dir>/rules.json (see
references/rules-record.md); --main-starts is the ¶ or PDF page where chapter 1 begins, if not found.
docx resolves each paragraph style through document defaults, the basedOn chain and direct formatting,
East Asian and Latin fonts apart, and reads every section. Rows are pass, fail, manual, not_checked or
not_stated, with sections, pages or paragraphs (¶ counts the body's paragraphs in order, table cells
included, text boxes not). A rule the school does not state is not_stated; a rule that could not be
read stays not_checked; a value seen only in the template, or a rule in conflict, gives manual. In a PDF
a wider margin and a font of another name are manual: ink gives a lower bound, and fonts change names.

Exit 0 when nothing failed; 1 when (rules) a stated rule's quote is missing or not in the text, or
(docx, pdf) a row is fail; 2 when an input cannot be read. compare only reports. Standard library only,
except pdf, which uses PyMuPDF; without it every PDF row is not_checked.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
STATES = ("pass", "fail", "manual", "not_checked", "not_stated")
SOURCES = ("stated", "observed_in_template", "not_stated", "not_checked")
REQUIRED = ("page_size", "margins", "body_font", "body_size", "line_spacing", "first_line_indent", "heading_numbering",
            "page_numbers", "reference_standard", "citation_style")
MARGIN_KEYS = ("top", "bottom", "left", "right", "inside", "outside", "gutter")
TOLERANCE_MM = 1.0   # convention: PDF sizes and ink within 1 mm of the rule count as equal (--tolerance-mm)
BAND = 0.12          # convention: page numbers and running heads sit in the top or bottom 12% of a page
MM = 25.4 / 72       # millimetres per PDF point
TWIP = 25.4 / 1440   # millimetres per twip
ZH_SIZES = {"初号": 42, "小初": 36, "一号": 26, "小一": 24, "二号": 22, "小二": 18, "三号": 16, "小三": 15, "四号": 14,
            "小四": 12, "五号": 10.5, "小五": 9, "六号": 7.5, "小六": 6.5, "七号": 5.5, "八号": 5}
FONT_ALIASES = {"宋体": "simsun", "新宋体": "nsimsun", "黑体": "simhei", "楷体": "kaiti", "仿宋": "fangsong",
                "楷体_gb2312": "kaiti_gb2312", "仿宋_gb2312": "fangsong_gb2312", "微软雅黑": "microsoftyahei",
                "等线": "dengxian", "华文宋体": "stsong", "华文中宋": "stzhongsong", "华文楷体": "stkaiti",
                "华文仿宋": "stfangsong", "隶书": "lisu", "幼圆": "youyuan"}
HAN = re.compile(r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯]")
LATIN = re.compile(r"[A-Za-z0-9]")
QUOTE_MARKS = dict.fromkeys(map(ord, "‘’‚‛“”„‟«»‹›´`\""), "'")
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
TYPED_NUMBER = re.compile(r"^\s*(?:第\s*[0-9一二三四五六七八九十百]+\s*[章节篇]|(?:chapter|section)\s+\d+|\d+(?:\.\d+)+"
                          r"|\d+(?:\s*[.、](?!\d)|\s+)|[(]?[一二三四五六七八九十]+[)、])", re.I)
CHAPTER_ONE = re.compile(r"^\s*(?:第\s*[1一]\s*章|chapter\s+(?:1|one|i)\b|1\s+[^\d\s.])", re.I)
REFERENCE_HEADINGS = {"参考文献", "references", "bibliography", "referencelist", "workscited", "literaturecited"}
PAGE_LABEL = re.compile(r"^[-–—\s]*(?:page\s+|第\s*)?(\d{1,4}|[ivxlcdm]{1,8})(?:\s*页)?[-–—\s]*$", re.I)
ROMAN = re.compile(r"^m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})$", re.I)
LEADER = re.compile(r"(?:\.{3,}|…+|·{3,})\s*\d+$")
ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def fail(message: str):
    print(f"format_check: {message}", file=sys.stderr)
    raise SystemExit(2)


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def table(header: tuple, rows: list) -> list:
    cell = lambda value: re.sub(r"\s+", " ", str(value)).replace("|", "/").strip()  # noqa: E731
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)]


def spans(numbers, prefix: str = "¶ ", cap: int = 10) -> str:
    """12, 13, 14, 20 as "¶ 12–14, 20"; no numbers give an empty string."""
    runs = []
    for n in sorted(set(numbers)):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    prefix = "p. " if prefix == "pp. " and len(runs) == 1 and runs[0][0] == runs[0][1] else prefix
    text = ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in runs[:cap])
    return prefix + text + (f" and {len(runs) - cap} more" if len(runs) > cap else "") if runs else ""


def length_mm(text):
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(mm|cm|in|inch|inches|pt|毫米|厘米|磅)\s*", str(text), re.I)
    units = {"mm": 1, "毫米": 1, "cm": 10, "厘米": 10, "pt": MM, "磅": MM}
    return float(m.group(1)) * units.get(m.group(2).lower(), 25.4) if m else None


def size_pt(text):
    text = str(text).strip()
    name = text[:-1] if text.endswith("号") and text[:-1] in ZH_SIZES else text
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:pt|磅)?", text, re.I)
    return float(ZH_SIZES[name]) if name in ZH_SIZES else float(m.group(1)) if m else None


def spacing(text):
    text = str(text).strip().lower()
    m = re.fullmatch(r"(exactly|at least)\s+(\d+(?:\.\d+)?)\s*pt", text)
    if m:
        return ("exact" if m.group(1) == "exactly" else "atLeast", float(m.group(2)))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:lines?)?|single|double", text)
    return ("multiple", float(m.group(1)) if m.group(1) else 1.0 if text == "single" else 2.0) if m else None


def indent(text):
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:characters?|chars?|字符)\s*", str(text), re.I)
    length = length_mm(text)
    return ("chars", float(m.group(1))) if m else None if length is None else ("pt", length / MM)


def page_dims(text):
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(mm|cm|in)\s*", str(text), re.I)
    return (length_mm(m.group(1) + m.group(3)), length_mm(m.group(2) + m.group(3))) if m else None


POSITIONS = {"top", "bottom", "left", "center", "right", "outside", "inside"}
SHAPES = {"page_size": lambda v: page_dims(v) is not None, "body_size": lambda v: size_pt(v) is not None,
          "line_spacing": lambda v: spacing(v) is not None, "first_line_indent": lambda v: indent(v) is not None,
          "body_font": lambda v: isinstance(v, dict) and bool(v) and set(v) <= {"east_asian", "latin"},
          "margins": lambda v: isinstance(v, dict) and bool(v) and set(v) <= set(MARGIN_KEYS) and None not in map(length_mm, v.values())
          and not (set(v) & {"left", "right"} and set(v) & {"inside", "outside"}),
          "page_numbers": lambda v: isinstance(v, dict) and set(v) <= {"front_matter", "main_matter", "main_starts_at", "position"}
          and v.get("front_matter", "roman") in ("roman", "arabic", "none") and v.get("main_matter", "arabic") in ("roman", "arabic")
          and isinstance(v.get("main_starts_at", 1), int) and set(str(v.get("position", "")).lower().split()) <= POSITIONS}


def show(value, prop: str = "") -> str:
    if value is None:
        return "not set in the file"
    if isinstance(value, dict):
        return ", ".join(f"{k} {show(v)}" for k, v in value.items())
    if isinstance(value, tuple):
        return {"multiple": "multiple {:g}", "exact": "exactly {:g} pt", "atLeast": "at least {:g} pt", "chars": "{:g} characters",
                "pt": "{:.1f} pt"}[value[0]].format(value[1])
    return f"{value:g} pt" if prop == "size" else f"level {value + 1}" if prop == "outline" else str(value)


def font_key(name) -> str:
    key = re.sub(r"[\s,-]+", "", unicodedata.normalize("NFKC", re.sub(r"^[A-Z]{6}\+", "", str(name or ""))).casefold())
    key = FONT_ALIASES.get(key, key)
    while (cut := re.sub(r"(?:psmt|mt|ps|bold|italic|regular|oblique)$", "", key)) != key and len(cut) >= 3:
        key = cut
    return key


def same_font(a, b) -> bool:
    a, b = font_key(a), font_key(b)
    return bool(a and b) and (a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a))))


def record_errors(record: dict) -> list:
    """What keeps the record from being used. Each required topic must be there, as not_stated when the
    rules are silent: that separates silence from a topic nobody looked for."""
    errors, head, rules = [], record.get("record"), record.get("rules")
    if not isinstance(head, dict) or not str(head.get("rules_source") or "").strip():
        errors.append("record must be an object naming rules_source (and school, template_source, date_read)")
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(head.get("date_read", ""))):
        errors.append("record.date_read must be the date the rules were read, as YYYY-MM-DD")
    if not isinstance(rules, list) or not all(isinstance(r, dict) and r.get("topic") for r in rules):
        return errors + ["rules must be a list of objects, each with a topic"]
    topics = Counter(r["topic"] for r in rules)
    errors += [f"topic {t} appears {n} times: keep one entry and put the other source in conflicts" for t, n in topics.items() if n > 1]
    errors += [f'topic {t} is missing (source "not_stated" when the rules are silent)' for t in REQUIRED if t not in topics]
    for rule in rules:
        where, source = f"rules[{rule['topic']}]", rule.get("source")
        if source not in SOURCES:
            errors.append(f"{where}.source must be one of {', '.join(SOURCES)}")
        elif source != "not_stated" and not str(rule.get("locator") or "").strip():
            errors.append(f"{where}.locator is missing (page and section, the template part, or the unread page)")
        if source in ("stated", "observed_in_template") and not SHAPES.get(rule["topic"], lambda v: True)(rule.get("value")):
            errors.append(f"{where}.value is not in the form the reference gives: {json.dumps(rule.get('value'), ensure_ascii=False)}")
    conflicts = record.get("conflicts", [])
    if not isinstance(conflicts, list) or not all(isinstance(c, dict) and c.get("topic") and c.get("detail") for c in conflicts):
        errors.append("conflicts must be a list of objects with topic, detail and decision")
    return errors


def load_book(args, required: bool = False) -> dict:
    path = Path(args.rules) if args.rules else Path(args.dir) / "rules.json"
    if not path.is_file():
        if required:
            fail(f"no rules record at {path}: record the school's rules first (references/rules-record.md).")
        return {"rules": {}, "pending": {}, "path": None}
    try:
        record = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{path} cannot be read as JSON: {exc}")
    errors = record_errors(record) if isinstance(record, dict) else ["the file must hold a JSON object"]
    if errors:
        fail(f"{path} is not in the format of references/rules-record.md:\n  - " + "\n  - ".join(errors))
    pending = {c["topic"]: c["detail"] for c in record.get("conflicts", [])
               if str(c.get("decision") or "pending").strip().lower() == "pending"}
    return {"rules": {r["topic"]: r for r in record["rules"]}, "pending": pending, "path": path, "record": record}


def judge(book: dict, topic: str, ok, text: str, covered: bool = True) -> tuple:
    """(state, detail) of one measurement against the rule recorded for topic."""
    rule = book["rules"].get(topic)
    if rule is None:
        return "not_checked", f"{text}. No rule recorded for {topic}{'' if book['path'] else ' (no rules.json)'}."
    source, where = rule["source"], rule.get("locator", "")
    if source in ("not_checked", "not_stated"):
        return source, f"{text}. " + ("The rules do not state it." if source == "not_stated" else f"Unreadable rule ({where}).")
    if topic in book["pending"]:
        return "manual", f"{text}. Conflict for the user to settle: {book['pending'][topic]}"
    if not covered or ok is None:
        return ("not_stated", f"{text}. The rule ({where}) says nothing about this part.") if not covered else ("not_checked", text)
    if source == "observed_in_template":
        return ("pass" if ok else "manual"), f"{text}; the template shows {show(rule['value'])}, which no written rule states."
    return ("pass" if ok else "fail"), f"{text}; the rule: {show(rule['value'])} ({where})."


def wanted(book: dict, topic: str, key: str = ""):
    """The rule's value for topic (or one key of it), parsed; None without a stated or observed rule."""
    rule = book["rules"].get(topic)
    if not rule or rule["source"] not in ("stated", "observed_in_template"):
        return None
    value = rule["value"].get(key) if key else rule["value"]
    parse = {"page_size": page_dims, "body_size": size_pt, "line_spacing": spacing, "first_line_indent": indent}
    return None if value is None else parse.get(topic, lambda v: v)(value)


def agrees(prop: str, have, want, size=None):
    if have is None or want is None:
        return None
    if prop == "size":
        return abs(have - want) < 0.26
    if prop in ("east_asian", "latin"):
        return same_font(have, want)
    if prop == "line":
        return have[0] == want[0] and abs(have[1] - want[1]) <= (0.01 if have[0] == "multiple" else 0.1)
    to_pt = lambda v: v[1] * size if v[0] == "chars" and size else v[1] if v[0] == "pt" else None  # noqa: E731
    return None if to_pt(have) is None or to_pt(want) is None else abs(to_pt(have) - to_pt(want)) <= 1.0


def finish(directory: Path, name: str, title: str, head: list, rows: list, tail: list, extra: dict) -> int:
    counts = Counter(row[2] for row in rows)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text("\n".join([f"# {title}", "", *head, "", f"{len(rows)} rows: " + ", ".join(
        f"{counts[s]} {s}" for s in STATES) + ".", "", *table(("Check", "Where", "State", "Detail"), rows), *tail]) + "\n",
        encoding="utf-8")
    result = {"ok": counts["fail"] == 0, "counts": {s: counts[s] for s in STATES},
              "failed": [f"{r[0]}: {r[1]}" for r in rows if r[2] == "fail"],
              "not_checked": [f"{r[0]}: {r[1]}" for r in rows if r[2] == "not_checked"], **extra, "report": str(directory / name)}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def merge(rows: list) -> list:
    """Rows with the same check, state and detail become one row naming every place."""
    out = {}
    for check, where, state, detail in rows:
        out.setdefault((check, state, detail), []).append(where)
    return [(check, "; ".join(places), state, detail) for (check, state, detail), places in out.items()]


def squeeze(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(QUOTE_MARKS).translate(DASHES).replace("\u00ad", "")
    return "".join(re.sub(r"(?<=[A-Za-z])-[ \t]*\n\s*(?=[a-z])", "", text).casefold().split())


def cmd_rules(args) -> int:
    directory, book, path = Path(args.dir), load_book(args, required=True), Path(args.text)
    try:
        pages = path.read_text(encoding="utf-8-sig").split("\f")
    except (OSError, UnicodeDecodeError):
        fail(f"{path} cannot be read as UTF-8 text. Give the rules as text: pdftotext -layout rules.pdf thesis-build/rules.txt")
    pages = pages[:-1] if len(pages) > 1 and not pages[-1].strip() else pages
    squeezed = [squeeze(page) for page in pages]
    blank = [n for n, page in enumerate(pages, 1) if len(pages) > 1 and len("".join(re.sub(
        r"(?m)^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$", "", page).split())) < 20]
    rows = []
    for rule in book["record"]["rules"]:
        topic, source, quote = rule["topic"], rule["source"], str(rule.get("quote") or "")
        page = next((n for n, s in enumerate(squeezed, 1) if quote.strip() and squeeze(quote) in s), None)
        if source != "stated":
            state, detail = {"observed_in_template": ("manual", "Only seen in the template: confirm it with the user."),
                             "not_checked": ("not_checked", f"Could not be read. {rule.get('note', '')}".strip()),
                             "not_stated": ("not_stated", "The rules do not state this.")}[source]
        elif not quote.strip():
            state, detail = "fail", "No quote: copy the rule's own words from the rules text."
        elif len(re.findall(r"[A-Za-z0-9]+", quote)) < 3 and len(HAN.findall(quote)) < 6:
            state, detail = "fail", "Too short to prove anything: quote at least three words or six Chinese characters."
        elif page or squeeze(quote) in "".join(squeezed):
            state, detail = "pass", f"Quote found{f' on page {page}' if page and len(pages) > 1 else ''}."
        else:
            state, detail = "fail", "Quote not in the text: copy it again, word for word, from one place."
        pending = book["pending"].get(topic)
        rows.append((topic, rule.get("locator") or "-", state, (f"{show(rule['value'])}. " if "value" in rule else "") + detail
                     + (f" Conflict for the user to settle: {pending}" if pending else "")))
    ok = all(row[2] != "fail" for row in rows)
    tail = ["", f"Pages without a text layer: {', '.join(map(str, blank))}. Rules on them are not_checked until the user gives "
            "a text version." if blank else "Every page has text."]
    finish(directory, "rules-check.md", "Rules record check", [f"Rules text: {path} ({len(pages)} page(s)). Record: "
           f"{book['path']}."], rows, tail, {"no_text_pages": blank, "conflicts_pending": book["pending"]})
    return 0 if ok else 1


def on(element) -> bool:
    return element is not None and element.get(W + "val", "1") not in ("0", "false", "off")


def val(element, tag: str):
    child = element.find(W + tag) if element is not None else None
    return child.get(W + "val") if child is not None else None


def theme_fonts(root) -> dict:
    """(major or minor, latin or ea) -> typeface; an empty East Asian face falls back to the Hans script entry."""
    nodes = {kind: root.find(f".//{A}{kind}Font") if root is not None else None for kind in ("major", "minor")}
    return {(kind, script): (node.find(A + script).get("typeface", "") if node.find(A + script) is not None else "") or next(
        (f.get("typeface") for f in node.findall(A + "font") if script == "ea" and f.get("script") == "Hans"), "")
        for kind, node in nodes.items() if node is not None for script in ("latin", "ea")}


def rprops(rpr, theme: dict) -> dict:
    """Run properties set at one level: fonts (a theme reference wins over a name) and size."""
    out, fonts = {}, rpr.find(W + "rFonts") if rpr is not None else None
    for key, themed, plain in (("latin", "asciiTheme", "ascii"), ("east_asian", "eastAsiaTheme", "eastAsia")):
        ref = fonts.get(W + themed) if fonts is not None else None
        name = (theme.get((ref[:5], "ea" if "EastAsia" in ref else "latin")) if ref else None) or (
            fonts.get(W + plain) if fonts is not None else None)
        out.update({key: name} if name else {})
    size = number(val(rpr, "sz"))
    return {**out, "size": size / 2} if size else out


def pprops(ppr) -> dict:
    """Paragraph properties set at one level: line spacing, first-line indent, outline level, numbering."""
    out, sp, ind, num = {}, *(ppr.find(W + t) if ppr is not None else None for t in ("spacing", "ind", "numPr"))
    line, rule = (number(sp.get(W + "line")), sp.get(W + "lineRule", "auto")) if sp is not None else (None, "")
    if line:
        out["line"] = ("multiple", round(line / 240, 2)) if rule == "auto" else ("exact" if rule == "exact" else "atLeast", line / 20)
    get = ind.get if ind is not None else {}.get
    fc, hc, fl, hg = (number(get(W + a)) for a in ("firstLineChars", "hangingChars", "firstLine", "hanging"))
    if (fc is not None or hc is not None) and ((fc or hc) or (fl is None and hg is None)):
        out["indent"] = ("chars", ((fc or 0) - (hc or 0)) / 100)   # *Chars win over twips, as in Word
    elif fl is not None or hg is not None:
        out["indent"] = ("pt", ((fl or 0) - (hg or 0)) / 20)
    if number(val(ppr, "outlineLvl")) is not None:
        out["outline"] = int(number(val(ppr, "outlineLvl")))
    if num is not None:
        out["num"] = (val(num, "numId"), None if number(val(num, "ilvl")) is None else int(number(val(num, "ilvl"))))
    return out


def chain(styles: dict, sid) -> dict:
    """The own properties of a style and of the styles it is based on, the base first."""
    seen = []
    while sid in styles and sid not in seen:
        seen, sid = seen + [sid], styles[sid]["based"]
    return {k: v for s in reversed(seen) for k, v in styles[s]["own"].items()}


def fields(root) -> tuple:
    """(field codes, field marks without a partner) of one part, in document order."""
    stack, codes, loose = [], [], 0
    for el in root.iter() if root is not None else ():
        kind = el.get(W + "fldCharType") if el.tag == W + "fldChar" else None
        if kind == "begin":
            stack.append([])
        elif kind == "end":
            codes, loose = (codes + ["".join(stack.pop()).strip()], loose) if stack else (codes, loose + 1)
        elif el.tag == W + "instrText" and stack:
            stack[-1].append(el.text or "")
        elif el.tag == W + "fldSimple":
            codes.append(el.get(W + "instr", "").strip())
    return codes, loose + len(stack)


def paragraphs(body, defaults: dict, styles: dict, theme: dict) -> list:
    boxed = {id(e) for box in body.iter(W + "txbxContent") for e in box.iter()}
    tabled = {id(p) for t in body.iter(W + "tbl") for p in t.iter(W + "p")}
    default = next((sid for sid, s in styles.items() if s["type"] == "paragraph" and s["default"]), None)
    out, section, run_keys = [], 0, ("latin", "east_asian", "size")
    for p in (p for p in body.iter(W + "p") if id(p) not in boxed):
        ppr = p.find(W + "pPr")
        sid = val(ppr, "pStyle") or default
        style_eff, runs = {**defaults, **chain(styles, sid)}, []
        for r in p.iter(W + "r"):
            text = "".join(t.text or "" if t.tag == W + "t" else " " for t in r if t.tag in (W + "t", W + "tab"))
            if id(r) not in boxed and text.strip():
                rpr, direct = r.find(W + "rPr"), rprops(r.find(W + "rPr"), theme)
                inherited = {k: v for k, v in {**style_eff, **chain(styles, val(rpr, "rStyle"))}.items() if k in run_keys}
                runs.append((text, {**inherited, **direct}, direct))
        name, eff = styles.get(sid, {}).get("name") or "", {**style_eff, **pprops(ppr)}
        m = re.fullmatch(r"(?:heading|标题)\s*(\d)", name.strip(), re.I)
        level = eff.get("outline") if eff.get("outline") is not None else int(m.group(1)) - 1 if m else None
        out.append({"n": len(out) + 1, "style": sid, "name": name, "style_eff": style_eff, "eff": eff, "runs": runs,
                    "table": id(p) in tabled, "section": section, "level": level if level is not None and level < 9 else None,
                    "text": unicodedata.normalize("NFKC", "".join(t for t, _, _ in runs)).strip()})
        section += ppr is not None and ppr.find(W + "sectPr") is not None
    return out


def read_docx(path: Path) -> dict:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        fail(f"{path} cannot be read as a .docx ({exc}). Save it from Word as .docx.")
    cache = {}

    def part(name):
        if name and name not in cache:
            try:
                cache[name] = ET.fromstring(archive.read(name))
            except KeyError:
                cache[name] = None
            except ET.ParseError as exc:
                fail(f"{path}: {name} is not well-formed XML ({exc}).")
        return cache.get(name)

    with archive:
        doc = part("word/document.xml")
        body = doc.find(W + "body") if doc is not None else None
        if body is None:
            fail(f"{path} has no Word body (word/document.xml in the transitional format). Save it from Word as .docx.")
        rels = {rel.get("Id"): (rel.get("Type", "").rsplit("/", 1)[-1], rel.get("Target", "").lstrip("/")
                                if rel.get("Target", "").startswith("/") else "word/" + rel.get("Target", ""))
                for rel in (part("word/_rels/document.xml.rels") if part("word/_rels/document.xml.rels") is not None else [])}
        theme = theme_fonts(part(next((t for kind, t in rels.values() if kind == "theme"), None)))
        root, nroot, settings = part("word/styles.xml"), part("word/numbering.xml"), part("word/settings.xml")
        dd = root.find(W + "docDefaults") if root is not None else None
        defaults = {} if dd is None else {**rprops(dd.find(f"{W}rPrDefault/{W}rPr"), theme), **pprops(dd.find(f"{W}pPrDefault/{W}pPr"))}
        styles = {st.get(W + "styleId"): {"type": st.get(W + "type"), "name": val(st, "name"), "based": val(st, "basedOn"),
                                          "default": st.get(W + "default") in ("1", "true", "on"),
                                          "own": {**rprops(st.find(W + "rPr"), theme), **pprops(st.find(W + "pPr"))}}
                  for st in (root.findall(W + "style") if root is not None else [])}
        abstract = {node.get(W + "abstractNumId"): {int(number(lvl.get(W + "ilvl")) or 0): (val(lvl, "numFmt") or "decimal",
                    val(lvl, "lvlText") or "") for lvl in node.findall(W + "lvl")}
                    for node in (nroot.findall(W + "abstractNum") if nroot is not None else [])}
        numbering = {num.get(W + "numId"): abstract.get(val(num, "abstractNumId"))
                     for num in (nroot.findall(W + "num") if nroot is not None else [])}
        flag = lambda name: settings is not None and on(settings.find(W + name))  # noqa: E731
        sects = [p.find(f"{W}pPr/{W}sectPr") for p in body.iter(W + "p") if p.find(f"{W}pPr/{W}sectPr") is not None]
        sects.append(body.find(W + "sectPr") if body.find(W + "sectPr") is not None else ET.Element(W + "sectPr"))
        current, shows = {}, []
        for sect in sects:   # a section without its own header or footer of a type uses the previous one's
            current.update({(ref.tag, ref.get(W + "type", "default")): rels.get(ref.get(R_ID), ("", None))[1] for ref in sect
                            if ref.tag in (W + "headerReference", W + "footerReference")})
            kinds = ["default"] + ["first"] * on(sect.find(W + "titlePg")) + ["even"] * flag("evenAndOddHeaders")
            names = {current.get((tag, k)) for tag in (W + "headerReference", W + "footerReference") for k in kinds} - {None}
            shows.append(any(re.search(r"\bPAGE\b", " ".join(fields(part(name))[0])) for name in names))
        d = {"paras": paragraphs(body, defaults, styles, theme), "styles": styles, "defaults": defaults, "numbering": numbering,
             "fields": fields(doc), "mirror": flag("mirrorMargins"), "gutter_top": flag("gutterAtTop"), "sections": []}
    for i, sect in enumerate(sects):
        get = lambda tag, attr: number(sect.find(W + tag).get(W + attr)) if sect.find(W + tag) is not None else None  # noqa: E731
        ns, pn = [p["n"] for p in d["paras"] if p["section"] == i] or [0], sect.find(W + "pgNumType")
        d["sections"].append({"size": tuple(None if get("pgSz", k) is None else get("pgSz", k) * TWIP for k in ("w", "h")),
                              "mar": {k: abs(get("pgMar", k) or 0) * TWIP for k in ("top", "bottom", "left", "right", "gutter")},
                              "fmt": (pn.get(W + "fmt") if pn is not None else None) or "decimal",
                              "start": number(pn.get(W + "start")) if pn is not None else None,
                              "paras": spans(range(ns[0], ns[-1] + 1)), "first": ns[0], "last": ns[-1],
                              "shows": shows[i]})
    return d


def numbered(p: dict, numbering: dict):
    """True when Word shows an automatic number before the paragraph, False when not, None when unknown."""
    num = p["eff"].get("num")
    if not num or num[0] in (None, "0"):
        return False
    levels, ilvl = numbering.get(num[0]), num[1] if num[1] is not None else (p["level"] or 0)
    return None if not levels or ilvl not in levels else levels[ilvl][0] != "none" and bool(levels[ilvl][1])


def style_name(styles: dict, sid) -> str:
    name = styles.get(sid, {}).get("name") or str(sid)
    return name if name == sid or sid is None else f"{name} ({sid})"


def classify(paras: list, start) -> None:
    refs = None
    for p in paras:
        if p["level"] is not None and p["text"]:
            refs = None if refs is not None and p["level"] <= refs else refs
            refs = p["level"] if re.sub(r"[\W\d_]+", "", p["text"]).casefold() in REFERENCE_HEADINGS else refs
        caption = re.search(r"caption|题注", p["name"], re.I) or re.match(r"(?:图|表|figure|fig\.|table)\s*\d", p["text"], re.I)
        p["kind"] = ("heading" if p["level"] is not None else "table" if p["table"] else "toc" if re.match(r"toc|目录", p["name"], re.I)
                     else "caption" if caption else "references" if refs is not None else "front" if start and p["n"] < start
                     else "body" if p["text"] else "empty")


def dominant(p: dict, prop: str, pattern=None):
    """The paragraph's value of prop; for run properties, the one that carries the most characters."""
    if prop in ("line", "indent"):
        return p["eff"].get(prop)
    counts = Counter()
    for text, eff, _ in p["runs"]:
        counts[eff.get(prop)] += len(pattern.findall(text)) if pattern else len("".join(text.split()))
    return (+counts).most_common(1)[0][0] if +counts else None


def margin_targets(book: dict) -> tuple:
    """The rule's distance from the paper edge to the text per side (the gutter added to the binding side), and that side."""
    rule = wanted(book, "margins") or {}
    gutter = length_mm(rule.get("gutter", "0 mm"))
    want = {k: length_mm(v) + gutter * (k in ("inside", "left")) for k, v in rule.items() if k != "gutter"}
    return want, "inside" if {"inside", "outside"} & set(want) else "left"


def section_rows(book: dict, d: dict) -> list:
    (want, bind), rows, dims = margin_targets(book), [], wanted(book, "page_size")
    for i, s in enumerate(d["sections"], 1):
        where, (w, h), mar = f"section {i} ({s['paras']})", s["size"], s["mar"]
        turned = bool(w and h and w > h)   # a landscape section of the rule's paper has its sides swapped
        fits = None if dims is None or not (w and h) else abs(w - dims[turned]) <= 0.5 and abs(h - dims[not turned]) <= 0.5
        rows.append(("page_size", where, *judge(book, "page_size", fits, f"{w or 0:.1f} × {h or 0:.1f} mm" + ", landscape" * turned)))
        have = {"top": mar["top"], "bottom": mar["bottom"], "left": mar["left"], "inside": mar["left"], "right": mar["right"],
                "outside": mar["right"]}
        for k in ("top",) if d["gutter_top"] else ("left", "inside"):
            have[k] += mar["gutter"]
        off = [f"{k} {have[k]:.1f} (rule {v:.1f})" for k, v in want.items() if abs(have[k] - v) > 0.5]
        state, detail = judge(book, "margins", not off if want else None, ", ".join(f"{k} {v:.1f}" for k, v in mar.items()) + " mm"
                              + ("; distance from the edge to the text differs: " + ", ".join(off) if off else ""))
        note = (" A landscape section: which side binds depends on how the page is turned." if turned else
                " The rule names inside and outside, but the document does not mirror its margins." if bind == "inside"
                and not d["mirror"] else "") if state in ("pass", "fail") and want and (turned or bind == "inside") else ""
        rows.append(("margins", where, "manual" if note else state, detail + note))
    return merge(rows)


def number_rows(book: dict, d: dict, start) -> list:
    value = wanted(book, "page_numbers") or {}
    if start is None:
        return [("page_numbers", "document", "not_checked", "Chapter 1 not found: give --main-starts <¶ number>.")]
    secs = list(enumerate(d["sections"], 1))
    first = next((i for i, s in secs if s["last"] >= start), len(secs))
    shared = secs[first - 1][1]["first"] < start   # no section break before chapter 1: the front matter shares its numbering
    kind = lambda s: "roman" if "roman" in s["fmt"].lower() else "arabic" if s["fmt"] == "decimal" else s["fmt"]  # noqa: E731
    front, want = [(i, s) for i, s in secs[:first - 1 + shared] if s["shows"]], value.get("front_matter")
    bad = [i for i, s in front if want and (want == "none" or kind(s) != want)]
    rows = [("page_numbers.front", spans(range(1, first + shared), "sections ") or "none", *judge(book, "page_numbers", not bad,
             "front matter: " + ("; ".join(f"section {i}: {kind(s)}" for i, s in front) or "no page number shown"), bool(want)))]
    (i, s), mains, want_main, want_start = secs[first - 1], secs[first - 1:], value.get("main_matter"), value.get("main_starts_at")
    begin = s["start"] if s["start"] is not None else (1 if i == 1 else None)
    problems = [f"section {i} shows no page number"] * (not s["shows"]) + [f"chapter 1 shares section {i} with the front matter, "
                                                                          "so its numbering cannot start anew"] * shared
    if want_start is not None and begin != want_start and not shared:
        problems.append(f"section {i} starts at {begin:g}" if begin is not None else
                        f"section {i} continues the numbering of the section before instead of starting at {want_start}")
    for j, t in mains:
        problems += [f"section {j} uses {kind(t)}"] * bool(want_main and t["shows"] and kind(t) != want_main)
        problems += [f"section {j} ({t['paras']}) restarts at {t['start']:g}"] if t["start"] is not None and j > i else []
    summary = "; ".join(f"section {j}: {kind(t)}" + (f" from {t['start']:g}" if t["start"] is not None else "") for j, t in mains)
    rows.append(("page_numbers.main", f"sections {first}–{len(secs)}", *judge(book, "page_numbers", not problems,
                 "; ".join([f"main matter: {summary}", *problems]), bool(want_main) or want_start is not None)))
    return rows + [("page_numbers.position", "document", "manual", "Measured on pages: see pdf.")] * bool(value.get("position"))


def body_rows(book: dict, d: dict, start) -> list:
    paras, styles = d["paras"], d["styles"]
    body, rows = [p for p in paras if p["kind"] == "body"], []
    if not body:
        return [("body_text", "document", "not_checked", "No body paragraphs found in the main matter.")]
    sid = max({p["style"] for p in body}, key=lambda s: sum(len(p["text"]) for p in body if p["style"] == s))
    seff = next(p["style_eff"] for p in body if p["style"] == sid)
    scope = f"{len(body)} body paragraphs of the " + ("main matter" if start else "whole document (chapter 1 not found)")
    for topic, prop, pattern in (("body_size", "size", None), ("body_font", "east_asian", HAN), ("body_font", "latin", LATIN),
                                 ("line_spacing", "line", None), ("first_line_indent", "indent", None)):
        check = f"body_font.{prop}" if topic == "body_font" else topic
        want, have = wanted(book, topic, prop if topic == "body_font" else ""), seff.get(prop)
        rows.append((check, f"style {style_name(styles, sid)}", *judge(book, topic, agrees(prop, have, want, seff.get("size")),
                     f"{show(have, prop)} in the style of most of the {scope}", want is not None)))
        odd = [p for p in body if prop != "indent" and (not pattern or pattern.search(p["text"]))
               and agrees(prop, dominant(p, prop, pattern), want if want is not None else have) is False]
        if odd:
            seen = Counter(show(dominant(p, prop, pattern), prop) for p in odd)
            state, detail = judge(book, topic, False, f"{len(odd)} body paragraph(s) in " + ", ".join(
                f"{v} ({n})" for v, n in seen.most_common(3)) + f", first “{odd[0]['text'][:24]}…”", want is not None)
            rows.append((check, spans([p["n"] for p in odd]), state, detail))
    return rows


def heading_rows(d: dict) -> list:
    heads = [p for p in d["paras"] if p["kind"] == "heading" and p["text"]]
    if not heads:
        return [("headings", "document", "not_checked", "No headings: no paragraph has an outline level or a heading style.")]
    skips, typed, unsure, prev = [], [], [], None
    for p in heads:
        if prev is not None and p["level"] > prev + 1:
            skips.append(f"¶ {p['n']} “{p['text'][:30]}” is level {p['level'] + 1} after level {prev + 1}")
        prev, auto = p["level"], numbered(p, d["numbering"]) if TYPED_NUMBER.match(p["text"]) else False
        (typed if auto else unsure if auto is None else []).append(f"¶ {p['n']} “{p['text'][:30]}”")
    (codes, loose), toc = d["fields"], any(code.upper().startswith("TOC") for code in d["fields"][0])
    return [("heading_levels", f"{len(heads)} headings", "fail" if skips else "pass", "; ".join(skips[:10]) or "No level is skipped."),
            ("typed_heading_numbers", f"{len(heads)} headings", "fail" if typed else "manual" if unsure else "pass", "; ".join(
                typed[:10]) + ": typed on automatic numbering, so Word shows both" if typed else "; ".join(unsure[:10]) + ": typed, "
             "and the numbering definition could not be read" if unsure else "No number is typed on automatic numbering."),
            ("contents_field", "document body", "pass" if toc else "manual", "A TOC field builds the contents list." if toc
             else "No TOC field: a typed contents list does not follow the headings. Check it by eye, or insert one."),
            ("field_balance", "document body", "fail" if loose else "pass", f"{loose} field mark(s) without a partner: a field "
             "was cut when text was pasted. Repair it in Word and look at what it held." if loose else
             f"{len(codes)} field(s); each field that begins also ends.")]


def cmd_docx(args) -> int:
    directory, book = Path(args.dir), load_book(args)
    d = read_docx(Path(args.docx))
    start = args.main_starts or next((p["n"] for p in d["paras"] if p["level"] == 0 and p["text"] and not p["table"]
                                      and (CHAPTER_ONE.match(p["text"]) or numbered(p, d["numbering"]))), None)
    classify(d["paras"], start)
    rows = [*section_rows(book, d), *number_rows(book, d, start), *body_rows(book, d, start), *heading_rows(d)]
    used = [(style_name(d["styles"], sid), count, *(show(eff.get(k), k) for k in ("east_asian", "latin", "size", "line", "indent")),
             "" if eff.get("outline") is None else eff["outline"] + 1, spans([p["n"] for p in d["paras"] if p["style"] == sid and any(
                 k in r[2] and not agrees(k, r[2][k], eff.get(k)) for r in p["runs"] for k in ("size", "east_asian", "latin"))]))
            for sid, count in Counter(p["style"] for p in d["paras"] if p["text"]).most_common()
            for eff in [next(p["style_eff"] for p in d["paras"] if p["style"] == sid)]]
    tail = ["", "## Paragraph styles in use", "", "Resolved through document defaults and the basedOn chain (table styles are "
            "not). The last column lists paragraphs whose direct font or size formatting overrides the style.", "",
            *table(("Style", "¶", "East Asian", "Latin", "Size", "Line spacing", "First line", "Level", "Overridden in"), used),
            "", "Read from the file's XML: Word may render it differently from LibreOffice."]
    head = [f"Document: {args.docx} ({len(d['paras'])} paragraphs, {len(d['sections'])} sections). Chapter 1 starts at "
            + (f"¶ {start}." if start else "no paragraph found (give --main-starts)."), f"Rules: {book['path'] or 'none'}."]
    return finish(directory, "docx-check.md", "Word file check", head, rows, tail, {"main_starts": start})


def pymupdf():
    return next((importlib.import_module(n) for n in ("pymupdf", "fitz") if importlib.util.find_spec(n)), None)


def band(page: dict, line: dict):
    return "top" if line["box"][1] <= BAND * page["h"] else "bottom" if line["box"][3] >= (1 - BAND) * page["h"] else None


def page_label(page: dict):
    """The page number printed in the top or bottom band (a bottom one wins), with its kind and place."""
    found = [(band(page, line) == "bottom", m.group(1), line) for line in page["lines"] if band(page, line)
             for m in [PAGE_LABEL.match(line["text"])] if m and (m.group(1).isdigit() or ROMAN.match(m.group(1)))]
    if not found:
        return None
    bottom, token, line = max(found, key=lambda f: f[0])
    x, digits = (line["box"][0] + line["box"][2]) / 2, [ROMAN_VALUES[c] for c in token.lower() if not token.isdigit()]
    value = int(token) if token.isdigit() else sum(-v if i + 1 < len(digits) and v < digits[i + 1] else v for i, v in enumerate(digits))
    return {"kind": "arabic" if token.isdigit() else "roman", "value": value, "text": token, "line": line,
            "vertical": "bottom" if bottom else "top",
            "horizontal": "center" if abs(x - page["w"] / 2) < 0.1 * page["w"] else "left" if x < page["w"] / 2 else "right"}


def read_pages(doc) -> list:
    pages = []
    for page in doc:
        lines = [{"box": tuple(line["bbox"]), "spans": parts, "text": unicodedata.normalize("NFKC", "".join(
            s["text"] for s in parts)).strip()} for block in page.get_text("dict").get("blocks", []) for line in block.get("lines", [])
                 for parts in [[s for s in line.get("spans", []) if s.get("text", "").strip()]] if parts]
        pages.append({"n": page.number + 1, "w": page.rect.width, "h": page.rect.height, "lines": lines,
                      "images": [tuple(i["bbox"]) for i in page.get_image_info()], "turned": page.rotation != 0})
    head = lambda p, line: (band(p, line), re.sub(r"[\d\s]+", "", line["text"]).casefold())  # noqa: E731
    seen = Counter(key for p in pages for key in {head(p, line) for line in p["lines"] if band(p, line)})
    for p in pages:   # running heads: the same text in the same band on several pages; they and the number are not body
        p["label"] = page_label(p)
        p["body"] = [line for line in p["lines"] if not (p["label"] and line is p["label"]["line"])
                     and not (band(p, line) and seen[head(p, line)] >= (3 if len(pages) >= 6 else 2))]
    return pages


def margin_rows(book: dict, pages: list, tol: float) -> list:
    want, _ = margin_targets(book)
    turned, rows, seen = [], [], {s: [] for s in want or ("top", "bottom", "left", "right")}
    for p in pages:
        boxes = [line["box"] for line in p["body"]] + p["images"]
        if boxes and (p["turned"] or p["w"] > p["h"]):
            turned.append(p["n"])
        elif boxes:
            x0, y0, x1, y1 = (f(b[i] for b in boxes) for f, i in ((min, 0), (min, 1), (max, 2), (max, 3)))
            left, right, odd = max(x0, 0) * MM, max(p["w"] - x1, 0) * MM, p["n"] % 2 == 1
            have = {"top": max(y0, 0) * MM, "bottom": max(p["h"] - y1, 0) * MM, "left": left, "right": right,
                    "inside": left if odd else right, "outside": right if odd else left}
            for s in seen:
                seen[s].append((p["n"], have[s]))
    for s, values in ((s, v) for s, v in seen.items() if v):
        near_n, near = min(values, key=lambda item: item[1])
        into, wider = [n for n, v in values if s in want and v < want[s] - tol], s in want and near > want[s] + tol
        state, detail = judge(book, "margins", not into if s in want else None, f"text {near:.1f} mm from the {s} edge (p. {near_n})"
                              + (f", rule {want[s]:.1f} mm" if s in want else "") + (". No page's text comes within "
                              f"{tol:g} mm of the margin; ink gives only a lower bound, so the margin may be set wider: check "
                              "the page setup" if wider and not into else ""), bool(want) or s in want)
        rows.append((f"margins.{s}", spans(into, "pp. ") if into else f"{len(values)} pages", "manual" if state == "pass"
                     and wider else state, detail))
    return rows + [("margins", spans(turned, "pp. "), "manual", "Landscape or rotated pages: which side binds depends on how "
                    "the page is turned. Check them by eye.")] * bool(turned)


def text_rows(book: dict, pages: list) -> tuple:
    sizes, fonts, per_page = Counter(), Counter(), {}
    for p in pages:
        per_page[p["n"]] = here = Counter()
        for s in (s for line in p["body"] for s in line["spans"]):
            size, name = round(s["size"] * 2) / 2, re.sub(r"^[A-Z]{6}\+", "", s["font"])
            here[size] += len("".join(s["text"].split()))
            fonts[("east_asian", size, name)] += len(HAN.findall(s["text"]))
            fonts[("latin", size, name)] += len(re.findall(r"[A-Za-z]", s["text"]))
        sizes.update(here)
    if not sizes:
        return [(c, "PDF", "not_checked", "The PDF has no text layer (scanned pages?).") for c in ("body_size", "body_font")], None
    body, chars = sizes.most_common(1)[0]
    rows = [("body_size", f"{len(pages)} pages", *judge(book, "body_size", agrees("size", body, wanted(book, "body_size")),
             f"{body:g} pt carries {100 * chars / sum(sizes.values()):.0f}% of the characters"))]
    other = [n for n, c in per_page.items() if sum(c.values()) >= 200 and c.most_common(1)[0][0] != body]
    rows += [("body_size", spans(other, "pp. "), "manual", "Mostly " + ", ".join(f"{s:g} pt" for s in Counter(
        per_page[n].most_common(1)[0][0] for n in other)) + ": a chapter in another size, or tables, references or captions. "
        "Look at these pages.")] * bool(other)
    for prop in ("east_asian", "latin"):
        found = Counter({name: n for (k, size, name), n in fonts.items() if k == prop and size == body and n})
        want, name = wanted(book, "body_font", prop), found.most_common(1)[0][0] if found else None
        state, detail = judge(book, "body_font", agrees(prop, name, want), f"{name} at the body size" if name else
                              f"no {'Chinese' if prop == 'east_asian' else 'Latin'} text at {body:g} pt", want is not None)
        rows.append((f"body_font.{prop}", f"{len(pages)} pages", "manual" if state == "fail" else state, detail + (
            " A PDF may carry another name for the same face, or a substitute: compare by eye." if state == "fail" else "")))
    return rows, body


def pdf_main_start(pages: list, body):
    """The first page with a chapter-1 heading larger than the body text, skipping contents pages (dot leaders)."""
    return next((p["n"] for p in pages if body and sum(bool(LEADER.search(line["text"])) for line in p["body"]) < 3 and any(
        CHAPTER_ONE.match(line["text"]) and max(s["size"] for s in line["spans"]) >= body + 1 for line in p["body"])), None)


def pdf_number_rows(book: dict, pages: list, start) -> list:
    value, labelled = wanted(book, "page_numbers") or {}, [(p["n"], p["label"]) for p in pages if p["label"]]
    describe = lambda items: ", ".join(f"p. {n}: {l['text']}" for n, l in items[:6]) + (" …" if len(items) > 6 else "")  # noqa: E731
    if start is None:
        return [("page_numbers", "PDF", "not_checked", "Chapter 1 not found: give --main-starts <PDF page>. Numbers found: "
                 + (describe(labelled) or "none") + ".")]
    front, main = [x for x in labelled if x[0] < start], [x for x in labelled if x[0] >= start]
    want, want_main, want_start = value.get("front_matter"), value.get("main_matter"), value.get("main_starts_at")
    bad = [n for n, l in front if want and (want == "none" or l["kind"] != want)]
    rows = [("page_numbers.front", spans(range(1, start), "pp. ") if start > 1 else "none", *judge(book, "page_numbers", not bad,
             f"front matter: {describe(front) or 'none'}" + (f"; not {want} on {spans(bad, 'pp. ')}" if bad else ""), bool(want)))]
    problems = [f"p. {n} shows {l['text']} ({l['kind']})" for n, l in main if want_main and l["kind"] != want_main][:5]
    arabic, runs = [(n, l["value"]) for n, l in main if l["kind"] == "arabic"], []
    base_n, base_v = (start, want_start) if want_start is not None else arabic[0] if arabic else (0, 0)
    for n, v in arabic:   # consecutive pages that keep the same offset from the expected number form one run
        off = v - (base_v + n - base_n)
        if runs and runs[-1][4] == off:
            runs[-1][1], runs[-1][3] = n, v
        else:
            runs.append([n, n, v, v, off])
    problems += [f"{spans(range(a, b + 1), 'pp. ')} show {va}–{vb} where the sequence from p. {base_n} gives {va - off}–{vb - off}"
                 for a, b, va, vb, off in runs if off]
    rows.append(("page_numbers.main", spans(range(start, len(pages) + 1), "pp. "), *judge(book, "page_numbers", not problems,
                 f"main matter: {describe(main) or 'no page number'}" + ("; " + "; ".join(problems) if problems else ""),
                 bool(want_main) or want_start is not None)))
    words = str(value.get("position", "")).lower().split()
    if words:
        side = lambda n, w: {"outside": "right" if n % 2 else "left", "inside": "left" if n % 2 else "right"}.get(w, w)  # noqa: E731
        bad = [n for n, l in labelled if any(l["vertical" if w in ("top", "bottom") else "horizontal"] != side(n, w) for w in words)]
        rows.append(("page_numbers.position", spans(bad, "pp. ") if bad else f"{len(labelled)} pages", *judge(book, "page_numbers",
                     not bad, f"{len(bad)} of {len(labelled)} numbers elsewhere" if bad else f"all {len(labelled)} numbers in place")))
    return rows


def cmd_pdf(args) -> int:
    directory, book, path, fz = Path(args.dir), load_book(args), Path(args.pdf), pymupdf()
    if not path.is_file():
        fail(f"no such file: {path}")
    if fz is None:
        why = "PyMuPDF is not installed (neither import pymupdf nor import fitz works): install pymupdf, or check this by eye."
        rows = [(c, path.name, "not_checked", why) for c in ("page_size", "margins", "body_size", "body_font", "page_numbers",
                                                              "fonts_embedded")]
        return finish(directory, "pdf-check.md", "PDF check", [f"PDF: {path}"], rows, [], {"pymupdf": False})
    try:
        doc = fz.open(str(path))
        pages = read_pages(doc)
    except Exception as exc:   # PyMuPDF raises its own error types
        fail(f"{path} cannot be read as a PDF ({exc}).")
    dims, groups, tol = wanted(book, "page_size"), {}, args.tolerance_mm
    fits = lambda a, b: dims is not None and abs(a - dims[0]) <= tol and abs(b - dims[1]) <= tol  # noqa: E731
    for p in pages:
        w, h = p["w"] * MM, p["h"] * MM
        key = ("manual", f"{w:.1f} × {h:.1f} mm: landscape pages of the rule's paper") if fits(h, w) and not fits(w, h) else \
            judge(book, "page_size", None if dims is None else fits(w, h), f"{w:.1f} × {h:.1f} mm")
        groups.setdefault(key, []).append(p["n"])
    found, body = text_rows(book, pages)
    start = args.main_starts or pdf_main_start(pages, body)
    rows = [("page_size", spans(ns, "pp. "), state, detail) for (state, detail), ns in groups.items()]
    rows += margin_rows(book, pages, tol) + found + pdf_number_rows(book, pages, start)
    loose = {}
    for i, font in ((i, f) for i in range(doc.page_count) for f in doc.get_page_fonts(i) if f[1] == "n/a" and f[2] != "Type3"):
        loose.setdefault(re.sub(r"^[A-Z]{6}\+", "", font[3]), []).append(i + 1)
    rows.append(("fonts_embedded", f"{len(pages)} pages", "fail" if loose else "pass", "Not embedded: " + "; ".join(
        f"{name} ({spans(ns, 'pp. ')})" for name, ns in loose.items()) + ". Other machines show another font: export again "
        "with fonts embedded." if loose else "Every font is embedded."))
    head = [f"PDF: {path} ({len(pages)} pages); chapter 1 on page {start or 'not found (give --main-starts)'}; rules: "
            f"{book['path'] or 'none'}. The measurements hold for this PDF only; odd pages are taken as right-hand pages."]
    return finish(directory, "pdf-check.md", "PDF check", head, rows, [], {"pages": len(pages), "main_starts": start})


def cmd_compare(args) -> int:
    t, d = read_docx(Path(args.template)), read_docx(Path(args.thesis))
    rows, has_num = [], lambda e: bool(e.get("num")) and e["num"][0] not in (None, "0")
    for sid, count in Counter(p["style"] for p in d["paras"] if p["text"]).most_common():
        where, mine = f"{style_name(d['styles'], sid)} ({count} ¶)", {**d["defaults"], **chain(d["styles"], sid)}
        if sid not in t["styles"]:
            rows.append(("style_added", where, "manual", "Not in the template, probably brought in with a paper: give its "
                                                         "paragraphs a template style."))
            continue
        theirs = {**t["defaults"], **chain(t["styles"], sid)}
        diffs = [f"{label} {show(theirs.get(k), k)} → {show(mine.get(k), k)}" for k, label in (
            ("east_asian", "East Asian font"), ("latin", "Latin font"), ("size", "size"), ("line", "line spacing"),
            ("indent", "first line"), ("outline", "outline")) if theirs.get(k) != mine.get(k)]
        diffs += ["automatic numbering " + ("removed" if has_num(theirs) else "added")] * (has_num(theirs) != has_num(mine))
        rows.append(("style", where, "manual" if diffs else "pass", "; ".join(diffs) or "Same as the template."))
    setup = lambda s: tuple(None if v is None else round(v * 2) / 2 for v in (*s["size"], *s["mar"].values()))  # noqa: E731
    for i, s in enumerate(d["sections"], 1):
        known, paper = setup(s) in {setup(x) for x in t["sections"]}, " × ".join(f"{v:.1f}" for v in s["size"] if v is not None)
        rows.append(("section", f"section {i} ({s['paras']})", "pass" if known else "manual", f"paper {paper} mm, margins " + ", ".join(
            f"{k} {v:.1f}" for k, v in s["mar"].items()) + " mm" + ("" if known else "; not a page setup of the template")))
    finish(Path(args.dir), "compare.md", "Template comparison", [f"Template: {args.template}. Thesis: {args.thesis}. A difference "
           "is manual: the template may be older than the written rules, which decide."], merge(rows), [], {})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure a thesis against the school's recorded rules.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="thesis-build", help="Folder for the reports (default: thesis-build)")
    common.add_argument("--rules", help="The rules record (default: <dir>/rules.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rules", parents=[common], help="Check that every quote of rules.json is in the rules text").add_argument(
        "text", help="The rules as UTF-8 text; pdftotext -layout keeps the page breaks")
    for name, what in (("docx", "the thesis as .docx"), ("pdf", "the PDF the user exported")):
        p = sub.add_parser(name, parents=[common], help=f"Measure {what} against rules.json")
        p.add_argument(name, help=what)
        p.add_argument("--main-starts", type=int, help="Where chapter 1 begins: " + ("¶ number" if name == "docx" else "PDF page"))
    p.add_argument("--tolerance-mm", type=float, default=TOLERANCE_MM, help="A convention; default 1 mm")
    p = sub.add_parser("compare", parents=[common], help="Styles in use and sections that differ from the template")
    p.add_argument("template"), p.add_argument("thesis")
    args = parser.parse_args(argv)
    return {"rules": cmd_rules, "docx": cmd_docx, "pdf": cmd_pdf, "compare": cmd_compare}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
