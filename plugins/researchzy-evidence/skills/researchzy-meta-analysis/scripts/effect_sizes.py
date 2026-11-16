#!/usr/bin/env python3
"""Effect sizes for a meta-analysis from its extraction table, with every conversion declared per row.

  effect_sizes.py meta-analysis/extraction.csv --measure MD
  effect_sizes.py meta-analysis/extraction.csv --measure weight=MD --measure psqi=SMD
  effect_sizes.py meta-analysis/extraction.csv --measure death=OR --sparse death=mh
  effect_sizes.py meta-analysis/extraction.csv --measure MD --combine "Lee 2021" --split "Kim 2020" \\
                  --drop "Ono 2019=low dose"

One row per arm of a study (one row per study for ratio_ci, r and yi_se). A pool is one outcome at
one timepoint; a study enters a pool once, its arm(s) against the arm named "control". reported_as
says what a row holds and which columns it needs (n always); the change_ forms hold change from
baseline (change_sd, change_se, change_ci, change_median_iqr, change_median_range):

  mean_sd, change_sd    value = mean (or mean change), spread = SD
  mean_se, change_se    value, spread = SE                        SD = SE x sqrt(n)
  mean_ci, change_ci    value, low, high, ci_level                SD = sqrt(n)(high - low) / (2 t(n - 1))
  median_iqr            value = median, low = Q1, high = Q3       mean (Q1 + m + Q3)/3, SD (Wan 2014): estimated
  median_range          value = median, low = min, high = max     mean (a + 2m + b)/4, SD (Wan 2014): estimated
  events                events, n
  ratio_ci              value = the pool's OR, RR or HR, low, high, ci_level
  r                     value = correlation
  yi_se                 value = effect on the analysis scale (natural log for a ratio), spread = its SE

--measure MD, SMD (Hedges' g, exact J, var N/(n1 n2) + g^2/(2(N - 3.94))), OR, RR, RD, HR, Z (Fisher
z, var 1/(n - 3)) or GENERIC, for every outcome or as outcome=MEASURE. An MD uses each group's own SD.
Cluster rows are deflated by 1 + (m - 1) ICC; crossover rows use their within-person correlation.

Refused (marked in effects.csv, so meta_pool.py will not pool the file): a missing or impossible value;
a study twice in one pool (two rows for an arm, a study-level row beside arm rows, several arms against
one control without --combine, --split or --drop); an MD pool without one shared unit; an SMD pool
mixing change and final values; a cluster row without cluster_size, icc and icc_source ("adjusted"
for an estimate the source adjusted); a crossover row without corr and corr_source; an impossible
ratio CI; a binary pool with a zero cell or a pooled event rate below 1 % (a convention) without
--sparse mh (Mantel-Haenszel), peto (Peto OR), cc (0.5 added only to studies with a zero cell) or iv
(no zero cell). Studies with no events, or only events, in both arms leave OR and RR pools, counted.
Warned: an SD that looks like an SE (CI half-width / t, or far below the other studies' median while
SD x sqrt(n) is near it); a ratio CI asymmetric on the log scale beyond rounding; no locator.

Writes effects.csv and effects.md beside the table (or in --out); prints a JSON summary. Exit code 0
when every pool was computed, 1 when something was refused, 2 when the table cannot be read. Standard
library; scipy, when installed, gives the t quantiles. Portions are derived from MIT-licensed code:
see LICENSE-MIT.txt next to this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path

try:
    from scipy import stats as _stats
except ImportError:          # the t quantile below is used instead
    _stats = None

COLUMNS = ("study", "outcome", "timepoint", "arm", "n", "design", "reported_as", "value", "spread", "low", "high",
           "ci_level", "events", "cluster_size", "icc", "icc_source", "corr", "corr_source", "units", "reverse",
           "locator", "quote", "notes")
NEEDS = {"mean_sd": ("value", "spread"), "mean_se": ("value", "spread"), "mean_ci": ("value", "low", "high"),
         "change_sd": ("value", "spread"), "change_se": ("value", "spread"), "change_ci": ("value", "low", "high"),
         "median_iqr": ("value", "low", "high"), "median_range": ("value", "low", "high"),
         "change_median_iqr": ("value", "low", "high"), "change_median_range": ("value", "low", "high"),
         "events": ("events",), "ratio_ci": ("value", "low", "high"), "r": ("value",), "yi_se": ("value", "spread")}
CONTINUOUS = tuple(form for form in NEEDS if form.startswith(("mean_", "change_", "median_")))
STUDY_LEVEL = ("ratio_ci", "r", "yi_se")
ACCEPTS = {"MD": CONTINUOUS + ("yi_se",), "SMD": CONTINUOUS + ("yi_se",), "OR": ("events", "ratio_ci", "yi_se"),
           "RR": ("events", "ratio_ci", "yi_se"), "RD": ("events", "yi_se"), "HR": ("ratio_ci", "yi_se"),
           "Z": ("r", "yi_se"), "GENERIC": ("yi_se",)}
DESIGNS = ("parallel", "cluster", "crossover")
SPARSE = ("mh", "peto", "cc", "iv")
RARE = 0.01            # a pooled event rate below this makes a binary pool sparse (a convention)
SE_LIKE = 0.10         # an SD within 10 % of the CI half-width / t looks like an SE
FAR_BELOW = 0.5        # an SD below half the other studies' median SD is far below it
ASYMMETRY = 0.10       # log-scale asymmetry of a ratio CI, as a share of its half-width, beyond rounding
FIELDS = ("pool", "study", "outcome", "timepoint", "comparison", "measure", "yi", "vi", "se", "n1", "n2", "e1",
          "e2", "participants", "units", "design", "estimated", "change", "zero_cell", "sparse", "excluded",
          "refused", "method", "conversions", "warnings", "lines")
DECIMAL = re.compile(r"^[+-]?(?:\d+(?:\.(\d*))?|\.(\d+))$")
NORMAL = statistics.NormalDist()


def beta_reg(a: float, b: float, x: float) -> float:
    """The regularised incomplete beta function I_x(a, b), by its continued fraction (modified Lentz)."""
    if x <= 0 or x >= 1:
        return 0.0 if x <= 0 else 1.0
    if x > (a + 1) / (a + b + 2):
        return 1 - beta_reg(b, a, 1 - x)
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)) / a
    c, d, f = 1.0, 0.0, 1.0
    for i in range(400):
        m = i // 2
        step = 1.0 if i == 0 else (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)) if i % 2 == 0
                                   else -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1)))
        d = 1 + step * d
        d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + step / c
        c = c if abs(c) > 1e-300 else 1e-300
        f *= c * d
        if abs(c * d - 1) < 1e-15:
            break
    return front * (f - 1)


def t_quantile(p: float, df: float) -> float:
    """Quantile of Student's t: scipy when installed, else bisection on the CDF from beta_reg."""
    if _stats is not None:
        return float(_stats.t.ppf(p, df))
    if p < 0.5:
        return -t_quantile(1 - p, df)
    def cdf(t):
        return 1 - 0.5 * beta_reg(df / 2, 0.5, df / (df + t * t))
    low, high = 0.0, 1.0
    while cdf(high) < p:
        high *= 2
    for _ in range(100):
        low, high = ((low + high) / 2, high) if cdf((low + high) / 2) < p else (low, (low + high) / 2)
    return (low + high) / 2


