#!/usr/bin/env python3
"""Content guard for a LaTeX paper: snapshot before a fix, compare after it, list layout overrides.

  latex_guard.py snapshot main.tex -o latex-build/before.json
  latex_guard.py compare latex-build/before.json latex-build/after.json [--tolerance 0.1]
  latex_guard.py overrides main.tex

snapshot   follows \\input, \\include, \\subfile and \\import from the main file and records, each
           with file and line: labels, citation keys, \\includegraphics targets, section titles, the
           number of floats, bibliography files, packages and layout overrides, plus the word count
           of the text (from \\begin{document} on, and the title; comments and commands stripped,
           each formula counted as one word).
compare    lists every difference between two snapshots. Exit 1 when content changed: a label,
           citation, figure, float or section title was removed or renamed, a layout override was
           added, or the word count moved by more than the tolerance (default 0.1 per cent of the
           words before, and at least 2 words). A figure whose file was missing, replaced by one whose
           file exists, is listed as a corrected path, not as a change.
overrides  lists layout overrides with file and line: negative \\vspace or \\vskip, line spacing
           (\\baselinestretch, \\linespread, \\setstretch), \\geometry or margin lengths, float and
           display spacing lengths, \\looseness, \\enlargethispage, scaled or resized boxes, and
           \\small, \\footnotesize, \\scriptsize or \\tiny switched on for a whole float or for the
           rest of the document. It only reports (exit 0).

compare and overrides also write compare.md or overrides.md in --out (default latex-build).
Standard library only. latex_log.py and latex_pack.py import the tree walker from this file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Environments whose content TeX does not read as ordinary text: never touch a % inside them.
VERBATIM_ENVS = {"verbatim", "verbatim*", "Verbatim", "Verbatim*", "BVerbatim", "LVerbatim", "lstlisting",
                 "minted", "filecontents", "filecontents*", "comment"}
TWO_ARG_INPUTS = {"import", "subimport", "includefrom", "subincludefrom", "inputfrom", "subinputfrom"}
INPUT_RE = re.compile(r"\\(input|include|subfile|import|subimport|includefrom|subincludefrom|inputfrom|subinputfrom)"
                      r"(?![A-Za-z@])")
LABEL_RE = re.compile(r"\\label\s*(?:\[[^\]]*\]\s*)?\{([^{}]*)\}")
CITE_RE = re.compile(r"\\(?!citestyle\b|defcitealias\b)([A-Za-z]*cite[A-Za-z]*)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^{}]*)\}")
GRAPHICS_RE = re.compile(r"\\(includegraphics|includesvg|includepdf)\*?\s*(?:\[[^\]]*\]\s*)?\{([^{}]*)\}")
SECTION_RE = re.compile(r"\\(part|chapter|section|subsection|subsubsection|paragraph)(\*?)\s*(?:\[[^\]]*\]\s*)?(?=\{)")
GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\})*)\s*\}")
GRAPHIC_EXTS = ("", ".pdf", ".png", ".jpg", ".jpeg", ".eps", ".ps", ".mps", ".PDF", ".PNG", ".JPG", ".JPEG", ".EPS", ".svg")
FLOAT_RE = re.compile(r"\\begin\s*\{((?:figure|table|algorithm|wrapfigure|wraptable|sidewaysfigure|sidewaystable)\*?)\}")
BIB_RE = re.compile(r"\\(bibliography|addbibresource|bibliographystyle)\s*(?:\[[^\]]*\]\s*)?\{([^{}]*)\}")
PACKAGE_RE = re.compile(r"\\(?:usepackage|RequirePackage)\s*(?:\[([^\]]*)\]\s*)?\{([^{}]*)\}")
CLASS_RE = re.compile(r"\\documentclass\s*(?:\[([^\]]*)\]\s*)?\{([^{}]*)\}")
BEGIN_DOC_RE = re.compile(r"\\begin\s*\{document\}")
END_DOC_RE = re.compile(r"\\end\s*\{document\}")

_LENGTHS_MARGIN = r"textheight|textwidth|oddsidemargin|evensidemargin|topmargin|headheight|headsep|footskip|" \
                  r"marginparwidth|marginparsep|columnsep|hoffset|voffset"
_LENGTHS_SPACING = r"textfloatsep|floatsep|intextsep|dbltextfloatsep|dblfloatsep|abovecaptionskip|belowcaptionskip|" \
                   r"abovedisplayskip|belowdisplayskip|abovedisplayshortskip|belowdisplayshortskip|" \
                   r"parskip|baselineskip|topskip"
OVERRIDES = [
    ("negative_space", r"\\(?:vspace|addvspace)\*?\s*\{\s*-|\\vskip\s*-"),
    ("line_spacing", r"\\renewcommand\s*\{?\s*\\baselinestretch|\\def\s*\\baselinestretch|\\linespread\s*\{|"
                     r"\\setstretch\s*\{|\\begin\s*\{spacing\}"),
    ("margins", r"\\(?:geometry|newgeometry)\s*\{|\\usepackage\s*(?:\[[^\]]*\])?\s*\{[^}]*\bgeometry\b|"
                rf"\\(?:setlength|addtolength)\s*\{{?\s*\\(?:{_LENGTHS_MARGIN})\b|\\(?:{_LENGTHS_MARGIN})\s*=?\s*-?\d"),
    ("float_or_display_spacing", rf"\\(?:setlength|addtolength)\s*\{{?\s*\\(?:{_LENGTHS_SPACING})\b|"
                                 rf"\\(?:{_LENGTHS_SPACING})\s*=?\s*-?\d|\\titlespacing\b"),
    ("looseness", r"\\looseness\s*=?\s*-?\d"),
    ("enlargethispage", r"\\enlargethispage\*?\s*\{"),
    ("scaled_text", r"\\(?:resizebox|scalebox)\*?\s*\{|\\fontsize\s*\{"),
    ("compression_package", r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{[^}]*\bsavetrees\b"),
]
OVERRIDE_RES = [(kind, re.compile(pattern)) for kind, pattern in OVERRIDES]
SIZE_RE = re.compile(r"\\[{}]|\\begin\s*\{([^{}]*)\}|\\end\s*\{([^{}]*)\}|"
                     r"\\(small|footnotesize|scriptsize|tiny)(?![A-Za-z@])|([{}])")
SIZE_NAMES = {"small", "footnotesize", "scriptsize", "tiny"}
FLOATS = {"figure", "figure*", "table", "table*", "wrapfigure", "wraptable", "sidewaysfigure", "sidewaystable",
          "algorithm", "algorithm*"}

MATH_RE = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath|math|flalign|alignat)(\*?)\}.*?"
                     r"\\end\{\1\2\}|\\\[.*?\\\]|\\\(.*?\\\)|(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$.+?(?<!\\)\$", re.S)
DROP_NAMES = (r"label|ref|eqref|pageref|autoref|[cC]ref|nameref|vref|[A-Za-z]*cite[A-Za-z]*|includegraphics|includesvg|"
              r"includepdf|input|include|subfile|import|subimport|bibliography|bibliographystyle|addbibresource|"
              r"usepackage|documentclass|url|href|graphicspath|vspace|hspace|setlength|addtolength|setcounter|"
              r"newcommand|renewcommand|providecommand|hypersetup|captionsetup|linespread|enlargethispage|"
              r"lstinputlisting|end")
DROP_RE = re.compile(r"\\begin\s*\{[^{}]*\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?|"
                     rf"\\(?:{DROP_NAMES})(?![A-Za-z@])\*?(?:\s*\[[^\]]*\])*\s*\{{[^{{}}]*(?:\{{[^{{}}]*\}}[^{{}}]*)*\}}")
WORD_RE = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")


def strip_comments(text: str, keep_lines: bool = False) -> str:
    """Remove TeX comments without changing what TeX typesets.

    A % after an odd number of backslashes is a character, not a comment. Nothing changes inside
    verbatim-like environments, \\verb, \\lstinline, \\mintinline, \\url and \\href's address. A line
    that is only a comment is dropped (blanked with keep_lines, so line numbers stay); a comment
    after text keeps its %, so the line end still produces no space, unless the text before it ends
    in a blank, where the % made no difference.
    """
    out, env = [], None
    for line in text.split("\n"):
        ending = "\r" if line.endswith("\r") else ""
        line = line[:-1] if ending else line
        i, cut = 0, None
        while i < len(line):
            if env:
                end = line.find("\\end{%s}" % env, i)
                if end < 0:
                    break
                i, env = end + len(env) + 6, None
                continue
            char = line[i]
            if char == "%":
                cut = i
                break
            if char != "\\":
                i += 1
                continue
            match = re.match(r"\\([A-Za-z@]+\*?|.?)", line[i:])
            name, i = match.group(1), i + match.end()
            if name == "begin":
                env_match = re.match(r"\s*\{([^{}]*)\}", line[i:])
                if env_match and env_match.group(1) in VERBATIM_ENVS:
                    env, i = env_match.group(1), i + env_match.end()
            elif name in ("verb", "verb*", "lstinline") and i < len(line) and line[i] not in "{[ ":
                close = line.find(line[i], i + 1)
                i = len(line) if close < 0 else close + 1
            elif name in ("lstinline", "mintinline", "url", "href", "path"):
                if name == "mintinline":
                    _, i = braced(line, i)
                content, after = braced(line, i)
                i = after if content is not None else i
        if cut is None:
            out.append(line + ending)
        elif not line[:cut].strip():
            if keep_lines:
                out.append(ending)
        elif line[cut - 1] in " \t":
            out.append(line[:cut].rstrip() + ending)
        else:
            out.append(line[:cut + 1] + ending)
    return "\n".join(out)


def braced(text: str, i: int):
    """(content, index after the closing brace) for a brace group at text[i] (blanks skipped)."""
    while i < len(text) and text[i] in " \t":
        i += 1
    if i >= len(text) or text[i] != "{":
        return None, i
    depth, j = 0, i
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[i + 1:j], j + 1
        j += 1
    return None, i


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def unsafe_path(target: str) -> str:
    if target.startswith(("/", "~")) or re.match(r"[A-Za-z]:[\\/]", target):
        return "absolute path"
    if ".." in Path(target).parts:
        return "path leaves the folder (..)"
    return ""


def input_targets(text: str):
    """(command, target, offset) for each \\input-like command in comment-stripped text."""
    for match in INPUT_RE.finditer(text):
        name, j = match.group(1), match.end()
        if name in TWO_ARG_INPUTS:
            folder, j = braced(text, j)
            target, j = braced(text, j)
            if folder is not None and target is not None:
                yield name, (folder.rstrip("/") + "/" + target).lstrip("/") if folder else target, match.start()
            continue
        target, j = braced(text, j)
        if target is None and name == "input":
            bare = re.match(r"\s+([^\s{}%\\]+)", text[j:])
            target = bare.group(1) if bare else None
        if target:
            yield name, target.strip(), match.start()


def resolve(target: str, here: Path, root: Path, name: str = "input"):
    bases = [here, root] if name in ("subimport", "subincludefrom", "subinputfrom", "subfile") else [root, here]
    names = [target] if target.endswith(".tex") else [target + ".tex", target]
    for base in bases:
        for candidate in names:
            path = (base / candidate).expanduser()
            if path.is_file():
                return path.resolve()
    return None


def read_tree(main: Path) -> dict:
    """Every file reached from main through \\input-like commands, in reading order."""
    main, root = main.resolve(), main.resolve().parent
    files, missing, seen = [], [], set()

    def visit(path: Path, preamble: bool):
        if path in seen:
            return
        seen.add(path)
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = strip_comments(raw, keep_lines=True)
        begin = BEGIN_DOC_RE.search(text)
        body_start = begin.end() if begin and path == main else (len(text) if preamble else 0)
        end = END_DOC_RE.search(text, body_start)
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = str(path)
        entry = {"path": path, "rel": rel, "raw": raw, "text": text, "body": (body_start, end.start() if end else len(text)),
                 "outside": root not in path.parents and path != main}
        files.append(entry)
        for name, target, offset in input_targets(text):
            found = resolve(target, path.parent, root, name)
            where = f"{rel}:{line_of(text, offset)}"
            if found is None:
                missing.append({"command": name, "target": target, "at": where, "problem": unsafe_path(target)})
            else:
                visit(found, offset < body_start)

    visit(main, False)
    return {"main": main, "root": root, "files": files, "missing_inputs": missing}


def words(text: str) -> int:
    text = MATH_RE.sub(" xmathx ", text)
    text = DROP_RE.sub(" ", text)
    text = re.sub(r"\\[A-Za-z@]+\*?|\\.", " ", text)
    return len(WORD_RE.findall(re.sub(r"[{}\[\]~&#^_]", " ", text)))


def find_overrides(tree: dict) -> list:
    found = []
    for entry in tree["files"]:
        text, rel = entry["text"], entry["rel"]
        for kind, pattern in OVERRIDE_RES:
            for match in pattern.finditer(text):
                found.append({"kind": kind, "at": f"{rel}:{line_of(text, match.start())}",
                              "text": source_line(text, match.start())})
        start, end = entry["body"]
        stack, depth = [("document", 0)], 0
        for match in SIZE_RE.finditer(text, start, end):
            begin, finish, size, brace = match.groups()
            if brace:
                depth += 1 if brace == "{" else -1
            elif begin is not None:
                if begin in SIZE_NAMES:
                    size = begin
                stack.append((begin, depth))
            elif finish is not None and len(stack) > 1 and stack[-1][0] == finish:
                stack.pop()
            if size:
                env, env_depth = stack[-2] if begin in SIZE_NAMES else stack[-1]
                if depth == env_depth and (env in FLOATS or env == "document"):
                    scope = f"the whole {env} environment" if env in FLOATS else "all text after it"
                    found.append({"kind": "font_size", "at": f"{rel}:{line_of(text, match.start())}",
                                  "text": source_line(text, match.start()), "note": f"\\{size} applies to {scope}"})
    return sorted(found, key=lambda item: (item["at"].rsplit(":", 1)[0], int(item["at"].rsplit(":", 1)[1])))


def source_line(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start:end if end >= 0 else len(text)].strip()[:160]


def snapshot(main: Path) -> dict:
    tree = read_tree(main)
    result = {"tool": "researchzy-latex", "kind": "snapshot", "main": main.name, "root": str(tree["root"]),
              "taken": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": [], "labels": [],
              "citations": [], "graphics": [], "sections": [], "floats": {}, "bibliography": [], "packages": [],
              "documentclass": None, "words": 0, "missing_inputs": tree["missing_inputs"]}
    floats = Counter()
    prefixes = [""] + [p for e in tree["files"] for m in GRAPHICSPATH_RE.finditer(e["text"])
                       for p in re.findall(r"\{([^{}]*)\}", m.group(1))]
    for entry in tree["files"]:
        text, rel = entry["text"], entry["rel"]
        start, end = entry["body"]
        count = words(text[start:end])
        if entry["path"] == tree["main"]:
            title = re.search(r"\\title\s*(?:\[[^\]]*\])?(?=\{)", text[:start])
            count += words(braced(text, title.end())[0] or "") if title else 0
        result["words"] += count
        digest = hashlib.sha256(entry["raw"].encode("utf-8")).hexdigest()
        result["files"].append({"path": rel, "sha256": digest, "words": count})

        def at(pos):
            return f"{rel}:{line_of(text, pos)}"
        result["labels"] += [{"key": m.group(1).strip(), "at": at(m.start())} for m in LABEL_RE.finditer(text)]
        for m in CITE_RE.finditer(text):
            result["citations"] += [{"key": k.strip(), "at": at(m.start())} for k in m.group(2).split(",") if k.strip()]
        bases = (tree["root"], entry["path"].parent)
        result["graphics"] += [{"target": m.group(2).strip(), "at": at(m.start()),
                                "found": any((base / (prefix + m.group(2).strip() + ext)).is_file()
                                             for base in bases for prefix in prefixes for ext in GRAPHIC_EXTS)}
                               for m in GRAPHICS_RE.finditer(text)]
        for m in SECTION_RE.finditer(text):
            title = braced(text, m.end())[0] or ""
            result["sections"].append({"level": m.group(1) + m.group(2), "title": " ".join(title.split()),
                                       "at": at(m.start())})
        floats.update(m.group(1) for m in FLOAT_RE.finditer(text))
        result["bibliography"] += [{"command": m.group(1), "value": m.group(2).strip(), "at": at(m.start())}
                                   for m in BIB_RE.finditer(text)]
        for m in PACKAGE_RE.finditer(text):
            result["packages"] += [{"name": n.strip(), "options": (m.group(1) or "").strip(), "at": at(m.start())}
                                   for n in m.group(2).split(",") if n.strip()]
        klass = CLASS_RE.search(text)
        if klass and result["documentclass"] is None:
            result["documentclass"] = {"name": klass.group(2).strip(), "options": (klass.group(1) or "").strip()}
    result["floats"] = dict(sorted(floats.items()))
    result["overrides"] = find_overrides(tree)
    return result


def compare(before: dict, after: dict, tolerance: float) -> dict:
    def diff(field, key):
        old = Counter(key(item) for item in before.get(field, []))
        new = Counter(key(item) for item in after.get(field, []))
        return sorted((old - new).elements()), sorted((new - old).elements())

    removed, added = {}, {}
    for field, key in (("labels", lambda i: i["key"]), ("citations", lambda i: i["key"]),
                       ("graphics", lambda i: i["target"]), ("sections", lambda i: f'{i["level"]}: {i["title"]}'),
                       ("bibliography", lambda i: f'{i["command"]}{{{i["value"]}}}'),
                       ("packages", lambda i: i["name"]), ("overrides", lambda i: f'{i["kind"]}: {i["text"]}')):
        removed[field], added[field] = diff(field, key)
    # A graphic whose file was missing, replaced by one whose file exists, is a corrected path.
    missing_before = [t for t in removed["graphics"] if any(g["target"] == t and g.get("found") is False
                                                             for g in before.get("graphics", []))]
    found_after = [t for t in added["graphics"]
                   if any(g["target"] == t and g.get("found") for g in after.get("graphics", []))]
    path_fixes = list(zip(missing_before, found_after))
    for old, new in path_fixes:
        removed["graphics"].remove(old)
        added["graphics"].remove(new)
    floats_old, floats_new = Counter(before.get("floats", {})), Counter(after.get("floats", {}))
    removed["floats"], added["floats"] = dict(floats_old - floats_new), dict(floats_new - floats_old)
    allowed = max(2, round(before["words"] * tolerance / 100))
    delta = after["words"] - before["words"]
    old_files = {f["path"]: f for f in before.get("files", [])}
    new_files = {f["path"]: f for f in after.get("files", [])}
    files = {"changed": sorted(p for p in old_files.keys() & new_files.keys()
                               if old_files[p]["sha256"] != new_files[p]["sha256"]),
             "added": sorted(new_files.keys() - old_files.keys()), "removed": sorted(old_files.keys() - new_files.keys()),
             "word_changes": {p: new_files.get(p, {}).get("words", 0) - old_files.get(p, {}).get("words", 0)
                              for p in sorted(old_files.keys() | new_files.keys())
                              if new_files.get(p, {}).get("words", 0) != old_files.get(p, {}).get("words", 0)}}
    reasons = [f"{field} removed or renamed: {', '.join(map(str, values))}" for field, values in removed.items()
               if values and field not in ("packages", "overrides", "bibliography")]
    reasons += [f"layout override added: {item}" for item in added["overrides"]]
    reasons += [f"bibliography command removed: {item}" for item in removed["bibliography"]]
    if abs(delta) > allowed:
        reasons.append(f"word count moved by {delta:+d} (allowed {allowed})")
    return {"tool": "researchzy-latex", "kind": "compare", "before": before.get("taken"), "after": after.get("taken"),
            "content_changed": bool(reasons), "reasons": reasons, "removed": removed, "added": added,
            "words": {"before": before["words"], "after": after["words"], "delta": delta, "allowed": allowed,
                      "tolerance_percent": tolerance}, "files": files, "graphics_path_fixes": path_fixes,
            "missing_inputs": {"before": [m["target"] for m in before.get("missing_inputs", [])],
                               "after": [m["target"] for m in after.get("missing_inputs", [])]}}


def write_md(path: Path, title: str, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot, compare and layout-override scan for a LaTeX paper.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("snapshot", help="Record the content of a paper")
    p.add_argument("main", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True, help="The snapshot file to write (must not exist)")
    p = sub.add_parser("compare", help="Compare two snapshots; exit 1 when content changed")
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    p.add_argument("--tolerance", type=float, default=0.1, help="Allowed word-count change in per cent (default 0.1)")
    p.add_argument("--out", type=Path, default=Path("latex-build"))
    p = sub.add_parser("overrides", help="List layout overrides in the source")
    p.add_argument("main", type=Path)
    p.add_argument("--out", type=Path, default=Path("latex-build"))
    args = parser.parse_args(argv)

    try:
        if args.command == "snapshot":
            if args.output.exists():
                raise ValueError(f"{args.output} exists: choose a new name (before.json, after.json, ...)")
            result = snapshot(args.main)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            summary = {k: len(result[k]) for k in ("files", "labels", "citations", "graphics", "sections", "overrides")}
            print(json.dumps({"snapshot": str(args.output), **summary, "words": result["words"], "floats": result["floats"],
                              "missing_inputs": result["missing_inputs"]}, indent=2, ensure_ascii=False))
            return 0
        if args.command == "compare":
            snaps = [json.loads(p.read_text(encoding="utf-8")) for p in (args.before, args.after)]
            if any(s.get("kind") != "snapshot" for s in snaps):
                raise ValueError("both files must be snapshots written by `latex_guard.py snapshot`")
            result = compare(*snaps, args.tolerance)
            lines = [f"Before: {args.before} ({result['before']}). After: {args.after} ({result['after']}).", "",
                     "**Content changed.**" if result["content_changed"] else "**No content change found.**", ""]
            lines += [f"- {reason}" for reason in result["reasons"]]
            w = result["words"]
            lines += ["", f"Words: {w['before']} before, {w['after']} after ({w['delta']:+d}; allowed {w['allowed']}).", ""]
            for label, part in (("Removed", result["removed"]), ("Added", result["added"])):
                lines += [f"- {label} {field}: {', '.join(map(str, v)) if isinstance(v, list) else v}"
                          for field, v in part.items() if v]
            lines += [f"- Figure path corrected: {old} -> {new}" for old, new in result["graphics_path_fixes"]]
            missing = result["missing_inputs"]
            lines += [f"- Inputs missing before: {', '.join(missing['before'])}; after: "
                      f"{', '.join(missing['after']) or 'none'}"] if missing["before"] else []
            lines += [f"- Files changed: {', '.join(result['files']['changed']) or 'none'}"]
            write_md(args.out / "compare.md", "Content comparison", lines)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["content_changed"] else 0
        tree = read_tree(args.main)
        found = find_overrides(tree)
        lines = ["Layout overrides in the source. A venue's kit sets the layout; none of these may be added to "
                 "make a paper fit. Report each one to the user.", ""]
        lines += [f"- `{item['at']}` {item['kind']}: `{item['text']}`" + (f" ({item['note']})" if item.get("note") else "")
                  for item in found] or ["None found."]
        write_md(args.out / "overrides.md", "Layout overrides", lines)
        print(json.dumps({"overrides": found, "count": len(found)}, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"latex_guard: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
