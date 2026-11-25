#!/usr/bin/env python3
"""Survival analysis for the analysis script of researchzy-survival: statsmodels, with its defaults made explicit.

Imported by the analysis script next to rz_results; no commands. The script (references/km-logrank-cox.md) calls
rs.prepare() on the rows, runs the analyses, and records each with rz.record(id=..., **rs.fields(result)).

  prepare(frame, ...)          the rows the analysis uses; event codes 0 (censored), 1 (the event), 2.. (competing)
  km_table(data, group, ...)   Kaplan-Meier per group: pointwise band, number at risk, median, reverse-KM follow-up
  logrank(data, group, ...)    survdiff, with df = groups - 1 and the weights named
  cox(data, covariates, ...)   PHReg, ties="efron" and missing="raise" after an explicit filter; HR per parameter
  ph_test(cox, model, ...)     Grambsch-Therneau test per parameter and global, and the scaled-residual plot
  rmst(data, group, tau, ...)  restricted mean survival time per group and differences; tau within follow-up
  cif(data, cause, times, ...) Aalen-Johansen cumulative incidence with competing events
  schoenfeld_events(hr, ...)   events needed to compare two groups (standard library only)
  km_figure(km, name)          curves and number-at-risk table from km_table(), saved through rz_figure
  fields(result, ...)          the keyword arguments of rz_results.record() for one result, extra={"survival": ...}

statsmodels defaults replaced here: the status is a weight, so codes are mapped to 0/1 first (a 1/2 coding gives
wrong estimates without a warning); PHReg's Breslow ties become Efron and its silent dropping of incomplete rows a
recorded filter; an unreached median (NaN, or an infinite upper bound) becomes "not_reached"; the missing
proportional-hazards test is computed here. PHReg counts a row as at risk at its own entry time, so entry times move
forward by 1e-9 of the longest time: the Cox model, like the Kaplan-Meier estimate, then counts entry < t <= exit.
Row n is the n-th data row under the header (index n - 1 of read_csv), as in the probe. Bad input raises ValueError.
Needs numpy, pandas, scipy and statsmodels; figures need matplotlib and rz_figure.py; schoenfeld_events() needs none.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from statistics import NormalDist

try:
    import numpy as np
    from scipy import stats
    from statsmodels.duration.hazard_regression import PHReg
    from statsmodels.duration.survfunc import CumIncidenceRight, SurvfuncRight, survdiff
except ImportError:               # schoenfeld_events() works without them
    np = stats = PHReg = CumIncidenceRight = SurvfuncRight = survdiff = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

__version__ = "1.0.0"
OUT = "survival"
MISSING = frozenset({"", "na", "n/a", "nan", "null", "none", "#n/a", "."})
CONTEXT = ("time_unit", "time_zero", "subject", "event_mapping", "entry", "excluded")
BAND = "pointwise, log(-log) transform of the Greenwood standard error"
MEDIAN = ("first time the curve falls below 0.5; interval of Brookmeyer and Crowley: the event times where a z test of "
          "S(t) = 0.5 on the log(-log) scale is not rejected (statsmodels quantile_ci, method cloglog)")
FOLLOWUP = "reverse Kaplan-Meier: censoring counted as the event and events as censoring"
FILTER = "rows with a missing value in a model column are listed and left out; PHReg then runs with missing='raise'"
PH_METHOD = ("Grambsch-Therneau, 1994 approximation: Schoenfeld residuals r of d events, covariance V, centred time g, "
             "u = sum g r; per parameter d (uV)_j^2 / (V_jj sum g^2) on 1 df, global d u'Vu / sum g^2 on p df")
TIED = ("tied event times: statsmodels' Schoenfeld residuals use the full risk-set mean at a tied time, not Efron's, "
        "so the test can differ slightly from programs that adjust it")
TRANSFORMS = {"km": ("1 - Kaplan-Meier estimate of all rows of the model, just after the event time", "1 - KM(t)"),
              "rank": ("rank among the event times, ties given their average rank", "Rank of event time"),
              "identity": ("the event time", "Time ({unit})"), "log": ("log of the event time", "Log time ({unit})")}
WEIGHTS = {None: "log-rank (every event time weighted equally)", "gb": "Gehan-Breslow (number at risk)",
           "tw": "Tarone-Ware (square root of the number at risk)", "fh": "Fleming-Harrington (S(t-) to the power p)"}
CIF = "Aalen-Johansen (statsmodels CumIncidenceRight); pointwise interval, log(-log) scale, delta-method standard error"
RMST = "area under the Kaplan-Meier curve up to tau; variance sum A_j^2 d_j / (n_j (n_j - d_j)), A_j the area from t_j"


def _code(value) -> str:
    """A code, level or number as written, with "2.0" and "2" the same; "" when missing."""
    text = "" if value is None or (isinstance(value, float) and math.isnan(value)) else str(value).strip()
    if text.lower() in MISSING:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else text


def _number(value):
    """A finite float, or why there is none: "missing" or "not a number"."""
    text = _code(value)
    try:
        number = float(text) if text else None
    except ValueError:
        return "not a number"
    return "missing" if number is None else number if math.isfinite(number) else "not a number"


def _levels(values) -> list:
    found = sorted({v for v in values if v})
    try:
        return sorted(found, key=float)
    except ValueError:
        return found


def _bound(value, estimate):          # "not_estimable": no bound although the estimate exists
    if np.isfinite(value):
        return float(value)
    return "not_reached" if np.isinf(value) or not np.isfinite(estimate) else "not_estimable"


def _context(ctx, excluded) -> dict:
    return {**{k: ctx[k] for k in CONTEXT[:-1]}, "excluded": ctx["excluded"] + excluded}


def _n(data, mask) -> int:            # subjects: distinct ids when there is an id column
    column = data["context"]["id"]
    return int(len(set(data["frame"][column].to_numpy()[mask]))) if column else int(mask.sum())


def prepare(frame, *, time, event, mapping, time_unit, time_zero, subject="patient", entry=None, id=None,
            drop=None, source=None) -> dict:
    """Check and convert the rows the analysis uses; returns {"frame", "context"}.

    mapping    {code as written: 0 censored, 1 the event, 2, 3 ... competing events}, as the user confirmed it
    time_unit, time_zero, subject   the unit the user named, the plan's own words, what one unit of analysis is
    entry, id  entry times of start-stop rows (entry < time); the subject id, repeated only on start-stop rows
    drop       {row: reason} for rows the user decided to leave out; source: the data file, for figure records
    A code outside the mapping, a missing, non-numeric or negative time, a bad entry time or a repeated id raises
    ValueError naming the rows."""
    if SurvfuncRight is None:
        raise ImportError("rz_survival needs numpy, pandas, scipy and statsmodels; ask the user before installing them")
    absent = [c for c in (time, event, entry, id) if c is not None and c not in frame.columns]
    if absent:
        raise ValueError(f"no column {', '.join(map(repr, absent))}; columns: {', '.join(map(str, frame.columns))}")
    codes = {_code(k): v for k, v in dict(mapping).items()}
    if "" in codes or 1 not in codes.values() or not all(type(v) is int and v >= 0 for v in codes.values()):
        raise ValueError("mapping gives each event code as written 0 (censored), 1 (the event) or 2, 3 ... (competing "
                         "events), and at least one code is 1")
    for name, value in (("time_unit", time_unit), ("time_zero", time_zero), ("subject", subject)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required: it comes from the user or the plan, never from the numbers")
    rows = [int(i) + 1 for i in frame.index]
    drop = {int(k): str(v).strip() for k, v in (drop or {}).items()}
    if set(drop) - set(rows) or not all(drop.values()):
        raise ValueError(f"drop takes {{row: reason}} for rows of the data, each with a reason; not rows: "
                         f"{sorted(set(drop) - set(rows))}")
    problems, keep, parsed = {}, [], []
    entries = frame[entry] if entry else [None] * len(frame)
    for position, (row, t, e, s) in enumerate(zip(rows, frame[time], frame[event], entries)):
        if row in drop:
            continue
        found, t, s = [], _number(t), _number(s) if entry else 0.0
        if _code(e) not in codes:
            found.append(f"event code {_code(e) or '(missing)'!r} is not in the mapping")
        if isinstance(t, str) or t < 0:
            found.append(f"time is {t if isinstance(t, str) else 'negative'}")
        if entry and (isinstance(s, str) or s < 0 or (not isinstance(t, str) and s >= t)):
            found.append("the entry time is missing, negative or not before the exit time")
        for message in found:
            problems.setdefault(message, []).append(row)
        if not found:
            keep.append(position)
            parsed.append((t, codes[_code(e)], s, row))
    spans = {}
    for position, (t, _, s, row) in zip(keep, parsed) if id else ():
        spans.setdefault(_code(frame[id].iloc[position]), []).append((s, t, row))
    for key, items in spans.items():
        items.sort()
        bad = ("the id is missing" if not key else "the id repeats (duplicates, or start-stop rows that need entry=)"
               if len(items) > 1 and not entry else "the intervals of one id overlap"
               if any(b[0] < a[1] for a, b in zip(items, items[1:])) else None)
        if bad:
            problems.setdefault(bad, []).extend(r for _, _, r in items)
    if problems:
        raise ValueError("; ".join(f"{m} (rows {', '.join(map(str, sorted(r)[:10]))}{' ...' if len(r) > 10 else ''})"
                                   for m, r in problems.items())
                         + ". Decide with the user, then correct the mapping or list the rows in drop={row: reason}")
    out = frame.iloc[keep].copy()
    out["_time"], out["_event"], out["_row"] = [p[0] for p in parsed], [p[1] for p in parsed], [p[3] for p in parsed]
    if entry:
        out["_entry"] = [p[2] for p in parsed]
    ctx = {"time_unit": time_unit.strip(), "time_zero": time_zero.strip(), "subject": subject.strip(),
           "event_mapping": codes, "entry": entry, "excluded": [{"row": r, "reason": drop[r]} for r in sorted(drop)],
           "id": id, "source": source, "competing": sorted({p[1] for p in parsed if p[1] >= 2})}
    return {"frame": out, "context": ctx}


def _split(data, group=None, others=()) -> tuple:
    """[(level, mask)] of group (one "all" set without it), the codes of each column, the rows left out for a
    missing value with the reason, and the mask of rows kept."""
    frame, columns = data["frame"], [c for c in (group, *others) if c]
    absent = [c for c in columns if c not in frame.columns]
    if absent:
        raise ValueError(f"no column {', '.join(map(repr, absent))}")
    codes = {c: np.array([_code(v) for v in frame[c]], dtype=object) for c in columns}
    keep, excluded = np.ones(len(frame), bool), []
    for i, row in enumerate(frame["_row"]):
        gone = [c for c in columns if not codes[c][i]]
        if gone:
            keep[i] = False
            excluded.append({"row": int(row), "reason": "missing " + ", ".join(gone)})
    sets = [(lvl, keep & (codes[group] == lvl)) for lvl in _levels(codes[group][keep])] if group else [("all", keep)]
    return sets, codes, excluded, keep


def _arrays(data) -> tuple:
    """Time, status (code 1; competing codes count as censored), the codes, and entry times or None."""
    frame = data["frame"]
    events = frame["_event"].to_numpy(int)
    return frame["_time"].to_numpy(float), (events == 1).astype(float), events, (
        frame["_entry"].to_numpy(float) if "_entry" in frame else None)


def _one_cause(data, what, entry=True):
    """Refuse competing events (and entry times when entry is False) for an estimate of code 1 alone."""
    if data["context"]["competing"]:
        raise ValueError(f"the data hold competing events: {what} of code 1 alone overstates its incidence. Use cif(), "
                         "or prepare the data again with every event code mapped to 1 (survival free of any event)")
    if data["context"]["entry"] and not entry:
        raise ValueError(f"{what} here needs data without entry times")


def _band(prob, se, z) -> tuple:
    with np.errstate(divide="ignore", invalid="ignore"):
        w = z * se / (prob * np.abs(np.log(prob)))
        low, high = prob ** np.exp(w), prob ** np.exp(-w)
    ok = (prob > 0) & (prob < 1) & np.isfinite(w)
    return np.where(ok, low, np.nan), np.where(ok, high, np.nan)


def _median(sf, level) -> dict:
    estimate = sf.quantile(0.5)
    with np.errstate(divide="ignore", invalid="ignore"):
        low, high = sf.quantile_ci(0.5, alpha=1 - level, method="cloglog") if len(sf.surv_prob) else (np.nan, np.nan)
    out = {"estimate": _bound(estimate, estimate), "low": _bound(low, estimate), "high": _bound(high, estimate),
           "level": level, "method": MEDIAN}
    if np.any(np.abs(sf.surv_prob - 0.5) < 1e-12):
        out["note"] = ("the curve equals 0.5 over an interval: the median is the first time below 0.5; other "
                       "programs report the start or the middle of that interval")
    return out


def km_table(data, group=None, *, times, level=0.95, labels=None) -> dict:
    """Kaplan-Meier estimate per level of group, or of all rows. times: the print times of the number at risk, chosen
    with the user (at risk at t: time >= t, or entry < t <= time). labels: {level: [names the text uses for it]}, read
    by check_survival.py; default the level itself."""
    _one_cause(data, "1 - KM")
    sets, _, excluded, _ = _split(data, group)
    t_all, status, events, entry = _arrays(data)
    times = [float(x) for x in times]
    z, groups = NormalDist().inv_cdf(0.5 + level / 2), {}
    for name, mask in sets:
        t, s, e = t_all[mask], status[mask], None if entry is None else entry[mask]
        sf = SurvfuncRight(t, s, entry=e)
        low, high = _band(sf.surv_prob, sf.surv_prob_se, z)
        censored = np.sort(t[s == 0])
        steps = np.concatenate(([1.0], sf.surv_prob))                # before the first event, then after each one
        marks, lowest = steps[np.searchsorted(sf.surv_times, censored, side="right")], float(steps.min())
        fu = SurvfuncRight(t, (events[mask] == 0).astype(float), entry=e).quantile(0.5)
        groups[name] = {
            "n": _n(data, mask), "events": int(s.sum()), "censored": int(np.sum(events[mask] == 0)),
            "median": _median(sf, level), "lowest": lowest, "below_half": lowest < 0.5,
            "at_risk": {"times": times, "counts": [int(np.sum((t >= x) & (e is None or e < x))) for x in times]},
            "followup": {"median": _bound(fu, fu), "longest": float(t.max()), "method": FOLLOWUP},
            "labels": [str(v) for v in (labels or {}).get(name, [name])],
            "_curve": {"start": 0.0 if e is None else float(e.min()), "end": float(t.max()), "time": sf.surv_times,
                       "surv": sf.surv_prob, "low": low, "high": high, "censored": (censored, marks)}}
    return {"kind": "km", **_context(data["context"], excluded), "group_column": group, "level": level, "band": BAND,
            "times": times, "groups": groups, "_source": data["context"]["source"]}


def logrank(data, group, *, strata=None, weight_type=None, fh_p=None) -> dict:
    """survdiff across the levels of group, stratified by strata; competing codes count as censored (cause-specific).
    survdiff returns only the statistic and p: df is groups - 1. weight_type None is the log-rank test; "gb", "tw" or
    "fh" (with fh_p) only when the plan says so."""
    if weight_type not in WEIGHTS or (weight_type == "fh") != (fh_p is not None):
        raise ValueError("weight_type is None, 'gb', 'tw' or 'fh'; fh_p goes with 'fh' only")
    sets, codes, excluded, keep = _split(data, group, [strata] if strata else [])
    if len(sets) < 2:
        raise ValueError(f"{group} has fewer than two levels with data")
    t, status, _, entry = _arrays(data)
    if entry is not None and strata:
        raise ValueError("statsmodels' survdiff does not split entry times by stratum: no stratified log-rank test "
                         "with entry times here")
    statistic, p = survdiff(t[keep], status[keep], codes[group][keep], weight_type=weight_type,
                            strata=codes[strata][keep] if strata else None,
                            entry=None if entry is None else entry[keep], **({} if fh_p is None else {"fh_p": fh_p}))
    return {"kind": "logrank", **_context(data["context"], excluded), "group_column": group, "strata": strata,
            "competing_censored": data["context"]["competing"],
            "weights": WEIGHTS[weight_type] + (f", p = {fh_p}" if fh_p is not None else ""),
            "statistic": float(statistic), "df": len(sets) - 1, "p": float(p),
            "groups": {name: {"n": _n(data, mask), "events": int(status[mask].sum())} for name, mask in sets}}


def cox(data, covariates, *, reference=None, strata=None, level=0.95) -> dict:
    """Cox proportional hazards model: PHReg with ties="efron" and missing="raise", after the rows with a missing
    value in a model column are left out and listed. reference names the reference level of every categorical
    covariate ({"arm": "surgery"}); any other covariate must hold numbers. A level without events is refused: it has
    no hazard ratio. Competing codes count as censored: a cause-specific model of code 1."""
    covariates, reference = list(covariates), {k: _code(v) for k, v in (reference or {}).items()}
    if not covariates or len(set(covariates)) < len(covariates) or set(reference) - set(covariates):
        raise ValueError("covariates are distinct columns, and reference names only covariates")
    _, codes, excluded, keep = _split(data, None, covariates + ([strata] if strata else []))
    t, status, _, entry = (a if a is None else a[keep] for a in _arrays(data))
    columns, parameters = [], []
    for var in covariates:
        values = codes[var][keep]
        if var not in reference:
            try:
                columns.append(values.astype(float))
            except ValueError:
                raise ValueError(f"{var} holds text: name its reference level, reference={{{var!r}: ...}}") from None
            parameters.append({"name": var, "variable": var, "level": None, "reference": None})
            continue
        levels = _levels(values)
        if reference[var] not in levels:
            raise ValueError(f"the reference {reference[var]!r} is not a level of {var} ({', '.join(levels)})")
        for lvl in levels:
            if not status[values == lvl].sum():
                raise ValueError(f"{var} = {lvl} has no events in its {int(np.sum(values == lvl))} rows, so it has no "
                                 "hazard ratio: merge it with another level or leave it out; the user decides")
            if lvl != reference[var]:
                columns.append((values == lvl).astype(float))
                parameters.append({"name": f"{var}[{lvl}]", "variable": var, "level": lvl, "reference": reference[var]})
    x = np.column_stack(columns)
    if not np.isfinite(x).all() or np.linalg.matrix_rank(x) < x.shape[1]:
        raise ValueError("the covariates are not finite numbers, or are collinear (a constant or duplicated column)")
    shifted = None if entry is None else entry + 1e-9 * max(float(t.max()), 1.0)
    model = PHReg(t, x, status=status, entry=shifted, strata=codes[strata][keep] if strata else None,
                  ties="efron", missing="raise")
    fit = model.fit()
    beta, se = np.asarray(fit.params, float), np.asarray(fit.bse, float)
    step = np.asarray(fit.cov_params(), float) @ model.score(beta)
    z, events, k = NormalDist().inv_cdf(0.5 + level / 2), int(status.sum()), len(parameters)
    for j, p in enumerate(parameters):
        p.update(hr=math.exp(beta[j]), low=math.exp(beta[j] - z * se[j]), high=math.exp(beta[j] + z * se[j]),
                 p=float(fit.pvalues[j]), coef=float(beta[j]), se=float(se[j]))
    return {"kind": "cox", **_context(data["context"], excluded), "ties": "efron", "missing": FILTER,
            "competing_censored": data["context"]["competing"], "strata": strata, "level": level, "n": _n(data, keep),
            "events": events, "parameters": parameters,
            "events_per_parameter": {"events": events, "parameters": k, "ratio": round(events / k, 2)},
            "converged": bool(np.all(np.abs(step) < 1e-6 * (1 + np.abs(beta)))), "_fit": fit, "_time": t,
            "_status": status, "_entry": entry, "_source": data["context"]["source"]}


def _transform(kind, t, model):
    if kind == "identity":
        return t.copy()
    if kind == "log":
        if np.any(t <= 0):
            raise ValueError("the log transform needs event times above 0")
        return np.log(t)
    if kind == "rank":
        return stats.rankdata(t)
    sf = SurvfuncRight(model["_time"], model["_status"], entry=model["_entry"])
    return 1 - sf.surv_prob[np.searchsorted(sf.surv_times, t, side="right") - 1]


def ph_test(cox_result, *, model, transform="km", plot=True) -> dict:
    """Grambsch-Therneau test of proportional hazards for a cox() result, per parameter and global, and the scaled
    Schoenfeld residuals against the transformed time (plot: True, False, or a list of parameter names). It is a
    description, not a gate: report it with the plot and the alternative the plan fixed. model is the id the Cox
    result is recorded under."""
    if transform not in TRANSFORMS:
        raise ValueError(f"transform is one of {', '.join(TRANSFORMS)}")
    fit, residuals = cox_result["_fit"], np.asarray(cox_result["_fit"].schoenfeld_residuals, float)
    rows = np.isfinite(residuals).all(axis=1)                      # censored rows are NaN
    r, t, beta = residuals[rows], cox_result["_time"][rows], np.asarray(fit.params, float)
    v = np.asarray(fit.cov_params(), float)
    d, k = r.shape
    g = _transform(transform, t, cox_result)
    centred, spread = g - g.mean(), float(np.sum((g - g.mean()) ** 2))
    if d < 3 or spread <= 0:
        raise ValueError("fewer than three events, or all at one transformed time: no test")
    u = centred @ r
    per, overall = d * (u @ v) ** 2 / (np.diag(v) * spread), float(d * u @ v @ u / spread)
    names = [p["name"] for p in cox_result["parameters"]]
    chosen = names if plot is True else [n for n in names if n in (plot or [])]
    if plot not in (True, False, None) and len(chosen) < len(plot):
        raise ValueError(f"plot names a parameter the model lacks; it has {', '.join(names)}")
    out = {"kind": "ph_test", **{key: cox_result[key] for key in CONTEXT}, "model": model, "n": cox_result["n"],
           "events": d, "transform": transform, "transform_text": TRANSFORMS[transform][0], "method": PH_METHOD,
           "global": {"statistic": overall, "df": k, "p": float(stats.chi2.sf(overall, k))},
           "parameters": [{"name": n, "statistic": float(s), "df": 1, "p": float(stats.chi2.sf(s, 1))}
                          for n, s in zip(names, per)], "plot": "not drawn"}
    if len(np.unique(t)) < d:
        out["note"] = TIED
    if chosen:
        try:
            label = TRANSFORMS[transform][1].format(unit=cox_result["time_unit"])
            out["plot"] = _ph_figure(model, [names.index(n) for n in chosen], names, g, d * r @ v + beta, beta, label,
                                     cox_result["_source"])
        except ImportError as exc:
            out["plot"] = f"not_checked: {exc}"
    return out


def _figure(width_mm, height_mm) -> tuple:
    import rz_figure
    from matplotlib.figure import Figure
    rz_figure.apply_style()
    return rz_figure, Figure(figsize=rz_figure.figsize_mm(width_mm, height_mm))


def _save(rf, fig, name, source) -> str:
    main = getattr(sys.modules.get("__main__"), "__file__", None)
    return rf.save(fig, re.sub(r"[^A-Za-z0-9._-]+", "-", name), data=[source] if source else [], out=OUT, quiet=True,
                   script=main if main and Path(main).is_file() else None)["outputs"][1]["path"]


def _ph_figure(model, chosen, names, g, scaled, beta, xlabel, source) -> str:
    from statsmodels.nonparametric.smoothers_lowess import lowess
    columns, rows = (1, 1) if len(chosen) == 1 else (2, math.ceil(len(chosen) / 2))
    rf, fig = _figure(89 * columns, 55 * rows)
    for panel, j in enumerate(chosen):
        ax = fig.add_subplot(rows, columns, panel + 1)
        ax.plot(g, scaled[:, j], linestyle="none", marker="o", markersize=2, color="#999999")
        smooth = lowess(scaled[:, j], g, it=0)                     # no robust reweighting: a mean of beta(t)
        ax.plot(smooth[:, 0], smooth[:, 1], color=rf.PALETTE["blue"])
        ax.axhline(beta[j], color="black", linestyle="--", linewidth=0.8)
        ax.set(xlabel=xlabel, ylabel=f"Beta(t), {names[j]}")
        if len(chosen) > 1:
            ax.text(-0.2, 1.02, "abcdefghijklmnopqrstuvwxyz"[panel % 26], transform=ax.transAxes, fontweight="bold")
    return _save(rf, fig, f"ph-{model}", source)


def rmst(data, group=None, *, tau, reference=None, level=0.95) -> dict:
    """Restricted mean survival time up to tau per level of group, and each level minus the reference level with
    its interval and z test. tau must lie within every group's follow-up (at most its longest time)."""
    _one_cause(data, "RMST", entry=False)
    sets, _, excluded, _ = _split(data, group)
    t_all, status, _, _ = _arrays(data)
    longest = {name: float(t_all[mask].max()) for name, mask in sets}
    if tau <= 0 or tau > min(longest.values()):
        raise ValueError(f"tau must lie within every group's follow-up: at most {min(longest.values()):g} "
                         f"{data['context']['time_unit']} (longest times: {longest})")
    if group and reference not in longest:
        raise ValueError(f"reference must be one of {', '.join(longest)}")
    z, groups = NormalDist().inv_cdf(0.5 + level / 2), {}
    for name, mask in sets:
        sf = SurvfuncRight(t_all[mask], status[mask])
        inside = sf.surv_times <= tau
        edges = np.concatenate(([0.0], sf.surv_times[inside], [tau]))
        areas = np.concatenate(([1.0], sf.surv_prob[inside])) * np.diff(edges)
        after = np.cumsum(areas[::-1])[::-1][1:]                        # area from each event time to tau
        n, d = sf.n_risk[inside].astype(float), sf.n_events[inside].astype(float)
        ok = n > d
        se, value = math.sqrt(float(np.sum(after[ok] ** 2 * d[ok] / (n[ok] * (n[ok] - d[ok]))))), float(areas.sum())
        groups[name] = {"n": _n(data, mask), "events": int(status[mask].sum()), "rmst": value, "se": se,
                        "low": value - z * se, "high": value + z * se, "longest": longest[name]}
    differences = {}
    for name in [g for g in groups if g != reference] if group else []:
        a, b = groups[name], groups[reference]
        value, se = a["rmst"] - b["rmst"], math.hypot(a["se"], b["se"])
        differences[name] = {"value": value, "se": se, "low": value - z * se, "high": value + z * se,
                             "p": 2 * NormalDist().cdf(-abs(value) / se) if se > 0 else 1.0}
    return {"kind": "rmst", **_context(data["context"], excluded), "group_column": group, "reference": reference,
            "tau": float(tau), "level": level, "method": RMST, "groups": groups, "differences": differences}