def hedges_j(df: float, exact: bool = True) -> float:
    """Small-sample factor of Hedges' g: Gamma(df/2) / (sqrt(df/2) Gamma((df-1)/2)), or 1 - 3/(4 df - 1)."""
    if not exact:
        return 1 - 3 / (4 * df - 1)
    return math.exp(math.lgamma(df / 2) - 0.5 * math.log(df / 2) - math.lgamma((df - 1) / 2))


def number(text: str):
    text = (text or "").strip().replace("−", "-")
    try:
        value = float(text) if text else None
    except ValueError:
        value = math.nan
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{text!r} is not a number")
    return value


def ci_level(text: str) -> float:
    value = number((text or "").replace("%", ""))
    level = 0.95 if value is None else value / 100 if value > 1 else value
    if not 0.5 < level < 1:
        raise ValueError(f"ci_level {text!r} must be a level such as 95 or 0.95")
    return level


def printed(raw: str) -> tuple:
    """A number as printed: (value, half of its last decimal place)."""
    m = DECIMAL.match((raw or "").strip())
    if not m:
        raise ValueError(f"{raw!r} is not a plain decimal number")
    return float(raw), 0.5 * 10.0 ** -len(m.group(1) or m.group(2) or "")


def ratio_ci(raw: dict, level: float, warn: list) -> tuple:
    """log ratio and its variance from a printed ratio CI; refuses an impossible CI, warns on asymmetry."""
    (e, de), (lo, dl), (up, du) = (printed(raw.get(k, "")) for k in ("value", "low", "high"))
    if min(e, lo, up) < 0 or lo - dl > e + de or e - de > up + du or not lo < up:
        raise ValueError(f"impossible ratio CI {raw['value']} ({raw['low']} to {raw['high']}): a ratio and its "
                         "bounds are positive and the interval contains the estimate, even after rounding")
    if min(e, lo) == 0:
        raise ValueError("a ratio or bound printed as 0 has no logarithm: take more decimals from the source")
    # |ln up + ln lo - 2 ln e| over the half-width, at its smallest over every value within rounding
    h_max = (math.log(up + du) - math.log(max(lo - dl, 1e-300))) / 2
    if min(e - de, lo - dl) <= 0:
        warn.append("log-scale symmetry not assessed: a value within rounding is 0")
    else:
        n_min = math.log(up - du) + math.log(lo - dl) - 2 * math.log(e + de)
        n_max = math.log(up + du) + math.log(lo + dl) - 2 * math.log(e - de)
        bound = 0.0 if n_min <= 0 <= n_max else min(abs(n_min), abs(n_max)) / h_max
        if bound > ASYMMETRY:
            warn.append(f"the ratio CI is asymmetric on the log scale by at least {bound:.0%} of its half-width after "
                        "rounding: check the transcription (an exact or profile CI can be asymmetric)")
    z = NORMAL.inv_cdf(1 - (1 - level) / 2)
    return math.log(e), ((math.log(up) - math.log(lo)) / (2 * z)) ** 2


