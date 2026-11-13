#!/usr/bin/env python3
"""Evidence for a journal shortlist, and a check of the shortlist written from it.

The agent searches and judges. This script counts where similar papers and the manuscript's
references were published, asks two public registries what they hold about a venue, keeps every
venue fact with its source and the date it was read, and checks the finished shortlist.

  venue_tally.py tally --similar searches/similar-*.json --bib refs.bib --exclude "Journal of X"
  venue_tally.py tally --similar s1.json s2.json --references reference-lookups.json
  venue_tally.py lookup "PLOS ONE" "Nature Machine Intelligence"    Crossref by name, DOAJ by ISSN
  venue_tally.py lookup "eLife" --issn 2050-084X                     when the ISSN is known
  venue_tally.py fact "eLife" scope "…" --url https://… [--date 2026-11-12]   read on the venue's page
  venue_tally.py check journal-shortlist/shortlist.md

Files, under --dir (default: journal-shortlist): tally.json, tally.md, facts.json, facts.md and
cache.json (registry answers with the date they were read, so nothing is asked twice).

Network: `lookup` only, and only api.crossref.org and doaj.org, without a key. A registry that
answered and has no such journal is `not_found`; one that did not answer is `lookup_failed`,
and the venue then counts as not checked.

Exit codes: 0 done; 1 `check` found a broken rule; 2 bad input. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOOL = "researchzy-find-journal"
USER_AGENT = "researchzy-find-journal/1.0"
CROSSREF = "https://api.crossref.org/journals"
DOAJ = "https://doaj.org/api/search/journals/issn:"
PAUSE = 1.0  # seconds between two requests to the same host
BANDS = ("strong fit", "plausible", "stretch")
CONFIRM = "confirm on site"
STREAMS = ("similar", "references")
FIELDS = {  # the rows every venue has in the facts-to-confirm table
    "scope": "Scope statement", "article_types": "Article types accepted", "length_limits": "Length limits",
    "open_access": "Open-access model", "fee": "Fee", "peer_review": "Peer-review model",
    "time_to_decision": "Time to decision", "indexing": "Indexing", "preprint_policy": "Preprint policy",
}
FACT_ROWS = ["| Venue | Field | Value | Source | Date read |", "|---|---|---|---|---|"]
TALLY_ROWS = ["| Venue | Similar papers | References | Years | Examples |", "|---|---|---|---|---|"]
NOTES = (
    "DOAJ lists only fully open-access journals: a subscription or hybrid journal is expected to be `not found`.",
    "Crossref's journal list has no conferences: a conference is expected to be `not found` or `not matched`.",
    "Neither absence is a warning by itself. `lookup failed` means no answer: not checked; run it again later.",
    "DOAJ's fee, licence, review model and weeks are what the journal declared to DOAJ: confirm them on its site.",
    "DOAJ is asked with one ISSN (the electronic one when Crossref marks it); for an open-access journal it does "
    "not find, try the other ISSN with --issn.",
    "A registry record shows that a journal is registered and depositing DOIs, not what its standing is.",
)

ISSN_RE = re.compile(r"\d{4}-\d{3}[\dX]")
CONFERENCE_RE = re.compile(r"\b(?:conference|symposium|workshop|meeting|congress|colloquium)\b")
ORDINAL_RE = re.compile(
    r"\b(?:(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[ -])?"
    r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)|tenth|eleventh|twelfth"
    r"|(?:thir|four|fif|six|seven|eigh|nine)teenth|(?:twent|thirt|fort|fift|sixt|sevent|eight|ninet)ieth)\b")
REPOSITORIES = {  # preprint servers and repositories named at the start of a venue string
    "ssrn": "SSRN", "social science research network": "SSRN", "research square": "Research Square",
    "zenodo": "Zenodo", "osf": "OSF", "open science framework": "OSF", "preprints": "Preprints.org",
    "authorea": "Authorea", "figshare": "Figshare", "hal": "HAL", "dryad": "Dryad", "qeios": "Qeios",
}
# arXiv, bioRxiv, medRxiv, ChemRxiv, PsyArXiv and the like share their ending.
PREPRINT_RE = re.compile(r"\b(\w*rxiv)\b|^(" + "|".join(REPOSITORIES) + r")\b")

# `check`: a number in the same sentence or table cell as one of these words needs a row in facts.json.
TRIGGER_RE = re.compile(
    r"impact factor|acceptance rate|\bapcs?\b|article processing charge|\bfees?\b|\bweeks?\b|\bdays?\b", re.I)
NUMBER_RE = re.compile(r"(?<![\d.,-])\d+(?:,\d{3})*(?:\.\d+)?")
# One field of a .bib entry: a value in braces (nested up to three deep), in quotes, or bare.
BIB_FIELD_RE = re.compile(r'\s*([A-Za-z][\w-]*)\s*=\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}|"[^"]*"|[^,}\n]*)\s*,?')
PREDICTION_RE = re.compile(r"probabilit(?:y|ies)|(?:chances?|likelihood|odds) of (?:acceptance|being accepted)", re.I)

sleep = time.sleep
STATE = {"cache": {}, "last": {}, "calls": 0, "timeout": 15}


def fail(message: str):
    print(message, file=sys.stderr)
    sys.exit(2)


def today() -> str:
    return datetime.date.today().isoformat()


def read_json(path: Path, default=None):
    if default is not None and not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(f"Cannot read {path} as JSON: {error}")


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cell(value) -> str:
    """Text as it stands in a Markdown table cell."""
    return " ".join(str(value if value is not None else "").split()).replace("|", "/")


# Venue names: one key for the spellings of one venue, and a bucket for preprint servers.
def fold(text) -> str:
    """Lower case, accents removed, "&" spelled out; punctuation still in place."""
    text = unicodedata.normalize("NFKD", html.unescape(str(text or "")))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().replace("&", " and ")


def words(text: str) -> str:
    return " ".join(re.sub(r"[\W_]+", " ", text).split())


def venue_key(name) -> str:
    """The form in which two spellings of a venue are the same venue. Abbreviations are not expanded."""
    text = re.sub(r"\([^()]*\)\s*$", " ", fold(name))                       # a trailing "(CVPR 2021)" or "(London)"
    text = re.sub(r"\b(?:vol(?:ume)?|no|issue)\b\.?\s*\d+", " ", text)
    text = re.sub(r"\b(?:19|20)\d{2}\b|'\d{2}\b|\b\d+(?:st|nd|rd|th)\b", " ", text)   # years and "38th"
    text = re.sub(r"\s\d{1,5}$", "", words(text))                             # a bare volume number at the end
    if CONFERENCE_RE.search(text):
        text = re.sub(r"^(?:in )?proc(?:eedings)? (?:of )?", "", words(ORDINAL_RE.sub(" ", text)))
    text = re.sub(r"^the ", "", text)
    return "" if text in ("", "unknown", "none", "null", "n a") else text


def classify(raw) -> tuple:
    """(bucket, key, name as shown) of a venue string. The bucket is "venue", "preprint" or "" (no venue)."""
    key = venue_key(raw)
    match = PREPRINT_RE.search(key)
    if not match:
        return ("venue", key, " ".join(str(raw).split())) if key else ("", "", "")
    if match.group(2):
        return "preprint", REPOSITORIES[match.group(2)].lower(), REPOSITORIES[match.group(2)]
    shown = re.search(re.escape(match.group(1)), str(raw), re.I)
    return "preprint", match.group(1), shown.group() if shown else match.group(1)


def field_name(text: str) -> str:
    """A field's name from its name or its table label: "Open-access model" and "open_access" are one field."""
    plain = words(fold(text))
    return next((name for name, label in FIELDS.items() if plain in (words(fold(label)), name.replace("_", " "))),
                plain.replace(" ", "_"))


