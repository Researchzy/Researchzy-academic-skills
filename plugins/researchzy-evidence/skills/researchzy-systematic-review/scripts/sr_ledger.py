#!/usr/bin/env python3
"""The ledger of a systematic review: protocol, searches, records, duplicates and decisions, one entry per
record, so that sr_prisma.py can compute every number of the PRISMA 2020 flow from it.

  sr_ledger.py protocol protocol.json [--amend "what changed" --results-seen yes|no]
  sr_ledger.py search --source PubMed --kind database --interface E-utilities --query '...' \
                      --total 412 --pages 3 --last-page [--exported 412] [--filter mindate=2015/01/01]
  sr_ledger.py search --id s2 --incomplete-reason "..."         complete or correct a logged search
  sr_ledger.py records raw/s2.xml --search s2 --format pubmed     researchzy | pubmed | ctgov | ris
  sr_ledger.py dedup [--merge R0007 R0311] [--distinct R0012 R0408] [--reviewer user]
  sr_ledger.py decide decisions/ta-01.jsonl                       one JSON object per line
  sr_ledger.py check                                              writes check.md

A decision: {"record", "stage", "decision", "reviewer", "code", "quote", "locator", "study", "reason",
"note", "source"}; stages pre (remove, with a reason), ta (include, exclude, unsure) and ft (include,
exclude, not_retrieved with a note). An exclusion needs a protocol code and a quote, at ft also a
locator. The last decision for a record and stage is final. Records sharing a DOI, PMID, NCT number or
corpusId are one record. Quotes are compared ignoring case, spacing, punctuation other than signs,
ligatures and line-end hyphens.

All commands take --dir (default systematic-review). Standard library only; no network. Exit codes:
0 done; 1 protocol has problems, decide rejected a line, or check found an error; 2 an input cannot be
read.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DECISIONS = {"pre": ("remove",), "ta": ("include", "exclude", "unsure"), "ft": ("include", "exclude", "not_retrieved")}
FIELDS = ("record", "stage", "decision", "reviewer", "code", "quote", "locator", "study", "reason", "note", "source")
KINDS = ("database", "register", "other")
DESIGNS = ("parallel", "cluster", "crossover")
FRAMEWORKS = {"PICO": ("population", "intervention", "comparator", "outcome"),
              "PECO": ("population", "exposure", "comparator", "outcome"),
              "PIRD": ("population", "index_test", "reference_standard", "diagnosis"),
              "PCC": ("population", "concept", "context")}
# The extraction table of researchzy-meta-analysis, column for column; other columns are study characteristics.
EXTRACTION = ("study", "outcome", "timepoint", "arm", "n", "design", "reported_as", "value", "spread", "low", "high",
              "ci_level", "events", "cluster_size", "icc", "icc_source", "corr", "corr_source", "units", "reverse",
              "locator", "quote", "notes")
REPORTED_AS = ("mean_sd", "mean_se", "mean_ci", "change_sd", "change_se", "change_ci", "median_iqr", "median_range",
               "change_median_iqr", "change_median_range", "events", "ratio_ci", "r", "yi_se")
IDS = ("doi", "pmid", "nct", "corpus_id")    # a record's own identifiers: equal values mean the same record
TITLE_SIMILARITY = 0.90                      # with years at most YEAR_GAP apart: a candidate duplicate pair
YEAR_GAP = 1
MIN_QUOTE_WORDS = 3                          # a shorter quote occurs in almost any abstract
LETTER = r"[^\W\d_]"
WORD_RE = re.compile(r"[^\W_]+(?:\.\d+|,\d{3}(?!\d))*|[<>=\u2264\u2265\u00b1%-]")


def fail(message: str):
    print(f"sr_ledger: {message}", file=sys.stderr)
    raise SystemExit(2)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def num(record_id: str) -> int:
    return int(record_id[1:])


def read_bytes(path) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        fail(f"cannot read {path}: {exc.strerror or exc}")


def read_json(path):
    try:
        return json.loads(read_bytes(path).decode("utf-8-sig"))
    except ValueError as exc:
        fail(f"{path} is not valid JSON: {exc}")


def load(directory: Path) -> dict:
    if (directory / "ledger.json").exists():
        return read_json(directory / "ledger.json")
    return {"tool": "researchzy-systematic-review", "schema_version": 1, "protocol_history": [], "searches": [],
            "files": [], "records": {}, "merges": [], "distinct": [], "decisions": []}


def protocol(ledger: dict) -> dict:
    return ledger["protocol_history"][-1]["protocol"] if ledger["protocol_history"] else {}


def exclusion_codes(proto: dict) -> dict:
    return {c["code"]: c["text"] for c in proto.get("criteria", []) if c["code"].startswith("E")}


def cell(value) -> str:
    return re.sub(r"\s+", " ", str("" if value is None else value)).replace("|", "/")


def words(text) -> list:
    """The tokens the quote check compares: case, spacing, punctuation other than signs and comparisons,
    ligatures and a word split by a hyphen at a line end do not count."""
    text = unicodedata.normalize("NFKC", str(text or "")).casefold().replace("\u00ad", "")
    text = re.sub(rf"(?<={LETTER})[-\u2010\u2011]\s*\n\s*(?={LETTER})", "", text)
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)
    return WORD_RE.findall(re.sub(rf"(?<={LETTER})-(?={LETTER})", "", text))


def joined(text) -> str:
    return "\x1f" + "\x1f".join(words(text)) + "\x1f"


def contains(haystack: str, quote) -> bool:
    """Whether the quote's tokens occur in a row in `haystack`, a text passed through joined()."""
    tokens = words(quote)
    return bool(tokens) and "\x1f" + "\x1f".join(tokens) + "\x1f" in haystack


