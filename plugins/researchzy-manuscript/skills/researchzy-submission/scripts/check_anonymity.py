#!/usr/bin/env python3
"""Find what could identify the authors in the files of a blinded submission. Reports; edits nothing.

  check_anonymity.py submission/example-journal --identified title-page.md cover-letter.md
  check_anonymity.py submission/example-journal --extra okafor-lab --extra "Northtown Soil Survey"

Identifiers come from authors.json (default: in the folder): each author's name, family name,
"name_native", initials with and without full stops, email and its institutional domain, ORCID,
the parts of each affiliation, grant numbers, ethics and registration ids, and the lists under
"anonymity" ("handles", "repositories", "earlier_venues", "other"); add more with --extra or
--extra-file (one per line). Every file under the folder is read except requirements.json,
authors.json, report.md, anonymity.md, reviewer-candidates.json and the --identified files,
which are meant to carry names.

  identifier        an identifier in the text, with file and line (in a LaTeX comment, in a
                    reference list or in the text)
  self_citation     "our previous work", "we previously showed", "in our earlier study" …,
                    noting whether the sentence carries a citation
  section           an acknowledgements or funding section, or \\thanks, in a blinded file
  url               repository, personal and institutional links (anonymised mirrors are not hits)
  latex             \\author, \\affiliation, \\institute, \\address, \\email, \\orcid, \\thanks with content
  metadata          .docx, .xlsx, .pptx creator, last modified by, company, manager; tracked-change
                    and comment authors; PDF properties through pdfinfo; text in image files'
                    metadata bytes
  path              an absolute home-folder path (it carries a user name)
  file_name         an author's name, family name, email or handle in a file or folder name

A file or property that could not be read is listed as not_checked: PDF properties when pdfinfo
is missing, PDF text when pdftotext is missing, the pixels of every image. Writes anonymity.md
(default: in the folder) and prints JSON. Exit codes: 0 no hit; 1 a hit; 2 usage error.

Standard library only; pdfinfo and pdftotext (Poppler) are optional. Portions are derived from
MIT-licensed code: see LICENSE-MIT.txt next to this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree

TOOL = "researchzy-submission"
SKIP = ("requirements.json", "authors.json", "report.md", "anonymity.md", "reviewer-candidates.json")
TEXT = {".md", ".markdown", ".txt", ".tex", ".bib", ".bbl", ".csv", ".tsv", ".json", ".yaml", ".yml", ".py", ".r",
        ".rmd", ".qmd", ".ipynb", ".html", ".htm", ".xml", ".sty", ".cls", ".m", ".jl", ".sh"}
VECTOR = {".svg", ".eps", ".ps"}               # pictures stored as text: read as text, but not looked at
OOXML = {".docx", ".xlsx", ".pptx", ".docm"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".bmp", ".webp"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# Values of an author field that name a program or nobody, not a person.
NOT_A_PERSON = {"", "unknown", "anonymous", "author", "authors", "user", "administrator", "admin", "microsoft office user",
                "pandoc", "libreoffice", "openoffice", "word", "microsoft word", "overleaf", "latex", "pdftex", "quarto",
                "python-docx", "r", "rstudio", "google", "anonymized", "anonymised", "blinded"}
WEBMAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "icloud.com", "me.com",
           "proton.me", "protonmail.com", "qq.com", "163.com", "126.com", "aol.com", "gmx.de", "gmx.net"}
SELF_CITE = re.compile(
    r"\b(?:our|my)\s+(?:own\s+)?(?:previous|prior|earlier|recent|past|preliminary|former)\s+(?:\w+\s+)?"
    r"(?:work|works|study|studies|paper|papers|research|findings|results|analys[ie]s|trial|survey|experiments?|model)\b"
    r"|\bwe\s+(?:have\s+)?(?:previously|recently|earlier|already)\s+(?:\w+\s+)?(?:showed|shown|reported|demonstrated"
    r"|found|described|proposed|developed|introduced|published|presented|argued|established)\b"
    r"|\b(?:as|which)\s+we\s+(?:showed|reported|demonstrated|found|described|proposed|argued)\s+(?:in|previously|earlier|before)\b"
    r"|\bin\s+(?:our|my)\s+(?:earlier|previous|prior|recent|companion|own)\b"
    r"|\b(?:our|my)\s+(?:group|lab|laboratory|team)\s+(?:has|have|had|previously|recently)\b"
    r"|\bwe\s+(?:extend|build\s+on|build\s+upon|follow\s+up\s+on)\s+(?:our|my)\b", re.I)
CITATION = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?\s*[\[{]|\[-?@|\[\d+(?:[-–,]\s*\d+)*\]|\(\s*[A-Z][^()]{0,60}\d{4}[a-z]?\s*\)")
SECTION = re.compile(r"^\s*(?:#{1,6}\s*|\*\*\s*|__\s*|\\(?:sub)*section\*?\s*\{\s*|\\begin\{)?"
                     r"(acknowledge?ments?|acks|funding(?: statement| sources?)?|financial support|grant support"
                     r"|role of the funding source)\b\s*(?:\}|\*\*|__|:)?(.*)$", re.I)
LATEX = re.compile(r"\\(author|affiliation|affil|institute|institution|address|email|orcid|thanks|authornote)\*?"
                   r"\s*(?:\[[^\]]*\])?\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
ANONYMOUS = re.compile(r"anonym|blind|withheld|redacted|^\s*(?:authors?|author names?)\s*$|^\s*$", re.I)
URL = re.compile(r"(?:https?://|www\.)[^\s<>()\[\]{}\"'|]+|\b(?:github|gitlab)\.com/[^\s<>()\[\]{}\"'|]+", re.I)
ANON_URL = re.compile(r"anonymous\.4open\.science|anonymous\.|/anon(?:ymous|ymized|ymised)?[-/]|openreview\.net", re.I)
REPOSITORY = re.compile(r"github\.com|gitlab\.|bitbucket\.org|huggingface\.co|osf\.io|zenodo\.org|figshare\.com|"
                        r"codeocean\.com|dataverse|kaggle\.com|dryad|sourceforge\.net|npmjs\.com|pypi\.org|"
                        r"cran\.r-project\.org/package", re.I)
PERSONAL = re.compile(r"\.github\.io|sites\.google\.com|/~|/people/|/staff/|/faculty/|/profile|/users?/|/homepage|"
                      r"\.edu\b|\.ac\.[a-z]{2}\b|\.edu\.[a-z]{2}\b|\buni-[a-z]+\.|\.uni\.|lab\.|\blinkedin\.com|"
                      r"researchgate\.net|scholar\.google|orcid\.org|twitter\.com|x\.com/", re.I)
HOME_PATH = re.compile(r"/(?:Users|home)/[^\s<>\"'(){}]+"
                       r"|[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+[^\s<>\"'(){}]+")
REFERENCES = re.compile(r"^\s*(?:#{1,6}\s*|\\(?:sub)*section\*?\{)?\s*(?:references|bibliography|literature cited)"
                        r"\s*\}?\s*$|\\begin\{thebibliography\}|\\bibliography\{|\\printbibliography", re.I)


def fold(text: str) -> str:
    """Lower case without accents, so that "Lindqvíst" and "lindqvist" match."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def identifiers(record: dict, extra: list) -> list:
    """(kind, value, pattern) for everything that could identify an author."""
    out = []

    def add(kind, value, case_sensitive=False, body=None, before=r"(?<![\w@.])", after=r"(?![\w@]|\.\w)"):
        value = " ".join(str(value or "").split())
        if len(value) < 2 or any(v == value for _, v, _ in out):
            return
        body = body or re.escape(value if case_sensitive else fold(value))
        out.append((kind, value, re.compile(before + body + after, 0 if case_sensitive else re.I)))

    for author in record.get("authors") or []:
        name = " ".join(str(author.get("name") or "").split())
        add("name", name)
        add("name", author.get("name_native"), before="", after="")      # no word boundaries in CJK text
        add("family name", author.get("family_name") or (name.split()[-1] if name else ""), case_sensitive=True)
        initials = "".join(c for c in str(author.get("initials") or "".join(p[0] for p in re.split(r"[\s-]+", name) if p))
                           if c.isalpha()).upper()
        if len(initials) >= 2:
            add("initials", ".".join(initials) + ".", case_sensitive=True, body=r"\.\s*".join(initials) + r"\.")
            add("initials", initials, case_sensitive=True)
        email = str(author.get("email") or "").strip()
        add("email", email)
        domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
        if domain and domain not in WEBMAIL:
            add("email domain", domain, before=r"(?<![\w@-])")
        add("ORCID", re.sub(r"^https?://orcid\.org/", "", str(author.get("orcid") or "")))
        for affiliation in author.get("affiliations") or []:
            for part in str(affiliation).split(","):
                if len(part.split()) >= 2:          # one word is a city or a country: too common to count
                    add("institution", part)
        for handle in author.get("handles") or []:
            add("handle", handle)
    for entry in record.get("funding") if isinstance(record.get("funding"), list) else []:
        add("grant number", (entry or {}).get("grant_number") if isinstance(entry, dict) else "")
    for key, field, kind in (("ethics", "approval_id", "ethics approval id"), ("registrations", "id", "registration id")):
        for entry in record.get(key) if isinstance(record.get(key), list) else []:
            add(kind, entry.get(field) if isinstance(entry, dict) else "")
    lists = record.get("anonymity") if isinstance(record.get("anonymity"), dict) else {}
    for key, kind in (("handles", "handle"), ("repositories", "repository"), ("earlier_venues", "earlier venue"),
                      ("other", "other")):
        for value in lists.get(key) or []:
            add(kind, value)
    for value in extra:
        add("extra", value)
    return out


