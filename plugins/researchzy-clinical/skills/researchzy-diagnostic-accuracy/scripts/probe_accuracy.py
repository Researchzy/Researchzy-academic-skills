#!/usr/bin/env python3
"""Probe a diagnostic-accuracy or prediction-model data table before any estimate.

  probe_accuracy.py data.csv --id patient_id --reference biopsy --positive malignant --design consecutive
  probe_accuracy.py data.csv --id patient_id --unit nodule_id --reference biopsy --positive 1 \\
      --index biomarker --threshold 2.5 --split split --development development --test test \\
      --predictors age,size,smoker --date scan_date --design consecutive

The user names every column and value; nothing is guessed. Writes <out>/<data>.probe.json (--out,
default diagnostic-accuracy) and prints it. Each check is ok, problem or not_checked with a reason.
Patient ids are never printed: rows are named by their row number in the file (the header is row 1).

  reference        the reference standard has exactly two values, one of them --positive
  verification     rows without the reference standard, by split and by index result (partial
                   verification); the index result is --index-positive, or the score >= --threshold
  index_missing    rows with a reference value but no index result
  repeated_ids     patients with several rows (lesions, visits): analyse by patient; the same
                   --unit twice for one patient is a duplicate
  splits           units, patients, positives, negatives and prevalence per split value
  overlap          patients in more than one split; a row with an empty id or split is a problem too
  identical_rows   the same predictor values in two splits (one patient under two ids?)
  date_order       with --date: every development date before every test date (a temporal split)
  events           events (the rarer outcome) per candidate parameter in the development rows, a
                   categorical predictor counting its levels - 1; reported with no pass mark
  separation       complete or quasi-complete separation of the development rows by the predictors,
                   by linear programming; needs scipy, otherwise not_checked

"leakage" sums up overlap and date_order: ok, problem, or not_checked without --split. Exit code 1
when a patient is in two splits, the positive value is absent, or the reference standard does not
have exactly two values; 2 when the file cannot be read, a column does not exist or an option is
missing. Standard library only; scipy optional.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

MISSING = frozenset({"", "na", "n/a", "nan", "null", "none", "#n/a", ".", "missing", "缺失"})
DESIGNS = ("consecutive", "cross_sectional", "case_control", "enriched")
SHOWN = 10                     # row numbers listed per finding
TOLERANCE = 1e-6               # an LP optimum above this counts as separation
FULL_WIDTH = str.maketrans("０１２３４５６７８９．－＋", "0123456789.-+")


def fail(message: str):
    print(f"probe_accuracy: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_table(path: Path) -> tuple:
    if not path.is_file():
        fail(f"no such file: {path}")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    delimiter = "\t" if path.suffix.lower() in (".tsv", ".tab") else max(",;\t|", key=text.split("\n", 1)[0].count)
    rows = [(i + 1, row) for i, row in enumerate(csv.reader(text.splitlines(), delimiter=delimiter))]
    rows = [(i, row) for i, row in rows if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        fail(f"{path} has no data rows under its header")
    header = [name.strip() for name in rows[0][1]]
    return header, [(i, (row + [""] * len(header))[:len(header)]) for i, row in rows[1:]], hashlib.sha256(raw).hexdigest()


def number(text):
    try:
        value = float(str(text).translate(FULL_WIDTH))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def date(text):
    """(year, month, day) from 2021-03-05, 2021/3/5 or 2021年3月5日; None otherwise."""
    m = re.match(r"\s*(\d{4})\D{1,2}(\d{1,2})\D{1,2}(\d{1,2})(?!\d)", str(text).translate(FULL_WIDTH))
    if not m or not (1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31):
        return None
    return tuple(int(g) for g in m.groups())


def listed(rows) -> dict:
    rows = sorted(rows)
    return {"count": len(rows), "rows": rows[:SHOWN] + ([f"and {len(rows) - SHOWN} more"] if len(rows) > SHOWN else [])}


def check(status, reason, **facts) -> dict:
    return {"status": status, "reason": reason, **facts}


def same(value, wanted) -> bool:
    a, b = number(value), number(wanted)
    return value == wanted or (a is not None and a == b)


def verification(table, args):
    """Rows without the reference standard, by split and by index result."""
    def index_class(r):
        if r["index"] is None:
            return "index_missing"
        if args.index_positive is not None:
            return "index_positive" if same(r["index"], args.index_positive) else "index_negative"
        if args.threshold is not None:
            value = number(r["index"])
            return "index_not_a_number" if value is None else "index_positive" if value >= args.threshold else "index_negative"
        return "index_given" if args.index else "all"

    counts = defaultdict(lambda: defaultdict(lambda: {"rows": 0, "missing": 0}))
    for r in table:
        cell = counts[r["split"] or "(no split)" if args.split else "all"][index_class(r)]
        cell["rows"] += 1
        cell["missing"] += r["reference"] is None
    by = {s: {k: {**c, "share": round(c["missing"] / c["rows"], 4)} for k, c in sorted(groups.items())}
          for s, groups in sorted(counts.items())}
    missing = [r["row"] for r in table if r["reference"] is None]
    if not missing:
        return check("ok", "every row has the reference standard", by=by)
    return check("problem", f"{len(missing)} of {len(table)} rows have no reference standard: partial verification. "
                 "Report the counts by index result; do not drop the rows silently. Correcting verification bias is "
                 "outside this skill", by=by, **listed(missing))


def predictors_of(table, names):
    """Numeric predictors as floats; categorical ones (any non-number) with their levels."""
    kinds = {}
    for name in names:
        values = [r["predictors"][name] for r in table if r["predictors"][name] is not None]
        if values and all(number(v) is not None for v in values):
            kinds[name] = None
        else:
            kinds[name] = sorted(set(values))
    return kinds


def separation(rows, kinds):
    """Complete or quasi-complete separation by linear programming: is there a direction b, not all
    zero in effect, with (2y - 1) x.b >= 0 for every row (quasi), or > 0 for every row (complete)?"""
    try:
        from scipy.optimize import linprog
    except ImportError:
        return check("not_checked", "scipy is not installed: the separation check needs scipy.optimize.linprog")
    columns, names = [[1.0] * len(rows)], ["(intercept)"]
    for name, levels in kinds.items():
        if levels is None:
            values = [number(r["predictors"][name]) for r in rows]
            scale = max(abs(v) for v in values) or 1.0
            columns.append([v / scale for v in values])
            names.append(name)
        else:
            for level in levels[1:]:
                columns.append([float(r["predictors"][name] == level) for r in rows])
                names.append(f"{name}={level}")
    signed = [[(1 if r["y"] else -1) * col[i] for col in columns] for i, r in enumerate(rows)]
    k = len(columns)
    quasi = linprog([-sum(row[j] for row in signed) for j in range(k)], A_ub=[[-v for v in row] for row in signed],
                    b_ub=[0.0] * len(rows), bounds=[(-1, 1)] * k)
    if quasi.status != 0:
        return check("not_checked", f"the linear program did not solve: {quasi.message}")
    if -quasi.fun <= TOLERANCE:
        return check("ok", f"no separation of {len(rows)} complete development rows by {len(kinds)} predictor(s)")
    complete = linprog([0.0] * k + [-1.0], A_ub=[[-v for v in row] + [1.0] for row in signed], b_ub=[0.0] * len(rows),
                       bounds=[(-1, 1)] * k + [(0, 1)])
    kind = "complete" if complete.status == 0 and -complete.fun > TOLERANCE else "quasi-complete"
    involved = [names[j] for j in range(1, k) if abs(quasi.x[j]) > TOLERANCE]
    return check("problem", f"{kind} separation: a combination of {', '.join(involved) or 'the intercept'} splits the "
                 "outcomes, so a maximum-likelihood logistic fit has no finite estimate. Ask the user; penalised or "
                 "exact methods are a plan decision", kind=kind, involved=involved, rows_used=len(rows))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Probe a diagnostic-accuracy or prediction-model table.")
    parser.add_argument("file", type=Path, help="CSV or TSV file with a header row")
    parser.add_argument("--id", required=True, help="Column of the patient id")
    parser.add_argument("--reference", required=True, help="Column of the reference standard")
    parser.add_argument("--positive", required=True, help="The reference value that means the condition is present")
    parser.add_argument("--unit", help="Column of the unit within a patient (lesion, nodule, visit)")
    parser.add_argument("--index", help="Column of the index test result or score")
    parser.add_argument("--index-positive", help="The --index value that means a positive result")
    parser.add_argument("--threshold", type=float, help="The planned cut-off: a score at or above it is positive")
    parser.add_argument("--split", help="Column of the user's split")
    parser.add_argument("--development", help="The --split value of the development rows")
    parser.add_argument("--test", help="The --split value of the test rows")
    parser.add_argument("--date", help="Column of dates, for a temporal split")
    parser.add_argument("--predictors", default="", help="Comma-separated candidate predictors")
    parser.add_argument("--design", choices=DESIGNS, help="How the units were sampled")
    parser.add_argument("--na", action="append", default=[], help="A further value that means missing (repeatable)")
    parser.add_argument("--out", default="diagnostic-accuracy", help="Output folder (default: diagnostic-accuracy)")
    args = parser.parse_args(argv)
    predictors = [p.strip() for p in args.predictors.split(",") if p.strip()]
    for option, needs in (("index_positive", "index"), ("threshold", "index"), ("development", "split"),
                          ("test", "split"), ("date", "development"), ("date", "test")):
        if getattr(args, option) is not None and getattr(args, needs) is None:
            fail(f"--{option.replace('_', '-')} needs --{needs}")
    if args.index_positive is not None and args.threshold is not None:
        fail("give --index-positive for a categorical result or --threshold for a score, not both")
    header, rows, digest = read_table(args.file)
    roles = {"id": args.id, "reference": args.reference, "unit": args.unit, "index": args.index, "split": args.split,
             "date": args.date}
    for name in [c for c in roles.values() if c] + predictors:
        if name not in header:
            fail(f"{name!r} is not a column. Columns: {', '.join(header)}")
    tokens = MISSING | {t.strip().lower() for t in args.na}

    def cell(row, name):
        value = row[header.index(name)].strip() if name else None
        return None if value is None or value.lower() in tokens else value

    table = [{"row": i, **{role: cell(row, name) for role, name in roles.items()},
              "predictors": {p: cell(row, p) for p in predictors}} for i, row in rows]
    checks, exit_code = {}, 0

    values = Counter(r["reference"] for r in table if r["reference"] is not None)
    has_positive = any(same(v, args.positive) for v in values)
    if not has_positive or len(values) != 2:
        exit_code = 1
        why = (f"--positive {args.positive!r} does not occur" if not has_positive else
               f"{len(values)} distinct value(s): the reference standard must have two (multiclass outcomes are outside "
               "this skill)")
        checks["reference"] = check("problem", why, values=len(values), counts=sorted(values.values(), reverse=True))
    else:
        checks["reference"] = check("ok", "two values, one of them the positive value", counts={
            "positive": sum(n for v, n in values.items() if same(v, args.positive)),
            "negative": sum(n for v, n in values.items() if not same(v, args.positive))})
    for r in table:
        r["y"] = None if r["reference"] is None else int(same(r["reference"], args.positive))
    checks["verification"] = verification(table, args)
    if args.index:
        gaps = [r["row"] for r in table if r["reference"] is not None and r["index"] is None]
        checks["index_missing"] = check("problem" if gaps else "ok", f"{len(gaps)} verified row(s) have no index result"
                                        if gaps else "every verified row has an index result", **listed(gaps))
    else:
        checks["index_missing"] = check("not_checked", "no --index given")

    empty_id = [r["row"] for r in table if r["id"] is None]
    per_patient = Counter(r["id"] for r in table if r["id"] is not None)
    several = {p for p, n in per_patient.items() if n > 1}
    twice = Counter((r["id"], r["unit"]) for r in table if r["id"] is not None and r["unit"] is not None)
    duplicates = [r["row"] for r in table if r["unit"] is not None and twice[(r["id"], r["unit"])] > 1]
    facts = {"patients": len(per_patient), "units": sum(per_patient.values()),
             "patients_with_several_rows": len(several), "most_rows_per_patient": max(per_patient.values(), default=0),
             "duplicate_units": listed(duplicates)}
    if several or duplicates:
        checks["repeated_ids"] = check("problem", (f"{len(several)} patients have several rows: intervals come from a "
                                       "bootstrap by patient, and resampling and splits keep a patient's rows together")
                                       + (f"; {len(duplicates)} rows repeat a --unit of their patient" if duplicates
                                          else ""), **facts)
    else:
        checks["repeated_ids"] = check("ok", "one row per patient", **facts)

    if args.split:
        by_split = defaultdict(list)
        for r in table:
            by_split[r["split"]].append(r)
        counts = {}
        for name, members in sorted(by_split.items(), key=lambda kv: str(kv[0])):
            pos, neg = sum(r["y"] == 1 for r in members), sum(r["y"] == 0 for r in members)
            counts[name or "(empty)"] = {"units": len(members), "patients": len({r["id"] for r in members if r["id"]}),
                                         "positives": pos, "negatives": neg,
                                         "prevalence": round(pos / (pos + neg), 4) if pos + neg else None}
        lacking = [s for s, c in counts.items() if not (c["positives"] and c["negatives"])]
        checks["splits"] = check("problem" if lacking else "ok", f"split(s) without both outcomes: {', '.join(lacking)}"
                                 if lacking else "every split has positive and negative units", counts=counts)
        homes = defaultdict(set)
        for r in table:
            if r["id"] is not None and r["split"] is not None:
                homes[r["id"]].add(r["split"])
        crossing = {p for p, s in homes.items() if len(s) > 1}
        empty_split = [r["row"] for r in table if r["split"] is None]
        if crossing:
            exit_code = 1
        reasons = ([f"{len(crossing)} patient(s) have rows in more than one split"] if crossing else [])
        reasons += [f"{len(empty_id)} row(s) have no id"] * bool(empty_id)
        reasons += [f"{len(empty_split)} row(s) have no split"] * bool(empty_split)
        checks["overlap"] = check("problem" if reasons else "ok", "; ".join(reasons) or "no patient is in two splits",
                                  patients=len(crossing), rows=listed([r["row"] for r in table if r["id"] in crossing])["rows"],
                                  empty_id_rows=listed(empty_id), empty_split_rows=listed(empty_split))
    else:
        for name in ("splits", "overlap"):
            checks[name] = check("not_checked", "no --split given")

    complete = [r for r in table if all(v is not None for v in r["predictors"].values())]
    if args.split and predictors:
        def values_of(r):
            return tuple(v if number(v) is None else number(v) for v in r["predictors"].values())
        seen = defaultdict(set)
        for r in complete:
            if r["split"] is not None:
                seen[values_of(r)].add(r["split"])
        shared = [r["row"] for r in complete if len(seen[values_of(r)]) > 1]
        checks["identical_rows"] = check("problem" if shared else "ok", f"{len(shared)} rows share all predictor values "
                                         "with a row in another split: check whether they are one patient under two ids"
                                         if shared else "no predictor row appears in two splits", **listed(shared))
    else:
        checks["identical_rows"] = check("not_checked", "needs --split and --predictors")

    if args.date:
        dated = {k: [(date(r["date"]), r["row"]) for r in table if r["split"] == v] for k, v in
                 (("development", args.development), ("test", args.test))}
        unread = [row for pairs in dated.values() for d, row in pairs if d is None]
        dev, test = [d for d, _ in dated["development"] if d], [d for d, _ in dated["test"] if d]
        if not dev or not test:
            checks["date_order"] = check("not_checked", "no readable dates in the development or the test rows",
                                         unread=listed(unread))
        else:
            late = [row for d, row in dated["development"] if d and d >= min(test)]
            why = ([f"{len(late)} development row(s) are dated on or after the first test date"] if late else [])
            why += [f"{len(unread)} date(s) could not be read: write them as YYYY-MM-DD"] * bool(unread)
            checks["date_order"] = check("problem" if why else "ok", "; ".join(why) or "every development date precedes "
                                         "every test date", development="{}-{:02d}-{:02d} to ".format(*min(dev)) +
                                         "{}-{:02d}-{:02d}".format(*max(dev)), test="{}-{:02d}-{:02d} to ".format(
                                             *min(test)) + "{}-{:02d}-{:02d}".format(*max(test)), late=listed(late),
                                         unread=listed(unread))
    else:
        checks["date_order"] = check("not_checked", "no --date given: the split is not checked as a temporal one")

    fitting = [r for r in complete if r["y"] is not None and (r["split"] == args.development if args.development else True)]
    if predictors and fitting:
        kinds = predictors_of(fitting, predictors)
        parameters = sum(1 if levels is None else max(len(levels) - 1, 0) for levels in kinds.values())
        events = min(sum(r["y"] for r in fitting), sum(1 - r["y"] for r in fitting))
        checks["events"] = check("ok", "reported for the user to judge; no pass mark", events=events,
                                 parameters=parameters, rows=len(fitting),
                                 per_parameter=round(events / parameters, 2) if parameters else None,
                                 categorical={k: len(v) for k, v in kinds.items() if v is not None})
        checks["separation"] = separation(fitting, kinds) if events else check("problem", "only one outcome class")
    else:
        for name in ("events", "separation"):
            checks[name] = check("not_checked", "needs --predictors and development rows with the reference standard")

    if not args.split:
        leakage = check("not_checked", "no --split given: nothing to compare")
    else:
        bad = [k for k in ("overlap", "date_order") if checks[k]["status"] == "problem"]
        leakage = check("problem" if bad else "ok", f"problems in {', '.join(bad)}" if bad else
                        "no patient in two splits" + (" and the dates are in order" if checks["date_order"]["status"]
                                                      == "ok" else ""))
    if args.design in ("case_control", "enriched"):
        note = "refused unless the target population's prevalence is given with its source"
    else:
        note = "from the table" if args.design else "not_checked: no --design given"
    report = {"tool": "researchzy-diagnostic-accuracy", "schema_version": 1,
              "file": {"path": str(args.file), "sha256": digest, "rows": len(table)},
              "columns": {k: v for k, v in roles.items() if v}, "predictors": predictors, "positive": args.positive,
              "threshold": args.threshold, "index_positive": args.index_positive, "design": args.design,
              "split_values": {"development": args.development, "test": args.test}, "predictive_values": note,
              "checks": checks, "leakage": leakage, "problems": [k for k, c in checks.items() if c["status"] == "problem"],
              "exit": exit_code}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    (out / f"{args.file.stem}.probe.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