def cif(data, *, cause=1, group=None, times, level=0.95) -> dict:
    """Cumulative incidence of the event code cause at the given times, per level of group, with the other codes
    above 0 as competing events (Aalen-Johansen)."""
    if data["context"]["entry"]:
        raise ValueError("the cumulative incidence here needs data without entry times")
    sets, _, excluded, _ = _split(data, group)
    t_all, _, events, _ = _arrays(data)
    z, groups = NormalDist().inv_cdf(0.5 + level / 2), {}
    for name, mask in sets:
        t, e = t_all[mask], events[mask]
        found, at = CumIncidenceRight(t, e.astype(float)) if e.max() >= cause else None, []
        for x in times:
            i = -1 if found is None else int(np.searchsorted(found.times, x, side="right")) - 1
            f, se = (float(found.cinc[cause - 1][i]), float(found.cinc_se[cause - 1][i])) if i >= 0 else (0.0, 0.0)
            low, high = (float(b[0]) if np.isfinite(b[0]) else None for b in _band(np.array([f]), np.array([se]), z))
            at.append({"time": float(x), "cif": f, "se": se, "low": low, "high": high})
        groups[name] = {"n": _n(data, mask), "events": {str(c): int(np.sum(e == c)) for c in sorted(set(e) - {0})},
                        "at": at}
    return {"kind": "cif", **_context(data["context"], excluded), "group_column": group, "cause": cause,
            "level": level, "method": CIF, "times": [float(x) for x in times], "groups": groups}


