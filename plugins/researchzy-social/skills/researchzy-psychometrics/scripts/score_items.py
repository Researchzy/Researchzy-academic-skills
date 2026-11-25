#!/usr/bin/env python3
"""Score questionnaire items from the declared item map, and find keying problems in the data.

  score_items.py psychometrics/items.json                     the data file named in items.json
  score_items.py psychometrics/items.json --data survey.sav   a .sav file is read with pyreadstat
  score_items.py psychometrics/items.json --few-categories 4

items.json (references/item-map-and-scoring.md) declares each construct's items, its reverse-keyed
items, the lowest and highest response, the missing-value codes and whether the reverse items are
already reversed in the data file. The data file is never changed. In the folder of items.json the
script writes:

  <data>.scored.csv   a copy with missing codes emptied in every column and each declared reverse
                      item scored as (min + max) - x, unless reversed_in_data is true
  scoring.json        SHA-256 of the data, items.json and the copy; per construct the complete n,
                      alpha and each item's item-rest r before and after scoring; problems; leads
  scoring.md          the same as tables

Problems (exit code 1): a value outside [min, max] that is not a missing code, or not a number; an
item with one value only. Leads never fail; show each to the user: an item whose item-rest r is
negative after scoring, declared reverse or not (a reverse-worded item missing from "reverse", a
wrong key, an item reversed twice); a negative alpha; items that use fewer response categories than
--few-categories (a convention, default 5: the ordinal decision must be stated); value labels whose
end points run the other way from the construct's first item (.sav); an item map without a
"confirmed" date.

A .sav file is read with pyreadstat when it is installed, with its value labels and user-missing
values; otherwise export it as CSV. Standard library otherwise. Exit code 2 when an input cannot be
read or items.json is not in the format of the reference.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

NA = frozenset({"", "na", "n/a", "nan", "null", "none", "#n/a", "."})
LICENCES = ("licensed", "open", "unknown")
CAP = 10                      # leads of one kind listed before "and N more"


def fail(message: str):
    print(f"score_items: {message}", file=sys.stderr)
    raise SystemExit(2)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell(value) -> str:
    """A value as text: 2.0 as "2", a missing value as ""."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def number(text: str):
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def read_data(path: Path) -> tuple:
    """(header, rows of text, user-missing ranges per column, value labels per column)."""
    if not path.is_file():
        fail(f"no such data file: {path}")
    if path.suffix.lower() == ".sav":
        try:
            import pyreadstat
        except ImportError:
            fail(f"reading {path.name} needs pyreadstat: ask the user to export the file as CSV, or to agree to "
                 "installing it (python3 -m pip install --user pyreadstat)")
        try:
            frame, meta = pyreadstat.read_sav(str(path), user_missing=True)
        except Exception as exc:                     # pyreadstat raises its own error types
            fail(f"could not read {path}: {exc}")
        ranges = {c: [(r["lo"], r["hi"]) for r in rs] for c, rs in (meta.missing_ranges or {}).items()}
        for column, values in (meta.missing_user_values or {}).items():
            ranges.setdefault(column, []).extend((v, v) for v in values)
        rows = [[cell(v) for v in row] for row in frame.itertuples(index=False)]
        return [str(c) for c in frame.columns], rows, ranges, meta.variable_value_labels or {}
    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")
    first = content.split("\n", 1)[0]
    delimiter = "\t" if path.suffix.lower() in (".tsv", ".tab") else max(",;\t|", key=first.count)
    rows = [row for row in csv.reader(content.splitlines(), delimiter=delimiter) if any(c.strip() for c in row)]
    if len(rows) < 2:
        fail(f"{path} has no data rows under its header")
    header = [name.strip() for name in rows[0]]
    return header, [[c.strip() for c in (row + [""] * len(header))[:len(header)]] for row in rows[1:]], {}, {}


