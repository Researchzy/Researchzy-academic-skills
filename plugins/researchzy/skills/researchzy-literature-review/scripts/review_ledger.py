#!/usr/bin/env python3
"""The ledger of a literature review: what was searched, what was found, what was kept and why.

The agent searches and reads; this script keeps the books, so that the review's counts add up,
every cited paper is one the index returned, and the review can be resumed or updated later.

  review_ledger.py brief --topic "…" --question "…" --question "…" --scope "…" --criteria "…"
  review_ledger.py search --query '"sleep deprivation" memory' --total 412 --pass relevance
  review_ledger.py add results.json --search s1        papers a search returned (JSON as returned)
  review_ledger.py add seeds.json --seed               papers the user named
  review_ledger.py decide 123 456 --exclude --reason "animal study"
  review_ledger.py decide 789 --include --core
  review_ledger.py read 789 --depth full_text --source sources/789.pdf
  review_ledger.py extract extraction.json             {"789": {"method": "…", "result": "…"}}
  review_ledger.py status                              counts and what is still missing
  review_ledger.py export                              papers.csv, references.bib, search-log.md
  review_ledger.py check review.md                     every citation is an included paper

All commands take --dir (default: literature-review). Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

PASSES = ("library", "relevance", "foundational", "recent", "reviews", "contrary", "chain", "other")
# The passes a review is expected to run; `status` names the ones it has not, so that the
# review's limitations can say so.
EXPECTED_PASSES = ("relevance", "foundational", "recent", "reviews", "contrary")
DEPTHS = ("none", "metadata", "abstract", "full_text")
EXTRACT_FIELDS = ("theme", "question", "method", "data", "result", "limits", "relation", "locator")
PAPER_FIELDS = ("corpusId", "title", "authors", "authorCount", "year", "venue", "doi", "arxiv",
                "citationCount", "hasReadablePdf", "readerUrl")
STOPWORDS = frozenset("a an the of in on to for and or by with at as is are from into via using toward towards".split())
CITE_RE = re.compile(r"(?<![\w.@\\])@([A-Za-z][\w-]*)")


def load(directory: Path) -> dict:
    path = directory / "ledger.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"tool": "researchzy-literature-review", "schema_version": 1,
            "brief": {"topic": "", "questions": [], "scope": "", "criteria": "", "size": "full"},
            "searches": [], "papers": {}}


def save(directory: Path, ledger: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ledger.json").write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")


def ascii_word(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def author_names(paper: dict) -> list:
    names = [a.get("name", "") if isinstance(a, dict) else str(a) for a in paper.get("authors") or []]
    return [re.sub(r"\s+", " ", n).strip() for n in names if n and str(n).strip()]


def family_name(name: str) -> str:
    """The family name of "First Last" or "Last, First"."""
    if "," in name:
        return name.split(",", 1)[0].strip()
    return name.split()[-1] if name.split() else ""


def make_key(paper: dict, taken: set) -> str:
    """A citation key: first author's family name, year, first content word of the title."""
    names = author_names(paper)
    first = ascii_word(family_name(names[0])) if names else ""
    word = next((ascii_word(w) for w in re.findall(r"[^\W\d_]+", paper.get("title") or "")
                 if w.lower() not in STOPWORDS and len(ascii_word(w)) > 2), "")
    base = f"{first or 'anon'}{paper.get('year') or ''}{word}" or "paper"
    key, n = base, 0
    while key in taken:
        n += 1
        key = f"{base}{chr(96 + n) if n <= 26 else n}"
    return key


def paper_id(paper: dict) -> str:
    if paper.get("corpusId") not in (None, ""):
        return str(paper["corpusId"])
    basis = (paper.get("doi") or paper.get("arxiv") or paper.get("title") or "").lower()
    return "x" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:8]


def find(ledger: dict, ref: str) -> str:
    """A paper's id from its corpusId or its citation key."""
    if ref in ledger["papers"]:
        return ref
    for pid, paper in ledger["papers"].items():
        if paper.get("key") == ref:
            return pid
    raise SystemExit(f"No paper {ref!r} in the ledger. Add it first.")


def read_json(source: str):
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    return json.loads(text)


# ---------------------------------------------------------------------------------------------
# Commands


def cmd_brief(ledger: dict, args) -> dict:
    brief = ledger["brief"]
    for name in ("topic", "scope", "criteria", "size"):
        if getattr(args, name) is not None:
            brief[name] = getattr(args, name)
    if args.question:
        brief["questions"] = args.question
    return {"brief": brief}


