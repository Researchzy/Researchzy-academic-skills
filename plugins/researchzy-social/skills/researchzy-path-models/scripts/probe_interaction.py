#!/usr/bin/env python3
"""Simple slopes and Johnson-Neyman bounds of a two-way interaction, inside the moderator's observed range.

  probe_interaction.py --b1 0.40 --b3 0.15 --var-b1 0.0024 --var-b3 0.0021 --cov -0.0002 --df 344 \\
      --min 1 --max 7 --mean 6.02 --sd 1.31 --probe 4.5 6.25 7 mean+1sd
  probe_interaction.py --json paths/probe-input.json --out paths/probe-support.md

The model is y = b0 + b1*x + b2*w + b3*x*w + ..., fitted with w - center in place of w when the
moderator was centred (--center: the mean it was centred around; 0 when it was not). Probe values,
the range and the bounds are on the moderator's own scale. A probe is a number, mean, mean+Ksd or
mean-Ksd. --json takes the arguments of probe() by name (b1, b3, var_b1, var_b3, cov_b13, df,
w_min, w_max, w_mean, w_sd, probes, level, center); options given on the command line win.

For each probe: the simple slope b1 + b3*u with u = w - center, its standard error
sqrt(var_b1 + 2*u*cov + u^2*var_b3), t, the two-sided p from the t distribution with --df degrees
of freedom (the normal distribution without --df), and the interval at --level (default 0.95).
Johnson-Neyman: the moderator values where t equals the critical value, the roots of
(b3^2 - t^2 var_b3) u^2 + 2 (b1 b3 - t^2 cov) u + (b1^2 - t^2 var_b1) = 0; where the interval of the
slope excludes zero; which roots and regions lie inside [--min, --max].

Writes --out (default paths/probe.md) and prints the same as JSON; probe() returns it as a dict.
Exit code 1 when a probe value lies outside the observed range; 2 when an input is missing or
impossible (a negative variance, min above max, a slope variance that is not positive). Standard
library only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from statistics import NormalDist

PARAMETERS = ("b1", "b3", "var_b1", "var_b3", "cov_b13", "df", "w_min", "w_max", "w_mean", "w_sd", "probes", "level",
              "center")
OPTIONS = {"b1": "b1", "b3": "b3", "var_b1": "var_b1", "var_b3": "var_b3", "cov": "cov_b13", "df": "df", "min": "w_min",
           "max": "w_max", "mean": "w_mean", "sd": "w_sd", "center": "center", "level": "level"}


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b), from its continued fraction (modified Lentz)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if x > (a + 1.0) / (a + b + 2.0):                 # the fraction converges quickly only below this point
        return 1.0 - betainc(b, a, 1.0 - x)
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)) / a
    tiny = 1e-300
    f, c, d = tiny, tiny, 0.0
    for j in range(1, 2000):
        k = j - 1                                     # the j-th numerator is 1, then d_1, d_2, ...
        if k == 0:
            numerator = 1.0
        elif k % 2:
            m = (k - 1) // 2
            numerator = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        else:
            m = k // 2
            numerator = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1.0 + numerator * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + numerator / c
        c = c if abs(c) > tiny else tiny
        f *= c * d
        if abs(c * d - 1.0) < 1e-15:
            break
    return front * f


def two_sided_p(t: float, df) -> float:
    """P(|T| >= |t|) for Student's t with df degrees of freedom; the normal distribution when df is None."""
    if df is None:
        return 2.0 * (1.0 - NormalDist().cdf(abs(t)))
    return betainc(df / 2.0, 0.5, df / (df + t * t))


def critical(level: float, df) -> float:
    """The two-sided critical value of t (or z when df is None) at the interval level."""
    alpha = 1.0 - level
    if df is None:
        return NormalDist().inv_cdf(1.0 - alpha / 2.0)
    low, high = 0.0, 1.0
    while two_sided_p(high, df) > alpha:
        high *= 2.0
    for _ in range(200):
        middle = (low + high) / 2.0
        low, high = (middle, high) if two_sided_p(middle, df) > alpha else (low, middle)
    return (low + high) / 2.0


