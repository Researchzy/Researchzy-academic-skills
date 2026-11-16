#!/usr/bin/env python3
"""Pool the effects of a meta-analysis, record every result, and draw forest and funnel plots.

  meta_pool.py meta-analysis/effects.csv                         random effects, REML, Hartung-Knapp
  meta_pool.py meta-analysis/effects.csv --model random --tau2 REML --ci HK --primary "weight change"
  meta_pool.py meta-analysis/effects.csv --subgroup dose --level 0.95
  meta_pool.py meta-analysis/effects.csv --model fixed --no-plots

Each pool of effects.csv (one outcome at one timepoint) is pooled as the plan says:
  fixed    inverse variance; Mantel-Haenszel or Peto when effects.csv says so (effect_sizes.py --sparse)
  random   tau^2 by REML (Fisher scoring; when it does not converge, Paule-Mandel, and the record says
           so), PM, or DL truncated at 0 with the raw value kept; the interval by Hartung-Knapp on
           k - 1 df with its floor (q at least 1, so never narrower than the Wald interval), or Wald
Heterogeneity: Q with its df and p; I^2 = (Q - df)/Q truncated at 0, the raw value kept; tau^2, tau.
A random-effects pool with k >= 3 has the prediction interval mu +- t(k - 2) sqrt(tau^2 + SE^2), SE
from the chosen interval method; otherwise the record says why there is none.
Small-study test only at k >= 10 (a convention): Egger (MD, Z, HR, GENERIC), Peters (OR, RR; needs
counts), Egger on the modified SE sqrt(1/n1 + 1/n2) (SMD); none for RD. Subgroups (--subgroup, a study
column of the table): each group with its own tau^2; the test between groups (Q from each group's
estimate and Wald SE) only when every group has at least 4 studies (a convention). Sensitivity:
leave-one-out, without estimated rows, the other model, the other tau^2 estimators, the other
interval, and for sparse binary pools the other zero-event methods.

Records through rz_results (the copy next to this file) into meta-analysis/results.json: each main
pool with its p, sensitivity and subgroup results without one; the meta-analysis fields go in
extra["meta"]. Writes pooled.md and, with matplotlib, forest-<pool> and funnel-<pool> as PDF, PNG and
SVG, and prints a JSON summary. Exit code 0 on success; 1 when effects.csv has refused rows or a pool
cannot be pooled as planned (nothing is recorded); 2 when numpy or scipy is missing or effects.csv
cannot be read.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import importlib.util
import io
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import numpy as np
    from scipy import optimize, stats
except ImportError:          # reported in main()
    np = optimize = stats = None

LOG = ("OR", "RR", "HR")
NAMES = {"MD": "mean difference", "SMD": "standardised mean difference (Hedges' g)", "OR": "odds ratio",
         "RR": "risk ratio", "RD": "risk difference", "HR": "hazard ratio", "Z": "correlation", "GENERIC": "effect"}
UNITS = {"SMD": "SD", "OR": "ratio", "RR": "ratio", "HR": "ratio", "RD": "proportion", "Z": "unitless"}
TAU2 = ("REML", "PM", "DL")
MODEL = {"fixed": "fixed-effect", "random": "random-effects"}
SMALL_K = 10        # small-study tests only from this many studies (a convention)
SUBGROUP_K = 4      # the test between subgroups only when every group has this many studies (a convention)
OKABE = ("#0072B2", "#D55E00", "#000000", "#999999")


class PoolError(ValueError):
    pass


def tau2_estimate(y, v, method):
    """(tau^2, raw value, converged) by REML (Fisher scoring), Paule-Mandel or DerSimonian-Laird."""
    w = 1 / v
    mu = (w * y).sum() / w.sum()
    q, k = float((w * (y - mu) ** 2).sum()), len(y)
    c = w.sum() - (w ** 2).sum() / w.sum()
    dl = (q - (k - 1)) / c if c > 0 else 0.0
    if method == "DL":
        return max(0.0, dl), dl, True
    if method == "PM":
        def excess(t2):
            ws = 1 / (v + t2)
            return float((ws * (y - (ws * y).sum() / ws.sum()) ** 2).sum()) - (k - 1)
        if excess(0.0) <= 0:
            return 0.0, 0.0, True
        high = max(dl, float(v.mean()), 1e-12)
        while excess(high) > 0:
            high *= 2
        t2 = optimize.brentq(excess, 0.0, high, xtol=1e-14, rtol=1e-12)
        return t2, t2, True
    t2 = max(0.0, dl)
    for _ in range(100):
        ws = 1 / (v + t2)
        sw, sw2 = ws.sum(), (ws ** 2).sum()
        mu = (ws * y).sum() / sw
        score = (ws ** 2 * (y - mu) ** 2).sum() - sw + sw2 / sw
        info = sw2 - 2 * (ws ** 3).sum() / sw + (sw2 / sw) ** 2
        new = max(0.0, float(t2 + score / info))
        if abs(new - t2) <= 1e-10 * max(1.0, t2):
            return new, new, True
        t2 = new
    return t2, t2, False


def heterogeneity(y, v, centre=None) -> dict:
    """Q around the inverse-variance mean (or around the given centre), its df and p; I^2 truncated, raw kept."""
    w = 1 / v
    q = float((w * (y - ((w * y).sum() / w.sum() if centre is None else centre)) ** 2).sum())
    df = len(y) - 1
    raw = (q - df) / q * 100 if q > 0 else None
    return {"Q": q, "Q_df": df, "Q_p": float(stats.chi2.sf(q, df)) if df > 0 else None,
            "I2": max(0.0, raw) if raw is not None else 0.0, "I2_raw": raw}


def inverse_variance(y, v, model, method, ci, level) -> dict:
    """One inverse-variance pool on the analysis scale."""
    k, alpha = len(y), 1 - level
    out = {"method": "inverse variance", "model": model, **heterogeneity(y, v), "notes": []}
    if model == "fixed":
        w = 1 / v
        mu, se = float((w * y).sum() / w.sum()), float(math.sqrt(1 / w.sum()))
        out.update(tau2=None, tau=None, tau2_method=None, ci_method="Wald", pi=None, pi_reason="fixed-effect model: no "
                   "between-study variance, so no prediction interval", se_wald=se, weights=w / w.sum())
    else:
        used = method
        t2, raw, ok = tau2_estimate(y, v, method)
        if not ok:
            used, (t2, raw, _) = "PM", tau2_estimate(y, v, "PM")
            out["notes"].append("REML did not converge in 100 iterations; tau^2 by Paule-Mandel")
        ws = 1 / (v + t2)
        mu, se = float((ws * y).sum() / ws.sum()), float(math.sqrt(1 / ws.sum()))
        out.update(tau2=t2, tau=math.sqrt(t2), tau2_method=used, tau2_method_planned=method, tau2_converged=ok,
                   se_wald=se, weights=ws / ws.sum())
        if method == "DL":
            out["tau2_raw"] = raw
        out["ci_method"] = "Hartung-Knapp" if ci == "HK" else "Wald"
        if ci == "HK":
            hk = float((ws * (y - mu) ** 2).sum() / (k - 1))
            se = math.sqrt(max(1.0, hk) / ws.sum())
            out.update(hk_q=hk, hk_floor_applied=hk < 1)
            if hk < 1:
                out["notes"].append(f"Hartung-Knapp q = {hk:.3g} < 1: floor applied (Wald SE with t on {k - 1} df)")
        if k >= 3:
            half = float(stats.t.ppf(1 - alpha / 2, k - 2)) * math.sqrt(t2 + se ** 2)
            out.update(pi=(mu - half, mu + half), pi_reason=None)
        else:
            out.update(pi=None, pi_reason=f"k = {k}: a prediction interval needs at least 3 studies (k - 2 df)")
    t_based = out["ci_method"] == "Hartung-Knapp"
    crit = float(stats.t.ppf(1 - alpha / 2, k - 1) if t_based else stats.norm.ppf(1 - alpha / 2))
    stat = mu / se
    p = float(2 * (stats.t.sf(abs(stat), k - 1) if t_based else stats.norm.sf(abs(stat))))
    out.update(mu=mu, se=se, low=mu - crit * se, high=mu + crit * se, stat_name="t" if t_based else "z", stat=stat,
               df=k - 1 if t_based else None, p=p)
    return out


def counts(rows):
    a, n1, c, n2 = (np.array([float(r[key]) for r in rows]) for key in ("e1", "n1", "e2", "n2"))
    return a, n1 - a, c, n2 - c, n1, n2, n1 + n2


def mantel_haenszel(rows, measure, level) -> dict:
    """Mantel-Haenszel (OR, RR, RD) or Peto (measure 'PETO') fixed effect from the 2x2 counts."""
    a, b, c, d, n1, n2, n = counts(rows)
    y, v = np.array([float(r["yi"]) for r in rows]), np.array([float(r["vi"]) for r in rows])
    if measure == "PETO":       # per-study (O - E)/V; their inverse-variance Q is the Peto Q
        o_e, var = a - n1 * (a + c) / n, n1 * n2 * (a + c) * (b + d) / (n ** 2 * (n - 1))
        mu, se, weights = o_e.sum() / var.sum(), math.sqrt(1 / var.sum()), var
        y, v = o_e / var, 1 / var
    elif measure == "RD":
        weights = n1 * n2 / n
        mu = ((a * n2 - c * n1) / n).sum() / weights.sum()
        se = math.sqrt(((a * b * n2 ** 3 + c * d * n1 ** 3) / (n1 * n2 * n ** 2)).sum()) / weights.sum()
    else:
        r_, s_ = (a * d / n, b * c / n) if measure == "OR" else (a * n2 / n, c * n1 / n)
        if r_.sum() <= 0 or s_.sum() <= 0:
            raise PoolError("the Mantel-Haenszel ratio is 0 or infinite: one arm has no events in any study")
        mu, weights = math.log(r_.sum() / s_.sum()), s_
        if measure == "OR":
            p_, q_ = (a + d) / n, (b + c) / n
            se = math.sqrt((p_ * r_).sum() / (2 * r_.sum() ** 2) + (p_ * s_ + q_ * r_).sum() / (2 * r_.sum() * s_.sum())
                           + (q_ * s_).sum() / (2 * s_.sum() ** 2))
        else:
            se = math.sqrt(((n1 * n2 * (a + c) - a * c * n) / n ** 2).sum() / (r_.sum() * s_.sum()))
    het = heterogeneity(y, v, None if measure == "PETO" else mu)
    z = float(stats.norm.ppf(1 - (1 - level) / 2))
    note = ("Q from each study's own estimate (0.5 added to zero cells) around the Mantel-Haenszel estimate"
            if measure != "PETO" else "Q of the Peto method")
    return {"method": "Peto" if measure == "PETO" else "Mantel-Haenszel", "model": "fixed", **het, "tau2": None,
            "tau": None, "tau2_method": None, "ci_method": "Wald", "pi": None, "notes": [note],
            "pi_reason": "fixed-effect model: no between-study variance, so no prediction interval", "mu": float(mu),
            "se": se, "se_wald": se, "low": mu - z * se, "high": mu + z * se, "stat_name": "z", "stat": mu / se, "df": None,
            "p": float(2 * stats.norm.sf(abs(mu / se))), "weights": weights / weights.sum(), "study_y": y, "study_v": v}


def pool(rows, measure, how, args) -> dict:
    """how: (model, tau2 method, ci method) for inverse variance, or 'mh' / 'peto'."""
    if len(rows) < 2:
        raise PoolError("fewer than 2 studies")
    if how in ("mh", "peto"):
        if not all(r.get(key) for r in rows for key in ("e1", "n1", "e2", "n2")):
            raise PoolError("Mantel-Haenszel and Peto need the 2x2 counts of every study")
        return mantel_haenszel(rows, "PETO" if how == "peto" else measure, args.level)
    y, v = np.array([float(r["yi"]) for r in rows]), np.array([float(r["vi"]) for r in rows])
    return inverse_variance(y, v, *how, args.level)


def small_study(rows, measure) -> dict:
    """The test matched to the measure, only at k >= SMALL_K: (W)LS slope with a t test on k - 2 df."""
    k = len(rows)
    if k < SMALL_K:
        return {"status": "not run", "reason": f"k = {k}, fewer than {SMALL_K} studies (a convention)"}
    if measure == "RD":
        return {"status": "not run", "reason": "no small-study test is matched to the risk difference"}
    y, v = np.array([float(r["yi"]) for r in rows]), np.array([float(r["vi"]) for r in rows])
    try:
        if measure in ("OR", "RR"):
            a, b, c, d, n1, n2, n = counts(rows)
            name, x, w = "Peters", 1 / n, (a + c) * (b + d) / n
        elif measure == "SMD":
            n1, n2 = (np.array([float(r[key]) for r in rows]) for key in ("n1", "n2"))
            name, x = "Egger with the modified SE sqrt(1/n1 + 1/n2)", np.sqrt(1 / n1 + 1 / n2)
            w = 1 / x ** 2
        else:
            name, x, w = "Egger", np.sqrt(v), 1 / v
    except (KeyError, ValueError):
        return {"status": "not run", "reason": "the test needs the arm sizes (and counts) of every study"}
    design = np.column_stack([np.ones(k), x])
    xtwx = design.T @ (design * w[:, None])
    beta = np.linalg.solve(xtwx, design.T @ (w * y))
    s2 = float((w * (y - design @ beta) ** 2).sum() / (k - 2))
    se = math.sqrt(s2 * np.linalg.inv(xtwx)[1, 1])
    t = float(beta[1] / se)
    return {"status": "run", "test": name, "k": k, "slope": float(beta[1]), "se": se, "t": t, "df": k - 2,
            "p": float(2 * stats.t.sf(abs(t), k - 2)), "note": "asymmetry can have causes other than publication bias"}


def scale(measure, x):
    if x is None:
        return None
    return math.exp(x) if measure in LOG else math.tanh(x) if measure == "Z" else x


def summary_fields(res, measure, level, studies) -> dict:
    """The meta-analysis fields of one result, on the reported scale where they are estimates."""
    meta = {k: res.get(k) for k in ("model", "method", "tau2_method", "tau2_method_planned", "tau2_converged",
                                    "ci_method", "hk_floor_applied", "Q", "Q_df", "Q_p", "I2", "I2_raw", "tau2",
                                    "tau2_raw", "tau") if k in res}
    meta.update(k=len(studies), measure=measure, notes=res["notes"], pi_reason=res.get("pi_reason"),
                scale="log" if measure in LOG else "Fisher z" if measure == "Z" else "as reported",
                pi={"low": scale(measure, res["pi"][0]), "high": scale(measure, res["pi"][1]), "level": level}
                if res.get("pi") else None)
    if measure in LOG or measure == "Z":       # the analysis scale, kept beside the reported one
        meta["analysis_scale"] = {"estimate": res["mu"], "low": res["low"], "high": res["high"], "se": res["se"]}
    meta["weights"] = {r["study"]: round(float(w) * 100, 2) for r, w in zip(studies, res["weights"])}
    return meta


def plots(name, rows, res, measure, units, folder, level) -> list:
    """Forest and funnel plots as PDF, PNG and SVG; [] when matplotlib is missing."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import ticker
    except ImportError:
        return []
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "pool"
    y = np.array(res.get("study_y", [float(r["yi"]) for r in rows]))
    se = np.sqrt(np.array(res.get("study_v", [float(r["vi"]) for r in rows])))
    z = float(stats.norm.ppf(1 - (1 - level) / 2))
    k, written = len(rows), []
    with plt.rc_context({"font.size": 7, "pdf.fonttype": 42, "svg.fonttype": "none", "axes.spines.top": False,
                         "axes.spines.right": False}):
        fig, ax = plt.subplots(figsize=(170 / 25.4, (k + 5) * 5.5 / 25.4))
        fig.subplots_adjust(left=0.24, right=0.66, top=0.97, bottom=0.6 / ((k + 5) * 5.5 / 25.4))
        rows_y = np.arange(k, 0, -1) + 1.5
        back = np.vectorize(lambda x: scale(measure, x))
        lo, hi, mid = back(y - z * se), back(y + z * se), back(y)
        weights = np.array(res["weights"])
        ax.text(1.03, k + 2.1, f"Estimate [{level:.0%} CI]   Weight", transform=ax.get_yaxis_transform(), va="center",
                fontweight="bold")
        for i in range(k):
            ax.plot([lo[i], hi[i]], [rows_y[i]] * 2, color=OKABE[2], lw=0.8)
            ax.plot(mid[i], rows_y[i], "s", color=OKABE[0], ms=3 + 6 * math.sqrt(weights[i] / weights.max()))
            ax.text(1.03, rows_y[i], f"{mid[i]:.2f} [{lo[i]:.2f}, {hi[i]:.2f}]   {weights[i] * 100:.1f}%",
                    transform=ax.get_yaxis_transform(), va="center")
        est, low, high = (scale(measure, res[key]) for key in ("mu", "low", "high"))
        ax.fill([low, est, high, est], [0.8, 1.05, 0.8, 0.55], color=OKABE[1])
        ax.text(1.03, 0.8, f"{est:.2f} [{low:.2f}, {high:.2f}]", transform=ax.get_yaxis_transform(), va="center")
        labels = [r["study"] for r in rows] + ["Pooled"]
        ticks = list(rows_y) + [0.8]
        if res.get("pi"):
            p_lo, p_hi = scale(measure, res["pi"][0]), scale(measure, res["pi"][1])
            ax.plot([p_lo, p_hi], [0.0, 0.0], color=OKABE[1], lw=1.2, ls="--")
            ax.text(1.03, 0.0, f"PI [{p_lo:.2f}, {p_hi:.2f}]", transform=ax.get_yaxis_transform(), va="center")
            labels.append("Prediction interval")
            ticks.append(0.0)
        ax.axvline(1.0 if measure in LOG else 0.0, color=OKABE[3], lw=0.6)
        if measure in LOG:
            ax.set_xscale("log")
            ax.xaxis.set_major_locator(ticker.LogLocator(subs=(1.0, 2.0, 5.0)))
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:g}"))
            ax.xaxis.set_minor_formatter(ticker.NullFormatter())
        ax.set_yticks(ticks, labels)
        ax.set_ylim(-0.7, k + 2.3)
        ax.set_xlabel(f"{NAMES[measure]}" + (f" ({units})" if units not in ("ratio", "unitless") else ""))
        written += save(fig, folder / f"forest-{slug}")
        plt.close(fig)
        fig, ax = plt.subplots(figsize=(90 / 25.4, 75 / 25.4))
        fig.subplots_adjust(left=0.18, right=0.96, top=0.86, bottom=0.17)
        centre, top = res["mu"], float(se.max()) * 1.1
        ax.plot([centre - z * top, centre, centre + z * top], [top, 0, top], color=OKABE[3], lw=0.7, ls="--")
        ax.axvline(centre, color=OKABE[1], lw=0.8)
        ax.plot(y, se, "o", color=OKABE[0], ms=3.5)
        ax.set_ylim(top, 0)
        ax.set_xlabel(NAMES[measure] + (" (log scale)" if measure in LOG else " (Fisher z)" if measure == "Z" else ""))
        ax.set_ylabel("standard error")
        ax.set_title(f"k = {k}" + (f": too few studies to judge asymmetry (fewer than {SMALL_K})" if k < SMALL_K else ""),
                     fontsize=6.5)
        written += save(fig, folder / f"funnel-{slug}")
        plt.close(fig)
    return written