def parse(line: int, raw: dict, measure) -> dict:
    """One row on a common footing (mean and SD, events, or yi and vi), or with 'refused' set."""
    form, design = raw.get("reported_as", "").lower(), (raw.get("design") or "parallel").lower()
    r = {"line": line, "study": raw.get("study", ""), "outcome": raw.get("outcome", ""), "timepoint": raw.get("timepoint", ""),
         "arm": raw.get("arm", ""), "form": form, "design": design, "units": raw.get("units", ""), "raw": raw,
         "conv": [], "warn": [], "refused": None, "estimated": False, "change": form.startswith("change_"),
         "level": form in STUDY_LEVEL}
    try:
        if not r["study"] or not r["outcome"]:
            raise ValueError("study and outcome are required")
        if form not in NEEDS:
            raise ValueError(f"reported_as {form or '(empty)'!r} is not one of {', '.join(NEEDS)}")
        if design not in DESIGNS:
            raise ValueError(f"design {design!r} is not one of {', '.join(DESIGNS)}")
        if measure is None:
            raise ValueError(f"no --measure was given for outcome {r['outcome']!r}")
        if form not in ACCEPTS[measure]:
            raise ValueError(f"a {form} row cannot enter a {measure} pool")
        v = {k: number(raw.get(k)) for k in ("n", "value", "spread", "low", "high", "events", "cluster_size", "icc", "corr")}
        missing = [k for k in ("n",) + NEEDS[form] if v[k] is None]
        if missing:
            raise ValueError(f"{form} needs {', '.join(missing)}")
        n, level, reverse = v["n"], ci_level(raw.get("ci_level", "")), raw.get("reverse", "").lower() in ("yes", "true", "1")
        if n <= 0:
            raise ValueError("n must be positive")
        if reverse and form in ("events", "ratio_ci"):
            raise ValueError(f"reverse is not used with {form}: enter the outcome as the pool defines it")
        if reverse:
            r["conv"].append("sign reversed: the scale runs the other way")
        if not raw.get("locator"):
            r["warn"].append(f"line {line}: no locator, so the value cannot be traced to its place in the source")
        de = 1.0
        if design == "cluster" and raw.get("icc_source", "").lower() == "adjusted" and r["level"]:
            r["conv"].append("estimate already adjusted for clustering in the source")
        elif design == "cluster":
            if v["icc"] is None or v["cluster_size"] is None or not raw.get("icc_source"):
                raise ValueError("a cluster trial needs cluster_size, icc and icc_source (icc_source 'adjusted' only for "
                                 "a study-level estimate that the source already adjusted for clustering)")
            if not (0 <= v["icc"] < 1 and v["cluster_size"] >= 1):
                raise ValueError("icc must lie in [0, 1) and cluster_size be at least 1")
            de = 1 + (v["cluster_size"] - 1) * v["icc"]
            r["conv"].append(f"design effect 1 + ({v['cluster_size']:g} - 1) x {v['icc']:g} = {de:.4g} "
                             f"(ICC from {raw['icc_source']})")
        if design == "crossover" and not r["level"]:
            if form == "events":
                raise ValueError("a crossover trial's binary outcome needs its paired analysis, as ratio_ci or yi_se")
            if v["corr"] is None or not -1 < v["corr"] < 1 or not raw.get("corr_source"):
                raise ValueError("a crossover row needs corr (the within-person correlation, between -1 and 1) and corr_source")
            r["corr"] = v["corr"]
        if form in CONTINUOUS:
            m, s, lo, hi = v["value"], v["spread"], v["low"], v["high"]
            if form.endswith(("_ci", "_iqr", "_range")) and not (lo < hi and lo <= m <= hi):
                raise ValueError(f"value {m:g} must lie between low {lo:g} and high {hi:g}, with low < high")
            if form.endswith("_se"):
                s *= math.sqrt(n)
                r["conv"].append(f"SD = SE x sqrt(n) = {v['spread']:g} x sqrt({n:g})")
            elif form.endswith("_ci"):
                if n < 2:
                    raise ValueError("an SD from a CI needs n of at least 2")
                q = t_quantile(1 - (1 - level) / 2, n - 1)
                s = math.sqrt(n) * (hi - lo) / (2 * q)
                r["conv"].append(f"SD from the {level:.0%} CI of the mean, t({n - 1:g}) = {q:.4f}")
            elif "median_" in form:
                iqr = form.endswith("_iqr")
                divisor = 2 * NORMAL.inv_cdf((0.75 * n - 0.125) / (n + 0.25) if iqr else (n - 0.375) / (n + 0.25))
                if divisor <= 0:
                    raise ValueError("a median conversion needs n of at least 2")
                m, s = ((lo + m + hi) / 3 if iqr else (lo + 2 * m + hi) / 4), (hi - lo) / divisor
                r["estimated"] = True
                r["conv"].append(f"mean and SD estimated from the median and {'IQR' if iqr else 'range'} (Wan 2014)")
            if not s > 0:
                raise ValueError("the SD must be positive")
            r.update(mean=-m if reverse else m, sd=s, n=n, n_eff=n / de, kind="continuous")
        elif form == "events":
            if not 0 <= v["events"] <= n:
                raise ValueError("events must lie between 0 and n")
            r.update(e=v["events"] / de, n=n, n_eff=n / de, kind="binary")
        else:
            if form == "ratio_ci":
                yi, vi = ratio_ci(raw, level, r["warn"])
                r["conv"].append(f"log ratio; SE from the {level:.0%} CI")
            elif form == "r":
                if not -1 < v["value"] < 1 or n / de <= 3:
                    raise ValueError("r must lie between -1 and 1 and the (effective) n exceed 3")
                yi, vi, de = math.atanh(v["value"]), 1 / (n / de - 3), 1.0
                r["conv"].append("Fisher z = atanh(r), var = 1/(n - 3)")
            else:
                if not v["spread"] > 0:
                    raise ValueError("the SE must be positive")
                yi, vi = v["value"], v["spread"] ** 2
            r.update(yi=-yi if reverse else yi, vi=vi * de, n=n, kind="study")
    except ValueError as exc:
        r["refused"] = f"line {line}: {exc}"
    return r


