#!/usr/bin/env python3
"""Split a text into translation units, mask what must not change, and put a translation back.

  tr_units.py split SOURCE [--out translation]               write <out>/units.json
  tr_units.py unmask [--out translation] [--output FILE]     write the translated file

split reads .md, .tex, .txt, or the text of a .docx (headings, paragraphs and tables; each equation
becomes a placeholder; footnotes and comments are not read). A unit is a paragraph, heading, list
item, table row or caption. Formulas, LaTeX commands with their arguments, citations (\\cite{},
[@key], @key, [3]), URLs, DOIs, code and comments become tokens such as ⟦T0001⟧. A command whose
argument is prose (\\textbf{}, \\footnote{}, \\href{}{}), a LaTeX {group} and a placeholder ([Author
input needed: …]) become a pair ⟦T0002⟧…⟦/T0002⟧ around the words to translate. Display maths,
LaTeX floats and tables, and code blocks are kept as they are, except captions; so is a LaTeX
preamble, except \\title.

unmask reads <out>/units.translated.json ({"u0001": "the masked text, translated", …}) and writes
<out>/<name>.translated.<ext> (.md for a .docx) and unmask.json. A unit keeps its source text when
a token is missing, extra or duplicated, a pair is out of order, a backslash or a broken token is
outside the tokens, or it has no translation. Tokens may change order. unmask.json counts each
unit's failed attempts. unmask will not replace an output it did not write, or one edited since.

Exit codes: 0; 1 when unmask kept the source text of any unit; 2 for a missing, unreadable or
changed input. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

TOOL = "researchzy-translate"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
EQUATION = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"
TOKEN = re.compile(r"⟦(/?)(T\d{4,})⟧")
MATH_ENV, FLOAT_ENV = r"equation|align|alignat|gather|multline|flalign|eqnarray|displaymath|math", \
    r"figure|wrapfigure|sidewaysfigure|table|wraptable|sidewaystable"
WHOLE_ENV = re.compile(rf"(?:{MATH_ENV}|verbatim|Verbatim|lstlisting|minted|comment)\*?")
KEPT_ENV = re.compile(rf"(?:{MATH_ENV}|{FLOAT_ENV}|verbatim|Verbatim|lstlisting|minted|comment|tabular[x*]?|tabulary"
                      r"|longtable|algorithm|algorithmic|algorithm2e|tikzpicture|thebibliography)\*?")
# Commands whose last {argument} is prose: the command becomes a pair of tokens around it.
PROSE = frozenset("textbf textit textsl textsc textup textrm textsf textmd emph underline uline uwave sout hl mbox "
                  "text footnote footnotetext thanks caption subcaption captionof section subsection subsubsection "
                  "paragraph subparagraph chapter part title keywords href textcolor colorbox fbox enquote".split())
# Commands without arguments, so that a {group} or [label] after them stays text.
NOARG = frozenset("noindent indent centering raggedright raggedleft par newline linebreak pagebreak newpage clearpage "
                  "maketitle item bf it em rm sf tt sc sl small footnotesize scriptsize tiny normalsize large Large "
                  "LARGE huge Huge bfseries itshape mdseries upshape normalfont quad qquad hfill vfill dots ldots "
                  "cdots LaTeX TeX today appendix and protect relax smallskip medskip bigskip hline toprule midrule "
                  "bottomrule tableofcontents".split())
COMMAND = re.compile(r"\\(?:([A-Za-z@]+)\*?|(.))", re.S)
LINE_BREAK = re.compile(r"\\\\\*?(?:\[[^\]\n]*\])?")
PLACEHOLDER = re.compile(r"\[\s*(?:Evidence needed|Citation needed|Author input needed)\s*:\s*", re.I)
BRACKETED = re.compile(r"\[[^\[\]\n]*?-?@[A-Za-z0-9_][^\[\]\n]*\]|[\[［]\d{1,3}(?:\s*[-–—,，、;]\s*\d{1,3})*[\]］]"
                       r"|\[\^[^\]\s]+\]")
# ASCII lookbehind: a Han character before @ does not hide a citation key; an e-mail address does.
BARE_CITE = re.compile(r"(?<![A-Za-z0-9_.@\\/])-?@[A-Za-z0-9_](?:[A-Za-z0-9_:.+/-]*[A-Za-z0-9_])?")
URL_CHAR = r"[^\s<>{}\"'`，。；：！？、（）【】「」《》]"
URL = re.compile(rf"(?:https?://|www\.){URL_CHAR}+|(?:doi:\s*)?10\.\d{{4,9}}/{URL_CHAR}+", re.I)
TEX_ESCAPE = {"%": "\\%", "&": "\\&", "#": "\\#", "_": "\\_", "$": "\\$", "{": "\\{", "}": "\\}", "\u2009": "\\,"}


def fail(message: str):
    print(message, file=sys.stderr)
    raise SystemExit(2)


def docx_text(path: Path) -> str:
    """A .docx as plain paragraphs: headings as "#", a table as a Markdown table, each equation as
    an [Author input needed: …] placeholder. Text that a tracked change deleted is left out."""
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
        return "".join((node.text or "") if node.tag == W + "t" else " " if node.tag in (W + "tab", W + "br")
                       else equation() if node.tag == EQUATION else "" for node in p.iter()).strip()

    def equation() -> str:
        equations.append(1)
        return f"[Author input needed: equation {len(equations)} of the .docx goes here]"   # its text is not read

    out, equations = [], []
    for block in blocks(body):
        if block.tag == W + "p":
            style = block.find(f"{W}pPr/{W}pStyle")
            level = re.match(r"(?i)heading\s*(\d)", style.get(W + "val", "")) if style is not None else None
            text = paragraph(block)
            out.append(("#" * int(level.group(1)) + " " if level and text else "") + text)
        else:
            rows = [[" ".join(filter(None, map(paragraph, cell.iter(W + "p")))) for cell in row.iter(W + "tc")]
                    for row in block.iter(W + "tr")]
            lines = ["| " + " | ".join(cells) + " |" for cells in rows]
            out += ["\n".join(lines[:1] + ["|" + "---|" * len(rows[0])] + lines[1:])] if rows else []
    return "\n\n".join(out)


def read_source(path: Path) -> tuple[str, bool]:
    """(text, is LaTeX). Plain text and the text of a .docx are read like Markdown."""
    if not path.is_file():
        fail(f"No such file: {path}")
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return docx_text(path), False
    if suffix not in (".md", ".markdown", ".tex", ".txt"):
        fail(f"{path}: give a .md, .tex, .txt or .docx file")
    return path.read_text(encoding="utf-8-sig", errors="replace"), suffix == ".tex"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------
# Masking


def group_end(text: str, i: int, close: str) -> int:
    """The index after the group that opens at text[i] and closes with `close`, or -1."""
    opening, depth = text[i], 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        depth += (text[i] == opening) - (text[i] == close)
        i += 1
        if depth == 0:
            return i
    return -1


def arguments(text: str, j: int) -> list:
    """The [..] and {..} groups right after a command name that ends at j. Spaces may precede a
    {group}; a [group] must follow at once, so that "\\LaTeX [3]" keeps its citation."""
    groups = []
    while True:
        k = j + len(text[j:]) - len(text[j:].lstrip(" \t"))
        end = group_end(text, k, "}" if text[k] == "{" else "]") \
            if k < len(text) and (text[k] == "{" or (text[k] == "[" and k == j)) else -1
        if end < 0:
            return groups
        groups.append((k, end))
        j = end


def env_end(text: str, i: int, name: str) -> int:
    depth = 0
    for m in re.finditer(r"\\(begin|end)\s*\{" + re.escape(name) + r"\}", text[i:]):
        depth += 1 if m.group(1) == "begin" else -1
        if depth == 0:
            return i + m.end()
    return len(text)


def dollar_end(text: str, i: int, tex: bool) -> int:
    """The end of the formula opening with $ or $$ at i, or -1. Outside LaTeX the opening $ has no
    space after it, the closing one no space before it and no digit after it, and no blank line
    lies between: "$5 and $6" stays text. A $ inside braces opens a nested formula."""
    double = text.startswith("$$", i)
    j, depth = i + 1 + double, 0
    if not (tex or double) and (j >= len(text) or text[j].isspace()):
        return -1
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "\n" and not tex and re.match(r"\n[ \t]*\n", text[j:j + 40]):
            return -1
        depth += (c == "{") - (c == "}")
        if c == "$" and depth <= 0 and (text.startswith("$$", j) if double else
                                        tex or not (text[j - 1].isspace() or text[j + 1:j + 2].isdigit())):
            return j + 1 + double
        j += 1
    return -1


def mask(text: str, tex: bool, n: int = 1) -> tuple[str, dict, int]:
    """(masked text, {token: raw text, or [opening, closing] for a pair}, next token number)."""
    out, tokens, stack, i = [], {}, [], 0

    def token(raw: str, close: str | None = None) -> None:
        nonlocal n
        tokens[f"T{n:04d}"] = raw if close is None else [raw, close]
        out.append(f"⟦T{n:04d}⟧")
        stack.extend([f"T{n:04d}"] if close else [])
        n += 1

    while i < len(text):
        c, end, m = text[i], 0, None
        if c == "\\":
            m = COMMAND.match(text, i)
            name, symbol = (m.group(1), m.group(2)) if m else (None, "")
            if symbol in ("(", "["):
                j = text.find("\\)" if symbol == "(" else "\\]", i + 2)
                end = j + 2 if j >= 0 else len(text)
            elif tex and symbol and symbol in "%&#_${},":
                out.append("\u2009" if symbol == "," else symbol)          # unmask escapes it again
                i += 2
                continue
            elif symbol is not None:
                end = LINE_BREAK.match(text, i).end() if symbol == "\\" else i + 1 + bool(m)
            elif name == "begin" and (env := re.match(r"\s*\{([^{}]*)\}", text[m.end():])) \
                    and WHOLE_ENV.fullmatch(env.group(1)):
                end = env_end(text, i, env.group(1))
            elif name in NOARG:
                end = m.end()
            else:
                groups = arguments(text, m.end())
                end = groups[-1][1] if groups else m.end()
                if name in PROSE and groups and text[groups[-1][0]] == "{":
                    token(text[i:groups[-1][0] + 1], "}")
                    i = groups[-1][0] + 1
                    continue
        elif c in "}]" and stack and tokens[stack[-1]][1] == c:
            out.append(f"⟦/{stack.pop()}⟧")
            i += 1
            continue
        elif c == "{" and tex:
            token("{", "}")
            i += 1
            continue
        elif c == "[" and (m := PLACEHOLDER.match(text, i)):
            token(m.group(0), "]")
            i = m.end()
            continue
        elif c == "$":
            end = dollar_end(text, i, tex)
        elif c == "%" and tex:
            end = text.find("\n", i) + 1 or len(text)
        elif c == "}" and tex:
            end = i + 1                                     # its group opened in another unit
        elif c in "[［":
            end = (m := BRACKETED.match(text, i)) and m.end() or 0
        elif not tex and c == "`":
            run = re.match(r"`+", text[i:]).group(0)
            end = text.find(run, i + len(run)) + len(run) if run in text[i + len(run):] else 0
        elif not tex and c == "|":
            end = i + 1                                     # a table cell border
        elif not tex and c == "@":
            end = (m := BARE_CITE.match(text, i)) and m.end() or 0
        elif c in "hwHWd1" and not re.match(r"[A-Za-z0-9_/.]", text[i - 1:i] or " ") and (m := URL.match(text, i)):
            found = m.group(0)
            while found[-1] in ".,;:!?" or (found[-1] == ")" and found.count(")") > found.count("(")):
                found = found[:-1]
            end = i + len(found)
        if end > i:
            token(text[i:end])
            i = end
        else:
            out.append(c)
            i += 1
    for name in stack:                      # a group that closes in another unit stays as written
        tokens[name] = tokens[name][0]
    return "".join(out), tokens, n


def has_prose(text: str, tex: bool) -> bool:
    return bool(re.search(r"[^\W\d_]", TOKEN.sub(" ", mask(text, tex)[0])))


# ---------------------------------------------------------------------------------------------
# Splitting

HEAD_TEX = re.compile(r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph|title)\*?"
                      r"\s*(?:\[[^\]]*\])?\s*\{")
BEGIN = re.compile(r"\\begin\s*\{([^{}]+)\}")
STRUCTURE = re.compile(r"\\(?:begin|end)\s*\{[^{}]+\}(?:\s*\[[^\]]*\])?|\\item\b(?:\s*\[[^\]]*\])?")
CAPTION = re.compile(r"\\(?:sub)?caption(?:of)?\*?")
FENCE = re.compile(r"\s{0,3}(`{3,}|~{3,})")
MD_HEAD = re.compile(r"\s{0,3}#{1,6}\s+")
TABLE_RULE = re.compile(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?$")
MARKER = re.compile(r"\s*(?:[-*+•]\s+|\d{1,3}[.)]\s+|\d{1,2}[、）]\s*|[（(]\d{1,2}[)）]\s*|[①-⑳]\s*|>+\s?)")


def split(text: str, tex: bool) -> list:
    """[(type, start, end)] in reading order. Kept blocks: display maths, code, LaTeX floats and
    tables. The gaps between blocks (blank lines, list markers, structure commands) stay as they are."""
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    lines = [(s, (text.find("\n", s) + 1 or len(text) + 1) - 1) for s in starts]
    blocks, cur, k, body = [], [], 0, not tex or "\\begin{document}" not in text

    def flush() -> None:
        blocks.extend([tuple(cur)] if cur else [])
        cur.clear()

    def begin(kind: str, a: int, b: int) -> None:
        flush()
        cur.extend([kind, a, b] if text[a:b].strip() else [])

    def through(end: int) -> int:           # skip the lines a block spans; the end of its last line
        nonlocal k
        while k < len(lines) and lines[k][0] < end:
            k += 1
        return max(lines[k - 1][1], end) if k else end

    while k < len(lines):
        a, b = lines[k]
        k += 1
        line = text[a:b]
        lead, s = a + len(line) - len(line.lstrip()), line.strip()
        head = HEAD_TEX.match(text, lead) if tex else MD_HEAD.match(line)
        if head and tex and (body or "\\title" in head.group(0)) and (end := group_end(text, head.end() - 1, "}")) > 0:
            flush()
            blocks.append(("heading", head.end(), end - 1))
            begin("paragraph", end, through(end)) if body else through(end)
            continue
        if not body:
            body = "\\begin{document}" in line
            continue
        if not s:
            flush()
            continue
        env, fence = BEGIN.match(text, lead), None if tex else FENCE.match(line)
        if env and KEPT_ENV.fullmatch(env.group(1)):
            flush()
            end = through(env_end(text, lead, env.group(1)))
            blocks += float_blocks(text, lead, end) if re.fullmatch(rf"(?:{FLOAT_ENV})\*?", env.group(1)) \
                else [("kept", lead, end)]
        elif s.startswith(("$$", "\\[")) or fence:
            flush()
            if fence:
                mark = re.escape(fence.group(1)[0])
                close = re.compile(rf"\n\s{{0,3}}{mark}{{{len(fence.group(1))},}}[ \t]*(?:\n|$)")
                found = close.search(text, b)
                end = found.end() if found else len(text)
            else:
                close = text.find("$$" if s.startswith("$$") else "\\]", lead + 2)
                end = close + 2 if close >= 0 else len(text)
            blocks.append(("kept", lead, through(end)))
        elif tex and (structure := STRUCTURE.match(text, lead)):
            begin("item" if s.startswith("\\item") else "paragraph", structure.end(), b)
        elif not tex and head:
            flush()
            blocks.append(("heading", a + head.end(), a + len(re.sub(r"\s+#+\s*$", "", line))))
        elif not tex and s.startswith("|"):
            flush()
            if not TABLE_RULE.match(s):
                blocks.append(("row", a + line.index("|") + 1, a + line.rindex("|") if s.endswith("|") else b))
        elif not tex and (marker := MARKER.match(line)):
            begin("item", a + marker.end(), b)
        elif cur and cur[0] in ("paragraph", "item"):
            cur[2] = b
        else:
            begin("paragraph", lead, b)
    flush()
    return blocks


def float_blocks(text: str, a: int, b: int) -> list:
    """A figure or table environment: kept, except the text of each caption."""
    out, pos = [], a
    for m in CAPTION.finditer(text, a, b):
        braces = [g for g in arguments(text, m.end()) if text[g[0]] == "{"]
        if braces and braces[-1][1] <= b:
            out += [("kept", pos, braces[-1][0] + 1), ("caption", braces[-1][0] + 1, braces[-1][1] - 1)]
            pos = braces[-1][1] - 1
    return out + [("kept", pos, b)]


def units_of(text: str, tex: bool) -> list[dict]:
    """The blocks with ids: u0001… to translate, k001… kept. A block with no letters outside its
    tokens (a row of numbers, a lone citation) is kept."""
    out, counts = [], Counter()
    for kind, a, b in split(text, tex):
        a, b = a + len(text[a:b]) - len(text[a:b].lstrip()), b - len(text[a:b]) + len(text[a:b].rstrip())
        if a < b:
            kind = kind if kind != "kept" and has_prose(text[a:b], tex) else "kept"
            counts[kind == "kept"] += 1
            out.append({"id": f"k{counts[True]:03d}" if kind == "kept" else f"u{counts[False]:04d}", "type": kind,
                        "start": a, "end": b, "line": text.count("\n", 0, a) + 1})
    return out


# ---------------------------------------------------------------------------------------------
# Restoring


def restore(value: str, tokens: dict, tex: bool) -> tuple[str | None, list[str]]:
    """The translated unit with its tokens put back, or None and the reasons it cannot be."""
    found = TOKEN.findall(value)
    seen, problems, stack = Counter(found), [], []
    for name, raw in tokens.items():
        for slash in ("", "/") if isinstance(raw, list) else ("",):
            if seen[(slash, name)] != 1:
                problems.append(f"⟦{slash}{name}⟧ {'duplicated' if seen[(slash, name)] else 'missing'}")
    problems += [f"⟦{s}{t}⟧ is not a token of this unit" for s, t in dict.fromkeys(found)
                 if t not in tokens or (s and not isinstance(tokens[t], list))]
    for slash, name in (f for f in found if isinstance(tokens.get(f[1]), list)):
        if slash and (not stack or stack.pop() != name):
            problems.append(f"⟦/{name}⟧ comes before its ⟦{name}⟧ or crosses another pair")
            break
        stack.extend([] if slash else [name])
    prose = TOKEN.sub(" ", value)
    if "\\" in prose:
        at = prose.index("\\")
        problems.append(f"backslash outside the tokens: …{prose[max(0, at - 15):at + 15]}…")
    if "⟦" in prose or "⟧" in prose:
        problems.append("a broken token: ⟦ or ⟧ outside a token")
    if problems:
        return None, problems
    out, pieces = [], TOKEN.split(value)            # text, slash, name, text, slash, name, …, text
    for k in range(0, len(pieces), 3):
        out.append("".join(TEX_ESCAPE.get(ch, ch) for ch in pieces[k]) if tex else pieces[k])
        if k + 2 < len(pieces):
            raw = tokens[pieces[k + 2]]
            out.append(raw if isinstance(raw, str) else raw[bool(pieces[k + 1])])
            if re.search(r"\\[A-Za-z@]+\*?$", out[-1]) and pieces[k + 3][:1].isalpha():
                out.append(" ")             # \LaTeX文 or \LaTeXis would read as one unknown command
    return "".join(out), []


def cmd_split(args) -> int:
    path = Path(args.source)
    text, tex = read_source(path)
    units, kept_with_text, n = [], [], 1
    for block in units_of(text, tex):
        raw = text[block["start"]:block["end"]]
        if block["type"] == "kept":
            if has_prose(raw, tex):                                 # a LaTeX table with words in its cells
                kept_with_text.append({"id": block["id"], "line": block["line"], "text": raw[:80]})
            continue
        masked, tokens, n = mask(raw, tex, n)
        units.append({**block, "source": raw, "masked": masked, "tokens": tokens})
    if not units:
        fail(f"No text to translate in {path}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data = {"tool": TOOL, "source": {"path": str(path), "sha256": sha256(path)}, "units": units}
    (out / "units.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"units": len(units), "by_type": dict(Counter(u["type"] for u in units)), "tokens": n - 1,
                      "characters": sum(len(TOKEN.sub("", u["masked"])) for u in units),
                      "kept_with_text": kept_with_text, "units_file": str(out / "units.json"),
                      "write": str(out / "units.translated.json")}, indent=2, ensure_ascii=False))
    return 0


def cmd_unmask(args) -> int:
    out = Path(args.out)
    try:
        data = json.loads((out / "units.json").read_text(encoding="utf-8"))
        translated = json.loads((out / "units.translated.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"Cannot read {out / 'units.json'} and {out / 'units.translated.json'}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("units"), list) or "path" not in data.get("source", {}):
        fail(f"{out / 'units.json'} was not written by tr_units.py split: run split again")
    translated = translated.get("units", translated) if isinstance(translated, dict) else {}
    source = Path(data["source"]["path"])
    if not source.is_file() or sha256(source) != data["source"]["sha256"]:
        fail(f"{source} is missing or has changed since split: run split again")
    text, tex = read_source(source)
    log_path = out / "unmask.json"
    try:
        previous = json.loads(log_path.read_text(encoding="utf-8")) if log_path.is_file() else {}
    except ValueError:
        previous = {}                       # an unreadable log protects nothing: the output check below refuses
    suffix = ".md" if source.suffix.lower() == ".docx" else source.suffix
    target = Path(args.output or out / f"{source.stem}.translated{suffix}")
    if target.resolve() == source.resolve():
        fail("The output would replace the source file: choose another --output")
    if target.is_file() and previous.get("output", {}).get("sha256") != sha256(target):
        fail(f"{target} exists and was not written by unmask, or was edited after it: change "
             "units.translated.json instead, or pass --output")
    pieces, pos, log, summary = [], 0, {}, {"restored": 0, "kept_source": [], "missing": [], "unchanged": []}
    for unit in data["units"]:
        value, restored, problems = translated.get(unit["id"]), None, ["no translation"]
        if isinstance(value, str) and value.strip():
            value = value.strip()
            if unit["type"] in ("heading", "row", "caption"):        # one line each
                value = re.sub(r"\s*\n\s*", " ", value)
            restored, problems = restore(value, unit["tokens"], tex)
        attempts = previous.get("units", {}).get(unit["id"], {}).get("attempts", 0) + bool(problems and value)
        if problems and value:
            summary["kept_source"].append({"id": unit["id"], "line": unit["line"], "attempts": attempts,
                                           "problems": problems})
        elif problems:
            summary["missing"].append(unit["id"])
        else:
            summary["restored"] += 1
            summary["unchanged"] += [unit["id"]] if value == unit["masked"].strip() else []
        log[unit["id"]] = {"status": "kept_source" if problems else "restored", "attempts": attempts,
                           "problems": problems}
        pieces += [text[pos:unit["start"]], unit["source"] if problems else restored]
        pos = unit["end"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(pieces) + text[pos:], encoding="utf-8")
    log_path.write_text(json.dumps({"tool": TOOL, "output": {"path": str(target), "sha256": sha256(target)},
                                    "units": log}, indent=1, ensure_ascii=False), encoding="utf-8")
    summary.update(units=len(data["units"]), output=str(target),
                   tell_user=[u["id"] for u in summary["kept_source"] if u["attempts"] >= 3],
                   unknown_ids=sorted(set(translated) - {u["id"] for u in data["units"]}))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary["kept_source"] or summary["missing"] else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Translation units: split and mask a text, then restore it.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("split", help="Write units.json: units with their masked text and tokens")
    p.add_argument("source", help="A .md, .tex, .txt or .docx file")
    p.add_argument("--out", default="translation", help="Output folder (default: translation)")
    p = sub.add_parser("unmask", help="Check units.translated.json and write the translated file")
    p.add_argument("--out", default="translation", help="The folder of units.json (default: translation)")
    p.add_argument("--output", help="The translated file (default: <out>/<name>.translated.<ext>)")
    args = parser.parse_args(argv)
    return cmd_split(args) if args.command == "split" else cmd_unmask(args)


if __name__ == "__main__":
    sys.exit(main())