def hit(kind: str, file: str, where, found: str, text: str = "", **extra) -> dict:
    return {"kind": kind, "file": file, "where": where, "found": found, "text": " ".join(text.split())[:160], **extra}


# ---------------------------------------------------------------------------------------------
# Text


def scan_lines(name: str, lines: list, ids: list, tex: bool) -> list:
    """Identifier, self-citation, section, URL, LaTeX and path hits in (where, line) pairs."""
    hits, in_refs = [], name.lower().endswith((".bib", ".bbl"))
    for where, line in lines:
        in_refs = in_refs or bool(REFERENCES.search(line))
        comment = re.search(r"(?<!\\)%", line) if tex else None
        folded, reported = fold(line), []
        for kind, value, pattern in ids:
            m = pattern.search(line if pattern.flags & re.I == 0 else folded)
            if m and not any(fold(value) in r for r in reported):      # "Okafor" inside "Mira Okafor" is one hit
                reported.append(fold(value))
                context = "LaTeX comment" if comment and m.start() > comment.start() else \
                    "reference list" if in_refs else "text"
                hits.append(hit("identifier", name, where, f"{kind}: {value}", line, context=context))
        visible = line[:comment.start()] if comment else line
        phrases = [m.group(0) for m in SELF_CITE.finditer(visible)]
        if phrases:
            hits.append(hit("self_citation", name, where, "; ".join(phrases), line, cited=bool(CITATION.search(visible))))
        section = SECTION.match(visible)
        # a heading, a bare line "Acknowledgements", or a run-in label "Funding: …"; not a sentence
        if section and len(visible.strip()) <= 120 and (not section.group(2).strip() or ":" in visible[:section.end(1) + 3]
                                                        or visible.lstrip()[:1] in ("#", "*", "_", "\\")):
            hits.append(hit("section", name, where, f"{section.group(1)} section in a blinded file", line))
        for m in LATEX.finditer(visible) if tex else ():
            if m.group(1) == "thanks" or not ANONYMOUS.search(m.group(2)):
                hits.append(hit("latex", name, where, f"\\{m.group(1)}{{{m.group(2).strip()[:60]}}}", line))
        for m in URL.finditer(line):
            url = m.group(0).rstrip(".,;:")
            if ANON_URL.search(url):
                continue
            kind = "repository link" if REPOSITORY.search(url) else "personal or institutional link" \
                if PERSONAL.search(url) else None
            if kind:
                hits.append(hit("url", name, where, f"{kind}: {url}", line, context="reference list" if in_refs else "text"))
        for m in HOME_PATH.finditer(line):
            hits.append(hit("path", name, where, m.group(0), line))
    return hits


