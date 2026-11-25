#!/usr/bin/env python3
"""Diagnostic accuracy and prediction-model statistics, imported by the analysis script next to rz_results.

    import sys
    sys.path.insert(0, "<the scripts folder of this skill>")
    import rz_results as rz
    import rz_accuracy as ra
    rz.OUT = "diagnostic-accuracy"

  cells(y, positive)                 the 2x2 cells of a binary index result against the reference standard
  two_by_two(tp, fp, fn, tn, design=...)   sensitivity, specificity, PPV, NPV, LR+ and LR- with intervals
  dev_cutoff(y, score)               Youden's cut-off, for development data only
  auc(y, score, groups=None, seed=None)    DeLong with a logit-scale interval; a bootstrap by patient when
                                     a patient has several units
  compare_auc(y, a, b, groups=None, seed=None)   paired difference of two AUCs: DeLong, or the bootstrap
  mcnemar_pair(y, a, b, among=1)     two binary tests on the same units: exact McNemar p, and the
                                     difference in sensitivity (among=1) or specificity (among=0) with
                                     Newcombe's paired interval
  calibration(y, p, groups=None)     intercept with logit(p) as offset, slope, Wald intervals (cluster-
                                     robust by patient), lowess curve, tenths of risk, Brier score
  net_benefit(y, p, thresholds, design=...)   decision curve with treat-all and treat-none
  optimism(pipeline, X, y, groups=None, B=200, seed=...)   Harrell's bootstrap: the whole pipeline runs
                                     again on every resample of patients
  null_label_check(pipeline, X, y, groups=None, seed=...)  grouped cross-validation on permuted outcomes
  roc_figure, calibration_figure, decision_figure   drawn and saved through rz_figure.py
  record(result, id=..., question=..., model=..., dataset=...)   rz_results.record() with extra["accuracy"]

y is 1 for reference-positive units and 0 for the others. Missing values raise ValueError: exclusions
are made, counted and reported in the analysis script. groups holds the patient of each unit (a
nodule, a lesion, a visit). A pipeline is a function pipeline(X, y) -> predict, where predict(X)
returns one predicted risk per row; every step that learns from data happens inside it.

Needs numpy, scipy and statsmodels, and matplotlib for the figures; record() needs none of them.
Formulas: DeLong, DeLong and Clarke-Pearson (1988); midrank placements as in Sun and Xu (2014);
Newcombe (1998), method 10; likelihood-ratio intervals on the log scale (Simel, Samsa and Matchar
1991); net benefit, Vickers and Elkin (2006); optimism, Harrell, Lee and Mark (1996).
"""

from __future__ import annotations

import importlib
import json
import math
import numbers
import sys
import warnings
from pathlib import Path

try:
    import numpy as np
    from scipy import stats
except ImportError:            # record() works without them
    np = stats = None

__version__ = "1.0.0"
DESIGNS = ("consecutive", "cross_sectional", "case_control", "enriched")
COHORT = ("consecutive", "cross_sectional")      # the sample prevalence estimates the population's
DATASETS = ("development", "internal_validation", "test", "external", "study")
SOURCES = ("plan", "development", "published")
KINDS = ("two_by_two", "auc", "auc_difference", "paired_difference", "calibration", "net_benefit", "optimism",
         "null_label")
NAMES = {"sensitivity": "sensitivity", "specificity": "specificity", "ppv": "positive predictive value",
         "npv": "negative predictive value", "lr_positive": "positive likelihood ratio",
         "lr_negative": "negative likelihood ratio"}
METRICS = ("auc", "slope", "intercept", "brier")
EPS = 1e-10                    # risks are kept this far from 0 and 1 before logit() inside optimism()


def _need():
    if np is None:
        raise ImportError("rz_accuracy needs numpy, scipy and statsmodels; ask the user before installing them")


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _z(level) -> float:
    if not 0 < level < 1:
        raise ValueError("level must lie between 0 and 1, such as 0.95")
    return float(stats.norm.ppf(0.5 + level / 2))


def _binary(values, name="y"):
    v = np.asarray(values, dtype=float)
    if v.ndim != 1 or np.isnan(v).any() or not np.isin(v, (0, 1)).all():
        raise ValueError(f"{name} must be 0 or 1 for every unit, with no missing value: exclude rows in the analysis "
                         "script and count them")
    return v.astype(int)


def _scores(values, n, name="score"):
    v = np.asarray(values, dtype=float)
    if v.shape != (n,) or not np.isfinite(v).all():
        raise ValueError(f"{name} must hold one finite number per unit, with no missing value")
    return v


def _groups(groups, n):
    """(patient code of each unit, number of patients); codes are None when no groups are given."""
    if groups is None:
        return None, n
    ids = ["" if g is None or (isinstance(g, float) and math.isnan(g)) else str(g).strip() for g in groups]
    if len(ids) != n or not all(ids):
        raise ValueError("groups must give the patient of every unit, with no empty id")
    names = {name: i for i, name in enumerate(dict.fromkeys(ids))}
    return np.array([names[i] for i in ids]), len(names)


def _patient_rows(codes, patients):
    order = np.argsort(codes, kind="stable")
    return np.split(order, np.cumsum(np.bincount(codes, minlength=patients))[:-1])


def _seed(seed):
    if isinstance(seed, bool) or not isinstance(seed, numbers.Integral):
        raise ValueError("seed must be the whole number written in the plan")
    return int(seed)


