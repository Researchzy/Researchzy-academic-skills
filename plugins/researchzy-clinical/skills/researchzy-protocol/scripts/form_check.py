#!/usr/bin/env python3
"""Prove that a filled copy of an institution's Word form changed only the places that were declared.

  form_check.py compare FORM.docx FILLED.docx [--fill protocol/form-fill.json] [--dir protocol]
  form_check.py compare FORM.docx FORM.docx      before filling: every label and place must be found

form-fill.json lists each field: the label as the form prints it, the place of the answer (right: the next cell of
the label's row; below: the cell under the label; after: the body paragraphs after the label, up to the
paragraph `until`, which stays) and the value as a JSON string (references/forms-and-amendments.md). Labels match
after NFKC (full-width brackets and colons equal ASCII ones), ignoring case, spaces and a final colon.

Rows: label (found once), place (exists, is not the hidden part of a vertical merge, holds no other field's
label), label_kept, value (reads exactly the declared string), raw_newline (no line break typed inside a w:t,
which Word shows as a space), fonts (Latin and East Asian font and size of every filled run, resolved through
document defaults, the basedOn chain, character styles and the theme, equal the form's at that place), styles,
numbering, sections (every sectPr, header references by what they point at), headers_footers (each part, with
its images), outside (every block outside the places, cell properties included), pages (both files rendered by
LibreOffice; not_checked without it). Session ids, proofing marks and rendered page breaks are ignored.
Writes form-check.md in --dir and prints a JSON summary. States: pass, fail, manual (a person looks),
not_checked. Exit code 0 when nothing failed, 1 when a row fails, 2 when a file cannot be read or form-fill.json
is not in the documented format. Standard library only; pages runs soffice when it is installed.
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
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PLACES = ("right", "below", "after")
STATES = ("pass", "fail", "manual", "not_checked")
NOISE = {W + "proofErr", W + "lastRenderedPageBreak", W + "rsid"}
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")
LATIN = re.compile(r"[A-Za-z0-9]")
ALIASES = {"宋体": "simsun", "新宋体": "nsimsun", "黑体": "simhei", "楷体": "kaiti", "仿宋": "fangsong", "等线": "dengxian",
           "微软雅黑": "microsoftyahei"}


def fail(message: str):
    print(f"form_check: {message}", file=sys.stderr)
    raise SystemExit(2)


def key(text: str) -> str:
    """A label as matched: NFKC (full-width brackets and colons become ASCII), no case, no spaces, no final colon."""
    return "".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip(":")


def snip(text: str, size: int = 50) -> str:
    text = " ".join(text.split())
    return text if len(text) <= size else text[:size - 1] + "…"


def val(el, path: str):
    node = el.find(path) if el is not None else None
    return node.get(W + "val") if node is not None else None


def tree(d: dict, name):
    if name not in d["trees"]:
        try:
            d["trees"][name] = ET.fromstring(d["parts"][name]) if name in d["parts"] else None
        except ET.ParseError as exc:
            fail(f"{d['path']}: {name} is not well-formed XML ({exc}).")
    return d["trees"][name]


def rels(d: dict, name, compared: bool = False) -> dict:
    """{relationship id: target part} of one part. As compared, an image is named by its content too."""
    folder, base = posixpath.split(name or "")
    root, out = tree(d, posixpath.join(folder, "_rels", base + ".rels") if name else None), {}
    for rel in root if root is not None else []:
        target = rel.get("Target", "")
        t = target if rel.get("TargetMode") == "External" else posixpath.normpath(
            target.lstrip("/") if target.startswith("/") else posixpath.join(folder, target))
        out[rel.get("Id")] = f"{t}#{hashlib.sha256(d['parts'][t]).hexdigest()[:12]}" if compared and t in d["parts"] and not \
            t.endswith(".xml") else t
    return out


def theme_fonts(root) -> dict:
    """(major or minor, latin or ea) -> typeface; an empty East Asian face falls back to the Hans script entry."""
    out = {}
    for kind in ("major", "minor"):
        node = root.find(f".//{A}{kind}Font") if root is not None else None
        for script in ("latin", "ea") if node is not None else ():
            face = node.find(A + script)
            out[(kind, script)] = (face.get("typeface", "") if face is not None else "") or next(
                (f.get("typeface") for f in node.findall(A + "font") if script == "ea" and f.get("script") == "Hans"), "")
    return out


def rprops(rpr, theme: dict) -> dict:
    """Fonts and size set at one level; a theme reference wins over a font name, as in Word."""
    out, fonts = {}, rpr.find(W + "rFonts") if rpr is not None else None
    for prop, themed, plain in (("latin", "asciiTheme", "ascii"), ("east_asian", "eastAsiaTheme", "eastAsia")):
        ref = fonts.get(W + themed) if fonts is not None else None
        name = (theme.get((ref[:5], "ea" if "EastAsia" in ref else "latin")) if ref else None) or (
            fonts.get(W + plain) if fonts is not None else None)
        out.update({prop: name} if name else {})
    size = val(rpr, W + "sz")
    return {**out, "size": float(size) / 2} if size else out


def load(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile) as exc:
        fail(f"{path} cannot be read as a .docx ({exc}). Save a .doc file as .docx first.")
    d = {"path": path, "parts": parts, "trees": {}}
    root = tree(d, "word/document.xml")
    d["body"] = root.find(W + "body") if root is not None else None
    if d["body"] is None:
        fail(f"{path} has no word/document.xml body: save it from Word as .docx.")
    d["parent"] = {child: parent for parent in d["body"].iter() for child in parent}
    d["theme"] = theme_fonts(tree(d, next((t for t in rels(d, "word/document.xml").values() if "theme/" in t), None)))
    styles = tree(d, "word/styles.xml")
    d["styles"] = {s.get(W + "styleId"): (s.get(W + "type"), val(s, W + "basedOn"), rprops(s.find(W + "rPr"), d["theme"]),
                                          s.get(W + "default") in ("1", "true", "on"))
                   for s in (styles.findall(W + "style") if styles is not None else [])}
    d["defaults"] = rprops(styles.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr") if styles is not None else None, d["theme"])
    d["default_style"] = next((sid for sid, s in d["styles"].items() if s[0] == "paragraph" and s[3]), None)
    return d


def effective(d: dict, p, r=None) -> dict:
    """Fonts and size of run r of paragraph p or, when r is None, of p's paragraph mark: what typed text gets.
    A style's properties come from the styles it is based on, the base first."""
    def chain(sid, seen=()):
        return {} if sid not in d["styles"] or sid in seen else {**chain(d["styles"][sid][1], (*seen, sid)), **d["styles"][sid][2]}
    ppr = p.find(W + "pPr")
    eff = {**d["defaults"], **chain(val(ppr, W + "pStyle") or d["default_style"])}
    if r is None:
        return {**eff, **rprops(ppr.find(W + "rPr") if ppr is not None else None, d["theme"])}
    return {**eff, **chain(val(r.find(W + "rPr"), W + "rStyle")), **rprops(r.find(W + "rPr"), d["theme"])}