def combine(arms: list) -> dict:
    """Several arms as one group (Cochrane Handbook Table 6.5.a for means and SDs; events and n add up)."""
    if len({a["change"] for a in arms}) > 1:
        raise ValueError("cannot combine an arm of change values with an arm of final values")
    name = " + ".join(a["arm"] for a in arms)
    out = dict(arms[0], arm=name, estimated=any(a["estimated"] for a in arms), n=sum(a["n"] for a in arms),
               conv=[f"{a['arm']}: {c}" for a in arms for c in a["conv"]] + [f"arms {name} combined (Cochrane formula)"],
               warn=[w for a in arms for w in a["warn"]], line=[a["line"] for a in arms])
    if out["kind"] == "binary":
        out.update(e=sum(a["e"] for a in arms), n_eff=sum(a["n_eff"] for a in arms))
        return out
    n1, m1, s1 = arms[0]["n_eff"], arms[0]["mean"], arms[0]["sd"]
    for a in arms[1:]:
        n2, m2, s2 = a["n_eff"], a["mean"], a["sd"]
        s1 = math.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2 + n1 * n2 / (n1 + n2) * (m1 - m2) ** 2) / (n1 + n2 - 1))
        n1, m1 = n1 + n2, (n1 * m1 + n2 * m2) / (n1 + n2)
    out.update(n_eff=n1, mean=m1, sd=s1)
    return out