# tally: where similar papers and the references were published.
def read_bib(path: Path) -> list:
    """(reference key, paper) for each entry of a .bib file, with TeX markup removed from the fields."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        fail(f"Cannot read {path}: {error}")
    entries = []
    for match in re.finditer(r"@(\w+)\s*[{(]\s*([^,\s{}]+)\s*,", text):
        kind, fields, i = match.group(1).lower(), {}, match.end()
        if kind in ("comment", "string", "preamble"):
            continue
        while (found := BIB_FIELD_RE.match(text, i)):
            value, i = found.group(2).strip(), found.end()
            value = value[1:-1] if value[:1] in ('{', '"') else value
            value = re.sub(r"\\[a-zA-Z]+\s*|\\.", "", re.sub(r"\\([&%_#$])", r"\1", value))
            fields[found.group(1).lower()] = " ".join(re.sub(r"[{}]", "", value).replace("~", " ").split())
        # A booktitle is a venue only for a paper in proceedings, not for a chapter in a book.
        venue = (fields.get("journal") or fields.get("journaltitle")
                 or (fields.get("booktitle") if kind in ("inproceedings", "conference", "proceedings") else "")
                 or fields.get("archiveprefix") or fields.get("eprinttype") or "")
        entries.append((match.group(2), {"title": fields.get("title"), "doi": fields.get("doi"), "venue": venue,
                                         "year": fields.get("year") or fields.get("date")}))
    return entries


def add_paper(stream: dict, record: dict, label: str = "") -> None:
    """Add one paper to a stream. The same DOI, corpusId, reference key or title is one paper."""
    venue = record.get("venue") or record.get("journal") or ""
    bucket, key, shown = classify(venue.get("name") if isinstance(venue, dict) else venue)
    year = re.match(r"(?:1[5-9]|20)\d{2}", str(record.get("year") or ""))
    year = int(year.group()) if year else None
    title = " ".join(str(record.get("title") or "").split())
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", str(record.get("doi") or "").strip().lower())
    ids = [f"{kind}:{value}" for kind, value in (("doi", doi), ("id", record.get("corpusId")), ("key", label),
                                                 ("title", words(fold(title)))) if value not in (None, "")]
    found = not record.get("not_found")
    paper = next((stream["index"][i] for i in ids if i in stream["index"]), None)
    if paper is None:
        paper = {"label": label or title or doi or "untitled", "title": title, "year": year, "bucket": "",
                 "key": "", "venue": "", "not_found": not found}
        stream["papers"].append(paper)
    else:
        stream["duplicates"] += 1
        paper["not_found"] = paper["not_found"] and not found
        paper["title"] = paper["title"] or title
    # A journal beats a preprint server and either beats nothing: the published version is the one that counts.
    rank = {"": 0, "preprint": 1, "venue": 2}
    if rank[bucket] > rank[paper["bucket"]]:
        paper.update(bucket=bucket, key=key, venue=shown, year=year or paper["year"])
    paper["year"] = paper["year"] or year
    for i in ids:
        stream["index"].setdefault(i, paper)


def load_results(stream: dict, path: Path, name: str) -> dict:
    """Read a saved tool result into a stream: a list of papers, an object holding one under results, papers
    or items, or {reference: [papers]}, where the first paper is the match and an empty list is "not found"."""
    data = records = read_json(path)
    if isinstance(data, dict):
        inner = next((data[n] for n in ("results", "papers", "items") if n in data), None)
        records = inner if inner is not None else data if all(isinstance(v, list) for v in data.values()) else [data]
    if not isinstance(records, (list, dict)):
        fail(f"{path}: expected a list of papers, or an object with results, papers or items.")
    row = {"file": str(path), "stream": name, "records": 0}
    for label, found in (records.items() if isinstance(records, dict) else [("", r) for r in records]):
        label = str(label) if name == "references" else ""
        for record in (found if isinstance(found, list) else [found])[:1 if label else None]:
            if isinstance(record, dict) and (record.get("title") or record.get("doi")):
                add_paper(stream, record, label)
                row["records"] += 1
        if label and not found and f"key:{label}" not in stream["index"]:
            add_paper(stream, {"not_found": True}, label)
    if isinstance(data, dict):
        row.update({k: data[k] for k in ("query", "total") if data.get(k) not in (None, "")})
    return row


def finish_group(group: dict) -> dict:
    names = sorted(group["variants"], key=lambda v: (-group["variants"][v], len(v), v))
    years = [p["year"] for s in STREAMS for p in group[s] if p["year"]]
    return {"name": names[0], "key": group["key"], "variants": names, "similar": len(group["similar"]),
            "references": len(group["references"]), "years": [min(years), max(years)] if years else None,
            "examples": {s: [f"{p['title'][:120]} ({p['year']})" if p["year"] else p["title"][:120]
                             for p in sorted(group[s], key=lambda p: (-(p["year"] or 0), p["title"])) if p["title"]][:3]
                         for s in STREAMS}}


def write_tally_md(path: Path, tally: dict) -> None:
    s, r = tally["similar"], tally["references"]
    lines = ["# Venue tally", "",
             f"Similar papers: {s['papers']} ({s['deduplicated']} found more than once and counted once, "
             f"{s['without_venue']} without a venue). References: {r['papers']} ({r['deduplicated']} duplicates "
             f"counted once, {len(r['without_venue'])} without a venue, {len(r['not_found'])} not found in the index).",
             "", "The counts show where such work has appeared. They are evidence for a shortlist, not a ranking, "
             "and they say nothing about a venue's standing, fees or speed.", ""]
    for title, rows, note in (
            ("Venues", tally["venues"], "Most evidence first."),
            ("Preprint servers and repositories", tally["preprints"], "Counted apart: not venues to shortlist."),
            ("Excluded", tally["excluded"], "Left out at the user's request: they must not appear in the shortlist.")):
        if rows:
            lines += [f"## {title}", "", note, "", *TALLY_ROWS]
        for v in rows:
            also = [n for n in v.get("variants", []) if n != v["name"]]
            examples = ". ".join(f"{name.capitalize()}: " + " · ".join(v["examples"][name])
                                 for name in STREAMS if v.get("examples", {}).get(name))
            lines.append(f"| {cell(v['name'])}{' (also written: ' + cell('; '.join(also)) + ')' if also else ''} "
                         f"| {v['similar']} | {v['references']} "
                         f"| {'–'.join(str(y) for y in dict.fromkeys(v.get('years') or []))} | {cell(examples)} |")
        lines += [""] if rows else []
    for title, labels in (("References without a venue", r["without_venue"]),
                          ("References not found in the index", r["not_found"])):
        if labels:
            lines += [f"## {title}", "", *[f"- {cell(label)}" for label in labels], ""]
    lines += ["## Inputs", "", "| File | Stream | Query | Results reported | Records read |", "|---|---|---|---|---|"]
    lines += [f"| {cell(i['file'])} | {i['stream']} | {cell(i.get('query'))} | {cell(i.get('total'))} | {i['records']} |"
              for i in tally["inputs"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_tally(args, directory: Path) -> dict:
    if not (args.similar or args.bib or args.references):
        fail("tally needs --similar, --bib or --references.")
    streams = {name: {"papers": [], "index": {}, "duplicates": 0} for name in STREAMS}
    inputs = [load_results(streams["similar"], Path(p), "similar") for p in args.similar]
    for path in args.bib:
        entries = read_bib(Path(path))
        for key, paper in entries:
            add_paper(streams["references"], paper, key)
        inputs.append({"file": path, "stream": "references", "records": len(entries)})
    inputs += [load_results(streams["references"], Path(p), "references") for p in args.references]

    groups: dict = {}
    for name, stream in streams.items():
        for paper in stream["papers"]:
            if paper["bucket"]:
                group = groups.setdefault((paper["bucket"], paper["key"]), {
                    "key": paper["key"], "bucket": paper["bucket"], "variants": {}, "similar": [], "references": []})
                group["variants"][paper["venue"]] = group["variants"].get(paper["venue"], 0) + 1
                group[name].append(paper)
    done = sorted(((g["bucket"], finish_group(g)) for g in groups.values()),
                  key=lambda item: (-item[1]["similar"] - item[1]["references"], -item[1]["similar"], item[1]["name"]))
    excluded = {venue_key(name): " ".join(name.split()) for name in args.exclude if venue_key(name)}
    left_out = [v for _, v in done if v["key"] in excluded]
    left_out += [{"name": name, "key": key, "similar": 0, "references": 0} for key, name in excluded.items()
                 if key not in {v["key"] for v in left_out}]
    refs = streams["references"]
    tally = {
        "tool": TOOL, "schema_version": 1, "inputs": inputs,
        "similar": {"papers": len(streams["similar"]["papers"]), "deduplicated": streams["similar"]["duplicates"],
                    "without_venue": sum(1 for p in streams["similar"]["papers"] if not p["bucket"])},
        "references": {"papers": len(refs["papers"]), "deduplicated": refs["duplicates"],
                       "without_venue": [p["label"] for p in refs["papers"] if not p["bucket"] and not p["not_found"]],
                       "not_found": [p["label"] for p in refs["papers"] if p["not_found"]]},
        "venues": [v for bucket, v in done if bucket == "venue" and v["key"] not in excluded],
        "preprints": [v for bucket, v in done if bucket == "preprint" and v["key"] not in excluded],
        "excluded": left_out,
    }
    write_json(directory / "tally.json", tally)
    write_tally_md(directory / "tally.md", tally)

    return {**{name: {k: len(v) if isinstance(v, list) else v for k, v in tally[name].items()} for name in STREAMS},
            "venues": len(tally["venues"]),
            "top": [f"{v['name']}: {v['similar']} similar, {v['references']} in references" for v in tally["venues"][:10]],
            "preprints": [v["name"] for v in tally["preprints"]], "excluded": [v["name"] for v in left_out],
            "files": [str(directory / "tally.json"), str(directory / "tally.md")]}


# lookup and fact: venue facts with their source and the date they were read.
def open_url(url: str, timeout: int):
    """(status, body, headers). The status is None when no response arrived."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, b"", dict(error.headers or {})
    except Exception:
        return None, b"", {}


