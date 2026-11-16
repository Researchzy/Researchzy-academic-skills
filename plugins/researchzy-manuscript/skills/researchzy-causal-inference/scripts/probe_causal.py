#!/usr/bin/env python3
"""Probe the shape of a data table for a causal design, before any estimate.

  probe_causal.py data.csv --design did --unit county --time year --treat policy --outcome jobs
  probe_causal.py data.csv --design did --unit county --time year --cohort first_year --cluster state
  probe_causal.py data.csv --design panel --unit firm --time year --treat exposure
  probe_causal.py data.csv --design sc --unit state --time year --treat policy
  probe_causal.py data.csv --design iv --instrument lottery --treat attended --outcome score --cluster school
  probe_causal.py data.csv --design rd --running score --cutoff 60 --treat admitted
  probe_causal.py data.csv --design weighting --treat program --covariates age,income,prior

It reads only whether the outcome is missing, never its values, and writes <out>/<data>.design.json
(--out, default causal), printing the same JSON: missing values; the facts of the design (duplicate
unit-periods, cohorts, never- and always-treated units, reversals, periods without an untreated
unit, timing, feasible leads and lags; SC donors and the smallest attainable p; IV compliance
shares; RD counts, binomial tests near the cutoff, heaping and packages); the clustering (G, treated
G, sizes, concern flags, levels not finer than the assignment level, which --assign names; default
the unit or row); and the route: matched, ambiguous, not_identifiable_yet or not_attempted.

Concern flags follow MacKinnon, Nielsen and Webb (2023): G <= 12, or 6 or fewer treated or untreated
clusters; conventions, not limits. Standard library only. Exit code 2 when the input cannot be read,
a column does not exist or a required option is missing.
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
from importlib.util import find_spec
from pathlib import Path

MISSING = frozenset({"", "na", "n/a", "nan", "null", "none", "#n/a", "."})
NEEDS = {"did": ("unit", "time"), "panel": ("unit", "time", "treat"), "sc": ("unit", "time"),
         "iv": ("instrument", "treat"), "rd": ("running", "cutoff"), "weighting": ("treat", "covariates")}
FEW_G, FEW_SIDE = 12, 6       # concern zones of MacKinnon, Nielsen and Webb (2023), not limits
FEW_MASS = 30                 # this skill's working line for a running variable with few distinct values
WINDOWS = (20, 50, 100)       # the observations nearest the cutoff, for the binomial test
RD_PACKAGES = ("rdrobust", "rddensity")


def fail(message: str):
    print(f"probe_causal: {message}", file=sys.stderr)
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
    rows = [row for row in csv.reader(text.splitlines(), delimiter=delimiter) if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        fail(f"{path} has no data rows under its header.")
    header = [name.strip() for name in rows[0]]
    return header, [(row + [""] * len(header))[:len(header)] for row in rows[1:]], hashlib.sha256(raw).hexdigest()


def number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def show(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value


def route(outcome, design=None, headline=(), benchmark=(), why=(), steps=()):
    return {"outcome": outcome, "design": design, "headline": list(headline), "benchmark": list(benchmark),
            "why": list(why), "next": list(steps)}


def binomial_p(k: int, n: int) -> float:
    """Exact two-sided binomial p-value for k of n on one side when each side has probability 1/2."""
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def panel_facts(table, args):
    """Cohorts, timing, untreated units per period and event times, from --treat or --cohort."""
    raw_times = {r["time"] for r in table if r["time"] is not None}
    if not all(number(t) is not None for t in raw_times):
        fail(f"--time {args.time} must hold numbers (years, or periods numbered in order)")
    key = number
    periods = sorted({key(t) for t in raw_times})
    index = {p: i for i, p in enumerate(periods)}
    cells, paths, given = Counter(), defaultdict(dict), {}
    for r in table:
        if r["unit"] is None or r["time"] is None:
            continue
        cells[(r["unit"], key(r["time"]))] += 1
        paths[r["unit"]][key(r["time"])] = number(r["treat"]) if args.treat else None
        if args.cohort:
            c = number(r["cohort"])
            c = None if c is None or (c == 0 and 0 not in index) else c
            if given.setdefault(r["unit"], c) != c:
                fail(f"--cohort {args.cohort} takes several values for unit {r['unit']}")
    dupes = [f"{u} {show(t)}" for (u, t), n in cells.items() if n > 1]
    values = sorted({v for p in paths.values() for v in p.values() if v is not None})
    binary = set(values) <= {0.0, 1.0}
    first, reversals, mismatch, unchanged = {}, [], [], 0
    for unit, path in paths.items():
        seq = [path[t] for t in sorted(path) if path[t] is not None]
        unchanged += len(set(seq)) <= 1
        if args.treat and binary:
            first[unit] = next((t for t in sorted(path) if path[t] == 1), None)
            if any(a == 1 and b == 0 for a, b in zip(seq, seq[1:])):
                reversals.append(unit)
        if args.cohort:
            if args.treat and binary and first[unit] != given.get(unit):
                mismatch.append(unit)
            first[unit] = given.get(unit)
    always = sorted(u for u, g in first.items() if g is not None and g <= min(paths[u]))
    cohorts = Counter(first[u] for u in first if first[u] is not None and u not in always)
    never = sum(1 for g in first.values() if g is None)
    untreated = {p: sum(1 for u, g in first.items() if p in paths[u] and (g is None or g > p) and u not in always)
                 for p in periods}
    lags = Counter(e for g in cohorts if g in index for e in range(-index[g], len(periods) - index[g]))
    facts = {"units": len(paths), "periods": {"count": len(periods), "first": show(periods[0]) if periods else None,
                                               "last": show(periods[-1]) if periods else None},
             "duplicates": {"count": len(dupes), "examples": dupes[:5]},
             "balanced": all(len(p) == len(periods) for p in paths.values()),
             "treatment": {"values": [show(v) for v in values[:10]], "binary": binary}}
    if binary or args.cohort:
        facts.update(cohorts={str(show(g)): n for g, n in sorted(cohorts.items())}, never_treated=never,
                     always_treated=len(always), reversals=len(reversals), cohort_mismatch=len(mismatch),
                     timing="none" if not cohorts else "common" if len(cohorts) == 1 else "staggered",
                     untreated_per_period={str(show(p)): n for p, n in untreated.items()},
                     periods_without_untreated=[show(p) for p, n in untreated.items() if n == 0],
                     cohorts_not_periods=[show(g) for g in cohorts if g not in index],
                     event_times={"min": min(lags, default=None), "max": max(lags, default=None),
                                  "cohorts_per_event_time": {str(e): n for e, n in sorted(lags.items())}},
                     control_groups=(["never_treated"] if never else []) + (["not_yet_treated"] if len(cohorts) > 1 else []))
    else:
        facts["units_without_within_variation"] = unchanged
    assignment = {u: (first.get(u) if (binary or args.cohort) else tuple(sorted(p.items()))) for u, p in paths.items()}
    treated = {u for u, g in first.items() if g is not None} if (binary or args.cohort) else \
        {u for u, p in paths.items() if len({v for v in p.values() if v is not None}) > 1}
    return facts, assignment, treated, periods


def panel_route(design, f, assign_varies):
    if f["duplicates"]["count"]:
        return route("not_identifiable_yet", why=[f"{f['duplicates']['count']} unit-period pairs have several rows: "
                                                  "make one row per unit and period first"])
    if not f["treatment"]["binary"] and "cohorts" not in f:
        if design == "panel":
            return route("matched", "panel_fe", ["within"], why=["a treatment that varies within units: the within "
                         "estimator, which assumes strict exogeneity given the unit effects"],
                         steps=[f"{f['units_without_within_variation']} units never change treatment and add nothing "
                                "to the within estimate"])
        return route("not_attempted", why=["the treatment takes values other than 0 and 1: continuous or multi-valued "
                                           "treatments are outside this skill"])
    if f["reversals"]:
        return route("not_attempted", why=[f"treatment switches off again for {f['reversals']} unit(s): designs where "
                                           "treatment turns on and off are outside this skill"])
    if f["cohort_mismatch"] or assign_varies:
        return route("ambiguous", why=[f"--cohort and --treat disagree for {f['cohort_mismatch']} unit(s): ask which "
                                       "column records the first treated period" if f["cohort_mismatch"] else
                                       "treatment varies within the --assign groups: ask the user at which level "
                                       "treatment was assigned"])
    cohorts = f["cohorts"]
    if f["cohorts_not_periods"]:
        return route("not_identifiable_yet", why=[f"cohorts {f['cohorts_not_periods']} are not periods of the panel"])
    if not cohorts:
        return route("not_identifiable_yet", why=["no unit is observed both before and after its treatment starts"])
    treated = sum(cohorts.values())
    if design == "sc":
        pre = -f["event_times"]["min"] if f["event_times"]["min"] is not None else 0
        if treated > 1:
            return route("ambiguous", why=[f"{treated} treated units: basic synthetic control takes one. Ask whether to "
                                           "analyse each treated unit on its own or use the DiD route"])
        if f["never_treated"] < 3 or pre < 2:
            return route("not_identifiable_yet", why=["synthetic control needs three or more never-treated donors and "
                                                      "two or more pre-treatment periods"])
        return route("matched", "sc", ["synthetic_control"], why=[f"one treated unit, {f['never_treated']} donors, "
                     f"{pre} pre-treatment periods"], steps=[f"the smallest attainable p-value is 1/(J+1) = "
                                                            f"{1 / (f['never_treated'] + 1):.4g}"])
    if not f["never_treated"] and len(cohorts) == 1:
        return route("not_identifiable_yet", why=["every treated unit adopts at the same time and no unit stays "
                                                  "untreated: there is no comparison group"])
    steps = (["a binary treatment that stays on: this is difference-in-differences, and the within estimator with "
              "period effects is TWFE"] if design == "panel" else [])
    steps += [f"{f['always_treated']} always-treated unit(s) have no pre-period and are dropped"] * bool(f["always_treated"])
    if f["periods_without_untreated"]:
        steps.append(f"no untreated unit in {f['periods_without_untreated']}: ATT(g, t) is not identified there")
    if not f["never_treated"]:
        steps.append("no never-treated units: use not-yet-treated controls")
    if len(cohorts) == 1:
        return route("matched", "did_2x2", ["twfe", "interaction_ols", "callaway_santanna"],
                     why=["one adoption date and never-treated units: a 2x2 or common-timing design"], steps=steps)
    return route("matched", "staggered_did", ["callaway_santanna"], ["twfe"],
                 why=[f"{len(cohorts)} adoption cohorts: staggered adoption, where TWFE can weigh some comparisons "
                      "negatively; Callaway-Sant'Anna is the headline and TWFE stands beside it"], steps=steps)


def clustering(units, assignment, treated, args):
    """G, treated G and sizes per level; which levels are at or above the assignment level."""
    level_of = {"unit": args.unit or "row", "assign": args.assign, "cluster": args.cluster}
    assign_col = args.assign or level_of["unit"]
    out, notes = {"assignment": assign_col, "cluster": args.cluster or assign_col, "levels": {}}, []
    groups_of_assign = {u: units[u].get("assign", u) if args.assign else u for u in units}
    for role in ("unit", "assign", "cluster"):
        col = level_of[role]
        if not col or col in out["levels"]:
            continue
        member = {u: (u if role == "unit" else units[u].get(role)) for u in units}
        members = defaultdict(set)
        for u, g in member.items():
            if g is not None:
                members[g].add(u)
        spans = defaultdict(set)
        for u, g in member.items():
            spans[groups_of_assign[u]].add(g)
        sizes = [len(m) for m in members.values()] or [0]
        out["levels"][col] = {"G": len(members), "G_treated": sum(1 for m in members.values() if m & treated),
                              "units_per_cluster": {"min": min(sizes), "median": statistics.median(sizes), "max": max(sizes)},
                              "treatment_constant": all(len({assignment.get(u) for u in m}) <= 1 for m in members.values()),
                              "at_or_above_assignment": all(len(s) == 1 for s in spans.values())}
    chosen = out["levels"][out["cluster"]]
    flags = [f"G = {chosen['G']} <= {FEW_G}"] * (chosen["G"] <= FEW_G)
    flags += [f"treated G = {chosen['G_treated']} <= {FEW_SIDE}"] * (chosen["G_treated"] <= FEW_SIDE)
    flags += [f"untreated G = {chosen['G'] - chosen['G_treated']} <= {FEW_SIDE}"] * (chosen["G"] - chosen["G_treated"] <= FEW_SIDE)
    out.update(flags=flags, finer_than_assignment=not chosen["at_or_above_assignment"])
    if out["finer_than_assignment"]:
        notes.append(f"clusters of {out['cluster']} are finer than the assignment level {assign_col}: cluster by "
                     f"{assign_col} or coarser")
    level = out["levels"].get(args.cluster) or {}
    if args.cluster and not args.assign and level.get("treatment_constant") and level["units_per_cluster"]["max"] > 1:
        notes.append(f"treatment is constant within every {args.cluster}: if {args.cluster} assigned it, run again "
                     f"with --assign {args.cluster}")
    varies = bool(args.assign) and not out["levels"][args.assign]["treatment_constant"]
    return out, notes, varies


def rd_route(table, args):
    """Counts on each side, binomial tests near the cutoff, heaping, sharp or fuzzy, and the RD packages."""
    x, c = [number(r["running"]) for r in table if r["running"] is not None], args.cutoff
    if any(v is None for v in x):
        fail(f"--running {args.running} has values that are not numbers")
    below, near = [v for v in x if v < c], sorted(x, key=lambda v: (abs(v - c), v))
    packages = {name: find_spec(name) is not None for name in RD_PACKAGES}
    facts = {"cutoff": show(c), "below": len(below), "at_or_above": len(x) - len(below),
             "distinct_values": {"all": len(set(x)), "below": len(set(below)), "at_or_above": len(set(x) - set(below))},
             "binomial": [{"nearest": k, "below": sum(v < c for v in near[:k]), "at_or_above": sum(v >= c for v in near[:k]),
                           "p": binomial_p(sum(v < c for v in near[:k]), k)} for k in WINDOWS if len(x) >= k],
             "most_common_values": [{"value": show(v), "count": n, "share": n / len(x)} for v, n in Counter(x).most_common(5)],
             "packages": packages}
    if args.treat:
        sides = defaultdict(list)
        for r in table:
            if number(r["running"]) is not None and number(r["treat"]) is not None:
                sides[number(r["running"]) >= c].append(number(r["treat"]))
        share = {key: sum(sides[side]) / len(sides[side]) if sides[side] else None
                 for key, side in (("below", False), ("at_or_above", True))}
        facts.update(treated_share=share, sharp=share["below"] in (0, None) and share["at_or_above"] in (1, None))
    steps = [f"{len(set(x))} distinct values (at most {FEW_MASS}, this skill's working line): the estimate "
             "extrapolates between mass points; say so"] * (len(set(x)) <= FEW_MASS)
    steps += ["fuzzy design: the estimand is the effect for compliers at the cutoff"] * (facts.get("sharp") is False)
    if not below or len(below) == len(x):
        return facts, route("not_identifiable_yet", why=["no observations on one side of the cutoff"])
    if not all(packages.values()):
        return facts, route("not_attempted", why=["regression discontinuity needs the rdrobust and rddensity packages (GPL, "
                            "installed only with the user's consent, called but never copied); missing: "
                            + ", ".join(n for n, ok in packages.items() if not ok)])
    return facts, route("matched", "rd", ["rdrobust"], why=["observations on both sides of the cutoff"], steps=steps)


def binary_route(table, rows, cell, covariates, args):
    """IV: compliance shares of a binary instrument and treatment. Weighting: group sizes, missing covariates."""
    iv, name = args.design == "iv", args.instrument if args.design == "iv" else args.treat
    pairs = [(number(r["instrument"] if iv else r["treat"]), number(r["treat"])) for r in table]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    zs, ds = {a for a, _ in pairs}, {b for _, b in pairs}
    facts = {"rows_used": len(pairs), "values": sorted(show(a) for a in zs)[:10]}
    if not iv:
        facts.update(treated=sum(a == 1 for a, _ in pairs), control=sum(a == 0 for a, _ in pairs),
                     rows_missing_a_covariate=sum(1 for row in rows if any(cell(row, c) is None for c in covariates)))
        if not zs <= {0.0, 1.0}:
            return facts, route("not_attempted", why=[f"{name} is not 0/1: weighting here takes a binary treatment"])
        if min(facts["treated"], facts["control"]) < 2:
            return facts, route("not_identifiable_yet", why=["fewer than two treated or two control units"])
        return facts, route("matched", "weighting", ["ipw", "aipw"], why=["a binary treatment and covariates"])
    if len(zs) < 2 or len(ds) < 2:
        return facts, route("not_identifiable_yet", why=["the instrument or the treatment does not vary"])
    if all(a == b for a, b in pairs):
        return facts, route("not_identifiable_yet", why=["the instrument equals the treatment: that is not an IV design"])
    if zs <= {0.0, 1.0} and ds <= {0.0, 1.0}:
        p1, p0 = (sum(b for a, b in pairs if a == z) / sum(1 for a, _ in pairs if a == z) for z in (1, 0))
        facts["compliance"] = {"treated_if_instrument_1": p1, "treated_if_instrument_0": p0, "compliers": p1 - p0,
                               "always_takers": p0, "never_takers": 1 - p1}
    return facts, route("matched", "iv", ["2sls"], ["ols"], why=[f"{name} varies with the treatment"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Probe the shape of a data table for a causal design.")
    parser.add_argument("file", type=Path, help="CSV or TSV file with a header row")
    parser.add_argument("--design", required=True, choices=sorted(NEEDS), help="The design asked about")
    for name, text in (("unit", "the unit (county, firm, person)"), ("time", "the period"),
                       ("treat", "the treatment, 0/1 (or continuous for --design panel)"),
                       ("cohort", "the first treated period, missing for never-treated units"),
                       ("outcome", "the outcome (only its missingness is read)"), ("cluster", "the clusters"),
                       ("assign", "the level at which treatment was assigned"), ("instrument", "the instrument"),
                       ("running", "the RD running variable")):
        parser.add_argument(f"--{name}", help=f"Column of {text}")
    parser.add_argument("--cutoff", type=float, help="The RD cutoff; units at or above it are on the treated side")
    parser.add_argument("--covariates", default="", help="Comma-separated pre-treatment covariates (weighting)")
    parser.add_argument("--na", action="append", default=[], help="A further value that means missing (repeatable)")
    parser.add_argument("--out", default="causal", help="Output folder (default: causal)")
    args = parser.parse_args(argv)
    covariates = [c.strip() for c in args.covariates.split(",") if c.strip()]
    for need in NEEDS[args.design]:
        if not (covariates if need == "covariates" else getattr(args, need) is not None):
            fail(f"--design {args.design} needs --{need}")
    if args.design in ("did", "sc") and not (args.treat or args.cohort):
        fail(f"--design {args.design} needs --treat or --cohort")
    header, rows, digest = read_table(args.file)
    roles = ("unit", "time", "treat", "cohort", "outcome", "cluster", "assign", "instrument", "running")
    columns = {role: getattr(args, role) for role in roles if getattr(args, role)}
    for name in list(columns.values()) + covariates:
        if name not in header:
            fail(f"{name!r} is not a column. Columns: {', '.join(header)}")
    tokens = MISSING | {t.strip().lower() for t in args.na}

    def cell(row, name):
        value = row[header.index(name)].strip() if name else None
        return None if value is None or value.lower() in tokens else value

    table = [{role: cell(row, columns.get(role)) for role in roles} for row in rows]
    missing = {name: sum(1 for row in rows if cell(row, name) is None) for name in list(columns.values()) + covariates}
    units, seen, notes = defaultdict(dict), defaultdict(set), []
    for i, r in enumerate(table):
        u = r["unit"] if args.unit else str(i)
        if u is None:
            continue
        entry = units[u]
        for role in ("cluster", "assign"):
            if r[role] is not None:
                entry.setdefault(role, r[role])
                seen[(role, u)].add(r[role])
    for role in ("cluster", "assign"):
        spread = sum(1 for (r_, _), values in seen.items() if r_ == role and len(values) > 1)
        if spread:
            notes.append(f"{spread} unit(s) have several values of {getattr(args, role)}; the first one is used")
    if args.design in ("did", "panel", "sc"):
        facts, assignment, treated, _ = panel_facts(table, args)
    else:
        facts, assignment, treated = {}, {}, set()
        for i, r in enumerate(table):
            u = r["unit"] if args.unit else str(i)
            assignment.setdefault(u, {"iv": r["instrument"], "rd": r["running"], "weighting": r["treat"]}[args.design])
            x = number(r["running"]) if args.design == "rd" else None     # the assigned side: cutoff, instrument, treatment
            if (x is not None and x >= args.cutoff) if args.design == "rd" else \
                    number(r["instrument" if args.design == "iv" else "treat"]) == 1:
                treated.add(u)
    cluster_facts, cluster_notes, varies = clustering(units, assignment, treated, args)
    if args.design in ("did", "panel", "sc"):
        verdict = panel_route(args.design, facts, varies)
    else:
        facts, verdict = rd_route(table, args) if args.design == "rd" else binary_route(table, rows, cell, covariates, args)
    verdict["next"] += cluster_notes
    for name, count in missing.items():
        if count:
            notes.append(f"{name}: {count} of {len(rows)} missing; say in the plan how they are handled")
    report = {"tool": "researchzy-causal-inference", "schema_version": 1, "design_asked": args.design,
              "file": {"path": str(args.file), "sha256": digest, "rows": len(rows)}, "columns": columns,
              "covariates": covariates, "missing": missing, "facts": facts, "clustering": cluster_facts,
              "route": verdict, "notes": notes}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    (out / f"{args.file.stem}.design.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
