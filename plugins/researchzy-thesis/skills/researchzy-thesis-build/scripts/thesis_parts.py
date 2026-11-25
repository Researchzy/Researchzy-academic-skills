#!/usr/bin/env python3
"""Text guards for assembling a thesis from published papers: snapshots, bibliographies, abbreviations.

  thesis_parts.py snapshot papers/ -o thesis-build/before.json     visible text of each .docx, .md and .tex file
  thesis_parts.py diff thesis-build/before.json thesis-build/after.json [--unpublished paper3.docx]
  thesis_parts.py bib paper1/refs.bib paper2/refs.bib               one work under two keys, one key for two works
  thesis_parts.py abbreviations chapters/                          abbreviations and their long forms
  thesis_parts.py csl-sample thesis.bib style.csl [--keys a,b,c]    a few entries through pandoc citeproc

snapshot keeps sentences with their line or ¶ (citations, cross-references, formulas become tokens).
diff lists each before sentence found in no after file; one that differs only in figure, table, equation
or chapter numbers, or in citation form, is manual. Every before file counts as published unless named in
--unpublished. bib fails on one work under two keys, one key for two works, or a key repeated in a file.
abbreviations reads "long form (ABBR)" and "长形式（ABBR）"; two long forms in one script are manual leads.

Each command writes a report in --dir (default thesis-build) and prints a JSON summary; rows are pass, fail,
manual or not_checked. Exit 1 when (diff) a published sentence changed or disappeared or (bib) a row fails;
2 when an input cannot be read. Standard library only; csl-sample runs pandoc.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CSL = "{http://purl.org/net/xbiblio/csl}"
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
QUOTES = dict.fromkeys(map(ord, "‘’‚‛“”„‟«»‹›´`\""), "'")
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
SIMILAR = 0.6   # convention: a new sentence this similar to a missing one is shown as its changed form
SUFFIXES = (".docx", ".md", ".tex")
SKIP_DIRS = {"thesis-build", ".git", "__pycache__"}
NUMBERED = re.compile(r"(图|表|式|公式|附图|附表|figure|fig\.|table|tab\.|eq\.|equation|section|sec\.|chapter|appendix)\s*"
                      r"\(?(?:[a-z]?\d+(?:[.\-–]\d+)*|〔\w+〕)\)?", re.I)
CITATION = re.compile(r"〔\w+〕|\[\d+(?:\s*[,\-–]\s*\d+)*\]|\([^()]{0,80}?(?:19|20)\d{2}[a-z]?\)")
ABBR = re.compile(r"(?=(?:[^A-Z]*[A-Z]){2})[A-Za-z][A-Za-z0-9&/-]{1,9}")
ZH_LEAD = re.compile(r".*(?:本文|本研究|本章|我们|采用|基于|通过|根据|运用|引入|提出|称为|简称)|^[和与及或、的]+")


def fail(message: str):
    print(f"thesis_parts: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        fail(f"{path} cannot be read as UTF-8 text ({exc}).")


def report(directory: Path, name: str, title: str, head: list, rows: list, tail: list, extra: dict) -> int:
    counts, code = Counter(row[2] for row in rows), int(any(row[2] == "fail" for row in rows))
    cell = lambda value: re.sub(r"\s+", " ", str(value)).replace("|", "/").strip()  # noqa: E731
    lines = [f"# {title}", "", *head, "", f"{len(rows)} rows: " + ", ".join(f"{counts[s]} {s}" for s in (
        "pass", "fail", "manual", "not_checked")) + ".", "", "| Check | Where | State | Detail |", "|---|---|---|---|",
        *(f"| {' | '.join(cell(v) for v in row)} |" for row in rows), *tail]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": code == 0, "counts": dict(counts), "failed": [f"{r[0]}: {r[1]}" for r in rows if r[2] == "fail"],
                      **extra, "report": str(directory / name)}, indent=2, ensure_ascii=False))
    return code


def blocks(text: str) -> list:
    out, start, buffer = [], 1, []
    for number, line in enumerate(text.split("\n") + [""], 1):
        if line.strip():
            start, buffer = start if buffer else number, buffer + [line.strip()]
        elif buffer:
            out, buffer = out + [(start, "\n".join(buffer))], []
    return out


def keep(token: str):   # a replacement that keeps as many line breaks as it removes, so line numbers hold
    return lambda m: token + "\n" * m.group(0).count("\n")


def tex_blocks(text: str) -> list:
    text = re.sub(r"(?<!\\)%.*", "", text)
    begin = re.search(r"\\begin\s*\{document\}", text)
    text = re.split(r"\\end\s*\{document\}", "\n" * text[:begin.end()].count("\n") + text[begin.end():] if begin else text)[0]
    text = re.sub(r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath)(\*?)\}.*?\\end\{\1\2\}|\\\[.*?\\\]|"
                  r"\$\$.*?\$\$|(?<!\\)\$.+?(?<!\\)\$|\\\(.*?\\\)", keep("〔math〕"), text, flags=re.S)
    text = re.sub(r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|title|caption)\*?\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}",
                  "\ue000\\1\ue000", text)   # a heading or caption is a sentence of its own
    text = re.sub(r"\\[A-Za-z]*cite[A-Za-z]*\*?\s*(?:\[[^\]]*\]\s*){0,2}\{[^}]*\}", keep("〔cite〕"), text)
    text = re.sub(r"\\(?:[cC]ref|ref|eqref|autoref|pageref|nameref|vref)\*?\s*\{[^}]*\}", keep("〔ref〕"), text)
    text = re.sub(r"\\(?:begin|end)\s*\{[^}]*\}(?:\[[^\]]*\])?|\\(?:label|includegraphics|input|include|bibliography|"
                  r"bibliographystyle|addbibresource|usepackage|documentclass|graphicspath|vspace|hspace|url|href|newcommand|"
                  r"renewcommand|setlength)\*?\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}", keep(" "), text)
    text = re.sub(r"\\([%&#_$])", r"\1", re.sub(r"\\\\|~", " ", text))
    return blocks(re.sub(r"\\[A-Za-z@]+\*?(?:\s*\[[^\]]*\])?|[{}]", "", text))


def md_blocks(text: str) -> list:
    text = re.sub(r"\A---\n.*?\n(?:---|\.\.\.)\n", keep(""), text, flags=re.S)
    text = re.sub(r"<!--.*?-->|^```.*?^```", keep(""), text, flags=re.S | re.M)
    text = re.sub(r"\$\$.*?\$\$|(?<!\\)\$[^$\n]+\$", keep("〔math〕"), text, flags=re.S)
    text = re.sub(r"\[[^\]]*@[\w:.-]+[^\]]*\]|(?<![\w@])@[\w:.-]*\w", "〔cite〕", re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text))
    text = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+(.*)$", " \\1 ", re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text))
    return blocks(re.sub(r"[*_`|]+", " ", re.sub(r"(?m)^[ \t]{0,3}(?:>[ \t]?|[-*+][ \t]+|\d+[.)][ \t]+)", "", text)))


def docx_blocks(path: Path) -> list:
    """(¶ N, text) per paragraph, numbered as format_check.py does; citation and reference fields become tokens."""
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        fail(f"{path} cannot be read as a .docx ({exc}).")
    boxed = {id(e) for box in root.iter(W + "txbxContent") for e in box.iter()}
    out, stack = [], []
    for el in (e for e in root.iter() if id(e) not in boxed):
        kind = el.get(W + "fldCharType") if el.tag == W + "fldChar" else None
        if el.tag == W + "p":
            out.append([f"¶ {len(out) + 1}", ""])
        elif kind == "begin":
            stack.append({"code": "", "masked": False})
        elif kind == "separate" and stack:
            code = stack[-1]["code"].strip().upper()
            stack[-1]["masked"] = code.startswith(("ADDIN", "CITATION", "REF ", "PAGEREF", "NOTEREF", "SEQ"))
            out[-1][1] += ("〔cite〕" if code.startswith(("ADDIN", "CITATION")) else "〔ref〕") if stack[-1]["masked"] and out else ""
        elif kind == "end" and stack:
            stack.pop()
        elif el.tag == W + "instrText" and stack:
            stack[-1]["code"] += el.text or ""
        elif el.tag in (W + "t", W + "tab") and out and not any(f["masked"] for f in stack):
            out[-1][1] += (el.text or "") if el.tag == W + "t" else " "
    return [tuple(item) for item in out if item[1].strip()]


def files_of(target: Path) -> tuple:
    """(root, files): one file, or every .docx, .md and .tex file under a folder (not thesis-build/)."""
    if target.is_file():
        return target.parent, [target] if target.suffix.lower() in SUFFIXES else fail(f"{target} is not .docx, .md or .tex")
    files = sorted(p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES and not p.name.startswith("~$")
                   and not SKIP_DIRS & set(p.relative_to(target).parts)) if target.is_dir() else []
    return target, files or fail(f"no .docx, .md or .tex file at {target}")


def extract(path: Path) -> list:
    suffix = path.suffix.lower()
    return docx_blocks(path) if suffix == ".docx" else (md_blocks if suffix == ".md" else tex_blocks)(read_text(path))


def sentences(found: list) -> list:
    out = []
    for where, text in found:
        at = 0
        for piece in (p.strip() for p in re.split(r"(?<=[。！？!?；;])|(?<=\.)\s+(?=[A-Z0-9〔(\"'“])|\ue000", text)):
            at = text.find(piece, at)
            if len(HAN.findall(piece)) >= 4 or len(re.findall(r"[A-Za-z]{2,}", piece)) >= 3:
                out.append([f"line {where + text.count(chr(10), 0, at)}" if isinstance(where, int) else where, " ".join(piece.split())])
    return out


def norm(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).translate(QUOTES).translate(DASHES).casefold().split())


def soft(text: str) -> str:
    """A sentence without the numbers of figures, tables, equations and chapters, and without citations."""
    text = re.sub(r"第\s*[0-9一二三四五六七八九十]+\s*[章节]", "第〔n〕章", unicodedata.normalize("NFKC", text))
    return norm(CITATION.sub("〔n〕", NUMBERED.sub(lambda m: m.group(1) + "〔n〕", text)))


def cmd_snapshot(args) -> int:
    target, output = Path(args.target), Path(args.output)
    if output.exists():
        fail(f"{output} exists: choose a new name (before.json, after.json, ...).")
    root, files = files_of(target)
    data = {"tool": "researchzy-thesis-build", "kind": "snapshot", "source": str(target),
            "taken": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "files": [{"path": p.relative_to(root).as_posix(), "sentences": sentences(extract(p))} for p in files]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"snapshot": str(output), "files": {f["path"]: len(f["sentences"]) for f in data["files"]}}, ensure_ascii=False))
    return 0


def load_snapshot(path: Path) -> dict:
    try:
        data = json.loads(read_text(path))
    except ValueError as exc:
        fail(f"{path} is not JSON ({exc}).")
    return data if isinstance(data, dict) and data.get("kind") == "snapshot" else fail(f"{path} is not a snapshot of this script.")


def cmd_diff(args) -> int:
    before, after = load_snapshot(Path(args.before)), load_snapshot(Path(args.after))
    old = {norm(s) for f in before["files"] for _, s in f["sentences"]}
    new = [(f["path"], where, s, norm(s)) for f in after["files"] for where, s in f["sentences"]]
    present, pool, used, rows = {item[3] for item in new}, [item for item in new if item[3] not in old], set(), []
    unpublished = set(args.unpublished or [])
    for f in before["files"]:
        published = not ({f["path"], Path(f["path"]).name} & unpublished)
        for where, s in ((w, s) for w, s in f["sentences"] if norm(s) not in present):
            key, best, top = norm(s), None, SIMILAR
            for item in pool:
                m = difflib.SequenceMatcher(None, key, item[3], autojunk=False)
                if m.real_quick_ratio() >= top and m.quick_ratio() >= top and m.ratio() >= top:
                    best, top = item, m.ratio()
            used.add(best[2] if best else None)
            only_numbers = best is not None and soft(best[2]) == soft(s)
            state = "manual" if only_numbers or not published else "fail"
            change = ("only figure, table, equation or chapter numbers, or the citation form, differ" if only_numbers else
                      "changed" if best else "removed") + ("" if published else " (unpublished file)")
            rows.append(("sentence", f"{f['path']} {where}", state, f"{change}. Before: “{s[:240]}”" + (
                f" After ({best[0]} {best[1]}): “{best[2][:240]}”" if best else "")))
    fresh = [item for item in pool if item[2] not in used]
    if not rows:
        rows.append(("published_text", "all files", "pass", "Every sentence of the before snapshot is in the after snapshot."))
    tail = ["", f"## New text ({len(fresh)} sentences)", "", "In the after snapshot only, and not shown above as a changed form: "
            "bridging text, front matter, or edits. The first 20:", "", *(f"- {f} {w}: {s[:160]}" for f, w, s, _ in fresh[:20])]
    head = [f"Before: {args.before} ({before.get('taken')}, {len(before['files'])} files). After: {args.after} "
            f"({after.get('taken')}, {len(after['files'])} files). Published unless named: {', '.join(sorted(unpublished)) or 'all'}."]
    return report(Path(args.dir), "diff.md", "Text before and after assembly", head, rows, tail, {"new_sentences": len(fresh)})


def braced(text: str, i: int) -> tuple:
    """The content of the {...} or "..." value starting at text[i], and the index after it."""
    depth = 0
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if (text[i] == "{" and depth == 0) or (text[i] == '"' and j > i and text[j] == '"' and depth == 0):
            return text[i + 1:j], j + 1
    fail(f"an unclosed value at character {i} of a .bib file")


def bib_entries(path: Path) -> list:
    text, entries = read_text(path), []
    for m in re.finditer(r"@\s*([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,", text):
        if m.group(1).lower() in ("comment", "string", "preamble"):
            continue
        fields, i = {}, m.end()
        while field := re.compile(r"\s*([A-Za-z][\w:.-]*)\s*=\s*").match(text, i):
            i = field.end()
            if i < len(text) and text[i] in '{"':
                value, i = braced(text, i)
            else:
                bare = re.compile(r"[^,}\s]*").match(text, i)
                value, i = bare.group(0), bare.end()
            fields[field.group(1).lower()] = value
            comma = re.compile(r"\s*,").match(text, i)
            if not comma:
                break
            i = comma.end()
        title = re.sub(r"\\[`'^\"~=.uvHc]\s*|\\[A-Za-z]+\s*|[{}]", "", fields.get("title", ""))   # accents, commands, braces
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", fields.get("doi", "").strip().lower()).rstrip(".")
        entries.append({"key": m.group(2), "file": str(path), "doi": doi, "shown": " ".join(title.split())[:80],
                        "title": "".join(re.findall(r"\w+", "".join(c for c in unicodedata.normalize("NFKD", title).casefold()
                                                                      if not unicodedata.combining(c)))),
                        "year": "".join(re.findall(r"\d{4}", fields.get("year", fields.get("date", ""))))[:4]})
    return entries


def cmd_bib(args) -> int:
    entries, rows = [e for name in args.bib for e in bib_entries(Path(name))], []
    rows += [("key_repeated", f"{file}: {key}", "fail", f"The key appears {n} times in one file: BibTeX keeps only one.")
             for (file, key), n in Counter((e["file"], e["key"]) for e in entries).items() if n > 1]
    for key in dict.fromkeys(e["key"] for e in entries):
        group = [e for e in entries if e["key"] == key]
        a, b = group[0], next((e for e in group if e["file"] != group[0]["file"]), None)
        if b is None:
            continue
        clash = [f for f in ("doi", "year") if a[f] and b[f] and a[f] != b[f]] + ["title"] * bool(
            a["title"] and b["title"] and a["title"] not in b["title"] and b["title"] not in a["title"])
        same = all(a[f] == b[f] for f in ("doi", "title", "year"))
        rows.append(("one_key_two_works" if clash else "one_key_two_files", f"{key} ({a['file']}, {b['file']})",
                     "fail" if clash else "pass" if same else "manual",
                     f"Different {', '.join(clash)}: “{a['shown']}” and “{b['shown']}”. Give one of them a new key." if clash else
                     "The same entry in both files." if same else "The same work with different fields: keep the fuller entry."))
    signatures = {}
    for e in entries:
        for kind, sig in (("DOI", e["doi"]), ("title and year", e["title"] and (e["title"], e["year"])), ("title", e["title"])):
            signatures.setdefault((kind, sig), set()).add(e["key"]) if sig else None
    reported = set()
    for (kind, sig), keys in signatures.items():
        if len(keys) > 1 and frozenset(keys) not in reported:
            reported.add(frozenset(keys))
            rows.append(("one_work_two_keys", ", ".join(sorted(keys)), "manual" if kind == "title" else "fail", f"Same {kind}: “"
                         + next(e["shown"] for e in entries if e["key"] in keys) + ("”, but different years: a conference and a "
                         "journal version?" if kind == "title" else "”. Keep one key and change the citations that use the others.")))
    rows = rows or [("bibliography", f"{len(args.bib)} files", "pass", f"{len(entries)} entries: no work has two keys and "
                     "no key holds two works.")]
    return report(Path(args.dir), "bib-check.md", "Merged bibliography check", [f"Files: {', '.join(args.bib)} "
                  f"({len(entries)} entries)."], rows, [], {"entries": len(entries)})


def english_long(abbr: str, text: str, whole: bool = False):
    """The shortest run of words ending text that starts with the first letter and holds all letters in order."""
    words, letters = re.findall(r"[A-Za-z][A-Za-z'-]*", text), [c.lower() for c in abbr if c.isalpha()]
    for n in [len(words)] if whole else range(1, min(len(words), len(letters) + 5) + 1):
        run, at = words[-n:] if n else [], 0
        if not run or not letters or run[0][0].lower() != letters[0]:
            continue
        for c in letters:
            at = " ".join(run).lower().find(c, at) + 1
            if not at:
                break
        else:
            return " ".join(run)
    return None


def definitions(text: str) -> list:
    """(abbreviation, long form) pairs defined in text; full-width brackets and commas count."""
    text, found = unicodedata.normalize("NFKC", text), []
    for m in re.finditer(r"\(([^()]{1,120})\)", text):
        inner, before = m.group(1).strip(), text[max(0, m.start() - 160):m.start()].rstrip()
        parts = [x.strip() for x in re.split(r"[,;]", inner)]
        if ABBR.fullmatch(parts[-1]):
            head, zh = ", ".join(parts[:-1]), re.search(r"[\u4e00-\u9fff]{2,}$", before)
            longs = [head] if head and (HAN.search(head) or english_long(parts[-1], head, whole=True)) else []
            longs += [ZH_LEAD.sub("", zh.group(0))[-12:]] if zh else [english_long(parts[-1], before)] if len(parts) == 1 else []
            found += [(parts[-1], long, text.count("\n", 0, m.start())) for long in longs if long and len(long) >= 2]
        elif (prev := re.search(r"([A-Za-z][A-Za-z0-9&/-]{1,9})\s*$", before)) and ABBR.fullmatch(prev.group(1)) \
                and english_long(prev.group(1), inner, whole=True):
            found.append((prev.group(1), inner, text.count("\n", 0, m.start())))
    return found


def meanings(longs: list) -> list:
    """Long forms grouped by meaning: one contains the other, in the same script."""
    groups = []
    for long in dict.fromkeys(longs):
        key, script = "".join(re.findall(r"\w+", unicodedata.normalize("NFKC", long).casefold())), "zh" if HAN.search(long) else "en"
        group = next((g for g in groups if g["script"] == script and (key in g["key"] or g["key"] in key)), None)
        group["forms"].append(long) if group else groups.append({"script": script, "key": key, "forms": [long]})
    return groups


def cmd_abbreviations(args) -> int:
    defined, texts = {}, []
    for target in map(Path, args.files):
        root, files = files_of(target)
        for path in files:
            for where, text in extract(path):
                texts.append(unicodedata.normalize("NFKC", text))
                for abbr, long, down in definitions(text):
                    line = f"line {where + down}" if isinstance(where, int) else where
                    defined.setdefault(abbr, []).append((long, f"{path.relative_to(root).as_posix()} {line}"))
    everything, rows = "\n".join(texts), []
    for abbr in sorted(defined, key=str.casefold):
        groups = meanings([long for long, _ in defined[abbr]])
        clash = any(sum(g["script"] == s for g in groups) > 1 for s in ("zh", "en"))
        uses = len(re.findall(rf"(?<![A-Za-z0-9]){re.escape(abbr)}(?![A-Za-z0-9])", everything))
        rows.append(("two_long_forms" if clash else "defined", abbr, "manual" if clash else "pass", "; ".join(
            f"{long} ({where})" for long, where in defined[abbr][:6]) + f". Used {uses} times in these files."))
    leads = Counter(m for m in re.findall(r"(?<![A-Za-z0-9])[A-Z]{2,6}(?![A-Za-z0-9])", everything) if m not in defined)
    tail = ["", "## Used but not defined in these files (leads, at most 15)", "",
            ", ".join(f"{a} ({n})" for a, n in leads.most_common(15) if n >= 2) or "None used twice or more.", "", "A draft: the "
            "user confirms each long form before it enters the list of abbreviations."]
    return report(Path(args.dir), "abbreviations.md", "Abbreviations", [f"Files: {', '.join(args.files)}."], rows, tail,
                  {"defined": len(defined), "two_long_forms": [r[1] for r in rows if r[0] == "two_long_forms"]})


def cmd_csl(args) -> int:
    bib, csl = Path(args.bib), Path(args.csl)
    entries, pandoc, output = bib_entries(bib), shutil.which("pandoc"), ""
    try:
        root = ET.parse(csl).getroot()
    except (OSError, ET.ParseError) as exc:
        fail(f"{csl} cannot be read as a CSL style ({exc}).")
    info = {k: (root.findtext(f"{CSL}info/{CSL}{k}") or "").strip() for k in ("title", "id", "updated")}
    parent = next((link.get("href") for link in root.iter(CSL + "link") if link.get("rel") == "independent-parent"), "")
    keys = [k.strip() for k in args.keys.split(",")] if args.keys else [e["key"] for e in entries[:3]]
    if len(keys) < 2 or set(keys) - {e["key"] for e in entries}:
        fail(f"give at least two keys that are in {bib}; not found: {', '.join(set(keys) - {e['key'] for e in entries}) or '-'}")
    if parent and root.find(CSL + "citation") is None:
        state, detail = "not_checked", f"A dependent style: it only names its parent ({parent}). Download the parent and pass it."
    elif not pandoc:
        state, detail = "not_checked", "pandoc is not installed, so nothing was rendered. Install pandoc, or check the style by hand."
    else:
        sample = f"One work [@{keys[0]}]. Two works [@{keys[0]}; @{keys[1]}]. In the sentence, @{keys[-1]} [p. 12].\n\n# References\n"
        try:
            run = subprocess.run([pandoc, "--citeproc", "--bibliography", str(bib), "--csl", str(csl), "-f", "markdown", "-t",
                                  "plain", "--wrap=none"], input=sample, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            fail(f"pandoc did not run ({exc}).")
        if run.returncode:
            fail(f"pandoc could not render the sample: {run.stderr.strip()[:400]}")
        state, output = "manual", run.stdout
        detail = "Rendered below: compare it with the examples in the school's rules, by eye." + (
            f" pandoc warned: {run.stderr.strip()[:300]}" if run.stderr.strip() else "")
    head = [f"Style: {csl}: title “{info['title'] or 'none'}”, id {info['id'] or 'none'}, updated {info['updated'] or 'not stated'}"
            + (f", parent {parent}" if parent else "") + ". Record the URL it came from and the date in rules.json.",
            f"Entries: {', '.join(keys)} from {bib}."]
    tail = ["", "## Sample", "", "```", output.strip() or "(not rendered)", "```"]
    return report(Path(args.dir), "csl-sample.md", "Citation style sample", head, [("csl_sample", csl.name, state, detail)], tail,
                  {"style": info, "parent": parent, "keys": keys, "pandoc": bool(pandoc)})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Text guards for assembling a thesis from published papers.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="thesis-build", help="Folder for the reports (default: thesis-build)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("snapshot", help="Store the visible text of chapter files as sentences")
    p.add_argument("target", help="A folder of .docx, .md and .tex files, or one file"), p.add_argument("-o", "--output", required=True)
    p = sub.add_parser("diff", parents=[common], help="Sentences of the before snapshot missing from the after snapshot")
    p.add_argument("before"), p.add_argument("after"), p.add_argument("--unpublished", nargs="*", help="Before files that may change")
    sub.add_parser("bib", parents=[common], help="Duplicate works and clashing keys across .bib files").add_argument("bib", nargs="+")
    sub.add_parser("abbreviations", parents=[common], help="Abbreviations and their long forms").add_argument("files", nargs="+")
    p = sub.add_parser("csl-sample", parents=[common], help="Render a few entries with pandoc citeproc and a CSL style")
    p.add_argument("bib"), p.add_argument("csl"), p.add_argument("--keys", help="Comma-separated keys (default: the first three)")
    args = parser.parse_args(argv)
    return {"snapshot": cmd_snapshot, "diff": cmd_diff, "bib": cmd_bib, "abbreviations": cmd_abbreviations,
            "csl-sample": cmd_csl}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