def resolve(probes, mean: float, sd: float) -> list:
    """(label, value) for each probe: a number, or mean, mean+Ksd, mean-Ksd on the moderator's scale."""
    out = []
    for item in probes if isinstance(probes, (list, tuple)) else [probes]:
        try:
            value = float(item)
        except (TypeError, ValueError):
            value = None
        if value is not None and math.isfinite(value) and not isinstance(item, bool):
            out.append((f"{value:g}", value))
            continue
        text = str(item).replace(" ", "").lower()
        match = re.fullmatch(r"mean(?:([+-])(\d+(?:\.\d+)?)sd)?", text)
        if not match:
            raise ValueError(f"probe {item!r} is not a number, mean, mean+Ksd or mean-Ksd")
        k = float(match.group(2) or 0.0) * (-1.0 if match.group(1) == "-" else 1.0)
        out.append((text, mean + k * sd))
    if not out:
        raise ValueError("no probe values")
    return out


def johnson_neyman(b1, b3, var_b1, var_b3, cov_b13, crit, center, w_min, w_max) -> dict:
    """Where the slope's t equals the critical value, and where its interval excludes zero."""
    t2, inf = crit * crit, math.inf
    a, b, c = b3 * b3 - t2 * var_b3, b1 * b3 - t2 * cov_b13, b1 * b1 - t2 * var_b1
    if abs(a) <= 1e-12 * max(b3 * b3, t2 * var_b3, 1e-300):        # b3 itself sits at the critical value
        roots = [-c / (2.0 * b)] if b else []
        regions = ([(roots[0], inf)] if b > 0 else [(-inf, roots[0])]) if b else ([(-inf, inf)] if c > 0 else [])
    elif b * b - a * c <= 0:
        roots, regions = [], [(-inf, inf)] if a > 0 else []
    else:
        root = math.sqrt(b * b - a * c)
        roots = sorted(((-b - root) / a, (-b + root) / a))
        regions = [(-inf, roots[0]), (roots[1], inf)] if a > 0 else [(roots[0], roots[1])]
    roots = [u + center for u in roots]
    regions = [(low + center, high + center) for low, high in regions]
    inside = []
    for low, high in regions:
        start, end = max(low, w_min), min(high, w_max)
        if start < end:
            middle = (start + end) / 2.0
            inside.append({"from": start, "to": end,
                           "sign": "positive" if b1 + b3 * (middle - center) > 0 else "negative"})
    if inside:
        summary = "the interval of the slope excludes zero " + ", and ".join(
            f"from {r['from']:.4g} to {r['to']:.4g} ({r['sign']})" for r in inside)
    else:
        summary = "the interval of the slope includes zero everywhere"
    return {"roots": roots, "roots_in_range": [w_min <= r <= w_max for r in roots],
            "significant": [[None if math.isinf(low) else low, None if math.isinf(high) else high] for low, high in regions],
            "significant_in_range": inside, "summary": f"{summary} in the observed range {w_min:g} to {w_max:g}"}