def quote_words(quote) -> int:
    return sum(1 for w in words(quote) if w[0].isalnum())


def norm_title(title) -> str:
    return " ".join(re.findall(r"[^\W_]+", re.sub(r"<[^>]+>", " ", unicodedata.normalize("NFKC", str(title or "")).casefold())))


def similar(a: str, b: str) -> float:
    if not a or not b or 2 * min(len(a), len(b)) < TITLE_SIMILARITY * (len(a) + len(b)):
        return 0.0                                           # the ratio cannot reach the threshold
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return matcher.ratio() if matcher.quick_ratio() >= TITLE_SIMILARITY else 0.0


def year_of(value):
    found = re.search(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", str(value or ""))
    return int(found.group(1)) if found else None


def norm_doi(value) -> str:
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", str(value or "").strip().lower())
    return doi.rstrip(".,;") if doi.startswith("10.") else ""


def record(title, abstract="", year=None, doi="", pmid="", nct="", corpus_id=None, venue="", authors=(), links=()) -> dict:
    rec = {"title": " ".join(str(title or "").split()), "abstract": str(abstract or "").strip(), "year": year_of(year),
           "doi": norm_doi(doi), "pmid": re.sub(r"\D", "", str(pmid or "")), "nct": str(nct or "").strip().upper(),
           "corpus_id": "" if corpus_id in (None, "") else str(corpus_id), "venue": " ".join(str(venue or "").split()),
           "authors": [a for a in authors if a], "links": sorted({str(x).strip().upper() for x in links if x})}
    return {k: v for k, v in rec.items() if k == "title" or v not in ("", None, [])}


def parse_researchzy(raw: bytes) -> list:
    def papers(node) -> list:                  # pages, lists and wrappers around the paper objects
        if isinstance(node, list):
            return [p for item in node for p in papers(item)]
        if not isinstance(node, dict):
            return []
        return [node] if node.get("title") or node.get("corpusId") else [p for v in node.values() for p in papers(v)]
    return [record(p.get("title"), p.get("abstract") or p.get("abstractText"), p.get("year"), p.get("doi"),
                   corpus_id=p.get("corpusId"), venue=p.get("venue"),
                   authors=[a.get("name", "") if isinstance(a, dict) else str(a) for a in p.get("authors") or []])
            for p in papers(json.loads(raw.decode("utf-8-sig")))]


def text_of(element) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def parse_pubmed(raw: bytes) -> list:
    root, out = ET.fromstring(raw), []
    for art in list(root) if root.tag == "PubmedArticleSet" else [root]:
        if art.tag not in ("PubmedArticle", "PubmedBookArticle"):
            continue
        ids = {e.get("IdType"): e.text for e in art.findall("./*/ArticleIdList/ArticleId")}   # not the cited works' ids
        doi = ids.get("doi") or next((e.text for e in art.iter("ELocationID") if e.get("EIdType") == "doi"), "")
        abstract = " ".join((f"{a.get('Label')}: " if a.get("Label") else "") + text_of(a) for a in art.iter("AbstractText"))
        trials = [n.text for bank in art.iter("DataBank") if "clinicaltrials" in (bank.findtext("DataBankName") or "").lower()
                  for n in bank.iter("AccessionNumber")]
        authors = [" ".join(filter(None, (a.findtext("ForeName"), a.findtext("LastName")))) or a.findtext("CollectiveName")
                   for a in art.iter("Author")]
        out.append(record(text_of(art.find(".//ArticleTitle")) or text_of(art.find(".//BookTitle")), abstract,
                          text_of(art.find(".//PubDate")), doi, pmid=art.findtext(".//PMID"),
                          venue=art.findtext(".//Journal/Title"), authors=authors, links=trials))
    return out


def parse_ctgov(raw: bytes) -> list:
    data, out = json.loads(raw.decode("utf-8-sig")), []
    for page in data if isinstance(data, list) else [data]:
        for study in page.get("studies", [page]) if isinstance(page, dict) else []:
            sec = study.get("protocolSection") or {}
            ident, status, design = (sec.get(m) or {} for m in ("identificationModule", "statusModule", "designModule"))
            if not ident.get("nctId"):
                continue
            facts = (("Study type", design.get("studyType")), ("Allocation", (design.get("designInfo") or {}).get("allocation")),
                     ("Conditions", ", ".join((sec.get("conditionsModule") or {}).get("conditions") or [])),
                     ("Interventions", ", ".join(i.get("name", "") for i in (sec.get("armsInterventionsModule") or {}).get(
                         "interventions") or [])), ("Minimum age", (sec.get("eligibilityModule") or {}).get("minimumAge")))
            summary = "\n".join([(sec.get("descriptionModule") or {}).get("briefSummary") or ""] + [f"{k}: {v}." for k, v in facts if v])
            date = (status.get("studyFirstPostDateStruct") or status.get("startDateStruct") or {}).get("date")
            pmids = [r.get("pmid") for r in (sec.get("referencesModule") or {}).get("references") or []]
            out.append(record(ident.get("officialTitle") or ident.get("briefTitle"), summary, date, nct=ident["nctId"],
                              venue="ClinicalTrials.gov", links=pmids))
    return out


def parse_ris(raw: bytes) -> list:
    out, entry, last = [], None, None
    for line in raw.decode("utf-8-sig").splitlines():
        tagged = re.match(r"^([A-Z][A-Z0-9])  ?-(?: (.*))?$", line.rstrip())
        tag = tagged.group(1) if tagged else None
        if tag == "TY":
            entry, last = {}, None
        elif tag == "ER" and entry is not None:
            first = lambda *tags: next((entry[t][0] for t in tags if entry.get(t)), "")  # noqa: E731
            doi = first("DO") or next((u for u in entry.get("UR", []) if "doi.org/" in u.lower()), "")
            out.append(record(first("TI", "T1", "CT"), " ".join(entry.get("AB") or entry.get("N2") or []), first("PY", "Y1", "DA"),
                              doi, venue=first("T2", "JO", "JF", "JA"), authors=entry.get("AU", []) + entry.get("A1", [])))
            entry = None
        elif tag and entry is not None:
            last = tag
            entry.setdefault(tag, []).append((tagged.group(2) or "").strip())
        elif entry is not None and last and line.strip():
            entry[last][-1] += " " + line.strip()
    return out


PARSERS = {"researchzy": parse_researchzy, "pubmed": parse_pubmed, "ctgov": parse_ctgov, "ris": parse_ris}


def groups(ledger: dict) -> dict:
    """Each record's group: the lowest record id among the records sharing an identifier or merged by hand."""
    parent = {rid: rid for rid in ledger["records"]}

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def join(a, b):
        low, high = sorted((root(a), root(b)), key=num)
        parent[high] = low

    seen: dict = {}
    for rid, rec in ledger["records"].items():
        for key in IDS:
            if rec.get(key):
                join(seen.setdefault((key, rec[key]), rid), rid)
    for merge in ledger["merges"]:
        join(merge["a"], merge["b"])
    return {rid: root(rid) for rid in parent}


def finals(ledger: dict, grp: dict) -> dict:
    return {(grp.get(d["record"], d["record"]), d["stage"]): d for d in ledger["decisions"]}   # the last one wins


def candidates(ledger: dict, grp: dict) -> list:
    """Pairs of groups whose titles are similar and whose years are close; settled pairs are left out. `different`
    names identifier types both groups have: their values differ, which speaks against a duplicate."""
    recs, out, kinds = ledger["records"], [], {}
    for rid, c in grp.items():
        kinds.setdefault(c, set()).update(k for k in IDS if recs[rid].get(k))
    settled = {frozenset((grp[d["a"]], grp[d["b"]])) for d in ledger["distinct"]}
    items = [(recs[c].get("year"), norm_title(recs[c]["title"]), c) for c in sorted(set(grp.values()), key=num)]
    known = sorted((i for i in items if i[0] and i[1]), key=lambda i: i[0])
    unknown = [i for i in items if not i[0] and i[1]]
    for n, x in enumerate(known + unknown):
        for y in (known[n + 1:] if n < len(known) else known + unknown[n - len(known) + 1:]):
            if n < len(known) and y[0] - x[0] > YEAR_GAP:
                break
            if frozenset((x[2], y[2])) not in settled and (score := similar(x[1], y[1])) >= TITLE_SIMILARITY:
                out.append({"a": x[2], "b": y[2], "similarity": round(score, 3), "years": [x[0], y[0]],
                            "titles": [recs[x[2]]["title"], recs[y[2]]["title"]], "different": sorted(kinds[x[2]] & kinds[y[2]])})
    return out


def protocol_problems(p: dict) -> list:
    problems: list = []

    def need(ok, message):
        if not ok:
            problems.append(message)

    def text(value) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def items(key) -> list:
        need(isinstance(p.get(key), list), f"{key} must be a list")
        return p[key] if isinstance(p.get(key), list) else []

    need(text(p.get("title")) and text(p.get("question")), "title and question are needed")
    need(p.get("framework") in FRAMEWORKS, "framework must be one of " + ", ".join(FRAMEWORKS))
    need(all(text((p.get("elements") or {}).get(e)) for e in FRAMEWORKS.get(p.get("framework"), ())),
         "elements needs " + ", ".join(FRAMEWORKS.get(p.get("framework"), ("the framework's elements",))))
    criteria = [c if isinstance(c, dict) else {} for c in items("criteria")]
    codes = [str(c.get("code")) for c in criteria]
    need(all(re.fullmatch(r"[IE][1-9]\d*", code) and text(c.get("text")) for code, c in zip(codes, criteria)),
         "every criterion needs a code (I1, I2, ... or E1, E2, ...) and a text")
    need(len(codes) == len(set(codes)), "codes used twice: " + ", ".join(sorted({c for c in codes if codes.count(c) > 1})))
    excl = [c for c in codes if c.startswith("E")]
    need(excl and len(excl) < len(codes), "criteria need at least one inclusion (I) and one exclusion (E) code")
    order = items("exclusion_order")
    need(len(order) == len(set(order)) and set(order) == set(excl),
         f"exclusion_order must list every E code once, highest priority first ({', '.join(excl)})")
    outcomes = [o if isinstance(o, dict) else {} for o in items("outcomes")]
    need(all(text(o.get("name")) and o.get("role") in ("primary", "secondary") and o.get("timepoints") for o in outcomes)
         and any(o.get("role") == "primary" for o in outcomes), "outcomes need name, role and timepoints, and one primary")
    need(all(items(k) and all(map(text, p[k])) for k in ("designs", "sources")), "designs and sources must list entries")
    need(all(isinstance(x, dict) and text(x.get("limit")) and text(x.get("reason")) for x in items("limits")),
         "every limit needs a reason")
    cal = p.get("calibration") if isinstance(p.get("calibration"), dict) else {}
    need(all(type(cal.get(k)) in (int, float) and 0 <= cal[k] <= 1 for k in ("kappa_min", "recall_min")),
         "calibration.kappa_min and recall_min must be numbers from 0 to 1")
    need(isinstance(cal.get("user_screens"), bool) and (cal["user_screens"] or text(cal.get("declined_reason"))),
         "calibration.user_screens must be true, or false with a declined_reason")
    reg = p.get("registration") if isinstance(p.get("registration"), dict) else {}
    need(reg.get("status") in ("registered", "planned", "not_registered") and (reg.get("status") != "registered" or (
        text(reg.get("registry")) and text(reg.get("id")) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(reg.get("date"))))),
        "registration.status is registered (with registry, id, date YYYY-MM-DD), planned or not_registered")
    need(all(isinstance(s, dict) and any(text(s.get(k)) for k in ("doi", "pmid", "nct", "title")) for s in items("seeds")),
         "every seed needs a doi, pmid, nct or title")
    return problems


