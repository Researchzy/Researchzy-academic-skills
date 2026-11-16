#!/usr/bin/env python3
"""Pack the files a LaTeX build uses into a new folder and two archives, with a manifest.

  latex_pack.py pack paper/main.tex --out latex-build/source
  latex_pack.py pack paper/main.tex --out latex-build/source --fls paper/main.fls --warn-size-mb 10
  latex_pack.py pack paper/main.tex --out latex-build/source --keep-comments

Which files: with --fls, the files the last build read that lie inside the project folder (the
folder of the main file); without it, the files reached by following \\input, \\include, \\subfile
and \\import, the \\includegraphics targets (looked up with \\graphicspath and the engine's list of
extensions, in its order), listings and included PDFs, the bibliography and its style, and the
class and style files that sit in the project. Either way the .bib and .bst files are added (BibTeX
reads them, TeX does not, so they are not in the .fls) and <main>.bbl when it exists.

Comments are removed from .tex files (not from .cls, .sty, .bst or any other file: a venue's files
are copied byte for byte) without changing the output: never a \\%, nothing inside verbatim,
lstlisting, minted, filecontents or comment environments, \\verb, \\url or \\href, and a % that ends
a line after text is kept because it suppresses a space.

It refuses to write into the project folder or into a folder that exists and is not empty, and
never touches the project. It warns about absolute and ../ paths, files read from outside the
project, spaces and non-ASCII characters in file names, files larger than --warn-size-mb, a missing
or stale .bbl, and kept comment environments; it lists every project file it left out and why.

Writes <out>/ (the files, same layout), <out>.tar.gz and <out>.zip (files at the archive's root)
and <out>.MANIFEST.md beside the folder, and prints the commands that rebuild the archive in an
empty folder: run them, because only a clean build proves the archive is complete. Exit 1 when a
file the build needs could not be found or lies outside the project; 2 on bad arguments.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from latex_guard import BIB_RE, CLASS_RE, PACKAGE_RE, braced, line_of, read_tree, strip_comments, unsafe_path  # noqa: E402
import latex_log  # noqa: E402

# The order in which the graphics drivers try extensions (pdftex.def and luatex.def; xetex.def).
PDF_EXTENSIONS = [".pdf", ".png", ".jpg", ".mps", ".jpeg", ".jbig2", ".jb2", ".PDF", ".PNG", ".JPG", ".JPEG",
                  ".JBIG2", ".JB2", ".eps"]
XETEX_EXTENSIONS = [".pdf", ".PDF", ".ai", ".AI", ".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG", ".jp2", ".JP2",
                    ".jpf", ".JPF", ".bmp", ".BMP", ".ps", ".PS", ".eps", ".EPS", ".mps", ".MPS"]
BUILD_OUTPUT = {".aux", ".log", ".out", ".toc", ".lof", ".lot", ".fls", ".fdb_latexmk", ".synctex", ".bcf", ".blg",
                ".nav", ".snm", ".vrb", ".xdv", ".dvi", ".idx", ".ind", ".ilg", ".glo", ".gls", ".glg", ".ist", ".loa",
                ".lol", ".thm", ".brf", ".auxlock", ".tdo", ".run.xml", ".synctex.gz", ".bak", ".swp"}
STRIP_SUFFIXES = {".tex", ".tikz", ".pgf"}
FILE_ARG_RE = re.compile(r"\\(lstinputlisting|verbatiminput|includepdf|includesvg|inputminted)\*?\s*(?:\[[^\]]*\]\s*)?"
                         r"(?:\{[^{}]*\}\s*)?(?=\{)")
GRAPHICS_RE = re.compile(r"\\includegraphics\*?\s*(?:\[[^\]]*\]\s*){0,2}(?=\{)")
SYSTEM_SUFFIXES = {".cnf", ".fmt", ".map", ".enc", ".tfm", ".vf", ".pfb", ".otf", ".ttf", ".ttc"}


class Refused(Exception):
    """The arguments would overwrite something or cannot work."""


def suffix(path: Path) -> str:
    name = path.name
    for double in (".synctex.gz", ".run.xml"):
        if name.endswith(double):
            return double
    return path.suffix


def build_output(path: Path, main: Path) -> bool:
    return suffix(path) in BUILD_OUTPUT or path.name == main.with_suffix(".pdf").name or "-eps-converted-to" in path.name


def outside_note(path: Path):
    """None for a file of the TeX installation; otherwise why a file outside the project matters."""
    if "texmf" in path.parts or "texmf-local" in path.parts:
        return f"read from a personal or local TeX tree: {path}; the receiving system will not have it"
    installed = any(part.lower().startswith(("texlive", "texmf-", "miktex")) or part == "TeX" for part in path.parts)
    if installed or str(path).startswith(("/dev/", "/proc/", "/etc/", "/var/cache/")) or re.search(r"\.\d+pk$", path.name):
        return None
    if path.suffix.lower() in SYSTEM_SUFFIXES:
        return f"font or TeX file read from outside the project: {path}; the receiving system needs it too"
    return f"read from outside the project folder: {path}; move it into the project and change the path"


def files_from_fls(fls: Path, project: Path, main: Path, skip: list, kept: dict, warnings: list) -> None:
    pwd = fls.parent
    for line in fls.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("PWD "):
            pwd = Path(line[4:].strip())
            continue
        if not line.startswith("INPUT "):
            continue
        path = Path(line[6:].strip())
        path = (path if path.is_absolute() else pwd / path).resolve()
        if project not in path.parents:
            note = outside_note(path)
            if note and note not in warnings:
                warnings.append(note)
            continue
        if any(s == path or s in path.parents for s in skip) or not path.is_file():
            continue
        if build_output(path, main) and path != main.with_suffix(".bbl"):
            continue
        kept.setdefault(path.relative_to(project).as_posix(), "read by the build (.fls)")


def find_graphic(target: str, here: Path, project: Path, prefixes: list, extensions: list):
    for prefix in prefixes:
        for base in (project, here):
            stem = base / (prefix + target)
            names = [stem] if Path(target).suffix.lower() in {e.lower() for e in extensions} else []
            for candidate in names + [stem.with_name(stem.name + ext) for ext in extensions]:
                if candidate.is_file():
                    return candidate.resolve()
    return None


def files_from_source(main: Path, project: Path, engine: str, kept: dict, warnings: list, missing: list) -> list:
    """Add what the source names; return the bibliography files named."""
    tree = read_tree(main)
    for item in tree["missing_inputs"]:
        problem = item["problem"] or "not found"
        missing.append(f"\\{item['command']}{{{item['target']}}} at {item['at']}: {problem}")
    extensions = XETEX_EXTENSIONS if engine == "xelatex" else PDF_EXTENSIONS
    bibs, local = [], []
    for entry in tree["files"]:
        if entry["outside"]:
            missing.append(f"{entry['path']} is input from outside the project folder")
            continue
        kept.setdefault(entry["rel"], "input from the main file")
        text, here = entry["text"], entry["path"].parent
        found = re.search(r"\\graphicspath\s*\{((?:\{[^{}]*\}\s*)*)\}", text)
        prefixes = [""] + (re.findall(r"\{([^{}]*)\}", found.group(1)) if found else [])
        for regex, kind in ((GRAPHICS_RE, "graphics"), (FILE_ARG_RE, "file read by the source")):
            for m in regex.finditer(text):
                target = (braced(text, m.end())[0] or "").strip()
                where = f"{entry['rel']}:{line_of(text, m.start())}"
                if not target:
                    continue
                if unsafe_path(target):
                    missing.append(f"{target} at {where}: {unsafe_path(target)}")
                    continue
                path = (find_graphic(target, here, project, prefixes, extensions) if kind == "graphics"
                        else next((p.resolve() for p in (project / target, here / target) if p.is_file()), None))
                if path is None or project not in path.parents:
                    missing.append(f"{target} at {where}: not found in the project")
                else:
                    kept.setdefault(path.relative_to(project).as_posix(), kind)
        for m in BIB_RE.finditer(text):
            for name in m.group(2).split(","):
                name = name.strip()
                if m.group(1) == "bibliography" and not name.endswith(".bib"):
                    name += ".bib"
                elif m.group(1) == "bibliographystyle":
                    name += ".bst"
                if name.endswith(".bib"):
                    bibs.append(name)
                if (project / name).is_file():
                    kept.setdefault((project / name).resolve().relative_to(project).as_posix(),
                                    "bibliography style" if name.endswith(".bst") else "bibliography")
                elif name.endswith(".bib"):
                    missing.append(f"{name} (named at {entry['rel']}:{line_of(text, m.start())}) is not in the project")
        local += [(name.strip(), ".cls") for m in CLASS_RE.finditer(text) for name in m.group(2).split(",")]
        for m in PACKAGE_RE.finditer(text):
            local += [(name.strip(), ".sty") for name in m.group(2).split(",")]
            style = re.search(r"(?:^|,)\s*(?:bib)?style\s*=\s*([\w-]+)", m.group(1) or "")
            local += [(style.group(1), ".bbx"), (style.group(1), ".cbx")] if style else []
    seen = set()
    while local:
        name, ext = local.pop()
        path = project / (name + ext)
        if (name, ext) in seen or not path.is_file():
            continue
        seen.add((name, ext))
        kept.setdefault(path.relative_to(project).as_posix(), "class or style file in the project")
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"\\(?:RequirePackage|usepackage)\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}", text):
            local += [(n.strip(), ".sty") for n in m.group(1).split(",")]
        for m in re.finditer(r"\\LoadClass\w*\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}", text):
            local.append((m.group(1).strip(), ".cls"))
    return bibs


def name_warnings(rel: str, path: Path, size_mb) -> list:
    out = []
    if " " in rel:
        out.append(f"space in file name: {rel}")
    if not rel.isascii():
        out.append(f"non-ASCII character in file name: {rel}")
    if size_mb is not None and path.stat().st_size > size_mb * 1_000_000:
        out.append(f"{rel} is {path.stat().st_size / 1_000_000:.1f} MB (over {size_mb:g} MB)")
    return out


def copy_file(source: Path, target: Path, strip: bool) -> list:
    """Copy one file; return notes about comment environments kept."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if not strip:
        shutil.copyfile(source, target)
        return []
    data = source.read_bytes()
    try:
        text, codec = data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        text, codec = data.decode("latin-1"), "latin-1"
    stripped = strip_comments(text)
    target.write_bytes(stripped.encode(codec))
    return [f"{source.name}:{line_of(stripped, m.start())}: {m.group(0)} kept; its text is not typeset but is in the source"
            for m in re.finditer(r"\\begin\s*\{comment\}|\\iffalse\b", stripped)]


