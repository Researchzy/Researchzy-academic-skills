#!/usr/bin/env python3
"""Check that the quotes behind claim verdicts are really in the sources.

The agent reads a cited paper and judges whether it supports the sentence that cites it. This
script does the part that must not rest on the agent's word: every "supported" or "partly
supported" verdict has to carry a quote, and the quote has to be found in the source text. A
verdict whose quote is not in the source is not accepted.

  check_claims.py text paper.pdf [--out paper.txt]   a PDF as text with [[page N]] markers
  check_claims.py check claims.json [--out DIR]      verify the quotes, write claims-checked.json
                                                     and claims.md

claims.json, written by the agent:

  {"claims": [{
     "id": "c1", "ref_id": "he2016", "location": "main.tex:3",
     "sentence": "Residual networks reduced the top-5 error on ImageNet to 3.57%.",
     "verdict": "supported",            supported | partly_supported | not_supported |
                                        cannot_tell | not_checked
     "quote": "3.57% top-5 error on the ImageNet test set",
     "page": 1,
     "source": "sources/he2016.pdf",    a PDF, or a text file (with or without page markers)
     "read": "full_text",               full_text | abstract | none
     "comment": "the paper reports this for an ensemble"}]}

Standard library only; reading a PDF needs PyMuPDF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_match import match_quality, tokens  # noqa: E402

VERDICTS = ("supported", "partly_supported", "not_supported", "cannot_tell", "not_checked")
NEEDS_QUOTE = ("supported", "partly_supported")
PAGE_MARK_RE = re.compile(r"^\[\[page (\d+)\]\]\s*$", re.M)
# A quote of a few words proves little: it matches somewhere in most papers.
MIN_QUOTE_TOKENS = 5
# Below this, a source said to be the full text is an abstract or a failed extraction.
MIN_FULL_TEXT_TOKENS = 400


def pdf_pages(path: Path) -> list[str]:
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            raise SystemExit("Reading a PDF needs PyMuPDF (pip install pymupdf).")
    with fitz.open(path) as doc:
        return [page.get_text() for page in doc]


def source_pages(path: Path) -> list[tuple[int | None, str]]:
    """(page number, text) for each page of a source. A text file without page markers is one
    page whose number is unknown."""
    if path.suffix.lower() == ".pdf":
        return [(i, text) for i, text in enumerate(pdf_pages(path), 1)]
    text = path.read_text(encoding="utf-8", errors="replace")
    marks = list(PAGE_MARK_RE.finditer(text))
    if not marks:
        return [(None, text)]
    return [(int(m.group(1)), text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)])
            for i, m in enumerate(marks)]


def check_claim(claim: dict, base: Path, cache: dict) -> dict:
    out = dict(claim)
    verdict = str(claim.get("verdict") or "").strip().lower()
    quote = str(claim.get("quote") or "").strip()
    out.update({"check": "", "grade": "", "page_found": None, "accepted": False})
    if verdict not in VERDICTS:
        out["check"] = "unknown_verdict"
        return out
    if verdict in ("cannot_tell", "not_checked"):
        out["check"], out["accepted"] = "nothing_to_check", True
        return out
    if not quote:
        out["check"] = "needs_quote" if verdict in NEEDS_QUOTE else "no_quote_given"
        out["accepted"] = verdict not in NEEDS_QUOTE
        return out
    source = str(claim.get("source") or "").strip()
    path = (base / source) if source and not Path(source).is_absolute() else Path(source)
    if not source or not path.is_file():
        out["check"] = "no_source"
        return out
    if path not in cache:
        cache[path] = source_pages(path)
    pages = cache[path]
    whole = "\n".join(text for _, text in pages)
    out["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    out["source_tokens"] = len(tokens(whole))
    if str(claim.get("read") or "") == "full_text" and out["source_tokens"] < MIN_FULL_TEXT_TOKENS:
        out["read"] = "abstract"
        out["read_note"] = "the source is too short to be a full text"
    if len(tokens(quote)) < MIN_QUOTE_TOKENS:
        out["check"] = "quote_too_short"
        return out
    grade = match_quality(quote, whole)["grade"]
    out["grade"] = grade
    if grade in ("EXACT", "INTERLEAVED"):
        out["check"], out["accepted"] = "quote_found", True
        for number, text in pages:
            if number is not None and match_quality(quote, text)["grade"] in ("EXACT", "INTERLEAVED"):
                out["page_found"] = number
                break
    elif grade == "PARTIAL":
        out["check"] = "quote_unresolved"
    else:
        out["check"] = "quote_not_found"
    return out


CHECK_TEXT = {
    "quote_found": "quote found in the source",
    "quote_unresolved": "quote only partly found: look at the source",
    "quote_not_found": "quote is not in the source: verdict not accepted",
    "quote_too_short": "quote too short to prove anything",
    "needs_quote": "no quote given: verdict not accepted",
    "no_source": "source file missing: verdict not accepted",
    "no_quote_given": "no quote given",
    "nothing_to_check": "",
    "unknown_verdict": "verdict is not one of " + ", ".join(VERDICTS),
}


def write_markdown(path: Path, checked: list[dict]) -> None:
    def cell(value) -> str:
        return re.sub(r"\s+", " ", str(value if value is not None else "")).replace("|", "/")

    counts: dict = {}
    for c in checked:
        key = c.get("verdict") if c["accepted"] else "not accepted"
        counts[key] = counts.get(key, 0) + 1
    lines = ["# Claim check", "", "| Result | Citations |", "|---|---|"]
    lines += [f"| {str(k).replace('_', ' ')} | {v} |" for k, v in counts.items()]
    lines += ["", "A verdict of supported or partly supported is accepted only when its quote was found in "
              "the source. Verdicts from an abstract are marked.", "",
              "| Where | Reference | Sentence | Verdict | Quote from the source | Page | Check |",
              "|---|---|---|---|---|---|---|"]
    for c in checked:
        verdict = str(c.get("verdict", "")).replace("_", " ")
        if c.get("read") == "abstract" and c.get("verdict") in NEEDS_QUOTE + ("not_supported",):
            verdict += " (abstract only)"
        page = c.get("page_found") or c.get("page") or ""
        if c.get("page_found") and c.get("page") and str(c["page"]) != str(c["page_found"]):
            page = f"{c['page_found']} (given as {c['page']})"
        lines.append("| " + " | ".join(cell(v) for v in (
            c.get("location"), f"`{c.get('ref_id', '')}`", c.get("sentence"), verdict,
            c.get("quote"), page, CHECK_TEXT.get(c["check"], c["check"]))) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the quotes behind claim verdicts.")
    sub = parser.add_subparsers(dest="command", required=True)
    text = sub.add_parser("text", help="Write a PDF's text with [[page N]] markers")
    text.add_argument("pdf")
    text.add_argument("--out", help="Output file (default: the PDF's name with .txt)")
    check = sub.add_parser("check", help="Verify the quotes in claims.json")
    check.add_argument("claims")
    check.add_argument("--out", help="Output folder (default: the folder of claims.json)")
    check.add_argument("--strict", action="store_true", help="Exit 1 when a verdict is not accepted")
    args = parser.parse_args()

    if args.command == "text":
        pdf = Path(args.pdf)
        pages = pdf_pages(pdf)
        out = Path(args.out) if args.out else pdf.with_suffix(".txt")
        out.write_text("".join(f"[[page {i}]]\n{page}\n" for i, page in enumerate(pages, 1)), encoding="utf-8")
        words = sum(len(tokens(page)) for page in pages)
        print(json.dumps({"text": str(out), "pages": len(pages), "words": words,
                          "looks_complete": words >= MIN_FULL_TEXT_TOKENS}, indent=2))
        return 0

    claims_path = Path(args.claims).resolve()
    data = json.loads(claims_path.read_text(encoding="utf-8"))
    claims = data.get("claims", []) if isinstance(data, dict) else data
    out_dir = Path(args.out).resolve() if args.out else claims_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    checked = [check_claim(c, claims_path.parent, cache) for c in claims if isinstance(c, dict)]
    (out_dir / "claims-checked.json").write_text(
        json.dumps({"tool": "researchzy-reference-check", "claims": checked}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    write_markdown(out_dir / "claims.md", checked)
    rejected = [c for c in checked if not c["accepted"]]
    print(json.dumps({
        "claims": len(checked), "accepted": len(checked) - len(rejected),
        "not_accepted": [{"id": c.get("id"), "ref_id": c.get("ref_id"), "check": c["check"]} for c in rejected],
        "report": str(out_dir / "claims.md"),
    }, indent=2))
    return 1 if args.strict and rejected else 0


if __name__ == "__main__":
    sys.exit(main())