def schoenfeld_events(hr, *, alpha=0.05, power=0.8, allocation=0.5, sides=2, event_probability=None,
                      probability_source=None, path=None) -> dict:
    """Events needed to detect hazard ratio hr between two groups (Schoenfeld):
    D = (z(1 - alpha/sides) + z(power))^2 / (p (1 - p) ln(hr)^2), p the share allocated to one group. Patients =
    D / event_probability, only with the probability's source. path: also write the result there as JSON (name it
    survival/power-<name>.json so that check_survival.py looks its numbers up)."""
    if not (hr > 0 and hr != 1 and 0 < alpha < 1 and 0 < power < 1 and 0 < allocation < 1 and sides in (1, 2)):
        raise ValueError("hr > 0 and not 1; alpha, power and allocation between 0 and 1; sides 1 or 2")
    z = NormalDist().inv_cdf
    exact = (z(1 - alpha / sides) + z(power)) ** 2 / (allocation * (1 - allocation) * math.log(hr) ** 2)
    out = {"kind": "events", "formula": "D = (z(1 - alpha/sides) + z(power))^2 / (p (1 - p) ln(HR)^2)", "hr": hr,
           "alpha": alpha, "sides": sides, "power": power, "allocation": allocation, "events_exact": exact,
           "events": math.ceil(exact - 1e-9)}
    if event_probability is not None:
        if not (0 < event_probability <= 1 and isinstance(probability_source, str) and probability_source.strip()):
            raise ValueError("event_probability lies in (0, 1] and needs probability_source, where it comes from")
        out.update(event_probability=event_probability, probability_source=probability_source.strip(),
                   patients=math.ceil(out["events"] / event_probability - 1e-9))
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def km_figure(km, name, *, width_mm=89, height_mm=80, xlabel=None, ylabel="Survival probability", band=True) -> str:
    """The curves of km_table() with censoring marks and the pointwise band, and under them the number at risk at
    km["times"], both from the same table. Saved through rz_figure as survival/<name>.pdf, .png and .figure.json;
    returns the PNG's path."""
    rf, fig = _figure(width_mm, height_mm)
    keys = list(km["groups"])
    ax, table = fig.subplots(2, 1, height_ratios=[4, 0.5 + 0.4 * len(keys)])
    for i, key in enumerate(keys):
        g, style = km["groups"][key], rf.series_style(i)
        c, color, y = g["_curve"], style["color"], np.concatenate(([1.0], g["_curve"]["surv"]))
        ax.step(np.concatenate(([c["start"]], c["time"], [c["end"]])), np.append(y, y[-1]), where="post", color=color,
                linestyle=style["linestyle"], label=g["labels"][0])
        if band and len(c["time"]):
            ax.fill_between(np.append(c["time"], c["end"]), *(np.append(c[k], c[k][-1]) for k in ("low", "high")),
                            step="post", color=color, alpha=0.15, linewidth=0)
        ax.plot(*c["censored"], linestyle="none", marker="|", markersize=4, color=color)
        for x, count in zip(g["at_risk"]["times"], g["at_risk"]["counts"]):
            table.text(x, i, str(count), ha="center", va="center", color=color)
    for axis in (ax, table):
        axis.set_xlim(0, max(max(km["times"]), max(g["_curve"]["end"] for g in km["groups"].values())))
        axis.set_xticks(km["times"])
    ax.set(ylim=(0, 1.02), ylabel=ylabel, xlabel=xlabel or f"Time ({km['time_unit']})")
    if len(keys) > 1:
        ax.legend(loc="lower left")
    table.set(ylim=(len(keys) - 0.5, -0.5), yticks=range(len(keys)),
              yticklabels=[km["groups"][k]["labels"][0] for k in keys])
    table.tick_params(bottom=False, labelbottom=False, left=False)
    table.spines[:].set_visible(False)
    table.set_title("Number at risk", loc="left")
    return _save(rf, fig, name, km.get("_source"))