def _counts(y, groups):
    codes, patients = _groups(groups, len(y))
    return codes, {"units": int(len(y)), "patients": int(patients), "positives": int(y.sum())}


def _auc_value(y, s):
    """The AUC as the Mann-Whitney statistic with midranks (ties count half); None with one class."""
    m = int(y.sum())
    if m == 0 or m == len(y):
        return None
    r = stats.rankdata(s)
    return float((r[y == 1].sum() - m * (m + 1) / 2) / (m * (len(y) - m)))


def _placements(pos, neg):
    """DeLong's structural components: the share of negatives each positive outranks, and the share of
    positives that outrank each negative (ties count half). Each set averages to the AUC."""
    m, n = len(pos), len(neg)
    ranks = stats.rankdata(np.concatenate([pos, neg]))
    return (ranks[:m] - stats.rankdata(pos)) / n, 1 - (ranks[m:] - stats.rankdata(neg)) / m


def _bootstrap(stat, codes, patients, B, seed):
    """stat(row indices) over B resamples of patients drawn with replacement; failed draws are dropped."""
    rng, rows, values = np.random.default_rng(_seed(seed)), _patient_rows(codes, patients), []
    for _ in range(int(B)):
        value = stat(np.concatenate([rows[k] for k in rng.integers(0, patients, patients)]))
        if value is not None:
            values.append(value)
    return np.array(values)


def _percentile(values, level, B, seed):
    if len(values) < 2:
        return {"low": None, "high": None, "no_interval": "fewer than two resamples gave a value"}
    low, high = np.quantile(values, [(1 - level) / 2, (1 + level) / 2])
    return {"low": float(low), "high": float(high), "B": int(B), "B_used": int(len(values)), "seed": int(seed)}


def cells(y, positive) -> dict:
    """tp, fp, fn and tn of a binary index result (1 = positive) against the reference standard."""
    _need()
    y, t = _binary(y), _binary(positive, "positive")
    if len(t) != len(y):
        raise ValueError("y and positive must have one value per unit")
    return {"tp": int(((y == 1) & (t == 1)).sum()), "fp": int(((y == 0) & (t == 1)).sum()),
            "fn": int(((y == 1) & (t == 0)).sum()), "tn": int(((y == 0) & (t == 0)).sum())}


def _stated(prevalence, source):
    if prevalence is None:
        return None
    if not (isinstance(prevalence, numbers.Real) and 0 < prevalence < 1 and _text(source)):
        raise ValueError("prevalence must lie between 0 and 1 and come with prevalence_source: where it was "
                         "read (a paper and its table, a registry and its year)")
    return {"value": float(prevalence), "source": source.strip()}


def two_by_two(tp, fp, fn, tn, *, design, method="exact", level=0.95, prevalence=None, prevalence_source=None,
               patients=None) -> dict:
    """Sensitivity, specificity, PPV and NPV with exact (Clopper-Pearson) or Wilson intervals; LR+ and
    LR- with log-scale intervals. Predictive values come from the table only in a consecutive or
    cross-sectional sample; otherwise from Bayes' rule with a stated prevalence and its source, or
    not at all. An undefined measure has value None and a reason."""
    _need()
    from statsmodels.stats.proportion import proportion_confint
    counts = {"tp": tp, "fp": fp, "fn": fn, "tn": tn}
    if not all(isinstance(v, numbers.Integral) and not isinstance(v, bool) and v >= 0 for v in counts.values()):
        raise ValueError("tp, fp, fn and tn must be counts of units")
    if design not in DESIGNS:
        raise ValueError(f"design must be one of {', '.join(DESIGNS)}")
    if method not in ("exact", "wilson"):
        raise ValueError("method must be 'exact' (Clopper-Pearson) or 'wilson'")
    z, stated, measures = _z(level), _stated(prevalence, prevalence_source), {}

    def share(name, num, den, what):
        if den == 0:
            measures[name] = {"value": None, "reason": f"no {what}: the denominator is zero"}
            return
        low, high = proportion_confint(num, den, alpha=1 - level, method="beta" if method == "exact" else "wilson")
        measures[name] = {"value": num / den, "low": float(low), "high": float(high), "numerator": int(num),
                          "denominator": int(den), "method": "Clopper-Pearson" if method == "exact" else "Wilson"}

    def ratio(name, top, top_n, bottom, bottom_n):
        """(top / top_n) / (bottom / bottom_n) with the log-scale interval."""
        if top_n == 0 or bottom_n == 0 or bottom == 0:
            measures[name] = {"value": None, "reason": "undefined: " + ("a reference group is empty" if not
                              (top_n and bottom_n) else "its denominator proportion is zero, so the ratio is infinite")}
            return
        value = (top / top_n) / (bottom / bottom_n)
        if top == 0:
            measures[name] = {"value": value, "low": None, "high": None, "method": "log (Katz)",
                              "no_interval": "a zero cell: the log-scale interval is undefined"}
            return
        se = math.sqrt(1 / top - 1 / top_n + 1 / bottom - 1 / bottom_n)
        measures[name] = {"value": value, "low": value * math.exp(-z * se), "high": value * math.exp(z * se),
                          "se_log": se, "method": "log (Katz)"}

    share("sensitivity", tp, tp + fn, "reference-positive units")
    share("specificity", tn, tn + fp, "reference-negative units")
    ratio("lr_positive", tp, tp + fn, fp, fp + tn)
    ratio("lr_negative", fn, tp + fn, tn, fp + tn)
    if stated:
        prior = math.log(stated["value"] / (1 - stated["value"]))
        for name, lr, sign in (("ppv", measures["lr_positive"], 1), ("npv", measures["lr_negative"], -1)):
            if not lr.get("value") or lr.get("low") is None:
                measures[name] = {"value": None, "reason": "the likelihood ratio it needs has no value or no interval"}
                continue
            logit = sign * (math.log(lr["value"]) + prior)        # logit(NPV) = -(log LR- + logit(prevalence))
            ends = sorted(sign * (math.log(lr[k]) + prior) for k in ("low", "high"))
            measures[name] = {"value": 1 / (1 + math.exp(-logit)), "low": 1 / (1 + math.exp(-ends[0])),
                              "high": 1 / (1 + math.exp(-ends[1])), "prevalence": stated,
                              "method": "Bayes' rule from the likelihood ratio and the stated prevalence (logit interval)"}
    elif design in COHORT:
        share("ppv", tp, tp + fp, "positive index results")
        share("npv", tn, tn + fn, "negative index results")
    else:
        for name in ("ppv", "npv"):
            measures[name] = {"value": None, "reason": f"design {design}: the sampling fixed the share of positives, "
                              "so predictive values need the target population's prevalence with its source"}
    for m in measures.values():
        if m.get("value") is not None and m.get("low") is not None:
            m["level"] = level
    n = tp + fp + fn + tn
    return {"kind": "two_by_two", "design": design, "cells": counts, "level": level, "measures": measures,
            "sample_prevalence": (tp + fn) / n if n else None, "prevalence": stated,
            "units": n, "patients": patients or n, "positives": tp + fn}