def lines(*rows) -> list:
    return [x for r in rows for x in (r["line"] if isinstance(r["line"], list) else [r["line"]])]


def compare(t: dict, c: dict, share: float, measure: str) -> dict:
    """The effect of arm t against control c, of whose participants a share is used."""
    units = {x["units"].lower() for x in (t, c) if x["units"]}
    if len(units) > 1:
        raise ValueError("the two arms give different units")
    conv = [x if " combined " in x or x.startswith(t["arm"] + ":") else f"{t['arm']}: {x}" for x in t["conv"]]
    conv += [f"{c['arm']}: {x}" for x in c["conv"]] + ([f"control split, {share:.3g} of it used"] if share < 1 else [])
    comp = {"study": t["study"], "comparison": f"{t['arm']} vs {c['arm']}", "lines": lines(t, c), "design": t["design"],
            "conv": conv, "warn": list(dict.fromkeys(t["warn"] + c["warn"])), "estimated": t["estimated"] or c["estimated"],
            "units": t["units"] or c["units"], "participants": t["n"] + c["n"] * share, "kind": t["kind"]}
    if t["kind"] == "binary":
        comp.update(e1=t["e"], n1=t["n_eff"], e2=c["e"] * share, n2=c["n_eff"] * share)
        return comp
    if t["change"] != c["change"]:
        raise ValueError("one arm reports change from baseline and the other final values")
    comp["change"], (n1, m1, s1), (n2, m2, s2) = t["change"], (t["n_eff"], t["mean"], t["sd"]), (c["n_eff"] * share, c["mean"], c["sd"])
    if t["design"] == "crossover":
        if t["n"] != c["n"] or share < 1 or t.get("corr") != c.get("corr"):
            raise ValueError("a crossover comparison needs two rows on the same participants with the same corr")
        r, n = t["corr"], n1
        if measure == "MD":
            comp.update(yi=m1 - m2, vi=(s1 ** 2 + s2 ** 2 - 2 * r * s1 * s2) / n)
        else:
            g = hedges_j(n - 1) * (m1 - m2) / math.sqrt((s1 ** 2 + s2 ** 2) / 2)
            comp.update(yi=g, vi=(1 / n + g ** 2 / (2 * n)) * 2 * (1 - r))
        comp["conv"].append(f"paired analysis with within-person correlation {r:g}")
    elif measure == "MD":
        comp.update(yi=m1 - m2, vi=s1 ** 2 / n1 + s2 ** 2 / n2)
    else:
        df, big = n1 + n2 - 2, n1 + n2
        g = hedges_j(df) * (m1 - m2) / math.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / df)
        comp.update(yi=g, vi=big / (n1 * n2) + g ** 2 / (2 * (big - 3.94)))
    comp.update(n1=n1, n2=n2)
    return comp


def binary(comp: dict, measure: str, sparse) -> None:
    """yi and vi of a 2x2 comparison; 0.5 is added to each cell only when it has a zero cell and sparse is set."""
    a, c = comp["e1"], comp["e2"]
    b, d = comp["n1"] - a, comp["n2"] - c
    comp["zero"] = min(a, b, c, d) == 0
    if (a == 0 and c == 0) or (b == 0 and d == 0):
        if measure in ("OR", "RR"):
            comp["excluded"] = "no events, or only events, in both arms: no information on a ratio"
            return
    if comp["zero"]:
        if sparse is None:
            return
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
        comp["conv"].append("0.5 added to each cell (zero cell)" if sparse == "cc" else
                            "0.5 added to each cell for the study's own estimate only; the pool uses the counts")
    p1, p2 = a / (a + b), c / (c + d)
    yi, vi = {"OR": (math.log(a * d / (b * c)), 1 / a + 1 / b + 1 / c + 1 / d),
              "RR": (math.log(p1 / p2), 1 / a - 1 / (a + b) + 1 / c - 1 / (c + d)),
              "RD": (p1 - p2, p1 * (1 - p1) / (a + b) + p2 * (1 - p2) / (c + d))}[measure]
    comp.update(yi=yi, vi=vi)