def cmd_protocol(ledger, args, directory):
    proto = read_json(args.file)
    proto = {k: v for k, v in proto.items() if k not in ("version", "recorded")} if isinstance(proto, dict) else {}
    problems, history = protocol_problems(proto), ledger["protocol_history"]
    if problems:
        return {"recorded": False, "problems": problems}, 1
    if history and history[-1]["protocol"] == proto:
        return {"recorded": False, "version": len(history), "note": "the same as the recorded version"}, 0
    if history and not (args.amend and args.results_seen):
        fail("a protocol is recorded already: describe the change with --amend and --results-seen yes|no")
    history.append({"version": len(history) + 1, "recorded": now(), "change": args.amend or "",
                    "results_seen": args.results_seen == "yes" if history else None, "protocol": proto})
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "protocol.json").write_text(json.dumps(dict(proto, version=len(history), recorded=history[-1]["recorded"]),
                                                        indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"recorded": True, "version": len(history), "exclusion_order": proto["exclusion_order"],
            "calibration": proto["calibration"]}, 0


def find_search(ledger: dict, sid: str) -> dict:
    found = next((s for s in ledger["searches"] if s["id"] == sid), None)
    return found if found else fail(f"no search {sid!r}: log it first with the search command")


def cmd_search(ledger, args, directory):
    if args.id:
        search = find_search(ledger, args.id)
        search["revised"] = now()
    elif not all((args.source, args.kind, args.interface, args.query)):
        fail("a new search needs --source, --kind, --interface and --query")
    else:
        search = {"id": f"s{len(ledger['searches']) + 1}", "round": 1, "date": now(), "filters": {}, "total": None,
                  "exported": None, "pages": None, "last_page": False, "incomplete_reason": "", "note": ""}
        ledger["searches"].append(search)
    for name in ("source", "kind", "interface", "query", "date", "total", "exported", "pages", "round", "incomplete_reason", "note"):
        if getattr(args, name) is not None:
            search[name] = getattr(args, name)
    search["last_page"] = search["last_page"] or args.last_page
    for item in args.filter or []:
        name, sep, value = item.partition("=")
        search["filters"][name.strip()] = value.strip() if sep else fail(f"--filter takes name=value, not {item!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?Z?)?", search["date"]):
        fail(f"--date must be a UTC date such as 2026-11-13 or 2026-11-13T09:40Z, not {search['date']!r}")
    if min(search.get(n) or 0 for n in ("total", "exported", "pages")) < 0 or search["round"] < 1:
        fail("counts cannot be negative, and rounds start at 1")
    return {"search": search["id"], "round": search["round"]}, 0


def cmd_records(ledger, args, directory):
    search, added = find_search(ledger, args.search), []
    for name in args.files:
        raw = read_bytes(name)
        digest = hashlib.sha256(raw).hexdigest()
        if any(f["sha256"] == digest for f in ledger["files"]):
            fail(f"{name} has been added before (same content)")
        try:
            parsed = PARSERS[args.format](raw)
        except (ValueError, ET.ParseError, AttributeError, TypeError) as exc:
            fail(f"{name} cannot be read as {args.format}: {exc}")
        if not parsed:
            fail(f"no {args.format} records in {name}; a search without results needs no records command")
        for rec in parsed:
            added.append(f"R{len(ledger['records']) + 1:04d}")
            ledger["records"][added[-1]] = {"search": search["id"], "file": Path(name).name, **rec}
        ledger["files"].append({"path": str(name), "sha256": digest, "search": search["id"], "format": args.format,
                                "records": len(parsed)})
    return {"search": search["id"], "added": len(added), "ids": f"{added[0]} to {added[-1]}", "exported_in_log": search["exported"],
            "records_of_this_search": sum(1 for r in ledger["records"].values() if r["search"] == search["id"])}, 0


def cmd_dedup(ledger, args, directory):
    for key, pairs in (("merges", args.merge), ("distinct", args.distinct)):
        for a, b in pairs or []:
            if a not in ledger["records"] or b not in ledger["records"]:
                fail(f"no record {a if a not in ledger['records'] else b!r}")
            ledger[key].append({"a": a, "b": b, "reviewer": args.reviewer, "date": now()})
    grp = groups(ledger)
    pairs, size = candidates(ledger, grp), len(set(grp.values()))
    lines = ["# Duplicates", "", f"{len(grp)} records form {size} groups: records with the same DOI, PMID, NCT number or "
             f"corpusId are one record, and {len(ledger['merges'])} merges were confirmed by hand.", "",
             f"Candidate pairs to settle: {len(pairs)} (titles at least {TITLE_SIMILARITY:.0%} similar, years at most {YEAR_GAP} "
             "apart). Settle each with `dedup --merge A B` or `dedup --distinct A B`. Different identifiers of one kind "
             "(two DOIs, two NCT numbers) speak against a duplicate.", "",
             "| A | B | Similarity | Title A | Title B | Years | Different identifiers |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {p['a']} | {p['b']} | {p['similarity']} | {cell(p['titles'][0])} | {cell(p['titles'][1])} | "
              f"{p['years'][0]}, {p['years'][1]} | {', '.join(p['different'])} |" for p in pairs]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "duplicates.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"records": len(grp), "groups": size, "duplicates": len(grp) - size, "candidate_pairs": len(pairs),
            "report": str(directory / "duplicates.md")}, 0