def dev_cutoff(y, score) -> dict:
    """Youden's cut-off (the largest sensitivity + specificity - 1, units with score >= cut-off positive,
    the lowest such cut-off on a tie). Pass DEVELOPMENT data only: the result is labelled so."""
    _need()
    y = _binary(y)
    s = _scores(score, len(y))
    pos, neg, cuts = np.sort(s[y == 1]), np.sort(s[y == 0]), np.unique(s)
    if not len(pos) or not len(neg):
        raise ValueError("dev_cutoff needs positive and negative units")
    j = (len(pos) - np.searchsorted(pos, cuts)) / len(pos) + np.searchsorted(neg, cuts) / len(neg) - 1
    best = int(np.argmax(j))
    return {"value": float(cuts[best]), "source": "development", "rule": "Youden's J on the development data",
            "youden_j": float(j[best])}


def _logit_interval(theta, se, level):
    if not 0 < theta < 1 or not se > 0:
        return {"low": None, "high": None, "no_interval": "the AUC is 0 or 1, or has no variance: there is no "
                "logit-scale interval; report the counts"}
    centre, half = math.log(theta / (1 - theta)), _z(level) * se / (theta * (1 - theta))
    return {"low": 1 / (1 + math.exp(-(centre - half))), "high": 1 / (1 + math.exp(-(centre + half)))}


def auc(y, score, *, groups=None, level=0.95, B=2000, seed=None) -> dict:
    """The AUC with DeLong's standard error and an interval on the logit scale; when a patient has
    several units, the interval is a percentile bootstrap over patients (seed required)."""
    _need()
    y = _binary(y)
    s = _scores(score, len(y))
    codes, count = _counts(y, groups)
    m, n = count["positives"], count["units"] - count["positives"]
    if min(m, n) < 2:
        raise ValueError("an AUC interval needs at least two positive and two negative units")
    out = {"kind": "auc", "value": _auc_value(y, s), "level": level, **count}
    if count["patients"] == count["units"]:
        v10, v01 = _placements(s[y == 1], s[y == 0])
        se = math.sqrt(v10.var(ddof=1) / m + v01.var(ddof=1) / n)
        return {**out, "method": "DeLong, logit scale", "se": se, **_logit_interval(out["value"], se, level)}
    if seed is None:
        raise ValueError("units repeat within patients: the interval is a bootstrap by patient, which needs seed=")
    values = _bootstrap(lambda idx: _auc_value(y[idx], s[idx]), codes, count["patients"], B, seed)
    return {**out, "method": "bootstrap by patient, percentile", **_percentile(values, level, B, seed)}


