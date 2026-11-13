#!/usr/bin/env python3
"""Profile a data table before plotting it: what each column is, how many observations each
group has, what is missing, how the measures are spread, and whether the rows are independent.

  profile_data.py data.csv                                  guess the column roles
  profile_data.py data.tsv --id subject --group treatment   name the unit and the groups yourself
  profile_data.py data.csv --pair subject --group visit     rows with the same --pair value belong together
  profile_data.py data.csv --na -999                        count -999 as missing
  profile_data.py data.xlsx --sheet Sheet1 --name trial     Excel needs pandas with openpyxl

Roles: id (names the unit of analysis), group (categories to compare), time (an ordered axis),
measure (a numeric outcome), other. A guess is only a guess: when the summary shows a wrong
role, run again with --id, --group, --time, --measure or --pair.

Writes figures/<name>.profile.json (--out, --name; the name defaults to the file's) and prints a
short JSON summary: the roles, the design, the smallest n per group, and the charts the profile
rules out, each with the reason and what to draw instead. It profiles for plotting only: no
tests, no models.

Standard library only; pandas is used only to read Excel files. Exit code 2 when the input
cannot be read.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

MISSING = frozenset({"", "na", "n/a", "nan", "null", "none", "#n/a", "."})
ROLES = ("id", "group", "time", "measure", "other")
ID_WORDS = frozenset("id subject participant patient animal mouse donor sample specimen respondent case".split())
GROUP_WORDS = frozenset("group arm treatment condition genotype sex gender class category cohort batch site model "
                        "method strain type label cluster status species region".split())
TIME_WORDS = frozenset("time date day days week weeks month months year years hour hours minute minutes second "
                       "seconds visit session timepoint epoch step iteration wave".split())
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
SENTINELS = (-9999.0, -999.0, -99.0, 999.0, 9999.0)

# Thresholds behind the rule-outs; references/chart-selection.md gives the reasons.
MIN_N_POINTS_ONLY = 5      # under this, a box plot summarises fewer points than it has parts
MIN_N_BAR = 10             # under this, a bar of means hides data that fit on the page
MIN_N_DENSITY = 30         # under this, a violin or density curve is mostly the smoothing
MAX_GROUP_LEVELS = 20      # a text column with more distinct values is not a grouping
MAX_HUES = 8               # the palette has eight colours
MANY_POINTS = 5000         # above this, single markers overprint
SKEWED = 1.0               # |skewness| from which mean and SD stop describing the data
WIDE_RANGE = 100.0         # max/min from which a linear axis squeezes most of the data


def fail(message: str):
    print(f"profile_data: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_table(path: Path, sheet) -> tuple:
    """(header, rows of strings, delimiter) from a CSV, TSV or Excel file."""
    if not path.is_file():
        fail(f"no such file: {path}")
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        try:
            import pandas
        except ImportError:
            fail("reading Excel needs pandas with openpyxl; export the sheet as CSV instead.")
        try:
            frame = pandas.read_excel(path, sheet_name=sheet if sheet is not None else 0, dtype=str, keep_default_na=False)
        except Exception as exc:
            fail(f"could not read {path}: {exc}")
        return [str(c) for c in frame.columns], [[str(v) for v in row] for row in frame.values.tolist()], "excel"
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
    return rows[0], rows[1:], delimiter


def tokens(name: str) -> set:
    """The words of a column name: 'subjectID' and 'subject_id' both give {'subject', 'id'}."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return set(re.split(r"[^a-z0-9]+", spaced.lower())) - {""}


def as_number(value: str, decimal_comma: bool):
    if decimal_comma and re.fullmatch(r"[-+]?\d+,\d+", value):
        value = value.replace(",", ".")
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def as_date(value: str):
    for pattern in DATE_FORMATS:
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return None


def tidy(number: float):
    return float(f"{number:.6g}")