def probe(b1, b3, var_b1, var_b3, cov_b13, df, w_min, w_max, w_mean, w_sd, probes, level=0.95, center=0.0) -> dict:
    """Simple slopes at the probe values and the Johnson-Neyman bounds; see the module docstring."""
    numbers = {"b1": b1, "b3": b3, "var_b1": var_b1, "var_b3": var_b3, "cov_b13": cov_b13, "w_min": w_min,
               "w_max": w_max, "w_mean": w_mean, "w_sd": w_sd, "level": level, "center": center}
    bad = [name for name, value in numbers.items()
           if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)]
    if bad:
        raise ValueError(f"not a finite number: {', '.join(bad)}")
    if df is not None and (isinstance(df, bool) or not isinstance(df, (int, float)) or not df > 0):
        raise ValueError("df must be the positive residual degrees of freedom, or None for the normal distribution")
    if min(var_b1, var_b3, w_sd) < 0 or w_min > w_max or not 0 < level < 1:
        raise ValueError("a variance or the SD is negative, min is above max, or the level is not between 0 and 1")
    crit = critical(level, df)
    slopes = []
    for label, w in resolve(probes, w_mean, w_sd):
        u = w - center
        variance = var_b1 + 2.0 * u * cov_b13 + u * u * var_b3
        if not variance > 0:
            raise ValueError(f"the variance of the slope at {label} is not positive: check var_b1, var_b3 and cov_b13")
        slope, se = b1 + b3 * u, math.sqrt(variance)
        slopes.append({"label": label, "w": w, "in_range": w_min - 1e-9 <= w <= w_max + 1e-9, "slope": slope, "se": se,
                       "t": slope / se, "p": two_sided_p(slope / se, df), "low": slope - crit * se, "high": slope + crit * se})
    return {"level": level, "df": df, "distribution": "normal" if df is None else "t", "t_crit": crit, "b1": b1, "b3": b3,
            "center": center, "range": {"min": w_min, "max": w_max, "mean": w_mean, "sd": w_sd}, "slopes": slopes,
            "out_of_range": [s["label"] for s in slopes if not s["in_range"]],
            "jn": johnson_neyman(b1, b3, var_b1, var_b3, cov_b13, crit, center, w_min, w_max)}


def markdown(result: dict) -> str:
    level, r, df = f"{result['level']:.0%}", result["range"], result["df"]
    test = f"t with {df:g} df" if df is not None else "z (normal)"
    lines = ["# Simple slopes", "", f"The slope of the focal predictor at each probe value of the moderator, with {level} "
             f"intervals and {test}. Observed range of the moderator: {r['min']:g} to {r['max']:g} (mean {r['mean']:.4g}, "
             f"SD {r['sd']:.4g}).", "", f"| Probe | Moderator value | Slope | SE | {test.split()[0]} | p | {level} interval "
             "| In range |", "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {s['label']} | {s['w']:.4g} | {s['slope']:.4g} | {s['se']:.4g} | {s['t']:.3f} | {s['p']:.3g} | "
              f"{s['low']:.4g} to {s['high']:.4g} | {'yes' if s['in_range'] else 'no'} |" for s in result["slopes"]]
    jn = result["jn"]
    roots = ", ".join(f"{w:.4g} ({'inside' if inside else 'outside'} the range)"
                      for w, inside in zip(jn["roots"], jn["roots_in_range"])) or "none"
    lines += ["", f"Johnson-Neyman roots: {roots}. In words: {jn['summary']}."]
    if result["out_of_range"]:
        lines += ["", "Outside the observed range: " + ", ".join(result["out_of_range"]) + ". Probe inside the range "
                  "instead (for example the 16th, 50th and 84th percentiles of the analysed rows)."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Simple slopes and Johnson-Neyman bounds inside the observed range.")
    parser.add_argument("--json", type=Path, help="JSON file with the arguments of probe() by name")
    for option in OPTIONS:
        parser.add_argument(f"--{option.replace('_', '-')}", dest=option, type=float)
    parser.add_argument("--probe", nargs="+", help="Moderator values: numbers, mean, mean+1sd, mean-1sd")
    parser.add_argument("--out", type=Path, default=Path("paths/probe.md"), help="Markdown table (default paths/probe.md)")
    args = parser.parse_args(argv)
    inputs = {}
    try:
        if args.json:
            inputs = json.loads(args.json.read_text(encoding="utf-8"))
            if not isinstance(inputs, dict):
                raise ValueError("the JSON must be an object of probe() arguments")
        inputs.update({key: getattr(args, option) for option, key in OPTIONS.items() if getattr(args, option) is not None})
        if args.probe:
            inputs["probes"] = args.probe
        missing = [key for key in PARAMETERS if key not in inputs and key not in ("df", "level", "center")]
        if missing:
            raise ValueError(f"missing: {', '.join(missing)}")
        result = probe(**{key: inputs[key] for key in PARAMETERS if key in inputs} | {"df": inputs.get("df")})
    except (OSError, ValueError, TypeError) as exc:
        print(f"probe_interaction: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown(result), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["out_of_range"] else 0


if __name__ == "__main__":
    sys.exit(main())
