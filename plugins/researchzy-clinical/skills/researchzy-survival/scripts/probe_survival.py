#!/usr/bin/env python3
"""Probe a time-to-event table before any survival model is fitted.

  probe_survival.py data.csv --time days --event status --time-unit days --map 1=0,2=1 --group arm
  probe_survival.py data.csv --time days --event status --time-unit days --map 1=0,2=1 --group arm --id patient_id \
      --covariates age,stage,ecog,adjuvant --categorical stage,ecog,adjuvant \
      --zero-date diagnosis_date --known-date adjuvant=adjuvant_start
  probe_survival.py data.csv --time stop --start start --event death --id patient_id --time-unit days
  probe_survival.py data.csv --time months --event status --time-unit months --map 0=0,1=1,2=2

--map CODE=VALUE (repeatable, or comma-separated) is what each event code as written means, as the user confirmed
it: 0 censored, 1 the event, 2, 3 ... competing events. Without --map the codes must already be 0 and 1. --time-unit
is what the user said; the probe never guesses it from the numbers. --start names the entry column of start-stop rows.

Writes <out>/<data>.probe.json (--out, default survival) and prints it. Each check is ok, problem or not_checked,
with its detail:

  time_unit        given by the user, or not_checked
  event_codes      the codes as written and after the mapping: 0 and 1 (2, 3 ... only as mapped competing events);
                   1/2, words or booleans without a mapping are a problem: ask what they mean
  times            missing, non-numeric, negative and zero times, and bad start times, by row
  ties             events that share their time with another event
  ids              a repeated id: identical rows are duplicates; start-stop rows may repeat an id when their
                   intervals do not overlap
  groups           events, censorings and competing events per group and per stratum; a group without events
  complete_cases   complete rows for the group alone and with the covariates; missing values per column, by row
  parameters       events per parameter (a categorical covariate counts its levels minus one): a count, no pass mark
  followup         per group: reverse Kaplan-Meier median follow-up, longest time, lowest Kaplan-Meier estimate, and
                   whether it falls below 0.5 (otherwise the median will be not reached)
  time_zero        per grouping variable: known at time zero, from --zero-date and --known-date VAR=DATECOL (a later
                   date gives immortal time), from the user (--known-at-zero VAR), or not_checked

and a route: standard (Kaplan-Meier and Cox), start_stop, landmark_or_start_stop, competing_risks, or stop_and_ask
with the reasons and the route that follows the answers. Rows are numbered from 1 under the header; no id, date or
other value of a row is printed.

Exit code 0; 1 when the event codes are not 0/1 after the mapping, a time is negative, or an id repeats outside
start-stop rows (or start-stop intervals overlap); 2 when the file cannot be read or a column does not exist.
Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

MISSING = frozenset({"", "na", "n/a", "nan", "null", "none", "#n/a", "."})
DATES = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d")
SHOWN = 20                    # rows listed per finding; the counts are always complete
BLOCKING = ("time_unit", "event_codes", "times", "ids", "groups")


def fail(message: str):
    print(f"probe_survival: {message}", file=sys.stderr)
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


def code(value: str) -> str:
    """A code or level as written, with "2.0" and "2" the same; "" when missing."""
    text = value.strip()
    if text.lower() in MISSING:
        return ""
    try:
        found = float(text)
    except ValueError:
        return text
    return str(int(found)) if found.is_integer() else text


def number(value: str):
    try:
        found = float(value)
    except ValueError:
        return None
    return found if math.isfinite(found) else None


def listed(rows) -> str:
    rows = sorted(rows)
    return ", ".join(map(str, rows[:SHOWN])) + (f" and {len(rows) - SHOWN} more" if len(rows) > SHOWN else "")


def check(status: str, detail: str, **data) -> dict:
    return {"status": status, "detail": detail, **data}


def kaplan_meier(items: list) -> list:
    """[(time, S just after it)] at the event times of items (time, is_event, entry); at risk: entry < t <= time."""
    exits, entries = sorted(t for t, _, _ in items), sorted(a for _, _, a in items)
    events, s, out = Counter(t for t, e, _ in items if e), 1.0, []
    for t in sorted(events):
        at_risk = bisect_left(entries, t) - bisect_left(exits, t)
        s *= 1 - events[t] / at_risk if at_risk > 0 else 1.0
        out.append((t, s))
    return out


def parse_map(values: list) -> dict:
    mapping = {}
    for item in (part for value in values for part in value.split(",") if part.strip()):
        raw, _, meaning = item.partition("=")
        if not raw.strip() or not meaning.strip().isdigit():
            fail(f"--map takes CODE=VALUE with VALUE 0 (censored), 1 (the event) or 2, 3 ... (competing): {item!r}")
        mapping[code(raw)] = int(meaning)
    if mapping and 1 not in mapping.values():
        fail("--map must map at least one code to 1, the event")
    return mapping


def parse_date(text: str):
    for pattern in DATES:
        try:
            return datetime.strptime(text.strip(), pattern)
        except ValueError:
            continue
    return None


def read_rows(rows, cell, args) -> tuple:
    """The event_codes and times checks, and one record per row: row, time, start, code, usable."""
    mapping, raw = parse_map(args.map), Counter(code(cell(r, args.event)) for r in rows)
    plain = set(raw) <= {"0", "1"}           # without --map only 0/1 codes have a meaning; 1/2 does not
    mapped = {c: mapping.get(c) if mapping else int(c) if plain else None for c in raw}
    unknown = sorted(c for c, m in mapped.items() if m is None)
    found_codes = {c or "(missing)": {"rows": n, "means": mapped[c]} for c, n in sorted(raw.items())}
    if unknown:
        hint = " 1 and 2 often mean censored and died, but only the user can say." if {"1", "2"} <= set(raw) else ""
        bad = [i for i, r in enumerate(rows, 1) if mapped[code(cell(r, args.event))] is None]
        codes = check("problem", f"codes {', '.join(c or '(missing)' for c in unknown)} have no meaning yet (rows "
                      f"{listed(bad)}): ask the user what each code means, then pass --map.{hint}", codes=found_codes)
    elif 1 not in mapped.values():
        codes = check("problem", "no row carries the event (code 1)", codes=found_codes)
    else:
        codes = check("ok", "after the mapping: " + ", ".join(f"{c} -> {m}" for c, m in mapped.items()), codes=found_codes)
    found, records = defaultdict(list), []
    for i, r in enumerate(rows, 1):
        t, written = number(cell(r, args.time)), code(cell(r, args.time))
        start = number(cell(r, args.start)) if args.start else float("-inf")
        kind = ("missing time" if not written else "time is not a number" if t is None else "negative time" if t < 0
                else "zero time" if t == 0 else None)
        if kind:
            found[kind].append(i)
        if args.start and (start is None or start < 0 or (t is not None and start >= t)):
            found["start time missing, negative or not before the time"].append(i)
            start = None
        m = mapped.get(code(cell(r, args.event)))
        records.append({"row": i, "time": t, "start": start, "code": m,
                        "usable": t is not None and t >= 0 and start is not None})
    detail = "; ".join(f"{k}: {len(v)} (rows {listed(v)})" for k, v in found.items())
    times = check("problem", detail + ". List them for the user; never drop them silently",
                  **{k.replace(" ", "_"): sorted(v) for k, v in found.items()}) if found else check(
        "ok", f"all {len(rows)} times are numbers of 0 or more")
    return codes, times, records, bool(unknown) or bool(found.get("negative time"))


def check_ids(rows, records, cell, args) -> dict:
    if not args.id:
        return check("not_checked", "no --id column: repeated patients cannot be found")
    by_id = defaultdict(list)
    for r, rec in zip(rows, records):
        by_id[code(cell(r, args.id))].append((rec, tuple(c.strip() for c in r)))
    repeated = {k: v for k, v in by_id.items() if k and len(v) > 1}
    notes = [f"{len(by_id[''])} rows without an id (rows {listed(rec['row'] for rec, _ in by_id[''])})"] \
        if by_id.get("") else []
    if args.start:
        overlap = set()
        for v in repeated.values():
            spans = sorted((x for x, _ in v if x["usable"]), key=lambda x: x["start"])
            overlap |= {rec["row"] for a, b in zip(spans, spans[1:]) if b["start"] < a["time"] for rec in (a, b)}
        notes += [f"intervals of the same id overlap (rows {listed(overlap)})"] if overlap else []
        ok = f"{len(by_id)} ids; {len(repeated)} have several start-stop rows, none overlapping"
    else:
        same = sum(1 for v in repeated.values() if len({cells for _, cells in v}) == 1)
        rows_repeated = listed(rec["row"] for v in repeated.values() for rec, _ in v)
        notes += [f"{len(repeated)} ids appear on more than one row (rows {rows_repeated}); "
                  f"in {same} of them the rows are identical: duplicates, not start-stop data. If the rows are "
                  "intervals of one patient, run again with --start; otherwise ask the user which row stands"] \
            if repeated else []
        ok = f"{len(by_id)} ids, each on one row"
    return check("problem" if notes else "ok", "; ".join(notes) or ok, repeated_ids=len(repeated))


def count_groups(rows, records, cell, args) -> tuple:
    """The groups check, and the usable records of each group level (all rows without a group)."""
    table, members = defaultdict(Counter), defaultdict(list)
    for r, rec in zip(rows, records):
        if not rec["usable"]:
            continue
        for name in [n for n in (args.group, args.strata) if n] or [None]:
            level = code(cell(r, name)) if name else "all"
            if not level:
                continue
            key = f"{name}={level}" if name else level
            table[key]["rows"] += 1
            table[key]["censored" if rec["code"] == 0 else "events" if rec["code"] == 1 else "competing"] += 1
            if name == args.group:
                members[level].append(rec)
    table = {k: dict(v) for k, v in sorted(table.items())}
    empty = [k for k, c in table.items() if not c.get("events")]
    return check("problem" if empty else "ok", f"no events in {', '.join(empty)}: no hazard ratio for it; the user "
                 "decides whether to merge it or leave it out" if empty else "events in every group: " + "; ".join(
                     f"{k} {c.get('events', 0)} of {c['rows']}" for k, c in table.items()), counts=table), members


def check_models(rows, records, cell, args, covariates, settled) -> tuple:
    """The complete_cases and parameters checks; events are counted only when the codes are settled."""
    model = [c for c in (args.group, args.strata, *covariates) if c]
    usable = [(r, rec) for r, rec in zip(rows, records) if rec["usable"]]
    missing = {c: [rec["row"] for r, rec in usable if not code(cell(r, c))] for c in model}
    complete = [rec for r, rec in usable if all(code(cell(r, c)) for c in model)]
    alone = [rec for r, rec in usable if not args.group or code(cell(r, args.group))]
    events = sum(1 for rec in complete if rec["code"] == 1) if settled else None
    gaps = {c: v for c, v in missing.items() if v}
    cases = check("problem" if gaps else "ok", (f"{len(alone)} usable rows with the group, {len(complete)} with every "
                  "model column; missing: " + "; ".join(f"{c} {len(v)} (rows {listed(v)})" for c, v in gaps.items())
                  + ". State n per model and filter explicitly") if gaps else
                  f"{len(complete)} usable rows, none missing a model value", n_group=len(alone),
                  n_full=len(complete), events_full=events, missing={c: len(v) for c, v in missing.items()})
    categorical = {c.strip() for c in (args.categorical or "").split(",") if c.strip()} | {args.group}
    counted = {}
    for c in [c for c in (args.group, *covariates) if c]:
        levels = {code(cell(r, c)) for r in rows} - {""}
        counted[c] = max(len(levels) - 1, 0) if c in categorical or any(number(v) is None for v in levels) else 1
    total, parts = sum(counted.values()), ", ".join(f"{c} {n}" for c, n in counted.items())
    if not total or events is None:
        why = "no --group or --covariates: no model to count" if not total else (
            f"{total} parameters ({parts}); events not counted until the event codes have a confirmed meaning")
        return cases, check("not_checked", why, parameters=total, per_variable=counted)
    return cases, check("ok", f"{events} events for {total} parameters ({events / total:.1f} per parameter; {parts}). "
                        "A count, not a pass mark: the user decides what the model carries; never select covariates "
                        "by their p-values", events=events, parameters=total, per_variable=counted)


def check_followup(members, competing) -> dict:
    groups, lines = {}, []
    for level, part in sorted(members.items()):
        curve = kaplan_meier([(r["time"], r["code"] == 1 or (competing and r["code"] >= 2), r["start"]) for r in part])
        lowest = min((s for _, s in curve), default=1.0)
        reverse = kaplan_meier([(r["time"], r["code"] == 0, r["start"]) for r in part])
        groups[level] = {"median_followup": next((t for t, s in reverse if s < 0.5), "not_reached"),
                         "longest": max(r["time"] for r in part), "lowest_km": round(lowest, 4),
                         "below_half": lowest < 0.5}
        if lowest >= 0.5:
            lines.append(f"{level}: the Kaplan-Meier estimate stays at {lowest:.3f} or above, so its median will be "
                         "not reached")
    return check("ok", "; ".join(lines) or "every curve falls below 0.5", groups=groups,
                 method="reverse Kaplan-Meier for follow-up" + ("; any event for the Kaplan-Meier estimate, as there "
                                                                 "are competing events" if competing else ""))


def check_time_zero(rows, cell, args, known_dates) -> dict:
    variables, found = list(dict.fromkeys(v for v in (args.group, *known_dates, *args.known_at_zero) if v)), {}
    for var in variables:
        if var in args.known_at_zero:
            found[var] = check("ok", "known at time zero, as the user said")
            continue
        if var not in known_dates or not args.zero_date:
            found[var] = check("not_checked", f"ask the user whether {var} is known at time zero, or give the date it "
                               "became known with --zero-date and --known-date")
            continue
        delays, unread = [], 0
        for r in rows:
            start, known = parse_date(cell(r, args.zero_date)), parse_date(cell(r, known_dates[var]))
            if start is None or known is None:
                unread += bool(code(cell(r, known_dates[var])))
            else:
                delays.append((known - start).days)
        late = sorted(d for d in delays if d > 0)
        found[var] = check("problem", f"{var} becomes known after time zero in {len(late)} rows (median "
                           f"{late[len(late) // 2]} days, up to {late[-1]} days): the rows are classed by what happens "
                           "later (immortal time). Use a landmark analysis or start-stop rows with entry times",
                           late=len(late), longest_days=late[-1]) if late else check(
            "ok", f"{var} is known by time zero in all {len(delays)} rows with both dates")
        if unread:
            found[var]["unread_dates"] = unread
    states = {z["status"] for z in found.values()}
    status = "problem" if "problem" in states else "not_checked" if "not_checked" in states or not found else "ok"
    return check(status, "; ".join(f"{v}: {z['detail']}" for v, z in found.items()) or "no grouping variable named",
                 variables=found)


def probe(header: list, rows: list, args) -> tuple:
    """The checks, the route, and whether a case of exit code 1 was found."""
    covariates = [c.strip() for c in (args.covariates or "").split(",") if c.strip()]
    known_dates = dict(item.split("=", 1) for item in args.known_date)
    named = [args.time, args.event, args.start, args.group, args.strata, args.id, args.zero_date, *covariates,
             *known_dates, *known_dates.values(), *args.known_at_zero]
    absent = sorted({c for c in named if c and c not in header})
    if absent:
        fail(f"no column {', '.join(absent)}. Columns: {', '.join(header)}")
    index = {name: header.index(name) for name in named if name}

    def cell(row, name):
        return row[index[name]] if name else ""

    checks = {"time_unit": check("ok", f"{args.time_unit}, as the user said") if args.time_unit else check(
        "not_checked", "no --time-unit: ask the user; never infer the unit from the numbers")}
    checks["event_codes"], checks["times"], records, exit_one = read_rows(rows, cell, args)
    settled = checks["event_codes"]["status"] == "ok"
    checks["ids"] = check_ids(rows, records, cell, args)
    checks["complete_cases"], checks["parameters"] = check_models(rows, records, cell, args, covariates, settled)
    checks["time_zero"] = check_time_zero(rows, cell, args, known_dates)
    if not settled:
        for name in ("ties", "groups", "followup"):
            checks[name] = check("not_checked", "the event codes have no confirmed meaning: run again with --map")
        return finish(checks, args, [], exit_one)
    events = Counter(r["time"] for r in records if r["usable"] and r["code"] == 1)
    shared, total = sum(n for n in events.values() if n > 1), sum(events.values())
    checks["ties"] = check("ok", f"{shared} of {total} events share their time with another event "
                           f"({sum(1 for n in events.values() if n > 1)} shared times): use Efron's method and name it "
                           "in the methods" if shared else f"no two of the {total} events share a time",
                           events=total, events_at_shared_times=shared)
    checks["groups"], members = count_groups(rows, records, cell, args)
    competing = sorted({r["code"] for r in records if r["usable"] and r["code"] >= 2})
    checks["followup"] = check_followup(members or {"all": [r for r in records if r["usable"]]}, bool(competing))
    return finish(checks, args, competing, exit_one)


def finish(checks, args, competing, exit_one) -> tuple:
    """Order the checks, choose the route, and say whether a case of exit code 1 was found."""
    order = ("time_unit", "event_codes", "times", "ties", "ids", "groups", "complete_cases", "parameters", "followup",
             "time_zero")
    checks = {name: checks[name] for name in order}
    flow = ("competing_risks" if competing else "landmark_or_start_stop" if checks["time_zero"]["status"] == "problem"
            else "start_stop" if args.start else "standard")
    stops = [f"{name}: {checks[name]['detail']}" for name in BLOCKING
             if checks[name]["status"] == "problem" or (name == "time_unit" and checks[name]["status"] != "ok")]
    route = {"route": "stop_and_ask", "why": stops, "then": flow} if stops else {"route": flow, "why": []}
    return checks, route, exit_one or checks["ids"]["status"] == "problem"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Probe a time-to-event table before any survival model is fitted.")
    parser.add_argument("file", type=Path, help="CSV or TSV file with a header row")
    parser.add_argument("--time", required=True, help="Column of the event or censoring time (the exit time)")
    parser.add_argument("--event", required=True, help="Column of the event code")
    parser.add_argument("--time-unit", help="The unit of the time column, as the user said (days, months, ...)")
    parser.add_argument("--map", action="append", default=[], help="CODE=VALUE, repeatable or comma-separated")
    parser.add_argument("--start", help="Column of the entry time of start-stop rows")
    parser.add_argument("--group", help="Column of the groups to compare")
    parser.add_argument("--strata", help="Column of the strata")
    parser.add_argument("--covariates", help="Comma-separated candidate covariates")
    parser.add_argument("--categorical", help="Comma-separated covariates to count as categorical")
    parser.add_argument("--id", help="Column of the patient id")
    parser.add_argument("--zero-date", help="Column of the date of time zero (YYYY-MM-DD)")
    parser.add_argument("--known-date", action="append", default=[], help="VAR=DATECOL: the date VAR became known")
    parser.add_argument("--known-at-zero", action="append", default=[], help="A variable the user says is known at "
                        "time zero (repeatable)")
    parser.add_argument("--out", default="survival", help="Output folder (default: survival)")
    args = parser.parse_args(argv)
    if any("=" not in item for item in args.known_date):
        fail("--known-date takes VAR=DATECOL")
    header, rows, digest = read_table(args.file)
    checks, route, exit_one = probe(header, rows, args)
    report = {"tool": "researchzy-survival", "schema_version": 1,
              "file": {"path": str(args.file), "sha256": digest, "rows": len(rows)},
              "columns": {k: getattr(args, k) for k in ("time", "event", "start", "group", "strata", "id")},
              "time_unit": args.time_unit, "checks": checks, "route": route}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    (out / f"{args.file.stem}.probe.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return int(exit_one)


if __name__ == "__main__":
    sys.exit(main())