def describe(values: list) -> dict:
    """Range, centre, spread and skewness of a measure."""
    n = len(values)
    stats = {"n": n, "min": tidy(min(values)), "max": tidy(max(values)), "mean": tidy(statistics.fmean(values)),
             "median": tidy(statistics.median(values)), "zeros": sum(1 for v in values if v == 0),
             "negatives": sum(1 for v in values if v < 0), "distinct": len(set(values))}
    if n >= 2:
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
        spread = 1.5 * (q3 - q1)
        stats.update(sd=tidy(statistics.stdev(values)), q1=tidy(q1), q3=tidy(q3),
                     outside_1_5_iqr=sum(1 for v in values if v < q1 - spread or v > q3 + spread))
    mean = statistics.fmean(values)
    m2 = sum((v - mean) ** 2 for v in values) / n
    if n >= 3 and m2 > 0:      # adjusted Fisher-Pearson coefficient, as most statistics packages report it
        g1 = (sum((v - mean) ** 3 for v in values) / n) / m2 ** 1.5
        stats["skew"] = tidy(g1 * math.sqrt(n * (n - 1)) / (n - 2))
    return stats


def read_column(name: str, cells: list, missing: frozenset, decimal_comma: bool, numeric: bool = False) -> dict:
    """Type, counts and parsed values of one column; `numeric` reads it as numbers whatever it holds."""
    present = [(i, cell.strip()) for i, cell in enumerate(cells) if cell.strip().lower() not in missing]
    column = {"name": name, "n": len(present), "missing": len(cells) - len(present),
              "distinct": len({value for _, value in present}), "notes": []}
    numbers = [(i, as_number(value, decimal_comma)) for i, value in present]
    parsed = [(i, number) for i, number in numbers if number is not None]
    if not present:
        column["type"] = "empty"
    elif parsed and (numeric or 2 * len(parsed) >= len(present)):   # at least half are numbers
        column["type"] = "numeric"
        column["values"] = dict(parsed)
        odd = [value for (_, value), (_, number) in zip(present, numbers) if number is None]
        if odd:
            column["missing"] += len(odd)
            column["n"] -= len(odd)
            column["not_numbers"] = len(odd)
            column["notes"].append(f"{len(odd)} value(s) are not numbers ({', '.join(sorted(set(odd))[:3])}): counted as "
                                   "missing here. Decide how the figure shows them; they are not zero")
    elif all(as_date(value) for _, value in present):
        column["type"] = "datetime"
    else:
        column["type"] = "text"
    column["labels"] = {i: value for i, value in present}
    return column


def guess_role(column: dict) -> str:
    """A role from the column's name and values; "label" is a text column with no repeated value."""
    words, kind = tokens(column["name"]), column["type"]
    if kind == "empty" or column["distinct"] <= 1:
        return "other"
    if kind == "datetime":
        return "time"
    if "id" in words:
        return "id"
    whole = kind == "numeric" and all(float(v).is_integer() for v in column["values"].values())
    few = column["distinct"] <= MAX_GROUP_LEVELS and (kind == "text" or whole)
    if words & GROUP_WORDS and few:
        return "group"
    if words & TIME_WORDS:
        return "time"
    if words & ID_WORDS and column["distinct"] > 2:
        return "id"
    if kind == "text":
        if column["distinct"] == column["n"]:
            return "label"
        return "group" if few else "other"
    if column["distinct"] == 2 and whole:
        return "group"
    if whole and column["distinct"] <= 6:
        column["notes"].append(f"only {column['distinct']} distinct whole numbers: a group code or an ordinal score? "
                               "Pass --group if it names groups")
    return "measure"


