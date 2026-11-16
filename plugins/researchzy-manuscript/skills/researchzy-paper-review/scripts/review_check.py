#!/usr/bin/env python3
"""Hold a paper review to its contract, then write the report.

The agent reads the manuscript and judges it. This script checks the part that must not rest on
the agent's word: every finding has its fields and legal values, every quoted passage is in the
manuscript, a finding about something missing says where it was looked for, every serious finding
was checked against the manuscript a second time, and no verdict says "ready" beside a blocking
finding that stands.

  review_check.py check paper-review/findings.json --manuscript main.tex [FILE…] [--referee]
      writes review.md; with --referee also referee-report.md and to-editor.md
  review_check.py recheck paper-review/round-2/findings.json --manuscript revised.tex [FILE…]
      second round: is each quoted passage still in the revised manuscript; writes recheck.md

Both take --out DIR (default: the folder of findings.json) and print a JSON summary. Exit code 0:
the contract holds. 1: it does not; the summary lists the errors and check writes no report.
2: an input could not be read. Manuscript files: .tex, .md, .txt, .docx, .pdf.

findings.json, written by the agent:

  {"title": "…", "target": "…",            the manuscript's title; the venue aimed at, or "not stated"
   "summary": "…",                         the question, the design and the main claims; no judgement
   "strengths": ["…"],                     optional
   "coverage": [{"item": "manuscript",     manuscript, supplement, data and code are required items
                 "status": "read",         read | partly_read | not_read | not_provided
                 "note": "main.tex"}],     required for partly_read and not_read
   "claims": [{"id": "C1", "claim": "…",   optional: the load-bearing claims
               "location": "Abstract",
               "type": "causal",           causal | generalisation | improvement | priority | formal | descriptive
               "evidence": "Table 2",      where the manuscript supports it
               "support": "limited",       supported | limited | unsupported | contradicted | not_assessable
               "mismatch": ["scope"],      direction | magnitude | population | outcome | timepoint |
               "note": "…"}],              causal_language | scope
   "checks": {                             each status: done | skipped; skipped needs "note"
     "novelty": {"status": "done", "searches": [{"query": "…", "total": 41}],
                 "closest_works": [{"corpusId": 1, "title": "…", "year": 2024, "cited": false,
                                    "differs": "…"}]},
     "references": {"status": "skipped", "note": "…"},
     "statistics": {"status": "done", "note": "…"}},
   "findings": [{"id": "F1",
                 "severity": "major",              critical | major | minor
                 "evidence_status": "confirmed",   confirmed | reporting_gap | unresolved
                 "blocking": true,                 true | false; a critical finding is always blocking
                 "fixability": "existing_data",    existing_data | new_work | not_fixable_now
                 "location": "Section 4.2, Table 3",
                 "quote": "…",                     verbatim from the manuscript, five words or more
                 "where_looked": "…",              instead of a quote, for something missing from the paper
                 "observation": "…", "basis": "…", "why_it_matters": "…", "fix": "…", "closure_test": "…",
                 "claims": ["C1"],                 optional: the claims it bears on
                 "verification": {                 required for critical and major
                   "outcome": "confirmed",         confirmed | refuted | downgraded
                   "note": "…"},                   what was reread and what it showed
                 "recheck": {                      second round only
                   "status": "resolved",           resolved | partial | open | regressed
                   "quote": "…", "note": "…"}}],   quote: verbatim from the revised manuscript
   "verdicts": {                                   each verdict: hold | revise | ready | not_assessable
     "scientific": {"verdict": "revise", "reason": "…"},
     "submission": {"verdict": "hold", "reason": "…"}},
   "referee": {"venue": "…", "ai_use_confirmed": true,       with --referee only
               "recommendation": "…", "to_editor": "…"}}

Standard library only; a PDF manuscript needs PyMuPDF.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_match import match_quality, normalize, tokens  # noqa: E402

SEVERITIES = ("critical", "major", "minor")
EVIDENCE = ("confirmed", "reporting_gap", "unresolved")
FIXABILITY = ("existing_data", "new_work", "not_fixable_now")
OUTCOMES = ("confirmed", "refuted", "downgraded")
VERDICTS = ("hold", "revise", "ready", "not_assessable")
RECHECK = ("resolved", "partial", "open", "regressed")
COVERAGE = ("read", "partly_read", "not_read", "not_provided")
COVERAGE_ITEMS = ("manuscript", "supplement", "data", "code")
CLAIM_TYPES = ("causal", "generalisation", "improvement", "priority", "formal", "descriptive")
SUPPORT = ("supported", "limited", "unsupported", "contradicted", "not_assessable")
MISMATCH = ("direction", "magnitude", "population", "outcome", "timepoint", "causal_language", "scope")
CHECKS = ("novelty", "references", "statistics")
FINDING_TEXT = ("location", "observation", "basis", "why_it_matters", "fix", "closure_test")
# A quote of a few words proves little: it matches somewhere in most manuscripts.
MIN_QUOTE_TOKENS = 5
# The same floor for a script the word tokens of quote_match do not cover (Chinese, Cyrillic, Arabic…).
MIN_QUOTE_CHARS = 12

PLACEHOLDER_RE = re.compile(r"\b(?:TODO|TBD|FIXME|XXX+)\b|\{\{.*?\}\}|(?i:lorem ipsum)"
                            r"|(?i:\[(?:insert|placeholder|fill in|to be (?:added|filled|written))[^\]]*\])")
# A recommendation, which a referee gives to the editor and not to the authors.
DECISION_RE = re.compile(
    r"\brecommend(?:s|ed|ing)?\s+(?:acceptance|rejection|publication|accepting|rejecting|publishing)\b"
    r"|\b(?:paper|manuscript|submission|article|work)\s+(?:should|must|can|cannot|should\s+not)\s+be\s+"
    r"(?:accepted|rejected|published)\b"
    r"|\b(?:accept|reject)\s+(?:this|the)\s+(?:paper|manuscript|submission|article)\b"
    r"|\b(?:major|minor)\s+revisions?\b|\bsuitable\s+for\s+publication\b", re.I)
QUOTE_PROBLEM = {
    "partly": ("quote_partly_found", "most of its words are in the manuscript but not all. Copy the passage again "
                                     "from the file given to --manuscript."),
    "absent": ("quote_not_found", "it is not in the manuscript. Reread the passage: correct the quote, or withdraw "
                                  "the finding."),
    "too_short": ("quote_too_short", "quote the whole sentence or table row: at least five words."),
}
PASSAGE = {"found": "unchanged", "partly": "changed", "absent": "gone", "too_short": "unknown"}
RECHECK_PROBLEM = {
    "unknown_status": "recheck.status must be one of: " + ", ".join(RECHECK) + ".",
    "new_quote_not_found": "recheck.quote is not in the manuscript given. Copy it again from the revised file.",
    "resolved_not_shown": "marked resolved, but the quoted passage is unchanged and no new text is quoted. Put the "
                          "passage that closes it in recheck.quote, or use another status.",
}
FIX_TEXT = {"existing_data": "fixable with what the authors have", "new_work": "needs new work",
            "not_fixable_now": "not fixable in this paper"}
KIND = {"confirmed": "Concern", "reporting_gap": "Missing information", "unresolved": "Question"}


def fail(message: str):
    print(message, file=sys.stderr)
    sys.exit(2)


def read_manuscript(path: Path) -> str:
    if not path.is_file():
        fail(f"No such manuscript file: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import pymupdf as fitz
        except ImportError:
            try:
                import fitz
            except ImportError:
                fail("Reading a PDF needs PyMuPDF (pip install pymupdf). Or give the source files or a text export.")
        with fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                parts = [archive.read(name).decode("utf-8", "replace") for name in archive.namelist()
                         if re.fullmatch(r"word/(?:document|footnotes|endnotes)\.xml", name)]
        except (zipfile.BadZipFile, OSError):
            fail(f"{path} is not a readable .docx file.")
        xml = re.sub(r"<w:delText[^>]*>.*?</w:delText>", "", "\n".join(parts), flags=re.S)  # tracked deletions
        xml = re.sub(r"</w:p>|<w:br[^>]*>|<w:tab[^>]*>", "\n", xml)
        return html.unescape(re.sub(r"<[^>]+>", "", xml))
    return path.read_text(encoding="utf-8", errors="replace")


def squeeze(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text))


def load_texts(paths: list[str]) -> list[tuple[str, str]]:
    """(text, text without whitespace) for each manuscript file."""
    texts = [(text, squeeze(text)) for text in (read_manuscript(Path(path)) for path in paths)]
    if not any(bare for _, bare in texts):
        fail("No text could be read from the manuscript files. A scanned PDF has none: give the source files.")
    return texts


def locate(quote: str, texts: list[tuple[str, str]]) -> str:
    """Is the quote in the manuscript: found, partly (most of its words, in order), absent or too_short."""
    bare = squeeze(quote)
    letters = [ch for ch in bare if ch.isalnum()]
    if sum(not ch.isascii() for ch in letters) >= max(MIN_QUOTE_CHARS, len(letters) / 2):
        # Mostly a script without word tokens: match the characters, whatever the line breaks.
        return "found" if any(bare in whole for _, whole in texts) else "absent"
    if len(tokens(quote)) < MIN_QUOTE_TOKENS:
        return "too_short"
    grades = {match_quality(quote, text)["grade"] for text, _ in texts}
    return "found" if grades & {"EXACT", "INTERLEAVED"} else "partly" if "PARTIAL" in grades else "absent"


def text_of(obj, key: str) -> str:
    value = obj.get(key) if isinstance(obj, dict) else None
    return value.strip() if isinstance(value, str) else ""


def part(obj, key: str) -> dict:
    value = obj.get(key) if isinstance(obj, dict) else None
    return value if isinstance(value, dict) else {}


def rows(obj, key: str) -> list[dict]:
    value = obj.get(key) if isinstance(obj, dict) else None
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def names(value) -> list:
    return [value] if isinstance(value, str) else value if isinstance(value, list) else []


def strings(node, path: str = ""):
    """Every string in the file with its path, except quotes, which are the manuscript's own words."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key != "quote":
                yield from strings(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node, 1):
            label = value.get("id") if isinstance(value, dict) and isinstance(value.get("id"), str) else i
            yield from strings(value, f"{path}[{label}]")
    elif isinstance(node, str):
        yield path, node