def fetch_json(url: str) -> tuple:
    """(status, JSON object or None, date the answer was read). A pause per host, one retry on 429 or 503.
    Only answers are cached (a 200 that parses, a 404), so a failed lookup is asked again next time."""
    hit = STATE["cache"].get(url)
    if hit:
        return hit["status"], hit["data"], hit["date"]
    host, status, body = urllib.parse.urlsplit(url).netloc, None, b""
    for attempt in (1, 2):
        wait = STATE["last"].get(host, -PAUSE) + PAUSE - time.monotonic()
        if wait > 0:
            sleep(wait)
        status, body, headers = open_url(url, STATE["timeout"])
        STATE["last"][host] = time.monotonic()
        STATE["calls"] += 1
        if status not in (429, 503) or attempt == 2:
            break
        retry = str(headers.get("Retry-After") or "")
        sleep(min(float(retry), 30.0) if retry.isdigit() else 5.0)
    try:
        data = json.loads(body.decode("utf-8", "replace")) if status == 200 else None
    except ValueError:
        data = None
    data = data if isinstance(data, dict) else None
    if status == 404 or data is not None:
        STATE["cache"][url] = {"status": status, "data": data, "date": today()}
    return status, data, today()


def ask_crossref(name: str, issn: str) -> dict:
    """What Crossref's journal list holds for a name, or for an ISSN when one is given."""
    url = f"{CROSSREF}/{issn}" if issn else CROSSREF + "?" + urllib.parse.urlencode({"query": name, "rows": 5})
    status, data, date = fetch_json(url)
    out = {"url": url, "date": date, "status": "lookup_failed", "rows": {}, "issn": [], "near": [], "note": ""}
    message = (data or {}).get("message")
    if status == 404 and issn:
        out["status"] = "not_found"
    elif isinstance(message, dict):
        items = [message] if issn else [i for i in message.get("items") or [] if isinstance(i, dict)]
        # A title is a match only when it equals the asked name once both are normalised.
        exact = items if issn else [i for i in items if venue_key(i.get("title")) == venue_key(name)]
        if exact:
            record = max(exact, key=lambda i: (i.get("counts") or {}).get("current-dois") or 0)
            years = sorted((p for p in (record.get("breakdowns") or {}).get("dois-by-issued-year") or []
                            if isinstance(p, list) and len(p) == 2), reverse=True)[:4]
            # The electronic ISSN first: it is the one DOAJ is asked with.
            typed = [t.get("value") for t in record.get("issn-type") or [] if isinstance(t, dict)
                     and t.get("type") == "electronic"]
            out.update(status="found", issn=[str(n) for n in typed + list(record.get("ISSN") or []) if n], rows={
                "crossref_title": record.get("title"), "publisher": record.get("publisher"),
                "issn": ", ".join(dict.fromkeys(str(n) for n in record.get("ISSN") or [])),
                "current_dois": (record.get("counts") or {}).get("current-dois"),
                "dois_by_year": "; ".join(f"{year}: {count}" for year, count in years)})
            if len(exact) > 1:
                out["note"] = f"{len(exact)} Crossref records carry this title; give --issn to pin one"
            elif venue_key(record.get("title")) != venue_key(name):
                out["note"] = f"Crossref's title for this ISSN is {record.get('title')!r}"
        else:
            out["status"] = "not_matched" if items else "not_found"
            out["near"] = [f"{i.get('title')} ({', '.join(str(n) for n in i.get('ISSN') or []) or 'no ISSN'}; "
                           f"{i.get('publisher') or 'publisher not given'})" for i in items]
            out["note"] = "did you mean: " + "; ".join(out["near"]) if items else ""
    return out