def pack(args) -> dict:
    main = args.main.resolve()
    if not main.is_file():
        raise Refused(f"no such file: {args.main}")
    project, out = main.parent, args.out.resolve()
    if out == project or out in project.parents:
        raise Refused(f"{args.out} is the project folder or contains it: choose a new folder such as latex-build/source")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise Refused(f"{args.out} exists and is not empty: choose a new folder")
    beside = [out.with_name(out.name + ext) for ext in (".tar.gz", ".zip", ".MANIFEST.md")]
    if any(p.exists() for p in beside):
        raise Refused(f"{', '.join(str(p) for p in beside if p.exists())} exists: choose another --out name")
    if args.fls and not args.fls.is_file():
        raise Refused(f"no such file: {args.fls}")
    found = latex_log.detect(main)
    engine = (found.get("engine") or {}).get("value") or "pdflatex"
    kept, warnings, missing = {}, [], []
    skip = [out, project / "latex-build"]
    if args.fls:
        files_from_fls(args.fls.resolve(), project, main, skip, kept, warnings)
    bibs = files_from_source(main, project, engine, kept, warnings, missing)
    bbl = main.with_suffix(".bbl")
    if bbl.is_file():
        kept.setdefault(bbl.name, "bibliography as built (.bbl)")
        stale = [b for b in bibs if (project / b).is_file() and (project / b).stat().st_mtime > bbl.stat().st_mtime]
        if stale:
            warnings.append(f"{bbl.name} is older than {', '.join(stale)}: build again before packing")
    elif bibs:
        warnings.append(f"no {bbl.name}: build first, so that the archive carries the bibliography as built")
    for rel in list(kept):
        if any(s == project / rel or s in (project / rel).parents for s in skip):
            kept.pop(rel)
    out.mkdir(parents=True, exist_ok=True)
    for rel in sorted(kept):
        warnings += name_warnings(rel, project / rel, args.warn_size_mb)
        strip = not args.keep_comments and Path(rel).suffix in STRIP_SUFFIXES
        warnings += copy_file(project / rel, out / rel, strip)
    if args.keep_comments:
        warnings.append("comments kept (--keep-comments): they may hold notes, names and old text")
    left_out = []
    for path in sorted(project.rglob("*")):
        rel = path.relative_to(project).as_posix()
        if not path.is_file() or rel in kept or any(s == path or s in path.parents for s in skip):
            continue
        hidden = any(part.startswith(".") for part in path.relative_to(project).parts)
        if hidden and ".git" in path.relative_to(project).parts:
            continue
        reason = ("hidden file" if hidden else "build output" if build_output(path, main) else "not used by the build")
        left_out.append({"file": rel, "reason": reason})
    tar_path, zip_path, manifest = beside
    files = sorted(p for p in out.rglob("*") if p.is_file())
    with tarfile.open(tar_path, "w:gz") as tar:
        for path in files:
            tar.add(path, arcname=path.relative_to(out).as_posix())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(out).as_posix())
    only_bbl = (out / bbl.name).is_file() and not any((out / b).is_file() for b in bibs)
    command = (f"latexmk {latex_log.ENGINE_FLAGS.get(engine, '-pdf')} -file-line-error -halt-on-error "
               f"-interaction=nonstopmode {'-bibtex- ' if only_bbl else ''}{shlex.quote(main.name)}")
    script = Path(__file__).resolve().parent / "latex_log.py"
    rebuild = [f'tmp=$(mktemp -d) && tar -xzf {shlex.quote(str(tar_path))} -C "$tmp"',
               f'(cd "$tmp" && {command})',
               f'python3 {shlex.quote(str(script))} parse "$tmp/{main.with_suffix(".log").name}" '
               f'--out {shlex.quote(str(out.parent / (out.name + "-rebuild")))}']
    result = {"tool": "researchzy-latex", "command": "pack", "main": main.name, "project": str(project),
              "out": str(out), "engine": engine, "kept": [{"file": k, "reason": v} for k, v in sorted(kept.items())],
              "left_out": left_out, "problems": missing, "warnings": warnings,
              "archives": [str(tar_path), str(zip_path)], "manifest": str(manifest), "rebuild": rebuild,
              "comments_stripped": not args.keep_comments}
    write_manifest(manifest, result)
    return result