def build(study: str, rows: list, measure: str, opts: dict) -> list:
    """The comparisons one study contributes to a pool; raises ValueError when it cannot enter it."""
    level = [r for r in rows if r["level"]]
    dropped = {(study.lower(), arm) for arm in [r["arm"].lower() for r in rows]} & opts["drop"]
    arms = [r for r in rows if not r["level"] and (study.lower(), r["arm"].lower()) not in dropped]
    if level:
        if arms or len(level) > 1:
            raise ValueError("the study appears twice in this pool: keep one row for its comparison")
        r = level[0]
        return [{"study": study, "comparison": "as reported", "lines": [r["line"]], "conv": r["conv"], "warn": r["warn"],
                 "design": r["design"], "estimated": False, "units": r["units"], "participants": r["n"], "kind": "study",
                 "yi": r["yi"], "vi": r["vi"]}]
    names = [a["arm"].lower() for a in arms]
    if len(set(names)) < len(names):
        raise ValueError("two rows for one arm: the study appears twice in this pool")
    control = [a for a in arms if a["arm"].lower() == "control"]
    treated = [a for a in arms if a["arm"].lower() != "control"]
    if len(control) != 1 or not treated or len({a["kind"] for a in arms}) > 1:
        raise ValueError("needs one arm named control and at least one other arm, all continuous or all events")
    share = 1.0
    if len(treated) > 1:
        if study.lower() in opts["combine"]:
            treated = [combine(treated)]
        elif study.lower() in opts["split"]:
            share = 1 / len(treated)
        else:
            raise ValueError(f"{len(treated)} arms against one control: give --combine, --split or --drop for this study")
    comps = [compare(t, control[0], share, measure) for t in treated]
    for comp in comps:
        comp["conv"] += [f"arm {arm!r} left out (--drop)" for _, arm in sorted(dropped)]
    return comps


def pool_checks(comps: list, measure: str, sparse, outcome: str) -> tuple:
    """Refusals and notes that concern a whole pool; computes the binary effects."""
    refusals, notes = [], []
    if measure == "MD":
        units = {c["units"].strip().lower() for c in comps}
        if len(units) != 1 or "" in units:
            refusals.append("an MD pool needs one unit for every study in the units column (found: "
                            f"{', '.join(sorted(u or '(empty)' for u in units))}); if the scales differ, the plan needs an SMD")
    changes = {c["change"] for c in comps if "change" in c}
    if len(changes) > 1:
        if measure == "SMD":
            refusals.append("an SMD pool mixes change-from-baseline and final values: pool them separately")
        else:
            notes.append("the MD pool mixes change and final values (allowed for an MD; say so in the methods)")
    counted = [c for c in comps if c["kind"] == "binary"]
    if counted:
        for c in counted:
            binary(c, measure, sparse)
        zero = [c["study"] for c in counted if c.get("zero") and "excluded" not in c]
        events = sum(c["e1"] + c["e2"] for c in counted)
        rate = events / sum(c["n1"] + c["n2"] for c in counted)
        why = (f"{len(zero)} stud{'y has' if len(zero) == 1 else 'ies have'} a zero cell ({', '.join(zero)})" if zero else
               f"the pooled event rate is {rate:.2%}, below {RARE:.0%}" if rate < RARE else "")
        if why and sparse is None:
            refusals.append(f"{why}: choose --sparse {outcome}=mh, peto (OR only), cc" + ("" if zero else " or iv"))
        if sparse == "peto" and measure != "OR":
            refusals.append("--sparse peto is only for an OR pool")
        if sparse in ("mh", "peto") and len(counted) < len(comps):
            refusals.append(f"--sparse {sparse} needs 2x2 counts for every study in the pool")
        if sparse == "iv" and zero:
            refusals.append("--sparse iv is only for a sparse pool without zero cells")
        if why:
            notes.append(why)
    return refusals, notes