def ask_doaj(issn: str) -> dict:
    """Whether DOAJ lists a journal, and what the journal declared there. One request: DOAJ matches an ISSN
    against both of a journal's ISSNs, and a journal DOAJ does not list answers with no results."""
    out = {"url": DOAJ + issn if issn else "", "date": today(), "status": "not_looked_up", "rows": {},
           "note": "" if issn else "no ISSN known; give one with --issn"}
    if issn:
        status, data, out["date"] = fetch_json(out["url"])
        out["status"] = "not_found" if status == 200 and data is not None else "lookup_failed"
        record = next((r for r in (data or {}).get("results") or [] if isinstance(r, dict)), None)
        if record:
            bib, declared = record.get("bibjson") or {}, ", as declared to DOAJ"
            updated = str(record.get("last_updated") or "")[:10]
            licences = [x.get("type") for x in bib.get("license") or [] if isinstance(x, dict) and x.get("type")]
            apc, ref, weeks = bib.get("apc") or {}, bib.get("ref") or {}, bib.get("publication_time_weeks")
            prices = [f"{p.get('price')} {p.get('currency') or ''}".strip() for p in apc.get("max") or []
                      if isinstance(p, dict) and p.get("price") not in (None, "")]
            review = (bib.get("editorial") or {}).get("review_process") or []
            out.update(status="listed", rows={
                "doaj_title": bib.get("title"),
                "indexing": "Listed in DOAJ" + (f" (DOAJ record last updated {updated})" if updated else ""),
                "open_access": "Open access" + (f"; licence {', '.join(licences)}" if licences else "") + declared,
                "fee": ("No APC" + declared if apc.get("has_apc") is False else
                        "APC, highest charged: " + " or ".join(prices) + declared if apc.get("has_apc") and prices else
                        "Charges an APC, amount not given" + declared if apc.get("has_apc") else None),
                "fee_url": apc.get("url"),
                "peer_review": ", ".join(str(x) for x in review) + declared if review else None,
                # Not a time to decision: DOAJ records the span from submission to publication.
                "weeks_to_publication": (f"{weeks} weeks from submission to publication{declared}"
                                         if weeks not in (None, "") else None),
                "aims_scope_url": ref.get("aims_scope"), "author_instructions_url": ref.get("author_instructions"),
                "journal_url": ref.get("journal")})
    return out