def is_placeholder(text: str) -> bool:
    text = text.strip()
    return bool(text) and (not re.search(r"\w", text) or bool(re.fullmatch(r"<[^<>]*>", text))
                           or bool(PLACEHOLDER_RE.search(text)))


def recheck_finding(finding: dict, texts) -> dict:
    """Where a finding stands against a revised manuscript. "resolved" has to show in the text: the
    quoted passage changed or went, or recheck.quote, the new wording, is found."""
    recheck = part(finding, "recheck")
    quote, new = text_of(finding, "quote"), text_of(recheck, "quote")
    passage = PASSAGE[locate(quote, texts)] if quote else "no_quote"
    shown = ("found" if locate(new, texts) == "found" else "not_found") if new else "none"
    status, problem = recheck.get("status") if recheck else "not_rechecked", ""
    if status != "not_rechecked" and status not in RECHECK:
        problem = "unknown_status"
    elif shown == "not_found":
        problem = "new_quote_not_found"
    elif status == "resolved" and passage not in ("changed", "gone") and shown != "found":
        problem = "resolved_not_shown"
    return {"id": finding.get("id"), "severity": finding.get("severity"), "location": text_of(finding, "location"),
            "passage": passage, "status": status, "new_quote": shown, "problem": problem}


def check(data: dict, texts, referee: bool) -> tuple[list[dict], dict]:
    """The errors, and what the report is written from."""
    errors: list[dict] = []

    def err(where: str, problem: str, message: str) -> None:
        errors.append({"where": where, "problem": problem, "message": message})

    def need(obj: dict, key: str, where: str) -> str:
        if not text_of(obj, key):
            err(f"{where}.{key}", "missing_field", f"{where} needs {key}.")
        return text_of(obj, key)

    def choice(obj: dict, key: str, allowed: tuple, where: str):
        value = obj.get(key)
        if isinstance(value, str) and value in allowed:
            return value
        err(f"{where}.{key}", "missing_field" if value in (None, "") else "unknown_value",
            f"{where}.{key} must be one of: {', '.join(allowed)}.")
        return None

    for path, value in strings(data):
        if is_placeholder(value):
            err(path, "placeholder", f"{path} still holds a placeholder: {value.strip()[:40]!r}.")
    need(data, "summary", "review")

    coverage: dict = {}
    for i, row in enumerate(rows(data, "coverage"), 1):
        item = need(row, "item", f"coverage[{i}]")
        where = f"coverage[{item or i}]"
        coverage[item] = choice(row, "status", COVERAGE, where)
        if coverage[item] in ("partly_read", "not_read") and not text_of(row, "note"):
            err(f"{where}.note", "missing_field", f"{where}: say in note what was not read, and why.")
    for item in COVERAGE_ITEMS:
        if item not in coverage:
            err(f"coverage[{item}]", "missing_field", f"coverage needs an entry for {item}, also when it was not provided.")

    support: dict = {}
    for i, claim in enumerate(rows(data, "claims"), 1):
        cid = need(claim, "id", f"claims[{i}]")
        where = f"claims[{cid or i}]"
        if cid and cid in support:
            err(where, "duplicate_id", f"Two claims have the id {cid}.")
        need(claim, "claim", where)
        need(claim, "location", where)
        choice(claim, "type", CLAIM_TYPES, where)
        support[cid] = choice(claim, "support", SUPPORT, where)
        for kind in names(claim.get("mismatch")):
            if kind not in MISMATCH:
                err(f"{where}.mismatch", "unknown_value", f"{where}.mismatch takes: {', '.join(MISMATCH)}.")

    checks = part(data, "checks")
    for name in CHECKS:
        status = choice(part(checks, name), "status", ("done", "skipped"), f"checks.{name}")
        if status == "skipped" and not text_of(part(checks, name), "note"):
            err(f"checks.{name}.note", "missing_field", f"checks.{name}: say in note why it was skipped.")
    novelty = part(checks, "novelty")
    if novelty.get("status") == "done" and not rows(novelty, "searches"):
        err("checks.novelty.searches", "missing_field", "A novelty check that was done lists its searches.")
    for i, search in enumerate(rows(novelty, "searches"), 1):
        need(search, "query", f"checks.novelty.searches[{i}]")
        if type(search.get("total")) is not int:
            err(f"checks.novelty.searches[{i}].total", "missing_field",
                "total is the number of results the tool reported for the query.")
    for i, work in enumerate(rows(novelty, "closest_works"), 1):
        where = f"checks.novelty.closest_works[{i}]"
        if novelty.get("status") != "done" or work.get("corpusId") in (None, ""):
            err(where, "work_not_retrieved", f"{where}: a work is named only when a search of this session returned "
                                             "it: status done, and the corpusId the tool gave.")
        need(work, "title", where)
        need(work, "differs", where)
        if not isinstance(work.get("cited"), bool):
            err(f"{where}.cited", "missing_field", f"{where}.cited is true or false: is the work in the reference list.")

    seen: set = set()
    standing, withdrawn, resolved = [], [], []
    for i, finding in enumerate(rows(data, "findings"), 1):
        fid = need(finding, "id", f"findings[{i}]")
        where = f"findings[{fid or i}]"
        if fid and fid in seen:
            err(where, "duplicate_id", f"Two findings have the id {fid}. An id is never reused.")
        seen.add(fid)
        verification = part(finding, "verification")
        if verification.get("outcome") == "refuted":
            withdrawn.append(finding)
            continue
        if "recheck" in finding:
            state = recheck_finding(finding, texts)
            if state["problem"]:
                err(f"{where}.recheck", state["problem"], f"{where}: {RECHECK_PROBLEM[state['problem']]}")
            if state["status"] == "resolved":
                if not state["problem"]:
                    resolved.append(finding)
                continue
        severity = choice(finding, "severity", SEVERITIES, where)
        choice(finding, "evidence_status", EVIDENCE, where)
        choice(finding, "fixability", FIXABILITY, where)
        if not isinstance(finding.get("blocking"), bool):
            err(f"{where}.blocking", "missing_field", f"{where}.blocking must be true or false.")
        elif severity == "critical" and not finding["blocking"]:
            err(f"{where}.blocking", "critical_not_blocking",
                f"{where}: a critical finding is blocking. Set blocking to true, or lower the severity.")
        for key in FINDING_TEXT:
            need(finding, key, where)
        quote = text_of(finding, "quote")
        if quote:
            state = locate(quote, texts)
            if state != "found":
                err(f"{where}.quote", QUOTE_PROBLEM[state][0], f"{where}.quote: {QUOTE_PROBLEM[state][1]}")
        elif not text_of(finding, "where_looked"):
            err(f"{where}.where_looked", "needs_where_looked",
                f"{where} has no quote. Quote the passage; for something missing from the paper, say in "
                "where_looked which parts were searched for it.")
        if severity in ("critical", "major") and (verification.get("outcome") not in OUTCOMES
                                                  or not text_of(verification, "note")):
            err(f"{where}.verification", "needs_verification",
                f"{where}: a {severity} finding is checked against the manuscript again. Give verification.outcome "
                f"({', '.join(OUTCOMES)}) and verification.note.")
        elif verification and verification.get("outcome") not in OUTCOMES:
            err(f"{where}.verification", "unknown_value", f"{where}.verification.outcome must be one of: "
                                                          f"{', '.join(OUTCOMES)}.")
        for cid in names(finding.get("claims")):
            if not isinstance(cid, str) or cid not in support:
                err(f"{where}.claims", "unknown_claim", f"{where} names the claim {cid}, which is not in claims.")
        standing.append(finding)

    verdicts = {name: choice(part(part(data, "verdicts"), name), "verdict", VERDICTS, f"verdicts.{name}")
                for name in ("scientific", "submission")}
    for name in verdicts:
        need(part(part(data, "verdicts"), name), "reason", f"verdicts.{name}")
    blocking = [f.get("id") for f in standing if f.get("blocking") is True]
    # A blocking gap in reporting holds back the submission; whether it also holds back the science is a judgement.
    shown = [f.get("id") for f in standing if f.get("blocking") is True and f.get("evidence_status") != "reporting_gap"]
    failed = [cid for cid, level in support.items() if level in ("unsupported", "contradicted")]
    against = {"scientific": [], "submission": []}
    if coverage.get("manuscript") != "read":
        against["scientific"].append("the manuscript was not read in full")
        against["submission"].append("the manuscript was not read in full")
    if shown:
        against["scientific"].append("a confirmed or unresolved blocking finding stands: " + ", ".join(map(str, shown)))
    if failed:
        against["scientific"].append("a claim is rated unsupported or contradicted: " + ", ".join(map(str, failed)))
    if blocking:
        against["submission"].append("a blocking finding stands: " + ", ".join(map(str, blocking)))
    for name, reasons in against.items():
        if verdicts[name] == "ready" and reasons:
            err(f"verdicts.{name}", "ready_refused", f"The {name} verdict cannot be ready while " + "; ".join(reasons) + ".")

    if referee:
        ref = part(data, "referee")
        if ref.get("ai_use_confirmed") is not True:
            err("referee.ai_use_confirmed", "ai_use_not_confirmed",
                "Set it to true only after the user confirmed that the venue allows AI assistance with a review. "
                "Until then the manuscript is not read.")
        need(ref, "venue", "referee")
        need(ref, "recommendation", "referee")
        to_authors = {"summary": data.get("summary"), "strengths": data.get("strengths"),
                      "findings": [{k: f.get(k) for k in ("id", *FINDING_TEXT)} for f in standing],
                      "closest_works": [w.get("differs") for w in rows(novelty, "closest_works")]}
        for path, value in strings(to_authors):
            found = DECISION_RE.search(value)
            if found:
                err(path, "decision_in_author_comments", f"{path} gives the authors a recommendation "
                    f"({found.group(0)!r}). It belongs in referee.recommendation only.")

    standing.sort(key=lambda f: SEVERITIES.index(f["severity"]) if f.get("severity") in SEVERITIES else 9)
    return errors, {"standing": standing, "withdrawn": withdrawn, "resolved": resolved, "verdicts": verdicts,
                    "blocking": blocking, "not_checked": [n for n in CHECKS if part(checks, n).get("status") != "done"]}