def write_manifest(path: Path, result: dict) -> None:
    lines = ["# Source archive manifest", "", f"Main file `{result['main']}` in `{result['project']}`; engine "
             f"{result['engine']}. Comments {'removed' if result['comments_stripped'] else 'kept'}.", "",
             f"Archives: `{result['archives'][0]}`, `{result['archives'][1]}`.", ""]
    if result["problems"]:
        lines += ["## Files the build needs that are not in the archive", ""] + [f"- {p}" for p in result["problems"]] + [""]
    lines += ["## Warnings", ""] + ([f"- {w}" for w in result["warnings"]] or ["None."]) + [""]
    lines += [f"## Kept ({len(result['kept'])})", "", "| File | Why |", "|---|---|"]
    lines += [f"| {k['file']} | {k['reason']} |" for k in result["kept"]]
    lines += ["", f"## Left out ({len(result['left_out'])})", "", "| File | Why |", "|---|---|"]
    lines += [f"| {k['file']} | {k['reason']} |" for k in result["left_out"]] or ["| none | |"]
    lines += ["", "## Rebuild test", "", "Build the archive in an empty folder; the archive is complete only when this "
              "build has no errors and no undefined references or citations:", "", "```sh"] + result["rebuild"] + ["```"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pack the files a LaTeX build uses into a new folder and archives.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack", help="Copy the used files, strip comments, write archives and a manifest")
    p.add_argument("main", type=Path, help="The main .tex file")
    p.add_argument("--out", type=Path, required=True, help="A new or empty folder outside the project's own files")
    p.add_argument("--fls", type=Path, help="The .fls of the last build (latexmk writes it): the most complete list")
    p.add_argument("--keep-comments", action="store_true", help="Copy .tex files unchanged")
    p.add_argument("--warn-size-mb", type=float, help="Warn about files larger than this many megabytes")
    args = parser.parse_args(argv)
    try:
        result = pack(args)
    except (Refused, OSError) as exc:
        print(f"latex_pack: {exc}", file=sys.stderr)
        return 2
    summary = {k: result[k] for k in ("out", "archives", "manifest", "problems", "warnings", "rebuild")}
    summary.update(kept=len(result["kept"]), left_out=len(result["left_out"]))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