def cmd_search(ledger: dict, args) -> dict:
    filters = {}
    for item in args.filter or []:
        if "=" not in item:
            raise SystemExit(f"--filter takes name=value, got {item!r}")
        name, value = item.split("=", 1)
        filters[name.strip()] = value.strip()
    search = {"id": f"s{len(ledger['searches']) + 1}", "pass": args.search_pass, "question": args.question,
              "tool": args.tool, "query": args.query, "sort": args.sort, "filters": filters,
              "total": args.total, "fetched": args.fetched, "added": 0, "note": args.note or ""}
    ledger["searches"].append(search)
    return {"search": search["id"]}


def cmd_add(ledger: dict, args) -> dict:
    data = read_json(args.file)
    if isinstance(data, dict):
        data = data.get("papers") or data.get("results") or data.get("items") or [data]
    search = None
    if args.search:
        search = next((s for s in ledger["searches"] if s["id"] == args.search), None)
        if search is None:
            raise SystemExit(f"No search {args.search!r}. Log it first with the search command.")
    taken = {p.get("key") for p in ledger["papers"].values()}
    new = already = 0
    for raw in data:
        if not isinstance(raw, dict) or not (raw.get("title") or raw.get("corpusId")):
            continue
        pid = paper_id(raw)
        paper = ledger["papers"].get(pid)
        if paper is None:
            paper = {name: raw.get(name) for name in PAPER_FIELDS if raw.get(name) not in (None, "", [])}
            paper["authors"] = author_names(raw)
            paper.setdefault("authorCount", len(paper["authors"]))
            paper.update({"hasAbstract": bool(raw.get("abstract") or raw.get("abstractText") or raw.get("hasAbstract")),
                          "found_by": [], "seed": False, "in_library": False, "decision": "candidate",
                          "reason": "", "core": False, "read": "none", "source": "", "extract": {}})
            paper["key"] = make_key(paper, taken)
            taken.add(paper["key"])
            ledger["papers"][pid] = paper
            new += 1
            if search:
                search["added"] += 1
        else:
            already += 1
            for name in PAPER_FIELDS:  # a later, fuller record fills what an earlier brief one lacked
                if paper.get(name) in (None, "", []) and raw.get(name) not in (None, "", []):
                    paper[name] = raw[name]
            if len(author_names(raw)) > len(paper.get("authors") or []):
                paper["authors"] = author_names(raw)
            paper["hasAbstract"] = paper.get("hasAbstract") or bool(raw.get("abstract") or raw.get("abstractText"))
        if search and search["id"] not in paper["found_by"]:
            paper["found_by"].append(search["id"])
        paper["seed"] = paper["seed"] or args.seed
        paper["in_library"] = paper["in_library"] or args.library
    if search and search.get("fetched") is None:
        search["fetched"] = new + already
    return {"new": new, "already_in_ledger": already, "papers": len(ledger["papers"])}


def cmd_decide(ledger: dict, args) -> dict:
    decision = "included" if args.include else "excluded" if args.exclude else "candidate"
    if decision == "excluded" and not args.reason:
        raise SystemExit("An exclusion needs --reason.")
    for ref in args.papers:
        paper = ledger["papers"][find(ledger, ref)]
        paper["decision"], paper["reason"] = decision, args.reason or ""
        paper["core"] = bool(args.core) if decision == "included" else False
    return {"decided": len(args.papers), "decision": decision}


def cmd_read(ledger: dict, args) -> dict:
    paper = ledger["papers"][find(ledger, args.paper)]
    paper["read"] = args.depth
    if args.source:
        paper["source"] = args.source
    return {"paper": paper["key"], "read": paper["read"]}


def cmd_extract(ledger: dict, args) -> dict:
    if len(args.items) == 1 and "=" not in args.items[0]:
        rows = read_json(args.items[0])
    else:
        fields = dict(item.split("=", 1) for item in args.items[1:] if "=" in item)
        rows = {args.items[0]: fields}
    for ref, fields in rows.items():
        paper = ledger["papers"][find(ledger, str(ref))]
        paper["extract"].update({k: str(v).strip() for k, v in fields.items() if str(v).strip()})
    return {"extracted": len(rows)}