def save(fig, stem: Path) -> list:
    paths = []
    for ext, meta in (("pdf", {"CreationDate": None}), ("png", None), ("svg", {"Date": None})):
        fig.savefig(stem.with_suffix(f".{ext}"), dpi=300, metadata=meta)
        paths.append(str(stem.with_suffix(f".{ext}")))
    return paths


def analyse(name, rows, excluded, args) -> dict:
    """Every analysis of one pool, computed before anything is recorded."""
    measure, sparse = rows[0]["measure"], rows[0].get("sparse", "")
    if len(rows) < 2:
        return {"name": name, "measure": measure, "rows": rows, "single": True}
    planned = (args.model, args.tau2, args.ci)
    main_how = sparse if sparse in ("mh", "peto") else planned
    res = pool(rows, measure, main_how, args)
    if sparse in ("mh", "peto") and args.model == "random":
        res["notes"].append(f"the zero-event choice ({sparse}) is a fixed-effect method; it replaces the planned random effects")
    sens = []
    def add(label, subset, how):
        try:
            sens.append((label, subset, pool(subset, measure, how, args)))
        except PoolError as exc:
            sens.append((label, subset, str(exc)))
    if len(rows) >= 3:
        for r in rows:
            add(f"leave out {r['study']}", [x for x in rows if x is not r], main_how)
    kept = [r for r in rows if r.get("estimated") != "yes"]
    if len(kept) < len(rows):
        add("without estimated rows", kept, main_how)
    other_model = ("random", args.tau2, args.ci) if res["model"] == "fixed" else ("fixed", None, None)
    if sparse in ("", "iv", "cc"):
        add(MODEL[other_model[0]], rows, other_model)
    if res["model"] == "random":
        for method in TAU2:
            if method != res["tau2_method"]:
                add(f"tau2 by {method}", rows, ("random", method, args.ci))
        add("Wald interval" if args.ci == "HK" else "Hartung-Knapp interval", rows,
            ("random", res["tau2_method"], "Wald" if args.ci == "HK" else "HK"))
    if sparse == "cc" and any(r.get("zero_cell") == "yes" for r in rows):
        add("without the studies given 0.5", [r for r in rows if r.get("zero_cell") != "yes"], planned)
    if sparse in ("cc", "iv", "peto"):
        add("Mantel-Haenszel", rows, "mh")
    if sparse in ("mh", "iv") and measure == "OR":
        add("Peto", rows, "peto")
    if sparse in ("mh", "peto"):
        add("inverse variance, 0.5 added to studies with a zero cell", rows, planned)
    groups = []
    for column in args.subgroup:
        values = {}
        for r in rows:
            values.setdefault(r.get(column) or "(not given)", []).append(r)
        fits = []
        for value, subset in values.items():
            try:
                fits.append((value, subset, pool(subset, measure, main_how, args)))
            except PoolError:
                fits.append((value, subset, None))
        small = [f"{value} ({len(subset)})" for value, subset, _ in fits if len(subset) < SUBGROUP_K]
        test = {"status": "not run", "reason": "only one group"} if len(fits) < 2 else \
            {"status": "not run", "reason": f"fewer than {SUBGROUP_K} studies in {', '.join(small)}: described only"} if small else None
        if test is None:
            mus, ses = np.array([f["mu"] for _, _, f in fits]), np.array([f["se_wald"] for _, _, f in fits])
            w = 1 / ses ** 2
            qb = float((w * (mus - (w * mus).sum() / w.sum()) ** 2).sum())
            test = {"status": "run", "Q_between": qb, "df": len(fits) - 1, "p": float(stats.chi2.sf(qb, len(fits) - 1))}
        groups.append({"column": column, "fits": fits, "test": test})
    return {"name": name, "measure": measure, "rows": rows, "res": res, "sens": sens, "groups": groups,
            "small": small_study(rows, measure), "excluded": excluded, "single": False}