# ---------------------------------------------------------------------------------------------
# Reports


def flat(value) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def cell(value) -> str:
    return flat(value).replace("|", "/")


def table(header: list[str], body: list[list]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in body), ""]


def counts(findings: list[dict]) -> str:
    return ", ".join(f"{sum(1 for f in findings if f.get('severity') == s)} {s}" for s in SEVERITIES)


def finding_lines(finding: dict, to_authors: bool = False) -> list[str]:
    get = lambda key: flat(finding.get(key))  # noqa: E731
    if to_authors:
        lines = [f"**{get('id')}. {get('location')}** ({KIND[finding['evidence_status']]})", ""]
    else:
        lines = [f"#### {get('id')}. {get('location')}", "",
                 f"{finding['severity']} · {finding['evidence_status'].replace('_', ' ')} · "
                 f"{'blocking' if finding['blocking'] else 'not blocking'} · {FIX_TEXT[finding['fixability']]}", ""]
    lines += [f"> {get('quote')}", ""] if get("quote") else [f"Not found in: {get('where_looked')}", ""]
    labels = [("Observation", "observation"), ("Basis", "basis"), ("Why it matters", "why_it_matters"),
              ("Requested change" if to_authors else "Minimal fix", "fix"),
              ("Addressed when" if to_authors else "Closed when", "closure_test")]
    lines += [f"- **{label}.** {get(key)}" for label, key in labels]
    if not to_authors:
        verification, recheck = part(finding, "verification"), part(finding, "recheck")
        if verification:
            lines.append(f"- **Verification.** {flat(verification.get('outcome'))}: {flat(verification.get('note'))}")
        if names(finding.get("claims")):
            lines.append("- **Bears on.** " + ", ".join(map(str, names(finding.get("claims")))))
        if recheck:
            lines.append(f"- **Second round.** {flat(recheck.get('status'))}. {flat(recheck.get('note'))}".rstrip())
    return lines + [""]