def canon(el, names: dict, masked=frozenset()):
    """An element as compared: no session ids or proofing marks, relationships by target, a filled cell by its properties."""
    if el in masked:
        pr = el.find(W + "tcPr")
        return el.tag, "filled", None if pr is None else canon(pr, names)
    attrs = tuple(sorted((k, names.get(v, v) if k.startswith(R) else v) for k, v in el.attrib.items()
                         if not re.match(r"rsid|paraId|textId", k.rpartition("}")[2])))
    text = (el.text or "") if el.tag == W + "t" else (el.text or "").strip()
    return el.tag, attrs, text, tuple(canon(c, names, masked) for c in el if c.tag not in NOISE)


def text(el) -> str:
    """The text of a paragraph, cell or block: a tab as \\t, a line break as \\n, paragraphs joined by \\n."""
    return "\n".join("".join((c.text or "") if c.tag == W + "t" else "\t" if c.tag == W + "tab" else "\n"
                             for r in p.iter(W + "r") for c in r if c.tag in (W + "t", W + "tab", W + "br", W + "cr"))
                     for p in el.iter(W + "p"))


def locate(d: dict, field: dict) -> tuple:
    """(label element or None, place blocks or None, what went wrong)."""
    want, place, body = key(field["label"]), field["place"], d["body"]
    pool = [b for b in body if b.tag == W + "p"] if place == "after" else list(body.iter(W + "tc"))
    hits, n = [el for el in pool if key(text(el)) == want], field.get("occurrence")
    if not hits:
        shown = {key(text(el)): snip(text(el), 40) for el in pool if text(el).strip()}
        near = ", ".join(f"“{shown[k]}”" for k in get_close_matches(want, list(shown), 3, 0.6))
        return None, None, f"Not in the form{f'; the closest: {near}' if near else ''}. Copy the label as the form prints it."
    if len(hits) > 1 and n is None or (n or 1) > len(hits):
        return None, None, f"The label appears {len(hits)} time(s): set occurrence to one of 1 to {len(hits)}."
    label = hits[(n or 1) - 1]
    if place == "after":
        blocks = [b for b in body if b.tag != W + "sectPr"]
        start = blocks.index(label) + 1
        end = next((i for i in range(start, len(blocks)) if blocks[i].tag == W + "p" and key(text(blocks[i])) == key(field["until"])), None)
        if end is None:
            return label, None, f"until “{field['until']}” is not after the label: what followed the place is gone or misnamed."
        return (label, blocks[start:end], "") if end > start else (label, None, "Nothing lies between the label and until.")
    row = d["parent"][label]
    if place == "right":
        cells = [c for c in row if c.tag == W + "tc"]
        target = cells[cells.index(label) + 1] if cells.index(label) + 1 < len(cells) else None
    else:
        rows = [r for r in d["parent"][row] if r.tag == W + "tr"]
        below = rows[rows.index(row) + 1] if rows.index(row) + 1 < len(rows) else []
        col = lambda tc, tr: int(val(tr, f"{W}trPr/{W}gridBefore") or 0) + sum(  # noqa: E731
            int(val(c, f"{W}tcPr/{W}gridSpan") or 1) for c in list(tr)[:list(tr).index(tc)] if c.tag == W + "tc")
        target = next((c for c in below if c.tag == W + "tc" and col(c, below) == col(label, row)), None)
    if target is None:
        return label, None, f"No cell {'to the right of' if place == 'right' else 'below'} the label."
    merge = target.find(f"{W}tcPr/{W}vMerge")
    if merge is not None and merge.get(W + "val", "continue") != "restart":
        return label, None, "The cell is the hidden part of a vertical merge that starts above: Word shows only the first cell."
    return label, [target], ""


