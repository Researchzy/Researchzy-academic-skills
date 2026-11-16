#!/usr/bin/env python3
"""Find how a LaTeX project is built, turn its log into a short problem list, and read PDF facts.

  latex_log.py detect paper/                     main file, engine, bibliography tool, latexmk command
  latex_log.py detect paper/main.tex
  latex_log.py parse paper/main.log [--blg paper/main.blg] [--hbox-pt 5] [--out latex-build]
  latex_log.py pdf paper/main.pdf [--page-size a4|letter|210x297mm] [--max-pages 8 --content-pages 8
                                   --limit-source "kit guide p. 2, https://..., read 2026-11-13"]

detect  The main file is a \\documentclass file that no other file inputs (all candidates are listed
        when there are several). The engine comes from latexmkrc, a `% !TEX program` line or the
        packages (fontspec and unicode-math need XeLaTeX or LuaLaTeX, xeCJK XeLaTeX, luacode LuaLaTeX),
        else pdfLaTeX; the bibliography tool from biblatex's backend, \\addbibresource, \\bibliography
        with \\bibliographystyle, or a .bbl without its .bib. Each choice comes with its evidence.
        Exit 1 when it cannot decide: several main files, or signals that conflict.
parse   Joins the lines TeX wraps at 79 columns, follows the file stack, and writes problems.json and
        problems.md: error, missing_file, undefined_reference, undefined_citation, duplicate_label,
        overfull (hbox above --hbox-pt, every vbox), font, package_warning, bibliography (the .blg of
        BibTeX or Biber; <stem>.blg next to the log is read when --blg is not given) and rerun_needed,
        each with file, line, message and count. The first error is marked; later errors may be its
        consequences. A PDF next to a log with errors is a failed build. Exit 1 when there is an
        error or an undefined reference or citation; exit 2 when there is no log (not_checked).
pdf     Runs pdfinfo and pdffonts (Poppler): pages, page size, fonts not embedded, Type 3 fonts,
        document properties. Each fact is pass, fail, manual or not_checked. A page limit is checked
        only with --max-pages, --limit-source and --content-pages (the pages that count, which the
        script cannot find itself). Writes pdf-facts.json and pdf-facts.md. Exit 1 when a fact
        fails, 2 when pdfinfo or pdffonts is missing or the file is not a readable PDF.

Standard library only; no network.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shlex
import shutil
import subprocess
import sys
from collections import Counter, OrderedDict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from latex_guard import (BIB_RE, CLASS_RE, LABEL_RE, PACKAGE_RE, input_targets, read_tree,  # noqa: E402
                         resolve, strip_comments)

ENGINE_FLAGS = {"pdflatex": "-pdf", "xelatex": "-xelatex", "lualatex": "-lualatex", "latex": "-pdfdvi"}
PDF_MODES = {"1": "pdflatex", "2": "latex", "3": "latex", "4": "lualatex", "5": "xelatex"}
UNICODE = {"xelatex", "lualatex"}
ENGINE_PACKAGES = {"fontspec": UNICODE, "unicode-math": UNICODE, "polyglossia": UNICODE, "xeCJK": {"xelatex"},
                   "xltxtra": {"xelatex"}, "xunicode": {"xelatex"}, "luacode": {"lualatex"}, "luatexja": {"lualatex"},
                   "luatexja-fontspec": {"lualatex"}, "luaotfload": {"lualatex"}}
SHELL_ESCAPE_PACKAGES = {"minted", "pythontex", "svg", "gnuplottex", "shellesc"}
SKIP_DIRS = {"latex-build", "node_modules", "__pycache__"}
# Commands whose package a log names often enough to suggest it. A hint, not a fix by itself.
COMMAND_PACKAGES = {cmd: pkg for pkg, cmds in (
    ("booktabs", "toprule midrule bottomrule cmidrule"), ("siunitx", "SI si num qty unit"), ("graphicx", "includegraphics"),
    ("hyperref", "href autoref"), ("cleveref", "cref Cref"), ("natbib", "citep citet"), ("biblatex", "textcite parencite"),
    ("xcolor", "textcolor color"), ("amssymb", "mathbb"), ("amsmath", "eqref text boldsymbol"), ("multirow", "multirow"),
    ("subcaption", "subcaption"), ("lipsum", "lipsum"), ("todonotes", "todo"), ("url", "url")) for cmd in cmds.split()}
GRAPHIC_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".ps", ".mps", ".jbig2", ".jb2", ".svg", ".bmp")
SUPPORT_EXTS = {".sty": "package", ".cls": "class", ".clo": "class", ".def": "package", ".cfg": "package",
                ".fd": "package", ".bst": "bibliography_style", ".bbx": "bibliography_style", ".cbx": "bibliography_style"}
ERROR_HINTS = [(r"Option clash for package", "the package is loaded twice with different options"),
               (r"Unicode character|Invalid UTF-8|inputenc Error", "encoding: a character this engine is not set up for"),
               (r"Environment \S+ undefined", "the environment is misspelled or its package is not loaded"),
               (r"Missing \$ inserted", "a math character (_ ^ and the like) outside math, or a math command in text"),
               (r"File ended while scanning|Paragraph ended before", "a brace or an argument is not closed")]
CLASS_ORDER = ["error", "missing_file", "bibliography", "undefined_citation", "undefined_reference", "duplicate_label",
               "rerun_needed", "overfull", "font", "package_warning"]


def fail(message: str) -> int:
    print(f"latex_log: {message}", file=sys.stderr)
    return 2


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def magic(text: str, key: str):
    """The value of a `% !TeX <key> = value` line near the top of a file."""
    m = re.search(rf"^\s*%\s*!\s*TeX\s+{key}\s*=\s*(.+?)\s*$", text[:3000], re.I | re.M)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------------------------
# detect

def tex_files(root: Path) -> list:
    return sorted(p for p in root.rglob("*.tex") if p.is_file() and p.stat().st_size < 5_000_000
                  and not any(part.startswith(".") or part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]))


def latexmkrc(folder: Path) -> dict:
    found = {"files": [], "engine": None, "default_files": [], "bibtex_use": None, "out_dir": None}
    for name in ("latexmkrc", ".latexmkrc"):
        if not (folder / name).is_file():
            continue
        text = re.sub(r"#.*", "", read(folder / name))
        found["files"].append(name)
        mode = re.search(r"\$pdf_mode\s*=\s*([1-5])", text)
        runs = re.search(r"\$pdflatex\s*=\s*['\"]\s*(xelatex|lualatex)", text)
        if runs and (not mode or mode.group(1) == "1"):
            found["engine"] = (runs.group(1), f"{name}: $pdflatex runs {runs.group(1)}")
        elif mode:
            found["engine"] = (PDF_MODES[mode.group(1)], f"{name}: $pdf_mode = {mode.group(1)}")
        files = re.search(r"@default_files\s*=\s*\(([^)]*)\)", text)
        found["default_files"] += re.findall(r"['\"]([^'\"]+)['\"]", files.group(1)) if files else []
        for key, pattern in (("bibtex_use", r"\$bibtex_use\s*=\s*([\d.]+)"),
                             ("out_dir", r"\$(?:out|aux)_dir\s*=\s*['\"]([^'\"]+)")):
            m = re.search(pattern, text)
            found[key] = m.group(1) if m else found[key]
    return found


def find_main(path: Path):
    """(main or None, candidates, notes)."""
    if path.is_file():
        raw = read(path)
        if CLASS_RE.search(strip_comments(raw, keep_lines=True)):
            return path.resolve(), [{"file": path.name, "reason": "given"}], []
        target = (path.parent / magic(raw, "root")).resolve() if magic(raw, "root") else None
        if target and target.is_file():
            return target, [{"file": target.name, "reason": f"`% !TEX root` in {path.name}"}], []
        return None, [], [f"{path.name} has no \\documentclass: give the main file or the folder"]
    root = path.resolve()
    raws = {p: read(p) for p in tex_files(root)}
    texts = {p: strip_comments(raw, keep_lines=True) for p, raw in raws.items()}
    included, named = set(), Counter()
    for p, text in texts.items():
        included.update(filter(None, (resolve(t, p.parent, root, n) for n, t, _ in input_targets(text))))
        if magic(raws[p], "root"):
            named[(p.parent / magic(raws[p], "root")).resolve()] += 1
    candidates = []
    for p, text in texts.items():
        klass = CLASS_RE.search(text)
        if not klass or p.resolve() in included or klass.group(2).strip() == "subfiles":
            continue
        reason = "has \\documentclass and no other file inputs it"
        reason += "; class standalone (usually a figure source)" if klass.group(2).strip() == "standalone" else ""
        reason += f"; named by `% !TEX root` in {named[p.resolve()]} file(s)" if named[p.resolve()] else ""
        reason += "; inputs other files or holds the bibliography" if (next(input_targets(text), None)
                                                                         or BIB_RE.search(text)) else ""
        candidates.append({"file": p.relative_to(root).as_posix(), "reason": reason, "_path": p.resolve()})
    rc = latexmkrc(root)
    notes = [f"latexmkrc names the main file(s): {', '.join(rc['default_files'])}"] if rc["default_files"] else []
    pick = [c for c in candidates if c["file"] in rc["default_files"]] or [c for c in candidates if named[c["_path"]]]
    if len(pick) != 1:
        pick = [c for c in candidates if "standalone" not in c["reason"]]
    if len(pick) > 1 and sum("inputs other files" in c["reason"] for c in pick) == 1:
        pick = [c for c in pick if "inputs other files" in c["reason"]]
        notes.append(f"{pick[0]['file']} chosen: of the candidates, only it inputs other files or holds the bibliography")
    main = pick[0]["_path"] if len(pick) == 1 else None
    return main, [{k: v for k, v in c.items() if k != "_path"} for c in candidates], notes


def choose_engine(rc: dict, head: str, packages: dict, preamble: str, main: Path) -> dict:
    evidence, explicit, needed = [], [], None
    if rc["engine"]:
        explicit.append(rc["engine"][0])
        evidence.append(rc["engine"][1])
    program = magic(head, r"(?:TS-)?program")
    if program:
        name = program.lower()
        aliases = {"pdftex": "pdflatex", "xetex": "xelatex", "luatex": "lualatex", "latex": "pdflatex"}
        explicit.append(aliases.get(name, name))
        evidence.append(f"{main.name}: `% !TEX program = {program}`"
                        + (" (editors that write `latex` here run pdfLaTeX)" if name == "latex" else ""))
    signals = [("\\usepackage{%s}" % n, ENGINE_PACKAGES[n]) for n in packages if n in ENGINE_PACKAGES]
    signals += [("\\directlua", {"lualatex"})] if re.search(r"\\directlua\b", preamble) else []
    for name, engines in signals:
        needed = engines if needed is None else needed & engines
        evidence.append(f"{name} needs {' or '.join(sorted(engines))}")
    conflict = len(set(explicit)) > 1 or needed == set() or bool(needed and explicit and explicit[0] not in needed)
    if conflict:
        engine = None
        evidence.append("the signals above disagree: ask the user which engine the paper is built with")
    elif explicit:
        engine = explicit[0]
    elif needed:
        engine = "xelatex" if "xelatex" in needed else sorted(needed)[0]
        evidence += ["xelatex chosen; lualatex would also work, and nothing names either"] if len(needed) > 1 else []
    else:
        engine = "pdflatex"
        evidence.append("no latexmkrc engine, no `% !TEX program` line and no package that needs another engine")
    return {"value": engine, "evidence": evidence, "conflict": conflict}


def choose_bibliography(tree: dict, packages: dict, main: Path, rc: dict) -> dict:
    evidence, tool, files, conflict = [], None, [], False
    commands = [(m.group(1), m.group(2).strip()) for e in tree["files"] for m in BIB_RE.finditer(e["text"])]
    if "biblatex" in packages:
        backend = re.search(r"backend\s*=\s*(\w+)", packages["biblatex"])
        tool = "biber" if not backend or backend.group(1) == "biber" else "bibtex"
        evidence.append(f"\\usepackage[{packages['biblatex']}]{{biblatex}}"
                        + ("" if backend else ": biblatex uses Biber unless backend= says otherwise"))
        if "natbib" in packages or any(c == "bibliographystyle" for c, _ in commands):
            conflict = True
            evidence.append("biblatex is loaded together with natbib or \\bibliographystyle: they do not work together")
    elif any(c == "bibliography" for c, _ in commands):
        tool = "bibtex"
        style = [v for c, v in commands if c == "bibliographystyle"]
        evidence.append("\\bibliography{...}" + (f" with \\bibliographystyle{{{style[0]}}}" if style
                                                  else " without \\bibliographystyle (BibTeX will stop)"))
    elif re.search(r"\\begin\s*\{thebibliography\}", "\n".join(e["text"] for e in tree["files"])):
        evidence.append("a thebibliography list in the source: no bibliography tool runs")
    else:
        evidence.append("no bibliography commands found")
    for command, value in commands:
        if command in ("bibliography", "addbibresource"):
            files += [n.strip() if n.strip().endswith(".bib") or command == "addbibresource" else n.strip() + ".bib"
                      for n in value.split(",")]
    missing = [f for f in files if not (main.parent / f).is_file()]
    bbl = main.with_suffix(".bbl")
    if tool and files and len(missing) == len(files) and bbl.is_file():
        evidence.append(f"{bbl.name} exists and none of the .bib files does: the .bbl is used as it is "
                        "and cannot be rebuilt")
        tool = "bbl_only"
    elif missing:
        evidence.append(f"missing .bib file(s): {', '.join(missing)}")
    if rc["bibtex_use"] == "0":
        evidence.append("latexmkrc sets $bibtex_use = 0: latexmk never runs BibTeX or Biber")
    return {"tool": None if conflict else tool, "files": files, "missing": missing, "evidence": evidence,
            "conflict": conflict}


def detect(path: Path) -> dict:
    main, candidates, notes = find_main(path)
    project = path.resolve() if path.is_dir() else path.resolve().parent
    result = {"tool": "researchzy-latex", "command": "detect", "project": str(project), "candidates": candidates,
              "main": None, "engine": None, "bibliography": None, "latexmk": None, "notes": notes, "decided": False}
    if main is None:
        notes.append("several possible main files: ask the user which file is the paper" if len(candidates) > 1
                     else "no .tex file with \\documentclass was found" if not candidates else "no main file chosen")
        return result
    result["main"] = main.relative_to(project).as_posix() if project in main.parents else str(main)
    tree = read_tree(main)
    preamble = "\n".join(e["text"][:e["body"][0]] if e["path"] == main else e["text"] for e in tree["files"])
    packages = OrderedDict((n.strip(), (m.group(1) or "").strip()) for m in PACKAGE_RE.finditer(preamble)
                           for n in m.group(2).split(","))
    rc, workdir = latexmkrc(main.parent), main.parent
    if not rc["files"] and project in main.parents and latexmkrc(project)["files"]:
        rc, workdir = latexmkrc(project), project
    head = read(main)
    result["engine"] = engine = choose_engine(rc, head, packages, preamble, main)
    result["bibliography"] = bib = choose_bibliography(tree, packages, main, rc)
    notes += [f"\\usepackage{{{n}}} runs external programs and needs -shell-escape: ask the user before adding it, "
              "because it lets the document run any command" for n in packages if n in SHELL_ESCAPE_PACKAGES]
    if rc["out_dir"]:
        notes.append(f"latexmkrc writes build files to {rc['out_dir']}: the log is there, not next to {main.name}")
    notes += [f"a user-level {p} exists and also applies to every build"
              for p in (Path.home() / ".latexmkrc", Path.home() / ".config" / "latexmk" / "latexmkrc") if p.is_file()]
    if engine["value"] and engine["value"] not in ENGINE_FLAGS:
        notes.append(f"latexmk has no switch here for `{engine['value']}`: ask the user how the paper is built")
    elif engine["value"] and not bib["conflict"]:
        flags = [ENGINE_FLAGS[engine["value"]], "-file-line-error", "-halt-on-error", "-interaction=nonstopmode"]
        flags += ["-bibtex-"] if bib["tool"] == "bbl_only" else []
        target = shlex.quote(main.relative_to(workdir).as_posix())
        result["latexmk"] = {"cwd": str(workdir), "command": "latexmk " + " ".join(flags) + " " + target}
        result["decided"] = True
    return result


# ---------------------------------------------------------------------------------------------
# parse

def unwrap(data: bytes) -> list:
    """Logical lines: TeX breaks every line at 79 bytes (pdfTeX) or characters (XeTeX, LuaTeX)."""
    out, buffer = [], b""
    for raw in data.split(b"\n"):
        raw = raw.rstrip(b"\r")
        buffer += raw
        if len(raw) == 79 or len(raw.decode("utf-8", "replace")) == 79:
            continue
        out.append(buffer.decode("utf-8", "backslashreplace"))
        buffer = b""
    return out + ([buffer.decode("utf-8", "backslashreplace")] if buffer else [])


def looks_like_file(token: str) -> bool:
    return bool(token) and (token.startswith(("./", "../", "/", "~")) or re.match(r"[A-Za-z]:[\\/]", token) is not None
                            or re.fullmatch(r"[\w.+-]+(?:/[\w.+-]+)*\.[A-Za-z]\w{0,7}", token) is not None)


def clean_path(name: str, root: Path) -> str:
    name = name.strip().strip('"')
    name = name[2:] if name.startswith("./") else name
    if Path(name).is_absolute():
        try:
            return Path(name).resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            return name
    return name


def event(cls, message, file=None, line=None, severity="warning", **extra) -> dict:
    return {"class": cls, "severity": severity, "file": file, "line": line, "message": message, **extra}


def classify_error(message: str) -> dict:
    """The class and details of an error message (without its file:line: or ! prefix)."""
    for pattern, kind in ((r"File [`'](.+?)' not found", None), (r"Unable to load picture or PDF file '(.+?)'", "graphics"),
                          (r"I can't find file [`'](.+?)'", "input"),
                          (r"Font \S+=(\S+) .*not loadable: Metric \(TFM\) file not found", "font")):
        m = re.search(pattern, message)
        if m:
            name, ext = m.group(1) + (".tfm" if kind == "font" else ""), Path(m.group(1)).suffix.lower()
            graphics = ext in GRAPHIC_EXTS or ".def Error" in message
            kind = kind or SUPPORT_EXTS.get(ext) or ("graphics" if graphics else "input")
            return {"class": "missing_file", "kind": kind, "name": name}
    hint = next((h for pattern, h in ERROR_HINTS if re.search(pattern, message)), None)
    return {"class": "error", **({"hint": hint} if hint else {})}


def parse_log(log: Path, hbox_pt: float) -> tuple:
    lines, root = unwrap(log.read_bytes()), log.parent
    main_name = log.with_suffix(".tex").name if log.with_suffix(".tex").is_file() else None
    events, stack, facts = [], [], {"engine": None, "file_line_errors": False, "pdf": None, "pages": None,
                                    "fatal": False, "complete": False, "underfull": 0}
    skip_box, skip_next, pending, runaway = False, 0, None, None
    for index, line in enumerate(lines):
        if index == 0 and re.match(r"This is (\S+)", line):
            facts["engine"] = re.match(r"This is (\S+)", line).group(1).rstrip(",")
        facts["file_line_errors"] |= "file:line:error style messages enabled" in line
        output = re.match(r"Output written on (.+?) \((\d+) pages?", line)
        if output:
            facts["pdf"], facts["pages"] = clean_path(output.group(1), root), int(output.group(2))
        facts["complete"] |= bool(output) or line.startswith(("No pages of output", "Here is how much of TeX's memory"))
        if "Fatal error occurred, no output PDF file produced" in line:
            facts["fatal"] = True
            continue
        if skip_box:
            skip_box = bool(line.strip())
            continue
        if skip_next:
            skip_next -= 1
            continue
        if pending and re.match(r"(?:l\.(\d+)|<[^>]+>) ", line):
            number = re.match(r"l\.(\d+) ", line)
            if number:
                pending["line"] = pending["line"] or int(number.group(1))
                pending["context"] = line.strip()
            if "_seen" not in pending:
                pending["_seen"] = True
                pending.setdefault("context", line.strip())
                cs = re.search(r"(\\[A-Za-z@]+)\s*$", line)
                if pending["message"].startswith("Undefined control sequence") and cs:
                    pending["message"] = f"Undefined control sequence {cs.group(1)}"
                    if cs.group(1)[1:] in COMMAND_PACKAGES:
                        package = COMMAND_PACKAGES[cs.group(1)[1:]]
                        pending["hint"] = f"{cs.group(1)} usually comes from \\usepackage{{{package}}}"
            skip_next = 1
            continue
        if pending and pending.get("kind") == "input" and "could not locate the file with any of these extensions" in line:
            pending["kind"] = "graphics"
        if line.startswith("Runaway argument?"):
            runaway, skip_next = lines[index + 1].strip() if index + 1 < len(lines) else "", 1
            continue
        located = re.match(r"((?:[A-Za-z]:)?[^\s:][^:]*\.\w+):(\d+): (.+)$", line)
        bang = re.match(r"! (.+)$", line)
        if located or bang:
            message = (located.group(3) if located else bang.group(1)).strip()
            following = lines[index + 1] if index + 1 < len(lines) else ""
            if re.match(r"\s{6,}\S", following) and not following.strip().startswith(("l.", "<")):
                message += " " + following.strip()
            detail = classify_error(message)
            file = clean_path(located.group(1), root) if located else current_file(stack) or main_name
            number = int(located.group(2)) if located else None
            pending = event(detail.pop("class"), message, file, number, "error", **detail)
            if runaway is not None:
                pending.update(context=runaway[:120], message=f"Runaway argument: {message}")
                runaway = None
            previous = events[-1] if events else None
            if (previous and previous["class"] == "missing_file" and previous["line"] is None
                    and message.startswith("Emergency stop") and previous["file"] == file):
                previous["line"] = pending["line"]
            events.append(pending)
            continue
        found = warning_event(line, lines[index + 1:index + 6], stack, hbox_pt, facts)
        if found:
            skip_next = found.pop("_consumed", 0)
            skip_box = bool(found.pop("_box", False)) or found.get("class") == "overfull"
            if found.get("class"):
                events.append(found)
                pending = None
            continue
        track_files(line, stack, root)
    for e in events:
        e.pop("_seen", None)
    return events, facts


def current_file(stack: list):
    return next((name for name in reversed(stack) if name), None)


def track_files(line: str, stack: list, root: Path) -> None:
    """Push a file at "(name", anything else at "(", and pop at ")": balanced text cancels out."""
    for m in re.finditer(r'\((?:"([^"]+)"|([^\s()"]*))|\)', line):
        if m.group(0) == ")":
            if stack:
                stack.pop()
            continue
        token = m.group(1) or m.group(2)
        stack.append(clean_path(token, root) if looks_like_file(token) else None)


def warning_event(line, after, stack, hbox_pt, facts):
    """An event for a warning line; {} for a known line to drop; {"_box": True} for a box to skip; None."""
    file = current_file(stack)
    box = re.match(r"(Overfull|Underfull) \\([hv])box(?: \(([\d.]+)pt too (?:wide|high)\))?", line)
    if box:
        if box.group(1) == "Underfull" or (box.group(2) == "h" and float(box.group(3) or 0) <= hbox_pt):
            facts["underfull"] += box.group(1) == "Underfull"
            return {"_box": True}
        at = re.search(r"at lines? (\d+)|detected at line (\d+)", line)
        where = "while a page was being output" if "output is active" in line else line.split(")", 1)[1].strip()
        return event("overfull", f"Overfull \\{box.group(2)}box by {float(box.group(3)):g}pt ({where})", file,
                     int(at.group(1) or at.group(2)) if at else None, points=float(box.group(3)))
    text, consumed = line, 0
    head = re.match(r"(?:Package|Class) (\S+) Warning: |LaTeX Font Warning: |LaTeX Warning: ", line)
    prefix = ("Font" if "Font Warning" in head.group(0) else head.group(1)) if head else None
    for more in after:
        if not (prefix and more.startswith(f"({prefix})")):
            break
        text, consumed = text + " " + more[len(prefix) + 2:].strip(), consumed + 1
    found = warning_class(line, text, file)
    if found is not None and consumed:
        found["_consumed"] = consumed
    return found


def warning_class(line, text, file):
    number = re.search(r"on input line (\d+)", text)
    number = int(number.group(1)) if number else None
    for cls, pattern, wording in (
            ("undefined_citation", r"Citation [`'](.+?)' on page \S+ undefined", "Citation `{}' undefined"),
            ("undefined_reference", r"Reference [`'](.+?)' on page \S+ undefined", "Reference `{}' undefined"),
            ("duplicate_label", r"Label [`'](.+?)' multiply defined", "Label `{}' defined more than once")):
        m = re.search(pattern, text)
        if m:
            where = (None, None) if cls == "duplicate_label" else (file, number)
            return event(cls, wording.format(m.group(1)), *where, key=m.group(1))
    if re.search(r"There were (undefined references|undefined citations|multiply[- ]defined)|Some font shapes were "
                 r"not available|Size substitutions with differences|The following entry could not be found|"
                 r"Biber reported", text):
        return {}
    if re.search(r"Rerun to get|Please \(re\)run|Please rerun|[Rr]erun LaTeX|may have changed\. Rerun", text):
        return event("rerun_needed", re.sub(r"^(?:Package \S+ |LaTeX )Warning: ", "", text).strip(), file, number)
    m = re.search(r"Font shape [`'](.+?)' undefined.*?using [`'](.+?)' instead", text)
    if m:
        return event("font", f"Font shape {m.group(1)} is not available; {m.group(2)} used instead", file, number)
    m = re.match(r"Missing character: There is no (.+?) in font (.+?)!", line)
    if m:
        return event("font", f"Missing character {m.group(1)} in font {m.group(2)}", file, None)
    if "Font Warning" in text:
        return {}
    m = re.match(r"No file (.+)\.$", line)
    if m and m.group(1).endswith(".tex"):
        return event("missing_file", f"No file {m.group(1)}: \\include skipped it", file, None, "error", kind="input",
                     name=m.group(1))
    if m and m.group(1).endswith(".bbl"):
        return event("bibliography", f"No file {m.group(1)}: BibTeX or Biber did not run or failed", file, None, "error")
    if m:
        return {}
    head = re.match(r"(?:Package|Class) (\S+) Warning: |LaTeX Warning: ", text)
    if head or "pdfTeX warning" in line:
        body = text[head.end():] if head else line[line.find("pdfTeX warning"):]
        return event("package_warning", body.strip(), file, number,
                     source=(head.group(1) or "LaTeX") if head else "pdfTeX")
    return None


def parse_blg(blg: Path) -> list:
    """BibTeX and Biber messages from a .blg."""
    events, lines, source = [], read(blg).splitlines(), None
    for index, line in enumerate(lines):
        nxt = lines[index + 1] if index + 1 < len(lines) else ""
        m = re.match(r"(.*)---line (\d+) of file (.+)$", line)
        if m:
            before = "previous line" in "".join(lines[index + 1:index + 4])
            earlier = " (the error may be on the line before)" if before else ""
            events.append(event("bibliography", f"BibTeX: {m.group(1).strip()}{earlier}", m.group(3).strip(),
                                int(m.group(2)), "error"))
            continue
        m = re.match(r"Warning--(.*)$", line)
        if m:
            at = re.match(r"--line (\d+) of file (.+)$", nxt)
            events.append(event("bibliography", "BibTeX: " + m.group(1).strip(), at and at.group(2),
                                at and int(at.group(1))))
            continue
        if re.match(r"I couldn't open|I found no \\\w+ command", line):
            events.append(event("bibliography", "BibTeX: " + line.strip(), None, None, "error"))
        found = re.search(r"Found BibTeX data source '(.+?)'", line)
        source = found.group(1) if found else source
        m = re.match(r"(?:\[\d+\] \S+> )?(ERROR|WARN) - (.*)$", line)
        if m:
            message, file, number = m.group(2).strip(), None, None
            sub = re.match(r"BibTeX subsystem: \S+?, line (\d+), (.*)$", message)
            if sub:  # Biber reads a converted copy of the .bib; the line number is the original's
                file, number, message = source, int(sub.group(1)), sub.group(2)
            named = re.search(r"\(([^()]+\.bib)\)", message)
            events.append(event("bibliography", "Biber: " + message, named.group(1) if named else file, number,
                                "error" if m.group(1) == "ERROR" else "warning"))
    return events


def group(events: list, root: Path) -> list:
    groups = OrderedDict()
    for e in events:
        key = (e["class"], e["message"]) + ((e["file"], e["line"]) if e["severity"] == "error" else ())
        groups.setdefault(key, dict(e, count=0, locations=[]))
        groups[key]["count"] += 1
        where = f"{e['file']}:{e['line']}" if e["file"] and e["line"] else e["file"]
        if where and where not in groups[key]["locations"]:
            groups[key]["locations"].append(where)
    problems = list(groups.values())
    tex_errors = [p for p in problems if p["severity"] == "error" and p["class"] != "bibliography"
                  and not p["message"].startswith("No file")]
    for p in tex_errors:
        p["first" if p is tex_errors[0] else "possibly_caused_by_first"] = True
    hints_from_source(problems, root)
    return sorted(problems, key=lambda p: max(1, CLASS_ORDER.index(p["class"])))


def hints_from_source(problems: list, root: Path) -> None:
    """Where duplicate labels are defined; the nearest existing label, .bib key or file for a missing one."""
    labels, keys = {}, set()
    files = [p.relative_to(root).as_posix() for p in root.rglob("*")
             if p.is_file() and p.suffix.lower() in GRAPHIC_EXTS + (".tex",)
             and not any(part.startswith(".") or part in SKIP_DIRS for part in p.relative_to(root).parts[:-1])]
    for path in tex_files(root):
        text = strip_comments(read(path), keep_lines=True)
        for m in LABEL_RE.finditer(text):
            where = f"{path.relative_to(root).as_posix()}:{text.count(chr(10), 0, m.start()) + 1}"
            labels.setdefault(m.group(1).strip(), []).append(where)
    for path in root.glob("*.bib"):
        keys.update(re.findall(r"@(?!string|comment|preamble)\w+\s*[{(]\s*([^,\s]+)\s*,", read(path), re.I))
    for p in problems:
        if p["class"] == "duplicate_label" and labels.get(p["key"]):
            p["locations"] = labels[p["key"]]
        pool = labels if p["class"] == "undefined_reference" else keys if p["class"] == "undefined_citation" else None
        near = difflib.get_close_matches(p["key"], list(pool), n=1, cutoff=0.75) if pool and p["key"] not in pool else None
        if near:
            what = "label" if pool is labels else ".bib key (report it; do not change a citation key)"
            p["hint"] = f"closest existing {what}: {near[0]}"
        if p["class"] == "missing_file" and p.get("kind") in ("graphics", "input"):
            wanted = p["name"].rsplit(".", 1)[0] if Path(p["name"]).suffix.lower() in GRAPHIC_EXTS + (".tex",) else p["name"]
            pool = [f for f in files if (f.endswith(".tex")) == (p["kind"] == "input")]
            same = [f for f in pool if Path(f).stem == Path(wanted).name]
            near = same or [f for f in pool if f.rsplit(".", 1)[0] in difflib.get_close_matches(
                wanted, [g.rsplit(".", 1)[0] for g in pool], n=3, cutoff=0.75)]
            if near:
                p["hint"] = (f"closest existing file: {near[0]}" if len(near) == 1 else
                             f"several close files: {', '.join(near[:5])} (report; do not choose)")


def write_problems(out: Path, result: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "problems.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    build = result["build"]
    blg = f", bibliography log `{result['blg']}`" if result["blg"] else ""
    lines = ["# LaTeX build problems", "", f"Log: `{result['log']}`{blg}. Read {date.today().isoformat()}.", "",
             f"**Build: {build['status']}.** " + " ".join(build["notes"])]
    if result["problems"]:
        lines += ["", "| Class | Items | Occurrences |", "|---|---|---|"]
        lines += [f"| {c} | {v['items']} | {v['occurrences']} |" for c, v in result["counts"].items() if v["items"]]
    current = None
    for index, p in enumerate(result["problems"], 1):
        heading = "Errors and missing files" if p["class"] in ("error", "missing_file") else p["class"]
        if heading != current:
            current = heading
            lines += ["", f"## {heading}", ""]
        mark = ("**First error.** " if p.get("first") else
                "(May be caused by the first error.) " if p.get("possibly_caused_by_first") else "")
        where = ", ".join(p["locations"][:6]) or "no file or line given"
        lines.append(f"{index}. {mark}`{where}` {p['message']}" + (f" (x{p['count']})" if p["count"] > 1 else ""))
        lines += [f"   - {k}: `{p[k]}`" if k == "context" else f"   - {k}: {p[k]}"
                  for k in ("kind", "context", "hint") if p.get(k)]
    if not result["problems"]:
        lines += ["", "Nothing was checked." if build["status"] == "not_checked" else "No problems found in the log."]
    (out / "problems.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_parse(args) -> int:
    log, out = args.log, args.out
    counts = {c: {"items": 0, "occurrences": 0} for c in CLASS_ORDER}
    if not log.is_file():
        result = {"tool": "researchzy-latex", "command": "parse", "log": str(log), "blg": None, "problems": [],
                  "counts": counts, "build": {"status": "not_checked",
                                              "notes": [f"No log file at {log}: build first; nothing was checked."]}}
        write_problems(out, result)
        print(json.dumps({k: result[k] for k in ("log", "build")}, indent=2, ensure_ascii=False))
        return 2
    blg = args.blg or (log.with_suffix(".blg") if log.with_suffix(".blg").is_file() else None)
    if blg is not None and not blg.is_file():
        return fail(f"no such file: {blg}")
    events, facts = parse_log(log, args.hbox_pt)
    problems = group(events + (parse_blg(blg) if blg else []), log.parent)
    for p in problems:
        counts[p["class"]]["items"] += 1
        counts[p["class"]]["occurrences"] += p["count"]
    errors = [p for p in problems if p["severity"] == "error"]
    undefined = counts["undefined_reference"]["items"] + counts["undefined_citation"]["items"]
    pdf, notes = log.parent / (facts["pdf"] or log.with_suffix(".pdf").name), []
    if errors or facts["fatal"]:
        status = "failed"
        if pdf.is_file():
            notes.append(f"{pdf.name} is left from an earlier run: this run produced no PDF." if facts["fatal"] else
                         f"{pdf.name} exists, but the log holds errors: TeX guessed its way past them, so this PDF "
                         "is not a good build.")
    elif not facts["complete"]:
        status = "failed"
        notes.append("The log ends early: the run was interrupted or is still going.")
    else:
        status = "incomplete" if undefined or counts["rerun_needed"]["items"] else "ok"
    if status == "failed" and undefined:
        notes.append("The run stopped at an error, so some undefined references and citations may only mean it "
                     "did not finish.")
    if facts["engine"]:
        notes.append(f"Engine: {facts['engine']}" + ("." if facts["file_line_errors"] else
                                                     "; -file-line-error was off, so error files come from the file stack."))
    if facts["underfull"]:
        notes.append(f"{facts['underfull']} underfull box(es) not listed (spacing notes).")
    result = {"tool": "researchzy-latex", "command": "parse", "log": str(log), "blg": str(blg) if blg else None,
              "build": {"status": status, "pdf": facts["pdf"], "pages": facts["pages"], "notes": notes,
                        "hbox_threshold_pt": args.hbox_pt}, "counts": counts, "problems": problems}
    write_problems(out, result)
    print(json.dumps({"log": result["log"], "blg": result["blg"], "build": result["build"],
                      "counts": {c: v["items"] for c, v in counts.items() if v["items"]},
                      "first_error": next((f"{p['file']}:{p['line']} {p['message']}" for p in problems
                                           if p.get("first")), None),
                      "written": [str(out / "problems.json"), str(out / "problems.md")]}, indent=2, ensure_ascii=False))
    return 1 if errors or undefined else 0


# ---------------------------------------------------------------------------------------------
# pdf

def parse_pdffonts(text: str) -> list:
    """Rows of pdffonts output, cut at the columns its dashed rule line marks.

    A font name longer than its column pushes the rest of the row to the right; the shift is the
    overflow, so every later column moves by the same amount.
    """
    lines = text.splitlines()
    rule = next((i for i, line in enumerate(lines) if re.fullmatch(r"-+(?: -+)+", line.strip())), None)
    if not rule:
        return []
    names = lines[rule - 1].split()
    names = names[:-2] + ["object ID"] if names[-2:] == ["object", "ID"] else names
    spans = [(m.start(), m.end()) for m in re.finditer(r"-+", lines[rule])]
    if len(names) != len(spans):
        return []
    rows = []
    for line in filter(str.strip, lines[rule + 1:]):
        space = line.find(" ", spans[0][0])
        shift = max(0, (space if space >= 0 else len(line)) - spans[0][1])
        cells = [line[(start + shift if i else start):(end + shift if i < len(spans) - 1 else len(line))].strip()
                 for i, (start, end) in enumerate(spans)]
        rows.append(dict(zip(names, cells)))
    return rows


def parse_pdfinfo(text: str) -> dict:
    info = {"_sizes": []}
    for line in text.splitlines():
        m = re.match(r"Page\s*(\d*)\s+size:\s+([\d.]+) x ([\d.]+) pts", line)
        if m:
            info["_sizes"].append((int(m.group(1) or len(info["_sizes"]) + 1), float(m.group(2)), float(m.group(3))))
        elif re.match(r"[A-Za-z][A-Za-z ]*?:", line):
            key, _, value = line.partition(":")
            info[key] = value.strip()
    return info


def expected_size(text: str):
    named = {"a4": (595.276, 841.89), "letter": (612.0, 792.0)}
    m = re.fullmatch(r"([\d.]+)\s*x\s*([\d.]+)\s*(mm|pt|in)?", text.strip().lower())
    if text.lower() not in named and not m:
        raise ValueError(f"--page-size must be a4, letter or WxH with mm, pt or in (got {text!r})")
    scale = {"mm": 72 / 25.4, "pt": 1.0, "in": 72.0}[(m and m.group(3)) or "mm"]
    return named.get(text.lower()) or (float(m.group(1)) * scale, float(m.group(2)) * scale)


def run_tool(name: str, pdf: Path):
    binary = shutil.which(name)
    if not binary:
        return None, f"{name} is not installed (it comes with Poppler, package poppler-utils on most Linux systems)"
    command = [binary, "-f", "1", "-l", "99999", str(pdf)] if name == "pdfinfo" else [binary, str(pdf)]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=120, errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{name} failed: {exc}"
    said = (done.stderr or done.stdout).strip().splitlines()
    reason = said[-1] if said else f"exit code {done.returncode}"
    return (done.stdout, None) if done.returncode == 0 else (None, f"{name} could not read the file: {reason}")


def fact(name, status, detail, **extra) -> dict:
    return {"fact": name, "status": status, "detail": detail, **extra}


def size_fact(sizes: list, want) -> dict:
    shapes = sorted({(round(w, 2), round(h, 2)) for _, w, h in sizes})
    described = "; ".join(f"{w:g} x {h:g} pt ({w * 25.4 / 72:.1f} x {h * 25.4 / 72:.1f} mm)" for w, h in shapes)
    if want is None:
        return fact("page_size", "manual", f"{described or 'no page size reported'}; give --page-size to check it",
                    sizes_pt=shapes)

    def near(w, h):
        return abs(w - want[0]) <= 2 and abs(h - want[1]) <= 2
    off = [n for n, w, h in sizes if not near(w, h) and not near(h, w)]
    turned = [n for n, w, h in sizes if near(h, w) and not near(w, h)]
    detail = f"{described}; expected {want[0]:.1f} x {want[1]:.1f} pt" + (f"; other size on pages {off[:20]}" if off else "")
    detail += f"; turned sideways on pages {turned[:20]} (a landscape table or figure?)" if turned else ""
    return fact("page_size", "fail" if off or not sizes else "manual" if turned else "pass", detail, sizes_pt=shapes)


def cmd_pdf(args) -> int:
    if args.max_pages is not None and not args.limit_source:
        return fail("--max-pages needs --limit-source: where the limit comes from (file or URL, and the date read)")
    try:
        want = expected_size(args.page_size) if args.page_size else None
    except ValueError as exc:
        return fail(str(exc))
    with args.pdf.open("rb") as handle:
        if not handle.read(1024).lstrip().startswith(b"%PDF-"):
            return fail(f"{args.pdf} is not a PDF file")
    facts, missing = [], []
    info_text, problem = run_tool("pdfinfo", args.pdf)
    if info_text is None:
        missing.append(problem)
        facts += [fact(n, "not_checked", problem) for n in ("pages", "page_size", "properties")
                  + (("page_limit",) if args.max_pages is not None else ())]
    else:
        info = parse_pdfinfo(info_text)
        pages = int(info.get("Pages") or 0)
        if args.content_pages is not None and args.content_pages > pages:
            return fail(f"--content-pages {args.content_pages} is more than the {pages} pages of the PDF")
        facts.append(fact("pages", "manual", f"{pages} pages; compare with the venue's rule", value=pages))
        if args.max_pages is not None:
            source = f"limit {args.max_pages} from {args.limit_source}"
            facts.append(fact("page_limit", "manual", f"{source}; give --content-pages (the pages the limit counts) to "
                                                      "check it: the script cannot tell where those pages end")
                         if args.content_pages is None else
                         fact("page_limit", "pass" if args.content_pages <= args.max_pages else "fail",
                              f"{args.content_pages} counted pages; {source}"))
        facts.append(size_fact(info["_sizes"], want))
        props = {k.lower(): info.get(k, "") for k in ("Title", "Author", "Subject", "Keywords", "Creator", "Producer")}
        filled = ", ".join(f"{k}: {v}" for k, v in props.items() if v) or "all empty"
        facts.append(fact("properties", "manual", f"{filled}. An author name here identifies the authors in a "
                                                  "double-blind submission", properties=props))
        if info.get("Encrypted", "no").lower().startswith("yes"):
            facts.append(fact("encrypted", "manual", "the PDF is encrypted; some submission systems refuse such files"))
    fonts_text, problem = run_tool("pdffonts", args.pdf)
    rows = parse_pdffonts(fonts_text) if fonts_text else []
    if fonts_text is None or (not rows and "---" not in fonts_text):
        missing += [problem] if problem else []
        facts += [fact(n, "not_checked", problem or "pdffonts printed no font table")
                  for n in ("fonts_embedded", "type3_fonts")]
    else:
        loose = sorted({f"{r.get('name')} ({r.get('type')})" for r in rows if r.get("emb") == "no"})
        facts.append(fact("fonts_embedded", "fail" if loose else "pass",
                          f"not embedded: {', '.join(loose)}" if loose else f"all {len(rows)} fonts embedded", fonts=rows))
        type3 = [(r.get("object ID") or "?").split()[0] for r in rows if r.get("type", "").startswith("Type 3")]
        facts.append(fact("type3_fonts", "manual" if type3 else "pass",
                          f"{len(type3)} Type 3 font(s) (objects {', '.join(type3[:10])}): bitmap or figure fonts that many "
                          "submission systems refuse; check the kit's rules" if type3 else "no Type 3 fonts"))
    counts = {s: sum(1 for f in facts if f["status"] == s) for s in ("pass", "fail", "manual", "not_checked")}
    result = {"tool": "researchzy-latex", "command": "pdf", "file": str(args.pdf), "read": date.today().isoformat(),
              "facts": facts, "counts": counts, "missing_tools": missing}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "pdf-facts.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md = ["# PDF facts", "", f"File: `{args.pdf}`. Read {result['read']}.", "",
          "| Fact | Status | Detail |", "|---|---|---|"]
    md += [f"| {f['fact']} | {f['status']} | {f['detail']} |" for f in facts]
    (args.out / "pdf-facts.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(dict(result, facts=[{k: f[k] for k in ("fact", "status", "detail")} for f in facts]), indent=2,
                     ensure_ascii=False))
    return 2 if missing else 1 if counts["fail"] else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Detect a LaTeX build, parse its log, and read PDF facts.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("detect", help="Main file, engine, bibliography tool and latexmk command")
    p.add_argument("path", type=Path, help="The project folder or the main .tex file")
    p = sub.add_parser("parse", help="Turn a .log (and .blg) into problems.json and problems.md")
    p.add_argument("log", type=Path)
    p.add_argument("--blg", type=Path, help="The BibTeX or Biber log (default: <stem>.blg next to the log, if any)")
    p.add_argument("--hbox-pt", type=float, default=5.0, help="List overfull hboxes wider than this (default 5 pt)")
    p.add_argument("--out", type=Path, default=Path("latex-build"))
    p = sub.add_parser("pdf", help="Pages, page size, fonts and properties of a PDF")
    p.add_argument("pdf", type=Path)
    p.add_argument("--page-size", help="a4, letter, or WxH in mm (or with pt or in)")
    p.add_argument("--max-pages", type=int, help="The page limit, as the user's source states it")
    p.add_argument("--content-pages", type=int, help="How many pages the limit counts in this PDF")
    p.add_argument("--limit-source", help="Where the limit comes from: file or URL and the date it was read")
    p.add_argument("--out", type=Path, default=Path("latex-build"))
    args = parser.parse_args(argv)
    try:
        if args.command == "detect":
            if not args.path.exists():
                return fail(f"no such file or folder: {args.path}")
            result = detect(args.path)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["decided"] else 1
        return cmd_parse(args) if args.command == "parse" else cmd_pdf(args)
    except OSError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