# ---------------------------------------------------------------------------------------------
# Office files, PDFs, images


def xml_text(data: bytes) -> str:
    return " ".join(re.sub(rb"<[^>]+>", b" ", data).decode("utf-8", "replace").split())


def office_paragraphs(archive: zipfile.ZipFile) -> list:
    """The paragraphs of word/document.xml, numbered from 1."""
    root = ElementTree.fromstring(archive.read("word/document.xml"))
    return [(f"paragraph {i}", "".join(t.text or "" for t in p.iter(W + "t")))
            for i, p in enumerate(root.iter(W + "p"), 1)]


def scan_office(path: Path, name: str, ids: list) -> tuple:
    hits, unread = [], []
    try:
        with zipfile.ZipFile(path) as archive:
            parts = {n: archive.read(n) for n in archive.namelist() if n.endswith((".xml", ".rels"))}
            body = office_paragraphs(archive) if "word/document.xml" in parts else []
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError, KeyError) as exc:
        return [], [f"{name}: cannot be read as an Office file ({exc})"]
    hits += scan_lines(name, body, ids, tex=False)
    for part, data in parts.items():
        text = data.decode("utf-8", "replace")
        if part in ("docProps/core.xml", "docProps/app.xml"):
            for field in ("dc:creator", "cp:lastModifiedBy", "Company", "Manager"):
                for value in re.findall(rf"<{field}>([^<]*)</{field}>", text):
                    if fold(value.strip()) not in NOT_A_PERSON:
                        hits.append(hit("metadata", name, part, f"{field.split(':')[-1]}: {value.strip()}"))
        authors = set(re.findall(r'\bw(?:15)?:(?:author|userId)="([^"]*)"', text))
        hits += [hit("metadata", name, part, f"tracked-change or comment author: {a}") for a in sorted(authors)
                 if fold(a.strip()) not in NOT_A_PERSON]
        hits += [hit("path", name, part, p) for p in dict.fromkeys(HOME_PATH.findall(text))]
        if part not in ("word/document.xml", "docProps/core.xml", "docProps/app.xml", "[Content_Types].xml"):
            # headers, footers, footnotes, comments, slides, sheets, custom properties; link targets in .rels
            text = text if part.endswith(".rels") else xml_text(data)
            hits += [h for h in scan_lines(name, [(part, text)], ids, tex=False)
                     if h["kind"] in ("identifier", "self_citation", "url")]
    return hits, unread