def build_profile(header: list, rows: list, args, delimiter: str) -> dict:
    names, seen = [], {}
    for position, name in enumerate(header):
        name = name.strip() or f"column_{position + 1}"
        seen[name] = seen.get(name, 0) + 1
        names.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    width = len(names)
    ragged = sum(1 for row in rows if len(row) != width)
    rows = [(row + [""] * width)[:width] for row in rows]
    missing = MISSING | {token.strip().lower() for token in args.na or []}
    decimal_comma = delimiter in (";", "\t") and any(
        re.fullmatch(r"[-+]?\d+,\d+", cell.strip()) for row in rows[:200] for cell in row)
    columns = [read_column(name, [row[i] for row in rows], missing, decimal_comma, name in (args.measure or []))
               for i, name in enumerate(names)]
    by_name = {column["name"]: column for column in columns}

    chosen = {"id": [name for name in (args.id, args.pair) if name], "group": args.group or [],
              "time": [args.time] if args.time else [], "measure": args.measure or []}
    for role, picked in chosen.items():
        for name in picked:
            if name not in by_name:
                fail(f"{name!r} is not a column. Columns: {', '.join(names)}")
    for column in columns:
        user = next((role for role in ROLES if column["name"] in chosen.get(role, [])), None)
        column["role"], column["role_from"] = (user, "user") if user else (guess_role(column), "guess")
        if column["role"] == "measure" and column["type"] != "numeric":
            fail(f"--measure {column['name']!r} holds no numbers.")

    def of(role):
        return [c for c in columns if c["role"] == role]

    for label in of("label"):          # a text column in which no value repeats
        if not of("group") and label["n"] <= MAX_GROUP_LEVELS:
            label["role"] = "group"    # one row per label: a table of summaries
        else:
            label["role"] = "other" if of("id") else "id"
    for role in ("id", "time"):        # one unit column and one ordered axis: keep the first guess
        for extra in [c for c in of(role) if c["role_from"] == "guess"][0 if chosen[role] else 1:]:
            extra["role"] = "other"
            extra["notes"].append(f"looks like another {role} column and was left out: pass --{role} to use it")

    notes = [f"{ragged} row(s) had a different number of fields than the header"] if ragged else []
    if decimal_comma:
        notes.append("numbers with a decimal comma were read as decimals")
    measures, groups = of("measure"), of("group")
    time = of("time")[0] if of("time") else None
    unit = by_name[args.id or args.pair] if (args.id or args.pair) else (of("id")[0] if of("id") else None)
    link = by_name[args.pair] if args.pair else unit       # what ties observations together across conditions

    for column in measures:
        values = list(column["values"].values())
        column["stats"] = describe(values)
        for code in SENTINELS:
            rest = [v for v in values if v != code]
            if code in values and len(set(rest)) > 2 and (min(rest) >= 0 if code < 0 else max(rest) < code / 2):
                column["notes"].append(f"the value {code:g} occurs {values.count(code)} time(s) and lies outside the "
                                       f"rest ({min(rest):g} to {max(rest):g}): if it codes missing, run again with --na {code:g}")

    def cell_of(row_index: int, parts: list) -> tuple:
        return tuple(part["labels"].get(row_index) for part in parts)

    def counts(parts: list) -> dict:
        """Rows, units and non-missing n per measure for every combination of the given columns."""
        table: dict = {}
        for i in range(len(rows)):
            key = cell_of(i, parts)
            if None in key:
                continue
            entry = table.setdefault(" / ".join(key) or "all rows",
                                     {"rows": 0, "units": set(), "n": {m["name"]: set() for m in measures}})
            entry["rows"] += 1
            who = unit["labels"].get(i, i) if unit else i
            entry["units"].add(who)
            for m in measures:
                if i in m["values"]:
                    entry["n"][m["name"]].add(who)
        return {level: {"rows": e["rows"], **({"units": len(e["units"])} if unit else {}),
                        "n": {name: len(who) for name, who in e["n"].items()}} for level, e in table.items()}

    group_counts = {g["name"]: counts([g]) for g in groups} if groups else {"(no group)": counts([])}
    smallest = {m["name"]: min(level["n"][m["name"]] for table in group_counts.values() for level in table.values())
                for m in measures}
    if len(groups) > 1:                # the cells of a figure that splits by every group column at once
        crossed = counts(groups)
        if len(crossed) <= 60:
            group_counts[" x ".join(g["name"] for g in groups)] = crossed
            for m in measures:
                cell = min(level["n"][m["name"]] for level in crossed.values())
                if cell < smallest[m["name"]]:
                    notes.append(f"{m['name']}: split by {' and '.join(g['name'] for g in groups)} together, the "
                                 f"smallest cell has n = {cell}")

    design, structure = [], {}
    if unit is None:
        design.append("no_id_column")
        notes.append("no id column: every row is taken as one independent unit. If several rows come from the same "
                     "subject, sample or run, name that column with --id")
    else:
        rows_of: dict = {}
        for i, label in link["labels"].items():
            rows_of.setdefault(label, []).append(i)
        structure["unit"] = {"column": unit["name"], "ids": len(set(unit["labels"].values()))}
        structure["linked_by"] = {"column": link["name"], "ids": len(rows_of),
                                  "ids_with_several_rows": sum(1 for r in rows_of.values() if len(r) > 1),
                                  "most_rows_per_id": max(map(len, rows_of.values()), default=0)}
        for part in groups + ([time] if time else []):
            levels = {label for label in part["labels"].values()}
            spans = [len({part["labels"][i] for i in r if i in part["labels"]}) for r in rows_of.values()]
            several = sum(1 for s in spans if s > 1)
            if several:
                kind = "repeated_over_time" if part is time else "paired"
                if kind not in design:
                    design.append(kind)
                structure.setdefault(kind, {})[part["name"]] = {
                    "levels": len(levels), "ids": len(rows_of), "ids_in_several_levels": several,
                    # per measure: the ids that have a value in every level, i.e. the complete sets
                    "ids_complete": {m["name"]: sum(1 for r in rows_of.values()
                                                    if {part["labels"].get(i) for i in r if i in m["values"]} >= levels)
                                     for m in measures}}
        keys = groups + ([time] if time else [])
        repeats: dict = {}
        for i, label in unit["labels"].items():
            key = (label, *cell_of(i, keys))
            repeats[key] = repeats.get(key, 0) + 1
        several = sum(1 for n in repeats.values() if n > 1)
        if several:
            design.append("replicates")
            structure["replicates"] = {"cells_with_several_rows": several, "most_rows_per_cell": max(repeats.values())}
        if not design:
            design.append("independent")

    ruled_out = []

    def rule(chart: str, because: str, instead: str):
        ruled_out.append({"chart": chart, "because": because, "instead": instead})

    per = "unit" if unit else "row"
    if "paired" in design:
        column, info = next(iter(structure["paired"].items()))
        partial = [f"{info['ids'] - complete} of {info['ids']} lack a value of {name} in some level"
                   for name, complete in info["ids_complete"].items() if complete < info["ids"]]
        rule("independent-groups plots (bars, boxes or strips side by side without links)",
             f"{info['ids_in_several_levels']} of {info['ids']} {link['name']} values occur in several levels of "
             f"{column}: the observations are paired",
             "lines joining each unit's values, or a plot of the within-unit differences"
             + (f"; {'; '.join(partial)}: show these apart or say that they are left out" if partial else ""))
    if "repeated_over_time" in design:
        rule("one pooled line or scatter that treats every row as independent",
             f"the same {link['name']} is measured at several {time['name']} values",
             "one thin line per unit, with the group summary drawn on top")
    if "replicates" in design:
        rule("any plot or n that counts each row as an independent observation",
             f"{structure['replicates']['cells_with_several_rows']} unit-and-condition cells hold several rows "
             f"(up to {structure['replicates']['most_rows_per_cell']})",
             "one value per unit (state how the rows were combined), or the rows as small points nested under their unit")
    if groups and measures:
        low = min(smallest.values())
        if all(level["rows"] == 1 for g in groups for level in group_counts[g["name"]].values()):
            rule("box plots, violins, histograms and error bars computed from this file",
                 "there is one row per group: the file holds summaries, not observations",
                 "points or bars of the given values, with error bars only from a column that states them; or a table")
        elif low < MIN_N_POINTS_ONLY:
            rule("bars of means, box plots, violins and density curves",
                 f"the smallest group has n = {low} ({per}s with a value)", "every point, with a line at the median or mean")
        elif low < MIN_N_BAR:
            rule("bars of means (with or without error bars), violins and density curves",
                 f"the smallest group has n = {low} ({per}s with a value)",
                 "every point with a median or mean line; a box plot only with the points on top")
        elif low < MIN_N_DENSITY:
            rule("violins and density curves", f"the smallest group has n = {low} ({per}s with a value)",
                 "a box plot with the points on top, or an ECDF")
    for column in measures:
        stats = column["stats"]
        positive = [v for v in column["values"].values() if v > 0]
        wide = len(positive) > 1 and max(positive) / min(positive) >= WIDE_RANGE
        skewed = stats["n"] >= 8 and abs(stats.get("skew", 0)) >= SKEWED      # skewness of a handful of values is noise
        if skewed or wide:
            why = ([f"skewness {stats['skew']:.2f}"] if skewed else []) \
                + ([f"positive values span {min(positive):g} to {max(positive):g}"] if wide else [])
            blocked = stats["zeros"] + stats["negatives"]
            rule(f"mean with SD or SEM bars for {column['name']} on a linear axis", " and ".join(why),
                 "median and interquartile range, or a log axis" if not blocked else
                 f"median and interquartile range; a log axis cannot show the {blocked} zero or negative value(s), "
                 "so say how they are drawn")
    for column in groups:
        if column["distinct"] > MAX_HUES:
            rule(f"one colour per level of {column['name']}", f"{column['distinct']} levels and a palette of {MAX_HUES} colours",
                 "small multiples, direct labels, or colour for the few levels the message is about and grey for the rest")
    if len(rows) > MANY_POINTS:
        rule("a scatter plot of single opaque markers", f"{len(rows)} rows overprint",
             "hexagonal bins or a 2D density, or small transparent rasterized points")

    for column in columns:
        if column["missing"] and column["role"] in ("measure", "time", "group"):
            notes.append(f"{column['name']}: {column['missing']} of {len(rows)} missing. Missing is not zero: leave a gap "
                         "and report the n that was plotted")
        notes += [f"{column['name']}: {note}" for note in column["notes"]]
    plotted = sum(m["n"] for m in measures)
    if measures and plotted <= 6:
        notes.append(f"only {plotted} numbers to show: a sentence or a small table may serve better than a figure")

    def public(column: dict) -> dict:
        keep = {k: v for k, v in column.items() if k not in ("values", "labels", "notes")}
        if column["role"] in ("group", "time") and column["distinct"] <= MAX_GROUP_LEVELS:
            keep["levels"] = sorted(set(column["labels"].values()),
                                    key=lambda v: (as_number(v, False) is None, as_number(v, False) or 0, v))
        return keep

    return {"tool": "researchzy-figures", "schema_version": 1,
            "file": {"path": str(args.file), "sha256": hashlib.sha256(Path(args.file).read_bytes()).hexdigest(),
                     "rows": len(rows), "columns": width},
            "columns": [public(column) for column in columns],
            "design": design, "structure": structure, "n_per_group": group_counts, "smallest_n_per_group": smallest,
            "ruled_out": ruled_out, "notes": notes}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Profile a data table before plotting it.")
    parser.add_argument("file", type=Path, help="CSV, TSV or Excel file with a header row")
    parser.add_argument("--id", help="The column that names the unit of analysis (subject, sample, run)")
    parser.add_argument("--group", action="append", help="A column of categories to compare (repeatable)")
    parser.add_argument("--pair", help="The column whose equal values link observations that belong together")
    parser.add_argument("--time", help="The column of the ordered axis (time, dose step, visit)")
    parser.add_argument("--measure", action="append", help="A numeric outcome column (repeatable)")
    parser.add_argument("--na", action="append", help="A further value that means missing, e.g. -999 (repeatable)")
    parser.add_argument("--sheet", help="Excel sheet name (default: the first sheet)")
    parser.add_argument("--name", help="Name of the profile file (default: the data file's name)")
    parser.add_argument("--out", default="figures", help="Output folder (default: figures)")
    args = parser.parse_args(argv)

    header, rows, delimiter = read_table(args.file, args.sheet)
    profile = build_profile(header, rows, args, delimiter)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{args.name or args.file.stem}.profile.json"
    target.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "file": str(args.file), "rows": profile["file"]["rows"], "profile": str(target),
        "roles": {c["name"]: c["role"] + ("" if c["role_from"] == "guess" else " (set by user)") for c in profile["columns"]},
        "design": profile["design"], "smallest_n_per_group": profile["smallest_n_per_group"],
        "ruled_out": profile["ruled_out"], "notes": profile["notes"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