def runs(blocks: list) -> list:
    """(paragraph, run, text) of every run with visible text in the blocks."""
    paras = [p for b in blocks for p in ([b] if b.tag == W + "p" else b.iter(W + "p"))]
    return [(p, r, t) for p in paras for r in p.iter(W + "r") for t in ["".join(c.text or "" for c in r if c.tag == W + "t")]
            if t.strip()]


def font_problems(want: dict, got: dict, sample: str) -> list:
    name = lambda v: ALIASES.get("".join(unicodedata.normalize("NFKC", v or "").casefold().split()), v)  # noqa: E731
    return [f"{label} {got.get(prop) or 'not set'}, the form has {want.get(prop) or 'not set'}" for prop, label, pattern in (
        ("latin", "Latin font", LATIN), ("east_asian", "East Asian font", CJK), ("size", "size", re.compile(".")))
        if pattern.search(sample) and (name(got.get(prop)) != name(want.get(prop)) if prop != "size" else got.get(prop) != want.get(prop))]


def field_rows(t: dict, f: dict, fields: list, number: int, places: dict) -> list:
    field, name = fields[number - 1], f"{number}. {fields[number - 1]['label']}"
    label, blocks, why = locate(t, field)
    if label is None:
        return [("label", name, "fail", why)]
    rows = [("label", name, "pass", f"Occurrence {field['occurrence']}." if field.get("occurrence") else "Found once in the form.")]
    if blocks is None:
        return rows + [("place", name, "fail", why)]
    places["t"][number] = (label, blocks, field["place"])
    row = t["parent"].get(blocks[0]) if blocks[0].tag == W + "tc" else None
    tbl = None if row is None else t["parent"][row]
    spot = f"{len(blocks)} paragraph(s) after the label" if row is None else f"table {list(t['body'].iter(W + 'tbl')).index(tbl) + 1}" \
        f", row {tbl.findall(W + 'tr').index(row) + 1}, cell {row.findall(W + 'tc').index(blocks[0]) + 1}"
    held, others = "\n".join(text(b) for b in blocks), {key(x["label"]) for i, x in enumerate(fields, 1) if i != number}
    covers = any(key(line) in others for line in [held, *held.splitlines()])
    rows.append(("place", name, "fail" if covers else "manual" if held.strip() else "pass", spot + (
        f" holds “{snip(held)}”, the label of another field: check place and label." if covers else f" holds “{snip(held)}” in the "
        "form, which the value replaces: confirm it is a hint, not a label." if held.strip() else ".")))
    found = runs(blocks)
    want = effective(t, *found[0][:2]) if found else effective(t, next(blocks[0].iter(W + "p")))
    label_f, blocks_f, why_f = locate(f, field)
    rows.append(("label_kept", name, "pass" if label_f is not None else "fail", "Still in the filled form." if label_f is not None
                 else "No longer in the filled form: it was overwritten or deleted."))
    if blocks_f is None:
        return rows + [("value", name, "fail", why_f if label_f is not None else "The label is gone, so the place cannot be found.")]
    places["f"][number] = (label_f, blocks_f, field["place"])
    got, value = "\n".join(text(b) for b in blocks_f).strip("\n"), field["value"].replace("\r\n", "\n").strip("\n")
    converted = got.lstrip("0") == value.lstrip("0") or {got.lower(), value.lower()} <= {"no", "yes", "false", "true", "0", "1"}
    rows.append(("value", name, "pass" if got == value else "fail", f"Reads “{snip(got)}”." if got == value else
                 f"Reads “{snip(got)}”; form-fill.json: “{snip(value)}”." + (
                     " The value was converted on the way: write it as a string and fill it again." if converted else "")))
    typed = sum(1 for b in blocks_f for t_ in b.iter(W + "t") if re.search(r"[\r\n]", t_.text or ""))
    rows.append(("raw_newline", name, "fail" if typed else "pass", f"{typed} text element(s) hold a typed line break, which Word "
                 "shows as a space: write a line break element or a new paragraph." if typed else "No typed line break."))
    problems = [f"“{snip(s, 20)}”: " + "; ".join(p) for p_, r, s in runs(blocks_f) for p in [font_problems(want, effective(f, p_, r), s)] if p]
    rows.append(("fonts", name, "fail" if problems else "pass", "; ".join(problems[:3]) + f" ({len(problems)} run(s))" if problems
                 else f"Every filled run has the form's fonts here: {want.get('latin')}, {want.get('east_asian')}, {want.get('size')} pt."))
    return rows