def run_tool(command: list) -> str | None:
    try:
        done = subprocess.run(command, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else None


def scan_pdf(path: Path, name: str, ids: list) -> tuple:
    hits, unread = [], []
    if shutil.which("pdfinfo"):
        info = run_tool(["pdfinfo", "-enc", "UTF-8", str(path)])
        if info is None:
            unread.append(f"{name}: pdfinfo could not read the file, so its properties were not checked")
        for line in (info or "").splitlines():
            field, _, value = line.partition(":")
            value = value.strip()
            if field in ("Author", "Title", "Subject", "Keywords", "Creator", "Producer") and value:
                named = [f"{kind}: {v}" for kind, v, pattern in ids
                         if pattern.search(value if pattern.flags & re.I == 0 else fold(value))]
                if named or (field == "Author" and fold(value) not in NOT_A_PERSON):
                    found = f"{field}: {value}" + (f" ({named[0]})" if named else "")
                    hits.append(hit("metadata", name, "PDF properties", found))
    else:
        unread.append(f"{name}: PDF properties not checked, because pdfinfo (Poppler) is not installed")
    text = run_tool(["pdftotext", "-q", "-enc", "UTF-8", str(path), "-"]) if shutil.which("pdftotext") else None
    if text is None:
        unread.append(f"{name}: PDF text not checked (" + ("pdftotext is not installed)" if not shutil.which("pdftotext")
                                                           else "pdftotext could not read it)"))
    else:
        pages = text.split("\f")
        hits += scan_lines(name, [(f"page {i}", line) for i, page in enumerate(pages, 1) for line in page.splitlines()],
                           ids, tex=False)
    return hits, unread


def scan_image(path: Path, name: str, ids: list) -> tuple:
    """Metadata text (EXIF, XMP, PNG text chunks) is plain bytes inside the file; pixels are not read."""
    with path.open("rb") as handle:
        data = handle.read(1 << 20)                  # metadata sits near the start or the end of the file
        handle.seek(max(len(data), path.stat().st_size - (1 << 18)))
        data += handle.read()
    text = data.decode("latin-1")
    hits = [hit("metadata", name, "image metadata", f"{kind}: {value}") for kind, value, pattern in ids
            if kind in ("name", "family name", "email", "ORCID", "institution", "handle")
            and pattern.search(text if pattern.flags & re.I == 0 else fold(text))]
    hits += [hit("path", name, "image metadata", p) for p in dict.fromkeys(HOME_PATH.findall(text))][:5]
    return hits, [f"{name}: the picture itself was not looked at (labels, logos, maps, scanned forms)"]


def scan_file_name(rel: str, ids: list) -> list:
    spaced = re.sub(r"[_\-.+/\\]+", " ", rel)          # "Okafor_draft.docx" is read as "Okafor draft docx"
    return [hit("file_name", rel, "file name", f"{kind}: {value}", rel) for kind, value, pattern in ids
            if kind in ("name", "family name", "email", "handle", "repository")
            and any(pattern.search(x if pattern.flags & re.I == 0 else fold(x)) for x in (rel, spaced))]


# ---------------------------------------------------------------------------------------------


def scan(folder: Path, ids: list, identified: set) -> dict:
    hits, unread, read, skipped = [], [], [], []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        hidden = any(part.startswith(".") for part in path.parts[len(folder.parts):])
        if path.name in SKIP or path.resolve() in identified or hidden:
            skipped.append(rel)
            continue
        hits += scan_file_name(rel, ids)
        suffix = path.suffix.lower()
        try:
            if suffix in TEXT | VECTOR:
                lines = list(enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1))
                found = scan_lines(rel, lines, ids, tex=suffix in (".tex", ".sty", ".cls", ".bbl"))
                missed = [f"{rel}: the picture itself was not looked at (labels, logos, maps)"] if suffix in VECTOR else []
            elif suffix in OOXML:
                found, missed = scan_office(path, rel, ids)
            elif suffix == ".pdf":
                found, missed = scan_pdf(path, rel, ids)
            elif suffix in IMAGES:
                found, missed = scan_image(path, rel, ids)
            else:
                found, missed = [], [f"{rel}: a {suffix or 'file without an extension'} file is not read by this script"]
        except OSError as exc:
            found, missed = [], [f"{rel}: cannot be read ({exc.strerror or exc})"]
        hits += found
        unread += missed
        read.append(rel)
    return {"hits": hits, "not_checked": unread, "files_read": read, "skipped": skipped}