def load_map(path: Path) -> dict:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"could not read {path}: {exc}")
    constructs = spec.get("constructs") if isinstance(spec, dict) else None
    if not isinstance(constructs, dict) or not constructs:
        fail('items.json needs "constructs": {name: {"items", "reverse", "min", "max", "source", "licence"}}')
    if not isinstance(spec.get("reversed_in_data"), bool):
        fail('items.json needs "reversed_in_data": true or false. Ask the user whether the reverse-keyed items are '
             "already reversed in the data file")
    if not isinstance(spec.get("missing", []), list):
        fail('"missing" must be a list of codes such as ["-99"]')
    owner = {}
    for name, c in constructs.items():
        items, reverse = c.get("items"), c.get("reverse", [])
        if not (isinstance(items, list) and len(items) >= 2 and all(isinstance(i, str) for i in items)):
            fail(f'{name}: "items" must list two or more column names')
        if not isinstance(reverse, list) or set(reverse) - set(items):
            fail(f'{name}: "reverse" must list items of this construct (an empty list when there are none)')
        if not all(isinstance(c.get(k), (int, float)) and not isinstance(c.get(k), bool) for k in ("min", "max")) \
                or c["min"] >= c["max"]:
            fail(f'{name}: "min" and "max" must be the lowest and highest response, with min < max')
        if c.get("licence") not in LICENCES or not str(c.get("source") or "").strip():
            fail(f'{name}: give "source" and "licence" ({", ".join(LICENCES)})')
        for item in items:
            if item in owner:
                fail(f"{item} is listed under both {owner[item]} and {name}")
            owner[item] = name
    return spec


def analyse(columns: dict, items: list) -> dict:
    """n, alpha and each item's item-rest r over the rows where every item has a value."""
    rows = [values for values in zip(*(columns[i] for i in items)) if None not in values]
    out = {"n": len(rows), "alpha": None, "item_rest_r": {i: None for i in items}}
    if len(rows) < 3:
        return out
    totals = [sum(row) for row in rows]
    variance = statistics.variance(totals)
    if variance > 0:
        k = len(items)
        out["alpha"] = k / (k - 1) * (1 - sum(statistics.variance([r[j] for r in rows]) for j in range(k)) / variance)
    for j, item in enumerate(items):
        x = [row[j] for row in rows]
        try:
            out["item_rest_r"][item] = statistics.correlation(x, [t - v for t, v in zip(totals, x)])
        except statistics.StatisticsError:           # a constant item or a constant rest score
            pass
    return out