def summary(ledger: dict) -> dict:
    papers = list(ledger["papers"].values())
    included = [p for p in papers if p["decision"] == "included"]
    excluded = [p for p in papers if p["decision"] == "excluded"]
    reasons: dict = {}
    for p in excluded:
        reasons[p["reason"]] = reasons.get(p["reason"], 0) + 1
    depth = {d: sum(1 for p in included if p["read"] == d) for d in DEPTHS}
    seeds = [p for p in papers if p["seed"]]
    return {
        "searches": len(ledger["searches"]),
        "results_reported": sum(s.get("total") or 0 for s in ledger["searches"]),
        "results_looked_at": sum(s.get("fetched") or 0 for s in ledger["searches"]),
        "papers": len(papers),
        "undecided": sum(1 for p in papers if p["decision"] == "candidate"),
        "included": len(included),
        "core": sum(1 for p in included if p["core"]),
        "excluded": len(excluded),
        "excluded_by_reason": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "included_read": depth,
        "from_library": sum(1 for p in included if p["in_library"]),
        "seeds": len(seeds),
        "seeds_not_found_by_any_search": [p["key"] for p in seeds if not p["found_by"]],
        "included_without_extraction": [p["key"] for p in included if not p["extract"]],
        "included_not_read": [p["key"] for p in included if p["read"] in ("none", "metadata")],
        "core_not_read_in_full": [p["key"] for p in included if p["core"] and p["read"] != "full_text"],
        "passes_run": sorted({s["pass"] for s in ledger["searches"]}),
        "passes_not_run": [name for name in EXPECTED_PASSES if name not in {s["pass"] for s in ledger["searches"]}],
    }


def flow_sentence(s: dict) -> str:
    reasons = "; ".join(f"{reason or 'no reason given'}: {n}" for reason, n in s["excluded_by_reason"].items())
    read = s["included_read"]
    return (f"{s['searches']} searches reported {s['results_reported']} results, of which "
            f"{s['results_looked_at']} were looked at. They gave {s['papers']} distinct papers: "
            f"{s['included']} included ({s['core']} core), {s['excluded']} excluded"
            + (f" ({reasons})" if reasons else "") + f", {s['undecided']} undecided. "
            f"Of the included papers, {read['full_text']} were read in full, {read['abstract']} from "
            f"the abstract, and {read['metadata'] + read['none']} were not read.")


def cmd_status(ledger: dict, args) -> dict:
    s = summary(ledger)
    s["flow"] = flow_sentence(s)
    return s


def bibtex(paper: dict) -> str:
    def esc(text) -> str:
        return re.sub(r"([&%#_])", r"\\\1", str(text))

    names = list(paper.get("authors") or [])
    if (paper.get("authorCount") or 0) > len(names) and names:
        names.append("others")
    fields = [("title", "{" + esc(paper.get("title", "")) + "}"), ("author", " and ".join(esc(n) for n in names)),
              ("year", paper.get("year") or "")]
    if paper.get("venue"):
        fields.append(("journal", esc(paper["venue"])))
    if paper.get("doi"):
        fields.append(("doi", paper["doi"]))
    if paper.get("arxiv"):
        fields += [("eprint", paper["arxiv"]), ("archivePrefix", "arXiv")]
    kind = "article" if paper.get("venue") else "misc"
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields if value not in ("", None))
    return f"@{kind}{{{paper['key']},\n{body}\n}}"