def novelty_lines(data: dict, to_authors: bool = False) -> list[str]:
    novelty = part(part(data, "checks"), "novelty")
    works = [w for w in rows(novelty, "closest_works") if not (to_authors and w.get("cited"))]
    if to_authors:
        return (["## Related work to consider", "", "Records returned by a literature search, not in the reference list.",
                 "", *(f"- {flat(w.get('title'))} ({flat(w.get('year')) or 'n.d.'}): {flat(w.get('differs'))}"
                       for w in works), ""] if works else [])
    lines = ["## Novelty and missing citations", ""]
    if novelty.get("status") != "done":
        return lines + [f"Not checked: {flat(novelty.get('note')).rstrip('.')}. No judgement of novelty is made and "
                        "no prior work is named.", ""]
    lines += table(["Query", "Results reported"], [[f"`{flat(s.get('query'))}`", s.get("total")]
                                                   for s in rows(novelty, "searches")])
    if not works:
        return lines + ["These searches returned no work close enough to compare. That is a statement about the "
                        "searches, not about the literature.", ""]
    return lines + table(["Closest work", "Year", "Cited in the manuscript", "What differs"],
                         [[f"{flat(w.get('title'))} (corpusId {w.get('corpusId')})", w.get("year"),
                           "yes" if w.get("cited") else "no", w.get("differs")] for w in works])