def fmt(value) -> str:
    return "—" if value is None else f"{value:.2f}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Score items from psychometrics/items.json and find keying problems.")
    parser.add_argument("items", type=Path, help="The item map, psychometrics/items.json")
    parser.add_argument("--data", type=Path, help='The data file (default: "data" in items.json)')
    parser.add_argument("--few-categories", type=int, default=5,
                        help="Lead for items that use fewer response categories than this (a convention; default 5)")
    args = parser.parse_args(argv)
    spec = load_map(args.items)
    data = args.data or (Path(spec["data"]) if spec.get("data") else None)
    if data is None:
        fail('name the data file with --data or "data" in items.json')
    header, rows, ranges, labels = read_data(data)
    constructs = spec["constructs"]
    absent = [i for c in constructs.values() for i in c["items"] if i not in header]
    if absent:
        fail(f"not columns of {data.name}: {', '.join(absent)}. Columns: {', '.join(header)}")
    codes = {str(c).strip() for c in spec.get("missing", [])}
    numeric_codes = {number(c) for c in codes} - {None}

    def missing(text: str, column: str) -> bool:
        value = number(text)
        return text.lower() in NA or text in codes or (value is not None and (
            value in numeric_codes or any(lo <= value <= hi for lo, hi in ranges.get(column, ()))))

    table = [[("" if missing(text, column) else text) for text, column in zip(row, header)] for row in rows]
    problems, leads, report, raw, scored = [], defaultdict(list), {}, {}, {}
    for name, c in constructs.items():
        lo, hi, reverse = c["min"], c["max"], set(c.get("reverse", []))
        for item in c["items"]:
            j, bad, values = header.index(item), Counter(), []
            for row in table:
                value = number(row[j]) if row[j] else None
                if row[j] and (value is None or not lo <= value <= hi):
                    bad[row[j]] += 1
                    value = None
                values.append(value)
            if bad:
                shown = ", ".join(f"{text} ({count})" for text, count in bad.most_common(5))
                problems.append(f"{item}: {sum(bad.values())} value(s) outside {lo:g} to {hi:g} or not numbers: {shown}. "
                                "Declare a missing code in items.json, or ask the user; never recode them yourself")
            raw[item] = values
            flip = item in reverse and not spec["reversed_in_data"]
            scored[item] = [None if v is None else lo + hi - v for v in values] if flip else values
            used = {v for v in values if v is not None}
            if len(used) == 1:
                problems.append(f"{item}: every answer is {used.pop():g}: an item with one value carries no information")
            elif 1 < len(used) < args.few_categories:
                leads["few categories"].append(f"{item} ({name}) uses {len(used)} of its response categories: state the "
                                               "ordinal decision before the factor analyses")
        before, after = analyse(raw, c["items"]), analyse(scored, c["items"])
        for item in c["items"]:
            r0, r1 = before["item_rest_r"][item], after["item_rest_r"][item]
            if r1 is not None and r1 < 0 and item in reverse:
                leads["negative item-rest r"].append(
                    f"{item} ({name}): declared reverse, item-rest r {r1:.2f} after scoring ({fmt(r0)} in the data): "
                    "reversed twice (is reversed_in_data right?) or a wrong key. Ask the user")
            elif r1 is not None and r1 < 0:
                leads["negative item-rest r"].append(
                    f"{item} ({name}): item-rest r {r1:.2f}, not declared reverse: a reverse-worded item missing from "
                    '"reverse"? Ask the user; if it is, add it and run again')
        if after["alpha"] is not None and after["alpha"] < 0:
            leads["negative alpha"].append(f"{name}: alpha {after['alpha']:.2f} after scoring: a reverse key is probably "
                                           "missing or wrong")
        first = labels.get(c["items"][0]) or {}
        for item in c["items"][1:]:
            mine = labels.get(item) or {}
            if first.get(lo) and first.get(hi) and first.get(lo) != first.get(hi) and \
                    (mine.get(lo), mine.get(hi)) == (first.get(hi), first.get(lo)):
                leads["value labels"].append(f"{item} ({name}): its value labels run the other way from {c['items'][0]} "
                                             f"({lo:g} = {mine.get(lo)!r}): a reversed response scale in the file")
        report[name] = {"n": after["n"], "alpha_in_data": before["alpha"], "alpha_scored": after["alpha"],
                        "items": {i: {"reverse": i in reverse, "item_rest_r_in_data": before["item_rest_r"][i],
                                      "item_rest_r_scored": after["item_rest_r"][i],
                                      "categories_used": len({v for v in raw[i] if v is not None})}
                                  for i in c["items"]}}
    if not spec.get("confirmed"):
        leads["not confirmed"].append('items.json has no "confirmed" date: show the item map to the user and record '
                                      "the day they confirmed it")

    folder = args.items.parent
    target = folder / f"{data.stem}.scored.csv"
    if target.resolve() == data.resolve():
        fail(f"the scored copy would overwrite the data file {data}; move items.json to psychometrics/")
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for index, row in enumerate(table):
            writer.writerow([cell(scored[col][index]) if col in scored else text for text, col in zip(row, header)])
    shown = {kind: items[:CAP] + ([f"and {len(items) - CAP} more"] if len(items) > CAP else [])
             for kind, items in leads.items()}
    record = {"tool": "score_items.py", "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "items_json": {"path": str(args.items), "sha256": sha256(args.items)},
              "data": {"path": str(data), "sha256": sha256(data), "rows": len(rows)},
              "scored": {"path": str(target), "sha256": sha256(target)},
              "reversed_in_data": spec["reversed_in_data"], "missing_codes": sorted(codes),
              "file_missing_ranges": {k: v for k, v in ranges.items() if k in header},
              "constructs": report, "problems": problems, "leads": shown}
    (folder / "scoring.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Item scoring", "", f"Data `{data}` ({len(rows)} rows), item map `{args.items}`, scored copy `{target}`. "
             f"Reverse items {'were already reversed in the data' if spec['reversed_in_data'] else 'scored as (min + max) - x'}.",
             ""]
    for name, entry in report.items():
        lines += [f"## {name}", "", f"n with every item: {entry['n']}; alpha in the data {fmt(entry['alpha_in_data'])}, "
                  f"after scoring {fmt(entry['alpha_scored'])}.", "",
                  "| Item | Reverse | Item-rest r in the data | Item-rest r scored | Categories used |", "|---|---|---|---|---|"]
        lines += [f"| {i} | {'yes' if e['reverse'] else ''} | {fmt(e['item_rest_r_in_data'])} | {fmt(e['item_rest_r_scored'])} "
                  f"| {e['categories_used']} |" for i, e in entry["items"].items()]
        lines.append("")
    lines += ["## Problems", ""] + ([f"- {p}" for p in problems] or ["None."]) + ["", "## Leads (show each to the user)", ""]
    lines += [f"- {kind}: {item}" for kind, items in shown.items() for item in items] or ["None."]
    (folder / "scoring.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"scored": str(target), "constructs": {n: {k: e[k] for k in ("n", "alpha_in_data", "alpha_scored")}
                                                             for n, e in report.items()},
                      "problems": problems, "leads": shown, "report": str(folder / "scoring.md"),
                      "exit": int(bool(problems))}, indent=2, ensure_ascii=False))
    return int(bool(problems))


if __name__ == "__main__":
    sys.exit(main())