def changed(old, new, masked: set) -> str:
    """One difference, in words."""
    shown = lambda el: "a declared place" if el is None else f"the table that begins “{snip(text(el), 30)}”" if (  # noqa: E731
        el.tag == W + "tbl") else f"“{snip(text(el))}”" if text(el).strip() else "an empty paragraph"
    if old is None or new is None:
        return f"Missing from the filled form: {shown(old)}." if new is None else f"Added outside the declared places: {shown(new)}."
    if old.tag == new.tag == W + "tbl":
        pairs = [(a, b) for ra, rb in zip(old.iter(W + "tr"), new.iter(W + "tr"))
                 for a, b in zip(ra.findall(W + "tc"), rb.findall(W + "tc")) if a not in masked and b not in masked]
        diff = [f"“{snip(text(a), 30)}” → “{snip(text(b), 30)}”" for a, b in pairs if text(a) != text(b)]
        return f"In {shown(old)}: " + ("; ".join(diff[:3]) if diff else "rows, cells or their properties changed") + "."
    return f"Formatting or properties changed in {shown(old)}." if text(old) == text(new) else f"{shown(old)} became {shown(new)}."


def outside_rows(t: dict, f: dict, places: dict) -> list:
    """Every body block outside the places, in order; a declared region is one token, a filled cell keeps its properties."""
    def sequence(d, mine):
        cells = frozenset(b for _, blocks, place in mine.values() if place != "after" for b in blocks)
        regions = {label: (number, len(blocks)) for number, (label, blocks, place) in mine.items() if place == "after"}
        blocks, names, seq, i = [b for b in d["body"] if b.tag != W + "sectPr"], rels(d, "word/document.xml", True), [], 0
        while i < len(blocks):
            seq.append((canon(blocks[i], names, cells), blocks[i]))
            if blocks[i] in regions:
                seq.append((("declared place", regions[blocks[i]][0]), None))
                i += regions[blocks[i]][1]
            i += 1
        return seq
    st, sf = sequence(t, places["t"]), sequence(f, places["f"])
    masked = {b for side in places.values() for _, blocks, place in side.values() if place != "after" for b in blocks}
    found = []
    for op, a1, a2, b1, b2 in SequenceMatcher(None, [x[0] for x in st], [x[0] for x in sf], autojunk=False).get_opcodes():
        old, new = [x[1] for x in st[a1:a2]], [x[1] for x in sf[b1:b2]]
        found += [] if op == "equal" else [changed(old[i] if i < len(old) else None, new[i] if i < len(new) else None, masked)
                                           for i in range(max(len(old), len(new)))]
    return [("outside", "body", "fail" if found else "pass", " ".join(found[:6]) + (f" ({len(found) - 6} more)" if len(found) > 6
             else "") if found else f"All {len(st)} blocks outside the declared places are as in the form.")]