def verdict_table(data: dict, labels: tuple[str, str]) -> list[str]:
    verdicts = part(data, "verdicts")
    return table(["", "Verdict", "Reason"],
                 [[label, flat(part(verdicts, name).get("verdict")).replace("_", " "), part(verdicts, name).get("reason")]
                  for label, name in zip(labels, ("scientific", "submission"))])


def review_md(data: dict, state: dict, title: str) -> str:
    standing, verdicts = state["standing"], state["verdicts"]
    lines = [f"# Paper review: {title}", "",
             f"Scientific readiness: **{verdicts['scientific'].replace('_', ' ')}**. Submission readiness: "
             f"**{verdicts['submission'].replace('_', ' ')}**. Findings: {counts(standing)}; blocking: "
             f"{', '.join(map(str, state['blocking'])) or 'none'}. Target: {flat(data.get('target')) or 'not stated'}.",
             "", "This review gives no score and does not predict acceptance.", ""]
    if any("recheck" in f for f in rows(data, "findings")):
        lines += ["Second round. Resolved in the revision: "
                  f"{', '.join(flat(f.get('id')) for f in state['resolved']) or 'none'}.", ""]
    lines += ["## What was read", ""]
    lines += table(["Item", "Status", "Note"], [[r.get("item"), flat(r.get("status")).replace("_", " "), r.get("note")]
                                                for r in rows(data, "coverage")])
    lines += ["What was not read or not provided was not assessed. It is not counted as missing from the work.", "",
              "## The paper in brief", "", flat(data.get("summary")), ""]
    if names(data.get("strengths")):
        lines += ["Strengths:", "", *(f"- {flat(s)}" for s in names(data.get("strengths"))), ""]
    if rows(data, "claims"):
        bears = {c.get("id"): [f.get("id") for f in standing if c.get("id") in names(f.get("claims"))]
                 for c in rows(data, "claims")}
        lines += ["## Claims and evidence", ""]
        lines += table(["Claim", "Where", "Type", "Evidence in the manuscript", "Support", "Mismatch", "Findings"],
                       [[f"{c.get('id')}. {flat(c.get('claim'))}", c.get("location"), c.get("type"), c.get("evidence"),
                         flat(c.get("support")).replace("_", " "),
                         ", ".join(map(str, names(c.get("mismatch")))).replace("_", " "),
                         ", ".join(map(str, bears[c.get("id")]))] for c in rows(data, "claims")])
    lines += novelty_lines(data)
    lines += ["## Other checks", ""]
    for name in ("references", "statistics"):
        entry = part(part(data, "checks"), name)
        lines.append(f"- {name.capitalize()}: {'checked' if entry.get('status') == 'done' else 'not checked'}. "
                     f"{flat(entry.get('note'))}".rstrip())
    lines += ["", "## Findings", ""]
    for severity in SEVERITIES:
        tier = [f for f in standing if f["severity"] == severity]
        lines += [f"### {severity.capitalize()}", ""]
        lines += [line for f in tier for line in finding_lines(f)] if tier else [f"No {severity} findings.", ""]
    if state["resolved"]:
        lines += ["### Resolved in the revision", ""]
        lines += [f"- {flat(f.get('id'))}. {flat(f.get('location'))}: {flat(part(f, 'recheck').get('note'))}"
                  for f in state["resolved"]] + [""]
    if state["withdrawn"]:
        lines += ["### Withdrawn after verification", "",
                  ", ".join(flat(f.get("id")) for f in state["withdrawn"]) + ": refuted when checked against the "
                  "manuscript. Withdrawn findings stay in findings.json and are not part of this review.", ""]
    lines += ["## Verdicts", ""] + verdict_table(data, ("Scientific", "Submission"))
    if state["not_checked"]:
        lines += ["Not checked, so not covered by these verdicts: " + ", ".join(state["not_checked"]) + ".", ""]
    return "\n".join(lines)