def decision_problem(d: dict, ledger: dict, grp: dict, fin: dict, codes: dict) -> str:
    rid, stage, decision, text = d.get("record"), d.get("stage"), d.get("decision"), lambda k: str(d.get(k) or "").strip()
    checks = (
        (rid in ledger["records"], f"unknown record {rid!r}"),
        (decision in DECISIONS.get(stage, ()), "stage and decision must be pre: remove; ta: include, exclude, unsure; "
                                               "ft: include, exclude, not_retrieved"),
        (text("reviewer"), "reviewer is missing (model, user, or a name)"),
        (decision != "remove" or text("reason"), "a removal needs a reason"),
        (decision != "not_retrieved" or text("note"), "not_retrieved needs a note of what was tried"),
        (decision != "exclude" or d.get("code") in codes, f"the code is not an exclusion code of the protocol ({', '.join(codes)})"),
        (decision != "exclude" or quote_words(d.get("quote")) >= MIN_QUOTE_WORDS,
         f"an exclusion needs a quote of at least {MIN_QUOTE_WORDS} words copied from the record"),
        (decision != "exclude" or stage != "ft" or text("locator"), "a full-text exclusion needs a locator (page or section)"))
    problem = next((message for ok, message in checks if not ok), "")
    if problem or stage == "pre":
        return problem
    if (grp[rid], "pre") in fin:
        return "the record was removed before screening"
    if stage == "ft" and (fin.get((grp[rid], "ta")) or {}).get("decision") not in ("include", "unsure"):
        return "the record was not included at ta, so it has no full-text stage"
    return ""