def _public(value):
    if isinstance(value, dict):
        return {k: _public(v) for k, v in value.items() if not str(k).startswith("_")}
    return [_public(v) for v in value] if isinstance(value, list) else value


def _interval(low, high, level):
    return {"low": low, "high": high, "level": level} if isinstance(low, float) and isinstance(high, float) else None


def fields(result, *, group=None, parameter=None) -> dict:
    """The keyword arguments of rz_results.record() for one result: test, unit, n, estimate, interval, statistic,
    df, p, effect_size and extra={"survival": ...}. km, cif: one group per record (group=). cox: the parameter to
    report (parameter=, default the first). rmst: the group compared with the reference (group=), or the one group.
    The p-values of the log-rank and proportional-hazards tests stay in extra: they describe, so the record has none."""
    kind, extra, level, unit = result.get("kind"), _public(result), result.get("level"), result.get("time_unit")
    out = {"unit": result["subject"], "extra": {"survival": extra}}
    choices = {"km": result.get("groups"), "cif": result.get("groups"), "rmst": result.get("differences"),
               "cox": {p["name"]: p for p in result.get("parameters", [])}}.get(kind) or {}
    key = group if kind != "cox" else parameter
    if key is not None and key not in choices:
        raise ValueError(f"{'parameter' if kind == 'cox' else 'group'} is one of {', '.join(map(str, choices))}")
    key = next(iter(choices), None) if key is None else key
    if kind in ("km", "cif"):
        g = extra.pop("groups")[key]
        extra.update(group={"column": result["group_column"], "value": key}, **g)
        out["n"] = {"patients": g["n"]}
    if kind == "km":
        m, reached = g["median"], isinstance(g["median"]["estimate"], float)
        out.update(test="Kaplan-Meier estimate" + (" with entry times" if result["entry"] else ""),
                   estimate={"name": "median survival time", "value": m["estimate"], "units": unit} if reached else
                   {"name": "lowest Kaplan-Meier estimate (the median was not reached)", "value": g["lowest"],
                    "units": "proportion"}, interval=_interval(m["low"], m["high"], level) if reached else None)
    elif kind == "cif":
        last = g["at"][-1]
        out.update(test="Aalen-Johansen cumulative incidence", interval=_interval(last["low"], last["high"], level),
                   estimate={"name": f"cumulative incidence of event {result['cause']} at {last['time']:g} {unit}",
                             "value": last["cif"], "units": "proportion"})
    elif kind in ("logrank", "ph_test"):
        test = result if kind == "logrank" else result["global"]
        out.update(test=("stratified " if result.get("strata") else "") + result["weights"] if kind == "logrank" else
                   f"Grambsch-Therneau test of proportional hazards (time transform: {result['transform']})",
                   estimate={"name": "chi-square statistic", "value": test["statistic"], "units": "unitless"},
                   statistic={"name": "chi2", "value": test["statistic"]}, df=test["df"],
                   n={k: v["n"] for k, v in result["groups"].items()} if kind == "logrank" else
                   {"patients": result["n"], "events": result["events"]})
    elif kind == "cox":
        p, extra["reported"] = choices[key], key
        versus = f"{p['level']} vs {p['reference']}" if p["reference"] else f"per unit of {p['variable']}"
        out.update(test="Cox proportional hazards model, Efron ties" + (", stratified" if result["strata"] else ""),
                   n={"patients": result["n"], "events": result["events"]},
                   estimate={"name": f"hazard ratio, {p['variable']} {versus}", "value": p["hr"], "units": "ratio"},
                   interval=_interval(p["low"], p["high"], level), p=p["p"], effect_size="estimate",
                   statistic={"name": "z", "value": p["coef"] / p["se"]})
    elif kind == "rmst" and key is None:                                # one group: its RMST, no test
        g = next(iter(result["groups"].values()))
        out.update(test="restricted mean survival time", n={"patients": g["n"]},
                   estimate={"name": f"RMST up to {result['tau']:g} {unit}", "value": g["rmst"], "units": unit},
                   interval=_interval(g["low"], g["high"], level))
    elif kind == "rmst":
        d, ref, extra["reported"] = choices[key], result["reference"], key
        out.update(test="restricted mean survival time", n={k: result["groups"][k]["n"] for k in (key, ref)},
                   estimate={"name": f"RMST difference, {key} minus {ref}, up to {result['tau']:g} {unit}",
                             "value": d["value"], "units": unit}, interval=_interval(d["low"], d["high"], level),
                   statistic={"name": "z", "value": d["value"] / d["se"] if d["se"] else 0.0}, p=d["p"],
                   effect_size="estimate")
    else:
        raise ValueError("fields() takes a result of km_table, logrank, cox, ph_test, rmst or cif")
    return out