def referee_report_md(data: dict, state: dict, title: str) -> str:
    lines = [f"# Referee report: {title}", "", "Comments to the authors.", "", "## Summary of the submission", "",
             flat(data.get("summary")), ""]
    if names(data.get("strengths")):
        lines += ["## Strengths", "", *(f"- {flat(s)}" for s in names(data.get("strengths"))), ""]
    for heading, tiers in (("Major comments", ("critical", "major")), ("Minor comments", ("minor",))):
        tier = [f for f in state["standing"] if f["severity"] in tiers]
        lines += [f"## {heading}", ""]
        lines += [line for f in tier for line in finding_lines(f, to_authors=True)] if tier else ["None.", ""]
    return "\n".join(lines + novelty_lines(data, to_authors=True))


def to_editor_md(data: dict, state: dict, title: str) -> str:
    ref = part(data, "referee")
    lines = [f"# To the editor, in confidence: {title}", "", f"Venue: {flat(ref.get('venue'))}", "",
             f"Recommendation (a draft; the reviewer decides): {flat(ref.get('recommendation'))}", ""]
    if text_of(ref, "to_editor"):
        lines += [flat(ref.get("to_editor")), ""]
    lines += ["## Assessment", ""] + verdict_table(data, ("Scientific soundness", "As submitted"))
    lines += [f"Findings in the report to the authors: {counts(state['standing'])}. Blocking: "
              f"{', '.join(map(str, state['blocking'])) or 'none'}.", "", "## Limits of this review", ""]
    limits = [f"- {flat(r.get('item'))}: {flat(r.get('status')).replace('_', ' ')}. {flat(r.get('note'))}".rstrip()
              for r in rows(data, "coverage") if r.get("status") != "read"]
    limits += [f"- {name}: not checked. {flat(part(part(data, 'checks'), name).get('note'))}".rstrip()
               for name in state["not_checked"]]
    lines += (limits or ["- Everything provided was read, and every check was run."]) + [
        "", "## Use of AI", "", "The reviewer confirmed that the venue allows AI assistance. This report is a draft "
        "made with it: before sending anything, the reviewer reads the manuscript, checks each comment, and discloses "
        "the assistance as the venue requires.", ""]
    return "\n".join(lines)