def cmd_decide(ledger, args, directory):
    if not protocol(ledger):
        fail("record the protocol first with the protocol command")
    codes, grp = exclusion_codes(protocol(ledger)), groups(ledger)
    fin = finals(ledger, grp)
    text = sys.stdin.read() if args.file == "-" else read_bytes(args.file).decode("utf-8-sig")
    accepted, unchanged, rejected, seen = 0, 0, [], {}
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except ValueError:
            d = None
        d = d if isinstance(d, dict) else {"record": None, "not_an_object": True}
        key = (grp.get(d.get("record")), d.get("stage"))
        problem = "not a JSON object" if d.get("not_an_object") else decision_problem(d, ledger, grp, fin, codes)
        problem = problem or (f"line {seen[key]} of this file decides the same record and stage" if key in seen else "")
        if problem:
            rejected.append({"line": n, "record": d.get("record"), "problem": problem})
            continue
        seen[key] = n
        if key in fin and all(fin[key].get(k) == d.get(k) for k in FIELDS):
            unchanged += 1
            continue
        fin[key] = dict({k: d[k] for k in FIELDS if d.get(k) not in (None, "")},
                        protocol_version=len(ledger["protocol_history"]), recorded=now())
        ledger["decisions"].append(fin[key])
        accepted += 1
    return {"accepted": accepted, "unchanged": unchanged, "rejected": rejected}, 1 if rejected else 0