def compare_auc(y, score_a, score_b, *, groups=None, level=0.95, B=2000, seed=None) -> dict:
    """AUC(a) - AUC(b) on the same units: DeLong's paired variance with a z test, or, when a patient has
    several units, a percentile bootstrap over patients (no p-value)."""
    _need()
    y = _binary(y)
    a, b = _scores(score_a, len(y), "score_a"), _scores(score_b, len(y), "score_b")
    codes, count = _counts(y, groups)
    m, n = count["positives"], count["units"] - count["positives"]
    if min(m, n) < 2:
        raise ValueError("comparing AUCs needs at least two positive and two negative units")
    auc_a, auc_b = _auc_value(y, a), _auc_value(y, b)
    out = {"kind": "auc_difference", "value": auc_a - auc_b, "auc_a": auc_a, "auc_b": auc_b, "level": level, **count}
    if count["patients"] < count["units"]:
        if seed is None:
            raise ValueError("units repeat within patients: the interval is a bootstrap by patient, which needs seed=")

        def diff(idx):
            first = _auc_value(y[idx], a[idx])
            return None if first is None else first - _auc_value(y[idx], b[idx])
        values = _bootstrap(diff, codes, count["patients"], B, seed)
        return {**out, "method": "bootstrap by patient, paired, percentile", **_percentile(values, level, B, seed)}
    a10, a01 = _placements(a[y == 1], a[y == 0])
    b10, b01 = _placements(b[y == 1], b[y == 0])
    s10, s01 = np.cov(np.vstack([a10, b10])), np.cov(np.vstack([a01, b01]))
    var = (s10[0, 0] + s10[1, 1] - 2 * s10[0, 1]) / m + (s01[0, 0] + s01[1, 1] - 2 * s01[0, 1]) / n
    se = math.sqrt(max(float(var), 0.0))
    out.update(method="DeLong, paired", se=se)
    if se == 0:
        return {**out, "low": None, "high": None, "no_interval": "the two scores rank the units alike: no variance"}
    z = out["value"] / se
    return {**out, "low": out["value"] - _z(level) * se, "high": out["value"] + _z(level) * se, "z": z,
            "p": float(2 * stats.norm.sf(abs(z)))}