def recheck_md(table_rows: list[dict]) -> str:
    lines = ["# Second-round check", "", "Each finding's quoted passage against the revised manuscript. An unchanged "
             "passage does not mean the finding is open, and a changed one does not mean it is closed: apply the "
             "finding's closure test to the revised text.", ""]
    lines += table(["Finding", "Severity", "Where", "Quoted passage", "Status", "New text quoted", "Check"],
                   [[r["id"], r["severity"], r["location"], r["passage"].replace("_", " "),
                     str(r["status"]).replace("_", " "), r["new_quote"].replace("_", " "),
                     RECHECK_PROBLEM.get(r["problem"], "")] for r in table_rows])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hold a paper review to its contract and write the report.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("check", "Check findings.json against the manuscript and write the report"),
                       ("recheck", "Second round: is each quoted passage still in the revised manuscript")):
        p = sub.add_parser(name, help=text)
        p.add_argument("findings", help="findings.json")
        p.add_argument("--manuscript", nargs="+", required=True, metavar="FILE",
                       help="The manuscript and supplement files that were read (.tex .md .txt .docx .pdf)")
        p.add_argument("--out", help="Output folder (default: the folder of findings.json)")
        if name == "check":
            p.add_argument("--referee", action="store_true",
                           help="A report on someone else's paper: also write referee-report.md and to-editor.md")
    args = parser.parse_args()

    path = Path(args.findings)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(f"Cannot read {path}: {error}")
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        fail(f'{path} must be a JSON object with a "findings" list (an empty list when there are none).')
    texts = load_texts(args.manuscript)
    out_dir = Path(args.out) if args.out else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    title = flat(data.get("title")) or Path(args.manuscript[0]).name

    if args.command == "recheck":
        table_rows = [recheck_finding(f, texts) for f in rows(data, "findings")
                      if part(f, "verification").get("outcome") != "refuted"]
        (out_dir / "recheck.md").write_text(recheck_md(table_rows), encoding="utf-8")
        problems = [{"id": r["id"], "problem": r["problem"], "message": RECHECK_PROBLEM[r["problem"]]}
                    for r in table_rows if r["problem"]]
        group = lambda key, values: {v: [r["id"] for r in table_rows if r[key] == v] for v in values}  # noqa: E731
        print(json.dumps({"ok": not problems, "findings": len(table_rows),
                          "passage": group("passage", ("unchanged", "changed", "gone", "no_quote", "unknown")),
                          "status": group("status", (*RECHECK, "not_rechecked")),
                          "problems": problems, "report": str(out_dir / "recheck.md")}, indent=2, ensure_ascii=False))
        return 1 if problems else 0

    errors, state = check(data, texts, args.referee)
    written = []
    if not errors:
        reports = {"review.md": review_md}
        if args.referee:
            reports.update({"referee-report.md": referee_report_md, "to-editor.md": to_editor_md})
        for name, render in reports.items():
            (out_dir / name).write_text(render(data, state, title), encoding="utf-8")
            written.append(str(out_dir / name))
    print(json.dumps({
        "ok": not errors, "findings": len(rows(data, "findings")), "standing": len(state["standing"]),
        "by_severity": {s: sum(1 for f in state["standing"] if f.get("severity") == s) for s in SEVERITIES},
        "blocking": state["blocking"], "withdrawn": [f.get("id") for f in state["withdrawn"]],
        "resolved": [f.get("id") for f in state["resolved"]], "verdicts": state["verdicts"],
        "not_checked": state["not_checked"], "manuscript_words": sum(len(tokens(text)) for text, _ in texts),
        "errors": errors, "written": written,
    }, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