def export_status(search: dict, got: int) -> str:
    exported = got if search.get("exported") is None else search["exported"]
    if search.get("total") is None:
        return "total unknown"
    if exported >= search["total"] or search.get("last_page"):
        return "all exported"
    return "incomplete, explained" if search.get("incomplete_reason") else "incomplete"


def findings(ledger: dict, directory: Path) -> list:
    out, recs, proto = [], ledger["records"], protocol(ledger)

    def add(severity, code, where, detail):
        out.append({"severity": severity, "code": code, "where": where, "detail": detail})

    codes, disk = exclusion_codes(proto), directory / "protocol.json"
    if not proto:
        add("error", "NO_PROTOCOL", "protocol", "record the protocol with the protocol command")
    elif disk.is_file() and {k: v for k, v in read_json(disk).items() if k not in ("version", "recorded")} != proto:
        add("error", "PROTOCOL_CHANGED_UNRECORDED", "protocol.json", "it differs from the recorded protocol: run protocol --amend")
    if not ledger["searches"]:
        add("error", "NO_SEARCHES", "searches", "no search is logged")
    per_search = Counter(r["search"] for r in recs.values())
    for s in ledger["searches"]:
        got, status = per_search[s["id"]], export_status(s, per_search[s["id"]])
        if s.get("exported") is not None and s["exported"] != got:
            add("error", "EXPORT_COUNT_MISMATCH", s["id"], f"the log says {s['exported']} exported, {got} records were added")
        if status == "total unknown":
            add("warning", "SEARCH_TOTAL_UNKNOWN", s["id"], "no total from the source was logged: export completeness unknown")
        elif status.startswith("incomplete"):
            add("warning" if s["incomplete_reason"] else "error", "SEARCH_INCOMPLETE", s["id"], f"fewer exported than the total "
                f"of {s['total']} and the last page not reached: {s['incomplete_reason'] or 'fetch the rest or give a reason'}")
    grp = groups(ledger)
    fin, pairs, members, texts = finals(ledger, grp), candidates(ledger, grp), {}, {}
    if pairs:
        add("error", "DUPLICATE_CANDIDATES_PENDING", "dedup", f"{len(pairs)} candidate pairs, such as {pairs[0]['a']} and "
            f"{pairs[0]['b']}: settle each with dedup --merge or --distinct")
    for rid, c in grp.items():
        members.setdefault(c, []).append(recs[rid])

    def fulltext(rid, canonical, source=None):
        for name in (source, f"fulltext/{rid}.txt", f"fulltext/{canonical}.txt"):
            if name and (directory / name).is_file():
                texts.setdefault(name, joined((directory / name).read_text(encoding="utf-8", errors="replace")))
                return texts[name]
        return None

    earlier = {h["version"]: exclusion_codes(h["protocol"]) for h in ledger["protocol_history"]}
    for c in sorted(members, key=num):
        ta, ft = fin.get((c, "ta")), fin.get((c, "ft"))
        if (c, "pre") in fin:
            continue
        if not ta:
            add("error", "NO_DECISION", c, "reached title-abstract screening without a decision")
        elif ta["decision"] == "exclude" and ft:
            add("error", "NOT_AT_STAGE", c, "a full-text decision for a record excluded at title-abstract")
        elif ta["decision"] != "exclude" and not ft:
            add("error", "STAGE_TRANSFER_LOSS", c, f"{ta['decision']} at title-abstract, no full-text decision")
        for d in [x for x in (ta, ft) if x and x["decision"] == "exclude"]:
            where, ft_text = f"{c} {d['stage']}", d["stage"] == "ft" and fulltext(d["record"], c, d.get("source"))
            if d.get("code") not in codes:
                add("error", "CODE_NOT_IN_PROTOCOL", where, f"{d.get('code')} is not an exclusion code of the current protocol")
            elif earlier.get(d.get("protocol_version"), codes).get(d["code"]) != codes[d["code"]]:
                add("warning", "CODE_CHANGED_SINCE_DECISION", where, f"{d['code']} meant something else when this was decided")
            if d["stage"] == "ta" and not any(r.get("abstract") for r in members[c]):
                add("warning", "EXCLUDED_ON_TITLE_ONLY", where, "no abstract: allowed only when the title clearly fails")
            elif d["stage"] == "ta" and any(joined(r.get("title")) == joined(d.get("quote")) for r in members[c]):
                add("warning", "TITLE_AS_QUOTE", where, "the quote is the whole title: quote the words that show the reason")
            if d["stage"] == "ft" and ft_text is None:
                add("error", "FULLTEXT_MISSING", where, f"no text to check the quote in: save it as fulltext/{c}.txt")
            elif not (contains(ft_text, d.get("quote")) if ft_text else
                      any(contains(joined(r.get(f)), d.get("quote")) for r in members[c] for f in ("title", "abstract"))):
                add("error", "QUOTE_NOT_FOUND", where, f"not in the {'full text' if ft_text else 'title or abstract'}: {d.get('quote')!r}")
    main = {s["id"] for s in ledger["searches"] if s["kind"] != "other"}
    for seed in proto.get("seeds", []):
        ids, title = {"doi": norm_doi(seed.get("doi")), "pmid": seed.get("pmid"), "nct": str(seed.get("nct") or "").upper()}, \
            norm_title(seed.get("title"))
        if not any(r["search"] in main and (any(v and r.get(k) == str(v) for k, v in ids.items())
                                            or similar(title, norm_title(r["title"])) >= TITLE_SIMILARITY) for r in recs.values()):
            add("warning", "SEED_NOT_FOUND", seed.get("doi") or seed.get("pmid") or seed.get("nct") or seed.get("title"),
                "no database or register search found this known paper: search with the words it uses")
    cal = proto.get("calibration") or {}
    scores = [read_json(p) for p in (directory / "calibration").glob("round*-score.json")]
    latest = max(scores, key=lambda s: s.get("round", 0), default=None)
    if proto and cal.get("user_screens") is False:
        add("warning", "MODEL_ONLY_SCREENING", "calibration", f"the user did not screen ({cal.get('declined_reason')}): the "
            "methods and limitations must say that the model screened alone")
    elif proto and latest is None:
        add("error", "CALIBRATION_MISSING", "calibration", "no calibration round was scored (sr_agreement.py sample, score)")
    elif proto and latest.get("status") != "passed":
        add("error", "CALIBRATION_BELOW_THRESHOLD", f"round {latest.get('round')}", f"{latest.get('status')}: revise the "
            "criteria with the user, record the amendment and sample a new round")
    included, shared = {}, {}
    for (c, stage), d in fin.items():
        if stage == "ft" and d["decision"] == "include" and (c, "pre") not in fin:
            included.setdefault(d.get("study") or c, []).append(c)
            for key in {k for r in members[c] for k in (r.get("pmid"), r.get("nct"), *r.get("links", [])) if k}:
                shared.setdefault(key, set()).add(d.get("study") or c)
    for key, studies in shared.items():
        if len(studies) > 1:
            add("warning", "POSSIBLE_SAME_STUDY", key, f"included studies {', '.join(sorted(studies))} share {key}: reports of one "
                "study take the same study label")
    if (directory / "extraction.csv").is_file():
        with open(directory / "extraction.csv", newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            rows, missing = list(reader), [c for c in EXTRACTION if c not in [n.strip().lower() for n in reader.fieldnames or []]]
        if missing:
            add("error", "EXTRACTION_FORMAT", "extraction.csv", "missing columns: " + ", ".join(missing))
        rows = [] if missing else [{k.strip().lower(): (v or "").strip() for k, v in row.items() if k} for row in rows]
        for line, row in enumerate(rows, 2):
            where, study, quote = f"extraction.csv:{line}", row["study"], row["quote"]
            numbers = [w for w in words(quote) if re.fullmatch(r"\d+(?:\.\d+|,\d{3})*", w)]
            if study not in included:
                add("error", "EXTRACTION_STUDY_NOT_INCLUDED", where, f"{study!r} is not an included study")
            elif row["reported_as"].lower() not in REPORTED_AS or (row["design"] or "parallel").lower() not in DESIGNS:
                add("error", "EXTRACTION_FORMAT", where, "reported_as or design is not one of the allowed values")
            elif not any(row[k] for k in ("value", "spread", "low", "high", "events")):
                continue
            elif not row["locator"] or quote_words(quote) < MIN_QUOTE_WORDS:
                add("error", "EXTRACTION_NO_SOURCE", where, "a row with numbers needs a locator and a quote")
            elif not any(t and contains(t, quote) for t in (fulltext(r, r) for r in included[study])):
                add("error", "EXTRACTION_QUOTE_NOT_FOUND", where, f"not in a full text of {study}: {quote!r}")
            elif re.fullmatch(r"[-\u2212]?\d+(\.\d+)?", key := row["value"] or row["events"]) and not any(
                    abs(float(w.replace(",", "")) - float(key.lstrip("-\u2212"))) < 1e-9 for w in numbers):
                add("warning", "EXTRACTION_VALUE_NOT_IN_QUOTE", where, f"{key} is not a number of the quote")
        for study in [] if missing else sorted(set(included) - {r["study"] for r in rows}):
            add("warning", "EXTRACTION_STUDY_MISSING", study, "an included study has no row in extraction.csv")
    return out


def cmd_check(ledger, args, directory):
    found = sorted(findings(ledger, directory), key=lambda f: (f["severity"] != "error", f["code"]))
    errors = sum(1 for f in found if f["severity"] == "error")
    lines = ["# Check", "", f"{errors} errors, {len(found) - errors} warnings. Fix every error; explain each warning in the "
             "report.", "", "| Severity | Finding | Where | Detail |", "|---|---|---|---|"]
    lines += [f"| {f['severity']} | {f['code']} | {cell(f['where'])} | {cell(f['detail'])} |" for f in found]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"errors": errors, "warnings": len(found) - errors, "by_finding": dict(Counter(f["code"] for f in found)),
            "report": str(directory / "check.md")}, 1 if errors else 0