def part_rows(t: dict, f: dict) -> list:
    part_form = lambda d, name: None if tree(d, name) is None else canon(tree(d, name), rels(d, name, True))  # noqa: E731
    rows = []
    for check, name in (("styles", "word/styles.xml"), ("numbering", "word/numbering.xml")):
        a, b = tree(t, name), tree(f, name)
        if (a is None) != (b is None) or (a is not None and part_form(t, name) != part_form(f, name)):
            ids = [{(s.tag, s.get(W + "styleId") or s.get(W + "abstractNumId") or s.get(W + "numId")): canon(s, {}) for s in root}
                   for root in (a, b) if root is not None]
            diff = sorted(" ".join(filter(None, (tag.rpartition("}")[2], sid))) for tag, sid in ids[0].keys() | ids[-1].keys()
                          if ids[0].get((tag, sid)) != ids[-1].get((tag, sid))) if len(ids) == 2 else ["the whole part"]
            rows.append((check, name, "fail", f"Changed: {', '.join(diff[:8]) or 'document defaults'}. Filling a form never "
                                              "changes its styles or numbering."))
        else:
            rows.append((check, name, "pass", "Same as the form." if a is not None else "Neither file has this part."))
    sections = [[p.find(f"{W}pPr/{W}sectPr") for p in d["body"].iter(W + "p") if p.find(f"{W}pPr/{W}sectPr") is not None]
                + [d["body"].find(W + "sectPr")] for d in (t, f)]
    forms = [[None if s is None else canon(s, rels(d, "word/document.xml", True)) for s in side] for d, side in zip((t, f), sections)]
    off = [str(i) for i, (a, b) in enumerate(zip(*forms), 1) if a != b]
    rows.append(("sections", f"{len(forms[0])} section(s)", "pass" if forms[0] == forms[1] else "fail", "Page size, margins, "
                 "columns and header references as in the form." if forms[0] == forms[1] else f"The form has {len(forms[0])} "
                 f"section(s), the filled copy {len(forms[1])}; differing: {', '.join(off) or 'the count'}."))
    refs = [{(i, ref.tag.rpartition("}")[2], ref.get(W + "type", "default")): rels(d, "word/document.xml").get(ref.get(R + "id"))
             for i, s in enumerate(side, 1) if s is not None for ref in s if ref.tag in (W + "headerReference", W + "footerReference")}
            for d, side in zip((t, f), sections)]
    bad = [f"section {ref[0]} {ref[1]} ({ref[2]})" for ref, part in refs[0].items()
           if part_form(t, part) is None or part_form(t, part) != part_form(f, refs[1].get(ref))]
    rows.append(("headers_footers", f"{len(refs[0])} part(s)", "fail" if bad else "pass", "Changed or missing: " + "; ".join(bad)
                 + ". Logos, page numbers and running text stay as in the form." if bad else
                 "Every header and footer, with its images and fields, as in the form." if refs[0] else "The form has none."))
    return rows