def se_as_sd(rows: list) -> None:
    """Warn where a row's reported SD looks like an SE: against its own CI, or against the other studies."""
    arms = [r for r in rows if r.get("kind") == "continuous" and not r["refused"]]
    for r in arms:
        if r["form"] not in ("mean_sd", "change_sd"):
            continue
        sd, n = r["sd"], r["n"]
        lo, hi = number(r["raw"].get("low")), number(r["raw"].get("high"))
        if lo is not None and hi is not None and hi > lo and n >= 2:
            half = (hi - lo) / 2
            if any(abs(sd - half / q) <= SE_LIKE * half / q for q in (NORMAL.inv_cdf(0.975), t_quantile(0.975, n - 1))):
                r["warn"].append(f"line {r['line']}: the SD {sd:g} equals the CI half-width / t, so it is probably an SE")
        others = [o["sd"] for o in arms if o["study"] != r["study"]]
        if n >= 4 and len({o["study"] for o in arms if o["study"] != r["study"]}) >= 2:
            median = statistics.median(others)
            if sd < FAR_BELOW * median and abs(math.log(sd * math.sqrt(n) / median)) < abs(math.log(sd / median)):
                r["warn"].append(f"line {r['line']}: the SD {sd:g} is far below the other studies' median SD {median:.3g}, "
                                 f"and SD x sqrt(n) = {sd * math.sqrt(n):.3g} is close to it: check whether the source "
                                 "reports an SE")


def option_map(values: list, name: str, allowed) -> dict:
    """'MD' for every outcome or 'weight=MD' for one, as {outcome or None: value}."""
    out = {}
    for item in values:
        outcome, _, value = item.rpartition("=")
        key = value.strip().upper() if name == "measure" else value.strip().lower()
        if key not in allowed:
            raise ValueError(f"--{name} {item!r}: use one of {', '.join(allowed)}")
        out[outcome.strip() or None] = key
    return out