def _newcombe_paired(both, only_a, only_b, neither, level):
    """Newcombe's hybrid score interval for a paired difference p_a - p_b (his method 10): Wilson
    intervals of the two margins, combined with the phi correlation of the paired table."""
    from statsmodels.stats.proportion import proportion_confint
    n = both + only_a + only_b + neither
    p1, p2 = (both + only_a) / n, (both + only_b) / n
    l1, u1 = proportion_confint(both + only_a, n, alpha=1 - level, method="wilson")
    l2, u2 = proportion_confint(both + only_b, n, alpha=1 - level, method="wilson")
    margins = (both + only_a) * (only_b + neither) * (both + only_b) * (only_a + neither)
    phi = (both * neither - only_a * only_b) / math.sqrt(margins) if margins else 0.0
    down = (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2
    up = (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2
    return p1 - p2 - math.sqrt(max(down, 0.0)), p1 - p2 + math.sqrt(max(up, 0.0))


def mcnemar_pair(y, test_a, test_b, *, among=1, groups=None, level=0.95) -> dict:
    """Two binary index tests on the same units. among=1 compares sensitivities (reference-positive
    units), among=0 specificities. Exact McNemar p from the discordant pairs; Newcombe's interval."""
    _need()
    from statsmodels.stats.contingency_tables import mcnemar
    y, a, b = _binary(y), _binary(test_a, "test_a"), _binary(test_b, "test_b")
    if among not in (0, 1) or not len(a) == len(b) == len(y):
        raise ValueError("among is 1 (sensitivity) or 0 (specificity); y, test_a and test_b have one value per unit")
    codes, count = _counts(y, groups)
    if count["patients"] < count["units"]:
        raise ValueError("a patient has several units: McNemar's test needs independent pairs; use one unit per "
                         "patient, or a clustered method outside this skill")
    keep = y == among
    right_a, right_b = a[keep] == among, b[keep] == among
    table = {"both": int((right_a & right_b).sum()), "only_a": int((right_a & ~right_b).sum()),
             "only_b": int((~right_a & right_b).sum()), "neither": int((~right_a & ~right_b).sum())}
    total = sum(table.values())
    if total == 0:
        raise ValueError(f"no unit has reference value {among}")
    low, high = _newcombe_paired(*table.values(), level)
    p = float(mcnemar([[table["both"], table["only_a"]], [table["only_b"], table["neither"]]], exact=True).pvalue)
    return {"kind": "paired_difference", "measure": "sensitivity" if among == 1 else "specificity",
            "value": (table["only_a"] - table["only_b"]) / total, "low": low, "high": high, "level": level,
            "p": p, "table": table, "method": "Newcombe, paired (method 10)", "test": "McNemar, exact", **count}


def calibration(y, p, *, groups=None, level=0.95, bins=10, frac=2 / 3) -> dict:
    """Calibration of predicted risks: the intercept of a logistic model with logit(p) as offset
    (calibration-in-the-large), the slope on logit(p), Wald intervals (cluster-robust by patient when
    a patient has several units), a lowess curve, observed against predicted in tenths of risk, Brier."""
    _need()
    import statsmodels.api as sm
    from statsmodels.nonparametric.smoothers_lowess import lowess
    y = _binary(y)
    p = _scores(p, len(y), "p")
    if ((p <= 0) | (p >= 1)).any():
        raise ValueError("predicted risks must lie strictly between 0 and 1: logit(p) is infinite at 0 and 1")
    codes, count = _counts(y, groups)
    clustered = count["patients"] < count["units"]
    options = {"cov_type": "cluster", "cov_kwds": {"groups": codes}} if clustered else {}
    lp = np.log(p / (1 - p))
    family = sm.families.Binomial()
    citl = sm.GLM(y, np.ones((len(y), 1)), family=family, offset=lp).fit(**options)
    slope = sm.GLM(y, sm.add_constant(lp, has_constant="add"), family=family).fit(**options)
    ci_i, ci_s = citl.conf_int(alpha=1 - level)[0], slope.conf_int(alpha=1 - level)[1]
    curve = lowess(y, p, frac=frac, it=0)
    tenths = [{"mean_predicted": float(p[g].mean()), "observed": float(y[g].mean()), "units": int(len(g))}
              for g in np.array_split(np.argsort(p, kind="stable"), bins) if len(g)]
    return {"kind": "calibration", "level": level, **count,
            "intercept": {"value": float(citl.params[0]), "low": float(ci_i[0]), "high": float(ci_i[1]), "level": level},
            "slope": {"value": float(slope.params[1]), "low": float(ci_s[0]), "high": float(ci_s[1]), "level": level},
            "brier": float(((y - p) ** 2).mean()), "mean_predicted": float(p.mean()), "observed_rate": float(y.mean()),
            "method": "intercept: logistic model with logit(p) as offset; slope: logistic regression on logit(p); "
                      "Wald intervals" + (", cluster-robust by patient" if clustered else ""),
            "curve_method": f"lowess, frac {frac:.3g}, no robustness iterations",
            "curve": {"x": curve[:, 0].tolist(), "y": curve[:, 1].tolist()}, "tenths": tenths}


def net_benefit(y, p, thresholds, *, design, prevalence=None, prevalence_source=None, groups=None) -> dict:
    """Net benefit of treating units with p >= pt at each planned threshold pt: sens * prev - (1 - spec)
    * (1 - prev) * pt / (1 - pt), with treat-all and treat-none. prev is the sample's in a consecutive
    or cross-sectional design; otherwise a stated prevalence with its source is required."""
    _need()
    y = _binary(y)
    p = _scores(p, len(y), "p")
    t = np.asarray(thresholds, dtype=float)
    if t.ndim != 1 or not len(t) or not ((t > 0) & (t < 1)).all() or (np.diff(t) <= 0).any():
        raise ValueError("thresholds are the planned threshold probabilities: increasing, each between 0 and 1")
    if design not in DESIGNS:
        raise ValueError(f"design must be one of {', '.join(DESIGNS)}")
    stated = _stated(prevalence, prevalence_source)
    if stated is None and design not in COHORT:
        raise ValueError(f"design {design}: the sample prevalence is set by the sampling; net benefit needs the "
                         "target population's prevalence with prevalence_source")
    _, count = _counts(y, groups)
    m, n0 = count["positives"], count["units"] - count["positives"]
    if not m or not n0:
        raise ValueError("net benefit needs positive and negative units")
    prev = stated["value"] if stated else m / len(y)
    odds = t / (1 - t)
    treated = p[:, None] >= t[None, :]
    tpr, fpr = (treated & (y[:, None] == 1)).sum(0) / m, (treated & (y[:, None] == 0)).sum(0) / n0
    return {"kind": "net_benefit", "design": design, **count, "thresholds": t.tolist(),
            "model": (tpr * prev - fpr * (1 - prev) * odds).tolist(), "treat_all": (prev - (1 - prev) * odds).tolist(),
            "treat_none": [0.0] * len(t), "prevalence": stated or {"value": prev, "source": "the sample"}}


def _rows(X, idx):
    return X.iloc[idx].reset_index(drop=True) if hasattr(X, "iloc") else np.asarray(X)[idx]


def _risks(predict, X, n):
    risk = np.asarray(predict(X), dtype=float).reshape(-1)
    if risk.shape != (n,) or not np.isfinite(risk).all() or (risk < 0).any() or (risk > 1).any():
        raise ValueError("predict(X) must return one risk between 0 and 1 for each row of X")
    return risk


def _metrics(y, p):
    import statsmodels.api as sm
    q = np.clip(p, EPS, 1 - EPS)
    lp, family = np.log(q / (1 - q)), sm.families.Binomial()
    out = {"auc": _auc_value(y, p), "brier": float(((y - p) ** 2).mean()), "slope": None, "intercept": None}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            out["slope"] = float(sm.GLM(y, sm.add_constant(lp, has_constant="add"), family=family).fit().params[1])
            out["intercept"] = float(sm.GLM(y, np.ones((len(y), 1)), family=family, offset=lp).fit().params[0])
        except (ValueError, np.linalg.LinAlgError):
            pass
    return out


def _setup(pipeline, X, y, groups):
    _need()
    if not callable(pipeline):
        raise ValueError("pipeline must be a function pipeline(X, y) -> predict")
    y = _binary(y)
    if len(X) != len(y):
        raise ValueError("X and y must have one row per unit")
    codes, count = _counts(y, groups)
    return y, (np.arange(len(y)) if codes is None else codes), count


def optimism(pipeline, X, y, *, groups=None, B=200, seed) -> dict:
    """Harrell's bootstrap: apparent performance of the pipeline fitted to all data; on each of B
    resamples of patients, the pipeline is fitted again (every step), scored on the resample and on
    the original data; the mean difference is the optimism, subtracted from the apparent value."""
    y, codes, count = _setup(pipeline, X, y, groups)
    apparent = _metrics(y, _risks(pipeline(X, y), X, len(y)))
    rng, rows = np.random.default_rng(_seed(seed)), _patient_rows(codes, count["patients"])
    diffs, failures = {k: [] for k in METRICS}, []
    for _ in range(int(B)):
        idx = np.concatenate([rows[k] for k in rng.integers(0, count["patients"], count["patients"])])
        if y[idx].min() == y[idx].max():
            failures.append("a resample held one outcome class only")
            continue
        try:
            predict = pipeline(_rows(X, idx), y[idx])
            boot = _metrics(y[idx], _risks(predict, _rows(X, idx), len(idx)))
            orig = _metrics(y, _risks(predict, X, len(y)))
        except Exception as exc:          # a resample the pipeline cannot fit is counted, not hidden
            failures.append(f"{type(exc).__name__}: {exc}")
            continue
        for k in METRICS:
            if boot[k] is not None and orig[k] is not None:
                diffs[k].append(boot[k] - orig[k])
    metrics = {}
    for k in METRICS:
        if apparent[k] is not None and diffs[k]:
            gap = float(np.mean(diffs[k]))
            metrics[k] = {"apparent": apparent[k], "optimism": gap, "corrected": apparent[k] - gap}
    if "auc" not in metrics:
        raise ValueError("no resample gave an AUC: " + "; ".join(sorted(set(failures))[:3]))
    return {"kind": "optimism", "value": metrics["auc"]["corrected"], "metrics": metrics, "B": int(B),
            "B_used": int(B) - len(failures), "failures": len(failures), "failure_examples": sorted(set(failures))[:3],
            "seed": int(seed), "resampled": "patients" if count["patients"] < count["units"] else "units", **count}


def null_label_check(pipeline, X, y, *, groups=None, R=10, folds=5, seed, z=3.0) -> dict:
    """R times: permute the outcome, run the pipeline in a cross-validation grouped by patient, and
    score the out-of-fold risks against the permuted and against the true outcome. Both mean AUCs
    should be near 0.5; status is problem when either exceeds 0.5 + z * sd0 / sqrt(R), sd0 being the
    null standard deviation of an AUC, sqrt((m + n + 1) / (12 m n))."""
    y, codes, count = _setup(pipeline, X, y, groups)
    rng = np.random.default_rng(_seed(seed))
    if not 2 <= folds <= count["patients"]:
        raise ValueError("folds must lie between 2 and the number of patients")
    permuted, true, failures = [], [], []
    for _ in range(int(R)):
        labels, fold = rng.permutation(y), (rng.permutation(count["patients"]) % folds)[codes]
        risk = np.empty(len(y))
        try:
            for k in range(folds):
                train, held = np.flatnonzero(fold != k), np.flatnonzero(fold == k)
                if labels[train].min() == labels[train].max():
                    raise ValueError("a training fold held one outcome class only")
                risk[held] = _risks(pipeline(_rows(X, train), labels[train]), _rows(X, held), len(held))
        except Exception as exc:
            failures.append(f"{type(exc).__name__}: {exc}")
            continue
        permuted.append(_auc_value(labels, risk))
        true.append(_auc_value(y, risk))
    m, n = count["positives"], count["units"] - count["positives"]
    out = {"kind": "null_label", "R": int(R), "R_used": len(permuted), "folds": int(folds), "seed": int(seed),
           "failures": len(failures), "failure_examples": sorted(set(failures))[:3], **count}
    if not permuted:
        return {**out, "value": None, "status": "not_checked", "reason": "no repetition ran: " + "; ".join(out["failure_examples"])}
    margin = z * math.sqrt((m + n + 1) / (12 * m * n)) / math.sqrt(len(permuted))
    mean_p, mean_t = float(np.mean(permuted)), float(np.mean(true))
    reasons = ([f"the out-of-fold AUC on permuted outcomes averages {mean_p:.3f}: a step sees held-out rows"]
               if mean_p > 0.5 + margin else [])
    reasons += ([f"risks from a pipeline fitted to permuted outcomes predict the true outcome (AUC {mean_t:.3f}): it "
                 "learns from something other than its arguments, such as a model or a selection fitted outside it"]
                if mean_t > 0.5 + margin else [])
    return {**out, "value": mean_p, "range": [min(permuted), max(permuted)], "against_true_labels": mean_t,
            "margin": margin, "rule": f"problem above 0.5 + {z:g} x sd0 / sqrt(R)",
            "status": "problem" if reasons else "ok", "reason": "; ".join(reasons) or "both means within the margin"}


def _canvas(width_mm, height_mm):
    """rz_figure.py (the copy next to this file), a styled figure and its axes."""
    _need()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import rz_figure
    rz_figure.apply_style()
    return (rz_figure, *plt.subplots(figsize=rz_figure.figsize_mm(width_mm, height_mm)))


def _save(rf, fig, name, data, out, script):
    script = script or getattr(sys.modules.get("__main__"), "__file__", None)
    return rf.save(fig, name, data=data, out=out, script=script if script and Path(script).is_file() else None,
                   quiet=True)["outputs"][0]["path"]


def roc_figure(name, *, data, curves, out="diagnostic-accuracy/figures", width_mm=89, script=None) -> str:
    """curves: [(label, y, score, auc_result)]. Empirical ROC curves, the AUC and its interval in the
    legend. Returns the PDF path for record(figure=...)."""
    rf, fig, ax = _canvas(width_mm, width_mm)
    for i, (label, y, score, res) in enumerate(curves):
        y = _binary(y)
        s = _scores(score, len(y))
        order = np.argsort(-s, kind="mergesort")
        last = np.r_[np.flatnonzero(np.diff(s[order])), len(y) - 1]
        tp = np.cumsum(y[order])[last]
        shown = f"{label}: AUC {res['value']:.2f}" + (f" ({res['low']:.2f} to {res['high']:.2f})"
                                                       if res.get("low") is not None else "")
        style = rf.series_style(i)
        ax.plot(np.r_[0, (last + 1 - tp) / (len(y) - y.sum())], np.r_[0, tp / y.sum()], color=style["color"],
                linestyle=style["linestyle"], label=shown)
    ax.plot([0, 1], [0, 1], color="0.6", linewidth=0.6)
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="1 − specificity", ylabel="Sensitivity")
    ax.legend(loc="lower right")
    return _save(rf, fig, name, data, out, script)


def calibration_figure(name, *, data, cal, out="diagnostic-accuracy/figures", width_mm=89, script=None) -> str:
    """The lowess curve and the tenths of risk of a calibration() result, with the diagonal."""
    rf, fig, ax = _canvas(width_mm, width_mm)
    top = min(1.0, max(*cal["curve"]["x"], *cal["curve"]["y"], *(g["observed"] for g in cal["tenths"]), 0.05) * 1.05)
    ax.plot([0, top], [0, top], color="0.6", linewidth=0.6)
    ax.plot(cal["curve"]["x"], cal["curve"]["y"], color=rf.PALETTE["blue"], label=cal["curve_method"])
    ax.plot([g["mean_predicted"] for g in cal["tenths"]], [g["observed"] for g in cal["tenths"]], linestyle="none",
            marker="o", color=rf.PALETTE["black"], label="tenths of predicted risk")
    ax.set(xlim=(0, top), ylim=(0, top), xlabel="Predicted risk", ylabel="Observed proportion")
    ax.legend(loc="upper left")
    return _save(rf, fig, name, data, out, script)


def decision_figure(name, *, data, nb, out="diagnostic-accuracy/figures", width_mm=89, script=None) -> str:
    """Net benefit of the model, treat-all and treat-none over the planned thresholds."""
    rf, fig, ax = _canvas(width_mm, 70)
    for i, (key, label) in enumerate((("model", "Model"), ("treat_all", "Treat all"), ("treat_none", "Treat none"))):
        style = rf.series_style(i)
        ax.plot(nb["thresholds"], nb[key], color=style["color"], linestyle=style["linestyle"], label=label)
    top = max(max(nb["model"]), max(nb["treat_all"]), 0.01)
    ax.set(xlim=(nb["thresholds"][0], nb["thresholds"][-1]), ylim=(-0.1 * top, 1.1 * top),
           xlabel="Threshold probability", ylabel="Net benefit")
    ax.legend(loc="upper right")
    return _save(rf, fig, name, data, out, script)


def _leakage(probe):
    try:
        content = json.loads(Path(probe).read_text(encoding="utf-8"))
        return {"status": content["leakage"]["status"], "probe": str(probe), "data_sha256": content["file"]["sha256"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"could not read the probe {probe}: {exc}") from exc


def _threshold(threshold):
    if threshold is None:
        return None
    if not (isinstance(threshold, dict) and isinstance(threshold.get("value"), numbers.Real)):
        raise ValueError("threshold must be {'value': cut-off, 'source': 'plan' | 'development' | 'published'}")
    if threshold.get("source") not in SOURCES:
        raise ValueError(f"a cut-off from {threshold.get('source')!r} is refused: it comes from the plan, the "
                         "development data (dev_cutoff) or a published source with its citation, never the test data")
    if threshold["source"] == "published" and not _text(threshold.get("citation")):
        raise ValueError("a published cut-off needs its citation")
    return dict(threshold)


def record(result, *, id, question, dataset, model=None, models=None, design=None, family=None, role="primary",
           threshold=None, probe=None, no_calibration=None, figure=None, at=None, measures=None, notes="",
           kept=True, reason=None) -> list:
    """Record a result of this module through rz_results.record(), with the accuracy fields in
    extra["accuracy"]: kind, model, dataset, design, units, patients, positives, threshold and its
    source, the probe's leakage status, and the kind's own numbers. A 2x2 table gives one record per
    measure that has a value (<id>.sensitivity, ...); `measures` picks some, and asking for one that
    has no value raises its reason. A comparison names models=(first, second); a net benefit names
    `at`, the planned thresholds the text will print. A test-set result needs probe= a probe whose
    leakage status is ok. Returns the recorded entries."""
    rz = sys.modules.get("rz_results") or importlib.import_module("rz_results")

    def refuse(message):
        raise ValueError(f"rz_accuracy.record({id!r}): {message}")

    kind = result.get("kind") if isinstance(result, dict) else None
    if kind not in KINDS:
        refuse("result must be a dict returned by a function of rz_accuracy")
    if kind in ("auc_difference", "paired_difference"):
        if not (isinstance(models, (list, tuple)) and len(models) == 2 and all(_text(m) for m in models)):
            refuse("a comparison needs models=(first, second), in the order of the difference")
        model = model or f"{models[0]} vs {models[1]}"
    if not _text(model):
        refuse("model must name the model or index test")
    if dataset not in DATASETS:
        refuse(f"dataset must be one of {', '.join(DATASETS)}")
    design = result.get("design") or design
    if design not in DESIGNS:
        refuse(f"design must be one of {', '.join(DESIGNS)}")
    try:
        threshold = _threshold(threshold)
        leakage = _leakage(probe) if probe else None
    except ValueError as exc:
        refuse(str(exc))
    if dataset == "test" and (leakage or {}).get("status") != "ok":
        refuse("no test-set result before the probe's leakage status is ok: run probe_accuracy.py on the file that "
               "holds both splits, settle its problems, and pass probe=<its .probe.json>")
    base = {"kind": kind, "model": model, "dataset": dataset, "design": design, "units": result["units"],
            "patients": result["patients"], "positives": result["positives"], "threshold": threshold, "leakage": leakage}
    base.update({k: v for k, v in (("no_calibration", no_calibration), ("figure", figure), ("models", models and
                                   list(models))) if v})
    n = {"patients": int(result["patients"])}
    if result["units"] != result["patients"]:
        n["units"] = int(result["units"])
    common = {"question": question, "family": family or id, "role": role, "unit": "patient", "n": n, "notes": notes,
              "kept": kept, "reason": reason}

    def interval(r, level):
        return {"low": r["low"], "high": r["high"], "level": level} if r.get("low") is not None else None

    if kind == "two_by_two":
        wanted = list(measures or result["measures"])
        if set(wanted) - set(NAMES):
            refuse(f"measures are named {', '.join(NAMES)}")
        missing = {k: result["measures"][k]["reason"] for k in wanted if result["measures"].get(k, {}).get("value") is None}
        if measures and missing:
            refuse("; ".join(f"{k}: {v}" for k, v in missing.items()))
        skipped = {k: m["reason"] for k, m in result["measures"].items() if m.get("value") is None}
        entries = []
        for name in wanted:
            m = result["measures"][name]
            if m.get("value") is None:
                continue
            fields = {k: m[k] for k in ("numerator", "denominator", "method", "no_interval", "prevalence") if k in m}
            entries.append(rz.record(
                id=f"{id}.{name}", test=f"{NAMES[name]}, {m['method']}", interval=interval(m, result["level"]),
                estimate={"name": NAMES[name], "value": m["value"], "units": "ratio" if name.startswith("lr") else "proportion"},
                extra={"accuracy": {**base, "measure": name, **fields, "cells": result["cells"],
                                    "sample_prevalence": result["sample_prevalence"], "not_recorded": skipped}}, **common))
        return entries
    if kind == "auc":
        fields = {k: result[k] for k in ("method", "se", "B", "B_used", "seed", "no_interval") if k in result}
        return [rz.record(id=id, test=f"AUC, {result['method']}", interval=interval(result, result["level"]),
                          estimate={"name": "AUC", "value": result["value"], "units": "unitless"},
                          extra={"accuracy": {**base, **fields}}, **common)]
    if kind in ("auc_difference", "paired_difference"):
        what = "AUC" if kind == "auc_difference" else result["measure"]
        fields = {k: result[k] for k in ("method", "se", "B", "B_used", "seed", "no_interval", "measure", "table", "test")
                  if k in result}
        if kind == "auc_difference":
            fields["auc"] = {models[0]: result["auc_a"], models[1]: result["auc_b"]}
        tested = {"p": result["p"], "effect_size": "estimate"} if result.get("p") is not None else {}
        if result.get("z") is not None:
            tested["statistic"] = {"name": "z", "value": result["z"]}
        return [rz.record(id=id, test=f"difference in {what}, {result['method']}", interval=interval(result, result["level"]),
                          estimate={"name": f"difference in {what}, {models[0]} minus {models[1]}",
                                    "value": result["value"], "units": "unitless" if what == "AUC" else "proportion"},
                          extra={"accuracy": {**base, **fields}}, **tested, **common)]
    if kind == "calibration":
        fields = {k: result[k] for k in ("intercept", "slope", "brier", "mean_predicted", "observed_rate", "method",
                                         "curve_method")}
        return [rz.record(id=id, test="calibration intercept and slope", interval=interval(result["slope"], result["level"]),
                          estimate={"name": "calibration slope", "value": result["slope"]["value"], "units": "unitless"},
                          extra={"accuracy": {**base, **fields}}, **common)]
    if kind == "net_benefit":
        at = [result["thresholds"][0]] if at is None else list(at)
        rows = []
        for t in at:
            hit = [i for i, v in enumerate(result["thresholds"]) if abs(v - t) < 1e-9]
            if not hit:
                refuse(f"at={t} is not one of the planned thresholds")
            rows.append({"threshold": t, "model": result["model"][hit[0]], "treat_all": result["treat_all"][hit[0]]})
        t = result["thresholds"]
        return [rz.record(id=id, test="net benefit (decision curve)",
                          estimate={"name": f"net benefit at threshold {at[0]:g}", "value": rows[0]["model"],
                                    "units": "net true positives per patient"},
                          extra={"accuracy": {**base, "thresholds": {"from": t[0], "to": t[-1], "count": len(t)},
                                              "at": rows, "prevalence": result["prevalence"]}}, **common)]
    fields = {k: result[k] for k in ("metrics", "B", "B_used", "failures", "seed", "resampled", "status", "reason",
                                     "against_true_labels", "range", "R", "R_used", "folds", "margin", "rule") if k in result}
    if result.get("value") is None:
        refuse(f"the null-label check did not run: {result.get('reason')}")
    name = "optimism-corrected AUC" if kind == "optimism" else "mean out-of-fold AUC, permuted outcome"
    return [rz.record(id=id, test="bootstrap optimism (Harrell)" if kind == "optimism" else "null-label check",
                      estimate={"name": name, "value": result["value"], "units": "unitless"},
                      extra={"accuracy": {**base, **fields}}, **common)]
