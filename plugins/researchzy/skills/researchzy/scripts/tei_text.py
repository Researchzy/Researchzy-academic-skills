#!/usr/bin/env python3
"""Turn GROBID's TEI XML of a paper (grobidTeiXml from get_paper_files) into files an agent can read and cite.

  tei_text.py paper.tei.xml --out DIR

writes

  DIR/paper.md          title, authors with affiliations, keywords, abstract, the body section by section,
                        figure and table captions, footnotes and back matter (acknowledgements, funding,
                        availability), with a [[page N]] marker wherever the text moves to a new PDF page and
                        every in-text citation linked to its reference, as in "shown before [12](#b12)"
  DIR/references.json   the parsed reference list: id (the b12 of the links), title, authors, year, venue,
                        volume, pages, doi, arxiv, pmid, pmcid, its PDF page, and how often the text cites it

and prints a one-line summary. GROBID parses the PDF; it does not read it. Reference fields can be wrong or
missing, and tables and formulas lose their layout: check a reference against search_papers before relying on
it, and read a table or formula that matters in the PDF itself. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
SPACE_RE = re.compile(r"\s+")
CITATION_RE = re.compile(r"^([\[(]*)(.*?)([\]),;]*)$", re.S)
CAPTION_LABEL_RE = re.compile(r"^\s*(figure|fig\.|table)\s*[\w.-]*\s*[:.]\s*", re.I)
BACK_TITLES = {"acknowledgement": "Acknowledgements", "availability": "Availability", "annex": "Annex",
               "funding": "Funding", "contribution": "Author contributions"}
IDNO_FIELDS = {"doi": "doi", "arxiv": "arxiv", "pmid": "pmid", "pmcid": "pmcid"}
# Below this, the TEI holds an abstract or a failed extraction, not a full text.
MIN_FULL_TEXT_WORDS = 400


def local(element: ET.Element) -> str:
    return element.tag[len(TEI):] if isinstance(element.tag, str) and element.tag.startswith(TEI) else ""


def clean(text: str) -> str:
    return SPACE_RE.sub(" ", text).strip()


def plain(element: ET.Element | None) -> str:
    return "" if element is None else clean("".join(element.itertext()))


def page_of(element: ET.Element) -> int | None:
    """The PDF page of an element's first coordinates (coords="page,x,y,w,h;…"), its own or a descendant's."""
    for node in element.iter():
        first = (node.get("coords") or "").split(";", 1)[0].split(",", 1)[0].strip()
        if first.isdigit():
            return int(first)
    return None


class Paper:
    def __init__(self, root: ET.Element):
        self.root = root
        self.cited: dict[str, int] = {}
        self.citations = 0
        self.unlinked = 0
        self.lines: list[str] = []
        self.page: int | None = None
        self.pages_seen: set[int] = set()

    # Text with every bibliographic reference linked to its entry in the reference list.
    def inline(self, element: ET.Element) -> str:
        parts = [element.text or ""]
        for child in element:
            name = local(child)
            if name == "ref" and child.get("type") == "bibr":
                parts.append(self.citation(child))
            elif name == "note" and child.get("place") == "foot":
                pass  # footnotes are listed after the body
            elif name in ("lb", "pb"):
                parts.append(" ")
            else:
                parts.append(self.inline(child))
            parts.append(child.tail or "")
        return "".join(parts)

    def citation(self, ref: ET.Element) -> str:
        text = plain(ref)
        self.citations += 1
        targets = [target[1:] for target in (ref.get("target") or "").split() if target.startswith("#")]
        if not targets:
            self.unlinked += 1
            return text
        for target in targets:
            self.cited[target] = self.cited.get(target, 0) + 1
        # Printed brackets and separators stay outside the link: "[35, 2]" becomes "[[35](#b34), [2](#b1)]".
        match = CITATION_RE.match(text)
        before, label, after = match.groups() if match and match.group(2) else ("", text, "")
        return f"{before}[{label}](#{targets[0]}){after}"

    def emit(self, page: int | None, text: str) -> None:
        if not text:
            return
        if page is not None and page != self.page:
            self.lines.append(f"[[page {page}]]")
            self.page = page
            self.pages_seen.add(page)
        self.lines.append(text)

    def blocks(self, parent: ET.Element, level: int = 2) -> None:
        for child in parent:
            name = local(child)
            if name == "head":
                number = (child.get("n") or "").strip().rstrip(".")
                depth = level + number.count(".") if number else level  # 3.2.1 is a level below 3.2
                self.emit(page_of(child), "#" * min(depth, 6) + " " + (f"{number} " if number else "")
                          + clean(self.inline(child)))
            elif name == "div":
                self.blocks(child, level + 1 if child.find(TEI + "head") is not None
                            and parent.find(TEI + "head") is not None else level)
            elif name == "p":
                self.emit(page_of(child), clean(self.inline(child)))
            elif name == "formula":
                label, body = plain(child.find(TEI + "label")), plain(child)
                if label and body.endswith(label):
                    body = body[:-len(label)].rstrip()
                self.emit(page_of(child), f"$$ {body} $$" + (f" {label}" if label else ""))
            elif name == "list":
                self.emit(page_of(child), "\n".join("- " + clean(self.inline(item)) for item in child.findall(TEI + "item")))

    def header(self) -> None:
        title = plain(self.root.find(f"{TEI}teiHeader/{TEI}fileDesc/{TEI}titleStmt/{TEI}title"))
        self.lines.append(f"# {title or 'Untitled'}")
        authors = []
        for author in self.root.findall(f"{TEI}teiHeader/{TEI}fileDesc/{TEI}sourceDesc//{TEI}analytic/{TEI}author"):
            name = person(author.find(TEI + "persName"))
            if not name:
                continue
            places = [", ".join(plain(org) for org in affiliation.findall(TEI + "orgName"))
                      for affiliation in author.findall(TEI + "affiliation")]
            places = [place for place in places if place]
            authors.append(f"- {name}" + (f" ({'; '.join(places)})" if places else ""))
        if authors:
            self.lines.append("Authors, as parsed from the PDF (get_paper has the index's list):\n" + "\n".join(authors))
        keywords = [plain(term) for term in self.root.iter(TEI + "term")]
        if any(keywords):
            self.lines.append("Keywords: " + "; ".join(term for term in keywords if term))
        abstract = self.root.find(f"{TEI}teiHeader/{TEI}profileDesc/{TEI}abstract")
        if abstract is not None and plain(abstract):
            self.emit(page_of(abstract), "## Abstract")
            self.blocks(abstract, 3)

    def figures(self, body: ET.Element) -> None:
        figures = list(body.iter(TEI + "figure"))
        if figures:
            self.lines.append("## Figures and tables")
        for figure in figures:
            kind = "Table" if figure.get("type") == "table" else "Figure"
            label = plain(figure.find(TEI + "label"))
            caption = CAPTION_LABEL_RE.sub("", plain(figure.find(TEI + "figDesc")))
            self.emit(page_of(figure), f"**{kind} {label}.** {caption}".replace(" .**", ".**"))
            rows = ["| " + " | ".join(cells) + " |" for cells in
                    ([clean(self.inline(cell)) for cell in row.findall(TEI + "cell")] for row in figure.iter(TEI + "row"))
                    if any(cells)]
            if rows:
                self.lines.append("\n".join(rows[:1] + ["|---|"] + rows[1:]))

    def footnotes(self, body: ET.Element) -> None:
        notes = [note for note in body.iter(TEI + "note") if note.get("place") == "foot"]
        if notes:
            self.lines.append("## Footnotes")
        for note in notes:
            number = note.get("n")
            self.emit(page_of(note), (f"[{number}] " if number else "") + clean(self.inline(note)))

    def back(self, back: ET.Element) -> None:
        for div in back.findall(TEI + "div"):
            kind = div.get("type") or ""
            if kind == "references":
                continue
            if not any(child.find(TEI + "head") is not None for child in div) and div.find(TEI + "head") is None:
                self.emit(page_of(div), "## " + BACK_TITLES.get(kind, kind.title() or "Back matter"))
            self.blocks(div, 2)
        # The header names each funder and points to the grants, which GROBID lists in the back matter.
        grants = {org.get(XML_ID): [plain(idno) for idno in org.findall(TEI + "idno")] for org in back.iter(TEI + "org")}
        funders = []
        for funder in self.root.iter(TEI + "funder"):
            names = [plain(name) for name in funder.findall(TEI + "orgName")]
            numbers = [number.lstrip("&, ") for ref in (funder.get("ref") or "").split()
                       for number in grants.get(ref.lstrip("#"), [])]
            if any(names):
                funders.append(names[0] + (f" ({', '.join(names[1:])})" if len(names) > 1 else "")
                               + (f": {', '.join(n for n in numbers if n)}" if any(numbers) else ""))
        if funders:
            self.lines += ["## Funders", "\n".join(f"- {funder}" for funder in funders)]

    def markdown(self) -> str:
        self.header()
        text = self.root.find(f"{TEI}text")
        body = text.find(TEI + "body") if text is not None else None
        if body is not None:
            self.blocks(body)
            self.figures(body)
            self.footnotes(body)
        back = text.find(TEI + "back") if text is not None else None
        if back is not None:
            self.back(back)
        return "\n\n".join(self.lines) + "\n"

    def references(self) -> list[dict]:
        out = []
        for bibl in self.root.iter(TEI + "biblStruct"):
            ident = bibl.get(XML_ID)
            if not ident or not ident.startswith("b"):
                continue  # the paper's own record in the header has no reference id
            analytic, monogr = bibl.find(TEI + "analytic"), bibl.find(TEI + "monogr")
            article = plain(analytic.find(TEI + "title")) if analytic is not None else ""
            book = plain(monogr.find(TEI + "title")) if monogr is not None else ""
            entry: dict = {"id": ident, "title": article or book or None}
            if article and book:
                entry["venue"] = book
            people = analytic if analytic is not None and analytic.find(TEI + "author") is not None else monogr
            entry["authors"] = [name for name in (person(author.find(TEI + "persName"))
                                                  for author in (people.findall(TEI + "author") if people is not None
                                                                 else [])) if name]
            imprint = monogr.find(TEI + "imprint") if monogr is not None else None
            if imprint is not None:
                date = imprint.find(TEI + "date")
                year = (date.get("when") or plain(date))[:4] if date is not None else ""
                if year.isdigit():
                    entry["year"] = int(year)
                for scope in imprint.findall(TEI + "biblScope"):
                    unit = scope.get("unit")
                    value = plain(scope) or "-".join(filter(None, [scope.get("from"), scope.get("to")]))
                    if unit in ("volume", "issue") and value:
                        entry[unit] = value
                    elif unit == "page" and value:
                        entry["pages"] = value
            for idno in bibl.iter(TEI + "idno"):
                field = IDNO_FIELDS.get((idno.get("type") or "").lower())
                if field and plain(idno):
                    entry.setdefault(field, plain(idno))
            raw = next((plain(note) for note in bibl.findall(TEI + "note") if note.get("type") == "raw_reference"), "")
            if raw:
                entry["raw"] = raw
            entry["page"] = page_of(bibl)
            entry["citedInText"] = self.cited.get(ident, 0)
            out.append(entry)
        return out


def person(name: ET.Element | None) -> str:
    if name is None:
        return ""
    parts = [plain(part) for part in name if local(part) in ("forename", "surname")]
    return " ".join(part for part in parts if part) or plain(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tei", type=Path, help="GROBID TEI XML, as downloaded from grobidTeiXml")
    parser.add_argument("--out", type=Path, required=True, help="directory for paper.md and references.json")
    args = parser.parse_args(argv)
    try:
        root = ET.parse(args.tei).getroot()
    except (ET.ParseError, OSError) as error:
        print(f"{args.tei}: not a readable TEI XML file ({error})", file=sys.stderr)
        return 2
    if local(root) != "TEI":
        print(f"{args.tei}: the root element is not TEI", file=sys.stderr)
        return 2
    paper = Paper(root)
    markdown = paper.markdown()
    references = paper.references()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "paper.md").write_text(markdown, encoding="utf-8")
    (args.out / "references.json").write_text(
        json.dumps({"source": args.tei.name, "references": references}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    words = len(re.findall(r"\w+", markdown))
    pages = len(root.findall(f"{TEI}facsimile/{TEI}surface")) or len(paper.pages_seen)
    print(f"{args.out / 'paper.md'}: {words} words, {pages} pages, {len(references)} references, "
          f"{paper.citations - paper.unlinked} of {paper.citations} in-text citations linked to a reference")
    if words < MIN_FULL_TEXT_WORDS:
        print(f"Under {MIN_FULL_TEXT_WORDS} words: this is not a full text; read the PDF.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