def fmt(x) -> str:
    return "" if x is None else format(x, ".12g") if isinstance(x, float) else str(x)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Effect sizes from a meta-analysis extraction table.")
    parser.add_argument("table", type=Path, help="extraction.csv")
    parser.add_argument("--measure", action="append", required=True, help="MEASURE, or OUTCOME=MEASURE (repeatable)")
    parser.add_argument("--sparse", action="append", default=[], help="mh, peto, cc or iv, or OUTCOME=... (repeatable)")
    parser.add_argument("--combine", action="append", default=[], help="combine the arms of this study against control")
    parser.add_argument("--split", action="append", default=[], help="split this study's control among its arms")
    parser.add_argument("--drop", action="append", default=[], help="STUDY=ARM: leave this arm out")
    parser.add_argument("--out", type=Path, help="output folder (default: the table's folder)")
    args = parser.parse_args(argv)
    try:
        measures, sparse = option_map(args.measure, "measure", ACCEPTS), option_map(args.sparse, "sparse", SPARSE)
    except ValueError as exc:
        parser.error(str(exc))
    if any("=" not in item for item in args.drop):
        parser.error("--drop needs STUDY=ARM")
    opts = {"combine": {s.strip().lower() for s in args.combine}, "split": {s.strip().lower() for s in args.split},
            "drop": {tuple(x.strip().lower() for x in item.split("=", 1)) for item in args.drop}}
    try:
        with args.table.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            names = [h.strip().lower() for h in next(reader, [])]
            missing = [c for c in ("study", "outcome", "arm", "n", "reported_as") if c not in names]
            if missing or len(set(names)) < len(names):
                raise ValueError(f"missing column(s) {', '.join(missing)}" if missing else "a column name appears twice")
            table = [(i, {k: (cells[j].strip() if j < len(cells) else "") for j, k in enumerate(names) if k})
                     for i, cells in enumerate(reader, 2) if any(x.strip() for x in cells)]
    except (OSError, ValueError, UnicodeDecodeError, csv.Error) as exc:
        print(f"effect_sizes: cannot read {args.table}: {exc}", file=sys.stderr)
        return 2
    extra = [k for k in names if k and k not in COLUMNS]
    known = {raw.get("study", "").lower() for _, raw in table}
    warnings = [f"--combine, --split or --drop names {s!r}, which is not a study in the table"
                for s in sorted(opts["combine"] | opts["split"] | {study for study, _ in opts["drop"]}) if s not in known]
    pools: dict = {}
    for line, raw in table:
        measure = measures.get(raw.get("outcome", ""), measures.get(None))
        row = parse(line, raw, measure)
        pools.setdefault((row["outcome"], row["timepoint"]), {}).setdefault(row["study"], []).append(row)
    out_rows, summary, refused = [], [], []
    for (outcome, timepoint), studies in pools.items():
        pool = outcome + (f" @ {timepoint}" if timepoint else "")
        measure, choice = measures.get(outcome, measures.get(None)), sparse.get(outcome, sparse.get(None))
        comps, problems = [], []
        se_as_sd([r for rows in studies.values() for r in rows])
        for study, rows in studies.items():
            bad = [r["refused"] for r in rows if r["refused"]]
            try:
                if bad:
                    raise ValueError("; ".join(bad))
                comps += build(study, rows, measure, opts)
            except ValueError as exc:
                problems.append((study, lines(*rows), f"{study}: {exc}"))
        pool_refusals, notes = pool_checks(comps, measure, choice, outcome) if comps and measure else ([], [])
        for study, where, message in problems:
            out_rows.append({"pool": pool, "study": study, "outcome": outcome, "timepoint": timepoint, "measure": measure,
                             "refused": message, "lines": " ".join(map(str, where))})
        for c in comps:
            vi = c.get("vi")
            chars = {k: " / ".join(dict.fromkeys(r["raw"][k] for r in studies[c["study"]] if r["raw"].get(k)))
                     for k in extra}
            out_rows.append({"pool": pool, "study": c["study"], "outcome": outcome, "timepoint": timepoint,
                             "comparison": c["comparison"], "measure": measure, "yi": c.get("yi"), "vi": vi,
                             "se": math.sqrt(vi) if vi is not None else None, "n1": c.get("n1"), "n2": c.get("n2"),
                             "e1": c.get("e1"), "e2": c.get("e2"), "participants": c["participants"],
                             "units": c["units"], "design": c["design"], "estimated": "yes" if c["estimated"] else "",
                             "change": {True: "yes", False: "no"}.get(c.get("change"), ""),
                             "zero_cell": "yes" if c.get("zero") else "", "sparse": choice or "",
                             "excluded": c.get("excluded", ""), "refused": "; ".join(pool_refusals),
                             "method": measure, "conversions": "; ".join(c["conv"]), "warnings": "; ".join(c["warn"]),
                             "lines": " ".join(map(str, c["lines"])), **chars})
            warnings += [f"{pool}, {c['study']}: {w}" for w in c["warn"]]
        refused += [m for _, _, m in problems] + [f"{pool}: {m}" for m in pool_refusals]
        kept = [c for c in comps if "excluded" not in c]
        summary.append({"pool": pool, "measure": measure, "k": len(kept), "excluded": len(comps) - len(kept),
                        "estimated": sum(1 for c in kept if c["estimated"]), "sparse": choice, "notes": notes,
                        "status": "refused" if problems or pool_refusals else "ok"})
    folder = args.out or args.table.parent
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "effects.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FIELDS) + extra, extrasaction="ignore")
        writer.writeheader()
        for row in out_rows:
            writer.writerow({k: fmt(row.get(k)) for k in list(FIELDS) + extra})
    report = ["# Effect sizes", "", f"From `{args.table}`. One row per study and comparison; yi is on the analysis "
              "scale (log for OR, RR and HR; Fisher z for Z).", ""]
    for item in summary:
        rows = [r for r in out_rows if r["pool"] == item["pool"]]
        report += [f"## {item['pool']}: {item['measure']}, k = {item['k']} ({item['status']})", ""]
        report += [f"- {note}" for note in item["notes"]] + ([""] if item["notes"] else [])
        report += ["| Study | Comparison | yi | SE | n | How | Warnings or refusal |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            n = "/".join(f"{r[k]:.4g}" for k in ("n1", "n2") if r.get(k) is not None) or fmt(r.get("participants"))
            cells = (r["study"], r.get("comparison", ""), f"{r['yi']:.4g}" if r.get("yi") is not None else "",
                     f"{r['se']:.4g}" if r.get("se") is not None else "", n, r.get("conversions", "") or "as reported",
                     "; ".join(x for x in (r.get("excluded"), r.get("refused"), r.get("warnings")) if x))
            report.append("| " + " | ".join(str(x).replace("|", "/") for x in cells) + " |")
        report.append("")
    if refused:
        report += ["## Refused", ""] + [f"- {m}" for m in refused] + [""]
    (folder / "effects.md").write_text("\n".join(report), encoding="utf-8")
    code = 1 if refused else 0
    print(json.dumps({"effects": str(folder / "effects.csv"), "report": str(folder / "effects.md"), "pools": summary,
                      "refused": refused, "warnings": warnings,
                      "t_quantiles": "scipy" if _stats is not None else "computed by effect_sizes.py (scipy not installed)",
                      "exit": code}, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