def write_report(path: Path, folder: Path, result: dict, ids: list) -> None:
    def cell(value) -> str:
        return " ".join(str(value).split()).replace("|", "\\|")

    by_kind: dict = {}
    for h in result["hits"]:
        by_kind[h["kind"]] = by_kind.get(h["kind"], 0) + 1
    lines = [f"# Anonymity check: {folder.name}", "", "Internal working report. Do not upload it with the submission.", "",
             f"Files read: {len(result['files_read'])}. Left out as meant to carry names or as working files: "
             + (", ".join(result["skipped"]) or "none") + ".", "",
             f"Identifiers looked for: {len(ids)} ("
             + ", ".join(sorted({k for k, _, _ in ids})) + "). Nothing was changed in any file.", "",
             f"**{len(result['hits'])} hit(s)**" + (": " + ", ".join(f"{k} {n}" for k, n in sorted(by_kind.items()))
                                                     if by_kind else ". Not checked items below are not a pass."), ""]
    if result["hits"]:
        lines += ["| File | Where | Kind | Found | Text |", "|---|---|---|---|---|"]
        for h in result["hits"]:
            kind = h["kind"] + (f" ({h['context']})" if h.get("context") else "") + \
                (" (with a citation)" if h.get("cited") else "")
            lines.append(f"| {cell(h['file'])} | {cell(h['where'])} | {cell(kind)} | {cell(h['found'])} | {cell(h['text'])} |")
    lines += ["", "## Not checked", ""] + [f"- {cell(x)}" for x in result["not_checked"]] + \
        ([] if result["not_checked"] else ["Every file in the folder was read."])
    lines += ["", "## Still to look at by hand", "",
              "- Every figure, as an image: names, institution logos, maps, photographs of identifiable places, "
              "scanned forms.",
              "- Supplementary files and archives that are not in this folder, and the code and data links.",
              "- The PDF the submission system builds from the upload: open it and search it for the names.",
              "- Wording that identifies without a name: a cohort, site, instrument or project named in the text."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Find identifying details in the files of a blinded submission.")
    parser.add_argument("folder", help="The package folder, submission/<venue-slug>")
    parser.add_argument("--authors", help="Authors file (default: authors.json in the folder)")
    parser.add_argument("--identified", nargs="*", default=[], help="Files meant to carry names: title page, cover letter")
    parser.add_argument("--extra", action="append", default=[], help="Another identifier: a handle, a project name …")
    parser.add_argument("--extra-file", help="A text file with one more identifier per line")
    parser.add_argument("--out", help="Folder for anonymity.md (default: the package folder)")
    args = parser.parse_args(argv)
    folder = Path(args.folder)
    try:
        if not folder.is_dir():
            raise ValueError(f"the folder {folder} does not exist")
        record = json.loads(Path(args.authors or folder / "authors.json").read_text(encoding="utf-8-sig"))
        if not isinstance(record, dict) or not isinstance(record.get("authors"), list):
            raise ValueError("the authors file needs an \"authors\" list")
        extra = list(args.extra)
        if args.extra_file:
            extra += [x.strip() for x in Path(args.extra_file).read_text(encoding="utf-8").splitlines()
                      if x.strip() and not x.startswith("#")]
        missing = [f for f in args.identified if not (Path(f).is_file() or (folder / f).is_file())]
        if missing:
            raise ValueError(f"--identified: no such file: {', '.join(missing)}")
    except (OSError, ValueError) as exc:
        print(f"check_anonymity: {exc}", file=sys.stderr)
        return 2
    identified = {(Path(f) if Path(f).is_file() else folder / f).resolve() for f in args.identified}
    ids = identifiers(record, extra)
    result = scan(folder, ids, identified)
    out = Path(args.out) if args.out else folder
    out.mkdir(parents=True, exist_ok=True)
    write_report(out / "anonymity.md", folder, result, ids)
    print(json.dumps({"tool": TOOL, "hits": len(result["hits"]), "ok": not result["hits"],
                      "report": str(out / "anonymity.md"), **result}, indent=2, ensure_ascii=False))
    return 1 if result["hits"] else 0


if __name__ == "__main__":
    sys.exit(main())