def describe(measure, res) -> str:
    est, low, high = (scale(measure, res[k]) for k in ("mu", "low", "high"))
    return f"{est:.4g} ({low:.4g} to {high:.4g})"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pool the effects of a meta-analysis and record the results.")
    parser.add_argument("effects", type=Path, help="effects.csv from effect_sizes.py")
    parser.add_argument("--model", choices=("random", "fixed"), default="random")
    parser.add_argument("--tau2", choices=TAU2, default="REML", help="tau^2 estimator (default REML)")
    parser.add_argument("--ci", choices=("HK", "Wald"), default="HK", help="interval method (default HK)")
    parser.add_argument("--level", type=float, default=0.95)
    parser.add_argument("--subgroup", action="append", default=[], help="a study column of the table (repeatable)")
    parser.add_argument("--primary", action="append", default=[], help="the primary outcome (repeatable)")
    parser.add_argument("--out", type=Path, default=Path("meta-analysis"))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)
    if np is None:
        print(json.dumps({"status": "not_run", "missing": [m for m in ("numpy", "scipy") if importlib.util.find_spec(m) is None],
                          "message": "meta_pool.py needs numpy and scipy; install them (python3 -m pip install --user "
                                     "numpy scipy) after asking the user"}, indent=2))
        return 2
    if not 0.5 < args.level < 1:
        parser.error("--level must lie between 0.5 and 1")
    try:
        with args.effects.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            table, columns = list(reader), reader.fieldnames or []
        missing = [c for c in ("pool", "study", "outcome", "measure", "yi", "vi", "se", "refused", "excluded") if c not in columns]
        if missing:
            raise ValueError(f"not an effects.csv from effect_sizes.py (no {', '.join(missing)})")
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as exc:
        print(f"meta_pool: cannot read {args.effects}: {exc}", file=sys.stderr)
        return 2
    if any(column not in columns for column in args.subgroup):
        parser.error(f"--subgroup: effects.csv has no column {next(c for c in args.subgroup if c not in columns)!r}")
    refused = [f"{r.get('pool')}, {r.get('study')}: {r['refused']}" for r in table if r.get("refused")]
    if refused or not table:
        print(json.dumps({"status": "refused", "refused": refused or ["effects.csv has no rows"],
                          "message": "fix extraction.csv, run effect_sizes.py again, then pool"}, indent=2))
        return 1
    pools: dict = {}
    for r in table:
        pools.setdefault(r["pool"], {"rows": [], "excluded": []})["rows" if not r.get("excluded") else "excluded"].append(r)
    analyses = []
    try:
        for name, item in pools.items():
            analyses.append(analyse(name, item["rows"], item["excluded"], args))
    except PoolError as exc:
        print(json.dumps({"status": "not_pooled", "pool": name, "reason": str(exc)}, indent=2))
        return 1
    import rz_results as rz
    rz.OUT = str(args.out)
    report, summary, drawn = ["# Pooled results", ""], [], []
    for a in analyses:
        name, measure, rows = a["name"], a["measure"], a["rows"]
        units = UNITS.get(measure) or (rows[0].get("units") if rows else "") or "as reported"
        outcome = rows[0]["outcome"] if rows else name
        role = "primary" if outcome in args.primary or name in args.primary or (len(analyses) == 1 and not args.primary) \
            else "secondary"
        direction = "treatment vs control" if measure in LOG else "treatment minus control"
        question = f"What is the pooled {NAMES[measure]} for {name}, {direction}?"
        participants = lambda subset: max(1, round(sum(float(r["participants"]) for r in subset)))  # noqa: E731
        if a["single"]:
            rz.record(id=name, question=question, family=name, role=role, test="not pooled", unit="study",
                      n={"studies": len(rows)}, kept=False, reason="fewer than 2 studies: report the study's own estimate")
            report += [f"## {name}", "", "Not pooled: fewer than 2 studies.", ""]
            summary.append({"pool": name, "status": "not pooled: fewer than 2 studies"})
            continue
        res, z = a["res"], float(stats.norm.ppf(1 - (1 - args.level) / 2))
        meta = summary_fields(res, measure, args.level, rows)
        meta.update(analysis="main", participants=participants(rows), small_study=a["small"],
                    excluded=[{"study": r["study"], "reason": r["excluded"]} for r in a["excluded"]],
                    studies=[{"study": r["study"], "comparison": r["comparison"],
                              "estimate": scale(measure, float(r["yi"])),
                              "low": scale(measure, float(r["yi"]) - z * float(r["se"])),
                              "high": scale(measure, float(r["yi"]) + z * float(r["se"]))} for r in rows],
                    subgroups=[{"column": g["column"], "test": g["test"],
                                "groups": [{"value": value, "k": len(subset)} for value, subset, _ in g["fits"]]}
                               for g in a["groups"]])
        test = {"inverse variance": f"{MODEL[res['model']]} inverse-variance meta-analysis", "Mantel-Haenszel":
                "Mantel-Haenszel fixed-effect meta-analysis", "Peto": "Peto fixed-effect meta-analysis"}[res["method"]]
        if res["model"] == "random":
            test += f", tau^2 by {res['tau2_method']}, {res['ci_method']} interval"
        estimate = {"name": f"pooled {NAMES[measure]}, {direction}", "value": scale(measure, res["mu"]), "units": units}
        interval = {"low": scale(measure, res["low"]), "high": scale(measure, res["high"]), "level": args.level}
        rz.record(id=name, question=question, family=name, role=role, test=test, unit="study",
                  n={"studies": len(rows), "participants": participants(rows)}, estimate=estimate, interval=interval,
                  statistic={"name": res["stat_name"], "value": res["stat"]}, df=res["df"], p=res["p"],
                  effect_size="estimate", extra={"meta": meta})
        report += [f"## {name}", "", f"{test}; k = {len(rows)}, {participants(rows)} participants" +
                   (f"; {len(a['excluded'])} left out ({', '.join(r['study'] for r in a['excluded'])})" if a["excluded"] else ""), "",
                   f"- Pooled {NAMES[measure]}: {describe(measure, res)}"
                   + ("" if units in ("ratio", "unitless") else f" {units}") + f"; {res['stat_name']}"
                   + (f"({res['df']})" if res["df"] else "") + f" = {res['stat']:.3g}, p = {res['p']:.2g}",
                   "- Prediction interval: " + (f"{meta['pi']['low']:.4g} to {meta['pi']['high']:.4g}" if meta["pi"]
                                                else f"none ({res['pi_reason']})"),
                   f"- Heterogeneity: Q = {res['Q']:.4g} (df = {res['Q_df']}, p = {res['Q_p']:.2g}); I² = {res['I2']:.1f}%"
                   + (f" (raw {res['I2_raw']:.1f}%)" if res["I2_raw"] is not None and res["I2_raw"] < 0 else "")
                   + (f"; τ² = {res['tau2']:.4g}, τ = {res['tau']:.4g}" if res["tau2"] is not None else "")
                   + (f" (DL raw {res['tau2_raw']:.4g})" if res.get("tau2_raw", 0) < 0 else ""),
                   "- Small-study test: " + (f"{a['small']['test']}: t({a['small']['df']}) = {a['small']['t']:.3g}, "
                                             f"p = {a['small']['p']:.2g}" if a["small"]["status"] == "run"
                                             else f"not run ({a['small']['reason']})")]
        report += [f"- Note: {note}" for note in res["notes"]] + ["", "| Analysis | k | Estimate (CI) | τ² | I² |",
                                                                   "|---|---|---|---|---|"]

        def secondary(suffix, test, subset, fit, **fields):     # recorded without a p-value
            sub = dict(summary_fields(fit, measure, args.level, subset), participants=participants(subset), **fields)
            rz.record(id=f"{name} | {suffix}", question=question, family=name, role="secondary", test=test, unit="study",
                      n={"studies": len(subset), "participants": participants(subset)},
                      estimate=dict(estimate, value=scale(measure, fit["mu"])), extra={"meta": sub},
                      interval={"low": scale(measure, fit["low"]), "high": scale(measure, fit["high"]), "level": args.level})
        for label, subset, fit in a["sens"]:
            if isinstance(fit, str):
                report.append(f"| {label} | {len(subset)} | not pooled: {fit} | | |")
                continue
            secondary(label, f"sensitivity analysis: {label}", subset, fit, analysis="sensitivity", label=label)
            tau2 = "" if fit["tau2"] is None else f"{fit['tau2']:.4g}"
            report.append(f"| {label} | {len(subset)} | {describe(measure, fit)} | {tau2} | {fit['I2']:.1f}% |")
        for g in a["groups"]:
            test = g["test"]
            report += ["", f"Subgroups by {g['column']}: " + (f"Q between = {test['Q_between']:.4g} (df = {test['df']}, "
                       f"p = {test['p']:.2g})" if test["status"] == "run" else f"no test ({test['reason']})"), ""]
            for value, subset, fit in g["fits"]:
                if fit is None:
                    report.append(f"- {g['column']} = {value}: 1 study, not pooled")
                    continue
                secondary(f"{g['column']} = {value}", f"subgroup {g['column']} = {value}", subset, fit,
                          analysis="subgroup", column=g["column"], value=value)
                report.append(f"- {g['column']} = {value}: k = {len(subset)}, {describe(measure, fit)}, I² = {fit['I2']:.1f}%")
        report.append("")
        if not args.no_plots:
            drawn += plots(name, rows, res, measure, units, args.out, args.level)
        summary.append({"pool": name, "k": len(rows), "estimate": estimate["value"], "interval": [interval["low"],
                        interval["high"]], "I2": res["I2"], "tau2": res["tau2"], "pi": meta["pi"],
                        "small_study": a["small"]["status"]})
    data = [args.effects] + ([args.effects.parent / "extraction.csv"] if (args.effects.parent / "extraction.csv").is_file() else [])
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        finished = rz.finish(script=__file__, data=[str(p) for p in data], packages=("matplotlib",) if drawn else (),
                             settings={"model": args.model, "tau2": args.tau2, "ci": args.ci, "level": args.level,
                                       "subgroups": args.subgroup, "small_study_k": SMALL_K, "subgroup_k": SUBGROUP_K})
    (args.out / "pooled.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    plot_state = drawn or ("not drawn: --no-plots" if args.no_plots else "not drawn: matplotlib is not installed")
    print(json.dumps({"results": finished["results_file"], "report": str(args.out / "pooled.md"), "pools": summary,
                      "plots": plot_state, "kept": finished["kept"], "dropped": finished["dropped"]}, indent=2,
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