def pages_row(paths: tuple, out: Path) -> tuple:
    tool, counts = shutil.which("soffice") or shutil.which("libreoffice"), []
    if not tool:
        return ("pages", "both files", "not_checked", "LibreOffice (soffice) is not installed, so no page was counted: open the "
                "filled form and look at every page.")
    for side, path in zip(("form", "filled"), paths):
        folder = out / "form-pdf" / side
        folder.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run([tool, "--headless", "--convert-to", "pdf", "--outdir", folder, path], capture_output=True, timeout=180)
            counts.append(len(re.findall(rb"/Type\s*/Page\b", (folder / f"{path.stem}.pdf").read_bytes())))
        except (OSError, subprocess.SubprocessError) as exc:
            return ("pages", "both files", "not_checked", f"LibreOffice could not render {path.name} ({exc}).")
    return ("pages", "both files", "manual", f"The form renders as {counts[0]} page(s), the filled copy as {counts[1]}: look at "
            f"every page of {out / 'form-pdf' / 'filled'}.")


def load_fill(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError:
        fail(f"no fill map at {path}: declare the fields first (references/forms-and-amendments.md).")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{path} is not valid JSON: {exc}")
    fields = data.get("fields") if isinstance(data, dict) else None
    if not isinstance(fields, list) or not fields or not all(isinstance(x, dict) for x in fields):
        fail(f'{path} must hold a non-empty list "fields" of objects.')
    errors = [f"fields[{i}].{message}" for i, x in enumerate(fields, 1) for wrong, message in (
        (not str(x.get("label") or "").strip(), "label is missing"),
        (x.get("place") not in PLACES, f"place must be one of {', '.join(PLACES)}"),
        (not isinstance(x.get("value"), str), 'value must be a string written as the form shows it: "012345", not 12345; "No", not false'),
        (x.get("place") == "after" and not str(x.get("until") or "").strip(), "until must name the paragraph after the place that stays"),
        ("occurrence" in x and not (type(x["occurrence"]) is int and x["occurrence"] >= 1), "occurrence must be a whole number from 1"))
        if wrong]
    if errors:
        fail(f"{path} is not in the format of references/forms-and-amendments.md:\n  - " + "\n  - ".join(errors))
    return fields


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Prove that a filled copy of a Word form changed only the declared places.")
    p = parser.add_subparsers(dest="command", required=True).add_parser("compare", help="Compare a form with its filled copy")
    for name, about in (("form", "The institution's form, as received (.docx)"), ("filled", "The filled copy (.docx)"),
                        ("--fill", "The declared fields (default: <dir>/form-fill.json)"), ("--dir", "Folder for form-check.md")):
        p.add_argument(name, help=about, **({"default": "protocol"} if name == "--dir" else {}))
    args = parser.parse_args(argv)
    out, fill, paths = Path(args.dir), Path(args.fill or Path(args.dir) / "form-fill.json"), (Path(args.form), Path(args.filled))
    fields = load_fill(fill)
    t, f, rows, places = load(paths[0]), load(paths[1]), [], {"t": {}, "f": {}}
    for number in range(1, len(fields) + 1):
        rows += field_rows(t, f, fields, number, places)
    rows += part_rows(t, f) + outside_rows(t, f, places) + [pages_row(paths, out)]
    counts = {s: sum(r[2] == s for r in rows) for s in STATES}
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()[:12]  # noqa: E731
    lines = ["# Form check", "", f"Form: {paths[0]} (SHA-256 {digest(paths[0])}). Filled: {paths[1]} (SHA-256 "
             f"{digest(paths[1])}). Fields: {fill} ({len(fields)}).", "", f"{len(rows)} rows: " + ", ".join(
                 f"{counts[s]} {s}" for s in STATES) + ". `manual` and `not_checked` are not passes.", "",
             "| Check | Subject | State | Detail |", "|---|---|---|---|",
             *("| " + " | ".join(re.sub(r"\s+", " ", str(v)).replace("|", "/") for v in row) + " |" for row in rows)]
    out.mkdir(parents=True, exist_ok=True)
    (out / "form-check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = {"ok": counts["fail"] == 0, "counts": counts, **{name: [f"{r[0]}: {r[1]}" for r in rows if r[2] == state]
              for name, state in (("failed", "fail"), ("manual", "manual"), ("not_checked", "not_checked"))},
              "report": str(out / "form-check.md")}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