def cmd_export(ledger: dict, args) -> dict:
    directory = Path(args.dir)
    included = sorted((p for p in ledger["papers"].values() if p["decision"] == "included"),
                      key=lambda p: (not p["core"], -(p.get("citationCount") or 0), p["key"]))
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["key", "corpusId", "title", "authors", "year", "venue", "doi", "arxiv", "citations",
                     "core", "read", "in_library", "seed", *EXTRACT_FIELDS, "readerUrl"])
    for p in included:
        names = p.get("authors") or []
        shown = ", ".join(names[:3]) + (" et al." if (p.get("authorCount") or len(names)) > 3 else "")
        writer.writerow([p["key"], p.get("corpusId", ""), p.get("title", ""), shown, p.get("year", ""),
                         p.get("venue", ""), p.get("doi", ""), p.get("arxiv", ""), p.get("citationCount", ""),
                         "yes" if p["core"] else "", p["read"], "yes" if p["in_library"] else "",
                         "yes" if p["seed"] else "", *[p["extract"].get(f, "") for f in EXTRACT_FIELDS],
                         p.get("readerUrl", "")])
    (directory / "papers.csv").write_text(out.getvalue(), encoding="utf-8")
    (directory / "references.bib").write_text("\n\n".join(bibtex(p) for p in included) + "\n", encoding="utf-8")

    def cell(value) -> str:
        return re.sub(r"\s+", " ", str(value if value is not None else "")).replace("|", "/")

    lines = ["# Search log", "", flow_sentence(summary(ledger)), "",
             "| Search | Pass | Question | Query | Sort | Filters | Results reported | Looked at | New papers | Note |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for s in ledger["searches"]:
        filters = ", ".join(f"{k}={v}" for k, v in s["filters"].items())
        lines.append("| " + " | ".join(cell(v) for v in (
            s["id"], s["pass"], s.get("question"), f"`{s['query']}`", s.get("sort") or "relevance", filters,
            s.get("total"), s.get("fetched"), s["added"], s.get("note"))) + " |")
    (directory / "search-log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"included": len(included), "files": [str(directory / n) for n in ("papers.csv", "references.bib", "search-log.md")]}


def cmd_check(ledger: dict, args) -> dict:
    text = Path(args.review).read_text(encoding="utf-8")
    by_key = {p["key"]: p for p in ledger["papers"].values()}
    cited = []
    for key in CITE_RE.findall(text):
        key = key.rstrip("-")
        if key not in cited:
            cited.append(key)
    unknown = [k for k in cited if k not in by_key]
    not_included = [k for k in cited if k in by_key and by_key[k]["decision"] != "included"]
    good = [k for k in cited if k in by_key and by_key[k]["decision"] == "included"]
    result = {
        "citations": len(cited),
        "not_in_ledger": unknown,
        "not_included": not_included,
        "cited_but_not_read": [k for k in good if by_key[k]["read"] in ("none", "metadata")],
        "cited_from_abstract_only": [k for k in good if by_key[k]["read"] == "abstract"],
        "not_from_the_index": [k for k in good if by_key[k].get("corpusId") in (None, "")],
        "included_but_never_cited": sorted(p["key"] for p in ledger["papers"].values()
                                           if p["decision"] == "included" and p["key"] not in cited),
    }
    result["ok"] = not (unknown or not_included or result["cited_but_not_read"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="The ledger of a literature review.")
    parser.add_argument("--dir", default="literature-review", help="The review's folder (default: literature-review)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("brief", help="Record the review's questions, scope and criteria")
    p.add_argument("--topic")
    p.add_argument("--question", action="append", help="An answerable question (repeat for each)")
    p.add_argument("--scope")
    p.add_argument("--criteria")
    p.add_argument("--size", choices=("quick", "full"))

    p = sub.add_parser("search", help="Log one search")
    p.add_argument("--query", required=True)
    p.add_argument("--total", type=int, help="How many results the tool reported in all")
    p.add_argument("--fetched", type=int, help="How many of them were looked at")
    p.add_argument("--sort")
    p.add_argument("--filter", action="append", help="name=value, e.g. yearFrom=2020 (repeatable)")
    p.add_argument("--pass", dest="search_pass", choices=PASSES, default="relevance")
    p.add_argument("--question", type=int, help="Which question of the brief this search serves")
    p.add_argument("--tool", default="search_papers")
    p.add_argument("--note")

    p = sub.add_parser("add", help="Add the papers a search returned (a JSON file, or - for standard input)")
    p.add_argument("file")
    p.add_argument("--search", help="The search that returned them")
    p.add_argument("--seed", action="store_true", help="Papers the user named at the start")
    p.add_argument("--library", action="store_true", help="Papers from the user's library")

    p = sub.add_parser("decide", help="Include or exclude papers")
    p.add_argument("papers", nargs="+", help="corpusId or citation key")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--include", action="store_true")
    group.add_argument("--exclude", action="store_true")
    group.add_argument("--candidate", action="store_true", help="Back to undecided")
    p.add_argument("--reason", help="Required for an exclusion")
    p.add_argument("--core", action="store_true", help="One of the papers to read in full")

    p = sub.add_parser("read", help="Record how far a paper was read")
    p.add_argument("paper")
    p.add_argument("--depth", required=True, choices=DEPTHS)
    p.add_argument("--source", help="The file that was read")

    p = sub.add_parser("extract", help="Record what was extracted: a JSON file, or ID field=value …")
    p.add_argument("items", nargs="+")

    sub.add_parser("status", help="Counts, and what is still missing")
    sub.add_parser("export", help="Write papers.csv, references.bib and search-log.md")

    p = sub.add_parser("check", help="Check that every [@key] in the review is an included paper")
    p.add_argument("review")

    args = parser.parse_args()
    directory = Path(args.dir)
    directory.mkdir(parents=True, exist_ok=True)
    ledger = load(directory)
    result = {"brief": cmd_brief, "search": cmd_search, "add": cmd_add, "decide": cmd_decide, "read": cmd_read,
              "extract": cmd_extract, "status": cmd_status, "export": cmd_export, "check": cmd_check}[args.command](ledger, args)
    if args.command not in ("status", "check"):
        save(directory, ledger)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if args.command == "check" and not result["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
