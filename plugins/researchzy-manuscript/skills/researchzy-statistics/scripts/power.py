#!/usr/bin/env python3
"""Sample size, power or the detectable effect of a planned comparison, as a table and a justification.

  power.py two-means --diff 5 --sd 12 --outcome "systolic pressure at 12 weeks" --units mmHg --unit patients \\
           --effect-source prior-study --source-note "doi:10.1000/xyz123, Table 2, SD of the control arm"
  power.py two-means --diff 5 --sd1 10 --sd2 15 --ratio 2 ...   SDs not assumed equal; group 2 twice group 1
  power.py paired --diff 3 --sd-diff 6 ...                       or --sd 6 --corr 0.5 between the two occasions
  power.py two-proportions --p1 0.30 --p2 0.15 ...
  power.py correlation --r 0.3 ...
  power.py anova --means 10,12,15 --sd 6 ...                     one-way, equal groups, common SD
  ... --n 40                     the power of 40 per group instead of the n
  ... --n 40 --solve effect      the smallest effect 40 per group detect: a sensitivity analysis, not a justification
  ... --attrition 0.1 --icc 0.05 --cluster-size 20               inflate the n for drop-out and clustering

Effects are given in raw units, with the SD they are measured against where that applies.
--effect-source is required and says where the effect (in --solve effect: the SD or the baseline)
comes from: prior-study (--source-note must give the DOI and the place in the paper), pilot,
smallest-effect-of-interest, or convention (labelled as a convention everywhere it is printed).
observed is refused: power computed from a finished study's own effect adds nothing to its p-value.

How power is computed (scipy):
  two-means        Welch's t test: noncentral t, Welch-Satterthwaite df at the planned SDs and sizes
  paired           paired t test: noncentral t on the within-unit differences, df = n - 1
  two-proportions  z test of two proportions (chi-square without continuity correction): normal
                   approximation, pooled variance under the null, unpooled under the alternative
  correlation      test of Pearson's r: normal approximation through Fisher's z
  anova            F test: noncentral F with noncentrality f^2 * N, f = SD of the group means / SD
The tests in tests/test_power.py compare each with statsmodels or with a simulation.

The output is a table of n across a range of effects and powers (power across effects and n with
--n; the detectable effect across n and powers with --solve effect), never one n alone; the n
inflated for attrition and the design effect 1 + (m - 1) * ICC; and a justification paragraph with
the outcome and effect with its source, alpha and power, the test, the n with inflation, and the
software. Writes <out>/<name>.json and <name>.md (--out statistics, --name power) and prints a
JSON summary.

Needs scipy: without it prints {"status": "not_run", ...} and exits 2. Exit code 2 also for a
refused or invalid request, with the reason on stderr.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import re
import statistics
import sys
from pathlib import Path

try:
    import scipy
    from scipy import stats
except ImportError:          # reported in main(), after the request itself has been checked
    scipy = stats = None

__version__ = "1.0.0"
DESIGNS = ("two-means", "paired", "two-proportions", "correlation", "anova")
SOURCES = ("prior-study", "pilot", "smallest-effect-of-interest", "convention", "observed")
POWERS = (0.8, 0.85, 0.9, 0.95)
RANGE = (0.5, 0.75, 1.0, 1.25, 1.5)
INPUTS = ("alpha", "power", "alternative", "ratio", "n", "attrition", "icc", "cluster_size", "diff", "sd", "sd1", "sd2",
          "sd_diff", "corr", "p1", "p2", "r", "means", "groups")
MIN_N = {"two-means": 2, "paired": 2, "two-proportions": 2, "correlation": 4, "anova": 2}
MAX_N = 10_000_000
DOI = re.compile(r"10\.\d{4,9}/[^\s,;]+")
TESTS = {"two-means": "Welch two-sample t test", "paired": "paired t test",
         "two-proportions": "z test of two independent proportions (chi-square test without continuity correction)",
         "correlation": "test of Pearson's correlation (Fisher z approximation)",
         "anova": "one-way ANOVA F test (equal group sizes, common SD)"}


def fail(message: str):
    print(f"power: {message}", file=sys.stderr)
    raise SystemExit(2)


def fmt(x) -> str:
    return f"{x:.4g}" if isinstance(x, float) else str(x)


def tidy(x):
    return float(f"{x:.6g}") if isinstance(x, float) else x


def t_power(ncp: float, df: float, alpha: float, sides: int) -> float:
    crit = stats.t.ppf(1 - alpha / sides, df)
    power = stats.nct.sf(crit, df, abs(ncp))
    return float(power + (stats.nct.cdf(-crit, df, abs(ncp)) if sides == 2 else 0.0))


def normal_power(delta: float, se0: float, se1: float, alpha: float, sides: int) -> float:
    z = stats.norm.ppf(1 - alpha / sides)
    power = stats.norm.cdf((abs(delta) - z * se0) / se1)
    return float(power + (stats.norm.cdf((-abs(delta) - z * se0) / se1) if sides == 2 else 0.0))


def sizes(design: str, n: int, e: dict) -> list:
    if design in ("two-means", "two-proportions"):
        return [n, max(MIN_N[design], math.ceil(n * e["ratio"] - 1e-9))]
    return [n] * e["k"] if design == "anova" else [n]


def power_of(design: str, n: int, e: dict, alpha: float, sides: int) -> float:
    if design == "two-means":
        n1, n2 = sizes(design, n, e)
        v1, v2 = e["sd1"] ** 2 / n1, e["sd2"] ** 2 / n2
        df = (v1 + v2) ** 2 / (v1 ** 2 / (n1 - 1) + v2 ** 2 / (n2 - 1))
        return t_power(e["diff"] / math.sqrt(v1 + v2), df, alpha, sides)
    if design == "paired":
        return t_power(e["diff"] / e["sd_diff"] * math.sqrt(n), n - 1, alpha, sides)
    if design == "two-proportions":
        (n1, n2), p1, p2 = sizes(design, n, e), e["p1"], e["p2"]
        pooled = (n1 * p1 + n2 * p2) / (n1 + n2)
        se0 = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
        se1 = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
        return normal_power(p1 - p2, se0, se1, alpha, sides)
    if design == "correlation":
        se = 1 / math.sqrt(n - 3)
        return normal_power(math.atanh(e["r"]), se, se, alpha, sides)
    total, k = n * e["k"], e["k"]
    crit = stats.f.ppf(1 - alpha, k - 1, total - k)
    return float(stats.ncf.sf(crit, k - 1, total - k, e["f"] ** 2 * total))


def scaled(design: str, e: dict, k: float) -> dict:
    """The effect multiplied by k: the difference, the distance of p1 from p2, r, or f."""
    e = dict(e)
    key = {"two-means": "diff", "paired": "diff", "correlation": "r", "anova": "f"}.get(design)
    if key:
        e[key] *= k
    else:
        e["p1"] = e["p2"] + k * (e["p1"] - e["p2"])
    return e


def possible(design: str, e: dict) -> bool:
    if design == "two-proportions":
        return 0 < e["p1"] < 1
    return abs(e["r"]) < 1 if design == "correlation" else True


def solve_n(design, e, alpha, sides, target):
    """The smallest n per group (group 1 when the allocation is unequal) that reaches the target power."""
    lo = hi = MIN_N[design]
    if power_of(design, lo, e, alpha, sides) >= target:
        return lo
    while power_of(design, hi, e, alpha, sides) < target:
        lo, hi = hi, hi * 2
        if hi > MAX_N:
            return None
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (lo, mid) if power_of(design, mid, e, alpha, sides) >= target else (mid, hi)
    return hi


def solve_k(design, e, n, alpha, sides, target):
    """The smallest multiplier of the effect that reaches the target power with n per group."""
    limit = None
    if design == "correlation":
        limit = 1 / abs(e["r"])
    elif design == "two-proportions":
        limit = (1 - e["p2"] if e["p1"] > e["p2"] else e["p2"]) / abs(e["p1"] - e["p2"])
    hi = limit * (1 - 1e-9) if limit else 1.0
    while power_of(design, n, scaled(design, e, hi), alpha, sides) < target:
        if limit or hi > 1e6:
            return None
        hi *= 2
    lo = 0.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if power_of(design, n, scaled(design, e, mid), alpha, sides) >= target else (mid, hi)
    return hi


def describe(design: str, e: dict) -> dict:
    """The effect in raw units and, where there is one, its standardised form."""
    if design == "two-means":
        return {"raw": ("difference in means", e["diff"]),
                "standardised": ("d", e["diff"] / math.sqrt((e["sd1"] ** 2 + e["sd2"] ** 2) / 2))}
    if design == "paired":
        return {"raw": ("mean within-unit difference", e["diff"]), "standardised": ("d_z", e["diff"] / e["sd_diff"])}
    if design == "two-proportions":
        return {"raw": ("p1", e["p1"]), "standardised": ("risk difference", e["p1"] - e["p2"])}
    if design == "correlation":
        return {"raw": ("r", e["r"])}
    return {"raw": ("SD of the group means", e["f"] * e["sd"]), "standardised": ("Cohen's f", e["f"])}


def effect_from(args) -> dict:
    """Check the inputs of the design and turn them into the parameters power_of() takes."""
    effect_mode, e = args.solve == "effect", {"ratio": args.ratio}

    def need(name, value):
        if value is None:
            fail(f"{args.design} needs --{name}.")
        return value

    if args.ratio <= 0:
        fail("--ratio must be positive.")
    if args.design == "two-means":
        if args.sd is not None:
            e["sd1"] = e["sd2"] = args.sd
        else:
            e["sd1"], e["sd2"] = need("sd (or --sd1 and --sd2)", args.sd1), need("sd2", args.sd2)
        e["diff"] = 1.0 if effect_mode else need("diff", args.diff)
    elif args.design == "paired":
        if args.sd_diff is not None:
            e["sd_diff"] = args.sd_diff
        else:
            sd, corr = need("sd-diff (or --sd and --corr)", args.sd), need("corr", args.corr)
            if not -1 < corr < 1:
                fail("--corr must lie between -1 and 1.")
            e["sd_diff"] = sd * math.sqrt(2 * (1 - corr))      # SD of a difference of two equally variable occasions
        e["diff"] = 1.0 if effect_mode else need("diff", args.diff)
    elif args.design == "two-proportions":
        e["p2"] = need("p2", args.p2)
        e["p1"] = e["p2"] + 1 if effect_mode else need("p1", args.p1)      # effect mode searches both directions
        if not 0 < e["p2"] < 1 or not (effect_mode or 0 < e["p1"] < 1):
            fail("proportions must lie strictly between 0 and 1.")
    elif args.design == "correlation":
        e["r"] = 1.0 if effect_mode else need("r", args.r)
        if not effect_mode and not -1 < e["r"] < 1:
            fail("--r must lie strictly between -1 and 1.")
    else:
        e["sd"] = need("sd", args.sd)
        if effect_mode:
            e["k"], e["f"] = need("groups", args.groups), 1.0
        else:
            try:
                means = [float(x) for x in need("means", args.means).split(",")]
            except ValueError:
                fail("--means takes numbers separated by commas, for example 10,12,15.")
            if len(means) < 2:
                fail("--means needs at least two group means.")
            e["k"], e["means"], e["f"] = len(means), means, statistics.pstdev(means) / e["sd"]
        if e["k"] < 2:
            fail("--groups must be 2 or more.")
        if args.alternative == "one-sided":
            fail("the F test has no one-sided form.")
    if any(e.get(key) is not None and e[key] <= 0 for key in ("sd", "sd1", "sd2", "sd_diff")):
        fail("every SD must be positive.")
    if not effect_mode and describe(args.design, e)["raw"][1] == (e["p2"] if args.design == "two-proportions" else 0):
        fail("the effect is zero: no sample size detects it. Give the smallest effect that would matter.")
    return e


def check_request(args) -> list:
    """Refusals and warnings that do not need scipy."""
    if args.effect_source == "observed":
        fail("observed power is refused. Power computed from a finished study's own effect is a function of its "
             "p-value and adds nothing to it. Report the effect with its confidence interval, or run --solve effect "
             "at the achieved n and label it a sensitivity analysis.")
    if not 0 < args.alpha <= 0.5 or not args.alpha < args.power < 1:
        fail("--alpha must lie in (0, 0.5] and --power between alpha and 1.")
    if not 0 <= args.attrition < 1:
        fail("--attrition is a fraction from 0 to under 1, for example 0.15.")
    if (args.icc is None) != (args.cluster_size is None):
        fail("--icc and --cluster-size go together.")
    if args.icc is not None and (not 0 <= args.icc <= 1 or args.cluster_size < 1):
        fail("--icc must lie in [0, 1] and --cluster-size be 1 or more.")
    if args.solve == "n" and args.n is not None:
        args.solve = "power"                 # an n was given, so the question is its power
    if args.solve != "n" and args.n is None:
        fail(f"--solve {args.solve} needs --n, the n per group.")
    if args.n is not None and args.n < MIN_N[args.design]:
        fail(f"--n must be at least {MIN_N[args.design]} for {args.design}.")
    warnings = []
    note = (args.source_note or "").strip()
    if args.effect_source == "prior-study":
        doi = DOI.search(note)
        rest = re.sub(r"(?i)https?://(dx\.)?doi\.org/|doi:?", "", DOI.sub("", note))
        if not doi or not re.search(r"[A-Za-z]{3,}|\b[pP]\.?\s*\d", rest):
            fail("--effect-source prior-study needs --source-note with the DOI and where in the paper the value is, "
                 "for example \"doi:10.1000/xyz123, Table 2, SD of the control arm\". Read the value from the paper, "
                 "not from an abstract or from memory.")
    elif not note and args.effect_source != "convention":
        warnings.append("no --source-note: the justification carries an [Author input needed: ...] placeholder")
    if args.effect_source == "pilot":
        warnings.append("a pilot estimate is imprecise, and pilots chosen because they looked promising overstate the "
                        "effect: read the rows of the table below 1.0")
    if args.effect_source == "convention":
        warnings.append("the effect is a convention, not an estimate of the effect in this field; prefer the smallest "
                        "effect of interest or a prior study, and expect reviewers to ask")
    if args.icc is not None:
        warnings.append("the design effect assumes clusters of equal size; with unequal sizes or few clusters per "
                        "group it understates the n needed, and a simulation is the safer route")
    if args.design == "anova":
        warnings.append("computed for the classical F test; Welch's ANOVA has similar power when the SDs are equal, "
                        "and with unequal SDs a simulation is needed")
    if args.design == "two-proportions":
        warnings.append("normal approximation: with fewer than about 5 expected events per group the exact test needs "
                        "more units than this")
    return warnings


def source_text(args) -> str:
    note = (args.source_note or "").strip()
    if args.effect_source == "convention":
        return ("a conventional value" + (f" ({note})" if note else "")
                + ", which is a convention and not an estimate of the effect in this field")
    label = {"prior-study": "a prior study", "pilot": "pilot data",
             "smallest-effect-of-interest": "the smallest effect of interest"}[args.effect_source]
    return f"{label} ({note})" if note else f"{label} [Author input needed: where the value comes from]"


def effect_text(args, e: dict) -> str:
    u = f" {args.units}" if args.units else ""
    if args.design == "two-means":
        sd = (f"a common SD of {fmt(e['sd1'])}{u}" if e["sd1"] == e["sd2"]
              else f"SDs of {fmt(e['sd1'])} and {fmt(e['sd2'])}{u}")
        d = describe(args.design, e)["standardised"][1]
        return f"a difference in means of {fmt(e['diff'])}{u} with {sd} (d = {d:.2f})"
    if args.design == "paired":
        return (f"a mean within-{args.unit_singular} difference of {fmt(e['diff'])}{u} with an SD of the "
                f"differences of {fmt(tidy(e['sd_diff']))}{u} (d_z = {e['diff'] / e['sd_diff']:.2f})")
    if args.design == "two-proportions":
        return f"proportions of {fmt(e['p1'])} and {fmt(e['p2'])} (a difference of {fmt(tidy(e['p1'] - e['p2']))})"
    if args.design == "correlation":
        return f"a correlation of {fmt(e['r'])}"
    return (f"group means of {', '.join(fmt(m) for m in e['means'])}{u} with a common SD of {fmt(e['sd'])}{u} "
            f"(Cohen's f = {e['f']:.3f})")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sample size, power or detectable effect, with a table and a "
                                                 "justification.")
    parser.add_argument("design", choices=DESIGNS)
    for name in ("diff", "sd", "sd1", "sd2", "sd-diff", "corr", "p1", "p2", "r"):
        parser.add_argument(f"--{name}", type=float)
    parser.add_argument("--means", help="anova: the planned group means, comma-separated")
    parser.add_argument("--groups", type=int, help="anova with --solve effect: the number of groups")
    parser.add_argument("--ratio", type=float, default=1.0, help="n of group 2 / n of group 1 (default 1)")
    parser.add_argument("--effect-source", required=True, choices=SOURCES)
    parser.add_argument("--source-note", help="Where the value comes from; for prior-study the DOI and the place "
                                              "in the paper")
    parser.add_argument("--outcome", required=True, help="The outcome, as the justification should name it")
    parser.add_argument("--units", default="", help="Units of the outcome (mmHg, ms); empty for proportions and r")
    parser.add_argument("--unit", default="participants", help="What n counts, plural (default: participants)")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--power", type=float, default=0.8, help="Target power (default 0.8)")
    parser.add_argument("--alternative", choices=("two-sided", "one-sided"), default="two-sided")
    parser.add_argument("--solve", choices=("n", "power", "effect"), default="n")
    parser.add_argument("--n", type=int, help="n per group (group 1 with --ratio) for --solve power or effect")
    parser.add_argument("--attrition", type=float, default=0.0, help="Expected fraction lost, e.g. 0.1")
    parser.add_argument("--icc", type=float, help="Intraclass correlation within clusters")
    parser.add_argument("--cluster-size", type=float, help="Units per cluster")
    parser.add_argument("--range", default=",".join(map(str, RANGE)), help="Multipliers of the effect for the table")
    parser.add_argument("--out", default="statistics")
    parser.add_argument("--name", default="power")
    args = parser.parse_args(argv)
    args.unit_singular = re.sub(r"s$", "", args.unit) or args.unit
    warnings = check_request(args)
    e = effect_from(args)
    try:
        multipliers = sorted({float(x) for x in args.range.split(",")})
    except ValueError:
        fail("--range takes numbers separated by commas, for example 0.5,0.75,1,1.25,1.5.")
    if stats is None:
        print(json.dumps({"status": "not_run", "missing": "scipy", "message": "power.py needs scipy for the noncentral "
                          "t and F distributions. Install it (python3 -m pip install scipy) or run with a Python that "
                          "has it; nothing was computed."}, indent=2))
        return 2

    sides, d = 1 if args.alternative == "one-sided" else 2, args.design
    calc = {"alpha": args.alpha, "sides": sides, "powers": sorted(set(POWERS) | {args.power}),
            "sided": f"{args.alternative} " if d != "anova" else "",
            "software": f"power.py {__version__} (researchzy-statistics) with SciPy {scipy.__version__} "
                        f"on Python {platform.python_version()}"}
    record = {"tool": "researchzy-statistics", "schema_version": 1, "kind": "power", "design": d, "test": TESTS[d],
              "solve": args.solve, "purpose": "sensitivity analysis" if args.solve == "effect" else "justification",
              "outcome": args.outcome, "units": args.units, "unit": args.unit,
              "inputs": {k: tidy(v) for k, v in vars(args).items() if v is not None and k in INPUTS},
              "effect_source": {"kind": args.effect_source, "note": args.source_note,
                                "convention": args.effect_source == "convention"},
              "software": {"power.py": __version__, "scipy": scipy.__version__, "python": platform.python_version()}}
    if args.solve == "effect":
        sensitivity(args, e, record, calc)
    else:
        plan(args, e, record, calc, multipliers)
    record["warnings"] = warnings
    write(args, record, calc)
    return 0


def detectable(d, e, n, alpha, sides, target) -> list:
    """The smallest detectable effect per direction (both signs of p1 - p2 for proportions), or None."""
    found = []
    for base in ([dict(e, p1=e["p2"] + sign) for sign in (1.0, -1.0)] if d == "two-proportions" else [e]):
        k = solve_k(d, base, n, alpha, sides, target)
        found.append(None if k is None else {name: tidy(v) for name, v in describe(d, scaled(d, base, k)).values()})
    return found


def per_group(counts: list) -> str:
    return " and ".join(map(str, counts)) if len(set(counts)) > 1 else str(counts[0])


def group_phrase(counts: list, unit: str) -> str:
    """'16 subjects', '64 patients per group (128 in total)' or '30 and 60 patients in groups 1 and 2 (90 in total)'."""
    if len(counts) == 1:
        return f"{counts[0]} {unit}"
    where = "per group" if len(set(counts)) == 1 else "in groups 1 and 2"
    return f"{per_group(counts)} {unit} {where} ({sum(counts)} in total)"


def effect_label(values: dict, units: str) -> str:
    """'a difference in means of 4.98 mmHg (d = 0.498)', or 'p1 = 0.29 (risk difference = 0.14)'."""
    (raw, value), *rest = values.items()
    text = f"{raw} = {fmt(value)}" if raw in ("p1", "r") else f"a {raw} of {fmt(value)}{units}"
    return text + "".join(f" ({name} = {fmt(v)})" for name, v in rest)


def sensitivity(args, e, record, c) -> None:
    d, n = args.design, args.n
    units = f" {args.units}" if args.units and d in ("two-means", "paired", "anova") else ""
    record["effect_source"]["applies_to"] = "the SD or the baseline the detectable effect is measured against"
    found = detectable(d, e, n, c["alpha"], c["sides"], args.power)
    rows = [{"n": m, "detectable": {str(p): [None if x is None else next(iter(x.values()))
                                             for x in detectable(d, e, m, c["alpha"], c["sides"], p)]
                                    for p in c["powers"]}}
            for m in sorted({max(MIN_N[d], round(n * f)) for f in (0.5, 0.75, 1, 1.5, 2)})]
    record["result"] = {"n_per_group": sizes(d, n, e), "power": args.power,
                        "detectable_effect": dict(zip(("higher", "lower"), found))}
    record["table"] = {"rows": "n per group", "columns": "power", "data": rows, "cells": "detectable effect (raw units)"
                       + (" as higher p1 / lower p1" if d == "two-proportions" else "")}
    shown = [effect_label(x, units) for x in found if x]
    effect = (shown[0] + (f", or in the other direction {shown[1]}" if len(shown) > 1 else "")
              if shown else "no size within the possible range")
    record["justification"] = (
        f"Sensitivity analysis, not a sample-size justification. For {args.outcome}, with "
        f"{group_phrase(sizes(d, n, e), args.unit)}, a {c['sided']}{TESTS[d]} at alpha = {fmt(c['alpha'])} has {fmt(args.power * 100)}% "
        f"power to detect {effect}, with the SD or baseline taken from {source_text(args)}. This states "
        f"what the study could detect; it does not show that it could detect the effect that matters. Calculated with "
        f"{c['software']}.")


def plan(args, e, record, c, multipliers) -> None:
    d, alpha, sides, unit = args.design, c["alpha"], c["sides"], args.unit
    rows = []
    for m in multipliers:
        s = scaled(d, e, m)
        if m <= 0 or not possible(d, s):
            continue
        row = {"multiplier": m, "effect": {name: tidy(v) for name, v in describe(d, s).values()}}
        if args.solve == "n":
            row["n_per_group"] = {str(p): solve_n(d, s, alpha, sides, p) for p in c["powers"]}
        else:
            ns = sorted({max(MIN_N[d], round(args.n * f)) for f in (0.5, 0.75, 1, 1.5, 2)})
            row["power"] = {str(n): round(power_of(d, n, s, alpha, sides), 4) for n in ns}
        rows.append(row)
    record["table"] = {"rows": "effect (multiple of the planned effect)", "data": rows,
                       "columns": "target power" if args.solve == "n" else "n per group",
                       "cells": ("n per group" if len(sizes(d, 2, e)) > 1 else "n") if args.solve == "n" else "power"}
    opening = (f"The primary outcome is {args.outcome}. The calculation assumes {effect_text(args, e)}, taken from "
               f"{source_text(args)}.")
    if args.solve == "power":
        achieved = power_of(d, args.n, e, alpha, sides)
        record["result"] = {"n_per_group": sizes(d, args.n, e), "power": round(achieved, 4)}
        record["justification"] = (f"{opening} With {group_phrase(sizes(d, args.n, e), unit)}, a "
                                   f"{c['sided']}{TESTS[d]} at alpha = {fmt(alpha)} has "
                                   f"{fmt(round(achieved * 100, 1))}% power. Calculated with {c['software']}.")
        return
    n = solve_n(d, e, alpha, sides, args.power)
    if n is None:
        fail(f"no n up to {MAX_N:,} per group reaches the target power for this effect.")
    planned = sizes(d, n, e)
    de = 1 + (args.cluster_size - 1) * args.icc if args.icc is not None else 1.0
    inflated = [math.ceil(x * de / (1 - args.attrition) - 1e-9) for x in planned]
    record["result"] = {"n_per_group": planned, "n_total": sum(planned),
                        "achieved_power": round(power_of(d, n, e, alpha, sides), 4)}
    record["inflation"] = {"attrition": args.attrition, "design_effect": tidy(de), "icc": args.icc,
                           "cluster_size": args.cluster_size, "n_per_group": inflated, "n_total": sum(inflated)}
    text = (f"{opening} With a {c['sided']}alpha of {fmt(alpha)} and a power of {fmt(args.power * 100)}%, a {TESTS[d]} "
            f"needs {group_phrase(planned, unit)}.")
    extras = [f"{fmt(args.attrition * 100)}% attrition"] if args.attrition else []
    if args.icc is not None:
        clusters = [math.ceil(x / args.cluster_size - 1e-9) for x in inflated]
        record["inflation"]["clusters_per_group"] = clusters
        extras.append(f"a design effect of {de:.3g} (ICC {fmt(args.icc)}, {fmt(args.cluster_size)} {unit} per cluster)")
    if extras:
        text += (f" Allowing for {' and '.join(extras)}, the target is {group_phrase(inflated, unit)}"
                 + (f", in {per_group(clusters)} clusters per group" if args.icc is not None else "") + ".")
    else:
        text += " No allowance for attrition was requested."
    record["justification"] = f"{text} Calculated with {c['software']}."


def write(args, record, c) -> None:
    out, name, data = Path(args.out), args.name, record["table"]["data"]
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    source = args.effect_source + (" (a convention)" if args.effect_source == "convention" else "")
    lines = [f"# {'Sensitivity analysis' if args.solve == 'effect' else 'Sample size and power'}: {args.outcome}", "",
             f"Test: {TESTS[args.design]}, {c['sided']}alpha = {fmt(c['alpha'])}. Effect source: {source}"
             + (f": {args.source_note}" if args.source_note else "") + ".", ""]
    if args.solve == "effect":
        heads = [f"power {p:g}" for p in c["powers"]]
        cells = [(row["n"], [" / ".join("-" if v is None else fmt(v) for v in row["detectable"][str(p)])
                             for p in c["powers"]]) for row in data]
    else:
        heads = [f"power {p:g}" for p in c["powers"]] if args.solve == "n" else [f"n = {k}" for k in data[0]["power"]]
        units = f" {args.units}" if args.units and args.design in ("two-means", "paired", "anova") else ""
        cells = [(", ".join(f"{k} {fmt(v)}{units if i == 0 else ''}" for i, (k, v) in enumerate(row["effect"].items()))
                  + (" (planned)" if row["multiplier"] == 1 else ""),
                  ["not reached" if v is None else fmt(v) for v in (row.get("n_per_group") or row["power"]).values()])
                 for row in data]
    lines += [f"| {'n per group' if args.solve == 'effect' else 'Effect'} | " + " | ".join(heads) + " |",
              "|---" * (len(heads) + 1) + "|"] + [f"| {label} | " + " | ".join(row) + " |" for label, row in cells]
    lines += ["", f"Cells: {record['table']['cells']}.", "", "## Justification", "", record["justification"]]
    lines += (["", "## Warnings", ""] + [f"- {w}" for w in record["warnings"]]) if record["warnings"] else []
    (out / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = {k: record.get(k) for k in ("design", "solve", "purpose", "result", "inflation", "justification", "warnings")}
    summary["files"] = [str(out / f"{name}.json"), str(out / f"{name}.md")]
    print(json.dumps(summary, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    sys.exit(main())
