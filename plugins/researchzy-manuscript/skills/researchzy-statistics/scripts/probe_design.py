#!/usr/bin/env python3
"""Probe the design of a data table before a statistical method is chosen.

  probe_design.py data.csv --unit subject --group condition --outcome latency_min
  probe_design.py data.tsv --unit mouse --group genotype --outcome weight_g --time day
  probe_design.py data.csv --unit patient --cluster clinic --group arm --outcome responded
  probe_design.py data.csv --pair pair_id --unit patient --group arm --outcome score
  probe_design.py data.csv --rows-are-units --group arm --outcome score
  probe_design.py --profile figures/trial.profile.json --outcome latency_min

--unit is the column that names the unit of analysis (subject, animal, culture, run). --pair is
the column that links matched units when that is not the unit itself. --rows-are-units records
that the user said every row is a separate unit; without it and without --unit the design is
unit_not_declared and no method is proposed. --profile takes the data file and the unit, group
and time columns from a profile written by researchzy-figures; options given here win.

It writes <out>/<data>.design.json (--out, default statistics) and prints the same JSON: missing values
per column, the outcome type with its evidence, rows per unit, n per group in units and in rows,
complete and incomplete pairs or sets, clusters, replicate rows, sparse cells, the design
(independent, paired, repeated, clustered, replicates, unit_not_declared; several can hold at
once), the methods the design rules out with the reason, and the row of
references/method-table.md to read.

The probe counts and runs no test. It never looks at a normality test: the method follows from
the design and the question, not from a pre-test.

Standard library only. Exit code 2 when the input cannot be read or a column does not exist.
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
from pathlib import Path

MISSING = frozenset({"", "na", "n/a", "nan", "null", "none", "#n/a", "."})
TYPES = ("continuous", "binary", "count", "ordinal", "categorical")
ROLES = ("unit", "pair", "group", "outcome", "time", "cluster")
SPARSE = 5                    # an expected count under this makes the chi-square approximation poor
PREDICTOR_LEVELS = 6          # a numeric group column with more distinct values is a predictor, not groups
ROW_TESTS = ("independent-samples tests on the rows (Welch or Student t, Mann-Whitney, one-way ANOVA, "
             "Kruskal-Wallis, chi-square, Fisher)")


def fail(message: str):
    print(f"probe_design: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_table(path: Path) -> tuple:
    if not path.is_file():
        fail(f"no such file: {path}")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    first = text.split("\n", 1)[0]
    delimiter = "\t" if path.suffix.lower() in (".tsv", ".tab") else max(",;\t|", key=first.count)
    rows = [row for row in csv.reader(text.splitlines(), delimiter=delimiter) if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        fail(f"{path} has no data rows under its header.")
    header = [name.strip() for name in rows[0]]
    return header, [(row + [""] * len(header))[:len(header)] for row in rows[1:]], hashlib.sha256(raw).hexdigest()


def number(text: str):
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def outcome_type(values: list, declared) -> dict:
    """The type the values suggest, with the evidence; a declared type wins and is marked."""
    distinct = sorted(set(values))
    numbers = [number(value) for value in values]
    numeric = bool(values) and all(n is not None for n in numbers)
    whole = numeric and all(n == int(n) for n in numbers)
    shown = ", ".join(distinct[:6]) + (", ..." if len(distinct) > 6 else "")
    if len(distinct) < 2:
        guess, why = None, f"{len(distinct)} distinct value(s): nothing to analyse"
    elif len(distinct) == 2:
        guess, why = "binary", f"2 distinct values ({shown})"
    elif not numeric:
        guess, why = "categorical", (f"{len(distinct)} distinct text labels ({shown}); if they have an order, "
                                     "pass --outcome-type ordinal")
    elif not whole or min(numbers) < 0:
        guess, why = "continuous", f"{len(distinct)} distinct numbers from {min(numbers):g} to {max(numbers):g}"
    elif len(distinct) <= 7 and max(numbers) <= 10:
        guess, why = "ordinal", (f"{len(distinct)} distinct whole numbers from {min(numbers):g} to {max(numbers):g}: "
                                 "a score or a small count; pass --outcome-type to settle it")
    else:
        guess, why = "count", (f"non-negative whole numbers, {len(distinct)} distinct, largest {max(numbers):g}; if it "
                               "is a measurement recorded without decimals, pass --outcome-type continuous")
    if declared:
        return {"type": declared, "declared": True, "evidence": f"declared with --outcome-type; the values look {guess}: {why}"}
    return {"type": guess, "declared": False, "evidence": why}


def spread(counts: list) -> dict:
    return {"min": min(counts), "median": statistics.median(counts), "max": max(counts)}


def probe(header: list, rows: list, cols: dict, rows_are_units: bool, declared_type, extra_missing=()) -> dict:
    for role, name in cols.items():
        if name and name not in header:
            fail(f"--{role} {name!r} is not a column. Columns: {', '.join(header)}")
    if not cols["outcome"]:
        fail("--outcome is required: name the column of the outcome.")
    missing_tokens = MISSING | {token.strip().lower() for token in extra_missing}
    index = {role: header.index(name) for role, name in cols.items() if name}

    def cell(row, role):
        value = row[index[role]].strip() if role in index else None
        return None if value is None or value.lower() in missing_tokens else value

    table = [{role: cell(row, role) for role in ROLES} for row in rows]
    missing = {cols[role]: sum(1 for r in table if r[role] is None) for role in index}
    values = [r["outcome"] for r in table if r["outcome"] is not None]
    outcome = outcome_type(values, declared_type)
    kind = outcome["type"]
    notes, ruled_out, first = [], [], []
    report = {"columns": cols, "missing": missing, "outcome": outcome}

    def rule(method, because, instead):
        ruled_out.append({"method": method, "because": because, "instead": instead})

    unit_role = "unit" if cols["unit"] else "pair" if cols["pair"] else None
    link_role = "pair" if cols["pair"] else unit_role
    for i, r in enumerate(table):
        r["u"] = r[unit_role] if unit_role else (str(i) if rows_are_units else None)
        r["link"] = r[link_role] if link_role else r["u"]
    report["unit_declared_by"] = (f"column {cols[unit_role]}" if unit_role else
                                  "the user (--rows-are-units)" if rows_are_units else None)
    used = [r for r in table if r["u"] is not None and r["link"] is not None]
    levels = sorted({r["group"] for r in table if r["group"] is not None})
    predictor = len(levels) > PREDICTOR_LEVELS and all(number(level) is not None for level in levels)
    grouped = bool(cols["group"]) and not predictor

    groups = defaultdict(lambda: {"rows": 0, "rows_with_outcome": 0, "units": set(), "units_with_outcome": set()})
    for r in table:
        if grouped and r["group"] is None:
            continue
        entry = groups[r["group"] if grouped else "all rows"]
        entry["rows"] += 1
        entry["rows_with_outcome"] += r["outcome"] is not None
        if r["u"] is not None:
            entry["units"].add(r["u"])
            if r["outcome"] is not None:
                entry["units_with_outcome"].add(r["u"])
    report["n_per_group"] = {
        level: {"rows": e["rows"], "rows_with_outcome": e["rows_with_outcome"],
                **({"units": len(e["units"]), "units_with_outcome": len(e["units_with_outcome"])}
                   if unit_role or rows_are_units else {})} for level, e in sorted(groups.items())}

    design, within = [], []
    if not unit_role and not rows_are_units:
        design.append("unit_not_declared")
        rule("every test", "no column names the unit of analysis and the user has not said that each row is a "
             "separate unit", "ask the user what one row is, then run again with --unit or --rows-are-units")
    else:
        per_unit = Counter(r["u"] for r in used)
        report["rows_per_unit"] = {"units": len(per_unit), **spread(list(per_unit.values())),
                                   "units_with_several_rows": sum(1 for c in per_unit.values() if c > 1)}
        by_link = defaultdict(list)
        for r in used:
            by_link[r["link"]].append(r)
        link = cols[link_role] if link_role else "row"
        for role in ("group", "time"):
            if role not in index or (role == "group" and predictor):
                continue
            every = {r[role] for r in used if r[role] is not None}
            crossing = sum(1 for rs in by_link.values() if len({r[role] for r in rs if r[role] is not None}) > 1)
            if not crossing:
                continue
            within.append(role)
            kind_of = "paired" if role == "group" and len(every) == 2 else "repeated"
            complete = sum(1 for rs in by_link.values() if {r[role] for r in rs if r["outcome"] is not None} >= every)
            partial = sum(1 for rs in by_link.values() if any(r["outcome"] is not None for r in rs)) - complete
            if kind_of not in design:
                design.append(kind_of)
            counts = {"column": cols[role], "levels": len(every), "linked_by": link,
                      "ids_in_several_levels": crossing, "complete": complete, "incomplete": partial}
            if kind_of == "paired":
                report["pairs"] = counts
            else:
                report.setdefault("repeated", []).append(counts)
            rule(ROW_TESTS, f"{crossing} of {len(by_link)} {link} values have rows in several levels of {cols[role]}: "
                 "the rows are not independent", "the 'same unit measured again' column of the method table")
            if partial:
                rule(f"a test on complete {'pairs' if kind_of == 'paired' else 'sets'} that does not say what was left out",
                     f"{partial} {link} value(s) lack an outcome in some level of {cols[role]}; {complete} are complete",
                     f"report the {partial} as left out, or fit a mixed model, which keeps every observed value")
            if not complete:
                notes.append(f"no {link} value has an outcome in every level of {cols[role]}: the same ids were probably "
                             "given to different units in different groups. If so, make them unique and run again")
            elif role == "group":
                notes.append(f"equal {link} values are read as the same unit. If the levels of {cols[role]} hold "
                             "different units that share id values, make the ids unique and run again")
        cells = Counter((r["u"], r["group"], r["time"]) for r in used)
        several = sum(1 for c in cells.values() if c > 1)
        if several:
            design.append("replicates")
            report["replicates"] = {"cells_with_several_rows": several, "most_rows_per_cell": max(cells.values())}
            rule("any test or n that counts each row as an independent observation",
                 f"{several} unit-and-condition cells hold several rows (up to {max(cells.values())}): "
                 "the rows are replicates of one unit", "one value per unit and condition, or a model of the nesting")
            first.append("replicates: aggregate the rows to one value per unit and condition (state how), or fit a "
                         "mixed model with a random intercept per unit; n is the number of units")
        members, arms = defaultdict(set), defaultdict(set)
        for r in used:
            if r["cluster"] is not None:
                members[r["cluster"]].add(r["u"])
                arms[r["cluster"]].add(r["group"])
        sizes = [len(units) for units in members.values()]
        if sizes and max(sizes) > 1:
            constant = grouped and all(len(a - {None}) <= 1 for a in arms.values())
            design.append("clustered")
            report["clusters"] = {"column": cols["cluster"], "clusters": len(sizes), "units_per_cluster": spread(sizes),
                                  "group_constant_within_cluster": constant}
            rule("tests that treat units of the same cluster as independent",
                 f"{len(per_unit)} units sit in {len(sizes)} {cols['cluster']} clusters (up to {max(sizes)} in one)",
                 "cluster-robust standard errors, a mixed model with a random intercept per cluster, or one summary per cluster")
            first.append("clustered: " + ("the group is assigned per cluster, so n is the number of clusters; " if constant else "")
                         + "use cluster-robust errors or a random intercept per cluster, never a plain test on the units")
        if not design:
            design.append("independent")

    if kind in ("binary", "categorical") and grouped and len(levels) > 1:
        counts = Counter((r["group"], r["outcome"]) for r in table if r["group"] is not None and r["outcome"] is not None)
        row_totals, column_totals = Counter(), Counter()
        for (g, o), c in counts.items():
            row_totals[g] += c
            column_totals[o] += c
        total = sum(row_totals.values())
        expected = [row_totals[g] * column_totals[o] / total for g in row_totals for o in column_totals]
        low = sum(1 for e in expected if e < SPARSE)
        report["sparse_cells"] = {"table": f"{len(row_totals)} x {len(column_totals)}", "counted_in": "rows",
                                  "cells_expected_under_5": low, "smallest_expected": round(min(expected), 2),
                                  "zero_cells": sum(1 for g in row_totals for o in column_totals if not counts[(g, o)])}
        if low:
            rule("the chi-square test", f"{low} of {len(expected)} cells have an expected count under {SPARSE} "
                 f"(smallest {min(expected):.2f})", "Fisher's exact test for a 2 x 2 table, a permutation p-value otherwise")
    if kind in ("binary", "categorical"):
        rule("t tests, ANOVA and correlations on the category codes", f"the outcome is {kind}",
             "the rows for proportions in the method table")
        if kind == "categorical" and len(set(values)) == len(values):
            notes.append(f"{cols['outcome']}: no value repeats. Is this the outcome column?")
    elif kind == "ordinal":
        notes.append("ordinal outcome: a mean treats the steps as equal. Use the rank-based row, or say in the plan "
                     "why means are meaningful")
    elif kind == "count":
        notes.append("count outcome: with zeros or small counts use the count row (a rate ratio), not a t test")
    for name, count in missing.items():
        if count:
            notes.append(f"{name}: {count} of {len(rows)} missing. Decide in the plan how they are handled; missing is not zero")

    factor = levels if grouped else sorted({r["time"] for r in table if r["time"] is not None}) if within else []
    comparison = ("numeric predictor" if predictor else "one group" if len(factor) < 2
                  else "2 groups" if len(factor) == 2 else "3+ groups")
    if design == ["unit_not_declared"] or kind is None:
        route = None
    else:
        if grouped and "time" in within:
            row = "model"
            first.append(f"{cols['group']} and {cols['time']} are both in the design: fit outcome ~ group * time with a "
                         "random intercept per unit and report the interaction; the two-group cells do not apply")
        elif comparison == "numeric predictor":
            row = "continuous / numeric predictor" if kind == "continuous" else "model"
        elif comparison == "one group":
            row = f"{kind} / one group" if kind in ("continuous", "binary") else "describe only"
        else:
            row = f"{kind} / 2+ groups" if kind in ("categorical", "count") else f"{kind} / {comparison}"
        route = {"table": "references/method-table.md", "row": row,
                 "column": "same unit measured again" if within else "independent units", "first": first}
    report.update(design=design, ruled_out=ruled_out, route=route, notes=notes)
    return report


def from_profile(args) -> None:
    """Fill the file and the unit, group and time columns from a researchzy-figures profile."""
    try:
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
        columns = profile["columns"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fail(f"could not read the profile {args.profile}: {exc}")
    args.file = args.file or Path(profile.get("file", {}).get("path", ""))
    by_role = defaultdict(list)
    for column in columns:
        by_role[column.get("role")].append(column)
    args.profile_notes = [f"figures profile design: {', '.join(profile.get('design', []))}"]
    for option, role in (("unit", "id"), ("group", "group"), ("time", "time"), ("outcome", "measure")):
        found = by_role[role]
        if getattr(args, option) or not found or (role == "measure" and len(found) != 1):
            continue
        if option == "unit" and args.rows_are_units:
            continue
        setattr(args, option, found[0]["name"])
        if found[0].get("role_from") == "guess":
            args.profile_notes.append(f"--{option} {found[0]['name']} is a guess from the figures profile: confirm it")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Probe the design of a data table before a method is chosen.")
    parser.add_argument("file", type=Path, nargs="?", help="CSV or TSV file with a header row")
    parser.add_argument("--unit", help="Column naming the unit of analysis (subject, animal, culture, run)")
    parser.add_argument("--group", help="Column of the groups or conditions to compare")
    parser.add_argument("--outcome", help="Column of the outcome")
    parser.add_argument("--pair", help="Column linking matched units, when that is not the unit column")
    parser.add_argument("--time", help="Column of the occasion (visit, day) when units are measured repeatedly")
    parser.add_argument("--cluster", help="Column of the cluster the units sit in (clinic, litter, plate, class)")
    parser.add_argument("--rows-are-units", action="store_true", help="The user said that every row is one separate unit")
    parser.add_argument("--outcome-type", choices=TYPES, help="Declare the outcome type instead of the guess")
    parser.add_argument("--na", action="append", default=[], help="A further value that means missing (repeatable)")
    parser.add_argument("--profile", help="A <name>.profile.json written by researchzy-figures")
    parser.add_argument("--out", default="statistics", help="Output folder (default: statistics)")
    args = parser.parse_args(argv)
    args.profile_notes = []
    if args.profile:
        from_profile(args)
    if not args.file:
        fail("give a data file, or --profile.")
    if args.unit and args.rows_are_units:
        fail("--unit and --rows-are-units contradict each other.")
    header, rows, digest = read_table(args.file)
    report = probe(header, rows, {role: getattr(args, role) for role in ROLES}, args.rows_are_units,
                   args.outcome_type, args.na)
    report = {"tool": "researchzy-statistics", "schema_version": 1,
              "file": {"path": str(args.file), "sha256": digest, "rows": len(rows)}, **report}
    report["notes"] = args.profile_notes + report["notes"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    (out / f"{Path(args.file).stem}.design.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