COMMANDS = {"protocol": cmd_protocol, "search": cmd_search, "records": cmd_records, "dedup": cmd_dedup,
            "decide": cmd_decide, "check": cmd_check}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The ledger of a systematic review.")
    parser.add_argument("--dir", default="systematic-review", help="The review's folder (default: systematic-review)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("protocol", help="Check protocol.json and record it")
    p.add_argument("file")
    p.add_argument("--amend", help="What changed, when a protocol is recorded already")
    p.add_argument("--results-seen", choices=("yes", "no"), help="Whether screening results had been seen")
    p = sub.add_parser("search", help="Log one search, or complete a logged one with --id")
    for name in ("id", "source", "interface", "query", "incomplete-reason", "note"):
        p.add_argument(f"--{name}")
    p.add_argument("--kind", choices=KINDS)
    p.add_argument("--date", help="When it ran, in UTC (default: now)")
    p.add_argument("--filter", action="append", help="name=value as sent to the source (repeatable)")
    for name in ("total", "exported", "pages", "round"):
        p.add_argument(f"--{name}", type=int)
    p.add_argument("--last-page", action="store_true", help="The last page of results was fetched")
    p = sub.add_parser("records", help="Add the records of saved results to their search")
    p.add_argument("files", nargs="+")
    p.add_argument("--search", required=True)
    p.add_argument("--format", required=True, choices=PARSERS)
    p = sub.add_parser("dedup", help="Group duplicates, list candidate pairs, settle them")
    p.add_argument("--merge", nargs=2, action="append", metavar=("A", "B"))
    p.add_argument("--distinct", nargs=2, action="append", metavar=("A", "B"))
    p.add_argument("--reviewer", default="model", help="Who settled the pairs (default: model)")
    sub.add_parser("decide", help="Record decisions from a JSON-lines file (- for standard input)").add_argument("file")
    sub.add_parser("check", help="Check every rule; write check.md")
    args = parser.parse_args(argv)
    directory = Path(args.dir)
    ledger = load(directory)
    result, code = COMMANDS[args.command](ledger, args, directory)
    if args.command in ("protocol", "search", "records", "dedup", "decide"):
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "ledger.json.tmp"
        temporary.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(directory / "ledger.json")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
