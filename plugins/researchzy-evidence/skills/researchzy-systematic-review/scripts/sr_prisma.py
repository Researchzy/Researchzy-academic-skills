#!/usr/bin/env python3
"""The PRISMA 2020 flow of a systematic review, computed from the ledger that sr_ledger.py keeps.

  sr_prisma.py [--svg] [--round 2] [--previous-studies N --previous-reports M]

Every count comes from the per-record ledger: records identified per source, duplicates removed, records
removed for other reasons, records screened and excluded (per code), reports sought, not retrieved,
assessed and excluded (per code), and the studies and reports included. Each of six identities is OK
(both sides known and equal), FAIL (known and different) or NOT_ASSESSED (a side unknown); a check that
was not made is never OK. --round counts the records of one search round, so that an update shows the
previous version's studies and reports beside the new ones; --previous-studies and --previous-reports
add a previous version kept outside this ledger. The registration sentence compares the registration
date with the first database or register search.

Writes prisma.md (counts, identities, final decisions by reviewer, the full-text reports excluded and
included, the search table), prisma.json and, with --svg, prisma.svg.

Takes --dir (default systematic-review). Standard library only. Exit codes: 0 done; 1 an identity fails;
2 the ledger cannot be read.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import textwrap
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sr_ledger as sl  # noqa: E402


def identity(name: str, left, right, op: str = "=") -> dict:
    status = "NOT_ASSESSED" if left is None or right is None else "OK" if (left == right if op == "=" else left <= right) else "FAIL"
    return {"identity": name, "left": left, "right": right, "status": status}


def registration(proto: dict, ledger: dict) -> str:
    reg = proto.get("registration") or {}
    first = min((s["date"][:10] for s in ledger["searches"] if s["kind"] != "other" and s.get("round", 1) == 1), default=None)
    if reg.get("status") != "registered":
        return "The protocol was not registered" + (" (registration is planned)." if reg.get("status") == "planned" else ".")
    where = f"with {reg['registry']} ({reg['id']}) on {reg['date']}"
    if first is None:
        return f"The protocol was registered {where}; no search is logged, so its timing cannot be stated."
    if reg["date"] < first:
        return f"The protocol was prospectively registered {where}, before the first search on {first}."
    return f"The protocol was registered {where}, {'the day of' if reg['date'] == first else 'after'} the first search on {first}."


def flow(ledger: dict, rnd: int, ext_studies, ext_reports) -> dict:
    recs, grp, proto = ledger["records"], sl.groups(ledger), sl.protocol(ledger)
    fin, rounds, first = sl.finals(ledger, grp), {s["id"]: s.get("round", 1) for s in ledger["searches"]}, {}
    for rid, c in grp.items():
        first[c] = min(first.get(c, 10 ** 6), rounds[recs[rid]["search"]])
    rows = [rid for rid in recs if rounds[recs[rid]["search"]] == rnd]
    new = sorted({grp[r] for r in rows if first[grp[r]] == rnd}, key=sl.num)

    def dec(c, stage):
        return (fin.get((c, stage)) or {}).get("decision")

    def study(c):
        return fin[(c, "ft")].get("study") or c

    removed = [c for c in new if dec(c, "pre") == "remove"]
    screened = [c for c in new if dec(c, "pre") != "remove"]
    ta_out = [c for c in screened if dec(c, "ta") == "exclude"]
    sought = [c for c in screened if dec(c, "ta") in ("include", "unsure")]
    missing = [c for c in sought if dec(c, "ft") == "not_retrieved"]
    assessed = [c for c in sought if dec(c, "ft") in ("include", "exclude")]
    ft_out, included = [c for c in assessed if dec(c, "ft") == "exclude"], [c for c in assessed if dec(c, "ft") == "include"]
    old = [c for c in set(grp.values()) if first[c] < rnd and dec(c, "ft") == "include" and dec(c, "ta") != "exclude"]
    old_studies = {study(c) for c in old}
    added = {s for s in {study(c) for c in included} - old_studies if not s.startswith("previous:")}
    prev_s = None if ext_studies is None and ext_reports is not None else len(old_studies) + (ext_studies or 0)
    prev_r = None if ext_reports is None and ext_studies is not None else len(old) + (ext_reports or 0)
    total_s, total_r = (None if prev_s is None else prev_s + len(added)), (None if prev_r is None else prev_r + len(included))
    order = proto.get("exclusion_order", [])

    def reasons(ids, stage):
        counts = Counter(fin[(c, stage)].get("code") for c in ids)
        return {k: counts[k] for k in sorted(counts, key=lambda k: (order.index(k) if k in order else len(order), str(k)))}

    searches = [s for s in ledger["searches"] if s.get("round", 1) == rnd]
    per_search = Counter(recs[r]["search"] for r in rows)
    by_source = Counter()
    for s in searches:
        by_source[(sl.KINDS.index(s["kind"]), s["kind"], s["source"])] += per_search[s["id"]]
    exported = sum(per_search[s["id"]] if s.get("exported") is None else s["exported"] for s in searches)
    return {
        "round": rnd, "dates": [min((s["date"] for s in searches), default=""), max((s["date"] for s in searches), default="")],
        "identification": [{"kind": k, "source": s, "records": n} for (_, k, s), n in sorted(by_source.items())],
        "records_identified": len(rows), "duplicates_removed": len(rows) - len(new), "removed_other_reasons": len(removed),
        "records_screened": len(screened), "records_excluded": len(ta_out), "records_excluded_by_code": reasons(ta_out, "ta"),
        "reports_sought": len(sought), "reports_not_retrieved": len(missing), "reports_assessed": len(assessed),
        "reports_excluded": len(ft_out), "reports_excluded_by_code": reasons(ft_out, "ft"),
        "studies_included": len(added), "reports_included": len(included), "total": {"studies": total_s, "reports": total_r},
        "previous": {"studies": prev_s, "reports": prev_r} if rnd > 1 or {ext_studies, ext_reports} != {None} else None,
        "screened_by": {st: dict(Counter(fin[(c, st)].get("reviewer") for c in ids if (c, st) in fin))
                        for st, ids in (("ta", screened), ("ft", sought))},
        "identities": [
            identity("records identified - duplicates removed - removed for other reasons = records screened",
                     len(rows) - (len(rows) - len(new)) - len(removed), len(screened)),
            identity("records screened - records excluded = reports sought for retrieval", len(screened) - len(ta_out), len(sought)),
            identity("reports sought - reports not retrieved = reports assessed", len(sought) - len(missing), len(assessed)),
            identity("reports assessed - reports excluded = reports included", len(assessed) - len(ft_out), len(included)),
            identity("records identified = records exported, by the search log", len(rows), exported),
            identity("studies included <= reports of included studies", total_s, total_r, "<=")],
        "registration": registration(proto, ledger),
        "excluded_reports": [[c, recs[c]["title"], fin[(c, "ft")].get("code"), fin[(c, "ft")].get("locator")] for c in ft_out],
        "included_reports": [[study(c), c, recs[c]["title"], recs[c].get("year")] for c in included],
        "searches": [dict(s, records=per_search[s["id"]], export=sl.export_status(s, per_search[s["id"]])) for s in searches]}


def svg(f: dict, labels: dict) -> str:
    def n(value) -> str:                    # no-break spaces keep a count on the line of its label
        return f"(n\u00a0=\u00a0{value})"

    def reasons(counts):
        return [f"{code} {labels.get(code, '')} {n(k)}" for code, k in counts.items()]

    new, prev, total = "new " if f["previous"] else "", f["previous"] or {}, f["total"]
    rows = [([f"Studies included in previous version {n(prev['studies'])}",
              f"Reports of studies included in previous version {n(prev['reports'])}"], [], False)] if prev else []
    rows += [(["Records identified from:"] + [f"{i['source']} ({i['kind']}) {n(i['records'])}" for i in f["identification"]],
              ["Records removed before screening:", f"Duplicate records {n(f['duplicates_removed'])}",
               f"Removed for other reasons {n(f['removed_other_reasons'])}"], True),
             ([f"Records screened {n(f['records_screened'])}"],
              [f"Records excluded {n(f['records_excluded'])}"] + reasons(f["records_excluded_by_code"]), True),
             ([f"Reports sought for retrieval {n(f['reports_sought'])}"], [f"Reports not retrieved {n(f['reports_not_retrieved'])}"], True),
             ([f"Reports assessed for eligibility {n(f['reports_assessed'])}"],
              [f"Reports excluded {n(f['reports_excluded'])}"] + reasons(f["reports_excluded_by_code"]), True),
             ([f"{'New studies' if new else 'Studies'} included in review {n(f['studies_included'])}",
               f"Reports of {new}included studies {n(f['reports_included'])}"] + (
                 [f"Total studies included in review {n(total['studies'])}", f"Reports of total included studies {n(total['reports'])}"]
                 if prev else []), [], False)]
    out, y = [], 20
    for left, right, arrow in rows:
        left, right = ([w for line in side for w in textwrap.wrap(line, width)] for side, width in ((left, 50), (right, 42)))
        h, mid = 16 * max(len(left), len(right)) + 14, y + (16 * max(len(left), len(right)) + 14) // 2
        for x, width, lines in ((20, 340, left), (400, 300, right)):
            if lines:
                out.append(f'<rect x="{x}" y="{y}" width="{width}" height="{h}" fill="white" stroke="black"/>' + "".join(
                    f'<text x="{x + 8}" y="{y + 20 + 16 * i}">{html.escape(t)}</text>' for i, t in enumerate(lines)))
        if right:                           # arrowheads as triangles: not every program draws SVG markers
            out.append(f'<path d="M360,{mid} H392 M392,{mid - 4} L400,{mid} L392,{mid + 4} Z" stroke="black"/>')
        if arrow:
            out.append(f'<path d="M190,{y + h} V{y + h + 22} M186,{y + h + 22} L190,{y + h + 30} L194,{y + h + 22} Z" stroke="black"/>')
        y += h + 30
    return "\n".join([f'<svg xmlns="http://www.w3.org/2000/svg" width="720" height="{y}" viewBox="0 0 720 {y}" '
                      'font-family="Helvetica, Arial, sans-serif" font-size="12">', '<rect width="100%" height="100%" fill="white"/>',
                      *out, "</svg>"]) + "\n"


def markdown(f: dict, labels: dict) -> str:
    cell, new = sl.cell, " (new)" if f["previous"] else ""
    rows = [(f"Records identified: {i['source']} ({i['kind']})", i["records"]) for i in f["identification"]]
    rows += [("Duplicate records removed" + (" (with records screened in an earlier round)" if f["round"] > 1 else ""),
              f["duplicates_removed"]), ("Records removed for other reasons", f["removed_other_reasons"]),
             ("Records screened", f["records_screened"]), ("Records excluded", f["records_excluded"])]
    rows += [(f"- {k} {labels.get(k, '(not in the protocol)')}", n) for k, n in f["records_excluded_by_code"].items()]
    rows += [("Reports sought for retrieval", f["reports_sought"]), ("Reports not retrieved", f["reports_not_retrieved"]),
             ("Reports assessed for eligibility", f["reports_assessed"]), ("Reports excluded", f["reports_excluded"])]
    rows += [(f"- {k} {labels.get(k, '(not in the protocol)')}", n) for k, n in f["reports_excluded_by_code"].items()]
    rows += [(f"Studies included{new}", f["studies_included"]), (f"Reports of included studies{new}", f["reports_included"])]
    if f["previous"]:
        rows += [("Studies included in the previous version", f["previous"]["studies"]), ("Reports of studies included in the "
                 "previous version", f["previous"]["reports"]), ("Total studies included", f["total"]["studies"]),
                 ("Reports of total included studies", f["total"]["reports"])]
    lines = ["# PRISMA 2020 flow", "", f["registration"], "", f"Round {f['round']}; searches run from {f['dates'][0][:10]} to "
             f"{f['dates'][1][:10]} (UTC). Every count is computed from ledger.json.", "", "| Box | n |", "|---|---|",
             *[f"| {cell(a)} | {'not available' if b is None else b} |" for a, b in rows],
             "", "## Identities", "", "| Identity | Left | Right | Status |", "|---|---|---|---|",
             *[f"| {i['identity']} | {i['left']} | {i['right']} | {i['status']} |" for i in f["identities"]],
             "", "## Final decisions by reviewer", "", "| Stage | Reviewer | Records |", "|---|---|---|",
             *[f"| {st} | {cell(who)} | {n} |" for st, by in f["screened_by"].items() for who, n in by.items()],
             "", "## Full-text reports excluded", "", "| Record | Title | Code | Locator |", "|---|---|---|---|",
             *["| " + " | ".join(cell(v) for v in row) + " |" for row in f["excluded_reports"]],
             "", "## Reports of included studies", "", "| Study | Record | Title | Year |", "|---|---|---|---|",
             *["| " + " | ".join(cell(v) for v in row) + " |" for row in f["included_reports"]],
             "", "## Searches", "", "| Search | Source | Kind | Interface | Date (UTC) | Query | Filters | Total | Exported | "
             "Pages | Export |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    lines += ["| " + " | ".join(cell(v) for v in (s["id"], s["source"], s["kind"], s["interface"], s["date"], f"`{s['query']}`",
              ", ".join(f"{k}={v}" for k, v in s["filters"].items()), s["total"], s["records"], s["pages"],
              s["export"] + (f": {s['incomplete_reason']}" if s["incomplete_reason"] else "") + (f" ({s['note']})" if s["note"] else "")))
              + " |" for s in f["searches"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The PRISMA 2020 flow of a systematic review, from its ledger.")
    parser.add_argument("--dir", default="systematic-review", help="The review's folder (default: systematic-review)")
    parser.add_argument("--svg", action="store_true", help="Also draw prisma.svg")
    parser.add_argument("--round", type=int, help="The search round to count (default: the latest)")
    parser.add_argument("--previous-studies", type=int, help="Studies of a previous version kept outside this ledger")
    parser.add_argument("--previous-reports", type=int, help="Reports of a previous version kept outside this ledger")
    args = parser.parse_args(argv)
    directory = Path(args.dir)
    if not (directory / "ledger.json").exists():
        print(f"sr_prisma: no ledger in {directory}: run sr_ledger.py first", file=sys.stderr)
        raise SystemExit(2)
    ledger = sl.load(directory)
    rnd = args.round or max((s.get("round", 1) for s in ledger["searches"]), default=1)
    f, labels = flow(ledger, rnd, args.previous_studies, args.previous_reports), sl.exclusion_codes(sl.protocol(ledger))
    (directory / "prisma.md").write_text(markdown(f, labels), encoding="utf-8")
    (directory / "prisma.json").write_text(json.dumps(f, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.svg:
        (directory / "prisma.svg").write_text(svg(f, labels), encoding="utf-8")
    failed = [i["identity"] for i in f["identities"] if i["status"] == "FAIL"]
    print(json.dumps({"round": rnd, "records_identified": f["records_identified"], "records_screened": f["records_screened"],
                      "reports_assessed": f["reports_assessed"], "studies_included": f["studies_included"],
                      "reports_included": f["reports_included"], "identities_failed": failed,
                      "not_assessed": [i["identity"] for i in f["identities"] if i["status"] == "NOT_ASSESSED"],
                      "files": [str(directory / n) for n in ("prisma.md", "prisma.json", "prisma.svg")[:3 if args.svg else 2]]},
                     indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