def load_facts(directory: Path) -> list:
    data = read_json(directory / "facts.json", default={"facts": []})
    if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
        fail(f"{directory / 'facts.json'} is not a facts file written by this script.")
    return data["facts"]


def put_facts(facts: list, venue: str, source: str, rows: dict, url: str, date: str, note: str = "") -> None:
    """Replace what one source said about a venue. A page fact replaces only the same field."""
    key = venue_key(venue)
    facts[:] = [f for f in facts if not (venue_key(f.get("venue")) == key and f.get("source") == source
                                         and (source != "page" or f.get("field") in rows))]
    for name, value in rows.items():
        if value not in (None, ""):
            facts.append({"venue": " ".join(venue.split()), "field": name, "value": " ".join(str(value).split()),
                          "source_url": url, "retrieved": date, "source": source,
                          **({"note": note} if note and name.endswith("_status") else {})})


def save_facts(directory: Path, facts: list) -> None:
    """Write facts.json, and facts.md with the table rows ready to copy into the shortlist."""
    write_json(directory / "facts.json", {"tool": TOOL, "schema_version": 1, "facts": facts})
    venues = {key: next(f["venue"] for f in facts if venue_key(f["venue"]) == key)
              for key in dict.fromkeys(venue_key(f["venue"]) for f in facts)}

    def find(key: str, name: str):
        rows = [f for f in facts if venue_key(f["venue"]) == key and f["field"] == name]
        return next((f for f in rows if f["source"] == "page"), rows[0] if rows else None)   # the venue's page first

    def status(fact) -> str:
        return cell(f"{fact['value'].replace('_', ' ')}{' (' + fact['note'] + ')' if fact.get('note') else ''}, "
                    f"{fact['retrieved']}") if fact else "not looked up"

    def row(fact: dict, label: str) -> str:
        return f"| {cell(fact['venue'])} | {label} | {cell(fact['value'])} | {fact['source_url']} | {fact['retrieved']} |"

    lines = ["# Venue facts", "", "Every value below was read from the source and on the date shown.", "",
             "## Registry lookups", "", "| Venue | Crossref | DOAJ |", "|---|---|---|"]
    lines += [f"| {cell(name)} | {status(find(key, 'crossref_status'))} | {status(find(key, 'doaj_status'))} |"
              for key, name in venues.items()]
    lines += ["", *[f"- {note}" for note in NOTES], "", "## Rows for the facts-to-confirm table", "",
              f"Copy these rows into shortlist.md as they are. `{CONFIRM}` marks what nobody has read yet.", "",
              *FACT_ROWS]
    lines += [row(find(key, field), label) if find(key, field) else f"| {cell(name)} | {label} | {CONFIRM} | | |"
              for key, name in venues.items() for field, label in FIELDS.items()]
    lines += ["", "## Other recorded facts", "", *FACT_ROWS]
    lines += [row(f, f["field"]) for f in facts if f["field"] not in FIELDS and not f["field"].endswith("_status")]
    (directory / "facts.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_lookup(args, directory: Path) -> dict:
    issn = (args.issn or "").strip().upper()
    if issn and (len(args.venues) != 1 or not ISSN_RE.fullmatch(issn)):
        fail("--issn takes one ISSN in the form 1234-5678 and goes with exactly one venue name.")
    facts = load_facts(directory)
    STATE["cache"] = {} if args.refresh else read_json(directory / "cache.json", default={})
    STATE.update(timeout=args.timeout, calls=0)
    looked_up = []
    for venue in args.venues:
        found = ask_crossref(venue, issn)
        put_facts(facts, venue, "crossref", {**found["rows"], "crossref_status": found["status"]}, found["url"],
                  found["date"], found["note"])
        issns = [n for n in dict.fromkeys(([issn] if issn else []) + [n.upper() for n in found["issn"]])
                 if ISSN_RE.fullmatch(n)]
        listed = ask_doaj(issns[0] if issns else "")
        put_facts(facts, venue, "doaj", {**listed["rows"], "doaj_status": listed["status"]}, listed["url"],
                  listed["date"], listed["note"])
        looked_up.append({"venue": venue, "crossref": found["status"], "doaj": listed["status"], "issn": issns,
                          "did_you_mean": found["near"], "note": "; ".join(n for n in (found["note"], listed["note"]) if n)})
    write_json(directory / "cache.json", STATE["cache"])
    save_facts(directory, facts)
    return {"looked_up": looked_up, "registry_calls": STATE["calls"], "notes": list(NOTES),
            "files": [str(directory / "facts.json"), str(directory / "facts.md")]}


def cmd_fact(args, directory: Path) -> dict:
    field, value, date = field_name(args.field), " ".join(args.value.split()), args.date or today()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", field) or field.endswith("_status"):
        fail(f"Not a field name: {args.field!r}. Table fields: {', '.join(FIELDS)}; other names are free.")
    if not venue_key(args.venue) or value in ("", CONFIRM) or not re.fullmatch(r"https?://\S+", args.url):
        fail("fact needs a venue name, the value that was read, and --url with the page's http(s) address.")
    if not re.fullmatch(r"(19|20)\d\d-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", date):
        fail(f"--date must be a date such as 2026-11-12, got {date!r}.")
    facts = load_facts(directory)
    put_facts(facts, args.venue, "page", {field: value}, args.url, date)
    save_facts(directory, facts)
    return {"venue": args.venue, "field": field, "in_facts_table": field in FIELDS, "retrieved": date,
            "files": [str(directory / "facts.json"), str(directory / "facts.md")]}


# check: the shortlist against the tally and the facts.
def parse_shortlist(text: str) -> dict:
    """What `check` reads in shortlist.md (layout: references/shortlist-template.md): the venues under
    "## Shortlist" with band and reason, the body rows of each "## " section's tables, and every line outside
    code fences with the key of the venue whose heading it is under."""
    doc, name, in_body, fenced = {"venues": [], "tables": {}, "lines": []}, "", False, False
    for number, line in enumerate(text.splitlines(), 1):
        if fenced or line.strip().startswith("```"):
            fenced = fenced != line.strip().startswith("```")
            continue
        heading = re.match(r"(#{2,3})\s+(?:\d+[.)]\s*)?(.+?)\s*#*$", line)
        item = re.match(r"\s*[-*]\s*\**(band|reason)\**\s*:\**\s*(.*)$", line, re.I)
        if heading and heading.group(1) == "##":
            name = words(fold(heading.group(2)))
        elif heading and name == "shortlist":
            doc["venues"].append({"name": re.sub(r"[*`]", "", heading.group(2)).strip(), "line": number,
                                  "band": "", "reason": ""})
        elif item and name == "shortlist" and doc["venues"]:
            doc["venues"][-1][item.group(1).lower()] = re.sub(r"[*`]", "", item.group(2)).strip()
        doc["lines"].append((number, line, venue_key(doc["venues"][-1]["name"])
                             if name == "shortlist" and doc["venues"] else None))
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else None
        if cells and all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            in_body = True                      # the rule under a table's header row
        elif cells and in_body:
            doc["tables"].setdefault(name, []).append((number, cells))
        in_body = in_body and cells is not None
    return doc


def numbers_in(text: str) -> set:
    return {float(n.replace(",", "")) for n in NUMBER_RE.findall(text)}


def cmd_check(args, directory: Path) -> dict:
    try:
        text = Path(args.shortlist).read_text(encoding="utf-8")
    except OSError as error:
        fail(f"Cannot read {args.shortlist}: {error}")
    if not (directory / "tally.json").exists():
        fail(f"No tally.json in {directory}: run tally first, with the same --dir.")
    tally, facts, doc, problems = read_json(directory / "tally.json"), load_facts(directory), parse_shortlist(text), []

    def problem(rule: str, line: int, detail: str) -> None:
        problems.append({"rule": rule, "line": line, "detail": detail})

    def table(prefix: str) -> list:
        return next((rows for name, rows in doc["tables"].items() if name.startswith(prefix)), [])

    in_tally = {v["key"] for v in tally.get("venues", [])}
    named = [(line, cells[0]) for line, cells in table("added by judg") if venue_key(cells[0])]
    judged, listed = {venue_key(name) for _, name in named}, {}
    if not doc["venues"]:
        problem("layout", 0, "No venue found. Each venue is a '### <n>. <name>' heading under '## Shortlist'.")
    for v in doc["venues"]:
        key, name = venue_key(v["name"]), v["name"]
        named.append((v["line"], name))
        if key in listed:
            problem("layout", v["line"], f"{name} is on the shortlist twice.")
        listed[key] = name
        if key not in in_tally and key not in judged:
            problem("origin", v["line"], f"{name} is neither in tally.json nor under 'Added by judgement'.")
        if v["band"].lower() not in BANDS:
            problem("band", v["line"], f"{name}: band {v['band']!r}. Use one of: {', '.join(BANDS)}.")
        if not v["reason"]:
            problem("band", v["line"], f"{name}: no '- Reason:' line.")

    seen, confirm, sourced = set(), 0, 0
    for line, cells in table("facts to confirm"):
        venue, label, value, source, date = (cells + [""] * 5)[:5]
        key, field, where = venue_key(venue), field_name(label), f"{venue}, {label}"
        rows = [f for f in facts if venue_key(f.get("venue")) == key and f.get("field") == field
                and cell(f.get("value")).casefold() == cell(value).casefold()]
        named.append((line, venue))
        if key not in listed or field not in FIELDS:
            problem("facts_table", line, f"{where}: not a venue of the shortlist, or not a field of this table.")
            continue
        seen.add((key, field))
        if value == CONFIRM:
            confirm += 1
        elif not rows:
            problem("facts_table", line, f"{where}: this value has no row in facts.json. Record it with lookup or "
                    f"fact, or write '{CONFIRM}'.")
        elif not any(f.get("source_url") and f["source_url"] in source and f.get("retrieved") == date for f in rows):
            problem("facts_table", line, f"{where}: the source or the date is not the one in facts.json.")
        else:
            sourced += 1
    for key, name in listed.items():
        if (missing := [label for field, label in FIELDS.items() if (key, field) not in seen]):
            problem("facts_table", 0, f"{name}: no row for {', '.join(missing)}.")

    for line, cells in table("cascade plan"):
        venue = re.sub(r"[*`]", "", cells[1]).strip() if len(cells) > 1 else ""
        if venue_key(venue) and venue.lower() != "n/a":
            named.append((line, venue))
            if venue_key(venue) not in listed:
                problem("cascade", line, f"{venue} is in the cascade plan but not on the shortlist.")
    excluded = {v["key"] for v in tally.get("excluded", [])}
    for line, name in named:
        if venue_key(name) in excluded:
            problem("excluded", line, f"{name} was excluded and must not appear.")

    known: dict = {}   # venue -> the numbers in its recorded facts
    for fact in facts:
        if not str(fact.get("field", "")).endswith("_status"):
            known.setdefault(venue_key(fact.get("venue")), set()).update(numbers_in(str(fact.get("value"))))
    anywhere = set().union(*known.values())
    for number, raw, venue in doc["lines"]:
        # Addresses, dates, quoted titles, heading marks and list numbers are not metrics.
        line = re.sub(r"https?://\S+|\d{4}-\d{2}-\d{2}|“[^”]*”|\"[^\"]*\"", " ", raw)
        line = re.sub(r"^\s*(?:#+\s*)?(?:\d+[.)]\s+)?", "", line)
        for clause in re.split(r"\||[.;!?](?:\s|$)", line):
            if PREDICTION_RE.search(clause) or (re.search(r"\d\s*%", clause) and re.search(r"accept", clause, re.I)
                                                and not re.search(r"acceptance rate", clause, re.I)):
                problem("prediction", number, f"A probability or percentage of acceptance: {' '.join(clause.split())!r}. "
                        "Give a band and its reason.")
            trigger = TRIGGER_RE.search(clause)
            for n in sorted(numbers_in(clause) - (known.get(venue, set()) if venue else anywhere)) if trigger else []:
                problem("unsourced_number", number, f"{n:g} stands next to {trigger.group()!r} and is in no row of "
                        f"facts.json{' for this venue' if venue else ''}.")

    notes = [f"The shortlist has {len(listed)} venues; the aim is five to eight. Say why."] * (not 5 <= len(listed) <= 8)
    looked_up = {venue_key(f.get("venue")) for f in facts if f.get("field") == "crossref_status"}
    notes += [f"{name} was not looked up in the registries: name it under 'What was not checked'."
              for key, name in listed.items() if key not in looked_up]
    return {"ok": not problems, "venues": len(listed),
            "from_tally": [name for key, name in listed.items() if key in in_tally],
            "added_by_judgement": [name for key, name in listed.items() if key not in in_tally and key in judged],
            "facts_table": {"sourced": sourced, "confirm_on_site": confirm}, "problems": problems, "notes": notes}


def main() -> int:
    parser = argparse.ArgumentParser(description="Venue tallies, registry lookups and the check of a journal shortlist.")
    parser.add_argument("--dir", default="journal-shortlist", help="The output folder (default: journal-shortlist)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("tally", help="Count the venues of similar papers and of the manuscript's references")
    p.add_argument("--similar", nargs="+", action="extend", default=[], metavar="FILE",
                   help="Saved search_papers results for similar papers (JSON)")
    p.add_argument("--bib", action="append", default=[], metavar="FILE", help="The manuscript's .bib (repeatable)")
    p.add_argument("--references", nargs="+", action="extend", default=[], metavar="FILE",
                   help="Saved lookups of the references (JSON)")
    p.add_argument("--exclude", action="append", default=[], metavar="VENUE",
                   help="A venue to leave out, such as one that rejected the paper (repeatable)")

    p = sub.add_parser("lookup", help="Ask Crossref and DOAJ about venues (the only command that uses the network)")
    p.add_argument("venues", nargs="+", metavar="VENUE")
    p.add_argument("--issn", help="The journal's ISSN, with exactly one venue name")
    p.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds (default: 15)")
    p.add_argument("--refresh", action="store_true", help="Ignore the cache of earlier answers")

    p = sub.add_parser("fact", help="Record a fact read on the venue's own page in this session")
    p.add_argument("venue")
    p.add_argument("field", help="A table field (" + ", ".join(FIELDS) + ") or another name such as impact_factor")
    p.add_argument("value")
    p.add_argument("--url", required=True, help="The page the value was read on")
    p.add_argument("--date", help="The date it was read (default: today)")

    p = sub.add_parser("check", help="Check a shortlist against tally.json and facts.json")
    p.add_argument("shortlist")

    args = parser.parse_args()
    directory = Path(args.dir)
    if args.command != "check":
        directory.mkdir(parents=True, exist_ok=True)
    result = {"tally": cmd_tally, "lookup": cmd_lookup, "fact": cmd_fact, "check": cmd_check}[args.command](args, directory)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if args.command == "check" and not result["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
